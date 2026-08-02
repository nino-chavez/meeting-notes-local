//! Private verified one-shot transport for `note.project`.
//!
//! This owns only an ephemeral child lifetime.  It writes no application data,
//! receipts, locks, or diagnostics and is deliberately not registered with the
//! desktop command surface.

#![cfg_attr(
    not(test),
    expect(dead_code, reason = "private until the retrieval command is admitted")
)]

use std::fs::{self, File};
use std::io::{self, BufRead, BufReader, Read, Write};
use std::os::fd::{FromRawFd, RawFd};
use std::os::unix::fs::MetadataExt;
use std::os::unix::process::CommandExt;
use std::path::{Component, Path, PathBuf};
use std::process::{Child, Command, ExitStatus, Stdio};
use std::sync::mpsc;
use std::thread::JoinHandle;
use std::time::{Duration, Instant};

use serde::Serialize;
use sha2::{Digest, Sha256};

use crate::meeting::valid_opaque_id;
use crate::note_projection::{
    MAX_PROJECTION_FRAME_BYTES, NoteProjector, ProjectRequest, ProjectTransportError, StrictJson,
    array, exact_object, strict_json, string, u64_value,
};
use crate::supervision::{ProcessInspection, ProcessInspector, SystemProcessInspector};

const READY_TIMEOUT: Duration = Duration::from_secs(10);
const PROJECT_TIMEOUT: Duration = Duration::from_secs(30);
const CLEANUP_GRACE: Duration = Duration::from_millis(750);
const MAX_STDERR_BYTES: usize = 16 * 1024;
const MAX_MANIFEST_BYTES: u64 = 1024 * 1024;

pub(crate) struct ProcessNoteProjector {
    storage_root: PathBuf,
    manifest_path: PathBuf,
}

impl ProcessNoteProjector {
    pub(crate) fn new(storage_root: PathBuf, manifest_path: PathBuf) -> Self {
        Self {
            storage_root,
            manifest_path,
        }
    }

    fn project_inner(&self, request: &ProjectRequest) -> Result<Vec<u8>, ()> {
        validate_storage_root(&self.storage_root)?;
        validate_request(request)?;
        let runtime = verify_manifest(&self.manifest_path)?;
        let (read_fd, write_fd) = create_liveness_pipe().map_err(|_| ())?;
        let mut command = Command::new(&runtime.executable);
        command
            .args(["-I", "-S", "-E", "-s", "-B"])
            .arg(&runtime.bridge)
            .arg("--temporary-private-root")
            .arg(&self.storage_root)
            .arg("--note-runtime-manifest")
            .arg(&self.manifest_path)
            .arg("--parent-liveness-fd")
            .arg(read_fd.to_string())
            .current_dir(&runtime.resource_root)
            .env_clear()
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());
        unsafe {
            command.pre_exec(move || {
                if libc::setpgid(0, 0) != 0 {
                    return Err(io::Error::last_os_error());
                }
                Ok(())
            });
        }
        let mut child = match command.spawn() {
            Ok(child) => child,
            Err(_) => {
                unsafe {
                    libc::close(read_fd);
                    libc::close(write_fd);
                }
                return Err(());
            }
        };
        unsafe { libc::close(read_fd) };
        let liveness = unsafe { File::from_raw_fd(write_fd) };
        let (stdin, stdout, stderr) =
            match (child.stdin.take(), child.stdout.take(), child.stderr.take()) {
                (Some(stdin), Some(stdout), Some(stderr)) => (stdin, stdout, stderr),
                _ => {
                    drop(liveness);
                    let group = child.id() as i32;
                    let _ = signal_group(group, libc::SIGTERM);
                    if !wait_for_group_exit(&mut child, group, CLEANUP_GRACE) {
                        let _ = signal_group(group, libc::SIGKILL);
                        let _ = child.wait();
                    }
                    return Err(());
                }
            };
        let stderr_thread = std::thread::spawn(move || drain_stderr(stderr));
        let mut guard = ChildGuard::new(child, liveness, stderr_thread);
        let ready_deadline = Instant::now() + READY_TIMEOUT;
        verify_spawned_identity(guard.pid(), &runtime)?;

        let (ready_sender, ready_receiver) = mpsc::sync_channel(1);
        let ready_thread = std::thread::spawn(move || {
            let mut reader = BufReader::new(stdout);
            let frame = read_bounded_line(&mut reader);
            let _ = ready_sender.send((frame, reader));
        });
        let (ready, reader) = match ready_receiver
            .recv_timeout(ready_deadline.saturating_duration_since(Instant::now()))
        {
            Ok(value) => value,
            Err(_) => {
                guard.abort();
                let _ = ready_thread.join();
                return Err(());
            }
        };
        let _ = ready_thread.join();
        let ready = ready.map_err(|_| ())?;
        parse_ready(&ready, &runtime.manifest_sha256)?;

        let command = project_command(request)?;
        let mut stdin = stdin;
        stdin.write_all(&command).map_err(|_| ())?;
        drop(stdin);

        let project_deadline = Instant::now() + PROJECT_TIMEOUT;
        let (result_sender, result_receiver) = mpsc::sync_channel(1);
        let result_thread = std::thread::spawn(move || {
            let result = read_to_exact_eof(reader);
            let _ = result_sender.send(result);
        });
        let result = match result_receiver
            .recv_timeout(project_deadline.saturating_duration_since(Instant::now()))
        {
            Ok(result) => result,
            Err(_) => {
                guard.abort();
                let _ = result_thread.join();
                return Err(());
            }
        };
        let _ = result_thread.join();
        let result = result.map_err(|_| ())?;
        if !guard.finish_success(project_deadline)? {
            return Err(());
        }
        Ok(result)
    }
}

impl NoteProjector for ProcessNoteProjector {
    fn project(&self, request: &ProjectRequest) -> Result<Vec<u8>, ProjectTransportError> {
        self.project_inner(request)
            .map_err(|_| ProjectTransportError)
    }
}

struct VerifiedRuntime {
    resource_root: PathBuf,
    executable: PathBuf,
    executable_sha256: String,
    bridge: PathBuf,
    manifest_sha256: String,
}

struct RuntimeResource {
    relative_path: String,
    sha256: String,
}

fn verify_manifest(path: &Path) -> Result<VerifiedRuntime, ()> {
    if !path.is_absolute() {
        return Err(());
    }
    let resource_root = path.parent().ok_or(())?.to_path_buf();
    require_owned_directory(&resource_root)?;
    require_owned_file(path)?;
    let metadata = path.metadata().map_err(|_| ())?;
    if metadata.len() > MAX_MANIFEST_BYTES {
        return Err(());
    }
    let bytes = fs::read(path).map_err(|_| ())?;
    if bytes.len() as u64 != metadata.len() || bytes.contains(&b'\\') {
        return Err(());
    }
    let root = strict_json(&bytes).map_err(|_| ())?;
    let fields = exact_object(
        &root,
        [
            "schema",
            "role",
            "runtime",
            "bridge",
            "validator",
            "generator",
            "models",
        ],
    )
    .map_err(|_| ())?;
    if string(fields[0]).map_err(|_| ())? != "note-runtime/1"
        || string(fields[1]).map_err(|_| ())? != "project"
        || !matches!(fields[5], StrictJson::Null)
        || !array(fields[6]).map_err(|_| ())?.is_empty()
    {
        return Err(());
    }
    let runtime = parse_resource(fields[2])?;
    let bridge = parse_resource(fields[3])?;
    let validator = parse_resource(fields[4])?;
    if canonical_manifest(&runtime, &bridge, &validator).as_bytes() != bytes {
        return Err(());
    }
    let executable = verify_resource(&resource_root, &runtime)?;
    let bridge_path = verify_resource(&resource_root, &bridge)?;
    let _validator_path = verify_resource(&resource_root, &validator)?;
    Ok(VerifiedRuntime {
        resource_root,
        executable,
        executable_sha256: runtime.sha256,
        bridge: bridge_path,
        manifest_sha256: format!("{:x}", Sha256::digest(&bytes)),
    })
}

fn parse_resource(value: &StrictJson) -> Result<RuntimeResource, ()> {
    let fields = exact_object(value, ["relative_path", "sha256"]).map_err(|_| ())?;
    let relative_path = string(fields[0]).map_err(|_| ())?.to_owned();
    let sha256 = string(fields[1]).map_err(|_| ())?.to_owned();
    if !valid_relative_path(&relative_path) || !valid_digest(&sha256) {
        return Err(());
    }
    Ok(RuntimeResource {
        relative_path,
        sha256,
    })
}

fn canonical_manifest(
    runtime: &RuntimeResource,
    bridge: &RuntimeResource,
    validator: &RuntimeResource,
) -> String {
    format!(
        "{{\n  \"schema\": \"note-runtime/1\",\n  \"role\": \"project\",\n  \"runtime\": {{\n    \"relative_path\": \"{}\",\n    \"sha256\": \"{}\"\n  }},\n  \"bridge\": {{\n    \"relative_path\": \"{}\",\n    \"sha256\": \"{}\"\n  }},\n  \"validator\": {{\n    \"relative_path\": \"{}\",\n    \"sha256\": \"{}\"\n  }},\n  \"generator\": null,\n  \"models\": []\n}}",
        runtime.relative_path,
        runtime.sha256,
        bridge.relative_path,
        bridge.sha256,
        validator.relative_path,
        validator.sha256,
    )
}

fn verify_resource(root: &Path, resource: &RuntimeResource) -> Result<PathBuf, ()> {
    let mut current = root.to_path_buf();
    let parts: Vec<_> = Path::new(&resource.relative_path).components().collect();
    for (index, component) in parts.iter().enumerate() {
        let Component::Normal(component) = component else {
            return Err(());
        };
        current.push(component);
        let metadata = fs::symlink_metadata(&current).map_err(|_| ())?;
        if metadata.uid() != unsafe { libc::geteuid() }
            || metadata.file_type().is_symlink()
            || (index + 1 < parts.len() && !metadata.is_dir())
            || (index + 1 == parts.len() && !metadata.is_file())
        {
            return Err(());
        }
    }
    let bytes = fs::read(&current).map_err(|_| ())?;
    if format!("{:x}", Sha256::digest(&bytes)) != resource.sha256 {
        return Err(());
    }
    Ok(current)
}

fn require_owned_file(path: &Path) -> Result<(), ()> {
    let metadata = fs::symlink_metadata(path).map_err(|_| ())?;
    if !metadata.is_file()
        || metadata.file_type().is_symlink()
        || metadata.uid() != unsafe { libc::geteuid() }
    {
        return Err(());
    }
    Ok(())
}

fn require_owned_directory(path: &Path) -> Result<(), ()> {
    let metadata = fs::symlink_metadata(path).map_err(|_| ())?;
    if !metadata.is_dir()
        || metadata.file_type().is_symlink()
        || metadata.uid() != unsafe { libc::geteuid() }
    {
        return Err(());
    }
    Ok(())
}

fn validate_storage_root(path: &Path) -> Result<(), ()> {
    if !path.is_absolute() {
        return Err(());
    }
    let metadata = fs::symlink_metadata(path).map_err(|_| ())?;
    if !metadata.is_dir()
        || metadata.file_type().is_symlink()
        || metadata.uid() != unsafe { libc::geteuid() }
        || metadata.mode() & 0o777 != 0o700
    {
        return Err(());
    }
    Ok(())
}

fn validate_request(request: &ProjectRequest) -> Result<(), ()> {
    if !valid_opaque_id(&request.meeting_id)
        || !valid_digest(&request.note_json_sha256)
        || !valid_digest(&request.note_markdown_sha256)
        || !valid_digest(&request.transcript_sha256)
    {
        return Err(());
    }
    Ok(())
}

fn valid_relative_path(value: &str) -> bool {
    !value.is_empty()
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'.' | b'_' | b'-' | b'/'))
        && value
            .split('/')
            .all(|component| !component.is_empty() && !matches!(component, "." | ".."))
}

fn valid_digest(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

#[derive(Serialize)]
struct ProjectCommand<'a> {
    schema: &'static str,
    request_id: String,
    operation: &'static str,
    arguments: ProjectArguments<'a>,
}

#[derive(Serialize)]
struct ProjectArguments<'a> {
    meeting_id: &'a str,
    note_id: &'a str,
    transcript_id: &'a str,
}

fn project_command(request: &ProjectRequest) -> Result<Vec<u8>, ()> {
    let command = ProjectCommand {
        schema: "note-bridge-command/1",
        request_id: request.request_id.to_string(),
        operation: "note.project",
        arguments: ProjectArguments {
            meeting_id: &request.meeting_id,
            note_id: &request.note_json_sha256,
            transcript_id: &request.transcript_sha256,
        },
    };
    let mut bytes = serde_json::to_vec(&command).map_err(|_| ())?;
    bytes.push(b'\n');
    if bytes.len() > MAX_PROJECTION_FRAME_BYTES {
        return Err(());
    }
    Ok(bytes)
}

fn parse_ready(frame: &[u8], manifest_sha256: &str) -> Result<(), ()> {
    if frame.len() > MAX_PROJECTION_FRAME_BYTES
        || !frame.ends_with(b"\n")
        || frame[..frame.len() - 1]
            .iter()
            .any(|byte| matches!(byte, b'\n' | b'\r'))
    {
        return Err(());
    }
    let root = strict_json(&frame[..frame.len() - 1]).map_err(|_| ())?;
    let fields = exact_object(
        &root,
        [
            "schema",
            "event",
            "protocol",
            "role",
            "manifest_sha256",
            "operations",
        ],
    )
    .map_err(|_| ())?;
    let operations = array(fields[5]).map_err(|_| ())?;
    if string(fields[0]).map_err(|_| ())? != "note-bridge-event/1"
        || string(fields[1]).map_err(|_| ())? != "ready"
        || u64_value(fields[2]).map_err(|_| ())? != 1
        || string(fields[3]).map_err(|_| ())? != "project"
        || string(fields[4]).map_err(|_| ())? != manifest_sha256
        || operations.len() != 1
        || string(&operations[0]).map_err(|_| ())? != "note.project"
    {
        return Err(());
    }
    Ok(())
}

fn verify_spawned_identity(pid: u32, runtime: &VerifiedRuntime) -> Result<(), ()> {
    let deadline = Instant::now() + Duration::from_secs(1);
    loop {
        match SystemProcessInspector.inspect(pid).map_err(|_| ())? {
            ProcessInspection::Identity(identity)
                if identity.executable_sha256 == runtime.executable_sha256
                    && fs::canonicalize(&identity.executable_path).map_err(|_| ())?
                        == fs::canonicalize(&runtime.executable).map_err(|_| ())? =>
            {
                return Ok(());
            }
            ProcessInspection::Unavailable if Instant::now() < deadline => {
                std::thread::sleep(Duration::from_millis(10));
            }
            _ => return Err(()),
        }
    }
}

fn read_bounded_line(reader: &mut impl BufRead) -> io::Result<Vec<u8>> {
    let mut frame = Vec::new();
    loop {
        let available = reader.fill_buf()?;
        if available.is_empty() {
            return Err(io::Error::new(io::ErrorKind::UnexpectedEof, "closed frame"));
        }
        let consumed = available
            .iter()
            .position(|byte| *byte == b'\n')
            .map_or(available.len(), |position| position + 1);
        if frame.len() + consumed > MAX_PROJECTION_FRAME_BYTES {
            return Err(io::Error::other("oversized frame"));
        }
        frame.extend_from_slice(&available[..consumed]);
        reader.consume(consumed);
        if frame.ends_with(b"\n") {
            return Ok(frame);
        }
    }
}

fn read_to_exact_eof(mut reader: impl Read) -> io::Result<Vec<u8>> {
    let mut bytes = Vec::new();
    reader
        .by_ref()
        .take(MAX_PROJECTION_FRAME_BYTES as u64 + 1)
        .read_to_end(&mut bytes)?;
    if bytes.len() > MAX_PROJECTION_FRAME_BYTES
        || !bytes.ends_with(b"\n")
        || bytes[..bytes.len() - 1]
            .iter()
            .any(|byte| matches!(byte, b'\n' | b'\r'))
    {
        return Err(io::Error::other("invalid terminal frame"));
    }
    Ok(bytes)
}

fn drain_stderr(mut stderr: impl Read) -> bool {
    let mut total = 0_usize;
    let mut buffer = [0_u8; 4096];
    loop {
        match stderr.read(&mut buffer) {
            Ok(0) => return total <= MAX_STDERR_BYTES,
            Ok(read) => total = total.saturating_add(read),
            Err(error) if error.kind() == io::ErrorKind::Interrupted => continue,
            Err(_) => return false,
        }
    }
}

struct ChildGuard {
    child: Child,
    process_group_id: i32,
    liveness: Option<File>,
    stderr_thread: Option<JoinHandle<bool>>,
    finished: bool,
}

impl ChildGuard {
    fn new(child: Child, liveness: File, stderr_thread: JoinHandle<bool>) -> Self {
        let process_group_id = child.id() as i32;
        Self {
            child,
            process_group_id,
            liveness: Some(liveness),
            stderr_thread: Some(stderr_thread),
            finished: false,
        }
    }

    fn pid(&self) -> u32 {
        self.child.id()
    }

    fn finish_success(&mut self, deadline: Instant) -> Result<bool, ()> {
        let status = loop {
            if let Some(status) = self.child.try_wait().map_err(|_| ())? {
                break status;
            }
            if Instant::now() >= deadline {
                self.abort();
                return Ok(false);
            }
            std::thread::sleep(Duration::from_millis(10));
        };
        self.liveness.take();
        if group_exists(self.process_group_id) {
            self.abort();
            return Ok(false);
        }
        let stderr_ok = self
            .stderr_thread
            .take()
            .ok_or(())?
            .join()
            .map_err(|_| ())?;
        self.finished = true;
        Ok(success(status) && stderr_ok)
    }

    fn abort(&mut self) {
        if self.finished {
            return;
        }
        self.liveness.take();
        let _ = signal_group(self.process_group_id, libc::SIGTERM);
        if !wait_for_group_exit(&mut self.child, self.process_group_id, CLEANUP_GRACE) {
            let _ = signal_group(self.process_group_id, libc::SIGKILL);
            let _ = self.child.wait();
        }
        if let Some(thread) = self.stderr_thread.take() {
            let _ = thread.join();
        }
        self.finished = true;
    }
}

impl Drop for ChildGuard {
    fn drop(&mut self) {
        self.abort();
    }
}

fn success(status: ExitStatus) -> bool {
    status.success()
}

fn wait_for_group_exit(child: &mut Child, group: i32, grace: Duration) -> bool {
    let deadline = Instant::now() + grace;
    loop {
        let _ = child.try_wait();
        if !group_exists(group) {
            return true;
        }
        if Instant::now() >= deadline {
            return false;
        }
        std::thread::sleep(Duration::from_millis(10));
    }
}

fn group_exists(group: i32) -> bool {
    let result = unsafe { libc::kill(-group, 0) };
    result == 0 || io::Error::last_os_error().raw_os_error() == Some(libc::EPERM)
}

fn signal_group(group: i32, signal: i32) -> io::Result<()> {
    if unsafe { libc::kill(-group, signal) } == 0 {
        return Ok(());
    }
    let error = io::Error::last_os_error();
    if error.raw_os_error() == Some(libc::ESRCH) {
        Ok(())
    } else {
        Err(error)
    }
}

fn create_liveness_pipe() -> io::Result<(RawFd, RawFd)> {
    let mut descriptors = [-1; 2];
    if unsafe { libc::pipe(descriptors.as_mut_ptr()) } != 0 {
        return Err(io::Error::last_os_error());
    }
    let flags = unsafe { libc::fcntl(descriptors[1], libc::F_GETFD) };
    if flags == -1
        || unsafe { libc::fcntl(descriptors[1], libc::F_SETFD, flags | libc::FD_CLOEXEC) } == -1
    {
        unsafe {
            libc::close(descriptors[0]);
            libc::close(descriptors[1]);
        }
        return Err(io::Error::last_os_error());
    }
    Ok((descriptors[0], descriptors[1]))
}

#[cfg(test)]
mod tests {
    use std::collections::BTreeMap;
    use std::io::Cursor;
    use std::os::unix::fs::PermissionsExt;

    use serde_json::Value;
    use tempfile::TempDir;
    use uuid::Uuid;

    use super::*;
    use crate::note_projection::project_claims;

    #[test]
    fn transport_result_requires_one_terminal_newline_and_exact_eof() {
        assert!(read_to_exact_eof(Cursor::new(b"{}\n".to_vec())).is_ok());
        for invalid in [
            b"{}\n\n".as_slice(),
            b"{}\n ".as_slice(),
            b"{}\n{}\n".as_slice(),
            b"{}\r\n".as_slice(),
        ] {
            assert!(read_to_exact_eof(Cursor::new(invalid.to_vec())).is_err());
        }
    }

    #[test]
    fn real_python_project_bridge_round_trip_is_read_only_with_a_prior_gated_turn() {
        let temporary = TempDir::new().unwrap();
        let base = temporary.path().canonicalize().unwrap();
        let app = base.join("app");
        let resources = base.join("resources");
        fs::create_dir(&app).unwrap();
        fs::create_dir(&resources).unwrap();
        fs::set_permissions(&app, fs::Permissions::from_mode(0o700)).unwrap();
        fs::set_permissions(&resources, fs::Permissions::from_mode(0o700)).unwrap();
        let repository = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../..")
            .canonicalize()
            .unwrap();
        let python = python_executable();
        let runtime = resources.join("python-runtime");
        fs::copy(&python, &runtime).unwrap();
        fs::set_permissions(&runtime, fs::Permissions::from_mode(0o700)).unwrap();
        let bridge = resources.join("note_bridge.py");
        fs::copy(repository.join("worker/note_bridge.py"), &bridge).unwrap();
        fs::set_permissions(&bridge, fs::Permissions::from_mode(0o600)).unwrap();
        let validator = resources.join("note-validator.zip");
        build_validator_bundle(&python, &repository, &validator);
        let meeting_id = "meeting-gated-before-visible";
        let ids = write_note_pair(&python, &repository, &app, meeting_id);
        let manifest = resources.join("note-runtime.json");
        let runtime_resource = RuntimeResource {
            relative_path: "python-runtime".into(),
            sha256: sha256_path(&runtime),
        };
        let bridge_resource = RuntimeResource {
            relative_path: "note_bridge.py".into(),
            sha256: sha256_path(&bridge),
        };
        let validator_resource = RuntimeResource {
            relative_path: "note-validator.zip".into(),
            sha256: sha256_path(&validator),
        };
        fs::write(
            &manifest,
            canonical_manifest(&runtime_resource, &bridge_resource, &validator_resource),
        )
        .unwrap();
        fs::set_permissions(&manifest, fs::Permissions::from_mode(0o600)).unwrap();
        let before = tree(&app);
        let projector = ProcessNoteProjector::new(app.clone(), manifest);
        let request = ProjectRequest {
            request_id: Uuid::new_v4(),
            meeting_id: meeting_id.into(),
            note_json_sha256: ids["note"].as_str().unwrap().into(),
            note_markdown_sha256: ids["markdown"].as_str().unwrap().into(),
            transcript_sha256: ids["transcript"].as_str().unwrap().into(),
        };
        let pack: Value = serde_json::from_slice(
            &fs::read(repository.join("docs/prototype/fixtures/accepted-note2.fixture")).unwrap(),
        )
        .unwrap();
        let visible_turns: Vec<_> = pack["transcript"]["turns"]
            .as_array()
            .unwrap()
            .iter()
            .map(|turn| turn["text"].as_str().unwrap().to_owned())
            .collect();
        let claims = match project_claims(&projector, &request, &visible_turns) {
            Ok(claims) => claims,
            Err(error) => panic!("real projection failed: {error:?}"),
        };
        assert_eq!(claims.len(), 1);
        assert_eq!(claims[0].locators[0].turn, 0);
        assert_eq!(claims[0].locators[1].turn, 1);
        assert_eq!(tree(&app), before);
        assert!(!app.join("operations").exists());
        assert!(!app.join("children").exists());
    }

    fn python_executable() -> PathBuf {
        let output = Command::new("python3")
            .args(["-c", "import sys; print(sys.executable)"])
            .output()
            .unwrap();
        assert!(output.status.success());
        PathBuf::from(String::from_utf8(output.stdout).unwrap().trim())
            .canonicalize()
            .unwrap()
    }

    fn build_validator_bundle(python: &Path, repository: &Path, target: &Path) {
        let script = r#"import sys, zipfile
from pathlib import Path
repo, target = Path(sys.argv[1]), Path(sys.argv[2])
sources = {
  'note_validator.py': repo / 'worker/note_validator.py',
  'summarize.py': repo / 'notes/summarize.py',
  'transcript.py': repo / 'notes/transcript.py',
  'capture_health.py': repo / 'spike/capture_health.py',
}
with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_STORED) as archive:
  for name, source in sources.items(): archive.writestr(name, source.read_bytes())
"#;
        let status = Command::new(python)
            .args(["-I", "-S", "-E", "-s", "-B", "-c", script])
            .arg(repository)
            .arg(target)
            .status()
            .unwrap();
        assert!(status.success());
        fs::set_permissions(target, fs::Permissions::from_mode(0o600)).unwrap();
    }

    fn write_note_pair(python: &Path, repository: &Path, app: &Path, meeting_id: &str) -> Value {
        let script = r#"import hashlib, json, os, sys
from pathlib import Path
repo, root, meeting_id = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
sys.path.insert(0, str(repo / 'notes'))
sys.path.insert(0, str(repo / 'spike'))
sys.path.insert(0, str(repo))
from capture_health import build as build_capture_health
health = build_capture_health(
  mic_samples=16000,
  system_samples=16000,
  capture_elapsed_samples=16000,
  dropouts={'mic': [], 'system': []},
  tap_errors=[],
  transcription_requested=True,
  transcript_written=True,
)
pack = json.loads((repo / 'docs/prototype/fixtures/accepted-note2.fixture').read_text())
pack['transcript']['schema'] = 'capture-transcript/1'
pack['transcript']['capture_health'] = health
pack['transcript']['voiceprint'] = None
pack['transcript']['turns'].insert(0, {'start': 0.0, 'end': 0.5, 'speaker': 'Me', 'text': 'withheld before visible evidence', 'gated': True})
transcript_bytes = (json.dumps(pack['transcript'], indent=2) + '\n').encode()
transcript_id = hashlib.sha256(transcript_bytes).hexdigest()
meeting = root / 'meetings' / meeting_id
for directory in (root / 'meetings', meeting, meeting / 'transcript', meeting / 'notes'):
  directory.mkdir(mode=0o700, exist_ok=True)
  os.chmod(directory, 0o700)
def write(path, data):
  fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
  with os.fdopen(fd, 'wb') as handle: handle.write(data)
write(meeting / 'transcript' / f'{transcript_id}.json', transcript_bytes)
markdown_bytes = pack['markdown'].encode()
markdown_id = hashlib.sha256(markdown_bytes).hexdigest()
note = pack['note']
note['meeting']['id'] = meeting_id
note['meeting']['gated_turns'] = 1
note['capture_health'] = health
note['capture_integrity_unknown'] = False
note['capture_warnings'] = []
note['transcript'] = f'../transcript/{transcript_id}.json'
note['render']['path'] = f'{markdown_id}.md'
note_bytes = (json.dumps(note, ensure_ascii=False, indent=2) + '\n').encode()
note_id = hashlib.sha256(note_bytes).hexdigest()
write(meeting / 'notes' / f'{markdown_id}.md', markdown_bytes)
write(meeting / 'notes' / f'{note_id}.json', note_bytes)
print(json.dumps({'note': note_id, 'markdown': markdown_id, 'transcript': transcript_id}))
"#;
        let output = Command::new(python)
            .args(["-I", "-S", "-E", "-s", "-B", "-c", script])
            .arg(repository)
            .arg(app)
            .arg(meeting_id)
            .output()
            .unwrap();
        assert!(
            output.status.success(),
            "{}",
            String::from_utf8_lossy(&output.stderr)
        );
        serde_json::from_slice(&output.stdout).unwrap()
    }

    fn sha256_path(path: &Path) -> String {
        format!("{:x}", Sha256::digest(fs::read(path).unwrap()))
    }

    fn tree(root: &Path) -> BTreeMap<String, String> {
        fn walk(root: &Path, path: &Path, output: &mut BTreeMap<String, String>) {
            let mut entries: Vec<_> = fs::read_dir(path).unwrap().map(Result::unwrap).collect();
            entries.sort_by_key(|entry| entry.file_name());
            for entry in entries {
                let path = entry.path();
                if path.is_dir() {
                    walk(root, &path, output);
                } else {
                    output.insert(
                        path.strip_prefix(root).unwrap().display().to_string(),
                        sha256_path(&path),
                    );
                }
            }
        }
        let mut output = BTreeMap::new();
        walk(root, root, &mut output);
        output
    }
}

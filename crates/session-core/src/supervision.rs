use std::collections::HashSet;
use std::fs::File;
use std::io::{self, BufRead, BufReader, Write};
use std::os::fd::{FromRawFd, RawFd};
use std::os::unix::process::CommandExt;
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdout, Command, Stdio};
use std::sync::mpsc;
use std::time::{Duration, Instant};

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use sysinfo::{Pid, ProcessesToUpdate, System};
use thiserror::Error;

use crate::protocol::{
    MAX_FRAME_BYTES, Operation, ProtocolError, RequestTracker, WorkerCommand, WorkerReady,
    WorkerResult, parse_ready, parse_result,
};

pub const PARENT_FD_ENV: &str = "LMN_PARENT_LIVENESS_FD";

#[derive(Debug, Error)]
pub enum SupervisionError {
    #[error("worker executable is missing")]
    MissingChild,
    #[error("worker readiness timed out")]
    ReadyTimeout,
    #[error("worker exited before readiness")]
    EarlyExit,
    #[error(transparent)]
    Protocol(#[from] ProtocolError),
    #[error(transparent)]
    Io(#[from] io::Error),
}

pub struct OwnedChild {
    child: Child,
    process_group_id: i32,
    liveness_writer: Option<File>,
    protocol_stdout: Option<BufReader<ChildStdout>>,
    requests: RequestTracker,
}

impl OwnedChild {
    pub fn spawn(command: &mut Command) -> Result<Self, SupervisionError> {
        let program = PathBuf::from(command.get_program());
        if !program.is_file() {
            return Err(SupervisionError::MissingChild);
        }
        let (read_fd, write_fd) = create_liveness_pipe()?;
        command
            .env(PARENT_FD_ENV, read_fd.to_string())
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
        let child = match command.spawn() {
            Ok(child) => child,
            Err(error) => {
                unsafe {
                    libc::close(read_fd);
                    libc::close(write_fd);
                }
                return Err(error.into());
            }
        };
        unsafe {
            libc::close(read_fd);
        }
        let liveness_writer = unsafe { File::from_raw_fd(write_fd) };
        Ok(Self {
            process_group_id: child.id() as i32,
            child,
            liveness_writer: Some(liveness_writer),
            protocol_stdout: None,
            requests: RequestTracker::default(),
        })
    }

    pub fn pid(&self) -> u32 {
        self.child.id()
    }

    pub fn process_group_id(&self) -> i32 {
        self.process_group_id
    }

    pub fn wait_ready(
        &mut self,
        timeout: Duration,
        expected_operations: &HashSet<Operation>,
    ) -> Result<WorkerReady, SupervisionError> {
        let stdout = self
            .child
            .stdout
            .take()
            .ok_or_else(|| io::Error::other("worker stdout missing"))?;
        let (sender, receiver) = mpsc::channel();
        std::thread::spawn(move || {
            let mut reader = BufReader::new(stdout);
            let result = read_bounded_frame(&mut reader);
            let _ = sender.send((result, reader));
        });
        match receiver.recv_timeout(timeout) {
            Ok((Ok(frame), reader)) if !frame.is_empty() => {
                match parse_ready(&frame, expected_operations) {
                    Ok(ready) => {
                        self.protocol_stdout = Some(reader);
                        Ok(ready)
                    }
                    Err(error) => {
                        self.stop_and_wait(Duration::from_millis(500))?;
                        Err(error.into())
                    }
                }
            }
            Ok((Ok(_), _)) | Ok((Err(_), _)) => {
                self.stop_and_wait(Duration::from_millis(500))?;
                Err(SupervisionError::EarlyExit)
            }
            Err(mpsc::RecvTimeoutError::Timeout) => {
                self.stop_and_wait(Duration::from_millis(500))?;
                Err(SupervisionError::ReadyTimeout)
            }
            Err(mpsc::RecvTimeoutError::Disconnected) => {
                self.stop_and_wait(Duration::from_millis(500))?;
                Err(SupervisionError::EarlyExit)
            }
        }
    }

    pub fn request(&mut self, command: &WorkerCommand) -> Result<WorkerResult, SupervisionError> {
        self.requests.register(command.request_id)?;
        let mut frame = serde_json::to_vec(command).map_err(|_| ProtocolError::Malformed)?;
        frame.push(b'\n');
        if frame.len() > MAX_FRAME_BYTES {
            return Err(ProtocolError::FrameTooLarge.into());
        }
        let stdin = self
            .child
            .stdin
            .as_mut()
            .ok_or_else(|| io::Error::other("worker stdin missing"))?;
        stdin.write_all(&frame)?;
        stdin.flush()?;
        let stdout = self
            .protocol_stdout
            .as_mut()
            .ok_or_else(|| io::Error::other("worker readiness not complete"))?;
        let result = parse_result(&read_bounded_frame(stdout)?)?;
        self.requests.terminal(&result)?;
        Ok(result)
    }

    pub fn stop_and_wait(&mut self, grace: Duration) -> io::Result<()> {
        self.liveness_writer.take();
        signal_group(self.process_group_id, libc::SIGTERM)?;
        let deadline = Instant::now() + grace;
        while Instant::now() < deadline {
            if self.child.try_wait()?.is_some() {
                return Ok(());
            }
            std::thread::sleep(Duration::from_millis(10));
        }
        signal_group(self.process_group_id, libc::SIGKILL)?;
        self.child.wait()?;
        Ok(())
    }
}

fn read_bounded_frame(reader: &mut impl BufRead) -> Result<Vec<u8>, SupervisionError> {
    let mut frame = Vec::new();
    loop {
        let available = reader.fill_buf()?;
        if available.is_empty() {
            return Ok(frame);
        }
        let consumed = available
            .iter()
            .position(|byte| *byte == b'\n')
            .map_or(available.len(), |position| position + 1);
        if frame.len() + consumed > MAX_FRAME_BYTES {
            return Err(ProtocolError::FrameTooLarge.into());
        }
        frame.extend_from_slice(&available[..consumed]);
        reader.consume(consumed);
        if frame.last() == Some(&b'\n') {
            return Ok(frame);
        }
    }
}

impl Drop for OwnedChild {
    fn drop(&mut self) {
        if self.child.try_wait().ok().flatten().is_none() {
            let _ = self.stop_and_wait(Duration::from_millis(250));
        }
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

fn signal_group(group: i32, signal: i32) -> io::Result<()> {
    let result = unsafe { libc::kill(-group, signal) };
    if result == 0 {
        return Ok(());
    }
    let error = io::Error::last_os_error();
    if error.raw_os_error() == Some(libc::ESRCH) {
        Ok(())
    } else {
        Err(error)
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ProcessIdentity {
    pub pid: u32,
    pub start_time_epoch_seconds: u64,
    pub executable_path: PathBuf,
    pub executable_sha256: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct OwnershipReceipt {
    pub schema: OwnershipSchema,
    pub process_group_id: i32,
    pub application_build_sha256: String,
    pub worker_build_sha256: String,
    pub tap_build_sha256: String,
    pub children: Vec<ProcessIdentity>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum OwnershipSchema {
    #[serde(rename = "capture-ownership/1")]
    V1,
}

impl OwnershipReceipt {
    pub fn validate(&self) -> bool {
        let mut pids = HashSet::new();
        self.process_group_id > 0
            && valid_sha256(&self.application_build_sha256)
            && valid_sha256(&self.worker_build_sha256)
            && valid_sha256(&self.tap_build_sha256)
            && !self.children.is_empty()
            && self
                .children
                .iter()
                .any(|child| child.pid == self.process_group_id as u32)
            && self.children.iter().all(|child| {
                child.pid > 0
                    && child.start_time_epoch_seconds > 0
                    && pids.insert(child.pid)
                    && child.executable_path.is_absolute()
                    && valid_sha256(&child.executable_sha256)
            })
    }
}

pub trait ProcessInspector {
    fn inspect(&self, pid: u32) -> io::Result<ProcessInspection>;
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ProcessInspection {
    Absent,
    Identity(ProcessIdentity),
    Unavailable,
}

pub trait GroupSignaler {
    fn terminate(&self, process_group_id: i32) -> io::Result<()>;
}

pub struct SystemProcessInspector;

impl ProcessInspector for SystemProcessInspector {
    fn inspect(&self, pid: u32) -> io::Result<ProcessInspection> {
        let mut system = System::new();
        let system_pid = Pid::from_u32(pid);
        system.refresh_processes(ProcessesToUpdate::Some(&[system_pid]), true);
        let Some(process) = system.process(system_pid) else {
            return Ok(ProcessInspection::Absent);
        };
        let Some(executable) = process.exe() else {
            return Ok(ProcessInspection::Unavailable);
        };
        let executable_sha256 = match sha256_file(executable) {
            Ok(sha256) => sha256,
            Err(_) => return Ok(ProcessInspection::Unavailable),
        };
        Ok(ProcessInspection::Identity(ProcessIdentity {
            pid,
            start_time_epoch_seconds: process.start_time(),
            executable_path: executable.to_path_buf(),
            executable_sha256,
        }))
    }
}

pub struct SystemGroupSignaler;

impl GroupSignaler for SystemGroupSignaler {
    fn terminate(&self, process_group_id: i32) -> io::Result<()> {
        signal_group(process_group_id, libc::SIGTERM)
    }
}

#[derive(Debug, PartialEq, Eq)]
pub enum RecoveryDecision {
    NoChildrenLive,
    ExactGroupSignalled,
    AmbiguousIdentity,
}

#[derive(Debug, PartialEq, Eq)]
pub enum RecoveryCompletion {
    NoChildrenLive,
    StoppedExactGroup,
    AmbiguousIdentity,
    StillRunning,
}

pub fn recover_owned_group(
    receipt: &OwnershipReceipt,
    inspector: &dyn ProcessInspector,
    signaler: &dyn GroupSignaler,
) -> io::Result<RecoveryDecision> {
    if !receipt.validate() {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "capture ownership receipt is malformed",
        ));
    }
    let mut live = 0;
    for expected in &receipt.children {
        match inspector.inspect(expected.pid)? {
            ProcessInspection::Absent => {}
            ProcessInspection::Identity(actual) => {
                live += 1;
                if &actual != expected {
                    return Ok(RecoveryDecision::AmbiguousIdentity);
                }
            }
            ProcessInspection::Unavailable => {
                return Ok(RecoveryDecision::AmbiguousIdentity);
            }
        }
    }
    if live == 0 {
        return Ok(RecoveryDecision::NoChildrenLive);
    }
    signaler.terminate(receipt.process_group_id)?;
    Ok(RecoveryDecision::ExactGroupSignalled)
}

pub fn recover_owned_group_and_wait(
    receipt: &OwnershipReceipt,
    inspector: &dyn ProcessInspector,
    signaler: &dyn GroupSignaler,
    grace: Duration,
) -> io::Result<RecoveryCompletion> {
    match recover_owned_group(receipt, inspector, signaler)? {
        RecoveryDecision::NoChildrenLive => return Ok(RecoveryCompletion::NoChildrenLive),
        RecoveryDecision::AmbiguousIdentity => {
            return Ok(RecoveryCompletion::AmbiguousIdentity);
        }
        RecoveryDecision::ExactGroupSignalled => {}
    }
    let deadline = Instant::now() + grace;
    loop {
        let mut live = false;
        for expected in &receipt.children {
            match inspector.inspect(expected.pid)? {
                ProcessInspection::Absent => {}
                ProcessInspection::Identity(actual) => {
                    live = true;
                    if &actual != expected {
                        return Ok(RecoveryCompletion::AmbiguousIdentity);
                    }
                }
                ProcessInspection::Unavailable => {
                    return Ok(RecoveryCompletion::AmbiguousIdentity);
                }
            }
        }
        if !live {
            return Ok(RecoveryCompletion::StoppedExactGroup);
        }
        if Instant::now() >= deadline {
            return Ok(RecoveryCompletion::StillRunning);
        }
        std::thread::sleep(Duration::from_millis(10));
    }
}

fn valid_sha256(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn sha256_file(path: &Path) -> io::Result<String> {
    let bytes = std::fs::read(path)?;
    Ok(format!("{:x}", Sha256::digest(bytes)))
}

pub fn read_parent_liveness(fd: RawFd) -> io::Result<()> {
    let mut byte = [0_u8; 1];
    loop {
        let read = unsafe { libc::read(fd, byte.as_mut_ptr().cast(), 1) };
        if read == 0 {
            return Ok(());
        }
        if read < 0 {
            let error = io::Error::last_os_error();
            if error.kind() == io::ErrorKind::Interrupted {
                continue;
            }
            return Err(error);
        }
    }
}

pub fn expected_operations() -> HashSet<Operation> {
    use Operation::*;
    [
        ProfileInspect,
        ProfileAdopt,
        CaptureStart,
        CaptureStop,
        CaptureInspect,
        TranscriptCreate,
        NoteCreate,
        NoteInspect,
    ]
    .into_iter()
    .collect()
}

pub fn bounded_frame(frame: &[u8]) -> Result<&[u8], ProtocolError> {
    if frame.len() > MAX_FRAME_BYTES {
        Err(ProtocolError::FrameTooLarge)
    } else {
        Ok(frame)
    }
}

#[cfg(test)]
mod tests {
    use std::cell::{Cell, RefCell};
    use std::collections::HashMap;
    use std::rc::Rc;

    use super::*;

    struct FakeInspector(HashMap<u32, ProcessInspection>);
    impl ProcessInspector for FakeInspector {
        fn inspect(&self, pid: u32) -> io::Result<ProcessInspection> {
            Ok(self
                .0
                .get(&pid)
                .cloned()
                .unwrap_or(ProcessInspection::Absent))
        }
    }
    struct FakeSignaler(Cell<u32>);
    impl GroupSignaler for FakeSignaler {
        fn terminate(&self, _process_group_id: i32) -> io::Result<()> {
            self.0.set(self.0.get() + 1);
            Ok(())
        }
    }

    struct SharedInspector(Rc<RefCell<HashMap<u32, ProcessIdentity>>>);
    impl ProcessInspector for SharedInspector {
        fn inspect(&self, pid: u32) -> io::Result<ProcessInspection> {
            Ok(self
                .0
                .borrow()
                .get(&pid)
                .cloned()
                .map(ProcessInspection::Identity)
                .unwrap_or(ProcessInspection::Absent))
        }
    }

    struct ClearingSignaler {
        calls: Cell<u32>,
        processes: Rc<RefCell<HashMap<u32, ProcessIdentity>>>,
    }
    impl GroupSignaler for ClearingSignaler {
        fn terminate(&self, _process_group_id: i32) -> io::Result<()> {
            self.calls.set(self.calls.get() + 1);
            self.processes.borrow_mut().clear();
            Ok(())
        }
    }

    fn identity(pid: u32, start: u64) -> ProcessIdentity {
        ProcessIdentity {
            pid,
            start_time_epoch_seconds: start,
            executable_path: PathBuf::from("/fixed/worker"),
            executable_sha256: "d".repeat(64),
        }
    }

    #[test]
    fn fresh_launch_signals_only_exact_identity() {
        let expected = identity(44, 10);
        let receipt = OwnershipReceipt {
            schema: OwnershipSchema::V1,
            process_group_id: 44,
            application_build_sha256: "a".repeat(64),
            worker_build_sha256: "b".repeat(64),
            tap_build_sha256: "c".repeat(64),
            children: vec![expected.clone()],
        };
        let signaler = FakeSignaler(Cell::new(0));
        let exact = FakeInspector(HashMap::from([(44, ProcessInspection::Identity(expected))]));
        assert_eq!(
            recover_owned_group(&receipt, &exact, &signaler).unwrap(),
            RecoveryDecision::ExactGroupSignalled
        );
        assert_eq!(signaler.0.get(), 1);

        let reused = FakeInspector(HashMap::from([(
            44,
            ProcessInspection::Identity(identity(44, 11)),
        )]));
        assert_eq!(
            recover_owned_group(&receipt, &reused, &signaler).unwrap(),
            RecoveryDecision::AmbiguousIdentity
        );
        assert_eq!(signaler.0.get(), 1);
    }

    #[test]
    fn absent_process_is_clear_but_unavailable_identity_is_ambiguous() {
        let expected = identity(66, 30);
        let receipt = OwnershipReceipt {
            schema: OwnershipSchema::V1,
            process_group_id: 66,
            application_build_sha256: "a".repeat(64),
            worker_build_sha256: "b".repeat(64),
            tap_build_sha256: "c".repeat(64),
            children: vec![expected],
        };
        let signaler = FakeSignaler(Cell::new(0));

        assert_eq!(
            recover_owned_group(&receipt, &FakeInspector(HashMap::new()), &signaler).unwrap(),
            RecoveryDecision::NoChildrenLive
        );
        assert_eq!(signaler.0.get(), 0);

        let unavailable = FakeInspector(HashMap::from([(66, ProcessInspection::Unavailable)]));
        assert_eq!(
            recover_owned_group(&receipt, &unavailable, &signaler).unwrap(),
            RecoveryDecision::AmbiguousIdentity
        );
        assert_eq!(signaler.0.get(), 0);
    }

    #[test]
    fn exact_recovery_waits_until_the_recorded_child_is_gone() {
        let expected = identity(55, 20);
        let receipt = OwnershipReceipt {
            schema: OwnershipSchema::V1,
            process_group_id: 55,
            application_build_sha256: "a".repeat(64),
            worker_build_sha256: "b".repeat(64),
            tap_build_sha256: "c".repeat(64),
            children: vec![expected.clone()],
        };
        let processes = Rc::new(RefCell::new(HashMap::from([(55, expected)])));
        let inspector = SharedInspector(processes.clone());
        let signaler = ClearingSignaler {
            calls: Cell::new(0),
            processes,
        };
        assert_eq!(
            recover_owned_group_and_wait(
                &receipt,
                &inspector,
                &signaler,
                Duration::from_millis(20),
            )
            .unwrap(),
            RecoveryCompletion::StoppedExactGroup
        );
        assert_eq!(signaler.calls.get(), 1);
    }
}

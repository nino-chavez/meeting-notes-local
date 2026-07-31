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
pub struct ProcessIdentity {
    pub pid: u32,
    pub start_time_epoch_seconds: u64,
    pub executable_path: PathBuf,
    pub executable_sha256: String,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct OwnershipReceipt {
    pub schema: OwnershipSchema,
    pub process_group_id: i32,
    pub children: Vec<ProcessIdentity>,
}

#[derive(Debug, Serialize, Deserialize)]
pub enum OwnershipSchema {
    #[serde(rename = "capture-ownership/1")]
    V1,
}

pub trait ProcessInspector {
    fn identity(&self, pid: u32) -> io::Result<Option<ProcessIdentity>>;
}

pub trait GroupSignaler {
    fn terminate(&self, process_group_id: i32) -> io::Result<()>;
}

pub struct SystemProcessInspector;

impl ProcessInspector for SystemProcessInspector {
    fn identity(&self, pid: u32) -> io::Result<Option<ProcessIdentity>> {
        let mut system = System::new();
        let system_pid = Pid::from_u32(pid);
        system.refresh_processes(ProcessesToUpdate::Some(&[system_pid]), true);
        let Some(process) = system.process(system_pid) else {
            return Ok(None);
        };
        let Some(executable) = process.exe() else {
            return Ok(None);
        };
        Ok(Some(ProcessIdentity {
            pid,
            start_time_epoch_seconds: process.start_time(),
            executable_path: executable.to_path_buf(),
            executable_sha256: sha256_file(executable)?,
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

pub fn recover_owned_group(
    receipt: &OwnershipReceipt,
    inspector: &dyn ProcessInspector,
    signaler: &dyn GroupSignaler,
) -> io::Result<RecoveryDecision> {
    let mut live = 0;
    for expected in &receipt.children {
        if let Some(actual) = inspector.identity(expected.pid)? {
            live += 1;
            if &actual != expected {
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
    use std::cell::Cell;
    use std::collections::HashMap;

    use super::*;

    struct FakeInspector(HashMap<u32, ProcessIdentity>);
    impl ProcessInspector for FakeInspector {
        fn identity(&self, pid: u32) -> io::Result<Option<ProcessIdentity>> {
            Ok(self.0.get(&pid).cloned())
        }
    }
    struct FakeSignaler(Cell<u32>);
    impl GroupSignaler for FakeSignaler {
        fn terminate(&self, _process_group_id: i32) -> io::Result<()> {
            self.0.set(self.0.get() + 1);
            Ok(())
        }
    }

    fn identity(pid: u32, start: u64) -> ProcessIdentity {
        ProcessIdentity {
            pid,
            start_time_epoch_seconds: start,
            executable_path: PathBuf::from("/fixed/worker"),
            executable_sha256: "digest".into(),
        }
    }

    #[test]
    fn fresh_launch_signals_only_exact_identity() {
        let expected = identity(44, 10);
        let receipt = OwnershipReceipt {
            schema: OwnershipSchema::V1,
            process_group_id: 44,
            children: vec![expected.clone()],
        };
        let signaler = FakeSignaler(Cell::new(0));
        let exact = FakeInspector(HashMap::from([(44, expected)]));
        assert_eq!(
            recover_owned_group(&receipt, &exact, &signaler).unwrap(),
            RecoveryDecision::ExactGroupSignalled
        );
        assert_eq!(signaler.0.get(), 1);

        let reused = FakeInspector(HashMap::from([(44, identity(44, 11))]));
        assert_eq!(
            recover_owned_group(&receipt, &reused, &signaler).unwrap(),
            RecoveryDecision::AmbiguousIdentity
        );
        assert_eq!(signaler.0.get(), 1);
    }
}

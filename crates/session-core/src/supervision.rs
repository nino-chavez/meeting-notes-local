use std::collections::HashSet;
use std::fs::File;
use std::io::{self, BufRead, BufReader, Read, Write};
use std::os::fd::{FromRawFd, RawFd};
use std::os::unix::process::CommandExt;
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStderr, ChildStdout, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex, mpsc};
use std::thread::JoinHandle;
use std::time::{Duration, Instant};

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use sysinfo::{Pid, ProcessesToUpdate, System};
use thiserror::Error;

use crate::protocol::{
    MAX_FRAME_BYTES, MAX_PROGRESS_EVENTS_PER_SECOND, MAX_QUEUED_OUTPUTS, Operation, ProtocolError,
    RequestTracker, WorkerCommand, WorkerOutput, WorkerProgress, WorkerReady, WorkerResult,
    parse_output, parse_ready,
};

pub const PARENT_FD_ENV: &str = "LMN_PARENT_LIVENESS_FD";
pub const MAX_STDERR_BYTES: usize = 16 * 1024;

#[derive(Debug, Error)]
pub enum SupervisionError {
    #[error("worker executable is missing")]
    MissingChild,
    #[error("worker readiness timed out")]
    ReadyTimeout,
    #[error("worker exited before readiness")]
    EarlyExit,
    #[error("worker exited before completing its request")]
    WorkerExited,
    #[error("worker request exceeded its deadline")]
    RequestTimeout,
    #[error("worker standard error exceeded its byte limit")]
    StderrOverflow,
    #[error("worker protocol is not ready or is no longer usable")]
    Unavailable,
    #[error(transparent)]
    Protocol(#[from] ProtocolError),
    #[error(transparent)]
    Io(#[from] io::Error),
}

#[derive(Debug, Clone, Copy)]
enum WorkerFault {
    Protocol(ProtocolError),
    WorkerExited,
    StdoutIo,
    StderrIo,
    StderrOverflow,
}

struct DispatchItem {
    received_at: Instant,
    output: WorkerOutput,
}

pub struct OwnedChild {
    child: Child,
    process_group_id: i32,
    liveness_writer: Option<File>,
    output_receiver: Option<mpsc::Receiver<DispatchItem>>,
    dispatcher_thread: Option<JoinHandle<()>>,
    stderr_thread: Option<JoinHandle<()>>,
    requests: Arc<Mutex<RequestTracker>>,
    fault: Arc<Mutex<Option<WorkerFault>>>,
    shutting_down: Arc<AtomicBool>,
    stopped: bool,
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
        let mut child = match command.spawn() {
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
        let process_group_id = child.id() as i32;
        let fault = Arc::new(Mutex::new(None));
        let shutting_down = Arc::new(AtomicBool::new(false));
        let stderr = child
            .stderr
            .take()
            .ok_or_else(|| io::Error::other("worker stderr missing"))?;
        let stderr_thread = Some(spawn_stderr_monitor(
            stderr,
            process_group_id,
            Arc::clone(&fault),
            Arc::clone(&shutting_down),
        ));
        Ok(Self {
            process_group_id,
            child,
            liveness_writer: Some(liveness_writer),
            output_receiver: None,
            dispatcher_thread: None,
            stderr_thread,
            requests: Arc::new(Mutex::new(RequestTracker::default())),
            fault,
            shutting_down,
            stopped: false,
        })
    }

    pub fn pid(&self) -> u32 {
        self.child.id()
    }

    pub fn process_group_id(&self) -> i32 {
        self.process_group_id
    }

    pub fn check_health(&self) -> Result<(), SupervisionError> {
        if self.stopped || self.output_receiver.is_none() {
            return Err(SupervisionError::Unavailable);
        }
        match self.current_fault_error() {
            Some(error) => Err(error),
            None => Ok(()),
        }
    }

    pub fn wait_ready(
        &mut self,
        timeout: Duration,
        expected_operations: &HashSet<Operation>,
    ) -> Result<WorkerReady, SupervisionError> {
        if self.output_receiver.is_some() || self.stopped {
            return Err(SupervisionError::Unavailable);
        }
        let stdout = self
            .child
            .stdout
            .take()
            .ok_or_else(|| io::Error::other("worker stdout missing"))?;
        let (sender, receiver) = mpsc::channel();
        let ready_thread = std::thread::spawn(move || {
            let mut reader = BufReader::new(stdout);
            let result = read_bounded_frame(&mut reader);
            let _ = sender.send((result, reader));
        });
        let received = receiver.recv_timeout(timeout);
        match received {
            Ok((Ok(frame), reader)) if !frame.is_empty() => {
                let _ = ready_thread.join();
                if let Some(error) = self.current_fault_error() {
                    let _ = self.abort_and_wait(Duration::from_millis(500));
                    return Err(error);
                }
                match parse_ready(&frame, expected_operations) {
                    Ok(ready) => {
                        self.start_dispatcher(reader);
                        Ok(ready)
                    }
                    Err(error) => {
                        let _ = self.abort_and_wait(Duration::from_millis(500));
                        Err(error.into())
                    }
                }
            }
            Ok((Ok(_), _)) => {
                let _ = ready_thread.join();
                let error = self
                    .current_fault_error()
                    .unwrap_or(SupervisionError::EarlyExit);
                let _ = self.abort_and_wait(Duration::from_millis(500));
                Err(error)
            }
            Ok((Err(read_error), _)) => {
                let _ = ready_thread.join();
                let error = self.current_fault_error().unwrap_or(read_error);
                let _ = self.abort_and_wait(Duration::from_millis(500));
                Err(error)
            }
            Err(mpsc::RecvTimeoutError::Timeout) => {
                let _ = self.abort_and_wait(Duration::from_millis(500));
                let _ = ready_thread.join();
                Err(SupervisionError::ReadyTimeout)
            }
            Err(mpsc::RecvTimeoutError::Disconnected) => {
                let _ = ready_thread.join();
                let error = self
                    .current_fault_error()
                    .unwrap_or(SupervisionError::EarlyExit);
                let _ = self.abort_and_wait(Duration::from_millis(500));
                Err(error)
            }
        }
    }

    pub fn request_until<F>(
        &mut self,
        command: &WorkerCommand,
        deadline: Instant,
        mut on_progress: F,
    ) -> Result<WorkerResult, SupervisionError>
    where
        F: FnMut(&WorkerProgress) -> Result<(), ProtocolError>,
    {
        if self.stopped || self.output_receiver.is_none() {
            return Err(SupervisionError::Unavailable);
        }
        if let Some(error) = self.current_fault_error() {
            return Err(error);
        }
        let mut frame = serde_json::to_vec(command).map_err(|_| ProtocolError::Malformed)?;
        frame.push(b'\n');
        if frame.len() > MAX_FRAME_BYTES {
            return Err(ProtocolError::FrameTooLarge.into());
        }
        self.requests
            .lock()
            .expect("request tracker lock")
            .register(command)?;
        let stdin = self
            .child
            .stdin
            .as_mut()
            .ok_or_else(|| io::Error::other("worker stdin missing"))?;
        if let Err(error) = stdin.write_all(&frame).and_then(|_| stdin.flush()) {
            self.cancel_request(command.request_id);
            let _ = self.abort_and_wait(Duration::from_millis(500));
            return Err(error.into());
        }

        loop {
            if let Some(error) = self.current_fault_error() {
                self.cancel_request(command.request_id);
                let _ = self.abort_and_wait(Duration::from_millis(500));
                return Err(error);
            }
            let now = Instant::now();
            let receiver = self
                .output_receiver
                .as_ref()
                .expect("output receiver checked");
            let received = match receiver.try_recv() {
                Ok(item) => Ok(item),
                Err(mpsc::TryRecvError::Disconnected) => Err(mpsc::RecvTimeoutError::Disconnected),
                Err(mpsc::TryRecvError::Empty) if now >= deadline => {
                    Err(mpsc::RecvTimeoutError::Timeout)
                }
                Err(mpsc::TryRecvError::Empty) => {
                    receiver.recv_timeout(deadline.saturating_duration_since(now))
                }
            };
            let item = match received {
                Ok(item) => item,
                Err(mpsc::RecvTimeoutError::Timeout) => {
                    self.cancel_request(command.request_id);
                    let _ = self.abort_and_wait(Duration::from_millis(500));
                    return Err(SupervisionError::RequestTimeout);
                }
                Err(mpsc::RecvTimeoutError::Disconnected) => {
                    let error = self
                        .current_fault_error()
                        .unwrap_or(SupervisionError::WorkerExited);
                    self.cancel_request(command.request_id);
                    let _ = self.abort_and_wait(Duration::from_millis(500));
                    return Err(error);
                }
            };
            if item.received_at > deadline {
                self.cancel_request(command.request_id);
                let _ = self.abort_and_wait(Duration::from_millis(500));
                return Err(SupervisionError::RequestTimeout);
            }
            if let Some(error) = self.current_fault_error() {
                self.cancel_request(command.request_id);
                let _ = self.abort_and_wait(Duration::from_millis(500));
                return Err(error);
            }
            match item.output {
                WorkerOutput::Progress(progress) => {
                    if let Err(error) = on_progress(&progress) {
                        self.cancel_request(command.request_id);
                        let _ = self.abort_and_wait(Duration::from_millis(500));
                        return Err(error.into());
                    }
                }
                WorkerOutput::Result(result) => return Ok(result),
            }
        }
    }

    pub fn shutdown_and_wait(&mut self, grace: Duration) -> io::Result<()> {
        self.stop_owned_group(grace, false)
    }

    pub fn stop_and_wait(&mut self, grace: Duration) -> io::Result<()> {
        self.abort_and_wait(grace)
    }

    fn abort_and_wait(&mut self, grace: Duration) -> io::Result<()> {
        self.stop_owned_group(grace, true)
    }

    fn stop_owned_group(&mut self, grace: Duration, abort: bool) -> io::Result<()> {
        if self.stopped {
            return Ok(());
        }
        self.shutting_down.store(true, Ordering::SeqCst);
        self.child.stdin.take();
        self.liveness_writer.take();
        if !abort && wait_for_group_exit(&mut self.child, self.process_group_id, grace)? {
            return self.finish_stopped();
        }
        let terminate_error = signal_group(self.process_group_id, libc::SIGTERM).err();
        if wait_for_group_exit(&mut self.child, self.process_group_id, grace)? {
            return self.finish_stopped();
        }
        let kill_error = signal_group(self.process_group_id, libc::SIGKILL).err();
        if !wait_for_group_exit(
            &mut self.child,
            self.process_group_id,
            grace.max(Duration::from_millis(250)),
        )? {
            return Err(kill_error.or(terminate_error).unwrap_or_else(|| {
                io::Error::new(
                    io::ErrorKind::TimedOut,
                    "owned process group did not exit after SIGKILL",
                )
            }));
        }
        self.finish_stopped()
    }

    fn finish_stopped(&mut self) -> io::Result<()> {
        if self.child.try_wait()?.is_none() {
            self.child.wait()?;
        }
        self.output_receiver.take();
        join_thread(self.dispatcher_thread.take())?;
        join_thread(self.stderr_thread.take())?;
        self.stopped = true;
        Ok(())
    }

    fn start_dispatcher(&mut self, reader: BufReader<ChildStdout>) {
        let (sender, receiver) = mpsc::sync_channel(MAX_QUEUED_OUTPUTS);
        self.output_receiver = Some(receiver);
        self.dispatcher_thread = Some(spawn_dispatcher(
            reader,
            sender,
            self.process_group_id,
            Arc::clone(&self.requests),
            Arc::clone(&self.fault),
            Arc::clone(&self.shutting_down),
        ));
    }

    fn cancel_request(&self, request_id: uuid::Uuid) {
        self.requests
            .lock()
            .expect("request tracker lock")
            .cancel(request_id);
    }

    fn current_fault_error(&self) -> Option<SupervisionError> {
        self.fault
            .lock()
            .expect("worker fault lock")
            .map(worker_fault_error)
    }
}

fn spawn_dispatcher(
    mut reader: BufReader<ChildStdout>,
    sender: mpsc::SyncSender<DispatchItem>,
    process_group_id: i32,
    requests: Arc<Mutex<RequestTracker>>,
    fault: Arc<Mutex<Option<WorkerFault>>>,
    shutting_down: Arc<AtomicBool>,
) -> JoinHandle<()> {
    std::thread::spawn(move || {
        let mut progress_window = Instant::now();
        let mut progress_events = 0_usize;
        loop {
            let frame = match read_bounded_frame(&mut reader) {
                Ok(frame) if frame.is_empty() => {
                    if !shutting_down.load(Ordering::SeqCst) {
                        install_fault(
                            WorkerFault::WorkerExited,
                            &fault,
                            &shutting_down,
                            process_group_id,
                        );
                    }
                    break;
                }
                Ok(frame) => frame,
                Err(SupervisionError::Protocol(error)) => {
                    install_fault(
                        WorkerFault::Protocol(error),
                        &fault,
                        &shutting_down,
                        process_group_id,
                    );
                    break;
                }
                Err(_) => {
                    install_fault(
                        WorkerFault::StdoutIo,
                        &fault,
                        &shutting_down,
                        process_group_id,
                    );
                    break;
                }
            };
            let output = match parse_output(&frame) {
                Ok(output) => output,
                Err(error) => {
                    install_fault(
                        WorkerFault::Protocol(error),
                        &fault,
                        &shutting_down,
                        process_group_id,
                    );
                    break;
                }
            };
            let received_at = Instant::now();
            if matches!(output, WorkerOutput::Progress(_)) {
                if received_at.duration_since(progress_window) >= Duration::from_secs(1) {
                    progress_window = received_at;
                    progress_events = 0;
                }
                progress_events += 1;
                if progress_events > MAX_PROGRESS_EVENTS_PER_SECOND {
                    install_fault(
                        WorkerFault::Protocol(ProtocolError::EventRateExceeded),
                        &fault,
                        &shutting_down,
                        process_group_id,
                    );
                    break;
                }
            }
            let validation = {
                let mut tracker = requests.lock().expect("request tracker lock");
                match &output {
                    WorkerOutput::Progress(progress) => tracker.progress(progress),
                    WorkerOutput::Result(result) => tracker.terminal(result),
                }
            };
            if let Err(error) = validation {
                install_fault(
                    WorkerFault::Protocol(error),
                    &fault,
                    &shutting_down,
                    process_group_id,
                );
                break;
            }
            match sender.try_send(DispatchItem {
                received_at,
                output,
            }) {
                Ok(()) => {}
                Err(mpsc::TrySendError::Full(_)) => {
                    install_fault(
                        WorkerFault::Protocol(ProtocolError::OutputQueueOverflow),
                        &fault,
                        &shutting_down,
                        process_group_id,
                    );
                    break;
                }
                Err(mpsc::TrySendError::Disconnected(_)) => break,
            }
        }
    })
}

fn spawn_stderr_monitor(
    mut stderr: ChildStderr,
    process_group_id: i32,
    fault: Arc<Mutex<Option<WorkerFault>>>,
    shutting_down: Arc<AtomicBool>,
) -> JoinHandle<()> {
    std::thread::spawn(move || {
        let mut total = 0_usize;
        let mut overflowed = false;
        let mut buffer = [0_u8; 4096];
        loop {
            match stderr.read(&mut buffer) {
                Ok(0) => break,
                Ok(read) => {
                    total = total.saturating_add(read);
                    if total > MAX_STDERR_BYTES && !overflowed {
                        overflowed = true;
                        install_fault(
                            WorkerFault::StderrOverflow,
                            &fault,
                            &shutting_down,
                            process_group_id,
                        );
                    }
                }
                Err(error) if error.kind() == io::ErrorKind::Interrupted => continue,
                Err(_) => {
                    if !shutting_down.load(Ordering::SeqCst) {
                        install_fault(
                            WorkerFault::StderrIo,
                            &fault,
                            &shutting_down,
                            process_group_id,
                        );
                    }
                    break;
                }
            }
        }
    })
}

fn install_fault(
    new_fault: WorkerFault,
    fault: &Arc<Mutex<Option<WorkerFault>>>,
    shutting_down: &Arc<AtomicBool>,
    process_group_id: i32,
) {
    let installed = {
        let mut slot = fault.lock().expect("worker fault lock");
        if slot.is_some() {
            false
        } else {
            *slot = Some(new_fault);
            true
        }
    };
    if installed && !shutting_down.load(Ordering::SeqCst) {
        let _ = signal_group(process_group_id, libc::SIGTERM);
    }
}

fn worker_fault_error(fault: WorkerFault) -> SupervisionError {
    match fault {
        WorkerFault::Protocol(error) => SupervisionError::Protocol(error),
        WorkerFault::WorkerExited => SupervisionError::WorkerExited,
        WorkerFault::StdoutIo => SupervisionError::Io(io::Error::other("worker stdout failed")),
        WorkerFault::StderrIo => SupervisionError::Io(io::Error::other("worker stderr failed")),
        WorkerFault::StderrOverflow => SupervisionError::StderrOverflow,
    }
}

fn wait_for_group_exit(
    child: &mut Child,
    process_group_id: i32,
    grace: Duration,
) -> io::Result<bool> {
    let deadline = Instant::now() + grace;
    loop {
        let _ = child.try_wait()?;
        if !process_group_exists(process_group_id)? {
            return Ok(true);
        }
        if Instant::now() >= deadline {
            return Ok(false);
        }
        std::thread::sleep(Duration::from_millis(10));
    }
}

fn process_group_exists(process_group_id: i32) -> io::Result<bool> {
    let result = unsafe { libc::kill(-process_group_id, 0) };
    if result == 0 {
        return Ok(true);
    }
    let error = io::Error::last_os_error();
    match error.raw_os_error() {
        Some(libc::ESRCH) => Ok(false),
        Some(libc::EPERM) => Ok(true),
        _ => Err(error),
    }
}

fn join_thread(thread: Option<JoinHandle<()>>) -> io::Result<()> {
    if let Some(thread) = thread {
        thread
            .join()
            .map_err(|_| io::Error::other("worker I/O thread panicked"))?;
    }
    Ok(())
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
        let _ = self.abort_and_wait(Duration::from_millis(250));
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
        if probe_process_existence(pid)? == ProcessExistence::Absent {
            return Ok(ProcessInspection::Absent);
        }
        let mut system = System::new();
        let system_pid = Pid::from_u32(pid);
        system.refresh_processes(ProcessesToUpdate::Some(&[system_pid]), true);
        let Some(process) = system.process(system_pid) else {
            return Ok(ProcessInspection::Unavailable);
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

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum ProcessExistence {
    Absent,
    Present,
}

fn probe_process_existence(pid: u32) -> io::Result<ProcessExistence> {
    if pid == 0 {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "process identifier must be positive",
        ));
    }
    let pid = libc::pid_t::try_from(pid).map_err(|_| {
        io::Error::new(
            io::ErrorKind::InvalidInput,
            "process identifier exceeds the platform range",
        )
    })?;
    let result = unsafe { libc::kill(pid, 0) };
    let error = (result != 0).then(io::Error::last_os_error);
    classify_process_probe(result, error)
}

fn classify_process_probe(
    result: libc::c_int,
    error: Option<io::Error>,
) -> io::Result<ProcessExistence> {
    if result == 0 {
        return Ok(ProcessExistence::Present);
    }
    let error = error.unwrap_or_else(io::Error::last_os_error);
    match error.raw_os_error() {
        Some(libc::ESRCH) => Ok(ProcessExistence::Absent),
        Some(libc::EPERM) => Ok(ProcessExistence::Present),
        _ => Err(error),
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
    fn process_existence_probe_maps_only_esrch_to_absent() {
        assert_eq!(
            classify_process_probe(0, None).unwrap(),
            ProcessExistence::Present
        );
        assert_eq!(
            classify_process_probe(-1, Some(io::Error::from_raw_os_error(libc::ESRCH))).unwrap(),
            ProcessExistence::Absent
        );
        assert_eq!(
            classify_process_probe(-1, Some(io::Error::from_raw_os_error(libc::EPERM))).unwrap(),
            ProcessExistence::Present
        );
        let error = classify_process_probe(-1, Some(io::Error::from_raw_os_error(libc::EINVAL)))
            .unwrap_err();
        assert_eq!(error.raw_os_error(), Some(libc::EINVAL));
    }

    #[test]
    fn system_inspector_never_classifies_current_process_as_absent() {
        assert_eq!(
            probe_process_existence(std::process::id()).unwrap(),
            ProcessExistence::Present
        );
        assert!(matches!(
            SystemProcessInspector.inspect(std::process::id()).unwrap(),
            ProcessInspection::Identity(_) | ProcessInspection::Unavailable
        ));
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

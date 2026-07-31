use std::fs;
use std::process::{Command, Stdio};
use std::time::{Duration, Instant};

use local_meeting_notes_session_core::protocol::{
    CaptureProgressState, Operation, ProtocolError, WorkerCommand,
};
use local_meeting_notes_session_core::supervision::{
    OwnedChild, SupervisionError, expected_operations,
};
use tempfile::TempDir;

const FAKE_WORKER: &str = env!("CARGO_BIN_EXE_fake-worker");
const SUPERVISOR_HARNESS: &str = env!("CARGO_BIN_EXE_supervisor-harness");

#[test]
fn supervised_worker_keeps_protocol_after_readiness() {
    let mut command = Command::new(FAKE_WORKER);
    command.args(["--mode", "protocol"]);
    let mut child = OwnedChild::spawn(&mut command).unwrap();
    child
        .wait_ready(Duration::from_secs(1), &expected_operations())
        .unwrap();
    let request = WorkerCommand::new(
        Operation::CaptureInspect,
        serde_json::json!({"meeting_id": "fixture"}),
    );
    let result = child
        .request_until(
            &request,
            Instant::now() + Duration::from_secs(1),
            |_| Ok(()),
        )
        .unwrap();
    assert!(result.ok);
    assert_eq!(result.artifact_digests["fixture"], "digest");
}

#[test]
fn supervised_worker_dispatches_progress_before_result() {
    let mut command = Command::new(FAKE_WORKER);
    command.args(["--mode", "protocol-progress"]);
    let mut child = OwnedChild::spawn(&mut command).unwrap();
    child
        .wait_ready(Duration::from_secs(1), &expected_operations())
        .unwrap();
    let meeting_id = uuid::Uuid::new_v4();
    let request = WorkerCommand::new(
        Operation::CaptureStart,
        serde_json::json!({"meeting_id": meeting_id, "profile_id": "fixture"}),
    );
    let mut states = Vec::new();
    let result = child
        .request_until(
            &request,
            Instant::now() + Duration::from_secs(1),
            |progress| {
                states.push((progress.state, progress.meeting_id));
                Ok(())
            },
        )
        .unwrap();
    assert_eq!(states, vec![(CaptureProgressState::Recording, meeting_id)]);
    assert!(result.ok);
}

#[test]
fn unknown_progress_request_stops_and_reaps_worker() {
    let mut command = Command::new(FAKE_WORKER);
    command.args(["--mode", "wrong-progress"]);
    let mut child = OwnedChild::spawn(&mut command).unwrap();
    let pid = child.pid();
    child
        .wait_ready(Duration::from_secs(1), &expected_operations())
        .unwrap();
    let request = WorkerCommand::new(
        Operation::CaptureStart,
        serde_json::json!({
            "meeting_id": uuid::Uuid::new_v4(),
            "profile_id": "fixture"
        }),
    );
    assert!(matches!(
        child.request_until(
            &request,
            Instant::now() + Duration::from_secs(1),
            |_| Ok(())
        ),
        Err(SupervisionError::Protocol(ProtocolError::UnknownRequest))
    ));
    assert!(wait_until_gone(pid, Duration::from_secs(3)));
}

#[test]
fn request_deadline_stops_and_reaps_worker() {
    let mut command = Command::new(FAKE_WORKER);
    command.args(["--mode", "never-result"]);
    let mut child = OwnedChild::spawn(&mut command).unwrap();
    let pid = child.pid();
    child
        .wait_ready(Duration::from_secs(1), &expected_operations())
        .unwrap();
    let request = WorkerCommand::new(
        Operation::CaptureInspect,
        serde_json::json!({"meeting_id": "fixture"}),
    );
    assert!(matches!(
        child.request_until(
            &request,
            Instant::now() + Duration::from_millis(100),
            |_| Ok(())
        ),
        Err(SupervisionError::RequestTimeout)
    ));
    assert!(wait_until_gone(pid, Duration::from_secs(1)));
}

fn process_exists(pid: u32) -> bool {
    let result = unsafe { libc::kill(pid as i32, 0) };
    result == 0 || std::io::Error::last_os_error().raw_os_error() == Some(libc::EPERM)
}

fn wait_until_gone(pid: u32, timeout: Duration) -> bool {
    let deadline = Instant::now() + timeout;
    while Instant::now() < deadline {
        if !process_exists(pid) {
            return true;
        }
        std::thread::sleep(Duration::from_millis(20));
    }
    !process_exists(pid)
}

#[test]
fn missing_child_is_refused_without_spawn() {
    let mut command = Command::new("/definitely/missing/local-meeting-notes-worker");
    assert!(matches!(
        OwnedChild::spawn(&mut command),
        Err(SupervisionError::MissingChild)
    ));
}

#[test]
fn readiness_timeout_stops_and_reaps_worker() {
    let mut command = Command::new(FAKE_WORKER);
    command.args(["--mode", "never-ready"]);
    let mut child = OwnedChild::spawn(&mut command).unwrap();
    let pid = child.pid();
    assert!(matches!(
        child.wait_ready(Duration::from_millis(100), &expected_operations()),
        Err(SupervisionError::ReadyTimeout)
    ));
    assert!(wait_until_gone(pid, Duration::from_secs(1)));
}

#[test]
fn forced_exit_escalates_and_reaps_stubborn_worker() {
    let mut command = Command::new(FAKE_WORKER);
    command.args(["--mode", "stubborn"]);
    let mut child = OwnedChild::spawn(&mut command).unwrap();
    let pid = child.pid();
    child
        .wait_ready(Duration::from_secs(1), &expected_operations())
        .unwrap();
    child.stop_and_wait(Duration::from_millis(100)).unwrap();
    assert!(wait_until_gone(pid, Duration::from_secs(1)));
}

#[test]
fn malformed_handshake_fails_closed_and_reaps_worker() {
    let mut command = Command::new(FAKE_WORKER);
    command.args(["--mode", "malformed"]);
    let mut child = OwnedChild::spawn(&mut command).unwrap();
    let pid = child.pid();
    assert!(matches!(
        child.wait_ready(Duration::from_secs(1), &expected_operations()),
        Err(SupervisionError::Protocol(_))
    ));
    assert!(wait_until_gone(pid, Duration::from_secs(1)));
}

#[test]
fn stderr_overflow_fails_without_deadlock_and_reaps_worker() {
    let mut command = Command::new(FAKE_WORKER);
    command.args(["--mode", "stderr-overflow"]);
    let mut child = OwnedChild::spawn(&mut command).unwrap();
    let pid = child.pid();
    let result = child.wait_ready(Duration::from_secs(1), &expected_operations());
    assert!(matches!(result, Err(SupervisionError::StderrOverflow)));
    assert!(wait_until_gone(pid, Duration::from_secs(1)));
}

#[test]
fn worker_exit_cleanup_reaps_remaining_tap() {
    let temp = TempDir::new().unwrap();
    let pid_file = temp.path().join("children.json");
    let mut command = Command::new(FAKE_WORKER);
    command
        .args(["--mode", "ready-exit-with-tap"])
        .env("LMN_PID_FILE", &pid_file);
    let mut child = OwnedChild::spawn(&mut command).unwrap();
    child
        .wait_ready(Duration::from_secs(1), &expected_operations())
        .unwrap();
    let deadline = Instant::now() + Duration::from_secs(1);
    while !pid_file.exists() && Instant::now() < deadline {
        std::thread::sleep(Duration::from_millis(10));
    }
    let pids: serde_json::Value = serde_json::from_slice(&fs::read(&pid_file).unwrap()).unwrap();
    let tap = pids["tap"].as_u64().unwrap() as u32;
    child.stop_and_wait(Duration::from_millis(100)).unwrap();
    assert!(wait_until_gone(tap, Duration::from_secs(1)));
}

#[test]
fn parent_sigkill_closes_liveness_channel_for_worker_and_tap() {
    let temp = TempDir::new().unwrap();
    let pid_file = temp.path().join("children.json");
    let mut harness = Command::new(SUPERVISOR_HARNESS)
        .arg(FAKE_WORKER)
        .arg(&pid_file)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .unwrap();

    let deadline = Instant::now() + Duration::from_secs(3);
    while !pid_file.exists() && Instant::now() < deadline {
        std::thread::sleep(Duration::from_millis(20));
    }
    let pids: serde_json::Value = serde_json::from_slice(&fs::read(&pid_file).unwrap()).unwrap();
    let worker = pids["worker"].as_u64().unwrap() as u32;
    let tap = pids["tap"].as_u64().unwrap() as u32;

    unsafe {
        libc::kill(harness.id() as i32, libc::SIGKILL);
    }
    harness.wait().unwrap();

    assert!(wait_until_gone(worker, Duration::from_secs(3)));
    assert!(wait_until_gone(tap, Duration::from_secs(3)));
}

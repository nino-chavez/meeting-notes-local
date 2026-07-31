use std::env;
use std::fs;
use std::io::{self, BufRead, Write};
use std::process::{Command, Stdio};
use std::time::Duration;

use local_meeting_notes_session_core::supervision::{PARENT_FD_ENV, read_parent_liveness};
use uuid::Uuid;

fn parent_fd() -> i32 {
    env::var(PARENT_FD_ENV)
        .expect("parent liveness descriptor")
        .parse()
        .expect("numeric parent liveness descriptor")
}

fn ready() {
    println!(
        "{}",
        serde_json::json!({
            "schema": "worker-event/1",
            "event": "worker.ready",
            "protocol": 1,
            "build": "fake-worker-build",
            "runtime": {"kind": "bundled", "digest": "fake-runtime"},
            "tap": {"build": "fake-tap", "available": true},
            "models": [{"id": "fake-model", "digest": "fake-model-digest", "available": true}],
            "operations": [
                "profile.inspect", "profile.adopt", "capture.start", "capture.stop",
                "capture.inspect", "transcript.create", "note.create", "note.inspect"
            ]
        })
    );
    io::stdout().flush().unwrap();
}

#[allow(clippy::zombie_processes)]
fn spawn_tap_for_orphan_cleanup_test() -> u32 {
    let executable = env::current_exe().unwrap();
    Command::new(executable)
        .args(["--mode", "tap"])
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .unwrap()
        .id()
}

fn main() {
    let mode = env::args().nth(2).unwrap_or_else(|| "ready".into());
    match mode.as_str() {
        "exit" => std::process::exit(42),
        "never-ready" => read_parent_liveness(parent_fd()).unwrap(),
        "malformed" => {
            println!("{{}}");
            io::stdout().flush().unwrap();
            read_parent_liveness(parent_fd()).unwrap();
        }
        "ready" => {
            ready();
            read_parent_liveness(parent_fd()).unwrap();
        }
        "protocol" => {
            ready();
            for line in io::stdin().lock().lines() {
                let command: serde_json::Value = serde_json::from_str(&line.unwrap()).unwrap();
                println!(
                    "{}",
                    serde_json::json!({
                        "schema": "worker-result/1",
                        "request_id": command["request_id"],
                        "ok": true,
                        "code": null,
                        "recoverable": null,
                        "artifact_digests": {"fixture": "digest"}
                    })
                );
                io::stdout().flush().unwrap();
            }
        }
        "protocol-progress" => {
            ready();
            for line in io::stdin().lock().lines() {
                let command: serde_json::Value = serde_json::from_str(&line.unwrap()).unwrap();
                println!(
                    "{}",
                    serde_json::json!({
                        "schema": "worker-event/1",
                        "request_id": command["request_id"],
                        "event": "capture.state",
                        "state": "recording",
                        "meeting_id": command["arguments"]["meeting_id"]
                    })
                );
                println!(
                    "{}",
                    serde_json::json!({
                        "schema": "worker-result/1",
                        "request_id": command["request_id"],
                        "ok": true,
                        "code": null,
                        "recoverable": null,
                        "artifact_digests": {"fixture": "digest"}
                    })
                );
                io::stdout().flush().unwrap();
            }
        }
        "wrong-progress" => {
            ready();
            let line = io::stdin().lock().lines().next().unwrap().unwrap();
            let command: serde_json::Value = serde_json::from_str(&line).unwrap();
            println!(
                "{}",
                serde_json::json!({
                    "schema": "worker-event/1",
                    "request_id": Uuid::new_v4(),
                    "event": "capture.state",
                    "state": "recording",
                    "meeting_id": command["arguments"]["meeting_id"]
                })
            );
            io::stdout().flush().unwrap();
            read_parent_liveness(parent_fd()).unwrap();
        }
        "never-result" => {
            ready();
            let _ = io::stdin().lock().lines().next();
            read_parent_liveness(parent_fd()).unwrap();
        }
        "stderr-overflow" => {
            io::stderr().write_all(&vec![b'x'; 16 * 1024 + 1]).unwrap();
            io::stderr().flush().unwrap();
            read_parent_liveness(parent_fd()).unwrap();
        }
        "stubborn" => {
            unsafe {
                libc::signal(libc::SIGTERM, libc::SIG_IGN);
            }
            ready();
            loop {
                std::thread::sleep(Duration::from_secs(1));
            }
        }
        "ready-with-tap" => {
            let executable = env::current_exe().unwrap();
            let mut tap = Command::new(executable)
                .args(["--mode", "tap"])
                .stdin(Stdio::null())
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .spawn()
                .unwrap();
            if let Ok(path) = env::var("LMN_PID_FILE") {
                fs::write(
                    path,
                    format!(
                        "{{\"worker\":{},\"tap\":{}}}\n",
                        std::process::id(),
                        tap.id()
                    ),
                )
                .unwrap();
            }
            ready();
            read_parent_liveness(parent_fd()).unwrap();
            let _ = tap.wait();
        }
        "ready-exit-with-tap" => {
            // This mode deliberately exits without waiting so the supervisor
            // must prove it cleans up the remaining process-group member.
            let tap_pid = spawn_tap_for_orphan_cleanup_test();
            if let Ok(path) = env::var("LMN_PID_FILE") {
                fs::write(
                    path,
                    format!(
                        "{{\"worker\":{},\"tap\":{}}}\n",
                        std::process::id(),
                        tap_pid
                    ),
                )
                .unwrap();
            }
            ready();
        }
        "tap" => read_parent_liveness(parent_fd()).unwrap(),
        other => panic!("unknown fake mode {other}"),
    }
}

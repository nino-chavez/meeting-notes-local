use std::env;
use std::process::Command;
use std::time::Duration;

use local_meeting_notes_session_core::supervision::{OwnedChild, expected_operations};

fn main() {
    let worker = env::args().nth(1).expect("fake worker path");
    let pid_file = env::args().nth(2).expect("pid receipt path");
    let mut command = Command::new(worker);
    command
        .args(["--mode", "ready-with-tap"])
        .env("LMN_PID_FILE", pid_file);
    let mut child = OwnedChild::spawn(&mut command).expect("spawn fake worker");
    child
        .wait_ready(Duration::from_secs(2), &expected_operations())
        .expect("fake worker ready");
    loop {
        std::thread::sleep(Duration::from_secs(1));
    }
}

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::collections::HashSet;
#[cfg(debug_assertions)]
use std::path::PathBuf;
use std::process::Command;
use std::sync::Mutex;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use local_meeting_notes_session_core::diagnostic::write_private_diagnostic;
use local_meeting_notes_session_core::recovery::{RecoveryDisposition, scan_and_recover};
use local_meeting_notes_session_core::reducer::StartupState;
use local_meeting_notes_session_core::retention::{RetentionOutcome, execute_due_retention};
use local_meeting_notes_session_core::runtime::RuntimeManifest;
use local_meeting_notes_session_core::storage::StorageRoot;
use local_meeting_notes_session_core::supervision::{
    OwnedChild, SupervisionError, SystemGroupSignaler, SystemProcessInspector, expected_operations,
};
use tauri::{Manager, State};

struct StartupStatus(Mutex<StartupState>);
struct WorkerProcess(Mutex<Option<OwnedChild>>);

#[tauri::command]
fn startup_status(status: State<'_, StartupStatus>) -> StartupState {
    *status.0.lock().expect("startup status lock")
}

#[cfg(debug_assertions)]
fn repository_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(3)
        .expect("repository root above apps/desktop/src-tauri")
        .to_path_buf()
}

fn now_epoch_seconds() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs()
}

fn main() {
    tauri::Builder::default()
        .manage(StartupStatus(Mutex::new(StartupState::ShellRendered)))
        .manage(WorkerProcess(Mutex::new(None)))
        .invoke_handler(tauri::generate_handler![startup_status])
        .setup(|app| {
            let status = app.state::<StartupStatus>();
            *status.0.lock().expect("startup status lock") = StartupState::Checking;

            let app_data = app.path().app_data_dir()?;
            let resource_root = app.path().resource_dir()?;
            #[cfg(debug_assertions)]
            let protected_root = repository_root();
            #[cfg(not(debug_assertions))]
            let protected_root = resource_root.clone();
            let storage = StorageRoot::create(&app_data, &protected_root)
                .map_err(|error| io_error(error.to_string()))?;
            let diagnostics = storage.path().join("diagnostics");

            let recovery_ready = match scan_and_recover(
                &storage,
                now_epoch_seconds(),
                &SystemProcessInspector,
                &SystemGroupSignaler,
                Duration::from_millis(500),
            ) {
                Ok(report) => {
                    for meeting in &report.meetings {
                        match meeting.disposition {
                            RecoveryDisposition::Quarantined(code) => {
                                let _ = write_private_diagnostic(
                                    &diagnostics,
                                    code.as_str(),
                                    &format!(
                                        "meeting {} was quarantined without mutation",
                                        meeting.meeting_id
                                    ),
                                );
                            }
                            RecoveryDisposition::OwnershipAmbiguous => {
                                let _ = write_private_diagnostic(
                                    &diagnostics,
                                    "meeting_recovery_ownership_ambiguous",
                                    &format!(
                                        "meeting {} blocks capture because child identity is uncertain",
                                        meeting.meeting_id
                                    ),
                                );
                            }
                            _ => {}
                        }
                    }
                    !report.blocks_capture
                }
                Err(error) => {
                    let _ = write_private_diagnostic(
                        &diagnostics,
                        "meeting_recovery_failed",
                        &error.to_string(),
                    );
                    false
                }
            };

            if !recovery_ready {
                *status.0.lock().expect("startup status lock") = StartupState::DiagnosticWritten;
            } else {
                let manifest_path = resource_root.join("app-runtime.json");
                match RuntimeManifest::load_and_verify(&manifest_path) {
                    Ok(manifest) if !manifest.permits_application_start() => {
                        *status.0.lock().expect("startup status lock") =
                            StartupState::RuntimeMissing;
                    }
                    Ok(manifest) => {
                        let worker_path = resource_root.join(&manifest.runtime.path);
                        let mut command = Command::new(worker_path);
                        command
                            .args(["-E", "-s", "-B", "-m", "worker.main"])
                            .arg("--app-data-root")
                            .arg(storage.path())
                            .arg("--runtime-manifest")
                            .arg(&manifest_path);
                        command.current_dir(&resource_root);
                        match OwnedChild::spawn(&mut command) {
                            Ok(mut worker) => match worker
                                .wait_ready(Duration::from_secs(10), &expected_operations())
                            {
                                Ok(ready) if manifest.matches_ready(&ready) => {
                                    *app.state::<WorkerProcess>()
                                        .0
                                        .lock()
                                        .expect("worker process lock") = Some(worker);
                                    *status.0.lock().expect("startup status lock") =
                                        StartupState::Ready;
                                }
                                Ok(_) => {
                                    let _ = worker.stop_and_wait(Duration::from_millis(500));
                                    *status.0.lock().expect("startup status lock") =
                                        StartupState::RuntimeMissing;
                                }
                                Err(SupervisionError::ReadyTimeout) => {
                                    *status.0.lock().expect("startup status lock") =
                                        StartupState::ServiceTimeout;
                                }
                                Err(error) => {
                                    let _ = write_private_diagnostic(
                                        &diagnostics,
                                        "worker_startup_failed",
                                        &error.to_string(),
                                    );
                                    *status.0.lock().expect("startup status lock") =
                                        StartupState::DiagnosticWritten;
                                }
                            },
                            Err(SupervisionError::MissingChild) => {
                                *status.0.lock().expect("startup status lock") =
                                    StartupState::RuntimeMissing;
                            }
                            Err(error) => {
                                let _ = write_private_diagnostic(
                                    &diagnostics,
                                    "worker_spawn_failed",
                                    &error.to_string(),
                                );
                                *status.0.lock().expect("startup status lock") =
                                    StartupState::DiagnosticWritten;
                            }
                        }
                    }
                    Err(_) => {
                        *status.0.lock().expect("startup status lock") =
                            StartupState::RuntimeMissing;
                    }
                }
            }

            std::thread::spawn(move || {
                let mut reported_quarantines = HashSet::new();
                loop {
                    std::thread::sleep(Duration::from_secs(30));
                    match execute_due_retention(&storage, now_epoch_seconds()) {
                        Ok(outcomes) => {
                            for outcome in outcomes {
                                if let RetentionOutcome::Quarantined(meeting_id) = outcome
                                    && reported_quarantines.insert(meeting_id.clone())
                                {
                                    let _ = write_private_diagnostic(
                                        &diagnostics,
                                        "retention_meeting_quarantined",
                                        &format!(
                                            "meeting {meeting_id} was quarantined without mutation"
                                        ),
                                    );
                                }
                            }
                        }
                        Err(error) => {
                            let _ = write_private_diagnostic(
                                &diagnostics,
                                "retention_tick_failed",
                                &error.to_string(),
                            );
                        }
                    }
                }
            });
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("Local Meeting Notes shell failed");
}

fn io_error(message: String) -> Box<dyn std::error::Error> {
    Box::new(std::io::Error::other(message))
}

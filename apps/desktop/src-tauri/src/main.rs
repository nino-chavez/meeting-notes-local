#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
#![cfg_attr(feature = "library-dev-surface", allow(dead_code))]

#[cfg(feature = "library-dev-surface")]
mod library_dev_surface;
// The library reader is intentionally private and unregistered.  It maps an
// already-built projection into closed DTOs, but does not create storage or
// provide a Tauri command.
#[allow(dead_code)]
mod library_reader;

// The correction/regeneration facade is intentionally compiled but not wired
// into the current internal-alpha command set.
#[allow(dead_code)]
mod product_facade;
// The manual audio-deletion facade is intentionally compiled but not wired
// into the current internal-alpha command set.
#[allow(dead_code)]
mod manual_delete_facade;

#[cfg(feature = "preview-surface")]
use manual_delete_facade::{
    AudioDeletionReview, ManualAudioDeletionFacadeError, ManualAudioDeletionFacadeOutcome,
    ManualAudioDeletionUiArgs,
};

use std::collections::{HashMap, HashSet};
use std::fs::{self, File};
use std::io::{self, BufRead, BufReader, Read, Write};
use std::os::fd::{AsRawFd, FromRawFd, RawFd};
use std::os::unix::process::CommandExt;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, ExitStatus, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex, mpsc};
use std::thread::JoinHandle;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use local_meeting_notes_session_core::diagnostic::write_private_diagnostic;
#[cfg(any(feature = "preview-surface", test))]
use local_meeting_notes_session_core::meeting::resolve_artifact;
use local_meeting_notes_session_core::meeting::{
    ArtifactRef, AudioRetention, AudioRetentionRule, AudioState, MeetingArtifacts,
    MeetingLifecycle, MeetingRecord, MeetingSchema, artifact_ref, load_meeting, read_private_bytes,
    retention_policy_sha256, write_meeting,
};
use local_meeting_notes_session_core::meeting_coordination::MeetingStorageCoordination;
use local_meeting_notes_session_core::protocol::{
    Operation, ProtocolError, WorkerCommand, WorkerResult,
};
use local_meeting_notes_session_core::recovery::{
    RecoveryCode, RecoveryDisposition, scan_and_recover,
};
use local_meeting_notes_session_core::reducer::{
    CaptureState, ExclusiveOperation, Reducer, StartupState,
};
use local_meeting_notes_session_core::retention::{
    AppDataWriterLock, RetentionOutcome, execute_due_retention_excluding, meeting_dir,
};
use local_meeting_notes_session_core::runtime::RuntimeManifest;
use local_meeting_notes_session_core::storage::{
    StorageRoot, create_private_dir, durable_create_new, sync_directory,
};
use local_meeting_notes_session_core::supervision::{
    OwnedChild, OwnershipReceipt, OwnershipSchema, ProcessIdentity, ProcessInspection,
    ProcessInspector, SupervisionError, SystemGroupSignaler, SystemProcessInspector,
    internal_alpha_operations,
};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use tauri::{AppHandle, Manager, State};
use uuid::Uuid;

const CAPTURE_EVENT_MAX_BYTES: usize = 64 * 1024;
const ATTEMPT_MAX_BYTES: u64 = 256 * 1024;
const TRANSCRIPT_MAX_BYTES: u64 = 16 * 1024 * 1024;
const CAPTURE_ARM_TIMEOUT: Duration = Duration::from_secs(120);
const CAPTURE_STOP_TIMEOUT: Duration = Duration::from_secs(20);
const WORKER_REQUEST_TIMEOUT: Duration = Duration::from_secs(30);
const TRANSCRIPT_REQUEST_TIMEOUT: Duration = Duration::from_secs(2 * 60 * 60);
const PARTICIPANT_NOTICE_VERSION: &str = "internal-transcript-alpha/1";
#[cfg(feature = "preview-surface")]
const ACTIVE_WINDOW_LABEL: &str = "preview";
#[cfg(not(feature = "preview-surface"))]
const ACTIVE_WINDOW_LABEL: &str = "main";

struct ApplicationState {
    model: Mutex<AppModel>,
    storage: Mutex<Option<StorageContext>>,
    runtime: Mutex<Option<RuntimeIdentity>>,
    worker: Mutex<Option<OwnedChild>>,
    capture_task: Mutex<Option<CaptureTaskControl>>,
    command_lock: Mutex<()>,
    app_data_writer_lock: Mutex<Option<AppDataWriterLock>>,
    retention_started: AtomicBool,
    #[cfg(feature = "preview-surface")]
    preview_library: Mutex<Option<library_reader::LibraryReader>>,
}

impl Default for ApplicationState {
    fn default() -> Self {
        Self {
            model: Mutex::new(AppModel::default()),
            storage: Mutex::new(None),
            runtime: Mutex::new(None),
            worker: Mutex::new(None),
            capture_task: Mutex::new(None),
            command_lock: Mutex::new(()),
            app_data_writer_lock: Mutex::new(None),
            retention_started: AtomicBool::new(false),
            #[cfg(feature = "preview-surface")]
            preview_library: Mutex::new(None),
        }
    }
}

struct AppModel {
    reducer: Reducer,
    admission: String,
    retention_operational: bool,
    meeting_id: Option<String>,
    started_at_epoch_seconds: Option<u64>,
    degraded: bool,
    mic_state: Option<String>,
    system_state: Option<String>,
    turns: Vec<TranscriptTurn>,
    warnings: Vec<String>,
    error: Option<String>,
}

impl Default for AppModel {
    fn default() -> Self {
        Self {
            reducer: Reducer::default(),
            admission: "internal-alpha".into(),
            retention_operational: false,
            meeting_id: None,
            started_at_epoch_seconds: None,
            degraded: false,
            mic_state: None,
            system_state: None,
            turns: Vec::new(),
            warnings: Vec::new(),
            error: None,
        }
    }
}

impl AppModel {
    fn snapshot(&self) -> AppSnapshot {
        AppSnapshot {
            startup: self.reducer.startup(),
            admission: self.admission.clone(),
            preview: cfg!(feature = "preview-surface"),
            retention_operational: self.retention_operational,
            capture: self.reducer.capture(),
            meeting_id: self.meeting_id.clone(),
            started_at_epoch_seconds: self.started_at_epoch_seconds,
            degraded: self.degraded,
            mic_state: self.mic_state.clone(),
            system_state: self.system_state.clone(),
            turns: self.turns.clone(),
            warnings: self.warnings.clone(),
            error: self.error.clone(),
        }
    }

    fn clear_meeting_projection(&mut self) {
        self.meeting_id = None;
        self.started_at_epoch_seconds = None;
        self.degraded = false;
        self.mic_state = None;
        self.system_state = None;
        self.turns.clear();
        self.warnings.clear();
        self.error = None;
    }
}

#[derive(Clone, Serialize)]
struct AppSnapshot {
    startup: StartupState,
    admission: String,
    preview: bool,
    retention_operational: bool,
    capture: CaptureState,
    meeting_id: Option<String>,
    started_at_epoch_seconds: Option<u64>,
    degraded: bool,
    mic_state: Option<String>,
    system_state: Option<String>,
    turns: Vec<TranscriptTurn>,
    warnings: Vec<String>,
    error: Option<String>,
}

#[derive(Clone, Serialize)]
struct TranscriptTurn {
    #[serde(rename = "sourceTurnIndex")]
    source_turn_index: u32,
    speaker: Option<String>,
    start: f64,
    text: String,
}

struct RestoredTranscriptProjection {
    meeting_id: String,
    turns: Vec<TranscriptTurn>,
    warnings: Vec<String>,
}

#[cfg(feature = "preview-surface")]
#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct PreviewLibraryTranscript {
    state: &'static str,
    meeting_id: Option<String>,
    turns: Vec<TranscriptTurn>,
    warnings: Vec<String>,
    message: String,
}

#[cfg(any(feature = "preview-surface", test))]
#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct PreviewProfileSnapshot {
    state: &'static str,
}

fn apply_restored_transcript_projection(
    model: &mut AppModel,
    projection: RestoredTranscriptProjection,
) -> Result<(), String> {
    model
        .reducer
        .restore_capture_projection(CaptureState::TranscriptReady)
        .map_err(error_text)?;
    model.meeting_id = Some(projection.meeting_id);
    model.turns = projection.turns;
    model.warnings = projection.warnings;
    Ok(())
}

#[derive(Clone)]
struct StorageContext {
    storage: StorageRoot,
    resource_root: PathBuf,
    manifest_path: PathBuf,
    diagnostics: PathBuf,
}

#[cfg(any(feature = "preview-surface", test))]
fn with_meeting_storage_sequence<T>(
    coordination: &MeetingStorageCoordination,
    operation: impl FnOnce(&HashSet<String>) -> T,
) -> Result<T, ()> {
    let sequence = coordination.lock_sequence().map_err(|_| ())?;
    let active_meeting_ids = sequence.active_meeting_ids().map_err(|_| ())?;
    let response = operation(&active_meeting_ids);
    drop(sequence);
    Ok(response)
}

impl ApplicationState {
    #[allow(dead_code)]
    fn manual_audio_deletion_facade(&self) -> manual_delete_facade::ManualAudioDeletionFacade<'_> {
        manual_delete_facade::ManualAudioDeletionFacade::new(&self.app_data_writer_lock)
    }

    fn meeting_storage_coordination(&self) -> Result<Arc<MeetingStorageCoordination>, String> {
        self.app_data_writer_lock
            .lock()
            .map_err(|_| "the app-data writer lock is unavailable".to_string())?
            .as_ref()
            .map(AppDataWriterLock::coordination)
            .ok_or_else(|| "the app-data writer lock is unavailable".to_string())
    }

    #[cfg(feature = "preview-surface")]
    fn with_preview_library<T>(
        &self,
        unavailable: impl Fn() -> T,
        operation: impl FnOnce(&mut library_reader::LibraryReader, &HashSet<String>) -> T,
    ) -> T {
        let coordination = match self.meeting_storage_coordination() {
            Ok(coordination) => coordination,
            Err(_) => return unavailable(),
        };
        with_meeting_storage_sequence(&coordination, |active_meeting_ids| {
            let mut library = match self.preview_library.lock() {
                Ok(library) => library,
                Err(_) => return unavailable(),
            };
            let Some(reader) = library.as_mut() else {
                return unavailable();
            };
            operation(reader, active_meeting_ids)
        })
        .unwrap_or_else(|_| unavailable())
    }
}

#[derive(Clone)]
struct RuntimeIdentity {
    admission: String,
    worker_build_sha256: String,
    worker_executable_sha256: String,
    tap_build_sha256: String,
    tap_path: PathBuf,
}

struct CaptureTaskControl {
    meeting_id: String,
    sender: mpsc::SyncSender<CaptureTaskCommand>,
}

struct CaptureTaskRegistration {
    app: AppHandle,
    meeting_id: String,
}

impl Drop for CaptureTaskRegistration {
    fn drop(&mut self) {
        let state = self.app.state::<ApplicationState>();
        clear_capture_task(&state, &self.meeting_id);
    }
}

enum CaptureTaskCommand {
    Stop,
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct StartAttestation {
    participants_consented: bool,
    headphones: bool,
    operator_alone: bool,
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct CaptureAttemptReceipt {
    schema: String,
    meeting_id: String,
    attempt_id: String,
    created_at_epoch_seconds: u64,
    application_build_sha256: String,
    participant_notice_version: String,
    operator_attestation: StartAttestation,
    retention_policy_sha256: String,
}

struct AttemptContext {
    meeting_dir: PathBuf,
    application_build_sha256: String,
}

#[derive(Debug)]
enum WorkerCallError {
    Rejected,
    Supervisor(String),
}

impl WorkerCallError {
    fn is_supervisor(&self) -> bool {
        matches!(self, Self::Supervisor(_))
    }
}

impl std::fmt::Display for WorkerCallError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Rejected => formatter.write_str("worker rejected the operation"),
            Self::Supervisor(detail) => formatter.write_str(detail),
        }
    }
}

#[derive(Debug, PartialEq, Eq)]
enum CaptureEvent {
    Paused,
    Recording,
    Finalized {
        mic_samples: u64,
        system_samples: u64,
    },
    Failed {
        code: String,
    },
    Interrupted,
}

enum CaptureStreamItem {
    Event(CaptureEvent),
    ProtocolFailure,
    Closed,
}

struct CaptureProcess {
    child: Option<Child>,
    control: Option<File>,
    liveness: Option<File>,
    events: mpsc::Receiver<CaptureStreamItem>,
    reader_thread: Option<JoinHandle<()>>,
    process_group_id: i32,
    finished: bool,
}

impl CaptureProcess {
    fn spawn(
        executable: &Path,
        capture_directory: &Path,
        process_group_id: i32,
    ) -> Result<Self, String> {
        if !executable.is_file() || process_group_id <= 0 {
            return Err("capture helper is unavailable".into());
        }
        let capture_directory_file = File::open(capture_directory).map_err(error_text)?;
        let (control_read, control_write) = cloexec_pipe().map_err(error_text)?;
        let (event_read, event_write) = cloexec_pipe().map_err(error_text)?;
        let (liveness_read, liveness_write) = cloexec_pipe().map_err(error_text)?;
        let inherited = [
            capture_directory_file.as_raw_fd(),
            control_read.as_raw_fd(),
            event_write.as_raw_fd(),
            liveness_read.as_raw_fd(),
        ];
        let mut command = Command::new(executable);
        command
            .arg("--capture-dir-fd")
            .arg(inherited[0].to_string())
            .arg("--control-fd")
            .arg(inherited[1].to_string())
            .arg("--event-fd")
            .arg(inherited[2].to_string())
            .arg("--parent-liveness-fd")
            .arg(inherited[3].to_string())
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null());
        unsafe {
            command.pre_exec(move || {
                if libc::setpgid(0, process_group_id) != 0 {
                    return Err(io::Error::last_os_error());
                }
                for descriptor in inherited {
                    set_close_on_exec(descriptor, false)?;
                }
                Ok(())
            });
        }
        let mut child = command.spawn().map_err(error_text)?;
        drop(capture_directory_file);
        drop(control_read);
        drop(event_write);
        drop(liveness_read);

        let (sender, events) = mpsc::channel();
        let reader_thread = match std::thread::Builder::new()
            .name("meeting-capture-events".into())
            .spawn(move || read_capture_events(event_read, sender))
        {
            Ok(thread) => thread,
            Err(error) => {
                drop(control_write);
                drop(liveness_write);
                let _ = child.kill();
                let _ = child.wait();
                return Err(error.to_string());
            }
        };
        Ok(Self {
            child: Some(child),
            control: Some(control_write),
            liveness: Some(liveness_write),
            events,
            reader_thread: Some(reader_thread),
            process_group_id,
            finished: false,
        })
    }

    fn pid(&self) -> Result<u32, String> {
        self.child
            .as_ref()
            .map(Child::id)
            .ok_or_else(|| "capture helper is no longer running".into())
    }

    fn send(&mut self, command: u8) -> Result<(), String> {
        self.control
            .as_mut()
            .ok_or_else(|| "capture control channel is closed".to_string())?
            .write_all(&[command])
            .map_err(error_text)
    }

    fn receive_until(&self, deadline: Instant) -> Result<CaptureEvent, String> {
        let remaining = deadline.saturating_duration_since(Instant::now());
        if remaining.is_zero() {
            return Err("capture helper timed out".into());
        }
        match self.events.recv_timeout(remaining) {
            Ok(CaptureStreamItem::Event(event)) => Ok(event),
            Ok(CaptureStreamItem::ProtocolFailure) => {
                Err("capture helper returned an invalid event".into())
            }
            Ok(CaptureStreamItem::Closed) | Err(mpsc::RecvTimeoutError::Disconnected) => {
                Err("capture helper exited before completing".into())
            }
            Err(mpsc::RecvTimeoutError::Timeout) => Err("capture helper timed out".into()),
        }
    }

    fn receive_briefly(&self, timeout: Duration) -> Result<Option<CaptureEvent>, String> {
        match self.events.recv_timeout(timeout) {
            Ok(CaptureStreamItem::Event(event)) => Ok(Some(event)),
            Ok(CaptureStreamItem::ProtocolFailure) => {
                Err("capture helper returned an invalid event".into())
            }
            Ok(CaptureStreamItem::Closed) | Err(mpsc::RecvTimeoutError::Disconnected) => {
                Err("capture helper exited while recording".into())
            }
            Err(mpsc::RecvTimeoutError::Timeout) => Ok(None),
        }
    }

    fn finish_cleanly(&mut self, deadline: Instant) -> Result<(), String> {
        let Some(status) = self.wait_for_exit(deadline).map_err(error_text)? else {
            self.cleanup();
            return Err("capture helper did not exit after finalization".into());
        };
        if !status.success() {
            self.cleanup();
            return Err("capture helper reported an unsuccessful exit".into());
        }
        self.control.take();
        self.liveness.take();
        self.join_reader()?;
        self.finished = true;
        Ok(())
    }

    fn wait_for_exit(&mut self, deadline: Instant) -> io::Result<Option<ExitStatus>> {
        loop {
            let Some(child) = self.child.as_mut() else {
                return Ok(None);
            };
            if let Some(status) = child.try_wait()? {
                let _ = child.wait();
                self.child.take();
                return Ok(Some(status));
            }
            if Instant::now() >= deadline {
                return Ok(None);
            }
            std::thread::sleep(Duration::from_millis(10));
        }
    }

    fn join_reader(&mut self) -> Result<(), String> {
        if let Some(thread) = self.reader_thread.take() {
            thread
                .join()
                .map_err(|_| "capture event reader failed".to_string())?;
        }
        Ok(())
    }

    fn cleanup(&mut self) {
        self.control.take();
        self.liveness.take();
        let first_deadline = Instant::now() + Duration::from_millis(750);
        if self.wait_for_exit(first_deadline).ok().flatten().is_none() {
            let _ = signal_process_group(self.process_group_id, libc::SIGTERM);
            let second_deadline = Instant::now() + Duration::from_millis(750);
            if self.wait_for_exit(second_deadline).ok().flatten().is_none() {
                let _ = signal_process_group(self.process_group_id, libc::SIGKILL);
                if let Some(mut child) = self.child.take() {
                    let _ = child.wait();
                }
            }
        }
        let _ = self.join_reader();
        self.finished = true;
    }
}

impl Drop for CaptureProcess {
    fn drop(&mut self) {
        if !self.finished {
            self.cleanup();
        }
    }
}

#[tauri::command]
fn app_snapshot(state: State<'_, ApplicationState>) -> AppSnapshot {
    state
        .model
        .lock()
        .expect("application model lock")
        .snapshot()
}

#[tauri::command]
fn start_meeting(
    app: AppHandle,
    retention_days: u64,
    attestation: StartAttestation,
) -> Result<AppSnapshot, String> {
    validate_start_request(retention_days, &attestation)?;
    let state = app.state::<ApplicationState>();
    let _command = state.command_lock.lock().expect("command lock");
    let meeting_id = Uuid::new_v4().to_string();
    let attempt_id = Uuid::new_v4().to_string();
    let (sender, receiver) = mpsc::sync_channel(1);
    let snapshot = {
        let mut model = state.model.lock().expect("application model lock");
        if model.reducer.startup() != StartupState::Ready
            || model.reducer.capture() != CaptureState::Idle
        {
            return Err("A meeting cannot start from the current state.".into());
        }
        if !model.retention_operational {
            return Err("Audio retention needs attention before another meeting can start.".into());
        }
        let mut active = state.capture_task.lock().expect("capture task lock");
        if active.is_some() {
            return Err("Another capture attempt is already active.".into());
        }
        transition_capture(&mut model, CaptureState::Arming)?;
        model.clear_meeting_projection();
        model.meeting_id = Some(meeting_id.clone());
        *active = Some(CaptureTaskControl {
            meeting_id: meeting_id.clone(),
            sender,
        });
        model.snapshot()
    };
    let task_app = app.clone();
    let spawn_failure_meeting_id = meeting_id.clone();
    std::thread::Builder::new()
        .name("meeting-capture-attempt".into())
        .spawn(move || {
            run_capture_task(
                task_app,
                meeting_id,
                attempt_id,
                retention_days,
                attestation,
                receiver,
            )
        })
        .map_err(|error| {
            fail_capture_task(
                &app,
                None,
                false,
                true,
                "capture_task_spawn_failed",
                &error.to_string(),
                "The recording task could not start.",
            );
            clear_capture_task(&app.state::<ApplicationState>(), &spawn_failure_meeting_id);
            "The recording task could not start.".to_string()
        })?;
    Ok(snapshot)
}

#[tauri::command]
fn stop_meeting(app: AppHandle) -> Result<AppSnapshot, String> {
    let state = app.state::<ApplicationState>();
    let _command = state.command_lock.lock().expect("command lock");
    let mut model = state.model.lock().expect("application model lock");
    if model.reducer.capture() != CaptureState::Recording {
        return Err("No recording is ready to stop.".into());
    }
    transition_capture(&mut model, CaptureState::Stopping)?;
    let send_result = state
        .capture_task
        .lock()
        .expect("capture task lock")
        .as_ref()
        .ok_or_else(|| "The recording task is unavailable.".to_string())?
        .sender
        .try_send(CaptureTaskCommand::Stop);
    if send_result.is_err() {
        transition_capture(&mut model, CaptureState::RecoveredInterrupted)?;
        model.error = Some("The recording task ended before Stop completed.".into());
        return Err("The recording task ended before Stop completed.".into());
    }
    Ok(model.snapshot())
}

#[tauri::command]
fn dismiss_meeting(app: AppHandle) -> Result<AppSnapshot, String> {
    let state = app.state::<ApplicationState>();
    let _command = state.command_lock.lock().expect("command lock");
    let mut model = state.model.lock().expect("application model lock");
    if model.reducer.startup() != StartupState::Ready {
        return Err("Finish the installation check before starting another meeting.".into());
    }
    if state
        .capture_task
        .lock()
        .expect("capture task lock")
        .is_some()
    {
        return Err("The current meeting is still finishing.".into());
    }
    if !matches!(
        model.reducer.capture(),
        CaptureState::TranscriptReady
            | CaptureState::TranscriptionFailed
            | CaptureState::RecoveredInterrupted
    ) {
        return Err("The current meeting cannot be dismissed yet.".into());
    }
    transition_capture(&mut model, CaptureState::Idle)?;
    model.clear_meeting_projection();
    if !model.retention_operational && model.reducer.startup() == StartupState::Ready {
        model.error =
            Some("Audio retention needs attention before another meeting can start.".into());
        transition_startup(&mut model, StartupState::DiagnosticWritten)?;
    }
    Ok(model.snapshot())
}

fn prepare_startup_retry(model: &mut AppModel) -> Result<(), String> {
    transition_startup(model, StartupState::Retrying)?;
    if model.reducer.capture() == CaptureState::Idle {
        model.error = None;
    }
    Ok(())
}

#[tauri::command]
fn retry_startup(app: AppHandle) -> Result<AppSnapshot, String> {
    let state = app.state::<ApplicationState>();
    let _command = state.command_lock.lock().expect("command lock");
    if state
        .capture_task
        .lock()
        .expect("capture task lock")
        .is_some()
    {
        return Err("Startup cannot be retried while a meeting is active.".into());
    }
    let snapshot = {
        let mut model = state.model.lock().expect("application model lock");
        if !matches!(
            model.reducer.startup(),
            StartupState::RuntimeMissing
                | StartupState::ServiceTimeout
                | StartupState::DiagnosticWritten
        ) {
            return Err("The installation check is not waiting for a retry.".into());
        }
        prepare_startup_retry(&mut model)?;
        model.snapshot()
    };
    let task_app = app.clone();
    let spawned = std::thread::Builder::new()
        .name("meeting-runtime-retry".into())
        .spawn(move || initialize_application(task_app, true));
    if let Err(error) = spawned {
        write_diagnostic(&state, "startup_retry_spawn_failed", &error.to_string());
        finish_startup_failure(
            &state,
            true,
            StartupFailure::Diagnostic,
            "the installation retry could not start",
        );
        return Err("The installation retry could not start.".into());
    }
    Ok(snapshot)
}

#[cfg(feature = "preview-surface")]
#[tauri::command]
fn preview_library_snapshot(state: State<'_, ApplicationState>) -> library_reader::LibrarySnapshot {
    let storage = state
        .storage
        .lock()
        .expect("storage context lock")
        .as_ref()
        .map(|context| context.storage.clone());
    let Some(storage) = storage else {
        return library_reader::LibraryReader::unavailable_snapshot();
    };
    let coordination = match state.meeting_storage_coordination() {
        Ok(coordination) => coordination,
        Err(_) => return library_reader::LibraryReader::unavailable_snapshot(),
    };
    with_meeting_storage_sequence(&coordination, |active_meeting_ids| {
        let mut reader = match library_reader::LibraryReader::rebuild(storage, active_meeting_ids) {
            Ok(reader) => reader,
            Err(_) => return library_reader::LibraryReader::unavailable_snapshot(),
        };
        let snapshot = reader.snapshot(active_meeting_ids);
        let Ok(mut library) = state.preview_library.lock() else {
            return library_reader::LibraryReader::unavailable_snapshot();
        };
        *library = Some(reader);
        snapshot
    })
    .unwrap_or_else(|_| library_reader::LibraryReader::unavailable_snapshot())
}

#[cfg(feature = "preview-surface")]
#[tauri::command]
fn preview_profile_snapshot() -> PreviewProfileSnapshot {
    PreviewProfileSnapshot {
        state: "setup-unavailable",
    }
}

#[cfg(feature = "preview-surface")]
#[tauri::command]
fn preview_library_search(
    query: String,
    state: State<'_, ApplicationState>,
) -> library_reader::LibrarySearchResponse {
    let mut response = state.with_preview_library(
        library_reader::LibraryReader::unavailable_search,
        |reader, active| reader.search(&query, active),
    );
    // Preview's active reader is deliberately transcript/title metadata only.
    // The broader projection contract also supports future claim readers, but
    // this surface cannot make claim text a search destination yet.
    response
        .results
        .retain(|result| matches!(result.kind, "transcript" | "withheld" | "meeting"));
    if matches!(response.state, "results" | "results-incomplete") && response.results.is_empty() {
        if response.unavailable_count == 0 {
            response.state = "no-results";
            response.message =
                "No retained transcript, title, or folder matched that search.".into();
        } else {
            response.state = "incomplete";
            response.message = format!(
                "No retained transcript, title, or folder match was found among readable meetings. {} could not be searched.",
                response.unavailable_count
            );
        }
    }
    response
}

#[cfg(feature = "preview-surface")]
#[tauri::command]
fn preview_library_open_search_result(
    handle: String,
    state: State<'_, ApplicationState>,
) -> library_reader::LibrarySearchOpenResponse {
    state.with_preview_library(
        || library_reader::LibrarySearchOpenResponse {
            state: "unavailable",
            transcript_handle: None,
            meeting_id: None,
            source_turn_index: None,
            start: None,
            end: None,
            message: "The local Preview library is unavailable. Reopen the app and try again."
                .into(),
        },
        |reader, active| reader.open_search_result(&handle, active),
    )
}

#[cfg(feature = "preview-surface")]
#[tauri::command]
fn preview_library_open_note(
    handle: String,
    state: State<'_, ApplicationState>,
) -> library_reader::LibraryNoteResponse {
    state.with_preview_library(
        || library_reader::LibraryReader::unavailable_note(""),
        |reader, active| reader.open_note(&handle, active),
    )
}

#[cfg(feature = "preview-surface")]
#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct PreviewAudioDeletionResponse {
    state: &'static str,
    audio_retention: Option<library_reader::LibraryAudioRetention>,
    message: String,
}

#[cfg(any(feature = "preview-surface", test))]
#[derive(Debug, PartialEq, Eq)]
struct PreviewAudioDeletionGateRefusal {
    state: &'static str,
    message: &'static str,
}

#[cfg(any(feature = "preview-surface", test))]
fn with_preview_audio_deletion_gate<T>(
    startup: StartupState,
    capture: CaptureState,
    operation: impl FnOnce() -> T,
) -> Result<T, PreviewAudioDeletionGateRefusal> {
    if startup != StartupState::Ready {
        return Err(PreviewAudioDeletionGateRefusal {
            state: "not-ready",
            message: "Recording deletion is available after the installation check is ready.",
        });
    }
    if !matches!(capture, CaptureState::Idle | CaptureState::TranscriptReady) {
        return Err(PreviewAudioDeletionGateRefusal {
            state: "capture-active",
            message: "Recording deletion is unavailable while a meeting is active or recovering.",
        });
    }
    Ok(operation())
}

#[cfg(feature = "preview-surface")]
#[tauri::command]
fn preview_delete_meeting_audio(
    handle: String,
    state: State<'_, ApplicationState>,
) -> PreviewAudioDeletionResponse {
    let Ok(_command) = state.command_lock.lock() else {
        return PreviewAudioDeletionResponse {
            state: "unavailable",
            audio_retention: None,
            message: "Recording deletion is unavailable. Reopen Library and try again.".into(),
        };
    };
    let (startup, capture) = match state.model.lock() {
        Ok(model) => (model.reducer.startup(), model.reducer.capture()),
        Err(_) => {
            return PreviewAudioDeletionResponse {
                state: "unavailable",
                audio_retention: None,
                message: "Recording deletion is unavailable. Reopen Library and try again.".into(),
            };
        }
    };
    let access = match with_preview_audio_deletion_gate(startup, capture, || {
        state.with_preview_library(
            || library_reader::LibraryAudioDeletionAccess {
                state: "unavailable",
                meeting_id: None,
                message: "Recording deletion is unavailable. Reopen Library and try again.".into(),
            },
            |reader, active| reader.authorize_audio_deletion(&handle, active),
        )
    }) {
        Ok(access) => access,
        Err(refusal) => {
            return PreviewAudioDeletionResponse {
                state: refusal.state,
                audio_retention: None,
                message: refusal.message.into(),
            };
        }
    };

    // Any attempted mutation boundary invalidates every retained reader handle.
    *state.preview_library.lock().expect("preview library lock") = None;

    let storage = state
        .storage
        .lock()
        .expect("storage context lock")
        .as_ref()
        .map(|context| context.storage.clone());
    let retention_for = |meeting_id: &str| {
        let storage = storage.as_ref()?;
        let coordination = state.meeting_storage_coordination().ok()?;
        with_meeting_storage_sequence(&coordination, |active| {
            (!active.contains(meeting_id))
                .then(|| library_reader::LibraryReader::read_audio_retention(storage, meeting_id))
        })
        .ok()
        .flatten()
    };

    let Some(meeting_id) = access.meeting_id else {
        return PreviewAudioDeletionResponse {
            state: access.state,
            audio_retention: None,
            message: access.message,
        };
    };
    if access.state != "authorized" {
        return PreviewAudioDeletionResponse {
            state: access.state,
            audio_retention: retention_for(&meeting_id),
            message: access.message,
        };
    }

    let result = state
        .manual_audio_deletion_facade()
        .delete_audio(ManualAudioDeletionUiArgs {
            meeting_id: meeting_id.clone(),
            review: AudioDeletionReview::Reviewed,
        });
    let (response_state, message) = match result {
        Ok(ManualAudioDeletionFacadeOutcome::AudioReleased) => (
            "released",
            "The meeting recording was permanently deleted from this Mac.",
        ),
        Ok(ManualAudioDeletionFacadeOutcome::RecoveredRemoval) => (
            "released",
            "The interrupted recording deletion was recovered and completed.",
        ),
        Ok(ManualAudioDeletionFacadeOutcome::AlreadyReleased) => (
            "already-released",
            "This meeting recording was already deleted.",
        ),
        Ok(ManualAudioDeletionFacadeOutcome::DeferredActive) => (
            "deferred-active",
            "Recording deletion was deferred because this meeting is still active.",
        ),
        Err(ManualAudioDeletionFacadeError::MeetingActionInProgress) => (
            "action-in-progress",
            "Another action for this meeting is in progress. Reopen Library and try again.",
        ),
        Err(
            ManualAudioDeletionFacadeError::ConfirmationRequired
            | ManualAudioDeletionFacadeError::WriterLockUnavailable
            | ManualAudioDeletionFacadeError::StorageUnavailable,
        ) => (
            "unavailable",
            "Recording deletion could not complete. Reopen Library and try again.",
        ),
    };
    PreviewAudioDeletionResponse {
        state: response_state,
        audio_retention: retention_for(&meeting_id),
        message: message.into(),
    }
}

#[cfg(feature = "preview-surface")]
#[tauri::command]
fn preview_library_open_evidence(
    handle: String,
    locator_ordinal: usize,
    state: State<'_, ApplicationState>,
) -> library_reader::LibraryEvidenceResponse {
    state.with_preview_library(
        library_reader::LibraryReader::unavailable_evidence,
        |reader, active| reader.open_evidence(&handle, locator_ordinal, active),
    )
}

#[cfg(feature = "preview-surface")]
#[tauri::command]
fn preview_library_open_transcript(
    handle: String,
    state: State<'_, ApplicationState>,
) -> PreviewLibraryTranscript {
    state.with_preview_library(
        || PreviewLibraryTranscript {
            state: "unavailable",
            meeting_id: None,
            turns: Vec::new(),
            warnings: Vec::new(),
            message: "The local Preview library is unavailable. Reopen the app and try again."
                .into(),
        },
        |reader, active| match reader.open_transcript_bound(
            &handle,
            active,
            |storage, meeting_id, artifact| {
                (
                    meeting_id.to_owned(),
                    load_bound_preview_transcript_projection(storage, meeting_id, artifact),
                )
            },
        ) {
            Ok((meeting_id, Ok((turns, warnings)))) => PreviewLibraryTranscript {
                state: "transcript",
                meeting_id: Some(meeting_id),
                turns,
                warnings,
                message: "Retained transcript from this Preview meeting.".into(),
            },
            Ok((_, Err(_))) => PreviewLibraryTranscript {
                state: "stale",
                meeting_id: None,
                turns: Vec::new(),
                warnings: Vec::new(),
                message: "That transcript is no longer available. Reopen Library and try again."
                    .into(),
            },
            Err(opened) => PreviewLibraryTranscript {
                state: opened.state,
                meeting_id: None,
                turns: Vec::new(),
                warnings: Vec::new(),
                message: opened.message,
            },
        },
    )
}

#[cfg(any(feature = "preview-surface", test))]
fn load_bound_preview_transcript_projection(
    storage: &StorageRoot,
    meeting_id: &str,
    expected: &ArtifactRef,
) -> Result<(Vec<TranscriptTurn>, Vec<String>), String> {
    let directory = meeting_dir(storage, meeting_id).map_err(error_text)?;
    let meeting = load_meeting(&directory).map_err(error_text)?;
    if meeting.artifacts.current_transcript.as_ref() != Some(expected) {
        return Err("the selected transcript pointer changed".into());
    }
    let path = resolve_artifact(&directory, &expected.relative_path).map_err(error_text)?;
    let bytes = read_private_bytes(&path, TRANSCRIPT_MAX_BYTES).map_err(error_text)?;
    if format!("{:x}", Sha256::digest(&bytes)) != expected.sha256 {
        return Err("the selected transcript bytes changed".into());
    }
    let (turns, mut warnings) = parse_transcript_projection(&bytes)?;
    let current = load_meeting(&directory).map_err(error_text)?;
    if current.artifacts.current_transcript.as_ref() != Some(expected)
        || artifact_ref(&directory, &expected.relative_path).map_err(error_text)? != *expected
    {
        return Err("the selected transcript changed while opening".into());
    }
    if current.retention.state == AudioState::Released {
        warnings.push(
            "Meeting audio was deleted under the selected retention period. The transcript remains."
                .into(),
        );
    }
    Ok((turns, warnings))
}

#[cfg(not(feature = "library-dev-surface"))]
fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _, _| {
            if let Some(window) = app.get_webview_window(ACTIVE_WINDOW_LABEL) {
                let _ = window.set_focus();
            }
        }))
        .manage(ApplicationState::default())
        .invoke_handler(tauri::generate_handler![
            app_snapshot,
            start_meeting,
            stop_meeting,
            dismiss_meeting,
            retry_startup,
            #[cfg(feature = "preview-surface")]
            preview_library_snapshot,
            #[cfg(feature = "preview-surface")]
            preview_profile_snapshot,
            #[cfg(feature = "preview-surface")]
            preview_library_search,
            #[cfg(feature = "preview-surface")]
            preview_library_open_search_result,
            #[cfg(feature = "preview-surface")]
            preview_library_open_note,
            #[cfg(feature = "preview-surface")]
            preview_library_open_evidence,
            #[cfg(feature = "preview-surface")]
            preview_library_open_transcript,
            #[cfg(feature = "preview-surface")]
            preview_delete_meeting_audio
        ])
        .setup(|app| {
            let handle = app.handle().clone();
            std::thread::Builder::new()
                .name("meeting-runtime-startup".into())
                .spawn(move || initialize_application(handle, false))
                .map_err(io_error)?;
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("Local Meeting Notes shell failed");
}

#[cfg(feature = "library-dev-surface")]
fn main() {
    library_dev_surface::run();
}

fn initialize_application(app: AppHandle, retry: bool) {
    let state = app.state::<ApplicationState>();
    {
        let mut model = state.model.lock().expect("application model lock");
        model.retention_operational = false;
        if !retry && transition_startup(&mut model, StartupState::Checking).is_err() {
            return;
        }
    }

    state.runtime.lock().expect("runtime identity lock").take();
    let worker_cleanup = state
        .worker
        .lock()
        .expect("worker process lock")
        .take()
        .map(|mut worker| worker.stop_and_wait(Duration::from_millis(750)));
    if let Some(Err(error)) = worker_cleanup {
        write_diagnostic(&state, "worker_cleanup_failed", &error.to_string());
        finish_startup_failure(
            &state,
            retry,
            StartupFailure::Diagnostic,
            "the previous worker could not be stopped safely",
        );
        return;
    }

    let storage_context = match create_storage_context(&app) {
        Ok(context) => context,
        Err(error) => {
            finish_startup_failure(&state, retry, StartupFailure::Diagnostic, &error);
            return;
        }
    };
    if let Err(error) = ensure_app_data_writer_lock(&state, &storage_context.storage) {
        finish_startup_failure(&state, retry, StartupFailure::Diagnostic, &error);
        return;
    }
    *state.storage.lock().expect("storage context lock") = Some(storage_context.clone());

    let coordination = match state.meeting_storage_coordination() {
        Ok(coordination) => coordination,
        Err(_) => {
            finish_startup_failure(
                &state,
                retry,
                StartupFailure::Diagnostic,
                "meeting storage coordination is unavailable",
            );
            return;
        }
    };
    let storage_sequence = match coordination.lock_sequence() {
        Ok(sequence) => sequence,
        Err(_) => {
            finish_startup_failure(
                &state,
                retry,
                StartupFailure::Diagnostic,
                "meeting storage coordination is unavailable",
            );
            return;
        }
    };

    let recovery = scan_and_recover(
        &storage_context.storage,
        now_epoch_seconds(),
        &SystemProcessInspector,
        &SystemGroupSignaler,
        Duration::from_millis(750),
    );
    let (recovery_ready, restorable_meetings) = match recovery {
        Ok(report) => {
            let mut retention_ready = true;
            let mut restorable_meetings = Vec::new();
            for meeting in &report.meetings {
                match meeting.disposition {
                    RecoveryDisposition::Valid | RecoveryDisposition::RecoveredAudioDeletion => {
                        restorable_meetings.push(meeting.meeting_id.clone());
                    }
                    RecoveryDisposition::Quarantined(code) => {
                        if code == RecoveryCode::RetentionMismatch {
                            retention_ready = false;
                        }
                        let _ = write_private_diagnostic(
                            &storage_context.diagnostics,
                            code.as_str(),
                            &format!(
                                "meeting {} was quarantined without mutation",
                                meeting.meeting_id
                            ),
                        );
                    }
                    RecoveryDisposition::OwnershipAmbiguous => {
                        let _ = write_private_diagnostic(
                            &storage_context.diagnostics,
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
            (
                !report.blocks_capture && retention_ready,
                restorable_meetings,
            )
        }
        Err(error) => {
            let _ = write_private_diagnostic(
                &storage_context.diagnostics,
                "meeting_recovery_failed",
                &error.to_string(),
            );
            (false, Vec::new())
        }
    };
    if !recovery_ready {
        finish_startup_failure(
            &state,
            retry,
            StartupFailure::Diagnostic,
            "meeting recovery requires attention",
        );
        return;
    }
    let restored_transcript =
        match load_latest_transcript_projection(&storage_context.storage, &restorable_meetings) {
            Ok(projection) => projection,
            Err(error) => {
                let _ = write_private_diagnostic(
                    &storage_context.diagnostics,
                    "transcript_restore_failed",
                    &error,
                );
                finish_startup_failure(
                    &state,
                    retry,
                    StartupFailure::Diagnostic,
                    "a retained transcript could not be reopened safely",
                );
                return;
            }
        };
    drop(storage_sequence);
    {
        let mut model = state.model.lock().expect("application model lock");
        model.retention_operational = true;
    }
    start_retention_executor(&app, &storage_context);

    let manifest = match RuntimeManifest::load_and_verify(&storage_context.manifest_path) {
        Ok(manifest) if manifest.is_internal_alpha() => manifest,
        _ => {
            finish_startup_failure(
                &state,
                retry,
                StartupFailure::Runtime,
                "the packaged runtime is missing or changed",
            );
            return;
        }
    };
    let worker_path = storage_context.resource_root.join(&manifest.runtime.path);
    let mut command = Command::new(worker_path);
    command
        .args(["-E", "-s", "-B", "-m", "worker.main"])
        .arg("--app-data-root")
        .arg(storage_context.storage.path())
        .arg("--runtime-manifest")
        .arg(&storage_context.manifest_path)
        .current_dir(&storage_context.resource_root);
    let mut worker = match OwnedChild::spawn(&mut command) {
        Ok(worker) => worker,
        Err(SupervisionError::MissingChild) => {
            finish_startup_failure(
                &state,
                retry,
                StartupFailure::Runtime,
                "the packaged worker is missing",
            );
            return;
        }
        Err(error) => {
            let _ = write_private_diagnostic(
                &storage_context.diagnostics,
                "worker_spawn_failed",
                &error.to_string(),
            );
            finish_startup_failure(
                &state,
                retry,
                StartupFailure::Diagnostic,
                "the packaged worker could not start",
            );
            return;
        }
    };
    let ready = worker.wait_ready(Duration::from_secs(10), &internal_alpha_operations());
    match ready {
        Ok(ready) if manifest.matches_ready(&ready) => {}
        Err(SupervisionError::ReadyTimeout) => {
            finish_startup_failure(
                &state,
                retry,
                StartupFailure::Timeout,
                "the packaged worker did not answer",
            );
            return;
        }
        Ok(_) => {
            if let Err(error) = worker.stop_and_wait(Duration::from_millis(750)) {
                let _ = write_private_diagnostic(
                    &storage_context.diagnostics,
                    "worker_identity_mismatch_cleanup_failed",
                    &error.to_string(),
                );
                finish_startup_failure(
                    &state,
                    retry,
                    StartupFailure::Diagnostic,
                    "the mismatched worker could not be stopped safely",
                );
                return;
            }
            finish_startup_failure(
                &state,
                retry,
                StartupFailure::Runtime,
                "the packaged worker identity does not match the application",
            );
            return;
        }
        Err(error) => {
            let _ = write_private_diagnostic(
                &storage_context.diagnostics,
                "worker_startup_failed",
                &error.to_string(),
            );
            finish_startup_failure(
                &state,
                retry,
                StartupFailure::Diagnostic,
                "the packaged worker failed its startup check",
            );
            return;
        }
    }

    let retention_ready = state
        .model
        .lock()
        .expect("application model lock")
        .retention_operational;
    if !retention_ready {
        if let Err(error) = worker.stop_and_wait(Duration::from_millis(750)) {
            let _ = write_private_diagnostic(
                &storage_context.diagnostics,
                "worker_retention_block_cleanup_failed",
                &error.to_string(),
            );
        }
        finish_startup_failure(
            &state,
            retry,
            StartupFailure::Diagnostic,
            "audio retention needs attention before startup can finish",
        );
        return;
    }

    let runtime = RuntimeIdentity {
        admission: "internal-alpha".into(),
        worker_build_sha256: manifest.worker.sha256.clone(),
        worker_executable_sha256: manifest.runtime.sha256.clone(),
        tap_build_sha256: manifest.tap.sha256.clone(),
        tap_path: storage_context.resource_root.join(&manifest.tap.path),
    };
    *state.worker.lock().expect("worker process lock") = Some(worker);
    *state.runtime.lock().expect("runtime identity lock") = Some(runtime.clone());
    let mut model = state.model.lock().expect("application model lock");
    model.admission = runtime.admission;
    if let Some(projection) = restored_transcript
        && let Err(error) = apply_restored_transcript_projection(&mut model, projection)
    {
        model.error = Some(error);
        let _ = transition_startup(&mut model, StartupState::DiagnosticWritten);
        return;
    }
    if let Err(error) = transition_startup(&mut model, StartupState::Ready) {
        model.error = Some(error);
    }
}

enum StartupFailure {
    Runtime,
    Timeout,
    Diagnostic,
}

fn finish_startup_failure(
    state: &ApplicationState,
    retry: bool,
    failure: StartupFailure,
    detail: &str,
) {
    let target = match (retry, failure) {
        (_, StartupFailure::Timeout) => StartupState::ServiceTimeout,
        (false, StartupFailure::Runtime) => StartupState::RuntimeMissing,
        (false, StartupFailure::Diagnostic) => StartupState::DiagnosticWritten,
        (true, StartupFailure::Runtime) => StartupState::ReinstallRequired,
        (true, StartupFailure::Diagnostic) => StartupState::DiagnosticWritten,
    };
    let mut model = state.model.lock().expect("application model lock");
    if transition_startup(&mut model, target).is_err() {
        model.error = Some("The installation check stopped in an invalid state.".into());
    } else {
        model.error = Some(detail.into());
    }
}

fn create_storage_context(app: &AppHandle) -> Result<StorageContext, String> {
    let app_data = app.path().app_data_dir().map_err(error_text)?;
    let resource_root = app.path().resource_dir().map_err(error_text)?;
    #[cfg(debug_assertions)]
    let protected_root = repository_root();
    #[cfg(not(debug_assertions))]
    let protected_root = resource_root.clone();
    let storage = StorageRoot::create(&app_data, &protected_root).map_err(error_text)?;
    Ok(StorageContext {
        manifest_path: resource_root.join("app-runtime.json"),
        diagnostics: storage.path().join("diagnostics"),
        storage,
        resource_root,
    })
}

fn ensure_app_data_writer_lock(
    state: &ApplicationState,
    storage: &StorageRoot,
) -> Result<(), String> {
    let mut held = state
        .app_data_writer_lock
        .lock()
        .map_err(|_| "the app-data writer lock is unavailable".to_string())?;
    if held.is_some() {
        return Ok(());
    }
    *held = Some(acquire_app_data_writer_lock(storage)?);
    Ok(())
}

fn acquire_app_data_writer_lock(storage: &StorageRoot) -> Result<AppDataWriterLock, String> {
    AppDataWriterLock::acquire(storage).map_err(error_text)
}

#[cfg(debug_assertions)]
fn repository_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(3)
        .expect("repository root above apps/desktop/src-tauri")
        .to_path_buf()
}

fn start_retention_executor(app: &AppHandle, context: &StorageContext) {
    let state = app.state::<ApplicationState>();
    if state.retention_started.swap(true, Ordering::SeqCst) {
        return;
    }
    let app = app.clone();
    let storage = context.storage.clone();
    let diagnostics = context.diagnostics.clone();
    std::thread::spawn(move || {
        let mut reported_quarantines = HashSet::new();
        loop {
            std::thread::sleep(Duration::from_secs(30));
            let state = app.state::<ApplicationState>();
            let coordination = match state.meeting_storage_coordination() {
                Ok(coordination) => coordination,
                Err(_) => {
                    let _ = write_private_diagnostic(
                        &diagnostics,
                        "retention_coordination_failed",
                        "meeting storage coordination is unavailable",
                    );
                    mark_retention_unavailable(&app);
                    continue;
                }
            };
            let storage_sequence = match coordination.lock_sequence() {
                Ok(sequence) => sequence,
                Err(_) => {
                    let _ = write_private_diagnostic(
                        &diagnostics,
                        "retention_coordination_failed",
                        "meeting storage sequence lock is unavailable",
                    );
                    mark_retention_unavailable(&app);
                    continue;
                }
            };
            let active_meetings = match storage_sequence.active_meeting_ids() {
                Ok(active) => active,
                Err(_) => {
                    drop(storage_sequence);
                    let _ = write_private_diagnostic(
                        &diagnostics,
                        "retention_coordination_failed",
                        "active meeting registry is unavailable",
                    );
                    mark_retention_unavailable(&app);
                    continue;
                }
            };
            let retention_result =
                execute_due_retention_excluding(&storage, now_epoch_seconds(), &active_meetings);
            drop(storage_sequence);
            match retention_result {
                Ok(outcomes) => {
                    let mut retention_failed = false;
                    for outcome in outcomes {
                        if let RetentionOutcome::Quarantined(meeting_id) = outcome {
                            retention_failed = true;
                            if reported_quarantines.insert(meeting_id.clone()) {
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
                    if retention_failed {
                        mark_retention_unavailable(&app);
                    }
                }
                Err(error) => {
                    let _ = write_private_diagnostic(
                        &diagnostics,
                        "retention_tick_failed",
                        &error.to_string(),
                    );
                    mark_retention_unavailable(&app);
                }
            }
        }
    });
}

fn mark_retention_unavailable(app: &AppHandle) {
    let state = app.state::<ApplicationState>();
    let mut model = state.model.lock().expect("application model lock");
    model.retention_operational = false;
    model.error = Some("Audio retention needs attention before another meeting can start.".into());
    if model.reducer.capture() == CaptureState::Idle
        && model.reducer.startup() == StartupState::Ready
    {
        let _ = transition_startup(&mut model, StartupState::DiagnosticWritten);
    }
}

fn run_capture_task(
    app: AppHandle,
    meeting_id: String,
    attempt_id: String,
    retention_days: u64,
    attestation: StartAttestation,
    commands: mpsc::Receiver<CaptureTaskCommand>,
) {
    let state = app.state::<ApplicationState>();
    let _task_registration = CaptureTaskRegistration {
        app: app.clone(),
        meeting_id: meeting_id.clone(),
    };
    let storage = match state.storage.lock().expect("storage context lock").clone() {
        Some(storage) => storage,
        None => {
            fail_capture_task(
                &app,
                Some(&meeting_id),
                false,
                true,
                "capture_storage_unavailable",
                "storage context is missing",
                "Private meeting storage is unavailable.",
            );
            return;
        }
    };
    let runtime = match state.runtime.lock().expect("runtime identity lock").clone() {
        Some(runtime) => runtime,
        None => {
            fail_capture_task(
                &app,
                Some(&meeting_id),
                false,
                true,
                "capture_runtime_unavailable",
                "runtime identity is missing",
                "The local runtime is unavailable.",
            );
            return;
        }
    };
    let (process_group_id, initial_worker_identity) = match inspect_worker(&state, &runtime) {
        Ok(identity) => identity,
        Err(error) => {
            fail_capture_task(
                &app,
                Some(&meeting_id),
                false,
                true,
                "capture_worker_unavailable",
                &error,
                "The local worker stopped before recording began.",
            );
            return;
        }
    };
    let coordination = match state.meeting_storage_coordination() {
        Ok(coordination) => coordination,
        Err(error) => {
            fail_capture_task(
                &app,
                Some(&meeting_id),
                false,
                true,
                "capture_storage_coordination_failed",
                &error,
                "Private meeting storage could not be reserved safely.",
            );
            return;
        }
    };
    let _active_meeting_lease = match coordination.acquire(&meeting_id) {
        Ok(lease) => lease,
        Err(error) => {
            let error = error.to_string();
            fail_capture_task(
                &app,
                Some(&meeting_id),
                false,
                true,
                "capture_storage_coordination_failed",
                &error,
                "Private meeting storage could not be reserved safely.",
            );
            return;
        }
    };
    let attempt = match create_attempt(
        &storage.storage,
        &meeting_id,
        &attempt_id,
        retention_days,
        attestation,
    ) {
        Ok(attempt) => attempt,
        Err(error) => {
            fail_capture_task(
                &app,
                Some(&meeting_id),
                false,
                true,
                "capture_attempt_write_failed",
                &error,
                "The private attempt receipt could not be saved.",
            );
            return;
        }
    };

    let mut helper = match CaptureProcess::spawn(
        &runtime.tap_path,
        &attempt.meeting_dir.join("capture"),
        process_group_id,
    ) {
        Ok(helper) => helper,
        Err(error) => {
            fail_capture_task(
                &app,
                Some(&meeting_id),
                false,
                false,
                "capture_helper_spawn_failed",
                &error,
                "The audio helper could not start.",
            );
            return;
        }
    };
    match helper.receive_until(Instant::now() + Duration::from_secs(10)) {
        Ok(CaptureEvent::Paused) => {}
        Ok(_) => {
            fail_capture_task(
                &app,
                Some(&meeting_id),
                false,
                false,
                "capture_helper_bad_pause",
                "capture helper did not begin in paused state",
                "The audio helper did not start safely.",
            );
            return;
        }
        Err(error) => {
            fail_capture_task(
                &app,
                Some(&meeting_id),
                false,
                false,
                "capture_helper_pause_failed",
                &error,
                "The audio helper did not reach its safe paused state.",
            );
            return;
        }
    }

    let helper_identity = match helper.pid().and_then(inspect_process) {
        Ok(identity) if identity.executable_sha256 == runtime.tap_build_sha256 => identity,
        _ => {
            fail_capture_task(
                &app,
                Some(&meeting_id),
                false,
                true,
                "capture_helper_identity_failed",
                "capture helper identity could not be established",
                "The audio helper identity could not be verified.",
            );
            return;
        }
    };
    let current_worker_identity = match inspect_process(initial_worker_identity.pid) {
        Ok(identity)
            if identity == initial_worker_identity
                && identity.executable_sha256 == runtime.worker_executable_sha256 =>
        {
            identity
        }
        _ => {
            fail_capture_task(
                &app,
                Some(&meeting_id),
                false,
                true,
                "capture_worker_identity_changed",
                "worker identity changed before ownership commit",
                "The local worker changed before recording began.",
            );
            return;
        }
    };
    let ownership = OwnershipReceipt {
        schema: OwnershipSchema::V1,
        process_group_id,
        application_build_sha256: attempt.application_build_sha256.clone(),
        worker_build_sha256: runtime.worker_build_sha256.clone(),
        tap_build_sha256: runtime.tap_build_sha256.clone(),
        children: vec![current_worker_identity, helper_identity],
    };
    if write_ownership_receipt(&attempt.meeting_dir, &ownership).is_err() {
        fail_capture_task(
            &app,
            Some(&meeting_id),
            false,
            true,
            "capture_ownership_write_failed",
            "capture ownership receipt could not become durable",
            "The capture ownership receipt could not be saved.",
        );
        return;
    }
    let ownership_ref = match artifact_ref(&attempt.meeting_dir, "ownership.json") {
        Ok(reference) => reference,
        Err(error) => {
            fail_capture_task(
                &app,
                Some(&meeting_id),
                false,
                true,
                "capture_ownership_verify_failed",
                &error.to_string(),
                "The capture ownership receipt could not be verified.",
            );
            return;
        }
    };
    let mut meeting = match load_meeting(&attempt.meeting_dir) {
        Ok(meeting) => meeting,
        Err(error) => {
            fail_capture_task(
                &app,
                Some(&meeting_id),
                false,
                true,
                "capture_meeting_load_failed",
                &error.to_string(),
                "The meeting record could not be reopened.",
            );
            return;
        }
    };
    meeting.artifacts.ownership = Some(ownership_ref);
    meeting.lifecycle = MeetingLifecycle::Incomplete;
    if let Err(error) = write_meeting(&attempt.meeting_dir, &meeting) {
        fail_capture_task(
            &app,
            Some(&meeting_id),
            false,
            true,
            "capture_meeting_ownership_commit_failed",
            &error.to_string(),
            "The meeting ownership record could not be committed.",
        );
        return;
    }
    let recovery_required = true;
    if let Err(error) = helper.send(b'S') {
        fail_capture_task(
            &app,
            Some(&meeting_id),
            recovery_required,
            true,
            "capture_start_signal_failed",
            &error,
            "Recording could not begin.",
        );
        return;
    }
    match helper.receive_until(Instant::now() + CAPTURE_ARM_TIMEOUT) {
        Ok(CaptureEvent::Recording) => {}
        Ok(CaptureEvent::Failed { code }) => {
            fail_capture_task(
                &app,
                Some(&meeting_id),
                recovery_required,
                true,
                "capture_hardware_failed",
                &format!("capture helper failed with code {code}"),
                capture_user_message(&code),
            );
            return;
        }
        Ok(_) => {
            fail_capture_task(
                &app,
                Some(&meeting_id),
                recovery_required,
                true,
                "capture_recording_event_invalid",
                "capture helper emitted an unexpected event before recording",
                "Both audio channels did not become ready.",
            );
            return;
        }
        Err(error) => {
            fail_capture_task(
                &app,
                Some(&meeting_id),
                recovery_required,
                true,
                "capture_recording_event_failed",
                &error,
                "Both audio channels did not become ready.",
            );
            return;
        }
    }
    let recording_started = Instant::now();
    let started_at_epoch_seconds = now_epoch_seconds();
    {
        let mut model = state.model.lock().expect("application model lock");
        if transition_capture(&mut model, CaptureState::Recording).is_err() {
            drop(model);
            fail_capture_task(
                &app,
                Some(&meeting_id),
                recovery_required,
                true,
                "capture_recording_transition_failed",
                "application state changed during capture arming",
                "The recording state could not be confirmed.",
            );
            return;
        }
        model.started_at_epoch_seconds = Some(started_at_epoch_seconds);
        model.mic_state = Some("Active".into());
        model.system_state = Some("Active".into());
    }

    loop {
        match commands.try_recv() {
            Ok(CaptureTaskCommand::Stop) => break,
            Err(mpsc::TryRecvError::Disconnected) => {
                fail_capture_task(
                    &app,
                    Some(&meeting_id),
                    recovery_required,
                    true,
                    "capture_control_disconnected",
                    "application capture control closed",
                    "The recording control closed unexpectedly.",
                );
                return;
            }
            Err(mpsc::TryRecvError::Empty) => {}
        }
        match helper.receive_briefly(Duration::from_millis(100)) {
            Ok(None) => {}
            Ok(Some(CaptureEvent::Failed { code })) => {
                fail_capture_task(
                    &app,
                    Some(&meeting_id),
                    recovery_required,
                    true,
                    "capture_failed_while_recording",
                    &format!("capture helper failed with code {code}"),
                    capture_user_message(&code),
                );
                return;
            }
            Ok(Some(CaptureEvent::Interrupted)) => {
                fail_capture_task(
                    &app,
                    Some(&meeting_id),
                    recovery_required,
                    true,
                    "capture_interrupted",
                    "capture helper reported interruption",
                    "Recording was interrupted before both files were finalized.",
                );
                return;
            }
            Ok(Some(_)) | Err(_) => {
                fail_capture_task(
                    &app,
                    Some(&meeting_id),
                    recovery_required,
                    true,
                    "capture_event_invalid",
                    "capture helper emitted an invalid event sequence",
                    "The audio helper stopped following the recording protocol.",
                );
                return;
            }
        }
    }

    let capture_elapsed_samples = match elapsed_samples(recording_started.elapsed()) {
        Ok(samples) => samples,
        Err(error) => {
            fail_capture_task(
                &app,
                Some(&meeting_id),
                recovery_required,
                true,
                "capture_elapsed_time_invalid",
                &error,
                "The recording exceeded the supported duration.",
            );
            return;
        }
    };
    if let Err(error) = helper.send(b'X') {
        fail_capture_task(
            &app,
            Some(&meeting_id),
            recovery_required,
            true,
            "capture_stop_signal_failed",
            &error,
            "The audio helper did not receive Stop.",
        );
        return;
    }
    let finalized = match helper.receive_until(Instant::now() + CAPTURE_STOP_TIMEOUT) {
        Ok(CaptureEvent::Finalized {
            mic_samples,
            system_samples,
        }) if mic_samples > 0 && system_samples > 0 => (mic_samples, system_samples),
        Ok(CaptureEvent::Failed { code }) => {
            fail_capture_task(
                &app,
                Some(&meeting_id),
                recovery_required,
                true,
                "capture_finalize_failed",
                &format!("capture helper failed with code {code}"),
                capture_user_message(&code),
            );
            return;
        }
        Ok(_) => {
            fail_capture_task(
                &app,
                Some(&meeting_id),
                recovery_required,
                true,
                "capture_finalize_event_invalid",
                "capture helper did not return a valid finalized event",
                "Both audio files could not be finalized.",
            );
            return;
        }
        Err(error) => {
            fail_capture_task(
                &app,
                Some(&meeting_id),
                recovery_required,
                true,
                "capture_finalize_event_failed",
                &error,
                "Both audio files could not be finalized.",
            );
            return;
        }
    };
    if finalized.0 > 16_000 * 60 * 60 * 24 || finalized.1 > 16_000 * 60 * 60 * 24 {
        fail_capture_task(
            &app,
            Some(&meeting_id),
            recovery_required,
            true,
            "capture_sample_count_invalid",
            "capture helper returned an out-of-range sample count",
            "The finalized audio timing was invalid.",
        );
        return;
    }
    if let Err(error) = helper.finish_cleanly(Instant::now() + Duration::from_secs(5)) {
        fail_capture_task(
            &app,
            Some(&meeting_id),
            recovery_required,
            true,
            "capture_helper_exit_failed",
            &error,
            "The audio helper did not close cleanly.",
        );
        return;
    }
    drop(helper);

    let capture_result = request_worker(
        &state,
        Operation::CaptureFinalize,
        json!({
            "meeting_id": meeting_id,
            "started_at_epoch_seconds": started_at_epoch_seconds,
            "capture_elapsed_samples": capture_elapsed_samples,
        }),
        WORKER_REQUEST_TIMEOUT,
    );
    let capture_digests = match capture_result {
        Ok(result) => match exact_digests(
            &result,
            &["capture-session", "capture-mic", "capture-system"],
        ) {
            Ok(digests) => digests,
            Err(error) => {
                fail_capture_task(
                    &app,
                    Some(&meeting_id),
                    recovery_required,
                    true,
                    "capture_digest_set_invalid",
                    &error,
                    "The finalized capture could not be verified.",
                );
                return;
            }
        },
        Err(error) => {
            fail_capture_task(
                &app,
                Some(&meeting_id),
                recovery_required,
                error.is_supervisor(),
                "capture_worker_finalize_failed",
                &error.to_string(),
                "The finalized capture did not pass its integrity check.",
            );
            return;
        }
    };
    if let Err(error) = commit_captured_meeting(&attempt.meeting_dir, &capture_digests) {
        fail_capture_task(
            &app,
            Some(&meeting_id),
            recovery_required,
            true,
            "capture_meeting_commit_failed",
            &error,
            "The validated capture could not be committed.",
        );
        return;
    }
    {
        let mut model = state.model.lock().expect("application model lock");
        if transition_capture(&mut model, CaptureState::Captured).is_err()
            || transition_capture(&mut model, CaptureState::Transcribing).is_err()
        {
            drop(model);
            fail_capture_task(
                &app,
                Some(&meeting_id),
                false,
                true,
                "capture_processing_transition_failed",
                "application state changed before transcription",
                "The captured meeting could not enter transcription.",
            );
            return;
        }
    }

    let transcript_result = request_worker(
        &state,
        Operation::TranscriptCreate,
        json!({"meeting_id": meeting_id}),
        TRANSCRIPT_REQUEST_TIMEOUT,
    );
    let transcript_digests = match transcript_result {
        Ok(result) => match exact_digests(&result, &["transcript"]) {
            Ok(digests) => digests,
            Err(error) => {
                finish_transcription_failure(
                    &app,
                    &attempt.meeting_dir,
                    &meeting_id,
                    false,
                    "transcript_digest_set_invalid",
                    &error,
                    "The transcript result could not be verified.",
                );
                return;
            }
        },
        Err(error) => {
            finish_transcription_failure(
                &app,
                &attempt.meeting_dir,
                &meeting_id,
                error.is_supervisor(),
                "transcript_worker_failed",
                &error.to_string(),
                "The offline transcript could not be created.",
            );
            return;
        }
    };
    let transcript_digest = &transcript_digests["transcript"];
    let transcript_reference = match verified_artifact(
        &attempt.meeting_dir,
        &format!("transcript/{transcript_digest}.json"),
        transcript_digest,
    ) {
        Ok(reference) => reference,
        Err(error) => {
            finish_transcription_failure(
                &app,
                &attempt.meeting_dir,
                &meeting_id,
                false,
                "transcript_artifact_invalid",
                &error,
                "The transcript file did not match its verified identity.",
            );
            return;
        }
    };
    let (turns, warnings) =
        match load_transcript_projection(&attempt.meeting_dir, &transcript_reference) {
            Ok(projection) => projection,
            Err(error) => {
                finish_transcription_failure(
                    &app,
                    &attempt.meeting_dir,
                    &meeting_id,
                    false,
                    "transcript_projection_invalid",
                    &error,
                    "The transcript could not be displayed safely.",
                );
                return;
            }
        };
    let mut meeting = match load_meeting(&attempt.meeting_dir) {
        Ok(meeting) => meeting,
        Err(error) => {
            finish_transcription_failure(
                &app,
                &attempt.meeting_dir,
                &meeting_id,
                true,
                "transcript_meeting_load_failed",
                &error.to_string(),
                "The transcript could not be attached to its meeting.",
            );
            return;
        }
    };
    meeting.lifecycle = MeetingLifecycle::TranscriptReady;
    meeting.artifacts.current_transcript = Some(transcript_reference);
    if let Err(error) = write_meeting(&attempt.meeting_dir, &meeting) {
        finish_transcription_failure(
            &app,
            &attempt.meeting_dir,
            &meeting_id,
            true,
            "transcript_meeting_commit_failed",
            &error.to_string(),
            "The transcript could not be attached to its meeting.",
        );
        return;
    }
    {
        let mut model = state.model.lock().expect("application model lock");
        if transition_capture(&mut model, CaptureState::TranscriptReady).is_err() {
            model.error = Some("The transcript was saved but its screen could not open.".into());
        } else {
            model.turns = turns;
            model.warnings = warnings;
            model.error = None;
            model.mic_state = None;
            model.system_state = None;
        }
    }
}

fn write_ownership_receipt(meeting_dir: &Path, ownership: &OwnershipReceipt) -> Result<(), String> {
    if !ownership.validate() {
        return Err("capture ownership receipt is invalid".into());
    }
    let encoded = serde_json::to_vec_pretty(ownership).map_err(error_text)?;
    durable_create_new(&meeting_dir.join("ownership.json"), &encoded).map_err(error_text)
}

fn validate_start_request(days: u64, attestation: &StartAttestation) -> Result<(), String> {
    if !matches!(days, 1 | 7 | 30) {
        return Err("Choose one of the available audio-retention periods.".into());
    }
    if !attestation.participants_consented {
        return Err("Confirm that everyone agreed before recording.".into());
    }
    if !attestation.headphones {
        return Err("This alpha requires headphones.".into());
    }
    if !attestation.operator_alone {
        return Err("This alpha requires one person near the microphone.".into());
    }
    Ok(())
}

fn create_attempt(
    storage: &StorageRoot,
    meeting_id: &str,
    attempt_id: &str,
    retention_days: u64,
    attestation: StartAttestation,
) -> Result<AttemptContext, String> {
    let meeting_dir = meeting_dir(storage, meeting_id).map_err(error_text)?;
    let capture_dir = meeting_dir.join("capture");
    create_private_dir(&meeting_dir).map_err(error_text)?;
    create_private_dir(&capture_dir).map_err(error_text)?;
    let result = (|| {
        let created_at_epoch_seconds = now_epoch_seconds();
        let seconds = retention_days
            .checked_mul(24 * 60 * 60)
            .ok_or_else(|| "retention period overflowed".to_string())?;
        let rule = AudioRetentionRule::DeleteAfter { seconds };
        let policy_sha256 = retention_policy_sha256(&rule);
        let application_build_sha256 =
            sha256_file(&std::env::current_exe().map_err(error_text)?).map_err(error_text)?;
        let attempt = CaptureAttemptReceipt {
            schema: "capture-attempt/1".into(),
            meeting_id: meeting_id.into(),
            attempt_id: attempt_id.into(),
            created_at_epoch_seconds,
            application_build_sha256: application_build_sha256.clone(),
            participant_notice_version: PARTICIPANT_NOTICE_VERSION.into(),
            operator_attestation: attestation,
            retention_policy_sha256: policy_sha256.clone(),
        };
        durable_create_new(
            &meeting_dir.join("attempt.json"),
            &serde_json::to_vec_pretty(&attempt).map_err(error_text)?,
        )
        .map_err(error_text)?;
        let meeting = MeetingRecord {
            schema: MeetingSchema::V2,
            meeting_id: meeting_id.into(),
            lifecycle: MeetingLifecycle::RecoveredInterrupted,
            retention: AudioRetention {
                rule,
                policy_sha256,
                next_deletion_at_epoch_seconds: Some(
                    created_at_epoch_seconds
                        .checked_add(seconds)
                        .ok_or_else(|| "retention deadline overflowed".to_string())?,
                ),
                state: AudioState::NeverCreated,
                deletion_receipt: None,
            },
            artifacts: MeetingArtifacts {
                attempt: artifact_ref(&meeting_dir, "attempt.json").map_err(error_text)?,
                ownership: None,
                capture_session: None,
                microphone_audio: None,
                system_audio: None,
                current_transcript: None,
                current_note: None,
            },
            pending_storage_operation: None,
        };
        meeting.validate(meeting_id).map_err(error_text)?;
        durable_create_new(
            &meeting_dir.join("meeting.json"),
            &serde_json::to_vec_pretty(&meeting).map_err(error_text)?,
        )
        .map_err(error_text)?;
        sync_directory(&meeting_dir).map_err(error_text)?;
        Ok(AttemptContext {
            meeting_dir: meeting_dir.clone(),
            application_build_sha256,
        })
    })();
    if result.is_err() {
        let _ = fs::remove_file(meeting_dir.join("meeting.json"));
        let _ = fs::remove_file(meeting_dir.join("attempt.json"));
        let _ = fs::remove_dir(&capture_dir);
        let _ = fs::remove_dir(&meeting_dir);
        if let Some(meetings) = meeting_dir.parent() {
            let _ = sync_directory(meetings);
        }
    }
    result
}

fn inspect_worker(
    state: &ApplicationState,
    runtime: &RuntimeIdentity,
) -> Result<(i32, ProcessIdentity), String> {
    let worker = state.worker.lock().expect("worker process lock");
    let worker = worker
        .as_ref()
        .ok_or_else(|| "worker process is unavailable".to_string())?;
    worker.check_health().map_err(error_text)?;
    let process_group_id = worker.process_group_id();
    let identity = inspect_process(worker.pid())?;
    if identity.executable_sha256 != runtime.worker_executable_sha256 {
        return Err("worker executable identity does not match the runtime manifest".into());
    }
    Ok((process_group_id, identity))
}

fn inspect_process(pid: u32) -> Result<ProcessIdentity, String> {
    match SystemProcessInspector.inspect(pid).map_err(error_text)? {
        ProcessInspection::Identity(identity) => Ok(identity),
        ProcessInspection::Absent => Err("owned process is absent".into()),
        ProcessInspection::Unavailable => Err("owned process identity is unavailable".into()),
    }
}

fn request_worker(
    state: &ApplicationState,
    operation: Operation,
    arguments: Value,
    timeout: Duration,
) -> Result<HashMap<String, String>, WorkerCallError> {
    let command = WorkerCommand::new(operation, arguments);
    let mut guard = state.worker.lock().expect("worker process lock");
    let result = match guard.as_mut() {
        Some(worker) => worker.request_until(&command, Instant::now() + timeout, |_| {
            Err(ProtocolError::InvalidEvent)
        }),
        None => return Err(WorkerCallError::Supervisor("worker is unavailable".into())),
    };
    let result: WorkerResult = match result {
        Ok(result) => result,
        Err(error) => {
            guard.take();
            return Err(WorkerCallError::Supervisor(error.to_string()));
        }
    };
    if !result.ok {
        return Err(WorkerCallError::Rejected);
    }
    Ok(result.artifact_digests)
}

fn exact_digests(
    values: &HashMap<String, String>,
    expected: &[&str],
) -> Result<HashMap<String, String>, String> {
    let actual = values.keys().map(String::as_str).collect::<HashSet<_>>();
    let expected = expected.iter().copied().collect::<HashSet<_>>();
    if actual != expected || values.values().any(|digest| !valid_sha256(digest)) {
        return Err("worker artifact digest set is invalid".into());
    }
    Ok(values.clone())
}

fn valid_sha256(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn commit_captured_meeting(
    meeting_dir: &Path,
    digests: &HashMap<String, String>,
) -> Result<(), String> {
    let capture_session = verified_artifact(
        meeting_dir,
        "capture/session.json",
        &digests["capture-session"],
    )?;
    let microphone_audio =
        verified_artifact(meeting_dir, "capture/mic.wav", &digests["capture-mic"])?;
    let system_audio = verified_artifact(
        meeting_dir,
        "capture/system.wav",
        &digests["capture-system"],
    )?;
    let mut meeting = load_meeting(meeting_dir).map_err(error_text)?;
    if meeting.lifecycle != MeetingLifecycle::Incomplete || meeting.artifacts.ownership.is_none() {
        return Err("meeting is not awaiting a finalized capture".into());
    }
    meeting.lifecycle = MeetingLifecycle::Captured;
    meeting.retention.state = AudioState::Retained;
    meeting.artifacts.capture_session = Some(capture_session);
    meeting.artifacts.microphone_audio = Some(microphone_audio);
    meeting.artifacts.system_audio = Some(system_audio);
    write_meeting(meeting_dir, &meeting).map_err(error_text)
}

fn verified_artifact(
    meeting_dir: &Path,
    relative_path: &str,
    expected_digest: &str,
) -> Result<ArtifactRef, String> {
    let reference = artifact_ref(meeting_dir, relative_path).map_err(error_text)?;
    if reference.sha256 != expected_digest {
        return Err("worker digest does not match the private artifact".into());
    }
    Ok(reference)
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct TranscriptDocument {
    schema: String,
    #[serde(rename = "source")]
    _source: String,
    attribution: String,
    #[serde(rename = "bleed")]
    _bleed: Option<Value>,
    #[serde(rename = "voiceprint")]
    _voiceprint: Option<Value>,
    #[serde(rename = "capture_health")]
    _capture_health: Value,
    turns: Vec<TranscriptInputTurn>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct TranscriptInputTurn {
    start: f64,
    end: f64,
    speaker: Option<String>,
    text: String,
    gated: Option<bool>,
    gate_score: Option<f64>,
    gate_reason: Option<String>,
}

fn load_latest_transcript_projection(
    storage: &StorageRoot,
    eligible_meeting_ids: &[String],
) -> Result<Option<RestoredTranscriptProjection>, String> {
    let mut latest: Option<(u64, String, PathBuf, ArtifactRef, AudioState)> = None;
    for meeting_id in eligible_meeting_ids {
        let directory = meeting_dir(storage, meeting_id).map_err(error_text)?;
        let meeting = load_meeting(&directory).map_err(error_text)?;
        if !matches!(
            meeting.lifecycle,
            MeetingLifecycle::TranscriptReady
                | MeetingLifecycle::SummaryFailed
                | MeetingLifecycle::Ready
        ) {
            continue;
        }
        let transcript = meeting
            .artifacts
            .current_transcript
            .clone()
            .ok_or_else(|| "transcript-bearing meeting has no current transcript".to_string())?;
        let created_at_epoch_seconds = load_attempt_created_at(&directory, &meeting)?;
        let replace = match &latest {
            Some((latest_created, latest_id, ..)) => {
                created_at_epoch_seconds > *latest_created
                    || (created_at_epoch_seconds == *latest_created
                        && meeting.meeting_id > *latest_id)
            }
            None => true,
        };
        if replace {
            latest = Some((
                created_at_epoch_seconds,
                meeting.meeting_id,
                directory,
                transcript,
                meeting.retention.state,
            ));
        }
    }

    let Some((_created, meeting_id, directory, transcript, audio_state)) = latest else {
        return Ok(None);
    };
    let (turns, mut warnings) = load_transcript_projection(&directory, &transcript)?;
    if audio_state == AudioState::Released {
        warnings.push(
            "Meeting audio was deleted under the selected retention period. The transcript remains."
                .into(),
        );
    }
    Ok(Some(RestoredTranscriptProjection {
        meeting_id,
        turns,
        warnings,
    }))
}

fn load_attempt_created_at(meeting_dir: &Path, meeting: &MeetingRecord) -> Result<u64, String> {
    let actual =
        artifact_ref(meeting_dir, &meeting.artifacts.attempt.relative_path).map_err(error_text)?;
    if actual != meeting.artifacts.attempt {
        return Err("capture attempt no longer matches its meeting record".into());
    }
    let bytes = read_private_bytes(
        &meeting_dir.join(&meeting.artifacts.attempt.relative_path),
        ATTEMPT_MAX_BYTES,
    )
    .map_err(error_text)?;
    let attempt: CaptureAttemptReceipt = serde_json::from_slice(&bytes).map_err(error_text)?;
    if attempt.schema != "capture-attempt/1"
        || attempt.meeting_id != meeting.meeting_id
        || Uuid::parse_str(&attempt.attempt_id).is_err()
        || !valid_sha256(&attempt.application_build_sha256)
        || attempt.participant_notice_version != PARTICIPANT_NOTICE_VERSION
        || !attempt.operator_attestation.participants_consented
        || !attempt.operator_attestation.headphones
        || !attempt.operator_attestation.operator_alone
        || attempt.retention_policy_sha256 != meeting.retention.policy_sha256
    {
        return Err("capture attempt metadata is invalid".into());
    }
    Ok(attempt.created_at_epoch_seconds)
}

fn load_transcript_projection(
    meeting_dir: &Path,
    reference: &ArtifactRef,
) -> Result<(Vec<TranscriptTurn>, Vec<String>), String> {
    let actual = artifact_ref(meeting_dir, &reference.relative_path).map_err(error_text)?;
    if &actual != reference {
        return Err("retained transcript no longer matches its meeting record".into());
    }
    let path = meeting_dir.join(&reference.relative_path);
    let bytes = read_private_bytes(&path, TRANSCRIPT_MAX_BYTES).map_err(error_text)?;
    parse_transcript_projection(&bytes)
}

fn parse_transcript_projection(bytes: &[u8]) -> Result<(Vec<TranscriptTurn>, Vec<String>), String> {
    let document: TranscriptDocument = serde_json::from_slice(bytes).map_err(error_text)?;
    if document.schema != "capture-transcript/1"
        || !matches!(document.attribution.as_str(), "channel" | "none")
        || document.turns.len() > 20_000
    {
        return Err("transcript presentation schema is invalid".into());
    }
    let unattributed = document.attribution == "none";
    let mut turns = Vec::with_capacity(document.turns.len());
    let mut gated = 0_u64;
    for (source_turn_index, turn) in document.turns.into_iter().enumerate() {
        if !turn.start.is_finite()
            || !turn.end.is_finite()
            || turn.start < 0.0
            || turn.end < turn.start
            || turn.text.len() > 100_000
            || turn
                .speaker
                .as_ref()
                .is_some_and(|speaker| speaker.len() > 256)
            || (!unattributed
                && turn
                    .speaker
                    .as_deref()
                    .is_some_and(|speaker| !matches!(speaker, "Me" | "Them")))
            || ((turn.gate_score.is_some() || turn.gate_reason.is_some())
                && turn.gated != Some(true))
        {
            return Err("transcript turn is invalid".into());
        }
        if turn.gated == Some(true) {
            gated += 1;
            continue;
        }
        turns.push(TranscriptTurn {
            source_turn_index: source_turn_index as u32,
            speaker: if unattributed { None } else { turn.speaker },
            start: turn.start,
            text: turn.text,
        });
    }
    let mut warnings = Vec::new();
    if document.attribution == "none" {
        warnings.push(
            "Speaker labels are unavailable because the channel split could not be trusted.".into(),
        );
    }
    if gated > 0 {
        warnings.push(format!(
            "The voice check withheld {gated} microphone segment(s); review the retained capture if words appear missing."
        ));
    }
    Ok((turns, warnings))
}

fn finish_transcription_failure(
    app: &AppHandle,
    meeting_dir: &Path,
    _meeting_id: &str,
    block_start: bool,
    code: &str,
    detail: &str,
    user_message: &str,
) {
    let mut must_block_start = block_start;
    let persistence_error = match load_meeting(meeting_dir) {
        Ok(mut meeting) if meeting.lifecycle == MeetingLifecycle::Captured => {
            meeting.lifecycle = MeetingLifecycle::TranscriptionFailed;
            write_meeting(meeting_dir, &meeting)
                .err()
                .map(|error| error.to_string())
        }
        Ok(_) => Some("meeting was not in captured state".into()),
        Err(error) => Some(error.to_string()),
    };
    if let Some(error) = persistence_error {
        must_block_start = true;
        write_diagnostic(
            &app.state::<ApplicationState>(),
            "transcript_failure_state_write_failed",
            &error,
        );
    }
    let state = app.state::<ApplicationState>();
    write_diagnostic(&state, code, detail);
    {
        let mut model = state.model.lock().expect("application model lock");
        let _ = transition_capture(&mut model, CaptureState::TranscriptionFailed);
        if must_block_start && model.reducer.startup() == StartupState::Ready {
            let _ = transition_startup(&mut model, StartupState::DiagnosticWritten);
        }
        model.error = Some(user_message.into());
        model.mic_state = None;
        model.system_state = None;
    }
}

#[allow(clippy::too_many_arguments)]
fn fail_capture_task(
    app: &AppHandle,
    _meeting_id: Option<&str>,
    recovery_required: bool,
    block_start: bool,
    code: &str,
    detail: &str,
    user_message: &str,
) {
    let state = app.state::<ApplicationState>();
    write_diagnostic(&state, code, detail);
    {
        let mut model = state.model.lock().expect("application model lock");
        if matches!(
            model.reducer.capture(),
            CaptureState::Arming | CaptureState::Recording | CaptureState::Stopping
        ) {
            let _ = transition_capture(&mut model, CaptureState::RecoveredInterrupted);
        }
        if (recovery_required || block_start) && model.reducer.startup() == StartupState::Ready {
            let _ = transition_startup(&mut model, StartupState::DiagnosticWritten);
        }
        model.error = Some(user_message.into());
        model.mic_state = None;
        model.system_state = None;
    }
}

fn clear_capture_task(state: &ApplicationState, meeting_id: &str) {
    let mut task = state.capture_task.lock().expect("capture task lock");
    if task
        .as_ref()
        .is_some_and(|task| task.meeting_id == meeting_id)
    {
        task.take();
    }
}

fn write_diagnostic(state: &ApplicationState, code: &str, detail: &str) {
    if let Some(storage) = state.storage.lock().expect("storage context lock").as_ref() {
        let _ = write_private_diagnostic(&storage.diagnostics, code, detail);
    }
}

fn transition_startup(model: &mut AppModel, target: StartupState) -> Result<(), String> {
    model
        .reducer
        .begin(ExclusiveOperation::StartupRecovery)
        .map_err(error_text)?;
    let result = model.reducer.transition_startup(target).map_err(error_text);
    model.reducer.finish(ExclusiveOperation::StartupRecovery);
    result
}

fn transition_capture(model: &mut AppModel, target: CaptureState) -> Result<(), String> {
    model
        .reducer
        .begin(ExclusiveOperation::CaptureTransition)
        .map_err(error_text)?;
    let result = model.reducer.transition_capture(target).map_err(error_text);
    model.reducer.finish(ExclusiveOperation::CaptureTransition);
    result
}

fn read_capture_events(file: File, sender: mpsc::Sender<CaptureStreamItem>) {
    let mut reader = BufReader::new(file);
    loop {
        let mut frame = Vec::new();
        let read = std::io::Read::by_ref(&mut reader)
            .take((CAPTURE_EVENT_MAX_BYTES + 1) as u64)
            .read_until(b'\n', &mut frame);
        match read {
            Ok(0) => {
                let _ = sender.send(CaptureStreamItem::Closed);
                return;
            }
            Ok(_) if frame.len() <= CAPTURE_EVENT_MAX_BYTES && frame.ends_with(b"\n") => {
                frame.pop();
                match parse_capture_event(&frame) {
                    Ok(event) => {
                        if sender.send(CaptureStreamItem::Event(event)).is_err() {
                            return;
                        }
                    }
                    Err(_) => {
                        let _ = sender.send(CaptureStreamItem::ProtocolFailure);
                        return;
                    }
                }
            }
            Ok(_) | Err(_) => {
                let _ = sender.send(CaptureStreamItem::ProtocolFailure);
                return;
            }
        }
    }
}

fn parse_capture_event(frame: &[u8]) -> Result<CaptureEvent, String> {
    let value: Value = serde_json::from_slice(frame).map_err(error_text)?;
    let object = value
        .as_object()
        .ok_or_else(|| "capture event is not an object".to_string())?;
    if object.get("schema").and_then(Value::as_str) != Some("capture-event/1") {
        return Err("capture event schema is invalid".into());
    }
    match object.get("event").and_then(Value::as_str) {
        Some("paused") if exact_object_keys(object, &["schema", "event"]) => {
            Ok(CaptureEvent::Paused)
        }
        Some("recording") if exact_object_keys(object, &["schema", "event", "format"]) => {
            let format = object["format"]
                .as_object()
                .ok_or_else(|| "capture format is invalid".to_string())?;
            if !exact_object_keys(format, &["encoding", "sample_rate", "channels"])
                || format.get("encoding").and_then(Value::as_str) != Some("pcm_s16le")
                || format.get("sample_rate").and_then(Value::as_u64) != Some(16_000)
                || format.get("channels").and_then(Value::as_u64) != Some(1)
            {
                return Err("capture format is invalid".into());
            }
            Ok(CaptureEvent::Recording)
        }
        Some("finalized") if exact_object_keys(object, &["schema", "event", "legs"]) => {
            let legs = object["legs"]
                .as_object()
                .ok_or_else(|| "capture legs are invalid".to_string())?;
            if !exact_object_keys(legs, &["mic", "system"]) {
                return Err("capture legs are invalid".into());
            }
            let samples = |name: &str| -> Result<u64, String> {
                let leg = legs[name]
                    .as_object()
                    .ok_or_else(|| "capture leg is invalid".to_string())?;
                if !exact_object_keys(leg, &["samples"]) {
                    return Err("capture leg is invalid".into());
                }
                leg["samples"]
                    .as_u64()
                    .ok_or_else(|| "capture sample count is invalid".to_string())
            };
            Ok(CaptureEvent::Finalized {
                mic_samples: samples("mic")?,
                system_samples: samples("system")?,
            })
        }
        Some("failed") => {
            let valid_keys = exact_object_keys(object, &["schema", "event", "code", "detail"])
                || exact_object_keys(object, &["schema", "event", "code", "detail", "leg"]);
            let code = object.get("code").and_then(Value::as_str);
            let detail = object.get("detail").and_then(Value::as_str);
            let leg = object.get("leg").and_then(Value::as_str);
            if !valid_keys
                || code.is_none_or(|code| code.is_empty() || code.len() > 128)
                || detail.is_none_or(|detail| detail.len() > 4_096)
                || leg.is_some_and(|leg| !matches!(leg, "mic" | "system"))
            {
                return Err("capture failure event is invalid".into());
            }
            Ok(CaptureEvent::Failed {
                code: code.expect("validated code").into(),
            })
        }
        Some("interrupted") if exact_object_keys(object, &["schema", "event"]) => {
            Ok(CaptureEvent::Interrupted)
        }
        _ => Err("capture event is outside the closed schema".into()),
    }
}

fn exact_object_keys(object: &serde_json::Map<String, Value>, expected: &[&str]) -> bool {
    object.len() == expected.len() && expected.iter().all(|key| object.contains_key(*key))
}

fn cloexec_pipe() -> io::Result<(File, File)> {
    let mut descriptors = [-1; 2];
    if unsafe { libc::pipe(descriptors.as_mut_ptr()) } != 0 {
        return Err(io::Error::last_os_error());
    }
    let result = set_close_on_exec(descriptors[0], true)
        .and_then(|_| set_close_on_exec(descriptors[1], true));
    if let Err(error) = result {
        unsafe {
            libc::close(descriptors[0]);
            libc::close(descriptors[1]);
        }
        return Err(error);
    }
    Ok(unsafe {
        (
            File::from_raw_fd(descriptors[0]),
            File::from_raw_fd(descriptors[1]),
        )
    })
}

fn set_close_on_exec(descriptor: RawFd, enabled: bool) -> io::Result<()> {
    let flags = unsafe { libc::fcntl(descriptor, libc::F_GETFD) };
    if flags == -1 {
        return Err(io::Error::last_os_error());
    }
    let updated = if enabled {
        flags | libc::FD_CLOEXEC
    } else {
        flags & !libc::FD_CLOEXEC
    };
    if unsafe { libc::fcntl(descriptor, libc::F_SETFD, updated) } == -1 {
        return Err(io::Error::last_os_error());
    }
    Ok(())
}

fn signal_process_group(process_group_id: i32, signal: i32) -> io::Result<()> {
    if unsafe { libc::kill(-process_group_id, signal) } == 0 {
        return Ok(());
    }
    let error = io::Error::last_os_error();
    if error.raw_os_error() == Some(libc::ESRCH) {
        Ok(())
    } else {
        Err(error)
    }
}

fn elapsed_samples(duration: Duration) -> Result<u64, String> {
    let samples = duration.as_secs_f64() * 16_000.0;
    let maximum = (16_000 * 60 * 60 * 24) as f64;
    if !samples.is_finite() || samples < 1.0 || samples > maximum {
        return Err("capture elapsed time is outside the supported range".into());
    }
    Ok(samples.round() as u64)
}

fn capture_user_message(code: &str) -> &'static str {
    match code {
        "microphone_permission_denied" => {
            "Microphone access was not granted. Nothing was marked complete."
        }
        "system_tap_setup_failed" | "system_tap_unavailable" | "system_tap_start_failed" => {
            "System-audio access was unavailable. Nothing was marked complete."
        }
        _ => "An audio channel failed. Nothing was marked complete.",
    }
}

fn now_epoch_seconds() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs()
}

fn sha256_file(path: &Path) -> io::Result<String> {
    let mut file = File::open(path)?;
    let mut digest = Sha256::new();
    let mut buffer = [0_u8; 64 * 1024];
    loop {
        let read = file.read(&mut buffer)?;
        if read == 0 {
            break;
        }
        digest.update(&buffer[..read]);
    }
    Ok(format!("{:x}", digest.finalize()))
}

fn error_text(error: impl std::fmt::Display) -> String {
    error.to_string()
}

fn io_error(error: io::Error) -> Box<dyn std::error::Error> {
    Box::new(error)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Barrier;
    use tempfile::TempDir;

    fn valid_attestation() -> StartAttestation {
        StartAttestation {
            participants_consented: true,
            headphones: true,
            operator_alone: true,
        }
    }

    fn test_storage() -> (TempDir, StorageRoot) {
        let temporary = TempDir::new().unwrap();
        let repository = temporary.path().join("repository");
        fs::create_dir(&repository).unwrap();
        let storage = StorageRoot::create(&temporary.path().join("app-data"), &repository).unwrap();
        (temporary, storage)
    }

    fn storage_tree_bytes(path: &Path) -> Vec<(String, Vec<u8>)> {
        fn visit(root: &Path, path: &Path, entries: &mut Vec<(String, Vec<u8>)>) {
            let mut children = fs::read_dir(path)
                .unwrap()
                .map(|entry| entry.unwrap().path())
                .collect::<Vec<_>>();
            children.sort();
            for child in children {
                if child.is_dir() {
                    visit(root, &child, entries);
                } else {
                    entries.push((
                        child.strip_prefix(root).unwrap().display().to_string(),
                        fs::read(&child).unwrap(),
                    ));
                }
            }
        }
        let mut entries = Vec::new();
        visit(path, path, &mut entries);
        entries
    }

    #[test]
    fn active_meeting_lease_is_exclusive_and_released_on_drop() {
        let state = ApplicationState::default();
        let (_temporary, storage) = test_storage();
        ensure_app_data_writer_lock(&state, &storage).unwrap();
        let coordination = state.meeting_storage_coordination().unwrap();
        let lease = coordination.acquire("meeting-a").unwrap();
        assert!(
            state
                .meeting_storage_coordination()
                .unwrap()
                .acquire("meeting-a")
                .is_err()
        );
        let active = coordination
            .lock_sequence()
            .unwrap()
            .active_meeting_ids()
            .unwrap();
        assert_eq!(active.len(), 1);
        assert!(active.contains("meeting-a"));

        drop(lease);

        assert!(
            coordination
                .lock_sequence()
                .unwrap()
                .active_meeting_ids()
                .unwrap()
                .is_empty()
        );
        assert!(
            state
                .meeting_storage_coordination()
                .unwrap()
                .acquire("meeting-a")
                .is_ok()
        );
    }

    #[test]
    fn preview_sequence_barrier_blocks_reader_entry_without_sleeping() {
        let coordination = Arc::new(MeetingStorageCoordination::default());
        let held = coordination.lock_sequence().unwrap();
        let barrier = Arc::new(Barrier::new(2));
        let (entered_sender, entered_receiver) = mpsc::channel();
        let task_coordination = Arc::clone(&coordination);
        let task_barrier = Arc::clone(&barrier);
        let task = std::thread::spawn(move || {
            task_barrier.wait();
            with_meeting_storage_sequence(&task_coordination, |_| {
                entered_sender.send(()).unwrap();
            })
            .unwrap();
        });

        barrier.wait();
        assert!(entered_receiver.try_recv().is_err());
        drop(held);
        entered_receiver.recv().unwrap();
        task.join().unwrap();
    }

    #[test]
    fn poisoned_preview_sequence_fails_closed_before_reader_operation() {
        let coordination = Arc::new(MeetingStorageCoordination::default());
        let poisoned = Arc::clone(&coordination);
        assert!(
            std::thread::spawn(move || {
                let _sequence = poisoned.lock_sequence().unwrap();
                panic!("synthetic sequence poison");
            })
            .join()
            .is_err()
        );
        let called = std::cell::Cell::new(false);

        let response = with_meeting_storage_sequence(&coordination, |_| called.set(true));

        assert!(response.is_err());
        assert!(!called.get());
    }

    #[test]
    fn preview_commands_share_sequence_before_reader_mutex_order() {
        let coordination = Arc::new(MeetingStorageCoordination::default());
        let reader = Arc::new(Mutex::new(()));
        let (first_entered_sender, first_entered_receiver) = mpsc::channel();
        let (release_sender, release_receiver) = mpsc::channel();
        let (second_done_sender, second_done_receiver) = mpsc::channel();

        let first_coordination = Arc::clone(&coordination);
        let first_reader = Arc::clone(&reader);
        let first = std::thread::spawn(move || {
            with_meeting_storage_sequence(&first_coordination, |_| {
                let _reader = first_reader.lock().unwrap();
                first_entered_sender.send(()).unwrap();
                release_receiver.recv().unwrap();
            })
            .unwrap();
        });
        first_entered_receiver.recv().unwrap();

        let second_coordination = Arc::clone(&coordination);
        let second_reader = Arc::clone(&reader);
        let second = std::thread::spawn(move || {
            with_meeting_storage_sequence(&second_coordination, |_| {
                let _reader = second_reader.lock().unwrap();
                second_done_sender.send(()).unwrap();
            })
            .unwrap();
        });
        assert!(second_done_receiver.try_recv().is_err());
        release_sender.send(()).unwrap();
        second_done_receiver.recv().unwrap();
        first.join().unwrap();
        second.join().unwrap();
    }

    #[test]
    fn preview_audio_deletion_gate_refuses_before_consuming_handle() {
        let mut handle = Some("single-use-handle");
        for startup in [
            StartupState::ShellRendered,
            StartupState::Checking,
            StartupState::RuntimeMissing,
            StartupState::ServiceTimeout,
            StartupState::DiagnosticWritten,
            StartupState::Retrying,
            StartupState::ReinstallRequired,
        ] {
            let refused =
                with_preview_audio_deletion_gate(startup, CaptureState::Idle, || handle.take());
            assert_eq!(refused.unwrap_err().state, "not-ready");
            assert_eq!(handle, Some("single-use-handle"));
        }
        for capture in [
            CaptureState::Arming,
            CaptureState::Recording,
            CaptureState::Stopping,
            CaptureState::Captured,
            CaptureState::Transcribing,
            CaptureState::Summarizing,
            CaptureState::Ready,
            CaptureState::TranscriptionFailed,
            CaptureState::SummaryFailed,
            CaptureState::RecoveredInterrupted,
        ] {
            let refused =
                with_preview_audio_deletion_gate(StartupState::Ready, capture, || handle.take());
            assert_eq!(refused.unwrap_err().state, "capture-active");
            assert_eq!(handle, Some("single-use-handle"));
        }

        let authorized =
            with_preview_audio_deletion_gate(StartupState::Ready, CaptureState::Idle, || {
                handle.take()
            })
            .unwrap();
        assert_eq!(authorized, Some("single-use-handle"));
        assert_eq!(handle, None);

        let mut transcript_ready_handle = Some("transcript-ready-handle");
        assert_eq!(
            with_preview_audio_deletion_gate(
                StartupState::Ready,
                CaptureState::TranscriptReady,
                || transcript_ready_handle.take(),
            )
            .unwrap(),
            Some("transcript-ready-handle")
        );
    }

    #[test]
    fn preview_reader_commands_preserve_app_snapshot_and_storage_bytes() {
        let state = ApplicationState::default();
        let before_snapshot = serde_json::to_value(state.model.lock().unwrap().snapshot()).unwrap();
        let (_temporary, storage) = test_storage();
        let meeting_id = Uuid::new_v4().to_string();
        write_transcript_fixture(
            &storage,
            &meeting_id,
            10,
            AudioState::Retained,
            "stable synthetic words",
        );
        let before_storage = storage_tree_bytes(storage.path());
        let coordination = MeetingStorageCoordination::default();

        with_meeting_storage_sequence(&coordination, |active| {
            let mut reader = library_reader::LibraryReader::rebuild(storage.clone(), active)
                .expect("synthetic Preview reader");
            let snapshot = reader.snapshot(active);
            let note = reader.open_note(&snapshot.rows[0].handle, active);
            let transcript_handle = note.transcript_handle.unwrap();
            let opened = reader
                .open_transcript_bound(
                    &transcript_handle,
                    active,
                    load_bound_preview_transcript_projection,
                )
                .unwrap()
                .unwrap();
            assert_eq!(opened.0[0].text, "stable synthetic words");
            assert_eq!(reader.search("", active).state, "invalid");
        })
        .unwrap();

        assert_eq!(storage_tree_bytes(storage.path()), before_storage);
        assert_eq!(
            serde_json::to_value(state.model.lock().unwrap().snapshot()).unwrap(),
            before_snapshot
        );
    }

    #[test]
    fn preview_snapshot_excludes_active_meeting_and_keeps_prior_stable_row() {
        let (_temporary, storage) = test_storage();
        let stable_id = Uuid::new_v4().to_string();
        let active_id = Uuid::new_v4().to_string();
        write_transcript_fixture(
            &storage,
            &stable_id,
            10,
            AudioState::Retained,
            "prior stable words",
        );
        let active_directory = write_transcript_fixture(
            &storage,
            &active_id,
            20,
            AudioState::Retained,
            "partial active words",
        )
        .parent()
        .unwrap()
        .parent()
        .unwrap()
        .to_path_buf();
        fs::write(
            active_directory.join("attempt.json"),
            b"writer is replacing this receipt",
        )
        .unwrap();
        let coordination = MeetingStorageCoordination::default();
        let _active = coordination.acquire(&active_id).unwrap();

        with_meeting_storage_sequence(&coordination, |active| {
            let mut reader = library_reader::LibraryReader::rebuild(storage.clone(), active)
                .expect("stable meetings remain readable");
            let snapshot = reader.snapshot(active);
            assert_eq!(snapshot.rows.len(), 1);
            assert_eq!(snapshot.rows[0].meeting_id, stable_id);
        })
        .unwrap();
    }

    #[test]
    fn app_data_writer_lock_is_exclusive_and_released_with_its_file() {
        let (_temporary, storage) = test_storage();
        let held = acquire_app_data_writer_lock(&storage).unwrap();

        assert!(acquire_app_data_writer_lock(&storage).is_err());

        drop(held);
        assert!(acquire_app_data_writer_lock(&storage).is_ok());
    }

    fn write_transcript_fixture(
        storage: &StorageRoot,
        meeting_id: &str,
        created_at_epoch_seconds: u64,
        audio_state: AudioState,
        text: &str,
    ) -> PathBuf {
        let directory = meeting_dir(storage, meeting_id).unwrap();
        create_private_dir(&directory).unwrap();
        create_private_dir(&directory.join("capture")).unwrap();
        create_private_dir(&directory.join("transcript")).unwrap();
        create_private_dir(&directory.join("deletion")).unwrap();
        durable_create_new(&directory.join("ownership.json"), b"{}\n").unwrap();
        durable_create_new(&directory.join("capture/session.json"), b"{}\n").unwrap();
        durable_create_new(&directory.join("capture/mic.wav"), b"synthetic microphone").unwrap();
        durable_create_new(&directory.join("capture/system.wav"), b"synthetic system").unwrap();
        let microphone_audio = artifact_ref(&directory, "capture/mic.wav").unwrap();
        let system_audio = artifact_ref(&directory, "capture/system.wav").unwrap();
        let deletion_receipt = if audio_state == AudioState::Released {
            fs::remove_file(directory.join("capture/mic.wav")).unwrap();
            fs::remove_file(directory.join("capture/system.wav")).unwrap();
            durable_create_new(&directory.join("deletion/audio-deletion.json"), b"{}\n").unwrap();
            Some(artifact_ref(&directory, "deletion/audio-deletion.json").unwrap())
        } else {
            None
        };
        let rule = AudioRetentionRule::DeleteAfter { seconds: 86_400 };
        let policy_sha256 = retention_policy_sha256(&rule);
        let attempt = CaptureAttemptReceipt {
            schema: "capture-attempt/1".into(),
            meeting_id: meeting_id.into(),
            attempt_id: Uuid::new_v4().to_string(),
            created_at_epoch_seconds,
            application_build_sha256: "a".repeat(64),
            participant_notice_version: PARTICIPANT_NOTICE_VERSION.into(),
            operator_attestation: valid_attestation(),
            retention_policy_sha256: policy_sha256.clone(),
        };
        durable_create_new(
            &directory.join("attempt.json"),
            &serde_json::to_vec_pretty(&attempt).unwrap(),
        )
        .unwrap();
        let transcript_bytes = serde_json::to_vec_pretty(&json!({
            "schema": "capture-transcript/1",
            "source": "synthetic-restart-fixture",
            "attribution": "channel",
            "bleed": null,
            "voiceprint": null,
            "capture_health": {},
            "turns": [{
                "start": 0.0,
                "end": 1.0,
                "speaker": "Me",
                "text": text,
            }],
        }))
        .unwrap();
        let transcript_digest = format!("{:x}", Sha256::digest(&transcript_bytes));
        let transcript_relative = format!("transcript/{transcript_digest}.json");
        let transcript_path = directory.join(&transcript_relative);
        durable_create_new(&transcript_path, &transcript_bytes).unwrap();
        let meeting = MeetingRecord {
            schema: MeetingSchema::V2,
            meeting_id: meeting_id.into(),
            lifecycle: MeetingLifecycle::TranscriptReady,
            retention: AudioRetention {
                rule,
                policy_sha256,
                next_deletion_at_epoch_seconds: Some(created_at_epoch_seconds + 86_400),
                state: audio_state,
                deletion_receipt,
            },
            artifacts: MeetingArtifacts {
                attempt: artifact_ref(&directory, "attempt.json").unwrap(),
                ownership: Some(artifact_ref(&directory, "ownership.json").unwrap()),
                capture_session: Some(artifact_ref(&directory, "capture/session.json").unwrap()),
                microphone_audio: Some(microphone_audio),
                system_audio: Some(system_audio),
                current_transcript: Some(artifact_ref(&directory, &transcript_relative).unwrap()),
                current_note: None,
            },
            pending_storage_operation: None,
        };
        write_meeting(&directory, &meeting).unwrap();
        transcript_path
    }

    #[test]
    fn start_requires_every_assertion_and_a_closed_retention_choice() {
        assert!(validate_start_request(1, &valid_attestation()).is_ok());
        assert!(validate_start_request(7, &valid_attestation()).is_ok());
        assert!(validate_start_request(30, &valid_attestation()).is_ok());
        assert!(validate_start_request(2, &valid_attestation()).is_err());
        for field in 0..3 {
            let mut attestation = valid_attestation();
            match field {
                0 => attestation.participants_consented = false,
                1 => attestation.headphones = false,
                _ => attestation.operator_alone = false,
            }
            assert!(validate_start_request(7, &attestation).is_err());
        }
    }

    #[test]
    fn capture_events_are_closed_and_format_bound() {
        assert_eq!(
            parse_capture_event(br#"{"schema":"capture-event/1","event":"paused"}"#).unwrap(),
            CaptureEvent::Paused
        );
        assert_eq!(
            parse_capture_event(
                br#"{"schema":"capture-event/1","event":"recording","format":{"encoding":"pcm_s16le","sample_rate":16000,"channels":1}}"#
            )
            .unwrap(),
            CaptureEvent::Recording
        );
        assert!(
            parse_capture_event(br#"{"schema":"capture-event/1","event":"paused","extra":true}"#)
                .is_err()
        );
        assert!(
            parse_capture_event(
                br#"{"schema":"capture-event/1","event":"recording","format":{"encoding":"pcm_f32le","sample_rate":16000,"channels":1}}"#
            )
            .is_err()
        );
    }

    #[test]
    fn worker_digest_sets_are_exact_and_lowercase() {
        let valid = HashMap::from([("transcript".into(), "a".repeat(64))]);
        assert!(exact_digests(&valid, &["transcript"]).is_ok());
        let extra = HashMap::from([
            ("transcript".into(), "a".repeat(64)),
            ("note".into(), "b".repeat(64)),
        ]);
        assert!(exact_digests(&extra, &["transcript"]).is_err());
        let uppercase = HashMap::from([("transcript".into(), "A".repeat(64))]);
        assert!(exact_digests(&uppercase, &["transcript"]).is_err());
    }

    #[test]
    fn transcript_projection_filters_gated_words_without_claiming_a_note() {
        let document = br#"{
          "schema":"capture-transcript/1",
          "source":"fixture",
          "attribution":"channel",
          "bleed":null,
          "voiceprint":null,
          "capture_health":{},
          "turns":[
            {"start":0.0,"end":1.0,"speaker":"Me","text":"visible"},
            {"start":1.0,"end":2.0,"speaker":"Me","text":"withheld","gated":true,"gate_score":0.1,"gate_reason":"fixture"}
          ]
        }"#;
        let (turns, warnings) = parse_transcript_projection(document).unwrap();
        assert_eq!(turns.len(), 1);
        assert_eq!(turns[0].text, "visible");
        assert_eq!(warnings.len(), 1);
    }

    #[test]
    fn fresh_process_projects_latest_valid_transcript() {
        let (_temporary, storage) = test_storage();
        let older = Uuid::new_v4().to_string();
        let newer = Uuid::new_v4().to_string();
        write_transcript_fixture(&storage, &older, 10, AudioState::Retained, "older");
        write_transcript_fixture(&storage, &newer, 20, AudioState::Retained, "newer");

        let projection = load_latest_transcript_projection(&storage, &[newer.clone(), older])
            .unwrap()
            .unwrap();
        assert_eq!(projection.meeting_id, newer);
        assert_eq!(projection.turns[0].text, "newer");
    }

    #[test]
    fn restored_projection_becomes_the_ready_startup_snapshot() {
        let mut model = AppModel::default();
        transition_startup(&mut model, StartupState::Checking).unwrap();
        apply_restored_transcript_projection(
            &mut model,
            RestoredTranscriptProjection {
                meeting_id: "meeting-fixture".into(),
                turns: vec![TranscriptTurn {
                    source_turn_index: 0,
                    speaker: Some("Me".into()),
                    start: 0.0,
                    text: "visible".into(),
                }],
                warnings: Vec::new(),
            },
        )
        .unwrap();
        transition_startup(&mut model, StartupState::Ready).unwrap();

        let snapshot = model.snapshot();
        assert_eq!(snapshot.startup, StartupState::Ready);
        assert_eq!(snapshot.capture, CaptureState::TranscriptReady);
        assert_eq!(snapshot.meeting_id.as_deref(), Some("meeting-fixture"));
        assert_eq!(snapshot.turns[0].text, "visible");
    }

    #[test]
    fn startup_retry_preserves_the_specific_attempt_failure() {
        let mut model = AppModel::default();
        transition_startup(&mut model, StartupState::Checking).unwrap();
        transition_startup(&mut model, StartupState::Ready).unwrap();
        transition_capture(&mut model, CaptureState::Arming).unwrap();
        transition_capture(&mut model, CaptureState::RecoveredInterrupted).unwrap();
        transition_startup(&mut model, StartupState::DiagnosticWritten).unwrap();
        model.error =
            Some("Microphone access was not granted. Nothing was marked complete.".into());

        prepare_startup_retry(&mut model).unwrap();

        assert_eq!(model.reducer.startup(), StartupState::Retrying);
        assert_eq!(
            model.error.as_deref(),
            Some("Microphone access was not granted. Nothing was marked complete.")
        );
    }

    #[test]
    fn startup_retry_clears_an_idle_installation_failure() {
        let mut model = AppModel::default();
        transition_startup(&mut model, StartupState::Checking).unwrap();
        transition_startup(&mut model, StartupState::DiagnosticWritten).unwrap();
        model.error = Some("stale installation failure".into());

        prepare_startup_retry(&mut model).unwrap();

        assert_eq!(model.reducer.startup(), StartupState::Retrying);
        assert!(model.error.is_none());
    }

    #[test]
    fn equal_attempt_times_choose_the_greatest_meeting_id() {
        let (_temporary, storage) = test_storage();
        let mut ids = [Uuid::new_v4().to_string(), Uuid::new_v4().to_string()];
        ids.sort();
        write_transcript_fixture(&storage, &ids[0], 10, AudioState::Retained, "lower");
        write_transcript_fixture(&storage, &ids[1], 10, AudioState::Retained, "higher");

        let projection =
            load_latest_transcript_projection(&storage, &[ids[1].clone(), ids[0].clone()])
                .unwrap()
                .unwrap();
        assert_eq!(projection.meeting_id, ids[1]);
        assert_eq!(projection.turns[0].text, "higher");
    }

    #[test]
    fn fresh_process_keeps_transcript_visible_after_audio_release() {
        let (_temporary, storage) = test_storage();
        let meeting_id = Uuid::new_v4().to_string();
        write_transcript_fixture(
            &storage,
            &meeting_id,
            10,
            AudioState::Released,
            "still here",
        );

        let projection =
            load_latest_transcript_projection(&storage, std::slice::from_ref(&meeting_id))
                .unwrap()
                .unwrap();
        assert_eq!(projection.turns[0].text, "still here");
        assert!(projection.warnings.iter().any(|warning| {
            warning.contains("audio was deleted") && warning.contains("transcript remains")
        }));
    }

    #[test]
    fn fresh_process_with_no_transcript_remains_idle() {
        let (_temporary, storage) = test_storage();
        assert!(
            load_latest_transcript_projection(&storage, &[])
                .unwrap()
                .is_none()
        );
    }

    #[test]
    fn changed_transcript_is_not_projected() {
        let (_temporary, storage) = test_storage();
        let meeting_id = Uuid::new_v4().to_string();
        let transcript_path =
            write_transcript_fixture(&storage, &meeting_id, 10, AudioState::Retained, "before");
        fs::write(transcript_path, b"changed").unwrap();

        assert!(load_latest_transcript_projection(&storage, &[meeting_id]).is_err());
    }

    #[test]
    fn preview_bound_transcript_rejects_pointer_replacement_after_reader_validation() {
        let (_temporary, storage) = test_storage();
        let meeting_id = Uuid::new_v4().to_string();
        write_transcript_fixture(
            &storage,
            &meeting_id,
            10,
            AudioState::Retained,
            "stable synthetic words",
        );
        let directory = meeting_dir(&storage, &meeting_id).unwrap();
        let mut meeting = load_meeting(&directory).unwrap();
        let expected = meeting.artifacts.current_transcript.clone().unwrap();
        let (turns, _) =
            load_bound_preview_transcript_projection(&storage, &meeting_id, &expected).unwrap();
        assert_eq!(turns[0].text, "stable synthetic words");

        let replacement = serde_json::to_vec_pretty(&json!({
            "schema": "capture-transcript/1",
            "source": "synthetic-replacement-fixture",
            "attribution": "channel",
            "bleed": null,
            "voiceprint": null,
            "capture_health": {},
            "turns": [{
                "start": 0.0,
                "end": 1.0,
                "speaker": "Me",
                "text": "replacement synthetic words",
            }],
        }))
        .unwrap();
        let replacement_digest = format!("{:x}", Sha256::digest(&replacement));
        let replacement_relative = format!("transcript/{replacement_digest}.json");
        durable_create_new(&directory.join(&replacement_relative), &replacement).unwrap();
        meeting.artifacts.current_transcript =
            Some(artifact_ref(&directory, &replacement_relative).unwrap());
        write_meeting(&directory, &meeting).unwrap();

        assert!(
            load_bound_preview_transcript_projection(&storage, &meeting_id, &expected).is_err()
        );
    }

    #[test]
    fn preview_bound_transcript_hashes_the_exact_bytes_it_parses() {
        let (_temporary, storage) = test_storage();
        let meeting_id = Uuid::new_v4().to_string();
        let transcript_path = write_transcript_fixture(
            &storage,
            &meeting_id,
            10,
            AudioState::Retained,
            "stable synthetic words",
        );
        let directory = meeting_dir(&storage, &meeting_id).unwrap();
        let expected = load_meeting(&directory)
            .unwrap()
            .artifacts
            .current_transcript
            .unwrap();
        fs::write(transcript_path, b"changed synthetic bytes").unwrap();

        assert!(
            load_bound_preview_transcript_projection(&storage, &meeting_id, &expected).is_err()
        );
    }
}

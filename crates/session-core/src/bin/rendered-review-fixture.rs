//! Seeds one private, deterministic app-data tree for rendered review.
//!
//! The command accepts exactly one absolute path. The final component must be
//! `com.ninochavez.local-meeting-notes.fixture`; it never accepts a live app
//! data root and it has no cleanup mode.

use std::env;
use std::fs;
use std::io::{self, Read, Write};
use std::os::unix::fs::{OpenOptionsExt, PermissionsExt};
use std::path::{Path, PathBuf};

use local_meeting_notes_session_core::meeting::{
    artifact_ref, load_meeting, retention_policy_sha256, verify_record_artifacts, write_meeting,
    AudioRetention, AudioRetentionRule, AudioState, MeetingArtifacts, MeetingLifecycle,
    MeetingRecord, MeetingSchema,
};
use local_meeting_notes_session_core::meeting_coordination::MeetingStorageCoordination;
use local_meeting_notes_session_core::model_store::{
    activate_model, install_receipt_bytes, verify_model_directory, ModelCatalog, ModelStoreError,
    TranscriptModelFileRole,
};
use local_meeting_notes_session_core::retention::{AppDataWriterLock, AppDataWriterLockError};
use local_meeting_notes_session_core::runtime::{RuntimeError, RuntimeManifest};
use local_meeting_notes_session_core::storage::{
    create_private_dir, durable_create_new, sync_directory, StorageRoot,
};
use local_meeting_notes_session_core::transcript_retry::{
    TranscriptRetryAuthority, TranscriptRetrySourceBinding,
};
use serde_json::json;
use sha2::{Digest, Sha256};
use uuid::Uuid;

const BUNDLE_NAME: &str = "com.ninochavez.local-meeting-notes.fixture";
const MEETING_ID: &str = "11111111-1111-4111-8111-111111111111";
const OPERATION_ID: &str = "22222222-2222-4222-8222-222222222222";
const CREATED_AT: u64 = 1_700_000_042;
const AUDIO_SAMPLE_RATE: u32 = 8_000;
const AUDIO_FRAMES: usize = AUDIO_SAMPLE_RATE as usize * 8;

#[derive(Debug, thiserror::Error)]
enum FixtureError {
    #[error("fixture root must be an absolute path")]
    RelativeRoot,
    #[error("fixture root final component must be {BUNDLE_NAME}")]
    WrongRootName,
    #[error("fixture root may not be a symlink")]
    Symlink,
    #[error("fixture root parent is too broad")]
    BroadRoot,
    #[error("fixture root already contains data")]
    ExistingData,
    #[error("fixture root may not be inside the source repository")]
    InsideRepository,
    #[error("fixture root is not a private directory")]
    UnsafeDirectory,
    #[error(transparent)]
    Io(#[from] io::Error),
    #[error(transparent)]
    Json(#[from] serde_json::Error),
    #[error(transparent)]
    Meeting(#[from] local_meeting_notes_session_core::meeting::MeetingError),
    #[error(transparent)]
    Storage(#[from] local_meeting_notes_session_core::storage::StorageError),
    #[error(transparent)]
    Retry(#[from] local_meeting_notes_session_core::transcript_retry::TranscriptRetryError),
    #[error("fixture root marker is missing or not the exact synthetic marker")]
    InvalidMarker,
    #[error("model install path is unsafe: {0}")]
    UnsafeInstallPath(String),
    #[error("bundle runtime manifest has no verified model catalog")]
    MissingModelCatalog,
    #[error("selected model is not a transcript model in the verified catalog")]
    UnknownModel,
    #[error("a model or active-model pointer already exists")]
    ExistingModel,
    #[error("source model changed during the bounded copy")]
    SourceChanged,
    #[error(transparent)]
    Runtime(#[from] RuntimeError),
    #[error(transparent)]
    ModelStore(#[from] ModelStoreError),
    #[error(transparent)]
    WriterLock(#[from] AppDataWriterLockError),
}

fn main() {
    let mut args = env::args().skip(1);
    let Some(first) = args.next() else {
        eprintln!("usage: rendered-review-fixture /absolute/path/{BUNDLE_NAME}");
        std::process::exit(2);
    };
    let result = if first == "install-model" {
        let root = args.next();
        let bundle = args.next();
        let source = args.next();
        let model_id = args.next();
        if args.next().is_some()
            || root.is_none()
            || bundle.is_none()
            || source.is_none()
            || model_id.is_none()
        {
            eprintln!("usage: rendered-review-fixture install-model ROOT BUNDLE_RESOURCES SOURCE_MODEL_DIR MODEL_ID");
            std::process::exit(2);
        }
        install_model(
            Path::new(root.as_deref().expect("checked root")),
            Path::new(bundle.as_deref().expect("checked bundle")),
            Path::new(source.as_deref().expect("checked source")),
            model_id.as_deref().expect("checked model id"),
            repository_root(),
        )
    } else if args.next().is_some() {
        eprintln!("usage: rendered-review-fixture /absolute/path/{BUNDLE_NAME}");
        std::process::exit(2);
    } else {
        seed(Path::new(&first), repository_root())
    };
    if let Err(error) = result {
        eprintln!("rendered-review-fixture: {error}");
        std::process::exit(1);
    }
    if first == "install-model" {
        println!("installed verified synthetic model");
    } else {
        println!("seeded synthetic fixture at {first}");
    }
}

fn repository_root() -> PathBuf {
    // CARGO_MANIFEST_DIR is crates/session-core. Its grandparent is the
    // repository root in this workspace.
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .and_then(Path::parent)
        .expect("session-core repository root")
        .to_path_buf()
}

fn seed(root: &Path, repository: PathBuf) -> Result<(), FixtureError> {
    validate_root(root, &repository)?;
    let storage = StorageRoot::create(root, &repository)?;
    let meeting_dir = storage.path().join("meetings").join(MEETING_ID);
    for child in ["", "capture", "transcript", "notes"] {
        create_private_dir(&meeting_dir.join(child))?;
    }

    let rule = AudioRetentionRule::UntilManualDeletion;
    let policy = retention_policy_sha256(&rule);
    let attempt = json!({
        "schema": "capture-attempt/1",
        "meeting_id": MEETING_ID,
        "attempt_id": "11111111-1111-4111-8111-111111111111",
        "created_at_epoch_seconds": CREATED_AT,
        "application_build_sha256": "a".repeat(64),
        "participant_notice_version": "internal-transcript-alpha/1",
        "operator_attestation": {
            "participantsConsented": true,
            "headphones": true,
            "operatorAlone": true,
        },
        "retention_policy_sha256": policy,
    });
    write_new(
        &meeting_dir.join("attempt.json"),
        &serde_json::to_vec_pretty(&attempt)?,
    )?;
    write_new(
        &meeting_dir.join("ownership.json"),
        br#"{"schema":"capture-ownership/1","source":"synthetic-fixture"}
"#,
    )?;

    let mic = wav(AUDIO_FRAMES);
    let system = wav(AUDIO_FRAMES);
    write_new(&meeting_dir.join("capture/mic.wav"), &mic)?;
    write_new(&meeting_dir.join("capture/system.wav"), &system)?;
    let mic_ref = artifact_ref(&meeting_dir, "capture/mic.wav")?;
    let system_ref = artifact_ref(&meeting_dir, "capture/system.wav")?;
    let receipt = json!({
        "schema": "capture-session/2",
        "status": "complete",
        "started_at": "2023-11-14T22:13:20+0000",
        "finalized_at": "2023-11-14T22:13:21+0000",
        "health": {"schema":"capture-health/1","usable":true},
        "quality": {
            "schema": "capture-quality/1",
            "source": {"leg":"mic","artifact":"mic.wav","samples":AUDIO_FRAMES,"sha256":mic_ref.sha256},
            "metrics": {"duration_s":8.0},
            "observations": {
                "silence":{"status":"observed","detail":"synthetic"},
                "clipping":{"status":"not_observed","detail":"synthetic"},
                "low_input":{"status":"observed","detail":"synthetic"},
                "background_noise":{"status":"unknown","detail":"synthetic"}
            }
        },
        "microphone": {"schema":"capture-microphone/1","index":0,"name":"Synthetic microphone"},
        "reconciliation": {"legs":{"mic":"complete","system":"complete"}},
        "artifacts": [
            {"name":"mic.wav","bytes":mic.len(),"sha256":mic_ref.sha256,"mode":"0600"},
            {"name":"system.wav","bytes":system.len(),"sha256":system_ref.sha256,"mode":"0600"}
        ]
    });
    write_new(
        &meeting_dir.join("capture/session.json"),
        &serde_json::to_vec_pretty(&receipt)?,
    )?;
    let session_ref = artifact_ref(&meeting_dir, "capture/session.json")?;

    let source = transcript_bytes(&[
        ("Me", "We will review the synthetic launch checklist."),
        ("Them", "The next step is to test the rendered comparison."),
        ("Me", "The fixture contains no real meeting material."),
    ]);
    let source_digest = digest(&source);
    let source_path = format!("transcript/{source_digest}.json");
    write_new(&meeting_dir.join(&source_path), &source)?;
    let current_ref = artifact_ref(&meeting_dir, &source_path)?;

    let meeting = MeetingRecord {
        schema: MeetingSchema::V2,
        meeting_id: MEETING_ID.to_owned(),
        lifecycle: MeetingLifecycle::TranscriptReady,
        retention: AudioRetention {
            rule,
            policy_sha256: policy,
            next_deletion_at_epoch_seconds: None,
            state: AudioState::Retained,
            deletion_receipt: None,
        },
        artifacts: MeetingArtifacts {
            attempt: artifact_ref(&meeting_dir, "attempt.json")?,
            ownership: Some(artifact_ref(&meeting_dir, "ownership.json")?),
            capture_session: Some(session_ref.clone()),
            microphone_audio: Some(mic_ref.clone()),
            system_audio: Some(system_ref.clone()),
            current_transcript: Some(current_ref.clone()),
            current_note: None,
        },
        pending_storage_operation: None,
    };
    write_meeting(&meeting_dir, &meeting)?;
    verify_record_artifacts(&meeting_dir, &load_meeting(&meeting_dir)?)?;

    let candidate = transcript_bytes(&[
        ("Me", "We will review the synthetic comparison fixture."),
        ("Them", "The candidate is different and remains pending."),
        ("Me", "The current transcript pointer stays unchanged."),
    ]);
    let coordination = MeetingStorageCoordination::default();
    let authority = TranscriptRetryAuthority::new(&storage, &coordination);
    authority.create_candidate(
        MEETING_ID,
        Uuid::parse_str(OPERATION_ID).expect("fixed operation id"),
        &candidate,
        &TranscriptRetrySourceBinding {
            source_transcript_sha256: current_ref.sha256.clone(),
            capture_session_sha256: session_ref.sha256.clone(),
            microphone_audio_sha256: mic_ref.sha256.clone(),
            system_audio_sha256: system_ref.sha256.clone(),
            candidate_transcript_sha256: digest(&candidate),
        },
    )?;

    let marker = json!({
        "schema": "synthetic-fixture-evidence/1",
        "bundle": BUNDLE_NAME,
        "private_data": false,
        "product_evidence": false,
        "content": "deterministic invented review fixture",
        "meeting_id": MEETING_ID,
        "retry_operation_id": OPERATION_ID,
        "covered_states": ["retained meeting", "verified audio", "quality and device projections", "pending transcript retry"],
        "note": "No generated note is seeded; this fixture remains TranscriptReady and does not invoke a note worker."
    });
    write_new(
        &storage.path().join("SYNTHETIC_FIXTURE.json"),
        &serde_json::to_vec_pretty(&marker)?,
    )?;
    Ok(())
}

#[derive(serde::Deserialize)]
#[serde(deny_unknown_fields)]
struct SyntheticFixtureMarker {
    schema: String,
    bundle: String,
    private_data: bool,
    product_evidence: bool,
    content: String,
    meeting_id: String,
    retry_operation_id: String,
    covered_states: Vec<String>,
    note: String,
}

fn install_model(
    root: &Path,
    bundle_resources: &Path,
    source_model_dir: &Path,
    model_id: &str,
    repository: PathBuf,
) -> Result<(), FixtureError> {
    validate_install_root(root, &repository)?;
    validate_external_directory(bundle_resources, "bundle resources")?;
    validate_external_directory(source_model_dir, "source model")?;
    if source_model_dir.starts_with(&repository.canonicalize().unwrap_or(repository.clone())) {
        return Err(FixtureError::UnsafeInstallPath(
            "source model is inside the source repository".into(),
        ));
    }

    let manifest_path = bundle_resources.join("app-runtime.json");
    let manifest = RuntimeManifest::load_and_verify(&manifest_path)?;
    let catalog_resource = manifest
        .model_catalog
        .as_ref()
        .ok_or(FixtureError::MissingModelCatalog)?;
    let catalog_path = manifest
        .model_catalog_path(&manifest_path)
        .ok_or(FixtureError::MissingModelCatalog)?;
    let catalog = ModelCatalog::load_and_verify(&catalog_path, &catalog_resource.sha256)?;
    let entry = catalog
        .model(model_id)
        .map_err(|_| FixtureError::UnknownModel)?
        .clone();
    if source_model_dir.file_name().and_then(|name| name.to_str()) != Some(entry.revision.as_str())
        || source_model_dir
            .parent()
            .and_then(Path::file_name)
            .and_then(|name| name.to_str())
            != Some(entry.id.as_str())
    {
        return Err(FixtureError::UnsafeInstallPath(
            "source model leaf must be exactly <id>/<revision>".into(),
        ));
    }

    let storage = StorageRoot::create(root, &repository)?;
    let active_path = storage
        .resolve(Path::new("models/active-model.json"))
        .map_err(|error| FixtureError::Storage(error))?;
    if fs::symlink_metadata(&active_path).is_ok() {
        return Err(FixtureError::ExistingModel);
    }
    let target = storage
        .resolve(&Path::new("models").join(&entry.id).join(&entry.revision))
        .map_err(FixtureError::Storage)?;
    if fs::symlink_metadata(&target).is_ok()
        || fs::symlink_metadata(&storage.path().join("MODEL_FIXTURE.json")).is_ok()
    {
        return Err(FixtureError::ExistingModel);
    }

    // Keep the canonical writer boundary through copy, re-verification, and
    // activation. A live app cannot race this fixture install.
    let _writer_lock = AppDataWriterLock::acquire(&storage)?;
    if fs::symlink_metadata(&active_path).is_ok()
        || fs::symlink_metadata(&target).is_ok()
        || fs::symlink_metadata(&storage.path().join("MODEL_FIXTURE.json")).is_ok()
    {
        return Err(FixtureError::ExistingModel);
    }
    verify_model_directory(source_model_dir, &entry).map_err(|_| FixtureError::SourceChanged)?;
    create_private_dir(&target)?;
    for file in &entry.files {
        if !matches!(
            file.role,
            TranscriptModelFileRole::Config | TranscriptModelFileRole::Weights
        ) {
            return Err(FixtureError::ModelStore(
                ModelStoreError::InvalidCatalogEntry,
            ));
        }
        copy_private_model_file(
            &source_model_dir.join(&file.name),
            &target.join(&file.name),
            file.bytes,
        )?;
    }
    durable_create_new(
        &target.join("model-install.json"),
        &install_receipt_bytes(&entry),
    )?;
    sync_directory(&target)?;
    verify_model_directory(&target, &entry)?;
    verify_model_directory(source_model_dir, &entry).map_err(|_| FixtureError::SourceChanged)?;

    let model_marker = json!({
        "schema": "synthetic-model-fixture/1",
        "model_id": entry.id,
        "revision": entry.revision,
        "private_data": false,
        "product_evidence": false,
        "note": "Public model bytes copied from a verified catalog entry for synthetic fixture review."
    });
    durable_create_new(
        &storage.path().join("MODEL_FIXTURE.json"),
        &serde_json::to_vec_pretty(&model_marker)?,
    )?;
    activate_model(&storage, &entry)?;
    Ok(())
}

fn validate_install_root(root: &Path, repository: &Path) -> Result<(), FixtureError> {
    if !root.is_absolute() || root.file_name().and_then(|name| name.to_str()) != Some(BUNDLE_NAME) {
        return Err(FixtureError::WrongRootName);
    }
    let metadata = fs::symlink_metadata(root).map_err(|_| FixtureError::UnsafeDirectory)?;
    if metadata.file_type().is_symlink() {
        return Err(FixtureError::Symlink);
    }
    if !metadata.file_type().is_dir() || metadata.permissions().mode() & 0o777 != 0o700 {
        return Err(FixtureError::UnsafeDirectory);
    }
    let parent = root
        .parent()
        .ok_or(FixtureError::BroadRoot)?
        .canonicalize()
        .unwrap_or_else(|_| root.parent().unwrap().to_path_buf());
    if [
        "/",
        "/tmp",
        "/private/tmp",
        "/Users",
        "/Users/nino",
        "/Users/nino/Workspace",
        "/Users/nino/Workspace/dev",
        "/Users/nino/Workspace/dev/apps",
    ]
    .iter()
    .any(|broad| parent == Path::new(broad))
    {
        return Err(FixtureError::BroadRoot);
    }
    let repository = repository
        .canonicalize()
        .unwrap_or_else(|_| repository.to_path_buf());
    if root.starts_with(&repository) || parent.starts_with(&repository) {
        return Err(FixtureError::InsideRepository);
    }
    let marker_path = root.join("SYNTHETIC_FIXTURE.json");
    let marker_metadata =
        fs::symlink_metadata(&marker_path).map_err(|_| FixtureError::InvalidMarker)?;
    if marker_metadata.file_type().is_symlink()
        || !marker_metadata.file_type().is_file()
        || marker_metadata.permissions().mode() & 0o777 != 0o600
    {
        return Err(FixtureError::InvalidMarker);
    }
    let marker: SyntheticFixtureMarker = serde_json::from_slice(&fs::read(&marker_path)?)
        .map_err(|_| FixtureError::InvalidMarker)?;
    if marker.schema != "synthetic-fixture-evidence/1"
        || marker.bundle != BUNDLE_NAME
        || marker.private_data
        || marker.product_evidence
        || marker.content != "deterministic invented review fixture"
        || marker.meeting_id != MEETING_ID
        || marker.retry_operation_id != OPERATION_ID
        || marker.covered_states
            != vec![
                "retained meeting",
                "verified audio",
                "quality and device projections",
                "pending transcript retry",
            ]
        || marker.note
            != "No generated note is seeded; this fixture remains TranscriptReady and does not invoke a note worker."
    {
        return Err(FixtureError::InvalidMarker);
    }
    if fs::symlink_metadata(root.join("MODEL_FIXTURE.json")).is_ok() {
        return Err(FixtureError::ExistingModel);
    }
    Ok(())
}

fn validate_external_directory(path: &Path, label: &str) -> Result<(), FixtureError> {
    if !path.is_absolute() {
        return Err(FixtureError::UnsafeInstallPath(format!(
            "{label} must be absolute"
        )));
    }
    let metadata = fs::symlink_metadata(path)
        .map_err(|_| FixtureError::UnsafeInstallPath(format!("{label} is missing")))?;
    if metadata.file_type().is_symlink() || !metadata.file_type().is_dir() {
        return Err(FixtureError::UnsafeInstallPath(format!(
            "{label} must be a nonsymlink directory"
        )));
    }
    Ok(())
}

fn copy_private_model_file(
    source: &Path,
    target: &Path,
    expected_bytes: u64,
) -> Result<(), FixtureError> {
    let mut input = fs::OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW)
        .open(source)
        .map_err(FixtureError::Io)?;
    let metadata = input.metadata()?;
    if !metadata.file_type().is_file() || metadata.len() != expected_bytes {
        return Err(FixtureError::SourceChanged);
    }
    let mut output = fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o600)
        .open(target)?;
    let mut buffer = [0_u8; 64 * 1024];
    let mut copied = 0_u64;
    loop {
        let read = input.read(&mut buffer)?;
        if read == 0 {
            break;
        }
        output.write_all(&buffer[..read])?;
        copied = copied.saturating_add(read as u64);
    }
    if copied != expected_bytes {
        return Err(FixtureError::SourceChanged);
    }
    output.sync_all()?;
    Ok(())
}

fn validate_root(root: &Path, repository: &Path) -> Result<(), FixtureError> {
    if !root.is_absolute() {
        return Err(FixtureError::RelativeRoot);
    }
    if root.file_name().and_then(|name| name.to_str()) != Some(BUNDLE_NAME) {
        return Err(FixtureError::WrongRootName);
    }
    if fs::symlink_metadata(root)
        .map(|metadata| metadata.file_type().is_symlink())
        .unwrap_or(false)
    {
        return Err(FixtureError::Symlink);
    }
    let parent = root.parent().ok_or(FixtureError::BroadRoot)?;
    let parent = parent
        .canonicalize()
        .unwrap_or_else(|_| parent.to_path_buf());
    if [
        "/",
        "/tmp",
        "/private/tmp",
        "/Users",
        "/Users/nino",
        "/Users/nino/Workspace",
        "/Users/nino/Workspace/dev",
        "/Users/nino/Workspace/dev/apps",
    ]
    .iter()
    .any(|broad| parent == Path::new(broad))
    {
        return Err(FixtureError::BroadRoot);
    }
    let repository = repository
        .canonicalize()
        .unwrap_or_else(|_| repository.to_path_buf());
    let root_lexical = root.to_path_buf();
    if root_lexical.starts_with(&repository) || parent.starts_with(&repository) {
        return Err(FixtureError::InsideRepository);
    }
    if let Ok(metadata) = fs::symlink_metadata(root) {
        if !metadata.file_type().is_dir() || metadata.permissions().mode() & 0o777 != 0o700 {
            return Err(FixtureError::UnsafeDirectory);
        }
        if fs::read_dir(root)?.next().is_some() {
            return Err(FixtureError::ExistingData);
        }
    }
    Ok(())
}

fn write_new(path: &Path, bytes: &[u8]) -> io::Result<()> {
    durable_create_new(path, bytes)
}

fn digest(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

fn transcript_bytes(turns: &[(&str, &str)]) -> Vec<u8> {
    let turns = turns
        .iter()
        .enumerate()
        .map(|(index, (speaker, text))| {
            json!({
                "start": index as f64,
                "end": index as f64 + 0.5,
                "speaker": speaker,
                "text": text,
                "gated": false
            })
        })
        .collect::<Vec<_>>();
    serde_json::to_vec_pretty(&json!({
        "schema":"capture-transcript/1",
        "source":"synthetic-fixture",
        "attribution":"channel",
        "bleed":null,
        "voiceprint":null,
        "capture_health": {"schema":"capture-health/1","usable":true},
        "turns": turns
    }))
    .expect("synthetic transcript is serializable")
}

fn wav(frames: usize) -> Vec<u8> {
    let data_len = (frames * 2) as u32;
    let mut bytes = Vec::with_capacity(44 + data_len as usize);
    bytes.extend_from_slice(b"RIFF");
    bytes.extend_from_slice(&(36 + data_len).to_le_bytes());
    bytes.extend_from_slice(b"WAVEfmt ");
    bytes.extend_from_slice(&16_u32.to_le_bytes());
    bytes.extend_from_slice(&1_u16.to_le_bytes());
    bytes.extend_from_slice(&1_u16.to_le_bytes());
    bytes.extend_from_slice(&8_000_u32.to_le_bytes());
    bytes.extend_from_slice(&16_000_u32.to_le_bytes());
    bytes.extend_from_slice(&2_u16.to_le_bytes());
    bytes.extend_from_slice(&16_u16.to_le_bytes());
    bytes.extend_from_slice(b"data");
    bytes.extend_from_slice(&data_len.to_le_bytes());
    for _ in 0..frames {
        bytes.extend_from_slice(&0_i16.to_le_bytes());
    }
    bytes
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::symlink;
    use tempfile::TempDir;

    use local_meeting_notes_session_core::capture_quality::{
        project_capture_quality, project_recording_device, CaptureQualityObservationKind,
        CaptureQualityObservationStatus, CaptureQualityState, RecordingDeviceState,
    };
    use local_meeting_notes_session_core::meeting::verify_artifact_ref;
    use local_meeting_notes_session_core::model_store::{
        active_model, ModelCatalogSchema, TranscriptModel, TranscriptModelFile,
    };
    use local_meeting_notes_session_core::transcript_retry::TranscriptRetryState;
    use std::os::unix::fs::PermissionsExt;

    fn target(temp: &TempDir) -> PathBuf {
        temp.path().join(BUNDLE_NAME)
    }

    fn repo(temp: &TempDir) -> PathBuf {
        let path = temp.path().join("repository");
        create_private_dir(&path).unwrap();
        path
    }

    #[test]
    fn deterministic_private_free_shape_has_comparable_pending_retry() {
        let temp = TempDir::new().unwrap();
        let root = target(&temp);
        let repository = repo(&temp);
        seed(&root, repository).unwrap();
        let second_temp = TempDir::new().unwrap();
        seed(&target(&second_temp), repo(&second_temp)).unwrap();
        assert_eq!(snapshot(&root), snapshot(&target(&second_temp)));

        let storage = StorageRoot::create(&root, &temp.path().join("repository")).unwrap();
        let meeting_dir = storage.path().join("meetings").join(MEETING_ID);
        let meeting = load_meeting(&meeting_dir).unwrap();
        verify_record_artifacts(&meeting_dir, &meeting).unwrap();
        assert_eq!(meeting.lifecycle, MeetingLifecycle::TranscriptReady);
        assert!(Uuid::parse_str(MEETING_ID).is_ok());
        let source = meeting.artifacts.current_transcript.clone().unwrap();
        let quality = project_capture_quality(&meeting_dir, &meeting).unwrap();
        assert_eq!(quality.state, CaptureQualityState::Available);
        assert_eq!(
            quality
                .observations
                .iter()
                .find(|observation| observation.kind == CaptureQualityObservationKind::Silence)
                .unwrap()
                .status,
            CaptureQualityObservationStatus::Observed
        );
        assert_eq!(
            quality
                .observations
                .iter()
                .find(|observation| { observation.kind == CaptureQualityObservationKind::LowInput })
                .unwrap()
                .status,
            CaptureQualityObservationStatus::Observed
        );
        assert_eq!(
            project_recording_device(&meeting_dir, &meeting)
                .unwrap()
                .state,
            RecordingDeviceState::Identified
        );
        verify_artifact_ref(&meeting_dir, &meeting.artifacts.microphone_audio.unwrap()).unwrap();
        verify_artifact_ref(&meeting_dir, &meeting.artifacts.system_audio.unwrap()).unwrap();
        assert_silent_wav(&fs::read(meeting_dir.join("capture/mic.wav")).unwrap());
        assert_silent_wav(&fs::read(meeting_dir.join("capture/system.wav")).unwrap());

        let coordination = MeetingStorageCoordination::default();
        let authority = TranscriptRetryAuthority::new(&storage, &coordination);
        let pending = authority
            .discover_pending_candidate(MEETING_ID)
            .unwrap()
            .unwrap();
        assert_eq!(
            pending.state,
            TranscriptRetryState::CandidateAvailableForComparison
        );
        assert_ne!(
            pending.source_transcript_sha256,
            pending.candidate_transcript_sha256
        );
        assert_eq!(
            load_meeting(&meeting_dir)
                .unwrap()
                .artifacts
                .current_transcript
                .unwrap(),
            source
        );
        let bytes = authority
            .read_candidate_bytes(MEETING_ID, pending.operation_id)
            .unwrap();
        assert!(String::from_utf8_lossy(&bytes).contains("candidate is different"));
        let marker = fs::read_to_string(root.join("SYNTHETIC_FIXTURE.json")).unwrap();
        assert!(marker.contains("private_data"));
        assert!(marker.contains("product_evidence"));
    }

    fn assert_silent_wav(bytes: &[u8]) {
        assert_eq!(&bytes[0..4], b"RIFF");
        assert_eq!(&bytes[8..12], b"WAVE");
        assert_eq!(&bytes[12..16], b"fmt ");
        assert_eq!(
            u32::from_le_bytes(bytes[24..28].try_into().unwrap()),
            AUDIO_SAMPLE_RATE
        );
        assert_eq!(u16::from_le_bytes(bytes[22..24].try_into().unwrap()), 1);
        assert_eq!(u16::from_le_bytes(bytes[34..36].try_into().unwrap()), 16);
        assert_eq!(&bytes[36..40], b"data");
        let data_bytes = u32::from_le_bytes(bytes[40..44].try_into().unwrap()) as usize;
        assert_eq!(data_bytes, AUDIO_FRAMES * 2);
        assert_eq!(bytes.len(), 44 + data_bytes);
        assert!(bytes[44..].iter().all(|sample| *sample == 0));
    }

    fn snapshot(root: &Path) -> Vec<(String, Vec<u8>)> {
        fn walk(root: &Path, current: &Path, files: &mut Vec<(String, Vec<u8>)>) {
            for entry in fs::read_dir(current).unwrap() {
                let entry = entry.unwrap();
                let path = entry.path();
                if path.is_dir() {
                    walk(root, &path, files);
                } else {
                    files.push((
                        path.strip_prefix(root).unwrap().display().to_string(),
                        fs::read(path).unwrap(),
                    ));
                }
            }
        }
        let mut files = Vec::new();
        walk(root, root, &mut files);
        files.sort_by(|left, right| left.0.cmp(&right.0));
        files
    }

    #[test]
    fn rejects_wrong_name_broad_root_symlink_and_existing_content() {
        let temp = TempDir::new().unwrap();
        let repository = repo(&temp);
        assert!(matches!(
            validate_root(&temp.path().join("wrong"), &repository),
            Err(FixtureError::WrongRootName)
        ));
        assert!(matches!(
            validate_root(Path::new("/tmp").join(BUNDLE_NAME).as_path(), &repository),
            Err(FixtureError::BroadRoot)
        ));

        let link = target(&temp);
        symlink(temp.path(), &link).unwrap();
        assert!(matches!(
            validate_root(&link, &repository),
            Err(FixtureError::Symlink)
        ));

        let existing_temp = TempDir::new().unwrap();
        let existing = target(&existing_temp);
        let existing_repository = repo(&existing_temp);
        create_private_dir(&existing).unwrap();
        create_private_dir(&existing.join("meetings")).unwrap();
        write_new(&existing.join("meetings/real.json"), b"not fixture").unwrap();
        assert!(matches!(
            validate_root(&existing, &existing_repository),
            Err(FixtureError::ExistingData)
        ));
    }

    fn write_bundle_file(path: &Path, bytes: &[u8]) -> String {
        fs::write(path, bytes).unwrap();
        fs::set_permissions(path, fs::Permissions::from_mode(0o600)).unwrap();
        digest(bytes)
    }

    fn install_inputs(
        temp: &TempDir,
    ) -> (
        PathBuf,
        PathBuf,
        PathBuf,
        PathBuf,
        TranscriptModel,
        Vec<u8>,
        Vec<u8>,
    ) {
        let root = target(temp);
        let repository = repo(temp);
        seed(&root, repository.clone()).unwrap();

        let model_id = "fixture-model";
        let revision = "a".repeat(40);
        let config = br#"{"model":"fixture"}
"#
        .to_vec();
        let weights = b"synthetic weights".to_vec();
        let entry = TranscriptModel {
            id: model_id.into(),
            revision: revision.clone(),
            title: "Synthetic transcript model".into(),
            detail: "Public bytes for fixture review.".into(),
            download_bytes: (config.len() + weights.len()) as u64,
            installed_bytes: (config.len() + weights.len()) as u64,
            files: vec![
                TranscriptModelFile {
                    role: TranscriptModelFileRole::Config,
                    name: "config.json".into(),
                    url: format!("https://models.example/{revision}/config.json"),
                    bytes: config.len() as u64,
                    sha256: digest(&config),
                },
                TranscriptModelFile {
                    role: TranscriptModelFileRole::Weights,
                    name: "weights.safetensors".into(),
                    url: format!("https://models.example/{revision}/weights.safetensors"),
                    bytes: weights.len() as u64,
                    sha256: digest(&weights),
                },
            ],
        };
        let bundle = temp.path().join("bundle");
        create_private_dir(&bundle).unwrap();
        let catalog_bytes = serde_json::to_vec_pretty(&ModelCatalog {
            schema: ModelCatalogSchema::V1,
            models: vec![entry.clone()],
            note_models: Vec::new(),
        })
        .unwrap();
        let catalog_digest = write_bundle_file(&bundle.join("model-catalog.json"), &catalog_bytes);
        for (name, bytes) in [
            ("runtime", b"runtime".as_slice()),
            ("worker", b"worker".as_slice()),
            ("tap", b"tap".as_slice()),
            ("encoder", b"encoder".as_slice()),
            ("permission-probe", b"probe".as_slice()),
        ] {
            write_bundle_file(&bundle.join(name), bytes);
        }
        let manifest = json!({
            "schema":"app-runtime/2", "admission":"product",
            "runtime":{"path":"runtime","sha256":digest(b"runtime")},
            "worker":{"path":"worker","sha256":digest(b"worker")},
            "tap":{"path":"tap","sha256":digest(b"tap")},
            "encoder":{"path":"encoder","sha256":digest(b"encoder")},
            "permission_probe":{"path":"permission-probe","sha256":digest(b"probe")},
            "model_catalog":{"path":"model-catalog.json","sha256":catalog_digest},
            "models":[]
        });
        write_bundle_file(
            &bundle.join("app-runtime.json"),
            &serde_json::to_vec_pretty(&manifest).unwrap(),
        );

        let source = temp.path().join(model_id).join(&revision);
        create_private_dir(source.parent().unwrap()).unwrap();
        create_private_dir(&source).unwrap();
        write_bundle_file(&source.join("config.json"), &config);
        write_bundle_file(&source.join("weights.safetensors"), &weights);
        write_bundle_file(
            &source.join("model-install.json"),
            &install_receipt_bytes(&entry),
        );
        (root, repository, bundle, source, entry, config, weights)
    }

    #[test]
    fn install_model_copies_verified_public_bytes_and_activates_exact_entry() {
        let temp = TempDir::new().unwrap();
        let (root, repository, bundle, source, entry, config, weights) = install_inputs(&temp);
        install_model(&root, &bundle, &source, &entry.id, repository.clone()).unwrap();

        let storage = StorageRoot::create(&root, &repository).unwrap();
        let catalog = ModelCatalog {
            schema: ModelCatalogSchema::V1,
            models: vec![entry.clone()],
            note_models: Vec::new(),
        };
        assert_eq!(
            active_model(&storage, &catalog).unwrap().unwrap().revision,
            entry.revision
        );
        let target = storage
            .path()
            .join("models")
            .join(&entry.id)
            .join(&entry.revision);
        assert_eq!(fs::read(target.join("config.json")).unwrap(), config);
        assert_eq!(
            fs::read(target.join("weights.safetensors")).unwrap(),
            weights
        );
        verify_model_directory(&target, &entry).unwrap();
        let model_marker = fs::read_to_string(storage.path().join("MODEL_FIXTURE.json")).unwrap();
        assert!(model_marker.contains(&entry.id));
        assert!(!model_marker.contains(source.to_string_lossy().as_ref()));
    }

    #[test]
    fn install_model_refuses_wrong_marker_existing_target_and_changed_source() {
        let temp = TempDir::new().unwrap();
        let (root, repository, bundle, source, entry, _, _) = install_inputs(&temp);
        fs::write(root.join("SYNTHETIC_FIXTURE.json"), b"{}").unwrap();
        fs::set_permissions(
            root.join("SYNTHETIC_FIXTURE.json"),
            fs::Permissions::from_mode(0o600),
        )
        .unwrap();
        assert!(matches!(
            install_model(&root, &bundle, &source, &entry.id, repository.clone()),
            Err(FixtureError::InvalidMarker)
        ));

        let temp = TempDir::new().unwrap();
        let (root, repository, bundle, source, entry, _, _) = install_inputs(&temp);
        let target = root.join("models").join(&entry.id).join(&entry.revision);
        create_private_dir(&target).unwrap();
        assert!(matches!(
            install_model(&root, &bundle, &source, &entry.id, repository.clone()),
            Err(FixtureError::ExistingModel)
        ));

        let temp = TempDir::new().unwrap();
        let (root, repository, bundle, source, entry, _, _) = install_inputs(&temp);
        fs::write(source.join("weights.safetensors"), b"changed").unwrap();
        assert!(matches!(
            install_model(&root, &bundle, &source, &entry.id, repository),
            Err(FixtureError::SourceChanged)
        ));
    }
}

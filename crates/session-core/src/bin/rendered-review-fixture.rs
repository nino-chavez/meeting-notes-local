//! Seeds one private, deterministic app-data tree for rendered review.
//!
//! The command accepts exactly one absolute path. The final component must be
//! `com.ninochavez.local-meeting-notes.fixture`; it never accepts a live app
//! data root and it has no cleanup mode.

use std::env;
use std::fs;
use std::io;
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};

use local_meeting_notes_session_core::meeting::{
    artifact_ref, load_meeting, retention_policy_sha256, verify_record_artifacts, write_meeting,
    AudioRetention, AudioRetentionRule, AudioState, MeetingArtifacts, MeetingLifecycle,
    MeetingRecord, MeetingSchema,
};
use local_meeting_notes_session_core::meeting_coordination::MeetingStorageCoordination;
use local_meeting_notes_session_core::storage::{
    create_private_dir, durable_create_new, StorageRoot,
};
use local_meeting_notes_session_core::transcript_retry::{
    TranscriptRetryAuthority, TranscriptRetrySourceBinding,
};
use serde_json::json;
use sha2::{Digest, Sha256};
use uuid::Uuid;

const BUNDLE_NAME: &str = "com.ninochavez.local-meeting-notes.fixture";
const MEETING_ID: &str = "fixture-meeting-001";
const OPERATION_ID: &str = "22222222-2222-4222-8222-222222222222";
const CREATED_AT: u64 = 1_700_000_042;

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
}

fn main() {
    let mut args = env::args().skip(1);
    let Some(root) = args.next() else {
        eprintln!("usage: rendered-review-fixture /absolute/path/{BUNDLE_NAME}");
        std::process::exit(2);
    };
    if args.next().is_some() {
        eprintln!("usage: rendered-review-fixture /absolute/path/{BUNDLE_NAME}");
        std::process::exit(2);
    }

    let root = PathBuf::from(root);
    if let Err(error) = seed(&root, repository_root()) {
        eprintln!("rendered-review-fixture: {error}");
        std::process::exit(1);
    }
    println!("seeded synthetic fixture at {}", root.display());
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

    let mic = wav(220, 160);
    let system = wav(440, 160);
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
            "source": {"leg":"mic","artifact":"mic.wav","samples":160,"sha256":mic_ref.sha256},
            "metrics": {"duration_s":0.02},
            "observations": {
                "silence":{"status":"not_observed","detail":"synthetic"},
                "clipping":{"status":"not_observed","detail":"synthetic"},
                "low_input":{"status":"not_observed","detail":"synthetic"},
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
        "note": "No generated note is seeded: note semantics are worker-owned and the reader requires a projector for Ready notes."
    });
    write_new(
        &storage.path().join("SYNTHETIC_FIXTURE.json"),
        &serde_json::to_vec_pretty(&marker)?,
    )?;
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

fn wav(frequency: u32, frames: usize) -> Vec<u8> {
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
    for index in 0..frames {
        let sample = (((index as u32 * frequency) % 2_000) as i16) - 1_000;
        bytes.extend_from_slice(&sample.to_le_bytes());
    }
    bytes
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::symlink;
    use tempfile::TempDir;

    use local_meeting_notes_session_core::capture_quality::{
        project_capture_quality, project_recording_device, CaptureQualityState,
        RecordingDeviceState,
    };
    use local_meeting_notes_session_core::meeting::verify_artifact_ref;
    use local_meeting_notes_session_core::transcript_retry::TranscriptRetryState;

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
        let source = meeting.artifacts.current_transcript.clone().unwrap();
        let quality = project_capture_quality(&meeting_dir, &meeting).unwrap();
        assert_eq!(quality.state, CaptureQualityState::Available);
        assert_eq!(
            project_recording_device(&meeting_dir, &meeting)
                .unwrap()
                .state,
            RecordingDeviceState::Identified
        );
        verify_artifact_ref(&meeting_dir, &meeting.artifacts.microphone_audio.unwrap()).unwrap();
        verify_artifact_ref(&meeting_dir, &meeting.artifacts.system_audio.unwrap()).unwrap();

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
}

use std::collections::HashSet;
use std::fs;
use std::io::{self, Read};
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use thiserror::Error;

use crate::meeting::{
    ArtifactRef, AudioState, MAX_RECEIPT_BYTES, MeetingError, MeetingRecord,
    PendingStorageOperation, artifact_ref, load_meeting, open_private_file, read_private_bytes,
    resolve_artifact, verify_artifact_ref, verify_record_artifacts, verify_record_static_artifacts,
    write_meeting,
};
use crate::storage::{
    StorageRoot, create_private_dir, durable_create_new, durable_replace, sync_directory,
};

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct AudioDeletionReceipt {
    schema: AudioDeletionSchema,
    capture_session_sha256: String,
    state: DeletionState,
    artifacts: Vec<DeletedArtifact>,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
enum AudioDeletionSchema {
    #[serde(rename = "audio-deletion/1")]
    V1,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "kebab-case")]
enum DeletionState {
    Deleting,
    Staged,
    Removed,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct DeletedArtifact {
    relative_name: String,
    byte_size: u64,
    sha256: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum RetentionOutcome {
    NotDue(String),
    AudioReleased(String),
    RecoveredRemoval(String),
    Quarantined(String),
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum MeetingRetentionResult {
    NotDue,
    AudioReleased,
    RecoveredRemoval,
}

#[derive(Debug, Error)]
pub enum RetentionError {
    #[error("audio state is unexplained")]
    UnexplainedAudioLoss,
    #[error("audio deletion receipt is malformed")]
    MalformedReceipt,
    #[error("capture audio is not a regular private file")]
    InvalidAudio,
    #[error(transparent)]
    Meeting(#[from] MeetingError),
    #[error(transparent)]
    Io(#[from] io::Error),
    #[error(transparent)]
    Json(#[from] serde_json::Error),
}

pub fn execute_due_retention(
    storage: &StorageRoot,
    now_epoch_seconds: u64,
) -> Result<Vec<RetentionOutcome>, RetentionError> {
    let meetings = storage
        .resolve(Path::new("meetings"))
        .map_err(|error| io::Error::other(error.to_string()))?;
    let mut outcomes = Vec::new();
    for entry in fs::read_dir(meetings)? {
        let entry = entry?;
        let id = entry.file_name().to_string_lossy().into_owned();
        if !entry.file_type()?.is_dir() {
            outcomes.push(RetentionOutcome::Quarantined(id));
            continue;
        }
        let meeting_dir = entry.path();
        let result = (|| {
            let mut meeting = load_meeting(&meeting_dir)?;
            reconcile_meeting_retention(&meeting_dir, &mut meeting, now_epoch_seconds, true)
        })();
        outcomes.push(match result {
            Ok(MeetingRetentionResult::NotDue) => RetentionOutcome::NotDue(id),
            Ok(MeetingRetentionResult::AudioReleased) => RetentionOutcome::AudioReleased(id),
            Ok(MeetingRetentionResult::RecoveredRemoval) => RetentionOutcome::RecoveredRemoval(id),
            Err(_) => RetentionOutcome::Quarantined(id),
        });
    }
    Ok(outcomes)
}

pub(crate) fn reconcile_meeting_retention(
    meeting_dir: &Path,
    meeting: &mut MeetingRecord,
    now_epoch_seconds: u64,
    execute_due: bool,
) -> Result<MeetingRetentionResult, RetentionError> {
    meeting.validate(&meeting.meeting_id)?;
    verify_record_static_artifacts(meeting_dir, meeting)?;
    let receipt_path = meeting_dir.join("deletion/audio-deletion.json");
    let receipt_present = match fs::symlink_metadata(&receipt_path) {
        Ok(_) => true,
        Err(error) if error.kind() == io::ErrorKind::NotFound => false,
        Err(error) => return Err(error.into()),
    };

    if receipt_present {
        let receipt = load_receipt(&receipt_path)?;
        validate_receipt_binding(meeting, &receipt)?;
        let already_released = meeting.retention.state == AudioState::Released;
        if already_released {
            let stored_receipt = meeting
                .retention
                .deletion_receipt
                .as_ref()
                .ok_or(RetentionError::MalformedReceipt)?;
            verify_artifact_ref(meeting_dir, stored_receipt)?;
            if receipt.state != DeletionState::Removed {
                return Err(RetentionError::MalformedReceipt);
            }
        }
        finish_staged_removal(meeting_dir, &receipt_path, meeting, receipt)?;
        write_meeting(meeting_dir, meeting)?;
        return Ok(if already_released {
            MeetingRetentionResult::NotDue
        } else {
            MeetingRetentionResult::RecoveredRemoval
        });
    }

    if matches!(
        meeting.retention.state,
        AudioState::Deleting | AudioState::Released
    ) {
        return Err(RetentionError::UnexplainedAudioLoss);
    }
    verify_record_artifacts(meeting_dir, meeting)?;
    if meeting.retention.state == AudioState::NeverCreated {
        return Ok(MeetingRetentionResult::NotDue);
    }
    let due = meeting
        .retention
        .next_deletion_at_epoch_seconds
        .is_some_and(|deadline| deadline <= now_epoch_seconds);
    if !execute_due || !due {
        return Ok(MeetingRetentionResult::NotDue);
    }

    let capture_session = meeting
        .artifacts
        .capture_session
        .as_ref()
        .ok_or(RetentionError::UnexplainedAudioLoss)?;
    let mut artifacts = Vec::new();
    for reference in audio_references(meeting) {
        let inspected = inspect_audio(
            &resolve_artifact(meeting_dir, &reference.relative_path)?,
            &reference.relative_path,
        )?;
        if inspected.sha256 != reference.sha256 {
            return Err(RetentionError::UnexplainedAudioLoss);
        }
        artifacts.push(inspected);
    }
    if artifacts.is_empty() {
        return Err(RetentionError::UnexplainedAudioLoss);
    }
    artifacts.sort_by(|left, right| left.relative_name.cmp(&right.relative_name));
    let receipt = AudioDeletionReceipt {
        schema: AudioDeletionSchema::V1,
        capture_session_sha256: capture_session.sha256.clone(),
        state: DeletionState::Deleting,
        artifacts,
    };
    let deletion_dir = meeting_dir.join("deletion");
    create_private_dir(&deletion_dir)?;
    durable_create_new(&receipt_path, &serde_json::to_vec_pretty(&receipt)?)?;
    meeting.retention.state = AudioState::Deleting;
    meeting.pending_storage_operation = Some(PendingStorageOperation::AudioDeletionV1);
    write_meeting(meeting_dir, meeting)?;

    finish_staged_removal(meeting_dir, &receipt_path, meeting, receipt)?;
    write_meeting(meeting_dir, meeting)?;
    Ok(MeetingRetentionResult::AudioReleased)
}

fn finish_staged_removal(
    meeting_dir: &Path,
    receipt_path: &Path,
    meeting: &mut MeetingRecord,
    mut receipt: AudioDeletionReceipt,
) -> Result<(), RetentionError> {
    validate_receipt_binding(meeting, &receipt)?;
    let deletion_dir = meeting_dir.join("deletion");
    let capture_dir = meeting_dir.join("capture");
    ensure_no_unbound_audio(meeting_dir, meeting)?;

    if receipt.state == DeletionState::Removed {
        for reference in audio_references(meeting) {
            let live = resolve_artifact(meeting_dir, &reference.relative_path)?;
            let staged = staged_path(&deletion_dir, &reference.relative_path)?;
            if path_present(&live)? || path_present(&staged)? {
                return Err(RetentionError::UnexplainedAudioLoss);
            }
        }
        finalize_released_record(meeting_dir, receipt_path, meeting)?;
        return Ok(());
    }

    if receipt.state == DeletionState::Deleting {
        let mut validated_locations = Vec::with_capacity(receipt.artifacts.len());
        for expected in &receipt.artifacts {
            let live = resolve_artifact(meeting_dir, &expected.relative_name)?;
            let staged = staged_path(&deletion_dir, &expected.relative_name)?;
            let live_present = path_present(&live)?;
            let staged_present = path_present(&staged)?;
            if live_present == staged_present {
                return Err(RetentionError::UnexplainedAudioLoss);
            }
            let present = if live_present { &live } else { &staged };
            let actual = inspect_audio(present, &expected.relative_name)?;
            if &actual != expected {
                return Err(RetentionError::UnexplainedAudioLoss);
            }
            validated_locations.push((live, staged, live_present));
        }

        for (live, staged, live_present) in validated_locations {
            if live_present {
                fs::rename(&live, &staged)?;
            }
        }
        sync_directory(&capture_dir)?;
        sync_directory(&deletion_dir)?;
        receipt.state = DeletionState::Staged;
        durable_replace(receipt_path, &serde_json::to_vec_pretty(&receipt)?)?;
    }

    let mut staged_to_remove = Vec::with_capacity(receipt.artifacts.len());
    for expected in &receipt.artifacts {
        let live = resolve_artifact(meeting_dir, &expected.relative_name)?;
        if path_present(&live)? {
            return Err(RetentionError::UnexplainedAudioLoss);
        }
        let staged = staged_path(&deletion_dir, &expected.relative_name)?;
        if path_present(&staged)? {
            let actual = inspect_audio(&staged, &expected.relative_name)?;
            if &actual != expected {
                return Err(RetentionError::UnexplainedAudioLoss);
            }
            staged_to_remove.push(staged);
        }
    }
    for staged in staged_to_remove {
        fs::remove_file(staged)?;
    }
    sync_directory(&deletion_dir)?;
    receipt.state = DeletionState::Removed;
    durable_replace(receipt_path, &serde_json::to_vec_pretty(&receipt)?)?;
    finalize_released_record(meeting_dir, receipt_path, meeting)?;
    Ok(())
}

fn finalize_released_record(
    meeting_dir: &Path,
    receipt_path: &Path,
    meeting: &mut MeetingRecord,
) -> Result<(), RetentionError> {
    let receipt_relative = receipt_path
        .strip_prefix(meeting_dir)
        .map_err(|_| RetentionError::MalformedReceipt)?
        .to_str()
        .ok_or(RetentionError::MalformedReceipt)?;
    meeting.retention.state = AudioState::Released;
    meeting.retention.deletion_receipt = Some(artifact_ref(meeting_dir, receipt_relative)?);
    meeting.pending_storage_operation = None;
    Ok(())
}

fn validate_receipt_binding(
    meeting: &MeetingRecord,
    receipt: &AudioDeletionReceipt,
) -> Result<(), RetentionError> {
    let capture_session = meeting
        .artifacts
        .capture_session
        .as_ref()
        .ok_or(RetentionError::MalformedReceipt)?;
    if receipt.capture_session_sha256 != capture_session.sha256 {
        return Err(RetentionError::MalformedReceipt);
    }
    let references = audio_references(meeting);
    if references.is_empty() || receipt.artifacts.len() != references.len() {
        return Err(RetentionError::MalformedReceipt);
    }
    let mut names = HashSet::new();
    for artifact in &receipt.artifacts {
        if !names.insert(&artifact.relative_name) {
            return Err(RetentionError::MalformedReceipt);
        }
        let Some(reference) = references
            .iter()
            .find(|reference| reference.relative_path == artifact.relative_name)
        else {
            return Err(RetentionError::MalformedReceipt);
        };
        if artifact.sha256 != reference.sha256 {
            return Err(RetentionError::MalformedReceipt);
        }
    }
    Ok(())
}

fn ensure_no_unbound_audio(
    meeting_dir: &Path,
    meeting: &MeetingRecord,
) -> Result<(), RetentionError> {
    for (relative, bound) in [
        (
            "capture/mic.wav",
            meeting.artifacts.microphone_audio.is_some(),
        ),
        (
            "capture/system.wav",
            meeting.artifacts.system_audio.is_some(),
        ),
    ] {
        if bound {
            continue;
        }
        let live = meeting_dir.join(relative);
        let staged = staged_path(&meeting_dir.join("deletion"), relative)?;
        if path_present(&live)? || path_present(&staged)? {
            return Err(RetentionError::UnexplainedAudioLoss);
        }
    }
    Ok(())
}

fn audio_references(meeting: &MeetingRecord) -> Vec<&ArtifactRef> {
    [
        meeting.artifacts.microphone_audio.as_ref(),
        meeting.artifacts.system_audio.as_ref(),
    ]
    .into_iter()
    .flatten()
    .collect()
}

fn staged_path(deletion_dir: &Path, relative_name: &str) -> Result<PathBuf, RetentionError> {
    let file_name = Path::new(relative_name)
        .file_name()
        .and_then(|name| name.to_str())
        .ok_or(RetentionError::MalformedReceipt)?;
    if !matches!(relative_name, "capture/mic.wav" | "capture/system.wav") {
        return Err(RetentionError::MalformedReceipt);
    }
    Ok(deletion_dir.join(format!("{file_name}.staged")))
}

fn path_present(path: &Path) -> Result<bool, RetentionError> {
    match fs::symlink_metadata(path) {
        Ok(_) => Ok(true),
        Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(false),
        Err(error) => Err(error.into()),
    }
}

fn load_receipt(path: &Path) -> Result<AudioDeletionReceipt, RetentionError> {
    let bytes = read_private_bytes(path, MAX_RECEIPT_BYTES)?;
    serde_json::from_slice(&bytes).map_err(|_| RetentionError::MalformedReceipt)
}

fn inspect_audio(path: &Path, relative_name: &str) -> Result<DeletedArtifact, RetentionError> {
    let mut file = open_private_file(path).map_err(|_| RetentionError::InvalidAudio)?;
    let metadata = file.metadata()?;
    let mut hasher = Sha256::new();
    let mut buffer = [0_u8; 64 * 1024];
    loop {
        let read = file.read(&mut buffer)?;
        if read == 0 {
            break;
        }
        hasher.update(&buffer[..read]);
    }
    Ok(DeletedArtifact {
        relative_name: relative_name.into(),
        byte_size: metadata.len(),
        sha256: format!("{:x}", hasher.finalize()),
    })
}

pub fn meeting_dir(storage: &StorageRoot, meeting_id: &str) -> Result<PathBuf, io::Error> {
    storage
        .resolve(&Path::new("meetings").join(meeting_id))
        .map_err(|error| io::Error::other(error.to_string()))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::meeting::{
        AudioRetention, AudioRetentionRule, MeetingArtifacts, MeetingLifecycle, MeetingSchema,
        artifact_ref, retention_policy_sha256,
    };
    use crate::storage::{create_private_dir, durable_create_new};
    use tempfile::TempDir;

    fn fixture(storage: &StorageRoot, id: &str, deadline: Option<u64>) -> (PathBuf, MeetingRecord) {
        let directory = meeting_dir(storage, id).unwrap();
        create_private_dir(&directory).unwrap();
        create_private_dir(&directory.join("capture")).unwrap();
        for (relative, bytes) in [
            ("attempt.json", b"attempt".as_slice()),
            ("ownership.json", b"ownership".as_slice()),
            ("capture/session.json", b"session".as_slice()),
            ("capture/mic.wav", b"mic".as_slice()),
            ("capture/system.wav", b"system".as_slice()),
        ] {
            durable_create_new(&directory.join(relative), bytes).unwrap();
        }
        let rule = match deadline {
            Some(_) => AudioRetentionRule::DeleteAfter { seconds: 10 },
            None => AudioRetentionRule::UntilManualDeletion,
        };
        let meeting = MeetingRecord {
            schema: MeetingSchema::V2,
            meeting_id: id.into(),
            lifecycle: MeetingLifecycle::Captured,
            retention: AudioRetention {
                policy_sha256: retention_policy_sha256(&rule),
                rule,
                next_deletion_at_epoch_seconds: deadline,
                state: AudioState::Retained,
                deletion_receipt: None,
            },
            artifacts: MeetingArtifacts {
                attempt: artifact_ref(&directory, "attempt.json").unwrap(),
                ownership: Some(artifact_ref(&directory, "ownership.json").unwrap()),
                capture_session: Some(artifact_ref(&directory, "capture/session.json").unwrap()),
                microphone_audio: Some(artifact_ref(&directory, "capture/mic.wav").unwrap()),
                system_audio: Some(artifact_ref(&directory, "capture/system.wav").unwrap()),
                current_transcript: None,
                current_note: None,
            },
            pending_storage_operation: None,
        };
        durable_create_new(
            &directory.join("meeting.json"),
            &serde_json::to_vec_pretty(&meeting).unwrap(),
        )
        .unwrap();
        (directory, meeting)
    }

    fn storage() -> (TempDir, StorageRoot) {
        let temp = TempDir::new().unwrap();
        let repo = temp.path().join("repo");
        create_private_dir(&repo).unwrap();
        let storage = StorageRoot::create(&temp.path().join("app"), &repo).unwrap();
        (temp, storage)
    }

    fn begin_audio_deletion(directory: &Path, meeting: &mut MeetingRecord) {
        create_private_dir(&directory.join("deletion")).unwrap();
        let receipt = AudioDeletionReceipt {
            schema: AudioDeletionSchema::V1,
            capture_session_sha256: meeting
                .artifacts
                .capture_session
                .as_ref()
                .unwrap()
                .sha256
                .clone(),
            state: DeletionState::Deleting,
            artifacts: vec![
                inspect_audio(&directory.join("capture/mic.wav"), "capture/mic.wav").unwrap(),
                inspect_audio(&directory.join("capture/system.wav"), "capture/system.wav").unwrap(),
            ],
        };
        durable_create_new(
            &directory.join("deletion/audio-deletion.json"),
            &serde_json::to_vec_pretty(&receipt).unwrap(),
        )
        .unwrap();
        meeting.retention.state = AudioState::Deleting;
        meeting.pending_storage_operation = Some(PendingStorageOperation::AudioDeletionV1);
        write_meeting(directory, meeting).unwrap();
    }

    #[test]
    fn due_retention_preserves_content_lifecycle() {
        let (_temp, storage) = storage();
        let (directory, _) = fixture(&storage, "meeting-a", Some(10));
        create_private_dir(&directory.join("transcript")).unwrap();
        durable_create_new(&directory.join("transcript/retained.json"), b"{}\n").unwrap();

        assert_eq!(
            execute_due_retention(&storage, 10).unwrap(),
            vec![RetentionOutcome::AudioReleased("meeting-a".into())]
        );
        assert!(!directory.join("capture/mic.wav").exists());
        assert!(!directory.join("capture/system.wav").exists());
        assert!(directory.join("transcript/retained.json").exists());
        let final_meeting = load_meeting(&directory).unwrap();
        assert_eq!(final_meeting.lifecycle, MeetingLifecycle::Captured);
        assert_eq!(final_meeting.retention.state, AudioState::Released);
        verify_record_artifacts(&directory, &final_meeting).unwrap();
    }

    #[test]
    fn missing_audio_without_completed_receipt_is_quarantined_without_rewrite() {
        let (_temp, storage) = storage();
        let (directory, meeting) = fixture(&storage, "meeting-b", Some(10));
        fs::remove_file(directory.join("capture/mic.wav")).unwrap();
        let before = fs::read(directory.join("meeting.json")).unwrap();

        assert_eq!(
            execute_due_retention(&storage, 10).unwrap(),
            vec![RetentionOutcome::Quarantined("meeting-b".into())]
        );
        assert_eq!(fs::read(directory.join("meeting.json")).unwrap(), before);
        assert_eq!(meeting.retention.state, AudioState::Retained);
    }

    #[test]
    fn tampered_staged_audio_is_quarantined_without_further_deletion() {
        let (_temp, storage) = storage();
        let (directory, mut meeting) = fixture(&storage, "meeting-c", Some(10));
        begin_audio_deletion(&directory, &mut meeting);
        fs::rename(
            directory.join("capture/mic.wav"),
            directory.join("deletion/mic.wav.staged"),
        )
        .unwrap();
        durable_replace(&directory.join("deletion/mic.wav.staged"), b"tampered").unwrap();

        assert_eq!(
            execute_due_retention(&storage, 10).unwrap(),
            vec![RetentionOutcome::Quarantined("meeting-c".into())]
        );
        assert!(directory.join("deletion/mic.wav.staged").exists());
        assert!(directory.join("capture/system.wav").exists());
    }

    #[test]
    fn tampered_second_audio_is_detected_before_either_artifact_moves() {
        let (_temp, storage) = storage();
        let (directory, mut meeting) = fixture(&storage, "meeting-d", Some(10));
        begin_audio_deletion(&directory, &mut meeting);
        durable_replace(&directory.join("capture/system.wav"), b"tampered-system").unwrap();

        assert_eq!(
            execute_due_retention(&storage, 10).unwrap(),
            vec![RetentionOutcome::Quarantined("meeting-d".into())]
        );
        assert!(directory.join("capture/mic.wav").exists());
        assert!(directory.join("capture/system.wav").exists());
        assert!(!directory.join("deletion/mic.wav.staged").exists());
        assert!(!directory.join("deletion/system.wav.staged").exists());
    }

    #[test]
    fn missing_second_audio_is_detected_before_the_first_artifact_moves() {
        let (_temp, storage) = storage();
        let (directory, mut meeting) = fixture(&storage, "meeting-e", Some(10));
        begin_audio_deletion(&directory, &mut meeting);
        fs::remove_file(directory.join("capture/system.wav")).unwrap();

        assert_eq!(
            execute_due_retention(&storage, 10).unwrap(),
            vec![RetentionOutcome::Quarantined("meeting-e".into())]
        );
        assert!(directory.join("capture/mic.wav").exists());
        assert!(!directory.join("capture/system.wav").exists());
        assert!(!directory.join("deletion/mic.wav.staged").exists());
        assert!(!directory.join("deletion/system.wav.staged").exists());
    }

    #[test]
    fn malformed_meeting_does_not_abort_another_meeting() {
        let (_temp, storage) = storage();
        let (bad, _) = fixture(&storage, "bad", None);
        fixture(&storage, "good", None);
        durable_replace(&bad.join("meeting.json"), b"not-json").unwrap();

        let outcomes = execute_due_retention(&storage, 10).unwrap();
        assert!(outcomes.contains(&RetentionOutcome::Quarantined("bad".into())));
        assert!(outcomes.contains(&RetentionOutcome::NotDue("good".into())));
    }

    #[test]
    fn malformed_deletion_receipt_does_not_abort_another_meeting() {
        let (_temp, storage) = storage();
        let (bad, _) = fixture(&storage, "bad-receipt", None);
        fixture(&storage, "good-receipt", None);
        create_private_dir(&bad.join("deletion")).unwrap();
        durable_create_new(&bad.join("deletion/audio-deletion.json"), b"not-json").unwrap();

        let outcomes = execute_due_retention(&storage, 10).unwrap();
        assert!(outcomes.contains(&RetentionOutcome::Quarantined("bad-receipt".into())));
        assert!(outcomes.contains(&RetentionOutcome::NotDue("good-receipt".into())));
    }

    #[test]
    fn changed_completed_receipt_is_not_silently_rebound() {
        let (_temp, storage) = storage();
        let (directory, _) = fixture(&storage, "receipt-tamper", Some(10));
        execute_due_retention(&storage, 10).unwrap();
        let meeting_before = fs::read(directory.join("meeting.json")).unwrap();
        let receipt_path = directory.join("deletion/audio-deletion.json");
        let mut receipt: AudioDeletionReceipt =
            serde_json::from_slice(&fs::read(&receipt_path).unwrap()).unwrap();
        receipt.capture_session_sha256 = "0".repeat(64);
        durable_replace(&receipt_path, &serde_json::to_vec_pretty(&receipt).unwrap()).unwrap();

        assert_eq!(
            execute_due_retention(&storage, 10).unwrap(),
            vec![RetentionOutcome::Quarantined("receipt-tamper".into())]
        );
        assert_eq!(
            fs::read(directory.join("meeting.json")).unwrap(),
            meeting_before
        );
    }
}

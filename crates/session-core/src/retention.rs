use std::collections::HashSet;
use std::fs;
use std::io::{self, Read};
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use thiserror::Error;

use crate::meeting::{
    AUDIO_ARTIFACT_PATHS, ArtifactRef, AudioState, MAX_RECEIPT_BYTES, MeetingError,
    MeetingLifecycle, MeetingRecord, PendingStorageOperation, artifact_ref, load_meeting,
    open_private_file, read_private_bytes, require_private_directory, resolve_artifact,
    verify_artifact_ref, verify_record_artifacts, verify_record_static_artifacts, write_meeting,
};
use crate::meeting_coordination::{MeetingCoordinationError, MeetingStorageCoordination};
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
    DeferredActive(String),
    NotDue(String),
    AudioReleased(String),
    RecoveredRemoval(String),
    Quarantined(String),
}

/// Result of the application-private, per-meeting audio-release action.
///
/// This deliberately reports only storage authority states. It neither changes a
/// retention policy nor deletes the meeting record, transcript, note, profile,
/// or another meeting.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ManualAudioDeletionOutcome {
    DeferredActive,
    AudioReleased,
    RecoveredRemoval,
    AlreadyReleased,
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

#[derive(Debug, Error)]
pub enum ManualAudioDeletionError {
    #[error("meeting storage coordination is unavailable")]
    Coordination(#[from] MeetingCoordinationError),
    #[error(transparent)]
    Meeting(#[from] MeetingError),
    #[error(transparent)]
    Retention(#[from] RetentionError),
    #[error(transparent)]
    Io(#[from] io::Error),
}

/// Releases only the bound audio for one exact, non-active meeting.
///
/// The caller supplies the same coordination authority used by capture and
/// correction operations. This action first claims the target's active-meeting
/// lease, then holds the storage sequence gate through the staged
/// deletion/recovery path, so it cannot overlap an active capture or
/// nonterminal correction/note operation. This is intentionally session-core
/// only: no command, startup hook, or UI is wired here.
pub fn delete_meeting_audio_manually(
    storage: &StorageRoot,
    coordination: &MeetingStorageCoordination,
    meeting_id: &str,
) -> Result<ManualAudioDeletionOutcome, ManualAudioDeletionError> {
    let _lease = match coordination.acquire(meeting_id) {
        Ok(lease) => lease,
        Err(MeetingCoordinationError::AlreadyActive) => {
            return Ok(ManualAudioDeletionOutcome::DeferredActive);
        }
        Err(error) => return Err(error.into()),
    };
    let _sequence = coordination.lock_sequence()?;

    let directory = meeting_dir(storage, meeting_id)?;
    let mut meeting = load_meeting(&directory)?;
    if meeting.retention.state == AudioState::Released {
        // Re-validate the completed receipt before making the idempotent claim.
        // A changed receipt must remain a refusal, not be silently rebound.
        preflight_meeting_retention(&directory, &meeting)?;
        return Ok(ManualAudioDeletionOutcome::AlreadyReleased);
    }

    match reconcile_meeting_audio_deletion(&directory, &mut meeting, true)? {
        MeetingRetentionResult::NotDue => {
            // A retained meeting cannot reach this path because manual deletion
            // authorizes release independently of its policy or deadline.
            Err(RetentionError::UnexplainedAudioLoss.into())
        }
        MeetingRetentionResult::AudioReleased => Ok(ManualAudioDeletionOutcome::AudioReleased),
        MeetingRetentionResult::RecoveredRemoval => {
            Ok(ManualAudioDeletionOutcome::RecoveredRemoval)
        }
    }
}

pub fn execute_due_retention(
    storage: &StorageRoot,
    now_epoch_seconds: u64,
) -> Result<Vec<RetentionOutcome>, RetentionError> {
    execute_due_retention_excluding(storage, now_epoch_seconds, &HashSet::new())
}

pub fn execute_due_retention_excluding(
    storage: &StorageRoot,
    now_epoch_seconds: u64,
    active_meeting_ids: &HashSet<String>,
) -> Result<Vec<RetentionOutcome>, RetentionError> {
    let meetings = storage
        .resolve(Path::new("meetings"))
        .map_err(|error| io::Error::other(error.to_string()))?;
    let mut outcomes = Vec::new();
    for entry in fs::read_dir(meetings)? {
        let entry = entry?;
        let id = entry.file_name().to_string_lossy().into_owned();
        if active_meeting_ids.contains(&id) {
            outcomes.push(RetentionOutcome::DeferredActive(id));
            continue;
        }
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

pub(crate) fn preflight_meeting_retention(
    meeting_dir: &Path,
    meeting: &MeetingRecord,
) -> Result<(), RetentionError> {
    meeting.validate(&meeting.meeting_id)?;
    verify_record_static_artifacts(meeting_dir, meeting)?;
    validate_deletion_directory(meeting_dir)?;
    let receipt_path = meeting_dir.join("deletion/audio-deletion.json");
    if !deletion_receipt_present(&receipt_path)? {
        if matches!(
            meeting.retention.state,
            AudioState::Deleting | AudioState::Released
        ) {
            return Err(RetentionError::UnexplainedAudioLoss);
        }
        ensure_no_staged_audio_without_receipt(meeting_dir)?;
        if meeting.lifecycle != MeetingLifecycle::Incomplete {
            ensure_no_unbound_audio(meeting_dir, meeting)?;
        }
        verify_record_artifacts(meeting_dir, meeting)?;
        return Ok(());
    }

    let receipt = load_receipt(&receipt_path)?;
    validate_receipt_binding(meeting, &receipt)?;
    if meeting.retention.state == AudioState::Released {
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
    validate_receipt_storage(meeting_dir, meeting, &receipt)
}

pub(crate) fn reconcile_meeting_retention(
    meeting_dir: &Path,
    meeting: &mut MeetingRecord,
    now_epoch_seconds: u64,
    execute_due: bool,
) -> Result<MeetingRetentionResult, RetentionError> {
    let due = meeting
        .retention
        .next_deletion_at_epoch_seconds
        .is_some_and(|deadline| deadline <= now_epoch_seconds);
    reconcile_meeting_audio_deletion(meeting_dir, meeting, execute_due && due)
}

/// Runs the audited `audio-deletion/1` recovery and staged-removal state
/// machine. `release_retained_audio` controls only the authority to begin a
/// new deletion; receipts already on disk are always reconciled first.
fn reconcile_meeting_audio_deletion(
    meeting_dir: &Path,
    meeting: &mut MeetingRecord,
    release_retained_audio: bool,
) -> Result<MeetingRetentionResult, RetentionError> {
    preflight_meeting_retention(meeting_dir, meeting)?;
    let receipt_path = meeting_dir.join("deletion/audio-deletion.json");
    let receipt_present = deletion_receipt_present(&receipt_path)?;

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
    if !release_retained_audio {
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
    validate_receipt_storage(meeting_dir, meeting, &receipt)?;

    if receipt.state == DeletionState::Removed {
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

fn deletion_receipt_present(receipt_path: &Path) -> Result<bool, RetentionError> {
    match fs::symlink_metadata(receipt_path) {
        Ok(_) => Ok(true),
        Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(false),
        Err(error) => Err(error.into()),
    }
}

fn validate_deletion_directory(meeting_dir: &Path) -> Result<(), RetentionError> {
    let deletion_dir = meeting_dir.join("deletion");
    match fs::symlink_metadata(&deletion_dir) {
        Ok(_) => {
            require_private_directory(&deletion_dir)?;
            Ok(())
        }
        Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(()),
        Err(error) => Err(error.into()),
    }
}

fn validate_receipt_storage(
    meeting_dir: &Path,
    meeting: &MeetingRecord,
    receipt: &AudioDeletionReceipt,
) -> Result<(), RetentionError> {
    let deletion_dir = meeting_dir.join("deletion");
    ensure_no_unbound_audio(meeting_dir, meeting)?;
    for expected in &receipt.artifacts {
        let live = resolve_artifact(meeting_dir, &expected.relative_name)?;
        let staged = staged_path(&deletion_dir, &expected.relative_name)?;
        let live_present = path_present(&live)?;
        let staged_present = path_present(&staged)?;
        match receipt.state {
            DeletionState::Deleting => {
                if live_present == staged_present {
                    return Err(RetentionError::UnexplainedAudioLoss);
                }
                let present = if live_present { &live } else { &staged };
                if inspect_audio(present, &expected.relative_name)? != *expected {
                    return Err(RetentionError::UnexplainedAudioLoss);
                }
            }
            DeletionState::Staged => {
                if live_present {
                    return Err(RetentionError::UnexplainedAudioLoss);
                }
                if staged_present && inspect_audio(&staged, &expected.relative_name)? != *expected {
                    return Err(RetentionError::UnexplainedAudioLoss);
                }
            }
            DeletionState::Removed => {
                if live_present || staged_present {
                    return Err(RetentionError::UnexplainedAudioLoss);
                }
            }
        }
    }
    Ok(())
}

fn ensure_no_staged_audio_without_receipt(meeting_dir: &Path) -> Result<(), RetentionError> {
    let deletion_dir = meeting_dir.join("deletion");
    for relative in AUDIO_ARTIFACT_PATHS {
        if path_present(&staged_path(&deletion_dir, relative)?)? {
            return Err(RetentionError::UnexplainedAudioLoss);
        }
    }
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
    let bound: HashSet<&str> = audio_references(meeting)
        .into_iter()
        .map(|reference| reference.relative_path.as_str())
        .collect();
    for relative in AUDIO_ARTIFACT_PATHS {
        if bound.contains(relative) {
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
    if !AUDIO_ARTIFACT_PATHS.contains(&relative_name) {
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
    use crate::meeting_coordination::MeetingStorageCoordination;
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

    fn partial_fixture(storage: &StorageRoot, id: &str) -> (PathBuf, MeetingRecord) {
        let directory = meeting_dir(storage, id).unwrap();
        create_private_dir(&directory).unwrap();
        create_private_dir(&directory.join("capture")).unwrap();
        durable_create_new(&directory.join("attempt.json"), b"attempt").unwrap();
        durable_create_new(&directory.join("ownership.json"), b"ownership").unwrap();
        let mic_bytes = vec![1_u8; 44];
        let system_bytes = vec![2_u8; 44];
        durable_create_new(&directory.join("capture/.mic.wav.partial"), &mic_bytes).unwrap();
        durable_create_new(
            &directory.join("capture/.system.wav.partial"),
            &system_bytes,
        )
        .unwrap();
        let mic = artifact_ref(&directory, "capture/.mic.wav.partial").unwrap();
        let system = artifact_ref(&directory, "capture/.system.wav.partial").unwrap();
        let interruption = serde_json::json!({
            "schema": "capture-interruption/1",
            "status": "interrupted",
            "reason": "fresh-process-recovery",
            "meeting_id": id,
            "artifacts": [
                {
                    "name": ".mic.wav.partial",
                    "bytes": mic_bytes.len(),
                    "sha256": mic.sha256.clone(),
                    "mode": "0600"
                },
                {
                    "name": ".system.wav.partial",
                    "bytes": system_bytes.len(),
                    "sha256": system.sha256.clone(),
                    "mode": "0600"
                }
            ]
        });
        durable_create_new(
            &directory.join("capture/session.json"),
            &serde_json::to_vec_pretty(&interruption).unwrap(),
        )
        .unwrap();
        let rule = AudioRetentionRule::DeleteAfter { seconds: 10 };
        let meeting = MeetingRecord {
            schema: MeetingSchema::V2,
            meeting_id: id.into(),
            lifecycle: MeetingLifecycle::RecoveredInterrupted,
            retention: AudioRetention {
                policy_sha256: retention_policy_sha256(&rule),
                rule,
                next_deletion_at_epoch_seconds: Some(10),
                state: AudioState::Retained,
                deletion_receipt: None,
            },
            artifacts: MeetingArtifacts {
                attempt: artifact_ref(&directory, "attempt.json").unwrap(),
                ownership: Some(artifact_ref(&directory, "ownership.json").unwrap()),
                capture_session: Some(artifact_ref(&directory, "capture/session.json").unwrap()),
                microphone_audio: Some(mic),
                system_audio: Some(system),
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

    fn advance_interrupted_deletion_to_staged(directory: &Path) {
        fs::rename(
            directory.join("capture/mic.wav"),
            directory.join("deletion/mic.wav.staged"),
        )
        .unwrap();
        fs::rename(
            directory.join("capture/system.wav"),
            directory.join("deletion/system.wav.staged"),
        )
        .unwrap();
        sync_directory(&directory.join("capture")).unwrap();
        sync_directory(&directory.join("deletion")).unwrap();
        let receipt_path = directory.join("deletion/audio-deletion.json");
        let mut receipt: AudioDeletionReceipt =
            serde_json::from_slice(&fs::read(&receipt_path).unwrap()).unwrap();
        receipt.state = DeletionState::Staged;
        durable_replace(&receipt_path, &serde_json::to_vec_pretty(&receipt).unwrap()).unwrap();
    }

    fn advance_interrupted_deletion_to_removed(directory: &Path) {
        advance_interrupted_deletion_to_staged(directory);
        fs::remove_file(directory.join("deletion/mic.wav.staged")).unwrap();
        fs::remove_file(directory.join("deletion/system.wav.staged")).unwrap();
        sync_directory(&directory.join("deletion")).unwrap();
        let receipt_path = directory.join("deletion/audio-deletion.json");
        let mut receipt: AudioDeletionReceipt =
            serde_json::from_slice(&fs::read(&receipt_path).unwrap()).unwrap();
        receipt.state = DeletionState::Removed;
        durable_replace(&receipt_path, &serde_json::to_vec_pretty(&receipt).unwrap()).unwrap();
    }

    #[test]
    fn manual_deletion_releases_an_until_manual_meeting_and_preserves_other_private_content() {
        let (_temp, storage) = storage();
        let (target, _) = fixture(&storage, "manual-target", None);
        let (other, _) = fixture(&storage, "manual-other", Some(1_000));
        create_private_dir(&target.join("transcript")).unwrap();
        create_private_dir(&target.join("notes")).unwrap();
        create_private_dir(&storage.path().join("profile")).unwrap();
        durable_create_new(&target.join("transcript/retained.json"), b"transcript").unwrap();
        durable_create_new(&target.join("notes/retained.md"), b"note").unwrap();
        durable_create_new(&storage.path().join("profile/profile.json"), b"profile").unwrap();
        let coordination = MeetingStorageCoordination::default();

        assert_eq!(
            delete_meeting_audio_manually(&storage, &coordination, "manual-target").unwrap(),
            ManualAudioDeletionOutcome::AudioReleased
        );

        assert!(!target.join("capture/mic.wav").exists());
        assert!(!target.join("capture/system.wav").exists());
        assert!(target.join("transcript/retained.json").exists());
        assert!(target.join("notes/retained.md").exists());
        assert!(storage.path().join("profile/profile.json").exists());
        assert!(other.join("capture/mic.wav").exists());
        assert!(other.join("capture/system.wav").exists());
        assert_eq!(
            load_meeting(&target).unwrap().retention.state,
            AudioState::Released
        );
    }

    #[test]
    fn manual_deletion_ignores_a_not_yet_due_deadline_and_is_idempotent() {
        let (_temp, storage) = storage();
        let (directory, _) = fixture(&storage, "manual-before-deadline", Some(u64::MAX));
        let coordination = MeetingStorageCoordination::default();

        assert_eq!(
            delete_meeting_audio_manually(&storage, &coordination, "manual-before-deadline")
                .unwrap(),
            ManualAudioDeletionOutcome::AudioReleased
        );
        let committed = fs::read(directory.join("meeting.json")).unwrap();
        assert_eq!(
            delete_meeting_audio_manually(&storage, &coordination, "manual-before-deadline")
                .unwrap(),
            ManualAudioDeletionOutcome::AlreadyReleased
        );
        assert_eq!(fs::read(directory.join("meeting.json")).unwrap(), committed);
    }

    #[test]
    fn manual_deletion_defers_an_active_meeting_without_opening_its_directory() {
        let (_temp, storage) = storage();
        let (directory, _) = fixture(&storage, "manual-active", None);
        durable_replace(&directory.join("meeting.json"), b"write-in-progress").unwrap();
        let before = fs::read(directory.join("meeting.json")).unwrap();
        let coordination = MeetingStorageCoordination::default();
        let _lease = coordination.acquire("manual-active").unwrap();

        assert_eq!(
            delete_meeting_audio_manually(&storage, &coordination, "manual-active").unwrap(),
            ManualAudioDeletionOutcome::DeferredActive
        );
        assert_eq!(fs::read(directory.join("meeting.json")).unwrap(), before);
        assert!(directory.join("capture/mic.wav").exists());
        assert!(directory.join("capture/system.wav").exists());
    }

    #[test]
    fn manual_deletion_recovers_each_interrupted_receipt_phase() {
        let (_temp, storage) = storage();
        let coordination = MeetingStorageCoordination::default();

        for (id, advance) in [
            ("manual-deleting", None),
            (
                "manual-staged",
                Some(advance_interrupted_deletion_to_staged as fn(&Path)),
            ),
            (
                "manual-removed",
                Some(advance_interrupted_deletion_to_removed as fn(&Path)),
            ),
        ] {
            let (directory, mut meeting) = fixture(&storage, id, None);
            begin_audio_deletion(&directory, &mut meeting);
            if let Some(advance) = advance {
                advance(&directory);
            }

            assert_eq!(
                delete_meeting_audio_manually(&storage, &coordination, id).unwrap(),
                ManualAudioDeletionOutcome::RecoveredRemoval
            );
            assert_eq!(
                load_meeting(&directory).unwrap().retention.state,
                AudioState::Released
            );
            assert!(!directory.join("capture/mic.wav").exists());
            assert!(!directory.join("capture/system.wav").exists());
            assert!(!directory.join("deletion/mic.wav.staged").exists());
            assert!(!directory.join("deletion/system.wav.staged").exists());
        }
    }

    #[test]
    fn manual_deletion_refuses_unbound_or_missing_audio_without_rewrite() {
        let (_temp, storage) = storage();
        let (directory, _) = partial_fixture(&storage, "manual-unbound");
        durable_create_new(&directory.join("capture/mic.wav"), &[7_u8; 44]).unwrap();
        let before = fs::read(directory.join("meeting.json")).unwrap();
        let coordination = MeetingStorageCoordination::default();

        assert!(delete_meeting_audio_manually(&storage, &coordination, "manual-unbound").is_err());
        assert_eq!(fs::read(directory.join("meeting.json")).unwrap(), before);
        assert!(directory.join("capture/mic.wav").exists());
        assert!(directory.join("capture/.mic.wav.partial").exists());
        assert!(!directory.join("deletion/audio-deletion.json").exists());
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
    fn active_meeting_is_deferred_without_read_or_mutation() {
        let (_temp, storage) = storage();
        let (directory, _) = fixture(&storage, "meeting-active", Some(10));
        durable_replace(&directory.join("meeting.json"), b"write-in-progress").unwrap();
        let before = fs::read(directory.join("meeting.json")).unwrap();
        let active = HashSet::from(["meeting-active".to_string()]);

        assert_eq!(
            execute_due_retention_excluding(&storage, 10, &active).unwrap(),
            vec![RetentionOutcome::DeferredActive("meeting-active".into())]
        );
        assert_eq!(fs::read(directory.join("meeting.json")).unwrap(), before);
        assert!(directory.join("capture/mic.wav").exists());
        assert!(directory.join("capture/system.wav").exists());
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

    #[test]
    fn due_retention_atomically_releases_bound_partial_names() {
        let (_temp, storage) = storage();
        let (directory, _) = partial_fixture(&storage, "partial-release");

        assert_eq!(
            execute_due_retention(&storage, 10).unwrap(),
            vec![RetentionOutcome::AudioReleased("partial-release".into())]
        );
        assert!(!directory.join("capture/.mic.wav.partial").exists());
        assert!(!directory.join("capture/.system.wav.partial").exists());
        assert!(!directory.join("deletion/.mic.wav.partial.staged").exists());
        assert!(
            !directory
                .join("deletion/.system.wav.partial.staged")
                .exists()
        );
        let meeting = load_meeting(&directory).unwrap();
        assert_eq!(meeting.lifecycle, MeetingLifecycle::RecoveredInterrupted);
        assert_eq!(meeting.retention.state, AudioState::Released);
        let receipt: serde_json::Value = serde_json::from_slice(
            &fs::read(directory.join("deletion/audio-deletion.json")).unwrap(),
        )
        .unwrap();
        let names: Vec<_> = receipt["artifacts"]
            .as_array()
            .unwrap()
            .iter()
            .map(|artifact| artifact["relative_name"].as_str().unwrap())
            .collect();
        assert_eq!(
            names,
            vec!["capture/.mic.wav.partial", "capture/.system.wav.partial"]
        );
    }

    #[test]
    fn tampered_partial_pair_is_rejected_before_either_leg_moves() {
        let (_temp, storage) = storage();
        let (directory, _) = partial_fixture(&storage, "partial-tamper");
        durable_replace(&directory.join("capture/.system.wav.partial"), &[9_u8; 44]).unwrap();

        assert_eq!(
            execute_due_retention(&storage, 10).unwrap(),
            vec![RetentionOutcome::Quarantined("partial-tamper".into())]
        );
        assert!(directory.join("capture/.mic.wav.partial").exists());
        assert!(directory.join("capture/.system.wav.partial").exists());
        assert!(!directory.join("deletion/.mic.wav.partial.staged").exists());
        assert!(
            !directory
                .join("deletion/.system.wav.partial.staged")
                .exists()
        );
        assert!(!directory.join("deletion/audio-deletion.json").exists());
    }

    #[test]
    fn unbound_duplicate_name_is_rejected_before_retention_mutates_state() {
        let (_temp, storage) = storage();
        let (directory, _) = partial_fixture(&storage, "partial-duplicate");
        durable_create_new(&directory.join("capture/mic.wav"), &[7_u8; 44]).unwrap();
        let before = fs::read(directory.join("meeting.json")).unwrap();

        assert_eq!(
            execute_due_retention(&storage, 10).unwrap(),
            vec![RetentionOutcome::Quarantined("partial-duplicate".into())]
        );
        assert_eq!(fs::read(directory.join("meeting.json")).unwrap(), before);
        assert!(!directory.join("deletion/audio-deletion.json").exists());
        assert!(directory.join("capture/mic.wav").exists());
        assert!(directory.join("capture/.mic.wav.partial").exists());
    }
}

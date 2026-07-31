use std::fs;
use std::io::{self, Read};
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use thiserror::Error;

use crate::storage::{
    StorageRoot, create_private_dir, durable_create_new, durable_replace, sync_directory,
};

#[derive(Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct MeetingRecord {
    pub schema: MeetingSchema,
    pub meeting_id: String,
    pub lifecycle: MeetingLifecycle,
    pub capture_session_sha256: String,
    pub next_audio_deletion_at_epoch_seconds: Option<u64>,
    pub audio_released: bool,
    pub pending_storage_operation: Option<String>,
}

#[derive(Debug, Serialize, Deserialize, PartialEq, Eq)]
pub enum MeetingSchema {
    #[serde(rename = "meeting/1")]
    V1,
}

#[derive(Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "kebab-case")]
pub enum MeetingLifecycle {
    Captured,
    Ready,
    Deleting,
    AudioReleased,
    Quarantined,
}

#[derive(Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct AudioDeletionReceipt {
    schema: AudioDeletionSchema,
    capture_session_sha256: String,
    state: DeletionState,
    artifacts: Vec<DeletedArtifact>,
}

#[derive(Debug, Serialize, Deserialize)]
enum AudioDeletionSchema {
    #[serde(rename = "audio-deletion/1")]
    V1,
}

#[derive(Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "kebab-case")]
enum DeletionState {
    Deleting,
    Removed,
}

#[derive(Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct DeletedArtifact {
    relative_name: String,
    byte_size: u64,
    sha256: String,
}

#[derive(Debug, PartialEq, Eq)]
pub enum RetentionOutcome {
    NotDue(String),
    AudioReleased(String),
    RecoveredRemoval(String),
    Quarantined(String),
}

#[derive(Debug, Error)]
pub enum RetentionError {
    #[error("meeting record is malformed")]
    MalformedMeeting,
    #[error("audio state is unexplained")]
    UnexplainedAudioLoss,
    #[error("capture audio is not a regular private file")]
    InvalidAudio,
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
        if !entry.file_type()?.is_dir() {
            continue;
        }
        let meeting_dir = entry.path();
        let meeting_path = meeting_dir.join("meeting.json");
        let bytes = match fs::read(&meeting_path) {
            Ok(bytes) => bytes,
            Err(_) => {
                outcomes.push(RetentionOutcome::Quarantined(
                    entry.file_name().to_string_lossy().into_owned(),
                ));
                continue;
            }
        };
        let mut meeting: MeetingRecord = match serde_json::from_slice(&bytes) {
            Ok(meeting) => meeting,
            Err(_) => {
                outcomes.push(RetentionOutcome::Quarantined(
                    entry.file_name().to_string_lossy().into_owned(),
                ));
                continue;
            }
        };
        let receipt_path = meeting_dir.join("deletion/audio-deletion.json");
        let mic = meeting_dir.join("capture/mic.wav");
        let system = meeting_dir.join("capture/system.wav");

        if receipt_path.exists() {
            let receipt: AudioDeletionReceipt = serde_json::from_slice(&fs::read(&receipt_path)?)?;
            if receipt.capture_session_sha256 != meeting.capture_session_sha256 {
                meeting.lifecycle = MeetingLifecycle::Quarantined;
                write_meeting(&meeting_path, &meeting)?;
                outcomes.push(RetentionOutcome::Quarantined(meeting.meeting_id));
                continue;
            }
            if finish_staged_removal(&meeting_dir, &receipt_path, &mut meeting, receipt).is_err() {
                meeting.lifecycle = MeetingLifecycle::Quarantined;
                write_meeting(&meeting_path, &meeting)?;
                outcomes.push(RetentionOutcome::Quarantined(meeting.meeting_id));
                continue;
            }
            write_meeting(&meeting_path, &meeting)?;
            outcomes.push(RetentionOutcome::RecoveredRemoval(meeting.meeting_id));
            continue;
        }

        if !mic.exists() || !system.exists() {
            meeting.lifecycle = MeetingLifecycle::Quarantined;
            write_meeting(&meeting_path, &meeting)?;
            outcomes.push(RetentionOutcome::Quarantined(meeting.meeting_id));
            continue;
        }

        let due = meeting
            .next_audio_deletion_at_epoch_seconds
            .is_some_and(|deadline| deadline <= now_epoch_seconds);
        if !due || meeting.audio_released {
            outcomes.push(RetentionOutcome::NotDue(meeting.meeting_id));
            continue;
        }

        let artifacts = vec![
            inspect_audio(&mic, "capture/mic.wav")?,
            inspect_audio(&system, "capture/system.wav")?,
        ];
        let receipt = AudioDeletionReceipt {
            schema: AudioDeletionSchema::V1,
            capture_session_sha256: meeting.capture_session_sha256.clone(),
            state: DeletionState::Deleting,
            artifacts,
        };
        let deletion_dir = meeting_dir.join("deletion");
        create_private_dir(&deletion_dir)?;
        durable_create_new(&receipt_path, &serde_json::to_vec_pretty(&receipt)?)?;
        meeting.lifecycle = MeetingLifecycle::Deleting;
        meeting.pending_storage_operation = Some("audio-deletion/1".into());
        write_meeting(&meeting_path, &meeting)?;

        fs::rename(&mic, deletion_dir.join("mic.wav.staged"))?;
        fs::rename(&system, deletion_dir.join("system.wav.staged"))?;
        sync_directory(&meeting_dir.join("capture"))?;
        sync_directory(&deletion_dir)?;
        finish_staged_removal(&meeting_dir, &receipt_path, &mut meeting, receipt)?;
        write_meeting(&meeting_path, &meeting)?;
        outcomes.push(RetentionOutcome::AudioReleased(meeting.meeting_id));
    }
    Ok(outcomes)
}

fn finish_staged_removal(
    meeting_dir: &Path,
    receipt_path: &Path,
    meeting: &mut MeetingRecord,
    mut receipt: AudioDeletionReceipt,
) -> Result<(), RetentionError> {
    let deletion_dir = meeting_dir.join("deletion");
    let capture_dir = meeting_dir.join("capture");
    if receipt.state == DeletionState::Removed {
        let any_audio_exists = [
            capture_dir.join("mic.wav"),
            capture_dir.join("system.wav"),
            deletion_dir.join("mic.wav.staged"),
            deletion_dir.join("system.wav.staged"),
        ]
        .iter()
        .any(|path| path.exists());
        if any_audio_exists {
            return Err(RetentionError::UnexplainedAudioLoss);
        }
        meeting.lifecycle = MeetingLifecycle::AudioReleased;
        meeting.audio_released = true;
        meeting.pending_storage_operation = None;
        return Ok(());
    }

    for (relative_name, live, staged) in [
        (
            "capture/mic.wav",
            capture_dir.join("mic.wav"),
            deletion_dir.join("mic.wav.staged"),
        ),
        (
            "capture/system.wav",
            capture_dir.join("system.wav"),
            deletion_dir.join("system.wav.staged"),
        ),
    ] {
        if live.exists() && staged.exists() {
            return Err(RetentionError::UnexplainedAudioLoss);
        }
        let expected = receipt
            .artifacts
            .iter()
            .find(|artifact| artifact.relative_name == relative_name)
            .ok_or(RetentionError::UnexplainedAudioLoss)?;
        let present = if live.exists() {
            Some(&live)
        } else if staged.exists() {
            Some(&staged)
        } else {
            None
        };
        if let Some(path) = present {
            let actual = inspect_audio(path, relative_name)?;
            if actual.byte_size != expected.byte_size || actual.sha256 != expected.sha256 {
                return Err(RetentionError::UnexplainedAudioLoss);
            }
        }
        if live.exists() && !staged.exists() {
            fs::rename(&live, &staged)?;
        }
        if staged.exists() {
            fs::remove_file(staged)?;
        }
    }
    sync_directory(&capture_dir)?;
    sync_directory(&deletion_dir)?;
    receipt.state = DeletionState::Removed;
    durable_replace(receipt_path, &serde_json::to_vec_pretty(&receipt)?)?;
    meeting.lifecycle = MeetingLifecycle::AudioReleased;
    meeting.audio_released = true;
    meeting.pending_storage_operation = None;
    Ok(())
}

fn inspect_audio(path: &Path, relative_name: &str) -> Result<DeletedArtifact, RetentionError> {
    let metadata = fs::symlink_metadata(path)?;
    if !metadata.file_type().is_file() || metadata.file_type().is_symlink() {
        return Err(RetentionError::InvalidAudio);
    }
    let mut file = fs::File::open(path)?;
    let mut hasher = Sha256::new();
    let mut buffer = [0_u8; 8192];
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

fn write_meeting(path: &Path, meeting: &MeetingRecord) -> Result<(), RetentionError> {
    durable_replace(path, &serde_json::to_vec_pretty(meeting)?)?;
    Ok(())
}

pub fn meeting_dir(storage: &StorageRoot, meeting_id: &str) -> Result<PathBuf, io::Error> {
    storage
        .resolve(&Path::new("meetings").join(meeting_id))
        .map_err(|error| io::Error::other(error.to_string()))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::storage::{create_private_dir, durable_create_new};
    use tempfile::TempDir;

    #[test]
    fn due_retention_removes_only_bound_audio() {
        let temp = TempDir::new().unwrap();
        let repo = temp.path().join("repo");
        create_private_dir(&repo).unwrap();
        let storage = StorageRoot::create(&temp.path().join("app"), &repo).unwrap();
        let meeting_dir = meeting_dir(&storage, "meeting-a").unwrap();
        create_private_dir(&meeting_dir.join("capture")).unwrap();
        create_private_dir(&meeting_dir.join("transcript")).unwrap();
        durable_create_new(&meeting_dir.join("capture/mic.wav"), b"mic").unwrap();
        durable_create_new(&meeting_dir.join("capture/system.wav"), b"system").unwrap();
        durable_create_new(&meeting_dir.join("transcript/retained.json"), b"{}\n").unwrap();
        let meeting = MeetingRecord {
            schema: MeetingSchema::V1,
            meeting_id: "meeting-a".into(),
            lifecycle: MeetingLifecycle::Captured,
            capture_session_sha256: "capture-digest".into(),
            next_audio_deletion_at_epoch_seconds: Some(10),
            audio_released: false,
            pending_storage_operation: None,
        };
        durable_create_new(
            &meeting_dir.join("meeting.json"),
            &serde_json::to_vec_pretty(&meeting).unwrap(),
        )
        .unwrap();

        let outcomes = execute_due_retention(&storage, 10).unwrap();
        assert_eq!(
            outcomes,
            vec![RetentionOutcome::AudioReleased("meeting-a".into())]
        );
        assert!(!meeting_dir.join("capture/mic.wav").exists());
        assert!(!meeting_dir.join("capture/system.wav").exists());
        assert!(meeting_dir.join("transcript/retained.json").exists());
        let final_meeting: MeetingRecord =
            serde_json::from_slice(&fs::read(meeting_dir.join("meeting.json")).unwrap()).unwrap();
        assert!(final_meeting.audio_released);
        assert_eq!(final_meeting.lifecycle, MeetingLifecycle::AudioReleased);
    }

    #[test]
    fn missing_audio_without_completed_receipt_quarantines() {
        let temp = TempDir::new().unwrap();
        let repo = temp.path().join("repo");
        create_private_dir(&repo).unwrap();
        let storage = StorageRoot::create(&temp.path().join("app"), &repo).unwrap();
        let meeting_dir = meeting_dir(&storage, "meeting-b").unwrap();
        create_private_dir(&meeting_dir.join("capture")).unwrap();
        let meeting = MeetingRecord {
            schema: MeetingSchema::V1,
            meeting_id: "meeting-b".into(),
            lifecycle: MeetingLifecycle::AudioReleased,
            capture_session_sha256: "capture-digest".into(),
            next_audio_deletion_at_epoch_seconds: None,
            audio_released: true,
            pending_storage_operation: None,
        };
        durable_create_new(
            &meeting_dir.join("meeting.json"),
            &serde_json::to_vec_pretty(&meeting).unwrap(),
        )
        .unwrap();

        assert_eq!(
            execute_due_retention(&storage, 10).unwrap(),
            vec![RetentionOutcome::Quarantined("meeting-b".into())]
        );
    }

    #[test]
    fn tampered_staged_audio_is_quarantined_without_deletion() {
        let temp = TempDir::new().unwrap();
        let repo = temp.path().join("repo");
        create_private_dir(&repo).unwrap();
        let storage = StorageRoot::create(&temp.path().join("app"), &repo).unwrap();
        let meeting_dir = meeting_dir(&storage, "meeting-c").unwrap();
        let capture_dir = meeting_dir.join("capture");
        let deletion_dir = meeting_dir.join("deletion");
        create_private_dir(&capture_dir).unwrap();
        create_private_dir(&deletion_dir).unwrap();
        let mic = capture_dir.join("mic.wav");
        let system = capture_dir.join("system.wav");
        durable_create_new(&mic, b"mic").unwrap();
        durable_create_new(&system, b"system").unwrap();

        let receipt = AudioDeletionReceipt {
            schema: AudioDeletionSchema::V1,
            capture_session_sha256: "capture-digest".into(),
            state: DeletionState::Deleting,
            artifacts: vec![
                inspect_audio(&mic, "capture/mic.wav").unwrap(),
                inspect_audio(&system, "capture/system.wav").unwrap(),
            ],
        };
        durable_create_new(
            &deletion_dir.join("audio-deletion.json"),
            &serde_json::to_vec_pretty(&receipt).unwrap(),
        )
        .unwrap();
        fs::rename(&mic, deletion_dir.join("mic.wav.staged")).unwrap();
        durable_replace(&deletion_dir.join("mic.wav.staged"), b"tampered").unwrap();

        let meeting = MeetingRecord {
            schema: MeetingSchema::V1,
            meeting_id: "meeting-c".into(),
            lifecycle: MeetingLifecycle::Deleting,
            capture_session_sha256: "capture-digest".into(),
            next_audio_deletion_at_epoch_seconds: Some(10),
            audio_released: false,
            pending_storage_operation: Some("audio-deletion/1".into()),
        };
        durable_create_new(
            &meeting_dir.join("meeting.json"),
            &serde_json::to_vec_pretty(&meeting).unwrap(),
        )
        .unwrap();

        assert_eq!(
            execute_due_retention(&storage, 10).unwrap(),
            vec![RetentionOutcome::Quarantined("meeting-c".into())]
        );
        assert!(deletion_dir.join("mic.wav.staged").exists());
        assert!(system.exists());
    }
}

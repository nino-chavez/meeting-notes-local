use std::fs;
use std::io;
use std::path::Path;
use std::time::Duration;

use serde_json::from_slice;
use thiserror::Error;

use crate::meeting::{
    AudioState, MAX_RECEIPT_BYTES, MeetingError, MeetingLifecycle, MeetingRecord, artifact_ref,
    load_meeting, read_private_bytes, resolve_artifact, verify_record_static_artifacts,
    write_meeting,
};
use crate::retention::{MeetingRetentionResult, RetentionError, reconcile_meeting_retention};
use crate::storage::StorageRoot;
use crate::supervision::{
    GroupSignaler, OwnershipReceipt, ProcessInspector, RecoveryCompletion,
    recover_owned_group_and_wait,
};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RecoveryReport {
    pub meetings: Vec<RecoveredMeeting>,
    pub blocks_capture: bool,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RecoveredMeeting {
    pub meeting_id: String,
    pub disposition: RecoveryDisposition,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum RecoveryDisposition {
    Valid,
    RecoveredInterrupted,
    RecoveredAudioDeletion,
    Quarantined(RecoveryCode),
    OwnershipAmbiguous,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RecoveryCode {
    MalformedMeeting,
    ArtifactMismatch,
    OwnershipMalformed,
    RetentionMismatch,
}

impl RecoveryCode {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::MalformedMeeting => "meeting_recovery_malformed",
            Self::ArtifactMismatch => "meeting_recovery_artifact_mismatch",
            Self::OwnershipMalformed => "meeting_recovery_ownership_malformed",
            Self::RetentionMismatch => "meeting_recovery_retention_mismatch",
        }
    }
}

#[derive(Debug, Error)]
pub enum RecoveryError {
    #[error("meeting storage cannot be enumerated")]
    StorageUnavailable,
    #[error(transparent)]
    Io(#[from] io::Error),
}

enum OneMeeting {
    Disposition(RecoveryDisposition),
    OwnershipBlocked,
    OwnershipMalformed,
}

pub fn scan_and_recover(
    storage: &StorageRoot,
    now_epoch_seconds: u64,
    inspector: &dyn ProcessInspector,
    signaler: &dyn GroupSignaler,
    shutdown_grace: Duration,
) -> Result<RecoveryReport, RecoveryError> {
    let meetings_dir = storage
        .resolve(Path::new("meetings"))
        .map_err(|_| RecoveryError::StorageUnavailable)?;
    let entries = fs::read_dir(meetings_dir).map_err(|_| RecoveryError::StorageUnavailable)?;
    let mut report = RecoveryReport {
        meetings: Vec::new(),
        blocks_capture: false,
    };

    for entry in entries {
        let entry = entry?;
        let id = entry.file_name().to_string_lossy().into_owned();
        if !entry.file_type()?.is_dir() {
            report.meetings.push(RecoveredMeeting {
                meeting_id: id,
                disposition: RecoveryDisposition::Quarantined(RecoveryCode::MalformedMeeting),
            });
            continue;
        }
        let meeting_dir = entry.path();
        let result = recover_one(
            &meeting_dir,
            now_epoch_seconds,
            inspector,
            signaler,
            shutdown_grace,
        );
        let disposition = match result {
            Ok(OneMeeting::Disposition(disposition)) => disposition,
            Ok(OneMeeting::OwnershipBlocked) => {
                report.blocks_capture = true;
                RecoveryDisposition::OwnershipAmbiguous
            }
            Ok(OneMeeting::OwnershipMalformed) => {
                report.blocks_capture = true;
                RecoveryDisposition::Quarantined(RecoveryCode::OwnershipMalformed)
            }
            Err(RecoveryOneError::Meeting(MeetingError::ArtifactMismatch)) => {
                RecoveryDisposition::Quarantined(RecoveryCode::ArtifactMismatch)
            }
            Err(RecoveryOneError::Meeting(_)) => {
                if meeting_dir.join("ownership.json").exists() {
                    report.blocks_capture = true;
                }
                RecoveryDisposition::Quarantined(RecoveryCode::MalformedMeeting)
            }
            Err(RecoveryOneError::Retention(_)) => {
                RecoveryDisposition::Quarantined(RecoveryCode::RetentionMismatch)
            }
            Err(RecoveryOneError::Io(_)) => {
                if meeting_dir.join("ownership.json").exists() {
                    report.blocks_capture = true;
                }
                RecoveryDisposition::Quarantined(RecoveryCode::MalformedMeeting)
            }
        };
        report.meetings.push(RecoveredMeeting {
            meeting_id: id,
            disposition,
        });
    }
    Ok(report)
}

#[derive(Debug, Error)]
enum RecoveryOneError {
    #[error(transparent)]
    Meeting(#[from] MeetingError),
    #[error(transparent)]
    Retention(#[from] RetentionError),
    #[error(transparent)]
    Io(#[from] io::Error),
}

fn recover_one(
    meeting_dir: &Path,
    now_epoch_seconds: u64,
    inspector: &dyn ProcessInspector,
    signaler: &dyn GroupSignaler,
    shutdown_grace: Duration,
) -> Result<OneMeeting, RecoveryOneError> {
    let mut meeting = load_meeting(meeting_dir)?;
    if meeting.lifecycle != MeetingLifecycle::Incomplete {
        let result =
            reconcile_meeting_retention(meeting_dir, &mut meeting, now_epoch_seconds, true)?;
        return Ok(OneMeeting::Disposition(match result {
            MeetingRetentionResult::NotDue => RecoveryDisposition::Valid,
            MeetingRetentionResult::AudioReleased | MeetingRetentionResult::RecoveredRemoval => {
                RecoveryDisposition::RecoveredAudioDeletion
            }
        }));
    }

    verify_record_static_artifacts(meeting_dir, &meeting)?;
    if let Some(ownership_ref) = &meeting.artifacts.ownership {
        let path = resolve_artifact(meeting_dir, &ownership_ref.relative_path)?;
        let bytes = read_private_bytes(&path, MAX_RECEIPT_BYTES)?;
        let receipt: OwnershipReceipt = match from_slice(&bytes) {
            Ok(receipt) => receipt,
            Err(_) => return Ok(OneMeeting::OwnershipMalformed),
        };
        if !receipt.validate() {
            return Ok(OneMeeting::OwnershipMalformed);
        }
        match recover_owned_group_and_wait(&receipt, inspector, signaler, shutdown_grace)? {
            RecoveryCompletion::NoChildrenLive | RecoveryCompletion::StoppedExactGroup => {}
            RecoveryCompletion::AmbiguousIdentity | RecoveryCompletion::StillRunning => {
                return Ok(OneMeeting::OwnershipBlocked);
            }
        }
    } else if capture_material_exists(meeting_dir)? {
        return Ok(OneMeeting::OwnershipMalformed);
    }

    bind_interrupted_artifacts(meeting_dir, &mut meeting)?;
    write_meeting(meeting_dir, &meeting)?;
    let _ = reconcile_meeting_retention(meeting_dir, &mut meeting, now_epoch_seconds, true)?;
    Ok(OneMeeting::Disposition(
        RecoveryDisposition::RecoveredInterrupted,
    ))
}

fn capture_material_exists(meeting_dir: &Path) -> Result<bool, io::Error> {
    for relative in [
        "capture/session.json",
        "capture/mic.wav",
        "capture/system.wav",
    ] {
        match fs::symlink_metadata(meeting_dir.join(relative)) {
            Ok(_) => return Ok(true),
            Err(error) if error.kind() == io::ErrorKind::NotFound => {}
            Err(error) => return Err(error),
        }
    }
    Ok(false)
}

fn bind_interrupted_artifacts(
    meeting_dir: &Path,
    meeting: &mut MeetingRecord,
) -> Result<(), MeetingError> {
    let session = optional_artifact(meeting_dir, "capture/session.json")?;
    let microphone = optional_artifact(meeting_dir, "capture/mic.wav")?;
    let system = optional_artifact(meeting_dir, "capture/system.wav")?;
    if (microphone.is_some() || system.is_some()) && session.is_none() {
        return Err(MeetingError::Malformed(
            "partial audio lacks its initial session receipt",
        ));
    }
    meeting.artifacts.capture_session = session;
    meeting.artifacts.microphone_audio = microphone;
    meeting.artifacts.system_audio = system;
    meeting.lifecycle = MeetingLifecycle::RecoveredInterrupted;
    meeting.retention.state = if meeting.artifacts.microphone_audio.is_some()
        || meeting.artifacts.system_audio.is_some()
    {
        AudioState::Retained
    } else {
        AudioState::NeverCreated
    };
    meeting.retention.deletion_receipt = None;
    meeting.pending_storage_operation = None;
    Ok(())
}

fn optional_artifact(
    meeting_dir: &Path,
    relative_path: &str,
) -> Result<Option<crate::meeting::ArtifactRef>, MeetingError> {
    let path = meeting_dir.join(relative_path);
    match fs::symlink_metadata(&path) {
        Ok(_) => Ok(Some(artifact_ref(meeting_dir, relative_path)?)),
        Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(None),
        Err(error) => Err(error.into()),
    }
}

#[cfg(test)]
mod tests {
    use std::cell::Cell;
    use std::collections::HashMap;
    use std::path::PathBuf;

    use super::*;
    use crate::meeting::{
        ArtifactRef, AudioRetention, AudioRetentionRule, MeetingArtifacts, MeetingSchema,
        retention_policy_sha256,
    };
    use crate::retention::meeting_dir;
    use crate::storage::{create_private_dir, durable_create_new, durable_replace};
    use crate::supervision::{OwnershipSchema, ProcessIdentity};
    use tempfile::TempDir;

    struct FakeInspector(HashMap<u32, ProcessIdentity>);

    impl ProcessInspector for FakeInspector {
        fn identity(&self, pid: u32) -> io::Result<Option<ProcessIdentity>> {
            Ok(self.0.get(&pid).cloned())
        }
    }

    struct FakeSignaler(Cell<u32>);

    impl GroupSignaler for FakeSignaler {
        fn terminate(&self, _process_group_id: i32) -> io::Result<()> {
            self.0.set(self.0.get() + 1);
            Ok(())
        }
    }

    fn make_storage() -> (TempDir, StorageRoot) {
        let temp = TempDir::new().unwrap();
        let repo = temp.path().join("repo");
        create_private_dir(&repo).unwrap();
        let storage = StorageRoot::create(&temp.path().join("app"), &repo).unwrap();
        (temp, storage)
    }

    fn write_incomplete(
        storage: &StorageRoot,
        id: &str,
        ownership: Option<OwnershipReceipt>,
    ) -> PathBuf {
        let directory = meeting_dir(storage, id).unwrap();
        create_private_dir(&directory).unwrap();
        durable_create_new(&directory.join("attempt.json"), b"attempt").unwrap();
        let ownership_ref = ownership.map(|receipt| {
            durable_create_new(
                &directory.join("ownership.json"),
                &serde_json::to_vec_pretty(&receipt).unwrap(),
            )
            .unwrap();
            artifact_ref(&directory, "ownership.json").unwrap()
        });
        let rule = AudioRetentionRule::DeleteAfter { seconds: 30 };
        let meeting = MeetingRecord {
            schema: MeetingSchema::V2,
            meeting_id: id.into(),
            lifecycle: MeetingLifecycle::Incomplete,
            retention: AudioRetention {
                policy_sha256: retention_policy_sha256(&rule),
                rule,
                next_deletion_at_epoch_seconds: Some(100),
                state: AudioState::NeverCreated,
                deletion_receipt: None,
            },
            artifacts: MeetingArtifacts {
                attempt: artifact_ref(&directory, "attempt.json").unwrap(),
                ownership: ownership_ref,
                capture_session: None,
                microphone_audio: None,
                system_audio: None,
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
        directory
    }

    fn identity(pid: u32, start: u64) -> ProcessIdentity {
        ProcessIdentity {
            pid,
            start_time_epoch_seconds: start,
            executable_path: PathBuf::from("/fixed/worker"),
            executable_sha256: "d".repeat(64),
        }
    }

    fn ownership(expected: ProcessIdentity) -> OwnershipReceipt {
        OwnershipReceipt {
            schema: OwnershipSchema::V1,
            process_group_id: expected.pid as i32,
            application_build_sha256: "a".repeat(64),
            worker_build_sha256: "b".repeat(64),
            tap_build_sha256: "c".repeat(64),
            children: vec![expected],
        }
    }

    #[test]
    fn incomplete_meeting_recovers_and_preserves_partial_audio() {
        let (_temp, storage) = make_storage();
        let expected = identity(44, 10);
        let directory = write_incomplete(&storage, "partial", Some(ownership(expected)));
        create_private_dir(&directory.join("capture")).unwrap();
        durable_create_new(&directory.join("capture/session.json"), b"incomplete").unwrap();
        durable_create_new(&directory.join("capture/mic.wav"), b"partial-mic").unwrap();
        let report = scan_and_recover(
            &storage,
            10,
            &FakeInspector(HashMap::new()),
            &FakeSignaler(Cell::new(0)),
            Duration::from_millis(1),
        )
        .unwrap();

        assert!(!report.blocks_capture);
        assert_eq!(
            report.meetings[0].disposition,
            RecoveryDisposition::RecoveredInterrupted
        );
        let meeting = load_meeting(&directory).unwrap();
        assert_eq!(meeting.lifecycle, MeetingLifecycle::RecoveredInterrupted);
        assert_eq!(meeting.retention.state, AudioState::Retained);
        assert!(directory.join("capture/mic.wav").exists());
        assert!(meeting.artifacts.system_audio.is_none());
    }

    #[test]
    fn reused_pid_is_not_signalled_and_blocks_capture() {
        let (_temp, storage) = make_storage();
        let expected = identity(44, 10);
        let directory = write_incomplete(&storage, "ambiguous", Some(ownership(expected)));
        let signaler = FakeSignaler(Cell::new(0));
        let report = scan_and_recover(
            &storage,
            10,
            &FakeInspector(HashMap::from([(44, identity(44, 11))])),
            &signaler,
            Duration::from_millis(1),
        )
        .unwrap();

        assert!(report.blocks_capture);
        assert_eq!(signaler.0.get(), 0);
        assert_eq!(
            report.meetings[0].disposition,
            RecoveryDisposition::OwnershipAmbiguous
        );
        assert_eq!(
            load_meeting(&directory).unwrap().lifecycle,
            MeetingLifecycle::Incomplete
        );
    }

    #[test]
    fn malformed_meeting_isolated_from_valid_recovery() {
        let (_temp, storage) = make_storage();
        let bad = write_incomplete(&storage, "bad", None);
        let good = write_incomplete(&storage, "good", None);
        durable_replace(&bad.join("meeting.json"), b"not-json").unwrap();
        let report = scan_and_recover(
            &storage,
            10,
            &FakeInspector(HashMap::new()),
            &FakeSignaler(Cell::new(0)),
            Duration::from_millis(1),
        )
        .unwrap();

        assert!(report.meetings.iter().any(|meeting| {
            meeting.meeting_id == "bad"
                && matches!(
                    meeting.disposition,
                    RecoveryDisposition::Quarantined(RecoveryCode::MalformedMeeting)
                )
        }));
        assert_eq!(
            load_meeting(&good).unwrap().lifecycle,
            MeetingLifecycle::RecoveredInterrupted
        );
    }

    #[test]
    fn malformed_ownership_blocks_capture_without_mutating_record() {
        let (_temp, storage) = make_storage();
        let directory = write_incomplete(&storage, "ownership", None);
        durable_create_new(&directory.join("ownership.json"), b"not-json").unwrap();
        let mut meeting = load_meeting(&directory).unwrap();
        meeting.artifacts.ownership = Some(ArtifactRef {
            relative_path: "ownership.json".into(),
            sha256: crate::meeting::hash_private_file(&directory.join("ownership.json")).unwrap(),
        });
        write_meeting(&directory, &meeting).unwrap();
        let before = fs::read(directory.join("meeting.json")).unwrap();

        let report = scan_and_recover(
            &storage,
            10,
            &FakeInspector(HashMap::new()),
            &FakeSignaler(Cell::new(0)),
            Duration::from_millis(1),
        )
        .unwrap();
        assert!(report.blocks_capture);
        assert_eq!(fs::read(directory.join("meeting.json")).unwrap(), before);
    }
}

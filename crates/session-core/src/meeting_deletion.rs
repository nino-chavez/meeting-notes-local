//! Whole-meeting deletion — the `meeting-deletion/1` audited removal.
//!
//! This removes an entire meeting: audio, transcript, note, operator note, and
//! the meeting record itself. It is deliberately a separate schema and a
//! separate state machine from `audio-deletion/1`, for two independent reasons.
//!
//! **The receipt cannot live inside what it deletes.** `audio-deletion/1` writes
//! its receipt to `meeting_dir/deletion/audio-deletion.json` and the meeting
//! record keeps an `ArtifactRef` to it, which works because that operation keeps
//! the meeting. Whole-meeting deletion removes that directory, so a receipt
//! stored there would destroy its own evidence, and a crash midway would leave
//! nothing for recovery to reconcile against. This receipt therefore lives at
//! `<root>/deletions/<meeting_id>.json`, outside the meeting.
//!
//! **The name would otherwise lie.** A receipt listing a transcript and an
//! operator note under a schema called `audio-deletion/1` misdescribes what
//! happened. This codebase refuses that everywhere else, so it refuses it here.
//!
//! The ordering inside the state machine is the safety property, not an
//! implementation detail. `meeting.json` is removed *first*, because every
//! reader in this crate reaches a meeting through `load_meeting`, and without
//! that file the load fails. After the `staged` transition there is no window in
//! which a partially removed directory can be read as an intact meeting — which
//! is the specific failure this operation must never produce.

use std::fs;
use std::io::{self, Read};
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use thiserror::Error;

use crate::meeting::{
    MAX_RECEIPT_BYTES, MeetingError, load_meeting, open_private_file, read_private_bytes,
    require_private_directory, valid_opaque_id,
};
use crate::meeting_coordination::{MeetingCoordinationError, MeetingStorageCoordination};
use crate::operation_store::{OperationStore, OperationStoreError, StoredOperationRequest};
use crate::storage::{StorageRoot, create_private_dir, durable_create_new, durable_replace};

/// Directory holding deletion receipts, as a child of the storage root.
///
/// `StorageRoot::create` seeds a fixed list of children and does not enforce it
/// as an exact set, so adding this one is additive: an older build reading a
/// root that has it is unaffected, and a newer build reading an older root
/// creates it on demand rather than assuming it.
pub(crate) const DELETIONS_DIR: &str = "deletions";

const MAX_INVENTORY_ENTRIES: usize = 4096;

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct MeetingDeletionReceipt {
    schema: MeetingDeletionSchema,
    meeting_id: String,
    state: MeetingDeletionState,
    artifacts: Vec<DeletedArtifact>,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
enum MeetingDeletionSchema {
    #[serde(rename = "meeting-deletion/1")]
    V1,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "kebab-case")]
enum MeetingDeletionState {
    /// Receipt written, inventory recorded, nothing removed yet.
    Deleting,
    /// `meeting.json` is gone. The directory can no longer load as a meeting.
    Staged,
    /// The meeting directory is gone.
    Removed,
}

/// One removed file, recorded by digest rather than by content.
///
/// A transcript's bytes are private meeting material and never appear here; its
/// SHA-256 is the same class of record `audio-deletion/1` already keeps for
/// audio, so the receipt stays content-free.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct DeletedArtifact {
    relative_name: String,
    byte_size: u64,
    sha256: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum MeetingDeletionOutcome {
    /// The meeting is active. Nothing was inspected and nothing was mutated.
    DeferredActive,
    /// The meeting and every artifact bound to it are gone.
    MeetingRemoved,
    /// An interrupted removal was found and completed.
    RecoveredRemoval,
    /// A completed removal already existed for this identifier.
    AlreadyRemoved,
}

#[derive(Debug, Error)]
pub enum MeetingDeletionError {
    #[error("meeting storage coordination is unavailable")]
    Coordination(#[from] MeetingCoordinationError),
    #[error(transparent)]
    Meeting(#[from] MeetingError),
    #[error(transparent)]
    Io(#[from] io::Error),
    #[error(transparent)]
    Json(#[from] serde_json::Error),
    #[error(transparent)]
    OperationStore(#[from] OperationStoreError),
    #[error("meeting has a nonterminal product operation")]
    NonterminalProductOperation,
    #[error("meeting deletion receipt is malformed")]
    MalformedReceipt,
    #[error("meeting storage contains an entry that is not a regular private file")]
    UnsafeEntry,
    #[error("meeting storage holds more entries than an inventory may describe")]
    InventoryTooLarge,
    #[error("no such meeting")]
    NoSuchMeeting,
}

/// The sole capability that may remove a whole meeting.
///
/// Obtained only by borrowing an [`crate::retention::AppDataWriterLock`] that
/// already holds the owner-only process lock for this storage root, so the raw
/// mutation path cannot be reached from a dependent crate.
///
/// ```compile_fail
/// use local_meeting_notes_session_core::meeting_deletion::delete_meeting_wholly;
/// # let _ = delete_meeting_wholly;
/// ```
pub struct WholeMeetingDeletionAuthority<'a> {
    pub(crate) storage: &'a StorageRoot,
    pub(crate) coordination: &'a MeetingStorageCoordination,
}

impl WholeMeetingDeletionAuthority<'_> {
    /// Removes one exact, non-active meeting in full.
    ///
    /// The caller is responsible for having obtained the operator's separate
    /// confirmation. This layer enforces authority and ordering, not consent.
    pub fn delete_meeting(
        &self,
        meeting_id: &str,
    ) -> Result<MeetingDeletionOutcome, MeetingDeletionError> {
        delete_meeting_wholly(self.storage, self.coordination, meeting_id)
    }
}

pub(crate) fn deletions_dir(storage: &StorageRoot) -> Result<PathBuf, MeetingDeletionError> {
    let path = storage
        .resolve(Path::new(DELETIONS_DIR))
        .map_err(|error| io::Error::other(error.to_string()))?;
    if !path.exists() {
        create_private_dir(&path)?;
    }
    Ok(path)
}

fn receipt_path(storage: &StorageRoot, meeting_id: &str) -> Result<PathBuf, MeetingDeletionError> {
    Ok(deletions_dir(storage)?.join(format!("{meeting_id}.json")))
}

fn load_receipt(path: &Path) -> Result<MeetingDeletionReceipt, MeetingDeletionError> {
    let bytes = read_private_bytes(path, MAX_RECEIPT_BYTES)?;
    serde_json::from_slice(&bytes).map_err(|_| MeetingDeletionError::MalformedReceipt)
}

fn write_receipt(
    path: &Path,
    receipt: &MeetingDeletionReceipt,
    create: bool,
) -> Result<(), MeetingDeletionError> {
    let bytes = serde_json::to_vec_pretty(receipt)?;
    if create {
        durable_create_new(path, &bytes)?;
    } else {
        durable_replace(path, &bytes)?;
    }
    Ok(())
}

/// Walks the meeting directory and records every file by size and digest.
///
/// Refuses anything that is not a directory or a regular file. A symlink inside
/// meeting storage means the tree is not what it claims to be, and removing it
/// could reach outside the meeting — so the inventory refuses rather than
/// following it.
fn take_inventory(meeting_dir: &Path) -> Result<Vec<DeletedArtifact>, MeetingDeletionError> {
    let mut artifacts = Vec::new();
    let mut stack = vec![meeting_dir.to_path_buf()];
    while let Some(current) = stack.pop() {
        for entry in fs::read_dir(&current)? {
            let entry = entry?;
            let path = entry.path();
            let metadata = fs::symlink_metadata(&path)?;
            if metadata.file_type().is_symlink() {
                return Err(MeetingDeletionError::UnsafeEntry);
            }
            if metadata.is_dir() {
                stack.push(path);
                continue;
            }
            if !metadata.is_file() {
                return Err(MeetingDeletionError::UnsafeEntry);
            }
            if artifacts.len() >= MAX_INVENTORY_ENTRIES {
                return Err(MeetingDeletionError::InventoryTooLarge);
            }
            let relative = path
                .strip_prefix(meeting_dir)
                .map_err(|_| MeetingDeletionError::UnsafeEntry)?
                .to_string_lossy()
                .into_owned();
            // Streamed in fixed blocks rather than read whole, and through the
            // private-file opener, matching `inspect_audio` in the audited
            // audio path. A meeting's two capture legs are the largest files
            // this walks and an hour of them is gigabytes, so reading a whole
            // file to digest it would spike memory by the size of the meeting.
            let mut file =
                open_private_file(&path).map_err(|_| MeetingDeletionError::UnsafeEntry)?;
            let mut hasher = Sha256::new();
            let mut buffer = [0_u8; 64 * 1024];
            loop {
                let read = file.read(&mut buffer)?;
                if read == 0 {
                    break;
                }
                hasher.update(&buffer[..read]);
            }
            artifacts.push(DeletedArtifact {
                relative_name: relative,
                byte_size: metadata.len(),
                sha256: format!("{:x}", hasher.finalize()),
            });
        }
    }
    artifacts.sort_by(|left, right| left.relative_name.cmp(&right.relative_name));
    Ok(artifacts)
}

/// Drives the receipt from its recorded state to `removed`.
///
/// Every transition is written before the mutation it authorizes, so a crash
/// resumes from a state that is never ahead of the filesystem.
fn finish_removal(
    meeting_dir: &Path,
    receipt_path: &Path,
    mut receipt: MeetingDeletionReceipt,
) -> Result<(), MeetingDeletionError> {
    if receipt.state == MeetingDeletionState::Deleting {
        // `meeting.json` first. After this the directory cannot load as a
        // meeting, which is the property that makes a half-deleted meeting
        // impossible to mistake for an intact one.
        let record = meeting_dir.join("meeting.json");
        if record.exists() {
            fs::remove_file(&record)?;
        }
        receipt.state = MeetingDeletionState::Staged;
        write_receipt(receipt_path, &receipt, false)?;
    }

    if receipt.state == MeetingDeletionState::Staged {
        if meeting_dir.exists() {
            fs::remove_dir_all(meeting_dir)?;
        }
        receipt.state = MeetingDeletionState::Removed;
        write_receipt(receipt_path, &receipt, false)?;
    }

    Ok(())
}

pub(crate) fn delete_meeting_wholly(
    storage: &StorageRoot,
    coordination: &MeetingStorageCoordination,
    meeting_id: &str,
) -> Result<MeetingDeletionOutcome, MeetingDeletionError> {
    if !valid_opaque_id(meeting_id) {
        return Err(MeetingError::Malformed("meeting identifier mismatch").into());
    }

    // The lease is taken before anything is inspected, so an active meeting is
    // refused without a single read of its storage.
    let _lease = match coordination.acquire(meeting_id) {
        Ok(lease) => lease,
        Err(MeetingCoordinationError::AlreadyActive) => {
            return Ok(MeetingDeletionOutcome::DeferredActive);
        }
        Err(error) => return Err(error.into()),
    };
    let _sequence = coordination.lock_sequence()?;

    let receipt_path = receipt_path(storage, meeting_id)?;
    let meeting_dir = storage
        .resolve(&Path::new("meetings").join(meeting_id))
        .map_err(|error| io::Error::other(error.to_string()))?;

    // An existing receipt is reconciled before any new authority is considered,
    // so an interrupted removal always completes rather than restarting.
    if receipt_path.exists() {
        let receipt = load_receipt(&receipt_path)?;
        if receipt.meeting_id != meeting_id {
            return Err(MeetingDeletionError::MalformedReceipt);
        }
        if receipt.state == MeetingDeletionState::Removed && !meeting_dir.exists() {
            return Ok(MeetingDeletionOutcome::AlreadyRemoved);
        }
        finish_removal(&meeting_dir, &receipt_path, receipt)?;
        return Ok(MeetingDeletionOutcome::RecoveredRemoval);
    }

    if !meeting_dir.exists() {
        return Err(MeetingDeletionError::NoSuchMeeting);
    }
    require_private_directory(&meeting_dir)?;

    // Loading proves the directory is a meeting this build understands. A
    // meeting that cannot load is quarantined by retention and is not removed
    // here, because deleting what we cannot describe would produce a receipt
    // that names nothing.
    let meeting = load_meeting(&meeting_dir)?;
    if meeting.meeting_id != meeting_id {
        return Err(MeetingError::Malformed("meeting identifier mismatch").into());
    }

    let operations = OperationStore::open(storage)?;
    let has_nonterminal = operations.scan()?.values().any(|receipt| {
        if receipt.commit.is_some() {
            return false;
        }
        match &receipt.request {
            StoredOperationRequest::Restoration(request) => {
                request.meeting_id.to_string() == meeting_id
            }
            StoredOperationRequest::NoteGeneration(request) => {
                request.meeting_id.to_string() == meeting_id
            }
        }
    });
    if has_nonterminal {
        return Err(MeetingDeletionError::NonterminalProductOperation);
    }

    let artifacts = take_inventory(&meeting_dir)?;
    let receipt = MeetingDeletionReceipt {
        schema: MeetingDeletionSchema::V1,
        meeting_id: meeting_id.to_string(),
        state: MeetingDeletionState::Deleting,
        artifacts,
    };
    // The receipt exists on disk before the first byte is removed. That
    // ordering is what makes an interrupted deletion recoverable at all.
    write_receipt(&receipt_path, &receipt, true)?;
    finish_removal(&meeting_dir, &receipt_path, receipt)?;
    Ok(MeetingDeletionOutcome::MeetingRemoved)
}

/// Identifiers with a deletion receipt that has not reached `removed`.
///
/// Retention and the library both enumerate `meetings/*`. Between the `staged`
/// and `removed` transitions the directory exists without a `meeting.json`, and
/// both readers would otherwise report that as a quarantined meeting — which
/// would show the operator a damaged meeting where they asked for an absent one.
///
/// This is a read and behaves like one: an absent `deletions/` directory means
/// no deletion has ever been started, so it reports none rather than creating
/// the directory as a side effect of being asked.
pub fn pending_deletion_ids(storage: &StorageRoot) -> Result<Vec<String>, MeetingDeletionError> {
    let directory = storage
        .resolve(Path::new(DELETIONS_DIR))
        .map_err(|error| io::Error::other(error.to_string()))?;
    if !directory.exists() {
        return Ok(Vec::new());
    }
    let mut ids = Vec::new();
    for entry in fs::read_dir(&directory)? {
        let entry = entry?;
        if !entry.file_type()?.is_file() {
            continue;
        }
        let Ok(receipt) = load_receipt(&entry.path()) else {
            continue;
        };
        if receipt.state != MeetingDeletionState::Removed {
            ids.push(receipt.meeting_id);
        }
    }
    ids.sort();
    Ok(ids)
}

/// Completes every interrupted whole-meeting deletion.
///
/// Runs at startup, before retention and before any library read, so that a
/// meeting the operator deleted never reappears as damaged after a crash.
pub fn reconcile_pending_meeting_deletions(
    storage: &StorageRoot,
    coordination: &MeetingStorageCoordination,
) -> Result<Vec<String>, MeetingDeletionError> {
    let mut completed = Vec::new();
    for id in pending_deletion_ids(storage)? {
        match delete_meeting_wholly(storage, coordination, &id) {
            Ok(MeetingDeletionOutcome::RecoveredRemoval)
            | Ok(MeetingDeletionOutcome::MeetingRemoved) => completed.push(id),
            // An active meeting cannot also be mid-deletion, but if the lease is
            // held the honest response is to leave it for the next startup
            // rather than force it.
            Ok(_) => {}
            Err(error) => return Err(error),
        }
    }
    Ok(completed)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::meeting::{
        AudioRetention, AudioRetentionRule, AudioState, MeetingArtifacts, MeetingLifecycle,
        MeetingRecord, MeetingSchema, artifact_ref, retention_policy_sha256,
    };
    use crate::storage::durable_create_new;
    use tempfile::TempDir;

    fn storage() -> (TempDir, StorageRoot) {
        let temp = TempDir::new().unwrap();
        let repo = temp.path().join("repo");
        create_private_dir(&repo).unwrap();
        let storage = StorageRoot::create(&temp.path().join("app"), &repo).unwrap();
        (temp, storage)
    }

    /// A meeting carrying every artifact class this operation must remove:
    /// audio, the transcript that is the retained evidence, a note, and the
    /// operator's own note, which is interpretation rather than evidence.
    fn fixture(storage: &StorageRoot, id: &str) -> PathBuf {
        let directory = storage
            .resolve(&Path::new("meetings").join(id))
            .unwrap();
        create_private_dir(&directory).unwrap();
        create_private_dir(&directory.join("capture")).unwrap();
        for (relative, bytes) in [
            ("attempt.json", b"attempt".as_slice()),
            ("ownership.json", b"ownership".as_slice()),
            ("capture/session.json", b"session".as_slice()),
            ("capture/mic.wav", b"mic".as_slice()),
            ("capture/system.wav", b"system".as_slice()),
            // Content that reads like meeting material, deliberately sharing no
            // substring with its own filename, so a leak test can tell the two
            // apart.
            ("transcript.json", b"we agreed to ship on friday".as_slice()),
            ("operator-note.json", b"{\"text\":\"chase legal\"}".as_slice()),
        ] {
            durable_create_new(&directory.join(relative), bytes).unwrap();
        }
        let rule = AudioRetentionRule::UntilManualDeletion;
        let meeting = MeetingRecord {
            schema: MeetingSchema::V2,
            meeting_id: id.into(),
            lifecycle: MeetingLifecycle::Captured,
            retention: AudioRetention {
                policy_sha256: retention_policy_sha256(&rule),
                rule,
                next_deletion_at_epoch_seconds: None,
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
        directory
    }

    #[test]
    fn a_removed_meeting_leaves_nothing_behind_and_says_what_it_took() {
        let (_temp, storage) = storage();
        let directory = fixture(&storage, "gone");
        let coordination = MeetingStorageCoordination::default();

        assert_eq!(
            delete_meeting_wholly(&storage, &coordination, "gone").unwrap(),
            MeetingDeletionOutcome::MeetingRemoved
        );
        assert!(!directory.exists(), "the meeting directory survived");

        let receipt = load_receipt(&receipt_path(&storage, "gone").unwrap()).unwrap();
        assert_eq!(receipt.state, MeetingDeletionState::Removed);
        let named: Vec<_> = receipt
            .artifacts
            .iter()
            .map(|artifact| artifact.relative_name.as_str())
            .collect();
        // The transcript and the operator note are named, which is precisely
        // what `audio-deletion/1` could not honestly have claimed.
        assert!(named.contains(&"transcript.json"), "{named:?}");
        assert!(named.contains(&"operator-note.json"), "{named:?}");
        assert!(named.contains(&"capture/mic.wav"), "{named:?}");
        assert!(named.contains(&"meeting.json"), "{named:?}");
    }

    #[test]
    fn the_receipt_records_digests_and_never_the_bytes() {
        let (_temp, storage) = storage();
        fixture(&storage, "digests");
        let coordination = MeetingStorageCoordination::default();
        delete_meeting_wholly(&storage, &coordination, "digests").unwrap();

        let raw = fs::read_to_string(receipt_path(&storage, "digests").unwrap()).unwrap();
        assert!(
            !raw.contains("chase legal"),
            "the operator note's text reached the receipt"
        );
        assert!(
            !raw.contains("we agreed to ship"),
            "transcript bytes reached the receipt"
        );
        // The filename is expected and must stay: naming what was removed is
        // the receipt's job. Only the content is forbidden.
        assert!(raw.contains("transcript.json"));
        let receipt = load_receipt(&receipt_path(&storage, "digests").unwrap()).unwrap();
        let note = receipt
            .artifacts
            .iter()
            .find(|artifact| artifact.relative_name == "operator-note.json")
            .unwrap();
        assert_eq!(note.sha256.len(), 64);
    }

    #[test]
    fn an_active_meeting_is_refused_without_its_storage_being_touched() {
        let (_temp, storage) = storage();
        let directory = fixture(&storage, "busy");
        let coordination = MeetingStorageCoordination::default();
        let _held = coordination.acquire("busy").unwrap();

        assert_eq!(
            delete_meeting_wholly(&storage, &coordination, "busy").unwrap(),
            MeetingDeletionOutcome::DeferredActive
        );
        assert!(directory.join("meeting.json").exists());
        assert!(
            !receipt_path(&storage, "busy").unwrap().exists(),
            "a refusal wrote a receipt"
        );
    }

    #[test]
    fn an_interrupted_removal_completes_rather_than_restarting() {
        let (_temp, storage) = storage();
        let directory = fixture(&storage, "torn");
        let coordination = MeetingStorageCoordination::default();

        // Simulate a crash immediately after the receipt was written and before
        // any file was removed.
        let path = receipt_path(&storage, "torn").unwrap();
        let receipt = MeetingDeletionReceipt {
            schema: MeetingDeletionSchema::V1,
            meeting_id: "torn".into(),
            state: MeetingDeletionState::Deleting,
            artifacts: take_inventory(&directory).unwrap(),
        };
        write_receipt(&path, &receipt, true).unwrap();

        assert_eq!(
            delete_meeting_wholly(&storage, &coordination, "torn").unwrap(),
            MeetingDeletionOutcome::RecoveredRemoval
        );
        assert!(!directory.exists());
        assert_eq!(
            load_receipt(&path).unwrap().state,
            MeetingDeletionState::Removed
        );
    }

    #[test]
    fn a_half_removed_meeting_can_never_be_read_as_intact() {
        let (_temp, storage) = storage();
        let directory = fixture(&storage, "half");
        let path = receipt_path(&storage, "half").unwrap();
        let receipt = MeetingDeletionReceipt {
            schema: MeetingDeletionSchema::V1,
            meeting_id: "half".into(),
            state: MeetingDeletionState::Deleting,
            artifacts: take_inventory(&directory).unwrap(),
        };
        write_receipt(&path, &receipt, true).unwrap();

        // Drive only the first transition, then stop where a crash would.
        let mut staged = receipt;
        fs::remove_file(directory.join("meeting.json")).unwrap();
        staged.state = MeetingDeletionState::Staged;
        write_receipt(&path, &staged, false).unwrap();

        assert!(
            directory.exists(),
            "precondition: the directory is still present"
        );
        assert!(
            load_meeting(&directory).is_err(),
            "a staged meeting still loaded as a meeting"
        );
    }

    #[test]
    fn retention_skips_a_meeting_that_is_mid_deletion_instead_of_quarantining_it() {
        let (_temp, storage) = storage();
        let directory = fixture(&storage, "middeletion");
        let path = receipt_path(&storage, "middeletion").unwrap();
        let receipt = MeetingDeletionReceipt {
            schema: MeetingDeletionSchema::V1,
            meeting_id: "middeletion".into(),
            state: MeetingDeletionState::Staged,
            artifacts: take_inventory(&directory).unwrap(),
        };
        write_receipt(&path, &receipt, true).unwrap();
        fs::remove_file(directory.join("meeting.json")).unwrap();

        let outcomes = crate::retention::execute_due_retention(&storage, 0).unwrap();
        assert!(
            outcomes.is_empty(),
            "retention reported a deleting meeting: {outcomes:?}"
        );
    }

    #[test]
    fn startup_reconciliation_finishes_what_a_crash_left() {
        let (_temp, storage) = storage();
        let directory = fixture(&storage, "resumed");
        let coordination = MeetingStorageCoordination::default();
        let path = receipt_path(&storage, "resumed").unwrap();
        let receipt = MeetingDeletionReceipt {
            schema: MeetingDeletionSchema::V1,
            meeting_id: "resumed".into(),
            state: MeetingDeletionState::Deleting,
            artifacts: take_inventory(&directory).unwrap(),
        };
        write_receipt(&path, &receipt, true).unwrap();

        let completed = reconcile_pending_meeting_deletions(&storage, &coordination).unwrap();
        assert_eq!(completed, vec!["resumed".to_string()]);
        assert!(!directory.exists());
        assert!(pending_deletion_ids(&storage).unwrap().is_empty());
    }

    #[test]
    fn deleting_the_same_meeting_twice_is_idempotent() {
        let (_temp, storage) = storage();
        fixture(&storage, "twice");
        let coordination = MeetingStorageCoordination::default();
        assert_eq!(
            delete_meeting_wholly(&storage, &coordination, "twice").unwrap(),
            MeetingDeletionOutcome::MeetingRemoved
        );
        assert_eq!(
            delete_meeting_wholly(&storage, &coordination, "twice").unwrap(),
            MeetingDeletionOutcome::AlreadyRemoved
        );
    }

    #[test]
    fn a_symlink_inside_meeting_storage_is_refused_rather_than_followed() {
        let (_temp, storage) = storage();
        let directory = fixture(&storage, "linked");
        let outside = storage.path().join("outside.txt");
        fs::write(&outside, b"not part of this meeting").unwrap();
        std::os::unix::fs::symlink(&outside, directory.join("escape.json")).unwrap();

        let coordination = MeetingStorageCoordination::default();
        assert!(matches!(
            delete_meeting_wholly(&storage, &coordination, "linked"),
            Err(MeetingDeletionError::UnsafeEntry)
        ));
        assert!(outside.exists(), "the symlink target was removed");
        assert!(directory.exists(), "a refusal removed the meeting anyway");
    }

    #[test]
    fn an_absent_meeting_is_not_reported_as_a_successful_deletion() {
        let (_temp, storage) = storage();
        let coordination = MeetingStorageCoordination::default();
        assert!(matches!(
            delete_meeting_wholly(&storage, &coordination, "never-existed"),
            Err(MeetingDeletionError::NoSuchMeeting)
        ));
    }

    #[test]
    fn a_receipt_naming_another_meeting_is_refused() {
        let (_temp, storage) = storage();
        let directory = fixture(&storage, "mismatch");
        let path = receipt_path(&storage, "mismatch").unwrap();
        let receipt = MeetingDeletionReceipt {
            schema: MeetingDeletionSchema::V1,
            meeting_id: "a-different-meeting".into(),
            state: MeetingDeletionState::Deleting,
            artifacts: Vec::new(),
        };
        write_receipt(&path, &receipt, true).unwrap();

        let coordination = MeetingStorageCoordination::default();
        assert!(matches!(
            delete_meeting_wholly(&storage, &coordination, "mismatch"),
            Err(MeetingDeletionError::MalformedReceipt)
        ));
        assert!(directory.join("meeting.json").exists());
    }

    #[test]
    fn a_file_larger_than_the_read_buffer_digests_correctly() {
        // The inventory streams in 64 KiB blocks instead of reading whole files,
        // because a meeting's capture legs are the largest thing it walks and an
        // hour of them is gigabytes. A chunked digest that mishandled a block
        // boundary would still pass every other test here, since every other
        // fixture file is a few bytes.
        let (_temp, storage) = storage();
        let directory = fixture(&storage, "large");
        let payload: Vec<u8> = (0..(64 * 1024 * 2 + 517)).map(|i| (i % 251) as u8).collect();
        fs::write(directory.join("capture/mic.wav"), &payload).unwrap();

        let expected = format!("{:x}", Sha256::digest(&payload));
        let inventory = take_inventory(&directory).unwrap();
        let recorded = inventory
            .iter()
            .find(|artifact| artifact.relative_name == "capture/mic.wav")
            .unwrap();
        assert_eq!(recorded.sha256, expected);
        assert_eq!(recorded.byte_size, payload.len() as u64);
    }
}

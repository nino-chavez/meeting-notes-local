//! Durable, source-bound transcript retry candidates.
//!
//! A retry is an immutable transcript revision next to the current revision.
//! Creating one never changes `meeting.json`.  An operator can keep the
//! current transcript or promote the candidate later; both decisions are
//! recorded in the candidate receipt and can be resumed after a crash.

use std::fs;
use std::io;
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use thiserror::Error;
use uuid::Uuid;

use crate::meeting::{
    load_meeting, read_private_bytes, require_private_directory, valid_opaque_id,
    verify_artifact_ref, verify_record_artifacts, write_meeting, ArtifactRef, AudioState,
    MeetingError, MeetingLifecycle, MeetingRecord, MAX_RECEIPT_BYTES,
};
use crate::meeting_coordination::{MeetingCoordinationError, MeetingStorageCoordination};
use crate::storage::{create_private_dir, durable_create_new, durable_replace, StorageRoot};

const RETRY_DIRECTORY: &str = "transcript-retry";
const RECEIPT_FILE: &str = "receipt.json";
const MAX_TRANSCRIPT_BYTES: u64 = 16 * 1024 * 1024;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum TranscriptRetryState {
    CandidateAvailableForComparison,
    CurrentKept,
    CandidatePromoted,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TranscriptRetryOutcome {
    CandidateAvailableForComparison,
    CurrentKept,
    CandidatePromoted,
}

impl From<TranscriptRetryState> for TranscriptRetryOutcome {
    fn from(state: TranscriptRetryState) -> Self {
        match state {
            TranscriptRetryState::CandidateAvailableForComparison => {
                Self::CandidateAvailableForComparison
            }
            TranscriptRetryState::CurrentKept => Self::CurrentKept,
            TranscriptRetryState::CandidatePromoted => Self::CandidatePromoted,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum TranscriptRetryCandidateSchema {
    #[serde(rename = "transcript-retry-candidate/1")]
    V1,
}

/// The durable receipt for one immutable candidate and its operator decision.
/// The four source digests are captured before the worker result is admitted.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct TranscriptRetryCandidate {
    pub schema: TranscriptRetryCandidateSchema,
    pub operation_id: Uuid,
    pub meeting_id: String,
    pub state: TranscriptRetryState,
    pub source_transcript_sha256: String,
    pub capture_session_sha256: String,
    pub microphone_audio_sha256: String,
    pub system_audio_sha256: String,
    pub candidate_transcript: ArtifactRef,
}

#[derive(Debug, Error)]
pub enum TranscriptRetryError {
    #[error("meeting storage coordination is unavailable")]
    Coordination(#[from] MeetingCoordinationError),
    #[error(transparent)]
    Meeting(#[from] MeetingError),
    #[error(transparent)]
    Io(#[from] io::Error),
    #[error(transparent)]
    Json(#[from] serde_json::Error),
    #[error("no such meeting")]
    NoSuchMeeting,
    #[error("meeting has no current transcript")]
    NoCurrentTranscript,
    #[error("meeting audio is released and cannot authorize a retry")]
    AudioReleased,
    #[error("retry candidate is missing or changed")]
    CandidateChanged,
    #[error("retry candidate belongs to another meeting")]
    CrossMeetingCandidate,
    #[error("retry operation receipt is malformed or incomplete")]
    MalformedOperation,
    #[error("retry operation already exists with different bytes")]
    ConflictingOperation,
    #[error("retry source capture has changed or is stale")]
    StaleSource,
    #[error("retry candidate is not in an available state")]
    InvalidState,
}

/// The only capability that can admit or decide a transcript retry.  The
/// caller holds the same process-local meeting lease used by capture/storage.
pub struct TranscriptRetryAuthority<'a> {
    pub(crate) storage: &'a StorageRoot,
    pub(crate) coordination: &'a MeetingStorageCoordination,
}

impl<'a> TranscriptRetryAuthority<'a> {
    pub fn new(storage: &'a StorageRoot, coordination: &'a MeetingStorageCoordination) -> Self {
        Self {
            storage,
            coordination,
        }
    }

    /// Stores an immutable candidate and source binding. This does not write
    /// or replace the meeting record's current transcript pointer.
    pub fn create_candidate(
        &self,
        meeting_id: &str,
        operation_id: Uuid,
        candidate_bytes: &[u8],
    ) -> Result<TranscriptRetryOutcome, TranscriptRetryError> {
        let _lease = self.coordination.acquire(meeting_id)?;
        let meeting_dir = self.meeting_dir(meeting_id)?;
        let meeting = self.load_source(&meeting_dir, meeting_id)?;
        if candidate_bytes.is_empty() || candidate_bytes.len() as u64 > MAX_TRANSCRIPT_BYTES {
            return Err(TranscriptRetryError::CandidateChanged);
        }

        let operation_dir = self.operation_dir(&meeting_dir, operation_id)?;
        if path_exists(&operation_dir)? {
            let candidate = load_receipt(&operation_dir, operation_id)?;
            self.validate_receipt(&meeting_dir, &meeting, &candidate, meeting_id)?;
            if candidate.candidate_transcript.sha256 != digest_bytes(candidate_bytes) {
                return Err(TranscriptRetryError::ConflictingOperation);
            }
            verify_artifact_ref(&meeting_dir, &candidate.candidate_transcript)?;
            return Ok(candidate.state.into());
        }

        let current = meeting
            .artifacts
            .current_transcript
            .as_ref()
            .ok_or(TranscriptRetryError::NoCurrentTranscript)?;
        let capture_session = meeting
            .artifacts
            .capture_session
            .as_ref()
            .ok_or(TranscriptRetryError::StaleSource)?;
        let microphone = meeting
            .artifacts
            .microphone_audio
            .as_ref()
            .ok_or(TranscriptRetryError::StaleSource)?;
        let system = meeting
            .artifacts
            .system_audio
            .as_ref()
            .ok_or(TranscriptRetryError::StaleSource)?;
        let candidate_sha = digest_bytes(candidate_bytes);
        let candidate = TranscriptRetryCandidate {
            schema: TranscriptRetryCandidateSchema::V1,
            operation_id,
            meeting_id: meeting_id.to_owned(),
            state: TranscriptRetryState::CandidateAvailableForComparison,
            source_transcript_sha256: current.sha256.clone(),
            capture_session_sha256: capture_session.sha256.clone(),
            microphone_audio_sha256: microphone.sha256.clone(),
            system_audio_sha256: system.sha256.clone(),
            candidate_transcript: ArtifactRef {
                relative_path: format!("transcript/{candidate_sha}.json"),
                sha256: candidate_sha,
            },
        };
        validate_candidate_shape(&candidate)?;

        let transcript_dir = meeting_dir.join("transcript");
        create_private_dir(&transcript_dir)?;
        let candidate_path = meeting_dir.join(&candidate.candidate_transcript.relative_path);
        match fs::symlink_metadata(&candidate_path) {
            Ok(_) => {
                verify_artifact_ref(&meeting_dir, &candidate.candidate_transcript)
                    .map_err(|_| TranscriptRetryError::CandidateChanged)?;
                if read_private_bytes(&candidate_path, MAX_TRANSCRIPT_BYTES)? != candidate_bytes {
                    return Err(TranscriptRetryError::CandidateChanged);
                }
            }
            Err(error) if error.kind() == io::ErrorKind::NotFound => {
                durable_create_new(&candidate_path, candidate_bytes)?;
            }
            Err(error) => return Err(error.into()),
        }

        create_private_dir(&meeting_dir.join(RETRY_DIRECTORY))?;
        create_private_dir(&operation_dir)?;
        let receipt_path = operation_dir.join(RECEIPT_FILE);
        durable_create_new(&receipt_path, &serde_json::to_vec_pretty(&candidate)?)?;
        Ok(TranscriptRetryOutcome::CandidateAvailableForComparison)
    }

    pub fn keep_current(
        &self,
        meeting_id: &str,
        operation_id: Uuid,
    ) -> Result<TranscriptRetryOutcome, TranscriptRetryError> {
        let _lease = self.coordination.acquire(meeting_id)?;
        let meeting_dir = self.meeting_dir(meeting_id)?;
        let meeting = self.load_source(&meeting_dir, meeting_id)?;
        let operation_dir = self.operation_dir(&meeting_dir, operation_id)?;
        let mut candidate = load_receipt(&operation_dir, operation_id)?;
        self.validate_receipt(&meeting_dir, &meeting, &candidate, meeting_id)?;
        if candidate.state == TranscriptRetryState::CandidateAvailableForComparison
            && meeting.artifacts.current_transcript.as_ref()
                == Some(&candidate.candidate_transcript)
        {
            candidate.state = TranscriptRetryState::CandidatePromoted;
            write_receipt(&operation_dir, &candidate)?;
            return Ok(TranscriptRetryOutcome::CandidatePromoted);
        }
        if candidate.state != TranscriptRetryState::CandidateAvailableForComparison {
            return Ok(candidate.state.into());
        }
        candidate.state = TranscriptRetryState::CurrentKept;
        write_receipt(&operation_dir, &candidate)?;
        Ok(TranscriptRetryOutcome::CurrentKept)
    }

    /// Promotes only the candidate pointer and the lifecycle needed to make
    /// the new transcript readable. Existing note files remain on disk; their
    /// pointer is cleared because they bind the prior transcript.
    pub fn promote_candidate(
        &self,
        meeting_id: &str,
        operation_id: Uuid,
    ) -> Result<TranscriptRetryOutcome, TranscriptRetryError> {
        let _lease = self.coordination.acquire(meeting_id)?;
        let meeting_dir = self.meeting_dir(meeting_id)?;
        let mut meeting = self.load_source(&meeting_dir, meeting_id)?;
        let operation_dir = self.operation_dir(&meeting_dir, operation_id)?;
        let mut candidate = load_receipt(&operation_dir, operation_id)?;
        self.validate_receipt(&meeting_dir, &meeting, &candidate, meeting_id)?;
        if candidate.state == TranscriptRetryState::CurrentKept {
            return Ok(TranscriptRetryOutcome::CurrentKept);
        }
        if candidate.state == TranscriptRetryState::CandidatePromoted {
            if meeting.artifacts.current_transcript.as_ref()
                != Some(&candidate.candidate_transcript)
            {
                return Err(TranscriptRetryError::MalformedOperation);
            }
            return Ok(TranscriptRetryOutcome::CandidatePromoted);
        }

        // A crash after meeting.json was published but before the terminal
        // receipt is durable is completed here, never rolled back.
        if meeting.artifacts.current_transcript.as_ref() == Some(&candidate.candidate_transcript) {
            candidate.state = TranscriptRetryState::CandidatePromoted;
            write_receipt(&operation_dir, &candidate)?;
            return Ok(TranscriptRetryOutcome::CandidatePromoted);
        }

        let current = meeting
            .artifacts
            .current_transcript
            .as_ref()
            .ok_or(TranscriptRetryError::NoCurrentTranscript)?;
        if current.sha256 != candidate.source_transcript_sha256 {
            return Err(TranscriptRetryError::StaleSource);
        }
        meeting.artifacts.current_transcript = Some(candidate.candidate_transcript.clone());
        meeting.artifacts.current_note = None;
        meeting.lifecycle = MeetingLifecycle::TranscriptReady;
        write_meeting(&meeting_dir, &meeting)?;
        candidate.state = TranscriptRetryState::CandidatePromoted;
        write_receipt(&operation_dir, &candidate)?;
        Ok(TranscriptRetryOutcome::CandidatePromoted)
    }

    /// Reads a candidate for comparison without changing any durable state.
    pub fn inspect_candidate(
        &self,
        meeting_id: &str,
        operation_id: Uuid,
    ) -> Result<TranscriptRetryCandidate, TranscriptRetryError> {
        let meeting_dir = self.meeting_dir(meeting_id)?;
        let meeting = self.load_source(&meeting_dir, meeting_id)?;
        let candidate = load_receipt(
            &self.operation_dir(&meeting_dir, operation_id)?,
            operation_id,
        )?;
        self.validate_receipt(&meeting_dir, &meeting, &candidate, meeting_id)?;
        Ok(candidate)
    }

    fn meeting_dir(&self, meeting_id: &str) -> Result<PathBuf, TranscriptRetryError> {
        let path = self
            .storage
            .resolve(&Path::new("meetings").join(meeting_id))
            .map_err(|_| TranscriptRetryError::NoSuchMeeting)?;
        match fs::symlink_metadata(&path) {
            Ok(_) => Ok(path),
            Err(error) if error.kind() == io::ErrorKind::NotFound => {
                Err(TranscriptRetryError::NoSuchMeeting)
            }
            Err(error) => Err(error.into()),
        }
    }

    fn operation_dir(
        &self,
        meeting_dir: &Path,
        operation_id: Uuid,
    ) -> Result<PathBuf, TranscriptRetryError> {
        let root = meeting_dir.join(RETRY_DIRECTORY);
        match fs::symlink_metadata(&root) {
            Ok(_) => require_private_directory(&root)?,
            Err(error) if error.kind() == io::ErrorKind::NotFound => {}
            Err(error) => return Err(error.into()),
        }
        let path = root.join(operation_id.to_string());
        if let Ok(_) = fs::symlink_metadata(&path) {
            require_private_directory(&path)?;
        }
        Ok(path)
    }

    fn load_source(
        &self,
        meeting_dir: &Path,
        meeting_id: &str,
    ) -> Result<MeetingRecord, TranscriptRetryError> {
        let meeting = load_meeting(meeting_dir)?;
        if meeting.meeting_id != meeting_id {
            return Err(TranscriptRetryError::CrossMeetingCandidate);
        }
        if meeting.retention.state != AudioState::Retained {
            return Err(TranscriptRetryError::AudioReleased);
        }
        verify_record_artifacts(meeting_dir, &meeting)?;
        Ok(meeting)
    }

    fn validate_receipt(
        &self,
        meeting_dir: &Path,
        meeting: &MeetingRecord,
        candidate: &TranscriptRetryCandidate,
        meeting_id: &str,
    ) -> Result<(), TranscriptRetryError> {
        validate_candidate_shape(candidate)?;
        if candidate.meeting_id != meeting_id || candidate.meeting_id != meeting.meeting_id {
            return Err(TranscriptRetryError::CrossMeetingCandidate);
        }
        let current = meeting
            .artifacts
            .current_transcript
            .as_ref()
            .ok_or(TranscriptRetryError::NoCurrentTranscript)?;
        let capture = meeting
            .artifacts
            .capture_session
            .as_ref()
            .ok_or(TranscriptRetryError::StaleSource)?;
        let microphone = meeting
            .artifacts
            .microphone_audio
            .as_ref()
            .ok_or(TranscriptRetryError::StaleSource)?;
        let system = meeting
            .artifacts
            .system_audio
            .as_ref()
            .ok_or(TranscriptRetryError::StaleSource)?;
        if candidate.state == TranscriptRetryState::CandidatePromoted {
            if current != &candidate.candidate_transcript {
                return Err(TranscriptRetryError::StaleSource);
            }
        } else if current == &candidate.candidate_transcript {
            // Meeting publication may have won a crash race with the receipt.
        } else if current.sha256 != candidate.source_transcript_sha256
            || capture.sha256 != candidate.capture_session_sha256
            || microphone.sha256 != candidate.microphone_audio_sha256
            || system.sha256 != candidate.system_audio_sha256
        {
            return Err(TranscriptRetryError::StaleSource);
        }
        verify_artifact_ref(meeting_dir, &candidate.candidate_transcript)
            .map_err(|_| TranscriptRetryError::CandidateChanged)
    }
}

fn path_exists(path: &Path) -> Result<bool, TranscriptRetryError> {
    match fs::symlink_metadata(path) {
        Ok(_) => {
            require_private_directory(path)?;
            Ok(true)
        }
        Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(false),
        Err(error) => Err(error.into()),
    }
}

fn load_receipt(
    operation_dir: &Path,
    operation_id: Uuid,
) -> Result<TranscriptRetryCandidate, TranscriptRetryError> {
    require_private_directory(operation_dir)
        .map_err(|_| TranscriptRetryError::MalformedOperation)?;
    let path = operation_dir.join(RECEIPT_FILE);
    let bytes = read_private_bytes(&path, MAX_RECEIPT_BYTES)
        .map_err(|_| TranscriptRetryError::MalformedOperation)?;
    let candidate: TranscriptRetryCandidate =
        serde_json::from_slice(&bytes).map_err(|_| TranscriptRetryError::MalformedOperation)?;
    validate_candidate_shape(&candidate)?;
    if candidate.operation_id != operation_id {
        return Err(TranscriptRetryError::MalformedOperation);
    }
    Ok(candidate)
}

fn write_receipt(
    operation_dir: &Path,
    candidate: &TranscriptRetryCandidate,
) -> Result<(), TranscriptRetryError> {
    durable_replace(
        operation_dir.join(RECEIPT_FILE).as_path(),
        &serde_json::to_vec_pretty(candidate)?,
    )?;
    Ok(())
}

fn validate_candidate_shape(
    candidate: &TranscriptRetryCandidate,
) -> Result<(), TranscriptRetryError> {
    if candidate.schema != TranscriptRetryCandidateSchema::V1
        || !valid_opaque_id(&candidate.meeting_id)
        || !valid_sha256(&candidate.source_transcript_sha256)
        || !valid_sha256(&candidate.capture_session_sha256)
        || !valid_sha256(&candidate.microphone_audio_sha256)
        || !valid_sha256(&candidate.system_audio_sha256)
        || candidate.candidate_transcript.relative_path
            != format!("transcript/{}.json", candidate.candidate_transcript.sha256)
        || !valid_sha256(&candidate.candidate_transcript.sha256)
    {
        return Err(TranscriptRetryError::MalformedOperation);
    }
    Ok(())
}

fn valid_sha256(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn digest_bytes(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::meeting::{
        artifact_ref, AudioRetention, AudioRetentionRule, MeetingArtifacts, MeetingSchema,
        MAX_MEETING_RECORD_BYTES,
    };
    use crate::storage::StorageRoot;
    use std::os::unix::fs::OpenOptionsExt;
    use tempfile::TempDir;

    struct Fixture {
        _temp: TempDir,
        storage: StorageRoot,
        coordination: MeetingStorageCoordination,
        meeting_dir: PathBuf,
        source: Vec<u8>,
    }

    fn private_file(path: &Path, bytes: &[u8]) {
        let mut file = std::fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .mode(0o600)
            .open(path)
            .unwrap();
        std::io::Write::write_all(&mut file, bytes).unwrap();
        file.sync_all().unwrap();
    }

    fn fixture() -> Fixture {
        let temp = TempDir::new().unwrap();
        let repo = temp.path().join("repo");
        create_private_dir(&repo).unwrap();
        let storage = StorageRoot::create(&temp.path().join("app-data"), &repo).unwrap();
        let meeting_dir = storage.path().join("meetings/meeting-a");
        create_private_dir(&meeting_dir).unwrap();
        create_private_dir(&meeting_dir.join("capture")).unwrap();
        create_private_dir(&meeting_dir.join("transcript")).unwrap();
        let source = br#"{"schema":"capture-transcript/1"}"#.to_vec();
        private_file(&meeting_dir.join("attempt.json"), b"attempt");
        private_file(&meeting_dir.join("ownership.json"), b"owner");
        private_file(&meeting_dir.join("capture/session.json"), b"capture");
        private_file(&meeting_dir.join("capture/mic.wav"), &[1; 64]);
        private_file(&meeting_dir.join("capture/system.wav"), &[2; 64]);
        let src_path = meeting_dir
            .join("transcript")
            .join(format!("{}.json", digest_bytes(&source)));
        private_file(&src_path, &source);
        let rule = AudioRetentionRule::UntilManualDeletion;
        let meeting = MeetingRecord {
            schema: MeetingSchema::V2,
            meeting_id: "meeting-a".into(),
            lifecycle: MeetingLifecycle::TranscriptReady,
            retention: AudioRetention {
                policy_sha256: crate::meeting::retention_policy_sha256(&rule),
                rule,
                next_deletion_at_epoch_seconds: None,
                state: AudioState::Retained,
                deletion_receipt: None,
            },
            artifacts: MeetingArtifacts {
                attempt: artifact_ref(&meeting_dir, "attempt.json").unwrap(),
                ownership: Some(artifact_ref(&meeting_dir, "ownership.json").unwrap()),
                capture_session: Some(artifact_ref(&meeting_dir, "capture/session.json").unwrap()),
                microphone_audio: Some(artifact_ref(&meeting_dir, "capture/mic.wav").unwrap()),
                system_audio: Some(artifact_ref(&meeting_dir, "capture/system.wav").unwrap()),
                current_transcript: Some(
                    artifact_ref(
                        &meeting_dir,
                        &format!("transcript/{}.json", digest_bytes(&source)),
                    )
                    .unwrap(),
                ),
                current_note: None,
            },
            pending_storage_operation: None,
        };
        write_meeting(&meeting_dir, &meeting).unwrap();
        Fixture {
            _temp: temp,
            storage,
            coordination: MeetingStorageCoordination::default(),
            meeting_dir,
            source,
        }
    }

    #[test]
    fn candidate_is_available_without_pointer_mutation_and_can_be_kept() {
        let fixture = fixture();
        let authority = TranscriptRetryAuthority::new(&fixture.storage, &fixture.coordination);
        let before = read_private_bytes(
            &fixture.meeting_dir.join("meeting.json"),
            MAX_MEETING_RECORD_BYTES,
        )
        .unwrap();
        let id = Uuid::new_v4();
        assert_eq!(
            authority
                .create_candidate("meeting-a", id, b"candidate")
                .unwrap(),
            TranscriptRetryOutcome::CandidateAvailableForComparison
        );
        assert_eq!(
            read_private_bytes(
                &fixture.meeting_dir.join("meeting.json"),
                MAX_MEETING_RECORD_BYTES
            )
            .unwrap(),
            before
        );
        assert_eq!(
            authority.keep_current("meeting-a", id).unwrap(),
            TranscriptRetryOutcome::CurrentKept
        );
        assert_eq!(
            authority.keep_current("meeting-a", id).unwrap(),
            TranscriptRetryOutcome::CurrentKept
        );
    }

    #[test]
    fn promotion_changes_only_current_pointer_and_preserves_bytes() {
        let fixture = fixture();
        let authority = TranscriptRetryAuthority::new(&fixture.storage, &fixture.coordination);
        let id = Uuid::new_v4();
        let candidate = b"candidate transcript";
        let source_path = fixture
            .meeting_dir
            .join("transcript")
            .join(format!("{}.json", digest_bytes(&fixture.source)));
        assert_eq!(
            authority
                .create_candidate("meeting-a", id, candidate)
                .unwrap(),
            TranscriptRetryOutcome::CandidateAvailableForComparison
        );
        assert_eq!(
            authority.promote_candidate("meeting-a", id).unwrap(),
            TranscriptRetryOutcome::CandidatePromoted
        );
        assert_eq!(
            read_private_bytes(&source_path, MAX_TRANSCRIPT_BYTES).unwrap(),
            fixture.source
        );
        let meeting = load_meeting(&fixture.meeting_dir).unwrap();
        assert_eq!(
            meeting.artifacts.current_transcript.unwrap().sha256,
            digest_bytes(candidate)
        );
        assert_eq!(
            authority.promote_candidate("meeting-a", id).unwrap(),
            TranscriptRetryOutcome::CandidatePromoted
        );
    }

    #[test]
    fn promotion_receipt_recovers_after_meeting_publish() {
        let fixture = fixture();
        let authority = TranscriptRetryAuthority::new(&fixture.storage, &fixture.coordination);
        let id = Uuid::new_v4();
        authority
            .create_candidate("meeting-a", id, b"candidate")
            .unwrap();
        let receipt = authority.inspect_candidate("meeting-a", id).unwrap();
        let mut meeting = load_meeting(&fixture.meeting_dir).unwrap();
        meeting.artifacts.current_transcript = Some(receipt.candidate_transcript);
        meeting.lifecycle = MeetingLifecycle::TranscriptReady;
        write_meeting(&fixture.meeting_dir, &meeting).unwrap();
        assert_eq!(
            authority.promote_candidate("meeting-a", id).unwrap(),
            TranscriptRetryOutcome::CandidatePromoted
        );
    }

    #[test]
    fn released_audio_and_stale_source_fail_closed() {
        let fixture = fixture();
        let authority = TranscriptRetryAuthority::new(&fixture.storage, &fixture.coordination);
        let id = Uuid::new_v4();
        authority
            .create_candidate("meeting-a", id, b"candidate")
            .unwrap();
        let mut meeting = load_meeting(&fixture.meeting_dir).unwrap();
        create_private_dir(&fixture.meeting_dir.join("deletion")).unwrap();
        private_file(
            &fixture.meeting_dir.join("deletion/audio-deletion.json"),
            b"released",
        );
        meeting.retention.state = AudioState::Released;
        meeting.retention.deletion_receipt =
            Some(artifact_ref(&fixture.meeting_dir, "deletion/audio-deletion.json").unwrap());
        write_meeting(&fixture.meeting_dir, &meeting).unwrap();
        assert!(matches!(
            authority.create_candidate("meeting-a", Uuid::new_v4(), b"other"),
            Err(TranscriptRetryError::AudioReleased)
        ));
    }
}

use std::fs::{self, File, OpenOptions};
use std::io::{self, Read};
use std::os::unix::fs::{OpenOptionsExt, PermissionsExt};
use std::path::{Component, Path, PathBuf};

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use thiserror::Error;

use crate::storage::durable_replace;

pub const MAX_MEETING_RECORD_BYTES: u64 = 256 * 1024;
pub const MAX_RECEIPT_BYTES: u64 = 256 * 1024;

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct MeetingRecord {
    pub schema: MeetingSchema,
    pub meeting_id: String,
    pub lifecycle: MeetingLifecycle,
    pub retention: AudioRetention,
    pub artifacts: MeetingArtifacts,
    pub pending_storage_operation: Option<PendingStorageOperation>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum MeetingSchema {
    #[serde(rename = "meeting/2")]
    V2,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum MeetingLifecycle {
    Incomplete,
    Captured,
    TranscriptReady,
    TranscriptionFailed,
    SummaryFailed,
    Ready,
    RecoveredInterrupted,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct AudioRetention {
    pub rule: AudioRetentionRule,
    pub policy_sha256: String,
    pub next_deletion_at_epoch_seconds: Option<u64>,
    pub state: AudioState,
    pub deletion_receipt: Option<ArtifactRef>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "kebab-case", deny_unknown_fields)]
pub enum AudioRetentionRule {
    DeleteAfter { seconds: u64 },
    UntilManualDeletion,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum AudioState {
    NeverCreated,
    Retained,
    Deleting,
    Released,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct MeetingArtifacts {
    pub attempt: ArtifactRef,
    pub ownership: Option<ArtifactRef>,
    pub capture_session: Option<ArtifactRef>,
    pub microphone_audio: Option<ArtifactRef>,
    pub system_audio: Option<ArtifactRef>,
    pub current_transcript: Option<ArtifactRef>,
    pub current_note: Option<NoteRevisionRef>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct NoteRevisionRef {
    pub json: ArtifactRef,
    pub markdown: ArtifactRef,
    pub source_transcript_sha256: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ArtifactRef {
    pub relative_path: String,
    pub sha256: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum PendingStorageOperation {
    #[serde(rename = "audio-deletion/1")]
    AudioDeletionV1,
}

#[derive(Debug, Error)]
pub enum MeetingError {
    #[error("meeting record is malformed: {0}")]
    Malformed(&'static str),
    #[error("meeting artifact is missing or changed")]
    ArtifactMismatch,
    #[error("private meeting storage is invalid")]
    InvalidPrivateStorage,
    #[error(transparent)]
    Io(#[from] io::Error),
    #[error(transparent)]
    Json(#[from] serde_json::Error),
}

impl MeetingRecord {
    pub fn validate(&self, directory_id: &str) -> Result<(), MeetingError> {
        if !valid_opaque_id(directory_id) || self.meeting_id != directory_id {
            return Err(MeetingError::Malformed("meeting identifier mismatch"));
        }
        if self.retention.policy_sha256 != retention_policy_sha256(&self.retention.rule) {
            return Err(MeetingError::Malformed("retention policy digest mismatch"));
        }
        match self.retention.rule {
            AudioRetentionRule::DeleteAfter { seconds } => {
                if seconds == 0 || self.retention.next_deletion_at_epoch_seconds.is_none() {
                    return Err(MeetingError::Malformed("invalid automatic retention rule"));
                }
            }
            AudioRetentionRule::UntilManualDeletion => {
                if self.retention.next_deletion_at_epoch_seconds.is_some() {
                    return Err(MeetingError::Malformed("manual retention has a deadline"));
                }
            }
        }

        validate_ref(&self.artifacts.attempt, "attempt.json")?;
        if let Some(ownership) = &self.artifacts.ownership {
            validate_ref(ownership, "ownership.json")?;
        }
        if let Some(session) = &self.artifacts.capture_session {
            validate_ref(session, "capture/session.json")?;
        }
        if let Some(mic) = &self.artifacts.microphone_audio {
            validate_ref(mic, "capture/mic.wav")?;
        }
        if let Some(system) = &self.artifacts.system_audio {
            validate_ref(system, "capture/system.wav")?;
        }
        if let Some(transcript) = &self.artifacts.current_transcript {
            validate_digest_named_ref(transcript, "transcript", "json")?;
        }
        if let Some(note) = &self.artifacts.current_note {
            validate_digest_named_ref(&note.json, "notes", "json")?;
            validate_sha256(&note.source_transcript_sha256)?;
            let markdown_path = format!("notes/{}.md", note.json.sha256);
            validate_ref(&note.markdown, &markdown_path)?;
        }

        let complete_capture = self.artifacts.capture_session.is_some()
            && self.artifacts.microphone_audio.is_some()
            && self.artifacts.system_audio.is_some();
        let any_capture = self.artifacts.capture_session.is_some()
            || self.artifacts.microphone_audio.is_some()
            || self.artifacts.system_audio.is_some();
        let any_audio =
            self.artifacts.microphone_audio.is_some() || self.artifacts.system_audio.is_some();
        let transcript = self.artifacts.current_transcript.is_some();
        let note = self.artifacts.current_note.is_some();

        match self.lifecycle {
            MeetingLifecycle::Incomplete => {
                if any_capture || transcript || note {
                    return Err(MeetingError::Malformed(
                        "incomplete meeting points to committed artifacts",
                    ));
                }
            }
            MeetingLifecycle::Captured | MeetingLifecycle::TranscriptionFailed => {
                if !complete_capture || transcript || note || self.artifacts.ownership.is_none() {
                    return Err(MeetingError::Malformed(
                        "invalid captured meeting artifacts",
                    ));
                }
            }
            MeetingLifecycle::TranscriptReady | MeetingLifecycle::SummaryFailed => {
                if !complete_capture || !transcript || note || self.artifacts.ownership.is_none() {
                    return Err(MeetingError::Malformed(
                        "invalid transcript-ready artifacts",
                    ));
                }
            }
            MeetingLifecycle::Ready => {
                if !complete_capture || !transcript || !note || self.artifacts.ownership.is_none() {
                    return Err(MeetingError::Malformed("invalid ready meeting artifacts"));
                }
                let current = self
                    .artifacts
                    .current_transcript
                    .as_ref()
                    .expect("checked above");
                let source = &self
                    .artifacts
                    .current_note
                    .as_ref()
                    .expect("checked above")
                    .source_transcript_sha256;
                if source != &current.sha256 {
                    return Err(MeetingError::Malformed("note binds another transcript"));
                }
            }
            MeetingLifecycle::RecoveredInterrupted => {
                if transcript || note {
                    return Err(MeetingError::Malformed(
                        "interrupted meeting points to derived artifacts",
                    ));
                }
                if any_audio && self.artifacts.capture_session.is_none() {
                    return Err(MeetingError::Malformed(
                        "partial audio lacks a capture session receipt",
                    ));
                }
            }
        }

        match self.retention.state {
            AudioState::NeverCreated => {
                if any_audio
                    || self.retention.deletion_receipt.is_some()
                    || self.pending_storage_operation.is_some()
                {
                    return Err(MeetingError::Malformed("invalid never-created audio state"));
                }
            }
            AudioState::Retained => {
                if !any_audio
                    || self.retention.deletion_receipt.is_some()
                    || self.pending_storage_operation.is_some()
                {
                    return Err(MeetingError::Malformed("invalid retained audio state"));
                }
            }
            AudioState::Deleting => {
                if !any_audio
                    || self.retention.deletion_receipt.is_some()
                    || self.pending_storage_operation
                        != Some(PendingStorageOperation::AudioDeletionV1)
                {
                    return Err(MeetingError::Malformed("invalid deleting audio state"));
                }
            }
            AudioState::Released => {
                let Some(receipt) = &self.retention.deletion_receipt else {
                    return Err(MeetingError::Malformed("released audio lacks a receipt"));
                };
                validate_ref(receipt, "deletion/audio-deletion.json")?;
                if !any_audio || self.pending_storage_operation.is_some() {
                    return Err(MeetingError::Malformed("invalid released audio state"));
                }
            }
        }

        if self.lifecycle == MeetingLifecycle::Incomplete
            && self.retention.state != AudioState::NeverCreated
        {
            return Err(MeetingError::Malformed("incomplete meeting owns audio"));
        }
        if self.lifecycle == MeetingLifecycle::RecoveredInterrupted {
            if any_audio && self.retention.state == AudioState::NeverCreated {
                return Err(MeetingError::Malformed("partial audio is not retained"));
            }
            if !any_audio && self.retention.state != AudioState::NeverCreated {
                return Err(MeetingError::Malformed("interrupted meeting has no audio"));
            }
        }
        Ok(())
    }
}

pub fn retention_policy_sha256(rule: &AudioRetentionRule) -> String {
    #[derive(Serialize)]
    struct CanonicalPolicy<'a> {
        schema: &'static str,
        rule: &'a AudioRetentionRule,
    }
    let bytes = serde_json::to_vec(&CanonicalPolicy {
        schema: "audio-retention-policy/1",
        rule,
    })
    .expect("retention policy is serializable");
    format!("{:x}", Sha256::digest(bytes))
}

pub fn load_meeting(meeting_dir: &Path) -> Result<MeetingRecord, MeetingError> {
    require_private_directory(meeting_dir)?;
    let directory_id = meeting_dir
        .file_name()
        .and_then(|name| name.to_str())
        .ok_or(MeetingError::Malformed("meeting directory name is invalid"))?;
    let bytes = read_private_bytes(&meeting_dir.join("meeting.json"), MAX_MEETING_RECORD_BYTES)?;
    let meeting: MeetingRecord = serde_json::from_slice(&bytes)?;
    meeting.validate(directory_id)?;
    Ok(meeting)
}

pub fn write_meeting(meeting_dir: &Path, meeting: &MeetingRecord) -> Result<(), MeetingError> {
    let directory_id = meeting_dir
        .file_name()
        .and_then(|name| name.to_str())
        .ok_or(MeetingError::Malformed("meeting directory name is invalid"))?;
    meeting.validate(directory_id)?;
    durable_replace(
        &meeting_dir.join("meeting.json"),
        &serde_json::to_vec_pretty(meeting)?,
    )?;
    Ok(())
}

pub fn verify_record_artifacts(
    meeting_dir: &Path,
    meeting: &MeetingRecord,
) -> Result<(), MeetingError> {
    verify_record_static_artifacts(meeting_dir, meeting)?;
    if meeting.retention.state == AudioState::Retained {
        for reference in [
            meeting.artifacts.microphone_audio.as_ref(),
            meeting.artifacts.system_audio.as_ref(),
        ]
        .into_iter()
        .flatten()
        {
            verify_artifact_ref(meeting_dir, reference)?;
        }
    }
    if let Some(reference) = &meeting.retention.deletion_receipt {
        verify_artifact_ref(meeting_dir, reference)?;
    }
    Ok(())
}

pub fn verify_record_static_artifacts(
    meeting_dir: &Path,
    meeting: &MeetingRecord,
) -> Result<(), MeetingError> {
    verify_artifact_ref(meeting_dir, &meeting.artifacts.attempt)?;
    if let Some(reference) = &meeting.artifacts.ownership {
        verify_artifact_ref(meeting_dir, reference)?;
    }
    if let Some(reference) = &meeting.artifacts.capture_session {
        verify_artifact_ref(meeting_dir, reference)?;
    }
    if let Some(reference) = &meeting.artifacts.current_transcript {
        verify_artifact_ref(meeting_dir, reference)?;
    }
    if let Some(note) = &meeting.artifacts.current_note {
        verify_artifact_ref(meeting_dir, &note.json)?;
        verify_artifact_ref(meeting_dir, &note.markdown)?;
    }
    Ok(())
}

pub fn artifact_ref(meeting_dir: &Path, relative_path: &str) -> Result<ArtifactRef, MeetingError> {
    let path = resolve_artifact(meeting_dir, relative_path)?;
    Ok(ArtifactRef {
        relative_path: relative_path.to_owned(),
        sha256: hash_private_file(&path)?,
    })
}

pub fn verify_artifact_ref(
    meeting_dir: &Path,
    reference: &ArtifactRef,
) -> Result<(), MeetingError> {
    let path = resolve_artifact(meeting_dir, &reference.relative_path)?;
    if hash_private_file(&path)? != reference.sha256 {
        return Err(MeetingError::ArtifactMismatch);
    }
    Ok(())
}

pub fn resolve_artifact(meeting_dir: &Path, relative_path: &str) -> Result<PathBuf, MeetingError> {
    let relative = Path::new(relative_path);
    if relative.is_absolute()
        || relative
            .components()
            .any(|component| !matches!(component, Component::Normal(_)))
    {
        return Err(MeetingError::Malformed("artifact path is unsafe"));
    }
    let mut parent = meeting_dir.to_path_buf();
    let component_count = relative.components().count();
    for component in relative
        .components()
        .take(component_count.saturating_sub(1))
    {
        parent.push(component.as_os_str());
        require_private_directory(&parent)?;
    }
    Ok(meeting_dir.join(relative))
}

pub fn read_private_bytes(path: &Path, maximum: u64) -> Result<Vec<u8>, MeetingError> {
    let mut file = open_private_file(path)?;
    let length = file.metadata()?.len();
    if length > maximum {
        return Err(MeetingError::InvalidPrivateStorage);
    }
    let mut bytes = Vec::with_capacity(length as usize);
    file.read_to_end(&mut bytes)?;
    Ok(bytes)
}

pub fn hash_private_file(path: &Path) -> Result<String, MeetingError> {
    let mut file = open_private_file(path)?;
    let mut hasher = Sha256::new();
    let mut buffer = [0_u8; 64 * 1024];
    loop {
        let read = file.read(&mut buffer)?;
        if read == 0 {
            break;
        }
        hasher.update(&buffer[..read]);
    }
    Ok(format!("{:x}", hasher.finalize()))
}

pub fn open_private_file(path: &Path) -> Result<File, MeetingError> {
    let file = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW)
        .open(path)?;
    let metadata = file.metadata()?;
    if !metadata.file_type().is_file() || metadata.permissions().mode() & 0o777 != 0o600 {
        return Err(MeetingError::InvalidPrivateStorage);
    }
    Ok(file)
}

pub fn require_private_directory(path: &Path) -> Result<(), MeetingError> {
    let metadata = fs::symlink_metadata(path)?;
    if metadata.file_type().is_symlink()
        || !metadata.file_type().is_dir()
        || metadata.permissions().mode() & 0o777 != 0o700
    {
        return Err(MeetingError::InvalidPrivateStorage);
    }
    Ok(())
}

fn validate_ref(reference: &ArtifactRef, expected_path: &str) -> Result<(), MeetingError> {
    if reference.relative_path != expected_path {
        return Err(MeetingError::Malformed(
            "artifact path does not match its role",
        ));
    }
    validate_sha256(&reference.sha256)
}

fn validate_digest_named_ref(
    reference: &ArtifactRef,
    directory: &str,
    extension: &str,
) -> Result<(), MeetingError> {
    validate_sha256(&reference.sha256)?;
    let expected = format!("{directory}/{}.{}", reference.sha256, extension);
    validate_ref(reference, &expected)
}

fn validate_sha256(value: &str) -> Result<(), MeetingError> {
    if value.len() != 64
        || !value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
    {
        return Err(MeetingError::Malformed("invalid sha256"));
    }
    Ok(())
}

fn valid_opaque_id(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 128
        && value != "."
        && value != ".."
        && value
            .chars()
            .all(|character| character.is_ascii_alphanumeric() || "-_".contains(character))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn digest(character: char) -> String {
        std::iter::repeat_n(character, 64).collect()
    }

    fn reference(path: impl Into<String>, character: char) -> ArtifactRef {
        ArtifactRef {
            relative_path: path.into(),
            sha256: digest(character),
        }
    }

    fn captured() -> MeetingRecord {
        let rule = AudioRetentionRule::DeleteAfter { seconds: 30 };
        MeetingRecord {
            schema: MeetingSchema::V2,
            meeting_id: "meeting-a".into(),
            lifecycle: MeetingLifecycle::Captured,
            retention: AudioRetention {
                policy_sha256: retention_policy_sha256(&rule),
                rule,
                next_deletion_at_epoch_seconds: Some(40),
                state: AudioState::Retained,
                deletion_receipt: None,
            },
            artifacts: MeetingArtifacts {
                attempt: reference("attempt.json", 'a'),
                ownership: Some(reference("ownership.json", 'b')),
                capture_session: Some(reference("capture/session.json", 'c')),
                microphone_audio: Some(reference("capture/mic.wav", 'd')),
                system_audio: Some(reference("capture/system.wav", 'e')),
                current_transcript: None,
                current_note: None,
            },
            pending_storage_operation: None,
        }
    }

    #[test]
    fn captured_shape_is_closed_and_valid() {
        let meeting = captured();
        meeting.validate("meeting-a").unwrap();
        let mut value = serde_json::to_value(meeting).unwrap();
        value["unexpected"] = serde_json::json!(true);
        assert!(serde_json::from_value::<MeetingRecord>(value).is_err());

        let mut value = serde_json::to_value(captured()).unwrap();
        value["retention"]["rule"]["unexpected"] = serde_json::json!(true);
        assert!(serde_json::from_value::<MeetingRecord>(value).is_err());
    }

    #[test]
    fn ready_requires_a_note_bound_to_the_current_transcript() {
        let mut meeting = captured();
        meeting.lifecycle = MeetingLifecycle::Ready;
        let transcript_digest = digest('f');
        meeting.artifacts.current_transcript = Some(reference(
            format!("transcript/{transcript_digest}.json"),
            'f',
        ));
        assert!(meeting.validate("meeting-a").is_err());

        let note_digest = digest('1');
        meeting.artifacts.current_note = Some(NoteRevisionRef {
            json: reference(format!("notes/{note_digest}.json"), '1'),
            markdown: reference(format!("notes/{note_digest}.md"), '2'),
            source_transcript_sha256: transcript_digest,
        });
        meeting.validate("meeting-a").unwrap();
    }

    #[test]
    fn audio_release_does_not_erase_ready_content_state() {
        let mut meeting = captured();
        meeting.retention.state = AudioState::Released;
        meeting.retention.deletion_receipt = Some(reference("deletion/audio-deletion.json", '9'));
        meeting.validate("meeting-a").unwrap();
        assert_eq!(meeting.lifecycle, MeetingLifecycle::Captured);
    }

    #[test]
    fn unsafe_or_non_digest_named_artifacts_are_refused() {
        let mut meeting = captured();
        meeting.artifacts.capture_session = Some(reference("../session.json", 'c'));
        assert!(meeting.validate("meeting-a").is_err());

        let mut meeting = captured();
        meeting.artifacts.current_transcript = Some(reference("transcript/current.json", 'f'));
        meeting.lifecycle = MeetingLifecycle::TranscriptReady;
        assert!(meeting.validate("meeting-a").is_err());
    }
}

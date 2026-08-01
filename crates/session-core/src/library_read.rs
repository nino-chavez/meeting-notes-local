//! Read-only, rebuildable exact retrieval for the private meeting library.
//!
//! This is deliberately not a command or persistence API.  It owns no writer,
//! persists no index, and refuses to turn malformed private bytes into search
//! authority.  Library metadata is deliberately outside this transcript-only slice.

use std::cell::RefCell;
use std::collections::BTreeMap;
use std::fs;
use std::path::Path;

use icu_normalizer::ComposingNormalizer;
use serde::Deserialize;
use thiserror::Error;
use unicode_segmentation::UnicodeSegmentation;
use uuid::Uuid;

use crate::meeting::{
    AudioState, MAX_MEETING_RECORD_BYTES, MAX_RECEIPT_BYTES, MeetingLifecycle, artifact_ref,
    load_meeting, read_private_bytes, require_private_directory, verify_artifact_ref,
    verify_record_static_artifacts,
};
use crate::storage::StorageRoot;

const MAX_TRANSCRIPT_BYTES: u64 = 16 * 1024 * 1024;
const MAX_TURNS: usize = 20_000;
const NOTICE_VERSION: &str = "internal-transcript-alpha/1";
/// Rust 1.94.0 source identity used by `char::to_lowercase` in
/// `search-normalization/1`.
pub const SEARCH_NORMALIZATION_RUST_COMMIT: &str = "4a4ef493e3a1488c6e321570238084b38948f6db";

/// Bounds every input this reader accepts.  A bound failure rejects the complete
/// build; a caller must not expose a prefix as a library.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ReadLimits {
    pub max_meetings: usize,
    pub max_total_bytes: u64,
    pub max_transcript_bytes: u64,
}

impl Default for ReadLimits {
    fn default() -> Self {
        Self {
            max_meetings: 100,
            max_total_bytes: 64 * 1024 * 1024,
            max_transcript_bytes: MAX_TRANSCRIPT_BYTES,
        }
    }
}

#[derive(Debug, Error, PartialEq, Eq)]
pub enum LibraryReadError {
    #[error("library read capacity exceeded")]
    CapacityExceeded,
    #[error("library snapshot is stale")]
    SnapshotStale,
    #[error("library request is invalid")]
    InvalidRequest,
    #[error("library artifact is unavailable")]
    ArtifactUnavailable,
}

#[derive(Clone, PartialEq, Eq)]
pub struct LibraryProjection {
    snapshot_id: Uuid,
    rows: Vec<LibraryRow>,
    quarantined_meetings: usize,
    limits: ReadLimits,
    hits: RefCell<BTreeMap<String, SealedHit>>,
}

#[derive(Clone, PartialEq, Eq)]
pub struct LibraryRow {
    pub meeting_id: String,
    pub created_at_epoch_seconds: u64,
    pub transcript_sha256: String,
    pub audio_state: AudioState,
    lifecycle: MeetingLifecycle,
    meeting_record_sha256: String,
    transcript_relative_path: String,
    turns: Vec<StoredTurn>,
    attempt_sha256: String,
}

#[derive(Clone, PartialEq, Eq)]
struct StoredTurn {
    index: u32,
    text: String,
    gated: bool,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct LibraryHit {
    projection_id: Uuid,
    key: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
enum SealedHit {
    Transcript {
        key: String,
        authority: HitAuthority,
        source_turn_index: u32,
        original_scalar_start: u64,
        original_scalar_end: u64,
        normalized_query: String,
    },
    Withheld {
        key: String,
        authority: HitAuthority,
        source_turn_index: u32,
        normalized_query: String,
    },
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct HitAuthority {
    meeting_id: String,
    created_at_epoch_seconds: u64,
    meeting_record_sha256: String,
    lifecycle: MeetingLifecycle,
    audio_state: AudioState,
    attempt_sha256: String,
    transcript_sha256: String,
    transcript_relative_path: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum OpenedLibraryHit {
    Transcript {
        meeting_id: String,
        source_turn_index: u32,
        original_scalar_start: u64,
        original_scalar_end: u64,
        text: String,
    },
    Withheld {
        meeting_id: String,
        source_turn_index: u32,
    },
}

impl LibraryProjection {
    pub fn rebuild(storage: &StorageRoot, limits: ReadLimits) -> Result<Self, LibraryReadError> {
        if limits.max_meetings == 0
            || limits.max_total_bytes == 0
            || limits.max_transcript_bytes == 0
        {
            return Err(LibraryReadError::CapacityExceeded);
        }
        let meetings_path = storage
            .resolve(Path::new("meetings"))
            .map_err(|_| LibraryReadError::ArtifactUnavailable)?;
        require_private_directory(&meetings_path)
            .map_err(|_| LibraryReadError::ArtifactUnavailable)?;
        let mut directories = Vec::new();
        for entry in
            fs::read_dir(&meetings_path).map_err(|_| LibraryReadError::ArtifactUnavailable)?
        {
            let entry = entry.map_err(|_| LibraryReadError::ArtifactUnavailable)?;
            let name = entry.file_name();
            let Some(name) = name.to_str() else { continue };
            if valid_opaque_id(name)
                && entry
                    .file_type()
                    .map_err(|_| LibraryReadError::ArtifactUnavailable)?
                    .is_dir()
                && !entry
                    .file_type()
                    .map_err(|_| LibraryReadError::ArtifactUnavailable)?
                    .is_symlink()
            {
                directories.push((name.to_owned(), entry.path()));
            }
        }
        directories.sort_by(|left, right| left.0.cmp(&right.0));
        if directories.len() > limits.max_meetings {
            return Err(LibraryReadError::CapacityExceeded);
        }

        let mut total = 0_u64;
        let mut rows = Vec::new();
        let mut quarantined = 0;
        for (_, directory) in &directories {
            match inspect_meeting(directory, limits, &mut total) {
                Ok(Some(row)) => rows.push(row),
                Ok(None) => continue,
                Err(LibraryReadError::CapacityExceeded) => {
                    return Err(LibraryReadError::CapacityExceeded);
                }
                Err(_) => quarantined += 1,
            }
        }
        rows.sort_by(meeting_order);
        Ok(Self {
            snapshot_id: Uuid::new_v4(),
            rows,
            quarantined_meetings: quarantined,
            limits,
            hits: RefCell::new(BTreeMap::new()),
        })
    }

    pub fn rows(&self) -> &[LibraryRow] {
        &self.rows
    }
    pub fn quarantined_meetings(&self) -> usize {
        self.quarantined_meetings
    }

    pub fn search(&self, query: &str) -> Result<Vec<LibraryHit>, LibraryReadError> {
        let normalized = normalize_query(query)?;
        let mut hits = Vec::new();
        for row in &self.rows {
            let authority = self.authority(row);
            for turn in &row.turns {
                for (start, end) in normalized_matches(&turn.text, &normalized) {
                    if turn.gated {
                        hits.push(SealedHit::Withheld {
                            key: format!("{}:w:{}", row.meeting_id, turn.index),
                            authority: authority.clone(),
                            source_turn_index: turn.index,
                            normalized_query: normalized.clone(),
                        });
                    } else {
                        hits.push(SealedHit::Transcript {
                            key: format!("{}:t:{}:{}:{}", row.meeting_id, turn.index, start, end),
                            authority: authority.clone(),
                            source_turn_index: turn.index,
                            original_scalar_start: start,
                            original_scalar_end: end,
                            normalized_query: normalized.clone(),
                        });
                    }
                }
            }
        }
        hits.sort_by(hit_order);
        hits.dedup_by(|left, right| hit_key(left) == hit_key(right));
        let mut retained = self.hits.borrow_mut();
        Ok(hits
            .into_iter()
            .map(|hit| {
                let key = format!("{}:{}", self.snapshot_id, hit_key(&hit));
                retained.insert(key.clone(), hit);
                LibraryHit {
                    projection_id: self.snapshot_id,
                    key,
                }
            })
            .collect())
    }

    pub fn open(
        &self,
        storage: &StorageRoot,
        handle: &LibraryHit,
    ) -> Result<OpenedLibraryHit, LibraryReadError> {
        if handle.projection_id != self.snapshot_id {
            return Err(LibraryReadError::SnapshotStale);
        }
        let hit = self
            .hits
            .borrow()
            .get(&handle.key)
            .cloned()
            .ok_or(LibraryReadError::SnapshotStale)?;
        let rebuilt =
            Self::rebuild(storage, self.limits).map_err(|_| LibraryReadError::SnapshotStale)?;
        let row = rebuilt
            .rows
            .iter()
            .find(|row| row.meeting_id == hit_meeting_id(&hit))
            .ok_or(LibraryReadError::SnapshotStale)?;
        if rebuilt.authority(row) != *hit_authority(&hit) {
            return Err(LibraryReadError::SnapshotStale);
        }
        match hit {
            SealedHit::Transcript {
                source_turn_index,
                original_scalar_start,
                original_scalar_end,
                normalized_query,
                ..
            } => {
                let turn = row
                    .turns
                    .iter()
                    .find(|turn| turn.index == source_turn_index && !turn.gated)
                    .ok_or(LibraryReadError::SnapshotStale)?;
                if !span_is_valid(&turn.text, original_scalar_start, original_scalar_end) {
                    return Err(LibraryReadError::SnapshotStale);
                }
                if !normalized_matches(&turn.text, &normalized_query)
                    .contains(&(original_scalar_start, original_scalar_end))
                {
                    return Err(LibraryReadError::SnapshotStale);
                }
                Ok(OpenedLibraryHit::Transcript {
                    meeting_id: row.meeting_id.clone(),
                    source_turn_index,
                    original_scalar_start,
                    original_scalar_end,
                    text: scalar_slice(&turn.text, original_scalar_start, original_scalar_end)
                        .ok_or(LibraryReadError::SnapshotStale)?,
                })
            }
            SealedHit::Withheld {
                source_turn_index,
                normalized_query,
                ..
            } => {
                if !row
                    .turns
                    .iter()
                    .any(|turn| turn.index == source_turn_index && turn.gated)
                {
                    return Err(LibraryReadError::SnapshotStale);
                }
                let turn = row
                    .turns
                    .iter()
                    .find(|turn| turn.index == source_turn_index)
                    .ok_or(LibraryReadError::SnapshotStale)?;
                if normalized_matches(&turn.text, &normalized_query).is_empty() {
                    return Err(LibraryReadError::SnapshotStale);
                }
                Ok(OpenedLibraryHit::Withheld {
                    meeting_id: row.meeting_id.clone(),
                    source_turn_index,
                })
            }
        }
    }

    fn authority(&self, row: &LibraryRow) -> HitAuthority {
        HitAuthority {
            meeting_id: row.meeting_id.clone(),
            created_at_epoch_seconds: row.created_at_epoch_seconds,
            meeting_record_sha256: row.meeting_record_sha256.clone(),
            lifecycle: row.lifecycle,
            audio_state: row.audio_state,
            attempt_sha256: row.attempt_sha256.clone(),
            transcript_sha256: row.transcript_sha256.clone(),
            transcript_relative_path: row.transcript_relative_path.clone(),
        }
    }

    #[cfg(test)]
    fn sealed(&self, handle: &LibraryHit) -> Option<SealedHit> {
        self.hits.borrow().get(&handle.key).cloned()
    }
}

fn inspect_meeting(
    directory: &Path,
    limits: ReadLimits,
    total: &mut u64,
) -> Result<Option<LibraryRow>, LibraryReadError> {
    let _meeting_bytes = bounded_read(
        &directory.join("meeting.json"),
        MAX_MEETING_RECORD_BYTES,
        total,
        limits,
    )?;
    let meeting = load_meeting(directory).map_err(|_| LibraryReadError::ArtifactUnavailable)?;
    verify_record_static_artifacts(directory, &meeting)
        .map_err(|_| LibraryReadError::ArtifactUnavailable)?;
    if let Some(receipt) = &meeting.retention.deletion_receipt {
        verify_artifact_ref(directory, receipt)
            .map_err(|_| LibraryReadError::ArtifactUnavailable)?;
        account_reference(directory, receipt, total, limits)?;
    }
    for reference in [
        meeting.artifacts.ownership.as_ref(),
        meeting.artifacts.capture_session.as_ref(),
        meeting
            .artifacts
            .current_note
            .as_ref()
            .map(|note| &note.json),
        meeting
            .artifacts
            .current_note
            .as_ref()
            .map(|note| &note.markdown),
    ]
    .into_iter()
    .flatten()
    {
        account_reference(directory, reference, total, limits)?;
    }
    let meeting_record = artifact_ref(directory, "meeting.json")
        .map_err(|_| LibraryReadError::ArtifactUnavailable)?;
    let attempt = artifact_ref(directory, "attempt.json")
        .map_err(|_| LibraryReadError::ArtifactUnavailable)?;
    if attempt != meeting.artifacts.attempt {
        return Err(LibraryReadError::ArtifactUnavailable);
    }
    let attempt_bytes = bounded_read(
        &directory.join("attempt.json"),
        MAX_RECEIPT_BYTES,
        total,
        limits,
    )?;
    let attempt_data: Attempt = serde_json::from_slice(&attempt_bytes)
        .map_err(|_| LibraryReadError::ArtifactUnavailable)?;
    if attempt_data.schema != "capture-attempt/1"
        || attempt_data.meeting_id != meeting.meeting_id
        || Uuid::parse_str(&attempt_data.attempt_id).is_err()
        || !valid_digest(&attempt_data.application_build_sha256)
        || attempt_data.participant_notice_version != NOTICE_VERSION
        || !attempt_data.operator_attestation.participants_consented
        || !attempt_data.operator_attestation.headphones
        || !attempt_data.operator_attestation.operator_alone
        || attempt_data.retention_policy_sha256 != meeting.retention.policy_sha256
    {
        return Err(LibraryReadError::ArtifactUnavailable);
    }
    if !matches!(
        meeting.lifecycle,
        MeetingLifecycle::TranscriptReady
            | MeetingLifecycle::SummaryFailed
            | MeetingLifecycle::Ready
    ) {
        return Ok(None);
    }
    let current = meeting
        .artifacts
        .current_transcript
        .as_ref()
        .ok_or(LibraryReadError::ArtifactUnavailable)?;
    let actual = artifact_ref(directory, &current.relative_path)
        .map_err(|_| LibraryReadError::ArtifactUnavailable)?;
    if &actual != current {
        return Err(LibraryReadError::ArtifactUnavailable);
    }
    let bytes = bounded_read(
        &directory.join(&current.relative_path),
        limits.max_transcript_bytes,
        total,
        limits,
    )?;
    let document: Transcript =
        serde_json::from_slice(&bytes).map_err(|_| LibraryReadError::ArtifactUnavailable)?;
    let turns = validate_transcript(document)?;
    // Re-read the pointers after inspection before allowing this candidate into a snapshot.
    let again = load_meeting(directory).map_err(|_| LibraryReadError::ArtifactUnavailable)?;
    if again != meeting
        || artifact_ref(directory, "meeting.json")
            .map_err(|_| LibraryReadError::ArtifactUnavailable)?
            != meeting_record
        || artifact_ref(directory, "attempt.json")
            .map_err(|_| LibraryReadError::ArtifactUnavailable)?
            != attempt
        || artifact_ref(directory, &current.relative_path)
            .map_err(|_| LibraryReadError::ArtifactUnavailable)?
            != actual
    {
        return Err(LibraryReadError::ArtifactUnavailable);
    }
    Ok(Some(LibraryRow {
        meeting_id: meeting.meeting_id.clone(),
        created_at_epoch_seconds: attempt_data.created_at_epoch_seconds,
        transcript_sha256: current.sha256.clone(),
        audio_state: meeting.retention.state,
        lifecycle: meeting.lifecycle,
        meeting_record_sha256: meeting_record.sha256,
        transcript_relative_path: current.relative_path.clone(),
        turns,
        attempt_sha256: attempt.sha256,
    }))
}

fn bounded_read(
    path: &Path,
    maximum: u64,
    total: &mut u64,
    limits: ReadLimits,
) -> Result<Vec<u8>, LibraryReadError> {
    let bytes =
        read_private_bytes(path, maximum).map_err(|_| LibraryReadError::ArtifactUnavailable)?;
    *total = total
        .checked_add(bytes.len() as u64)
        .ok_or(LibraryReadError::CapacityExceeded)?;
    if *total > limits.max_total_bytes {
        return Err(LibraryReadError::CapacityExceeded);
    }
    Ok(bytes)
}

fn account_reference(
    directory: &Path,
    reference: &crate::meeting::ArtifactRef,
    total: &mut u64,
    limits: ReadLimits,
) -> Result<(), LibraryReadError> {
    let _ = bounded_read(
        &directory.join(&reference.relative_path),
        limits.max_total_bytes,
        total,
        limits,
    )?;
    Ok(())
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Attempt {
    schema: String,
    meeting_id: String,
    attempt_id: String,
    created_at_epoch_seconds: u64,
    application_build_sha256: String,
    participant_notice_version: String,
    operator_attestation: Attestation,
    retention_policy_sha256: String,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Attestation {
    participants_consented: bool,
    headphones: bool,
    operator_alone: bool,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Transcript {
    schema: String,
    source: String,
    attribution: String,
    #[serde(rename = "bleed")]
    _bleed: Option<serde_json::Value>,
    #[serde(rename = "voiceprint")]
    _voiceprint: Option<serde_json::Value>,
    capture_health: serde_json::Value,
    turns: Vec<Turn>,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Turn {
    start: f64,
    end: f64,
    speaker: Option<String>,
    text: String,
    gated: Option<bool>,
    gate_score: Option<f64>,
    gate_reason: Option<String>,
}

fn validate_transcript(document: Transcript) -> Result<Vec<StoredTurn>, LibraryReadError> {
    if document.schema != "capture-transcript/1"
        || document.source.is_empty()
        || !matches!(document.attribution.as_str(), "channel" | "none")
        || !document.capture_health.is_object()
        || document.turns.len() > MAX_TURNS
    {
        return Err(LibraryReadError::ArtifactUnavailable);
    }
    document
        .turns
        .into_iter()
        .enumerate()
        .map(|(index, turn)| {
            if !turn.start.is_finite()
                || !turn.end.is_finite()
                || turn.start < 0.0
                || turn.end < turn.start
                || turn.text.len() > 100_000
                || turn
                    .speaker
                    .as_ref()
                    .is_some_and(|speaker| speaker.len() > 256)
                || (document.attribution == "channel"
                    && turn
                        .speaker
                        .as_deref()
                        .is_some_and(|speaker| !matches!(speaker, "Me" | "Them")))
                || ((turn.gate_score.is_some() || turn.gate_reason.is_some())
                    && turn.gated != Some(true))
            {
                return Err(LibraryReadError::ArtifactUnavailable);
            }
            Ok(StoredTurn {
                index: index as u32,
                text: turn.text,
                gated: turn.gated == Some(true),
            })
        })
        .collect()
}

fn normalize_query(query: &str) -> Result<String, LibraryReadError> {
    if query.chars().any(is_forbidden) {
        return Err(LibraryReadError::InvalidRequest);
    }
    let trimmed = query.trim_matches(char::is_whitespace);
    if trimmed.is_empty() || trimmed.chars().count() > 256 {
        return Err(LibraryReadError::InvalidRequest);
    }
    Ok(normalize(trimmed).0)
}

fn normalized_matches(field: &str, needle: &str) -> Vec<(u64, u64)> {
    let (haystack, origins) = normalize(field);
    if needle.is_empty() {
        return Vec::new();
    }
    let chars: Vec<_> = haystack.chars().collect();
    let needle: Vec<_> = needle.chars().collect();
    chars
        .windows(needle.len())
        .enumerate()
        .filter(|(_, window)| *window == needle.as_slice())
        .map(|(start, _)| {
            let span = &origins[start..start + needle.len()];
            (
                span.iter().map(|range| range.0).min().unwrap_or(0),
                span.iter().map(|range| range.1).max().unwrap_or(0),
            )
        })
        .collect()
}

/// Frozen `search-normalization/1`: grapheme -> ICU NFC -> Rust lowercase,
/// with every normalized scalar retaining its complete original scalar range.
fn normalize(value: &str) -> (String, Vec<(u64, u64)>) {
    let nfc = ComposingNormalizer::new_nfc();
    let mut normalized = String::new();
    let mut origins = Vec::new();
    let mut scalar = 0_u64;
    for grapheme in value.graphemes(true) {
        let count = grapheme.chars().count() as u64;
        let range = (scalar, scalar + count);
        scalar += count;
        let mut nfc_text = String::new();
        nfc.normalize_to(grapheme, &mut nfc_text)
            .expect("string write");
        for character in nfc_text.chars().flat_map(char::to_lowercase) {
            normalized.push(character);
            origins.push(range);
        }
    }
    (normalized, origins)
}

fn is_forbidden(character: char) -> bool {
    character.is_control() || matches!(character, '\u{2028}' | '\u{2029}')
}
fn valid_opaque_id(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 128
        && value != "."
        && value != ".."
        && value
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || matches!(c, '-' | '_'))
}
fn valid_digest(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}
fn span_is_valid(text: &str, start: u64, end: u64) -> bool {
    start < end && end <= text.chars().count() as u64
}
fn scalar_slice(text: &str, start: u64, end: u64) -> Option<String> {
    if !span_is_valid(text, start, end) {
        return None;
    }
    Some(
        text.chars()
            .skip(start as usize)
            .take((end - start) as usize)
            .collect(),
    )
}
#[cfg(test)]
fn digest_bytes(bytes: &[u8]) -> String {
    use sha2::{Digest, Sha256};
    format!("{:x}", Sha256::digest(bytes))
}
fn meeting_order(left: &LibraryRow, right: &LibraryRow) -> std::cmp::Ordering {
    right
        .created_at_epoch_seconds
        .cmp(&left.created_at_epoch_seconds)
        .then_with(|| left.meeting_id.cmp(&right.meeting_id))
}
fn hit_key(hit: &SealedHit) -> &str {
    match hit {
        SealedHit::Transcript { key, .. } | SealedHit::Withheld { key, .. } => key,
    }
}
fn hit_meeting_id(hit: &SealedHit) -> &str {
    match hit {
        SealedHit::Transcript { authority, .. } | SealedHit::Withheld { authority, .. } => {
            &authority.meeting_id
        }
    }
}
fn hit_authority(hit: &SealedHit) -> &HitAuthority {
    match hit {
        SealedHit::Transcript { authority, .. } | SealedHit::Withheld { authority, .. } => {
            authority
        }
    }
}
fn hit_order(left: &SealedHit, right: &SealedHit) -> std::cmp::Ordering {
    let (lc, li) = hit_sort(left);
    let (rc, ri) = hit_sort(right);
    rc.cmp(&lc)
        .then_with(|| hit_meeting_id(left).cmp(hit_meeting_id(right)))
        .then_with(|| li.cmp(&ri))
        .then_with(|| hit_key(left).cmp(hit_key(right)))
}
fn hit_sort(hit: &SealedHit) -> (u64, u64) {
    match hit {
        SealedHit::Transcript {
            authority,
            source_turn_index,
            original_scalar_start,
            ..
        } => (
            authority_created(authority),
            ((*source_turn_index as u64) << 32) | *original_scalar_start,
        ),
        SealedHit::Withheld {
            authority,
            source_turn_index,
            ..
        } => (
            authority_created(authority),
            ((*source_turn_index as u64) << 32) | u32::MAX as u64,
        ),
    }
}
fn authority_created(authority: &HitAuthority) -> u64 {
    authority.created_at_epoch_seconds
}

#[cfg(test)]
mod tests {
    use std::fs;
    use std::path::{Path, PathBuf};

    use serde_json::json;
    use sha2::{Digest, Sha256};
    use tempfile::TempDir;

    use super::*;
    use crate::meeting::{
        ArtifactRef, AudioRetention, AudioRetentionRule, MeetingArtifacts, MeetingRecord,
        MeetingSchema, artifact_ref, retention_policy_sha256, write_meeting,
    };
    use crate::storage::{create_private_dir, durable_create_new};

    struct Fixture {
        temp: TempDir,
        storage: StorageRoot,
    }

    impl Fixture {
        fn new() -> Self {
            let temp = TempDir::new().unwrap();
            let repository = temp.path().join("repository");
            create_private_dir(&repository).unwrap();
            let storage = StorageRoot::create(&temp.path().join("data"), &repository).unwrap();
            Self { temp, storage }
        }

        fn meeting(&self, id: &str, created: u64, turns: &[(&str, bool)]) -> PathBuf {
            let directory = self.storage.path().join("meetings").join(id);
            for child in ["", "capture", "transcript", "deletion"] {
                create_private_dir(&directory.join(child)).unwrap();
            }
            let rule = AudioRetentionRule::DeleteAfter { seconds: 60 };
            let policy = retention_policy_sha256(&rule);
            let attempt = json!({
                "schema": "capture-attempt/1", "meeting_id": id,
                "attempt_id": "11111111-1111-4111-8111-111111111111",
                "created_at_epoch_seconds": created,
                "application_build_sha256": "a".repeat(64),
                "participant_notice_version": NOTICE_VERSION,
                "operator_attestation": {"participants_consented": true, "headphones": true, "operator_alone": true},
                "retention_policy_sha256": policy,
            });
            durable_create_new(
                &directory.join("attempt.json"),
                &serde_json::to_vec_pretty(&attempt).unwrap(),
            )
            .unwrap();
            for path in [
                "ownership.json",
                "capture/session.json",
                "deletion/audio-deletion.json",
            ] {
                durable_create_new(&directory.join(path), b"{}\n").unwrap();
            }
            let turns: Vec<_> = turns.iter().enumerate().map(|(index, (text, gated))| json!({
                "start": index as f64, "end": index as f64 + 0.5, "speaker": "Me", "text": text,
                "gated": gated,
            })).collect();
            let transcript = serde_json::to_vec_pretty(&json!({
                "schema": "capture-transcript/1", "source": "synthetic", "attribution": "channel",
                "bleed": null, "voiceprint": null, "capture_health": {}, "turns": turns,
            }))
            .unwrap();
            let digest = format!("{:x}", Sha256::digest(&transcript));
            let relative = format!("transcript/{digest}.json");
            durable_create_new(&directory.join(&relative), &transcript).unwrap();
            let reference = |path: &str| artifact_ref(&directory, path).unwrap();
            let record = MeetingRecord {
                schema: MeetingSchema::V2,
                meeting_id: id.into(),
                lifecycle: MeetingLifecycle::TranscriptReady,
                retention: AudioRetention {
                    rule,
                    policy_sha256: policy,
                    next_deletion_at_epoch_seconds: Some(created + 60),
                    state: AudioState::Released,
                    deletion_receipt: Some(reference("deletion/audio-deletion.json")),
                },
                artifacts: MeetingArtifacts {
                    attempt: reference("attempt.json"),
                    ownership: Some(reference("ownership.json")),
                    capture_session: Some(reference("capture/session.json")),
                    microphone_audio: Some(ArtifactRef {
                        relative_path: "capture/mic.wav".into(),
                        sha256: "b".repeat(64),
                    }),
                    system_audio: Some(ArtifactRef {
                        relative_path: "capture/system.wav".into(),
                        sha256: "c".repeat(64),
                    }),
                    current_transcript: Some(reference(&relative)),
                    current_note: None,
                },
                pending_storage_operation: None,
            };
            write_meeting(&directory, &record).unwrap();
            directory
        }
    }

    #[test]
    fn rebuild_is_read_only_and_quarantines_tampered_meetings() {
        let fixture = Fixture::new();
        fixture.meeting("meeting-a", 10, &[("safe token", false)]);
        let bad = fixture.meeting("meeting-b", 9, &[("tampered token", false)]);
        fs::write(bad.join("attempt.json"), b"not a receipt").unwrap();
        let before = tree_digest(fixture.storage.path());
        let projection =
            LibraryProjection::rebuild(&fixture.storage, ReadLimits::default()).unwrap();
        assert_eq!(projection.rows().len(), 1);
        assert_eq!(projection.quarantined_meetings(), 1);
        assert_eq!(before, tree_digest(fixture.storage.path()));
        assert!(fixture.temp.path().exists());
    }

    #[test]
    fn normalized_overlapping_search_has_stable_natural_keys() {
        let fixture = Fixture::new();
        fixture.meeting("meeting-a", 10, &[("e\u{301}chooooo", false)]);
        let projection =
            LibraryProjection::rebuild(&fixture.storage, ReadLimits::default()).unwrap();
        let hits = projection.search(" ÉCHO ").unwrap();
        assert_eq!(hits.len(), 1);
        assert!(matches!(
            projection.sealed(&hits[0]),
            Some(SealedHit::Transcript {
                original_scalar_start: 0,
                original_scalar_end: 5,
                ..
            })
        ));
        assert_eq!(
            hit_key(&projection.sealed(&hits[0]).unwrap()),
            hit_key(
                &projection
                    .sealed(&projection.search("écho").unwrap()[0])
                    .unwrap()
            )
        );
        assert_eq!(normalized_matches("oooo", "oo").len(), 3);
    }

    #[test]
    fn withheld_opens_without_text_and_retained_opens_with_original_span() {
        let fixture = Fixture::new();
        fixture.meeting(
            "meeting-a",
            10,
            &[("visible token", false), ("hidden token", true)],
        );
        let projection =
            LibraryProjection::rebuild(&fixture.storage, ReadLimits::default()).unwrap();
        let retained = projection.search("visible").unwrap().remove(0);
        assert!(matches!(
            projection.open(&fixture.storage, &retained).unwrap(),
            OpenedLibraryHit::Transcript {
                original_scalar_start: 0,
                original_scalar_end: 7,
                ..
            }
        ));
        let withheld = projection.search("hidden").unwrap().remove(0);
        assert!(matches!(
            projection.open(&fixture.storage, &withheld).unwrap(),
            OpenedLibraryHit::Withheld { .. }
        ));
    }

    #[test]
    fn open_fails_closed_when_any_bound_artifact_drifts() {
        for target in ["meeting", "attempt", "transcript"] {
            let fixture = Fixture::new();
            let directory = fixture.meeting("meeting-a", 10, &[("stable token", false)]);
            let projection =
                LibraryProjection::rebuild(&fixture.storage, ReadLimits::default()).unwrap();
            let hit = projection.search("stable").unwrap().remove(0);
            match target {
                "meeting" => fs::write(directory.join("meeting.json"), b"{}").unwrap(),
                "attempt" => fs::write(directory.join("attempt.json"), b"{}").unwrap(),
                "transcript" => {
                    let current = load_meeting(&directory)
                        .unwrap()
                        .artifacts
                        .current_transcript
                        .unwrap();
                    fs::write(directory.join(current.relative_path), b"changed").unwrap();
                }
                _ => unreachable!(),
            }
            assert_eq!(
                projection.open(&fixture.storage, &hit),
                Err(LibraryReadError::SnapshotStale)
            );
        }
    }

    #[test]
    fn handles_are_projection_owned_and_unknown_handles_are_stale() {
        let fixture = Fixture::new();
        fixture.meeting("meeting-a", 10, &[("stable token", false)]);
        let projection =
            LibraryProjection::rebuild(&fixture.storage, ReadLimits::default()).unwrap();
        let handle = projection.search("stable").unwrap().remove(0);
        let forged = LibraryHit {
            projection_id: projection.snapshot_id,
            key: "forged".into(),
        };
        assert_eq!(
            projection.open(&fixture.storage, &forged),
            Err(LibraryReadError::SnapshotStale)
        );
        let other = LibraryProjection::rebuild(&fixture.storage, ReadLimits::default()).unwrap();
        assert_eq!(
            projection.open(&fixture.storage, &other.search("stable").unwrap()[0]),
            Err(LibraryReadError::SnapshotStale)
        );
        assert!(projection.open(&fixture.storage, &handle).is_ok());
    }

    #[test]
    fn lifecycle_and_current_transcript_pointer_drift_are_stale() {
        let fixture = Fixture::new();
        let directory = fixture.meeting("meeting-a", 10, &[("stable token", false)]);
        let projection =
            LibraryProjection::rebuild(&fixture.storage, ReadLimits::default()).unwrap();
        let handle = projection.search("stable").unwrap().remove(0);
        let mut record = load_meeting(&directory).unwrap();
        record.lifecycle = MeetingLifecycle::SummaryFailed;
        write_meeting(&directory, &record).unwrap();
        assert_eq!(
            projection.open(&fixture.storage, &handle),
            Err(LibraryReadError::SnapshotStale)
        );

        let fixture = Fixture::new();
        let directory = fixture.meeting("meeting-a", 10, &[("stable token", false)]);
        let projection =
            LibraryProjection::rebuild(&fixture.storage, ReadLimits::default()).unwrap();
        let handle = projection.search("stable").unwrap().remove(0);
        let mut record = load_meeting(&directory).unwrap();
        let original = record.artifacts.current_transcript.clone().unwrap();
        let bytes = fs::read(directory.join(&original.relative_path)).unwrap();
        let alternate = format!("{}\n", String::from_utf8(bytes).unwrap());
        let digest = format!("{:x}", Sha256::digest(alternate.as_bytes()));
        let relative = format!("transcript/{digest}.json");
        durable_create_new(&directory.join(&relative), alternate.as_bytes()).unwrap();
        record.artifacts.current_transcript = Some(artifact_ref(&directory, &relative).unwrap());
        write_meeting(&directory, &record).unwrap();
        assert_eq!(
            projection.open(&fixture.storage, &handle),
            Err(LibraryReadError::SnapshotStale)
        );
    }

    #[test]
    fn transcript_search_and_limits_refuse_whole_build() {
        let fixture = Fixture::new();
        fixture.meeting("meeting-a", 10, &[("token", false)]);
        let projection =
            LibraryProjection::rebuild(&fixture.storage, ReadLimits::default()).unwrap();
        assert_eq!(projection.search("token").unwrap().len(), 1);
        assert!(matches!(
            LibraryProjection::rebuild(
                &fixture.storage,
                ReadLimits {
                    max_total_bytes: 1,
                    ..ReadLimits::default()
                }
            ),
            Err(LibraryReadError::CapacityExceeded)
        ));
        for (input, expected, origins) in NORMALIZATION_FIXTURES {
            let actual = normalize(input);
            assert_eq!(actual.0, *expected);
            assert_eq!(actual.1, *origins);
        }
        assert_eq!(
            normalized_matches("aaaa", "aa"),
            vec![(0, 2), (1, 3), (2, 4)]
        );
        assert!(normalize_query(&"a".repeat(256)).is_ok());
        assert_eq!(
            normalize_query(&"a".repeat(257)),
            Err(LibraryReadError::InvalidRequest)
        );
        assert_eq!(
            normalize_query(" \n token"),
            Err(LibraryReadError::InvalidRequest)
        );
    }

    fn tree_digest(path: &Path) -> Vec<(String, String)> {
        fn walk(root: &Path, path: &Path, output: &mut Vec<(String, String)>) {
            let metadata = fs::symlink_metadata(path).unwrap();
            let relative = path.strip_prefix(root).unwrap().display().to_string();
            if metadata.is_dir() {
                output.push((
                    format!("d:{relative}"),
                    format!("{:o}", metadata.permissions().mode() & 0o777),
                ));
                let mut children: Vec<_> =
                    fs::read_dir(path).unwrap().map(Result::unwrap).collect();
                children.sort_by_key(|entry| entry.file_name());
                for child in children {
                    walk(root, &child.path(), output);
                }
            } else {
                output.push((
                    format!("f:{relative}"),
                    digest_bytes(&fs::read(path).unwrap()),
                ));
            }
        }
        use std::os::unix::fs::PermissionsExt;
        let mut output = Vec::new();
        walk(path, path, &mut output);
        output
    }

    type NormalizationFixture = (&'static str, &'static str, &'static [(u64, u64)]);
    const NORMALIZATION_FIXTURES: &[NormalizationFixture] = &[
        ("é", "é", &[(0, 1)]),
        ("e\u{301}", "é", &[(0, 2)]),
        ("İ", "i\u{307}", &[(0, 1), (0, 1)]),
        ("👩‍💻", "👩‍💻", &[(0, 3), (0, 3), (0, 3)]),
    ];
}

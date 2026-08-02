//! Read-only, rebuildable exact retrieval for the private meeting library.
//!
//! This is deliberately not a command or persistence API.  It owns no writer,
//! persists no index, and refuses to turn malformed private bytes into search
//! authority.  Library metadata is deliberately outside this transcript-only slice.

use std::cell::RefCell;
use std::collections::BTreeMap;
use std::fs;
use std::io::Read;
use std::path::Path;
use std::sync::Arc;

use icu_normalizer::ComposingNormalizer;
use serde::Deserialize;
use thiserror::Error;
use unicode_segmentation::UnicodeSegmentation;
use uuid::Uuid;

use crate::library_metadata::{MetadataIdentity, MetadataState, read_library_metadata};
use crate::meeting::{
    MAX_MEETING_RECORD_BYTES, MAX_RECEIPT_BYTES, MeetingLifecycle, artifact_ref, load_meeting,
    open_private_file, require_private_directory, valid_opaque_id, verify_artifact_ref,
    verify_record_static_artifacts,
};
use crate::note_projection::{
    NoteProjector, ProjectRequest, ProjectionError, UnavailableProjector, project_claims,
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

pub struct LibraryProjection {
    snapshot_id: Uuid,
    rows: Vec<LibraryRow>,
    quarantined_meetings: usize,
    limits: ReadLimits,
    metadata: MetadataState,
    projector: Arc<dyn NoteProjector>,
    hits: RefCell<BTreeMap<String, SealedHit>>,
}

#[derive(Clone, PartialEq, Eq)]
pub struct LibraryRow {
    pub meeting_id: String,
    pub created_at_epoch_seconds: u64,
    pub transcript_sha256: Option<String>,
    lifecycle: MeetingLifecycle,
    meeting_record_sha256: String,
    transcript_relative_path: Option<String>,
    turns: Vec<StoredTurn>,
    note_json_sha256: Option<String>,
    note_markdown_sha256: Option<String>,
    claims: Vec<StoredClaim>,
    attempt_sha256: String,
    title: Option<String>,
    folder: Option<String>,
}

#[derive(Clone, PartialEq, Eq)]
struct StoredTurn {
    index: u32,
    text: String,
    gated: bool,
}

#[derive(Clone, PartialEq, Eq)]
struct StoredClaim {
    ordinal: u64,
    sha256: String,
    claim_type: crate::note_projection::ClaimType,
    text: String,
    // Locators stay in the sealed snapshot identity.  They are never exposed
    // by a read result or diagnostic.
    locators: Vec<crate::note_projection::Locator>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct LibraryHit {
    projection_id: Uuid,
    key: String,
}

#[derive(Clone, PartialEq, Eq)]
enum SealedHit {
    Claim {
        key: String,
        authority: HitAuthority,
        claim: StoredClaim,
        normalized_query: String,
    },
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
    Meeting {
        key: String,
        authority: HitAuthority,
        normalized_query: String,
    },
}

#[derive(Clone, PartialEq, Eq)]
struct HitAuthority {
    meeting_id: String,
    created_at_epoch_seconds: u64,
    meeting_record_sha256: String,
    lifecycle: MeetingLifecycle,
    attempt_sha256: String,
    transcript_sha256: Option<String>,
    transcript_relative_path: Option<String>,
    note_json_sha256: Option<String>,
    note_markdown_sha256: Option<String>,
    metadata_identity: MetadataIdentity,
}

#[derive(Clone, PartialEq, Eq)]
pub enum OpenedLibraryHit {
    Claim {
        meeting_id: String,
        claim_ordinal: u64,
        claim: String,
    },
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
    Meeting {
        meeting_id: String,
        title: Option<String>,
        folder: Option<String>,
    },
}

impl LibraryProjection {
    pub fn rebuild(storage: &StorageRoot, limits: ReadLimits) -> Result<Self, LibraryReadError> {
        Self::rebuild_with_projector(storage, limits, Arc::new(UnavailableProjector))
    }

    /// Rebuilds through an injected, read-only `note.project` transport.  The
    /// snapshot retains no child output beyond the accepted current claims.
    pub fn rebuild_with_projector(
        storage: &StorageRoot,
        limits: ReadLimits,
        projector: Arc<dyn NoteProjector>,
    ) -> Result<Self, LibraryReadError> {
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
            match inspect_meeting(directory, limits, &mut total, projector.as_ref()) {
                Ok(Some(row)) => rows.push(row),
                Ok(None) => continue,
                Err(MeetingInspectionError::CapacityExceeded) => {
                    return Err(LibraryReadError::CapacityExceeded);
                }
                Err(MeetingInspectionError::Unavailable) => {
                    return Err(LibraryReadError::ArtifactUnavailable);
                }
                Err(MeetingInspectionError::Quarantine) => quarantined += 1,
            }
        }
        rows.sort_by(meeting_order);
        let metadata = read_library_metadata(storage);
        if let Some(document) = metadata.document() {
            // Metadata gains authority only when every row targets a safely
            // projected meeting.  A sparse record may omit any meeting.
            if document.meetings.iter().all(|row| {
                rows.iter()
                    .any(|meeting| meeting.meeting_id == row.meeting_id)
            }) {
                for row in &mut rows {
                    if let Some(label) = document
                        .meetings
                        .iter()
                        .find(|label| label.meeting_id == row.meeting_id)
                    {
                        row.title = label.title.clone();
                        row.folder = label
                            .folder_id
                            .as_ref()
                            .and_then(|id| document.folders.iter().find(|folder| &folder.id == id))
                            .map(|folder| folder.name.clone());
                    }
                }
            } else {
                // Metadata rows cannot hide invalid or unavailable meetings.
                // Preserve a content-free unavailable state instead.
                return Ok(Self {
                    snapshot_id: Uuid::new_v4(),
                    rows,
                    quarantined_meetings: quarantined,
                    limits,
                    metadata: metadata.unavailable_after_relative_validation(),
                    projector,
                    hits: RefCell::new(BTreeMap::new()),
                });
            }
        }
        Ok(Self {
            snapshot_id: Uuid::new_v4(),
            rows,
            quarantined_meetings: quarantined,
            limits,
            metadata,
            projector,
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
            for claim in &row.claims {
                if !normalized_matches(&claim.text, &normalized).is_empty() {
                    hits.push(SealedHit::Claim {
                        key: format!(
                            "{}:c:{}:{}",
                            row.meeting_id,
                            row.note_json_sha256.as_deref().unwrap_or_default(),
                            claim.ordinal
                        ),
                        authority: authority.clone(),
                        claim: claim.clone(),
                        normalized_query: normalized.clone(),
                    });
                }
            }
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
            if row
                .title
                .as_ref()
                .is_some_and(|title| !normalized_matches(title, &normalized).is_empty())
                || row
                    .folder
                    .as_ref()
                    .is_some_and(|folder| !normalized_matches(folder, &normalized).is_empty())
            {
                hits.push(SealedHit::Meeting {
                    key: format!("{}:m", row.meeting_id),
                    authority: authority.clone(),
                    normalized_query: normalized.clone(),
                });
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
        let rebuilt = Self::rebuild_with_projector(storage, self.limits, self.projector.clone())
            .map_err(|_| LibraryReadError::SnapshotStale)?;
        let row = rebuilt
            .rows
            .iter()
            .find(|row| row.meeting_id == hit_meeting_id(&hit))
            .ok_or(LibraryReadError::SnapshotStale)?;
        if rebuilt.authority(row) != *hit_authority(&hit) {
            return Err(LibraryReadError::SnapshotStale);
        }
        match hit {
            SealedHit::Claim {
                claim,
                normalized_query,
                ..
            } => {
                let current = row
                    .claims
                    .iter()
                    .find(|candidate| candidate.ordinal == claim.ordinal)
                    .ok_or(LibraryReadError::SnapshotStale)?;
                if current != &claim
                    || normalized_matches(&current.text, &normalized_query).is_empty()
                {
                    return Err(LibraryReadError::SnapshotStale);
                }
                Ok(OpenedLibraryHit::Claim {
                    meeting_id: row.meeting_id.clone(),
                    claim_ordinal: current.ordinal,
                    claim: current.text.clone(),
                })
            }
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
            SealedHit::Meeting {
                normalized_query, ..
            } => {
                if row
                    .title
                    .as_ref()
                    .is_none_or(|title| normalized_matches(title, &normalized_query).is_empty())
                    && row.folder.as_ref().is_none_or(|folder| {
                        normalized_matches(folder, &normalized_query).is_empty()
                    })
                {
                    return Err(LibraryReadError::SnapshotStale);
                }
                Ok(OpenedLibraryHit::Meeting {
                    meeting_id: row.meeting_id.clone(),
                    title: row.title.clone(),
                    folder: row.folder.clone(),
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
            attempt_sha256: row.attempt_sha256.clone(),
            transcript_sha256: row.transcript_sha256.clone(),
            transcript_relative_path: row.transcript_relative_path.clone(),
            note_json_sha256: row.note_json_sha256.clone(),
            note_markdown_sha256: row.note_markdown_sha256.clone(),
            metadata_identity: self.metadata.identity(),
        }
    }

    #[cfg(test)]
    fn sealed(&self, handle: &LibraryHit) -> Option<SealedHit> {
        self.hits.borrow().get(&handle.key).cloned()
    }
}

enum MeetingInspectionError {
    Quarantine,
    CapacityExceeded,
    Unavailable,
}

impl From<LibraryReadError> for MeetingInspectionError {
    fn from(value: LibraryReadError) -> Self {
        match value {
            LibraryReadError::CapacityExceeded => Self::CapacityExceeded,
            LibraryReadError::ArtifactUnavailable
            | LibraryReadError::InvalidRequest
            | LibraryReadError::SnapshotStale => Self::Quarantine,
        }
    }
}

fn inspect_meeting(
    directory: &Path,
    limits: ReadLimits,
    total: &mut u64,
    projector: &dyn NoteProjector,
) -> Result<Option<LibraryRow>, MeetingInspectionError> {
    let _meeting_bytes = bounded_read(
        &directory.join("meeting.json"),
        MAX_MEETING_RECORD_BYTES,
        total,
        limits,
    )?;
    let meeting = load_meeting(directory).map_err(|_| MeetingInspectionError::Quarantine)?;
    verify_record_static_artifacts(directory, &meeting)
        .map_err(|_| MeetingInspectionError::Quarantine)?;
    if let Some(receipt) = &meeting.retention.deletion_receipt {
        verify_artifact_ref(directory, receipt).map_err(|_| MeetingInspectionError::Quarantine)?;
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
    let meeting_record =
        artifact_ref(directory, "meeting.json").map_err(|_| MeetingInspectionError::Quarantine)?;
    let attempt =
        artifact_ref(directory, "attempt.json").map_err(|_| MeetingInspectionError::Quarantine)?;
    if attempt != meeting.artifacts.attempt {
        return Err(MeetingInspectionError::Quarantine);
    }
    let attempt_bytes = bounded_read(
        &directory.join("attempt.json"),
        MAX_RECEIPT_BYTES,
        total,
        limits,
    )?;
    let attempt_data: Attempt =
        serde_json::from_slice(&attempt_bytes).map_err(|_| MeetingInspectionError::Quarantine)?;
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
        return Err(MeetingInspectionError::Quarantine);
    }
    let (transcript_sha256, transcript_relative_path, turns, current_artifact) = if matches!(
        meeting.lifecycle,
        MeetingLifecycle::TranscriptReady
            | MeetingLifecycle::SummaryFailed
            | MeetingLifecycle::Ready
    ) {
        let current = meeting
            .artifacts
            .current_transcript
            .as_ref()
            .ok_or(MeetingInspectionError::Quarantine)?;
        let actual = artifact_ref(directory, &current.relative_path)
            .map_err(|_| MeetingInspectionError::Quarantine)?;
        if &actual != current {
            return Err(MeetingInspectionError::Quarantine);
        }
        let bytes = bounded_read(
            &directory.join(&current.relative_path),
            limits.max_transcript_bytes,
            total,
            limits,
        )?;
        let document: Transcript =
            serde_json::from_slice(&bytes).map_err(|_| MeetingInspectionError::Quarantine)?;
        (
            Some(current.sha256.clone()),
            Some(current.relative_path.clone()),
            validate_transcript(document)?,
            Some(actual),
        )
    } else {
        // The closed lifecycle table admits these rows for metadata only.  No
        // transcript bytes or transcript search authority are inferred.
        (None, None, Vec::new(), None)
    };
    let (note_json_sha256, note_markdown_sha256, claims) = if meeting.lifecycle
        == MeetingLifecycle::Ready
    {
        let note = meeting
            .artifacts
            .current_note
            .as_ref()
            .ok_or(MeetingInspectionError::Quarantine)?;
        let request = ProjectRequest {
            request_id: Uuid::new_v4(),
            meeting_id: meeting.meeting_id.clone(),
            note_json_sha256: note.json.sha256.clone(),
            note_markdown_sha256: note.markdown.sha256.clone(),
            transcript_sha256: transcript_sha256
                .clone()
                .ok_or(MeetingInspectionError::Quarantine)?,
        };
        let transcript_text: Vec<_> = turns.iter().map(|turn| turn.text.clone()).collect();
        let claims =
            project_claims(projector, &request, &transcript_text).map_err(|error| match error {
                ProjectionError::ArtifactMissing
                | ProjectionError::ArtifactInvalid
                | ProjectionError::ArtifactChanged => MeetingInspectionError::Quarantine,
                ProjectionError::CapacityExceeded => MeetingInspectionError::CapacityExceeded,
                ProjectionError::Unavailable => MeetingInspectionError::Unavailable,
            })?;
        let claims = claims
            .into_iter()
            .map(|claim| StoredClaim {
                ordinal: claim.ordinal,
                sha256: claim.sha256,
                claim_type: claim.claim_type,
                text: claim.text,
                locators: claim.locators,
            })
            .collect();
        (
            Some(note.json.sha256.clone()),
            Some(note.markdown.sha256.clone()),
            claims,
        )
    } else {
        (None, None, Vec::new())
    };
    // Re-read the pointers after inspection before allowing this candidate into a snapshot.
    let again = load_meeting(directory).map_err(|_| MeetingInspectionError::Quarantine)?;
    if again != meeting
        || artifact_ref(directory, "meeting.json")
            .map_err(|_| MeetingInspectionError::Quarantine)?
            != meeting_record
        || artifact_ref(directory, "attempt.json")
            .map_err(|_| MeetingInspectionError::Quarantine)?
            != attempt
        || current_artifact.as_ref().is_some_and(|actual| {
            artifact_ref(directory, &actual.relative_path)
                .map(|again| again != *actual)
                .unwrap_or(true)
        })
        || meeting.artifacts.current_note.as_ref().is_some_and(|note| {
            artifact_ref(directory, &note.json.relative_path)
                .map(|again| again != note.json)
                .unwrap_or(true)
                || artifact_ref(directory, &note.markdown.relative_path)
                    .map(|again| again != note.markdown)
                    .unwrap_or(true)
        })
    {
        return Err(MeetingInspectionError::Quarantine);
    }
    Ok(Some(LibraryRow {
        meeting_id: meeting.meeting_id.clone(),
        created_at_epoch_seconds: attempt_data.created_at_epoch_seconds,
        transcript_sha256,
        lifecycle: meeting.lifecycle,
        meeting_record_sha256: meeting_record.sha256,
        transcript_relative_path,
        turns,
        note_json_sha256,
        note_markdown_sha256,
        claims,
        attempt_sha256: attempt.sha256,
        title: None,
        folder: None,
    }))
}

fn bounded_read(
    path: &Path,
    maximum: u64,
    total: &mut u64,
    limits: ReadLimits,
) -> Result<Vec<u8>, LibraryReadError> {
    let mut file = open_private_file(path).map_err(|_| LibraryReadError::ArtifactUnavailable)?;
    let length = file
        .metadata()
        .map_err(|_| LibraryReadError::ArtifactUnavailable)?
        .len();
    if length > maximum {
        return Err(LibraryReadError::CapacityExceeded);
    }
    *total = total
        .checked_add(length)
        .ok_or(LibraryReadError::CapacityExceeded)?;
    if *total > limits.max_total_bytes {
        return Err(LibraryReadError::CapacityExceeded);
    }
    let mut bytes = Vec::new();
    file.read_to_end(&mut bytes)
        .map_err(|_| LibraryReadError::ArtifactUnavailable)?;
    if bytes.len() as u64 != length {
        return Err(LibraryReadError::ArtifactUnavailable);
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
                || (document.attribution == "channel"
                    && turn.gated == Some(true)
                    && turn.speaker.as_deref() != Some("Me"))
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
        SealedHit::Claim { key, .. }
        | SealedHit::Transcript { key, .. }
        | SealedHit::Withheld { key, .. }
        | SealedHit::Meeting { key, .. } => key,
    }
}
fn hit_meeting_id(hit: &SealedHit) -> &str {
    match hit {
        SealedHit::Claim { authority, .. }
        | SealedHit::Transcript { authority, .. }
        | SealedHit::Withheld { authority, .. }
        | SealedHit::Meeting { authority, .. } => &authority.meeting_id,
    }
}
fn hit_authority(hit: &SealedHit) -> &HitAuthority {
    match hit {
        SealedHit::Claim { authority, .. }
        | SealedHit::Transcript { authority, .. }
        | SealedHit::Withheld { authority, .. }
        | SealedHit::Meeting { authority, .. } => authority,
    }
}
fn hit_order(left: &SealedHit, right: &SealedHit) -> std::cmp::Ordering {
    hit_kind(left).cmp(&hit_kind(right)).then_with(|| {
        let (lc, li) = hit_sort(left);
        let (rc, ri) = hit_sort(right);
        rc.cmp(&lc)
            .then_with(|| hit_meeting_id(left).cmp(hit_meeting_id(right)))
            .then_with(|| li.cmp(&ri))
            .then_with(|| hit_key(left).cmp(hit_key(right)))
    })
}
fn hit_kind(hit: &SealedHit) -> u8 {
    match hit {
        SealedHit::Claim { .. } => 0,
        SealedHit::Transcript { .. } | SealedHit::Withheld { .. } => 1,
        SealedHit::Meeting { .. } => 2,
    }
}
fn hit_sort(hit: &SealedHit) -> (u64, u64) {
    match hit {
        SealedHit::Claim {
            authority, claim, ..
        } => (authority_created(authority), claim.ordinal),
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
        SealedHit::Meeting { authority, .. } => (authority_created(authority), u64::MAX),
    }
}
fn authority_created(authority: &HitAuthority) -> u64 {
    authority.created_at_epoch_seconds
}

#[cfg(test)]
mod tests {
    use std::fs;
    use std::path::{Path, PathBuf};
    use std::sync::{Arc, Mutex};

    use serde_json::json;
    use sha2::{Digest, Sha256};
    use tempfile::TempDir;

    use super::*;
    use crate::meeting::{
        ArtifactRef, AudioRetention, AudioRetentionRule, AudioState, MeetingArtifacts,
        MeetingRecord, MeetingSchema, artifact_ref, retention_policy_sha256, write_meeting,
    };
    use crate::note_projection::{NoteProjector, ProjectRequest, ProjectTransportError};
    use crate::storage::{create_private_dir, durable_create_new};

    macro_rules! assert_stale {
        ($result:expr) => {
            assert!(matches!($result, Err(LibraryReadError::SnapshotStale)));
        };
    }

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

        fn metadata(&self, bytes: &[u8]) -> PathBuf {
            let library = self.storage.path().join("library");
            create_private_dir(&library).unwrap();
            let path = library.join("metadata.json");
            if path.exists() {
                fs::remove_file(&path).unwrap();
            }
            durable_create_new(&path, bytes).unwrap();
            path
        }

        fn ready_meeting(&self, id: &str, created: u64) -> PathBuf {
            let directory = self.meeting(
                id,
                created,
                &[
                    ("alpha", false),
                    ("beta", false),
                    ("gamma", false),
                    ("aé🙂z", false),
                ],
            );
            let mut record = load_meeting(&directory).unwrap();
            create_private_dir(&directory.join("notes")).unwrap();
            let json = b"{}\n";
            let markdown = b"# private\n";
            let json_digest = digest_bytes(json);
            let markdown_digest = digest_bytes(markdown);
            let json_path = format!("notes/{json_digest}.json");
            let markdown_path = format!("notes/{markdown_digest}.md");
            durable_create_new(&directory.join(&json_path), json).unwrap();
            durable_create_new(&directory.join(&markdown_path), markdown).unwrap();
            let transcript = record
                .artifacts
                .current_transcript
                .as_ref()
                .unwrap()
                .sha256
                .clone();
            record.lifecycle = MeetingLifecycle::Ready;
            record.artifacts.current_note = Some(crate::meeting::NoteRevisionRef {
                json: artifact_ref(&directory, &json_path).unwrap(),
                markdown: artifact_ref(&directory, &markdown_path).unwrap(),
                source_transcript_sha256: transcript,
            });
            write_meeting(&directory, &record).unwrap();
            directory
        }

        fn metadata_only_meeting(
            &self,
            id: &str,
            created: u64,
            lifecycle: MeetingLifecycle,
        ) -> PathBuf {
            let directory = self.meeting(id, created, &[("unsearched", false)]);
            let mut record = load_meeting(&directory).unwrap();
            record.lifecycle = lifecycle;
            record.artifacts.current_transcript = None;
            record.artifacts.current_note = None;
            match lifecycle {
                MeetingLifecycle::Incomplete => {
                    record.artifacts.ownership = None;
                    record.artifacts.capture_session = None;
                    record.artifacts.microphone_audio = None;
                    record.artifacts.system_audio = None;
                    record.retention.state = AudioState::NeverCreated;
                    record.retention.deletion_receipt = None;
                }
                MeetingLifecycle::Captured | MeetingLifecycle::TranscriptionFailed => {}
                MeetingLifecycle::RecoveredInterrupted => {
                    record.artifacts.ownership = None;
                    record.artifacts.capture_session = None;
                    record.artifacts.microphone_audio = None;
                    record.artifacts.system_audio = None;
                    record.retention.state = AudioState::NeverCreated;
                    record.retention.deletion_receipt = None;
                }
                _ => panic!("fixture only supports metadata-only lifecycles"),
            }
            write_meeting(&directory, &record).unwrap();
            directory
        }
    }

    #[derive(Clone, Copy)]
    enum ProjectorMode {
        Success,
        Refusal(&'static str),
        Transport,
    }

    struct FixtureProjector(Mutex<ProjectorMode>);

    impl FixtureProjector {
        fn new(mode: ProjectorMode) -> Self {
            Self(Mutex::new(mode))
        }
        fn set(&self, mode: ProjectorMode) {
            *self.0.lock().unwrap() = mode;
        }
    }

    impl NoteProjector for FixtureProjector {
        fn project(&self, request: &ProjectRequest) -> Result<Vec<u8>, ProjectTransportError> {
            match *self.0.lock().unwrap() {
                ProjectorMode::Transport => Err(ProjectTransportError),
                ProjectorMode::Refusal(code) => {
                    Ok(format!("{{\"schema\":\"note-projection-result/1\",\"request_id\":\"{}\",\"operation\":\"note.project\",\"outcome\":\"refused\",\"projection\":null,\"failure\":{{\"code\":\"{code}\",\"recoverable\":{}}}}}\n", request.request_id, code == "artifact-missing").into_bytes())
                }
                ProjectorMode::Success => {
                    let locator = "{\"turn\":0,\"start\":0,\"end\":5,\"text_sha256\":\"8ed3f6ad685b959ead7022518e1af76cd816f8e8ec7ccdda1ed4018e8f2223f8\"}";
                    let claims = (0..3)
                        .map(|ordinal| format!("{{\"claim_ordinal\":{ordinal},\"claim_sha256\":\"b8eccd74fe344c3e91654493ed1cc69e9b637cf8dd0ed2d2884f2375bd15c4f2\",\"claim_type\":\"decision\",\"evidence_state\":\"located\",\"claim\":\"claim-a\",\"locators\":[{locator}]}}"))
                        .collect::<Vec<_>>()
                        .join(",");
                    Ok(format!("{{\"schema\":\"note-projection-result/1\",\"request_id\":\"{}\",\"operation\":\"note.project\",\"outcome\":\"succeeded\",\"projection\":{{\"schema\":\"note-claim-projection/1\",\"note_json_sha256\":\"{}\",\"note_markdown_sha256\":\"{}\",\"transcript_sha256\":\"{}\",\"claims\":[{claims}]}},\"failure\":null}}\n", request.request_id, request.note_json_sha256, request.note_markdown_sha256, request.transcript_sha256).into_bytes())
                }
            }
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
    fn current_claims_use_fixture_projection_preserve_duplicate_ordinals_and_reinspect_on_open() {
        let fixture = Fixture::new();
        fixture.ready_meeting("meeting-a", 10);
        let projector = Arc::new(FixtureProjector::new(ProjectorMode::Success));
        let projection = LibraryProjection::rebuild_with_projector(
            &fixture.storage,
            ReadLimits::default(),
            projector.clone(),
        )
        .unwrap();
        let hits = projection.search("a").unwrap();
        assert!(matches!(
            projection.sealed(&hits[0]),
            Some(SealedHit::Claim {
                claim: StoredClaim { ordinal: 0, .. },
                ..
            })
        ));
        let claim_hits = projection.search("claim-a").unwrap();
        assert_eq!(claim_hits.len(), 3, "same text remains distinct by ordinal");
        for (ordinal, hit) in claim_hits.iter().enumerate() {
            assert!(
                matches!(projection.open(&fixture.storage, hit).unwrap(), OpenedLibraryHit::Claim { claim_ordinal, ref claim, .. } if claim_ordinal == ordinal as u64 && claim == "claim-a")
            );
        }
        projector.set(ProjectorMode::Refusal("artifact-changed"));
        assert_stale!(projection.open(&fixture.storage, &claim_hits[0]));

        let fixture = Fixture::new();
        let directory = fixture.ready_meeting("meeting-a", 10);
        let projector = Arc::new(FixtureProjector::new(ProjectorMode::Success));
        let projection = LibraryProjection::rebuild_with_projector(
            &fixture.storage,
            ReadLimits::default(),
            projector,
        )
        .unwrap();
        let hit = projection.search("claim-a").unwrap().remove(0);
        let note = load_meeting(&directory)
            .unwrap()
            .artifacts
            .current_note
            .unwrap();
        fs::write(directory.join(note.json.relative_path), b"changed").unwrap();
        assert_stale!(projection.open(&fixture.storage, &hit));
    }

    #[test]
    fn projection_failures_never_publish_partial_ready_meetings() {
        for (mode, expected) in [
            (
                ProjectorMode::Refusal("projection-capacity-exceeded"),
                LibraryReadError::CapacityExceeded,
            ),
            (
                ProjectorMode::Refusal("invalid-request"),
                LibraryReadError::ArtifactUnavailable,
            ),
            (
                ProjectorMode::Transport,
                LibraryReadError::ArtifactUnavailable,
            ),
        ] {
            let fixture = Fixture::new();
            fixture.ready_meeting("meeting-a", 10);
            fixture.ready_meeting("meeting-b", 9);
            let projector = Arc::new(FixtureProjector::new(mode));
            assert!(matches!(
                LibraryProjection::rebuild_with_projector(
                    &fixture.storage,
                    ReadLimits::default(),
                    projector,
                ),
                Err(actual) if actual == expected
            ));
        }
    }

    #[test]
    fn artifact_refusals_quarantine_only_the_affected_ready_meeting() {
        for code in ["artifact-missing", "artifact-invalid", "artifact-changed"] {
            let fixture = Fixture::new();
            fixture.ready_meeting("meeting-a", 10);
            let projector = Arc::new(FixtureProjector::new(ProjectorMode::Refusal(code)));
            let projection = LibraryProjection::rebuild_with_projector(
                &fixture.storage,
                ReadLimits::default(),
                projector,
            )
            .unwrap();
            assert!(projection.rows().is_empty(), "{code}");
            assert_eq!(projection.quarantined_meetings(), 1, "{code}");
        }
    }

    #[test]
    fn missing_metadata_keeps_transcript_authority_and_valid_metadata_coalesces_meeting_hits() {
        let fixture = Fixture::new();
        fixture.meeting("meeting-a", 10, &[("transcript token", false)]);
        let missing = LibraryProjection::rebuild(&fixture.storage, ReadLimits::default()).unwrap();
        assert_eq!(missing.search("transcript").unwrap().len(), 1);
        assert!(missing.search("project").unwrap().is_empty());

        fixture.metadata(br#"{"schema":"library-metadata/1","revision":4,"folders":[{"id":"11111111-1111-4111-8111-111111111111","name":"Project Atlas"}],"meetings":[{"meeting_id":"meeting-a","title":"Project kickoff","folder_id":"11111111-1111-4111-8111-111111111111"}]}"#);
        let projection =
            LibraryProjection::rebuild(&fixture.storage, ReadLimits::default()).unwrap();
        let title = projection.search("project").unwrap();
        assert_eq!(title.len(), 1, "title and folder are one meeting hit");
        assert!(
            matches!(projection.open(&fixture.storage, &title[0]).unwrap(), OpenedLibraryHit::Meeting { ref title, ref folder, .. } if title.as_deref() == Some("Project kickoff") && folder.as_deref() == Some("Project Atlas"))
        );
        assert_eq!(projection.search("transcript").unwrap().len(), 1);
    }

    #[test]
    fn every_safe_metadata_only_lifecycle_is_projected_without_transcript_authority() {
        let fixture = Fixture::new();
        let cases = [
            ("meeting-a", MeetingLifecycle::Incomplete),
            ("meeting-b", MeetingLifecycle::Captured),
            ("meeting-c", MeetingLifecycle::TranscriptionFailed),
            ("meeting-d", MeetingLifecycle::RecoveredInterrupted),
        ];
        for (offset, (id, lifecycle)) in cases.iter().enumerate() {
            fixture.metadata_only_meeting(id, 10 + offset as u64, *lifecycle);
        }
        fixture.meeting("meeting-z", 20, &[("transcript token", false)]);
        fixture.metadata(br#"{"schema":"library-metadata/1","revision":1,"folders":[],"meetings":[{"meeting_id":"meeting-a","title":"Organizer a","folder_id":null},{"meeting_id":"meeting-b","title":"Organizer b","folder_id":null},{"meeting_id":"meeting-c","title":"Organizer c","folder_id":null},{"meeting_id":"meeting-d","title":"Organizer d","folder_id":null}]}"#);

        let projection =
            LibraryProjection::rebuild(&fixture.storage, ReadLimits::default()).unwrap();
        assert_eq!(projection.rows().len(), 5);
        assert_eq!(projection.search("organizer").unwrap().len(), 4);
        assert_eq!(projection.search("transcript").unwrap().len(), 1);
        for (id, lifecycle) in cases {
            let row = projection
                .rows()
                .iter()
                .find(|row| row.meeting_id == id)
                .unwrap();
            assert_eq!(row.lifecycle, lifecycle);
            assert_eq!(row.transcript_sha256, None);
            assert!(row.turns.is_empty());
        }
    }

    #[cfg(target_os = "macos")]
    #[test]
    fn metadata_fifo_never_blocks_the_projection() {
        use std::ffi::CString;
        use std::time::{Duration, Instant};
        let fixture = Fixture::new();
        fixture.meeting("meeting-a", 10, &[("transcript token", false)]);
        let library = fixture.storage.path().join("library");
        create_private_dir(&library).unwrap();
        let fifo =
            CString::new(library.join("metadata.json").as_os_str().as_encoded_bytes()).unwrap();
        assert_eq!(unsafe { libc::mkfifo(fifo.as_ptr(), 0o600) }, 0);
        let started = Instant::now();
        let projection =
            LibraryProjection::rebuild(&fixture.storage, ReadLimits::default()).unwrap();
        assert!(started.elapsed() < Duration::from_secs(1));
        assert_eq!(projection.search("transcript").unwrap().len(), 1);
        assert!(projection.search("metadata").unwrap().is_empty());
    }

    #[test]
    fn malformed_metadata_loses_only_label_authority() {
        let cases: &[&[u8]] = &[
            br#"{"schema":"library-metadata/1","revision":0,"folders":[],"meetings":[],"extra":true}"#,
            br#"{"schema":"library-metadata/1","revision":0,"folders":[],"meetings":[],"meetings":[]}"#,
            br#"{"schema":"library-metadata/1","revision":0,"folders":[],"meetings":[{"meeting_id":"meeting-a","title":null}]}"#,
            br#"{"schema":"library-metadata/1","revision":0,"folders":[{"name":"x","id":"11111111-1111-4111-8111-111111111111"}],"meetings":[]}"#,
            br#"{"schema":"library-metadata/1","revision":0,"folders":[{"id":"11111111-1111-4111-8111-111111111111","name":"e\u0301"}],"meetings":[]}"#,
            br#"{"schema":"library-metadata/1","revision":0,"folders":[{"id":"11111111-1111-4111-8111-111111111111","name":"a"},{"id":"00000000-0000-4000-8000-000000000000","name":"b"}],"meetings":[]}"#,
            br#"{"schema":"library-metadata/1","revision":0,"folders":[{"id":"11111111-1111-4111-8111-111111111111","name":"a"},{"id":"11111111-1111-4111-8111-111111111111","name":"b"}],"meetings":[]}"#,
            br#"{"schema":"library-metadata/1","revision":0,"folders":[{"id":"11111111-1111-4111-4111-111111111111","name":"a"}],"meetings":[]}"#,
            br#"{"schema":"library-metadata/1","revision":0,"folders":[{"id":"11111111-1111-4111-8111-11111111111A","name":"a"}],"meetings":[]}"#,
            br#"{"schema":"library-metadata/1","revision":0,"folders":[{"id":"11111111-1111-4111-8111-111111111111","name":"a"}],"meetings":[{"meeting_id":"meeting-a","title":null,"folder_id":"11111111-1111-4111-8111-111111111111"},{"meeting_id":"meeting-a","title":null,"folder_id":null}]}"#,
            br#"{"schema":"library-metadata/1","revision":0,"folders":[{"id":"11111111-1111-4111-8111-111111111111","name":"a"}],"meetings":[{"meeting_id":"meeting-a","title":null,"folder_id":"11111111-1111-4111-8111-111111111111"},{"meeting_id":"meeting-a","title":null,"folder_id":null}]}"#,
            br#"{"schema":"library-metadata/1","revision":0,"folders":[{"id":"11111111-1111-4111-8111-111111111111","name":"a"}],"meetings":[{"meeting_id":"meeting-a","title":null,"folder_id":"22222222-2222-4222-8222-222222222222"}]}"#,
            br#"{"schema":"library-metadata/1","revision":0,"folders":[],"meetings":[{"meeting_id":"unknown","title":"x","folder_id":null}]}"#,
            br#"{"schema":"library-metadata/1","revision":0,"folders":[],"meetings":[{"meeting_id":"meeting-a","title":"x/y","folder_id":null}]}"#,
        ];
        for bytes in cases {
            let fixture = Fixture::new();
            fixture.meeting("meeting-a", 10, &[("transcript token", false)]);
            fixture.metadata(bytes);
            let projection =
                LibraryProjection::rebuild(&fixture.storage, ReadLimits::default()).unwrap();
            assert!(projection.search("x").unwrap().is_empty());
            assert_eq!(projection.search("transcript").unwrap().len(), 1);
        }
    }

    #[test]
    fn every_metadata_state_change_stales_prior_hits() {
        let fixture = Fixture::new();
        fixture.meeting("meeting-a", 10, &[("transcript token", false)]);
        let missing = LibraryProjection::rebuild(&fixture.storage, ReadLimits::default()).unwrap();
        let missing_hit = missing.search("transcript").unwrap().remove(0);
        fixture.metadata(br#"{"schema":"library-metadata/1","revision":1,"folders":[],"meetings":[{"meeting_id":"meeting-a","title":"first","folder_id":null}]}"#);
        assert_stale!(missing.open(&fixture.storage, &missing_hit));

        let variants: &[Option<&[u8]>] = &[
            Some(br#"{ "schema" : "library-metadata/1", "revision" : 1, "folders" : [], "meetings" : [{ "meeting_id" : "meeting-a", "title" : "first", "folder_id" : null }] }"#),
            Some(br#"{"schema":"library-metadata/1","revision":1,"folders":[],"meetings":[{"meeting_id":"meeting-a","title":"other","folder_id":null}]}"#),
            Some(br#"{"schema":"library-metadata/1","revision":2,"folders":[],"meetings":[{"meeting_id":"meeting-a","title":"first","folder_id":null}]}"#),
            None,
        ];
        for replacement in variants {
            let fixture = Fixture::new();
            fixture.meeting("meeting-a", 10, &[("transcript token", false)]);
            fixture.metadata(br#"{"schema":"library-metadata/1","revision":1,"folders":[],"meetings":[{"meeting_id":"meeting-a","title":"first","folder_id":null}]}"#);
            let projection =
                LibraryProjection::rebuild(&fixture.storage, ReadLimits::default()).unwrap();
            let hit = projection.search("first").unwrap().remove(0);
            let path = fixture.storage.path().join("library/metadata.json");
            match replacement {
                Some(bytes) => {
                    fs::remove_file(&path).unwrap();
                    durable_create_new(&path, bytes).unwrap();
                }
                None => fs::remove_file(&path).unwrap(),
            }
            assert_stale!(projection.open(&fixture.storage, &hit));
        }
    }

    #[test]
    fn unsafe_metadata_nodes_fail_closed_without_losing_transcript_rows() {
        for fault in ["symlink", "hard-link", "mode", "oversize"] {
            let fixture = Fixture::new();
            fixture.meeting("meeting-a", 10, &[("transcript token", false)]);
            let path = fixture.metadata(br#"{"schema":"library-metadata/1","revision":1,"folders":[],"meetings":[{"meeting_id":"meeting-a","title":"private title","folder_id":null}]}"#);
            match fault {
                "symlink" => {
                    let target = fixture.storage.path().join("library/target.json");
                    fs::rename(&path, &target).unwrap();
                    std::os::unix::fs::symlink("target.json", &path).unwrap();
                }
                "hard-link" => {
                    fs::hard_link(&path, fixture.storage.path().join("library/other.json"))
                        .unwrap();
                }
                "mode" => {
                    use std::os::unix::fs::PermissionsExt;
                    fs::set_permissions(&path, fs::Permissions::from_mode(0o644)).unwrap();
                }
                "oversize" => {
                    fs::write(&path, vec![b'x'; 1024 * 1024 + 1]).unwrap();
                }
                _ => unreachable!(),
            }
            let projection =
                LibraryProjection::rebuild(&fixture.storage, ReadLimits::default()).unwrap();
            assert!(projection.search("private").unwrap().is_empty(), "{fault}");
            assert_eq!(projection.search("transcript").unwrap().len(), 1, "{fault}");
        }
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
    fn channel_attribution_withholds_only_microphone_turns() {
        let fixture = Fixture::new();
        let directory = fixture.meeting("meeting-a", 10, &[("hidden token", true)]);
        let mut record = load_meeting(&directory).unwrap();
        let transcript = serde_json::to_vec_pretty(&json!({
            "schema": "capture-transcript/1",
            "source": "synthetic",
            "attribution": "channel",
            "bleed": null,
            "voiceprint": null,
            "capture_health": {},
            "turns": [{
                "start": 0.0,
                "end": 0.5,
                "speaker": "Them",
                "text": "hidden token",
                "gated": true,
            }],
        }))
        .unwrap();
        let digest = format!("{:x}", Sha256::digest(&transcript));
        let relative = format!("transcript/{digest}.json");
        durable_create_new(&directory.join(&relative), &transcript).unwrap();
        record.artifacts.current_transcript = Some(artifact_ref(&directory, &relative).unwrap());
        write_meeting(&directory, &record).unwrap();

        let projection =
            LibraryProjection::rebuild(&fixture.storage, ReadLimits::default()).unwrap();
        assert!(projection.rows().is_empty());
        assert_eq!(projection.quarantined_meetings(), 1);
    }

    #[test]
    fn open_fails_closed_when_any_bound_artifact_drifts() {
        for target in [
            "meeting",
            "attempt",
            "ownership",
            "capture",
            "deletion",
            "transcript",
        ] {
            let fixture = Fixture::new();
            let directory = fixture.meeting("meeting-a", 10, &[("stable token", false)]);
            let projection =
                LibraryProjection::rebuild(&fixture.storage, ReadLimits::default()).unwrap();
            let hit = projection.search("stable").unwrap().remove(0);
            match target {
                "meeting" => fs::write(directory.join("meeting.json"), b"{}").unwrap(),
                "attempt" => fs::write(directory.join("attempt.json"), b"{}").unwrap(),
                "ownership" => fs::write(directory.join("ownership.json"), b"{}").unwrap(),
                "capture" => fs::write(directory.join("capture/session.json"), b"{}").unwrap(),
                "deletion" => {
                    fs::write(directory.join("deletion/audio-deletion.json"), b"{}").unwrap()
                }
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
            assert_stale!(projection.open(&fixture.storage, &hit));
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
        assert_stale!(projection.open(&fixture.storage, &forged));
        let other = LibraryProjection::rebuild(&fixture.storage, ReadLimits::default()).unwrap();
        assert_stale!(projection.open(&fixture.storage, &other.search("stable").unwrap()[0]));
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
        assert_stale!(projection.open(&fixture.storage, &handle));

        let fixture = Fixture::new();
        let directory = fixture.meeting("meeting-a", 10, &[("stable token", false)]);
        let projection =
            LibraryProjection::rebuild(&fixture.storage, ReadLimits::default()).unwrap();
        let handle = projection.search("stable").unwrap().remove(0);
        let mut record = load_meeting(&directory).unwrap();
        durable_create_new(&directory.join("capture/mic.wav"), b"mic").unwrap();
        durable_create_new(&directory.join("capture/system.wav"), b"system").unwrap();
        record.artifacts.microphone_audio =
            Some(artifact_ref(&directory, "capture/mic.wav").unwrap());
        record.artifacts.system_audio =
            Some(artifact_ref(&directory, "capture/system.wav").unwrap());
        record.retention.state = AudioState::Retained;
        record.retention.deletion_receipt = None;
        write_meeting(&directory, &record).unwrap();
        assert_stale!(projection.open(&fixture.storage, &handle));

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
        assert_stale!(projection.open(&fixture.storage, &handle));
    }

    #[test]
    fn transcript_search_and_limits_refuse_whole_build() {
        let fixture = Fixture::new();
        let directory = fixture.meeting("meeting-a", 10, &[("token", false)]);
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
        assert!(matches!(
            LibraryProjection::rebuild(
                &fixture.storage,
                ReadLimits {
                    max_transcript_bytes: 1,
                    ..ReadLimits::default()
                }
            ),
            Err(LibraryReadError::CapacityExceeded)
        ));
        let meeting_bytes = fs::metadata(directory.join("meeting.json")).unwrap().len();
        let deletion_bytes = fs::metadata(directory.join("deletion/audio-deletion.json"))
            .unwrap()
            .len();
        assert!(matches!(
            LibraryProjection::rebuild(
                &fixture.storage,
                ReadLimits {
                    max_total_bytes: meeting_bytes + deletion_bytes,
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

    #[test]
    fn pinned_rust_compiler_matches_normalization_contract() {
        let output = std::process::Command::new("rustc")
            .arg("-Vv")
            .output()
            .expect("rustc must be on PATH for Rust tests");
        let version = String::from_utf8(output.stdout).expect("rustc version is UTF-8");
        assert!(output.status.success());
        assert!(version.contains("release: 1.94.0"));
        assert!(version.contains(SEARCH_NORMALIZATION_RUST_COMMIT));
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

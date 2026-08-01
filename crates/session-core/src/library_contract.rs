//! Closed fixture parser for the unregistered library boundary.
//!
//! This module intentionally has no storage, index, or Tauri dependency. It
//! freezes the bytes and shapes that a later storage-backed coordinator must
//! consume before that boundary can be registered.

use std::ops::Range;

use icu_normalizer::ComposingNormalizerBorrowed;
use serde::{Deserialize, Serialize, de::DeserializeOwned};
use serde_json::Value;
use thiserror::Error;
use unicode_segmentation::UnicodeSegmentation;

macro_rules! schema {
    ($name:ident, $wire:literal) => {
        #[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
        pub enum $name {
            #[serde(rename = $wire)]
            V1,
        }
    };
}

schema!(LibraryOperationsSchema, "library-operations/1");
schema!(SearchNormalizationSchema, "search-normalization/1");
schema!(LibrarySnapshotSchema, "library-snapshot/1");
schema!(LibrarySearchResultSchema, "library-search-result/1");
schema!(LibrarySearchHitSchema, "library-search-hit/1");
schema!(LibraryHitSchema, "library-hit/1");
schema!(LibraryMetadataResultSchema, "library-metadata-result/1");
schema!(LibraryErrorSchema, "library-error/1");

#[derive(Debug, Error, PartialEq, Eq)]
pub enum LibraryContractError {
    #[error("invalid library contract JSON")]
    InvalidJson,
    #[error("library contract is not canonical two-space JSON")]
    NonCanonicalJson,
    #[error("fixture operation shape does not match its operation name")]
    OperationShape,
    #[error("runtime content cannot use the fixture redaction sentinel")]
    RedactionSentinel,
    #[error("hit locator cannot land on an empty or reversed source span")]
    MalformedLanding,
    #[error("normalization query is empty")]
    EmptyQuery,
}

/// Parses an application-boundary object only when its bytes are canonical
/// two-space JSON without a terminal newline. Serde's closed structs reject
/// unknown and duplicate fields before this byte check freezes key order.
pub fn parse_canonical<T>(bytes: &[u8]) -> Result<T, LibraryContractError>
where
    T: DeserializeOwned + Serialize,
{
    let parsed = serde_json::from_slice(bytes).map_err(|_| LibraryContractError::InvalidJson)?;
    let canonical =
        serde_json::to_vec_pretty(&parsed).map_err(|_| LibraryContractError::InvalidJson)?;
    if canonical != bytes {
        return Err(LibraryContractError::NonCanonicalJson);
    }
    Ok(parsed)
}

/// Parses a runtime search hit after enforcing its content-bearing invariants.
/// Fixture redaction sentinels are intentionally rejected here and accepted only
/// by `parse_fixture`.
pub fn parse_runtime_search_hit(bytes: &[u8]) -> Result<SearchHit, LibraryContractError> {
    let hit: SearchHit = parse_canonical(bytes)?;
    hit.validate_runtime_content()?;
    Ok(hit)
}

/// Parses a runtime opened hit after enforcing its exact landing invariants.
/// Fixture redaction sentinels are intentionally rejected here and accepted only
/// by `parse_fixture`.
pub fn parse_runtime_open_hit(bytes: &[u8]) -> Result<OpenHit, LibraryContractError> {
    let hit: OpenHit = parse_canonical(bytes)?;
    hit.validate_runtime_content()?;
    Ok(hit)
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct NormalizationPin {
    pub schema: SearchNormalizationSchema,
    pub unicode_version: String,
    pub unicode_segmentation: String,
    pub unicode_segmentation_checksum: String,
    pub icu_normalizer: String,
    pub icu_normalizer_checksum: String,
    pub icu_normalizer_data: String,
    pub icu_normalizer_data_checksum: String,
    pub rustc_commit: String,
}

impl NormalizationPin {
    pub fn is_pinned(&self) -> bool {
        self.unicode_version == "17.0.0"
            && self.unicode_segmentation == "1.13.3"
            && self.unicode_segmentation_checksum
                == "c6f5d3c3b1bf09027a88a6bc961fc00497d651009560b5463668dc81b0fa87a8"
            && self.icu_normalizer == "2.2.0"
            && self.icu_normalizer_checksum
                == "c56e5ee99d6e3d33bd91c5d85458b6005a22140021cc324cea84dd0e72cff3b4"
            && self.icu_normalizer_data == "2.2.0"
            && self.icu_normalizer_data_checksum
                == "da3be0ae77ea334f4da67c12f149704f19f81d1adf7c51cf482943e84a2bad38"
            && self.rustc_commit == "4a4ef493e3a1488c6e321570238084b38948f6db"
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct LibraryFixture {
    pub schema: LibraryOperationsSchema,
    pub normalization: NormalizationPin,
    pub operations: Vec<FixtureOperation>,
    pub search_hit_variants: Vec<SearchHit>,
    pub open_hit_variants: Vec<OpenHit>,
    pub errors: Vec<LibraryError>,
    pub normalization_cases: Vec<NormalizationCase>,
    pub required_cases: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FixtureOperation {
    pub operation: LibraryOperation,
    pub arguments: Value,
    pub result: Value,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum LibraryOperation {
    #[serde(rename = "library_snapshot")]
    Snapshot,
    #[serde(rename = "library_snapshot_page")]
    SnapshotPage,
    #[serde(rename = "library_search")]
    Search,
    #[serde(rename = "open_library_hit")]
    OpenHit,
    #[serde(rename = "create_folder")]
    CreateFolder,
    #[serde(rename = "rename_folder")]
    RenameFolder,
    #[serde(rename = "delete_folder")]
    DeleteFolder,
    #[serde(rename = "assign_meeting_folder")]
    AssignMeetingFolder,
    #[serde(rename = "set_meeting_title")]
    SetMeetingTitle,
}

pub fn parse_fixture(bytes: &[u8]) -> Result<LibraryFixture, LibraryContractError> {
    let fixture: LibraryFixture =
        serde_json::from_slice(bytes).map_err(|_| LibraryContractError::InvalidJson)?;
    if !fixture.normalization.is_pinned() {
        return Err(LibraryContractError::OperationShape);
    }
    for operation in &fixture.operations {
        validate_fixture_operation(operation)?;
    }
    Ok(fixture)
}

fn parse_value<T: DeserializeOwned>(value: &Value) -> Result<T, LibraryContractError> {
    serde_json::from_value(value.clone()).map_err(|_| LibraryContractError::OperationShape)
}

fn validate_fixture_operation(operation: &FixtureOperation) -> Result<(), LibraryContractError> {
    match operation.operation {
        LibraryOperation::Snapshot => {
            let _: SnapshotArgs = parse_value(&operation.arguments)?;
            let _: LibrarySnapshot = parse_value(&operation.result)?;
        }
        LibraryOperation::SnapshotPage => {
            let _: SnapshotPageArgs = parse_value(&operation.arguments)?;
            let _: LibrarySnapshot = parse_value(&operation.result)?;
        }
        LibraryOperation::Search => {
            let _: LibrarySearchArgs = parse_value(&operation.arguments)?;
            let _: LibrarySearchResult = parse_value(&operation.result)?;
        }
        LibraryOperation::OpenHit => {
            let _: OpenLibraryHitArgs = parse_value(&operation.arguments)?;
            let _: OpenHit = parse_value(&operation.result)?;
        }
        LibraryOperation::CreateFolder => {
            let _: CreateFolderArgs = parse_value(&operation.arguments)?;
            let _: MetadataResult = parse_value(&operation.result)?;
        }
        LibraryOperation::RenameFolder => {
            let _: RenameFolderArgs = parse_value(&operation.arguments)?;
            let _: MetadataResult = parse_value(&operation.result)?;
        }
        LibraryOperation::DeleteFolder => {
            let _: DeleteFolderArgs = parse_value(&operation.arguments)?;
            let _: MetadataResult = parse_value(&operation.result)?;
        }
        LibraryOperation::AssignMeetingFolder => {
            let _: AssignMeetingFolderArgs = parse_value(&operation.arguments)?;
            let _: MetadataResult = parse_value(&operation.result)?;
        }
        LibraryOperation::SetMeetingTitle => {
            let _: SetMeetingTitleArgs = parse_value(&operation.arguments)?;
            let _: MetadataResult = parse_value(&operation.result)?;
        }
    }
    Ok(())
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SnapshotArgs {}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SnapshotPageArgs {
    pub snapshot_id: String,
    pub cursor: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum LibraryView {
    #[serde(rename = "all")]
    All,
    #[serde(rename = "recorded-actions")]
    RecordedActions,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct LibrarySearchArgs {
    pub snapshot_id: String,
    pub query: String,
    pub folder_id: Option<String>,
    pub start_epoch_seconds: Option<u64>,
    pub end_epoch_seconds: Option<u64>,
    pub view: LibraryView,
    pub cursor: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct OpenLibraryHitArgs {
    pub snapshot_id: String,
    pub hit_id: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CreateFolderArgs {
    pub expected_revision: u64,
    pub name: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RenameFolderArgs {
    pub folder_id: String,
    pub expected_revision: u64,
    pub name: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct DeleteFolderArgs {
    pub folder_id: String,
    pub expected_revision: u64,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct AssignMeetingFolderArgs {
    pub meeting_id: String,
    pub folder_id: Option<String>,
    pub expected_revision: u64,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SetMeetingTitleArgs {
    pub meeting_id: String,
    pub expected_revision: u64,
    pub title: Option<String>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum ContentState {
    #[serde(rename = "incomplete")]
    Incomplete,
    #[serde(rename = "captured")]
    Captured,
    #[serde(rename = "transcription-failed")]
    TranscriptionFailed,
    #[serde(rename = "recovered-interrupted")]
    RecoveredInterrupted,
    #[serde(rename = "transcript-only")]
    TranscriptOnly,
    #[serde(rename = "summary-failed")]
    SummaryFailed,
    #[serde(rename = "ready")]
    Ready,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum AudioState {
    #[serde(rename = "never-created")]
    NeverCreated,
    #[serde(rename = "retained")]
    Retained,
    #[serde(rename = "deleting")]
    Deleting,
    #[serde(rename = "released")]
    Released,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct LibraryCounts {
    pub valid_meetings: u64,
    pub searchable_meetings: u64,
    pub quarantined_meetings: u64,
    pub degraded_capture_meetings: u64,
    pub unknown_capture_meetings: u64,
    pub withheld_turns: u64,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Folder {
    pub id: String,
    pub name: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum CaptureHealthStatus {
    #[serde(rename = "clean")]
    Clean,
    #[serde(rename = "degraded")]
    Degraded,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CaptureHealth {
    pub status: CaptureHealthStatus,
    pub mic_dropouts: u64,
    pub system_dropouts: u64,
    pub tap_errors: u64,
    pub leg_span_mismatch: bool,
    pub mic_wall_shortfall: bool,
    pub system_wall_shortfall: bool,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct MeetingRow {
    pub meeting_id: String,
    pub content_state: ContentState,
    pub created_at_epoch_seconds: u64,
    pub title: Option<String>,
    pub folder_id: Option<String>,
    pub audio_state: AudioState,
    pub capture_health: Option<CaptureHealth>,
    pub withheld_turn_count: u64,
    pub searchable: bool,
}

/// Verifies the frozen meeting-page order without constructing a projection.
pub fn meeting_rows_are_total_ordered(rows: &[MeetingRow]) -> bool {
    rows.windows(2).all(|pair| {
        let current = &pair[0];
        let next = &pair[1];
        current.created_at_epoch_seconds > next.created_at_epoch_seconds
            || (current.created_at_epoch_seconds == next.created_at_epoch_seconds
                && current.meeting_id.as_bytes() < next.meeting_id.as_bytes())
    })
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum SnapshotState {
    #[serde(rename = "empty")]
    Empty,
    #[serde(rename = "populated")]
    Populated,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct LibrarySnapshot {
    pub schema: LibrarySnapshotSchema,
    pub snapshot_id: String,
    pub metadata_revision: u64,
    pub state: SnapshotState,
    pub counts: LibraryCounts,
    pub folders: Vec<Folder>,
    pub meetings: Vec<MeetingRow>,
    pub next_cursor: Option<String>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum SearchState {
    #[serde(rename = "results")]
    Results,
    #[serde(rename = "no-results")]
    NoResults,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum MeetingHitKind {
    #[serde(rename = "meeting")]
    Meeting,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum ClaimHitKind {
    #[serde(rename = "claim")]
    Claim,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum TranscriptHitKind {
    #[serde(rename = "transcript")]
    Transcript,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum WithheldHitKind {
    #[serde(rename = "withheld")]
    Withheld,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SearchMeetingHit {
    pub schema: LibrarySearchHitSchema,
    pub kind: MeetingHitKind,
    pub snapshot_id: String,
    pub hit_id: String,
    pub metadata_revision: u64,
    pub meeting_id: String,
    pub created_at_epoch_seconds: u64,
    pub content_state: ContentState,
    pub audio_state: AudioState,
    pub title: Option<String>,
    pub folder_id: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SearchClaimHit {
    pub schema: LibrarySearchHitSchema,
    pub kind: ClaimHitKind,
    pub snapshot_id: String,
    pub hit_id: String,
    pub metadata_revision: u64,
    pub meeting_id: String,
    pub created_at_epoch_seconds: u64,
    pub content_state: ContentState,
    pub audio_state: AudioState,
    pub preview: String,
    pub transcript_sha256: String,
    pub note_json_sha256: String,
    pub note_markdown_sha256: String,
    pub claim_sha256: String,
    pub source_turn: u64,
    pub source_start: u64,
    pub source_end: u64,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SearchTranscriptHit {
    pub schema: LibrarySearchHitSchema,
    pub kind: TranscriptHitKind,
    pub snapshot_id: String,
    pub hit_id: String,
    pub metadata_revision: u64,
    pub meeting_id: String,
    pub created_at_epoch_seconds: u64,
    pub content_state: ContentState,
    pub audio_state: AudioState,
    pub preview: String,
    pub transcript_sha256: String,
    pub source_turn: u64,
    pub source_start: u64,
    pub source_end: u64,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SearchWithheldHit {
    pub schema: LibrarySearchHitSchema,
    pub kind: WithheldHitKind,
    pub snapshot_id: String,
    pub hit_id: String,
    pub metadata_revision: u64,
    pub meeting_id: String,
    pub created_at_epoch_seconds: u64,
    pub content_state: ContentState,
    pub audio_state: AudioState,
    pub base_transcript_sha256: String,
    pub current_view_sha256: String,
    pub source_turn: u64,
    pub gate_state: GateState,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum GateState {
    #[serde(rename = "unresolved")]
    Unresolved,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(untagged)]
pub enum SearchHit {
    Meeting(SearchMeetingHit),
    Claim(SearchClaimHit),
    Transcript(SearchTranscriptHit),
    Withheld(SearchWithheldHit),
}

impl SearchHit {
    pub fn validate_runtime_content(&self) -> Result<(), LibraryContractError> {
        match self {
            Self::Claim(hit) => {
                if hit.preview.is_empty() {
                    Err(LibraryContractError::RedactionSentinel)
                } else if hit.source_start >= hit.source_end {
                    Err(LibraryContractError::MalformedLanding)
                } else {
                    Ok(())
                }
            }
            Self::Transcript(hit) => {
                if hit.preview.is_empty() {
                    Err(LibraryContractError::RedactionSentinel)
                } else if hit.source_start >= hit.source_end {
                    Err(LibraryContractError::MalformedLanding)
                } else {
                    Ok(())
                }
            }
            Self::Meeting(_) | Self::Withheld(_) => Ok(()),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct LibrarySearchResult {
    pub schema: LibrarySearchResultSchema,
    pub snapshot_id: String,
    pub metadata_revision: u64,
    pub state: SearchState,
    pub counts: LibraryCounts,
    pub hits: Vec<SearchHit>,
    pub next_cursor: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Locator {
    pub turn: u64,
    pub start: u64,
    pub end: u64,
    pub text_sha256: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum EvidenceState {
    #[serde(rename = "located")]
    Located,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct OpenMeetingHit {
    pub schema: LibraryHitSchema,
    pub kind: MeetingHitKind,
    pub snapshot_id: String,
    pub hit_id: String,
    pub metadata_revision: u64,
    pub meeting_id: String,
    pub created_at_epoch_seconds: u64,
    pub title: Option<String>,
    pub folder_id: Option<String>,
    pub content_state: ContentState,
    pub audio_state: AudioState,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct OpenClaimHit {
    pub schema: LibraryHitSchema,
    pub kind: ClaimHitKind,
    pub snapshot_id: String,
    pub hit_id: String,
    pub metadata_revision: u64,
    pub meeting_id: String,
    pub created_at_epoch_seconds: u64,
    pub content_state: ContentState,
    pub audio_state: AudioState,
    pub transcript_sha256: String,
    pub note_json_sha256: String,
    pub note_markdown_sha256: String,
    pub claim_sha256: String,
    pub locators: Vec<Locator>,
    pub evidence_state: EvidenceState,
    pub claim: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct OpenTranscriptHit {
    pub schema: LibraryHitSchema,
    pub kind: TranscriptHitKind,
    pub snapshot_id: String,
    pub hit_id: String,
    pub metadata_revision: u64,
    pub meeting_id: String,
    pub created_at_epoch_seconds: u64,
    pub content_state: ContentState,
    pub audio_state: AudioState,
    pub transcript_sha256: String,
    pub source_turn: u64,
    pub source_start: u64,
    pub source_end: u64,
    pub span: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct OpenWithheldHit {
    pub schema: LibraryHitSchema,
    pub kind: WithheldHitKind,
    pub snapshot_id: String,
    pub hit_id: String,
    pub metadata_revision: u64,
    pub meeting_id: String,
    pub created_at_epoch_seconds: u64,
    pub content_state: ContentState,
    pub audio_state: AudioState,
    pub base_transcript_sha256: String,
    pub current_view_sha256: String,
    pub source_turn: u64,
    pub gate_state: GateState,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(untagged)]
pub enum OpenHit {
    Meeting(OpenMeetingHit),
    Claim(OpenClaimHit),
    Transcript(OpenTranscriptHit),
    Withheld(OpenWithheldHit),
}

impl OpenHit {
    pub fn validate_runtime_content(&self) -> Result<(), LibraryContractError> {
        match self {
            Self::Claim(hit) if hit.claim.is_empty() => {
                Err(LibraryContractError::RedactionSentinel)
            }
            Self::Claim(hit)
                if hit
                    .locators
                    .iter()
                    .any(|locator| locator.start >= locator.end) =>
            {
                Err(LibraryContractError::MalformedLanding)
            }
            Self::Transcript(hit) if hit.span.is_empty() => {
                Err(LibraryContractError::RedactionSentinel)
            }
            Self::Transcript(hit) if hit.source_start >= hit.source_end => {
                Err(LibraryContractError::MalformedLanding)
            }
            _ => Ok(()),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct MetadataResult {
    pub schema: LibraryMetadataResultSchema,
    pub revision: u64,
    pub changed: bool,
    pub folder_id: Option<String>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum LibraryErrorCode {
    #[serde(rename = "invalid-request")]
    InvalidRequest,
    #[serde(rename = "snapshot-stale")]
    SnapshotStale,
    #[serde(rename = "library-rebuilding")]
    Rebuilding,
    #[serde(rename = "library-capacity-exceeded")]
    CapacityExceeded,
    #[serde(rename = "metadata-unavailable")]
    MetadataUnavailable,
    #[serde(rename = "artifact-unavailable")]
    ArtifactUnavailable,
    #[serde(rename = "metadata-revision-conflict")]
    MetadataRevisionConflict,
    #[serde(rename = "internal-error")]
    InternalError,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct LibraryError {
    pub schema: LibraryErrorSchema,
    pub code: LibraryErrorCode,
    pub recoverable: bool,
    pub current_revision: Option<u64>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct NormalizationCase {
    pub name: String,
    pub query: String,
    pub source: String,
    pub normalized: String,
    pub source_start: u32,
    pub source_end: u32,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct NormalizedField {
    pub normalized: String,
    /// One original Unicode-scalar range per scalar in `normalized`.
    pub origins: Vec<Range<u32>>,
}

pub fn normalize_with_origins(source: &str) -> NormalizedField {
    let normalizer = ComposingNormalizerBorrowed::new_nfc();
    let mut normalized = String::new();
    let mut origins = Vec::new();
    let mut scalar_start = 0_u32;
    for grapheme in source.graphemes(true) {
        let scalar_end = scalar_start + grapheme.chars().count() as u32;
        let nfc = normalizer.normalize(grapheme);
        for scalar in nfc.chars().flat_map(char::to_lowercase) {
            normalized.push(scalar);
            origins.push(scalar_start..scalar_end);
        }
        scalar_start = scalar_end;
    }
    NormalizedField {
        normalized,
        origins,
    }
}

pub fn normalize_query(query: &str) -> Result<String, LibraryContractError> {
    let normalized = normalize_with_origins(query).normalized;
    if normalized.is_empty() {
        Err(LibraryContractError::EmptyQuery)
    } else {
        Ok(normalized)
    }
}

/// Returns every grapheme-safe original scalar span for literal normalized matches.
pub fn exact_match_spans(
    source: &str,
    query: &str,
) -> Result<Vec<Range<u32>>, LibraryContractError> {
    let field = normalize_with_origins(source);
    let query = normalize_query(query)?;
    let query_scalar_len = query.chars().count();
    let mut scalar_offset = 0_usize;
    let mut spans = Vec::new();
    for (byte_offset, _) in field.normalized.match_indices(&query) {
        scalar_offset += field.normalized[..byte_offset].chars().count() - scalar_offset;
        let matched = &field.origins[scalar_offset..scalar_offset + query_scalar_len];
        let start = matched.iter().map(|range| range.start).min().unwrap();
        let end = matched.iter().map(|range| range.end).max().unwrap();
        spans.push(start..end);
    }
    Ok(spans)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn fixture_bytes() -> &'static [u8] {
        include_bytes!("../../../tests/fixtures/library-operations-v1.fixture")
    }

    fn fixture() -> LibraryFixture {
        parse_fixture(fixture_bytes()).unwrap()
    }

    fn operation(fixture: &LibraryFixture, operation: LibraryOperation) -> &FixtureOperation {
        fixture
            .operations
            .iter()
            .find(|candidate| candidate.operation == operation)
            .unwrap()
    }

    fn assert_unknown_field_refused<T: DeserializeOwned>(value: &Value) {
        let mut drifted = value.clone();
        drifted
            .as_object_mut()
            .unwrap()
            .insert("unexpected".to_owned(), Value::Bool(true));
        assert!(serde_json::from_value::<T>(drifted).is_err());
    }

    #[test]
    fn fixture_consumes_every_closed_operation_and_variant() {
        let parsed = fixture();
        assert_eq!(parsed.operations.len(), 9);
        assert_eq!(parsed.search_hit_variants.len(), 4);
        assert_eq!(parsed.open_hit_variants.len(), 3);
        assert_eq!(parsed.errors.len(), 8);
        assert!(
            parsed
                .required_cases
                .contains(&"meeting-101-pagination".to_owned())
        );
        assert!(
            parsed
                .required_cases
                .contains(&"cursor-query-filter-binding".to_owned())
        );
        assert!(
            parsed
                .required_cases
                .contains(&"multiple-claims-one-span".to_owned())
        );
    }

    #[test]
    fn rejects_unknown_duplicate_and_enum_drift_in_both_directions() {
        assert!(serde_json::from_str::<LibrarySearchArgs>(r#"{"snapshot_id":"a","query":"q","folder_id":null,"start_epoch_seconds":null,"end_epoch_seconds":null,"view":"semantic","cursor":null}"#).is_err());
        assert!(serde_json::from_str::<LibrarySearchArgs>(r#"{"snapshot_id":"a","query":"q","folder_id":null,"start_epoch_seconds":null,"end_epoch_seconds":null,"view":"all","cursor":null,"unexpected":true}"#).is_err());
        assert!(serde_json::from_str::<LibrarySearchArgs>(r#"{"snapshot_id":"a","query":"q","query":"again","folder_id":null,"start_epoch_seconds":null,"end_epoch_seconds":null,"view":"all","cursor":null}"#).is_err());
        let mut bytes = fixture_bytes().to_vec();
        let needle = b"\"unicode_version\": \"17.0.0\"";
        let index = bytes
            .windows(needle.len())
            .position(|window| window == needle)
            .unwrap();
        bytes[index + 20] = b'9';
        assert_eq!(
            parse_fixture(&bytes),
            Err(LibraryContractError::OperationShape)
        );
    }

    #[test]
    fn every_fixture_request_and_response_refuses_unknown_fields() {
        let parsed = fixture();
        for operation in &parsed.operations {
            match operation.operation {
                LibraryOperation::Snapshot => {
                    assert_unknown_field_refused::<SnapshotArgs>(&operation.arguments);
                    assert_unknown_field_refused::<LibrarySnapshot>(&operation.result);
                }
                LibraryOperation::SnapshotPage => {
                    assert_unknown_field_refused::<SnapshotPageArgs>(&operation.arguments);
                    assert_unknown_field_refused::<LibrarySnapshot>(&operation.result);
                }
                LibraryOperation::Search => {
                    assert_unknown_field_refused::<LibrarySearchArgs>(&operation.arguments);
                    assert_unknown_field_refused::<LibrarySearchResult>(&operation.result);
                }
                LibraryOperation::OpenHit => {
                    assert_unknown_field_refused::<OpenLibraryHitArgs>(&operation.arguments);
                    assert_unknown_field_refused::<OpenHit>(&operation.result);
                }
                LibraryOperation::CreateFolder => {
                    assert_unknown_field_refused::<CreateFolderArgs>(&operation.arguments);
                    assert_unknown_field_refused::<MetadataResult>(&operation.result);
                }
                LibraryOperation::RenameFolder => {
                    assert_unknown_field_refused::<RenameFolderArgs>(&operation.arguments);
                    assert_unknown_field_refused::<MetadataResult>(&operation.result);
                }
                LibraryOperation::DeleteFolder => {
                    assert_unknown_field_refused::<DeleteFolderArgs>(&operation.arguments);
                    assert_unknown_field_refused::<MetadataResult>(&operation.result);
                }
                LibraryOperation::AssignMeetingFolder => {
                    assert_unknown_field_refused::<AssignMeetingFolderArgs>(&operation.arguments);
                    assert_unknown_field_refused::<MetadataResult>(&operation.result);
                }
                LibraryOperation::SetMeetingTitle => {
                    assert_unknown_field_refused::<SetMeetingTitleArgs>(&operation.arguments);
                    assert_unknown_field_refused::<MetadataResult>(&operation.result);
                }
            }
        }
        for hit in &parsed.search_hit_variants {
            assert_unknown_field_refused::<SearchHit>(&serde_json::to_value(hit).unwrap());
        }
        for hit in &parsed.open_hit_variants {
            assert_unknown_field_refused::<OpenHit>(&serde_json::to_value(hit).unwrap());
        }
        for error in &parsed.errors {
            assert_unknown_field_refused::<LibraryError>(&serde_json::to_value(error).unwrap());
        }
        assert!(
            serde_json::from_str::<CreateFolderArgs>(
                r#"{"expected_revision":3,"expected_revision":4,"name":"folder"}"#
            )
            .is_err()
        );
    }

    #[test]
    fn canonical_parser_freezes_order_and_refuses_terminal_newline() {
        let canonical = br#"{
  "snapshot_id": "snapshot",
  "cursor": "cursor"
}"#;
        let _: SnapshotPageArgs = parse_canonical(canonical).unwrap();
        assert_eq!(
            parse_canonical::<SnapshotPageArgs>(
                b"{\"cursor\":\"cursor\",\"snapshot_id\":\"snapshot\"}"
            ),
            Err(LibraryContractError::NonCanonicalJson)
        );
        assert_eq!(
            parse_canonical::<SnapshotPageArgs>(
                b"{\n  \"snapshot_id\": \"snapshot\",\n  \"cursor\": \"cursor\"\n}\n"
            ),
            Err(LibraryContractError::NonCanonicalJson)
        );
    }

    #[test]
    fn normalization_maps_fixture_cases_to_grapheme_safe_origins() {
        for case in &fixture().normalization_cases {
            let field = normalize_with_origins(&case.source);
            assert_eq!(field.normalized, case.normalized, "{}", case.name);
            assert!(
                exact_match_spans(&case.source, &case.query)
                    .unwrap()
                    .contains(&(case.source_start..case.source_end)),
                "{}",
                case.name
            );
        }
    }

    #[test]
    fn pagination_keeps_the_whole_snapshot_and_opaque_cursor_binding() {
        let parsed = fixture();
        let first: LibrarySnapshot =
            parse_value(&operation(&parsed, LibraryOperation::Snapshot).result).unwrap();
        let page_args: SnapshotPageArgs =
            parse_value(&operation(&parsed, LibraryOperation::SnapshotPage).arguments).unwrap();
        let second: LibrarySnapshot =
            parse_value(&operation(&parsed, LibraryOperation::SnapshotPage).result).unwrap();
        assert_eq!(page_args.snapshot_id, first.snapshot_id);
        assert_eq!(Some(page_args.cursor), first.next_cursor);
        assert_eq!(first.counts, second.counts);
        assert_eq!(first.folders, second.folders);
        assert!(
            first.meetings[0].created_at_epoch_seconds
                > second.meetings[0].created_at_epoch_seconds
        );
        assert!(meeting_rows_are_total_ordered(&first.meetings));
        let mut tied = first.meetings.clone();
        tied.push(MeetingRow {
            meeting_id: "meeting-0000".to_owned(),
            created_at_epoch_seconds: tied[0].created_at_epoch_seconds,
            ..tied[0].clone()
        });
        assert!(!meeting_rows_are_total_ordered(&tied));

        // A cursor is opaque request data, not a query field: another query has
        // a different canonical request byte sequence and cannot be mistaken
        // for the fixture's first search request by a future coordinator.
        let mut search: LibrarySearchArgs =
            parse_value(&operation(&parsed, LibraryOperation::Search).arguments).unwrap();
        let original = serde_json::to_vec_pretty(&search).unwrap();
        search.query = "other-token".to_owned();
        assert_ne!(original, serde_json::to_vec_pretty(&search).unwrap());
    }

    #[test]
    fn tagged_hit_parsers_refuse_cross_variant_and_validate_landing() {
        assert!(serde_json::from_str::<SearchHit>(r#"{"schema":"library-search-hit/1","kind":"claim","snapshot_id":"s","hit_id":"h","metadata_revision":1,"meeting_id":"m","created_at_epoch_seconds":1,"content_state":"ready","audio_state":"released","title":null,"folder_id":null}"#).is_err());
        assert!(serde_json::from_str::<OpenHit>(r#"{"schema":"library-hit/1","kind":"withheld","snapshot_id":"s","hit_id":"h","metadata_revision":1,"meeting_id":"m","created_at_epoch_seconds":1,"content_state":"transcript-only","audio_state":"retained","base_transcript_sha256":"a","current_view_sha256":"b","source_turn":1,"gate_state":"resolved"}"#).is_err());
        let malformed: OpenHit = serde_json::from_str(r#"{"schema":"library-hit/1","kind":"transcript","snapshot_id":"s","hit_id":"h","metadata_revision":1,"meeting_id":"m","created_at_epoch_seconds":1,"content_state":"ready","audio_state":"released","transcript_sha256":"a","source_turn":1,"source_start":2,"source_end":1,"span":"x"}"#).unwrap();
        assert_eq!(
            malformed.validate_runtime_content(),
            Err(LibraryContractError::MalformedLanding)
        );
        let canonical = serde_json::to_vec_pretty(&malformed).unwrap();
        assert_eq!(
            parse_runtime_open_hit(&canonical),
            Err(LibraryContractError::MalformedLanding)
        );
    }

    #[test]
    fn fixture_redaction_sentinels_are_never_runtime_content() {
        let parsed = fixture();
        for hit in &parsed.search_hit_variants {
            if matches!(hit, SearchHit::Claim(_) | SearchHit::Transcript(_)) {
                assert_eq!(
                    hit.validate_runtime_content(),
                    Err(LibraryContractError::RedactionSentinel)
                );
            }
        }
        for hit in &parsed.open_hit_variants {
            if matches!(hit, OpenHit::Transcript(_)) {
                assert_eq!(
                    hit.validate_runtime_content(),
                    Err(LibraryContractError::RedactionSentinel)
                );
            }
        }
    }

    #[test]
    fn withheld_is_a_closed_non_landing_variant() {
        let parsed = fixture();
        let withheld = parsed
            .search_hit_variants
            .iter()
            .find(|hit| matches!(hit, SearchHit::Withheld(_)))
            .unwrap();
        assert!(matches!(
            withheld,
            SearchHit::Withheld(SearchWithheldHit {
                gate_state: GateState::Unresolved,
                ..
            })
        ));
        let encoded = serde_json::to_value(withheld).unwrap();
        assert!(encoded.get("preview").is_none());
        assert!(encoded.get("source_start").is_none());
    }

    #[test]
    fn documented_claim_landing_is_parser_coverage_not_fixture_evidence() {
        let claim = OpenHit::Claim(OpenClaimHit {
            schema: LibraryHitSchema::V1,
            kind: ClaimHitKind::Claim,
            snapshot_id: "11111111-1111-4111-8111-111111111111".to_owned(),
            hit_id: "44444444-4444-4444-8444-444444444444".to_owned(),
            metadata_revision: 3,
            meeting_id: "meeting-0001".to_owned(),
            created_at_epoch_seconds: 1_785_600_000,
            content_state: ContentState::Ready,
            audio_state: AudioState::Released,
            transcript_sha256: "a".repeat(64),
            note_json_sha256: "b".repeat(64),
            note_markdown_sha256: "c".repeat(64),
            claim_sha256: "d".repeat(64),
            locators: vec![Locator {
                turn: 12,
                start: 4,
                end: 23,
                text_sha256: "e".repeat(64),
            }],
            evidence_state: EvidenceState::Located,
            claim: "x".to_owned(),
        });
        assert_eq!(claim.validate_runtime_content(), Ok(()));
        let canonical = serde_json::to_vec_pretty(&claim).unwrap();
        assert_eq!(parse_runtime_open_hit(&canonical), Ok(claim));
    }
}

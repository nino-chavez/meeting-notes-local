//! Private, read-only DTO adapter for an already-built meeting-library projection.
//!
//! This is deliberately not a Tauri command, state container, or storage builder.
//! Its only authority is to retain opaque projection handles long enough to reopen
//! the exact current claim or locator through `LibraryProjection`.

use std::collections::HashMap;

use local_meeting_notes_session_core::library_read::{
    ClaimEvidenceState, LibraryHit, LibraryProjection, OpenedLibraryHit,
};
use local_meeting_notes_session_core::meeting::MeetingLifecycle;
use local_meeting_notes_session_core::note_projection::ClaimType;
use local_meeting_notes_session_core::storage::StorageRoot;
use serde::Serialize;
use uuid::Uuid;

const STALE_MESSAGE: &str = "That view is no longer current. Reopen it and try again.";
const UNAVAILABLE_MESSAGE: &str = "The local library is unavailable. Reopen the app and try again.";

/// Owns only opaque handles into one immutable `LibraryProjection` snapshot.
pub(crate) struct LibraryReader {
    storage: StorageRoot,
    projection: LibraryProjection,
    handles: HashMap<String, LibraryHit>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct LibrarySnapshot {
    pub(crate) state: &'static str,
    pub(crate) rows: Vec<LibrarySnapshotRow>,
    pub(crate) message: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct LibrarySnapshotRow {
    pub(crate) meeting_id: String,
    pub(crate) label: String,
    pub(crate) created_at_epoch_seconds: u64,
    pub(crate) transcript_available: bool,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct LibrarySearchResponse {
    pub(crate) state: &'static str,
    pub(crate) results: Vec<LibrarySearchResult>,
    pub(crate) message: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct LibrarySearchResult {
    pub(crate) handle: String,
    pub(crate) kind: &'static str,
    pub(crate) meeting_id: String,
    pub(crate) text: Option<String>,
    pub(crate) source_turn_index: Option<u32>,
    pub(crate) claim_ordinal: Option<u64>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct LibraryNoteResponse {
    pub(crate) state: &'static str,
    pub(crate) meeting_id: String,
    pub(crate) claims: Vec<LibraryClaim>,
    pub(crate) message: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct LibraryClaim {
    pub(crate) handle: String,
    pub(crate) ordinal: u64,
    pub(crate) claim_type: &'static str,
    pub(crate) claim: String,
    pub(crate) evidence_state: &'static str,
    pub(crate) locator_count: usize,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct LibraryEvidenceResponse {
    pub(crate) state: &'static str,
    pub(crate) meeting_id: Option<String>,
    pub(crate) source_turn_index: Option<u32>,
    pub(crate) text: Option<String>,
    pub(crate) message: String,
}

impl LibraryReader {
    /// Takes an already-built projection. It never creates, rebuilds, or mutates
    /// storage; `LibraryProjection` performs its own fresh read on every open.
    pub(crate) fn new(storage: StorageRoot, projection: LibraryProjection) -> Self {
        Self {
            storage,
            projection,
            handles: HashMap::new(),
        }
    }

    pub(crate) fn snapshot(&self) -> LibrarySnapshot {
        if self.projection.rows().is_empty() {
            return LibrarySnapshot {
                state: "empty",
                rows: Vec::new(),
                message: "No retained meetings are available.".into(),
            };
        }
        LibrarySnapshot {
            state: "populated",
            rows: self
                .projection
                .rows()
                .iter()
                .map(|row| LibrarySnapshotRow {
                    meeting_id: row.meeting_id.clone(),
                    label: row.title().unwrap_or("Untitled meeting").to_owned(),
                    created_at_epoch_seconds: row.created_at_epoch_seconds,
                    transcript_available: row.transcript_sha256.is_some(),
                })
                .collect(),
            message: "Retained meetings are available.".into(),
        }
    }

    /// Confines a transcript-open request to a row that this exact read-only
    /// projection accepted. The caller still reopens and verifies the artifact.
    pub(crate) fn has_transcript(&self, meeting_id: &str) -> bool {
        self.projection.rows().iter().any(|row| {
            row.meeting_id == meeting_id && row.transcript_sha256.is_some()
        })
    }

    pub(crate) fn search(&mut self, query: &str) -> LibrarySearchResponse {
        // A handle is valid only for the response that returned it. Keeping old
        // handles would retain an unbounded amount of private snapshot state.
        self.handles.clear();
        match self.projection.search(query) {
            Ok(hits) if hits.is_empty() => LibrarySearchResponse {
                state: "no-results",
                results: Vec::new(),
                message: "No retained text matched that search.".into(),
            },
            Ok(hits) => {
                let mut results = Vec::new();
                for hit in hits {
                    let handle = self.retain_handle(hit.clone());
                    match self.projection.open(&self.storage, &hit) {
                        Ok(OpenedLibraryHit::Claim {
                            meeting_id,
                            claim,
                            claim_ordinal,
                            ..
                        }) => results.push(LibrarySearchResult {
                            handle,
                            kind: "claim",
                            meeting_id,
                            text: Some(claim),
                            source_turn_index: None,
                            claim_ordinal: Some(claim_ordinal),
                        }),
                        Ok(OpenedLibraryHit::Transcript {
                            meeting_id,
                            text,
                            source_turn_index,
                            ..
                        }) => results.push(LibrarySearchResult {
                            handle,
                            kind: "transcript",
                            meeting_id,
                            text: Some(text),
                            source_turn_index: Some(source_turn_index),
                            claim_ordinal: None,
                        }),
                        Ok(OpenedLibraryHit::Withheld {
                            meeting_id,
                            source_turn_index,
                        }) => results.push(LibrarySearchResult {
                            handle,
                            kind: "withheld",
                            meeting_id,
                            text: None,
                            source_turn_index: Some(source_turn_index),
                            claim_ordinal: None,
                        }),
                        Ok(OpenedLibraryHit::Meeting {
                            meeting_id,
                            title,
                            folder,
                        }) => results.push(LibrarySearchResult {
                            handle,
                            kind: "meeting",
                            meeting_id,
                            text: title.or(folder),
                            source_turn_index: None,
                            claim_ordinal: None,
                        }),
                        Err(_) => return Self::stale_search(),
                    }
                }
                LibrarySearchResponse {
                    state: "results",
                    results,
                    message: "Exact results from the current library snapshot.".into(),
                }
            }
            Err(_) => Self::stale_search(),
        }
    }

    pub(crate) fn open_note(&mut self, meeting_id: &str) -> LibraryNoteResponse {
        // Opening a note establishes the next evidence-response boundary.
        self.handles.clear();
        let Some(row) = self
            .projection
            .rows()
            .iter()
            .find(|row| row.meeting_id == meeting_id)
        else {
            return Self::stale_note(meeting_id);
        };
        if row.lifecycle() == MeetingLifecycle::SummaryFailed {
            return LibraryNoteResponse {
                state: "summary-failed",
                meeting_id: meeting_id.into(),
                claims: Vec::new(),
                message: "A note was not produced. Retained transcript text remains available."
                    .into(),
            };
        }
        let handles = match self.projection.note_claims(meeting_id) {
            Ok(handles) => handles,
            Err(_) => return Self::stale_note(meeting_id),
        };
        let mut claims = Vec::new();
        for hit in handles {
            let handle = self.retain_handle(hit.clone());
            match self.projection.open(&self.storage, &hit) {
                Ok(OpenedLibraryHit::Claim {
                    claim_ordinal,
                    claim_type,
                    evidence_state,
                    claim,
                    locators,
                    ..
                }) => claims.push(LibraryClaim {
                    handle,
                    ordinal: claim_ordinal,
                    claim_type: claim_type_name(claim_type),
                    claim,
                    evidence_state: evidence_state_name(evidence_state),
                    locator_count: locators.len(),
                }),
                Ok(_) | Err(_) => return Self::stale_note(meeting_id),
            }
        }
        LibraryNoteResponse {
            state: "note",
            meeting_id: meeting_id.into(),
            claims,
            message: "Claim words can be opened against their exact transcript locators.".into(),
        }
    }

    pub(crate) fn open_evidence(
        &self,
        handle: &str,
        locator_ordinal: usize,
    ) -> LibraryEvidenceResponse {
        let Some(hit) = self.handles.get(handle) else {
            return Self::stale_evidence();
        };
        match self
            .projection
            .open_claim_evidence(&self.storage, hit, locator_ordinal)
        {
            Ok(evidence) => LibraryEvidenceResponse {
                state: "evidence",
                meeting_id: Some(evidence.meeting_id),
                source_turn_index: Some(evidence.source_turn_index),
                text: Some(evidence.text),
                message: "Exact text from the retained transcript locator.".into(),
            },
            Err(_) => Self::stale_evidence(),
        }
    }

    pub(crate) fn unavailable_snapshot() -> LibrarySnapshot {
        LibrarySnapshot {
            state: "empty",
            rows: Vec::new(),
            message: UNAVAILABLE_MESSAGE.into(),
        }
    }

    pub(crate) fn unavailable_search() -> LibrarySearchResponse {
        LibrarySearchResponse {
            state: "empty",
            results: Vec::new(),
            message: UNAVAILABLE_MESSAGE.into(),
        }
    }

    pub(crate) fn unavailable_note(meeting_id: &str) -> LibraryNoteResponse {
        LibraryNoteResponse {
            state: "empty",
            meeting_id: meeting_id.into(),
            claims: Vec::new(),
            message: UNAVAILABLE_MESSAGE.into(),
        }
    }

    pub(crate) fn unavailable_evidence() -> LibraryEvidenceResponse {
        LibraryEvidenceResponse {
            state: "empty",
            meeting_id: None,
            source_turn_index: None,
            text: None,
            message: UNAVAILABLE_MESSAGE.into(),
        }
    }

    fn retain_handle(&mut self, hit: LibraryHit) -> String {
        let handle = Uuid::new_v4().to_string();
        self.handles.insert(handle.clone(), hit);
        handle
    }

    #[cfg(test)]
    pub(crate) fn retained_handle_count(&self) -> usize {
        self.handles.len()
    }

    fn stale_search() -> LibrarySearchResponse {
        LibrarySearchResponse {
            state: "stale",
            results: Vec::new(),
            message: STALE_MESSAGE.into(),
        }
    }

    fn stale_note(meeting_id: &str) -> LibraryNoteResponse {
        LibraryNoteResponse {
            state: "stale",
            meeting_id: meeting_id.into(),
            claims: Vec::new(),
            message: STALE_MESSAGE.into(),
        }
    }

    fn stale_evidence() -> LibraryEvidenceResponse {
        LibraryEvidenceResponse {
            state: "stale",
            meeting_id: None,
            source_turn_index: None,
            text: None,
            message: STALE_MESSAGE.into(),
        }
    }
}

fn claim_type_name(value: ClaimType) -> &'static str {
    match value {
        ClaimType::Decision => "decision",
        ClaimType::Action => "action",
        ClaimType::Proposal => "proposal",
        ClaimType::Question => "question",
    }
}

fn evidence_state_name(value: ClaimEvidenceState) -> &'static str {
    match value {
        ClaimEvidenceState::Located => "located",
    }
}

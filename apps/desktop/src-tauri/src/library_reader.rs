//! Private, read-only DTO adapter for an already-built meeting-library projection.
//!
//! This is deliberately not a Tauri command, state container, or storage builder.
//! Its only authority is to retain opaque projection handles long enough to reopen
//! the exact current claim or locator through `LibraryProjection`.

use std::collections::HashMap;

use local_meeting_notes_session_core::library_read::{
    ClaimEvidenceState, LibraryHit, LibraryProjection, LibraryReadError, OpenedLibraryHit,
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
    pub(crate) unavailable_count: usize,
    pub(crate) message: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct LibrarySnapshotRow {
    pub(crate) handle: String,
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
    pub(crate) unavailable_count: usize,
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

/// A verified search handle can only reopen its current projection target. It
/// deliberately returns a turn identity, never a filename or a general path.
#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct LibrarySearchOpenResponse {
    pub(crate) state: &'static str,
    pub(crate) transcript_handle: Option<String>,
    pub(crate) meeting_id: Option<String>,
    pub(crate) source_turn_index: Option<u32>,
    pub(crate) message: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct LibraryNoteResponse {
    pub(crate) state: &'static str,
    pub(crate) transcript_handle: Option<String>,
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
    pub(crate) transcript_handle: Option<String>,
    pub(crate) meeting_id: Option<String>,
    pub(crate) source_turn_index: Option<u32>,
    pub(crate) start: Option<u64>,
    pub(crate) end: Option<u64>,
    pub(crate) text: Option<String>,
    pub(crate) message: String,
}

#[derive(Debug)]
pub(crate) struct LibraryTranscriptAccess {
    pub(crate) state: &'static str,
    pub(crate) meeting_id: Option<String>,
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

    pub(crate) fn snapshot(&mut self) -> LibrarySnapshot {
        self.handles.clear();
        let unavailable_count = self.projection.quarantined_meetings();
        if self.projection.rows().is_empty() {
            return LibrarySnapshot {
                state: if unavailable_count == 0 {
                    "empty"
                } else {
                    "incomplete"
                },
                rows: Vec::new(),
                unavailable_count,
                message: if unavailable_count == 0 {
                    "No retained meetings are available.".into()
                } else {
                    format!("{unavailable_count} retained meeting(s) could not be read.")
                },
            };
        }
        let source_rows: Vec<_> = self
            .projection
            .rows()
            .iter()
            .map(|row| {
                (
                    row.meeting_id.clone(),
                    row.title().unwrap_or("Untitled meeting").to_owned(),
                    row.created_at_epoch_seconds,
                    row.transcript_sha256.is_some(),
                )
            })
            .collect();
        let mut rows = Vec::new();
        for (meeting_id, label, created_at_epoch_seconds, transcript_available) in source_rows {
            let Ok(hit) = self.projection.meeting_handle(&meeting_id) else {
                return Self::unavailable_snapshot();
            };
            rows.push(LibrarySnapshotRow {
                handle: self.retain_handle(hit),
                meeting_id,
                label,
                created_at_epoch_seconds,
                transcript_available,
            });
        }
        LibrarySnapshot {
            state: if unavailable_count == 0 {
                "populated"
            } else {
                "populated-incomplete"
            },
            rows,
            unavailable_count,
            message: if unavailable_count == 0 {
                "Retained meetings are available.".into()
            } else {
                format!("Retained meetings are available. {unavailable_count} could not be read.")
            },
        }
    }

    pub(crate) fn search(&mut self, query: &str) -> LibrarySearchResponse {
        // A handle is valid only for the response that returned it. Keeping old
        // handles would retain an unbounded amount of private snapshot state.
        self.handles.clear();
        let unavailable_count = self.projection.quarantined_meetings();
        match self.projection.search(query) {
            Ok(hits) if hits.is_empty() => LibrarySearchResponse {
                state: if unavailable_count == 0 {
                    "no-results"
                } else {
                    "incomplete"
                },
                results: Vec::new(),
                unavailable_count,
                message: if unavailable_count == 0 {
                    "No retained text matched that search.".into()
                } else {
                    format!(
                        "No match was found among readable meetings. {unavailable_count} could not be searched."
                    )
                },
            },
            Ok(hits) => {
                if self.projection.validate_snapshot(&self.storage).is_err() {
                    return Self::stale_search();
                }
                let mut results = Vec::new();
                for hit in hits {
                    match self.projection.open_snapshot(&hit) {
                        Ok(OpenedLibraryHit::Claim {
                            meeting_id,
                            claim,
                            claim_ordinal,
                            ..
                        }) => results.push(LibrarySearchResult {
                            handle: self.retain_handle(hit),
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
                            handle: self.retain_handle(hit),
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
                            handle: self.retain_handle(hit),
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
                            handle: self.retain_handle(hit),
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
                    state: if unavailable_count == 0 {
                        "results"
                    } else {
                        "results-incomplete"
                    },
                    results,
                    unavailable_count,
                    message: if unavailable_count == 0 {
                        "Exact results from the current library snapshot.".into()
                    } else {
                        format!(
                            "Exact results from readable meetings. {unavailable_count} could not be searched."
                        )
                    },
                }
            }
            Err(LibraryReadError::InvalidRequest) => Self::invalid_search(),
            Err(LibraryReadError::CapacityExceeded) => Self::bounded_search(),
            Err(_) => Self::stale_search(),
        }
    }

    /// Reopens a result through the projection's normal stale-artifact checks.
    /// Search terms never become filesystem or transcript-enumeration authority.
    pub(crate) fn open_search_result(&mut self, handle: &str) -> LibrarySearchOpenResponse {
        let Some(hit) = self.handles.get(handle).cloned() else {
            self.handles.clear();
            return Self::stale_search_open();
        };
        self.handles.clear();
        match self.projection.open(&self.storage, &hit) {
            Ok(OpenedLibraryHit::Transcript {
                meeting_id,
                source_turn_index,
                ..
            }) => self.retain_search_open(
                hit,
                "transcript",
                Some(meeting_id),
                Some(source_turn_index),
                "Opening the exact retained transcript turn that matched.",
            ),
            Ok(OpenedLibraryHit::Meeting { meeting_id, .. }) => self.retain_search_open(
                hit,
                "meeting",
                Some(meeting_id),
                None,
                "Opening this retained meeting's canonical transcript.",
            ),
            Ok(OpenedLibraryHit::Withheld {
                meeting_id,
                source_turn_index,
            }) => self.retain_search_open(
                hit,
                "withheld",
                Some(meeting_id),
                Some(source_turn_index),
                "A voice check withheld this matching turn. It is not shown as transcript text.",
            ),
            // Preview does not expose note reading yet, so a retained claim is
            // not a transcript/title search destination.
            Ok(OpenedLibraryHit::Claim { .. }) | Err(_) => Self::stale_search_open(),
        }
    }

    pub(crate) fn open_note(&mut self, handle: &str) -> LibraryNoteResponse {
        // Opening a note establishes the next evidence-response boundary.
        let Some(hit) = self.handles.get(handle).cloned() else {
            self.handles.clear();
            return Self::stale_note("");
        };
        self.handles.clear();
        let meeting_id = match self.projection.open(&self.storage, &hit) {
            Ok(OpenedLibraryHit::Meeting { meeting_id, .. }) => meeting_id,
            Ok(_) | Err(_) => return Self::stale_note(""),
        };
        let Some(lifecycle) = self
            .projection
            .rows()
            .iter()
            .find(|row| row.meeting_id == meeting_id)
            .map(|row| row.lifecycle())
        else {
            return Self::stale_note(&meeting_id);
        };
        match lifecycle {
            MeetingLifecycle::SummaryFailed => {
                return LibraryNoteResponse {
                    state: "summary-failed",
                    transcript_handle: self.retain_transcript_handle(&meeting_id),
                    meeting_id: meeting_id.into(),
                    claims: Vec::new(),
                    message: "A note was not produced. Retained transcript text remains available."
                        .into(),
                };
            }
            MeetingLifecycle::Ready => {}
            _ => {
                return LibraryNoteResponse {
                    state: "transcript-only",
                    transcript_handle: self.retain_transcript_handle(&meeting_id),
                    meeting_id: meeting_id.into(),
                    claims: Vec::new(),
                    message:
                        "No admitted note is available. Retained transcript text remains available."
                            .into(),
                };
            }
        }
        let handles = match self.projection.note_claims(&meeting_id) {
            Ok(handles) => handles,
            Err(_) => return Self::stale_note(&meeting_id),
        };
        let mut claims = Vec::new();
        for hit in handles {
            let handle = self.retain_handle(hit.clone());
            match self.projection.open_snapshot(&hit) {
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
                Ok(_) | Err(_) => return Self::stale_note(&meeting_id),
            }
        }
        LibraryNoteResponse {
            state: "note",
            transcript_handle: self.retain_transcript_handle(&meeting_id),
            meeting_id: meeting_id.into(),
            claims,
            message: "Claim words can be opened against their exact transcript locators.".into(),
        }
    }

    pub(crate) fn open_evidence(
        &mut self,
        handle: &str,
        locator_ordinal: usize,
    ) -> LibraryEvidenceResponse {
        let Some(hit) = self.handles.get(handle).cloned() else {
            self.handles.clear();
            return Self::stale_evidence();
        };
        self.handles.clear();
        match self
            .projection
            .open_claim_evidence(&self.storage, &hit, locator_ordinal)
        {
            Ok(evidence) => {
                let transcript_handle = self.retain_transcript_handle(&evidence.meeting_id);
                LibraryEvidenceResponse {
                    state: "evidence",
                    transcript_handle,
                    meeting_id: Some(evidence.meeting_id),
                    source_turn_index: Some(evidence.source_turn_index),
                    start: Some(evidence.start),
                    end: Some(evidence.end),
                    text: Some(evidence.text),
                    message: "Exact text from the retained transcript locator.".into(),
                }
            }
            Err(_) => Self::stale_evidence(),
        }
    }

    pub(crate) fn open_transcript(&mut self, handle: &str) -> LibraryTranscriptAccess {
        let Some(hit) = self.handles.get(handle).cloned() else {
            self.handles.clear();
            return Self::stale_transcript();
        };
        self.handles.clear();
        let response = match self.projection.open(&self.storage, &hit) {
            Ok(OpenedLibraryHit::Transcript { meeting_id, .. })
            | Ok(OpenedLibraryHit::Meeting { meeting_id, .. }) => LibraryTranscriptAccess {
                state: "transcript",
                meeting_id: Some(meeting_id),
                message: "Opening the retained canonical transcript.".into(),
            },
            Ok(OpenedLibraryHit::Withheld { .. }) => LibraryTranscriptAccess {
                state: "withheld",
                meeting_id: None,
                message: "A voice check withheld that matching turn from transcript text.".into(),
            },
            Ok(OpenedLibraryHit::Claim { .. }) | Err(_) => Self::stale_transcript(),
        };
        response
    }

    pub(crate) fn unavailable_snapshot() -> LibrarySnapshot {
        LibrarySnapshot {
            state: "unavailable",
            rows: Vec::new(),
            unavailable_count: 0,
            message: UNAVAILABLE_MESSAGE.into(),
        }
    }

    pub(crate) fn unavailable_search() -> LibrarySearchResponse {
        LibrarySearchResponse {
            state: "unavailable",
            results: Vec::new(),
            unavailable_count: 0,
            message: UNAVAILABLE_MESSAGE.into(),
        }
    }

    pub(crate) fn unavailable_note(meeting_id: &str) -> LibraryNoteResponse {
        LibraryNoteResponse {
            state: "unavailable",
            transcript_handle: None,
            meeting_id: meeting_id.into(),
            claims: Vec::new(),
            message: UNAVAILABLE_MESSAGE.into(),
        }
    }

    pub(crate) fn unavailable_evidence() -> LibraryEvidenceResponse {
        LibraryEvidenceResponse {
            state: "unavailable",
            transcript_handle: None,
            meeting_id: None,
            source_turn_index: None,
            start: None,
            end: None,
            text: None,
            message: UNAVAILABLE_MESSAGE.into(),
        }
    }

    fn retain_handle(&mut self, hit: LibraryHit) -> String {
        let handle = Uuid::new_v4().to_string();
        self.handles.insert(handle.clone(), hit);
        handle
    }

    fn retain_transcript_handle(&mut self, meeting_id: &str) -> Option<String> {
        self.projection
            .meeting_handle(meeting_id)
            .ok()
            .map(|hit| self.retain_handle(hit))
    }

    fn retain_search_open(
        &mut self,
        hit: LibraryHit,
        state: &'static str,
        meeting_id: Option<String>,
        source_turn_index: Option<u32>,
        message: &'static str,
    ) -> LibrarySearchOpenResponse {
        self.handles.clear();
        LibrarySearchOpenResponse {
            state,
            transcript_handle: Some(self.retain_handle(hit)),
            meeting_id,
            source_turn_index,
            message: message.into(),
        }
    }

    #[cfg(test)]
    pub(crate) fn retained_handle_count(&self) -> usize {
        self.handles.len()
    }

    fn stale_search() -> LibrarySearchResponse {
        LibrarySearchResponse {
            state: "stale",
            results: Vec::new(),
            unavailable_count: 0,
            message: STALE_MESSAGE.into(),
        }
    }

    fn stale_search_open() -> LibrarySearchOpenResponse {
        LibrarySearchOpenResponse {
            state: "stale",
            transcript_handle: None,
            meeting_id: None,
            source_turn_index: None,
            message: STALE_MESSAGE.into(),
        }
    }

    fn stale_note(meeting_id: &str) -> LibraryNoteResponse {
        LibraryNoteResponse {
            state: "stale",
            transcript_handle: None,
            meeting_id: meeting_id.into(),
            claims: Vec::new(),
            message: STALE_MESSAGE.into(),
        }
    }

    fn stale_evidence() -> LibraryEvidenceResponse {
        LibraryEvidenceResponse {
            state: "stale",
            transcript_handle: None,
            meeting_id: None,
            source_turn_index: None,
            start: None,
            end: None,
            text: None,
            message: STALE_MESSAGE.into(),
        }
    }

    fn stale_transcript() -> LibraryTranscriptAccess {
        LibraryTranscriptAccess {
            state: "stale",
            meeting_id: None,
            message: STALE_MESSAGE.into(),
        }
    }

    fn invalid_search() -> LibrarySearchResponse {
        LibrarySearchResponse {
            state: "invalid",
            results: Vec::new(),
            unavailable_count: 0,
            message: "Enter at least two characters to search retained text.".into(),
        }
    }

    fn bounded_search() -> LibrarySearchResponse {
        LibrarySearchResponse {
            state: "bounded",
            results: Vec::new(),
            unavailable_count: 0,
            message: "That search has too many matches. Use a more specific exact phrase.".into(),
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

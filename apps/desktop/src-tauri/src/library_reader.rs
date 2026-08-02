//! Private, read-only DTO adapter for an already-built meeting-library projection.
//!
//! This is deliberately not a Tauri command, state container, or storage builder.
//! Its only authority is to retain opaque projection handles long enough to reopen
//! the exact current claim or locator through `LibraryProjection`.

use std::collections::HashMap;
use std::fs;

use local_meeting_notes_session_core::library_read::{
    ClaimEvidenceState, LibraryHit, LibraryProjection, LibraryReadError, OpenedLibraryHit,
};
use local_meeting_notes_session_core::meeting::{
    ArtifactRef, AudioRetentionRule, AudioState, MeetingLifecycle, load_meeting, resolve_artifact,
    verify_record_artifacts, verify_record_static_artifacts,
};
use local_meeting_notes_session_core::note_projection::ClaimType;
use local_meeting_notes_session_core::retention::meeting_dir;
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
    audio_deletion_handles: HashMap<String, LibraryHit>,
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
    pub(crate) start: Option<u64>,
    pub(crate) end: Option<u64>,
    pub(crate) claim_ordinal: Option<u64>,
    pub(crate) transcript_available: bool,
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
    pub(crate) start: Option<u64>,
    pub(crate) end: Option<u64>,
    pub(crate) message: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct LibraryNoteResponse {
    pub(crate) state: &'static str,
    pub(crate) transcript_handle: Option<String>,
    pub(crate) audio_deletion_handle: Option<String>,
    pub(crate) meeting_id: String,
    pub(crate) claims: Vec<LibraryClaim>,
    pub(crate) audio_retention: LibraryAudioRetention,
    pub(crate) message: String,
}

/// Content-free, freshly checked retention facts for one meeting detail view.
/// The browser receives no artifact path, digest, audio bytes, or deletion
/// authority. This remains a read-only Preview projection.
#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct LibraryAudioRetention {
    pub(crate) state: &'static str,
    pub(crate) policy: &'static str,
    pub(crate) deadline_epoch_seconds: Option<u64>,
    pub(crate) retained_bytes: Option<u64>,
    pub(crate) message: String,
}

#[derive(Debug, PartialEq, Eq)]
pub(crate) struct LibraryAudioDeletionAccess {
    pub(crate) state: &'static str,
    pub(crate) meeting_id: Option<String>,
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
    pub(crate) transcript_artifact: Option<ArtifactRef>,
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
            audio_deletion_handles: HashMap::new(),
        }
    }

    pub(crate) fn snapshot(&mut self) -> LibrarySnapshot {
        self.clear_handles();
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
        self.clear_handles();
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
                            start: None,
                            end: None,
                            claim_ordinal: Some(claim_ordinal),
                            transcript_available: true,
                        }),
                        Ok(OpenedLibraryHit::Transcript {
                            meeting_id,
                            text,
                            source_turn_index,
                            original_scalar_start,
                            original_scalar_end,
                            ..
                        }) => results.push(LibrarySearchResult {
                            handle: self.retain_handle(hit),
                            kind: "transcript",
                            meeting_id,
                            text: Some(text),
                            source_turn_index: Some(source_turn_index),
                            start: Some(original_scalar_start),
                            end: Some(original_scalar_end),
                            claim_ordinal: None,
                            transcript_available: true,
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
                            start: None,
                            end: None,
                            claim_ordinal: None,
                            transcript_available: false,
                        }),
                        Ok(OpenedLibraryHit::Meeting {
                            meeting_id,
                            title,
                            folder,
                            ..
                        }) => {
                            let transcript_available = self.meeting_has_transcript(&meeting_id);
                            results.push(LibrarySearchResult {
                                handle: self.retain_handle(hit),
                                kind: "meeting",
                                meeting_id,
                                text: title.or(folder),
                                source_turn_index: None,
                                start: None,
                                end: None,
                                claim_ordinal: None,
                                transcript_available,
                            });
                        }
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
            self.clear_handles();
            return Self::stale_search_open();
        };
        self.clear_handles();
        match self.projection.open(&self.storage, &hit) {
            Ok(OpenedLibraryHit::Transcript {
                meeting_id,
                source_turn_index,
                original_scalar_start,
                original_scalar_end,
                ..
            }) => self.retain_search_open(
                hit,
                "transcript",
                Some(meeting_id),
                Some(source_turn_index),
                Some(original_scalar_start),
                Some(original_scalar_end),
                "Opening the exact retained transcript turn that matched.",
            ),
            Ok(OpenedLibraryHit::Meeting { meeting_id, .. }) => {
                if self.meeting_has_transcript(&meeting_id) {
                    self.retain_search_open(
                        hit,
                        "meeting",
                        Some(meeting_id),
                        None,
                        None,
                        None,
                        "Opening this retained meeting's canonical transcript.",
                    )
                } else {
                    LibrarySearchOpenResponse {
                        state: "metadata-only",
                        transcript_handle: None,
                        meeting_id: Some(meeting_id),
                        source_turn_index: None,
                        start: None,
                        end: None,
                        message: "No transcript was created for this retained meeting.".into(),
                    }
                }
            }
            Ok(OpenedLibraryHit::Withheld {
                meeting_id,
                source_turn_index,
            }) => self.retain_search_open(
                hit,
                "withheld",
                Some(meeting_id),
                Some(source_turn_index),
                None,
                None,
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
            self.clear_handles();
            return Self::stale_note("");
        };
        self.clear_handles();
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
        let audio_retention = self.audio_retention(&meeting_id);
        let audio_deletion_handle =
            self.retain_audio_deletion_handle(&meeting_id, audio_retention.state == "retained");
        match lifecycle {
            MeetingLifecycle::SummaryFailed => {
                return LibraryNoteResponse {
                    state: "summary-failed",
                    transcript_handle: self.retain_transcript_handle(&meeting_id),
                    audio_deletion_handle,
                    meeting_id: meeting_id.into(),
                    claims: Vec::new(),
                    audio_retention,
                    message: "A note was not produced. Retained transcript text remains available."
                        .into(),
                };
            }
            MeetingLifecycle::Ready => {}
            _ => {
                let transcript_handle = self.retain_transcript_handle(&meeting_id);
                return LibraryNoteResponse {
                    state: "transcript-only",
                    transcript_handle: transcript_handle.clone(),
                    audio_deletion_handle,
                    meeting_id: meeting_id.into(),
                    claims: Vec::new(),
                    audio_retention,
                    message: if transcript_handle.is_some() {
                        "No admitted note is available. Retained transcript text remains available."
                            .into()
                    } else {
                        "No transcript was created for this retained meeting.".into()
                    },
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
            audio_deletion_handle,
            meeting_id: meeting_id.into(),
            claims,
            audio_retention,
            message: "Claim words can be opened against their exact transcript locators.".into(),
        }
    }

    pub(crate) fn open_evidence(
        &mut self,
        handle: &str,
        locator_ordinal: usize,
    ) -> LibraryEvidenceResponse {
        let Some(hit) = self.handles.get(handle).cloned() else {
            self.clear_handles();
            return Self::stale_evidence();
        };
        self.clear_handles();
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
            self.clear_handles();
            return Self::stale_transcript();
        };
        self.clear_handles();
        let response = match self.projection.open(&self.storage, &hit) {
            Ok(OpenedLibraryHit::Transcript {
                meeting_id,
                transcript_artifact,
                ..
            }) => LibraryTranscriptAccess {
                state: "transcript",
                meeting_id: Some(meeting_id),
                transcript_artifact: Some(transcript_artifact),
                message: "Opening the retained canonical transcript.".into(),
            },
            Ok(OpenedLibraryHit::Meeting {
                meeting_id,
                transcript_artifact: Some(transcript_artifact),
                ..
            }) => LibraryTranscriptAccess {
                state: "transcript",
                meeting_id: Some(meeting_id),
                transcript_artifact: Some(transcript_artifact),
                message: "Opening the retained canonical transcript.".into(),
            },
            Ok(OpenedLibraryHit::Meeting { .. }) => Self::stale_transcript(),
            Ok(OpenedLibraryHit::Withheld { .. }) => LibraryTranscriptAccess {
                state: "withheld",
                meeting_id: None,
                transcript_artifact: None,
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
            audio_deletion_handle: None,
            meeting_id: meeting_id.into(),
            claims: Vec::new(),
            audio_retention: Self::unavailable_audio_retention(),
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

    fn retain_audio_deletion_handle(&mut self, meeting_id: &str, retained: bool) -> Option<String> {
        if !retained {
            return None;
        }
        let hit = self.projection.meeting_handle(meeting_id).ok()?;
        let handle = Uuid::new_v4().to_string();
        self.audio_deletion_handles.insert(handle.clone(), hit);
        Some(handle)
    }

    pub(crate) fn authorize_audio_deletion(&mut self, handle: &str) -> LibraryAudioDeletionAccess {
        let hit = self.audio_deletion_handles.get(handle).cloned();
        self.clear_handles();
        let Some(hit) = hit else {
            return Self::stale_audio_deletion();
        };
        let meeting_id = match self.projection.open(&self.storage, &hit) {
            Ok(OpenedLibraryHit::Meeting { meeting_id, .. }) => meeting_id,
            Ok(_) | Err(_) => return Self::stale_audio_deletion(),
        };
        match Self::read_audio_retention(&self.storage, &meeting_id).state {
            "retained" => LibraryAudioDeletionAccess {
                state: "authorized",
                meeting_id: Some(meeting_id),
                message: "The reviewed meeting recording may be deleted.".into(),
            },
            "released" => LibraryAudioDeletionAccess {
                state: "already-released",
                meeting_id: Some(meeting_id),
                message: "This meeting recording was already deleted.".into(),
            },
            "deleting" => LibraryAudioDeletionAccess {
                state: "deleting",
                meeting_id: Some(meeting_id),
                message: "This meeting recording is already being deleted.".into(),
            },
            "not-recorded" => LibraryAudioDeletionAccess {
                state: "not-recorded",
                meeting_id: Some(meeting_id),
                message: "This meeting has no retained recording to delete.".into(),
            },
            _ => LibraryAudioDeletionAccess {
                state: "unavailable",
                meeting_id: None,
                message: "Recording deletion is unavailable. Reopen Library and try again.".into(),
            },
        }
    }

    fn clear_handles(&mut self) {
        self.handles.clear();
        self.audio_deletion_handles.clear();
    }

    fn retain_transcript_handle(&mut self, meeting_id: &str) -> Option<String> {
        if !self.meeting_has_transcript(meeting_id) {
            return None;
        }
        self.projection
            .meeting_handle(meeting_id)
            .ok()
            .map(|hit| self.retain_handle(hit))
    }

    fn meeting_has_transcript(&self, meeting_id: &str) -> bool {
        self.projection
            .rows()
            .iter()
            .any(|row| row.meeting_id == meeting_id && row.transcript_sha256.is_some())
    }

    fn audio_retention(&self, meeting_id: &str) -> LibraryAudioRetention {
        Self::read_audio_retention(&self.storage, meeting_id)
    }

    pub(crate) fn read_audio_retention(
        storage: &StorageRoot,
        meeting_id: &str,
    ) -> LibraryAudioRetention {
        let Ok(directory) = meeting_dir(storage, meeting_id) else {
            return Self::unavailable_audio_retention();
        };
        let Ok(meeting) = load_meeting(&directory) else {
            return Self::unavailable_audio_retention();
        };
        let (policy, deadline_epoch_seconds) = match meeting.retention.rule {
            AudioRetentionRule::DeleteAfter { .. } => (
                "scheduled",
                meeting.retention.next_deletion_at_epoch_seconds,
            ),
            AudioRetentionRule::UntilManualDeletion => ("manual", None),
        };
        match meeting.retention.state {
            AudioState::Retained => {
                if verify_record_artifacts(&directory, &meeting).is_err() {
                    return Self::unavailable_audio_retention();
                }
                let bytes = [
                    meeting.artifacts.microphone_audio.as_ref(),
                    meeting.artifacts.system_audio.as_ref(),
                ]
                .into_iter()
                .flatten()
                .try_fold(0_u64, |total, artifact| {
                    let path =
                        resolve_artifact(&directory, &artifact.relative_path).map_err(|_| ())?;
                    let size = fs::metadata(path).map_err(|_| ())?.len();
                    total.checked_add(size).ok_or(())
                });
                let Ok(retained_bytes) = bytes else {
                    return Self::unavailable_audio_retention();
                };
                LibraryAudioRetention {
                    state: "retained",
                    policy,
                    deadline_epoch_seconds,
                    retained_bytes: Some(retained_bytes),
                    message: "Meeting audio is retained on this Mac.".into(),
                }
            }
            AudioState::Released => {
                if verify_record_artifacts(&directory, &meeting).is_err() {
                    return Self::unavailable_audio_retention();
                }
                LibraryAudioRetention {
                    state: "released",
                    policy,
                    deadline_epoch_seconds,
                    retained_bytes: None,
                    message:
                        "Meeting audio was deleted. The transcript, note, and evidence remain."
                            .into(),
                }
            }
            AudioState::Deleting => {
                if verify_record_static_artifacts(&directory, &meeting).is_err() {
                    return Self::unavailable_audio_retention();
                }
                LibraryAudioRetention {
                    state: "deleting",
                    policy,
                    deadline_epoch_seconds,
                    retained_bytes: None,
                    message: "Meeting audio deletion is already in progress.".into(),
                }
            }
            AudioState::NeverCreated => LibraryAudioRetention {
                state: "not-recorded",
                policy,
                deadline_epoch_seconds,
                retained_bytes: None,
                message: "This meeting has no retained audio.".into(),
            },
        }
    }

    fn unavailable_audio_retention() -> LibraryAudioRetention {
        LibraryAudioRetention {
            state: "unavailable",
            policy: "unknown",
            deadline_epoch_seconds: None,
            retained_bytes: None,
            message: "Audio retention details are unavailable. Reopen Library and try again."
                .into(),
        }
    }

    fn retain_search_open(
        &mut self,
        hit: LibraryHit,
        state: &'static str,
        meeting_id: Option<String>,
        source_turn_index: Option<u32>,
        start: Option<u64>,
        end: Option<u64>,
        message: &'static str,
    ) -> LibrarySearchOpenResponse {
        self.clear_handles();
        LibrarySearchOpenResponse {
            state,
            transcript_handle: Some(self.retain_handle(hit)),
            meeting_id,
            source_turn_index,
            start,
            end,
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
            start: None,
            end: None,
            message: STALE_MESSAGE.into(),
        }
    }

    fn stale_note(meeting_id: &str) -> LibraryNoteResponse {
        LibraryNoteResponse {
            state: "stale",
            transcript_handle: None,
            audio_deletion_handle: None,
            meeting_id: meeting_id.into(),
            claims: Vec::new(),
            audio_retention: Self::unavailable_audio_retention(),
            message: STALE_MESSAGE.into(),
        }
    }

    fn stale_audio_deletion() -> LibraryAudioDeletionAccess {
        LibraryAudioDeletionAccess {
            state: "stale",
            meeting_id: None,
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
            transcript_artifact: None,
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

#[cfg(test)]
mod tests {
    use std::fs;
    use std::os::unix::fs::symlink;

    use local_meeting_notes_session_core::meeting::{
        AudioRetention, MeetingArtifacts, MeetingRecord, MeetingSchema, artifact_ref,
        retention_policy_sha256, write_meeting,
    };
    use local_meeting_notes_session_core::storage::{
        StorageRoot, create_private_dir, durable_create_new,
    };
    use serde_json::json;
    use sha2::Digest;
    use tempfile::TempDir;

    use super::*;

    const MEETING_ID: &str = "11111111-1111-4111-8111-111111111111";

    struct Fixture {
        _temporary: TempDir,
        storage: StorageRoot,
        directory: std::path::PathBuf,
    }

    fn fixture(
        state: AudioState,
        rule: AudioRetentionRule,
        microphone: &[u8],
        system: &[u8],
    ) -> Fixture {
        let temporary = TempDir::new().unwrap();
        let protected = temporary.path().join("protected");
        create_private_dir(&protected).unwrap();
        let storage = StorageRoot::create(&temporary.path().join("app-data"), &protected).unwrap();
        let directory = storage.path().join("meetings").join(MEETING_ID);
        create_private_dir(&directory).unwrap();
        create_private_dir(&directory.join("capture")).unwrap();
        let policy_sha256 = retention_policy_sha256(&rule);
        let attempt = serde_json::to_vec_pretty(&json!({
            "schema": "capture-attempt/1",
            "meeting_id": MEETING_ID,
            "attempt_id": "22222222-2222-4222-8222-222222222222",
            "created_at_epoch_seconds": 1_728_000_000_u64,
            "application_build_sha256": "a".repeat(64),
            "participant_notice_version": "internal-transcript-alpha/1",
            "operator_attestation": {
                "participantsConsented": true,
                "headphones": true,
                "operatorAlone": true
            },
            "retention_policy_sha256": policy_sha256,
        }))
        .unwrap();
        durable_create_new(&directory.join("attempt.json"), &attempt).unwrap();
        let transcript_bytes = serde_json::to_vec_pretty(&json!({
            "schema": "capture-transcript/1",
            "source": "synthetic",
            "attribution": "channel",
            "bleed": null,
            "voiceprint": null,
            "capture_health": {},
            "turns": []
        }))
        .unwrap();
        let transcript_relative = format!(
            "transcript/{:x}.json",
            sha2::Sha256::digest(&transcript_bytes)
        );

        let lifecycle = if state == AudioState::NeverCreated {
            MeetingLifecycle::Incomplete
        } else {
            create_private_dir(&directory.join("deletion")).unwrap();
            create_private_dir(&directory.join("transcript")).unwrap();
            durable_create_new(&directory.join("ownership.json"), b"ownership").unwrap();
            durable_create_new(&directory.join("capture/session.json"), b"session").unwrap();
            durable_create_new(&directory.join("capture/mic.wav"), microphone).unwrap();
            durable_create_new(&directory.join("capture/system.wav"), system).unwrap();
            durable_create_new(&directory.join(&transcript_relative), &transcript_bytes).unwrap();
            MeetingLifecycle::TranscriptReady
        };
        let deletion_receipt = if state == AudioState::Released {
            fs::remove_file(directory.join("capture/mic.wav")).unwrap();
            fs::remove_file(directory.join("capture/system.wav")).unwrap();
            durable_create_new(&directory.join("deletion/audio-deletion.json"), b"released")
                .unwrap();
            Some(artifact_ref(&directory, "deletion/audio-deletion.json").unwrap())
        } else {
            None
        };
        let next_deletion_at_epoch_seconds = match rule {
            AudioRetentionRule::DeleteAfter { .. } if state != AudioState::NeverCreated => {
                Some(1_728_000_060)
            }
            AudioRetentionRule::DeleteAfter { .. } | AudioRetentionRule::UntilManualDeletion => {
                None
            }
        };
        let record = MeetingRecord {
            schema: MeetingSchema::V2,
            meeting_id: MEETING_ID.into(),
            lifecycle,
            retention: AudioRetention {
                policy_sha256,
                rule,
                next_deletion_at_epoch_seconds,
                state,
                deletion_receipt,
            },
            artifacts: MeetingArtifacts {
                attempt: artifact_ref(&directory, "attempt.json").unwrap(),
                ownership: (state != AudioState::NeverCreated)
                    .then(|| artifact_ref(&directory, "ownership.json").unwrap()),
                capture_session: (state != AudioState::NeverCreated)
                    .then(|| artifact_ref(&directory, "capture/session.json").unwrap()),
                microphone_audio: (state != AudioState::NeverCreated).then(|| ArtifactRef {
                    relative_path: "capture/mic.wav".into(),
                    sha256: format!("{:x}", sha2::Sha256::digest(microphone)),
                }),
                system_audio: (state != AudioState::NeverCreated).then(|| ArtifactRef {
                    relative_path: "capture/system.wav".into(),
                    sha256: format!("{:x}", sha2::Sha256::digest(system)),
                }),
                current_transcript: (state != AudioState::NeverCreated)
                    .then(|| artifact_ref(&directory, &transcript_relative).unwrap()),
                current_note: None,
            },
            pending_storage_operation: (state == AudioState::Deleting).then_some(
                local_meeting_notes_session_core::meeting::PendingStorageOperation::AudioDeletionV1,
            ),
        };
        write_meeting(&directory, &record).unwrap();
        Fixture {
            _temporary: temporary,
            storage,
            directory,
        }
    }

    #[test]
    fn retention_projection_reports_exact_two_leg_bytes_and_scheduled_deadline() {
        let fixture = fixture(
            AudioState::Retained,
            AudioRetentionRule::DeleteAfter { seconds: 60 },
            &[1; 19],
            &[2; 23],
        );

        let retention = LibraryReader::read_audio_retention(&fixture.storage, MEETING_ID);

        assert_eq!(retention.state, "retained");
        assert_eq!(retention.policy, "scheduled");
        assert_eq!(retention.deadline_epoch_seconds, Some(1_728_000_060));
        assert_eq!(retention.retained_bytes, Some(42));
        assert!(
            !serde_json::to_string(&retention)
                .unwrap()
                .contains("capture/")
        );
    }

    #[test]
    fn retained_meeting_gets_a_single_use_deletion_handle_not_generic_handle_authority() {
        let fixture = fixture(
            AudioState::Retained,
            AudioRetentionRule::UntilManualDeletion,
            &[1; 19],
            &[2; 23],
        );
        let projection = LibraryProjection::rebuild(&fixture.storage, Default::default()).unwrap();
        let mut reader = LibraryReader::new(fixture.storage.clone(), projection);
        let snapshot = reader.snapshot();
        let generic_handle = snapshot.rows[0].handle.clone();

        let refused = reader.authorize_audio_deletion(&generic_handle);
        assert_eq!(refused.state, "stale");
        assert_eq!(refused.meeting_id, None);

        let snapshot = reader.snapshot();
        let note = reader.open_note(&snapshot.rows[0].handle);
        let deletion_handle = note
            .audio_deletion_handle
            .expect("retained meeting deletion handle");
        let authorized = reader.authorize_audio_deletion(&deletion_handle);
        assert_eq!(authorized.state, "authorized");
        assert_eq!(authorized.meeting_id.as_deref(), Some(MEETING_ID));

        let reused = reader.authorize_audio_deletion(&deletion_handle);
        assert_eq!(reused.state, "stale");
        assert_eq!(reused.meeting_id, None);
    }

    #[test]
    fn released_meeting_has_no_audio_deletion_handle() {
        let fixture = fixture(
            AudioState::Released,
            AudioRetentionRule::UntilManualDeletion,
            &[1; 19],
            &[2; 23],
        );
        let projection = LibraryProjection::rebuild(&fixture.storage, Default::default()).unwrap();
        let mut reader = LibraryReader::new(fixture.storage, projection);
        let snapshot = reader.snapshot();
        let note = reader.open_note(&snapshot.rows[0].handle);

        assert_eq!(note.audio_retention.state, "released");
        assert_eq!(note.audio_deletion_handle, None);
    }

    #[test]
    fn manual_released_never_created_and_deleting_are_content_free_states() {
        let manual = fixture(
            AudioState::Retained,
            AudioRetentionRule::UntilManualDeletion,
            &[1; 44],
            &[2; 48],
        );
        let released = fixture(
            AudioState::Released,
            AudioRetentionRule::DeleteAfter { seconds: 60 },
            &[1; 44],
            &[2; 48],
        );
        let never_created = fixture(
            AudioState::NeverCreated,
            AudioRetentionRule::UntilManualDeletion,
            &[],
            &[],
        );
        let deleting = fixture(
            AudioState::Deleting,
            AudioRetentionRule::DeleteAfter { seconds: 60 },
            &[1; 44],
            &[2; 48],
        );

        let manual = LibraryReader::read_audio_retention(&manual.storage, MEETING_ID);
        let released = LibraryReader::read_audio_retention(&released.storage, MEETING_ID);
        let never_created = LibraryReader::read_audio_retention(&never_created.storage, MEETING_ID);
        let deleting = LibraryReader::read_audio_retention(&deleting.storage, MEETING_ID);

        assert_eq!(
            (manual.state, manual.policy, manual.deadline_epoch_seconds),
            ("retained", "manual", None)
        );
        assert_eq!(released.state, "released");
        assert_eq!(released.retained_bytes, None);
        assert_eq!(never_created.state, "not-recorded");
        assert_eq!(deleting.state, "deleting");
    }

    #[test]
    fn changed_missing_or_symlinked_audio_fails_closed() {
        for mutation in ["changed", "missing", "symlink"] {
            let fixture = fixture(
                AudioState::Retained,
                AudioRetentionRule::UntilManualDeletion,
                &[1; 44],
                &[2; 48],
            );
            let microphone = fixture.directory.join("capture/mic.wav");
            match mutation {
                "changed" => fs::write(&microphone, b"changed").unwrap(),
                "missing" => fs::remove_file(&microphone).unwrap(),
                "symlink" => {
                    fs::remove_file(&microphone).unwrap();
                    let target = fixture.directory.join("capture/not-audio");
                    durable_create_new(&target, b"not audio").unwrap();
                    symlink(target, microphone).unwrap();
                }
                _ => unreachable!(),
            }

            let retention = LibraryReader::read_audio_retention(&fixture.storage, MEETING_ID);
            assert_eq!(retention.state, "unavailable", "{mutation}");
            assert_eq!(retention.retained_bytes, None, "{mutation}");
        }
    }
}

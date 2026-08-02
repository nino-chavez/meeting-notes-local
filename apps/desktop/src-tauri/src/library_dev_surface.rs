//! Development-only, synthetic read surface for the library reader.
//!
//! This module is compiled only with `library-dev-surface`. It has no capture,
//! retention, export, correction, regeneration, or production-data commands.

use std::collections::HashMap;
use std::path::Path;
use std::sync::{Arc, Mutex};

use local_meeting_notes_session_core::library_read::{
    ClaimEvidenceState, LibraryHit, LibraryProjection, LibraryReadError, OpenedLibraryHit,
    ReadLimits,
};
use local_meeting_notes_session_core::meeting::{
    ArtifactRef, AudioRetention, AudioRetentionRule, AudioState, MeetingArtifacts,
    MeetingLifecycle, MeetingRecord, MeetingSchema, NoteRevisionRef, artifact_ref,
    retention_policy_sha256, write_meeting,
};
use local_meeting_notes_session_core::note_projection::{
    NoteProjector, ProjectRequest, ProjectTransportError,
};
use local_meeting_notes_session_core::storage::{
    StorageRoot, create_private_dir, durable_create_new,
};
use serde::Serialize;
use serde_json::json;
use sha2::{Digest, Sha256};
use tauri::{AppHandle, Manager, State};
use uuid::Uuid;

const FIXTURE_MEETING_ID: &str = "library-dev-sample";
const FIXTURE_MARKER: &str = "library-dev-fixture-v1.json";
const NOTICE_VERSION: &str = "internal-transcript-alpha/1";

struct DevLibrary {
    storage: StorageRoot,
    projection: LibraryProjection,
    handles: HashMap<String, LibraryHit>,
}

#[derive(Default)]
pub struct DevSurfaceState {
    library: Mutex<Option<DevLibrary>>,
    startup_error: Mutex<Option<String>>,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct DevSnapshot {
    state: &'static str,
    rows: Vec<DevRow>,
    message: String,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct DevRow {
    meeting_id: String,
    label: String,
    created_at_epoch_seconds: u64,
    transcript_available: bool,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct DevSearchResponse {
    state: &'static str,
    results: Vec<DevSearchResult>,
    message: String,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct DevSearchResult {
    handle: String,
    kind: &'static str,
    meeting_id: String,
    text: Option<String>,
    source_turn_index: Option<u32>,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct DevNoteResponse {
    state: &'static str,
    meeting_id: String,
    claims: Vec<DevClaim>,
    message: String,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct DevClaim {
    handle: String,
    ordinal: u64,
    claim_type: &'static str,
    claim: String,
    evidence_state: &'static str,
    locator_count: usize,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct DevEvidenceResponse {
    state: &'static str,
    meeting_id: Option<String>,
    source_turn_index: Option<u32>,
    text: Option<String>,
    message: String,
}

pub fn run() {
    tauri::Builder::default()
        .manage(DevSurfaceState::default())
        .invoke_handler(tauri::generate_handler![
            library_dev_snapshot,
            library_dev_search,
            library_dev_open_note,
            library_dev_open_evidence
        ])
        .setup(|app| Ok(initialize(app.handle())?))
        .run(tauri::generate_context!())
        .expect("Local Meeting Notes library development surface failed");
}

fn initialize(app: &AppHandle) -> tauri::Result<()> {
    let state = app.state::<DevSurfaceState>();
    match create_dev_library(app) {
        Ok(library) => {
            *state.library.lock().expect("development library lock") = Some(library);
            *state
                .startup_error
                .lock()
                .expect("development startup lock") = None;
        }
        Err(error) => {
            *state
                .startup_error
                .lock()
                .expect("development startup lock") = Some(error);
        }
    }
    Ok(())
}

#[tauri::command]
fn library_dev_snapshot(state: State<'_, DevSurfaceState>) -> DevSnapshot {
    let guard = state.library.lock().expect("development library lock");
    if let Some(library) = guard.as_ref() {
        let rows = library
            .projection
            .rows()
            .iter()
            .map(|row| DevRow {
                meeting_id: row.meeting_id.clone(),
                label: "Sanitized library sample".into(),
                created_at_epoch_seconds: row.created_at_epoch_seconds,
                transcript_available: row.transcript_sha256.is_some(),
            })
            .collect();
        return DevSnapshot {
            state: "populated",
            rows,
            message:
                "Synthetic, sanitized development data only. This does not open production data."
                    .into(),
        };
    }
    DevSnapshot {
        state: "empty",
        rows: Vec::new(),
        message: state
            .startup_error
            .lock()
            .expect("development startup lock")
            .clone()
            .unwrap_or_else(|| "No synthetic fixture is available.".into()),
    }
}

#[tauri::command]
fn library_dev_search(query: String, state: State<'_, DevSurfaceState>) -> DevSearchResponse {
    let mut guard = state.library.lock().expect("development library lock");
    let Some(library) = guard.as_mut() else {
        return unavailable_search(&state);
    };
    match library.projection.search(&query) {
        Ok(hits) if hits.is_empty() => DevSearchResponse {
            state: "no-results",
            results: Vec::new(),
            message: "No sanitized sample matched that search.".into(),
        },
        Ok(hits) => {
            let mut results = Vec::new();
            for hit in hits {
                let handle = retain_handle(library, hit.clone());
                match library.projection.open(&library.storage, &hit) {
                    Ok(OpenedLibraryHit::Claim {
                        meeting_id, claim, ..
                    }) => results.push(DevSearchResult {
                        handle,
                        kind: "claim",
                        meeting_id,
                        text: Some(claim),
                        source_turn_index: None,
                    }),
                    Ok(OpenedLibraryHit::Transcript {
                        meeting_id,
                        text,
                        source_turn_index,
                        ..
                    }) => results.push(DevSearchResult {
                        handle,
                        kind: "transcript",
                        meeting_id,
                        text: Some(text),
                        source_turn_index: Some(source_turn_index),
                    }),
                    Ok(OpenedLibraryHit::Withheld {
                        meeting_id,
                        source_turn_index,
                    }) => results.push(DevSearchResult {
                        handle,
                        kind: "withheld",
                        meeting_id,
                        text: None,
                        source_turn_index: Some(source_turn_index),
                    }),
                    Ok(OpenedLibraryHit::Meeting { meeting_id, .. }) => {
                        results.push(DevSearchResult {
                            handle,
                            kind: "meeting",
                            meeting_id,
                            text: Some("Sanitized library sample".into()),
                            source_turn_index: None,
                        })
                    }
                    Err(error) => return stale_search(error),
                }
            }
            DevSearchResponse {
                state: "results",
                results,
                message: "Search results are read-only projections of the sanitized fixture."
                    .into(),
            }
        }
        Err(error) => stale_search(error),
    }
}

#[tauri::command]
fn library_dev_open_note(meeting_id: String, state: State<'_, DevSurfaceState>) -> DevNoteResponse {
    let mut guard = state.library.lock().expect("development library lock");
    let Some(library) = guard.as_mut() else {
        return unavailable_note(&meeting_id, &state);
    };
    let handles = match library.projection.note_claims(&meeting_id) {
        Ok(handles) => handles,
        Err(error) => return stale_note(&meeting_id, error),
    };
    let mut claims = Vec::new();
    for hit in handles {
        let handle = retain_handle(library, hit.clone());
        match library.projection.open(&library.storage, &hit) {
            Ok(OpenedLibraryHit::Claim {
                claim_ordinal,
                claim_type,
                evidence_state,
                claim,
                locators,
                ..
            }) => claims.push(DevClaim {
                handle,
                ordinal: claim_ordinal,
                claim_type: claim_type_name(claim_type),
                claim,
                evidence_state: evidence_state_name(evidence_state),
                locator_count: locators.len(),
            }),
            Ok(_) => return stale_note(&meeting_id, LibraryReadError::SnapshotStale),
            Err(error) => return stale_note(&meeting_id, error),
        }
    }
    DevNoteResponse {
        state: "note",
        meeting_id,
        claims,
        message: "Located means these words occur in the transcript. It does not mean semantic support was verified."
            .into(),
    }
}

#[tauri::command]
fn library_dev_open_evidence(
    handle: String,
    locator_ordinal: usize,
    state: State<'_, DevSurfaceState>,
) -> DevEvidenceResponse {
    let guard = state.library.lock().expect("development library lock");
    let Some(library) = guard.as_ref() else {
        return unavailable_evidence(&state);
    };
    let Some(hit) = library.handles.get(&handle) else {
        return stale_evidence();
    };
    match library
        .projection
        .open_claim_evidence(&library.storage, hit, locator_ordinal)
    {
        Ok(evidence) => DevEvidenceResponse {
            state: "evidence",
            meeting_id: Some(evidence.meeting_id),
            source_turn_index: Some(evidence.source_turn_index),
            text: Some(evidence.text),
            message: "Exact locator text from the synthetic transcript.".into(),
        },
        Err(_) => stale_evidence(),
    }
}

fn create_dev_library(app: &AppHandle) -> Result<DevLibrary, String> {
    let app_data = app.path().app_data_dir().map_err(error_text)?;
    let protected_root = app.path().resource_dir().map_err(error_text)?;
    let storage = StorageRoot::create(&app_data, &protected_root).map_err(error_text)?;
    seed_synthetic_fixture(&storage)?;
    let projection = LibraryProjection::rebuild_with_projector(
        &storage,
        ReadLimits::default(),
        Arc::new(SyntheticProjector),
    )
    .map_err(|_| "The synthetic development library could not be projected.".to_string())?;
    Ok(DevLibrary {
        storage,
        projection,
        handles: HashMap::new(),
    })
}

fn seed_synthetic_fixture(storage: &StorageRoot) -> Result<(), String> {
    let marker = storage.path().join(FIXTURE_MARKER);
    if marker.exists() {
        return Ok(());
    }
    let directory = storage.path().join("meetings").join(FIXTURE_MEETING_ID);
    if directory.exists() {
        return Err("The synthetic development fixture is incomplete. Remove only this development app’s data and reopen it.".into());
    }
    for child in ["", "capture", "transcript", "notes", "deletion"] {
        create_private_dir(&directory.join(child)).map_err(error_text)?;
    }
    let rule = AudioRetentionRule::DeleteAfter { seconds: 60 };
    let policy = retention_policy_sha256(&rule);
    let attempt = json!({
        "schema": "capture-attempt/1",
        "meeting_id": FIXTURE_MEETING_ID,
        "attempt_id": "11111111-1111-4111-8111-111111111111",
        "created_at_epoch_seconds": 1_728_000_000_u64,
        "application_build_sha256": "a".repeat(64),
        "participant_notice_version": NOTICE_VERSION,
        "operator_attestation": {"participants_consented": true, "headphones": true, "operator_alone": true},
        "retention_policy_sha256": policy,
    });
    write_new(
        &directory.join("attempt.json"),
        &serde_json::to_vec_pretty(&attempt).map_err(error_text)?,
    )?;
    for relative in [
        "ownership.json",
        "capture/session.json",
        "deletion/audio-deletion.json",
    ] {
        write_new(&directory.join(relative), b"{}\n")?;
    }
    let transcript = json!({
        "schema": "capture-transcript/1", "source": "development-sanitized-fixture", "attribution": "channel",
        "bleed": null, "voiceprint": null, "capture_health": {},
        "turns": [
            {"start": 0.0, "end": 1.0, "speaker": "Sample", "text": "Use Thursday as the sample launch date.", "gated": false},
            {"start": 1.0, "end": 2.0, "speaker": "Sample", "text": "Schedule the sample design review before the demo.", "gated": false},
            {"start": 2.0, "end": 3.0, "speaker": "Sample", "text": "withheld sample detail", "gated": true}
        ]
    });
    let transcript_bytes = serde_json::to_vec_pretty(&transcript).map_err(error_text)?;
    let transcript_digest = digest(&transcript_bytes);
    let transcript_relative = format!("transcript/{transcript_digest}.json");
    write_new(&directory.join(&transcript_relative), &transcript_bytes)?;
    let note_json = b"{}\n";
    let note_markdown = b"# Sanitized fixture\n";
    let note_json_digest = digest(note_json);
    let note_markdown_digest = digest(note_markdown);
    let note_json_relative = format!("notes/{note_json_digest}.json");
    let note_markdown_relative = format!("notes/{note_markdown_digest}.md");
    write_new(&directory.join(&note_json_relative), note_json)?;
    write_new(&directory.join(&note_markdown_relative), note_markdown)?;
    let reference = |relative: &str| artifact_ref(&directory, relative).map_err(error_text);
    let record = MeetingRecord {
        schema: MeetingSchema::V2,
        meeting_id: FIXTURE_MEETING_ID.into(),
        lifecycle: MeetingLifecycle::Ready,
        retention: AudioRetention {
            rule,
            policy_sha256: policy,
            next_deletion_at_epoch_seconds: Some(1_728_000_060),
            state: AudioState::Released,
            deletion_receipt: Some(reference("deletion/audio-deletion.json")?),
        },
        artifacts: MeetingArtifacts {
            attempt: reference("attempt.json")?,
            ownership: Some(reference("ownership.json")?),
            capture_session: Some(reference("capture/session.json")?),
            microphone_audio: Some(fake_audio_ref("capture/mic.wav", 'b')),
            system_audio: Some(fake_audio_ref("capture/system.wav", 'c')),
            current_transcript: Some(reference(&transcript_relative)?),
            current_note: Some(NoteRevisionRef {
                json: reference(&note_json_relative)?,
                markdown: reference(&note_markdown_relative)?,
                source_transcript_sha256: transcript_digest,
            }),
        },
        pending_storage_operation: None,
    };
    write_meeting(&directory, &record).map_err(error_text)?;
    write_new(&marker, b"{\"schema\":\"library-dev-fixture/1\"}\n")
}

struct SyntheticProjector;

impl NoteProjector for SyntheticProjector {
    fn project(&self, request: &ProjectRequest) -> Result<Vec<u8>, ProjectTransportError> {
        let claims = [
            (
                "decision",
                "Use Thursday as the sample launch date.",
                0_u64,
                "Thursday",
            ),
            (
                "action",
                "Schedule the sample design review before the demo.",
                1_u64,
                "sample design review",
            ),
        ]
        .into_iter()
        .enumerate()
        .map(|(ordinal, (claim_type, claim, turn, evidence))| {
            let start = scalar_offset(claim, evidence).expect("fixture locator");
            let end = start + evidence.chars().count() as u64;
            json!({
                "claim_ordinal": ordinal as u64,
                "claim_sha256": digest(claim.as_bytes()),
                "claim_type": claim_type,
                "evidence_state": "located",
                "claim": claim,
                "locators": [{
                    "turn": turn,
                    "start": start,
                    "end": end,
                    "text_sha256": digest(evidence.as_bytes())
                }]
            })
        })
        .collect::<Vec<_>>();
        let frame = json!({
            "schema": "note-projection-result/1",
            "request_id": request.request_id,
            "operation": "note.project",
            "outcome": "succeeded",
            "projection": {
                "schema": "note-claim-projection/1",
                "note_json_sha256": request.note_json_sha256,
                "note_markdown_sha256": request.note_markdown_sha256,
                "transcript_sha256": request.transcript_sha256,
                "claims": claims
            },
            "failure": null
        });
        let mut bytes = serde_json::to_vec(&frame).map_err(|_| ProjectTransportError)?;
        bytes.push(b'\n');
        Ok(bytes)
    }
}

fn retain_handle(library: &mut DevLibrary, hit: LibraryHit) -> String {
    let handle = Uuid::new_v4().to_string();
    library.handles.insert(handle.clone(), hit);
    handle
}

fn write_new(path: &Path, bytes: &[u8]) -> Result<(), String> {
    durable_create_new(path, bytes).map_err(error_text)
}

fn fake_audio_ref(relative_path: &str, byte: char) -> ArtifactRef {
    ArtifactRef {
        relative_path: relative_path.into(),
        sha256: byte.to_string().repeat(64),
    }
}

fn digest(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

fn scalar_offset(text: &str, needle: &str) -> Option<u64> {
    text.find(needle)
        .map(|byte_offset| text[..byte_offset].chars().count() as u64)
}

fn claim_type_name(
    value: local_meeting_notes_session_core::note_projection::ClaimType,
) -> &'static str {
    match value {
        local_meeting_notes_session_core::note_projection::ClaimType::Decision => "decision",
        local_meeting_notes_session_core::note_projection::ClaimType::Action => "action",
        local_meeting_notes_session_core::note_projection::ClaimType::Proposal => "proposal",
        local_meeting_notes_session_core::note_projection::ClaimType::Question => "question",
    }
}

fn evidence_state_name(value: ClaimEvidenceState) -> &'static str {
    match value {
        ClaimEvidenceState::Located => "located",
    }
}

fn stale_search(_: LibraryReadError) -> DevSearchResponse {
    DevSearchResponse {
        state: "stale",
        results: Vec::new(),
        message: "That view is stale. Reopen the sanitized sample and try again.".into(),
    }
}

fn stale_note(meeting_id: &str, _: LibraryReadError) -> DevNoteResponse {
    DevNoteResponse {
        state: "stale",
        meeting_id: meeting_id.into(),
        claims: Vec::new(),
        message: "That note view is stale. Reopen the sanitized sample and try again.".into(),
    }
}

fn stale_evidence() -> DevEvidenceResponse {
    DevEvidenceResponse {
        state: "stale",
        meeting_id: None,
        source_turn_index: None,
        text: None,
        message: "That evidence view is stale. Reopen the note and try again.".into(),
    }
}

fn unavailable_search(state: &DevSurfaceState) -> DevSearchResponse {
    DevSearchResponse {
        state: "empty",
        results: Vec::new(),
        message: startup_message(state),
    }
}

fn unavailable_note(meeting_id: &str, state: &DevSurfaceState) -> DevNoteResponse {
    DevNoteResponse {
        state: "empty",
        meeting_id: meeting_id.into(),
        claims: Vec::new(),
        message: startup_message(state),
    }
}

fn unavailable_evidence(state: &DevSurfaceState) -> DevEvidenceResponse {
    DevEvidenceResponse {
        state: "empty",
        meeting_id: None,
        source_turn_index: None,
        text: None,
        message: startup_message(state),
    }
}

fn startup_message(state: &DevSurfaceState) -> String {
    state
        .startup_error
        .lock()
        .expect("development startup lock")
        .clone()
        .unwrap_or_else(|| "No synthetic fixture is available.".into())
}

fn error_text(error: impl std::fmt::Display) -> String {
    error.to_string()
}

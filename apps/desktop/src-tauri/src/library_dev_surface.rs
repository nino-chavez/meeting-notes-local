//! Development-only, synthetic read surface for the library reader.
//!
//! This module is compiled only with `library-dev-surface`. It has no capture,
//! retention, export, correction, regeneration, or production-data commands.

use std::path::Path;
use std::sync::{Arc, Mutex};

use local_meeting_notes_session_core::library_read::{LibraryProjection, ReadLimits};
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
use serde_json::json;
use sha2::{Digest, Sha256};
use tauri::{AppHandle, Manager, State};

use crate::library_reader::{
    LibraryEvidenceResponse, LibraryNoteResponse, LibraryReader, LibrarySearchResponse,
    LibrarySnapshot,
};

const DEV_IDENTIFIER: &str = "com.ninochavez.local-meeting-notes.library-dev";
const FIXTURE_STORAGE_GENERATION: &str = "fixture-v2";
const FIXTURE_MEETING_ID: &str = "library-dev-sample-v2";
const FIXTURE_MARKER: &str = "library-dev-fixture-v2.json";
const NOTICE_VERSION: &str = "internal-transcript-alpha/1";

struct DevLibrary {
    reader: LibraryReader,
}

#[derive(Default)]
pub struct DevSurfaceState {
    library: Mutex<Option<DevLibrary>>,
    startup_error: Mutex<Option<String>>,
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
        .setup(|app| {
            initialize(app.handle())
                .map_err(|error| Box::<dyn std::error::Error>::from(std::io::Error::other(error)))
        })
        .run(tauri::generate_context!())
        .expect("Local Meeting Notes library development surface failed");
}

fn initialize(app: &AppHandle) -> Result<(), String> {
    if app.config().identifier != DEV_IDENTIFIER {
        return Err(
            "The library development surface requires its isolated Tauri configuration.".into(),
        );
    }
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
fn library_dev_snapshot(state: State<'_, DevSurfaceState>) -> LibrarySnapshot {
    snapshot_response(&state)
}

fn snapshot_response(state: &DevSurfaceState) -> LibrarySnapshot {
    let mut guard = state.library.lock().expect("development library lock");
    if let Some(library) = guard.as_mut() {
        let mut response = library.reader.snapshot();
        if response.state == "populated" {
            for row in &mut response.rows {
                row.label = "Sanitized library sample".into();
            }
            response.message =
                "Synthetic, sanitized development data only. This does not open production data."
                    .into();
        } else {
            response.message =
                "The synthetic meeting is unavailable. Reopen this development app to retry."
                    .into();
        }
        return response;
    }
    let mut response = LibraryReader::unavailable_snapshot();
    response.message = startup_message(state);
    response
}

#[tauri::command]
fn library_dev_search(query: String, state: State<'_, DevSurfaceState>) -> LibrarySearchResponse {
    search_response(&query, &state)
}

fn search_response(query: &str, state: &DevSurfaceState) -> LibrarySearchResponse {
    let mut guard = state.library.lock().expect("development library lock");
    let Some(library) = guard.as_mut() else {
        return unavailable_search(state);
    };
    synthetic_search_response(library.reader.search(query))
}

fn synthetic_search_response(mut response: LibrarySearchResponse) -> LibrarySearchResponse {
    for result in &mut response.results {
        if result.kind == "meeting" {
            result.text = Some("Sanitized library sample".into());
        }
    }
    response.message = match response.state {
        "results" | "results-incomplete" => "Results from the synthetic meeting.",
        "no-results" => "No sanitized sample matched that search.",
        "bounded" => "That search has too many matches. Use a more specific phrase.",
        "stale" => "That view is stale. Reopen the sanitized sample and try again.",
        _ => "No synthetic fixture is available.",
    }
    .into();
    response
}

#[tauri::command]
fn library_dev_open_note(handle: String, state: State<'_, DevSurfaceState>) -> LibraryNoteResponse {
    open_note_response(&handle, &state)
}

fn open_note_response(handle: &str, state: &DevSurfaceState) -> LibraryNoteResponse {
    let mut guard = state.library.lock().expect("development library lock");
    let Some(library) = guard.as_mut() else {
        return unavailable_note("", state);
    };
    let mut response = library.reader.open_note(handle);
    response.message = match response.state {
        "note" => "Words located in the transcript. Semantic support has not been reviewed.",
        "summary-failed" => {
            "The synthetic note was not produced. Search retained transcript text instead."
        }
        "stale" => "That note view is stale. Reopen the sanitized sample and try again.",
        _ => "No synthetic fixture is available.",
    }
    .into();
    response
}

#[tauri::command]
fn library_dev_open_evidence(
    handle: String,
    locator_ordinal: usize,
    state: State<'_, DevSurfaceState>,
) -> LibraryEvidenceResponse {
    open_evidence_response(&handle, locator_ordinal, &state)
}

fn open_evidence_response(
    handle: &str,
    locator_ordinal: usize,
    state: &DevSurfaceState,
) -> LibraryEvidenceResponse {
    let mut guard = state.library.lock().expect("development library lock");
    let Some(library) = guard.as_mut() else {
        return unavailable_evidence(state);
    };
    let mut response = library.reader.open_evidence(handle, locator_ordinal);
    response.message = match response.state {
        "evidence" => "Exact locator text from the synthetic transcript.",
        "stale" => "That evidence view is stale. Reopen the note and try again.",
        _ => "No synthetic fixture is available.",
    }
    .into();
    response
}

fn create_dev_library(app: &AppHandle) -> Result<DevLibrary, String> {
    let app_data = app.path().app_data_dir().map_err(error_text)?;
    let protected_root = app.path().resource_dir().map_err(error_text)?;
    let storage = StorageRoot::create(&app_data.join(FIXTURE_STORAGE_GENERATION), &protected_root)
        .map_err(error_text)?;
    create_dev_library_at(storage)
}

fn create_dev_library_at(storage: StorageRoot) -> Result<DevLibrary, String> {
    seed_synthetic_fixture(&storage)?;
    project_seeded_library(storage)
}

fn project_seeded_library(storage: StorageRoot) -> Result<DevLibrary, String> {
    let projection = LibraryProjection::rebuild_with_projector(
        &storage,
        ReadLimits::default(),
        Arc::new(SyntheticProjector),
    )
    .map_err(|error| {
        format!("The synthetic development library could not be projected: {error}.")
    })?;
    let rows = projection.rows();
    if rows.len() != 1 || rows[0].meeting_id != FIXTURE_MEETING_ID {
        return Err("The synthetic development fixture is incomplete. Remove only this development app’s data and reopen it.".into());
    }
    Ok(DevLibrary {
        reader: LibraryReader::new(storage, projection),
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
        "operator_attestation": {"participantsConsented": true, "headphones": true, "operatorAlone": true},
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
            {"start": 0.0, "end": 1.0, "speaker": "Them", "text": "Use Thursday in the café sample launch date.", "gated": false},
            {"start": 1.0, "end": 2.0, "speaker": "Them", "text": "Schedule the sample design review before the demo.", "gated": false},
            {"start": 2.0, "end": 3.0, "speaker": "Me", "text": "withheld sample detail", "gated": true}
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
    write_new(&marker, b"{\"schema\":\"library-dev-fixture/2\"}\n")
}

struct SyntheticProjector;

impl NoteProjector for SyntheticProjector {
    fn project(&self, request: &ProjectRequest) -> Result<Vec<u8>, ProjectTransportError> {
        let claims = [
            (
                "decision",
                "Use Thursday in the café sample launch date.",
                0_u64,
                "café",
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
            format!(
                "{{\"claim_ordinal\":{ordinal},\"claim_sha256\":\"{}\",\"claim_type\":\"{claim_type}\",\"evidence_state\":\"located\",\"claim\":\"{claim}\",\"locators\":[{{\"turn\":{turn},\"start\":{start},\"end\":{end},\"text_sha256\":\"{}\"}}]}}",
                digest(claim.as_bytes()),
                digest(evidence.as_bytes()),
            )
        })
        .collect::<Vec<_>>()
        .join(",");
        let mut bytes = format!(
            "{{\"schema\":\"note-projection-result/1\",\"request_id\":\"{}\",\"operation\":\"note.project\",\"outcome\":\"succeeded\",\"projection\":{{\"schema\":\"note-claim-projection/1\",\"note_json_sha256\":\"{}\",\"note_markdown_sha256\":\"{}\",\"transcript_sha256\":\"{}\",\"claims\":[{claims}]}},\"failure\":null}}",
            request.request_id,
            request.note_json_sha256,
            request.note_markdown_sha256,
            request.transcript_sha256,
        )
        .into_bytes();
        bytes.push(b'\n');
        Ok(bytes)
    }
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

fn unavailable_search(state: &DevSurfaceState) -> LibrarySearchResponse {
    let mut response = LibraryReader::unavailable_search();
    response.message = startup_message(state);
    response
}

fn unavailable_note(meeting_id: &str, state: &DevSurfaceState) -> LibraryNoteResponse {
    let mut response = LibraryReader::unavailable_note(meeting_id);
    response.message = startup_message(state);
    response
}

fn unavailable_evidence(state: &DevSurfaceState) -> LibraryEvidenceResponse {
    let mut response = LibraryReader::unavailable_evidence();
    response.message = startup_message(state);
    response
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

#[cfg(test)]
mod tests {
    use super::*;
    use crate::library_reader::LibrarySearchResult;
    use local_meeting_notes_session_core::meeting::{
        MeetingLifecycle, load_meeting, write_meeting,
    };
    use local_meeting_notes_session_core::storage::{create_private_dir, durable_replace};
    use tempfile::TempDir;

    fn seeded_library() -> (TempDir, DevLibrary) {
        let temporary = TempDir::new().unwrap();
        let protected_root = temporary.path().join("protected-root");
        create_private_dir(&protected_root).unwrap();
        let storage = StorageRoot::create(&temporary.path().join("data"), &protected_root).unwrap();
        seed_synthetic_fixture(&storage).unwrap();
        clear_test_xattrs(storage.path());
        let library = project_seeded_library(storage).unwrap();
        (temporary, library)
    }

    fn populated_state() -> (TempDir, DevSurfaceState) {
        let (temporary, library) = seeded_library();
        let state = DevSurfaceState::default();
        *state.library.lock().unwrap() = Some(library);
        (temporary, state)
    }

    fn captured_reader() -> (TempDir, LibraryReader) {
        let temporary = TempDir::new().unwrap();
        let protected_root = temporary.path().join("protected-root");
        create_private_dir(&protected_root).unwrap();
        let storage = StorageRoot::create(&temporary.path().join("data"), &protected_root).unwrap();
        seed_synthetic_fixture(&storage).unwrap();
        clear_test_xattrs(storage.path());

        let directory = storage.path().join("meetings").join(FIXTURE_MEETING_ID);
        let mut meeting = load_meeting(&directory).unwrap();
        meeting.lifecycle = MeetingLifecycle::Captured;
        meeting.artifacts.current_transcript = None;
        meeting.artifacts.current_note = None;
        write_meeting(&directory, &meeting).unwrap();

        clear_test_xattrs(storage.path());

        let reader = project_seeded_library(storage).unwrap().reader;
        (temporary, reader)
    }

    #[cfg(target_os = "macos")]
    fn clear_test_xattrs(path: &Path) {
        let status = std::process::Command::new("xattr")
            .args(["-rc"])
            .arg(path)
            .status()
            .unwrap();
        assert!(status.success());
    }

    #[cfg(not(target_os = "macos"))]
    fn clear_test_xattrs(_: &Path) {}

    #[test]
    fn ipc_response_helpers_return_populated_snapshot_search_note_and_unicode_evidence() {
        let (_temporary, state) = populated_state();
        let snapshot = snapshot_response(&state);
        assert_eq!(snapshot.state, "populated");
        assert_eq!(snapshot.rows.len(), 1);
        let snapshot_json = serde_json::to_value(&snapshot).unwrap();
        assert_eq!(snapshot_json["rows"][0]["meetingId"], FIXTURE_MEETING_ID);
        assert_eq!(snapshot_json["rows"][0]["transcriptAvailable"], true);

        let search = search_response("café", &state);
        assert_eq!(search.state, "results");
        assert!(search.results.len() >= 2);
        let claim = search
            .results
            .iter()
            .find(|result| result.kind == "claim")
            .unwrap();
        assert_eq!(
            claim.text.as_deref(),
            Some("Use Thursday in the café sample launch date.")
        );
        assert_eq!(claim.source_turn_index, None);
        assert_eq!(claim.claim_ordinal, Some(0));
        assert_eq!(
            serde_json::to_value(&search).unwrap()["results"][0]["claimOrdinal"],
            0
        );
        assert!(!search.results[0].handle.is_empty());

        let note = open_note_response(&snapshot_response(&state).rows[0].handle, &state);
        assert_eq!(note.state, "note");
        assert_eq!(note.meeting_id, FIXTURE_MEETING_ID);
        assert_eq!(note.claims.len(), 2);
        let handle = note.claims[0].handle.clone();
        assert_ne!(handle, note.meeting_id);
        assert_ne!(handle, note.claims[0].claim);
        assert!(note.claims[0].locator_count > 0);

        let evidence = open_evidence_response(&handle, 0, &state);
        assert_eq!(evidence.state, "evidence");
        assert_eq!(evidence.meeting_id.as_deref(), Some(FIXTURE_MEETING_ID));
        assert_eq!(evidence.source_turn_index, Some(0));
        assert_eq!(evidence.start, Some(20));
        assert_eq!(evidence.end, Some(24));
        assert_eq!(evidence.text.as_deref(), Some("café"));
    }

    #[test]
    fn stale_fixture_marker_without_expected_meeting_fails_closed() {
        let temporary = TempDir::new().unwrap();
        let protected_root = temporary.path().join("protected-root");
        create_private_dir(&protected_root).unwrap();
        let storage = StorageRoot::create(&temporary.path().join("data"), &protected_root).unwrap();
        write_new(
            &storage.path().join(FIXTURE_MARKER),
            b"{\"schema\":\"library-dev-fixture/2\"}\n",
        )
        .unwrap();

        let error = create_dev_library_at(storage).err().unwrap();
        assert!(error.contains("synthetic development fixture is incomplete"));
    }

    #[test]
    fn ipc_response_helpers_redact_empty_no_result_withheld_and_stale_states() {
        let empty = DevSurfaceState::default();
        assert_eq!(snapshot_response(&empty).state, "unavailable");
        let empty_search = search_response("anything", &empty);
        assert_eq!(empty_search.state, "unavailable");
        assert!(empty_search.results.is_empty());
        let empty_note = open_note_response("opaque-handle", &empty);
        assert_eq!(empty_note.state, "unavailable");
        assert!(empty_note.claims.is_empty());
        let empty_evidence = open_evidence_response("opaque-handle", 0, &empty);
        assert_eq!(empty_evidence.state, "unavailable");
        assert!(empty_evidence.text.is_none());
        assert!(empty_evidence.meeting_id.is_none());
        assert!(empty_evidence.source_turn_index.is_none());

        let (temporary, state) = populated_state();
        let no_results = search_response("not-present", &state);
        assert_eq!(no_results.state, "no-results");
        assert!(no_results.results.is_empty());
        assert_eq!(
            serde_json::to_value(&no_results).unwrap()["results"],
            json!([])
        );

        let withheld = search_response("withheld", &state);
        assert_eq!(withheld.state, "results");
        assert_eq!(withheld.results.len(), 1);
        assert_eq!(withheld.results[0].kind, "withheld");
        assert_eq!(withheld.results[0].text, None);
        assert_eq!(withheld.results[0].source_turn_index, Some(2));
        assert!(
            !serde_json::to_string(&withheld)
                .unwrap()
                .contains("withheld sample detail")
        );

        let note = open_note_response(&snapshot_response(&state).rows[0].handle, &state);
        let handle = note.claims[0].handle.clone();
        let meeting_directory = temporary
            .path()
            .join("data")
            .join("meetings")
            .join(FIXTURE_MEETING_ID);
        let meeting = load_meeting(&meeting_directory).unwrap();
        let note_path =
            meeting_directory.join(meeting.artifacts.current_note.unwrap().json.relative_path);
        durable_replace(&note_path, b"{\"changed\":true}\n").unwrap();
        let stale = open_evidence_response(&handle, 0, &state);
        assert_eq!(stale.state, "stale");
        assert!(stale.text.is_none());
        assert!(stale.meeting_id.is_none());
        assert!(stale.source_turn_index.is_none());
        assert!(!serde_json::to_string(&stale).unwrap().contains("café"));
    }

    #[test]
    fn private_reader_keeps_exact_claim_precedence_and_locator_evidence() {
        let (_temporary, state) = populated_state();
        let mut guard = state.library.lock().unwrap();
        let reader = &mut guard.as_mut().unwrap().reader;

        let results = reader.search("café");
        assert_eq!(results.state, "results");
        assert!(results.results.iter().any(|result| result.kind == "claim"));
        assert!(
            results
                .results
                .iter()
                .any(|result| result.kind == "transcript")
        );
        let claim = results
            .results
            .iter()
            .find(|result| result.kind == "claim")
            .unwrap();
        let evidence = reader.open_evidence(&claim.handle, 0);
        assert_eq!(evidence.state, "evidence");
        assert_eq!(evidence.source_turn_index, Some(0));
        assert_eq!(evidence.text.as_deref(), Some("café"));
    }

    #[test]
    fn private_reader_discards_superseded_handles_after_each_response() {
        let (_temporary, state) = populated_state();
        let mut guard = state.library.lock().unwrap();
        let reader = &mut guard.as_mut().unwrap().reader;

        let mut prior_search_handle = String::new();
        for _ in 0..8 {
            let search = reader.search("café");
            assert_eq!(search.state, "results");
            assert_eq!(reader.retained_handle_count(), search.results.len());
            let handle = search.results[0].handle.clone();
            assert_eq!(reader.open_evidence(&handle, 0).state, "evidence");
            prior_search_handle = handle;
        }
        let no_results = reader.search("not-present");
        assert_eq!(no_results.state, "no-results");
        assert_eq!(reader.retained_handle_count(), 0);
        assert_eq!(reader.open_evidence(&prior_search_handle, 0).state, "stale");

        for _ in 0..8 {
            let snapshot = reader.snapshot();
            let note = reader.open_note(&snapshot.rows[0].handle);
            assert_eq!(note.state, "note");
            assert!(note.transcript_handle.is_some());
            assert_eq!(reader.retained_handle_count(), note.claims.len() + 1);
            assert_eq!(
                reader.open_evidence(&note.claims[0].handle, 0).state,
                "evidence"
            );
        }
        assert_eq!(reader.open_note("missing").state, "stale");
        assert_eq!(reader.retained_handle_count(), 0);
    }

    #[test]
    fn private_reader_returns_closed_empty_stale_and_withheld_responses() {
        let empty_temporary = TempDir::new().unwrap();
        let empty_protected_root = empty_temporary.path().join("protected-root");
        create_private_dir(&empty_protected_root).unwrap();
        let empty_storage =
            StorageRoot::create(&empty_temporary.path().join("data"), &empty_protected_root)
                .unwrap();
        let empty_projection =
            LibraryProjection::rebuild(&empty_storage, ReadLimits::default()).unwrap();
        let empty_snapshot = LibraryReader::new(empty_storage, empty_projection).snapshot();
        assert_eq!(empty_snapshot.state, "empty");
        assert_eq!(
            empty_snapshot.message,
            "No retained meetings are available."
        );

        let unavailable = LibraryReader::unavailable_search();
        assert_eq!(unavailable.state, "unavailable");
        assert!(unavailable.results.is_empty());
        assert_ne!(unavailable.message, empty_snapshot.message);
        assert!(!unavailable.message.contains("sample"));

        let (temporary, state) = populated_state();
        let (handle, withheld) = {
            let mut guard = state.library.lock().unwrap();
            let reader = &mut guard.as_mut().unwrap().reader;
            let withheld = reader.search("withheld");
            let snapshot = reader.snapshot();
            let note = reader.open_note(&snapshot.rows[0].handle);
            (note.claims[0].handle.clone(), withheld)
        };
        assert_eq!(withheld.state, "results");
        assert_eq!(withheld.results[0].kind, "withheld");
        assert!(withheld.results[0].text.is_none());
        assert!(
            !serde_json::to_string(&withheld)
                .unwrap()
                .contains("withheld sample detail")
        );

        let meeting_directory = temporary
            .path()
            .join("data")
            .join("meetings")
            .join(FIXTURE_MEETING_ID);
        let meeting = load_meeting(&meeting_directory).unwrap();
        durable_replace(
            &meeting_directory.join(meeting.artifacts.current_note.unwrap().json.relative_path),
            b"{\"changed\":true}\n",
        )
        .unwrap();
        let stale = state
            .library
            .lock()
            .unwrap()
            .as_mut()
            .unwrap()
            .reader
            .open_evidence(&handle, 0);
        assert_eq!(stale.state, "stale");
        assert!(stale.text.is_none());
        assert!(stale.meeting_id.is_none());
        assert!(!serde_json::to_string(&stale).unwrap().contains("café"));
        assert!(!stale.message.contains("café"));
    }

    #[test]
    fn private_reader_distinguishes_summary_failed_from_empty_note() {
        let temporary = TempDir::new().unwrap();
        let protected_root = temporary.path().join("protected-root");
        create_private_dir(&protected_root).unwrap();
        let storage = StorageRoot::create(&temporary.path().join("data"), &protected_root).unwrap();
        seed_synthetic_fixture(&storage).unwrap();
        clear_test_xattrs(storage.path());
        let directory = storage.path().join("meetings").join(FIXTURE_MEETING_ID);
        let mut meeting = load_meeting(&directory).unwrap();
        meeting.lifecycle = MeetingLifecycle::SummaryFailed;
        meeting.artifacts.current_note = None;
        write_meeting(&directory, &meeting).unwrap();

        let mut reader = project_seeded_library(storage).unwrap().reader;
        let snapshot = reader.snapshot();
        assert_eq!(snapshot.state, "populated");
        let note = reader.open_note(&snapshot.rows[0].handle);
        assert_eq!(note.state, "summary-failed");
        assert!(note.claims.is_empty());
    }

    #[test]
    fn private_reader_returns_transcript_only_when_no_current_note_is_admitted() {
        let temporary = TempDir::new().unwrap();
        let protected_root = temporary.path().join("protected-root");
        create_private_dir(&protected_root).unwrap();
        let storage = StorageRoot::create(&temporary.path().join("data"), &protected_root).unwrap();
        seed_synthetic_fixture(&storage).unwrap();
        clear_test_xattrs(storage.path());
        let directory = storage.path().join("meetings").join(FIXTURE_MEETING_ID);
        let mut meeting = load_meeting(&directory).unwrap();
        meeting.lifecycle = MeetingLifecycle::TranscriptReady;
        meeting.artifacts.current_note = None;
        write_meeting(&directory, &meeting).unwrap();

        let mut reader = project_seeded_library(storage).unwrap().reader;
        let snapshot = reader.snapshot();
        let note = reader.open_note(&snapshot.rows[0].handle);
        assert_eq!(note.state, "transcript-only");
        assert!(note.transcript_handle.is_some());
        assert!(note.claims.is_empty());
        assert!(note.message.contains("No admitted note"));
    }

    #[test]
    fn metadata_only_rows_never_issue_transcript_handles() {
        let (_temporary, mut reader) = captured_reader();

        let snapshot = reader.snapshot();
        assert_eq!(snapshot.rows.len(), 1);
        assert!(!snapshot.rows[0].transcript_available);
        assert_eq!(
            reader.open_transcript(&snapshot.rows[0].handle).state,
            "stale"
        );

        let snapshot = reader.snapshot();
        let note = reader.open_note(&snapshot.rows[0].handle);
        assert_eq!(note.state, "transcript-only");
        assert!(note.transcript_handle.is_none());
        assert_eq!(
            note.message,
            "No transcript was created for this retained meeting."
        );
    }

    #[test]
    fn development_wrapper_redacts_meeting_result_labels() {
        let response = synthetic_search_response(LibrarySearchResponse {
            state: "results",
            results: vec![LibrarySearchResult {
                handle: "opaque-handle".into(),
                kind: "meeting",
                meeting_id: FIXTURE_MEETING_ID.into(),
                text: Some("private meeting label".into()),
                source_turn_index: None,
                claim_ordinal: None,
                transcript_available: true,
            }],
            unavailable_count: 0,
            message: "untrusted test response".into(),
        });
        assert_eq!(response.state, "results");
        assert_eq!(response.results.len(), 1);
        assert_eq!(response.results[0].kind, "meeting");
        assert_eq!(
            response.results[0].text.as_deref(),
            Some("Sanitized library sample")
        );
        assert!(
            !serde_json::to_string(&response)
                .unwrap()
                .contains("private meeting label")
        );
    }
}

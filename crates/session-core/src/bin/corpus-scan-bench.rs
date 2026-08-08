//! Measures the file-scan library rebuild against a synthetic corpus.
//!
//! `vertical-slice.md` deferred any persistent index "until a measured corpus
//! exceeds the bounded scan envelope" and named a synthetic no-private-text
//! benchmark as the thing that would measure it. This is that benchmark.
//!
//! Every byte it writes is generated here from a counter. It reads no real
//! meeting, and it must never be pointed at a live storage root: it creates the
//! corpus it measures.
//!
//! ```text
//! corpus-scan-bench <work-dir> <meetings> [turns-per-meeting]
//! ```
//!
//! Prints one JSON receipt on stdout. Progress goes to stderr so the receipt
//! survives a pipe.
//!
//! The query figures report `{shown, matched}`. Before 2026-08-08 they reported
//! the string `library read capacity exceeded` for a common word at every size
//! this harness was ever run at, which is the defect the truncation fixed.
//!
//! **It measures both halves of a library open.** The projection rebuild was the
//! only number here until 2026-08-08, and `LibraryReader::rebuild` also syncs the
//! corpus index on the same path — so a launch cost quoted from the scan alone is
//! the smaller half of an unknown sum. Both are reported, cold and warm.

use std::collections::HashSet;
use std::path::Path;
use std::time::Instant;

use local_meeting_notes_session_core::corpus_index::CorpusIndex;
use local_meeting_notes_session_core::corpus_window::EmbedderIdentity;
use local_meeting_notes_session_core::library_read::{LibraryProjection, ReadLimits};
use local_meeting_notes_session_core::meeting::{
    ArtifactRef, AudioRetention, AudioRetentionRule, AudioState, MeetingArtifacts,
    MeetingLifecycle, MeetingRecord, MeetingSchema, artifact_ref, retention_policy_sha256,
    write_meeting,
};
use local_meeting_notes_session_core::storage::{
    StorageRoot, create_private_dir, durable_create_new,
};
use sha2::{Digest, Sha256};

/// Deterministic synthetic turn text. No private material can reach this file.
fn turn_text(meeting: usize, turn: usize) -> String {
    const WORDS: [&str; 8] = [
        "alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta",
    ];
    let mut text = String::with_capacity(96);
    for offset in 0..12 {
        if offset > 0 {
            text.push(' ');
        }
        text.push_str(WORDS[(meeting + turn + offset) % WORDS.len()]);
    }
    // One rare token per meeting, so a warm query has something to find that is
    // not present in every row.
    if turn == meeting % 7 {
        text.push_str(&format!(" marker{meeting:06}"));
    }
    text
}

fn write_synthetic_meeting(
    storage: &StorageRoot,
    index: usize,
    turns_per_meeting: usize,
) -> Result<u64, Box<dyn std::error::Error>> {
    let id = format!("synthetic-{index:06}");
    let directory = storage.path().join("meetings").join(&id);
    for child in ["", "capture", "transcript", "deletion"] {
        create_private_dir(&directory.join(child))?;
    }

    let created = 1_700_000_000_u64 + index as u64;
    let rule = AudioRetentionRule::DeleteAfter { seconds: 60 };
    let policy = retention_policy_sha256(&rule);
    let attempt = serde_json::json!({
        "schema": "capture-attempt/1",
        "meeting_id": id,
        "attempt_id": "11111111-1111-4111-8111-111111111111",
        "created_at_epoch_seconds": created,
        "application_build_sha256": "a".repeat(64),
        "participant_notice_version": "internal-transcript-alpha/1",
        "operator_attestation": {
            "participantsConsented": true,
            "headphones": true,
            "operatorAlone": true,
        },
        "retention_policy_sha256": policy,
    });
    durable_create_new(
        &directory.join("attempt.json"),
        &serde_json::to_vec_pretty(&attempt)?,
    )?;
    for path in [
        "ownership.json",
        "capture/session.json",
        "deletion/audio-deletion.json",
    ] {
        durable_create_new(&directory.join(path), b"{}\n")?;
    }

    let turns: Vec<_> = (0..turns_per_meeting)
        .map(|turn| {
            serde_json::json!({
                "start": turn as f64,
                "end": turn as f64 + 0.5,
                "speaker": if turn % 2 == 0 { "Me" } else { "Them" },
                "text": turn_text(index, turn),
                "gated": false,
            })
        })
        .collect();
    let transcript = serde_json::to_vec_pretty(&serde_json::json!({
        "schema": "capture-transcript/1",
        "source": "synthetic",
        "attribution": "channel",
        "bleed": null,
        "voiceprint": null,
        "capture_health": {},
        "turns": turns,
    }))?;
    let transcript_bytes = transcript.len() as u64;
    let digest = format!("{:x}", Sha256::digest(&transcript));
    let relative = format!("transcript/{digest}.json");
    durable_create_new(&directory.join(&relative), &transcript)?;

    let reference = |path: &str| artifact_ref(&directory, path).expect("synthetic artifact");
    // TranscriptReady, not Ready. A Ready row makes the projection call the
    // out-of-process note projector once per meeting, which would measure the
    // worker rather than the scan. The deferral clause this benchmark exists to
    // settle is about walking and validating files.
    let record = MeetingRecord {
        schema: MeetingSchema::V2,
        meeting_id: id,
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
    write_meeting(&directory, &record)?;
    Ok(transcript_bytes)
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let arguments: Vec<String> = std::env::args().collect();
    if arguments.len() < 3 {
        eprintln!("usage: corpus-scan-bench <work-dir> <meetings> [turns-per-meeting]");
        std::process::exit(2);
    }
    let work_dir = std::fs::canonicalize(Path::new(&arguments[1]))?;
    let meetings: usize = arguments[2].parse()?;
    let turns_per_meeting: usize = arguments
        .get(3)
        .map(|value| value.parse())
        .transpose()?
        .unwrap_or(200);

    let repository = work_dir.join("repository");
    create_private_dir(&repository)?;
    let root = work_dir.join("data");
    if root.exists() {
        std::fs::remove_dir_all(&root)?;
    }
    let storage = StorageRoot::create(&root, &repository)?;

    let write_started = Instant::now();
    let mut transcript_bytes = 0_u64;
    for index in 0..meetings {
        transcript_bytes += write_synthetic_meeting(&storage, index, turns_per_meeting)?;
        if index % 100 == 99 {
            eprintln!("wrote {} of {meetings}", index + 1);
        }
    }
    let write_seconds = write_started.elapsed().as_secs_f64();

    // The bench measures the scan, not the default refusal. Raise both bounds
    // past the corpus so a capacity refusal cannot be mistaken for a timing.
    let limits = ReadLimits {
        max_meetings: meetings.max(1) * 2,
        max_total_bytes: transcript_bytes.saturating_mul(4).max(64 * 1024 * 1024),
        max_transcript_bytes: 16 * 1024 * 1024,
    };

    let cold_started = Instant::now();
    let projection = LibraryProjection::rebuild_excluding(&storage, limits, &HashSet::new())?;
    let cold_milliseconds = cold_started.elapsed().as_secs_f64() * 1000.0;
    let rows = projection.rows().len();

    // Warm query: a token present in exactly one meeting, then one present in
    // every meeting. The second is the worst case, and refusing it is a valid
    // measured outcome — `MAX_SEARCH_RESULTS` makes a broad query return
    // `library-capacity-exceeded` rather than a silent prefix. Record that
    // instead of aborting, because it is the number the store has to answer.
    let measure = |query: &str| {
        let started = Instant::now();
        let outcome = projection.search(query);
        let milliseconds = (started.elapsed().as_secs_f64() * 100_000.0).round() / 100.0;
        match outcome {
            // Two numbers since 2026-08-08: what a person is shown, and how many
            // matched. Before that this field held the string
            // "library read capacity exceeded" at every size measured, because a
            // common word refused the whole query rather than answering it.
            Ok(found) => (
                milliseconds,
                serde_json::json!({"shown": found.hits.len(), "matched": found.total}),
            ),
            Err(error) => (milliseconds, serde_json::json!(format!("{error}"))),
        }
    };
    let (rare_milliseconds, rare_hits) = measure(&format!("marker{:06}", meetings / 2));
    let (common_milliseconds, common_hits) = measure("alpha");

    // The index sync, which the scan number alone leaves out. `LibraryReader`
    // runs both on every library open, so a launch cost is their sum and not
    // either one — and until 2026-08-08 only the first had ever been measured.
    //
    // Cold is the whole corpus written: rows, turns, windows, segments. Warm is
    // the same call against an unchanged corpus, which is what almost every open
    // actually is — one digest over the projection's row identities and one
    // SELECT, per `sync_if_changed`.
    let mut index = CorpusIndex::open(&storage)?;
    let cold_sync_started = Instant::now();
    let synced = index.sync_if_changed(&projection)?;
    let cold_sync_milliseconds = cold_sync_started.elapsed().as_secs_f64() * 1000.0;
    let warm_sync_started = Instant::now();
    let resynced = index.sync_if_changed(&projection)?;
    let warm_sync_milliseconds = warm_sync_started.elapsed().as_secs_f64() * 1000.0;
    let windows = index
        .vector_coverage(&EmbedderIdentity::measured())?
        .windows;

    let receipt = serde_json::json!({
        "schema": "corpus-scan-bench/1",
        "corpus": {
            "meetings": meetings,
            "turns_per_meeting": turns_per_meeting,
            "transcript_bytes": transcript_bytes,
        },
        "rows_projected": rows,
        "write_seconds": (write_seconds * 1000.0).round() / 1000.0,
        "cold_rebuild_milliseconds": (cold_milliseconds * 100.0).round() / 100.0,
        "warm_rare_query_milliseconds": rare_milliseconds,
        "warm_rare_query_hits": rare_hits,
        "warm_common_query_milliseconds": common_milliseconds,
        "warm_common_query_hits": common_hits,
        "search_result_cap": local_meeting_notes_session_core::library_read::MAX_SEARCH_RESULTS,
        "cold_index_sync_milliseconds": (cold_sync_milliseconds * 100.0).round() / 100.0,
        "cold_index_sync_wrote": synced.is_some(),
        "warm_index_sync_milliseconds": (warm_sync_milliseconds * 100.0).round() / 100.0,
        "warm_index_sync_wrote": resynced.is_some(),
        "corpus_windows": windows,
    });
    println!("{}", serde_json::to_string_pretty(&receipt)?);
    Ok(())
}

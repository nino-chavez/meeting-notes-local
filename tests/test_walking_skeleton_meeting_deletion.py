"""Artifact contracts complementing executable trust-state transition tests."""

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "prototype/walking-skeleton/app.js").read_text()
CSS = (ROOT / "prototype/walking-skeleton/styles.css").read_text()
README = (ROOT / "prototype/walking-skeleton/README.md").read_text()
MANIFEST = json.loads((ROOT / "prototype/walking-skeleton/review-manifest.json").read_text())


def test_whole_meeting_scope_is_explicit_and_staged():
    for consequence in (
        "Meeting metadata",
        "Canonical transcript and every transcript revision",
        "Notes and stale note history",
        "Evidence links",
        "Retained audio, if any",
        "Your separate voice profile",
        "Your audio-retention policy",
        "Every other meeting",
    ):
        assert consequence in APP
    assert "Step 1 of 2 · review scope" in APP
    assert "Step 2 of 2 · explicit confirmation" in APP
    assert "I understand this permanently deletes the entire meeting." in APP
    assert "Cancel — keep this meeting" in APP
    assert "This is different from deleting the recording." in APP


def test_interrupted_request_receipt_is_content_free_and_failure_is_visible():
    assert "trustState.validateDeletionReceipt(written)" in APP
    assert "This recovery state cannot be trusted." in APP
    assert "No operation was guessed or silently discarded." in APP
    assert "no meeting title, transcript, note, evidence, audio, or private content" in APP


def test_request_only_recovery_hides_target_from_every_current_view():
    assert "state.unavailableMeetingIds.includes(meeting.id)" in APP
    assert "state.tombstonedMeetingIds.includes(meeting.id)" in APP
    assert 'return meetings.filter((meeting) => !meetingIsUnavailable(meeting));' in APP
    assert 'return activeMeetings().flatMap' in APP
    assert 'for (const meeting of activeMeetings())' in APP
    assert 'return [...activeMeetings()].sort' in APP
    assert 'const held = activeMeetings().filter' in APP
    assert "The affected meeting is unavailable in Find, Meetings, and Promises" in APP


def test_resume_is_idempotent_and_clears_only_after_terminal_completion():
    assert 'state.recoveryMode !== "meeting-deletion"' in APP
    assert 'state.meetingDeletionRecoveryState = "resuming";' in APP
    assert "transitionTimer = window.setTimeout(() => finishMeetingDeletion(), 650);" in APP
    finish_start = APP.index("function finishMeetingDeletion()")
    finish_end = APP.index("function confirmMeetingDeletion()", finish_start)
    finish_body = APP[finish_start:finish_end]
    assert "trustState.completeMeetingDeletion" in finish_body
    assert "writeSessionStateEnvelope(tombstoned)" in finish_body
    assert 'state.meetingDeletionRecoveryState = "completed";' in finish_body
    assert "if (!clearMeetingDeletionRecoveryReceipt())" in finish_body
    assert "a second reload\nreconstructs the same recovery surface" in README


def test_manifest_records_pending_scope_and_non_approvals():
    slice_ = MANIFEST["wholeMeetingDeletionSlice"]
    assert slice_["status"] == "pending-operator-review"
    assert slice_["source"] == "synthetic"
    assert slice_["terminalScope"]["removed"] == [
        "meeting metadata",
        "canonical transcript and revisions",
        "notes and stale history",
        "evidence links",
        "retained audio if any",
    ]
    assert slice_["terminalScope"]["remains"] == [
        "separate voice profile",
        "retention policy",
        "other meetings",
    ]
    assert "native deletion implementation" in slice_["doesNotApprove"]
    assert "beta admission or release" in slice_["doesNotApprove"]


def test_manifest_binds_the_current_prototype_files():
    for name, digest in MANIFEST["files"].items():
        actual = hashlib.sha256((ROOT / "prototype/walking-skeleton" / name).read_bytes()).hexdigest()
        assert digest == f"sha256:{actual}"


def test_960_by_900_uses_internal_recovery_scrolling_not_outer_page_scrolling():
    assert "overflow: hidden;" in CSS.split("body {", 1)[1].split("}", 1)[0]
    assert ".recovery-pane { min-height: 0; overflow-y: auto;" in CSS
    assert 'target.scrollIntoView({ block: "center", inline: "nearest" })' in APP


def test_capture_gap_history_survives_recovery_until_the_next_capture():
    begin = APP[APP.index("function beginCapture()") : APP.index("function cancelCapture()")]
    degraded = APP[APP.index("function previewDegradedCapture()") : APP.index("function recoverSystemAudio()")]
    recover = APP[APP.index("function recoverSystemAudio()") : APP.index("function stopCapture()")]
    stop = APP[APP.index("function stopCapture()") : APP.index("function openCapturedMeeting()")]

    assert "state.captureHadGap = false;" in begin
    assert "state.captureHadGap = true;" in degraded
    assert "state.captureDegraded = false;" in recover
    assert "captureHadGap" not in recover
    assert 'state.captureOutputMeetingId = state.captureHadGap ? "m-02" : "m-05";' in stop
    assert APP.count("state.captureHadGap = false;") == 1


def test_programmatic_h1_focus_does_not_reuse_the_keyboard_control_ring():
    assert '[tabindex]:not(h1[tabindex="-1"]):focus-visible {' in CSS
    assert 'h1[tabindex="-1"]:focus { outline: none; }' in CSS
    assert "button:focus-visible," in CSS


def test_prototype_has_no_direct_console_writes():
    assert "console." not in APP

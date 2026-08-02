"""Static contracts for the synthetic whole-meeting deletion review slice."""

import json
import hashlib
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


def test_interrupted_request_receipt_is_content_free_and_fails_closed():
    assert 'keys !== "meetingId,operationId,scenario,schema"' in APP
    assert 'receipt.schema !== "walking-skeleton-meeting-deletion/1"' in APP
    assert 'receipt.scenario !== "whole-meeting-deletion-request-only"' in APP
    assert "clearMeetingDeletionRecoveryReceipt();" in APP
    assert "One recovery operation at a time. A mixed or unknown state is not resumed." in APP
    assert "no meeting title, transcript, note, evidence, audio, or private content" in APP


def test_request_only_recovery_hides_target_from_every_current_view():
    assert 'meetingDeletionId: recoveringMeetingDeletion ? "m-05" : null' in APP
    assert 'return meetings.filter((meeting) => !meetingIsUnavailable(meeting));' in APP
    assert 'return activeMeetings().flatMap' in APP
    assert 'for (const meeting of activeMeetings())' in APP
    assert 'return [...activeMeetings()].sort' in APP
    assert 'const held = activeMeetings().filter' in APP
    assert "The affected meeting is unavailable in Find, Meetings, and Promises" in APP


def test_resume_is_idempotent_and_clears_only_after_terminal_completion():
    assert 'if (state.meetingDeletionRecoveryState !== "interrupted") return;' in APP
    assert 'state.meetingDeletionRecoveryState = "resuming";' in APP
    assert "transitionTimer = window.setTimeout(() => finishMeetingDeletion(), 650);" in APP
    finish_start = APP.index("function finishMeetingDeletion()")
    finish_end = APP.index("function confirmMeetingDeletion()", finish_start)
    finish_body = APP[finish_start:finish_end]
    assert 'state.meetingDeletionRecoveryState = "completed";' in finish_body
    assert "clearMeetingDeletionRecoveryReceipt();" in finish_body
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


def test_prototype_has_no_direct_console_writes():
    assert "console." not in APP

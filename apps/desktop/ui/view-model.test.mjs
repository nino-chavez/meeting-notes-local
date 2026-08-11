import assert from "node:assert/strict";
import test from "node:test";

import {
  canOpenStart,
  canStartMeeting,
  captureActivity,
  captureActivityElapsedSeconds,
  captureIsInProgress,
  capturePresentation,
  humanize,
  mergePermissions,
  permissionSummary,
  retentionLabel,
  shouldPollSnapshot,
  transcriptPlainText,
  transcriptionWorkerHeartbeatAgeSeconds,
} from "./view-model.mjs";

test("capture states lead with the actual next condition", () => {
  assert.equal(capturePresentation({ capture: "recording" }).title, "Stay in the conversation.");
  const transcriptReady = capturePresentation({ capture: "transcript-ready" });
  assert.equal(transcriptReady.tone, "complete");
  assert.match(transcriptReady.detail, /already saved on this Mac/);
  assert.equal(capturePresentation({ capture: "not-a-state" }).tone, "attention");
  assert.equal(captureIsInProgress({ capture: "transcribing" }), true);
  assert.equal(captureIsInProgress({ capture: "transcript-ready" }), false);
});

test("activity reports a real phase duration without inventing progress", () => {
  const snapshot = {
    capture: "transcribing",
    capture_state_started_at_epoch_seconds: 100,
    transcription_last_worker_heartbeat_at_epoch_seconds: 160,
  };
  assert.equal(captureActivity(snapshot).label, "Transcribing locally");
  assert.equal(captureActivityElapsedSeconds(snapshot, 163), 63);
  assert.equal(transcriptionWorkerHeartbeatAgeSeconds(snapshot, 163), 3);
  assert.equal(captureActivityElapsedSeconds({ capture: "transcript-ready" }, 163), null);
  assert.equal(transcriptionWorkerHeartbeatAgeSeconds({ capture: "recording" }, 163), null);
});

test("recording starts only from the actual ready-and-idle state", () => {
  assert.equal(canStartMeeting({ startup: "ready", capture: "idle" }), true);
  assert.equal(canStartMeeting({ startup: "checking", capture: "idle" }), false);
  assert.equal(canStartMeeting({ startup: "ready", capture: "recording" }), false);
});

test("the recording sheet waits for both audio sources", () => {
  const ready = { startup: "ready", capture: "idle" };
  assert.equal(canOpenStart(ready, { microphone: "authorized", systemAudio: "authorized" }), true);
  assert.equal(canOpenStart(ready, { microphone: "authorized", systemAudio: "unmeasured" }), false);
  assert.equal(canOpenStart({ startup: "checking", capture: "idle" }, { microphone: "authorized", systemAudio: "authorized" }), false);
});

test("permission checks retain an initial unmeasured system-audio state", () => {
  const firstCheck = mergePermissions(null, { microphone: "not-determined", systemAudio: "unmeasured" });
  assert.equal(firstCheck.systemAudio, "unmeasured");
  const microphoneApproved = mergePermissions(firstCheck, { microphone: "authorized", systemAudio: "unmeasured" });
  assert.equal(microphoneApproved.microphone, "authorized");
  assert.equal(microphoneApproved.systemAudio, "unmeasured");
  const audioApproved = mergePermissions(microphoneApproved, { microphone: "unmeasured", systemAudio: "authorized" });
  assert.equal(audioApproved.microphone, "authorized");
  assert.equal(audioApproved.systemAudio, "authorized");
});

test("audio setup does not confuse unknown with permission denied", () => {
  assert.equal(permissionSummary(null).state, "checking");
  assert.equal(permissionSummary({ probeUnavailable: true }).title, "Audio access could not be checked");
  assert.equal(permissionSummary({ microphone: "denied", systemAudio: "unmeasured" }).title, "Microphone access is needed");
  assert.equal(permissionSummary({ microphone: "authorized", systemAudio: "unmeasured" }).title, "Allow system audio");
  assert.equal(permissionSummary({ microphone: "authorized", systemAudio: "authorized" }).state, "ready");
});

test("small display helpers stay readable", () => {
  assert.equal(retentionLabel(1), "1 day");
  assert.equal(retentionLabel(7), "7 days");
  assert.equal(humanize("evidence_state"), "Evidence State");
});

test("a copied transcript keeps known gaps visible", () => {
  const copied = transcriptPlainText([
    { start: 0, speaker: "Me", text: "we agreed to defer the migration" },
    { start: 63, withheld: true },
    { start: 125, speaker: "Them", text: "  send the numbers Friday  " },
    { start: 130, speaker: "Them", text: "   " },
    { start: 140, text: "no speaker recorded" },
  ]);
  assert.deepEqual(copied.split("\n"), [
    "[00:00] Me: we agreed to defer the migration",
    "[01:03] (withheld — a voice check set this turn aside)",
    "[02:05] Them: send the numbers Friday",
    "[02:20] Unattributed: no speaker recorded",
  ]);
  assert.equal(transcriptPlainText([]), "");
  assert.equal(transcriptPlainText(null), "");
});

test("startup keeps polling until the app is ready", () => {
  assert.equal(shouldPollSnapshot({ startup: "checking", capture: "idle" }), true);
  assert.equal(shouldPollSnapshot({ startup: "ready", capture: "idle" }), false);
  assert.equal(shouldPollSnapshot({ startup: "ready", capture: "recording" }), true);
});

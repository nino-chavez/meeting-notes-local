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
  meetingRecoveryPresentation,
  meetingNotePresentation,
  mergePermissions,
  noteGenerationPresentation,
  permissionSummary,
  retentionLabel,
  shouldPollSnapshot,
  transcriptPlainText,
  transcriptSpeakerLabel,
  transcriptTurnsForSourceSpeaker,
  transcriptTurnsMatching,
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

test("a point-only artifact is not presented as a meeting summary", () => {
  const point = { ordinal: 0, claimType: "point", claim: "A selected excerpt." };
  assert.deepEqual(meetingNotePresentation({ claims: [point] }), {
    state: "extracts-only",
    summary: [],
    groups: [],
    highlights: [point],
  });
});

test("a generated meeting note leads with summary and outcome groups", () => {
  const decision = { ordinal: 0, claimType: "decision", claim: "Use the smaller battery." };
  const action = { ordinal: 1, claimType: "action", claim: "Send the cost table." };
  const presentation = meetingNotePresentation({
    claims: [
      { ordinal: 0, claimType: "summary", claim: "The group chose the smaller battery and assigned the cost follow-up." },
      decision,
      action,
    ],
  });
  assert.equal(presentation.state, "note");
  assert.deepEqual(presentation.summary, [
    { ordinal: 0, claimType: "summary", claim: "The group chose the smaller battery and assigned the cost follow-up." },
  ]);
  assert.deepEqual(presentation.groups.map((group) => group.title), ["Decisions", "Follow-ups"]);
  assert.deepEqual(presentation.highlights, []);
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

test("the rendered transcript names known and missing attribution without guessing", () => {
  assert.equal(transcriptSpeakerLabel({ speaker: "Me" }), "Me");
  assert.equal(transcriptSpeakerLabel({ speaker: "  Them  " }), "Them");
  assert.equal(transcriptSpeakerLabel({ speaker: "Facilitator" }), "Facilitator");
  assert.equal(transcriptSpeakerLabel({}), "Unattributed");
  assert.equal(transcriptSpeakerLabel({ speaker: "   " }), "Unattributed");
  assert.equal(transcriptSpeakerLabel({ speaker: "Me", withheld: true }), null);
});

test("speaker correction targets only the matching retained source group", () => {
  const turns = [
    { sourceSpeaker: "Me", speaker: "Me" },
    { sourceSpeaker: "Them", speaker: "Alex", speakerCorrected: true },
    { sourceSpeaker: "Them", speaker: "Alex", speakerCorrected: true },
    { sourceSpeaker: null, speaker: null },
    { sourceSpeaker: "Them", speaker: null, withheld: true },
  ];
  assert.equal(transcriptTurnsForSourceSpeaker(turns, "Them").length, 2);
  assert.equal(transcriptTurnsForSourceSpeaker(turns, null).length, 1);
  assert.equal(transcriptTurnsForSourceSpeaker(turns, "Me").length, 1);
});

test("transcript search only matches retained text", () => {
  const turns = [
    { text: "Decide the release date" },
    { text: "This turn cannot be searched", withheld: true },
    { text: "Send the release recap" },
  ];
  assert.deepEqual(transcriptTurnsMatching(turns, "RELEASE"), [turns[0], turns[2]]);
  assert.deepEqual(transcriptTurnsMatching(turns, ""), turns);
  assert.deepEqual(transcriptTurnsMatching(null, "release"), []);
});

test("startup keeps polling until the app is ready", () => {
  assert.equal(shouldPollSnapshot({ startup: "checking", capture: "idle" }), true);
  assert.equal(shouldPollSnapshot({ startup: "ready", capture: "idle" }), false);
  assert.equal(shouldPollSnapshot({ startup: "ready", capture: "recording" }), true);
});

test("the generate control follows the backend's eligibility signal alone", () => {
  const eligible = { meetingId: "m-1", regenerationSourceSha256: "a".repeat(64) };
  const idle = noteGenerationPresentation(eligible, "");
  assert.equal(idle.action, "generate-note");
  assert.equal(idle.disabled, false);
  assert.equal(idle.label, "Generate note");
  assert.match(idle.help, /on this Mac/);
  assert.match(idle.help, /minutes/);

  const busy = noteGenerationPresentation(eligible, "m-1");
  assert.equal(busy.disabled, true);
  assert.equal(busy.label, "Generating note…");
  assert.match(busy.help, /keep using Yawn/);

  // Another meeting generating does not disable this one's control.
  assert.equal(noteGenerationPresentation(eligible, "m-2").disabled, false);

  const replacement = noteGenerationPresentation({ ...eligible, claims: [{ ordinal: 0 }] }, "");
  assert.equal(replacement.label, "Regenerate note");
  assert.match(replacement.help, /current note stays in place/);

  // No source pin — a ready note, a stale view, a deleted transcript — no control.
  assert.equal(noteGenerationPresentation({ meetingId: "m-1" }, ""), null);
  assert.equal(noteGenerationPresentation({ regenerationSourceSha256: "x" }, ""), null);
  assert.equal(noteGenerationPresentation(null, ""), null);
});

test("summary failure keeps the transcript and offers regeneration when its source is pinned", () => {
  const recovery = meetingRecoveryPresentation({
    state: "summary-failed",
    meetingId: "m-1",
    regenerationSourceSha256: "a".repeat(64),
    claims: [],
  }, { state: "transcript", turns: [{ text: "kept" }] });
  assert.equal(recovery.state, "summary-failed");
  assert.equal(recovery.action.action, "generate-note");
  assert.equal(recovery.action.label, "Regenerate note");
  assert.match(recovery.detail, /transcript/);
  assert.match(recovery.detail, /remain unchanged/);
});

test("summary failure without a source explains that retry is unavailable", () => {
  const recovery = meetingRecoveryPresentation({
    state: "summary-failed",
    meetingId: "m-1",
    claims: [],
  });
  assert.equal(recovery.state, "summary-failed-no-source");
  assert.equal(recovery.action, null);
  assert.match(recovery.detail, /cannot retry/);
  assert.match(recovery.detail, /stays unchanged/);
});

test("active generation says what remains without offering a second retry", () => {
  const recovery = meetingRecoveryPresentation({
    state: "summary-failed",
    meetingId: "m-1",
    regenerationSourceSha256: "a".repeat(64),
    claims: [{ claimType: "summary", claim: "The current note." }],
  }, { state: "transcript" }, "m-1");
  assert.equal(recovery.state, "generating");
  assert.equal(recovery.action, null);
  assert.match(recovery.detail, /current note stays in place/);
});

test("stale transcript routes back to meetings instead of inventing a transcript retry", () => {
  const recovery = meetingRecoveryPresentation(
    { state: "transcript-only", meetingId: "m-1" },
    { state: "stale", turns: [], message: "That transcript is no longer available." },
  );
  assert.equal(recovery.state, "transcript-unavailable");
  assert.deepEqual(recovery.action, { action: "meetings", label: "Back to meetings" });
  assert.match(recovery.detail, /stay unchanged/);
});

test("released audio says retranscription is unavailable while preserving the note and transcript", () => {
  const recovery = meetingRecoveryPresentation({
    state: "transcript-only",
    meetingId: "m-1",
    audioRetention: { state: "released" },
  }, { state: "transcript", turns: [{ text: "kept" }] });
  assert.equal(recovery.state, "audio-released");
  assert.equal(recovery.action, null);
  assert.match(recovery.detail, /cannot be retranscribed/);
  assert.match(recovery.detail, /remain available/);
});

test("released audio remains visible even when a usable note is present", () => {
  const recovery = meetingRecoveryPresentation({
    state: "ready",
    meetingId: "m-1",
    claims: [{ claimType: "summary", claim: "The current note." }],
    audioRetention: { state: "released" },
  }, { state: "transcript", turns: [{ text: "kept" }] });
  assert.equal(recovery.state, "audio-released");
  assert.equal(recovery.action, null);
});

test("speaker corrections no longer create a recovery block before note generation", () => {
  const recovery = meetingRecoveryPresentation({
    state: "ready",
    meetingId: "m-1",
    regenerationSourceSha256: "a".repeat(64),
    claims: [{ claimType: "summary", claim: "The current note." }],
  }, { state: "transcript", turns: [{ speakerCorrected: true }] });
  assert.equal(recovery, null);
});

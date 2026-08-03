"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const trust = require("../prototype/walking-skeleton/trust-state.js");

const deletionReceipt = JSON.stringify({
  schema: "walking-skeleton-meeting-deletion/1",
  scenario: "whole-meeting-deletion-request-only",
  meetingId: "m-05",
  operationId: "synthetic-delete-m05-v1"
});

const regenerationReceipt = JSON.stringify({
  schema: "walking-skeleton-recovery/1",
  scenario: "note-regeneration-request-only",
  meetingId: "m-02",
  transcriptView: 2,
  priorNoteVersion: 1
});

function serializedSession(change = {}) {
  return JSON.stringify({ ...trust.defaultSessionState(), ...change });
}

test("a first synthetic session starts with no unavailable meetings", () => {
  const context = trust.resolvePersistentContext({ session: null, regeneration: null, meetingDeletion: null });
  assert.equal(context.mode, "normal");
  assert.deepEqual(context.unavailableMeetingIds, []);
});

test("Reset and default switching retain a pending deletion and route to recovery", () => {
  const reset = trust.guardReviewerNavigation("meeting-deletion", "retrieval", "retrieval");
  const switchDefault = trust.guardReviewerNavigation("meeting-deletion", "retrieval", "meetings");
  assert.deepEqual(reset, { route: "meeting-deletion-recovery", defaultDirection: "retrieval", retained: true });
  assert.deepEqual(switchDefault, reset);
});

test("unknown deletion receipt fields fail closed without making the target current", () => {
  const malformed = JSON.stringify({
    schema: "walking-skeleton-meeting-deletion/1",
    scenario: "whole-meeting-deletion-request-only",
    meetingId: "m-05",
    operationId: "synthetic-delete-m05-v1",
    unknown: true
  });
  const context = trust.resolvePersistentContext({
    session: serializedSession(),
    regeneration: null,
    meetingDeletion: malformed
  });
  assert.equal(context.mode, "blocked");
  assert.deepEqual(context.unavailableMeetingIds, ["m-05"]);
  assert.equal(context.quarantinedEvidence.find((item) => item.key === trust.storageKeys.meetingDeletion).status, "invalid");
});

test("mixed valid receipts fail closed and quarantine both affected operations", () => {
  const context = trust.resolvePersistentContext({
    session: serializedSession(),
    regeneration: regenerationReceipt,
    meetingDeletion: deletionReceipt
  });
  assert.equal(context.mode, "blocked");
  assert.deepEqual(context.unavailableMeetingIds, ["m-02", "m-05"]);
  assert.deepEqual(context.quarantinedEvidence.map((item) => item.status), ["valid", "valid", "valid"]);
  assert.equal(trust.guardReviewerNavigation(context.mode, "retrieval", "meetings").route, "recovery-error");
});

test("interrupted deletion preserves unrelated settings and released-audio state", () => {
  const original = trust.defaultSessionState();
  original.setupPermissions = { microphone: false, systemAudio: true };
  original.retentionPeriodDays = 30;
  original.voiceProfileStatus = "missing";
  original.releasedAudioMeetingIds = ["m-04"];
  original.correction = { restored: true, regenerated: true };
  const context = trust.resolvePersistentContext({
    session: JSON.stringify(original),
    regeneration: null,
    meetingDeletion: deletionReceipt
  });
  assert.equal(context.mode, "meeting-deletion");
  assert.deepEqual(context.session, original);
  assert.deepEqual(context.unavailableMeetingIds, ["m-05"]);
});

test("terminal completion is idempotent and persists a tombstone across plain reload", () => {
  const original = trust.defaultSessionState();
  const completedOnce = trust.completeMeetingDeletion(original);
  const completedTwice = trust.completeMeetingDeletion(completedOnce);
  assert.deepEqual(completedTwice, completedOnce);
  const afterReload = trust.resolvePersistentContext({
    session: JSON.stringify(completedTwice),
    regeneration: null,
    meetingDeletion: null
  });
  assert.equal(afterReload.mode, "normal");
  assert.deepEqual(afterReload.unavailableMeetingIds, ["m-05"]);
  assert.deepEqual(afterReload.session.tombstonedMeetingIds, ["m-05"]);
});

test("invalid session envelopes fail closed instead of losing a possible tombstone", () => {
  const invalid = JSON.stringify({ ...trust.defaultSessionState(), unexpected: "field" });
  const context = trust.resolvePersistentContext({
    session: invalid,
    regeneration: null,
    meetingDeletion: null
  });
  assert.equal(context.mode, "blocked");
  assert.deepEqual(context.unavailableMeetingIds, ["m-05"]);
});

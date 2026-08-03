"use strict";

(function exposeTrustState(root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.WalkingSkeletonTrustState = api;
})(typeof globalThis === "object" ? globalThis : this, function createTrustState() {
  const storageKeys = Object.freeze({
    session: "local-meeting-notes:walking-skeleton-session-state",
    regeneration: "local-meeting-notes:walking-skeleton-recovery",
    meetingDeletion: "local-meeting-notes:walking-skeleton-meeting-deletion-recovery"
  });

  const sessionSchema = "walking-skeleton-session-state/1";
  const deletionSchema = "walking-skeleton-meeting-deletion/1";
  const regenerationSchema = "walking-skeleton-recovery/1";

  function defaultSessionState() {
    return {
      schema: sessionSchema,
      setupPermissions: { microphone: true, systemAudio: true },
      retentionPeriodDays: 14,
      voiceProfileStatus: "valid",
      releasedAudioMeetingIds: [],
      correction: { restored: false, regenerated: false },
      tombstonedMeetingIds: []
    };
  }

  function clone(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function hasExactKeys(value, expected) {
    if (!value || typeof value !== "object" || Array.isArray(value)) return false;
    return Object.keys(value).sort().join(",") === [...expected].sort().join(",");
  }

  function isUniqueSubset(value, allowed) {
    return Array.isArray(value)
      && value.every((item) => allowed.includes(item))
      && new Set(value).size === value.length;
  }

  function validateSessionState(value) {
    if (!hasExactKeys(value, [
      "schema",
      "setupPermissions",
      "retentionPeriodDays",
      "voiceProfileStatus",
      "releasedAudioMeetingIds",
      "correction",
      "tombstonedMeetingIds"
    ])) return false;
    if (value.schema !== sessionSchema) return false;
    if (!hasExactKeys(value.setupPermissions, ["microphone", "systemAudio"])) return false;
    if (typeof value.setupPermissions.microphone !== "boolean" || typeof value.setupPermissions.systemAudio !== "boolean") return false;
    if (value.retentionPeriodDays !== null && ![1, 7, 14, 30].includes(value.retentionPeriodDays)) return false;
    if (!["valid", "missing"].includes(value.voiceProfileStatus)) return false;
    if (!isUniqueSubset(value.releasedAudioMeetingIds, ["m-04"])) return false;
    if (!hasExactKeys(value.correction, ["restored", "regenerated"])) return false;
    if (typeof value.correction.restored !== "boolean" || typeof value.correction.regenerated !== "boolean") return false;
    if (value.correction.regenerated && !value.correction.restored) return false;
    return isUniqueSubset(value.tombstonedMeetingIds, ["m-05"]);
  }

  function validateDeletionReceipt(value) {
    return hasExactKeys(value, ["schema", "scenario", "meetingId", "operationId"])
      && value.schema === deletionSchema
      && value.scenario === "whole-meeting-deletion-request-only"
      && value.meetingId === "m-05"
      && value.operationId === "synthetic-delete-m05-v1";
  }

  function validateRegenerationReceipt(value) {
    return hasExactKeys(value, ["schema", "scenario", "meetingId", "transcriptView", "priorNoteVersion"])
      && value.schema === regenerationSchema
      && value.scenario === "note-regeneration-request-only"
      && value.meetingId === "m-02"
      && value.transcriptView === 2
      && value.priorNoteVersion === 1;
  }

  function inspectRaw(raw, validator) {
    if (raw === null || raw === undefined) return { status: "absent", value: null };
    try {
      const value = JSON.parse(raw);
      return validator(value) ? { status: "valid", value } : { status: "invalid", value: null };
    } catch {
      return { status: "invalid", value: null };
    }
  }

  function resolvePersistentContext(raw) {
    const session = inspectRaw(raw.session, validateSessionState);
    const regeneration = inspectRaw(raw.regeneration, validateRegenerationReceipt);
    const meetingDeletion = inspectRaw(raw.meetingDeletion, validateDeletionReceipt);
    const unavailable = new Set(session.status === "valid"
      ? session.value.tombstonedMeetingIds
      : session.status === "invalid"
        ? ["m-05"]
        : []);
    const issues = [];

    if (session.status === "invalid") issues.push("synthetic session state is unreadable or has unknown fields");
    if (regeneration.status === "invalid") {
      issues.push("note-regeneration receipt is unreadable or has unknown fields");
      unavailable.add("m-02");
    }
    if (meetingDeletion.status !== "absent") unavailable.add("m-05");
    if (meetingDeletion.status === "invalid") issues.push("whole-meeting deletion receipt is unreadable or has unknown fields");
    if (regeneration.status !== "absent" && meetingDeletion.status !== "absent") {
      issues.push("two recovery receipts are present at the same time");
      unavailable.add("m-02");
      unavailable.add("m-05");
    }

    const mode = issues.length
      ? "blocked"
      : meetingDeletion.status === "valid"
        ? "meeting-deletion"
        : regeneration.status === "valid"
          ? "regeneration"
          : "normal";

    return {
      mode,
      issues,
      session: session.status === "valid" ? clone(session.value) : defaultSessionState(),
      sessionWasAbsent: session.status === "absent",
      regenerationReceipt: regeneration.value,
      meetingDeletionReceipt: meetingDeletion.value,
      unavailableMeetingIds: [...unavailable].sort(),
      quarantinedEvidence: [
        [storageKeys.session, session.status],
        [storageKeys.regeneration, regeneration.status],
        [storageKeys.meetingDeletion, meetingDeletion.status]
      ].filter(([, status]) => status !== "absent").map(([key, status]) => ({ key, status }))
    };
  }

  function guardReviewerNavigation(mode, currentDefault, requestedDefault = currentDefault) {
    if (mode === "blocked") return { route: "recovery-error", defaultDirection: currentDefault, retained: true };
    if (mode === "meeting-deletion") return { route: "meeting-deletion-recovery", defaultDirection: currentDefault, retained: true };
    if (mode === "regeneration") return { route: "meeting", defaultDirection: currentDefault, retained: true };
    return { route: "home", defaultDirection: requestedDefault, retained: false };
  }

  function completeMeetingDeletion(session, meetingId = "m-05") {
    if (!validateSessionState(session) || meetingId !== "m-05") throw new Error("Invalid synthetic deletion transition");
    const next = clone(session);
    if (!next.tombstonedMeetingIds.includes(meetingId)) next.tombstonedMeetingIds.push(meetingId);
    next.tombstonedMeetingIds.sort();
    return next;
  }

  return Object.freeze({
    storageKeys,
    defaultSessionState,
    validateSessionState,
    validateDeletionReceipt,
    validateRegenerationReceipt,
    resolvePersistentContext,
    guardReviewerNavigation,
    completeMeetingDeletion
  });
});

import assert from "node:assert/strict";
import test from "node:test";

import {
  createTransitionGate,
  createSingleFlight,
  displayedClaimIdentity,
  normalizedScrollPosition,
  prepareConsentTransition,
  refreshFindGeneration,
  retentionDeadlineMessage,
  restoredScrollPosition,
  rowForMeetingId,
  rootForDestination,
  mutableActionPolicy,
  meetingDetailPresentation,
  resolvedScreenForSnapshot,
  sameDisplayedClaim,
  transitionOwnsRoute,
  transcriptReturnRoute,
  workflowScreenForSnapshot,
} from "./navigation-state.mjs";

test("workflow routes advance only while they own the screen", () => {
  const recording = { startup: "ready", capture: "recording" };
  const ready = { startup: "ready", capture: "transcript-ready" };

  assert.equal(workflowScreenForSnapshot(recording), "recording-screen");
  assert.equal(workflowScreenForSnapshot(ready), "transcript-screen");
  assert.equal(resolvedScreenForSnapshot(recording, "meetings-screen", false), "meetings-screen");
  assert.equal(resolvedScreenForSnapshot(ready, "profile-screen", false), "profile-screen");
  assert.equal(resolvedScreenForSnapshot(recording, "find-screen", true), "recording-screen");
  assert.equal(workflowScreenForSnapshot({ startup: "checking", capture: "idle" }), "startup-screen");
});

test("mutable actions match the admitted capture and startup states", () => {
  const recording = mutableActionPolicy({ preview: true, startup: "ready", capture: "recording" });
  assert.equal(recording.showProductNavigation, true);
  assert.equal(recording.canStartMeeting, false);
  assert.equal(recording.canSubmitStart, false);
  assert.equal(recording.showStop, true);
  assert.equal(recording.stopDisabled, false);

  const pending = mutableActionPolicy(
    { preview: true, startup: "ready", capture: "recording" },
    { stopPending: true },
  );
  assert.equal(pending.stopDisabled, true);
  assert.equal(pending.stopLabel, "Stopping…");

  const stopping = mutableActionPolicy({ preview: true, startup: "ready", capture: "stopping" });
  assert.equal(stopping.showStop, true);
  assert.equal(stopping.stopDisabled, true);
  assert.equal(stopping.stopLabel, "Stopping…");

  const processing = mutableActionPolicy({ preview: true, startup: "ready", capture: "transcribing" });
  assert.equal(processing.showStop, false);
  assert.equal(processing.canDismissMeeting, false);

  const transcript = mutableActionPolicy({ preview: true, startup: "ready", capture: "transcript-ready" });
  assert.equal(transcript.canStartMeeting, true);
  assert.equal(transcript.canDismissMeeting, true);

  const idle = mutableActionPolicy({ preview: true, startup: "ready", capture: "idle" });
  assert.equal(idle.canSubmitStart, true);
  assert.equal(idle.canDismissMeeting, false);

  const recovered = mutableActionPolicy({ preview: true, startup: "ready", capture: "recovered-interrupted" });
  assert.equal(recovered.canDismissMeeting, true);

  const failure = mutableActionPolicy({ preview: true, startup: "service-timeout", capture: "idle" });
  assert.equal(failure.canRetryStartup, true);
  assert.equal(failure.showProductNavigation, true);
  assert.equal(
    mutableActionPolicy({ preview: true, startup: "runtime-missing", capture: "idle" }).canRetryStartup,
    false,
  );
});

test("retention copy says when audio becomes due and when deletion can run", () => {
  const copy = retentionDeadlineMessage(1_728_000_060);

  assert.match(copy, /^Audio becomes due for deletion on .+\. Deletion runs while the app is open, or the next time it opens\.$/);
  assert.doesNotMatch(copy, /Scheduled to delete/);
});

test("retention copy does not invent a deletion time for invalid deadlines", () => {
  assert.equal(
    retentionDeadlineMessage("not-a-deadline"),
    "The audio deletion time is unavailable. This Preview cannot show when the audio becomes due.",
  );
  assert.equal(
    retentionDeadlineMessage(0),
    "The audio deletion time is unavailable. This Preview cannot show when the audio becomes due.",
  );
});

test("single-flight initialization deduplicates only an in-flight snapshot", async () => {
  let loads = 0;
  let release;
  const initializer = createSingleFlight(() => {
    loads += 1;
    return new Promise((resolve) => { release = resolve; });
  });

  const first = initializer.run();
  const second = initializer.run();
  await Promise.resolve();
  assert.equal(first, second);
  assert.equal(loads, 1);
  release({ state: "populated" });
  assert.deepEqual(await first, { state: "populated" });

  const third = initializer.run();
  await Promise.resolve();
  assert.equal(loads, 2);
  release({ state: "empty" });
  assert.deepEqual(await third, { state: "empty" });
});

test("overlapping Find refreshes share one generation and a later refresh is fresh", async () => {
  const events = [];
  const renderedHandles = [];
  const releaseSnapshots = [];
  let responseGeneration = 0;
  const actions = {
    invalidateResults: () => { events.push("invalidate"); },
    snapshot: () => {
      responseGeneration += 1;
      events.push(`snapshot:${responseGeneration}`);
      return new Promise((resolve) => { releaseSnapshots.push(resolve); });
    },
    search: async (query) => {
      responseGeneration += 1;
      events.push(`search:${query}:${responseGeneration}`);
      return { handle: `search-handle-${responseGeneration}` };
    },
    render: (response) => {
      events.push(`render:${response.handle}`);
      renderedHandles.push(response.handle);
    },
  };
  const refresh = createSingleFlight(
    () => refreshFindGeneration("first", actions),
  );

  const first = refresh.run();
  await Promise.resolve();
  const overlapping = refresh.run();
  assert.equal(first, overlapping);
  assert.deepEqual(events, ["invalidate", "snapshot:1"]);

  releaseSnapshots.shift()();
  await Promise.all([first, overlapping]);
  assert.deepEqual(events, [
    "invalidate", "snapshot:1", "search:first:2", "render:search-handle-2",
  ]);

  const later = refresh.run();
  await Promise.resolve();
  assert.notEqual(later, first);
  assert.deepEqual(events, [
    "invalidate", "snapshot:1", "search:first:2", "render:search-handle-2",
    "invalidate", "snapshot:3",
  ]);
  releaseSnapshots.shift()();
  await later;
  assert.deepEqual(events, [
    "invalidate", "snapshot:1", "search:first:2", "render:search-handle-2",
    "invalidate", "snapshot:3", "search:first:4", "render:search-handle-4",
  ]);
  assert.deepEqual(renderedHandles, ["search-handle-2", "search-handle-4"]);
  assert.notEqual(renderedHandles[0], renderedHandles[1]);
});

test("cold empty Find snapshots once without creating result handles", async () => {
  const events = [];
  await refreshFindGeneration("", {
    invalidateResults: () => { events.push("invalidate"); },
    snapshot: async () => { events.push("snapshot"); },
    search: async () => { events.push("search"); },
    render: () => { events.push("render"); },
  });
  assert.deepEqual(events, ["invalidate", "snapshot"]);
});

test("failed Find refresh leaves invalidated results unrendered", async () => {
  const events = [];
  await assert.rejects(refreshFindGeneration("words", {
    invalidateResults: () => { events.push("invalidate"); },
    snapshot: async () => {
      events.push("snapshot");
      throw new Error("snapshot failed");
    },
    search: async () => { events.push("search"); },
    render: () => { events.push("render"); },
  }), /snapshot failed/);
  assert.deepEqual(events, ["invalidate", "snapshot"]);
});

test("transcript-ready start dismisses and clears before requiring idle", async () => {
  const events = [];
  const ready = await prepareConsentTransition("transcript-ready", {
    dismiss: async () => { events.push("dismiss"); },
    clearPriorAttempt: () => { events.push("clear"); },
    refresh: async () => {
      events.push("refresh");
      return { capture: "idle" };
    },
  });

  assert.equal(ready, true);
  assert.deepEqual(events, ["dismiss", "clear", "refresh"]);
});

test("failed dismissal never clears state, refreshes, or admits consent", async () => {
  const events = [];
  await assert.rejects(
    prepareConsentTransition("transcript-ready", {
      dismiss: async () => {
        events.push("dismiss");
        throw new Error("dismiss failed");
      },
      clearPriorAttempt: () => { events.push("clear"); },
      refresh: async () => {
        events.push("refresh");
        return { capture: "idle" };
      },
    }),
    /dismiss failed/,
  );
  assert.deepEqual(events, ["dismiss"]);
});

test("idle start is direct and other capture states refuse consent", async () => {
  const actions = {
    dismiss: async () => { throw new Error("unexpected dismissal"); },
    clearPriorAttempt: () => { throw new Error("unexpected clear"); },
    refresh: async () => { throw new Error("unexpected refresh"); },
  };
  assert.equal(await prepareConsentTransition("idle", actions), true);
  assert.equal(await prepareConsentTransition("recording", actions), false);
});

test("nested routes keep their real product root", () => {
  assert.equal(rootForDestination("find-screen", "meetings-screen"), "find-screen");
  assert.equal(rootForDestination("meeting-detail-screen", "meetings-screen"), "meetings-screen");
  assert.equal(rootForDestination("library-transcript-screen", "find-screen"), "find-screen");
  assert.equal(rootForDestination("profile-screen", "promises-screen"), "promises-screen");
  assert.equal(rootForDestination("profile-screen", "unknown"), "find-screen");
});

test("returning restores scroll while new content starts at the top", () => {
  assert.equal(restoredScrollPosition(undefined), 0);
  assert.equal(restoredScrollPosition(184), 184);
  assert.equal(restoredScrollPosition(184, true), 0);
});

test("a fresh snapshot looks up a meeting by durable id, not an old handle", () => {
  const first = { rows: [{ meetingId: "meeting-a", handle: "old-handle" }] };
  const fresh = { rows: [{ meetingId: "meeting-a", handle: "fresh-handle" }] };

  assert.equal(rowForMeetingId(first, "meeting-a")?.handle, "old-handle");
  assert.equal(rowForMeetingId(fresh, "meeting-a")?.handle, "fresh-handle");
  assert.equal(rowForMeetingId(fresh, "missing"), null);
  assert.equal(rowForMeetingId({ rows: null }, "meeting-a"), null);
});

test("evidence opened from a meeting detail carries normalized scroll and a full claim identity", () => {
  const claim = { ordinal: 4, claimType: "action", claim: "Follow up with the customer." };
  assert.deepEqual(
    transcriptReturnRoute("meeting-detail", "meeting-a", { claim, detailScrollTop: 184.5 }),
    {
      destination: "meeting-detail",
      meetingId: "meeting-a",
      claim,
      detailScrollTop: 184.5,
    },
  );
  assert.deepEqual(
    transcriptReturnRoute("find", "meeting-a", { claim, detailScrollTop: 184 }),
    { destination: "product-root", meetingId: null, claim: null, detailScrollTop: 0 },
  );
  assert.deepEqual(
    transcriptReturnRoute("meeting-detail", "", { claim, detailScrollTop: 184 }),
    { destination: "product-root", meetingId: null, claim: null, detailScrollTop: 0 },
  );
  assert.equal(normalizedScrollPosition(-1), 0);
  assert.equal(normalizedScrollPosition(Number.NaN), 0);
  assert.equal(normalizedScrollPosition(51.25), 51.25);
});

test("rebuilt claim focus requires the exact displayed identity", () => {
  const original = { ordinal: 4, claimType: "action", claim: "Follow up with the customer." };
  assert.deepEqual(displayedClaimIdentity(original), original);
  assert.equal(sameDisplayedClaim(original, { ...original }), true);
  assert.equal(sameDisplayedClaim(original, { ...original, claim: "Follow up later." }), false);
  assert.equal(sameDisplayedClaim(original, { ...original, claimType: "decision" }), false);
  assert.equal(sameDisplayedClaim(original, { ...original, ordinal: 5 }), false);
  assert.equal(sameDisplayedClaim(original, { ordinal: 4, claimType: "action" }), false);
});

test("a transition gate admits one response-scoped operation and releases it for the next", () => {
  const gate = createTransitionGate();
  const route = { screen: "meeting-detail-screen", revision: 2 };
  const first = gate.enter("open-note", route);
  assert.ok(first);
  assert.equal(gate.enter("open-evidence", route), null);
  assert.equal(gate.owns(first), true);
  assert.equal(transitionOwnsRoute(gate, first, route), true);
  assert.equal(
    transitionOwnsRoute(gate, first, { screen: "find-screen", revision: 3 }),
    false,
  );
  assert.equal(gate.release({ ...first }), false);
  assert.equal(gate.release(first), true);
  const second = gate.enter("open-evidence", { screen: "meeting-detail-screen", revision: 3 });
  assert.ok(second);
  assert.notEqual(second.sequence, first.sequence);
});

test("metadata-only meeting detail is inspectable but never offers transcript text", () => {
  assert.deepEqual(
    meetingDetailPresentation({ state: "transcript-only", transcriptHandle: null }),
    {
      kind: "metadata-only",
      title: "Meeting details.",
      lede: "This meeting’s retained status and recording information are available. No transcript was created.",
      fallbackTitle: "No transcript was created",
      fallbackCopy: "There are no retained words or automatic note to open for this meeting.",
      canOpenTranscript: false,
    },
  );
  assert.equal(
    meetingDetailPresentation({ state: "transcript-only", transcriptHandle: "fresh-handle" }).canOpenTranscript,
    true,
  );
  assert.deepEqual(
    meetingDetailPresentation({ state: "summary-failed", transcriptHandle: null }),
    {
      kind: "transcript-unavailable",
      title: "Meeting details.",
      lede: "A transcript is not available from this retained meeting view.",
      fallbackTitle: "Transcript unavailable",
      fallbackCopy: "No retained words or automatic note can be opened right now. Reopen Meetings and try again.",
      canOpenTranscript: false,
    },
  );
  assert.deepEqual(
    meetingDetailPresentation({ state: "stale", transcriptHandle: null }),
    {
      kind: "unavailable",
      title: "Meeting unavailable.",
      lede: "This retained meeting could not be reopened. Its current transcript, note, and recording facts are unavailable in this view.",
      fallbackTitle: "Meeting unavailable",
      fallbackCopy: "Reopen Meetings and try again.",
      canOpenTranscript: false,
    },
  );
});

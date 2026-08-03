import assert from "node:assert/strict";
import test from "node:test";

import {
  createTransitionGate,
  createSingleFlight,
  acceptAuthoritativeSnapshot,
  isDismissalReadySnapshot,
  settleDismissal,
  createLatestRequestGate,
  createRouteOwnershipGate,
  displayedClaimIdentity,
  changedStatusText,
  connectionUncertaintyStatus,
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
    true,
  );
});

test("latest snapshot request wins when responses resolve out of order", () => {
  const gate = createLatestRequestGate();
  const first = gate.begin();
  const second = gate.begin();
  const applied = [];

  if (gate.isCurrent(second)) applied.push("stopping");
  if (gate.isCurrent(first)) applied.push("recording");

  assert.equal(gate.isCurrent(first), false);
  assert.equal(gate.isCurrent(second), true);
  assert.deepEqual(applied, ["stopping"]);
});

test("a superseded snapshot result is distinguishable from a fresh snapshot", () => {
  const gate = createLatestRequestGate();
  const first = gate.begin();
  const second = gate.begin();
  const firstResult = gate.isCurrent(first) ? { capture: "recording" } : null;
  const secondResult = gate.isCurrent(second) ? { capture: "stopping" } : null;

  assert.equal(firstResult, null);
  assert.deepEqual(secondResult, { capture: "stopping" });
});

test("explicit row and result routes supersede a pending Done or Recover workflow", () => {
  const routes = createRouteOwnershipGate();
  const doneOrRecover = routes.advance();
  const rowRoute = routes.advance();
  assert.equal(routes.owns(doneOrRecover), false);
  assert.equal(routes.owns(rowRoute), true);

  const resultRoute = routes.advance();
  assert.equal(routes.owns(rowRoute), false);
  assert.equal(routes.owns(resultRoute), true);
});

test("header status avoids repeated announcements and keeps a Stop warning through uncertainty", () => {
  assert.equal(changedStatusText("Recording", "Recording"), null);
  assert.equal(changedStatusText("Recording", "Stopping"), "Stopping");
  assert.equal(
    connectionUncertaintyStatus("recording", { stopFailed: true }),
    "Recording · Stop needs attention · connection uncertain",
  );
  assert.equal(connectionUncertaintyStatus("stopping"), "Stopping · connection uncertain");
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

test("a command snapshot supersedes a pre-command poll before it can render", () => {
  const gate = createLatestRequestGate();
  const preCommandPoll = gate.begin();
  const events = [];
  const commandSnapshot = { capture: "arming" };

  assert.deepEqual(acceptAuthoritativeSnapshot(commandSnapshot, {
    invalidateSnapshotRequests: () => {
      events.push("invalidate");
      gate.invalidate();
    },
    render: (snapshot) => { events.push(`render:${snapshot.capture}`); },
    schedule: (snapshot) => { events.push(`schedule:${snapshot.capture}`); },
  }), commandSnapshot);
  if (gate.isCurrent(preCommandPoll)) events.push("render:old-poll");

  assert.deepEqual(events, ["invalidate", "render:arming", "schedule:arming"]);
});

test("Start, Stop, and dismiss command snapshots drive the visible capture state without app snapshots", () => {
  const rendered = [];
  const scheduled = [];
  let invalidations = 0;
  const apply = (snapshot) => acceptAuthoritativeSnapshot(snapshot, {
    invalidateSnapshotRequests: () => { invalidations += 1; },
    render: (next) => { rendered.push(next.capture); },
    schedule: (next) => { scheduled.push(next.capture); },
  });

  apply({ capture: "arming" });
  apply({ capture: "stopping" });
  apply({ capture: "idle" });

  assert.deepEqual(rendered, ["arming", "stopping", "idle"]);
  assert.deepEqual(scheduled, ["arming", "stopping", "idle"]);
  assert.equal(invalidations, 3);
});

test("Start and Done or Recover share the one dismiss command result", async () => {
  let dismissals = 0;
  let releaseDismiss;
  const transition = createSingleFlight(async () => {
    dismissals += 1;
    await new Promise((resolve) => { releaseDismiss = resolve; });
    return { capture: "idle", startup: "ready", preview: true, retention_operational: true };
  });

  const routes = createRouteOwnershipGate();
  const startRoute = routes.advance();
  const clearedBy = [];
  const fromStart = prepareConsentTransition("transcript-ready", {
    dismiss: () => transition.run(),
    ownsRoute: () => routes.owns(startRoute),
    clearHiddenAttempt: () => { clearedBy.push("Start hidden"); },
    afterOwnedDismiss: () => { clearedBy.push("Start visible"); },
  });
  await Promise.resolve();
  releaseDismiss();
  await Promise.resolve();
  const doneRoute = routes.advance();
  const fromDoneOrRecover = prepareConsentTransition("transcript-ready", {
    dismiss: () => transition.run(),
    ownsRoute: () => routes.owns(doneRoute),
    clearHiddenAttempt: () => { clearedBy.push("Done or Recover hidden"); },
    afterOwnedDismiss: () => { clearedBy.push("Done or Recover visible"); },
  });
  assert.equal(dismissals, 1);

  assert.deepEqual(await Promise.all([fromStart, fromDoneOrRecover]), [false, true]);
  assert.deepEqual(clearedBy, ["Start hidden", "Done or Recover hidden", "Done or Recover visible"]);
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

test("Find does not invalidate or render after its route loses ownership", async () => {
  const events = [];
  let ownsRoute = true;
  let releaseSnapshot;
  const refresh = refreshFindGeneration("words", {
    isCurrent: () => ownsRoute,
    invalidateResults: () => { events.push("invalidate"); },
    snapshot: () => new Promise((resolve) => { releaseSnapshot = resolve; }),
    search: async () => {
      events.push("search");
      return { handle: "result" };
    },
    render: () => { events.push("render"); },
  });
  await Promise.resolve();
  ownsRoute = false;
  releaseSnapshot();
  assert.equal(await refresh, null);
  assert.deepEqual(events, ["invalidate"]);
});

test("transcript-ready start clears hidden state before owned visible cleanup", async () => {
  const events = [];
  const ready = await prepareConsentTransition("transcript-ready", {
    dismiss: async () => {
      events.push("dismiss");
      return { capture: "idle", startup: "ready", preview: true, retention_operational: true };
    },
    clearHiddenAttempt: () => { events.push("clear-hidden"); },
    afterOwnedDismiss: () => { events.push("clear-visible"); },
  });

  assert.equal(ready, true);
  assert.deepEqual(events, ["dismiss", "clear-hidden", "clear-visible"]);
});

test("a non-idle dismissal response never clears the prior attempt", async () => {
  const events = [];
  const ready = await prepareConsentTransition("transcript-ready", {
    dismiss: async () => {
      events.push("dismiss");
      return { capture: "transcript-ready" };
    },
    clearHiddenAttempt: () => { events.push("clear-hidden"); },
    afterOwnedDismiss: () => { events.push("clear-visible"); },
  });

  assert.equal(ready, false);
  assert.deepEqual(events, ["dismiss"]);
});

test("failed dismissal never clears state, refreshes, or admits consent", async () => {
  const events = [];
  await assert.rejects(
    prepareConsentTransition("transcript-ready", {
      dismiss: async () => {
        events.push("dismiss");
        throw new Error("dismiss failed");
      },
      clearHiddenAttempt: () => { events.push("clear-hidden"); },
      afterOwnedDismiss: () => { events.push("clear-visible"); },
    }),
    /dismiss failed/,
  );
  assert.deepEqual(events, ["dismiss"]);
});

test("route loss after dismissal still clears hidden consent state but not visible state", async () => {
  const events = [];
  const ready = await prepareConsentTransition("transcript-ready", {
    dismiss: async () => {
      events.push("dismiss");
      return { capture: "idle", startup: "ready", preview: true, retention_operational: true };
    },
    ownsRoute: () => false,
    clearHiddenAttempt: () => { events.push("clear-hidden"); },
    afterOwnedDismiss: () => { events.push("clear-visible"); },
  });

  assert.equal(ready, false);
  assert.deepEqual(events, ["dismiss", "clear-hidden"]);
});

test("Done or Recover navigation loss prevents visible cleanup", async () => {
  const routes = createRouteOwnershipGate();
  const doneOrRecover = routes.advance();
  const events = [];
  const ready = await prepareConsentTransition("transcript-ready", {
    dismiss: async () => {
      events.push("dismiss");
      routes.advance();
      return { capture: "idle", startup: "ready", preview: true, retention_operational: true };
    },
    ownsRoute: () => routes.owns(doneOrRecover),
    clearHiddenAttempt: () => { events.push("clear-hidden"); },
    afterOwnedDismiss: () => { events.push("clear-visible"); },
  });

  assert.equal(ready, false);
  assert.deepEqual(events, ["dismiss", "clear-hidden"]);
});

test("Start leaves a successful diagnostic dismissal rendered and only clears hidden consent", async () => {
  const events = [];
  const diagnostic = {
    capture: "idle",
    startup: "diagnostic-written",
    preview: true,
    retention_operational: false,
  };
  const ready = await prepareConsentTransition("transcript-ready", {
    dismiss: async () => diagnostic,
    clearHiddenAttempt: () => { events.push("clear-hidden"); },
    afterOwnedDismiss: () => { events.push("clear-visible"); },
  });

  assert.equal(isDismissalReadySnapshot(diagnostic), false);
  assert.equal(ready, false);
  assert.deepEqual(events, ["clear-hidden"]);
});

test("Done or Recover leaves a successful diagnostic dismissal on its startup screen", () => {
  const events = [];
  const diagnostic = {
    capture: "idle",
    startup: "diagnostic-written",
    preview: true,
    retention_operational: false,
  };
  const admitted = settleDismissal(diagnostic, {
    clearHiddenAttempt: () => { events.push("clear-hidden"); },
    afterOwnedDismiss: () => { events.push("clear-visible"); },
  });

  assert.equal(admitted, false);
  assert.deepEqual(events, ["clear-hidden"]);
});

test("idle start is direct and other capture states refuse consent", async () => {
  const actions = {
    dismiss: async () => { throw new Error("unexpected dismissal"); },
    clearHiddenAttempt: () => { throw new Error("unexpected clear"); },
    afterOwnedDismiss: () => { throw new Error("unexpected visible cleanup"); },
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

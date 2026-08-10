import assert from "node:assert/strict";
import test from "node:test";

import {
  createTransitionGate,
  createSingleFlight,
  createWriteQueue,
  acceptAuthoritativeSnapshot,
  isDismissalReadySnapshot,
  settleDismissal,
  createLatestRequestGate,
  createRouteOwnershipGate,
  displayedClaimIdentity,
  enrollmentRecorderPresentation,
  operatingPointPresentation,
  changedStatusText,
  firstRunDeniedPermissionName,
  liveNoteStatus,
  firstRunStepFor,
  captureChannelPresentation,
  connectionUncertaintyStatus,
  headerActionPolicy,
  transcriptPlainText,
  headerStatusPresentation,
  quickControlPresentation,
  commandMenuPresentation,
  helpTopicPresentation,
  shellStatePresentation,
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
  workflowReturnPolicy,
  workflowScreenForSnapshot,
} from "./navigation-state.mjs";

test("workflow routes advance only while they own the screen", () => {
  const recording = { startup: "ready", capture: "recording" };
  const ready = { startup: "ready", capture: "transcript-ready" };

  assert.equal(workflowScreenForSnapshot(recording), "recording-screen");
  assert.equal(workflowScreenForSnapshot(ready), "transcript-screen");
  assert.equal(
    workflowScreenForSnapshot({ startup: "ready", capture: "transcript-ready", meeting_id: "meeting-1" }),
    "meeting-detail-screen",
  );
  assert.equal(workflowScreenForSnapshot({ startup: "ready", capture: "idle" }), "meetings-screen");
  assert.equal(resolvedScreenForSnapshot(recording, "meetings-screen", false), "meetings-screen");
  assert.equal(resolvedScreenForSnapshot(ready, "profile-screen", false), "profile-screen");
  assert.equal(resolvedScreenForSnapshot(recording, "meetings-screen", true), "recording-screen");
  assert.equal(workflowScreenForSnapshot({ startup: "checking", capture: "idle" }), "startup-screen");
});

test("header actions keep one recording control and offer a return to owned workflow states", () => {
  const idle = headerActionPolicy({ startup: "ready", capture: "idle" });
  assert.equal(idle.showProductNavigation, true);
  assert.equal(idle.showStart, true);
  assert.equal(idle.startLabel, "Record a meeting");
  assert.equal(idle.showStop, false);
  assert.equal(idle.showWorkflowReturn, false);

  const transcript = headerActionPolicy(
    { startup: "ready", capture: "transcript-ready" },
    { workflowOwnsRoute: false },
  );
  assert.equal(transcript.showStart, true);
  assert.equal(transcript.startLabel, "Record another meeting");
  assert.equal(transcript.showWorkflowReturn, false);
  assert.equal(transcript.workflowReturnLabel, "View transcript");
  assert.equal(transcript.workflowDestination, "transcript-screen");

  // Reading a finished transcript must not be a dead end: the record control
  // stays in the header there, so the way out never sits below the transcript.
  const onTranscript = headerActionPolicy(
    { startup: "ready", capture: "transcript-ready" },
    { currentScreen: "transcript-screen" },
  );
  assert.equal(onTranscript.showStart, true);
  // Product screens offer a next recording after a completed capture. A
  // mid-capture state still offers no second record control.
  assert.equal(
    headerActionPolicy(
      { startup: "ready", capture: "transcript-ready" },
      { currentScreen: "meetings-screen" },
    ).showStart,
    true,
  );
  const onMeeting = headerActionPolicy(
    { startup: "ready", capture: "transcript-ready" },
    { currentScreen: "meeting-detail-screen", workflowOwnsRoute: false },
  );
  assert.equal(onMeeting.showStart, true);
  assert.equal(onMeeting.startLabel, "Record another meeting");
  assert.equal(onMeeting.showWorkflowReturn, false);
  assert.equal(
    headerActionPolicy(
      { startup: "ready", capture: "recording" },
      { currentScreen: "transcript-screen" },
    ).showStart,
    false,
  );

  assert.deepEqual(
    workflowReturnPolicy({ startup: "ready", capture: "transcribing" }),
    { show: true, label: "View progress", destination: "processing-screen" },
  );
  assert.deepEqual(
    workflowReturnPolicy({ startup: "runtime-missing", capture: "idle" }),
    { show: true, label: "View issue", destination: "startup-screen" },
  );
  assert.equal(
    headerActionPolicy({ startup: "runtime-missing", capture: "idle" }).showProductNavigation,
    false,
  );
  assert.equal(
    headerActionPolicy(
      { startup: "ready", capture: "idle" },
      { currentScreen: "idle-screen" },
    ).showStart,
    false,
  );
  assert.equal(
    headerActionPolicy(
      { startup: "ready", capture: "idle" },
      { currentScreen: "meeting-detail-screen" },
    ).showStart,
    true,
  );
  assert.equal(
    headerActionPolicy(
      { startup: "ready", capture: "idle" },
      { currentScreen: "library-transcript-screen" },
    ).showStart,
    true,
  );
});

test("channel and header visual states use only the relevant snapshot facts", () => {
  assert.deepEqual(captureChannelPresentation(undefined), { label: "Unknown", state: "unknown" });
  assert.deepEqual(captureChannelPresentation("Active"), { label: "Active", state: "active" });
  assert.deepEqual(captureChannelPresentation("Unavailable"), { label: "Unavailable", state: "attention" });
  assert.equal(headerStatusPresentation({ startup: "ready", capture: "idle" }), "unknown");
  assert.equal(headerStatusPresentation({ startup: "ready", capture: "recording" }), "active");
  assert.equal(headerStatusPresentation({ startup: "ready", capture: "recording", degraded: true }), "attention");
  assert.equal(headerStatusPresentation({ startup: "runtime-missing", capture: "idle" }), "attention");
});

test("the desktop quick control names every admitted capture state and action", () => {
  assert.deepEqual(
    quickControlPresentation({ startup: "ready", capture: "idle" }),
    {
      state: "idle",
      triggerLabel: "Ready",
      title: "Ready to record",
      detail: "Nothing is recording. Every attempt starts with consent and retention review.",
      primaryLabel: "Record a meeting",
      secondaryLabel: "",
    },
  );
  assert.equal(
    quickControlPresentation({ startup: "ready", capture: "recording" }).state,
    "recording",
  );
  const degraded = quickControlPresentation({ startup: "ready", capture: "recording", degraded: true });
  assert.equal(degraded.state, "degraded");
  assert.equal(degraded.triggerLabel, "Recording issue");
  assert.equal(degraded.secondaryLabel, "Stop recording");
  assert.equal(
    quickControlPresentation({ startup: "ready", capture: "transcribing" }).primaryLabel,
    "View progress",
  );
  assert.equal(
    quickControlPresentation({ startup: "ready", capture: "transcript-ready" }).secondaryLabel,
    "Record another",
  );
  assert.equal(
    quickControlPresentation({ startup: "runtime-missing", capture: "idle" }).state,
    "error",
  );
});

test("the command menu keeps routes stable and capture actions state-aware", () => {
  const idle = commandMenuPresentation({ startup: "ready", capture: "idle" });
  assert.deepEqual(
    idle.slice(0, 4).map(({ id, shortcut }) => [id, shortcut]),
    [["meetings", "⌘1"], ["ask", "⌘2"], ["actions", "⌘3"], ["settings", "⌘,"]],
  );
  assert.equal(idle.some((command) => command.id === "home"), false);
  assert.equal(idle.find((command) => command.id === "actions").planned, true);
  assert.equal(idle.find((command) => command.id === "setup").action, "setup");
  assert.equal(idle.find((command) => command.id === "states").action, "states");
  assert.equal(idle.find((command) => command.id === "help").action, "help");
  assert.equal(idle.find((command) => command.id === "desktop").action, "desktop");
  assert.deepEqual(
    idle.find((command) => command.id === "workflow"),
    {
      id: "workflow",
      label: "Record a meeting",
      detail: "Open consent and retention review before recording",
      shortcut: "",
      action: "start",
    },
  );

  const recording = commandMenuPresentation({ startup: "ready", capture: "recording" });
  assert.equal(recording.find((command) => command.id === "workflow").label, "View recording");
  assert.equal(recording.find((command) => command.id === "stop").action, "stop");

  const processing = commandMenuPresentation({ startup: "ready", capture: "transcribing" });
  assert.equal(processing.find((command) => command.id === "workflow").label, "View progress");
  assert.equal(processing.some((command) => command.id === "stop"), false);
});

test("help topics keep diagnostics private and updates manual", () => {
  const diagnostics = helpTopicPresentation("diagnostics");
  assert.equal(diagnostics.primaryAction, "states");
  assert.match(diagnostics.lede, /owner-only file on this Mac/);
  assert.deepEqual(diagnostics.facts.map(([label, value]) => [label, value]), [
    ["Included", "Error code and redacted detail"],
    ["Redacted", "Paths, email-like tokens, and environment-style values"],
    ["Not attached", "Audio, transcript files, or operator notes"],
  ]);

  const updates = helpTopicPresentation("updates");
  assert.match(updates.title, /manual for the first release/);
  assert.equal(updates.facts[0][1], "Unavailable");
  assert.match(updates.facts[2][2], /still needs migration-failure and rollback proof/);
  assert.equal(helpTopicPresentation("unknown").id, "overview");
});

test("system-state previews name what survived and never promote interruption to completion", () => {
  const loading = shellStatePresentation("loading");
  assert.equal(loading.primaryAction, "home");
  assert.match(loading.lede, /Recording controls stay unavailable/);

  const empty = shellStatePresentation("empty");
  assert.equal(empty.title, "No retained meetings yet.");
  assert.equal(empty.primaryAction, "start");

  const failure = shellStatePresentation("failure");
  assert.deepEqual(failure.facts.map(([label, value]) => [label, value]), [
    ["Recording audio", "Retained for recovery"],
    ["Operator note", "Retained"],
    ["Transcript", "Unavailable"],
  ]);

  const recovery = shellStatePresentation("recovery");
  assert.equal(recovery.facts[0][1], "Interrupted");
  assert.match(recovery.lede, /rather than complete/);

  const repair = shellStatePresentation("repair");
  assert.equal(repair.primaryAction, "loading");
  assert.match(repair.lede, /private diagnostic on this Mac/);
  assert.equal(shellStatePresentation("unknown").id, "loading");
});

test("mutable actions match the admitted capture and startup states", () => {
  const recording = mutableActionPolicy({ startup: "ready", capture: "recording" });
  assert.equal(recording.showProductNavigation, true);
  assert.equal(recording.canStartMeeting, false);
  assert.equal(recording.canSubmitStart, false);
  assert.equal(recording.showStop, true);
  assert.equal(recording.stopDisabled, false);

  const pending = mutableActionPolicy(
    { startup: "ready", capture: "recording" },
    { stopPending: true },
  );
  assert.equal(pending.stopDisabled, true);
  assert.equal(pending.stopLabel, "Stopping…");

  const stopping = mutableActionPolicy({ startup: "ready", capture: "stopping" });
  assert.equal(stopping.showStop, true);
  assert.equal(stopping.stopDisabled, true);
  assert.equal(stopping.stopLabel, "Stopping…");

  const processing = mutableActionPolicy({ startup: "ready", capture: "transcribing" });
  assert.equal(processing.showStop, false);
  assert.equal(processing.canDismissMeeting, false);

  const transcript = mutableActionPolicy({ startup: "ready", capture: "transcript-ready" });
  assert.equal(transcript.canStartMeeting, true);
  assert.equal(transcript.canDismissMeeting, true);

  const idle = mutableActionPolicy({ startup: "ready", capture: "idle" });
  assert.equal(idle.canSubmitStart, true);
  assert.equal(idle.canDismissMeeting, false);

  const recovered = mutableActionPolicy({ startup: "ready", capture: "recovered-interrupted" });
  assert.equal(recovered.canDismissMeeting, true);

  const failure = mutableActionPolicy({ startup: "service-timeout", capture: "idle" });
  assert.equal(failure.canRetryStartup, true);
  assert.equal(failure.showProductNavigation, true);
  assert.equal(
    mutableActionPolicy({ startup: "runtime-missing", capture: "idle" }).canRetryStartup,
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
    return { capture: "idle", startup: "ready", retention_operational: true };
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
      return { capture: "idle", startup: "ready", retention_operational: true };
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
      return { capture: "idle", startup: "ready", retention_operational: true };
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
      return { capture: "idle", startup: "ready", retention_operational: true };
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
  assert.equal(rootForDestination("home-screen", "find-screen"), "home-screen");
  assert.equal(rootForDestination("find-screen", "meetings-screen"), "find-screen");
  assert.equal(rootForDestination("meetings-screen", "find-screen"), "meetings-screen");
  assert.equal(rootForDestination("promises-screen", "find-screen"), "promises-screen");
  assert.equal(rootForDestination("meeting-detail-screen", "meetings-screen"), "meetings-screen");
  assert.equal(rootForDestination("library-transcript-screen", "find-screen"), "find-screen");
  assert.equal(rootForDestination("library-transcript-screen", "promises-screen"), "promises-screen");
  assert.equal(rootForDestination("profile-screen", "meetings-screen"), "meetings-screen");
  assert.equal(rootForDestination("profile-screen", "unknown"), "meetings-screen");
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
    transcriptReturnRoute("meeting-detail", "meeting-a", { claim, detailScrollTop: 184.5, detailTab: "evidence" }),
    {
      destination: "meeting-detail",
      meetingId: "meeting-a",
      claim,
      detailScrollTop: 184.5,
      detailTab: "evidence",
    },
  );
  assert.deepEqual(
    transcriptReturnRoute("find", "meeting-a", { claim, detailScrollTop: 184 }),
    {
      destination: "find",
      meetingId: null,
      claim: null,
      detailScrollTop: 0,
      detailTab: "note",
      findFocus: "exact",
    },
  );
  assert.equal(
    transcriptReturnRoute("find", "", { findFocus: "meaning" }).findFocus,
    "meaning",
  );
  assert.deepEqual(
    transcriptReturnRoute("meeting-detail", "", { claim, detailScrollTop: 184 }),
    { destination: "product-root", meetingId: null, claim: null, detailScrollTop: 0, detailTab: "note" },
  );
  assert.equal(
    transcriptReturnRoute("meeting-detail", "meeting-a", { detailTab: "unknown" }).detailTab,
    "note",
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
    meetingDetailPresentation({ state: "transcript-only", transcriptHandle: "fresh-handle" }),
    {
      kind: "transcript-only",
      title: "Transcript",
      lede: "No automatic note was created for this meeting. The retained transcript remains the source of record.",
      fallbackTitle: "Transcript only",
      fallbackCopy: "Open the retained transcript to review this meeting’s words.",
      canOpenTranscript: true,
    },
  );
  assert.deepEqual(
    meetingDetailPresentation({ state: "summary-failed", transcriptHandle: "fresh-handle" }),
    {
      kind: "transcript-only",
      title: "Transcript",
      lede: "An automatic note is not available for this meeting. The retained transcript remains the source of record.",
      fallbackTitle: "Transcript only",
      fallbackCopy: "Open the retained transcript to review this meeting’s words.",
      canOpenTranscript: true,
    },
  );
  assert.deepEqual(
    meetingDetailPresentation({ state: "summary-failed", transcriptHandle: null }),
    {
      kind: "transcript-unavailable",
      title: "Meeting details.",
      lede: "A transcript is not available from this retained meeting view.",
      fallbackTitle: "Transcript unavailable",
      fallbackCopy: "No retained words or automatic note can be opened right now. Return to Meetings and try again.",
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
      fallbackCopy: "Return to Meetings and try again.",
      canOpenTranscript: false,
    },
  );
});

test("the release snapshot carries no lane flag and still reaches Start recording", () => {
  // The 0.2.0 cohort DMG shipped a shell whose record entry and navigation
  // required a preview-lane flag the release backend never sends, so the
  // button was unreachable on every machine. The product surface keys off
  // startup and capture state alone; lanes differ only in which commands
  // their window capability permits.
  const shipped = headerActionPolicy({ startup: "ready", capture: "idle" });
  assert.equal(shipped.showProductNavigation, true);
  assert.equal(shipped.showStart, true);
  assert.equal(
    mutableActionPolicy({ startup: "ready", capture: "idle" }).canStartMeeting,
    true,
  );
});

test("the recorder surface alone decides the three recorder modes", () => {
  // An active take shows Stop regardless of availability flags: the backend
  // reports availability false during a take, and the in-progress sitting in
  // the store's projection is the authoritative signal.
  assert.deepEqual(
    enrollmentRecorderPresentation({
      recordingAvailable: false,
      recordingUnavailableReason: "A setup recording is already in progress.",
      sittings: [{ state: "recording-in-progress" }],
      lastOutcome: null,
    }),
    { mode: "recording", entryText: "", outcomeText: "" },
  );
  assert.deepEqual(
    enrollmentRecorderPresentation({
      recordingAvailable: true,
      recordingUnavailableReason: null,
      sittings: [{ state: "saved" }],
      lastOutcome:
        "The recording was saved: voice material is stored and the temporary recording was deleted.",
    }),
    {
      mode: "ready",
      entryText: "",
      outcomeText:
        "The recording was saved: voice material is stored and the temporary recording was deleted.",
    },
  );
  // A closed capture whose attempt is still finishing (derivation) is its
  // own mode: no Stop control, the backend's progress sentence, and the
  // caller keeps polling until the attempt ends.
  assert.deepEqual(
    enrollmentRecorderPresentation({
      recordingAvailable: false,
      recordingUnavailableReason:
        "The recording finished. The app is deriving voice material from it now.",
      sittings: [{ state: "raw-retained" }],
      lastOutcome: null,
      attemptActive: true,
    }),
    {
      mode: "processing",
      entryText:
        "The recording finished. The app is deriving voice material from it now.",
      outcomeText: "",
    },
  );
  // Unavailable renders the backend's own boundary sentence, and a missing
  // surface never renders as permission.
  assert.equal(
    enrollmentRecorderPresentation({
      recordingAvailable: false,
      recordingUnavailableReason: "This build does not yet include an approved voice-measurement model.",
      sittings: [],
      lastOutcome: null,
    }).entryText,
    "This build does not yet include an approved voice-measurement model.",
  );
  assert.deepEqual(enrollmentRecorderPresentation(null), {
    mode: "unavailable",
    entryText:
      "Voice profile status is unavailable, so a setup recording cannot start.",
    outcomeText: "",
  });
});

test("operating points order loosest to strictest with measured costs and no invented rows", () => {
  const rows = operatingPointPresentation([
    { targetFrr: 0.1, measuredFrr: 0.083, nOperator: 12, falseAdmitRate: 0.0, nOther: 22, threshold: 0.31 },
    { targetFrr: 0.02, measuredFrr: 0.0, nOperator: 12, falseAdmitRate: 0.045, nOther: 22, threshold: 0.18 },
    { targetFrr: 0.05, measuredFrr: 0.041, nOperator: 12, falseAdmitRate: 0.0, nOther: 22, threshold: 0.24 },
  ]);
  assert.deepEqual(
    rows.map((row) => [row.label, row.point.targetFrr]),
    [
      ["Preserve more of my speech", 0.02],
      ["Measured middle point", 0.05],
      ["Keep more other voices out", 0.1],
    ],
  );
  assert.equal(
    rows[0].costs,
    "Sets aside about 0.0% of your held-out speech (12 segments) · admits about 4.5% of other voices (22 segments).",
  );
  // One measured option is not a choice, and an empty response renders nothing.
  assert.deepEqual(operatingPointPresentation([{ targetFrr: 0.05, measuredFrr: 0, nOperator: 5, falseAdmitRate: 0, nOther: 20 }]), []);
  assert.deepEqual(operatingPointPresentation(null), []);
});

test("copied transcript text keeps withheld turns visible", () => {
  const text = transcriptPlainText([
    { start: 0, speaker: "Me", text: "we agreed to defer the migration" },
    { start: 63, withheld: true },
    { start: 125, speaker: "Them", text: "  send the numbers Friday  " },
    { start: 130, speaker: "Them", text: "   " },
    { start: 140, text: "no speaker recorded" },
  ]);
  assert.deepEqual(text.split("\n"), [
    "[00:00] Me: we agreed to defer the migration",
    "[01:03] (withheld — a voice check set this turn aside)",
    "[02:05] Them: send the numbers Friday",
    "[02:20] Unattributed: no speaker recorded",
  ]);
  // A transcript that hands over only the words it kept would read complete
  // while the app knows it is not.
  assert.ok(text.includes("withheld"));
  assert.equal(transcriptPlainText([]), "");
  assert.equal(transcriptPlainText(null), "");
});

test("first run routes on what was measured, and never on what was not", () => {
  const probe = (over) => ({
    microphone: "authorized",
    systemAudio: "unmeasured",
    probeUnavailable: false,
    prompted: false,
    ...over,
  });

  // The ordinary opening hand: nothing asked yet.
  assert.equal(firstRunStepFor(probe({ microphone: "not-determined" })), "request-microphone");
  // A microphone that is settled and fine leaves system audio as the next question,
  // because a status read cannot measure a tap and says so.
  assert.equal(firstRunStepFor(probe({})), "request-audio-capture");

  // The route a review found broken. `first_run_request_system_audio` answers about
  // the tap and reports the microphone as `unmeasured`; reading that as `unknown`
  // sent a granted permission to the panel that says nothing could be measured.
  assert.equal(
    firstRunStepFor(probe({ microphone: "unmeasured", systemAudio: "authorized" })),
    "enrol-voice",
  );
  assert.equal(
    firstRunStepFor(probe({ microphone: "unmeasured", systemAudio: "unavailable" })),
    "denied-recovery",
  );

  // "You said no" and "we could not ask" stay apart, in both directions.
  assert.equal(firstRunStepFor(probe({ microphone: "denied" })), "denied-recovery");
  assert.equal(firstRunStepFor(probe({ microphone: "restricted" })), "denied-recovery");
  assert.equal(firstRunStepFor(probe({ microphone: "unknown" })), "unavailable");
  assert.equal(firstRunStepFor(probe({ probeUnavailable: true })), "unavailable");
  assert.equal(firstRunStepFor(null), "unavailable");
  assert.equal(firstRunStepFor(probe({ systemAudio: "unsupported" })), "unavailable");

  // A value neither side knows about must not be read as progress. The Rust enum
  // is closed, so this is unreachable today; it is pinned because the way it goes
  // wrong later is a build that adds a state and a shell that treats it as fine.
  assert.equal(firstRunStepFor(probe({ microphone: "granted" })), "unavailable");
  assert.equal(firstRunStepFor(probe({ microphone: undefined })), "unavailable");
  // System audio is the opposite default on purpose: not knowing means ask.
  assert.equal(firstRunStepFor(probe({ systemAudio: "yes" })), "request-audio-capture");

  // The recovery panel names one System Settings row, and which one depends on
  // which permission was refused — the microphone is checked first.
  assert.equal(firstRunDeniedPermissionName(probe({ microphone: "denied" })), "Microphone");
  assert.equal(
    firstRunDeniedPermissionName(probe({ microphone: "unmeasured", systemAudio: "unavailable" })),
    "System Audio Recording",
  );
});

test("the live note reports only states this build can actually reach", () => {
  // Nothing transcribes while a meeting runs — capture finishes, then the
  // transcript is made — so `streaming` and `lagging` from the screen inventory
  // cannot occur and are not rendered. These four can.
  assert.equal(liveNoteStatus({}).state, "empty");
  assert.equal(liveNoteStatus({ text: "a thought" }).state, "typing");
  assert.equal(liveNoteStatus({ text: "a thought", pending: true }).message, "Saving…");
  assert.equal(liveNoteStatus({ text: "a thought", saved: true }).message, "Saved.");

  // An unreadable note is not an error that clears on retry: it means words
  // exist that this build could not parse, and typing into an empty box would
  // replace text the operator never saw. So the box closes.
  const unreadable = liveNoteStatus({ unreadable: true, text: "" });
  assert.equal(unreadable.state, "unreadable");
  assert.equal(unreadable.editable, false);

  // A failed save keeps the box open, because the text in it is the only copy.
  const failed = liveNoteStatus({ text: "a thought", failed: "That note could not be saved." });
  assert.equal(failed.state, "failed");
  assert.equal(failed.editable, true);
  assert.equal(failed.message, "That note could not be saved.");

  // Unreadable outranks everything, including a pending save.
  assert.equal(liveNoteStatus({ unreadable: true, pending: true, failed: "x" }).editable, false);
});

test("a write queue runs every push, unlike single flight which drops them", async () => {
  // The contrast is the reason this exists. Both are given the same three calls
  // while the first is still running.
  const singleFlightRuns = [];
  let release;
  const blocked = new Promise((resolve) => { release = resolve; });
  const flight = createSingleFlight(() => { singleFlightRuns.push(1); return blocked; });
  flight.run(); flight.run(); flight.run();
  // The loader is deferred a microtask, so let it start before counting.
  await Promise.resolve();
  assert.equal(singleFlightRuns.length, 1, "single flight coalesces, by design");
  release();

  // The queue runs all three, in order, each reading state as of when it runs.
  const observed = [];
  let value = "a";
  const queue = createWriteQueue(async () => { observed.push(value); });
  const first = queue.push();
  value = "b";
  const second = queue.push();
  value = "c";
  const third = queue.push();
  await Promise.all([first, second, third]);
  {
    // Three runs, not one. And each saw the value current when its turn came,
    // which is what lets one appended save capture typing that landed during the
    // save ahead of it — the guarantee the flush on Stop depends on.
    assert.equal(observed.length, 3);
    assert.deepEqual(observed, ["c", "c", "c"]);
  }
});

test("a rejected write does not poison the queue behind it", async () => {
  const ran = [];
  let fail = true;
  const queue = createWriteQueue(async () => {
    ran.push(fail);
    if (fail) { fail = false; throw new Error("save failed"); }
  });
  // The first rejects. Awaiting it must not throw at the caller, and the second
  // must still run — a failed autosave cannot stop the flush that follows it.
  await queue.push();
  await queue.push();
  assert.deepEqual(ran, [true, false]);
});

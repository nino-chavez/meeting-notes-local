export const PRODUCT_ROOT_SCREENS = Object.freeze([
  "find-screen",
  "meetings-screen",
  "promises-screen",
]);

export function workflowScreenForSnapshot(snapshot, currentScreen = "find-screen") {
  const startup = snapshot?.startup || "diagnostic-written";
  const capture = snapshot?.capture || "idle";
  if (startup !== "ready") return "startup-screen";
  if (capture === "idle") {
    return currentScreen === "idle-screen" ? "idle-screen" : "find-screen";
  }
  return {
    arming: "arming-screen",
    recording: "recording-screen",
    stopping: "recording-screen",
    captured: "processing-screen",
    transcribing: "processing-screen",
    "transcript-ready": "transcript-screen",
  }[capture] || "error-screen";
}

export function resolvedScreenForSnapshot(snapshot, currentScreen, workflowOwnsRoute) {
  return workflowOwnsRoute
    ? workflowScreenForSnapshot(snapshot, currentScreen)
    : currentScreen;
}

export function mutableActionPolicy(snapshot, { stopPending = false } = {}) {
  const startup = snapshot?.startup || "diagnostic-written";
  const capture = snapshot?.capture || "idle";
  const startupReady = startup === "ready";
  const stopping = capture === "stopping";
  const recording = capture === "recording";
  return {
    showProductNavigation: true,
    canStartMeeting: startupReady
      && ["idle", "transcript-ready"].includes(capture),
    canSubmitStart: startupReady && capture === "idle",
    canDismissMeeting: startupReady
      && ["transcript-ready", "transcription-failed", "recovered-interrupted"].includes(capture),
    canRetryStartup: ["runtime-missing", "service-timeout", "diagnostic-written"].includes(startup)
      && !["arming", "recording", "stopping", "captured", "transcribing"].includes(capture),
    showStop: startupReady && (recording || stopping),
    stopDisabled: !recording || stopPending,
    stopLabel: stopping || stopPending ? "Stopping…" : "Stop recording",
  };
}

export function headerActionPolicy(snapshot, {
  stopPending = false,
  workflowOwnsRoute = true,
  currentScreen = "find-screen",
} = {}) {
  const capture = snapshot?.capture || "idle";
  const startup = snapshot?.startup || "diagnostic-written";
  const actions = mutableActionPolicy(snapshot, { stopPending });
  const workflow = workflowReturnPolicy(snapshot);
  return {
    showProductNavigation: actions.showProductNavigation && startup === "ready",
    // The finished-transcript screen carries the record action too. Its only
    // exit used to be a control below the whole transcript, so on a long
    // meeting the way out was hundreds of turns down and read as a bug
    // (operator report, 2026-08-05). `canStartMeeting` already admits
    // transcript-ready, and openStartMeeting routes through
    // prepareConsentTransition, which dismisses the finished attempt before
    // consent — so this exposes an existing supported path rather than a new
    // one. Every other screen still requires a genuinely idle capture.
    showStart: actions.canStartMeeting
      && ((capture === "idle"
        && [
          "find-screen",
          "meetings-screen",
          "promises-screen",
          "meeting-detail-screen",
          "library-transcript-screen",
          "profile-screen",
        ].includes(currentScreen))
        || (capture === "transcript-ready" && currentScreen === "transcript-screen")),
    showStop: actions.showStop,
    stopDisabled: actions.stopDisabled,
    stopLabel: actions.stopLabel,
    showWorkflowReturn: !workflowOwnsRoute && workflow.show,
    workflowReturnLabel: workflow.label,
    workflowDestination: workflow.destination,
    startupReady: startup === "ready",
  };
}

export function captureChannelPresentation(state) {
  if (state === "Active") return { label: "Active", state: "active" };
  if (typeof state === "string" && state.trim()) return { label: state, state: "attention" };
  return { label: "Unknown", state: "unknown" };
}

export function headerStatusPresentation(snapshot) {
  const startup = snapshot?.startup || "diagnostic-written";
  const capture = snapshot?.capture || "idle";
  if (capture === "recording") {
    return snapshot?.degraded ? "attention" : "active";
  }
  if (["runtime-missing", "service-timeout", "diagnostic-written", "reinstall-required"].includes(startup)
      || !["idle", "arming", "stopping", "captured", "transcribing", "transcript-ready"].includes(capture)) {
    return "attention";
  }
  return "unknown";
}

export function workflowReturnPolicy(snapshot) {
  const startup = snapshot?.startup || "diagnostic-written";
  const capture = snapshot?.capture || "idle";
  const destination = workflowScreenForSnapshot(snapshot);
  if (startup !== "ready" || !["idle", "arming", "recording", "stopping", "captured", "transcribing", "transcript-ready"].includes(capture)) {
    return { show: true, label: "View issue", destination };
  }
  if (["arming", "recording", "stopping"].includes(capture)) {
    return { show: true, label: "View recording", destination };
  }
  if (["captured", "transcribing"].includes(capture)) {
    return { show: true, label: "View progress", destination };
  }
  if (capture === "transcript-ready") {
    return { show: true, label: "View transcript", destination };
  }
  return { show: false, label: "", destination };
}

export function connectionUncertaintyStatus(capture, { stopFailed = false } = {}) {
  if (capture === "recording") {
    return stopFailed
      ? "Recording · Stop needs attention · connection uncertain"
      : "Recording · connection uncertain";
  }
  if (capture === "stopping") return "Stopping · connection uncertain";
  return "Connection uncertain · local state has not changed";
}

export function changedStatusText(previous, next) {
  return previous === next ? null : next;
}

export function rootForDestination(destination, currentRoot = "find-screen") {
  if (PRODUCT_ROOT_SCREENS.includes(destination)) return destination;
  return PRODUCT_ROOT_SCREENS.includes(currentRoot) ? currentRoot : "find-screen";
}

export function restoredScrollPosition(storedPosition, reset = false) {
  if (reset || !Number.isFinite(storedPosition) || storedPosition < 0) return 0;
  return storedPosition;
}

export function normalizedScrollPosition(value) {
  return Number.isFinite(value) && value >= 0 ? value : 0;
}

export function rowForMeetingId(snapshot, meetingId) {
  if (!meetingId || !Array.isArray(snapshot?.rows)) return null;
  return snapshot.rows.find((row) => row?.meetingId === meetingId) || null;
}

export function displayedClaimIdentity(claim) {
  if (!Number.isInteger(claim?.ordinal)
      || typeof claim?.claimType !== "string"
      || typeof claim?.claim !== "string") return null;
  return {
    ordinal: claim.ordinal,
    claimType: claim.claimType,
    claim: claim.claim,
  };
}

export function sameDisplayedClaim(left, right) {
  const first = displayedClaimIdentity(left);
  const second = displayedClaimIdentity(right);
  return Boolean(first && second
    && first.ordinal === second.ordinal
    && first.claimType === second.claimType
    && first.claim === second.claim);
}

export function transcriptReturnRoute(origin, meetingId, {
  claim = null,
  detailScrollTop = 0,
} = {}) {
  if (origin === "meeting-detail" && meetingId) {
    return {
      destination: "meeting-detail",
      meetingId,
      claim: displayedClaimIdentity(claim),
      detailScrollTop: normalizedScrollPosition(detailScrollTop),
    };
  }
  return {
    destination: "product-root",
    meetingId: null,
    claim: null,
    detailScrollTop: 0,
  };
}

export function meetingDetailPresentation(response) {
  const transcriptAvailable = Boolean(response?.transcriptHandle);
  if (response?.state === "transcript-only" && !transcriptAvailable) {
    return {
      kind: "metadata-only",
      title: "Meeting details.",
      lede: "This meeting’s retained status and recording information are available. No transcript was created.",
      fallbackTitle: "No transcript was created",
      fallbackCopy: "There are no retained words or automatic note to open for this meeting.",
      canOpenTranscript: false,
    };
  }
  if (response?.state === "summary-failed" && !transcriptAvailable) {
    return {
      kind: "transcript-unavailable",
      title: "Meeting details.",
      lede: "A transcript is not available from this retained meeting view.",
      fallbackTitle: "Transcript unavailable",
      fallbackCopy: "No retained words or automatic note can be opened right now. Return to Meetings and try again.",
      canOpenTranscript: false,
    };
  }
  if (response?.state !== "note" && !transcriptAvailable) {
    return {
      kind: "unavailable",
      title: "Meeting unavailable.",
      lede: "This retained meeting could not be reopened. Its current transcript, note, and recording facts are unavailable in this view.",
      fallbackTitle: "Meeting unavailable",
      fallbackCopy: "Return to Meetings and try again.",
      canOpenTranscript: false,
    };
  }
  if (response?.state === "transcript-only" || response?.state === "summary-failed") {
    const summaryFailed = response.state === "summary-failed";
    return {
      kind: "transcript-only",
      title: "Transcript",
      lede: summaryFailed
        ? "An automatic note is not available for this meeting. The retained transcript remains the source of record."
        : "No automatic note was created for this meeting. The retained transcript remains the source of record.",
      fallbackTitle: "Transcript only",
      fallbackCopy: "Open the retained transcript to review this meeting’s words.",
      canOpenTranscript: transcriptAvailable,
    };
  }
  return {
    kind: "note",
    title: "Note and transcript.",
    lede: "An automatic note is a reading aid. Evidence links locate the exact retained transcript words behind each claim.",
    fallbackTitle: "Transcript only",
    fallbackCopy: "No automatic note is available for this meeting. The retained transcript remains the source of record.",
    canOpenTranscript: false,
  };
}

export function createTransitionGate() {
  let active = null;
  let sequence = 0;
  return {
    enter(kind, route) {
      if (active) return null;
      const ticket = { kind, route, sequence: sequence += 1 };
      active = ticket;
      return ticket;
    },
    owns(ticket) {
      return active === ticket;
    },
    release(ticket) {
      if (active !== ticket) return false;
      active = null;
      return true;
    },
    active() {
      return active;
    },
  };
}

export function transitionOwnsRoute(gate, ticket, route) {
  return Boolean(gate?.owns(ticket)
    && ticket?.route?.screen === route?.screen
    && ticket?.route?.revision === route?.revision);
}

export function retentionDeadlineMessage(epochSeconds) {
  const value = Number(epochSeconds) * 1000;
  const deadline = new Date(value);
  if (!Number.isFinite(value) || value <= 0 || Number.isNaN(deadline.getTime())) {
    return "The audio deletion time is unavailable. This Preview cannot show when the audio becomes due.";
  }
  const localDateTime = new Intl.DateTimeFormat(undefined, {
    dateStyle: "full", timeStyle: "short",
  }).format(deadline);
  return `Audio becomes due for deletion on ${localDateTime}. Deletion runs while the app is open, or the next time it opens.`;
}

export function createSingleFlight(loader) {
  let activePromise = null;
  return {
    run() {
      if (!activePromise) {
        const load = Promise.resolve().then(loader);
        const shared = load.finally(() => {
          if (activePromise === shared) activePromise = null;
        });
        activePromise = shared;
      }
      return activePromise;
    },
  };
}

export function createLatestRequestGate() {
  let latest = 0;
  return {
    begin() {
      latest += 1;
      return latest;
    },
    isCurrent(ticket) {
      return ticket === latest;
    },
    invalidate() {
      latest += 1;
      return latest;
    },
  };
}

export function createRouteOwnershipGate() {
  let current = 0;
  return {
    advance() {
      current += 1;
      return current;
    },
    owns(ticket) {
      return ticket === current;
    },
  };
}

export function createFreshSnapshotOperation(refresh, superseded) {
  return createSingleFlight(async () => {
    let snapshot = await refresh();
    while (snapshot === superseded) snapshot = await refresh();
    return snapshot;
  });
}

export function acceptAuthoritativeSnapshot(snapshot, actions) {
  actions.invalidateSnapshotRequests();
  actions.render(snapshot);
  actions.schedule(snapshot);
  return snapshot;
}

export function isDismissalReadySnapshot(snapshot) {
  return snapshot?.capture === "idle"
    && snapshot?.startup === "ready"
    && snapshot?.retention_operational !== false;
}

export function settleDismissal(snapshot, actions) {
  if (snapshot?.capture !== "idle") return false;
  actions.clearHiddenAttempt();
  if (!isDismissalReadySnapshot(snapshot)) return false;
  if (actions.ownsRoute && !actions.ownsRoute()) return false;
  actions.afterOwnedDismiss();
  return true;
}

export async function refreshFindGeneration(query, actions) {
  if (actions.isCurrent && !actions.isCurrent()) return null;
  actions.invalidateResults();
  await actions.snapshot();
  if (actions.isCurrent && !actions.isCurrent()) return null;
  if (!query) return null;
  const response = await actions.search(query);
  if (actions.isCurrent && !actions.isCurrent()) return null;
  actions.render(response);
  return response;
}

export async function prepareConsentTransition(capture, actions) {
  if (capture === "idle") return true;
  if (capture !== "transcript-ready") return false;
  const snapshot = await actions.dismiss();
  return settleDismissal(snapshot, actions);
}

// § I choosing-operating-point: two or three ordered named options, each
// carrying both actual measured costs, and never a number to type. The
// first (lowest target) preserves more of the operator's speech; the last
// (highest target) keeps more other voices out; a surviving middle point is
// exactly that. Fewer than two rows is not a choice and renders nothing.
export function operatingPointPresentation(points) {
  const rows = (Array.isArray(points) ? points : [])
    .filter((point) => Number.isFinite(point?.targetFrr))
    .sort((a, b) => a.targetFrr - b.targetFrr);
  if (rows.length < 2) return [];
  return rows.map((point, index) => ({
    point,
    label:
      index === 0
        ? "Preserve more of my speech"
        : index === rows.length - 1
          ? "Keep more other voices out"
          : "Measured middle point",
    costs: operatingPointCosts(point),
  }));
}

export function operatingPointCosts(point) {
  const rate = (value) => `${(value * 100).toFixed(1)}%`;
  const own = `Sets aside about ${rate(point.measuredFrr)} of your held-out speech (${point.nOperator} segments)`;
  const others =
    point.falseAdmitRate === null || point.falseAdmitRate === undefined
      ? "no measured other-voice cost"
      : `admits about ${rate(point.falseAdmitRate)} of other voices (${point.nOther} segments)`;
  return `${own} · ${others}.`;
}

// The recorder half of the Voice profile screen has exactly four modes, and
// the surface alone decides them: an active take shows Stop; a take whose
// capture closed but whose attempt is still finishing (derivation) shows the
// backend's own progress sentence and keeps polling; an available recorder
// shows the start form; everything else shows the backend's boundary
// sentence. The fallback sentence mirrors the backend's status-unavailable
// reason so a missing surface never renders as permission.
export function enrollmentRecorderPresentation(surface) {
  const sittings = Array.isArray(surface?.sittings) ? surface.sittings : [];
  const recordingActive = sittings.some(
    (sitting) => sitting?.state === "recording-in-progress",
  );
  if (recordingActive) {
    return { mode: "recording", entryText: "", outcomeText: "" };
  }
  const outcomeText = typeof surface?.lastOutcome === "string" ? surface.lastOutcome : "";
  if (surface?.attemptActive === true) {
    return {
      mode: "processing",
      entryText:
        surface?.recordingUnavailableReason
        || "The app is finishing this setup recording.",
      outcomeText,
    };
  }
  if (surface?.recordingAvailable === true) {
    return { mode: "ready", entryText: "", outcomeText };
  }
  return {
    mode: "unavailable",
    entryText:
      surface?.recordingUnavailableReason
      || "Voice profile status is unavailable, so a setup recording cannot start.",
    outcomeText,
  };
}

// Plain text for the operator's clipboard, so a transcript can be pasted into
// whatever they already use. A withheld turn keeps a line of its own: dropping
// it would hand over a transcript that reads complete while the app knows it is
// not, which is the one thing this product exists not to do. The text carries no
// path, digest or meeting identifier — the operator asked for the words.
export function transcriptPlainText(turns) {
  const rows = Array.isArray(turns) ? turns : [];
  const lines = [];
  for (const turn of rows) {
    const seconds = Math.max(0, Math.floor(Number(turn?.start) || 0));
    const stamp = `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
    if (turn?.withheld) {
      lines.push(`[${stamp}] (withheld — a voice check set this turn aside)`);
      continue;
    }
    const speaker = typeof turn?.speaker === "string" && turn.speaker
      ? turn.speaker
      : "Unattributed";
    const text = typeof turn?.text === "string" ? turn.text.trim() : "";
    if (!text) continue;
    lines.push(`[${stamp}] ${speaker}: ${text}`);
  }
  return lines.join("\n");
}

// § H. The one place a permission measurement becomes a first-run step.
//
// Kept here rather than in main.js because it is a routing decision, and routing
// decisions in this shell are pure functions with tests. It was written inline in
// main.js first and a review found a route it got wrong; nothing could have failed,
// because nothing was calling it.
//
// `unmeasured` is the load-bearing value. A request answers about the permission it
// asked for and says `unmeasured` about the other one, which is not the same as
// `unknown` — `unknown` means the measurement failed and the operator has nowhere
// to go, while `unmeasured` means carry on with what the previous step established.
// Reading a system-audio request's `unmeasured` microphone as `unknown` sent a
// successful grant to the panel that says nothing could be measured.
export function firstRunStepFor(result) {
  if (!result || result.probeUnavailable) return "unavailable";
  const microphone = result.microphone;
  if (microphone === "not-determined") return "request-microphone";
  // restricted is grouped with denied because the operator's next action is the
  // same — it cannot be resolved from inside this app either way.
  if (microphone === "denied" || microphone === "restricted") return "denied-recovery";
  // Only these two continue, and the list is stated rather than left as a fall-
  // through: anything else — `unknown`, or a value a future build sends that this
  // one does not know — must stop here rather than be read as progress. `unmeasured`
  // continues because it is only produced by the system-audio request, which is
  // reachable only from a step that already measured the microphone as authorized.
  if (microphone !== "authorized" && microphone !== "unmeasured") return "unavailable";
  switch (result.systemAudio) {
    case "authorized":
      return "enrol-voice";
    case "unavailable":
      return "denied-recovery";
    case "unsupported":
    case "unknown":
      return "unavailable";
    default:
      // `unmeasured` is the ordinary case: there is no status API for taps, so the
      // only way to learn this is to ask, and asking is the step.
      return "request-audio-capture";
  }
}

// Which System Settings row to name on the recovery panel.
//
// The microphone is checked first, so a refusal there is the reason unless the
// microphone is fine. Named exactly, because "grant the permission in System
// Settings" sends an operator to a list of fourteen rows.
export function firstRunDeniedPermissionName(result) {
  return result?.microphone === "denied" || result?.microphone === "restricted"
    ? "Microphone"
    : "System Audio Recording";
}

// § D. What the live-note surface says about itself.
//
// Kept pure and here, with the shell's other decisions, because the previous
// surface built inline in main.js shipped a route nothing could test. The four
// states are the ones that can actually occur in this build; `streaming` and
// `lagging` from the screen inventory cannot, because nothing transcribes while
// a meeting runs — capture finishes, then the transcript is made. A surface
// carrying a state its pipeline cannot reach is the failure feature 10 forbids,
// so they are absent rather than stubbed.
//
// `unreadable` is not an error state that resolves on retry. It means a note
// exists that this build could not parse, and the only correct response is to
// stop offering to type over it — an empty box the operator fills would replace
// words they never saw.
export function liveNoteStatus(note = {}) {
  if (note.unreadable) {
    return {
      state: "unreadable",
      editable: false,
      message: "An earlier note for this meeting could not be read, so it has been left alone.",
    };
  }
  if (note.failed) {
    return { state: "failed", editable: true, message: note.failed };
  }
  if (note.pending) {
    return { state: "typing", editable: true, message: "Saving…" };
  }
  if (note.saved) {
    return { state: "typing", editable: true, message: "Saved." };
  }
  if (!note.text) {
    return { state: "empty", editable: true, message: "" };
  }
  return { state: "typing", editable: true, message: "" };
}

// Serialize writes without dropping any of them.
//
// The distinction from `createSingleFlight` is the whole point and it is easy to
// get backwards. Single-flight *coalesces*: a call arriving during a run gets the
// running promise back and its own work never happens. That is right for a read,
// where a fresh answer is a fresh answer. It is wrong for a write, and a live
// note is where the difference is worth someone's words: a save arriving while
// another is in flight was dropped, so pressing Stop mid-autosave flushed
// nothing, and the closing thought the flush exists to keep was the one lost.
//
// Each push appends a link that runs after everything ahead of it, so the work
// reads its inputs when it runs rather than when it was queued. That is what lets
// one appended write capture keystrokes that landed during the previous one.
// A rejected link cannot poison the chain: the queue continues.
export function createWriteQueue(write) {
  let tail = Promise.resolve();
  return {
    push() {
      tail = tail.then(write).catch(() => {});
      return tail;
    },
  };
}

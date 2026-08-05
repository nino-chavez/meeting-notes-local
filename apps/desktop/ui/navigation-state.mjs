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
    showStart: actions.canStartMeeting
      && capture === "idle"
      && [
        "find-screen",
        "meetings-screen",
        "promises-screen",
        "meeting-detail-screen",
        "library-transcript-screen",
        "profile-screen",
      ].includes(currentScreen),
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

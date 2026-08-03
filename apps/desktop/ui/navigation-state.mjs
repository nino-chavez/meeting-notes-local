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
  const preview = snapshot?.preview === true;
  const startup = snapshot?.startup || "diagnostic-written";
  const capture = snapshot?.capture || "idle";
  const startupReady = startup === "ready";
  const stopping = capture === "stopping";
  const recording = capture === "recording";
  return {
    showProductNavigation: preview,
    canStartMeeting: preview && startupReady
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
      fallbackCopy: "No retained words or automatic note can be opened right now. Reopen Meetings and try again.",
      canOpenTranscript: false,
    };
  }
  if (response?.state !== "note" && !transcriptAvailable) {
    return {
      kind: "unavailable",
      title: "Meeting unavailable.",
      lede: "This retained meeting could not be reopened. Its current transcript, note, and recording facts are unavailable in this view.",
      fallbackTitle: "Meeting unavailable",
      fallbackCopy: "Reopen Meetings and try again.",
      canOpenTranscript: false,
    };
  }
  if (response?.state === "transcript-only" || response?.state === "summary-failed") {
    return {
      kind: "transcript-only",
      title: "Note and transcript.",
      lede: "A supported note is a reading aid. Every claim opens the exact retained transcript words behind it.",
      fallbackTitle: "Transcript only",
      fallbackCopy: "No supported automatic note is available for this meeting. The retained transcript remains the source of record.",
      canOpenTranscript: transcriptAvailable,
    };
  }
  return {
    kind: "note",
    title: "Note and transcript.",
    lede: "A supported note is a reading aid. Every claim opens the exact retained transcript words behind it.",
    fallbackTitle: "Transcript only",
    fallbackCopy: "No supported automatic note is available for this meeting. The retained transcript remains the source of record.",
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
    && snapshot?.preview === true
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

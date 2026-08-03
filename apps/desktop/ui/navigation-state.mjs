export const PRODUCT_ROOT_SCREENS = Object.freeze([
  "find-screen",
  "meetings-screen",
  "promises-screen",
]);

export function rootForDestination(destination, currentRoot = "find-screen") {
  if (PRODUCT_ROOT_SCREENS.includes(destination)) return destination;
  return PRODUCT_ROOT_SCREENS.includes(currentRoot) ? currentRoot : "find-screen";
}

export function restoredScrollPosition(storedPosition, reset = false) {
  if (reset || !Number.isFinite(storedPosition) || storedPosition < 0) return 0;
  return storedPosition;
}

export function rowForMeetingId(snapshot, meetingId) {
  if (!meetingId || !Array.isArray(snapshot?.rows)) return null;
  return snapshot.rows.find((row) => row?.meetingId === meetingId) || null;
}

export function transcriptReturnRoute(origin, meetingId, claimOrdinal = null) {
  if (origin === "meeting-detail" && meetingId) {
    return {
      destination: "meeting-detail",
      meetingId,
      claimOrdinal: Number.isInteger(claimOrdinal) ? claimOrdinal : null,
    };
  }
  return { destination: "product-root", meetingId: null, claimOrdinal: null };
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
  if (response?.state !== "note" && !transcriptAvailable) {
    return {
      kind: "transcript-unavailable",
      title: "Meeting details.",
      lede: "This meeting’s retained status and recording information are available. Its transcript is not available from this view.",
      fallbackTitle: "Transcript unavailable",
      fallbackCopy: "No retained words or automatic note can be opened right now. Reopen Meetings and try again.",
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

export async function refreshFindGeneration(query, actions) {
  actions.invalidateResults();
  await actions.snapshot();
  if (!query) return null;
  const response = await actions.search(query);
  actions.render(response);
  return response;
}

export async function prepareConsentTransition(capture, actions) {
  if (capture === "idle") return true;
  if (capture !== "transcript-ready") return false;
  await actions.dismiss();
  actions.clearPriorAttempt();
  const snapshot = await actions.refresh();
  return snapshot?.capture === "idle";
}

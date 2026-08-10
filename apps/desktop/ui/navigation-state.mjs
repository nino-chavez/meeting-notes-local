export const PRODUCT_ROOT_SCREENS = Object.freeze([
  "find-screen",
  "meetings-screen",
  "promises-screen",
]);

export function workflowScreenForSnapshot(snapshot, currentScreen = "meetings-screen") {
  const startup = snapshot?.startup || "diagnostic-written";
  const capture = snapshot?.capture || "idle";
  if (startup !== "ready") return "startup-screen";
  if (capture === "idle") {
    return currentScreen === "idle-screen" ? "idle-screen" : "meetings-screen";
  }
  return {
    arming: "arming-screen",
    recording: "recording-screen",
    stopping: "recording-screen",
    captured: "processing-screen",
    transcribing: "processing-screen",
    "transcript-ready": snapshot?.meeting_id ? "meeting-detail-screen" : "transcript-screen",
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
  currentScreen = "meetings-screen",
} = {}) {
  const capture = snapshot?.capture || "idle";
  const startup = snapshot?.startup || "diagnostic-written";
  const actions = mutableActionPolicy(snapshot, { stopPending });
  const workflow = workflowReturnPolicy(snapshot);
  const recordActionScreens = [
    "find-screen",
    "meetings-screen",
    "promises-screen",
    "meeting-detail-screen",
    "library-transcript-screen",
    "profile-screen",
    "transcript-screen",
  ];
  const showFinishedRecordAction = capture === "transcript-ready"
    && recordActionScreens.includes(currentScreen);
  return {
    showProductNavigation: actions.showProductNavigation && startup === "ready",
    // A completed attempt is already retained in Meetings. Once its transcript
    // has been handed into the product, repeating "View transcript" as the
    // global primary action is redundant and can even point at the record the
    // operator is already reading. `canStartMeeting` admits transcript-ready,
    // and openStartMeeting dismisses that finished attempt before consent, so
    // the useful next action is to record another meeting. The transcript stays
    // reachable from Meetings and the transcript-ready status control.
    showStart: actions.canStartMeeting
      && ((capture === "idle" && recordActionScreens.includes(currentScreen))
        || showFinishedRecordAction),
    startLabel: showFinishedRecordAction ? "Record another meeting" : "Record a meeting",
    showStop: actions.showStop,
    stopDisabled: actions.stopDisabled,
    stopLabel: actions.stopLabel,
    showWorkflowReturn: !workflowOwnsRoute && workflow.show && !showFinishedRecordAction,
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

export function quickControlPresentation(snapshot) {
  const startup = snapshot?.startup || "diagnostic-written";
  const capture = snapshot?.capture || "idle";
  if (startup !== "ready") {
    return {
      state: "error",
      triggerLabel: "Needs attention",
      title: "Recording unavailable",
      detail: "Open Yawn to review the local startup issue.",
      primaryLabel: "View issue",
      secondaryLabel: "",
    };
  }
  if (capture === "idle") {
    return {
      state: "idle",
      triggerLabel: "Ready",
      title: "Ready to record",
      detail: "Nothing is recording. Every attempt starts with consent and retention review.",
      primaryLabel: "Record a meeting",
      secondaryLabel: "",
    };
  }
  if (capture === "arming") {
    return {
      state: "preparing",
      triggerLabel: "Preparing",
      title: "Preparing both channels",
      detail: "Nothing is recording yet. Capture starts only after both channels are ready.",
      primaryLabel: "View preparation",
      secondaryLabel: "",
    };
  }
  if (capture === "recording") {
    const degraded = snapshot?.degraded === true;
    return {
      state: degraded ? "degraded" : "recording",
      triggerLabel: degraded ? "Recording issue" : "Recording",
      title: degraded ? "Recording with one channel at risk" : "Recording",
      detail: degraded
        ? "Recording continues. One local audio channel needs attention."
        : "Microphone and system audio are both active on this Mac.",
      primaryLabel: "View recording",
      secondaryLabel: "Stop recording",
    };
  }
  if (capture === "stopping") {
    return {
      state: "stopping",
      triggerLabel: "Stopping",
      title: "Securing the recording",
      detail: "Both local audio files are being closed before transcription begins.",
      primaryLabel: "View recording",
      secondaryLabel: "",
    };
  }
  if (capture === "captured" || capture === "transcribing") {
    return {
      state: "processing",
      triggerLabel: "Processing",
      title: "Transcribing on this Mac",
      detail: "The recording has stopped. You may use the rest of Yawn while the transcript is prepared.",
      primaryLabel: "View progress",
      secondaryLabel: "",
    };
  }
  if (capture === "transcript-ready") {
    return {
      state: "result",
      triggerLabel: "Transcript ready",
      title: "Transcript ready",
      detail: "The retained transcript is ready to review on this Mac.",
      primaryLabel: "View transcript",
      secondaryLabel: "Record another",
    };
  }
  return {
    state: "error",
    triggerLabel: "Needs attention",
    title: "Capture needs attention",
    detail: "Open Yawn to review what was retained and what did not complete.",
    primaryLabel: "View issue",
    secondaryLabel: "",
  };
}

export function commandMenuPresentation(snapshot) {
  const capture = snapshot?.capture || "idle";
  const workflow = quickControlPresentation(snapshot);
  const commands = [
    {
      id: "meetings",
      label: "Meetings",
      detail: "Open the local library with the newest note beside it",
      shortcut: "⌘1",
      action: "meetings",
    },
    {
      id: "ask",
      label: "Ask",
      detail: "Search retained transcripts on this Mac",
      shortcut: "⌘2",
      action: "ask",
    },
    {
      id: "actions",
      label: "Actions",
      detail: "Review proposed follow-ups · planned shell",
      shortcut: "⌘3",
      action: "actions",
      planned: true,
    },
    {
      id: "settings",
      label: "Settings",
      detail: "Capture, privacy, and voice profile",
      shortcut: "⌘,",
      action: "settings",
    },
    {
      id: "desktop",
      label: "Desktop behavior",
      detail: "Window, menubar, notifications, and accessibility",
      shortcut: "",
      action: "desktop",
    },
    {
      id: "setup",
      label: "Preview first-run setup",
      detail: "Walk permission and recovery states · synthetic shell",
      shortcut: "",
      action: "setup",
    },
    {
      id: "states",
      label: "Preview system states",
      detail: "Review loading, empty, failure, recovery, and repair",
      shortcut: "",
      action: "states",
    },
    {
      id: "help",
      label: "Help and diagnostics",
      detail: "Recording help, privacy, diagnostics, and manual updates",
      shortcut: "",
      action: "help",
    },
    {
      id: "workflow",
      label: workflow.primaryLabel,
      detail: capture === "idle"
        ? "Open consent and retention review before recording"
        : workflow.detail,
      shortcut: "",
      action: capture === "idle" ? "start" : "workflow",
    },
  ];
  if (capture === "recording") {
    commands.push({
      id: "stop",
      label: "Stop recording",
      detail: "End capture and begin local transcription",
      shortcut: "",
      action: "stop",
    });
  }
  return commands;
}

export function helpTopicPresentation(topicId) {
  const topics = {
    overview: {
      id: "overview",
      context: "Help",
      title: "Find the right next step.",
      lede: "Choose the problem that matches what you can see. Yawn keeps recovery steps specific so a permission refusal is never treated like a broken installation.",
      facts: [
        ["Cannot record", "Check both permissions", "Microphone and system audio are required"],
        ["Meeting looks incomplete", "Review Meetings", "Interrupted and failed work stays labelled"],
        ["Installation will not start", "Use the repair path", "Existing meetings stay separate from bundled components"],
      ],
      primaryLabel: "Check recording setup",
      primaryAction: "setup",
    },
    recording: {
      id: "recording",
      context: "Record a meeting",
      title: "Start with consent, headphones, and two audio channels.",
      lede: "Every recording begins with a review. Yawn does not detect meetings automatically in the current product boundary.",
      facts: [
        ["Consent", "Confirm it yourself", "The app cannot decide consent or recording law"],
        ["Headphones", "Required in Preview", "Speaker playback can make the transcript incomplete"],
        ["Retention", "Choose for each meeting", "A global default is not built"],
      ],
      primaryLabel: "Prepare a recording",
      primaryAction: "start",
    },
    permissions: {
      id: "permissions",
      context: "Permission problems",
      title: "A refusal and a failed check need different fixes.",
      lede: "If macOS already refused access, change it in Privacy & Security. If the check itself cannot run, retry once and then reinstall the signed app.",
      facts: [
        ["Microphone", "Privacy & Security → Microphone", "Switch Yawn on, then check again"],
        ["System audio", "Privacy & Security → Screen & System Audio Recording", "macOS reports access only when capture is attempted"],
        ["Check unavailable", "Possible incomplete installation", "This is not the same as saying no"],
      ],
      primaryLabel: "Preview setup recovery",
      primaryAction: "setup",
    },
    privacy: {
      id: "privacy",
      context: "Privacy and retention",
      title: "Meeting data stays on this Mac.",
      lede: "Yawn has no account or upload path. Recording audio and its retained transcript have separate lifetimes.",
      facts: [
        ["Recording audio", "Deleted on its deadline", "If Yawn is closed, deletion runs when it next opens"],
        ["Transcript and note", "Remain after audio deletion", "Playback and retranscription are then unavailable"],
        ["Voice profile", "Stored separately", "Resetting it does not delete meetings"],
      ],
      primaryLabel: "Open privacy settings",
      primaryAction: "privacy",
    },
    diagnostics: {
      id: "diagnostics",
      context: "Private diagnostics",
      title: "A diagnostic explains a local failure without attaching a meeting.",
      lede: "The current writer stores an error code and redacted detail in an owner-only file on this Mac. This browser shell cannot inspect or reveal that file.",
      facts: [
        ["Included", "Error code and redacted detail", "Each file is capped at 16 KB"],
        ["Redacted", "Paths, email-like tokens, and environment-style values", "The file is created with owner-only permissions"],
        ["Not attached", "Audio, transcript files, or operator notes", "No diagnostic upload or sharing action exists"],
      ],
      primaryLabel: "Preview installation repair",
      primaryAction: "states",
    },
    updates: {
      id: "updates",
      context: "Updates",
      title: "Updates are manual for the first release.",
      lede: "Yawn has no automatic updater. A newer signed and notarized disk image is installed by dragging Yawn to Applications and replacing the current copy.",
      facts: [
        ["Check for updates", "Unavailable", "This build does not contact an update service"],
        ["Install", "Replace the app manually", "Do not delete local app data or meetings"],
        ["Upgrade safety", "Not yet release-proven", "A second version still needs migration-failure and rollback proof"],
      ],
      primaryLabel: "View build details",
      primaryAction: "about",
    },
  };
  return topics[topicId] || topics.overview;
}

export function shellStatePresentation(stateId) {
  const states = {
    loading: {
      id: "loading",
      context: "Opening Yawn",
      tone: "loading",
      title: "Checking this installation.",
      lede: "The window is ready. Recording controls stay unavailable until the bundled local components answer.",
      facts: [
        ["Application window", "Ready", "Safe controls are visible"],
        ["Bundled files", "Checking", "No meeting can start yet"],
        ["Local worker", "Waiting", "Nothing has been sent anywhere"],
      ],
      primaryLabel: "Open Meetings",
      primaryAction: "meetings",
    },
    empty: {
      id: "empty",
      context: "Meetings",
      tone: "empty",
      title: "No retained meetings yet.",
      lede: "Finish a recording to create the first local meeting. An empty library is not a search failure.",
      facts: [
        ["Meeting data", "Nothing stored", "No recording or transcript was opened"],
        ["Search", "Nothing to search", "Search becomes useful after the first transcript"],
      ],
      primaryLabel: "Record a meeting",
      primaryAction: "start",
    },
    failure: {
      id: "failure",
      context: "Local processing",
      tone: "attention",
      title: "A transcript was not created.",
      lede: "The recording stopped safely, but local transcription did not finish. Yawn does not present this meeting as complete.",
      facts: [
        ["Recording audio", "Retained for recovery", "Still follows its original retention choice"],
        ["Operator note", "Retained", "Your typed note remains separate"],
        ["Transcript", "Unavailable", "No transcript or automatic note is claimed"],
      ],
      primaryLabel: "Review Meetings",
      primaryAction: "meetings",
    },
    recovery: {
      id: "recovery",
      context: "Recovered after interruption",
      tone: "recovery",
      title: "Part of a recording was recovered.",
      lede: "Yawn found local capture evidence during startup and kept the meeting marked interrupted rather than complete.",
      facts: [
        ["Completion", "Interrupted", "The meeting is never presented as uninterrupted"],
        ["Recovered audio", "Kept locally", "It stays under the original retention choice"],
        ["Transcript", "Not claimed", "Local processing must succeed before one appears"],
      ],
      primaryLabel: "Review Meetings",
      primaryAction: "meetings",
    },
    repair: {
      id: "repair",
      context: "Installation needs repair",
      tone: "attention",
      title: "This build cannot start a meeting.",
      lede: "The window opened safely, stopped partial local work, and saved a private diagnostic on this Mac.",
      facts: [
        ["Capture", "Unavailable", "No degraded recording was started"],
        ["Retained meetings", "Still readable", "Existing local evidence remains separate"],
        ["Diagnostic", "Saved locally", "It contains no meeting transcript in this preview"],
      ],
      primaryLabel: "Check again",
      primaryAction: "loading",
    },
  };
  return states[stateId] || states.loading;
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

export function rootForDestination(destination, currentRoot = "meetings-screen") {
  if (PRODUCT_ROOT_SCREENS.includes(destination)) return destination;
  return PRODUCT_ROOT_SCREENS.includes(currentRoot) ? currentRoot : "meetings-screen";
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
  detailTab = "note",
  findFocus = "exact",
} = {}) {
  if (origin === "meeting-detail" && meetingId) {
    return {
      destination: "meeting-detail",
      meetingId,
      claim: displayedClaimIdentity(claim),
      detailScrollTop: normalizedScrollPosition(detailScrollTop),
      detailTab: ["note", "transcript", "actions", "evidence", "details"].includes(detailTab)
        ? detailTab
        : "note",
    };
  }
  if (origin === "find") {
    return {
      destination: "find",
      meetingId: null,
      claim: null,
      detailScrollTop: 0,
      detailTab: "note",
      // Exact search can rebuild its local result list on return. Meaning
      // search must never invoke the worker merely because someone pressed
      // Back, so the source field is restored instead.
      findFocus: findFocus === "meaning" ? "meaning" : "exact",
    };
  }
  return {
    destination: "product-root",
    meetingId: null,
    claim: null,
    detailScrollTop: 0,
    detailTab: "note",
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

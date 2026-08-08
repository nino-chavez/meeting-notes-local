import {
  createSingleFlight,
  createWriteQueue,
  acceptAuthoritativeSnapshot,
  isDismissalReadySnapshot,
  settleDismissal,
  createFreshSnapshotOperation,
  createLatestRequestGate,
  createRouteOwnershipGate,
  createTransitionGate,
  changedStatusText,
  firstRunDeniedPermissionName,
  liveNoteStatus,
  firstRunStepFor,
  enrollmentRecorderPresentation,
  transcriptPlainText,
  operatingPointPresentation,
  captureChannelPresentation,
  connectionUncertaintyStatus,
  headerActionPolicy,
  headerStatusPresentation,
  mutableActionPolicy,
  prepareConsentTransition,
  retentionDeadlineMessage,
  refreshFindGeneration,
  restoredScrollPosition,
  rootForDestination,
  meetingDetailPresentation,
  rowForMeetingId,
  sameDisplayedClaim,
  transitionOwnsRoute,
  transcriptReturnRoute,
  resolvedScreenForSnapshot,
} from "./navigation-state.mjs";

const invoke = window.__TAURI__?.core?.invoke;

const screens = new Map(
  [...document.querySelectorAll(".screen")].map((screen) => [screen.id, screen]),
);
const headerState = document.querySelector("#header-state");
const headerStatusDot = document.querySelector("#header-status-dot");
const releaseBadge = document.querySelector("#release-badge");
const meetingLabel = document.querySelector("#meeting-id");
const mainRegion = document.querySelector("main");
const startForm = document.querySelector("#start-form");
const startButton = document.querySelector("#start-button");
const startError = document.querySelector("#start-error");
const stopButton = document.querySelector("#stop-button");
const stopError = document.querySelector("#stop-error");
const retryStartup = document.querySelector("#retry-startup");
const productNav = document.querySelector("#product-nav");
const findLink = document.querySelector("#find-link");
const meetingsLink = document.querySelector("#meetings-link");
const promisesLink = document.querySelector("#promises-link");
const profileLink = document.querySelector("#profile-link");
const workflowReturn = document.querySelector("#workflow-return");
const startMeetingAction = document.querySelector("#start-meeting-action");
const newMeetingButton = document.querySelector("#new-meeting");
const recoverButton = document.querySelector("#recover-button");
const startTransitionError = document.querySelector("#start-transition-error");
const profileLede = document.querySelector("#profile-lede");
const profileStatusTitle = document.querySelector("#profile-status-title");
const profileStatusCopy = document.querySelector("#profile-status-copy");
const profileFootnote = document.querySelector("#profile-footnote");
const profileSetup = document.querySelector("#profile-setup");
const profileNextStep = document.querySelector("#profile-next-step");
const profileEnrollmentGates = document.querySelector("#profile-enrollment-gates");
const profileRecorderEntry = document.querySelector("#profile-recorder-entry");
const profileSittings = document.querySelector("#profile-sittings");
const sittingForm = document.querySelector("#sitting-form");
const sittingSourceClass = document.querySelector("#sitting-source-class");
const sittingStart = document.querySelector("#sitting-start");
const sittingActive = document.querySelector("#sitting-active");
const sittingStop = document.querySelector("#sitting-stop");
const sittingError = document.querySelector("#sitting-error");
const sittingOutcome = document.querySelector("#sitting-outcome");
const operatingPointsSection = document.querySelector("#profile-operating-points");
const operatingPointsForm = document.querySelector("#operating-points-form");
const operatingPointsRows = document.querySelector("#operating-points-rows");
const operatingPointsError = document.querySelector("#operating-points-error");
const operatingPointsLoad = document.querySelector("#operating-points-load");
const operatingPointsBuild = document.querySelector("#operating-points-build");
const profileResetConfirmation = document.querySelector("#profile-reset-confirmation");
const profileResetConfirm = document.querySelector("#profile-reset-confirm");
const profileResetCancel = document.querySelector("#profile-reset-cancel");
const profileResetStatus = document.querySelector("#profile-reset-status");
const micChannel = document.querySelector("#mic-channel");
const systemChannel = document.querySelector("#system-channel");
const libraryList = document.querySelector("#library-list");
const libraryNotice = document.querySelector("#library-notice");
// The meetings screen's own status line. `library-notice` belongs to Find,
// and a rename refusal shown there is a refusal the operator never sees.
const libraryOrganizationNotice = document.querySelector("#library-organization-notice");
const filterFolder = document.querySelector("#filter-folder");
const filterName = document.querySelector("#filter-name");
const filterFrom = document.querySelector("#filter-from");
const filterTo = document.querySelector("#filter-to");
const filterClear = document.querySelector("#filter-clear");
const filterNewFolder = document.querySelector("#filter-new-folder");
// What the operator has narrowed to. Held here rather than read back off the
// controls, because the snapshot has to be requested with the same filter the
// controls show, and re-deriving it in two places is how those drift apart.
let libraryFilter = {};
let libraryMetadataRevision = null;
const librarySearch = document.querySelector("#library-search");
const librarySearchQuery = document.querySelector("#library-search-query");
const librarySearchSubmit = librarySearch.querySelector("button[type=\"submit\"]");
const librarySearchResults = document.querySelector("#library-search-results");
const findStart = document.querySelector("#find-start");
const corpusSearch = document.querySelector("#corpus-search");
const corpusSearchQuestion = document.querySelector("#corpus-search-question");
const corpusSearchSubmit = corpusSearch.querySelector("button[type=\"submit\"]");
const corpusSearchResults = document.querySelector("#corpus-search-results");
const corpusNotice = document.querySelector("#corpus-notice");
const corpusCoverage = document.querySelector("#corpus-coverage");
const corpusCoverageCopy = document.querySelector("#corpus-coverage-copy");
const corpusPrepare = document.querySelector("#corpus-prepare");
const meetingDetailState = document.querySelector("#meeting-detail-state");
const meetingDetailTitle = document.querySelector("#meeting-detail-title");
const meetingDetailLede = document.querySelector("#meeting-detail-lede");
const meetingClaimList = document.querySelector("#meeting-claim-list");
const meetingNoNote = document.querySelector("#meeting-no-note");
const meetingNoNoteTitle = document.querySelector("#meeting-no-note-title");
const meetingNoNoteCopy = document.querySelector("#meeting-no-note-copy");
const meetingOpenTranscript = document.querySelector("#meeting-open-transcript");
const meetingRetention = document.querySelector("#meeting-retention");
const meetingRetentionTitle = document.querySelector("#meeting-retention-title");
const meetingRetentionPolicy = document.querySelector("#meeting-retention-policy");
const meetingRetentionSize = document.querySelector("#meeting-retention-size");
const meetingRetentionConsequence = document.querySelector("#meeting-retention-consequence");
const recordingDeleteAction = document.querySelector("#recording-delete-action");
const recordingDeleteReview = document.querySelector("#recording-delete-review");
const recordingDeleteConfirmation = document.querySelector("#recording-delete-confirmation");
const recordingDeleteCancel = document.querySelector("#recording-delete-cancel");
const recordingDeleteConfirm = document.querySelector("#recording-delete-confirm");
const recordingDeleteStatus = document.querySelector("#recording-delete-status");
const meetingDeleteAction = document.querySelector("#meeting-delete-action");
const meetingDeleteReview = document.querySelector("#meeting-delete-review");
const meetingDeleteConfirmation = document.querySelector("#meeting-delete-confirmation");
const meetingDeleteCancel = document.querySelector("#meeting-delete-cancel");
const meetingDeleteConfirm = document.querySelector("#meeting-delete-confirm");
const meetingDeleteStatus = document.querySelector("#meeting-delete-status");
const retention = document.querySelector("#retention-days");
const checks = [
  document.querySelector("#consent-check"),
  document.querySelector("#headphones-check"),
  document.querySelector("#room-check"),
];

let lastSnapshot = null;
let pollTimer = null;
let startedAt = null;
let elapsedTimer = null;
let meetingAudioDeletionHandle = "";
let meetingDeletionHandle = "";
let currentScreen = "startup-screen";
let productRootScreen = "find-screen";
let transcriptReturnContext = null;
let routeRevision = 0;
let findNavigationBusy = false;
let findRefreshBusyCount = 0;
let handleNavigationBusy = false;
let workflowOwnsRoute = true;
let stopCommandPending = false;
let stopCommandFailed = false;
let announcedHeaderState = headerState.textContent;
const screenScrollPositions = new Map();
const libraryInitialization = createSingleFlight(
  // The filter travels with the request. Rust applies it and reports both
  // counts, so the shell never computes "showing N of M" from a list it
  // already trimmed itself.
  () => invoke("preview_library_snapshot", { filter: libraryFilter }),
);
const findRefreshOperation = createSingleFlight(performFindRefresh);
const handleTransitionGate = createTransitionGate();
const snapshotRequestGate = createLatestRequestGate();
const routeOwnership = createRouteOwnershipGate();
const REFRESH_SUPERSEDED = Symbol("refresh-superseded");
const refreshCurrentOperation = createFreshSnapshotOperation(refresh, REFRESH_SUPERSEDED);
const dismissMeetingOperation = createSingleFlight(async () => {
  const snapshot = await invoke("dismiss_meeting");
  return acceptCommandSnapshot(snapshot);
});

function showScreen(id, { resetScroll = false, focus = true } = {}) {
  const destination = screens.get(id);
  if (!destination) return;
  const routeChanged = currentScreen !== id;
  if (routeChanged) screenScrollPositions.set(currentScreen, mainRegion.scrollTop);
  if (routeChanged) routeRevision += 1;
  currentScreen = id;
  productRootScreen = rootForDestination(id, productRootScreen);
  document.documentElement.dataset.screen = id;
  for (const [screenId, screen] of screens) {
    screen.classList.toggle("active", screenId === id);
  }
  if (resetScroll) screenScrollPositions.delete(id);
  mainRegion.scrollTop = restoredScrollPosition(screenScrollPositions.get(id), resetScroll);
  syncProductNavigation();
  if (lastSnapshot) renderCaptureAction(lastSnapshot);
  if ((routeChanged || resetScroll) && focus) {
    const heading = destination.querySelector("h1, h2");
    if (heading) {
      heading.tabIndex = -1;
      heading.focus({ preventScroll: true });
    } else {
      mainRegion.focus({ preventScroll: true });
    }
  }
}

function syncProductNavigation() {
  const settingsActive = currentScreen === "profile-screen";
  const directRoot = ["find-screen", "meetings-screen", "promises-screen"].includes(currentScreen)
    ? currentScreen
    : productRootScreen;
  for (const [link, destination] of [
    [findLink, "find-screen"],
    [meetingsLink, "meetings-screen"],
    [promisesLink, "promises-screen"],
  ]) {
    if (!settingsActive && directRoot === destination) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  }
  if (settingsActive) profileLink.setAttribute("aria-current", "page");
  else profileLink.removeAttribute("aria-current");
}

function syncNavigationBusy() {
  librarySearchSubmit.disabled = findNavigationBusy || handleNavigationBusy;
}

function beginHandleTransition(kind, control = null) {
  const ticket = handleTransitionGate.enter(kind, {
    screen: currentScreen,
    revision: routeRevision,
  });
  if (!ticket) return null;
  handleNavigationBusy = true;
  syncNavigationBusy();
  if (control) control.disabled = true;
  return { ticket, control };
}

function currentTransitionOwnsRoute(transition, screen = transition?.ticket?.route?.screen) {
  return Boolean(transition
    && transitionOwnsRoute(handleTransitionGate, transition.ticket, {
      screen,
      revision: routeRevision,
    }));
}

function finishHandleTransition(transition) {
  if (!transition) return;
  if (transition.control) transition.control.disabled = false;
  handleTransitionGate.release(transition.ticket);
  handleNavigationBusy = Boolean(handleTransitionGate.active());
  syncNavigationBusy();
}

function selectProductScreen(id, options = {}) {
  workflowOwnsRoute = false;
  routeOwnership.advance();
  if (currentScreen === id) routeRevision += 1;
  showScreen(id, options);
}

function beginWorkflowRoute() {
  workflowOwnsRoute = true;
  return routeOwnership.advance();
}

function workflowRouteIsCurrent(token) {
  return workflowOwnsRoute && routeOwnership.owns(token);
}

function claimExplicitRoute() {
  workflowOwnsRoute = false;
  return routeOwnership.advance();
}

function setHeaderState(text) {
  const next = changedStatusText(announcedHeaderState, text);
  if (next === null) return;
  announcedHeaderState = next;
  headerState.textContent = next;
}

function scheduleSnapshotPoll(snapshot) {
  const active = ["arming", "recording", "stopping", "captured", "transcribing"].includes(snapshot.capture);
  schedulePoll(active ? 400 : 1500);
}

function acceptCommandSnapshot(snapshot) {
  return acceptAuthoritativeSnapshot(snapshot, {
    invalidateSnapshotRequests: () => snapshotRequestGate.invalidate(),
    render,
    schedule: scheduleSnapshotPoll,
  });
}

function showWorkflowScreen(snapshot, options = {}) {
  const destination = resolvedScreenForSnapshot(snapshot, currentScreen, workflowOwnsRoute);
  if (destination !== currentScreen) showScreen(destination, options);
  return destination;
}

function renderCaptureAction(snapshot) {
  if ((snapshot?.capture || "idle") !== "recording") {
    stopCommandPending = false;
    stopCommandFailed = false;
  }
  const policy = headerActionPolicy(snapshot, {
    stopPending: stopCommandPending,
    workflowOwnsRoute,
    currentScreen,
  });
  productNav.hidden = !policy.showProductNavigation;
  profileLink.hidden = !policy.showProductNavigation;
  startMeetingAction.hidden = !policy.showStart;
  stopButton.hidden = !policy.showStop;
  stopButton.disabled = policy.stopDisabled;
  stopButton.textContent = policy.stopLabel;
  workflowReturn.hidden = !policy.showWorkflowReturn;
  workflowReturn.textContent = policy.workflowReturnLabel;
  workflowReturn.dataset.destination = policy.workflowDestination;
  return policy;
}

function renderChannelState(target, state) {
  const presentation = captureChannelPresentation(state);
  target.dataset.state = presentation.state;
  target.querySelector("small").textContent = presentation.label;
}

function renderConnectionUncertainty() {
  document.documentElement.dataset.connectionState = "uncertain";
  headerStatusDot.dataset.state = "attention";
  setHeaderState(connectionUncertaintyStatus(lastSnapshot?.capture, {
    stopFailed: stopCommandFailed,
  }));
}

async function initializeLibraryReader() {
  if (!invoke) throw new Error("The local application bridge is unavailable.");
  return libraryInitialization.run();
}

function initializeFindInBackground() {
  if (currentScreen === "find-screen") void refreshFindView();
}

function invalidateLibraryHandles() {
  libraryList.replaceChildren();
  librarySearchResults.replaceChildren();
  // Meaning results hold transcript handles minted against the same projection
  // as every other row here, so they die at the same moment. Left standing they
  // would be buttons that look live and open nothing.
  corpusSearchResults.replaceChildren();
  meetingClaimList.replaceChildren();
  meetingNoNote.hidden = true;
  document.querySelector("#meeting-detail-transcript-handle").value = "";
  meetingAudioDeletionHandle = "";
  meetingDeletionHandle = "";
  recordingDeleteAction.hidden = true;
  meetingDeleteAction.hidden = true;
  closeRecordingDeleteReview();
  closeMeetingDeleteReview();
}

function setError(element, message) {
  element.textContent = message || "The operation could not complete.";
  element.hidden = false;
}

function clearError(element) {
  element.textContent = "";
  element.hidden = true;
}

function message(target, text, state = "") {
  target.textContent = text;
  target.dataset.state = state;
}

function startIsAllowed() {
  return mutableActionPolicy(lastSnapshot).canSubmitStart
    && lastSnapshot?.retention_operational === true
    && checks.every((check) => check.checked)
    && retention.value !== "";
}

function updateStartButton() {
  startButton.disabled = !startIsAllowed() || startButton.dataset.busy === "true";
}

function formatElapsed(seconds) {
  const safe = Math.max(0, Math.floor(seconds));
  return `${String(Math.floor(safe / 60)).padStart(2, "0")}:${String(safe % 60).padStart(2, "0")}`;
}

function beginElapsed(epochSeconds) {
  startedAt = Number(epochSeconds) * 1000;
  const render = () => {
    const elapsed = startedAt ? (Date.now() - startedAt) / 1000 : 0;
    document.querySelector("#elapsed-time").textContent = formatElapsed(elapsed);
  };
  render();
  if (!elapsedTimer) elapsedTimer = window.setInterval(render, 1000);
}

function endElapsed() {
  if (elapsedTimer) window.clearInterval(elapsedTimer);
  elapsedTimer = null;
  startedAt = null;
}

let renderedAttemptTurns = [];
let renderedLibraryTurns = [];

// The frozen restore shape needs the meeting and the digest the projection was
// verified against. Both come from the snapshot and are held here, never in the
// DOM — the same rule the Library route follows.
let attemptTranscriptRestore = null;

function renderTranscript(snapshot) {
  // A relaunch reaches this screen without ever having passed through recording,
  // so the note may not be loaded yet. Loading is idempotent per meeting, so this
  // resolves immediately in the ordinary case.
  void loadLiveNoteFor(snapshot.meeting_id).then(renderTranscriptNote);
  renderedAttemptTurns = Array.isArray(snapshot.turns) ? snapshot.turns : [];
  attemptTranscriptRestore =
    snapshot.meeting_id && snapshot.current_transcript_sha256
      ? {
          meetingId: snapshot.meeting_id,
          currentTranscriptSha256: snapshot.current_transcript_sha256,
        }
      : null;
  renderTurns(
    document.querySelector("#transcript-turns"),
    document.querySelector("#transcript-warning"),
    snapshot.turns,
    snapshot.warnings,
    null,
    // Restoring belongs here and not only in Meetings. The gate's worst failure
    // is a colleague beside the operator being cut from a record of a meeting
    // nobody can hold again, and the remedy is worth less the longer it waits.
    // Sending the operator to another screen to reach it was the delay.
    attemptTranscriptRestore ? restoreAttemptWithheldTurnAction : null,
  );
}

async function restoreAttemptWithheldTurnAction(turn, control) {
  if (!invoke || !attemptTranscriptRestore) return;
  const context = attemptTranscriptRestore;
  const restoreError = document.querySelector("#transcript-restore-error");
  restoreError.hidden = true;
  restoreError.textContent = "";
  control.disabled = true;
  control.textContent = "Restoring…";
  try {
    await invoke("restore_withheld_turn", {
      meetingId: context.meetingId,
      sourceTranscriptSha256: context.currentTranscriptSha256,
      sourceTurnIndex: turn.sourceTurnIndex,
    });
  } catch (error) {
    if (currentScreen !== "transcript-screen") return;
    control.disabled = false;
    control.textContent = "Restore this turn";
    restoreError.textContent =
      typeof error === "string" ? error : "The turn was not restored. Try again.";
    restoreError.hidden = false;
    return;
  }
  // Past this line the turn IS restored. A failure to redraw is a different
  // sentence from a failure to restore, and saying the first one here would tell
  // the operator to retry something that already succeeded.
  try {
    // A restoration publishes a new current transcript, so the projection on
    // screen — and the digest a second restore would have to name — are both
    // stale now. Rebuilding before the next poll is what keeps a second restore
    // from being refused as a changed source.
    await invoke("refresh_current_transcript");
  } catch {
    if (currentScreen !== "transcript-screen") return;
    restoreError.textContent =
      "The turn was restored. This view could not be refreshed — open the meeting from Meetings to read it.";
    restoreError.hidden = false;
    return;
  }
  await refreshCurrent();
}

async function copyTranscript(turns, control, status) {
  const text = transcriptPlainText(turns);
  if (!text) {
    status.textContent = "Nothing to copy.";
    return;
  }
  control.disabled = true;
  try {
    await navigator.clipboard.writeText(text);
    status.textContent = "Copied.";
  } catch {
    status.textContent = "Copy failed. Select the text instead.";
  } finally {
    control.disabled = false;
  }
}

function appendTurnText(target, text, locator = null) {
  if (!locator || !Number.isInteger(locator.start) || !Number.isInteger(locator.end)) {
    target.textContent = text || "";
    return;
  }
  const characters = Array.from(text || "");
  if (locator.start < 0 || locator.end <= locator.start || locator.end > characters.length) {
    target.textContent = text || "";
    return;
  }
  target.append(document.createTextNode(characters.slice(0, locator.start).join("")));
  const matched = document.createElement("mark");
  matched.className = "matched-locator";
  matched.textContent = characters.slice(locator.start, locator.end).join("");
  target.append(matched, document.createTextNode(characters.slice(locator.end).join("")));
}

function renderTurns(container, warning, turns, warnings, match = null, restore = null) {
  container.replaceChildren();
  const safeWarnings = Array.isArray(warnings) ? warnings : [];
  warning.hidden = safeWarnings.length === 0;
  // One paragraph each rather than one joined string. The gate can now say that
  // a person beside the operator is being removed from a record that cannot be
  // re-made, and that sentence arrives alongside a retention notice and a
  // segment count — joined into a single run of text it reads as boilerplate.
  // The producer orders them, most serious first.
  warning.replaceChildren(
    ...safeWarnings.map((text) => {
      const line = document.createElement("p");
      line.className = "warning-line";
      line.textContent = text;
      return line;
    }),
  );
  for (const turn of turns || []) {
    const row = document.createElement("section");
    row.className = "turn";
    if (turn.withheld) {
      row.classList.add("withheld-turn");
      const meta = document.createElement("div");
      meta.className = "turn-meta";
      const speaker = document.createElement("strong");
      speaker.textContent = "Withheld";
      const time = document.createElement("time");
      time.textContent = formatElapsed(turn.start || 0);
      meta.append(speaker, time);
      const note = document.createElement("p");
      note.className = "withheld-note";
      note.textContent = "A voice check withheld this turn's text.";
      row.append(meta, note);
      if (restore) {
        const action = document.createElement("button");
        action.type = "button";
        action.className = "secondary restore-turn";
        action.textContent = "Restore this turn";
        action.addEventListener("click", () => restore(turn, action));
        row.append(action);
      }
      container.append(row);
      continue;
    }
    const matchesTurn = Number.isInteger(match?.sourceTurnIndex)
      && turn.sourceTurnIndex === match.sourceTurnIndex;
    if (matchesTurn) {
      row.classList.add("matched-turn");
      row.dataset.sourceTurnIndex = String(match.sourceTurnIndex);
      row.tabIndex = -1;
      row.setAttribute("aria-label", `Exact transcript match in turn ${match.sourceTurnIndex + 1}`);
    }
    const meta = document.createElement("div");
    meta.className = "turn-meta";
    const speaker = document.createElement("strong");
    speaker.textContent = turn.speaker || "Unattributed";
    const time = document.createElement("time");
    time.textContent = formatElapsed(turn.start || 0);
    meta.append(speaker, time);
    const text = document.createElement("p");
    appendTurnText(text, turn.text, matchesTurn ? match : null);
    row.append(meta, text);
    container.append(row);
  }
  if (!container.children.length) {
    const empty = document.createElement("p");
    empty.className = "empty-transcript";
    empty.textContent = "No speech was detected in this capture.";
    container.append(empty);
  }
  if (Number.isInteger(match?.sourceTurnIndex)) {
    window.requestAnimationFrame(() => {
      const destination = container.querySelector(`[data-source-turn-index="${match.sourceTurnIndex}"]`);
      destination?.scrollIntoView({ block: "center" });
      destination?.focus({ preventScroll: true });
    });
  }
}

function formatMeetingTime(epochSeconds) {
  const value = Number(epochSeconds) * 1000;
  if (!Number.isFinite(value) || value <= 0) return "Retained meeting";
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function formatByteSize(bytes) {
  if (!Number.isInteger(bytes) || bytes < 0) return "Size unavailable";
  if (bytes < 1024) return `${bytes} bytes`;
  const units = ["KB", "MB", "GB", "TB"];
  let value = bytes;
  let unit = -1;
  do {
    value /= 1024;
    unit += 1;
  } while (value >= 1024 && unit < units.length - 1);
  return `${value.toFixed(value >= 10 || unit === 0 ? 0 : 1)} ${units[unit]} (${bytes.toLocaleString()} bytes)`;
}

function closeRecordingDeleteReview() {
  recordingDeleteConfirmation.hidden = true;
  recordingDeleteStatus.hidden = true;
  recordingDeleteStatus.textContent = "";
  recordingDeleteConfirm.disabled = false;
  recordingDeleteConfirm.textContent = "Permanently delete recording";
}

function closeMeetingDeleteReview() {
  meetingDeleteConfirmation.hidden = true;
  meetingDeleteStatus.hidden = true;
  meetingDeleteStatus.textContent = "";
  meetingDeleteConfirm.disabled = false;
  meetingDeleteConfirm.textContent = "Permanently delete meeting";
}

function renderAudioRetention(retention, deletionHandle = "") {
  meetingAudioDeletionHandle = "";
  recordingDeleteAction.hidden = true;
  closeRecordingDeleteReview();
  meetingRetention.hidden = !retention;
  if (!retention) return;
  const state = retention.state || "unavailable";
  const policy = retention.policy || "unknown";
  const deadline = retention.deadlineEpochSeconds;
  meetingRetention.dataset.state = state;
  meetingRetentionSize.hidden = true;
  if (state === "retained") {
    meetingRetentionTitle.textContent = "Recording retained";
    meetingRetentionPolicy.textContent = policy === "manual"
      ? "Kept until you delete the recording."
      : retentionDeadlineMessage(deadline);
    meetingRetentionSize.hidden = false;
    meetingRetentionSize.textContent = `Retained audio: ${formatByteSize(retention.retainedBytes)} across both recording channels.`;
    meetingRetentionConsequence.textContent = "The separate voice profile is unaffected by this meeting’s retention state.";
    if (deletionHandle) {
      meetingAudioDeletionHandle = deletionHandle;
      recordingDeleteAction.hidden = false;
    }
    return;
  }
  if (state === "released") {
    meetingRetentionTitle.textContent = "Recording deleted";
    meetingRetentionPolicy.textContent = retention.message || "Meeting audio was deleted.";
    meetingRetentionConsequence.textContent = "The transcript, note, and evidence remain. You can no longer listen to the recording, check this transcription against it, or transcribe it again. The separate voice profile is unaffected.";
    return;
  }
  if (state === "deleting") {
    meetingRetentionTitle.textContent = "Recording deletion in progress";
    meetingRetentionPolicy.textContent = retention.message || "Meeting audio deletion is already in progress.";
    meetingRetentionConsequence.textContent = "The transcript, note, evidence, and separate voice profile are not changed by this status.";
    return;
  }
  if (state === "not-recorded") {
    meetingRetentionTitle.textContent = "No recording retained";
    meetingRetentionPolicy.textContent = retention.message || "This meeting has no retained audio.";
    meetingRetentionConsequence.textContent = "The separate voice profile is unaffected.";
    return;
  }
  meetingRetentionTitle.textContent = "Recording retention needs attention";
  meetingRetentionPolicy.textContent = retention.message || "Audio retention details are unavailable. Return to Meetings and try again.";
  meetingRetentionConsequence.textContent = "No recording action is available from this Preview view.";
}

function renderLibrary(snapshot) {
  libraryMetadataRevision = Number.isInteger(snapshot.metadataRevision)
    ? snapshot.metadataRevision
    : null;
  renderFolderOptions(snapshot);
  // Shown only when something is narrowed. A permanently visible "Clear" on an
  // unfiltered list implies a filter that is not there.
  filterClear.hidden = !snapshot.filterActive;
  libraryList.replaceChildren();
  document.querySelector("#library-copy").textContent = snapshot.message || "Opening retained meetings on this Mac.";
  if (snapshot.state !== "populated" && snapshot.state !== "populated-incomplete") {
    const empty = document.createElement("p");
    empty.className = "library-empty";
    empty.textContent = snapshot.state === "empty"
      ? "No retained meetings yet. Finish a recording to see it here."
      : snapshot.state === "unavailable"
        ? "Meetings are not available yet. No retained meeting or transcript was opened."
        : "Some retained meetings could not be read. Try loading Meetings again.";
    libraryList.append(empty);
    return;
  }
  for (const row of snapshot.rows || []) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "library-row";
    button.dataset.meetingHandle = row.handle;
    button.dataset.meetingId = row.meetingId || "";
    // A meeting with no title is named by when it was recorded, which the row
    // already carries. Rust sends no second, UTC copy of that instant.
    const captured = formatMeetingTime(row.createdAtEpochSeconds);
    const labelSource = row.labelSource || "date";
    const labelText = row.label || captured;
    button.dataset.label = labelText;
    button.dataset.labelSource = labelSource;
    button.addEventListener("click", () => openMeetingDetail(
      row.handle,
      "meetings-screen",
      button,
    ));
    const summary = document.createElement("span");
    const label = document.createElement("strong");
    label.textContent = labelText;
    const notes = [];
    if (labelSource !== "date") notes.push(captured);
    // Said in the meeting, not written by the operator. Without this the row
    // reads as a title somebody chose.
    if (labelSource === "derived") notes.push("Opening line");
    if (!row.transcriptAvailable) notes.push("No transcript");
    const time = document.createElement("small");
    time.textContent = notes.join(" · ");
    time.hidden = notes.length === 0;
    summary.append(label, time);
    const action = document.createElement("span");
    action.textContent = row.transcriptAvailable ? "Open meeting" : "Open details";
    button.append(summary, action);
    libraryList.append(button);

    // Rename sits outside the row button rather than inside it: a button in a
    // button does not nest, and the whole row already means "open this".
    // A null revision means the record could not be read, and renaming is
    // withheld rather than attempted against a revision nobody knows.
    if (Number.isInteger(snapshot.metadataRevision)) {
      const rename = document.createElement("button");
      rename.type = "button";
      rename.className = "library-rename";
      rename.dataset.meetingId = row.meetingId || "";
      rename.textContent = labelSource === "operator" ? "Rename" : "Name this meeting";
      rename.addEventListener("click", () => renameMeeting(row, snapshot.metadataRevision));
      libraryList.append(rename);

      const move = document.createElement("select");
      move.className = "library-move";
      move.setAttribute("aria-label", `Folder for ${labelText}`);
      const none = document.createElement("option");
      none.value = "";
      none.textContent = "Unfiled";
      move.append(none);
      for (const folder of snapshot.folders || []) {
        const option = document.createElement("option");
        option.value = folder.id;
        option.textContent = folder.name;
        move.append(option);
      }
      move.value = row.folderId || "";
      move.addEventListener("change", () => moveMeeting(row, move.value || null));
      libraryList.append(move);
    }
  }
}

function renderLibrarySearch(response) {
  librarySearchResults.replaceChildren();
  findStart.hidden = true;
  clearError(libraryNotice);
  if (response.state !== "results" && response.state !== "results-incomplete") {
    setError(libraryNotice, response.message || "No retained text matched that search.");
    return;
  }
  for (const result of response.results || []) {
    const metadataOnly = result.kind === "meeting" && result.transcriptAvailable !== true;
    const row = document.createElement(metadataOnly ? "div" : "button");
    row.className = "library-search-result";
    if (metadataOnly) {
      row.dataset.state = "metadata-only";
    } else {
      row.type = "button";
      row.dataset.searchHandle = result.handle;
      row.addEventListener("click", () => openLibrarySearchResult(result.handle, row));
    }
    const summary = document.createElement("span");
    const label = document.createElement("strong");
    const detail = document.createElement("small");
    if (result.kind === "withheld") {
      label.textContent = "Withheld turn";
      detail.textContent = "A voice check withheld matching text.";
    } else if (result.kind === "meeting") {
      label.textContent = result.text || "Retained meeting";
      detail.textContent = "Title or folder match";
    } else {
      label.textContent = result.text || "Matched transcript text";
      detail.textContent = Number.isInteger(result.sourceTurnIndex)
        ? `Transcript · turn ${result.sourceTurnIndex + 1}`
        : "Transcript";
    }
    summary.append(label, detail);
    const action = document.createElement("span");
    action.textContent = metadataOnly
      ? "No transcript was created"
      : result.kind === "withheld"
        ? "Review status"
        : "Open transcript";
    row.append(summary, action);
    librarySearchResults.append(row);
  }
  const resultCount = (response.results || []).length;
  const total = Number.isInteger(response.totalMatches) ? response.totalMatches : resultCount;
  // The result is the rows. The total is a diagnostic, and it only earns a
  // sentence when it changes what the reader should do — which is when the page
  // was cut and narrowing the query would show them something else.
  const cut = total > resultCount
    ? `Showing the ${resultCount} most recent of ${total} matches. Add a word to narrow it.`
    : `${resultCount} exact ${resultCount === 1 ? "match" : "matches"} found.`;
  const resultMessage = response.state === "results-incomplete" ? response.message : cut;
  setError(libraryNotice, resultMessage || "Exact results from your retained meetings.");
}

// One click's ceiling. Rust caps a single `corpus_embed_pending` call at 512
// windows; this caps how many calls one click makes. Both bounds exist because
// a pass that never converges should stop and say so rather than spin.
const CORPUS_PREPARE_MAX_PASSES = 24;

// Meaning search reports how much of the corpus it actually searched, in every
// state including its failures. "Nothing matched" and "nothing has been
// prepared" are different sentences and only one of them is about the question.
function renderCorpusCoverage(response) {
  const windows = Number.isInteger(response.windows) ? response.windows : 0;
  const covered = Number.isInteger(response.covered) ? response.covered : 0;
  if (windows === 0 || covered >= windows) {
    corpusCoverage.hidden = true;
    return;
  }
  corpusCoverageCopy.textContent = covered === 0
    ? `None of your ${windows} passages are prepared yet. Preparing reads them through a model inside this app; nothing is sent anywhere.`
    : `${covered} of ${windows} passages are prepared. The rest were not searched.`;
  corpusPrepare.textContent = covered === 0 ? "Prepare passages" : "Prepare the rest";
  corpusCoverage.hidden = false;
}

function corpusAnswerLabel(answer) {
  if (answer.title) return answer.title;
  return formatMeetingTime(answer.createdAtEpochSeconds);
}

function renderCorpusAnswers(response) {
  corpusSearchResults.replaceChildren();
  renderCorpusCoverage(response);
  if (response.state !== "answered") {
    setError(corpusNotice, response.message || "That description could not be searched.");
    return;
  }
  for (const answer of response.answers || []) {
    const openable = Boolean(answer.transcriptHandle);
    const row = document.createElement(openable ? "button" : "div");
    row.className = "corpus-answer";
    if (openable) {
      row.type = "button";
      row.dataset.transcriptHandle = answer.transcriptHandle;
      row.addEventListener("click", () => openCorpusAnswer(answer, row));
    } else {
      row.dataset.state = "unopenable";
    }
    const label = document.createElement("strong");
    label.textContent = corpusAnswerLabel(answer);
    const where = document.createElement("small");
    // Turns are numbered for a person here and stored from zero, exactly as an
    // exact hit is, so the two searches never number one transcript two ways.
    const first = answer.firstTurnIndex + 1;
    const last = answer.lastTurnIndex + 1;
    const turns = first === last ? `turn ${first}` : `turns ${first}\u2013${last}`;
    where.textContent = answer.folder ? `${answer.folder} \u00b7 ${turns}` : turns;
    // The passage, not a score. A cosine similarity is not a probability and
    // printing it as a percentage would claim a confidence nobody measured; the
    // words are what lets a person judge whether the match is the right one.
    const quote = document.createElement("blockquote");
    quote.textContent = answer.quote;
    const action = document.createElement("span");
    // Three sentences, not two. A row with no handle because the library reader
    // was gone must not tell the operator this meeting has no transcript.
    action.textContent = openable
      ? "Open transcript"
      : response.handles === "unavailable"
        ? "Open it from Meetings"
        : "No transcript to open";
    row.append(label, where, quote, action);
    corpusSearchResults.append(row);
  }
  const ties = Number.isInteger(response.nearTies) ? response.nearTies : 0;
  // Both failures in the 200-meeting measurement arrived as ties at a margin of
  // 0.0000. A person who is told the top few are indistinguishable can pick the
  // right one; an accuracy figure hides exactly that case.
  const crowding = ties > 1
    ? ` ${ties} meetings scored close enough together that the order between them means little \u2014 read the passages rather than the ranking.`
    : "";
  setError(corpusNotice, `${response.message || "Meetings that match that description."}${crowding}`);
}

async function searchCorpus(event) {
  event.preventDefault();
  if (!invoke) return false;
  const revision = routeRevision;
  const ownsRoute = () => currentScreen === "find-screen" && routeRevision === revision;
  const question = corpusSearchQuestion.value.trim();
  corpusSearchResults.replaceChildren();
  corpusCoverage.hidden = true;
  if (!question) {
    setError(corpusNotice, "Describe what the meeting was about.");
    return false;
  }
  corpusSearchSubmit.disabled = true;
  setError(corpusNotice, "Searching by meaning on this Mac\u2026");
  try {
    // The library reader owns the corpus sync and the handles this answer will
    // carry, so it is initialized before the question rather than after it.
    await initializeLibraryReader();
    const response = await invoke("corpus_search", { question });
    if (!ownsRoute()) return false;
    renderCorpusAnswers(response);
    return response.state === "answered";
  } catch {
    if (ownsRoute()) {
      setError(corpusNotice, "Meaning search is unavailable right now. Exact word search still works.");
    }
    return false;
  } finally {
    corpusSearchSubmit.disabled = false;
  }
}

async function openCorpusAnswer(answer, control = null) {
  if (!answer.transcriptHandle) return false;
  claimExplicitRoute();
  const transition = beginHandleTransition("open-transcript", control);
  if (!transition) return false;
  productRootScreen = "find-screen";
  return await openLibraryTranscript(
    answer.transcriptHandle,
    // Land on the turn the passage starts at. The store cites character ranges
    // too, and this does not carry them: the exact path uses them to highlight
    // one matched phrase, and a passage is 128 words with no phrase to point at.
    { sourceTurnIndex: answer.firstTurnIndex, start: null, end: null },
    null,
    transition,
  );
}

async function prepareCorpusPassages() {
  if (!invoke) return false;
  const revision = routeRevision;
  const ownsRoute = () => currentScreen === "find-screen" && routeRevision === revision;
  corpusPrepare.disabled = true;
  try {
    for (let pass = 0; pass < CORPUS_PREPARE_MAX_PASSES; pass += 1) {
      const result = await invoke("corpus_embed_pending");
      if (!ownsRoute()) return false;
      renderCorpusCoverage(result);
      if (result.stop === "complete") {
        setError(corpusNotice, `All ${result.windows} passages are prepared. Ask your question again.`);
        return true;
      }
      if (result.stop !== "budget") {
        setError(corpusNotice, corpusPrepareFailure(result.stop));
        return false;
      }
      setError(corpusNotice, `Preparing on this Mac \u2014 ${result.covered} of ${result.windows} passages done\u2026`);
    }
    setError(corpusNotice, "Preparing stopped part-way. Run it again to continue where it left off.");
    return false;
  } catch {
    if (ownsRoute()) setError(corpusNotice, "Preparing is unavailable right now. Try again.");
    return false;
  } finally {
    corpusPrepare.disabled = false;
  }
}

function corpusPrepareFailure(stop) {
  if (stop === "busy") return "Finish the current recording before preparing passages.";
  if (stop === "model-mismatch") {
    return "This installation packages a different model than the stored passages were prepared with. Reinstall to search by meaning.";
  }
  if (stop === "worker-unavailable" || stop === "reply-incomplete") {
    return "The local model stopped answering. Reopen the app and run this again.";
  }
  return "Passages could not be prepared right now. Try again.";
}

function renderStartup(state) {
  const labels = {
    "shell-rendered": ["Opening the local shell", "Opening"],
    checking: ["Checking bundled files", "Checking"],
    "runtime-missing": ["This installation is incomplete", "Reinstall required"],
    "service-timeout": ["The local worker did not answer", "Check again"],
    "diagnostic-written": ["A private diagnostic was saved", "Needs attention"],
    retrying: ["Checking bundled files again", "Checking"],
    "reinstall-required": ["This installation must be repaired", "Reinstall required"],
  };
  const [heading, badge] = labels[state] || labels["diagnostic-written"];
  document.querySelector("#runtime-status").textContent = heading;
  document.querySelector("#runtime-pill").textContent = badge;
  document.querySelector("#startup-title").textContent =
    state === "runtime-missing" || state === "reinstall-required"
      ? "This build cannot start a meeting."
      : "Checking this installation.";
  retryStartup.hidden = !mutableActionPolicy(lastSnapshot).canRetryStartup;
  showWorkflowScreen(lastSnapshot, { resetScroll: currentScreen !== "startup-screen" });
}

function render(snapshot) {
  lastSnapshot = snapshot;
  const startup = snapshot.startup || "diagnostic-written";
  const capture = snapshot.capture || "idle";
  document.documentElement.dataset.startupState = startup;
  document.documentElement.dataset.captureState = capture;
  document.documentElement.dataset.connectionState = "connected";
  headerStatusDot.dataset.state = headerStatusPresentation(snapshot);
  releaseBadge.textContent = "Preview";
  renderCaptureAction(snapshot);
  meetingLabel.hidden = !snapshot.meeting_id;
  meetingLabel.textContent = snapshot.meeting_id ? `Meeting ${snapshot.meeting_id.slice(0, 8)}` : "";

  if (startup !== "ready") {
    setHeaderState("Nothing is recording");
    endElapsed();
    // A startup failure outranks first run, so hand the route back rather than let
    // a permission screen sit on top of a diagnostic that knows more.
    if (currentScreen === "first-run-screen") beginWorkflowRoute();
    renderStartup(startup);
    return;
  }

  switch (capture) {
    case "idle":
      setHeaderState("Ready");
      endElapsed();
      // The one call site: a started app at rest is the only moment first run may
      // take the screen, and it takes it at most once per launch.
      void considerFirstRun();
      // No meeting is open, so nothing typed belongs to anything. Reset rather
      // than carry one meeting's note into the next.
      resetLiveNote();
      if (workflowOwnsRoute && currentScreen !== "idle-screen") {
        showWorkflowScreen(snapshot, { resetScroll: true });
        initializeFindInBackground();
      }
      if (!snapshot.retention_operational) {
        setError(startError, snapshot.error || "Audio retention needs attention before another meeting can start.");
      }
      updateStartButton();
      break;
    case "arming":
      setHeaderState("Preparing recording");
      endElapsed();
      showWorkflowScreen(snapshot, { resetScroll: currentScreen !== "arming-screen" });
      break;
    case "recording":
      setHeaderState(stopCommandFailed
        ? "Recording · Stop needs attention"
        : snapshot.degraded ? "Recording · channel needs attention" : "Recording · both channels active");
      document.querySelector("#capture-health").textContent = snapshot.degraded
        ? "Recording continues, but one channel reported a problem."
        : "Microphone and system audio are both arriving.";
      renderChannelState(micChannel, snapshot.mic_state);
      renderChannelState(systemChannel, snapshot.system_state);
      beginElapsed(snapshot.started_at_epoch_seconds);
      showWorkflowScreen(snapshot, { resetScroll: currentScreen !== "recording-screen" });
      void loadLiveNoteFor(snapshot.meeting_id);
      break;
    case "stopping":
      setHeaderState("Stopping and flushing audio");
      document.querySelector("#capture-health").textContent = "Finalizing both local audio files.";
      showWorkflowScreen(snapshot);
      break;
    case "captured":
    case "transcribing":
      setHeaderState("Transcribing locally");
      endElapsed();
      showWorkflowScreen(snapshot, { resetScroll: currentScreen !== "processing-screen" });
      break;
    case "transcript-ready":
      setHeaderState("Transcript ready");
      endElapsed();
      if (workflowOwnsRoute) {
        renderTranscript(snapshot);
        showWorkflowScreen(snapshot, { resetScroll: currentScreen !== "transcript-screen" });
      }
      break;
    default:
      setHeaderState("Needs attention");
      endElapsed();
      document.querySelector("#error-detail").textContent = snapshot.error || "The attempt stopped before a validated transcript was ready.";
      showWorkflowScreen(snapshot, { resetScroll: currentScreen !== "error-screen" });
  }
}

// The §K standing statement: what recording audio is held, how much, and
// until when. Rows are facts, not navigation — the library list directly
// below opens meetings — and every sentence comes from the store's own
// state vocabulary.
function renderRetentionOverview(overview) {
  const heading = document.querySelector("#retention-overview-total");
  const copy = document.querySelector("#retention-overview-copy");
  const list = document.querySelector("#retention-overview-rows");
  const state = overview?.state || "unavailable";
  heading.textContent =
    state === "holding" ? `${formatByteSize(overview.totalRetainedBytes)} held` : "";
  copy.textContent =
    overview?.message
    || "Retention status is unavailable. Reopen Meetings and try again.";
  const rows = (Array.isArray(overview?.rows) ? overview.rows : []).filter(
    (row) => row?.audioState !== "never-created",
  );
  list.hidden = state !== "holding" || rows.length === 0;
  list.replaceChildren(
    ...rows.map((row) => {
      const item = document.createElement("li");
      const when = formatMeetingTime(row.createdAtEpochSeconds);
      let detail;
      if (row.audioState === "retained") {
        const size = formatByteSize(row.retainedBytes ?? -1);
        detail =
          row.policy === "scheduled"
            ? `${size} · ${retentionDeadlineMessage(row.deadlineEpochSeconds)}`
            : `${size} · Kept until you delete the recording.`;
      } else if (row.audioState === "deleting") {
        detail = "Deletion is already in progress.";
      } else {
        detail = "Audio deleted. The transcript, note, and evidence remain.";
      }
      item.textContent = `${when} — ${detail}`;
      return item;
    }),
  );
}

async function refreshRetentionOverview(revision) {
  if (!invoke) return;
  const overview = await invoke("preview_retention_overview").catch(() => null);
  if (currentScreen !== "meetings-screen" || routeRevision !== revision) return;
  renderRetentionOverview(overview);
}


// A date input gives a local calendar day; capture time is UTC epoch seconds.
// The conversion happens here because this is the only layer that knows the
// operator's zone — Rust deliberately does not, and `meeting_title.rs` refused to
// format dates in UTC for the same reason.
//
// **These parsed the date as UTC midnight until 2026-08-08 — the date string with
// a zulu suffix appended — and that silently dropped meetings.** A day interpreted
// in UTC is not the day the operator picked:
// west of UTC the end bound lands hours early, so filtering "to 8 August" in
// Chicago excluded a meeting recorded at 20:30 that evening — reproduced before
// the fix. The list then reported "showing 3 of 40" with a wrong 3, which is
// exactly the quiet lie the two-count message exists to prevent.
//
// Both bounds are built from local date parts. The end is the next local midnight
// minus one second rather than start + 86,399, because a day is not always 86,400
// seconds long: on a spring-forward date it is 82,800, and the arithmetic version
// would have run an hour past midnight into the following day.
function localDayParts(value) {
  if (!value) return null;
  const [year, month, day] = value.split("-").map(Number);
  if (!Number.isInteger(year) || !Number.isInteger(month) || !Number.isInteger(day)) return null;
  return [year, month, day];
}

function dayStartEpochSeconds(value) {
  const parts = localDayParts(value);
  if (!parts) return undefined;
  const [year, month, day] = parts;
  const local = new Date(year, month - 1, day, 0, 0, 0, 0);
  return Number.isFinite(local.getTime()) ? Math.floor(local.getTime() / 1000) : undefined;
}

function dayEndEpochSeconds(value) {
  const parts = localDayParts(value);
  if (!parts) return undefined;
  const [year, month, day] = parts;
  // `day + 1` normalizes across month and year ends on its own.
  const nextMidnight = new Date(year, month - 1, day + 1, 0, 0, 0, 0);
  return Number.isFinite(nextMidnight.getTime())
    ? Math.floor(nextMidnight.getTime() / 1000) - 1
    : undefined;
}

function readLibraryFilter() {
  const folder = filterFolder.value;
  const name = filterName.value.trim();
  const filter = {};
  if (folder === "unfiled") filter.unfiled = true;
  else if (folder) filter.folderId = folder;
  if (name) filter.title = name;
  const from = dayStartEpochSeconds(filterFrom.value);
  const to = dayEndEpochSeconds(filterTo.value);
  if (from !== undefined) filter.startEpochSeconds = from;
  if (to !== undefined) filter.endEpochSeconds = to;
  return filter;
}

// Rebuilt from the snapshot rather than appended to, so a folder deleted
// elsewhere stops being offered. The current selection is restored when it
// still exists and dropped when it does not — a filter naming a folder that is
// gone would show an empty list with no way to tell why.
function renderFolderOptions(snapshot) {
  const chosen = filterFolder.value;
  filterFolder.replaceChildren();
  const all = document.createElement("option");
  all.value = "";
  all.textContent = "All folders";
  const unfiled = document.createElement("option");
  unfiled.value = "unfiled";
  unfiled.textContent = "Unfiled";
  filterFolder.append(all, unfiled);
  for (const folder of snapshot.folders || []) {
    const option = document.createElement("option");
    option.value = folder.id;
    option.textContent = folder.name;
    filterFolder.append(option);
  }
  const stillThere = Array.from(filterFolder.options).some((option) => option.value === chosen);
  filterFolder.value = stillThere ? chosen : "";
  if (!stillThere && chosen) {
    delete libraryFilter.folderId;
    delete libraryFilter.unfiled;
  }
}

async function applyLibraryFilter() {
  libraryFilter = readLibraryFilter();
  await rebuildMeetingsView();
}

function clearLibraryFilter() {
  filterFolder.value = "";
  filterName.value = "";
  filterFrom.value = "";
  filterTo.value = "";
  libraryFilter = {};
  void rebuildMeetingsView();
}

// Filing a meeting is one command and a reload, like renaming. The select is
// per row rather than a bulk action: moving several meetings at once is a
// surface decision nobody has made, and guessing at it here would be the
// speculative half of this feature.
async function moveMeeting(row, folderId) {
  if (!invoke) return;
  clearError(libraryOrganizationNotice);
  if (!Number.isInteger(libraryMetadataRevision)) return;
  let response;
  try {
    response = await invoke("library_assign_meeting_folder", {
      expectedRevision: libraryMetadataRevision,
      meetingId: row.meetingId,
      folderId,
    });
  } catch {
    setError(libraryOrganizationNotice, "That change could not be saved. Nothing was written.");
    return;
  }
  if (response.state !== "ok") {
    setError(libraryOrganizationNotice, response.message);
    if (response.state === "revision-conflict") await rebuildMeetingsView();
    return;
  }
  await rebuildMeetingsView();
}

async function createFolder() {
  if (!invoke) return;
  clearError(libraryOrganizationNotice);
  if (!Number.isInteger(libraryMetadataRevision)) return;
  const answer = window.prompt("Name the new folder.", "");
  if (answer === null || answer.trim() === "") return;
  let response;
  try {
    response = await invoke("library_create_folder", {
      expectedRevision: libraryMetadataRevision,
      name: answer,
    });
  } catch {
    setError(libraryOrganizationNotice, "That folder could not be created. Nothing was written.");
    return;
  }
  if (response.state !== "ok") {
    setError(libraryOrganizationNotice, response.message);
    if (response.state === "revision-conflict") await rebuildMeetingsView();
    return;
  }
  await rebuildMeetingsView();
}

// The operator's own title, which outranks the meeting's opening line and the
// capture time beneath it. Until this existed the top branch of that precedence
// could never fire, because nothing in the product wrote the record it reads.
//
// `prompt` rather than an inline field: this is one string with no formatting,
// the shell has no modal of its own, and building one to type a title into is
// the kind of surface that should follow a person actually wanting it. An empty
// answer clears the title and restores the derived one, which is the contract's
// nullable title and is stated in the prompt rather than left to be discovered.
async function renameMeeting(row, expectedRevision) {
  if (!invoke) return;
  const current = row.labelSource === "operator" ? row.label : "";
  const answer = window.prompt(
    "Name this meeting. Leave it empty to go back to its opening line.",
    current || "",
  );
  if (answer === null) return;
  clearError(libraryOrganizationNotice);
  const title = answer.trim() === "" ? null : answer;
  let response;
  try {
    response = await invoke("library_set_meeting_title", {
      expectedRevision,
      meetingId: row.meetingId,
      title,
    });
  } catch {
    setError(libraryOrganizationNotice, "That change could not be saved. Nothing was written.");
    return;
  }
  if (response.state !== "ok") {
    setError(libraryOrganizationNotice, response.message);
    // A conflict means somebody else's change is already in the record, so the
    // rows on screen are stale. Reload rather than leaving them looking current.
    if (response.state === "revision-conflict") await rebuildMeetingsView();
    return;
  }
  if (!response.changed) {
    setError(libraryOrganizationNotice, response.message);
    return;
  }
  await rebuildMeetingsView();
}

async function rebuildMeetingsView() {
  if (!invoke) return;
  document.querySelector("#library-copy").textContent = "Opening retained meetings on this Mac.";
  invalidateLibraryHandles();
  const revision = routeRevision;
  try {
    const snapshot = await initializeLibraryReader();
    if (currentScreen !== "meetings-screen" || routeRevision !== revision) return;
    renderLibrary(snapshot);
    await refreshRetentionOverview(revision);
  } catch {
    if (currentScreen !== "meetings-screen" || routeRevision !== revision) return;
    renderLibrary({ state: "unavailable", rows: [], message: "Meetings are unavailable right now." });
    renderRetentionOverview(null);
  }
}

async function openFind({ resetQuery = false } = {}) {
  if (!invoke) return;
  if (resetQuery) librarySearchQuery.value = "";
  selectProductScreen("find-screen");
  await refreshFindView();
}

async function openMeetings({ resetFind = false } = {}) {
  if (!invoke) return;
  if (resetFind) librarySearchQuery.value = "";
  selectProductScreen("meetings-screen");
  await rebuildMeetingsView();
}

async function openPromises({ resetFind = false } = {}) {
  if (resetFind) librarySearchQuery.value = "";
  invalidateLibraryHandles();
  selectProductScreen("promises-screen", { resetScroll: true });
}

function showStartTransitionError() {
  startTransitionError.textContent = "The current meeting could not be closed safely. A new consent form was not opened. Return to Find and try again.";
  showScreen("start-meeting-error-screen", { resetScroll: true });
}

async function openStartMeeting() {
  if (!invoke || !mutableActionPolicy(lastSnapshot).canStartMeeting) return;
  clearError(startError);
  const routeToken = beginWorkflowRoute();
  startMeetingAction.disabled = true;
  startMeetingAction.textContent = "Opening…";
  try {
    const ready = await prepareConsentTransition(lastSnapshot.capture, {
      dismiss: () => dismissMeetingOperation.run(),
      clearHiddenAttempt: () => clearAttemptReview(true),
      afterOwnedDismiss: () => {
        invalidateLibraryHandles();
      },
      ownsRoute: () => workflowRouteIsCurrent(routeToken),
    });
    if (!ready) {
      if (!workflowRouteIsCurrent(routeToken)) return;
      if (lastSnapshot?.capture === "idle" && !isDismissalReadySnapshot(lastSnapshot)) return;
      showStartTransitionError();
      return;
    }
    if (workflowRouteIsCurrent(routeToken)) {
      clearAttemptReview(true);
      showScreen("idle-screen", { resetScroll: true });
    }
  } catch {
    if (workflowRouteIsCurrent(routeToken)) showStartTransitionError();
  } finally {
    startMeetingAction.disabled = false;
    startMeetingAction.textContent = "Record a meeting";
  }
}

// The guided-enrolment shortfall is stated in the terms the capture gate
// enforces, never as a progress bar: "return at least an hour after the first
// session" tells the operator what to do, and "80%" tells them to keep going.
// The gates say what clearing those requirements still would not decide.
// It is shown only where it can be acted on: the lifecycle answered and no
// profile is active. When voice status is unavailable or needs attention there
// is nothing to act on, and while a preserved profile awaits migration review
// the pending decision is the operator's next step, not a new sitting.
function renderEnrollmentGuidance(snapshot) {
  const applies =
    snapshot?.state === "baseline-ready" && snapshot?.profileActive !== true;
  const guidance = applies ? snapshot?.guidedEnrollment : null;
  const nextStep = guidance?.nextStep;
  profileNextStep.hidden = !nextStep;
  profileNextStep.textContent = nextStep || "";
  const gates = applies && Array.isArray(guidance?.gates) ? guidance.gates : [];
  profileEnrollmentGates.hidden = gates.length === 0;
  profileEnrollmentGates.textContent = gates.join(" ");
  renderOperatingPointsSection(guidance);
}

// § I: the one screen in the product that presents a trade-off rather than a
// reading. The section appears only in choosing-operating-point; its radios
// stay disabled until measurements load, no row is checked in advance, and
// Build stays disabled until the operator has explicitly selected one.
let latestOperatingPoints = null;
let operatingPointsBusy = false;

function renderOperatingPointsSection(guidance) {
  const applies = guidance?.state === "choosing-operating-point";
  operatingPointsSection.hidden = !applies;
  if (!applies) {
    latestOperatingPoints = null;
    operatingPointsRows.disabled = true;
    operatingPointsBuild.disabled = true;
    operatingPointsError.hidden = true;
    operatingPointsError.textContent = "";
    operatingPointsRows.replaceChildren(
      Object.assign(document.createElement("legend"), {
        textContent: "Measured options",
      }),
    );
  }
}

function renderOperatingPointRows(response) {
  const rows = operatingPointPresentation(response?.points);
  if (response?.state !== "choices" || rows.length < 2 || !response?.choicesSha256) {
    latestOperatingPoints = null;
    operatingPointsRows.disabled = true;
    operatingPointsBuild.disabled = true;
    operatingPointsError.textContent =
      response?.message
      || "The measured options are unavailable right now. Try again.";
    operatingPointsError.hidden = false;
    return;
  }
  latestOperatingPoints = { choicesSha256: response.choicesSha256, rows };
  operatingPointsError.hidden = true;
  operatingPointsError.textContent = "";
  operatingPointsRows.replaceChildren(
    Object.assign(document.createElement("legend"), {
      textContent: "Measured options",
    }),
    ...rows.map((row) => {
      const label = document.createElement("label");
      label.className = "check-row";
      const input = document.createElement("input");
      input.type = "radio";
      input.name = "operating-point";
      input.value = String(row.point.targetFrr);
      const text = document.createElement("span");
      const title = document.createElement("strong");
      title.textContent = `${row.label}.`;
      const costs = document.createElement("small");
      costs.textContent = row.costs;
      text.append(title, costs);
      label.append(input, text);
      return label;
    }),
  );
  operatingPointsRows.disabled = false;
  operatingPointsBuild.disabled = true;
  operatingPointsLoad.textContent = "Measure the options again";
}

async function loadOperatingPoints() {
  if (!invoke || operatingPointsBusy) return;
  operatingPointsBusy = true;
  operatingPointsLoad.disabled = true;
  try {
    const response = await invoke("preview_enrollment_operating_points").catch(() => null);
    if (currentScreen !== "profile-screen") return;
    renderOperatingPointRows(response);
  } finally {
    operatingPointsBusy = false;
    operatingPointsLoad.disabled = false;
  }
}

function selectedOperatingPoint() {
  const checked = operatingPointsRows.querySelector(
    "input[name=\"operating-point\"]:checked",
  );
  if (!checked || !latestOperatingPoints) return null;
  const target = Number(checked.value);
  const row = latestOperatingPoints.rows.find(
    (candidate) => candidate.point.targetFrr === target,
  );
  return row ? { target, choicesSha256: latestOperatingPoints.choicesSha256 } : null;
}

async function buildVoiceProfile(event) {
  event.preventDefault();
  if (!invoke || operatingPointsBusy) return;
  const selection = selectedOperatingPoint();
  if (!selection) {
    operatingPointsError.textContent = "Choose one measured option first.";
    operatingPointsError.hidden = false;
    return;
  }
  operatingPointsBusy = true;
  operatingPointsBuild.disabled = true;
  operatingPointsLoad.disabled = true;
  operatingPointsRows.disabled = true;
  operatingPointsBuild.textContent = "Building…";
  operatingPointsError.hidden = true;
  try {
    const snapshot = await invoke("preview_enrollment_build_profile", {
      selectedTarget: selection.target,
      choicesSha256: selection.choicesSha256,
    });
    if (currentScreen !== "profile-screen") return;
    renderProfile(snapshot);
    const surface = await invoke("preview_enrollment_surface").catch(() => null);
    if (currentScreen === "profile-screen") renderEnrollmentSittings(surface);
    profileStatusTitle.focus();
  } catch (error) {
    if (currentScreen !== "profile-screen") return;
    operatingPointsRows.disabled = false;
    operatingPointsBuild.disabled = false;
    operatingPointsError.textContent =
      typeof error === "string"
        ? error
        : "The profile was not built. Review the options and try again.";
    operatingPointsError.hidden = false;
  } finally {
    operatingPointsBusy = false;
    operatingPointsLoad.disabled = false;
    operatingPointsBuild.textContent = "Build voice profile";
  }
}

// Per-sitting lifecycle copy, content-free by construction: state labels come
// from the evidence store, and nothing here carries an audio digest, timing,
// or transcript-derived value. "Saved" is only ever the store's terminal
// state — derived material stored, raw recording deleted under its receipt.
const SITTING_STATE_COPY = {
  "recording-in-progress": "This recording did not finish. It will be set aside as a rehearsal.",
  "raw-retained": "Waiting for the app to derive voice material. The temporary recording is kept until that completes.",
  "cleanup-pending": "Voice material is stored. The app still has to delete the temporary recording.",
  saved: "Saved. The temporary recording has been deleted.",
  rehearsal: "Rehearsal only. It does not count toward setup.",
};

let latestEnrollmentSurface = null;
let sittingPollTimer = null;
let sittingCommandPending = false;

function renderEnrollmentSittings(surface) {
  latestEnrollmentSurface = surface;
  const presentation = enrollmentRecorderPresentation(surface);
  profileRecorderEntry.hidden = !presentation.entryText;
  profileRecorderEntry.textContent = presentation.entryText;
  sittingForm.hidden = presentation.mode !== "ready";
  sittingActive.hidden = presentation.mode !== "recording";
  sittingOutcome.hidden = !presentation.outcomeText;
  sittingOutcome.textContent = presentation.outcomeText;
  if (presentation.mode !== "ready") {
    sittingError.hidden = true;
    sittingError.textContent = "";
  }
  sittingStart.disabled = sittingCommandPending;
  sittingStop.disabled = sittingCommandPending;
  const sittings = Array.isArray(surface?.sittings) ? surface.sittings : [];
  profileSittings.hidden = sittings.length === 0;
  profileSittings.replaceChildren(
    ...sittings.map((sitting) => {
      const item = document.createElement("li");
      const kind =
        sitting?.kind === "negative-source" ? "Comparison speech" : "Voice session";
      const copy = SITTING_STATE_COPY[sitting?.state] || "State unavailable.";
      item.textContent = `${kind}: ${copy}`;
      return item;
    }),
  );
  syncGuidedSetupEntry();
  if (presentation.mode === "recording" || presentation.mode === "processing") {
    scheduleSittingPoll();
  }
}

function sittingAttemptRunning(surface) {
  const mode = enrollmentRecorderPresentation(surface).mode;
  return mode === "recording" || mode === "processing";
}

// While a take is active the recorder surface is the only live projection,
// so the profile screen re-reads it on a short cadence. The poll dies with
// the route and re-arms itself only while a recording is still in progress;
// when the take ends it refreshes the profile snapshot once, so the guided
// next step reflects the new evidence without reopening the screen.
function scheduleSittingPoll() {
  if (sittingPollTimer) window.clearTimeout(sittingPollTimer);
  sittingPollTimer = window.setTimeout(async () => {
    sittingPollTimer = null;
    if (!invoke || currentScreen !== "profile-screen") return;
    const wasRunning = sittingAttemptRunning(latestEnrollmentSurface);
    const surface = await invoke("preview_enrollment_surface").catch(() => null);
    if (currentScreen !== "profile-screen") return;
    renderEnrollmentSittings(surface);
    if (wasRunning && !sittingAttemptRunning(surface)) {
      const snapshot = await invoke("preview_profile_snapshot").catch(() => null);
      if (currentScreen === "profile-screen" && snapshot) renderProfile(snapshot);
      renderEnrollmentSittings(surface);
    }
  }, 1500);
}

function selectedSittingRequest() {
  const kind =
    sittingForm.querySelector("input[name=\"sitting-kind\"]:checked")?.value
    || "operator-sitting";
  if (kind !== "negative-source") return { kind, sourceClass: null };
  const sourceClass =
    sittingSourceClass.querySelector("input[name=\"sitting-source-class\"]:checked")?.value
    || null;
  return { kind, sourceClass };
}

function syncSittingSourceClass() {
  const { kind } = selectedSittingRequest();
  sittingSourceClass.hidden = kind !== "negative-source";
}

async function startSittingRecording(event) {
  event.preventDefault();
  if (!invoke || sittingCommandPending) return;
  const { kind, sourceClass } = selectedSittingRequest();
  if (kind === "negative-source" && !sourceClass) {
    sittingError.textContent = "Choose where the comparison speech comes from first.";
    sittingError.hidden = false;
    return;
  }
  sittingCommandPending = true;
  sittingStart.disabled = true;
  sittingError.hidden = true;
  sittingError.textContent = "";
  try {
    const surface = await invoke("preview_enrollment_start_sitting", {
      kind,
      sourceClass,
    });
    sittingCommandPending = false;
    if (currentScreen !== "profile-screen") return;
    renderEnrollmentSittings(surface);
    sittingStop.focus();
  } catch (error) {
    sittingCommandPending = false;
    if (currentScreen !== "profile-screen") return;
    sittingStart.disabled = false;
    sittingError.textContent =
      typeof error === "string" ? error : "The setup recording could not start.";
    sittingError.hidden = false;
  }
}

async function stopSittingRecording() {
  if (!invoke || sittingCommandPending) return;
  sittingCommandPending = true;
  sittingStop.disabled = true;
  try {
    await invoke("preview_enrollment_stop_sitting");
  } catch {
    // The refusal reaches the operator through the surface poll below: a
    // vanished take renders its outcome sentence, not a second error path.
  }
  sittingCommandPending = false;
  if (currentScreen !== "profile-screen") return;
  sittingActive.hidden = true;
  const surface = await invoke("preview_enrollment_surface").catch(() => null);
  if (currentScreen !== "profile-screen") return;
  renderEnrollmentSittings(surface);
  if (sittingAttemptRunning(surface)) {
    scheduleSittingPoll();
  } else {
    const snapshot = await invoke("preview_profile_snapshot").catch(() => null);
    if (currentScreen === "profile-screen" && snapshot) renderProfile(snapshot);
    renderEnrollmentSittings(surface);
  }
}

let latestProfileSnapshot = null;

// "Set up voice profile" is live exactly when the recorder below it can act:
// the no-profile state with a recorder the surface reports ready or already
// recording. Both projections arrive separately, so this sync runs from
// whichever lands last.
function syncGuidedSetupEntry() {
  if (profileSetup.dataset.action !== "setup") return;
  if (
    latestProfileSnapshot?.state !== "baseline-ready"
    || latestProfileSnapshot?.profilePresent !== false
    || latestProfileSnapshot?.profileActive === true
  ) {
    return;
  }
  const mode = enrollmentRecorderPresentation(latestEnrollmentSurface).mode;
  profileSetup.disabled = mode === "unavailable";
  profileStatusCopy.textContent =
    mode === "unavailable"
      ? "Private setup storage is ready. Guided setup is not part of this build."
      : "Private setup storage is ready. Setup recordings below are where you begin.";
}

function renderProfile(snapshot) {
  latestProfileSnapshot = snapshot;
  const state = snapshot?.state || "unavailable";
  profileResetConfirmation.hidden = true;
  profileResetStatus.hidden = true;
  profileResetStatus.textContent = "";
  profileResetConfirm.disabled = false;
  profileResetConfirm.textContent = "Delete voice profile";
  profileResetCancel.disabled = false;
  profileSetup.disabled = true;
  profileSetup.textContent = "Set up voice profile";
  profileSetup.dataset.action = "setup";
  renderEnrollmentGuidance(snapshot);
  // Presence and activation are separate lifecycle facts. An active enrolled
  // profile must never inherit the preserved-legacy copy below, which promises
  // that this build will not activate what it found. The heading stays
  // "Voice profile." in every state — the state lives in the lede and the
  // status card, so no state ever reads as two competing headlines.
  if (state === "baseline-ready" && snapshot?.profileActive === true) {
    profileLede.textContent = "A profile is active. Recording still requires headphones and only you near the microphone.";
    profileStatusTitle.textContent = "Voice isolation is on";
    profileStatusCopy.textContent = "This profile passed the app’s final checks before it was stored. It sets aside speech that does not match you; it does not name speakers.";
    profileFootnote.textContent = "Removing the profile deletes it, its calibrated setting, and its setup records. Meetings, transcripts, notes, and evidence remain.";
    profileSetup.disabled = false;
    profileSetup.textContent = "Reset stored profile";
    profileSetup.dataset.action = "reset";
    return;
  }
  if (state === "baseline-ready" && snapshot?.profilePresent === false) {
    profileLede.textContent = "Voice isolation is off. You can record now — one speaker, wearing headphones. A profile will let the app set aside speech that is not yours.";
    profileStatusTitle.textContent = "No profile is set up";
    profileStatusCopy.textContent = "Private setup storage is ready. Guided setup is not part of this build.";
    profileFootnote.textContent = "Opening this screen reads only the setup status. It never opens meetings or transcripts.";
    syncGuidedSetupEntry();
    return;
  }
  if (state === "baseline-ready" && snapshot?.profilePresent === true) {
    profileLede.textContent = "Stored profile material was found, but it is not active. Recording works the same either way — one speaker, wearing headphones.";
    profileStatusTitle.textContent = "Stored material is not active";
    profileStatusCopy.textContent = "This build will not turn these bytes on. You can remove them through a separate confirmation without changing any meeting.";
    profileFootnote.textContent = "Opening this screen reads only the setup status. Reset is the only action that opens and changes the stored profile slot.";
    profileSetup.disabled = false;
    profileSetup.textContent = "Reset stored profile";
    profileSetup.dataset.action = "reset";
    return;
  }
  if (state === "migration-review-required") {
    profileLede.textContent = "A profile from an earlier version was found. This build left it untouched and will not turn it on.";
    profileStatusTitle.textContent = "Earlier profile needs review";
    profileStatusCopy.textContent = "Preserve for review adds lifecycle records around the exact stored bytes. It does not turn them on or change them.";
    profileFootnote.textContent = "Leaving this screen keeps the stored profile unchanged. Removal stays a separate confirmed action.";
    profileSetup.disabled = false;
    profileSetup.textContent = "Preserve for review";
    profileSetup.dataset.action = "preserve";
    return;
  }
  if (state === "needs-attention") {
    profileLede.textContent = "Profile storage needs attention. Nothing was turned on or deleted.";
    profileStatusTitle.textContent = "Storage needs attention";
    profileStatusCopy.textContent = "Your retained meetings are still readable. Guided setup and reset stay unavailable in this build.";
    profileFootnote.textContent = "Opening this screen reads only the attention state. It never opens meetings or transcripts.";
    return;
  }
  profileLede.textContent = "This build could not read its own voice-setup state.";
  profileStatusTitle.textContent = "Status unavailable";
  profileStatusCopy.textContent = "Recording stays available under the current one-speaker limit. Retained meetings remain readable.";
  profileFootnote.textContent = "Try opening Settings again after the installation check finishes.";
}

function showProfileResetConfirmation() {
  if (profileSetup.disabled || profileSetup.dataset.action !== "reset") return;
  profileResetConfirmation.hidden = false;
  profileResetStatus.hidden = true;
  profileResetConfirm.disabled = false;
  profileResetCancel.disabled = false;
  profileResetConfirm.focus();
}

function cancelProfileReset() {
  profileResetConfirmation.hidden = true;
  profileResetStatus.hidden = true;
  profileSetup.focus();
}

async function resetStoredProfile() {
  if (!invoke || profileResetConfirm.disabled) return;
  const revision = routeRevision;
  profileResetConfirm.disabled = true;
  profileResetCancel.disabled = true;
  profileResetConfirm.textContent = "Deleting…";
  profileResetStatus.hidden = true;
  try {
    const snapshot = await invoke("preview_profile_reset", { confirmed: true });
    if (currentScreen !== "profile-screen" || routeRevision !== revision) return;
    renderProfile(snapshot);
    profileStatusCopy.textContent = "The stored voice profile was deleted. Meetings and their retained artifacts were not changed.";
    profileFootnote.textContent = "The reset journal retains only its completion count, latest event, fixed empty slots, and filesystem metadata.";
    profileStatusTitle.focus();
  } catch (error) {
    if (currentScreen !== "profile-screen" || routeRevision !== revision) return;
    profileResetConfirm.disabled = false;
    profileResetCancel.disabled = false;
    profileResetConfirm.textContent = "Delete voice profile";
    profileResetStatus.textContent = typeof error === "string" ? error : "The profile was not reset. Review the current status and try again.";
    profileResetStatus.hidden = false;
  }
}

async function preserveLegacyProfile() {
  if (!invoke || profileSetup.disabled) return;
  const revision = routeRevision;
  profileSetup.disabled = true;
  profileSetup.textContent = "Preserving…";
  try {
    const snapshot = await invoke("preview_profile_preserve_legacy");
    if (currentScreen === "profile-screen" && routeRevision === revision) renderProfile(snapshot);
  } catch {
    if (currentScreen !== "profile-screen" || routeRevision !== revision) return;
    const snapshot = await invoke("preview_profile_snapshot").catch(() => ({ state: "unavailable" }));
    renderProfile(snapshot);
    if (snapshot?.state === "migration-review-required") {
      profileStatusCopy.textContent = "The stored profile was left unchanged. Finish any active operation, then try again.";
    }
  }
}

function runProfileAction() {
  if (profileSetup.dataset.action === "setup") {
    if (profileSetup.disabled) return;
    document
      .querySelector("#profile-recorder")
      .scrollIntoView({ behavior: "smooth", block: "start" });
    const focusTarget = !sittingForm.hidden
      ? sittingForm.querySelector("input[name=\"sitting-kind\"]:checked")
      : !sittingActive.hidden
        ? sittingStop
        : null;
    focusTarget?.focus({ preventScroll: true });
    return;
  }
  if (profileSetup.dataset.action === "preserve") {
    preserveLegacyProfile();
    return;
  }
  if (profileSetup.dataset.action === "reset") showProfileResetConfirmation();
}

async function openProfile() {
  if (!invoke) return;
  selectProductScreen("profile-screen", { resetScroll: true });
  const revision = routeRevision;
  try {
    const snapshot = await invoke("preview_profile_snapshot");
    if (currentScreen === "profile-screen" && routeRevision === revision) renderProfile(snapshot);
  } catch {
    if (currentScreen === "profile-screen" && routeRevision === revision) {
      renderProfile({ state: "unavailable" });
    }
  }
  const surface = await invoke("preview_enrollment_surface").catch(() => null);
  if (currentScreen === "profile-screen" && routeRevision === revision) {
    renderEnrollmentSittings(surface);
  }
}

async function returnToProductHome() {
  if (productRootScreen === "meetings-screen") {
    await openMeetings();
    return;
  }
  if (productRootScreen === "promises-screen") {
    await openPromises();
    return;
  }
  await openFind();
}

function returnToWorkflow() {
  if (!lastSnapshot) return;
  const routeToken = beginWorkflowRoute();
  if (!workflowRouteIsCurrent(routeToken)) return;
  if (lastSnapshot.capture === "transcript-ready") renderTranscript(lastSnapshot);
  showWorkflowScreen(lastSnapshot, { resetScroll: true });
}

function reportLibraryOpenFailure(messageText) {
  if (currentScreen === "meeting-detail-screen") {
    message(meetingDetailState, messageText, "stale");
    return;
  }
  setError(libraryNotice, messageText);
}

// The frozen restore shape needs back exactly what this view was verified
// against: the meeting and the bound transcript digest of the open
// projection. Both live here, never in the DOM.
let libraryTranscriptRestore = null;

async function openLibraryTranscript(
  handle,
  matchedSourceTurnIndex = null,
  returnContext = null,
  nestedTransition = null,
  control = null,
) {
  if (!invoke || !handle) return;
  if (!nestedTransition) claimExplicitRoute();
  const transition = nestedTransition || beginHandleTransition("open-transcript", control);
  if (!transition) return false;
  invalidateLibraryHandles();
  try {
    const result = await invoke("preview_library_open_transcript", { handle });
    if (!currentTransitionOwnsRoute(transition)) return false;
    if (result.state !== "transcript") {
      reportLibraryOpenFailure(result.message || "That transcript is no longer current. Return and try again.");
      return false;
    }
    libraryTranscriptRestore =
      result.meetingId && result.currentTranscriptSha256
        ? {
            meetingId: result.meetingId,
            currentTranscriptSha256: result.currentTranscriptSha256,
          }
        : null;
    const restoreError = document.querySelector("#library-restore-error");
    restoreError.hidden = true;
    restoreError.textContent = "";
    renderedLibraryTurns = Array.isArray(result.turns) ? result.turns : [];
    renderTurns(
      document.querySelector("#library-transcript-turns"),
      document.querySelector("#library-transcript-warning"),
      result.turns,
      result.warnings,
      matchedSourceTurnIndex,
      libraryTranscriptRestore ? restoreWithheldTurnAction : null,
    );
    transcriptReturnContext = returnContext;
    showScreen("library-transcript-screen", { resetScroll: true });
    return true;
  } catch {
    if (!currentTransitionOwnsRoute(transition)) return false;
    reportLibraryOpenFailure("That transcript could not be opened. Return and try again.");
    return false;
  } finally {
    if (!nestedTransition) finishHandleTransition(transition);
  }
}

async function restoreWithheldTurnAction(turn, control) {
  if (!invoke || !libraryTranscriptRestore) return;
  const context = libraryTranscriptRestore;
  const restoreError = document.querySelector("#library-restore-error");
  restoreError.hidden = true;
  restoreError.textContent = "";
  control.disabled = true;
  control.textContent = "Restoring…";
  try {
    await invoke("restore_withheld_turn", {
      meetingId: context.meetingId,
      sourceTranscriptSha256: context.currentTranscriptSha256,
      sourceTurnIndex: turn.sourceTurnIndex,
    });
  } catch (error) {
    if (currentScreen !== "library-transcript-screen") return;
    control.disabled = false;
    control.textContent = "Restore this turn";
    restoreError.textContent =
      typeof error === "string" ? error : "The turn was not restored. Try again.";
    restoreError.hidden = false;
    return;
  }
  await reopenRestoredTranscript(context);
}

// A successful restoration publishes a new current transcript, so every
// handle bound to the old digest is stale by construction. The refresh walks
// the same path a cold open would: fresh snapshot, the meeting's current
// row, its note projection, and the transcript handle that projection names.
async function reopenRestoredTranscript(context) {
  claimExplicitRoute();
  const transition = beginHandleTransition("restore-turn-refresh", null);
  if (!transition) return;
  try {
    invalidateLibraryHandles();
    const snapshot = await initializeLibraryReader();
    if (!currentTransitionOwnsRoute(transition, "library-transcript-screen")) return;
    const row = rowForMeetingId(snapshot, context.meetingId);
    const detail = row?.handle
      ? await invoke("preview_library_open_note", { handle: row.handle })
      : null;
    if (!currentTransitionOwnsRoute(transition, "library-transcript-screen")) return;
    if (!detail?.transcriptHandle) {
      renderLibrary(snapshot);
      productRootScreen = "meetings-screen";
      showScreen("meetings-screen", { resetScroll: false });
      document.querySelector("#library-copy").textContent =
        "The turn was restored. Reopen the meeting to read the updated transcript.";
      return;
    }
    await openLibraryTranscript(
      detail.transcriptHandle,
      null,
      transcriptReturnContext,
      transition,
    );
  } catch {
    if (!currentTransitionOwnsRoute(transition, "library-transcript-screen")) return;
    const snapshot = await initializeLibraryReader().catch(() => null);
    if (snapshot) renderLibrary(snapshot);
    productRootScreen = "meetings-screen";
    showScreen("meetings-screen", { resetScroll: false });
    document.querySelector("#library-copy").textContent =
      "The turn was restored. Reopen the meeting to read the updated transcript.";
  } finally {
    finishHandleTransition(transition);
  }
}

function claimTypeLabel(value) {
  return {
    decision: "Decision",
    action: "Action",
    question: "Question",
    proposal: "Proposal",
  }[value] || "Claim";
}

// § D on the retained-meeting screen. Same two states the live surface keeps
// apart, for the same reason: an unreadable note told as "no note" says the
// operator wrote nothing while the app is holding words it could not parse.
function renderDetailNote(note) {
  const section = document.querySelector("#detail-note");
  const target = document.querySelector("#detail-note-text");
  if (note?.unreadable) {
    section.hidden = false;
    section.dataset.state = "unreadable";
    target.textContent =
      "A note was saved for this meeting and could not be read back. It has been left on disk untouched.";
    return;
  }
  const text = typeof note?.text === "string" ? note.text : "";
  section.hidden = !text;
  section.dataset.state = "typing";
  target.textContent = text;
}

function renderMeetingDetail(response) {
  renderDetailNote(response?.operatorNote);
  const presentation = meetingDetailPresentation(response);
  meetingClaimList.replaceChildren();
  meetingNoNote.hidden = true;
  meetingDetailTitle.textContent = presentation.title;
  meetingDetailLede.textContent = presentation.lede;
  meetingNoNoteTitle.textContent = presentation.fallbackTitle;
  meetingNoNoteCopy.textContent = presentation.fallbackCopy;
  meetingOpenTranscript.hidden = !presentation.canOpenTranscript;
  meetingDetailState.dataset.meetingId = response.meetingId || "";
  renderAudioRetention(response.audioRetention, response.audioDeletionHandle);
  // Offered for any meeting the reader could open, including one whose audio
  // was already released: the transcript, the note and the record are still there.
  meetingDeletionHandle = response.meetingDeletionHandle || "";
  meetingDeleteAction.hidden = !meetingDeletionHandle;
  const statusCopy = presentation.kind === "transcript-only"
    ? "Transcript available. Automatic notes are not available yet."
    : presentation.kind === "metadata-only"
      ? "Meeting details are available. No transcript was created."
      : response.message || "Opening retained meeting…";
  message(meetingDetailState, statusCopy, response.state || "");
  if (response.state !== "note") {
    meetingNoNote.hidden = presentation.kind === "note";
    return;
  }
  for (const [index, claim] of (response.claims || []).entries()) {
    const card = document.createElement("article");
    card.className = "meeting-claim";
    const meta = document.createElement("p");
    meta.className = "claim-meta";
    meta.textContent = `${claimTypeLabel(claim.claimType)} · words located`;
    const text = document.createElement("p");
    text.className = "claim-text";
    text.textContent = claim.claim;
    const open = document.createElement("button");
    open.type = "button";
    open.className = "secondary claim-evidence";
    open.dataset.claimOrdinal = String(claim.ordinal);
    open.dataset.claimIndex = String(index);
    open.textContent = "Show exact words in transcript";
    open.addEventListener("click", () => openMeetingEvidence(
      claim.handle,
      response.meetingId,
      claim,
      open,
    ));
    card.append(meta, text, open);
    meetingClaimList.append(card);
  }
  if (!meetingClaimList.children.length) {
    message(meetingDetailState, "This automatic note has no claims with text locators. The retained transcript remains the source of record.", "note");
  }
}

async function openMeetingDetail(handle, returnScreen = "meetings-screen", control = null) {
  if (!invoke || !handle) return;
  if (handleTransitionGate.active()) return false;
  claimExplicitRoute();
  productRootScreen = rootForDestination(returnScreen, productRootScreen);
  invalidateLibraryHandles();
  meetingRetention.hidden = true;
  message(meetingDetailState, "Opening this retained meeting…");
  showScreen("meeting-detail-screen", { resetScroll: true });
  const transition = beginHandleTransition("open-meeting-detail", control);
  if (!transition) return false;
  try {
    const response = await invoke("preview_library_open_note", { handle });
    if (!currentTransitionOwnsRoute(transition, "meeting-detail-screen")) return false;
    document.querySelector("#meeting-detail-transcript-handle").value = response.transcriptHandle || "";
    renderMeetingDetail(response);
    return true;
  } catch {
    if (!currentTransitionOwnsRoute(transition, "meeting-detail-screen")) return false;
    message(meetingDetailState, "That meeting could not be opened. Return to Meetings and try again.", "stale");
    meetingNoNote.hidden = true;
    return false;
  } finally {
    finishHandleTransition(transition);
  }
}

function focusRestoredMeetingOrigin(context, response) {
  if (context.claim) {
    const origin = [...meetingClaimList.querySelectorAll(".claim-evidence")].find((control) => {
      const claim = response.claims?.[Number(control.dataset.claimIndex)];
      return sameDisplayedClaim(claim, context.claim);
    });
    if (origin) {
      origin.focus({ preventScroll: true });
      return;
    }
    message(meetingDetailState, "This meeting changed while you were reviewing. The current detail is shown.", "changed");
    meetingDetailTitle.tabIndex = -1;
    meetingDetailTitle.focus({ preventScroll: true });
    return;
  }
  if (!meetingOpenTranscript.hidden) {
    meetingOpenTranscript.focus({ preventScroll: true });
    return;
  }
  meetingDetailTitle.tabIndex = -1;
  meetingDetailTitle.focus({ preventScroll: true });
}

async function restoreMeetingDetailAfterTranscript(context, transition) {
  if (!invoke || !context?.meetingId) return false;
  try {
    const snapshot = await initializeLibraryReader();
    if (!currentTransitionOwnsRoute(transition, "library-transcript-screen")) return false;
    const row = rowForMeetingId(snapshot, context.meetingId);
    if (!row?.handle) {
      renderLibrary(snapshot);
      productRootScreen = "meetings-screen";
      showScreen("meetings-screen", { resetScroll: false });
      document.querySelector("#library-copy").textContent = "That meeting is no longer available in this fresh library view.";
      return false;
    }
    const response = await invoke("preview_library_open_note", { handle: row.handle });
    if (!currentTransitionOwnsRoute(transition, "library-transcript-screen")) return false;
    document.querySelector("#meeting-detail-transcript-handle").value = response.transcriptHandle || "";
    renderMeetingDetail(response);
    screenScrollPositions.set("meeting-detail-screen", context.detailScrollTop);
    showScreen("meeting-detail-screen", { resetScroll: false, focus: false });
    mainRegion.scrollTop = context.detailScrollTop;
    focusRestoredMeetingOrigin(context, response);
    return true;
  } catch {
    if (!currentTransitionOwnsRoute(transition, "library-transcript-screen")) return false;
    const snapshot = await initializeLibraryReader().catch(() => null);
    if (!currentTransitionOwnsRoute(transition, "library-transcript-screen")) return false;
    if (snapshot) renderLibrary(snapshot);
    productRootScreen = "meetings-screen";
    showScreen("meetings-screen", { resetScroll: false });
    document.querySelector("#library-copy").textContent = "That meeting could not be reopened from the refreshed Meetings view.";
    return false;
  }
}

async function returnFromLibraryTranscript() {
  claimExplicitRoute();
  const transition = beginHandleTransition("return-from-transcript", document.querySelector("#library-transcript-back"));
  if (!transition) return false;
  const context = transcriptReturnContext;
  transcriptReturnContext = null;
  try {
    if (context?.destination === "meeting-detail") {
      return await restoreMeetingDetailAfterTranscript(context, transition);
    }
    if (!currentTransitionOwnsRoute(transition, "library-transcript-screen")) return false;
    await returnToProductHome();
    return true;
  } finally {
    finishHandleTransition(transition);
  }
}

async function openMeetingEvidence(handle, meetingId, claim, control) {
  if (!invoke || !handle) return;
  claimExplicitRoute();
  const returnContext = transcriptReturnRoute("meeting-detail", meetingId, {
    claim,
    detailScrollTop: mainRegion.scrollTop,
  });
  const transition = beginHandleTransition("open-claim-evidence", control);
  if (!transition) return false;
  invalidateLibraryHandles();
  message(meetingDetailState, "Opening the claim’s exact retained words…");
  try {
    const result = await invoke("preview_library_open_evidence", { handle, locatorOrdinal: 0 });
    if (!currentTransitionOwnsRoute(transition, "meeting-detail-screen")) return false;
    if (result.state !== "evidence" || !result.transcriptHandle || !Number.isInteger(result.sourceTurnIndex)) {
      message(meetingDetailState, result.message || "That claim is no longer current. Return to Meetings and try again.", result.state || "stale");
      return false;
    }
    return await openLibraryTranscript(result.transcriptHandle, {
      sourceTurnIndex: result.sourceTurnIndex,
      start: result.start,
      end: result.end,
    }, returnContext, transition);
  } catch {
    if (!currentTransitionOwnsRoute(transition, "meeting-detail-screen")) return false;
    message(meetingDetailState, "That claim could not be opened. Return to Meetings and try again.", "stale");
    return false;
  } finally {
    finishHandleTransition(transition);
  }
}

function setFindRefreshBusy(busy) {
  findRefreshBusyCount = Math.max(0, findRefreshBusyCount + (busy ? 1 : -1));
  findNavigationBusy = findRefreshBusyCount > 0;
  syncNavigationBusy();
}

async function performFindRefresh() {
  const revision = routeRevision;
  const ownsRoute = () => currentScreen === "find-screen" && routeRevision === revision;
  const query = librarySearchQuery.value.trim();
  findStart.hidden = Boolean(query);
  if (query) {
    setError(libraryNotice, "Searching your retained meetings…");
  } else {
    clearError(libraryNotice);
    librarySearchResults.replaceChildren();
  }
  try {
    await refreshFindGeneration(query, {
      isCurrent: ownsRoute,
      invalidateResults: invalidateLibraryHandles,
      snapshot: initializeLibraryReader,
      search: (currentQuery) => invoke("preview_library_search", { query: currentQuery }),
      render: (response) => {
        if (ownsRoute()) renderLibrarySearch(response);
      },
    });
    if (!query && ownsRoute()) {
      clearError(libraryNotice);
      findStart.hidden = false;
    }
    return { revision, ok: true };
  } catch {
    if (ownsRoute()) {
      invalidateLibraryHandles();
      setError(libraryNotice, "Search is unavailable right now. Try Find again.");
    }
    return { revision, ok: false };
  }
}

async function refreshFindView() {
  if (!invoke) return false;
  const requestedRevision = routeRevision;
  setFindRefreshBusy(true);
  try {
    const result = await findRefreshOperation.run();
    if (currentScreen === "find-screen"
        && requestedRevision === routeRevision
        && result.revision !== routeRevision) {
      return refreshFindView();
    }
    return result.ok;
  } finally {
    setFindRefreshBusy(false);
  }
}

async function searchLibrary(event) {
  event.preventDefault();
  await refreshFindView();
}

async function openLibrarySearchResult(handle, control = null) {
  if (!invoke || !handle) return;
  claimExplicitRoute();
  const transition = beginHandleTransition("open-search-result", control);
  if (!transition) return false;
  productRootScreen = "find-screen";
  invalidateLibraryHandles();
  setError(libraryNotice, "Opening the selected retained result…");
  try {
    const result = await invoke("preview_library_open_search_result", { handle });
    if (!currentTransitionOwnsRoute(transition, "find-screen")) return false;
    if (!result.transcriptHandle || result.state === "withheld") {
      setError(libraryNotice, result.message || "That result cannot be opened as visible transcript text. Run the search again to continue.");
      return false;
    }
    if (result.state !== "transcript" && result.state !== "meeting") {
      setError(libraryNotice, result.message || "That search result is no longer current. Run the search again to continue.");
      return false;
    }
    const exactMatch = Number.isInteger(result.sourceTurnIndex)
      ? {
          sourceTurnIndex: result.sourceTurnIndex,
          start: Number.isInteger(result.start) ? result.start : null,
          end: Number.isInteger(result.end) ? result.end : null,
        }
      : null;
    return await openLibraryTranscript(result.transcriptHandle, exactMatch, null, transition);
  } catch {
    if (!currentTransitionOwnsRoute(transition, "find-screen")) return false;
    setError(libraryNotice, "That search result could not be opened. Run the search again to continue.");
    return false;
  } finally {
    finishHandleTransition(transition);
  }
}

function schedulePoll(delay) {
  if (pollTimer) window.clearTimeout(pollTimer);
  pollTimer = window.setTimeout(refreshCurrent, delay);
}

async function refresh() {
  if (!invoke) {
    renderConnectionUncertainty();
    return null;
  }
  const ticket = snapshotRequestGate.begin();
  try {
    const snapshot = await invoke("app_snapshot");
    if (!snapshotRequestGate.isCurrent(ticket)) return REFRESH_SUPERSEDED;
    render(snapshot);
    scheduleSnapshotPoll(snapshot);
    return snapshot;
  } catch {
    if (!snapshotRequestGate.isCurrent(ticket)) return REFRESH_SUPERSEDED;
    renderConnectionUncertainty();
    schedulePoll(2000);
    return null;
  }
}

function refreshCurrent() {
  return refreshCurrentOperation.run();
}

function clearAttemptReview(clearRetention = false) {
  checks.forEach((check) => { check.checked = false; });
  if (clearRetention) retention.value = "";
  updateStartButton();
}

async function dismissAttemptAndReturnFind(control) {
  if (!invoke) {
    showStartTransitionError();
    return;
  }
  if (!mutableActionPolicy(lastSnapshot).canDismissMeeting) {
    showStartTransitionError();
    return;
  }
  const routeToken = beginWorkflowRoute();
  if (control) control.disabled = true;
  try {
    const snapshot = await dismissMeetingOperation.run();
    const admitted = settleDismissal(snapshot, {
      clearHiddenAttempt: () => clearAttemptReview(true),
      ownsRoute: () => workflowRouteIsCurrent(routeToken),
      afterOwnedDismiss: invalidateLibraryHandles,
    });
    if (!admitted) return;
    productRootScreen = "find-screen";
    librarySearchQuery.value = "";
    selectProductScreen("find-screen", { resetScroll: true });
    await refreshFindView();
  } catch {
    if (workflowRouteIsCurrent(routeToken)) showStartTransitionError();
  } finally {
    if (control) control.disabled = false;
  }
}

async function returnToFindAfterStartError(control) {
  const routeToken = beginWorkflowRoute();
  if (control) control.disabled = true;
  try {
    const currentCapture = lastSnapshot?.capture;
    const currentReady = lastSnapshot?.startup === "ready"
      && ["idle", "transcript-ready"].includes(currentCapture);
    const snapshot = currentReady ? lastSnapshot : await refreshCurrent();
    if (snapshot?.startup !== "ready"
        || !["idle", "transcript-ready"].includes(snapshot.capture)) {
      if (workflowRouteIsCurrent(routeToken)) showStartTransitionError();
      return;
    }
    if (!workflowRouteIsCurrent(routeToken)) return;
    productRootScreen = "find-screen";
    librarySearchQuery.value = "";
    selectProductScreen("find-screen");
    await refreshFindView();
  } finally {
    if (control) control.disabled = false;
  }
}

for (const field of checks) field.addEventListener("change", updateStartButton);
// Changing the retention period never invalidates the attestation checkboxes:
// consent, headphones, and one-operator are facts about the room, not about
// how long audio is kept.
retention.addEventListener("change", updateStartButton);

startForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearError(startError);
  if (!startIsAllowed() || !invoke) return;
  const request = {
    retentionDays: Number(retention.value),
    attestation: {
      participantsConsented: checks[0].checked,
      headphones: checks[1].checked,
      operatorAlone: checks[2].checked,
    },
  };
  clearAttemptReview();
  startButton.dataset.busy = "true";
  startButton.textContent = "Preparing…";
  updateStartButton();
  try {
    const snapshot = await invoke("start_meeting", request);
    acceptCommandSnapshot(snapshot);
  } catch (error) {
    setError(startError, String(error));
  } finally {
    startButton.dataset.busy = "false";
    startButton.textContent = "Start recording";
    updateStartButton();
  }
});

stopButton.addEventListener("click", async () => {
  if (stopCommandPending || lastSnapshot?.capture !== "recording") return;
  // The flag closes the re-entrancy window BEFORE the first await, and the
  // re-render disables the button. Setting it after the flush left the guard
  // open for the whole of it: a second click would pass, find nothing dirty,
  // and reach `stop_meeting` first, so the first click's stop returned "no
  // recording is ready to stop" and painted a red failure over a stop that
  // worked. That the flush is exactly what an operator typing up to the last
  // second triggers is what made it reachable rather than theoretical.
  stopCommandFailed = false;
  stopCommandPending = true;
  renderCaptureAction(lastSnapshot);
  clearError(stopError);
  // Whatever was typed since the last autosave is written before the meeting
  // moves on. Without this the final thought — usually the one written as the
  // call is wrapping up — is the one the debounce loses.
  await flushLiveNote();
  try {
    const snapshot = await invoke("stop_meeting");
    acceptCommandSnapshot(snapshot);
  } catch (error) {
    setError(stopError, String(error));
    stopCommandPending = false;
    stopCommandFailed = true;
    renderCaptureAction(lastSnapshot);
    setHeaderState("Recording · Stop needs attention");
  }
});

newMeetingButton.addEventListener("click", () => dismissAttemptAndReturnFind(newMeetingButton));
document.querySelector("#transcript-copy").addEventListener("click", (event) => {
  copyTranscript(
    renderedAttemptTurns,
    event.currentTarget,
    document.querySelector("#transcript-copy-status"),
  );
});
document.querySelector("#library-transcript-copy").addEventListener("click", (event) => {
  copyTranscript(
    renderedLibraryTurns,
    event.currentTarget,
    document.querySelector("#library-transcript-copy-status"),
  );
});
recoverButton.addEventListener("click", () => dismissAttemptAndReturnFind(recoverButton));

retryStartup.addEventListener("click", async () => {
  if (!invoke || !mutableActionPolicy(lastSnapshot).canRetryStartup) return;
  const snapshot = await invoke("retry_startup");
  acceptCommandSnapshot(snapshot);
});

findLink.addEventListener("click", () => openFind({ resetQuery: true }));
meetingsLink.addEventListener("click", () => openMeetings({ resetFind: true }));
promisesLink.addEventListener("click", () => openPromises({ resetFind: true }));
profileLink.addEventListener("click", openProfile);
profileSetup.addEventListener("click", runProfileAction);
profileResetConfirm.addEventListener("click", resetStoredProfile);
profileResetCancel.addEventListener("click", cancelProfileReset);
sittingForm.addEventListener("submit", startSittingRecording);
sittingForm.addEventListener("change", syncSittingSourceClass);
sittingStop.addEventListener("click", stopSittingRecording);
operatingPointsLoad.addEventListener("click", loadOperatingPoints);
operatingPointsForm.addEventListener("submit", buildVoiceProfile);
operatingPointsForm.addEventListener("change", () => {
  operatingPointsBuild.disabled = !selectedOperatingPoint();
});
workflowReturn.addEventListener("click", returnToWorkflow);
startMeetingAction.addEventListener("click", openStartMeeting);
document.querySelector("#start-back").addEventListener("click", returnToProductHome);
document.querySelector("#start-transition-back").addEventListener(
  "click",
  (event) => returnToFindAfterStartError(event.currentTarget),
);
librarySearch.addEventListener("submit", searchLibrary);
corpusSearch.addEventListener("submit", searchCorpus);
corpusPrepare.addEventListener("click", prepareCorpusPassages);
document.querySelector("#profile-back").addEventListener("click", returnToProductHome);
document.querySelector("#library-transcript-back").addEventListener("click", returnFromLibraryTranscript);
document.querySelector("#meeting-detail-back").addEventListener("click", returnToProductHome);
recordingDeleteReview.addEventListener("click", () => {
  if (!meetingAudioDeletionHandle) return;
  recordingDeleteConfirmation.hidden = false;
  recordingDeleteConfirm.focus();
});
recordingDeleteCancel.addEventListener("click", () => {
  closeRecordingDeleteReview();
  recordingDeleteReview.focus();
});
recordingDeleteConfirm.addEventListener("click", async () => {
  if (!invoke || !meetingAudioDeletionHandle) return;
  const handle = meetingAudioDeletionHandle;
  invalidateLibraryHandles();
  recordingDeleteAction.hidden = false;
  recordingDeleteConfirmation.hidden = false;
  recordingDeleteConfirm.disabled = true;
  recordingDeleteConfirm.textContent = "Deleting recording…";
  recordingDeleteStatus.hidden = false;
  recordingDeleteStatus.textContent = "Permanently deleting this meeting’s local audio…";
  try {
    const response = await invoke("preview_delete_meeting_audio", { handle });
    if (response.audioRetention) renderAudioRetention(response.audioRetention);
    message(meetingDetailState, response.message || "Recording deletion finished.", response.state || "");
    if (!response.audioRetention) {
      recordingDeleteStatus.textContent = response.message || "Recording deletion could not complete. Return to Meetings and try again.";
      recordingDeleteConfirm.disabled = true;
    }
  } catch {
    recordingDeleteStatus.textContent = "Recording deletion could not complete. Return to Meetings and try again.";
    recordingDeleteConfirm.disabled = true;
  }
});
meetingDeleteReview.addEventListener("click", () => {
  if (!meetingDeletionHandle) return;
  meetingDeleteConfirmation.hidden = false;
  meetingDeleteConfirm.focus();
});
meetingDeleteCancel.addEventListener("click", () => {
  closeMeetingDeleteReview();
  meetingDeleteReview.focus();
});
meetingDeleteConfirm.addEventListener("click", async () => {
  if (!invoke || !meetingDeletionHandle) return;
  const handle = meetingDeletionHandle;
  invalidateLibraryHandles();
  meetingDeleteAction.hidden = false;
  meetingDeleteConfirmation.hidden = false;
  meetingDeleteConfirm.disabled = true;
  meetingDeleteConfirm.textContent = "Deleting meeting…";
  meetingDeleteStatus.hidden = false;
  meetingDeleteStatus.textContent = "Permanently deleting this meeting and everything recorded with it…";
  try {
    // `confirmed` is this click, and this shell is what asked. The panel above
    // is the operator-facing confirmation; sending `true` asserts it happened.
    // The Rust side does not and cannot re-derive that, so this is a report,
    // not a proof.
    const response = await invoke("preview_delete_meeting", { handle, confirmed: true });
    if (response.state === "removed" || response.state === "already-removed") {
      // The meeting no longer exists, so its detail view must not remain open.
      // Staying here would render a meeting that is gone, which is the
      // tombstone this action exists to avoid.
      returnToProductHome();
      return;
    }
    meetingDeleteStatus.textContent = response.message || "Meeting deletion could not complete. Return to Meetings and try again.";
    meetingDeleteConfirm.disabled = true;
  } catch {
    meetingDeleteStatus.textContent = "Meeting deletion could not complete. Return to Meetings and try again.";
    meetingDeleteConfirm.disabled = true;
  }
});
meetingOpenTranscript.addEventListener("click", () => {
  const handle = document.querySelector("#meeting-detail-transcript-handle").value;
  const meetingId = meetingDetailState.dataset.meetingId || "";
  if (handle) {
    openLibraryTranscript(handle, null, transcriptReturnRoute("meeting-detail", meetingId, {
      detailScrollTop: mainRegion.scrollTop,
    }), null, meetingOpenTranscript);
  }
});


// § D. The operator's own note.
//
// Loaded once per meeting rather than polled: the snapshot ticks every 400 ms
// while recording and this text can be long, so it is read on entry and written
// on a debounce. The app never reads it back into anything — it is not evidence,
// nothing cites it, and no generator is given it.
const liveNoteSection = document.querySelector("#live-note");
const liveNoteText = document.querySelector("#live-note-text");
const liveNoteState = document.querySelector("#live-note-state");
const LIVE_NOTE_SAVE_DELAY = 1200;

let liveNoteMeetingId = null;
let liveNoteTimer = null;
let liveNoteDirty = false;
let liveNoteSaving = false;
let liveNoteFailure = "";
let liveNoteSavedRecently = false;
let liveNoteUnreadable = false;
// What storage last confirmed, which is not the same as what is in the box. The
// transcript screen rendered the box, so a dropped save showed the operator
// their unsaved words as their saved note — nothing looked wrong until relaunch.
let liveNoteSavedText = "";

function renderLiveNote() {
  const status = liveNoteStatus({
    unreadable: liveNoteUnreadable,
    failed: liveNoteFailure,
    pending: liveNoteDirty || liveNoteSaving,
    saved: liveNoteSavedRecently,
    text: liveNoteText.value,
  });
  liveNoteSection.dataset.state = status.state;
  liveNoteText.disabled = !status.editable;
  liveNoteState.textContent = status.message;
}

async function loadLiveNoteFor(meetingId) {
  if (!invoke || !meetingId || liveNoteMeetingId === meetingId) return;
  liveNoteMeetingId = meetingId;
  liveNoteDirty = false;
  liveNoteFailure = "";
  liveNoteSavedRecently = false;
  try {
    const note = await invoke("operator_note");
    // A meeting can change while this is in flight; a note published onto the
    // wrong meeting would put one meeting's thinking under another's heading.
    if (liveNoteMeetingId !== meetingId) return;
    liveNoteUnreadable = Boolean(note?.unreadable);
    liveNoteSavedText = typeof note?.text === "string" ? note.text : "";
    liveNoteText.value = liveNoteSavedText;
  } catch {
    if (liveNoteMeetingId !== meetingId) return;
    liveNoteUnreadable = false;
    liveNoteSavedText = "";
    liveNoteText.value = "";
    liveNoteFailure = "This meeting's note could not be opened.";
  }
  renderLiveNote();
}

// Saves are serialized on one chain rather than dropped when one is in flight.
//
// The first version early-returned on `liveNoteSaving`, which made the flush on
// Stop a no-op whenever the debounce had just fired — precisely the closing
// thought the flush exists to keep. It also stranded the debounce: a timer that
// fired mid-save dropped its write and rescheduled nothing, leaving "Saving…" on
// screen with no save pending. Queueing fixes both, because a link appended to
// the chain runs after the in-flight one and reads the text as it is then.
async function writeLiveNote() {
  const meetingId = liveNoteMeetingId;
  const text = liveNoteText.value;
  liveNoteSaving = true;
  liveNoteDirty = false;
  renderLiveNote();
  try {
    const note = await invoke("save_operator_note", { text });
    if (liveNoteMeetingId !== meetingId) return;
    liveNoteFailure = "";
    liveNoteUnreadable = Boolean(note?.unreadable);
    // What storage now holds, from storage's own answer rather than from the
    // box. Every later reader uses this.
    liveNoteSavedText = typeof note?.text === "string" ? note.text : "";
    liveNoteSavedRecently = !liveNoteDirty;
  } catch (error) {
    if (liveNoteMeetingId !== meetingId) return;
    // The text stays in the box. Clearing it on a failed save would destroy the
    // only copy of something the operator cannot retype from memory.
    liveNoteDirty = true;
    liveNoteFailure =
      typeof error === "string" ? error : "That note could not be saved. It is still here.";
  } finally {
    if (liveNoteMeetingId === meetingId) {
      liveNoteSaving = false;
      renderLiveNote();
    }
  }
}

const liveNoteWrites = createWriteQueue(() =>
  invoke && !liveNoteUnreadable && liveNoteDirty ? writeLiveNote() : undefined);

function saveLiveNote() {
  return liveNoteWrites.push();
}

function resetLiveNote() {
  if (liveNoteMeetingId === null) return;
  if (liveNoteTimer) {
    window.clearTimeout(liveNoteTimer);
    liveNoteTimer = null;
  }
  liveNoteMeetingId = null;
  liveNoteDirty = false;
  liveNoteFailure = "";
  liveNoteSavedRecently = false;
  liveNoteUnreadable = false;
  liveNoteSavedText = "";
  liveNoteText.value = "";
  renderLiveNote();
}

async function flushLiveNote() {
  if (liveNoteTimer) {
    window.clearTimeout(liveNoteTimer);
    liveNoteTimer = null;
  }
  // One appended link is enough: it runs after anything in flight, and reads the
  // text at that moment, so it captures keystrokes that landed during the wait.
  await saveLiveNote();
}

// Shown back on the finished-transcript screen, read-only. Without this the
// note disappears the moment the meeting ends, onto a screen the operator has no
// way to return to — which reads as lost, not as saved.
const transcriptNoteSection = document.querySelector("#transcript-note");
const transcriptNoteText = document.querySelector("#transcript-note-text");

function renderTranscriptNote() {
  // "Could not be read" is not "nothing was written", and collapsing them here
  // would undo the whole reason the flag exists — the operator would be told
  // they took no notes when the app is holding words it could not parse.
  if (liveNoteUnreadable) {
    transcriptNoteSection.hidden = false;
    transcriptNoteSection.dataset.state = "unreadable";
    transcriptNoteText.textContent =
      "A note was saved for this meeting and could not be read back. It has been left on disk untouched rather than replaced.";
    return;
  }
  transcriptNoteSection.dataset.state = "typing";
  // What storage confirmed, never the box. Rendering the box meant a dropped
  // save displayed unsaved words as the saved note, and nothing looked wrong
  // until the next launch. Found by review on 128283a.
  const text = liveNoteSavedText;
  transcriptNoteSection.hidden = !text;
  transcriptNoteText.textContent = text;
}

liveNoteText.addEventListener("input", () => {
  liveNoteDirty = true;
  liveNoteSavedRecently = false;
  liveNoteFailure = "";
  renderLiveNote();
  if (liveNoteTimer) window.clearTimeout(liveNoteTimer);
  liveNoteTimer = window.setTimeout(() => {
    liveNoteTimer = null;
    void saveLiveNote();
  }, LIVE_NOTE_SAVE_DELAY);
});

// § H. First run.
//
// The step is derived from a measurement every time, never remembered. There is no
// "first run completed" flag on disk on purpose: a stored flag would keep claiming
// setup was finished after an operator revoked a permission in System Settings,
// which is precisely the state this surface exists to catch. Deriving it means the
// flow reappears exactly when it is true again and disappears on its own.
const firstRunScreen = document.querySelector("#first-run-screen");
const firstRunPanels = new Map(
  [...firstRunScreen.querySelectorAll("[data-step-panel]")].map((panel) => [
    panel.dataset.stepPanel,
    panel,
  ]),
);
const firstRunDeniedPane = document.querySelector("#first-run-denied-pane");

function showFirstRunStep(step) {
  firstRunScreen.dataset.step = step;
  for (const [name, panel] of firstRunPanels) panel.hidden = name !== step;
}

function renderFirstRun(result, { origin = "" } = {}) {
  // The mapping itself lives in navigation-state.mjs with the shell's other routing
  // decisions, where it is tested.
  const step = firstRunStepFor(result);
  if (step === "denied-recovery") {
    firstRunDeniedPane.textContent = firstRunDeniedPermissionName(result);
  }
  if (origin === "microphone" && step === "request-audio-capture") {
    message(
      document.querySelector("#first-run-microphone-state"),
      "Microphone allowed.",
      "ok",
    );
  }
  showFirstRunStep(step);
  return step;
}

async function readFirstRunPermissions() {
  try {
    return await invoke("first_run_permissions");
  } catch {
    return null;
  }
}

async function runFirstRunRequest(command, control, statusNode, origin) {
  control.disabled = true;
  try {
    const result = await invoke(command);
    // A request that showed no dialog is the signal to route to System Settings
    // rather than let the operator press the same button again.
    if (result && result.prompted === false && origin === "microphone"
      && (result.microphone === "denied" || result.microphone === "restricted")) {
      message(statusNode, "macOS did not show a prompt; this was refused earlier.", "warn");
    }
    renderFirstRun(result, { origin });
  } catch {
    message(statusNode, "The permission request could not run.", "warn");
  } finally {
    control.disabled = false;
  }
}

document.querySelector("#first-run-begin").addEventListener("click", async () => {
  renderFirstRun(await readFirstRunPermissions());
});
document.querySelector("#first-run-ask-microphone").addEventListener("click", (event) => {
  runFirstRunRequest(
    "first_run_request_microphone",
    event.currentTarget,
    document.querySelector("#first-run-microphone-state"),
    "microphone",
  );
});
document.querySelector("#first-run-ask-system-audio").addEventListener("click", (event) => {
  runFirstRunRequest(
    "first_run_request_system_audio",
    event.currentTarget,
    document.querySelector("#first-run-system-audio-state"),
    "system-audio",
  );
});
document.querySelector("#first-run-recheck").addEventListener("click", async () => {
  renderFirstRun(await readFirstRunPermissions());
});
document.querySelector("#first-run-retry-probe").addEventListener("click", async () => {
  renderFirstRun(await readFirstRunPermissions());
});
document.querySelector("#first-run-enrol").addEventListener("click", () => {
  // Routes to the enrolment surface that already exists rather than duplicating it.
  selectProductScreen("profile-screen", { resetScroll: true });
});
document.querySelector("#first-run-skip-enrol").addEventListener("click", () => {
  showFirstRunStep("ready");
});
document.querySelector("#first-run-done").addEventListener("click", () => {
  selectProductScreen("idle-screen", { resetScroll: true });
});
// Narrowing the list. Folder and the two dates re-request on change; the name box
// waits for the operator to stop typing rather than issuing a snapshot per
// keystroke, because each one is a validated read of every meeting on disk.
filterFolder.addEventListener("change", () => void applyLibraryFilter());
filterFrom.addEventListener("change", () => void applyLibraryFilter());
filterTo.addEventListener("change", () => void applyLibraryFilter());
let filterNameTimer = null;
filterName.addEventListener("input", () => {
  if (filterNameTimer !== null) clearTimeout(filterNameTimer);
  filterNameTimer = setTimeout(() => {
    filterNameTimer = null;
    void applyLibraryFilter();
  }, 250);
});
filterClear.addEventListener("click", clearLibraryFilter);
filterNewFolder.addEventListener("click", () => void createFolder());

// The two dead ends get an exit. Neither panel's primary control can succeed from
// inside this window — one needs System Settings, the other needs a reinstall — so
// without this the first thing a new operator meets is a screen they cannot leave.
for (const id of ["#first-run-leave-denied", "#first-run-leave-unavailable"]) {
  document.querySelector(id).addEventListener("click", () => {
    selectProductScreen("idle-screen", { resetScroll: true });
  });
}

// Entry. Considered once per launch, and only from a resting, started app.
//
// The first version ran at load and lost the screen immediately: `workflowOwnsRoute`
// starts true, so the next poll tick resolved a workflow destination and navigated
// away — every 1500 ms, forever. First run was unreachable in practice and every
// test still passed, because route ownership is shell state that no unit test holds.
// So this waits for a snapshot, claims the route explicitly the way every other
// non-workflow screen does, and is driven from `render` rather than from load.
//
// Two conditions outrank it, both checked against the snapshot rather than assumed:
// a startup that is not ready, because the diagnostic knows more than a permission
// check that cannot even resolve its probe without storage; and a capture that is
// not idle, because a meeting in progress is not a moment to ask about setup.
let firstRunConsidered = false;

async function considerFirstRun() {
  if (firstRunConsidered) return;
  firstRunConsidered = true;
  const result = await readFirstRunPermissions();
  if (!result) return;
  const step = firstRunStepFor(result);
  if (step === "enrol-voice" || step === "ready") return;
  // Re-read the snapshot rather than trusting the one that got us here: the probe
  // ran across an await, and a startup failure in that window outranks this screen.
  if ((lastSnapshot?.startup || "") !== "ready" || (lastSnapshot?.capture || "") !== "idle") return;
  renderFirstRun(result);
  claimExplicitRoute();
  showScreen("first-run-screen", { resetScroll: true });
}

renderStartup("shell-rendered");
refreshCurrent();

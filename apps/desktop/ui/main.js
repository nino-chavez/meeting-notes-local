import {
  createSingleFlight,
  createLatestRequestGate,
  createRouteOwnershipGate,
  createTransitionGate,
  changedStatusText,
  connectionUncertaintyStatus,
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
const startMeetingAction = document.querySelector("#start-meeting-action");
const newMeetingButton = document.querySelector("#new-meeting");
const recoverButton = document.querySelector("#recover-button");
const startTransitionError = document.querySelector("#start-transition-error");
const profileKicker = document.querySelector("#profile-kicker");
const profileTitle = document.querySelector("#profile-title");
const profileLede = document.querySelector("#profile-lede");
const profileStatusTitle = document.querySelector("#profile-status-title");
const profileStatusCopy = document.querySelector("#profile-status-copy");
const libraryList = document.querySelector("#library-list");
const libraryNotice = document.querySelector("#library-notice");
const librarySearch = document.querySelector("#library-search");
const librarySearchQuery = document.querySelector("#library-search-query");
const librarySearchSubmit = librarySearch.querySelector("button[type=\"submit\"]");
const librarySearchResults = document.querySelector("#library-search-results");
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
  () => invoke("preview_library_snapshot"),
);
const findRefreshOperation = createSingleFlight(performFindRefresh);
const handleTransitionGate = createTransitionGate();
const snapshotRequestGate = createLatestRequestGate();
const routeOwnership = createRouteOwnershipGate();
const REFRESH_SUPERSEDED = Symbol("refresh-superseded");
const dismissMeetingOperation = createSingleFlight(
  () => invoke("dismiss_meeting"),
);

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
  const productActive = [
    "find-screen",
    "meetings-screen",
    "promises-screen",
    "meeting-detail-screen",
    "library-transcript-screen",
  ].includes(currentScreen);
  const activeLink = {
    "find-screen": findLink,
    "meetings-screen": meetingsLink,
    "promises-screen": promisesLink,
  }[productRootScreen];
  for (const link of [findLink, meetingsLink, promisesLink]) {
    if (productActive && !settingsActive && link === activeLink) link.setAttribute("aria-current", "page");
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
  const policy = mutableActionPolicy(snapshot, { stopPending: stopCommandPending });
  productNav.hidden = !policy.showProductNavigation;
  profileLink.hidden = !policy.showProductNavigation;
  startMeetingAction.hidden = !policy.canStartMeeting;
  stopButton.hidden = !policy.showStop;
  stopButton.disabled = policy.stopDisabled;
  stopButton.textContent = policy.stopLabel;
  return policy;
}

function renderConnectionUncertainty() {
  document.documentElement.dataset.connectionState = "uncertain";
  setHeaderState(connectionUncertaintyStatus(lastSnapshot?.capture, {
    stopFailed: stopCommandFailed,
  }));
}

async function initializeLibraryReader() {
  if (!invoke) throw new Error("The local application bridge is unavailable.");
  return libraryInitialization.run();
}

function initializeFindInBackground() {
  void refreshFindView();
}

function invalidateLibraryHandles() {
  libraryList.replaceChildren();
  librarySearchResults.replaceChildren();
  meetingClaimList.replaceChildren();
  meetingNoNote.hidden = true;
  document.querySelector("#meeting-detail-transcript-handle").value = "";
  meetingAudioDeletionHandle = "";
  recordingDeleteAction.hidden = true;
  closeRecordingDeleteReview();
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

function renderTranscript(snapshot) {
  renderTurns(
    document.querySelector("#transcript-turns"),
    document.querySelector("#transcript-warning"),
    snapshot.turns,
    snapshot.warnings,
  );
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

function renderTurns(container, warning, turns, warnings, match = null) {
  container.replaceChildren();
  const safeWarnings = Array.isArray(warnings) ? warnings : [];
  warning.hidden = safeWarnings.length === 0;
  warning.textContent = safeWarnings.join(" ");
  for (const turn of turns || []) {
    const row = document.createElement("section");
    row.className = "turn";
    const matchesTurn = Number.isInteger(match?.sourceTurnIndex)
      && turn.sourceTurnIndex === match.sourceTurnIndex;
    if (matchesTurn) {
      row.classList.add("matched-turn");
      row.dataset.sourceTurnIndex = String(match.sourceTurnIndex);
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
      const destination = container.querySelector(".matched-locator")
        || container.querySelector(`[data-source-turn-index="${match.sourceTurnIndex}"]`);
      destination?.scrollIntoView({ block: "center" });
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
  meetingRetentionPolicy.textContent = retention.message || "Audio retention details are unavailable. Reopen Meetings and try again.";
  meetingRetentionConsequence.textContent = "No recording action is available from this Preview view.";
}

function renderLibrary(snapshot) {
  libraryList.replaceChildren();
  document.querySelector("#library-copy").textContent = snapshot.message || "Opening retained meetings on this Mac.";
  if (snapshot.state !== "populated" && snapshot.state !== "populated-incomplete") {
    const empty = document.createElement("p");
    empty.className = "library-empty";
    empty.textContent = snapshot.state === "empty"
      ? "No retained meetings yet. Finish a recording to see it here."
      : snapshot.state === "unavailable"
        ? "The local library is not available yet. No retained meeting or transcript was opened."
        : "Some retained meetings could not be read. Reopen Library and try again.";
    libraryList.append(empty);
    return;
  }
  for (const row of snapshot.rows || []) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "library-row";
    button.dataset.meetingHandle = row.handle;
    button.dataset.meetingId = row.meetingId || "";
    button.dataset.label = row.label || "Untitled meeting";
    button.addEventListener("click", () => openMeetingDetail(
      row.handle,
      "meetings-screen",
      button,
    ));
    const summary = document.createElement("span");
    const label = document.createElement("strong");
    label.textContent = row.label || "Untitled meeting";
    const time = document.createElement("small");
    time.textContent = formatMeetingTime(row.createdAtEpochSeconds);
    summary.append(label, time);
    const action = document.createElement("span");
    action.textContent = row.transcriptAvailable ? "Open meeting" : "No transcript was created";
    button.append(summary, action);
    libraryList.append(button);
  }
}

function renderLibrarySearch(response) {
  librarySearchResults.replaceChildren();
  clearError(libraryNotice);
  if (response.state !== "results" && response.state !== "results-incomplete") {
    setError(libraryNotice, response.message || "No retained text matched that search.");
    return;
  }
  for (const result of response.results || []) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "library-search-result";
    button.dataset.searchHandle = result.handle;
    const metadataOnly = result.kind === "meeting" && result.transcriptAvailable !== true;
    button.disabled = metadataOnly;
    button.addEventListener("click", () => openLibrarySearchResult(result.handle, button));
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
    button.append(summary, action);
    librarySearchResults.append(button);
  }
  setError(libraryNotice, response.message || "Exact results from your retained meetings.");
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
  const preview = snapshot.preview === true;
  releaseBadge.textContent = preview ? "Preview" : "Internal alpha";
  renderCaptureAction(snapshot);
  meetingLabel.textContent = snapshot.meeting_id ? `Meeting ${snapshot.meeting_id.slice(0, 8)}` : "";

  if (startup !== "ready") {
    setHeaderState("Nothing is recording");
    endElapsed();
    renderStartup(startup);
    return;
  }

  switch (capture) {
    case "idle":
      setHeaderState("Ready · nothing is recording");
      endElapsed();
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
      setHeaderState("Preparing · nothing is recording");
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
      document.querySelector("#mic-state").textContent = snapshot.mic_state || "Active";
      document.querySelector("#system-state").textContent = snapshot.system_state || "Active";
      beginElapsed(snapshot.started_at_epoch_seconds);
      showWorkflowScreen(snapshot, { resetScroll: currentScreen !== "recording-screen" });
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
      setHeaderState("Transcript ready · nothing is recording");
      endElapsed();
      if (workflowOwnsRoute) {
        renderTranscript(snapshot);
        showWorkflowScreen(snapshot, { resetScroll: currentScreen !== "transcript-screen" });
      }
      break;
    default:
      setHeaderState("Nothing is recording · needs attention");
      endElapsed();
      document.querySelector("#error-detail").textContent = snapshot.error || "The attempt stopped before a validated transcript was ready.";
      showWorkflowScreen(snapshot, { resetScroll: currentScreen !== "error-screen" });
  }
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
  } catch {
    if (currentScreen !== "meetings-screen" || routeRevision !== revision) return;
    renderLibrary({ state: "unavailable", rows: [], message: "Meetings are unavailable right now." });
  }
}

async function openFind() {
  if (!invoke) return;
  selectProductScreen("find-screen");
  await refreshFindView();
}

async function openMeetings() {
  if (!invoke) return;
  selectProductScreen("meetings-screen");
  await rebuildMeetingsView();
}

function openPromises() {
  if (lastSnapshot?.preview === false) return;
  selectProductScreen("promises-screen");
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
      clearPriorAttempt: () => {
        clearAttemptReview(true);
        invalidateLibraryHandles();
      },
      ownsRoute: () => workflowRouteIsCurrent(routeToken),
      refresh: refreshCurrent,
    });
    if (!ready) {
      if (!workflowRouteIsCurrent(routeToken)) return;
      showStartTransitionError();
      return;
    }
    if (workflowRouteIsCurrent(routeToken)) showScreen("idle-screen", { resetScroll: true });
  } catch {
    if (workflowRouteIsCurrent(routeToken)) showStartTransitionError();
  } finally {
    startMeetingAction.disabled = false;
    startMeetingAction.textContent = "Start meeting";
  }
}

function renderProfile(snapshot) {
  const state = snapshot?.state || "unavailable";
  if (state === "setup-unavailable") {
    profileKicker.textContent = "Voice profile · Setup required";
    profileTitle.textContent = "Your voice setup takes two sittings.";
    profileLede.textContent = "Voice isolation is not active in this Preview. Alpha recording remains limited to one person near the microphone.";
    profileStatusTitle.textContent = "Voice setup is not available yet";
    profileStatusCopy.textContent = "Setup is not available in this Preview yet. Current alpha recording remains available under its existing one-operator limits.";
    return;
  }
  profileKicker.textContent = "Voice profile · Needs attention";
  profileTitle.textContent = "Voice setup status is unavailable.";
  profileLede.textContent = "This Preview could not read its own voice-setup capability state.";
  profileStatusTitle.textContent = "Voice isolation is unavailable";
  profileStatusCopy.textContent = "The app did not open or change profile material. Current retained meetings remain readable.";
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
}

async function returnToProductHome() {
  if (productRootScreen === "meetings-screen") {
    await openMeetings();
    return;
  }
  if (productRootScreen === "promises-screen") {
    openPromises();
    return;
  }
  await openFind();
}

function reportLibraryOpenFailure(messageText) {
  if (productRootScreen === "meetings-screen" && currentScreen === "meeting-detail-screen") {
    message(meetingDetailState, messageText, "stale");
    return;
  }
  setError(libraryNotice, messageText);
}

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
    renderTurns(
      document.querySelector("#library-transcript-turns"),
      document.querySelector("#library-transcript-warning"),
      result.turns,
      result.warnings,
      matchedSourceTurnIndex,
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

function claimTypeLabel(value) {
  return {
    decision: "Decision",
    action: "Action",
    question: "Question",
    proposal: "Proposal",
  }[value] || "Claim";
}

function renderMeetingDetail(response) {
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
  message(meetingDetailState, response.message || "Opening retained meeting…", response.state || "");
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
    message(meetingDetailState, "This note has no supported claims. The retained transcript remains the source of record.", "note");
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
    document.querySelector("#library-copy").textContent = "That meeting could not be reopened from the fresh library view.";
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
  if (query) setError(libraryNotice, "Searching your retained meetings…");
  else clearError(libraryNotice);
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
    if (!query && ownsRoute()) clearError(libraryNotice);
    return { revision, ok: true };
  } catch {
    if (ownsRoute()) {
      invalidateLibraryHandles();
      setError(libraryNotice, "Find is unavailable right now. Reopen Find and try again.");
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
  pollTimer = window.setTimeout(refresh, delay);
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
    const active = ["arming", "recording", "stopping", "captured", "transcribing"].includes(snapshot.capture);
    schedulePoll(active ? 400 : 1500);
    return snapshot;
  } catch {
    if (!snapshotRequestGate.isCurrent(ticket)) return REFRESH_SUPERSEDED;
    renderConnectionUncertainty();
    schedulePoll(2000);
    return null;
  }
}

async function refreshCurrent() {
  let snapshot = await refresh();
  while (snapshot === REFRESH_SUPERSEDED) snapshot = await refresh();
  return snapshot;
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
    await dismissMeetingOperation.run();
    if (!workflowRouteIsCurrent(routeToken)) return;
    clearAttemptReview(true);
    invalidateLibraryHandles();
    const snapshot = await refreshCurrent();
    if (!workflowRouteIsCurrent(routeToken)) return;
    if (snapshot?.capture !== "idle") {
      showStartTransitionError();
      return;
    }
    if (currentScreen !== "find-screen") {
      productRootScreen = "find-screen";
      selectProductScreen("find-screen", { resetScroll: true });
      await refreshFindView();
    }
  } catch {
    if (workflowRouteIsCurrent(routeToken)) showStartTransitionError();
  } finally {
    if (control) control.disabled = false;
  }
}

async function returnToFindAfterStartError() {
  const routeToken = beginWorkflowRoute();
  const currentCapture = lastSnapshot?.capture;
  const currentReady = lastSnapshot?.startup === "ready"
    && lastSnapshot?.preview === true
    && ["idle", "transcript-ready"].includes(currentCapture);
  const snapshot = currentReady ? lastSnapshot : await refreshCurrent();
  if (snapshot?.startup !== "ready"
      || snapshot?.preview !== true
      || !["idle", "transcript-ready"].includes(snapshot.capture)) {
    if (workflowRouteIsCurrent(routeToken)) showStartTransitionError();
    return;
  }
  if (!workflowRouteIsCurrent(routeToken)) return;
  productRootScreen = "find-screen";
  selectProductScreen("find-screen");
  await refreshFindView();
}

for (const field of checks) field.addEventListener("change", updateStartButton);
retention.addEventListener("change", () => {
  clearAttemptReview();
});

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
    await invoke("start_meeting", request);
    await refresh();
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
  clearError(stopError);
  stopCommandFailed = false;
  stopCommandPending = true;
  renderCaptureAction(lastSnapshot);
  try {
    await invoke("stop_meeting");
    await refresh();
  } catch (error) {
    setError(stopError, String(error));
    stopCommandPending = false;
    stopCommandFailed = true;
    renderCaptureAction(lastSnapshot);
    setHeaderState("Recording · Stop needs attention");
  }
});

newMeetingButton.addEventListener("click", () => dismissAttemptAndReturnFind(newMeetingButton));
recoverButton.addEventListener("click", () => dismissAttemptAndReturnFind(recoverButton));

retryStartup.addEventListener("click", async () => {
  if (invoke && mutableActionPolicy(lastSnapshot).canRetryStartup) await invoke("retry_startup");
  await refresh();
});

findLink.addEventListener("click", openFind);
meetingsLink.addEventListener("click", openMeetings);
promisesLink.addEventListener("click", openPromises);
profileLink.addEventListener("click", openProfile);
startMeetingAction.addEventListener("click", openStartMeeting);
document.querySelector("#start-back").addEventListener("click", openFind);
document.querySelector("#start-transition-back").addEventListener("click", returnToFindAfterStartError);
librarySearch.addEventListener("submit", searchLibrary);
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
      recordingDeleteStatus.textContent = response.message || "Recording deletion could not complete. Reopen Meetings and try again.";
      recordingDeleteConfirm.disabled = true;
    }
  } catch {
    recordingDeleteStatus.textContent = "Recording deletion could not complete. Reopen Meetings and try again.";
    recordingDeleteConfirm.disabled = true;
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

renderStartup("shell-rendered");
refresh();

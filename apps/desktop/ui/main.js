import {
  createSingleFlight,
  prepareConsentTransition,
  refreshFindGeneration,
  restoredScrollPosition,
  rootForDestination,
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
const meetingClaimList = document.querySelector("#meeting-claim-list");
const meetingNoNote = document.querySelector("#meeting-no-note");
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
const screenScrollPositions = new Map();
const libraryInitialization = createSingleFlight(
  () => invoke("preview_library_snapshot"),
);
const findRefreshOperation = createSingleFlight(performFindRefresh);

function showScreen(id, { resetScroll = false, focus = true } = {}) {
  const destination = screens.get(id);
  if (!destination) return;
  const routeChanged = currentScreen !== id;
  if (routeChanged) screenScrollPositions.set(currentScreen, mainRegion.scrollTop);
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
  const activeLink = {
    "find-screen": findLink,
    "meetings-screen": meetingsLink,
    "promises-screen": promisesLink,
  }[productRootScreen];
  for (const link of [findLink, meetingsLink, promisesLink]) {
    if (link === activeLink) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  }
}

function isIdleProductScreen() {
  return [
    "find-screen",
    "meetings-screen",
    "promises-screen",
    "profile-screen",
    "idle-screen",
    "meeting-detail-screen",
    "library-transcript-screen",
    "transcript-screen",
    "start-meeting-error-screen",
  ].includes(currentScreen);
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
  return lastSnapshot?.retention_operational === true
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

function localRetentionDeadline(epochSeconds) {
  const value = Number(epochSeconds) * 1000;
  if (!Number.isFinite(value) || value <= 0) return "The scheduled deletion time is unavailable.";
  return `Scheduled to delete on ${new Intl.DateTimeFormat(undefined, {
    dateStyle: "full", timeStyle: "short",
  }).format(new Date(value))}.`;
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
      : localRetentionDeadline(deadline);
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
      : "Some retained meetings could not be read. Reopen Meetings and try again.";
    libraryList.append(empty);
    return;
  }
  for (const row of snapshot.rows || []) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "library-row";
    button.dataset.meetingHandle = row.handle;
    button.dataset.label = row.label || "Untitled meeting";
    button.disabled = row.transcriptAvailable !== true;
    button.addEventListener("click", () => openMeetingDetail(row.handle, "meetings-screen"));
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
    button.addEventListener("click", () => openLibrarySearchResult(result.handle));
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
  retryStartup.hidden = !["service-timeout", "diagnostic-written"].includes(state);
  showScreen("startup-screen");
}

function render(snapshot) {
  lastSnapshot = snapshot;
  const startup = snapshot.startup || "diagnostic-written";
  const capture = snapshot.capture || "idle";
  document.documentElement.dataset.startupState = startup;
  document.documentElement.dataset.captureState = capture;
  const preview = snapshot.preview === true;
  releaseBadge.textContent = preview ? "Preview" : "Internal alpha";
  const productNavigationAvailable = preview && ["idle", "transcript-ready"].includes(capture) && startup === "ready";
  productNav.hidden = !productNavigationAvailable;
  profileLink.hidden = !productNavigationAvailable;
  startMeetingAction.hidden = !productNavigationAvailable;
  meetingLabel.textContent = snapshot.meeting_id ? `Meeting ${snapshot.meeting_id.slice(0, 8)}` : "";

  if (startup !== "ready") {
    headerState.textContent = "Nothing is recording";
    endElapsed();
    renderStartup(startup);
    return;
  }

  switch (capture) {
    case "idle":
      headerState.textContent = "Ready · nothing is recording";
      endElapsed();
      if (!isIdleProductScreen()) {
        showScreen("find-screen", { resetScroll: true });
        initializeFindInBackground();
      }
      if (!snapshot.retention_operational) {
        setError(startError, snapshot.error || "Audio retention needs attention before another meeting can start.");
      }
      updateStartButton();
      break;
    case "arming":
      headerState.textContent = "Preparing · nothing is recording";
      endElapsed();
      showScreen("arming-screen", { resetScroll: true });
      break;
    case "recording":
      headerState.textContent = snapshot.degraded ? "Recording · channel needs attention" : "Recording · both channels active";
      stopButton.disabled = false;
      document.querySelector("#capture-health").textContent = snapshot.degraded
        ? "Recording continues, but one channel reported a problem."
        : "Microphone and system audio are both arriving.";
      document.querySelector("#mic-state").textContent = snapshot.mic_state || "Active";
      document.querySelector("#system-state").textContent = snapshot.system_state || "Active";
      beginElapsed(snapshot.started_at_epoch_seconds);
      showScreen("recording-screen", { resetScroll: currentScreen !== "recording-screen" });
      break;
    case "stopping":
      headerState.textContent = "Stopping and flushing audio";
      stopButton.disabled = true;
      document.querySelector("#capture-health").textContent = "Finalizing both local audio files.";
      showScreen("recording-screen");
      break;
    case "captured":
    case "transcribing":
      headerState.textContent = "Transcribing locally";
      endElapsed();
      showScreen("processing-screen", { resetScroll: currentScreen !== "processing-screen" });
      break;
    case "transcript-ready":
      headerState.textContent = "Transcript ready · nothing is recording";
      endElapsed();
      renderTranscript(snapshot);
      if (!isIdleProductScreen()) showScreen("transcript-screen", { resetScroll: true });
      break;
    default:
      headerState.textContent = "Nothing is recording · needs attention";
      endElapsed();
      document.querySelector("#error-detail").textContent = snapshot.error || "The attempt stopped before a validated transcript was ready.";
      showScreen("error-screen");
  }
}

async function rebuildMeetingsView() {
  if (!invoke) return;
  document.querySelector("#library-copy").textContent = "Opening retained meetings on this Mac.";
  invalidateLibraryHandles();
  try {
    const snapshot = await initializeLibraryReader();
    renderLibrary(snapshot);
  } catch {
    renderLibrary({ state: "unavailable", rows: [], message: "Meetings are unavailable right now." });
  }
}

async function openFind() {
  if (!invoke || lastSnapshot?.preview !== true) return;
  showScreen("find-screen");
  await refreshFindView();
}

async function openMeetings() {
  if (!invoke || lastSnapshot?.preview !== true) return;
  showScreen("meetings-screen");
  await rebuildMeetingsView();
}

function openPromises() {
  if (!lastSnapshot?.preview) return;
  showScreen("promises-screen");
}

function showStartTransitionError() {
  startTransitionError.textContent = "The current meeting could not be closed safely. A new consent form was not opened. Return to Find and try again.";
  showScreen("start-meeting-error-screen", { resetScroll: true });
}

async function openStartMeeting() {
  if (!invoke || !lastSnapshot?.preview) return;
  clearError(startError);
  startMeetingAction.disabled = true;
  startMeetingAction.textContent = "Opening…";
  try {
    const ready = await prepareConsentTransition(lastSnapshot.capture, {
      dismiss: () => invoke("dismiss_meeting"),
      clearPriorAttempt: () => {
        clearAttemptReview(true);
        invalidateLibraryHandles();
      },
      refresh,
    });
    if (!ready) {
      showStartTransitionError();
      return;
    }
    showScreen("idle-screen", { resetScroll: true });
  } catch {
    showStartTransitionError();
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
  if (!invoke || lastSnapshot?.preview !== true) return;
  showScreen("profile-screen", { resetScroll: true });
  try {
    renderProfile(await invoke("preview_profile_snapshot"));
  } catch {
    renderProfile({ state: "unavailable" });
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

async function openLibraryTranscript(handle, matchedSourceTurnIndex = null) {
  if (!invoke || !handle) return;
  invalidateLibraryHandles();
  try {
    const result = await invoke("preview_library_open_transcript", { handle });
    if (result.state !== "transcript") {
      reportLibraryOpenFailure(result.message || "That transcript is no longer current. Return and try again.");
      return;
    }
    renderTurns(
      document.querySelector("#library-transcript-turns"),
      document.querySelector("#library-transcript-warning"),
      result.turns,
      result.warnings,
      matchedSourceTurnIndex,
    );
    showScreen("library-transcript-screen", { resetScroll: true });
  } catch {
    reportLibraryOpenFailure("That transcript could not be opened. Return and try again.");
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
  meetingClaimList.replaceChildren();
  meetingNoNote.hidden = true;
  renderAudioRetention(response.audioRetention, response.audioDeletionHandle);
  message(meetingDetailState, response.message || "Opening retained meeting…", response.state || "");
  if (response.state !== "note") {
    const showsTranscriptFallback = ["transcript-only", "summary-failed"].includes(response.state)
      && Boolean(response.transcriptHandle);
    meetingNoNote.hidden = !showsTranscriptFallback;
    return;
  }
  for (const claim of response.claims || []) {
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
    open.textContent = "Show exact words in transcript";
    open.addEventListener("click", () => openMeetingEvidence(claim.handle));
    card.append(meta, text, open);
    meetingClaimList.append(card);
  }
  if (!meetingClaimList.children.length) {
    message(meetingDetailState, "This note has no supported claims. The retained transcript remains the source of record.", "note");
  }
}

async function openMeetingDetail(handle, returnScreen = "meetings-screen") {
  if (!invoke || !handle) return;
  productRootScreen = rootForDestination(returnScreen, productRootScreen);
  invalidateLibraryHandles();
  meetingRetention.hidden = true;
  message(meetingDetailState, "Opening this retained meeting…");
  showScreen("meeting-detail-screen", { resetScroll: true });
  try {
    const response = await invoke("preview_library_open_note", { handle });
    document.querySelector("#meeting-detail-transcript-handle").value = response.transcriptHandle || "";
    renderMeetingDetail(response);
  } catch {
    message(meetingDetailState, "That meeting could not be opened. Return to Meetings and try again.", "stale");
    meetingNoNote.hidden = true;
  }
}

async function openMeetingEvidence(handle) {
  if (!invoke || !handle) return;
  invalidateLibraryHandles();
  message(meetingDetailState, "Opening the claim’s exact retained words…");
  try {
    const result = await invoke("preview_library_open_evidence", { handle, locatorOrdinal: 0 });
    if (result.state !== "evidence" || !result.transcriptHandle || !Number.isInteger(result.sourceTurnIndex)) {
      message(meetingDetailState, result.message || "That claim is no longer current. Return to Meetings and try again.", result.state || "stale");
      return;
    }
    await openLibraryTranscript(result.transcriptHandle, {
      sourceTurnIndex: result.sourceTurnIndex,
      start: result.start,
      end: result.end,
    });
  } catch {
    message(meetingDetailState, "That claim could not be opened. Return to Meetings and try again.", "stale");
  }
}

function setFindRefreshBusy(busy) {
  librarySearchSubmit.disabled = busy;
  for (const link of [findLink, meetingsLink, promisesLink]) link.disabled = busy;
}

async function performFindRefresh() {
  const query = librarySearchQuery.value.trim();
  if (query) setError(libraryNotice, "Searching your retained meetings…");
  else clearError(libraryNotice);
  try {
    await refreshFindGeneration(query, {
      invalidateResults: invalidateLibraryHandles,
      snapshot: initializeLibraryReader,
      search: (currentQuery) => invoke("preview_library_search", { query: currentQuery }),
      render: (response) => {
        if (currentScreen === "find-screen") renderLibrarySearch(response);
      },
    });
    if (!query && currentScreen === "find-screen") clearError(libraryNotice);
    return true;
  } catch {
    invalidateLibraryHandles();
    if (currentScreen === "find-screen") {
      setError(libraryNotice, "Find is unavailable right now. Reopen Find and try again.");
    }
    return false;
  }
}

async function refreshFindView() {
  if (!invoke) return false;
  setFindRefreshBusy(true);
  try {
    return await findRefreshOperation.run();
  } finally {
    setFindRefreshBusy(false);
  }
}

async function searchLibrary(event) {
  event.preventDefault();
  await refreshFindView();
}

async function openLibrarySearchResult(handle) {
  if (!invoke || !handle) return;
  productRootScreen = "find-screen";
  invalidateLibraryHandles();
  setError(libraryNotice, "Opening the selected retained result…");
  try {
    const result = await invoke("preview_library_open_search_result", { handle });
    if (!result.transcriptHandle || result.state === "withheld") {
      setError(libraryNotice, result.message || "That result cannot be opened as visible transcript text. Run the search again to continue.");
      return;
    }
    if (result.state !== "transcript" && result.state !== "meeting") {
      setError(libraryNotice, result.message || "That search result is no longer current. Run the search again to continue.");
      return;
    }
    const exactMatch = Number.isInteger(result.sourceTurnIndex)
      ? {
          sourceTurnIndex: result.sourceTurnIndex,
          start: Number.isInteger(result.start) ? result.start : null,
          end: Number.isInteger(result.end) ? result.end : null,
        }
      : null;
    await openLibraryTranscript(result.transcriptHandle, exactMatch);
  } catch {
    setError(libraryNotice, "That search result could not be opened. Run the search again to continue.");
  }
}

function schedulePoll(delay) {
  if (pollTimer) window.clearTimeout(pollTimer);
  pollTimer = window.setTimeout(refresh, delay);
}

async function refresh() {
  if (!invoke) {
    render({ startup: "diagnostic-written", capture: "idle", error: "The local application bridge is unavailable." });
    return null;
  }
  try {
    const snapshot = await invoke("app_snapshot");
    render(snapshot);
    const active = ["arming", "recording", "stopping", "captured", "transcribing"].includes(snapshot.capture);
    schedulePoll(active ? 400 : 1500);
    return snapshot;
  } catch {
    render({ startup: "diagnostic-written", capture: "idle", error: "The local safety check could not finish." });
    schedulePoll(2000);
    return null;
  }
}

function clearAttemptReview(clearRetention = false) {
  checks.forEach((check) => { check.checked = false; });
  if (clearRetention) retention.value = "";
  updateStartButton();
}

async function dismissAttemptAndReturnFind() {
  if (!invoke) {
    showStartTransitionError();
    return;
  }
  try {
    await invoke("dismiss_meeting");
    clearAttemptReview(true);
    invalidateLibraryHandles();
    const snapshot = await refresh();
    if (snapshot?.capture !== "idle") {
      showStartTransitionError();
      return;
    }
    if (currentScreen !== "find-screen") {
      productRootScreen = "find-screen";
      showScreen("find-screen", { resetScroll: true });
      await refreshFindView();
    }
  } catch {
    showStartTransitionError();
  }
}

async function returnToFindAfterStartError() {
  const currentCapture = lastSnapshot?.capture;
  const currentReady = lastSnapshot?.startup === "ready"
    && lastSnapshot?.preview === true
    && ["idle", "transcript-ready"].includes(currentCapture);
  const snapshot = currentReady ? lastSnapshot : await refresh();
  if (snapshot?.startup !== "ready"
      || snapshot?.preview !== true
      || !["idle", "transcript-ready"].includes(snapshot.capture)) {
    showStartTransitionError();
    return;
  }
  productRootScreen = "find-screen";
  showScreen("find-screen");
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
  clearError(stopError);
  stopButton.disabled = true;
  stopButton.textContent = "Stopping…";
  try {
    await invoke("stop_meeting");
    await refresh();
  } catch (error) {
    setError(stopError, String(error));
    stopButton.disabled = false;
  } finally {
    stopButton.textContent = "Stop recording";
  }
});

document.querySelector("#new-meeting").addEventListener("click", dismissAttemptAndReturnFind);
document.querySelector("#recover-button").addEventListener("click", dismissAttemptAndReturnFind);

retryStartup.addEventListener("click", async () => {
  if (invoke) await invoke("retry_startup");
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
document.querySelector("#library-transcript-back").addEventListener("click", returnToProductHome);
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
document.querySelector("#meeting-open-transcript").addEventListener("click", () => {
  const handle = document.querySelector("#meeting-detail-transcript-handle").value;
  if (handle) openLibraryTranscript(handle);
});

renderStartup("shell-rendered");
refresh();

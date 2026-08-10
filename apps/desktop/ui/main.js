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
  quickControlPresentation,
  commandMenuPresentation,
  helpTopicPresentation,
  shellStatePresentation,
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
import {
  effectiveDesktopLayout,
  normalizeDesktopLayout,
  opensMeetingBesideList,
} from "./layout-preference.mjs";

const shellParams = new window.URLSearchParams(window.location.search);
const rawInvoke = window.__TAURI__?.core?.invoke;
const installedUiReview = Boolean(rawInvoke && shellParams.get("review") === "synthetic");
const invoke = installedUiReview ? null : rawInvoke;
const shellEnvironment = installedUiReview ? "installed-review" : invoke ? "installed" : "browser";
const shellPrototype = installedUiReview || (!rawInvoke && shellParams.has("prototype"));
const requestedNativeCalibration = shellPrototype
  ? shellParams.get("calibration") || "split"
  : "";
const nativeCalibration = requestedNativeCalibration === "wireframe"
  ? ""
  : ["document", "reference"].includes(requestedNativeCalibration)
    ? requestedNativeCalibration
    : shellPrototype || invoke
      ? "split"
      : "";
document.documentElement.dataset.shellEnvironment = shellEnvironment;
if (installedUiReview) document.documentElement.dataset.syntheticReview = "true";
if (nativeCalibration) {
  document.documentElement.dataset.nativeCalibration = nativeCalibration;
  const calibrationTitles = {
    split: "Mac Split",
    document: "Document",
    reference: "Native Reference",
  };
  if (shellPrototype) document.title = `Yawn — ${calibrationTitles[nativeCalibration]}`;
}

const screens = new Map(
  [...document.querySelectorAll(".screen")].map((screen) => [screen.id, screen]),
);
const headerState = document.querySelector("#header-state");
const headerStatus = document.querySelector("#header-status");
const headerStatusDot = document.querySelector("#header-status-dot");
const releaseBadge = document.querySelector("#release-badge");
const meetingLabel = document.querySelector("#meeting-id");
const mainRegion = document.querySelector("main");
const skipLink = document.querySelector(".skip-link");
const startForm = document.querySelector("#start-form");
const startButton = document.querySelector("#start-button");
const startError = document.querySelector("#start-error");
const stopButton = document.querySelector("#stop-button");
const stopError = document.querySelector("#stop-error");
const retryStartup = document.querySelector("#retry-startup");
const startupCopy = document.querySelector("#startup-copy");
const startupStatusCard = document.querySelector("#startup-status-card");
const runtimeStatusIndicator = document.querySelector("#runtime-status-indicator");
const commandMenuTrigger = document.querySelector("#command-menu-trigger");
const commandMenuBackdrop = document.querySelector("#command-menu-backdrop");
const commandMenuClose = document.querySelector("#command-menu-close");
const commandMenuInput = document.querySelector("#command-menu-input");
const commandMenuList = document.querySelector("#command-menu-list");
const commandMenuEmpty = document.querySelector("#command-menu-empty");
const quickControlTrigger = document.querySelector("#quick-control-trigger");
const quickControlTriggerGlyph = document.querySelector("#quick-control-trigger-glyph");
const quickControlTriggerLabel = document.querySelector("#quick-control-trigger-label");
const quickControlPopover = document.querySelector("#quick-control-popover");
const quickControlClose = document.querySelector("#quick-control-close");
const quickControlStatusGlyph = document.querySelector("#quick-control-status-glyph");
const quickControlState = document.querySelector("#quick-control-state");
const quickControlElapsed = document.querySelector("#quick-control-elapsed");
const quickControlDetail = document.querySelector("#quick-control-detail");
const quickControlPrimary = document.querySelector("#quick-control-primary");
const quickControlSecondary = document.querySelector("#quick-control-secondary");
const productNav = document.querySelector("#product-nav");
const findLink = document.querySelector("#find-link");
const meetingsLink = document.querySelector("#meetings-link");
const promisesLink = document.querySelector("#promises-link");
const allMeetingsLink = document.querySelector("#all-meetings-link");
const unfiledMeetingsLink = document.querySelector("#unfiled-meetings-link");
const profileLink = document.querySelector("#profile-link");
const workflowReturn = document.querySelector("#workflow-return");
const startMeetingAction = document.querySelector("#start-meeting-action");
const newMeetingButton = document.querySelector("#new-meeting");
const recoverButton = document.querySelector("#recover-button");
const actionsWorkspacePreview = document.querySelector("#actions-workspace-preview");
const meetingsWorkspacePreview = document.querySelector("#meetings-workspace-preview");
const meetingsRetainedPreview = document.querySelector("#meetings-retained-preview");
const prototypeMeetingBack = document.querySelector("#prototype-meeting-back");
const settingsTabs = [...document.querySelectorAll("[data-settings-tab]")];
const settingsPanels = [...document.querySelectorAll("[data-settings-panel]")];
const settingsRetentionPreview = document.querySelector("#settings-retention-preview");
const settingsRetentionPreviewStatus = document.querySelector("#settings-retention-preview-status");
const settingsReviewAudio = document.querySelector("#settings-review-audio");
const settingsPreviewFirstRun = document.querySelector("#settings-preview-first-run");
const settingsPreviewStates = document.querySelector("#settings-preview-states");
const settingsOpenHelp = document.querySelector("#settings-open-help");
const stateReviewTabs = [...document.querySelectorAll("[data-state-preview]")];
const statePreviewCard = document.querySelector("#state-preview-card");
const statePreviewContext = document.querySelector("#state-preview-context");
const statePreviewTitle = document.querySelector("#state-preview-title");
const statePreviewLede = document.querySelector("#state-preview-lede");
const statePreviewFacts = document.querySelector("#state-preview-facts");
const stateReviewPrimary = document.querySelector("#state-review-primary");
const stateReviewExit = document.querySelector("#state-review-exit");
const stateReviewMeetings = document.querySelector("#state-review-meetings");
const helpTabs = [...document.querySelectorAll("[data-help-topic]")];
const helpTopicCard = document.querySelector("#help-topic-card");
const helpTopicContext = document.querySelector("#help-topic-context");
const helpTopicTitle = document.querySelector("#help-topic-title");
const helpTopicLede = document.querySelector("#help-topic-lede");
const helpTopicFacts = document.querySelector("#help-topic-facts");
const helpTopicPrimary = document.querySelector("#help-topic-primary");
const helpExit = document.querySelector("#help-exit");
const helpMeetings = document.querySelector("#help-meetings");
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
const meetingDetailMeta = document.querySelector("#meeting-detail-meta");
const meetingDetailLede = document.querySelector("#meeting-detail-lede");
const meetingFocusToggle = document.querySelector("#meeting-focus-toggle");
const meetingDockRecord = document.querySelector("#meeting-dock-record");
const meetingContextList = document.querySelector("#meeting-context-list");
const meetingClaimList = document.querySelector("#meeting-claim-list");
const meetingNoNote = document.querySelector("#meeting-no-note");
const meetingNoNoteTitle = document.querySelector("#meeting-no-note-title");
const meetingNoNoteCopy = document.querySelector("#meeting-no-note-copy");
const meetingOpenTranscript = document.querySelector("#meeting-open-transcript");
const meetingTranscriptSummary = document.querySelector("#meeting-transcript-summary");
const meetingActionList = document.querySelector("#meeting-action-list");
const meetingActionEmpty = document.querySelector("#meeting-action-empty");
const meetingEvidenceList = document.querySelector("#meeting-evidence-list");
const meetingEvidenceEmpty = document.querySelector("#meeting-evidence-empty");
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
const preflightRetentionSummary = document.querySelector("#preflight-retention-summary");
const checks = [
  document.querySelector("#consent-check"),
  document.querySelector("#headphones-check"),
  document.querySelector("#room-check"),
];

let lastSnapshot = null;
let lastRenderedCapture = null;
let pollTimer = null;
let startedAt = null;
let elapsedTimer = null;
let meetingAudioDeletionHandle = "";
let meetingDeletionHandle = "";
let retainedMeetingTab = "note";
let meetingContextRows = [];
let activeMeetingId = "";
let meetingContextBusyId = "";
let currentScreen = "startup-screen";
let productRootScreen = "meetings-screen";
let desktopLayoutPreference = "automatic";
let transcriptReturnContext = null;
let routeRevision = 0;
let findNavigationBusy = false;
let findRefreshBusyCount = 0;
let handleNavigationBusy = false;
let workflowOwnsRoute = true;
let stopCommandPending = false;
let stopCommandFailed = false;
let prototypeCaptureStartedAt = 0;
let prototypeCaptureDegraded = false;
let activeSettingsTab = shellPrototype ? "capture" : "voice";
let activeStateReviewId = "loading";
let activeHelpTopicId = "overview";
let helpReturnScreen = "meetings-screen";
let commandMenuReturnFocus = null;
let commandMenuEntries = [];
let commandMenuActiveIndex = 0;
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

function applyDesktopLayout(value) {
  desktopLayoutPreference = normalizeDesktopLayout(value);
  document.documentElement.dataset.layoutPreference = desktopLayoutPreference;
  document.documentElement.dataset.effectiveLayout = effectiveDesktopLayout(
    desktopLayoutPreference,
    window.innerWidth,
  );
}

async function initializeDesktopLayout() {
  if (!invoke) {
    applyDesktopLayout("automatic");
    return;
  }
  const saved = await invoke("get_desktop_layout").catch(() => "automatic");
  applyDesktopLayout(saved);
}

function shouldOpenMeetingBesideList() {
  return opensMeetingBesideList(desktopLayoutPreference, window.innerWidth);
}

applyDesktopLayout("automatic");

function showScreen(id, { resetScroll = false, focus = true } = {}) {
  const destination = screens.get(id);
  if (!destination) return;
  if (id !== "meeting-detail-screen" && shellPrototype) setMeetingFocus(false);
  const routeChanged = currentScreen !== id;
  if (routeChanged) screenScrollPositions.set(currentScreen, mainRegion.scrollTop);
  if (routeChanged) routeRevision += 1;
  currentScreen = id;
  productRootScreen = rootForDestination(id, productRootScreen);
  document.documentElement.dataset.screen = id;
  applyDesktopLayout(desktopLayoutPreference);
  for (const [screenId, screen] of screens) {
    const active = screenId === id;
    screen.classList.toggle("active", active);
    // CSS-only route visibility left a visibly restored selected meeting out of
    // the installed WKWebView accessibility tree after Consent → Back. Keep the
    // DOM visibility state semantic so visual and assistive routes change together.
    screen.hidden = !active;
  }
  // WebKit retains the selected-meeting accessibility subtree when its route is
  // already active, but can lose it after that screen was hidden for Consent.
  // Moving the existing node (not cloning it) refreshes that native tree while
  // preserving listeners, IDs, form state, and the screen registry.
  if (routeChanged) destination.parentElement?.append(destination);
  if (resetScroll) screenScrollPositions.delete(id);
  mainRegion.scrollTop = restoredScrollPosition(screenScrollPositions.get(id), resetScroll);
  syncProductNavigation();
  if (lastSnapshot) renderCaptureAction(lastSnapshot);
  if ((routeChanged || resetScroll) && focus) {
    const focusDestination = () => {
      if (currentScreen !== id || destination.hidden) return;
      const heading = destination.querySelector("h1, h2");
      if (heading) {
        heading.tabIndex = -1;
        heading.focus({ preventScroll: true });
      } else {
        mainRegion.focus({ preventScroll: true });
      }
    };
    focusDestination();
    // WKWebView can retain a CSS-visible route outside its accessibility tree
    // when focus moves in the same task that restores it. Reapply focus after
    // layout, but only while this route still owns the destination.
    window.requestAnimationFrame(focusDestination);
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
  const normalized = text.toLowerCase();
  headerStatus.dataset.state = normalized.includes("recording")
    ? normalized.includes("attention") ? "degraded" : "recording"
    : normalized.includes("transcrib") || normalized.includes("preparing") || normalized.includes("opening")
      ? "processing"
      : normalized.includes("attention") || normalized.includes("could not")
        ? "error"
        : "ready";
}

function setMeetingFocus(focused) {
  const enabled = Boolean(
    shellPrototype
      && focused
      && !["split", "reference"].includes(nativeCalibration),
  );
  document.documentElement.dataset.meetingFocus = enabled ? "true" : "false";
  meetingFocusToggle.setAttribute("aria-pressed", String(enabled));
  meetingFocusToggle.textContent = enabled ? "Show library" : "Focus meeting";
}

function restoreShellSnapshotStatus() {
  if (!shellPrototype || !lastSnapshot) return;
  const startup = lastSnapshot.startup || "diagnostic-written";
  const capture = lastSnapshot.capture || "idle";
  headerStatusDot.dataset.state = headerStatusPresentation(lastSnapshot);
  if (startup !== "ready") setHeaderState("Nothing is recording");
  else if (capture === "idle") setHeaderState("Ready");
  else if (capture === "arming") setHeaderState("Preparing recording");
  else if (capture === "recording") setHeaderState(lastSnapshot.degraded
    ? "Recording · channel needs attention"
    : "Recording · both channels active");
  else if (capture === "stopping") setHeaderState("Stopping and flushing audio");
  else if (["captured", "transcribing"].includes(capture)) setHeaderState("Transcribing locally");
  else if (capture === "transcript-ready") setHeaderState("Transcript ready");
  else setHeaderState("Needs attention");
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

function renderQuickControl(snapshot) {
  const presentation = quickControlPresentation(snapshot);
  quickControlTriggerGlyph.dataset.state = presentation.state;
  quickControlStatusGlyph.dataset.state = presentation.state;
  quickControlTriggerLabel.textContent = presentation.triggerLabel;
  quickControlTrigger.setAttribute(
    "aria-label",
    `Recording status: ${presentation.triggerLabel}. Open quick control.`,
  );
  quickControlState.textContent = presentation.title;
  quickControlDetail.textContent = presentation.detail;
  const showElapsed = ["recording", "degraded"].includes(presentation.state);
  quickControlElapsed.hidden = !showElapsed;
  quickControlPrimary.textContent = presentation.primaryLabel;
  quickControlSecondary.hidden = !presentation.secondaryLabel;
  quickControlSecondary.textContent = presentation.secondaryLabel || "";
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
  document.documentElement.dataset.productNavigation = String(policy.showProductNavigation);
  profileLink.hidden = !policy.showProductNavigation;
  startMeetingAction.hidden = !policy.showStart;
  startMeetingAction.textContent = policy.startLabel;
  stopButton.hidden = !policy.showStop;
  stopButton.disabled = policy.stopDisabled;
  stopButton.textContent = policy.stopLabel;
  workflowReturn.hidden = !policy.showWorkflowReturn;
  workflowReturn.textContent = policy.workflowReturnLabel;
  workflowReturn.dataset.destination = policy.workflowDestination;
  renderQuickControl(snapshot);
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
  const snapshot = await libraryInitialization.run();
  rememberMeetingContext(snapshot);
  return snapshot;
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
  meetingActionList.replaceChildren();
  meetingEvidenceList.replaceChildren();
  document.querySelector("#detail-note").hidden = true;
  meetingNoNote.hidden = true;
  meetingActionEmpty.hidden = true;
  meetingEvidenceEmpty.hidden = true;
  meetingOpenTranscript.hidden = true;
  document.querySelector("#meeting-detail-transcript-handle").value = "";
  meetingAudioDeletionHandle = "";
  meetingDeletionHandle = "";
  recordingDeleteAction.hidden = true;
  meetingDeleteAction.hidden = true;
  closeRecordingDeleteReview();
  closeMeetingDeleteReview();
}

// The context pane keeps presentation metadata only. A library snapshot's
// handles belong to that one backend projection and become stale as soon as a
// meeting is opened. Switching by durable meeting ID lets us request a fresh
// row and use only the handle minted by that request.
function rememberMeetingContext(snapshot) {
  if (!["populated", "populated-incomplete", "empty"].includes(snapshot?.state)) return;
  meetingContextRows = (snapshot.rows || []).map((row) => ({
    meetingId: row.meetingId || "",
    label: row.label || "",
    labelSource: row.labelSource || "date",
    createdAtEpochSeconds: row.createdAtEpochSeconds,
    transcriptAvailable: Boolean(row.transcriptAvailable),
  })).filter((row) => row.meetingId);
  renderMeetingContextList();
}

function renderMeetingContextList() {
  meetingContextList.replaceChildren();
  if (!meetingContextRows.length) {
    const empty = document.createElement("p");
    empty.className = "meeting-context-empty ys-empty-row";
    empty.textContent = "No other retained meetings are available in this view.";
    meetingContextList.append(empty);
    return;
  }
  for (const row of meetingContextRows) {
    const captured = formatMeetingTime(row.createdAtEpochSeconds);
    const labelText = row.label || captured;
    const selected = row.meetingId === activeMeetingId;
    const button = document.createElement("button");
    button.type = "button";
    button.className = "meeting-context-row ys-meeting-row";
    button.dataset.meetingId = row.meetingId;
    button.setAttribute("aria-current", selected ? "page" : "false");
    button.disabled = Boolean(meetingContextBusyId);
    button.addEventListener("click", () => {
      if (selected) {
        meetingDetailTitle.focus({ preventScroll: true });
        return;
      }
      void openMeetingByIdFresh(row.meetingId, button);
    });
    const copy = document.createElement("span");
    copy.className = "ys-row-copy";
    const label = document.createElement("strong");
    label.textContent = labelText;
    const meta = document.createElement("small");
    const notes = [];
    if (row.labelSource !== "date") notes.push(captured);
    if (!row.transcriptAvailable) notes.push("No transcript");
    meta.textContent = notes.join(" · ");
    meta.hidden = notes.length === 0;
    copy.append(label, meta);
    const state = document.createElement("span");
    state.textContent = row.meetingId === meetingContextBusyId
      ? "Opening…"
      : selected ? "Current" : "Open";
    button.append(copy, state);
    meetingContextList.append(button);
  }
}

function setError(element, message) {
  element.textContent = message || "The operation could not complete.";
  element.hidden = false;
}

function clearError(element) {
  element.textContent = "";
  element.hidden = true;
}

// Search uses the shared inline-notice grammar, but its states are not all
// failures. A useful empty result, a partial corpus, and a failed local command
// need different tones without changing the retrieval command's fixed state.
function searchNoticeTone(state) {
  if (["results-incomplete", "incomplete", "nothing-prepared", "busy"].includes(state)) {
    return "warning";
  }
  if (["unavailable", "worker-unavailable", "model-mismatch", "reply-incomplete"].includes(state)) {
    return "error";
  }
  return "information";
}

function setSearchNotice(element, messageText, tone = "information") {
  element.dataset.tone = tone;
  setError(element, messageText);
}

function clearSearchNotice(element) {
  element.dataset.tone = "information";
  clearError(element);
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

function updatePreflightRetentionSummary() {
  const days = Number(retention.value);
  preflightRetentionSummary.textContent = days > 0
    ? `Delete meeting audio after ${days} ${days === 1 ? "day" : "days"}. The transcript remains.`
    : "Choose how long it stays on this Mac.";
}

function prototypeCaptureSnapshot(capture, overrides = {}) {
  return {
    startup: "ready",
    capture,
    retention_operational: true,
    meeting_id: "prototype-capture",
    started_at_epoch_seconds: prototypeCaptureStartedAt,
    degraded: prototypeCaptureDegraded,
    mic_state: "Active",
    system_state: prototypeCaptureDegraded ? "Unavailable" : "Active",
    turns: [],
    warnings: [],
    ...overrides,
  };
}

function renderPrototypeCapture(capture, overrides = {}) {
  render(prototypeCaptureSnapshot(capture, overrides));
}

function finishPrototypeTranscript() {
  renderPrototypeCapture("transcript-ready", {
    turns: [
      { sourceTurnIndex: 0, speaker: "Them", start: 4, text: "Let’s keep the pilot to one customer for two weeks." },
      { sourceTurnIndex: 1, speaker: "Me", start: 11, text: "I’ll schedule the review for Friday and bring the handoff notes." },
      { sourceTurnIndex: 2, speaker: "Them", start: 19, text: "That works. Legal still needs to clear the sample data first." },
    ],
  });
}

function leavePrototypeCapture(destination = "meetings-screen") {
  endElapsed();
  clearAttemptReview(true);
  resetLiveNote();
  prototypeCaptureDegraded = false;
  lastSnapshot = prototypeCaptureSnapshot("idle", { meeting_id: null });
  setHeaderState("Click-through prototype · nothing is recording");
  selectProductScreen(destination, { resetScroll: true });
}

function formatElapsed(seconds) {
  const safe = Math.max(0, Math.floor(seconds));
  return `${String(Math.floor(safe / 60)).padStart(2, "0")}:${String(safe % 60).padStart(2, "0")}`;
}

function beginElapsed(epochSeconds) {
  startedAt = Number(epochSeconds) * 1000;
  const render = () => {
    const elapsed = installedUiReview ? 18 : startedAt ? (Date.now() - startedAt) / 1000 : 0;
    const elapsedText = formatElapsed(elapsed);
    document.querySelector("#elapsed-time").textContent = elapsedText;
    quickControlElapsed.textContent = elapsedText;
  };
  render();
  if (!installedUiReview && !elapsedTimer) elapsedTimer = window.setInterval(render, 1000);
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
  matched.className = "ys-transcript__match";
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
    row.className = "ys-transcript__turn";
    if (turn.withheld) {
      row.classList.add("ys-transcript__turn--withheld");
      const meta = document.createElement("div");
      meta.className = "ys-transcript__meta";
      const speaker = document.createElement("strong");
      speaker.textContent = "Withheld";
      const time = document.createElement("time");
      time.textContent = formatElapsed(turn.start || 0);
      meta.append(speaker, time);
      const note = document.createElement("p");
      note.className = "ys-transcript__withheld-note";
      note.textContent = "A voice check withheld this turn's text.";
      row.append(meta, note);
      if (restore) {
        const action = document.createElement("button");
        action.type = "button";
        action.className = "secondary ys-button ys-transcript__restore";
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
      row.classList.add("ys-transcript__turn--match");
      row.dataset.sourceTurnIndex = String(match.sourceTurnIndex);
      row.tabIndex = -1;
      row.setAttribute("aria-label", `Exact transcript match in turn ${match.sourceTurnIndex + 1}`);
    }
    const meta = document.createElement("div");
    meta.className = "ys-transcript__meta";
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
    empty.className = "ys-transcript__empty";
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
  recordingDeleteConfirm.disabled = shellPrototype;
  recordingDeleteConfirm.textContent = shellPrototype
    ? "Deletion unavailable in shell"
    : "Permanently delete recording";
}

function closeMeetingDeleteReview() {
  meetingDeleteConfirmation.hidden = true;
  meetingDeleteStatus.hidden = true;
  meetingDeleteStatus.textContent = "";
  meetingDeleteConfirm.disabled = shellPrototype;
  meetingDeleteConfirm.textContent = shellPrototype
    ? "Deletion unavailable in shell"
    : "Permanently delete meeting";
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
  rememberMeetingContext(snapshot);
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
    empty.className = "library-empty ys-empty-row";
    empty.textContent = snapshot.state === "empty"
      ? "No retained meetings yet. Finish a recording to see it here."
      : snapshot.state === "unavailable"
        ? "Meetings are not available yet. No retained meeting or transcript was opened."
        : "Some retained meetings could not be read. Try loading Meetings again.";
    libraryList.append(empty);
    return;
  }
  for (const row of snapshot.rows || []) {
    const item = document.createElement("article");
    item.className = "library-item";
    const button = document.createElement("button");
    button.type = "button";
    button.className = "library-row ys-meeting-row";
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
    item.append(button);

    // Rename sits outside the row button rather than inside it: a button in a
    // button does not nest, and the whole row already means "open this".
    // A null revision means the record could not be read, and renaming is
    // withheld rather than attempted against a revision nobody knows.
    if (Number.isInteger(snapshot.metadataRevision)) {
      const actions = document.createElement("details");
      actions.className = "library-item-actions";
      const actionsLabel = document.createElement("summary");
      actionsLabel.textContent = "More";
      actionsLabel.setAttribute("aria-label", `More actions for ${labelText}`);
      const actionControls = document.createElement("div");
      actionControls.className = "library-item-action-controls";
      const rename = document.createElement("button");
      rename.type = "button";
      rename.className = "library-rename";
      rename.dataset.meetingId = row.meetingId || "";
      rename.textContent = labelSource === "operator" ? "Rename" : "Name this meeting";
      rename.addEventListener("click", () => renameMeeting(row, snapshot.metadataRevision));

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
      actionControls.append(rename, move);
      actions.append(actionsLabel, actionControls);
      item.append(actions);
    }
    libraryList.append(item);
  }
}

function renderLibrarySearch(response) {
  librarySearchResults.replaceChildren();
  findStart.hidden = true;
  clearSearchNotice(libraryNotice);
  if (response.state !== "results" && response.state !== "results-incomplete") {
    setSearchNotice(
      libraryNotice,
      response.message || "No retained text matched that search.",
      searchNoticeTone(response.state),
    );
    return;
  }
  for (const result of response.results || []) {
    const metadataOnly = result.kind === "meeting" && result.transcriptAvailable !== true;
    const row = document.createElement(metadataOnly ? "div" : "button");
    row.className = "ys-search__result";
    row.dataset.kind = result.kind || "unknown";
    if (metadataOnly) {
      row.dataset.state = "metadata-only";
    } else {
      row.type = "button";
      row.dataset.searchHandle = result.handle;
      row.addEventListener("click", () => openLibrarySearchResult(result.handle, row));
    }
    const summary = document.createElement("span");
    summary.className = "ys-search__result-copy";
    const label = document.createElement("strong");
    label.className = "ys-search__result-title";
    const detail = document.createElement("span");
    detail.className = "ys-search__result-meta";
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
    action.className = "ys-search__result-action";
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
  setSearchNotice(
    libraryNotice,
    resultMessage || "Exact results from your retained meetings.",
    searchNoticeTone(response.state),
  );
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
    setSearchNotice(
      corpusNotice,
      response.message || "That description could not be searched.",
      searchNoticeTone(response.state),
    );
    return;
  }
  for (const answer of response.answers || []) {
    const openable = Boolean(answer.transcriptHandle);
    const row = document.createElement(openable ? "button" : "div");
    row.className = "ys-search__result ys-search__result--passage";
    row.dataset.kind = "passage";
    if (openable) {
      row.type = "button";
      row.dataset.transcriptHandle = answer.transcriptHandle;
      row.addEventListener("click", () => openCorpusAnswer(answer, row));
    } else {
      row.dataset.state = "unopenable";
    }
    const label = document.createElement("strong");
    label.className = "ys-search__result-title";
    label.textContent = corpusAnswerLabel(answer);
    const where = document.createElement("small");
    where.className = "ys-search__result-meta";
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
    quote.className = "ys-search__quote";
    quote.textContent = answer.quote;
    const action = document.createElement("span");
    action.className = "ys-search__result-action";
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
  setSearchNotice(
    corpusNotice,
    `${response.message || "Meetings that match that description."}${crowding}`,
    searchNoticeTone(response.state),
  );
}

async function searchCorpus(event) {
  event.preventDefault();
  if (shellPrototype) {
    setSearchNotice(corpusNotice, "The browser shell has no retained passages to search. Nothing was queried or invented.");
    return false;
  }
  if (!invoke) return false;
  const revision = routeRevision;
  const ownsRoute = () => currentScreen === "find-screen" && routeRevision === revision;
  const question = corpusSearchQuestion.value.trim();
  corpusSearchResults.replaceChildren();
  corpusCoverage.hidden = true;
  if (!question) {
    setSearchNotice(corpusNotice, "Describe what the meeting was about.");
    return false;
  }
  corpusSearchSubmit.disabled = true;
  setSearchNotice(corpusNotice, "Searching by meaning on this Mac\u2026");
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
      setSearchNotice(corpusNotice, "Meaning search is unavailable right now. Exact word search still works.", "error");
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
  const returnContext = transcriptReturnRoute("find", "", { findFocus: "meaning" });
  return await openLibraryTranscript(
    answer.transcriptHandle,
    // Land on the turn the passage starts at. The store cites character ranges
    // too, and this does not carry them: the exact path uses them to highlight
    // one matched phrase, and a passage is 128 words with no phrase to point at.
    { sourceTurnIndex: answer.firstTurnIndex, start: null, end: null },
    returnContext,
    transition,
  );
}

async function prepareCorpusPassages() {
  if (shellPrototype) {
    setSearchNotice(corpusNotice, "The browser shell has no retained meetings to prepare. The installed app performs this work locally.");
    return false;
  }
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
        setSearchNotice(corpusNotice, `All ${result.windows} passages are prepared. Ask your question again.`, "success");
        return true;
      }
      if (result.stop !== "budget") {
        setSearchNotice(corpusNotice, corpusPrepareFailure(result.stop), result.stop === "busy" ? "warning" : "error");
        return false;
      }
      setSearchNotice(corpusNotice, `Preparing on this Mac \u2014 ${result.covered} of ${result.windows} passages done\u2026`);
    }
    setSearchNotice(corpusNotice, "Preparing stopped part-way. Run it again to continue where it left off.", "warning");
    return false;
  } catch {
    if (ownsRoute()) setSearchNotice(corpusNotice, "Preparing is unavailable right now. Try again.", "error");
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
    "shell-rendered": {
      heading: "Opening the local shell",
      badge: "Opening",
      tone: "processing",
      copy: "The window opens before any audio or model process starts.",
    },
    checking: {
      heading: "Checking bundled files",
      badge: "Checking",
      tone: "processing",
      copy: "Recording stays unavailable until the local components answer.",
    },
    "runtime-missing": {
      heading: "This installation is incomplete",
      badge: "Reinstall required",
      tone: "error",
      copy: "A bundled local component is missing. Nothing is recording; restore this installation, then check again.",
    },
    "service-timeout": {
      heading: "The local worker did not answer",
      badge: "Check again",
      tone: "warning",
      copy: "Nothing is recording. Checking again reruns the local startup check without opening a meeting.",
    },
    "diagnostic-written": {
      heading: "A private diagnostic was saved",
      badge: "Needs attention",
      tone: "error",
      copy: "Yawn stopped before opening a meeting and did not mark anything complete. Check again to rerun the local startup check.",
    },
    retrying: {
      heading: "Checking bundled files again",
      badge: "Checking",
      tone: "processing",
      copy: "The same local installation is being checked again. Recording stays unavailable until it finishes.",
    },
    "reinstall-required": {
      heading: "This installation must be repaired",
      badge: "Reinstall required",
      tone: "error",
      copy: "The local check could not repair this installation. Reinstall Yawn, then open it again; nothing is recording.",
    },
  };
  const { heading, badge, tone, copy } = labels[state] || labels["diagnostic-written"];
  document.querySelector("#runtime-status").textContent = heading;
  document.querySelector("#runtime-pill").textContent = badge;
  runtimeStatusIndicator.dataset.state = tone;
  startupStatusCard.dataset.tone = tone;
  startupCopy.textContent = copy;
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
  const previousCapture = lastRenderedCapture;
  lastRenderedCapture = capture;
  document.documentElement.dataset.startupState = startup;
  document.documentElement.dataset.captureState = capture;
  document.documentElement.dataset.connectionState = "connected";
  headerStatusDot.dataset.state = headerStatusPresentation(snapshot);
  releaseBadge.textContent = shellPrototype ? "Shell preview" : "Preview";
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
        const destination = showWorkflowScreen(snapshot, { resetScroll: true });
        if (destination === "meetings-screen") void openMeetings();
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
        if (["captured", "transcribing"].includes(previousCapture)) {
          void handoffCompletedCapture(snapshot);
        } else {
          void openMeetings({ preferredMeetingId: snapshot.meeting_id || "" });
        }
      }
      break;
    default:
      setHeaderState("Needs attention");
      endElapsed();
      document.querySelector("#error-detail").textContent = snapshot.error || "The attempt stopped before a validated transcript was ready.";
      showWorkflowScreen(snapshot, { resetScroll: currentScreen !== "error-screen" });
  }
}

async function handoffCompletedCapture(snapshot) {
  const meetingId = snapshot?.meeting_id || "";
  if (!meetingId) {
    renderTranscript(snapshot);
    showScreen("transcript-screen", { resetScroll: true });
    return;
  }
  const opened = await openMeetingByIdFresh(meetingId);
  if (!opened) return;
  selectRetainedMeetingTab("transcript", { focus: true, reveal: true });
  message(
    meetingDetailState,
    "Transcript ready. This retained meeting is selected; open the source words below.",
    "ready",
  );
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

async function rebuildMeetingsView({ selectDefault = false, preferredMeetingId = "" } = {}) {
  if (!invoke) return;
  document.querySelector("#library-copy").textContent = "Opening retained meetings on this Mac.";
  invalidateLibraryHandles();
  const revision = routeRevision;
  try {
    const snapshot = await initializeLibraryReader();
    if (currentScreen !== "meetings-screen" || routeRevision !== revision) return;
    renderLibrary(snapshot);
    if (selectDefault && Array.isArray(snapshot.rows) && snapshot.rows.length) {
      const row = rowForMeetingId(snapshot, preferredMeetingId) || snapshot.rows[0];
      const control = [...libraryList.querySelectorAll(".library-row")]
        .find((candidate) => candidate.dataset.meetingId === row.meetingId) || null;
      await openMeetingDetail(row.handle, "meetings-screen", control);
      return;
    }
    await refreshRetentionOverview(revision);
  } catch {
    if (currentScreen !== "meetings-screen" || routeRevision !== revision) return;
    renderLibrary({ state: "unavailable", rows: [], message: "Meetings are unavailable right now." });
    renderRetentionOverview(null);
  }
}

async function openFind({ resetQuery = false } = {}) {
  if (!invoke && !shellPrototype) return;
  restoreShellSnapshotStatus();
  if (resetQuery) librarySearchQuery.value = "";
  selectProductScreen("find-screen");
  if (invoke) await refreshFindView();
}

async function openMeetings({ resetFind = false, browseAll = false, preferredMeetingId = "" } = {}) {
  if (!invoke && !shellPrototype) return;
  restoreShellSnapshotStatus();
  if (resetFind) librarySearchQuery.value = "";
  if (shellPrototype && !browseAll) {
    openPrototypeMeetingDetail(activeMeetingId || "prototype-meeting", { focus: true });
    return;
  }
  selectProductScreen("meetings-screen");
  if (invoke) {
    await rebuildMeetingsView({
      selectDefault: !browseAll && shouldOpenMeetingBesideList(),
      preferredMeetingId,
    });
  }
}

async function openPromises({ resetFind = false } = {}) {
  restoreShellSnapshotStatus();
  if (resetFind) librarySearchQuery.value = "";
  invalidateLibraryHandles();
  selectProductScreen("promises-screen", { resetScroll: true });
}

function showStartTransitionError() {
  startTransitionError.textContent = "The current meeting could not be closed safely. A new consent form was not opened. Return to Meetings and try again.";
  showScreen("start-meeting-error-screen", { resetScroll: true });
}

async function openStartMeeting() {
  if (shellPrototype) {
    beginWorkflowRoute();
    prototypeCaptureDegraded = false;
    lastSnapshot = prototypeCaptureSnapshot("idle", { meeting_id: null });
    renderCaptureAction(lastSnapshot);
    setHeaderState("Click-through prototype · nothing is recording");
    clearAttemptReview(true);
    clearError(startError);
    showScreen("idle-screen", { resetScroll: true });
    return;
  }
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
    startMeetingAction.textContent = lastSnapshot?.capture === "transcript-ready"
      ? "Record another meeting"
      : "Record a meeting";
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

async function openProfile({ pane } = {}) {
  const requestedPane = pane === "voice" ? pane : null;
  if (shellPrototype) {
    if (requestedPane) activeSettingsTab = requestedPane;
    restoreShellSnapshotStatus();
    selectProductScreen("profile-screen", { resetScroll: true });
    selectSettingsPanel(activeSettingsTab);
    return;
  }
  if (!invoke) return;
  if (requestedPane) {
    try {
      localStorage.setItem("yawn-settings:last-pane", requestedPane);
    } catch {
      // Settings can safely use its own saved pane when storage is unavailable.
    }
  }
  try {
    await invoke("open_settings_window");
    return;
  } catch {
    // Preview builds that do not admit the production Settings command retain
    // the existing measured voice-profile route instead of losing access.
  }
  selectProductScreen("profile-screen", { resetScroll: true });
  selectSettingsPanel(requestedPane || "voice");
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

function selectSettingsPanel(tabName, { focusTab = false } = {}) {
  const tab = settingsTabs.find((candidate) => candidate.dataset.settingsTab === tabName);
  if (!tab || (tab.classList.contains("prototype-only") && !shellPrototype)) return;
  activeSettingsTab = tabName;
  for (const candidate of settingsTabs) {
    const selected = candidate === tab;
    candidate.setAttribute("aria-selected", String(selected));
    candidate.tabIndex = selected ? 0 : -1;
  }
  for (const panel of settingsPanels) {
    panel.hidden = panel.dataset.settingsPanel !== tabName;
  }
  if (shellPrototype && tabName === "voice") {
    profileStatusTitle.textContent = "Setup unavailable in this browser shell";
    profileStatusCopy.textContent = "The installed app reads private setup status and enforces its measured voice-profile gates. This prototype does not open or store setup audio.";
    profileRecorderEntry.textContent = "Install-level setup recording is not connected in this browser representation.";
    profileSetup.disabled = true;
  }
  if (focusTab) tab.focus();
}

function moveSettingsTab(currentTab, direction) {
  const available = settingsTabs.filter((tab) => (
    shellPrototype || !tab.classList.contains("prototype-only")
  ));
  const currentIndex = available.indexOf(currentTab);
  if (currentIndex < 0) return;
  const next = available[(currentIndex + direction + available.length) % available.length];
  selectSettingsPanel(next.dataset.settingsTab, { focusTab: true });
}

function renderStateReview(stateId, { focusTab = false } = {}) {
  const presentation = shellStatePresentation(stateId);
  activeStateReviewId = presentation.id;
  const selectedTab = stateReviewTabs.find((tab) => tab.dataset.statePreview === presentation.id);
  for (const tab of stateReviewTabs) {
    const selected = tab === selectedTab;
    tab.setAttribute("aria-selected", String(selected));
    tab.tabIndex = selected ? 0 : -1;
  }
  statePreviewCard.dataset.tone = presentation.tone;
  statePreviewCard.setAttribute("aria-labelledby", selectedTab.id);
  statePreviewContext.textContent = presentation.context;
  statePreviewTitle.textContent = presentation.title;
  statePreviewLede.textContent = presentation.lede;
  stateReviewPrimary.textContent = presentation.primaryLabel;
  stateReviewPrimary.dataset.action = presentation.primaryAction;
  statePreviewFacts.replaceChildren(...presentation.facts.map(([term, value, detail]) => {
    const row = document.createElement("div");
    const label = document.createElement("dt");
    label.textContent = term;
    const description = document.createElement("dd");
    const title = document.createElement("strong");
    title.textContent = value;
    const copy = document.createElement("span");
    copy.textContent = detail;
    description.append(title, copy);
    row.append(label, description);
    return row;
  }));
  if (focusTab) selectedTab.focus();
}

function openStateReview() {
  if (!shellPrototype) return;
  claimExplicitRoute();
  renderStateReview(activeStateReviewId);
  setHeaderState("System-state preview · nothing is recording");
  showScreen("state-review-screen", { resetScroll: true });
}

function renderHelpTopic(topicId, { focusTab = false } = {}) {
  const presentation = helpTopicPresentation(topicId);
  activeHelpTopicId = presentation.id;
  const selectedTab = helpTabs.find((tab) => tab.dataset.helpTopic === presentation.id);
  for (const tab of helpTabs) {
    const selected = tab === selectedTab;
    tab.setAttribute("aria-selected", String(selected));
    tab.tabIndex = selected ? 0 : -1;
  }
  helpTopicCard.setAttribute("aria-labelledby", selectedTab.id);
  helpTopicContext.textContent = presentation.context;
  helpTopicTitle.textContent = presentation.title;
  helpTopicLede.textContent = presentation.lede;
  helpTopicPrimary.textContent = presentation.primaryLabel;
  helpTopicPrimary.dataset.action = presentation.primaryAction;
  helpTopicFacts.replaceChildren(...presentation.facts.map(([term, value, detail]) => {
    const row = document.createElement("div");
    const label = document.createElement("dt");
    label.textContent = term;
    const description = document.createElement("dd");
    const title = document.createElement("strong");
    title.textContent = value;
    const copy = document.createElement("span");
    copy.textContent = detail;
    description.append(title, copy);
    row.append(label, description);
    return row;
  }));
  if (focusTab) selectedTab.focus();
}

function openHelp() {
  if (!shellPrototype) return;
  if (currentScreen !== "help-screen") helpReturnScreen = currentScreen;
  claimExplicitRoute();
  renderHelpTopic(activeHelpTopicId);
  setHeaderState("Help · nothing is recording");
  showScreen("help-screen", { resetScroll: true });
}

function moveHelpTab(currentTab, direction) {
  const currentIndex = helpTabs.indexOf(currentTab);
  if (currentIndex < 0) return;
  const next = helpTabs[(currentIndex + direction + helpTabs.length) % helpTabs.length];
  renderHelpTopic(next.dataset.helpTopic, { focusTab: true });
}

function runHelpAction(action) {
  if (action === "start") void openStartMeeting();
  else if (action === "setup") openPrototypeFirstRun();
  else if (action === "privacy") {
    activeSettingsTab = "privacy";
    restoreShellSnapshotStatus();
    void openProfile();
  } else if (action === "states") {
    activeStateReviewId = "repair";
    openStateReview();
  } else if (action === "about") {
    activeSettingsTab = "about";
    restoreShellSnapshotStatus();
    void openProfile();
  }
}

function closeHelp() {
  restoreShellSnapshotStatus();
  if (helpReturnScreen === "profile-screen") {
    void openProfile();
    return;
  }
  void returnToProductRoot();
}

function moveStateReviewTab(currentTab, direction) {
  const currentIndex = stateReviewTabs.indexOf(currentTab);
  if (currentIndex < 0) return;
  const next = stateReviewTabs[(currentIndex + direction + stateReviewTabs.length) % stateReviewTabs.length];
  renderStateReview(next.dataset.statePreview, { focusTab: true });
}

function runStateReviewPrimary() {
  const action = stateReviewPrimary.dataset.action;
  if (action === "start") void openStartMeeting();
  else if (action === "meetings") void openMeetings({ resetFind: true });
  else if (action === "loading") renderStateReview("loading");
}

async function returnToProductRoot() {
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

async function returnToWorkflow() {
  if (!lastSnapshot) return;
  if (lastSnapshot.capture === "transcript-ready") {
    await handoffCompletedCapture(lastSnapshot);
    return;
  }
  const routeToken = beginWorkflowRoute();
  if (!workflowRouteIsCurrent(routeToken)) return;
  showWorkflowScreen(lastSnapshot, { resetScroll: true });
}

function setCommandMenuActiveIndex(nextIndex, { reveal = false } = {}) {
  if (!commandMenuEntries.length) {
    commandMenuActiveIndex = 0;
    commandMenuInput.removeAttribute("aria-activedescendant");
    return;
  }
  commandMenuActiveIndex = (nextIndex + commandMenuEntries.length) % commandMenuEntries.length;
  commandMenuEntries.forEach(({ button }, index) => {
    const active = index === commandMenuActiveIndex;
    button.dataset.active = String(active);
    button.setAttribute("aria-selected", String(active));
  });
  const activeButton = commandMenuEntries[commandMenuActiveIndex].button;
  commandMenuInput.setAttribute("aria-activedescendant", activeButton.id);
  if (reveal) activeButton.scrollIntoView({ block: "nearest" });
}

function renderCommandMenu() {
  const query = commandMenuInput.value.trim().toLocaleLowerCase();
  const commands = commandMenuPresentation(lastSnapshot).filter((command) => (
    `${command.label} ${command.detail}`.toLocaleLowerCase().includes(query)
  ));
  commandMenuList.replaceChildren();
  commandMenuEntries = commands.map((command) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "command-menu-row";
    button.id = `command-option-${command.id}`;
    button.setAttribute("role", "option");
    button.dataset.commandId = command.id;

    const copy = document.createElement("span");
    copy.className = "command-menu-copy";
    const label = document.createElement("strong");
    label.textContent = command.label;
    const detail = document.createElement("small");
    detail.textContent = command.detail;
    copy.append(label, detail);

    const meta = document.createElement("span");
    meta.className = "command-menu-meta";
    if (command.planned) {
      const planned = document.createElement("span");
      planned.className = "command-menu-planned";
      planned.textContent = "Planned";
      meta.append(planned);
    }
    if (command.shortcut) {
      const shortcut = document.createElement("kbd");
      shortcut.setAttribute("aria-hidden", "true");
      shortcut.textContent = command.shortcut;
      meta.append(shortcut);
    }
    button.append(copy, meta);
    button.addEventListener("mouseenter", () => {
      const index = commandMenuEntries.findIndex((entry) => entry.button === button);
      if (index >= 0) setCommandMenuActiveIndex(index);
    });
    button.addEventListener("click", () => runShellCommand(command));
    commandMenuList.append(button);
    return { command, button };
  });
  commandMenuEmpty.hidden = commandMenuEntries.length > 0;
  setCommandMenuActiveIndex(0);
}

function closeCommandMenu({ restoreFocus = true } = {}) {
  commandMenuBackdrop.hidden = true;
  commandMenuTrigger.setAttribute("aria-expanded", "false");
  commandMenuInput.removeAttribute("aria-activedescendant");
  if (restoreFocus && commandMenuReturnFocus?.isConnected) commandMenuReturnFocus.focus();
  commandMenuReturnFocus = null;
}

function openCommandMenu() {
  if (!shellPrototype) return;
  closeQuickControl();
  commandMenuReturnFocus = document.activeElement;
  commandMenuInput.value = "";
  renderCommandMenu();
  commandMenuBackdrop.hidden = false;
  commandMenuTrigger.setAttribute("aria-expanded", "true");
  commandMenuInput.focus();
}

function runShellCommand(command) {
  closeCommandMenu({ restoreFocus: false });
  if (command.action === "meetings") void openMeetings({ resetFind: true });
  else if (command.action === "ask") void openFind({ resetQuery: true });
  else if (command.action === "actions") void openPromises({ resetFind: true });
  else if (command.action === "settings") void openProfile();
  else if (command.action === "desktop") {
    activeSettingsTab = "desktop";
    void openProfile();
  }
  else if (command.action === "setup") openPrototypeFirstRun();
  else if (command.action === "states") openStateReview();
  else if (command.action === "help") openHelp();
  else if (command.action === "start") void openStartMeeting();
  else if (command.action === "workflow") returnToWorkflow();
  else if (command.action === "stop") stopButton.click();
}

function runShellCommandById(commandId) {
  const command = commandMenuPresentation(lastSnapshot).find((entry) => entry.id === commandId);
  if (command) runShellCommand(command);
}

function closeQuickControl({ restoreFocus = false } = {}) {
  quickControlPopover.hidden = true;
  quickControlTrigger.setAttribute("aria-expanded", "false");
  if (restoreFocus) quickControlTrigger.focus();
}

function openQuickControl() {
  renderQuickControl(lastSnapshot);
  quickControlPopover.hidden = false;
  quickControlTrigger.setAttribute("aria-expanded", "true");
  quickControlPrimary.focus();
}

function runQuickControlPrimary() {
  closeQuickControl();
  if ((lastSnapshot?.capture || "idle") === "idle") {
    void openStartMeeting();
    return;
  }
  returnToWorkflow();
}

function runQuickControlSecondary() {
  closeQuickControl();
  if (lastSnapshot?.capture === "recording") {
    stopButton.click();
    return;
  }
  if (lastSnapshot?.capture === "transcript-ready") void openStartMeeting();
}

function reportLibraryOpenFailure(messageText) {
  if (currentScreen === "meeting-detail-screen") {
    message(meetingDetailState, messageText, "stale");
    return;
  }
  setSearchNotice(libraryNotice, messageText, "error");
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

function selectRetainedMeetingTab(tabName, { focus = false, reveal = false } = {}) {
  const validTabs = ["note", "transcript", "actions", "evidence", "details"];
  retainedMeetingTab = validTabs.includes(tabName) ? tabName : "note";
  for (const tab of document.querySelectorAll("[data-retained-meeting-tab]")) {
    const selected = tab.dataset.retainedMeetingTab === retainedMeetingTab;
    tab.setAttribute("aria-selected", String(selected));
    tab.tabIndex = selected ? 0 : -1;
    if (selected && focus) tab.focus({ preventScroll: true });
  }
  let activePanel = null;
  for (const panel of document.querySelectorAll("[data-retained-meeting-panel]")) {
    const active = panel.dataset.retainedMeetingPanel === retainedMeetingTab;
    panel.hidden = !active;
    panel.classList.toggle("active", active);
    if (active) activePanel = panel;
  }
  if (reveal && activePanel) {
    activePanel.scrollIntoView({
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
      block: "start",
    });
  }
}

function appendMeetingClaim(target, claim, response, index, sourceTab, variant = "note") {
  const card = document.createElement("article");
  card.className = variant === "action"
    ? "meeting-action-card"
    : variant === "evidence"
      ? "meeting-evidence-card"
      : "meeting-claim";
  const meta = document.createElement("p");
  meta.className = "claim-meta";
  meta.textContent = variant === "action"
    ? "Action"
    : claimTypeLabel(claim.claimType);
  const text = document.createElement("p");
  text.className = "claim-text";
  text.textContent = claim.claim;
  const open = document.createElement("button");
  open.type = "button";
  open.className = "secondary claim-evidence";
  open.dataset.claimOrdinal = String(claim.ordinal);
  open.dataset.claimIndex = String(index);
  open.textContent = shellPrototype
    ? sourceTab === "evidence" ? "Show excerpt" : "View source"
    : "View in transcript";
  let prototypeEvidencePreview = null;
  if (shellPrototype && sourceTab === "evidence") {
    prototypeEvidencePreview = document.createElement("blockquote");
    prototypeEvidencePreview.className = "prototype-evidence-preview";
    prototypeEvidencePreview.hidden = true;
    const quote = document.createElement("p");
    quote.textContent = `“${claim.evidenceText || "Synthetic source words are not available for this claim."}”`;
    const source = document.createElement("span");
    source.textContent = `Synthetic transcript · ${claim.evidenceSpeaker || "Speaker"} · ${claim.evidenceTime || "time unavailable"}`;
    prototypeEvidencePreview.append(quote, source);
    open.setAttribute("aria-expanded", "false");
  }
  open.addEventListener("click", () => {
    if (shellPrototype) {
      if (sourceTab === "evidence") {
        const expanded = prototypeEvidencePreview.hidden;
        prototypeEvidencePreview.hidden = !expanded;
        open.setAttribute("aria-expanded", String(expanded));
        open.textContent = expanded ? "Hide excerpt" : "Show excerpt";
      } else {
        selectRetainedMeetingTab("evidence", { focus: true, reveal: true });
      }
      return;
    }
    openMeetingEvidence(
      claim.handle,
      response.meetingId,
      claim,
      open,
      sourceTab,
    );
  });
  card.append(meta, text, open);
  if (prototypeEvidencePreview) card.append(prototypeEvidencePreview);
  target.append(card);
}

function renderMeetingDetail(response) {
  renderDetailNote(response?.operatorNote);
  const presentation = meetingDetailPresentation(response);
  meetingClaimList.replaceChildren();
  meetingActionList.replaceChildren();
  meetingEvidenceList.replaceChildren();
  meetingNoNote.hidden = true;
  meetingActionEmpty.hidden = true;
  meetingEvidenceEmpty.hidden = true;
  const selectedContext = meetingContextRows.find((row) => row.meetingId === response.meetingId);
  meetingDetailTitle.textContent = selectedContext?.label
    || (selectedContext ? formatMeetingTime(selectedContext.createdAtEpochSeconds) : "")
    || presentation.title;
  meetingDetailMeta.textContent = selectedContext
    ? formatMeetingTime(selectedContext.createdAtEpochSeconds)
    : "Retained meeting";
  meetingDetailLede.textContent = presentation.lede;
  meetingDetailLede.hidden = presentation.kind === "note";
  meetingNoNoteTitle.textContent = presentation.fallbackTitle;
  meetingNoNoteCopy.textContent = presentation.fallbackCopy;
  const transcriptAvailable = Boolean(response?.transcriptHandle);
  meetingOpenTranscript.hidden = !transcriptAvailable;
  meetingOpenTranscript.disabled = false;
  meetingOpenTranscript.textContent = shellPrototype
    ? "Preview retained transcript"
    : "Open retained transcript";
  meetingTranscriptSummary.dataset.state = transcriptAvailable ? "available" : "unavailable";
  meetingTranscriptSummary.querySelector("h3").textContent = transcriptAvailable
    ? "Open the retained words."
    : "No retained transcript is available.";
  meetingTranscriptSummary.querySelector("p").textContent = transcriptAvailable
    ? "The transcript stays separate from any generated note. Withheld speech remains marked as unavailable."
    : "This meeting has no transcript that can be opened from the current retained record.";
  meetingDetailState.dataset.meetingId = response.meetingId || "";
  activeMeetingId = response.meetingId || activeMeetingId;
  renderMeetingContextList();
  renderAudioRetention(response.audioRetention, response.audioDeletionHandle);
  // Offered for any meeting the reader could open, including one whose audio
  // was already released: the transcript, the note and the record are still there.
  closeMeetingDeleteReview();
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
    meetingActionEmpty.hidden = false;
    meetingEvidenceEmpty.hidden = false;
    return;
  }
  for (const [index, claim] of (response.claims || []).entries()) {
    appendMeetingClaim(meetingClaimList, claim, response, index, "note");
    appendMeetingClaim(meetingEvidenceList, claim, response, index, "evidence", "evidence");
    if (claim.claimType === "action") {
      appendMeetingClaim(meetingActionList, claim, response, index, "actions", "action");
    }
  }
  if (!meetingClaimList.children.length) {
    message(meetingDetailState, "This automatic note has no claims with text locators. The retained transcript remains the source of record.", "note");
  }
  meetingActionEmpty.hidden = Boolean(meetingActionList.children.length);
  meetingEvidenceEmpty.hidden = Boolean(meetingEvidenceList.children.length);
}

async function openMeetingDetail(handle, returnScreen = "meetings-screen", control = null) {
  if (!invoke || !handle) return;
  if (handleTransitionGate.active()) return false;
  claimExplicitRoute();
  productRootScreen = rootForDestination(returnScreen, productRootScreen);
  activeMeetingId = control?.dataset.meetingId || activeMeetingId;
  renderMeetingContextList();
  invalidateLibraryHandles();
  meetingRetention.hidden = true;
  selectRetainedMeetingTab("note");
  meetingDetailTitle.textContent = "Opening meeting";
  meetingDetailMeta.textContent = "Retained meeting";
  meetingDetailLede.textContent = "Reading this meeting’s retained note, transcript status, and recording details.";
  meetingDetailLede.hidden = false;
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

async function openMeetingByIdFresh(meetingId, control = null) {
  if (!meetingId) return false;
  if (shellPrototype) {
    openPrototypeMeetingDetail(meetingId, { focus: true });
    return true;
  }
  if (!invoke || handleTransitionGate.active()) return false;
  claimExplicitRoute();
  productRootScreen = "meetings-screen";
  activeMeetingId = meetingId;
  meetingContextBusyId = meetingId;
  renderMeetingContextList();
  invalidateLibraryHandles();
  meetingRetention.hidden = true;
  selectRetainedMeetingTab("note");
  meetingDetailTitle.textContent = "Opening meeting";
  meetingDetailLede.textContent = "Refreshing the local meeting list before opening this retained record.";
  message(meetingDetailState, "Refreshing this meeting from its durable ID…");
  showScreen("meeting-detail-screen", { resetScroll: true });
  const transition = beginHandleTransition("switch-meeting-detail", control);
  if (!transition) {
    meetingContextBusyId = "";
    renderMeetingContextList();
    return false;
  }
  try {
    const snapshot = await initializeLibraryReader();
    if (!currentTransitionOwnsRoute(transition, "meeting-detail-screen")) return false;
    const row = rowForMeetingId(snapshot, meetingId);
    if (!row?.handle) {
      message(meetingDetailState, "That meeting is no longer available in the refreshed Meetings view.", "stale");
      return false;
    }
    const response = await invoke("preview_library_open_note", { handle: row.handle });
    if (!currentTransitionOwnsRoute(transition, "meeting-detail-screen")) return false;
    document.querySelector("#meeting-detail-transcript-handle").value = response.transcriptHandle || "";
    renderMeetingDetail(response);
    return true;
  } catch {
    if (!currentTransitionOwnsRoute(transition, "meeting-detail-screen")) return false;
    message(meetingDetailState, "That meeting could not be reopened from the refreshed Meetings view.", "stale");
    return false;
  } finally {
    meetingContextBusyId = "";
    renderMeetingContextList();
    finishHandleTransition(transition);
  }
}

function focusRestoredMeetingOrigin(context, response) {
  selectRetainedMeetingTab(context.detailTab || "note");
  if (context.claim) {
    const activePanel = document.querySelector(`[data-retained-meeting-panel="${retainedMeetingTab}"]`);
    const origin = [...(activePanel?.querySelectorAll(".claim-evidence") || [])].find((control) => {
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
    selectRetainedMeetingTab(context.detailTab || "note");
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
    if (context?.destination === "find") {
      return await returnToFindAfterTranscript(context, transition);
    }
    if (!currentTransitionOwnsRoute(transition, "library-transcript-screen")) return false;
    await returnToProductRoot();
    return true;
  } finally {
    finishHandleTransition(transition);
  }
}

async function returnToFindAfterTranscript(context, transition) {
  if (!currentTransitionOwnsRoute(transition, "library-transcript-screen")) return false;
  productRootScreen = "find-screen";
  selectProductScreen("find-screen", { focus: false });
  if (context.findFocus === "exact") {
    await refreshFindView();
  } else {
    // Handles are intentionally invalidated when the transcript opens. Do not
    // rerun the model just because Back was pressed; keep the question and put
    // focus there so the operator decides whether to ask again.
    setSearchNotice(corpusNotice, "Your wording is still here. Search again to see current matching passages.");
  }
  if (currentScreen !== "find-screen") return false;
  const focusTarget = context.findFocus === "meaning" ? corpusSearchQuestion : librarySearchQuery;
  focusTarget.focus({ preventScroll: true });
  return true;
}

async function openMeetingEvidence(handle, meetingId, claim, control, sourceTab = "note") {
  if (!invoke || !handle) return;
  claimExplicitRoute();
  const returnContext = transcriptReturnRoute("meeting-detail", meetingId, {
    claim,
    detailScrollTop: mainRegion.scrollTop,
    detailTab: sourceTab,
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
    setSearchNotice(libraryNotice, "Searching your retained meetings…");
  } else {
    clearSearchNotice(libraryNotice);
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
      clearSearchNotice(libraryNotice);
      findStart.hidden = false;
    }
    return { revision, ok: true };
  } catch {
    if (ownsRoute()) {
      invalidateLibraryHandles();
      setSearchNotice(libraryNotice, "Search is unavailable right now. Try Find again.", "error");
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
  if (shellPrototype) {
    setSearchNotice(libraryNotice, "The browser shell has no retained meetings to search. Nothing was queried or invented.");
    return;
  }
  await refreshFindView();
}

async function openLibrarySearchResult(handle, control = null) {
  if (!invoke || !handle) return;
  claimExplicitRoute();
  const transition = beginHandleTransition("open-search-result", control);
  if (!transition) return false;
  productRootScreen = "find-screen";
  invalidateLibraryHandles();
  setSearchNotice(libraryNotice, "Opening the selected retained result…");
  try {
    const result = await invoke("preview_library_open_search_result", { handle });
    if (!currentTransitionOwnsRoute(transition, "find-screen")) return false;
    if (!result.transcriptHandle || result.state === "withheld") {
      setSearchNotice(libraryNotice, result.message || "That result cannot be opened as visible transcript text. Run the search again to continue.", "warning");
      return false;
    }
    if (result.state !== "transcript" && result.state !== "meeting") {
      setSearchNotice(libraryNotice, result.message || "That search result is no longer current. Run the search again to continue.", "warning");
      return false;
    }
    const exactMatch = Number.isInteger(result.sourceTurnIndex)
      ? {
          sourceTurnIndex: result.sourceTurnIndex,
          start: Number.isInteger(result.start) ? result.start : null,
          end: Number.isInteger(result.end) ? result.end : null,
        }
      : null;
    return await openLibraryTranscript(
      result.transcriptHandle,
      exactMatch,
      transcriptReturnRoute("find", "", { findFocus: "exact" }),
      transition,
    );
  } catch {
    if (!currentTransitionOwnsRoute(transition, "find-screen")) return false;
    setSearchNotice(libraryNotice, "That search result could not be opened. Run the search again to continue.", "error");
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
  updatePreflightRetentionSummary();
  updateStartButton();
}

async function dismissAttemptAndReturnFind(control) {
  if (shellPrototype) {
    leavePrototypeCapture("find-screen");
    return;
  }
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
retention.addEventListener("change", () => {
  updatePreflightRetentionSummary();
  updateStartButton();
});

startForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearError(startError);
  if (!startIsAllowed()) return;
  if (shellPrototype) {
    prototypeCaptureStartedAt = Math.floor(Date.now() / 1000);
    prototypeCaptureDegraded = false;
    liveNoteMeetingId = "prototype-capture";
    liveNoteSavedText = "";
    liveNoteText.value = "";
    liveNoteDirty = false;
    liveNoteFailure = "";
    renderLiveNote();
    renderPrototypeCapture("arming");
    return;
  }
  if (!invoke) return;
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
  if (shellPrototype) {
    liveNoteSavedText = liveNoteText.value;
    liveNoteDirty = false;
    liveNoteSavedRecently = Boolean(liveNoteSavedText);
    renderLiveNote();
    renderPrototypeCapture("transcribing");
    return;
  }
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

document.querySelector("#prototype-arming-ready").addEventListener("click", () => {
  renderPrototypeCapture("recording");
});
document.querySelector("#prototype-arming-cancel").addEventListener("click", () => {
  leavePrototypeCapture();
});
document.querySelector("#prototype-recording-degrade").addEventListener("click", (event) => {
  prototypeCaptureDegraded = !prototypeCaptureDegraded;
  renderPrototypeCapture("recording");
  event.currentTarget.textContent = prototypeCaptureDegraded
    ? "Restore both synthetic channels"
    : "Simulate system-audio issue";
});
document.querySelector("#prototype-processing-complete").addEventListener("click", finishPrototypeTranscript);
document.querySelector("#prototype-open-result").addEventListener("click", () => {
  openPrototypeMeetingDetail("prototype-meeting", { focus: true });
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
allMeetingsLink.addEventListener("click", () => openMeetings({ resetFind: true, browseAll: true }));
unfiledMeetingsLink.addEventListener("click", () => {
  filterFolder.value = "unfiled";
  libraryFilter = { folder: "unfiled" };
  void openMeetings({ resetFind: true, browseAll: true });
});
document.querySelector("#prototype-browse-all").addEventListener("click", () => {
  void openMeetings({ resetFind: true, browseAll: true });
});
for (const folder of document.querySelectorAll("[data-prototype-folder]")) {
  folder.addEventListener("click", () => openPrototypeMeetingDetail());
}
for (const control of [actionsWorkspacePreview, meetingsWorkspacePreview]) {
  control.addEventListener("click", () => {
    productRootScreen = "meetings-screen";
    selectProductScreen("prototype-meeting-screen", { resetScroll: true });
  });
}
const prototypeMeetingRows = [
  { meetingId: "prototype-meeting", label: "Acme pilot planning", labelSource: "operator", createdAtEpochSeconds: 1786153800, transcriptAvailable: true },
  { meetingId: "prototype-weekly", label: "Weekly product check-in", labelSource: "derived", createdAtEpochSeconds: 1786066200, transcriptAvailable: true },
  { meetingId: "prototype-intake", label: "Customer intake", labelSource: "operator", createdAtEpochSeconds: 1785897000, transcriptAvailable: false },
];

function prototypeMeetingResponse(meetingId) {
  const fixtures = {
    "prototype-meeting": {
      operatorNote: "Use Acme for the pilot if legal clears the sample data.",
      claims: [
        { ordinal: 0, claimType: "decision", claim: "The pilot will run for two weeks with one customer.", handle: "prototype-evidence-0", evidenceText: "Let’s keep the pilot to one customer for two weeks, then review the handoff data.", evidenceSpeaker: "You", evidenceTime: "12:08" },
        { ordinal: 1, claimType: "action", claim: "Run the pilot review on Friday.", handle: "prototype-evidence-1", evidenceText: "I’ll run the pilot review Friday and bring back the completion time.", evidenceSpeaker: "Other side", evidenceTime: "12:21" },
        { ordinal: 2, claimType: "question", claim: "Which customer gives the pilot a fair test?", handle: "prototype-evidence-2", evidenceText: "We still need to decide which customer gives us a fair test.", evidenceSpeaker: "You", evidenceTime: "12:42" },
      ],
    },
    "prototype-weekly": {
      operatorNote: "Confirm the onboarding copy before the next build.",
      claims: [
        { ordinal: 0, claimType: "decision", claim: "The team will keep the first-run flow to three steps.", handle: "prototype-weekly-evidence-0", evidenceText: "Let’s keep first run to three steps. Anything else can wait until after the first successful note.", evidenceSpeaker: "You", evidenceTime: "08:14" },
        { ordinal: 1, claimType: "action", claim: "Review the first-run copy before Tuesday.", handle: "prototype-weekly-evidence-1", evidenceText: "I’ll review the first-run copy before Tuesday and flag anything unclear.", evidenceSpeaker: "Other side", evidenceTime: "08:37" },
      ],
    },
    "prototype-intake": { operatorNote: "Waiting for consent before recording.", claims: [] },
  };
  const fixture = fixtures[meetingId] || fixtures["prototype-meeting"];
  const transcriptAvailable = meetingId !== "prototype-intake";
  return {
    state: transcriptAvailable ? "note" : "transcript-only",
    meetingId,
    transcriptHandle: transcriptAvailable ? `prototype-transcript-${meetingId}` : "",
    audioDeletionHandle: transcriptAvailable ? `prototype-audio-delete-${meetingId}` : "",
    meetingDeletionHandle: `prototype-meeting-delete-${meetingId}`,
    operatorNote: { text: fixture.operatorNote, unreadable: false },
    claims: fixture.claims,
    audioRetention: transcriptAvailable ? {
      state: "retained",
      policy: "scheduled",
      deadlineEpochSeconds: Math.floor(Date.now() / 1000) + 604800,
      retainedBytes: 25165824,
      message: "Synthetic retention example.",
    } : { state: "not-recorded", message: "Synthetic example: no recording was retained." },
    message: "Synthetic meeting opened. Nothing was read from or written to your Mac.",
  };
}

function openPrototypeMeetingDetail(meetingId = "prototype-meeting", { focus = false } = {}) {
  productRootScreen = "meetings-screen";
  meetingContextRows = prototypeMeetingRows.map((row) => ({ ...row }));
  const response = prototypeMeetingResponse(meetingId);
  document.querySelector("#meeting-detail-transcript-handle").value = response.transcriptHandle;
  renderMeetingDetail(response);
  selectRetainedMeetingTab("note");
  selectProductScreen("meeting-detail-screen", { resetScroll: true });
  setMeetingFocus(focus);
  if (focus) {
    meetingDetailTitle.tabIndex = -1;
    meetingDetailTitle.focus({ preventScroll: true });
  }
}

meetingsRetainedPreview.addEventListener("click", () => {
  openPrototypeMeetingDetail();
});
prototypeMeetingBack.addEventListener("click", () => void openMeetings({ resetFind: true, browseAll: true }));
for (const tab of settingsTabs) {
  tab.addEventListener("click", () => selectSettingsPanel(tab.dataset.settingsTab));
  tab.addEventListener("keydown", (event) => {
    if (["ArrowDown", "ArrowRight"].includes(event.key)) {
      event.preventDefault();
      moveSettingsTab(tab, 1);
    } else if (["ArrowUp", "ArrowLeft"].includes(event.key)) {
      event.preventDefault();
      moveSettingsTab(tab, -1);
    } else if (event.key === "Home") {
      event.preventDefault();
      const first = settingsTabs.find((candidate) => shellPrototype || !candidate.classList.contains("prototype-only"));
      selectSettingsPanel(first.dataset.settingsTab, { focusTab: true });
    } else if (event.key === "End") {
      event.preventDefault();
      const available = settingsTabs.filter((candidate) => shellPrototype || !candidate.classList.contains("prototype-only"));
      selectSettingsPanel(available.at(-1).dataset.settingsTab, { focusTab: true });
    }
  });
}
settingsRetentionPreview.addEventListener("change", (event) => {
  if (!shellPrototype || event.target.name !== "settings-retention") return;
  settingsRetentionPreviewStatus.textContent = `Preview choice: ${event.target.value}. This is not saved and does not change any existing recording.`;
});
settingsReviewAudio.addEventListener("click", async () => {
  await openMeetings({ resetFind: true });
  document.querySelector("#retention-overview").scrollIntoView({ block: "start" });
});
settingsPreviewFirstRun.addEventListener("click", openPrototypeFirstRun);
settingsPreviewStates.addEventListener("click", openStateReview);
settingsOpenHelp.addEventListener("click", openHelp);
skipLink.addEventListener("click", (event) => {
  event.preventDefault();
  mainRegion.scrollTop = 0;
  mainRegion.focus({ preventScroll: true });
});
for (const tab of helpTabs) {
  tab.addEventListener("click", () => renderHelpTopic(tab.dataset.helpTopic));
  tab.addEventListener("keydown", (event) => {
    if (event.key !== "ArrowDown" && event.key !== "ArrowRight" && event.key !== "ArrowUp" && event.key !== "ArrowLeft") return;
    event.preventDefault();
    moveHelpTab(tab, event.key === "ArrowDown" || event.key === "ArrowRight" ? 1 : -1);
  });
}
helpTopicPrimary.addEventListener("click", () => runHelpAction(helpTopicPrimary.dataset.action));
helpExit.addEventListener("click", closeHelp);
helpMeetings.addEventListener("click", () => {
  restoreShellSnapshotStatus();
  void openMeetings({ resetFind: true, browseAll: true });
});
for (const tab of stateReviewTabs) {
  tab.addEventListener("click", () => renderStateReview(tab.dataset.statePreview));
  tab.addEventListener("keydown", (event) => {
    if (["ArrowDown", "ArrowRight"].includes(event.key)) {
      event.preventDefault();
      moveStateReviewTab(tab, 1);
    } else if (["ArrowUp", "ArrowLeft"].includes(event.key)) {
      event.preventDefault();
      moveStateReviewTab(tab, -1);
    } else if (event.key === "Home") {
      event.preventDefault();
      renderStateReview(stateReviewTabs[0].dataset.statePreview, { focusTab: true });
    } else if (event.key === "End") {
      event.preventDefault();
      renderStateReview(stateReviewTabs.at(-1).dataset.statePreview, { focusTab: true });
    }
  });
}
stateReviewPrimary.addEventListener("click", runStateReviewPrimary);
stateReviewExit.addEventListener("click", () => void openMeetings({ resetFind: true, browseAll: true }));
stateReviewMeetings.addEventListener("click", () => void openMeetings({ resetFind: true, browseAll: true }));
for (const control of document.querySelectorAll(".action-filter")) {
  control.addEventListener("click", () => {
    for (const peer of document.querySelectorAll(".action-filter")) {
      peer.setAttribute("aria-pressed", String(peer === control));
    }
  });
}
function selectMeetingPreviewTab(tabName) {
  for (const tab of document.querySelectorAll("[data-meeting-tab]")) {
    const selected = tab.dataset.meetingTab === tabName;
    tab.setAttribute("aria-selected", String(selected));
    tab.tabIndex = selected ? 0 : -1;
  }
  for (const panel of document.querySelectorAll("[data-meeting-panel]")) {
    const active = panel.dataset.meetingPanel === tabName;
    panel.hidden = !active;
    panel.classList.toggle("active", active);
  }
}
for (const tab of document.querySelectorAll("[data-meeting-tab]")) {
  tab.addEventListener("click", () => selectMeetingPreviewTab(tab.dataset.meetingTab));
  tab.addEventListener("keydown", (event) => {
    const tabs = [...document.querySelectorAll("[data-meeting-tab]")];
    const currentIndex = tabs.indexOf(tab);
    let next = null;
    if (["ArrowRight", "ArrowDown"].includes(event.key)) next = tabs[(currentIndex + 1) % tabs.length];
    else if (["ArrowLeft", "ArrowUp"].includes(event.key)) next = tabs[(currentIndex - 1 + tabs.length) % tabs.length];
    else if (event.key === "Home") next = tabs[0];
    else if (event.key === "End") next = tabs.at(-1);
    if (!next) return;
    event.preventDefault();
    selectMeetingPreviewTab(next.dataset.meetingTab);
    next.focus();
  });
}
for (const jump of document.querySelectorAll("[data-meeting-tab-jump]")) {
  jump.addEventListener("click", () => selectMeetingPreviewTab(jump.dataset.meetingTabJump));
}
for (const tab of document.querySelectorAll("[data-retained-meeting-tab]")) {
  tab.addEventListener("click", () => selectRetainedMeetingTab(
    tab.dataset.retainedMeetingTab,
    { reveal: true },
  ));
  tab.addEventListener("keydown", (event) => {
    const tabs = [...document.querySelectorAll("[data-retained-meeting-tab]")];
    const currentIndex = tabs.indexOf(tab);
    let next = null;
    if (["ArrowRight", "ArrowDown"].includes(event.key)) next = tabs[(currentIndex + 1) % tabs.length];
    else if (["ArrowLeft", "ArrowUp"].includes(event.key)) next = tabs[(currentIndex - 1 + tabs.length) % tabs.length];
    else if (event.key === "Home") next = tabs[0];
    else if (event.key === "End") next = tabs.at(-1);
    if (!next) return;
    event.preventDefault();
    selectRetainedMeetingTab(next.dataset.retainedMeetingTab, { focus: true });
  });
}
profileLink.addEventListener("click", openProfile);
meetingFocusToggle.addEventListener("click", () => {
  setMeetingFocus(document.documentElement.dataset.meetingFocus !== "true");
});
meetingDockRecord.addEventListener("click", openStartMeeting);
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
workflowReturn.addEventListener("click", () => void returnToWorkflow());
startMeetingAction.addEventListener("click", openStartMeeting);
commandMenuTrigger.addEventListener("click", () => {
  if (commandMenuBackdrop.hidden) openCommandMenu();
  else closeCommandMenu();
});
commandMenuClose.addEventListener("click", closeCommandMenu);
commandMenuInput.addEventListener("input", renderCommandMenu);
commandMenuBackdrop.addEventListener("click", (event) => {
  if (event.target === commandMenuBackdrop) closeCommandMenu();
});
commandMenuBackdrop.addEventListener("keydown", (event) => {
  if (event.key === "ArrowDown") {
    event.preventDefault();
    setCommandMenuActiveIndex(commandMenuActiveIndex + 1, { reveal: true });
    commandMenuInput.focus();
  } else if (event.key === "ArrowUp") {
    event.preventDefault();
    setCommandMenuActiveIndex(commandMenuActiveIndex - 1, { reveal: true });
    commandMenuInput.focus();
  } else if (event.key === "Enter" && commandMenuEntries.length) {
    event.preventDefault();
    runShellCommand(commandMenuEntries[commandMenuActiveIndex].command);
  } else if (event.key === "Tab") {
    const focusable = [commandMenuInput, ...commandMenuEntries.map(({ button }) => button), commandMenuClose];
    const currentIndex = focusable.indexOf(document.activeElement);
    const direction = event.shiftKey ? -1 : 1;
    const nextIndex = (currentIndex + direction + focusable.length) % focusable.length;
    event.preventDefault();
    focusable[nextIndex].focus();
  }
});
quickControlTrigger.addEventListener("click", () => {
  if (quickControlPopover.hidden) openQuickControl();
  else closeQuickControl({ restoreFocus: true });
});
quickControlClose.addEventListener("click", () => closeQuickControl({ restoreFocus: true }));
quickControlPrimary.addEventListener("click", runQuickControlPrimary);
quickControlSecondary.addEventListener("click", runQuickControlSecondary);
document.addEventListener("keydown", (event) => {
  const commandKey = event.metaKey && !event.altKey && !event.ctrlKey;
  if (shellPrototype && commandKey && event.key.toLocaleLowerCase() === "k") {
    event.preventDefault();
    if (commandMenuBackdrop.hidden) openCommandMenu();
    else closeCommandMenu();
    return;
  }
  if (commandKey && !event.shiftKey) {
    const routeShortcut = {
      "1": "meetings",
      "2": "search",
      ...(shellPrototype ? { "3": "actions" } : {}),
      ",": "settings",
    }[event.key];
    if (routeShortcut) {
      event.preventDefault();
      if (routeShortcut === "meetings") void openMeetings({ resetFind: true });
      else if (routeShortcut === "search") void openFind({ resetQuery: true });
      else if (routeShortcut === "settings") void openProfile();
      else runShellCommandById(routeShortcut);
      return;
    }
  }
  if (!shellPrototype) return;
  if (event.key === "Escape" && !commandMenuBackdrop.hidden) {
    event.preventDefault();
    closeCommandMenu();
  } else if (event.key === "Escape" && !quickControlPopover.hidden) {
    closeQuickControl({ restoreFocus: true });
  }
});
document.addEventListener("click", (event) => {
  if (quickControlPopover.hidden) return;
  if (quickControlPopover.contains(event.target) || quickControlTrigger.contains(event.target)) return;
  closeQuickControl();
});
window.addEventListener("resize", () => applyDesktopLayout(desktopLayoutPreference));
window.addEventListener("yawn:desktop-layout-changed", (event) => {
  applyDesktopLayout(event.detail);
});
document.querySelector("#start-back").addEventListener("click", returnToProductRoot);
document.querySelector("#start-transition-back").addEventListener(
  "click",
  (event) => returnToFindAfterStartError(event.currentTarget),
);
librarySearch.addEventListener("submit", searchLibrary);
corpusSearch.addEventListener("submit", searchCorpus);
corpusPrepare.addEventListener("click", prepareCorpusPassages);
document.querySelector("#profile-back").addEventListener("click", returnToProductRoot);
document.querySelector("#library-transcript-back").addEventListener("click", returnFromLibraryTranscript);
document.querySelector("#meeting-detail-back").addEventListener("click", () => {
  if (shellPrototype) void returnToProductRoot();
  else void openMeetings({ browseAll: true });
});
document.querySelector("#meeting-record-back").addEventListener("click", () => {
  void openMeetings({ browseAll: true });
});
document.querySelector("#meeting-record-search").addEventListener("click", () => {
  void openFind({ resetQuery: true });
});
recordingDeleteReview.addEventListener("click", () => {
  if (!meetingAudioDeletionHandle) return;
  recordingDeleteConfirmation.hidden = false;
  (shellPrototype ? recordingDeleteCancel : recordingDeleteConfirm).focus();
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
  (shellPrototype ? meetingDeleteCancel : meetingDeleteConfirm).focus();
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
      returnToProductRoot();
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
  if (shellPrototype) {
    productRootScreen = "meetings-screen";
    selectMeetingPreviewTab("transcript");
    selectProductScreen("prototype-meeting-screen", { resetScroll: true });
    return;
  }
  const handle = document.querySelector("#meeting-detail-transcript-handle").value;
  const meetingId = meetingDetailState.dataset.meetingId || "";
  if (handle) {
    openLibraryTranscript(handle, null, transcriptReturnRoute("meeting-detail", meetingId, {
      detailScrollTop: mainRegion.scrollTop,
      detailTab: "transcript",
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
const firstRunProgressItems = [...firstRunScreen.querySelectorAll("[data-first-run-progress]")];
const firstRunProgressOrder = [
  "welcome",
  "request-microphone",
  "request-audio-capture",
  "enrol-voice",
  "ready",
];

function renderFirstRunProgress(step) {
  let currentStep = step;
  let attention = false;
  if (step === "denied-recovery") {
    currentStep = firstRunDeniedPane.textContent === "Microphone"
      ? "request-microphone"
      : "request-audio-capture";
    attention = true;
  } else if (step === "unavailable") {
    currentStep = "welcome";
    attention = true;
  }
  const currentIndex = firstRunProgressOrder.indexOf(currentStep);
  firstRunProgressItems.forEach((item, index) => {
    item.dataset.state = index < currentIndex
      ? "complete"
      : index === currentIndex
        ? attention ? "attention" : "current"
        : "upcoming";
  });
}

function showFirstRunStep(step) {
  firstRunScreen.dataset.step = step;
  for (const [name, panel] of firstRunPanels) panel.hidden = name !== step;
  renderFirstRunProgress(step);
}

function openPrototypeFirstRun() {
  if (!shellPrototype) return;
  claimExplicitRoute();
  for (const status of firstRunScreen.querySelectorAll(".first-run-state")) {
    status.textContent = "";
    status.removeAttribute("data-state");
  }
  firstRunDeniedPane.textContent = "Microphone";
  showFirstRunStep("welcome");
  setHeaderState("Setup preview · nothing is recording");
  showScreen("first-run-screen", { resetScroll: true });
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
  if (shellPrototype) {
    showFirstRunStep("request-microphone");
    return;
  }
  renderFirstRun(await readFirstRunPermissions());
});
document.querySelector("#first-run-ask-microphone").addEventListener("click", (event) => {
  if (shellPrototype) {
    message(document.querySelector("#first-run-microphone-state"), "Synthetic state: microphone allowed.", "ok");
    showFirstRunStep("request-audio-capture");
    return;
  }
  runFirstRunRequest(
    "first_run_request_microphone",
    event.currentTarget,
    document.querySelector("#first-run-microphone-state"),
    "microphone",
  );
});
document.querySelector("#first-run-ask-system-audio").addEventListener("click", (event) => {
  if (shellPrototype) {
    message(document.querySelector("#first-run-system-audio-state"), "Synthetic state: system audio allowed.", "ok");
    showFirstRunStep("enrol-voice");
    return;
  }
  runFirstRunRequest(
    "first_run_request_system_audio",
    event.currentTarget,
    document.querySelector("#first-run-system-audio-state"),
    "system-audio",
  );
});
document.querySelector("#first-run-recheck").addEventListener("click", async () => {
  if (shellPrototype) {
    showFirstRunStep(
      firstRunDeniedPane.textContent === "Microphone"
        ? "request-audio-capture"
        : "enrol-voice",
    );
    return;
  }
  renderFirstRun(await readFirstRunPermissions());
});
document.querySelector("#first-run-retry-probe").addEventListener("click", async () => {
  if (shellPrototype) {
    showFirstRunStep("welcome");
    return;
  }
  renderFirstRun(await readFirstRunPermissions());
});
document.querySelector("#prototype-first-run-unavailable").addEventListener("click", () => {
  showFirstRunStep("unavailable");
});
document.querySelector("#prototype-first-run-deny-microphone").addEventListener("click", () => {
  firstRunDeniedPane.textContent = "Microphone";
  showFirstRunStep("denied-recovery");
});
document.querySelector("#prototype-first-run-deny-system-audio").addEventListener("click", () => {
  firstRunDeniedPane.textContent = "System Audio Recording";
  showFirstRunStep("denied-recovery");
});
document.querySelector("#first-run-exit").addEventListener("click", () => void openMeetings({ resetFind: true, browseAll: true }));
document.querySelector("#first-run-enrol").addEventListener("click", () => {
  activeSettingsTab = "voice";
  if (shellPrototype) {
    // The browser prototype retains its reference-only profile surface.
    selectProductScreen("profile-screen", { resetScroll: true });
    selectSettingsPanel("voice");
    return;
  }
  void openProfile({ pane: "voice" });
});
document.querySelector("#first-run-skip-enrol").addEventListener("click", () => {
  showFirstRunStep("ready");
});
document.querySelector("#first-run-done").addEventListener("click", () => {
  if (shellPrototype) void openMeetings({ resetFind: true, browseAll: true });
  else selectProductScreen("idle-screen", { resetScroll: true });
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
    if (shellPrototype) void openMeetings({ resetFind: true, browseAll: true });
    else selectProductScreen("idle-screen", { resetScroll: true });
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

if (shellPrototype) {
  document.documentElement.dataset.prototype = "true";
  releaseBadge.textContent = "Shell preview";
  lastSnapshot = { startup: "ready", capture: "idle", retention_operational: true };
  workflowOwnsRoute = false;
  renderCaptureAction(lastSnapshot);
  setHeaderState("Click-through prototype · nothing is recording");
  openPrototypeMeetingDetail(activeMeetingId || "prototype-meeting", { focus: true });
  if (nativeCalibration === "document") setMeetingFocus(true);
} else {
  renderStartup("shell-rendered");
  void initializeDesktopLayout().finally(refreshCurrent);
}

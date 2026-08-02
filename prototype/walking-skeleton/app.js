"use strict";

const meetings = [
  {
    id: "m-01",
    title: "Inventory migration follow-up",
    date: "Apr 10, 2026 at 10:00 AM",
    folder: "Operations",
    transcriptStatus: "complete",
    audio: { state: "released", detail: "Audio released Apr 17. Transcript evidence remains available." },
    turns: [
      { id: "m01-t01", at: "00:00:12", speaker: "Them", text: "The export freeze begins next Monday." },
      { id: "m01-t02", at: "00:00:21", speaker: "Me", text: "Let’s defer the inventory migration until the export freeze ends." },
      { id: "m01-t03", at: "00:00:34", speaker: "Me", text: "I will send the freeze calendar after this call." },
      { id: "m01-t04", at: "00:00:46", speaker: "Them", text: "Proposal: use a weekly export until the freeze ends." },
      { id: "m01-t05", at: "00:00:57", speaker: "Me", text: "That keeps the receiving team unblocked." }
    ],
    claims: [
      {
        id: "m01-c01",
        kind: "decision",
        text: "Defer the inventory migration until the export freeze ends.",
        evidenceState: "located",
        locator: { turnId: "m01-t02", start: 6, end: 64, quote: "defer the inventory migration until the export freeze ends" }
      },
      {
        id: "m01-c02",
        kind: "commitment",
        text: "Send the freeze calendar after the call.",
        evidenceState: "located",
        locator: { turnId: "m01-t03", start: 0, end: 47, quote: "I will send the freeze calendar after this call" }
      },
      {
        id: "m01-c03",
        kind: "proposal",
        text: "Use a weekly export until the freeze ends.",
        evidenceState: "located",
        locator: { turnId: "m01-t04", start: 0, end: 51, quote: "Proposal: use a weekly export until the freeze ends" }
      },
      {
        id: "m01-c04",
        kind: "decision",
        text: "Replace the migration permanently with weekly exports.",
        evidenceState: "composed",
        evidenceDetail: "Quoted words were not found in the canonical transcript.",
        locator: null
      },
      {
        id: "m01-c05",
        kind: "question",
        text: "Does the freeze end before July?",
        evidenceState: "unquoted",
        evidenceDetail: "No words were supplied for this claim.",
        locator: null
      },
      {
        id: "m01-c06",
        kind: "question",
        text: "Budget?",
        evidenceState: "untestable",
        evidenceDetail: "The supplied words are too short to establish a reliable exact match.",
        locator: null
      }
    ]
  },
  {
    id: "m-02",
    title: "Estimate handoff",
    date: "Apr 24, 2026 at 11:30 AM",
    folder: "Operations",
    transcriptStatus: "partial",
    audio: { state: "held", detail: "18.4 MB · scheduled for release May 24" },
    coverage: "One 18-second turn was withheld. It may contain speech that was said but is not included in the note.",
    turns: [
      { id: "m02-t01", at: "00:00:16", speaker: "Them", text: "The estimate needs a range, not one number." },
      { id: "m02-t02", at: "00:00:31", speaker: "Me", text: "We decided to send an estimate range after finance checks the assumptions." },
      {
        id: "m02-gap01",
        type: "gap",
        at: "00:01:08–00:01:26",
        text: "18 seconds withheld by the voice gate"
      },
      {
        id: "m02-t04",
        at: "00:01:08",
        speaker: "Me",
        text: "I can send the revised estimate on Thursday.",
        withheld: true
      },
      { id: "m02-t05", at: "00:01:32", speaker: "Them", text: "Can the support team review it Friday?" }
    ],
    claims: [
      {
        id: "m02-c01",
        kind: "decision",
        text: "Send an estimate range after finance checks assumptions.",
        evidenceState: "located",
        locator: { turnId: "m02-t02", start: 3, end: 73, quote: "decided to send an estimate range after finance checks the assumptions" }
      },
      {
        id: "m02-c02",
        kind: "question",
        text: "Can the support team review the estimate Friday?",
        evidenceState: "located",
        locator: { turnId: "m02-t05", start: 0, end: 37, quote: "Can the support team review it Friday" }
      }
    ],
    regeneratedClaim: {
      id: "m02-c03",
      kind: "commitment",
      text: "Send the revised estimate on Thursday.",
      evidenceState: "located",
      locator: { turnId: "m02-t04", start: 0, end: 43, quote: "I can send the revised estimate on Thursday" }
    }
  },
  {
    id: "m-03",
    title: "Partner check-in",
    date: "May 2, 2026 at 9:00 AM",
    folder: "Partnerships",
    transcriptStatus: "missing",
    audio: { state: "held", detail: "9.2 MB · recording is safe" },
    failure: {
      text: "The recording is safe, but its transcript is not available yet.",
      diagnostic: "~/Library/Logs/local-meeting-notes/m-03.txt"
    },
    turns: [],
    claims: []
  },
  {
    id: "m-04",
    title: "Retention review",
    date: "May 9, 2026 at 5:00 AM",
    folder: "Operations",
    transcriptStatus: "complete",
    audio: { state: "expiring", detail: "6.3 MB · scheduled for release May 10, 2026" },
    turns: [
      { id: "m04-t01", at: "00:00:09", speaker: "Me", text: "Keep meeting audio for fourteen days, then release it." }
    ],
    claims: [
      {
        id: "m04-c01",
        kind: "decision",
        text: "Use a fourteen-day audio retention period.",
        evidenceState: "located",
        locator: { turnId: "m04-t01", start: 0, end: 53, quote: "Keep meeting audio for fourteen days, then release it" }
      }
    ]
  },
  {
    id: "m-05",
    title: "Discovery call — reporting workflow",
    date: "May 8, 2026 at 2:00 PM",
    folder: "Sales",
    transcriptStatus: "complete",
    audio: { state: "held", detail: "12.7 MB · scheduled for release May 22, 2026" },
    noteLayout: "survey-core",
    summary: "Support trends are copied into a shared report each Friday. The first pilot will import the weekly CSV and preserve the source rows. A redacted sample is due Tuesday, while account names in exported summaries could block legal review.",
    reviewPrompt: "Can you see what was decided, what happens next, and what could block the pilot before opening the transcript?",
    turns: [
      { id: "m05-t01", at: "00:00:18", speaker: "Them", text: "Our team spends Friday afternoons copying support trends into a shared report." },
      { id: "m05-t02", at: "00:00:42", speaker: "Me", text: "We agreed the first pilot will import the weekly CSV and preserve the original rows." },
      { id: "m05-t03", at: "00:01:05", speaker: "Them", text: "If account names appear in an exported summary, legal review will block the pilot." },
      { id: "m05-t04", at: "00:01:28", speaker: "Me", text: "I will send a sample redacted report by Tuesday." },
      { id: "m05-t05", at: "00:01:49", speaker: "Them", text: "Can the report separate urgent defects from general requests?" },
      { id: "m05-t06", at: "00:02:02", speaker: "Me", text: "That split may help, but we did not decide it today." }
    ],
    claims: [
      {
        id: "m05-c01",
        kind: "customer_need",
        text: "Spend less time copying support trends into the weekly report.",
        evidenceState: "located",
        supportType: "inferred",
        locator: { turnId: "m05-t01", start: 9, end: 77, quote: "spends Friday afternoons copying support trends into a shared report" }
      },
      {
        id: "m05-c02",
        kind: "decision",
        text: "Import the weekly CSV and preserve the original rows for the first pilot.",
        evidenceState: "located",
        supportType: "stated",
        locator: { turnId: "m05-t02", start: 3, end: 83, quote: "agreed the first pilot will import the weekly CSV and preserve the original rows" }
      },
      {
        id: "m05-c03",
        kind: "commitment",
        text: "Send a sample redacted report by Tuesday.",
        evidenceState: "located",
        supportType: "stated",
        owner: "Me",
        locator: { turnId: "m05-t04", start: 0, end: 47, quote: "I will send a sample redacted report by Tuesday" }
      },
      {
        id: "m05-c04",
        kind: "question",
        text: "Can the report separate urgent defects from general requests?",
        evidenceState: "located",
        supportType: "stated",
        locator: { turnId: "m05-t05", start: 0, end: 60, quote: "Can the report separate urgent defects from general requests" }
      },
      {
        id: "m05-c05",
        kind: "risk",
        text: "Account names in an exported summary could block legal review.",
        evidenceState: "located",
        supportType: "stated",
        locator: { turnId: "m05-t03", start: 3, end: 81, quote: "account names appear in an exported summary, legal review will block the pilot" }
      }
    ]
  }
];

const recoveredPartnerTurn = {
  id: "m03-t01",
  at: "00:00:18",
  speaker: "Them",
  text: "Please send the agenda before the next check-in."
};

const recoveredPartnerClaim = {
  id: "m03-c01",
  kind: "commitment",
  text: "Send the agenda before the next check-in.",
  evidenceState: "located",
  locator: { turnId: "m03-t01", start: 7, end: 47, quote: "send the agenda before the next check-in" }
};

const viewLabels = {
  meetings: "Meetings",
  commitments: "Promises",
  retrieval: "Find"
};

const workspace = document.querySelector("#workspace");
const footerDirection = document.querySelector("#footer-direction");
const captureLayer = document.querySelector("#capture-layer");
const toast = document.querySelector("#toast");
const recoveryFixtureKey = "local-meeting-notes:walking-skeleton-recovery";

let loadTimer;
let transitionTimer;
let captureTimer;
let toastTimer;
let state = freshState(readDirection(), readRecoveryFixture());

function readDirection() {
  const direction = new URLSearchParams(window.location.search).get("direction");
  return Object.hasOwn(viewLabels, direction) ? direction : "retrieval";
}

function readRecoveryFixture() {
  try {
    const raw = window.sessionStorage.getItem(recoveryFixtureKey);
    if (!raw) return null;
    const fixture = JSON.parse(raw);
    const keys = Object.keys(fixture ?? {}).sort().join(",");
    if (
      keys !== "meetingId,priorNoteVersion,scenario,schema,transcriptView"
      || fixture.schema !== "walking-skeleton-recovery/1"
      || fixture.scenario !== "note-regeneration-request-only"
      || fixture.meetingId !== "m-02"
      || fixture.transcriptView !== 2
      || fixture.priorNoteVersion !== 1
    ) {
      clearRecoveryFixture();
      return null;
    }
    return fixture;
  } catch {
    clearRecoveryFixture();
    return null;
  }
}

function clearRecoveryFixture() {
  try {
    window.sessionStorage.removeItem(recoveryFixtureKey);
  } catch {
    // The prototype remains usable when browser storage is unavailable.
  }
}

function freshState(defaultDirection, recoveryFixture = null) {
  const recoveringRegeneration = recoveryFixture?.scenario === "note-regeneration-request-only";
  return {
    defaultDirection,
    view: defaultDirection,
    loading: true,
    route: recoveringRegeneration ? "meeting" : "home",
    query: "",
    selectedMeetingId: recoveringRegeneration ? "m-02" : null,
    selectedClaimId: null,
    selectedTranscriptLocator: null,
    claimFilter: defaultDirection === "commitments" ? "commitments" : "all",
    folderFilter: null,
    focusRequest: null,
    reviewingGap: false,
    restored: recoveringRegeneration,
    regenerating: false,
    regenerated: false,
    recoveryState: recoveringRegeneration ? "interrupted" : "none",
    partnerRecovering: false,
    partnerRecovered: false,
    retentionConfirming: false,
    retentionReleased: false,
    capturePhase: "idle",
    consentConfirmed: false,
    captureDegraded: false,
    captureRecovering: false,
    captureOutputMeetingId: null,
    captureHudHidden: false,
    settingsReturnRoute: "home",
    setupStep: "overview",
    setupPermissions: { microphone: true, systemAudio: true },
    retentionPeriodDays: 14,
    retentionDraftDays: null,
    voiceProfileStatus: "valid",
    profileResetConfirming: false,
    enrollmentRecording: false,
    enrollmentRecordingKind: null,
    enrollmentNegativeSource: null,
    enrollmentPolicy: null,
    enrollmentBuildPhase: null,
    enrollmentDiscardConfirming: false
  };
}

function capturePrerequisitesReady() {
  return state.setupPermissions.microphone
    && state.setupPermissions.systemAudio
    && Number.isInteger(state.retentionPeriodDays)
    && state.voiceProfileStatus === "valid";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function kindLabel(kind) {
  const labels = {
    commitment: "Recorded promise",
    customer_need: "Customer need",
    decision: "Decision",
    proposal: "Proposal",
    question: "Open question",
    risk: "Risk"
  };
  if (!labels[kind]) throw new Error(`Unknown claim kind: ${kind}`);
  return labels[kind];
}

function supportTypeLabel(claim) {
  if (!claim.supportType) return null;
  if (claim.supportType === "stated") return "Stated";
  if (claim.supportType === "inferred") return "Inferred";
  throw new Error(`Unknown support type: ${claim.supportType}`);
}

function evidenceLabel(claim) {
  if (claim.evidenceState === "located") return "Words located";
  if (claim.evidenceState === "composed") return "Composed · words not found";
  if (claim.evidenceState === "untestable") return "Untestable · words too short to check";
  if (claim.evidenceState === "unquoted") return "Unquoted · no words supplied";
  throw new Error(`Unknown evidence state: ${claim.evidenceState}`);
}

function claimsFor(meeting) {
  if (meeting.id === "m-02" && state.restored && !state.regenerated) return [];
  const claims = [...meeting.claims];
  if (meeting.id === "m-02" && state.regenerated) claims.push(meeting.regeneratedClaim);
  if (meeting.id === "m-03" && state.partnerRecovered) claims.push(recoveredPartnerClaim);
  return claims;
}

function turnsFor(meeting) {
  if (meeting.id === "m-03" && state.partnerRecovered) return [recoveredPartnerTurn];
  return meeting.turns;
}

function allClaims() {
  return meetings.flatMap((meeting) => claimsFor(meeting).map((claim) => ({ meeting, claim })));
}

function findMeeting(id) {
  return meetings.find((meeting) => meeting.id === id);
}

function findClaim(id) {
  for (const meeting of meetings) {
    const claim = claimsFor(meeting).find((item) => item.id === id);
    if (claim) return { meeting, claim };
  }
  return null;
}

function currentAudio(meeting) {
  if (meeting.id === "m-04" && state.retentionReleased) {
    return { state: "released", detail: "Audio released now. Transcript evidence remains available." };
  }
  return meeting.audio;
}

function noteState(meeting) {
  if (meeting.id === "m-02" && state.restored && !state.regenerated) return "stale";
  return "ready";
}

function assertFixtureIntegrity() {
  const turns = new Map(meetings.flatMap((meeting) => meeting.turns.filter((turn) => !turn.type).map((turn) => [turn.id, turn.text])));
  turns.set(recoveredPartnerTurn.id, recoveredPartnerTurn.text);
  const claims = [
    ...meetings.flatMap((meeting) => meeting.claims),
    meetings.find((meeting) => meeting.id === "m-02").regeneratedClaim,
    recoveredPartnerClaim
  ];
  for (const claim of claims) {
    if (!claim.locator) continue;
    const text = turns.get(claim.locator.turnId);
    const located = text?.slice(claim.locator.start, claim.locator.end);
    if (located !== claim.locator.quote) {
      throw new Error(`Synthetic locator mismatch for ${claim.id}`);
    }
  }
  const discovery = meetings.find((meeting) => meeting.id === "m-05");
  const requiredDiscoveryKinds = ["customer_need", "decision", "commitment", "question", "risk"];
  for (const kind of requiredDiscoveryKinds) {
    if (!discovery.claims.some((claim) => claim.kind === kind)) {
      throw new Error(`Synthetic discovery note is missing ${kind}`);
    }
  }
  if (!discovery.claims.every((claim) => claim.supportType === "stated" || claim.supportType === "inferred")) {
    throw new Error("Synthetic discovery claims require explicit stated or inferred labels");
  }
}

function startLoading() {
  window.clearTimeout(loadTimer);
  state.loading = true;
  render();
  loadTimer = window.setTimeout(() => {
    state.loading = false;
    render();
  }, 350);
}

function resetPrototype(direction = state.defaultDirection) {
  window.clearTimeout(transitionTimer);
  window.clearTimeout(captureTimer);
  clearRecoveryFixture();
  state = freshState(direction);
  startLoading();
}

function setDirection(direction) {
  if (!Object.hasOwn(viewLabels, direction) || direction === state.defaultDirection) return;
  const url = new URL(window.location.href);
  url.searchParams.set("direction", direction);
  window.history.replaceState({}, "", url);
  resetPrototype(direction);
}

function switchView(view) {
  if (!Object.hasOwn(viewLabels, view)) return;
  state.view = view;
  state.route = "home";
  state.query = "";
  state.selectedMeetingId = null;
  state.selectedClaimId = null;
  state.selectedTranscriptLocator = null;
  state.claimFilter = view === "commitments" ? "commitments" : "all";
  state.folderFilter = null;
  state.reviewingGap = false;
  state.focusRequest = "heading";
  render();
}

function syncChrome() {
  document.querySelectorAll("[data-direction]").forEach((button) => {
    const selected = button.dataset.direction === state.defaultDirection;
    button.setAttribute("aria-selected", String(selected));
    button.tabIndex = selected ? 0 : -1;
  });
  document.querySelectorAll("[data-view]").forEach((button) => {
    if (state.route !== "settings" && button.dataset.view === state.view) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });
  const settingsAction = document.querySelector("#settings-action");
  if (state.route === "settings") settingsAction.setAttribute("aria-current", "page");
  else settingsAction.removeAttribute("aria-current");
  const captureLabels = {
    idle: { status: "Nothing is recording", action: "Start meeting", className: "" },
    consent: { status: "Ready to start", action: "Setup open", className: "is-armed" },
    recording: { status: "Recording · healthy", action: "Show status", className: "is-recording" },
    transcribing: { status: "Transcribing locally", action: "Show status", className: "is-transcribing" },
    ready: { status: "Meeting ready", action: "Open meeting", className: "is-ready" }
  };
  const recoveryPending = state.recoveryState === "interrupted" || state.recoveryState === "resuming";
  const captureChrome = state.enrollmentRecording
    ? { status: "Recording · voice enrollment", action: "Show enrollment", className: "is-recording" }
    : state.captureDegraded && state.capturePhase === "recording"
      ? { status: "Recording · system audio interrupted", action: "Show status", className: "is-degraded" }
      : state.capturePhase === "idle" && recoveryPending
        ? { status: "Recovery needs attention", action: "Review recovery", className: "is-setup" }
      : state.capturePhase === "idle" && !capturePrerequisitesReady()
        ? { status: "Setup required", action: "Finish setup", className: "is-setup" }
        : captureLabels[state.capturePhase];
  const productState = document.querySelector("#product-state");
  productState.className = `product-state ${captureChrome.className}`.trim();
  document.querySelector("#product-state-text").textContent = captureChrome.status;
  document.querySelector("#capture-action").textContent = captureChrome.action;
  workspace.setAttribute("aria-label", state.route === "settings" ? "Settings" : `${viewLabels[state.view]} view`);
  footerDirection.textContent = `Viewing ${viewLabels[state.view]} · opens on ${viewLabels[state.defaultDirection]}`;
}

function showToast(message) {
  window.clearTimeout(toastTimer);
  toast.textContent = message;
  toast.hidden = false;
  toastTimer = window.setTimeout(() => {
    toast.hidden = true;
  }, 2600);
}

function restoreRequestedFocus() {
  const request = state.focusRequest;
  state.focusRequest = null;
  if (!request) return;
  window.requestAnimationFrame(() => {
    let target;
    if (request === "capture") target = captureLayer.querySelector("h1, h2");
    if (request === "results") target = workspace.querySelector(".section-heading h2, .empty-state h2");
    if (request === "gap") target = workspace.querySelector("#withheld-turn");
    if (request === "status") target = workspace.querySelector(".destructive-card h2, .stale-panel h2, .failure-panel h2, .state-panel h2");
    if (!target) target = workspace.querySelector("h1");
    if (!target) target = workspace;
    target.setAttribute("tabindex", "-1");
    target.focus({ preventScroll: true });
  });
}

function render() {
  syncChrome();
  if (state.loading) {
    const recovering = state.recoveryState === "interrupted";
    workspace.innerHTML = `
      <section class="loading-view" role="status" aria-busy="true">
        <span class="loading-mark" aria-hidden="true"></span>
        <h1>${recovering ? "Checking interrupted work." : "Opening your meeting memory."}</h1>
        <p>${recovering ? "Rebuilding one synthetic meeting from a content-free recovery receipt." : "Loading five synthetic meetings without touching Preview data."}</p>
      </section>`;
    renderCaptureLayer();
    restoreRequestedFocus();
    return;
  }

  if (state.route === "settings") {
    renderSettings();
  } else if (state.route === "transcript") {
    renderTranscript();
  } else if (state.route === "meeting") {
    renderMeetingDetail();
  } else if (state.route === "claim") {
    renderClaimDetail();
  } else if (state.view === "meetings") {
    renderMeetingsHome();
  } else if (state.view === "commitments") {
    renderCommitmentsHome();
  } else {
    renderRetrievalHome();
  }
  renderCaptureLayer();
  restoreRequestedFocus();
}

function renderCaptureLayer() {
  const consentOpen = state.capturePhase === "consent";
  document.querySelector(".review-bar").inert = consentOpen;
  document.querySelector(".app-shell").inert = consentOpen;
  captureLayer.className = "";
  captureLayer.innerHTML = "";
  if (state.capturePhase === "idle" || (state.captureHudHidden && state.capturePhase !== "consent")) return;
  if (state.capturePhase === "consent") {
    captureLayer.className = "is-modal";
    captureLayer.innerHTML = `
      <div class="capture-scrim">
        <section class="capture-dialog" role="dialog" aria-modal="true" aria-labelledby="capture-consent-title">
          <p class="kicker">Manual start · one capture attempt</p>
          <h1 id="capture-consent-title">Ready to remember this meeting?</h1>
          <p class="lede">Record the microphone and system audio on this Mac, then transcribe after you stop.</p>
          <div class="section-heading"><h2>Before recording</h2><span>Ready</span></div>
          <div class="preflight-list" aria-label="Capture readiness">
            <div><strong>Microphone</strong><span>Ready · voice profile loaded</span></div>
            <div><strong>System audio</strong><span>Ready · headphones expected</span></div>
            <div><strong>Audio retention</strong><span>Release after 14 days</span></div>
            <div><strong>Processing</strong><span>Local on this Mac</span></div>
          </div>
          <label class="consent-check">
            <input id="capture-consent" type="checkbox" ${state.consentConfirmed ? "checked" : ""} />
            <span><strong>I confirmed everyone knows this meeting will be recorded.</strong><small>This attestation applies only to this attempt. The app does not decide whether consent is sufficient.</small></span>
          </label>
          <div class="capture-actions">
            <button class="primary-button" type="button" data-action="begin-capture" ${state.consentConfirmed ? "" : "disabled"}>Start recording</button>
            <button class="secondary-button" type="button" data-action="cancel-capture">Cancel</button>
          </div>
          <p class="prototype-boundary">Synthetic interaction only. No microphone, system audio, model, or product record is used.</p>
        </section>
      </div>`;
    return;
  }
  captureLayer.className = "is-hud";
  if (state.capturePhase === "recording") {
    const degraded = state.captureDegraded;
    captureLayer.innerHTML = `
      <aside class="floating-capture-hud ${degraded ? "is-degraded" : ""}" aria-label="Recording status">
        <header><div><p class="kicker">${degraded ? "Recording degraded" : "Recording now"}</p><h2>${degraded ? "System audio interrupted" : "Listening to both sides"}</h2></div><button class="hud-dismiss" type="button" data-action="hide-capture-hud" aria-label="Dismiss recording status">Dismiss</button></header>
        <div class="capture-clock"><span>${degraded ? "00:18" : "00:12"}</span><small>${degraded ? "Still recording" : "Elapsed"}</small></div>
        <div class="channel-health">
          <div class="channel-row is-healthy"><span class="channel-mark" aria-hidden="true"></span><strong>Microphone · Me</strong><span>Healthy</span></div>
          <div class="channel-row ${degraded ? "is-interrupted" : "is-healthy"}"><span class="channel-mark" aria-hidden="true"></span><strong>System audio · Them</strong><span>${degraded ? "Interrupted at 00:12" : "Healthy"}</span></div>
        </div>
        ${degraded ? `<p class="capture-warning"><strong>Recording continues with a known gap.</strong> Far-end words may be missing.</p>` : `<p class="capture-guidance">Me/Them are capture channels, not named speakers.</p>`}
        <div class="capture-actions">
          <button class="primary-button stop-button" type="button" data-action="stop-capture">Stop recording</button>
          ${degraded
            ? `<button class="secondary-button" type="button" data-action="recover-system-audio" ${state.captureRecovering ? "disabled" : ""}>${state.captureRecovering ? "Checking…" : "Try again"}</button>`
            : `<button class="text-button prototype-action" type="button" data-action="preview-degraded">Preview interruption</button>`}
        </div>
        <p class="prototype-boundary">Prototype state · no audio captured</p>
      </aside>`;
    return;
  }
  if (state.capturePhase === "transcribing") {
    captureLayer.innerHTML = `
      <aside class="floating-capture-hud capture-processing" role="status" aria-busy="true">
        <header><div><p class="kicker">Recording saved</p><h2>Transcribing locally</h2></div><button class="hud-dismiss" type="button" data-action="hide-capture-hud" aria-label="Dismiss processing status">Dismiss</button></header>
        <p class="hud-copy">Canonical words come first. The library remains available while the synthetic transition finishes.</p>
        <div class="compact-progress"><span class="is-done">Capture saved</span><span class="is-active">Transcript</span><span>Note</span></div>
        <p class="prototype-boundary">No model is running</p>
      </aside>`;
    return;
  }
  if (state.capturePhase === "ready") {
    const output = findMeeting(state.captureOutputMeetingId) || findMeeting("m-05");
    const hasGap = output.id === "m-02";
    captureLayer.innerHTML = `
      <aside class="floating-capture-hud capture-ready ${hasGap ? "has-gap" : ""}" role="status">
        <header><div><p class="kicker">${hasGap ? "Ready · known gap" : "Meeting ready"}</p><h2>${escapeHtml(output.title)}</h2></div><button class="hud-dismiss" type="button" data-action="hide-capture-hud" aria-label="Dismiss ready status">Dismiss</button></header>
        <p class="hud-copy">${hasGap ? "The interrupted channel remains visible as missing coverage." : "The synthetic note and canonical transcript are ready to inspect."}</p>
        <button class="primary-button" type="button" data-action="open-captured-meeting">Open meeting</button>
        <p class="prototype-boundary">Opens an existing synthetic fixture</p>
      </aside>`;
  }
}

function searchFormMarkup(compact = false) {
  return `
    <form class="search-block" id="search-form">
      <label for="memory-search">Find exact words</label>
      <div class="search-row">
        <input id="memory-search" name="query" type="search" value="${escapeHtml(state.query)}" placeholder="Try “legal review”" autocomplete="off" />
        <button type="submit">Find</button>
      </div>
      <p class="search-help">Searches claim text, canonical transcript words, meeting titles, and folders on this Mac.${compact ? "" : " Exact words stay linked to their source."}</p>
    </form>`;
}

function taskMarkup() {
  return `
    <section class="task-card" aria-label="Shared review task">
      <span class="label">Same task from every starting view</span>
      <p>Find what could <strong>block the reporting pilot</strong>, open the discovery call, then trace that risk to exact words.</p>
    </section>`;
}

function setupProgressMarkup(activeStep) {
  const steps = [
    { id: "permissions", label: "1 · Permissions" },
    { id: "retention", label: "2 · Audio" },
    { id: "profile", label: "3 · Voice profile" }
  ];
  const activeIndex = steps.findIndex((step) => step.id === activeStep);
  return `
    <ol class="setup-progress" aria-label="First-run setup progress">
      ${steps.map((step, index) => `<li class="${index === activeIndex ? "is-active" : index < activeIndex ? "is-done" : ""}">${escapeHtml(step.label)}</li>`).join("")}
    </ol>`;
}

function settingsRailMarkup() {
  return `
    <aside class="settings-rail">
      <p class="kicker">Local controls</p>
      <h2>Settings</h2>
      <p>Readiness, meeting-audio retention, and the owner voice profile stay visible in one place.</p>
      <button class="secondary-button" type="button" data-action="close-settings" ${state.enrollmentRecording ? "disabled" : ""}>Back to ${escapeHtml(viewLabels[state.view])}</button>
      <section class="settings-boundary">
        <span class="label">Prototype boundary</span>
        <p>These controls change synthetic browser state only. They do not inspect macOS permissions, record enrollment audio, or delete product data.</p>
      </section>
    </aside>`;
}

function settingsOverviewMarkup() {
  const ready = capturePrerequisitesReady();
  const captureBusy = state.capturePhase !== "idle" || state.enrollmentRecording;
  const retention = Number.isInteger(state.retentionPeriodDays)
    ? `Delete after ${state.retentionPeriodDays} day${state.retentionPeriodDays === 1 ? "" : "s"}`
    : "Choose a period";
  const profileReady = state.voiceProfileStatus === "valid";
  return `
    <section class="settings-content">
      <header class="settings-intro">
        <p class="kicker">Readiness</p>
        <h1>${ready ? "Ready to record." : "Finish setup before recording."}</h1>
        <p class="lede">Start is available only when both capture permissions, an audio auto-deletion period, and a valid owner voice profile are present.</p>
      </header>
      <div class="readiness-list" aria-label="Capture prerequisites">
        <article class="readiness-row ${state.setupPermissions.microphone ? "is-ready" : "is-needed"}">
          <div><span class="label">Microphone</span><strong>${state.setupPermissions.microphone ? "Allowed" : "Permission needed"}</strong></div>
          <span>${state.setupPermissions.microphone ? "Required source is available" : "Recording cannot start"}</span>
        </article>
        <article class="readiness-row ${state.setupPermissions.systemAudio ? "is-ready" : "is-needed"}">
          <div><span class="label">System audio</span><strong>${state.setupPermissions.systemAudio ? "Allowed" : "Permission needed"}</strong></div>
          <span>${state.setupPermissions.systemAudio ? "Required source is available" : "Recording cannot start"}</span>
        </article>
        <article class="readiness-row ${Number.isInteger(state.retentionPeriodDays) ? "is-ready" : "is-needed"}">
          <div><span class="label">Meeting audio</span><strong>${escapeHtml(retention)}</strong></div>
          <button class="text-button" type="button" data-action="change-retention" ${captureBusy ? "disabled" : ""}>${Number.isInteger(state.retentionPeriodDays) ? "Change" : "Choose"}</button>
        </article>
        <article class="readiness-row ${profileReady ? "is-ready" : "is-needed"}">
          <div><span class="label">Voice profile</span><strong>${profileReady ? "Valid · owner only" : "Enrollment needed"}</strong></div>
          ${profileReady
            ? `<button class="text-button" type="button" data-action="request-profile-reset" ${captureBusy ? "disabled" : ""}>Reset</button>`
            : `<button class="text-button" type="button" data-action="review-profile-needed" ${captureBusy ? "disabled" : ""}>Review next step</button>`}
        </article>
      </div>
      ${state.profileResetConfirming ? `
        <section class="destructive-card" aria-labelledby="reset-profile-title">
          <p class="label">Separate trust action</p>
          <h2 id="reset-profile-title">Reset the voice profile?</h2>
          <p>This removes the private profile, its calibrated threshold, and enrollment provenance. Meetings, notes, transcripts, retained meeting audio, and your auto-deletion choice remain.</p>
          <p><strong>Recording will stay unavailable until enrollment is complete again.</strong></p>
          <div class="confirmation-actions">
            <button class="danger-button" type="button" data-action="confirm-profile-reset">Reset voice profile</button>
            <button class="secondary-button" type="button" data-action="cancel-profile-reset">Cancel</button>
          </div>
        </section>` : ""}
      <section class="settings-secondary">
        <div>
          <span class="label">Calendar</span>
          <h2>Off · optional</h2>
          <p>Capture works without calendar access. A later preparation brief can ask separately.</p>
        </div>
        <div>
          <span class="label">Synthetic disk snapshot</span>
          <h2>46.6 MB audio held</h2>
          <p>Across four meetings. Notes and transcripts are stored separately.</p>
        </div>
      </section>
      ${captureBusy ? `<p class="settings-lock"><strong>Recording state is active.</strong> Retention and profile changes wait until this attempt finishes.</p>` : ""}
      <button class="text-button prototype-action" type="button" data-action="preview-first-run" ${captureBusy ? "disabled" : ""}>Preview the first-run state</button>
    </section>`;
}

function permissionsSetupMarkup() {
  const bothAllowed = state.setupPermissions.microphone && state.setupPermissions.systemAudio;
  return `
    <section class="settings-content">
      ${setupProgressMarkup("permissions")}
      <header class="settings-intro compact">
        <p class="kicker">First run · required</p>
        <h1>Allow the two sources recording needs.</h1>
        <p class="lede">Without both sources, the app can still open existing meetings but cannot start a supported recording.</p>
      </header>
      <div class="permission-list">
        <article>
          <div><span class="label">Microphone</span><h2>${state.setupPermissions.microphone ? "Allowed" : "Permission needed"}</h2><p>Captures the enrolled operator at the microphone.</p></div>
          <button class="secondary-button" type="button" data-action="grant-setup-permission" data-permission="microphone" ${state.setupPermissions.microphone ? "disabled" : ""}>${state.setupPermissions.microphone ? "Shown as allowed" : "Show as allowed"}</button>
        </article>
        <article>
          <div><span class="label">System audio</span><h2>${state.setupPermissions.systemAudio ? "Allowed" : "Permission needed"}</h2><p>Captures the far end while headphones are in use.</p></div>
          <button class="secondary-button" type="button" data-action="grant-setup-permission" data-permission="systemAudio" ${state.setupPermissions.systemAudio ? "disabled" : ""}>${state.setupPermissions.systemAudio ? "Shown as allowed" : "Show as allowed"}</button>
        </article>
      </div>
      <p class="prototype-boundary">The web prototype does not request macOS permission. These buttons expose the granted and blocked states for review.</p>
      <button class="primary-button" type="button" data-action="continue-to-retention" ${bothAllowed ? "" : "disabled"}>Choose audio auto-deletion</button>
    </section>`;
}

function retentionSetupMarkup() {
  const changing = state.setupStep === "retention-change";
  const options = [1, 7, 14, 30];
  return `
    <section class="settings-content">
      ${changing ? "" : setupProgressMarkup("retention")}
      <header class="settings-intro compact">
        <p class="kicker">${changing ? "Meeting audio" : "First run · your choice"}</p>
        <h1>Choose when meeting audio is deleted.</h1>
        <p class="lede">Notes, transcripts, and text evidence stay. Deleting audio removes playback, audio review, and re-transcription.</p>
      </header>
      <fieldset class="retention-choices">
        <legend>Auto-delete meeting audio</legend>
        ${options.map((days) => `
          <label>
            <input type="radio" name="retention-period" value="${days}" ${state.retentionDraftDays === days ? "checked" : ""} />
            <span><strong>After ${days} day${days === 1 ? "" : "s"}</strong><small>The choice applies to each new meeting.</small></span>
          </label>`).join("")}
      </fieldset>
      <p class="choice-help">No option is chosen for a new setup. You can release one meeting’s audio sooner from its note.</p>
      <div class="setup-actions">
        <button class="primary-button" type="button" data-action="save-retention" ${Number.isInteger(state.retentionDraftDays) ? "" : "disabled"}>${changing ? "Save auto-deletion" : "Continue to voice profile"}</button>
        <button class="secondary-button" type="button" data-action="${changing ? "cancel-retention-change" : "back-to-permissions"}">${changing ? "Cancel" : "Back"}</button>
      </div>
    </section>`;
}

function profileNeededMarkup() {
  return `
    <section class="settings-content">
      ${setupProgressMarkup("profile")}
      <header class="settings-intro compact">
        <p class="kicker">Voice profile · required</p>
        <h1>Your voice profile is still needed.</h1>
        <p class="lede">It helps keep the transcript centered on the enrolled operator. It does not name other speakers.</p>
      </header>
      <section class="profile-explainer">
        <h2>Enrollment uses separate calibration recordings.</h2>
        <ol>
          <li><strong>Two operator sittings</strong><span>At least one hour apart; different days are ideal.</span></li>
          <li><strong>One permitted other-voice sample</strong><span>Public-domain or licensed speech, or a person who agreed to make the calibration recording.</span></li>
          <li><strong>One measured policy choice</strong><span>Choose the trade-off only after both observed error rates are visible.</span></li>
        </ol>
        <p>Dedicated calibration audio and working files are deleted as soon as the private derived material is safely stored. Meetings keep their own retention period.</p>
      </section>
      <p class="settings-lock"><strong>Recording remains unavailable.</strong> Complete guided enrollment before starting a supported meeting. The returning fixture below is independent; it does not finish this enrollment.</p>
      <div class="setup-actions">
        <button class="primary-button" type="button" data-action="start-enrollment">Start voice enrollment</button>
        <button class="secondary-button" type="button" data-action="load-returning-profile-fixture">Load separate returning-profile fixture</button>
      </div>
    </section>`;
}

function enrollmentProgressMarkup(active) {
  const steps = [
    { id: "voice-one", label: "1 · Voice sample" },
    { id: "voice-two", label: "2 · Later sample" },
    { id: "other-voice", label: "3 · Other voice" },
    { id: "policy", label: "4 · Policy" }
  ];
  const activeIndex = steps.findIndex((step) => step.id === active);
  return `
    <ol class="enrollment-progress" aria-label="Voice enrollment progress">
      ${steps.map((step, index) => `<li class="${index === activeIndex ? "is-active" : index < activeIndex ? "is-done" : ""}">${escapeHtml(step.label)}</li>`).join("")}
    </ol>`;
}

function enrollmentDiscardMarkup() {
  return `
    <div class="enrollment-discard">
      ${state.enrollmentDiscardConfirming ? `
        <section class="destructive-card" aria-labelledby="discard-enrollment-title">
          <p class="label">Incomplete enrollment</p>
          <h2 id="discard-enrollment-title">Discard this enrollment?</h2>
          <p>Dedicated enrollment audio, private derived samples, comparison scores, and partial profile work are removed. Existing meetings, meeting audio, notes, transcripts, retention choice, and any previously valid profile remain.</p>
          <div class="confirmation-actions">
            <button class="danger-button" type="button" data-action="confirm-enrollment-discard">Discard enrollment</button>
            <button class="secondary-button" type="button" data-action="cancel-enrollment-discard">Cancel</button>
          </div>
        </section>` : `<button class="text-button danger-text" type="button" data-action="request-enrollment-discard">Discard enrollment</button>`}
    </div>`;
}

function enrollmentRecorderMarkup(kind) {
  const isOtherVoice = kind === "other-voice";
  return `
    <section class="enrollment-recorder" role="status" aria-live="polite">
      <div class="recording-pulse" aria-hidden="true"></div>
      <div>
        <span class="label">Recording now · synthetic</span>
        <h2>${isOtherVoice ? "Listening to the permitted comparison speech" : "Listening to your voice"}</h2>
        <p>Microphone only. System audio and existing meetings are not used.</p>
      </div>
      <button class="primary-button stop-button" type="button" data-action="stop-enrollment-recording">Stop sample</button>
    </section>`;
}

function enrollmentSittingMarkup(which) {
  const first = which === 1;
  const kind = first ? "operator-one" : "operator-two";
  const recording = state.enrollmentRecording && state.enrollmentRecordingKind === kind;
  return `
    <section class="settings-content">
      ${enrollmentProgressMarkup(first ? "voice-one" : "voice-two")}
      <header class="settings-intro compact enrollment-intro">
        <p class="kicker">Voice enrollment · ${first ? "first" : "later"} sitting</p>
        <h1>${first ? "Record your first voice sample." : "Record a separate voice sample."}</h1>
        <p class="lede">Speak naturally in a quiet place. The app reports whether it has enough usable speech; it does not turn a progress percentage into proof.</p>
      </header>
      ${recording ? enrollmentRecorderMarkup(kind) : `
        <section class="enrollment-card">
          <div><span class="label">Before recording</span><h2>Only your microphone is used.</h2><p>${first ? "This starts a dedicated calibration sitting, not a meeting." : "The recorded timestamps must show at least one hour since the first sitting; another day is ideal."}</p></div>
          <button class="primary-button" type="button" data-action="start-enrollment-recording" data-kind="${kind}">Start sample</button>
        </section>`}
      <p class="lifecycle-note"><strong>Short-lived source audio.</strong> The dedicated WAV, transcript, segments, and working files are deleted as soon as the private derived material is safely stored. Failure or discard removes partial work.</p>
      ${enrollmentDiscardMarkup()}
    </section>`;
}

function enrollmentWaitMarkup() {
  return `
    <section class="settings-content">
      ${enrollmentProgressMarkup("voice-two")}
      <header class="settings-intro compact enrollment-intro">
        <p class="kicker">First sitting saved</p>
        <h1>Return at least one hour later.</h1>
        <p class="lede">Another day is ideal. The product reads recorded timestamps and will not treat two clips from one sitting as separate evidence.</p>
      </header>
      <section class="readiness-list enrollment-facts">
        <article class="readiness-row is-ready"><div><span class="label">Private derived sample</span><strong>Stored for comparison</strong></div><span>Owner account only</span></article>
        <article class="readiness-row is-ready"><div><span class="label">Dedicated source audio</span><strong>Deleted after safe storage</strong></div><span>No meeting was created</span></article>
        <article class="readiness-row is-needed"><div><span class="label">Second sitting</span><strong>Not eligible yet</strong></div><span>Measured at runtime</span></article>
      </section>
      <div class="setup-actions">
        <button class="secondary-button prototype-action" type="button" data-action="load-later-sitting-fixture">Load eligible later-sitting fixture</button>
        <button class="text-button" type="button" data-action="close-settings">Return to meetings</button>
      </div>
      <p class="prototype-boundary">The fixture advances review without asserting that real time elapsed.</p>
      ${enrollmentDiscardMarkup()}
    </section>`;
}

function enrollmentReviewMarkup() {
  return `
    <section class="settings-content">
      ${enrollmentProgressMarkup("other-voice")}
      <header class="settings-intro compact enrollment-intro">
        <p class="kicker">Two-sitting fixture · review</p>
        <h1>Your samples can now be compared.</h1>
        <p class="lede">The exact counts and gap come from the enrollment record. Refused or incomplete material cannot reach the next step.</p>
      </header>
      <div class="enrollment-metrics" aria-label="Synthetic operator sample facts">
        <div><strong>2</strong><span>separate sittings</span></div>
        <div><strong>25 hr</strong><span>fixture gap</span></div>
        <div><strong>100</strong><span>held-out samples</span></div>
      </div>
      <p class="lifecycle-note"><strong>Non-personal fixture.</strong> These counts test the interaction and do not describe the reviewer. Both dedicated recordings are already represented as deleted.</p>
      <div class="setup-actions">
        <button class="primary-button" type="button" data-action="continue-to-negative-sample">Add permitted other-voice speech</button>
      </div>
      ${enrollmentDiscardMarkup()}
    </section>`;
}

function negativeSampleMarkup() {
  const recording = state.enrollmentRecording && state.enrollmentRecordingKind === "other-voice";
  return `
    <section class="settings-content">
      ${enrollmentProgressMarkup("other-voice")}
      <header class="settings-intro compact enrollment-intro">
        <p class="kicker">Comparison speech · required</p>
        <h1>Measure what the gate might mistake for you.</h1>
        <p class="lede">Use permitted speech only. Do not record a private conversation, an unaware bystander, or unlicensed program audio.</p>
      </header>
      ${recording ? enrollmentRecorderMarkup("other-voice") : `
        <fieldset class="negative-source-choices">
          <legend>Choose the source for this calibration recording</legend>
          <label><input type="radio" name="negative-source" value="licensed" ${state.enrollmentNegativeSource === "licensed" ? "checked" : ""} /><span><strong>Public-domain or licensed playback</strong><small>Play permitted speech near the microphone.</small></span></label>
          <label><input type="radio" name="negative-source" value="consenting" ${state.enrollmentNegativeSource === "consenting" ? "checked" : ""} /><span><strong>A consenting person</strong><small>They knowingly record speech for this calibration.</small></span></label>
        </fieldset>
        <p class="choice-help">The registered floor is 60 seconds of scorable speech across at least 20 segments. Neither number is a statistical guarantee.</p>
        <button class="primary-button" type="button" data-action="start-enrollment-recording" data-kind="other-voice" ${state.enrollmentNegativeSource ? "" : "disabled"}>Start comparison sample</button>`}
      <p class="lifecycle-note"><strong>Separate lifecycle.</strong> This dedicated audio and its working files are deleted after private comparison scores are safely stored. It never becomes meeting content.</p>
      ${enrollmentDiscardMarkup()}
    </section>`;
}

function voicePolicyMarkup() {
  const policies = [
    { id: "preserve", label: "Preserve more of my speech", operator: "1 of 100 operator samples dropped", other: "31 of 40 other-voice samples included" },
    { id: "middle", label: "Choose the measured middle point", operator: "5 of 100 operator samples dropped", other: "29 of 40 other-voice samples included" },
    { id: "exclude", label: "Keep more other voices out", operator: "20 of 100 operator samples dropped", other: "22 of 40 other-voice samples included" }
  ];
  return `
    <section class="settings-content">
      ${enrollmentProgressMarkup("policy")}
      <header class="settings-intro compact enrollment-intro">
        <p class="kicker">Measured policy · no default</p>
        <h1>Choose which error to avoid first.</h1>
        <p class="lede">Dropping your speech loses meeting memory. Including another voice can misstate who said it. Both measured costs stay visible.</p>
      </header>
      <fieldset class="voice-policy-choices">
        <legend>Non-personal deterministic fixture</legend>
        ${policies.map((policy) => `
          <label>
            <input type="radio" name="voice-policy" value="${policy.id}" ${state.enrollmentPolicy === policy.id ? "checked" : ""} />
            <span><strong>${escapeHtml(policy.label)}</strong><small>${escapeHtml(policy.operator)}</small><small>${escapeHtml(policy.other)}</small></span>
          </label>`).join("")}
      </fieldset>
      <p class="choice-help">These rates come from the repository’s fixed non-personal score fixture. They are not measurements of your voice and no row is recommended.</p>
      <div class="setup-actions">
        <button class="primary-button" type="button" data-action="build-enrollment-profile" ${state.enrollmentPolicy ? "" : "disabled"}>Build selected profile</button>
      </div>
      ${enrollmentDiscardMarkup()}
    </section>`;
}

function enrollmentBuildMarkup() {
  const persisting = state.enrollmentBuildPhase === "persisting";
  return `
    <section class="settings-content">
      ${enrollmentProgressMarkup("policy")}
      <header class="settings-intro compact enrollment-intro">
        <p class="kicker">Private profile · local build</p>
        <h1>${persisting ? "Saving the profile for this account." : "Building the selected voice profile."}</h1>
        <p class="lede">Start remains blocked until the selected measured row and its provenance are safely stored and can be validated again.</p>
      </header>
      <div class="build-progress" role="status" aria-live="polite">
        <span class="is-done">Measurements checked</span>
        <span class="${persisting ? "is-done" : "is-active"}">Profile built</span>
        <span class="${persisting ? "is-active" : ""}">Owner-only save</span>
      </div>
      <p class="lifecycle-note"><strong>No valid profile yet.</strong> A build result without successful private persistence cannot enable Start. Failure deletes partial output and leaves enrollment incomplete.</p>
      <p class="prototype-boundary">Synthetic transition only. No model runs and no profile is written.</p>
    </section>`;
}

function renderSettings() {
  let content;
  if (state.setupStep === "permissions") content = permissionsSetupMarkup();
  else if (state.setupStep === "retention" || state.setupStep === "retention-change") content = retentionSetupMarkup();
  else if (state.setupStep === "profile") content = profileNeededMarkup();
  else if (state.setupStep === "enrollment-one") content = enrollmentSittingMarkup(1);
  else if (state.setupStep === "enrollment-wait") content = enrollmentWaitMarkup();
  else if (state.setupStep === "enrollment-two") content = enrollmentSittingMarkup(2);
  else if (state.setupStep === "enrollment-review") content = enrollmentReviewMarkup();
  else if (state.setupStep === "enrollment-negative") content = negativeSampleMarkup();
  else if (state.setupStep === "enrollment-policy") content = voicePolicyMarkup();
  else if (state.setupStep === "enrollment-build") content = enrollmentBuildMarkup();
  else content = settingsOverviewMarkup();
  workspace.innerHTML = `<div class="settings-layout">${settingsRailMarkup()}${content}</div>`;
}

function meetingsNewestFirst() {
  return [...meetings].sort((a, b) => meetingTimestamp(b) - meetingTimestamp(a));
}

function meetingTimestamp(meeting) {
  return Date.parse(meeting.date.replace(" at ", " "));
}

function meetingRowsMarkup(list = meetingsNewestFirst()) {
  return list.map((meeting) => {
    const audio = currentAudio(meeting);
    const status = meeting.id === "m-03" && !state.partnerRecovered
      ? "Transcript unavailable"
      : meeting.id === "m-02" && state.regenerated
        ? "Transcript ready · note version 2"
        : meeting.id === "m-02" && state.restored
          ? "Transcript changed · note needs regeneration"
      : meeting.transcriptStatus === "partial"
        ? "Partial transcript · 1 withheld turn"
        : audio.state === "released"
          ? "Transcript ready · audio released"
          : "Transcript ready";
    return `
      <button class="meeting-row" type="button" data-action="open-meeting" data-meeting-id="${meeting.id}">
        <span>
          <span class="row-title">${escapeHtml(meeting.title)}</span>
          <span class="row-meta">${escapeHtml(meeting.date)} · ${escapeHtml(meeting.folder)} · ${escapeHtml(status)}</span>
        </span>
        <span class="row-action">Open meeting</span>
      </button>`;
  }).join("");
}

function renderMeetingsHome() {
  const results = search(state.query);
  workspace.innerHTML = `
    <div class="workspace-grid">
      <aside class="rail">
        <p class="kicker">Meetings view</p>
        <h2 class="rail-title">Browse meetings</h2>
        <p class="rail-copy">Begin with the meeting, then find the claim inside it.</p>
        <div class="filter-stack" aria-label="Meeting folders">
          <button class="filter-button" type="button" data-action="clear-query" aria-pressed="${state.folderFilter === null}"><span>All meetings</span><small>${meetings.length}</small></button>
          <button class="filter-button" type="button" aria-pressed="${state.folderFilter === "Operations"}" data-action="folder-filter" data-folder="Operations"><span>Operations</span><small>${meetings.filter((meeting) => meeting.folder === "Operations").length}</small></button>
          <button class="filter-button" type="button" aria-pressed="${state.folderFilter === "Partnerships"}" data-action="folder-filter" data-folder="Partnerships"><span>Partnerships</span><small>${meetings.filter((meeting) => meeting.folder === "Partnerships").length}</small></button>
          <button class="filter-button" type="button" aria-pressed="${state.folderFilter === "Sales"}" data-action="folder-filter" data-folder="Sales"><span>Sales</span><small>${meetings.filter((meeting) => meeting.folder === "Sales").length}</small></button>
        </div>
        ${taskMarkup()}
      </aside>
      <section class="content-pane">
        <div class="home-intro">
          <p class="kicker">Retained meetings</p>
          <h1>Your Library.</h1>
          <p class="lede">Open a meeting by date, or search across its note and transcript.</p>
        </div>
        ${searchFormMarkup()}
        ${state.query ? meetingSearchResultsMarkup(results) : `
          <div class="section-heading"><h2>Recent meetings</h2><span>${meetings.length} retained</span></div>
          <div class="meeting-list">${meetingRowsMarkup()}</div>`}
      </section>
    </div>`;
}

function filteredClaims() {
  const rows = allClaims();
  if (state.claimFilter === "decisions") return rows.filter(({ claim }) => claim.kind === "decision");
  if (state.claimFilter === "commitments") return rows.filter(({ claim }) => claim.kind === "commitment");
  if (state.claimFilter === "open") return rows.filter(({ claim }) => claim.kind === "proposal" || claim.kind === "question");
  return rows;
}

function renderCommitmentsHome() {
  const results = search(state.query);
  const rows = state.query ? results : filteredClaims().map(({ meeting, claim }) => ({ type: "claim", meeting, claim }));
  workspace.innerHTML = `
    <div class="workspace-grid">
      <aside class="rail">
        <p class="kicker">Promises view</p>
        <h2 class="rail-title">Recorded promises</h2>
        <p class="rail-copy">Begin with recorded promises across meetings. Switch filters to inspect decisions, proposals, or questions. This is evidence, not a task list.</p>
        <div class="filter-stack" aria-label="Claim type">
          ${filterButton("all", "All memory", allClaims().length)}
          ${filterButton("decisions", "Decisions", allClaims().filter(({ claim }) => claim.kind === "decision").length)}
          ${filterButton("commitments", "Recorded promises", allClaims().filter(({ claim }) => claim.kind === "commitment").length)}
          ${filterButton("open", "Proposals & questions", allClaims().filter(({ claim }) => claim.kind === "proposal" || claim.kind === "question").length)}
        </div>
        <button class="secondary-button" type="button" data-action="copy-promises">Copy recorded promises</button>
        ${taskMarkup()}
      </aside>
      <section class="content-pane">
        <div class="home-intro">
          <p class="kicker">Across your meetings</p>
          <h1>What did we promise?</h1>
          <p class="lede">Recorded promises lead. Their source meeting and exact words stay one step away.</p>
        </div>
        ${searchFormMarkup()}
        <div class="section-heading"><h2>${state.query ? `Results for “${escapeHtml(state.query)}”` : escapeHtml(filterTitle())}</h2><span>${rows.length} ${rows.length === 1 ? (state.query ? "result" : "claim") : (state.query ? "results" : "claims")}</span></div>
        ${rows.length ? `<div class="${state.query ? "result-list" : "claim-list"}">${state.query ? rows.map((result) => resultRowMarkup(result)).join("") : claimRowsMarkup(rows)}</div>` : emptySearchMarkup()}
      </section>
    </div>`;
}

function filterButton(value, label, count) {
  return `<button class="filter-button" type="button" data-action="claim-filter" data-filter="${value}" aria-pressed="${state.claimFilter === value}"><span>${escapeHtml(label)}</span><small>${count}</small></button>`;
}

function filterTitle() {
  return {
    all: "All claims",
    decisions: "Decisions",
    commitments: "Recorded promises",
    open: "Proposals and open questions"
  }[state.claimFilter];
}

function claimRowsMarkup(results) {
  return results.map((result) => {
    const { meeting, claim } = result;
    return `
      <button class="claim-row" type="button" data-action="open-claim" data-claim-id="${claim.id}">
        <span class="claim-kind ${claim.kind}">${escapeHtml(kindLabel(claim.kind))}</span>
        <span>
          <span class="row-title">${escapeHtml(claim.text)}</span>
          <span class="row-meta">${escapeHtml(meeting.title)} · ${escapeHtml(meeting.date)} · <span class="evidence-state ${claim.evidenceState}">${escapeHtml(evidenceLabel(claim))}</span></span>
        </span>
        <span class="row-action">Open claim</span>
      </button>`;
  }).join("");
}

function renderRetrievalHome() {
  const results = search(state.query);
  workspace.innerHTML = `
    <div class="workspace-grid retrieval-grid">
      <aside class="rail">
        <p class="kicker">Find view</p>
        <h2 class="rail-title">Find what you remember</h2>
        <p class="rail-copy">Start with a subject or exact phrase. Results can be claims, transcript words, or meetings.</p>
        ${searchFormMarkup(true)}
        ${state.query ? searchResultsListMarkup(results) : `<p class="rail-note">Use the navigation above to browse Meetings or review Promises without losing the shared meeting record.</p>`}
      </aside>
      <section class="content-pane">
        ${retrievalContentMarkup()}
      </section>
    </div>`;
}

function retrievalContentMarkup() {
  return `
    <div class="home-intro">
      <p class="kicker">Meeting memory</p>
      <h1>Ask with the words you have.</h1>
      <p class="lede">Land on an answer, then check the canonical transcript—the closest supported record of what was audibly said, with known gaps still visible—before relying on it.</p>
    </div>
    ${taskMarkup()}
    <div class="section-heading"><h2>Recent memory</h2><span>Not a task list</span></div>
    <div class="claim-list">${claimRowsMarkup(allClaims()
      .filter(({ claim }) => ["decision", "commitment", "risk"].includes(claim.kind))
      .sort((a, b) => meetingTimestamp(b.meeting) - meetingTimestamp(a.meeting))
      .slice(0, 4)
      .map(({ meeting, claim }) => ({ type: "claim", meeting, claim })))}</div>`;
}

function search(query) {
  const needle = query.trim().toLocaleLowerCase();
  if (!needle) return [];
  const results = [];
  for (const { meeting, claim } of allClaims()) {
    if (claim.text.toLocaleLowerCase().includes(needle)) results.push({ type: "claim", meeting, claim });
  }
  for (const meeting of meetings) {
    for (const turn of turnsFor(meeting)) {
      const normalizedTurn = turn.text?.toLocaleLowerCase();
      const start = normalizedTurn?.indexOf(needle) ?? -1;
      const includedInCurrentTranscript = !turn.type && (!turn.withheld || (meeting.id === "m-02" && state.restored));
      if (includedInCurrentTranscript && start >= 0) {
        results.push({
          type: "transcript",
          meeting,
          turn,
          locator: { turnId: turn.id, start, end: start + needle.length, quote: turn.text.slice(start, start + needle.length) }
        });
      }
    }
    if (`${meeting.title} ${meeting.folder}`.toLocaleLowerCase().includes(needle)) {
      results.push({ type: "meeting", meeting });
    }
  }
  return results;
}

function meetingSearchResultsMarkup(results) {
  if (!results.length) return emptySearchMarkup();
  const grouped = new Map();
  for (const result of results) {
    const existing = grouped.get(result.meeting.id) || { meeting: result.meeting, results: [] };
    existing.results.push(result);
    grouped.set(result.meeting.id, existing);
  }
  return `
    <div class="section-heading"><h2>Matching meetings</h2><span>${grouped.size} ${grouped.size === 1 ? "meeting" : "meetings"}</span></div>
    ${[...grouped.values()].map(({ meeting, results: groupResults }) => `
      <section class="meeting-search-group">
        <header class="meeting-search-header">
          <div><strong>${escapeHtml(meeting.title)}</strong><span>${escapeHtml(meeting.date)} · ${groupResults.length} ${groupResults.length === 1 ? "match" : "matches"}</span></div>
          <button type="button" data-action="open-meeting" data-meeting-id="${meeting.id}">Open meeting</button>
        </header>
        ${groupResults.map((result) => resultRowMarkup(result, "meeting")).join("")}
      </section>`).join("")}`;
}

function searchResultsListMarkup(results) {
  if (!results.length) return emptySearchMarkup();
  return `
    <div class="section-heading"><h2>${results.length} results</h2><span>Claims first</span></div>
    <div class="result-list">${results.map((result) => resultRowMarkup(result, "retrieval")).join("")}</div>`;
}

function resultRowMarkup(result) {
  if (result.type === "claim") {
    return `
      <button class="result-row" type="button" data-action="open-claim" data-claim-id="${result.claim.id}">
        <span class="claim-kind ${result.claim.kind}">${escapeHtml(kindLabel(result.claim.kind))}</span>
        <span><span class="row-title">${escapeHtml(result.claim.text)}</span><span class="row-meta">${escapeHtml(result.meeting.title)} · ${escapeHtml(evidenceLabel(result.claim))}</span></span>
        <span class="row-action">Open claim</span>
      </button>`;
  }
  if (result.type === "transcript") {
    return `
      <button class="result-row" type="button" data-action="open-turn" data-meeting-id="${result.meeting.id}" data-turn-id="${result.turn.id}">
        <span class="claim-kind">Transcript</span>
        <span><span class="row-title">“${escapeHtml(result.turn.text)}”</span><span class="row-meta">${escapeHtml(result.meeting.title)} · canonical words</span></span>
        <span class="row-action">Open words</span>
      </button>`;
  }
  return `
    <button class="result-row" type="button" data-action="open-meeting" data-meeting-id="${result.meeting.id}">
      <span class="claim-kind">Meeting</span>
      <span><span class="row-title">${escapeHtml(result.meeting.title)}</span><span class="row-meta">${escapeHtml(result.meeting.date)} · ${escapeHtml(result.meeting.folder)}</span></span>
      <span class="row-action">Open meeting</span>
    </button>`;
}

function emptySearchMarkup() {
  return `
    <section class="empty-state">
      <h2>No matching words were found.</h2>
      <p>This corpus has a withheld span in Estimate handoff. Not found does not mean never said.</p>
      <button class="text-button" type="button" data-action="open-meeting" data-meeting-id="m-02">Review the withheld span</button>
    </section>`;
}

function renderClaimDetail() {
  const found = findClaim(state.selectedClaimId);
  if (!found) {
    state.route = "home";
    render();
    return;
  }
  const content = claimDetailMarkup(found.meeting, found.claim);
  if (state.view === "retrieval") {
    const results = search(state.query);
    workspace.innerHTML = `
      <div class="workspace-grid retrieval-grid">
        <aside class="rail">
          <p class="kicker">Preserved search</p>
          ${searchFormMarkup(true)}
          ${searchResultsListMarkup(results)}
        </aside>
        <section class="content-pane">${content}</section>
      </div>`;
    return;
  }
  workspace.innerHTML = `
    <div class="workspace-grid">
      <aside class="rail">${detailRailMarkup(found.meeting)}</aside>
      <section class="content-pane">${content}</section>
    </div>`;
}

function detailRailMarkup(meeting) {
  const title = state.view === "meetings" ? "Meetings" : "Recorded promises";
  return `
    <p class="kicker">${escapeHtml(title)}</p>
    <h2 class="rail-title">${escapeHtml(meeting.title)}</h2>
    <p class="rail-copy">${escapeHtml(meeting.date)} · ${escapeHtml(meeting.folder)}</p>
    <button class="secondary-button" type="button" data-action="back-results">Back to ${state.query ? `“${escapeHtml(state.query)}”` : "Library"}</button>
    <div class="section-heading"><h3>Meeting claims</h3><span>${claimsFor(meeting).length}</span></div>
    ${claimsFor(meeting).map((claim) => `<button class="text-button" type="button" data-action="open-claim" data-claim-id="${claim.id}">${escapeHtml(kindLabel(claim.kind))}: ${escapeHtml(claim.text)}</button>`).join("")}`;
}

function claimDetailMarkup(meeting, claim) {
  const stale = noteState(meeting) === "stale";
  const supportType = supportTypeLabel(claim);
  const supportExplanation = claim.supportType === "inferred"
    ? "The note wording is an interpretation of those words, not a quote."
    : claim.supportType === "stated"
      ? "The note labels this as directly stated."
      : "The locator makes no stated-versus-inferred judgment.";
  return `
    <nav class="breadcrumb" aria-label="Breadcrumb">
      <button type="button" data-action="back-results">${state.query ? `Results for “${escapeHtml(state.query)}”` : "Library"}</button>
      <span aria-hidden="true">/</span>
      <span>${escapeHtml(meeting.title)}</span>
    </nav>
    <header class="detail-header">
      <div>
        <p class="kicker">${escapeHtml(kindLabel(claim.kind))}${supportType ? ` · ${escapeHtml(supportType)}` : ""} · ${escapeHtml(evidenceLabel(claim))}</p>
        <h1>${escapeHtml(claim.text)}</h1>
        <p class="detail-meta">From ${escapeHtml(meeting.title)} · ${escapeHtml(meeting.date)}</p>
      </div>
      <div class="detail-actions">
        ${claim.locator ? `<button class="primary-button" type="button" data-action="open-evidence" data-claim-id="${claim.id}">Open exact words</button>` : ""}
        <button class="secondary-button" type="button" data-action="open-meeting" data-meeting-id="${meeting.id}">Open full meeting</button>
        <button class="text-button" type="button" data-action="copy-claim" data-claim-id="${claim.id}">Copy claim</button>
      </div>
    </header>
    ${coverageMarkup(meeting)}
    ${stale ? staleMarkup() : ""}
    ${claim.evidenceState === "located" ? `
      <section class="state-panel">
        <p class="label">${supportType ? `${escapeHtml(supportType)} · ` : ""}What “words located” means</p>
        <h2>The cited words occur in the transcript.</h2>
        <p>${escapeHtml(supportExplanation)} Location does not prove semantic support. Open the canonical words and decide.</p>
      </section>` : `
      <section class="failure-panel">
        <p class="label">Evidence gap</p>
        <h2>${escapeHtml(evidenceLabel(claim))}</h2>
        <p>${escapeHtml(claim.evidenceDetail)}</p>
      </section>`}
    <div class="section-heading"><h2>Other claims from this meeting</h2><span>Read order</span></div>
    ${claimsFor(meeting).filter((item) => item.id !== claim.id).slice(0, 3).map((item) => claimCardMarkup(meeting, item)).join("")}`;
}

function coverageMarkup(meeting) {
  if (meeting.id === "m-02") {
    const label = state.restored ? "Withheld turn restored" : "One withheld turn";
    const detail = state.restored
      ? "The canonical transcript changed. Note version 1 is history until a replacement is generated."
      : meeting.coverage;
    return `
      <section class="coverage-strip is-gap">
        <span class="coverage-mark" aria-hidden="true"></span>
        <div><strong>${escapeHtml(label)}</strong><span>${escapeHtml(detail)}</span></div>
        <button type="button" data-action="review-gap">${state.restored ? "Open restored turn" : "Review withheld turn"}</button>
      </section>`;
  }
  const audio = currentAudio(meeting);
  if (audio.state === "released") {
    return `
      <section class="coverage-strip">
        <span class="coverage-mark" aria-hidden="true"></span>
        <div><strong>Transcript evidence remains</strong><span>${escapeHtml(audio.detail)} Playback and re-transcription are unavailable.</span></div>
        <button type="button" data-action="open-meeting" data-meeting-id="${meeting.id}">Meeting details</button>
      </section>`;
  }
  return `
    <section class="coverage-strip">
      <span class="coverage-mark" aria-hidden="true"></span>
      <div><strong>Canonical transcript available</strong><span>${escapeHtml(audio.detail)}</span></div>
      <button type="button" data-action="open-meeting" data-meeting-id="${meeting.id}">Meeting details</button>
    </section>`;
}

function staleMarkup() {
  const recovering = state.recoveryState === "interrupted" || state.recoveryState === "resuming";
  const resuming = state.recoveryState === "resuming" || state.regenerating;
  return `
    <section class="stale-panel ${recovering ? "is-recovery" : ""}">
      <p class="label">${recovering ? "Recovered after a document reload" : "Stale note · version 1 is history"}</p>
      <h2>${recovering ? "Your transcript correction is safe. No replacement note was published." : "The corrected transcript has no current note yet."}</h2>
      <p>${recovering
        ? "The canonical transcript includes the restored turn. Note version 1 remains stale history, and the interrupted request can be retried without accepting a partial note."
        : "The prior note stays available as history but does not include the restored turn. Generate version 2 from the corrected canonical transcript."}</p>
      <div class="stale-actions">
        <button class="primary-button" type="button" data-action="regenerate-note" ${resuming ? "disabled" : ""}>${resuming ? "Regenerating…" : recovering ? "Resume note regeneration" : "Generate note version 2"}</button>
        ${recovering ? "" : `<button class="text-button prototype-action" type="button" data-action="preview-document-reload-interruption">Prototype: interrupt after request</button>`}
      </div>
      ${recovering
        ? `<p class="prototype-boundary">Synthetic recovery preview. The native app and product records are not exercised.</p>`
        : `<p class="prototype-boundary">Reviewer action writes a content-free request receipt, then reloads this document.</p>`}
    </section>`;
}

function revisionHistoryMarkup(meeting) {
  if (meeting.id !== "m-02" || !state.restored) return "";
  const currentNote = state.regenerated;
  const recovered = state.recoveryState === "recovered";
  return `
    <section class="revision-lineage" aria-label="Transcript and note history">
      <div class="section-heading">
        <h2>${state.recoveryState === "none" ? "Transcript and note history" : "What survived"}</h2>
        <span>${currentNote ? "Current note ready" : "Regeneration needed"}</span>
      </div>
      <div class="revision-row is-current">
        <div><strong>Transcript view 2</strong><span>Includes the restored withheld turn.</span></div>
        <span>Current</span>
      </div>
      <div class="revision-row is-history">
        <div><strong>Note version 1</strong><span>Built from transcript view 1 and excluded from current results.</span></div>
        <span>Stale history</span>
      </div>
      <div class="revision-row ${currentNote ? "is-current" : "is-missing"}">
        <div><strong>Note version 2</strong><span>${currentNote ? "Built from transcript view 2 and includes the restored promise." : "No partial replacement has product authority."}</span></div>
        <span>${currentNote ? "Current" : "Not published"}</span>
      </div>
      ${recovered ? `<p class="recovery-receipt"><strong>Recovery complete.</strong> One replacement note became current; no partial note was published.</p>` : ""}
    </section>`;
}

function claimCardMarkup(meeting, claim) {
  const supportType = supportTypeLabel(claim);
  return `
    <article class="claim-card">
      <div class="claim-card-meta">
        <span class="claim-kind ${claim.kind}">${escapeHtml(kindLabel(claim.kind))}</span>
        <span class="evidence-state ${claim.evidenceState}">${escapeHtml(evidenceLabel(claim))}</span>
        ${supportType ? `<span class="support-state ${claim.supportType}">${escapeHtml(supportType)}</span>` : ""}
        ${claim.owner ? `<span class="owner-state">Owner: ${escapeHtml(claim.owner)}</span>` : ""}
      </div>
      <p>${escapeHtml(claim.text)}</p>
      <div class="claim-card-footer">
        <button class="text-button" type="button" data-action="open-claim" data-claim-id="${claim.id}">Open claim</button>
        ${claim.locator ? `<button class="text-button" type="button" data-action="open-evidence" data-claim-id="${claim.id}">Show exact words</button>` : ""}
      </div>
    </article>`;
}

function meetingNoteMarkup(meeting, claims) {
  if (!claims.length) {
    return `<section class="empty-state"><h2>No note was created.</h2><p>The transcript remains the durable artifact.</p></section>`;
  }
  if (meeting.noteLayout !== "survey-core") {
    return claims.map((claim) => claimCardMarkup(meeting, claim)).join("");
  }
  const sections = [
    { id: "decisions", title: "Decisions", kinds: ["decision"] },
    { id: "actions", title: "Actions & owners", kinds: ["commitment"] },
    { id: "questions", title: "Open questions", kinds: ["question"] },
    { id: "risks", title: "Risks & blockers", kinds: ["risk"] },
    { id: "needs", title: "Customer needs", kinds: ["customer_need"] }
  ];
  return `
    <p class="note-boundary-line"><strong>Synthetic content review.</strong> Hierarchy and evidence behavior only; automatic extraction and usefulness have not been reviewed.</p>
    <section class="note-summary-card" aria-labelledby="note-summary-title">
      <span class="label">Concise summary · derived</span>
      <h2 id="note-summary-title">Summary</h2>
      <p>${escapeHtml(meeting.summary)}</p>
    </section>
    <div class="note-sections">
      ${sections.map((section) => {
        const sectionClaims = claims.filter((claim) => section.kinds.includes(claim.kind));
        return `
          <section class="note-section" aria-labelledby="note-${section.id}">
            <div class="section-heading">
              <h2 id="note-${section.id}">${escapeHtml(section.title)}</h2>
              <span>${sectionClaims.length}</span>
            </div>
            ${sectionClaims.map((claim) => claimCardMarkup(meeting, claim)).join("")}
          </section>`;
      }).join("")}
    </div>`;
}

function renderMeetingDetail() {
  const meeting = findMeeting(state.selectedMeetingId);
  if (!meeting) {
    state.route = "home";
    render();
    return;
  }
  workspace.innerHTML = `
    <div class="workspace-grid">
      <aside class="rail">
        <p class="kicker">Meeting source</p>
        <h2 class="rail-title">${escapeHtml(meeting.title)}</h2>
        <p class="rail-copy">${escapeHtml(meeting.date)} · ${escapeHtml(meeting.folder)}</p>
        <button class="secondary-button" type="button" data-action="back-results">Back to ${state.query ? `“${escapeHtml(state.query)}”` : "Library"}</button>
        ${retentionFactsMarkup()}
        ${meeting.reviewPrompt ? `<section class="rail-review"><span class="label">Review question</span><p>${escapeHtml(meeting.reviewPrompt)}</p></section>` : ""}
      </aside>
      <section class="content-pane">
        ${meetingDetailMarkup(meeting)}
      </section>
    </div>`;
}

function meetingDetailMarkup(meeting) {
  if (meeting.id === "m-03" && !state.partnerRecovered) return partnerFailureMarkup(meeting);
  const stale = noteState(meeting) === "stale";
  const claims = stale ? meeting.claims : claimsFor(meeting);
  const transcriptLabel = meeting.id === "m-03" && state.partnerRecovered
    ? "Recovered transcript"
    : meeting.id === "m-02" && state.restored
      ? "Corrected transcript"
      : meeting.transcriptStatus === "partial"
        ? "Partial transcript"
        : "Canonical transcript";
  return `
    <header class="detail-header">
      <div>
        <p class="kicker">${escapeHtml(transcriptLabel)} · ${stale ? "no current note" : "note ready"}</p>
        <h1>${escapeHtml(meeting.title)}</h1>
        <p class="detail-meta">${escapeHtml(meeting.date)} · ${escapeHtml(meeting.folder)}</p>
      </div>
      <div class="detail-actions">
        <button class="primary-button" type="button" data-action="open-transcript" data-meeting-id="${meeting.id}">Open transcript</button>
      </div>
    </header>
    ${coverageMarkup(meeting)}
    ${stale ? staleMarkup() : ""}
    ${revisionHistoryMarkup(meeting)}
    <div class="section-heading"><h2>${stale ? "Prior note" : "Meeting note"}</h2><span>Version ${meeting.id === "m-02" && state.regenerated ? "2" : "1"} · ${stale ? "history · " : ""}${claims.length} claims</span></div>
    <div class="${stale ? "historical-note" : "current-note"}">${meetingNoteMarkup(meeting, claims)}</div>
    ${retentionActionMarkup(meeting)}`;
}

function partnerFailureMarkup(meeting) {
  return `
    <header class="detail-header">
      <div>
        <p class="kicker">Transcript unavailable</p>
        <h1>${escapeHtml(meeting.title)}</h1>
        <p class="detail-meta">${escapeHtml(meeting.date)} · ${escapeHtml(meeting.folder)}</p>
      </div>
    </header>
    <section class="failure-panel" aria-busy="${state.partnerRecovering}">
      <p class="label">Local processing needs attention</p>
      <h2>${state.partnerRecovering ? "Retrying transcription…" : escapeHtml(meeting.failure.text)}</h2>
      <p>${state.partnerRecovering ? "The recording remains unchanged while the local worker starts again." : "No note is shown while its canonical transcript is missing."}</p>
      <code class="diagnostic">${escapeHtml(meeting.failure.diagnostic)}</code>
      <button class="primary-button" type="button" data-action="retry-transcript" ${state.partnerRecovering ? "disabled" : ""}>${state.partnerRecovering ? "Retrying…" : "Retry transcription"}</button>
    </section>
    ${retentionActionMarkup(meeting)}`;
}

function retentionFactsMarkup() {
  const held = meetings.filter((meeting) => ["held", "expiring"].includes(currentAudio(meeting).state));
  const audioMegabytes = { "m-02": 18.4, "m-03": 9.2, "m-04": 6.3, "m-05": 12.7 };
  const bytes = held.reduce((total, meeting) => total + (audioMegabytes[meeting.id] ?? 0), 0);
  return `
    <div class="section-heading"><h3>Audio held</h3><span>${held.length}</span></div>
    <p class="rail-copy">${bytes.toFixed(1)} MB across this synthetic corpus. Transcript evidence is retained separately.</p>`;
}

function retentionActionMarkup(meeting) {
  const audio = currentAudio(meeting);
  if (audio.state === "released") {
    return `
      <section class="state-panel">
        <p class="label">Audio released</p>
        <h2>The note and transcript remain readable.</h2>
        <p>Playback, re-transcription, and audio review are no longer available for this meeting.</p>
      </section>`;
  }
  if (meeting.id !== "m-04") return "";
  return `
    <section class="state-panel">
      <p class="label">Recording retention</p>
      <h2>${escapeHtml(audio.detail)}</h2>
      <p>Releasing audio keeps the meeting, note, canonical transcript, and text evidence locators.</p>
      ${state.retentionConfirming ? `
        <div class="confirmation">
          <p><strong>Release this synthetic recording now?</strong> This prototype action changes only in-memory fixture state.</p>
          <div class="confirmation-actions">
            <button class="danger-button" type="button" data-action="confirm-release-audio">Release audio</button>
            <button class="secondary-button" type="button" data-action="cancel-release-audio">Cancel</button>
          </div>
        </div>` : `<button class="secondary-button" type="button" data-action="release-audio">Release audio now</button>`}
    </section>`;
}

function renderTranscript() {
  const meeting = findMeeting(state.selectedMeetingId);
  if (!meeting) {
    state.route = "home";
    render();
    return;
  }
  const selected = state.selectedClaimId ? findClaim(state.selectedClaimId) : null;
  const claim = selected?.meeting.id === meeting.id ? selected.claim : null;
  const transcriptLocator = claim?.locator || state.selectedTranscriptLocator;
  workspace.innerHTML = `
    <div class="transcript-layout">
      <section class="transcript-reader">
        <nav class="breadcrumb" aria-label="Breadcrumb">
          <button type="button" data-action="back-from-transcript">${claim ? "Claim" : "Meeting"}</button>
          <span aria-hidden="true">/</span>
          <span>Canonical transcript</span>
        </nav>
        <p class="kicker">Transcript · ${meeting.id === "m-02" && state.restored ? "corrected canonical words" : meeting.transcriptStatus === "partial" ? "partial capture" : "canonical words"}</p>
        <h1>${escapeHtml(meeting.title)}</h1>
        <p class="transcript-meta">${escapeHtml(meeting.date)} · timestamps are synthetic · one canonical transcript</p>
        ${meeting.id === "m-02" ? coverageMarkup(meeting) : ""}
        ${noteState(meeting) === "stale" ? staleMarkup() : ""}
        <div class="turn-list">${turnsMarkup(meeting, transcriptLocator)}</div>
      </section>
      <aside class="source-rail">
        <p class="kicker">Source context</p>
        <h2>${claim ? escapeHtml(kindLabel(claim.kind)) : transcriptLocator ? "Transcript match" : "Meeting transcript"}</h2>
        <p>${claim ? escapeHtml(claim.text) : transcriptLocator ? `“${escapeHtml(transcriptLocator.quote)}”` : "Read the canonical words in order."}</p>
        ${transcriptLocator ? `<div class="source-fact"><strong>${claim ? escapeHtml(evidenceLabel(claim)) : "Exact words found"}</strong><span>Text locator: ${escapeHtml(`${transcriptLocator.turnId} [${transcriptLocator.start}, ${transcriptLocator.end})`)}</span></div>` : ""}
        <div class="source-fact"><strong>${meeting.id === "m-02" ? (state.restored ? "Withheld turn restored" : "One withheld turn") : "Transcript available"}</strong><span>${meeting.id === "m-02" ? "Gap at 00:01:08–00:01:26" : escapeHtml(currentAudio(meeting).detail)}</span></div>
        <div class="source-fact"><strong>Note ${noteState(meeting) === "stale" ? "needs regeneration" : "is current"}</strong><span>${meeting.id === "m-02" && state.regenerated ? "Version 2 includes the restored promise." : meeting.id === "m-02" && state.restored ? "Version 1 remains history; no partial replacement is current." : "Claims remain separate from canonical words."}</span></div>
        ${meeting.id === "m-02" && !state.restored ? `<button class="primary-button" type="button" data-action="review-gap">Review withheld turn</button>` : ""}
        <button class="secondary-button" type="button" data-action="back-results">Back to ${state.query ? `“${escapeHtml(state.query)}” results` : "Library"}</button>
      </aside>
    </div>`;
  if (state.reviewingGap || state.restored) {
    window.requestAnimationFrame(() => document.querySelector("#withheld-turn")?.scrollIntoView({ block: "center" }));
  } else if (transcriptLocator) {
    window.requestAnimationFrame(() => document.querySelector(".turn.is-locator")?.scrollIntoView({ block: "center" }));
  }
}

function turnsMarkup(meeting, transcriptLocator) {
  return turnsFor(meeting).map((turn) => {
    if (turn.type === "gap") return gapMarkup(meeting);
    if (turn.withheld && !state.restored) return "";
    const locator = transcriptLocator?.turnId === turn.id ? transcriptLocator : null;
    return turnMarkup(turn, locator, turn.withheld && state.restored);
  }).join("");
}

function turnMarkup(turn, locator, restored = false) {
  const text = locator ? highlightedText(turn.text, locator) : escapeHtml(turn.text);
  return `
    <article class="turn ${locator ? "is-locator" : ""}">
      <div class="turn-meta"><strong>${escapeHtml(turn.speaker)}</strong><span>${escapeHtml(turn.at)}</span>${restored ? "<span>Restored</span>" : ""}</div>
      <p class="turn-text">${text}</p>
    </article>`;
}

function highlightedText(text, locator) {
  const start = Math.max(0, Math.min(locator.start, text.length));
  const end = Math.max(start, Math.min(locator.end, text.length));
  return `${escapeHtml(text.slice(0, start))}<mark>${escapeHtml(text.slice(start, end))}</mark>${escapeHtml(text.slice(end))}`;
}

function gapMarkup(meeting) {
  if (meeting.id !== "m-02") return "";
  const hidden = meeting.turns.find((turn) => turn.id === "m02-t04");
  const showReviewText = state.reviewingGap && !state.restored;
  return `
    <section class="gap-turn ${state.restored ? "is-restored" : ""}" id="withheld-turn">
      <strong>${state.restored ? "Restored to the canonical transcript" : "18 seconds withheld by the voice gate"}</strong>
      <span>00:01:08–00:01:26 · this is different from “nothing was said”</span>
      ${showReviewText ? `<p>${escapeHtml(hidden.text)}</p>` : ""}
      ${!showReviewText && !state.restored ? `<button class="secondary-button" type="button" data-action="review-gap">Review withheld turn</button>` : ""}
      ${state.reviewingGap && !state.restored ? `<button class="primary-button" type="button" data-action="restore-turn">Restore to transcript</button>` : ""}
    </section>`;
}

function openClaim(claimId) {
  const found = findClaim(claimId);
  if (!found) return;
  state.selectedClaimId = claimId;
  state.selectedMeetingId = found.meeting.id;
  state.selectedTranscriptLocator = null;
  state.route = "claim";
  state.focusRequest = "heading";
  render();
}

function openMeeting(meetingId) {
  state.selectedMeetingId = meetingId;
  state.selectedClaimId = null;
  state.selectedTranscriptLocator = null;
  state.route = "meeting";
  state.focusRequest = "heading";
  render();
}

function openEvidence(claimId) {
  const found = findClaim(claimId);
  if (!found || !found.claim.locator) return;
  state.selectedClaimId = claimId;
  state.selectedMeetingId = found.meeting.id;
  state.selectedTranscriptLocator = null;
  state.reviewingGap = false;
  state.route = "transcript";
  state.focusRequest = "heading";
  render();
}

function openTranscriptTurn(meetingId, turnId) {
  const result = search(state.query).find((item) => item.type === "transcript" && item.meeting.id === meetingId && item.turn.id === turnId);
  if (!result) return;
  state.selectedMeetingId = meetingId;
  state.selectedClaimId = null;
  state.selectedTranscriptLocator = result.locator;
  state.route = "transcript";
  state.focusRequest = "heading";
  render();
}

function backToResults() {
  state.route = "home";
  state.selectedMeetingId = null;
  state.selectedClaimId = null;
  state.selectedTranscriptLocator = null;
  state.reviewingGap = false;
  state.focusRequest = state.query ? "results" : "heading";
  render();
}

function reviewGap() {
  state.selectedMeetingId = "m-02";
  if (!state.selectedClaimId) state.selectedClaimId = "m02-c01";
  state.selectedTranscriptLocator = null;
  state.reviewingGap = !state.restored;
  state.route = "transcript";
  state.focusRequest = "gap";
  render();
}

function restoreTurn() {
  state.restored = true;
  state.regenerated = false;
  state.recoveryState = "none";
  state.reviewingGap = false;
  state.selectedClaimId = null;
  state.selectedTranscriptLocator = null;
  showToast("Turn restored. Note version 1 is now stale.");
  state.focusRequest = "gap";
  render();
}

function previewDocumentReloadInterruption() {
  if (!state.restored || state.regenerated || state.regenerating) return;
  const fixture = {
    schema: "walking-skeleton-recovery/1",
    scenario: "note-regeneration-request-only",
    meetingId: "m-02",
    transcriptView: 2,
    priorNoteVersion: 1
  };
  try {
    window.sessionStorage.setItem(recoveryFixtureKey, JSON.stringify(fixture));
    window.location.reload();
  } catch {
    showToast("This browser blocked the synthetic recovery receipt; the prototype was not reloaded.");
  }
}

function regenerateNote() {
  if (!state.restored || state.regenerating) return;
  const resumingRecovery = state.recoveryState === "interrupted";
  state.regenerating = true;
  if (resumingRecovery) state.recoveryState = "resuming";
  state.focusRequest = "status";
  render();
  transitionTimer = window.setTimeout(() => {
    state.regenerating = false;
    state.regenerated = true;
    if (state.recoveryState === "resuming") {
      state.recoveryState = "recovered";
      clearRecoveryFixture();
    }
    showToast(`${resumingRecovery ? "Recovery complete. " : ""}Note version 2 now includes the restored promise.`);
    state.focusRequest = "heading";
    render();
  }, 650);
}

async function copyText(text, message) {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.append(textarea);
    textarea.select();
    document.execCommand("copy");
    textarea.remove();
  }
  showToast(message);
}

function nextMissingSetupStep() {
  if (!state.setupPermissions.microphone || !state.setupPermissions.systemAudio) return "permissions";
  if (!Number.isInteger(state.retentionPeriodDays)) return "retention";
  if (state.voiceProfileStatus !== "valid") return "profile";
  return "overview";
}

function openSettings(step = "overview") {
  if (state.route !== "settings") state.settingsReturnRoute = state.route;
  state.route = "settings";
  state.setupStep = state.enrollmentRecording ? state.setupStep : step;
  state.profileResetConfirming = false;
  if (step === "retention") state.retentionDraftDays = state.retentionPeriodDays;
  state.focusRequest = "heading";
  render();
}

function closeSettings() {
  if (state.route !== "settings" || state.enrollmentRecording) return;
  state.route = state.settingsReturnRoute === "settings" ? "home" : state.settingsReturnRoute;
  state.setupStep = "overview";
  state.profileResetConfirming = false;
  state.retentionDraftDays = null;
  state.focusRequest = "heading";
  render();
}

function previewFirstRun() {
  if (state.capturePhase !== "idle" || state.enrollmentRecording) return;
  clearEnrollmentState();
  state.setupPermissions = { microphone: false, systemAudio: false };
  state.retentionPeriodDays = null;
  state.retentionDraftDays = null;
  state.voiceProfileStatus = "missing";
  state.profileResetConfirming = false;
  state.setupStep = "permissions";
  state.consentConfirmed = false;
  state.focusRequest = "heading";
  render();
}

function grantSetupPermission(permission) {
  if (state.route !== "settings" || state.setupStep !== "permissions") return;
  if (!Object.hasOwn(state.setupPermissions, permission)) return;
  state.setupPermissions[permission] = true;
  render();
}

function continueToRetention() {
  if (!state.setupPermissions.microphone || !state.setupPermissions.systemAudio) return;
  state.setupStep = "retention";
  state.retentionDraftDays = state.retentionPeriodDays;
  state.focusRequest = "heading";
  render();
}

function saveRetention() {
  if (!Number.isInteger(state.retentionDraftDays)) return;
  state.retentionPeriodDays = state.retentionDraftDays;
  state.consentConfirmed = false;
  if (state.setupStep === "retention-change") {
    state.setupStep = "overview";
    showToast(`Meeting audio will auto-delete after ${state.retentionPeriodDays} days in this fixture.`);
  } else {
    state.setupStep = "profile";
  }
  state.retentionDraftDays = null;
  state.focusRequest = "heading";
  render();
}

function requestProfileReset() {
  if (state.capturePhase !== "idle" || state.enrollmentRecording || state.voiceProfileStatus !== "valid") return;
  state.profileResetConfirming = true;
  state.focusRequest = "status";
  render();
}

function confirmProfileReset() {
  if (!state.profileResetConfirming || state.capturePhase !== "idle" || state.enrollmentRecording) return;
  clearEnrollmentState();
  state.profileResetConfirming = false;
  state.voiceProfileStatus = "missing";
  state.consentConfirmed = false;
  state.setupStep = "profile";
  showToast("Synthetic voice profile reset. Meetings and retention remain.");
  state.focusRequest = "heading";
  render();
}

function loadReturningProfileFixture() {
  if (state.capturePhase !== "idle" || state.enrollmentRecording) return;
  clearEnrollmentState();
  state.voiceProfileStatus = "valid";
  state.setupStep = "overview";
  showToast("Separate returning-profile fixture loaded. No profile was built here.");
  state.focusRequest = "heading";
  render();
}

function clearEnrollmentState() {
  window.clearTimeout(transitionTimer);
  state.enrollmentRecording = false;
  state.enrollmentRecordingKind = null;
  state.enrollmentNegativeSource = null;
  state.enrollmentPolicy = null;
  state.enrollmentBuildPhase = null;
  state.enrollmentDiscardConfirming = false;
}

function startEnrollment() {
  if (state.capturePhase !== "idle" || state.voiceProfileStatus === "valid") return;
  clearEnrollmentState();
  state.setupStep = "enrollment-one";
  state.focusRequest = "heading";
  render();
}

function startEnrollmentRecording(kind) {
  const allowed = {
    "operator-one": "enrollment-one",
    "operator-two": "enrollment-two",
    "other-voice": "enrollment-negative"
  };
  if (state.capturePhase !== "idle" || state.setupStep !== allowed[kind]) return;
  if (kind === "other-voice" && !state.enrollmentNegativeSource) return;
  state.enrollmentRecording = true;
  state.enrollmentRecordingKind = kind;
  state.enrollmentDiscardConfirming = false;
  state.focusRequest = "heading";
  render();
}

function stopEnrollmentRecording() {
  if (!state.enrollmentRecording) return;
  const kind = state.enrollmentRecordingKind;
  state.enrollmentRecording = false;
  state.enrollmentRecordingKind = null;
  if (kind === "operator-one") {
    state.setupStep = "enrollment-wait";
    showToast("First fixture sitting saved; dedicated source audio is represented as deleted.");
  } else if (kind === "operator-two") {
    state.setupStep = "enrollment-review";
    showToast("Second fixture sitting saved; dedicated source audio is represented as deleted.");
  } else if (kind === "other-voice") {
    state.setupStep = "enrollment-policy";
    showToast("Comparison scores saved; dedicated source audio is represented as deleted.");
  }
  state.focusRequest = "heading";
  render();
}

function requestEnrollmentDiscard() {
  if (!state.setupStep.startsWith("enrollment-")) return;
  state.enrollmentRecording = false;
  state.enrollmentRecordingKind = null;
  state.enrollmentDiscardConfirming = true;
  state.focusRequest = "status";
  render();
}

function confirmEnrollmentDiscard() {
  if (!state.enrollmentDiscardConfirming) return;
  clearEnrollmentState();
  state.voiceProfileStatus = "missing";
  state.setupStep = "profile";
  state.consentConfirmed = false;
  showToast("Synthetic enrollment discarded. Meetings and retention remain.");
  state.focusRequest = "heading";
  render();
}

function buildEnrollmentProfile() {
  if (state.setupStep !== "enrollment-policy" || !state.enrollmentPolicy) return;
  state.setupStep = "enrollment-build";
  state.enrollmentBuildPhase = "building";
  state.focusRequest = "heading";
  render();
  transitionTimer = window.setTimeout(() => {
    state.enrollmentBuildPhase = "persisting";
    render();
    transitionTimer = window.setTimeout(() => {
      state.voiceProfileStatus = "valid";
      state.enrollmentBuildPhase = null;
      state.setupStep = "overview";
      showToast("Synthetic owner-only profile saved. This Mac is ready to record.");
      state.focusRequest = "heading";
      render();
    }, 450);
  }, 450);
}

function showCapture() {
  if (state.enrollmentRecording) {
    openSettings(state.setupStep);
    return;
  }
  if (state.recoveryState === "interrupted" || state.recoveryState === "resuming") {
    openMeeting("m-02");
    state.focusRequest = "status";
    render();
    showToast("Finish the recovered note regeneration before starting another meeting.");
    return;
  }
  if (state.capturePhase === "ready") {
    openCapturedMeeting();
    return;
  }
  if (state.capturePhase === "idle") {
    if (!capturePrerequisitesReady()) {
      openSettings(nextMissingSetupStep());
      return;
    }
    state.capturePhase = "consent";
    state.consentConfirmed = false;
    state.captureOutputMeetingId = null;
  }
  state.captureHudHidden = false;
  state.focusRequest = "capture";
  render();
}

function beginCapture() {
  if (state.capturePhase !== "consent" || !state.consentConfirmed) return;
  state.capturePhase = "recording";
  state.captureDegraded = false;
  state.captureRecovering = false;
  state.captureHudHidden = false;
  state.focusRequest = "capture";
  showToast("Synthetic recording started. Both channels are healthy.");
  render();
}

function cancelCapture() {
  if (state.capturePhase !== "consent") return;
  state.capturePhase = "idle";
  state.consentConfirmed = false;
  state.captureHudHidden = false;
  state.focusRequest = "heading";
  render();
}

function previewDegradedCapture() {
  if (state.capturePhase !== "recording") return;
  state.captureDegraded = true;
  state.captureRecovering = false;
  state.focusRequest = "capture";
  render();
}

function recoverSystemAudio() {
  if (state.capturePhase !== "recording" || !state.captureDegraded || state.captureRecovering) return;
  state.captureRecovering = true;
  render();
  transitionTimer = window.setTimeout(() => {
    state.captureRecovering = false;
    state.captureDegraded = false;
    showToast("System audio returned. The earlier interruption remains in capture history.");
    state.focusRequest = "capture";
    render();
  }, 500);
}

function stopCapture() {
  if (state.capturePhase !== "recording") return;
  window.clearTimeout(transitionTimer);
  state.captureOutputMeetingId = state.captureDegraded ? "m-02" : "m-05";
  state.capturePhase = "transcribing";
  state.captureDegraded = false;
  state.captureRecovering = false;
  state.consentConfirmed = false;
  state.captureHudHidden = false;
  state.focusRequest = "capture";
  render();
  captureTimer = window.setTimeout(() => {
    state.capturePhase = "ready";
    showToast(state.captureOutputMeetingId === "m-02" ? "Transcript ready with one known gap." : "Transcript and synthetic note are ready.");
    state.focusRequest = "capture";
    render();
  }, 900);
}

function openCapturedMeeting() {
  const outputMeetingId = state.captureOutputMeetingId || "m-05";
  state.capturePhase = "idle";
  state.captureDegraded = false;
  state.captureOutputMeetingId = null;
  state.captureHudHidden = false;
  openMeeting(outputMeetingId);
}

function hideCaptureHud() {
  if (state.capturePhase === "idle" || state.capturePhase === "consent") return;
  state.captureHudHidden = true;
  state.focusRequest = "heading";
  render();
}

document.querySelector(".direction-tabs").addEventListener("keydown", (event) => {
  if (!['ArrowLeft', 'ArrowRight'].includes(event.key)) return;
  const order = ["meetings", "commitments", "retrieval"];
  const current = order.indexOf(state.defaultDirection);
  const delta = event.key === "ArrowRight" ? 1 : -1;
  const next = order[(current + delta + order.length) % order.length];
  setDirection(next);
  document.querySelector(`[data-direction="${next}"]`)?.focus();
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && state.capturePhase === "consent") cancelCapture();
  if (event.key === "Escape" && state.profileResetConfirming) {
    state.profileResetConfirming = false;
    state.focusRequest = "heading";
    render();
  }
  if (event.key === "Escape" && state.enrollmentDiscardConfirming) {
    state.enrollmentDiscardConfirming = false;
    state.focusRequest = "heading";
    render();
  }
});

document.addEventListener("submit", (event) => {
  if (event.target.id !== "search-form") return;
  event.preventDefault();
  state.query = new FormData(event.target).get("query").trim();
  state.folderFilter = null;
  state.route = "home";
  state.selectedMeetingId = null;
  state.selectedClaimId = null;
  state.selectedTranscriptLocator = null;
  state.focusRequest = "results";
  render();
});

document.addEventListener("change", (event) => {
  if (event.target.id === "capture-consent") {
    state.consentConfirmed = event.target.checked;
    const startButton = document.querySelector("[data-action=begin-capture]");
    if (startButton) startButton.disabled = !state.consentConfirmed;
    return;
  }
  if (event.target.name === "retention-period") {
    state.retentionDraftDays = Number(event.target.value);
    const saveButton = document.querySelector("[data-action=save-retention]");
    if (saveButton) saveButton.disabled = false;
    return;
  }
  if (event.target.name === "negative-source") {
    state.enrollmentNegativeSource = event.target.value;
    const startButton = document.querySelector("[data-action=start-enrollment-recording]");
    if (startButton) startButton.disabled = false;
    return;
  }
  if (event.target.name === "voice-policy") {
    state.enrollmentPolicy = event.target.value;
    const buildButton = document.querySelector("[data-action=build-enrollment-profile]");
    if (buildButton) buildButton.disabled = false;
  }
});

document.addEventListener("click", (event) => {
  const direction = event.target.closest("[data-direction]")?.dataset.direction;
  if (direction) {
    setDirection(direction);
    return;
  }
  const view = event.target.closest("[data-view]")?.dataset.view;
  if (view) {
    switchView(view);
    return;
  }
  const button = event.target.closest("[data-action]");
  if (!button) return;
  const action = button.dataset.action;
  if (action === "open-settings") openSettings(state.enrollmentRecording ? state.setupStep : "overview");
  if (action === "close-settings") closeSettings();
  if (action === "preview-first-run") previewFirstRun();
  if (action === "grant-setup-permission") grantSetupPermission(button.dataset.permission);
  if (action === "continue-to-retention") continueToRetention();
  if (action === "back-to-permissions") {
    state.setupStep = "permissions";
    state.retentionDraftDays = null;
    state.focusRequest = "heading";
    render();
  }
  if (action === "change-retention") {
    if (state.capturePhase !== "idle") return;
    state.setupStep = "retention-change";
    state.retentionDraftDays = state.retentionPeriodDays;
    state.focusRequest = "heading";
    render();
  }
  if (action === "save-retention") saveRetention();
  if (action === "cancel-retention-change") {
    state.setupStep = "overview";
    state.retentionDraftDays = null;
    state.focusRequest = "heading";
    render();
  }
  if (action === "request-profile-reset") requestProfileReset();
  if (action === "cancel-profile-reset") {
    state.profileResetConfirming = false;
    state.focusRequest = "heading";
    render();
  }
  if (action === "confirm-profile-reset") confirmProfileReset();
  if (action === "review-profile-needed") {
    state.setupStep = "profile";
    state.focusRequest = "heading";
    render();
  }
  if (action === "load-returning-profile-fixture") loadReturningProfileFixture();
  if (action === "start-enrollment") startEnrollment();
  if (action === "start-enrollment-recording") startEnrollmentRecording(button.dataset.kind);
  if (action === "stop-enrollment-recording") stopEnrollmentRecording();
  if (action === "load-later-sitting-fixture") {
    state.setupStep = "enrollment-two";
    state.focusRequest = "heading";
    render();
  }
  if (action === "continue-to-negative-sample") {
    state.setupStep = "enrollment-negative";
    state.focusRequest = "heading";
    render();
  }
  if (action === "request-enrollment-discard") requestEnrollmentDiscard();
  if (action === "cancel-enrollment-discard") {
    state.enrollmentDiscardConfirming = false;
    state.focusRequest = "heading";
    render();
  }
  if (action === "confirm-enrollment-discard") confirmEnrollmentDiscard();
  if (action === "build-enrollment-profile") buildEnrollmentProfile();
  if (action === "show-capture") showCapture();
  if (action === "begin-capture") beginCapture();
  if (action === "cancel-capture") cancelCapture();
  if (action === "preview-degraded") previewDegradedCapture();
  if (action === "recover-system-audio") recoverSystemAudio();
  if (action === "stop-capture") stopCapture();
  if (action === "open-captured-meeting") openCapturedMeeting();
  if (action === "hide-capture-hud") hideCaptureHud();
  if (action === "open-claim") openClaim(button.dataset.claimId);
  if (action === "open-meeting") openMeeting(button.dataset.meetingId);
  if (action === "open-evidence") openEvidence(button.dataset.claimId);
  if (action === "open-transcript") {
    state.selectedMeetingId = button.dataset.meetingId;
    state.selectedTranscriptLocator = null;
    state.route = "transcript";
    state.focusRequest = "heading";
    render();
  }
  if (action === "open-turn") {
    openTranscriptTurn(button.dataset.meetingId, button.dataset.turnId);
  }
  if (action === "back-results") backToResults();
  if (action === "back-from-transcript") {
    state.route = state.selectedClaimId ? "claim" : "meeting";
    state.focusRequest = "heading";
    render();
  }
  if (action === "review-gap") reviewGap();
  if (action === "restore-turn") restoreTurn();
  if (action === "preview-document-reload-interruption") previewDocumentReloadInterruption();
  if (action === "regenerate-note") regenerateNote();
  if (action === "claim-filter") {
    state.claimFilter = button.dataset.filter;
    state.focusRequest = "results";
    render();
  }
  if (action === "folder-filter") {
    state.query = button.dataset.folder;
    state.folderFilter = button.dataset.folder;
    state.focusRequest = "results";
    render();
  }
  if (action === "clear-query") {
    state.query = "";
    state.folderFilter = null;
    state.route = "home";
    state.focusRequest = "heading";
    render();
  }
  if (action === "copy-claim") {
    const found = findClaim(button.dataset.claimId);
    if (found) copyText(found.claim.text, "Claim copied. No meeting content left the browser.");
  }
  if (action === "copy-promises") {
    const promises = allClaims().filter(({ claim }) => claim.kind === "commitment").map(({ meeting, claim }) => `- ${claim.text} — ${meeting.title}`).join("\n");
    copyText(promises, "Recorded promises copied as plain text.");
  }
  if (action === "retry-transcript") {
    state.partnerRecovering = true;
    state.focusRequest = "status";
    render();
    transitionTimer = window.setTimeout(() => {
      state.partnerRecovering = false;
      state.partnerRecovered = true;
      showToast("Transcript recovered. One located promise is now available.");
      state.focusRequest = "heading";
      render();
    }, 600);
  }
  if (action === "release-audio") {
    state.retentionConfirming = true;
    state.focusRequest = "status";
    render();
  }
  if (action === "cancel-release-audio") {
    state.retentionConfirming = false;
    state.focusRequest = "status";
    render();
  }
  if (action === "confirm-release-audio") {
    state.retentionConfirming = false;
    state.retentionReleased = true;
    showToast("Synthetic audio released. Note and transcript remain.");
    state.focusRequest = "status";
    render();
  }
});

document.querySelector("#reset-prototype").addEventListener("click", () => resetPrototype());

assertFixtureIntegrity();
startLoading();

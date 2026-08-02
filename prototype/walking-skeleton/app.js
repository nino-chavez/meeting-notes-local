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
const toast = document.querySelector("#toast");

let loadTimer;
let transitionTimer;
let toastTimer;
let state = freshState(readDirection());

function readDirection() {
  const direction = new URLSearchParams(window.location.search).get("direction");
  return Object.hasOwn(viewLabels, direction) ? direction : "retrieval";
}

function freshState(defaultDirection) {
  return {
    defaultDirection,
    view: defaultDirection,
    loading: true,
    route: "home",
    query: "",
    selectedMeetingId: null,
    selectedClaimId: null,
    selectedTranscriptLocator: null,
    claimFilter: defaultDirection === "commitments" ? "commitments" : "all",
    folderFilter: null,
    focusRequest: null,
    reviewingGap: false,
    restored: false,
    regenerating: false,
    regenerated: false,
    partnerRecovering: false,
    partnerRecovered: false,
    retentionConfirming: false,
    retentionReleased: false
  };
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
  return kind === "commitment" ? "Recorded promise" : kind[0].toUpperCase() + kind.slice(1);
}

function evidenceLabel(claim) {
  if (claim.evidenceState === "located") return "Words located";
  if (claim.evidenceState === "composed") return "Composed · words not found";
  if (claim.evidenceState === "untestable") return "Untestable · words too short to check";
  if (claim.evidenceState === "unquoted") return "Unquoted · no words supplied";
  throw new Error(`Unknown evidence state: ${claim.evidenceState}`);
}

function claimsFor(meeting) {
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
    if (button.dataset.view === state.view) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });
  workspace.setAttribute("aria-label", `${viewLabels[state.view]} view`);
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
    if (request === "results") target = workspace.querySelector(".section-heading h2, .empty-state h2");
    if (request === "gap") target = workspace.querySelector("#withheld-turn");
    if (request === "status") target = workspace.querySelector(".stale-panel h2, .failure-panel h2, .state-panel h2");
    if (!target) target = workspace.querySelector("h1");
    if (!target) target = workspace;
    target.setAttribute("tabindex", "-1");
    target.focus({ preventScroll: true });
  });
}

function render() {
  syncChrome();
  if (state.loading) {
    workspace.innerHTML = `
      <section class="loading-view" role="status" aria-busy="true">
        <span class="loading-mark" aria-hidden="true"></span>
        <h1>Opening your meeting memory.</h1>
        <p>Loading four synthetic meetings without touching Preview data.</p>
      </section>`;
    restoreRequestedFocus();
    return;
  }

  if (state.route === "transcript") {
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
  restoreRequestedFocus();
}

function searchFormMarkup(compact = false) {
  return `
    <form class="search-block" id="search-form">
      <label for="memory-search">Find exact words</label>
      <div class="search-row">
        <input id="memory-search" name="query" type="search" value="${escapeHtml(state.query)}" placeholder="Try “estimate range”" autocomplete="off" />
        <button type="submit">Find</button>
      </div>
      <p class="search-help">Searches claim text, canonical transcript words, meeting titles, and folders on this Mac.${compact ? "" : " Exact words stay linked to their source."}</p>
    </form>`;
}

function taskMarkup() {
  return `
    <section class="task-card" aria-label="Shared review task">
      <span class="label">Same task from every starting view</span>
      <p>Find the <strong>estimate range</strong> decision, open the exact words, then review the withheld turn and regenerate the note.</p>
    </section>`;
}

function meetingRowsMarkup(list = meetings) {
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
          <button class="filter-button" type="button" data-action="clear-query" aria-pressed="${state.folderFilter === null}"><span>All meetings</span><small>4</small></button>
          <button class="filter-button" type="button" aria-pressed="${state.folderFilter === "Operations"}" data-action="folder-filter" data-folder="Operations"><span>Operations</span><small>3</small></button>
          <button class="filter-button" type="button" aria-pressed="${state.folderFilter === "Partnerships"}" data-action="folder-filter" data-folder="Partnerships"><span>Partnerships</span><small>1</small></button>
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
          <div class="section-heading"><h2>Recent meetings</h2><span>4 retained</span></div>
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
    <div class="claim-list">${claimRowsMarkup(allClaims().filter(({ claim }) => claim.kind === "decision" || claim.kind === "commitment").slice(0, 4).map(({ meeting, claim }) => ({ type: "claim", meeting, claim })))}</div>`;
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
      if (!turn.type && !turn.withheld && start >= 0) {
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
  return `
    <nav class="breadcrumb" aria-label="Breadcrumb">
      <button type="button" data-action="back-results">${state.query ? `Results for “${escapeHtml(state.query)}”` : "Library"}</button>
      <span aria-hidden="true">/</span>
      <span>${escapeHtml(meeting.title)}</span>
    </nav>
    <header class="detail-header">
      <div>
        <p class="kicker">${escapeHtml(kindLabel(claim.kind))} · ${escapeHtml(evidenceLabel(claim))}</p>
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
        <p class="label">What “words located” means</p>
        <h2>The cited words occur in the transcript.</h2>
        <p>This does not prove they support the note’s interpretation. Open the canonical words and decide.</p>
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
      ? "The canonical transcript changed. The note was marked stale until regeneration."
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
  return `
    <section class="stale-panel">
      <p class="label">Stale · transcript changed</p>
      <h2>The current note does not include the restored turn.</h2>
      <p>Keep note version 1 as history, then regenerate from the corrected canonical transcript.</p>
      <button class="primary-button" type="button" data-action="regenerate-note" ${state.regenerating ? "disabled" : ""}>${state.regenerating ? "Regenerating…" : "Regenerate note"}</button>
    </section>`;
}

function claimCardMarkup(meeting, claim) {
  return `
    <article class="claim-card">
      <span class="claim-kind ${claim.kind}">${escapeHtml(kindLabel(claim.kind))} · <span class="evidence-state ${claim.evidenceState}">${escapeHtml(evidenceLabel(claim))}</span></span>
      <p>${escapeHtml(claim.text)}</p>
      <div class="claim-card-footer">
        <button class="text-button" type="button" data-action="open-claim" data-claim-id="${claim.id}">Open claim</button>
        ${claim.locator ? `<button class="text-button" type="button" data-action="open-evidence" data-claim-id="${claim.id}">Show exact words</button>` : ""}
      </div>
    </article>`;
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
      </aside>
      <section class="content-pane">
        ${meetingDetailMarkup(meeting)}
      </section>
    </div>`;
}

function meetingDetailMarkup(meeting) {
  if (meeting.id === "m-03" && !state.partnerRecovered) return partnerFailureMarkup(meeting);
  const claims = claimsFor(meeting);
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
        <p class="kicker">${escapeHtml(transcriptLabel)} · note ${noteState(meeting) === "stale" ? "stale" : "ready"}</p>
        <h1>${escapeHtml(meeting.title)}</h1>
        <p class="detail-meta">${escapeHtml(meeting.date)} · ${escapeHtml(meeting.folder)}</p>
      </div>
      <div class="detail-actions">
        <button class="primary-button" type="button" data-action="open-transcript" data-meeting-id="${meeting.id}">Open transcript</button>
      </div>
    </header>
    ${coverageMarkup(meeting)}
    ${noteState(meeting) === "stale" ? staleMarkup() : ""}
    <div class="section-heading"><h2>Meeting note</h2><span>Version ${meeting.id === "m-02" && state.regenerated ? "2" : "1"} · ${claims.length} claims</span></div>
    ${claims.length ? claims.map((claim) => claimCardMarkup(meeting, claim)).join("") : `<section class="empty-state"><h2>No note was created.</h2><p>The transcript remains the durable artifact.</p></section>`}
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
  const bytes = held.reduce((total, meeting) => total + (meeting.id === "m-02" ? 18.4 : meeting.id === "m-03" ? 9.2 : 6.3), 0);
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
        <div class="source-fact"><strong>Note ${noteState(meeting) === "stale" ? "needs regeneration" : "is current"}</strong><span>${meeting.id === "m-02" && state.regenerated ? "Version 2 includes the restored promise." : "Claims remain separate from canonical words."}</span></div>
        ${meeting.id === "m-02" && !state.restored ? `<button class="primary-button" type="button" data-action="review-gap">Review withheld turn</button>` : ""}
        ${meeting.id === "m-02" && state.restored && !state.regenerated ? `<button class="primary-button" type="button" data-action="regenerate-note" ${state.regenerating ? "disabled" : ""}>${state.regenerating ? "Regenerating…" : "Regenerate note"}</button>` : ""}
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
  state.reviewingGap = false;
  showToast("Turn restored. Note version 1 is now stale.");
  state.focusRequest = "gap";
  render();
}

function regenerateNote() {
  if (!state.restored || state.regenerating) return;
  state.regenerating = true;
  state.focusRequest = "status";
  render();
  transitionTimer = window.setTimeout(() => {
    state.regenerating = false;
    state.regenerated = true;
    showToast("Note version 2 now includes the restored promise.");
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

document.querySelector(".direction-tabs").addEventListener("keydown", (event) => {
  if (!['ArrowLeft', 'ArrowRight'].includes(event.key)) return;
  const order = ["meetings", "commitments", "retrieval"];
  const current = order.indexOf(state.defaultDirection);
  const delta = event.key === "ArrowRight" ? 1 : -1;
  const next = order[(current + delta + order.length) % order.length];
  setDirection(next);
  document.querySelector(`[data-direction="${next}"]`)?.focus();
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

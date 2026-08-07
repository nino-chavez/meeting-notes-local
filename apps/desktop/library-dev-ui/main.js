const invoke = window.__TAURI__?.core?.invoke;

const libraryState = document.querySelector("#library-state");
const libraryList = document.querySelector("#library-list");
const noteTitle = document.querySelector("#note-title");
const noteState = document.querySelector("#note-state");
const claimList = document.querySelector("#claim-list");
const query = document.querySelector("#search-query");
const searchButton = document.querySelector("#search-button");
const searchState = document.querySelector("#search-state");
const searchResults = document.querySelector("#search-results");
const evidenceState = document.querySelector("#evidence-state");
const evidenceText = document.querySelector("#evidence-text");

function message(target, text, state = "") {
  target.textContent = text;
  target.dataset.state = state;
}

function button(text, className = "") {
  const element = document.createElement("button");
  element.type = "button";
  element.textContent = text;
  if (className) element.className = className;
  return element;
}

async function openNote(meetingId, targetClaimOrdinal = null) {
  if (!invoke) return;
  const response = await invoke("library_dev_open_note", { meetingId });
  claimList.replaceChildren();
  evidenceText.hidden = true;
  evidenceText.textContent = "";
  message(evidenceState, "Choose “Show in transcript” from a claim.");
  noteTitle.textContent = response.state === "note" ? "Sanitized meeting note" : "Meeting needs attention";
  message(noteState, response.message, response.state);
  if (response.state !== "note") return;
  let targetClaim = null;
  for (const claim of response.claims) {
    const card = document.createElement("article");
    card.className = "claim";
    card.dataset.claimOrdinal = String(claim.ordinal);
    const meta = document.createElement("p");
    meta.className = "meta";
    meta.textContent = `${claim.claimType} · words located`;
    const text = document.createElement("p");
    text.textContent = claim.claim;
    const open = button("Show in transcript", "quiet");
    open.addEventListener("click", () => openEvidence(claim.handle));
    card.append(meta, text, open);
    claimList.append(card);
    if (claim.ordinal === targetClaimOrdinal) targetClaim = { card, handle: claim.handle };
  }
  if (targetClaim) {
    targetClaim.card.tabIndex = -1;
    targetClaim.card.focus();
    targetClaim.card.scrollIntoView({ block: "nearest" });
    await openEvidence(targetClaim.handle);
    message(noteState, "Opened the matching claim. Words located in the transcript; semantic support has not been reviewed.", "note");
  }
}

async function openEvidence(handle) {
  if (!invoke) return;
  const response = await invoke("library_dev_open_evidence", { handle, locatorOrdinal: 0 });
  const turn = Number.isInteger(response.sourceTurnIndex) ? ` · turn ${response.sourceTurnIndex + 1}` : "";
  message(evidenceState, response.text ? `Matched words from transcript${turn}` : response.message, response.state);
  evidenceText.hidden = !response.text;
  evidenceText.textContent = response.text || "";
}

function renderSearch(response) {
  searchResults.replaceChildren();
  message(searchState, response.message, response.state);
  for (const result of response.results) {
    const card = document.createElement("article");
    card.className = "search-result";
    const meta = document.createElement("p");
    meta.className = "meta";
    meta.textContent = result.kind === "withheld" ? "withheld" : result.kind;
    const text = document.createElement("p");
    text.textContent = result.kind === "withheld"
      ? "Matching transcript content is withheld from this read surface."
      : result.text || "No displayable text.";
    card.append(meta, text);
    if (result.kind === "claim" || result.kind === "meeting") {
      const open = button(result.kind === "claim" ? "Open claim" : "Open meeting", "quiet");
      open.addEventListener("click", () => openNote(result.meetingId, result.claimOrdinal));
      card.append(open);
    }
    searchResults.append(card);
  }
}

async function search() {
  if (!invoke) return;
  searchButton.disabled = true;
  try {
    const response = await invoke("library_dev_search", { query: query.value });
    renderSearch(response);
  } catch {
    message(searchState, "The synthetic search could not complete.", "empty");
  } finally {
    searchButton.disabled = false;
  }
}

async function load() {
  if (!invoke) {
    message(libraryState, "The local development bridge is unavailable.", "empty");
    return;
  }
  try {
    const snapshot = await invoke("library_dev_snapshot");
    libraryList.replaceChildren();
    message(libraryState, snapshot.message, snapshot.state);
    for (const row of snapshot.rows) {
      // Nullable since auto-titling: a meeting with no title and no transcript
      // sends none, and this surface's own fixture always has one.
      const open = button(row.label || "Synthetic meeting", "library-row");
      const detail = document.createElement("small");
      detail.textContent = "Synthetic meeting · transcript available";
      open.append(detail);
      open.addEventListener("click", () => openNote(row.meetingId));
      libraryList.append(open);
    }
    if (snapshot.rows.length > 0) await openNote(snapshot.rows[0].meetingId);
  } catch {
    message(libraryState, "The synthetic fixture could not open.", "empty");
  }
}

searchButton.addEventListener("click", search);
query.addEventListener("keydown", (event) => {
  if (event.key === "Enter") search();
});

load();

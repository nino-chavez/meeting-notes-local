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

async function openNote(meetingId) {
  if (!invoke) return;
  const response = await invoke("library_dev_open_note", { meetingId });
  claimList.replaceChildren();
  noteTitle.textContent = response.state === "note" ? "Sanitized library sample" : "Reader needs attention";
  message(noteState, response.message, response.state);
  if (response.state !== "note") return;
  for (const claim of response.claims) {
    const card = document.createElement("article");
    card.className = "claim";
    const meta = document.createElement("p");
    meta.className = "meta";
    meta.textContent = `${claim.claimType} · ${claim.evidenceState}`;
    const text = document.createElement("p");
    text.textContent = claim.claim;
    const open = button("Open exact evidence", "quiet");
    open.addEventListener("click", () => openEvidence(claim.handle));
    card.append(meta, text, open);
    claimList.append(card);
  }
}

async function openEvidence(handle) {
  if (!invoke) return;
  const response = await invoke("library_dev_open_evidence", { handle, locatorOrdinal: 0 });
  message(evidenceState, response.message, response.state);
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
      const open = button("Open note", "quiet");
      open.addEventListener("click", () => openNote(result.meetingId));
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
      const open = button(row.label, "library-row");
      const detail = document.createElement("small");
      detail.textContent = "Sanitized fixture · transcript available";
      open.append(detail);
      open.addEventListener("click", () => openNote(row.meetingId));
      libraryList.append(open);
    }
  } catch {
    message(libraryState, "The synthetic fixture could not open.", "empty");
  }
}

searchButton.addEventListener("click", search);
query.addEventListener("keydown", (event) => {
  if (event.key === "Enter") search();
});

load();

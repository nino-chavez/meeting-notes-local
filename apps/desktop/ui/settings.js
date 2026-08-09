const invoke = window.__TAURI__?.core?.invoke;
const panes = ["capture", "privacy", "connections", "voice", "desktop", "shortcuts", "about"];
const tabs = [...document.querySelectorAll("[data-pane]")];
const panels = [...document.querySelectorAll("[data-pane-panel]")];
const storageKey = "yawn-settings:last-pane";

function validPane(value) {
  return panes.includes(value) ? value : "capture";
}

function adjacentPane(current, key) {
  if (key === "Home") return panes[0];
  if (key === "End") return panes.at(-1);
  const index = Math.max(0, panes.indexOf(current));
  const delta = key === "ArrowLeft" || key === "ArrowUp" ? -1 : 1;
  return panes[(index + delta + panes.length) % panes.length];
}

async function updateTitle(pane) {
  const label = tabs.find((tab) => tab.dataset.pane === pane)?.textContent.trim() || "Settings";
  const title = `${label} — Yawn Settings`;
  document.title = title;
  try {
    await window.__TAURI__?.window?.getCurrentWindow().setTitle(title);
  } catch {
    // The document title remains the truthful fallback outside Tauri.
  }
}

function activatePane(value, { focus = false } = {}) {
  const pane = validPane(value);
  tabs.forEach((tab) => {
    const selected = tab.dataset.pane === pane;
    tab.setAttribute("aria-selected", String(selected));
    tab.tabIndex = selected ? 0 : -1;
    if (selected && focus) tab.focus();
  });
  panels.forEach((panel) => {
    panel.hidden = panel.dataset.panePanel !== pane;
  });
  try {
    localStorage.setItem(storageKey, pane);
  } catch {
    // Storage refusal does not block navigation.
  }
  void updateTitle(pane);
}

function permissionPresentation(value, channel) {
  if (value === "authorized") return { label: "Allowed", state: "ready", help: `${channel} access is allowed for this signed app.` };
  if (value === "denied" || value === "restricted") return { label: "Not allowed", state: "error", help: `macOS is not allowing ${channel.toLowerCase()} access. Change it in System Settings.` };
  if (value === "not-determined") return { label: "Not asked", state: "information", help: `${channel} access has not been requested on this Mac.` };
  if (value === "unavailable" || value === "unsupported") return { label: "Unavailable", state: "error", help: `${channel} capture is unavailable on this Mac.` };
  if (value === "unmeasured") return { label: "Not checked", state: "information", help: `${channel} cannot be checked without attempting access. Settings did not ask.` };
  return { label: "Unknown", state: "warning", help: `${channel} status could not be determined.` };
}

function renderPermission(statusId, helpId, value, channel) {
  const presentation = permissionPresentation(value, channel);
  const status = document.querySelector(statusId);
  status.dataset.state = presentation.state;
  status.querySelector("span:last-child").textContent = presentation.label;
  document.querySelector(helpId).textContent = presentation.help;
}

async function refreshPermissions() {
  const control = document.querySelector("#refresh-permissions");
  control.disabled = true;
  try {
    const result = await invoke?.("first_run_permissions");
    if (!result || result.probeUnavailable) throw new Error("permission probe unavailable");
    renderPermission("#microphone-status", "#microphone-help", result.microphone, "Microphone");
    renderPermission("#system-audio-status", "#system-audio-help", result.systemAudio, "System audio");
  } catch {
    renderPermission("#microphone-status", "#microphone-help", "unknown", "Microphone");
    renderPermission("#system-audio-status", "#system-audio-help", "unknown", "System audio");
  } finally {
    control.disabled = false;
  }
}

tabs.forEach((tab) => {
  tab.addEventListener("click", () => activatePane(tab.dataset.pane));
  tab.addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    activatePane(adjacentPane(tab.dataset.pane, event.key), { focus: true });
  });
});

document.querySelector("#refresh-permissions").addEventListener("click", refreshPermissions);

let savedPane = "capture";
try {
  savedPane = validPane(localStorage.getItem(storageKey));
} catch {
  // Capture remains the safe default.
}
activatePane(savedPane);
void refreshPermissions();

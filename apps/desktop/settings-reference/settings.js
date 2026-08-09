import { PANE_IDS, adjacentPane, paneWindowTitle, validPane } from "./settings-state.mjs";

const PANE_STORAGE_KEY = "yawn-settings-reference:last-pane";
const CONTROL_STORAGE_KEY = "yawn-settings-reference:capture-controls";
const tabs = [...document.querySelectorAll("[data-pane]")];
const panels = [...document.querySelectorAll("[data-pane-panel]")];

function readStoredPane() {
  try {
    return validPane(localStorage.getItem(PANE_STORAGE_KEY));
  } catch {
    return "capture";
  }
}

function writeStoredPane(pane) {
  try {
    localStorage.setItem(PANE_STORAGE_KEY, pane);
  } catch {
    // A storage refusal must not block pane navigation.
  }
}

async function updateNativeTitle(pane) {
  const title = paneWindowTitle(pane);
  document.title = title;
  try {
    await window.__TAURI__?.window?.getCurrentWindow().setTitle(title);
  } catch {
    // The document title remains correct in non-Tauri contract tests.
  }
}

function activatePane(pane, { focus = false } = {}) {
  const activePane = validPane(pane);
  tabs.forEach((tab) => {
    const selected = tab.dataset.pane === activePane;
    tab.setAttribute("aria-selected", String(selected));
    tab.tabIndex = selected ? 0 : -1;
    if (selected && focus) tab.focus();
  });
  panels.forEach((panel) => {
    panel.hidden = panel.dataset.panePanel !== activePane;
  });
  writeStoredPane(activePane);
  void updateNativeTitle(activePane);
}

tabs.forEach((tab) => {
  tab.addEventListener("click", () => activatePane(tab.dataset.pane));
  tab.addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End"].includes(event.key)) {
      return;
    }
    event.preventDefault();
    activatePane(adjacentPane(tab.dataset.pane, event.key), { focus: true });
  });
});

function readControlState() {
  try {
    return JSON.parse(localStorage.getItem(CONTROL_STORAGE_KEY) || "{}");
  } catch {
    return {};
  }
}

function writeControlState() {
  const state = {};
  document.querySelectorAll("[data-setting]").forEach((control) => {
    state[control.dataset.setting] = control.type === "checkbox" ? control.checked : control.value;
  });
  try {
    localStorage.setItem(CONTROL_STORAGE_KEY, JSON.stringify(state));
  } catch {
    // The reference remains usable when persistence is unavailable.
  }
}

const savedControls = readControlState();
document.querySelectorAll("[data-setting]").forEach((control) => {
  const saved = savedControls[control.dataset.setting];
  if (saved !== undefined) {
    if (control.type === "checkbox" && typeof saved === "boolean") control.checked = saved;
    if (control.type !== "checkbox" && [...control.options].some((option) => option.value === saved)) {
      control.value = saved;
    }
  }
  control.addEventListener("change", writeControlState);
});

activatePane(readStoredPane());

// Keep the ordered list exercised in production code so accidental tab drift is visible.
if (tabs.length !== PANE_IDS.length) {
  document.body.dataset.navigationContract = "invalid";
}

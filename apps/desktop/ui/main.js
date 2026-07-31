document.documentElement.dataset.shellRendered = "true";

const title = document.querySelector("#status-title");
const pill = document.querySelector(".pill");

const labels = {
  "shell-rendered": ["Opening the local shell", "Opening"],
  checking: ["Checking this installation", "Checking"],
  ready: ["Local runtime is ready", "Ready"],
  "runtime-missing": ["Local runtime is missing", "Reinstall required"],
  "service-timeout": ["Local runtime did not answer", "Retry available"],
  "diagnostic-written": ["A private diagnostic was saved", "Needs attention"],
  retrying: ["Checking this installation again", "Checking"],
  "reinstall-required": ["This installation must be repaired", "Reinstall required"],
};

async function loadStartupStatus() {
  try {
    const state = await window.__TAURI__.core.invoke("startup_status");
    const [heading, badge] = labels[state] ?? labels["diagnostic-written"];
    title.textContent = heading;
    pill.textContent = badge;
    document.documentElement.dataset.startupState = state;
  } catch {
    title.textContent = "The local safety check could not finish";
    pill.textContent = "Needs attention";
    document.documentElement.dataset.startupState = "diagnostic-written";
  }
}

loadStartupStatus();

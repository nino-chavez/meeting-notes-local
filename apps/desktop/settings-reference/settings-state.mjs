export const PANE_IDS = [
  "capture",
  "privacy",
  "connections",
  "voice",
  "desktop",
  "shortcuts",
  "about",
];

export const PANE_TITLES = {
  capture: "Capture",
  privacy: "Privacy",
  connections: "Connections",
  voice: "Voice profile",
  desktop: "Desktop behavior",
  shortcuts: "Shortcuts",
  about: "About",
};

export function validPane(value) {
  return PANE_IDS.includes(value) ? value : "capture";
}

export function adjacentPane(current, key) {
  const currentIndex = Math.max(0, PANE_IDS.indexOf(validPane(current)));
  if (key === "Home") return PANE_IDS[0];
  if (key === "End") return PANE_IDS.at(-1);
  if (key === "ArrowRight" || key === "ArrowDown") {
    return PANE_IDS[(currentIndex + 1) % PANE_IDS.length];
  }
  if (key === "ArrowLeft" || key === "ArrowUp") {
    return PANE_IDS[(currentIndex - 1 + PANE_IDS.length) % PANE_IDS.length];
  }
  return validPane(current);
}

export function paneWindowTitle(pane) {
  return `${PANE_TITLES[validPane(pane)]} — Yawn Settings`;
}

export const DESKTOP_LAYOUTS = Object.freeze(["automatic", "focus", "library"]);

export function normalizeDesktopLayout(value) {
  return DESKTOP_LAYOUTS.includes(value) ? value : "automatic";
}

export function effectiveDesktopLayout(value, width) {
  const preference = normalizeDesktopLayout(value);
  const safeWidth = Number.isFinite(width) ? width : 0;
  if (preference === "focus") return "focus";
  if (preference === "library") return safeWidth >= 900 ? "library" : "split";
  return safeWidth >= 800 ? "split" : "focus";
}

export function opensMeetingBesideList(value, width) {
  return effectiveDesktopLayout(value, width) !== "focus";
}

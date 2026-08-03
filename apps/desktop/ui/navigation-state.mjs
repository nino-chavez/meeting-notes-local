export const PRODUCT_ROOT_SCREENS = Object.freeze([
  "find-screen",
  "meetings-screen",
  "promises-screen",
]);

export function rootForDestination(destination, currentRoot = "find-screen") {
  if (PRODUCT_ROOT_SCREENS.includes(destination)) return destination;
  return PRODUCT_ROOT_SCREENS.includes(currentRoot) ? currentRoot : "find-screen";
}

export function restoredScrollPosition(storedPosition, reset = false) {
  if (reset || !Number.isFinite(storedPosition) || storedPosition < 0) return 0;
  return storedPosition;
}

export function createSingleFlight(loader) {
  let activePromise = null;
  return {
    run() {
      if (!activePromise) {
        activePromise = Promise.resolve()
          .then(loader)
          .catch((error) => {
            activePromise = null;
            throw error;
          });
      }
      return activePromise;
    },
    reset() {
      activePromise = null;
    },
  };
}

export async function prepareConsentTransition(capture, actions) {
  if (capture === "idle") return true;
  if (capture !== "transcript-ready") return false;
  await actions.dismiss();
  actions.clearPriorAttempt();
  const snapshot = await actions.refresh();
  return snapshot?.capture === "idle";
}

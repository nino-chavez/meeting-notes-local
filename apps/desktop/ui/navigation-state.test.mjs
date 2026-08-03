import assert from "node:assert/strict";
import test from "node:test";

import {
  createSingleFlight,
  prepareConsentTransition,
  refreshFindGeneration,
  restoredScrollPosition,
  rootForDestination,
} from "./navigation-state.mjs";

test("single-flight initialization deduplicates only an in-flight snapshot", async () => {
  let loads = 0;
  let release;
  const initializer = createSingleFlight(() => {
    loads += 1;
    return new Promise((resolve) => { release = resolve; });
  });

  const first = initializer.run();
  const second = initializer.run();
  await Promise.resolve();
  assert.equal(first, second);
  assert.equal(loads, 1);
  release({ state: "populated" });
  assert.deepEqual(await first, { state: "populated" });

  const third = initializer.run();
  await Promise.resolve();
  assert.equal(loads, 2);
  release({ state: "empty" });
  assert.deepEqual(await third, { state: "empty" });
});

test("every Find refresh renders handles from a new response generation", async () => {
  const events = [];
  const renderedHandles = [];
  let responseGeneration = 0;
  const actions = {
    invalidateResults: () => { events.push("invalidate"); },
    snapshot: async () => {
      responseGeneration += 1;
      events.push(`snapshot:${responseGeneration}`);
    },
    search: async (query) => {
      responseGeneration += 1;
      events.push(`search:${query}:${responseGeneration}`);
      return { handle: `search-handle-${responseGeneration}` };
    },
    render: (response) => {
      events.push(`render:${response.handle}`);
      renderedHandles.push(response.handle);
    },
  };

  await refreshFindGeneration("first", actions);
  await refreshFindGeneration("first", actions);
  assert.deepEqual(events, [
    "invalidate", "snapshot:1", "search:first:2", "render:search-handle-2",
    "invalidate", "snapshot:3", "search:first:4", "render:search-handle-4",
  ]);
  assert.deepEqual(renderedHandles, ["search-handle-2", "search-handle-4"]);
  assert.notEqual(renderedHandles[0], renderedHandles[1]);
});

test("cold empty Find snapshots once without creating result handles", async () => {
  const events = [];
  await refreshFindGeneration("", {
    invalidateResults: () => { events.push("invalidate"); },
    snapshot: async () => { events.push("snapshot"); },
    search: async () => { events.push("search"); },
    render: () => { events.push("render"); },
  });
  assert.deepEqual(events, ["invalidate", "snapshot"]);
});

test("failed Find refresh leaves invalidated results unrendered", async () => {
  const events = [];
  await assert.rejects(refreshFindGeneration("words", {
    invalidateResults: () => { events.push("invalidate"); },
    snapshot: async () => {
      events.push("snapshot");
      throw new Error("snapshot failed");
    },
    search: async () => { events.push("search"); },
    render: () => { events.push("render"); },
  }), /snapshot failed/);
  assert.deepEqual(events, ["invalidate", "snapshot"]);
});

test("transcript-ready start dismisses and clears before requiring idle", async () => {
  const events = [];
  const ready = await prepareConsentTransition("transcript-ready", {
    dismiss: async () => { events.push("dismiss"); },
    clearPriorAttempt: () => { events.push("clear"); },
    refresh: async () => {
      events.push("refresh");
      return { capture: "idle" };
    },
  });

  assert.equal(ready, true);
  assert.deepEqual(events, ["dismiss", "clear", "refresh"]);
});

test("failed dismissal never clears state, refreshes, or admits consent", async () => {
  const events = [];
  await assert.rejects(
    prepareConsentTransition("transcript-ready", {
      dismiss: async () => {
        events.push("dismiss");
        throw new Error("dismiss failed");
      },
      clearPriorAttempt: () => { events.push("clear"); },
      refresh: async () => {
        events.push("refresh");
        return { capture: "idle" };
      },
    }),
    /dismiss failed/,
  );
  assert.deepEqual(events, ["dismiss"]);
});

test("idle start is direct and other capture states refuse consent", async () => {
  const actions = {
    dismiss: async () => { throw new Error("unexpected dismissal"); },
    clearPriorAttempt: () => { throw new Error("unexpected clear"); },
    refresh: async () => { throw new Error("unexpected refresh"); },
  };
  assert.equal(await prepareConsentTransition("idle", actions), true);
  assert.equal(await prepareConsentTransition("recording", actions), false);
});

test("nested routes keep their real product root", () => {
  assert.equal(rootForDestination("find-screen", "meetings-screen"), "find-screen");
  assert.equal(rootForDestination("meeting-detail-screen", "meetings-screen"), "meetings-screen");
  assert.equal(rootForDestination("library-transcript-screen", "find-screen"), "find-screen");
  assert.equal(rootForDestination("profile-screen", "promises-screen"), "promises-screen");
  assert.equal(rootForDestination("profile-screen", "unknown"), "find-screen");
});

test("returning restores scroll while new content starts at the top", () => {
  assert.equal(restoredScrollPosition(undefined), 0);
  assert.equal(restoredScrollPosition(184), 184);
  assert.equal(restoredScrollPosition(184, true), 0);
});

// The shell calls only names it actually has.
//
// Written 2026-08-07 after an over-broad edit deleted `renderTranscriptNote`
// while a call to it survived. `node --check` passed — it parses, it does not
// resolve — and the Rust contract tests passed too, because they assert strings
// that were still present elsewhere in the file. The failure would have been a
// ReferenceError the first time a transcript rendered, which is to say on every
// finished meeting.
//
// This repo deliberately carries no JS toolchain: no package manager install, no
// node_modules, no lint. So the check is written against `node:test`, which is
// already the harness, rather than by adding ESLint for one rule.
//
// It is intentionally narrow. Only *bare* calls are examined — `name(` not
// preceded by a dot — because member calls resolve against objects this cannot
// see. A name counts as available if the file declares it, imports it, or it is
// on the browser/ECMAScript allowlist below. The allowlist is the maintenance
// cost, and it is the right place for the cost to sit: a new global is one line,
// and forgetting it fails loudly rather than silently.

import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));

// Globals the shell may call without declaring. Kept short on purpose: anything
// long enough to hide a typo defeats the check.
const AVAILABLE_GLOBALS = new Set([
  // ECMAScript
  "Array", "BigInt", "Boolean", "Error", "JSON", "Map", "Math", "Number",
  "Object", "Promise", "Set", "String", "Symbol", "parseFloat", "parseInt",
  "Date", "isNaN", "isFinite", "encodeURIComponent", "decodeURIComponent", "structuredClone",
  // Browser
  "alert", "atob", "btoa", "clearInterval", "clearTimeout", "confirm", "fetch",
  "queueMicrotask", "requestAnimationFrame", "setInterval", "setTimeout",
  // Control flow and operators the call-shaped regex also matches
  "if", "for", "while", "switch", "catch", "return", "typeof", "function",
  "await", "async", "new", "delete", "void", "in", "of", "do", "else", "yield",
]);

function withoutStringsAndComments(source) {
  // Crude but sufficient: the goal is to stop a call-shaped sequence inside a
  // comment or a message string from being read as a call. Replacing rather than
  // deleting keeps every offset, so nothing shifts.
  return source
    .replace(/\/\*[\s\S]*?\*\//g, (match) => " ".repeat(match.length))
    .replace(/(^|[^:])\/\/[^\n]*/g, (match, lead) => lead + " ".repeat(match.length - lead.length))
    .replace(/`(?:\\[\s\S]|[^\\`])*`/g, (match) => `\`${" ".repeat(Math.max(0, match.length - 2))}\``)
    .replace(/"(?:\\[\s\S]|[^\\"\n])*"/g, (match) => `"${" ".repeat(Math.max(0, match.length - 2))}"`)
    .replace(/'(?:\\[\s\S]|[^\\'\n])*'/g, (match) => `'${" ".repeat(Math.max(0, match.length - 2))}'`);
}

function declaredNames(source) {
  const names = new Set();
  for (const [, name] of source.matchAll(/\bfunction\s+([A-Za-z_$][\w$]*)/g)) names.add(name);
  for (const [, name] of source.matchAll(/\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)/g)) names.add(name);
  for (const [, name] of source.matchAll(/\bclass\s+([A-Za-z_$][\w$]*)/g)) names.add(name);
  // Destructured bindings and parameters, which are call targets often enough.
  for (const [, group] of source.matchAll(/\b(?:const|let|var)\s*\{([^}]*)\}/g)) {
    for (const part of group.split(",")) {
      const name = part.split(":").pop().split("=")[0].trim();
      if (/^[A-Za-z_$][\w$]*$/.test(name)) names.add(name);
    }
  }
  for (const [, group] of source.matchAll(/\bimport\s*\{([^}]*)\}\s*from/g)) {
    for (const part of group.split(",")) {
      const name = part.split(" as ").pop().trim();
      if (/^[A-Za-z_$][\w$]*$/.test(name)) names.add(name);
    }
  }
  // Method shorthand in an object literal — `enter() { ... }` — is a definition
  // that reads exactly like a call. Collecting it as declared is what keeps this
  // check usable on `navigation-state.mjs`, which is full of them.
  for (const [, name] of source.matchAll(/([A-Za-z_$][\w$]*)\s*\([^()]*\)\s*\{/g)) {
    names.add(name);
  }
  // Function parameters. Coarse — every identifier inside a parameter list —
  // which errs toward accepting, and accepting is the safe direction for a
  // check whose only job is to catch a name that exists nowhere at all.
  for (const [, group] of source.matchAll(/(?:function\s*[\w$]*\s*|\)\s*=>|\b)\(([^()]*)\)\s*(?:=>|\{)/g)) {
    for (const [, name] of group.matchAll(/([A-Za-z_$][\w$]*)/g)) names.add(name);
  }
  return names;
}

function bareCallTargets(source) {
  const targets = new Map();
  for (const match of source.matchAll(/(^|[^.\w$])([A-Za-z_$][\w$]*)\s*\(/gm)) {
    const name = match[2];
    if (!targets.has(name)) {
      targets.set(name, source.slice(0, match.index).split("\n").length);
    }
  }
  return targets;
}

for (const file of ["main.js", "navigation-state.mjs"]) {
  test(`${file} calls nothing it does not have`, () => {
    const source = withoutStringsAndComments(readFileSync(join(here, file), "utf8"));
    const available = declaredNames(source);
    const missing = [];
    for (const [name, line] of bareCallTargets(source)) {
      if (available.has(name) || AVAILABLE_GLOBALS.has(name)) continue;
      missing.push(`${file}:${line} calls ${name}(), which is never declared or imported`);
    }
    assert.deepEqual(missing, []);
  });
}

test("the shell renders its own transcript note, which an edit once removed", () => {
  // The specific regression, kept beside the general check so the reason the
  // general check exists is not lost if it is ever softened.
  const source = readFileSync(join(here, "main.js"), "utf8");
  assert.match(source, /function renderTranscriptNote\(\)/);
  assert.match(source, /\.then\(renderTranscriptNote\)/);
});

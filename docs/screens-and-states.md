# Screens and states — local-meeting-notes

The L5 inventory. Authored **before** any template, component, or token, per the
Blueprint finding that L4 templates cannot be derived without an L5 surface
inventory — and that patching at L1 when the missing primitive is at L4 produces
bugs that *move* from surface to surface rather than closing.

This is a native-shell app, so "route + auth state" does not apply. The
equivalent axes are **surface** and **lifecycle state**.

---

## A. Menubar item

Always present. The primary UI — most sessions never open a window.

| State | Trigger | Treatment |
|---|---|---|
| `idle` | Default | Hollow glyph. No motion. |
| `detected` | An app started using the microphone | Glyph gains outline emphasis. Still not recording. |
| `armed` | Consent given, countdown running | Countdown is legible in the glyph itself, not only in the notification. |
| `recording` | Capture running, both legs healthy | Filled glyph in the live accent. This is the only place the accent appears. |
| `degraded` | Recording, but one leg failed | Filled glyph, accent, plus a persistent mark. Never silently "recording." |
| `transcribing` | Capture ended, ASR still running | Distinct from both idle and recording. |
| `error` | Unrecoverable | Neutral error mark. Never the live accent. |

**Load-bearing rule:** `recording` and `degraded` must be distinguishable at a
glance without a click. A tool that may be listening and looks identical whether
it is or isn't is the failure this product cannot ship with.

---

## B. Detection notification — the consent moment

The highest-stakes surface in the product. Two-party consent is a legal
constraint in roughly a dozen US states, and this is the only surface that
addresses it.

| State | Trigger | Notes |
|---|---|---|
| `prompt` | Mic-use detected | Offers record / not this time / never for this app. |
| `countdown` | Auto-start enabled | Cancellable for its full duration. The countdown is the consent window; it cannot be zero. |
| `declined` | Dismissed or explicitly declined | Silent. No re-prompt for the same session. |
| `suppressed` | App on the never-list | No notification at all. |
| `manual` | Started from the menubar with no detection | Skips detection but not the consent affordance. |

**Design question this surface owns:** whether the far end is told. Circleback,
Granola and Fireflies each answered differently — Fireflies' bot announces
itself by existing; the bot-free products leave it to the operator. The default
here is a decision, not an oversight, and it belongs in this inventory rather
than in an implementation detail.

---

## C. Recording HUD

Visible while capturing. Small, positioned, dismissible to the menubar.

| State | Trigger |
|---|---|
| `running` | Both legs healthy, levels moving on both |
| `mic-only` | System-audio tap failed or was never granted |
| `system-only` | Microphone muted or unavailable |
| `tap-lost` | Tap died mid-meeting — device change, permission revoked, aggregate device torn down |
| `device-changed` | Default input or output switched mid-meeting |
| `drift` | The two streams' timestamps have diverged past threshold |
| `stopping` | Capture ending, buffers flushing |

**`tap-lost`, `device-changed` and `drift` are states on this surface, not error
dialogs.** They are expected conditions across a 60-minute capture, and the
recording continues degraded rather than failing. Modeling them as modals is the
error that makes the tool untrustworthy in the exact moment it matters.

Two independently-clocked streams are the source of `drift`; see the teardown's
engineering notes. The HUD is where that becomes visible to the operator.

---

## D. Live note surface

Open during the meeting. The operator types their own notes while transcription
runs — the Granola insight, and the reason this isn't just a transcript viewer.

| State | Trigger |
|---|---|
| `empty` | Meeting started, nothing typed, no transcript yet |
| `typing` | Operator notes only |
| `streaming` | Transcript arriving alongside notes |
| `lagging` | ASR behind real time by more than a chunk |
| `queued` | ASR unavailable; audio buffered, transcript deferred |

`queued` inherits `local-dictation`'s existing principle: the pipeline degrades
rather than hard-failing, and the operator is told which leg is down.

---

## E. Note detail — post-meeting

| State | Trigger |
|---|---|
| `processing` | Transcript complete, summary running |
| `ready` | Summary written |
| `summary-failed` | Model unreachable — raw transcript is shown, marked as unsummarized |
| `edited` | Operator has modified the note |
| `exported` | Written out to Markdown |

`summary-failed` is a first-class state, not an error. The transcript is the
durable artifact; the summary is an enhancement over it.

---

## F. Notes library

The IA surface. Decides whether the corpus is useful in six months or a junk
drawer.

| State | Trigger |
|---|---|
| `first-run` | No notes yet |
| `populated` | Default |
| `searching` | Query active |
| `no-results` | Query returns nothing |
| `filtered` | Narrowed by date, participant, or tag |

**Open IA decisions this surface owns**, to be settled before it is designed:
the organizing primitive (chronological, by counterpart, by project), whether
notes link to each other, and whether search covers transcripts or only notes.

---

## G. Settings

| State | Trigger |
|---|---|
| `permissions-needed` | Microphone or audio-capture permission missing |
| `permissions-partial` | One granted, one not — the common real state |
| `ready` | All grants present |
| `device-selection` | Choosing input / output to capture |
| `model-selection` | ASR and summarization model choice |

`permissions-partial` is the state that actually occurs and the one most likely
to be skipped in design. macOS attributes prompts to the launching binary, and
under launchd there is no hosting terminal — `local-dictation`'s README already
documents this trap.

---

## H. First run

| State |
|---|
| `welcome` |
| `request-microphone` |
| `request-audio-capture` |
| `denied-recovery` — deep-link to the right System Settings pane |
| `ready` |

---

## L4 templates derived from the above

Five, and no more until an L5 state demands a sixth:

1. **Shell chrome** — window frame, sidebar, title treatment. Used by D, E, F, G.
2. **List–detail** — F to E.
3. **Transient overlay** — B and C. Positioned, non-modal, dismissible.
4. **Form** — G.
5. **Sequence** — H, and only H.

The menubar item (A) is not a template. It is a single glyph with seven states
and is specified directly.

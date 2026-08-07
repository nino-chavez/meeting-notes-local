# MLX title-selection probe

**Registered 2026-08-08, before any inference call. Nothing in this section
reports a result.** The prediction below is the point of the exercise; a number
recorded after the fact is not evidence about what was expected.

This is a separate contract in separate files. It reads `MLX_RUNTIME` from
`mlx_note_admission.py` and writes nothing there, so **no committed note receipt
is invalidated and no note request digest moves.** A reader who has absorbed that
file's history of digest invalidation should not assume otherwise.

## The question

`meeting_title::derived_title` already names a meeting: the first non-gated turn
whose opening sentence runs to at least six words. It landed 2026-08-07 and it is
deliberately crude.

**Does a pinned local model pick a better turn than "the first one long enough"?**

Not "can a model write a title." The model never writes anything here.

## The model returns an index, and cannot return words

The response contract is one JSON object with one field:

    {"turn": <one offered turn number>}   or   {"turn": null}

Every word of every title still comes from `meeting_title.rs`, applied to
whichever turn the model named. Three consequences, and they are why the shape
is this and not the obvious one:

**A selected title is a span of the transcript by construction.** Not validated
afterwards, not requested in a prompt. There is no channel through which model
text could reach a title, so the invariant that evidence is never decoration
holds as a property of the decoder.

**The model's measured weakness is designed out rather than tested again.**
`MLX_NOTE_ADMISSION.md` records this exact model reproducing *enumerated* values
10 of 10 and non-enumerated 90-character identifiers 1 of 10 — and that one a
coin flip, at +0.16 logits against a mean of −1.03. Enumerating the offered
identifiers moved the mean margin +2.74 and fixed 7 of 10. A single small integer
from an enumerated set is the easiest thing that file measured this model doing.
Asking it for a span, a citation, or a phrase would spend the probe re-measuring
a known failure.

**A wrong pick is a real sentence from the meeting**, just not the most
identifying one. The worst case is a worse label. It is never an invented one.

## What is offered, and what is not

Gated turns are **absent from the offered set**, not marked within it. A withheld
microphone turn therefore has no index in the response language, and the mask
cannot emit one. `derived_title` skips gated turns by filtering them; here they
are not in the alphabet. That is strictly stronger, and it is the difference
between a rule that is checked and one that cannot be broken.

## The mask, and a soundness claim that is total rather than sampled

`title_decoding.py` is a sibling of `structured_decoding.py`, not an extension.
It reuses that module's `allowed_token_ids` and `make_contract_logits_processor`
unchanged — both take the machine as a parameter — because those carry four
corrections found by running the note probe: the stop token living above
`vocab_size`, stop tokens being decoded into the walked text, the first token
arriving unmasked, and the per-state cache.

The note mask's soundness could only be enumerated "at a reduced ceiling (one
item, two fragment IDs)", and at that ceiling **288 of the 385 accepted strings
were invalid JSON**. The reduction was forced by free-text holes, which are
infinite.

This contract has no free-text hole. With `n` offered turns the language is
exactly `n + 1` strings, so `test_mlx_title_selection.py` enumerates **all** of
them by walking the machine's own transitions and `json.loads` every one. The
claim here is *there is no invalid string*, not *no invalid string was found*.

Whitespace is excluded from that walk and covered by a separate test. The machine
tolerates unbounded whitespace runs before and after the object — because
`mlx_lm==0.30.4` samples the first token before any logits processor runs, and
this model opens its turn with a newline — so including it turns a search over a
small language into a search over 4^ceiling whitespace strings. The first version
of the test did exactly that and had to be killed.

**The parser is independent of the mask and both run.** Where they disagree, the
mask is stricter and only about formatting: it admits one spelling per answer, so
a masked run's responses are byte-comparable across repeats, while the parser
accepts any JSON meaning the same thing. Where meaning is at stake — `02`, `-1`,
a trailing comma, a duplicate key, `true` (which `isinstance(True, int)` would
have decoded as turn one) — both refuse.

## The fixtures, and what `intended_turn` is

Ten synthetic transcripts in `title_selection_fixtures.json`. Every word was
invented for that file; no meeting recording, Preview datum or product record
appears in it.

`control_turn` is what `derived_title` picks. It is **asserted by a Rust test
against the real function** —
`the_probe_fixtures_name_the_turn_this_function_actually_picks` — so the baseline
cannot drift from the shipped rule, and the probe never reimplements it. One
implementation, one file carrying both arms' expectations.

`intended_turn` is the turn that names the meeting in the fixture author's
judgment, recorded before any model ran. **Agreement with it is a selection
measurement and not a usefulness claim.** No mechanical result here can establish
that a title is worth reading.

### The suite was rebalanced because it was gameable

The first draft put the identifying turn second-from-the-start in five of ten
cases and last in five. **"Always take the second offered turn" scored 6 of 10
and "always take the last" scored 5** — strategies that read nothing, either of
which would have been reported as selection working.

`test_no_degenerate_position_rule_scores_well` now caps every position rule at 3
of 10, and the fixtures were changed against the test rather than the test
relaxed against the fixtures. Measured baselines, all registered before the run:

| Strategy | Score | Reads the words? |
|---|---|---|
| `derived_title`, the shipped rule | **1 / 10** | no |
| always the first offered turn | 1 / 10 | no |
| always the second offered turn | **3 / 10** | no |
| always the last offered turn | 0 / 10 | no |
| always abstain | 1 / 10 | no |
| uniform random over offered ∪ {null} | 2.28 / 10 expected | no |

## The prediction, stated before the answer is known

**Registered prediction, two-sided: the model agrees with `intended_turn` on 6 to
9 of the 10 fixtures.**

The bound is two-sided on purpose. `MLX_NOTE_ADMISSION.md` records a one-sided
bound being satisfied by a *harmful* result and calls scoring that a hit "exactly
the charitable reading this file exists to refuse."

- **Below 6**, the model is not reliably beating a rule that reads nothing — the
  strongest such rule scores 3 — and the selection path is closed for this model
  at this size. That is a real finding and it saves building the Rust seam.
- **At 10**, something other than selection is likely carrying the result. A
  1.5B 4-bit model scoring perfectly on a semantic judgment is more plausibly a
  cue left in the fixture authoring than a capability, and it must be found
  before the result is claimed.

**Two controls, registered with it:**

1. `no-agenda-abstain` must return exactly `{"turn":null}`. A model that cannot
   abstain will produce a confident title for a meeting that has no subject, and
   that is a separate finding from picking the wrong turn.
2. `agenda-first` must return turn 0, where the deterministic rule is already
   right. An intervention that buys late-agenda fixtures by systematically
   avoiding the first turn is not selection.

## Gates

| Gate | Pass condition | Failure |
|---|---|---|
| Syntax and schema | **Not discriminating for the model**, by construction, and it measures the mask. Every response parses, or the mask is wrong. | Any refusal here is a mask defect and must be reported as one, never as a model result. |
| Mask never refuses | `MaskRefused` is not raised on any fixture. | A refusal means the model reached a state the machine cannot continue — a mask defect, not a candidate rejection. |
| Selection | 6 to 9 of 10 agree with `intended_turn`. | Outside that range, see the two clauses above. |
| Abstention | `no-agenda-abstain` returns null. | Reported separately; it does not by itself close the path. |
| Repeatability | Response SHA-256 identical across three cold runs from fresh processes, at temperature 0.0 and seed 0. | Any variation rejects the result; do not average it away. |
| Latency and memory | Reported, and **not** a rejection criterion. The mask runs in Python and is rebuilt per request because its language depends on which turns that request offers. | — |
| Human judgment of whether the titles are worth reading | **Unreachable from here.** | — |

## What a pass would and would not authorize

It **would** authorize building the selection seam in Rust — a `title_from_turn`
beside `derived_title`, taking a validated turn index and applying the same
cleaning and ceiling.

It would **not** admit a note generator, wire anything into the product runtime,
add a worker operation, or satisfy the human gate. `MLX_NOTE_ADMISSION.md`'s gate
table ends at "no admission without a recorded human decision, even if every
mechanical gate passes", and whether an auto-title is worth reading is that
decision. A builder can register, measure and pin this. A builder cannot admit
it.

## Scope

Synthetic fixtures only. No meeting recording, Preview data, or product record.
A disposable pip environment under `/private/tmp`, built with the same wheels
`MLX_RUNTIME` pins, verified by the same guard before a token is generated. The
model is the already-downloaded pinned revision; nothing is re-fetched.

This changes no product runtime, adds no command, and admits nothing.

---

## Result

*Not yet run. This section is deliberately empty in the commit that registers the
prediction above, so that the registration and the result cannot be confused for
having been written together.*

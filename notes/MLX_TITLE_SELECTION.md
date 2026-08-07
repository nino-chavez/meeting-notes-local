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

## Result — 2026-08-08 — the prediction failed, and the path is closed for this model

Run against the pinned model tree `3aaeeac4…`, the pinned wheels, and the
fixtures at the digest the receipts carry. Three cold runs from fresh processes.
Receipts: `mlx_title_selection_receipt.json` and its `_run2` / `_run3` siblings.

**The model agreed with `intended_turn` on 5 of 10. The registered range was 6 to
9. The prediction is wrong and the registered consequence stands: the selection
path is closed for this model at this size.**

| fixture | control | intended | selected | agreed |
|---|---|---|---|---|
| `agenda-after-logistics` | 1 | 2 | **2** | yes |
| `agenda-first` | 0 | 0 | **0** | yes |
| `agenda-late` | 1 | 4 | 5 | no |
| `two-topics` | 0 | 2 | 3 | no |
| `question-agenda` | 0 | 1 | **1** | yes |
| `no-agenda-abstain` | 0 | null | 1 | no |
| `numbers-and-names` | 0 | 2 | 1 | no |
| `negation` | 0 | 1 | **1** | yes |
| `withheld-first` | 1 | 2 | **2** | yes |
| `long-identifying-turn` | 0 | 2 | 1 | no |

### The number is better than every baseline and still below the floor, and the floor wins

5 of 10 beats the shipped rule at 1, the best position rule at 3, and uniform
random at an expected 2.28. It is doing something.

**That paragraph is the whole reason the floor was registered in advance.** The
argument "5 beats every baseline, so this is a pass" is available now and was
available before the run, and adopting it after seeing 5 is the charitable
re-reading this discipline exists to refuse. The floor was set at 6 — double the
strongest non-reading rule — while the outcome was unknown. It stays where it was
put. What the comparison earns is a narrower statement, not a different verdict:
**the result is between random and useful, and the registered threshold for
"useful" was not met.**

### Every mechanical gate passed, which is what makes the selection number readable

| Gate | Result |
|---|---|
| Mask never refused | Pass — no `MaskRefused` on any of 30 calls |
| Syntax and schema | Pass, and non-discriminating by construction — 10 bytes and 7 generated tokens on every call, finish `stop` every time |
| Repeatability | **Pass** — response digests, selections and whole receipts identical across three cold runs once timings are excluded, and a test compares the committed artifacts rather than this sentence |
| Latency | 0.41–0.55 s per call, model load 0.42–0.44 s, mask build 0.25–0.28 s. Reported, not a rejection criterion |
| Model tree | `3aaeeac4…` before and after every run |
| Control 2 — `agenda-first` returns 0 | **Pass**. The model did not buy late-agenda fixtures by avoiding the first turn |
| Control 1 — `no-agenda-abstain` returns null | **Fail**, and see below |

The failure is not a shape failure. Unlike the note probe, whose first two
attempts died on JSON syntax and had to be re-run under a corrected mask, nothing
here was spent measuring a serializer.

### The model never abstained, on any fixture

**0 of 30 calls returned `{"turn":null}`**, including every call on the fixture
built for it, where nothing said identifies a meeting and the model answered
"Yes I can hear you perfectly well."

This is a distinct finding from picking the wrong turn, and it is worse for the
product. A selection model that cannot abstain cannot be given the decision "does
this meeting have a subject at all" — it will always name one. The abstention
branch is reachable in the language, the mask admits it, and the system prompt
asks for it in as many words; it was simply never taken.

### What is not claimed

**No mechanism.** Four of the five misses are visible — the reaction chosen over
the statement, the second topic over the first, logistics over substance twice —
and it would be easy to write a sentence explaining them. `MLX_NOTE_ADMISSION.md`
asserted two mechanisms as established and retracted both; this section is not
going to assert a third from ten fixtures and no probe. The observations are
recorded and nothing is inferred from them.

**Not a statement about local models.** One model, one size, one quantisation,
one prompt, ten synthetic fixtures, one author's judgment of what "intended"
means. A 7B model, a different prompt, or few-shot examples are all untested, and
this result forecloses none of them — it forecloses spending the Rust seam on
*this* candidate.

**Not a statement about auto-titling.** The shipped extractive rule is unaffected
and still names every meeting. What did not happen is the improvement.

### What this licenses

Nothing new gets built. The Rust `title_from_turn` seam is **not** written,
because it now has neither a caller nor a measurement supporting one — which was
the whole point of running the probe before building it.

The harness, mask, fixtures and receipts stay. They are the instrument for the
next candidate, and re-running it against a different model is a `--model-directory`
away.

**A falsifier for anyone who repeats this.** If a candidate clears 6 of 10 here
but still never abstains, the abstention failure is the model class and not this
one, and the contract needs a different answer to "no subject" than asking the
model for one.

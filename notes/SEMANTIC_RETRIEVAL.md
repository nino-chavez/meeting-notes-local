# Semantic retrieval probe

**Registered 2026-08-08, before any download or inference call. Nothing in this
section reports a result.**

Separate contract, separate files. It shares no pin, prompt or receipt with
`MLX_NOTE_ADMISSION.md` or `MLX_TITLE_SELECTION.md`, so no committed receipt on
either path is invalidated by anything here.

## The question

Exact search over the corpus shipped and works on the words people actually said.
Wave 1 item 5 asks for semantic search beside it.

**Given a question, does a small local embedding model retrieve the meeting a
person meant — including when the question's words appear nowhere in it?**

## What is embedded, and what is not

**One vector per meeting**, over the concatenation of its retained turns. The
queue row asks for search over the corpus, and that is a question about which
meeting to open. Landing on the exact claim inside one is item 6 and needs a
different unit; measuring it here would answer a question nobody asked yet.

Nothing is embedded that search does not already read. Withheld turns are absent
from the projection's searchable text and are absent here for the same reason.

## What it is measured against, and why that is the hard part

`library_read::search` is a substring search. Typing a whole question into it
returns nothing, and reporting that as a win would be measuring a strawman. So
the baseline is what a person actually does today: **the single keyword they
would type.**

`semantic_retrieval_fixtures.json` carries ten synthetic meetings and ten
questions. Each question names the meeting a person meant, the keyword they would
try, and whether that keyword finds it. **`exact_helps` is asserted by a Rust test
against the real function** —
`the_semantic_probe_fixtures_describe_what_exact_search_actually_does` — so the
baseline cannot drift from the shipped one or be written down from memory.

The suite is deliberately half and half. Five questions where the keyword already
works, five where it does not. A suite of only the second kind rewards any
non-empty retrieval; a suite of only the first measures nothing a substring match
cannot already do.

### The fixtures were hardened against a control that reads no meaning

A crude word-overlap ranker — shared words between question and transcript, no
model — initially scored **8 of 10 overall and 3 of 5 on the questions exact
search cannot answer.** That is a strategy with no understanding in it, and it
was passing the half of the suite that exists to need understanding.

Two of the three were real: the transcript for "office space" contained the word
*office*, and the one for "database change" contained *change*, while the
fixture's own note claimed those words were absent. The third was a tie-break
artifact — zero shared words ranked first on identifier order alone.

Both words were removed from the transcripts and the control now treats zero
overlap as no answer. **The fixtures were changed, not the bar.**

### Registered baselines, all measured before the run

| Strategy | Overall | On the five exact search cannot answer | Reads meaning? |
|---|---|---|---|
| `library_read::search` with the keyword | **5 / 10** | **0 / 5** | no — substring |
| Word-overlap ranker, no model | 5 / 10 | 0 / 5 | no |
| Uniform random top-1 over ten meetings | 1 / 10 expected | 0.5 / 5 expected | no |

## The prediction, stated before the answer is known

**Registered prediction, two-sided: top-1 accuracy of 8 to 10 of 10 overall, and
at least 4 of the 5 questions exact search cannot answer.**

The second clause is the discriminating one. Overall accuracy can be carried by
the easy half; only the hard half distinguishes retrieval from matching.

- **Below 4 on the hard five**, the model is not supplying what semantic search
  exists to supply, and the path is closed for this model at this size. Two
  non-semantic strategies already score 5 overall, so an overall score alone
  cannot rescue it.
- **Above 9 overall with fewer than 4 on the hard five** would mean it is winning
  exactly where a substring match already wins, which is not a reason to add a
  model, and must be found before anything is claimed.

**One control, registered with it:** the five questions exact search already
answers must score at least 4 of 5. An arm that buys paraphrase at the cost of
proper nouns is a regression wearing a feature's name.

## Gates

| Gate | Pass condition | Failure |
|---|---|---|
| Retrieval | 8–10 overall **and** ≥4 of the hard five | See the two clauses above |
| Control — no regression | ≥4 of the five exact search already answers | Reported separately; on its own it does not close the path |
| Repeatability | Byte-identical vectors and identical rankings across three runs from fresh processes | Any variation rejects the result rather than being averaged |
| Latency | Embedding the ten-meeting corpus and one query, reported. **Not a rejection criterion** — this is a reference implementation, not the shipping one | — |
| Human judgment of whether the results are useful | **Unreachable from here.** Ten synthetic meetings is not a corpus | — |

## What is pinned

- Model `sentence-transformers/all-MiniLM-L6-v2`, Apache-2.0, at immutable
  revision `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`. `model.safetensors` is
  90,868,376 bytes with SHA-256
  `53aa51172d142c89d9012cce15ae4d6cc0ca6895895114379cacb4fab128d9db`, taken from
  the Hugging Face metadata endpoint before any download.
- Package `sentence-transformers==5.7.0`, Apache-2.0.
- A disposable pip environment under `/private/tmp`, as every probe here uses.

### The convenient MLX route is GPL and this repository is MIT

`mlx-embeddings` 0.1.0 is **GPL-3.0**. This repository is MIT, and the product
runtime is MLX-based, so the obvious "just use the MLX embedding wrapper" path is
closed for anything that ships — not on preference, on licence.

That is why the probe uses the reference implementation rather than the eventual
one. The question here is whether *these weights* retrieve the right meeting; the
answer does not depend on which framework multiplies the matrices. **If it passes,
writing the forward pass against MLX directly is the packaging task**, and its
vectors can be checked against this run's. If it fails, that work is never
started, which is the whole reason for probing first.

## What a pass would and would not authorize

It **would** authorize building the vector store — a column beside the corpus
index, written when the index syncs — and an MLX forward pass to fill it.

It would **not** admit anything into the product runtime, add a command, package
a model, or establish that semantic results are useful. Ten synthetic meetings
written by the person grading them is a measurement of retrieval mechanics on a
toy corpus. `MLX_NOTE_ADMISSION.md`'s gate table ends at a recorded human
decision, and that gate is the operator's.

## Scope

Synthetic fixtures only. No meeting recording, Preview data, or product record.
This changes no product runtime, adds no command, and admits nothing.

---

## Result — 2026-08-08 — the prediction holds, and the margins are the finding

Three runs from fresh processes against the pinned revision. The weights' SHA-256
matched the digest taken from the metadata endpoint **before** the download.
Receipts: `semantic_retrieval_receipt.json` and its `_run2` / `_run3` siblings.

**10 of 10 overall, and 5 of 5 on the questions exact search cannot answer.** The
registered range was 8–10 overall with at least 4 of the hard five, and the
no-regression control required at least 4 of the easy five. All three hold.

| Arm | Overall | Hard five | Easy five |
|---|---|---|---|
| `library_read::search` with the keyword | 5 / 10 | **0 / 5** | 5 / 5 |
| Word-overlap ranker, no model | 5 / 10 | **0 / 5** | 5 / 5 |
| **all-MiniLM-L6-v2, cosine over one vector per meeting** | **10 / 10** | **5 / 5** | 5 / 5 |

Repeatability held: the three receipts are identical once the embedding time is
excluded, including every similarity margin to six decimals.

### The score is not the interesting number. The margins are.

| Question class | Margin over the runner-up |
|---|---|
| The five exact search already answers | 0.101, 0.237, 0.323, 0.429, 0.461 |
| The five it cannot | **0.013, 0.021, 0.038**, 0.117, 0.214 |

**Three of the five questions this feature exists for were near-ties.**

| Question | Chose | Runner-up |
|---|---|---|
| "Which meeting was about hiring problems?" | `meeting-h` 0.2426 | `meeting-d` 0.2299 |
| "Did we talk about giving up some of our office space?" | `meeting-i` 0.3158 | `meeting-a` 0.2777 |
| "What was the data retention problem?" | `meeting-j` 0.2719 | `meeting-d` 0.2505 |

A 0.013 separation on a corpus of **ten** meetings is a coin landing the right way
up, not a capability. The relevant number is not this run's accuracy; it is how
many distractors sit within 0.013 of the right answer when there are a thousand
meetings instead of nine. Nothing here measures that, and this section is not going
to infer it.

Read the two tables together and the honest statement is narrow: **on a
ten-meeting corpus, this model separates the right meeting from nine wrong ones —
comfortably where the words match and barely where they do not.** That is enough
to justify building the store. It is not enough to predict behaviour at scale, and
the next measurement on this path is a distractor-density one, not a bigger
question list.

### Everything else was uneventful, which is worth one line

The corpus embedded in 0.11–0.92 s (the first run includes a cold model load).
Nothing in the mechanical envelope is near a limit, and latency was registered as
reported-not-rejecting because this is the reference implementation rather than
the shipping one.

### What is not claimed

**Not usefulness.** Ten synthetic meetings written by the person grading them is a
measurement of retrieval mechanics on a toy corpus. Whether semantic results help
is the operator's gate, and it is unreachable from here.

**Not a scale claim**, per the margins above.

**Not a packaging decision.** These vectors came from the Apache-2.0 reference
implementation. `mlx-embeddings` is GPL-3.0 and this repository is MIT, so the
shipping path is a forward pass written against MLX — and its vectors can now be
checked against this run's receipts, which is what makes that task verifiable
rather than hopeful.

### What this licenses

Building the vector store: a column beside the corpus index, written when the
index syncs, and an MLX forward pass to fill it. That is Wave 1 item 5's build,
and it now has a measurement behind it rather than an assumption.

**A falsifier for whoever does it.** If the MLX forward pass reproduces these ten
rankings but its margins on the hard five differ by more than 0.01, the two
implementations are not computing the same thing and the difference must be found
before either is trusted — the rankings agreeing is a weaker check than it looks
when three of them are decided by 0.013.

---

## Correction — 2026-08-08 — the measured setup reads the first 256 tokens of a meeting

Found while writing the MLX implementation, by reading
`sentence_bert_config.json` rather than by anything failing.

**`max_seq_length` is 256.** `SentenceTransformer.encode` truncates to it
silently. The fixtures above are 39 to 48 tokens each, so nothing was ever cut
and the ceiling could not appear in that result.

A real meeting is not 48 tokens. An hour of speech is roughly twelve thousand,
of which this model reads the first two per cent — the opening small talk, and
none of the decision.

**What this does and does not invalidate.** The measured numbers stand: those ten
meetings were embedded whole, the rankings and margins are real, and the MLX
implementation reproduces them. What does not survive is the *unit*. "One vector
per meeting" is what was measured and it is not what can ship, because at real
length it is one vector per meeting's first minute.

**This is a fixture-shape failure, not a model failure**, and it is the second
one this document records. The first was a word-overlap control passing the hard
half; both come from fixtures small and clean enough to hide a property of the
real input. Short synthetic meetings were chosen so the corpus could be read at a
glance, and that choice is exactly what concealed this.

### Registered follow-up, before it is built

The unit has to change and the choice is not obvious, so it is registered rather
than decided in code:

- **One vector per turn** — natural boundaries, no arbitrary cuts, and the count
  grows with the corpus. It also makes meeting-level retrieval an aggregation
  question (best turn? mean? top-k?) that this probe has not measured.
- **One vector per window of N tokens** — bounded count, but cuts land mid-sentence
  and a window straddling two subjects embeds neither.

**Neither is chosen here.** The next measurement on this path is the one already
registered — distractor density at corpus scale — and it should be run against
whichever unit is being proposed, on meetings long enough to truncate. Running it
on 48-token fixtures would repeat the mistake this section is recording.

## The MLX implementation agrees — 2026-08-08

`mlx_minilm.py` is the forward pass this document said the licence required:
BERT encoder, six layers, mean pooling, weights loaded from the pinned
checkpoint. The tokenizer stays `transformers`, which is Apache-2.0 — tokenizing
is not the licence problem, and whether that dependency belongs in the product
runtime is a separate question this does not answer.

The registered falsifier was that rankings agreeing is too weak a check when
three of the deciding comparisons turn on 0.013, so the margins had to agree
within 0.01.

| Check | Result |
|---|---|
| Rankings agreeing with the committed receipt | **10 of 10** |
| Worst margin difference | **0.000001**, against a 0.01 tolerance |
| Compared against | the committed receipt, not a freshly computed reference |

Receipt: `mlx_minilm_verification_receipt.json`. The comparison refuses outright
if the fixtures have moved since the reference run, because a check that
regenerates its own baseline cannot fail.

Two implementation details worth naming, because each would have passed a ranking
check and failed the margin one: `hidden_act` is `gelu`, meaning the erf
formulation rather than the tanh approximation they differ by ~1e-3; and the
checkpoint carries a `pooler.dense` head that sentence-transformers does not use
for this model, so pooling is the mask-weighted mean and not that head.

**`encode` refuses input over 256 tokens rather than truncating it.** The
reference implementation truncates silently, which is how the ceiling above went
unnoticed. Whatever the unit turns out to be, the decision about a long meeting
should be made by something that knows it is making one.

---

## Preregistered amendment — 2026-08-08 — distractor density, and choosing the unit

**Registered before the run. Nothing in this section reports a result.**

The correction above left the unit undecided on purpose and named the measurement
that should decide it. This is that measurement, and it answers both open
questions at once, because they are the same question: **what happens when the
meetings are long and there are many of them.**

### The corpus

`semantic_scale_corpus.json`. A meeting is an opening, a substantive block and a
closing; the openings and closings are logistics and small talk, which is what
really fills the first minutes of a call and which pushes the identifying content
past the 256-token window. A corpus of short dense meetings would hide the
property under test — which is precisely how the ceiling went unnoticed the first
time.

Three populations, **reported separately, because conflating them inflates the
claim**:

| Population | How made | Why |
|---|---|---|
| 10 targets | hand-written | what the questions are about |
| 10 near misses | **hand-written, one per target** | another lease, another rollback, another renewal where usage fell. These cannot be generated: a bank-composed corpus is distinct by construction, and reporting accuracy against it as a scale result is the third fixture-shape trap this document would then have recorded |
| filler | template + substituted entities | to reach a corpus size, and honestly labelled as distinct by construction |

Corpora are **nested**: the corpus at 60 is the first 60 meetings of the corpus at
200, so the density curve is measured over one growing corpus rather than four
unrelated ones.

### The metric is density, not accuracy

Top-1 accuracy at 200 meetings can be 10 of 10 while three distractors sit within
0.005, and those two facts point opposite ways for a product. So the headline is
**how many meetings fall within 0.02 of the top hit**, per question, per unit.
Accuracy is the summary; the distribution is the finding.

`near_miss_rank` is reported per question as well — where the hand-written
adjacent meeting lands. A near miss ranked second is the honest picture of this
model's discrimination in a way an aggregate cannot be.

### Three units, and one fixed aggregation

- `meeting-truncated` — one vector per meeting, cut at the ceiling. What the
  2026-08-08 probe measured, kept as an arm so the cost of that cut is a number
  rather than an argument.
- `turn` — one vector per turn. Natural boundaries, unbounded count.
- `window` — one vector per 128 words. Bounded count, cuts land anywhere.

**Aggregation is fixed at max chunk similarity, and that choice could carry the
result.** Mean-of-top-k is untested; a per-turn arm winning under max might lose
under mean. The comparison below is conditional on this aggregation and says so
rather than being reported as a property of the units.

### The prediction, stated before the answer is known

**Registered prediction: `turn` and `window` each retrieve at least 3 more of the
10 than `meeting-truncated` at the largest corpus size, and the two of them land
within 1 of each other.**

The comparison is the prediction, not the absolute numbers — the decision this
measurement exists for is which unit, and an absolute score cannot make it.

**The tie clause matters more than the gap clause.** If `turn` and `window` land
within 1, the tiebreak is cost and shape rather than accuracy: turn count grows
without bound and varies per meeting, window count is bounded and predictable.
Saying that in advance stops a one-point difference from being read as a mandate.

**Falsifiers.**

- **If `meeting-truncated` is within 2 of the best unit**, truncation costs less
  than the correction assumed, and that correction is overstated. It would not
  make truncation correct — reading 2% of a meeting is still wrong — but the
  argument for changing the unit would then rest on principle rather than on this
  measurement, and it should be said that way.
- **If density does not grow with corpus size**, the synthetic filler is too
  distinct to be a distractor at all, and the result says nothing about a real
  corpus. The near-miss ranks are the check: if the hand-written adjacent
  meetings do not crowd the target while generated filler does not either, the
  corpus is the problem.

### What a result would and would not authorize

It would decide the unit, and license building the vector store around it.

It would **not** establish that retrieval is useful, that a synthetic corpus
predicts a real one, or that the model is admitted. Those are unchanged.

### Result — 2026-08-08 — the prediction holds, and yesterday's headline does not

Receipt: `semantic_scale_receipt.json`. 200 meetings of 497–638 tokens each,
**every one over the 256 ceiling**, nested so each size is a prefix of the next.

**Both registered clauses hold.** `turn` and `window` each beat
`meeting-truncated` by 6 of 10 at N=200, against a registered floor of 3, and
they land 0 apart, inside the registered 1.

| Unit | N=200 | Hard five | Easy five | Pieces stored | Median within 0.02 |
|---|---|---|---|---|---|
| `meeting-truncated` | **1 / 10** | 0 / 5 | 1 / 5 | 200 | **22** |
| `turn` | 7 / 10 | 2 / 5 | 5 / 5 | **16,020** | 0 |
| `window` (128 words) | 7 / 10 | **3 / 5** | 4 / 5 | **800** | 0 |

#### The unit is `window`, and the tie clause is what decides it

Both non-truncating units score 7. The registered tiebreak was cost and shape,
and it is not close: `window` stores **800 pieces where `turn` stores 16,020** —
twenty times fewer — and its count is bounded and predictable per meeting, while
turn count varies with how much people interrupt each other.

Registering that tiebreak in advance is what makes this a decision rather than a
preference. Had it not been written down, 3/5 versus 2/5 on the hard half would
have been available to argue `window` won on quality, and a one-question
difference cannot carry that.

#### Yesterday's result does not survive a realistic corpus

| | 2026-08-08, ten 48-token meetings | 2026-08-08, 200 realistic meetings |
|---|---|---|
| Overall | 10 / 10 | 7 / 10 |
| The five exact search cannot answer | **5 / 5** | **3 / 5** |

**The hard half is where it degrades**, which is the half the feature exists for.
Adding the small talk that actually surrounds a decision costs two of those five,
with the unit chosen and the corpus only 200 meetings deep.

The two failures are legible in the receipt and neither is a near-miss confusion:
the "hiring problems" and "data retention" questions land on generated filler at
a margin of **exactly 0.0000**, with 11 and 15 meetings inside the band. They are
not choosing wrongly between plausible candidates; they are matching nothing in
particular and landing on chatter.

#### Density is the finding the accuracy hides

Median meetings within 0.02 of the top hit, as the corpus grows:

| Unit | N=30 | N=60 | N=120 | N=200 |
|---|---|---|---|---|
| `meeting-truncated` | 3 | 6 | 13 | **22** |
| `turn` | 0 | 0 | 0 | 0 |
| `window` | 0 | 0 | 0 | 0 |

Truncated meetings become indistinguishable at a rate proportional to the corpus
— at 200 meetings, roughly one in nine sits inside the band. The other two units
hold a clean separation **on the questions they answer**, and all of their density
is concentrated on the questions they fail. That is the more useful shape: a wrong
answer arrives with a visible tie rather than a confident margin, which is
something a surface could act on.

#### Two things this overstates, said plainly

**The truncated arm's collapse is exaggerated by the corpus.** Openings are drawn
verbatim from a bank of twelve, so truncated meetings are near-duplicates of each
other and several margins are exactly 0.0000. Real meetings open formulaically but
not identically. Truncation is clearly bad; 1 of 10 is worse than it would be on
real transcripts, and the direction is the finding rather than the magnitude.

**Two hundred meetings of ten minutes is not a year of work.** The meetings are
497–638 tokens; an hour is roughly twelve thousand. Density grows with both corpus
size and meeting length, and only the first was varied here.

#### What this licenses

Building the vector store around **one vector per 128-word window**, with the
piece count that implies — 4 per meeting at this length, bounded, and cheap enough
that a thousand meetings is four thousand vectors.

It does **not** establish that retrieval is useful. 7 of 10 with the hard half at
3 of 5 is a number the operator should see before anything is built on it, and it
is materially worse than the number this document reported yesterday.

#### The third fixture-shape failure on this path, caught by the receipt

The first corpus produced 212-token meetings, of which 8 in 200 crossed the
ceiling. It would have measured **dilution and reported it as truncation**. The
receipt's own `meeting_tokens.over_ceiling` field is what surfaced it, before the
result was written.

A fourth was caught by the implementation: the truncating arm cut at 200 *words*,
which is 266 tokens, and `encode` refused rather than truncating — the refusal
added in the previous change. A run that silently truncated would have produced
plausible numbers for a different experiment.

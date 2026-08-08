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

## Result

*Not yet run. Deliberately empty in the commit that registers the prediction
above, so the two cannot be confused for having been written together.*

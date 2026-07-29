# Notes evaluation — does a local model invent things?

Run 2026-07-28. `llama3.1:8b` via Ollama on Apple Silicon, temperature 0,
`num_ctx` 32768. Three QMSum meetings, eight runs covering all three attribution
levels and four input shapes, plus one deliberate truncation control.
Tool: [`summarize.py`](./summarize.py). Reproduce with `python notes/fetch_corpus.py`.

The capture spike answered whether the audio can be split. This answers the
question underneath the product: **a note about a meeting you only half
remember is worse than no note if any of it is invented.** Everything below is
built to detect invention rather than to admire fluency.

---

## The result that matters: the worst defect was in the prompt

The unattributed contract used to illustrate agentless phrasing with two
example sentences. Here is what the model wrote for an ICSI research meeting:

```
## Decisions
- The launch date was moved forward.
- Someone is to follow up with the supplier regarding the IBM equipment.
```

Neither `launch` nor `supplier` occurs **once** in that transcript. Both came
out of the instructions. The model had been shown two sentences as a
demonstration of *grammar* and reproduced them as *facts*.

That note was well-formed, named nobody, invented no numbers, and was read in
full — so every check in place at the time passed it. It was caught by grepping
the transcript by hand.

Two things changed:

1. **The examples are gone.** The contract describes the grammar instead. Style
   examples built from content words are indistinguishable from content.
2. **`check_prompt_echo` gates on it.** It fires on words the instructions and
   the notes share while the transcript does not. There is no innocent reason
   for a word to travel that route, and the prompt is a file that will be
   edited again.

The general lesson is not about this prompt. Watching numbers was the wrong
check on its own — **fabricated prose carries no digits.**

---

## Results

`topics` is lexical overlap against QMSum's human-written topic list. Crude, and
treated as crude: it is a coverage smoke test, not a score.

| Meeting | Kind | Mode | Turns | Prompt tokens | Time | Topics | Words |
|---|---|---|---|---|---|---|---|
| ES2004c | AMI, product design | named | 582 | 10 562 | 48 s | 4/5 | 200 |
| ES2004c | | **channel (Me/Them)** | 582 | 10 145 | 105 s | 4/5 | 174 |
| ES2004c | | unattributed | 582 | 9 661 | 44 s | 4/5 | 161 |
| ES2004c | | **bleed simulated** | 1 164 | 18 919 | 127 s | 4/5 | 168 |
| Bmr006 | ICSI, research group | named | 1 365 | 27 530 | 276 s | 4/5 | 270 |
| Bmr006 | | unattributed | 1 365 | 24 202 | 214 s | 3/5 | 205 |
| covid_4 | Committee hearing | named | 276 | 21 884 | 136 s | 2/7 | 252 |
| covid_4 | | unattributed | 276 | 20 189 | 158 s | 1/7 | 268 |

Across all runs: no invented numbers, no prompt echo, and at every
capture-derived level, no fabricated speaker and no implied actor.

**`channel` is in that table because it is the path the README recommends.** A
clean headphone capture measures low bleed, and the spike then writes
`attribution: "channel"` — so Me/Them is the default a real user hits, not an
exotic case. It had been specified and never run; `check_attribution` returned
"does not apply" for it, meaning the contract governing the recommended setup
was enforced by nothing. It now applies at `channel` too, with `Them` forbidden
as an actor and `Me` permitted, because the person holding the microphone is a
real identity and the far side is one undifferentiated audio stream rather than
a person.

The same fix closes a hole on the production path at `none`: a real capture
arrives with its labels already dropped by the spike, so the corpus-derived
speaker list is empty and the name arm of the check had nothing to match. `Me`
and `Them` are now always in the forbidden set.

---

## Bleed destroys the speaker split. It does not destroy the notes.

This is the finding that changes the product, and it points the opposite way
from what `spike/RESULTS.md` implied.

Stripping labels is only half of what a contaminated capture does. When the
microphone hears the speakers, both legs transcribe the same speech, so every
utterance reaches the summarizer **twice** — adjacent, near-identical, with no
label to explain why. The spike measured +0.93 correlation doing exactly this
and printed each sentence once as `Me` and once as `Them`. A summarizer only
ever tested on label-stripped input has been tested against a tidier problem
than the real one.

So `--simulate-bleed` doubles every line as well as dropping the labels. The
notes came out **at full coverage** — 4/5 topics, same as the clean run, with a
correct and complete decision list. Summarization is compression, and the first
thing compression discards is repetition.

That means the `bleed-detected` state in
[`docs/screens-and-states.md`](../docs/screens-and-states.md) should degrade
**attribution only**, not the whole artifact. The honest product behaviour on
speakers is a complete set of notes with no speaker labels — not a warning
banner over a degraded one, and not a refusal.

The transcript is still duplicated and still unpleasant to read directly. The
notes are the thing worth reading, which is the argument for generating them
even in the case the capture spike called worst.

---

## Committee hearings are the failure case

covid_4 covers 1–2 of 7 topics. It is not a long meeting by turn count — 276
turns — but each turn is a long formal statement, and 20 000 tokens of
parliamentary testimony spans far more distinct subjects than a design meeting
of the same size.

The notes it produced were true. They were just a small fraction of what was
discussed, presented with the same confident structure as the complete ones.
Nothing in the output signals the difference, and none of the checks catch it,
because a check for invention cannot detect omission.

Not chased further here. An 8B model was the point of this pass; a larger local
model is the obvious next thing to compare against, and the harness takes
`--model` for exactly that.

---

## What the checks do, and what they cannot do

| Check | Gates? | Catches |
|---|---|---|
| `check_context` | yes | Silent truncation — the server's own prompt token count against the prompt sent |
| `check_attribution` | yes | A speaker named, or an actor implied, at `none` **and at `channel`** |
| `check_numbers` | yes | Figures in the notes that appear nowhere in the transcript |
| `check_prompt_echo` | yes | Content that came from the instructions rather than the meeting |
| `check_owner_grounding` | **no** | At `named`, an item whose owner never said anything like it — advisory |
| `check_grounding` | **no** | Content words absent from the transcript — advisory only |

`check_owner_grounding` closes the level that had nothing watching it. At `none`
and `channel` the checks forbid naming people; at `named` the model is *supposed*
to name them, so no check applied — on the one level where the names belong to
real colleagues. Putting a coworker's name against a commitment they never made
is the worst thing this tool can do, and it was unguarded.

It is advisory because work is routinely assigned *to* someone by someone else,
and the owner may say nothing but "yeah". And it has a real blind spot: it
compares words, so it catches an owner who never discussed the topic and misses
an owner who discussed something adjacent. On the real meeting below, the note
put one attendee down as giving feedback on the project plan when what they
offered was feedback in the first sync meeting. They genuinely said "feedback",
"project" and "plan" — just not about that object. Word overlap cannot see the object of a
verb, and this check does not pretend to.

`check_grounding` stays out of the verdict deliberately. On real notes it
surfaced genuine fabrications (`launch`, `supplier`) alongside innocent
paraphrase (`covered`, `handle`) with nothing in the lexical signal separating
them. Making it a gate would mean either failing good notes or padding the
ignore list until it caught nothing.

**The checks are themselves checked.** `python notes/summarize.py --self-test`
runs all of them against notes with known verdicts, in both directions. Six of
those fixtures are failures these checks actually had:

- A role name used as a topic ("the group discussed market trends, user
  interface, and materials") was reported as a fabricated speaker. AMI's roles
  are *Marketing*, *User Interface*, *Industrial Designer* — all ordinary
  phrases in a meeting about designing a product. **A check that invents a
  fabrication is the same failure the tool exists to prevent, pointed
  backwards.** Names now count only in an attributing position.
- Collective phrasing ("they decided", "the group agreed") was flagged as
  implied attribution. It isn't: bleed destroys *which side spoke*, not the fact
  that a meeting collectively settled something. The line is singular versus
  collective.

---

## Incidental findings

**Ollama's context default would have silently eaten most of the corpus, and
the gate was made to fire before that was claimed.** `num_ctx` defaults to 4096
regardless of the model's real window. Bmr006 needs 27 530 tokens. Running it
deliberately at the default:

```
$ python3 notes/summarize.py notes/corpus/Bmr006.json --num-ctx 4096
  context   TRUNCATED — server read 4096 prompt tokens for a prompt
            estimated at 28279; the tail of the meeting was dropped
```

85% of the meeting discarded, and the notes it produced were well-formed prose
about the opening with nothing marking the difference. This is why the check
gates rather than warns.

That run paid for itself twice. The advisory grounding list jumped from 2 terms
to 12 — truncation does not merely shorten the notes, it pushes the model to
invent. And it exposed a **false positive in the gating prompt-echo check**: the
word "notes" appears in every instruction and every note, so it read as content
that travelled from prompt to output without passing through the transcript.
"note", "notes", "transcript", "meeting" and "speaker" are now register rather
than content. A gating check with a false positive fails good work, which is the
same defect as passing bad work with the sign flipped.

**Temperature 0 is reproducible back-to-back and not across time — the earlier
claim here was wrong.** Two consecutive runs of the same transcript do produce
byte-identical notes, which is what this document originally reported. Running
the same transcript again later, after other work had passed through Ollama, did
not: two action items and all three open questions came out different, including
one run that surfaced a schedule commitment the other never mentioned.

Same input, same model, same temperature, materially different notes. So the
earlier reading was two samples from one warm model, generalised into a property
of the setup. Treat any output difference as signal only when the runs are
adjacent.

**Speed is not a constraint.** 44 s for a 40-minute meeting, 276 s for the
1 365-turn one, on an 8B model on a laptop. Notes are a post-meeting artifact;
nothing here needs to be real-time.

**Naming is not free even when labels are present.** At attribution level
`named`, with reliable speaker labels and an instruction to use them, the model
still wrote mostly agentless notes. At `channel`, where "you agreed to X" is
both permitted and correct, it wrote no second-person attributions at all.
Getting owners onto action items will take more than having the data — which
also means the attribution checks have so far only ever been exercised against a
model that under-attributes. They are controls against a failure this model does
not currently reach for.

---

## A real meeting, from Google Meet

Everything above ran on corpus transcripts. The pipeline was then pointed at a
genuine 37-minute Google Meet call — four colleagues, real ASR output with
crosstalk interleaved mid-sentence, and Gemini's own notes in the same export to
compare against. **The transcript and the notes it produced are not in this
repository and never will be; that meeting belongs to the people in it.** What
is here is `load_meet()`, which parses the format.

It went better than the corpus runs predicted, and it found two defects.

What the notes got right, verified line by line against the transcript rather
than against the model's confidence: the project's purpose, the straw-man
project plan and its correct owner, the data-quality risk, the conflict between
old documents and current features, and — in the runs that caught it — the
"not sooner than 2 months because of security checks" timeline, correctly
attributed. Nothing was invented outright in any run.

What it got wrong is subtler and worth more than the successes:

- **Omission again.** The `named` run missed two commitments Gemini caught: the
  GitHub-usernames request and the weekly sync, both plainly in the transcript.
  The `channel` and bleed-simulated runs caught the sync and missed others. No
  check detects this, which is the same hole covid_4 exposed.
- **Adjacent-object drift.** One attendee was written down as reviewing and
  giving feedback on the project plan; what they offered was feedback in the
  first sync meeting. Every element individually true, the composition wrong.
  This is the failure a proofread survives.

Two checks changed because of it. `check_owner_grounding` exists at all, and
`check_numbers` no longer exempts small integers that carry a unit — the note
line "at least 2 months" was a schedule commitment nobody would be held to by a
check that skipped every integer under eleven. It happened to be true. Nothing
in this harness established that, which is the only part that matters.

---

## The finding this whole harness was built in the wrong direction for

Every gating check here detects **invention**. After four meetings and a dozen
runs, invention barely happened. The only outright fabrication in the entire
evaluation was the one *this file's own prompt* put there.

What happens instead is **omission**, and it happens constantly.

Measured against the action items Google Meet's own notetaker recorded for the
same calls — two real meetings, 37 and 56 minutes — hand-verified line by line
against the transcripts:

| Meeting | Reference items | `llama3.1:8b` | `gemma3:12b` |
|---|---|---|---|
| A — 37 min, 4 attendees | 4 | 2 | 2 |
| B — 56 min, 9 attendees | 6 | 1 | 2 |
| **Total** | **10** | **3** | **4** |

Every one of those ten items was confirmed present in the transcript first, so
these are our omissions rather than the reference's inventions. The clearest
case: one two-word noun phrase naming a document to be sent is said five times
in meeting B and appears in neither of our notes until the 12B run. Two other
commitment phrases are said twice each and are missed by both models.

(The meetings behind these figures are real client calls, so the phrases are
described rather than quoted. Nothing from them — audio, transcript, notes, or
participant names — is in this repository.)

**Roughly a third of the commitments.** On a 56-minute nine-person call, the 8B
model produced three action items where the reference had six, and only one of
its three matched anything in the reference.

Both notes passed every gating check. Both were true. Both were half a meeting,
presented with the structure and confidence of a complete one — which is the
part that matters, because a reader without the transcript cannot tell the
difference.

**Model size did not fix it.** 8B and 12B miss the same count, and interestingly
not the same items: the 12B run recovered a standing Monday checkpoint meeting
that the 8B run dropped entirely, and it is genuinely in the transcript. So the
larger model is not more complete, it is differently incomplete. That is not the
shape of a problem that goes away by scaling up on a laptop.

The honest reading of "are local models good enough": for **not lying**, on this
evidence, yes. For **not leaving most of the commitments on the floor**, no —
and the checks in this file were all pointed at the wrong failure.

Stated as the comparison it actually is: **in this configuration, against a
hosted frontier notetaker, this pipeline is at roughly a third.**

That sentence used to end "and nothing about it is close yet", with a warning
that our own ASR was unmeasured and "can only make the number worse". Both
halves of that turned out to be wrong, and the next section is why. A third is
what one configuration scores, not what the pipeline can do.

One caveat holds in both directions regardless: the reference is another model's
output, not ground truth. Google's notetaker has its own omissions and nothing
here measures those.

---

## Running the same audio through both chains

The recording for meeting B arrived, so the whole comparison could finally be
made properly: one 57-minute call, our capture chain against Google's, ending in
the same six reference commitments. Three arms, changing one thing at a time.
Every figure below is hand-verified against the transcript, because the models'
own recall scores are worthless (see above).

| Arm | Transcript | Labels | `llama3.1:8b` | `gemma3:12b` |
|---|---|---|---|---|
| A | Google's | named | 1/6 | 2/6 |
| B | Google's | stripped | 0/6 | 3/6 |
| C | **ours, from the audio** | none | 0/6 | **4/6** |

**Our speech recognition is not the bottleneck. It is not even a cost.**
`compare_transcripts.py` checks whether the words each commitment depends on
survived, which matters more here than word error rate — a transcript can lose
"um" a hundred times and lose nothing, but lose the one phrase naming a promised
document once and that commitment becomes unwritable. Across all six
commitments, **zero terms present
in Google's transcript were missing from ours.** Identical counts on every row,
at 91% of the word count and 25x realtime on a laptop.

**The surprise is that our transcript is better input than Google's.** Meet buys
speaker labels by cutting turns at every interruption: 43% of its units are three
words or fewer, against 11% of ours, and during crosstalk it emits speaker labels
*inside* another speaker's sentence —

```
Speaker A: Oh, wait. Are you able to share? You should be able Speaker B:
Speaker A: to. Speaker B: to
```

— where Whisper returns "Oh wait, are you able to share? You should be able to."
as one intact sentence. Attribution is paid for with sentence integrity, and for
writing notes the sentences matter more.

So the best result in this whole evaluation is the **fully local end-to-end**
one: our audio, our ASR, no speaker labels, agentless notes. 4 of 6 against
Gemini's 6, on a nine-person hour-long client call.

Two honest limits on that. The effect is **not consistent across models** — the
same changes that took gemma3 from 2/6 to 4/6 took llama3.1 from 1/6 to 0/6, so
this is a property of a configuration, not a law. And it is one meeting. What it
does establish is that the ordering of these arms is not what anyone would have
guessed, and that the remaining gap is entirely in note-writing.

---

## The recall judge has to be calibrated before it is quoted

`check_recall` is the only check here that asks a model instead of counting
strings. That was arrived at the hard way: two lexical versions were written
first, and both were wrong in opposite directions. Scoring against an item's
full content words rated a note **4/4** that never says "GitHub" once, because
"provide", "project", "repository" and the attendees' names appear in every row.
Restricting to each item's unique terms then rejected notes that plainly did
cover the item, because the unique set fills with incidental words like "gain"
and "access".

The gap between "send GitHub usernames" and "Share GitHub Usernames: provide
GitHub usernames to gain access" is semantic. No threshold turns word overlap
into meaning, and tuning one until the fixtures passed would have produced a
number that measured the fixtures.

So a model judges it — and then the judge itself gets tested, because a model's
opinion is not a measurement until it is shown to distinguish the cases:

```
$ python3 notes/summarize.py --validate-judge --model gemma3:12b
  agreement 4/5
```

| Judge | Agreement with known answers |
|---|---|
| `llama3.1:8b` | 3/5 — marks absent items present |
| `gemma3:12b` | 4/5 |

**Neither passes.** Both fail the same fixture, and it is the decisive one: a
note saying "provide access to the project repository" is scored as covering
"share GitHub usernames so access can be granted". That is the same
adjacent-object confusion the notes themselves commit — the judge cannot see it
because the judge has the failure.

Which is exactly why the report never prints a recall score on its own:

```
recall  4/4 — judged by gemma3:12b, not measured; calibrate it with --validate-judge
```

That 4/4 is a model grading its own output with an instrument that failed
calibration. Hand-checking the same notes against the transcript gives 2/4. The
label is doing real work.

On the second meeting it does much more than that. Both models were asked to
score their own notes against the same six reference items:

| Model | Self-judged recall | Hand-verified |
|---|---|---|
| `llama3.1:8b` | 5/6 | 1/6 |
| `gemma3:12b` | 6/6 | 2/6 |

**A local model rates its own notes three to five times better than they are.**
Not a small calibration offset — the 8B model claimed it had captured five of
six commitments while having captured one. Any pipeline that let a model grade
its own output here would report near-perfect recall forever, and every number
in this document would have been decoration.

**A parse failure nearly became a verdict here too.** Asked for `PRESENT`/
`ABSENT`, llama3.1 answered `MENTIONED` / `NOT MENTIONED` — four substantively
reasonable judgements that a `PRESENT|ABSENT` regex scored as zero parsed
answers, which read downstream as "nothing found". The first conclusion drawn
from that was that the model could not follow the format. The model was fine;
the parser was brittle. Negatives are now matched before positives, since "NOT
MENTIONED" contains "MENTIONED", and anything unrecognised is reported as
`NO VERDICT` rather than folded into a count.

---

## Two passes do not fix omission. They move it.

Every finding above says the same thing: what the local models lose is
commitments, not accuracy. A single pass compresses ~8600 words into ~280 — a
30:1 ratio at which dropping things is the expected behaviour. So the obvious fix
is to stop asking for that ratio in one step: extract items from each slice of
the transcript, then consolidate. `--passes 2` does exactly that, with
overlapping slices so a commitment spanning a cut survives in one of them.

It does not work, and the way it fails is more interesting than the fact.

Two meetings, one model (`gemma3:12b`), same transcript and same contract within
each meeting, hand-scored against the rule written *before* the run — a
precaution taken because the previous turn's strict-versus-generous call on a
single item moved a total from 3/6 to 4/6.

| | one pass | two passes |
|---|---|---|
| meeting A (57 min, 6 reference commitments) | **5/6** | 4/6 |
| meeting B (37 min, 4 reference commitments) | 2/4 | **3/4** |
| **total** | **7/10** | **7/10** |
| note length | 18 and 11 bullets | 118 and 61 bullets |
| wall clock | 64 s and 43 s | 344 s and 138 s |

A dead heat on recall, for 5x the output and 4x the time. Worse, the extra
output is not elaboration — the consolidation pass turned **118 extracted items
into 118 bullets**. It merged nothing. The step told "this is a de-duplication
task, not a selection task" performed neither, and the result is a transcript
dump wearing the shape of notes.

**The two arms miss different things, and their union is complete.** Meeting A's
single pass caught a housekeeping commitment about access and a decision about
categorising a data breakdown that the two-pass run lost entirely; the two-pass
run caught an engineering-review commitment the single pass never mentioned. Same
pattern in meeting B. Take the union of the two arms and every meeting scores
**6/6 and 4/4**.

That is the finding worth keeping. The information survives into *some* note
every time; no single strategy collects all of it. That points at ensembling —
run both, union the items — rather than at a better prompt, and it is a different
project from tuning one pass.

Two smaller results fell out of the same run:

- **Local extraction lacks the context to know what matters.** The commitment
  about meeting access was missed by the extraction pass, not lost in the merge —
  it never appeared in the 118 extracted items at all. Reading only the opening
  slice, the model saw housekeeping chatter; reading the whole meeting, it saw an
  action item. Slicing buys a gentler compression ratio and pays for it in
  context.
- **The model judge is worse than its calibration score suggests.** On meeting B
  it reported 4/4 where hand-scoring gives 2/4. On the two-pass note it produced
  output that could not be parsed at all for any of the four items. Recall here
  stays hand-checked.

## What this evaluation structurally cannot tell you

Stated plainly, in the same spirit as `spike/RESULTS.md`:

- **The corpus transcripts are clean.** QMSum is human-corrected. This is now
  closed for one meeting: arm C ran from the audio through our own recogniser,
  and the assumption written here previously — that Meet's recogniser is better
  than local Whisper — did not survive being tested.
- **Turn boundaries still come from a file, not from two legs.** Arm C gets them
  from Whisper's segmentation of a single mixed channel. The spike's merge
  derives them from timestamps across two independently-clocked legs, which is a
  different and worse input than anything measured here.
- **~~Nothing here has run through the capture path.~~ Closed, and it cost
  nothing.** The 57.6-minute recording behind arm C was played back through the
  tap while both legs recorded for 75 minutes. Comparing the system leg against
  arm C's direct decode of the same file holds audio and model constant: the two
  transcripts carried **identical counts** of every commitment term, and the
  capture-path transcript ran 101% of the direct decode's word count. The
  resampling round-trip and the block chunking cost no content. Drift came out
  bounded under ~230 ms/hour — roughly 8x inside typical cross-leg turn spacing,
  though not inside the closest 7% of it. Details and the three unrelated defects
  that run exposed are in [`spike/RESULTS.md`](../spike/RESULTS.md).
- **The mic leg still invalidates `channel`, for a new reason.** That same run
  showed a silent operator leg producing 400 hallucinated turns — 92 of them the
  single line `"Thank you."` — which the merge labelled `Me` because bleed
  measured LOW and the capture kept its labels. So every recall number in this
  file was measured at `none` or `named`, and the `channel` figures here come from
  `as_channel()` on clean corpus text. A real `channel` transcript is dirtier than
  anything measured in this document.
- **n = 3 meetings, one model, one prompt.** Enough to find a fabrication class
  and fix it. Not enough to claim a quality level.
- **Topic coverage is word overlap.** It cannot tell a note that covered a topic
  well from one that mentioned it.
- **Omission is measured, not solved.** `check_recall` finally asks whether
  something true is missing, but it needs a reference list to compare against
  and a judge good enough to compare with. Neither local model passes judge
  calibration, so on this machine recall is currently a model's opinion with a
  warning label, not a number to quote.
- **One meeting with a platform reference.** The recall figures above rest on
  four action items from one 37-minute call. Enough to establish that omission
  is the dominant failure and that 12B does not fix it; nowhere near enough to
  put a percentage on either claim.

The way to close the first two is the capture that was already the next step:
run a real meeting, then point `summarize.py` at `spike/out/transcript.json`.
The spike now writes that file, and derives its attribution level from its own
bleed measurement, so a contaminated capture arrives here as `none` without
anyone having to remember to say so.

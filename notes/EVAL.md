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

### Answered since: the judge passes, and holds on cases it has never seen

Everything above describes a five-fixture calibration that no local model passed.
That is now history, and it was closed without relaxing anything.

Two changes did it. The judge is asked about **one reference item per call**
rather than handed the whole list — on the fixtures that alone is the difference
between 14/16 and 16/16 for `gemma3:12b`, and both items it recovers are absent
ones it had called present, which is the direction that inflates recall. And the
judging prompt was rewritten to pose the adjudication rule directly.

```
$ python3 notes/summarize.py --validate-judge --model gemma3:12b
  agreement 16/16
  control   8/16 for a judge rigged to answer PRESENT — rejected
```

| Judge | Agreement | Verdict |
|---|---|---|
| `gemma3:12b` | 16/16 | passes |
| `llama3.1:latest` | 13/16 | rejected |
| rigged to answer PRESENT | 8/16 | rejected |
| alternating, ignoring the notes | 12/16 | rejected |
| never answers at all | 0/16 | rejected |

**The harness was strengthened, not loosened, and the check for that is
specific:** the fixture that previously failed *both* models — a note saying
"provide access to the project repository" scored as covering "share GitHub
usernames so access can be granted" — is still there, unchanged, and is now
passed. A calibration set that grew from 5 cases to 16 while dropping the one
that used to fail would have been the tell. It kept it. The three sabotaged
judges exist for the same reason: a fixture set that has only ever been run
against judges hoped to be good establishes nothing about its power to reject
one.

**Held out, because 16/16 on your own fixtures is not evidence they were written
before you saw the answers.** Sixteen further cases were written independently
from the same adjudication rule, with content the judge's author never saw, and
scored blind:

```
16 held-out items — 9 present, 7 absent
held-out agreement 15/16
```

A judge fitted to its own calibration set collapses on unseen cases. This one
did not, which is stronger evidence than any assurance about when the fixtures
were authored.

**The single held-out failure names the judge's weak spot, and it is worth
knowing rather than smoothing.** It was an owner substitution — a reference item
naming one person against a note attributing the same commitment to another. The
rule counts that as recalled, because owner errors are a separate defect class
that `check_owner_grounding` already tracks; folding them into recall would
conflate two things this project keeps apart. The judge called it absent. It got
the equivalent case right in the shipped fixtures, so this is inconsistency on
owner substitution rather than a rule it has simply not learned.

**The error direction is the safe one.** Calling a wrong-owner hit "absent"
*under*-reports recall. A judge that inflated instead would let a regression ship
looking clean, which is the failure the whole harness exists to prevent — so
recall figures from this judge should be read as a floor, not a point estimate.

`check_recall` now runs the calibration inline and returns `calibrated` and
`control_rejected` alongside the score, so a recall number cannot be quoted
without its instrument's status travelling with it. That costs sixteen extra
model calls per run, which is the right trade while the judge is new and the
wrong one once it is boring; revisit it when the cost is felt.

### And it still does not transfer to real notes

Everything above is calibration against fixtures. Calibration is not external
validity, and the two come apart here badly enough that **recall on real
meetings still has to be hand-checked.**

`spike/RESULTS.md` records the one published hand-scored result this project
has: against six reference commitments, room-contaminated notes hit 3 and a
clean control hit 2. Running the calibrated judge over those same notes and the
same six items:

| Notes | Hand-scored | Judge | Re-adjudicated here |
|---|---|---|---|
| room-contaminated | 3/6 | **1/6** | ~2.5/6 |
| clean control | 2/6 | **1/6** | ~1.5/6 |

The third column is this document's own re-reading of both notes against the
rule, item by item, and it lands between the other two — so the hand figures
were slightly generous and the judge is badly under-reporting. A judge that
finds one commitment where a careful reader finds two and a half cannot gate
regressions: the changes worth detecting are smaller than its error.

**What it is not.** Each of these was tested and eliminated rather than assumed:

- *Not the item format.* The reference items carry `[Owner] {Title}:`
  scaffolding unlike any fixture. Stripping it changes nothing — 1/6 either way.
- *Not compound items.* Two of the missed items name two objects where the notes
  carry one, which the rule scores as a half. Reducing them to a single object
  does not flip either verdict.
- *Not the owner.* The prompt already says owners do not matter, and removing
  the owner from the item changes nothing.
- *Not sampling noise.* `ollama_chat` pins `temperature: 0.0`, and the same item
  against the same note returns the same verdict seven times out of seven.

**What it is, at least in part.** On a one-line note the judge calls "provide the
measurement plan to the team" ABSENT against "share a measurement plan with
&lt;client&gt;", and PRESENT against "share a measurement plan with the team". The
recipient is doing the work. That is wrong under a rule that turns on the
*object* of the commitment — a recipient is a party to it, exactly like an
owner, and owners are already excluded.

**The obvious fix was tried and rejected on the evidence.** Adding a recipient
clause to the prompt's list of differences that do not matter held the fixtures
at 16/16 — and dropped the contaminated note from 1/6 to 0/6, flipping an
unrelated, clear-cut item ("John will share the brand guidelines document"
against "send the brand guidelines document") from PRESENT to ABSENT. Two
different wordings, the same regression. It was reverted rather than kept for
the fixture score.

That failure is the more useful finding: **a bullet that should have touched only
recipient cases changed a verdict that has no recipient ambiguity at all.** A 12B
judge is sensitive to prompt edits in ways sixteen fixtures cannot detect, which
means fixture agreement is necessary and nowhere near sufficient.

**The structural gap.** Every fixture note is a handful of tidy lines. The real
notes are ~250 words across four headings and fourteen bullets. The calibration
set does not exercise the condition the judge runs in, so passing it says
nothing about the operating case. Closing this needs fixtures built from real
notes — which needs hand-scored real meetings, of which this project has two.
That is the same sample-size wall every recall claim here runs into, and no
amount of prompt work gets around it.

---

## How a commitment is scored as recalled

Every recall figure in this file is hand-checked, which makes the judgement the
instrument — and an instrument calibrated after seeing the results is not one.
This rule was written before the two-pass run below and applied to both arms
unchanged.

A reference commitment counts as **hit** when both hold: the note names the same
object of the commitment (paraphrase and synonyms fine; a category standing in
for the object is not — "share a document" does not hit "share the brand
guidelines"), and it appears *as a commitment*, under Decisions or Action items
or stated in the Summary as something that will happen. A topic raised in
discussion does not hit a commitment to act on it.

The cases that actually came up, resolved in advance:

- **Same object, different verb** — "review X" against a reference item "send X".
  **Miss.** They are different commitments with different owners, and counting
  them together would let any mention of the object score.
- **Right commitment, wrong owner.** **Hit**, recorded separately. Owner errors
  are their own defect class, already measured by `check_owner_grounding`.
- **Commitment split across two bullets.** **Hit** if the bullets together carry
  the object and the commitment.
- **Reference item naming two artefacts, one covered.** **Half.** Scoring it
  whole hides real omission; scoring it a miss hides real recall.
- **Right commitment filed under the wrong heading.** **Hit.** Section placement
  is formatting, not recall.

Scoring goes one reference item at a time across all arms, rather than one arm
end to end, because scoring an arm as a unit invites calibrating to its voice.

**This rule postdates some numbers above.** The earlier arm-C figure of 4/6 on
meeting A and the 5/6 baseline below are the same configuration scored before and
after it existed. The rule is the reason the numbers differ; treat figures from
this section onward as the comparable ones.

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

**The two arms miss different things.** Meeting A's single pass caught a
housekeeping commitment about access and a decision about categorising a data
breakdown that the two-pass run lost entirely; the two-pass run caught an
engineering-review commitment the single pass never mentioned. Same pattern in
meeting B. Scored as a union, the two arms together cover **6/6 and 4/4**.

Read that as a ceiling, not a result. It is a union taken *after* scoring both
arms against the reference — the score an oracle gets for knowing which arm to
believe. A real ensemble would have to merge 118 bullets with 18 and no reference
to guide it, and this same run measured what unguided merging does: 118 items in,
118 bullets out. So the honest statement is that **the information survives into
some arm every time, which bounds what any ensemble could recover** — not that
ensembling is therefore the answer. Whether merging can be made to work without a
reference is untested, and the one measurement here is discouraging.

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

## The prompt was telling it to omit

Two of the four rules at the top of the summarizer used to read:

> If you are not sure something was said, leave it out.
> Prefer omitting a section to padding it.

Those were written when the open question was whether a local model invents
things. It measurably does not. What it does is leave commitments out — the
finding this entire document keeps arriving at — and the instructions were asking
for exactly that. The prompt was tuned against the failure that was feared and
never revisited after the real one was found.

The fix keeps every accuracy rule and stops the accuracy rules from doubling as
permission to write less. "If you are not sure, leave it out" becomes "do not
write anything the transcript does not support" — the same bar on each sentence,
with no invitation to write fewer of them. "Prefer omitting to padding" says what
padding actually is (filler and restatement) and states plainly that it does not
mean dropping something genuinely decided. And one rule was added, aimed at what
the misses had in common:

> List every decision and every commitment, including routine ones — scheduling
> a meeting, sending a file, granting access, following up.

Same transcripts, same contract, same scoring rule, only the rules changed:

| | before | after |
|---|---|---|
| `gemma3:12b` | 7/10 | **8/10** |
| `llama3.1:8b` | 1/10 | **4.5/10** |

**Both models improve, which nothing else in this document has managed.** Every
earlier change moved one model and moved the other the wrong way — attribution
level took gemma 2/6→4/6 while taking llama 1/6→0/6, and two passes took gemma
down and llama's meeting up. This is the first change that survives a second
model.

The 8B model is the striking one. On the 57-minute meeting under the old rules it
scored **zero** — four decisions, three action items, all true, not one of them a
commitment the reference recorded. It was not failing to understand the meeting.
It was doing what it had been told.

**It holds on a corpus it was not tuned on.** The change was made and measured on
two client calls in one domain, which is exactly the situation where a prompt
edit fits the meetings it was written against. Re-run over the three QMSum
meetings — academic and parliamentary, different speakers, different subject
matter, human-written references — at the same `none` contract:

| meeting | words | bullets | topics covered |
|---|---|---|---|
| ES2004c | 7.8k | 21 → 22 | 4/5 → 4/5 |
| covid_4 | 16k | 20 → 19 | 2/7 → 2/7 |
| **Bmr006** | **21k** | **8 → 23** | **4/5 → 5/5** |

No meeting regressed, and the one that moved is the longest — where the
compression the old rules asked for bit hardest. Under the old rules a
21,000-word meeting produced **three action items**; it now produces eleven, and
every one spot-checked against the transcript is grounded in it (the subjects
they name occur 1 to 33 times each). Every run passes attribution, numbers,
prompt-echo and context.

The committee hearing stays at 2/7 either way, which is consistent with the
separate finding above that it fails for a different reason.

Three things worth stating about what this is not:

- **Nothing was traded for it.** All four runs pass every gating check —
  attribution, numbers, prompt echo, context. The two owners the 8B model names
  appear 3 and 15 times in the transcript, so they come from what was said. Notes
  grew from 18 to 21 bullets and 11 to 16, not to the 118 that two passes
  produced.
- **The gained items are the ones the change aimed at.** The clearest is a
  commitment to schedule a recurring sync — administrative, easy to read as not
  worth writing down, and recorded by the reference.
- **One commitment is missed by both models under both prompts**: providing
  usernames so repository access can be granted. The two-pass run caught it. That
  is the ceiling result again — the information reaches some arm, and no single
  configuration collects all of it.

The two-pass measurements above predate this change; both arms there used the old
rules, so that comparison stands on its own terms but its absolute numbers are no
longer the current baseline.

## Where omission happens, and why fixing it there does not work

The two models miss almost disjoint sets of commitments, which is odd enough to
chase. Locating each reference commitment in its transcript explains it:

| commitment | position | mentions | `gemma3:12b` | `llama3.1` |
|---|---|---|---|---|
| access to the recording | 0–1% | repeated | hit | miss |
| categorise the data breakdown | 5% | once | hit | miss |
| share a measurement plan | 50% | once | hit | miss |
| draft a project plan | 76% | once | hit | hit |
| provide usernames for access | **92%** | **once** | **miss** | hit |
| engineering review of a diagram | **95%** | **once** | **miss** | hit |

Both of the 12B model's misses are mentioned exactly once in the final 10%.
Single-mention commitments at 5%, 50% and 76% are all found, so the variable is
position rather than rarity. The 8B model fails the other way round — it misses
early and middle items and catches both late ones. They are not differently
capable; they are differently biased, and that is why their union is complete.

**The information is there and the model can extract it.** Handed only the last
fifth of the same two transcripts, `gemma3:12b` found both commitments it had
just missed. Reading everything is what loses them.

Which makes the fix look obvious: run one extra short pass over the closing fifth
and hand its commitments to the main pass as a checklist. That was built and
measured. **It does not work.**

| | one pass | plus a closing pass |
|---|---|---|
| `gemma3:12b` | **8/10** | 7/10 |
| `llama3.1` | 4.5/10 | 4.5/10 |

Both late commitments were recovered, exactly as designed. Three earlier ones
were lost paying for them — including, on one meeting, the single most
substantial commitment in it, replaced by end-of-meeting logistics phrased as
"someone will have something halfbaked within the week". Reverted; the code is
not in the repository.

That is the third intervention to behave this way. Two passes: relocation.
Room-noise contamination: relocation. A closing pass: relocation. Set against the
one change that did raise the number — deleting the instructions to omit — the
pattern is hard to miss:

> **The model reports a roughly fixed number of commitments. Interventions that
> redirect its attention change which ones fill that budget. The only thing that
> raised the count was changing what it was told to produce.**

Worth holding loosely — it rests on two meetings and one scoring rule, and a
budget that moved once could move again. But it predicts that further attention
plumbing is not where the next gain is, and it is cheap to falsify: any
attention-level change that raises the total on both models refutes it.

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

---

## Claims cite the transcript, and the checker was wrong about whether they did

Measured 2026-07-29 on three corpus meetings with `llama3.1:latest`, labels
stripped. The note format now carries a quote per claim; the *code* locates that
quote and derives the turn index, because asking an 8B model for an index returns a
plausible number and that is the fabrication class the check exists to catch.

**The first figures published from this were wrong, in the under-reporting
direction.** Two regexes decided independently whether a claim was cited: one
required the quote on the line below the claim, the other matched any list item the
first had not. The model collapsed the quote onto the claim's own line on two of the
three meetings, so the first missed, the second swallowed the whole line, and the
claim landed in `uncited` — a bucket that does not fail a run.

| Meeting | Turns | Path | First reported | Re-derived |
|---|---|---|---|---|
| ES2004c | 582 | single pass | 7 verified / 3 unsupported / 1 untestable | unchanged |
| covid_4 | 276 | single pass | 15 unquoted | 4 verified / 4 unsupported / 7 unquoted |
| Bmr006 | 1365 | chunked, 17 slices | 83 unquoted | 33 verified / 41 unsupported / 9 untestable |

**covid_4's run reported PASS while carrying four composed quotes.** That is the
worst consequence and it is not about citations: an aggregate verdict computed from
buckets that disagree about their own coverage will report clean, because the bucket
items fall into is the benign one. The repair is one parser that classifies every
list item exactly once, plus a control asserting the buckets partition the items.
Twelve citation controls passed throughout — every one of them used the layout the
contract asks for, so none of them exercised the layout the model actually produced.

**What the numbers support, and what they do not.** Verified runs between a quarter
and two thirds; it is neither rare nor dependable. No note is uniformly one thing —
all three carry at least two states. Long inputs are *not* simply worse: the
1365-turn chunked run verified 40% against the 582-turn run's 64% and the 276-turn
run's 27%, so length does not order them. An earlier claim in this session that
compliance is "unstable run-to-run" rested partly on a console capture that was
truncated at both ends and cannot be re-measured; what the artifacts do support is
that the model varies its citation **layout** between runs and between meetings.

**Every row above predates the prompt fix below, except one.** The table is the state
the notes were *measured in*, which is what the re-derivation preserves — but the
citation format changed afterwards, and that is the one change able to move all of it.
Re-run on ES2004c under the revised prompt: **8 verified of 10**, ten next-line quotes,
zero collapses, zero bracket echo, zero slot-name echo, in 45s against the earlier
run's minutes. covid_4 and Bmr006 have **not** been re-measured under it, so their rows
describe the old prompt and should not be quoted as current.

**A second prompt-echo, traded for the first.** Illustrating the citation format with
real prose got that prose back as a decision the meeting reached, so the example
became `<angle-bracket placeholders>`. The model then copied the brackets: 83 of 83
Bmr006 claims and 8 of 8 covid_4 claims arrived as `- <the claim>`. Neither check saw
it, because what leaked was punctuation rather than any word, and `check_prompt_echo`
compares content n-grams. The slots are named in capitals now — if those leak, that
existing check catches them by the mechanism it already has. Choosing the failure an
existing check can see beats choosing the one that reads better in the prompt.

**The collapsed reading is now a compatibility reader, not an active layout.** Under
the revised prompt ES2004c produced zero collapsed citations, so if that holds the
path never fires on a new run and stays exercised only by fixtures. It has to stay:
artifacts made before the prompt fix still need it, and all three figures in the table
above were confirmed unchanged by re-running `--recheck` after the reading was bounded.
The consequence worth stating is that its residual risk — two mid-line arrows in a note
carrying no citations at all — will now never be observed in production, so the
fixtures are the only thing standing behind it.

**Re-deriving is part of the artifact contract.** `--recheck` recomputes the citation
result for a `note/1` artifact from the note text and the transcript, with no model
call. Correcting the figures above by re-running would have produced *different
notes*, so the corrected numbers would not have described the notes that were
measured. Only the citation check is recomputed; `numbers`, `grounding` and
`prompt_echo` compare against the rendered prompt and the system message, which the
artifact does not store, so their stored verdicts are carried forward rather than
silently recomputed against a substitute input.

---

## The merge pass repeats itself, and the section headings were the data model

Two findings from asking what the note's four sections are for. Measured 2026-07-29 on
the three corpus meetings.

**The consolidator introduces duplication rather than resolving it.** On Bmr006 (1365
turns, chunked over 17 slices) extraction produced **160 items with one redundant pair**;
consolidating them produced **83 items of which 14 were exact repeats** of an earlier
claim — same text, same quote, same evidence state, checked before the fix was written.
Seven consecutive items reappeared verbatim seven positions later. The single-pass path
produced zero duplicates on either shorter meeting, which is why `dedupe_items` is
applied only where the defect is: adding it to the single-pass path would carry machinery
for a failure that path does not have and would hide it if it ever appeared.

Stripped and counted, the same treatment as the template punctuation — a note listing one
decision twice is simply wrong and has one obvious resolution, but the count is evidence
about the chunked path's reliability and vanishes from the note the moment it is fixed.
It travels in `note/1`'s **provenance** rather than its `checks`, because `--recheck`
recomputes checks from the note text and the note no longer contains the evidence.

**Near-duplicate items are not the cause, which was worth checking before fixing the
wrong layer.** At Jaccard ≥ 0.6 the 160 extracted items contain **4** near-duplicate
pairs. The overlap window exists so a commitment spanning a slice boundary survives in
one of them, and it is doing that job. The repetition is the merge pass on a long list.

**Re-run under the revised prompt, and the duplication was gone.** Same command, same
input, 16 slices: **55 items, zero repeats, zero template punctuation**, in 312s against
the earlier run's 588s. So the caps-slot prompt fixed three things at once — bracket
echo, the note's length, and the repetition — and `dedupe_items` fired on nothing. It
stays as regression insurance: the defect was real and measured, and nothing guarantees
a model that stopped repeating itself keeps not doing it.

**It does not help the artifacts that carry the defect, and an earlier draft of this
section claimed it did.** `dedupe_items` runs in `summarize_chunked`; `recheck` never
calls it, by the deliberate separation that keeps re-derivation from rewriting notes. So
pre-fix artifacts are exactly the case it cannot reach. The compatibility-reader argument
belongs to the *collapsed-layout* path, which really is on the recheck route through
`_parse_claims`.

**Two numbers, because they are two facts.** `provenance.duplicates_removed` counts what
generation excised, and is `null` on the single-pass path rather than 0 — that path cannot
produce the number, and recording a zero would assert a measurement never taken, which is
the ambiguity refused for `transform`. `checks.citations.repeats` counts repeats *still
present*, runs on both paths and on `--recheck`, and is what makes the chunked-only
placement safe: a single-pass regression stays visible instead of being reported as a
clean zero by a field that path never fills.

| | old prompt | revised prompt |
|---|---|---|
| items | 83 | 55 |
| exact repeats | 14 | 0 |
| verified | 33 (40%) | 20 (36%) |
| template punctuation | 83 of 83 | 0 |
| layout | collapsed | collapsed |

**What it did not fix: the layout, or the verification rate.** Quotes still arrive on the
claim's own line rather than below it, and roughly a third verify either way.

**And it traded one leak for another — the third in a row.** Specifying the citation
format by example has now leaked three different things into the notes: real prose from
the first example, came back as a decision the meeting reached; angle brackets from the
second, on 83 of 83 claims; and now a **trailing pipe on all 55**, because the
consolidator holds both the extraction contract (which separates an item from its
evidence with a pipe) and the note contract (which uses a blockquote), and emitted
`claim | > quote` — keeping one separator and adding the other.

The lesson is not that a fourth example will be the right one. **A model given a format
template copies the template's punctuation**, so the parser has to tolerate the family
and the claim text has to be cleaned mechanically rather than asked for cleanly. Both are
now in `_parse_claims`, and each note records which `layout` it used so run-to-run
variation is a field rather than something a person has to eyeball.

**The count is trustworthy now and still an order of magnitude off.** 55 real items
against a human reference that segments the same meeting into **5** subjects. So
duplication was part of the problem and not the problem.

**The mislabelling claim is weaker than it was and is stated at its real strength.** An
earlier draft argued from 44 entries in a Decisions section being implausible for a
research meeting; the re-run gives **14**, which is not implausible, and the sentence was
carried forward with the number swapped — a conclusion surviving a correction that had
undercut it. Read instead of counted, about six of the 14 are decisions ("Anonymize
transcript but not audio", "Public release should be same as licensed one") and the rest
are aspirations ("Have fair amount of data for same meeting"), ideas ("Try summarization
of meetings"), assertions someone made ("Don't need speech signal for summarization"), or
descriptions of what the project already does ("Record people and make audio
recordings").

**That is a reading, not a measurement**, and the distinction matters because this file's
whole discipline is not accepting one for the other. The measurement exists and has not
been run: `check_recall`'s judge could be pointed at "is this entry a decision the
meeting settled" the same way it is pointed at commitment recall. Until it is, the
candidate-C decision rests on its other three legs, none of which involve this — DP-4, no
extra model capability, and a discard that stopped.

**And the sections were the data model.** The extraction pass labels every item DECISION,
ACTION or QUESTION; the consolidator turns the label into a markdown heading; by the time
a `note/1` artifact existed the label survived only as *which section a claim sat under*.
Every claim now carries `type`, recovered from its heading, with an unrecognised heading
keeping its own words rather than being forced into one of the three. Nothing new is
asked of the model — this is a discard that stopped. `docs/journeys.md` records the three
candidate structures and why sections became a rendering.

---

## One of nineteen entries under "Decisions" is a decision the meeting settled

The measurement the previous section named as owed. Run 2026-07-29 with `--measure-settlement`.

**It is possible only because the citations landed.** A claim's evidence is located in
the transcript by code, so "is this filed correctly" stops needing a human reference and
becomes a question about words already verified as said. Only `verified` claims can be
measured — an `unsupported` claim's quote was composed, so judging it would measure the
model's invention rather than the meeting. That is 19 of the 28 Decisions entries across
the three meetings.

**Result: 1 of 19.** The eighteen negatives cite proposals ("rather we should have
different meetings by the same group but hopefully…"), hedges ("I think that when we do
that world release, it should be the same"), commentary ("which is really what makes this
corpus powerful"), descriptions of a design under discussion ("On the bottom we were
gonna have the rubber…"), a bare fragment ("non-English speaking countries"), and one
trailing off mid-thought ("so that we can, uh I don't know").

**The one positive is contestable, and it is the whole numerator, so it is printed
rather than summarised.** "Anonymize transcript but not audio", turn 1297: *everywhere
they said "Jose" that you could replace it with "speaker-seven"*. **A reading of this
record disagrees with the judge** — "that you could replace it with" states a
possibility, which the judge's own rule lists under NOT settled. The figure above is
what the calibrated instrument returned and is reported as such; a calibrated instrument
is not an oracle, and one contested entry out of nineteen is inside the noise of a single
judgement. The defensible form of the finding is **at most 1 of 19**, and the direction
does not change either way.

An earlier version of the report printed quotes only for the negatives, which made the
single entry a reader most needs to check the one entry they could not see.

**A distinct failure mode in covid_4, worth naming separately.** All four of its measured
entries cite petitions being *read into the record* — "The petitioners call upon the
Government of Canada to…". Those are not decisions the meeting reached and not proposals
either; they are the contents of documents being presented. A section named Decisions
gave the model nowhere else to put them.

### The calibration nearly certified a wrong number, and that is the larger finding

The judge was calibrated first, and the fixtures **as originally written passed
`llama3.1` at 12/12 with the rigged control rejected.** Pointed at the real notes it
returned **0 of 19** — a tidier, stronger result than the truth, produced by an
instrument that had been shown to work.

It was wrong for a reason the fixtures could not see: every settled example was a clean
sentence, and real transcript speech is disfluent. `llama3.1` reads hesitation as
uncertainty and answers NO to it. Adding three disfluent-but-settled fixtures ("yeah um
okay do that then", "we'll we'll just go with plastic, uh, for the body") dropped it to
11/14, and one prompt repair — *hesitation is not disagreement; judge what the words land
on, not how fluently they arrive* — recovered only 12/14. It still fails the
self-repetition cases, so it is not the judge for this. `gemma3:12b` scores **14/14** with
the rigged control rejected at 7/14, and produced the figure above.

**That 14/14 certifies `gemma3:12b` on this question and nothing else.** This file now
holds two judge calibrations for two different tasks, and which model passes differs by
task — a score recorded a few sections from the recall calibration is not a general
endorsement of the model. Each calibration licenses one judge, on one question, against
one fixture set.

**Third instance of one shape this session, so it is a rule and not an anecdote:
fixtures drawn from the ideal case certify an instrument that will meet the real case.**
The citation controls all used the layout the contract asks for rather than the one the
model produces, and reported 41 real citations as zero. The claim-state fixtures used the
clean multi-line form for the same reason. And here a clean calibration set would have
published 0-of-19. In each case the check passed, the control was rejected, and the
instrument was still measuring the wrong thing — because the fixture author and the
format author were the same person.

**Sample is 19 entries across 3 meetings and one judge.** It bounds a claim about this
taxonomy; it does not establish a rate. What it is sufficient for is the conclusion
`docs/journeys.md` draws — that a section named Decisions collects things the meeting did
not decide — and that conclusion no longer rests on a reading.

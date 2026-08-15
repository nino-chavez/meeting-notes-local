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

That means a `bleed-detected` result should degrade **attribution only**, not
the whole artifact. The honest product behaviour on
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
attached a participant to a commitment whose object was not the one they had
spoken about — they had discussed a neighbouring object, so every content word
the check compares was genuinely present. Word overlap cannot see the object of a
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

## A real meeting, outside the corpus

Everything above ran on corpus transcripts. The pipeline was then pointed at a
real private call — hosted-platform ASR output with crosstalk interleaved
mid-sentence, and the platform notetaker's own notes in the same export to
compare against. **The transcript and the notes it produced are not in this
repository and never will be; that meeting belongs to the people in it.** What
is here is `load_meet()`, which parses the format. The call's participants,
subject matter and duration are withheld throughout this document; what is
reported is the pipeline's behaviour on it.

It went better than the corpus runs predicted, and it found two defects.

What the notes got right was verified line by line against the transcript rather
than against the model's confidence: the substantive topics, an owner correctly
attached to the commitment that was theirs, a stated risk, and — in the runs that
caught it — a schedule commitment, correctly attributed. The topics themselves
are withheld. Nothing was invented outright in any run.

What it got wrong is subtler and worth more than the successes:

- **Omission again.** The `named` run missed two commitments the reference
  notetaker caught, both plainly in the transcript. The `channel` and
  bleed-simulated runs caught one of them and missed others. No check detects
  this, which is the same hole covid_4 exposed.
- **Adjacent-object drift.** A participant was written down as having committed
  to act on one object when what they had actually spoken about was a
  neighbouring one. Every element individually true, the composition wrong.
  This is the failure a proofread survives.

Two checks changed because of it. `check_owner_grounding` exists at all, and
`check_numbers` no longer exempts small integers that carry a unit — a note line
carrying a small integer and a unit of time was a schedule commitment nobody
would be held to by a check that skipped every integer under eleven. It happened
to be true. Nothing in this harness established that, which is the only part
that matters.

---

## The finding this whole harness was built in the wrong direction for

Every gating check here detects **invention**. After four meetings and a dozen
runs, invention barely happened. The only outright fabrication in the entire
evaluation was the one *this file's own prompt* put there.

What happens instead is **omission**, and it happens constantly.

Measured against the action items the hosted platform's own notetaker recorded
for the same calls — two real meetings, the second roughly half again as long as
the first — hand-verified line by line against the transcripts:

| Meeting | Reference items | `llama3.1:8b` | `gemma3:12b` |
|---|---|---|---|
| A — shorter call | 4 | 2 | 2 |
| B — longer call | 6 | 1 | 2 |
| **Total** | **10** | **3** | **4** |

Every one of those ten items was confirmed present in the transcript first, so
these are our omissions rather than the reference's inventions. The clearest
case: one two-word noun phrase naming a document to be sent is said five times
in meeting B and appears in neither of our notes until the 12B run. Two other
commitment phrases are said twice each and are missed by both models.

(The meetings behind these figures are real client calls, so the phrases are
described rather than quoted. Nothing from them — audio, transcript, notes, or
participant names — is in this repository.)

**Roughly a third of the commitments.** On the longer call, the 8B model
produced three action items where the reference had six, and only one of its
three matched anything in the reference.

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
output, not ground truth. The hosted notetaker has its own omissions and nothing
here measures those.

---

## Running the same audio through both chains

The recording for meeting B arrived, so the whole comparison could finally be
made properly: one call, our capture chain against the hosted platform's, ending
in the same six reference commitments. Three arms, changing one thing at a time.
Every figure below is hand-verified against the transcript, because the models'
own recall scores are worthless (see above).

| Arm | Transcript | Labels | `llama3.1:8b` | `gemma3:12b` |
|---|---|---|---|---|
| A | the platform's | named | 1/6 | 2/6 |
| B | the platform's | stripped | 0/6 | 3/6 |
| C | **ours, from the audio** | none | 0/6 | **4/6** |

**Our speech recognition is not the bottleneck. It is not even a cost.**
`compare_transcripts.py` checks whether the words each commitment depends on
survived, which matters more here than word error rate — a transcript can lose
"um" a hundred times and lose nothing, but lose the one phrase naming a promised
document once and that commitment becomes unwritable. Across all six
commitments, **zero terms present
in the platform's transcript were missing from ours.** Identical counts on every
row, at 91% of the word count and 25x realtime on a laptop.

**The surprise is that our transcript is better input than the platform's.** It
buys speaker labels by cutting turns at every interruption: 43% of its units are
three words or fewer, against 11% of ours, and during crosstalk it emits speaker
labels *inside* another speaker's sentence — in the case we hit, splitting a
single speaker's two-sentence utterance across four interleaved label segments,
with its final word landing under two different speakers. Whisper returns that
same utterance as one intact sentence. (The utterance itself is from a private
call and is not reproduced here.) Attribution is paid for with sentence integrity, and for writing notes the
sentences matter more.

So the best result in this whole evaluation is the **fully local end-to-end**
one: our audio, our ASR, no speaker labels, agentless notes. 4 of 6 against the
reference notetaker's 6, on the longer client call.

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
full content words rated a note **4/4** that never names the item's distinctive
object at all, because the item's generic words — and the participants' names —
appear in every row. Restricting to each item's unique terms then rejected notes
that plainly did cover the item, because the unique set fills with incidental
words.

The gap between a reference item and a note line that genuinely covers it is
semantic: the two can share almost every content word and still name different
objects, or share almost none and name the same one. No threshold turns word
overlap into meaning, and tuning one until the fixtures passed would have
produced a number that measured the fixtures.

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
note describing the *outcome* of a commitment is scored as covering the
commitment to perform the specific step that produces it, though the two name
different objects. That is the same adjacent-object confusion the notes
themselves commit — the judge cannot see it because the judge has the failure.

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
specific:** the fixture that previously failed *both* models — the
adjacent-object case described above, where a note naming the *outcome* of a
commitment was scored as covering the commitment to perform the step that
produces it — is still there, unchanged, and is now passed. A calibration set that grew from 5 cases to 16 while dropping the one
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

**What it is, at least in part.** Holding a one-line note fixed and changing only
the *recipient* named in the reference item flips the judge's verdict on it
between ABSENT and PRESENT. The recipient is doing the work. That is wrong under
a rule that turns on the *object* of the commitment — a recipient is a party to
it, exactly like an owner, and owners are already excluded. (The item is from a
private call; the wording is withheld.)

**The obvious fix was tried and rejected on the evidence.** Adding a recipient
clause to the prompt's list of differences that do not matter held the fixtures
at 16/16 — and dropped the contaminated note from 1/6 to 0/6, flipping an
unrelated, clear-cut item from PRESENT to ABSENT — one with no recipient in it
at all, where the note and the reference named the same object in near-identical
words. Two different wordings of the clause, the same regression. It was
reverted rather than kept for the fixture score.

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
for the object is not — "share a document" does not hit a commitment to share one
specific named document), and it appears *as a commitment*, under Decisions or Action items
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
the longer meeting and the 5/6 baseline below are the same configuration scored before and
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
| longer meeting (6 reference commitments) | **5/6** | 4/6 |
| shorter meeting (4 reference commitments) | 2/4 | **3/4** |
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

The 8B model is the striking one. On the longer meeting under the old rules it
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
- **The gained items are the ones the change aimed at.** The clearest is an
  administrative scheduling commitment — easy to read as not worth writing down,
  and recorded by the reference.
- **One commitment is missed by both models under both prompts.** The two-pass
  run caught it. That is the ceiling result again — the information reaches some
  arm, and no single configuration collects all of it.

The two-pass measurements above predate this change; both arms there used the old
rules, so that comparison stands on its own terms but its absolute numbers are no
longer the current baseline.

## Where omission happens, and why fixing it there does not work

The two models miss almost disjoint sets of commitments, which is odd enough to
chase. Locating each reference commitment in its transcript explains it:

The six commitments are the reference items from a private call, so they are
identified here by position rather than by what they were:

| commitment | position | mentions | `gemma3:12b` | `llama3.1` |
|---|---|---|---|---|
| 1 | 0–1% | repeated | hit | miss |
| 2 | 5% | once | hit | miss |
| 3 | 50% | once | hit | miss |
| 4 | 76% | once | hit | hit |
| 5 | **92%** | **once** | **miss** | hit |
| 6 | **95%** | **once** | **miss** | hit |

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
substantial commitment in it, replaced by a vague end-of-meeting logistics item
the model had written in its place. Reverted; the code is not in the repository.

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
  nothing.** The recording behind arm C was played back through the
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
  four action items from a single call. Enough to establish that omission
  is the dominant failure and that 12B does not fix it; nowhere near enough to
  put a percentage on either claim.

The way to close the first two is the capture that was already the next step:
run a real meeting, then point `summarize.py` at that session's transcript, for
example `~/meeting-smoke/transcript.json`. The spike writes it inside the new
capture directory chosen for that meeting, and derives its attribution level from
its own bleed measurement, so a contaminated capture arrives here as `none`
without anyone having to remember to say so.

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
asked of the model — this is a discard that stopped. Sections are a rendering of
typed claims, not a model decision.

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
that a section named Decisions can collect things the meeting did not decide —
and that conclusion no longer rests on a reading.

---

## "Verified" was answering a question nothing asked: 6 of 31

Run 2026-07-29 with `--measure-support`, judge `gemma3:12b`, calibrated 14/14 against a
rigged control it rejects at 6/14.

**The defect first, because it was shipped.** The citation check locates a quote in the
transcript and the artifact called that state `verified`, which the surface drew with a
green tick. Locating a quote establishes that the words were said at a turn. It
establishes nothing about whether they bear on the claim, and one action item — "Burn
extra CD-ROMs for meeting attendees" — cites turn 307, *"You know, I personally would not
want a CD of my meeting"*, checked against the transcript around it. Located speech
arguing the opposite of its own claim, presented as verified.

Renamed: `verified` → **`located`**, `unsupported` → **`composed`**. The second was
overstating in the other direction — it meant the narrow, specific thing that the words
are not in the transcript at all, while its name laid claim to the support question. Both
names are now what the check actually establishes.

**Then the measurement. 6 of 31 located quotes support the claim they are attached to.**

| kind | supports | of |
|---|---|---|
| decision | 5 | 19 |
| question | 1 | 4 |
| action | **0** | 8 |

Three failure modes, and only the third is what a reader would guess:

- **Contradiction.** The CD-ROM case. The words argue against the claim.
- **Unrelated.** "Offer professors and senior doctoral students…" cites *"talking about
  the kind of thing that you were just talking about"*; "Get more regular meetings…"
  cites *"just because it would be very hard to process the data in all senses"*. Neither
  quote carries any content about its claim.
- **Weaker than claimed.** "Get a DAT machine" cites *"we could just get a DAT
  machine"*; "Write down error message" cites *"maybe we should write it down"*. Real
  speech, on topic, proposing rather than committing.

**This retires the settlement measurement rather than sitting beside it.** "Do these words
show something settled" is what "do these words support DECISION: X" answers when the
claim's type is in front of the judge, and two instruments answering overlapping questions
is the shape this file keeps repairing. The earlier figure — at most 1 of 19 Decisions
entries settled — stands as a recorded finding; the support judge is the instrument going
forward, and the disfluent fixtures that made the settlement calibration worth anything
migrated into it.

**Calibration needed a third failure class, which the disfluency lesson predicted.**
`gemma3:12b` first scored 12/14, failing both cases where topical relevance or an opinion
about what should happen was accepted as supporting a DECISION. Naming those two
explicitly in the prompt — being on the same topic is not support; an opinion about what
should happen is not a decision — took it to 14/14. A fixture set covering only the
weaker-than-claimed mode would have certified a judge blind to contradiction, which is
the mode that makes a note false rather than thin.

**Consequence for the surface, which is why this is not only a record.** `located` no
longer takes `semantic-success`. Success is a verdict; this is not one, and a green tick
on a state that means "the words exist" told the reader something had passed when four
fifths of the time nothing had. It takes `semantic-info`, and success stays unused until
something earns it.

**31 claims, 3 meetings, one judge.** The per-kind rows are shown so the split is visible,
not so a rate can be read off 4 questions or 8 actions.

**The verdicts are written into the artifact, so the surface can stop implying more than
was checked.** `--measure-support` records them under `support`, content-addressed on
claim and quote rather than keyed by position — `recheck` rebuilds `claims` from the
citation buckets, so a verdict stored on a claim would be dropped the next time it ran,
and `recheck` now reports when stored verdicts and located claims have parted company. A
located claim on a note that has not been measured says so in those words rather than
looking clean.

### What the corpus has left to give

This is the fourth measurement in a row to find the notes' *content* failing rather than
their presentation: sections are not the model's to choose, `Decisions` mostly does not
hold decisions, and most located evidence does not support its claim. Every one was found
by inspecting artifacts, and this file's own boundary has not moved — a corpus can show
that a note is wrong and cannot show whether a note is *useful to the person who was in
the meeting*.

What only the dogfood run settles: whether a note about the operator's own meeting is
worth reading at all; whether the claims that fail these checks are ones he would have
wanted; whether 55 items on a 75-minute call is thoroughness or noise; and whether the
`located`/`composed` distinction changes what he trusts. Those are all questions about a
reader, and the corpus has no reader in it.

---

## A fourth bucket, and what it should and should not fix (written before the run)

Four measurements found the notes' content wrong and none attempted a repair. This is
the first repair, and its expected effect is recorded **before** it ran, because twice in
this file's history a conclusion has survived a figure that undercut it. A prediction
written afterwards is not a prediction.

**The diagnosis.** Classifying all 25 non-supporting cases from the 6-of-31 measurement:

| failure | count | what it looks like |
|---|---|---|
| **overstatement** | 11 | quote is apt, claim drops its hedge — "Get a DAT machine" from *"we could just get a DAT machine"* |
| mis-selection | 9 | quote does not bear on the claim — "Offer professors and senior doctoral students" from *"talking about the kind of thing that you were just talking about"* |
| category error | 4 | covid_4's petitions read into the record, filed as Decisions |
| contradiction | 1 | *"I personally would not want a CD of my meeting"* under "Burn extra CD-ROMs for meeting attendees" |

**So the largest class is the model having nowhere honest to put what it found.** Given
Decisions, Action items and Open questions, a real quote saying "maybe we should X" has
to become a decision, a commitment, or nothing. There was no bucket for *raised and not
agreed*, and 11 items were forced up a level to fit.

**The repair: a `Proposed` section**, with the test stated in the prompt — words that
hedge, suggest or ask make an item Proposed even when the idea is good and even when it
plainly should have been agreed, and a meeting that settled little correctly produces a
note that is mostly Proposed.

**Predicted effect, and its ceiling.** Overstatement (11) should move, and the petitions
(4) may — a petition is a request, which is what Proposed is for, but that is reasoning
about a label and the judge decides it, so it is not predicted either way. Mis-selection
(9) and contradiction (1) **cannot** move: nothing about a new label changes a model
attaching an unrelated quote. **Expected 17 of 31 supported, up to 21 if the petitions
land in Proposed.** A result well above 21 means something other than the new bucket
changed, and that would need explaining rather than celebrating.

**Two other candidates, developed and not chosen yet.** *Invert the generation* — have
the model find turns where something was settled and write the claim from those words,
so a claim cannot drift from evidence it was derived from. That is the only one of the
three that addresses mis-selection. And *gate at check time* — run the support judge
inside the pipeline and drop or mark failing items, which costs a model call per item
with a second model and trades recall for precision.

**Why the fourth bucket goes first, and it is not that it is cheaper.** Shipping it
alongside the inverted generation would make the next measurement uninterpretable — two
changes addressing different failure classes, one number, no way to attribute the
movement. Sequencing here buys attribution, which is the campsite carve-out's own reason
rather than an appeal to effort.

**One note on circularity, since the generator and the checker now share a rule.** The
prompt states the hedge test and the support judge enforces it; that is the intended
relationship — a checker verifying the generator honoured a contract. The protection that
matters is that `SUPPORT_FIXTURES` are synthetic and drawn from no corpus meeting, so the
judge's calibration is independent of the items being measured. That still holds after
adding the two `PROPOSAL` fixtures, which cover both directions: hedged words support a
proposal claim, and words that settle something do not.

---

## The fourth separator, and the third time a blind spot hid failures in a benign bucket

Adding the `Proposed` section changed how the consolidator formats citations, and the
parser could not read the new shape. Measured 2026-07-29.

**The note reported 93 items carrying no quote. It carried 93 quotes.** The consolidator
stopped converting the extraction format and passed it straight through as
`claim | quote` — zero `>` characters in the whole note. `_SAME_LINE` looked only for
`>`, so every item fell through to `uncited`, which does not fail a run.

Read with the pipe accepted: **24 located, 56 composed, 13 untestable**, and the run's
verdict moved `passed: true` → `false`. So the blind spot was not merely under-counting
evidence — **it was hiding 56 fabricated quotes in the one bucket that lets a run pass.**

**Third instance, same structure, three different characters.** Next-line-only reported
41 real citations as absent. Then the collapsed `>` form. Now the pipe. Each time the
parser knew one shape, the model produced another, and the items landed in `uncited` —
benign by design, because a model ignoring a format instruction is a prompt problem. The
design was right and the blast radius was not: a bucket that cannot fail a run is where
undetected failures accumulate. `layout` and `separator` are recorded per note now, so
which shape a run produced is a field rather than something a person has to notice.

The pipe was always in the template. `QUOTE_FROM_ITEMS` tells the consolidator that
"every item you were given ends with a pipe", so the rule this file already recorded —
a model given a format template copies the template's punctuation — predicted this
separator specifically, and the parser was not updated to match.

**A second effect of the new section, unpredicted and not a formatting problem.** In
`Proposed`, the consolidator **swapped claim and quote**: extraction produced
`ACTION: write down error message next time it occurs | maybe we should write it down`
and the note reads `- Maybe we should write it down | write down error message next time
it occurs`. The hedged speech became the claim and the claim became the evidence. That is
defensible as a reading — the proposal *is* "maybe we should write it down" — and it
breaks the contract that a claim is a statement and a quote is what was said.

### The prediction was ill-posed, which is worth more than whether it was right

`633ef5a` predicted 17 of 31 supported, up to 21. **That prediction assumed a fixed claim
set**, and the repair changes which claims get extracted at all: ES2004c went from 11
claims to 17, covid_4 from 15 to 8, Bmr006 from 55 to 93. The denominator moved, so
"17 of 31" cannot be compared against anything the repair produced.

Pre-registering was still the right instinct and the flaw is in the quantity chosen, not
the practice. A prediction about a *rate* would have survived a changing denominator; one
about a count did not. Recorded here rather than quietly swapped for whatever the new
numbers support, which is the failure mode this file has already had twice.

### Result: the support rate roughly doubled, and the new bucket is the best-supported kind

| | before `Proposed` | after |
|---|---|---|
| located claims | 31 | 42 |
| **support rate** | **6 (19%)** | **17 (40%)** |
| supported / all claims | 6 of 81 (7%) | 17 of 118 (14%) |
| decision | 5 of 19 (26%) | 7 of 17 (41%) |
| action | **0 of 8** | 3 of 12 (25%) |
| question | 1 of 4 | 2 of 6 (33%) |
| **proposal** | — | **5 of 7 (71%)** |

**`Proposed` is the best-supported kind in the note, by a wide margin.** That is the
diagnosis confirming itself: the model was finding hedged speech all along, and given a
bucket whose contract matches what it found, the evidence and the claim agree. Decisions
and actions both improved as the overstated items moved out from under them — action
items went from nothing supported to a quarter.

**Both framings agree, which matters because the denominator moved.** Support per located
claim went 19% → 40%; support per claim in the whole note went 7% → 14%. The note also
got 46% longer, so the repair did not buy precision by writing less.

**The prediction overestimated, read as a rate.** `633ef5a` predicted 17 of 31 — 55% —
and the measured rate is 40%. It was ill-posed as a count for the reason recorded above,
but converting it charitably to a rate still leaves it optimistic by a third, and the
numerator landing on 17 is coincidence rather than accuracy. The most likely reason is
that the repair extracts *more* marginal claims as well as re-filing overstated ones,
which the prediction did not account for.

**What is still broken, and it is what the prediction said could not move.**
Mis-selection and contradiction are untouched by a new label, so the remaining 25
unsupported claims are dominated by quotes that do not bear on their claim. That is what
the second candidate addresses — inverting the generation so a claim is written *from* the
turn it cites rather than matched to one afterwards — and it is the next repair, not a
measurement.

## Repair 2: the quote is written before the claim

`Proposed` was a new label. This is a change to the order the model generates in, which
is the mechanism the diagnosis actually pointed at.

A model generates left to right, so whichever field it writes first is the one the second
is conditioned on. The extraction contract asked for `ACTION: <claim> | <words>`, which
has the model settle on a claim and then go looking for words to justify one it has
already committed to. Reversed — `<words> | ACTION: <claim>` — the claim can only be a
reading of words it has already copied down.

### The disaggregated baseline, which is not what the aggregate said

| | claims | located | supported | composed |
|---|---|---|---|---|
| Bmr006 (chunked) | 93 | 24 | 8 (33%) | **56 (60%)** |
| ES2004c (single-pass) | 17 | 11 | 4 (36%) | 2 |
| covid_4 (single-pass) | 8 | 7 | 5 (71%) | 1 |

**Bmr006 carries 56 of the 59 composed quotes in the corpus.** The aggregate "40% of
located claims are supported" was hiding the larger failure, because a composed quote
never reaches the support judge at all — it is excluded from the denominator the rate is
computed over. Sixty per cent of the longest meeting's claims cite words that are not in
the transcript, and the support rate cannot see any of them.

This change touches only the chunked path, so **Bmr006 is the whole experiment**. The two
single-pass meetings run unchanged code at `temperature: 0.0` and should return the same
notes; that is a smoke test, not a control, and it carries no information about the
change. Single-pass inversion is deliberately not attempted here: the note *is* that
path's raw output, so inverting it means deciding whether the markdown becomes a
rendering of the artifact rather than the model's own text, and that is a separate
question from this one.

### Two changes ship together, because the first forces the second

`PROPOSAL` is added to the extraction contract in the same commit. Not scope creep, and
not a second repair: the extraction pass currently emits 68 ACTION, 72 DECISION, 20
QUESTION and **zero PROPOSAL** — all 13 of Bmr006's proposals came from the consolidator
re-filing them downstream. A model that reads hedged words *first* and is offered only
DECISION, ACTION and QUESTION has no truthful line to write, so inverting without the
label would build a prompt that requires overstatement.

They are separable in the measurement even though not in the change. The label can only
move items *out* of decision and action, never into them, so **the support rate restricted
to decision and action claims is a number the label cannot inflate.** It is reported
alongside the aggregate.

### Registered before the run, as rates, with the absolutes that would undercut them

1. **Composed falls from 60% to under 30% of Bmr006's claims.** The largest predicted
   effect, and it is not about generation order — it is `QUOTE_FROM_ITEMS` naming which
   side of the pipe holds spoken words. The old wording said only "carry those words
   across", and the consolidator picked the wrong side often enough to invent 56 quotes.
2. **Support among located claims rises from 33% to between 45% and 60%**, and the
   absolute count rises above 8. Both, or the result is a smaller note rather than a
   better one.
3. **Claim count may fall,** because quote-first means the model can only write what it
   found words for. Reported per meeting either way. A rate rise at 60 claims is a
   different finding from the same rate at 93.
4. **Mis-selection and contradiction shrink; overstatement falls via the label, not the
   order.** "we could just get a DAT machine" supports "ACTION: Get a DAT machine" in
   either order — only `PROPOSAL` touches that one. An aggregate that moves with
   mis-selection flat means something other than the stated mechanism fired.
5. **The order the model actually used is the gate on all of the above.** `report` now
   prints it. If most lines come back claim-first, the inversion did not happen and
   nothing below that line is evidence about inversion.

### The inversion is free where it belongs and expensive one stage later

The extraction pass complied completely: **227 items, every one of them quote-first,
none dropped**, against 160 items in the old order. The label mix moved as far as the
order did — 81 PROPOSAL where the contract had previously made 0 possible, and DECISION
falling from 72 to 45. A model that reads the words first files far less of what it hears
as settled.

The merge then threw the evidence away. **86 note items carrying zero quotes**, where the
same pass on claim-first input had produced 93 items all carrying one.

The cause is not the instruction, it is the shape of the job. Feeding the consolidator
`<words> | LABEL: <claim>` while asking it to emit the claim on one line and the words
on the next makes every one of 227 items a transposition performed during a merge. On
claim-first input the same pass is close to a copy. An 8B model given the transposition
dropped the harder half of each pair rather than moving it.

So `summarize_chunked` normalises between the stages: the model still *writes*
quote-first, which is where the order decides what the claim is conditioned on, and the
consolidator is handed the order it has to emit. The two orders in one pipeline are the
point rather than an inconsistency.

**This is the second time a repair to one pass silently broke the contract of the next**,
and both times the break landed in `uncited` — the bucket that does not fail a run. The
first was `QUOTE_FROM_TRANSCRIPT` being appended to a shared contract, which asked the
consolidator for verbatim quotes from a transcript it had never seen. A pipeline whose
stages share prompt fragments needs the fragment's claims about the *previous* stage
re-checked whenever that stage changes, and neither time did any control catch it.

### A precondition tested after the money was spent

All three runs did the full model work, printed a complete set of checks, and then died
writing output: `--out` takes a file and was given a directory. Six minutes of local
inference on a 1365-turn meeting, discarded on the last statement — and because `report`
had already printed, the log ended in a full checks block and read as a successful run.

The findings above survive that, because they were printed rather than written. The fix
is not the path: it is that `--out` is now validated immediately after argument parsing,
before anything is spent. Any precondition testable for free belongs before the cost, not
beside the use.

### Where repair 2 stands, and what finishing it requires

The change is committed at `f2056a6` and **the result is not measured**. What is settled
is the mechanism: the extraction pass writes quote-first without exception, and the merge
has to be fed claim-first or it discards the evidence. What is not settled is whether
conditioning the claim on the quote reduces mis-selection, which is the entire question
the repair was built to answer.

The registered predictions stand unchanged and unread — they are above, and they were
committed at `92e5374` before any of this ran. Nothing below should be written until they
have been compared against a real run.

To finish, in order:

1. Regenerate all three notes. Bmr006 is the experiment and takes about six minutes;
   the other two are unchanged single-pass code and reproduced bit-identically last
   time, which is a smoke test that the change stayed on the chunked path.

       python3 notes/summarize.py notes/corpus/Bmr006.json  --strip --passes 2 \
           --out notes/out/Bmr006.md
       python3 notes/summarize.py notes/corpus/ES2004c.json --strip --out notes/out/ES2004c.md
       python3 notes/summarize.py notes/corpus/covid_4.json --strip --out notes/out/covid_4.md

2. **Read the `extraction` line before anything else.** It reports the order the model
   actually used. Claim-first lines mean the inversion did not happen and no number
   under it is evidence about inversion.
3. **Read the `reversed_locatable` line next**, and do not believe a fabrication count
   that appears above a non-zero one. It counts collapsed items whose *claim* is in the
   transcript and whose *quote* is not — speech on the wrong side of the separator,
   scored as invented by a parser assumption rather than by the model. If it fires, fix
   the read and `--recheck`; do not regenerate, because that would move the note and the
   judgement together.
4. Measure only the explicit comparison artifacts with the calibrated judge. These
   historical runs have `passed: false`, so the current harness requires the
   research-only `--measure-failed-diagnostic` flag as well as `--measure-support`.
   Do not use a wildcard that can pull a later failed run into hundreds of inference
   calls. Calibration failure or a passing sabotaged control still refuses the result.
5. Compare against the four registered quantities, and report the decision+action rate
   beside the aggregate. That is the number `PROPOSAL` cannot inflate, because the label
   only moves items out of those two types.
6. Classify the surviving unsupported claims by failure class. An aggregate that moved
   with mis-selection flat means something other than the stated mechanism fired, and
   saying so is worth more than the aggregate.

The baseline to compare against is in the table under "The disaggregated baseline"
above: Bmr006 93 claims / 24 located / 8 supported / 56 composed. **Do not read the
corpus-wide "40% supported" as the thing to beat** — it is computed over located claims
only, so it cannot see the 56 composed quotes that are the larger failure.

`docs/prototype/build.py` renders from these artifacts and should be rebuilt afterwards;
it reads `type` and `status` and needs no change for any of this.

### The measured baseline is not in version control, and nearly went the way of the last one

`notes/out/` is gitignored — it holds derivatives of a third-party corpus — so the
`837f10f` artifacts carrying the measured support verdicts existed on one disk and
nowhere else. Regenerating produces a *different note*, so an overwrite is not a
recoverable loss: the numbers in the tables above would have been left as assertions with
no artifact behind them, which is the one thing the `note/1` format exists to prevent.

They are copied to `notes/out/baseline-837f10f/`, which is inside the same ignored
directory and therefore still not in the repo. That is the correct place for a
comparison baseline and the wrong place for a permanent record. **Any future run that
will be compared against a previous one should snapshot the previous one first**, and
the same is true of `--measure-support` verdicts, which cost a second model pass to
recreate and cannot be recreated exactly at all once the note has moved.

A regeneration of Bmr006 was left running when this was written, so `notes/out/` may hold
a **partial** set: a new Bmr006 beside two artifacts from the previous run. Check
`provenance.generated_at` before comparing anything, and note that a freshly generated
artifact carries no `support` key at all until `--measure-support` has been run over it —
an absent support rate is not a rate of zero.

## Repair 2 result: inconclusive — its precondition failed

The first observed Repair 2 regeneration is **not a result**. Its artifact was generated
at `2026-07-30T07:47:59-0500`; its SHA-256 is
`8828f3b452c5dc8c70a7e82eed564ce7562fed085674c85425806cc3f43ccb32`. Its extraction
check was false, and the consolidator produced 63 claims with no quoted evidence. That is
the pipeline defect the run was supposed to prevent, not a measurement of whether
quote-first generation changed support. The registered Repair 2 predictions above remain
historical predictions; they are neither confirmed nor rejected by this run.

That artifact is in the ignored local path
`notes/out/repair2-failed-20260730-074759/Bmr006.note.json`. The digest pins the local
observation, but the ignored snapshot is **not durable repository evidence** and must not
be represented as such.

Do not run the support judge on that artifact, compare its counts to the baseline, or
rewrite `notes/out` to make it look coherent. The invalid run is retained only as a failed
precondition: a later repair must make its transport contract mechanically auditable
before another model call can be evidence.

## Repair 3: typed quote-first records, registered before a new run

Repair 3 removes prose and pipe syntax from the handoff between extraction and
consolidation. Both calls request Ollama JSON-schema output. Local decoding rejects blank
or malformed transport, duplicate/unknown/missing/blank fields, invalid labels, and any
record whose raw object key order is not `quote`, `label`, `claim`. That last check is
intentional: JSON semantics discard key order, but generation order is the mechanism
Repair 2 was testing.

The consolidator receives serialized validated records, not transcript text or markdown.
It may rewrite a claim and deduplicate records, but every output quote must exactly match
an extraction quote with the same label. Every extraction quote must also be locatable in
the visible source slice before it is handed downstream.

Each validated extraction record receives a deterministic local source ID. Every
consolidated record must name at least one of those IDs; across the full output each input
ID must appear exactly once. Unknown IDs, repeated IDs, dropped IDs, cross-label merges,
and a quote not copied from one of its covered sources all fail the run. Source IDs never
render. Control and line-break characters are refused in summary, quote, and claim fields,
and local rendering proves a one-to-one cardinality between validated output records and
parsed Markdown claims. There is no Markdown dedupe after that proof.

The artifact records stage source and ordinal, the exact resolved Ollama model digest,
options, schemas, and hashes of system prompt, input prompt, validated consolidation
listing, and raw model response. It does not add raw responses or a second transcript
copy. A mutable model tag that cannot be resolved unambiguously from Ollama before
inference fails the run. `--recheck` remains a legacy `note/1` citation recalculation. It
cannot revalidate a prior structured raw response, because that response is intentionally
not retained.

Predictions, recorded before inference:

1. A blank, malformed, or claim-first response will fail closed before a note, artifact,
   or support number is written. A schema-valid empty item list is allowed for a genuinely
   empty slice or meeting; an overall empty-claim artifact is valid only if every structured
   response validated.
2. A completed chunked run will have no unquoted rendered items introduced by the merge.
   Each rendered quote will be traceable to a validated extraction record with the same
   label, and every extracted source ID will be represented exactly once. This is a
   transport invariant, not evidence that the quote supports its claim.
3. The Bmr006 support and composed-quote rates are deliberately **not predicted** here.
   Repair 3 changes the permitted merge operation and may change the claim set. They are
   measured only after the structural controls pass, reported against the Repair 2
   baseline as a new condition, and never substituted for the prior Repair 2 prediction.

## Repair 3 result: refused before the first slice could become evidence

The first full Bmr006 run stopped on slice 1 of 16:

    qmsum:Bmr006 (labels stripped) [slice 1/16]: extraction evidence refused:
    4 extraction quote(s) are absent from the visible slice

No note, artifact, or support result was written. The structured transport did what it
was built to do: it refused a model response that satisfied the JSON schema but did not
carry verifiable evidence.

The six returned records were inspected only to diagnose that refusal, not to score the
repair. Two quotes were locatable under the then-current rule. Three differed only
because QMSum separates closed-class contractions (`it 's`, `I 'd`); the citation
normalizer now treats those forms as the same words. The fourth was materially different:
the model removed recorded disfluencies such as `w will` and `b it 'd` while presenting
the result as a verbatim quote. That record still fails, correctly.

The narrow contraction correction also moved the old Bmr006 baseline from 24 to 33
locatable claims. Nine of the newly locatable claims have no stored support verdict, and
eight collapsed items locate only when read in the reverse orientation. The previously
reported 8-of-24 support figure is therefore not a stable target for a new condition.
It remains a historical result under its old locator, not a denominator to preserve by
changing the evidence rule.

Another run of the same copied-quote contract is not useful. At least the disfluency-
cleaned record is already known to fail the stated verbatim precondition. Relaxing the
locator until it accepts model-repaired speech would make the model choose and edit its
evidence after generation, which is the defect these repairs are meant to remove.

## Repair 4: choose canonical evidence, then write the claim

The current contract has one model-authored stage: extraction. A preflight version also
asked the model to consolidate records, but the synthetic run recorded below proved that
exact coverage was not a feasible prompt contract. That model stage never produced a
Repair 4 artifact and is not part of the implementation.

Each extraction response contains only `source_fragment_ids`, `label`, and `claim`.
Local code then performs deterministic normalization. Its claim identity is the
JSON-decoded string after one exact outer-whitespace `str.strip()`; raw JSON spelling is
not identity. It may group at most three records only when label, canonical claim UTF-8,
and ordered `source_fragment_ids` are identical. The first occurrence keeps its position
and canonical decoded claim. Equal prose attached to different evidence remains
separate, and every extraction item appears exactly once. The artifact field remains
named `consolidated_items` for compatibility, but no model authored that list.

The durable graph hashes every extraction and normalized claim, so changing note prose
and `claims[]` together no longer leaves the declared evidence untouched. This does not
prove that an extraction claim fairly reads its selected words; the support check and
human review still own that judgment. Repair 4 writes no `.items.md` extraction sidecar.
It does not persist every selected fragment as a second transcript-derived list. The
note still carries the primary evidence excerpt for each rendered claim. A retired
sidecar already present beside `--out` refuses the run before inference; the tool does
not silently delete it.

Stage receipts distinguish model evidence from local work. The exact validated
`message.content` JSON is retained for every extraction call. Its schema permits only
IDs, labels, and claims; it has no source-text field and does not retain a second
transcript copy. The final `local-normalization-receipt/1` records the deterministic
contract, safe-input and durable-output digests, counts, coverage, and largest group. It
has no model, schema, prompt, or response fields. `--recheck` decodes extraction again
under the strict key-order and schema rules, reconstructs it from the retained
transcript, reruns local normalization, and requires the output graph and receipt to
match exactly.

Two boundaries remain receipts rather than replayable evidence. The Ollama transport
envelope is not retained, and the historical `/api/tags` response used to resolve the
model digest is not retained. Model identity is therefore only cross-checked among
artifact fields. The artifacts are also unsigned: their hashes prove internal
consistency, not authorship or authenticity. A writer able to coordinate changes across
safe responses, graph rows, contracts, hashes, note JSON, and Markdown is outside this
trust boundary. These are contract corrections, not evidence that the model produces
acceptable notes.

Repair 4 keeps the causal part of quote-first generation and removes the copying task the
model has repeatedly failed. Local code divides each visible transcript turn into
deterministic, overlapping source fragments. The model sees each fragment with an opaque
ID and must emit each response item in the exact order `source_fragment_ids`, `label`,
`claim`. The first field is an ordered array of one to three IDs, so source selection
precedes interpretation. The model does not author the rendered quote; its claim may
still reuse meeting words.

Fragments target 32 whitespace-delimited words with an 8-word overlap and never cross a
turn. A final remainder under 12 words is appended to the preceding fragment. Exact
Unicode character offsets, the transformed transcript-view digest, and the turn ordinal
make the IDs independent of slice boundaries. The same fragment exposed in two
overlapping slices has the same ID. Gated turns are not in the visible transcript view
and cannot enter a fragment enum.

Each slice gets a dynamic JSON schema whose enum is exactly the fragment IDs displayed
in that slice. `source_fragment_ids` is nonempty, unique, in canonical transcript order,
and capped at three. Local validation rejects unknown, duplicate, blank, out-of-order,
out-of-slice, excessive, or unresolvable references. Only after that validation does
local code attach each exact source passage and a separate extraction-item ID. It never
joins speech from separate turns into a synthetic quote. The durable extraction row is
exactly
`evidence_item_id`, `slice_ordinal`, `source_fragment_ids`, `label`, and
`claim_sha256`; the claim itself remains in the retained safe response. Selecting a
source fragment establishes only that those words were said; it does not establish that
the resulting claim is a fair reading of them.

Normalization does not ask for another response. It walks validated extraction in first-
occurrence order and groups only the exact canonical identity defined above. The durable
normalized row is `source_item_ids`, `source_claim_sha256s`, `source_fragment_ids`,
`label`, and `claim_sha256`. Its source-fragment sequence is the identical sequence
shared by every member, never a union of different evidence. The final quote resolves
locally through that sequence. No model can compose, repair, transpose, merge, or rewrite
at this stage.

Repair 4 artifacts use `note/2`; legacy `note/1` artifacts and readers remain supported.
A `note/2` file missing its graph, stage responses, provenance, or render contract fails
strictly and cannot fall back to the legacy citation checker. Its JSON is the canonical
note. The sibling Markdown must be the exact UTF-8, LF-terminated rendering named and
hashed by the JSON. Both output names are checked before inference. Existing files,
directories, and symlinks are refused by default, and `--replace` is required to replace
the pair. Construction and validation finish before either target write; owner-private
same-directory temporary files are installed atomically per file, and an ordinary
second-install exception rolls a new or replacement pair back. The pair is not
crash-atomic: process or OS failure between file installs can leave a partial or stale
mix, which the render digest detects on the next read. Recheck and support-measurement
updates replace the canonical JSON through the same owner-private atomic-file path and
revalidate the unchanged Markdown pair. A stale `.items.md` still refuses the run. Like
the other hashes, the pair digest does not authenticate a coordinated rewrite.

The sizing decision is measured before implementation. On Bmr006, 32-word fragments with
8-word overlap increase visible extraction text by about 42% across 16 slices and keep
the largest visible prompt below roughly 3,700 tokens under this repository's
characters-per-token estimate. The dynamic enums add schema bytes whose Ollama token
cost is not yet measured; context checks still use the server's observed prompt count
and fail the run if any slice is truncated.

The plural reference shape is also measured rather than precautionary. Four of the 12
baseline claims that the calibrated judge marked supported need words from more than one
dialogue turn: the object is named in one turn and qualified, accepted, or completed in
another. A singleton reference would make at least one third of the currently
support-positive examples impossible to represent faithfully. Three references cover
proposal, qualification, and assent; a claim needing more must be split instead of
becoming an unbounded evidence bag.

Predictions, recorded before implementation or inference:

1. A completed chunked run has no model-authored quote text. Every rendered evidence
   passage resolves byte-for-byte to an offered fragment in the exact transformed
   transcript view; separate turns are never rendered as one quote.
2. An invented, cross-slice, unresolved, or reordered evidence reference fails before
   consolidation. A missing, repeated, cross-label, or unselected covered extraction item
   fails before rendering. No note or artifact is written from either failure.
3. Changing slice boundaries does not change a fragment's ID. Changing visible transcript
   content does change the view digest and fragment namespace. Transforms and gate removal
   cannot silently make an ID resolve to different words.
4. A completed Bmr006 artifact covers every validated extraction item exactly once and
   renders one claim for every validated consolidated record. Its provenance retains the
   exact validated safe JSON replies and is sufficient to distinguish this condition from
   Repairs 2 and 3; transport envelopes and the historical model-list response remain
   outside the artifact.
5. No support rate, label mix, or claim count is predicted. Source selection removes copied-
   quote composition; it does not prevent a model from choosing the wrong real fragment or
   overstating what that fragment means. Those remain acceptance questions for the
   calibrated support pass and human inspection after all structural gates pass.

### Synthetic preflight refused model consolidation

The registered predictions above remain unchanged. Before any Bmr006 inference, a live
`llama3.1` synthetic run validated extraction and then stopped at consolidation:

    consolidation: structured output refused:
    consolidation may merge only byte-identical extraction claims

No note or artifact was written; the requested output directory stayed empty. The model
had merged non-byte-identical extraction claims despite an explicit contract forbidding
that operation. This is preflight evidence about feasibility, not a corpus result. A
prompted model merge is not a reliable implementation of exact coverage.

Repair 4 therefore no longer makes a consolidation model call. After strict extraction
decoding and evidence attachment, local code performs one deterministic normalization:
it may group up to three items only when their label, canonical decoded claim UTF-8, and
ordered `source_fragment_ids` are all identical. Canonical means the JSON-decoded claim
after one exact outer-whitespace `str.strip()`; two raw JSON strings can therefore share
one canonical identity. The first occurrence keeps its position and canonical claim.
Equal prose attached to different evidence remains separate. Every validated extraction
item appears in exactly one output group.

The final stage is a `local-normalization-receipt/1`, not a simulated model receipt. It
records the normalization contract and digest, safe input and durable output digests,
counts, coverage, and largest observed group. It carries no model, schema, prompt, or
response fields. Recheck rebuilds extraction from retained safe JSON plus the transcript,
runs the same local normalization, and requires the durable output and local receipt to
match exactly. Only extraction stages carry model receipts.

This correction removes a feasibility failure before spending a Bmr006 run. It does not
change the registered corpus outcome predictions or establish note quality.

### First registered run: output was unbounded, so timeout is not a result

The first Bmr006 run against the registered Repair 4 contract produced no artifact. It
spent about 25 minutes across the extraction work that completed, then one Ollama
`/api/chat` request reached the command's 900-second timeout. There is no validated
response from that stage, no completed extraction graph, and no note or support
measurement. The registered predictions above therefore remain unchanged: a transport
timeout before a response exists cannot confirm or reject any of them.

The request itself was not bounded in the dimension that failed. Its schema constrained
each evidence set to one to three offered fragment IDs, but the top-level `items` array
had no maximum, `claim` had no maximum length, and the Ollama options carried no
`num_predict`. The server had a wall-clock timeout but the generation contract still
allowed an indefinitely growing response. This is feasibility evidence about the runner,
not a corpus result.

Every extraction call is now bounded from the evidence it is offered:

- `items.maxItems = min(visible source fragments, 48)`;
- `claim.maxLength` is 160 Unicode characters, matching the existing short, atomic-claim
  contract; a longer thought must be split rather than expanding one record without end;
- `num_predict = min(8192, 64 + 192 × items.maxItems)`.

The item ceiling comes from the observed density rather than the timeout after the fact.
The prior quote-first Bmr006 extraction produced 227 items across 16 slices, about 14 per
slice. Forty-eight is more than three times that observed rate and still allows roughly
one item per 31 input words in a nominal 1,500-word slice. The tradeoff is recall: a slice
with more than 48 real atomic claims cannot express all of them under this contract. That
limit is now visible and reviewable; an unlimited array hid the same choice behind
runtime and let one request consume the full timeout.

The 64-token base pays for the response envelope. The 192-token allowance budgets one
compact record, its enumerated IDs, label, and bounded claim. The 8,192-token ceiling is
the independent final stop. Under the exact Bmr006 defaults the 16 slices expose 65–136
source fragments each, so every one now offers at most 48 output items and carries the
same 8,192-token cap. If Ollama reports `done_reason=length`, the stage fails even when
the returned prefix happens to be valid JSON. A response missing `done: true` or the
recognized `done_reason=stop` also fails; the discarded transport envelope cannot be
replaced by an assumption that generation completed. Incomplete JSON fails strict
decoding as before. None can be mistaken for a smaller complete extraction or written
as an artifact.

The schema, formula, cap, and actual per-slice `num_predict` now travel in the structured
run contract and extraction receipts. Each receipt also retains only the minimal
transport completion proof, exactly `done: true` and `done_reason: stop`; it does not
retain the full Ollama envelope, timing data, or token telemetry. Recheck requires that
exact nested shape and refuses a missing or changed completion proof. It re-derives all
other bounds from the retained transcript. An over-cardinality response, a 161-character
claim, a receipt with a changed budget, or a schema-constrained call with no budget fails
closed. A transport timeout is reported as one concise refusal naming the slice, without
a Python traceback.

No Bmr006 inference was rerun for this correction. It makes the registered run finite and
replayable; whether the model now completes, what it extracts, and whether those claims
are supported remain the next measurement.

### Second registered run: the graph completed, and the note failed acceptance

The bounded run completed all 16 extraction calls in 4,144.5 seconds. Every call reported
`done: true` and `done_reason: stop`; the largest observed prompt was 9,912 tokens against
`num_ctx 32768`. It selected 678 source-reference-first items, resolved all 678 references,
and local normalization rendered 663 claims while covering every extraction item exactly
once. Fourteen exact same-evidence groups were normalized, with a largest group of three.
The retained diagnostic is
`notes/out/repair4-82b45c0/Bmr006.note.json`, generated at
`2026-07-30T13:48:36-0500`, SHA-256
`68c3d2819df8f951351ad61376b0316651a76bc01c872bff76931d663d983e59`.
It records model tag `llama3.1:latest` at resolved digest
`46e0c10c039e019119339687c3c1757cc81b9da49709a3b3924863ba87ca666e`.
It is ignored local evidence, not durable repository evidence.

Those figures confirm the structural predictions only. The note failed its own
attribution gate through phrases including `I will`, `you said`, and `you will` after
attribution had been stripped. The stored diagnostic also named `Them`, but that arm was
a checker false positive: lowercase `by them` is a pronoun, not the synthetic
title-cased channel label. The checker now distinguishes those cases; the independent
actor phrases still fail the verdict.

Its 663 claims comprised 233 actions, 10 decisions, 375 proposals, and 45 questions.
They contain 21,015 whitespace-delimited words against 21,138 in the transformed
transcript; claim prose alone is 8,409 words. One hundred twenty claims repeat an
earlier normalized claim and 184 contain no more than three words. Twelve of 16 slices
returned the maximum 48 items. Inspection found action claims such as `Yeah`, `Right`,
`OK`, and `Mm-hmm`. This is extreme extraction density. Whether a summary is useful is
an operator judgment this corpus cannot make; this artifact is withheld because it
independently failed the hard attribution gate.

No support pass follows. It would require 663 claim calls plus 34 calibration and
sabotaged-control calls. A calibrated support verdict for hundreds of claims cannot make
an artifact that already failed attribution eligible for the product, and it would not
answer the binding feasibility question. The useful conclusion is narrower:

- the Repair 4 evidence graph is mechanically replayable and resolves selected words;
- `llama3.1:latest` under this 16-slice extraction contract produced a rejected
  663-claim output on Bmr006;
- 69 minutes and 663 claims are measured feasibility costs, not a human usefulness
  verdict; no registered threshold turns either into one;
- this run does not justify a support or tuning pass before a compact artifact clears
  the existing acceptance checks.

The run also exposed a product-boundary defect in the harness. `--out` wrote the
Markdown/JSON pair before returning the failed verdict, so a `passed: false` diagnostic
had the same filename and schema as a ready note. Default output now fails closed:
failed checks write no note, while `--retain-failed-diagnostic` is the explicit
research-only escape hatch. The prototype refuses every artifact whose `passed` field is
not exactly `true` as a ready note. It renders none of that artifact's claims or trust
counts and routes the encounter to `summary-failed`, where the retained transcript
remains available for retry.

### Product-oriented whole-context candidate: bounded, completed, and rejected

This is not a second registered Repair 4 corpus result. It is one bounded attempt to
populate the accepted-note side of the product encounter with a different installed
model and a whole-context prompt:

    python3 notes/summarize.py notes/corpus/ES2004c.json \
      --model gemma3:12b --num-ctx 32768 --timeout 1800 \
      --strip --passes 2 --chunk-words 9000 --overlap-words 0 \
      --retain-failed-diagnostic \
      --out notes/out/product-candidate-gemma3/ES2004c.md

The raw QMSum source contains 604 annotated rows and 8,103 whitespace-delimited
content words. The canonical loader removes non-speech markers and empty results. The
artifact therefore records 582 model-visible turns containing 7,850 content words
before the 582 prompt bullet markers are added. The single extraction call completed
in 475.3 seconds with `done: true` and `done_reason: stop`, but the server reported
reading exactly 32,768 prompt tokens for a prompt estimated at 33,393. The hard context
check therefore records that the last estimated 625 tokens were dropped.

The validated response reached the 48-item ceiling. All 48 records carried label
`ACTION`, selected the same first source fragment, and repeated the same claim. Local
normalization, whose maximum group is three, rendered 16 identical claims; the citation
check found 15 repeats. Exact reference resolution and attribution passed, but they do
not repair the missing prompt tail or turn repeated first-fragment output into a note.
The overall verdict is `passed: false`.

The research-only diagnostic is
`notes/out/product-candidate-gemma3/ES2004c.note.json`, generated at
`2026-07-30T14:25:09-0500`, SHA-256
`5f47d39d0aafe72fa7953c7f15a9cebfe0fb5a86867f8b43baef85db75f9753c`.
Its sibling Markdown has SHA-256
`5c6091fccd3bc11233e7dde87e0d97910e0d241144905dd32dfc082aea882b8e`.
It records `gemma3:12b` at resolved digest
`f4031aab637d1ffa37b42570452ae0e4fad0314754d17ded67322e4b95836f8a`.
These are digest-pinned, ignored local run observations, not durable repository
evidence or accepted product data.

The product prototype built from that directory reports zero accepted notes, one
withheld summary, and zero rendered claims. It keeps the transcript and retry path.
That is the intended failure encounter, not an acceptable-note encounter.

Taken together, the bounded `llama3.1:latest` Bmr006 run and this bounded
`gemma3:12b` ES2004c run reject the current enumerative, model-authored list contract
under the two tested conditions. They do not prove that automatic notes are infeasible,
that either model cannot work under a materially different architecture, or that a
transcript-first product is unusable. More prompt tuning inside this contract is not
the next product step. The next decision is among:

1. generate deterministic evidence candidates first, then let a model label,
   paraphrase or abstain one candidate at a time;
2. make the first beta transcript-first and withhold automatic notes until a new
   extractor clears acceptance; or
3. continue generative-extractor research outside the first-beta critical path.

No application implementation or accepted-note operator review follows from this
rejected diagnostic.

## Candidate-first extraction: registered architecture spike

The two rejected runs above share one remaining authority defect: the model decides how
many records exist. A JSON array ceiling makes that choice finite, but it does not make
the choice local, complete or compact. Candidate-first extraction changes the question.
Local code enumerates the evidence units. The model must return one decision for every
unit it receives.

This is a new architecture experiment, not Repair 5 and not an accepted-note result. It
does not alter `structured-run/4`, whose prompts, schemas and receipts must continue to
replay historical artifacts exactly.

### Design comparison fixed before inference

Two deterministic generators were developed far enough to compare on the three existing
corpus files:

| generator | ES2004c | Bmr006 | covid_4 | authority |
|---|---:|---:|---:|---|
| broad, one candidate per canonical source fragment | 645 | 1,571 | 658 | acceptance baseline |
| cue, one candidate per lexical cue hit | 182 | 389 | 300 | efficiency challenger only |

Both use the existing `source-fragments/1` map. A candidate exposes the fragment before
the anchor, the anchor and the fragment after it, when those exist. Any kept claim must
cite the anchor and may cite at most two of the visible neighbours.

The cue generator is not allowed to become the recall authority from these counts. A
prior, broader cue draft exposed only 13 of 17 supported claims in the repository's
older manually judged sample, missing examples including delivery media, disk archiving
and a proposed mirror display. The draft and sample do not measure this exact narrower
generator, so 13/17 is a risk signal rather than its recall rate. It is still sufficient
to reject the inference that lexical cues lose nothing.

The broad generator deliberately pays the opposite cost. Every canonical fragment
becomes an anchor, so no transcript region is removed before inference. This does not
prove that one three-fragment packet contains every part of a multi-turn event, or that
the classifier will keep the right regions. Broad generation removes a lexical
prefilter as the cause of omission; only the atomized event ledger can establish
packet-level exposure.

### Fixed decision contract

Candidate generation and model classification are separate stages. The candidate
manifest binds:

- the transformed transcript digest;
- the source-fragment and generator-contract digests, including the exact cue and
  assent regular expressions;
- stable candidate IDs in transcript order;
- each anchor and its visible neighbouring fragment IDs; and
- the complete manifest digest.

Cue candidates also send the exact cue family, character span and matched text to the
classifier. Multiple cue hits over the same three visible fragments therefore remain
distinct inputs rather than identical packets carrying different opaque IDs.

Classification runs in fixed batches. Every response must return every offered candidate
ID exactly once, in the offered order, with only `KEEP` or `ABSTAIN`. Missing, duplicated,
reordered, unknown or extra IDs refuse the whole batch. A length stop, missing completion
proof, malformed JSON or context truncation refuses the whole run. An abstention is
durable evidence about what the classifier saw; it is not discarded because it produced
no note claim.

Claim writing is a later stage. It does not run unless classification first clears the
registered mechanical measurement below and a human-locked event ledger establishes
packet exposure and classifier recall on the target record types. When built, each kept
candidate will receive a separate fixed-cardinality label-and-claim response. The old
free-list extractor is not used as a fallback.

### What the corpus can establish

QMSum is not event-level gold. Its exact transcript words are source evidence. Its
`relevant_text_span` fields are human-selected search regions, often much wider than one
decision or commitment. Its written answers are abstractive and non-exhaustive. A
candidate touching such a span proves only that the classifier retained somewhere to
look; it does not prove that a particular event was exposed or understood.

Event recall therefore requires a separate, ignored `candidate-exposure-reference/1`
ledger of atomized events and exact acceptable evidence bundles. An agent may draft it,
but that does not give it judgment authority. The operator must review and explicitly
lock a ledger covering every decision, action, proposal and unresolved material question
in the full 582-turn evaluation transcript before any corpus classification call. Its
exact pending-lock file digest must then receive explicit out-of-band operator approval.
An optional pre-inference commit may preserve non-sensitive provenance, but it is not a
mechanical approval gate. Candidate generation must produce the same manifest digest
when the ledger is absent, empty or label-shuffled.

The search-span smoke uses a separate `qmsum-search-spans/1` registry. QMSum spans are
zero-based, inclusive raw-row ordinals. The registry maps them through the canonical
non-speech cleaner, retains the raw-corpus, mapping, span and cleaned-transcript
digests, and refuses a mapping that does not reproduce the model-visible turns. Raw
row numbers are never treated as cleaned turn numbers.

### First registered run

The first live classifier run is fixed to:

- corpus: stripped-attribution ES2004c, raw SHA-256
  `31815196407111dba01f8b8cbfa31cd07fb8a682e4005bae7846893ab93a6778`;
- transformed transcript view SHA-256
  `d10d60293f503724820957b95f7da0bf2aaa3513edee879cfcd03a0b5cca7940`;
- generator: broad, one candidate per canonical source fragment, producing manifest
  SHA-256
  `bd33f6da6b3aa9a2a76b203b53de56c7adc8854f10a047e00086d2bae48872df`;
- diagnostic span-registry SHA-256
  `00e770f6fc26a0f1664f0f4f440bd07ce43c24fc3054c09531f29cbe10f624c1`;
- model: `gemma3:12b`, required to resolve to
  `f4031aab637d1ffa37b42570452ae0e4fad0314754d17ded67322e4b95836f8a`;
- batch size: 32;
- context: 16,384 tokens;
- temperature: zero;
- output bound: `min(2048, 32 + 48 × candidates)`, or 1,568 tokens for every
  full batch;
- no claim generation, support judge or semantic deduplication.

The executable registration has SHA-256
`cf377030002773496ce98c221a6f15120028e258bace236b2ba260e9175744e4`.
It also pins the generator, fragment, fixture and system contracts. The runner must
rederive all registered inputs and refuse a changed corpus or mutable model tag before
the first paid call.

The largest serialized batch plus a minimal complete 32-row response is 30,800
characters, or 8,324 tokens under the repository's deliberately conservative
3.7-characters-per-token estimator. The 16,384-token registration leaves roughly
twofold static headroom. The runner must additionally require transport completion and
prove `prompt_eval_count + eval_count` stays below the context limit; the existing
prompt-only check is insufficient for this experiment.

The classifier prompt and fixtures are fixed in `notes/candidate_first.py`. Six KEEP
and six ABSTAIN cases cover an explicit decision, action, proposal, unresolved question,
adjacent assent, ambiguous commitment, status, presentation fact, social speech, empty
backchannel, answered question and noncommittal opinion. The fixture SHA-256 is
`52bb4ac93d1dc5e9a384c78b2801fca22865640304301510031ec16ab1e4fb91`;
the classifier-system SHA-256 is
`8dcacef1d52991e0972e1522e85617b1dec31a1b4a6cae2beb8522bbaf770119`.
The two sabotaged systems are fixed to always KEEP and always ABSTAIN.

It passes only if all of the following hold:

1. synthetic KEEP/ABSTAIN fixtures pass 12 of 12; deterministic all-KEEP and all-ABSTAIN
   responses are rejected for semantic disagreement, and both sabotaged model calls
   complete normally, produce their commanded pattern and are rejected for the same
   reason;
2. all 645 candidates receive exactly one replayable decision, with every transport and
   context check passing;
3. the pending lock file existed before approval, its exact raw-file digest was
   approved out of band before the first corpus call, the effective operator-locked
   ledger and its digest therefore existed before inference,
   every target event has at least one complete acceptable evidence bundle in a broad
   packet, and the classifier keeps at least one acceptable anchor for every target
   event — 100% packet exposure and 100% classifier recall;
4. no more than 64 candidates are kept — about eight per 1,000 cleaned words and enough
   to bound the next stage to two 32-candidate batches;
5. classification completes within 900 seconds on the current machine; and
6. two no-model manifest generations are byte-identical.

The 13-span QMSum result is always emitted as a diagnostic, never a pass condition.
Those regions were selected to answer broad factual questions; some contain only
presentation facts or questions answered immediately, which the classifier contract
correctly tells the model to abstain on. Requiring all 13 would reward a contract
violation.

The keep-rate and time bounds are product feasibility limits, not quality scores. No
live run starts until the pending lock file's exact digest is explicitly approved, the
runner has versioned per-batch receipts and an aggregate replay validator, and the
ledger stays bound to this registration and candidate manifest. A separate
pre-inference commit may preserve the non-sensitive lock for audit, but the runner does
not mechanically require Git provenance and the commit cannot supply human approval. A
run that fails any numbered item stops before claim generation. A run that passes
allows the fixed label-and-claim stage to be built; it does not establish that its
eventual claims are compact, supported or useful.

Registered predictions:

1. Manifest determinism and exact response coverage will pass; those are mechanical
   properties of the new contract.
2. Broad packets will expose every operator-locked event, and the classifier will retain
   at least one acceptable anchor for every event.
3. The classifier will keep no more than 64 candidates, because most canonical
   fragments are discussion, repetition or backchannel rather than an atomic decision,
   action, proposal or open question.
4. The 900-second runtime bar is uncertain. It is the first measurement of whether
   fixed-cardinality classification is cheaper in practice than free-list generation.

No prediction is registered for QMSum search-span coverage, final claim count, support or
human usefulness. The evidence required for those judgments does not exist yet.

### First post-registration result: manifest determinism passed

After the registration above was committed as `0b3f9a7`, the pinned no-model command
generated the full broad manifest twice into separate private files. `cmp` found no byte
difference. Both files were mode `0600`, 406,540 bytes, and SHA-256
`f693e196a1b6365fb52a687d6b9afc018b87f300cc1b52daa7f8659a613766b9`.
A retained copy lives outside Git at
`candidate-manifest-0b3f9a7.json` in the session's private visualization directory.

This satisfies only the registered byte-determinism gate. It is not classifier output,
does not consult an event ledger, and carries no evidence about event recall, note
quality or product readiness.

### Pre-inference status: the machinery passed; the result does not exist

The event-review and classifier runners now pass deterministic tests using a fake model
connection. No Ollama call or corpus classification has run.

The private review draft contains 66 proposed target events. Twenty-four contiguous
sections expose all 582 cleaned transcript turns so the operator can find events the
draft omitted, not merely approve what an agent selected. The smallest set of
candidates that covers every proposed evidence bundle contains 63 candidates. The
registered run may keep at most 64. If the operator retains all 66 events and their
current bundles, the classifier therefore has room for only one non-target KEEP. That is
a preregistered feasibility risk, not a reason to change the limit after seeing a
result.

The review tool:

- keeps draft references, submitted decisions and promoted runner ledgers as distinct
  schemas;
- requires Accept, Edit or Reject for every proposed event and explicit review of every
  transcript section;
- requires each section to resolve explicitly to no missing event or a reported missing
  event, requires a note for the latter, and refuses ledger promotion while any report
  remains;
- refuses exact normalized duplicate retained propositions;
- records a reason for every edit or rejection;
- persists validated decisions and ledgers outside Git as immutable mode-`0600` files;
  and
- cannot create operator authority from its own output.

The classifier runner re-derives the reference and decisions, rebuilds the promoted
ledger, checks packet exposure and the approved lock bytes before resolving the model,
then retains replayable receipts for three semantic preflights and 21 corpus batches.
Every resolution and call is bounded by the time remaining in the registered
900-second whole-run deadline. The operator-supplied lock digest proves only that the
runner received the exact approved file; the operator's explicit approval is the
authority.

The next sequence is fixed:

1. the operator reviews all proposed events and all transcript sections;
2. any section reporting a missing event stops promotion; the event plan and whole
   review are revised;
3. otherwise the submitted controls are validated and canonical private decisions, a
   pending ledger and a `pending-operator-approval` lock file are written;
4. the exact decision digest, ledger digest and raw lock-file SHA-256 are presented back
   to the operator;
5. the operator explicitly approves or declines that exact lock-file digest; and
6. only an approved digest may be supplied to the registered classifier runner.

A passing classifier result would authorize the fixed-cardinality label-and-claim
experiment. It would not establish note usefulness, produce an accepted real-content
encounter, or make the product ready for implementation, beta or general availability.

### Pre-run amendment, 2026-08-14: the output bound was measured wrong and re-registered

No registered ES2004c corpus call has run under any registration. Before the
first one, the private-capture lane (`notes/capture_classifier.py`, same
classifier contract, different corpus) made the first live call under the
registered decoding options and was refused by the runner's own completion
proof: gemma3:12b hit the 1,568-token output limit on a full 32-candidate
batch.

A single off-registration probe with the ceiling raised to 4,096 measured the
truth. The pinned model (`f4031aab…`) completed the same batch cleanly —
`done_reason: stop`, 32 unique candidate IDs, valid schema — at 2,401 output
tokens: **75.0 tokens per item against the budgeted 48**, 1.47 characters per
token, because 64-hex candidate IDs tokenize far below the repository's
3.7-characters-per-token estimator. The registered run would have refused
identically at batch 1 of 21. The estimator was conservative for prompt
budgeting and anti-conservative for output budgeting; nothing had ever
exercised the output side.

The amendment changes exactly one formula:
`num_predict = min(2048, 32 + 48 × candidates)` becomes
`min(4096, 32 + 96 × candidates)` — measured 75 per item plus ~28% headroom.
A full batch's ceiling becomes 3,104; the measured full-batch prompt of
12,944 tokens plus that ceiling stays under the unchanged 16,384-token
context. Model, digest, batch size, temperature, prompts, fixtures, schemas,
gates, and every other registered value are untouched.

The executable registration is therefore re-pinned from
`cf377030002773496ce98c221a6f15120028e258bace236b2ba260e9175744e4` to
`87526ad6f0b16f123f85e35f916d2bd13b2518b1027d2d0aac899ad2913223a8`, and every
artifact binding the old digest — review references, decision exports,
ledgers, and pending locks — must be regenerated and re-approved before use.
The registered predictions above stand unchanged; prediction 4's runtime
uncertainty now includes the measured fact that responses are ~2.4k tokens
per full batch.

### Second pre-run amendment, 2026-08-14: short model-facing locators

Still before any registered corpus call. Under the corrected output budget,
the next live private-capture attempt was refused by strict decoding: an item
did not match its expected candidate ID. A content-free six-batch diagnostic
(coverage and order only; no verdicts retained) measured the failure shape on
the pinned model: every batch completed with the correct cardinality, but
**2 of 6 batches contained duplicated and dropped 64-hex candidate IDs**, and
3 of 6 returned items out of registered order. The model cannot reliably echo
thirty-two 64-character hexadecimal strings, independent of budget.

The amendment stops asking it to. The response contract now uses
batch-positional locators `c01..cNN` in the model-facing packets and schema
enum; local decode maps each locator back to its registered candidate ID.
Decode requires exact single coverage of the offered locators — duplicates,
gaps, and unknown locators still refuse — and canonicalizes item order
deterministically, counting displacement into the replayable
`out_of_order_positions` diagnostic, because order carries no information the
locator does not already carry and no JSON schema can constrain it. The
classifier system prompt, fixtures, model pin, batch size, context, gates,
and the corrected output budget are unchanged; the sabotage controls and
fixture calls use the same locator contract.

The executable registration re-pins from `87526ad6…3223a8` to
`cbbb4e2448475ce5375b075d806581448936c81f7942c489c55c2e0a923d7a69`. Artifacts
bound to superseded digests must be regenerated and re-approved. A side
effect worth recording: locators cut the response cost roughly threefold, so
the 96-token per-item budget from the first amendment is now generous rather
than tight.

### View-sensitivity measurement, 2026-08-14 — no further amendment adopted

After the locator amendment, the first complete live run on a private capture
ledger (a real 12-minute in-person 1:1; 164 Whisper rows; 13 operator-adopted
events) refused at the recall gate. Three follow-up diagnostics reshaped only
the classifier's view of the same transcript, holding model, prompt, fixtures,
temperature, and decode constant. Content-controlled results:

| View | Candidates | Recall | Keep (limit 64) | Missed events |
| --- | --- | --- | --- | --- |
| Registered: row units, ±1 fragment, 16k ctx | 165 | 10/13 | 97 | ev-008, ev-011, ev-012 |
| Row units, ±2 fragments, 32k ctx | 165 | 11/13 | 133 | ev-011, ev-012 |
| Coalesced ~280-char units, ±2, 32k ctx | 71 | 9/13 | 39 | ev-008, ev-009, ev-010, ev-011 |

Every configuration produced a different miss-set; two events that every
row-unit view recalled were lost by the coalesced view, and the widened
window recovered one event at the cost of the classifier keeping 81% of all
candidates. The keep overflow is not backchannels: only 21 of the 133 keeps
were bare assents.

Conclusion recorded rather than patched around: on live-capture speech,
gemma3:12b's KEEP/ABSTAIN judgment at temperature zero is **view-sensitive**
— reshaping what the model sees moves which commitments it loses, and no
tested view met the 100%-recall gate. A fourth view adjustment fitted to this
one meeting would be curve-fitting, so none was adopted: the widened-window
and unit-coalescing changes were reverted from the working tree after
measurement (the coalescing implementation and its measurements are retained
privately with the capture packet). The registration remains the locator
registration.

What this leaves open, deliberately, as the next decision: a different or
larger local model under the same harness; per-candidate calls or
self-consistency voting instead of single-pass batches; or accepting a
sub-100% recall gate with an explicit human backstop. Each changes the
experiment's meaning and needs its own preregistration.

### Preregistration — model scale-up, 2026-08-14

The view-sensitivity conclusion above leaves the model as the next variable.
The amendment swaps exactly one registered value pair: `model` becomes
`gemma3:27b` at a digest pinned after download. Same family, same template,
same license terms as the registered 12b; prompts, fixtures, locators, batch
size, context, decoding options, and gates are untouched, so parameter count
is the only difference between the two arms.

Registered predictions, before any 27b token is generated:

1. On the private-capture ledger under the registered view (row units, ±1
   fragment), 27b's recall will be at least 11/13, and its miss-set will be
   a subset of the 12b miss-set {ev-008, ev-011, ev-012} — scale should not
   lose events the smaller model found.
2. The keep count is uncertain; no prediction is registered beyond the
   standing 64 gate.
3. Falsifier: if 27b's miss-set is not a subset of the 12b's — if scale moves
   which commitments are lost the way view reshaping did — the
   model-scale hypothesis is falsified for this contract, and the next arm is
   self-consistency voting rather than a still-larger model.

A content-controlled diagnostic runs before any official gated run, so an
operator approval cycle is spent only on a configuration the diagnostic
predicts will pass.

### Scale-up result, 2026-08-14 — falsified; 12b pin restored

gemma3:27b (digest `a418f583…`) ran the registered view on the same capture
ledger. Recall **4 of 13**, keep **11 of 165**. The miss-set is emphatically
not a subset of the 12b's: seven events every 12b configuration recalled were
lost (ev-003 through ev-007, ev-009, ev-010), while ev-008 — the assigned
action item both the 12b arm and the frontier roadmap missed — was recalled.
Prediction 1 falsified; per the preregistered falsifier, the next arm is
self-consistency rather than a still-larger model. The registered model pin
is restored to gemma3:12b, returning the registration byte-exact to
`cbbb4e24…`.

The cross-model picture, all at temperature zero on the same prompt:

| Arm | Keep of 165 | Recall |
| --- | --- | --- |
| 12b, registered view | 97 | 10/13 |
| 12b, ±2 window | 133 | 11/13 |
| 12b, coalesced units | 39 (of 71) | 9/13 |
| 27b, registered view | 11 | 4/13 |

Two facts worth more than another run. First, the KEEP/ABSTAIN criterion is
uncalibrated across models: the same words produce a 59% keep-rate from 12b
and a 7% keep-rate from 27b, so the gate's meaning does not transfer with the
prompt. Second, a deterministic union across the three 12b views — computable
from the retained diagnostics with no new inference — reaches 12/13 and no
further: **ev-011, a real assigned action stated across ten disfluent rows,
is missed by every view, both models, and the frontier roadmap.** Only the
human-reviewed draft caught it. Temperature-sampled majority voting remains
the registered next arm, but its ceiling should be read against that
universal miss: a majority cannot recover what no configuration keeps even
once.

The measured boundary, stated as the running conclusion: no tested local
configuration meets the 100%-recall gate on real disfluent meeting speech,
and the one instrument that has caught every event in this study is the
operator-reviewed evidence ledger itself.

### Product decision, 2026-08-14 — the generator is admitted at measured quality

The operator reviewed today's boundary and made the product call this study
existed to inform: generated notes enter Yawn as **cited drafts paired with
the transcript**, not as a record. Two inputs settled it. The measurement:
the best local configuration keeps 11 of 13 operator-locked events with a
citation path for every keep, and the miss class is characterized (assigned
actions and late-meeting items spread across short disfluent rows), not
anecdotal. The market check (Granola, Otter, Notion — vendor docs and
current reviews pulled 2026-08-14): every comparable tool ships the same
summary-plus-transcript pairing and none claims the summary is complete, so
the 100%-recall gate was the bar for a note that *replaces* its transcript —
a product nobody ships. That gate is retired for shipping and retained as a
research instrument.

The ship gate that replaces it, for any note-generation build that reaches
the app surface:

1. **Recall ≥ 11/13** on the operator-locked private-capture ledger under
   the registered configuration, re-measured after any change to model,
   prompt, view, or decoding.
2. **Every displayed point cites its transcript rows**, and the citation
   resolves on the meeting's own transcript surface. A point that cannot
   cite is not displayed.
3. **The note surface states its own incompleteness** — a generated note is
   labeled a draft from the transcript, with the transcript in the same
   view, per the product brief's standing rule that a tidy summary must
   never look like a complete record.
4. The keep budget (≤ 64) and time budget (≤ 900 s) stand unchanged.

This is a posture decision, not a run, so no registration digest changes.
The next work is app-side: an architecture decision on what runtime executes
the pinned model inside a local-only product, before any UI.

### Preregistration — MLX runtime re-measurement arm

The runtime decision (`docs/note-runtime-decision.md`) moves the shipped
generator from ollama to MLX-LM, and ship-gate condition 1 requires recall
re-measured after any runtime change. This arm measures it, before any app
code merges.

Candidate pin: `mlx-community/gemma-3-12b-it-qat-4bit` — the MLX conversion
of Google's QAT 4-bit release, the same weight family ollama's `gemma3:12b`
ships, so this is the closest available match to the measured configuration.
The exact model-tree digest is pinned after download, before any run.
Runtime identity: the documented MLX research recipe (CPython 3.14,
`mlx==0.32.0`, `mlx-lm==0.30.4`, `transformers==5.0.0rc1`), recorded
per-receipt as in the MLX admission harness.

Configuration under test: the ±2 fragment window view — the only measured
configuration that reaches the ship gate's 11/13 (ollama 12b: keep 133,
recall 11/13, miss {ev-011, ev-012}). Prompt, locators, decoding options,
batch shape, and budgets are unchanged from the registered contract; the
transport changes from ollama HTTP to in-process MLX-LM generation with the
same deterministic (temperature-zero) decoding.

Registered predictions, before any MLX token is generated:

1. Recall on the operator-locked capture ledger under the ±2 window view
   will be within one event of the ollama measurement: 10–12 of 13.
2. The miss-set will include ev-011 (missed by every configuration ever
   tested, both families, and the frontier roadmap).
3. No keep-count prediction is registered beyond the standing 64 gate;
   today's evidence says keep-rate is the least stable quantity across
   runtimes.

Falsifier: recall below 11/13 on this view fails ship-gate condition 1 for
this pin; per the runtime decision doc, the MLX runtime choice reopens
(next candidates: a different quantization of the same weights, then a
different model family — each its own preregistered arm, not silent
retries). A content-controlled diagnostic runs before any official gated
run, so an operator approval cycle is spent only on a configuration the
diagnostic predicts will pass.

### MLX diagnostic, unconstrained emission — transport failure, not a weights measurement

The first MLX diagnostics (gemma-3-12b-it-qat-4bit, ±2 window view, temp 0,
mlx-lm 0.30.4) never measured the weights. Unconstrained generation emitted
fenced JSON in a self-invented shape (a bare list keyed `classification`);
strict registered decoding refused all six batches. A measured shape adapter
recovered three batches — and each recovered batch kept 32 of 32 candidates.
The other three batches refused even adapted. Face-value tally (decisions 96
of 165, keep 96, "recall 11/13") is a keep-everything artifact: a transport
that keeps whatever it parses recalls events with no selectivity at all, and
blows the 64-keep gate while measuring nothing. Conclusion: ollama's
registered `response_format` was doing load-bearing enforcement, and format
constraint is a required transport property, not serialization detail.

### Preregistration amendment — constrained-verdict MLX transport

The next diagnostic replaces free generation with a constrained decoder built
on plain mlx-lm APIs (no new packages; runtime identity unchanged): the
response JSON is assembled deterministically in the registered shape and
offered order, and the model contributes exactly one greedy binary choice per
candidate — KEEP vs ABSTAIN — scored at the verdict position with the full
prompt and all prior forced tokens in context. This is the ollama
`response_format` grammar tightened to its decision content: order and shape
become exact by construction (registered decode's canonicalization becomes a
no-op), and duplicates, drops, and unknown locators become impossible.

Registered predictions, before any constrained token is scored:

1. All six batches decode strictly; decisions = 165 of 165.
2. Keep count: no prediction — calibration across transports is exactly what
   this arm measures (unconstrained QAT kept 100% where it parsed; ollama
   kept 81% on this view).
3. Recall: the standing prediction from the arm preregistration (10–12 of 13,
   ev-011 in the miss-set) carries over unchanged.

Falsifier unchanged: recall below 11/13 on this view fails ship-gate
condition 1 for this pin and reopens the runtime choice. If the constrained
arm passes as diagnostic, the official gated run re-runs it under a fresh
operator-approved lock before anything merges.

### Constrained-verdict result — pin falsified on keep calibration

The constrained transport worked exactly as registered: all six batches
decoded strictly, 165 of 165 decisions (prediction 1 held). The verdicts did
not: **keep 165 of 165, abstain 0**. Recall "13/13" is vacuous — a classifier
that keeps everything recalls everything and selects nothing — and the keep
gate fails at 2.6x the 64 budget, so this pin fails ship-gate condition 4.

A margin probe on batch 1 rules out the comparison as the artifact: the
first-token logit gap and the full teacher-forced sequence-logprob gap agree
on every candidate (disagreement 0/32), KEEP wins 32/32 with min +6.375,
median +10.75, max +12.5 nats, and no candidate comes within 1 nat. The
model is not near a boundary being tipped by tokenization; the quantized
weights are certain.

The comparison that matters: ollama's `gemma3:12b` — the same nominal QAT
weight family — abstained on 19% of these candidates (keep 133/165) on the
same view at the same temperature. The MLX 4-bit QAT conversion abandons
abstention wholesale. Conclusion for the record: **quantization artifact
identity, not weight-family identity, is a behavioral variable.** A model
pin must name the exact artifact measured; "same weights, different
quantizer" is a different model.

### Preregistration — higher-precision quantization arm

Per the runtime decision doc's ordered fallback ("a different quantization
of the same weights" before "a different model family"): next arm is
`mlx-community/gemma-3-12b-it-8bit`, digest pinned after download, same
constrained-verdict transport, same ±2 view, temperature zero.

Registered predictions:

1. Strict decode 165/165 — transport property, carries over.
2. Directional keep prediction: 8-bit abstains on some candidates
   (keep < 165). This is the discriminator: if 8-bit also keeps everything,
   quantization precision is exonerated and the divergence is in the MLX
   prompt assembly (chat-template rendering vs ollama's template), which
   becomes the next preregistered investigation before any further model
   download.
3. Ship falsifier unchanged: recall < 11/13 on this view, or keep > 64,
   fails the pin.

### 8-bit result — quantization exonerated; the divergence is prompt assembly

`mlx-community/gemma-3-12b-it-8bit` under the identical constrained-verdict
transport: keep **165 of 165**, abstain 0, all batches strict — byte-for-byte
the same verdict profile as the 4-bit QAT arm. Prediction 2's discriminator
fires in the exonerating direction: two quantizations of the same weights at
different precisions agree completely, so quantization precision is not the
cause. The keep-everything behavior comes from what the MLX transport shows
the model — chat-template rendering, BOS handling, or the forced-serialization
context at the verdict position — relative to whatever ollama's build showed
it. Per the preregistration, the next step is the prompt-assembly parity
investigation (byte-level comparison of rendered prompts and generation
context between the two transports) before any further model download.

### Prompt-assembly parity — the rendering difference, measured at source

Byte-level comparison of the two transports' rendering of the same
system+user pair:

- HF/MLX `apply_chat_template` (gemma-3): one merged turn —
  `<bos><start_of_turn>user\n{system}\n\n{user}<end_of_turn>\n<start_of_turn>model\n`.
- ollama's gemma3 template (`ollama show gemma3:12b --template`): the system
  message is its **own** user turn —
  `<start_of_turn>user\n{system}<end_of_turn>\n<start_of_turn>user\n{user}<end_of_turn>\n<start_of_turn>model\n`
  (BOS added by the runtime).

### Preregistration — ollama-structure rendering arm

Same constrained-verdict transport, same ±2 view, temperature zero,
gemma-3-12b-it-qat-4bit (the family match to ollama's Q4 QAT build), with one
change: the prompt is rendered in ollama's two-turn structure instead of the
HF merged-turn structure, BOS prepended once.

Registered predictions:

1. Strict decode 165/165 (transport property, carries).
2. Directional: abstention reappears (keep < 165). If keep is materially
   below 165 and within sight of ollama's 133, prompt structure is the
   dominant variable and the MLX transport adopts the ollama rendering for
   the official arm. If keep stays 165, the remaining suspects are the
   forced-serialization context at the verdict position and runner-side
   sampling internals, in that order — each its own arm before any new model.
3. Ship falsifier unchanged: recall < 11/13 or keep > 64 fails the pin.

### Ollama-structure result — prompt structure is the dominant variable, and the gate is jointly unsatisfiable

Two-turn rendering, same weights, same transport: keep **136 of 165**,
recall **11/13** (prediction 2 met — within three keeps of ollama's 133, so
the MLX transport adopts the ollama rendering). Per-batch profile is not
calibrated selectivity: batch 1 abstained 29 of 32, batches 2–6 kept
everything, and the miss-set moved again — {ev-001, ev-002}, the meeting's
opening, where ollama's 133-keep run missed {ev-011, ev-012}, the closing.

The larger fact this run makes unavoidable: **no measured configuration on
any transport satisfies the ship gate's two quantitative conditions
jointly.** Every configuration reaching recall ≥ 11/13 keeps 97–136 of 165
candidates — the keep-64 budget fails by 1.5–2.1x, and a "note" citing ~80%
of the transcript rows is not a selective draft. Every configuration
respecting the keep budget (27b: 11 keeps; coalesced view: 39) collapses to
recall 4/13–9/13. The precision/recall frontier of the gemma family on this
task, measured across two transports, three quantizations, two scales, and
four views, does not pass through (recall ≥ 11/13, keep ≤ 64). The ship
gate as ratified embeds a joint constraint nothing measured has met; the
morning's product decision priced the recall number but not the keep bloat.
This goes back to the operator before any further arm.

### Operator decision + preregistration — deterministic pruning stage

The operator chose to keep both gate numbers and measure a third path: a
deterministic second stage that prunes the recall-satisfying keep set down
to the 64 budget while preserving at least one acceptable anchor per locked
event. No model runs in the pruner; it is local code over verdicts, so it
composes with the bridge's existing decode step and reads its budget from
the registration like everything else.

Instrument: the adopted configuration (gemma-3-12b-it-qat-4bit, constrained
verdicts, ollama two-turn rendering, ±2 view) re-runs once with a decisions
dump (candidate ids and verdicts only, private file). Pruning strategies
are then evaluated OFFLINE against the dumped keep set and the locked
ledger — no further inference. The strategy family registered for
evaluation, all deterministic:

1. Contiguous-run collapse: adjacent keeps (overlapping visible windows)
   merge into one run; each run retains one representative anchor
   (first/middle/longest — each scored).
2. Bare-assent drop: keeps whose anchor matches the registered assent
   pattern are pruned first.
3. Per-region cap: at most N keeps per transcript section, N swept.
4. Compositions of 1–3.

Gate for this arm: some registered strategy yields keep ≤ 64 AND retains an
acceptable anchor for all events the unpruned set recalled (11/13 here).

Honesty constraint, recorded up front: any pruner selected on this ledger
is FITTED to one meeting (n=1). Passing offline does not clear the ship
gate; it authorizes a validation run on a second, freshly reviewed capture
before any official gated run. A pruner that only works on the meeting it
was tuned on is a memorized answer, not a capability.

Prediction: contiguous-run collapse alone brings keep under 64 (the 136
keeps tile mostly contiguous spans; runs, not points, are what the model
is really marking). No prediction on whether anchor retention survives
representative selection — that is what the offline evaluation measures.

### Pruning arm result — falsified, and the reason reframes the program

Offline evaluation (38 strategies: contiguous-run collapse × gap × representative,
assent-drop, section caps, compositions) against the dumped MLX keep set:
**zero strategies pass.** The dump shows why no pruner could: the 136 keeps
are one contiguous slab (anchor turns 0–163, a single 30-turn abstain
window). Instrument correction recorded: the evaluator's first assent match
recompiled the registered pattern without its flags (0 matches vs the
registered object's 20); corrected before any conclusion was drawn.

### The mechanism, isolated — block verdicts, not judgment

Two discriminators close the causal chain:

1. Unconstrained emission + two-turn rendering: keep-all in every parsed
   batch — the teacher-forced skeleton is exonerated.
2. The registered ollama arm re-run with `repeat_penalty` explicitly 1.0
   (the registered transport never set it, so 1.1 was silently active in
   every prior ollama measurement): keep **133**, recall **11/13** — totals
   identical to the penalty-default run, so the penalty is exonerated too.
   But the distribution is the finding: batches 1–4 and 6 keep all;
   **batch 5 abstains all 32.** Batch 5 spans the turns holding ev-011 and
   ev-012 — the ollama arm's entire miss-set. The MLX two-turn arm put its
   abstain block on batch 1 and missed ev-001/ev-002.

Unified reinterpretation of every number this program has produced: at
temperature zero, gemma-family models emit **regionally uniform verdict
blocks per response** — whole batches flip KEEP or ABSTAIN together. What
looked like view-sensitivity, scale miscalibration, transport divergence,
and calibrated abstention is one mechanism: which batch catches the abstain
block. Recall differences measure block placement, not evidence judgment.
Per-candidate selectivity has never been observed in any configuration:
2 runtimes, 2 penalties, 3 quantizations, 2 scales, 2 renderings, 2
decoding modes, 4 views.

The one untested cell that would prove or refute per-candidate judgment:
**batch size 1** — 165 independent single-candidate calls, where no block
larger than one candidate is possible. Estimated ~4–5 h at current prompt
sizes. Not run; whether to spend it is the operator's call, recorded as the
only remaining registered arm on this model family.

### Preregistration — batch-size-1 arm (operator-authorized, final arm on this family)

165 independent single-candidate calls: ollama transport (gemma3:12b,
digest f4031aab…), ±2 view, registered schema per call, temperature zero,
`repeat_penalty` explicitly 1.0, `num_predict` per the registered formula at
one candidate. No response can contain a verdict block larger than one
candidate, so block placement is eliminated as a mechanism by construction.
Decisions dumped (ids and verdicts only, private).

Registered predictions:

1. All 165 calls decode strictly.
2. The block-verdict hypothesis predicts near-uniform verdicts at n=1
   (keep ≈ 165 or ≈ 0): a model that flips whole batches is reading region
   texture, not candidates, and a region of one still reads as its texture.
   Per-candidate judgment predicts an interior keep count with keeps
   concentrating on event anchors.
3. Caveat recorded before the run: single-candidate calls remove
   cross-candidate context, which changes the task. A keep-all outcome
   means candidates look keepable in isolation — that still disqualifies
   the family for temp-0 selection, since both the batched and unbatched
   forms would then have failed for different reasons.

Disposition rule: interior keep count with recall ≥ 11/13 at keep ≤ 64 →
the batching redesign becomes the registered product path. Near-uniform
verdicts → this model family is disqualified for candidate selection and
today's boundary is terminal pending a new model generation.

### Batch-size-1 result — block hypothesis refuted; the family has per-candidate judgment

All 165 single-candidate calls decoded strictly (prediction 1 held).
Keep **71 of 165**, scattered across **35 separate regions** (the batched
slab had 2), bare-assent keeps 3. Recall **12 of 13** — the highest any
single configuration has measured, equal to the old cross-view union
ceiling. The block-verdict prediction (near-uniform verdicts at n=1) is
refuted: batching was destroying real per-candidate judgment, not
revealing its absence.

The miss is ev-005 (PROPOSAL). **ev-011 — missed by every batched
configuration, every view, both scales, and the frontier roadmap — is
caught.** The "universal miss" was a block artifact.

Registered pruning strategies re-evaluated offline on this keep set:
**five pass** the (keep ≤ 64, recall preserved at 12/13) rule —
contiguous-run collapse at gap 1 (rep first/longest/ends: keep 35/35/51)
and gap 2 (rep middle/longest: keep 20/20). Strategy selection is
deliberately deferred to validation: choosing among five passes fitted to
one meeting is the overfit the preregistration warned against.

### Disposition — batching redesign is the registered product path

Per the arm's disposition rule: interior keeps, recall 12/13, and pruned
keep well under 64 → the product pipeline becomes: single-candidate
verdicts → deterministic contiguous-run collapse → cited excerpts. Two
registered steps remain before any official gated run, in order:

1. **MLX batch-size-1 re-measurement** on this ledger (the ship runtime is
   MLX; today's n=1 arm ran on ollama, and transport parity at n=1 is
   unmeasured). Single-candidate prompts are small; cost is comparable to
   today's run.
2. **Second-capture validation**: a fresh meeting, operator-reviewed ledger
   and lock, then the n=1 pipeline with all five passing pruners scored.
   Only a pruner that passes on the meeting it was not fitted to advances
   to the official registration change (±2 view, two-turn rendering, MLX
   runtime identity, batch size 1, the surviving pruner, and the fresh
   operator lock, as one preregistered adoption).

### MLX batch-size-1 parity — judgment survives the ship transport

Registered step 1 ran: gemma-3-12b-it-qat-4bit, constrained verdicts,
two-turn rendering, batch size 1, same ledger. Keep **104 of 165** —
interior and scattered, more permissive than ollama's 71 but nothing like
the batched slab — and recall **12/13 with the identical miss, ev-005**.
Per-candidate judgment is a property of unbatched prompting, not of the
ollama runtime.

Pruner scoring on the MLX keep set narrows the field to one: of the five
fdd59c81-passing strategies, only **contiguous-run collapse (gap 1,
longest-anchor representative)** passes on both transports (MLX: keep 27,
recall 12/13). The second-capture validation scores all five as
preregistered, but ship candidacy requires the both-transport survivor.

### Second-capture validation — ledger locked, run authorized

Meeting 81b2fe54 (299-turn single-speaker internal presentation — a
different meeting genre from the 630 1:1): 13 agent-drafted events were
bulk-ratified by the operator (provenance caveat in the packet's
DECISION-RECORD.md), promoted to ledger 77b4173f…, and the operator
approved lock 622dd23a… scoped to the batch-size-1 ollama arm plus offline
pruner scoring. The run is in flight; its script verifies the approved
digest against the lock bytes before any inference.

### Validation matrix complete — the pipeline clears the ship gate in all four cells

Meeting 2 (81b2fe54), MLX transport, batch size 1, under the operator's
extended lock: unpruned keep **152 of 300**, recall **13/13** — the second
perfect out-of-sample recall of the night. (Procedural note for the record:
the first MLX launch on this ledger was killed before any inference
completed because the approved lock named the ollama transport only; the
operator granted a scope extension before the relaunch. The lock protocol
held because it was enforced against its author, which is the point.)

The full 2×2, batch-size-1 unpruned:

| Cell | Keep | Recall |
| --- | --- | --- |
| fdd59c81 · ollama | 71/165 | 12/13 |
| fdd59c81 · MLX | 104/165 | 12/13 |
| 81b2fe54 · ollama | 90/300 | 13/13 |
| 81b2fe54 · MLX | 152/300 | 13/13 |

And the pruner that survives everywhere — **contiguous-run collapse, gap 1,
longest-anchor representative** — against the ship gate (recall ≥ 11/13,
keep ≤ 64):

| Cell | Keep after prune | Recall | Ship gate |
| --- | --- | --- | --- |
| fdd59c81 · ollama | 35 | 12/13 | pass |
| fdd59c81 · MLX | 27 | 12/13 | pass |
| 81b2fe54 · ollama | 48 | 12/13 | pass |
| 81b2fe54 · MLX | 54 | 11/13 | pass |

No other strategy passes all four cells. Margins recorded honestly: the
thinnest cell (81b2fe54 · MLX) sits exactly at the 11/13 bar, MLX keep
rates run ~1.5x ollama's and vary across meetings (63% vs 51%), and ev-012
is pruned away in both meeting-2 cells — the pruner's known cost lands on
events whose best anchors sit mid-run. The measured pipeline for adoption:
single-candidate verdicts → gap-1/longest collapse → 27–54 cited excerpts.

### What remains before the app surface

One preregistered registration change, drafted for a fresh operator lock:
±2 view, two-turn rendering, MLX runtime identity, batch size 1, the
gap-1/longest pruning stage, and gates restated against it — then the
official gated run, then the four parked branches wire it in per the merge
checklist in docs/note-runtime-decision.md.

### Operator delegation — 2026-08-14 late evening

The operator granted standing authorization for the remainder of the
adoption thread: "be smart. go autonomous. you understand the goal. you
don't need my approval to get there." Recorded scope, as understood: the
product registration below, fresh ledger/lock cycles on the two existing
capture ledgers with approvals recorded against this delegation, the
official gated runs, merging the four parked branches into local main, and
wiring the pipeline — with no remote pushes, no external hosting or
publishing, and no new meeting data. Anything outside that scope still
returns to the operator.

### Preregistration — product registration v1 (the adoption)

A second registration block, `PRODUCT_RUN`, lands in
`notes/candidate_first.py` beside the untouched research registration
(whose digest `cbbb4e24…` must remain byte-identical — asserted in the
self-test). Field-level content, fixed before implementation:

- Generator: `PRODUCT_CONTRACT` — the registered contract with the ±2
  visible window (`visible_window: 2`, five-fragment cap, two-fragment
  context strings); STRATEGY_BROAD; corpus-independent (no QMSum manifest
  pin — manifests derive per capture under the contract digest).
- Classifier: `mlx-community/gemma-3-12b-it-qat-4bit`, snapshot
  `66fc51ef…`, model tree digest `48dfcf43…` (tree_sha256 over the
  snapshot, .cache excluded); runtime identity CPython 3.14 / mlx 0.32.0 /
  mlx-lm 0.30.4; transport `mlx-constrained-verdict/1` (deterministic
  skeleton, one greedy first-token KEEP/ABSTAIN choice per candidate);
  prompt rendering `gemma3-two-turn/1` (system as its own user turn, BOS
  once); batch size 1; temperature 0.
- Pruner: contiguous-run collapse, gap 1, longest-anchor representative,
  earliest-ordinal tie-break — the only strategy that passed all four
  validation cells.
- Gates, applied to the PRUNED set: recalled events × 13 ≥ 11 × locked
  events (the 11/13 ship ratio, ledger-size independent); keep ≤ 64;
  elapsed ≤ 900 s.

Validation basis: the completed 2×2 matrix above (two meetings, two
transports; unpruned recall 12–13/13, pruned always within gates on the
adopted cells). Implementation follows this entry.

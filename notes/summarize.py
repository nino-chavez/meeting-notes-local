#!/usr/bin/env python3
"""Transcript to notes, locally, with the fabrication checked rather than hoped for.

This is the second half of the pipeline. The capture spike proved audio can be
split into two legs; it also proved that on speakers the split is fiction. So
this half cannot assume it knows who said what, and the interesting question is
not "can a local model summarize a meeting" but "does it invent things when the
speaker labels are taken away."

Two things make that answerable instead of a matter of taste:

  1. The corpus ships a human-written summary. Notes are compared against a
     reference, not against a feeling.
  2. The unattributed contract is checked mechanically. If the model names a
     speaker whose label was never in its input, that is a fabrication with no
     other explanation, and it is found by string search rather than by reading.

Silent truncation is treated as a failure, not a degradation: Ollama defaults
`num_ctx` to 4096 regardless of what the model supports, which would summarize
the first eight minutes of a forty-minute meeting and say nothing about it. The
runner compares the server's own reported prompt token count against the prompt
it sent and refuses the result if they disagree.

Usage:
    python notes/summarize.py notes/corpus/ES2004c.json
    python notes/summarize.py notes/corpus/ES2004c.json --strip
    python notes/summarize.py notes/corpus/ES2004c.json --simulate-bleed
    python notes/summarize.py spike/out/transcript.json
    python notes/summarize.py --self-test
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from transcript import CHANNEL, NAMED, NONE, Transcript, Turn, load, qmsum_reference

OLLAMA = "http://localhost:11434"
DEFAULT_MODEL = "llama3.1:latest"

# Ollama silently clamps to 4096 unless told otherwise. 32k holds a ~90-minute
# meeting at the ~3.7 chars/token these transcripts run at.
DEFAULT_NUM_CTX = 32768

SECTIONS = """\
Output exactly these markdown sections, in this order, and omit any section that
would have no real content:

## Summary
Three to six sentences on what the meeting was about and where it landed.

## Decisions
What was actually settled. Not what was discussed.

## Action items
What someone committed to do next.

## Open questions
What was raised and left unresolved."""

BASE_RULES = """\
You are writing notes from a meeting transcript.

Rules that override everything else:
- Every statement you write must be supported by the transcript. If you are not
  sure something was said, leave it out.
- Never invent names, numbers, dates, quantities, or deadlines. If the
  transcript does not contain a figure, your notes must not contain one.
- Prefer omitting a section to padding it. An empty section is a true statement
  about the meeting; a padded one is not.
- Write plainly. No preamble, no sign-off, no "in this meeting" throat-clearing.

""" + SECTIONS

# The two-pass prompts. Omission, not invention, is what the measurements in
# EVAL.md keep finding, and a single pass over a 57-minute transcript compresses
# roughly 8600 words into 150 — a 57:1 ratio at which dropping things is the
# expected behaviour rather than a defect. These split that into a slice-level
# pass that is not allowed to compress and a merge that is not allowed to select.
EXTRACT_RULES = """\
You are reading ONE SLICE of a longer meeting transcript and pulling out the raw
material for its notes. This is not the notes. Something left out here cannot be
recovered later, because no later step sees this transcript again.

Rules that override everything else:
- Every line must be supported by this slice. Never invent names, numbers,
  dates, quantities, or deadlines.
- Completeness beats brevity. This is the opposite of summarising: if something
  might be a decision, a commitment, or an unresolved question, include it.
- Keep the transcript's own words for the specific things involved — documents,
  systems, datasets, metrics, deliverables. A commitment stripped of the name of
  the thing it concerns cannot be reconstructed downstream, and that is the
  failure this pass exists to prevent.
- One item per line, each starting with DECISION:, ACTION:, or QUESTION:.
- A slice is mostly ordinary conversation. If it contains none of these, output
  nothing at all.
- No preamble, no summary, no headings, no commentary."""

CONSOLIDATE_RULES = """\
You are turning an ordered list of items, extracted from consecutive slices of
one meeting, into that meeting's notes.

Because the slices overlap and people repeat themselves, the same commitment
often appears several times in slightly different words.

Rules that override everything else:
- Use ONLY the items given. Add nothing, however plausible it would be.
- Merge duplicates: several lines describing one commitment become one line,
  keeping the most specific wording, including the names of documents and
  systems.
- Do NOT drop an item because the list is long. Every distinct decision, action
  and open question in the input must survive into the output. This is a
  de-duplication task, not a selection task — you are not choosing the important
  ones, you are removing the repeated ones.

""" + SECTIONS

# The one place the three attribution levels diverge. Everything above is shared;
# what changes is who the notes are permitted to name.
CONTRACTS = {
    NAMED: """\
Speaker labels in this transcript are reliable. Attribute a decision or an
action item to a speaker when the transcript makes the owner explicit. When the
owner is not explicit, write the item without an owner rather than guessing.""",
    CHANNEL: """\
This transcript is labelled only "Me" and "Them". "Me" is the person who
recorded the meeting; "Them" is everyone else, and they are NOT distinguished
from one another. You may write "you" for things labelled Me. You must never
invent a name for anyone on the Them side, and you must never write as if Them
were a single identifiable person.""",
    # No illustrative sentences here, deliberately. An earlier version of this
    # contract demonstrated agentless phrasing with two example sentences, and
    # the model copied both into its notes as decisions the meeting had reached
    # — in a transcript where neither subject is mentioned once. Style examples
    # made of content words are indistinguishable from content. The grammar is
    # described instead, and the groundedness check below exists because that
    # failure got past every other check in this file.
    NONE: """\
This transcript has NO speaker labels. Who said what is not recoverable, because
the microphone was picking up the other participants through the speakers, so
the channels cannot be trusted.

Therefore: write every decision and every action item WITHOUT an actor. Put the
thing that was decided in the subject position and leave the doer out entirely.
Where a sentence forces an owner, use "someone".

Do not attribute anything on the basis of who was speaking — that information
does not exist here. You may still report a name if the words themselves assign
the work, because that comes from what was said rather than from the channel.
Do not write "you", "I", "he", or "she" as the doer of an action. Do not infer
that two statements came from the same person. An action item with no
identifiable owner is a correct and complete answer.""",
}

# What the unattributed contract actually forbids is claiming that a *particular
# person* did something, because that is precisely what bleed destroys. It does
# not forbid saying the meeting as a whole settled on something — "the group
# agreed", "they decided", "we landed on X" make no identity claim, and a note
# barred from them would be unreadable.
#
# So the line is singular versus collective. "you", "I", "he", "she" individuate
# and are fabrication. "we", "they", "the group", "someone" do not.
ATTRIBUTION_VERBS = (
    r"will|shall|is\s+to|are\s+to|agreed|committed|decided|owns?|takes?|took|"
    r"said|says|proposed|suggested|volunteered|raised|presented|led|reported|"
    r"asked|noted|argued|confirmed"
)

LEAK_PATTERNS = [
    # Singular actors doing things. `they`/`we` deliberately absent.
    re.compile(rf"\b(?:you|he|she)\s+(?:{ATTRIBUTION_VERBS})\b", re.IGNORECASE),
    # The lookbehind excludes upper case as well as lower: it used to be
    # `(?<![a-z])`, which let "AI will be used to generate X" register as the
    # operator personally committing to something. Case-sensitivity is still
    # wanted for the "I" itself, so this cannot fold into re.IGNORECASE.
    re.compile(rf"(?<![A-Za-z])I\s+(?:{ATTRIBUTION_VERBS})\b"),
    # An explicit owner column, whatever fills it.
    re.compile(r"\b(?:assigned to|owner|action owner|responsible)\s*[:—-]\s*\S", re.IGNORECASE),
]

# At `channel` the operator IS a known identity, so "you agreed to X" is a
# correct claim rather than a fabricated one. Everything that individuates the
# far side is still forbidden.
CHANNEL_LEAK_PATTERNS = [
    re.compile(rf"\b(?:he|she)\s+(?:{ATTRIBUTION_VERBS})\b", re.IGNORECASE),
    re.compile(r"\b(?:assigned to|owner|action owner|responsible)\s*[:—-]\s*\S", re.IGNORECASE),
]


def ollama_chat(model: str, system: str, user: str, num_ctx: int, timeout: int):
    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "options": {
            "num_ctx": num_ctx,
            # Notes are an extraction task. Sampling here buys variation in
            # exactly the dimension where variation is a defect.
            "temperature": 0.0,
        },
    }).encode()
    req = urllib.request.Request(
        f"{OLLAMA}/api/chat", data=body, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.URLError as e:
        raise SystemExit(
            f"cannot reach Ollama at {OLLAMA} ({e.reason}).\n"
            "Start it with `ollama serve`, and check the model is pulled:\n"
            f"  ollama pull {model}"
        ) from e


def check_one_context(response: dict, prompt: str, num_ctx: int) -> dict:
    """Did the server actually read the whole prompt for a single call?

    `prompt_eval_count` is the server's own count of the tokens it processed. If
    the prompt is long and that number lands suspiciously near a context
    boundary, the tail was dropped — and the notes will look perfectly
    well-formed while covering only the opening.
    """
    counted = response.get("prompt_eval_count")
    estimate = len(prompt) / 3.7
    if counted is None:
        return {"ok": None, "reason": "server did not report prompt_eval_count"}
    truncated = counted >= num_ctx - 64 or (estimate > 1.35 * counted and estimate > 2000)
    return {
        "ok": not truncated,
        "counted": counted,
        "estimated": int(estimate),
        "num_ctx": num_ctx,
        "reason": (
            f"server read {counted} prompt tokens for a prompt estimated at "
            f"{int(estimate)}; the tail was dropped"
        ) if truncated else "",
    }


def check_context(calls: list[dict], num_ctx: int) -> dict:
    """The same check across every model call a run made.

    A multi-pass run reads the transcript in slices, so there is no single
    prompt to check — and a strategy that exists to improve recall would be
    self-defeating if one slice in the middle were silently truncated. One bad
    call condemns the run: the notes cannot be better than the worst read.
    """
    results = [check_one_context(c["response"], c["prompt"], num_ctx) for c in calls]
    if not results:
        return {"ok": None, "reason": "no model calls recorded", "calls": 0}
    bad = [(c, r) for c, r in zip(calls, results, strict=True) if r["ok"] is False]
    unverified = [r for r in results if r["ok"] is None]
    if bad:
        call, res = bad[0]
        return {**res, "calls": len(calls),
                "reason": f"{call['label']}: {res['reason']}"
                          + (f" (and {len(bad) - 1} other calls)" if len(bad) > 1 else "")}
    if unverified:
        return {**unverified[0], "calls": len(calls)}
    return {**max(results, key=lambda r: r["counted"]), "calls": len(calls)}


def check_attribution(note: str, transcript: Transcript, stripped_speakers: list[str]) -> dict:
    """Whether the notes claimed a speaker identity the input did not support.

    Applies at `none` and at `channel`, because both are capture-derived levels
    where identity is partly or wholly unavailable. Only `named` is exempt.

    At `none` the model was shown a transcript with the labels removed, so a
    role name it reproduces cannot have come from its input.

    At `channel` the model was shown "Me" and "Them". "Me" is a real identity —
    the person recording — so attributing to "you" is correct there. "Them" is
    not: it is an undifferentiated far side, and treating it as one actor is the
    same fabrication in a different costume. `channel` is what the *recommended*
    capture produces, since headphones mean low bleed, so leaving it unchecked
    would leave the default path unenforced.

    "Me" and "Them" are always in the forbidden-name set, not just the corpus
    speakers. On a real capture the spike has already dropped the labels, so
    `stripped_speakers` arrives empty and the name arm would otherwise be a
    no-op on exactly the path that matters.

    The bare-name version of this check does not survive contact with real
    transcripts. AMI's speaker roles are "Marketing", "User Interface",
    "Industrial Designer" — all of which are also ordinary phrases in a meeting
    *about* designing a product. A note that correctly says the group discussed
    "market trends, user interface, and materials" gets flagged for naming a
    speaker it never named. That first-pass check reported a fabrication that had
    not happened, which is the same failure the tool exists to prevent, pointed
    the other way.

    So a name only counts when it sits in an attributing position: doing
    something, or credited as the source of something.
    """
    if transcript.attribution == NAMED:
        return {"applies": False}

    if transcript.attribution == CHANNEL:
        forbidden = ["Them"]
        patterns = CHANNEL_LEAK_PATTERNS
    else:
        forbidden = [*stripped_speakers, "Me", "Them"]
        patterns = LEAK_PATTERNS

    names = []
    for s in forbidden:
        n = re.escape(s)
        attributing = (
            rf"\b{n}\b\s*(?:{ATTRIBUTION_VERBS})\b"          # Marketing agreed …
            rf"|\b(?:by|from|per|according to)\s+{n}\b"       # … raised by Marketing
            rf"|\b{n}(?:'s|’s)\s+(?:action|task|commitment|point)"  # noqa: RUF001
            rf"|^\s*[-*]?\s*{n}\s*[:—-]"                      # Marketing: … / - Marketing —
        )
        if re.search(attributing, note, re.IGNORECASE | re.MULTILINE):
            names.append(s)

    leaks = [m.group(0) for p in patterns for m in p.finditer(note)]
    return {
        "applies": True,
        "ok": not names and not leaks,
        "named_speakers": names,
        "actor_phrases": sorted(set(leaks)),
    }


# Vocabulary a well-formed note contains because it is a note, not because the
# meeting was about it. Summary prose reaches for these regardless of subject.
_NOTE_REGISTER = {
    "note", "notes", "transcript", "meeting", "speaker", "speakers",
    "summary", "decision", "decisions", "action", "actions", "item", "items",
    "question", "questions", "open", "discussed", "discussion",
    "group", "team", "someone", "agreed", "decided", "raised", "unresolved",
    "including", "various", "related", "regarding", "several", "aspects",
    "issues", "topics", "point", "points", "made", "also", "next", "follow",
    "about", "there", "their", "these", "those", "which", "would", "could",
    "should", "will", "been", "were", "with", "that", "this", "from", "have",
    "into", "such", "than", "then", "they", "them", "what", "when", "still",
    "needs", "need", "well", "more", "most", "some", "other", "over",
    "covered", "handle", "handling", "built", "build", "touched", "management",
    "provide", "provided", "providing", "ensure", "remains", "continue",
    "additional", "particularly", "possibility", "consistent",
}


def _words(s: str) -> set[str]:
    return set(re.findall(r"[a-z]{4,}", s.lower()))


# Four words: long enough that ordinary phrasing does not collide by accident,
# short enough to catch a lifted clause rather than only a whole sentence.
_ECHO_NGRAM = 4


def _ngrams(s: str, n: int) -> set[str]:
    """Every n-word sequence in `s`, normalised to bare lowercase words."""
    words = re.findall(r"[a-z']+", s.lower())
    return {" ".join(words[i:i + n]) for i in range(len(words) - n + 1)}


def check_prompt_echo(note: str, source_text: str, system: str) -> dict:
    """Content the notes took from the instructions rather than from the meeting.

    This is the failure that motivated every check below it. The unattributed
    contract used to demonstrate agentless phrasing with two example sentences.
    The model lifted both into its notes as decisions the meeting had reached —
    in a transcript where neither subject occurs once. Those notes were
    well-formed, named nobody, invented no numbers, and were read in full, so
    the context, attribution and number checks all passed a wholly fabricated
    decision. Numbers were the wrong thing to watch on their own: fabricated
    prose carries no digits.

    The examples are gone, but the prompt is a file and files get edited. This
    check makes reintroducing content words into any instruction an immediate,
    named failure rather than something discovered in a note months later.

    Matched on phrases, not single words. The first version compared word sets
    and claimed there was "no innocent reason for a word to travel that route",
    which is simply false: it gated three real runs on "rather", "involved" and
    "leave", ordinary register vocabulary that happened to sit in the rules and
    not in that particular meeting. The defence was `_NOTE_REGISTER`, a
    hand-maintained list of innocent words, and a list that grew by three in one
    evening was never going to converge.

    A phrase is the right unit anyway, because the failure this exists for was
    two whole example *sentences* lifted verbatim. Four consecutive words shared
    with the instructions and absent from the meeting is strong evidence; one
    word is noise. A phrase whose content words all appear in the transcript is
    not an echo either — the model can reach the prompt's phrasing honestly by
    way of the meeting, which is the third self-test control.
    """
    src_words = _words(source_text)
    src_stems = {w[:5] for w in src_words}
    note_grams = _ngrams(note, _ECHO_NGRAM)
    shared = note_grams & _ngrams(system, _ECHO_NGRAM)

    echoed = []
    for gram in sorted(shared):
        content = [w for w in gram.split() if len(w) >= 4 and w not in _NOTE_REGISTER]
        # Nothing but register words: no content travelled, whatever matched.
        if not content:
            continue
        # Every content word is in the meeting, so the phrasing is reachable
        # from the transcript and the overlap with the prompt proves nothing.
        if all(w in src_words or w[:5] in src_stems for w in content):
            continue
        echoed.append(gram)
    return {"ok": not echoed, "echoed": echoed}


def check_grounding(note: str, source_text: str) -> dict:
    """Content words in the notes that appear nowhere in the transcript.

    Advisory, not a gate, and the distinction is the point. Matching is by
    five-character prefix so ordinary paraphrase survives — "anonymization" is
    grounded by "anonymize" — but a summarizer's job is to compress and
    rephrase, so some legitimate word choice will always land here. Run against
    real notes it surfaced the genuine fabrications ("launch", "supplier")
    alongside innocent paraphrase ("covered", "handle") with nothing in the
    lexical signal to separate them.

    Reporting it as a verdict would mean either failing good notes or padding
    the ignore list until it stops catching anything. So it prints terms worth
    a glance and stays out of the pass/fail decision.
    """
    source_stems = {w[:5] for w in _words(source_text)}
    ungrounded = sorted(
        w for w in _words(note)
        if w not in _NOTE_REGISTER and w[:5] not in source_stems
    )
    return {"ok": not ungrounded, "ungrounded": ungrounded}


def _section(note: str, heading: str) -> list[str]:
    """The non-empty lines under one `## Heading`, up to the next heading."""
    out, inside = [], False
    for line in note.splitlines():
        if line.strip().startswith("##"):
            inside = heading.lower() in line.lower()
            continue
        if inside and line.strip():
            out.append(line.strip())
    return out


def check_owner_grounding(note: str, transcript: Transcript) -> dict:
    """At `named`, did the person on the hook actually say anything like it?

    This is the check the `named` level was missing, and it guards the failure
    with the worst consequences of any in this file: an action item that puts a
    real colleague's name against a commitment they never made. `check_
    attribution` deliberately does not apply here — at `named` the model is
    *supposed* to name people — so nothing was watching the one level where the
    names belong to actual coworkers.

    It found a real case immediately. On a genuine 37-minute Meet transcript the
    notes put one attendee down as reviewing and giving feedback on the project
    plan. What that person actually offered was feedback in the first sync
    meeting. Real person, real offer, wrong object — the kind of drift that
    survives a proofread because every element of it is individually true.

    Advisory, and it has to be: work is frequently assigned *to* someone by
    someone else, and the owner may say nothing more than "yeah". Low overlap is
    a prompt to check the attribution, not proof it is wrong.
    """
    if transcript.attribution != NAMED:
        return {"applies": False}

    speakers = transcript.speakers
    if not speakers:
        return {"applies": False}

    said = {
        s: _words(" ".join(t.text for t in transcript.turns if t.speaker == s))
        for s in speakers
    }
    everything = _words(transcript.render())
    participant_words = {w for s in speakers for w in _words(s)}
    # "input", "provide", "share" describe the shape of a commitment rather than
    # its substance, and appear in notes far more than in speech.
    participant_words |= {"input", "provide", "share", "shared", "providing"}

    weak = []
    for line in _section(note, "Action items") + _section(note, "Decisions"):
        for s in speakers:
            # Surnames are rare enough in speech that first names carry the match.
            first = s.split()[0]
            if not re.search(rf"\b(?:{re.escape(s)}|{re.escape(first)})\b", line, re.IGNORECASE):
                continue
            # Every participant's name comes out, not just this owner's. An item
            # with two owners would otherwise be judged partly on whether each
            # of them said the other's surname, which nobody does out loud.
            claim = _words(line) - _NOTE_REGISTER - participant_words
            # Only judge words the meeting actually contains; anything else is
            # check_grounding's problem, not an attribution question.
            claim = {w for w in claim if any(x[:5] == w[:5] for x in everything)}
            if len(claim) < 3:
                continue
            theirs = {w for w in claim if any(x[:5] == w[:5] for x in said[s])}
            if len(theirs) * 2 < len(claim):
                weak.append({
                    "owner": s,
                    "line": line,
                    "overlap": f"{len(theirs)}/{len(claim)}",
                    "absent": sorted(claim - theirs)[:6],
                })
    return {"applies": True, "ok": not weak, "weak": weak}


# A bare digit in prose is usually rhetoric ("three options"). The same digit
# in front of a unit is a commitment somebody will be held to.
_QUANTITY = re.compile(
    r"\b(\d[\d,.]*)\s*(seconds?|minutes?|hours?|days?|weeks?|months?|quarters?|"
    r"years?|people|persons?|users?|customers?|engineers?|percent|%|dollars?|"
    r"euros?|pounds?|[kmb]\b)",
    re.IGNORECASE,
)


# Models answer this question in their own vocabulary regardless of the format
# they are given. Asked for PRESENT/ABSENT, llama3.1 replied MENTIONED / NOT
# MENTIONED — four substantively correct-ish judgements that a PRESENT|ABSENT
# regex scored as zero parsed answers, which then read downstream as "nothing
# was found". A parse failure that arrives looking like a verdict is worse than
# a crash, so negatives are matched before positives (NOT MENTIONED contains
# MENTIONED) and anything unrecognised is reported as unparsed, never folded
# into a result.
_ABSENT_WORDS = re.compile(
    r"\b(?:absent|missing|not\s+(?:mentioned|present|covered|found)|no\b|omitted|"
    r"uncovered)", re.IGNORECASE)
_PRESENT_WORDS = re.compile(
    r"\b(?:present|mentioned|covered|found|yes|included)\b", re.IGNORECASE)


def _parse_verdict(text: str, n: int) -> bool | None:
    """True present, False absent, None when the model did not answer item n."""
    m = re.search(rf"^\s*{n}\s*[.):\-]?\s*(.+)$", text, re.MULTILINE)
    if not m:
        return None
    answer = m.group(1).strip()
    if _ABSENT_WORDS.search(answer):
        return False
    if _PRESENT_WORDS.search(answer):
        return True
    return None


# Known-answer fixtures. A judge that cannot pass these is not measuring recall,
# and its agreement with these is reported rather than assumed.
JUDGE_FIXTURES = [
    (["Send the signed contract to the vendor by Friday",
      "Book the venue for the offsite",
      "Migrate the billing service off the legacy queue"],
     ("## Action items\n- Someone will get the contract signed and over to the "
      "vendor this week.\n- The billing service needs to come off the old queue."),
     [True, False, True]),
    (["Share GitHub usernames so access can be granted",
      "Draft a straw man project plan"],
     ("## Action items\n- Draft a straw man project plan with objectives and "
      "open questions.\n- Provide access to the project repository."),
     [False, True]),
]


def validate_judge(model: str, num_ctx: int, timeout: int) -> dict:
    """Does this model actually agree with known answers?

    Recall is the one check here that asks a model instead of counting strings,
    which means the instrument needs calibrating before its readings mean
    anything. Two local models disagreed sharply on the same real notes — one
    marked every reference item present, the other marked most of them
    correctly — so "the judge said 4/4" is not a fact about the notes until the
    judge has been shown to distinguish the cases at all.
    """
    right = total = 0
    detail = []
    for items, note, expected in JUDGE_FIXTURES:
        numbered = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(items))
        out = ollama_chat(
            model, RECALL_JUDGE,
            f"REFERENCE ITEMS:\n{numbered}\n\nNOTES:\n{note}\n\n"
            f"Answer for items 1 to {len(items)}.",
            num_ctx, timeout,
        )["message"]["content"]
        for i, want in enumerate(expected, start=1):
            got = _parse_verdict(out, i)
            total += 1
            right += got == want
            detail.append({"item": items[i - 1], "want": want, "got": got})
    return {"model": model, "agreement": f"{right}/{total}",
            "ok": right == total, "detail": detail}


RECALL_JUDGE = """\
You are checking whether a set of meeting notes covers a list of reference items.

For each numbered reference item, decide whether the notes mention that item —
the same commitment or topic, in any wording. Paraphrase counts. A different
owner still counts. Vague overlap does not: the notes must actually refer to
that specific thing.

Answer with one line per item and nothing else:

1. PRESENT
2. ABSENT

No explanation, no preamble, no other text."""


def check_recall(note: str, reference_items: list[str], model: str,
                 num_ctx: int, timeout: int) -> dict:
    """What the notes left out, measured against an independent list.

    Every other check in this file asks whether something in the notes is false.
    None of them asks whether something true is missing — and after four
    meetings, omission is the failure that actually happens. A committee hearing
    came back covering one topic of seven. A real Meet call dropped two of the
    four commitments its own platform had recorded. Both sets of notes passed
    every check cleanly, because everything they *did* say was true.

    Confident, well-formed, and half the meeting. Nothing in the output marks
    the difference, and a reader with no transcript cannot tell the complete
    note from the partial one.

    Recall needs a reference, so this takes one: a list of items somebody else
    produced from the same meeting — a platform's own action items, a human's
    notes. Not ground truth, since the reference has its own omissions. It is a
    second opinion, and disagreement in either direction is worth reading.

    This is the one check here that asks a model rather than counting strings,
    and it is deliberate. Two lexical versions were written first and both were
    wrong in opposite directions. Scoring against all of an item's content words
    called a note 4/4 that never mentioned GitHub usernames once — "provide",
    "project", "repository" and the attendees' names appear in every row, so an
    item cleared the bar without its subject appearing anywhere. Restricting to
    each item's unique terms then failed notes that plainly did cover the item,
    because the unique set fills up with incidental words like "gain" and
    "access". The gap between "send GitHub usernames" and "Share GitHub
    Usernames: provide GitHub usernames to gain access" is semantic, and no
    amount of threshold-tuning turns word overlap into meaning. Tuning it until
    the fixtures passed would have produced a number that measured the fixtures.

    So the model does the matching, and the result is labelled as a model's
    judgement rather than a measurement. Its verdicts on a real meeting were
    checked by hand against a transcript before this was trusted at all.
    """
    if not reference_items:
        return {"applies": False}

    numbered = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(reference_items))
    verdicts = ollama_chat(
        model, RECALL_JUDGE,
        f"REFERENCE ITEMS:\n{numbered}\n\nNOTES:\n{note}\n\nAnswer for items 1 to "
        f"{len(reference_items)}.",
        num_ctx, timeout,
    )["message"]["content"]

    found, missed, unparsed = [], [], []
    for i, item in enumerate(reference_items, start=1):
        verdict = _parse_verdict(verdicts, i)
        if verdict is None:
            unparsed.append(item)
        elif verdict:
            found.append({"item": item})
        else:
            missed.append({"item": item})

    total = len(found) + len(missed)
    return {
        "applies": True,
        "ok": not missed and not unparsed,
        "found": found,
        "missed": missed,
        "unparsed": unparsed,
        "judge": model,
        # A judge that answered nothing used to render as "0/0", which reads like
        # a reference list with no items rather than a judge that failed on every
        # one of them. It happened for real: a 2200-word note pushed the judge
        # into prose it could not be parsed out of, and the run reported 0/0
        # beside a four-item reference. The denominator now counts what was
        # asked, and unanswered items are named rather than divided away.
        "score": (f"{len(found)}/{total}" if not unparsed else
                  f"{len(found)}/{len(reference_items)} with "
                  f"{len(unparsed)} unanswered — judge output unusable"),
    }


# Reference lists arrive as bullets, checkboxes, or "[Owner] Title: body" rows.
_REF_BULLET = re.compile(r"^\s*(?:[-*•●]|\[\s*[x ]?\s*\]|\d+[.)])\s+(.*)$")


def load_reference(path: Path) -> list[str]:
    """A list of expected items, one per line, however it was bulleted."""
    items = []
    for line in path.read_text().splitlines():
        if line.strip().startswith("#"):
            continue
        if m := _REF_BULLET.match(line):
            items.append(m.group(1).strip())
        elif line.strip() and items and not line[:1].strip():
            items[-1] = f"{items[-1]} {line.strip()}"
    return [i for i in items if i]


def check_numbers(note: str, source_text: str) -> dict:
    """Numbers in the notes that are nowhere in the transcript.

    Numbers are where fabrication does the most damage: a wrong price or date in
    a note about a meeting you half-remember is worse than no note.

    Bare integers up to ten are ignored, because prose generates them without
    claiming anything ("three options", "the second point"). That exemption used
    to swallow the numbers that matter most. A real meeting produced the note
    line "it will likely take at least 2 months due to security checks" — a
    schedule commitment somebody would be held to, and invisible to this check
    because 2 ≤ 10. It happened to be true. Nothing here established that.

    So a digit followed by a unit is always checked, however small, and matched
    together with its unit: "2 months" is not verified by a transcript that says
    "2 people".
    """
    def digits(s: str) -> set[str]:
        return set(re.findall(r"\b\d[\d,.]*\b", s))

    def quantities(s: str) -> set[str]:
        return {f"{n} {u.lower()}" for n, u in _QUANTITY.findall(s)}

    bare = sorted(
        n for n in digits(note) - digits(source_text)
        if not (n.isdigit() and int(n) <= 10)
    )
    unsupported_quantities = sorted(quantities(note) - quantities(source_text))
    invented = sorted(set(bare) | set(unsupported_quantities))
    return {"ok": not invented, "invented": invented}


def summarize(transcript: Transcript, model: str, num_ctx: int, timeout: int) -> dict:
    system = BASE_RULES + "\n\n" + CONTRACTS[transcript.attribution]
    rendered = transcript.render()
    user = f"Transcript:\n\n{rendered}\n\nWrite the notes."

    t0 = time.monotonic()
    response = ollama_chat(model, system, user, num_ctx, timeout)
    elapsed = time.monotonic() - t0

    return {
        "note": response["message"]["content"].strip(),
        "elapsed_s": elapsed,
        "model": model,
        "rendered": rendered,
        "system": system,
        "calls": [{"label": "notes", "prompt": system + user, "response": response}],
    }


def chunk_transcript(transcript: Transcript, target_words: int,
                     overlap_words: int) -> list[Transcript]:
    """Slice a transcript into overlapping windows, cutting on turn boundaries.

    The windows overlap because commitments are routinely made across a turn
    boundary — one person asks, another agrees — and a cut between the two
    leaves neither half usable in either slice. Overlap costs duplicate items,
    which the consolidation pass is explicitly told to merge; a missed
    commitment has no such remedy.
    """
    windows, current, words, i = [], [], 0, 0
    turns = transcript.turns
    while i < len(turns):
        current.append(turns[i])
        words += len(turns[i].text.split())
        i += 1
        if words >= target_words and i < len(turns):
            windows.append(current)
            back, rewound = 0, 0
            while back < len(current) - 1 and rewound < overlap_words:
                back += 1
                rewound += len(current[-back].text.split())
            i -= back
            current, words = [], 0
    if current:
        windows.append(current)
    return [
        Transcript(source=f"{transcript.source} [slice {n}/{len(windows)}]",
                   attribution=transcript.attribution, turns=w)
        for n, w in enumerate(windows, 1)
    ]


_ITEM = re.compile(r"^\s*(?:[-*]\s*)?(DECISION|ACTION|QUESTION)\s*:\s*(.+)$", re.IGNORECASE)


def summarize_chunked(transcript: Transcript, model: str, num_ctx: int, timeout: int,
                      target_words: int, overlap_words: int) -> dict:
    """Extract per slice, then consolidate — trading passes for recall.

    The single-pass summarizer is asked to compress a whole meeting in one step,
    and every measurement in EVAL.md says what it loses under that pressure is
    commitments. Here each slice is compressed gently and the merge is forbidden
    to select, so no step faces the ratio that causes the loss.

    This is not free. It makes one model call per slice plus one, and it
    introduces a second place for omission to happen — the merge. The extracted
    items are returned alongside the note precisely so the two stages can be
    scored separately: if extraction finds a commitment the note lacks, the
    defect is in the merge, which is a different fix.
    """
    contract = CONTRACTS[transcript.attribution]
    extract_system = EXTRACT_RULES + "\n\n" + contract
    consolidate_system = CONSOLIDATE_RULES + "\n\n" + contract
    slices = chunk_transcript(transcript, target_words, overlap_words)

    t0 = time.monotonic()
    calls, items = [], []
    for chunk in slices:
        user = f"Transcript slice:\n\n{chunk.render()}\n\nList the items."
        response = ollama_chat(model, extract_system, user, num_ctx, timeout)
        calls.append({"label": chunk.source, "prompt": extract_system + user,
                      "response": response})
        for line in response["message"]["content"].splitlines():
            if m := _ITEM.match(line):
                items.append(f"{m.group(1).upper()}: {m.group(2).strip()}")

    listing = "\n".join(items) if items else "(no items were extracted)"
    user = f"Items extracted from the meeting, in order:\n\n{listing}\n\nWrite the notes."
    response = ollama_chat(model, consolidate_system, user, num_ctx, timeout)
    calls.append({"label": "consolidate", "prompt": consolidate_system + user,
                  "response": response})
    elapsed = time.monotonic() - t0

    return {
        "note": response["message"]["content"].strip(),
        "elapsed_s": elapsed,
        "model": model,
        "rendered": transcript.render(),
        "system": extract_system + "\n" + consolidate_system,
        "calls": calls,
        "extracted": items,
        "slices": len(slices),
    }


def report(result: dict, transcript: Transcript, stripped_speakers: list[str],
           reference: dict | None, num_ctx: int, expected: list[str] | None = None) -> bool:
    note = result["note"]
    ctx = check_context(result["calls"], num_ctx)
    attr = check_attribution(note, transcript, stripped_speakers)
    nums = check_numbers(note, result["rendered"])
    echo = check_prompt_echo(note, result["rendered"], result["system"])
    grounding = check_grounding(note, result["rendered"])
    owners = check_owner_grounding(note, transcript)
    recall = check_recall(note, expected or [], result["model"], num_ctx, 300)

    print(f"\n=== notes ({transcript.attribution}) ===\n")
    print(note)

    print("\n=== checks ===\n")
    print(f"  source        {transcript.source}")
    print(f"  turns         {len(transcript.turns)}")
    print(f"  model         {result['model']}  in {result['elapsed_s']:.1f}s")

    if ctx["ok"] is None:
        print(f"  context       UNVERIFIED — {ctx['reason']}")
    elif ctx["ok"]:
        across = f" across {ctx['calls']} calls" if ctx.get("calls", 1) > 1 else ""
        print(f"  context       whole transcript read{across} "
              f"({ctx['counted']} prompt tokens at the largest, "
              f"num_ctx {ctx['num_ctx']})")
    else:
        print(f"  context       TRUNCATED — {ctx['reason']}")

    if attr["applies"]:
        if attr["ok"]:
            print("  attribution   clean — no speaker named, no actor implied")
        else:
            if attr["named_speakers"]:
                print(f"  attribution   FABRICATED — named {attr['named_speakers']} "
                      "from a transcript with no labels")
            if attr["actor_phrases"]:
                print(f"  attribution   FABRICATED — implied an actor: {attr['actor_phrases']}")
    else:
        print(f"  attribution   n/a at level '{transcript.attribution}'")

    if nums["ok"]:
        print("  numbers       every figure in the notes appears in the transcript")
    else:
        print(f"  numbers       NOT IN TRANSCRIPT: {nums['invented']}")

    if echo["ok"]:
        print("  prompt echo   no content taken from the instructions")
    else:
        print(f"  prompt echo   FABRICATED FROM THE PROMPT: {echo['echoed']}")

    if owners["applies"]:
        if owners["ok"]:
            print("  owners        each attributed item overlaps what that person said")
        else:
            print("  owners        CHECK THESE ATTRIBUTIONS (advisory):")
            for w in owners["weak"]:
                print(f"                  {w['owner']} — overlap {w['overlap']}, "
                      f"absent from their turns: {w['absent']}")
                print(f"                  \"{w['line'][:88]}\"")

    if recall["applies"]:
        # Never print this number without saying who produced it. It is one
        # model's opinion of another model's output, and on this machine no
        # local judge has yet passed --validate-judge.
        print(f"  recall        {recall['score']} — judged by {recall['judge']}, "
              "not measured; calibrate it with --validate-judge")
        for m in recall["missed"]:
            print(f"                  MISSED: {m['item'][:78]}")
        for u in recall["unparsed"]:
            print(f"                  NO VERDICT (judge did not answer): {u[:60]}")

    if grounding["ok"]:
        print("  grounding     every content word traces to something said")
    else:
        print(f"  grounding     for review (advisory, expect paraphrase): "
              f"{grounding['ungrounded']}")

    if reference and reference.get("summary"):
        print("\n=== human reference ===\n")
        print(f"  {reference['summary']}")
        if reference.get("topics"):
            print("\n  topics the meeting actually covered:")
            for t in reference["topics"]:
                covered = _topic_covered(t, note)
                print(f"    [{'x' if covered else ' '}] {t}")
            hit = sum(_topic_covered(t, note) for t in reference["topics"])
            print(f"\n  {hit}/{len(reference['topics'])} topics touched by the notes")

    # Grounding is deliberately absent: it is advisory, for the reason given in
    # its docstring.
    return (
        ctx["ok"] is not False
        and (not attr["applies"] or attr["ok"])
        and nums["ok"]
        and echo["ok"]
    )


_STOPWORDS = {"the", "of", "and", "a", "on", "about", "for", "to", "in", "last",
              "actual", "up", "study", "meeting", "device", "new"}


def _topic_covered(topic: str, note: str) -> bool:
    """Cheap lexical overlap. Indicative, not a score — see EVAL.md."""
    words = [w for w in re.findall(r"[a-z]{4,}", topic.lower()) if w not in _STOPWORDS]
    if not words:
        return False
    note_l = note.lower()
    return sum(w in note_l for w in words) >= max(1, len(words) // 2)


# Notes with known verdicts. A check that has only ever been seen to pass is not
# evidence of anything, so each case below states what it is proving. The false
# positives are the ones that matter: they are the failures this check already
# had, kept as fixtures so they cannot come back.
SELF_TEST = [
    # (label, note, speakers, expect_ok)
    ("collective phrasing is not attribution",
     ("## Decisions\nThe group agreed on kinetic charging. They decided to use plastic.\n"
      "## Action items\nSomeone is to check the cost of voice recognition."),
     ["Marketing", "User Interface"], True),

    ("a role name used as a topic is not attribution",
     ("## Summary\nThe group discussed market trends, user interface, and materials.\n"
      "Marketing feedback was reviewed alongside the industrial design constraints."),
     ["Marketing", "User Interface", "Industrial Designer"], True),

    ("a role name in an attributing position is caught",
     "## Decisions\nMarketing agreed to run the trend study before the next meeting.",
     ["Marketing", "User Interface"], False),

    ("credit-to-a-source phrasing is caught",
     "## Open questions\nThe cost of voice recognition, raised by Industrial Designer.",
     ["Industrial Designer"], False),

    ("an owner column is caught whatever fills it",
     "## Action items\n- Chase the supplier. Owner: the person who raised it.",
     ["Marketing"], False),

    ("second person is caught, because it claims the operator committed",
     "## Action items\nYou agreed to check the financial feasibility.",
     ["Marketing"], False),

    ("a speaker-prefixed line is caught",
     "## Decisions\n- Marketing: the cover should be rubberised.",
     ["Marketing"], False),
]

# The `channel` level has its own contract: "Me" is a real identity, "Them" is
# not. These run against a channel transcript rather than an unattributed one.
CHANNEL_SELF_TEST = [
    ("second person is correct at channel — Me is a known identity",
     "## Action items\nYou agreed to check the financial feasibility.", True),
    ("collective phrasing about the far side is fine",
     "## Decisions\nThe group agreed on kinetic charging.", True),
    ("treating Them as one actor is caught",
     "## Action items\nThem agreed to send the revised quote.", False),
    ("crediting the far side as a source is caught",
     "## Open questions\nThe cost of the cover, raised by Them.", False),
    ("individuating the far side is caught",
     "## Decisions\n- She proposed moving to a rubber cover.", False),
]


def run_self_test() -> int:
    failures = 0
    print("=== attribution check, positive and negative controls ===\n")
    for label, note, speakers, expect_ok in SELF_TEST:
        t = Transcript(source="self-test", attribution=NONE, turns=[Turn(text="x")])
        got = check_attribution(note, t, speakers)
        ok = got["ok"] == expect_ok
        failures += not ok
        verdict = "pass" if ok else "FAIL"
        want = "clean" if expect_ok else "flagged"
        print(f"  [{verdict}] expects {want:8s} — {label}")
        if not ok:
            print(f"          got names={got['named_speakers']} "
                  f"phrases={got['actor_phrases']}")

    print("\n=== attribution check at `channel` (the recommended capture path) ===\n")
    for label, note, expect_ok in CHANNEL_SELF_TEST:
        t = Transcript(source="self-test", attribution=CHANNEL,
                       turns=[Turn(text="x", speaker="Me")])
        got = check_attribution(note, t, [])
        ok = got["ok"] == expect_ok
        failures += not ok
        want = "clean" if expect_ok else "flagged"
        print(f"  [{'pass' if ok else 'FAIL'}] expects {want:8s} — {label}")
        if not ok:
            print(f"          got names={got['named_speakers']} phrases={got['actor_phrases']}")

    print("\n=== owner-grounding check (advisory, `named` only) ===\n")
    owner_turns = [
        Turn(text="I'll come up with just a straw man project plan", speaker="Robin Vance"),
        Turn(text="I'd love to be included on the first one just to give any feedback",
             speaker="Alex Ferris"),
        Turn(text="give me your GitHub usernames and I'll get you access", speaker="Robin Vance"),
    ]
    for label, note, expect_ok in [
        ("an owner who said the thing passes",
         "## Action items\n- Robin Vance will come up with a straw man project plan.", True),
        # Every element true, wrong object — the drift a proofread survives.
        ("an owner credited with someone else's object is surfaced",
         ("## Action items\n- Alex Ferris will review and give feedback on the straw man "
          "project plan."), False),
        ("an item with no owner is not an attribution question",
         "## Action items\n- Someone is to come up with a straw man project plan.", True),
    ]:
        t = Transcript(source="self-test", attribution=NAMED, turns=owner_turns)
        got = check_owner_grounding(note, t)
        ok = got["ok"] == expect_ok
        failures += not ok
        want = "clean" if expect_ok else "flagged"
        print(f"  [{'pass' if ok else 'FAIL'}] expects {want:8s} — {label}")
        if not ok:
            print(f"          got weak={got['weak']}")

    print("\n=== number check ===\n")
    for label, note, source, expect_ok in [
        ("a figure present in the transcript passes",
         "Budget is 12.5 euro", "we said 12.5 euro", True),
        ("a figure absent from the transcript is caught",
         "Budget is 47 euro", "we said 12.5 euro", False),
        ("small integers from prose are not treated as claims",
         "There were 3 options", "no digits here", True),
        # The exemption above used to swallow schedule commitments.
        ("a small integer with a unit IS a claim and is checked",
         "It will take at least 2 months", "no timeline was given", False),
        ("a quantity present in the transcript passes",
         "It will take at least 2 months", "not sooner than 2 months, security", True),
        ("a quantity is matched with its unit, not just its digit",
         "We need 2 months", "there were 2 people on the call", False),
    ]:
        got = check_numbers(note, source)
        ok = got["ok"] == expect_ok
        failures += not ok
        print(f"  [{'pass' if ok else 'FAIL'}] {label}")
        if not ok:
            print(f"          got invented={got['invented']}")

    # The regression that motivated this check, replayed verbatim. The note is
    # the one the model actually produced, and the instruction text is the one
    # that leaked into it.
    leaky_instruction = ('Use agentless phrasing — "the launch date was moved '
                         'forward", "someone is to follow up with the supplier".')
    print("\n=== prompt-echo check (gating) ===\n")
    for label, note, source, system, expect_ok in [
        ("instruction examples echoed as decisions are caught",
         ("## Decisions\n- The launch date was moved forward.\n"
          "- Someone is to follow up with the supplier."),
         "we should anonymize the corpus before release", leaky_instruction, False),
        ("a note that shares no content with the instructions passes",
         "## Decisions\n- Kinetic charging was chosen.",
         "we went with kinetic charging", leaky_instruction, True),
        ("wording present in the transcript is not an echo",
         "## Decisions\n- The launch date was moved forward.",
         "we moved the launch date forward", leaky_instruction, True),
    ]:
        got = check_prompt_echo(note, source, system)
        ok = got["ok"] == expect_ok
        failures += not ok
        print(f"  [{'pass' if ok else 'FAIL'}] {label}")
        if not ok:
            print(f"          got echoed={got['echoed']}")

    print("\n=== grounding check (advisory) ===\n")
    for label, note, source, expect_ok in [
        ("fabricated content is surfaced",
         "## Decisions\n- The launch date was moved forward.",
         "we should anonymize the corpus before release", False),
        ("note-register vocabulary is not treated as content",
         "## Summary\nThe meeting discussed several issues and the group agreed.",
         "kinetic charging", True),
    ]:
        got = check_grounding(note, source)
        ok = got["ok"] == expect_ok
        failures += not ok
        print(f"  [{'pass' if ok else 'FAIL'}] {label}")
        if not ok:
            print(f"          got ungrounded={got['ungrounded']}")

    outcome = (
        "all controls behaved as specified" if not failures
        else f"{failures} control(s) wrong"
    )
    print(f"\n  {outcome}")
    return 1 if failures else 0


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("transcript", type=Path, nargs="?",
                   help="QMSum meeting JSON or a capture transcript")
    p.add_argument("--self-test", action="store_true",
                   help="run the fabrication checks against notes with known verdicts")
    p.add_argument("--validate-judge", action="store_true",
                   help="check whether a model can judge recall, against known answers")
    p.add_argument("--strip", action="store_true",
                   help="remove speaker labels, testing the unattributed contract")
    p.add_argument("--simulate-bleed", action="store_true",
                   help="remove labels AND double every line, as a contaminated capture arrives")
    p.add_argument("--as-channel", metavar="SPEAKER", nargs="?", const=True,
                   help="collapse to the Me/Them split a clean headphone capture produces")
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--num-ctx", type=int, default=DEFAULT_NUM_CTX)
    p.add_argument("--timeout", type=int, default=900)
    p.add_argument(
        "--passes", type=int, choices=(1, 2), default=1,
        help="1 = summarize the whole transcript in one call. 2 = extract items "
             "per slice, then consolidate; slower, aimed at omission",
    )
    p.add_argument("--chunk-words", type=int, default=1500,
                   help="target words per slice at --passes 2")
    p.add_argument("--overlap-words", type=int, default=150,
                   help="overlap between slices, so a commitment spanning a cut "
                        "survives in one of them")
    p.add_argument("--out", type=Path, help="also write the notes to this file")
    p.add_argument("--reference", type=Path,
                   help="a list of expected items to measure recall against "
                        "(a platform's own action items, or a human's notes)")
    args = p.parse_args()

    if args.self_test:
        return run_self_test()
    if args.validate_judge:
        v = validate_judge(args.model, args.num_ctx, 300)
        print(f"\n=== recall judge: {v['model']} ===\n")
        for d in v["detail"]:
            got = {True: "present", False: "absent", None: "UNPARSED"}[d["got"]]
            want = "present" if d["want"] else "absent"
            print(f"  [{'pass' if d['got'] == d['want'] else 'FAIL'}] "
                  f"wanted {want:8s} got {got:8s} — {d['item'][:60]}")
        print(f"\n  agreement {v['agreement']}")
        if not v["ok"]:
            print("  This model cannot be trusted to measure recall. Its verdicts\n"
                  "  would be a number, not a measurement.")
        return 0 if v["ok"] else 1
    if args.transcript is None:
        p.error("a transcript is required (or --self-test)")

    if not args.transcript.exists():
        raise SystemExit(
            f"{args.transcript} not found.\n"
            "Fetch the evaluation corpus first:  python notes/fetch_corpus.py"
        )

    t = load(args.transcript)
    reference = None
    if t.source.startswith("qmsum:"):
        reference = qmsum_reference(args.transcript)

    stripped_speakers = t.speakers
    if args.simulate_bleed:
        t = t.simulate_bleed()
    elif args.as_channel:
        t = t.as_channel(None if args.as_channel is True else args.as_channel)
    elif args.strip:
        t = t.strip_attribution()

    expected = load_reference(args.reference) if args.reference else []

    if args.passes == 2:
        result = summarize_chunked(t, args.model, args.num_ctx, args.timeout,
                                   args.chunk_words, args.overlap_words)
    else:
        result = summarize(t, args.model, args.num_ctx, args.timeout)
    passed = report(result, t, stripped_speakers, reference, args.num_ctx, expected)

    if args.out:
        args.out.write_text(result["note"] + "\n")
        print(f"\n  wrote {args.out}")
        if "extracted" in result:
            # Written beside the notes so the two stages can be scored apart.
            # A commitment present here and absent from the notes is a merge
            # defect; one absent from both is an extraction defect, and they do
            # not have the same fix.
            items = args.out.with_suffix(".items.md")
            items.write_text("\n".join(result["extracted"]) + "\n")
            print(f"  wrote {items} ({len(result['extracted'])} extracted items)")

    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())

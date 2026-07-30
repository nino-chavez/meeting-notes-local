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
import contextlib
import io
import itertools
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
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
What someone committed to do next. Every one of them, routine included.

## Proposed
What was suggested, offered or asked for and NOT agreed to. Anything hedged — "maybe
we should", "we could", "I think we ought to", "they are asking for" — belongs here and
not under Decisions or Action items.

## Open questions
What was raised and left unresolved.

Under every single item in Decisions, Action items and Open questions, add one
line holding the spoken words the item rests on, like this:

- ITEM IN YOUR OWN WORDS
  > SPOKEN WORDS COPIED EXACTLY

Write the item on its own line and nothing else on it. Write the spoken words on
the next line, indented, starting with the > character. ITEM IN YOUR OWN WORDS
and SPOKEN WORDS COPIED EXACTLY name the two slots; do not write those words.
Do not put angle brackets or square brackets around anything.

Put an item where its spoken words put it, not where it would be most useful. Words
that hedge, suggest or ask make it Proposed even when the idea is a good one and even
when it plainly should have been agreed. A meeting that settled little produces a note
that is mostly Proposed, and that is the correct note.

The Summary section takes no quotes."""

# Where those words come from differs by path, and conflating the two guaranteed
# fabrication. The single-pass summarizer holds the transcript, so it copies from
# it. The consolidator never sees a transcript — it receives an item list — so it
# can only carry across evidence the extraction pass already attached. Appending
# "copy from the transcript" to a shared contract asked the consolidator for
# verbatim quotes from something it had never been shown, and every citation it
# produced was therefore invented by construction.
QUOTE_FROM_TRANSCRIPT = """
Copy the quoted words from the transcript exactly as they appear. Do not tidy
them, complete them, or join words from different parts of the transcript. At
least five words, or it proves nothing."""

QUOTE_FROM_ITEMS = """
Every item you were given ends with a pipe and the words that item rests on.
Carry those words across unchanged, on their own line below the item, starting with
the > character. Never write a quote of your own: you have not seen the transcript,
so anything you compose is invented. An item that arrived without evidence after
its pipe gets no quoted line at all."""
# The example above is a shape, not a sentence, and that is deliberate. The first
# version illustrated it with real prose — "The team settled on the rubber casing"
# over a matching quote — and llama3.1 reproduced both as a decision ES2004c had
# reached. That meeting really is about a rubber cover, so the echo read as almost
# true, which is the worst version of it.
#
# This repository had already made that exact mistake once: two example sentences
# in a phrasing rule came back as decisions a research meeting reached, and the
# repair was to delete them. Reintroducing it while adding a check that catches it
# is at least a well-instrumented mistake — `check_prompt_echo` and
# `check_citations` both flagged it independently on the first real run.
#
# Angle brackets fixed the content echo and bought a syntax echo. Every claim in two
# of three real runs came back as `- <the claim>`, brackets and all, and those were the
# same runs that collapsed the quote onto the item's line: the model copied the
# template's punctuation and its layout together. Neither check saw it, because what
# leaked was the shape rather than any word — `check_prompt_echo` compares content
# n-grams and found nothing to report.
#
# Named slots in capitals leak visibly instead. If a model writes "ITEM IN YOUR OWN
# WORDS" into a note, that phrase is in the system prompt, so `check_prompt_echo`
# catches it by the mechanism it already has. Choosing the failure that an existing
# check can see beats choosing the one that looks tidier in the prompt.

# Two of the four rules here used to instruct omission — "if you are not sure,
# leave it out" and "prefer omitting a section to padding it". They were written
# when the open question was whether a local model invents things. It does not;
# what it does is leave commitments out, and these rules were telling it to.
# Accuracy is still absolute, but it now applies to each statement written rather
# than doubling as a reason to write fewer of them.
BASE_RULES = """\
You are writing notes from a meeting transcript.

Rules that override everything else:
- Every statement you write must be supported by the transcript. Do not write
  anything the transcript does not support.
- Never invent names, numbers, dates, quantities, or deadlines. If the
  transcript does not contain a figure, your notes must not contain one.
- List every decision and every commitment, including routine ones — scheduling
  a meeting, sending a file, granting access, following up. A commitment that
  seems too small or too administrative to write down is still a commitment, and
  leaving those out is the most common way notes like these go wrong.
- Do not pad. Padding means filler, restatement, or anything the meeting did not
  produce; it does not mean leaving out something that was genuinely decided or
  promised. An empty section is a true statement about a meeting that settled
  nothing — it is not a target.
- Write plainly. No preamble, no sign-off, no "in this meeting" throat-clearing.

""" + SECTIONS + QUOTE_FROM_TRANSCRIPT

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
- One item per line, each starting with DECISION:, ACTION:, or QUESTION:, and
  end every line with a pipe followed by at least five words copied from this
  slice exactly as they appear:

  ACTION: <what was committed to> | <words copied from this slice>

  Those words are the only evidence anything downstream will have. No later step
  sees this transcript, so a line without them cannot be traced back to speech by
  anyone, ever.
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

""" + SECTIONS + QUOTE_FROM_ITEMS

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


_LIST_ITEM = re.compile(r"^[ \t]*[-*][ \t]+(?P<body>\S.*?)[ \t]*$")
_HEADING = re.compile(r"^[ \t]*#{1,6}[ \t]+(?P<title>\S.*?)[ \t]*$")

# The heading an item sits under, normalised. Not a taxonomy invented here: these are
# the three labels the extraction pass already emits (`_ITEM`), and the section names
# the prompt already asks for. An unrecognised heading keeps its own words rather than
# being forced into one of the three, because a note that grew a fourth section is
# information and silently relabelling it would destroy that.
_TYPES = {"decisions": "decision", "decision": "decision",
          "action items": "action", "actions": "action", "action": "action",
          "proposed": "proposal", "proposals": "proposal",
          "proposal": "proposal", "suggestions": "proposal",
          "open questions": "question", "questions": "question",
          "question": "question"}


def _claim_type(section: str | None) -> str | None:
    """Which kind of thing a claim is, recovered from the note's own structure.

    The extraction pass labels every item DECISION, ACTION or QUESTION and the label is
    then thrown away: the consolidator turns it into a markdown heading, and by the time
    a `note/1` artifact exists the only trace is which section a claim happens to sit
    under. So a surface wanting to group or filter by kind had to re-parse the note and
    become a second authority on what a section means.

    Recovering it here makes the note's *sections* a rendering choice rather than the
    model's structural decision — which is what `docs/journeys.md` settles on, and what
    film-room's DP-4 already argues in general: analysis is the substrate and outputs
    are renderers. A flat list of typed claims can be grouped by kind, filtered to
    commitments for J2, or read in order for J1, with no further model call.
    """
    if not section:
        return None
    return _TYPES.get(section.strip().lower(), section.strip().lower())
_BLOCKQUOTE = re.compile(r"^[ \t]*>[ \t]*(?P<quote>\S.*?)[ \t]*$")
# The same-line collapse, in either separator the model has actually used. The contract
# asks for the quote on the line below; runs have instead produced `claim > quote`,
# `claim | > quote`, and — after a fourth section was added — `claim | quote`, the
# extraction format passed straight through without conversion.
#
# **Reading only `>` would repeat a defect this file has already repaired.** When the
# parser knew only the next-line form, 41 real citations reported as "no quote offered",
# a bucket that does not fail a run. A pipe-separated note is the same situation with a
# different character: 93 located quotes on one meeting would read as absent. The rule
# recorded then applies now — a model given a format template copies the template's
# punctuation, and the pipe is in the template, because `QUOTE_FROM_ITEMS` tells the
# consolidator that "every item you were given ends with a pipe".
_SAME_LINE = re.compile(r"^(?P<claim>.*?\S)[ \t]+(?P<sep>[>|])[ \t]*(?P<quote>\S.*)$")
# Leftover template punctuation around a claim, stripped for comparison and counted
# so the leak stays visible instead of being quietly cleaned up.
_WRAPPED = re.compile(r"^[<\[](?P<inner>[^<>\[\]]+)[>\]]$")


def _parse_claims(note: str) -> list[dict]:
    """Every list item in the note, each classified exactly once.

    One parser, because two were the defect. `_CITED` matched only the quote-on-the-
    next-line layout and `_UNCITED` matched anything that `_CITED` did not, so when the
    model collapsed a citation onto one line the item fell through to `uncited` — a
    bucket that does not fail a run. 83 real citations on one meeting and 8 on another
    were reported as "no quote offered", and the run read clean. Two authorities on
    whether a claim was cited, disagreeing in silence, is the same defect this file has
    now repaired three times in other places.

    Accepting both layouts is not leniency about the contract. The contract is enforced
    by the prompt; a checker that reports 0 quotes when 33 are present is not strict,
    it is wrong. Deviations that matter are counted and reported instead.
    """
    lines = note.splitlines()
    offsets, pos = [], 0
    for line in lines:
        offsets.append(pos)
        pos += len(line) + 1

    # Which layout this note uses, decided once for the whole note rather than per
    # item. Reading a mid-line `>` as a citation wherever one appears would turn
    # "sustained throughput > 100 requests per second" into a quote that cannot be
    # located and therefore into a reported fabrication — inventing a fabrication is
    # worse than the bug being fixed here, which only misfiled real ones. Markdown
    # agrees: a blockquote marker is only a blockquote at the start of a line.
    #
    # A note commits to one layout. Where a quote appears below any item, that is the
    # note's layout and a mid-line `>` is prose. Otherwise two or more items sharing
    # the collapsed shape is the model having flattened the template, which is what it
    # did on two of three real meetings; a single one is a comparison.
    has_below = any(
        _LIST_ITEM.match(lines[i]) and i + 1 < len(lines) and _BLOCKQUOTE.match(lines[i + 1])
        for i in range(len(lines)))
    collapsed_shaped = sum(
        1 for i, line in enumerate(lines)
        if (m := _LIST_ITEM.match(line)) and _SAME_LINE.match(m.group("body")))
    read_collapsed = not has_below and collapsed_shaped >= 2
    layout = "next-line" if has_below else "collapsed" if read_collapsed else "none"
    # Which separator, alongside which layout: four shapes have appeared across real runs
    # and "collapsed" alone no longer says which one a note used. Taken from the regex
    # rather than re-detected, so there is one answer to what the separator was.
    separator = None
    if read_collapsed:
        separator = next((m.group("sep") for line in lines
                          if (li := _LIST_ITEM.match(line))
                          and (m := _SAME_LINE.match(li.group("body")))), None)

    out, i, section = [], 0, None
    while i < len(lines):
        if h := _HEADING.match(lines[i]):
            section = h.group("title").strip()
            i += 1
            continue
        m = _LIST_ITEM.match(lines[i])
        if not m:
            i += 1
            continue
        claim, at, quote = m.group("body"), offsets[i], None
        below = _BLOCKQUOTE.match(lines[i + 1]) if i + 1 < len(lines) else None
        if below:
            quote = below.group("quote")
            i += 2
        else:
            if read_collapsed and (collapse := _SAME_LINE.match(claim)):
                # The extraction format separates an item from its evidence with a
                # pipe and the note format uses a blockquote. The consolidator, holding
                # both contracts, emitted `claim | > quote` — keeping one separator and
                # adding the other — so every claim in a chunked note carried a
                # trailing pipe. Stripped here because it is punctuation from a format,
                # never part of what was claimed.
                claim = collapse.group("claim").rstrip(" \t|")
                quote = collapse.group("quote")
            i += 1
        wrapped = bool(w := _WRAPPED.match(claim))
        if w:
            claim = w.group("inner").strip()
        # `end` is the offset just past this item, blockquote included. The parser is
        # the only thing that knows whether an item consumed one line or two, so a
        # caller that needs to excise one asks rather than recomputing it.
        end = offsets[i] if i < len(lines) else len(note)
        out.append({"claim": claim, "quote": quote, "at": at, "end": end,
                    "wrapped": wrapped, "type": _claim_type(section),
                    "layout": layout, "separator": separator})
    return out


def dedupe_items(note: str) -> tuple[str, int]:
    """Drop repeated items from a note, keeping the first of each.

    The consolidator repeats itself. Measured on a 1365-turn meeting: extraction
    produced 160 items with one redundant pair, and consolidating them produced 83
    items of which **14 were exact repeats of an earlier claim** — the merge step
    introducing duplication rather than resolving it. The single-pass path produced
    none on either shorter meeting, which is why this is applied only where the defect
    is; adding it to `summarize` would carry machinery for a failure that path does not
    have and would hide it if it ever appeared.

    **Stripped and counted, not silently cleaned.** The same treatment as the template
    punctuation in `_parse_claims`: a note listing one decision twice is simply wrong
    and there is one obvious resolution, but the count is evidence about how reliable
    the chunked path is and disappears from the note the moment it is fixed. It travels
    in provenance for that reason.

    Keeping the first occurrence's evidence is safe rather than assumed to be: all
    twelve repeated claims on that meeting carried byte-identical quotes and identical
    evidence states, checked before this rule was written.
    """
    items = _parse_claims(note)
    seen, cuts = set(), []
    for item in items:
        key = " ".join(_seq(item["claim"]))
        if key in seen:
            cuts.append((item["at"], item["end"]))
        else:
            seen.add(key)
    if not cuts:
        return note, 0
    out, prev = [], 0
    for start, end in cuts:
        out.append(note[prev:start])
        prev = end
    out.append(note[prev:])
    return "".join(out), len(cuts)

# Short quotes collide by accident. Four content words is the same floor
# `_ECHO_NGRAM` uses, and for the same reason: long enough that ordinary phrasing
# does not match by chance, short enough that a lifted clause still counts.
_MIN_QUOTE_WORDS = 4


def _seq(s: str) -> list[str]:
    """Bare lowercase words, in order.

    Order matters here where `_words` discards it: a citation is a claim about a
    contiguous span of speech, so the check has to be a subsequence test rather
    than a set test. Punctuation and case are dropped because they are
    transcription artifacts — ASR output has no reliable capitalisation and
    invents commas — and flagging those as fabrication would be the check crying
    wolf, which this project has already shipped once and had to repair.
    """
    return re.findall(r"[a-z0-9']+", s.lower())


def check_citations(note: str, transcript: Transcript) -> dict:
    """Whether each claim's quoted evidence actually appears in the transcript.

    The strongest mechanical check available here, and the reason is that its
    failure mode is unambiguous. `check_grounding` asks whether a note's content
    words appear somewhere in the input, which a fluent paraphrase passes; this
    asks whether a specific contiguous span of speech exists, which nothing but
    real speech passes.

    **The model quotes and this locates**, which is the whole design. Asking an 8B
    model for a turn index or a timestamp gets a plausible number back — that is
    precisely the fabrication class this file exists to catch, invited in through
    the citation format. So the model is asked only for words it can see, and the
    position is derived here by finding them. A citation therefore cannot carry a
    wrong timestamp; it can only fail to be found at all.

    Deriving the position is not decoration. `journeys.md` J1 turns on tracing a
    claim back to the words behind it, and `DESIGN.md` retains the transcript
    rather than the audio precisely so that path survives deletion. A verified
    quote with a turn index is that path.
    """
    turns = [(i, t) for i, t in enumerate(transcript.turns)]
    haystacks = [(i, _seq(t.text)) for i, t in turns]

    def locate(quote: str) -> tuple[int, float | None] | None:
        q = _seq(quote)
        if len(q) < _MIN_QUOTE_WORDS:
            return None
        for i, hay in haystacks:
            for start in range(len(hay) - len(q) + 1):
                if hay[start:start + len(q)] == q:
                    return i, transcript.turns[i].start
        return None

    cited, fabricated, unverifiable, uncited = [], [], [], []
    items = _parse_claims(note)
    for item in items:
        quote = item["quote"]
        # `at` is the claim's character offset in the note. The buckets group by
        # outcome because that is what a verdict needs; a surface rendering the note
        # wants read order. Carrying the offset lets one pass serve both instead of
        # forcing a renderer to re-parse the note and disagree with this function
        # about what a claim is.
        row = {"claim": item["claim"], "quote": quote, "at": item["at"],
               "type": item["type"]}
        if quote is None:
            # Not a fabrication and not a pass. Counted so a model that ignores the
            # format cannot read as a clean run.
            row["why"] = "no quote was offered, so nothing traces back to the words"
            uncited.append(row)
            continue
        # Four outcomes, and the third is the difference between a check and a
        # nuisance. A quote too short to be distinctive has not been shown to be
        # false — it cannot be tested either way, and treating untestable as
        # fabricated would fail a run because a model quoted three words. This
        # project already shipped a check that reported fabrications which had not
        # happened, and repairing it is why `check_attribution` needs an attributing
        # position. The same discipline applies here.
        if len(_seq(quote)) < _MIN_QUOTE_WORDS:
            row["why"] = (f"under {_MIN_QUOTE_WORDS} words, so it could match by "
                          f"accident and is not evidence either way")
            unverifiable.append(row)
            continue
        hit = locate(quote)
        if hit is None:
            row["why"] = "does not appear in the transcript"
            fabricated.append(row)
        else:
            row["turn"], row["start"] = hit[0], hit[1]
            cited.append(row)

    # Template punctuation the model copied into its own claims. A prompt-compliance
    # count, not an evidence state: it says the instruction leaked, which is a thing
    # to fix in the prompt and not a thing the operator has to reason about.
    wrapped = sum(1 for it in items if it["wrapped"])
    # Repeats still present in the note. Distinct from provenance's
    # `duplicates_removed`, which counts what generation excised: this one runs on both
    # paths and on `--recheck`, so the single-pass path is covered and artifacts written
    # before any of this get the number backfilled. Placing the fix on the chunked path
    # only was supposed to leave a single-pass regression visible, and without a check
    # on both it would not have been.
    seen_claims, repeats = set(), 0
    for it in items:
        key = " ".join(_seq(it["claim"]))
        repeats += key in seen_claims
        seen_claims.add(key)
    # One value for the note: the parser decides the layout per note, so every item
    # agrees and reading it off the first is not a sample.
    layout = items[0]["layout"] if items else "none"
    separator = items[0]["separator"] if items else None
    # The invariant that would have caught the two-parser defect: every item the
    # parser found lands in exactly one bucket. When the buckets are allowed to
    # disagree about what they cover, items go missing into whichever one is benign.
    assert len(cited) + len(fabricated) + len(unverifiable) + len(uncited) == len(items)
    return {
        "applies": bool(transcript.turns),
        "ok": not fabricated,
        "items": len(items),
        "cited": cited,
        "fabricated": fabricated,
        "unverifiable": unverifiable,
        "uncited": uncited,
        "template_echo": wrapped,
        "layout": layout,
        "separator": separator,
        "repeats": repeats,
    }


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


def _parse_verdict(text: str) -> bool | None:
    """True present, False absent, None when the model did not answer.

    This used to take an item number and pick that line out of a batched reply,
    which coupled every verdict to the model's numbering holding for the whole
    list. It did not: one 2200-word note pushed the judge into prose, all four
    items came back unparsed together, and the run reported 0/0. Items are asked
    one per call now, so a reply is a verdict or it is nothing, and one
    unreadable answer costs one item instead of the list.
    """
    answer = text.strip()
    if _ABSENT_WORDS.search(answer):
        return False
    if _PRESENT_WORDS.search(answer):
        return True
    return None


# Asking "the same commitment **or topic**" is not the rule any recall figure in
# EVAL.md was scored under. That rule — §"How a commitment is scored as recalled"
# — says a topic raised in discussion does not hit a commitment to act on it, and
# requires the notes to name the commitment's own object. On the fixture that
# decides calibration, notes reading "provide access to the project repository"
# against a reference item "share GitHub usernames so access can be granted", the
# old wording licensed PRESENT while the fixture expected ABSENT.
#
# That disagreement was recorded as the judge sharing the adjacent-object
# blindness of the notes it grades. Part of it was simpler than that: two
# instruments were being asked two different questions and marked against one
# answer key. Transcribing the rule clause for clause takes gemma3:12b from 12/16
# to 16/16 on the fixtures below, holding everything else fixed.
#
# Half credit is the one clause deliberately not transcribed. The rule awards it
# to a reference item naming two artefacts where the notes cover one, and a third
# verdict word would widen a parse surface that has already failed twice here.
# Such an item is split into one fixture per artefact instead, which scores the
# same and keeps the vocabulary binary.
# The list framing below is deliberate and survives an attempt to remove it.
# Items are asked one per call, so "which of a list" describes a request that
# arrives holding exactly one item, and rewriting it into the singular reads
# better. Rewritten that way it measures worse, on both models and stably:
# gemma3:12b 15/16 against 16/16, llama3.1 12/16 against 13/16, three runs each.
# The one fixture the singular version loses is the wrong-owner case, which is
# not obviously connected to plurality. No account of why is offered here
# because none was established — only that the tidier wording is the worse
# instrument, and the wording was chosen by measurement rather than by reading.
RECALL_JUDGE = """\
You are checking which of a list of commitments from a meeting were written down
in that meeting's notes.

A reference item is PRESENT only when BOTH of these hold:

1. The notes name the same thing the commitment is about. Paraphrase and
   synonyms are fine. A broader category standing in for that thing is not:
   notes saying "share a document" do not cover "share the brand guidelines".
   Where a reference item states a purpose ("... so that X can happen"), the
   thing is what gets done, not the purpose — notes that mention only the
   purpose do not cover the commitment.
2. The notes state it as something that will be done — under Decisions or
   Action items, or in the Summary as something that is going to happen.

Otherwise the item is ABSENT. In particular:

- The same thing with a different action is ABSENT. "Review the report" does not
  cover a commitment to send the report; those are different commitments.
- The thing only coming up in discussion is ABSENT. A topic the meeting talked
  about is not a commitment to act on it.

Three differences do NOT make an item absent:

- A different owner, or no owner at all. Who is named does not matter.
- The commitment split across two bullets, if between them they carry both the
  thing and the commitment.
- The item filed under a different heading than you would expect. Where it sits
  is formatting.

Answer with one word and nothing else: PRESENT or ABSENT."""


def _judge_item(item: str, note: str, model: str, num_ctx: int, timeout: int,
                system: str = RECALL_JUDGE) -> bool | None:
    """One reference item, one call.

    Batching the whole list into a single call was the original shape and it
    costs accuracy as well as robustness: on the fixtures below gemma3:12b scores
    14/16 batched and 16/16 asked one at a time, under the identical rule. The
    two it recovers are both absent items it had called present, which is the
    direction that matters — a judge that waves items through reports recall the
    notes did not earn.

    `system` is a parameter so the harness can run a deliberately broken judge
    down this same path. A control that bypasses the call and the parser proves
    nothing about a pipeline whose failures have all been in the call and the
    parser.
    """
    out = ollama_chat(model, system, f"REFERENCE ITEM:\n{item}\n\nNOTES:\n{note}",
                      num_ctx, timeout)
    return _parse_verdict(out["message"]["content"])


# Known-answer fixtures. A judge that cannot pass these is not measuring recall,
# and its agreement with these is reported rather than assumed.
#
# There were five judgements here, covering two of the rule's clauses. Five is
# not enough to separate a judge from a coin, and worse, a judge answering
# PRESENT to everything — the documented failure of the 8B model — scored 3 of
# them, a majority. The set now walks every clause of EVAL.md's "How a commitment
# is scored as recalled" in both directions.
#
# The clauses are the anti-fitting argument. That rule was written before the
# two-pass run and published; each case below is one of its enumerated
# resolutions rather than a case chosen because a model gets it right. Where the
# rule states an example ("share a document" against "share the brand
# guidelines"), the fixture uses the rule's own example rather than a new one.
#
# Balance is a property to preserve when editing: 8 present against 8 absent, so
# neither degenerate answer takes more than half. `--validate-judge` proves that
# on the real path every time it runs, by scoring a sabotaged judge alongside the
# real one, and `--self-test` proves it offline against three synthetic ones.
JUDGE_FIXTURES = [
    # Paraphrase hits, and an item the notes simply do not contain.
    (["Send the signed contract to the vendor by Friday",
      "Book the venue for the offsite",
      "Migrate the billing service off the legacy queue"],
     ("## Action items\n- Someone will get the contract signed and over to the "
      "vendor this week.\n- The billing service needs to come off the old queue."),
     [True, False, True]),

    # The fixture calibration turns on. The notes record the *purpose* of the
    # commitment — access — and never its object, the usernames. Both local
    # models called this present, which was read as the judge sharing the
    # adjacent-object blindness of the notes it grades.
    (["Share GitHub usernames so access can be granted",
      "Draft a straw man project plan"],
     ("## Action items\n- Draft a straw man project plan with objectives and "
      "open questions.\n- Provide access to the project repository."),
     [False, True]),

    # A category standing in for the object, then the same object under a
    # different verb. Both notes lines are real commitments about adjacent
    # things, which is the only shape that discriminates: a judge matching on
    # subject matter passes them, a judge matching on the commitment does not.
    (["Send the brand guidelines to the agency",
      "Review the Q3 forecast before the board meeting"],
     ("## Action items\n- Someone will send a document over to the agency.\n"
      "- The Q3 forecast goes into the board pack on Monday."),
     [False, False]),

    # Three differences the rule says do not count — wrong owner, wrong heading,
    # split across two bullets — against one item that is genuinely missing.
    (["Priya will circulate the migration runbook",
      "Book a follow-up session with the data team",
      "Update the onboarding checklist and publish it to the wiki",
      "Archive the old runbook"],
     ("## Decisions\n- The migration runbook will be circulated by Tom after the "
      "review.\n## Action items\n- A follow-up with the data team goes in the "
      "calendar this week.\n- The onboarding checklist needs updating.\n"
      "- Whatever comes out of that gets published to the wiki."),
     [True, True, True, False]),

    # Discussed at length and explicitly unresolved is not a commitment; stated
    # in the Summary as something that will happen is one. Both directions of
    # "appears as a commitment", in a single note.
    (["Switch the error tracking to the new vendor",
      "Send the revised pricing sheet to finance",
      "Renew the monitoring contract"],
     ("## Summary\nThe group compared error tracking vendors at length and nobody "
      "landed on one. The revised pricing sheet is going to finance before the end "
      "of the week.\n## Open questions\n- Which error tracking vendor to move to."),
     [False, True, False]),

    # The rule's half-credit case — one reference item naming two artefacts, one
    # covered — split into a fixture per artefact, which scores the same and
    # keeps the verdict vocabulary binary.
    (["Share the meeting recording",
      "Share the slide deck"],
     "## Action items\n- The recording will be shared with everyone who missed it.",
     [True, False]),
]


# A judge that always answers PRESENT. Run through the real call and the real
# parser, not simulated, because every failure this judging path has actually had
# has been in the call or the parser rather than in the scoring.
SABOTAGED_JUDGE = """\
You are checking meeting notes against a commitment.

Answer with one word and nothing else: PRESENT.

Answer PRESENT whatever the notes say, including when they say nothing about it."""


SUPPORT_JUDGE = """\
You are checking whether some words from a meeting support a claim written about that
meeting. The words were really said; that is already established. Your only question is
whether they support THIS claim AS IT IS WRITTEN.

The claim begins with what kind of thing it says it is. Honour that:

- DECISION claims that the meeting settled something. Words that propose, suggest, hedge
  or ask do not support it. "maybe we should use rubber" does not support "DECISION:
  Rubber chosen".
- ACTION claims someone committed to do something. Words that raise it as a possibility
  do not support it. "we could just get a DAT machine" does not support "ACTION: Get a
  DAT machine".
- PROPOSAL claims something was suggested, offered or asked for and NOT agreed to.
  **Hedged and suggesting words are exactly the right evidence for a PROPOSAL claim**:
  "maybe we should", "we could", "I'd suggest", "I think we ought to", "they are asking
  for" all SUPPORT one. Every rule below about hedging, preference or weakness is about
  DECISION and ACTION claims and does not apply to a PROPOSAL. What fails a PROPOSAL
  claim is words that *settle* the thing — "okay let's go with the rubber then" is
  stronger than the claim — or words about something else.
- QUESTION claims something was asked or left open.

Answer NO when the words:

- say the opposite of the claim, or argue against it;
- are about something else, or are a fragment carrying no relevant content;
- support only a weaker version — discussion where the claim says decision, a
  possibility where the claim says commitment.

Two things that are NOT support, and both look like support at a glance:

- **Being on the same topic is not support.** Words that merely mention the subject
  carry no claim about it. "non-English speaking countries" does not support "DECISION:
  Market it abroad" — it names the topic and settles nothing.
- **An opinion about what should happen is not a decision.** "I think it should be the
  same" and "it ought to be X" state a preference. They **do** support a PROPOSAL or a
  QUESTION claim; they do not support a DECISION or an ACTION claim.

Hesitation is not disagreement. People say "uh", "um", repeat themselves and restart
sentences while agreeing to things. Judge what the words land on, not how fluently they
arrive: "yeah um okay do that then" supports a DECISION claim.

Answer with one word and nothing else: YES or NO."""

SABOTAGED_SUPPORT_JUDGE = """\
You are checking words from a meeting against a claim.

Answer with one word and nothing else: YES.

Answer YES whatever the words say, including when they contradict the claim."""

# Deliberately synthetic and deliberately NOT drawn from the meetings this judge is
# pointed at: calibrating on the items under measurement would encode the answer the
# measurement is meant to find. The casing domain matches this file's other fixtures and
# belongs to no corpus meeting.
#
# Covering the three ways support fails, because a set covering only one certifies a
# judge blind to the others — the lesson the settlement fixtures taught when a clean
# calibration set nearly published a wrong figure. Contradiction is listed first because
# it is the one that makes a note actively false rather than merely thin.
SUPPORT_FIXTURES = [
    ([
        # Supported, including disfluently. These are why the calibration means
        # anything: real transcript speech does not sound like a written sentence, and a
        # judge answering NO to hesitation would pass a tidy set and then reject every
        # real quote.
        "DECISION: Rubber chosen for the case ||| okay let's go with the rubber then",
        ("DECISION: No backlight in the first run ||| right so - so that's that, no "
         "backlight in the first run then"),
        "DECISION: Plastic body ||| we'll we'll just go with plastic, uh, for the body",
        "ACTION: Send the cost breakdown ||| fine, i'll send the cost breakdown tomorrow",
        "ACTION: Smaller battery ||| yeah um okay do that then, the smaller battery",
        ("QUESTION: Whether to record the rooms separately ||| what if we recorded "
         "the two rooms separately"),
        # The new bucket, both directions. A PROPOSAL claim is supported by hedged words
        # and NOT by words that settle the thing — an under-claim is as wrong as an
        # over-claim, and without the second fixture the judge could pass everything by
        # treating PROPOSAL as a weaker bar that anything clears.
        "PROPOSAL: Rubber for the case ||| maybe we should use rubber for the case",
        # This fixture originally read "PROPOSAL: Smaller battery ||| we could probably
        # get away with the smaller battery" and the answer key said supported. The judge
        # said no and **the judge was right**: "we could get away with X" is about
        # tolerating X, not proposing it, which is a distinction the key had missed.
        # Corrected rather than argued with — a fixture whose answer a careful person
        # cannot reach without hesitating is not a fixture, by this file's own bar.
        ("PROPOSAL: Use the smaller battery ||| i'd suggest we go with the smaller "
         "battery"),
        # Contradiction: the words argue against the claim.
        ("ACTION: Burn CDs for every attendee ||| you know, i personally would not "
         "want a CD of my meeting"),
        ("DECISION: Rubber chosen for the case ||| honestly i think rubber is the "
         "wrong material here"),
        # Unrelated, or a fragment carrying nothing.
        ("ACTION: Offer the seminar to senior students ||| talking about the kind of "
         "thing that you were just talking about"),
        "DECISION: Market it abroad ||| non-English speaking countries",
        # Stronger than the claim states, which is the inverse error and equally wrong:
        # a note filing a settled decision as merely proposed is also inaccurate.
        "PROPOSAL: Rubber for the case ||| okay let's go with the rubber then",
        # Supports only a weaker version than the claim states.
        "DECISION: Rubber chosen for the case ||| maybe we should use rubber for the case",
        ("ACTION: Get a DAT machine ||| we could have a fairly We could just get a "
         "DAT machine"),
        ("DECISION: World release matches the licensed one ||| i think that when we "
         "do that world release, it should be the same"),
        "ACTION: Write down the error message ||| maybe we should write it down",
    ], "", [True, True, True, True, True, True, True, True,
            False, False, False, False, False, False, False, False, False]),
]


def _judge_support(claim: str, quote: str, kind: str | None, model: str, num_ctx: int,
                   timeout: int, system: str = SUPPORT_JUDGE) -> bool | None:
    """Do these located words support this claim as written?

    The question `verified` was silently taken to answer and never asked. Locating a
    quote establishes that the words were said at a turn; nothing checked that they bear
    on the claim, and one action item cites speech arguing the opposite of itself.

    The claim's `type` goes to the judge because the claim's own first word is part of
    what has to be supported: a proposal supports "this was discussed" and not "this was
    decided". That is also why the settlement judge is retired — with the type visible,
    its question is this question.
    """
    label = f"{kind.upper()}: " if kind else ""
    out = ollama_chat(model, system,
                      f"CLAIM:\n{label}{claim}\n\nWORDS SAID IN THE MEETING:\n{quote}",
                      num_ctx, timeout)
    return _parse_verdict(out["message"]["content"])


def _fixture_judge_support(item: str, _note: str, model: str, num_ctx: int, timeout: int,
                           system: str = SUPPORT_JUDGE) -> bool | None:
    """A fixture's `CLAIM ||| quote` string, split and passed through the real path.

    Split here rather than stored pre-split so `score_fixtures` keeps one shape for both
    calibration sets. The separator is three pipes because a single one appears in
    extraction output and would make a fixture ambiguous.
    """
    claim, quote = item.split("|||", 1)
    kind, _, rest = claim.strip().partition(":")
    return _judge_support(rest.strip() or claim.strip(), quote.strip(),
                          kind.strip() if rest else None, model, num_ctx, timeout,
                          system)


def score_fixtures(judge, fixtures=None) -> dict:
    """Agreement of any judge — a model, or a rigged one — with the fixtures.

    `judge(item, note) -> bool | None`. Taking the judge as an argument is what
    lets the fixtures be pointed at something known to be broken. A calibration
    set that has only ever been run against judges hoped to be good establishes
    nothing about its own power to reject one, which is the same defect as a
    check that has only ever been seen to pass.
    """
    right = total = 0
    detail = []
    for items, note, expected in (JUDGE_FIXTURES if fixtures is None else fixtures):
        # strict: a fixture whose answer key is the wrong length would otherwise
        # be silently truncated into a shorter, easier calibration set.
        for item, want in zip(items, expected, strict=True):
            got = judge(item, note)
            total += 1
            right += got == want
            detail.append({"item": item, "want": want, "got": got})
    return {"right": right, "total": total, "agreement": f"{right}/{total}",
            "ok": right == total, "detail": detail}


def validate_judge(model: str, num_ctx: int, timeout: int) -> dict:
    """Does this model actually agree with known answers?

    Recall is the one check here that asks a model instead of counting strings,
    which means the instrument needs calibrating before its readings mean
    anything. Two local models disagreed sharply on the same real notes — one
    marked every reference item present, the other marked most of them
    correctly — so "the judge said 4/4" is not a fact about the notes until the
    judge has been shown to distinguish the cases at all.

    The bar is every fixture, not a threshold. Each one is a case a careful
    person applying the published rule answers without hesitating; a judge that
    misses one is wrong about a clause of the rule, and which clause is not
    something a passing score would tell you. Relaxing this to a proportion when
    a model lands one short is how a calibration set stops measuring anything.

    The sabotaged control runs alongside, and its failure is part of the verdict.
    If a judge told to answer PRESENT unconditionally can clear these fixtures,
    they are not fixtures, and the real judge's score means nothing either.
    """
    real = score_fixtures(
        lambda item, note: _judge_item(item, note, model, num_ctx, timeout))
    control = score_fixtures(
        lambda item, note: _judge_item(item, note, model, num_ctx, timeout,
                                       SABOTAGED_JUDGE))
    return {
        "model": model,
        "agreement": real["agreement"],
        "detail": real["detail"],
        "control": control["agreement"],
        "control_rejected": not control["ok"],
        "ok": real["ok"] and not control["ok"],
    }


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

    So the model does the matching, against the same written rule the hand
    scoring used, and the judge is calibrated in the same run that uses it rather
    than on somebody's memory of having calibrated it once. Temperature 0 is
    reproducible back to back and not across time — the same transcript, model
    and temperature produced materially different notes on a later day — so a
    calibration from another session is a claim about another session. It costs
    32 calls, sixteen known answers and sixteen for the sabotaged control: 15 s
    on gemma3:12b beside the 87 s that run's summarization took, and 8 s on
    llama3.1. A sixth of the run to know whether the number means anything.
    """
    if not reference_items:
        return {"applies": False}

    calibration = validate_judge(model, num_ctx, timeout)

    found, missed, unparsed = [], [], []
    for item in reference_items:
        judged = _judge_item(item, note, model, num_ctx, timeout)
        if judged is None:
            unparsed.append(item)
        elif judged:
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
        "calibrated": calibration["ok"],
        "calibration": calibration["agreement"],
        "control_rejected": calibration["control_rejected"],
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


_ITEM = re.compile(
    r"^\s*(?:[-*]\s*)?(DECISION|ACTION|PROPOSAL|QUESTION)\s*:\s*(?P<text>[^|]+?)"
    r"(?:\s*\|\s*(?P<quote>.+?))?\s*$", re.IGNORECASE)


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
                # The quote travels with the item, and that is load-bearing rather
                # than tidy. Only this pass sees the transcript; the consolidator
                # receives the item list alone. Dropping the quote here left the
                # consolidator asked for verbatim evidence from a transcript it had
                # never been shown, so every citation it produced was necessarily
                # invented — a structural guarantee of fabrication, arriving because
                # a requirement was added to a contract both passes share.
                quote = (m.group("quote") or "").strip()
                items.append(f"{m.group(1).upper()}: {m.group('text').strip()}"
                             + (f" | {quote}" if quote else ""))

    listing = "\n".join(items) if items else "(no items were extracted)"
    user = f"Items extracted from the meeting, in order:\n\n{listing}\n\nWrite the notes."
    response = ollama_chat(model, consolidate_system, user, num_ctx, timeout)
    calls.append({"label": "consolidate", "prompt": consolidate_system + user,
                  "response": response})
    elapsed = time.monotonic() - t0

    note, repeats = dedupe_items(response["message"]["content"].strip())

    return {
        "note": note,
        "elapsed_s": elapsed,
        "model": model,
        "rendered": transcript.render(),
        "system": extract_system + "\n" + consolidate_system,
        "calls": calls,
        "extracted": items,
        "slices": len(slices),
        "duplicates_removed": repeats,
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
    # The visible count, and the held-back count beside it when there is one. A bare
    # count here disagreed with the transcript on disk, which holds both.
    held = (f"  ({len(transcript.gated_turns)} held back by the voiceprint gate, "
            f"still in the transcript)" if transcript.gated_turns else "")
    print(f"  turns         {len(transcript.turns)}{held}")
    print(f"  model         {result['model']}  in {result['elapsed_s']:.1f}s")
    if result.get("duplicates_removed"):
        # Reported, not hidden. The consolidator repeating itself is a fact about the
        # chunked path's reliability, and the note it came from no longer shows it.
        print(f"  consolidate   {result['duplicates_removed']} repeated item(s) removed "
              f"— the merge pass emitted the same claim more than once")

    # Before the fabrication checks, because this one is about what is MISSING from
    # the input rather than what the model added to it. Every check below asks
    # whether the notes say more than the transcript supports; this asks whether
    # the transcript itself is short of the meeting. A reader who does not know
    # that words were removed will read a gap as a meeting that had none.
    for warning in transcript.gate_warnings:
        print(f"  capture       {warning}")

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
        # Never print this number without saying who produced it and whether that
        # judge agreed with the known answers in this same run. It stays one
        # model's opinion of another model's output; what the calibration line
        # buys is knowing whether the opinion tracks the rule the hand scoring
        # used. An uncalibrated judge does not get to render a score — the 8B
        # model rated its own notes 5/6 where hand-checking gave 1/6, and a
        # number like that printed beside a warning is still read as a number.
        if recall["calibrated"]:
            print(f"  recall        {recall['score']} — judged by {recall['judge']}, "
                  f"which agreed with {recall['calibration']} known answers in "
                  "this run")
        else:
            reason = (f"agreed with only {recall['calibration']} known answers"
                      if recall["control_rejected"] else
                      "passed a control judge rigged to answer PRESENT, so the "
                      "fixtures decided nothing")
            print(f"  recall        NOT MEASURED — {recall['judge']} "
                  f"{reason}. Its verdicts below are not a score.")
        for m in recall["missed"]:
            print(f"                  MISSED: {m['item'][:78]}")
        for u in recall["unparsed"]:
            print(f"                  NO VERDICT (judge did not answer): {u[:60]}")

    if grounding["ok"]:
        print("  grounding     every content word traces to something said")
    else:
        print(f"  grounding     for review (advisory, expect paraphrase): "
              f"{grounding['ungrounded']}")

    cites = check_citations(note, transcript)
    if cites["applies"]:
        if cites["fabricated"]:
            # Not advisory. A quote that is not in the transcript is the one
            # failure in this file with no innocent explanation.
            print(f"  citations     FABRICATED — {len(cites['fabricated'])} of "
                  f"{len(cites['fabricated']) + len(cites['cited'])} quotes are not "
                  f"in the transcript")
            # Printed whole. An earlier version cut these at 70 characters, which
            # sliced them mid-word and made every failure look like a truncation
            # bug in the checker rather than a fabrication by the model — the one
            # reading this line most needs to rule out. A quote short enough to
            # fit was indistinguishable from one that had been cut, so the display
            # destroyed exactly the evidence it existed to show.
            for row in cites["fabricated"][:5]:
                print(f"                {row['why']}: {row['quote']!r}")
        elif cites["cited"]:
            at = [f"{r['start']:.0f}s" for r in cites["cited"][:4] if r["start"]]
            print(f"  citations     {len(cites['cited'])} verified against the "
                  f"transcript{' at ' + ', '.join(at) if at else ''}")
        if cites["unverifiable"]:
            print(f"  citations     {len(cites['unverifiable'])} quote(s) too short to "
                  f"test — neither evidence nor fabrication")
        if cites["repeats"]:
            print(f"  citations     {cites['repeats']} claim(s) repeat an earlier one "
                  f"verbatim — the note says the same thing twice")
        if cites["layout"] == "collapsed":
            # Not a failure — the checker reads both — but the contract asks for the
            # quote on its own line, and which layout a model produced has been the
            # hardest thing here to state precisely because the evidence was a note
            # somebody had to look at. Recorded so it stops being anecdote.
            sep = {">": "a blockquote marker", "|": "a pipe"}.get(cites["separator"],
                                                                       "an unknown mark")
            print(f"  citations     quotes arrived on the claim's own line after {sep}, "
                  f"not below it — the contract asks for below")
        if cites["uncited"]:
            print(f"  citations     {len(cites['uncited'])} item(s) carry no quote, "
                  f"so nothing can be traced back to the words")

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
    # its docstring. Citations are NOT advisory — an unlocatable quote is the one
    # failure here with no innocent explanation, where a paraphrase failing the
    # grounding check has several. A missing quote does not fail the run: it is a
    # model ignoring a format instruction, which is a prompt problem and is
    # reported as its own line rather than folded into a correctness verdict.
    #
    # The checks are returned rather than only printed. A caller that needs a
    # finding — the note artifact needs the citation outcome, because that outcome
    # is what a reader has to see beside each claim — would otherwise re-run the
    # check and become a second authority on it. Every defect this file has had to
    # repair was two places deciding the same thing, so the verdict and the
    # evidence behind it leave here together.
    checks = {
        "context": ctx,
        "attribution": attr,
        "numbers": nums,
        "prompt_echo": echo,
        "grounding": grounding,
        "owner_grounding": owners,
        "recall": recall,
        "citations": cites,
    }
    return {"passed": verdict(checks), **checks}


def verdict(checks: dict) -> bool:
    """Whether a run passes, from its checks. The only place that decides.

    Written once because the alternative was tried in this very file, in the change
    that repaired two parsers disagreeing about the same question: `recheck` grew its
    own formula, and it diverged three ways within a dozen lines of the original. It
    dropped `context`, so a run whose prompt had been truncated could be rechecked into
    passing. It lost `attribution`'s `applies` guard, so a level that permits no actors
    could fail on a check that does not apply to it. And it swept in `grounding`, which
    is advisory by an explicit decision recorded ten lines above.

    None of those were reasoning errors. They are what happens when a formula is
    retyped from memory beside the one it has to match.
    """
    ctx = checks["context"]
    attr = checks["attribution"]
    return (
        ctx["ok"] is not False
        and (not attr["applies"] or attr["ok"])
        and checks["numbers"]["ok"]
        and checks["prompt_echo"]["ok"]
        and checks["citations"]["ok"]
    )


NOTE_SCHEMA = "note/1"

# The four states a claim can be in, and every one of them has to be renderable.
# `docs/journeys.md` J1 beat 3 is the operator deciding whether to trust a claim, and
# a format showing only the good case would hide the majority of what the runs produce:
# across three real meetings roughly a third of claims carried locatable evidence, and
# on the longest, composed quotes outnumbered located ones. Both halves are common.
#
# **These names were `verified` and `unsupported`, and both overstated their warrant.**
# `verified` was read as "this claim checks out" — including by the surface, which drew
# it with a green tick — when all the check establishes is that the quoted words appear
# at a turn. Whether they *support the claim* is a different question that nothing asked:
# one action item reading "Burn extra CD-ROMs for meeting attendees" cites turn 307,
# "You know, I personally would not want a CD of my meeting", which is verified speech
# arguing the opposite of its claim. And `unsupported` collided with that same question
# while actually meaning something narrower and more specific — that the words are not in
# the transcript at all, so the model composed them.
LOCATED = "located"        # the quoted words are in the transcript, at a known turn
COMPOSED = "composed"      # they are not, and the transcript was the model's only input
UNTESTABLE = "untestable"  # too short to distinguish evidence from coincidence
UNQUOTED = "unquoted"      # the claim offered no evidence at all


def measure_support(artifacts: list[Path], model: str, num_ctx: int,
                    timeout: int) -> int:
    """Do located quotes support the claims they are attached to?

    The question `verified` was taken to answer and nothing asked. Locating a quote
    proves the words were said at a turn; it says nothing about whether they bear on the
    claim. One action item, "Burn extra CD-ROMs for meeting attendees", cites turn 307 —
    "You know, I personally would not want a CD of my meeting" — which is located speech
    arguing the opposite of its claim, rendered with a tick.

    **Only located claims can be measured**, which is the honest boundary: a composed
    quote's words were never said, so judging their support would measure the model's
    invention rather than the meeting. That is 31 claims across the three meetings.

    Replaces a narrower settlement measurement, whose question — "do these words show
    something settled" — is what this one answers when the claim's type is in front of
    the judge. Its disfluent fixtures live on here, because they are the reason its
    calibration was worth anything.

    Calibration runs first and its failure is the whole result.
    """
    print("\n=== calibrating the support judge ===\n")
    real = score_fixtures(
        lambda item, note: _fixture_judge_support(item, note, model, num_ctx, timeout),
        SUPPORT_FIXTURES)
    control = score_fixtures(
        lambda item, note: _fixture_judge_support(item, note, model, num_ctx, timeout,
                                                 SABOTAGED_SUPPORT_JUDGE),
        SUPPORT_FIXTURES)
    for d in real["detail"]:
        mark = "pass" if d["got"] == d["want"] else "FAIL"
        want = "supports" if d["want"] else "does not"
        print(f"  [{mark}] {want:9s} — {d['item'][:66]}")
    print(f"\n  agreement {real['agreement']}")
    print(f"  control   {control['agreement']} for a judge rigged to answer YES — "
          f"{'rejected' if not control['ok'] else 'NOT REJECTED'}")

    if control["ok"]:
        print("\n  A judge told to answer YES unconditionally cleared these fixtures,\n"
              "  so they are not fixtures and no figure below would mean anything.")
        return 1
    if not real["ok"]:
        print("\n  This model cannot be trusted to tell supporting evidence from\n"
              "  contradicting, unrelated, or merely weaker evidence. No figure is\n"
              "  reported: an uncalibrated judge's number is worse than none.\n"
              "  Measured 2026-07-29: gemma3:12b is the judge this repository has\n"
              "  calibrated for this class of question. Try --model gemma3:12b.")
        return 1

    print("\n=== do located quotes support their claims ===\n")
    supported = unsupported = unparsed = 0
    by_kind: dict[str, list[bool | None]] = {}
    for path in artifacts:
        doc = json.loads(path.read_text())
        claims = [c for c in doc["claims"] if c["status"] == LOCATED]
        verdicts = []
        print(f"  {doc['meeting']['id']}: {len(claims)} located of "
              f"{len(doc['claims'])} claims")
        for c in claims:
            verdict = _judge_support(c["claim"], c["quote"], c.get("type"), model,
                                     num_ctx, timeout)
            by_kind.setdefault(c.get("type") or "untyped", []).append(verdict)
            if verdict is None:
                unparsed += 1
            elif verdict:
                supported += 1
            else:
                unsupported += 1
            word = {True: "supports", False: "does not", None: "no verdict"}[verdict]
            print(f"    [{word:10s}] {(c.get('type') or '?').upper():8s} "
                  f"{c['claim'][:40]}")
            # Every verdict shows its quote, supporting ones included. A reader checking
            # a rate needs to see the cases on both sides of it.
            print(f"                 turn {c['turn']}: {c['quote'][:88]!r}")
            verdicts.append({"claim": c["claim"], "quote": c["quote"],
                             "supports": verdict})

        # Written into the artifact so the measurement is reusable instead of a console
        # run somebody has to remember. Content-addressed on claim and quote rather than
        # keyed by position: `recheck` rebuilds `claims` from the citation buckets, and a
        # verdict stored on a claim would be silently dropped the next time it ran.
        doc["support"] = {
            "judge": model,
            "calibration": real["agreement"],
            "measured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "verdicts": verdicts,
        }
        path.write_text(json.dumps(doc, indent=2) + "\n")
        print(f"    wrote {len(verdicts)} verdict(s) into {path.name}")

    judged = supported + unsupported
    print(f"\n  {supported} of {judged} located quotes support their claim"
          + (f"; {unparsed} unparsed" if unparsed else ""))
    for kind, verdicts in sorted(by_kind.items()):
        ok = sum(1 for v in verdicts if v)
        print(f"    {kind:9s} {ok} of {len(verdicts)}")
    print(f"\n  {judged} claims across {len(artifacts)} meetings and one judge. The "
          f"per-kind rows are\n  too thin to compare kinds — they are shown so a reader "
          f"can see the split, not\n  so a rate can be read off them.")
    return 0


def recheck(artifact: Path) -> dict:
    """Re-derive an existing artifact's citations without calling a model.

    Needed because the checker changes. The two-parser defect meant three artifacts on
    disk reported 0 quotes where 41 were present, and re-running the model to correct
    that would have cost eleven minutes on the longest meeting *and* produced a
    different note — so the corrected figure would not have been the corrected figure
    for the note that was measured. Re-deriving keeps the note fixed and moves only the
    judgement, which is what a correction is.

    Only the citation check is recomputed, because it is the only one whose inputs
    survive in the artifact: the note text and the transcript. `numbers`, `grounding`
    and `prompt_echo` compare against the rendered prompt and the system message, which
    are not stored; carrying their stored verdicts forward is honest, silently
    recomputing them against a substitute input would not be.
    """
    doc = json.loads(artifact.read_text())
    if doc.get("schema") != NOTE_SCHEMA:
        raise SystemExit(f"{artifact}: expected {NOTE_SCHEMA}, got {doc.get('schema')!r}")
    if "transform" not in doc:
        raise SystemExit(f"{artifact}: no `transform`, so the turn indices cannot be "
                         f"resolved. Regenerate from the model.")

    t = load((artifact.parent / doc["transcript"]).resolve())
    transform = doc["transform"]
    if transform == "strip":
        t = t.strip_attribution()
    elif transform == "as-channel":
        t = t.as_channel(None)
    elif transform == "simulate-bleed":
        t = t.simulate_bleed()
    elif transform is not None:
        raise SystemExit(f"{artifact}: unknown transform {transform!r}")

    cites = check_citations(doc["note"], t)
    doc["claims"] = _claims_in_read_order(cites)
    doc["checks"]["citations"] = cites
    # The stored verdict was formed with the old citation result in it, so it has to
    # move too — otherwise the artifact would carry a corrected finding under an
    # uncorrected pass mark.
    was = doc["passed"]
    doc["passed"] = verdict(doc["checks"])
    if support := doc.get("support"):
        judged = {(v["claim"], v["quote"]) for v in support["verdicts"]}
        now = {(c["claim"], c["quote"]) for c in doc["claims"] if c["status"] == LOCATED}
        if stale := judged - now:
            print(f"      {len(stale)} stored support verdict(s) no longer match any "
                  f"located claim — re-run --measure-support")
        if fresh := now - judged:
            print(f"      {len(fresh)} located claim(s) have no support verdict")
    doc["provenance"]["rechecked_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    artifact.write_text(json.dumps(doc, indent=2) + "\n")

    by = Counter(c["status"] for c in doc["claims"])
    print(f"  {artifact.name}: {cites['items']} items -> "
          f"{', '.join(f'{n} {s}' for s, n in by.most_common())}")
    if cites["template_echo"]:
        print(f"      {cites['template_echo']} claim(s) carried template punctuation")
    if was != doc["passed"]:
        print(f"      verdict moved: passed {was} -> {doc['passed']}")
    return doc


def _claims_in_read_order(cites: dict) -> list[dict]:
    """The four buckets merged back into the order a reader meets them in."""
    claims = [
        {"status": status, **row}
        for status, rows in ((LOCATED, cites["cited"]),
                             (COMPOSED, cites["fabricated"]),
                             (UNTESTABLE, cites["unverifiable"]),
                             (UNQUOTED, cites["uncited"]))
        for row in rows
    ]
    claims.sort(key=lambda c: c["at"])
    return claims


def note_artifact(result: dict, transcript: Transcript, checks: dict,
                  transcript_path: Path, out_dir: Path,
                  transform: str | None = None) -> dict:
    """The note as data, with each claim's evidence state attached.

    The markdown a model emits is a *rendering* of a note, not the note. It cannot
    carry which claims were checked or what the check found, so a surface reading it
    would have to re-derive both and would disagree with `report` about it. This is
    the artifact; the markdown is kept beside it for reading.

    **Evidence is referenced, never copied.** A claim carries a turn index, and the
    words live in the transcript at `transcript`. Duplicating the speech into the
    note would make two records of what was said and let them drift — and
    `docs/journeys.md` retains the transcript precisely so the note does not have to
    be self-contained. A renderer joins the two.

    COMPOSED deserves its plain name. The model's entire input was this
    transcript, so a quote that is not in it was not misheard or lost to a failed
    capture — it was composed. That distinction is the one thing J1 beat 4 says the
    product must never blur, and here it is not ambiguous.
    """
    # Read order, not verdict order. The buckets group by outcome because that is
    # what a verdict needs; a reader meets these claims one after another. Shared with
    # `recheck` rather than written twice — two merges would be two answers to what
    # order a note is in.
    claims = _claims_in_read_order(checks["citations"])

    return {
        "schema": NOTE_SCHEMA,
        "meeting": {
            "id": transcript_path.stem,
            "source": transcript.source,
            "attribution": transcript.attribution,
            "speakers": transcript.speakers,
            "turns": len(transcript.turns),
            # Both counts, because the gate's held-back turns are still evidence the
            # operator may overrule, and a surface that shows only the visible count
            # disagrees with the transcript on disk.
            "gated_turns": len(transcript.gated_turns),
            "duration_s": max((t.start for t in transcript.turns if t.start is not None),
                              default=None),
        },
        # Where the words are, and which shape of them the turn indices count.
        # Relative so an exported note and its transcript can be moved together; a
        # renderer resolves it against the note's own directory.
        #
        # `transform` is not metadata, it is the key to the indices. A claim's `turn`
        # is a position in the transcript AS THE MODEL SAW IT, and the transforms do
        # not all preserve positions — `simulate_bleed` doubles every line, so a
        # renderer that loaded the raw file would resolve every citation to the wrong
        # words while looking like it worked. `strip_attribution` happens to preserve
        # them, which is exactly why this cannot be left implicit: the safe case would
        # have hidden the unsafe one until someone rendered a bleed run.
        "transcript": os.path.relpath(transcript_path, out_dir),
        "transform": transform,
        "note": result["note"],
        "claims": claims,
        "capture": transcript.gate,
        "provenance": {
            "model": result["model"],
            "elapsed_s": round(result["elapsed_s"], 1),
            "passes": 2 if "extracted" in result else 1,
            "slices": result.get("slices"),
            # Belongs here rather than in `checks` because the note no longer contains
            # the evidence: once the repeats are excised, nothing recomputable from the
            # note text can recover the count, so a `--recheck` would drop it.
            #
            # `null` on the single-pass path, never 0. Only the chunked path excises
            # repeats, so 0 there would assert a measurement that was never taken — and
            # the whole reason the fix is chunked-only is to leave a single-pass
            # regression visible. `checks.citations.repeats` is the number that covers
            # both paths. Same reasoning as `transform`: absent and zero are different
            # facts and a field that conflates them hides the one that matters.
            "duplicates_removed": result.get("duplicates_removed"),
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        },
        # Carried whole. A surface may only need citations today, but a note whose
        # own record of what was checked is partial cannot be audited later.
        "checks": {k: v for k, v in checks.items() if k != "passed"},
        "passed": checks["passed"],
    }


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
        mark = "pass" if ok else "FAIL"
        want = "clean" if expect_ok else "flagged"
        print(f"  [{mark}] expects {want:8s} — {label}")
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

    # Verdict parsing is the whole of what stands between a model's reply and a
    # recall number, and asking items one at a time removed the numbering that
    # used to sit in front of it. It has failed twice: llama3.1 answering
    # MENTIONED / NOT MENTIONED to a PRESENT|ABSENT regex, and a long note
    # pushing the judge into prose. Neither is caught by the fixture arms below,
    # which hand the scorer verdicts directly and never reach the parser —
    # breaking the negative alternation so that "NOT MENTIONED" reads as present
    # leaves every one of them green. Replayed here against known strings.
    print("\n=== verdict parsing ===\n")
    for reply, want in [
        ("PRESENT", True),
        ("ABSENT", False),
        # The regression itself: negatives are matched first because the string
        # for "no" is contained in the string for "yes".
        ("NOT MENTIONED", False),
        ("MENTIONED", True),
        ("Yes, the notes cover this.", True),
        ("No, the notes do not mention it.", False),
        ("  present  ", True),
        # Prose in neither vocabulary is unparsed, never folded into a count. A
        # parse failure arriving dressed as a verdict is worse than a crash.
        ("It is difficult to say either way from these notes.", None),
    ]:
        got = _parse_verdict(reply)
        ok = got == want
        failures += not ok
        name = {True: "present", False: "absent", None: "unparsed"}
        print(f"  [{'pass' if ok else 'FAIL'}] {name[want]:8s} — {reply.strip()[:44]!r}")
        if not ok:
            print(f"          got {name[got]}")

    # The recall fixtures are the one calibration set here that a model is
    # measured against, which makes their power to reject a bad judge the thing
    # holding up every recall number. These arms need no Ollama: they replace the
    # model with a judge whose answers are known in advance, and assert the
    # fixtures fail it. A calibration set that a judge answering without reading
    # can pass reports confidence nobody earned.
    print("\n=== recall fixtures reject a judge that does not read ===\n")
    # The alternating judge's score is an artifact of the order the fixtures
    # happen to sit in, not a property of anything. Only its rejection is the
    # assertion; reordering the fixtures will move the number and must not be
    # read as the arm getting better or worse.
    flips = itertools.count()
    degenerate = [
        ("always present — the 8B model's documented failure", lambda i, n: True),
        ("always absent", lambda i, n: False),
        ("alternating, ignoring the notes", lambda i, n: next(flips) % 2 == 0),
        ("never answers at all", lambda i, n: None),
    ]
    for label, judge in degenerate:
        got = score_fixtures(judge)
        ok = not got["ok"]
        failures += not ok
        print(f"  [{'pass' if ok else 'FAIL'}] rejected — {label} "
              f"(scored {got['agreement']})")

    # Balance is what stops a degenerate judge scoring a respectable number even
    # while failing. It is asserted rather than trusted to survive editing.
    wants = [w for _, _, expected in JUDGE_FIXTURES for w in expected]
    balanced = sum(wants) * 2 == len(wants)
    failures += not balanced
    print(f"  [{'pass' if balanced else 'FAIL'}] fixtures balanced — "
          f"{sum(wants)} present, {len(wants) - sum(wants)} absent")

    print("\n=== citations ===\n")
    # A real transcript's shape: contiguous speech with timestamps, so a quote can
    # be located and a turn index derived rather than trusted.
    cite_t = Transcript(source="fixture", attribution=CHANNEL, turns=[
        Turn(text="i think we should go with the rubber for the case", speaker="Me",
             start=12.0),
        Turn(text="the supplier said eight weeks which is too long for us",
             speaker="Them", start=48.5),
    ])

    def cite_case(label: str, note: str, want_ok: bool, **expect) -> None:
        nonlocal failures
        got = check_citations(note, cite_t)
        # Compare by what the RESULT holds, not by what the expectation looks like. An
        # int expectation used to mean "this many rows", which stopped being true when
        # the result gained a scalar count and turned a control into a TypeError.
        ok = got["ok"] == want_ok and all(
            len(got[k]) == v if isinstance(got[k], list) else got[k] == v
            for k, v in expect.items())
        failures += not ok
        print(f"  [{'pass' if ok else 'FAIL'}] {label}")
        if not ok:
            print(f"          ok={got['ok']} cited={len(got['cited'])} "
                  f"fabricated={len(got['fabricated'])} uncited={len(got['uncited'])}")

    cite_case("a quote lifted from the transcript verifies",
              "## Decisions\n- Rubber casing chosen.\n  > go with the rubber for the case",
              True, cited=1, fabricated=0)
    cite_case("and the turn index is derived here rather than trusted from the model",
              "## Decisions\n- Rubber casing chosen.\n  > go with the rubber for the case",
              True)
    cite_case("punctuation and case differences are transcription artifacts, not fabrication",
              "## Decisions\n- Rubber casing chosen.\n  > Go with the RUBBER, for the case!",
              True, cited=1)
    cite_case("a quote that is not in the transcript is caught",
              "## Decisions\n- Budget approved.\n  > the budget was approved unanimously",
              False, fabricated=1)
    cite_case("words from two different turns cannot be joined into one quote",
              "## Decisions\n- Both.\n  > for the case the supplier said eight weeks",
              False, fabricated=1)
    cite_case("a quote too short to test is neither credited nor called fabricated",
              "## Decisions\n- Rubber.\n  > the case", True,
              unverifiable=1, cited=0, fabricated=0)
    cite_case("an item with no quote is neither a pass nor a fabrication",
              "## Decisions\n- Rubber casing chosen, with no evidence offered.",
              True, uncited=1, cited=0, fabricated=0)
    # The Summary section takes no quotes by contract, and its prose must not be
    # mistaken for an uncited item — it is not a list.
    cite_case("summary prose is not counted as an uncited item",
              "## Summary\nThe team met and chose a casing material.", True, uncited=0)

    # The kind of thing a claim is, recovered from the heading it sits under. It exists
    # at extraction and was discarded by the time an artifact was written, so any
    # surface wanting to group by kind had to re-parse the note.
    def type_case(label: str, note: str, want: list[str | None]) -> None:
        nonlocal failures
        got = [i["type"] for i in _parse_claims(note)]
        ok = got == want
        failures += not ok
        print(f"  [{'pass' if ok else 'FAIL'}] {label}")
        if not ok:
            print(f"          got {got} want {want}")

    type_case("each section names its claims' kind",
              "## Decisions\n- A.\n## Action items\n- B.\n## Proposed\n- C.\n"
              "## Open questions\n- D.\n",
              ["decision", "action", "proposal", "question"])
    type_case("an unrecognised heading keeps its own words rather than being forced",
              "## Risks\n- A.\n", ["risks"])
    type_case("an item before any heading has no kind rather than a guessed one",
              "- A.\n## Decisions\n- B.\n", [None, "decision"])

    # The third layout, produced by the consolidator holding both contracts at once: it
    # kept the extraction format's pipe AND added the note format's blockquote marker,
    # so every claim in a chunked note carried a trailing pipe into the artifact.
    cite_case("a claim does not keep the separator the model left on it",
              "## Decisions\n"
              "- Rubber chosen. | > go with the rubber for the case\n"
              "- Lead time long. | > the supplier said eight weeks which is too long\n",
              True, cited=2, layout="collapsed")
    got = check_citations(
        "## Decisions\n"
        "- Rubber chosen. | > go with the rubber for the case\n"
        "- Lead time long. | > the supplier said eight weeks which is too long\n", cite_t)
    pipe_ok = all(not r["claim"].endswith("|") for r in got["cited"])
    failures += not pipe_ok
    print(f"  [{'pass' if pipe_ok else 'FAIL'}] and the claim text itself is clean")
    if not pipe_ok:
        print(f"          got {[r['claim'] for r in got['cited']]}")

    # Repeats are counted on both paths, which is what makes the chunked-only placement
    # of `dedupe_items` safe: a single-pass regression is visible rather than reported
    # as a clean zero by a field that path can never populate.
    cite_case("a repeated claim is counted wherever it appears",
              "## Decisions\n- Rubber chosen.\n- Lead time long.\n- Rubber chosen.\n",
              True, repeats=1)
    cite_case("distinct claims count no repeats",
              "## Decisions\n- Rubber chosen.\n- Lead time long.\n", True, repeats=0)
    cite_case("punctuation does not make a repeat look distinct here either",
              "## Decisions\n- Rubber chosen.\n- RUBBER, chosen!\n", True, repeats=1)

    # The layout a note used, recorded rather than eyeballed later.
    # The fourth shape, which appeared when a fifth section was added to the prompt: the
    # consolidator stopped converting the extraction format and passed `claim | quote`
    # straight through. Reading only `>` reported 93 located quotes on one meeting as
    # absent — the same defect as the next-line-only parser, one character over.
    cite_case("a pipe separates a claim from its quote as readily as a blockquote mark",
              "## Decisions\n"
              "- Rubber chosen. | go with the rubber for the case\n"
              "- Lead time long. | the supplier said eight weeks which is too long\n",
              True, cited=2, uncited=0, layout="collapsed", separator="|")
    cite_case("and the separator is recorded, since collapsed no longer says which",
              "## Decisions\n"
              "- Rubber chosen. > go with the rubber for the case\n"
              "- Lead time long. > the supplier said eight weeks which is too long\n",
              True, separator=">")
    cite_case("the next-line layout is recorded as such",
              "## Decisions\n- Rubber chosen.\n  > go with the rubber for the case",
              True, layout="next-line")
    cite_case("a note with no citations at all records no layout",
              "## Decisions\n- Rubber chosen.", True, layout="none")
    #  The verdict has to move, or none of the above changes a run's outcome.
    verdict_note = "## Decisions\n- Budget approved.\n  > the budget was approved"
    cite_case("a fabricated citation is not advisory", verdict_note, False)

    # The layout the model actually produced on two of three real meetings, and the
    # blind spot that made 41 located quotes report as zero. Every fixture above uses
    # the next-line form the contract asks for, which is why twelve controls passed
    # while the checker was wrong on most real output.
    collapsed_note = (
        "## Decisions\n"
        "- Rubber casing chosen. > go with the rubber for the case\n"
        "- Lead time too long. > the supplier said eight weeks which is too long\n")
    cite_case("quotes collapsed onto the items' own lines are still citations",
              collapsed_note, True, cited=2, uncited=0)
    cite_case("and a collapsed quote that is not in the transcript still fails",
              "## Decisions\n"
              "- Budget approved. > the budget was approved today\n"
              "- Rubber chosen. > go with the rubber for the case\n",
              False, fabricated=1, cited=1, uncited=0)
    cite_case("template punctuation the model copied is stripped and counted",
              "## Decisions\n"
              "- <Rubber casing chosen> > go with the rubber for the case\n"
              "- <Lead time too long> > the supplier said eight weeks which is too long\n",
              True, cited=2, template_echo=2)
    cite_case("a claim with no quote is not read as a collapsed one",
              "## Decisions\n- Rubber casing chosen with nothing offered.",
              True, uncited=1, cited=0, template_echo=0)
    # The collapsed reading has to be bounded, or it manufactures the failure it was
    # added to stop under-reporting. A `>` inside a claim is prose, and reading it as a
    # citation would report a fabrication that never happened — the crying-wolf
    # direction this file has already had to repair once.
    cite_case("a comparison inside a claim is not read as a citation",
              "## Decisions\n"
              "- Throughput target set at > 100 requests per second.\n"
              "  > go with the rubber for the case\n",
              True, cited=1, fabricated=0, uncited=0)
    cite_case("and a lone mid-line arrow in a note with no citations is left alone",
              "## Decisions\n- Throughput target set at > 100 requests per second.",
              True, uncited=1, cited=0, fabricated=0)
    # The invariant, asserted from outside rather than trusted from the assert inside:
    # buckets that are allowed to disagree about their coverage lose items into
    # whichever one is benign, and `uncited` is benign.
    partition_note = (
        "## Decisions\n"
        "- Located. > go with the rubber for the case\n"
        "- Composed. > the budget was approved today\n"
        "- Short. > the case\n"
        "- Bare.\n")
    got = check_citations(partition_note, cite_t)
    covered = sum(len(got[k]) for k in ("cited", "fabricated", "unverifiable", "uncited"))
    part_ok = got["items"] == 4 and covered == 4
    failures += not part_ok
    print(f"  [{'pass' if part_ok else 'FAIL'}] every item lands in exactly one bucket, "
          f"across all four outcomes")
    if not part_ok:
        print(f"          items={got['items']} covered={covered}")

    print("\n=== the consolidator repeating itself ===\n")

    def dedupe_case(label: str, note: str, want_removed: int, want_items: int,
                    want_first_quote: str | None = None) -> None:
        nonlocal failures
        got, removed = dedupe_items(note)
        items = _parse_claims(got)
        ok = removed == want_removed and len(items) == want_items
        if want_first_quote is not None:
            ok = ok and items and items[0]["quote"] == want_first_quote
        # The excision must not corrupt what it leaves behind: every surviving item has
        # to still parse, and the buckets have to still partition them.
        cites = check_citations(got, cite_t)
        covered = sum(len(cites[k]) for k in
                      ("cited", "fabricated", "unverifiable", "uncited"))
        ok = ok and covered == cites["items"] == len(items)
        failures += not ok
        print(f"  [{'pass' if ok else 'FAIL'}] {label}")
        if not ok:
            print(f"          removed={removed} want={want_removed} "
                  f"items={len(items)} want={want_items} covered={covered}")

    dedupe_case("an exact repeat is dropped and the first is kept",
                "## Decisions\n- Rubber chosen.\n- Lead time long.\n- Rubber chosen.\n",
                1, 2)
    dedupe_case("a repeat takes its quote line with it, not the survivor's",
                "## Decisions\n"
                "- Rubber chosen.\n  > go with the rubber for the case\n"
                "- Rubber chosen.\n  > the supplier said eight weeks which is too long\n",
                1, 1, "go with the rubber for the case")
    dedupe_case("punctuation and case do not make two claims distinct",
                "## Decisions\n- Rubber chosen.\n- RUBBER, chosen!\n", 1, 1)
    dedupe_case("distinct claims are untouched",
                "## Decisions\n- Rubber chosen.\n- Lead time long.\n", 0, 2)
    dedupe_case("a note with no repeats is returned unchanged",
                "## Summary\nProse only, no items.\n", 0, 0)
    # Three of the same claim collapse to one, not two — the seen-set is what makes the
    # rule idempotent rather than pairwise.
    dedupe_case("three copies collapse to one",
                "## Decisions\n- A thing.\n- A thing.\n- A thing.\n", 2, 1)
    # A model's last line often has no trailing newline, and the span of a final item is
    # the one case `_parse_claims` computes from the note's length rather than the next
    # line's offset.
    dedupe_case("a repeat as the final line, with no trailing newline",
                "## Decisions\n- A thing.\n- Another.\n- A thing.", 1, 2)
    dedupe_case("a repeat whose quote is the note's final line",
                "## Decisions\n- A thing.\n  > go with the rubber for the case\n"
                "- A thing.\n  > the supplier said eight weeks which is too long",
                1, 1, "go with the rubber for the case")

    # One formula for the run's verdict, checked against the shape `recheck` reads. The
    # divergence this catches was real: a retyped formula dropped `context`, lost
    # `attribution`'s applies guard, and swept in advisory grounding.
    stored = {
        "context": {"ok": False, "reason": "tail dropped"},
        "attribution": {"applies": True, "ok": True},
        "numbers": {"ok": True}, "prompt_echo": {"ok": True},
        "grounding": {"ok": False}, "citations": {"ok": True},
    }
    v_ok = verdict(stored) is False
    stored["context"]["ok"] = True
    v_ok = v_ok and verdict(stored) is True          # advisory grounding stays advisory
    stored["attribution"] = {"applies": False, "ok": False}
    v_ok = v_ok and verdict(stored) is True          # a check that does not apply
    failures += not v_ok
    print(f"  [{'pass' if v_ok else 'FAIL'}] the verdict honours context, the applies "
          f"guard, and grounding being advisory")

    # The quote has to survive the merge, because only the extraction pass sees a
    # transcript. When _ITEM dropped everything after the pipe, the consolidator
    # was asked for verbatim evidence from a transcript it had never been shown,
    # which made every citation on the chunked path invented by construction.
    def item_case(label: str, line: str, want) -> None:
        nonlocal failures
        m = _ITEM.match(line)
        got = None if not m else (m.group(1).upper(), m.group("text").strip(),
                                  (m.group("quote") or "").strip())
        ok = got == want
        failures += not ok
        print(f"  [{'pass' if ok else 'FAIL'}] {label}")
        if not ok:
            print(f"          got {got!r}")

    item_case("an extracted item carries its evidence through the merge",
              "ACTION: Send the corpus licence | i'll send an email and ask",
              ("ACTION", "Send the corpus licence", "i'll send an email and ask"))
    item_case("an item with no evidence still parses, rather than being dropped",
              "DECISION: Delay the anonymisation",
              ("DECISION", "Delay the anonymisation", ""))
    item_case("a quote containing a pipe keeps everything after the first one",
              "QUESTION: Which encoding | we said utf-8 | not latin-1",
              ("QUESTION", "Which encoding", "we said utf-8 | not latin-1"))

    print("\n=== the run's verdict, and the artifact it writes ===\n")
    # `check_citations` returning ok=False is not what stops a run — `report`'s
    # aggregation is, and until now nothing exercised it. The controls above all
    # tested the check while the caller went unexamined, which is the same shape as
    # every defect this project has had to repair: validation placed where it was
    # convenient rather than where it was relied upon. A real run reported 106
    # fabricated quotes and its recorded exit status was 0, which is either this
    # aggregation or the harness around it — untestable while the verdict had no
    # control at all.
    def verdict_result(note: str) -> dict:
        prompt = "system and transcript"
        return {
            "note": note,
            "rendered": "we should go with the rubber for the case",
            "system": "instructions that share no long phrase with the note",
            "model": "fixture",
            "elapsed_s": 0.0,
            "calls": [{"label": "single pass", "prompt": prompt,
                       "response": {"prompt_eval_count": 500}}],
        }

    verdict_t = Transcript(source="fixture", attribution=CHANNEL, turns=[
        Turn(text="we should go with the rubber for the case", speaker="Me", start=3.0),
    ])

    def verdict_case(label: str, note: str, want_pass: bool,
                     want_status: str | None = None) -> None:
        nonlocal failures
        res = verdict_result(note)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            checks = report(res, verdict_t, [], None, 32768)
            doc = note_artifact(res, verdict_t, checks, Path("corpus/fix.json"),
                                Path("out"))
        ok = checks["passed"] == want_pass
        if want_status is not None:
            ok = ok and [c["status"] for c in doc["claims"]] == [want_status]
        # The artifact must agree with the verdict it was built from rather than
        # recomputing it, which is the reason `report` returns its checks.
        ok = ok and doc["passed"] == checks["passed"]
        failures += not ok
        print(f"  [{'pass' if ok else 'FAIL'}] {label}")
        if not ok:
            print(f"          passed={checks['passed']} want={want_pass} "
                  f"statuses={[c['status'] for c in doc['claims']]}")

    verdict_case("a fabricated quote fails the run, not just the check",
                 "## Decisions\n- Budget approved.\n  > the budget was approved today",
                 False, COMPOSED)
    verdict_case("a located quote passes and is marked verified",
                 "## Decisions\n- Rubber chosen.\n  > go with the rubber for the case",
                 True, LOCATED)
    verdict_case("a claim with no quote does not fail the run, and is marked unquoted",
                 "## Decisions\n- Rubber chosen, with nothing offered.", True, UNQUOTED)
    verdict_case("a quote too short to test does not fail the run",
                 "## Decisions\n- Rubber.\n  > the case", True, UNTESTABLE)

    # Read order, because that is what a surface renders and the buckets destroy it.
    ordered = verdict_result(
        "## Decisions\n"
        "- Budget approved.\n  > the budget was approved today\n"
        "- Rubber chosen.\n  > go with the rubber for the case\n")
    with contextlib.redirect_stdout(io.StringIO()):
        ordered_checks = report(ordered, verdict_t, [], None, 32768)
        ordered_doc = note_artifact(ordered, verdict_t, ordered_checks,
                                    Path("corpus/fix.json"), Path("out"))
    got_order = [c["status"] for c in ordered_doc["claims"]]
    order_ok = got_order == [COMPOSED, LOCATED]
    failures += not order_ok
    print(f"  [{'pass' if order_ok else 'FAIL'}] claims keep the order they are read "
          f"in, not the order they were judged in")
    if not order_ok:
        print(f"          got {got_order}")

    # Computed here, after the last control. An earlier version derived it above
    # the verdict block, so a failure in the newest controls could not move the
    # summary line — a verdict formed before its evidence arrived, which is the
    # defect those very controls exist to catch.
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
    p.add_argument("--measure-support", type=Path, nargs="+", metavar="NOTE.JSON",
                   help="judge whether each located quote supports the claim it is "
                        "attached to; calibrates the judge first and reports no figure "
                        "if it fails")
    p.add_argument("--recheck", type=Path, nargs="+", metavar="NOTE.JSON",
                   help="re-derive the citation check for existing note/1 artifacts "
                        "without calling a model, and rewrite them in place")
    p.add_argument("--reference", type=Path,
                   help="a list of expected items to measure recall against "
                        "(a platform's own action items, or a human's notes)")
    args = p.parse_args()

    if args.self_test:
        return run_self_test()
    if args.measure_support:
        return measure_support(args.measure_support, args.model, args.num_ctx,
                               args.timeout)
    if args.recheck:
        print("\n=== re-derived, no model call ===\n")
        rechecked = [recheck(a) for a in args.recheck]
        return 0 if all(d["passed"] for d in rechecked) else 1
    if args.validate_judge:
        v = validate_judge(args.model, args.num_ctx, 300)
        print(f"\n=== recall judge: {v['model']} ===\n")
        for d in v["detail"]:
            got = {True: "present", False: "absent", None: "UNPARSED"}[d["got"]]
            want = "present" if d["want"] else "absent"
            print(f"  [{'pass' if d['got'] == d['want'] else 'FAIL'}] "
                  f"wanted {want:8s} got {got:8s} — {d['item'][:60]}")
        print(f"\n  agreement {v['agreement']}")
        print(f"  control   {v['control']} for a judge rigged to answer PRESENT — "
              f"{'rejected' if v['control_rejected'] else 'NOT REJECTED'}")
        if not v["control_rejected"]:
            print("  The fixtures did not reject a judge that answers without\n"
                  "  reading. Nothing above is evidence about the real judge.")
        elif not v["ok"]:
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
    checks = report(result, t, stripped_speakers, reference, args.num_ctx, expected)

    if args.out:
        args.out.write_text(result["note"] + "\n")
        print(f"\n  wrote {args.out}")
        # The artifact, beside the reading copy. `note/1` is what a surface renders:
        # the markdown alone cannot say which claims were checked or what was found,
        # and a renderer that re-derived that would become a second authority on it.
        artifact = args.out.with_suffix(".note.json")
        transform = ("simulate-bleed" if args.simulate_bleed
                     else "as-channel" if args.as_channel
                     else "strip" if args.strip else None)
        doc = note_artifact(result, t, checks, args.transcript, args.out.parent,
                            transform)
        artifact.write_text(json.dumps(doc, indent=2) + "\n")
        by_status = Counter(c["status"] for c in doc["claims"])
        print(f"  wrote {artifact} ({len(doc['claims'])} claims: "
              f"{', '.join(f'{n} {s}' for s, n in by_status.most_common()) or 'none'})")
        if "extracted" in result:
            # Written beside the notes so the two stages can be scored apart.
            # A commitment present here and absent from the notes is a merge
            # defect; one absent from both is an extraction defect, and they do
            # not have the same fix.
            items = args.out.with_suffix(".items.md")
            items.write_text("\n".join(result["extracted"]) + "\n")
            print(f"  wrote {items} ({len(result['extracted'])} extracted items)")

    return 0 if checks["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())

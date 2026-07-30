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
import hashlib
import io
import itertools
import json
import os
import re
import sys
import tempfile
import time
import unicodedata
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
#
# The extraction line puts the quote BEFORE the claim, and the order is the whole
# point rather than a formatting preference. A model generates left to right, so
# whichever field it writes first is the one the second is conditioned on. Asking
# for `ACTION: ... | words` had it settle on a claim and then go looking for words
# to justify one it had already committed to — which is exactly what the support
# measurement found: of 25 claims whose quote did not support them, 9 cited words
# that did not bear on the claim at all and 1 cited words that contradicted it.
# Writing the words first makes the claim a reading of them.
#
# What this cannot fix is overstatement — 11 of those 25 — where the quote is
# genuinely about the claim's subject but says something weaker. "we could just
# get a DAT machine" supports writing "ACTION: Get a DAT machine" from those very
# words, in either order. That is what the PROPOSAL label is for, and it is added
# here in the same change because inverting without it would force the failure:
# a model reading hedged words first, offered only DECISION/ACTION/QUESTION, has
# no truthful line to write.
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
- Work through the offered source fragments in order. Select the one to three fragment
  IDs a record needs before interpreting what their exact words establish. Do not
  reproduce, tidy, complete, or join the source words. Local code resolves each
  selected ID back to its exact text.
- Take the label from the source fragments you selected, not from what would be most useful.
  DECISION: those words settle it. ACTION: someone commits in those words to doing
  it. PROPOSAL: those words suggest, offer or ask for it without settling it —
  anything hedged, "maybe we should", "we could", "I think we ought to", is a
  PROPOSAL however good the idea is. QUESTION: those words ask it and leave it open.
- A slice is mostly ordinary conversation. If it contains none of these, return an
  empty item list. Do not add a preamble, summary, heading, or commentary."""

CONSOLIDATE_RULES = """\
You are turning an ordered list of items, extracted from consecutive slices of
one meeting, into that meeting's notes.

Because the slices overlap and people repeat themselves, the same commitment
often appears several times in slightly different words.

Rules that override everything else:
- Use ONLY the items given. Add nothing, however plausible it would be.
- Merge duplicates: several records describing one commitment become one record,
  keeping the most specific wording, including the names of documents and
  systems.
- Do NOT drop an item because the list is long. Every distinct decision, action
  and open question in the input must survive into the output. This is a
  de-duplication task, not a selection task — you are not choosing the important
  ones, you are removing the repeated ones."""

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


def _ollama_payload(model: str, system: str, user: str, num_ctx: int,
                    response_format: dict | None = None) -> dict:
    """Build the documented /api/chat request without making a network call."""
    payload = {
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
    }
    if response_format is not None:
        # Ollama's documented /api/chat contract accepts a JSON schema directly at
        # `format`; do not stringify it or silently fall back to grammar-free text.
        payload["format"] = response_format
    return payload


def ollama_chat(
    model: str,
    system: str,
    user: str,
    num_ctx: int,
    timeout: int,
    response_format: dict | None = None,
):
    """Call Ollama, optionally requiring a JSON-schema response.

    Structured output constrains the model, but it is not the trust boundary.  The
    caller still receives the raw JSON text and validates it with
    ``decode_records`` below: JSON Schema cannot express duplicate object keys or
    the evidence-before-claim generation order.
    """
    body = json.dumps(_ollama_payload(model, system, user, num_ctx, response_format)).encode()
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


def model_identity_from_tags(payload: object, requested: str) -> dict:
    """Resolve one mutable model name to exactly one immutable local digest."""
    if not isinstance(payload, dict) or not isinstance(payload.get("models"), list):
        raise StructuredOutputError("Ollama /api/tags returned an invalid model list")
    candidates = [
        row for row in payload["models"]
        if isinstance(row, dict) and requested in {row.get("name"), row.get("model")}
    ]
    if len(candidates) != 1:
        raise StructuredOutputError(
            f"model {requested!r} resolved to {len(candidates)} local entries")
    row = candidates[0]
    digest = row.get("digest")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise StructuredOutputError(f"model {requested!r} has no valid SHA-256 digest")
    return {
        "requested": requested,
        "name": row.get("name") or row.get("model"),
        "digest": digest,
    }


def resolve_ollama_model(model: str, timeout: int) -> dict:
    """Resolve a model once before inference; mutable tags are not provenance."""
    req = urllib.request.Request(f"{OLLAMA}/api/tags")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            payload = json.loads(response.read())
    except (urllib.error.URLError, json.JSONDecodeError) as e:
        raise SystemExit(
            f"cannot resolve Ollama model {model!r} from {OLLAMA}/api/tags: {e}"
        ) from e
    try:
        return model_identity_from_tags(payload, model)
    except StructuredOutputError as e:
        raise SystemExit(f"cannot start inference: {e}") from e


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
# the four labels the extraction pass emits (`_LABELS`), and the section names the
# prompt already asks for. An unrecognised heading keeps its own words rather than
# being forced into one of the four, because a note that grew a fifth section is
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
# punctuation, and the pipe is in the template, because `QUOTE_FROM_ITEMS` describes an
# item list whose fields are pipe-separated.
#
# Which side of that separator holds speech is an assumption, not something the line
# says. The current chunked path normalises the consolidator input to claim-first, so
# the assumed reading matches the live contract. `check_citations` still measures the
# opposite reading for artifacts generated before that normalisation, and for a model
# that copies an unexpected layout despite it.
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
    """Legacy Markdown dedupe, retained only to keep its historical controls executable.

    The consolidator repeats itself. Measured on a 1365-turn meeting: extraction
    produced 160 items with one redundant pair, and consolidating them produced 83
    items of which **14 were exact repeats of an earlier claim** — the merge step
    introducing duplication rather than resolving it. The single-pass path produced
    none on either shorter meeting. The structured path no longer calls this: complete
    typed source-ID coverage is proved before rendering, and deleting Markdown after
    that proof would invalidate it.

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
    wolf, which this project has already shipped once and had to repair. Some
    corpora also put whitespace before English contraction suffixes (`we 'd`,
    `did n't`) while a model copies the same words as `we'd`, `didn't`. Join only
    those closed-class suffixes. Do not smooth disfluencies or repeated tokens:
    those are recorded words, and deleting them is not transcription punctuation.
    """
    normalized = re.sub(
        r"\s+(?=(?:'(?:s|d|re|ve|ll|m)|n't)\b)",
        "",
        s.lower(),
    )
    return re.findall(r"[a-z0-9']+", normalized)


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
    # A collapsed line has two sides and no marker saying which is speech. `_SAME_LINE`
    # assumes the current contract's reading order — claim, separator, quote. The live
    # chunked path now feeds the consolidator in that order too; the reverse diagnostic
    # remains for artifacts generated before that normalisation and for contract
    # deviations a later `--recheck` must not silently misread.
    #
    # Counted rather than corrected. Swapping the sides on evidence would change the
    # measured fabrication rate in the same run that changes the prompt, and there
    # would be no way to say which moved it. This says how many collapsed items locate
    # only when read backwards; if it is large the parser is wrong, and `--recheck`
    # exists to move the judgement without regenerating the note. Both sides must first
    # meet the quote-length floor: `locate` deliberately returns None without searching
    # shorter text, so treating that None as "not in the transcript" would assert a
    # comparison the checker never made.
    reversed_locatable = sum(
        1 for it in items
        if it["layout"] == "collapsed" and it["quote"] is not None
        and len(_seq(it["quote"])) >= _MIN_QUOTE_WORDS
        and len(_seq(it["claim"])) >= _MIN_QUOTE_WORDS
        and locate(it["quote"]) is None and locate(it["claim"]) is not None
    )
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
        "reversed_locatable": reversed_locatable,
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


def _support_judge_prompt(claim: str, quote: str,
                          kind: str | None) -> str:
    """The exact per-verdict user prompt, shared by inference and provenance."""
    label = f"{kind.upper()}: " if kind else ""
    return f"CLAIM:\n{label}{claim}\n\nWORDS SAID IN THE MEETING:\n{quote}"


def _safe_support_receipt(response: dict) -> dict:
    """Retain a reproducible verdict without retaining arbitrary model output.

    YES and NO are safe to keep: they contain no transcript text. Anything else is
    hashed but not copied, and therefore cannot become a displayed conclusion.
    """
    raw = response.get("message", {}).get("content", "")
    if not isinstance(raw, str):
        raw = ""
    token = raw.strip().upper()
    safe_response = raw if token in {"YES", "NO"} else None
    return {
        "judge_response": safe_response,
        "judge_response_sha256": _sha256(raw),
        "supports": {"YES": True, "NO": False}.get(token),
    }


def _judge_support_receipt(claim: str, quote: str, kind: str | None, model: str,
                           num_ctx: int, timeout: int,
                           system: str = SUPPORT_JUDGE) -> dict:
    response = ollama_chat(
        model, system, _support_judge_prompt(claim, quote, kind), num_ctx, timeout
    )
    return _safe_support_receipt(response)


def _support_fixture_cases() -> list[tuple[str, bool]]:
    """Flatten the support fixture registry in its stable measured order."""
    return [
        (item, want)
        for items, _note, expected in SUPPORT_FIXTURES
        for item, want in zip(items, expected, strict=True)
    ]


def _support_fixture_prompt(item: str) -> tuple[str, str, str | None]:
    """Return claim, quote, and kind exactly as the fixture judge receives them."""
    claim, quote = item.split("|||", 1)
    kind, _, rest = claim.strip().partition(":")
    return (
        rest.strip() or claim.strip(),
        quote.strip(),
        kind.strip() if rest else None,
    )


def _score_support_fixture_receipts(model: str, num_ctx: int, timeout: int,
                                    system: str) -> dict:
    """Calibrate support with retained one-word receipts, not an asserted total."""
    receipts = []
    detail = []
    right = 0
    for index, (item, want) in enumerate(_support_fixture_cases(), 1):
        claim, quote, kind = _support_fixture_prompt(item)
        user = _support_judge_prompt(claim, quote, kind)
        receipt = _judge_support_receipt(
            claim, quote, kind, model, num_ctx, timeout, system,
        )
        got = receipt["supports"]
        right += got == want
        detail.append({"item": item, "got": got, "want": want})
        receipts.append({
            "fixture_id": f"support-fixture-{index:02d}",
            "judge_input_sha256": _sha256(user),
            "expected": want,
            **receipt,
        })
    total = len(receipts)
    return {
        "agreement": f"{right}/{total}",
        "ok": right == total,
        "detail": detail,
        "receipts": receipts,
    }


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
    validate_inference_options(model, num_ctx, timeout)
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


def validate_inference_options(model: object, num_ctx: object,
                               timeout: object) -> None:
    """Reject cheap invalid inference inputs before resolving or calling a model."""
    if not isinstance(model, str) or not model.strip():
        raise StructuredOutputError("model name must be a nonblank string")
    if isinstance(num_ctx, bool) or not isinstance(num_ctx, int) or num_ctx <= 0:
        raise StructuredOutputError("--num-ctx must be a positive integer")
    if isinstance(timeout, bool) or not isinstance(timeout, int) or timeout <= 0:
        raise StructuredOutputError("--timeout must be a positive integer")


def validate_chunking(target_words: object, overlap_words: object) -> None:
    """Reject chunking that cannot advance before any model work."""
    if (
        isinstance(target_words, bool)
        or not isinstance(target_words, int)
        or target_words <= 0
    ):
        raise StructuredOutputError("--chunk-words must be a positive integer")
    if (
        isinstance(overlap_words, bool)
        or not isinstance(overlap_words, int)
        or overlap_words < 0
    ):
        raise StructuredOutputError("--overlap-words must be a nonnegative integer")
    if overlap_words >= target_words:
        raise StructuredOutputError(
            "--overlap-words must be smaller than --chunk-words")


def summarize(transcript: Transcript, model: str, num_ctx: int, timeout: int) -> dict:
    validate_inference_options(model, num_ctx, timeout)
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


def _chunk_turn_windows(transcript: Transcript, target_words: int,
                        overlap_words: int) -> list[list[int]]:
    """Return overlapping windows as ordinals in the transformed transcript view."""
    validate_chunking(target_words, overlap_words)
    windows, current, words, i = [], [], 0, 0
    turns = transcript.turns
    while i < len(turns):
        current.append(i)
        words += len(turns[i].text.split())
        i += 1
        if words >= target_words and i < len(turns):
            windows.append(current)
            back, rewound = 0, 0
            while back < len(current) - 1 and rewound < overlap_words:
                back += 1
                rewound += len(turns[current[-back]].text.split())
            i -= back
            current, words = [], 0
    if current:
        windows.append(current)
    return windows


def chunk_transcript(transcript: Transcript, target_words: int,
                     overlap_words: int) -> list[Transcript]:
    """Slice a transcript into overlapping windows, cutting on turn boundaries.

    The windows overlap because commitments are routinely made across a turn
    boundary — one person asks, another agrees — and a cut between the two
    leaves neither half usable in either slice. Overlap costs duplicate items,
    which the consolidation pass is explicitly told to merge; a missed
    commitment has no such remedy.
    """
    windows = _chunk_turn_windows(transcript, target_words, overlap_words)
    return [
        transcript._derived(source=f"{transcript.source} [slice {n}/{len(windows)}]",
                            attribution=transcript.attribution,
                            turns=[transcript.turns[i] for i in ordinals])
        for n, ordinals in enumerate(windows, 1)
    ]


_LABELS = r"DECISION|ACTION|PROPOSAL|QUESTION"
_LABEL_VALUES = ("DECISION", "ACTION", "PROPOSAL", "QUESTION")
FRAGMENT_CONTRACT = {
    "schema": "source-fragments/1",
    "word_definition": "non-whitespace Unicode runs",
    "target_words": 32,
    "overlap_words": 8,
    "merge_tail_under_words": 12,
    "cross_turns": False,
    "offsets": "Unicode code point indices [start,end)",
}
STRUCTURED_NOTE_CONTRACT = {
    "schema": "evidence-bound-note/1",
    "heading": "## Evidence-bound note",
    "with_claims": "Every claim below is linked to retained meeting words.",
    "without_claims": "No evidence-bound claims were produced.",
    "model_authored_narrative": False,
}
STRUCTURED_RUN_CONTRACT = "structured-run/1"
STRUCTURED_STAGE_RECEIPT = "structured-stage-receipt/2"
SOURCE_EVIDENCE_CONTRACT = "source-evidence/1"
MAX_CONSOLIDATION_GROUP = 3
REPLAYABLE_INPUT = "replayable from the retained transcript"
REPLAYABLE_CONSOLIDATION_INPUT = (
    "replayable from the retained transcript and safe extraction JSON"
)
REPLAYABLE_SAFE_RESPONSE = (
    "replayable validated JSON; contains only IDs, labels, and claims"
)
TRANSPORT_RESPONSE_LIMIT = (
    "Ollama transport envelope is not retained; only validated message JSON remains"
)


def transcript_view_sha256(transcript: Transcript) -> str:
    """Bind references to the exact transformed text and labels shown to the model."""
    return _sha256(transcript.render())


def _turn_fragment_spans(text: str) -> list[tuple[int, int]]:
    """Deterministic exact-character spans for one turn.

    Full fragments advance by 24 words (32 with 8 words of overlap). A final
    non-overlapping remainder shorter than 12 words extends the preceding fragment;
    this is why the largest possible fragment is 43 words.
    """
    words = list(re.finditer(r"\S+", text))
    if not words:
        return []
    target = FRAGMENT_CONTRACT["target_words"]
    step = target - FRAGMENT_CONTRACT["overlap_words"]
    tail_floor = FRAGMENT_CONTRACT["merge_tail_under_words"]
    word_spans: list[tuple[int, int]] = []
    start = 0
    while start + target <= len(words):
        word_spans.append((start, start + target))
        start += step
    if not word_spans:
        word_spans.append((0, len(words)))
    else:
        uncovered = len(words) - word_spans[-1][1]
        if uncovered:
            if uncovered < tail_floor:
                word_spans[-1] = (word_spans[-1][0], len(words))
            else:
                word_spans.append((word_spans[-1][0] + step, len(words)))
    return [(words[start].start(), words[end - 1].end()) for start, end in word_spans]


def build_fragment_map(transcript: Transcript) -> dict:
    """Build canonical references once, before transcript slicing.

    IDs contain the full transformed-view digest, turn ordinal, and exact character
    offsets. They therefore stay stable when slice boundaries move and become
    unresolvable when any visible transcript content changes.
    """
    view_digest = transcript_view_sha256(transcript)
    fragments = []
    for turn, row in enumerate(transcript.turns):
        for start, end in _turn_fragment_spans(row.text):
            text = row.text[start:end]
            fragments.append({
                "source_fragment_id": (
                    f"sf-{view_digest}-t{turn:06d}-c{start:06d}-{end:06d}"
                ),
                "turn": turn,
                "char_start": start,
                "char_end": end,
                "text": text,
                "text_sha256": _sha256(text),
            })
    digest_rows = [
        {key: fragment[key] for key in (
            "source_fragment_id", "turn", "char_start", "char_end", "text_sha256"
        )}
        for fragment in fragments
    ]
    contract_json = json.dumps(
        FRAGMENT_CONTRACT, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    map_json = json.dumps(
        digest_rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return {
        "transcript_view_sha256": view_digest,
        "fragment_contract": dict(FRAGMENT_CONTRACT),
        "fragment_contract_sha256": _sha256(contract_json),
        "fragment_map_sha256": _sha256(map_json),
        "fragments": fragments,
    }


def resolve_fragment(fragment: dict, transcript: Transcript, view_digest: str) -> str:
    """Resolve and verify one fragment against the current transformed transcript."""
    if transcript_view_sha256(transcript) != view_digest:
        raise StructuredOutputError("transcript view digest changed before evidence resolution")
    turn = fragment.get("turn")
    start = fragment.get("char_start")
    end = fragment.get("char_end")
    if not isinstance(turn, int) or not 0 <= turn < len(transcript.turns):
        raise StructuredOutputError("source fragment turn is outside the transcript view")
    text = transcript.turns[turn].text
    if (not isinstance(start, int) or not isinstance(end, int)
            or not 0 <= start < end <= len(text)):
        raise StructuredOutputError("source fragment has invalid character offsets")
    exact = text[start:end]
    if _sha256(exact) != fragment.get("text_sha256") or exact != fragment.get("text"):
        raise StructuredOutputError("source fragment no longer resolves byte-for-byte")
    return exact


def extraction_format(fragment_ids: list[str]) -> dict:
    """Constrain one extraction response to references visible in that slice."""
    item = {
        "type": "object",
        "additionalProperties": False,
        "required": ["source_fragment_ids", "label", "claim"],
        "properties": {
            "source_fragment_ids": {
                "type": "array",
                "items": {"type": "string", "enum": fragment_ids},
                "minItems": 1,
                "maxItems": 3,
                "uniqueItems": True,
            },
            "label": {"type": "string", "enum": list(_LABEL_VALUES)},
            "claim": {"type": "string", "minLength": 1},
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["items"],
        "properties": {"items": {"type": "array", "items": item}},
    }


def consolidation_format(evidence_item_ids: list[str]) -> dict:
    """Constrain consolidation grouping and coverage to validated extraction items."""
    item = {
        "type": "object",
        "additionalProperties": False,
        "required": ["source_item_ids", "label", "claim"],
        "properties": {
            "source_item_ids": {
                "type": "array",
                "items": {"type": "string", "enum": evidence_item_ids},
                "minItems": 1,
                "maxItems": MAX_CONSOLIDATION_GROUP,
                "uniqueItems": True,
            },
            "label": {"type": "string", "enum": list(_LABEL_VALUES)},
            "claim": {"type": "string", "minLength": 1},
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["items"],
        "properties": {"items": {"type": "array", "items": item}},
    }


class StructuredOutputError(ValueError):
    """The model response did not satisfy the inter-stage data contract."""


class _OrderedObject:
    """A decoded JSON object, distinct from a JSON array even when both are empty."""

    def __init__(self, pairs: list[tuple[str, object]]):
        self.pairs = pairs


def _strict_json(raw: str) -> object:
    """Decode JSON while retaining object order and refusing duplicate keys."""
    if not isinstance(raw, str) or not raw.strip():
        raise StructuredOutputError("empty structured response")

    def ordered_object(pairs: list[tuple[str, object]]) -> _OrderedObject:
        keys = [key for key, _ in pairs]
        if len(set(keys)) != len(keys):
            raise StructuredOutputError(f"duplicate JSON key(s): {keys!r}")
        return _OrderedObject(pairs)

    try:
        return json.loads(raw, object_pairs_hook=ordered_object)
    except json.JSONDecodeError as e:
        raise StructuredOutputError(f"malformed JSON: {e.msg}") from e


def _object(value: object, keys: tuple[str, ...], where: str) -> dict:
    """Validate one ordered object, including its raw generation order."""
    if not isinstance(value, _OrderedObject):
        raise StructuredOutputError(f"{where}: expected a JSON object")
    got = tuple(key for key, _ in value.pairs)
    if got != keys:
        expected = ", ".join(keys)
        actual = ", ".join(str(k) for k in got)
        raise StructuredOutputError(
            f"{where}: expected keys in order ({expected}), got ({actual})")
    return dict(value.pairs)


def _text(value: object, where: str) -> str:
    if not isinstance(value, str):
        raise StructuredOutputError(f"{where}: expected a string")
    if not value.strip():
        raise StructuredOutputError(f"{where}: blank fields are not evidence")
    if any(unicodedata.category(ch) in {"Cc", "Zl", "Zp"} for ch in value):
        raise StructuredOutputError(f"{where}: control or line-break characters are forbidden")
    return value.strip()


def _extract_item(value: object, where: str) -> dict:
    keys = ("source_fragment_ids", "label", "claim")
    item = _object(value, keys, where)
    for key in ("label", "claim"):
        item[key] = _text(item[key], f"{where}.{key}")
    fragment_ids = item["source_fragment_ids"]
    if not isinstance(fragment_ids, list) or not 1 <= len(fragment_ids) <= 3:
        raise StructuredOutputError(
            f"{where}.source_fragment_ids: expected an array of one to three IDs")
    if any(not isinstance(fragment_id, str) or not fragment_id.strip()
           for fragment_id in fragment_ids):
        raise StructuredOutputError(
            f"{where}.source_fragment_ids: expected nonblank strings")
    item["source_fragment_ids"] = [fragment_id.strip() for fragment_id in fragment_ids]
    if len(set(item["source_fragment_ids"])) != len(item["source_fragment_ids"]):
        raise StructuredOutputError(f"{where}.source_fragment_ids: duplicate reference")
    if item["label"] not in _LABEL_VALUES:
        raise StructuredOutputError(f"{where}.label: invalid label {item['label']!r}")
    return item


def _consolidated_item(value: object, where: str) -> dict:
    keys = ("source_item_ids", "label", "claim")
    item = _object(value, keys, where)
    for key in ("label", "claim"):
        item[key] = _text(item[key], f"{where}.{key}")
    if item["label"] not in _LABEL_VALUES:
        raise StructuredOutputError(f"{where}.label: invalid label {item['label']!r}")
    sources = item["source_item_ids"]
    if (not isinstance(sources, list)
            or not 1 <= len(sources) <= MAX_CONSOLIDATION_GROUP):
        raise StructuredOutputError(
            f"{where}.source_item_ids: expected one to "
            f"{MAX_CONSOLIDATION_GROUP} IDs")
    if any(not isinstance(source_id, str) or not source_id.strip() for source_id in sources):
        raise StructuredOutputError(
            f"{where}.source_item_ids: expected nonblank strings")
    item["source_item_ids"] = [source_id.strip() for source_id in sources]
    if len(set(item["source_item_ids"])) != len(item["source_item_ids"]):
        raise StructuredOutputError(f"{where}.source_item_ids: duplicate coverage")
    return item


def decode_records(raw: str, stage: str, *,
                   allowed_fragment_ids: list[str] | None = None,
                   input_items: list[dict] | None = None) -> dict:
    """Validate a schema-constrained response instead of trusting its JSON shape.

    The explicit key-order assertion is intentional. JSON objects are semantically
    unordered, but generation is not: the evidence reference must be written before
    the claim. Accepting a parsed dict would turn a claim-first response into a false
    success.
    """
    root = _strict_json(raw)
    if stage == "extract":
        doc = _object(root, ("items",), "extraction")
        if not isinstance(doc["items"], list):
            raise StructuredOutputError("extraction.items: expected an array")
        if allowed_fragment_ids is None:
            raise StructuredOutputError(
                "extraction: visible source fragment IDs are required")
        allowed = set(allowed_fragment_ids)
        items = [
            _extract_item(item, f"extraction.items[{i}]")
            for i, item in enumerate(doc["items"])
        ]
        selected = [
            fragment_id
            for item in items
            for fragment_id in item["source_fragment_ids"]
        ]
        unknown = sorted(set(selected) - allowed)
        if unknown:
            raise StructuredOutputError(
                f"extraction selected source fragment(s) outside this slice: {unknown!r}")
        positions = {fragment_id: index
                     for index, fragment_id in enumerate(allowed_fragment_ids)}
        for item in items:
            order = [positions[fragment_id] for fragment_id in item["source_fragment_ids"]]
            if order != sorted(order):
                raise StructuredOutputError(
                    "extraction source fragments are not in canonical transcript order")
        return {"items": items}
    if stage != "consolidate":
        raise ValueError(f"unknown structured stage {stage!r}")
    doc = _object(root, ("items",), "consolidation")
    if not isinstance(doc["items"], list):
        raise StructuredOutputError("consolidation.items: expected an array")
    items = [
        _consolidated_item(item, f"consolidation.items[{i}]")
        for i, item in enumerate(doc["items"])
    ]
    if input_items is None:
        raise StructuredOutputError("consolidation: validated input records are required")
    inputs = {item["evidence_item_id"]: item for item in input_items}
    if len(inputs) != len(input_items):
        raise StructuredOutputError("consolidation input contains duplicate evidence item IDs")
    covered: list[str] = []
    for item in items:
        sources = []
        for source_id in item["source_item_ids"]:
            if source_id not in inputs:
                raise StructuredOutputError(
                    f"consolidation source item ID does not exist: {source_id!r}")
            sources.append(inputs[source_id])
            covered.append(source_id)
        if any(source["label"] != item["label"] for source in sources):
            raise StructuredOutputError(
                "consolidation merged source item IDs across incompatible labels")
        if any(_sha256(source["claim"]) != source.get("claim_sha256")
               for source in sources):
            raise StructuredOutputError(
                "consolidation input claim disagrees with its attached digest")
        if (len(sources) > 1
                and len({source["claim_sha256"] for source in sources}) != 1):
            raise StructuredOutputError(
                "consolidation may merge only byte-identical extraction claims")
        ordered_refs = []
        seen_refs = set()
        for source in sources:
            for evidence_ref in source["evidence_refs"]:
                fragment_id = evidence_ref["source_fragment_id"]
                if fragment_id not in seen_refs:
                    seen_refs.add(fragment_id)
                    ordered_refs.append(evidence_ref)
        ordered_refs.sort(key=lambda ref: (
            ref["turn"], ref["char_start"], ref["char_end"],
            ref["source_fragment_id"],
        ))
        primary = ordered_refs[0]
        item.update({
            "quote": primary["quote"],
            "source_fragment_id": primary["source_fragment_id"],
            "turn": primary["turn"],
            "char_start": primary["char_start"],
            "char_end": primary["char_end"],
            "text_sha256": primary["text_sha256"],
            "evidence_refs": ordered_refs,
            "claim_sha256": _sha256(item["claim"]),
            "source_claim_sha256s": [
                source["claim_sha256"] for source in sources
            ],
        })
    duplicates = [source_id for source_id, count in Counter(covered).items() if count != 1]
    if duplicates:
        raise StructuredOutputError(
            f"consolidation covered source item IDs more than once: {duplicates!r}")
    missing = sorted(set(inputs) - set(covered))
    if missing:
        raise StructuredOutputError(
            f"consolidation discarded source item IDs: {missing!r}")
    return {"items": items}


def attach_evidence_items(items: list[dict], slice_ordinal: int,
                          fragment_lookup: dict[str, dict],
                          transcript: Transcript, view_digest: str) -> list[dict]:
    """Attach local record IDs and exact source text after reference validation."""
    attached = []
    for index, item in enumerate(items, 1):
        evidence_refs = []
        for fragment_id in item["source_fragment_ids"]:
            try:
                fragment = fragment_lookup[fragment_id]
            except KeyError as e:
                raise StructuredOutputError(
                    f"source fragment cannot be resolved: {fragment_id!r}") from e
            evidence_refs.append({
                "source_fragment_id": fragment_id,
                "turn": fragment["turn"],
                "char_start": fragment["char_start"],
                "char_end": fragment["char_end"],
                "text_sha256": fragment["text_sha256"],
                "quote": resolve_fragment(fragment, transcript, view_digest),
            })
        primary = evidence_refs[0]
        attached.append({
            **item,
            "evidence_item_id": f"slice-{slice_ordinal:04d}-item-{index:04d}",
            "slice_ordinal": slice_ordinal,
            "claim_sha256": _sha256(item["claim"]),
            "quote": primary["quote"],
            "turn": primary["turn"],
            "char_start": primary["char_start"],
            "char_end": primary["char_end"],
            "text_sha256": primary["text_sha256"],
            "evidence_refs": evidence_refs,
        })
    return attached


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _json_sha256(value: object) -> str:
    return _sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ))


def _valid_sha256(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _response_provenance(stage: str, source: str, ordinal: int, response: dict,
                         schema: dict, model_identity: dict, num_ctx: int, system: str,
                         user: str, input_records: str | None = None,
                         input_contract: object | None = None,
                         input_prompt_template: str | None = None,
                         reference_context: dict | None = None,
                         response_cardinality: dict | None = None) -> dict:
    """Retain the validated safe JSON reply, never the transport envelope."""
    raw = response.get("message", {}).get("content", "")
    result = {
        "schema_contract": STRUCTURED_STAGE_RECEIPT,
        "stage": stage,
        "source": source,
        "ordinal": ordinal,
        "model": model_identity["requested"],
        "resolved_model": model_identity["name"],
        "model_digest": model_identity["digest"],
        "options": {"num_ctx": num_ctx, "temperature": 0.0},
        "schema": schema,
        "schema_sha256": _json_sha256(schema),
        "system_prompt_sha256": _sha256(system),
        "input_prompt_sha256": _sha256(user),
        "input_prompt_validation": (
            REPLAYABLE_INPUT
            if stage == "extract" else REPLAYABLE_CONSOLIDATION_INPUT
        ),
        "validated_response_json": raw,
        "validated_response_sha256": _sha256(raw),
        "response_validation": REPLAYABLE_SAFE_RESPONSE,
        "transport_response_retained": False,
        "transport_response_limit": TRANSPORT_RESPONSE_LIMIT,
    }
    if input_records is not None:
        # Safe extraction JSON plus the retained transcript reconstruct this input
        # without persisting a second source-text copy.
        result["input_records_sha256"] = _sha256(input_records)
        result["input_records_validation"] = REPLAYABLE_CONSOLIDATION_INPUT
    if input_contract is not None:
        result["input_contract_sha256"] = _json_sha256(input_contract)
    if input_prompt_template is not None:
        result["input_prompt_template_sha256"] = _sha256(input_prompt_template)
    if reference_context is not None:
        result["reference_context"] = reference_context
    if response_cardinality is not None:
        result["response_cardinality"] = response_cardinality
    return result


def render_structured_note(items: list[dict]) -> str:
    """Render only evidence-bound claims under a deterministic local wrapper."""
    titles = {
        "DECISION": "Decisions",
        "ACTION": "Action items",
        "PROPOSAL": "Proposed",
        "QUESTION": "Open questions",
    }
    lines = [
        STRUCTURED_NOTE_CONTRACT["heading"],
        (
            STRUCTURED_NOTE_CONTRACT["with_claims"]
            if items else
            STRUCTURED_NOTE_CONTRACT["without_claims"]
        ),
    ]
    for label in _LABEL_VALUES:
        group = [item for item in items if item["label"] == label]
        if not group:
            continue
        lines.extend(("", f"## {titles[label]}"))
        for item in group:
            lines.extend((f"- {item['claim']}", f"  > {item['quote']}"))
    return "\n".join(lines)


def validate_structured_render(note: str, items: list[dict]) -> dict:
    """Prove rendering neither injected nor discarded a typed consolidated record."""
    if note != render_structured_note(items):
        raise StructuredOutputError(
            "structured note contains text outside the deterministic local rendering")
    parsed = _parse_claims(note)
    expected = [
        item
        for label in _LABEL_VALUES
        for item in items
        if item["label"] == label
    ]
    if len(parsed) != len(expected):
        raise StructuredOutputError(
            f"rendered {len(parsed)} claims from {len(expected)} consolidated records")
    for index, (actual, source) in enumerate(zip(parsed, expected, strict=True)):
        if (actual["claim"], actual["quote"], actual["type"]) != (
                source["claim"], source["quote"], source["label"].lower()):
            raise StructuredOutputError(
                f"rendered claim {index} does not match its consolidated record")
    return {"records": len(items), "rendered_claims": len(parsed), "ok": True}


def validate_evidence_contract(evidence: dict, transcript: Transcript) -> list[dict]:
    """Resolve the durable ID/coverage graph against the retained transcript.

    This is the authority for Repair 4 artifacts. It never searches Markdown for a
    plausible match: every reference must resolve at its declared exact character
    span in the exact transformed transcript view.
    """
    if (not isinstance(evidence, dict)
            or evidence.get("schema") != SOURCE_EVIDENCE_CONTRACT):
        raise StructuredOutputError("missing or unknown source evidence contract")
    fragment_map = build_fragment_map(transcript)
    for key in (
        "transcript_view_sha256",
        "fragment_contract_sha256",
        "fragment_map_sha256",
    ):
        if evidence.get(key) != fragment_map[key]:
            raise StructuredOutputError(f"source evidence {key} does not match transcript")
    if evidence.get("fragment_contract") != fragment_map["fragment_contract"]:
        raise StructuredOutputError("source evidence fragment contract is not current")

    fragment_lookup = {
        fragment["source_fragment_id"]: fragment
        for fragment in fragment_map["fragments"]
    }
    fragment_order = {
        fragment["source_fragment_id"]: index
        for index, fragment in enumerate(fragment_map["fragments"])
    }
    extraction_rows = evidence.get("extraction_items")
    consolidation_rows = evidence.get("consolidated_items")
    if not isinstance(extraction_rows, list) or not isinstance(consolidation_rows, list):
        raise StructuredOutputError("source evidence record lists are required")

    inputs: dict[str, dict] = {}
    for index, row in enumerate(extraction_rows):
        if not isinstance(row, dict) or set(row) != {
                "evidence_item_id", "slice_ordinal", "source_fragment_ids",
                "label", "claim_sha256"}:
            raise StructuredOutputError(
                f"source evidence extraction item {index} has the wrong shape")
        evidence_item_id = row["evidence_item_id"]
        slice_ordinal = row["slice_ordinal"]
        fragment_ids = row["source_fragment_ids"]
        label = row["label"]
        if (not isinstance(evidence_item_id, str) or not evidence_item_id
                or evidence_item_id in inputs):
            raise StructuredOutputError(
                "source evidence extraction item IDs must be unique nonblank strings")
        item_id_match = re.fullmatch(
            r"slice-(\d{4})-item-(\d{4})", evidence_item_id
        )
        if (not isinstance(slice_ordinal, int) or slice_ordinal < 1
                or item_id_match is None
                or int(item_id_match.group(1)) != slice_ordinal):
            raise StructuredOutputError(
                "source evidence extraction item has no valid slice identity")
        if (not isinstance(fragment_ids, list) or not 1 <= len(fragment_ids) <= 3
                or any(not isinstance(fragment_id, str) or not fragment_id
                       for fragment_id in fragment_ids)
                or len(set(fragment_ids)) != len(fragment_ids)):
            raise StructuredOutputError(
                "source evidence extraction references must contain one to three unique IDs")
        if label not in _LABEL_VALUES:
            raise StructuredOutputError("source evidence extraction label is invalid")
        if not _valid_sha256(row["claim_sha256"]):
            raise StructuredOutputError(
                "source evidence extraction claim digest is invalid")
        try:
            positions = [fragment_order[fragment_id] for fragment_id in fragment_ids]
        except (KeyError, TypeError) as e:
            raise StructuredOutputError(
                "source evidence extraction reference is unknown") from e
        if positions != sorted(positions):
            raise StructuredOutputError(
                "source evidence extraction references are not in transcript order")
        inputs[evidence_item_id] = row

    covered: list[str] = []
    resolved = []
    for index, row in enumerate(consolidation_rows):
        if not isinstance(row, dict) or set(row) != {
                "source_item_ids", "source_claim_sha256s",
                "source_fragment_ids", "label", "claim_sha256"}:
            raise StructuredOutputError(
                f"source evidence consolidated item {index} has the wrong shape")
        source_ids = row["source_item_ids"]
        source_claim_sha256s = row["source_claim_sha256s"]
        declared_fragments = row["source_fragment_ids"]
        label = row["label"]
        if (not isinstance(source_ids, list)
                or not 1 <= len(source_ids) <= MAX_CONSOLIDATION_GROUP
                or any(not isinstance(source_id, str) or not source_id
                       for source_id in source_ids)
                or len(set(source_ids)) != len(source_ids)):
            raise StructuredOutputError(
                "source evidence consolidation coverage exceeds its bounded group")
        if (not isinstance(source_claim_sha256s, list)
                or len(source_claim_sha256s) != len(source_ids)
                or any(not _valid_sha256(digest)
                       for digest in source_claim_sha256s)):
            raise StructuredOutputError(
                "source evidence consolidation member claim digests are invalid")
        if not _valid_sha256(row["claim_sha256"]):
            raise StructuredOutputError(
                "source evidence consolidated claim digest is invalid")
        if (not isinstance(declared_fragments, list)
                or any(not isinstance(fragment_id, str) or not fragment_id
                       for fragment_id in declared_fragments)
                or len(set(declared_fragments)) != len(declared_fragments)):
            raise StructuredOutputError(
                "source evidence consolidated fragments must be unique IDs")
        try:
            sources = [inputs[source_id] for source_id in source_ids]
        except (KeyError, TypeError) as e:
            raise StructuredOutputError(
                "source evidence consolidation covers an unknown item") from e
        if label not in _LABEL_VALUES or any(source["label"] != label for source in sources):
            raise StructuredOutputError(
                "source evidence consolidation crosses incompatible labels")
        expected_source_claims = [
            source["claim_sha256"] for source in sources
        ]
        if source_claim_sha256s != expected_source_claims:
            raise StructuredOutputError(
                "source evidence consolidation member claim digests disagree")
        if len(sources) > 1 and len(set(source_claim_sha256s)) != 1:
            raise StructuredOutputError(
                "source evidence merged distinct extraction claims")
        covered.extend(source_ids)
        union_ids = sorted(
            {
                fragment_id
                for source in sources
                for fragment_id in source["source_fragment_ids"]
            },
            key=fragment_order.__getitem__,
        )
        if declared_fragments != union_ids:
            raise StructuredOutputError(
                "source evidence consolidated fragments are not the canonical covered union")
        refs = []
        for fragment_id in union_ids:
            fragment = fragment_lookup[fragment_id]
            refs.append({
                "source_fragment_id": fragment_id,
                "turn": fragment["turn"],
                "char_start": fragment["char_start"],
                "char_end": fragment["char_end"],
                "text_sha256": fragment["text_sha256"],
                "quote": resolve_fragment(
                    fragment, transcript, fragment_map["transcript_view_sha256"]
                ),
            })
        resolved.append({
            "source_item_ids": source_ids,
            "source_claim_sha256s": source_claim_sha256s,
            "source_fragment_ids": union_ids,
            "label": label,
            "claim_sha256": row["claim_sha256"],
            "evidence_refs": refs,
        })

    repeated = sorted(
        source_id for source_id, count in Counter(covered).items() if count != 1
    )
    if repeated:
        raise StructuredOutputError(
            f"source evidence item coverage is repeated: {repeated!r}")
    missing = sorted(set(inputs) - set(covered))
    if missing:
        raise StructuredOutputError(
            f"source evidence item coverage is incomplete: {missing!r}")
    return resolved


def runtime_uses_source_evidence(result: dict) -> bool:
    """Whether a live result declares any part of the Repair 4 contract."""
    if any(key in result for key in (
        "claim_evidence_contract", "evidence_contract", "consolidated_records",
        "structured_provenance", "structured_contract",
    )):
        return True
    note = result.get("note")
    if (isinstance(note, str)
            and note.startswith(STRUCTURED_NOTE_CONTRACT["heading"] + "\n")):
        return True
    return (
        isinstance(result.get("model_identity"), dict)
        and "slices" in result
    )


def artifact_uses_source_evidence(doc: dict) -> bool:
    """Detect Repair 4 even when its evidence graph was emptied or removed."""
    if doc.get("schema") == STRUCTURED_NOTE_SCHEMA:
        return True
    if "claim_evidence_contract" in doc or "evidence" in doc:
        return True
    provenance = doc.get("provenance")
    if isinstance(provenance, dict) and any(
            provenance.get(key) is not None
            for key in ("source_evidence", "structured_stages", "structured_contract")):
        return True
    checks = doc.get("checks")
    citations = checks.get("citations") if isinstance(checks, dict) else None
    if isinstance(citations, dict) and "authority" in citations:
        return True
    # Repair 4 is the first two-pass path that resolves an immutable model identity.
    # This residual signature keeps a damaged artifact on the strict path even if
    # every explicit graph marker was removed together.
    if (isinstance(provenance, dict)
            and provenance.get("passes") == 2
            and isinstance(provenance.get("model_identity"), dict)):
        return True
    note = doc.get("note")
    if (isinstance(note, str)
            and note.startswith(STRUCTURED_NOTE_CONTRACT["heading"] + "\n")):
        return True
    claims = doc.get("claims")
    return isinstance(claims, list) and any(
        isinstance(claim, dict)
        and any(key in claim for key in (
            "source_item_ids", "source_claim_sha256s", "claim_sha256",
            "evidence_refs",
        ))
        for claim in claims
    )


def structured_citations(result: dict, transcript: Transcript) -> dict:
    """Build citation findings from validated fragment references, not Markdown search."""
    if result.get("claim_evidence_contract") != SOURCE_EVIDENCE_CONTRACT:
        raise StructuredOutputError(
            "Repair 4 runtime result has no explicit evidence discriminator")
    if "evidence_contract" not in result:
        raise StructuredOutputError(
            "Repair 4 runtime result is missing its source evidence graph")
    resolved = validate_evidence_contract(result["evidence_contract"], transcript)
    replay = validate_structured_stage_receipts(
        result.get("structured_provenance"),
        result.get("structured_contract"),
        result["evidence_contract"],
        transcript,
        result.get("model"),
        result.get("model_identity"),
    )
    consolidated = result["consolidated_records"]["items"]
    if consolidated != replay["consolidated_items"]:
        raise StructuredOutputError(
            "runtime consolidated records disagree with retained safe response")
    if result["note"] != render_structured_note(consolidated):
        raise StructuredOutputError(
            "runtime structured note contains text outside evidence-bound records")
    if len(resolved) != len(consolidated):
        raise StructuredOutputError(
            "resolved evidence count does not match consolidated records")
    parsed = _parse_claims(result["note"])
    expected = [
        (item, evidence)
        for label in _LABEL_VALUES
        for item, evidence in zip(consolidated, resolved, strict=True)
        if item["label"] == label
    ]
    if len(parsed) != len(expected):
        raise StructuredOutputError(
            "rendered note count does not match structured evidence records")

    cited = []
    for rendered, (item, evidence) in zip(parsed, expected, strict=True):
        if (item["source_item_ids"] != evidence["source_item_ids"]
                or item["source_claim_sha256s"]
                != evidence["source_claim_sha256s"]
                or item["label"] != evidence["label"]
                or item["evidence_refs"] != evidence["evidence_refs"]
                or _sha256(item["claim"]) != evidence["claim_sha256"]):
            raise StructuredOutputError(
                "runtime consolidated claim or evidence disagrees with durable coverage")
        primary = evidence["evidence_refs"][0]
        if (rendered["claim"], rendered["quote"], rendered["type"]) != (
                item["claim"], primary["quote"], item["label"].lower()):
            raise StructuredOutputError(
                "rendered Markdown disagrees with locally resolved structured evidence")
        cited.append({
            "claim": item["claim"],
            "quote": primary["quote"],
            "at": rendered["at"],
            "type": item["label"].lower(),
            "turn": primary["turn"],
            "start": transcript.turns[primary["turn"]].start,
            "source_item_ids": evidence["source_item_ids"],
            "source_claim_sha256s": evidence["source_claim_sha256s"],
            "claim_sha256": evidence["claim_sha256"],
            "evidence_refs": [
                {key: ref[key] for key in (
                    "source_fragment_id", "turn", "char_start", "char_end",
                    "text_sha256",
                )}
                for ref in evidence["evidence_refs"]
            ],
        })
    repeats = len(cited) - len({" ".join(_seq(row["claim"])) for row in cited})
    return {
        "applies": bool(transcript.turns),
        "ok": True,
        "items": len(cited),
        "cited": cited,
        "fabricated": [],
        "unverifiable": [],
        "uncited": [],
        "template_echo": sum(1 for item in parsed if item["wrapped"]),
        "layout": parsed[0]["layout"] if parsed else "none",
        "separator": parsed[0]["separator"] if parsed else None,
        "repeats": repeats,
        "reversed_locatable": 0,
        "authority": "source-evidence/1",
    }


def structured_artifact_citations(doc: dict, transcript: Transcript) -> dict:
    """Replay safe stage JSON and re-derive Repair 4 claims and references."""
    if doc.get("schema") != STRUCTURED_NOTE_SCHEMA:
        raise StructuredOutputError(
            f"Repair 4 artifact requires schema {STRUCTURED_NOTE_SCHEMA}")
    if doc.get("claim_evidence_contract") != SOURCE_EVIDENCE_CONTRACT:
        raise StructuredOutputError(
            "Repair 4 artifact has no current evidence discriminator")
    if "evidence" not in doc:
        raise StructuredOutputError(
            "Repair 4 artifact is missing its source evidence graph")
    evidence = doc["evidence"]
    if not isinstance(evidence, dict):
        raise StructuredOutputError(
            "Repair 4 artifact source evidence graph is not an object")
    resolved = validate_evidence_contract(evidence, transcript)
    expected_provenance = {
        key: evidence[key]
        for key in (
            "schema", "transcript_view_sha256",
            "fragment_contract_sha256", "fragment_map_sha256",
        )
    }
    if doc.get("provenance", {}).get("source_evidence") != expected_provenance:
        raise StructuredOutputError(
            "artifact source evidence provenance disagrees with its coverage graph")
    provenance = doc.get("provenance", {})
    replay = validate_structured_stage_receipts(
        provenance.get("structured_stages"),
        provenance.get("structured_contract"),
        evidence,
        transcript,
        provenance.get("model"),
        provenance.get("model_identity"),
    )
    parsed = _parse_claims(doc["note"])
    expected = [
        (evidence, item)
        for label in _LABEL_VALUES
        for evidence, item in zip(
            resolved, replay["consolidated_items"], strict=True
        )
        if evidence["label"] == label
    ]
    if len(parsed) != len(expected):
        raise StructuredOutputError(
            "artifact Markdown count does not match durable evidence records")
    cited = []
    for rendered, (evidence, item) in zip(parsed, expected, strict=True):
        primary = evidence["evidence_refs"][0]
        if (rendered["quote"], rendered["type"], rendered["claim"],
                _sha256(rendered["claim"])) != (
                primary["quote"], evidence["label"].lower(),
                item["claim"], evidence["claim_sha256"]):
            raise StructuredOutputError(
                "artifact Markdown claim or quote disagrees with durable evidence")
        cited.append({
            "claim": rendered["claim"],
            "quote": primary["quote"],
            "at": rendered["at"],
            "type": evidence["label"].lower(),
            "turn": primary["turn"],
            "start": transcript.turns[primary["turn"]].start,
            "source_item_ids": evidence["source_item_ids"],
            "source_claim_sha256s": evidence["source_claim_sha256s"],
            "claim_sha256": evidence["claim_sha256"],
            "evidence_refs": [
                {key: ref[key] for key in (
                    "source_fragment_id", "turn", "char_start", "char_end",
                    "text_sha256",
                )}
                for ref in evidence["evidence_refs"]
            ],
        })
    rendered_items = [
        {
            "label": evidence["label"],
            "claim": item["claim"],
            "quote": evidence["evidence_refs"][0]["quote"],
        }
        for rendered, (evidence, item) in zip(parsed, expected, strict=True)
    ]
    if doc["note"] != render_structured_note(rendered_items):
        raise StructuredOutputError(
            "artifact note contains narrative outside evidence-bound records")
    # Stored claims are not trusted as the authority, but disagreement is corruption,
    # not permission to silently replace one evidence graph with another.
    stored = doc.get("claims")
    if not isinstance(stored, list) or len(stored) != len(cited):
        raise StructuredOutputError(
            "artifact claims do not match durable source evidence cardinality")
    for old, new in zip(stored, cited, strict=True):
        if {
            key: old.get(key)
            for key in (
                "status", "claim", "quote", "at", "type", "turn", "start",
                "source_item_ids", "source_claim_sha256s", "claim_sha256",
                "evidence_refs",
            )
        } != {
            "status": LOCATED,
            **{
                key: new[key]
                for key in (
                    "claim", "quote", "at", "type", "turn", "start",
                    "source_item_ids", "source_claim_sha256s", "claim_sha256",
                    "evidence_refs",
                )
            },
        }:
            raise StructuredOutputError(
                "artifact claim evidence metadata disagrees with durable coverage")
    repeats = len(cited) - len({" ".join(_seq(row["claim"])) for row in cited})
    return {
        "applies": bool(transcript.turns),
        "ok": True,
        "items": len(cited),
        "cited": cited,
        "fabricated": [],
        "unverifiable": [],
        "uncited": [],
        "template_echo": sum(1 for item in parsed if item["wrapped"]),
        "layout": parsed[0]["layout"] if parsed else "none",
        "separator": parsed[0]["separator"] if parsed else None,
        "repeats": repeats,
        "reversed_locatable": 0,
        "authority": "source-evidence/1",
    }


EXTRACT_STRUCTURED_RULES = EXTRACT_RULES + """

Return ONLY a JSON object matching the supplied schema. It has an `items` array.
Each item object MUST write its keys in this exact order: `source_fragment_ids`,
`label`, `claim`. `source_fragment_ids` comes first and contains one to three IDs
offered in this slice, in transcript order, with no duplicate. Use more than one only
when the claim genuinely depends on words from multiple turns or fragments. `label` is
one of the four allowed uppercase values. `claim` is your short reading of those
fragments' words. Do not copy source text into any field. Do not return markdown,
headings, comments, or any key not in the schema."""

CONSOLIDATE_STRUCTURED_RULES = CONSOLIDATE_RULES + """

Return ONLY a JSON object matching the supplied schema. Its only root key MUST be
`items`. Each item object MUST write its keys in this exact order:
`source_item_ids`, `label`, `claim`. Choose the complete group of input record IDs
before writing its label or claim. Cover every input item ID exactly once across the
output; never drop, repeat, invent, or merge IDs carrying different labels. A group
contains at most three IDs. Merge only claims whose input claim text is byte-for-byte
identical; otherwise preserve each as its own output item. You may not compose or repair
evidence. Local code resolves the ordered union of source fragments from the covered
records. Do not return a summary, narrative, markdown, headings, comments, or any key
not in the schema."""

CONSOLIDATION_USER_TEMPLATE = (
    "Validated extracted records from the meeting, in order:\n\n"
    "{records}\n\nConsolidate the records without adding narrative."
)


def _structured_systems(transcript: Transcript) -> tuple[str, str]:
    contract = CONTRACTS[transcript.attribution]
    return (
        EXTRACT_STRUCTURED_RULES + "\n\n" + contract,
        CONSOLIDATE_STRUCTURED_RULES + "\n\n" + contract,
    )


def _fragments_by_turn(fragment_map: dict) -> dict[int, list[dict]]:
    grouped: dict[int, list[dict]] = {}
    for fragment in fragment_map["fragments"]:
        grouped.setdefault(fragment["turn"], []).append(fragment)
    return grouped


def _extraction_request(transcript: Transcript, fragment_map: dict,
                        turn_ordinals: list[int]) -> tuple[list[dict], list[str], dict, str]:
    """Rebuild one extraction request from the retained transcript view."""
    grouped = _fragments_by_turn(fragment_map)
    visible_fragments = [
        fragment
        for turn in turn_ordinals
        for fragment in grouped.get(turn, [])
    ]
    visible_ids = [
        fragment["source_fragment_id"] for fragment in visible_fragments
    ]
    source_rows = []
    for fragment in visible_fragments:
        row = {
            "source_fragment_id": fragment["source_fragment_id"],
            "text": fragment["text"],
        }
        speaker = transcript.turns[fragment["turn"]].speaker
        if transcript.attribution != NONE and speaker:
            row["speaker"] = speaker
        source_rows.append(row)
    source_listing = json.dumps(
        source_rows, ensure_ascii=False, separators=(",", ":")
    )
    schema = extraction_format(visible_ids)
    user = (
        "Visible source fragments from one transcript slice. The `text` fields "
        "are exact and the array is in transcript order:\n\n"
        f"{source_listing}\n\nExtract the records by source fragment ID."
    )
    return visible_fragments, visible_ids, schema, user


def _claim_digest(row: dict) -> str:
    digest = row.get("claim_sha256")
    claim = row.get("claim")
    if _valid_sha256(digest):
        if isinstance(claim, str) and _sha256(claim) != digest:
            raise StructuredOutputError(
                "structured record claim disagrees with its digest")
        return digest
    if not isinstance(claim, str) or not claim:
        raise StructuredOutputError("structured record has no claim digest")
    return _sha256(claim)


def _consolidation_input_contract(rows: list[dict]) -> list[dict]:
    """Digest-only graph view alongside the separately retained safe claim JSON."""
    contract = []
    for row in rows:
        fragment_ids = row.get("source_fragment_ids")
        if fragment_ids is None:
            fragment_ids = [
                ref["source_fragment_id"] for ref in row["evidence_refs"]
            ]
        contract.append({
            "evidence_item_id": row["evidence_item_id"],
            "source_fragment_ids": list(fragment_ids),
            "label": row["label"],
            "claim_sha256": _claim_digest(row),
        })
    return contract


def _consolidation_listing(items: list[dict]) -> str:
    records = [
        {
            "evidence_item_id": item["evidence_item_id"],
            "source_fragments": [
                {
                    "source_fragment_id": ref["source_fragment_id"],
                    "text": ref["quote"],
                }
                for ref in item["evidence_refs"]
            ],
            "label": item["label"],
            "claim": item["claim"],
        }
        for item in items
    ]
    return json.dumps(records, ensure_ascii=False, separators=(",", ":"))


def _durable_extraction_rows(items: list[dict]) -> list[dict]:
    return [
        {
            "evidence_item_id": item["evidence_item_id"],
            "slice_ordinal": item["slice_ordinal"],
            "source_fragment_ids": item["source_fragment_ids"],
            "label": item["label"],
            "claim_sha256": _claim_digest(item),
        }
        for item in items
    ]


def _durable_consolidation_rows(items: list[dict]) -> list[dict]:
    return [
        {
            "source_item_ids": item["source_item_ids"],
            "source_claim_sha256s": item["source_claim_sha256s"],
            "source_fragment_ids": [
                ref["source_fragment_id"] for ref in item["evidence_refs"]
            ],
            "label": item["label"],
            "claim_sha256": _claim_digest(item),
        }
        for item in items
    ]


def _validate_structured_contract(contract: dict, evidence: dict) -> tuple[int, int]:
    """Re-derive counts and the explicit consolidation loss bound."""
    required = {
        "schema", "evidence_contract", "stage_receipt_contract",
        "target_words", "overlap_words", "num_ctx", "temperature",
        "model_identity_validation",
        "input_sources", "covered_sources", "output_records", "rendered_claims",
        "max_consolidation_group", "merged_groups", "max_observed_group",
        "merge_semantics", "render_contract", "render_contract_sha256",
    }
    if not isinstance(contract, dict) or set(contract) != required:
        raise StructuredOutputError("artifact structured run contract has the wrong shape")
    if (contract["schema"] != STRUCTURED_RUN_CONTRACT
            or contract["evidence_contract"] != SOURCE_EVIDENCE_CONTRACT
            or contract["stage_receipt_contract"] != STRUCTURED_STAGE_RECEIPT):
        raise StructuredOutputError("artifact structured run contract is not current")
    target = contract["target_words"]
    overlap = contract["overlap_words"]
    if (not isinstance(target, int) or not isinstance(overlap, int)
            or target <= 0 or not 0 <= overlap < target):
        raise StructuredOutputError("artifact structured chunking parameters are invalid")
    if (not isinstance(contract["num_ctx"], int) or contract["num_ctx"] <= 0
            or contract["temperature"] != 0.0):
        raise StructuredOutputError("artifact structured inference options are invalid")
    if contract["model_identity_validation"] != (
            "cross-checked receipt; historical tags response is not retained"):
        raise StructuredOutputError(
            "artifact structured model identity limitation is missing")
    extraction_rows = evidence["extraction_items"]
    consolidation_rows = evidence["consolidated_items"]
    groups = [len(row["source_item_ids"]) for row in consolidation_rows]
    expected = {
        "input_sources": len(extraction_rows),
        "covered_sources": sum(groups),
        "output_records": len(consolidation_rows),
        "rendered_claims": len(consolidation_rows),
        "max_consolidation_group": MAX_CONSOLIDATION_GROUP,
        "merged_groups": sum(size > 1 for size in groups),
        "max_observed_group": max(groups, default=0),
        "merge_semantics": (
            "only byte-identical source claims may merge; consolidated semantic "
            "fidelity is not mechanically verified"
        ),
    }
    if any(contract.get(key) != value for key, value in expected.items()):
        raise StructuredOutputError(
            "artifact structured counts or consolidation bound do not re-derive")
    render_contract_json = json.dumps(
        STRUCTURED_NOTE_CONTRACT, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"),
    )
    if (contract["render_contract"] != STRUCTURED_NOTE_CONTRACT
            or contract["render_contract_sha256"] != _sha256(render_contract_json)):
        raise StructuredOutputError(
            "artifact evidence-bound render contract is missing or changed")
    return target, overlap


def validate_structured_stage_receipts(stages: object, contract: dict, evidence: dict,
                                       transcript: Transcript, model: object,
                                       model_identity: object) -> dict:
    """Replay safe stage JSON and re-derive the complete structured graph.

    The retained JSON contains only IDs, labels, and claims. Source text remains in
    the transcript, while model API identity is still only an internally consistent
    receipt because the historical tags response is not retained.
    """
    target, overlap = _validate_structured_contract(contract, evidence)
    expected_options = {
        "num_ctx": contract["num_ctx"],
        "temperature": contract["temperature"],
    }
    if (not isinstance(model, str) or not model
            or not isinstance(model_identity, dict)
            or set(model_identity) != {"requested", "name", "digest"}
            or model_identity.get("requested") != model
            or not isinstance(model_identity.get("name"), str)
            or not model_identity["name"]
            or not _valid_sha256(model_identity.get("digest"))):
        raise StructuredOutputError(
            "structured run has no valid immutable summarization model identity")
    if not isinstance(stages, list):
        raise StructuredOutputError("structured stage receipts are missing")

    fragment_map = build_fragment_map(transcript)
    turn_windows = _chunk_turn_windows(transcript, target, overlap)
    extraction_rows = evidence["extraction_items"]
    consolidation_rows = evidence["consolidated_items"]
    if len(stages) != len(turn_windows) + 1:
        raise StructuredOutputError(
            "structured stage receipt count does not match the chunking contract")
    if any(row["slice_ordinal"] > len(turn_windows) for row in extraction_rows):
        raise StructuredOutputError(
            "source evidence extraction item belongs to no retained slice")
    extract_system, consolidate_system = _structured_systems(transcript)
    base_keys = {
        "schema_contract", "stage", "source", "ordinal",
        "model", "resolved_model", "model_digest", "options",
        "schema", "schema_sha256", "system_prompt_sha256",
        "input_prompt_sha256", "input_prompt_validation",
        "validated_response_json", "validated_response_sha256",
        "response_validation", "transport_response_retained",
        "transport_response_limit",
        "reference_context", "response_cardinality",
    }
    common_references = {
        "transcript_view_sha256": fragment_map["transcript_view_sha256"],
        "fragment_contract_sha256": fragment_map["fragment_contract_sha256"],
        "fragment_map_sha256": fragment_map["fragment_map_sha256"],
    }
    fragment_lookup = {
        fragment["source_fragment_id"]: fragment
        for fragment in fragment_map["fragments"]
    }
    replayed_extraction_items = []

    for ordinal, turn_ordinals in enumerate(turn_windows, 1):
        receipt = stages[ordinal - 1]
        if not isinstance(receipt, dict) or set(receipt) != base_keys:
            raise StructuredOutputError(
                f"structured extraction receipt {ordinal} has the wrong shape")
        visible, visible_ids, schema, user = _extraction_request(
            transcript, fragment_map, turn_ordinals
        )
        selected = [
            row for row in extraction_rows if row["slice_ordinal"] == ordinal
        ]
        safe_response = receipt["validated_response_json"]
        if not isinstance(safe_response, str):
            raise StructuredOutputError(
                f"structured extraction receipt {ordinal} has no retained JSON")
        replayed = decode_records(
            safe_response, "extract", allowed_fragment_ids=visible_ids
        )
        attached = attach_evidence_items(
            replayed["items"], ordinal, fragment_lookup, transcript,
            fragment_map["transcript_view_sha256"],
        )
        if _durable_extraction_rows(attached) != selected:
            raise StructuredOutputError(
                f"structured extraction receipt {ordinal} disagrees with evidence")
        replayed_extraction_items.extend(attached)
        expected_reference = {
            **common_references,
            "visible_fragment_ids_sha256": _json_sha256(visible_ids),
            "visible_fragments": len(visible),
            "selected_fragment_references": sum(
                len(row["source_fragment_ids"]) for row in attached
            ),
        }
        expected_cardinality = {
            "items": len(attached),
            "selected_fragment_references": expected_reference[
                "selected_fragment_references"
            ],
        }
        expected_source = (
            f"{transcript.source} [slice {ordinal}/{len(turn_windows)}]"
        )
        if (
            receipt["schema_contract"] != STRUCTURED_STAGE_RECEIPT
            or receipt["stage"] != "extract"
            or receipt["source"] != expected_source
            or receipt["ordinal"] != ordinal
            or receipt["model"] != model_identity["requested"]
            or receipt["resolved_model"] != model_identity["name"]
            or receipt["model_digest"] != model_identity["digest"]
            or receipt["options"] != expected_options
            or receipt["schema"] != schema
            or receipt["schema_sha256"] != _json_sha256(schema)
            or receipt["system_prompt_sha256"] != _sha256(extract_system)
            or receipt["input_prompt_sha256"] != _sha256(user)
            or receipt["input_prompt_validation"] != REPLAYABLE_INPUT
            or receipt["validated_response_sha256"] != _sha256(safe_response)
            or receipt["response_validation"] != REPLAYABLE_SAFE_RESPONSE
            or receipt["transport_response_retained"] is not False
            or receipt["transport_response_limit"] != TRANSPORT_RESPONSE_LIMIT
            or receipt["reference_context"] != expected_reference
            or receipt["response_cardinality"] != expected_cardinality
        ):
            raise StructuredOutputError(
                f"structured extraction receipt {ordinal} does not re-derive")

    receipt = stages[-1]
    consolidation_keys = base_keys | {
        "input_records_sha256", "input_records_validation",
        "input_contract_sha256", "input_prompt_template_sha256",
    }
    if not isinstance(receipt, dict) or set(receipt) != consolidation_keys:
        raise StructuredOutputError(
            "structured consolidation receipt has the wrong shape")
    if _durable_extraction_rows(replayed_extraction_items) != extraction_rows:
        raise StructuredOutputError(
            "structured extraction receipts do not reproduce the durable order")
    input_contract = _consolidation_input_contract(replayed_extraction_items)
    input_records = _consolidation_listing(replayed_extraction_items)
    input_prompt = CONSOLIDATION_USER_TEMPLATE.format(records=input_records)
    consolidation_schema = consolidation_format([
        row["evidence_item_id"] for row in extraction_rows
    ])
    consolidation_reference = {
        **common_references,
        "input_evidence_items": len(extraction_rows),
        "output_records": len(consolidation_rows),
    }
    consolidation_cardinality = {
        "items": len(consolidation_rows),
        "covered_source_items": sum(
            len(row["source_item_ids"]) for row in consolidation_rows
        ),
    }
    safe_response = receipt["validated_response_json"]
    if not isinstance(safe_response, str):
        raise StructuredOutputError(
            "structured consolidation receipt has no retained JSON")
    replayed_consolidation = decode_records(
        safe_response, "consolidate", input_items=replayed_extraction_items
    )
    if (_durable_consolidation_rows(replayed_consolidation["items"])
            != consolidation_rows):
        raise StructuredOutputError(
            "structured consolidation receipt disagrees with durable evidence")
    if (
        receipt["schema_contract"] != STRUCTURED_STAGE_RECEIPT
        or receipt["stage"] != "consolidate"
        or receipt["source"] != "consolidate"
        or receipt["ordinal"] != len(turn_windows) + 1
        or receipt["model"] != model_identity["requested"]
        or receipt["resolved_model"] != model_identity["name"]
        or receipt["model_digest"] != model_identity["digest"]
        or receipt["options"] != expected_options
        or receipt["schema"] != consolidation_schema
        or receipt["schema_sha256"] != _json_sha256(consolidation_schema)
        or receipt["system_prompt_sha256"] != _sha256(consolidate_system)
        or receipt["input_prompt_sha256"] != _sha256(input_prompt)
        or receipt["input_prompt_validation"] != REPLAYABLE_CONSOLIDATION_INPUT
        or receipt["input_prompt_template_sha256"]
        != _sha256(CONSOLIDATION_USER_TEMPLATE)
        or receipt["input_records_sha256"] != _sha256(input_records)
        or receipt["input_records_validation"] != REPLAYABLE_CONSOLIDATION_INPUT
        or receipt["input_contract_sha256"] != _json_sha256(input_contract)
        or receipt["validated_response_sha256"] != _sha256(safe_response)
        or receipt["response_validation"] != REPLAYABLE_SAFE_RESPONSE
        or receipt["transport_response_retained"] is not False
        or receipt["transport_response_limit"] != TRANSPORT_RESPONSE_LIMIT
        or receipt["reference_context"] != consolidation_reference
        or receipt["response_cardinality"] != consolidation_cardinality
    ):
        raise StructuredOutputError(
            "structured consolidation receipt does not re-derive")
    return {
        "stages": stages,
        "extraction_items": replayed_extraction_items,
        "consolidated_items": replayed_consolidation["items"],
    }

# The order the contract now asks for: spoken words, pipe, label, item. The quote
# group excludes pipes, so it cannot swallow a later field by backtracking.
_ITEM_QUOTE_FIRST = re.compile(
    rf"^\s*(?:[-*]\s*)?(?P<quote>[^|]*?\S)\s*\|\s*(?P<label>{_LABELS})\s*:\s*"
    r"(?P<text>\S.*?)\s*$", re.IGNORECASE)

# The order it used to ask for, still read. Not politeness towards an old format:
# a line matching neither pattern is dropped silently, and three separate defects in
# this file were failures landing somewhere nothing counted them. A model that
# ignores the inversion has to show up as a number, because "40 of 93 lines came
# back in the old order" is the finding that explains a flat result, and a line that
# quietly disappears looks identical to a slice that contained nothing.
_ITEM_CLAIM_FIRST = re.compile(
    rf"^\s*(?:[-*]\s*)?(?P<label>{_LABELS})\s*:\s*(?P<text>[^|]+?)"
    r"(?:\s*\|\s*(?P<quote>.+?))?\s*$", re.IGNORECASE)

# A line that carries a pipe or a label was trying to be an item, so failing to parse
# it is a defect. A line with neither is the preamble the contract forbids but models
# still write, and ignoring that is correct rather than lossy.
_ITEMISH = re.compile(rf"\||\b(?:{_LABELS})\s*:", re.IGNORECASE)


def parse_item(line: str) -> dict | None:
    """One extraction line, or None if it is not one.

    Quote-first is tried first because it is what the contract asks for. The two
    patterns are anchored at opposite ends, so an ordinary line matches at most one
    of them; only a line carrying two labels could match both, and the current
    contract is the tiebreak.
    """
    for order, pattern in (("quote-first", _ITEM_QUOTE_FIRST),
                           ("claim-first", _ITEM_CLAIM_FIRST)):
        if m := pattern.match(line):
            return {"label": m.group("label").upper(),
                    "text": m.group("text").strip(),
                    "quote": (m.group("quote") or "").strip(),
                    "order": order}
    return None


def check_extraction(lines: list[str], parsed: list[dict]) -> dict:
    """Whether every line that tried to be an item became one, and in which order.

    Separate from the note checks because it scores a different artifact — the
    intermediate list, which no reader ever sees and which is therefore the easiest
    place in the pipeline for content to go missing without anybody noticing.
    """
    dropped = [ln.strip() for ln in lines
               if ln.strip() and _ITEMISH.search(ln) and not parse_item(ln)]
    orders = Counter(p["order"] for p in parsed)
    return {
        "applies": True,
        "ok": not dropped,
        "dropped": dropped,
        "orders": dict(orders),
        "labels": dict(Counter(p["label"] for p in parsed)),
    }


def summarize_chunked(transcript: Transcript, model: str, num_ctx: int, timeout: int,
                      target_words: int, overlap_words: int,
                      model_identity: dict | None = None) -> dict:
    """Extract per slice, then consolidate — trading passes for recall.

    The single-pass summarizer is asked to compress a whole meeting in one step,
    and every measurement in EVAL.md says what it loses under that pressure is
    commitments. Here each slice is compressed gently and the merge is forbidden
    to select, so no step faces the ratio that causes the loss.

    This is not free. It makes one model call per slice plus one, and it
    introduces a second place for omission to happen — the merge. The durable
    graph keeps item identities, claim digests, and exact coverage so the two
    stages can be audited without writing a second transcript-derived sidecar.
    """
    validate_inference_options(model, num_ctx, timeout)
    validate_chunking(target_words, overlap_words)
    extract_system, consolidate_system = _structured_systems(transcript)
    turn_windows = _chunk_turn_windows(transcript, target_words, overlap_words)
    slices = [
        transcript._derived(
            source=f"{transcript.source} [slice {ordinal}/{len(turn_windows)}]",
            attribution=transcript.attribution,
            turns=[transcript.turns[index] for index in turn_ordinals],
        )
        for ordinal, turn_ordinals in enumerate(turn_windows, 1)
    ]
    fragment_map = build_fragment_map(transcript)
    fragment_lookup = {
        fragment["source_fragment_id"]: fragment
        for fragment in fragment_map["fragments"]
    }
    live_model_identity = model_identity is None
    identity = model_identity or resolve_ollama_model(model, min(timeout, 30))
    if identity.get("requested") != model:
        raise StructuredOutputError(
            "summarization model identity does not match the requested model")

    t0 = time.monotonic()
    calls, items, stage_provenance = [], [], []
    selected_fragment_count = 0
    for ordinal, (chunk, turn_ordinals) in enumerate(
            zip(slices, turn_windows, strict=True), 1):
        _visible_fragments, visible_ids, schema, user = _extraction_request(
            transcript, fragment_map, turn_ordinals
        )
        response = ollama_chat(model, extract_system, user, num_ctx, timeout,
                               schema)
        calls.append({"label": chunk.source, "prompt": extract_system + user,
                      "response": response})
        raw = response.get("message", {}).get("content", "")
        try:
            extracted = decode_records(
                raw, "extract", allowed_fragment_ids=visible_ids
            )
        except StructuredOutputError as e:
            raise SystemExit(f"{chunk.source}: structured extraction refused: {e}") from e
        try:
            attached = attach_evidence_items(
                extracted["items"], ordinal, fragment_lookup, transcript,
                fragment_map["transcript_view_sha256"],
            )
        except StructuredOutputError as e:
            raise SystemExit(f"{chunk.source}: extraction evidence refused: {e}") from e
        items.extend(attached)
        selected_fragment_count += sum(
            len(item["source_fragment_ids"]) for item in attached
        )
        stage_provenance.append(_response_provenance(
            "extract", chunk.source, ordinal, response, schema, identity, num_ctx,
            extract_system, user, reference_context={
                "transcript_view_sha256": fragment_map["transcript_view_sha256"],
                "fragment_contract_sha256": fragment_map["fragment_contract_sha256"],
                "fragment_map_sha256": fragment_map["fragment_map_sha256"],
                "visible_fragment_ids_sha256": _json_sha256(visible_ids),
                "visible_fragments": len(visible_ids),
                "selected_fragment_references": sum(
                    len(item["source_fragment_ids"]) for item in attached
                ),
            }, response_cardinality={
                "items": len(attached),
                "selected_fragment_references": sum(
                    len(item["source_fragment_ids"]) for item in attached
                ),
            }))

    # `json.dumps` is the only transport between the two model stages. Its shape has
    # no overloaded punctuation. Evidence text is locally resolved, not model-authored.
    listing = _consolidation_listing(items)
    user = CONSOLIDATION_USER_TEMPLATE.format(records=listing)
    consolidate_schema = consolidation_format(
        [item["evidence_item_id"] for item in items]
    )
    response = ollama_chat(model, consolidate_system, user, num_ctx, timeout,
                           consolidate_schema)
    calls.append({"label": "consolidate", "prompt": consolidate_system + user,
                  "response": response})
    elapsed = time.monotonic() - t0
    raw = response.get("message", {}).get("content", "")
    try:
        consolidated = decode_records(raw, "consolidate", input_items=items)
    except StructuredOutputError as e:
        raise SystemExit(f"consolidation: structured output refused: {e}") from e
    stage_provenance.append(_response_provenance(
        "consolidate", "consolidate", len(slices) + 1, response,
        consolidate_schema, identity, num_ctx, consolidate_system, user,
        input_records=listing,
        input_contract=_consolidation_input_contract(items),
        input_prompt_template=CONSOLIDATION_USER_TEMPLATE,
        reference_context={
            "transcript_view_sha256": fragment_map["transcript_view_sha256"],
            "fragment_contract_sha256": fragment_map["fragment_contract_sha256"],
            "fragment_map_sha256": fragment_map["fragment_map_sha256"],
            "input_evidence_items": len(items),
            "output_records": len(consolidated["items"]),
        }, response_cardinality={
            "items": len(consolidated["items"]),
            "covered_source_items": sum(
                len(item["source_item_ids"]) for item in consolidated["items"]
            ),
        }))
    if (live_model_identity
            and resolve_ollama_model(model, min(timeout, 30)) != identity):
        raise SystemExit(
            "summarization model identity changed during inference; no note written"
        )

    note = render_structured_note(consolidated["items"])
    try:
        rendered = validate_structured_render(note, consolidated["items"])
    except StructuredOutputError as e:
        raise SystemExit(f"structured rendering refused: {e}") from e
    evidence_contract = {
        "schema": SOURCE_EVIDENCE_CONTRACT,
        "transcript_view_sha256": fragment_map["transcript_view_sha256"],
        "fragment_contract": fragment_map["fragment_contract"],
        "fragment_contract_sha256": fragment_map["fragment_contract_sha256"],
        "fragment_map_sha256": fragment_map["fragment_map_sha256"],
        "extraction_items": _durable_extraction_rows(items),
        "consolidated_items": _durable_consolidation_rows(
            consolidated["items"]
        ),
    }
    render_contract_json = json.dumps(
        STRUCTURED_NOTE_CONTRACT, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )

    return {
        "claim_evidence_contract": SOURCE_EVIDENCE_CONTRACT,
        "note": note,
        "elapsed_s": elapsed,
        "model": model,
        "model_identity": identity,
        "rendered": transcript.render(),
        "system": extract_system + "\n" + consolidate_system,
        "calls": calls,
        "consolidated_records": consolidated,
        "evidence_contract": evidence_contract,
        "structured_render": rendered,
        "structured_provenance": stage_provenance,
        "structured_contract": {
            "schema": STRUCTURED_RUN_CONTRACT,
            "evidence_contract": SOURCE_EVIDENCE_CONTRACT,
            "stage_receipt_contract": STRUCTURED_STAGE_RECEIPT,
            "target_words": target_words,
            "overlap_words": overlap_words,
            "num_ctx": num_ctx,
            "temperature": 0.0,
            "model_identity_validation": (
                "cross-checked receipt; historical tags response is not retained"
            ),
            "input_sources": len(items),
            "covered_sources": sum(
                len(item["source_item_ids"]) for item in consolidated["items"]),
            "output_records": len(consolidated["items"]),
            "rendered_claims": rendered["rendered_claims"],
            "max_consolidation_group": MAX_CONSOLIDATION_GROUP,
            "merged_groups": sum(
                len(item["source_item_ids"]) > 1
                for item in consolidated["items"]
            ),
            "max_observed_group": max(
                (len(item["source_item_ids"]) for item in consolidated["items"]),
                default=0,
            ),
            "merge_semantics": (
                "only byte-identical source claims may merge; consolidated semantic "
                "fidelity is not mechanically verified"
            ),
            "render_contract": dict(STRUCTURED_NOTE_CONTRACT),
            "render_contract_sha256": _sha256(render_contract_json),
        },
        "extraction": {
            "applies": True,
            "ok": True,
            "dropped": [],
            "orders": {"source-reference-first": len(items)},
            "labels": dict(Counter(item["label"] for item in items)),
            "transport": "json-schema",
            "fragment_references": {
                "items": len(items),
                "selected": selected_fragment_count,
                "resolved": selected_fragment_count,
            },
        },
        "slices": len(slices),
        # Structured coverage is validated before rendering. A markdown dedupe here
        # would discard typed coverage after that proof and make it false.
        "duplicates_removed": None,
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
    # Refuse a malformed source-evidence graph before the first recall-model call.
    # A durable graph is a deterministic precondition, not something to discover
    # after calibration and one inference call per reference item have been spent.
    if runtime_uses_source_evidence(result):
        try:
            cites = structured_citations(result, transcript)
        except StructuredOutputError as e:
            raise SystemExit(f"structured evidence refused during report: {e}") from e
    else:
        cites = check_citations(note, transcript)
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
    if extraction := result.get("extraction"):
        # Which order the model actually wrote, printed every run rather than only
        # when it disagrees. The key-order validator, not the prompt, establishes it.
        counts = ", ".join(f"{n} {order}" for order, n in
                           sorted(extraction["orders"].items()))
        labels = ", ".join(f"{n} {lab.lower()}" for lab, n in
                           sorted(extraction["labels"].items()))
        print(f"  extraction    {counts or 'no items'} — {labels or 'none'}")
        if references := extraction.get("fragment_references"):
            print(f"                {references['resolved']}/"
                  f"{references['selected']} source fragment reference(s) "
                  "resolved at exact spans")
        for line in extraction["dropped"]:
            print(f"                DROPPED (looks like an item, parsed as none): {line}")
    if runtime_uses_source_evidence(result):
        structured_contract = result["structured_contract"]
        print(
            f"  consolidate   {structured_contract['merged_groups']} byte-identical "
            f"claim group(s); largest {structured_contract['max_observed_group']}/"
            f"{structured_contract['max_consolidation_group']}"
        )
        print(
            "                member IDs and claim digests retained; fidelity of each "
            "rewritten output claim is not mechanically proven"
        )
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
        elif cites["cited"] and cites.get("authority") == "source-evidence/1":
            refs = sum(len(row["evidence_refs"]) for row in cites["cited"])
            print(f"  citations     {refs} exact source fragment reference(s) resolved "
                  f"for {len(cites['cited'])} claim(s) — support is not implied")
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
        if cites["reversed_locatable"]:
            # Read this before believing the fabrication count above it. These items
            # have testable text on both sides and only the assumed claim side locates,
            # so the parser orientation may be wrong. The count is evidence to inspect,
            # not proof that every side should be swapped.
            print(f"  citations     {cites['reversed_locatable']} collapsed item(s) locate "
                  f"only when read backwards with both sides long enough to test — "
                  f"inspect the parser orientation before trusting fabrication counts")
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
        # Absent on the single-pass path, which has no intermediate list to lose
        # anything in. Recorded rather than omitted so a reader of the artifact can
        # tell "this path has no such stage" from "nobody looked".
        "extraction": result.get("extraction", {"applies": False, "ok": None}),
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
    # `.get` because artifacts written before the extraction check existed have no
    # such key, and `recheck` runs this formula over them. Defaulting to "does not
    # apply" says what is true of those files: the stage was not scored. Defaulting
    # to ok=True would have claimed it passed.
    extraction = checks.get("extraction", {"applies": False})
    return (
        ctx["ok"] is not False
        and (not attr["applies"] or attr["ok"])
        and checks["numbers"]["ok"]
        and checks["prompt_echo"]["ok"]
        and checks["citations"]["ok"]
        # A line the model wrote as an item and the parser did not read is content
        # dropped between two stages, where no reader and no other check can see it.
        and (not extraction["applies"] or extraction["ok"])
    )


LEGACY_NOTE_SCHEMA = "note/1"
STRUCTURED_NOTE_SCHEMA = "note/2"
NOTE_SCHEMAS = {LEGACY_NOTE_SCHEMA, STRUCTURED_NOTE_SCHEMA}
NOTE_RENDER_SCHEMA = "note-render/1"

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


def _artifact_transcript(artifact: Path, doc: dict) -> Transcript:
    """Load the retained transcript in the exact transformed view an artifact names."""
    t = load((artifact.parent / doc["transcript"]).resolve())
    transform = doc["transform"]
    if transform == "strip":
        return t.strip_attribution()
    if transform == "as-channel":
        return t.as_channel(None)
    if transform == "simulate-bleed":
        return t.simulate_bleed()
    if transform is not None:
        raise StructuredOutputError(f"unknown transcript transform {transform!r}")
    return t


def _support_key(record: dict) -> tuple:
    """Content identity for a support verdict, including declared evidence coverage."""
    fragment_ids = record.get("source_fragment_ids")
    if fragment_ids is None and record.get("evidence_refs"):
        fragment_ids = [
            ref["source_fragment_id"] for ref in record["evidence_refs"]
        ]
    if fragment_ids is not None:
        return (
            "source-evidence/1",
            record.get("claim"),
            record.get("type"),
            tuple(record.get("source_item_ids") or ()),
            tuple(fragment_ids),
        )
    return ("legacy-quote", record.get("claim"), record.get("quote"))


def _claim_evidence_text(claim: dict, transcript: Transcript) -> tuple[str, list[str]]:
    """Resolve the declared evidence set without joining it into a synthetic quote."""
    refs = claim.get("evidence_refs")
    if not refs:
        return claim["quote"], []
    fragment_map = build_fragment_map(transcript)
    lookup = {
        fragment["source_fragment_id"]: fragment
        for fragment in fragment_map["fragments"]
    }
    texts = []
    ids = []
    for ref in refs:
        fragment_id = ref["source_fragment_id"]
        try:
            fragment = lookup[fragment_id]
        except KeyError as e:
            raise StructuredOutputError(
                f"support evidence fragment is unknown: {fragment_id!r}") from e
        for key in ("turn", "char_start", "char_end", "text_sha256"):
            if ref.get(key) != fragment[key]:
                raise StructuredOutputError(
                    f"support evidence metadata disagrees for {fragment_id!r}")
        ids.append(fragment_id)
        texts.append(resolve_fragment(
            fragment, transcript, fragment_map["transcript_view_sha256"]
        ))
    if len(texts) == 1:
        return texts[0], ids
    displayed = "\n\n".join(
        f"[SOURCE FRAGMENT {index}]\n{text}"
        for index, text in enumerate(texts, 1)
    )
    return displayed, ids


def _validated_support_receipt(receipt: dict, where: str) -> bool | None:
    """Re-derive a verdict from its retained safe model response."""
    response = receipt.get("judge_response")
    digest = receipt.get("judge_response_sha256")
    asserted = receipt.get("supports")
    if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        raise StructuredOutputError(f"{where}: invalid judge response digest")
    if response is None:
        if asserted is not None:
            raise StructuredOutputError(
                f"{where}: an unretained response cannot carry a verdict")
        return None
    if not isinstance(response, str) or response.strip().upper() not in {"YES", "NO"}:
        raise StructuredOutputError(f"{where}: retained judge response is not YES or NO")
    if _sha256(response) != digest:
        raise StructuredOutputError(f"{where}: judge response digest does not match")
    derived = response.strip().upper() == "YES"
    if asserted is not derived:
        raise StructuredOutputError(
            f"{where}: asserted verdict disagrees with the judge response")
    return derived


def _validate_support_fixture_receipts(receipts: object, system: str,
                                       where: str) -> dict:
    """Recompute fixture agreement from exact prompt and response receipts."""
    cases = _support_fixture_cases()
    if not isinstance(receipts, list) or len(receipts) != len(cases):
        raise StructuredOutputError(f"{where}: fixture receipt count is wrong")
    right = 0
    for index, (receipt, (item, want)) in enumerate(
            zip(receipts, cases, strict=True), 1):
        if not isinstance(receipt, dict):
            raise StructuredOutputError(f"{where}[{index}]: receipt is not an object")
        claim, quote, kind = _support_fixture_prompt(item)
        expected_prompt = _support_judge_prompt(claim, quote, kind)
        if (receipt.get("fixture_id") != f"support-fixture-{index:02d}"
                or receipt.get("judge_input_sha256") != _sha256(expected_prompt)
                or receipt.get("expected") is not want):
            raise StructuredOutputError(
                f"{where}[{index}]: fixture identity disagrees with the registry")
        got = _validated_support_receipt(receipt, f"{where}[{index}]")
        right += got == want
    total = len(cases)
    return {
        "agreement": f"{right}/{total}",
        "ok": right == total,
        "system_sha256": _sha256(system),
    }


def validate_support_measurement(doc: dict, transcript: Transcript) -> dict | None:
    """Recompute the identity of every displayed Repair 4 support verdict.

    The model's answer cannot be reproduced from a mutable tag and a claim index.
    Repair 4 binds it to the resolved model digest, the calibrated judge contract,
    the exact prompt, and the complete declared evidence set. Legacy note artifacts
    keep their earlier support shape; this stricter contract applies only where the
    source-evidence graph makes exact reconstruction possible.
    """
    support = doc.get("support")
    if not artifact_uses_source_evidence(doc):
        return support
    if "evidence" not in doc:
        raise StructuredOutputError(
            "Repair 4 artifact is missing its source evidence graph")
    structured_artifact_citations(doc, transcript)
    if support is None:
        return None
    if not isinstance(support, dict) or support.get("schema") != "support-measurement/1":
        raise StructuredOutputError(
            "structured artifact support has no support-measurement/1 contract")
    judge = support.get("judge")
    identity = support.get("judge_identity")
    if (not isinstance(judge, str) or not judge
            or not isinstance(identity, dict)
            or identity.get("requested") != judge
            or not isinstance(identity.get("name"), str)
            or not identity["name"]
            or not isinstance(identity.get("digest"), str)
            or re.fullmatch(r"[0-9a-f]{64}", identity["digest"]) is None):
        raise StructuredOutputError(
            "structured artifact support has no valid immutable judge identity")
    fixture_sha256 = _sha256(json.dumps(
        SUPPORT_FIXTURES, ensure_ascii=False, separators=(",", ":")
    ))
    if support.get("judge_system_sha256") != _sha256(SUPPORT_JUDGE):
        raise StructuredOutputError(
            "structured artifact support judge contract differs from this harness")
    if support.get("control_system_sha256") != _sha256(SABOTAGED_SUPPORT_JUDGE):
        raise StructuredOutputError(
            "structured artifact support control contract differs from this harness")
    if support.get("fixture_set_sha256") != fixture_sha256:
        raise StructuredOutputError(
            "structured artifact support fixtures differ from this harness")
    options = support.get("options")
    if (not isinstance(options, dict)
            or set(options) != {"num_ctx", "temperature"}
            or not isinstance(options["num_ctx"], int)
            or options["num_ctx"] <= 0
            or options["temperature"] != 0.0):
        raise StructuredOutputError(
            "structured artifact support has invalid judge options")
    real_calibration = _validate_support_fixture_receipts(
        support.get("calibration_receipts"), SUPPORT_JUDGE,
        "support calibration",
    )
    control_calibration = _validate_support_fixture_receipts(
        support.get("control_receipts"), SABOTAGED_SUPPORT_JUDGE,
        "support control",
    )
    if (not real_calibration["ok"] or control_calibration["ok"]
            or support.get("calibration") != real_calibration["agreement"]
            or support.get("control") != control_calibration["agreement"]):
        raise StructuredOutputError(
            "structured artifact support calibration receipts do not authorize a score")
    verdicts = support.get("verdicts")
    if not isinstance(verdicts, list):
        raise StructuredOutputError(
            "structured artifact support verdicts are not an array")

    claims = doc.get("claims")
    if not isinstance(claims, list):
        raise StructuredOutputError("structured artifact claims are not an array")
    remaining = list(verdicts)
    for claim in claims:
        matches = [
            verdict for verdict in remaining
            if isinstance(verdict, dict) and _support_key(verdict) == _support_key(claim)
        ]
        if len(matches) != 1:
            raise StructuredOutputError(
                "structured artifact support does not cover each claim exactly once")
        verdict = matches[0]
        remaining.remove(verdict)
        _validated_support_receipt(
            verdict, f"support verdict for {claim.get('claim')!r}"
        )
        if (verdict.get("claim"), verdict.get("quote"), verdict.get("type")) != (
                claim["claim"], claim["quote"], claim.get("type")):
            raise StructuredOutputError(
                "structured artifact support verdict changed its claim identity")
        evidence_text, fragment_ids = _claim_evidence_text(claim, transcript)
        if (verdict.get("source_item_ids") != claim.get("source_item_ids")
                or verdict.get("source_fragment_ids") != fragment_ids
                or verdict.get("evidence_set_sha256") != _sha256(evidence_text)
                or verdict.get("judge_input_sha256") != _sha256(
                    _support_judge_prompt(
                        claim["claim"], evidence_text, claim.get("type")
                    )
                )):
            raise StructuredOutputError(
                "structured artifact support verdict disagrees with its exact evidence")
    if remaining:
        raise StructuredOutputError(
            "structured artifact support contains verdicts for unknown claims")
    return support


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
    validate_inference_options(model, num_ctx, timeout)
    prepared = []
    for path in artifacts:
        artifact_bytes = path.read_bytes()
        artifact_text = artifact_bytes.decode("utf-8")
        doc = json.loads(artifact_text)
        if "transform" not in doc:
            raise SystemExit(
                f"{path}: no `transform`, so evidence coordinates cannot be resolved")
        try:
            validate_artifact_pair(doc, path)
            if artifact_uses_source_evidence(doc):
                transcript = _artifact_transcript(path, doc)
                cites = structured_artifact_citations(doc, transcript)
                claims = _claims_in_read_order(cites)
            else:
                transcript = None
                claims = [c for c in doc["claims"] if c["status"] == LOCATED]
        except (KeyError, TypeError, StructuredOutputError) as e:
            raise SystemExit(f"{path}: source evidence refused: {e}") from e
        prepared.append((
            path, doc, transcript, claims,
            hashlib.sha256(artifact_bytes).hexdigest(),
        ))

    judge_identity = resolve_ollama_model(model, min(timeout, 30))
    judge_system_sha256 = _sha256(SUPPORT_JUDGE)
    control_system_sha256 = _sha256(SABOTAGED_SUPPORT_JUDGE)
    fixture_set_sha256 = _sha256(json.dumps(
        SUPPORT_FIXTURES, ensure_ascii=False, separators=(",", ":")
    ))
    print("\n=== calibrating the support judge ===\n")
    real = _score_support_fixture_receipts(
        model, num_ctx, timeout, SUPPORT_JUDGE
    )
    control = _score_support_fixture_receipts(
        model, num_ctx, timeout, SABOTAGED_SUPPORT_JUDGE
    )
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

    if resolve_ollama_model(model, min(timeout, 30)) != judge_identity:
        raise SystemExit(
            "support judge identity changed during calibration; no claims measured"
        )

    print("\n=== do located quotes support their claims ===\n")
    supported = unsupported = unparsed = 0
    by_kind: dict[str, list[bool | None]] = {}
    for path, doc, transcript, claims, artifact_sha256 in prepared:
        verdicts = []
        print(f"  {doc['meeting']['id']}: {len(claims)} located of "
              f"{len(doc['claims'])} claims")
        for c in claims:
            evidence_text, fragment_ids = (
                _claim_evidence_text(c, transcript)
                if transcript is not None else (c["quote"], [])
            )
            receipt = _judge_support_receipt(
                c["claim"], evidence_text, c.get("type"), model, num_ctx, timeout
            )
            verdict = receipt["supports"]
            judge_input_sha256 = _sha256(
                _support_judge_prompt(c["claim"], evidence_text, c.get("type"))
            )
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
            where = (
                f"{len(fragment_ids)} source fragment(s)"
                if fragment_ids else f"turn {c['turn']}"
            )
            print(f"                 {where}: {c['quote'][:88]!r}")
            support_row = {
                "claim": c["claim"],
                "quote": c["quote"],
                "type": c.get("type"),
                "supports": verdict,
                "judge_input_sha256": judge_input_sha256,
                "judge_response": receipt["judge_response"],
                "judge_response_sha256": receipt["judge_response_sha256"],
            }
            if fragment_ids:
                support_row.update({
                    "source_item_ids": c["source_item_ids"],
                    "source_fragment_ids": fragment_ids,
                    "evidence_set_sha256": _sha256(evidence_text),
                })
            verdicts.append(support_row)

        # Written into the artifact so the measurement is reusable instead of a console
        # run somebody has to remember. Content-addressed on claim and quote rather than
        # keyed by position: `recheck` rebuilds `claims` from the citation buckets, and a
        # verdict stored on a claim would be silently dropped the next time it ran.
        current_identity = resolve_ollama_model(model, min(timeout, 30))
        if current_identity != judge_identity:
            raise SystemExit(
                "support judge identity changed during measurement; no verdicts written"
            )
        if hashlib.sha256(path.read_bytes()).hexdigest() != artifact_sha256:
            raise SystemExit(
                f"{path}: note artifact changed during support measurement; "
                "no verdicts written"
            )
        doc["support"] = {
            "schema": "support-measurement/1",
            "judge": model,
            "judge_identity": judge_identity,
            "judge_system_sha256": judge_system_sha256,
            "control_system_sha256": control_system_sha256,
            "fixture_set_sha256": fixture_set_sha256,
            "options": {"num_ctx": num_ctx, "temperature": 0.0},
            "calibration": real["agreement"],
            "control": control["agreement"],
            "calibration_receipts": real["receipts"],
            "control_receipts": control["receipts"],
            "measured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "verdicts": verdicts,
        }
        _write_support_measurement(path, doc, transcript)
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


def _write_support_measurement(path: Path, doc: dict,
                               transcript: Transcript | None) -> None:
    """Validate and atomically persist support without disturbing the note pair."""
    validate_note_render(doc)
    if transcript is not None:
        validate_support_measurement(doc, transcript)
    _atomic_replace_text(
        path, json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
    )
    validate_artifact_pair(doc, path)


def recheck(artifact: Path) -> dict:
    """Re-derive an existing artifact's citations without calling a model.

    Needed because the checker changes. The two-parser defect meant three artifacts on
    disk reported 0 quotes where 41 were present, and re-running the model to correct
    that would have cost eleven minutes on the longest meeting *and* produced a
    different note — so the corrected figure would not have been the corrected figure
    for the note that was measured. Re-deriving keeps the note fixed and moves only the
    judgement, which is what a correction is.

    Only the citation check is recomputed, because it is the only legacy check whose
    inputs survive in the artifact: the note text and the transcript. `numbers`,
    `grounding` and `prompt_echo` compare against the rendered prompt and the system
    message, which are not stored; carrying their stored verdicts forward is honest,
    silently recomputing them against a substitute input would not be.

    Repair 4 additionally retains each schema-validated message JSON body. Recheck
    decodes those safe ID/label/claim objects again, including key order and
    cardinality, then re-derives extraction claims, consolidation input, coverage,
    output claims, and digests against the transcript. The Ollama transport envelope
    and historical model-list response remain absent. The artifact is unsigned, so a
    coordinated rewrite of content, contracts, and hashes is outside this check's
    trust boundary.
    """
    doc = json.loads(artifact.read_text())
    if doc.get("schema") not in NOTE_SCHEMAS:
        raise SystemExit(
            f"{artifact}: expected one of {sorted(NOTE_SCHEMAS)}, "
            f"got {doc.get('schema')!r}")
    if "transform" not in doc:
        raise SystemExit(f"{artifact}: no `transform`, so the turn indices cannot be "
                         f"resolved. Regenerate from the model.")

    try:
        validate_artifact_pair(doc, artifact)
        t = _artifact_transcript(artifact, doc)
        cites = (
            structured_artifact_citations(doc, t)
            if artifact_uses_source_evidence(doc) else check_citations(doc["note"], t)
        )
    except StructuredOutputError as e:
        raise SystemExit(f"{artifact}: source evidence refused: {e}") from e
    doc["claims"] = _claims_in_read_order(cites)
    doc["checks"]["citations"] = cites
    # The stored verdict was formed with the old citation result in it, so it has to
    # move too — otherwise the artifact would carry a corrected finding under an
    # uncorrected pass mark.
    was = doc["passed"]
    doc["passed"] = verdict(doc["checks"])
    support = validate_support_measurement(doc, t) if "support" in doc else None
    if support:
        judged = {_support_key(v) for v in support["verdicts"]}
        now = {_support_key(c) for c in doc["claims"] if c["status"] == LOCATED}
        if stale := judged - now:
            print(f"      {len(stale)} stored support verdict(s) no longer match any "
                  f"located claim — re-run --measure-support")
        if fresh := now - judged:
            print(f"      {len(fresh)} located claim(s) have no support verdict")
    doc["provenance"]["rechecked_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    _atomic_replace_text(
        artifact, json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
    )
    try:
        validate_artifact_pair(doc, artifact)
    except StructuredOutputError as e:
        raise SystemExit(f"{artifact}: rewritten note pair refused: {e}") from e

    by = Counter(c["status"] for c in doc["claims"])
    print(f"  {artifact.name}: {cites['items']} items -> "
          f"{', '.join(f'{n} {s}' for s, n in by.most_common())}")
    if cites["template_echo"]:
        print(f"      {cites['template_echo']} claim(s) carried template punctuation")
    if cites["reversed_locatable"]:
        # Printed here as well as in `report`, and this is the place it matters more:
        # re-deriving is how a parser assumption gets corrected against a note that
        # has already been generated, so the count that says the assumption is wrong
        # has to reach the person running the correction.
        print(f"      {cites['reversed_locatable']} collapsed item(s) locate only when "
              f"read backwards with both sides long enough to test — inspect the "
              f"parser orientation")
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
                  transform: str | None = None,
                  markdown_path: Path | None = None) -> dict:
    """The note as data, with each claim's evidence state attached.

    The markdown a model emits is a *rendering* of a note, not the note. It cannot
    carry which claims were checked or what the check found, so a surface reading it
    would have to re-derive both and would disagree with `report` about it. This is
    the artifact; the markdown is kept beside it for reading.

    **Evidence is referenced, not duplicated as a second transcript.** A claim keeps
    the legacy primary `quote` for note/1 readers, while Repair 4 carries every source
    as an exact turn/character-span reference. The retained transcript remains the
    authority; recheck resolves those spans and refuses a drifting compatibility quote.

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
    structured = runtime_uses_source_evidence(result)
    markdown_path = markdown_path or (out_dir / f"{transcript_path.stem}.md")
    markdown_text = result["note"] + "\n"
    if structured:
        try:
            expected_citations = structured_citations(result, transcript)
        except StructuredOutputError as e:
            raise StructuredOutputError(
                f"cannot write Repair 4 artifact: {e}"
            ) from e
        if checks["citations"] != expected_citations:
            raise StructuredOutputError(
                "cannot write Repair 4 artifact from a different citation verdict")

    artifact = {
        "schema": STRUCTURED_NOTE_SCHEMA if structured else LEGACY_NOTE_SCHEMA,
        **({
            "claim_evidence_contract": SOURCE_EVIDENCE_CONTRACT
        } if structured else {}),
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
        "render": {
            "schema": NOTE_RENDER_SCHEMA,
            "path": os.path.relpath(markdown_path, out_dir),
            "encoding": "utf-8",
            "line_ending": "LF",
            "terminal_newline": True,
            "note_sha256": _sha256(result["note"]),
            "markdown_sha256": _sha256(markdown_text),
        },
        "claims": claims,
        # Repair 4's durable ID and coverage graph. It retains references, labels,
        # and exact-span metadata but no second transcript.
        **({"evidence": result["evidence_contract"]} if structured else {}),
        "capture": transcript.gate,
        "provenance": {
            "model": result["model"],
            "model_identity": result.get("model_identity"),
            "elapsed_s": round(result["elapsed_s"], 1),
            "passes": 2 if structured else 1,
            "slices": result.get("slices"),
            # `null` on both current paths: live Markdown is never deduplicated after
            # generation. Kept for note/1 compatibility with older artifacts that
            # recorded the now-retired chunked Markdown pass.
            "duplicates_removed": result.get("duplicates_removed"),
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            # Only schema-validated stage JSON survives: IDs, labels, and claims.
            # Source text stays in the transcript; the Ollama transport envelope and
            # historical model-list response do not become artifact authority.
            "structured_stages": result.get("structured_provenance"),
            "structured_contract": result.get("structured_contract"),
            "source_evidence": (
                {
                    key: result["evidence_contract"][key]
                    for key in (
                        "schema", "transcript_view_sha256",
                        "fragment_contract_sha256", "fragment_map_sha256",
                    )
                }
                if structured else None
            ),
        },
        # Carried whole. A surface may only need citations today, but a note whose
        # own record of what was checked is partial cannot be audited later.
        "checks": {k: v for k, v in checks.items() if k != "passed"},
        "passed": checks["passed"],
    }
    return artifact


def write_note_outputs(result: dict, transcript: Transcript, checks: dict,
                       transcript_path: Path, out: Path,
                       transform: str | None = None, *,
                       replace: bool = False) -> tuple[dict, tuple[Path, Path]]:
    """Validate, then install an owner-private Markdown/JSON pair.

    JSON is the canonical note. Markdown is its exact UTF-8 rendering, bound back to
    the artifact by two digests. Each file is installed atomically from a same-directory
    temporary file. Ordinary exceptions roll back a new or replacement pair; a process
    or OS crash between the two atomic installs can still leave a detectable mismatch.
    """
    markdown, artifact = validate_output_target(out, replace=replace)
    doc = note_artifact(
        result, transcript, checks, transcript_path, out.parent, transform,
        markdown_path=markdown,
    )
    markdown_text = validate_note_render(doc)
    if runtime_uses_source_evidence(result):
        # Artifact construction is complete before either public target can exist.
        structured_artifact_citations(doc, transcript)
    artifact_text = json.dumps(doc, ensure_ascii=False, indent=2) + "\n"

    # Close the ordinary preflight-to-write race before creating temporary content.
    validate_output_target(out, replace=replace)
    artifact_temp = _write_private_temp(artifact, artifact_text)
    markdown_temp = None
    installed: list[tuple[Path, Path]] = []
    replaced: list[tuple[Path, Path]] = []
    replacement_installs: list[tuple[Path, os.stat_result]] = []
    try:
        markdown_temp = _write_private_temp(markdown, markdown_text)
        if replace:
            for target in (artifact, markdown):
                if target.exists() or target.is_symlink():
                    backup = _reserve_private_backup(target)
                    os.replace(target, backup)
                    replaced.append((target, backup))
                    if not backup.is_symlink():
                        os.chmod(backup, 0o600)
        for temp, target in (
            (artifact_temp, artifact),
            (markdown_temp, markdown),
        ):
            if replace:
                os.replace(temp, target)
                replacement_installs.append((
                    target, target.stat(follow_symlinks=False)
                ))
            else:
                # `link` is an atomic no-clobber install on the same filesystem.
                os.link(temp, target)
                installed.append((target, temp))
        _fsync_directory(out.parent)
    except Exception as install_error:
        # A late no-clobber conflict must not strand the other half of a new pair.
        # Compare inodes before unlinking so a concurrent replacement is never removed.
        rollback_errors = []
        if replace:
            for target, installed_stat in reversed(replacement_installs):
                try:
                    current = target.stat(follow_symlinks=False)
                    if (
                        current.st_dev,
                        current.st_ino,
                    ) == (
                        installed_stat.st_dev,
                        installed_stat.st_ino,
                    ):
                        target.unlink()
                except FileNotFoundError:
                    pass
                except OSError as e:
                    rollback_errors.append(e)
            for target, backup in reversed(replaced):
                try:
                    if backup.exists() or backup.is_symlink():
                        os.replace(backup, target)
                except OSError as e:
                    rollback_errors.append(e)
        else:
            for target, temp in reversed(installed):
                try:
                    target_stat = target.stat(follow_symlinks=False)
                    temp_stat = temp.stat(follow_symlinks=False)
                except FileNotFoundError:
                    continue
                if (
                    target_stat.st_dev,
                    target_stat.st_ino,
                ) == (
                    temp_stat.st_dev,
                    temp_stat.st_ino,
                ):
                    try:
                        target.unlink()
                    except OSError as e:
                        rollback_errors.append(e)
        with contextlib.suppress(OSError):
            _fsync_directory(out.parent)
        if rollback_errors:
            raise StructuredOutputError(
                "note-pair install failed and rollback was incomplete"
            ) from install_error
        raise
    else:
        for _target, backup in replaced:
            with contextlib.suppress(OSError):
                backup.unlink()
        with contextlib.suppress(OSError):
            _fsync_directory(out.parent)
    finally:
        for temp in (artifact_temp, markdown_temp):
            if temp is not None:
                with contextlib.suppress(FileNotFoundError):
                    temp.unlink()

    validate_artifact_pair(doc, artifact)
    return doc, (markdown, artifact)


def output_paths(out: Path) -> tuple[Path, Path]:
    """Return the human-readable note and its canonical JSON artifact."""
    return out, out.with_suffix(".note.json")


def validate_output_target(out: Path, *, replace: bool = False) -> tuple[Path, Path]:
    """Preflight both output names before inference or filesystem mutation."""
    if out.name.endswith(".items.md"):
        raise StructuredOutputError(
            "--out cannot use the retired .items.md sidecar name")
    if not out.parent.exists():
        raise StructuredOutputError(
            f"--out {out}: parent directory {out.parent} does not exist")
    if not out.parent.is_dir():
        raise StructuredOutputError(
            f"--out {out}: parent path {out.parent} is not a directory")
    stale_sidecar = out.with_suffix(".items.md")
    if stale_sidecar.exists() or stale_sidecar.is_symlink():
        raise StructuredOutputError(
            f"--out refused: retired extraction sidecar still exists at "
            f"{stale_sidecar}. Move or remove it explicitly before this run."
        )
    markdown, artifact = output_paths(out)
    for label, path in (("Markdown", markdown), ("artifact", artifact)):
        exists = path.exists() or path.is_symlink()
        if path.is_dir() and not path.is_symlink():
            raise StructuredOutputError(
                f"--out refused: {label} target is a directory: {path}")
        if exists and not replace:
            raise StructuredOutputError(
                f"--out refused: {label} target already exists at {path}. "
                "Use --replace to replace the pair explicitly.")
    return markdown, artifact


def validate_note_render(doc: dict, markdown_text: str | None = None) -> str:
    """Re-derive the exact Markdown bytes declared by a note artifact."""
    note = doc.get("note")
    if not isinstance(note, str):
        raise StructuredOutputError("note artifact has no string `note`")
    render = doc.get("render")
    if render is None:
        if doc.get("schema") == STRUCTURED_NOTE_SCHEMA:
            raise StructuredOutputError(
                f"{STRUCTURED_NOTE_SCHEMA} artifact is missing its render contract")
        canonical = note + "\n"
        if markdown_text is not None and markdown_text != canonical:
            raise StructuredOutputError(
                "legacy Markdown does not match the note stored in JSON")
        return canonical

    required = {
        "schema", "path", "encoding", "line_ending", "terminal_newline",
        "note_sha256", "markdown_sha256",
    }
    if not isinstance(render, dict) or set(render) != required:
        raise StructuredOutputError("note render contract has the wrong shape")
    render_path = render["path"]
    if (
        not isinstance(render_path, str)
        or not render_path
        or render_path in {".", ".."}
        or "/" in render_path
        or "\\" in render_path
        or Path(render_path).is_absolute()
    ):
        raise StructuredOutputError(
            "note render path must be one filename beside the JSON artifact")
    if (
        render["schema"] != NOTE_RENDER_SCHEMA
        or render["encoding"] != "utf-8"
        or render["line_ending"] != "LF"
        or render["terminal_newline"] is not True
    ):
        raise StructuredOutputError("note render encoding contract is not current")
    if "\r" in note:
        raise StructuredOutputError(
            "note render declares LF but the canonical note contains CR characters")
    canonical = note + "\n"
    if (
        render["note_sha256"] != _sha256(note)
        or render["markdown_sha256"] != _sha256(canonical)
    ):
        raise StructuredOutputError(
            "note or Markdown digest does not re-derive from canonical JSON")
    if markdown_text is not None and markdown_text != canonical:
        raise StructuredOutputError(
            "Markdown file does not exactly match the canonical note in JSON")
    return canonical


def validate_artifact_pair(doc: dict, artifact: Path) -> Path | None:
    """Validate a JSON artifact and its declared sibling Markdown rendering."""
    canonical = validate_note_render(doc)
    render = doc.get("render")
    if render is None:
        return None
    markdown = artifact.parent / render["path"]
    for label, path in (("artifact", artifact), ("Markdown", markdown)):
        if path.is_symlink():
            raise StructuredOutputError(
                f"{label} side of note pair may not be a symlink: {path}")
        if not path.is_file():
            raise StructuredOutputError(
                f"{label} side of note pair is missing or not a file: {path}")
        if (
            doc.get("schema") == STRUCTURED_NOTE_SCHEMA
            and path.stat().st_mode & 0o777 != 0o600
        ):
            raise StructuredOutputError(
                f"{STRUCTURED_NOTE_SCHEMA} {label} is not owner-private: {path}")
    try:
        markdown_text = markdown.read_text(encoding="utf-8")
    except UnicodeDecodeError as e:
        raise StructuredOutputError(
            f"Markdown side of note pair is not UTF-8: {markdown}") from e
    validate_note_render(doc, markdown_text)
    if markdown_text != canonical:
        raise StructuredOutputError(
            "Markdown side of note pair differs from canonical JSON")
    return markdown


def _write_private_temp(target: Path, text: str) -> Path:
    """Write and fsync an owner-only temporary file beside its final target."""
    fd, name = tempfile.mkstemp(
        dir=target.parent,
        prefix=f".{target.name}.",
        suffix=".tmp",
        text=True,
    )
    temp = Path(name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        with contextlib.suppress(OSError):
            os.close(fd)
        with contextlib.suppress(FileNotFoundError):
            temp.unlink()
        raise
    return temp


def _reserve_private_backup(target: Path) -> Path:
    """Reserve an unguessable sibling name for reversible pair replacement."""
    fd, name = tempfile.mkstemp(
        dir=target.parent,
        prefix=f".{target.name}.",
        suffix=".backup",
    )
    os.close(fd)
    backup = Path(name)
    backup.unlink()
    return backup


def _fsync_directory(path: Path) -> None:
    """Persist same-directory renames/links before reporting the pair as written."""
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _atomic_replace_text(target: Path, text: str) -> None:
    """Replace one file atomically from an owner-private sibling temporary."""
    temp = _write_private_temp(target, text)
    try:
        os.replace(temp, target)
        _fsync_directory(target.parent)
    finally:
        with contextlib.suppress(FileNotFoundError):
            temp.unlink()


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
    print("=== capture provenance survives transcript transforms ===\n")
    captured = Transcript(
        source="capture fixture",
        attribution=CHANNEL,
        turns=[Turn(text="visible words", speaker="Me", start=1.0)],
        gated_turns=[Turn(text="withheld words", speaker="Me", start=2.0)],
        gate={"applied": True, "rejected": 1, "rejected_seconds": 1.0},
    )
    derived = {
        "strip": captured.strip_attribution(),
        "channel": captured.as_channel("Me"),
        "bleed": captured.simulate_bleed(),
        "chunk": chunk_transcript(captured, target_words=1, overlap_words=0)[0],
    }
    kept = all(d.gate == captured.gate and len(d.gated_turns) == 1
               and d.gate_warnings for d in derived.values())
    failures += not kept
    print(f"  [{'pass' if kept else 'FAIL'}] every derived transcript keeps the "
          "gate report, warning, and withheld turn")
    derived["strip"].gate["rejected"] = 99
    isolated = captured.gate["rejected"] == 1
    failures += not isolated
    print(f"  [{'pass' if isolated else 'FAIL'}] a derived view cannot mutate the "
          "capture's gate report")

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
        Turn(text="we 'd have enough data if it 's ready", speaker="Me", start=55.0),
        Turn(text="we definitely w will need it 'd b it 'd be nice",
             speaker="Me", start=60.0),
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
    cite_case("spaced contraction suffixes are corpus formatting, not different words",
              "## Decisions\n- Enough data.\n  > we'd have enough data if it's ready",
              True, cited=1)
    cite_case("normalization does not delete recorded disfluencies to make a quote fit",
              "## Decisions\n- More data.\n  > we definitely will need it'd be nice",
              False, fabricated=1)
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
    # Which side of a collapsed line holds speech is an assumption. The note below is
    # the failure an older, reverse-order consolidator input could produce: real quotes
    # on the left and summaries on the right. The two items land in different buckets —
    # one fabricated and one untestable because its assumed quote is short. Only the
    # testable reverse match belongs in `reversed_locatable`; counting the short side
    # would promote "not searched" into "not found".
    cite_case("a testable reverse match is counted without promoting a short side "
              "into a failed search",
              "## Decisions\n"
              "- go with the rubber for the case | Rubber casing chosen.\n"
              "- the supplier said eight weeks which is too long | Lead time too long.\n",
              False, fabricated=1, unverifiable=1, cited=0, reversed_locatable=1)
    cite_case("and a note read the right way round reports none",
              collapsed_note, True, reversed_locatable=0)
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
        p = parse_item(line)
        got = None if not p else (p["label"], p["text"], p["quote"], p["order"])
        ok = got == want
        failures += not ok
        print(f"  [{'pass' if ok else 'FAIL'}] {label}")
        if not ok:
            print(f"          got {got!r}")

    item_case("the inverted line reads the words before the pipe as the quote",
              "i'll send an email and ask | ACTION: Send the corpus licence",
              ("ACTION", "Send the corpus licence", "i'll send an email and ask",
               "quote-first"))
    # The defect this reproduces: hedged speech under a summary that overstates it.
    # Whichever field the parser calls the quote decides whether `check_citations`
    # looks for the spoken words in the transcript or for the model's own summary,
    # and the second finds nothing and calls it fabricated.
    item_case("a hedged quote is not mistaken for the claim it sits beside",
              "maybe we should write it down | PROPOSAL: Write down the error message",
              ("PROPOSAL", "Write down the error message",
               "maybe we should write it down", "quote-first"))
    item_case("a claim containing a pipe survives the inverted split",
              "we said utf-8 | QUESTION: Which encoding | and which locale",
              ("QUESTION", "Which encoding | and which locale", "we said utf-8",
               "quote-first"))
    item_case("the order the contract used to ask for is still read, and recorded",
              "ACTION: Send the corpus licence | i'll send an email and ask",
              ("ACTION", "Send the corpus licence", "i'll send an email and ask",
               "claim-first"))
    item_case("an item with no evidence still parses, rather than being dropped",
              "DECISION: Delay the anonymisation",
              ("DECISION", "Delay the anonymisation", "", "claim-first"))
    item_case("a quote containing a pipe keeps everything after the first one",
              "QUESTION: Which encoding | we said utf-8 | not latin-1",
              ("QUESTION", "Which encoding", "we said utf-8 | not latin-1",
               "claim-first"))

    # Both halves of the drop check, because only the negative one is load-bearing.
    # A check that flags every unparsed line would flag the preamble the model writes
    # despite being told not to, and a check nobody can keep green gets switched off.
    drop_lines = [
        "we agreed on the rubber case | RESOLUTION: use rubber",  # a label it invented
        "Here are the items from this slice:",                    # preamble, correctly ignored
        "",
        "i'll send an email and ask | ACTION: Send the corpus licence",
    ]
    ext = check_extraction(drop_lines, [p for ln in drop_lines if (p := parse_item(ln))])
    ext_ok = (ext["ok"] is False
              and ext["dropped"] == ["we agreed on the rubber case | RESOLUTION: use rubber"]
              and ext["orders"] == {"quote-first": 1})
    failures += not ext_ok
    print(f"  [{'pass' if ext_ok else 'FAIL'}] a line shaped like an item that parses as "
          f"none is counted, and preamble is not")
    if not ext_ok:
        print(f"          got {ext!r}")

    clean = check_extraction(["i'll send an email and ask | ACTION: Send the corpus licence"],
                             [parse_item("i'll send an email and ask | ACTION: Send it")])
    v_ext = dict(stored, extraction={"applies": True, "ok": False})
    drop_fails = clean["ok"] is True and verdict(v_ext) is False
    failures += not drop_fails
    print(f"  [{'pass' if drop_fails else 'FAIL'}] a dropped extraction line fails the run, "
          f"rather than being reported and passing")

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

    print("\n=== structured note transport ===\n")

    def control(label: str, ok: bool) -> None:
        nonlocal failures
        failures += not ok
        print(f"  [{'pass' if ok else 'FAIL'}] {label}")

    # Fragment construction is local and deterministic. These controls use the
    # awkward inputs a copied-quote model had been tidying: Unicode, pipes, repeated
    # words, and a tail just below the merge floor.
    words_43 = [f"u{i}" for i in range(43)]
    words_43[3:7] = ["café", "a|b", "repeat", "repeat"]
    words_44 = [f"v{i}" for i in range(44)]
    fragment_fixture = Transcript(
        source="fragment fixture",
        attribution=NONE,
        turns=[
            Turn(text="  " + " \t".join(words_43) + "  ", start=1.0),
            Turn(text=" ".join(words_44), start=2.0),
            Turn(text="proposal words stay | exact and repeated repeated", start=3.0),
        ],
        gated_turns=[Turn(text="this gated speech must never become evidence")],
    )
    fragment_map = build_fragment_map(fragment_fixture)
    fragments = fragment_map["fragments"]
    control(
        "32-word fragments overlap by eight, merge an under-12 tail, and never cross turns",
        len([row for row in fragments if row["turn"] == 0]) == 1
        and len(fragments[0]["text"].split()) == 43
        and len([row for row in fragments if row["turn"] == 1]) == 2
        and all(row["turn"] in {0, 1, 2} for row in fragments)
        and all("gated speech" not in row["text"] for row in fragments),
    )
    exact_fragment = fragments[0]
    control(
        "fragment offsets preserve Unicode, pipes, repeated words, and internal whitespace",
        fragment_fixture.turns[0].text[
            exact_fragment["char_start"]:exact_fragment["char_end"]
        ] == exact_fragment["text"]
        and "café" in exact_fragment["text"]
        and "a|b" in exact_fragment["text"]
        and "repeat \trepeat" in exact_fragment["text"],
    )
    same_map = build_fragment_map(fragment_fixture)
    changed_fixture = fragment_fixture._derived(
        source="changed",
        attribution=NONE,
        turns=[
            Turn(text=fragment_fixture.turns[0].text + " changed"),
            *fragment_fixture.turns[1:],
        ],
    )
    changed_map = build_fragment_map(changed_fixture)
    control(
        "fragment IDs ignore slice boundaries but change namespace with visible content",
        [row["source_fragment_id"] for row in same_map["fragments"]]
        == [row["source_fragment_id"] for row in fragments]
        and fragment_map["transcript_view_sha256"]
        != changed_map["transcript_view_sha256"]
        and not (
            {row["source_fragment_id"] for row in fragments}
            & {row["source_fragment_id"] for row in changed_map["fragments"]}
        ),
    )
    narrow_windows = _chunk_turn_windows(fragment_fixture, 20, 5)
    wide_windows = _chunk_turn_windows(fragment_fixture, 80, 10)
    all_ids = {row["source_fragment_id"] for row in fragments}
    narrow_ids = {
        row["source_fragment_id"]
        for window in narrow_windows
        for turn in window
        for row in fragments
        if row["turn"] == turn
    }
    wide_ids = {
        row["source_fragment_id"]
        for window in wide_windows
        for turn in window
        for row in fragments
        if row["turn"] == turn
    }
    repeated_fixture = Transcript(
        source="repeated turns", attribution=NONE,
        turns=[Turn(text="same words repeat exactly"),
               Turn(text="same words repeat exactly")],
    )
    repeated_ids = [
        row["source_fragment_id"]
        for row in build_fragment_map(repeated_fixture)["fragments"]
    ]
    control(
        "changing slice windows cannot change IDs, and repeated text keeps distinct spans",
        narrow_ids == wide_ids == all_ids
        and len(repeated_ids) == len(set(repeated_ids)) == 2,
    )

    fragment_ids = [row["source_fragment_id"] for row in fragments]
    dynamic_extract = extraction_format(fragment_ids)
    request = _ollama_payload("fixture", "system", "user", 1234, dynamic_extract)
    control(
        "each extraction call sends a slice-local fragment enum without sampling",
        request.get("format") == dynamic_extract
        and dynamic_extract["properties"]["items"]["items"]["properties"][
            "source_fragment_ids"
        ]["items"]["enum"] == fragment_ids
        and request["options"]["temperature"] == 0.0
        and request["stream"] is False,
    )
    control(
        "the live extraction schema has no field where a model can author quote text",
        "quote" not in dynamic_extract["properties"]["items"]["items"]["properties"],
    )

    def extract_case(label: str, source_fragment_ids: list[str],
                     want_ok: bool) -> dict | None:
        raw = json.dumps({
            "items": [{
                "source_fragment_ids": source_fragment_ids,
                "label": "QUESTION",
                "claim": "Keep the source evidence exact",
            }]
        }, ensure_ascii=False, separators=(",", ":"))
        try:
            got = decode_records(
                raw, "extract", allowed_fragment_ids=fragment_ids
            )
            ok = want_ok
        except StructuredOutputError:
            got, ok = None, not want_ok
        control(label, ok)
        return got

    extract_case("one source fragment is a valid evidence set",
                 fragment_ids[:1], True)
    two_refs = extract_case("two ordered source fragments are a valid evidence set",
                            fragment_ids[:2], True)
    extract_case("three ordered source fragments are a valid evidence set",
                 fragment_ids[:3], True)
    extract_case("an empty evidence set fails before a claim exists", [], False)
    extract_case("duplicate source fragments fail", [fragment_ids[0], fragment_ids[0]],
                 False)
    extract_case("out-of-order source fragments fail",
                 [fragment_ids[1], fragment_ids[0]], False)
    extract_case("a source fragment outside the slice fails",
                 [fragment_ids[0][:-1] + "x"], False)
    extract_case("four source fragments exceed the bounded evidence set",
                 fragment_ids[:4], False)
    reordered_raw = json.dumps({
        "items": [{
            "claim": "Claim came first",
            "label": "QUESTION",
            "source_fragment_ids": [fragment_ids[0]],
        }]
    }, separators=(",", ":"))
    try:
        decode_records(
            reordered_raw, "extract", allowed_fragment_ids=fragment_ids
        )
        reordered_refused = False
    except StructuredOutputError:
        reordered_refused = True
    control("claim-first extraction keys fail the causal generation audit",
            reordered_refused)
    invalid_extractions = (
        "",
        "ACTION: send the file",
        '{"items":{}}',
        '{"items":[{"source_fragment_ids":[],"label":"QUESTION","claim":"x"}]}',
        ('{"items":[{"source_fragment_ids":["' + fragment_ids[0]
         + '"],"label":"RESOLUTION","claim":"x"}]}'),
        ('{"items":[{"source_fragment_ids":["' + fragment_ids[0]
         + '"],"label":"QUESTION","claim":"  "}]}'),
        ('{"items":[{"source_fragment_ids":["' + fragment_ids[0]
         + '"],"label":"QUESTION","claim":"x\\n- injected"}]}'),
        ('{"items":[{"source_fragment_ids":["' + fragment_ids[0]
         + '"],"label":"QUESTION","claim":"x","confidence":"high"}]}'),
        ('{"items":[{"source_fragment_ids":["' + fragment_ids[0]
         + '"],"source_fragment_ids":["' + fragment_ids[1]
         + '"],"label":"QUESTION","claim":"x"}]}'),
    )
    invalid_closed = True
    for raw in invalid_extractions:
        try:
            decode_records(raw, "extract", allowed_fragment_ids=fragment_ids)
            invalid_closed = False
        except StructuredOutputError:
            pass
    control(
        "blank, malformed, duplicate-key, invalid, injected, and extra fields fail closed",
        invalid_closed,
    )
    empty_extract = decode_records(
        '{"items":[]}', "extract", allowed_fragment_ids=fragment_ids
    )
    empty_consolidation = decode_records(
        '{"items":[]}',
        "consolidate", input_items=[],
    )
    empty_note = render_structured_note(empty_consolidation["items"])
    control(
        "schema-valid empty stages render an explicit local no-claims state",
        empty_extract == {"items": []}
        and empty_consolidation == {"items": []}
        and empty_note == (
            "## Evidence-bound note\nNo evidence-bound claims were produced."
        )
        and not _parse_claims(empty_note),
    )
    shared_fragment = decode_records(
        json.dumps({
            "items": [
                {"source_fragment_ids": [fragment_ids[0]], "label": "QUESTION",
                 "claim": "Choose the source format"},
                {"source_fragment_ids": [fragment_ids[0]], "label": "PROPOSAL",
                 "claim": "Retain the repeated words"},
            ]
        }, separators=(",", ":")),
        "extract", allowed_fragment_ids=fragment_ids,
    )
    control(
        "one source fragment can independently support two extraction records",
        len(shared_fragment["items"]) == 2
        and all(
            item["source_fragment_ids"] == [fragment_ids[0]]
            for item in shared_fragment["items"]
        ),
    )

    assert two_refs is not None
    action_raw = json.dumps({
        "items": [{
            "source_fragment_ids": [fragment_ids[2]],
            "label": "ACTION",
            "claim": "Send the exact record",
        }]
    }, separators=(",", ":"))
    action = decode_records(
        action_raw, "extract", allowed_fragment_ids=fragment_ids[2:]
    )
    question_items = attach_evidence_items(
        two_refs["items"], 1,
        {row["source_fragment_id"]: row for row in fragments},
        fragment_fixture, fragment_map["transcript_view_sha256"],
    )
    action_items = attach_evidence_items(
        action["items"], 2,
        {row["source_fragment_id"]: row for row in fragments},
        fragment_fixture, fragment_map["transcript_view_sha256"],
    )
    source_items = [*question_items, *action_items]
    source_ids = [row["evidence_item_id"] for row in source_items]
    dynamic_consolidate = consolidation_format(source_ids)
    valid_consolidation_raw = json.dumps({
        "items": [
            {
                "source_item_ids": [source_ids[0]],
                "label": "QUESTION",
                "claim": "Keep the source evidence exact",
            },
            {
                "source_item_ids": [source_ids[1]],
                "label": "ACTION",
                "claim": "Send the exact record",
            },
        ],
    }, separators=(",", ":"))
    consolidated_new = decode_records(
        valid_consolidation_raw, "consolidate", input_items=source_items
    )
    control(
        "consolidation groups first and resolves a canonical ordered fragment union locally",
        tuple(dynamic_consolidate["properties"]) == ("items",)
        and "summary" not in json.dumps(dynamic_consolidate)
        and tuple(dynamic_consolidate["properties"]["items"]["items"]["properties"])
        == ("source_item_ids", "label", "claim")
        and len(consolidated_new["items"][0]["evidence_refs"]) == 2
        and consolidated_new["items"][0]["quote"]
        == consolidated_new["items"][0]["evidence_refs"][0]["quote"],
    )

    def consolidation_case(label: str, rows: list[dict], want_ok: bool) -> None:
        raw = json.dumps(
            {"items": rows},
            separators=(",", ":"),
        )
        try:
            decode_records(raw, "consolidate", input_items=source_items)
            ok = want_ok
        except StructuredOutputError:
            ok = not want_ok
        control(label, ok)

    consolidation_case(
        "consolidation cannot drop a validated extraction item",
        [{
            "source_item_ids": [source_ids[0]], "label": "QUESTION",
            "claim": "Keep the evidence exact",
        }],
        False,
    )
    consolidation_case(
        "consolidation cannot cover one extraction item twice",
        [
            {"source_item_ids": [source_ids[0]], "label": "QUESTION",
             "claim": "First"},
            {"source_item_ids": [source_ids[0], source_ids[1]], "label": "QUESTION",
             "claim": "Second"},
        ],
        False,
    )
    consolidation_case(
        "consolidation cannot invent an extraction item ID",
        [
            {"source_item_ids": ["unknown"], "label": "QUESTION", "claim": "Unknown"},
            {"source_item_ids": source_ids, "label": "QUESTION", "claim": "All"},
        ],
        False,
    )
    consolidation_case(
        "consolidation cannot merge extraction items across labels",
        [{"source_item_ids": source_ids, "label": "QUESTION", "claim": "Crossed"}],
        False,
    )
    duplicate_inputs = []
    for index in range(1, 5):
        duplicate = json.loads(json.dumps(source_items[0]))
        duplicate["evidence_item_id"] = f"duplicate-{index}"
        duplicate_inputs.append(duplicate)
    bounded_duplicate = decode_records(
        json.dumps({
            "items": [{
                "source_item_ids": [
                    row["evidence_item_id"] for row in duplicate_inputs[:3]
                ],
                "label": duplicate_inputs[0]["label"],
                "claim": "Keep the source evidence exact",
            }],
        }, separators=(",", ":")),
        "consolidate", input_items=duplicate_inputs[:3],
    )
    four_way_refused = False
    try:
        decode_records(
            json.dumps({
                "items": [{
                    "source_item_ids": [
                        row["evidence_item_id"] for row in duplicate_inputs
                    ],
                    "label": duplicate_inputs[0]["label"],
                    "claim": "Keep the source evidence exact",
                }],
            }, separators=(",", ":")),
            "consolidate", input_items=duplicate_inputs,
        )
    except StructuredOutputError:
        four_way_refused = True
    distinct_inputs = json.loads(json.dumps(duplicate_inputs[:2]))
    distinct_inputs[1]["claim"] = "A different extraction claim"
    distinct_inputs[1]["claim_sha256"] = _sha256(distinct_inputs[1]["claim"])
    distinct_merge_refused = False
    try:
        decode_records(
            json.dumps({
                "items": [{
                    "source_item_ids": [
                        row["evidence_item_id"] for row in distinct_inputs
                    ],
                    "label": distinct_inputs[0]["label"],
                    "claim": "One rewritten claim",
                }],
            }, separators=(",", ":")),
            "consolidate", input_items=distinct_inputs,
        )
    except StructuredOutputError:
        distinct_merge_refused = True
    control(
        "consolidation groups at most three byte-identical claims and retains every member digest",
        dynamic_consolidate["properties"]["items"]["items"]["properties"][
            "source_item_ids"
        ]["maxItems"] == MAX_CONSOLIDATION_GROUP
        and len(bounded_duplicate["items"][0]["source_claim_sha256s"]) == 3
        and len(set(
            bounded_duplicate["items"][0]["source_claim_sha256s"]
        )) == 1
        and four_way_refused
        and distinct_merge_refused,
    )
    consolidation_injection_closed = True
    for raw in (
        json.dumps({
            "summary": "MODEL-AUTHORED NARRATIVE",
            "items": [
                {"source_item_ids": [source_ids[0]], "label": "QUESTION",
                 "claim": "Question"},
                {"source_item_ids": [source_ids[1]], "label": "ACTION",
                 "claim": "Action"},
            ],
        }, separators=(",", ":")),
        json.dumps({
            "items": [
                {"claim": "Question", "label": "QUESTION",
                 "source_item_ids": [source_ids[0]]},
                {"source_item_ids": [source_ids[1]], "label": "ACTION",
                 "claim": "Action"},
            ],
        }, separators=(",", ":")),
    ):
        try:
            decode_records(raw, "consolidate", input_items=source_items)
            consolidation_injection_closed = False
        except StructuredOutputError:
            pass
    control(
        "consolidation refuses model narrative and claim-first item keys",
        consolidation_injection_closed,
    )

    fixture_identity = model_identity_from_tags(
        {"models": [{"name": "fixture:latest", "model": "fixture:latest",
                     "digest": "a" * 64}]},
        "fixture:latest",
    )
    try:
        model_identity_from_tags(
            {"models": [
                {"name": "fixture:latest", "digest": "a" * 64},
                {"model": "fixture:latest", "digest": "b" * 64},
            ]},
            "fixture:latest",
        )
        ambiguous_model_refused = False
    except StructuredOutputError:
        ambiguous_model_refused = True
    control(
        "a mutable model tag resolves to one immutable digest before inference",
        fixture_identity["digest"] == "a" * 64 and ambiguous_model_refused,
    )
    original_resolve = resolve_ollama_model
    original_chat = ollama_chat
    invalid_preflight_calls = []

    def forbidden_inference(*_args, **_kwargs):
        invalid_preflight_calls.append("called")
        raise AssertionError("invalid options reached model work")

    globals()["resolve_ollama_model"] = forbidden_inference
    globals()["ollama_chat"] = forbidden_inference
    invalid_options_refused = True
    preflight_fixture = Transcript(
        source="invalid preflight fixture",
        attribution=NONE,
        turns=[Turn(text="one short turn")],
    )
    try:
        for model, num_ctx, timeout, target, overlap in (
            ("fixture:latest", 32768, 1, 0, 0),
            ("fixture:latest", 32768, 1, 10, -1),
            ("fixture:latest", 32768, 1, 10, 10),
            ("fixture:latest", 32768, 1, 10, 11),
            ("", 32768, 1, 10, 0),
            ("fixture:latest", 0, 1, 10, 0),
            ("fixture:latest", 32768, 0, 10, 0),
        ):
            try:
                summarize_chunked(
                    preflight_fixture, model, num_ctx, timeout, target, overlap
                )
                invalid_options_refused = False
            except StructuredOutputError:
                pass
    finally:
        globals()["resolve_ollama_model"] = original_resolve
        globals()["ollama_chat"] = original_chat
    control(
        "invalid inference and chunk options fail before model resolution or calls",
        invalid_options_refused and not invalid_preflight_calls,
    )
    fixture_transcript = Transcript(
        source="structured fixture",
        attribution=NONE,
        turns=[
            Turn(text="we said utf-8 | not latin-1", start=4.0),
            Turn(text="and agreed to keep the exact source words", start=5.0),
        ],
    )
    original_chat = ollama_chat
    try:
        def source_fixture_chat(model, system, user, num_ctx, timeout,
                                response_format=None):
            properties = response_format["properties"]["items"]["items"]["properties"]
            if "source_fragment_ids" in properties:
                ids = properties["source_fragment_ids"]["items"]["enum"]
                content = json.dumps({
                    "items": [{
                        "source_fragment_ids": ids[:2],
                        "label": "QUESTION",
                        "claim": "Choose and retain the exact encoding words",
                    }]
                }, separators=(",", ":"))
            elif "source_item_ids" in properties:
                ids = properties["source_item_ids"]["items"]["enum"]
                content = json.dumps({
                    "items": [{
                        "source_item_ids": ids,
                        "label": "QUESTION",
                        "claim": "Choose and retain the exact encoding words",
                    }],
                }, separators=(",", ":"))
            else:
                raise AssertionError("chunked stage omitted its source-reference schema")
            return {"message": {"content": content}, "prompt_eval_count": 16}

        globals()["ollama_chat"] = source_fixture_chat
        staged_new = summarize_chunked(
            fixture_transcript, "fixture:latest", 32768, 1, 1000, 0,
            model_identity=fixture_identity,
        )
    finally:
        globals()["ollama_chat"] = original_chat
    try:
        def empty_source_fixture_chat(model, system, user, num_ctx, timeout,
                                      response_format=None):
            return {
                "message": {"content": '{"items":[]}'},
                "prompt_eval_count": 8,
            }

        globals()["ollama_chat"] = empty_source_fixture_chat
        staged_empty = summarize_chunked(
            fixture_transcript, "fixture:latest", 32768, 1, 1000, 0,
            model_identity=fixture_identity,
        )
    finally:
        globals()["ollama_chat"] = original_chat
    empty_source_cites = structured_citations(staged_empty, fixture_transcript)
    control(
        "zero-item output is a deterministic no-evidence-bound-claims state",
        staged_empty["note"] == (
            "## Evidence-bound note\nNo evidence-bound claims were produced."
        )
        and staged_empty["consolidated_records"] == {"items": []}
        and staged_empty["evidence_contract"]["extraction_items"] == []
        and staged_empty["evidence_contract"]["consolidated_items"] == []
        and empty_source_cites["cited"] == [],
    )
    source_cites = structured_citations(staged_new, fixture_transcript)
    structured_checks = {
        **stored,
        "citations": source_cites,
        "extraction": staged_new["extraction"],
    }
    structured_doc = note_artifact(
        staged_new, fixture_transcript,
        {"passed": verdict(structured_checks), **structured_checks},
        Path("fixture.json"), Path("."),
    )
    artifact_cites = structured_artifact_citations(
        structured_doc, fixture_transcript
    )
    control(
        "source references survive extraction, consolidation, Markdown, note/2, and recheck",
        source_cites["authority"] == "source-evidence/1"
        and structured_doc["schema"] == STRUCTURED_NOTE_SCHEMA
        and len(source_cites["cited"][0]["evidence_refs"]) == 2
        and artifact_cites["cited"] == source_cites["cited"]
        and structured_doc["claims"][0]["quote"]
        == fixture_transcript.turns[0].text
        and len(structured_doc["claims"][0]["evidence_refs"]) == 2
        and structured_doc["evidence"]["fragment_map_sha256"]
        == staged_new["evidence_contract"]["fragment_map_sha256"],
    )
    control(
        "multiple evidence turns remain separate references rather than a synthetic quote",
        fixture_transcript.turns[1].text not in structured_doc["claims"][0]["quote"]
        and len(structured_doc["claims"][0]["evidence_refs"]) == 2
        and '"quote"' not in json.dumps(structured_doc["evidence"])
        and fixture_transcript.turns[0].text not in json.dumps(
            structured_doc["evidence"]
        ),
    )
    replayed_stages = validate_structured_stage_receipts(
        staged_new["structured_provenance"],
        staged_new["structured_contract"],
        staged_new["evidence_contract"],
        fixture_transcript,
        staged_new["model"],
        staged_new["model_identity"],
    )
    control(
        "safe stage JSON replays key order, claims, consolidation input, and coverage",
        all(row["model_digest"] == fixture_identity["digest"]
                for row in staged_new["structured_provenance"])
        and all("raw_response" not in row and "response_sha256" not in row
                for row in staged_new["structured_provenance"])
        and all(row["transport_response_retained"] is False
                and row["transport_response_limit"] == TRANSPORT_RESPONSE_LIMIT
                and row["response_validation"] == REPLAYABLE_SAFE_RESPONSE
                and row["validated_response_sha256"]
                == _sha256(row["validated_response_json"])
                for row in staged_new["structured_provenance"])
        and all(
            row["input_prompt_validation"] == REPLAYABLE_INPUT
            for row in staged_new["structured_provenance"]
            if row["stage"] == "extract"
        )
        and staged_new["structured_provenance"][-1][
            "input_prompt_validation"
        ] == REPLAYABLE_CONSOLIDATION_INPUT
        and staged_new["structured_provenance"][-1][
            "input_records_validation"
        ] == REPLAYABLE_CONSOLIDATION_INPUT
        and all({"transcript_view_sha256", "fragment_contract_sha256",
                 "fragment_map_sha256"}
                <= row["reference_context"].keys()
                for row in staged_new["structured_provenance"])
        and replayed_stages["stages"] is staged_new["structured_provenance"]
        and replayed_stages["consolidated_items"]
        == staged_new["consolidated_records"]["items"]
        and len(replayed_stages["extraction_items"])
        == len(staged_new["evidence_contract"]["extraction_items"])
        and fixture_transcript.turns[0].text not in json.dumps(
            staged_new["structured_provenance"], ensure_ascii=False
        )
        and structured_doc["provenance"]["source_evidence"][
            "transcript_view_sha256"
        ] == transcript_view_sha256(fixture_transcript)
        and staged_new["structured_contract"]["render_contract"]
        == STRUCTURED_NOTE_CONTRACT
        and staged_new["structured_contract"]["render_contract_sha256"]
        == _sha256(json.dumps(
            STRUCTURED_NOTE_CONTRACT, ensure_ascii=False, sort_keys=True,
            separators=(",", ":"),
        ))
    )
    with tempfile.TemporaryDirectory(prefix="repair4-output-control-") as tmp:
        output_dir = Path(tmp)
        output_path = output_dir / "fixture.md"
        validate_output_target(output_path)
        written_doc, written_paths = write_note_outputs(
            staged_new, fixture_transcript,
            {"passed": verdict(structured_checks), **structured_checks},
            Path("fixture.json"), output_path,
        )
        written_names = {path.name for path in written_paths}
        actual_names = {path.name for path in output_dir.iterdir()}
        pair_path = validate_artifact_pair(
            written_doc, output_path.with_suffix(".note.json")
        )
        pair_modes = {
            path.name: path.stat().st_mode & 0o777
            for path in written_paths
        }
        canonical_markdown = validate_note_render(written_doc)
        pair_regenerates = (
            pair_path == output_path
            and output_path.read_text(encoding="utf-8") == canonical_markdown
        )

        prior_pair = {
            path: path.read_bytes()
            for path in written_paths
        }
        try:
            write_note_outputs(
                staged_new, fixture_transcript,
                {"passed": verdict(structured_checks), **structured_checks},
                Path("fixture.json"), output_path,
            )
            target_conflict_refused = False
        except StructuredOutputError:
            target_conflict_refused = True
        target_conflict_unchanged = all(
            path.read_bytes() == content
            for path, content in prior_pair.items()
        )

        interrupted_output = output_dir / "interrupted.md"
        before_interrupted = {path.name for path in output_dir.iterdir()}
        original_link = os.link
        link_calls = 0

        def fail_second_link(source, target):
            nonlocal link_calls
            link_calls += 1
            if link_calls == 2:
                raise OSError("injected second no-clobber install failure")
            return original_link(source, target)

        os.link = fail_second_link
        try:
            write_note_outputs(
                staged_new, fixture_transcript,
                {"passed": verdict(structured_checks), **structured_checks},
                Path("fixture.json"), interrupted_output,
            )
            new_pair_rollback = False
        except OSError:
            new_pair_rollback = True
        finally:
            os.link = original_link
        new_pair_rollback = (
            new_pair_rollback
            and before_interrupted
            == {path.name for path in output_dir.iterdir()}
            and not interrupted_output.exists()
            and not interrupted_output.with_suffix(".note.json").exists()
        )

        replacement_before = {
            path: path.read_bytes()
            for path in written_paths
        }
        before_replacement = {path.name for path in output_dir.iterdir()}
        original_replace = os.replace

        def fail_second_replace(source, target):
            if (
                Path(target) == output_path
                and Path(source).name.endswith(".tmp")
            ):
                raise OSError("injected second replacement install failure")
            return original_replace(source, target)

        os.replace = fail_second_replace
        try:
            write_note_outputs(
                staged_new, fixture_transcript,
                {"passed": verdict(structured_checks), **structured_checks},
                Path("fixture.json"), output_path,
                replace=True,
            )
            replacement_rollback = False
        except OSError:
            replacement_rollback = True
        finally:
            os.replace = original_replace
        replacement_rollback = (
            replacement_rollback
            and before_replacement
            == {path.name for path in output_dir.iterdir()}
            and all(
                path.read_bytes() == content
                for path, content in replacement_before.items()
            )
            and validate_artifact_pair(
                written_doc, output_path.with_suffix(".note.json")
            ) == output_path
        )

        replaced_doc, _ = write_note_outputs(
            staged_new, fixture_transcript,
            {"passed": verdict(structured_checks), **structured_checks},
            Path("fixture.json"), output_path,
            replace=True,
        )
        replace_pair_ok = validate_artifact_pair(
            replaced_doc, output_path.with_suffix(".note.json")
        ) == output_path

        output_path.write_text("tampered Markdown\n", encoding="utf-8")
        try:
            validate_artifact_pair(
                replaced_doc, output_path.with_suffix(".note.json")
            )
            pair_tamper_refused = False
        except StructuredOutputError:
            pair_tamper_refused = True
        _atomic_replace_text(output_path, validate_note_render(replaced_doc))
        validate_artifact_pair(
            replaced_doc, output_path.with_suffix(".note.json")
        )

        broken_output = output_dir / "broken.md"
        broken_result = json.loads(json.dumps(staged_new))
        broken_result["evidence_contract"]["fragment_map_sha256"] = "0" * 64
        before_broken = {path.name for path in output_dir.iterdir()}
        try:
            write_note_outputs(
                broken_result, fixture_transcript,
                {"passed": verdict(structured_checks), **structured_checks},
                Path("fixture.json"), broken_output,
            )
            construction_refused = False
        except StructuredOutputError:
            construction_refused = True
        after_broken = {path.name for path in output_dir.iterdir()}
        construction_left_nothing = (
            before_broken == after_broken
            and not broken_output.exists()
            and not broken_output.with_suffix(".note.json").exists()
        )

        directory_output = output_dir / "directory.md"
        directory_output.mkdir()
        try:
            validate_output_target(directory_output, replace=True)
            directory_refused = False
        except StructuredOutputError:
            directory_refused = True
        directory_output.rmdir()
        symlink_target = output_dir / "symlink-target"
        symlink_target.write_text("not a note")
        symlink_output = output_dir / "symlink.md"
        symlink_output.symlink_to(symlink_target)
        try:
            validate_output_target(symlink_output)
            symlink_default_refused = False
        except StructuredOutputError:
            symlink_default_refused = True
        symlink_replace_explicit = (
            validate_output_target(symlink_output, replace=True)[0]
            == symlink_output
        )
        symlink_output.unlink()
        symlink_target.unlink()

        stale_output = output_dir / "stale.md"
        stale_output.with_suffix(".items.md").write_text(
            "retired transcript-derived evidence"
        )
        try:
            validate_output_target(stale_output)
            stale_sidecar_refused = False
        except StructuredOutputError:
            stale_sidecar_refused = True
    control(
        "Repair 4 writes a private, canonical Markdown/note JSON pair only",
        "extracted" not in staged_new
        and "extracted_records" not in staged_new
        and structured_doc["claim_evidence_contract"]
        == SOURCE_EVIDENCE_CONTRACT
        and written_names == actual_names
        == {"fixture.md", "fixture.note.json"}
        and pair_modes == {"fixture.md": 0o600, "fixture.note.json": 0o600}
        and pair_regenerates
        and target_conflict_refused
        and target_conflict_unchanged
        and new_pair_rollback
        and replacement_rollback
        and replace_pair_ok
        and pair_tamper_refused
        and construction_refused
        and construction_left_nothing
        and directory_refused
        and symlink_default_refused
        and symlink_replace_explicit
        and stale_sidecar_refused,
    )
    receipt_tampers = []
    tampered_schema = json.loads(json.dumps(structured_doc))
    tampered_schema["provenance"]["structured_stages"][0]["schema"][
        "tampered"
    ] = True
    tampered_schema["provenance"]["structured_stages"][0][
        "schema_sha256"
    ] = _json_sha256(
        tampered_schema["provenance"]["structured_stages"][0]["schema"]
    )
    receipt_tampers.append(tampered_schema)
    tampered_model = json.loads(json.dumps(structured_doc))
    tampered_model["provenance"]["structured_stages"][0][
        "model_digest"
    ] = "b" * 64
    receipt_tampers.append(tampered_model)
    tampered_cardinality = json.loads(json.dumps(structured_doc))
    tampered_cardinality["provenance"]["structured_stages"][0][
        "response_cardinality"
    ]["items"] += 1
    receipt_tampers.append(tampered_cardinality)
    tampered_input_contract = json.loads(json.dumps(structured_doc))
    tampered_input_contract["provenance"]["structured_stages"][-1][
        "input_contract_sha256"
    ] = "c" * 64
    receipt_tampers.append(tampered_input_contract)
    tampered_safe_claim = json.loads(json.dumps(structured_doc))
    safe_stage = tampered_safe_claim["provenance"]["structured_stages"][0]
    changed_safe = safe_stage["validated_response_json"].replace(
        "Choose and retain the exact encoding words",
        "A different retained extraction claim",
        1,
    )
    safe_stage["validated_response_json"] = changed_safe
    safe_stage["validated_response_sha256"] = _sha256(changed_safe)
    receipt_tampers.append(tampered_safe_claim)
    tampered_safe_order = json.loads(json.dumps(structured_doc))
    safe_stage = tampered_safe_order["provenance"]["structured_stages"][0]
    safe_doc = json.loads(safe_stage["validated_response_json"])
    item = safe_doc["items"][0]
    reordered_safe = json.dumps({
        "items": [{
            "claim": item["claim"],
            "label": item["label"],
            "source_fragment_ids": item["source_fragment_ids"],
        }],
    }, separators=(",", ":"))
    safe_stage["validated_response_json"] = reordered_safe
    safe_stage["validated_response_sha256"] = _sha256(reordered_safe)
    receipt_tampers.append(tampered_safe_order)
    receipt_tampers_refused = True
    for candidate in receipt_tampers:
        try:
            structured_artifact_citations(candidate, fixture_transcript)
            receipt_tampers_refused = False
        except StructuredOutputError:
            pass
    control(
        "tampered stage schema, model, counts, inputs, safe claims, or key order fails recheck",
        receipt_tampers_refused,
    )
    narrative_runtime = json.loads(json.dumps(staged_new))
    narrative_runtime["note"] += "\nMODEL-AUTHORED NARRATIVE"
    narrative_artifact = json.loads(json.dumps(structured_doc))
    narrative_artifact["note"] += "\nMODEL-AUTHORED NARRATIVE"
    narrative_refused = True
    for candidate, validator in (
        (narrative_runtime, lambda value: structured_citations(
            value, fixture_transcript
        )),
        (narrative_artifact, lambda value: structured_artifact_citations(
            value, fixture_transcript
        )),
    ):
        try:
            validator(candidate)
            narrative_refused = False
        except StructuredOutputError:
            pass
    control(
        "no model-authored narrative can survive beside evidence-covered records",
        narrative_refused,
    )
    coordinated_claim = json.loads(json.dumps(structured_doc))
    original_claim = coordinated_claim["claims"][0]["claim"]
    changed_claim = "A coordinated but unsupported replacement claim"
    coordinated_claim["note"] = coordinated_claim["note"].replace(
        original_claim, changed_claim, 1
    )
    coordinated_claim["claims"][0]["claim"] = changed_claim
    coordinated_claim["claims"][0]["claim_sha256"] = _sha256(changed_claim)
    try:
        structured_artifact_citations(coordinated_claim, fixture_transcript)
        coordinated_claim_refused = False
    except StructuredOutputError:
        coordinated_claim_refused = True
    control(
        "changing Markdown and claims together cannot outrun the durable claim digest",
        coordinated_claim_refused,
    )
    recall_was_called = False
    original_check_recall = check_recall

    def forbidden_recall(*_args, **_kwargs):
        nonlocal recall_was_called
        recall_was_called = True
        raise AssertionError("recall ran before structured evidence validation")

    globals()["check_recall"] = forbidden_recall
    malformed_runtime_refused = True
    for mutation in (
        "wrong digest", "empty graph", "removed graph",
        "heading only", "runtime signature only",
    ):
        malformed_runtime = json.loads(json.dumps(staged_new))
        if mutation == "wrong digest":
            malformed_runtime["evidence_contract"]["fragment_map_sha256"] = "0" * 64
        elif mutation == "empty graph":
            malformed_runtime["evidence_contract"] = {}
        elif mutation == "removed graph":
            del malformed_runtime["evidence_contract"]
        else:
            for key in (
                "claim_evidence_contract", "evidence_contract",
                "consolidated_records", "structured_provenance",
                "structured_contract",
            ):
                malformed_runtime.pop(key, None)
            if mutation == "heading only":
                malformed_runtime.pop("model_identity", None)
                malformed_runtime.pop("slices", None)
            else:
                malformed_runtime["note"] = malformed_runtime["note"].replace(
                    STRUCTURED_NOTE_CONTRACT["heading"], "## Damaged heading", 1
                )
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                report(
                    malformed_runtime, fixture_transcript, [], None, 32768,
                    ["A reference item that would otherwise invoke the judge"],
                )
            malformed_runtime_refused = False
        except SystemExit:
            pass
    globals()["check_recall"] = original_check_recall
    control(
        "damaged or stripped runtime evidence is refused before any recall-model work",
        malformed_runtime_refused and not recall_was_called,
    )
    support_prompt = _support_judge_prompt(
        "Retain exact evidence", "we should retain the exact evidence", "proposal"
    )
    control(
        "support provenance can bind the exact typed claim and evidence prompt",
        support_prompt.startswith("CLAIM:\nPROPOSAL: Retain exact evidence")
        and _sha256(support_prompt)
        != _sha256(_support_judge_prompt(
            "Retain exact evidence", "different words", "proposal"
        ))
        and re.fullmatch(r"[0-9a-f]{64}", _sha256(SUPPORT_JUDGE)) is not None,
    )
    support_doc = json.loads(json.dumps(structured_doc))
    support_claim = support_doc["claims"][0]
    support_evidence, support_fragment_ids = _claim_evidence_text(
        support_claim, fixture_transcript
    )
    fixture_cases = _support_fixture_cases()

    def fixture_receipts(use_expected: bool) -> list[dict]:
        rows = []
        for index, (item, want) in enumerate(fixture_cases, 1):
            claim, quote, kind = _support_fixture_prompt(item)
            answer = want if use_expected else True
            response = "YES" if answer else "NO"
            rows.append({
                "fixture_id": f"support-fixture-{index:02d}",
                "judge_input_sha256": _sha256(
                    _support_judge_prompt(claim, quote, kind)
                ),
                "expected": want,
                "judge_response": response,
                "judge_response_sha256": _sha256(response),
                "supports": answer,
            })
        return rows

    calibration_receipts = fixture_receipts(True)
    control_receipts = fixture_receipts(False)
    control_right = sum(
        receipt["supports"] == want
        for receipt, (_, want) in zip(control_receipts, fixture_cases, strict=True)
    )
    fixture_total = len(fixture_cases)
    support_doc["support"] = {
        "schema": "support-measurement/1",
        "judge": fixture_identity["requested"],
        "judge_identity": fixture_identity,
        "judge_system_sha256": _sha256(SUPPORT_JUDGE),
        "control_system_sha256": _sha256(SABOTAGED_SUPPORT_JUDGE),
        "fixture_set_sha256": _sha256(json.dumps(
            SUPPORT_FIXTURES, ensure_ascii=False, separators=(",", ":")
        )),
        "options": {"num_ctx": 32768, "temperature": 0.0},
        "calibration": f"{fixture_total}/{fixture_total}",
        "control": f"{control_right}/{fixture_total}",
        "calibration_receipts": calibration_receipts,
        "control_receipts": control_receipts,
        "verdicts": [{
            "claim": support_claim["claim"],
            "quote": support_claim["quote"],
            "type": support_claim["type"],
            "supports": True,
            "judge_response": "YES",
            "judge_response_sha256": _sha256("YES"),
            "judge_input_sha256": _sha256(_support_judge_prompt(
                support_claim["claim"], support_evidence, support_claim["type"]
            )),
            "source_item_ids": support_claim["source_item_ids"],
            "source_fragment_ids": support_fragment_ids,
            "evidence_set_sha256": _sha256(support_evidence),
        }],
    }
    valid_support = validate_support_measurement(
        support_doc, fixture_transcript
    ) is support_doc["support"]
    valid_support_payload = json.loads(json.dumps(support_doc["support"]))
    support_surface_tamper = json.loads(json.dumps(support_doc))
    support_surface_tamper["note"] = support_surface_tamper["note"].replace(
        support_claim["claim"], changed_claim, 1
    )
    support_surface_tamper["claims"][0]["claim"] = changed_claim
    support_surface_tamper["claims"][0]["claim_sha256"] = _sha256(changed_claim)
    try:
        validate_support_measurement(
            support_surface_tamper, fixture_transcript
        )
        support_surface_tamper_refused = False
    except StructuredOutputError:
        support_surface_tamper_refused = True
    support_doc["support"]["verdicts"][0]["supports"] = False
    try:
        validate_support_measurement(support_doc, fixture_transcript)
        changed_support_refused = False
    except StructuredOutputError:
        changed_support_refused = True
    control(
        "displayed support is re-derived from model, calibration, prompt, and evidence receipts",
        valid_support and changed_support_refused
        and support_surface_tamper_refused,
    )
    with tempfile.TemporaryDirectory(prefix="repair4-support-write-") as tmp:
        support_markdown = Path(tmp) / "fixture.md"
        persisted_support_doc, _ = write_note_outputs(
            staged_new, fixture_transcript,
            {"passed": verdict(structured_checks), **structured_checks},
            Path("fixture.json"), support_markdown,
        )
        persisted_support_doc["support"] = valid_support_payload
        support_artifact = support_markdown.with_suffix(".note.json")
        _write_support_measurement(
            support_artifact, persisted_support_doc, fixture_transcript
        )
        support_before_invalid = support_artifact.read_bytes()
        invalid_support_doc = json.loads(json.dumps(persisted_support_doc))
        invalid_support_doc["support"]["verdicts"][0]["supports"] = False
        try:
            _write_support_measurement(
                support_artifact, invalid_support_doc, fixture_transcript
            )
            invalid_support_write_refused = False
        except StructuredOutputError:
            invalid_support_write_refused = True
        support_write_ok = (
            support_artifact.stat().st_mode & 0o777 == 0o600
            and validate_artifact_pair(
                persisted_support_doc, support_artifact
            ) == support_markdown
            and json.loads(support_artifact.read_text())["support"]
            == valid_support_payload
            and invalid_support_write_refused
            and support_artifact.read_bytes() == support_before_invalid
        )
    control(
        "support persistence is private, atomic, pair-checked, and validates before write",
        support_write_ok,
    )
    empty_artifact = json.loads(json.dumps(structured_doc))
    empty_artifact["evidence"] = {}
    removed_artifact = json.loads(json.dumps(structured_doc))
    del removed_artifact["evidence"]
    stripped_artifact = json.loads(json.dumps(structured_doc))
    del stripped_artifact["claim_evidence_contract"]
    del stripped_artifact["evidence"]
    for key in ("source_evidence", "structured_stages", "structured_contract"):
        stripped_artifact["provenance"].pop(key, None)
    for claim in stripped_artifact["claims"]:
        for key in (
            "source_item_ids", "source_claim_sha256s", "claim_sha256",
            "evidence_refs",
        ):
            claim.pop(key, None)
    stripped_identity_artifact = json.loads(json.dumps(stripped_artifact))
    stripped_identity_artifact["provenance"].pop("model_identity", None)
    authority_only_artifact = json.loads(json.dumps(stripped_identity_artifact))
    authority_only_artifact["note"] = authority_only_artifact["note"].replace(
        STRUCTURED_NOTE_CONTRACT["heading"], "## Damaged heading", 1
    )
    authority_only_artifact["checks"]["citations"]["authority"] = "damaged"
    artifact_downgrades_refused = (
        artifact_uses_source_evidence(empty_artifact)
        and artifact_uses_source_evidence(removed_artifact)
        and artifact_uses_source_evidence(stripped_artifact)
        and artifact_uses_source_evidence(stripped_identity_artifact)
        and artifact_uses_source_evidence(authority_only_artifact)
    )
    for damaged in (
        empty_artifact, removed_artifact, stripped_artifact,
        stripped_identity_artifact, authority_only_artifact,
    ):
        try:
            structured_artifact_citations(damaged, fixture_transcript)
            artifact_downgrades_refused = False
        except StructuredOutputError:
            pass
    control(
        "empty, removed, or stripped Repair 4 graph/provenance cannot downgrade to legacy",
        artifact_downgrades_refused,
    )
    different_evidence = {
        **structured_doc["claims"][0],
        "evidence_refs": [{
            **structured_doc["claims"][0]["evidence_refs"][0],
            "source_fragment_id": "different",
        }],
    }
    control(
        "support identity includes the complete declared evidence set",
        _support_key(structured_doc["claims"][0])
        != _support_key(different_evidence),
    )
    tampered = json.loads(json.dumps(structured_doc))
    tampered["evidence"]["consolidated_items"][0]["source_fragment_ids"].reverse()
    try:
        structured_artifact_citations(tampered, fixture_transcript)
        tamper_refused = False
    except StructuredOutputError:
        tamper_refused = True
    control("a reordered durable evidence union fails recheck", tamper_refused)
    digest_tampers_refused = True
    for field in ("claim_sha256", "source_claim_sha256s"):
        damaged = json.loads(json.dumps(structured_doc))
        row = damaged["evidence"]["consolidated_items"][0]
        if field == "claim_sha256":
            row[field] = "d" * 64
        else:
            row[field][0] = "e" * 64
        try:
            structured_artifact_citations(damaged, fixture_transcript)
            digest_tampers_refused = False
        except StructuredOutputError:
            pass
    extraction_digests = Counter(
        row["claim_sha256"]
        for row in structured_doc["evidence"]["extraction_items"]
    )
    covered_digests = Counter(
        digest
        for row in structured_doc["evidence"]["consolidated_items"]
        for digest in row["source_claim_sha256s"]
    )
    control(
        "output and member claim digests fail closed and cover every extraction claim once",
        digest_tampers_refused and extraction_digests == covered_digests,
    )

    # The same source fragment may be selected independently in overlapping slices.
    # Record coverage, not fragment uniqueness across the meeting, is the invariant.
    overlap_evidence = json.loads(json.dumps(structured_doc["evidence"]))
    first_input = overlap_evidence["extraction_items"][0]
    overlap_evidence["extraction_items"].append({
        "evidence_item_id": "slice-0002-item-0001",
        "slice_ordinal": 2,
        "source_fragment_ids": list(first_input["source_fragment_ids"]),
        "label": first_input["label"],
        "claim_sha256": first_input["claim_sha256"],
    })
    overlap_evidence["consolidated_items"][0]["source_item_ids"].append(
        "slice-0002-item-0001"
    )
    overlap_evidence["consolidated_items"][0]["source_claim_sha256s"].append(
        first_input["claim_sha256"]
    )
    overlap_resolved = validate_evidence_contract(
        overlap_evidence, fixture_transcript
    )
    control(
        "overlap may repeat a fragment across extraction records while covering each record once",
        len(overlap_resolved) == 1
        and len(overlap_resolved[0]["source_item_ids"]) == 2
        and len(overlap_resolved[0]["evidence_refs"]) == 2,
    )

    structured_verdict = dict(stored, extraction={"applies": True, "ok": False})
    structured_verdict_fails = verdict(structured_verdict) is False
    failures += not structured_verdict_fails
    print(f"  [{'pass' if structured_verdict_fails else 'FAIL'}] a refused structured "
          "stage fails the run verdict")

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
    transform = p.add_mutually_exclusive_group()
    transform.add_argument(
        "--strip", action="store_true",
        help="remove speaker labels, testing the unattributed contract",
    )
    transform.add_argument(
        "--simulate-bleed", action="store_true",
        help="remove labels AND double every line, as a contaminated capture arrives",
    )
    transform.add_argument(
        "--as-channel", metavar="SPEAKER", nargs="?", const=True,
        help="collapse to the Me/Them split a clean headphone capture produces",
    )
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
    p.add_argument(
        "--replace", action="store_true",
        help="replace both existing --out Markdown and note JSON explicitly",
    )
    p.add_argument("--measure-support", type=Path, nargs="+", metavar="NOTE.JSON",
                   help="judge whether each located quote supports the claim it is "
                        "attached to; calibrates the judge first and reports no figure "
                        "if it fails")
    p.add_argument("--recheck", type=Path, nargs="+", metavar="NOTE.JSON",
                   help="re-derive the citation check for note/1 or note/2 artifacts "
                        "without calling a model, and rewrite them in place")
    p.add_argument("--reference", type=Path,
                   help="a list of expected items to measure recall against "
                        "(a platform's own action items, or a human's notes)")
    args = p.parse_args()

    if args.replace and args.out is None:
        p.error("--replace requires --out")
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

    try:
        validate_inference_options(args.model, args.num_ctx, args.timeout)
        if args.passes == 2:
            validate_chunking(args.chunk_words, args.overlap_words)
    except StructuredOutputError as e:
        p.error(str(e))

    if not args.transcript.exists():
        raise SystemExit(
            f"{args.transcript} not found.\n"
            "Fetch the evaluation corpus first:  python notes/fetch_corpus.py"
        )

    # Checked here rather than where it is written, which is after the model work.
    # `--out notes/out` cost six minutes of local inference on a 1365-turn meeting and
    # then died on the last statement, and because `report` had already printed, the
    # log ended in a full set of checks and looked like a run that had succeeded. Every
    # precondition that can be tested without spending anything belongs before the
    # spending, not beside the use.
    if args.out and args.out.is_dir():
        raise SystemExit(f"--out takes a file, and {args.out} is a directory. "
                         f"Try --out {args.out / args.transcript.stem}.md")
    if args.out:
        try:
            validate_output_target(args.out, replace=args.replace)
        except StructuredOutputError as e:
            raise SystemExit(str(e)) from e

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
        transform = ("simulate-bleed" if args.simulate_bleed
                     else "as-channel" if args.as_channel
                     else "strip" if args.strip else None)
        doc, (markdown, artifact) = write_note_outputs(
            result, t, checks, args.transcript, args.out, transform,
            replace=args.replace,
        )
        print(f"\n  wrote {markdown}")
        by_status = Counter(c["status"] for c in doc["claims"])
        print(f"  wrote {artifact} ({len(doc['claims'])} claims: "
              f"{', '.join(f'{n} {s}' for s, n in by_status.most_common()) or 'none'})")

    return 0 if checks["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())

"""The transcript format that sits between capture and notes.

One shape, three attribution levels, because how much the notes are allowed to
claim depends entirely on how the audio was captured:

    named    Real participants are known. A bot was in the call, or the meeting
             UI was scraped, or the transcript came from a corpus that has them.
             Notes may say "Marketing agreed to X".

    channel  Only the capture topology is known: one leg is the microphone (the
             operator) and one is the system (everyone else). Notes may say
             "you agreed to X", but nobody on the far side can be named.

    none     Speaker identity is not recoverable. This is what `bleed-detected`
             means in docs/screens-and-states.md: the microphone was hearing the
             speakers, both legs carry the same words, and the split is fiction.
             Notes must be written without actors.

The levels are not a quality gradient to be papered over. They are three
different contracts about what the notes are permitted to assert, and the
summarizer enforces a different one for each.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

NAMED = "named"
CHANNEL = "channel"
NONE = "none"
LEVELS = (NAMED, CHANNEL, NONE)


@dataclass
class Turn:
    text: str
    speaker: str | None = None
    start: float | None = None


@dataclass
class Transcript:
    source: str
    attribution: str
    turns: list[Turn] = field(default_factory=list)

    def __post_init__(self):
        if self.attribution not in LEVELS:
            raise ValueError(f"attribution must be one of {LEVELS}, got {self.attribution!r}")

    @property
    def speakers(self) -> list[str]:
        return sorted({t.speaker for t in self.turns if t.speaker})

    def render(self) -> str:
        """The transcript as the model sees it.

        At `none` the speaker fields are not merely ignored, they are dropped —
        the model cannot leak an attribution it was never shown. This is the
        difference between instructing a model not to do something and making it
        unable to; the mechanical checks in summarize.py depend on the latter.
        """
        lines = []
        for t in self.turns:
            if self.attribution == NONE or not t.speaker:
                lines.append(f"- {t.text}")
            else:
                lines.append(f"{t.speaker}: {t.text}")
        return "\n".join(lines)

    def strip_attribution(self) -> "Transcript":  # noqa: UP037
        """The same words with every speaker label removed.

        Tests the `none` contract on material where the true answer is known.
        Note what this does *not* reproduce — see `simulate_bleed`.
        """
        return Transcript(
            source=f"{self.source} (labels stripped)",
            attribution=NONE,
            turns=[Turn(text=t.text, start=t.start) for t in self.turns],
        )

    def as_channel(self, me: str | None = None) -> "Transcript":  # noqa: UP037
        """Collapse named speakers to the Me/Them split a clean capture produces.

        This is the level the recommended setup actually yields: headphones mean
        low bleed, low bleed means the legs stay independent, and the capture
        writes `channel`. Testing only `named` and `none` would leave the
        default path unexercised.

        One speaker becomes "Me" — the person holding the microphone — and every
        other speaker collapses into a single undifferentiated "Them", which is
        precisely what the system leg is. The far side is not four people to the
        capture; it is one audio stream.
        """
        me = me or (self.speakers[0] if self.speakers else None)
        return Transcript(
            source=f"{self.source} (as channel, Me={me})",
            attribution=CHANNEL,
            turns=[
                Turn(text=t.text, start=t.start,
                     speaker="Me" if t.speaker == me else "Them")
                for t in self.turns
            ],
        )

    def simulate_bleed(self) -> "Transcript":  # noqa: UP037
        """What a bleed-contaminated capture actually looks like.

        Removing the labels is only half of it. When the microphone is hearing
        the speakers, both legs transcribe the same speech, so every utterance
        reaches the summarizer TWICE — adjacent, near-identical, and with no
        label to explain why. The spike measured +0.93 envelope correlation
        doing exactly this (spike/RESULTS.md), and its transcript showed each
        sentence once as "Me" and once as "Them".

        A summarizer that only ever saw label-stripped input has not been tested
        against the condition the capture spike proved is the default on
        speakers. It has been tested against a tidier problem.

        The duplicate is placed adjacent to its original because that is where
        the timestamp merge puts it — the acoustic path is tens of milliseconds.
        """
        doubled = []
        for t in self.turns:
            doubled.append(Turn(text=t.text, start=t.start))
            doubled.append(Turn(text=t.text, start=t.start))
        return Transcript(
            source=f"{self.source} (bleed simulated: unlabelled, every line doubled)",
            attribution=NONE,
            turns=doubled,
        )


# Utterances the corpora annotate but nobody said. Left in, they become several
# hundred lines of noise the model has to read past.
_NON_SPEECH = {"{vocalsound}", "{gap}", "{disfmarker}", "{pause}", "{nonvocalsound}", "{comment}"}


def _clean(text: str) -> str:
    for token in _NON_SPEECH:
        text = text.replace(token, " ")
    return " ".join(text.split())


def load_qmsum(path: Path) -> Transcript:
    """A QMSum meeting: real speech, real speakers, and a human reference summary.

    QMSum (Zhong et al., 2021) repackages the AMI and ICSI meeting corpora plus
    parliamentary committee transcripts, each with human-written summaries. The
    human summary is what makes this an evaluation rather than a demo.
    """
    data = json.loads(path.read_text())
    turns = [
        Turn(text=_clean(t["content"]), speaker=t["speaker"])
        for t in data["meeting_transcripts"]
        if _clean(t["content"])
    ]
    return Transcript(source=f"qmsum:{path.stem}", attribution=NAMED, turns=turns)


def qmsum_reference(path: Path) -> dict:
    """The human-written summary and topic list shipped alongside the transcript."""
    data = json.loads(path.read_text())
    general = data.get("general_query_list") or []
    return {
        "summary": general[0]["answer"] if general else "",
        "topics": [t["topic"] for t in data.get("topic_list", [])],
    }


def load_capture(path: Path) -> Transcript:
    """A transcript written by spike/dual_capture.py.

    The capture records its own bleed measurement, so the attribution level is
    read from the file rather than assumed here. A capture that measured high
    bleed arrives as `none` and gets the unattributed contract automatically.
    """
    data = json.loads(path.read_text())
    return Transcript(
        source=data.get("source", path.stem),
        attribution=data["attribution"],
        turns=[
            Turn(text=t["text"], speaker=t.get("speaker"), start=t.get("start"))
            for t in data["turns"]
        ],
    )


# A Meet transcript line opens a turn with one to four capitalised name words
# and a colon. Matched conservatively so that ordinary mid-sentence colons
# ("the problem is this: nobody updates it") do not read as a new speaker.
_MEET_SPEAKER = re.compile(r"^([A-Z][\w.'-]*(?: [A-Z][\w.'-]*){0,3}): ?(.*)$")
_MEET_CLOCK = re.compile(r"^(\d{2}):(\d{2}):(\d{2})\s*$")
_MEET_END = "Transcription ended after"


def load_meet(path: Path) -> Transcript:
    """A Google Meet transcript, as exported or lifted out of a Gemini notes PDF.

    Meet is a primary target for this tool, so parsing its export belongs in the
    repository even though no Meet transcript ever will — every one of them is
    somebody's actual meeting.

    Three things about the format matter downstream:

    Turns wrap across lines. A line without a `Name:` prefix continues the
    previous speaker rather than starting a new turn, so joining has to be
    stateful; splitting on newlines shatters sentences mid-clause.

    Timestamps arrive as their own line every minute or so, not per turn. Each
    turn takes the last clock seen, which makes `start` accurate to roughly the
    gap between markers — fine for ordering, useless for alignment.

    Overlapping speech is interleaved, not merged. Meet emits each speaker's
    words in the order it resolved them, so a crosstalk moment arrives as
    fragments alternating between speakers mid-sentence. That is real ASR output
    and it is left exactly as it is: repairing it here would hide the input the
    summarizer actually has to survive.
    """
    lines = path.read_text().splitlines()

    start_at = next(
        (i for i, line in enumerate(lines) if _MEET_CLOCK.match(line)), None
    )
    if start_at is None:
        raise ValueError(f"{path}: no Meet transcript found (expected a HH:MM:SS marker)")

    turns: list[Turn] = []
    clock = 0.0
    for line in lines[start_at:]:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(_MEET_END):
            break
        if m := _MEET_CLOCK.match(stripped):
            h, mnt, s = (int(g) for g in m.groups())
            clock = h * 3600 + mnt * 60 + s
            continue
        if m := _MEET_SPEAKER.match(stripped):
            turns.append(Turn(text=m.group(2).strip(), speaker=m.group(1), start=clock))
        elif turns:
            turns[-1].text = f"{turns[-1].text} {stripped}".strip()

    turns = [t for t in turns if t.text]
    if not turns:
        raise ValueError(f"{path}: transcript section found but no speaker turns in it")
    return Transcript(source=f"meet:{path.stem}", attribution=NAMED, turns=turns)


def load(path: Path) -> Transcript:
    """Dispatch on file shape rather than on a flag the caller has to remember."""
    raw = path.read_text()
    try:
        data = json.loads(raw)
    except ValueError:
        return load_meet(path)
    if "meeting_transcripts" in data:
        return load_qmsum(path)
    if "turns" in data:
        return load_capture(path)
    raise ValueError(f"{path}: not a QMSum meeting, a capture, or a Meet transcript")

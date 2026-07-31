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
import sys
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "spike"))

from capture_health import TRANSCRIPT_SCHEMA as CAPTURE_TRANSCRIPT_SCHEMA
from capture_health import UNKNOWN_WARNING as CAPTURE_INTEGRITY_UNKNOWN_WARNING
from capture_health import validate as validate_capture_health
from capture_health import warning as capture_health_warning

NAMED = "named"
CHANNEL = "channel"
NONE = "none"
LEVELS = (NAMED, CHANNEL, NONE)
FILE_TRANSCRIPT_SCHEMA = "file-transcript/1"


@dataclass
class Turn:
    text: str
    speaker: str | None = None
    start: float | None = None


@dataclass
class Transcript:
    source: str
    attribution: str
    # Only what the model may see. Turns the capture's voiceprint gate marked as not
    # the operator are NOT in here — they are in `gated_turns`, and the separation is
    # structural on purpose.
    #
    # The first version of this filtered gated turns inside `render()` and left them
    # in `turns`, which put the obligation to remember on every transform. It was
    # already broken when written: `strip_attribution` rebuilds each Turn to drop the
    # speaker, so `--strip` reconstructed the room's speech without the mark and fed
    # it back to the model. `as_channel` and `simulate_bleed` rebuild turns too, and
    # `chunk_transcript` sizes windows by counting them.
    #
    # This is the same argument the attribution contract already makes one line down:
    # the difference between instructing something not to happen and making it unable
    # to. Four call sites remembering a rule is an instruction. A field they cannot
    # reach is a fact.
    turns: list[Turn] = field(default_factory=list)
    # The gated turns themselves, kept so the operator can overrule a gate that
    # removed a colleague. Derived views carry them as provenance but never move
    # them into `turns`, so no attribution or bleed transform can feed them back to
    # the model.
    gated_turns: list[Turn] = field(default_factory=list)
    # What the capture's voiceprint gate did, when there was one. Carried through
    # rather than dropped at the loader because the gate can delete a co-located
    # participant, and `docs/screens-and-states.md` requires that warning to reach
    # the post-meeting note. It never influences the prompt — a summarizer must not
    # be told that words are missing, only the human reading the result.
    gate: dict | None = None
    # Whether the capture itself met its integrity floor. This is separate from
    # voiceprint gating: a driver dropout or tap failure qualifies every word in the
    # transcript, and moving the transcript away from session.json must not erase
    # that fact. Like `gate`, it never becomes model input.
    capture_health: dict | None = None
    # A schema-less dual-capture transcript predates persisted integrity evidence.
    # It remains readable as evidence, but every derived view and note has to carry
    # the fact that completeness cannot be established.
    capture_integrity_unknown: bool = False

    def __post_init__(self):
        if self.attribution not in LEVELS:
            raise ValueError(f"attribution must be one of {LEVELS}, got {self.attribution!r}")
        if not isinstance(self.capture_integrity_unknown, bool):
            raise ValueError("capture_integrity_unknown must be boolean")
        if self.capture_health is not None:
            validate_capture_health(self.capture_health, transcript_context=True)

    @property
    def gate_warnings(self) -> list[str]:
        """Anything about the gate a human reading these notes has to be told."""
        g = self.gate
        if not g:
            return []
        out = []
        if g.get("persistent_other"):
            share, secs = g.get("coherent_share") or 0, g.get("rejected_seconds") or 0
            out.append(
                f"the capture's voiceprint gate removed ~{share * secs:.0f}s of one "
                f"recurring voice ({share:.0%} of everything it dropped). If that was "
                f"a participant, these notes are missing their words.")
        elif g.get("rejected"):
            out.append(
                f"the voiceprint gate removed {g['rejected']} segment(s), "
                f"{g.get('rejected_seconds', 0)}s, as not the operator"
                + (f", {g['borderline']} of them close calls" if g.get("borderline")
                   else ""))
        if g.get("applied") is False and g.get("why"):
            out.append(f"the voiceprint gate did not run: {g['why']}. Speech from the "
                       f"room, if there was any, is in this transcript.")
        return out

    @property
    def health_warnings(self) -> list[str]:
        """Capture failures a human must see before treating omissions as silence."""
        out = (
            [CAPTURE_INTEGRITY_UNKNOWN_WARNING]
            if self.capture_integrity_unknown else []
        )
        if self.capture_health is not None:
            warning = capture_health_warning(
                self.capture_health, transcript_context=True
            )
            if warning:
                out.append(warning)
        return out

    @property
    def capture_warnings(self) -> list[str]:
        """All capture provenance that must reach the note and its reader."""
        return self.health_warnings + self.gate_warnings

    @property
    def speakers(self) -> list[str]:
        return sorted({t.speaker for t in self.turns if t.speaker})

    def render(self) -> str:
        """The transcript as the model sees it.

        At `none` the speaker fields are not merely ignored, they are dropped —
        the model cannot leak an attribution it was never shown. This is the
        difference between instructing a model not to do something and making it
        unable to; the mechanical checks in summarize.py depend on the latter.

        Gated turns need no filtering here: they are not in `turns` at all. See the
        field comment for why that is structural rather than a convention.
        """
        lines = []
        for t in self.turns:
            if self.attribution == NONE or not t.speaker:
                lines.append(f"- {t.text}")
            else:
                lines.append(f"{t.speaker}: {t.text}")
        return "\n".join(lines)

    def _derived(self, *, source: str, attribution: str, turns: list[Turn]) -> Transcript:
        """Make a transformed view without discarding capture provenance.

        `turns` is deliberately the only part a transform may change.  The gate
        report and its withheld turns are not prompt input, but they are evidence
        for the person reading the resulting note.  Rebuilding a Transcript with
        just visible turns used to make a simulated or label-stripped run read as
        though no voiceprint gate had run at all.
        """
        return Transcript(
            source=source,
            attribution=attribution,
            turns=turns,
            gated_turns=[Turn(text=t.text, speaker=t.speaker, start=t.start)
                         for t in self.gated_turns],
            gate=deepcopy(self.gate),
            capture_health=deepcopy(self.capture_health),
            capture_integrity_unknown=self.capture_integrity_unknown,
        )

    def strip_attribution(self) -> "Transcript":  # noqa: UP037
        """The same words with every speaker label removed.

        Tests the `none` contract on material where the true answer is known.
        Note what this does *not* reproduce — see `simulate_bleed`.
        """
        return self._derived(
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
        return self._derived(
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
        return self._derived(
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
    schema = data.get("schema")
    if schema is None:
        integrity_unknown = True
    elif schema == CAPTURE_TRANSCRIPT_SCHEMA:
        integrity_unknown = False
    else:
        raise ValueError(f"{path}: unknown capture transcript schema {schema!r}")
    health = data.get("capture_health")
    if schema == CAPTURE_TRANSCRIPT_SCHEMA and health is None:
        raise ValueError(
            f"{path}: {CAPTURE_TRANSCRIPT_SCHEMA} requires capture_health"
        )
    if health is not None:
        try:
            validate_capture_health(health, transcript_context=True)
        except ValueError as exc:
            raise ValueError(f"{path}: invalid capture_health: {exc}") from None

    def turn(t: dict) -> Turn:
        return Turn(text=t["text"], speaker=t.get("speaker"), start=t.get("start"))

    # Split at the boundary, once. Everything downstream operates on `turns` and
    # therefore cannot leak a gated turn into a prompt, however it reshapes them.
    return Transcript(
        source=data.get("source", path.stem),
        attribution=data["attribution"],
        turns=[turn(t) for t in data["turns"] if not t.get("gated")],
        gated_turns=[turn(t) for t in data["turns"] if t.get("gated")],
        gate=data.get("voiceprint"),
        capture_health=health,
        capture_integrity_unknown=integrity_unknown,
    )


def load_file_transcript(path: Path) -> Transcript:
    """A single mixed recording transcribed without dual-capture provenance."""
    data = json.loads(path.read_text())
    schema = data.get("schema")
    legacy = schema is None and str(data.get("source", "")).startswith("recording:")
    if schema != FILE_TRANSCRIPT_SCHEMA and not legacy:
        raise ValueError(f"{path}: unknown file transcript schema {schema!r}")
    if data.get("attribution") != NONE:
        raise ValueError(
            f"{path}: a mixed file transcript must use {NONE!r} attribution"
        )
    if data.get("capture_health") is not None:
        raise ValueError(
            f"{path}: a mixed file transcript cannot claim dual-capture health"
        )

    def turn(t: dict) -> Turn:
        return Turn(text=t["text"], speaker=t.get("speaker"), start=t.get("start"))

    return Transcript(
        source=data.get("source", path.stem),
        attribution=NONE,
        turns=[turn(t) for t in data["turns"]],
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
        if (
            data.get("schema") == FILE_TRANSCRIPT_SCHEMA
            or (
                data.get("schema") is None
                and str(data.get("source", "")).startswith("recording:")
            )
        ):
            return load_file_transcript(path)
        return load_capture(path)
    raise ValueError(f"{path}: not a QMSum meeting, a capture, or a Meet transcript")

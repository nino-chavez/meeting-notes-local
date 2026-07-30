"""Renders the J1 retrieval prototype from real note artifacts.

`docs/journeys.md` chose to design C → B → A and named two things worth
prototyping: J1's retrieval path, and the note format. This builds both, and it is
a *generator* rather than a page for two reasons that are not stylistic.

**The populated page cannot be committed.** Its content is derived from QMSum,
which is third-party data under someone else's licence — `.gitignore` already keeps
`notes/corpus/` and `notes/out/` out of the repo and `notes/fetch_corpus.py`
fetches on demand. So the reproducible thing is the renderer; the artifact is local.

**A prototype must not invent content.** `journeys.md`: "A prototype needs real
content or it settles nothing", and the operator's own recorded objection — "so
where is the content I use for reviewing with 630?" — is what the alternative looks
like from outside. Every claim, quote, turn and count on the page is read from a
`note/1` or `note/2` artifact that a real model run produced. Nothing here composes
a meeting.

**What it therefore cannot show, it labels.** film-room's Decision 0047 records the
operator opening a shell with placeholder interiors and reasonably mistaking one for
a broken folder chooser. The conclusion drawn there is that a fixture cannot serve as
an operator encounter. So each region on this page states whether it is real data, a
component specimen with a stated contract, or an open question — and the regions the
corpus cannot populate say so in place rather than being quietly dropped.

Legacy `note/1` artifacts remain readable. Repair 4 uses `note/2`; its JSON is the
canonical note and its sibling Markdown must match the retained render digest before
the prototype will use either surface.

Run:  python docs/prototype/build.py            # reads notes/out/*.note.json
"""

from __future__ import annotations

import html
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "notes"))

from summarize import (  # noqa: E402
    NOTE_SCHEMAS,
    _seq,
    _support_key,
    artifact_uses_source_evidence,
    structured_artifact_citations,
    validate_artifact_pair,
    validate_evidence_contract,
    validate_support_measurement,
)
from transcript import load  # noqa: E402  (needs the path above)

sys.path.insert(0, str(REPO / "spike"))

from speaker_gate import operating_point_choices  # noqa: E402

OUT_DIR = REPO / "notes" / "out"

# Read from DESIGN.md rather than restated here. A prototype that hardcodes its own
# palette is the free-picked-palette failure with extra steps, and this project's
# tokens carry a constraint no generic palette does: the accent means live capture
# and must not appear on any surface in this file.
DESIGN = REPO / "DESIGN.md"

# The four evidence states, from `notes/summarize.py`. Each carries a mark and a word
# as well as a color, because `DIRECTION.md` forbids state carried by color alone —
# "pair state word/icon with color" — and because at a glance the mark is what
# separates two states that share the neutral hue.
#
# `composed` takes `semantic-error` under DESIGN.md's rule that a warning needing
# color is an error. The two neutral states take `semantic-warning`, which resolves to
# neutral-300 on purpose: an amber warning would collide with the live indicator.
STATES = {
    # `semantic-info`, not `semantic-success`. Success is a verdict and this is not one:
    # measured on this corpus, **6 of 31 located quotes actually support the claim they
    # are attached to** — action items 0 of 8. A green tick on a state that means only
    # "the words exist at this turn" told the reader the claim had passed something, and
    # four fifths of the time nothing had. Success stays unused until something earns it.
    "located": ("dot", "words located", "var(--semantic-info)",
                ("these words are in the transcript at the turn shown — whether they "
                 "support the claim is a separate question, measured separately, and "
                 "mostly answered no")),
    "composed": ("cross", "not in the transcript", "var(--semantic-error)",
                 "the model composed this quote — the transcript was its only input"),
    "untestable": ("tilde", "too short to check", "var(--semantic-warning)",
                   "under four words, so a match would prove nothing either way"),
    "unquoted": ("dash", "no quote offered", "var(--semantic-warning)",
                 "the claim cites nothing, so it cannot be traced back to the words"),
}

MARKS = {"dot": "&#9656;", "cross": "&#10007;", "tilde": "&#126;",
         "dash": "&#8212;"}

# What each claim KIND means, which is a different axis from its evidence state and was
# not on the page. `PROPOSED` in particular is new vocabulary — it exists because the
# note had nowhere honest to file "maybe we should X" and eleven items were forced up a
# level to fit. A surface that prints a word it never defines fails the cold-start test
# this project took from film-room: separate what the surface tells a reader from what it
# expects them to work out.
KINDS = {
    "decision": "the meeting settled it",
    "action": "someone committed to do it",
    "proposal": "raised, offered or asked for — and not agreed to",
    "question": "asked and left open",
}


def tokens() -> dict[str, str]:
    """The colour tokens, harvested from DESIGN.md's frontmatter.

    Parsed rather than copied so the page cannot drift from the document that governs
    it. `DESIGN.md` states the accent is forbidden in navigation, selection, links,
    focus rings, hover states, charts and every empty state — which is every element
    on this page — so it is harvested and then deliberately unused.
    """
    text = DESIGN.read_text()
    body = text.split("---", 2)[1]
    out, in_colors = {}, False
    for line in body.splitlines():
        if line.startswith("colors:"):
            in_colors = True
            continue
        if in_colors:
            if line and not line.startswith((" ", "\t")):
                break
            if ":" in line and '"' in line:
                k, v = line.split(":", 1)
                out[k.strip()] = v.strip().strip('"')
    if "accent" not in out or "surface-base" not in out:
        raise SystemExit(f"{DESIGN} did not yield the expected colour tokens")
    return out


def transcript_for(doc: dict, note_path: Path):
    """The transcript in the exact transformed shape the evidence coordinates count.

    `transform` is applied here rather than assumed. A claim's `turn` is a position in
    the transcript as the model saw it, and the transforms do not all preserve
    positions — reading the raw file for a `simulate-bleed` run would resolve every
    citation to the wrong words while appearing to work.
    """
    # A checked baseline may live one directory below `notes/out/`, so a note's
    # relative transcript path has to keep the coordinate system it was written in.
    # Trying only note_path.parent makes a perfectly valid snapshot look broken and
    # tempts a reviewer to render the mutable `notes/out` directory instead.
    raw_path = Path(doc["transcript"])
    candidates = [
        note_path.parent / raw_path,
        note_path.parents[1] / raw_path,
        REPO / "notes" / "out" / raw_path,
        REPO / "notes" / raw_path,
    ]
    transcript_path = next((p.resolve() for p in candidates if p.exists()), None)
    if transcript_path is None:
        tried = "\n  ".join(str(p.resolve()) for p in candidates)
        raise SystemExit(
            f"{note_path.name}: cannot locate declared transcript {raw_path!s}. "
            f"Tried:\n  {tried}"
        )
    t = load(transcript_path)
    # Absent is refused rather than read as "none". `.get()` would map a missing key
    # and a deliberate no-transform onto the same value, and the two disagree about
    # what the indices count — an artifact that cannot say is not safe to render, even
    # though `strip` happens to preserve positions and would have looked fine.
    if "transform" not in doc:
        raise SystemExit(
            f"{note_path.name} declares no `transform`, so which turn indexing its "
            f"claims count is unknown. Regenerate it with a current "
            f"notes/summarize.py."
        )
    transform = doc["transform"]
    if transform == "strip":
        t = t.strip_attribution()
    elif transform == "as-channel":
        t = t.as_channel(None)
    elif transform == "simulate-bleed":
        t = t.simulate_bleed()
    elif transform is not None:
        raise SystemExit(f"{note_path}: unknown transform {transform!r}")
    return t


def esc(s) -> str:
    return html.escape(str(s), quote=True)


def stamp(seconds) -> str:
    if seconds is None:
        return "--:--"
    m, s = divmod(int(seconds), 60)
    return f"{m:d}:{s:02d}"


def counts(doc: dict) -> dict[str, int]:
    c = dict.fromkeys(STATES, 0)
    for claim in doc["claims"]:
        c[claim["status"]] += 1
    return c


def note_annotation(status: str, body: str) -> str:
    """A region's epistemic status, rendered in place.

    Not a footnote. The whole reason this layer exists is that a reader cannot tell a
    real region from a fixture by looking, and a legend somewhere else does not travel
    with the region being looked at.
    """
    return (f'<p class="annot annot-{esc(status)}">'
            f'<span class="annot-tag">{esc(status)}</span>{body}</p>')


def trust_bar(c: dict[str, int]) -> str:
    """Proportional, and labelled, because the proportion is the finding.

    Notes differ in this and nothing else on a list row shows it: across three real
    runs the checkable share was 7 of 11, 33 of 83 and 4 of 15. `F` exists to make that
    visible before the note is opened, which `journeys.md` argues is the difference
    between a corpus and a junk drawer.
    """
    total = sum(c.values())
    if not total:
        return '<span class="bar-empty">no claims extracted</span>'
    segs = "".join(
        f'<span class="seg" style="flex:{n};background:{STATES[s][2]}" '
        f'title="{esc(n)} {esc(STATES[s][1])}"></span>'
        for s, n in c.items() if n)
    # The label names both numbers a reader acts on. An earlier version gave only the
    # located count, which left the segments to carry "how bad is the rest" by colour
    # and put the number that matters most on a weak note — how many quotes the model
    # composed — behind a hover. Not a direction breach: the bar is an aggregate of
    # claims that each carry their own state in words, so `DIRECTION.md`'s rule about
    # per-item state is not in scope. It was simply under-informing.
    composed = c["composed"]
    tail = (f', <strong>{composed}</strong> quoted words the model composed'
            if composed else "")
    return (f'<span class="bar">{segs}</span>'
            f'<span class="bar-label"><strong>{c["located"]}</strong> of {total} '
            f'claims can be checked against the words{tail}</span>')


def support_line(claim: dict, support: dict | None) -> str:
    """Whether the located words support this claim, when that has been measured.

    Absent by default and absent honestly: the measurement costs a model call per claim
    with a second model, so a note carries it only after `--measure-support` has run. A
    surface that showed nothing here would let a located quote keep implying more than it
    establishes, which is what the `verified` rename was for — so where the verdict
    exists it is rendered, and where it does not the claim says the question is unasked
    rather than passed.
    """
    if claim["status"] != "located":
        return ""
    if not support:
        return ('<p class="support unmeasured">whether these words support the claim '
                'has not been measured on this note</p>')
    for v in support["verdicts"]:
        if _support_key(v) == _support_key(claim):
            if v["supports"] is None:
                return ('<p class="support unmeasured">the judge returned no verdict on '
                        'whether these words support the claim</p>')
            if v["supports"]:
                return (f'<p class="support yes">the words support this claim '
                        f'<span class="by">judged by {esc(support["judge"])}, '
                        f'calibrated {esc(support["calibration"])}</span></p>')
            return (f'<p class="support no">these words do <strong>not</strong> support '
                    f'this claim &mdash; they contradict it, are about something else, '
                    f'or support only a weaker version '
                    f'<span class="by">judged by {esc(support["judge"])}, '
                    f'calibrated {esc(support["calibration"])}</span></p>')
    return ('<p class="support unmeasured">no support verdict recorded for this '
            'claim</p>')


def claim_row(claim: dict, i: int, meeting: str, support: dict | None = None) -> str:
    mark, word, color, why = STATES[claim["status"]]
    quote = claim.get("quote")
    turn = claim.get("turn")
    # The kind of thing this is, recovered by the summarizer from the note's own
    # headings rather than re-parsed here. It is what makes E's grouping a rendering
    # choice instead of whatever the model happened to emit — see journeys.md.
    kind = (f'<span class="kind">{esc(claim["type"])}</span>'
            if claim.get("type") else "")
    body = [
        f'<p class="claim-text">{kind}{esc(claim["claim"])}</p>',
        (f'<p class="claim-state" style="--state:{color}">'
         f'<span class="mark" aria-hidden="true">{MARKS[mark]}</span>'
         f'<span class="word">{esc(word)}</span>'
         f'<span class="why">{esc(why)}</span></p>'),
    ]
    evidence_rows = claim.get("_resolved_evidence_refs")
    if evidence_rows is None and quote:
        evidence_rows = [{
            "turn": turn,
            "quote": quote,
            "start": claim.get("start"),
        }]
    for evidence_index, evidence in enumerate(evidence_rows or [], 1):
        evidence_turn = evidence["turn"]
        evidence_quote = evidence["quote"]
        # The locator is derived by finding the quote, never taken from the model. It
        # shows a timestamp when there is one and the turn position when there is not:
        # corpus transcripts carry no times, and a button reading "--:--" claims a
        # precision the material does not have while hiding that it still works. A
        # real capture always records times, so this is a limit of the corpus.
        where = (stamp(evidence.get("start")) if evidence.get("start") is not None
                 else f"turn {evidence_turn}")
        at = (f'<button class="at" data-meeting="{esc(meeting)}" '
              f'data-turn="{evidence_turn}">{esc(where)}</button>') \
            if evidence_turn is not None else ""
        part = (
            f'<span class="evidence-part">source {evidence_index} of '
            f'{len(evidence_rows)}</span>'
            if len(evidence_rows) > 1 else ""
        )
        # The block carries the verdict's colour on its edge. Presenting a composed
        # quote in the same frame as a located one lets it read as evidence, which is
        # the failure this whole surface exists to prevent — and the state word sits
        # directly above, so the colour is never carrying the state alone.
        body.append(f'<blockquote class="quote" style="--state:{color}">{at}{part}'
                    f'<span class="qtext">{esc(evidence_quote)}</span></blockquote>')
    body.append(support_line(claim, support))
    return f'<li class="claim claim-{esc(claim["status"])}" id="c-{esc(meeting)}-{i}">' \
           + "".join(body) + "</li>"


def transcript_pane(meeting: str, turns: list, cited: set[int]) -> str:
    """The retained words, with a position column that carries something real.

    A transcript with no times gets turn numbers rather than a column of `--:--`. The
    column's job is to let the operator say where in the record they are and point
    someone else at it; a repeated placeholder does that job worse than a number and
    implies the times exist but failed to render.
    """
    timed = any(t.start is not None for t in turns)
    rows = []
    for i, t in enumerate(turns):
        who = f'<span class="who">{esc(t.speaker)}</span>' if t.speaker else ""
        klass = "turn cited" if i in cited else "turn"
        where = stamp(t.start) if timed else str(i)
        rows.append(f'<li class="{klass}" id="t-{esc(meeting)}-{i}">'
                    f'<span class="tt">{esc(where)}</span>{who}'
                    f'<span class="text">{esc(t.text)}</span></li>')
    return f'<ol class="turns" id="tr-{esc(meeting)}">' + "".join(rows) + "</ol>"


def check_locators(doc: dict, transcript, note_path: Path) -> None:
    """Every located claim's locator must land on the words it quotes.

    The one promise this page makes that a reader cannot check by looking. A button
    that scrolls to the wrong turn is indistinguishable from one that works — the page
    still moves, a turn still highlights, and the operator reads speech that did not
    produce the claim. That is worse than no button, because it manufactures
    confidence. So it is asserted at build time rather than spot-checked visually.

    Repair 4 artifacts resolve their declared fragment map and exact character spans
    through the summarizer's validator. Legacy artifacts still use `_seq`, imported
    rather than reimplemented, so this renderer never becomes a second authority on
    what either evidence contract means.
    """
    turns = transcript.turns
    if artifact_uses_source_evidence(doc):
        if "evidence" not in doc:
            raise SystemExit(
                f"{note_path.name}: Repair 4 artifact is missing its source "
                "evidence graph"
            )
        try:
            structured_artifact_citations(doc, transcript)
            resolved = validate_evidence_contract(doc["evidence"], transcript)
        except ValueError as e:
            raise SystemExit(f"{note_path.name}: source evidence refused: {e}") from e
        expected = [
            evidence
            for label in ("DECISION", "ACTION", "PROPOSAL", "QUESTION")
            for evidence in resolved
            if evidence["label"] == label
        ]
        if len(expected) != len(doc["claims"]):
            raise SystemExit(
                f"{note_path.name}: {len(expected)} evidence records do not match "
                f"{len(doc['claims'])} claims"
            )
        for claim, evidence in zip(doc["claims"], expected, strict=True):
            resolved_refs = [
                {
                    key: ref[key]
                    for key in (
                        "source_fragment_id", "turn", "char_start", "char_end",
                        "text_sha256",
                    )
                }
                for ref in evidence["evidence_refs"]
            ]
            if (claim.get("source_item_ids") != evidence["source_item_ids"]
                    or claim.get("source_claim_sha256s")
                    != evidence["source_claim_sha256s"]
                    or claim.get("claim_sha256") != evidence["claim_sha256"]
                    or claim.get("evidence_refs") != resolved_refs
                    or claim.get("status") != "located"
                    or claim.get("type") != evidence["label"].lower()):
                raise SystemExit(
                    f"{note_path.name}: claim evidence metadata disagrees with "
                    "the durable coverage graph"
                )
            claim["_resolved_evidence_refs"] = [
                {
                    "turn": ref["turn"],
                    "start": turns[ref["turn"]].start,
                    "quote": ref["quote"],
                }
                for ref in evidence["evidence_refs"]
            ]
            if (claim.get("quote"), claim.get("turn")) != (
                    evidence["evidence_refs"][0]["quote"],
                    evidence["evidence_refs"][0]["turn"]):
                raise SystemExit(
                    f"{note_path.name}: compatibility quote/turn is not the first "
                    "declared source fragment"
                )
        try:
            validate_support_measurement(doc, transcript)
        except ValueError as e:
            raise SystemExit(
                f"{note_path.name}: support measurement refused: {e}"
            ) from e
        return

    for claim in doc["claims"]:
        if claim["status"] != "located":
            continue
        i = claim.get("turn")
        if i is None or not 0 <= i < len(turns):
            raise SystemExit(
                f"{note_path.name}: a located claim points at turn {i}, which is not "
                f"in a transcript of {len(turns)} turns. The artifact and the "
                f"transcript disagree — check `transform`."
            )
        q, hay = _seq(claim["quote"]), _seq(turns[i].text)
        if not any(hay[s:s + len(q)] == q for s in range(len(hay) - len(q) + 1)):
            raise SystemExit(
                f"{note_path.name}: turn {i} does not contain the quote it is cited "
                f"for.\n  quote: {claim['quote']!r}\n  turn:  {turns[i].text!r}"
            )


def meeting_section(doc: dict, note_path: Path) -> tuple[str, dict]:
    m = doc["meeting"]
    transcript = transcript_for(doc, note_path)
    turns = transcript.turns
    check_locators(doc, transcript, note_path)
    c = counts(doc)
    cited = {
        ref["turn"]
        for claim in doc["claims"]
        for ref in claim.get(
            "_resolved_evidence_refs",
            ([{"turn": claim["turn"]}] if claim.get("turn") is not None else []),
        )
    }
    prov = doc["provenance"]

    support = doc.get("support")
    claims = "".join(claim_row(cl, i, m["id"], support)
                     for i, cl in enumerate(doc["claims"]))
    path = ("two passes over "
            f"{prov['slices']} slices" if prov["passes"] == 2 else "a single pass")

    # Every figure here is read from the artifact. The turn count, the claim counts,
    # the model, the elapsed time and the slice count are all what the run recorded.
    meta = (f'{esc(len(turns))} turns &middot; {esc(m["attribution"])} attribution '
            f'&middot; {esc(prov["model"])}, {path}, {esc(prov["elapsed_s"])}s')

    return (f'''
<section class="meeting" id="m-{esc(m["id"])}">
  <header class="mhead">
    <h3>{esc(m["id"])}</h3>
    <p class="meta">{meta}</p>
    <div class="trust">{trust_bar(c)}</div>
  </header>
  <div class="split">
    <div class="col">
      <h4>The note &mdash; every claim with its evidence state</h4>
      {note_annotation("real data",
                       "Generated by a real model run over this transcript. The "
                       "claims appear in the order they are read, not grouped by "
                       "outcome: reordering by trust would hide how much of the note "
                       "carries composed evidence, which is the one thing this surface exists to "
                       "show.")}
      <ol class="claims">{claims}</ol>
    </div>
    <div class="col col-evidence">
      <h4>The transcript &mdash; what was actually said</h4>
      {note_annotation("real data",
                       "The retained artifact. Each source fragment's position is a "
                       "button: it moves to the exact turn behind that part of the claim. That "
                       "path is J1 beat 3, and it survives the audio being deleted "
                       "because it does not use the audio.")}
      {transcript_pane(m["id"], turns, cited)}
    </div>
  </div>
</section>''', c)


def library_row(doc: dict) -> str:
    m, c = doc["meeting"], counts(doc)
    return f'''
    <li class="lib-row">
      <span class="lib-ident">
        <a class="lib-open" href="#m-{esc(m["id"])}">{esc(m["id"])}</a>
        <span class="lib-src">{esc(m["source"])}</span>
        <span class="lib-turns">{esc(m["turns"])} turns</span>
        <span class="lib-date" title="corpus meetings carry no date; a real capture
          records captured_at">no date</span>
      </span>
      <span class="lib-trust">{trust_bar(c)}</span>
    </li>'''


def specimen() -> str:
    """J1 beat 4, which the corpus cannot populate, as a labelled specimen.

    QMSum transcripts are full-recall reference text: no capture gate ran, so there is
    no recall figure and no held-back turn. Inventing one would make every judgement
    on this page worthless. The figures below are the project's own published
    measurements from `spike/RESULTS.md`, rendered as a component with a stated data
    contract rather than as a meeting that exists.
    """
    return f'''
<section class="specimen" id="honesty">
  <h3>Specimen &mdash; "not captured" is not "never said"</h3>
  {note_annotation("component specimen",
                   "This is not a meeting. No corpus transcript can populate it: "
                   "QMSum is full-recall reference text, so no capture gate ran and "
                   "there is no recall figure to show. The numbers are this "
                   "project's own published measurements, and the component is here "
                   "to settle the treatment, not to claim a meeting.")}
  <div class="banner">
    <p class="banner-lead">This note was written from part of the meeting.</p>
    <ul class="banner-facts">
      <li><strong>30.7%</strong> of the meeting's words reached the transcript
          <span class="src">measured on the level-45 sweep take</span></li>
      <li><strong>14.2%</strong> of merged turns were the room rather than a
          participant <span class="src">the 75-minute capture, 802 turns</span></li>
    </ul>
    <p class="banner-tail">A claim absent from this note may never have been said, or
      may be in the two-thirds that was not captured. This surface is the only place
      that difference can be told, and the figures to tell it are already in the
      artifact.</p>
  </div>
  {note_annotation("open question",
                   "What the operator can <em>do</em> here is undesigned. Seeing "
                   "that a third of the meeting is missing does not recover it, and "
                   "whether this offers re-processing, a jump to the gate's held-back "
                   "turns, or nothing at all is J4 and unanswered.")}
</section>'''


def operating_point_fixture() -> list[dict]:
    """Measured, non-personal points for reviewing a populated product choice.

    The values are derived through the shipping calibration arithmetic from fixed
    score fixtures. They demonstrate the populated state without presenting a
    reviewer with a fabricated personal result. Production supplies held-out scores
    from the owner and the permitted negative sample instead.
    """
    operator = [0.60 + i * 0.003 for i in range(100)]
    negative = [0.54 + i * 0.007 for i in range(40)]
    return operating_point_choices(
        operator,
        negative,
        negative_scorable_seconds=80.0,
    )


def operating_point_markup(points: list[dict]) -> str:
    labels = (
        ["Preserve more of my speech", "Keep more other voices out"]
        if len(points) == 2
        else [
            "Preserve more of my speech",
            "Choose the measured middle point",
            "Keep more other voices out",
        ]
    )
    return "".join(
        f'''<label><input type="radio" name="voice-policy"
          data-target="{point["target_frr"]:.8f}"
          data-operator-rate="{point["measured_frr"]:.8f}"
          data-negative-rate="{point["false_admit_rate"]:.8f}" disabled>
        <strong>{esc(label)}</strong>
        <span>Load the measured-point fixture to review both rates.</span></label>'''
        for label, point in zip(labels, points, strict=True)
    )


def encounter() -> str:
    """The interaction questions the corpus cannot answer, marked in place.

    This is deliberately state choreography, not a fake meeting. QMSum gives the
    library and evidence path real words, but it contains neither a local capture,
    a consent event, a gated turn, nor retained audio. The controls let an operator
    test the decisions those absences leave open without claiming that the selected
    state produced the QMSum note below.
    """
    points = operating_point_fixture()
    returning = points[(len(points) - 1) // 2]
    markup = '''
<section class="encounter" id="encounter" data-initial-panel="spec-library">
  <header class="encounter-head">
    <div>
      <p class="eyebrow">interaction specimen</p>
      <h2>Cold-start capture and recovery path</h2>
      <p class="lede">The library below remains real QMSum-derived content. Everything
        in this strip is a state specimen: it tests what the app says and lets the
        operator choose, but it does not create a meeting, transcript, or result.</p>
    </div>
    <div class="menubar" aria-live="polite">
      <span class="menubar-label">menu bar</span>
      <span class="menubar-glyph glyph-idle" id="menubar-glyph" aria-hidden="true">○</span>
      <strong id="menubar-word">idle</strong>
    </div>
  </header>
  <div class="encounter-controls" aria-label="Review states">
    <button type="button" data-panel="spec-library">library</button>
    <button type="button" data-panel="spec-first-run">first launch</button>
    <button type="button" data-panel="spec-enrollment-blocked">enrollment blocked</button>
    <button type="button" data-panel="spec-enrolled">enrolled profile</button>
    <button type="button" data-panel="spec-profile-reset">reset profile</button>
    <button type="button" data-panel="spec-detected">future: detection</button>
    <button type="button" data-panel="spec-consent">consent</button>
    <button type="button" data-panel="spec-armed">armed</button>
    <button type="button" data-panel="spec-recording">recording</button>
    <button type="button" data-panel="spec-degraded">degraded</button>
    <button type="button" data-panel="spec-transcribing">transcribing</button>
    <button type="button" data-panel="spec-processing-failed">processing failure</button>
    <button type="button" data-panel="spec-correction">correction</button>
    <button type="button" data-panel="spec-retention">retention</button>
    <button type="button" data-panel="spec-delete-meeting">delete meeting</button>
    <button type="button" data-panel="spec-far-end">far-end notice</button>
  </div>

  <section class="encounter-panel is-active" id="spec-library" data-menubar="idle">
    <h3>Open to the library, with a note already visible</h3>
    <p>This is the cold-start default: content is present, but no capture resumes and
      no note is chosen for the operator. The real-data library and detail follow this
      specimen.</p>
    <p class="state-result" id="capture-eligibility">Supported capture unavailable:
      complete voice enrollment first. Existing meetings remain readable.</p>
    <div class="panel-actions">
      <button type="button" id="manual-capture" data-action="manual-start" disabled>
        start capture — setup required
      </button>
      <button type="button" data-panel="spec-first-run">review first launch</button>
      <button type="button" data-panel="spec-enrollment-blocked">
        review enrollment blocker</button>
    </div>
  </section>

  <section class="encounter-panel" id="spec-first-run" data-menubar="idle" hidden>
    <p class="eyebrow">first launch · required permissions · interaction specimen</p>
    <h3>Allow the two sources capture needs</h3>
    <p>This prototype never requests a macOS permission. The controls expose the
      required states and the recovery path only. Capture stays unavailable until both
      sources are granted.</p>
    <div class="setup-status">
      <p><strong>Microphone</strong><span id="permission-microphone">permission needed</span></p>
      <p><strong>System audio capture</strong><span id="permission-system">
        permission needed</span></p>
    </div>
    <div class="panel-actions">
      <button type="button" data-permission="microphone">show microphone granted</button>
      <button type="button" data-permission="system">show system capture granted</button>
    </div>
    <p class="state-result" id="permissions-result">Two permissions still needed.</p>
    <button type="button" data-panel="spec-retention-choice"
      data-requires-permissions disabled>
      choose meeting-audio retention
    </button>
  </section>

  <section class="encounter-panel" id="spec-enrollment-blocked"
    data-menubar="idle" hidden>
    <p class="eyebrow">blocked · no valid profile loaded</p>
    <h3>Supported capture waits for a measured voice profile</h3>
    <p>A first profile comes from dedicated calibration, not from an ungated meeting.
      The app reports observed facts here; this specimen uses placeholders rather than
      inventing a result for its reviewer.</p>
    <div class="setup-status">
      <p><strong>Separate sittings</strong><span>measured at runtime</span></p>
      <p><strong>Held-out operator speech</strong><span>measured at runtime</span></p>
      <p><strong>Time between sittings</strong><span>measured at runtime</span></p>
      <p><strong>Other-voice sample</strong><span>measured at runtime</span></p>
    </div>
    <ul class="setup-list">
      <li><strong>At least two sittings</strong>, at least one hour apart; different
        days are ideal.</li>
      <li>Enough held-out operator speech to resolve at least two distinct policies.</li>
      <li>Negative material from public or licensed playback, or a person who
        consented to make the calibration recording.</li>
    </ul>
    <p class="state-result" id="enrollment-status">Enrollment blocked. No profile or
      personal result is claimed by this prototype.</p>
    <div class="panel-actions">
      <button type="button" data-enrollment-event="save-first">
        review first-sitting saved</button>
      <button type="button" id="load-valid-profile-fixture"
        data-enrollment-event="load-returning-profile">
        load returning valid-profile fixture</button>
    </div>
  </section>

  <section class="encounter-panel" id="spec-first-sitting-saved"
    data-menubar="idle" hidden>
    <p class="eyebrow">accumulating · first sitting saved</p>
    <h3>Keep derived material; remove the dedicated raw recording</h3>
    <p>After owner-only embeddings and provenance are written safely, the product
      deletes the dedicated WAV, transcript, temporary segments, and partial working
      files immediately. It keeps only the owner-only derived enrollment material
      needed to compare a later sitting.</p>
    <p class="state-result">Review transition only — no sitting was recorded or saved
      for this prototype.</p>
    <div class="panel-actions">
      <button type="button" data-enrollment-event="resume-after-gap">
        review resume after the gap</button>
      <button type="button" data-discard-origin="spec-first-sitting-saved">
        discard enrollment</button>
    </div>
  </section>

  <section class="encounter-panel" id="spec-resume-after-gap"
    data-menubar="idle" hidden>
    <p class="eyebrow">resume · first sitting derived material held</p>
    <h3>Return at least one hour later; another day is ideal</h3>
    <p>The product reads the recorded timestamps. It does not turn two clips from one
      session into two sittings, and it does not fabricate elapsed time in this
      specimen.</p>
    <p class="state-result">Elapsed time and next eligibility are measured at runtime.</p>
    <div class="panel-actions">
      <button type="button" data-enrollment-event="review-second">
        review second-sitting completion</button>
      <button type="button" data-discard-origin="spec-resume-after-gap">
        discard enrollment</button>
    </div>
  </section>

  <section class="encounter-panel" id="spec-second-sitting-review"
    data-menubar="idle" hidden>
    <p class="eyebrow">accumulating · second sitting review</p>
    <h3>Review what the two operator sittings support</h3>
    <p>The runtime state reports the exact sitting count, gap, held-out segments, and
      any refusal. Each dedicated raw recording is deleted immediately after its
      owner-only derived material is safely stored.</p>
    <p>If extraction fails, the operator cancels, or the flow is abandoned, partial
      raw and working files are deleted and enrollment remains incomplete.</p>
    <p class="state-result">No operator counts are asserted by this specimen.</p>
    <div class="panel-actions">
      <button type="button" data-enrollment-event="review-negative">
        review the required negative sample</button>
      <button type="button" data-discard-origin="spec-second-sitting-review">
        discard enrollment</button>
    </div>
  </section>

  <section class="encounter-panel" id="spec-negative-sample" data-menubar="idle" hidden>
    <p class="eyebrow">negative sample · dedicated calibration material</p>
    <h3>Measure what the gate might mistake for you</h3>
    <p>Use either public-domain or appropriately licensed speech played near the
      microphone, or a person who knowingly agrees to make this calibration recording.
      Do not capture a private conversation, an unaware bystander, or unlicensed
      program audio for this step.</p>
    <p>The registered product floor is at least 60 seconds of scorable speech across
      at least 20 segments. The minute is the documented speech floor; 20 segments is
      a product judgement that stops one long passage from pretending to be a score
      distribution. Neither is presented as a statistical guarantee.</p>
    <fieldset class="negative-choice">
      <legend>Review an allowed source — none is preselected</legend>
      <label><input type="radio" name="negative-source">
        Public-domain or licensed speech playback</label>
      <label><input type="radio" name="negative-source">
        A consenting person recording for calibration</label>
    </fieldset>
    <p>After owner-only negative scores are safely stored, the dedicated raw recording,
      transcript, temporary segments, and partial working files are deleted
      immediately. Failure, cancellation, or abandonment deletes partial raw and leaves
      enrollment incomplete. Existing source meetings are never copied or deleted;
      each keeps the audio-retention period already chosen for it.</p>
    <p class="state-result" id="negative-material-result">No source selected in this
      specimen. No recording is made.</p>
    <div class="panel-actions">
      <button type="button" id="load-operating-fixture"
        data-enrollment-event="measurements-ready" disabled>
        load measured-point fixture</button>
      <button type="button" data-discard-origin="spec-negative-sample">
        discard enrollment</button>
    </div>
  </section>

  <section class="encounter-panel" id="spec-operating-point" data-menubar="idle" hidden>
    <p class="eyebrow">operating point · ordered policy choice</p>
    <h3>Choose which error the gate should avoid first</h3>
    <p>The product populates both rates below from the operator's held-out sittings
      and the permitted negative sample. Until those measurements exist, the choices
      remain unavailable. No option is selected or recommended by default.</p>
    <fieldset class="voice-policy-choice" id="voice-policy-choices">
      <legend>Ordered from preserving your speech to excluding other voices</legend>
      __OPERATING_POINT_CHOICES__
    </fieldset>
    <p class="state-result" id="voice-policy-result">No policy selected. This
      prototype has no personal measurements; fixture choices remain disabled until
      the measured-point transition runs.</p>
    <div class="panel-actions">
      <button type="button" id="continue-selected-policy"
        data-enrollment-event="select-policy" disabled>
        continue with selected measured policy</button>
      <button type="button" data-discard-origin="spec-operating-point">
        discard enrollment</button>
    </div>
  </section>

  <section class="encounter-panel" id="spec-ready-to-build" data-menubar="idle" hidden>
    <p class="eyebrow">ready to build · measured policy selected</p>
    <h3>Build only from the selected row and its private receipt</h3>
    <p>The production boundary receives the held-out score arrays, negative-source
      manifests, and selected target. It re-derives the offered rows and will not
      accept a caller-supplied threshold or operating-point object.</p>
    <p class="state-result" id="ready-policy-result">A fixture policy was selected;
      no profile has been built or persisted.</p>
    <button type="button" data-enrollment-event="build-profile">
      run profile-build fixture</button>
    <button type="button" data-discard-origin="spec-ready-to-build">
      discard enrollment</button>
  </section>

  <section class="encounter-panel" id="spec-building-profile" data-menubar="idle" hidden>
    <p class="eyebrow">profile build · persistence not yet confirmed</p>
    <h3>Start remains blocked until owner-only persistence succeeds</h3>
    <p>This state separates a completed calculation from a durable profile. A process
      failure here deletes partial output and leaves enrollment incomplete.</p>
    <p class="state-result">Build fixture complete; persistence success has not been
      recorded. No profile exists for this reviewer.</p>
    <button type="button" data-enrollment-event="persist-profile-success">
      record owner-only persistence-success fixture</button>
    <button type="button" data-discard-origin="spec-building-profile">
      discard enrollment</button>
  </section>

  <section class="encounter-panel" id="spec-enrolled" data-menubar="idle" hidden>
    <p class="eyebrow">enrolled fixture · persistence success recorded</p>
    <h3>The new profile is now valid; capture still needs every prerequisite</h3>
    <p>This state is reachable only after a measured radio is selected, the build
      transition runs, and owner-only persistence succeeds. It shows measured rates,
      sittings, held-out speech, build time, and encoder identity. This specimen
      changes no file and claims none of those facts about its reviewer.</p>
    <div class="setup-status">
      <p><strong>Selected policy and rates</strong><span>shown at runtime</span></p>
      <p><strong>Enrollment provenance</strong><span>shown at runtime</span></p>
      <p><strong>Profile owner</strong><span>this macOS account only</span></p>
    </div>
    <p>The profile is app-private, owner-only, and separate from every meeting. It is
      not included in exports. Dedicated calibration audio has already been deleted;
      source meetings retain their own chosen lifecycle.</p>
    <p class="state-result">A valid profile is one prerequisite. Start also requires
      both current permissions and a selected meeting-audio retention period.</p>
    <button type="button" data-panel="spec-library">review combined readiness</button>
    <button type="button" data-panel="spec-profile-reset">review profile reset</button>
  </section>

  <section class="encounter-panel" id="spec-returning-profile"
    data-menubar="idle" hidden>
    <p class="eyebrow">returning-valid-profile fixture · no profile built here</p>
    <h3>A previously persisted valid profile satisfies one readiness requirement</h3>
    <p>The explicit fixture transition represents a profile that has already passed
      schema, provenance, encoder, and operating-point validation. It neither builds a
      profile nor claims one exists for this reviewer.</p>
    <div class="setup-status">
      <p><strong>Fixture operator speech dropped</strong>
        <span>__RETURNING_OPERATOR_RATE__ measured</span></p>
      <p><strong>Fixture negative speech admitted</strong>
        <span>__RETURNING_NEGATIVE_RATE__ measured</span></p>
      <p><strong>Profile owner</strong><span>fixture macOS account only</span></p>
    </div>
    <p class="state-result">Start remains blocked until both current permission
      fixtures and an explicit retention fixture are also loaded.</p>
    <button type="button" id="load-returning-prerequisites">
      load returning permissions and retention fixtures</button>
    <button type="button" data-panel="spec-library">review combined readiness</button>
    <button type="button" data-panel="spec-profile-reset">review profile reset</button>
  </section>

  <section class="encounter-panel" id="spec-discard-enrollment"
    data-menubar="idle" hidden>
    <p class="eyebrow">discard incomplete enrollment · destructive</p>
    <h3>Discard enrollment without touching meetings</h3>
    <p>Discard deletes derived operator embeddings, negative scores, temporary
      provenance, any partial profile, and every partial dedicated raw or working file.
      Enrollment becomes incomplete. Existing meetings, notes, transcripts, meeting
      audio, retention choices, and any previously valid profile remain.</p>
    <p class="state-result" id="discard-result">Incomplete enrollment material remains
      in this interaction specimen.</p>
    <button type="button" id="discard-enrollment-now">discard enrollment</button>
    <div class="confirm-box" id="discard-enrollment-confirm" hidden>
      <strong>Discard this incomplete enrollment?</strong>
      <p>All dedicated enrollment material and partial derived work go. Source meetings
        are never copied or deleted. No profile is built. This product action cannot be
        undone; this specimen changes no file.</p>
      <button type="button" id="confirm-discard-enrollment"
        data-enrollment-event="discard">discard enrollment material</button>
      <button type="button" id="cancel-discard-enrollment">cancel</button>
    </div>
  </section>

  <section class="encounter-panel" id="spec-profile-reset" data-menubar="idle" hidden>
    <p class="eyebrow">owner-only profile · separately deletable</p>
    <h3>Reset the voice profile without deleting meetings</h3>
    <p class="state-result" id="profile-result">The profile remains in this
      interaction specimen.</p>
    <button type="button" id="reset-profile-now">reset voice profile</button>
    <div class="confirm-box" id="reset-profile-confirm" hidden>
      <strong>Delete the local voice profile?</strong>
      <p>The profile, calibrated threshold, and enrollment provenance go. Existing
        notes, transcripts, meeting audio, and meeting retention choices remain.
        Dedicated calibration raw was already deleted after its owner-only derived
        material was stored. The application blocks capture until enrollment completes
        again; only the research CLI may run ungated outside the beta. This product
        action cannot be undone; this specimen changes no file.</p>
      <button type="button" id="confirm-reset-profile">delete profile</button>
      <button type="button" id="cancel-reset-profile">cancel</button>
    </div>
  </section>

  <section class="encounter-panel" id="spec-retention-choice" data-menubar="idle" hidden>
    <p class="eyebrow">first launch · choice required</p>
    <h3>Choose how long audio stays on this Mac</h3>
    <p>Notes and transcripts remain when meeting audio is deleted. There is
      intentionally no preselected period: this choice concerns recordings of other
      people. Dedicated enrollment raw is shorter lived and is deleted as soon as the
      needed owner-only derived material is safely stored.</p>
    <fieldset class="retention-choice">
      <legend>Auto-deletion period</legend>
      <label><input type="radio" name="retention-period" value="30 days"> 30 days</label>
      <label><input type="radio" name="retention-period" value="90 days"> 90 days</label>
      <label><input type="radio" name="retention-period" value="1 year"> 1 year</label>
      <label><input type="radio" name="retention-period"
        value="Keep audio until I delete it">
        Keep audio until I delete it</label>
    </fieldset>
    <p class="state-result" id="retention-result">No period selected.</p>
    <button type="button" data-panel="spec-enrollment-blocked"
      data-requires-retention disabled>
      continue to required voice enrollment
    </button>
  </section>

  <section class="encounter-panel" id="spec-detected" data-menubar="detected" hidden>
    <p class="eyebrow">future research · excluded from supported beta</p>
    <h3>Microphone-use detection is not the beta start path</h3>
    <p>The beta starts manually from the library or menubar. This state remains here
      only to test a possible future detection signal: outlined, not recording, and
      with no timer started.</p>
    <button type="button" id="future-consent">show consent</button>
    <button type="button" data-panel="spec-library">not this time</button>
  </section>

  <section class="encounter-panel" id="spec-consent" data-menubar="idle" hidden>
    <p class="eyebrow">operator attestation · capture is not running</p>
    <h3>Do the participants know and agree to this recording?</h3>
    <p>The app cannot infer consent from microphone activity. The operator must attest
      before the cancellable countdown begins. The product shows the chosen meeting
      audio-retention period here and states that the transcript and note remain until
      the meeting itself is deleted.</p>
    <p class="state-result" id="consent-retention">Meeting audio retention: selected
      period shown at runtime. Transcript and note: held until this meeting is
      deleted.</p>
    <label class="attestation"><input type="checkbox" id="participant-attested">
      I confirm the participants know this meeting will be recorded, understand the
      retention shown above, and agree.
    </label>
    <p class="state-result" id="attestation-result">Attestation required.</p>
    <div class="panel-actions">
      <button type="button" id="consent-continue" data-panel="spec-armed"
        data-requires-attestation disabled>
        confirm and continue
      </button>
      <button type="button" id="cancel-capture-attempt">not this time</button>
    </div>
  </section>

  <section class="encounter-panel" id="spec-armed" data-menubar="armed" hidden>
    <p class="eyebrow">consent recorded · cancellable countdown</p>
    <h3>Armed — recording begins after the consent window</h3>
    <p class="countdown">00:05</p>
    <button type="button" data-panel="spec-recording">start capture</button>
    <button type="button" id="cancel-armed">cancel</button>
  </section>

  <section class="encounter-panel" id="spec-recording" data-menubar="recording" hidden>
    <p class="eyebrow">capture running · both legs healthy</p>
    <h3>Recording</h3>
    <p class="meter" aria-label="Audio level reading"><span></span><span></span><span></span>
      <span></span><span></span><span></span></p>
    <p>The meter is a static specimen under reduced motion. A real capture is the only
      thing that may move it.</p>
    <button type="button" data-panel="spec-transcribing" data-action="manual-stop">
      stop capture
    </button>
    <button type="button" data-panel="spec-degraded">simulate a lost system tap</button>
  </section>

  <section class="encounter-panel" id="spec-degraded" data-menubar="degraded" hidden>
    <p class="eyebrow">capture continues · system audio unavailable</p>
    <h3>Degraded, not silently healthy</h3>
    <p>The microphone leg remains. The menubar keeps the live mark and adds a persistent
      fault mark; the split cannot be claimed while the system leg is missing.</p>
    <button type="button" data-panel="spec-recording">system tap restored</button>
    <button type="button" data-panel="spec-transcribing" data-action="manual-stop">
      stop capture
    </button>
  </section>

  <section class="encounter-panel" id="spec-transcribing" data-menubar="transcribing" hidden>
    <p class="eyebrow">capture stopped · retained audio is processing locally</p>
    <h3>Transcribing</h3>
    <p>No claim or transcript is shown as the result of this specimen. The next state
      only demonstrates where a completed note would appear.</p>
    <button type="button" data-panel="spec-note-ready" data-action="finish-processing">
      finish processing</button>
    <button type="button" data-panel="spec-processing-failed">simulate processing failure</button>
  </section>

  <section class="encounter-panel" id="spec-processing-failed" data-menubar="error" hidden>
    <p class="eyebrow">processing failure · recoverable</p>
    <h3>The summary did not run. The transcript remains.</h3>
    <p>This is not a blank note and not a lost recording. The real transcript treatment
      below is evidence for the detail view; it was not produced by this specimen.</p>
    <button type="button" data-panel="spec-transcribing">retry processing</button>
  </section>

  <section class="encounter-panel" id="spec-note-ready" data-menubar="idle" hidden>
    <p class="eyebrow">interaction specimen · no source content asserted</p>
    <h3>A new note appears at the top of the library</h3>
    <p>The specimen row is now visible below. It carries no invented meeting name,
      quote, or result. Its review action moves to the real QMSum-derived detail
      treatment and says so before the move.</p>
    <button type="button" data-action="open-real-data-detail">
      review the real-data detail treatment
    </button>
  </section>

  <section class="encounter-panel" id="spec-correction" data-menubar="idle" hidden>
    <p class="eyebrow">correction specimen · no gated turn in QMSum</p>
    <h3>A withheld turn is visible before it is restored</h3>
    <p>These source artifacts have no captured voice-gate rejection. This panel tests
      the required consequence only: restoring withheld speech makes the current note
      stale; it cannot silently remain the summary of the old transcript.</p>
    <div class="withheld-turn" id="withheld-turn">
      <strong>withheld turn</strong><span>Interaction specimen — source words omitted.</span>
    </div>
    <p class="state-result" id="correction-result">Displayed note: current for the
      transcript before this turn is restored.</p>
    <button type="button" id="restore-turn">restore turn and mark note for regeneration</button>
    <button type="button" id="regenerate-note" disabled>regenerate note</button>
    <button type="button" data-panel="spec-library">return to real-data note</button>
  </section>

  <section class="encounter-panel" id="spec-retention" data-menubar="idle" hidden>
    <p class="eyebrow">delete-audio specimen · no local file is touched</p>
    <h3>Delete audio; keep the note and transcript evidence</h3>
    <p>Deleting audio removes both captured WAV files and the ability to replay tone
      or identity. The note, transcript, claim-to-words links, and separately stored
      voice profile remain.</p>
    <p class="state-result" id="audio-result">Audio files are still held in this
      specimen.</p>
    <button type="button" id="delete-audio-now">delete audio now</button>
    <div class="confirm-box" id="delete-audio-confirm" hidden>
      <strong>Delete the audio files now?</strong>
      <p>The note, transcript, claim evidence, and voice profile remain. Both meeting
        WAV files, audio playback, tone checks, identity checks against that audio, and
        retranscription from that audio go. The product action cannot be undone; this
        specimen changes no file.</p>
      <button type="button" id="confirm-delete-audio">delete audio files</button>
      <button type="button" id="cancel-delete-audio">cancel</button>
    </div>
    <button type="button" data-panel="spec-delete-meeting">review delete meeting</button>
    <button type="button" data-panel="spec-library">return to library</button>
  </section>

  <section class="encounter-panel" id="spec-delete-meeting" data-menubar="idle" hidden>
    <p class="eyebrow">delete-meeting specimen · no local file is touched</p>
    <h3>Delete the whole meeting</h3>
    <p>This is separate from deleting audio and from resetting the voice profile. It
      removes the note, transcript, evidence links, both audio files, and this
      meeting's retention record. The owner-only voice profile remains.</p>
    <p class="state-result" id="meeting-result">The meeting is still held in this
      specimen.</p>
    <button type="button" id="delete-meeting-now">delete meeting</button>
    <div class="confirm-box" id="delete-meeting-confirm" hidden>
      <strong>Delete this meeting permanently?</strong>
      <p>The note, transcript, claim evidence, both meeting WAV files, and this
        meeting's retention record all go. Nothing from this meeting remains to
        retrieve or regenerate. The separately stored voice profile and other meetings
        remain. The product action cannot be undone; this specimen changes no file.</p>
      <button type="button" id="confirm-delete-meeting">delete note, transcript, and audio</button>
      <button type="button" id="cancel-delete-meeting">cancel</button>
    </div>
    <button type="button" data-panel="spec-library">return to library</button>
  </section>

  <section class="encounter-panel" id="spec-far-end" data-menubar="idle" hidden>
    <p class="eyebrow">open product decision · not implemented</p>
    <h3>What does the far end hear?</h3>
    <p>No convention is selected. The category handles this differently; this product
      must choose before capture ships beyond a controlled beta.</p>
    <fieldset class="notice-choice">
      <legend>Review the policy alternatives</legend>
      <label><input type="radio" name="far-end"> The operator tells participants</label>
      <label><input type="radio" name="far-end"> The app announces recording</label>
      <label><input type="radio" name="far-end"> Capture is blocked until another
        policy is chosen</label>
    </fieldset>
    <p class="state-result" id="notice-result">No policy selected in this prototype.</p>
  </section>
</section>'''
    return (
        markup
        .replace("__OPERATING_POINT_CHOICES__", operating_point_markup(points))
        .replace("__RETURNING_OPERATOR_RATE__", f"{returning['measured_frr']:.1%}")
        .replace("__RETURNING_NEGATIVE_RATE__", f"{returning['false_admit_rate']:.1%}")
    )


def page(sections: str, library: str, totals: dict[str, int], tok: dict[str, str],
         meetings: int) -> str:
    css_vars = "\n      ".join(f"--{k}: {v};" for k, v in tok.items())
    legend = "".join(
        f'<li style="--state:{color}"><span class="mark">{MARKS[mark]}</span>'
        f'<span class="word">{esc(word)}</span>'
        f'<span class="why">{esc(why)}</span></li>'
        for mark, word, color, why in STATES.values())
    kinds = "".join(
        f'<li><span class="mark kind-mark">{esc(k[:1].upper())}</span>'
        f'<span class="word"><span class="kind">{esc(k)}</span></span>'
        f'<span class="why">{esc(v)}</span></li>'
        for k, v in KINDS.items())
    total = sum(totals.values())
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>J1 retrieval prototype &mdash; local-meeting-notes</title>
<style>
  :root {{
      {css_vars}
      --ui: Inter, -apple-system, BlinkMacSystemFont, 'SF Pro Text', system-ui, sans-serif;
      --mono: 'JetBrains Mono', 'SF Mono', ui-monospace, Menlo, monospace;
  }}
  /* Dark-first, single mode, per DESIGN.md. No light theme by decision. */
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: var(--surface-base); color: var(--neutral-100);
         font: 13px/1.55 var(--ui); }}
  .wrap {{ max-width: 1240px; margin: 0 auto; padding: 32px 24px 80px; }}
  h1 {{ font-size: 24px; margin: 0 0 8px; }}
  h2 {{ font-size: 18px; margin: 48px 0 4px; }}
  h3 {{ font-size: 15px; margin: 0 0 4px; }}
  h4 {{ font-size: 12px; text-transform: uppercase; letter-spacing: .07em;
        color: var(--neutral-400); margin: 0 0 8px; font-weight: 600; }}
  .lede {{ color: var(--neutral-300); max-width: 74ch; margin: 0 0 4px; }}
  /* Focus rings are a high-contrast neutral outline, never the accent: the accent
     means live capture, and an accent ring would put that colour under the cursor on
     every tab press. */
  :focus-visible {{ outline: 2px solid var(--neutral-50); outline-offset: 2px; }}

  .annot {{ font-size: 11px; line-height: 1.5; color: var(--neutral-400);
            border-left: 2px solid var(--neutral-700); padding: 6px 0 6px 10px;
            margin: 8px 0 14px; max-width: 78ch; }}
  .annot-tag {{ display: inline-block; font-family: var(--mono); font-size: 10px;
                text-transform: uppercase; letter-spacing: .06em;
                color: var(--neutral-200); background: var(--surface-overlay);
                border-radius: 2px; padding: 1px 6px; margin-right: 8px; }}

  .legend {{ list-style: none; margin: 16px 0 0; padding: 14px 16px; display: grid;
             gap: 8px; background: var(--surface-raised); border-radius: 6px; }}
  .legend li {{ display: grid; grid-template-columns: 18px 170px 1fr; gap: 10px;
                align-items: baseline; font-size: 12px; }}
  .legend.kinds {{ margin-top: 10px; }}
  .kind-mark {{ color: var(--neutral-500); }}
  .mark {{ color: var(--state); font-family: var(--mono); }}
  .word {{ color: var(--neutral-100); }}
  .why {{ color: var(--neutral-400); }}

  .lib {{ list-style: none; margin: 0; padding: 0; border-radius: 6px;
          background: var(--surface-raised); overflow: hidden; }}
  /* One layout at every width. A five-column row squeezed the trust bar into 320px
     while this surface's whole job is trust at a glance, so identity sits on one line
     and the bar gets the full row underneath. Fewer rules, and the wider bar is the
     more legible of the two. */
  .lib-row {{ padding: 12px 16px; border-top: 1px solid var(--surface-base); }}
  .lib-row:first-child {{ border-top: 0; }}
  .lib-ident {{ display: flex; flex-wrap: wrap; gap: 14px; align-items: baseline;
                margin-bottom: 9px; }}
  .lib-trust {{ display: block; max-width: 620px; }}
  .lib-open {{ color: var(--neutral-50); font-weight: 600; text-decoration: none;
               border-bottom: 1px solid var(--neutral-600); }}
  .lib-src, .lib-turns, .lib-date {{ color: var(--neutral-400); font-size: 12px; }}
  .lib-date {{ font-style: italic; }}

  .bar {{ display: flex; height: 6px; border-radius: 3px; overflow: hidden;
          background: var(--neutral-800); }}
  .seg {{ display: block; }}
  .bar-label {{ display: block; font-size: 11px; color: var(--neutral-400);
                margin-top: 5px; }}
  .bar-label strong {{ color: var(--neutral-100); }}
  .bar-empty {{ font-size: 11px; color: var(--neutral-400); }}

  .meeting {{ margin: 40px 0 0; padding-top: 24px;
              border-top: 1px solid var(--neutral-800); }}
  .mhead .meta {{ color: var(--neutral-400); font-size: 12px; margin: 0 0 10px;
                  font-family: var(--mono); }}
  .trust {{ max-width: 380px; margin-bottom: 4px; }}
  .split {{ display: grid; grid-template-columns: 1fr 1fr; gap: 28px;
            align-items: start; margin-top: 18px; }}
  /* The evidence column stays put while the claims scroll past it. A note has far
     more claims than the transcript pane is tall — 83 on the longest meeting — so
     without this the right half of the surface is empty for most of its height, and
     checking a claim against the words means scrolling back up to find the pane. The
     two things this surface exists to show side by side have to stay side by side. */
  .col-evidence {{ position: sticky; top: 16px; }}

  .claims {{ list-style: none; margin: 0; padding: 0; }}
  .claim {{ background: var(--surface-raised); border-radius: 6px; padding: 12px 14px;
            margin-bottom: 10px; }}
  .claim-text {{ margin: 0 0 7px; color: var(--neutral-100); }}
  .kind {{ font-family: var(--mono); font-size: 10px; text-transform: uppercase;
           letter-spacing: .06em; color: var(--neutral-400);
           background: var(--surface-base); border-radius: 2px; padding: 1px 5px;
           margin-right: 8px; vertical-align: 1px; }}
  .claim-state {{ margin: 0; font-size: 11px; display: grid;
                  grid-template-columns: 14px auto 1fr; gap: 7px;
                  align-items: baseline; }}
  .claim-state .mark {{ color: var(--state); }}
  .claim-state .word {{ color: var(--state); white-space: nowrap; }}
  .support {{ margin: 8px 0 0; font-size: 11px; line-height: 1.5; }}
  .support.no {{ color: var(--semantic-error); }}
  .support.yes {{ color: var(--neutral-200); }}
  .support.unmeasured {{ color: var(--neutral-500); font-style: italic; }}
  .support .by {{ color: var(--neutral-500); font-style: normal; }}
  .quote {{ margin: 9px 0 0; padding: 8px 10px; background: var(--surface-base);
            border-left: 2px solid var(--state); border-radius: 0 4px 4px 0;
            font-family: var(--mono); font-size: 12px; color: var(--neutral-200); }}
  .at {{ font: inherit; color: var(--neutral-50); background: var(--surface-overlay);
         border: 0; border-radius: 2px; padding: 1px 6px; margin-right: 8px;
         cursor: pointer; }}
  .evidence-part {{ color: var(--neutral-500); font-size: 10px;
                    text-transform: uppercase; letter-spacing: .04em;
                    margin-right: 8px; }}
  .turns {{ list-style: none; margin: 0; padding: 8px 0; max-height: 620px;
            overflow-y: auto; background: var(--surface-raised); border-radius: 6px;
            counter-reset: none; }}
  .turn {{ display: grid; grid-template-columns: 46px 1fr; gap: 10px;
           padding: 4px 14px; font-size: 12px; }}
  .turn .tt {{ font-family: var(--mono); color: var(--neutral-500); font-size: 11px; }}
  .turn .who {{ display: none; }}
  .turn .text {{ color: var(--neutral-300); font-family: var(--mono);
                 line-height: 1.5; }}
  .turn.cited .text {{ color: var(--neutral-50); }}
  .turn.cited {{ background: var(--surface-overlay); }}
  .turn.flash {{ outline: 2px solid var(--neutral-50); outline-offset: -2px; }}

  .specimen {{ margin: 48px 0 0; padding-top: 24px;
               border-top: 1px solid var(--neutral-800); }}
  .banner {{ background: var(--surface-raised); border-radius: 6px; padding: 16px 18px;
             max-width: 78ch; }}
  .banner-lead {{ margin: 0 0 10px; color: var(--neutral-50); font-size: 15px; }}
  .banner-facts {{ list-style: none; margin: 0 0 12px; padding: 0; display: grid;
                   gap: 7px; }}
  .banner-facts li {{ font-size: 12px; color: var(--neutral-200); }}
  .banner-facts strong {{ font-family: var(--mono); color: var(--neutral-50); }}
  .banner-facts .src {{ color: var(--neutral-500); font-size: 11px; }}
  .banner-tail {{ margin: 0; font-size: 12px; color: var(--neutral-300); }}

  .encounter {{ margin: 28px 0 42px; border: 1px solid var(--neutral-700);
                background: var(--surface-raised); border-radius: 6px; }}
  .encounter-head {{ display: grid; grid-template-columns: 1fr auto; gap: 28px;
                     align-items: start; padding: 18px 18px 14px; }}
  .encounter h2 {{ margin: 0 0 4px; font-size: 18px; }}
  .encounter h3 {{ font-size: 15px; margin: 0 0 7px; }}
  .eyebrow {{ margin: 0 0 5px; color: var(--neutral-400); font-family: var(--mono);
              font-size: 10px; letter-spacing: .08em; text-transform: uppercase; }}
  .menubar {{ min-width: 140px; display: grid; grid-template-columns: 25px 1fr;
              gap: 2px 8px; align-items: center; padding: 9px 10px;
              border: 1px solid var(--neutral-600); border-radius: 4px;
              font: 11px/1.2 var(--mono); }}
  .menubar-label {{ grid-column: 1 / -1; color: var(--neutral-500); font-size: 9px;
                    text-transform: uppercase; letter-spacing: .08em; }}
  .menubar-glyph {{ font-size: 20px; line-height: 1; color: var(--neutral-200); }}
  .menubar strong {{ color: var(--neutral-100); font-weight: 600; }}
  .menubar .glyph-recording, .menubar .glyph-degraded {{ color: var(--accent); }}
  .menubar .glyph-error {{ color: var(--semantic-error); }}
  .encounter-controls {{ display: flex; gap: 6px; flex-wrap: wrap; padding: 0 18px 14px;
                        border-bottom: 1px solid var(--neutral-700); }}
  .encounter button {{ background: var(--surface-overlay); border: 1px solid var(--neutral-600);
                       border-radius: 3px; color: var(--neutral-100); cursor: pointer;
                       font: 11px/1.3 var(--ui); padding: 6px 9px; }}
  .encounter button:hover {{ border-color: var(--neutral-300); }}
  .encounter button:disabled {{ cursor: not-allowed; color: var(--neutral-500);
                                border-color: var(--neutral-700); }}
  .encounter-panel {{ min-height: 180px; padding: 18px; }}
  .encounter-panel > p {{ color: var(--neutral-300); max-width: 72ch; margin: 0 0 12px; }}
  .panel-actions {{ display: flex; flex-wrap: wrap; gap: 8px; }}
  .setup-status {{ display: grid; gap: 7px; max-width: 520px; margin: 12px 0; }}
  .setup-status p {{ display: grid; grid-template-columns: 190px 1fr; gap: 12px;
                     margin: 0; padding: 7px 9px; background: var(--surface-base);
                     color: var(--neutral-300); }}
  .setup-status strong {{ color: var(--neutral-100); }}
  .setup-list {{ max-width: 72ch; color: var(--neutral-300); }}
  .setup-list li {{ margin-bottom: 7px; }}
  .attestation {{ display: block; max-width: 640px; margin: 14px 0; padding: 12px;
                  border: 1px solid var(--neutral-600); color: var(--neutral-100); }}
  .retention-choice, .notice-choice, .negative-choice, .voice-policy-choice {{
    display: grid; gap: 8px; max-width: 620px; margin: 14px 0; padding: 12px;
    border: 1px solid var(--neutral-600); }}
  .retention-choice legend, .notice-choice legend, .negative-choice legend,
  .voice-policy-choice legend {{ color: var(--neutral-200); }}
  .retention-choice label, .notice-choice label, .negative-choice label,
  .voice-policy-choice label {{ color: var(--neutral-300); }}
  .voice-policy-choice label {{ display: grid; grid-template-columns: auto 1fr;
                                column-gap: 8px; padding: 8px 0;
                                border-bottom: 1px solid var(--neutral-700); }}
  .voice-policy-choice label:last-child {{ border-bottom: 0; }}
  .voice-policy-choice input {{ grid-row: 1 / span 2; }}
  .voice-policy-choice strong {{ color: var(--neutral-100); }}
  .voice-policy-choice span {{ color: var(--neutral-400); font: 11px/1.45 var(--mono); }}
  .state-result {{ color: var(--neutral-200) !important; border-left: 2px solid var(--neutral-500);
                   padding-left: 9px; }}
  .countdown {{ font: 24px/1 var(--mono); color: var(--neutral-50) !important; }}
  .meter {{ display: flex; align-items: end; gap: 3px; height: 24px; }}
  .meter span {{ display: block; width: 5px; background: var(--accent); }}
  .meter span:nth-child(1) {{ height: 6px; }} .meter span:nth-child(2) {{ height: 13px; }}
  .meter span:nth-child(3) {{ height: 20px; }} .meter span:nth-child(4) {{ height: 16px; }}
  .meter span:nth-child(5) {{ height: 10px; }} .meter span:nth-child(6) {{ height: 5px; }}
  .withheld-turn {{ display: grid; gap: 4px; max-width: 600px; padding: 10px 12px;
                    background: var(--surface-base); border-left: 2px solid var(--neutral-400);
                    font: 12px/1.45 var(--mono); color: var(--neutral-300); }}
  .withheld-turn strong {{ color: var(--neutral-100); font-size: 11px; }}
  .withheld-turn.restored {{ border-left-color: var(--semantic-info); }}
  .confirm-box {{ max-width: 620px; margin: 12px 0; padding: 12px;
                  border: 1px solid var(--semantic-error); background: var(--surface-base); }}
  .confirm-box strong {{ color: var(--neutral-50); }}
  .confirm-box p {{ color: var(--neutral-300); margin: 6px 0 10px; }}
  .specimen-new-note {{ display: none; border: 1px solid var(--neutral-600);
                         background: var(--surface-overlay); margin-bottom: 10px; }}
  .specimen-new-note.is-visible {{ display: block; }}
  .lib-review {{ margin-top: 8px; padding: 5px 8px; color: var(--neutral-100);
                 background: var(--surface-base); border: 1px solid var(--neutral-600);
                 border-radius: 3px; cursor: pointer; }}
  .displayed-note-state {{ max-width: 78ch; padding: 8px 10px;
                           border-left: 2px solid var(--semantic-info);
                           color: var(--neutral-300); background: var(--surface-raised); }}
  .displayed-note-state.is-stale {{ border-left-color: var(--semantic-error);
                                    color: var(--neutral-100); }}

  .open ul {{ max-width: 80ch; color: var(--neutral-300); }}
  .open li {{ margin-bottom: 9px; }}
  .open strong {{ color: var(--neutral-100); }}
  @media (max-width: 980px) {{
    .split {{ grid-template-columns: 1fr; }}
    .encounter-head {{ grid-template-columns: 1fr; }}
  }}
</style></head>
<body><div class="wrap">

<h1>The retrieval path, as far as real content can settle it</h1>
<p class="lede">Three weeks after a call the operator needs a decision they half
  remember. They know the subject, not the date. <strong>Journey J1</strong> from
  <code>docs/journeys.md</code>, built to answer two design questions: what a note
  has to look like for a claim to be trustworthy, and whether a weak note is
  visible before it is opened.</p>
<p class="lede">Every claim, quote, timestamp and count on this page was produced by
  a real model run over a real transcript. {total} claims across {meetings}
  {"meeting" if meetings == 1 else "meetings"}. Nothing here invents a meeting, and
  the regions the corpus cannot populate say so in place.</p>

{encounter()}

<ul class="legend">{legend}</ul>

<ul class="legend kinds">{kinds}</ul>

<h2>The library</h2>
<p class="lede">Filing is already settled &mdash; folders, chronological within them,
  from the market check in <code>journeys.md</code>. So the only question left for
  this surface is the one that decides whether the corpus is useful in six months:
  <strong>can you tell a note is weak without opening it?</strong></p>
{note_annotation("real data",
                 "Three meetings, which is enough to populate this honestly and not "
                 "enough to test search. No search box is drawn: one that ranked "
                 "three results would look settled while resting on nothing.")}
{note_annotation("open question",
                 "The date column reads <em>no date</em> because corpus meetings "
                 "carry none. A real capture records <code>captured_at</code>, so "
                 "this is a limit of the material and not of the product &mdash; but "
                 "it does mean chronological ordering is untested here.")}
<ul class="lib">
  <li class="lib-row specimen-new-note" id="specimen-new-note">
    <span class="lib-ident"><strong>new note</strong><span class="lib-src">interaction
      specimen</span>
      <span class="lib-turns">no meeting content asserted</span></span>
    <span class="bar-label">This row appears only after the specimen reaches its
      ready state. It does not stand in for a captured meeting.</span>
    <button type="button" class="lib-review" data-action="open-real-data-detail">
      review real-data detail treatment
    </button>
  </li>
  {library}
</ul>

<div id="real-data-detail">
  <h2>The note, and the words behind it</h2>
  <p class="displayed-note-state" id="displayed-note-state">
    Displayed note: current for its stored baseline transcript.
  </p>
</div>
{sections}

{specimen()}

<section class="open">
  <h2>What this settles, and what it does not</h2>
  <ul>
    <li><strong>Settled: a claim's evidence state is part of the claim.</strong> Not a
      hover, not a detail view. On a long meeting most claims fail their citation
      check, so a format that only renders located evidence would have been designed
      against a fraction of its own content.</li>
    <li><strong>Settled: read order, not trust order.</strong> Sorting claims by
      trust would hide the shape of the note, which is the failure
      <code>journeys.md</code> describes as lying by omission.</li>
    <li><strong>Settled: the claim &rarr; words path needs no audio.</strong> The
      timestamp button resolves a quote to its turn using only the retained
      transcript, so deleting audio costs confirmation of tone, not the check.</li>
    <li><strong>Not settled: search.</strong> Three meetings cannot rank. The market
      check says search must cover the transcript and metadata rather than the notes
      alone, and that is a decision, not a tested design.</li>
    <li><strong>Specimen only: correction has the required consequence.</strong> J4.
      Restoring withheld speech marks the note stale and regeneration is a separate
      action. QMSum has no gated turn, so this settles the transition and not whether
      correction works on a real capture.</li>
    <li><strong>Not settled by any prototype: whether the notes are good.</strong>
      That needs the dogfood run, and no fixture substitutes for it.</li>
  </ul>
</section>

</div>
<script>
  // The claim-to-words path. The turn index was derived by locating the quote in the
  // transcript, never supplied by the model, so this cannot land on the wrong words.
  document.addEventListener('click', function (e) {{
    var b = e.target.closest('.at');
    if (!b) return;
    var el = document.getElementById('t-' + b.dataset.meeting + '-' + b.dataset.turn);
    if (!el) return;
    el.scrollIntoView({{block: 'center', behavior: 'smooth'}});
    document.querySelectorAll('.turn.flash').forEach(function (n) {{
      n.classList.remove('flash');
    }});
    el.classList.add('flash');
  }});

  // Interaction specimens use one state switcher. The panels declare their menubar
  // reading in markup, so a new state cannot be wired only in JavaScript and leave the
  // primary status ambiguous. Nothing below fabricates transcript or note content.
  // BEGIN ENROLLMENT STATE MACHINE
  var ENROLLMENT_TRANSITIONS = Object.freeze({{
    blocked: Object.freeze({{
      'save-first': 'first-sitting-saved',
      'load-returning-profile': 'returning-valid-profile'
    }}),
    'first-sitting-saved': Object.freeze({{
      'resume-after-gap': 'resume-after-gap',
      discard: 'blocked'
    }}),
    'resume-after-gap': Object.freeze({{
      'review-second': 'second-sitting-review',
      discard: 'blocked'
    }}),
    'second-sitting-review': Object.freeze({{
      'review-negative': 'negative-sample',
      discard: 'blocked'
    }}),
    'negative-sample': Object.freeze({{
      'measurements-ready': 'operating-point',
      discard: 'blocked'
    }}),
    'operating-point': Object.freeze({{
      'select-policy': 'ready-to-build',
      discard: 'blocked'
    }}),
    'ready-to-build': Object.freeze({{
      'build-profile': 'building-profile',
      discard: 'blocked'
    }}),
    'building-profile': Object.freeze({{
      'persist-profile-success': 'enrolled',
      discard: 'blocked'
    }}),
    enrolled: Object.freeze({{
      reset: 'blocked'
    }}),
    'returning-valid-profile': Object.freeze({{
      reset: 'blocked'
    }})
  }});
  function nextEnrollmentState(state, event) {{
    var available = ENROLLMENT_TRANSITIONS[state];
    if (!available || !available[event]) {{
      throw new Error('invalid enrollment transition: ' + state + ' + ' + event);
    }}
    return available[event];
  }}
  function enrollmentEventEnabled(state, event) {{
    var available = ENROLLMENT_TRANSITIONS[state];
    return Boolean(available && available[event]);
  }}
  function enrollmentHasValidProfile(state) {{
    return state === 'enrolled' || state === 'returning-valid-profile';
  }}
  // END ENROLLMENT STATE MACHINE

  var panels = Array.prototype.slice.call(document.querySelectorAll('.encounter-panel'));
  var glyphs = {{
    idle: ['○', 'idle', 'glyph-idle'],
    detected: ['◎', 'detected', 'glyph-detected'],
    armed: ['◌', 'armed', 'glyph-armed'],
    recording: ['●', 'recording', 'glyph-recording'],
    degraded: ['●!', 'degraded', 'glyph-degraded'],
    transcribing: ['≋', 'transcribing', 'glyph-transcribing'],
    error: ['X', 'processing failed', 'glyph-error']
  }};
  function showPanel(id) {{
    var next = document.getElementById(id);
    if (!next || !next.classList.contains('encounter-panel')) return;
    panels.forEach(function (panel) {{
      var active = panel === next;
      panel.hidden = !active;
      panel.classList.toggle('is-active', active);
    }});
    var state = next.dataset.menubar || 'idle';
    var reading = glyphs[state] || glyphs.idle;
    var glyph = document.getElementById('menubar-glyph');
    glyph.textContent = reading[0];
    glyph.className = 'menubar-glyph ' + reading[2];
    document.getElementById('menubar-word').textContent = reading[1];
  }}
  // BEGIN CAPTURE DOM CONTRACT
  var enrollmentState = 'blocked';
  var grantedPermissions = new Set();
  var selectedRetention = null;
  var selectedPolicyTarget = null;
  var discardOriginPanel = null;
  var captureAttemptActive = false;
  function captureReady() {{
    return enrollmentHasValidProfile(enrollmentState)
      && grantedPermissions.has('microphone')
      && grantedPermissions.has('system')
      && Boolean(selectedRetention);
  }}
  function resetCaptureConsent() {{
    captureAttemptActive = false;
    var attestation = document.getElementById('participant-attested');
    attestation.checked = false;
    document.querySelector('[data-requires-attestation]').disabled = true;
    document.getElementById('attestation-result').textContent =
      'Attestation required.';
  }}
  function recordCaptureAttestation(checked) {{
    document.querySelector('[data-requires-attestation]').disabled =
      !(captureAttemptActive && checked);
    document.getElementById('attestation-result').textContent =
      captureAttemptActive
        ? (checked
          ? 'Operator attestation recorded for this capture attempt.'
          : 'Attestation required.')
        : 'Start a ready capture attempt before attesting.';
  }}
  function clearEnrollmentChoices() {{
    selectedPolicyTarget = null;
    document.querySelectorAll('input[name="voice-policy"]')
      .forEach(function (input) {{
        input.checked = false;
      }});
    document.querySelectorAll('input[name="negative-source"]')
      .forEach(function (input) {{
        input.checked = false;
      }});
    document.getElementById('negative-material-result').textContent =
      'No allowed source selected.';
    document.getElementById('voice-policy-result').textContent =
      'No measured policy selected.';
    document.getElementById('ready-policy-result').textContent =
      'No profile build is pending.';
  }}
  function renderEnrollmentState() {{
    var allowed = captureReady();
    var negativeSource = document.querySelector(
      'input[name="negative-source"]:checked'
    );
    var selectedPolicy = document.querySelector(
      'input[name="voice-policy"]:checked'
    );
    var start = document.getElementById('manual-capture');
    start.disabled = !allowed;
    start.textContent = allowed
      ? 'start capture manually'
      : 'start capture — setup required';
    var missing = [];
    if (!enrollmentHasValidProfile(enrollmentState)) missing.push('valid profile');
    if (!grantedPermissions.has('microphone')) missing.push('microphone permission');
    if (!grantedPermissions.has('system')) missing.push('system-audio permission');
    if (!selectedRetention) missing.push('meeting-audio retention');
    document.getElementById('capture-eligibility').textContent = allowed
      ? 'Supported capture ready: valid profile, both current permissions, and '
        + 'meeting-audio retention are present.'
      : 'Supported capture unavailable: missing ' + missing.join(', ') + '.';
    document.getElementById('future-consent').disabled = !allowed;
    document.querySelectorAll('button[data-enrollment-event]')
      .forEach(function (button) {{
        var eventAllowed = enrollmentEventEnabled(
          enrollmentState,
          button.dataset.enrollmentEvent
        );
        if (button.id === 'load-operating-fixture') {{
          eventAllowed = eventAllowed && Boolean(negativeSource);
        }}
        if (button.id === 'continue-selected-policy') {{
          eventAllowed = eventAllowed
            && Boolean(selectedPolicy)
            && selectedPolicy.dataset.target === selectedPolicyTarget;
        }}
        button.disabled = !eventAllowed;
      }});
    document.querySelectorAll('input[name="voice-policy"]')
      .forEach(function (input) {{
        input.disabled = enrollmentState !== 'operating-point';
      }});
  }}
  function recordPermission(permission) {{
    grantedPermissions.add(permission);
    document.getElementById('permission-' + permission).textContent =
      'granted-state specimen';
    var remaining = 2 - grantedPermissions.size;
    document.getElementById('permissions-result').textContent = remaining
      ? remaining + ' permission' + (remaining === 1 ? '' : 's') + ' still needed.'
      : 'Both required permission states reviewed. No macOS grant changed.';
    document.querySelector('[data-requires-permissions]').disabled = remaining > 0;
    renderEnrollmentState();
  }}
  function chooseRetention(period) {{
    resetCaptureConsent();
    selectedRetention = period;
    document.getElementById('retention-result').textContent =
      period + ' selected for this specimen. No recommendation is implied.';
    document.getElementById('consent-retention').textContent =
      'Meeting audio retention: ' + period + '. Transcript and note: held until '
      + 'this meeting is deleted.';
    document.querySelector('[data-requires-retention]').disabled = false;
    renderEnrollmentState();
  }}
  function loadReturningPrerequisitesFixture() {{
    recordPermission('microphone');
    recordPermission('system');
    var retention = document.querySelector(
      'input[name="retention-period"][value="90 days"]'
    );
    retention.checked = true;
    chooseRetention(retention.value);
  }}
  function beginCaptureAttempt() {{
    resetCaptureConsent();
    if (!captureReady()) return false;
    captureAttemptActive = true;
    showPanel('spec-consent');
    return true;
  }}
  function cancelCaptureAttempt(panel) {{
    resetCaptureConsent();
    showPanel(panel || 'spec-library');
  }}
  function completeCaptureAttempt() {{
    resetCaptureConsent();
  }}
  function resetProfileFixture() {{
    resetCaptureConsent();
    enrollmentState = enrollmentHasValidProfile(enrollmentState)
      ? nextEnrollmentState(enrollmentState, 'reset')
      : 'blocked';
    clearEnrollmentChoices();
    renderEnrollmentState();
    showPanel('spec-enrollment-blocked');
  }}
  function openDiscard(originPanel) {{
    discardOriginPanel = originPanel;
    showPanel('spec-discard-enrollment');
  }}
  function cancelDiscard() {{
    document.getElementById('discard-enrollment-confirm').hidden = true;
    document.getElementById('discard-result').textContent =
      'Discard cancelled. Incomplete enrollment material remains in this specimen.';
    showPanel(discardOriginPanel || 'spec-enrollment-blocked');
  }}
  // END CAPTURE DOM CONTRACT

  function showRatesFromFixture() {{
    document.querySelectorAll('input[name="voice-policy"]').forEach(function (input) {{
      var row = input.parentElement.querySelector('span');
      row.textContent =
        'Fixture measured: my speech dropped '
        + (Number(input.dataset.operatorRate) * 100).toFixed(1)
        + '% · negative speech admitted '
        + (Number(input.dataset.negativeRate) * 100).toFixed(1)
        + '% · choose with --target-frr '
        + Number(input.dataset.target).toFixed(2);
    }});
  }}
  var eventPanels = {{
    'save-first': 'spec-first-sitting-saved',
    'resume-after-gap': 'spec-resume-after-gap',
    'review-second': 'spec-second-sitting-review',
    'review-negative': 'spec-negative-sample',
    'measurements-ready': 'spec-operating-point',
    'select-policy': 'spec-ready-to-build',
    'build-profile': 'spec-building-profile',
    'persist-profile-success': 'spec-enrolled',
    'load-returning-profile': 'spec-returning-profile',
    discard: 'spec-enrollment-blocked'
  }};
  document.querySelectorAll('button[data-enrollment-event]')
    .forEach(function (button) {{
      button.addEventListener('click', function () {{
        var event = button.dataset.enrollmentEvent;
        enrollmentState = nextEnrollmentState(enrollmentState, event);
        if (event === 'measurements-ready') showRatesFromFixture();
        if (event === 'discard') clearEnrollmentChoices();
        renderEnrollmentState();
        showPanel(eventPanels[event]);
      }});
    }});
  document.getElementById('manual-capture').addEventListener('click', function () {{
    beginCaptureAttempt();
  }});
  renderEnrollmentState();
  document.addEventListener('click', function (e) {{
    var button = e.target.closest('button[data-panel]');
    if (!button || button.disabled) return;
    if (button.dataset.panel === 'spec-consent') resetCaptureConsent();
    showPanel(button.dataset.panel);
  }});
  document.querySelectorAll('button[data-permission]').forEach(function (button) {{
    button.addEventListener('click', function () {{
      recordPermission(button.dataset.permission);
    }});
  }});
  document.querySelectorAll('input[name="retention-period"]').forEach(function (input) {{
    input.addEventListener('change', function () {{
      chooseRetention(input.value);
    }});
  }});
  document.querySelectorAll('input[name="negative-source"]').forEach(function (input) {{
    input.addEventListener('change', function () {{
      document.getElementById('negative-material-result').textContent =
        'Allowed source selected for interaction review. No recording is made, and '
        + 'no compliance result is claimed.';
      renderEnrollmentState();
    }});
  }});
  document.querySelectorAll('input[name="voice-policy"]').forEach(function (input) {{
    input.addEventListener('change', function () {{
      selectedPolicyTarget = input.dataset.target;
      document.getElementById('voice-policy-result').textContent =
        'Fixture policy selected for review: my speech dropped '
        + (Number(input.dataset.operatorRate) * 100).toFixed(1)
        + '%, negative speech admitted '
        + (Number(input.dataset.negativeRate) * 100).toFixed(1)
        + '%. No profile is built.';
      document.getElementById('ready-policy-result').textContent =
        'Selected fixture target ' + Number(input.dataset.target).toFixed(2)
        + ' with both measured costs. Build and persistence have not run.';
      renderEnrollmentState();
    }});
  }});
  document.getElementById('participant-attested').addEventListener('change', function (e) {{
    recordCaptureAttestation(e.target.checked);
  }});
  document.getElementById('load-returning-prerequisites')
    .addEventListener('click', loadReturningPrerequisitesFixture);
  document.getElementById('future-consent')
    .addEventListener('click', beginCaptureAttempt);
  document.getElementById('cancel-capture-attempt')
    .addEventListener('click', function () {{
      cancelCaptureAttempt('spec-library');
  }});
  document.getElementById('cancel-armed')
    .addEventListener('click', function () {{
      cancelCaptureAttempt('spec-library');
  }});
  document.querySelectorAll('button[data-discard-origin]')
    .forEach(function (button) {{
      button.addEventListener('click', function () {{
        openDiscard(button.dataset.discardOrigin);
      }});
  }});
  document.querySelectorAll('input[name="far-end"]').forEach(function (input) {{
    input.addEventListener('change', function () {{
      document.getElementById('notice-result').textContent =
        'Policy selection is deliberately not stored by this prototype.';
    }});
  }});
  document.getElementById('restore-turn').addEventListener('click', function () {{
    document.getElementById('withheld-turn').classList.add('restored');
    document.getElementById('correction-result').textContent =
      'Displayed note: stale — restored speech is not reflected until regeneration.';
    document.getElementById('displayed-note-state').textContent =
      'Displayed note: stale — a withheld turn was restored. Regenerate before use.';
    document.getElementById('displayed-note-state').classList.add('is-stale');
    document.getElementById('regenerate-note').disabled = false;
  }});
  document.getElementById('regenerate-note').addEventListener('click', function () {{
    document.getElementById('correction-result').textContent =
      'Displayed note: current-state transition completed as an interaction specimen.';
    document.getElementById('displayed-note-state').textContent =
      'Displayed note: current-state specimen. No QMSum note was regenerated or changed.';
    document.getElementById('displayed-note-state').classList.remove('is-stale');
    document.getElementById('regenerate-note').disabled = true;
  }});
  document.getElementById('delete-audio-now').addEventListener('click', function () {{
    document.getElementById('delete-audio-confirm').hidden = false;
  }});
  document.getElementById('cancel-delete-audio').addEventListener('click', function () {{
    document.getElementById('delete-audio-confirm').hidden = true;
    document.getElementById('audio-result').textContent =
      'Audio deletion cancelled. Audio files remain held in this specimen.';
  }});
  document.getElementById('confirm-delete-audio').addEventListener('click', function () {{
    document.getElementById('delete-audio-confirm').hidden = true;
    document.getElementById('audio-result').textContent =
      'Audio deleted in the interaction specimen. Note, transcript, claim evidence, '
      + 'and voice profile remain; no local file changed.';
  }});
  document.getElementById('delete-meeting-now').addEventListener('click', function () {{
    document.getElementById('delete-meeting-confirm').hidden = false;
  }});
  document.getElementById('cancel-delete-meeting').addEventListener('click', function () {{
    document.getElementById('delete-meeting-confirm').hidden = true;
    document.getElementById('meeting-result').textContent =
      'Meeting deletion cancelled. Note, transcript, evidence, and audio remain.';
  }});
  document.getElementById('confirm-delete-meeting')
    .addEventListener('click', function () {{
      document.getElementById('delete-meeting-confirm').hidden = true;
      document.getElementById('meeting-result').textContent =
        'Meeting deleted in the interaction specimen. Other meetings and the voice '
        + 'profile remain; no local file changed.';
  }});
  document.getElementById('reset-profile-now').addEventListener('click', function () {{
    document.getElementById('reset-profile-confirm').hidden = false;
  }});
  document.getElementById('cancel-reset-profile').addEventListener('click', function () {{
    document.getElementById('reset-profile-confirm').hidden = true;
    document.getElementById('profile-result').textContent =
      'Profile reset cancelled. The profile remains in this interaction specimen.';
  }});
  document.getElementById('confirm-reset-profile')
    .addEventListener('click', function () {{
      document.getElementById('reset-profile-confirm').hidden = true;
      resetProfileFixture();
      document.getElementById('profile-result').textContent =
        'Profile deleted in the interaction specimen. Existing meetings remain; '
        + 'application capture is blocked until re-enrollment. Only the research CLI '
        + 'may run ungated outside the beta. No local file changed.';
  }});
  document.getElementById('discard-enrollment-now').addEventListener('click', function () {{
    document.getElementById('discard-enrollment-confirm').hidden = false;
  }});
  document.getElementById('cancel-discard-enrollment')
    .addEventListener('click', cancelDiscard);
  document.getElementById('confirm-discard-enrollment')
    .addEventListener('click', function () {{
      document.getElementById('discard-enrollment-confirm').hidden = true;
      document.getElementById('discard-result').textContent =
        'Incomplete enrollment discarded in the interaction specimen. Meetings and '
        + 'any previously valid profile remain; no local file changed.';
  }});
  document.querySelectorAll('[data-action="manual-stop"]')
    .forEach(function (button) {{
      button.addEventListener('click', completeCaptureAttempt);
  }});
  document.querySelector('[data-action="finish-processing"]')
    .addEventListener('click', function () {{
      document.getElementById('specimen-new-note').classList.add('is-visible');
      completeCaptureAttempt();
    }});
  document.querySelectorAll('[data-action="open-real-data-detail"]')
    .forEach(function (button) {{
      button.addEventListener('click', function () {{
        showPanel('spec-library');
        document.getElementById('real-data-detail').scrollIntoView({{block: 'start'}});
      }});
    }});
</script>
</body></html>
'''


def check_wiring(page_html: str) -> int:
    """Every locator button must target an element that exists on the page.

    `check_locators` proves the *data* is right — that turn N holds the quote cited for
    it. This proves the *markup* is right, and they are different failures. If the id a
    button builds and the id a turn carries ever disagree, the data stays correct and
    every button silently does nothing: no error, no console message, just a page that
    does not move. Two id spellings derived independently is the same shape as the two
    parsers and the two verdict formulas, so it gets the same treatment.
    """
    targets = set(re.findall(r'<li class="turn[^"]*" id="([^"]+)"', page_html))
    wanted = [f"t-{m}-{t}" for m, t in
              re.findall(r'<button class="at" data-meeting="([^"]+)" data-turn="(\d+)"',
                         page_html)]
    missing = [w for w in wanted if w not in targets]
    if missing:
        raise SystemExit(
            f"{len(missing)} locator button(s) point at ids that are not on the page, "
            f"e.g. {missing[:3]}. The claim data may be correct while every button "
            f"does nothing."
        )
    return len(wanted)


def check_enrollment_js(page_html: str) -> int:
    """Execute the enrollment transition function, independent of browser markup.

    String presence cannot prove that Start enables after a valid-profile load and
    disables again on reset. The state machine is deliberately pure so Node can run
    those exact transitions without a browser or a fake DOM.
    """
    match = re.search(
        r"// BEGIN ENROLLMENT STATE MACHINE(.*?)// END ENROLLMENT STATE MACHINE",
        page_html,
        re.DOTALL,
    )
    if not match:
        raise SystemExit("enrollment JavaScript state machine is missing")
    controls = match.group(1)
    assertions = r"""
const assert = require('node:assert/strict');
let checks = 0;
function equal(actual, expected, message) {
  assert.equal(actual, expected, message);
  checks += 1;
}
function throws(callback, message) {
  assert.throws(callback, message);
  checks += 1;
}
const known = Object.keys(ENROLLMENT_TRANSITIONS);
for (const state of known) {
  equal(
    enrollmentHasValidProfile(state),
    state === 'enrolled' || state === 'returning-valid-profile',
    'valid-profile classification drifted for ' + state
  );
}
let state = 'blocked';
equal(enrollmentHasValidProfile(state), false);
state = nextEnrollmentState(state, 'save-first');
equal(state, 'first-sitting-saved');
state = nextEnrollmentState(state, 'resume-after-gap');
equal(state, 'resume-after-gap');
state = nextEnrollmentState(state, 'review-second');
equal(state, 'second-sitting-review');
state = nextEnrollmentState(state, 'review-negative');
equal(state, 'negative-sample');
state = nextEnrollmentState(state, 'measurements-ready');
equal(state, 'operating-point');
throws(() => nextEnrollmentState(state, 'persist-profile-success'));
state = nextEnrollmentState(state, 'select-policy');
equal(state, 'ready-to-build');
state = nextEnrollmentState(state, 'build-profile');
equal(state, 'building-profile');
equal(enrollmentHasValidProfile(state), false);
state = nextEnrollmentState(state, 'persist-profile-success');
equal(state, 'enrolled');
equal(enrollmentHasValidProfile(state), true);
state = nextEnrollmentState(state, 'reset');
equal(state, 'blocked');
equal(enrollmentHasValidProfile(state), false);
equal(nextEnrollmentState('blocked', 'load-returning-profile'),
      'returning-valid-profile');
equal(enrollmentEventEnabled('negative-sample', 'measurements-ready'), true);
equal(enrollmentEventEnabled('blocked', 'measurements-ready'), false);
equal(nextEnrollmentState('resume-after-gap', 'discard'), 'blocked');
throws(() => nextEnrollmentState('returning-valid-profile', 'discard'));
throws(() => nextEnrollmentState('operating-point', 'load-returning-profile'));
throws(() => nextEnrollmentState('blocked', 'review-second'));
process.stdout.write(String(checks));
"""
    try:
        result = subprocess.run(
            ["node", "-e", controls + assertions],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise SystemExit(f"cannot execute enrollment JavaScript checks: {exc}") from exc
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise SystemExit(f"enrollment JavaScript transition check failed:\n{detail}")
    try:
        return int(result.stdout)
    except ValueError as exc:
        raise SystemExit("enrollment JavaScript check returned no assertion count") from exc


def check_capture_dom_js(page_html: str) -> int:
    """Exercise readiness and capture-attempt state against concrete DOM fields."""
    state = re.search(
        r"// BEGIN ENROLLMENT STATE MACHINE(.*?)// END ENROLLMENT STATE MACHINE",
        page_html,
        re.DOTALL,
    )
    contract = re.search(
        r"// BEGIN CAPTURE DOM CONTRACT(.*?)// END CAPTURE DOM CONTRACT",
        page_html,
        re.DOTALL,
    )
    if not state or not contract:
        raise SystemExit("capture DOM contract or enrollment state machine is missing")
    harness = r"""
const assert = require('node:assert/strict');
let checks = 0;
function equal(actual, expected, message) {
  assert.equal(actual, expected, message);
  checks += 1;
}
function fake(id, extra = {}) {
  return Object.assign({
    id,
    disabled: false,
    checked: false,
    hidden: false,
    textContent: '',
    dataset: {}
  }, extra);
}
const elements = {};
for (const id of [
  'participant-attested', 'attestation-result', 'manual-capture',
  'capture-eligibility', 'future-consent', 'permission-microphone',
  'permission-system', 'permissions-result', 'retention-result',
  'consent-retention', 'discard-enrollment-confirm', 'discard-result'
]) elements[id] = fake(id);
const requiresAttestation = fake('requires-attestation');
const requiresPermissions = fake('requires-permissions');
const requiresRetention = fake('requires-retention');
const negativeInputs = [fake('negative-source')];
const policyInputs = [
  fake('policy-loose', {dataset: {target: '0.05'}}),
  fake('policy-strict', {dataset: {target: '0.20'}})
];
const retentionInputs = [
  fake('retention-30', {value: '30 days'}),
  fake('retention-90', {value: '90 days'})
];
const eventButtons = [
  fake('load-operating-fixture', {
    dataset: {enrollmentEvent: 'measurements-ready'}
  }),
  fake('continue-selected-policy', {
    dataset: {enrollmentEvent: 'select-policy'}
  }),
  fake('build-profile', {dataset: {enrollmentEvent: 'build-profile'}}),
  fake('persist-profile', {
    dataset: {enrollmentEvent: 'persist-profile-success'}
  })
];
let shownPanel = null;
function showPanel(id) { shownPanel = id; }
const document = {
  getElementById(id) {
    if (!elements[id]) elements[id] = fake(id);
    return elements[id];
  },
  querySelector(selector) {
    if (selector === '[data-requires-attestation]') return requiresAttestation;
    if (selector === '[data-requires-permissions]') return requiresPermissions;
    if (selector === '[data-requires-retention]') return requiresRetention;
    if (selector === 'input[name="negative-source"]:checked') {
      return negativeInputs.find((input) => input.checked) || null;
    }
    if (selector === 'input[name="voice-policy"]:checked') {
      return policyInputs.find((input) => input.checked) || null;
    }
    if (selector === 'input[name="retention-period"][value="90 days"]') {
      return retentionInputs[1];
    }
    throw new Error('unhandled querySelector: ' + selector);
  },
  querySelectorAll(selector) {
    if (selector === 'button[data-enrollment-event]') return eventButtons;
    if (selector === 'input[name="voice-policy"]') return policyInputs;
    if (selector === 'input[name="negative-source"]') return negativeInputs;
    throw new Error('unhandled querySelectorAll: ' + selector);
  }
};
"""
    assertions = r"""
renderEnrollmentState();
equal(elements['manual-capture'].disabled, true, 'fresh Start must be blocked');
elements['participant-attested'].checked = true;
recordCaptureAttestation(true);
equal(requiresAttestation.disabled, true,
      'direct Consent review cannot attest without a ready Start attempt');
resetCaptureConsent();

enrollmentState = nextEnrollmentState('blocked', 'load-returning-profile');
renderEnrollmentState();
equal(elements['manual-capture'].disabled, true,
      'a valid returning profile alone must not enable Start');
recordPermission('microphone');
equal(elements['manual-capture'].disabled, true,
      'one permission must not enable Start');
recordPermission('system');
equal(elements['manual-capture'].disabled, true,
      'both permissions without retention must not enable Start');
chooseRetention('30 days');
equal(elements['manual-capture'].disabled, false,
      'profile plus permissions plus retention enables Start');

elements['participant-attested'].checked = true;
requiresAttestation.disabled = false;
equal(beginCaptureAttempt(), true, 'ready Start reaches consent');
equal(shownPanel, 'spec-consent');
equal(elements['participant-attested'].checked, false,
      'every new Start clears prior attestation');
equal(requiresAttestation.disabled, true,
      'every new Start disables Continue');
elements['participant-attested'].checked = true;
recordCaptureAttestation(true);
equal(requiresAttestation.disabled, false,
      'attestation enables Continue only inside the active Start attempt');

requiresAttestation.disabled = false;
cancelCaptureAttempt('spec-library');
equal(shownPanel, 'spec-library');
equal(elements['participant-attested'].checked, false,
      'cancel clears attestation');
equal(requiresAttestation.disabled, true, 'cancel disables Continue');

elements['participant-attested'].checked = true;
requiresAttestation.disabled = false;
completeCaptureAttempt();
equal(elements['participant-attested'].checked, false,
      'completion clears attestation');
equal(requiresAttestation.disabled, true, 'completion disables Continue');

elements['participant-attested'].checked = true;
requiresAttestation.disabled = false;
chooseRetention('90 days');
equal(elements['participant-attested'].checked, false,
      'retention change clears attestation');
equal(requiresAttestation.disabled, true, 'retention change disables Continue');

elements['participant-attested'].checked = true;
requiresAttestation.disabled = false;
resetProfileFixture();
equal(enrollmentState, 'blocked', 'reset removes valid profile state');
equal(elements['participant-attested'].checked, false,
      'profile reset clears attestation');
equal(requiresAttestation.disabled, true, 'profile reset disables Continue');
equal(elements['manual-capture'].disabled, true, 'reset disables Start');
equal(shownPanel, 'spec-enrollment-blocked',
      'reset success is shown on the blocker');

grantedPermissions = new Set();
selectedRetention = null;
enrollmentState = nextEnrollmentState('blocked', 'load-returning-profile');
renderEnrollmentState();
equal(elements['manual-capture'].disabled, true,
      'returning fixture starts with prerequisites absent');
loadReturningPrerequisitesFixture();
equal(retentionInputs[1].checked, true,
      'returning readiness explicitly loads a retention fixture');
equal(grantedPermissions.size, 2,
      'returning readiness explicitly loads both permission fixtures');
equal(elements['manual-capture'].disabled, false,
      'explicit returning prerequisites complete readiness');

enrollmentState = 'operating-point';
grantedPermissions = new Set();
selectedRetention = null;
selectedPolicyTarget = null;
policyInputs.forEach((input) => { input.checked = false; });
renderEnrollmentState();
equal(eventButtons[1].disabled, true,
      'no measured radio selection keeps policy continuation disabled');
equal(elements['manual-capture'].disabled, true,
      'operating point is not a valid profile');
selectedPolicyTarget = policyInputs[0].dataset.target;
renderEnrollmentState();
equal(eventButtons[1].disabled, true,
      'a target variable without a checked radio cannot bypass policy selection');
policyInputs[0].checked = true;
renderEnrollmentState();
equal(eventButtons[1].disabled, false,
      'a checked measured row enables policy continuation');
negativeInputs[0].checked = true;
clearEnrollmentChoices();
renderEnrollmentState();
equal(policyInputs[0].checked, false,
      'discard or reset clears the visible policy selection');
equal(negativeInputs[0].checked, false,
      'discard or reset clears the prior negative-source selection');
equal(eventButtons[1].disabled, true,
      'a cleared policy cannot carry into another enrollment');
selectedPolicyTarget = policyInputs[0].dataset.target;
policyInputs[0].checked = true;
renderEnrollmentState();
enrollmentState = nextEnrollmentState(enrollmentState, 'select-policy');
renderEnrollmentState();
equal(enrollmentState, 'ready-to-build');
equal(elements['manual-capture'].disabled, true,
      'ready-to-build is not a valid profile');
enrollmentState = nextEnrollmentState(enrollmentState, 'build-profile');
renderEnrollmentState();
equal(enrollmentState, 'building-profile');
equal(elements['manual-capture'].disabled, true,
      'build completion without persistence keeps Start blocked');
enrollmentState = nextEnrollmentState(enrollmentState, 'persist-profile-success');
renderEnrollmentState();
equal(enrollmentState, 'enrolled');
equal(elements['manual-capture'].disabled, true,
      'persistence success alone still lacks permissions and retention');
recordPermission('microphone');
recordPermission('system');
chooseRetention('30 days');
equal(elements['manual-capture'].disabled, false,
      'persisted profile plus explicit prerequisites enables Start');

enrollmentState = 'first-sitting-saved';
openDiscard('spec-first-sitting-saved');
equal(shownPanel, 'spec-discard-enrollment');
cancelDiscard();
equal(enrollmentState, 'first-sitting-saved',
      'cancel Discard preserves enrollment state');
equal(shownPanel, 'spec-first-sitting-saved',
      'cancel Discard returns to its origin panel');
process.stdout.write(String(checks));
"""
    try:
        result = subprocess.run(
            ["node", "-e", harness + state.group(1) + contract.group(1) + assertions],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise SystemExit(f"cannot execute capture DOM checks: {exc}") from exc
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise SystemExit(f"capture DOM check failed:\n{detail}")
    try:
        return int(result.stdout)
    except ValueError as exc:
        raise SystemExit("capture DOM check returned no assertion count") from exc


def check_encounter_wiring(page_html: str) -> int:
    """Fail if an interaction state can be named but not reached.

    The review surface is deliberately static, so a dead control would otherwise look
    like a product omission rather than a prototype wiring bug. This checks the
    markup contract rather than attempting to execute browser JavaScript here.
    """
    expected = {
        "spec-library", "spec-first-run", "spec-detected", "spec-consent",
        "spec-enrollment-blocked", "spec-first-sitting-saved",
        "spec-resume-after-gap", "spec-second-sitting-review",
        "spec-negative-sample", "spec-operating-point", "spec-ready-to-build",
        "spec-building-profile", "spec-enrolled",
        "spec-returning-profile", "spec-discard-enrollment",
        "spec-profile-reset", "spec-retention-choice",
        "spec-armed", "spec-recording", "spec-degraded", "spec-transcribing",
        "spec-processing-failed", "spec-note-ready", "spec-correction",
        "spec-retention", "spec-delete-meeting", "spec-far-end",
    }
    panels = set(re.findall(
        r'<section class="encounter-panel[^\"]*"\s+id="([^\"]+)"\s+'
        r'data-menubar="([^\"]+)"',
        page_html,
    ))
    flat_page = re.sub(r"\s+", " ", page_html)
    panel_ids = {panel for panel, _ in panels}
    if panel_ids != expected:
        raise SystemExit(
            "encounter panels do not match the reviewed state set: "
            f"missing {sorted(expected - panel_ids)}, unexpected {sorted(panel_ids - expected)}"
        )
    allowed_menubar = {"idle", "detected", "armed", "recording", "degraded",
                       "transcribing", "error"}
    unknown = {state for _, state in panels} - allowed_menubar
    if unknown:
        raise SystemExit(f"encounter declares unknown menubar state(s): {sorted(unknown)}")
    targets = re.findall(r'<button[^>]*data-panel="([^\"]+)"', page_html)
    missing = sorted(set(targets) - panel_ids)
    if missing:
        raise SystemExit(f"encounter button(s) target no panel: {missing}")
    transition_panels = {
        "spec-first-sitting-saved", "spec-resume-after-gap",
        "spec-second-sitting-review", "spec-negative-sample",
        "spec-operating-point", "spec-ready-to-build", "spec-building-profile",
        "spec-enrolled", "spec-returning-profile",
    }
    special_panels = set(re.findall(r'data-discard-origin="([^\"]+)"', page_html))
    special_panels.add("spec-discard-enrollment")
    if not expected <= set(targets) | transition_panels | special_panels | {"spec-library"}:
        raise SystemExit("some reviewed encounter states have no incoming control")
    enrollment_events = set(re.findall(r'data-enrollment-event="([^\"]+)"', page_html))
    expected_events = {
        "save-first", "resume-after-gap", "review-second", "review-negative",
        "measurements-ready", "select-policy", "build-profile",
        "persist-profile-success", "load-returning-profile", "discard",
    }
    if enrollment_events != expected_events:
        raise SystemExit(
            "enrollment controls do not match the executable state machine: "
            f"missing {sorted(expected_events - enrollment_events)}, "
            f"unexpected {sorted(enrollment_events - expected_events)}"
        )
    if len(re.findall(r'<input[^>]+name="retention-period"', page_html)) != 4:
        raise SystemExit("first-run retention choice no longer exposes four test options")
    retention = re.search(
        r'<fieldset class="retention-choice">(.*?)</fieldset>', page_html, re.DOTALL
    )
    if not retention or "checked" in retention.group(1):
        raise SystemExit("first-run retention choice must have no default")
    if (
        'data-panel="spec-enrollment-blocked" data-requires-retention disabled'
        not in re.sub(r"\s+", " ", page_html)
    ):
        raise SystemExit("retention must lead to enrollment, not an apparently ready library")
    if len(re.findall(r'<button[^>]+data-permission="(?:microphone|system)"', page_html)) != 2:
        raise SystemExit("first-run no longer exposes both required permission states")
    if "At least two sittings" not in page_html or "at least one hour apart" not in page_html:
        raise SystemExit("voice enrollment no longer states its multi-sitting requirement")
    manual_start = re.search(r'<button[^>]+id="manual-capture"[^>]*>', page_html)
    if not manual_start or "disabled" not in manual_start.group(0):
        raise SystemExit("supported capture is no longer initially blocked on enrollment")
    if "start capture — setup required" not in page_html:
        raise SystemExit("the capture blocker no longer names incomplete setup")
    negative = re.search(
        r'<fieldset class="negative-choice">(.*?)</fieldset>', page_html, re.DOTALL
    )
    if (
        not negative
        or len(re.findall(r'name="negative-source"', negative.group(1))) != 2
        or "checked" in negative.group(1)
    ):
        raise SystemExit("negative material must offer two allowed, unselected sources")
    for required in (
        "Public-domain or licensed speech playback",
        "A consenting person recording for calibration",
        "Source meetings are never copied or deleted",
        "Failure, cancellation, or abandonment deletes partial raw",
        "at least 60 seconds of scorable speech across at least 20 segments",
    ):
        if required not in flat_page:
            raise SystemExit(f"enrollment lifecycle no longer states: {required}")
    policy = re.search(
        r'<fieldset class="voice-policy-choice"[^>]*>(.*?)</fieldset>',
        page_html,
        re.DOTALL,
    )
    inputs = re.findall(
        r'<input type="radio" name="voice-policy"\s+'
        r'data-target="([^"]+)"\s+data-operator-rate="([^"]+)"\s+'
        r'data-negative-rate="([^"]+)" disabled>',
        policy.group(1) if policy else "",
    )
    if not policy or len(inputs) not in (2, 3) or "checked" in policy.group(1):
        raise SystemExit("voice policy must expose two or three options with no default")
    expected_points = [
        (
            f"{point['target_frr']:.8f}",
            f"{point['measured_frr']:.8f}",
            f"{point['false_admit_rate']:.8f}",
        )
        for point in operating_point_fixture()
    ]
    if inputs != expected_points:
        raise SystemExit("prototype policies drifted from speaker_gate's measured choices")
    if any("disabled" not in tag for tag in re.findall(
        r'<input[^>]+name="voice-policy"[^>]*>', policy.group(1)
    )):
        raise SystemExit("voice-policy radios must stay disabled without measurements")
    if "%" in policy.group(1):
        raise SystemExit("voice-policy specimen must not invent personal rates")
    if "this macOS account only" not in page_html or "not included in exports" not in page_html:
        raise SystemExit("the voice profile is no longer clearly owner-only and app-private")
    if "future: detection" not in page_html or "excluded from supported beta" not in page_html:
        raise SystemExit("microphone-use detection is no longer bounded outside beta")
    consent = re.search(
        r'<section class="encounter-panel" id="spec-consent".*?</section>',
        page_html,
        re.DOTALL,
    )
    if not consent or 'id="participant-attested"' not in consent.group(0):
        raise SystemExit("consent no longer requires an operator attestation")
    if 'data-menubar="idle"' not in consent.group(0):
        raise SystemExit("manual-start consent must use the neutral menubar state")
    if "checked" in consent.group(0) or "never for this app" in consent.group(0).lower():
        raise SystemExit("consent is preselected or offers an unimplemented persistent block")
    required_ids = {
        "menubar-glyph", "menubar-word", "permission-microphone", "permission-system",
        "permissions-result", "capture-eligibility", "manual-capture",
        "enrollment-status", "load-valid-profile-fixture",
        "load-returning-prerequisites", "participant-attested",
        "attestation-result", "consent-retention", "consent-continue",
        "cancel-capture-attempt", "cancel-armed", "future-consent",
        "negative-material-result", "load-operating-fixture",
        "voice-policy-choices", "voice-policy-result", "continue-selected-policy",
        "ready-policy-result",
        "discard-result", "discard-enrollment-now", "discard-enrollment-confirm",
        "confirm-discard-enrollment", "cancel-discard-enrollment",
        "profile-result", "reset-profile-now", "reset-profile-confirm",
        "confirm-reset-profile", "cancel-reset-profile",
        "retention-result", "withheld-turn", "correction-result", "restore-turn",
        "regenerate-note", "displayed-note-state", "audio-result", "delete-audio-now",
        "delete-audio-confirm", "confirm-delete-audio", "cancel-delete-audio",
        "meeting-result", "delete-meeting-now", "delete-meeting-confirm",
        "confirm-delete-meeting", "cancel-delete-meeting", "specimen-new-note",
        "real-data-detail", "notice-result",
    }
    present_ids = set(re.findall(r' id="([^\"]+)"', page_html))
    if missing := sorted(required_ids - present_ids):
        raise SystemExit(f"encounter JavaScript hook(s) missing from markup: {missing}")
    actions = set(re.findall(r'data-action="([^\"]+)"', page_html))
    expected_actions = {
        "manual-start", "manual-stop", "finish-processing", "open-real-data-detail"
    }
    if expected_actions - actions:
        raise SystemExit("encounter no longer exposes the reviewed transition actions")
    if len(re.findall(
        r'<button[^>]+data-action="open-real-data-detail"', page_html
    )) != 2:
        raise SystemExit("ready state and specimen row must both reach real-data detail")
    if "The note, transcript, claim evidence, and voice profile remain." not in flat_page:
        raise SystemExit("delete-audio confirmation no longer states what survives")
    if (
        "The note, transcript, claim evidence, both meeting WAV files, and this"
        not in flat_page
        or "The separately stored voice profile and other meetings" not in flat_page
    ):
        raise SystemExit("delete-meeting confirmation no longer states its full consequence")
    reset = re.search(
        r'<div class="confirm-box" id="reset-profile-confirm".*?</div>',
        page_html,
        re.DOTALL,
    )
    flat_reset = re.sub(r"\s+", " ", reset.group(0)) if reset else ""
    if (
        not reset
        or "Existing notes, transcripts, meeting audio, and meeting retention choices remain"
        not in flat_reset
        or "The application blocks capture until enrollment completes again"
        not in flat_reset
        or "only the research CLI may run ungated outside the beta" not in flat_reset
    ):
        raise SystemExit("profile reset no longer states its exact independent consequence")
    reset_panel = re.search(
        r'<section class="encounter-panel" id="spec-profile-reset".*?</section>',
        page_html,
        re.DOTALL,
    )
    if reset_panel and 'data-panel="spec-enrollment-blocked"' in reset_panel.group(0):
        raise SystemExit("profile reset exposes blocked state before deletion succeeds")
    discard = re.search(
        r'<div class="confirm-box" id="discard-enrollment-confirm".*?</div>',
        page_html,
        re.DOTALL,
    )
    flat_discard = re.sub(r"\s+", " ", discard.group(0)) if discard else ""
    if (
        not discard
        or "All dedicated enrollment material and partial derived work go"
        not in flat_discard
        or "Source meetings are never copied or deleted" not in flat_discard
        or "No profile is built" not in flat_discard
    ):
        raise SystemExit("discard enrollment no longer states its exact consequence")
    if "__OPERATING_" in page_html or "__RETURNING_" in page_html:
        raise SystemExit("an enrollment fixture placeholder reached the rendered page")
    return len(targets)


def main() -> int:
    # A directory argument, so the renderer can be exercised against a fixture without
    # writing into the directory holding real meeting artifacts.
    out_dir = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else OUT_DIR
    page_path = out_dir / "prototype.html"
    notes = sorted(out_dir.glob("*.note.json"))
    if not notes:
        raise SystemExit(
            f"no note artifacts in {out_dir}.\n"
            "Generate at least one first, for example:\n"
            "  python notes/summarize.py notes/corpus/ES2004c.json --strip "
            "--out notes/out/ES2004c.md"
        )

    tok = tokens()
    sections, library, totals = [], [], dict.fromkeys(STATES, 0)
    for path in notes:
        doc = json.loads(path.read_text())
        if doc.get("schema") not in NOTE_SCHEMAS:
            raise SystemExit(
                f"{path}: expected one of {sorted(NOTE_SCHEMAS)}, "
                f"got {doc.get('schema')!r}")
        try:
            validate_artifact_pair(doc, path)
        except ValueError as e:
            raise SystemExit(f"{path}: note pair refused: {e}") from e
        section, c = meeting_section(doc, path)
        sections.append(section)
        library.append(library_row(doc))
        for k, v in c.items():
            totals[k] += v

    rendered = page("".join(sections), "".join(library), totals, tok, len(notes))
    buttons = check_wiring(rendered)
    encounter_controls = check_encounter_wiring(rendered)
    enrollment_assertions = check_enrollment_js(rendered)
    capture_dom_assertions = check_capture_dom_js(rendered)
    page_path.write_text(rendered)
    size = page_path.stat().st_size / 1024
    noun = "meeting" if len(notes) == 1 else "meetings"
    print(f"wrote {page_path}  ({size:.0f} KB, {len(notes)} {noun}, "
          f"{sum(totals.values())} claims, {buttons} locators all resolving, "
          f"{encounter_controls} encounter controls wired, "
          f"{enrollment_assertions} enrollment transitions checked, "
          f"{capture_dom_assertions} capture DOM assertions checked)")
    for state, n in totals.items():
        print(f"  {n:>4}  {state}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

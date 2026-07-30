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
`note/1` artifact that a real model run produced. Nothing here composes a meeting.

**What it therefore cannot show, it labels.** film-room's Decision 0047 records the
operator opening a shell with placeholder interiors and reasonably mistaking one for
a broken folder chooser. The conclusion drawn there is that a fixture cannot serve as
an operator encounter. So each region on this page states whether it is real data, a
component specimen with a stated contract, or an open question — and the regions the
corpus cannot populate say so in place rather than being quietly dropped.

Run:  python docs/prototype/build.py            # reads notes/out/*.note.json
"""

from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "notes"))

from summarize import _seq  # noqa: E402
from transcript import load  # noqa: E402  (needs the path above)

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


def turns_for(doc: dict, note_path: Path) -> list:
    """The transcript in the shape the claim indices count.

    `transform` is applied here rather than assumed. A claim's `turn` is a position in
    the transcript as the model saw it, and the transforms do not all preserve
    positions — reading the raw file for a `simulate-bleed` run would resolve every
    citation to the wrong words while appearing to work.
    """
    t = load((note_path.parent / doc["transcript"]).resolve())
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
    return t.turns


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


def claim_row(claim: dict, i: int, meeting: str) -> str:
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
    if quote:
        # The locator is derived by finding the quote, never taken from the model. It
        # shows a timestamp when there is one and the turn position when there is not:
        # corpus transcripts carry no times, and a button reading "--:--" claims a
        # precision the material does not have while hiding that it still works. A
        # real capture always records times, so this is a limit of the corpus.
        where = (stamp(claim["start"]) if claim.get("start") is not None
                 else f"turn {turn}")
        at = (f'<button class="at" data-meeting="{esc(meeting)}" data-turn="{turn}">'
              f'{esc(where)}</button>') if turn is not None else ""
        # The block carries the verdict's colour on its edge. Presenting a composed
        # quote in the same frame as a located one lets it read as evidence, which is
        # the failure this whole surface exists to prevent — and the state word sits
        # directly above, so the colour is never carrying the state alone.
        body.append(f'<blockquote class="quote" style="--state:{color}">{at}'
                    f'<span class="qtext">{esc(quote)}</span></blockquote>')
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


def check_locators(doc: dict, turns: list, note_path: Path) -> None:
    """Every located claim's locator must land on the words it quotes.

    The one promise this page makes that a reader cannot check by looking. A button
    that scrolls to the wrong turn is indistinguishable from one that works — the page
    still moves, a turn still highlights, and the operator reads speech that did not
    produce the claim. That is worse than no button, because it manufactures
    confidence. So it is asserted at build time rather than spot-checked visually.

    `_seq` is imported from the summarizer rather than reimplemented. Splitting words a
    second way here would make this file a second authority on what a quote matches,
    and the two would disagree on exactly the inputs that matter — the punctuation and
    casing that ASR invents.
    """
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
    turns = turns_for(doc, note_path)
    check_locators(doc, turns, note_path)
    c = counts(doc)
    cited = {cl["turn"] for cl in doc["claims"] if cl.get("turn") is not None}
    prov = doc["provenance"]

    claims = "".join(claim_row(cl, i, m["id"]) for i, cl in enumerate(doc["claims"]))
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
                       "The retained artifact. A located claim's timestamp is a "
                       "button: it moves to the turn the quote was located in. That "
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


def page(sections: str, library: str, totals: dict[str, int], tok: dict[str, str],
         meetings: int) -> str:
    css_vars = "\n      ".join(f"--{k}: {v};" for k, v in tok.items())
    legend = "".join(
        f'<li style="--state:{color}"><span class="mark">{MARKS[mark]}</span>'
        f'<span class="word">{esc(word)}</span>'
        f'<span class="why">{esc(why)}</span></li>'
        for mark, word, color, why in STATES.values())
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
  .quote {{ margin: 9px 0 0; padding: 8px 10px; background: var(--surface-base);
            border-left: 2px solid var(--state); border-radius: 0 4px 4px 0;
            font-family: var(--mono); font-size: 12px; color: var(--neutral-200); }}
  .at {{ font: inherit; color: var(--neutral-50); background: var(--surface-overlay);
         border: 0; border-radius: 2px; padding: 1px 6px; margin-right: 8px;
         cursor: pointer; }}
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

  .open ul {{ max-width: 80ch; color: var(--neutral-300); }}
  .open li {{ margin-bottom: 9px; }}
  .open strong {{ color: var(--neutral-100); }}
  @media (max-width: 980px) {{
    .split {{ grid-template-columns: 1fr; }}
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

<ul class="legend">{legend}</ul>

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
<ul class="lib">{library}</ul>

<h2>The note, and the words behind it</h2>
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
    <li><strong>Not settled: what to do about a bad claim.</strong> J4. The operator
      can see that a quote was composed and can read the transcript; they cannot
      correct, dismiss, or re-run anything.</li>
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
        if doc.get("schema") != "note/1":
            raise SystemExit(f"{path}: expected schema note/1, got {doc.get('schema')!r}")
        section, c = meeting_section(doc, path)
        sections.append(section)
        library.append(library_row(doc))
        for k, v in c.items():
            totals[k] += v

    rendered = page("".join(sections), "".join(library), totals, tok, len(notes))
    buttons = check_wiring(rendered)
    page_path.write_text(rendered)
    size = page_path.stat().st_size / 1024
    noun = "meeting" if len(notes) == 1 else "meetings"
    print(f"wrote {page_path}  ({size:.0f} KB, {len(notes)} {noun}, "
          f"{sum(totals.values())} claims, {buttons} locators all resolving)")
    for state, n in totals.items():
        print(f"  {n:>4}  {state}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

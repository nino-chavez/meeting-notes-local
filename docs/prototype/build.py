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

Run:

    python3 docs/prototype/build.py \
      --notes-dir notes/out \
      --out ~/private-meeting-review/prototype.html \
      --node /absolute/path/to/node

For the operator-confirmed real-content encounter, keep the immutable six-file
capture directory separate from its approved review packet:

    python3 docs/prototype/build.py \
      --capture-dir /private/capture \
      --encounter-content /private/review/review-content.json \
      --content-approval /private/review/content-approval.json \
      --out /private/review/prototype.html \
      --node /absolute/path/to/node

The output directory must already exist, be owner-only (0700), and sit outside
every Git repository. The renderer refuses an existing output rather than
replacing it.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import wave
from collections.abc import Callable
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "notes"))
sys.path.insert(0, str(REPO / "spike"))

from capture_health import UNKNOWN_WARNING as CAPTURE_INTEGRITY_UNKNOWN_WARNING  # noqa: E402
from capture_health import build as build_capture_health  # noqa: E402
from capture_health import validate as validate_capture_health  # noqa: E402
from capture_health import warning as capture_health_warning  # noqa: E402
from summarize import (  # noqa: E402
    NOTE_SCHEMAS,
    _seq,
    _support_key,
    artifact_uses_source_evidence,
    reconcile_capture_provenance,
    structured_artifact_citations,
    transcript_view_sha256,
    validate_artifact_pair,
    validate_evidence_contract,
    validate_stored_verdict,
    validate_support_measurement,
)
from transcript import Transcript, load  # noqa: E402  (needs the path above)

sys.path.insert(0, str(REPO / "spike"))

from dual_capture import (  # noqa: E402
    finalize_session,
    open_private_binary,
    sha256,
    write_private_text,
)
from speaker_gate import operating_point_choices  # noqa: E402
from verify_capture import VerificationError, verify_capture  # noqa: E402

GIT = Path("/usr/bin/git")
FIXTURE_PACK = REPO / "docs" / "prototype" / "fixtures" / "accepted-note2.fixture"
FIXTURE_MARKER = {
    "schema": "prototype-mechanical-fixture/1",
    "product_evidence": False,
}
FIXTURE_TRANSCRIPT_VIEW_SHA256 = (
    "a33dcffb8640f196be5709bfdbb830a51662e05ea52f93a2d12cb3c3cc3c442b"
)


def _git_environment() -> dict[str, str]:
    """A fixed environment for proving a destination is outside Git."""
    return {
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "HOME": "/var/empty",
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": "/usr/bin:/bin",
    }


def _require_outside_git(directory: Path) -> None:
    """Fail closed unless Git itself says no repository owns this directory."""
    if not GIT.is_file() or not os.access(GIT, os.X_OK):
        raise SystemExit(
            f"cannot prove the private output is outside Git: {GIT} is unavailable"
        )
    result = subprocess.run(
        [str(GIT), "-C", str(directory), "rev-parse", "--absolute-git-dir"],
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
        env=_git_environment(),
    )
    if result.returncode == 0:
        git_dir = result.stdout.strip() or "an enclosing Git repository"
        raise SystemExit(
            f"private prototype output must be outside every Git repository; "
            f"{directory} is owned by {git_dir}"
        )
    detail = (result.stderr or result.stdout).strip().lower()
    if result.returncode != 128 or "not a git repository" not in detail:
        raise SystemExit(
            "cannot prove the private output is outside Git: "
            f"git returned {result.returncode}: {detail or 'no diagnostic'}"
        )


def private_output_target(path: Path) -> Path:
    """Resolve and validate a fresh owner-private HTML destination."""
    expanded = path.expanduser()
    if not expanded.is_absolute():
        raise SystemExit("--out must be an absolute path (a leading ~ is accepted)")
    if expanded.suffix.lower() != ".html":
        raise SystemExit("--out must name one .html file")
    if expanded.name in {"", ".", ".."}:
        raise SystemExit("--out must name one file")

    raw_parent = expanded.parent
    try:
        raw_parent_stat = os.lstat(raw_parent)
    except FileNotFoundError as exc:
        raise SystemExit(f"--out parent does not exist: {raw_parent}") from exc
    if stat.S_ISLNK(raw_parent_stat.st_mode):
        raise SystemExit(f"--out parent may not be a symlink: {raw_parent}")

    try:
        parent = raw_parent.resolve(strict=True)
    except OSError as exc:
        raise SystemExit(f"cannot resolve --out parent {raw_parent}: {exc}") from exc
    parent_stat = parent.stat()
    if not stat.S_ISDIR(parent_stat.st_mode):
        raise SystemExit(f"--out parent is not a directory: {parent}")
    if parent_stat.st_uid != os.geteuid():
        raise SystemExit(f"--out parent is not owned by the current user: {parent}")
    if stat.S_IMODE(parent_stat.st_mode) != 0o700:
        raise SystemExit(f"--out parent must be mode 0700: {parent}")
    _require_outside_git(parent)

    target = parent / expanded.name
    if os.path.lexists(target):
        raise SystemExit(
            f"--out already exists or is a symlink: {target}; use a fresh filename"
        )
    return target


def _sha256_file(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            value.update(chunk)
    return value.hexdigest()


def _private_json_input(path: Path, label: str) -> tuple[Path, dict]:
    """Load one owner-only external JSON input without following a symlink."""
    expanded = path.expanduser()
    if expanded.parent.is_symlink():
        raise SystemExit(f"{label} parent may not be a symlink")
    if expanded.is_symlink() or not expanded.is_file():
        raise SystemExit(f"{label} must be one regular file, not a symlink")
    try:
        resolved = expanded.resolve(strict=True)
    except OSError as exc:
        raise SystemExit(f"cannot resolve {label} {expanded}: {exc}") from exc
    info = resolved.stat()
    if info.st_uid != os.geteuid():
        raise SystemExit(f"{label} must be owned by the current user")
    if stat.S_IMODE(info.st_mode) != 0o600:
        raise SystemExit(f"{label} must be mode 0600")
    parent_info = resolved.parent.stat()
    if parent_info.st_uid != os.geteuid():
        raise SystemExit(f"{label} parent must be owned by the current user")
    if stat.S_IMODE(parent_info.st_mode) != 0o700:
        raise SystemExit(f"{label} parent must be mode 0700")
    _require_outside_git(resolved.parent)
    try:
        value = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"{label} is not readable JSON: {exc}") from None
    if not isinstance(value, dict):
        raise SystemExit(f"{label} must contain one JSON object")
    return resolved, value


def load_encounter_review(
    capture_dir: Path,
    content_path: Path,
    approval_path: Path,
) -> tuple[dict, dict, Transcript]:
    """Reconcile human-curated encounter content without promoting it to a note."""
    supplied_capture = capture_dir.expanduser()
    if supplied_capture.is_symlink():
        raise SystemExit("--capture-dir may not be a symlink")
    try:
        capture = supplied_capture.resolve(strict=True)
    except OSError as exc:
        raise SystemExit(f"cannot resolve --capture-dir {capture_dir}: {exc}") from exc
    _require_outside_git(capture)
    try:
        verify_capture(capture, interaction_canary=True)
    except VerificationError as exc:
        raise SystemExit(f"encounter capture refused: {exc}") from None

    content_file, content = _private_json_input(
        content_path, "--encounter-content"
    )
    approval_file, approval = _private_json_input(
        approval_path, "--content-approval"
    )
    if content_file.parent != approval_file.parent:
        raise SystemExit("encounter content and approval must share one private directory")
    if content_file.parent == capture:
        raise SystemExit("review inputs may not alter the immutable capture directory")

    if set(content) != {
        "schema",
        "origin",
        "product_evidence",
        "runtime_validation",
        "source",
        "meeting",
        "items",
    }:
        raise SystemExit("encounter review content has the wrong top-level shape")
    if (
        content.get("schema") != "encounter-review-content/1"
        or content.get("origin") != "review-draft"
        or content.get("product_evidence") is not False
        or content.get("runtime_validation") != "not_run"
    ):
        raise SystemExit(
            "encounter content must remain a non-product review draft with runtime not run"
        )

    if set(approval) != {
        "schema",
        "review_content_sha256",
        "participant_consent_before_capture",
        "curation",
        "reviewer",
        "decided_at",
    }:
        raise SystemExit("encounter content approval has the wrong shape")
    if approval.get("schema") != "encounter-content-approval/1":
        raise SystemExit("encounter content approval has an unknown schema")
    if approval.get("review_content_sha256") != _sha256_file(content_file):
        raise SystemExit("encounter approval does not bind the exact review content")
    if approval.get("participant_consent_before_capture") != "confirmed":
        raise SystemExit("encounter approval does not confirm participant consent")
    if approval.get("curation") != "accept":
        raise SystemExit("encounter content was not accepted by the operator")
    if not isinstance(approval.get("reviewer"), str) or not approval["reviewer"].strip():
        raise SystemExit("encounter approval has no reviewer identifier")
    if not isinstance(approval.get("decided_at"), str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{4}",
        approval["decided_at"],
    ):
        raise SystemExit("encounter approval has no recognized decision timestamp")

    source = content.get("source")
    meeting = content.get("meeting")
    items = content.get("items")
    if not isinstance(source, dict) or set(source) != {
        "capture_id",
        "capture_mode",
        "transcript_file",
        "transcript_sha256",
        "session_file",
        "session_sha256",
    }:
        raise SystemExit("encounter content source has the wrong shape")
    if not isinstance(meeting, dict) or set(meeting) != {
        "id",
        "title",
        "captured_at",
    }:
        raise SystemExit("encounter meeting metadata has the wrong shape")
    capture_id = source.get("capture_id")
    if not isinstance(capture_id, str) or not re.fullmatch(
        r"[A-Za-z0-9._-]{1,80}", capture_id
    ):
        raise SystemExit("encounter capture id is not a safe stable identifier")
    if meeting.get("id") != capture_id:
        raise SystemExit("encounter meeting id does not match its capture id")
    if not isinstance(meeting.get("title"), str) or not meeting["title"].strip():
        raise SystemExit("encounter meeting has no review title")
    if source.get("capture_mode") != "headphones":
        raise SystemExit("encounter content is not declared as a headphone capture")
    if source.get("transcript_file") != "transcript.json":
        raise SystemExit("encounter content names the wrong transcript artifact")
    if source.get("session_file") != "session.json":
        raise SystemExit("encounter content names the wrong session artifact")

    transcript_path = capture / "transcript.json"
    session_path = capture / "session.json"
    if source.get("transcript_sha256") != _sha256_file(transcript_path):
        raise SystemExit("encounter content does not bind the retained transcript")
    if source.get("session_sha256") != _sha256_file(session_path):
        raise SystemExit("encounter content does not bind the capture session")
    session = json.loads(session_path.read_text(encoding="utf-8"))
    if meeting.get("captured_at") != session.get("started_at"):
        raise SystemExit("encounter captured_at does not match the capture session")

    transcript_doc = json.loads(transcript_path.read_text(encoding="utf-8"))
    turns = transcript_doc.get("turns")
    if not isinstance(items, list) or not 3 <= len(items) <= 12:
        raise SystemExit("encounter review must contain 3 to 12 items")
    if not isinstance(turns, list):
        raise SystemExit("encounter transcript has no turn list")
    allowed_types = {"decision", "action", "proposal", "open_question"}
    seen = set()
    for number, item in enumerate(items, start=1):
        if not isinstance(item, dict) or set(item) != {"type", "claim", "evidence"}:
            raise SystemExit(f"encounter item {number} has the wrong shape")
        if item.get("type") not in allowed_types:
            raise SystemExit(f"encounter item {number} has an unknown type")
        claim = item.get("claim")
        evidence = item.get("evidence")
        if not isinstance(claim, str) or not claim.strip() or claim != claim.strip():
            raise SystemExit(f"encounter item {number} has an invalid claim")
        if not isinstance(evidence, list) or not 1 <= len(evidence) <= 3:
            raise SystemExit(f"encounter item {number} must carry 1 to 3 evidence spans")
        item_key = [item["type"], claim]
        for span_number, span in enumerate(evidence, start=1):
            if not isinstance(span, dict) or set(span) != {"turn", "quote"}:
                raise SystemExit(
                    f"encounter item {number} evidence {span_number} has the wrong shape"
                )
            turn = span.get("turn")
            quote = span.get("quote")
            if type(turn) is not int or not 0 <= turn < len(turns):
                raise SystemExit(
                    f"encounter item {number} evidence {span_number} points outside the transcript"
                )
            if (
                not isinstance(quote, str)
                or quote != quote.strip()
                or len(quote.split()) < 4
                or quote not in turns[turn].get("text", "")
            ):
                raise SystemExit(
                    f"encounter item {number} evidence {span_number} does not resolve exactly"
                )
            item_key.extend((turn, quote))
        frozen_key = tuple(item_key)
        if frozen_key in seen:
            raise SystemExit("encounter review contains a duplicate item")
        seen.add(frozen_key)

    transcript = load(transcript_path)
    return content, approval, transcript


def _fsync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def publish_private_html(
    path: Path,
    rendered: str,
    *,
    before_publish: Callable[[], None] | None = None,
    sync_directory: Callable[[Path], None] = _fsync_directory,
) -> tuple[Path, str]:
    """Publish UTF-8 HTML owner-only, atomically, and without replacement."""
    target = private_output_target(path)
    payload = rendered.encode("utf-8")
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".partial",
        dir=target.parent,
    )
    temporary = Path(temporary_name)
    published = False
    temporary_identity: os.stat_result | None = None
    try:
        os.fchmod(fd, 0o600)
        handle = os.fdopen(fd, "wb")
        fd = -1
        with handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        temporary_identity = temporary.stat()

        # Close the ordinary validation-to-publication race. The hard link below is
        # still the no-overwrite authority if a target appears after this check.
        if private_output_target(path) != target:
            raise SystemExit("--out resolved to a different target during the build")
        if before_publish is not None:
            before_publish()
        try:
            os.link(temporary, target, follow_symlinks=False)
        except FileExistsError as exc:
            raise SystemExit(
                f"--out appeared during the build: {target}; nothing was replaced"
            ) from exc
        published = True
        sync_directory(target.parent)
        temporary.unlink()
        sync_directory(target.parent)
        final = target.lstat()
        if not stat.S_ISREG(final.st_mode) or stat.S_IMODE(final.st_mode) != 0o600:
            raise SystemExit(f"private prototype did not publish as mode 0600: {target}")
        installed_digest = hashlib.sha256(target.read_bytes()).hexdigest()
        if installed_digest != hashlib.sha256(payload).hexdigest():
            raise SystemExit(
                f"private prototype bytes changed during publication: {target}"
            )
        return target, installed_digest
    # Roll back this invocation's inode for every post-link exit, including the
    # SystemExit guards below and an operator interrupt during final validation.
    except BaseException:
        if (
            published
            and temporary_identity is not None
            and os.path.lexists(target)
        ):
            try:
                target_identity = target.lstat()
                if (
                    target_identity.st_dev == temporary_identity.st_dev
                    and target_identity.st_ino == temporary_identity.st_ino
                ):
                    target.unlink()
                    sync_directory(target.parent)
            except OSError:
                pass
        raise
    finally:
        if fd >= 0:
            os.close(fd)
        if temporary.exists():
            temporary.unlink()


def resolve_node(value: Path | None) -> tuple[Path, str]:
    """Resolve one exact Node binary and record the version used for checks."""
    if value is None:
        raise SystemExit("Node is required; pass one absolute executable with --node")
    candidate = value.expanduser()
    if not candidate.is_absolute():
        raise SystemExit("--node must be an absolute executable path")
    try:
        executable = candidate.resolve(strict=True)
    except OSError as exc:
        raise SystemExit(f"cannot resolve Node executable {candidate}: {exc}") from exc
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise SystemExit(f"Node executable is not an executable file: {executable}")
    try:
        result = subprocess.run(
            [str(executable), "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
            env={
                "LANG": "C",
                "LC_ALL": "C",
                "PATH": f"{executable.parent}:/usr/bin:/bin",
            },
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SystemExit(f"cannot execute Node version check: {exc}") from exc
    version = result.stdout.strip()
    if result.returncode or not re.fullmatch(r"v\d+\.\d+\.\d+", version):
        detail = (result.stderr or result.stdout).strip()
        raise SystemExit(f"Node version check failed: {detail or result.returncode}")
    return executable, version


def run_node(executable: Path, script: str, label: str) -> str:
    """Run one bounded builtin-only JavaScript control under the pinned binary."""
    try:
        result = subprocess.run(
            [str(executable), "-e", script],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
            env={
                "LANG": "C",
                "LC_ALL": "C",
                "PATH": f"{executable.parent}:/usr/bin:/bin",
            },
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SystemExit(f"cannot execute {label}: {exc}") from exc
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise SystemExit(f"{label} failed:\n{detail}")
    return result.stdout

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


def transcript_for(doc: dict, note_path: Path) -> Transcript:
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


def capture_warning_markup(doc: dict, *, compact: bool = False) -> str:
    """Render persisted capture warnings, refusing an artifact that hides failure."""
    warnings = doc.get("capture_warnings") or []
    if not isinstance(warnings, list) or not all(
        isinstance(warning, str) and warning.strip() for warning in warnings
    ):
        raise SystemExit("note artifact capture_warnings must be a list of text")
    integrity_unknown = doc.get("capture_integrity_unknown", False)
    if not isinstance(integrity_unknown, bool):
        raise SystemExit("note artifact capture_integrity_unknown must be boolean")
    if (
        integrity_unknown
        and CAPTURE_INTEGRITY_UNKNOWN_WARNING not in warnings
    ):
        raise SystemExit(
            "note artifact records unknown capture integrity but does not carry its "
            "canonical warning"
        )
    health = doc.get("capture_health")
    if health is not None:
        try:
            usable = validate_capture_health(health, transcript_context=True)
            expected_health_warning = capture_health_warning(
                health, transcript_context=True
            )
        except ValueError as exc:
            raise SystemExit(f"note artifact has invalid capture_health: {exc}") from None
        if not usable and expected_health_warning not in warnings:
            raise SystemExit(
                "note artifact records failed capture health but does not carry its "
                "canonical warning"
            )
    if not warnings:
        return ""
    if compact:
        return (
            f'<span class="lib-capture" title="{esc(" | ".join(warnings))}">'
            f'capture warning &middot; {len(warnings)} issue'
            f'{"s" if len(warnings) != 1 else ""}</span>'
        )
    items = "".join(f"<li>{esc(warning)}</li>" for warning in warnings)
    return (
        '<aside class="capture-warning" role="alert">'
        "<strong>Capture warning</strong>"
        f"<ul>{items}</ul>"
        "</aside>"
    )


def check_capture_warning_renderer() -> None:
    """Synthetic control for the artifact-to-banner seam real corpus data lacks."""
    health = build_capture_health(
        mic_samples=16_000,
        system_samples=16_000,
        capture_elapsed_samples=16_000,
        dropouts={
            "mic": [{"at_s": 0.2, "detail": "input overflow"}],
            "system": [],
        },
        tap_errors=[],
        transcription_requested=True,
        transcript_written=True,
    )
    warning = capture_health_warning(health, transcript_context=True)
    fixture = {"capture_health": health, "capture_warnings": [warning]}
    rendered = capture_warning_markup(fixture)
    if 'role="alert"' not in rendered or esc(warning) not in rendered:
        raise SystemExit(
            "capture warning fixture did not survive the note-artifact banner renderer"
        )
    hidden = {"capture_health": health, "capture_warnings": []}
    try:
        capture_warning_markup(hidden)
    except SystemExit:
        pass
    else:
        raise SystemExit("failed capture health rendered without a warning")

    legacy = {
        "capture_health": None,
        "capture_integrity_unknown": True,
        "capture_warnings": [CAPTURE_INTEGRITY_UNKNOWN_WARNING],
    }
    legacy_rendered = capture_warning_markup(legacy)
    if (
        'role="alert"' not in legacy_rendered
        or esc(CAPTURE_INTEGRITY_UNKNOWN_WARNING) not in legacy_rendered
    ):
        raise SystemExit(
            "legacy unknown-integrity warning did not survive the banner renderer"
        )
    legacy["capture_warnings"] = []
    try:
        capture_warning_markup(legacy)
    except SystemExit:
        pass
    else:
        raise SystemExit("unknown capture integrity rendered without a warning")

    with tempfile.TemporaryDirectory(prefix="capture-warning-builder-") as tmp:
        fixture_dir = Path(tmp)
        transcript_path = fixture_dir / "transcript.json"
        transcript_path.write_text(json.dumps({
            "source": "capture legacy fixture",
            "attribution": "channel",
            "turns": [],
        }))
        note_path = fixture_dir / "legacy.note.json"
        note_doc = {
            "schema": "note/1",
            "transcript": "transcript.json",
            "transform": None,
        }
        retained = transcript_for(note_doc, note_path)
        reconciled = reconcile_capture_provenance(
            note_doc,
            retained,
            where=note_path.name,
            allow_absent_legacy=True,
        )
        retained_banner = capture_warning_markup(reconciled)
        if (
            'role="alert"' not in retained_banner
            or esc(CAPTURE_INTEGRITY_UNKNOWN_WARNING) not in retained_banner
        ):
            raise SystemExit(
                "a legacy note did not recover capture provenance from its transcript"
            )
        stripped = dict(
            note_doc,
            capture_health=None,
            capture_integrity_unknown=False,
            capture_warnings=[],
        )
        try:
            reconcile_capture_provenance(
                stripped,
                retained,
                where=note_path.name,
                allow_absent_legacy=True,
            )
        except ValueError:
            return
    raise SystemExit("a note was allowed to contradict its retained transcript")


def require_ready_note(doc: dict, path: Path) -> None:
    """Refuse a diagnostic artifact where the product expects a usable note."""
    try:
        passed = validate_stored_verdict(
            doc.get("checks"), doc.get("passed"), str(path)
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise SystemExit(f"{path}: stored note verdict refused: {exc}") from exc
    if not passed:
        raise SystemExit(
            f"{path}: this run failed its own acceptance checks. It is a research "
            "diagnostic, not a ready note; show the retained transcript in the "
            "summary-failed state instead."
        )


def check_note_admission_renderers() -> None:
    passing_checks = {
        "context": {"ok": True},
        "attribution": {"applies": True, "ok": True},
        "numbers": {"ok": True},
        "prompt_echo": {"ok": True},
        "citations": {
            "applies": True,
            "ok": True,
            "cited": [],
            "fabricated": [],
            "unverifiable": [],
            "uncited": [],
            "items": 0,
        },
        "extraction": {"applies": False, "ok": None},
    }
    fixture = {
        "schema": "note/1",
        "passed": False,
        "checks": {
            **passing_checks,
            "attribution": {"applies": True, "ok": False},
        },
        "meeting": {
            "id": "fixture",
            "source": "fixture",
            "attribution": "none",
            "turns": 1,
        },
        "claims": [{"claim": "REJECTED CLAIM MUST NOT RENDER"}],
        "provenance": {
            "model": "fixture",
            "elapsed_s": 0.1,
            "passes": 1,
            "slices": None,
        },
    }
    try:
        require_ready_note(fixture, Path("failed.note.json"))
    except SystemExit as exc:
        if "summary-failed" in str(exc):
            pass
        else:
            raise
    else:
        raise SystemExit(
            "a passed:false diagnostic was allowed onto a ready-note surface"
        )

    transcript = Transcript(
        source="fixture",
        attribution="none",
        turns=[],
    )
    capture_doc = {
        "capture_health": None,
        "capture_integrity_unknown": True,
        "capture_warnings": [CAPTURE_INTEGRITY_UNKNOWN_WARNING],
    }
    failed_section = failed_meeting_section(
        fixture, Path("failed.note.json"), transcript, capture_doc
    )
    failed_row = failed_library_row(fixture, capture_doc)
    if (
        "REJECTED CLAIM MUST NOT RENDER" in failed_section + failed_row
        or 'class="claims"' in failed_section + failed_row
        or 'class="trust"' in failed_section + failed_row
        or (failed_section + failed_row).count("Summary withheld") != 1
    ):
        raise SystemExit(
            "a passed:false diagnostic leaked claims or ready-note trust into "
            "the product encounter"
        )

    accepted = dict(fixture)
    accepted["passed"] = True
    accepted["checks"] = passing_checks
    accepted["claims"] = []
    ready_section, _counts = meeting_section(
        accepted, Path("accepted.note.json"), transcript, capture_doc
    )
    ready_row = library_row(accepted, capture_doc)
    if 'class="claims"' not in ready_section or 'class="lib-trust"' not in ready_row:
        raise SystemExit("the accepted-note renderer no longer reaches its ready surface")


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


def encounter_claim_row(item: dict, index: int, meeting: str, transcript: Transcript) -> str:
    """Render one operator-confirmed review item without implying model validation."""
    color = STATES["located"][2]
    evidence_rows = []
    for evidence_index, evidence in enumerate(item["evidence"], start=1):
        turn = evidence["turn"]
        part = (
            f'<span class="evidence-part">source {evidence_index} of '
            f'{len(item["evidence"])}</span>'
            if len(item["evidence"]) > 1
            else ""
        )
        evidence_rows.append(
            f'<blockquote class="quote" style="--state:{color}">'
            f'<button class="at" data-meeting="{esc(meeting)}" data-turn="{turn}">'
            f'{esc(stamp(transcript.turns[turn].start))}</button>{part}'
            f'<span class="qtext">{esc(evidence["quote"])}</span></blockquote>'
        )
    kind = item["type"].replace("_", " ")
    return f'''
<li class="claim claim-located" id="c-{esc(meeting)}-{index}">
  <p class="claim-text"><span class="kind">{esc(kind)}</span>{esc(item["claim"])}</p>
  <p class="claim-state" style="--state:{color}">
    <span class="mark" aria-hidden="true">{MARKS[STATES["located"][0]]}</span>
    <span class="word">operator confirmed</span>
    <span class="why">wording and exact evidence accepted in a separate digest-bound review</span>
  </p>
  {"".join(evidence_rows)}
  <p class="support unmeasured">Automatic extraction and application runtime were not tested.</p>
</li>'''


def encounter_meeting_section(content: dict, transcript: Transcript) -> str:
    """Render approved interaction content while keeping it outside note/2."""
    meeting = content["meeting"]
    meeting_id = meeting["id"]
    cited = {
        evidence["turn"]
        for item in content["items"]
        for evidence in item["evidence"]
    }
    claims = "".join(
        encounter_claim_row(item, index, meeting_id, transcript)
        for index, item in enumerate(content["items"])
    )
    return f'''
<section class="meeting" id="m-{esc(meeting_id)}">
  <header class="mhead">
    <p class="eyebrow">human-curated real content &middot; product evidence false</p>
    <h3>{esc(meeting["title"])}</h3>
    <p class="meta">{len(transcript.turns)} turns &middot; channel attribution &middot;
      {len(content["items"])} operator-confirmed review items</p>
    <div class="trust"><span class="bar-label"><strong>{len(content["items"])}</strong>
      items approved for this interaction review; automatic note quality was not tested</span></div>
  </header>
  <div class="split">
    <div class="col">
      <h4>The review &mdash; every item with its accepted evidence</h4>
      {note_annotation("human-curated",
                       "Real meeting words and operator-confirmed wording. An automatic "
                       "diagnostic supplied a draft pool but failed its own attribution "
                       "check; it is not rendered and supplies no product result.")}
      <ol class="claims">{claims}</ol>
    </div>
    <div class="col col-evidence">
      <h4>The transcript &mdash; retained source words</h4>
      {note_annotation("real data",
                       "Each evidence button resolves to the exact retained turn. The "
                       "capture passed the bounded headphone interaction gate; this does "
                       "not test an application runtime.")}
      {transcript_pane(meeting_id, transcript.turns, cited)}
    </div>
  </div>
</section>'''


def encounter_library_row(content: dict, transcript: Transcript) -> str:
    meeting = content["meeting"]
    return f'''
    <li class="lib-row">
      <span class="lib-ident">
        <a class="lib-open" href="#m-{esc(meeting["id"])}">{esc(meeting["title"])}</a>
        <span class="lib-src">human-curated interaction content</span>
        <span class="lib-turns">{len(transcript.turns)} turns</span>
        <span class="lib-date">{esc(meeting["captured_at"])}</span>
      </span>
      <span class="lib-trust"><span class="bar-label">
        <strong>{len(content["items"])}</strong> operator-confirmed review items &middot;
        automatic extraction and runtime not tested
      </span></span>
    </li>'''


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


def meeting_section(
    doc: dict,
    note_path: Path,
    transcript: Transcript,
    capture_doc: dict,
) -> tuple[str, dict]:
    require_ready_note(doc, note_path)
    m = doc["meeting"]
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
    capture_warning = capture_warning_markup(capture_doc)
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
    {capture_warning}
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


def failed_reasons(doc: dict) -> list[str]:
    """Translate only hard-gate failures; advisory checks do not become causes."""
    checks = doc["checks"]
    reasons = []
    context = checks["context"]
    attribution = checks["attribution"]
    extraction = checks.get("extraction", {"applies": False})
    if context["ok"] is False:
        reasons.append("The model did not read the complete transcript.")
    if attribution["applies"] and not attribution["ok"]:
        reasons.append(
            "The draft assigned speech to people this transcript could not identify."
        )
    if not checks["numbers"]["ok"]:
        reasons.append("The draft introduced figures that are not in the transcript.")
    if not checks["prompt_echo"]["ok"]:
        reasons.append("The draft copied meeting content from its instructions.")
    if not checks["citations"]["ok"]:
        reasons.append("The draft presented words the transcript does not contain.")
    if extraction["applies"] and not extraction["ok"]:
        reasons.append("The extraction stage dropped content shaped like a note item.")
    return reasons or ["The stored checks rejected this draft."]


def failed_meeting_section(
    doc: dict,
    note_path: Path,
    transcript: Transcript,
    capture_doc: dict,
) -> str:
    """Render the retained transcript without admitting rejected claim content."""
    m = doc["meeting"]
    prov = doc["provenance"]
    reasons = "".join(f"<li>{esc(reason)}</li>" for reason in failed_reasons(doc))
    capture_warning = capture_warning_markup(capture_doc)
    section = f'''
<section class="meeting summary-withheld" id="failed-{esc(m["id"])}">
  <header class="mhead">
    <p class="eyebrow">transcript ready &middot; summary withheld</p>
    <h3>{esc(m["id"])}</h3>
    <p class="meta">{esc(len(transcript.turns))} turns &middot;
      {esc(prov["model"])} &middot; {esc(prov["elapsed_s"])}s</p>
    {capture_warning}
  </header>
  <div class="split">
    <div class="col withheld-summary">
      <h4>No usable summary was produced</h4>
      <p>The retained transcript is intact. The generated draft failed the checks
        required before a note can enter the library:</p>
      <ul>{reasons}</ul>
      <p>The rejected draft remains research evidence only. None of its claims are
        shown or counted here.</p>
      <button type="button" data-panel="spec-summarizing"
        data-action="retry-summary">review the summary retry state (prototype)</button>
    </div>
    <div class="col col-evidence">
      <h4>The retained transcript</h4>
      {transcript_pane(m["id"], transcript.turns, set())}
    </div>
  </div>
</section>'''
    if 'class="claims"' in section or 'class="trust"' in section:
        raise SystemExit(
            f"{note_path}: rejected output reached a ready-note renderer"
        )
    return section


def library_row(doc: dict, capture_doc: dict) -> str:
    m, c = doc["meeting"], counts(doc)
    capture_warning = capture_warning_markup(capture_doc, compact=True)
    return f'''
    <li class="lib-row">
      <span class="lib-ident">
        <a class="lib-open" href="#m-{esc(m["id"])}">{esc(m["id"])}</a>
        <span class="lib-src">{esc(m["source"])}</span>
        <span class="lib-turns">{esc(m["turns"])} turns</span>
        <span class="lib-date" title="corpus meetings carry no date; a real capture
          records captured_at">no date</span>
        {capture_warning}
      </span>
      <span class="lib-trust">{trust_bar(c)}</span>
    </li>'''


def failed_library_row(doc: dict, capture_doc: dict) -> str:
    """One product row for a retained transcript whose summary was rejected."""
    m = doc["meeting"]
    capture_warning = capture_warning_markup(capture_doc, compact=True)
    return f'''
    <li class="lib-row summary-withheld-row">
      <span class="lib-ident">
        <a class="lib-open" href="#failed-{esc(m["id"])}">{esc(m["id"])}</a>
        <span class="lib-src">{esc(m["source"])}</span>
        <span class="lib-turns">{esc(m["turns"])} turns</span>
        <span class="lib-date">transcript ready</span>
        {capture_warning}
      </span>
      <span class="summary-withheld-label">Summary withheld &mdash; open the transcript
        or retry processing.</span>
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
      <p class="eyebrow">review build &middot; no files changed</p>
      <h2>Capture a meeting</h2>
      <p class="lede">Walk through setup, recording, processing, and recovery. This
        click-through requests no permissions and records nothing.</p>
    </div>
    <div class="menubar" aria-live="polite">
      <span class="menubar-label">menu bar</span>
      <span class="menubar-glyph glyph-idle" id="menubar-glyph" aria-hidden="true">○</span>
      <strong id="menubar-word">idle</strong>
    </div>
  </header>
  <details class="reviewer-details state-picker">
    <summary>Reviewer shortcut: open any state</summary>
    <div class="encounter-controls" aria-label="Review states">
      <button type="button" data-panel="spec-library">library</button>
      <button type="button" data-panel="spec-empty-library">empty library</button>
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
      <button type="button" data-panel="spec-summarizing">summarizing</button>
      <button type="button" data-panel="spec-processing-failed">processing failure</button>
    <button type="button" data-panel="spec-correction">correction</button>
    <button type="button" data-panel="spec-retention">retention</button>
      <button type="button" data-panel="spec-delete-meeting">delete meeting</button>
      <button type="button" data-panel="spec-far-end">far-end notice</button>
      <button type="button" data-recovery-start="runtime-missing">
        startup: runtime missing</button>
      <button type="button" data-recovery-start="service-timeout">
        startup: service timeout</button>
      <button type="button" data-recovery-reset>
        reset startup specimen</button>
    </div>
  </details>

  <section class="encounter-panel is-active" id="spec-library" data-menubar="idle">
    <h3>Your meetings</h3>
    <p>Opening the app never resumes a recording. Existing transcripts remain readable
      even when their summaries were withheld.</p>
    <p class="state-result" id="capture-eligibility">Supported capture unavailable:
      complete voice enrollment first. Existing meetings remain readable.</p>
      <div class="panel-actions">
      <button type="button" id="manual-capture" data-action="manual-start" disabled>
        start capture — setup required
      </button>
      <button type="button" data-panel="spec-first-run">review first launch</button>
        <button type="button" data-panel="spec-enrollment-blocked">
          review enrollment blocker</button>
        <button type="button" data-panel="spec-empty-library">review empty library</button>
        <button type="button" data-panel="spec-retention">
          review storage and deletion</button>
        <button type="button" data-recovery-start="runtime-missing">
          review missing-runtime recovery</button>
        <button type="button" data-recovery-start="service-timeout">
          review service-timeout recovery</button>
      </div>
    </section>

  <section class="encounter-panel" id="spec-empty-library" data-menubar="idle" hidden>
      <p class="eyebrow">first-run library · interaction specimen</p>
      <h3>No meetings yet</h3>
      <p>No meeting, transcript, note, or audio is held in this specimen. Nothing is
        recording, and this is different from transcription or summary work still in
        progress. This is not a loading failure.</p>
      <p class="state-result">Start remains unavailable until permissions, retention,
        and voice enrollment are complete.</p>
      <div class="panel-actions">
        <button type="button" data-panel="spec-first-run">review first launch</button>
        <button type="button" data-panel="spec-library">return to populated library</button>
    </div>
  </section>

  <section class="encounter-panel" id="spec-startup-runtime-missing"
    data-menubar="startup-failed" hidden>
    <p class="eyebrow">interaction specimen · no runtime checked</p>
    <h3>Local capture needs setup</h3>
    <p>One required local component is unavailable. Existing meetings remain readable.
      No capture began, so this attempt created no meeting audio.</p>
    <p class="state-result">Interaction specimen: no diagnostic was written and no
      local file changed.</p>
    <div class="panel-actions">
      <button type="button" data-recovery-event="diagnostic-written">
        review diagnostic step</button>
      <button type="button" data-panel="spec-library">
        return to library — capture stays blocked</button>
    </div>
  </section>

  <section class="encounter-panel" id="spec-startup-service-timeout"
    data-menubar="startup-failed" hidden>
    <p class="eyebrow">interaction specimen · no runtime checked</p>
    <h3>Local capture did not finish starting</h3>
    <p>A child service did not report ready. A real app must stop partial child work,
      keep existing meetings readable, and preserve any audio already captured before
      the timeout.</p>
    <p class="state-result">Interaction specimen: no diagnostic was written and no
      local file changed.</p>
    <div class="panel-actions">
      <button type="button" data-recovery-event="diagnostic-written">
        review diagnostic step</button>
      <button type="button" data-panel="spec-library">
        return to library — capture stays blocked</button>
    </div>
  </section>

  <section class="encounter-panel" id="spec-startup-runtime-diagnostic"
    data-menubar="startup-failed" hidden>
    <p class="eyebrow">diagnostic-location specimen · runtime missing</p>
    <h3>Where a local diagnostic would be shown</h3>
    <p>An implemented app must show the exact local path. This review build leaves a
      labelled slot instead of inventing a file it did not write.</p>
    <p class="state-result">Diagnostic location: unavailable in this specimen. No
      diagnostic was written and no local file changed.</p>
    <div class="panel-actions">
      <button type="button" data-recovery-event="retry">review bounded retry</button>
      <button type="button" data-panel="spec-library">
        return to library — capture stays blocked</button>
    </div>
  </section>

  <section class="encounter-panel" id="spec-startup-timeout-diagnostic"
    data-menubar="startup-failed" hidden>
    <p class="eyebrow">diagnostic-location specimen · service timeout</p>
    <h3>Where a local diagnostic would be shown</h3>
    <p>An implemented app must show the exact local path after stopping partial child
      work. This review build leaves a labelled slot instead of inventing a file.</p>
    <p class="state-result">Diagnostic location: unavailable in this specimen. No
      diagnostic was written and no local file changed.</p>
    <div class="panel-actions">
      <button type="button" data-recovery-event="retry">review bounded retry</button>
      <button type="button" data-panel="spec-library">
        return to library — capture stays blocked</button>
    </div>
  </section>

  <section class="encounter-panel" id="spec-startup-retry"
    data-menubar="startup-failed" hidden>
    <p class="eyebrow">ordered recovery specimen · retry in review only</p>
    <h3>Try the local components again</h3>
    <p>A real retry checks the same local components. It does not delete meetings or
      recorded audio, and another retry cannot start while one is active.</p>
    <p class="state-result">Interaction specimen: no service was retried, no diagnostic
      was written, and no local file changed.</p>
    <div class="panel-actions">
      <button type="button" data-recovery-event="recovered">
        show startup problem cleared</button>
      <button type="button" data-recovery-event="failed">show retry still blocked</button>
      <button type="button" data-panel="spec-library">
        return to library — capture stays blocked</button>
    </div>
  </section>

  <section class="encounter-panel" id="spec-startup-reinstall"
    data-menubar="startup-failed" hidden>
    <p class="eyebrow">last recovery step · reinstall guidance specimen</p>
    <h3>Reinstall local capture components</h3>
    <p>Use this only after the ordered earlier step cannot restore readiness. Existing
      meetings and any retained audio remain on this Mac.</p>
    <p class="state-result">Interaction specimen: nothing was reinstalled, no
      diagnostic was written, and no local file changed.</p>
    <div class="panel-actions">
      <button type="button" data-recovery-event="recheck">review readiness check</button>
      <button type="button" data-panel="spec-library">
        return to library — capture stays blocked</button>
    </div>
  </section>

  <section class="encounter-panel" id="spec-startup-blocked"
    data-menubar="startup-failed" hidden>
    <p class="eyebrow">recovery exhausted · capture remains blocked</p>
    <h3>Local capture is still unavailable</h3>
    <p>The ordered retry and reinstall check did not restore readiness. Existing notes
      and transcripts remain readable; any retained audio remains available on this Mac.
      Repair or reinstall the local components before another capture attempt.</p>
    <p class="state-result">Interaction specimen: no repair ran, no diagnostic was
      written, and no local file changed.</p>
    <button type="button" data-panel="spec-library">
      return to library — capture stays blocked</button>
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
    <p class="eyebrow">processing-order specimen · capture would be stopped</p>
    <h3>Transcribing</h3>
    <p>In a real capture, retained audio is processed locally here. This specimen creates
      no transcript. Transcription must finish before summary generation begins; neither
      state means a usable note exists.</p>
    <button type="button" data-panel="spec-summarizing" data-action="finish-transcription">
      finish transcription</button>
    <button type="button" data-panel="spec-transcription-failed">
      simulate transcription failure</button>
  </section>

  <section class="encounter-panel" id="spec-summarizing" data-menubar="summarizing" hidden>
    <p class="eyebrow">processing-order specimen · no transcript created here</p>
    <h3>Building and checking the note</h3>
    <p>In a real capture, this state begins after the transcript is retained. No note is
      ready until claim evidence, attribution, and the stored verdict reconcile. A
      rejected result keeps the transcript and withholds the note.</p>
    <button type="button" data-panel="spec-note-ready" data-action="finish-processing">
      finish summary checks</button>
    <button type="button" data-panel="spec-processing-failed">
      simulate rejected summary</button>
  </section>

  <section class="encounter-panel" id="spec-transcription-failed"
    data-menubar="error" hidden>
    <p class="eyebrow">transcription-failure specimen · no transcript created here</p>
    <h3>A failed transcription would leave the captured audio available</h3>
    <p>In a real capture, no transcript or summary would exist yet. Retry starts
      transcription again from the retained meeting audio; it does not pretend a note
      survived.</p>
    <button type="button" data-panel="spec-transcribing"
      data-action="retry-transcription">retry transcription from retained audio</button>
  </section>

  <section class="encounter-panel" id="spec-processing-failed" data-menubar="error" hidden>
    <p class="eyebrow">summary-failure specimen · no accepted note created here</p>
    <h3>A rejected summary would leave the transcript available</h3>
    <p>In a real run, the transcript remains when the model is unavailable or its output
      fails the checks that keep invented attribution and evidence out of a ready note.
      Rejected output is diagnostic material, not a note in the library.</p>
    <button type="button" data-panel="spec-summarizing"
      data-action="retry-summary">retry summary from retained transcript</button>
  </section>

  <section class="encounter-panel" id="spec-note-ready" data-menubar="idle" hidden>
    <p class="eyebrow">interaction specimen · no source content asserted</p>
    <h3>A successful note would appear at the top of the library</h3>
    <p>The specimen row is now visible below. It carries no invented meeting name,
      quote, or result. The available real detail may be a retained transcript whose
      summary was withheld; the action says only that it opens the available treatment.</p>
    <button type="button" data-action="open-real-data-detail">
      review the available meeting detail
    </button>
    <button type="button" data-panel="spec-correction">
      review a withheld-turn correction
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


def page(
    sections: str,
    library: str,
    totals: dict[str, int],
    tok: dict[str, str],
    meetings: int,
    accepted: int,
    rejected: int,
    *,
    encounter_review: bool = False,
) -> str:
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
    if encounter_review:
        detail_state = (
            "Displayed review: operator-confirmed for this interaction only; "
            "automatic extraction and application runtime were not tested."
        )
        product_lede = (
            "A local-first macOS product encounter populated with a consented headphone "
            "capture. This reviews interaction design, not automatic note quality."
        )
        evidence_lede = (
            f"This build contains {meetings} real channel-attributed transcript and "
            f"{sum(totals.values())} operator-confirmed review items. The populated "
            "content is human-curated, product evidence is false, and runtime validation "
            "was not run."
        )
        details_label = "Reviewer details: boundaries on the approved encounter content"
        reviewer_legend = note_annotation(
            "human-curated",
            "The populated items do not use automatic-note evidence states. Their "
            "wording and exact transcript spans were accepted through a separate "
            "digest-bound operator receipt.",
        )
        library_lede = (
            "The populated row is real meeting content approved for this interaction "
            "review. It is not a passing automatic note."
        )
        provenance_annotation = note_annotation(
            "human-curated",
            f"{meetings} retained real transcript and {sum(totals.values())} "
            "operator-confirmed review items. Automatic extraction and application "
            "runtime remain untested.",
        )
        date_annotation = note_annotation(
            "real data",
            "The date comes from the capture session. Speaker labels remain Me and "
            "Them because channel attribution does not identify a person by name.",
        )
    else:
        detail_state = (
            "Displayed note: current for its retained transcript."
            if accepted
            else "No accepted note is available in this build. The retained transcript is shown."
        )
        product_lede = (
            "A local-first macOS product encounter. Capture is manual, headphones "
            "are required, and no summary enters the library unless its hard checks pass."
        )
        evidence_lede = (
            f"This build contains {meetings} "
            f'{"real transcript" if meetings == 1 else "real transcripts"}: '
            f'{accepted} accepted {"summary" if accepted == 1 else "summaries"} and '
            f'{rejected} {"summary withheld" if rejected == 1 else "summaries withheld"}. '
            "Rejected draft claims are not shown or counted."
        )
        details_label = "Reviewer details: evidence labels used on accepted notes"
        reviewer_legend = (
            f'<ul class="legend">{legend}</ul><ul class="legend kinds">{kinds}</ul>'
        )
        library_lede = (
            "A failed summary never becomes an empty or misleading note. Open its "
            "retained transcript, or retry processing."
        )
        provenance_annotation = note_annotation(
            "real data",
            f"{meetings} retained real transcript"
            f'{"s" if meetings != 1 else ""}; {accepted} accepted summary '
            f"and {rejected} withheld. Rejected claim content never enters these rows.",
        )
        date_annotation = note_annotation(
            "open question",
            "The date column reads <em>no date</em> because corpus meetings carry none. "
            "A real capture records <code>captured_at</code>, so this is a limit of "
            "the material and not of the product &mdash; but it does mean chronological "
            "ordering is untested here.",
        )
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Meeting notes product encounter</title>
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
  .lib-capture {{ color: var(--semantic-error); font-size: 11px;
                  flex-basis: 100%; }}
  .summary-withheld-label {{ display: block; color: var(--semantic-error);
                             font-size: 12px; }}

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
  .capture-warning {{ max-width: 78ch; margin: 14px 0 4px;
                      padding: 12px 14px; background: var(--surface-raised);
                      border-left: 2px solid var(--semantic-error);
                      border-radius: 0 4px 4px 0; }}
  .capture-warning strong {{ color: var(--semantic-error); }}
  .capture-warning ul {{ margin: 6px 0 0; padding-left: 18px; }}
  .withheld-summary {{ padding: 16px 18px; background: var(--surface-raised);
                       border-left: 2px solid var(--semantic-error);
                       border-radius: 0 6px 6px 0; }}
  .withheld-summary p, .withheld-summary li {{ color: var(--neutral-300); }}
  .withheld-summary button {{ background: var(--surface-overlay);
                              border: 1px solid var(--neutral-600);
                              border-radius: 3px; color: var(--neutral-100);
                              cursor: pointer; padding: 6px 9px; }}
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
  .reviewer-details {{ margin: 14px 0; color: var(--neutral-400); }}
  .reviewer-details > summary {{ cursor: pointer; color: var(--neutral-300);
                                 font-size: 12px; }}
  .state-picker {{ margin: 0; border-bottom: 1px solid var(--neutral-700); }}
  .state-picker > summary {{ padding: 9px 18px; }}
  .state-picker .encounter-controls {{ padding-top: 4px; border-bottom: 0; }}
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

<h1>Meeting notes</h1>
<p class="lede">{esc(product_lede)}</p>
<p class="lede">{esc(evidence_lede)}</p>

{encounter()}

<details class="reviewer-details">
<summary>{esc(details_label)}</summary>
{reviewer_legend}
</details>

<h2>Your meetings</h2>
<p class="lede">{esc(library_lede)}</p>
<details class="reviewer-details">
<summary>Reviewer details: provenance and corpus limits</summary>
{provenance_annotation}
{date_annotation}
</details>
<ul class="lib">
  <li class="lib-row specimen-new-note" id="specimen-new-note">
    <span class="lib-ident"><strong>new note</strong><span class="lib-src">interaction
      specimen</span>
      <span class="lib-turns">no meeting content asserted</span></span>
    <span class="bar-label">This row appears only after the specimen reaches its
      ready state. It does not stand in for a captured meeting.</span>
    <button type="button" class="lib-review" data-action="open-real-data-detail">
      review available meeting detail
    </button>
  </li>
  {library}
</ul>

<div id="real-data-detail">
  <h2>Meeting detail</h2>
  <p class="displayed-note-state" id="displayed-note-state">
    {esc(detail_state)}
  </p>
</div>
{sections}

<details class="reviewer-details">
<summary>Reviewer details: historical evidence treatment and open questions</summary>
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
</details>

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

  // BEGIN STARTUP RECOVERY STATE MACHINE
  var STARTUP_RECOVERY_TRANSITIONS = Object.freeze({{
    idle: Object.freeze({{
      'runtime-missing': 'runtime-missing',
      'service-timeout': 'service-timeout'
    }}),
    'runtime-missing': Object.freeze({{
      'diagnostic-written': 'runtime-diagnostic'
    }}),
    'service-timeout': Object.freeze({{
      'diagnostic-written': 'timeout-diagnostic'
    }}),
    'runtime-diagnostic': Object.freeze({{
      retry: 'retry-runtime'
    }}),
    'timeout-diagnostic': Object.freeze({{
      retry: 'retry-timeout'
    }}),
    'retry-runtime': Object.freeze({{
      recovered: 'idle',
      failed: 'reinstall'
    }}),
    'retry-timeout': Object.freeze({{
      recovered: 'idle',
      failed: 'reinstall'
    }}),
    reinstall: Object.freeze({{
      recheck: 'retry-after-reinstall'
    }}),
    'retry-after-reinstall': Object.freeze({{
      recovered: 'idle',
      failed: 'blocked'
    }}),
    blocked: Object.freeze({{}})
  }});
  var STARTUP_RECOVERY_PANELS = Object.freeze({{
    idle: 'spec-library',
    'runtime-missing': 'spec-startup-runtime-missing',
    'service-timeout': 'spec-startup-service-timeout',
    'runtime-diagnostic': 'spec-startup-runtime-diagnostic',
    'timeout-diagnostic': 'spec-startup-timeout-diagnostic',
    'retry-runtime': 'spec-startup-retry',
    'retry-timeout': 'spec-startup-retry',
    reinstall: 'spec-startup-reinstall',
    'retry-after-reinstall': 'spec-startup-retry',
    blocked: 'spec-startup-blocked'
  }});
  function nextStartupRecoveryState(state, event) {{
    var available = STARTUP_RECOVERY_TRANSITIONS[state];
    if (!available || !available[event]) {{
      throw new Error('invalid startup recovery transition: ' + state + ' + ' + event);
    }}
    return available[event];
  }}
  function startupRecoveryPanel(state) {{
    var panel = STARTUP_RECOVERY_PANELS[state];
    if (!panel) throw new Error('no startup recovery panel for ' + state);
    return panel;
  }}
  // END STARTUP RECOVERY STATE MACHINE

  var panels = Array.prototype.slice.call(document.querySelectorAll('.encounter-panel'));
  var glyphs = {{
    idle: ['○', 'idle', 'glyph-idle'],
    detected: ['◎', 'detected', 'glyph-detected'],
    armed: ['◌', 'armed', 'glyph-armed'],
    recording: ['●', 'recording', 'glyph-recording'],
    degraded: ['●!', 'degraded', 'glyph-degraded'],
    transcribing: ['≋', 'transcribing', 'glyph-transcribing'],
    summarizing: ['≋', 'summarizing', 'glyph-transcribing'],
    'startup-failed': ['X', 'startup blocked', 'glyph-error'],
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
  var startupRecoveryState = 'idle';
  var enrollmentState = 'blocked';
  var grantedPermissions = new Set();
  var selectedRetention = null;
  var selectedPolicyTarget = null;
  var discardOriginPanel = null;
  var captureAttemptActive = false;
  function beginStartupRecovery(failure) {{
    if (startupRecoveryState !== 'idle') {{
      throw new Error('startup recovery already active: ' + startupRecoveryState);
    }}
    startupRecoveryState = nextStartupRecoveryState(startupRecoveryState, failure);
    renderEnrollmentState();
    showPanel(startupRecoveryPanel(startupRecoveryState));
  }}
  function advanceStartupRecovery(event) {{
    startupRecoveryState = nextStartupRecoveryState(startupRecoveryState, event);
    renderEnrollmentState();
    showPanel(startupRecoveryPanel(startupRecoveryState));
  }}
  function resetStartupRecovery() {{
    startupRecoveryState = 'idle';
    renderEnrollmentState();
    showPanel(startupRecoveryPanel(startupRecoveryState));
  }}
  function captureReady() {{
    return startupRecoveryState === 'idle'
      && enrollmentHasValidProfile(enrollmentState)
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
    if (startupRecoveryState !== 'idle') missing.push('local capture runtime');
    document.getElementById('capture-eligibility').textContent = allowed
      ? 'Supported capture ready: valid profile, both current permissions, and '
        + 'meeting-audio retention are present.'
      : 'Supported capture unavailable: missing ' + missing.join(', ') + '.';
    document.getElementById('future-consent').disabled = !allowed;
    document.querySelectorAll('button[data-recovery-start]')
      .forEach(function (button) {{
        button.disabled = startupRecoveryState !== 'idle';
      }});
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
    if (
      button.dataset.action === 'retry-transcription'
      || button.dataset.action === 'retry-summary'
    ) {{
      var retryPanel = document.getElementById(button.dataset.panel);
      retryPanel.setAttribute('tabindex', '-1');
      retryPanel.focus({{preventScroll: true}});
      document.getElementById('encounter').scrollIntoView({{
        block: 'start',
        behavior: 'smooth'
      }});
    }}
  }});
  document.querySelectorAll('button[data-recovery-start]').forEach(function (button) {{
    button.addEventListener('click', function () {{
      beginStartupRecovery(button.dataset.recoveryStart);
    }});
  }});
  document.querySelectorAll('button[data-recovery-event]').forEach(function (button) {{
    button.addEventListener('click', function () {{
      advanceStartupRecovery(button.dataset.recoveryEvent);
    }});
  }});
  document.querySelectorAll('button[data-recovery-reset]').forEach(function (button) {{
    button.addEventListener('click', resetStartupRecovery);
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


def check_enrollment_js(page_html: str, node: Path) -> int:
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
    output = run_node(
        node,
        controls + assertions,
        "enrollment JavaScript transition check",
    )
    try:
        return int(output)
    except ValueError as exc:
        raise SystemExit("enrollment JavaScript check returned no assertion count") from exc


def check_startup_recovery_js(page_html: str, node: Path) -> int:
    """Execute the ordered startup-recovery contract without a browser."""
    match = re.search(
        r"// BEGIN STARTUP RECOVERY STATE MACHINE"
        r"(.*?)// END STARTUP RECOVERY STATE MACHINE",
        page_html,
        re.DOTALL,
    )
    if not match:
        raise SystemExit("startup recovery JavaScript state machine is missing")
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

let state = nextStartupRecoveryState('idle', 'runtime-missing');
equal(state, 'runtime-missing');
equal(startupRecoveryPanel(state), 'spec-startup-runtime-missing');
throws(() => nextStartupRecoveryState(state, 'retry'),
       'runtime missing cannot skip its diagnostic');
throws(() => nextStartupRecoveryState(state, 'recovered'),
       'a startup failure cannot jump to ready');
state = nextStartupRecoveryState(state, 'diagnostic-written');
equal(state, 'runtime-diagnostic');
equal(startupRecoveryPanel(state), 'spec-startup-runtime-diagnostic');
throws(() => nextStartupRecoveryState(state, 'reinstall'),
       'runtime missing takes its bounded retry before reinstall');
state = nextStartupRecoveryState(state, 'retry');
equal(state, 'retry-runtime');
equal(startupRecoveryPanel(state), 'spec-startup-retry');
throws(() => nextStartupRecoveryState(state, 'retry'),
       'a retry cannot start while one is active');
state = nextStartupRecoveryState(state, 'failed');
equal(state, 'reinstall');
equal(startupRecoveryPanel(state), 'spec-startup-reinstall');
throws(() => nextStartupRecoveryState(state, 'recovered'),
       'reinstall guidance is not proof of recovery');
state = nextStartupRecoveryState(state, 'recheck');
equal(state, 'retry-after-reinstall');
equal(startupRecoveryPanel(state), 'spec-startup-retry');
throws(() => nextStartupRecoveryState(state, 'retry'),
       'a post-reinstall check cannot overlap another retry');
state = nextStartupRecoveryState(state, 'failed');
equal(state, 'blocked');
equal(startupRecoveryPanel(state), 'spec-startup-blocked');
throws(() => nextStartupRecoveryState(state, 'recheck'),
       'an exhausted recovery is stable until a new operator action');

state = nextStartupRecoveryState('idle', 'service-timeout');
equal(state, 'service-timeout');
equal(startupRecoveryPanel(state), 'spec-startup-service-timeout');
throws(() => nextStartupRecoveryState(state, 'retry'),
       'service timeout cannot retry before a diagnostic exists');
state = nextStartupRecoveryState(state, 'diagnostic-written');
equal(state, 'timeout-diagnostic');
equal(startupRecoveryPanel(state), 'spec-startup-timeout-diagnostic');
throws(() => nextStartupRecoveryState(state, 'reinstall'),
       'service timeout takes its bounded retry before reinstall');
state = nextStartupRecoveryState(state, 'retry');
equal(state, 'retry-timeout');
equal(startupRecoveryPanel(state), 'spec-startup-retry');
throws(() => nextStartupRecoveryState(state, 'retry'),
       'a second timeout retry cannot overlap the first');
state = nextStartupRecoveryState(state, 'recovered');
equal(state, 'idle');
equal(startupRecoveryPanel(state), 'spec-library');

state = nextStartupRecoveryState('idle', 'service-timeout');
state = nextStartupRecoveryState(state, 'diagnostic-written');
state = nextStartupRecoveryState(state, 'retry');
state = nextStartupRecoveryState(state, 'failed');
equal(state, 'reinstall');
equal(startupRecoveryPanel(state), 'spec-startup-reinstall');
state = nextStartupRecoveryState(state, 'recheck');
equal(state, 'retry-after-reinstall');
equal(startupRecoveryPanel(state), 'spec-startup-retry');
state = nextStartupRecoveryState(state, 'recovered');
equal(state, 'idle');
equal(startupRecoveryPanel(state), 'spec-library');
throws(() => nextStartupRecoveryState('idle', 'note-ready'),
       'startup recovery never routes directly to a note');
process.stdout.write(String(checks));
"""
    output = run_node(
        node,
        controls + assertions,
        "startup recovery JavaScript transition check",
    )
    try:
        return int(output)
    except ValueError as exc:
        raise SystemExit("startup recovery JavaScript check returned no assertion count") from exc


def check_capture_dom_js(page_html: str, node: Path) -> int:
    """Exercise readiness and capture-attempt state against concrete DOM fields."""
    enrollment_state = re.search(
        r"// BEGIN ENROLLMENT STATE MACHINE(.*?)// END ENROLLMENT STATE MACHINE",
        page_html,
        re.DOTALL,
    )
    startup_state = re.search(
        r"// BEGIN STARTUP RECOVERY STATE MACHINE"
        r"(.*?)// END STARTUP RECOVERY STATE MACHINE",
        page_html,
        re.DOTALL,
    )
    contract = re.search(
        r"// BEGIN CAPTURE DOM CONTRACT(.*?)// END CAPTURE DOM CONTRACT",
        page_html,
        re.DOTALL,
    )
    if not enrollment_state or not startup_state or not contract:
        raise SystemExit(
            "capture DOM, enrollment, or startup recovery contract is missing"
        )
    harness = r"""
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
const recoveryStartButtons = [
  fake('runtime-missing', {dataset: {recoveryStart: 'runtime-missing'}}),
  fake('service-timeout', {dataset: {recoveryStart: 'service-timeout'}})
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
    if (selector === 'button[data-recovery-start]') return recoveryStartButtons;
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

beginStartupRecovery('runtime-missing');
equal(startupRecoveryState, 'runtime-missing');
equal(shownPanel, 'spec-startup-runtime-missing');
equal(elements['manual-capture'].disabled, true,
      'startup failure disables an otherwise ready Start');
equal(recoveryStartButtons.every((button) => button.disabled), true,
      'an active recovery disables competing failure starts');
throws(() => beginStartupRecovery('service-timeout'),
       'a second recovery cannot overwrite the active one');
equal(startupRecoveryState, 'runtime-missing',
      'refused scenario switch preserves the active failure');
advanceStartupRecovery('diagnostic-written');
advanceStartupRecovery('retry');
equal(startupRecoveryState, 'retry-runtime');
throws(() => beginStartupRecovery('service-timeout'),
       'a retry cannot be replaced by another failure');
advanceStartupRecovery('failed');
advanceStartupRecovery('recheck');
advanceStartupRecovery('failed');
equal(startupRecoveryState, 'blocked');
equal(shownPanel, 'spec-startup-blocked');
equal(beginCaptureAttempt(), false,
      'exhausted startup recovery blocks capture');
showPanel('spec-library');
equal(shownPanel, 'spec-library');
equal(elements['manual-capture'].disabled, true,
      'returning to the library does not cure startup failure');
resetStartupRecovery();
equal(startupRecoveryState, 'idle');
equal(shownPanel, 'spec-library');
equal(elements['manual-capture'].disabled, false,
      'explicit specimen reset restores otherwise complete readiness');
equal(recoveryStartButtons.every((button) => !button.disabled), true,
      'explicit specimen reset re-enables reviewer scenario starts');
beginStartupRecovery('service-timeout');
advanceStartupRecovery('diagnostic-written');
advanceStartupRecovery('retry');
advanceStartupRecovery('failed');
equal(startupRecoveryState, 'reinstall',
      'failed timeout retry reaches reinstall guidance');
advanceStartupRecovery('recheck');
equal(startupRecoveryState, 'retry-after-reinstall',
      'timeout recovery rechecks once after reinstall guidance');
advanceStartupRecovery('recovered');
equal(startupRecoveryState, 'idle',
      'successful post-reinstall check clears the startup block');
equal(shownPanel, 'spec-library');
equal(elements['manual-capture'].disabled, false,
      'successful post-reinstall check restores otherwise complete readiness');

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
    output = run_node(
        node,
        (
            harness
            + enrollment_state.group(1)
            + startup_state.group(1)
            + contract.group(1)
            + assertions
        ),
        "capture DOM check",
    )
    try:
        return int(output)
    except ValueError as exc:
        raise SystemExit("capture DOM check returned no assertion count") from exc


def check_encounter_wiring(page_html: str) -> int:
    """Fail if an interaction state can be named but not reached.

    The review surface is deliberately static, so a dead control would otherwise look
    like a product omission rather than a prototype wiring bug. This checks the
    markup contract rather than attempting to execute browser JavaScript here.
    """
    expected = {
        "spec-library", "spec-empty-library", "spec-first-run",
        "spec-startup-runtime-missing", "spec-startup-service-timeout",
        "spec-startup-runtime-diagnostic", "spec-startup-timeout-diagnostic",
        "spec-startup-retry", "spec-startup-reinstall", "spec-startup-blocked",
        "spec-detected", "spec-consent",
        "spec-enrollment-blocked", "spec-first-sitting-saved",
        "spec-resume-after-gap", "spec-second-sitting-review",
        "spec-negative-sample", "spec-operating-point", "spec-ready-to-build",
        "spec-building-profile", "spec-enrolled",
        "spec-returning-profile", "spec-discard-enrollment",
        "spec-profile-reset", "spec-retention-choice",
        "spec-armed", "spec-recording", "spec-degraded", "spec-transcribing",
        "spec-summarizing", "spec-transcription-failed",
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
    allowed_menubar = {
        "idle", "detected", "armed", "recording", "degraded", "transcribing",
        "summarizing", "startup-failed", "error",
    }
    unknown = {state for _, state in panels} - allowed_menubar
    if unknown:
        raise SystemExit(f"encounter declares unknown menubar state(s): {sorted(unknown)}")
    targets = re.findall(r'<button[^>]*data-panel="([^\"]+)"', page_html)
    missing = sorted(set(targets) - panel_ids)
    if missing:
        raise SystemExit(f"encounter button(s) target no panel: {missing}")
    state_pickers = re.findall(
        r'<details class="reviewer-details state-picker">.*?</details>',
        page_html,
        re.DOTALL,
    )
    if len(state_pickers) != 1:
        raise SystemExit("encounter must have exactly one identifiable reviewer state picker")
    primary_page = page_html.replace(state_pickers[0], "", 1)
    primary_targets = set(
        re.findall(r'<button[^>]*data-panel="([^\"]+)"', primary_page)
    )
    for required_primary in ("spec-correction", "spec-retention"):
        if required_primary not in primary_targets:
            raise SystemExit(
                f"{required_primary} is reachable only through the reviewer state picker"
            )
    transition_panels = {
        "spec-first-sitting-saved", "spec-resume-after-gap",
        "spec-second-sitting-review", "spec-negative-sample",
        "spec-operating-point", "spec-ready-to-build", "spec-building-profile",
        "spec-enrolled", "spec-returning-profile",
        "spec-startup-runtime-missing", "spec-startup-service-timeout",
        "spec-startup-runtime-diagnostic", "spec-startup-timeout-diagnostic",
        "spec-startup-retry", "spec-startup-reinstall", "spec-startup-blocked",
    }
    special_panels = set(re.findall(r'data-discard-origin="([^\"]+)"', page_html))
    special_panels.add("spec-discard-enrollment")
    if not expected <= set(targets) | transition_panels | special_panels | {"spec-library"}:
        raise SystemExit("some reviewed encounter states have no incoming control")

    def encounter_panel(panel_id: str) -> str:
        panel = re.search(
            rf'<section class="encounter-panel[^\"]*" id="{panel_id}".*?</section>',
            page_html,
            re.DOTALL,
        )
        if not panel:
            raise SystemExit(f"encounter panel {panel_id} is missing")
        return panel.group(0)

    library_panel = encounter_panel("spec-library")
    for route in (
        'data-panel="spec-empty-library"',
        'data-panel="spec-retention"',
        'data-recovery-start="runtime-missing"',
        'data-recovery-start="service-timeout"',
    ):
        if route not in library_panel:
            raise SystemExit(f"library has no primary encounter route for {route}")
    empty_panel = encounter_panel("spec-empty-library")
    if (
        'data-panel="spec-first-run"' not in empty_panel
        or 'data-panel="spec-library"' not in empty_panel
        or "No meeting, transcript, note, or audio is held" not in empty_panel
    ):
        raise SystemExit("empty library no longer names what is absent and how to continue")

    recovery_events = {
        "spec-startup-runtime-missing": {"diagnostic-written"},
        "spec-startup-service-timeout": {"diagnostic-written"},
        "spec-startup-runtime-diagnostic": {"retry"},
        "spec-startup-timeout-diagnostic": {"retry"},
        "spec-startup-retry": {"recovered", "failed"},
        "spec-startup-reinstall": {"recheck"},
        "spec-startup-blocked": set(),
    }
    for panel_id, expected_panel_events in recovery_events.items():
        panel = encounter_panel(panel_id)
        actual_panel_events = set(
            re.findall(r'data-recovery-event="([^\"]+)"', panel)
        )
        if actual_panel_events != expected_panel_events:
            raise SystemExit(
                f"{panel_id} recovery events drifted: "
                f"expected {sorted(expected_panel_events)}, "
                f"got {sorted(actual_panel_events)}"
            )
        if (
            'data-panel="spec-library"' not in panel
            or "capture stays blocked" not in panel
        ):
            raise SystemExit(
                f"{panel_id} does not preserve the startup block on library return"
            )
        if "spec-note-ready" in panel:
            raise SystemExit(f"{panel_id} bypasses processing into a ready note")
        lower_panel = re.sub(r"\s+", " ", panel.lower())
        if (
            "no diagnostic was written" not in lower_panel
            or "no local file changed" not in lower_panel
        ):
            raise SystemExit(f"{panel_id} implies the interaction specimen changed files")

    transcribing_panel = encounter_panel("spec-transcribing")
    summarizing_panel = encounter_panel("spec-summarizing")
    transcription_failed_panel = encounter_panel("spec-transcription-failed")
    summary_failed_panel = encounter_panel("spec-processing-failed")
    if (
        'data-panel="spec-summarizing" data-action="finish-transcription"'
        not in re.sub(r"\s+", " ", transcribing_panel)
        or 'data-panel="spec-transcription-failed"'
        not in re.sub(r"\s+", " ", transcribing_panel)
        or 'data-panel="spec-note-ready" data-action="finish-processing"'
        not in re.sub(r"\s+", " ", summarizing_panel)
        or 'data-panel="spec-processing-failed"'
        not in re.sub(r"\s+", " ", summarizing_panel)
        or 'data-panel="spec-transcribing" data-action="retry-transcription"'
        not in re.sub(r"\s+", " ", transcription_failed_panel)
        or 'data-panel="spec-summarizing" data-action="retry-summary"'
        not in re.sub(r"\s+", " ", summary_failed_panel)
    ):
        raise SystemExit(
            "post-meeting processing or its artifact-specific retry path drifted"
        )
    note_ready_panel = encounter_panel("spec-note-ready")
    if 'data-panel="spec-correction"' not in note_ready_panel:
        raise SystemExit("ready-note flow has no primary route to withheld-turn correction")

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
        "manual-start", "manual-stop", "finish-transcription", "finish-processing",
        "open-real-data-detail", "retry-transcription", "retry-summary",
    }
    if expected_actions - actions:
        raise SystemExit("encounter no longer exposes the reviewed transition actions")
    for recovery_hook in (
        "button[data-recovery-start]",
        "button[data-recovery-event]",
        "button[data-recovery-reset]",
    ):
        if (
            f"document.querySelectorAll('{recovery_hook}')" not in page_html
            or "addEventListener('click'" not in page_html
        ):
            raise SystemExit(f"startup recovery click hook missing for {recovery_hook}")
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


def render_encounter_review(
    capture_dir: Path,
    content_path: Path,
    approval_path: Path,
    node: Path,
) -> tuple[str, dict[str, int]]:
    """Render one approved real-content encounter without accepting a model note."""
    check_capture_warning_renderer()
    check_note_admission_renderers()
    content, _approval, transcript = load_encounter_review(
        capture_dir,
        content_path,
        approval_path,
    )
    totals = dict.fromkeys(STATES, 0)
    totals["located"] = len(content["items"])
    section = encounter_meeting_section(content, transcript)
    library = encounter_library_row(content, transcript)
    if (
        "human-curated real content" not in section
        or "product evidence false" not in section
        or "Automatic extraction and application runtime were not tested" not in section
        or "Generated by a real model run" in section
    ):
        raise SystemExit("encounter content lost its visible non-product boundary")
    rendered = page(
        section,
        library,
        totals,
        tokens(),
        1,
        0,
        0,
        encounter_review=True,
    )
    buttons = check_wiring(rendered)
    if buttons != sum(len(item["evidence"]) for item in content["items"]):
        raise SystemExit("encounter evidence locator count drifted during rendering")
    encounter_controls = check_encounter_wiring(rendered)
    enrollment_assertions = check_enrollment_js(rendered, node)
    startup_assertions = check_startup_recovery_js(rendered, node)
    capture_dom_assertions = check_capture_dom_js(rendered, node)
    summary = {
        "meetings": 1,
        "accepted": 0,
        "rejected": 0,
        "claims": len(content["items"]),
        "locators": buttons,
        "encounter_controls": encounter_controls,
        "enrollment_assertions": enrollment_assertions,
        "startup_assertions": startup_assertions,
        "capture_dom_assertions": capture_dom_assertions,
        "encounter_review": True,
        **{f"state_{state}": count for state, count in totals.items()},
    }
    return rendered, summary


def render_note_directory(
    notes_dir: Path,
    node: Path,
    *,
    allow_fixture: bool = False,
) -> tuple[str, dict[str, int]]:
    """Render and mechanically exercise one directory of retained note pairs."""
    check_capture_warning_renderer()
    check_note_admission_renderers()
    if notes_dir.is_symlink():
        raise SystemExit(f"--notes-dir may not be a symlink: {notes_dir}")
    try:
        source_dir = notes_dir.resolve(strict=True)
    except OSError as exc:
        raise SystemExit(f"cannot resolve --notes-dir {notes_dir}: {exc}") from exc
    if not source_dir.is_dir():
        raise SystemExit(f"--notes-dir is not a directory: {source_dir}")
    notes = sorted(source_dir.glob("*.note.json"))
    if not notes:
        raise SystemExit(
            f"no note artifacts in {source_dir}.\n"
            "Generate at least one first, for example:\n"
            "  python3 notes/summarize.py notes/corpus/ES2004c.json --strip "
            "--out notes/out/ES2004c.md"
        )

    tok = tokens()
    sections, library, totals = [], [], dict.fromkeys(STATES, 0)
    accepted = rejected = 0
    for path in notes:
        doc = json.loads(path.read_text(encoding="utf-8"))
        if "prototype_fixture" in doc and not allow_fixture:
            raise SystemExit(
                f"{path}: a prototype mechanical fixture is not product evidence "
                "and cannot enter a normal review build"
            )
        if allow_fixture and doc.get("prototype_fixture") != FIXTURE_MARKER:
            raise SystemExit(
                f"{path}: internal fixture rendering requires the exact "
                "non-product fixture marker"
            )
        if doc.get("schema") not in NOTE_SCHEMAS:
            raise SystemExit(
                f"{path}: expected one of {sorted(NOTE_SCHEMAS)}, "
                f"got {doc.get('schema')!r}")
        transcript = transcript_for(doc, path)
        fixture_view = (
            transcript_view_sha256(transcript)
            == FIXTURE_TRANSCRIPT_VIEW_SHA256
        )
        if fixture_view and not allow_fixture:
            raise SystemExit(
                f"{path}: the registered synthetic fixture transcript is not "
                "product evidence and cannot enter a normal review build"
            )
        if allow_fixture and not fixture_view:
            raise SystemExit(
                f"{path}: internal fixture rendering requires the exact registered "
                "synthetic transcript"
            )
        try:
            capture_doc = reconcile_capture_provenance(
                doc,
                transcript,
                where=str(path),
                allow_absent_legacy=True,
            )
            validate_artifact_pair(capture_doc, path, transcript)
        except ValueError as e:
            raise SystemExit(f"{path}: note pair refused: {e}") from e
        if doc["passed"] is True:
            section, c = meeting_section(doc, path, transcript, capture_doc)
            library_row_html = library_row(doc, capture_doc)
            accepted += 1
        else:
            section = failed_meeting_section(doc, path, transcript, capture_doc)
            c = dict.fromkeys(STATES, 0)
            library_row_html = failed_library_row(doc, capture_doc)
            rejected += 1
        sections.append(section)
        library.append(library_row_html)
        for k, v in c.items():
            totals[k] += v

    rendered = page(
        "".join(sections),
        "".join(library),
        totals,
        tok,
        len(notes),
        accepted,
        rejected,
    )
    buttons = check_wiring(rendered)
    encounter_controls = check_encounter_wiring(rendered)
    enrollment_assertions = check_enrollment_js(rendered, node)
    startup_assertions = check_startup_recovery_js(rendered, node)
    capture_dom_assertions = check_capture_dom_js(rendered, node)
    summary = {
        "meetings": len(notes),
        "accepted": accepted,
        "rejected": rejected,
        "claims": sum(totals.values()),
        "locators": buttons,
        "encounter_controls": encounter_controls,
        "enrollment_assertions": enrollment_assertions,
        "startup_assertions": startup_assertions,
        "capture_dom_assertions": capture_dom_assertions,
        **{f"state_{state}": count for state, count in totals.items()},
    }
    return rendered, summary


def _write_synthetic_control(path: Path, payload: str) -> None:
    """Write one owner-private self-test input without creating product evidence."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.fchmod(fd, 0o600)
        handle = os.fdopen(fd, "w", encoding="utf-8", newline="\n")
        fd = -1
        with handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        _fsync_directory(path.parent)
    finally:
        if fd >= 0:
            os.close(fd)


def materialize_synthetic_note2_control(
    directory: Path,
) -> tuple[Path, Path, Path]:
    """Materialize the tracked, independently serialized non-product fixture."""
    try:
        pack = json.loads(FIXTURE_PACK.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"cannot load synthetic fixture pack {FIXTURE_PACK}: {exc}") from exc
    expected_keys = {
        "schema",
        "product_evidence",
        "transcript_filename",
        "note_filename",
        "markdown_filename",
        "transcript",
        "note",
        "markdown",
    }
    if not isinstance(pack, dict) or set(pack) != expected_keys:
        raise SystemExit("synthetic fixture pack has the wrong wrapper shape")
    if (
        pack["schema"] != "prototype-fixture-pack/1"
        or pack["product_evidence"] is not False
        or not isinstance(pack["transcript"], dict)
        or not isinstance(pack["note"], dict)
        or not isinstance(pack["markdown"], str)
    ):
        raise SystemExit("synthetic fixture pack does not declare non-product data")

    filenames = {
        "transcript": pack["transcript_filename"],
        "note": pack["note_filename"],
        "markdown": pack["markdown_filename"],
    }
    expected_names = {
        "transcript": "synthetic-control-not-product-evidence.json",
        "note": "synthetic-control-not-product-evidence.note.json",
        "markdown": "synthetic-control-not-product-evidence.md",
    }
    if filenames != expected_names:
        raise SystemExit("synthetic fixture pack filenames drifted")
    if any(
        not isinstance(name, str)
        or not name
        or Path(name).name != name
        or "/" in name
        or "\\" in name
        for name in filenames.values()
    ):
        raise SystemExit("synthetic fixture pack contains an unsafe filename")

    note = pack["note"]
    if note.get("prototype_fixture") != FIXTURE_MARKER:
        raise SystemExit("synthetic note/2 fixture is missing its non-product marker")
    if (
        note.get("schema") != "note/2"
        or note.get("passed") is not True
        or note.get("transcript") != filenames["transcript"]
        or note.get("render", {}).get("path") != filenames["markdown"]
    ):
        raise SystemExit("synthetic note/2 fixture no longer binds its serialized pair")
    if (
        note.get("evidence", {}).get("transcript_view_sha256")
        != FIXTURE_TRANSCRIPT_VIEW_SHA256
    ):
        raise SystemExit(
            "synthetic note/2 fixture transcript digest drifted from its "
            "registered non-product identity"
        )

    transcript_path = directory / filenames["transcript"]
    note_path = directory / filenames["note"]
    markdown_path = directory / filenames["markdown"]
    _write_synthetic_control(
        transcript_path,
        json.dumps(pack["transcript"], ensure_ascii=False, indent=2) + "\n",
    )
    _write_synthetic_control(
        note_path,
        json.dumps(note, ensure_ascii=False, indent=2) + "\n",
    )
    _write_synthetic_control(markdown_path, pack["markdown"])
    return transcript_path, note_path, markdown_path


def _expect_refusal(callback: Callable[[], object], phrase: str) -> None:
    try:
        callback()
    except SystemExit as exc:
        if phrase not in str(exc):
            raise SystemExit(
                f"self-test expected refusal containing {phrase!r}, got {exc!s}"
            ) from exc
        return
    raise SystemExit(f"self-test expected refusal containing {phrase!r}")


def materialize_synthetic_encounter_control(
    root: Path,
) -> tuple[Path, Path, Path]:
    """Create a private, explicitly non-product encounter fixture for controls."""
    capture = root / "encounter-capture"
    capture.mkdir(mode=0o700)
    samples = 48_000
    for leg in ("mic", "system"):
        with (
            open_private_binary(capture / f"{leg}.wav") as handle,
            wave.open(handle, "wb") as wav,
        ):
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(16_000)
            wav.writeframes(b"\x01\0" * samples)
    health = build_capture_health(
        mic_samples=samples,
        system_samples=samples,
        capture_elapsed_samples=samples,
        dropouts={"mic": [], "system": []},
        tap_errors=[],
        transcription_requested=True,
        transcript_written=True,
    )
    turns = [
        {
            "speaker": "Me",
            "start": 0.0,
            "end": 0.8,
            "text": "We will review the fixture tomorrow morning.",
        },
        {
            "speaker": "Them",
            "start": 1.0,
            "end": 1.8,
            "text": "Please send the approved summary after review.",
        },
        {
            "speaker": "Me",
            "start": 2.0,
            "end": 2.8,
            "text": "Which retention period should remain available?",
        },
    ]
    transcript = {
        "schema": "capture-transcript/1",
        "source": "synthetic encounter control",
        "attribution": "channel",
        "bleed": None,
        "voiceprint": None,
        "capture_health": health,
        "turns": turns,
    }
    write_private_text(
        capture / "transcript.json",
        json.dumps(transcript, ensure_ascii=False, indent=2) + "\n",
    )
    for leg in ("mic", "system"):
        write_private_text(
            capture / f"{leg}-segments.json",
            json.dumps(
                {
                    "schema": "mic-segments/1",
                    "timeline": f"{leg}-local",
                    "leg": leg,
                    "duration_s": samples / 16_000,
                    "filtered": ["voicing"],
                    "labels": None,
                    "audio_sha256": sha256(capture / f"{leg}.wav"),
                    "audio_samples": samples,
                    "captured_at": "2000-01-01T00:00:00+0000",
                    "segments": [],
                },
                indent=2,
            )
            + "\n",
        )
    started_at = "2000-01-01T00:00:00+0000"
    finalize_session(capture, started_at, health)

    review = root / "encounter-review"
    review.mkdir(mode=0o700)
    capture_id = "synthetic-encounter-control"
    content = {
        "schema": "encounter-review-content/1",
        "origin": "review-draft",
        "product_evidence": False,
        "runtime_validation": "not_run",
        "source": {
            "capture_id": capture_id,
            "capture_mode": "headphones",
            "transcript_file": "transcript.json",
            "transcript_sha256": _sha256_file(capture / "transcript.json"),
            "session_file": "session.json",
            "session_sha256": _sha256_file(capture / "session.json"),
        },
        "meeting": {
            "id": capture_id,
            "title": "Synthetic encounter control",
            "captured_at": started_at,
        },
        "items": [
            {
                "type": "decision",
                "claim": "The fixture review is scheduled for tomorrow morning.",
                "evidence": [{"turn": 0, "quote": turns[0]["text"]}],
            },
            {
                "type": "action",
                "claim": "Send the approved summary after review.",
                "evidence": [{"turn": 1, "quote": turns[1]["text"]}],
            },
            {
                "type": "open_question",
                "claim": "The retention period remains open.",
                "evidence": [{"turn": 2, "quote": turns[2]["text"]}],
            },
        ],
    }
    content_path = review / "review-content.json"
    _write_synthetic_control(
        content_path,
        json.dumps(content, ensure_ascii=False, indent=2) + "\n",
    )
    approval_path = review / "content-approval.json"
    _write_synthetic_control(
        approval_path,
        json.dumps(
            {
                "schema": "encounter-content-approval/1",
                "review_content_sha256": _sha256_file(content_path),
                "participant_consent_before_capture": "confirmed",
                "curation": "accept",
                "reviewer": "synthetic control",
                "decided_at": "2000-01-01T00:00:00+0000",
            },
            indent=2,
        )
        + "\n",
    )
    return capture, content_path, approval_path


def self_test(node: Path) -> int:
    """Exercise private publication and a serialized accepted note/2 route."""
    checks = 0
    with tempfile.TemporaryDirectory(prefix="prototype-builder-self-test-") as tmp:
        root = Path(tmp)
        os.chmod(root, 0o700)

        umask_target = root / "umask.html"
        old_umask = os.umask(0)
        try:
            _published, umask_digest = publish_private_html(
                umask_target, "owner private\n"
            )
        finally:
            os.umask(old_umask)
        if (
            stat.S_IMODE(umask_target.stat().st_mode) != 0o600
            or umask_target.read_text(encoding="utf-8") != "owner private\n"
            or umask_digest
            != hashlib.sha256(b"owner private\n").hexdigest()
        ):
            raise SystemExit(
                "self-test: umask 000 did not yield exact private bytes and digest"
            )
        checks += 1

        _expect_refusal(
            lambda: publish_private_html(umask_target, "replacement"),
            "already exists",
        )
        if umask_target.read_text(encoding="utf-8") != "owner private\n":
            raise SystemExit("self-test: existing prototype was overwritten")
        checks += 1

        directory_target = root / "directory.html"
        directory_target.mkdir(mode=0o700)
        _expect_refusal(
            lambda: publish_private_html(directory_target, "replacement"),
            "already exists",
        )
        if not directory_target.is_dir():
            raise SystemExit("self-test: directory target was changed")
        checks += 1

        victim = root / "victim.html"
        publish_private_html(victim, "victim\n")
        symlink_target = root / "symlink.html"
        symlink_target.symlink_to(victim.name)
        _expect_refusal(
            lambda: publish_private_html(symlink_target, "replacement"),
            "already exists",
        )
        if victim.read_text(encoding="utf-8") != "victim\n":
            raise SystemExit("self-test: symlink refusal changed its victim")
        checks += 1

        raced = root / "raced.html"

        def create_racing_target() -> None:
            _write_synthetic_control(raced, "competing bytes\n")

        _expect_refusal(
            lambda: publish_private_html(
                raced,
                "must lose the race",
                before_publish=create_racing_target,
            ),
            "appeared during the build",
        )
        if raced.read_text(encoding="utf-8") != "competing bytes\n":
            raise SystemExit("self-test: racing target did not win unchanged")
        if list(root.glob(".raced.html.*.partial")):
            raise SystemExit("self-test: target race left a temporary file")
        checks += 1

        interrupted = root / "interrupted.html"

        def inject_interruption() -> None:
            raise RuntimeError("injected before publication")

        try:
            publish_private_html(
                interrupted,
                "must not publish",
                before_publish=inject_interruption,
            )
        except RuntimeError as exc:
            if str(exc) != "injected before publication":
                raise
        else:
            raise SystemExit("self-test: injected publication interruption was ignored")
        if os.path.lexists(interrupted) or list(root.glob(".interrupted.html.*.partial")):
            raise SystemExit("self-test: interrupted publication left output or temp bytes")
        checks += 1

        late_failure = root / "late-failure.html"
        sync_calls = 0

        def fail_second_directory_sync(path: Path) -> None:
            nonlocal sync_calls
            sync_calls += 1
            if sync_calls == 2:
                raise OSError("injected cleanup durability failure")
            _fsync_directory(path)

        try:
            publish_private_html(
                late_failure,
                "must roll back\n",
                sync_directory=fail_second_directory_sync,
            )
        except OSError as exc:
            if str(exc) != "injected cleanup durability failure":
                raise
        else:
            raise SystemExit("self-test: late publication failure was ignored")
        if (
            os.path.lexists(late_failure)
            or list(root.glob(".late-failure.html.*.partial"))
        ):
            raise SystemExit(
                "self-test: late durability failure left output or temporary bytes"
            )
        checks += 1

        mutated_target = root / "mutated-after-link.html"
        mutation_sync_calls = 0

        def mutate_after_second_directory_sync(path: Path) -> None:
            nonlocal mutation_sync_calls
            mutation_sync_calls += 1
            _fsync_directory(path)
            if mutation_sync_calls == 2:
                mutated_target.write_text("changed after link\n", encoding="utf-8")

        _expect_refusal(
            lambda: publish_private_html(
                mutated_target,
                "original bytes\n",
                sync_directory=mutate_after_second_directory_sync,
            ),
            "bytes changed during publication",
        )
        if (
            os.path.lexists(mutated_target)
            or list(root.glob(".mutated-after-link.html.*.partial"))
        ):
            raise SystemExit(
                "self-test: post-link guard failure left output or temporary bytes"
            )
        checks += 1

        insecure = root / "insecure"
        insecure.mkdir(mode=0o700)
        os.chmod(insecure, 0o755)
        _expect_refusal(
            lambda: private_output_target(insecure / "prototype.html"),
            "mode 0700",
        )
        checks += 1

        real_parent = root / "real-parent"
        real_parent.mkdir(mode=0o700)
        linked_parent = root / "linked-parent"
        linked_parent.symlink_to(real_parent.name, target_is_directory=True)
        _expect_refusal(
            lambda: private_output_target(linked_parent / "prototype.html"),
            "parent may not be a symlink",
        )
        checks += 1

        with tempfile.TemporaryDirectory(
            prefix=".prototype-private-self-test-",
            dir=REPO,
        ) as inside:
            inside_git = Path(inside)
            os.chmod(inside_git, 0o700)
            _expect_refusal(
                lambda: private_output_target(inside_git / "prototype.html"),
                "outside every Git repository",
            )
        checks += 1

        _expect_refusal(lambda: resolve_node(None), "Node is required")
        _expect_refusal(
            lambda: resolve_node(Path("node")),
            "--node must be an absolute",
        )
        non_executable = root / "not-node"
        _write_synthetic_control(non_executable, "not executable\n")
        _expect_refusal(
            lambda: resolve_node(non_executable),
            "not an executable file",
        )
        checks += 1

        original_environment = {
            key: os.environ.get(key)
            for key in ("PATH", "NODE_OPTIONS", "NODE_PATH")
        }
        try:
            os.environ["PATH"] = str(root)
            os.environ["NODE_OPTIONS"] = "--require /definitely/missing.js"
            os.environ["NODE_PATH"] = "/definitely/missing"
            if run_node(
                node,
                "process.stdout.write('pinned')",
                "hostile-environment Node control",
            ) != "pinned":
                raise SystemExit("self-test: hostile environment changed Node execution")
        finally:
            for key, prior in original_environment.items():
                if prior is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = prior
        checks += 1

        fixture_dir = root / "serialized-note2"
        fixture_dir.mkdir(mode=0o700)
        materialize_synthetic_note2_control(fixture_dir)
        _expect_refusal(
            lambda: render_note_directory(fixture_dir, node),
            "not product evidence",
        )
        if os.path.lexists(fixture_dir / "prototype.html"):
            raise SystemExit("self-test: normal fixture refusal published HTML")
        checks += 1

        stripped_fixture_dir = root / "stripped-serialized-note2"
        stripped_fixture_dir.mkdir(mode=0o700)
        _transcript_path, stripped_note_path, _markdown_path = (
            materialize_synthetic_note2_control(stripped_fixture_dir)
        )
        stripped_note = json.loads(
            stripped_note_path.read_text(encoding="utf-8")
        )
        stripped_note.pop("prototype_fixture")
        stripped_note_path.unlink()
        _write_synthetic_control(
            stripped_note_path,
            json.dumps(stripped_note, ensure_ascii=False, indent=2) + "\n",
        )
        _expect_refusal(
            lambda: render_note_directory(stripped_fixture_dir, node),
            "registered synthetic fixture transcript",
        )
        checks += 1

        rendered, summary = render_note_directory(
            fixture_dir,
            node,
            allow_fixture=True,
        )
        if (
            summary["meetings"] != 1
            or summary["accepted"] != 1
            or summary["rejected"] != 0
            or summary["claims"] != 1
            or summary["locators"] != 2
            or "synthetic-control-not-product-evidence" not in rendered
        ):
            raise SystemExit(
                "self-test: serialized synthetic note/2 did not reach the accepted "
                "detail and locator path"
            )
        synthetic_page = fixture_dir / "prototype.html"
        _page, page_digest = publish_private_html(synthetic_page, rendered)
        if (
            stat.S_IMODE(synthetic_page.stat().st_mode) != 0o600
            or page_digest
            != hashlib.sha256(synthetic_page.read_bytes()).hexdigest()
        ):
            raise SystemExit("self-test: synthetic rendered page is not mode 0600")
        checks += 1

        encounter_capture, encounter_content, encounter_approval = (
            materialize_synthetic_encounter_control(root)
        )
        encounter_page, encounter_summary = render_encounter_review(
            encounter_capture,
            encounter_content,
            encounter_approval,
            node,
        )
        if (
            encounter_summary["claims"] != 3
            or encounter_summary["locators"] != 3
            or encounter_summary.get("encounter_review") is not True
            or "human-curated real content" not in encounter_page
            or "product evidence false" not in encounter_page
            or "automatic extraction and application runtime were not tested"
            not in encounter_page.lower()
        ):
            raise SystemExit(
                "self-test: approved encounter content lost its visible authority boundary"
            )
        encounter_target = root / "encounter-prototype.html"
        _encounter_path, encounter_digest = publish_private_html(
            encounter_target,
            encounter_page,
        )
        if (
            stat.S_IMODE(encounter_target.stat().st_mode) != 0o600
            or encounter_digest
            != hashlib.sha256(encounter_target.read_bytes()).hexdigest()
        ):
            raise SystemExit("self-test: encounter page is not exact owner-private output")
        checks += 1

        approval_doc = json.loads(encounter_approval.read_text(encoding="utf-8"))
        mismatched_approval = encounter_approval.parent / "mismatched-approval.json"
        _write_synthetic_control(
            mismatched_approval,
            json.dumps(
                {**approval_doc, "review_content_sha256": "0" * 64},
                indent=2,
            )
            + "\n",
        )
        _expect_refusal(
            lambda: load_encounter_review(
                encounter_capture,
                encounter_content,
                mismatched_approval,
            ),
            "does not bind",
        )
        checks += 1

        declined_approval = encounter_approval.parent / "declined-approval.json"
        _write_synthetic_control(
            declined_approval,
            json.dumps({**approval_doc, "curation": "decline"}, indent=2) + "\n",
        )
        _expect_refusal(
            lambda: load_encounter_review(
                encounter_capture,
                encounter_content,
                declined_approval,
            ),
            "not accepted",
        )
        checks += 1

        content_doc = json.loads(encounter_content.read_text(encoding="utf-8"))
        bad_content_doc = json.loads(json.dumps(content_doc))
        bad_content_doc["items"][0]["evidence"][0]["quote"] = (
            "words that do not occur in the retained turn"
        )
        bad_content = encounter_content.parent / "bad-content.json"
        _write_synthetic_control(
            bad_content,
            json.dumps(bad_content_doc, indent=2) + "\n",
        )
        bad_approval = encounter_content.parent / "bad-content-approval.json"
        _write_synthetic_control(
            bad_approval,
            json.dumps(
                {
                    **approval_doc,
                    "review_content_sha256": _sha256_file(bad_content),
                },
                indent=2,
            )
            + "\n",
        )
        _expect_refusal(
            lambda: load_encounter_review(
                encounter_capture,
                bad_content,
                bad_approval,
            ),
            "does not resolve exactly",
        )
        checks += 1

        linked_content = encounter_content.parent / "linked-content.json"
        linked_content.symlink_to(encounter_content.name)
        _expect_refusal(
            lambda: load_encounter_review(
                encounter_capture,
                linked_content,
                encounter_approval,
            ),
            "regular file",
        )
        checks += 1

    print(
        f"prototype builder self-test: pass ({checks} private/publication and "
        "serialized note/2 and encounter controls; synthetic content is not "
        "product evidence)"
    )
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build an owner-private local click-through from retained notes."
    )
    parser.add_argument(
        "--notes-dir",
        type=Path,
        help="directory containing retained *.note.json pairs",
    )
    parser.add_argument(
        "--capture-dir",
        type=Path,
        help="verified private capture directory for interaction-review mode",
    )
    parser.add_argument(
        "--encounter-content",
        type=Path,
        help="approved encounter-review-content/1 JSON outside Git",
    )
    parser.add_argument(
        "--content-approval",
        type=Path,
        help="digest-bound encounter-content-approval/1 JSON outside Git",
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="fresh absolute .html path in an existing external 0700 directory",
    )
    parser.add_argument(
        "--node",
        type=Path,
        required=True,
        help="absolute Node executable used for every JavaScript control",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run synthetic publication and renderer controls; write no retained output",
    )
    args = parser.parse_args(argv)
    encounter_values = (
        args.capture_dir,
        args.encounter_content,
        args.content_approval,
    )
    if args.self_test:
        if args.notes_dir is not None or args.out is not None or any(encounter_values):
            parser.error("--self-test does not accept content or output inputs")
    elif args.out is None:
        parser.error("--out is required")
    elif args.notes_dir is not None and any(encounter_values):
        parser.error("--notes-dir and interaction-review inputs are mutually exclusive")
    elif any(encounter_values) and not all(encounter_values):
        parser.error(
            "interaction review requires --capture-dir, --encounter-content, "
            "and --content-approval"
        )
    elif args.notes_dir is None and not all(encounter_values):
        parser.error("use --notes-dir or all three interaction-review inputs")
    return args


def print_build_summary(
    page_path: Path,
    page_digest: str,
    summary: dict[str, int],
    node: Path,
    node_version: str,
) -> None:
    size = page_path.stat().st_size / 1024
    noun = "meeting" if summary["meetings"] == 1 else "meetings"
    if summary.get("encounter_review"):
        description = (
            f"{summary['meetings']} {noun}, {summary['claims']} operator-confirmed "
            f"review items, automatic extraction and runtime not tested"
        )
    else:
        description = (
            f"{summary['meetings']} {noun}, {summary['accepted']} accepted, "
            f"{summary['rejected']} summary withheld, {summary['claims']} claims"
        )
    print(
        f"wrote {page_path}  ({size:.0f} KB, {description}, "
        f"{summary['locators']} locators all resolving, "
        f"{summary['encounter_controls']} encounter controls wired, "
        f"{summary['enrollment_assertions']} enrollment transitions checked, "
        f"{summary['startup_assertions']} startup recovery transitions checked, "
        f"{summary['capture_dom_assertions']} capture DOM assertions checked)"
    )
    for state in STATES:
        print(f"  {summary[f'state_{state}']:>4}  {state}")
    print(f"  sha256  {page_digest}")
    print(
        "  runtime  "
        f"Python {Path(sys.executable).resolve()} {sys.version.split()[0]}; "
        f"Node {node} {node_version}"
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.self_test:
        node, _node_version = resolve_node(args.node)
        return self_test(node)

    # Validate the private destination before reading note content or running the
    # JavaScript controls. A bad output path must not spend the expensive work first.
    private_output_target(args.out)
    node, node_version = resolve_node(args.node)
    if args.encounter_content is not None:
        rendered, summary = render_encounter_review(
            args.capture_dir,
            args.encounter_content,
            args.content_approval,
            node,
        )
    else:
        rendered, summary = render_note_directory(args.notes_dir, node)
    page_path, page_digest = publish_private_html(args.out, rendered)
    print_build_summary(page_path, page_digest, summary, node, node_version)
    return 0


if __name__ == "__main__":
    sys.exit(main())

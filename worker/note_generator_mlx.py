#!/usr/bin/env python3
"""The product note generator: evidence selection plus note synthesis in one session.

This is the child `worker/note_bridge.py` spawns on the `generate` role. It
speaks the bridge's session protocol — one JSON request line in on stdin, one
JSON response line out on stdout, until stdin closes — and it implements the
registered `mlx-constrained-verdict/1` transport from
`candidate_first.PRODUCT_RUN`.

The first stage restricts the model to one greedy KEEP-or-ABSTAIN choice per
candidate locator. The second stage asks the same local model for overview and
outcome prose from only those retained excerpts. That prose remains untrusted:
the pinned validator resolves its evidence aliases, rejects unsupported
decision/action labels, and refuses a note without an evidence-linked overview.

SYNC OBLIGATION. `notes/product_run.py` is the reference implementation, and
these semantics must stay identical to it, function for function:

  * `MLXVerdictTransport.decide` — gemma3-two-turn/1 rendering (system as its
    own user turn, BOS prepended exactly once and never by the tokenizer),
    chunked prefill at 2048 tokens through one `make_prompt_cache`, one greedy
    first-token comparison of KEEP vs ABSTAIN per locator with the response
    skeleton forced into the cache between choices, temperature zero.
  * `_assemble_contract_response` — the exact response bytes built from the
    locators and the verdicts.

The duplication is deliberate. This child runs under the bridge's generator
flags with site-packages on the path and *nothing else*: it may import
`mlx_lm`, `mlx.core`, and the standard library, and it may not import from
`notes/`, because the bridge's confined import path does not carry those
modules and the research lane must not become a runtime dependency of the
product. Changing the decode in either file without changing the other is a
silent divergence between the measured configuration and the shipped one — the
two blocks below are ~40 lines and must be diffed together.

Failure posture, matched to the bridge's taxonomy. A problem with one request
(no locators offered, a model directory that is not there, a decode that
raises) writes one JSON error line and exits nonzero. The bridge reads the
*line*, not the exit code: an error line is not a classifier response, so
`decode_classification` refuses it and the run becomes `transcript-only`
with `response-contract`. A problem before any line can be produced (mlx_lm
missing, stdin unreadable) exits nonzero with no line, which the bridge sees
as a closed pipe — `provider-generation-failure`. Nothing here ever guesses a
verdict, and nothing here writes to the user's storage.
"""

import json
import os
import sys


class _Refused(Exception):
    """One request could not be answered; the bridge is told, not guessed at."""


def _offered_locators(request):
    """Read the closed locator set out of the request's own response format.

    The bridge builds this schema from the candidates it enumerated locally, so
    it is the one authoritative statement of what this child is allowed to
    answer about. Absent or malformed means the request is not a classification
    request, and the answer is a refusal rather than a best guess.
    """
    try:
        enum = (
            request["response_format"]["properties"]["items"]["items"]
            ["properties"]["candidate_id"]["enum"]
        )
    except (KeyError, TypeError, IndexError) as exc:
        raise _Refused("request offers no candidate locators") from exc
    if not isinstance(enum, list) or not enum:
        raise _Refused("request offers no candidate locators")
    if any(not isinstance(value, str) or not value for value in enum):
        raise _Refused("request offers a malformed candidate locator")
    if len(set(enum)) != len(enum):
        raise _Refused("request offers a duplicated candidate locator")
    return list(enum)


def _model_directory(request):
    directory = request.get("model_directory") if isinstance(request, dict) else None
    if not isinstance(directory, str) or not directory:
        raise _Refused("request names no model directory")
    # Checked, not trusted: the bridge verified and opened this tree before the
    # child was spawned, and a directory that has gone missing since is a
    # refusal rather than an mlx_lm traceback the bridge would have to read as
    # a closed pipe.
    if not os.path.isdir(directory):
        raise _Refused("model directory is not present")
    return directory


class _Session:
    """One model, loaded once, serving every request on this stdin."""

    def __init__(self):
        self._directory = None
        self._model = None
        self._tokenizer = None

    def resolve(self, directory):
        if self._directory is None:
            try:
                from mlx_lm import load as mlx_load

                self._model, self._tokenizer = mlx_load(directory)
            except Exception as exc:  # noqa: BLE001 - any load failure is one refusal
                raise _Refused("model could not be loaded") from exc
            self._directory = directory
        elif directory != self._directory:
            # The bridge sends the same verified path on every request. A
            # different one mid-session means the caller's model identity moved
            # under a session that already loaded weights.
            raise _Refused("model directory changed within one session")
        return self._loaded()

    def _loaded(self):
        """The loaded pair. Named to mirror `MLXVerdictTransport._load`.

        The reference implementation loads lazily inside `decide`; here the
        load is a separate step because the session protocol resolves the
        model directory per request before any decoding starts. Same two
        objects, one call earlier.
        """
        if self._model is None:
            raise _Refused("the model was not resolved before decoding")
        return self._model, self._tokenizer

    # --- begin block mirrored from notes/product_run.py MLXVerdictTransport.decide
    def decide(self, system: str, user: str, locators: list[str]) -> list[str]:
        import mlx.core as mx
        from mlx_lm.models.cache import make_prompt_cache

        model, tok = self._loaded()
        keep_first = tok.encode("KEEP", add_special_tokens=False)[0]
        abstain_first = tok.encode("ABSTAIN", add_special_tokens=False)[0]
        if keep_first == abstain_first:
            raise _Refused(
                "verdict options do not diverge at the first token")
        text = (
            "<start_of_turn>user\n" + system + "<end_of_turn>\n"
            + "<start_of_turn>user\n" + user + "<end_of_turn>\n"
            + "<start_of_turn>model\n"
        )
        tokens = [tok.bos_token_id] + tok.encode(text, add_special_tokens=False)
        cache = make_prompt_cache(model)

        def feed(chunk_tokens: list[int], chunk: int = 2048):
            last = None
            for start in range(0, len(chunk_tokens), chunk):
                logits = model(
                    mx.array([chunk_tokens[start:start + chunk]]), cache=cache)
                last = logits[0, -1, :]
                mx.eval(last)
            return last

        last = feed(tokens)
        verdicts = []
        for index, locator in enumerate(locators):
            prefix = ("" if index == 0 else ", ") + \
                '{"candidate_id": ' + json.dumps(locator) + ', "verdict": "'
            last = feed(tok.encode(prefix, add_special_tokens=False))
            verdict = (
                "KEEP" if last[keep_first].item() > last[abstain_first].item()
                else "ABSTAIN"
            )
            verdicts.append(verdict)
            last = feed(tok.encode(verdict + '"}', add_special_tokens=False))
        # The registered batch size is 1, so this runs once per candidate and a
        # real meeting offers up to a few hundred — mlx's allocator caches freed
        # scratch buffers for reuse rather than returning them to the OS, and
        # nothing here ever reuses a cache across calls (each call builds its
        # own above), so without this the cache grows unbounded across the run
        # instead of staying near one batch's peak.
        mx.clear_cache()
        return verdicts
    # --- end block mirrored from notes/product_run.py MLXVerdictTransport.decide

    def synthesize(self, system: str, user: str, max_tokens: int) -> str:
        """Generate one bounded meeting-note proposal from selected excerpts.

        Unlike the registered KEEP/ABSTAIN classifier above, this is prose. The
        child therefore contributes only an untrusted JSON string; the pinned
        validator resolves every selected evidence ID, drops malformed rows,
        and refuses when no usable overview survives.
        """
        from mlx_lm import generate
        from mlx_lm.sample_utils import make_sampler

        model, tok = self._loaded()
        prompt = (
            "<start_of_turn>user\n" + system + "<end_of_turn>\n"
            + "<start_of_turn>user\n" + user + "<end_of_turn>\n"
            + "<start_of_turn>model\n"
        )
        try:
            return generate(
                model,
                tok,
                prompt=prompt,
                max_tokens=max_tokens,
                sampler=make_sampler(temp=0.0),
                verbose=False,
            )
        except Exception as exc:  # noqa: BLE001 - one failed decode is a refusal
            raise _Refused("the meeting-note decode did not complete") from exc


# --- begin block mirrored from notes/product_run.py _assemble_contract_response
def _assemble_contract_response(locators: list[str], verdicts: list[str]) -> str:
    items = ", ".join(
        '{"candidate_id": ' + json.dumps(locator) + ', "verdict": "' + verdict + '"}'
        for locator, verdict in zip(locators, verdicts, strict=True)
    )
    return '{"items": [' + items + "]}"
# --- end block mirrored from notes/product_run.py _assemble_contract_response


def _answer(session, request):
    directory = _model_directory(request)
    system = request.get("system")
    user = request.get("user")
    if not isinstance(system, str) or not isinstance(user, str) or not system or not user:
        raise _Refused("request carries no prompt")
    # The registered transport is temperature zero, and this decoder is greedy
    # by construction. A request asking for anything else is refused rather
    # than answered greedily under a label that says otherwise.
    if request.get("temperature") not in (0, 0.0):
        raise _Refused("request asks for a temperature the transport cannot honour")
    session.resolve(directory)
    if request.get("schema") == "note-synthesis-request/1":
        max_tokens = request.get("num_predict")
        if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or not 256 <= max_tokens <= 4096:
            raise _Refused("meeting-note output bound is invalid")
        content = session.synthesize(system, user, max_tokens)
        return json.dumps({"content": content}, ensure_ascii=False, separators=(",", ":"))
    locators = _offered_locators(request)
    try:
        verdicts = session.decide(system, user, locators)
    except _Refused:
        raise
    except Exception as exc:  # noqa: BLE001 - any decode failure is one refusal
        raise _Refused("the constrained decode did not complete") from exc
    if len(verdicts) != len(locators):
        raise _Refused("the constrained decode did not answer every locator")
    return _assemble_contract_response(locators, verdicts)


def _write(line):
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


def main():
    session = _Session()
    while True:
        line = sys.stdin.readline()
        if not line:
            return 0
        if not line.strip():
            continue
        try:
            request = json.loads(line)
            if not isinstance(request, dict):
                raise _Refused("request is not a JSON object")
            response = _answer(session, request)
        except _Refused as exc:
            # A refusal is a closed statement of what failed, with no candidate
            # text, no prompt, and no transcript bytes in it.
            _write(json.dumps({"error": str(exc)}))
            return 1
        except (ValueError, UnicodeError):
            _write(json.dumps({"error": "request was not readable JSON"}))
            return 1
        _write(response)


if __name__ == "__main__":
    raise SystemExit(main())

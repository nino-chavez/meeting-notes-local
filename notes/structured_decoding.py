"""A structure-only mask for the note response contract.

Registered by `MLX_NOTE_ADMISSION.md` § "Preregistered amendment — 2026-08-05".
It exists to remove one confound and no more: both prior model failures were
response *shape*, so neither said anything about whether the model understood
the transcript. This withholds every token that would leave the contract, and
leaves every value free.

The first version of this file did not hold that line — it completed strings
`json.loads` rejects, a trailing comma in either list, which is the very refusal
class it exists to remove. `test_structured_decoding.py` now walks the whole
accepted language and parses each string rather than testing a list of cases, so
the claim in the paragraph above is checked rather than asserted.

**What it constrains:** JSON syntax, the single root field `items`, the five
item field names in the registered order, and the exact abstention
`{"items":[]}`. Whitespace is tolerated before and after the object, and only
there, because the enforcement boundary `_strict_json` calls `json.loads` on the
raw string and that already parses.

**What it deliberately does not constrain:** the candidate ID, the source
fragment IDs, the citation, the label, and the claim — every one of which the
harness could pin, because it offers the IDs and knows which fragment the
citation must equal. Pinning them would make the protocol's locator gate
impossible to fail, and a gate that cannot fail is not a gate that passed.

MLX-LM ships no grammar decoder (its own `setup.py` carries no such
dependency), but documents the hook this plugs into:
`logits_processors: Optional[List[Callable[[mx.array, mx.array], mx.array]]]`.
A masking library would drag transitive licences and wheel hashes into a probe
whose whole point is to be disposable, so the machine is written here — small,
closed, and exercised against a synthetic vocabulary before any model is
fetched.

**Why a character-level machine rather than a prefix test.** The obvious
implementation asks, for every token in the vocabulary, whether
`emitted + token` is still a viable prefix. That is correct and unusably slow:
151,643 tokens re-walking a growing string on every one of up to 512 steps did
not finish a two-fixture probe in ten minutes. Here the machine advances one
character at a time and its state is a hashable value, so a token only has to be
walked against the *state* — and the allowed set for each state is computed once
and cached. Roughly forty states exist, so the vocabulary is scanned forty times
for the whole run rather than once per generated token.
"""

from __future__ import annotations

# The registered contract, as a skeleton of literals with free-text holes.
# `_decode_response` enforces the same root and the same field order; this
# machine must never be the place either is defined loosely.
ITEM_FIELDS = ("candidate_id", "source_fragment_ids", "citation", "label", "claim")

# A JSON string value may not carry a raw quote, a backslash, or a control
# character. Forbidding all three means the only way out of a free-text hole is
# the closing quote, so an unterminated or illegally escaped string cannot be
# sampled. The cost — a claim cannot contain a quotation mark — is accepted and
# stated rather than discovered.
_FORBIDDEN_IN_FREE_TEXT = frozenset('"\\') | {chr(code) for code in range(0x20)}
_WHITESPACE = frozenset(" \t\r\n")

MAX_ITEMS = 8
MAX_FRAGMENT_IDS = 3

# States. Each is a hashable tuple so it can key the allowed-token cache.
#   ("pre",)                     before the object; whitespace or "{"
#   ("lit", text, index, cont)   inside a fixed literal, resuming at `cont`
#   ("free", cont)               inside a JSON string body, resuming at `cont`
#   ("items", n)                 an item must open here; at n == 0 the list may
#                                instead close, which is the abstention
#   ("field", n, i)              at the start of item n's field i
#   ("ids", n, count)            an ID must open here; `count` already taken
#   ("id_more", n, count)        after an ID: a comma, or close the list
#   ("item_end", n)              after an item's "}": another item, or close
#   ("done",)                    the object is closed; whitespace only
START = ("pre",)


def _literal(text: str, cont: tuple) -> tuple:
    return ("lit", text, 0, cont)


def _field_state(item: int, index: int) -> tuple:
    """Entering item `item`'s field `index`, which begins with its quoted name."""
    if index >= len(ITEM_FIELDS):
        return _literal("}", ("item_end", item))
    name = ITEM_FIELDS[index]
    prefix = f'"{name}":' if index == 0 else f',"{name}":'
    if name == "source_fragment_ids":
        return _literal(prefix + "[", ("ids", item, 0))
    return _literal(prefix + '"', ("free", _field_state(item, index + 1)))


def step(state: tuple, character: str) -> tuple | None:
    """Advance one character, or None if it leaves the contract."""
    kind = state[0]

    if kind == "pre":
        if character in _WHITESPACE:
            return state
        return step(_literal('{"items":[', ("items", 0)), character)

    if kind == "lit":
        _, text, index, cont = state
        if character != text[index]:
            return None
        index += 1
        return cont if index == len(text) else ("lit", text, index, cont)

    if kind == "free":
        _, cont = state
        if character == '"':
            return cont
        if character in _FORBIDDEN_IN_FREE_TEXT:
            return None
        return state

    if kind == "items":
        _, taken = state
        # `]` closes only from the opening position, where it spells the
        # registered abstention `{"items":[]}`. A comma re-enters this state with
        # `taken > 0`, and accepting `]` there would admit `[{…},]` — invalid
        # JSON, and precisely the `response-json-syntax` refusal this mask exists
        # to make unreachable. The legitimate close after an item runs through
        # ("item_end", n).
        if character == "]" and taken == 0:
            return _literal("}", ("done",))
        if character == "{" and taken < MAX_ITEMS:
            # The brace is consumed here, so the item resumes at its first
            # field name rather than at another opening brace.
            return _field_state(taken + 1, 0)
        return None

    if kind == "ids":
        _, item, count = state
        # No `]` at all: this state is the position where an ID *must* appear,
        # whether it is the first or one following a comma. The list closes from
        # ("id_more", …), so both `[]` and `["f1",]` are unreachable.
        if character == '"' and count < MAX_FRAGMENT_IDS:
            return ("free", ("id_more", item, count + 1))
        return None

    if kind == "id_more":
        _, item, count = state
        # Guarded so a comma never leads somewhere with no continuation. At the
        # ceiling, ("ids", item, MAX_FRAGMENT_IDS) can take neither a quote nor
        # — since the branch above — a bracket, and the model would hit
        # `MaskRefused` mid-response having done nothing wrong.
        if character == "," and count < MAX_FRAGMENT_IDS:
            return ("ids", item, count)
        if character == "]":
            return _field_state(item, ITEM_FIELDS.index("source_fragment_ids") + 1)
        return None

    if kind == "item_end":
        _, item = state
        # Same guard, same reason: at MAX_ITEMS the comma would reach an
        # ("items", MAX_ITEMS) that can open no item and can no longer close.
        if character == "," and item < MAX_ITEMS:
            return ("items", item)
        if character == "]":
            return _literal("}", ("done",))
        return None

    if kind == "done":
        return state if character in _WHITESPACE else None

    return None


class MaskRefused(ValueError):
    """The machine cannot express the contract with this vocabulary."""


class ContractMachine:
    """Which continuations of the emitted text can still reach a valid response.

    The response language is small enough to walk directly, and the machine must
    accept exactly this and nothing else — a trailing comma in either list is
    valid here and invalid to `json.loads`, so it is written out rather than
    left implied:

        {"items":[]}
        {"items":[<item>(,<item>){0,7}]}
        <item> = {"candidate_id":"<free>","source_fragment_ids":[<ids>],
                  "citation":"<free>","label":"<free>","claim":"<free>"}
        <ids>  = "<free>"(,"<free>"){0,2}
    """

    def state_after(self, text: str, state: tuple = START) -> tuple | None:
        for character in text:
            state = step(state, character)
            if state is None:
                return None
        return state

    def viable(self, text: str) -> bool:
        return self.state_after(text) is not None

    def complete(self, text: str) -> bool:
        return self.state_after(text) == ("done",)


def allowed_token_ids(
    machine: ContractMachine,
    state: tuple,
    vocabulary: dict[int, str],
    eos_ids: frozenset[int] = frozenset(),
) -> set[int]:
    """Every token that keeps the response reachable from `state`.

    EOS is admitted only once the object is closed, so the model cannot stop
    mid-response and leave the parser a truncated string.
    """
    finished = state == ("done",)
    allowed: set[int] = set()
    # End-of-turn is handled outside the vocabulary scan, not inside it. A
    # tokenizer's `vocab_size` counts the base vocabulary and excludes the added
    # special tokens, so this model's `<|im_end|>` (151645, against a vocab_size
    # of 151643) was absent from the scan entirely. The model then produced a
    # correct response and could not stop: it padded whitespace to the 512-token
    # cap and every call recorded `response-length-truncation`. Deriving the stop
    # token from the same range as the ordinary tokens is what caused that.
    if finished:
        allowed |= set(eos_ids)
    for identifier, text in vocabulary.items():
        if identifier in eos_ids or not text:
            continue
        if machine.state_after(text, state) is not None:
            allowed.add(identifier)
    if not allowed:
        raise MaskRefused(
            "no token continues the contract; the vocabulary cannot express it"
        )
    return allowed


def make_contract_logits_processor(tokenizer, machine: ContractMachine | None = None):
    """The `logits_processors` callable MLX-LM documents, over this contract.

    Signature per MLX-LM: `Callable[[mx.array, mx.array], mx.array]` — the tokens
    generated so far and the current logits, returning modified logits.

    **The first token is not masked.** `mlx_lm==0.30.4` samples once before any
    processor runs; the first call already carries a token. The machine tolerates
    leading whitespace for exactly that reason, and this model opens its turn
    with a newline. If a run ever begins with something else, `MaskRefused` says
    so rather than producing a quietly meaningless result.
    """
    import mlx.core as mx

    machine = machine or ContractMachine()
    eos_ids = _eos_ids(tokenizer)
    if not eos_ids:
        raise MaskRefused("the tokenizer names no end-of-turn token")
    vocabulary = _decoded_vocabulary(tokenizer)
    cache: dict[tuple, "mx.array"] = {}

    def processor(tokens, logits):
        # Stop tokens are dropped before decoding. `decode` renders `<|im_end|>`
        # literally, and the loop calls the processor once more after sampling
        # it, so a completed response would arrive here with a marker appended
        # and be rejected for leaving a contract it had just satisfied. They can
        # only be sampled at `done` — the mask withholds them everywhere else —
        # so dropping them cannot hide a stop in the middle of a response.
        body = [int(value) for value in tokens if int(value) not in eos_ids]
        emitted = tokenizer.decode(body) if body else ""
        state = machine.state_after(emitted)
        if state is None:
            raise MaskRefused(
                "generation left the contract before the mask could act"
            )
        indices = cache.get(state)
        if indices is None:
            indices = mx.array(
                sorted(allowed_token_ids(machine, state, vocabulary, eos_ids))
            )
            cache[state] = indices
        mask = mx.full(logits.shape, -float("inf"))
        # Restore only the surviving columns; every other logit stays at -inf, so
        # the sampler cannot reach a token that leaves the contract.
        mask[..., indices] = logits[..., indices]
        return mask

    return processor


def _eos_ids(tokenizer) -> frozenset[int]:
    """Every id that ends the turn, taken from the tokenizer rather than a range.

    `eos_token_ids` is a set on MLX-LM's wrapper; `eos_token_id` is the single
    id underneath. Both are read because a model may stop on more than one, and
    a stop token that the mask does not know about is a mask that cannot let the
    model finish.
    """
    found: set[int] = set()
    many = getattr(tokenizer, "eos_token_ids", None)
    if isinstance(many, (set, frozenset, list, tuple)):
        found |= {value for value in many if isinstance(value, int)}
    single = getattr(tokenizer, "eos_token_id", None)
    if isinstance(single, int):
        found.add(single)
    return frozenset(found)


def _decoded_vocabulary(tokenizer) -> dict[int, str]:
    """Token id → the text it contributes, taken from the tokenizer itself.

    `convert_ids_to_tokens` returns the internal spelling, which carries byte-BPE
    artifacts; decoding each id individually returns what the string actually
    gains, which is what the machine reasons about.
    """
    size = getattr(tokenizer, "vocab_size", None)
    if not isinstance(size, int):
        vocabulary = tokenizer.get_vocab()
        size = max(vocabulary.values()) + 1
    decoded: dict[int, str] = {}
    for identifier in range(size):
        try:
            decoded[identifier] = tokenizer.decode([identifier])
        except Exception:
            continue
    return decoded

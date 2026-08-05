"""A structure-only mask for the note response contract.

Registered by `MLX_NOTE_ADMISSION.md` § "Preregistered amendment — 2026-08-05".
It exists to remove one confound and no more: both prior model failures were
response *shape*, so neither said anything about whether the model understood
the transcript. This makes shape unreachable and leaves every value free.

**What it constrains:** JSON syntax, the single root field `items`, the five
item field names in the registered order, and the exact abstention
`{"items":[]}`.

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
"""

from __future__ import annotations

from dataclasses import dataclass, field

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


class MaskRefused(ValueError):
    """The machine cannot express the contract with this vocabulary."""


@dataclass
class _State:
    """Where the machine is, expressed as text rather than token indices.

    Deliberately not a token-level state: two tokenizers can spell the same
    literal differently, and a machine that reasons about the *string* is one
    fewer assumption between this file and the model.
    """

    pending: str = ""
    stack: list = field(default_factory=list)


class ContractMachine:
    """Which continuations of the emitted text can still reach a valid response.

    The response language is small enough to walk directly:

        {"items":[]}
        {"items":[<item>(,<item>)*]}
        <item> = {"candidate_id":"<free>","source_fragment_ids":[<free-list>],
                  "citation":"<free>","label":"<free>","claim":"<free>"}

    Every position is either inside a fixed literal, inside a free string, or at
    one of three choice points: first item or abstain, another ID or close the
    list, another item or close the response.
    """

    def __init__(self, max_items: int = 8, max_fragment_ids: int = 3) -> None:
        self.max_items = max_items
        self.max_fragment_ids = max_fragment_ids

    # -- the language, as a prefix test ------------------------------------

    def viable(self, text: str) -> bool:
        """Whether `text` is a prefix of at least one contract-shaped response."""
        return self._walk(text) is not None

    def complete(self, text: str) -> bool:
        state = self._walk(text)
        return state is not None and state == "done"

    def _walk(self, text: str):
        """Consume `text`, returning an opaque position or None if it left the language.

        Written as an explicit cursor rather than a regex because the free-text
        holes are unbounded and a regex over them is where the subtle bugs live.
        """
        index = 0
        items = 0

        def literal(expected: str) -> bool:
            nonlocal index
            take = text[index:index + len(expected)]
            if not expected.startswith(take):
                return False
            index += len(take)
            return True

        def exhausted() -> bool:
            return index >= len(text)

        def free_string() -> bool:
            """A JSON string body up to and including its closing quote."""
            nonlocal index
            while index < len(text):
                character = text[index]
                if character == '"':
                    index += 1
                    return True
                if character in _FORBIDDEN_IN_FREE_TEXT:
                    return False
                index += 1
            return True

        if not literal('{"items":['):
            return None
        if exhausted():
            return "open"

        # Choice point 1: abstain, or open the first item.
        while True:
            if text[index] == "]":
                index += 1
                if not literal("}"):
                    return None
                return "done" if exhausted() else None
            if text[index] != "{":
                return None
            items += 1
            if items > self.max_items:
                return None
            index += 1

            for position, name in enumerate(ITEM_FIELDS):
                if not literal(f'"{name}":'):
                    return None
                if exhausted():
                    return "open"
                if name == "source_fragment_ids":
                    if not literal("["):
                        return None
                    identifiers = 0
                    while True:
                        if exhausted():
                            return "open"
                        if text[index] == "]" and identifiers:
                            index += 1
                            break
                        if text[index] != '"':
                            return None
                        index += 1
                        identifiers += 1
                        if identifiers > self.max_fragment_ids:
                            return None
                        if not free_string():
                            return None
                        if exhausted():
                            return "open"
                        # Choice point 2: another ID, or close the list.
                        if text[index] == ",":
                            index += 1
                            continue
                        if text[index] == "]":
                            index += 1
                            break
                        return None
                else:
                    if not literal('"'):
                        return None
                    if exhausted():
                        return "open"
                    if not free_string():
                        return None
                if exhausted():
                    return "open"
                if position < len(ITEM_FIELDS) - 1:
                    if not literal(","):
                        return None
                    if exhausted():
                        return "open"

            if not literal("}"):
                return None
            if exhausted():
                return "open"
            # Choice point 3: another item, or close the response.
            if text[index] == ",":
                index += 1
                if exhausted():
                    return "open"
                continue
            if text[index] == "]":
                index += 1
                if not literal("}"):
                    return None
                return "done" if exhausted() else None
            return None


def allowed_token_ids(
    machine: ContractMachine,
    emitted: str,
    vocabulary: dict[int, str],
    eos_ids: frozenset[int] = frozenset(),
) -> set[int]:
    """Every token that keeps the response reachable, plus EOS once it is complete.

    Linear in the vocabulary per step, which is the honest cost of not importing
    a compiled grammar. The probe generates at most 512 tokens against two
    fixtures; a product path would need an index, and this is not one.
    """
    allowed: set[int] = set()
    finished = machine.complete(emitted)
    for identifier, text in vocabulary.items():
        if identifier in eos_ids:
            if finished:
                allowed.add(identifier)
            continue
        if not text:
            continue
        if machine.viable(emitted + text):
            allowed.add(identifier)
    if not allowed:
        raise MaskRefused(
            "no token continues the contract; the vocabulary cannot express it"
        )
    return allowed


def make_contract_logits_processor(tokenizer, machine: ContractMachine | None = None):
    """The `logits_processors` callable MLX-LM documents, over this contract.

    Signature per MLX-LM: `Callable[[mx.array, mx.array], mx.array]` — the tokens
    generated so far and the current logits, returning modified logits. The
    prompt is not in `tokens`, so the emitted text is exactly the response.
    """
    import mlx.core as mx

    machine = machine or ContractMachine()
    vocabulary = _decoded_vocabulary(tokenizer)
    eos_ids = frozenset(
        identifier
        for identifier in (getattr(tokenizer, "eos_token_id", None),)
        if isinstance(identifier, int)
    )

    def processor(tokens, logits):
        emitted = tokenizer.decode([int(value) for value in tokens]) if len(tokens) else ""
        allowed = allowed_token_ids(machine, emitted, vocabulary, eos_ids)
        mask = mx.full(logits.shape, -float("inf"))
        indices = mx.array(sorted(allowed))
        # Restore only the surviving columns; every other logit stays at -inf, so
        # the sampler cannot reach a token that leaves the contract.
        mask[..., indices] = logits[..., indices]
        return mask

    return processor


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

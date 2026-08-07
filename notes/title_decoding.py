"""Structure-only mask for the title-selection contract.

The response language is `{"turn":<value>}`, where `<value>` is `null` or one
of the offered turn indices, and nothing else. It is a sibling of
`structured_decoding.py` rather than an extension of it: that machine's shape is
the note contract's, and bending one machine around two contracts would give
neither a language you can read off the class.

What it *does* reuse is that module's `allowed_token_ids` and
`make_contract_logits_processor`, unchanged. Both take the machine as a
parameter and only ever call `state_after` and compare against `("done",)`, so
this class satisfies them by duck typing. That reuse is deliberate and it is the
valuable part: those functions carry four corrections found by running the note
probe — the stop token living above `vocab_size`, stop tokens being decoded into
the walked text, the first token arriving unmasked, and the per-state cache.
Rewriting them here would rediscover all four.

# The whole language, and why that sentence is stronger here

`structured_decoding.py` records a correction: its soundness could only be
enumerated "at a reduced ceiling (one item, two fragment IDs)", and at that
ceiling 288 of 385 accepted strings were invalid JSON. The reduction was forced
by free-text holes, which are infinite.

This contract has no free-text hole. With `n` offered turns the language is
exactly `n + 1` strings, so `test_title_decoding.py` enumerates **all** of them
and `json.loads` every one. The soundness claim here is total rather than
sampled, which is the difference between "no invalid string was found" and
"there is no invalid string".

# What the mask makes impossible rather than merely wrong

A withheld turn is not in the offered set, so no index naming one is in the
language. The model cannot select a withheld turn, as opposed to being checked
afterwards for having done so. `meeting_title::derived_title` skips gated turns
by filtering them; here they are absent from the alphabet.

The model also cannot emit text. Every value is an integer or `null`, so a
selected title is by construction a span of the transcript, and "the model does
not write the title" is a property of the decoder rather than a promise in a
prompt.
"""

from __future__ import annotations

_WHITESPACE = frozenset(" \t\r\n")

# The one literal every response opens with. Written once, here, and consumed by
# both the machine and the test that enumerates the language.
PREFIX = '{"turn":'
SUFFIX = "}"
ABSTENTION_VALUE = "null"

START = ("pre",)


def _literal(text: str, cont: tuple) -> tuple:
    return ("lit", text, 0, cont)


def values_for(offered: tuple[int, ...]) -> tuple[str, ...]:
    """Every value literal this response may carry, abstention first.

    Indices are rendered without padding, and `values_for` is the only place
    that decides how. A response is compared against these strings rather than
    parsed as a number, so `03` and `3` cannot both mean turn three.
    """
    if not offered:
        raise ValueError("a request with no offered turn cannot be answered")
    if len(set(offered)) != len(offered) or any(index < 0 for index in offered):
        raise ValueError("offered turns must be unique and non-negative")
    return (ABSTENTION_VALUE, *(str(index) for index in offered))


class TitleSelectionMachine:
    """Which continuations can still reach a valid response.

        {"turn":null}
        {"turn":<one of the offered indices>}

    No trailing whitespace inside the object, no leading zeros, no alternative
    spelling of the same index. Leading whitespace *before* the object is
    tolerated for one measured reason: `mlx_lm==0.30.4` samples the first token
    before any logits processor runs, and this model opens its turn with a
    newline.
    """

    def __init__(self, offered: tuple[int, ...]):
        self.values = values_for(tuple(offered))

    def step(self, state: tuple, character: str) -> tuple | None:
        kind = state[0]

        if kind == "pre":
            if character in _WHITESPACE:
                return state
            return self.step(_literal(PREFIX, ("val", "")), character)

        if kind == "lit":
            _, text, index, cont = state
            if character != text[index]:
                return None
            index += 1
            return cont if index == len(text) else ("lit", text, index, cont)

        if kind == "val":
            _, prefix = state
            # The close is offered only when the prefix is already a complete
            # value. With both 1 and 12 on offer, "1" is simultaneously a
            # finished answer and an unfinished one, and this is the state that
            # lets it be both without the machine having to guess.
            if character == SUFFIX and prefix in self.values:
                return ("done",)
            extended = prefix + character
            if any(value.startswith(extended) for value in self.values):
                return ("val", extended)
            return None

        if kind == "done":
            return state if character in _WHITESPACE else None

        return None

    def state_after(self, text: str, state: tuple = START) -> tuple | None:
        for character in text:
            state = self.step(state, character)
            if state is None:
                return None
        return state

    def viable(self, text: str) -> bool:
        return self.state_after(text) is not None

    def complete(self, text: str) -> bool:
        return self.state_after(text) == ("done",)

    def language(self) -> tuple[str, ...]:
        """Every string this machine completes. Finite, and short enough to test.

        Built from the same `values` the machine walks, so a test comparing the
        two would be circular — `test_title_decoding.py` therefore checks this
        against a search over the machine's own transitions instead, and checks
        both against `json.loads`.
        """
        return tuple(f"{PREFIX}{value}{SUFFIX}" for value in self.values)

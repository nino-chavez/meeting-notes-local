from __future__ import annotations

import hashlib
import unittest

from transcript import CHANNEL, PromptOverlay, Transcript, Turn


class PromptOverlayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.transcript = Transcript(
            source="overlay fixture",
            attribution=CHANNEL,
            turns=[Turn("Kibbel approved the plan.", speaker="Them")],
            gated_turns=[Turn("Kibbel is withheld.", speaker="Them")],
        )
        source = "Kibbel"
        self.replacement = {
            "turn": 0,
            "char_start": 0,
            "char_end": len(source),
            "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
            # Deliberately longer than the retained source.
            "replacement": "Kibble Labs",
        }

    def test_speaker_then_vocabulary_composition_is_prompt_only(self) -> None:
        overlay = PromptOverlay.from_transport(
            self.transcript,
            [{"source_speaker": "Them", "replacement": "Alex"}],
            [self.replacement],
        )

        self.assertEqual(overlay.speaker(0), "Alex")
        self.assertEqual(overlay.text(0, 0, len(self.transcript.turns[0].text)),
                         "Kibble Labs approved the plan.")
        # The retained source and withheld rows are never rewritten.
        self.assertEqual(self.transcript.turns[0].text, "Kibbel approved the plan.")
        self.assertEqual(self.transcript.gated_turns[0].text, "Kibbel is withheld.")

    def test_no_vocabulary_is_a_no_op_and_stale_or_withheld_ranges_refuse(self) -> None:
        no_op = PromptOverlay.from_transport(self.transcript)
        self.assertEqual(no_op.speaker(0), "Them")
        self.assertEqual(no_op.text(0, 0, len(self.transcript.turns[0].text)),
                         self.transcript.turns[0].text)

        stale = {**self.replacement, "source_sha256": "0" * 64}
        with self.assertRaisesRegex(ValueError, "stale"):
            PromptOverlay.from_transport(self.transcript, vocabulary_replacements=[stale])
        # Only visible turns are indexed. A gated row cannot be named by the
        # transport and therefore cannot reach a prompt.
        withheld = {**self.replacement, "turn": 1}
        with self.assertRaisesRegex(ValueError, "range"):
            PromptOverlay.from_transport(self.transcript, vocabulary_replacements=[withheld])

    def test_overlapping_source_ranges_refuse(self) -> None:
        overlap = {
            "turn": 0,
            "char_start": 1,
            "char_end": 3,
            "source_sha256": hashlib.sha256("ib".encode("utf-8")).hexdigest(),
            "replacement": "IB",
        }
        with self.assertRaisesRegex(ValueError, "range"):
            PromptOverlay.from_transport(
                self.transcript, vocabulary_replacements=[self.replacement, overlap]
            )


if __name__ == "__main__":
    unittest.main()

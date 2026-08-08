//! The unit a vector is computed over: 128 words of non-gated transcript.
//!
//! # Why this shape, and why it is not adjustable
//!
//! `notes/SEMANTIC_RETRIEVAL.md` registered three candidate units and measured
//! them on 2026-08-08 over 200 meetings of realistic length. Whole-meeting
//! embedding collapsed to 1 of 10 once every meeting crossed the model's
//! 256-token ceiling. Per-turn and per-128-word-window tied at 7 of 10, inside
//! the registered margin, and the registered cost tiebreak chose window: 800
//! pieces where turn stored 16,020, bounded per meeting rather than varying
//! with how much people interrupt each other.
//!
//! So [`WINDOW_WORDS`] is 128, windows do not overlap, and both facts are
//! load-bearing rather than tuneable. A stride that overlaps, or a width that
//! does not, produces a store whose retrieval quality nothing has measured —
//! and it would do so silently, because the code would still run.
//! `notes/window_equivalence_fixture.json` freezes the measured harness's own
//! boundaries and `the_measured_windowing_is_reproduced_exactly` holds this
//! module to them.
//!
//! # Three decisions the measurement did not make
//!
//! **Gated turns contribute nothing.** The probe's corpus has no gated turns,
//! so the measurement is silent here and this is a choice. Exact search already
//! reports a gated match as [`crate::library_read::LibraryHit`]'s withheld
//! shape — it can say "the word you typed is in here" without showing the line,
//! because the word is literally there. A semantic hit has no such footing: it
//! would assert that withheld speech is *about* something, citing no resolvable
//! words at all. This repository's first invariant is that evidence is never
//! decoration, and that settles it.
//!
//! One consequence: dropping a gated turn stitches the speech on either side of
//! it into one window. The segments below still cite the true turns and offsets,
//! but a renderer must not present the joined text as contiguous prose.
//!
//! **A meeting with no words produces no windows.** The probe's window arm
//! yields one empty piece for an empty meeting (`or [""]`) so that arm always
//! has something to compare. A store must not hold a vector for nothing, so
//! this yields an empty list instead. That is a deliberate divergence from the
//! frozen harness and the fixture does not cover it; `an_empty_meeting_yields_no_windows`
//! does.
//!
//! **Words are split the way Python splits them.** [`is_word_separator`] is
//! `char::is_whitespace` widened by four control characters, because the
//! measured boundaries came from Python's `str.split()` and Python's
//! `str.isspace()` includes U+001C through U+001F where Rust's `White_Space`
//! does not. Transcript text is not filtered for control characters —
//! `library_read`'s `is_forbidden` guards the search query, not the turn — so
//! the difference is reachable rather than theoretical.
//!
//! # What a window carries
//!
//! Segments, not text. A [`WindowSegment`] is `(source_turn_index,
//! original_scalar_start, original_scalar_end)` — the same vocabulary a
//! transcript search hit already uses, so a semantic hit can be rendered by the
//! machinery that renders an exact one. The text reconstructs through
//! [`window_text`]; storing it would duplicate private material for no gain.

use sha2::{Digest, Sha256};

/// 128 words per window, from the registered measurement. See the module doc
/// before changing it: this is not a tuning parameter.
pub const WINDOW_WORDS: usize = 128;

/// How a meeting's windows combine into one score, fixed by the same run.
///
/// `semantic_scale_probe.py` names it registered rather than chosen per run,
/// "because a per-turn arm winning under max might lose under mean-of-top-k,
/// which is untested". Recorded here so the read side inherits the contract
/// instead of inventing a second one.
pub const AGGREGATION: &str = "max-chunk-similarity";

/// How close another meeting has to be before a person could plausibly have
/// been shown it instead. Registered before the run, not fitted after it.
pub const DENSITY_BAND: f32 = 0.02;

/// Everything that has to match for two vectors to be worth comparing.
///
/// Naming the model is not enough. A reimplementation of the same checkpoint can
/// pool differently, truncate at a different length, or use the tanh gelu
/// approximation, and each of those produces vectors that are the right shape
/// and the wrong direction — a store that compared them would return confident
/// nonsense with nothing to catch it. So the choices `notes/mlx_minilm.py`
/// documents making are part of the identity.
///
/// **`tokenizer_sha256` was missing when this type landed on 2026-08-08**, and
/// it is the field that most needed to be here: text reaches the model as token
/// IDs, so two tokenizers disagreeing changes every vector while every other
/// field still matches. It cost nothing to add because no vector existed yet.
/// The digest, not a name — `bert-wordpiece` does not distinguish two
/// configurations of the same algorithm, and this checkpoint's own
/// `tokenizer.json` carries truncation at 128 and fixed padding to 128 that
/// have to be turned off. A name would call that the same tokenizer.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct EmbedderIdentity {
    pub model: String,
    pub revision: String,
    /// SHA-256 of the `tokenizer.json` the vectors were produced with.
    pub tokenizer_sha256: String,
    /// SHA-256 of `model.safetensors`. `revision` names which weights these are
    /// meant to be; this is the check that they are. Both stay — a label a human
    /// reads and a digest a machine compares are different jobs.
    pub weights_sha256: String,
    /// The mask-weighted mean over the last hidden state. Not `[CLS]`, and not
    /// the checkpoint's `pooler.dense` head, which sentence-transformers does
    /// not use for this model.
    pub pooling: String,
    pub max_sequence_tokens: u32,
    /// `erf-gelu`, the exact formulation. `gelu_new`'s tanh approximation is a
    /// different function and would be a different identity.
    pub activation: String,
    pub dimension: u32,
}

impl EmbedderIdentity {
    /// The reference implementation the measurement ran on:
    /// `notes/mlx_minilm.py` against the pinned weights recorded in
    /// `notes/SEMANTIC_RETRIEVAL.md`.
    ///
    /// Nothing in this crate can produce these vectors — no embedder ships yet.
    /// It exists so the store can refuse anything that is not this.
    pub fn measured() -> Self {
        Self {
            model: "sentence-transformers/all-MiniLM-L6-v2".to_owned(),
            revision: "1110a243fdf4706b3f48f1d95db1a4f5529b4d41".to_owned(),
            // `tokenizer.json` at that revision, digested in-session and
            // recorded in `notes/packaged_tokenizer_receipt.json`.
            tokenizer_sha256: "be50c3628f2bf5bb5e3a7f17b1f74611b2561a3a27eeab05e5aa30f411572037"
                .to_owned(),
            weights_sha256: "53aa51172d142c89d9012cce15ae4d6cc0ca6895895114379cacb4fab128d9db"
                .to_owned(),
            pooling: "mask-weighted-mean".to_owned(),
            max_sequence_tokens: 256,
            activation: "erf-gelu".to_owned(),
            dimension: 384,
        }
    }

    /// The manifest resource IDs this identity is about, and the fields each
    /// one has to equal. `worker/build_manifest.py` writes these IDs.
    pub const TOKENIZER_MODEL_ID: &'static str = "all-minilm-l6-v2-tokenizer";
    pub const WEIGHTS_MODEL_ID: &'static str = "all-minilm-l6-v2-weights";

    /// Is the model this runtime packaged the model these vectors describe?
    ///
    /// **This is the check the identity fields existed to make and did not.**
    /// Until 2026-08-08 `tokenizer_sha256` was a literal in this file and the
    /// manifest recorded the packaged tokenizer's digest, and nothing compared
    /// them — so the field asserted a fact rather than testing one. Two
    /// tokenizers turn the same sentence into different token IDs, and every
    /// other identity field would still have matched.
    ///
    /// Absent resources are a mismatch, not an exemption: a runtime that
    /// packages no embedding model must not be treated as packaging the right
    /// one.
    pub fn matches_manifest(&self, models: &[(&str, &str)]) -> bool {
        let digest = |id: &str| {
            models
                .iter()
                .find(|(name, _)| *name == id)
                .map(|(_, digest)| *digest)
        };
        digest(Self::TOKENIZER_MODEL_ID) == Some(self.tokenizer_sha256.as_str())
            && digest(Self::WEIGHTS_MODEL_ID) == Some(self.weights_sha256.as_str())
    }

    /// One line, field order fixed, for the column a vector is keyed by. Any
    /// difference in any field is a different string and therefore a different
    /// embedder.
    pub fn canonical(&self) -> String {
        format!(
            "{}@{} tokenizer={} weights={} pooling={} max_tokens={} activation={} dim={}",
            self.model,
            self.revision,
            self.tokenizer_sha256,
            self.weights_sha256,
            self.pooling,
            self.max_sequence_tokens,
            self.activation,
            self.dimension
        )
    }
}

/// One contiguous run of words inside a single turn.
///
/// Offsets are Unicode scalar indices into the turn's original text, matching
/// `library_read`'s `original_scalar_start` / `original_scalar_end`.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct WindowSegment {
    pub source_turn_index: u64,
    pub original_scalar_start: u64,
    pub original_scalar_end: u64,
}

/// A window's provenance. Never its text.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CorpusWindow {
    pub window_index: u64,
    pub word_count: u64,
    pub segments: Vec<WindowSegment>,
}

/// Python's `str.isspace()`, which is what the measured harness split on.
///
/// `char::is_whitespace` is the Unicode `White_Space` property. Python adds the
/// four information separators, and `separator_set_matches_python_isspace` pins
/// the whole set rather than this sentence.
pub fn is_word_separator(character: char) -> bool {
    character.is_whitespace() || matches!(character, '\u{1c}'..='\u{1f}')
}

/// Segment one meeting's turns into windows.
///
/// `turns` yields `(turn_index, text, gated)` in transcript order. Gated turns
/// are skipped entirely; see the module doc for why.
pub fn windows<'a, I>(turns: I) -> Vec<CorpusWindow>
where
    I: IntoIterator<Item = (u64, &'a str, bool)>,
{
    let mut finished: Vec<CorpusWindow> = Vec::new();
    let mut segments: Vec<WindowSegment> = Vec::new();
    let mut words = 0_usize;

    for (turn_index, text, gated) in turns {
        if gated {
            continue;
        }
        for (start, end) in word_spans(text) {
            match segments.last_mut() {
                Some(segment) if segment.source_turn_index == turn_index => {
                    segment.original_scalar_end = end;
                }
                _ => segments.push(WindowSegment {
                    source_turn_index: turn_index,
                    original_scalar_start: start,
                    original_scalar_end: end,
                }),
            }
            words += 1;
            if words == WINDOW_WORDS {
                finished.push(CorpusWindow {
                    window_index: finished.len() as u64,
                    word_count: words as u64,
                    segments: std::mem::take(&mut segments),
                });
                words = 0;
            }
        }
    }
    if words > 0 {
        finished.push(CorpusWindow {
            window_index: finished.len() as u64,
            word_count: words as u64,
            segments,
        });
    }
    finished
}

/// Rebuild the exact string the measurement embedded: the window's words joined
/// by one space.
///
/// Deliberately not the source slice. The harness joined turns and re-split on
/// whitespace, so runs of spaces, tabs and newlines collapse; a slice would keep
/// them and quietly embed different bytes than were measured.
///
/// `turn` resolves a turn index to its original text. `None` means the window
/// cannot be reconstructed — a missing turn, or an offset past the end of one —
/// and the caller must refuse rather than embed a partial window.
pub fn window_text<'a>(
    window: &CorpusWindow,
    turn: impl Fn(u64) -> Option<&'a str>,
) -> Option<String> {
    let mut words: Vec<&str> = Vec::new();
    for segment in &window.segments {
        let text = turn(segment.source_turn_index)?;
        let slice = scalar_slice(
            text,
            segment.original_scalar_start,
            segment.original_scalar_end,
        )?;
        words.extend(slice.split(is_word_separator).filter(|w| !w.is_empty()));
    }
    if words.len() as u64 != window.word_count {
        return None;
    }
    Some(words.join(" "))
}

/// What a vector is bound to. A window whose text changes gets a new digest, so
/// a vector computed from the old text stops matching instead of answering with
/// yesterday's meeting.
pub fn window_digest(text: &str) -> String {
    let mut hasher = Sha256::new();
    hasher.update(text.as_bytes());
    hex(&hasher.finalize())
}

fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|byte| format!("{byte:02x}")).collect()
}

/// Scalar spans of each maximal run of non-separator characters.
fn word_spans(text: &str) -> Vec<(u64, u64)> {
    let mut spans = Vec::new();
    let mut open: Option<u64> = None;
    let mut scalar = 0_u64;
    for character in text.chars() {
        if is_word_separator(character) {
            if let Some(start) = open.take() {
                spans.push((start, scalar));
            }
        } else if open.is_none() {
            open = Some(scalar);
        }
        scalar += 1;
    }
    if let Some(start) = open {
        spans.push((start, scalar));
    }
    spans
}

/// Slice by Unicode scalar index, refusing rather than panicking on a range the
/// text cannot supply.
fn scalar_slice(text: &str, start: u64, end: u64) -> Option<&str> {
    if end < start {
        return None;
    }
    let mut byte_start = None;
    let mut byte_end = None;
    for (scalar, (offset, _)) in text.char_indices().enumerate() {
        let scalar = scalar as u64;
        if scalar == start {
            byte_start = Some(offset);
        }
        if scalar == end {
            byte_end = Some(offset);
        }
    }
    let total = text.chars().count() as u64;
    if end == total {
        byte_end = Some(text.len());
    }
    if start == total && end == total {
        byte_start = Some(text.len());
    }
    Some(&text[byte_start?..byte_end?])
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::Value;
    use std::path::PathBuf;

    fn fixture() -> Value {
        let path = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../notes/window_equivalence_fixture.json");
        let bytes = std::fs::read(&path).expect("equivalence fixture is committed");
        serde_json::from_slice(&bytes).expect("equivalence fixture is JSON")
    }

    /// Frozen artifact: every expectation here was produced by
    /// `semantic_scale_probe.chunk_units`, the function whose output the
    /// committed receipt describes. It pins literals from that file and does
    /// **not** follow this module's constants, because its job is to catch this
    /// module drifting away from what was measured.
    #[test]
    fn the_measured_windowing_is_reproduced_exactly() {
        let document = fixture();
        assert_eq!(document["schema"], "window-equivalence/1");
        assert_eq!(
            document["window_tokens"].as_u64(),
            Some(WINDOW_WORDS as u64),
            "the fixture was generated at a different width than this module uses"
        );
        let cases = document["cases"].as_array().expect("cases");
        assert_eq!(cases.len(), 7, "the fixture is frozen at seven cases");

        let mut total_windows = 0;
        for case in cases {
            let identifier = case["id"].as_str().expect("id");
            let turns: Vec<String> = case["turns"]
                .as_array()
                .expect("turns")
                .iter()
                .map(|turn| turn.as_str().expect("turn text").to_owned())
                .collect();
            let expected: Vec<&str> = case["windows"]
                .as_array()
                .expect("windows")
                .iter()
                .map(|window| window.as_str().expect("window text"))
                .collect();

            let indexed: Vec<(u64, &str, bool)> = turns
                .iter()
                .enumerate()
                .map(|(index, text)| (index as u64, text.as_str(), false))
                .collect();
            let produced = windows(indexed);
            assert_eq!(
                produced.len(),
                expected.len(),
                "{identifier}: window count differs from the measured harness"
            );
            for (window, expected_text) in produced.iter().zip(&expected) {
                let text = window_text(window, |index| {
                    turns.get(index as usize).map(String::as_str)
                })
                .expect("every window reconstructs from its own segments");
                assert_eq!(
                    &text, expected_text,
                    "{identifier}: window {} text differs from the measured harness",
                    window.window_index
                );
            }
            total_windows += produced.len();
        }
        assert_eq!(
            total_windows, 18,
            "the fixture is frozen at eighteen windows"
        );
    }

    /// Live behaviour, so it follows the constant rather than a literal.
    #[test]
    fn only_the_last_window_of_a_meeting_may_be_short() {
        let long = (0..WINDOW_WORDS * 2 + 7)
            .map(|index| format!("w{index}"))
            .collect::<Vec<_>>()
            .join(" ");
        let produced = windows([(0_u64, long.as_str(), false)]);
        assert_eq!(produced.len(), 3);
        assert_eq!(produced[0].word_count, WINDOW_WORDS as u64);
        assert_eq!(produced[1].word_count, WINDOW_WORDS as u64);
        assert_eq!(produced[2].word_count, 7);
        for (position, window) in produced.iter().enumerate() {
            assert_eq!(window.window_index, position as u64);
        }
    }

    #[test]
    fn a_gated_turn_contributes_no_words_and_no_segments() {
        let produced = windows([
            (0_u64, "alpha beta", false),
            (1_u64, "withheld words here", true),
            (2_u64, "gamma", false),
        ]);
        assert_eq!(produced.len(), 1);
        assert_eq!(produced[0].word_count, 3);
        let touched: Vec<u64> = produced[0]
            .segments
            .iter()
            .map(|segment| segment.source_turn_index)
            .collect();
        assert_eq!(touched, vec![0, 2], "a gated turn was cited by a window");
    }

    /// The window either side of withheld speech joins. The citation must still
    /// name two turns, so a renderer can refuse to present it as one sentence.
    #[test]
    fn text_across_a_gated_turn_joins_but_the_citation_does_not() {
        let turns = ["we agreed to", "the private part", "ship on Friday"];
        let produced = windows([
            (0_u64, turns[0], false),
            (1_u64, turns[1], true),
            (2_u64, turns[2], false),
        ]);
        let text = window_text(&produced[0], |index| turns.get(index as usize).copied())
            .expect("reconstructs");
        assert_eq!(text, "we agreed to ship on Friday");
        assert_eq!(produced[0].segments.len(), 2);
    }

    #[test]
    fn an_empty_meeting_yields_no_windows() {
        assert!(windows([(0_u64, "   \t\n ", false)]).is_empty());
        assert!(windows([(0_u64, "every word withheld", true)]).is_empty());
        assert!(windows(std::iter::empty::<(u64, &str, bool)>()).is_empty());
    }

    /// The four separators Python counts and Rust does not are the reason this
    /// predicate exists rather than `char::is_whitespace`.
    #[test]
    fn separator_set_matches_python_isspace() {
        let expected: Vec<u32> = vec![
            0x9, 0xa, 0xb, 0xc, 0xd, 0x1c, 0x1d, 0x1e, 0x1f, 0x20, 0x85, 0xa0, 0x1680, 0x2000,
            0x2001, 0x2002, 0x2003, 0x2004, 0x2005, 0x2006, 0x2007, 0x2008, 0x2009, 0x200a, 0x2028,
            0x2029, 0x202f, 0x205f, 0x3000,
        ];
        let actual: Vec<u32> = (0..=0x10_FFFF_u32)
            .filter_map(char::from_u32)
            .filter(|character| is_word_separator(*character))
            .map(u32::from)
            .collect();
        assert_eq!(actual, expected);
        for separator in [0x1c, 0x1d, 0x1e, 0x1f] {
            let character = char::from_u32(separator).expect("separator");
            assert!(
                !character.is_whitespace(),
                "U+{separator:04X} is now Unicode whitespace; the widening is stale"
            );
        }
    }

    #[test]
    fn offsets_are_scalars_not_bytes() {
        let text = "héllo wörld";
        let produced = windows([(0_u64, text, false)]);
        let segment = produced[0].segments[0];
        assert_eq!(segment.original_scalar_start, 0);
        assert_eq!(
            segment.original_scalar_end,
            text.chars().count() as u64,
            "a multi-byte turn must report scalar offsets, not byte offsets"
        );
        assert_ne!(text.len(), text.chars().count());
    }

    #[test]
    fn a_window_whose_turn_is_gone_refuses_rather_than_shortening() {
        let produced = windows([(0_u64, "alpha beta", false), (1_u64, "gamma", false)]);
        assert!(window_text(&produced[0], |index| (index == 0).then_some("alpha beta")).is_none());
    }

    #[test]
    fn every_reimplementable_choice_is_inside_the_identity() {
        let measured = EmbedderIdentity::measured();
        for altered in [
            EmbedderIdentity {
                pooling: "cls".to_owned(),
                ..measured.clone()
            },
            EmbedderIdentity {
                max_sequence_tokens: 512,
                ..measured.clone()
            },
            EmbedderIdentity {
                activation: "tanh-gelu".to_owned(),
                ..measured.clone()
            },
            EmbedderIdentity {
                revision: "0000000000000000000000000000000000000000".to_owned(),
                ..measured.clone()
            },
            // The one this type shipped without. Two tokenizers turn the same
            // sentence into different token IDs, so every vector differs while
            // every other field still matches.
            EmbedderIdentity {
                tokenizer_sha256: "0".repeat(64),
                ..measured.clone()
            },
            EmbedderIdentity {
                weights_sha256: "0".repeat(64),
                ..measured.clone()
            },
        ] {
            assert_ne!(
                altered.canonical(),
                measured.canonical(),
                "a vector produced under a different choice would compare as the same embedder"
            );
        }
        assert!(measured.canonical().contains("all-MiniLM-L6-v2"));
    }

    #[test]
    fn a_manifest_packaging_a_different_model_does_not_match() {
        let measured = EmbedderIdentity::measured();
        let packaged = [
            (
                EmbedderIdentity::TOKENIZER_MODEL_ID,
                measured.tokenizer_sha256.as_str(),
            ),
            (
                EmbedderIdentity::WEIGHTS_MODEL_ID,
                measured.weights_sha256.as_str(),
            ),
            ("whisper-large-v3-turbo-weights", "irrelevant"),
        ];
        assert!(measured.matches_manifest(&packaged));

        let other = "0".repeat(64);
        for swapped in [
            [
                (EmbedderIdentity::TOKENIZER_MODEL_ID, other.as_str()),
                (
                    EmbedderIdentity::WEIGHTS_MODEL_ID,
                    measured.weights_sha256.as_str(),
                ),
            ],
            [
                (
                    EmbedderIdentity::TOKENIZER_MODEL_ID,
                    measured.tokenizer_sha256.as_str(),
                ),
                (EmbedderIdentity::WEIGHTS_MODEL_ID, other.as_str()),
            ],
        ] {
            assert!(!measured.matches_manifest(&swapped));
        }
        assert!(
            !measured.matches_manifest(&[]),
            "a runtime packaging no model must not read as packaging the right one"
        );
    }

    #[test]
    fn the_digest_moves_when_the_text_moves() {
        assert_eq!(window_digest("alpha beta"), window_digest("alpha beta"));
        assert_ne!(window_digest("alpha beta"), window_digest("alpha  beta"));
        assert_eq!(window_digest("").len(), 64);
    }
}

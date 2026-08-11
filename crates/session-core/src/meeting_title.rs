//! What a meeting is called when nobody has called it anything.
//!
//! Every row in the library reads `Untitled meeting` today. That is not a
//! placeholder waiting on a feature: [`crate::library_metadata`] states in its
//! first line that it "deliberately has no writer", so the operator title it
//! reads is a field nothing in this product can set. Forty meetings are forty
//! identical rows. Meetings must remain readable under generated date-based labels
//! and
//! at "title is nullable to restore the generated date label". Neither
//! sentence had an implementation behind it.
//!
//! The precedence a reader applies is operator title, then derived title, then
//! the meeting's capture time. This module owns the middle one. Only the first
//! is authority; this one is recomputed from canonical bytes on every read.
//!
//! The last one is deliberately not here. A row already carries
//! `created_at_epoch_seconds`, and the shell already formats it in the
//! operator's own locale and zone — so a second copy of the same instant,
//! rendered here in UTC, would be a duplicate rather than a label. A reader
//! with no title and no transcript is told exactly that, and falls back to the
//! time it already has.
//!
//! # Why nothing here is stored
//!
//! A derived title is a library label, and `corpus_index` quotes the rule it
//! would break: "no derived index may become the sole copy of a meeting,
//! transcript, note, locator, or library label." Storing one would also need a
//! record, a writer, a revision, and a staleness rule against the transcript
//! digest — all of it to hold a value that is a pure function of bytes already
//! on disk. Recomputing it costs a pass over turns the reader has just parsed,
//! and it cannot go stale, because there is nothing to go stale against.
//!
//! # Why the title is extracted rather than written
//!
//! The category writes titles: Granola, Otter and Circleback all hand a
//! transcript to a model and display the phrase it returns. This product's one
//! surviving content invariant is that evidence is never decoration — a claim
//! cites resolvable words — and a phrase a model composed cites nothing. So
//! the title here is a span of the meeting: the first thing said in it that is
//! long enough to identify it. The operator can read the words back in the
//! transcript, because they are the transcript's own.
//!
//! That is a deliberate divergence from the category and it costs something
//! real. "Let's start with the Q3 pricing review" is a worse label than
//! "Q3 pricing", and no rule here will ever produce the second. Replacing
//! *which* span is chosen with a local model's judgment — the selection, not
//! the words — is the next build, and it lands behind this same function.
//!
//! # What the operator sees
//!
//! A derived label is a quotation of a meeting's opening line, displayed in a
//! list, without the meeting being opened. That is category-normal and it is
//! still a change in what a passer-by can read off the screen, so the shell
//! marks a derived label as derived rather than passing it off as a title
//! somebody chose.

/// Turns shorter than this never become a title.
///
/// It is a threshold on a distribution nobody has measured, chosen to skip
/// "yeah", "can you hear me", and "one sec" without skipping a genuinely short
/// agenda line. It is the arbitrary number in this module and the honest
/// falsifier is the operator: if the labels read as noise, this is the first
/// thing to move, and moving it changes no contract.
pub const MIN_TITLE_WORDS: usize = 6;

/// The 120-scalar ceiling keeps a derived label and a typed title within the same
/// practical reading width.
pub const MAX_TITLE_SCALARS: usize = 120;

/// The first thing said in this meeting that is long enough to identify it.
///
/// Turns arrive in canonical order as `(text, gated)`. A gated turn is a
/// withheld microphone turn: the reader retains its text so the operator can
/// restore it, and search exposes it only as `withheld`. A label is a list
/// surface with no gate behind it, so gated turns are skipped here — that is
/// the one rule in this module that is a safety property rather than a taste.
/// The precedence this module's doc names, in the one place that owns it.
///
/// Operator title, then derived title, then the capture time. The third tier
/// returns `None` rather than a string: a surface already holds
/// `created_at_epoch_seconds` and formats it in the operator's own zone, so a
/// second copy of the same instant rendered here in UTC would be a duplicate.
///
/// It exists because the rule had two readers before it had a home. The library
/// list applied it and the search surface did not, which put the same meeting on
/// the same screen under a sentence in one place and a timestamp in the other —
/// the kind of disagreement a reader finds and a test does not.
pub fn label(operator: Option<&str>, derived: Option<String>) -> (Option<String>, &'static str) {
    if let Some(title) = operator {
        return (Some(title.to_owned()), "operator");
    }
    match derived {
        Some(derived) => (Some(derived), "derived"),
        None => (None, "date"),
    }
}

pub fn derived_title<'a, I>(turns: I) -> Option<String>
where
    I: IntoIterator<Item = (&'a str, bool)>,
{
    turns
        .into_iter()
        .filter(|(_, gated)| !gated)
        .find_map(|(text, _)| opening_label(text))
}

/// One turn's opening sentence, cleaned and bounded, or nothing if it is too
/// short to name a meeting.
fn opening_label(text: &str) -> Option<String> {
    let sentence = first_sentence(text);
    let collapsed = collapse(sentence);
    if collapsed.split(' ').filter(|word| !word.is_empty()).count() < MIN_TITLE_WORDS {
        return None;
    }
    let bounded = truncate_at_word_boundary(&collapsed, MAX_TITLE_SCALARS);
    let trimmed = bounded.trim_end_matches('.').trim_end();
    (!trimmed.is_empty()).then(|| trimmed.to_owned())
}

/// Up to and including the first sentence terminator that is followed by
/// whitespace or the end of the turn.
///
/// The lookahead is what keeps `3.5` and `a.m.` inside one sentence. It does
/// not keep `Dr. Ellis` there, and no cheap rule does; a label that stops at
/// "Dr" is wrong in a way the operator can see and correct, which is the
/// failure mode to prefer.
fn first_sentence(text: &str) -> &str {
    let mut characters = text.char_indices().peekable();
    while let Some((offset, character)) = characters.next() {
        if !matches!(character, '.' | '?' | '!') {
            continue;
        }
        let ends_here = characters
            .peek()
            .is_none_or(|(_, next)| next.is_whitespace());
        if ends_here {
            return &text[..offset + character.len_utf8()];
        }
    }
    text
}

/// Every whitespace run becomes one space and control characters are dropped,
/// so nothing in a label can move a cursor or open a line in whatever renders
/// it. Unicode line separators are covered by the whitespace arm — `U+2028`
/// and `U+2029` carry `White_Space`, so they collapse to a space rather than
/// falling through to the control arm.
fn collapse(text: &str) -> String {
    let mut out = String::with_capacity(text.len());
    let mut pending_space = false;
    for character in text.chars() {
        if character.is_whitespace() {
            pending_space = !out.is_empty();
            continue;
        }
        if character.is_control() {
            continue;
        }
        if pending_space {
            out.push(' ');
            pending_space = false;
        }
        out.push(character);
    }
    out
}

/// At most `max` Unicode scalars, cut back to the last space so a label never
/// ends mid-word. A first word longer than the ceiling is cut where the
/// ceiling falls, because the alternative is an empty label.
fn truncate_at_word_boundary(text: &str, max: usize) -> String {
    if text.chars().count() <= max {
        return text.to_owned();
    }
    let cut: String = text.chars().take(max).collect();
    match cut.rfind(' ') {
        Some(index) if index > 0 => cut[..index].to_owned(),
        _ => cut,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn turns<'a>(rows: &'a [(&'a str, bool)]) -> impl IntoIterator<Item = (&'a str, bool)> {
        rows.iter().copied()
    }

    /// The probe's fixtures assert which turn this function picks. This test is
    /// the assertion — without it `control_turn` would be a number in a JSON
    /// file describing behaviour nothing checks, and the probe would be
    /// measuring the model against a baseline it had guessed at.
    ///
    /// It needs no new public API. Deriving from the whole transcript and
    /// deriving from the named turn alone must produce the same string, and
    /// every turn before it must produce nothing — which is exactly what "the
    /// first turn that qualifies" means.
    #[test]
    fn the_probe_fixtures_name_the_turn_this_function_actually_picks() {
        let document: serde_json::Value =
            serde_json::from_str(include_str!("../../../notes/title_selection_fixtures.json"))
                .expect("fixtures parse");
        assert_eq!(document["schema"], "title-selection-fixtures/1");
        let fixtures = document["fixtures"].as_array().expect("fixture array");
        assert!(!fixtures.is_empty());

        for fixture in fixtures {
            let name = fixture["name"].as_str().expect("fixture name");
            let rows: Vec<(&str, bool)> = fixture["turns"]
                .as_array()
                .expect("turns")
                .iter()
                .map(|turn| {
                    (
                        turn["text"].as_str().expect("turn text"),
                        turn["gated"].as_bool().expect("turn gated"),
                    )
                })
                .collect();
            let control = fixture["control_turn"].as_u64().expect("control_turn") as usize;

            let whole = derived_title(turns(&rows));
            let alone = derived_title(turns(&rows[control..=control]));
            assert!(alone.is_some(), "{name}: control turn derives no title");
            assert_eq!(whole, alone, "{name}: the picked turn is not control_turn");

            for (index, row) in rows[..control].iter().enumerate() {
                assert_eq!(
                    derived_title(turns(std::slice::from_ref(row))),
                    None,
                    "{name}: turn {index} qualifies, so control_turn is not the first"
                );
            }
        }
    }

    #[test]
    fn the_first_long_enough_opening_line_becomes_the_title() {
        assert_eq!(
            derived_title(turns(&[
                ("Hey.", false),
                ("Can you hear me?", false),
                (
                    "Let's start with the Q3 pricing review. Ravi has the numbers.",
                    false
                ),
            ])),
            Some("Let's start with the Q3 pricing review".into())
        );
    }

    #[test]
    fn a_withheld_turn_is_never_a_title_even_when_it_is_the_only_candidate() {
        assert_eq!(
            derived_title(turns(&[(
                "My doctor called about the biopsy results this morning.",
                true
            )])),
            None,
            "a gated turn is withheld from search and must be withheld from a list label"
        );
        assert_eq!(
            derived_title(turns(&[
                (
                    "My doctor called about the biopsy results this morning.",
                    true
                ),
                ("We should walk through the migration plan today.", false),
            ])),
            Some("We should walk through the migration plan today".into())
        );
    }

    #[test]
    fn a_transcript_with_nothing_long_enough_yields_no_title() {
        assert_eq!(
            derived_title(turns(&[
                ("Hi.", false),
                ("Yeah.", false),
                ("One sec", false)
            ])),
            None
        );
        assert_eq!(derived_title(turns(&[])), None);
    }

    #[test]
    fn a_sentence_terminator_inside_a_number_or_abbreviation_does_not_end_the_sentence() {
        assert_eq!(
            derived_title(turns(&[(
                "The build is 3.5 hours and we cannot ship it.",
                false
            )])),
            Some("The build is 3.5 hours and we cannot ship it".into())
        );
    }

    #[test]
    fn a_question_keeps_its_mark_and_a_statement_loses_its_stop() {
        assert_eq!(
            derived_title(turns(&[("Are we still shipping this on Friday?", false)])),
            Some("Are we still shipping this on Friday?".into())
        );
        assert_eq!(
            derived_title(turns(&[("We are shipping this on Friday.", false)])),
            Some("We are shipping this on Friday".into())
        );
    }

    #[test]
    fn control_characters_and_line_separators_never_reach_a_label() {
        let title = derived_title(turns(&[(
            "we\u{7}should\u{2028}review\nthe   deployment\tchecklist today",
            false,
        )]))
        .unwrap();
        assert_eq!(title, "weshould review the deployment checklist today");
        assert!(!title.chars().any(|character| character.is_control()));
        assert!(!title.contains(['\u{2028}', '\u{2029}']));
    }

    #[test]
    fn a_long_opening_line_is_cut_at_a_word_boundary_within_the_ceiling() {
        let text = "we need to talk about the migration plan because the schema \
                    change landed last night and nobody has looked at what it did \
                    to the reporting jobs yet";
        let title = derived_title(turns(&[(text, false)])).unwrap();
        assert!(title.chars().count() <= MAX_TITLE_SCALARS);
        assert!(text.starts_with(&title), "a title is a span of the turn");
        assert!(!title.ends_with(' '));
        assert!(
            text[title.len()..].starts_with(' '),
            "the cut lands between words, not inside one"
        );
    }

    #[test]
    fn a_single_word_longer_than_the_ceiling_is_cut_at_the_ceiling() {
        let word = "a".repeat(MAX_TITLE_SCALARS + 40);
        let text = format!("{word} and then some more words after it");
        let title = derived_title(turns(&[(text.as_str(), false)])).unwrap();
        assert_eq!(title.chars().count(), MAX_TITLE_SCALARS);
    }

    #[test]
    fn a_title_is_always_a_contiguous_span_of_the_turn_it_came_from() {
        for text in [
            "Let's start with the Q3 pricing review. Ravi has the numbers.",
            "Are we still shipping this on Friday?",
            "we need to talk about the migration plan because the schema change landed",
        ] {
            let title = derived_title(turns(&[(text, false)])).unwrap();
            assert!(
                text.contains(&title),
                "{title:?} is not a span of {text:?} — the evidence claim in this module is false"
            );
        }
    }
}

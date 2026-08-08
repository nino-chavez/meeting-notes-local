//! Walking the corpus's unembedded windows through an embedder and into the store.
//!
//! # The seam, and why it is a trait
//!
//! The only embedder that exists is a Python process on the other side of a
//! JSON protocol, reached through the desktop crate's `WorkerPort`. None of that
//! belongs here: this module owns *which* windows to send, *how many* at a time,
//! and what a reply has to contain before a vector is stored. The transport owns
//! base64 and timeouts.
//!
//! So [`WindowEmbedder`] is deliberately one method taking already-built
//! [`PendingWindow`]s and returning decoded vectors. A fake implements it in
//! four lines, which is how everything below is tested without a model.
//!
//! # What a pass will not do
//!
//! **It will not skip a window it asked about.** A digest missing from a reply
//! stops the pass. The alternative — carry on and try the next batch — quietly
//! produces a store that is permanently short of a few windows nobody can name,
//! and `vector_coverage` would report the gap without ever explaining it.
//!
//! **It will not retry.** The desktop's `ProcessWorkerPort` drops the worker
//! from application state on any error, so every later caller sees "worker is
//! unavailable" — an embedding failure that retried would take transcription
//! down with it for longer. One failure ends the pass and says so.
//!
//! **It will not run forever.** `budget_windows` bounds one pass. The number is
//! the caller's, because the caller knows whether it is on a path a person is
//! waiting on.
//!
//! # A duplicate reply entry is correct, not short
//!
//! Two windows with identical text have identical vectors, and the worker
//! returns one entry for both — pinned on that side by
//! `identical_windows_collapse_to_one_entry`. So a reply is matched back **by
//! digest, per window**, never by length. Comparing counts would refuse a
//! correct answer.

use std::collections::HashMap;

use crate::corpus_index::{CorpusIndex, CorpusIndexError, PendingWindow, WindowVector};
use crate::corpus_window::EmbedderIdentity;

/// Windows per request, and it must not exceed the worker's own cap.
///
/// `worker/embedding.py` derives `MAX_WINDOWS_PER_REQUEST` from the protocol's
/// 64 KiB frame: 384 little-endian float32s is 2,048 base64 characters, so
/// twenty-four replies fit with room for their digests. Asking for more gets the
/// whole batch refused.
///
/// `the_request_size_matches_the_workers_own_cap` reads the Python rather than
/// trusting this comment. That is not caution — the same two-language constant
/// drifted on 2026-08-08 with a correct comment sitting directly above it, and
/// left the app refusing its own worker.
pub const WINDOWS_PER_REQUEST: usize = 24;

/// Why a pass stopped before the corpus was covered.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum FillStop {
    /// Nothing left to embed. The only outcome that means the store is complete.
    Complete,
    /// `budget_windows` reached. More remain and another pass will get them.
    BudgetReached,
    /// The embedder failed. Not retried; see the module doc.
    EmbedderUnavailable(String),
    /// A reply did not answer for a window that was asked about.
    ReplyIncomplete,
    /// The runtime packages a different model than these vectors describe.
    ModelMismatch,
}

/// What one pass did. Counts only; never a meeting ID, never text.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FillOutcome {
    pub requested: usize,
    pub embedded: usize,
    pub batches: usize,
    pub stop: FillStop,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct EmbedderUnavailable(pub String);

/// Text to vector. The only thing this module needs from a model.
pub trait WindowEmbedder {
    /// Digest to vector for the windows offered, or an error for the batch.
    ///
    /// A reply may be **shorter** than the request when two windows hold
    /// identical text. It may never be longer, and every requested digest must
    /// appear; the caller checks both.
    fn embed(
        &self,
        windows: &[PendingWindow],
    ) -> Result<HashMap<String, Vec<f32>>, EmbedderUnavailable>;
}

/// Embed up to `budget_windows` of whatever this embedder still owes vectors
/// for, oldest meeting first.
///
/// `packaged_models` is the runtime manifest's `(id, sha256)` pairs. The pass
/// refuses before its first request if they do not describe the model this
/// identity names — vectors from a different tokenizer are the right shape and
/// the wrong direction, and nothing downstream can tell.
pub fn fill_vectors(
    index: &mut CorpusIndex,
    identity: &EmbedderIdentity,
    embedder: &dyn WindowEmbedder,
    packaged_models: &[(&str, &str)],
    budget_windows: usize,
) -> Result<FillOutcome, CorpusIndexError> {
    let mut outcome = FillOutcome {
        requested: 0,
        embedded: 0,
        batches: 0,
        stop: FillStop::Complete,
    };
    if !identity.matches_manifest(packaged_models) {
        outcome.stop = FillStop::ModelMismatch;
        return Ok(outcome);
    }
    if budget_windows == 0 {
        outcome.stop = FillStop::BudgetReached;
        return Ok(outcome);
    }

    while outcome.requested < budget_windows {
        let room = (budget_windows - outcome.requested).min(WINDOWS_PER_REQUEST);
        let pending = index.pending_windows(identity, room)?;
        if pending.is_empty() {
            outcome.stop = FillStop::Complete;
            return Ok(outcome);
        }
        outcome.requested += pending.len();
        outcome.batches += 1;

        let replies = match embedder.embed(&pending) {
            Ok(replies) => replies,
            Err(EmbedderUnavailable(reason)) => {
                outcome.stop = FillStop::EmbedderUnavailable(reason);
                return Ok(outcome);
            }
        };

        let mut vectors = Vec::with_capacity(pending.len());
        for window in &pending {
            // By digest, per window. A shorter reply is correct when two windows
            // share text; a *missing* digest is a refusal.
            let Some(values) = replies.get(&window.text_sha256) else {
                outcome.stop = FillStop::ReplyIncomplete;
                return Ok(outcome);
            };
            vectors.push(WindowVector {
                meeting_id: window.meeting_id.clone(),
                window_index: window.window_index,
                text_sha256: window.text_sha256.clone(),
                values: values.clone(),
            });
        }
        // The store re-checks width and binding and refuses the whole batch, so
        // a wrong-sized vector cannot arrive through here even if the transport
        // let it past.
        outcome.embedded += index.store_window_vectors(identity, &vectors)?;
    }

    outcome.stop = FillStop::BudgetReached;
    Ok(outcome)
}

#[cfg(test)]
mod tests {
    use std::cell::RefCell;

    use super::*;

    /// A model that answers with a distinct unit vector per digest, so a
    /// ranking assertion is about ranking rather than floating point.
    struct FakeEmbedder {
        dimension: usize,
        calls: RefCell<Vec<usize>>,
        fail_on_call: Option<usize>,
        omit: Option<String>,
        wrong_width: bool,
    }

    impl FakeEmbedder {
        fn new(dimension: usize) -> Self {
            Self {
                dimension,
                calls: RefCell::new(Vec::new()),
                fail_on_call: None,
                omit: None,
                wrong_width: false,
            }
        }
    }

    impl WindowEmbedder for FakeEmbedder {
        fn embed(
            &self,
            windows: &[PendingWindow],
        ) -> Result<HashMap<String, Vec<f32>>, EmbedderUnavailable> {
            let call = self.calls.borrow().len();
            self.calls.borrow_mut().push(windows.len());
            if self.fail_on_call == Some(call) {
                return Err(EmbedderUnavailable("the worker went away".into()));
            }
            let width = if self.wrong_width {
                self.dimension - 1
            } else {
                self.dimension
            };
            Ok(windows
                .iter()
                .filter(|window| self.omit.as_deref() != Some(window.text_sha256.as_str()))
                .map(|window| {
                    let mut values = vec![0.0_f32; width];
                    let slot = usize::from_str_radix(&window.text_sha256[..4], 16).unwrap_or(0);
                    values[slot % width] = 1.0;
                    (window.text_sha256.clone(), values)
                })
                .collect())
        }
    }

    fn measured_models(identity: &EmbedderIdentity) -> Vec<(&str, &str)> {
        vec![
            (
                EmbedderIdentity::TOKENIZER_MODEL_ID,
                identity.tokenizer_sha256.as_str(),
            ),
            (
                EmbedderIdentity::WEIGHTS_MODEL_ID,
                identity.weights_sha256.as_str(),
            ),
        ]
    }

    use crate::corpus_index::tests::{Fixture, synced};

    fn corpus(meetings: usize) -> (Fixture, CorpusIndex) {
        let fixture = Fixture::new();
        for index in 0..meetings {
            fixture.meeting(
                &format!("meeting-{index:03}"),
                100 + index as u64,
                &[&format!(
                    "meeting {index} said something worth finding later"
                )],
            );
        }
        let index = synced(&fixture);
        (fixture, index)
    }

    #[test]
    fn a_pass_embeds_every_window_and_stops_when_there_is_nothing_left() {
        let identity = EmbedderIdentity::measured();
        let (_fixture, mut index) = corpus(3);
        let embedder = FakeEmbedder::new(identity.dimension as usize);

        let outcome = fill_vectors(
            &mut index,
            &identity,
            &embedder,
            &measured_models(&identity),
            1_000,
        )
        .unwrap();
        assert_eq!(outcome.stop, FillStop::Complete);
        assert_eq!((outcome.requested, outcome.embedded), (3, 3));
        assert!(index.vector_coverage(&identity).unwrap().complete());

        // A second pass has nothing to do and must not call the embedder again.
        let before = embedder.calls.borrow().len();
        let again = fill_vectors(
            &mut index,
            &identity,
            &embedder,
            &measured_models(&identity),
            1_000,
        )
        .unwrap();
        assert_eq!(again.stop, FillStop::Complete);
        assert_eq!(again.requested, 0);
        assert_eq!(embedder.calls.borrow().len(), before);
    }

    #[test]
    fn a_pass_batches_at_the_request_size_and_never_above_it() {
        let identity = EmbedderIdentity::measured();
        let (_fixture, mut index) = corpus(WINDOWS_PER_REQUEST + 5);
        let embedder = FakeEmbedder::new(identity.dimension as usize);

        let outcome = fill_vectors(
            &mut index,
            &identity,
            &embedder,
            &measured_models(&identity),
            1_000,
        )
        .unwrap();
        assert_eq!(outcome.stop, FillStop::Complete);
        assert_eq!(outcome.batches, 2);
        assert_eq!(*embedder.calls.borrow(), vec![WINDOWS_PER_REQUEST, 5]);
    }

    #[test]
    fn the_budget_bounds_a_pass_and_the_last_request_is_not_oversized() {
        let identity = EmbedderIdentity::measured();
        let (_fixture, mut index) = corpus(WINDOWS_PER_REQUEST + 5);
        let embedder = FakeEmbedder::new(identity.dimension as usize);

        let outcome = fill_vectors(
            &mut index,
            &identity,
            &embedder,
            &measured_models(&identity),
            WINDOWS_PER_REQUEST + 2,
        )
        .unwrap();
        assert_eq!(outcome.stop, FillStop::BudgetReached);
        assert_eq!(outcome.requested, WINDOWS_PER_REQUEST + 2);
        assert_eq!(*embedder.calls.borrow(), vec![WINDOWS_PER_REQUEST, 2]);

        let coverage = index.vector_coverage(&identity).unwrap();
        assert_eq!(coverage.embedded, WINDOWS_PER_REQUEST + 2);
        assert!(!coverage.complete(), "a bounded pass must not read as done");
    }

    #[test]
    fn a_zero_budget_asks_the_embedder_nothing() {
        let identity = EmbedderIdentity::measured();
        let (_fixture, mut index) = corpus(2);
        let embedder = FakeEmbedder::new(identity.dimension as usize);

        let outcome = fill_vectors(
            &mut index,
            &identity,
            &embedder,
            &measured_models(&identity),
            0,
        )
        .unwrap();
        assert_eq!(outcome.stop, FillStop::BudgetReached);
        assert!(embedder.calls.borrow().is_empty());
    }

    #[test]
    fn a_failed_batch_ends_the_pass_rather_than_moving_to_the_next() {
        let identity = EmbedderIdentity::measured();
        let (_fixture, mut index) = corpus(WINDOWS_PER_REQUEST + 5);
        let mut embedder = FakeEmbedder::new(identity.dimension as usize);
        embedder.fail_on_call = Some(1);

        let outcome = fill_vectors(
            &mut index,
            &identity,
            &embedder,
            &measured_models(&identity),
            1_000,
        )
        .unwrap();
        assert_eq!(
            outcome.stop,
            FillStop::EmbedderUnavailable("the worker went away".into())
        );
        assert_eq!(embedder.calls.borrow().len(), 2, "it retried a dead worker");
        assert_eq!(
            index.vector_coverage(&identity).unwrap().embedded,
            WINDOWS_PER_REQUEST,
            "the batch that succeeded before the failure was kept"
        );
    }

    #[test]
    fn a_reply_that_skips_a_window_stops_the_pass_and_stores_none_of_that_batch() {
        let identity = EmbedderIdentity::measured();
        let (_fixture, mut index) = corpus(3);
        let skipped = index.pending_windows(&identity, 0).unwrap()[1]
            .text_sha256
            .clone();
        let mut embedder = FakeEmbedder::new(identity.dimension as usize);
        embedder.omit = Some(skipped);

        let outcome = fill_vectors(
            &mut index,
            &identity,
            &embedder,
            &measured_models(&identity),
            1_000,
        )
        .unwrap();
        assert_eq!(outcome.stop, FillStop::ReplyIncomplete);
        assert_eq!(
            index.vector_coverage(&identity).unwrap().embedded,
            0,
            "a partial answer left a partly-filled store"
        );
    }

    /// Two meetings holding the same words produce one reply entry for both, and
    /// both windows must end up with it. Comparing reply length to request
    /// length would refuse this correct answer.
    #[test]
    fn identical_windows_share_one_reply_entry_and_both_are_stored() {
        let identity = EmbedderIdentity::measured();
        let fixture = Fixture::new();
        fixture.meeting("meeting-a", 100, &["the lease renews in March"]);
        fixture.meeting("meeting-b", 200, &["the lease renews in March"]);
        let mut index = synced(&fixture);
        let embedder = FakeEmbedder::new(identity.dimension as usize);

        let pending = index.pending_windows(&identity, 0).unwrap();
        assert_eq!(pending.len(), 2);
        assert_eq!(pending[0].text_sha256, pending[1].text_sha256);

        let outcome = fill_vectors(
            &mut index,
            &identity,
            &embedder,
            &measured_models(&identity),
            1_000,
        )
        .unwrap();
        assert_eq!(outcome.stop, FillStop::Complete);
        assert_eq!((outcome.requested, outcome.embedded), (2, 2));
        assert!(index.vector_coverage(&identity).unwrap().complete());
    }

    #[test]
    fn a_wrong_width_vector_is_refused_by_the_store_rather_than_stored() {
        let identity = EmbedderIdentity::measured();
        let (_fixture, mut index) = corpus(1);
        let mut embedder = FakeEmbedder::new(identity.dimension as usize);
        embedder.wrong_width = true;

        assert!(matches!(
            fill_vectors(
                &mut index,
                &identity,
                &embedder,
                &measured_models(&identity),
                1_000
            ),
            Err(CorpusIndexError::VectorRejected)
        ));
        assert_eq!(index.vector_coverage(&identity).unwrap().embedded, 0);
    }

    #[test]
    fn a_runtime_packaging_another_model_is_refused_before_anything_is_asked() {
        let identity = EmbedderIdentity::measured();
        let (_fixture, mut index) = corpus(2);
        let embedder = FakeEmbedder::new(identity.dimension as usize);

        let outcome = fill_vectors(
            &mut index,
            &identity,
            &embedder,
            &[
                (
                    EmbedderIdentity::TOKENIZER_MODEL_ID,
                    "0".repeat(64).as_str(),
                ),
                (
                    EmbedderIdentity::WEIGHTS_MODEL_ID,
                    identity.weights_sha256.as_str(),
                ),
            ],
            1_000,
        )
        .unwrap();
        assert_eq!(outcome.stop, FillStop::ModelMismatch);
        assert!(
            embedder.calls.borrow().is_empty(),
            "it embedded with a model it had not checked"
        );
    }

    /// Both sides of a two-language constant, read rather than restated. The
    /// lesson is dated: 2026-08-08, when the operation set drifted with a
    /// correct comment above it.
    #[test]
    fn the_request_size_matches_the_workers_own_cap() {
        let source = std::fs::read_to_string(
            std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../worker/embedding.py"),
        )
        .expect("worker/embedding.py is committed beside this crate");
        let line = source
            .lines()
            .find(|line| line.starts_with("MAX_WINDOWS_PER_REQUEST"))
            .expect("the worker still names MAX_WINDOWS_PER_REQUEST");
        let worker: usize = line
            .split('=')
            .nth(1)
            .and_then(|value| value.trim().parse().ok())
            .expect("its value is a plain integer");
        assert_eq!(
            WINDOWS_PER_REQUEST, worker,
            "asking for more than the worker accepts gets every batch refused"
        );
    }
}

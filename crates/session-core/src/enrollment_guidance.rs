//! Deterministic, content-free guidance for guided multi-session enrolment.
//!
//! `docs/screens-and-states.md` § I states the load-bearing rule for this
//! surface: the accumulating states must name the shortfall **in the terms the
//! code enforces**, never as a progress bar. A bar at "80%" tells the operator
//! to keep going; "return at least one hour after the first sitting, then
//! supply a permitted negative sample" tells them what to do.
//!
//! This module is that shortfall calculation and nothing else. It is
//! deliberately *not* an admission authority. The canonical semantic authority
//! is `spike/speaker_gate.py`: `load_profile`/`verify_provenance` re-derive the
//! enrolment contract from the profile receipt, and `worker/adapters.py`'s
//! `profile_inspect` runs that loader before any candidate reaches
//! `retention::ProfileLifecycleAuthority::enroll_profile_candidate`. What
//! happens here is *pre-build guidance*: it tells the operator what is still
//! missing before they spend a sitting, using the same rules that will later
//! refuse the build. A shortfall reported here is a refusal that has not
//! happened yet, not a verdict that one will not.
//!
//! Every constant below is mirrored from `spike/speaker_gate.py` with its
//! source name recorded, and [`tests::enforced_constants_match_the_capture_gate`]
//! pins each one. The repository's audit rule applies to this file as much as to
//! any artifact: a restatement of a contract is not the contract, so these are
//! re-derived at the canonical source rather than copied from § I's prose.
//!
//! Nothing here reads audio, transcripts, segment text, or profile bytes. The
//! evidence records carry counts, durations, timestamps and digests only.

use serde::Serialize;

/// A threshold needs cross-session variation to mean anything, so one sitting
/// can never enrol. Mirrors `verify_provenance`'s `n_sittings < 2` refusal.
pub const MIN_SITTINGS: usize = 2;

/// `speaker_gate.MIN_SITTING_GAP_S`. The canonical check is `gap < 3600` →
/// refuse, so exactly one hour passes. Different days are ideal, and the
/// surface says so, but only the hour is enforced.
pub const MIN_SITTING_GAP_SECONDS: u64 = 3_600;

/// `speaker_gate.MIN_ENROLL_SEGMENTS`. A separate floor from held-out
/// resolvability: both apply.
pub const MIN_ENROLL_SEGMENTS: u32 = 3;

/// `run_calibrate` refuses a recording with `len(emb) <= MIN_ENROLL_SEGMENTS`
/// and asks for `MIN_ENROLL_SEGMENTS + 1`, because a leave-one-out pass enrols
/// on `n - 1`. It is a floor on *each* sitting, not on their sum.
pub const MIN_SCORABLE_SEGMENTS_PER_SITTING: u32 = MIN_ENROLL_SEGMENTS + 1;

/// The pooled held-out count below which `operating_point_choices` cannot offer
/// two distinct targets, which it refuses to do. Derived from
/// `OPERATING_POINT_TARGETS`: the loosest needs `ceil(1/0.20) = 5` and the
/// next needs `ceil(1/0.10) = 10`, so ten is the necessary count for a choice
/// to exist at all. It is not sufficient — measured cost pairs may still
/// collapse, and only the operator's own calibration can show that.
pub const MIN_HELD_OUT_FOR_TWO_CHOICES: u32 = 10;

/// `speaker_gate.MIN_SCORABLE_S`. Segments shorter than this are kept in the
/// transcript but not judged by the gate, so they do not count as evidence.
pub const MIN_SCORABLE_SECONDS: f64 = 2.0;

/// `speaker_gate.MIN_NEGATIVE_SCORABLE_SECONDS`. The registered speech floor.
pub const MIN_NEGATIVE_SCORABLE_SECONDS: f64 = 60.0;

/// `speaker_gate.MIN_NEGATIVE_SCORABLE_SEGMENTS`. A product judgement separate
/// from duration: it stops one long passage posing as a score distribution and
/// permits a 5% false-admission observation. Neither floor is a statistical
/// guarantee.
pub const MIN_NEGATIVE_SCORABLE_SEGMENTS: u32 = 20;

/// `speaker_gate.THIN_HELD_OUT`. Above the resolvable floor and below this, a
/// sample quantile is real but soft. This is advisory, never a refusal.
pub const THIN_HELD_OUT_SEGMENTS: u32 = 30;

/// `speaker_gate.OPERATING_POINT_TARGETS`. Offered targets, loosest last.
pub const OPERATING_POINT_TARGETS: [f64; 5] = [0.01, 0.02, 0.05, 0.10, 0.20];

/// `speaker_gate.NEGATIVE_SOURCE_CLASSES`. A negative sample is not permission
/// to harvest someone else's speech.
pub const PERMITTED_NEGATIVE_SOURCE_CLASSES: [&str; 2] =
    ["public-or-licensed", "consenting-person"];

/// `speaker_gate.min_resolvable`: `ceil(1 / target_frr)`.
///
/// An order statistic cannot express a target the held-out sample is too small
/// to resolve. Returns `None` for a target outside `(0, 1]`, which no offered
/// target is.
#[must_use]
pub fn min_resolvable_held_out(target_frr: f64) -> Option<u32> {
    if !target_frr.is_finite() || target_frr <= 0.0 || target_frr > 1.0 {
        return None;
    }
    let resolvable = (1.0_f64 / target_frr).ceil();
    if resolvable > f64::from(u32::MAX) {
        return None;
    }
    Some(resolvable as u32)
}

/// One dedicated operator calibration sitting, recorded content-free.
///
/// `captured_at_epoch` is `None` for a recording made before the field existed.
/// `speaker_gate._sitting_metadata_problems` refuses that case outright rather
/// than assuming an order, because nothing then establishes the recording as a
/// separate sitting.
#[derive(Debug, Clone, PartialEq)]
pub struct SittingEvidence {
    pub captured_at_epoch: Option<u64>,
    pub audio_sha256: String,
    pub scorable_segments: u32,
    pub scorable_seconds: f64,
}

/// One permitted negative recording, recorded content-free.
#[derive(Debug, Clone, PartialEq)]
pub struct NegativeSourceEvidence {
    pub source_class: String,
    pub audio_sha256: String,
    pub scorable_segments: u32,
    pub scorable_seconds: f64,
}

/// Everything accumulated so far for one in-progress enrolment.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct EnrollmentEvidence {
    pub sittings: Vec<SittingEvidence>,
    pub negative_sources: Vec<NegativeSourceEvidence>,
}

/// The reachable states of `docs/screens-and-states.md` § I that a deterministic
/// evaluation over accumulated evidence can decide.
///
/// The states this deliberately cannot reach are named in
/// [`GuidedEnrollmentStatus::gates`]: every sitting state needs real dedicated
/// operator audio, and `ready-to-build` needs an operator selection that has no
/// default.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum GuidedEnrollmentState {
    /// No evidence at all. Supported meeting capture stays disabled.
    Blocked,
    /// Exactly one sitting held and the enforced gap has not yet elapsed for a
    /// second. The surface names the gap; it does not invent elapsed time.
    ResumeAfterGap,
    /// Operator sittings satisfy their own floors; observed counts and any
    /// refusal are shown before asking for negative material.
    SecondSittingReview,
    /// Operator material is sufficient and no permitted negative sample exists.
    NeedsOtherVoice,
    /// Every deterministic floor is met. The measured operating-point choices
    /// are produced by the worker, not here, and no option is selected by
    /// default.
    ChoosingOperatingPoint,
    /// Accumulated evidence cannot become a supported profile as it stands.
    Refused,
}

impl GuidedEnrollmentState {
    #[must_use]
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Blocked => "blocked",
            Self::ResumeAfterGap => "resume-after-gap",
            Self::SecondSittingReview => "second-sitting-review",
            Self::NeedsOtherVoice => "needs-other-voice",
            Self::ChoosingOperatingPoint => "choosing-operating-point",
            Self::Refused => "refused",
        }
    }
}

/// A shortfall stated in the terms the canonical gate enforces.
///
/// Each variant carries the observed value and the enforced floor so the
/// surface can render a sentence naming both without recomputing either.
// Not `Eq`: the negative-material floors are measured in seconds, and a
// duration is a float here for the same reason it is in the capture gate.
#[derive(Debug, Clone, PartialEq, Serialize)]
#[serde(tag = "reason", rename_all = "kebab-case")]
pub enum EnrollmentShortfall {
    /// A sitting does not record when it was captured, so nothing establishes
    /// it as separate from the others.
    SittingTimeUnrecorded,
    TooFewSittings {
        have: usize,
        need: usize,
    },
    /// Two sittings closer together than the enforced gap. Reported in whole
    /// minutes, matching the canonical message.
    SittingsTooClose {
        gap_minutes: u64,
        need_minutes: u64,
    },
    /// A sitting record repeats a recording already counted: pieces of a single
    /// recording rather than separate sittings.
    RepeatedSittingRecording {
        audio_sha256: String,
    },
    /// Fewer scorable operator segments than the centroid floor.
    TooFewScorableSegments {
        have: u32,
        need: u32,
    },
    /// The pooled held-out sample cannot express two offered targets, and one
    /// option is not a choice the operating-point screen may present.
    HeldOutCannotOfferTwoChoices {
        held_out: u32,
        need: u32,
    },
    NegativeSampleMissing,
    NegativeSourceNotPermitted {
        source_class: String,
    },
    RepeatedNegativeRecording {
        audio_sha256: String,
    },
    NegativeSpeechTooShort {
        have_seconds: f64,
        need_seconds: f64,
    },
    NegativeSegmentsTooFew {
        have: u32,
        need: u32,
    },
}

impl EnrollmentShortfall {
    /// The operator-facing sentence. It states what to do, not how complete the
    /// work is, and it never quotes meeting or profile content.
    #[must_use]
    pub fn sentence(&self) -> String {
        match self {
            Self::SittingTimeUnrecorded => "One voice session does not record when it was \
                captured, so nothing establishes it as a separate session. Record it again."
                .to_string(),
            Self::TooFewSittings { have, need } => format!(
                "{have} of {need} voice sessions recorded. A threshold needs speech from \
                 more than one session before it means anything."
            ),
            Self::SittingsTooClose {
                gap_minutes,
                need_minutes,
            } => format!(
                "Two voice sessions were recorded {gap_minutes} minutes apart. Return at \
                 least {need_minutes} minutes after the first one — a different day is \
                 ideal — and record again."
            ),
            Self::RepeatedSittingRecording { .. } => "The same recording was supplied as \
                more than one voice session. Pieces of one recording are not separate \
                sessions, and carry none of the session-to-session variation the second \
                one is for. Record another session instead."
                .to_string(),
            Self::TooFewScorableSegments { have, need } => format!(
                "One voice session holds {have} judgeable speech segments and each needs \
                 {need}. Only speech of at least {MIN_SCORABLE_SECONDS:.0} seconds counts, \
                 so record that session again and talk normally throughout."
            ),
            Self::HeldOutCannotOfferTwoChoices { held_out, need } => format!(
                "{held_out} judgeable speech segments across your sessions can express at \
                 most one measured option, and setup offers a choice rather than a single \
                 setting; {need} are needed. Record a longer session."
            ),
            Self::NegativeSampleMissing => format!(
                "Supply permitted speech that is not you: at least \
                 {MIN_NEGATIVE_SCORABLE_SECONDS:.0} seconds across at least \
                 {MIN_NEGATIVE_SCORABLE_SEGMENTS} segments. Use public-domain or licensed \
                 playback, or a person who knowingly consents to make this recording. \
                 Without it the threshold says how much of you it drops and nothing about \
                 what it lets through."
            ),
            Self::NegativeSourceNotPermitted { source_class } => format!(
                "A comparison recording is labelled {source_class:?}, which is not a \
                 permitted source. Use public-domain or licensed playback, or a person \
                 who knowingly consents. Do not use a private conversation, an unaware \
                 bystander, or unlicensed program audio."
            ),
            Self::RepeatedNegativeRecording { .. } => "The same comparison recording was \
                supplied more than once. One recording cannot raise the evidence by \
                appearing twice. Supply different permitted speech."
                .to_string(),
            Self::NegativeSpeechTooShort {
                have_seconds,
                need_seconds,
            } => format!(
                "{have_seconds:.0} of {need_seconds:.0} seconds of judgeable comparison \
                 speech. Supply more permitted speech that is not you."
            ),
            Self::NegativeSegmentsTooFew { have, need } => format!(
                "{have} of {need} comparison speech segments. One long passage cannot \
                 stand in for a spread of separate ones."
            ),
        }
    }
}

/// An observation worth stating that is not a refusal.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(tag = "advisory", rename_all = "kebab-case")]
pub enum EnrollmentAdvisory {
    /// Above the resolvable floor but below `THIN_HELD_OUT_SEGMENTS`, where a
    /// sample quantile still moves by more than a hundredth when one
    /// observation is added or removed.
    HeldOutThin { held_out: u32, comfortable: u32 },
}

impl EnrollmentAdvisory {
    #[must_use]
    pub fn sentence(&self) -> String {
        match self {
            Self::HeldOutThin {
                held_out,
                comfortable,
            } => format!(
                "{held_out} held-out speech segments is enough to offer a choice but is \
                 still thin; around {comfortable} is where the measurement stops moving. \
                 Another session would make the offered rates steadier."
            ),
        }
    }
}

/// What this evaluation deliberately cannot decide.
///
/// Rendered beside the state so a surface can never imply that clearing every
/// deterministic floor completes enrolment.
pub const GUIDED_ENROLLMENT_GATES: [&str; 3] = [
    "Recording a dedicated voice session is an operator action on real hardware; this \
     Preview does not record one yet.",
    "The measured options come from your own calibration at runtime, and no option is \
     selected by default.",
    "Building a profile is refused again by the canonical loader before anything is \
     stored, so clearing these requirements is not admission.",
];

/// The result of evaluating one accumulated evidence set.
#[derive(Debug, Clone, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct GuidedEnrollmentStatus {
    pub state: GuidedEnrollmentState,
    /// The single next thing to do, or `None` once every deterministic floor is
    /// met and the remaining work is an operator decision. Carried as a field
    /// rather than computed by the reader, so the surface cannot pick its own
    /// ordering and quietly ask for the larger errand first.
    pub next_step: Option<String>,
    pub shortfalls: Vec<EnrollmentShortfall>,
    pub advisories: Vec<EnrollmentAdvisory>,
    pub sittings_recorded: usize,
    pub scorable_operator_segments: u32,
    pub negative_scorable_segments: u32,
    pub negative_scorable_seconds: f64,
    pub gates: &'static [&'static str],
}

/// Evaluates accumulated evidence against the enforced enrolment contract.
///
/// Ordering is deliberate: operator-material shortfalls are reported before
/// negative-material ones, because asking someone to find permitted speech that
/// is not them is the larger errand and should not be raised while their own
/// sittings are still short.
#[must_use]
pub fn evaluate_enrollment_evidence(evidence: &EnrollmentEvidence) -> GuidedEnrollmentStatus {
    let mut shortfalls = Vec::new();
    let mut advisories = Vec::new();

    let sittings_recorded = evidence.sittings.len();
    let scorable_operator_segments = evidence.sittings.iter().fold(0_u32, |total, sitting| {
        total.saturating_add(sitting.scorable_segments)
    });

    // A sitting with no recorded capture time cannot be ordered against the
    // others, so the gap check below would be meaningless rather than merely
    // unmet. Report it and stop reasoning about gaps.
    let every_sitting_timed = evidence
        .sittings
        .iter()
        .all(|sitting| sitting.captured_at_epoch.is_some());
    if !every_sitting_timed {
        shortfalls.push(EnrollmentShortfall::SittingTimeUnrecorded);
    }

    if sittings_recorded < MIN_SITTINGS {
        shortfalls.push(EnrollmentShortfall::TooFewSittings {
            have: sittings_recorded,
            need: MIN_SITTINGS,
        });
    }

    // Any repeat is refused, not merely a set that collapses to one recording.
    // `preflight_calibrate` treats `--calibrate` and `--against` identically —
    // "one recording cannot count as two sittings" — and it is the producing
    // boundary, so it is stricter than `verify_provenance`'s distinct-count
    // rule. A count-based check would pass `[A, A, B]`, tell the operator every
    // requirement was met, and let the build refuse afterwards.
    let mut seen_sitting_recordings: Vec<&str> = Vec::new();
    for sitting in &evidence.sittings {
        let digest = sitting.audio_sha256.as_str();
        if seen_sitting_recordings.contains(&digest) {
            shortfalls.push(EnrollmentShortfall::RepeatedSittingRecording {
                audio_sha256: sitting.audio_sha256.clone(),
            });
        } else {
            seen_sitting_recordings.push(digest);
        }
    }

    if every_sitting_timed && sittings_recorded >= MIN_SITTINGS {
        let mut stamps: Vec<u64> = evidence
            .sittings
            .iter()
            .filter_map(|sitting| sitting.captured_at_epoch)
            .collect();
        stamps.sort_unstable();
        for pair in stamps.windows(2) {
            let gap = pair[1] - pair[0];
            if gap < MIN_SITTING_GAP_SECONDS {
                shortfalls.push(EnrollmentShortfall::SittingsTooClose {
                    gap_minutes: gap / 60,
                    need_minutes: MIN_SITTING_GAP_SECONDS / 60,
                });
                break;
            }
        }
    }

    // The floor is per recording, not across the set. `run_calibrate` refuses
    // any single sitting with `len(emb) <= MIN_ENROLL_SEGMENTS`, because a
    // leave-one-out pass enrols on `n - 1` and a sitting at the enrolment
    // minimum fails inside the loop instead. Summing would let one rich sitting
    // carry a recording the canonical CLI rejects outright.
    let thinnest_sitting = evidence
        .sittings
        .iter()
        .map(|sitting| sitting.scorable_segments)
        .min();
    if thinnest_sitting.is_some_and(|smallest| smallest < MIN_SCORABLE_SEGMENTS_PER_SITTING) {
        shortfalls.push(EnrollmentShortfall::TooFewScorableSegments {
            have: thinnest_sitting.unwrap_or_default(),
            need: MIN_SCORABLE_SEGMENTS_PER_SITTING,
        });
    }

    // Held-out sample size is the *pooled* leave-one-sitting-out score count.
    // `leave_one_sitting_out_scores` extends one list inside its per-sitting
    // loop, so every sitting's segments land in the same array, and
    // `operating_point_choices` tests `len(operator_scores)` against
    // `min_resolvable(target)`. Bounding by the smallest sitting instead would
    // report a shortfall where the loader raises no refusal.
    //
    // Two choices are required, not one: `operating_point_choices` refuses when
    // fewer than two distinct feasible points survive, so resolving only the
    // loosest target is already a refusal. This is the necessary count; whether
    // two points stay *distinct* depends on measured costs that only the
    // operator's own calibration produces, so the loader still decides.
    if sittings_recorded >= MIN_SITTINGS {
        let held_out = scorable_operator_segments;
        if held_out < MIN_HELD_OUT_FOR_TWO_CHOICES {
            shortfalls.push(EnrollmentShortfall::HeldOutCannotOfferTwoChoices {
                held_out,
                need: MIN_HELD_OUT_FOR_TWO_CHOICES,
            });
        } else if held_out < THIN_HELD_OUT_SEGMENTS {
            advisories.push(EnrollmentAdvisory::HeldOutThin {
                held_out,
                comfortable: THIN_HELD_OUT_SEGMENTS,
            });
        }
    }

    let operator_material_is_sufficient = shortfalls.is_empty();

    let mut negative_scorable_segments = 0_u32;
    let mut negative_scorable_seconds = 0.0_f64;
    let mut seen_negative_recordings: Vec<&str> = Vec::new();
    for source in &evidence.negative_sources {
        if !PERMITTED_NEGATIVE_SOURCE_CLASSES.contains(&source.source_class.as_str()) {
            shortfalls.push(EnrollmentShortfall::NegativeSourceNotPermitted {
                source_class: source.source_class.clone(),
            });
            continue;
        }
        if seen_negative_recordings.contains(&source.audio_sha256.as_str()) {
            shortfalls.push(EnrollmentShortfall::RepeatedNegativeRecording {
                audio_sha256: source.audio_sha256.clone(),
            });
            continue;
        }
        seen_negative_recordings.push(source.audio_sha256.as_str());
        negative_scorable_segments =
            negative_scorable_segments.saturating_add(source.scorable_segments);
        negative_scorable_seconds += source.scorable_seconds;
    }

    if evidence.negative_sources.is_empty() {
        shortfalls.push(EnrollmentShortfall::NegativeSampleMissing);
    } else {
        if negative_scorable_seconds < MIN_NEGATIVE_SCORABLE_SECONDS {
            shortfalls.push(EnrollmentShortfall::NegativeSpeechTooShort {
                have_seconds: negative_scorable_seconds,
                need_seconds: MIN_NEGATIVE_SCORABLE_SECONDS,
            });
        }
        if negative_scorable_segments < MIN_NEGATIVE_SCORABLE_SEGMENTS {
            shortfalls.push(EnrollmentShortfall::NegativeSegmentsTooFew {
                have: negative_scorable_segments,
                need: MIN_NEGATIVE_SCORABLE_SEGMENTS,
            });
        }
    }

    let state = guided_state(
        &shortfalls,
        sittings_recorded,
        operator_material_is_sufficient,
    );

    GuidedEnrollmentStatus {
        state,
        next_step: shortfalls.first().map(EnrollmentShortfall::sentence),
        shortfalls,
        advisories,
        sittings_recorded,
        scorable_operator_segments,
        negative_scorable_segments,
        negative_scorable_seconds,
        gates: &GUIDED_ENROLLMENT_GATES,
    }
}

fn guided_state(
    shortfalls: &[EnrollmentShortfall],
    sittings_recorded: usize,
    operator_material_is_sufficient: bool,
) -> GuidedEnrollmentState {
    if shortfalls.is_empty() {
        return GuidedEnrollmentState::ChoosingOperatingPoint;
    }
    // A repeated recording, an unrecorded capture time, an impermissible source
    // or a duplicated negative are not shortfalls that another sitting closes:
    // the evidence already on hand cannot become a supported profile.
    let refused = shortfalls.iter().any(|shortfall| {
        matches!(
            shortfall,
            EnrollmentShortfall::SittingTimeUnrecorded
                | EnrollmentShortfall::RepeatedSittingRecording { .. }
                | EnrollmentShortfall::NegativeSourceNotPermitted { .. }
                | EnrollmentShortfall::RepeatedNegativeRecording { .. }
        )
    });
    if refused {
        return GuidedEnrollmentState::Refused;
    }
    if operator_material_is_sufficient {
        return GuidedEnrollmentState::NeedsOtherVoice;
    }
    match sittings_recorded {
        0 => GuidedEnrollmentState::Blocked,
        1 => GuidedEnrollmentState::ResumeAfterGap,
        _ => GuidedEnrollmentState::SecondSittingReview,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sitting(captured_at_epoch: u64, digest: &str, segments: u32) -> SittingEvidence {
        SittingEvidence {
            captured_at_epoch: Some(captured_at_epoch),
            audio_sha256: digest.to_string(),
            scorable_segments: segments,
            scorable_seconds: f64::from(segments) * 3.0,
        }
    }

    fn permitted_negative(digest: &str, segments: u32, seconds: f64) -> NegativeSourceEvidence {
        NegativeSourceEvidence {
            source_class: "public-or-licensed".to_string(),
            audio_sha256: digest.to_string(),
            scorable_segments: segments,
            scorable_seconds: seconds,
        }
    }

    /// Two sittings exactly one hour apart with comfortable material and a
    /// permitted negative sample: every deterministic floor met.
    fn complete_evidence() -> EnrollmentEvidence {
        EnrollmentEvidence {
            sittings: vec![sitting(0, "a", 40), sitting(3_600, "b", 40)],
            negative_sources: vec![permitted_negative("n", 24, 72.0)],
        }
    }

    #[test]
    fn enforced_constants_match_the_capture_gate() {
        // Pinned against `spike/speaker_gate.py`. These are re-derived at the
        // canonical source rather than from § I's restatement of it; a drift
        // here means the surface would guide an operator toward a build the
        // loader will refuse.
        assert_eq!(MIN_SITTING_GAP_SECONDS, 3_600, "MIN_SITTING_GAP_S");
        assert_eq!(MIN_ENROLL_SEGMENTS, 3, "MIN_ENROLL_SEGMENTS");
        assert!(
            (MIN_SCORABLE_SECONDS - 2.0).abs() < f64::EPSILON,
            "MIN_SCORABLE_S"
        );
        assert!(
            (MIN_NEGATIVE_SCORABLE_SECONDS - 60.0).abs() < f64::EPSILON,
            "MIN_NEGATIVE_SCORABLE_SECONDS"
        );
        assert_eq!(
            MIN_NEGATIVE_SCORABLE_SEGMENTS, 20,
            "MIN_NEGATIVE_SCORABLE_SEGMENTS"
        );
        assert_eq!(THIN_HELD_OUT_SEGMENTS, 30, "THIN_HELD_OUT");
        // `run_calibrate` refuses `len(emb) <= MIN_ENROLL_SEGMENTS` per recording.
        assert_eq!(MIN_SCORABLE_SEGMENTS_PER_SITTING, 4);
        // `operating_point_choices` refuses fewer than two distinct points, and
        // the two loosest targets need ceil(1/0.20)=5 and ceil(1/0.10)=10.
        let mut requirements: Vec<u32> = OPERATING_POINT_TARGETS
            .iter()
            .filter_map(|target| min_resolvable_held_out(*target))
            .collect();
        requirements.sort_unstable();
        assert_eq!(requirements[0], 5);
        assert_eq!(requirements[1], MIN_HELD_OUT_FOR_TWO_CHOICES);
        assert_eq!(
            OPERATING_POINT_TARGETS,
            [0.01, 0.02, 0.05, 0.10, 0.20],
            "OPERATING_POINT_TARGETS"
        );
        assert_eq!(
            PERMITTED_NEGATIVE_SOURCE_CLASSES,
            ["public-or-licensed", "consenting-person"],
            "NEGATIVE_SOURCE_CLASSES"
        );
    }

    /// `as_str` and the serde derive are two spellings of one mapping, and the
    /// UI reads the serialized one. Pinning them together stops a silent
    /// divergence, and pins both against § I's state names, which the screen
    /// inventory and this module have to keep agreeing on.
    #[test]
    fn state_names_match_between_serde_and_as_str() {
        let states = [
            (GuidedEnrollmentState::Blocked, "blocked"),
            (GuidedEnrollmentState::ResumeAfterGap, "resume-after-gap"),
            (
                GuidedEnrollmentState::SecondSittingReview,
                "second-sitting-review",
            ),
            (GuidedEnrollmentState::NeedsOtherVoice, "needs-other-voice"),
            (
                GuidedEnrollmentState::ChoosingOperatingPoint,
                "choosing-operating-point",
            ),
            (GuidedEnrollmentState::Refused, "refused"),
        ];
        for (state, expected) in states {
            assert_eq!(state.as_str(), expected);
            assert_eq!(
                serde_json::to_value(state).unwrap(),
                serde_json::Value::String(expected.to_string()),
                "serde and as_str must not diverge for {expected}"
            );
        }
    }

    #[test]
    fn min_resolvable_matches_ceil_of_one_over_target() {
        assert_eq!(min_resolvable_held_out(0.01), Some(100));
        assert_eq!(min_resolvable_held_out(0.02), Some(50));
        assert_eq!(min_resolvable_held_out(0.05), Some(20));
        assert_eq!(min_resolvable_held_out(0.10), Some(10));
        assert_eq!(min_resolvable_held_out(0.20), Some(5));
        assert_eq!(min_resolvable_held_out(0.0), None);
        assert_eq!(min_resolvable_held_out(-0.5), None);
        assert_eq!(min_resolvable_held_out(f64::NAN), None);
    }

    #[test]
    fn no_evidence_is_blocked_and_asks_for_the_first_sitting() {
        let status = evaluate_enrollment_evidence(&EnrollmentEvidence::default());
        assert_eq!(status.state, GuidedEnrollmentState::Blocked);
        assert_eq!(status.sittings_recorded, 0);
        // The first thing said is about sittings, not about finding another
        // person's voice.
        assert!(matches!(
            status.shortfalls.first(),
            Some(EnrollmentShortfall::TooFewSittings { have: 0, need: 2 })
        ));
        assert!(status.next_step.is_some());
    }

    #[test]
    fn one_sitting_asks_the_operator_to_return_after_the_gap() {
        let evidence = EnrollmentEvidence {
            sittings: vec![sitting(0, "a", 40)],
            negative_sources: Vec::new(),
        };
        let status = evaluate_enrollment_evidence(&evidence);
        assert_eq!(status.state, GuidedEnrollmentState::ResumeAfterGap);
        assert_eq!(status.sittings_recorded, 1);
    }

    #[test]
    fn exactly_one_hour_apart_passes_because_the_gate_refuses_only_below_it() {
        // `speaker_gate._sitting_problems` refuses `gap < MIN_SITTING_GAP_S`,
        // so the boundary itself is admissible. § I says the same in prose;
        // this pins the code.
        let status = evaluate_enrollment_evidence(&complete_evidence());
        assert!(
            !status
                .shortfalls
                .iter()
                .any(|s| matches!(s, EnrollmentShortfall::SittingsTooClose { .. })),
            "exactly 3600s must not be reported as too close: {:?}",
            status.shortfalls
        );
        assert_eq!(status.state, GuidedEnrollmentState::ChoosingOperatingPoint);
    }

    #[test]
    fn one_second_under_the_hour_is_refused_with_the_observed_gap() {
        let evidence = EnrollmentEvidence {
            sittings: vec![sitting(0, "a", 40), sitting(3_599, "b", 40)],
            negative_sources: vec![permitted_negative("n", 24, 72.0)],
        };
        let status = evaluate_enrollment_evidence(&evidence);
        assert_eq!(status.state, GuidedEnrollmentState::SecondSittingReview);
        assert!(
            status
                .shortfalls
                .contains(&EnrollmentShortfall::SittingsTooClose {
                    gap_minutes: 59,
                    need_minutes: 60,
                })
        );
    }

    #[test]
    fn two_pieces_of_one_recording_are_refused_rather_than_counted() {
        // The failure mode § I names: chunking one recording reads as satisfied
        // and carries none of the session-to-session variation the plural is
        // for. Same digest twice, an hour apart on paper.
        let evidence = EnrollmentEvidence {
            sittings: vec![sitting(0, "same", 40), sitting(7_200, "same", 40)],
            negative_sources: vec![permitted_negative("n", 24, 72.0)],
        };
        let status = evaluate_enrollment_evidence(&evidence);
        assert_eq!(status.state, GuidedEnrollmentState::Refused);
        assert!(
            status
                .shortfalls
                .contains(&EnrollmentShortfall::RepeatedSittingRecording {
                    audio_sha256: "same".to_string(),
                })
        );
    }

    /// `preflight_calibrate` refuses *any* repeated `--calibrate` digest, not
    /// only a set that collapses to one recording. A distinct-count check would
    /// pass this and report every requirement met, leaving the build to refuse
    /// afterwards — the under-report this module exists to prevent. It would
    /// also make `Refused` escapable by adding a third distinct sitting.
    #[test]
    fn a_repeated_sitting_is_refused_even_beside_a_distinct_third() {
        let evidence = EnrollmentEvidence {
            sittings: vec![
                sitting(0, "a", 40),
                sitting(7_200, "a", 40),
                sitting(14_400, "b", 40),
            ],
            negative_sources: vec![permitted_negative("n", 24, 72.0)],
        };
        let status = evaluate_enrollment_evidence(&evidence);
        assert_eq!(status.state, GuidedEnrollmentState::Refused);
        assert!(
            status
                .shortfalls
                .contains(&EnrollmentShortfall::RepeatedSittingRecording {
                    audio_sha256: "a".to_string(),
                })
        );
        assert!(status.next_step.is_some());
    }

    #[test]
    fn an_untimed_sitting_is_refused_and_suppresses_gap_reasoning() {
        let evidence = EnrollmentEvidence {
            sittings: vec![
                SittingEvidence {
                    captured_at_epoch: None,
                    audio_sha256: "a".to_string(),
                    scorable_segments: 40,
                    scorable_seconds: 120.0,
                },
                sitting(3_600, "b", 40),
            ],
            negative_sources: vec![permitted_negative("n", 24, 72.0)],
        };
        let status = evaluate_enrollment_evidence(&evidence);
        assert_eq!(status.state, GuidedEnrollmentState::Refused);
        assert!(
            status
                .shortfalls
                .contains(&EnrollmentShortfall::SittingTimeUnrecorded)
        );
        assert!(
            !status
                .shortfalls
                .iter()
                .any(|s| matches!(s, EnrollmentShortfall::SittingsTooClose { .. })),
            "an unordered sitting makes the gap meaningless, not merely unmet"
        );
    }

    #[test]
    fn sufficient_operator_material_without_a_negative_sample_needs_another_voice() {
        let evidence = EnrollmentEvidence {
            sittings: vec![sitting(0, "a", 40), sitting(3_600, "b", 40)],
            negative_sources: Vec::new(),
        };
        let status = evaluate_enrollment_evidence(&evidence);
        assert_eq!(status.state, GuidedEnrollmentState::NeedsOtherVoice);
        assert!(
            status
                .shortfalls
                .contains(&EnrollmentShortfall::NegativeSampleMissing)
        );
    }

    #[test]
    fn both_negative_floors_are_reported_independently() {
        // Duration and segment count are separate judgements, so one long
        // passage clears seconds while failing segments.
        let evidence = EnrollmentEvidence {
            sittings: vec![sitting(0, "a", 40), sitting(3_600, "b", 40)],
            negative_sources: vec![permitted_negative("n", 4, 90.0)],
        };
        let status = evaluate_enrollment_evidence(&evidence);
        assert!(
            status
                .shortfalls
                .contains(&EnrollmentShortfall::NegativeSegmentsTooFew { have: 4, need: 20 })
        );
        assert!(
            !status
                .shortfalls
                .iter()
                .any(|s| matches!(s, EnrollmentShortfall::NegativeSpeechTooShort { .. })),
            "90s clears the duration floor"
        );
    }

    #[test]
    fn a_repeated_negative_recording_cannot_inflate_either_floor() {
        let evidence = EnrollmentEvidence {
            sittings: vec![sitting(0, "a", 40), sitting(3_600, "b", 40)],
            negative_sources: vec![
                permitted_negative("n", 24, 72.0),
                permitted_negative("n", 24, 72.0),
            ],
        };
        let status = evaluate_enrollment_evidence(&evidence);
        assert_eq!(status.state, GuidedEnrollmentState::Refused);
        // The duplicate contributed nothing to the running totals.
        assert_eq!(status.negative_scorable_segments, 24);
        assert!((status.negative_scorable_seconds - 72.0).abs() < f64::EPSILON);
    }

    #[test]
    fn an_impermissible_negative_source_is_refused_and_never_counted() {
        let evidence = EnrollmentEvidence {
            sittings: vec![sitting(0, "a", 40), sitting(3_600, "b", 40)],
            negative_sources: vec![NegativeSourceEvidence {
                source_class: "overheard".to_string(),
                audio_sha256: "n".to_string(),
                scorable_segments: 40,
                scorable_seconds: 200.0,
            }],
        };
        let status = evaluate_enrollment_evidence(&evidence);
        assert_eq!(status.state, GuidedEnrollmentState::Refused);
        assert_eq!(status.negative_scorable_segments, 0);
        assert!(status.negative_scorable_seconds.abs() < f64::EPSILON);
    }

    /// `leave_one_sitting_out_scores` extends one array inside its per-sitting
    /// loop, so the held-out sample is every sitting pooled — not the smallest
    /// fold. Bounding by the smallest sitting would report a shortfall against
    /// material the loader accepts, which this module's contract forbids.
    #[test]
    fn held_out_size_is_the_pooled_score_count_across_sittings() {
        let evidence = EnrollmentEvidence {
            sittings: vec![sitting(0, "a", 40), sitting(3_600, "b", 4)],
            negative_sources: vec![permitted_negative("n", 24, 72.0)],
        };
        let status = evaluate_enrollment_evidence(&evidence);
        assert_eq!(status.scorable_operator_segments, 44);
        assert!(
            !status.shortfalls.iter().any(|shortfall| matches!(
                shortfall,
                EnrollmentShortfall::HeldOutCannotOfferTwoChoices { .. }
            )),
            "44 pooled segments resolve several targets: {:?}",
            status.shortfalls
        );
        assert_eq!(status.state, GuidedEnrollmentState::ChoosingOperatingPoint);
    }

    /// One measured option is not a choice. `operating_point_choices` refuses
    /// when fewer than two distinct feasible points survive, so a pooled count
    /// that resolves only the loosest target is already a refusal.
    #[test]
    fn a_pooled_sample_resolving_only_the_loosest_target_is_reported() {
        let evidence = EnrollmentEvidence {
            sittings: vec![sitting(0, "a", 5), sitting(3_600, "b", 4)],
            negative_sources: vec![permitted_negative("n", 24, 72.0)],
        };
        let status = evaluate_enrollment_evidence(&evidence);
        assert_eq!(status.scorable_operator_segments, 9);
        assert!(
            status
                .shortfalls
                .contains(&EnrollmentShortfall::HeldOutCannotOfferTwoChoices {
                    held_out: 9,
                    need: 10,
                })
        );
    }

    /// The scorable floor is per recording, not a sum: `run_calibrate` refuses
    /// any single recording at or below `MIN_ENROLL_SEGMENTS`, so one rich
    /// sitting cannot carry a thin one past it.
    #[test]
    fn a_single_thin_sitting_is_reported_even_beside_a_rich_one() {
        let thin = EnrollmentEvidence {
            sittings: vec![sitting(0, "a", 40), sitting(3_600, "b", 2)],
            negative_sources: vec![permitted_negative("n", 24, 72.0)],
        };
        assert!(
            evaluate_enrollment_evidence(&thin)
                .shortfalls
                .contains(&EnrollmentShortfall::TooFewScorableSegments { have: 2, need: 4 })
        );
        // Exactly MIN_ENROLL_SEGMENTS is still refused; the CLI asks for one more.
        let boundary = EnrollmentEvidence {
            sittings: vec![sitting(0, "a", 40), sitting(3_600, "b", 3)],
            negative_sources: vec![permitted_negative("n", 24, 72.0)],
        };
        assert!(
            evaluate_enrollment_evidence(&boundary)
                .shortfalls
                .contains(&EnrollmentShortfall::TooFewScorableSegments { have: 3, need: 4 })
        );
        let admissible = EnrollmentEvidence {
            sittings: vec![sitting(0, "a", 40), sitting(3_600, "b", 4)],
            negative_sources: vec![permitted_negative("n", 24, 72.0)],
        };
        assert!(
            !evaluate_enrollment_evidence(&admissible)
                .shortfalls
                .iter()
                .any(|shortfall| matches!(
                    shortfall,
                    EnrollmentShortfall::TooFewScorableSegments { .. }
                ))
        );
    }

    #[test]
    fn a_thin_pooled_sample_is_advisory_and_not_a_refusal() {
        let evidence = EnrollmentEvidence {
            sittings: vec![sitting(0, "a", 10), sitting(3_600, "b", 8)],
            negative_sources: vec![permitted_negative("n", 24, 72.0)],
        };
        let status = evaluate_enrollment_evidence(&evidence);
        assert_eq!(status.scorable_operator_segments, 18);
        assert_eq!(status.state, GuidedEnrollmentState::ChoosingOperatingPoint);
        assert!(status.shortfalls.is_empty());
        assert!(
            status
                .advisories
                .contains(&EnrollmentAdvisory::HeldOutThin {
                    held_out: 18,
                    comfortable: 30,
                })
        );
    }

    #[test]
    fn clearing_every_floor_still_reports_the_gates_it_cannot_decide() {
        let status = evaluate_enrollment_evidence(&complete_evidence());
        assert_eq!(status.state, GuidedEnrollmentState::ChoosingOperatingPoint);
        assert!(status.next_step.is_none());
        // Nothing here may read as admission: the operator decision and the
        // canonical loader both still stand between this and a stored profile.
        assert_eq!(status.gates.len(), GUIDED_ENROLLMENT_GATES.len());
        assert!(!status.gates.is_empty());
    }

    #[test]
    fn every_shortfall_and_advisory_renders_a_content_free_sentence() {
        let shortfalls = [
            EnrollmentShortfall::SittingTimeUnrecorded,
            EnrollmentShortfall::TooFewSittings { have: 0, need: 2 },
            EnrollmentShortfall::SittingsTooClose {
                gap_minutes: 12,
                need_minutes: 60,
            },
            EnrollmentShortfall::RepeatedSittingRecording {
                audio_sha256: "a".to_string(),
            },
            EnrollmentShortfall::TooFewScorableSegments { have: 2, need: 4 },
            EnrollmentShortfall::HeldOutCannotOfferTwoChoices {
                held_out: 9,
                need: 10,
            },
            EnrollmentShortfall::NegativeSampleMissing,
            EnrollmentShortfall::NegativeSourceNotPermitted {
                source_class: "overheard".to_string(),
            },
            EnrollmentShortfall::RepeatedNegativeRecording {
                audio_sha256: "n".to_string(),
            },
            EnrollmentShortfall::NegativeSpeechTooShort {
                have_seconds: 12.0,
                need_seconds: 60.0,
            },
            EnrollmentShortfall::NegativeSegmentsTooFew { have: 4, need: 20 },
        ];
        for shortfall in &shortfalls {
            let sentence = shortfall.sentence();
            assert!(!sentence.is_empty());
            // A percentage would be the progress bar § I rules out.
            assert!(
                !sentence.contains('%'),
                "shortfall must state the enforced term, not a completion share: {sentence}"
            );
        }
        // The digest of a private recording must never reach the operator
        // sentence, because it identifies material this surface never displays.
        let repeated = EnrollmentShortfall::RepeatedNegativeRecording {
            audio_sha256: "0123456789abcdef".to_string(),
        };
        assert!(!repeated.sentence().contains("0123456789abcdef"));

        let advisory = EnrollmentAdvisory::HeldOutThin {
            held_out: 8,
            comfortable: 30,
        };
        assert!(!advisory.sentence().is_empty());
    }

    #[test]
    fn evaluation_is_deterministic_and_order_independent_for_sittings() {
        let forward = complete_evidence();
        let mut reversed = forward.clone();
        reversed.sittings.reverse();
        assert_eq!(
            evaluate_enrollment_evidence(&forward),
            evaluate_enrollment_evidence(&reversed)
        );
    }
}

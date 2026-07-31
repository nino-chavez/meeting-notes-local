"""One deterministic contract for capture integrity and its persisted evidence."""

from __future__ import annotations

import math

RATE = 16_000
MIN_LEG_SAMPLES = RATE // 5
MAX_CLOCK_DRIFT_PPM = 50
# The two streams have begun as much as 1.7 s apart in measured captures. Round that
# observed bound up to the next 200 ms capture block; this is acquisition skew, not a
# meeting-quality duration threshold.
MAX_CAPTURE_STARTUP_SKEW_SAMPLES = 2 * RATE
SCHEMA = "capture-health/1"
TRANSCRIPT_SCHEMA = "capture-transcript/1"
UNKNOWN_WARNING = (
    "capture integrity is unknown: this legacy capture transcript predates "
    "persisted capture-health evidence. Treat it as retained evidence, not a "
    "complete meeting record."
)


def build(
    *,
    mic_samples: int,
    system_samples: int,
    capture_elapsed_samples: int,
    dropouts: dict[str, list[dict]],
    tap_errors: list[dict],
    transcription_requested: bool,
    transcript_written: bool,
) -> dict:
    """Build the evidence required to call a dual-leg capture usable.

    These are integrity floors, not product-quality thresholds. Loudness, word
    count, note quality and a minimum meeting length deliberately do not decide this
    verdict. Whether both legs cover the wall span that was actually captured does.
    """
    if (
        isinstance(mic_samples, bool)
        or not isinstance(mic_samples, int)
        or isinstance(system_samples, bool)
        or not isinstance(system_samples, int)
        or isinstance(capture_elapsed_samples, bool)
        or not isinstance(capture_elapsed_samples, int)
    ):
        raise ValueError("capture and leg sample counts must be integers")
    if capture_elapsed_samples < 0:
        raise ValueError("capture elapsed samples cannot be negative")
    if not isinstance(dropouts, dict):
        raise ValueError("capture dropouts must be grouped by leg")
    if not isinstance(tap_errors, list):
        raise ValueError("tap_errors must be a list")
    if not isinstance(transcription_requested, bool) or not isinstance(
        transcript_written, bool
    ):
        raise ValueError("transcription evidence must be boolean")
    leg_dropouts = {}
    for leg_name in ("mic", "system"):
        events = dropouts.get(leg_name)
        if not isinstance(events, list):
            raise ValueError(f"{leg_name} dropouts must be a list")
        if not all(isinstance(event, dict) for event in events):
            raise ValueError(f"{leg_name} dropout evidence must contain objects")
        leg_dropouts[leg_name] = events
    if not all(isinstance(event, dict) for event in tap_errors):
        raise ValueError("tap error evidence must contain objects")

    blockers = []
    if mic_samples <= 0:
        blockers.append({
            "code": "no_samples",
            "leg": "mic",
            "detail": "the microphone leg produced no samples",
        })
    elif mic_samples < MIN_LEG_SAMPLES:
        blockers.append({
            "code": "incomplete_capture_block",
            "leg": "mic",
            "samples": mic_samples,
            "minimum_samples": MIN_LEG_SAMPLES,
            "detail": (
                "the microphone leg ended before one configured capture block "
                f"({mic_samples} of {MIN_LEG_SAMPLES} samples)"
            ),
        })
    if system_samples <= 0:
        blockers.append({
            "code": "no_samples",
            "leg": "system",
            "detail": "the system leg produced no samples",
        })
    elif system_samples < MIN_LEG_SAMPLES:
        blockers.append({
            "code": "incomplete_capture_block",
            "leg": "system",
            "samples": system_samples,
            "minimum_samples": MIN_LEG_SAMPLES,
            "detail": (
                "the system leg ended before one configured capture block "
                f"({system_samples} of {MIN_LEG_SAMPLES} samples)"
            ),
        })
    for leg_name in ("mic", "system"):
        events = leg_dropouts[leg_name]
        if events:
            blockers.append({
                "code": "driver_dropout",
                "leg": leg_name,
                "count": len(events),
                "detail": f"{leg_name} reported lost samples, so its timeline has gaps",
            })
    if tap_errors:
        blockers.append({
            "code": "tap_error",
            "leg": "system",
            "count": len(tap_errors),
            "detail": "the system-audio tap reported an error or fatal event",
        })
    if transcription_requested and not transcript_written:
        blockers.append({
            "code": "transcript_missing",
            "detail": "transcription was requested but no transcript artifact was written",
        })
    allowed_leg_delta = MAX_CAPTURE_STARTUP_SKEW_SAMPLES + math.ceil(
        max(mic_samples, system_samples, 0)
        * MAX_CLOCK_DRIFT_PPM
        / 1_000_000
    )
    leg_delta = abs(mic_samples - system_samples)
    if (
        mic_samples >= MIN_LEG_SAMPLES
        and system_samples >= MIN_LEG_SAMPLES
        and leg_delta > allowed_leg_delta
    ):
        shorter_leg = "mic" if mic_samples < system_samples else "system"
        blockers.append({
            "code": "leg_span_mismatch",
            "leg": shorter_leg,
            "difference_samples": leg_delta,
            "allowed_difference_samples": allowed_leg_delta,
            "detail": (
                f"the {shorter_leg} leg ended materially before the other leg "
                f"({leg_delta} samples apart; at most {allowed_leg_delta} are "
                "allowed for measured startup skew plus bounded clock drift)"
            ),
        })
    allowed_wall_shortfall = MAX_CAPTURE_STARTUP_SKEW_SAMPLES + math.ceil(
        capture_elapsed_samples * MAX_CLOCK_DRIFT_PPM / 1_000_000
    )
    wall_shortfalls = {
        "mic": max(capture_elapsed_samples - mic_samples, 0),
        "system": max(capture_elapsed_samples - system_samples, 0),
    }
    for leg_name, shortfall in wall_shortfalls.items():
        if (
            capture_elapsed_samples >= MIN_LEG_SAMPLES
            and shortfall > allowed_wall_shortfall
        ):
            blockers.append({
                "code": "leg_ended_before_capture_stop",
                "leg": leg_name,
                "shortfall_samples": shortfall,
                "allowed_shortfall_samples": allowed_wall_shortfall,
                "detail": (
                    f"the {leg_name} leg ended materially before capture stopped "
                    f"({shortfall} samples short; at most "
                    f"{allowed_wall_shortfall} are allowed for measured startup "
                    "skew plus bounded clock drift)"
                ),
            })

    return {
        "schema": SCHEMA,
        "usable": not blockers,
        "requirements": {
            "both_legs_reached_one_capture_block": (
                mic_samples >= MIN_LEG_SAMPLES
                and system_samples >= MIN_LEG_SAMPLES
            ),
            "continuous_timelines": not any(leg_dropouts.values()),
            "tap_reported_no_errors": not tap_errors,
            "legs_cover_same_capture_span": leg_delta <= allowed_leg_delta,
            "both_legs_cover_observed_capture_span": not any(
                shortfall > allowed_wall_shortfall
                for shortfall in wall_shortfalls.values()
            ),
            "transcript_written_when_requested": (
                not transcription_requested or transcript_written
            ),
        },
        "legs": {
            "mic": {
                "samples": mic_samples,
                "duration_s": round(mic_samples / RATE, 3),
                "dropouts": leg_dropouts["mic"],
            },
            "system": {
                "samples": system_samples,
                "duration_s": round(system_samples / RATE, 3),
                "dropouts": leg_dropouts["system"],
                "tap_errors": tap_errors,
            },
        },
        "transcription": {
            "requested": transcription_requested,
            "transcript_written": transcript_written,
        },
        "timing": {
            "capture_elapsed_samples": capture_elapsed_samples,
            "capture_elapsed_s": round(capture_elapsed_samples / RATE, 3),
            "leg_sample_difference": leg_delta,
            "allowed_leg_sample_difference": allowed_leg_delta,
            "wall_shortfall_samples": wall_shortfalls,
            "allowed_wall_shortfall_samples": allowed_wall_shortfall,
            "clock_drift_ppm": MAX_CLOCK_DRIFT_PPM,
        },
        "blockers": blockers,
    }


def validate(health: dict, *, transcript_context: bool = False) -> bool:
    """Re-derive a stored verdict from evidence instead of trusting its booleans."""
    if not isinstance(health, dict) or health.get("schema") != SCHEMA:
        raise ValueError("capture health is absent or uses an unknown schema")
    try:
        legs = health["legs"]
        transcription = health["transcription"]
        rebuilt = build(
            mic_samples=legs["mic"]["samples"],
            system_samples=legs["system"]["samples"],
            capture_elapsed_samples=health["timing"]["capture_elapsed_samples"],
            dropouts={
                "mic": legs["mic"]["dropouts"],
                "system": legs["system"]["dropouts"],
            },
            tap_errors=legs["system"]["tap_errors"],
            transcription_requested=transcription["requested"],
            transcript_written=transcription["transcript_written"],
        )
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"capture health evidence is malformed: {exc}") from None
    if health != rebuilt:
        raise ValueError(
            "capture health verdict does not match its timing, sample, dropout, tap, "
            "and transcription evidence"
        )
    if transcript_context:
        transcription = rebuilt["transcription"]
        if not (
            transcription["requested"] and transcription["transcript_written"]
        ):
            raise ValueError(
                "a transcript must carry capture health that says transcription was "
                "requested and its artifact was written"
            )
    return rebuilt["usable"]


def warning(health: dict, *, transcript_context: bool = False) -> str | None:
    """The one human-facing consequence of failed capture-health evidence."""
    if validate(health, transcript_context=transcript_context):
        return None
    details = "; ".join(blocker["detail"] for blocker in health["blockers"])
    return (
        f"capture integrity failed: {details}. The transcript is retained evidence, "
        "not a complete meeting record."
    )

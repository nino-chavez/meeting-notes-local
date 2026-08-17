"""One deterministic contract for capture integrity and its persisted evidence."""

from __future__ import annotations

import math
import hashlib
import struct
import wave
from pathlib import Path

RATE = 16_000
MIN_LEG_SAMPLES = RATE // 5
MAX_CLOCK_DRIFT_PPM = 50
# The two streams have begun as much as 1.7 s apart in measured captures. Round that
# observed bound up to the next 200 ms capture block; this is acquisition skew, not a
# meeting-quality duration threshold.
MAX_CAPTURE_STARTUP_SKEW_SAMPLES = 2 * RATE
SCHEMA = "capture-health/1"
TRANSCRIPT_SCHEMA = "capture-transcript/1"
QUALITY_SCHEMA = "capture-quality/1"
MICROPHONE_SCHEMA = "capture-microphone/1"
QUALITY_STATUSES = frozenset({"observed", "not_observed", "unknown"})
UNKNOWN_WARNING = (
    "capture integrity is unknown: this legacy capture transcript predates "
    "persisted capture-health evidence. Treat it as retained evidence, not a "
    "complete meeting record."
)


def unknown_quality(reason: str = "quality evidence was not persisted") -> dict:
    """Return an explicit, non-integrity quality result for legacy captures."""
    if not isinstance(reason, str) or not reason:
        raise ValueError("quality unknown reason must be a non-empty string")
    return {
        "schema": QUALITY_SCHEMA,
        "source": {"leg": "mic", "artifact": "mic.wav", "samples": None},
        "metrics": None,
        "observations": {
            name: {"status": "unknown", "detail": reason}
            for name in ("silence", "clipping", "low_input", "background_noise")
        },
    }


def _observation(status: str, detail: str, **metrics) -> dict:
    if status not in QUALITY_STATUSES:
        raise ValueError(f"unknown quality status: {status!r}")
    value = {"status": status, "detail": detail}
    if metrics:
        value["metrics"] = metrics
    return value


def build_quality_evidence(audio, *, source_sha256: str | None = None) -> dict:
    """Derive bounded microphone observations from PCM samples.

    This is guidance only. It never contributes to the capture-health usable
    verdict. A short or empty input cannot support a quality claim, so each
    observation is explicitly ``unknown`` rather than guessed.
    """
    count = 0
    total_squared = 0.0
    peak = 0.0
    clipped_count = 0
    window = RATE // 10
    window_squared = 0.0
    window_count = 0
    window_rms = []
    try:
        values = iter(audio)
        for raw_value in values:
            value = float(raw_value)
            if not math.isfinite(value) or abs(value) > 1.0:
                return unknown_quality("microphone samples are outside bounded PCM range")
            count += 1
            absolute = abs(value)
            total_squared += value * value
            peak = max(peak, absolute)
            clipped_count += int(absolute >= 0.999)
            window_squared += value * value
            window_count += 1
            if window_count == window:
                window_rms.append(math.sqrt(window_squared / window))
                window_squared = 0.0
                window_count = 0
    except (TypeError, ValueError, OverflowError):
        return unknown_quality("microphone samples are unavailable or malformed")
    if count == 0:
        return unknown_quality("microphone WAV contains no samples")
    if count < window:
        return unknown_quality(
            "microphone recording is too short for bounded quality observations"
        )
    # 100 ms windows are the same block size used by the recorder's input path.
    rms = math.sqrt(total_squared / count)
    clipped = clipped_count / count
    metrics = {
        "samples": count,
        "duration_s": round(count / RATE, 3),
        "rms": round(rms, 6),
        "peak": round(peak, 6),
        "clipped_fraction": round(clipped, 6),
        "window_count": len(window_rms),
        "floor_rms": round(min(window_rms), 6) if window_rms else None,
        "active_rms": round(max(window_rms), 6) if window_rms else None,
    }
    source = {"leg": "mic", "artifact": "mic.wav", "samples": count}
    if source_sha256 is not None:
        if not isinstance(source_sha256, str) or len(source_sha256) != 64:
            raise ValueError("quality source digest must be a SHA-256 hex string")
        source["sha256"] = source_sha256

    enough_windows = len(window_rms) >= 2
    floor = min(window_rms) if window_rms else 0.0
    active = max(window_rms) if window_rms else 0.0
    return {
        "schema": QUALITY_SCHEMA,
        "source": source,
        "metrics": metrics,
        "observations": {
            "silence": _observation(
                "observed" if rms < 0.003 else "not_observed",
                "the microphone recording is below the digital-silence floor"
                if rms < 0.003
                else "the microphone recording contains measurable signal",
                rms=metrics["rms"],
                threshold=0.003,
            ),
            "clipping": _observation(
                "observed" if clipped >= 0.001 else "not_observed",
                "samples reach the bounded PCM ceiling"
                if clipped >= 0.001
                else "no material run of samples reaches the bounded PCM ceiling",
                clipped_fraction=metrics["clipped_fraction"],
                threshold=0.001,
            ),
            "low_input": _observation(
                "observed" if rms < 0.01 else "not_observed",
                "the microphone level is below the low-input floor"
                if rms < 0.01
                else "the microphone level clears the low-input floor",
                rms=metrics["rms"],
                threshold=0.01,
            ),
            "background_noise": (
                _observation(
                    "unknown",
                    "the recording is too short to compare quiet and active windows",
                )
                if not enough_windows
                else _observation(
                    (
                        "observed"
                        if floor >= 0.01 and floor / max(active, 1e-12) >= 0.35
                        else "not_observed"
                    ),
                    "the quiet windows retain material microphone energy"
                    if floor >= 0.01 and floor / max(active, 1e-12) >= 0.35
                    else "quiet windows do not retain material microphone energy",
                    floor_rms=metrics["floor_rms"],
                    active_rms=metrics["active_rms"],
                    floor_to_active=round(floor / max(active, 1e-12), 6),
                    floor_threshold=0.01,
                    ratio_threshold=0.35,
                )
            ),
        },
    }


def build_quality_from_wav(path: Path, *, source_sha256: str | None = None) -> dict:
    """Read one supported WAV and derive quality evidence without resampling."""
    try:
        with wave.open(str(path), "rb") as audio:
            if (
                audio.getnchannels() != 1
                or audio.getsampwidth() != 2
                or audio.getframerate() != RATE
                or audio.getcomptype() != "NONE"
            ):
                return unknown_quality("microphone WAV is not mono 16 kHz PCM")
            frames = audio.getnframes()
            def values():
                remaining = frames
                while remaining:
                    chunk_frames = min(65_536, remaining)
                    encoded = audio.readframes(chunk_frames)
                    if len(encoded) != chunk_frames * 2:
                        raise ValueError("microphone WAV is truncated")
                    yield from (
                        sample[0] / 32768.0
                        for sample in struct.iter_unpack("<h", encoded)
                    )
                    remaining -= chunk_frames
            return build_quality_evidence(values(), source_sha256=source_sha256)
    except (EOFError, OSError, wave.Error):
        return unknown_quality("microphone WAV is unreadable")
    except ValueError as exc:
        return unknown_quality(str(exc))


def validate_quality_evidence(quality: dict, *, mic_path: Path | None = None) -> bool:
    """Reject unknown schemas/shapes and, when available, re-derive from WAV bytes."""
    if not isinstance(quality, dict) or quality.get("schema") != QUALITY_SCHEMA:
        raise ValueError("capture quality is absent or uses an unknown schema")
    if set(quality) != {"schema", "source", "metrics", "observations"}:
        raise ValueError("capture quality has an unknown shape")
    source = quality["source"]
    if not isinstance(source, dict) or set(source) - {"leg", "artifact", "samples", "sha256"}:
        raise ValueError("capture quality source has an unknown shape")
    if source.get("leg") != "mic" or source.get("artifact") != "mic.wav":
        raise ValueError("capture quality must describe mic.wav")
    if source.get("samples") is not None and (
        isinstance(source.get("samples"), bool)
        or not isinstance(source.get("samples"), int)
        or source.get("samples") < 0
    ):
        raise ValueError("capture quality source sample count is malformed")
    if "sha256" in source and (
        not isinstance(source["sha256"], str)
        or len(source["sha256"]) != 64
        or any(character not in "0123456789abcdef" for character in source["sha256"])
    ):
        raise ValueError("capture quality source digest is malformed")
    observations = quality["observations"]
    expected = {"silence", "clipping", "low_input", "background_noise"}
    if not isinstance(observations, dict) or set(observations) != expected:
        raise ValueError("capture quality observations are incomplete or unknown")
    expected_observation_metrics = {
        "silence": {"rms", "threshold"},
        "clipping": {"clipped_fraction", "threshold"},
        "low_input": {"rms", "threshold"},
        "background_noise": {
            "floor_rms", "active_rms", "floor_to_active", "floor_threshold", "ratio_threshold"
        },
    }
    for name, observation in observations.items():
        if not isinstance(observation, dict) or set(observation) - {"status", "detail", "metrics"}:
            raise ValueError(f"capture quality {name} observation has an unknown shape")
        if (
            observation.get("status") not in QUALITY_STATUSES
            or not isinstance(observation.get("detail"), str)
        ):
            raise ValueError(f"capture quality {name} observation is malformed")
        if "metrics" in observation:
            metrics_value = observation["metrics"]
            if (
                not isinstance(metrics_value, dict)
                or set(metrics_value) != expected_observation_metrics[name]
            ):
                raise ValueError(f"capture quality {name} metrics have an unknown shape")
    metrics = quality["metrics"]
    if metrics is not None and not isinstance(metrics, dict):
        raise ValueError("capture quality metrics must be an object or null")
    if metrics is not None and set(metrics) != {
        "samples", "duration_s", "rms", "peak", "clipped_fraction",
        "window_count", "floor_rms", "active_rms",
    }:
        raise ValueError("capture quality metrics have an unknown shape")
    if mic_path is not None:
        if "sha256" in source:
            digest = hashlib.sha256()
            try:
                with mic_path.open("rb") as handle:
                    for chunk in iter(lambda: handle.read(1 << 20), b""):
                        digest.update(chunk)
            except OSError as exc:
                raise ValueError(f"microphone WAV cannot be hashed ({exc})") from None
            if digest.hexdigest() != source["sha256"]:
                raise ValueError("quality source digest does not match mic.wav")
        expected_quality = build_quality_from_wav(mic_path, source_sha256=source.get("sha256"))
        if quality != expected_quality:
            raise ValueError("capture quality does not match mic.wav")
    return True


def build_microphone_identity(*, index, name, hostapi=None) -> dict:
    """Persist only the resolved input identity needed to explain a recording."""
    if isinstance(index, bool) or not isinstance(index, int) or index < 0:
        raise ValueError("microphone index must be a non-negative integer")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("microphone name must be non-empty")
    if hostapi is not None and (
        isinstance(hostapi, bool) or not isinstance(hostapi, int) or hostapi < 0
    ):
        raise ValueError("microphone hostapi must be a non-negative integer")
    identity = {"schema": MICROPHONE_SCHEMA, "index": index, "name": name}
    if hostapi is not None:
        identity["hostapi"] = hostapi
    return identity


def validate_microphone_identity(identity: dict) -> bool:
    if not isinstance(identity, dict) or identity.get("schema") != MICROPHONE_SCHEMA:
        raise ValueError("microphone identity is absent or uses an unknown schema")
    if set(identity) - {"schema", "index", "name", "hostapi"}:
        raise ValueError("microphone identity has an unknown shape")
    build_microphone_identity(
        index=identity.get("index"), name=identity.get("name"), hostapi=identity.get("hostapi")
    )
    return True


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

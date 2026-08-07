//! First run's permission surface (§ H): report the two capture permissions, and
//! ask for them, without ever claiming a state that was not measured.
//!
//! The measurement itself lives in `capture/permission-probe`, a separate signed
//! binary — see its README for why the two permissions are not symmetric and why
//! system audio has no check-without-asking mode. This module is the boundary
//! between that binary and the shell: it resolves the probe through the runtime
//! manifest so an unverified one is never spawned, runs exactly one mode, and
//! parses the result as untrusted input.
//!
//! **The probe's stdout is untrusted.** It is a child process reading platform
//! state, and `screens-and-states.md § Rendered transcript text is untrusted
//! input` applies to it as much as to a transcript. Every field is matched against
//! a closed set here; an unrecognised value becomes `Unknown` rather than being
//! passed through to a surface that would render it. The shell therefore cannot be
//! made to display a string the probe invented.
//!
//! Every response carries only an enum and a boolean. No path, no error text from
//! the platform, and no operator content crosses this boundary.

use std::path::PathBuf;
use std::process::Command;

use local_meeting_notes_session_core::runtime::RuntimeManifest;
use serde::Serialize;
use serde_json::Value;

/// What the operator's microphone permission is, in the terms the surface uses.
///
/// `NotDetermined` is the only state from which asking shows a dialog, which is
/// why the surface has to distinguish it from `Denied` — pressing a button in the
/// denied state does nothing visible, and a surface that offered it would appear
/// broken. `Unknown` covers both the platform's own `@unknown default` and any
/// value this build does not recognise.
///
/// `Unmeasured` means this response did not ask. It exists because `Unknown` and
/// "we did not look" are different facts that a surface acts on differently, and
/// collapsing them once already broke a route: a system-audio request reported the
/// microphone as `Unknown`, and the mapping — correctly, for what it was told —
/// sent a successful grant to the panel that says nothing could be measured.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum MicrophonePermission {
    Authorized,
    Denied,
    Restricted,
    NotDetermined,
    Unmeasured,
    Unknown,
}

impl MicrophonePermission {
    fn parse(value: Option<&str>) -> Self {
        match value {
            Some("authorized") => Self::Authorized,
            Some("denied") => Self::Denied,
            Some("restricted") => Self::Restricted,
            Some("not-determined") => Self::NotDetermined,
            // `Unmeasured` is deliberately not parseable. It is this module's own
            // statement that a response did not ask, never a claim the probe is
            // allowed to make: the platform gives a status API for the microphone,
            // so a probe answering "unmeasured" is a probe that malfunctioned, and
            // `Unknown` is the right reading of that.
            _ => Self::Unknown,
        }
    }
}

/// What the system-audio permission is.
///
/// `Unmeasured` is a first-class answer, not a failure. There is no status API for
/// process taps, so the only check is creating one, and creating one is what raises
/// the prompt. A `status` call therefore cannot know, and says so rather than
/// guessing — which is the same rule that put the probe in a separate binary.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum SystemAudioPermission {
    Authorized,
    Unavailable,
    Unsupported,
    Unmeasured,
    Unknown,
}

impl SystemAudioPermission {
    fn parse(value: Option<&str>) -> Self {
        match value {
            Some("authorized") => Self::Authorized,
            Some("unavailable") => Self::Unavailable,
            Some("unsupported") => Self::Unsupported,
            Some("unmeasured") => Self::Unmeasured,
            _ => Self::Unknown,
        }
    }
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct FirstRunPermissions {
    pub microphone: MicrophonePermission,
    pub system_audio: SystemAudioPermission,
    /// True when the probe could not be resolved, verified, run, or parsed.
    ///
    /// Kept separate from the permission values so a surface can distinguish "the
    /// microphone is denied" from "we do not know". Collapsing those two into one
    /// state is how a first-run screen ends up telling an operator to change a
    /// setting that was never the problem.
    pub probe_unavailable: bool,
    /// True when the last request actually showed the operator a dialog.
    ///
    /// `false` after a request from an already-settled state, which is the signal
    /// the surface needs to route to System Settings instead of repeating itself.
    pub prompted: bool,
}

impl FirstRunPermissions {
    fn unavailable() -> Self {
        Self {
            microphone: MicrophonePermission::Unknown,
            system_audio: SystemAudioPermission::Unknown,
            probe_unavailable: true,
            prompted: false,
        }
    }
}

/// One probe run, or `None` if anything at all went wrong.
///
/// A non-zero exit is not automatically a failure: the probe exits 0 for a denied
/// permission because a denial is an answer. Exit 2 means it could not answer, and
/// that is the only status treated as unavailable.
fn run_probe(manifest_path: &PathBuf, mode: &str) -> Option<Value> {
    let probe = RuntimeManifest::verified_permission_probe(manifest_path).ok()?;
    let output = Command::new(probe).arg(mode).output().ok()?;
    if output.status.code() != Some(0) {
        return None;
    }
    // Bounded by construction rather than by measurement: the probe caps its own
    // microphone wait at 120 s and the tap create returns immediately, so this
    // cannot block a command thread forever. Stated from the probe's source — as of
    // 2026-08-06 neither request mode has been executed in any context, because
    // running one outside the signed bundle mutates the calling app's TCC state and
    // answers about the wrong binary. Only `status` has been exercised.
    let parsed: Value = serde_json::from_slice(&output.stdout).ok()?;
    if parsed.get("schema").and_then(Value::as_str) != Some("permission-probe/1") {
        return None;
    }
    Some(parsed)
}

fn read(parsed: &Value, key: &str) -> Option<String> {
    parsed.get(key).and_then(Value::as_str).map(str::to_owned)
}

pub fn permissions_status(manifest_path: &PathBuf) -> FirstRunPermissions {
    let Some(parsed) = run_probe(manifest_path, "status") else {
        return FirstRunPermissions::unavailable();
    };
    FirstRunPermissions {
        microphone: MicrophonePermission::parse(read(&parsed, "microphone").as_deref()),
        system_audio: SystemAudioPermission::parse(read(&parsed, "system_audio").as_deref()),
        probe_unavailable: false,
        prompted: false,
    }
}

pub fn request_microphone(manifest_path: &PathBuf) -> FirstRunPermissions {
    let Some(parsed) = run_probe(manifest_path, "request-microphone") else {
        return FirstRunPermissions::unavailable();
    };
    FirstRunPermissions {
        microphone: MicrophonePermission::parse(read(&parsed, "microphone").as_deref()),
        // A microphone request says nothing about system audio, and this must not
        // imply otherwise: the surface reads them independently.
        system_audio: SystemAudioPermission::Unmeasured,
        probe_unavailable: false,
        prompted: parsed
            .get("prompted")
            .and_then(Value::as_bool)
            .unwrap_or(false),
    }
}

pub fn request_system_audio(manifest_path: &PathBuf) -> FirstRunPermissions {
    let Some(parsed) = run_probe(manifest_path, "request-system-audio") else {
        return FirstRunPermissions::unavailable();
    };
    FirstRunPermissions {
        // Symmetric to the above: creating a tap says nothing about the microphone.
        microphone: MicrophonePermission::Unmeasured,
        system_audio: SystemAudioPermission::parse(read(&parsed, "system_audio").as_deref()),
        probe_unavailable: false,
        // The platform gives no way to know whether the tap create raised a dialog
        // or answered from a remembered decision, so this stays false rather than
        // asserting either.
        prompted: false,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn every_unrecognised_probe_value_becomes_unknown_rather_than_passing_through() {
        assert_eq!(
            MicrophonePermission::parse(Some("authorized")),
            MicrophonePermission::Authorized
        );
        assert_eq!(
            MicrophonePermission::parse(Some("not-determined")),
            MicrophonePermission::NotDetermined
        );
        // The cases that matter: anything the probe could emit that this build does
        // not know about, including an injected string, lands on Unknown.
        for hostile in ["", "AUTHORIZED", "granted", "<script>", "authorized "] {
            assert_eq!(
                MicrophonePermission::parse(Some(hostile)),
                MicrophonePermission::Unknown,
                "{hostile:?} must not be treated as a known state"
            );
        }
        assert_eq!(MicrophonePermission::parse(None), MicrophonePermission::Unknown);
        for hostile in ["", "AUTHORIZED", "denied", "yes"] {
            assert_eq!(
                SystemAudioPermission::parse(Some(hostile)),
                SystemAudioPermission::Unknown,
                "{hostile:?} must not be treated as a known state"
            );
        }
    }

    #[test]
    fn the_shell_reads_camel_case_keys_and_kebab_case_states() {
        // The shell reads `probeUnavailable` and `systemAudio`. Serializing this
        // struct with Rust's default naming would hand it `probe_unavailable`, so
        // every field would read `undefined` and the surface would silently route
        // to its unavailable panel forever. Pinned because nothing else would fail.
        let encoded = serde_json::to_string(&FirstRunPermissions {
            microphone: MicrophonePermission::NotDetermined,
            system_audio: SystemAudioPermission::Unmeasured,
            probe_unavailable: false,
            prompted: true,
        })
        .unwrap();
        assert!(encoded.contains("\"probeUnavailable\":false"), "{encoded}");
        assert!(encoded.contains("\"systemAudio\":\"unmeasured\""), "{encoded}");
        // The state values are compared as literals in main.js, so their casing is
        // part of the contract too.
        assert!(encoded.contains("\"microphone\":\"not-determined\""), "{encoded}");
    }

    #[test]
    fn a_request_says_unmeasured_about_the_permission_it_did_not_ask_about() {
        // Each request mode measures one permission. What it reports about the other
        // has to say "did not ask" and not "unrecognised", because the surface routes
        // on the difference: `unknown` means nothing could be measured and sends the
        // operator to a dead end, while `unmeasured` means carry on with what the
        // previous step established. Reported by review on 5f54376, where a granted
        // system-audio permission routed to the unavailable panel.
        let encoded = serde_json::to_string(&FirstRunPermissions {
            microphone: MicrophonePermission::Unmeasured,
            system_audio: SystemAudioPermission::Authorized,
            probe_unavailable: false,
            prompted: false,
        })
        .unwrap();
        assert!(encoded.contains("\"microphone\":\"unmeasured\""), "{encoded}");
        // And the probe cannot claim it: a microphone status is always available on
        // the platform, so this value is only ever this module's own.
        assert_eq!(
            MicrophonePermission::parse(Some("unmeasured")),
            MicrophonePermission::Unknown
        );
    }

    #[test]
    fn an_unresolvable_probe_reports_unknown_and_not_denied() {
        let missing = PathBuf::from("/nonexistent/app-runtime.json");
        let status = permissions_status(&missing);
        assert!(status.probe_unavailable);
        // The distinction this preserves: "we could not ask" is not "you said no".
        // A surface told `denied` here would send the operator to System Settings to
        // fix a permission that was never the problem.
        assert_eq!(status.microphone, MicrophonePermission::Unknown);
        assert_eq!(status.system_audio, SystemAudioPermission::Unknown);
        assert!(!status.prompted);
        assert!(request_microphone(&missing).probe_unavailable);
        assert!(request_system_audio(&missing).probe_unavailable);
    }
}

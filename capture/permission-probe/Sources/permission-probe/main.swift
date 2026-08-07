// What are this application's two capture permissions, right now?
//
// First run (§H in screens-and-states.md) has to reach a `ready` state that means
// "permissions exist". Feature 10 says the shell never lies at menubar size, so a
// surface may not claim readiness it cannot measure. Nothing in the app could
// measure it: the microphone check lives inside MeetingCaptureCLI's start path
// (`AVCaptureDevice.authorizationStatus` at the point of opening the engine), and
// the system-audio check is the OSStatus of `AudioHardwareCreateProcessTap`. Both
// are discovered by trying to record. A first-run screen cannot record.
//
// This is a separate executable rather than a mode on MeetingCaptureCLI on purpose.
// That CLI's argument contract is exactly four inherited file descriptors and it is
// frozen (vertical-slice.md Wave B); widening it to answer a question that has
// nothing to do with capture would spend a frozen contract on a convenience. The
// precedent in this directory is `aec-probe`: a standalone package that answers one
// question and writes no product record. This follows it.
//
// The two permissions are not symmetric, and the asymmetry is the honest part.
//
// Microphone has a real status API. `status` reports it without prompting.
//
// System audio does not. macOS 14.4's Core Audio process taps report authorization
// through the status of the create call itself — the tap manager in
// `capture/audiotee` learns it exactly that way and no query API is used anywhere
// in this tree. So the only way to know is to create a tap and destroy it, which is
// also what raises the prompt the first time. That means system audio has no
// "check without asking" mode, and this probe does not pretend otherwise: `status`
// reports it as unmeasured, and a caller wanting the truth must run
// `request-system-audio`. Reporting a guess instead would be the lie feature 10
// exists to prevent.
//
// Creating and immediately destroying a tap records nothing. No audio buffer is
// read, no aggregate device is built, no file is written, and no product record is
// touched. This binary never opens the capture directory and takes no descriptors.
//
// Usage:
//   permission-probe status                  microphone only; never prompts
//   permission-probe request-microphone      prompts if undetermined; reports result
//   permission-probe request-system-audio    creates and destroys one tap; reports result
//
// Output is one line of JSON on stdout. Exit status is 0 whenever the probe ran to
// completion, including when a permission is denied — a denial is an answer, not a
// probe failure. Exit 2 means the probe could not answer.

import AVFoundation
import CoreAudio
import Foundation

let SCHEMA = "permission-probe/1"

/// The five states `AVCaptureDevice` distinguishes, named as the surface names them.
func microphoneStatus() -> String {
  switch AVCaptureDevice.authorizationStatus(for: .audio) {
  case .authorized: return "authorized"
  case .denied: return "denied"
  case .restricted: return "restricted"
  case .notDetermined: return "not-determined"
  @unknown default: return "unknown"
  }
}

func emit(_ payload: [String: Any]) {
  var complete = payload
  complete["schema"] = SCHEMA
  guard
    let data = try? JSONSerialization.data(
      withJSONObject: complete, options: [.sortedKeys]),
    let line = String(data: data, encoding: .utf8)
  else {
    FileHandle.standardError.write(Data("permission-probe could not encode its result\n".utf8))
    exit(2)
  }
  print(line)
}

func fail(_ detail: String) -> Never {
  emit(["outcome": "probe-failed", "detail": detail])
  exit(2)
}

/// Ask for the microphone, then report what the platform settled on.
///
/// `requestAccess` only prompts from `.notDetermined`; from `.denied` it returns
/// immediately without showing anything, which is why the caller is told to send the
/// operator to System Settings rather than to press the button again.
func requestMicrophone() -> Never {
  let before = microphoneStatus()
  guard before == "not-determined" else {
    emit(["action": "request-microphone", "prompted": false, "microphone": before])
    exit(0)
  }
  let settled = DispatchSemaphore(value: 0)
  AVCaptureDevice.requestAccess(for: .audio) { _ in settled.signal() }
  if settled.wait(timeout: .now() + 120) == .timedOut {
    fail("the microphone prompt was not answered within 120 seconds")
  }
  emit(["action": "request-microphone", "prompted": true, "microphone": microphoneStatus()])
  exit(0)
}

/// Create one system-audio tap and destroy it, to learn whether we are allowed to.
///
/// Mirrors `AudioTapManager`'s description for the system default output so the
/// answer is about the same permission the real capture needs — mixdown of the
/// default output device's first stream — and not about some narrower tap that
/// might be permitted when the real one is not. Nothing is read from the tap.
func requestSystemAudio() -> Never {
  guard #available(macOS 14.4, *) else {
    emit([
      "action": "request-system-audio", "system_audio": "unsupported",
      "detail": "process taps require macOS 14.4 or later",
    ])
    exit(0)
  }
  let description = CATapDescription()
  description.name = "permission-probe"
  description.isPrivate = true
  description.muteBehavior = .unmuted
  description.isMixdown = true
  description.isMono = true
  description.isExclusive = false
  description.deviceUID = nil
  description.stream = 0

  var tapID = AudioObjectID(kAudioObjectUnknown)
  let status = AudioHardwareCreateProcessTap(description, &tapID)
  if status == kAudioHardwareNoError {
    AudioHardwareDestroyProcessTap(tapID)
    emit(["action": "request-system-audio", "system_audio": "authorized", "status": 0])
    exit(0)
  }
  // The create call is the only signal there is. A non-zero status here means the
  // tap was refused; this probe reports the status rather than translating every
  // Core Audio code into a permission verdict it cannot substantiate.
  emit([
    "action": "request-system-audio", "system_audio": "unavailable",
    "status": Int(status),
  ])
  exit(0)
}

func reportStatus() -> Never {
  emit([
    "action": "status",
    "microphone": microphoneStatus(),
    // Deliberately not a guess. See the header: there is no query API, and the only
    // measurement raises a prompt, which `status` promises not to do.
    "system_audio": "unmeasured",
    "system_audio_detail": "run request-system-audio; creating a tap is the only check",
  ])
  exit(0)
}

let arguments = Array(CommandLine.arguments.dropFirst())
guard arguments.count == 1 else {
  fail("permission-probe takes exactly one of: status, request-microphone, request-system-audio")
}
switch arguments[0] {
case "status": reportStatus()
case "request-microphone": requestMicrophone()
case "request-system-audio": requestSystemAudio()
default:
  fail("unknown mode \(arguments[0]); expected status, request-microphone, or request-system-audio")
}

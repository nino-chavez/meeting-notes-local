# Post-approval macOS vertical slice

## Status

This is an implementation contract, not permission to implement.

Application work remains blocked by
[`encounter-acceptance.md`](./encounter-acceptance.md). The repository's fresh
history closes the source-distribution stop; it does not approve the encounter
or permit private meeting artifacts in Git. No application build may be
described as beta-ready while the encounter gate remains open.

The contract exists now so the first implementation does not have to settle
process ownership, persistence, recovery, and security while it is also trying
to prove a real meeting path.

## Reader and job

This document is for the implementer and reviewer who pick up the application
after the product encounter is approved. Their job is to build the smallest
true path from manual Start to an evidence-bearing note, know which process owns
each decision, and know which failures must be demonstrated before the path can
be called working.

The reader may know Tauri, Rust, Swift, and Python. They should not need any
prior project session or commit narrative.

## Outcome

The first completed vertical slice does exactly this:

1. The application window and tray render even when every worker is absent.
2. A valid enrolled profile, healthy packaged resources, an enforceable
   retention period, and a fresh participant attestation make manual Start
   available; hardware readiness is confirmed during `arming`.
3. One headphone meeting is captured into a new private directory.
4. Stop produces a validated `capture-session/2` receipt.
5. Post-meeting transcription produces a validated
   `capture-transcript/1` artifact.
6. Note generation either produces a validated, passing `note/2` pair or
   leaves the transcript available in a distinct `summary-failed` state.
7. The library and note reader reopen the same validated artifacts after a
   fresh process launch.

This is narrower than the first beta. It still includes the minimum automatic
audio-retention executor: a human meeting cannot be recorded under a deletion
period the application does not enforce. Correction, in-app profile enrolment
and reset, disk accounting, immediate manual audio deletion, and whole-meeting
deletion follow as trust-action slices over the same storage contract. They are
not silently implied by the first end-to-end run, and no build reaches beta
until they work.

The supported operating envelope remains:

- macOS 14.4 or later;
- manual Start and Stop;
- headphones;
- one enrolled operator at the microphone;
- nobody else in the room;
- local post-meeting processing;
- no speaker playback, live transcription, automatic meeting detection,
  calendar preparation, named participants, cross-meeting search, sharing, or
  product-development inference.

Headphones and an empty room are operator assertions. The application must
state them before Start; it must not claim it detected conditions it cannot
measure.

## Decisions that are already closed

- The shell is Tauri, not SwiftUI. `DESIGN.md` owns that decision.
- Rust owns application and capture-attempt state.
- The Swift tap and Python worker are packaged children, not independently
  installed services.
- Existing validated artifact formats remain canonical. The application does
  not rewrite their semantics in Rust.
- A rejected note is never a ready note.
- The browser-facing interface receives named operations, never general shell
  or filesystem authority.
- No worker or capture process is managed by `launchd` in this slice.

Changing any of these is an architecture change, not an implementation detail.

## Runtime boundary considered

Three concrete shapes were checked against a missing runtime, a child that
never becomes ready, an interrupted capture, a rejected note, and a fresh
launch.

| Candidate | Shape | Result |
|---|---|---|
| Script-launching shell | Tauri invokes the current capture and summarizer CLIs and infers state from console output and directories. | Rejected. Console prose is not a protocol, a CLI exit cannot represent the live degraded states, and Rust would have to reproduce Python artifact rules to decide what happened. |
| Rust session core with one typed local worker | Rust owns the reducer, child process group, approved storage root, diagnostics, and UI commands. A Python child exposes versioned JSON-lines operations over the current capture, transcript, note, and profile code. The Swift tap exists only inside an active capture. | Chosen. It preserves one application authority without duplicating the evidence logic. |
| Local HTTP daemon | A long-running Python service owns capture and processing while Tauri calls it over loopback, following the broad Film Room process shape. | Rejected for this slice. It adds a port, token, server readiness, request surface, and daemon lifetime to a local command-and-event workload that does not need them. |

The Film Room Tauri shell remains the internal reference for bundled-resource
checks, child cleanup, private diagnostics, startup timeouts, and a window that
renders without its worker. Its loopback server is not copied because the
transport need is different.

## Chosen process shape

```text
Tauri webview
  named commands and escaped display data
          |
          v
Rust session core
  reducer | tray | consent | policy | recovery | diagnostics
          |
          | versioned JSON lines over stdin/stdout
          v
Python worker process group
  capture adapter | transcript adapter | note adapter | profile inspection
          |
          | capture.start only, after the attempt receipt is durable
          v
Swift Core Audio tap (capture-attempt scoped)

$APP_DATA
  meeting records | canonical capture/transcript/note artifacts | profile
```

Rust starts the worker as an embedded external binary and owns the worker's
process group. The worker may create the Swift tap only for an approved capture
request, and that tap stays in the same owned group. Stopping, timing out, or
exiting the application must stop and wait for the whole group.

The Python worker is application-scoped and may stay ready while the
application is open. Ready does not mean recording. The Swift tap is
attempt-scoped, and no tap exists before a capture request has passed the static
readiness and attestation gates.

Normal child cleanup is not enough. A Rust crash or `SIGKILL` does not
automatically kill its descendants. Rust therefore creates a parent-liveness
pipe whose write end exists only in the Rust process. The worker and every tap
inherit the read end and must stop capture and exit when it reaches EOF. The
worker cannot mask or close that signal while a tap is live.

Before tap launch, the application writes the attempt receipt. The tap starts
paused, then Rust writes `ownership.json` before any meeting audio file is
opened or `recording` is emitted. That receipt binds every child PID and process
start time, process-group ID, executable path and digest, and the application,
worker, and tap build digests.

If the worker exits while Rust is alive, Rust observes the child exit, signals
the owned process group, and waits for every recorded child. If Rust dies, the
direct liveness pipe makes both worker and tap exit. A fresh launch waits for
that shutdown, then compares each surviving PID's current process start time
and executable path and digest with `ownership.json`. It signals only an exact
match. PID or process-group number alone is never authority to kill a process.
If identity cannot be proven, Start stays blocked and recovery explains why
without signalling an unrelated process.

There is no `launchd` job. A job that can restart or outlive the Tauri
application conflicts with per-attempt consent and makes process ownership
ambiguous after a crash.

Tauri's current canonical patterns support this boundary:

- [embedded external binaries](https://v2.tauri.app/develop/sidecar/) for
  target-specific sidecars and Rust-side spawning;
- the [Rust tray API](https://v2.tauri.app/learn/system-tray/) for a tray whose
  reading comes from the same reducer as the window;
- explicit [window capabilities](https://v2.tauri.app/security/capabilities/)
  instead of broad shell or filesystem permission;
- a restrictive, local-only [content security policy](https://v2.tauri.app/security/csp/).

The webview receives no generic shell command, child-process handle, arbitrary
path, or unrestricted filesystem primitive. Registering a Rust-side sidecar
facility does not authorize its JavaScript API.

## Authority by component

| Component | Owns | Must not own |
|---|---|---|
| Tauri webview | Rendering, local interaction state, accessible focus and announcements | Process launch, storage paths, artifact acceptance, consent persistence |
| Rust session core | Startup and capture reducer, one-at-a-time operation lock, attestation lifetime, policy checks, process group, private diagnostics, meeting index projection, deletion orchestration | Transcription, voice scoring, note claims, or a second interpretation of artifact validity |
| Python worker | Versioned operations over the existing capture, profile, transcript, and note validators | Product readiness, arbitrary commands or paths, retention policy, UI state |
| Swift tap | System and microphone audio acquisition for the current capture | Restart policy, meeting identity, transcript or note behavior |
| Canonical artifacts | Durable evidence and the accepted result of each completed stage | Live child state or permission state |

The Rust reducer may say that a job is running or failed. It may say a note is
ready only after the Python validator returns the digests of a `note/2` JSON and
Markdown pair whose stored verdict is exactly passing.

## Worker protocol

Standard output is protocol-only JSON Lines. Standard error is a bounded
diagnostic stream written to an owner-only file after redaction. No transcript,
note body, audio sample, model prompt, environment variable, or command line is
copied into routine diagnostics.

The first child message is a readiness handshake:

```json
{
  "schema": "worker-event/1",
  "event": "worker.ready",
  "protocol": 1,
  "build": "<worker build digest>",
  "runtime": {
    "kind": "bundled",
    "digest": "<runtime digest>"
  },
  "tap": {
    "build": "<tap build digest>",
    "available": true
  },
  "models": [
    {
      "id": "<fixed local model id>",
      "digest": "<model digest>",
      "available": true
    }
  ],
  "operations": [
    "profile.inspect",
    "profile.adopt",
    "capture.start",
    "capture.stop",
    "capture.inspect",
    "transcript.create",
    "note.create",
    "note.inspect"
  ]
}
```

Every command has one request identifier and one terminal result:

```json
{
  "schema": "worker-command/1",
  "request_id": "<uuid>",
  "operation": "capture.start",
  "arguments": {
    "meeting_id": "<uuid>",
    "profile_id": "<opaque local id>"
  }
}
```

Progress and results use the same request identifier:

```json
{
  "schema": "worker-event/1",
  "request_id": "<uuid>",
  "event": "capture.state",
  "state": "recording",
  "meeting_id": "<uuid>"
}
```

```json
{
  "schema": "worker-result/1",
  "request_id": "<uuid>",
  "ok": false,
  "code": "tap_ready_timeout",
  "recoverable": true
}
```

Rules:

- Schema, operation, identifier, state, and error-code fields are closed
  enumerations.
- Unknown schemas, duplicate terminal results, unknown request identifiers,
  malformed JSON, and events invalid for the current reducer state fail closed.
- Frame bytes, queued events, event rate, standard-error bytes, and each
  diagnostic file have explicit upper bounds. Crossing one is a protocol
  failure, not backpressure on the UI.
- Commands accept opaque identifiers, not frontend-supplied paths, executable
  names, model names, or arguments.
- Rust generates every request, meeting, attempt, and profile-candidate
  identifier. The webview cannot supply one.
- Rust gives the worker one fixed app-data root at launch. The worker resolves
  identifiers below it and rejects traversal, symlinks that escape it, reuse,
  and unexpected ownership or modes.
- Readiness has a measured, configurable deadline. A test may shorten it; beta
  packaging pins it only after cold-start measurements.
- A timeout kills and waits for the owned process group before recovery becomes
  available.
- Only one startup recovery, capture transition, or destructive storage
  operation may hold the reducer lock.
- The worker protocol is not a public plugin API. Adding an operation requires
  a schema and a failure test.

The thin worker should call extracted library functions, not parse the existing
CLI's human-readable output. Research flags such as protocol capture, AEC
sweeps, simulated bleed, experimental profiles, and ungated capture are not
worker operations.

`capture.state: recording` is emitted only after both audio legs report their
expected format and readiness. The current tap wrapper has no app-facing ready
acknowledgement, so adding and fault-testing that message is part of the real
worker boundary. Static preflight before attestation checks only bundled files,
digests, compatible schemas, and non-capturing OS status. It never starts the
tap. Hardware acquisition and any permission that cannot be checked without it
occur during `arming`, after the attempt receipt is durable; failure returns to
a permission or recovery state without emitting `recording`.

The packaged worker is a target-specific executable with its Python runtime and
fixed model resources inside the application bundle. It never depends on a
system Python installation. Missing or mismatched worker, tap, runtime, or model
resources produce `runtime-missing` before Start.

## Storage contract

The first slice uses the filesystem already required by the audio artifacts. It
does not add SQLite.

```text
$APP_DATA/                         0700
  diagnostics/                    0700
  profile/                        0700
    voiceprint.json               0600
  meetings/                       0700
    <meeting-id>/                 0700
      meeting.json                0600
      attempt.json                0600
      ownership.json              0600
      capture/
        session.json              0600
        mic.wav                   0600
        system.wav                0600
      transcript/
        <revision-digest>.json    0600
      notes/
        <note-digest>.json        0600
        <note-digest>.md          0600
      deletion/                   0700
```

`attempt.json` is an immutable `capture-attempt/1` receipt written before the
tap launches. It binds the Rust-generated meeting and attempt identifiers,
time, application build, participant-notice version, the operator's
attestation, headphone and empty-room assertions, and retention-policy digest.
It records an operator assertion; it is not proof that every participant
consented.

`ownership.json` is an immutable `capture-ownership/1` receipt written after the
tap starts paused and before audio files open. It carries the exact per-child
identity used by stop and recovery. If it cannot become durable, the process
group is stopped and the attempt never reaches `recording`.

`meeting.json` is the mutable application-owned receipt. It contains lifecycle
state, the chosen retention rule and next deletion time, the digests of
`attempt.json` and `ownership.json`, relative artifact identifiers and digests,
the current transcript and note revisions, and pending storage operations. None
of these receipts contains copied transcript or note text.

Application writes use a same-directory temporary file, file `fsync`, atomic
no-overwrite or replace as appropriate, and parent-directory `fsync`. The
current capture manifest writer fsyncs its temporary file but not its parent,
and ordinary transcript writes do not yet meet this durability contract. The
real worker phase must harden a shared owner-private writer and migrate those
paths before Rust may advance a meeting record.

Commit order is artifact bytes, artifact durability, Python validation, then
the Rust meeting receipt that points to the returned digest. A crash may leave
an unreferenced private artifact, which recovery can quarantine and reconcile;
it may not leave a committed pointer to absent bytes. Existing capture and note
validators remain the source for artifact meaning. Rust does not reproduce
them.

The library is rebuilt by scanning and validating meeting records at startup.
That is adequate for the bounded, single-user beta and avoids a transaction
split between a database and immutable files. A future SQLite index may be
added only as a rebuildable cache after measured library size makes the scan a
problem. It cannot become the sole copy of transcript, note, or evidence data.

No private output may be created inside the source repository. Running under
`umask 000` must still yield `0700` directories and `0600` private files.

Before in-app enrolment exists, the development slice may adopt one existing
strict `voiceprint/2` profile through a controlled path. A Rust-owned native
picker copies the selected file into an owner-only quarantine below
`$APP_DATA`; the webview never receives the original path. `profile.adopt`
validates the quarantined file with the current strict loader, including schema,
encoder fingerprint, enrolment provenance, and experimental status. Rust
installs a passing profile by digest and deletes the quarantine copy. It imports
no raw enrolment audio. This bridge is disabled in beta; in-app enrolment and
its immediate raw-data deletion contract must replace it first.

The automatic retention executor is part of the first human-capture slice.
Rust records the next deletion time in `meeting.json`, scans due work on launch
and while running, and first writes a durable deletion receipt. It stages the
two WAVs by same-volume rename and fsyncs both directories while the meeting
reads `deleting`. It then removes the staged bytes, fsyncs the deletion
directory, advances the receipt to `removed`, and only then commits
`audio-released` to `meeting.json`. A crash before that last commit leaves the
conservative `deleting` state; recovery verifies the receipt and absence of the
bound digests before advancing it. Manual deletion, disk accounting, policy
change, and whole-meeting deletion reuse the mechanism in the later
trust-action slice.

The completed operation receipt has schema `audio-deletion/1`. It binds the
original `capture-session/2` digest and the exact relative name, byte size, and
SHA-256 of each removed WAV. Post-deletion inspection is a composite rule:

- with both WAVs present, the existing capture validator must pass;
- with both WAVs absent, the previously admitted capture-receipt digest and a
  completed `audio-deletion/1` receipt must reconcile, after which the reader
  reports `complete, audio-released`;
- one missing WAV, an unbound name or digest, or absence without that receipt
  quarantines the meeting.

The deletion receipt authorizes only those audio bytes to be absent. It does not
weaken transcript, note, evidence, or capture-health validation.

There is deliberately no background deletion daemon. The period makes audio
due at a wall-clock time; deletion runs then if the tray application is open,
or immediately on its next launch. The retention surface must state that
closing the application pauses enforcement. Before beta, it must also offer
Delete now. Copy that promises deletion at an exact time while the application
is closed would be false.

## State and recovery contract

### Startup

The bundled HTML, CSS, JavaScript, and Rust shell render before worker
preflight. Startup then moves through the reducer:

```text
shell-rendered
  -> checking
  -> ready
  -> runtime-missing | service-timeout | diagnostic-written
  -> retrying
  -> ready | reinstall-required
```

`runtime-missing` and `service-timeout` are different evidence. Returning to the
library does not clear either. Only a successful bounded preflight clears the
block. A reviewer-only reset may clear a fixture during UI tests; production
code has no equivalent.

### Capture and processing

```text
idle
  -> arming
  -> recording
  -> stopping
  -> captured
  -> transcribing
  -> summarizing
  -> ready
```

Failure branches are distinct:

- `transcription-failed` retains the validated capture and retries
  transcription.
- `summary-failed` retains the validated transcript and retries summary.
- a lost tap or invalid final health produces an interrupted capture, not
  `captured`;
- a rejected `note/2` produces `summary-failed`, never `ready`.

The neutral Start affordance may open the attempt review only after static
worker, tap, runtime, and model integrity checks pass and a strict,
non-experimental `voiceprint/2` profile is loaded. Static preflight never starts
an audio-capable process.

Audio acquisition is disabled until all of these are current at the same time:

- the automatic retention executor passed its startup check and the operator
  chose a meeting-audio retention period;
- non-capturing permission status is satisfactory; any permission that requires
  acquisition will be resolved during `arming`, not represented as already
  granted;
- the operator attested participant notice for this attempt;
- the operator affirmed headphones and an empty room;
- the immutable attempt and ownership receipts are durable.

The worker may start the tap in a paused mode that cannot open capture devices
so its process identity can be committed to `ownership.json`. Only then may it
acquire and discard frames while permissions and format settle. It must not
create meeting audio files or emit `recording` until both legs are ready.

Every new Start, decline, cancelled countdown, completed capture, profile reset,
or retention change clears the attempt attestation.

### Fresh-process recovery

On launch, Rust scans meeting records and `capture-session/2` receipts before it
offers Start.

- A terminal, validated capture remains terminal.
- An `incomplete` meeting first follows its ownership receipt. Recovery waits
  for the parent-liveness shutdown, reads each surviving process identity from
  the OS, compares every recorded field, and terminates only exact matches.
- Once no matching child is live, the meeting is marked
  `recovered-interrupted`. If identity is ambiguous, Start remains blocked and
  no unrelated process is signalled.
- Recording never resumes automatically.
- Readable partial WAVs are preserved and named as partial. They do not become a
  product note without a separate, explicit recovery contract and validated
  health.
- A missing or malformed record is quarantined from the library, named in a
  private diagnostic, and left untouched for inspection.
- Recovery of one meeting does not block reading other valid meetings. It does
  block a new capture while child ownership is uncertain.

## Build order after approval

The order is fixed because each layer supplies the evidence needed by the next.

### 0. Human gates

No product implementation starts until:

1. a short, consented headphone capture supplies real retained words;
2. an agent may draft a small evidence-bound content set, but the operator
   confirms it only through a separate `encounter-content-approval/1` receipt
   bound to the draft's exact SHA-256;
3. the private `encounter-review-content/1` packet and approval receipt
   reconcile and visibly say that automatic extraction and runtime validation
   were not run;
4. the operator reviews that real-content encounter cold and approves the
   interaction.

The exhaustive ES2004c candidate ledger and registered classifier remain a
separate research gate for reporting classifier recall. They do not produce a
product note, test semantic support, or block the executable safety skeleton.
Human-curated encounter content may not be reused as model or runtime evidence.

The retired repository's privacy incident is tracked separately from this fresh
history. It does not grant authority to import old Git objects, private capture
material, or meeting-derived review packets into this repository.

### 1. Executable safety skeleton

Build the Tauri/Rust shell, reducer, explicit capabilities, local-only CSP,
private diagnostic writer, storage-root guard, typed protocol parser, process
group supervision, parent-liveness channel, automatic retention executor, and
fake worker/tap binaries.

Exit: the shell passes missing-child, timeout, duplicate-operation, forced-exit,
Rust `SIGKILL`, due-retention, and fresh-launch recovery tests without importing
a model or touching hardware.

### 2. Real worker boundary

Extract app-safe adapters around strict profile loading, capture finalization,
transcript creation, note generation, and artifact-pair validation. Package the
worker and Swift tap as target-specific sidecars. Add the tap readiness and
parent-liveness contracts, and harden canonical app writes through the shared
durable writer. Keep research CLI options out of the operation registry.

Exit: prerecorded fixtures travel through one protocol and produce the same
digests and verdicts as the direct validated functions.

### 3. True end-to-end surface

Implement the approved tray, consent, capture HUD, processing, library, note,
evidence, and failure states. Adopt one existing valid profile through the
strict development-only path; enrolment UI is a later trust-action slice.

Exit: one real headphone capture reaches either a passing, unedited model
`note/2` or an honest retained-transcript failure, and the same result reopens
after quitting every process. Every rendered claim locator resolves. A separate
human adjudication records whether each cited fragment semantically supports the
claim, and a short pre-run event reference characterizes omissions. Its
retention receipt is durable, and an accelerated copy of the same operation
proves automatic audio expiry before another person's build can use it.

An honest failure validates the failure path. It does not satisfy the pre-beta
automatic-note gate below.

### 4. Trust actions

Add enrolment and profile reset, immutable transcript correction, stale-note
marking and regeneration, disk accounting, policy change, immediate staged
audio deletion, and staged whole-meeting deletion. Remove or disable the
development profile-adoption bridge.

Exit: each action survives injected interruption and a fresh process. A real
gated canary supplies at least one withheld-turn decision; restoring it creates
a new transcript view, marks the old note stale, and requires a separate
regeneration action. Deleting audio leaves the note and transcript. Deleting a
meeting leaves the profile and other meetings.

### 5. Limited beta packaging and admission

Bundle the runtime, models, worker, and tap; add required macOS usage
descriptions and entitlements; sign, notarize, install on a fresh account, and
run the admission canary before any beta meeting. Do not begin the beta unless
the pre-beta automatic-note receipt passes.

#### Automatic-note admission

A failed or rejected run may prove honest failure handling, but it blocks beta
admission. Admission requires one exact private receipt binding all of these:

1. A consented headphone canary ran through the installed app path with a valid
   voice profile, passing capture health, and the frozen model/runtime identity.
2. The unedited result is `note/2` with `passed` exactly `true`; every rendered
   claim locator resolves to the retained transcript.
3. A person adjudicated every claim's cited words for semantic support and
   compared the note with a short event reference prepared before note
   generation.
4. The operator explicitly accepted the observed unsupported claims,
   omissions, and overall usefulness for a small monitored beta.
5. The same build passed restart, retention, correction, and deletion evidence
   required by the preceding phases.

Changing any bound artifact, model identity, or build invalidates this receipt.
One passing canary admits only the narrow monitored beta; it establishes no
population performance rate or GA envelope.

Exit: hardware permissions are attributed to the installed application, update
and recovery behavior are exercised, and the operator—not the test suite—judges
the notes useful.

## Parallel work

Parallel implementation begins only after the operation schemas, reducer,
storage record, and approved encounter are frozen.

| Workstream | Can run independently | Joins at |
|---|---|---|
| Rust shell and supervisor | Reducer, process group, diagnostics, storage guards, fake children | Versioned worker fixture |
| Python worker adapters | Existing validators behind fixed commands; protocol conformance fixtures | Rust protocol parser |
| Approved interface | Tauri components against reducer fixtures; no direct worker calls | Rust command facade |
| Swift packaging | Target-triple binary, ready/failure fixture, permission metadata | Real worker capture operation |
| Fault and packaging tests | Fake child matrix, private modes, fresh-process recovery, cold-bundle checks | Each workstream's executable output |

Do not parallelize competing definitions of the reducer, worker schema, meeting
record, or artifact authority. Those are shared contracts, not workstreams.

Each independent implementation uses its own worktree. No workstream imports a
private meeting artifact into Git.

## Human work and autonomous work

| Decision or action | Autonomous | Requires the operator or another person |
|---|---:|---:|
| Contract, scaffold, fixtures, fault injection, static checks | Yes | No |
| Candidate-event decisions and exact ledger approval for the research result | No | Yes |
| Consent and curation of real interaction-review content | Preparation only | Yes |
| Product-encounter approval | No | Yes |
| macOS permission prompts and real hardware capture | Preparation only | Yes |
| Participant notice and consent | No | Yes |
| Retention-period and far-end-notice product choices | Options and consequences only | Yes |
| Note usefulness and whether missing words are acceptable | Metrics only | Yes |
| Semantic-support adjudication of the first automatic canary | Preparation only | Yes |
| Apple identity, signing, notarization, release | Build preparation only | Yes |
| Privacy history rewrite or repository access change | No | Explicit authorization required |
| Beta or GA release decision | Evidence packet only | Yes |

## Acceptance and fault matrix

Passing the current Python self-tests does not satisfy these application
contracts. The installed boundary needs its own evidence.

| Fault or action | Required observable result |
|---|---|
| Worker, tap, or model bundle missing | Window renders; Start is disabled; no child remains; owner-only diagnostic names the component without meeting text |
| Worker starts but never sends `worker.ready` | Deadline stops and waits for the process group; one recovery action becomes available |
| Malformed JSON, unknown event, duplicate result | Request fails closed; reducer does not advance; bounded diagnostic records the protocol code |
| Second capture or recovery starts while one is active | Command is refused before a child or directory is created |
| Consent screen is open or attestation write fails | No tap process or audio file exists; the reducer cannot enter `recording` |
| App receives `SIGKILL` during recording while a fake tap ignores ordinary stop | Parent-liveness EOF stops the worker and tap; fresh launch verifies the identity receipt, preserves partial WAVs, never resumes, and names the meeting interrupted |
| Worker crashes while its tap is live | The inherited liveness channel or owned process-group cleanup stops the tap; Rust records interruption and cannot advance capture health |
| Tap exits, device changes, or permission disappears mid-capture | Audio already written remains; final health cannot say complete; the meeting cannot become a ready note |
| Transcription fails | Capture stays readable and retry begins from the capture |
| Summary is rejected or crashes | Transcript stays readable; no canonical ready-note record is created; retry begins from the transcript |
| Profile is missing, malformed, experimental, or fingerprint-mismatched | Start is disabled before tap launch |
| Adopted profile is oversized, a symlink, changes after selection, or fails strict validation | Quarantine is removed, installed profile is unchanged, and the webview learns no source path |
| `passed: false` note or mismatched Markdown sibling is injected | Reader refuses ready state and reports a bounded artifact error |
| State file write, `fsync`, replace, or parent `fsync` fails | Old committed state survives; status does not advance; temporary material remains private and is cleaned or recoverable |
| Run under `umask 000` | App root and directories are `0700`; private files are `0600`; nothing is written in the repository |
| Retention time becomes due while the app is closed | Next launch stages and removes the bound WAVs under a durable receipt, fsyncs removal, then commits `audio-released`; transcript, note, profile, and other meetings remain |
| One or both WAVs disappear without a matching completed `audio-deletion/1` receipt | Meeting is quarantined; the reader does not relabel unexplained loss as retention |
| Restart during correction or deletion | Operation resumes or rolls back from a receipt; no silent partial authority change |
| Delete audio | WAVs disappear through staged deletion; transcript, evidence, note, profile, and other meetings remain; note reads `audio-released` |
| Delete meeting | That meeting becomes unreachable atomically, then is removed; profile and other meetings remain |
| Untrusted transcript contains markup or script text | It renders as text under the local-only CSP and cannot invoke a command |
| Cold signed install on a fresh macOS account | Signature and bundled resources verify; prompts belong to the app; first capture, quit, reopen, and deletion are exercised |

## Release stops

- A passing deterministic test is mechanical evidence, not product approval.
- A real capture is not operator-confirmed review content.
- Human-curated review content is not an automatic product note.
- An approved encounter is not a working application.
- One accepted automatic note is not a beta.
- A working development build is not a cold signed install.
- One operator's canary is not a beta envelope.
- A limited headphone beta is not evidence for speaker mode.
- No GA claim is available until beta use establishes permissions, recovery,
  update behavior, privacy operations, useful notes, and the stated operating
  envelope on installed builds.

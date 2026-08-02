# macOS walking skeleton and delivery contract

## Status

The accepted interaction receipt remains the implementation contract for the
claim-to-canonical-transcript behavior it actually reviewed. Frozen storage, worker,
retention, recovery and evidence contracts also remain binding. It does not authorize
an unresolved whole-product navigation or composition.

The interaction gate in
[`encounter-acceptance.md`](./encounter-acceptance.md) passed on 2026-07-31 for
the exact digest-bound private page. The repository's fresh history and that
receipt do not permit private meeting artifacts in Git. They also do not prove
the application runtime or automatic-note quality, so no application build may
be described as beta-ready from this approval.

Product UI work is therefore back at a bounded design gate: first approve a running
synthetic interaction skeleton, then record that exact candidate as the composition
contract for the real walking skeleton. That later receipt can supersede layout,
navigation and screen geometry without weakening the already-proved evidence behavior
or non-visual contracts. The already-started profile lifecycle join may reach a clean
checkpoint because it does not choose the interface; guided enrolment, reset and other
new surfaces wait for the approved composition.

The transcript-only internal-alpha path is implemented and packaged with the real
local worker runtime. Commit
`5fe9aecd4f53204dc6e82573fd4b4dde37efd6d1` has a signed and notarized DMG that
passes the mechanical release suite and independent Gatekeeper verification.
The first hardware attempts correctly failed closed when macOS denied microphone
access. They exposed two release defects: recovery lost the specific permission
message, and the executable requesting microphone access lacked Apple's required
audio-input entitlement, so the app never appeared in System Settings. Both are
fixed and enforced by the signed-bundle verifier. The next hardware attempt
reached transcription and exposed a third defect: data-dependent library output
entered the worker's JSON-only protocol channel. Commit `8a2359f` isolates all
operation output from that channel, and commit `5fe9aec` strengthens the packaged
runtime regression so it invokes the real transcript model. The corrected
installed build subsequently completed two-leg capture and local transcription
on real hardware. Its completed transcript screen returned after a true quit and
fresh launch without emitting transcript text into the release receipt. The
one-day retention deadline is recorded locally; automatic deletion at that
deadline and clean transfer remain open. Until both pass, the alpha is not
cleared for distribution. Automatic-note admission remains a separate, unmet
beta gate.

The contract exists now so the first implementation does not have to settle
process ownership, persistence, recovery, and security while it is also trying
to prove a real meeting path.

## Current milestone plan

Status as of 2026-08-02. ETA ranges assume timely human review and no major reset in
automatic-note quality. Passing tests are bounded evidence; they do not advance a
human gate.

### Active delivery spine

Design proceeds **retrieval → commitments and notes → capture**. Implementation then
walks the operator's chronological path:

`Launch → Record → Stop → Transcribe → Library → Note → Evidence → Correct/regenerate → Retrieve`

The active visible stream is the first part of that spine: compare Meetings, Recorded
promises, and Find as possible default opening views using one shared synthetic corpus.
All three remain available in the composed product and converge on the same meeting,
note, canonical-transcript, evidence, correction, and regeneration destinations. Each
starting view must support finding an old decision, recognizing a gap, correcting the
record, regenerating the note and returning to retrieval. Operator approval binds the
exact default, first-class navigation, labels, and transitions. That composition then
becomes the implementation contract for a real installed vertical slice.

Find is not an equal-weight guess: it is the provisional default because the market
positions corpus retrieval as core value, Gong documents multiple retrieval entry
points, and the registered `n=3` colleague snapshot favors a question-shaped entry 2:1
over filters while scoring cited cross-meeting value 5, 4, and 5. Meetings remains the
first-class source/filter path; Recorded promises remains a prominent derived view.
The current beta still uses exact transcript-and-metadata search, not conversational
cross-meeting answers.

Keep the current synthetic corpus frozen until that navigation comparison closes; it
exists to hold evidence states and tasks constant. The next prototype flesh-out then
holds the approved navigation constant and uses a synthetic sales/discovery meeting,
the first-meeting scenario selected by 3/3 respondents. That slice compares the shared
note hierarchy—summary, decisions, actions/owners, open questions, risks/blockers—and
its evidence treatment without confounding the navigation decision.

The running comparison now separates the two controls explicitly: a dark reviewer bar
changes only the default opening, while the light app header keeps Find, Meetings, and
Promises persistently available. Moving among those product destinations preserves a
restored transcript turn, stale/regenerated note state, the resulting promise, and the
meeting's updated status. The remaining design gate is the operator's judgment of that
hierarchy, not whether the three capabilities can coexist mechanically.

| Wave | Current status and active stream | Join or exit | Human gate | ETA |
|---|---|---|---|---|
| A. Alpha release closure | The unchanged signed alpha is waiting for its natural one-day deletion event and a clean Mac or account transfer. PR #2 stays draft. | Bind both receipts to the frozen build, then reconcile the draft PR and release record. | Real transfer, permissions, capture, recovery, and deletion observation. | 1–3 calendar days |
| B. Shared-contract freeze | Complete and independently re-audited after one narrow correction. Implementation proved that supported macOS exposes no descriptor-based executable launch, so the original audited wording required an impossible primitive. The corrected contract keeps the signed interpreter, standard library, and dynamic libraries inside the release trust boundary and descriptor-retains every manifest-listed bridge-controlled resource. All other correction/regeneration, worker, recovery, artifact, receipt, and fixture contracts remain frozen. | Real projector transport must implement the corrected descriptor handoff, cancellation, and parent-death contract before admission. | None. | Complete 2026-08-01 |
| C. Trust foundation | In progress, with the fixed-slot lifecycle join parked as an audited implementation candidate rather than installed Preview work. The independent audit found two release blockers: initial slot publication can mutate a pathname before descriptor identity is proved, and receipt validation accepts impossible phase histories. The candidate also overstates volume readiness and must not be promoted. The independently audited restoration coordinator, development-only profile bridge and staged one-meeting audio-deletion facade remain bounded evidence. Capture admission and the frozen alpha command boundary are unchanged. Guided enrolment/reset, withheld-turn restoration, policy change and whole-meeting deletion remain. | Preserve the candidate and its passing tests, but do not install or promote it. Resume with descriptor-before-mutation publication, legal transition validation, strict encoder validation and guided enrolment/reset after the walking-skeleton prototype establishes their product place. | Retention-policy wording and far-end-notice choices; real deletion, profile policy, reset and withheld-turn decisions. | Cumulative 1–2 weeks after the design gate |
| D. Evidence-linked automatic notes | In progress. The private coordinator and inspect-only transport remain closed and recovery-tested. The corrected synthetic-only MLX harness now advertises and parses the same strict `{"items":[...]}` contract, binds immutable model/runtime identities, separates tree hashing and model load from per-call timing, and fails closed to `transcript-only`. The bounded two-fixture Qwen2.5 1.5B corrective probe was rejected: the supported fixture produced invalid JSON and the empty fixture returned the wrong root/shape. The full suite correctly did not run, and the runner now refuses that scope until a fresh-process orchestrator implements the registered 12-fixture cold/warm repeat matrix. SmolLM2's earlier result remains inconclusive. Neither model is admitted, no third candidate is scheduled, and no generator is wired into Preview. | Keep note work off the Preview critical path. Before any new model search, decide and preregister one bounded decoding/contract repair or close this small-model path. Admit a create bridge only after typed output, exact locators, fidelity, latency, memory, repeatability, and human semantic/usefulness gates pass. | Semantic support and usefulness adjudication. | Additional 2–3 weeks after a registered experiment passes |
| E. Product surfaces and retrieval | Rebaselined to prototype-first. The separate Preview proves bounded reader and voice-capability mechanics and renders the real Library, exact search, meeting detail, canonical transcript, retention/disk state and reviewed one-meeting audio-deletion interaction in the original light/editorial system. Those working surfaces are evidence, not automatic approval of the whole-product IA. The active stream now compares Meetings, Recorded promises, and Find as three default opening views at 960×900 against the same synthetic corpus, including evidence landing, uncertainty, correction/regeneration and return-to-retrieval. All three remain in the product; no prototype view writes product records or reads private meetings. The frozen alpha command boundary remains unchanged. | Operator approves one exact composed navigation system: default view, first-class destinations, labels, transitions, and shared detail/evidence surfaces. Deliver that composition as thin installed Preview increments. | Cold operator review of all starting views and explicit approval of one exact composition. | Prototype comparison 1–3 days; implementation remains within the cumulative 2–3 week surface range |
| F. Beta packaging and admission | Blocked by C–E. | Frozen build/model identities, installed canary, locator resolution, correction/restart/retention/deletion receipts. | Pre-run reference, semantic review, and operator usefulness verdict. | Cumulative 6–9 weeks |
| G. Production hardening and GA | Not started. | Clean accounts/Macs, upgrade/migration/rollback, fault injection, privacy/security, and content-free diagnostics. | Explicit beta admission and later GA release decisions. | Cumulative 9–14 weeks |
| H. Later extensions | Outside v1: optional EventKit brief, operator-authored live note, detection, and conversational cross-meeting retrieval. Speaker playback/AEC remains research. | Each extension receives its own contract and evidence. | Separate scope and release decisions. | 1–4 weeks each after v1; no AEC ETA before feasibility passes |

### Transcript fidelity, readability, and evidence navigation

This area records the worthwhile product opportunities from the CrisperWhisper
analysis without scheduling a runtime replacement or schema rewrite.

#### Product authority — adopted now

- The product has one canonical transcript: the closest supported record of what was
  audibly said. Notes are interpretation derived from it.
- Every transcript records an explicit transcription policy: faithful/verbatim-oriented
  at first, with model digest, decoding configuration, language, timing mode, alignment
  method, processing duration, and cold/warm state.
- Any cleaned text is a reversible **Readable transcript** presentation, never a second
  authoritative or “intended” transcript. Every readable phrase and note claim must
  resolve to exact canonical words; evidence links always land there.

#### First bounded experiment — after the active visible-reader slice

Use the existing pinned MLX large-v3-turbo model with `word_timestamps=True` over only
public or synthetic audio in an isolated sidecar. It must not write Preview or product
records. Compare the current deliberate anti-poisoning setting,
`condition_on_previous_text=False`, with one isolated continuation/seam arm. Do not
change the default unless registered long-form fixtures show fewer seam drops and
duplicates without error cascades. Smaller MLX variants may serve only as packaging or
latency controls; quality remains the gate.

Measure fillers, false starts, repeated words, corrections, names, numbers, negation,
silence hallucinations, looping, truncation or early end-of-transcript, long-form
seams, timing monotonicity, cold/warm latency, peak memory, and repeatability. Exit on
registered fidelity, timing, memory, and operator evidence-seek value, not the mere
presence of timestamps. This experiment is independent and does not block Library,
the note reader, trust controls, alpha receipts, or continual Preview delivery.

#### Conditional adoption — only after the sidecar passes

- Add optional typed word timing to transcript artifacts: word text, start, end,
  physical channel, model/alignment provenance, and whether timing is decoded, aligned,
  or interpolated.
- Keep the current claim-to-text character locator authoritative. Time augments it with
  channel/audio seeking; it never replaces it or strengthens approximate alignment.
- Prove phrase-level audio seeking in a disposable viewer first. Require finite ordered
  times, correct channel and duration bounds, exact text-locator resolution, and
  operator review before Preview integration.
- Join deterministic seam, silence, looping, fallback, and early-termination fixtures
  to the permanent suite. Diagnostics remain content-free: model identity/digest,
  duration, cold/warm state, timing mode, and failure category.

#### Readable transcript — after canonical timing and fidelity pass

Prototype a reversible view over the canonical transcript. It may visually suppress
fillers and repeated fragments or normalize punctuation, casing, and formatting. It
must not silently alter names, dates, numbers, negation, commitments, or ambiguous
corrections. One action reveals the exact original passage and, only if timing passes,
plays the correct channel interval. A transformation that cannot preserve exact word
mapping is interpretation and belongs with generated notes, not the transcript.

Run a cold operator comparison on reading speed, trust, locator corrections, and
usefulness before admission. The current MLX model does not claim CrisperWhisper's
learned controllable modes; this plan adopts the product separation, not that model
claim.

#### Later correction and alignment research

Investigate whether operator-corrected text can regain approximate word timing through
alignment. Forced or interpolated timing must stay labelled approximate and cannot
strengthen evidence or masquerade as decoded timing. A glossary/hotword concept for
names and domain terms requires an independently licensed local implementation and a
registered accuracy test. “Verbatimize” is not a requirement; the only relevant idea
is correction-to-audio reconciliation, never synthesizing disfluencies into the
canonical record.

#### Explicit non-adoptions and blockers

- No CrisperWhisper weights or outputs enter Product or Preview without a separate
  commercial licence. Its non-commercial weights remain research-only.
- No PyTorch runtime migration is scheduled for this macOS-arm64 envelope. PyTorch is a
  valid research environment; CrisperWhisper's measured MPS selection and Transformers
  fallback defects are packaging defects, not general PyTorch defects.
- No dual authoritative transcripts, diarization, speaker identity, overlap
  resolution, live transcription, or speaker-mode admission follows from this work.
- No approximate forced alignment is evidence, and no runtime, model, schema, or
  signing change is made merely to demonstrate a concept already testable in MLX.

The adoption order is therefore: finish the current visible reader prototype; run the
independent MLX word-timestamp and fidelity benchmark; join only passing contract and
test ideas into trust/evidence work; prototype Readable transcript only after canonical
timing and evidence-seek review pass. Every shipped feature still requires the existing
human semantic, usefulness, and release gates.

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
  product-development inference; and
- no transcript-evaluation submission, recording contribution, telemetry upload, or
  research-transfer service.

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

The alpha exposed a smaller ownership fork inside the chosen shape. It was checked
against permission attribution, a Rust `SIGKILL`, a worker crash, the durable attempt
and ownership receipts, capture finalization, and fresh-process recovery:

| Capture-child candidate | Result |
|---|---|
| Python spawns and controls Swift | Rejected. It inserts the model process between Rust's consent/reducer authority and the permission-bearing capture child, while Rust still has to inspect both identities and recover their shared process group. |
| Rust spawns and controls Swift; Python validates finalized artifacts | **Chosen and implemented by the alpha.** It follows Tauri's Rust-side external-binary pattern, keeps Start/Stop under the same authority as consent and recovery, and leaves Python as the canonical capture/transcript/note validator. |
| A separate capture daemon owns Swift | Rejected. It adds another lifetime, readiness surface, and recovery authority without removing either existing child. |

The shipped alpha code is the internal reference implementation for the chosen
sub-boundary. The earlier Python-owned diagram below was a stale design claim, not
authority to rewrite the working capture path.

## Chosen process shape

```text
Tauri webview
  named commands and escaped display data
          |
          v
Rust session core
  reducer | tray | consent | policy | recovery | diagnostics
          |\
          | \ attempt-scoped control bytes and capture events
          |  v
          |  Swift Core Audio tap
          |  microphone + system acquisition only
          |
          | versioned JSON lines over stdin/stdout
          v
Python worker
  capture finalization/inspection | transcript | note | profile validation

$APP_DATA
  meeting records | canonical capture/transcript/note artifacts | profile
```

Rust starts the application-scoped worker and attempt-scoped Swift tap and owns
their alpha process group. It may create the Swift tap only after an approved
attempt receipt is durable, and the tap stays in that group. Stopping, timing
out, or exiting the application must stop and wait for the alpha group. A
one-shot note child uses its own separately owned process group under the rules
below; it never joins or changes alpha ownership. The worker never starts or
stops capture; after Swift closes both WAV legs, `capture.finalize` validates them and
creates the canonical capture-session receipt.

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
Process existence is checked independently with `kill(pid, 0)`: only `ESRCH`
means absent. A successful probe or `EPERM` without a complete inspectable
identity remains ambiguous. If identity cannot be proven, Start stays blocked
and recovery explains why without signalling an unrelated process.

There is no `launchd` job. A job that can restart or outlive the Tauri
application conflicts with per-attempt consent and makes process ownership
ambiguous after a crash.

### Private one-shot note bridge

Wave D does not add `note.create` to the transcript-alpha worker or introduce a
second application-scoped service. Rust may spawn a separately manifested,
one-shot Python note child after alpha readiness. Each child sends one
`note-bridge-event/1` ready frame, accepts exactly one
`note-bridge-command/1` request, emits exactly one role-specific terminal result,
and exits. The create role advertises only `note.create`; the independent
inspection role advertises only `note.inspect`. A create child and the fresh
child that inspects its output are separate processes.

Claim retrieval needs canonical claim text and resolved locators, but the frozen
`note.inspect` result deliberately returns only artifact digests. Three seams
were compared before adding that authority:

| Shape | Consequence | Decision |
|---|---|---|
| Parse `note/2` again in Rust after `note.inspect` | Keeps one worker operation, but creates a second semantic note and locator validator that can disagree with the Python authority. | Rejected. |
| Add claims to the existing `note.inspect` result | Avoids another operation, but silently changes the digest-only contract already used by note generation and recovery. | Rejected. |
| Add a separate read-only `note.project` role and result | Keeps `note.inspect` unchanged, reuses the same coherent Python validation, and gives Rust only the bounded current-claim projection it needs. | Chosen. |

The project role advertises only `note.project`. It uses the same validator-only
runtime as inspect: `generator` is null and `models` is empty. It is read-only,
creates no app data or receipt, and is not a note generator. The role remains
private and unregistered until its Rust-owned process transport, exact parser,
library join, corpus bound, and cold surface review pass.

The app fixes the private storage root and verifies one closed `note-runtime/1`
manifest before spawn. Its fields, in canonical order, are `schema`, `role`,
`runtime`, `bridge`, `validator`, `generator`, and `models`. Runtime, bridge, and
validator each contain only `relative_path` then lowercase `sha256`, in that
order. Generator is either null or an object containing `id`, `relative_path`,
and `sha256`, in that order. Each model uses that same field order. Bundle-relative paths must resolve below
the verified resource root without links. IDs are unique, model rows are sorted
by ID, unknown fields are refused, and every identifier and relative path is
ASCII restricted to letters, digits, `.`, `_`, `-`, and `/`; empty components,
`.`/`..`, backslashes, control characters, and JSON escapes are refused. The manifest identity is the SHA-256 of
two-space pretty UTF-8 JSON in this field order with no terminal newline.
`role: inspect` and `role: project` require `generator: null` and `models: []`; `role: create`
requires an admitted generator and its complete nonempty model inventory.
macOS has no supported `fexecve` or `execveat` equivalent and refuses execution
through `/dev/fd`. The executable therefore has a deliberately separate trust
boundary from the resources it loads. A product-admitted interpreter must be a
nested Mach-O named by the closed bundle manifest, signed with the same Developer
ID team as the strictly verified outer application, covered by the hardened
runtime, and bound by its exact SHA-256. Release verification checks the nested
signature, team, path, digest, outer signature, notarization, and Gatekeeper
result. Rust also opens and hashes that path without following links immediately
before spawn. Those pre-spawn signature, path, and digest checks are the launch
trust boundary; the current worker may receive the fixed storage root at spawn.
Rust then refuses the child before sending a command or meeting identifier unless
the spawned PID resolves to the same regular-file identity and digest. This is a
platform-signed executable boundary, not descriptor-pinned execution.
Development or ad-hoc executables cannot satisfy product admission.
The interpreter's packaged standard library and dynamic libraries remain inside
that same strictly verified signed-runtime boundary; they are not
bridge-controlled manifest resources and are not described as descriptor-pinned.

Every manifest-listed bridge-controlled resource remains descriptor-pinned. Rust opens the
resource root with Darwin `O_NOFOLLOW_ANY | O_DIRECTORY | O_CLOEXEC`, then opens
the manifest, bridge, validator, generator, and models relative to that retained
root with `openat` and `O_NOFOLLOW_ANY | O_CLOEXEC`. It requires regular
bundle-owned files, hashes their descriptor bytes, and compares them with the
manifest. The parent descriptors remain `O_CLOEXEC`. Child-only `dup2` actions
map them to closed deterministic descriptor numbers and clear close-on-exec only
on those duplicates immediately before launching the interpreter. The
bootstrap is compiled into the signed Rust application and passed as the fixed
Python `-c` program; it is not another bundle pathname. For bridge-controlled
resources, the interpreter receives only those descriptor numbers. Its other
fixed launch inputs are the compiled bootstrap, fixed storage root, and expected
parent PID. It receives or reopens no bridge-resource pathname. The bootstrap
hashes and executes the bridge bytes from its inherited descriptor, and the
bridge loads the manifest, validator, generator, and models from their inherited
descriptors. It rechecks size, owner, mode, device, inode, and digest before
ready. A library that reopens a bridge-resource pathname does not meet this
contract. Ready echoes the digest of the
descriptor-read manifest only after the actually loaded resources pass; echoing
a supplied digest is not evidence.

This boundary protects against stale, linked, replaced, or mismatched bundle
resources and against sending meeting authority to an unverified child. It does
not claim to close a transient executable-path replace/restore race between the
bracketed checks. Exploiting that race requires an active same-account attacker,
which this boundary excludes because that account already has direct authority
over the owner-only meeting store. Defending against that actor would require a
separately sandboxed, monolithic signed helper and a new security contract.

Three implementable shapes were compared after the descriptor-execution audit
failed:

| Shape | Consequence | Decision |
|---|---|---|
| Port the Python note validator into Rust | Removes the interpreter boundary but creates the second semantic authority this role exists to avoid. | Rejected. |
| Copy a verified interpreter and resources into a private request snapshot | Conflicts with the receipt-free temporary-copy prohibition and adds a transient writable-executable publication, cleanup, and crash-recovery surface while still relying on a pathname at `exec`. | Rejected. |
| Use the signed nested interpreter and inherit verified resource descriptors | Matches the existing signed-app boundary, keeps one Python semantic authority, and removes pathname reopening for every bridge-controlled byte. | Chosen. |

The ready frame is exactly:

```json
{
  "schema": "note-bridge-event/1",
  "event": "ready",
  "protocol": 1,
  "role": "inspect",
  "manifest_sha256": "<note-runtime/1 digest>",
  "operations": ["note.inspect"]
}
```

The create role substitutes `create` and the one-element operation list
`["note.create"]`; the project role substitutes `project` and
`["note.project"]`. Role, manifest digest, and operation list must exactly match
the verified manifest. Unknown fields, enum values, duplicate operations, or a
different order are protocol failure.

The single command has fields `schema`, `request_id`, `operation`, and
`arguments`, in that order; duplicate, missing, unknown, or reordered keys are
refused. `request_id` is a canonical lowercase hyphenated UUID and must match
the terminal result. Create arguments are exactly the frozen `meeting_id` and
`source_transcript_sha256`. Inspect arguments are exactly `meeting_id`,
`note_id`, and `transcript_id`, in that order. Project uses those same three
ordered arguments. `meeting_id` follows the shared opaque meeting-ID predicate:
1 through 128 ASCII alphanumeric, `-`, or `_` bytes and neither `.` nor `..`.
`note_id` and `transcript_id` are lowercase SHA-256 values. No path, prompt,
model name, or storage root crosses the frame.

The terminal result has fields `schema: note-bridge-result/1`, `request_id`,
`operation`, `outcome`, `artifact_digests`, and `failure`. Outcome is the closed
enum `succeeded`, `note-rejected`, or `refused`. Success has `failure: null` and
exactly the three frozen digest keys `note`, `note-markdown`, and `transcript`.
Only create may return `note-rejected`; it has empty digests and exactly
`{"code":"note_rejected","recoverable":true}`. Refusal has empty digests and
one content-free failure code from `invalid-request`, `artifact-missing`,
`artifact-changed`, `artifact-invalid`, `runtime-unavailable`,
`generator-unavailable`, or `internal-error`, plus a Boolean `recoverable`.
Refusal never becomes a persisted note rejection. Unknown or missing fields,
wrong role/operation combinations, a second result, or success at end-of-file
without the exact result are protocol failure.

`note.project` leaves that result unchanged and uses a distinct
`note-projection-result/1` frame. Its fields are exactly `schema`, `request_id`,
`operation`, `outcome`, `projection`, and `failure`, in that order. Operation is
`note.project`; outcome is `succeeded` or `refused`. Success has `failure: null`
and one `note-claim-projection/1` object. Refusal has `projection: null` and one
content-free failure object whose fields are exactly `code` then `recoverable`.

The projection fields are exactly `schema`, `note_json_sha256`,
`note_markdown_sha256`, `transcript_sha256`, and `claims`, in that order. The
three identities must equal the coherent, freshly re-inspected artifact
snapshot. Claims remain in canonical note read order. Every claim row has
exactly `claim_ordinal`, `claim_sha256`, `claim_type`, `evidence_state`, `claim`,
and `locators`, in that order. `claim_ordinal` is a zero-based contiguous JSON
integer no greater than 2^64 - 1 and equal to the row's array position; a
Boolean is not an integer.
It is the row identity within the exact note digest. `claim_sha256` is the
lowercase SHA-256 of the claim's UTF-8 bytes. It is never a row identity and may
repeat without qualification; only `claim_ordinal` within the exact note digest
identifies a row. `claim_type` is `decision`, `action`, `proposal`, or `question`.
Current accepted `note/2` authoritatively re-derives
only `evidence_state: located`; every claim therefore has one through three
locators. `composed`, `untestable`, and `unquoted` remain later Wave D states
that require a note-schema and validator change plus separate beta admission.
Projection cannot infer or introduce them. Claim text is the canonical nonempty
product claim of at most 160 Unicode scalar values.

Each locator has exactly `turn`, `start`, `end`, and `text_sha256`. Turn, start,
and end are JSON integers from zero through 2^64 - 1 and Booleans are refused.
`turn` is less than the exact transcript turn count; offsets are half-open Unicode-scalar indices
with `start < end <=` that turn's Unicode-scalar count. `text_sha256` is the
lowercase SHA-256 of the UTF-8 encoding of the exact scalar slice. Locator rows
are unique and sorted by `(turn, start, end, text_sha256)`. Python derives these
rows only after the same descriptor-pinned note, Markdown, transcript,
evidence-graph, and rendered-claim checks used by `note.inspect`; it never
trusts stored claim rows alone. An empty claims list is valid. No partial
projection is valid.

The serialized result plus newline remains inside the existing 65,536-byte
frame. A valid note whose complete projection does not fit returns only
`projection-capacity-exceeded`, `recoverable: false`; it never truncates claims.
Other project refusals are the inspect set with the same recoverability:
`invalid-request`/false, `artifact-invalid`/false,
`artifact-missing`/true, and `artifact-changed`/false. Transport, timeout,
runtime failure, malformed output, or an unrecognized refusal is protocol
failure. Artifact missing, invalid, or changed quarantines that ready meeting;
the library never exposes it as transcript-only. Projection capacity failure
fails the whole rebuild as `library-capacity-exceeded`. Invalid request,
transport, timeout, runtime failure, malformed output, or an unknown refusal
fails the whole rebuild as `artifact-unavailable`. A snapshot assembled from
only some claims or only some projectable ready meetings is never published.
The protocol-only, content-free case pack is
`tests/fixtures/note-projection-v1.fixture`. Its non-prose tokens freeze valid
commands, all admitted claim types and locator cardinalities, duplicate claim
text including otherwise identical repeated rows, shared locators, Unicode-scalar
landing, refusal mapping, deterministic capacity/no-truncation, recursive exact
field order, and duplicate/unknown-field rejection. It is not evidence that any
product note is valid.

Role fixes the refusal codes and their mapping. Create accepts only
`invalid-request` with `recoverable: false`, which maps to
`NoteGenerationWorkerError::Refused`; and `runtime-unavailable`,
`generator-unavailable`, or `internal-error` with `recoverable: true`, which map
to `NoteGenerationWorkerError::Unavailable`. Inspect accepts only
`invalid-request`/false and `artifact-invalid`/false, which map to
`NoteArtifactError::Malformed`; `artifact-missing`/true, which maps to
`NoteArtifactError::Missing`; and `artifact-changed`/false, which maps to
`NoteArtifactError::Changed`. Transport, timeout, or child-runtime failure is not
a refusal frame; the concrete inspector must add and return an internal
`NoteArtifactError::Unavailable` before it may bind to the coordinator. The
inspect-only probe therefore cannot implement that trait yet. A create
`note-rejected` result reconstructs exactly `NoteCreateWorkerFailure` with code
`NoteRejected`, `recoverable: true`, and an empty artifact-digest map. The command
schema must be exactly `note-bridge-command/1`, and the result's request ID and
operation must equal that command.

A frame is at most 65,536 bytes including its newline; stderr is capped at 16
KiB and may not contain meeting text. Ready is bounded to 10 seconds and
inspection or projection to 30 seconds. The initial 15-minute creation ceiling is provisional
until cold-start measurement. Timeout, explicit cancellation, malformed output,
extra frames, or identity mismatch terminates the one-shot process group, waits
750 milliseconds, then kills and waits if needed. The transport accepts one
cloneable cancellation token and polls it while waiting for ready, result, or
exit; cancellation has a distinct internal outcome and may not publish a partial
snapshot. On macOS the child watches the expected parent PID with `kqueue`
`EVFILT_PROC | NOTE_EXIT`, checks its parent before and after registering that
watch, and exits if the parent changes or ends. This avoids the non-atomic
`pipe` then `FD_CLOEXEC` window on a platform without `pipe2`. The child may not
detach, create a new session, or mask or close the parent watch. The first bridge version forbids generator/model
subprocesses, so the owned group contains only the direct one-shot child;
admitting descendants later requires a new ownership contract. Normal
shutdown stops and waits for the one-shot group.

Each create or inspect spawn that participates in a durable note operation gets
a UUID request directory below that operation:
`children/<request-id>/`. Before Rust sends the command, it writes an immutable,
owner-private `ownership.json` with schema `note-child-ownership/1`, operation
ID, request ID, role, manifest SHA-256, PID, process start time, process-group ID,
and executable relative path and SHA-256. After Rust has waited for that exact
child, it writes `exit.json` with schema `note-child-exit/1`, the same operation,
request, manifest, and process identity, completion time, and the closed outcome
`observed-exit`, `terminated`, or `absent-after-crash`. The phase-specific
`observed-exit` shape alone carries an integer exit code from 0 through 255; the
other shapes omit that field. Both receipts are content-free and refuse unknown,
explicit-null, or phase-forbidden fields. A new attempt
uses a new request ID and directory; it never overwrites an earlier child
receipt.

Fresh recovery scans child ownership before retrying a request or inspecting a
stored result. An ownership receipt without an exit receipt requires the same
independent PID existence and exact start-time, group, executable-path, and
digest comparison used for capture recovery. Rust signals and waits only for an
exact match. `ESRCH` is absent; `EPERM`, a live mismatched PID, or an identity
that cannot be inspected is ambiguous and blocks note recovery without
signalling. Recovery writes the exit receipt only after absence or exact cleanup
is established. It cannot begin worker retry or meeting mutation while an
identity-bound child remains live or ambiguous.

Rust alone owns `.writer.lock`, the active-meeting lease, durable operation
receipts, meeting publication, and recovery. The one-shot child never receives
or contends for the writer lock. The lease spans request persistence, child
execution, fresh inspection, meeting publication, and terminal commit. Success
is exactly the frozen three-digest result. Generator rejection is exactly
`note_rejected`, `recoverable: true`, and no artifact digests. Missing runtime or
model, timeout, malformed output, or protocol failure is worker unavailability,
not note rejection. A crash after immutable artifact creation but before result
storage leaves those bytes without product authority.

Projection is not a durable note operation. It takes no writer lock, writes no
ownership or exit receipt, and publishes no persistent projection. Rust owns
the one-shot child lifetime and keeps a successful result only inside the
immutable in-memory library snapshot. Project may not write note, transcript,
claim, locator, or rendered-note bytes outside canonical storage. Its semantic
validation operates on descriptor-retained bytes and in-memory objects; the
temporary snapshot copies currently used by the inspection harness are not an
admissible implementation for this receipt-free operation.

Note recovery runs only after existing ownership recovery, interrupted deletion,
newly due retention, and unchanged transcript-alpha readiness have completed,
but before note-library exposure. Note-runtime
failure may quarantine the affected operation and disable note work; it cannot
change alpha readiness. No command, UI capability, semantic-quality claim, or
beta admission follows from this private bridge.

The create role is not implemented or advertised until a fixed generator and
model identity are admitted. Before then, validator-only inspect and project
one-shots may exist only in the repository test harness, using a temporary
private root that the harness removes after the child has exited. They are not
packaged, installed, started by the app, or permitted to write app data or an
ownership/generation receipt. They may prove framing, confinement, liveness,
timeout, changed-artifact refusal, and exact projection, but may not implement
`NoteGenerationWorker`, enter the note coordinator, or translate missing
generation into `note_rejected`.

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
| Python worker | Versioned operations over capture finalization and the existing profile, transcript, and note validators | Capture-child launch or Stop, product readiness, arbitrary commands or paths, retention policy, UI state |
| One-shot note child | One manifested create, inspect, or project operation; immutable note publication for create; and Python-owned note semantics. Project is read-only and returns only an in-memory current-claim projection. | Application lifetime, alpha readiness, writer lock, meeting pointers, recovery ordering, persistent projections, project artifact publication, receipts, commands, or UI state |
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
  "schema": "worker-event/2",
  "event": "worker.ready",
  "protocol": 2,
  "admission": "internal-alpha",
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
    "capture.finalize",
    "capture.inspect",
    "transcript.create"
  ]
}
```

Every command has one request identifier and one terminal result:

```json
{
  "schema": "worker-command/2",
  "request_id": "<uuid>",
  "operation": "capture.finalize",
  "arguments": {
    "meeting_id": "<uuid>",
    "started_at_epoch_seconds": 1785600000,
    "capture_elapsed_samples": 960000
  }
}
```

The worker does not emit capture progress; Rust receives capture events directly from
Swift. Results use the command's request identifier:

```json
{
  "schema": "worker-result/2",
  "request_id": "<uuid>",
  "ok": true,
  "code": null,
  "recoverable": null,
  "artifact_digests": {
    "capture-session": "<sha256>",
    "capture-mic": "<sha256>",
    "capture-system": "<sha256>"
  }
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
- `operations` lists runnable operations for the stated runtime admission. A
  reserved name or adapter that always refuses is not a capability and must not
  appear. `note.create` joins the product-admission list only with its executable
  implementation and acceptance fixtures.

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
  library/                        0700
    metadata.json                 0600, optional organization record
  profile/                        0700
    voiceprint.json               0600, profile bytes or zero-byte absence marker
    lifecycle/                    0700
      receipt.a.json              0600, alternating journal slot
      receipt.b.json              0600, alternating journal slot
      reset.tombstone             0600, zero when idle
      enrollment.staged          0600, zero when idle
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
        audio-deletion.json       0600
```

The application form of `capture-session/2` is the immutable acquisition
receipt. Its closed payload is `session.json`, `mic.wav`, and `system.wav`;
`verify_acquisition` re-derives capture health and reconciles the stored byte,
mode, name, and digest inventory before ASR begins. Transcript revisions are
written only below `transcript/` and are never copied back into `capture/`.

The existing `verify_capture` entry point remains the stricter validator for
combined research and machine-transfer packets that intentionally co-locate
segment evidence and `transcript.json` with the audio. That packet shape is not
the application's durable storage layout. Keeping the two validators explicit
avoids making either the capture receipt or a copied transcript a second
authority for the other.

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

`meeting.json` is the mutable application-owned `meeting/2` receipt. Its closed
shape is:

```text
schema, meeting_id, lifecycle
retention { rule, policy_sha256, next_deletion_at_epoch_seconds,
            state, deletion_receipt }
artifacts { attempt, ownership, capture_session, microphone_audio,
            system_audio, current_transcript, current_note }
pending_storage_operation
```

Every artifact reference contains only an exact relative path and lowercase
SHA-256. A current-note reference contains the JSON and Markdown references plus
the SHA-256 of its source transcript; it contains no copied meeting text.
`meeting/2` has stable content lifecycles `incomplete`, `captured`,
`transcript-ready`, `transcription-failed`, `summary-failed`, `ready`, and
`recovered-interrupted`. Live `transcribing` and `summarizing` remain reducer
states: the durable record stays at its last retry source until validated
artifact bytes commit.

Audio retention is orthogonal to that content lifecycle. Its states are
`never-created`, `retained`, `deleting`, and `released`. Releasing audio does not
erase whether the retained transcript and note are ready. Quarantine is a
startup-library disposition, not a meeting lifecycle: an inconsistent record is
left byte-for-byte untouched and excluded from the projection.

The earlier `meeting/1` safety-skeleton shape is not silently upgraded: it lacks
the provenance needed to authorize recovery or deletion. A scanner leaves such
a development record untouched and quarantines it until an explicit migration
contract exists.

Application writes use a same-directory temporary file, file `fsync`, atomic
no-overwrite or replace as appropriate, and parent-directory `fsync`. A replace
followed by a parent-directory `fsync` error has an uncertain durability result;
the application does not advance in-memory status, and fresh recovery accepts
only a complete state whose referenced bytes reconcile. The
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

### Correction and regeneration revisions

Three persistence shapes were compared against the real withheld-turn and
rejected-note cases:

| Shape | Consequence | Decision |
|---|---|---|
| Rewrite the current transcript and add a stale boolean | Smallest surface, but destroys the original gate decision and permits a ready note to bind words that changed underneath it. | Rejected. |
| Immutable transcript views plus immutable operation receipts | Preserves the captured transcript, makes stale-note status derivable, and fits the existing current-artifact pointers. | Chosen. |
| Event-source every meeting mutation in `meeting/3` | Strong recovery model, but adds a migration and a second indexing system before one correction path works. | Defer until measured need. |

The first-beta correction is deliberately narrow: restore a turn that the
voice gate withheld. It is not free-form transcript editing. The Tauri command
`restore_withheld_turn` and worker operation `transcript.restore` carry only
`meeting_id`, the exact current transcript SHA-256, and the source turn index;
they cannot carry replacement meeting text or a path. The worker
re-validates that the source revision is current and the selected source turn
is actually withheld, then creates a content-addressed `transcript-view/1`
overlay. The overlay binds the original capture-transcript digest, its parent
view digest, and the cumulative sorted set of restored source-turn indices. It
copies no meeting text. Readers resolve that overlay against the immutable base
transcript and refuse a missing, changed, cyclic, non-withheld, or already
restored source-turn reference. A restore must add exactly one new base-turn
index; it cannot produce a no-op successor chain.

The executable contract is owned by
`crates/session-core/src/operations.rs` and the single cross-runtime fixture
`tests/fixtures/product-operations-v1.json`. The Tauri/JavaScript boundary uses
the command names above with `camelCase` argument and response fields. Worker
commands for the application-scoped worker use `snake_case` fields under
`worker-command/2`. The one-shot note bridge is the sole exception and uses its
closed `note-bridge-command/1` shape below. Both sides refuse
unknown fields. Rust additionally binds request, result, view, and commit
digests and identities, including the canonical `meeting.json` bytes named by
the terminal commit. Python independently validates the worker-facing
arguments and joins every returned digest to the inspected transcript view or
note pair. The recoverable `note_rejected` worker result maps only to the
artifact-free `note-rejected` persisted outcome. These field names, enum values,
schema tags, and hashing bytes are the Wave B definitions. Content-addressed
contract objects use their schema field order, two-space pretty JSON, UTF-8,
and no terminal newline; the fixture freezes those exact bytes across Rust and
Python. An implementation stream may consume them but may not silently redefine
them.

Publishing the new transcript pointer clears `current_note` and returns the
meeting to `transcript-ready`. The old note files remain immutable. The
correction receipt binds their exact references and the successor transcript,
which is the durable statement that they are stale; stale notes never enter the
current library projection. `regenerate_note` is a separate Tauri command bound
to the exact current transcript digest and dispatches `note.create`. A passing
`note/2` pair may advance the meeting to `ready`. A rejected run advances to
`summary-failed` with no current note, rendered claims, or claim-derived counts.
The first beta shows one fixed product message: the transcript is available, a
note was not accepted, and regeneration can be retried. Its terminal operation
receipt keeps a bounded failure code for diagnostics and retry analysis, but
`meeting/2` does not select one historical failure receipt as current UI
authority. A research-only `passed: false` diagnostic never enters the product
notes directory.

Correction and generation each use an owner-private
`operations/<operation_id>/` directory with immutable `request.json`, optional
validated `result.json`, and terminal `commit.json` receipts. Recovery applies
an uncommitted result only when `meeting.json` still names the request's source
revision. If `meeting.json` already names the result's successor, has the
expected lifecycle, and has cleared or replaced the exact prior note as the
operation requires, recovery writes the missing terminal commit instead. Every
other source/result/pointer combination is refused without mutation. Request
alone is retryable; a validated result can be committed after reinspection; a
commit must reconcile with `meeting.json`. An orphan artifact without a bound
result remains private but has no product authority. More than one nonterminal
operation for a meeting is quarantined rather than ordered by guesswork. Future correction,
generation, and deletion writers must take the same active-meeting lease and
storage sequence gate as capture. A correction also refuses before request or
recovery work while `meeting.json` names any pending storage operation, and it
rechecks that condition before publishing a result or writing a missing commit.

Note JSON and Markdown have independent content identities. Product storage is
`notes/<json_sha256>.json` and `notes/<markdown_sha256>.md`; the JSON's
`render.path` must name the latter digest, and its `transcript` field must be
exactly `../transcript/<current_transcript_sha256>.json`. The Markdown digest is
known first, then the JSON is encoded and named by its own digest. This avoids
the impossible earlier rule in which the JSON embedded a Markdown filename
derived from the still-unknown JSON hash. Product `note/2` also sets
`meeting.id` to the enclosing application meeting ID; the research writer's
transcript-stem fallback has no product authority. `note.inspect` accepts digest IDs,
recomputes all three files, validates the `note/2` pair and claim locators, and
returns only those digests. `note.create` is not advertised until it implements
this exact publication contract.

The library is rebuilt by scanning and validating meeting records at startup.
That is adequate for the bounded, single-user beta and avoids a transaction
split between a database and immutable files. A future SQLite index may be
added only as a rebuildable cache after measured library size makes the scan a
problem. It cannot become the sole copy of transcript, note, or evidence data.

### Exact library retrieval

Current executable status: a private Rust spine now implements the first read
paths below. It verifies canonical meeting, attempt, static lifecycle,
deletion-reference, and current transcript identities; retains metadata-only
rows for the four non-transcript lifecycles; and refuses a partial projection at
configured limits. Its descriptor-bound `library/metadata.json` reader rejects
unsafe ownership, modes, links, flags, ACLs, extended attributes, resource
forks, blocking special files, and path or identity drift. Exact normalized
search covers retained transcript text, operator titles, and folder names.
Withheld and malformed metadata text stay out of debug output, and opening a hit
re-inspects its exact meeting, attempt, transcript, and metadata authority.

The reader and its repairs passed an independent adversarial audit with no open
P0, P1, or P2 findings. That is bounded source and test evidence, not beta
admission. An installed production-branch positive read on clean APFS, a real
extended-ACL rejection fixture, and a deterministic concurrent replacement-race
harness remain unproven. Claims and current-note precedence, restored transcript
views, paging and cursors, mutations, the synthetic corpus benchmark, Tauri/UI
registration, and cold review also remain.

The first beta includes exact, non-generative search across the validated local
library. It does not include conversational or semantic cross-meeting retrieval.
The accepted 2026-07-31 encounter contained no cross-meeting search; the working
library and search surface therefore needs its own cold review before command
registration. Calling exact search and generated retrieval by one name obscures
a beta requirement behind an excluded research capability.

Rust rebuilds one in-memory `library-projection/1` after every fresh launch from
canonical meeting records and their current validated artifacts. The projection
is never persisted. SQLite, full-text indexes, embeddings, and per-meeting
search sidecars are deferred until a measured corpus exceeds the bounded scan
envelope. No derived index may become the sole copy of a meeting, transcript,
note, locator, or library label.

Library organization has one separate canonical record at
`library/metadata.json`. Its `library-metadata/1` fields are exactly `schema`,
`revision`, `folders`, and `meetings`, in that order. `revision` is an unsigned
64-bit integer. `folders` is sorted by `id`; each row has exactly `id` then
`name`. Folder IDs are unique lowercase UUIDs generated by Rust. `meetings` is a
sparse list sorted by `meeting_id`; each unique row has exactly `meeting_id`,
`title`, and `folder_id`. `meeting_id` follows the existing `meeting/2` opaque-ID
contract rather than a new UUID-only rule. `title` and `folder_id` are nullable;
null folder means `Unfiled`, and a nonnull folder must name a row in the same
record. A row for a meeting that has no safe current `meeting/2` is malformed,
not a hidden archive.

Names and titles are trimmed NFC Unicode strings from 1 through 120 scalar
values with no control characters, `/`, `\\`, or Unicode line separators. The
record contains no transcript, note, query, locator, participant, or profile
text. `library/` is `0700`; the record is a regular owner-owned `0600` file with
link count one and no symlink, hard-link, flags, ACL, xattr, or resource fork.
It is capped at 1 MiB, refuses unknown or duplicate JSON fields and duplicate or
unsorted rows, and is replaced atomically under the process writer lock only
when `expected_revision` equals the retained record. A changing mutation writes
exactly `revision + 1`; overflow refuses. A semantic no-op returns the unchanged
revision and writes nothing. A missing record means revision zero with no rows.
A malformed record is left untouched; meetings remain readable under generated
date-based labels in `Unfiled`, while organization mutation is disabled and a
content-free recovery diagnostic is shown.

Creating, renaming, or deleting a folder and assigning, unfiling, or titling a
meeting changes only this record. Deleting a folder atomically sets every row
that names it to `folder_id: null`. Whole-meeting deletion is not admitted until
its staged operation removes the metadata row in the same recoverable sequence
as the meeting bytes; leaving title or folder text behind is not successful
whole-meeting deletion.

Startup constructs no partial search authority. It first:

1. enumerates directories whose names satisfy the existing opaque meeting-ID
   predicate, without following links;
2. validates each `meeting/2`, re-inspects its exact `capture-attempt/1`, and
   uses only that receipt's `created_at_epoch_seconds` as capture time;
3. applies the closed lifecycle table below, inspecting transcript or note bytes
   only when that lifecycle requires them;
4. re-reads the meeting pointer, attempt identity, and metadata revision after
   inspection so a concurrent committed operation cannot publish a stale view;
   and
5. excludes an inconsistent meeting without moving or rewriting it, while
   continuing to validate the rest of the corpus.

| `meeting/2` lifecycle | Library row | Search authority |
|---|---|---|
| `incomplete` | `incomplete` | Metadata only; no transcript or claims |
| `captured` | `captured` | Metadata only; the live reducer may separately show `transcribing` |
| `transcription-failed` | `transcription-failed` | Metadata only; retry remains available |
| `recovered-interrupted` | `recovered-interrupted` | Metadata only; recovery remains available |
| `transcript-ready` | `transcript-only` | Validated current transcript; no claims |
| `summary-failed` | `summary-failed` | Validated current transcript; no claims |
| `ready` | `ready` | Validated current transcript and current `note/2` claims |

`empty` means no valid meeting rows, not “no accepted notes.” Invalid records
contribute only to the quarantined count. Only after the complete bounded scan
does Rust publish an opaque `snapshot_id`. Search over a rebuilding,
capacity-exceeded, or wholly failed projection returns that state; it never
searches a prefix and calls the absence a result.

Every authoritative change invalidates the current snapshot before mutation:
correction, regeneration, metadata replacement, retention, audio deletion, and
whole-meeting deletion. A new snapshot is published only after the operation is
terminal and the complete affected projection has been rebuilt. Every snapshot,
hit, and cursor binds the exact metadata revision. Retention or audio deletion
keeps transcript/note search authority but refreshes audio state. Whole-meeting
deletion removes the row and its metadata only after its deletion receipt is
terminal.

Beta search is one literal mode. Query bytes must be valid UTF-8, contain 2
through 256 Unicode scalar values after trimming Unicode whitespace, and
contain no control or line-separator characters. `search-normalization/1` is
pinned to Unicode 17.0.0, `unicode-segmentation` 1.13.3 with crate checksum
`c6f5d3c3b1bf09027a88a6bc961fc00497d651009560b5463668dc81b0fa87a8`,
`icu_normalizer` and `icu_normalizer_data` 2.2.0 with checksums
`c56e5ee99d6e3d33bd91c5d85458b6005a22140021cc324cea84dd0e72cff3b4`
and `da3be0ae77ea334f4da67c12f149704f19f81d1adf7c51cf482943e84a2bad38`,
and Rust 1.94.0 commit
`4a4ef493e3a1488c6e321570238084b38948f6db` for `char::to_lowercase`.
Changing any one requires a new normalization schema and fixture.

The transform segments each field into extended grapheme clusters, records
each cluster's half-open original Unicode-scalar range, applies ICU NFC and
Rust Unicode lowercase conversion per cluster, and maps every normalized scalar
back to that complete original range. A match is one contiguous normalized
substring inside one canonical field; its displayed span is the minimum start
through maximum end of the matched origin ranges. This is a grapheme-safe
displayed source span, not a claim that normalization preserved the exact
matched scalar boundary. Query normalization uses the same transform without an
origin map. The canonical fixture covers composed and decomposed `é`, expanding
`İ`, emoji sequences, and repeated text. Search does not stem, fuzz, join turns,
infer synonyms or subjects, or generate an answer.

The searched fields are current accepted claim text, each retained transcript
turn, operator title, and folder name. Fixed `Me` and `Them` labels are indexed
only when the validated transcript declares `attribution: channel`. A withheld
microphone turn is searchable only as `withheld`; it receives no `Me` authority,
binds the base transcript digest, source-turn index, current view digest, and
unresolved gate state, and opens only the correction decision. Attribution
`none` adds no channel labels. Capture time is an inclusive UTC epoch-second
range over the validated attempt receipt, not formatted text search. Named
participants, inferred counterparties, tags, and generated subjects are absent.

Result precedence is closed. A claim-text match, or a transcript match already
cited by a current accepted claim, yields one `claim` hit for each matching claim.
Every matching retained turn also yields its canonical `transcript` or `withheld`
hit, including when a current claim cites that same span. A title, folder, or
channel-only match yields `meeting`. Claim text and cited-span matches for the
same claim ordinal deduplicate; the canonical transcript hit remains separate.
Stale notes and rejected summaries contribute no claims. Claim and
transcript/withheld hits bind the exact current transcript digest; meeting-only
hits do not invent one. Claim hits additionally bind current note JSON and
Markdown digests plus the complete projected row: claim ordinal, digest, type,
located state, canonical claim text, and validated locator set.
Transcript hits bind
the source turn and mapped original character span. Opening any hit re-inspects
all bound meeting, attempt, metadata, transcript, note, and gate identities;
drift returns `snapshot-stale` and no content.

The commitment-organized library is `view: recorded-actions`, not a separate
surface or task database. It filters current accepted claims whose existing
typed-claim value is exactly `action`. “Recorded actions” says what the note
classified; it does not claim a person accepted an obligation or that the app
owns follow-through. There are no checkboxes, assignees, due dates, reminders,
or completion state. Copy/export remains disabled until the separate redaction
and export decision closes.

The private Rust/UI boundary uses the canonical
`tests/fixtures/library-operations-v1.fixture` JSON fixture and remains unregistered
until the working surface and corpus benchmark pass. Every request and response
refuses unknown or duplicate fields. Schema values, enum values, and key order
are frozen by the fixture. Runtime contract objects use canonical two-space
UTF-8 JSON bytes with no terminal newline; the aggregate fixture is a normal
text file and ends with one newline. Its operations and exact fields are:

- `library_snapshot` has no arguments. `library_snapshot_page` arguments are
  exactly `snapshot_id` and required nonnull `cursor`. Both return fields `schema`,
  `snapshot_id`, `metadata_revision`, `state`, `counts`, `folders`, `meetings`,
  and `next_cursor`. State is `empty` or `populated`. Counts contain exactly
  `valid_meetings`, `searchable_meetings`, `quarantined_meetings`,
  `degraded_capture_meetings`, `unknown_capture_meetings`, and
  `withheld_turns`. Folder rows contain exactly `id` and `name`. Each meeting
  row contains `meeting_id`, `content_state`, `created_at_epoch_seconds`,
  nullable `title`, nullable `folder_id`, `audio_state`, nullable
  `capture_health`, `withheld_turn_count`, and `searchable`.
  Counts and folders describe the immutable whole snapshot and therefore remain
  byte-identical on every page.
- `library_search` arguments are `snapshot_id`, `query`, nullable `folder_id`,
  nullable `start_epoch_seconds`, nullable `end_epoch_seconds`, `view`, and
  nullable `cursor`. View is `all` or `recorded-actions`. Its result fields are
  `schema`, `snapshot_id`, `metadata_revision`, `state`, `counts`, `hits`, and
  `next_cursor`; state is `results` or `no-results`. Search hit rows are the
  same four closed tagged variants as `open_library_hit`, but claim and
  transcript variants carry `preview` instead of full locator/span content;
  withheld rows carry no meeting text.
- `open_library_hit` arguments are exactly `snapshot_id` and `hit_id`. The
  result is the closed tagged union `meeting`, `claim`, `transcript`, or
  `withheld`. Every variant contains `schema`, `kind`, `snapshot_id`, `hit_id`,
  `metadata_revision`, `meeting_id`, and `created_at_epoch_seconds`. `meeting`
  adds nullable `title`, nullable `folder_id`, `content_state`, and
  `audio_state`; `claim` adds `content_state`, `audio_state`, the
  transcript, note JSON, note Markdown, and claim digests plus its exact locator
  rows, evidence state, and current claim text; `transcript` adds
  `content_state`, `audio_state`, transcript digest, source-turn index, original
  scalar start/end, and exact retained span; `withheld` adds `content_state`,
  `audio_state`, the base/current-view digests, source-turn index, unresolved
  gate state, and no ordinary transcript landing.
- `create_folder`, `rename_folder`, `delete_folder`,
  `assign_meeting_folder`, and `set_meeting_title` are distinct named commands;
  their argument objects do not repeat the operation name. Each carries
  `expected_revision` plus only the exact semantic fields shown in the fixture.
  `assign_meeting_folder` accepts nullable `folder_id` to unfile; title is
  nullable to restore the generated date label. Every mutation returns exactly
  `schema`, `revision`, `changed`, and nullable `folder_id`. A changed
  `create_folder` result returns the generated ID; every other result returns
  the affected folder ID when one exists and null for title-only mutation. The
  UI refreshes the revision-bound snapshot after every changed mutation.

The error enum is exactly `invalid-request`, `snapshot-stale`,
`library-rebuilding`, `library-capacity-exceeded`, `metadata-unavailable`,
`artifact-unavailable`, `metadata-revision-conflict`, and `internal-error`.
Error fields are exactly `schema`, `code`, `recoverable`, and nullable
`current_revision`; only a metadata revision conflict carries the retained
current revision. Errors contain no private text. Snapshot pages contain at
most 100 meetings; search pages contain at most 100 hits.

Both orders are total. Meeting pages order newest
`created_at_epoch_seconds` first, then meeting ID by UTF-8 byte order. Search
orders by that meeting key, then by the earliest validated locator's source turn
and original scalar start, hit kind in `claim`, `transcript`, `withheld`,
`meeting` order, claim digest, claim ordinal, and hit ID. A meeting hit uses
unsigned-64 maximum for turn and start. A withheld hit uses its source
turn and unsigned-64 maximum for the private sort start; that sentinel is not
returned as an evidence span. Each canonical projected claim ordinal produces
at most one hit; claim-text and cited-span matches for that same ordinal
deduplicate. Equal claim text with different types or evidence remains separate,
as do several claims that cite one source span. Rust keeps cursors inside the immutable
snapshot and generates opaque cursor IDs bound to snapshot, metadata revision,
query digest, filter digest, and last sort key. A cursor is not frontend data
authority and cannot be reused with another query or filter.

Rust generates snapshot, hit, cursor, and folder IDs. Existing meeting IDs come
only from validated canonical records. The webview never supplies a filesystem
path, digest, note ID, transcript ID, artifact locator, executable, model, or
storage root. The exact corpus and latency bounds are pinned by a synthetic
no-private-text benchmark before registration. Crossing the corpus bound yields
`library-capacity-exceeded`; it never silently omits meetings.

The screen vocabulary is `first-run`, `populated`, `searching`, `no-results`,
and `filtered`, where filtered means folder, UTC date range, or Recorded actions.
Within rows, `content_state` is exactly `incomplete`, `captured`,
`transcription-failed`,
`recovered-interrupted`, `transcript-only`, `summary-failed`, `ready`, and
`audio_state` independently carries `never-created`, `retained`, `deleting`, or
`released`. Thus ready content with released audio remains
`content_state: ready, audio_state: released`; neither axis overwrites the
other. Every no-results response comes only from a complete projection and
includes the fixed counts above. The product says “No
exact match in the available record,” never “This was never said.” Diagnostics
may contain only a fixed code, component, opaque meeting ID, artifact kind,
digest, and counts. They never contain query, title, folder, transcript, note,
claim, snippet, or evidence text.

For a transcript-bearing row, nullable `capture_health` is either absent only
for legacy unknown integrity or has exact fields `status`, `mic_dropouts`,
`system_dropouts`, `tap_errors`, `leg_span_mismatch`,
`mic_wall_shortfall`, and `system_wall_shortfall`. Counts are the lengths of the
validated `capture-health/1` event arrays. The three Booleans are the negations
of `legs_cover_same_capture_span` and the mic/system comparisons of
`wall_shortfall_samples` with `allowed_wall_shortfall_samples`. Status is
`clean` only when all counts are zero, all three flags are false, and the
re-derived health verdict passes; otherwise it is `degraded`. A legacy
transcript with unknown integrity uses null and increments
`unknown_capture_meetings`. Non-transcript rows use null but increment neither
capture count. Labels never replace these persisted facts.

The fixture is the contract source, not evidence that an implementation exists.
Before implementation may call this boundary frozen, an executable parser and
suite must consume the fixture, reject field and enum drift in both directions,
and pass deterministic cases for every lifecycle row, first-run, no-results,
transcript-only, summary-failed, ready, stale-note exclusion, audio-released,
malformed metadata, invalid attempt, malformed meeting, changed artifact,
withheld hit, attribution `none`, capture gap, capacity overrun, metadata change,
whole-meeting deletion, and snapshot/cursor drift. The cases prove claim-first
precedence, normalization-to-origin mapping, exact locator landing,
current-note-only indexing, revision conflicts and no-ops, unfile/folder-delete
semantics, no prefix search during rebuild, and unchanged canonical meeting
bytes during every read. A synthetic corpus pins supported meeting/searchable
byte counts plus cold-rebuild and warm-query latency. Passing these checks does
not register a command or approve the interaction; the operator must still
review the running library and note reader cold.

That pending executable suite must also cover meeting 101 pagination, folder-ID
discovery, every mutation's exact-field rejection, revision-conflict payloads,
query/filter cursor reuse, every content/audio cross-product, several claims
citing one span, claim-text/citation deduplication, normalization dependency
drift and origin mapping, capture-health derivation, and stale metadata/title
hits.

Transcript, claim, preview, and span strings in the checked-in fixture are empty
redaction sentinels used only to freeze field presence and order; executable
validators must reject those sentinels wherever runtime content is required.
Metadata and query examples use non-prose tokens that satisfy their runtime
shape. No meeting or synthetic meeting prose is stored in the fixture.

Note-to-note links, saved searches, tags, smart folders, inferred subjects,
named-participant search, semantic/fuzzy search, generated answers, and any
persisted search index remain deferred. Their absence is not silently filled by
model inference.

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

Profile reset uses a separate Rust-owned `profile-lifecycle/1` rolling journal
rather than the meeting operation store. The generic store terminates against
exact `meeting.json` bytes, while reset owns one account-level profile and must
not invent a meeting authority. Three candidate persistence shapes were
compared against reset, restart, reenrolment, and low-disk cases:

| Shape | Consequence | Decision |
|---|---|---|
| One immutable operation directory and tombstone per reset | Simple recovery and complete event history, but directories, receipts, and inodes grow without bound until they can prevent the next privacy action. | Rejected. |
| Collect old terminal directories | Eventually bounded, but pathname unlink recreates the swapped-entry deletion race and destroys the evidence being collected. | Rejected. |
| Fixed live, reset, and enrolment slots plus an alternating rolling journal | Constant storage, no data-path unlink, and closed reset/restart states; it preserves the completion count and latest event rather than an immutable history of every reset. | Chosen. |

After profile-storage initialization, `voiceprint.json`,
`lifecycle/reset.tombstone`, and `lifecycle/enrollment.staged` always exist.
Each is a distinct inode on the same volume. A zero-byte `voiceprint.json` means
that no profile is installed. Reset and guided enrolment reuse the other two
zero-byte slots; they never create per-operation tombstones.

Initialization runs under the writer and storage-sequence locks. Rust first
descriptor-binds `profile`, then create-new and full-syncs its sibling
`voiceprint.json` as a safe zero live slot when absent, or pins and validates an
existing safe live file. It next builds both receipt files and the reset and
enrolment zero slots under `profile/.lifecycle.initializing`, writes and
full-syncs a sequence-zero `baseline` receipt bound to the already pinned live
descriptor, syncs the initializing directory, then no-overwrite renames that
directory to `profile/lifecycle` with
`renameatx_np(RENAME_EXCL | RENAME_NOFOLLOW_ANY)` and syncs `profile`. The baseline binds all
three data-slot identities and records whether the live slot is zero or binds
the exact size and digest of an existing legacy profile. A safe semantically
invalid legacy file may be recorded as present so reset can remove it; the
baseline does not admit it for Start. A crash before publication leaves the
safe live sibling and at most the fixed initializing directory, which may
resume if every present object matches the closed initialization shape. Once
`profile/lifecycle` exists, a valid baseline or later receipt is mandatory.
Missing fixed objects or two invalid/empty receipt slots then quarantine
profile work; they are never reinterpreted as a fresh store.

`lifecycle/receipt.a.json` and `lifecycle/receipt.b.json` are permanent
alternating slots, each bounded to 16,384 bytes before read or parse. A virgin
slot is exactly zero length. Each valid nonempty slot contains canonical JSON
with no terminal newline and the exact envelope fields `schema`,
`payload_sha256`, and `payload`, in that order. `schema` is
`profile-lifecycle-slot/1`; `payload_sha256` is lowercase SHA-256 over the
two-space-pretty UTF-8 encoding of `payload` alone. The payload is a closed
`profile-lifecycle/1` object whose first fields are `schema`,
`receipt_sequence`, `operation`, and `phase`; its remaining phase-specific
fields are ordered as defined below. The allowed operation/phase pairs are
exactly `baseline/ready`, `reset/deleting`, `reset/staged`, `reset/removed`,
`enrollment/writing`, `enrollment/ready`, and `enrollment/active`.

To publish the next phase, Rust retains and verifies both fixed receipt-file
descriptors. It truncates and write-alls only the lower-sequence slot, a virgin
inactive slot, or a nonempty invalid inactive slot whose peer is the sole valid
authority. It then full-syncs and rereads that descriptor, revalidates its
pathname-to-fd identity, and only then selects the unique highest complete
valid sequence. A torn slot is ignored only while the other slot is complete.
Two virgin slots exist only inside the unpublished initializing directory; the
published lifecycle begins with one valid sequence-zero baseline. Equal
sequences, two different valid payloads at one sequence, overflow, or no valid
slot after publication quarantine the profile lifecycle. The sole highest
valid slot is never truncated. Every phase has its own closed decoder, so a
forbidden field is refused even when its JSON value is `null`.

A baseline payload then has `completed_reset_count`, `live`, `reset_slot`, and
`enrollment_slot`; its `receipt_sequence` and `completed_reset_count` are both
exactly zero. Reset `deleting` and `staged` payloads then have
`operation_id`, `requested_at`, `prior_completed_reset_count`, optional
`prior_last_reset` only when that count is nonzero, `profile`, and `reset_zero`.
Reset `removed` then has `completed_reset_count`, `last_reset`, `live_zero`, and
`reset_zero`. Every reset phase also has the exact untouched
`enrollment_zero`. Each non-baseline payload also binds
`predecessor_payload_sha256` immediately after `phase`.

An identity object has the exact fields `device`, `inode`, `generation`,
`birth_seconds`, `birth_nanoseconds`, `owner`, `mode`, `link_count`, and
`flags`. A slot object then has `identity`, `size`, and `sha256`; an exact
profile requires its bound size and digest, while a safe zero requires size
zero and the SHA-256 of an empty file. A reset `removed` payload drops the
profile size, digest, and all profile data. It retains the completed count,
last operation UUID and completion time, and both now-zero slot objects. Those
are filesystem identity metadata, not profile or enrolment provenance.
Recovery of one UUID sets the count to exactly
`prior_completed_reset_count + 1`; it never increments the same reset twice.
Sequences and counts are unsigned 64-bit integers and refuse overflow.
Operation IDs are canonical lowercase UUID strings. Times are integer Unix
epoch seconds. A `last_reset` object has exactly `operation_id` and
`completed_at`; it is absent, never null, when the completed count is zero.

Reset opens and retains both data-slot descriptors with
`O_RDWR | O_NOFOLLOW | O_CLOEXEC`. It writes and full-syncs `deleting` before
calling same-volume `renameatx_np(RENAME_SWAP | RENAME_NOFOLLOW_ANY)`. The
target volume must report `VOL_CAP_INT_RENAME_SWAP`; absence or runtime failure
blocks before content mutation. The swap exchanges the live profile and known
zero tombstone without overwriting or unlinking either inode. Rust then proves
that both pathnames name the retained opposite descriptors, syncs both
directories, and writes `staged`. It truncates only the retained original
profile descriptor to zero, full-syncs that descriptor, revalidates both paths
and objects, and writes `removed`. It never performs a rollback swap and never
calls unlink on a profile data slot.

Recovery uses this closed matrix. `P` is the receipt-bound original profile
inode and `Z` is the receipt-bound zero reset-slot inode:

| Receipt phase | Live `voiceprint.json` | Reset tombstone | Result |
|---|---|---|---|
| `deleting` | `P`, exact bound profile bytes | `Z`, safe zero | Pre-swap: retain both descriptors, swap once, verify, sync, and advance to `staged` |
| `deleting` | `Z`, safe zero | `P`, exact bound profile bytes | Swap completed: verify and advance to `staged` |
| `deleting` | `Z`, safe zero | `P`, safe zero | Swap and truncate survived an older phase receipt: full-sync and write this UUID's `removed` state with exactly the prior count plus one |
| `staged` | `Z`, safe zero | `P`, exact bound profile bytes | Truncate only the retained or exactly reopened `P` descriptor, full-sync, and advance to `removed` |
| `staged` | `Z`, safe zero | `P`, safe zero | Truncate completed: full-sync and advance to `removed` |
| `removed` | `Z`, safe zero | `P`, safe zero | Profile is absent and the latest reset is terminal |
| Any | Any other identity or content arrangement | Any other identity or content arrangement | Quarantine without swap, rollback, truncate, unlink, or receipt advancement |

An exact profile object requires the receipt identity and original digest. A
safe zero object requires its receipt identity, zero size, and the SHA-256 of
an empty file. A reset can start only when the live profile and reset tombstone
are different inodes. The `deleting` post-truncate row is deliberate: it closes
a crash in which the data transition persisted more strongly than the phase
receipt. A crash during swap exposes only the recognized pre- or post-swap
layout. A crash around truncate exposes exact original bytes, a safe zero, or an
unrecognized state that quarantines.

One FD-bound `safe profile tree` predicate governs initialization, reset, and
recovery. Rust descriptor-binds `$APP_DATA`, `$APP_DATA/profile`, the published
`profile/lifecycle` or fixed `profile/.lifecycle.initializing`, both receipt
slots, `reset.tombstone`, `enrollment.staged`, and the live `voiceprint.json`
without following links. Each directory is
current-effective-user-owned, exact `0700`, and has no extended ACL or extended
attributes. Each receipt or data slot is a current-effective-user-owned,
non-symlink regular file with one link, exact `0600`, `st_flags == 0`, no
extended ACL entries, and no extended attributes or resource fork. Profile
bytes must also remain within the profile size bound. ACL checks use the open
descriptor; `flistxattr(..., XATTR_SHOWCOMPRESSION)` prevents a compressed or
resource-fork attribute from hiding from the empty-attribute test. Unsafe or
swapped parent directories, receipt files, and leaves block before mutation.

The process-lifetime writer lock and global storage-sequence lock serialize one
profile-lifecycle coordinator across reset, enrolment, adoption, profile load,
and capture admission. Reset refuses while any meeting lease is active; a new
capture cannot enter while reset holds the sequence. Startup completes or
quarantines profile-lifecycle recovery before profile inspection, enrolment, or
Start. Start holds the same sequence while the strict Python loader revalidates
the nonzero installed bytes; a safe zero live slot is `not-enrolled`, never a
malformed profile. Rust then registers the active meeting lease; the
durable attempt binds the returned profile digest before the sequence is
released.

Guided enrolment publishes through the same rolling lifecycle journal, not an
independent authority. Its `writing` and `ready` payloads then have
`operation_id`, `requested_at`, `predecessor_reset` containing the completed
count and optional last UUID, `live_zero`, and the exact untouched `reset_zero`;
`writing` adds `enrollment_zero` while `ready` adds `staged_profile`. Its `active` payload
then has `operation_id`, `requested_at`, `completed_at`, `predecessor_reset`,
`live_profile`, `reset_zero`, and `enrollment_zero`. Each follows the common prefix and
predecessor hash above.

Enrolment starts only with exact receipt-bound safe zeros in the live and fixed
staged slots. It writes candidate bytes only through the retained staged-slot
descriptor after `writing` is durable. A fresh process seeing `writing` and
partial or uncommitted bytes truncates only that exact staged inode back to
zero, full-syncs it, and leaves the same operation recoverable for an explicit
retry; it never promotes bytes without a `ready` digest and strict profile verdict.
After validation and full sync, `ready` is durable before
`renameatx_np(RENAME_SWAP | RENAME_NOFOLLOW_ANY)` exchanges the staged profile
and live zero. With `L` as the bound live-zero inode and `E` as the bound
enrolment-slot inode, recovery is closed:

| Receipt phase | Live slot | Enrolment slot | Result |
|---|---|---|---|
| `writing` | `L`, safe zero | `E`, safe zero or uncommitted bytes | Truncate only exact `E` to zero when needed, full-sync, and leave this operation retryable |
| `ready` | `L`, safe zero | `E`, exact admitted profile | Swap once, verify, sync both directories, and write `active` |
| `ready` | `E`, exact admitted profile | `L`, safe zero | Recognize the completed swap, verify, and write `active` |
| `active` | `E`, exact admitted profile | `L`, safe zero | Terminal enrolled profile |
| Any | Any other identity or content arrangement | Any other identity or content arrangement | Quarantine without rollback, live-byte truncation, or receipt advancement |

Every reset row also requires its receipt-bound `enrollment_zero` to remain
unchanged, and every enrolment row requires its receipt-bound `reset_zero` to
remain unchanged. Thus every payload is complete current authority for all
three fixed slots even after the alternating journal overwrites older phases.
`active`, not an older `removed` payload, authorizes the nonzero live profile
and carries forward the predecessor reset count/UUID. The staged slot is again
a receipt-bound safe zero.

The current Python `_install_profile_bytes` no-overwrite bridge cannot replace
a lifecycle-owned zero absence marker and is retired when lifecycle storage is
initialized. It remains only a development-only legacy-store bridge and is not
beta profile authority. Future Rust-owned enrolment or adoption must use the
serialized lifecycle transition.

Reset logically removes semantically malformed, stale, experimental, or
fingerprint-mismatched `voiceprint.json` bytes when the installed object still
satisfies the safe-object predicate. Those semantic failures must not trap the
operator in a profile they cannot reset. A symlink, oversized file, wrong owner,
wrong mode, extra hard link, nonzero file flag, extended ACL, extended
attribute or resource fork, changed file, unsafe tree component, or ambiguous
journal is quarantined without following or mutating it. That storage block
disables Start and enrolment until an explicit repair path resolves it. A safe
zero live slot returns `already-absent` without creating a self-attesting reset
receipt.

Reset never opens or changes a meeting directory. Every reset or successful
enrolment clears the one-attempt participant attestation. The fixed journal and
zero slots count toward disk accounting and remain operator-visible. Reset
preflights and full-syncs the next inactive receipt slot before profile
mutation; allocation failure reports that no reset occurred. The rolling
journal is crash-recoverable latest-state evidence, not immutable history or a
tamper-evident log. Same-user receipt replay, concurrent hard-link creation,
whole-volume rollback, extra copies, APFS clones or snapshots, backups, and SSD
remnants are outside its guarantee. This is logical application-storage
deletion, not forensic secure erasure. The confirmation names those limits and
that the completion count, latest event, fixed zero slots, and filesystem
metadata remain.

The automatic retention executor is part of the first human-capture slice.
Rust records the next deletion time from durable attempt creation in
`meeting.json`, scans due work on launch and while running, and first writes a
durable deletion receipt. Before the first
rename, it validates the existence, regular-file type, private mode, byte size,
and digest of every bound WAV. It then stages the complete validated set by
same-volume rename, fsyncs both directories, and advances the receipt from
`deleting` to `staged`; the content lifecycle does not change. Only then does it
remove staged bytes, fsync the deletion directory, advance the receipt to
`removed`, and commit audio `released` to `meeting.json`. A crash before that
last commit leaves a conservative in-progress state; recovery validates every
remaining artifact against the durable phase before advancing it. This also
covers the one-leg subset preserved from an interrupted capture. Manual
deletion, disk accounting, policy change, and whole-meeting deletion reuse the
mechanism in the later trust-action slice.

An active-meeting lease is registered before its storage directory can be
published and remains held through the final transcript or failure record.
Startup recovery and every retention scan share the same process-local storage
sequence gate. A scan snapshots the active IDs under that gate and returns
`deferred-active` for them without opening or mutating their directories. This
prevents a retention pass from quarantining a partial create, deleting WAVs
during transcription, or replacing a newer meeting record with a stale copy.
A due meeting is reconsidered on the next 30-second pass after its lease clears.
The official Tauri single-instance plugin is registered first so an ordinary
second launch returns focus to the existing window before custom app setup. It
is a UX guard, not storage authority: socket errors can fail open. The storage
authority is a separate owner-only `.writer.lock` outside `meetings/`, held by
the process for its lifetime with a nonblocking exclusive `flock`. Contention or
lock errors fail startup before recovery, capture, or retention can mutate a
meeting. Source-level tests preserve plugin order and exercise lock contention;
an installed simultaneous-launch receipt remains a beta gate.

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
offers Start. It resolves exact child ownership first, then interrupted deletion,
then newly due retention. One meeting's malformed storage does not abort the
rest of the scan.

- A meeting directory whose record cannot be read and validated cannot be
  classified as terminal. It is quarantined and blocks Start; filesystem
  absence guesses are not a substitute for a durable terminal fact.
- A terminal, validated capture remains terminal.
- An `incomplete` meeting first requires the exact ownership receipt bound by
  `meeting.json`. A missing receipt or digest mismatch quarantines the meeting
  and blocks Start. Recovery then waits for the parent-liveness shutdown, reads
  each surviving process identity from the OS, compares every recorded field,
  and terminates only exact matches. A PID that exists but whose identity cannot
  be inspected remains ambiguous; it is not treated as an exited process.
- Once no matching child is live, the meeting is marked
  `recovered-interrupted`. If identity is ambiguous, Start remains blocked and
  no unrelated process is signalled.
- Before partial artifacts are bound or `meeting.json` is rewritten, recovery
  preflights the deletion receipt and staged paths without mutation. Impossible
  or malformed deletion state quarantines the original record byte-for-byte.
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

Status: implemented. The deterministic workspace suite passes those cases plus
malformed startup, private file-mode enforcement, missing deletion receipts, and
tampered staged-audio quarantine. The real worker boundary remains Phase 2.

### 2. Real worker boundary

Extract app-safe adapters around strict profile loading, capture finalization,
transcript creation, note generation, and artifact-pair validation. Package the
worker and Swift tap as target-specific sidecars. Add the tap readiness and
parent-liveness contracts, and harden canonical app writes through the shared
durable writer. Keep research CLI options out of the operation registry.

Exit: prerecorded fixtures travel through one protocol and produce the same
digests and verdicts as the direct validated functions.

Status: implemented for the transcript-only internal alpha. The closed worker
protocol now owns capture finalization and model-backed offline transcription;
the packaged arm64 runtime includes pinned CPython, the Swift two-leg capture
helper, and the admitted Whisper model inventory. Rust verifies the runtime
manifest, owns the worker and helper process groups, and validates the resulting
transcript before presenting it. The signed installed build has now completed a
real two-leg capture, local transcript, and fresh-process transcript recovery.
Its automatic audio-deletion and clean-transfer receipts remain open. Note
generation and `product` runtime admission remain intentionally outside this
alpha and still block the Phase 2 exit for beta.

The detached research CLI tap now uses the same parent-liveness primitive. Its
own session still prevents terminal `Ctrl-C` from racing the ordered stop path,
while an inherited pipe closes on parent crash or kill and stops the Core Audio
run loop. App-handshake, liveness-only, and CLI-to-tap FD controls cover both
launch modes without opening capture hardware.

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

Status: implemented only for the internal transcript alpha. Its approved surface
covers consent, two-leg capture, processing, transcript success, explicit
failure, restart recovery, and scheduled audio retention. A permission-denial
attempt validated the closed failure path. The corrected signed build has since
completed hardware capture, transcription, and fresh-process recovery. Its
one-day deletion deadline is recorded locally, but the automatic deletion event
and clean-transfer receipt remain open. Library, automatic-note, and evidence-
adjudication surfaces remain later beta work.

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
| A note JSON, Markdown, transcript, or meeting identity does not match its content-addressed path and request | `note.inspect` refuses every digest; `meeting.json` cannot advance to `ready` |
| A self-consistent `passed: false` research diagnostic is placed in product note storage | Product inspection refuses it; no claim, count, or note pointer gains authority |
| A withheld-turn restore completes before the terminal operation receipt is written | Fresh recovery either applies the validated successor to the still-current source or recognizes the already-applied exact successor and writes the missing commit; every other pointer combination is left untouched |
| Profile is missing, malformed, experimental, or fingerprint-mismatched | Start is disabled before tap launch |
| Adopted profile is oversized, a symlink, changes after selection, or fails strict validation | Quarantine is removed, installed profile is unchanged, and the webview learns no source path |
| Lifecycle initialization stops before publication | Fresh startup resumes only the exact private initializing tree, publishes one sequence-zero baseline, and never mistakes two empty published receipts for a fresh store |
| Reset stops before swap, after swap, or after descriptor truncation | Fresh startup accepts only the bound pre-swap, post-swap, or safe-zero row; it increments the reset count once and never rolls back, unlinks a slot, or truncates a substituted inode |
| A lifecycle parent, receipt, or data slot has a symlink, wrong owner/mode, hard link, flag, ACL, attribute, resource fork, missing identity, or conflicting receipt sequence | Profile loading, enrolment, reset, and Start quarantine before mutation |
| Enrolment stops while writing or after its publish swap | Fresh startup truncates only the exact uncommitted staged inode or recognizes the exact ready/active layout; a nonzero live profile has no authority without `enrollment/active` |
| `passed: false` note or mismatched Markdown sibling is injected | Reader refuses ready state and reports a bounded artifact error |
| State file write, `fsync`, replace, or parent `fsync` fails | Status does not advance from an error; a fresh process accepts only one complete state whose referenced bytes reconcile; temporary material remains private and is cleaned or recoverable |
| Run under `umask 000` | App root and directories are `0700`; private files are `0600`; nothing is written in the repository |
| Retention time becomes due while the app is closed | Next launch stages and removes the bound WAVs under a durable receipt, fsyncs removal, then commits `audio-released`; transcript, note, profile, and other meetings remain |
| Retention time becomes due while that meeting is capturing, finalizing, or transcribing | The scan returns `deferred-active` without opening the meeting; the next pass after the active lease clears performs the due deletion without losing the newer meeting record |
| A second app process opens the same app-data root | The single-instance plugin normally returns focus; independently, the process-lifetime app-data writer lock makes the newcomer fail closed before recovery, capture, or retention mutation |
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

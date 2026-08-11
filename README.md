# Yawn

Yawn is a private macOS meeting notepad. It records a consented meeting on the
Mac, keeps an operator's own notes beside the transcript, and retains a
readable meeting note without requiring an account, upload, calendar, bot, or
automatic sharing.

The interface is intentionally small:

1. Start one recording after an explicit consent and retention check.
2. Type the points that matter while the conversation is happening.
3. Reopen the finished note from Meetings.

Read [the product brief](./docs/product-brief.md) for the current product
contract and the research inputs behind the reset. Old UI, IA, and design
material was deliberately removed rather than treated as a design baseline.

## What is currently true

- macOS 14.4 or later is required.
- A recording requires participant consent, headphones, and one person near
  the microphone.
- Retained recording audio is explicitly set to 1, 7, or 30 days.
- Yawn distinguishes the operator's notes, generated claims, transcript text,
  withheld turns, and incomplete runs.
- Passing tests do not prove a useful real-meeting result or a completed
  human-quality review.

## Repository map

- [apps/desktop](./apps/desktop/) — the Tauri app and bundled frontend.
- [crates/session-core](./crates/session-core/) — capture, storage, transcript,
  and meeting-domain contracts.
- [worker](./worker/) — the local transcription and note-processing worker.
- [capture](./capture/) — signed macOS capture and permission helpers.
- [spike/RESULTS.md](./spike/RESULTS.md) — measured audio and voice-isolation
  evidence.
- [notes/EVAL.md](./notes/EVAL.md) — note-generation measurement evidence.
- [docs/distribution-runbook.md](./docs/distribution-runbook.md) — packaging
  and release procedure.

## Test the desktop app from a fresh clone

Yawn currently supports Apple-silicon Macs running macOS 14.4 or later. The
first setup downloads the local speech runtime and models (about 2 GB); no
meeting data is uploaded.

```sh
git clone git@github.com:nino-chavez/meeting-notes-local.git
cd meeting-notes-local
./worker/build_runtime.sh build-alpha
cd apps/desktop
npm ci
npm run dev
```

The runtime is intentionally ignored by Git. Do not commit it, symlink it, or
place meeting exports anywhere in this checkout.

The current package is an internal alpha. Before recording, grant the requested
macOS permissions and confirm consent, headphones, and that only one person is
near the microphone. A successful build does not prove a useful real-meeting
result.

## Checks

```sh
cd apps/desktop
npm run test:ui
```

For Rust changes, run the relevant
`cargo test -p local-meeting-notes-desktop` lane as well. The preview build is
a bounded development surface; it is not proof that a real meeting was
recorded, transcribed, or judged useful.

## License

MIT — see [LICENSE](./LICENSE).

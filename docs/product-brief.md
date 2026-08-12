# Product brief — Yawn

Status: reset on 2026-08-10.

## Who this is for

One person needs to stay in a conversation and still keep a useful private
record. They should be able to start capture clearly, jot down what matters,
and find the finished note later without learning a new workspace.

The reader knows how to use a Mac. They should not need to understand audio
routing, speech models, library handles, or internal product history.

## What must stay true

- Capture, transcription, and retained meeting data stay on this Mac. The app
  does not imply an account, cloud sync, a meeting bot, calendar access, sharing,
  or task creation.
- Recording starts only after the operator confirms participant consent,
  headphones, and that they are the one person near the microphone.
- Audio retention is chosen explicitly: 1, 7, or 30 days.
- The operator's own notes are distinct from generated meeting-note claims.
  A generated claim keeps its evidence state. A withheld turn never becomes
  invented transcript text.
- An interrupted or failed run is stated plainly. It is never presented as a
  completed meeting.

## What real meetings add

This reset is also grounded in private source material: local recordings,
captions, and note exports from real meetings. The source material itself is
not copied into this repository or product brief.

Those meetings make one interface requirement non-negotiable: a note can be
accurate and still leave out a commitment, a deadline, or the difference
between two nearby ideas. A tidy summary must never look like a complete record.

- During a meeting, the operator needs an unconstrained place to write their
  own reminders before a detail disappears.
- After a meeting, generated points are a **draft from the transcript**, not a
  final account. Each displayed point needs a clear path back to the retained
  source text.
- The full transcript stays available in the same meeting view. It is the
  record for checking a decision, owner, or follow-up that matters.
- The library remains organized around individual meetings. It does not become
  an action-item dashboard merely because a meeting contains commitments.

Historical Loom material will be incorporated by the same rule when its local
copies or links are available: derive product requirements, never copy private
meeting content into the app or repository.

## The product, from first principles

Yawn is a private meeting notepad with a recorder attached. It is not a
workspace, dashboard, task manager, CRM, team wiki, or calendar.

There are three moments that matter:

1. Before a meeting: one clear record action and a short consent check.
2. During a meeting: a calm note canvas, a visible recording state, and one
   obvious way to stop.
3. After a meeting: a readable note with the transcript available when needed,
   then a simple list of past meetings.

The finished note is the destination. The list exists to reopen finished notes;
it is not the home-screen subject. Settings remain a small auxiliary window.

## Interface rules

- Open to the next useful action, not a dashboard of features.
- Keep the recording control visible without surrounding it with setup,
  diagnostics, folders, templates, or planned features.
- Give the operator a plain place to type during capture. Their notes guide what
  they need to remember; they are not a form to complete.
- Keep the status language concrete: recording, preparing, finishing,
  transcript ready, or needs attention.
- Keep Settings limited to audio access and local speech-model storage. Show
  which model is in use. Allow switching only between meetings, and never
  remove the active model.
- Use a short, quiet Mac-native surface: generous reading width, one main
  content column, light chrome, and color only for recording or attention.
- Never use fake counts, placeholder meetings, promised automation, or a
  synthetic example as if it were data from this Mac.

## Not part of this reset

Do not add folders, saved views, action dashboards, templates, calendar sync,
meeting bots, sharing, collaborative workspaces, chat over every meeting, or
automatic task creation just to match the category. They need a separate
product decision and a real underlying capability.

## Research inputs, not copied product direction

Wispr Flow's current desktop Scratchpad is lightweight, keyboard-reachable, and
meant to stay out of the way of the work already on screen. That supports a
capture-first, low-chrome interaction model, not its account or sync model.

Granola's meeting notepad keeps a plain editor available during the meeting and
distinguishes a person's own notes from AI-enhanced material. That supports a
local note canvas and provenance distinction, not Granola's cloud integrations
or collaboration model.

Notion demonstrates bot-free system-audio capture, consent, and a searchable
record after a meeting. It is a useful category comparison, but its shared
workspace and automation are deliberately outside Yawn's scope.

Sources checked for this reset:

- [Wispr Flow Scratchpad update](https://wisprflow.ai/whats-new)
- [Granola's meeting-notepad explanation](https://www.granola.ai/blog/announcement)
- [Granola's note-editor documentation](https://docs.granola.ai/help-center/taking-notes/taking-notes-in-granola)
- [Notion AI Meeting Notes](https://www.notion.com/en-US/product/ai-meeting-notes)

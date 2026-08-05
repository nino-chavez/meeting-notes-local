# Local Meeting Notes — coworker alpha hand-off

Operator-owned draft. This is the note that accompanies the DMG link for the
internal coworker cohort. Plain language on purpose; edit freely.

## What you're getting

A local meeting notetaker for Apple-silicon Macs (macOS 14.4+). Everything —
audio, transcripts, search — stays on your machine. Nothing is uploaded
anywhere, ever. There is no account, no server, and no telemetry.

What works today: manual record (your mic plus the meeting audio your Mac
plays), local transcription after the meeting ends, transcript search, and
reviewed deletion of audio you don't want kept. If the app quits or crashes
mid-meeting, it recovers the recording on next launch.

What does not exist yet, on purpose: automatic meeting notes, voice
isolation (separating who said what), and auto-updates. When there's a new
build, you'll get a new link.

## Install

1. Download the DMG from the link you were given.
2. Verify it (paste in Terminal, compare against the checksum in the same
   message as your link):

   ```
   shasum -a 256 ~/Downloads/Yawn-*.dmg
   ```

3. Open the DMG, drag the app to Applications, launch it from Applications.
4. macOS will ask for Microphone and System Audio Recording permission on
   first use. Both are required to capture a meeting.

If macOS refuses to open the app or shows anything other than a normal
first-launch prompt, stop and report it exactly as shown — that's the most
valuable bug you can file. (The first install on a non-development Mac is
itself a release check we want the receipt from.)

## Using it honestly

- Best first tests: record yourself dictating, or a 1:1 where you've told
  the other person and they're fine with it.
- Recording broader work meetings is your judgment under our own workplace
  norms — the app doesn't make that call for you, and some places/people
  require everyone's consent. When in doubt, ask the room.
- Use headphones for anything with remote participants; it keeps the two
  audio legs clean.

## Reporting back

Tell us what happened, never what was said. Do not send audio files or
transcripts — the whole point of the product is that those never leave your
machine, and we hold ourselves to that in testing too.

Useful reports, roughly in order of value:

1. Install or first-launch friction, verbatim messages, screenshots of
   dialogs (not of transcript content).
2. Permission prompts that didn't appear, appeared twice, or didn't stick.
3. A meeting that recorded silence, one leg only, or garbled audio — say
   which mic/headphones/meeting app you used.
4. Recovery: if the app or Mac died mid-meeting, did the recording survive?
5. Transcript quality as an impression ("names mangled", "crosstalk lost"),
   not as excerpts.
6. Anything the app claimed that turned out not to be true.

## Expectations

This is an internal alpha. It is deliberately narrow, updates are manual,
and your feedback shapes what gets built next — including the delivery site
this link came from, which is itself a draft of the eventual public one.

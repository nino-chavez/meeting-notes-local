# Yawn — coworker alpha hand-off

Operator-owned draft. This is the note that accompanies the DMG link for the
internal coworker cohort. Plain language on purpose; edit freely.

## What you're getting

A local meeting notetaker for Apple-silicon Macs (macOS 14.4+). Everything —
audio, transcripts, search — stays on your machine. Nothing is uploaded
anywhere, ever. There is no account, no server, and no telemetry.

The app installs as **Yawn**. If you have an older link that installed "Local
Meeting Notes", this replaces it and keeps the meetings you already have.

What works today: manual record (your mic plus the meeting audio your Mac
plays), local transcription after the meeting ends, transcript search, copying a
transcript out, reviewed deletion of audio you don't want kept, and — new in
this build — an optional voice check that marks speech on your microphone that
doesn't sound like you. If the app quits or crashes mid-meeting, it recovers the
recording on next launch.

What does not exist yet, on purpose: automatic meeting notes and auto-updates.
When there's a new build, you'll get a new link.

## The voice check — read this before you switch it on

This is the new thing in this build, and it's the part we most want you to be
skeptical about.

**Nobody has run it end to end on a real meeting.** Everything below is what the
code does, checked line by line, on a build that has passed its packaging checks.
It has not been through a meeting on an installed copy. You are the first, and
that is exactly why we want your report — including "the button you described
isn't there."

**It does nothing until you switch it on.** Until you finish voice setup, your
transcripts are exactly what they were before: every audible voice, nothing
marked, nothing hidden. There is no profile, so there is no check.

**What it does once you do.** You record a few short samples of yourself
talking. The app measures what you sound like and, from then on, on your
microphone leg only, marks the turns that don't match. A marked turn is **not
deleted.** It stays in the transcript in its place, its text hidden behind the
label "Withheld", and you can put it back.

**Restoring is on both screens, as of 2026-08-06.** The withheld turns each
carry a "Restore this turn" button on the screen you see right after recording,
and on the meeting opened from Meetings. It used to be in Meetings only, which
meant the fix for the mistake that matters most was one navigation away from
where you saw it. If you are on a build from before that date, use Meetings.

**Where it can be wrong, and why that matters more than a mangled word.** The
threshold that decides "not you" was measured on your own setup recordings and
never on a real meeting, so we do not know its real-world error rate. The
failure we care about isn't a garbled name. It's a colleague sitting near your
laptop whose speech gets marked as not-you, in a record of a meeting nobody can
hold again. The app states the first point on the transcript screen every time
the check runs, and raises a separate alert when the speech it withholds keeps
coming back as one voice — which is what that colleague looks like from the
inside.

**If you see that alert, go read what was withheld and restore anything that
belongs.** That is a judgment about who was in the room, and the app cannot make
it for you.

**Headphones change whether it runs at all.** If your microphone is picking up
enough of the meeting's own audio, the app stops claiming who said what — the
split isn't reliable at that point — and the voice check doesn't run. Use
headphones if you want the check to apply.

**To switch it off**, delete the stored voice profile in voice setup. The check
stops; transcripts you already have are untouched.

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
  audio legs clean, and it's also what lets the voice check run.

## Reporting back

Tell us what happened, never what was said. Do not send audio files or
transcripts — the whole point of the product is that those never leave your
machine, and we hold ourselves to that in testing too.

Useful reports, roughly in order of value:

1. Install or first-launch friction, verbatim messages, screenshots of
   dialogs (not of transcript content).
2. Permission prompts that didn't appear, appeared twice, or didn't stick.
3. **The voice check marking a real person as not-you** — roughly how many turns,
   whether it was one person or scattered, and whether the "keeps returning as
   one voice" alert appeared. This is the one we have no measurement for.
4. The voice check withholding *your own* speech, and roughly how much.
5. A meeting that recorded silence, one leg only, or garbled audio — say
   which mic/headphones/meeting app you used.
6. Recovery: if the app or Mac died mid-meeting, did the recording survive?
7. Transcript quality as an impression ("names mangled", "crosstalk lost"),
   not as excerpts.
8. Anything the app claimed that turned out not to be true.

For 3 and 4 we want counts and impressions, not the text — "about eight turns,
all the same colleague" is exactly the right amount of detail.

## Expectations

This is an internal alpha. It is deliberately narrow, updates are manual,
and your feedback shapes what gets built next — including the delivery site
this link came from, which is itself a draft of the eventual public one.

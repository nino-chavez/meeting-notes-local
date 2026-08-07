//! § D. The operator's own note, typed during the meeting.
//!
//! Brought into v1 by operator decision on 2026-08-06; the scope amendment is in
//! `docs/product-definition.md`. What a person chooses to write down while
//! listening is not recoverable from the recording afterwards, which is the whole
//! argument for the surface.
//!
//! **This is interpretation, not evidence, and it is stored as such.** Every
//! evidence artifact in this product is digest-named and bound into
//! `meeting.json`, so a citation can only ever resolve to bytes that were
//! verified. Nothing cites an operator note. Binding it the same way would
//! rewrite the meeting record on every autosave and strand an orphaned
//! digest-named file behind each one, so it is a fixed path in the meeting
//! directory, replaced atomically. The frozen `meeting/2` contract is untouched,
//! which also means a note can never make a meeting unreadable to a build that
//! predates this module.
//!
//! **The text is operator content and is treated like transcript text.** It is
//! never logged, never placed in a diagnostic, and never carried in an error
//! string. The errors here name the failure, not the note.

use std::path::Path;

use local_meeting_notes_session_core::meeting::read_private_bytes;
use local_meeting_notes_session_core::storage::durable_replace;
use serde::{Deserialize, Serialize};

/// The most a note may hold, in bytes of UTF-8.
///
/// Roughly a quarter of a million characters — far past any meeting's worth of
/// typing, and far under the transcript ceiling. It exists so a runaway writer
/// cannot fill a disk through an autosave, and so the read below is bounded by
/// something other than hope.
const MAX_TEXT_BYTES: usize = 256 * 1024;

/// The read bound, which must exceed `MAX_TEXT_BYTES` by enough for the envelope
/// and JSON string escaping. Escaping can expand a byte to six (`\u00XX`), so the
/// margin is generous rather than tight; a file past this is refused rather than
/// truncated, because half an operator's note is worse than none.
const MAX_FILE_BYTES: u64 = 2 * 1024 * 1024;

const FILE_NAME: &str = "operator-note.json";

#[derive(Debug, Serialize, Deserialize, PartialEq, Eq)]
enum NoteSchema {
    #[serde(rename = "operator-note/1")]
    V1,
}

#[derive(Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct StoredNote {
    schema: NoteSchema,
    text: String,
}

/// What the surface is told. Deliberately not the note plus a status string: the
/// shell decides how to present an empty note, and conflating "nothing written"
/// with "nothing readable" is the mistake first run's permission surface had to
/// be corrected for.
#[derive(Debug, Serialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase")]
pub struct OperatorNote {
    pub text: String,
    /// True when a note exists on disk but could not be read or parsed.
    ///
    /// Separate from an empty note, because the consequences are opposite: an
    /// empty note may be typed into, and an unreadable one must not be — saving
    /// over it would destroy whatever it holds. The shell refuses editing on
    /// this, which is the only reason the flag exists.
    pub unreadable: bool,
}

pub fn read(meeting_dir: &Path) -> OperatorNote {
    let path = meeting_dir.join(FILE_NAME);
    if !path.exists() {
        return OperatorNote {
            text: String::new(),
            unreadable: false,
        };
    }
    // A symlink here is not an operator note. `read_private_bytes` enforces the
    // rest of the safe-file predicate; this module adds no exception to it.
    match read_private_bytes(&path, MAX_FILE_BYTES)
        .ok()
        .and_then(|bytes| serde_json::from_slice::<StoredNote>(&bytes).ok())
    {
        Some(stored) => OperatorNote {
            text: stored.text,
            unreadable: false,
        },
        None => OperatorNote {
            text: String::new(),
            unreadable: true,
        },
    }
}

pub fn write(meeting_dir: &Path, text: &str) -> Result<(), String> {
    if text.len() > MAX_TEXT_BYTES {
        return Err("That note is too long to save.".into());
    }
    // Refuse to overwrite something this build could not read. The operator did
    // not see its contents, so they cannot have meant to replace them.
    if read(meeting_dir).unreadable {
        return Err("This meeting's note could not be read, so it was not replaced.".into());
    }
    let bytes = serde_json::to_vec(&StoredNote {
        schema: NoteSchema::V1,
        text: text.to_owned(),
    })
    .map_err(|_| "That note could not be saved.".to_string())?;
    // Atomic replace: a crash mid-write leaves the previous note, never a
    // half-written one. The window this does lose is the typing since the last
    // save, which is what the shell's autosave interval bounds.
    durable_replace(&meeting_dir.join(FILE_NAME), &bytes)
        .map_err(|_| "That note could not be saved.".to_string())
}

#[cfg(test)]
mod tests {
    use super::*;
    use local_meeting_notes_session_core::storage::create_private_dir;
    use tempfile::TempDir;

    fn meeting() -> TempDir {
        let temporary = TempDir::new().unwrap();
        create_private_dir(&temporary.path().join("meeting")).unwrap();
        temporary
    }

    #[test]
    fn a_meeting_with_no_note_reads_empty_and_not_unreadable() {
        let temporary = meeting();
        let directory = temporary.path().join("meeting");
        assert_eq!(
            read(&directory),
            OperatorNote {
                text: String::new(),
                unreadable: false,
            }
        );
    }

    #[test]
    fn a_note_round_trips_and_replaces_in_place() {
        let temporary = meeting();
        let directory = temporary.path().join("meeting");
        write(&directory, "first pass").unwrap();
        assert_eq!(read(&directory).text, "first pass");
        // Replacement, not accumulation: one file, and the previous contents are
        // gone rather than left beside it under another name.
        write(&directory, "second pass, longer").unwrap();
        assert_eq!(read(&directory).text, "second pass, longer");
        let files: Vec<_> = std::fs::read_dir(&directory)
            .unwrap()
            .map(|entry| entry.unwrap().file_name())
            .collect();
        assert_eq!(files.len(), 1, "{files:?}");
    }

    #[test]
    fn an_unreadable_note_is_not_silently_replaced() {
        let temporary = meeting();
        let directory = temporary.path().join("meeting");
        std::fs::write(directory.join(FILE_NAME), b"{ not a note").unwrap();

        let found = read(&directory);
        assert!(found.unreadable);
        // Empty text, so nothing a corrupt file happens to contain reaches a
        // surface — and distinctly flagged, so the shell does not offer to type
        // over it.
        assert!(found.text.is_empty());

        assert!(write(&directory, "replacement").is_err());
        assert_eq!(
            std::fs::read(directory.join(FILE_NAME)).unwrap(),
            b"{ not a note",
            "the unreadable bytes must survive a refused write"
        );
    }

    #[test]
    fn a_note_past_the_ceiling_is_refused_rather_than_truncated() {
        let temporary = meeting();
        let directory = temporary.path().join("meeting");
        write(&directory, "kept").unwrap();
        assert!(write(&directory, &"x".repeat(MAX_TEXT_BYTES + 1)).is_err());
        // Half an operator's note is worse than none, so the refusal leaves the
        // last good one intact.
        assert_eq!(read(&directory).text, "kept");
        assert!(write(&directory, &"x".repeat(MAX_TEXT_BYTES)).is_ok());
    }

    #[test]
    fn a_note_carrying_an_unknown_field_is_refused_rather_than_partly_read() {
        let temporary = meeting();
        let directory = temporary.path().join("meeting");
        std::fs::write(
            directory.join(FILE_NAME),
            br#"{"schema":"operator-note/1","text":"words","extra":1}"#,
        )
        .unwrap();
        // `deny_unknown_fields` again: a note written by a later build carrying a
        // field this one does not understand is unreadable, not partly readable.
        // Failing closed keeps this build from dropping whatever that field held.
        assert!(read(&directory).unreadable);
    }
}

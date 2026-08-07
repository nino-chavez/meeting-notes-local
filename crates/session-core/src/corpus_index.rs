//! A rebuildable SQLite index over the canonical meeting corpus.
//!
//! # What this is not
//!
//! It is not an authority. Every row here is derived from files that
//! [`crate::library_read`] already validated against their content addresses,
//! and it is reachable only through [`LibraryRow::derived`], which hands out
//! exactly the fields a cache may hold. Deleting this database loses nothing:
//! [`CorpusIndex::replace_from_projection`] rebuilds it from the files, and
//! `rebuild_from_files_equals_the_live_index` pins that equality. A column with
//! no canonical file behind it fails that test, which is the point of it.
//!
//! `vertical-slice.md` permitted this on exactly those terms — "a rebuildable
//! cache after measured library size makes the scan a problem", and "no derived
//! index may become the sole copy of a meeting, transcript, note, locator, or
//! library label". Both clauses survive. The measurement that fired the first
//! one is `src/bin/corpus-scan-bench.rs`.
//!
//! # Why it exists
//!
//! The scan answers `rows()` and one exact query. It cannot answer the
//! questions the corpus features need — meetings in a folder, meetings in a
//! date range, how many matches exist when there are more than a screenful —
//! because it holds no queryable structure and refuses any query matching more
//! than `MAX_SEARCH_RESULTS` spans. A single 200-turn meeting already crosses
//! that for a common word.
//!
//! # Private material
//!
//! This database holds transcript text. It lives inside the 0700 storage root
//! at `library/corpus.sqlite3`, mode 0600, and never enters Git. `secure_delete`
//! is on so a removed meeting's pages are overwritten rather than left legible
//! in free space, which matches how audio is treated everywhere else here.

use std::path::{Path, PathBuf};

use rusqlite::{Connection, OpenFlags, OptionalExtension, params};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use thiserror::Error;

use crate::library_read::{DerivedRow, LibraryProjection};
use crate::meeting::MeetingLifecycle;
use crate::storage::{StorageRoot, create_private_dir};

/// Bumped only when a migration changes what a row means. The identity row
/// records the version that wrote the file, so an older binary meeting a newer
/// file refuses instead of misreading it.
pub const CORPUS_INDEX_SCHEMA: &str = "corpus-index/1";
const APPLIED_MIGRATION: i64 = 1;
const DATABASE_NAME: &str = "corpus.sqlite3";

#[derive(Debug, Error)]
pub enum CorpusIndexError {
    #[error("corpus index storage is unavailable")]
    StorageUnavailable,
    #[error("corpus index file is not private")]
    NotPrivate,
    #[error("corpus index schema is newer than this build")]
    SchemaAhead,
    #[error("corpus index rejected a row it cannot have derived")]
    UnderivableRow,
    #[error("corpus index database error")]
    Database,
}

impl From<rusqlite::Error> for CorpusIndexError {
    fn from(_: rusqlite::Error) -> Self {
        // Deliberately content-free. A SQLite error string can carry a column
        // value, and the values here are transcript text.
        Self::Database
    }
}

/// What a sync changed. Counts only; never a meeting ID, never text.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct SyncOutcome {
    pub meetings: usize,
    pub turns: usize,
}

/// A filter over the corpus. Every field is optional and they conjoin.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct ListRequest {
    pub folder: Option<String>,
    pub created_at_or_after: Option<u64>,
    pub created_at_or_before: Option<u64>,
    pub lifecycles: Vec<MeetingLifecycle>,
    /// Zero means "no cap"; a caller that wants a page states its size.
    pub limit: usize,
    pub offset: usize,
}

/// A page of results that states its own truncation.
///
/// `total` is the count matching the filter, `rows` is what this page carries.
/// The scan refuses rather than return a prefix; a store can page, but only if
/// the caller can tell a page from the whole answer. Two fields, not one.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ListPage {
    pub total: usize,
    pub rows: Vec<IndexedMeeting>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct IndexedMeeting {
    pub meeting_id: String,
    pub created_at_epoch_seconds: u64,
    pub lifecycle: MeetingLifecycle,
    pub meeting_record_sha256: String,
    pub attempt_sha256: String,
    pub transcript_sha256: Option<String>,
    pub transcript_relative_path: Option<String>,
    pub note_json_sha256: Option<String>,
    pub note_markdown_sha256: Option<String>,
    pub title: Option<String>,
    pub folder: Option<String>,
    pub turn_count: usize,
}

pub struct CorpusIndex {
    connection: Connection,
    path: PathBuf,
}

impl CorpusIndex {
    /// Opens, creating the file if absent, after checking by hand what SQLite
    /// will not check for us.
    ///
    /// `rusqlite` opens a path; none of `storage.rs`'s descriptor-bound
    /// guards run on that path. So the parent directory's mode and the file's
    /// mode, type and link state are verified here, before the path is handed
    /// over, and the mode is re-asserted after creation.
    pub fn open(storage: &StorageRoot) -> Result<Self, CorpusIndexError> {
        let library = storage
            .resolve(Path::new("library"))
            .map_err(|_| CorpusIndexError::StorageUnavailable)?;
        create_private_dir(&library).map_err(|_| CorpusIndexError::StorageUnavailable)?;
        let path = library.join(DATABASE_NAME);
        Self::open_at(&path)
    }

    fn open_at(path: &Path) -> Result<Self, CorpusIndexError> {
        require_private_parent(path)?;
        if let Ok(metadata) = std::fs::symlink_metadata(path) {
            require_private_file(&metadata)?;
        }
        let connection = Connection::open_with_flags(
            path,
            OpenFlags::SQLITE_OPEN_READ_WRITE
                | OpenFlags::SQLITE_OPEN_CREATE
                | OpenFlags::SQLITE_OPEN_NO_MUTEX,
        )?;
        // A fresh database is created with the process umask, which is not
        // ours to assume. Narrow it before anything is written into it.
        set_private_mode(path)?;

        // DELETE, not WAL: WAL's `-wal` and `-shm` sidecars would hold
        // transcript bytes under permissions SQLite chooses, and nothing here
        // needs a second concurrent reader yet. `secure_delete` overwrites
        // freed pages so a deleted meeting does not stay legible.
        connection.pragma_update(None, "journal_mode", "DELETE")?;
        connection.pragma_update(None, "secure_delete", "ON")?;
        connection.pragma_update(None, "foreign_keys", "ON")?;

        let index = Self {
            connection,
            path: path.to_path_buf(),
        };
        index.migrate()?;
        Ok(index)
    }

    fn migrate(&self) -> Result<(), CorpusIndexError> {
        let applied: Option<i64> = self
            .connection
            .query_row(
                "SELECT applied_migration FROM index_identity WHERE id = 0",
                [],
                |row| row.get(0),
            )
            .optional()
            .unwrap_or(None);
        match applied {
            Some(version) if version == APPLIED_MIGRATION => return Ok(()),
            // Forward-only. An older binary must not read a file a newer one
            // wrote, because it would read columns whose meaning changed.
            Some(version) if version > APPLIED_MIGRATION => {
                return Err(CorpusIndexError::SchemaAhead);
            }
            // No migration from a previous version exists yet, so the honest
            // upgrade for `corpus-index/0` is to drop and re-derive. The files
            // are the authority; nothing is lost.
            Some(_) => {
                self.connection.execute_batch(
                    "DROP TABLE IF EXISTS turn;
                     DROP TABLE IF EXISTS meeting;
                     DROP TABLE IF EXISTS index_identity;",
                )?;
            }
            None => {}
        }
        self.connection.execute_batch(MIGRATION_1)?;
        self.connection.execute(
            "INSERT OR REPLACE INTO index_identity (id, schema, sqlite_version, applied_migration)
             VALUES (0, ?1, ?2, ?3)",
            params![CORPUS_INDEX_SCHEMA, rusqlite::version(), APPLIED_MIGRATION],
        )?;
        Ok(())
    }

    pub fn path(&self) -> &Path {
        &self.path
    }

    /// The SQLite build that wrote this file, recorded beside the schema so the
    /// index carries its own provenance rather than inheriting the caller's.
    pub fn identity(&self) -> Result<(String, String), CorpusIndexError> {
        let row = self.connection.query_row(
            "SELECT schema, sqlite_version FROM index_identity WHERE id = 0",
            [],
            |row| Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?)),
        )?;
        Ok(row)
    }

    /// Replaces the whole index from one validated projection, in a single
    /// transaction. A failure leaves the previous contents intact.
    ///
    /// Full replace, not incremental: skipping unchanged meetings requires a
    /// per-meeting entry point into the validator, which is a change to an
    /// audited module and belongs in its own step. The scan still runs; what
    /// this buys is everything the scan cannot answer afterwards.
    pub fn replace_from_projection(
        &mut self,
        projection: &LibraryProjection,
    ) -> Result<SyncOutcome, CorpusIndexError> {
        let transaction = self.connection.transaction()?;
        transaction.execute("DELETE FROM turn", [])?;
        transaction.execute("DELETE FROM meeting", [])?;
        let mut meetings = 0;
        let mut turns = 0;
        {
            let mut insert_meeting = transaction.prepare(
                "INSERT INTO meeting (
                    meeting_id, created_at_epoch_seconds, lifecycle,
                    meeting_record_sha256, attempt_sha256,
                    transcript_sha256, transcript_relative_path,
                    note_json_sha256, note_markdown_sha256, title, folder
                 ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11)",
            )?;
            let mut insert_turn = transaction.prepare(
                "INSERT INTO turn (meeting_id, turn_index, visible_index, gated, text)
                 VALUES (?1, ?2, ?3, ?4, ?5)",
            )?;
            for row in projection.rows() {
                let derived: DerivedRow<'_> = row.derived();
                insert_meeting.execute(params![
                    derived.meeting_id,
                    derived.created_at_epoch_seconds,
                    lifecycle_name(derived.lifecycle)?,
                    derived.meeting_record_sha256,
                    derived.attempt_sha256,
                    derived.transcript_sha256,
                    derived.transcript_relative_path,
                    derived.note_json_sha256,
                    derived.note_markdown_sha256,
                    derived.title,
                    derived.folder,
                ])?;
                meetings += 1;
                for turn in &derived.turns {
                    insert_turn.execute(params![
                        derived.meeting_id,
                        turn.index,
                        turn.visible_index,
                        turn.gated,
                        turn.text,
                    ])?;
                    turns += 1;
                }
            }
        }
        transaction.commit()?;
        Ok(SyncOutcome { meetings, turns })
    }

    pub fn meeting_count(&self) -> Result<usize, CorpusIndexError> {
        let count: i64 = self
            .connection
            .query_row("SELECT COUNT(*) FROM meeting", [], |row| row.get(0))?;
        Ok(count as usize)
    }

    /// Filtered, ordered, paged read. Ordering matches the scan's: newest
    /// first, then by meeting ID, so a caller swapping one for the other sees
    /// the same sequence.
    pub fn list(&self, request: &ListRequest) -> Result<ListPage, CorpusIndexError> {
        let mut clauses: Vec<String> = Vec::new();
        let mut arguments: Vec<Box<dyn rusqlite::ToSql>> = Vec::new();
        if let Some(folder) = &request.folder {
            clauses.push(format!("folder = ?{}", arguments.len() + 1));
            arguments.push(Box::new(folder.clone()));
        }
        if let Some(after) = request.created_at_or_after {
            clauses.push(format!(
                "created_at_epoch_seconds >= ?{}",
                arguments.len() + 1
            ));
            arguments.push(Box::new(after as i64));
        }
        if let Some(before) = request.created_at_or_before {
            clauses.push(format!(
                "created_at_epoch_seconds <= ?{}",
                arguments.len() + 1
            ));
            arguments.push(Box::new(before as i64));
        }
        if !request.lifecycles.is_empty() {
            let mut placeholders = Vec::new();
            for lifecycle in &request.lifecycles {
                placeholders.push(format!("?{}", arguments.len() + 1));
                arguments.push(Box::new(lifecycle_name(*lifecycle)?));
            }
            clauses.push(format!("lifecycle IN ({})", placeholders.join(", ")));
        }
        let where_clause = if clauses.is_empty() {
            String::new()
        } else {
            format!(" WHERE {}", clauses.join(" AND "))
        };
        let bound: Vec<&dyn rusqlite::ToSql> =
            arguments.iter().map(|value| value.as_ref()).collect();

        let total: i64 = self.connection.query_row(
            &format!("SELECT COUNT(*) FROM meeting{where_clause}"),
            bound.as_slice(),
            |row| row.get(0),
        )?;

        let paging = if request.limit == 0 {
            String::new()
        } else {
            format!(" LIMIT {} OFFSET {}", request.limit, request.offset)
        };
        let mut statement = self.connection.prepare(&format!(
            "SELECT m.meeting_id, m.created_at_epoch_seconds, m.lifecycle,
                    m.meeting_record_sha256, m.attempt_sha256,
                    m.transcript_sha256, m.transcript_relative_path,
                    m.note_json_sha256, m.note_markdown_sha256, m.title, m.folder,
                    (SELECT COUNT(*) FROM turn t WHERE t.meeting_id = m.meeting_id)
             FROM meeting m{where_clause}
             ORDER BY m.created_at_epoch_seconds DESC, m.meeting_id ASC{paging}"
        ))?;
        let rows = statement
            .query_map(bound.as_slice(), |row| {
                Ok(IndexedMeeting {
                    meeting_id: row.get(0)?,
                    created_at_epoch_seconds: row.get::<_, i64>(1)? as u64,
                    lifecycle: parse_lifecycle(&row.get::<_, String>(2)?)
                        .unwrap_or(MeetingLifecycle::Incomplete),
                    meeting_record_sha256: row.get(3)?,
                    attempt_sha256: row.get(4)?,
                    transcript_sha256: row.get(5)?,
                    transcript_relative_path: row.get(6)?,
                    note_json_sha256: row.get(7)?,
                    note_markdown_sha256: row.get(8)?,
                    title: row.get(9)?,
                    folder: row.get(10)?,
                    turn_count: row.get::<_, i64>(11)? as usize,
                })
            })?
            .collect::<Result<Vec<_>, _>>()?;
        Ok(ListPage {
            total: total as usize,
            rows,
        })
    }

    /// A content digest over every stored row.
    ///
    /// Its only job is to make "this index is rebuildable" a comparison rather
    /// than an assertion: derive it twice, from a live index and from a fresh
    /// one built out of the files, and the digests match or a column is holding
    /// something no file produced.
    pub fn fingerprint(&self) -> Result<String, CorpusIndexError> {
        let mut hasher = Sha256::new();
        hasher.update(CORPUS_INDEX_SCHEMA.as_bytes());
        let mut meetings = self.connection.prepare(
            "SELECT meeting_id, created_at_epoch_seconds, lifecycle, meeting_record_sha256,
                    attempt_sha256, transcript_sha256, transcript_relative_path,
                    note_json_sha256, note_markdown_sha256, title, folder
             FROM meeting ORDER BY meeting_id ASC",
        )?;
        let mut rows = meetings.query([])?;
        while let Some(row) = rows.next()? {
            for column in 0..11 {
                hasher.update(b"\x1f");
                match row.get_ref(column)? {
                    rusqlite::types::ValueRef::Null => hasher.update(b"\x00"),
                    rusqlite::types::ValueRef::Integer(value) => hasher.update(value.to_be_bytes()),
                    rusqlite::types::ValueRef::Text(value) => hasher.update(value),
                    _ => return Err(CorpusIndexError::UnderivableRow),
                }
            }
            hasher.update(b"\x1e");
        }
        let mut turns = self.connection.prepare(
            "SELECT meeting_id, turn_index, visible_index, gated, text
             FROM turn ORDER BY meeting_id ASC, turn_index ASC",
        )?;
        let mut rows = turns.query([])?;
        while let Some(row) = rows.next()? {
            for column in 0..5 {
                hasher.update(b"\x1f");
                match row.get_ref(column)? {
                    rusqlite::types::ValueRef::Null => hasher.update(b"\x00"),
                    rusqlite::types::ValueRef::Integer(value) => hasher.update(value.to_be_bytes()),
                    rusqlite::types::ValueRef::Text(value) => hasher.update(value),
                    _ => return Err(CorpusIndexError::UnderivableRow),
                }
            }
            hasher.update(b"\x1e");
        }
        Ok(format!("{:x}", hasher.finalize()))
    }
}

const MIGRATION_1: &str = "
CREATE TABLE IF NOT EXISTS index_identity (
    id INTEGER PRIMARY KEY CHECK (id = 0),
    schema TEXT NOT NULL,
    sqlite_version TEXT NOT NULL,
    applied_migration INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS meeting (
    meeting_id TEXT PRIMARY KEY,
    created_at_epoch_seconds INTEGER NOT NULL,
    lifecycle TEXT NOT NULL,
    meeting_record_sha256 TEXT NOT NULL,
    attempt_sha256 TEXT NOT NULL,
    transcript_sha256 TEXT,
    transcript_relative_path TEXT,
    note_json_sha256 TEXT,
    note_markdown_sha256 TEXT,
    title TEXT,
    folder TEXT
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS meeting_created_at
    ON meeting (created_at_epoch_seconds DESC, meeting_id ASC);
CREATE INDEX IF NOT EXISTS meeting_folder ON meeting (folder);

CREATE TABLE IF NOT EXISTS turn (
    meeting_id TEXT NOT NULL REFERENCES meeting (meeting_id) ON DELETE CASCADE,
    turn_index INTEGER NOT NULL,
    visible_index INTEGER,
    gated INTEGER NOT NULL,
    text TEXT NOT NULL,
    PRIMARY KEY (meeting_id, turn_index)
) WITHOUT ROWID;
";

fn lifecycle_name(lifecycle: MeetingLifecycle) -> Result<String, CorpusIndexError> {
    // Through serde, so the stored name is the same string the canonical
    // record uses and cannot drift from it.
    match serde_json::to_value(lifecycle) {
        Ok(serde_json::Value::String(name)) => Ok(name),
        _ => Err(CorpusIndexError::UnderivableRow),
    }
}

fn parse_lifecycle(name: &str) -> Option<MeetingLifecycle> {
    serde_json::from_value(serde_json::Value::String(name.to_owned())).ok()
}

fn require_private_parent(path: &Path) -> Result<(), CorpusIndexError> {
    use std::os::unix::fs::PermissionsExt;
    let parent = path.parent().ok_or(CorpusIndexError::StorageUnavailable)?;
    let metadata =
        std::fs::symlink_metadata(parent).map_err(|_| CorpusIndexError::StorageUnavailable)?;
    if metadata.file_type().is_symlink()
        || !metadata.file_type().is_dir()
        || metadata.permissions().mode() & 0o777 != 0o700
    {
        return Err(CorpusIndexError::NotPrivate);
    }
    Ok(())
}

fn require_private_file(metadata: &std::fs::Metadata) -> Result<(), CorpusIndexError> {
    use std::os::unix::fs::PermissionsExt;
    if metadata.file_type().is_symlink()
        || !metadata.file_type().is_file()
        || metadata.permissions().mode() & 0o777 != 0o600
    {
        return Err(CorpusIndexError::NotPrivate);
    }
    Ok(())
}

fn set_private_mode(path: &Path) -> Result<(), CorpusIndexError> {
    use std::os::unix::fs::PermissionsExt;
    std::fs::set_permissions(path, std::fs::Permissions::from_mode(0o600))
        .map_err(|_| CorpusIndexError::NotPrivate)
}

#[cfg(test)]
mod tests {
    use std::collections::HashSet;

    use tempfile::TempDir;

    use super::*;
    use crate::library_read::ReadLimits;
    use crate::meeting::{
        ArtifactRef, AudioRetention, AudioRetentionRule, AudioState, MeetingArtifacts,
        MeetingRecord, MeetingSchema, artifact_ref, retention_policy_sha256, write_meeting,
    };
    use crate::storage::durable_create_new;

    struct Fixture {
        _temp: TempDir,
        storage: StorageRoot,
    }

    impl Fixture {
        fn new() -> Self {
            let temp = TempDir::new().unwrap();
            let repository = temp.path().join("repository");
            create_private_dir(&repository).unwrap();
            let storage = StorageRoot::create(&temp.path().join("data"), &repository).unwrap();
            Self {
                _temp: temp,
                storage,
            }
        }

        fn meeting(&self, id: &str, created: u64, turns: &[&str]) {
            let directory = self.storage.path().join("meetings").join(id);
            for child in ["", "capture", "transcript", "deletion"] {
                create_private_dir(&directory.join(child)).unwrap();
            }
            let rule = AudioRetentionRule::DeleteAfter { seconds: 60 };
            let policy = retention_policy_sha256(&rule);
            let attempt = serde_json::json!({
                "schema": "capture-attempt/1", "meeting_id": id,
                "attempt_id": "11111111-1111-4111-8111-111111111111",
                "created_at_epoch_seconds": created,
                "application_build_sha256": "a".repeat(64),
                "participant_notice_version": "internal-transcript-alpha/1",
                "operator_attestation": {
                    "participantsConsented": true, "headphones": true, "operatorAlone": true,
                },
                "retention_policy_sha256": policy,
            });
            durable_create_new(
                &directory.join("attempt.json"),
                &serde_json::to_vec_pretty(&attempt).unwrap(),
            )
            .unwrap();
            for path in [
                "ownership.json",
                "capture/session.json",
                "deletion/audio-deletion.json",
            ] {
                durable_create_new(&directory.join(path), b"{}\n").unwrap();
            }
            let turn_values: Vec<_> = turns
                .iter()
                .enumerate()
                .map(|(index, text)| {
                    serde_json::json!({
                        "start": index as f64, "end": index as f64 + 0.5,
                        "speaker": "Me", "text": text, "gated": false,
                    })
                })
                .collect();
            let transcript = serde_json::to_vec_pretty(&serde_json::json!({
                "schema": "capture-transcript/1", "source": "synthetic",
                "attribution": "channel", "bleed": null, "voiceprint": null,
                "capture_health": {}, "turns": turn_values,
            }))
            .unwrap();
            let digest = format!("{:x}", Sha256::digest(&transcript));
            let relative = format!("transcript/{digest}.json");
            durable_create_new(&directory.join(&relative), &transcript).unwrap();
            let reference = |path: &str| artifact_ref(&directory, path).unwrap();
            let record = MeetingRecord {
                schema: MeetingSchema::V2,
                meeting_id: id.into(),
                lifecycle: MeetingLifecycle::TranscriptReady,
                retention: AudioRetention {
                    rule,
                    policy_sha256: policy,
                    next_deletion_at_epoch_seconds: Some(created + 60),
                    state: AudioState::Released,
                    deletion_receipt: Some(reference("deletion/audio-deletion.json")),
                },
                artifacts: MeetingArtifacts {
                    attempt: reference("attempt.json"),
                    ownership: Some(reference("ownership.json")),
                    capture_session: Some(reference("capture/session.json")),
                    microphone_audio: Some(ArtifactRef {
                        relative_path: "capture/mic.wav".into(),
                        sha256: "b".repeat(64),
                    }),
                    system_audio: Some(ArtifactRef {
                        relative_path: "capture/system.wav".into(),
                        sha256: "c".repeat(64),
                    }),
                    current_transcript: Some(reference(&relative)),
                    current_note: None,
                },
                pending_storage_operation: None,
            };
            write_meeting(&directory, &record).unwrap();
        }

        fn projection(&self) -> LibraryProjection {
            LibraryProjection::rebuild_excluding(
                &self.storage,
                ReadLimits::default(),
                &HashSet::new(),
            )
            .unwrap()
        }
    }

    fn synced(fixture: &Fixture) -> CorpusIndex {
        let mut index = CorpusIndex::open(&fixture.storage).unwrap();
        index
            .replace_from_projection(&fixture.projection())
            .unwrap();
        index
    }

    #[test]
    fn a_synced_index_holds_one_row_per_validated_meeting() {
        let fixture = Fixture::new();
        fixture.meeting("meeting-a", 100, &["alpha beta", "gamma"]);
        fixture.meeting("meeting-b", 200, &["delta"]);
        let index = synced(&fixture);
        assert_eq!(index.meeting_count().unwrap(), 2);
        let page = index.list(&ListRequest::default()).unwrap();
        assert_eq!(page.total, 2);
        // Newest first, matching the scan's order.
        assert_eq!(page.rows[0].meeting_id, "meeting-b");
        assert_eq!(page.rows[1].meeting_id, "meeting-a");
        assert_eq!(page.rows[1].turn_count, 2);
    }

    /// The load-bearing test. Drop the database, rebuild from the files alone,
    /// and require the same content digest. A column written from anything but
    /// a canonical file fails here, which is what keeps this a cache.
    #[test]
    fn rebuild_from_files_equals_the_live_index() {
        let fixture = Fixture::new();
        fixture.meeting("meeting-a", 100, &["alpha beta", "gamma"]);
        fixture.meeting("meeting-b", 200, &["delta"]);
        let live = synced(&fixture).fingerprint().unwrap();

        let path = fixture.storage.path().join("library").join(DATABASE_NAME);
        std::fs::remove_file(&path).unwrap();
        assert!(!path.exists());

        let rebuilt = synced(&fixture).fingerprint().unwrap();
        assert_eq!(live, rebuilt);
    }

    /// The corpus store exists to answer what the scan refuses. The scan caps
    /// at `MAX_SEARCH_RESULTS` spans and returns `CapacityExceeded` beyond it;
    /// a filtered count must instead answer with a number.
    #[test]
    fn a_filter_answers_where_the_scan_refuses() {
        let fixture = Fixture::new();
        // Forty meetings of three turns each is 120 spans carrying the word,
        // past the hundred-hit cap and well inside a real corpus.
        for ordinal in 0..40 {
            fixture.meeting(
                &format!("meeting-{ordinal:03}"),
                100 + ordinal,
                &["common one", "common two", "common three"],
            );
        }
        let projection = fixture.projection();
        assert!(matches!(
            projection.search("common"),
            Err(crate::library_read::LibraryReadError::CapacityExceeded)
        ));

        let index = synced(&fixture);
        let page = index
            .list(&ListRequest {
                created_at_or_after: Some(120),
                limit: 5,
                ..Default::default()
            })
            .unwrap();
        // Total and returned are separate numbers, so a page is never mistaken
        // for the whole answer.
        assert_eq!(page.total, 20);
        assert_eq!(page.rows.len(), 5);
        assert_eq!(page.rows[0].created_at_epoch_seconds, 139);
    }

    #[test]
    fn lifecycle_round_trips_through_its_canonical_name() {
        let fixture = Fixture::new();
        fixture.meeting("meeting-a", 100, &["alpha"]);
        let index = synced(&fixture);
        let page = index
            .list(&ListRequest {
                lifecycles: vec![MeetingLifecycle::TranscriptReady],
                ..Default::default()
            })
            .unwrap();
        assert_eq!(page.total, 1);
        assert_eq!(page.rows[0].lifecycle, MeetingLifecycle::TranscriptReady);
        assert_eq!(
            lifecycle_name(MeetingLifecycle::TranscriptReady).unwrap(),
            "transcript-ready"
        );

        let empty = index
            .list(&ListRequest {
                lifecycles: vec![MeetingLifecycle::Ready],
                ..Default::default()
            })
            .unwrap();
        assert_eq!(empty.total, 0);
    }

    /// SQLite opens a path directly, so none of the descriptor-bound guards in
    /// `storage.rs` apply to it. These are the checks that replace them.
    #[test]
    fn every_file_the_index_leaves_behind_is_private() {
        use std::os::unix::fs::PermissionsExt;
        let fixture = Fixture::new();
        fixture.meeting("meeting-a", 100, &["alpha"]);
        let index = synced(&fixture);
        drop(index);

        let library = fixture.storage.path().join("library");
        let mut seen = 0;
        for entry in std::fs::read_dir(&library).unwrap() {
            let entry = entry.unwrap();
            let metadata = entry.metadata().unwrap();
            assert_eq!(
                metadata.permissions().mode() & 0o777,
                0o600,
                "{:?} is not 0600",
                entry.file_name()
            );
            seen += 1;
        }
        // No `-wal` or `-shm`: rollback journalling leaves one file at rest.
        assert_eq!(seen, 1);
    }

    #[test]
    fn a_group_readable_database_is_refused_rather_than_opened() {
        use std::os::unix::fs::PermissionsExt;
        let fixture = Fixture::new();
        let index = CorpusIndex::open(&fixture.storage).unwrap();
        let path = index.path().to_path_buf();
        drop(index);
        std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o640)).unwrap();
        assert!(matches!(
            CorpusIndex::open(&fixture.storage),
            Err(CorpusIndexError::NotPrivate)
        ));
    }

    #[test]
    fn a_newer_schema_refuses_instead_of_reading_columns_it_does_not_know() {
        let fixture = Fixture::new();
        let index = CorpusIndex::open(&fixture.storage).unwrap();
        index
            .connection
            .execute(
                "UPDATE index_identity SET applied_migration = ?1 WHERE id = 0",
                params![APPLIED_MIGRATION + 1],
            )
            .unwrap();
        drop(index);
        assert!(matches!(
            CorpusIndex::open(&fixture.storage),
            Err(CorpusIndexError::SchemaAhead)
        ));
    }

    #[test]
    fn the_index_records_the_sqlite_build_that_wrote_it() {
        let fixture = Fixture::new();
        let index = CorpusIndex::open(&fixture.storage).unwrap();
        let (schema, sqlite_version) = index.identity().unwrap();
        assert_eq!(schema, CORPUS_INDEX_SCHEMA);
        assert_eq!(sqlite_version, rusqlite::version());
        assert!(!sqlite_version.is_empty());
    }

    #[test]
    fn a_removed_meeting_leaves_no_turn_behind() {
        let fixture = Fixture::new();
        fixture.meeting("meeting-a", 100, &["alpha", "beta"]);
        fixture.meeting("meeting-b", 200, &["gamma"]);
        let mut index = synced(&fixture);
        let turns: i64 = index
            .connection
            .query_row("SELECT COUNT(*) FROM turn", [], |row| row.get(0))
            .unwrap();
        assert_eq!(turns, 3);

        std::fs::remove_dir_all(fixture.storage.path().join("meetings").join("meeting-a")).unwrap();
        let outcome = index
            .replace_from_projection(&fixture.projection())
            .unwrap();
        assert_eq!(outcome.meetings, 1);
        assert_eq!(outcome.turns, 1);
        let turns: i64 = index
            .connection
            .query_row("SELECT COUNT(*) FROM turn", [], |row| row.get(0))
            .unwrap();
        assert_eq!(turns, 1);
    }
}

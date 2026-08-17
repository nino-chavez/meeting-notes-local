//! Bounded, local exact replacements for names and meeting jargon.
//!
//! The vocabulary is an operator-owned list, not a text-learning system.  It
//! only matches the exact, case-sensitive source phrase supplied by the
//! operator.  Projections are derived values: this module never edits a
//! transcript or any other input artifact.

use std::collections::HashSet;
use std::fs::{self, OpenOptions};
use std::io::{self, Read};
use std::ops::Range;
use std::os::unix::fs::{OpenOptionsExt, PermissionsExt};
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use thiserror::Error;
use uuid::Uuid;

use crate::storage::{StorageRoot, durable_replace};

const VOCABULARY_FILE: &str = "local-vocabulary.json";
const MAX_DOCUMENT_BYTES: u64 = 256 * 1024;
const MAX_ENTRIES: usize = 256;
const MAX_ENTRY_TEXT_BYTES: usize = 512;
const MAX_ENTRY_TEXT_SCALARS: usize = 256;
const MAX_PROJECTION_BYTES: usize = 1024 * 1024;
/// A generate command is one bounded frame. Keep the vocabulary part well
/// below that frame's 64 KiB ceiling even when every replacement uses its
/// largest legal text.
const MAX_RANGE_REPLACEMENTS: usize = 64;

/// Limits exposed for the local UI and its tests.  Crossing any limit fails
/// closed; this store does not truncate operator input.
pub const LOCAL_VOCABULARY_MAX_DOCUMENT_BYTES: u64 = MAX_DOCUMENT_BYTES;
pub const LOCAL_VOCABULARY_MAX_ENTRIES: usize = MAX_ENTRIES;
pub const LOCAL_VOCABULARY_MAX_ENTRY_TEXT_BYTES: usize = MAX_ENTRY_TEXT_BYTES;
pub const LOCAL_VOCABULARY_MAX_ENTRY_TEXT_SCALARS: usize = MAX_ENTRY_TEXT_SCALARS;
pub const LOCAL_VOCABULARY_MAX_PROJECTION_BYTES: usize = MAX_PROJECTION_BYTES;
pub const LOCAL_VOCABULARY_MAX_RANGE_REPLACEMENTS: usize = MAX_RANGE_REPLACEMENTS;

#[derive(Debug, Error)]
pub enum LocalVocabularyError {
    #[error("local vocabulary storage is invalid or unreadable")]
    InvalidPrivateStorage,
    #[error("local vocabulary document is malformed: {0}")]
    Malformed(&'static str),
    #[error("local vocabulary entry is invalid: {0}")]
    InvalidEntry(&'static str),
    #[error("local vocabulary entry was not found")]
    NotFound,
    #[error("local vocabulary source phrase already exists")]
    DuplicateSourcePhrase,
    #[error("local vocabulary has reached its entry limit")]
    TooManyEntries,
    #[error("local vocabulary text exceeds its limit")]
    TextTooLarge,
    #[error("local vocabulary document exceeds its limit")]
    DocumentTooLarge,
    #[error("local vocabulary projection has too many replacements for one note request")]
    TooManyRangeReplacements,
    #[error(transparent)]
    Io(#[from] io::Error),
    #[error(transparent)]
    Json(#[from] serde_json::Error),
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct LocalVocabularyEntry {
    pub id: Uuid,
    pub source_phrase: String,
    pub preferred_replacement: String,
    pub enabled: bool,
    pub created_order: u64,
    pub updated_order: u64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct VocabularyApplication {
    pub entry_id: Uuid,
    /// Byte range in the original input text.  It remains valid even when
    /// the replacement has a different byte length.
    pub range: Range<usize>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct VocabularyProjection {
    pub text: String,
    pub applied: Vec<VocabularyApplication>,
}

/// One prompt-only replacement tied to an immutable source-turn scalar span.
///
/// `source_sha256` is the bytes of the original span, never the replacement.
/// The worker re-derives it from the retained transcript before it sends a
/// model request, so a vocabulary edit or a stale transcript cannot silently
/// move a replacement to different evidence.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct VocabularyRangeReplacement {
    pub turn: u32,
    pub char_start: u32,
    pub char_end: u32,
    pub source_sha256: String,
    pub replacement: String,
}

#[derive(Debug, Clone)]
pub struct LocalVocabularyStore {
    root: PathBuf,
    file: PathBuf,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct VocabularyDocument {
    schema: VocabularySchema,
    entries: Vec<LocalVocabularyEntryWire>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
enum VocabularySchema {
    #[serde(rename = "local-vocabulary/1")]
    V1,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct LocalVocabularyEntryWire {
    id: Uuid,
    source_phrase: String,
    preferred_replacement: String,
    enabled: bool,
    created_order: u64,
    updated_order: u64,
}

impl LocalVocabularyStore {
    /// Open the one bounded vocabulary document below an already-created
    /// [`StorageRoot`].  Opening never creates or repairs a document.
    pub fn open(root: &StorageRoot) -> Result<Self, LocalVocabularyError> {
        require_private_directory(root.path())?;
        let file = root
            .resolve(Path::new(VOCABULARY_FILE))
            .map_err(|_| LocalVocabularyError::InvalidPrivateStorage)?;
        if let Ok(metadata) = fs::symlink_metadata(&file) {
            validate_file_metadata(&metadata)?;
        }
        Ok(Self {
            root: root.path().to_path_buf(),
            file,
        })
    }

    /// Read the current entries in deterministic created-order.
    pub fn read(&self) -> Result<Vec<LocalVocabularyEntry>, LocalVocabularyError> {
        Ok(self.load()?.into_iter().map(Into::into).collect())
    }

    /// Alias for callers whose operation is explicitly a list operation.
    pub fn list(&self) -> Result<Vec<LocalVocabularyEntry>, LocalVocabularyError> {
        self.read()
    }

    pub fn add(
        &self,
        source_phrase: &str,
        preferred_replacement: &str,
    ) -> Result<LocalVocabularyEntry, LocalVocabularyError> {
        validate_text(source_phrase)?;
        validate_text(preferred_replacement)?;
        if source_phrase == preferred_replacement {
            return Err(LocalVocabularyError::InvalidEntry(
                "source and replacement must differ",
            ));
        }
        let id = Uuid::new_v4();
        let mut document = self.load()?;
        if document.len() >= MAX_ENTRIES {
            return Err(LocalVocabularyError::TooManyEntries);
        }
        if document
            .iter()
            .any(|entry| entry.source_phrase == source_phrase)
        {
            return Err(LocalVocabularyError::DuplicateSourcePhrase);
        }
        let order = next_order(&document)?;
        document.push(LocalVocabularyEntryWire {
            id,
            source_phrase: source_phrase.to_owned(),
            preferred_replacement: preferred_replacement.to_owned(),
            enabled: true,
            created_order: order,
            updated_order: order,
        });
        self.save(document)?;
        Ok(LocalVocabularyEntry {
            id,
            source_phrase: source_phrase.to_owned(),
            preferred_replacement: preferred_replacement.to_owned(),
            enabled: true,
            created_order: order,
            updated_order: order,
        })
    }

    pub fn edit(
        &self,
        id: Uuid,
        source_phrase: &str,
        preferred_replacement: &str,
    ) -> Result<LocalVocabularyEntry, LocalVocabularyError> {
        validate_text(source_phrase)?;
        validate_text(preferred_replacement)?;
        if source_phrase == preferred_replacement {
            return Err(LocalVocabularyError::InvalidEntry(
                "source and replacement must differ",
            ));
        }
        let mut document = self.load()?;
        if !document.iter().any(|entry| entry.id == id) {
            return Err(LocalVocabularyError::NotFound);
        }
        if document
            .iter()
            .any(|entry| entry.id != id && entry.source_phrase == source_phrase)
        {
            return Err(LocalVocabularyError::DuplicateSourcePhrase);
        }
        let updated_order = next_order(&document)?;
        let entry = document
            .iter_mut()
            .find(|entry| entry.id == id)
            .ok_or(LocalVocabularyError::NotFound)?;
        entry.source_phrase = source_phrase.to_owned();
        entry.preferred_replacement = preferred_replacement.to_owned();
        entry.updated_order = updated_order;
        let result = entry.clone();
        self.save(document)?;
        Ok(result.into())
    }

    pub fn enable(&self, id: Uuid) -> Result<LocalVocabularyEntry, LocalVocabularyError> {
        self.set_enabled(id, true)
    }

    pub fn disable(&self, id: Uuid) -> Result<LocalVocabularyEntry, LocalVocabularyError> {
        self.set_enabled(id, false)
    }

    pub fn set_enabled(
        &self,
        id: Uuid,
        enabled: bool,
    ) -> Result<LocalVocabularyEntry, LocalVocabularyError> {
        let mut document = self.load()?;
        let updated_order = next_order(&document)?;
        let entry = document
            .iter_mut()
            .find(|entry| entry.id == id)
            .ok_or(LocalVocabularyError::NotFound)?;
        entry.enabled = enabled;
        entry.updated_order = updated_order;
        let result = entry.clone();
        self.save(document)?;
        Ok(result.into())
    }

    pub fn delete(&self, id: Uuid) -> Result<(), LocalVocabularyError> {
        let mut document = self.load()?;
        let prior = document.len();
        document.retain(|entry| entry.id != id);
        if document.len() == prior {
            return Err(LocalVocabularyError::NotFound);
        }
        self.save(document)
    }

    /// Project exact, case-sensitive matches from the original text.  Matches
    /// are chosen left-to-right, preferring the longest source at each start,
    /// then the stable created-order.  Output is never scanned again.
    pub fn project(&self, input: &str) -> Result<VocabularyProjection, LocalVocabularyError> {
        if input.len() > MAX_PROJECTION_BYTES {
            return Err(LocalVocabularyError::TextTooLarge);
        }
        let entries = self
            .load()?
            .into_iter()
            .filter(|entry| entry.enabled)
            .collect::<Vec<_>>();
        project_with_entries(input, &entries)
    }

    /// Derive the closed prompt overlay for visible source turns.
    ///
    /// This is deliberately a pure derivation from retained turn text and the
    /// current enabled vocabulary. It does not create a transcript derivative.
    /// Scalar offsets are used on the wire because Python indexes `str` by
    /// Unicode scalar, while `VocabularyApplication` retains byte offsets for
    /// Rust callers that need them.
    pub fn project_turns(
        &self,
        turns: &[&str],
    ) -> Result<Vec<VocabularyRangeReplacement>, LocalVocabularyError> {
        if turns.len() > u32::MAX as usize {
            return Err(LocalVocabularyError::TextTooLarge);
        }
        let entries = self
            .load()?
            .into_iter()
            .filter(|entry| entry.enabled)
            .collect::<Vec<_>>();
        let mut replacements = Vec::new();
        for (turn, text) in turns.iter().enumerate() {
            let projection = project_with_entries(text, &entries)?;
            for application in projection.applied {
                if replacements.len() == MAX_RANGE_REPLACEMENTS {
                    return Err(LocalVocabularyError::TooManyRangeReplacements);
                }
                let source = &text[application.range.clone()];
                let entry = entries
                    .iter()
                    .find(|entry| entry.id == application.entry_id)
                    .expect("application entry came from the enabled entry list");
                replacements.push(VocabularyRangeReplacement {
                    turn: turn as u32,
                    char_start: text[..application.range.start].chars().count() as u32,
                    char_end: text[..application.range.end].chars().count() as u32,
                    source_sha256: format!("{:x}", Sha256::digest(source.as_bytes())),
                    replacement: entry.preferred_replacement.clone(),
                });
            }
        }
        Ok(replacements)
    }
}

fn project_with_entries(
    input: &str,
    entries: &[LocalVocabularyEntryWire],
) -> Result<VocabularyProjection, LocalVocabularyError> {
    if input.len() > MAX_PROJECTION_BYTES {
        return Err(LocalVocabularyError::TextTooLarge);
    }
    let mut output = String::with_capacity(input.len());
    let mut applied = Vec::new();
    let mut cursor = 0;
    while cursor < input.len() {
        let best = entries
            .iter()
            .filter(|entry| input[cursor..].starts_with(&entry.source_phrase))
            .max_by(|left, right| {
                left.source_phrase
                    .chars()
                    .count()
                    .cmp(&right.source_phrase.chars().count())
                    .then_with(|| right.created_order.cmp(&left.created_order))
                    .then_with(|| right.id.cmp(&left.id))
            });
        if let Some(entry) = best {
            let end = cursor + entry.source_phrase.len();
            if output
                .len()
                .checked_add(entry.preferred_replacement.len())
                .is_none_or(|length| length > MAX_PROJECTION_BYTES)
            {
                return Err(LocalVocabularyError::TextTooLarge);
            }
            applied.push(VocabularyApplication {
                entry_id: entry.id,
                range: cursor..end,
            });
            output.push_str(&entry.preferred_replacement);
            cursor = end;
        } else {
            let character = input[cursor..]
                .chars()
                .next()
                .expect("cursor is a character boundary");
            if output
                .len()
                .checked_add(character.len_utf8())
                .is_none_or(|length| length > MAX_PROJECTION_BYTES)
            {
                return Err(LocalVocabularyError::TextTooLarge);
            }
            output.push(character);
            cursor += character.len_utf8();
        }
    }
    if output.len() > MAX_PROJECTION_BYTES {
        return Err(LocalVocabularyError::TextTooLarge);
    }
    Ok(VocabularyProjection {
        text: output,
        applied,
    })
}

impl LocalVocabularyStore {
    fn load(&self) -> Result<Vec<LocalVocabularyEntryWire>, LocalVocabularyError> {
        require_private_directory(&self.root)?;
        let metadata = match fs::symlink_metadata(&self.file) {
            Ok(metadata) => metadata,
            Err(error) if error.kind() == io::ErrorKind::NotFound => return Ok(Vec::new()),
            Err(error) => return Err(error.into()),
        };
        validate_file_metadata(&metadata)?;
        if metadata.len() > MAX_DOCUMENT_BYTES {
            return Err(LocalVocabularyError::DocumentTooLarge);
        }
        let mut file = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_NOFOLLOW)
            .open(&self.file)
            .map_err(|_| LocalVocabularyError::InvalidPrivateStorage)?;
        let mut bytes = Vec::with_capacity(metadata.len() as usize);
        file.read_to_end(&mut bytes)
            .map_err(|_| LocalVocabularyError::InvalidPrivateStorage)?;
        if bytes.len() as u64 > MAX_DOCUMENT_BYTES {
            return Err(LocalVocabularyError::DocumentTooLarge);
        }
        let document: VocabularyDocument = serde_json::from_slice(&bytes)
            .map_err(|_| LocalVocabularyError::Malformed("document"))?;
        if !matches!(document.schema, VocabularySchema::V1) {
            return Err(LocalVocabularyError::Malformed("schema"));
        }
        validate_document(document.entries)
    }

    fn save(&self, entries: Vec<LocalVocabularyEntryWire>) -> Result<(), LocalVocabularyError> {
        require_private_directory(&self.root)?;
        let entries = validate_document(entries)?;
        let document = VocabularyDocument {
            schema: VocabularySchema::V1,
            entries,
        };
        let bytes = serde_json::to_vec_pretty(&document)?;
        if bytes.len() as u64 > MAX_DOCUMENT_BYTES {
            return Err(LocalVocabularyError::DocumentTooLarge);
        }
        if let Ok(metadata) = fs::symlink_metadata(&self.file) {
            validate_file_metadata(&metadata)?;
        }
        durable_replace(&self.file, &bytes)
            .map_err(|_| LocalVocabularyError::InvalidPrivateStorage)?;
        let metadata = fs::symlink_metadata(&self.file)
            .map_err(|_| LocalVocabularyError::InvalidPrivateStorage)?;
        validate_file_metadata(&metadata)
    }
}

fn require_private_directory(path: &Path) -> Result<(), LocalVocabularyError> {
    let metadata =
        fs::symlink_metadata(path).map_err(|_| LocalVocabularyError::InvalidPrivateStorage)?;
    if metadata.file_type().is_symlink()
        || !metadata.file_type().is_dir()
        || metadata.permissions().mode() & 0o777 != 0o700
    {
        return Err(LocalVocabularyError::InvalidPrivateStorage);
    }
    Ok(())
}

fn validate_file_metadata(metadata: &fs::Metadata) -> Result<(), LocalVocabularyError> {
    if metadata.file_type().is_symlink()
        || !metadata.file_type().is_file()
        || metadata.permissions().mode() & 0o777 != 0o600
    {
        return Err(LocalVocabularyError::InvalidPrivateStorage);
    }
    Ok(())
}

fn validate_text(text: &str) -> Result<(), LocalVocabularyError> {
    if text.is_empty() || text.trim().is_empty() {
        return Err(LocalVocabularyError::InvalidEntry("text is empty"));
    }
    if text.len() > MAX_ENTRY_TEXT_BYTES
        || text.chars().count() > MAX_ENTRY_TEXT_SCALARS
        || text.chars().any(char::is_control)
    {
        return Err(LocalVocabularyError::InvalidEntry("text is out of bounds"));
    }
    Ok(())
}

fn next_order(entries: &[LocalVocabularyEntryWire]) -> Result<u64, LocalVocabularyError> {
    entries
        .iter()
        .map(|entry| entry.created_order.max(entry.updated_order))
        .max()
        .unwrap_or(0)
        .checked_add(1)
        .ok_or(LocalVocabularyError::Malformed("ordering overflow"))
}

fn validate_document(
    mut entries: Vec<LocalVocabularyEntryWire>,
) -> Result<Vec<LocalVocabularyEntryWire>, LocalVocabularyError> {
    if entries.len() > MAX_ENTRIES {
        return Err(LocalVocabularyError::TooManyEntries);
    }
    let mut ids = HashSet::with_capacity(entries.len());
    let mut source_phrases = HashSet::with_capacity(entries.len());
    for entry in &entries {
        validate_text(&entry.source_phrase)?;
        validate_text(&entry.preferred_replacement)?;
        if entry.source_phrase == entry.preferred_replacement {
            return Err(LocalVocabularyError::InvalidEntry(
                "source and replacement must differ",
            ));
        }
        if entry.updated_order < entry.created_order {
            return Err(LocalVocabularyError::Malformed("ordering"));
        }
        if !ids.insert(entry.id) {
            return Err(LocalVocabularyError::Malformed("duplicate id"));
        }
        if !source_phrases.insert(&entry.source_phrase) {
            return Err(LocalVocabularyError::DuplicateSourcePhrase);
        }
    }
    entries.sort_by(|left, right| {
        left.created_order
            .cmp(&right.created_order)
            .then_with(|| left.id.cmp(&right.id))
    });
    Ok(entries)
}

impl From<LocalVocabularyEntryWire> for LocalVocabularyEntry {
    fn from(entry: LocalVocabularyEntryWire) -> Self {
        Self {
            id: entry.id,
            source_phrase: entry.source_phrase,
            preferred_replacement: entry.preferred_replacement,
            enabled: entry.enabled,
            created_order: entry.created_order,
            updated_order: entry.updated_order,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use std::os::unix::fs::PermissionsExt;
    use tempfile::TempDir;

    struct Fixture {
        _dir: TempDir,
        root: StorageRoot,
        store: LocalVocabularyStore,
    }

    impl Fixture {
        fn new() -> Self {
            let dir = TempDir::new().unwrap();
            let repo = dir.path().join("repo");
            fs::create_dir(&repo).unwrap();
            let root = StorageRoot::create(&dir.path().join("app-data"), &repo).unwrap();
            let store = LocalVocabularyStore::open(&root).unwrap();
            Self {
                _dir: dir,
                root,
                store,
            }
        }
    }

    #[test]
    fn restart_round_trip_and_crud_are_deterministic() {
        let fixture = Fixture::new();
        let added = fixture.store.add("Kibbel", "Kibble").unwrap();
        assert_eq!(fixture.store.list().unwrap(), vec![added.clone()]);
        let restarted = LocalVocabularyStore::open(&fixture.root).unwrap();
        assert_eq!(restarted.read().unwrap(), vec![added.clone()]);
        let edited = restarted
            .edit(added.id, "Kibbel Labs", "Kibble Labs")
            .unwrap();
        assert_eq!(edited.created_order, added.created_order);
        assert!(edited.updated_order > added.updated_order);
        let disabled = restarted.disable(edited.id).unwrap();
        assert!(!disabled.enabled);
        assert_eq!(
            restarted.project("Kibbel Labs").unwrap().text,
            "Kibbel Labs"
        );
        let enabled = restarted.enable(edited.id).unwrap();
        assert!(enabled.enabled);
        restarted.delete(edited.id).unwrap();
        assert!(restarted.list().unwrap().is_empty());
        assert!(matches!(
            restarted.delete(edited.id),
            Err(LocalVocabularyError::NotFound)
        ));
    }

    #[test]
    fn duplicate_and_invalid_entries_are_rejected() {
        let fixture = Fixture::new();
        fixture.store.add("Acme", "ACME").unwrap();
        assert!(matches!(
            fixture.store.add("Acme", "Other"),
            Err(LocalVocabularyError::DuplicateSourcePhrase)
        ));
        assert!(matches!(
            fixture.store.add("", "Replacement"),
            Err(LocalVocabularyError::InvalidEntry(_))
        ));
        assert!(matches!(
            fixture.store.add("same", "same"),
            Err(LocalVocabularyError::InvalidEntry(_))
        ));
        assert!(matches!(
            fixture.store.add("line\nbreak", "replacement"),
            Err(LocalVocabularyError::InvalidEntry(_))
        ));
    }

    #[test]
    fn serialized_documents_reject_unknown_fields_and_duplicate_ids() {
        let fixture = Fixture::new();
        let id = Uuid::new_v4();
        let entry = serde_json::json!({
            "id": id,
            "source_phrase": "Acme",
            "preferred_replacement": "ACME",
            "enabled": true,
            "created_order": 1,
            "updated_order": 1
        });
        let path = fixture.root.path().join(VOCABULARY_FILE);
        let unknown = serde_json::json!({
            "schema": "local-vocabulary/1",
            "entries": [entry.clone()],
            "unexpected": true
        });
        fs::write(&path, serde_json::to_vec(&unknown).unwrap()).unwrap();
        fs::set_permissions(&path, fs::Permissions::from_mode(0o600)).unwrap();
        assert!(matches!(
            fixture.store.list(),
            Err(LocalVocabularyError::Malformed(_))
        ));

        let duplicate = serde_json::json!({
            "schema": "local-vocabulary/1",
            "entries": [entry.clone(), {
                "id": id,
                "source_phrase": "Other",
                "preferred_replacement": "OTHER",
                "enabled": true,
                "created_order": 2,
                "updated_order": 2
            }]
        });
        fs::write(&path, serde_json::to_vec(&duplicate).unwrap()).unwrap();
        assert!(matches!(
            fixture.store.list(),
            Err(LocalVocabularyError::Malformed("duplicate id"))
        ));
    }

    #[test]
    fn exact_scope_case_and_overlap_order_are_preserved() {
        let fixture = Fixture::new();
        let short = fixture.store.add("New", "Old").unwrap();
        let long = fixture.store.add("New York", "NY").unwrap();
        let projection = fixture.store.project("New York meets new New.").unwrap();
        assert_eq!(projection.text, "NY meets new Old.");
        assert_eq!(projection.applied[0].entry_id, long.id);
        assert_eq!(projection.applied[0].range, 0..8);
        assert_eq!(projection.applied[1].entry_id, short.id);
        assert_eq!(projection.applied[1].range, 19..22);
    }

    #[test]
    fn equal_length_matches_use_stable_creation_order_and_do_not_recurse() {
        let fixture = Fixture::new();
        let first = fixture.store.add("AB", "ABCD").unwrap();
        let second = fixture.store.add("AB", "later");
        assert!(matches!(
            second,
            Err(LocalVocabularyError::DuplicateSourcePhrase)
        ));
        let nested = fixture.store.add("CD", "XX").unwrap();
        let projection = fixture.store.project("AB CD").unwrap();
        assert_eq!(projection.text, "ABCD XX");
        assert_eq!(projection.applied[0].entry_id, first.id);
        assert_eq!(projection.applied[0].range, 0..2);
        assert_eq!(projection.applied[1].entry_id, nested.id);
    }

    #[test]
    fn disabling_and_deleting_only_change_future_projections() {
        let fixture = Fixture::new();
        let entry = fixture.store.add("wrong", "right").unwrap();
        let original = String::from("wrong bytes stay exactly as written");
        let first = fixture.store.project(&original).unwrap();
        fixture.store.disable(entry.id).unwrap();
        assert_eq!(fixture.store.project(&original).unwrap().text, original);
        fixture.store.enable(entry.id).unwrap();
        assert_eq!(fixture.store.project(&original).unwrap(), first);
        fixture.store.delete(entry.id).unwrap();
        assert_eq!(fixture.store.project(&original).unwrap().text, original);
    }

    #[test]
    fn bounds_and_unreadable_storage_fail_closed() {
        let fixture = Fixture::new();
        let long = "x".repeat(MAX_ENTRY_TEXT_BYTES + 1);
        assert!(matches!(
            fixture.store.add(&long, "replacement"),
            Err(LocalVocabularyError::InvalidEntry(_))
        ));
        let path = fixture.root.path().join(VOCABULARY_FILE);
        fs::write(&path, vec![b'x'; MAX_DOCUMENT_BYTES as usize + 1]).unwrap();
        fs::set_permissions(&path, fs::Permissions::from_mode(0o600)).unwrap();
        assert!(matches!(
            fixture.store.list(),
            Err(LocalVocabularyError::DocumentTooLarge)
        ));
        fs::write(&path, b"{}").unwrap();
        assert!(matches!(
            fixture.store.list(),
            Err(LocalVocabularyError::Malformed(_))
        ));
        fs::set_permissions(&path, fs::Permissions::from_mode(0o644)).unwrap();
        assert!(matches!(
            fixture.store.list(),
            Err(LocalVocabularyError::InvalidPrivateStorage)
        ));
    }

    #[test]
    fn private_root_and_input_bytes_are_unchanged() {
        let fixture = Fixture::new();
        let entry = fixture.store.add("name", "Name").unwrap();
        let bytes = b"name\nname";
        let before = bytes.to_vec();
        let projection = fixture
            .store
            .project(std::str::from_utf8(bytes).unwrap())
            .unwrap();
        assert_eq!(bytes, before.as_slice());
        assert_eq!(projection.applied.len(), 2);
        assert_eq!(
            fs::metadata(fixture.root.path())
                .unwrap()
                .permissions()
                .mode()
                & 0o777,
            0o700
        );
        assert_eq!(
            fs::metadata(fixture.root.path().join(VOCABULARY_FILE))
                .unwrap()
                .permissions()
                .mode()
                & 0o777,
            0o600
        );
        assert_ne!(projection.text, std::str::from_utf8(bytes).unwrap());
        assert_eq!(projection.applied[0].entry_id, entry.id);
    }

    #[test]
    fn projection_stops_before_worst_case_expansion_can_grow_unbounded() {
        let fixture = Fixture::new();
        fixture
            .store
            .add("x", &"y".repeat(MAX_ENTRY_TEXT_SCALARS))
            .unwrap();
        let input = "x".repeat(MAX_PROJECTION_BYTES);
        assert!(matches!(
            fixture.store.project(&input),
            Err(LocalVocabularyError::TextTooLarge)
        ));
    }

    #[test]
    fn prompt_range_projection_keeps_original_scalar_offsets_when_text_length_changes() {
        let fixture = Fixture::new();
        fixture.store.add("Kibbel", "Kibble Labs").unwrap();
        let turns = [
            "Marta: Kibbel approved it.",
            "withheld Kibbel text is not supplied",
        ];
        let replacements = fixture.store.project_turns(&turns[..1]).unwrap();

        assert_eq!(replacements.len(), 1);
        assert_eq!(replacements[0].turn, 0);
        assert_eq!(replacements[0].char_start, 7);
        assert_eq!(replacements[0].char_end, 13);
        assert_eq!(replacements[0].replacement, "Kibble Labs");
        assert_eq!(
            replacements[0].source_sha256,
            format!("{:x}", Sha256::digest("Kibbel".as_bytes()))
        );
        // The only source passed to the pure derivation is visible turn zero.
        // A withheld row cannot get a prompt replacement by accident.
        assert!(fixture.store.project_turns(&[]).unwrap().is_empty());
    }

    #[test]
    fn prompt_range_projection_uses_the_same_overlap_and_no_op_rules() {
        let fixture = Fixture::new();
        fixture.store.add("New", "Old").unwrap();
        fixture.store.add("New York", "NY").unwrap();
        let replacements = fixture.store.project_turns(&["New York", "new"]).unwrap();
        assert_eq!(replacements.len(), 1);
        assert_eq!(replacements[0].turn, 0);
        assert_eq!(replacements[0].char_start, 0);
        assert_eq!(replacements[0].char_end, 8);
        assert_eq!(replacements[0].replacement, "NY");
    }

    #[test]
    fn prompt_range_projection_refuses_an_oversized_transport_overlay() {
        let fixture = Fixture::new();
        fixture.store.add("x", "y").unwrap();
        let turns = vec!["x"; MAX_RANGE_REPLACEMENTS + 1];
        assert!(matches!(
            fixture.store.project_turns(&turns),
            Err(LocalVocabularyError::TooManyRangeReplacements)
        ));
    }
}

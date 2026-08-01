use std::collections::HashMap;
use std::fs::{self, DirEntry};
use std::io;
use std::os::unix::fs::{DirBuilderExt, PermissionsExt};
use std::path::{Path, PathBuf};

use serde::Serialize;
use sha2::{Digest, Sha256};
use thiserror::Error;
use uuid::Uuid;

use crate::meeting::{
    MAX_RECEIPT_BYTES, MeetingError, MeetingRecord, read_private_bytes, require_private_directory,
};
use crate::operations::{
    MeetingOperationCommit, NoteGenerationRequest, NoteGenerationResult, NoteGenerationStatus,
    OperationContractError, ProductOperationKind, ProductOperationOutcome,
    TranscriptRestorationRequest, TranscriptRestorationResult,
};
use crate::storage::{StorageRoot, durable_create_new, sync_directory};

const OPERATIONS_DIRECTORY: &str = "operations";
const REQUEST_FILE: &str = "request.json";
const RESULT_FILE: &str = "result.json";
const COMMIT_FILE: &str = "commit.json";

#[derive(Debug, Error)]
pub enum OperationStoreError {
    #[error("operation receipt storage is invalid")]
    InvalidPrivateStorage,
    #[error("operation receipt is malformed: {0}")]
    Malformed(&'static str),
    #[error("operation receipt already exists")]
    AlreadyExists,
    #[error("operation receipt already exists with different bytes")]
    ConflictingBytes,
    #[error(transparent)]
    Io(#[from] io::Error),
}

impl From<MeetingError> for OperationStoreError {
    fn from(error: MeetingError) -> Self {
        match error {
            MeetingError::Io(error) => Self::Io(error),
            _ => Self::InvalidPrivateStorage,
        }
    }
}

impl From<OperationContractError> for OperationStoreError {
    fn from(_: OperationContractError) -> Self {
        Self::Malformed("receipt contract is invalid")
    }
}

#[derive(Debug, Clone)]
pub struct OperationStore {
    operations_dir: PathBuf,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum StoredOperationRequest {
    Restoration(TranscriptRestorationRequest),
    NoteGeneration(NoteGenerationRequest),
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum StoredOperationResult {
    Restoration(TranscriptRestorationResult),
    NoteGeneration(NoteGenerationResult),
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct StoredOperationReceipt {
    pub request: StoredOperationRequest,
    pub result: Option<StoredOperationResult>,
    pub commit: Option<MeetingOperationCommit>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum OperationReceiptState {
    RequestOnly,
    ResultStored,
    Committed,
}

impl StoredOperationRequest {
    pub fn operation_id(&self) -> Uuid {
        match self {
            Self::Restoration(request) => request.operation_id,
            Self::NoteGeneration(request) => request.operation_id,
        }
    }

    fn validate(&self) -> Result<(), OperationStoreError> {
        match self {
            Self::Restoration(request) => request.validate()?,
            Self::NoteGeneration(request) => request.validate()?,
        }
        Ok(())
    }

    fn canonical_bytes(&self) -> Result<Vec<u8>, OperationStoreError> {
        match self {
            Self::Restoration(request) => canonical_bytes(request),
            Self::NoteGeneration(request) => canonical_bytes(request),
        }
    }
}

impl StoredOperationResult {
    fn validate(&self) -> Result<(), OperationStoreError> {
        match self {
            Self::Restoration(result) => result.validate()?,
            Self::NoteGeneration(result) => result.validate()?,
        }
        Ok(())
    }

    fn canonical_bytes(&self) -> Result<Vec<u8>, OperationStoreError> {
        match self {
            Self::Restoration(result) => canonical_bytes(result),
            Self::NoteGeneration(result) => canonical_bytes(result),
        }
    }
}

impl StoredOperationReceipt {
    pub fn state(&self) -> OperationReceiptState {
        match (&self.result, &self.commit) {
            (None, None) => OperationReceiptState::RequestOnly,
            (Some(_), None) => OperationReceiptState::ResultStored,
            (Some(_), Some(_)) => OperationReceiptState::Committed,
            (None, Some(_)) => unreachable!("receipt validation refuses a commit without a result"),
        }
    }
}

impl OperationStore {
    pub fn open(root: &StorageRoot) -> Result<Self, OperationStoreError> {
        let operations_dir = root
            .resolve(Path::new(OPERATIONS_DIRECTORY))
            .map_err(|_| OperationStoreError::InvalidPrivateStorage)?;
        create_private_operation_root(&operations_dir)?;
        require_private_directory(&operations_dir)?;
        Ok(Self { operations_dir })
    }

    pub fn write_request(
        &self,
        request: &StoredOperationRequest,
    ) -> Result<(), OperationStoreError> {
        request.validate()?;
        let operation_dir = self.ensure_operation_dir(request.operation_id())?;
        write_receipt(
            &operation_dir.join(REQUEST_FILE),
            &request.canonical_bytes()?,
        )
    }

    pub fn write_result(
        &self,
        operation_id: Uuid,
        result: &StoredOperationResult,
    ) -> Result<(), OperationStoreError> {
        result.validate()?;
        let operation_dir = self.existing_operation_dir(operation_id)?;
        let request = self.load_request(&operation_dir)?;
        validate_result_matches_request(&request, result)?;
        write_receipt(&operation_dir.join(RESULT_FILE), &result.canonical_bytes()?)
    }

    pub fn write_commit(
        &self,
        operation_id: Uuid,
        commit: &MeetingOperationCommit,
        meeting: &MeetingRecord,
        meeting_bytes: &[u8],
    ) -> Result<(), OperationStoreError> {
        commit.validate()?;
        let operation_dir = self.existing_operation_dir(operation_id)?;
        let request = self.load_request(&operation_dir)?;
        let result = self
            .load_result(&operation_dir)?
            .ok_or(OperationStoreError::Malformed(
                "terminal commit lacks a result",
            ))?;
        validate_commit_matches_receipts(&request, &result, commit)?;
        crate::operations::validate_commit_meeting(commit, meeting, meeting_bytes)?;
        write_receipt(&operation_dir.join(COMMIT_FILE), &canonical_bytes(commit)?)
    }

    pub fn load(&self, operation_id: Uuid) -> Result<StoredOperationReceipt, OperationStoreError> {
        let operation_dir = self.existing_operation_dir(operation_id)?;
        self.load_from_dir(&operation_dir, operation_id)
    }

    pub fn scan(&self) -> Result<HashMap<Uuid, StoredOperationReceipt>, OperationStoreError> {
        require_private_directory(&self.operations_dir)?;
        let mut receipts = HashMap::new();
        for entry in fs::read_dir(&self.operations_dir)? {
            let entry = entry?;
            let operation_id = operation_id_from_entry(&entry)?;
            let operation_dir = entry.path();
            let receipt = self.load_from_dir(&operation_dir, operation_id)?;
            if receipts.insert(operation_id, receipt).is_some() {
                return Err(OperationStoreError::Malformed(
                    "duplicate operation identifier",
                ));
            }
        }
        Ok(receipts)
    }

    fn ensure_operation_dir(&self, operation_id: Uuid) -> Result<PathBuf, OperationStoreError> {
        let path = self.operation_path(operation_id);
        match fs::symlink_metadata(&path) {
            Ok(metadata) => {
                if metadata.file_type().is_symlink()
                    || !metadata.file_type().is_dir()
                    || metadata.permissions().mode() & 0o777 != 0o700
                {
                    return Err(OperationStoreError::InvalidPrivateStorage);
                }
            }
            Err(error) if error.kind() == io::ErrorKind::NotFound => {
                create_new_private_directory(&path, &self.operations_dir)?;
            }
            Err(error) => return Err(error.into()),
        }
        require_private_directory(&path)?;
        Ok(path)
    }

    fn existing_operation_dir(&self, operation_id: Uuid) -> Result<PathBuf, OperationStoreError> {
        let path = self.operation_path(operation_id);
        require_private_directory(&path)?;
        Ok(path)
    }

    fn operation_path(&self, operation_id: Uuid) -> PathBuf {
        self.operations_dir.join(operation_id.to_string())
    }

    fn load_from_dir(
        &self,
        operation_dir: &Path,
        operation_id: Uuid,
    ) -> Result<StoredOperationReceipt, OperationStoreError> {
        require_private_directory(operation_dir)?;
        let request = self.load_request(operation_dir)?;
        if request.operation_id() != operation_id {
            return Err(OperationStoreError::Malformed(
                "request identifier differs from directory",
            ));
        }
        let result = self.load_result(operation_dir)?;
        if let Some(result) = &result {
            validate_result_matches_request(&request, result)?;
        }
        let commit = read_optional(operation_dir, COMMIT_FILE, parse_commit)?;
        match (&result, &commit) {
            (None, Some(_)) => {
                return Err(OperationStoreError::Malformed(
                    "terminal commit lacks a result",
                ));
            }
            (Some(result), Some(commit)) => {
                validate_commit_matches_receipts(&request, result, commit)?
            }
            _ => {}
        }
        Ok(StoredOperationReceipt {
            request,
            result,
            commit,
        })
    }

    fn load_request(
        &self,
        operation_dir: &Path,
    ) -> Result<StoredOperationRequest, OperationStoreError> {
        read_required(operation_dir, REQUEST_FILE, parse_request)
    }

    fn load_result(
        &self,
        operation_dir: &Path,
    ) -> Result<Option<StoredOperationResult>, OperationStoreError> {
        read_optional(operation_dir, RESULT_FILE, parse_result)
    }
}

fn create_private_operation_root(path: &Path) -> Result<(), OperationStoreError> {
    match fs::symlink_metadata(path) {
        Ok(metadata) => {
            if metadata.file_type().is_symlink()
                || !metadata.file_type().is_dir()
                || metadata.permissions().mode() & 0o777 != 0o700
            {
                return Err(OperationStoreError::InvalidPrivateStorage);
            }
        }
        Err(error) if error.kind() == io::ErrorKind::NotFound => {
            let parent = path
                .parent()
                .ok_or(OperationStoreError::InvalidPrivateStorage)?;
            create_new_private_directory(path, parent)?;
        }
        Err(error) => return Err(error.into()),
    }
    Ok(())
}

fn create_new_private_directory(path: &Path, parent: &Path) -> Result<(), OperationStoreError> {
    require_private_directory(parent)?;
    let mut builder = fs::DirBuilder::new();
    builder.mode(0o700);
    builder.create(path)?;
    require_private_directory(path)?;
    sync_directory(parent)?;
    Ok(())
}

fn write_receipt(path: &Path, bytes: &[u8]) -> Result<(), OperationStoreError> {
    match fs::symlink_metadata(path) {
        Ok(metadata) => {
            if metadata.file_type().is_symlink()
                || !metadata.file_type().is_file()
                || metadata.permissions().mode() & 0o777 != 0o600
            {
                return Err(OperationStoreError::InvalidPrivateStorage);
            }
            if read_private_bytes(path, MAX_RECEIPT_BYTES)? == bytes {
                return Err(OperationStoreError::AlreadyExists);
            }
            return Err(OperationStoreError::ConflictingBytes);
        }
        Err(error) if error.kind() == io::ErrorKind::NotFound => {}
        Err(error) => return Err(error.into()),
    }
    durable_create_new(path, bytes).map_err(|error| {
        if error.kind() == io::ErrorKind::AlreadyExists {
            OperationStoreError::AlreadyExists
        } else {
            OperationStoreError::Io(error)
        }
    })
}

fn read_required<T>(
    operation_dir: &Path,
    name: &str,
    parse: impl FnOnce(&[u8]) -> Result<T, OperationStoreError>,
) -> Result<T, OperationStoreError> {
    let path = operation_dir.join(name);
    match fs::symlink_metadata(&path) {
        Ok(_) => {}
        Err(error) if error.kind() == io::ErrorKind::NotFound => {
            return Err(OperationStoreError::Malformed(
                "operation request is missing",
            ));
        }
        Err(error) => return Err(error.into()),
    }
    parse(&read_private_bytes(&path, MAX_RECEIPT_BYTES)?)
}

fn read_optional<T>(
    operation_dir: &Path,
    name: &str,
    parse: impl FnOnce(&[u8]) -> Result<T, OperationStoreError>,
) -> Result<Option<T>, OperationStoreError> {
    let path = operation_dir.join(name);
    match fs::symlink_metadata(&path) {
        Ok(_) => parse(&read_private_bytes(&path, MAX_RECEIPT_BYTES)?).map(Some),
        Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(None),
        Err(error) => Err(error.into()),
    }
}

fn parse_request(bytes: &[u8]) -> Result<StoredOperationRequest, OperationStoreError> {
    if let Ok(request) = serde_json::from_slice::<TranscriptRestorationRequest>(bytes) {
        request.validate()?;
        ensure_canonical(bytes, &request)?;
        return Ok(StoredOperationRequest::Restoration(request));
    }
    let request = serde_json::from_slice::<NoteGenerationRequest>(bytes)
        .map_err(|_| OperationStoreError::Malformed("request schema is not recognized"))?;
    request.validate()?;
    ensure_canonical(bytes, &request)?;
    Ok(StoredOperationRequest::NoteGeneration(request))
}

fn parse_result(bytes: &[u8]) -> Result<StoredOperationResult, OperationStoreError> {
    if let Ok(result) = serde_json::from_slice::<TranscriptRestorationResult>(bytes) {
        result.validate()?;
        ensure_canonical(bytes, &result)?;
        return Ok(StoredOperationResult::Restoration(result));
    }
    let result = serde_json::from_slice::<NoteGenerationResult>(bytes)
        .map_err(|_| OperationStoreError::Malformed("result schema is not recognized"))?;
    result.validate()?;
    ensure_canonical(bytes, &result)?;
    Ok(StoredOperationResult::NoteGeneration(result))
}

fn parse_commit(bytes: &[u8]) -> Result<MeetingOperationCommit, OperationStoreError> {
    let commit: MeetingOperationCommit = serde_json::from_slice(bytes)
        .map_err(|_| OperationStoreError::Malformed("commit schema is not recognized"))?;
    commit.validate()?;
    ensure_canonical(bytes, &commit)?;
    Ok(commit)
}

fn canonical_bytes<T: Serialize>(value: &T) -> Result<Vec<u8>, OperationStoreError> {
    serde_json::to_vec_pretty(value)
        .map_err(|_| OperationStoreError::Malformed("receipt cannot be serialized"))
}

fn ensure_canonical<T: Serialize>(bytes: &[u8], value: &T) -> Result<(), OperationStoreError> {
    if bytes != canonical_bytes(value)? {
        return Err(OperationStoreError::Malformed(
            "receipt bytes are not canonical",
        ));
    }
    Ok(())
}

fn validate_result_matches_request(
    request: &StoredOperationRequest,
    result: &StoredOperationResult,
) -> Result<(), OperationStoreError> {
    let agrees = match (request, result) {
        (
            StoredOperationRequest::Restoration(request),
            StoredOperationResult::Restoration(result),
        ) => {
            request.operation_id == result.operation_id
                && request.meeting_id == result.meeting_id
                && request.source_transcript_sha256 == result.source_transcript_sha256
        }
        (
            StoredOperationRequest::NoteGeneration(request),
            StoredOperationResult::NoteGeneration(result),
        ) => {
            request.operation_id == result.operation_id
                && request.meeting_id == result.meeting_id
                && request.source_transcript_sha256 == result.source_transcript_sha256
        }
        _ => false,
    };
    if !agrees {
        return Err(OperationStoreError::Malformed(
            "request and result schemas disagree",
        ));
    }
    Ok(())
}

fn validate_commit_matches_receipts(
    request: &StoredOperationRequest,
    result: &StoredOperationResult,
    commit: &MeetingOperationCommit,
) -> Result<(), OperationStoreError> {
    let request_digest = digest_bytes(&request.canonical_bytes()?);
    let result_digest = digest_bytes(&result.canonical_bytes()?);
    let coherent = match (request, result) {
        (
            StoredOperationRequest::Restoration(request),
            StoredOperationResult::Restoration(result),
        ) => {
            commit.operation_id == request.operation_id
                && commit.meeting_id == request.meeting_id
                && commit.kind == ProductOperationKind::RestoreWithheldTurn
                && commit.outcome == ProductOperationOutcome::TranscriptRestored
                && commit.request_sha256 == request_digest
                && commit.result_sha256 == result_digest
                && commit.current_transcript_sha256 == result.view.sha256
        }
        (
            StoredOperationRequest::NoteGeneration(request),
            StoredOperationResult::NoteGeneration(result),
        ) => {
            let outcome = match result.status {
                NoteGenerationStatus::Accepted => ProductOperationOutcome::NoteAccepted,
                NoteGenerationStatus::Rejected => ProductOperationOutcome::NoteRejected,
            };
            commit.operation_id == request.operation_id
                && commit.meeting_id == request.meeting_id
                && commit.kind == ProductOperationKind::GenerateNote
                && commit.outcome == outcome
                && commit.request_sha256 == request_digest
                && commit.result_sha256 == result_digest
                && commit.current_transcript_sha256 == request.source_transcript_sha256
                && commit.current_note == result.note
        }
        _ => false,
    };
    if !coherent {
        return Err(OperationStoreError::Malformed(
            "commit does not bind the stored receipts",
        ));
    }
    Ok(())
}

fn digest_bytes(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

fn operation_id_from_entry(entry: &DirEntry) -> Result<Uuid, OperationStoreError> {
    let metadata = entry.metadata()?;
    if !metadata.file_type().is_dir() || metadata.permissions().mode() & 0o777 != 0o700 {
        return Err(OperationStoreError::InvalidPrivateStorage);
    }
    let name = entry
        .file_name()
        .into_string()
        .map_err(|_| OperationStoreError::Malformed("operation directory name is invalid"))?;
    let operation_id = Uuid::parse_str(&name)
        .map_err(|_| OperationStoreError::Malformed("operation directory name is invalid"))?;
    if name != operation_id.to_string() {
        return Err(OperationStoreError::Malformed(
            "operation directory name is not canonical",
        ));
    }
    Ok(operation_id)
}

#[cfg(test)]
mod tests {
    use std::sync::Mutex;

    use std::os::unix::fs::{PermissionsExt, symlink};

    use serde::de::DeserializeOwned;
    use serde_json::Value;
    use tempfile::TempDir;

    use super::*;

    static UMASK_LOCK: Mutex<()> = Mutex::new(());

    fn fixtures() -> Value {
        serde_json::from_str(include_str!(
            "../../../tests/fixtures/product-operations-v1.json"
        ))
        .expect("shared operation fixture must be JSON")
    }

    fn parse<T: DeserializeOwned>(fixture: &Value, path: &[&str]) -> T {
        let mut value = fixture;
        for segment in path {
            value = &value[*segment];
        }
        serde_json::from_value(value.clone()).expect("fixture must match closed schema")
    }

    fn store() -> (TempDir, OperationStore) {
        let temp = TempDir::new().unwrap();
        let repo = temp.path().join("repo");
        fs::create_dir(&repo).unwrap();
        fs::set_permissions(&repo, fs::Permissions::from_mode(0o700)).unwrap();
        let root = StorageRoot::create(&temp.path().join("app"), &repo).unwrap();
        let store = OperationStore::open(&root).unwrap();
        (temp, store)
    }

    fn restoration_request(fixture: &Value) -> StoredOperationRequest {
        StoredOperationRequest::Restoration(parse(fixture, &["restoration", "request"]))
    }

    fn restoration_result(fixture: &Value) -> StoredOperationResult {
        StoredOperationResult::Restoration(parse(fixture, &["restoration", "result"]))
    }

    #[test]
    fn request_writes_are_create_new_and_preserve_exact_bytes() {
        let fixture = fixtures();
        let (temp, store) = store();
        let request = restoration_request(&fixture);
        let operation_id = request.operation_id();
        store.write_request(&request).unwrap();
        assert!(matches!(
            store.write_request(&request),
            Err(OperationStoreError::AlreadyExists)
        ));

        let mut changed = request.clone();
        match &mut changed {
            StoredOperationRequest::Restoration(restoration) => {
                restoration.requested_at_epoch_seconds += 1;
            }
            StoredOperationRequest::NoteGeneration(_) => unreachable!(),
        }
        assert!(matches!(
            store.write_request(&changed),
            Err(OperationStoreError::ConflictingBytes)
        ));
        assert_eq!(store.load(operation_id).unwrap().request, request);
        assert_eq!(
            read_private_bytes(
                &temp
                    .path()
                    .join("app")
                    .join(OPERATIONS_DIRECTORY)
                    .join(operation_id.to_string())
                    .join(REQUEST_FILE),
                MAX_RECEIPT_BYTES,
            )
            .unwrap(),
            request.canonical_bytes().unwrap()
        );
    }

    #[test]
    fn scan_reports_request_only_and_result_stored_without_ordering() {
        let fixture = fixtures();
        let (_temp, store) = store();
        let request = restoration_request(&fixture);
        let operation_id = request.operation_id();
        store.write_request(&request).unwrap();
        assert_eq!(
            store.scan().unwrap()[&operation_id].state(),
            OperationReceiptState::RequestOnly
        );

        let result = restoration_result(&fixture);
        store.write_result(operation_id, &result).unwrap();
        let scanned = store.scan().unwrap();
        assert_eq!(
            scanned[&operation_id].state(),
            OperationReceiptState::ResultStored
        );
        assert_eq!(scanned.len(), 1);
    }

    #[test]
    fn result_stored_does_not_claim_artifact_validation_or_recovery_authority() {
        let fixture = fixtures();
        let (temp, store) = store();
        let request = restoration_request(&fixture);
        let result = restoration_result(&fixture);
        let operation_id = request.operation_id();
        store.write_request(&request).unwrap();
        store.write_result(operation_id, &result).unwrap();
        let receipt = store.load(operation_id).unwrap();
        assert_eq!(receipt.state(), OperationReceiptState::ResultStored);
        assert!(receipt.commit.is_none());
        assert!(!temp.path().join("app").join("transcript").exists());
        // This store has no recovery classifier: a coordinator must re-inspect
        // the referenced artifacts and use the frozen classifier separately.
    }

    #[test]
    fn operation_directories_are_private_when_the_umask_is_open() {
        let _umask_lock = UMASK_LOCK.lock().unwrap();
        let temp = TempDir::new().unwrap();
        let repo = temp.path().join("repo");
        fs::create_dir(&repo).unwrap();
        fs::set_permissions(&repo, fs::Permissions::from_mode(0o700)).unwrap();
        let root = StorageRoot::create(&temp.path().join("app"), &repo).unwrap();
        let previous_umask = unsafe { libc::umask(0) };
        struct RestoreUmask(libc::mode_t);
        impl Drop for RestoreUmask {
            fn drop(&mut self) {
                unsafe {
                    libc::umask(self.0);
                }
            }
        }
        let _restore_umask = RestoreUmask(previous_umask);

        let store = OperationStore::open(&root).unwrap();
        let request = restoration_request(&fixtures());
        let operation_id = request.operation_id();
        store.write_request(&request).unwrap();

        let operations_dir = temp.path().join("app").join(OPERATIONS_DIRECTORY);
        assert_eq!(
            fs::metadata(&operations_dir).unwrap().permissions().mode() & 0o777,
            0o700
        );
        assert_eq!(
            fs::metadata(operations_dir.join(operation_id.to_string()))
                .unwrap()
                .permissions()
                .mode()
                & 0o777,
            0o700
        );
    }

    #[test]
    fn terminal_commit_is_written_only_after_the_frozen_receipts_reconcile() {
        let fixture = fixtures();
        let (_temp, store) = store();
        let request = restoration_request(&fixture);
        let result = restoration_result(&fixture);
        let operation_id = request.operation_id();
        let commit: MeetingOperationCommit = parse(&fixture, &["restoration", "commit"]);
        let meeting: MeetingRecord = parse(&fixture, &["committed_meetings", "restoration"]);
        let meeting_bytes = serde_json::to_vec_pretty(&meeting).unwrap();

        store.write_request(&request).unwrap();
        store.write_result(operation_id, &result).unwrap();
        store
            .write_commit(operation_id, &commit, &meeting, &meeting_bytes)
            .unwrap();
        assert_eq!(
            store.load(operation_id).unwrap().state(),
            OperationReceiptState::Committed
        );
    }

    #[test]
    fn scan_refuses_symlink_malformed_oversized_and_wrong_mode_receipts() {
        let fixture = fixtures();
        let (temp, store) = store();
        let request = restoration_request(&fixture);
        let operation_id = request.operation_id();
        let root = temp.path().join("app").join(OPERATIONS_DIRECTORY);
        let operation_dir = root.join(operation_id.to_string());
        symlink(temp.path(), &operation_dir).unwrap();
        assert!(matches!(
            store.scan(),
            Err(OperationStoreError::InvalidPrivateStorage)
        ));
        fs::remove_file(&operation_dir).unwrap();

        fs::create_dir(&operation_dir).unwrap();
        fs::set_permissions(&operation_dir, fs::Permissions::from_mode(0o700)).unwrap();
        durable_create_new(&operation_dir.join(REQUEST_FILE), b"{}").unwrap();
        assert!(matches!(
            store.scan(),
            Err(OperationStoreError::Malformed(_))
        ));
        fs::remove_file(operation_dir.join(REQUEST_FILE)).unwrap();
        durable_create_new(
            &operation_dir.join(REQUEST_FILE),
            &vec![b'x'; MAX_RECEIPT_BYTES as usize + 1],
        )
        .unwrap();
        assert!(matches!(
            store.scan(),
            Err(OperationStoreError::InvalidPrivateStorage)
        ));
        fs::remove_file(operation_dir.join(REQUEST_FILE)).unwrap();
        durable_create_new(
            &operation_dir.join(REQUEST_FILE),
            &request.canonical_bytes().unwrap(),
        )
        .unwrap();
        fs::set_permissions(
            operation_dir.join(REQUEST_FILE),
            fs::Permissions::from_mode(0o644),
        )
        .unwrap();
        assert!(matches!(
            store.scan(),
            Err(OperationStoreError::InvalidPrivateStorage)
        ));
    }
}

//! Account-private `profile-reset/1` storage authority.
//!
//! This module intentionally has no desktop command.  A future facade must hold
//! the process-lifetime app-data writer lock before it can call this destructive
//! boundary; the process-local meeting coordinator below is not that lock.

use std::collections::BTreeMap;
use std::ffi::CString;
use std::fs::{self, File, OpenOptions};
use std::io::{self, Read};
use std::os::fd::{AsRawFd, FromRawFd};
use std::os::unix::ffi::OsStrExt;
use std::os::unix::fs::{MetadataExt, OpenOptionsExt, PermissionsExt};
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use thiserror::Error;

use crate::meeting::valid_opaque_id;
use crate::meeting_coordination::{MeetingCoordinationError, MeetingStorageCoordination};
use crate::storage::{StorageRoot, create_private_dir, durable_create_new, durable_replace};

/// Kept equal to the bounded input accepted by the strict Python profile loader.
const MAX_PROFILE_BYTES: u64 = 4 * 1024 * 1024;
const MAX_RECEIPT_BYTES: u64 = 16 * 1024;
const PROFILE_RELATIVE_PATH: &str = "profile/voiceprint.json";
const RESET_OPERATIONS_RELATIVE_PATH: &str = "profile/reset-operations";
const STAGED_NAME: &str = "voiceprint.staged";
// This name is unique because it lives inside the operation-ID directory. It
// narrows the final removal race: no-replace move, identity revalidation, then
// unlink. A crash in this substep remains the existing `staged` receipt phase.
const REMOVING_NAME: &str = "voiceprint.removing";

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum InjectedFailurePhase {
    ReceiptCreated,
    RenameBeforeReceipt,
    Staged,
    UnlinkBeforeTerminal,
    Terminal,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct ProfileResetRequest<'a> {
    pub operation_id: &'a str,
    pub requested_at_epoch_seconds: u64,
    pub fail_after: Option<InjectedFailurePhase>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) enum ProfileResetOutcome {
    AlreadyAbsent,
    Removed { operation_id: String },
    RecoveredRemoval { operation_id: String },
    OperationComplete { operation_id: String },
}

#[derive(Debug, Error)]
pub(crate) enum ProfileResetError {
    #[error("meeting storage coordination is unavailable")]
    Coordination(#[from] MeetingCoordinationError),
    #[error("profile reset refuses while a meeting is active")]
    ActiveMeeting,
    #[error("profile reset operation identifier is invalid")]
    InvalidOperationId,
    #[error("another profile reset is incomplete")]
    NonterminalOperation,
    #[error("profile reset storage is ambiguous and requires repair")]
    Quarantined,
    #[error("profile reset was deliberately interrupted")]
    InjectedInterruption,
    #[error(transparent)]
    Io(#[from] io::Error),
    #[error(transparent)]
    Json(#[from] serde_json::Error),
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct ResetReceipt {
    schema: ResetSchema,
    operation_id: String,
    requested_at_epoch_seconds: u64,
    phase: ResetPhase,
    #[serde(skip_serializing_if = "Option::is_none")]
    relative_path: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    byte_size: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    sha256: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    removed_at_epoch_seconds: Option<u64>,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
enum ResetSchema {
    #[serde(rename = "profile-reset/1")]
    V1,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "kebab-case")]
enum ResetPhase {
    Deleting,
    Staged,
    Removed,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct ProfileBinding {
    byte_size: u64,
    sha256: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
struct FileIdentity {
    device: u64,
    inode: u64,
    mode: u32,
    owner: u32,
    byte_size: u64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct ProfileSnapshot {
    binding: ProfileBinding,
    identity: FileIdentity,
}

/// Start a new account-level reset or resume exactly the same incomplete one.
///
/// This is crate-private until a facade can prove it holds the lifetime writer
/// lock.  It does not parse a profile: semantic-invalid bytes are removable as
/// long as their filesystem identity is safe.
pub(crate) fn reset_profile(
    storage: &StorageRoot,
    coordination: &MeetingStorageCoordination,
    request: ProfileResetRequest<'_>,
) -> Result<ProfileResetOutcome, ProfileResetError> {
    if !valid_opaque_id(request.operation_id) {
        return Err(ProfileResetError::InvalidOperationId);
    }
    let sequence = coordination.lock_sequence()?;
    if !sequence.active_meeting_ids()?.is_empty() {
        return Err(ProfileResetError::ActiveMeeting);
    }
    reset_under_sequence(storage, request)
}

/// Reconcile a fresh-process reset before profile inspection, adoption, or Start.
/// The caller must arrange the lifetime writer lock; this helper is deliberately
/// crate-private until that facade exists.
pub(crate) fn recover_profile_resets(
    storage: &StorageRoot,
    coordination: &MeetingStorageCoordination,
    removed_at_epoch_seconds: u64,
    fail_after: Option<InjectedFailurePhase>,
) -> Result<Option<ProfileResetOutcome>, ProfileResetError> {
    let sequence = coordination.lock_sequence()?;
    if !sequence.active_meeting_ids()?.is_empty() {
        return Err(ProfileResetError::ActiveMeeting);
    }
    let journal = scan_journal(storage)?;
    let Some((operation_dir, receipt)) = journal.nonterminal else {
        return Ok(None);
    };
    let operation_id = receipt.operation_id.clone();
    finish_receipt(
        storage,
        &operation_dir,
        receipt,
        removed_at_epoch_seconds,
        fail_after,
    )?;
    Ok(Some(ProfileResetOutcome::RecoveredRemoval { operation_id }))
}

fn reset_under_sequence(
    storage: &StorageRoot,
    request: ProfileResetRequest<'_>,
) -> Result<ProfileResetOutcome, ProfileResetError> {
    let journal = scan_journal(storage)?;
    if let Some((operation_dir, receipt)) = journal.nonterminal {
        if receipt.operation_id != request.operation_id {
            return Err(ProfileResetError::NonterminalOperation);
        }
        finish_receipt(
            storage,
            &operation_dir,
            receipt,
            request.requested_at_epoch_seconds,
            request.fail_after,
        )?;
        return Ok(ProfileResetOutcome::RecoveredRemoval {
            operation_id: request.operation_id.to_owned(),
        });
    }
    if journal.terminals.contains_key(request.operation_id) {
        return Ok(ProfileResetOutcome::OperationComplete {
            operation_id: request.operation_id.to_owned(),
        });
    }

    let profile_dir = profile_dir(storage)?;
    let live = profile_dir.join("voiceprint.json");
    let binding = match inspect_private_profile(&live) {
        Ok(binding) => binding,
        Err(ProfilePresence::Absent) => return Ok(ProfileResetOutcome::AlreadyAbsent),
        Err(ProfilePresence::Unsafe) => return Err(ProfileResetError::Quarantined),
        Err(ProfilePresence::Io(error)) => return Err(error.into()),
    };
    let reset_root = reset_root(storage)?;
    create_private_dir(&reset_root)?;
    let operation_dir = reset_root.join(request.operation_id);
    if fs::symlink_metadata(&operation_dir).is_ok() {
        return Err(ProfileResetError::Quarantined);
    }
    create_private_dir(&operation_dir)?;
    let receipt_path = operation_dir.join("receipt.json");
    let receipt = ResetReceipt {
        schema: ResetSchema::V1,
        operation_id: request.operation_id.to_owned(),
        requested_at_epoch_seconds: request.requested_at_epoch_seconds,
        phase: ResetPhase::Deleting,
        relative_path: Some(PROFILE_RELATIVE_PATH.into()),
        byte_size: Some(binding.byte_size),
        sha256: Some(binding.sha256),
        removed_at_epoch_seconds: None,
    };
    durable_create_new(&receipt_path, &serde_json::to_vec_pretty(&receipt)?)
        .map_err(|_| ProfileResetError::Quarantined)?;
    maybe_interrupt(request.fail_after, InjectedFailurePhase::ReceiptCreated)?;
    finish_receipt(
        storage,
        &operation_dir,
        receipt,
        request.requested_at_epoch_seconds,
        request.fail_after,
    )?;
    Ok(ProfileResetOutcome::Removed {
        operation_id: request.operation_id.to_owned(),
    })
}

fn finish_receipt(
    storage: &StorageRoot,
    operation_dir: &Path,
    mut receipt: ResetReceipt,
    removed_at_epoch_seconds: u64,
    fail_after: Option<InjectedFailurePhase>,
) -> Result<(), ProfileResetError> {
    validate_receipt(&receipt)?;
    validate_private_directory(operation_dir)?;
    let receipt_path = operation_dir.join("receipt.json");
    let profile_dir = profile_dir(storage)?;
    let profile_fd = open_private_directory_fd(&profile_dir)?;
    let operation_fd = open_private_directory_fd(operation_dir)?;

    if receipt.phase == ResetPhase::Removed {
        if entry_exists_at(&operation_fd, STAGED_NAME)?
            || entry_exists_at(&operation_fd, REMOVING_NAME)?
        {
            return Err(ProfileResetError::Quarantined);
        }
        return Ok(());
    }

    let binding = binding_from_receipt(&receipt)?;
    match receipt.phase {
        ResetPhase::Deleting => {
            let live_state = exact_profile_at(&profile_fd, "voiceprint.json", &binding)?;
            let staged_state = exact_profile_at(&operation_fd, STAGED_NAME, &binding)?;
            if entry_exists_at(&operation_fd, REMOVING_NAME)? {
                return Err(ProfileResetError::Quarantined);
            }
            match (live_state, staged_state) {
                (ExactPathState::Exact(live), ExactPathState::Absent) => {
                    run_test_hook(
                        TestHookPoint::BeforeLiveStageMove,
                        &profile_dir,
                        operation_dir,
                    );
                    rename_no_replace(&profile_fd, "voiceprint.json", &operation_fd, STAGED_NAME)?;
                    let staged = exact_profile_at(&operation_fd, STAGED_NAME, &binding)?;
                    if staged != ExactPathState::Exact(live)
                        || entry_exists_at(&profile_fd, "voiceprint.json")?
                    {
                        return Err(ProfileResetError::Quarantined);
                    }
                    sync_directory_fd(&profile_fd)?;
                    sync_directory_fd(&operation_fd)?;
                    maybe_interrupt(fail_after, InjectedFailurePhase::RenameBeforeReceipt)?;
                }
                (ExactPathState::Absent, ExactPathState::Exact(_)) => {
                    // The rename was durable but the phase write was not.
                    sync_directory_fd(&profile_fd)?;
                    sync_directory_fd(&operation_fd)?;
                }
                _ => return Err(ProfileResetError::Quarantined),
            }
            receipt.phase = ResetPhase::Staged;
            durable_replace(&receipt_path, &serde_json::to_vec_pretty(&receipt)?)?;
            maybe_interrupt(fail_after, InjectedFailurePhase::Staged)?;
        }
        ResetPhase::Staged | ResetPhase::Removed => {}
    }

    let live_state = exact_profile_at(&profile_fd, "voiceprint.json", &binding)?;
    let staged_state = exact_profile_at(&operation_fd, STAGED_NAME, &binding)?;
    let removing_state = exact_profile_at(&operation_fd, REMOVING_NAME, &binding)?;
    match (live_state, staged_state, removing_state) {
        (ExactPathState::Absent, ExactPathState::Exact(staged), ExactPathState::Absent) => {
            run_test_hook(
                TestHookPoint::BeforeStagedRemovalMove,
                &profile_dir,
                operation_dir,
            );
            rename_no_replace(&operation_fd, STAGED_NAME, &operation_fd, REMOVING_NAME)?;
            let removing = exact_profile_at(&operation_fd, REMOVING_NAME, &binding)?;
            if removing != ExactPathState::Exact(staged.clone())
                || entry_exists_at(&operation_fd, STAGED_NAME)?
            {
                return Err(ProfileResetError::Quarantined);
            }
            sync_directory_fd(&operation_fd)?;
            unlink_checked(&operation_fd, REMOVING_NAME, &staged)?;
            sync_directory_fd(&operation_fd)?;
            maybe_interrupt(fail_after, InjectedFailurePhase::UnlinkBeforeTerminal)?;
        }
        (ExactPathState::Absent, ExactPathState::Absent, ExactPathState::Exact(removing)) => {
            // A crash happened after moving into the unique removal name. Recheck
            // that exact inode before the only unlink in this executor.
            unlink_checked(&operation_fd, REMOVING_NAME, &removing)?;
            sync_directory_fd(&operation_fd)?;
            maybe_interrupt(fail_after, InjectedFailurePhase::UnlinkBeforeTerminal)?;
        }
        (ExactPathState::Absent, ExactPathState::Absent, ExactPathState::Absent) => {
            // The unlink was durable but the terminal receipt was not.
            sync_directory_fd(&operation_fd)?;
        }
        _ => return Err(ProfileResetError::Quarantined),
    }
    receipt.phase = ResetPhase::Removed;
    receipt.relative_path = None;
    receipt.byte_size = None;
    receipt.sha256 = None;
    receipt.removed_at_epoch_seconds = Some(removed_at_epoch_seconds);
    durable_replace(&receipt_path, &serde_json::to_vec_pretty(&receipt)?)?;
    maybe_interrupt(fail_after, InjectedFailurePhase::Terminal)?;
    Ok(())
}

fn maybe_interrupt(
    configured: Option<InjectedFailurePhase>,
    point: InjectedFailurePhase,
) -> Result<(), ProfileResetError> {
    if configured == Some(point) {
        Err(ProfileResetError::InjectedInterruption)
    } else {
        Ok(())
    }
}

struct Journal {
    nonterminal: Option<(PathBuf, ResetReceipt)>,
    terminals: BTreeMap<String, ResetReceipt>,
}

fn scan_journal(storage: &StorageRoot) -> Result<Journal, ProfileResetError> {
    let reset_root = reset_root(storage)?;
    match fs::symlink_metadata(&reset_root) {
        Err(error) if error.kind() == io::ErrorKind::NotFound => {
            return Ok(Journal {
                nonterminal: None,
                terminals: BTreeMap::new(),
            });
        }
        Err(error) => return Err(error.into()),
        Ok(_) => validate_private_directory(&reset_root)?,
    }
    let mut nonterminal = None;
    let mut terminals = BTreeMap::new();
    for entry in fs::read_dir(&reset_root)? {
        let entry = entry?;
        let name = entry.file_name().to_string_lossy().into_owned();
        if !valid_opaque_id(&name) {
            return Err(ProfileResetError::Quarantined);
        }
        let operation_dir = entry.path();
        validate_private_directory(&operation_dir)?;
        let mut names = Vec::new();
        for child in fs::read_dir(&operation_dir)? {
            names.push(child?.file_name().to_string_lossy().into_owned());
        }
        if !names
            .iter()
            .all(|name| name == "receipt.json" || name == STAGED_NAME || name == REMOVING_NAME)
            || !names.iter().any(|name| name == "receipt.json")
        {
            return Err(ProfileResetError::Quarantined);
        }
        let receipt = load_receipt(&operation_dir.join("receipt.json"))?;
        if receipt.operation_id != name {
            return Err(ProfileResetError::Quarantined);
        }
        validate_receipt(&receipt)?;
        let staged_present = path_exists(&operation_dir.join(STAGED_NAME))?;
        let removing_present = path_exists(&operation_dir.join(REMOVING_NAME))?;
        if receipt.phase == ResetPhase::Removed {
            if staged_present || removing_present || terminals.insert(name, receipt).is_some() {
                return Err(ProfileResetError::Quarantined);
            }
        } else {
            if nonterminal.replace((operation_dir, receipt)).is_some() {
                return Err(ProfileResetError::Quarantined);
            }
        }
    }
    Ok(Journal {
        nonterminal,
        terminals,
    })
}

fn validate_receipt(receipt: &ResetReceipt) -> Result<(), ProfileResetError> {
    if !valid_opaque_id(&receipt.operation_id) {
        return Err(ProfileResetError::Quarantined);
    }
    match receipt.phase {
        ResetPhase::Deleting | ResetPhase::Staged => {
            if receipt.relative_path.as_deref() != Some(PROFILE_RELATIVE_PATH)
                || receipt.byte_size.is_none()
                || !receipt.sha256.as_deref().is_some_and(valid_sha256)
                || receipt.removed_at_epoch_seconds.is_some()
            {
                return Err(ProfileResetError::Quarantined);
            }
        }
        ResetPhase::Removed => {
            if receipt.relative_path.is_some()
                || receipt.byte_size.is_some()
                || receipt.sha256.is_some()
                || receipt.removed_at_epoch_seconds.is_none()
            {
                return Err(ProfileResetError::Quarantined);
            }
        }
    }
    Ok(())
}

fn binding_from_receipt(receipt: &ResetReceipt) -> Result<ProfileBinding, ProfileResetError> {
    if receipt.relative_path.as_deref() != Some(PROFILE_RELATIVE_PATH) {
        return Err(ProfileResetError::Quarantined);
    }
    Ok(ProfileBinding {
        byte_size: receipt.byte_size.ok_or(ProfileResetError::Quarantined)?,
        sha256: receipt
            .sha256
            .clone()
            .ok_or(ProfileResetError::Quarantined)?,
    })
}

fn profile_dir(storage: &StorageRoot) -> Result<PathBuf, ProfileResetError> {
    let path = storage
        .resolve(Path::new("profile"))
        .map_err(|_| ProfileResetError::Quarantined)?;
    validate_private_directory(&path)?;
    Ok(path)
}

fn reset_root(storage: &StorageRoot) -> Result<PathBuf, ProfileResetError> {
    storage
        .resolve(Path::new(RESET_OPERATIONS_RELATIVE_PATH))
        .map_err(|_| ProfileResetError::Quarantined)
}

fn load_receipt(path: &Path) -> Result<ResetReceipt, ProfileResetError> {
    let bytes =
        read_private_file(path, MAX_RECEIPT_BYTES).map_err(|_| ProfileResetError::Quarantined)?;
    let value: serde_json::Value =
        serde_json::from_slice(&bytes).map_err(|_| ProfileResetError::Quarantined)?;
    validate_receipt_key_set(&value)?;
    serde_json::from_value(value).map_err(|_| ProfileResetError::Quarantined)
}

/// `Option<T>` cannot distinguish a missing property from an explicit JSON
/// `null`. The journal is phase-closed, so validate the exact key set before
/// deserializing its typed values.
fn validate_receipt_key_set(value: &serde_json::Value) -> Result<(), ProfileResetError> {
    let object = value.as_object().ok_or(ProfileResetError::Quarantined)?;
    let phase = object
        .get("phase")
        .and_then(serde_json::Value::as_str)
        .ok_or(ProfileResetError::Quarantined)?;
    let expected: &[&str] = match phase {
        "deleting" | "staged" => &[
            "schema",
            "operation_id",
            "requested_at_epoch_seconds",
            "phase",
            "relative_path",
            "byte_size",
            "sha256",
        ],
        "removed" => &[
            "schema",
            "operation_id",
            "requested_at_epoch_seconds",
            "phase",
            "removed_at_epoch_seconds",
        ],
        _ => return Err(ProfileResetError::Quarantined),
    };
    if object.len() != expected.len() || expected.iter().any(|key| !object.contains_key(*key)) {
        return Err(ProfileResetError::Quarantined);
    }
    Ok(())
}

enum ProfilePresence {
    Absent,
    Unsafe,
    Io(io::Error),
}

fn inspect_private_profile(path: &Path) -> Result<ProfileBinding, ProfilePresence> {
    match exact_profile(path, None) {
        Ok(Some(binding)) => Ok(binding),
        Ok(None) => Err(ProfilePresence::Absent),
        Err(ProfileResetError::Io(error)) => Err(ProfilePresence::Io(error)),
        Err(_) => Err(ProfilePresence::Unsafe),
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
enum ExactPathState {
    Absent,
    Exact(ProfileSnapshot),
    Other,
}

fn exact_profile_at(
    parent: &File,
    name: &str,
    expected: &ProfileBinding,
) -> Result<ExactPathState, ProfileResetError> {
    let name = c_name(name)?;
    let descriptor = unsafe {
        libc::openat(
            parent.as_raw_fd(),
            name.as_ptr(),
            libc::O_RDONLY | libc::O_NOFOLLOW,
        )
    };
    if descriptor < 0 {
        return match io::Error::last_os_error().kind() {
            io::ErrorKind::NotFound => Ok(ExactPathState::Absent),
            _ => Ok(ExactPathState::Other),
        };
    }
    let mut file = unsafe { File::from_raw_fd(descriptor) };
    let snapshot = match read_profile_snapshot(&mut file, Some(expected)) {
        Ok(snapshot) => snapshot,
        Err(_) => return Ok(ExactPathState::Other),
    };
    // The fd pins the bytes while they are read. Reopen the directory-relative
    // entry no-follow and compare inode identity before an operation names it.
    let current = unsafe {
        libc::openat(
            parent.as_raw_fd(),
            name.as_ptr(),
            libc::O_RDONLY | libc::O_NOFOLLOW,
        )
    };
    if current < 0 {
        return Ok(ExactPathState::Other);
    }
    let current = unsafe { File::from_raw_fd(current) };
    let current_metadata = current.metadata()?;
    if !private_file_metadata(&current_metadata) || identity(&current_metadata) != snapshot.identity
    {
        return Ok(ExactPathState::Other);
    }
    Ok(ExactPathState::Exact(snapshot))
}

fn open_private_directory_fd(path: &Path) -> Result<File, ProfileResetError> {
    let path =
        CString::new(path.as_os_str().as_bytes()).map_err(|_| ProfileResetError::Quarantined)?;
    let descriptor = unsafe {
        libc::open(
            path.as_ptr(),
            libc::O_RDONLY | libc::O_DIRECTORY | libc::O_NOFOLLOW,
        )
    };
    if descriptor < 0 {
        return Err(ProfileResetError::Quarantined);
    }
    let file = unsafe { File::from_raw_fd(descriptor) };
    let metadata = file.metadata()?;
    if !private_directory_metadata(&metadata) {
        return Err(ProfileResetError::Quarantined);
    }
    Ok(file)
}

fn read_profile_snapshot(
    file: &mut File,
    expected: Option<&ProfileBinding>,
) -> Result<ProfileSnapshot, ProfileResetError> {
    let before = file.metadata()?;
    if !private_file_metadata(&before) || before.len() > MAX_PROFILE_BYTES {
        return Err(ProfileResetError::Quarantined);
    }
    let mut hasher = Sha256::new();
    let mut remaining = before.len();
    let mut buffer = [0_u8; 64 * 1024];
    while remaining > 0 {
        let read = file.read(&mut buffer)?;
        if read == 0 || read as u64 > remaining {
            return Err(ProfileResetError::Quarantined);
        }
        hasher.update(&buffer[..read]);
        remaining -= read as u64;
    }
    let after = file.metadata()?;
    if identity(&before) != identity(&after) || !private_file_metadata(&after) {
        return Err(ProfileResetError::Quarantined);
    }
    let binding = ProfileBinding {
        byte_size: before.len(),
        sha256: format!("{:x}", hasher.finalize()),
    };
    if expected.is_some_and(|expected| expected != &binding) {
        return Err(ProfileResetError::Quarantined);
    }
    Ok(ProfileSnapshot {
        binding,
        identity: identity(&before),
    })
}

fn identity(metadata: &fs::Metadata) -> FileIdentity {
    FileIdentity {
        device: metadata.dev(),
        inode: metadata.ino(),
        mode: metadata.mode(),
        owner: metadata.uid(),
        byte_size: metadata.len(),
    }
}

fn entry_exists_at(parent: &File, name: &str) -> Result<bool, ProfileResetError> {
    let name = c_name(name)?;
    let result = unsafe {
        libc::faccessat(
            parent.as_raw_fd(),
            name.as_ptr(),
            libc::F_OK,
            libc::AT_SYMLINK_NOFOLLOW,
        )
    };
    if result == 0 {
        Ok(true)
    } else if io::Error::last_os_error().kind() == io::ErrorKind::NotFound {
        Ok(false)
    } else {
        Err(ProfileResetError::Quarantined)
    }
}

fn sync_directory_fd(directory: &File) -> Result<(), ProfileResetError> {
    directory.sync_all().map_err(Into::into)
}

fn c_name(name: &str) -> Result<CString, ProfileResetError> {
    if name.is_empty() || name.contains('/') {
        return Err(ProfileResetError::Quarantined);
    }
    CString::new(name).map_err(|_| ProfileResetError::Quarantined)
}

fn rename_no_replace(
    from_directory: &File,
    from_name: &str,
    to_directory: &File,
    to_name: &str,
) -> Result<(), ProfileResetError> {
    let from_name = c_name(from_name)?;
    let to_name = c_name(to_name)?;
    rename_no_replace_platform(
        from_directory.as_raw_fd(),
        &from_name,
        to_directory.as_raw_fd(),
        &to_name,
    )
    .map_err(|_| ProfileResetError::Quarantined)
}

#[cfg(target_os = "macos")]
fn rename_no_replace_platform(
    from_directory: libc::c_int,
    from_name: &CString,
    to_directory: libc::c_int,
    to_name: &CString,
) -> io::Result<()> {
    unsafe extern "C" {
        fn renameatx_np(
            fromfd: libc::c_int,
            from: *const libc::c_char,
            tofd: libc::c_int,
            to: *const libc::c_char,
            flags: libc::c_uint,
        ) -> libc::c_int;
    }
    // RENAME_EXCL prevents replacement; RENAME_NOFOLLOW_ANY rejects a leaf or
    // intermediate symlink even if a hostile same-UID writer races this process.
    const RENAME_EXCL: libc::c_uint = 0x0000_0004;
    const RENAME_NOFOLLOW_ANY: libc::c_uint = 0x0000_0010;
    let result = unsafe {
        renameatx_np(
            from_directory,
            from_name.as_ptr(),
            to_directory,
            to_name.as_ptr(),
            RENAME_EXCL | RENAME_NOFOLLOW_ANY,
        )
    };
    if result == 0 {
        Ok(())
    } else {
        Err(io::Error::last_os_error())
    }
}

#[cfg(not(target_os = "macos"))]
fn rename_no_replace_platform(
    _from_directory: libc::c_int,
    _from_name: &CString,
    _to_directory: libc::c_int,
    _to_name: &CString,
) -> io::Result<()> {
    Err(io::Error::new(
        io::ErrorKind::Unsupported,
        "profile reset requires macOS renameatx_np RENAME_EXCL",
    ))
}

fn unlink_checked(
    directory: &File,
    name: &str,
    expected: &ProfileSnapshot,
) -> Result<(), ProfileResetError> {
    if exact_profile_at(directory, name, &expected.binding)?
        != ExactPathState::Exact(expected.clone())
    {
        return Err(ProfileResetError::Quarantined);
    }
    let name = c_name(name)?;
    if unsafe { libc::unlinkat(directory.as_raw_fd(), name.as_ptr(), 0) } != 0 {
        return Err(ProfileResetError::Quarantined);
    }
    Ok(())
}

/// Open no-follow, bound the complete bytes, and ensure the descriptor did not
/// change while hashing.  It deliberately performs no profile-schema parsing.
fn exact_profile(
    path: &Path,
    expected: Option<&ProfileBinding>,
) -> Result<Option<ProfileBinding>, ProfileResetError> {
    let metadata = match fs::symlink_metadata(path) {
        Ok(metadata) => metadata,
        Err(error) if error.kind() == io::ErrorKind::NotFound => return Ok(None),
        Err(error) => return Err(error.into()),
    };
    if !metadata.file_type().is_file()
        || metadata.file_type().is_symlink()
        || metadata.permissions().mode() & 0o777 != 0o600
        || metadata.uid() != unsafe { libc::geteuid() }
        || metadata.len() > MAX_PROFILE_BYTES
    {
        return Err(ProfileResetError::Quarantined);
    }
    let mut file = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW)
        .open(path)
        .map_err(|_| ProfileResetError::Quarantined)?;
    let before = file.metadata()?;
    if !private_file_metadata(&before) || before.len() > MAX_PROFILE_BYTES {
        return Err(ProfileResetError::Quarantined);
    }
    if before.dev() != metadata.dev()
        || before.ino() != metadata.ino()
        || before.len() != metadata.len()
    {
        return Err(ProfileResetError::Quarantined);
    }
    let mut hasher = Sha256::new();
    let mut remaining = before.len();
    let mut buffer = [0_u8; 64 * 1024];
    while remaining > 0 {
        let read = file.read(&mut buffer)?;
        if read == 0 || read as u64 > remaining {
            return Err(ProfileResetError::Quarantined);
        }
        hasher.update(&buffer[..read]);
        remaining -= read as u64;
    }
    let after = file.metadata()?;
    if before.dev() != after.dev()
        || before.ino() != after.ino()
        || before.mode() != after.mode()
        || before.uid() != after.uid()
        || before.len() != after.len()
        || !private_file_metadata(&after)
    {
        return Err(ProfileResetError::Quarantined);
    }
    let binding = ProfileBinding {
        byte_size: before.len(),
        sha256: format!("{:x}", hasher.finalize()),
    };
    if expected.is_some_and(|expected| expected != &binding) {
        return Err(ProfileResetError::Quarantined);
    }
    Ok(Some(binding))
}

fn read_private_file(path: &Path, maximum: u64) -> io::Result<Vec<u8>> {
    let mut file = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW)
        .open(path)?;
    let before = file.metadata()?;
    if !private_file_metadata(&before) || before.len() > maximum {
        return Err(io::Error::other("private file is unsafe"));
    }
    let mut bytes = Vec::with_capacity(before.len() as usize);
    file.read_to_end(&mut bytes)?;
    let after = file.metadata()?;
    if before.dev() != after.dev()
        || before.ino() != after.ino()
        || before.len() != after.len()
        || !private_file_metadata(&after)
    {
        return Err(io::Error::other("private file changed"));
    }
    Ok(bytes)
}

fn private_file_metadata(metadata: &fs::Metadata) -> bool {
    private_file_metadata_for_owner(metadata, unsafe { libc::geteuid() })
}

fn private_file_metadata_for_owner(metadata: &fs::Metadata, owner: u32) -> bool {
    metadata.file_type().is_file()
        && !metadata.file_type().is_symlink()
        && metadata.permissions().mode() & 0o777 == 0o600
        && metadata.uid() == owner
}

fn validate_private_directory(path: &Path) -> Result<(), ProfileResetError> {
    let metadata = fs::symlink_metadata(path).map_err(|_| ProfileResetError::Quarantined)?;
    if !private_directory_metadata(&metadata) {
        return Err(ProfileResetError::Quarantined);
    }
    Ok(())
}

fn private_directory_metadata(metadata: &fs::Metadata) -> bool {
    metadata.file_type().is_dir()
        && !metadata.file_type().is_symlink()
        && metadata.permissions().mode() & 0o777 == 0o700
        && metadata.uid() == unsafe { libc::geteuid() }
}

fn path_exists(path: &Path) -> Result<bool, ProfileResetError> {
    match fs::symlink_metadata(path) {
        Ok(_) => Ok(true),
        Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(false),
        Err(error) => Err(error.into()),
    }
}

fn valid_sha256(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum TestHookPoint {
    BeforeLiveStageMove,
    BeforeStagedRemovalMove,
}

#[cfg(test)]
thread_local! {
    static TEST_HOOK: std::cell::RefCell<Option<Box<dyn FnMut(TestHookPoint, &Path, &Path)>>> =
        std::cell::RefCell::new(None);
}

#[cfg(not(test))]
fn run_test_hook(_point: TestHookPoint, _profile_dir: &Path, _operation_dir: &Path) {}

#[cfg(test)]
fn run_test_hook(point: TestHookPoint, profile_dir: &Path, operation_dir: &Path) {
    TEST_HOOK.with(|hook| {
        if let Some(hook) = hook.borrow_mut().as_mut() {
            hook(point, profile_dir, operation_dir);
        }
    });
}

#[cfg(test)]
fn install_test_hook(hook: impl FnMut(TestHookPoint, &Path, &Path) + 'static) {
    TEST_HOOK.with(|slot| *slot.borrow_mut() = Some(Box::new(hook)));
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::storage::{StorageRoot, create_private_dir, durable_create_new};
    use tempfile::TempDir;

    fn fixture() -> (TempDir, StorageRoot, MeetingStorageCoordination) {
        let temp = TempDir::new().unwrap();
        let repo = temp.path().join("repo");
        create_private_dir(&repo).unwrap();
        let storage = StorageRoot::create(&temp.path().join("app"), &repo).unwrap();
        (temp, storage, MeetingStorageCoordination::default())
    }

    fn install(storage: &StorageRoot, bytes: &[u8]) -> PathBuf {
        let path = storage.path().join(PROFILE_RELATIVE_PATH);
        durable_create_new(&path, bytes).unwrap();
        path
    }

    fn request<'a>(
        id: &'a str,
        fail_after: Option<InjectedFailurePhase>,
    ) -> ProfileResetRequest<'a> {
        ProfileResetRequest {
            operation_id: id,
            requested_at_epoch_seconds: 123,
            fail_after,
        }
    }

    fn receipt(storage: &StorageRoot, id: &str) -> serde_json::Value {
        serde_json::from_slice(
            &fs::read(
                storage
                    .path()
                    .join(format!("profile/reset-operations/{id}/receipt.json")),
            )
            .unwrap(),
        )
        .unwrap()
    }

    #[test]
    fn resets_only_the_profile_and_writes_content_free_terminal_receipt() {
        let (_temp, storage, coordination) = fixture();
        install(&storage, b"semantic-invalid-but-safe");
        let meeting = storage.path().join("meetings/untouched/meeting.json");
        durable_create_new(&meeting, b"meeting").unwrap();
        assert_eq!(
            reset_profile(&storage, &coordination, request("reset-a", None)).unwrap(),
            ProfileResetOutcome::Removed {
                operation_id: "reset-a".into()
            }
        );
        assert!(!storage.path().join(PROFILE_RELATIVE_PATH).exists());
        assert_eq!(fs::read(meeting).unwrap(), b"meeting");
        let receipt = receipt(&storage, "reset-a");
        assert_eq!(receipt["schema"], "profile-reset/1");
        assert_eq!(receipt["phase"], "removed");
        assert!(receipt.get("relative_path").is_none());
        assert!(receipt.get("byte_size").is_none());
        assert!(receipt.get("sha256").is_none());
    }

    #[test]
    fn already_absent_creates_no_receipt_and_terminal_is_inert_to_reenrollment() {
        let (_temp, storage, coordination) = fixture();
        assert_eq!(
            reset_profile(&storage, &coordination, request("empty", None)).unwrap(),
            ProfileResetOutcome::AlreadyAbsent
        );
        assert!(!storage.path().join(RESET_OPERATIONS_RELATIVE_PATH).exists());
        install(&storage, b"first");
        reset_profile(&storage, &coordination, request("old", None)).unwrap();
        install(&storage, b"later-different-profile");
        assert_eq!(
            reset_profile(&storage, &coordination, request("old", None)).unwrap(),
            ProfileResetOutcome::OperationComplete {
                operation_id: "old".into()
            }
        );
        assert_eq!(
            fs::read(storage.path().join(PROFILE_RELATIVE_PATH)).unwrap(),
            b"later-different-profile"
        );
        reset_profile(&storage, &coordination, request("new", None)).unwrap();
        assert!(!storage.path().join(PROFILE_RELATIVE_PATH).exists());
    }

    #[test]
    fn recovery_matrix_handles_every_durable_crash_boundary() {
        for phase in [
            InjectedFailurePhase::ReceiptCreated,
            InjectedFailurePhase::RenameBeforeReceipt,
            InjectedFailurePhase::Staged,
            InjectedFailurePhase::UnlinkBeforeTerminal,
        ] {
            let (_temp, storage, coordination) = fixture();
            install(&storage, b"profile");
            assert!(matches!(
                reset_profile(&storage, &coordination, request("resume", Some(phase))),
                Err(ProfileResetError::InjectedInterruption)
            ));
            assert_eq!(
                recover_profile_resets(&storage, &coordination, 456, None).unwrap(),
                Some(ProfileResetOutcome::RecoveredRemoval {
                    operation_id: "resume".into()
                })
            );
            assert!(!storage.path().join(PROFILE_RELATIVE_PATH).exists());
            assert_eq!(receipt(&storage, "resume")["phase"], "removed");
        }
    }

    #[test]
    fn terminal_interruption_is_already_complete() {
        let (_temp, storage, coordination) = fixture();
        install(&storage, b"profile");
        assert!(matches!(
            reset_profile(
                &storage,
                &coordination,
                request("done", Some(InjectedFailurePhase::Terminal))
            ),
            Err(ProfileResetError::InjectedInterruption)
        ));
        assert_eq!(
            recover_profile_resets(&storage, &coordination, 456, None).unwrap(),
            None
        );
        assert_eq!(
            reset_profile(&storage, &coordination, request("done", None)).unwrap(),
            ProfileResetOutcome::OperationComplete {
                operation_id: "done".into()
            }
        );
    }

    #[test]
    fn unsafe_profile_shapes_and_ambiguous_journals_are_refused_without_mutation() {
        for make_unsafe in [
            |path: &Path| {
                fs::set_permissions(path, fs::Permissions::from_mode(0o644)).unwrap();
            },
            |path: &Path| {
                durable_replace(path, &vec![b'x'; MAX_PROFILE_BYTES as usize + 1]).unwrap();
            },
        ] {
            let (_temp, storage, coordination) = fixture();
            let profile = install(&storage, b"profile");
            make_unsafe(&profile);
            let before = fs::read(&profile).unwrap();
            assert!(matches!(
                reset_profile(&storage, &coordination, request("unsafe", None)),
                Err(ProfileResetError::Quarantined)
            ));
            assert_eq!(fs::read(&profile).unwrap(), before);
        }
        let (_temp, storage, coordination) = fixture();
        install(&storage, b"profile");
        let root = storage.path().join(RESET_OPERATIONS_RELATIVE_PATH);
        create_private_dir(&root.join("orphan")).unwrap();
        assert!(matches!(
            reset_profile(&storage, &coordination, request("unsafe", None)),
            Err(ProfileResetError::Quarantined)
        ));
        assert!(storage.path().join(PROFILE_RELATIVE_PATH).exists());
    }

    #[test]
    fn symlink_and_changed_target_are_quarantined_without_following_or_deleting() {
        use std::os::unix::fs::symlink;

        let (_temp, storage, coordination) = fixture();
        let outside = storage.path().join("outside-profile");
        durable_create_new(&outside, b"outside").unwrap();
        fs::remove_dir_all(storage.path().join("profile")).unwrap();
        symlink(&outside, storage.path().join("profile")).unwrap();
        assert!(matches!(
            reset_profile(&storage, &coordination, request("link", None)),
            Err(ProfileResetError::Quarantined)
        ));
        assert_eq!(fs::read(&outside).unwrap(), b"outside");

        let (_temp, storage, coordination) = fixture();
        let live = install(&storage, b"original");
        assert!(matches!(
            reset_profile(
                &storage,
                &coordination,
                request("changed", Some(InjectedFailurePhase::ReceiptCreated))
            ),
            Err(ProfileResetError::InjectedInterruption)
        ));
        durable_replace(&live, b"replacement").unwrap();
        assert!(matches!(
            reset_profile(&storage, &coordination, request("changed", None)),
            Err(ProfileResetError::Quarantined)
        ));
        assert_eq!(fs::read(live).unwrap(), b"replacement");
    }

    #[test]
    fn multiple_nonterminal_resets_and_receipt_collision_fail_closed() {
        let (_temp, storage, coordination) = fixture();
        install(&storage, b"profile");
        assert!(matches!(
            reset_profile(
                &storage,
                &coordination,
                request("one", Some(InjectedFailurePhase::ReceiptCreated))
            ),
            Err(ProfileResetError::InjectedInterruption)
        ));
        assert!(matches!(
            reset_profile(&storage, &coordination, request("two", None)),
            Err(ProfileResetError::NonterminalOperation)
        ));
        let root = storage.path().join(RESET_OPERATIONS_RELATIVE_PATH);
        create_private_dir(&root.join("two")).unwrap();
        let two = ResetReceipt {
            schema: ResetSchema::V1,
            operation_id: "two".into(),
            requested_at_epoch_seconds: 1,
            phase: ResetPhase::Deleting,
            relative_path: Some(PROFILE_RELATIVE_PATH.into()),
            byte_size: Some(7),
            sha256: Some(format!("{:064x}", 1)),
            removed_at_epoch_seconds: None,
        };
        durable_create_new(
            &root.join("two/receipt.json"),
            &serde_json::to_vec(&two).unwrap(),
        )
        .unwrap();
        assert!(matches!(
            recover_profile_resets(&storage, &coordination, 2, None),
            Err(ProfileResetError::Quarantined)
        ));
    }

    #[test]
    fn completed_receipts_are_preserved_and_new_operation_ids_never_overwrite_them() {
        let (_temp, storage, coordination) = fixture();
        install(&storage, b"first");
        reset_profile(&storage, &coordination, request("completed", None)).unwrap();
        let old_receipt = fs::read(
            storage
                .path()
                .join("profile/reset-operations/completed/receipt.json"),
        )
        .unwrap();
        install(&storage, b"second");
        reset_profile(&storage, &coordination, request("next", None)).unwrap();
        assert_eq!(
            fs::read(
                storage
                    .path()
                    .join("profile/reset-operations/completed/receipt.json"),
            )
            .unwrap(),
            old_receipt
        );
        assert_eq!(receipt(&storage, "next")["phase"], "removed");
    }

    #[test]
    fn active_meeting_refuses_without_creating_a_journal() {
        let (_temp, storage, coordination) = fixture();
        install(&storage, b"profile");
        let _lease = coordination.acquire("active").unwrap();
        assert!(matches!(
            reset_profile(&storage, &coordination, request("blocked", None)),
            Err(ProfileResetError::ActiveMeeting)
        ));
        assert!(!storage.path().join(RESET_OPERATIONS_RELATIVE_PATH).exists());
    }

    #[test]
    fn exact_private_modes_hold_under_a_permissive_umask() {
        let (_temp, storage, coordination) = fixture();
        let old = unsafe { libc::umask(0) };
        install(&storage, b"profile");
        reset_profile(&storage, &coordination, request("modes", None)).unwrap();
        unsafe { libc::umask(old) };
        let operation = storage.path().join("profile/reset-operations/modes");
        assert_eq!(
            fs::metadata(&operation).unwrap().permissions().mode() & 0o777,
            0o700
        );
        assert_eq!(
            fs::metadata(operation.join("receipt.json"))
                .unwrap()
                .permissions()
                .mode()
                & 0o777,
            0o600
        );
    }

    #[test]
    fn foreign_owner_metadata_is_not_accepted_as_a_resettable_private_file() {
        let (_temp, storage, _coordination) = fixture();
        let profile = install(&storage, b"profile");
        let metadata = fs::metadata(profile).unwrap();
        assert!(!private_file_metadata_for_owner(
            &metadata,
            unsafe { libc::geteuid() }.wrapping_add(1)
        ));
    }
}

//! Fixed-slot, account-private profile lifecycle authority.
//!
//! There is intentionally no command registration in this module.  Its caller
//! must hold the process writer lock; this crate-private boundary additionally
//! takes the storage sequence lock before it examines or changes profile data.

use std::fs::{self, File, OpenOptions};
use std::io::{self, Read, Seek, SeekFrom, Write};
use std::os::unix::fs::{DirBuilderExt, MetadataExt, OpenOptionsExt};
use std::path::Path;

#[cfg(target_os = "macos")]
use std::os::darwin::fs::MetadataExt as _;

use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use sha2::{Digest, Sha256};
use thiserror::Error;
use uuid::Uuid;

use crate::meeting_coordination::{MeetingCoordinationError, MeetingStorageCoordination};
use crate::storage::StorageRoot;

const MAX_PROFILE_BYTES: u64 = 4 * 1024 * 1024;
const MAX_RECEIPT_BYTES: u64 = 16 * 1024;
const EMPTY_SHA256: &str = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855";
const RECEIPT_A: &str = "receipt.a.json";
const RECEIPT_B: &str = "receipt.b.json";

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct ProfileResetRequest<'a> {
    pub operation_id: &'a str,
    pub requested_at_epoch_seconds: u64,
    pub completed_at_epoch_seconds: u64,
    pub fail_after: Option<InjectedFailurePhase>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum InjectedFailurePhase {
    Deleting,
    Swap,
    Staged,
    Truncate,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) enum ProfileResetOutcome {
    AlreadyAbsent,
    Removed { operation_id: String },
    RecoveredRemoval { operation_id: String },
    OperationComplete { operation_id: String },
}

#[derive(Debug, Error)]
pub(crate) enum ProfileLifecycleError {
    #[error("meeting storage coordination is unavailable")]
    Coordination(#[from] MeetingCoordinationError),
    #[error("profile lifecycle refuses while a meeting is active")]
    ActiveMeeting,
    #[error("profile lifecycle operation identifier is not a canonical lowercase UUID")]
    InvalidOperationId,
    #[error("another profile reset is incomplete")]
    NonterminalReset,
    #[error("guided enrollment is nonterminal and requires explicit enrollment recovery")]
    NonterminalEnrollment,
    #[error("profile lifecycle storage is unsafe or ambiguous and requires repair")]
    Quarantined,
    #[error("profile lifecycle requires macOS 14.4 or later on APFS with RENAME_SWAP")]
    SwapUnsupported,
    #[error("profile reset was deliberately interrupted")]
    InjectedInterruption,
    #[error(transparent)]
    Io(#[from] io::Error),
    #[error(transparent)]
    Json(#[from] serde_json::Error),
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Identity {
    device: u64,
    inode: u64,
    generation: u64,
    birth_seconds: i64,
    birth_nanoseconds: i64,
    owner: u32,
    mode: u32,
    link_count: u64,
    flags: u32,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Slot {
    identity: Identity,
    size: u64,
    sha256: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct LastReset {
    operation_id: String,
    completed_at: u64,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct PredecessorReset {
    completed_reset_count: u64,
    #[serde(skip_serializing_if = "Option::is_none")]
    last_reset: Option<LastReset>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
enum Payload {
    Baseline {
        sequence: u64,
        live: Slot,
        reset: Slot,
        enrollment: Slot,
    },
    ResetDeleting {
        sequence: u64,
        predecessor: String,
        operation_id: String,
        requested_at: u64,
        prior_count: u64,
        prior_last: Option<LastReset>,
        profile: Slot,
        reset_zero: Slot,
        enrollment_zero: Slot,
    },
    ResetStaged {
        sequence: u64,
        predecessor: String,
        operation_id: String,
        requested_at: u64,
        prior_count: u64,
        prior_last: Option<LastReset>,
        profile: Slot,
        reset_zero: Slot,
        enrollment_zero: Slot,
    },
    ResetRemoved {
        sequence: u64,
        predecessor: String,
        completed_count: u64,
        last_reset: LastReset,
        live_zero: Slot,
        reset_zero: Slot,
        enrollment_zero: Slot,
    },
    EnrollmentWriting {
        sequence: u64,
        predecessor: String,
        operation_id: String,
        requested_at: u64,
        prior_count: u64,
        prior_last: Option<LastReset>,
        live_zero: Slot,
        reset_zero: Slot,
        enrollment_zero: Slot,
    },
    EnrollmentReady {
        sequence: u64,
        predecessor: String,
        operation_id: String,
        requested_at: u64,
        prior_count: u64,
        prior_last: Option<LastReset>,
        live_zero: Slot,
        reset_zero: Slot,
        staged_profile: Slot,
    },
    EnrollmentActive {
        sequence: u64,
        predecessor: String,
        operation_id: String,
        requested_at: u64,
        completed_at: u64,
        prior_count: u64,
        prior_last: Option<LastReset>,
        live_profile: Slot,
        reset_zero: Slot,
        enrollment_zero: Slot,
    },
}

impl Payload {
    fn sequence(&self) -> u64 {
        match self {
            Self::Baseline { sequence, .. }
            | Self::ResetDeleting { sequence, .. }
            | Self::ResetStaged { sequence, .. }
            | Self::ResetRemoved { sequence, .. }
            | Self::EnrollmentWriting { sequence, .. }
            | Self::EnrollmentReady { sequence, .. }
            | Self::EnrollmentActive { sequence, .. } => *sequence,
        }
    }
    fn reset_count_and_last(&self) -> (u64, Option<LastReset>) {
        match self {
            Self::Baseline { .. } => (0, None),
            Self::ResetDeleting {
                prior_count,
                prior_last,
                ..
            }
            | Self::ResetStaged {
                prior_count,
                prior_last,
                ..
            }
            | Self::EnrollmentWriting {
                prior_count,
                prior_last,
                ..
            }
            | Self::EnrollmentReady {
                prior_count,
                prior_last,
                ..
            }
            | Self::EnrollmentActive {
                prior_count,
                prior_last,
                ..
            } => (*prior_count, prior_last.clone()),
            Self::ResetRemoved {
                completed_count,
                last_reset,
                ..
            } => (*completed_count, Some(last_reset.clone())),
        }
    }
    fn to_value(&self) -> Value {
        let mut m = Map::new();
        m.insert("schema".into(), Value::String("profile-lifecycle/1".into()));
        m.insert("receipt_sequence".into(), Value::from(self.sequence()));
        let (operation, phase) = match self {
            Self::Baseline { .. } => ("baseline", "ready"),
            Self::ResetDeleting { .. } => ("reset", "deleting"),
            Self::ResetStaged { .. } => ("reset", "staged"),
            Self::ResetRemoved { .. } => ("reset", "removed"),
            Self::EnrollmentWriting { .. } => ("enrollment", "writing"),
            Self::EnrollmentReady { .. } => ("enrollment", "ready"),
            Self::EnrollmentActive { .. } => ("enrollment", "active"),
        };
        m.insert("operation".into(), Value::String(operation.into()));
        m.insert("phase".into(), Value::String(phase.into()));
        match self {
            Self::Baseline {
                live,
                reset,
                enrollment,
                ..
            } => {
                put(&mut m, "completed_reset_count", &0u64);
                put(&mut m, "live", live);
                put(&mut m, "reset_slot", reset);
                put(&mut m, "enrollment_slot", enrollment);
            }
            Self::ResetDeleting {
                predecessor,
                operation_id,
                requested_at,
                prior_count,
                prior_last,
                profile,
                reset_zero,
                enrollment_zero,
                ..
            }
            | Self::ResetStaged {
                predecessor,
                operation_id,
                requested_at,
                prior_count,
                prior_last,
                profile,
                reset_zero,
                enrollment_zero,
                ..
            } => {
                common(&mut m, predecessor);
                reset_detail(
                    &mut m,
                    operation_id,
                    *requested_at,
                    *prior_count,
                    prior_last,
                    profile,
                    reset_zero,
                    enrollment_zero,
                );
            }
            Self::ResetRemoved {
                predecessor,
                completed_count,
                last_reset,
                live_zero,
                reset_zero,
                enrollment_zero,
                ..
            } => {
                common(&mut m, predecessor);
                put(&mut m, "completed_reset_count", completed_count);
                put(&mut m, "last_reset", last_reset);
                put(&mut m, "live_zero", live_zero);
                put(&mut m, "reset_zero", reset_zero);
                put(&mut m, "enrollment_zero", enrollment_zero);
            }
            Self::EnrollmentWriting {
                predecessor,
                operation_id,
                requested_at,
                prior_count,
                prior_last,
                live_zero,
                reset_zero,
                enrollment_zero,
                ..
            } => {
                common(&mut m, predecessor);
                enrollment_detail(
                    &mut m,
                    operation_id,
                    *requested_at,
                    *prior_count,
                    prior_last,
                    live_zero,
                    reset_zero,
                );
                put(&mut m, "enrollment_zero", enrollment_zero);
            }
            Self::EnrollmentReady {
                predecessor,
                operation_id,
                requested_at,
                prior_count,
                prior_last,
                live_zero,
                reset_zero,
                staged_profile,
                ..
            } => {
                common(&mut m, predecessor);
                enrollment_detail(
                    &mut m,
                    operation_id,
                    *requested_at,
                    *prior_count,
                    prior_last,
                    live_zero,
                    reset_zero,
                );
                put(&mut m, "staged_profile", staged_profile);
            }
            Self::EnrollmentActive {
                predecessor,
                operation_id,
                requested_at,
                completed_at,
                prior_count,
                prior_last,
                live_profile,
                reset_zero,
                enrollment_zero,
                ..
            } => {
                common(&mut m, predecessor);
                put(&mut m, "operation_id", operation_id);
                put(&mut m, "requested_at", requested_at);
                put(&mut m, "completed_at", completed_at);
                put(
                    &mut m,
                    "predecessor_reset",
                    &PredecessorReset {
                        completed_reset_count: *prior_count,
                        last_reset: prior_last.clone(),
                    },
                );
                put(&mut m, "live_profile", live_profile);
                put(&mut m, "reset_zero", reset_zero);
                put(&mut m, "enrollment_zero", enrollment_zero);
            }
        }
        Value::Object(m)
    }
}

fn put<T: Serialize>(m: &mut Map<String, Value>, key: &str, value: &T) {
    m.insert(
        key.into(),
        serde_json::to_value(value).expect("profile lifecycle values serialize"),
    );
}
fn common(m: &mut Map<String, Value>, predecessor: &str) {
    m.insert(
        "predecessor_payload_sha256".into(),
        Value::String(predecessor.into()),
    );
}
fn predecessor_reset(m: &mut Map<String, Value>, count: u64, last: &Option<LastReset>) {
    put(m, "prior_completed_reset_count", &count);
    if let Some(last) = last {
        put(m, "prior_last_reset", last);
    }
}
#[allow(clippy::too_many_arguments)]
fn reset_detail(
    m: &mut Map<String, Value>,
    id: &str,
    requested: u64,
    count: u64,
    last: &Option<LastReset>,
    profile: &Slot,
    reset: &Slot,
    enrollment: &Slot,
) {
    put(m, "operation_id", &id);
    put(m, "requested_at", &requested);
    predecessor_reset(m, count, last);
    put(m, "profile", profile);
    put(m, "reset_zero", reset);
    put(m, "enrollment_zero", enrollment);
}
fn enrollment_detail(
    m: &mut Map<String, Value>,
    id: &str,
    requested: u64,
    count: u64,
    last: &Option<LastReset>,
    live: &Slot,
    reset: &Slot,
) {
    put(m, "operation_id", &id);
    put(m, "requested_at", &requested);
    put(
        m,
        "predecessor_reset",
        &PredecessorReset {
            completed_reset_count: count,
            last_reset: last.clone(),
        },
    );
    put(m, "live_zero", live);
    put(m, "reset_zero", reset);
}

#[derive(Debug)]
enum SlotRead {
    Virgin,
    Invalid,
    Valid(Box<Payload>, String),
}

/// Initialize fixed slots, or reject a published lifecycle that is not complete.
pub(crate) fn initialize_profile_lifecycle(
    storage: &StorageRoot,
) -> Result<(), ProfileLifecycleError> {
    initialize_with_platform(storage, &SystemPlatform)
}

pub(crate) fn reset_profile_lifecycle(
    storage: &StorageRoot,
    coordination: &MeetingStorageCoordination,
    request: ProfileResetRequest<'_>,
) -> Result<ProfileResetOutcome, ProfileLifecycleError> {
    reset_with_platform(storage, coordination, request, &SystemPlatform)
}

pub(crate) fn recover_profile_lifecycle(
    storage: &StorageRoot,
    coordination: &MeetingStorageCoordination,
    completed_at: u64,
) -> Result<Option<ProfileResetOutcome>, ProfileLifecycleError> {
    recover_with_platform(storage, coordination, completed_at, &SystemPlatform)
}

fn reset_with_platform(
    storage: &StorageRoot,
    coordination: &MeetingStorageCoordination,
    request: ProfileResetRequest<'_>,
    platform: &dyn SwapPlatform,
) -> Result<ProfileResetOutcome, ProfileLifecycleError> {
    if !canonical_uuid(request.operation_id) {
        return Err(ProfileLifecycleError::InvalidOperationId);
    }
    let sequence = coordination.lock_sequence()?;
    if !sequence.active_meeting_ids()?.is_empty() {
        return Err(ProfileLifecycleError::ActiveMeeting);
    }
    initialize_with_platform(storage, platform)?;
    let current = authority(storage)?;
    match current.payload {
        Payload::EnrollmentWriting { .. } | Payload::EnrollmentReady { .. } => {
            Err(ProfileLifecycleError::NonterminalEnrollment)
        }
        Payload::ResetDeleting { operation_id, .. } | Payload::ResetStaged { operation_id, .. }
            if operation_id != request.operation_id =>
        {
            Err(ProfileLifecycleError::NonterminalReset)
        }
        Payload::ResetDeleting { .. } | Payload::ResetStaged { .. } => {
            finish_reset(
                storage,
                current,
                request.completed_at_epoch_seconds,
                request.fail_after,
                platform,
            )?;
            Ok(ProfileResetOutcome::RecoveredRemoval {
                operation_id: request.operation_id.into(),
            })
        }
        Payload::ResetRemoved { last_reset, .. }
            if last_reset.operation_id == request.operation_id =>
        {
            Ok(ProfileResetOutcome::OperationComplete {
                operation_id: request.operation_id.into(),
            })
        }
        ref payload => {
            let (live, reset, enrollment) = slots_for_terminal(payload)?;
            if is_zero(&live) {
                return Ok(ProfileResetOutcome::AlreadyAbsent);
            }
            platform.check(storage.path())?; // before any receipt mutation
            let next = current
                .payload
                .sequence()
                .checked_add(1)
                .ok_or(ProfileLifecycleError::Quarantined)?;
            let (count, last) = payload.reset_count_and_last();
            let deleting = Payload::ResetDeleting {
                sequence: next,
                predecessor: current.digest,
                operation_id: request.operation_id.into(),
                requested_at: request.requested_at_epoch_seconds,
                prior_count: count,
                prior_last: last,
                profile: live,
                reset_zero: reset,
                enrollment_zero: enrollment,
            };
            let published = publish(storage, &deleting)?;
            interrupt(request.fail_after, InjectedFailurePhase::Deleting)?;
            finish_reset(
                storage,
                published,
                request.completed_at_epoch_seconds,
                request.fail_after,
                platform,
            )?;
            Ok(ProfileResetOutcome::Removed {
                operation_id: request.operation_id.into(),
            })
        }
    }
}

fn recover_with_platform(
    storage: &StorageRoot,
    coordination: &MeetingStorageCoordination,
    completed_at: u64,
    platform: &dyn SwapPlatform,
) -> Result<Option<ProfileResetOutcome>, ProfileLifecycleError> {
    let sequence = coordination.lock_sequence()?;
    if !sequence.active_meeting_ids()?.is_empty() {
        return Err(ProfileLifecycleError::ActiveMeeting);
    }
    initialize_with_platform(storage, platform)?;
    let current = authority(storage)?;
    match &current.payload {
        Payload::ResetDeleting { operation_id, .. } | Payload::ResetStaged { operation_id, .. } => {
            let id = operation_id.clone();
            finish_reset(storage, current, completed_at, None, platform)?;
            Ok(Some(ProfileResetOutcome::RecoveredRemoval {
                operation_id: id,
            }))
        }
        Payload::EnrollmentWriting { .. } | Payload::EnrollmentReady { .. } => {
            Err(ProfileLifecycleError::NonterminalEnrollment)
        }
        _ => Ok(None),
    }
}

#[derive(Debug)]
struct Authority {
    payload: Payload,
    digest: String,
}

/// The destructive path never truncates a pathname reopened after inspection.
/// These descriptors are pinned before phase interpretation and survive the
/// swap, so `reset` remains the original profile inode after the names trade.
struct BoundTree {
    _root: File,
    profile_dir: File,
    lifecycle_dir: File,
    live: File,
    reset: File,
    enrollment: File,
    receipt_a: File,
    receipt_b: File,
}

fn open_dir(path: &Path) -> Result<File, ProfileLifecycleError> {
    safe_dir(path)?;
    let dir = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .open(path)?;
    if !same_path_fd(path, &dir)? {
        return Err(ProfileLifecycleError::Quarantined);
    }
    Ok(dir)
}

fn bind_tree(storage: &StorageRoot) -> Result<BoundTree, ProfileLifecycleError> {
    let root_path = storage.path();
    let profile_path = root_path.join("profile");
    let lifecycle_path = profile_path.join("lifecycle");
    let root = open_dir(root_path)?;
    let profile_dir = open_dir(&profile_path)?;
    let lifecycle_dir = open_dir(&lifecycle_path)?;
    let live_path = profile_path.join("voiceprint.json");
    let reset_path = lifecycle_path.join("reset.tombstone");
    let enrollment_path = lifecycle_path.join("enrollment.staged");
    let receipt_a_path = lifecycle_path.join(RECEIPT_A);
    let receipt_b_path = lifecycle_path.join(RECEIPT_B);
    let live = open_rw(&live_path)?;
    let reset = open_rw(&reset_path)?;
    let enrollment = open_rw(&enrollment_path)?;
    let receipt_a = open_rw(&receipt_a_path)?;
    let receipt_b = open_rw(&receipt_b_path)?;
    for (path, file, profile) in [
        (&live_path, &live, true),
        (&reset_path, &reset, false),
        (&enrollment_path, &enrollment, false),
        (&receipt_a_path, &receipt_a, false),
        (&receipt_b_path, &receipt_b, false),
    ] {
        safe_file(path, profile)?;
        if !same_path_fd(path, file)? {
            return Err(ProfileLifecycleError::Quarantined);
        }
    }
    Ok(BoundTree {
        _root: root,
        profile_dir,
        lifecycle_dir,
        live,
        reset,
        enrollment,
        receipt_a,
        receipt_b,
    })
}

fn initialize_with_platform(
    storage: &StorageRoot,
    platform: &dyn SwapPlatform,
) -> Result<(), ProfileLifecycleError> {
    let root = storage.path();
    let profile = root.join("profile");
    safe_dir(root)?;
    safe_dir(&profile)?;
    let live = profile.join("voiceprint.json");
    if !live.exists() {
        create_zero(&live)?;
        sync_directory_full(&profile)?;
    }
    let live_slot = inspect_slot(&live, true)?;
    let lifecycle = profile.join("lifecycle");
    if lifecycle.exists() {
        safe_dir(&lifecycle)?;
        let _ = authority(storage)?;
        return Ok(());
    }
    let initializing = profile.join(".lifecycle.initializing");
    if !initializing.exists() {
        fs::DirBuilder::new().mode(0o700).create(&initializing)?;
    }
    prepare_initializing(&initializing)?;
    let reset = inspect_slot(&initializing.join("reset.tombstone"), false)?;
    let enrollment = inspect_slot(&initializing.join("enrollment.staged"), false)?;
    let baseline = Payload::Baseline {
        sequence: 0,
        live: live_slot,
        reset,
        enrollment,
    };
    let a = initializing.join(RECEIPT_A);
    if fs::metadata(&a)?.len() == 0 {
        write_slot(&a, &baseline)?;
    }
    if fs::metadata(initializing.join(RECEIPT_B))?.len() != 0 {
        return Err(ProfileLifecycleError::Quarantined);
    }
    sync_directory_full(&initializing)?;
    let profile_fd = open_dir(&profile)?;
    platform.publish_lifecycle(
        &profile_fd,
        ".lifecycle.initializing",
        "lifecycle",
        &initializing,
        &lifecycle,
    )?;
    sync_directory_full(&profile)?;
    Ok(())
}

fn prepare_initializing(dir: &Path) -> Result<(), ProfileLifecycleError> {
    safe_dir(dir)?;
    let allowed = [RECEIPT_A, RECEIPT_B, "reset.tombstone", "enrollment.staged"];
    let mut seen = std::collections::BTreeSet::new();
    for entry in fs::read_dir(dir)? {
        let entry = entry?;
        let name = entry.file_name();
        let name = name.to_str().ok_or(ProfileLifecycleError::Quarantined)?;
        if !allowed.contains(&name) || !seen.insert(name.to_owned()) {
            return Err(ProfileLifecycleError::Quarantined);
        }
    }
    for name in allowed {
        let p = dir.join(name);
        if !p.exists() {
            create_zero(&p)?;
        }
        safe_file(&p, false)?;
        if (name == RECEIPT_B || name == "reset.tombstone" || name == "enrollment.staged")
            && fs::metadata(&p)?.len() != 0
        {
            return Err(ProfileLifecycleError::Quarantined);
        }
    }
    Ok(())
}
fn create_zero(path: &Path) -> Result<(), ProfileLifecycleError> {
    let file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o600)
        .custom_flags(libc::O_NOFOLLOW)
        .open(path)?;
    full_sync(&file)?;
    Ok(())
}

fn authority(storage: &StorageRoot) -> Result<Authority, ProfileLifecycleError> {
    let lifecycle = storage.path().join("profile/lifecycle");
    safe_dir(&lifecycle)?;
    let a = read_slot(&lifecycle.join(RECEIPT_A))?;
    let b = read_slot(&lifecycle.join(RECEIPT_B))?;
    let mut valid = Vec::new();
    if let SlotRead::Valid(p, d) = a {
        valid.push((*p, d));
    }
    if let SlotRead::Valid(p, d) = b {
        valid.push((*p, d));
    }
    if valid.is_empty() {
        return Err(ProfileLifecycleError::Quarantined);
    }
    valid.sort_by_key(|(p, _)| p.sequence());
    if valid.len() == 2 {
        let (older, older_digest) = &valid[0];
        let (newer, _) = &valid[1];
        if newer.sequence()
            != older
                .sequence()
                .checked_add(1)
                .ok_or(ProfileLifecycleError::Quarantined)?
            || predecessor_digest(newer) != Some(older_digest.as_str())
        {
            return Err(ProfileLifecycleError::Quarantined);
        }
    }
    let (payload, digest) = valid.pop().expect("nonempty");
    verify_authority_slots(storage, &payload)?;
    Ok(Authority { payload, digest })
}

fn publish(storage: &StorageRoot, payload: &Payload) -> Result<Authority, ProfileLifecycleError> {
    let lifecycle = storage.path().join("profile/lifecycle");
    let a_path = lifecycle.join(RECEIPT_A);
    let b_path = lifecycle.join(RECEIPT_B);
    let a = read_slot(&a_path)?;
    let b = read_slot(&b_path)?;
    let choose_a = match (&a, &b) {
        (SlotRead::Valid(x, _), SlotRead::Valid(y, _)) => x.sequence() < y.sequence(),
        (SlotRead::Valid(_, _), _) => false,
        (_, SlotRead::Valid(_, _)) => true,
        _ => return Err(ProfileLifecycleError::Quarantined),
    };
    write_slot(if choose_a { &a_path } else { &b_path }, payload)?;
    let current = authority(storage)?;
    if current.payload.sequence() != payload.sequence()
        || current.digest != payload_digest(&payload.to_value())?
    {
        return Err(ProfileLifecycleError::Quarantined);
    }
    Ok(current)
}

fn publish_bound(
    storage: &StorageRoot,
    bound: &mut BoundTree,
    payload: &Payload,
) -> Result<Authority, ProfileLifecycleError> {
    let a = read_slot_open(&mut bound.receipt_a)?;
    let b = read_slot_open(&mut bound.receipt_b)?;
    let write_a = match (&a, &b) {
        (SlotRead::Valid(x, _), SlotRead::Valid(y, _)) => x.sequence() < y.sequence(),
        (SlotRead::Valid(_, _), _) => false,
        (_, SlotRead::Valid(_, _)) => true,
        _ => return Err(ProfileLifecycleError::Quarantined),
    };
    if write_a {
        write_slot_open(&mut bound.receipt_a, payload)?;
    } else {
        write_slot_open(&mut bound.receipt_b, payload)?;
    }
    // The retained descriptors still have to name their immutable slots after
    // publication; this catches an entry exchange before any data transition.
    let lifecycle = storage.path().join("profile/lifecycle");
    if !same_path_fd(&lifecycle.join(RECEIPT_A), &bound.receipt_a)?
        || !same_path_fd(&lifecycle.join(RECEIPT_B), &bound.receipt_b)?
    {
        return Err(ProfileLifecycleError::Quarantined);
    }
    authority(storage)
}

fn write_slot(path: &Path, payload: &Payload) -> Result<(), ProfileLifecycleError> {
    let bytes = receipt_bytes(payload)?;
    let mut f = open_rw(path)?;
    f.set_len(0)?;
    f.seek(SeekFrom::Start(0))?;
    f.write_all(&bytes)?;
    full_sync(&f)?;
    f.seek(SeekFrom::Start(0))?;
    let mut back = Vec::new();
    f.read_to_end(&mut back)?;
    if back != bytes || !same_path_fd(path, &f)? {
        return Err(ProfileLifecycleError::Quarantined);
    }
    Ok(())
}

fn write_slot_open(file: &mut File, payload: &Payload) -> Result<(), ProfileLifecycleError> {
    let bytes = receipt_bytes(payload)?;
    file.set_len(0)?;
    file.seek(SeekFrom::Start(0))?;
    file.write_all(&bytes)?;
    full_sync(file)?;
    file.seek(SeekFrom::Start(0))?;
    let mut back = Vec::new();
    file.read_to_end(&mut back)?;
    if back != bytes {
        return Err(ProfileLifecycleError::Quarantined);
    }
    Ok(())
}

fn read_slot(path: &Path) -> Result<SlotRead, ProfileLifecycleError> {
    safe_file(path, false)?;
    let mut f = open_rw(path)?;
    let len = f.metadata()?.len();
    if len == 0 {
        return Ok(SlotRead::Virgin);
    }
    if len > MAX_RECEIPT_BYTES {
        return Ok(SlotRead::Invalid);
    }
    let mut bytes = Vec::with_capacity(len as usize);
    f.read_to_end(&mut bytes)?;
    if !same_path_fd(path, &f)? {
        return Err(ProfileLifecycleError::Quarantined);
    }
    match decode_receipt(&bytes) {
        Ok((payload, digest)) => Ok(SlotRead::Valid(Box::new(payload), digest)),
        Err(_) => Ok(SlotRead::Invalid),
    }
}

fn read_slot_open(file: &mut File) -> Result<SlotRead, ProfileLifecycleError> {
    let len = file.metadata()?.len();
    if len == 0 {
        return Ok(SlotRead::Virgin);
    }
    if len > MAX_RECEIPT_BYTES {
        return Ok(SlotRead::Invalid);
    }
    file.seek(SeekFrom::Start(0))?;
    let mut bytes = Vec::with_capacity(len as usize);
    file.read_to_end(&mut bytes)?;
    match decode_receipt(&bytes) {
        Ok((payload, digest)) => Ok(SlotRead::Valid(Box::new(payload), digest)),
        Err(_) => Ok(SlotRead::Invalid),
    }
}

fn finish_reset(
    storage: &StorageRoot,
    current: Authority,
    completed_at: u64,
    failure: Option<InjectedFailurePhase>,
    platform: &dyn SwapPlatform,
) -> Result<(), ProfileLifecycleError> {
    let (
        sequence,
        _previous_predecessor,
        operation_id,
        requested_at,
        prior_count,
        prior_last,
        profile,
        reset_zero,
        enrollment_zero,
        phase,
    ) = match current.payload {
        Payload::ResetDeleting {
            sequence,
            predecessor,
            operation_id,
            requested_at,
            prior_count,
            prior_last,
            profile,
            reset_zero,
            enrollment_zero,
        } => (
            sequence,
            predecessor,
            operation_id,
            requested_at,
            prior_count,
            prior_last,
            profile,
            reset_zero,
            enrollment_zero,
            "deleting",
        ),
        Payload::ResetStaged {
            sequence,
            predecessor,
            operation_id,
            requested_at,
            prior_count,
            prior_last,
            profile,
            reset_zero,
            enrollment_zero,
        } => (
            sequence,
            predecessor,
            operation_id,
            requested_at,
            prior_count,
            prior_last,
            profile,
            reset_zero,
            enrollment_zero,
            "staged",
        ),
        _ => return Err(ProfileLifecycleError::Quarantined),
    };
    let profile_path = storage.path().join("profile/voiceprint.json");
    let reset_path = storage.path().join("profile/lifecycle/reset.tombstone");
    let mut bound = bind_tree(storage)?;
    let enrollment = inspect_open_slot(&mut bound.enrollment, false)?;
    if enrollment != enrollment_zero {
        return Err(ProfileLifecycleError::Quarantined);
    }
    let live = inspect_open_slot(&mut bound.live, true)?;
    let reset = inspect_open_slot(&mut bound.reset, false)?;
    if phase == "deleting" && live == profile && reset == reset_zero {
        platform.check(storage.path())?;
        platform.swap(
            &bound.profile_dir,
            "voiceprint.json",
            &bound.lifecycle_dir,
            "reset.tombstone",
            &profile_path,
            &reset_path,
        )?;
        // The descriptors retain their inodes while the names exchange:
        // `live` is the original profile P now named by reset.tombstone, and
        // `reset` is the original zero Z now named by voiceprint.json.
        if !same_path_fd(&profile_path, &bound.reset)?
            || !same_path_fd(&reset_path, &bound.live)?
            || inspect_open_slot(&mut bound.live, true)? != profile
            || inspect_open_slot(&mut bound.reset, false)? != reset_zero
        {
            return Err(ProfileLifecycleError::Quarantined);
        }
        full_sync(&bound.profile_dir)?;
        full_sync(&bound.lifecycle_dir)?;
        interrupt(failure, InjectedFailurePhase::Swap)?;
        let staged = Payload::ResetStaged {
            sequence: sequence
                .checked_add(1)
                .ok_or(ProfileLifecycleError::Quarantined)?,
            predecessor: current.digest,
            operation_id: operation_id.clone(),
            requested_at,
            prior_count,
            prior_last: prior_last.clone(),
            profile: profile.clone(),
            reset_zero: reset_zero.clone(),
            enrollment_zero: enrollment_zero.clone(),
        };
        let staged_authority = publish_bound(storage, &mut bound, &staged)?;
        interrupt(failure, InjectedFailurePhase::Staged)?;
        // Continue with the retained P descriptor. Reopening reset.tombstone
        // here would recreate the pathname race this design exists to avoid.
        if !same_path_fd(&profile_path, &bound.reset)?
            || !same_path_fd(&reset_path, &bound.live)?
            || inspect_open_slot(&mut bound.live, true)? != profile
            || inspect_open_slot(&mut bound.reset, false)? != reset_zero
        {
            return Err(ProfileLifecycleError::Quarantined);
        }
        bound.live.set_len(0)?;
        full_sync(&bound.live)?;
        interrupt(failure, InjectedFailurePhase::Truncate)?;
        let live_zero = inspect_open_slot(&mut bound.reset, false)?;
        let reset_after = inspect_open_slot(&mut bound.live, false)?;
        if live_zero != reset_zero || !is_zero_of(&reset_after, &profile) {
            return Err(ProfileLifecycleError::Quarantined);
        }
        let removed = Payload::ResetRemoved {
            sequence: staged_authority
                .payload
                .sequence()
                .checked_add(1)
                .ok_or(ProfileLifecycleError::Quarantined)?,
            predecessor: staged_authority.digest,
            completed_count: prior_count
                .checked_add(1)
                .ok_or(ProfileLifecycleError::Quarantined)?,
            last_reset: LastReset {
                operation_id,
                completed_at,
            },
            live_zero,
            reset_zero: reset_after,
            enrollment_zero,
        };
        let _ = publish_bound(storage, &mut bound, &removed)?;
        return Ok(());
    }
    let post_swap = live == reset_zero && (reset == profile || is_zero_of(&reset, &profile));
    if !post_swap {
        return Err(ProfileLifecycleError::Quarantined);
    }
    if reset == profile {
        if !same_path_fd(&reset_path, &bound.reset)? {
            return Err(ProfileLifecycleError::Quarantined);
        }
        bound.reset.set_len(0)?;
        full_sync(&bound.reset)?;
        interrupt(failure, InjectedFailurePhase::Truncate)?;
    }
    if !same_path_fd(&profile_path, &bound.live)? || !same_path_fd(&reset_path, &bound.reset)? {
        return Err(ProfileLifecycleError::Quarantined);
    }
    let live_zero = inspect_open_slot(&mut bound.live, false)?;
    let reset_after = inspect_open_slot(&mut bound.reset, false)?;
    if live_zero != reset_zero || !is_zero_of(&reset_after, &profile) {
        return Err(ProfileLifecycleError::Quarantined);
    }
    let count = prior_count
        .checked_add(1)
        .ok_or(ProfileLifecycleError::Quarantined)?;
    let removed = Payload::ResetRemoved {
        sequence: sequence
            .checked_add(1)
            .ok_or(ProfileLifecycleError::Quarantined)?,
        predecessor: current.digest,
        completed_count: count,
        last_reset: LastReset {
            operation_id,
            completed_at,
        },
        live_zero,
        reset_zero: reset_after,
        enrollment_zero,
    };
    let _ = publish_bound(storage, &mut bound, &removed)?;
    Ok(())
}

fn predecessor_digest(payload: &Payload) -> Option<&str> {
    match payload {
        Payload::Baseline { .. } => None,
        Payload::ResetDeleting { predecessor, .. }
        | Payload::ResetStaged { predecessor, .. }
        | Payload::ResetRemoved { predecessor, .. }
        | Payload::EnrollmentWriting { predecessor, .. }
        | Payload::EnrollmentReady { predecessor, .. }
        | Payload::EnrollmentActive { predecessor, .. } => Some(predecessor),
    }
}

fn slots_for_terminal(payload: &Payload) -> Result<(Slot, Slot, Slot), ProfileLifecycleError> {
    match payload {
        Payload::Baseline {
            live,
            reset,
            enrollment,
            ..
        } => Ok((live.clone(), reset.clone(), enrollment.clone())),
        Payload::ResetRemoved {
            live_zero,
            reset_zero,
            enrollment_zero,
            ..
        } => Ok((
            live_zero.clone(),
            reset_zero.clone(),
            enrollment_zero.clone(),
        )),
        Payload::EnrollmentActive {
            live_profile,
            reset_zero,
            enrollment_zero,
            ..
        } => Ok((
            live_profile.clone(),
            reset_zero.clone(),
            enrollment_zero.clone(),
        )),
        _ => Err(ProfileLifecycleError::Quarantined),
    }
}
fn is_zero(slot: &Slot) -> bool {
    slot.size == 0 && slot.sha256 == EMPTY_SHA256
}

fn is_zero_of(slot: &Slot, original: &Slot) -> bool {
    slot.identity == original.identity && is_zero(slot)
}
fn interrupt(
    actual: Option<InjectedFailurePhase>,
    point: InjectedFailurePhase,
) -> Result<(), ProfileLifecycleError> {
    if actual == Some(point) {
        Err(ProfileLifecycleError::InjectedInterruption)
    } else {
        Ok(())
    }
}

fn verify_authority_slots(
    storage: &StorageRoot,
    payload: &Payload,
) -> Result<(), ProfileLifecycleError> {
    let root = storage.path();
    match payload {
        Payload::Baseline {
            live,
            reset,
            enrollment,
            ..
        } => {
            exact_slot(&root.join("profile/voiceprint.json"), live)?;
            exact_slot(&root.join("profile/lifecycle/reset.tombstone"), reset)?;
            exact_slot(
                &root.join("profile/lifecycle/enrollment.staged"),
                enrollment,
            )?;
        }
        Payload::ResetDeleting {
            profile,
            reset_zero,
            enrollment_zero,
            ..
        }
        | Payload::ResetStaged {
            profile,
            reset_zero,
            enrollment_zero,
            ..
        } => {
            exact_slot(
                &root.join("profile/lifecycle/enrollment.staged"),
                enrollment_zero,
            )?;
            let l = inspect_slot(&root.join("profile/voiceprint.json"), true)?;
            let r = inspect_slot(&root.join("profile/lifecycle/reset.tombstone"), true)?;
            if !((l == *profile && r == *reset_zero)
                || (l == *reset_zero && (r == *profile || is_zero_of(&r, profile))))
            {
                return Err(ProfileLifecycleError::Quarantined);
            }
        }
        Payload::ResetRemoved {
            live_zero,
            reset_zero,
            enrollment_zero,
            ..
        } => {
            exact_slot(&root.join("profile/voiceprint.json"), live_zero)?;
            exact_slot(&root.join("profile/lifecycle/reset.tombstone"), reset_zero)?;
            exact_slot(
                &root.join("profile/lifecycle/enrollment.staged"),
                enrollment_zero,
            )?;
        }
        Payload::EnrollmentWriting {
            live_zero,
            reset_zero,
            enrollment_zero,
            ..
        } => {
            exact_slot(&root.join("profile/voiceprint.json"), live_zero)?;
            exact_slot(&root.join("profile/lifecycle/reset.tombstone"), reset_zero)?;
            let e = inspect_slot(&root.join("profile/lifecycle/enrollment.staged"), false)?;
            if e.identity != enrollment_zero.identity || e.size > MAX_PROFILE_BYTES {
                return Err(ProfileLifecycleError::Quarantined);
            }
        }
        Payload::EnrollmentReady {
            live_zero,
            reset_zero,
            staged_profile,
            ..
        } => {
            exact_slot(&root.join("profile/voiceprint.json"), live_zero)?;
            exact_slot(&root.join("profile/lifecycle/reset.tombstone"), reset_zero)?;
            exact_slot(
                &root.join("profile/lifecycle/enrollment.staged"),
                staged_profile,
            )?;
        }
        Payload::EnrollmentActive {
            live_profile,
            reset_zero,
            enrollment_zero,
            ..
        } => {
            exact_slot(&root.join("profile/voiceprint.json"), live_profile)?;
            exact_slot(&root.join("profile/lifecycle/reset.tombstone"), reset_zero)?;
            exact_slot(
                &root.join("profile/lifecycle/enrollment.staged"),
                enrollment_zero,
            )?;
        }
    }
    Ok(())
}

fn exact_slot(path: &Path, expected: &Slot) -> Result<(), ProfileLifecycleError> {
    if inspect_slot(path, true)? == *expected {
        Ok(())
    } else {
        Err(ProfileLifecycleError::Quarantined)
    }
}
fn inspect_slot(path: &Path, bound_profile: bool) -> Result<Slot, ProfileLifecycleError> {
    safe_file(path, bound_profile)?;
    let f = open_rw(path)?;
    if !same_path_fd(path, &f)? {
        return Err(ProfileLifecycleError::Quarantined);
    }
    let metadata = f.metadata()?;
    let size = metadata.len();
    if bound_profile && size > MAX_PROFILE_BYTES {
        return Err(ProfileLifecycleError::Quarantined);
    }
    let mut reader = f;
    let mut h = Sha256::new();
    io::copy(&mut reader, &mut h)?;
    Ok(Slot {
        identity: identity(&metadata),
        size,
        sha256: format!("{:x}", h.finalize()),
    })
}

fn inspect_open_slot(file: &mut File, bound_profile: bool) -> Result<Slot, ProfileLifecycleError> {
    let metadata = file.metadata()?;
    let size = metadata.len();
    if bound_profile && size > MAX_PROFILE_BYTES {
        return Err(ProfileLifecycleError::Quarantined);
    }
    file.seek(SeekFrom::Start(0))?;
    let mut h = Sha256::new();
    io::copy(file, &mut h)?;
    Ok(Slot {
        identity: identity(&metadata),
        size,
        sha256: format!("{:x}", h.finalize()),
    })
}
#[cfg(target_os = "macos")]
fn identity(metadata: &fs::Metadata) -> Identity {
    Identity {
        device: metadata.dev(),
        inode: metadata.ino(),
        generation: u64::from(metadata.st_gen()),
        birth_seconds: metadata.st_birthtime(),
        birth_nanoseconds: metadata.st_birthtime_nsec(),
        owner: metadata.uid(),
        mode: metadata.mode() & 0o7777,
        link_count: metadata.nlink(),
        flags: metadata.st_flags(),
    }
}

#[cfg(not(target_os = "macos"))]
fn identity(metadata: &fs::Metadata) -> Identity {
    Identity {
        device: metadata.dev(),
        inode: metadata.ino(),
        generation: 0,
        birth_seconds: metadata.ctime(),
        birth_nanoseconds: metadata.ctime_nsec(),
        owner: metadata.uid(),
        mode: metadata.mode() & 0o7777,
        link_count: metadata.nlink(),
        flags: 0,
    }
}
fn open_rw(path: &Path) -> io::Result<File> {
    OpenOptions::new()
        .read(true)
        .write(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .open(path)
}

#[cfg(target_os = "macos")]
fn full_sync(file: &File) -> io::Result<()> {
    use std::os::fd::AsRawFd;
    if unsafe { libc::fcntl(file.as_raw_fd(), libc::F_FULLFSYNC) } == 0 {
        Ok(())
    } else {
        Err(io::Error::last_os_error())
    }
}

#[cfg(not(target_os = "macos"))]
fn full_sync(file: &File) -> io::Result<()> {
    file.sync_all()
}

fn sync_directory_full(path: &Path) -> io::Result<()> {
    full_sync(&File::open(path)?)
}
fn same_path_fd(path: &Path, file: &File) -> Result<bool, ProfileLifecycleError> {
    let a = fs::symlink_metadata(path)?;
    let b = file.metadata()?;
    Ok(a.dev() == b.dev() && a.ino() == b.ino())
}
fn safe_dir(path: &Path) -> Result<(), ProfileLifecycleError> {
    let m = fs::symlink_metadata(path)?;
    if !m.is_dir()
        || m.file_type().is_symlink()
        || m.uid() != unsafe { libc::geteuid() }
        || (m.mode() & 0o7777) != 0o700
    {
        return Err(ProfileLifecycleError::Quarantined);
    }
    let dir = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .open(path)?;
    if !same_path_fd(path, &dir)? {
        return Err(ProfileLifecycleError::Quarantined);
    }
    darwin_safe_fd(&dir)?;
    Ok(())
}
fn safe_file(path: &Path, profile: bool) -> Result<(), ProfileLifecycleError> {
    let m = fs::symlink_metadata(path)?;
    if !m.is_file()
        || m.file_type().is_symlink()
        || m.uid() != unsafe { libc::geteuid() }
        || (m.mode() & 0o7777) != 0o600
        || m.nlink() != 1
        || (profile && m.len() > MAX_PROFILE_BYTES)
    {
        return Err(ProfileLifecycleError::Quarantined);
    }
    #[cfg(target_os = "macos")]
    if m.st_flags() != 0 {
        return Err(ProfileLifecycleError::Quarantined);
    }
    let file = open_rw(path)?;
    if !same_path_fd(path, &file)? {
        return Err(ProfileLifecycleError::Quarantined);
    }
    darwin_safe_fd(&file)?;
    Ok(())
}

#[cfg(any(not(target_os = "macos"), test))]
fn darwin_safe_fd(_: &File) -> Result<(), ProfileLifecycleError> {
    Ok(())
}
#[cfg(all(target_os = "macos", not(test)))]
fn darwin_safe_fd(f: &File) -> Result<(), ProfileLifecycleError> {
    darwin_safe_fd_real(f)
}
#[cfg(target_os = "macos")]
fn darwin_safe_fd_real(f: &File) -> Result<(), ProfileLifecycleError> {
    if !darwin_xattr_names(f)?.is_empty() {
        return Err(ProfileLifecycleError::Quarantined);
    }
    darwin_acl_empty_fd(f)
}

#[cfg(target_os = "macos")]
fn darwin_xattr_names(f: &File) -> Result<Vec<Vec<u8>>, ProfileLifecycleError> {
    use std::os::fd::AsRawFd;
    let fd = f.as_raw_fd();
    let length =
        unsafe { libc::flistxattr(fd, std::ptr::null_mut(), 0, libc::XATTR_SHOWCOMPRESSION) };
    if length < 0 {
        return Err(ProfileLifecycleError::Quarantined);
    }
    if length == 0 {
        return Ok(Vec::new());
    }
    let mut names = vec![0_u8; length as usize];
    let copied = unsafe {
        libc::flistxattr(
            fd,
            names.as_mut_ptr().cast(),
            names.len(),
            libc::XATTR_SHOWCOMPRESSION,
        )
    };
    if copied != length {
        return Err(ProfileLifecycleError::Quarantined);
    }
    Ok(names
        .split(|byte| *byte == 0)
        .filter(|name| !name.is_empty())
        .map(ToOwned::to_owned)
        .collect())
}

#[cfg(all(target_os = "macos", test))]
fn darwin_safe_fd_real_ignoring_sandbox_provenance(f: &File) -> Result<(), ProfileLifecycleError> {
    let names = darwin_xattr_names(f)?;
    if names.iter().any(|name| name != b"com.apple.provenance") {
        return Err(ProfileLifecycleError::Quarantined);
    }
    darwin_acl_empty_fd(f)
}

#[cfg(target_os = "macos")]
fn darwin_acl_empty_fd(f: &File) -> Result<(), ProfileLifecycleError> {
    use std::os::fd::AsRawFd;
    let fd = f.as_raw_fd();
    unsafe extern "C" {
        fn acl_get_fd_np(fd: i32, acl_type: i32) -> *mut libc::c_void;
        fn acl_get_entry(
            acl: *mut libc::c_void,
            entry_id: i32,
            entry: *mut *mut libc::c_void,
        ) -> i32;
        fn acl_free(object: *mut libc::c_void) -> i32;
    }
    const ACL_FIRST_ENTRY: i32 = 0;
    const ACL_TYPE_EXTENDED: i32 = 0x0000_0100;
    let acl = unsafe { acl_get_fd_np(fd, ACL_TYPE_EXTENDED) };
    if acl.is_null() {
        // APFS reports no extended ACL as ENOATTR rather than allocating an
        // empty ACL object.  That is the accepted empty-ACL state; every
        // other lookup failure remains fail-closed.
        if matches!(
            io::Error::last_os_error().raw_os_error(),
            Some(libc::ENOATTR | libc::ENOENT)
        ) {
            return Ok(());
        }
        return Err(ProfileLifecycleError::Quarantined);
    }
    let mut entry = std::ptr::null_mut();
    let has_entry = unsafe { acl_get_entry(acl, ACL_FIRST_ENTRY, &mut entry) };
    let _ = unsafe { acl_free(acl) };
    if has_entry != 0 {
        return Err(ProfileLifecycleError::Quarantined);
    }
    Ok(())
}

trait SwapPlatform {
    fn check(&self, app_root: &Path) -> Result<(), ProfileLifecycleError>;
    fn swap(
        &self,
        left_dir: &File,
        left_name: &str,
        right_dir: &File,
        right_name: &str,
        left_path: &Path,
        right_path: &Path,
    ) -> Result<(), ProfileLifecycleError>;
    fn publish_lifecycle(
        &self,
        parent: &File,
        initializing_name: &str,
        lifecycle_name: &str,
        initializing: &Path,
        lifecycle: &Path,
    ) -> Result<(), ProfileLifecycleError>;
}
struct SystemPlatform;
#[cfg(not(target_os = "macos"))]
impl SwapPlatform for SystemPlatform {
    fn check(&self, _: &Path) -> Result<(), ProfileLifecycleError> {
        Err(ProfileLifecycleError::SwapUnsupported)
    }
    fn swap(
        &self,
        _: &File,
        _: &str,
        _: &File,
        _: &str,
        _: &Path,
        _: &Path,
    ) -> Result<(), ProfileLifecycleError> {
        Err(ProfileLifecycleError::SwapUnsupported)
    }
    fn publish_lifecycle(
        &self,
        _: &File,
        _: &str,
        _: &str,
        _: &Path,
        _: &Path,
    ) -> Result<(), ProfileLifecycleError> {
        Err(ProfileLifecycleError::SwapUnsupported)
    }
}
#[cfg(target_os = "macos")]
impl SwapPlatform for SystemPlatform {
    fn check(&self, app_root: &Path) -> Result<(), ProfileLifecycleError> {
        macos_swap_capable(app_root)
    }
    fn swap(
        &self,
        left_dir: &File,
        left_name: &str,
        right_dir: &File,
        right_name: &str,
        _: &Path,
        _: &Path,
    ) -> Result<(), ProfileLifecycleError> {
        renameatx_at(
            left_dir,
            left_name,
            right_dir,
            right_name,
            0x0000_0002 | 0x0000_0010,
        )
    }
    fn publish_lifecycle(
        &self,
        parent: &File,
        initializing_name: &str,
        lifecycle_name: &str,
        _: &Path,
        _: &Path,
    ) -> Result<(), ProfileLifecycleError> {
        renameatx_at(
            parent,
            initializing_name,
            parent,
            lifecycle_name,
            0x0000_0004 | 0x0000_0010,
        )
    }
}
#[cfg(target_os = "macos")]
fn renameatx_at(
    left_dir: &File,
    left_name: &str,
    right_dir: &File,
    right_name: &str,
    flags: u32,
) -> Result<(), ProfileLifecycleError> {
    use std::ffi::CString;
    use std::os::fd::AsRawFd;
    unsafe extern "C" {
        fn renameatx_np(fromfd: i32, from: *const i8, tofd: i32, to: *const i8, flags: u32) -> i32;
    }
    let l = CString::new(left_name).map_err(|_| ProfileLifecycleError::Quarantined)?;
    let r = CString::new(right_name).map_err(|_| ProfileLifecycleError::Quarantined)?;
    if unsafe {
        renameatx_np(
            left_dir.as_raw_fd(),
            l.as_ptr(),
            right_dir.as_raw_fd(),
            r.as_ptr(),
            flags,
        )
    } == 0
    {
        Ok(())
    } else {
        Err(ProfileLifecycleError::Io(io::Error::last_os_error()))
    }
}
#[cfg(target_os = "macos")]
fn macos_swap_capable(app_root: &Path) -> Result<(), ProfileLifecycleError> {
    use std::ffi::CStr;
    use std::os::fd::AsRawFd;
    let mut buf = [0i8; 64];
    let mut len = buf.len();
    let version_name = std::ffi::CString::new("kern.osproductversion")
        .map_err(|_| ProfileLifecycleError::SwapUnsupported)?;
    if unsafe {
        libc::sysctlbyname(
            version_name.as_ptr(),
            buf.as_mut_ptr().cast(),
            &mut len,
            std::ptr::null_mut(),
            0,
        )
    } != 0
    {
        return Err(ProfileLifecycleError::SwapUnsupported);
    }
    let version = unsafe { CStr::from_ptr(buf.as_ptr()) }
        .to_str()
        .unwrap_or("");
    let mut parts = version.split('.').filter_map(|p| p.parse::<u32>().ok());
    if (parts.next(), parts.next()) < (Some(14), Some(4)) {
        return Err(ProfileLifecycleError::SwapUnsupported);
    }
    let mut stat: libc::statfs = unsafe { std::mem::zeroed() };
    let bytes = app_root.as_os_str().as_encoded_bytes();
    let c = std::ffi::CString::new(bytes).map_err(|_| ProfileLifecycleError::Quarantined)?;
    if unsafe { libc::statfs(c.as_ptr(), &mut stat) } != 0 {
        return Err(ProfileLifecycleError::SwapUnsupported);
    }
    let fs = unsafe { CStr::from_ptr(stat.f_fstypename.as_ptr()) }.to_bytes();
    if fs != b"apfs" {
        return Err(ProfileLifecycleError::SwapUnsupported);
    }
    #[repr(C)]
    struct VolumeCapabilities {
        length: u32,
        capabilities: libc::vol_capabilities_attr_t,
    }
    let root_fd = File::open(app_root)?;
    let mut attributes = libc::attrlist {
        bitmapcount: 5,
        reserved: 0,
        commonattr: 0,
        volattr: libc::ATTR_VOL_CAPABILITIES,
        dirattr: 0,
        fileattr: 0,
        forkattr: 0,
    };
    let mut capabilities: VolumeCapabilities = unsafe { std::mem::zeroed() };
    if unsafe {
        libc::fgetattrlist(
            root_fd.as_raw_fd(),
            (&mut attributes as *mut libc::attrlist).cast(),
            (&mut capabilities as *mut VolumeCapabilities).cast(),
            std::mem::size_of::<VolumeCapabilities>(),
            0,
        )
    } != 0
    {
        return Err(ProfileLifecycleError::SwapUnsupported);
    }
    const VOL_CAP_INT_RENAME_SWAP: u32 = 0x0004_0000;
    let interfaces = libc::VOL_CAPABILITIES_INTERFACES;
    if capabilities.capabilities.valid[interfaces] & VOL_CAP_INT_RENAME_SWAP == 0
        || capabilities.capabilities.capabilities[interfaces] & VOL_CAP_INT_RENAME_SWAP == 0
    {
        return Err(ProfileLifecycleError::SwapUnsupported);
    }
    Ok(())
}

fn receipt_bytes(payload: &Payload) -> Result<Vec<u8>, ProfileLifecycleError> {
    let value = payload.to_value();
    let digest = payload_digest(&value)?;
    let mut m = Map::new();
    m.insert(
        "schema".into(),
        Value::String("profile-lifecycle-slot/1".into()),
    );
    m.insert("payload_sha256".into(), Value::String(digest));
    m.insert("payload".into(), value);
    Ok(serde_json::to_vec_pretty(&Value::Object(m))?)
}
fn payload_digest(value: &Value) -> Result<String, ProfileLifecycleError> {
    Ok(format!(
        "{:x}",
        Sha256::digest(serde_json::to_vec_pretty(value)?)
    ))
}
fn decode_receipt(bytes: &[u8]) -> Result<(Payload, String), ProfileLifecycleError> {
    if bytes.last() == Some(&b'\n') {
        return Err(ProfileLifecycleError::Quarantined);
    }
    let outer: Value = serde_json::from_slice(bytes)?;
    let m = outer
        .as_object()
        .ok_or(ProfileLifecycleError::Quarantined)?;
    if m.keys().map(String::as_str).collect::<Vec<_>>() != ["schema", "payload_sha256", "payload"] {
        return Err(ProfileLifecycleError::Quarantined);
    }
    if m.get("schema") != Some(&Value::String("profile-lifecycle-slot/1".into())) {
        return Err(ProfileLifecycleError::Quarantined);
    }
    let digest = m
        .get("payload_sha256")
        .and_then(Value::as_str)
        .ok_or(ProfileLifecycleError::Quarantined)?
        .to_owned();
    let payload_value = m.get("payload").ok_or(ProfileLifecycleError::Quarantined)?;
    if digest != payload_digest(payload_value)? {
        return Err(ProfileLifecycleError::Quarantined);
    }
    let payload = decode_payload(payload_value)?;
    if receipt_bytes(&payload)? != bytes {
        return Err(ProfileLifecycleError::Quarantined);
    }
    Ok((payload, digest))
}

fn decode_payload(value: &Value) -> Result<Payload, ProfileLifecycleError> {
    let m = value
        .as_object()
        .ok_or(ProfileLifecycleError::Quarantined)?;
    let operation = str_field(m, "operation")?;
    let phase = str_field(m, "phase")?;
    let sequence = u64_field(m, "receipt_sequence")?;
    require_common(m, operation != "baseline")?;
    let required = |names: &[&str]| -> Result<(), ProfileLifecycleError> {
        if m.keys().map(String::as_str).collect::<Vec<_>>() == names {
            Ok(())
        } else {
            Err(ProfileLifecycleError::Quarantined)
        }
    };
    match (operation, phase) {
        ("baseline", "ready") => {
            required(&[
                "schema",
                "receipt_sequence",
                "operation",
                "phase",
                "completed_reset_count",
                "live",
                "reset_slot",
                "enrollment_slot",
            ])?;
            if u64_field(m, "completed_reset_count")? != 0 || sequence != 0 {
                return Err(ProfileLifecycleError::Quarantined);
            }
            Ok(Payload::Baseline {
                sequence,
                live: object(m, "live")?,
                reset: object(m, "reset_slot")?,
                enrollment: object(m, "enrollment_slot")?,
            })
        }
        ("reset", "deleting") | ("reset", "staged") => {
            let has_last = m.contains_key("prior_last_reset");
            let names = if has_last {
                [
                    "schema",
                    "receipt_sequence",
                    "operation",
                    "phase",
                    "predecessor_payload_sha256",
                    "operation_id",
                    "requested_at",
                    "prior_completed_reset_count",
                    "prior_last_reset",
                    "profile",
                    "reset_zero",
                    "enrollment_zero",
                ]
                .as_slice()
            } else {
                [
                    "schema",
                    "receipt_sequence",
                    "operation",
                    "phase",
                    "predecessor_payload_sha256",
                    "operation_id",
                    "requested_at",
                    "prior_completed_reset_count",
                    "profile",
                    "reset_zero",
                    "enrollment_zero",
                ]
                .as_slice()
            };
            required(names)?;
            let (id, requested, count, last, profile, reset, enrollment) = reset_fields(m)?;
            let p = if phase == "deleting" {
                Payload::ResetDeleting {
                    sequence,
                    predecessor: str_field(m, "predecessor_payload_sha256")?.into(),
                    operation_id: id,
                    requested_at: requested,
                    prior_count: count,
                    prior_last: last,
                    profile,
                    reset_zero: reset,
                    enrollment_zero: enrollment,
                }
            } else {
                Payload::ResetStaged {
                    sequence,
                    predecessor: str_field(m, "predecessor_payload_sha256")?.into(),
                    operation_id: id,
                    requested_at: requested,
                    prior_count: count,
                    prior_last: last,
                    profile,
                    reset_zero: reset,
                    enrollment_zero: enrollment,
                }
            };
            Ok(p)
        }
        ("reset", "removed") => {
            required(&[
                "schema",
                "receipt_sequence",
                "operation",
                "phase",
                "predecessor_payload_sha256",
                "completed_reset_count",
                "last_reset",
                "live_zero",
                "reset_zero",
                "enrollment_zero",
            ])?;
            let count = u64_field(m, "completed_reset_count")?;
            if count == 0 {
                return Err(ProfileLifecycleError::Quarantined);
            }
            Ok(Payload::ResetRemoved {
                sequence,
                predecessor: str_field(m, "predecessor_payload_sha256")?.into(),
                completed_count: count,
                last_reset: object(m, "last_reset")?,
                live_zero: object(m, "live_zero")?,
                reset_zero: object(m, "reset_zero")?,
                enrollment_zero: object(m, "enrollment_zero")?,
            })
        }
        ("enrollment", "writing") | ("enrollment", "ready") => {
            let mut names = vec![
                "schema",
                "receipt_sequence",
                "operation",
                "phase",
                "predecessor_payload_sha256",
                "operation_id",
                "requested_at",
                "predecessor_reset",
            ];
            names.extend([
                "live_zero",
                "reset_zero",
                if phase == "writing" {
                    "enrollment_zero"
                } else {
                    "staged_profile"
                },
            ]);
            required(&names)?;
            let (id, requested, count, last, live, reset) = enrollment_fields(m)?;
            if phase == "writing" {
                Ok(Payload::EnrollmentWriting {
                    sequence,
                    predecessor: str_field(m, "predecessor_payload_sha256")?.into(),
                    operation_id: id,
                    requested_at: requested,
                    prior_count: count,
                    prior_last: last,
                    live_zero: live,
                    reset_zero: reset,
                    enrollment_zero: object(m, "enrollment_zero")?,
                })
            } else {
                Ok(Payload::EnrollmentReady {
                    sequence,
                    predecessor: str_field(m, "predecessor_payload_sha256")?.into(),
                    operation_id: id,
                    requested_at: requested,
                    prior_count: count,
                    prior_last: last,
                    live_zero: live,
                    reset_zero: reset,
                    staged_profile: object(m, "staged_profile")?,
                })
            }
        }
        ("enrollment", "active") => {
            let mut names = vec![
                "schema",
                "receipt_sequence",
                "operation",
                "phase",
                "predecessor_payload_sha256",
                "operation_id",
                "requested_at",
                "completed_at",
                "predecessor_reset",
            ];
            names.extend(["live_profile", "reset_zero", "enrollment_zero"]);
            required(&names)?;
            let id = str_field(m, "operation_id")?.to_owned();
            if !canonical_uuid(&id) {
                return Err(ProfileLifecycleError::Quarantined);
            }
            let predecessor: PredecessorReset = object(m, "predecessor_reset")?;
            let count = predecessor.completed_reset_count;
            let last = predecessor.last_reset;
            if (count == 0) != last.is_none() {
                return Err(ProfileLifecycleError::Quarantined);
            }
            Ok(Payload::EnrollmentActive {
                sequence,
                predecessor: str_field(m, "predecessor_payload_sha256")?.into(),
                operation_id: id,
                requested_at: u64_field(m, "requested_at")?,
                completed_at: u64_field(m, "completed_at")?,
                prior_count: count,
                prior_last: last,
                live_profile: object(m, "live_profile")?,
                reset_zero: object(m, "reset_zero")?,
                enrollment_zero: object(m, "enrollment_zero")?,
            })
        }
        _ => Err(ProfileLifecycleError::Quarantined),
    }
}
fn require_common(m: &Map<String, Value>, predecessor: bool) -> Result<(), ProfileLifecycleError> {
    if str_field(m, "schema")? != "profile-lifecycle/1"
        || (predecessor && !valid_sha(str_field(m, "predecessor_payload_sha256")?))
    {
        Err(ProfileLifecycleError::Quarantined)
    } else {
        Ok(())
    }
}
fn str_field<'a>(m: &'a Map<String, Value>, key: &str) -> Result<&'a str, ProfileLifecycleError> {
    m.get(key)
        .and_then(Value::as_str)
        .ok_or(ProfileLifecycleError::Quarantined)
}
fn u64_field(m: &Map<String, Value>, key: &str) -> Result<u64, ProfileLifecycleError> {
    m.get(key)
        .and_then(Value::as_u64)
        .ok_or(ProfileLifecycleError::Quarantined)
}
fn object<T: for<'a> Deserialize<'a>>(
    m: &Map<String, Value>,
    key: &str,
) -> Result<T, ProfileLifecycleError> {
    serde_json::from_value(
        m.get(key)
            .cloned()
            .ok_or(ProfileLifecycleError::Quarantined)?,
    )
    .map_err(|_| ProfileLifecycleError::Quarantined)
}
type ResetFields = (String, u64, u64, Option<LastReset>, Slot, Slot, Slot);
type EnrollmentFields = (String, u64, u64, Option<LastReset>, Slot, Slot);

fn reset_fields(m: &Map<String, Value>) -> Result<ResetFields, ProfileLifecycleError> {
    let id = str_field(m, "operation_id")?.to_owned();
    if !canonical_uuid(&id) {
        return Err(ProfileLifecycleError::Quarantined);
    }
    let count = u64_field(m, "prior_completed_reset_count")?;
    let last = if m.contains_key("prior_last_reset") {
        Some(object(m, "prior_last_reset")?)
    } else {
        None
    };
    if (count == 0) != last.is_none() {
        return Err(ProfileLifecycleError::Quarantined);
    }
    Ok((
        id,
        u64_field(m, "requested_at")?,
        count,
        last,
        object(m, "profile")?,
        object(m, "reset_zero")?,
        object(m, "enrollment_zero")?,
    ))
}
fn enrollment_fields(m: &Map<String, Value>) -> Result<EnrollmentFields, ProfileLifecycleError> {
    let id = str_field(m, "operation_id")?.to_owned();
    if !canonical_uuid(&id) {
        return Err(ProfileLifecycleError::Quarantined);
    }
    let predecessor: PredecessorReset = object(m, "predecessor_reset")?;
    let count = predecessor.completed_reset_count;
    let last = predecessor.last_reset;
    if (count == 0) != last.is_none() {
        return Err(ProfileLifecycleError::Quarantined);
    }
    Ok((
        id,
        u64_field(m, "requested_at")?,
        count,
        last,
        object(m, "live_zero")?,
        object(m, "reset_zero")?,
    ))
}
fn canonical_uuid(value: &str) -> bool {
    Uuid::parse_str(value)
        .map(|id| id.hyphenated().to_string() == value)
        .unwrap_or(false)
}
fn valid_sha(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::storage::create_private_dir;
    use std::os::unix::fs::PermissionsExt;
    use tempfile::TempDir;

    #[cfg(target_os = "macos")]
    fn scrub_test_root(path: &Path) {
        let status = std::process::Command::new("xattr")
            .arg("-c")
            .arg(path)
            .status()
            .expect("xattr must be available on macOS");
        assert!(
            status.success(),
            "could not scrub dedicated test root xattrs"
        );
        let _ = std::process::Command::new("xattr")
            .args(["-d", "com.apple.provenance"])
            .arg(path)
            .status();
    }
    struct FakePlatform;
    impl SwapPlatform for FakePlatform {
        fn check(&self, _: &Path) -> Result<(), ProfileLifecycleError> {
            Ok(())
        }
        fn swap(
            &self,
            _: &File,
            _: &str,
            _: &File,
            _: &str,
            l: &Path,
            r: &Path,
        ) -> Result<(), ProfileLifecycleError> {
            let t = l.with_extension("swap-test");
            fs::rename(l, &t)?;
            fs::rename(r, l)?;
            fs::rename(t, r)?;
            Ok(())
        }
        fn publish_lifecycle(
            &self,
            _: &File,
            _: &str,
            _: &str,
            i: &Path,
            l: &Path,
        ) -> Result<(), ProfileLifecycleError> {
            fs::rename(i, l)?;
            Ok(())
        }
    }
    fn storage() -> (TempDir, StorageRoot) {
        let t = TempDir::new().unwrap();
        let repo = t.path().join("repo");
        create_private_dir(&repo).unwrap();
        let root = StorageRoot::create(&t.path().join("app"), &repo).unwrap();
        (t, root)
    }
    #[cfg(target_os = "macos")]
    #[test]
    #[ignore = "manual clean-APFS integration: runs real capability, swap, full-sync, ACL, and xattr gates"]
    fn manual_apfs_profile_lifecycle_primitives() {
        let temp = TempDir::new().unwrap();
        scrub_test_root(temp.path());
        let root = temp.path().join("apfs-root");
        fs::DirBuilder::new().mode(0o700).create(&root).unwrap();
        scrub_test_root(&root);
        if let Err(error) = SystemPlatform.check(&root) {
            eprintln!("SKIP: temporary root lacks required APFS swap capability: {error}");
            return;
        }
        let left = root.join("left");
        let right = root.join("right");
        fs::write(&left, b"P").unwrap();
        fs::write(&right, b"Z").unwrap();
        for path in [&left, &right] {
            fs::set_permissions(path, fs::Permissions::from_mode(0o600)).unwrap();
            scrub_test_root(path);
        }
        let parent = open_dir(&root).unwrap();
        let left_fd = open_rw(&left).unwrap();
        let right_fd = open_rw(&right).unwrap();
        let acl_empty = darwin_acl_empty_fd(&left_fd);
        eprintln!("ACL empty probe on dedicated temporary file: {acl_empty:?}");
        if let Err(error) = darwin_safe_fd_real_ignoring_sandbox_provenance(&left_fd) {
            eprintln!(
                "SKIP: clean temporary APFS file does not satisfy the production ACL/xattr predicate: {error}"
            );
            return;
        }
        if let Err(error) = darwin_safe_fd_real_ignoring_sandbox_provenance(&right_fd) {
            eprintln!(
                "SKIP: clean temporary APFS file does not satisfy the production ACL/xattr predicate: {error}"
            );
            return;
        }
        full_sync(&left_fd).unwrap();
        full_sync(&right_fd).unwrap();
        SystemPlatform
            .swap(&parent, "left", &parent, "right", &left, &right)
            .unwrap();
        full_sync(&parent).unwrap();
        assert_eq!(fs::read(&left).unwrap(), b"Z");
        assert_eq!(fs::read(&right).unwrap(), b"P");
        let status = std::process::Command::new("xattr")
            .args(["-w", "com.example.profile-lifecycle-test", "x"])
            // After the exchange, `right` names P while `right_fd` still
            // pins Z (now named by `left`).
            .arg(&right)
            .status()
            .unwrap();
        assert!(status.success());
        assert!(matches!(
            darwin_safe_fd_real_ignoring_sandbox_provenance(&right_fd),
            Ok(())
        ));
        let right_after = open_rw(&right).unwrap();
        assert!(matches!(
            darwin_safe_fd_real_ignoring_sandbox_provenance(&right_after),
            Err(ProfileLifecycleError::Quarantined)
        ));
    }
    #[test]
    fn baseline_is_fixed_and_canonical() {
        let (_t, s) = storage();
        initialize_with_platform(&s, &FakePlatform).unwrap();
        let a = fs::read(s.path().join("profile/lifecycle/receipt.a.json")).unwrap();
        assert!(!a.ends_with(b"\n"));
        assert!(matches!(
            read_slot(&s.path().join("profile/lifecycle/receipt.a.json")).unwrap(),
            SlotRead::Valid(_, _)
        ));
        let auth = authority(&s).unwrap();
        assert!(matches!(auth.payload, Payload::Baseline { .. }));
    }
    #[test]
    fn explicit_null_and_unknown_fields_are_refused() {
        let (_t, s) = storage();
        initialize_with_platform(&s, &FakePlatform).unwrap();
        let p = s.path().join("profile/lifecycle/receipt.a.json");
        let mut v: Value = serde_json::from_slice(&fs::read(&p).unwrap()).unwrap();
        v["payload"]["live"] = Value::Null;
        fs::write(&p, serde_json::to_vec(&v).unwrap()).unwrap();
        assert!(matches!(
            authority(&s),
            Err(ProfileLifecycleError::Quarantined)
        ));
    }
    #[test]
    fn reset_uses_fixed_slots_and_recovers_each_data_transition() {
        let (_t, s) = storage();
        let live = s.path().join("profile/voiceprint.json");
        fs::write(&live, b"bad but removable profile").unwrap();
        fs::set_permissions(&live, fs::Permissions::from_mode(0o600)).unwrap();
        let c = MeetingStorageCoordination::default();
        let id = "123e4567-e89b-12d3-a456-426614174000";
        let e = reset_with_platform(
            &s,
            &c,
            ProfileResetRequest {
                operation_id: id,
                requested_at_epoch_seconds: 1,
                completed_at_epoch_seconds: 2,
                fail_after: Some(InjectedFailurePhase::Swap),
            },
            &FakePlatform,
        )
        .unwrap_err();
        assert!(
            matches!(e, ProfileLifecycleError::InjectedInterruption),
            "unexpected reset error: {e:?}"
        );
        let got = recover_with_platform(&s, &c, 2, &FakePlatform)
            .unwrap()
            .unwrap();
        assert!(matches!(got, ProfileResetOutcome::RecoveredRemoval { .. }));
        assert_eq!(fs::metadata(live).unwrap().len(), 0);
        let a = authority(&s).unwrap();
        assert!(matches!(
            a.payload,
            Payload::ResetRemoved {
                completed_count: 1,
                ..
            }
        ));
    }
    #[test]
    fn every_reset_crash_row_converges_without_unlinking_a_data_slot() {
        for failure in [
            InjectedFailurePhase::Deleting,
            InjectedFailurePhase::Swap,
            InjectedFailurePhase::Staged,
            InjectedFailurePhase::Truncate,
        ] {
            let (_t, s) = storage();
            let live = s.path().join("profile/voiceprint.json");
            fs::write(&live, b"semantically-invalid-but-safe").unwrap();
            fs::set_permissions(&live, fs::Permissions::from_mode(0o600)).unwrap();
            let c = MeetingStorageCoordination::default();
            let id = "123e4567-e89b-12d3-a456-426614174000";
            assert!(matches!(
                reset_with_platform(
                    &s,
                    &c,
                    ProfileResetRequest {
                        operation_id: id,
                        requested_at_epoch_seconds: 1,
                        completed_at_epoch_seconds: 2,
                        fail_after: Some(failure),
                    },
                    &FakePlatform,
                ),
                Err(ProfileLifecycleError::InjectedInterruption)
            ));
            assert!(matches!(
                recover_with_platform(&s, &c, 2, &FakePlatform),
                Ok(Some(ProfileResetOutcome::RecoveredRemoval { .. }))
            ));
            assert_eq!(fs::metadata(&live).unwrap().len(), 0);
            assert_eq!(
                fs::metadata(s.path().join("profile/lifecycle/reset.tombstone"))
                    .unwrap()
                    .len(),
                0
            );
            assert!(matches!(
                authority(&s).unwrap().payload,
                Payload::ResetRemoved { .. }
            ));
        }
    }
    #[test]
    fn reset_posttruncate_refuses_a_different_zero_inode() {
        let (_t, s) = storage();
        let live = s.path().join("profile/voiceprint.json");
        fs::write(&live, b"safe profile bytes").unwrap();
        fs::set_permissions(&live, fs::Permissions::from_mode(0o600)).unwrap();
        let c = MeetingStorageCoordination::default();
        assert!(matches!(
            reset_with_platform(
                &s,
                &c,
                ProfileResetRequest {
                    operation_id: "123e4567-e89b-12d3-a456-426614174000",
                    requested_at_epoch_seconds: 1,
                    completed_at_epoch_seconds: 2,
                    fail_after: Some(InjectedFailurePhase::Swap),
                },
                &FakePlatform,
            ),
            Err(ProfileLifecycleError::InjectedInterruption)
        ));
        let lifecycle = s.path().join("profile/lifecycle");
        let reset = lifecycle.join("reset.tombstone");
        let replacement = lifecycle.join("replacement-zero");
        create_zero(&replacement).unwrap();
        fs::rename(&replacement, &reset).unwrap();
        assert!(matches!(
            authority(&s),
            Err(ProfileLifecycleError::Quarantined)
        ));
    }
    #[test]
    fn unsafe_hard_link_and_two_torn_slots_quarantine() {
        let (_t, s) = storage();
        initialize_with_platform(&s, &FakePlatform).unwrap();
        let live = s.path().join("profile/voiceprint.json");
        let extra = s.path().join("profile/extra");
        fs::hard_link(&live, &extra).unwrap();
        assert!(matches!(
            authority(&s),
            Err(ProfileLifecycleError::Quarantined)
        ));
        fs::remove_file(extra).unwrap();
        for n in [RECEIPT_A, RECEIPT_B] {
            fs::write(s.path().join("profile/lifecycle").join(n), b"{").unwrap();
        }
        assert!(matches!(
            authority(&s),
            Err(ProfileLifecycleError::Quarantined)
        ));
    }
    #[test]
    fn enrollment_authority_refuses_reset() {
        let (_t, s) = storage();
        initialize_with_platform(&s, &FakePlatform).unwrap();
        let a = authority(&s).unwrap();
        let (live, reset, enroll) = slots_for_terminal(&a.payload).unwrap();
        let p = Payload::EnrollmentWriting {
            sequence: 1,
            predecessor: a.digest,
            operation_id: "123e4567-e89b-12d3-a456-426614174000".into(),
            requested_at: 1,
            prior_count: 0,
            prior_last: None,
            live_zero: live,
            reset_zero: reset,
            enrollment_zero: enroll,
        };
        publish(&s, &p).unwrap();
        let c = MeetingStorageCoordination::default();
        assert!(matches!(
            reset_with_platform(
                &s,
                &c,
                ProfileResetRequest {
                    operation_id: "123e4567-e89b-12d3-a456-426614174001",
                    requested_at_epoch_seconds: 1,
                    completed_at_epoch_seconds: 2,
                    fail_after: None
                },
                &FakePlatform
            ),
            Err(ProfileLifecycleError::NonterminalEnrollment)
        ));
    }
    #[test]
    fn one_torn_peer_is_ignored_but_the_untouched_third_slot_is_authority() {
        let (_t, s) = storage();
        initialize_with_platform(&s, &FakePlatform).unwrap();
        fs::write(s.path().join("profile/lifecycle/receipt.b.json"), b"{").unwrap();
        assert!(matches!(
            authority(&s).unwrap().payload,
            Payload::Baseline { .. }
        ));
        fs::write(
            s.path().join("profile/lifecycle/enrollment.staged"),
            b"drift",
        )
        .unwrap();
        let c = MeetingStorageCoordination::default();
        assert!(matches!(
            reset_with_platform(
                &s,
                &c,
                ProfileResetRequest {
                    operation_id: "123e4567-e89b-12d3-a456-426614174000",
                    requested_at_epoch_seconds: 1,
                    completed_at_epoch_seconds: 2,
                    fail_after: None,
                },
                &FakePlatform,
            ),
            Err(ProfileLifecycleError::Quarantined)
        ));
    }
    #[test]
    fn active_enrollment_is_current_profile_authority_and_can_reset() {
        let (_t, s) = storage();
        let live = s.path().join("profile/voiceprint.json");
        fs::write(&live, b"enrolled bytes").unwrap();
        fs::set_permissions(&live, fs::Permissions::from_mode(0o600)).unwrap();
        initialize_with_platform(&s, &FakePlatform).unwrap();
        let baseline = authority(&s).unwrap();
        let (live_profile, reset_zero, enrollment_zero) =
            slots_for_terminal(&baseline.payload).unwrap();
        let active = Payload::EnrollmentActive {
            sequence: 1,
            predecessor: baseline.digest,
            operation_id: "123e4567-e89b-12d3-a456-426614174000".into(),
            requested_at: 1,
            completed_at: 2,
            prior_count: 0,
            prior_last: None,
            live_profile,
            reset_zero,
            enrollment_zero,
        };
        publish(&s, &active).unwrap();
        assert!(matches!(
            authority(&s).unwrap().payload,
            Payload::EnrollmentActive { .. }
        ));
        let c = MeetingStorageCoordination::default();
        assert!(matches!(
            reset_with_platform(
                &s,
                &c,
                ProfileResetRequest {
                    operation_id: "123e4567-e89b-12d3-a456-426614174001",
                    requested_at_epoch_seconds: 3,
                    completed_at_epoch_seconds: 4,
                    fail_after: None,
                },
                &FakePlatform,
            ),
            Ok(ProfileResetOutcome::Removed { .. })
        ));
    }
    #[test]
    fn unsafe_leaf_mode_symlink_and_published_layout_are_quarantined() {
        let (_t, s) = storage();
        initialize_with_platform(&s, &FakePlatform).unwrap();
        let live = s.path().join("profile/voiceprint.json");
        fs::set_permissions(&live, fs::Permissions::from_mode(0o644)).unwrap();
        assert!(matches!(
            authority(&s),
            Err(ProfileLifecycleError::Quarantined)
        ));
        fs::set_permissions(&live, fs::Permissions::from_mode(0o600)).unwrap();
        fs::remove_file(&live).unwrap();
        std::os::unix::fs::symlink("/tmp/not-a-profile", &live).unwrap();
        assert!(matches!(
            authority(&s),
            Err(ProfileLifecycleError::Quarantined)
        ));
        let (_t, second) = storage();
        fs::create_dir(second.path().join("profile/lifecycle")).unwrap();
        assert!(matches!(
            initialize_with_platform(&second, &FakePlatform),
            Err(ProfileLifecycleError::Quarantined)
        ));
    }
}

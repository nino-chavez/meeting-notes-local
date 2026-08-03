//! Fixed-slot profile lifecycle journal.
//!
//! This module establishes and reopens the durable sequence-zero baseline,
//! preserves ambiguous legacy bytes only after an explicit review action, and
//! owns the crash-recoverable fixed-slot reset transition. Guided enrollment
//! reuses the same journal in the next vertical increment.

#![cfg(target_os = "macos")]

use std::io;
use std::time::{SystemTime, UNIX_EPOCH};

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use thiserror::Error;
use uuid::Uuid;

use crate::storage::{
    BoundPrivateDirectory, BoundPrivateFile, PrivateObjectIdentity, PrivateObjectObservation,
};

const LIVE_NAME: &str = "voiceprint.json";
const LIFECYCLE_NAME: &str = "lifecycle";
const INITIALIZING_NAME: &str = ".lifecycle.initializing";
const RECEIPT_A_NAME: &str = "receipt.a.json";
const RECEIPT_B_NAME: &str = "receipt.b.json";
const RESET_NAME: &str = "reset.tombstone";
const ENROLLMENT_NAME: &str = "enrollment.staged";
const RECEIPT_MAX_BYTES: u64 = 16_384;
const PROFILE_MAX_BYTES: u64 = 4 * 1024 * 1024;
const ZERO_SHA256: &str = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855";
const FIXED_NAMES: [&str; 4] = [ENROLLMENT_NAME, RECEIPT_A_NAME, RECEIPT_B_NAME, RESET_NAME];

#[derive(Debug, Error)]
pub enum ProfileLifecycleError {
    #[error("profile lifecycle is quarantined")]
    Quarantined,
    #[error("profile lifecycle initialization is ambiguous and requires migration review")]
    MigrationReviewRequired,
    #[error("profile lifecycle operation identifier is invalid")]
    InvalidOperationId,
    #[error("profile lifecycle receipt sequence overflowed")]
    SequenceOverflow,
    #[error("profile lifecycle reset count overflowed")]
    ResetCountOverflow,
    #[error("profile lifecycle volume does not support atomic file swap")]
    SwapUnsupported,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ProfileResetOutcome {
    AlreadyAbsent,
    Removed {
        operation_id: String,
        completed_reset_count: u64,
    },
    Recovered {
        operation_id: String,
        completed_reset_count: u64,
    },
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ProfileLifecycleBaseline {
    receipt_sequence: u64,
    completed_reset_count: u64,
    profile_size: u64,
    profile_sha256: String,
}

impl ProfileLifecycleBaseline {
    pub fn receipt_sequence(&self) -> u64 {
        self.receipt_sequence
    }

    pub fn completed_reset_count(&self) -> u64 {
        self.completed_reset_count
    }

    pub fn profile_present(&self) -> bool {
        self.profile_size != 0
    }

    pub fn profile_size(&self) -> u64 {
        self.profile_size
    }

    pub fn profile_sha256(&self) -> &str {
        &self.profile_sha256
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct ProfileSlot {
    identity: IdentityReceipt,
    size: u64,
    sha256: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct IdentityReceipt {
    device: u64,
    inode: u64,
    generation: u64,
    birth_seconds: u64,
    birth_nanoseconds: u32,
    owner: u32,
    mode: u32,
    link_count: u64,
    flags: u32,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct BaselinePayload {
    schema: String,
    receipt_sequence: u64,
    operation: String,
    phase: String,
    completed_reset_count: u64,
    live: ProfileSlot,
    reset_slot: ProfileSlot,
    enrollment_slot: ProfileSlot,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct LastReset {
    operation_id: String,
    completed_at: u64,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct ResetPendingPayload {
    schema: String,
    receipt_sequence: u64,
    operation: String,
    phase: String,
    predecessor_payload_sha256: String,
    operation_id: String,
    requested_at: u64,
    prior_completed_reset_count: u64,
    #[serde(skip_serializing_if = "Option::is_none")]
    prior_last_reset: Option<LastReset>,
    profile: ProfileSlot,
    reset_zero: ProfileSlot,
    enrollment_zero: ProfileSlot,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct ResetRemovedPayload {
    schema: String,
    receipt_sequence: u64,
    operation: String,
    phase: String,
    predecessor_payload_sha256: String,
    completed_reset_count: u64,
    last_reset: LastReset,
    live_zero: ProfileSlot,
    reset_zero: ProfileSlot,
    enrollment_zero: ProfileSlot,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(untagged)]
enum LifecyclePayload {
    Baseline(BaselinePayload),
    ResetPending(ResetPendingPayload),
    ResetRemoved(ResetRemovedPayload),
}

impl LifecyclePayload {
    fn receipt_sequence(&self) -> u64 {
        match self {
            Self::Baseline(payload) => payload.receipt_sequence,
            Self::ResetPending(payload) => payload.receipt_sequence,
            Self::ResetRemoved(payload) => payload.receipt_sequence,
        }
    }

    fn predecessor_payload_sha256(&self) -> Option<&str> {
        match self {
            Self::Baseline(_) => None,
            Self::ResetPending(payload) => Some(&payload.predecessor_payload_sha256),
            Self::ResetRemoved(payload) => Some(&payload.predecessor_payload_sha256),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct LifecycleEnvelope {
    schema: String,
    payload_sha256: String,
    payload: LifecyclePayload,
}

#[derive(Debug, Clone)]
struct ReceiptAuthority {
    payload: LifecyclePayload,
    payload_sha256: String,
    slot: ReceiptSlot,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum ReceiptSlot {
    A,
    B,
}

pub(crate) fn initialize_profile_lifecycle_bound(
    app_data: &BoundPrivateDirectory,
) -> Result<ProfileLifecycleBaseline, ProfileLifecycleError> {
    let profile = app_data.open_directory("profile").map_err(quarantine_io)?;
    let result = initialize_bound_profile(&profile);
    if app_data.revalidate().is_err() || profile.revalidate().is_err() {
        return Err(ProfileLifecycleError::Quarantined);
    }
    result
}

pub(crate) fn preserve_legacy_profile_bound(
    app_data: &BoundPrivateDirectory,
) -> Result<ProfileLifecycleBaseline, ProfileLifecycleError> {
    let profile = app_data.open_directory("profile").map_err(quarantine_io)?;
    let result = preserve_legacy_bound_profile(&profile);
    if app_data.revalidate().is_err() || profile.revalidate().is_err() {
        return Err(ProfileLifecycleError::Quarantined);
    }
    result
}

pub(crate) fn reset_profile_lifecycle_bound(
    app_data: &BoundPrivateDirectory,
    operation_id: &str,
    requested_at: u64,
) -> Result<ProfileResetOutcome, ProfileLifecycleError> {
    if !canonical_uuid(operation_id) {
        return Err(ProfileLifecycleError::InvalidOperationId);
    }
    let profile = app_data.open_directory("profile").map_err(quarantine_io)?;
    let result = reset_bound_profile(&profile, operation_id, requested_at);
    if app_data.revalidate().is_err() || profile.revalidate().is_err() {
        return Err(ProfileLifecycleError::Quarantined);
    }
    result
}

fn initialize_bound_profile(
    profile: &BoundPrivateDirectory,
) -> Result<ProfileLifecycleBaseline, ProfileLifecycleError> {
    match profile.open_directory(LIFECYCLE_NAME) {
        Ok(lifecycle) => {
            match profile.open_directory(INITIALIZING_NAME) {
                Err(error) if error.kind() == io::ErrorKind::NotFound => {}
                _ => return Err(ProfileLifecycleError::Quarantined),
            }
            let live = profile
                .open_file(LIVE_NAME, true, PROFILE_MAX_BYTES)
                .map_err(quarantine_io)?;
            validate_or_recover_published(profile, live, &lifecycle)
        }
        Err(error) if error.kind() == io::ErrorKind::NotFound => {
            let initializing = match profile.open_directory(INITIALIZING_NAME) {
                Ok(directory) => directory,
                Err(error) if error.kind() == io::ErrorKind::NotFound => {
                    match profile.open_file(LIVE_NAME, true, PROFILE_MAX_BYTES) {
                        Ok(_) => return Err(ProfileLifecycleError::MigrationReviewRequired),
                        Err(error) if error.kind() == io::ErrorKind::NotFound => profile
                            .create_directory(INITIALIZING_NAME)
                            .map_err(quarantine_io)?,
                        Err(error) => return Err(quarantine_io(error)),
                    }
                }
                Err(error) => return Err(quarantine_io(error)),
            };
            let live = match profile.open_file(LIVE_NAME, true, PROFILE_MAX_BYTES) {
                Ok(file) => file,
                Err(error) if error.kind() == io::ErrorKind::NotFound => {
                    profile.create_zero_file(LIVE_NAME).map_err(quarantine_io)?
                }
                Err(error) => return Err(quarantine_io(error)),
            };
            publish_initializing(profile, &live, initializing, false)
        }
        Err(error) => Err(quarantine_io(error)),
    }
}

fn preserve_legacy_bound_profile(
    profile: &BoundPrivateDirectory,
) -> Result<ProfileLifecycleBaseline, ProfileLifecycleError> {
    match profile.open_directory(LIFECYCLE_NAME) {
        Ok(_) => initialize_bound_profile(profile),
        Err(error) if error.kind() == io::ErrorKind::NotFound => {
            let live = profile
                .open_file(LIVE_NAME, true, PROFILE_MAX_BYTES)
                .map_err(quarantine_io)?;
            let initializing = match profile.open_directory(INITIALIZING_NAME) {
                Ok(directory) => directory,
                Err(error) if error.kind() == io::ErrorKind::NotFound => profile
                    .create_directory(INITIALIZING_NAME)
                    .map_err(quarantine_io)?,
                Err(error) => return Err(quarantine_io(error)),
            };
            publish_initializing(profile, &live, initializing, true)
        }
        Err(error) => Err(quarantine_io(error)),
    }
}

fn publish_initializing(
    profile: &BoundPrivateDirectory,
    live: &BoundPrivateFile,
    initializing: BoundPrivateDirectory,
    allow_unreceipted_nonzero_live: bool,
) -> Result<ProfileLifecycleBaseline, ProfileLifecycleError> {
    prepare_initializing(profile, live, &initializing, allow_unreceipted_nonzero_live)?;
    let lifecycle = profile
        .publish_directory_exclusive(initializing, INITIALIZING_NAME, LIFECYCLE_NAME)
        .map_err(quarantine_io)?;
    let live = profile
        .open_file(LIVE_NAME, true, PROFILE_MAX_BYTES)
        .map_err(quarantine_io)?;
    validate_or_recover_published(profile, live, &lifecycle)
}

fn prepare_initializing(
    profile: &BoundPrivateDirectory,
    live: &BoundPrivateFile,
    initializing: &BoundPrivateDirectory,
    allow_unreceipted_nonzero_live: bool,
) -> Result<(), ProfileLifecycleError> {
    let names = initializing.child_names().map_err(quarantine_io)?;
    if names
        .iter()
        .any(|name| !FIXED_NAMES.contains(&name.as_str()))
    {
        return Err(ProfileLifecycleError::Quarantined);
    }
    let live_observation = live
        .identity(profile, PROFILE_MAX_BYTES)
        .map_err(quarantine_io)?;
    if !allow_unreceipted_nonzero_live && live_observation.size != 0 {
        let receipt_a = match initializing.open_file(RECEIPT_A_NAME, false, RECEIPT_MAX_BYTES) {
            Ok(receipt) => receipt,
            Err(error) if error.kind() == io::ErrorKind::NotFound => {
                return Err(ProfileLifecycleError::MigrationReviewRequired);
            }
            Err(error) => return Err(quarantine_io(error)),
        };
        if receipt_a
            .read_all(initializing, RECEIPT_MAX_BYTES)
            .map_err(quarantine_io)?
            .is_empty()
        {
            return Err(ProfileLifecycleError::MigrationReviewRequired);
        }
    }
    for name in FIXED_NAMES {
        if !names.iter().any(|existing| existing == name) {
            initializing.create_zero_file(name).map_err(quarantine_io)?;
        }
    }

    let receipt_a = initializing
        .open_file(RECEIPT_A_NAME, true, RECEIPT_MAX_BYTES)
        .map_err(quarantine_io)?;
    let receipt_b = initializing
        .open_file(RECEIPT_B_NAME, true, RECEIPT_MAX_BYTES)
        .map_err(quarantine_io)?;
    let reset = initializing
        .open_file(RESET_NAME, true, 0)
        .map_err(quarantine_io)?;
    let enrollment = initializing
        .open_file(ENROLLMENT_NAME, true, 0)
        .map_err(quarantine_io)?;
    let payload = baseline_payload(profile, live, initializing, &reset, &enrollment)?;
    let expected = encode_envelope(payload)?;
    let a_bytes = receipt_a
        .read_all(initializing, RECEIPT_MAX_BYTES)
        .map_err(quarantine_io)?;
    let b_bytes = receipt_b
        .read_all(initializing, RECEIPT_MAX_BYTES)
        .map_err(quarantine_io)?;
    if !b_bytes.is_empty() {
        return Err(ProfileLifecycleError::Quarantined);
    }
    if a_bytes.is_empty() {
        receipt_a
            .replace_bytes(initializing, &expected, RECEIPT_MAX_BYTES)
            .map_err(quarantine_io)?;
    } else if a_bytes != expected || decode_envelope(&a_bytes).is_err() {
        return Err(ProfileLifecycleError::Quarantined);
    }
    initializing.sync_all().map_err(quarantine_io)?;
    Ok(())
}

fn validate_or_recover_published(
    profile: &BoundPrivateDirectory,
    live: BoundPrivateFile,
    lifecycle: &BoundPrivateDirectory,
) -> Result<ProfileLifecycleBaseline, ProfileLifecycleError> {
    if lifecycle.child_names().map_err(quarantine_io)? != FIXED_NAMES {
        return Err(ProfileLifecycleError::Quarantined);
    }
    let receipt_a = lifecycle
        .open_file(RECEIPT_A_NAME, true, RECEIPT_MAX_BYTES)
        .map_err(quarantine_io)?;
    let receipt_b = lifecycle
        .open_file(RECEIPT_B_NAME, true, RECEIPT_MAX_BYTES)
        .map_err(quarantine_io)?;
    let reset = lifecycle
        .open_file(RESET_NAME, true, PROFILE_MAX_BYTES)
        .map_err(quarantine_io)?;
    let enrollment = lifecycle
        .open_file(ENROLLMENT_NAME, false, 0)
        .map_err(quarantine_io)?;
    let authority = select_receipt_authority(lifecycle, &receipt_a, &receipt_b)?;
    match authority.payload.clone() {
        LifecyclePayload::Baseline(payload) => {
            let expected = baseline_payload(profile, &live, lifecycle, &reset, &enrollment)?;
            if payload != expected {
                return Err(ProfileLifecycleError::Quarantined);
            }
            Ok(status_from_baseline(&payload))
        }
        LifecyclePayload::ResetRemoved(payload) => {
            validate_removed_layout(profile, &live, lifecycle, &reset, &enrollment, &payload)?;
            Ok(status_from_removed(&payload))
        }
        LifecyclePayload::ResetPending(payload) => recover_reset(
            profile,
            live,
            lifecycle,
            reset,
            &enrollment,
            receipt_a,
            receipt_b,
            authority,
            payload,
            true,
        )
        .map(|(_, status)| status),
    }
}

fn select_receipt_authority(
    lifecycle: &BoundPrivateDirectory,
    receipt_a: &BoundPrivateFile,
    receipt_b: &BoundPrivateFile,
) -> Result<ReceiptAuthority, ProfileLifecycleError> {
    let mut valid = Vec::new();
    for (slot, receipt) in [(ReceiptSlot::A, receipt_a), (ReceiptSlot::B, receipt_b)] {
        let bytes = receipt
            .read_all(lifecycle, RECEIPT_MAX_BYTES)
            .map_err(quarantine_io)?;
        if bytes.is_empty() {
            continue;
        }
        match decode_lifecycle_envelope(&bytes) {
            Ok((payload, payload_sha256)) => valid.push(ReceiptAuthority {
                payload,
                payload_sha256,
                slot,
            }),
            Err(_) if is_self_consistent_unsupported_receipt(&bytes) => {
                return Err(ProfileLifecycleError::Quarantined);
            }
            Err(_) => {}
        }
    }
    match valid.len() {
        1 => Ok(valid.remove(0)),
        2 => {
            valid.sort_by_key(|authority| authority.payload.receipt_sequence());
            let older = &valid[0];
            let newer = &valid[1];
            if older.payload.receipt_sequence() == newer.payload.receipt_sequence()
                || older.payload.receipt_sequence().checked_add(1)
                    != Some(newer.payload.receipt_sequence())
                || newer.payload.predecessor_payload_sha256() != Some(older.payload_sha256.as_str())
            {
                return Err(ProfileLifecycleError::Quarantined);
            }
            Ok(valid.remove(1))
        }
        _ => Err(ProfileLifecycleError::Quarantined),
    }
}

fn status_from_baseline(payload: &BaselinePayload) -> ProfileLifecycleBaseline {
    ProfileLifecycleBaseline {
        receipt_sequence: payload.receipt_sequence,
        completed_reset_count: payload.completed_reset_count,
        profile_size: payload.live.size,
        profile_sha256: payload.live.sha256.clone(),
    }
}

fn status_from_removed(payload: &ResetRemovedPayload) -> ProfileLifecycleBaseline {
    ProfileLifecycleBaseline {
        receipt_sequence: payload.receipt_sequence,
        completed_reset_count: payload.completed_reset_count,
        profile_size: 0,
        profile_sha256: ZERO_SHA256.into(),
    }
}

fn validate_removed_layout(
    profile: &BoundPrivateDirectory,
    live: &BoundPrivateFile,
    lifecycle: &BoundPrivateDirectory,
    reset: &BoundPrivateFile,
    enrollment: &BoundPrivateFile,
    payload: &ResetRemovedPayload,
) -> Result<(), ProfileLifecycleError> {
    if payload.completed_reset_count == 0
        || !canonical_uuid(&payload.last_reset.operation_id)
        || observe_slot(profile, live, 0)? != payload.live_zero
        || observe_slot(lifecycle, reset, 0)? != payload.reset_zero
        || observe_slot(lifecycle, enrollment, 0)? != payload.enrollment_zero
        || !slot_is_zero(&payload.live_zero)
        || !slot_is_zero(&payload.reset_zero)
        || !slot_is_zero(&payload.enrollment_zero)
    {
        return Err(ProfileLifecycleError::Quarantined);
    }
    Ok(())
}

fn reset_bound_profile(
    profile: &BoundPrivateDirectory,
    operation_id: &str,
    requested_at: u64,
) -> Result<ProfileResetOutcome, ProfileLifecycleError> {
    match profile.open_directory(INITIALIZING_NAME) {
        Err(error) if error.kind() == io::ErrorKind::NotFound => {}
        _ => return Err(ProfileLifecycleError::Quarantined),
    }
    let lifecycle = profile
        .open_directory(LIFECYCLE_NAME)
        .map_err(quarantine_io)?;
    if lifecycle.child_names().map_err(quarantine_io)? != FIXED_NAMES {
        return Err(ProfileLifecycleError::Quarantined);
    }
    let live = profile
        .open_file(LIVE_NAME, true, PROFILE_MAX_BYTES)
        .map_err(quarantine_io)?;
    let receipt_a = lifecycle
        .open_file(RECEIPT_A_NAME, true, RECEIPT_MAX_BYTES)
        .map_err(quarantine_io)?;
    let receipt_b = lifecycle
        .open_file(RECEIPT_B_NAME, true, RECEIPT_MAX_BYTES)
        .map_err(quarantine_io)?;
    let reset = lifecycle
        .open_file(RESET_NAME, true, PROFILE_MAX_BYTES)
        .map_err(quarantine_io)?;
    let enrollment = lifecycle
        .open_file(ENROLLMENT_NAME, false, 0)
        .map_err(quarantine_io)?;
    let authority = select_receipt_authority(&lifecycle, &receipt_a, &receipt_b)?;

    match authority.payload.clone() {
        LifecyclePayload::Baseline(payload) => {
            let expected = baseline_payload(profile, &live, &lifecycle, &reset, &enrollment)?;
            if payload != expected {
                return Err(ProfileLifecycleError::Quarantined);
            }
            if !payload.live.size.eq(&0) {
                profile
                    .require_file_swap()
                    .map_err(|_| ProfileLifecycleError::SwapUnsupported)?;
                let pending = ResetPendingPayload {
                    schema: "profile-lifecycle/1".into(),
                    receipt_sequence: next_sequence(payload.receipt_sequence)?,
                    operation: "reset".into(),
                    phase: "deleting".into(),
                    predecessor_payload_sha256: authority.payload_sha256.clone(),
                    operation_id: operation_id.into(),
                    requested_at,
                    prior_completed_reset_count: payload.completed_reset_count,
                    prior_last_reset: None,
                    profile: payload.live,
                    reset_zero: payload.reset_slot,
                    enrollment_zero: payload.enrollment_slot,
                };
                let authority = publish_payload(
                    &lifecycle,
                    &receipt_a,
                    &receipt_b,
                    &authority,
                    LifecyclePayload::ResetPending(pending.clone()),
                )?;
                recover_reset(
                    profile,
                    live,
                    &lifecycle,
                    reset,
                    &enrollment,
                    receipt_a,
                    receipt_b,
                    authority,
                    pending,
                    false,
                )
                .map(|(outcome, _)| outcome)
            } else {
                Ok(ProfileResetOutcome::AlreadyAbsent)
            }
        }
        LifecyclePayload::ResetRemoved(payload) => {
            validate_removed_layout(profile, &live, &lifecycle, &reset, &enrollment, &payload)?;
            Ok(ProfileResetOutcome::AlreadyAbsent)
        }
        LifecyclePayload::ResetPending(payload) => recover_reset(
            profile,
            live,
            &lifecycle,
            reset,
            &enrollment,
            receipt_a,
            receipt_b,
            authority,
            payload,
            true,
        )
        .map(|(outcome, _)| outcome),
    }
}

#[allow(clippy::too_many_arguments)]
fn recover_reset(
    profile: &BoundPrivateDirectory,
    mut live: BoundPrivateFile,
    lifecycle: &BoundPrivateDirectory,
    mut reset: BoundPrivateFile,
    enrollment: &BoundPrivateFile,
    receipt_a: BoundPrivateFile,
    receipt_b: BoundPrivateFile,
    mut authority: ReceiptAuthority,
    mut pending: ResetPendingPayload,
    recovered: bool,
) -> Result<(ProfileResetOutcome, ProfileLifecycleBaseline), ProfileLifecycleError> {
    validate_reset_pending(&pending)?;
    let enrollment_now = observe_slot(lifecycle, enrollment, 0)?;
    if enrollment_now != pending.enrollment_zero || !slot_is_zero(&enrollment_now) {
        return Err(ProfileLifecycleError::Quarantined);
    }

    let mut live_now = observe_slot(profile, &live, PROFILE_MAX_BYTES)?;
    let mut reset_now = observe_slot(lifecycle, &reset, PROFILE_MAX_BYTES)?;
    let pre_swap = live_now == pending.profile && reset_now == pending.reset_zero;
    let post_swap = live_now == pending.reset_zero && reset_now == pending.profile;
    let post_truncate =
        live_now == pending.reset_zero && slot_is_zeroed_version_of(&reset_now, &pending.profile);
    if !pre_swap && !post_swap && !post_truncate {
        return Err(ProfileLifecycleError::Quarantined);
    }
    if pending.phase == "staged" && pre_swap {
        return Err(ProfileLifecycleError::Quarantined);
    }

    if pre_swap {
        profile
            .require_file_swap()
            .map_err(|_| ProfileLifecycleError::SwapUnsupported)?;
        let (profile_at_reset, zero_at_live) = profile
            .swap_files(live, PROFILE_MAX_BYTES, lifecycle, reset, 0)
            .map_err(quarantine_io)?;
        live = zero_at_live;
        reset = profile_at_reset;
        live_now = observe_slot(profile, &live, 0)?;
        reset_now = observe_slot(lifecycle, &reset, PROFILE_MAX_BYTES)?;
        if live_now != pending.reset_zero || reset_now != pending.profile {
            return Err(ProfileLifecycleError::Quarantined);
        }
    }

    if !post_truncate && pending.phase == "deleting" {
        let staged = ResetPendingPayload {
            receipt_sequence: next_sequence(pending.receipt_sequence)?,
            phase: "staged".into(),
            predecessor_payload_sha256: authority.payload_sha256.clone(),
            ..pending.clone()
        };
        authority = publish_payload(
            lifecycle,
            &receipt_a,
            &receipt_b,
            &authority,
            LifecyclePayload::ResetPending(staged.clone()),
        )?;
        pending = staged;
    }

    if !post_truncate {
        reset
            .replace_bytes(lifecycle, &[], PROFILE_MAX_BYTES)
            .map_err(quarantine_io)?;
        live_now = observe_slot(profile, &live, 0)?;
        reset_now = observe_slot(lifecycle, &reset, 0)?;
        if live_now != pending.reset_zero
            || !slot_is_zeroed_version_of(&reset_now, &pending.profile)
        {
            return Err(ProfileLifecycleError::Quarantined);
        }
    }

    let completed_reset_count = pending
        .prior_completed_reset_count
        .checked_add(1)
        .ok_or(ProfileLifecycleError::ResetCountOverflow)?;
    let removed = ResetRemovedPayload {
        schema: "profile-lifecycle/1".into(),
        receipt_sequence: next_sequence(authority.payload.receipt_sequence())?,
        operation: "reset".into(),
        phase: "removed".into(),
        predecessor_payload_sha256: authority.payload_sha256.clone(),
        completed_reset_count,
        last_reset: LastReset {
            operation_id: pending.operation_id.clone(),
            completed_at: epoch_seconds()?,
        },
        live_zero: live_now,
        reset_zero: reset_now,
        enrollment_zero: enrollment_now,
    };
    let authority = publish_payload(
        lifecycle,
        &receipt_a,
        &receipt_b,
        &authority,
        LifecyclePayload::ResetRemoved(removed.clone()),
    )?;
    validate_removed_layout(profile, &live, lifecycle, &reset, enrollment, &removed)?;
    let status = status_from_removed(&removed);
    if authority.payload.receipt_sequence() != status.receipt_sequence {
        return Err(ProfileLifecycleError::Quarantined);
    }
    let outcome = if recovered {
        ProfileResetOutcome::Recovered {
            operation_id: pending.operation_id,
            completed_reset_count,
        }
    } else {
        ProfileResetOutcome::Removed {
            operation_id: pending.operation_id,
            completed_reset_count,
        }
    };
    Ok((outcome, status))
}

fn publish_payload(
    lifecycle: &BoundPrivateDirectory,
    receipt_a: &BoundPrivateFile,
    receipt_b: &BoundPrivateFile,
    current: &ReceiptAuthority,
    payload: LifecyclePayload,
) -> Result<ReceiptAuthority, ProfileLifecycleError> {
    if payload.receipt_sequence()
        != current
            .payload
            .receipt_sequence()
            .checked_add(1)
            .ok_or(ProfileLifecycleError::SequenceOverflow)?
        || payload.predecessor_payload_sha256() != Some(current.payload_sha256.as_str())
    {
        return Err(ProfileLifecycleError::Quarantined);
    }
    let (slot, target) = match current.slot {
        ReceiptSlot::A => (ReceiptSlot::B, receipt_b),
        ReceiptSlot::B => (ReceiptSlot::A, receipt_a),
    };
    let bytes = encode_lifecycle_envelope(payload.clone())?;
    target
        .replace_bytes(lifecycle, &bytes, RECEIPT_MAX_BYTES)
        .map_err(quarantine_io)?;
    lifecycle.sync_all().map_err(quarantine_io)?;
    let written = target
        .read_all(lifecycle, RECEIPT_MAX_BYTES)
        .map_err(quarantine_io)?;
    let (decoded, payload_sha256) = decode_lifecycle_envelope(&written)?;
    if decoded != payload {
        return Err(ProfileLifecycleError::Quarantined);
    }
    Ok(ReceiptAuthority {
        payload,
        payload_sha256,
        slot,
    })
}

fn validate_reset_pending(payload: &ResetPendingPayload) -> Result<(), ProfileLifecycleError> {
    let last_reset_consistent = match (
        payload.prior_completed_reset_count,
        payload.prior_last_reset.as_ref(),
    ) {
        (0, None) => true,
        (0, Some(_)) | (_, None) => false,
        (_, Some(last)) => canonical_uuid(&last.operation_id),
    };
    if payload.schema != "profile-lifecycle/1"
        || payload.operation != "reset"
        || !matches!(payload.phase.as_str(), "deleting" | "staged")
        || !valid_sha256(&payload.predecessor_payload_sha256)
        || !canonical_uuid(&payload.operation_id)
        || !last_reset_consistent
        || !slot_is_zero(&payload.reset_zero)
        || !slot_is_zero(&payload.enrollment_zero)
        || payload.profile.size == 0
    {
        return Err(ProfileLifecycleError::Quarantined);
    }
    Ok(())
}

fn next_sequence(sequence: u64) -> Result<u64, ProfileLifecycleError> {
    sequence
        .checked_add(1)
        .ok_or(ProfileLifecycleError::SequenceOverflow)
}

fn slot_is_zero(slot: &ProfileSlot) -> bool {
    slot.size == 0 && slot.sha256 == ZERO_SHA256
}

fn slot_is_zeroed_version_of(current: &ProfileSlot, prior: &ProfileSlot) -> bool {
    current.identity == prior.identity && slot_is_zero(current)
}

fn canonical_uuid(value: &str) -> bool {
    Uuid::parse_str(value)
        .map(|uuid| uuid.to_string() == value)
        .unwrap_or(false)
}

fn valid_sha256(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn epoch_seconds() -> Result<u64, ProfileLifecycleError> {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_secs())
        .map_err(|_| ProfileLifecycleError::Quarantined)
}

fn baseline_payload(
    profile: &BoundPrivateDirectory,
    live: &BoundPrivateFile,
    lifecycle: &BoundPrivateDirectory,
    reset: &BoundPrivateFile,
    enrollment: &BoundPrivateFile,
) -> Result<BaselinePayload, ProfileLifecycleError> {
    let live = observe_slot(profile, live, PROFILE_MAX_BYTES)?;
    let reset_slot = observe_slot(lifecycle, reset, 0)?;
    let enrollment_slot = observe_slot(lifecycle, enrollment, 0)?;
    if live.identity.device != reset_slot.identity.device
        || live.identity.device != enrollment_slot.identity.device
        || live.identity.inode == reset_slot.identity.inode
        || live.identity.inode == enrollment_slot.identity.inode
        || reset_slot.identity.inode == enrollment_slot.identity.inode
        || reset_slot.size != 0
        || enrollment_slot.size != 0
        || reset_slot.sha256 != ZERO_SHA256
        || enrollment_slot.sha256 != ZERO_SHA256
    {
        return Err(ProfileLifecycleError::Quarantined);
    }
    Ok(BaselinePayload {
        schema: "profile-lifecycle/1".into(),
        receipt_sequence: 0,
        operation: "baseline".into(),
        phase: "ready".into(),
        completed_reset_count: 0,
        live,
        reset_slot,
        enrollment_slot,
    })
}

fn observe_slot(
    directory: &BoundPrivateDirectory,
    file: &BoundPrivateFile,
    max_bytes: u64,
) -> Result<ProfileSlot, ProfileLifecycleError> {
    let observation = file.identity(directory, max_bytes).map_err(quarantine_io)?;
    let bytes = file.read_all(directory, max_bytes).map_err(quarantine_io)?;
    Ok(ProfileSlot {
        identity: identity_receipt(observation),
        size: bytes.len() as u64,
        sha256: format!("{:x}", Sha256::digest(bytes)),
    })
}

fn identity_receipt(observation: PrivateObjectObservation) -> IdentityReceipt {
    let PrivateObjectIdentity {
        device,
        inode,
        generation,
        birth_seconds,
        birth_nanoseconds,
        owner,
        mode,
        link_count,
        flags,
    } = observation.identity;
    IdentityReceipt {
        device,
        inode,
        generation,
        birth_seconds,
        birth_nanoseconds,
        owner,
        mode,
        link_count,
        flags,
    }
}

fn encode_envelope(payload: BaselinePayload) -> Result<Vec<u8>, ProfileLifecycleError> {
    encode_lifecycle_envelope(LifecyclePayload::Baseline(payload))
}

fn encode_lifecycle_envelope(payload: LifecyclePayload) -> Result<Vec<u8>, ProfileLifecycleError> {
    let payload_bytes =
        serde_json::to_vec_pretty(&payload).map_err(|_| ProfileLifecycleError::Quarantined)?;
    let bytes = serde_json::to_vec_pretty(&LifecycleEnvelope {
        schema: "profile-lifecycle-slot/1".into(),
        payload_sha256: format!("{:x}", Sha256::digest(payload_bytes)),
        payload,
    })
    .map_err(|_| ProfileLifecycleError::Quarantined)?;
    if bytes.len() as u64 > RECEIPT_MAX_BYTES {
        return Err(ProfileLifecycleError::Quarantined);
    }
    Ok(bytes)
}

fn decode_envelope(bytes: &[u8]) -> Result<BaselinePayload, ProfileLifecycleError> {
    match decode_lifecycle_envelope(bytes)?.0 {
        LifecyclePayload::Baseline(payload) => Ok(payload),
        _ => Err(ProfileLifecycleError::Quarantined),
    }
}

fn decode_lifecycle_envelope(
    bytes: &[u8],
) -> Result<(LifecyclePayload, String), ProfileLifecycleError> {
    let envelope: LifecycleEnvelope =
        serde_json::from_slice(bytes).map_err(|_| ProfileLifecycleError::Quarantined)?;
    if envelope.schema != "profile-lifecycle-slot/1" || !valid_sha256(&envelope.payload_sha256) {
        return Err(ProfileLifecycleError::Quarantined);
    }
    match &envelope.payload {
        LifecyclePayload::Baseline(payload) => {
            if payload.schema != "profile-lifecycle/1"
                || payload.receipt_sequence != 0
                || payload.operation != "baseline"
                || payload.phase != "ready"
                || payload.completed_reset_count != 0
            {
                return Err(ProfileLifecycleError::Quarantined);
            }
        }
        LifecyclePayload::ResetPending(payload) => validate_reset_pending(payload)?,
        LifecyclePayload::ResetRemoved(payload) => {
            if payload.schema != "profile-lifecycle/1"
                || payload.operation != "reset"
                || payload.phase != "removed"
                || payload.completed_reset_count == 0
                || !valid_sha256(&payload.predecessor_payload_sha256)
                || !canonical_uuid(&payload.last_reset.operation_id)
                || !slot_is_zero(&payload.live_zero)
                || !slot_is_zero(&payload.reset_zero)
                || !slot_is_zero(&payload.enrollment_zero)
            {
                return Err(ProfileLifecycleError::Quarantined);
            }
        }
    }
    let payload_bytes = serde_json::to_vec_pretty(&envelope.payload)
        .map_err(|_| ProfileLifecycleError::Quarantined)?;
    if format!("{:x}", Sha256::digest(&payload_bytes)) != envelope.payload_sha256 {
        return Err(ProfileLifecycleError::Quarantined);
    }
    let canonical = encode_lifecycle_envelope(envelope.payload.clone())?;
    if canonical != bytes {
        return Err(ProfileLifecycleError::Quarantined);
    }
    Ok((envelope.payload, envelope.payload_sha256))
}

fn is_self_consistent_unsupported_receipt(bytes: &[u8]) -> bool {
    let Ok(document) = serde_json::from_slice::<serde_json::Value>(bytes) else {
        return false;
    };
    let Some(envelope) = document.as_object() else {
        return false;
    };
    let Some(schema) = envelope.get("schema").and_then(|value| value.as_str()) else {
        return false;
    };
    if schema.starts_with("profile-lifecycle-slot/") && schema != "profile-lifecycle-slot/1" {
        return true;
    }
    if schema != "profile-lifecycle-slot/1" {
        return false;
    }
    let Some(payload_sha256) = envelope
        .get("payload_sha256")
        .and_then(|value| value.as_str())
    else {
        return false;
    };
    if payload_sha256.len() != 64
        || !payload_sha256
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
    {
        return false;
    }
    let prefix = format!(
        "{{\n  \"schema\": \"profile-lifecycle-slot/1\",\n  \"payload_sha256\": \"{payload_sha256}\",\n  \"payload\": "
    );
    let Some(indented_payload) = bytes
        .strip_prefix(prefix.as_bytes())
        .and_then(|remainder| remainder.strip_suffix(b"\n}"))
    else {
        return false;
    };
    let Some(payload_bytes) = remove_envelope_indent(indented_payload) else {
        return false;
    };
    if format!("{:x}", Sha256::digest(&payload_bytes)) != payload_sha256 {
        return false;
    }
    let Ok(payload) = serde_json::from_slice::<serde_json::Value>(&payload_bytes) else {
        return false;
    };
    let Some(payload) = payload.as_object() else {
        return false;
    };
    let Some(payload_schema) = payload.get("schema").and_then(|value| value.as_str()) else {
        return false;
    };
    if payload_schema.starts_with("profile-lifecycle/") && payload_schema != "profile-lifecycle/1" {
        return true;
    }
    if payload_schema != "profile-lifecycle/1" {
        return false;
    }
    let Some(sequence) = payload
        .get("receipt_sequence")
        .and_then(|value| value.as_u64())
    else {
        return false;
    };
    let operation = payload.get("operation").and_then(|value| value.as_str());
    let phase = payload.get("phase").and_then(|value| value.as_str());
    sequence != 0 || operation != Some("baseline") || phase != Some("ready")
}

fn remove_envelope_indent(bytes: &[u8]) -> Option<Vec<u8>> {
    let mut output = Vec::with_capacity(bytes.len());
    for (index, line) in bytes.split(|byte| *byte == b'\n').enumerate() {
        if index != 0 {
            output.push(b'\n');
            output.extend_from_slice(line.strip_prefix(b"  ")?);
        } else {
            output.extend_from_slice(line);
        }
    }
    Some(output)
}

fn quarantine_io(_: io::Error) -> ProfileLifecycleError {
    ProfileLifecycleError::Quarantined
}

#[cfg(test)]
mod tests {
    use std::fs;
    use std::os::unix::fs::PermissionsExt;

    use tempfile::TempDir;

    use super::*;
    use crate::storage::{StorageRoot, create_private_dir, durable_create_new};

    fn initialize_profile_lifecycle(
        storage: &StorageRoot,
    ) -> Result<ProfileLifecycleBaseline, ProfileLifecycleError> {
        let app_data = BoundPrivateDirectory::open(storage.path()).map_err(quarantine_io)?;
        initialize_profile_lifecycle_bound(&app_data)
    }

    fn preserve_legacy_profile(
        storage: &StorageRoot,
    ) -> Result<ProfileLifecycleBaseline, ProfileLifecycleError> {
        let app_data = BoundPrivateDirectory::open(storage.path()).map_err(quarantine_io)?;
        preserve_legacy_profile_bound(&app_data)
    }

    fn reset_profile(storage: &StorageRoot) -> Result<ProfileResetOutcome, ProfileLifecycleError> {
        let app_data = BoundPrivateDirectory::open(storage.path()).map_err(quarantine_io)?;
        reset_profile_lifecycle_bound(&app_data, "123e4567-e89b-12d3-a456-426614174000", 10)
    }

    struct Fixture {
        _temp: TempDir,
        storage: StorageRoot,
    }

    impl Fixture {
        fn new() -> Self {
            let temp = TempDir::new().unwrap();
            let repo = temp.path().join("repo");
            create_private_dir(&repo).unwrap();
            let storage = StorageRoot::create(&temp.path().join("app"), &repo).unwrap();
            Self {
                _temp: temp,
                storage,
            }
        }

        fn profile(&self) -> std::path::PathBuf {
            self.storage.path().join("profile")
        }
    }

    #[test]
    fn initializes_zero_baseline_and_reopens_it_after_fresh_process() {
        let fixture = Fixture::new();
        let first = initialize_profile_lifecycle(&fixture.storage).unwrap();
        let second = initialize_profile_lifecycle(&fixture.storage).unwrap();
        assert_eq!(first, second);
        assert_eq!(first.receipt_sequence(), 0);
        assert_eq!(first.completed_reset_count(), 0);
        assert!(!first.profile_present());
        assert_eq!(first.profile_size(), 0);
        assert_eq!(first.profile_sha256(), ZERO_SHA256);
        let payload = decode_envelope(
            &fs::read(fixture.profile().join(LIFECYCLE_NAME).join(RECEIPT_A_NAME)).unwrap(),
        )
        .unwrap();
        assert_eq!(payload.reset_slot.sha256, ZERO_SHA256);
        assert_eq!(payload.enrollment_slot.sha256, ZERO_SHA256);
        assert_ne!(
            payload.live.identity.inode,
            payload.reset_slot.identity.inode
        );
        assert_ne!(
            payload.live.identity.inode,
            payload.enrollment_slot.identity.inode
        );
        assert_ne!(
            payload.reset_slot.identity.inode,
            payload.enrollment_slot.identity.inode
        );
        assert_eq!(
            payload.live.identity.device,
            payload.reset_slot.identity.device
        );
        assert_eq!(
            payload.live.identity.device,
            payload.enrollment_slot.identity.device
        );
    }

    #[test]
    fn refuses_ambiguous_legacy_profile_until_migration_is_reviewed() {
        let fixture = Fixture::new();
        durable_create_new(&fixture.profile().join(LIVE_NAME), b"legacy-profile").unwrap();
        assert!(matches!(
            initialize_profile_lifecycle(&fixture.storage),
            Err(ProfileLifecycleError::MigrationReviewRequired)
        ));
        assert_eq!(
            fs::read(fixture.profile().join(LIVE_NAME)).unwrap(),
            b"legacy-profile"
        );
        assert!(!fixture.profile().join(LIFECYCLE_NAME).exists());
        assert!(!fixture.profile().join(INITIALIZING_NAME).exists());
    }

    #[test]
    fn explicit_migration_preserves_exact_legacy_bytes_for_later_review() {
        let fixture = Fixture::new();
        let legacy = b"legacy-profile-sentinel";
        durable_create_new(&fixture.profile().join(LIVE_NAME), legacy).unwrap();

        let baseline = preserve_legacy_profile(&fixture.storage).unwrap();

        assert!(baseline.profile_present());
        assert_eq!(baseline.profile_size(), legacy.len() as u64);
        assert_eq!(
            baseline.profile_sha256(),
            format!("{:x}", Sha256::digest(legacy))
        );
        assert_eq!(fs::read(fixture.profile().join(LIVE_NAME)).unwrap(), legacy);
        assert!(!fixture.profile().join(INITIALIZING_NAME).exists());
        assert!(fixture.profile().join(LIFECYCLE_NAME).is_dir());
        assert_eq!(
            initialize_profile_lifecycle(&fixture.storage).unwrap(),
            baseline
        );
        assert_eq!(preserve_legacy_profile(&fixture.storage).unwrap(), baseline);
    }

    #[test]
    fn reset_removes_preserved_legacy_bytes_without_opening_a_meeting() {
        let fixture = Fixture::new();
        durable_create_new(
            &fixture.profile().join(LIVE_NAME),
            b"safe-but-not-activated-legacy-profile",
        )
        .unwrap();
        preserve_legacy_profile(&fixture.storage).unwrap();

        assert_eq!(
            reset_profile(&fixture.storage).unwrap(),
            ProfileResetOutcome::Removed {
                operation_id: "123e4567-e89b-12d3-a456-426614174000".into(),
                completed_reset_count: 1,
            }
        );
        assert_eq!(fs::read(fixture.profile().join(LIVE_NAME)).unwrap(), b"");
        assert_eq!(
            fs::read(fixture.profile().join(LIFECYCLE_NAME).join(RESET_NAME)).unwrap(),
            b""
        );
        let reopened = initialize_profile_lifecycle(&fixture.storage).unwrap();
        assert_eq!(reopened.receipt_sequence(), 3);
        assert_eq!(reopened.completed_reset_count(), 1);
        assert!(!reopened.profile_present());
        assert_eq!(
            reset_profile(&fixture.storage).unwrap(),
            ProfileResetOutcome::AlreadyAbsent
        );
    }

    #[test]
    fn fresh_process_recovers_each_durable_reset_data_layout() {
        for crash_point in ["deleting", "swapped", "staged", "truncated"] {
            let fixture = Fixture::new();
            durable_create_new(
                &fixture.profile().join(LIVE_NAME),
                b"safe-but-not-activated-legacy-profile",
            )
            .unwrap();
            preserve_legacy_profile(&fixture.storage).unwrap();

            let app_data = BoundPrivateDirectory::open(fixture.storage.path()).unwrap();
            let profile = app_data.open_directory("profile").unwrap();
            let lifecycle = profile.open_directory(LIFECYCLE_NAME).unwrap();
            let mut live = profile
                .open_file(LIVE_NAME, true, PROFILE_MAX_BYTES)
                .unwrap();
            let receipt_a = lifecycle
                .open_file(RECEIPT_A_NAME, true, RECEIPT_MAX_BYTES)
                .unwrap();
            let receipt_b = lifecycle
                .open_file(RECEIPT_B_NAME, true, RECEIPT_MAX_BYTES)
                .unwrap();
            let mut reset = lifecycle
                .open_file(RESET_NAME, true, PROFILE_MAX_BYTES)
                .unwrap();
            let enrollment = lifecycle.open_file(ENROLLMENT_NAME, false, 0).unwrap();
            let baseline = select_receipt_authority(&lifecycle, &receipt_a, &receipt_b).unwrap();
            let LifecyclePayload::Baseline(payload) = baseline.payload.clone() else {
                panic!("expected baseline");
            };
            let deleting = ResetPendingPayload {
                schema: "profile-lifecycle/1".into(),
                receipt_sequence: 1,
                operation: "reset".into(),
                phase: "deleting".into(),
                predecessor_payload_sha256: baseline.payload_sha256.clone(),
                operation_id: "123e4567-e89b-12d3-a456-426614174000".into(),
                requested_at: 10,
                prior_completed_reset_count: 0,
                prior_last_reset: None,
                profile: payload.live,
                reset_zero: payload.reset_slot,
                enrollment_zero: payload.enrollment_slot,
            };
            let deleting_authority = publish_payload(
                &lifecycle,
                &receipt_a,
                &receipt_b,
                &baseline,
                LifecyclePayload::ResetPending(deleting.clone()),
            )
            .unwrap();

            if crash_point != "deleting" {
                let swapped = profile
                    .swap_files(live, PROFILE_MAX_BYTES, &lifecycle, reset, 0)
                    .unwrap();
                reset = swapped.0;
                live = swapped.1;
            }
            let authority = if matches!(crash_point, "staged" | "truncated") {
                let staged = ResetPendingPayload {
                    receipt_sequence: 2,
                    phase: "staged".into(),
                    predecessor_payload_sha256: deleting_authority.payload_sha256.clone(),
                    ..deleting
                };
                publish_payload(
                    &lifecycle,
                    &receipt_a,
                    &receipt_b,
                    &deleting_authority,
                    LifecyclePayload::ResetPending(staged),
                )
                .unwrap()
            } else {
                deleting_authority
            };
            if crash_point == "truncated" {
                reset
                    .replace_bytes(&lifecycle, &[], PROFILE_MAX_BYTES)
                    .unwrap();
            }
            drop(authority);
            drop(enrollment);
            drop(reset);
            drop(live);
            drop(receipt_b);
            drop(receipt_a);
            drop(lifecycle);
            drop(profile);
            drop(app_data);

            let recovered = initialize_profile_lifecycle(&fixture.storage).unwrap();
            assert_eq!(recovered.completed_reset_count(), 1, "{crash_point}");
            assert!(!recovered.profile_present(), "{crash_point}");
            assert_eq!(fs::read(fixture.profile().join(LIVE_NAME)).unwrap(), b"");
            assert_eq!(
                fs::read(fixture.profile().join(LIFECYCLE_NAME).join(RESET_NAME)).unwrap(),
                b""
            );
        }
    }

    #[test]
    fn staged_receipt_never_authorizes_a_swap_that_did_not_happen() {
        let fixture = Fixture::new();
        let legacy = b"safe-but-not-activated-legacy-profile";
        durable_create_new(&fixture.profile().join(LIVE_NAME), legacy).unwrap();
        preserve_legacy_profile(&fixture.storage).unwrap();

        let app_data = BoundPrivateDirectory::open(fixture.storage.path()).unwrap();
        let profile = app_data.open_directory("profile").unwrap();
        let lifecycle = profile.open_directory(LIFECYCLE_NAME).unwrap();
        let live = profile
            .open_file(LIVE_NAME, true, PROFILE_MAX_BYTES)
            .unwrap();
        let receipt_a = lifecycle
            .open_file(RECEIPT_A_NAME, true, RECEIPT_MAX_BYTES)
            .unwrap();
        let receipt_b = lifecycle
            .open_file(RECEIPT_B_NAME, true, RECEIPT_MAX_BYTES)
            .unwrap();
        let reset = lifecycle.open_file(RESET_NAME, true, 0).unwrap();
        let enrollment = lifecycle.open_file(ENROLLMENT_NAME, false, 0).unwrap();
        let baseline = select_receipt_authority(&lifecycle, &receipt_a, &receipt_b).unwrap();
        let LifecyclePayload::Baseline(_payload) = baseline.payload.clone() else {
            panic!("expected baseline");
        };
        let staged = ResetPendingPayload {
            schema: "profile-lifecycle/1".into(),
            receipt_sequence: 1,
            operation: "reset".into(),
            phase: "staged".into(),
            predecessor_payload_sha256: baseline.payload_sha256.clone(),
            operation_id: "123e4567-e89b-12d3-a456-426614174000".into(),
            requested_at: 10,
            prior_completed_reset_count: 0,
            prior_last_reset: None,
            profile: observe_slot(&profile, &live, PROFILE_MAX_BYTES).unwrap(),
            reset_zero: observe_slot(&lifecycle, &reset, 0).unwrap(),
            enrollment_zero: observe_slot(&lifecycle, &enrollment, 0).unwrap(),
        };
        publish_payload(
            &lifecycle,
            &receipt_a,
            &receipt_b,
            &baseline,
            LifecyclePayload::ResetPending(staged),
        )
        .unwrap();
        drop(enrollment);
        drop(reset);
        drop(receipt_b);
        drop(receipt_a);
        drop(lifecycle);
        drop(live);
        drop(profile);
        drop(app_data);

        assert!(matches!(
            initialize_profile_lifecycle(&fixture.storage),
            Err(ProfileLifecycleError::Quarantined)
        ));
        assert_eq!(fs::read(fixture.profile().join(LIVE_NAME)).unwrap(), legacy);
    }

    #[test]
    fn explicit_migration_requires_an_existing_safe_live_slot() {
        let fixture = Fixture::new();

        assert!(matches!(
            preserve_legacy_profile(&fixture.storage),
            Err(ProfileLifecycleError::Quarantined)
        ));
        assert!(!fixture.profile().join(LIFECYCLE_NAME).exists());
        assert!(!fixture.profile().join(INITIALIZING_NAME).exists());
        assert!(!fixture.profile().join(LIVE_NAME).exists());
    }

    #[test]
    fn unreceipted_migration_crash_requires_fresh_explicit_review() {
        let fixture = Fixture::new();
        let legacy = b"legacy-profile-sentinel";
        durable_create_new(&fixture.profile().join(LIVE_NAME), legacy).unwrap();
        create_private_dir(&fixture.profile().join(INITIALIZING_NAME)).unwrap();

        assert!(matches!(
            initialize_profile_lifecycle(&fixture.storage),
            Err(ProfileLifecycleError::MigrationReviewRequired)
        ));
        assert_eq!(fs::read(fixture.profile().join(LIVE_NAME)).unwrap(), legacy);
        assert!(
            fs::read_dir(fixture.profile().join(INITIALIZING_NAME))
                .unwrap()
                .next()
                .is_none()
        );

        let baseline = preserve_legacy_profile(&fixture.storage).unwrap();
        assert!(baseline.profile_present());
        assert_eq!(fs::read(fixture.profile().join(LIVE_NAME)).unwrap(), legacy);
    }

    #[test]
    fn receipted_migration_crash_resumes_without_another_decision() {
        let fixture = Fixture::new();
        let legacy = b"legacy-profile-sentinel";
        durable_create_new(&fixture.profile().join(LIVE_NAME), legacy).unwrap();
        let app_data = BoundPrivateDirectory::open(fixture.storage.path()).unwrap();
        let profile = app_data.open_directory("profile").unwrap();
        let live = profile
            .open_file(LIVE_NAME, true, PROFILE_MAX_BYTES)
            .unwrap();
        let initializing = profile.create_directory(INITIALIZING_NAME).unwrap();
        prepare_initializing(&profile, &live, &initializing, true).unwrap();
        drop(initializing);
        drop(live);
        drop(profile);
        drop(app_data);

        let baseline = initialize_profile_lifecycle(&fixture.storage).unwrap();

        assert!(baseline.profile_present());
        assert_eq!(fs::read(fixture.profile().join(LIVE_NAME)).unwrap(), legacy);
        assert!(!fixture.profile().join(INITIALIZING_NAME).exists());
        assert!(fixture.profile().join(LIFECYCLE_NAME).is_dir());
    }

    #[test]
    fn publishes_canonical_receipt_and_leaves_peer_virgin() {
        let fixture = Fixture::new();
        initialize_profile_lifecycle(&fixture.storage).unwrap();
        let lifecycle = fixture.profile().join(LIFECYCLE_NAME);
        let bytes = fs::read(lifecycle.join(RECEIPT_A_NAME)).unwrap();
        assert!(!bytes.ends_with(b"\n"));
        assert!(
            bytes.starts_with(
                b"{\n  \"schema\": \"profile-lifecycle-slot/1\",\n  \"payload_sha256\":"
            )
        );
        assert!(decode_envelope(&bytes).is_ok());
        assert_eq!(
            fs::metadata(lifecycle.join(RECEIPT_B_NAME)).unwrap().len(),
            0
        );
        for name in FIXED_NAMES {
            assert_eq!(
                fs::metadata(lifecycle.join(name))
                    .unwrap()
                    .permissions()
                    .mode()
                    & 0o777,
                0o600
            );
        }
    }

    #[test]
    fn resumes_only_the_closed_partial_initialization_shape() {
        let fixture = Fixture::new();
        let initializing = fixture.profile().join(INITIALIZING_NAME);
        create_private_dir(&initializing).unwrap();
        durable_create_new(&initializing.join(RECEIPT_B_NAME), b"").unwrap();
        let baseline = initialize_profile_lifecycle(&fixture.storage).unwrap();
        assert_eq!(baseline.receipt_sequence(), 0);
        assert!(fixture.profile().join(LIFECYCLE_NAME).is_dir());
        assert!(!initializing.exists());

        let rejected = Fixture::new();
        let rejected_initializing = rejected.profile().join(INITIALIZING_NAME);
        create_private_dir(&rejected_initializing).unwrap();
        durable_create_new(&rejected_initializing.join("unexpected"), b"").unwrap();
        assert!(matches!(
            initialize_profile_lifecycle(&rejected.storage),
            Err(ProfileLifecycleError::Quarantined)
        ));

        let post_receipt = Fixture::new();
        let original = initialize_profile_lifecycle(&post_receipt.storage).unwrap();
        fs::rename(
            post_receipt.profile().join(LIFECYCLE_NAME),
            post_receipt.profile().join(INITIALIZING_NAME),
        )
        .unwrap();
        assert_eq!(
            initialize_profile_lifecycle(&post_receipt.storage).unwrap(),
            original
        );
    }

    #[test]
    fn accepts_one_torn_receipt_only_while_the_peer_is_authoritative() {
        let fixture = Fixture::new();
        let baseline = initialize_profile_lifecycle(&fixture.storage).unwrap();
        fs::write(
            fixture.profile().join(LIFECYCLE_NAME).join(RECEIPT_B_NAME),
            b"torn",
        )
        .unwrap();
        assert_eq!(
            initialize_profile_lifecycle(&fixture.storage).unwrap(),
            baseline
        );
    }

    #[test]
    fn a_self_consistent_higher_phase_cannot_be_mistaken_for_a_torn_peer() {
        let fixture = Fixture::new();
        initialize_profile_lifecycle(&fixture.storage).unwrap();
        let payload = b"{\n  \"schema\": \"profile-lifecycle/1\",\n  \"receipt_sequence\": 1,\n  \"operation\": \"reset\",\n  \"phase\": \"deleting\"\n}";
        let digest = format!("{:x}", Sha256::digest(payload));
        let indented = String::from_utf8(payload.to_vec())
            .unwrap()
            .replace('\n', "\n  ");
        let receipt = format!(
            "{{\n  \"schema\": \"profile-lifecycle-slot/1\",\n  \"payload_sha256\": \"{digest}\",\n  \"payload\": {indented}\n}}"
        );
        fs::write(
            fixture.profile().join(LIFECYCLE_NAME).join(RECEIPT_B_NAME),
            receipt,
        )
        .unwrap();
        assert!(matches!(
            initialize_profile_lifecycle(&fixture.storage),
            Err(ProfileLifecycleError::Quarantined)
        ));
    }

    #[test]
    fn quarantines_missing_or_duplicated_authority_in_published_store() {
        let missing = Fixture::new();
        initialize_profile_lifecycle(&missing.storage).unwrap();
        fs::remove_file(missing.profile().join(LIFECYCLE_NAME).join(RESET_NAME)).unwrap();
        assert!(matches!(
            initialize_profile_lifecycle(&missing.storage),
            Err(ProfileLifecycleError::Quarantined)
        ));

        let duplicate = Fixture::new();
        initialize_profile_lifecycle(&duplicate.storage).unwrap();
        let lifecycle = duplicate.profile().join(LIFECYCLE_NAME);
        let authority = fs::read(lifecycle.join(RECEIPT_A_NAME)).unwrap();
        fs::write(lifecycle.join(RECEIPT_B_NAME), authority).unwrap();
        assert!(matches!(
            initialize_profile_lifecycle(&duplicate.storage),
            Err(ProfileLifecycleError::Quarantined)
        ));
    }

    #[test]
    fn never_repairs_a_published_store_or_rebaselines_total_journal_loss() {
        let missing_live = Fixture::new();
        initialize_profile_lifecycle(&missing_live.storage).unwrap();
        fs::remove_file(missing_live.profile().join(LIVE_NAME)).unwrap();
        assert!(matches!(
            initialize_profile_lifecycle(&missing_live.storage),
            Err(ProfileLifecycleError::Quarantined)
        ));
        assert!(!missing_live.profile().join(LIVE_NAME).exists());

        let missing_journal = Fixture::new();
        initialize_profile_lifecycle(&missing_journal.storage).unwrap();
        fs::remove_dir_all(missing_journal.profile().join(LIFECYCLE_NAME)).unwrap();
        assert!(matches!(
            initialize_profile_lifecycle(&missing_journal.storage),
            Err(ProfileLifecycleError::MigrationReviewRequired)
        ));
        assert!(!missing_journal.profile().join(LIFECYCLE_NAME).exists());
        assert!(!missing_journal.profile().join(INITIALIZING_NAME).exists());
    }

    #[test]
    fn quarantines_changed_live_bytes_instead_of_rebaselining() {
        let fixture = Fixture::new();
        initialize_profile_lifecycle(&fixture.storage).unwrap();
        fs::write(fixture.profile().join(LIVE_NAME), b"changed").unwrap();
        assert!(matches!(
            initialize_profile_lifecycle(&fixture.storage),
            Err(ProfileLifecycleError::Quarantined)
        ));
    }

    #[test]
    fn canonical_receipt_bytes_are_part_of_authority() {
        let fixture = Fixture::new();
        initialize_profile_lifecycle(&fixture.storage).unwrap();
        let receipt = fixture.profile().join(LIFECYCLE_NAME).join(RECEIPT_A_NAME);
        let mut bytes = fs::read(&receipt).unwrap();
        bytes.push(b'\n');
        fs::write(receipt, bytes).unwrap();
        assert!(matches!(
            initialize_profile_lifecycle(&fixture.storage),
            Err(ProfileLifecycleError::Quarantined)
        ));
    }

    #[test]
    fn unsafe_app_data_root_blocks_before_profile_mutation() {
        let fixture = Fixture::new();
        fs::set_permissions(fixture.storage.path(), fs::Permissions::from_mode(0o755)).unwrap();
        assert!(matches!(
            initialize_profile_lifecycle(&fixture.storage),
            Err(ProfileLifecycleError::Quarantined)
        ));
        assert!(!fixture.profile().join(LIVE_NAME).exists());
        assert!(!fixture.profile().join(INITIALIZING_NAME).exists());
    }
}

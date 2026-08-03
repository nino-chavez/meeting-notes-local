//! Fixed-slot profile lifecycle journal.
//!
//! This first increment establishes and reopens the durable sequence-zero
//! baseline. Reset and enrollment mutations are intentionally not exposed yet.

#![cfg(target_os = "macos")]

use std::io;

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use thiserror::Error;

use crate::storage::{
    BoundPrivateDirectory, BoundPrivateFile, PrivateObjectIdentity, PrivateObjectObservation,
    StorageRoot,
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
pub(crate) enum ProfileLifecycleError {
    #[error("profile lifecycle is quarantined")]
    Quarantined,
    #[error("profile lifecycle initialization is ambiguous and requires migration review")]
    MigrationReviewRequired,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct ProfileLifecycleBaseline {
    receipt_sequence: u64,
    completed_reset_count: u64,
    profile_size: u64,
    profile_sha256: String,
}

impl ProfileLifecycleBaseline {
    pub(crate) fn receipt_sequence(&self) -> u64 {
        self.receipt_sequence
    }

    pub(crate) fn completed_reset_count(&self) -> u64 {
        self.completed_reset_count
    }

    pub(crate) fn profile_present(&self) -> bool {
        self.profile_size != 0
    }

    pub(crate) fn profile_size(&self) -> u64 {
        self.profile_size
    }

    pub(crate) fn profile_sha256(&self) -> &str {
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
struct BaselineEnvelope {
    schema: String,
    payload_sha256: String,
    payload: BaselinePayload,
}

pub(crate) fn initialize_profile_lifecycle(
    storage: &StorageRoot,
) -> Result<ProfileLifecycleBaseline, ProfileLifecycleError> {
    let app_data = BoundPrivateDirectory::open(storage.path()).map_err(quarantine_io)?;
    let profile = app_data.open_directory("profile").map_err(quarantine_io)?;
    let result = initialize_bound_profile(&profile);
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
            validate_published(profile, &live, &lifecycle)
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
            prepare_initializing(profile, &live, &initializing)?;
            let lifecycle = profile
                .publish_directory_exclusive(initializing, INITIALIZING_NAME, LIFECYCLE_NAME)
                .map_err(quarantine_io)?;
            validate_published(profile, &live, &lifecycle)
        }
        Err(error) => Err(quarantine_io(error)),
    }
}

fn prepare_initializing(
    profile: &BoundPrivateDirectory,
    live: &BoundPrivateFile,
    initializing: &BoundPrivateDirectory,
) -> Result<(), ProfileLifecycleError> {
    let names = initializing.child_names().map_err(quarantine_io)?;
    if names
        .iter()
        .any(|name| !FIXED_NAMES.contains(&name.as_str()))
    {
        return Err(ProfileLifecycleError::Quarantined);
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

fn validate_published(
    profile: &BoundPrivateDirectory,
    live: &BoundPrivateFile,
    lifecycle: &BoundPrivateDirectory,
) -> Result<ProfileLifecycleBaseline, ProfileLifecycleError> {
    if lifecycle.child_names().map_err(quarantine_io)? != FIXED_NAMES {
        return Err(ProfileLifecycleError::Quarantined);
    }
    let receipt_a = lifecycle
        .open_file(RECEIPT_A_NAME, false, RECEIPT_MAX_BYTES)
        .map_err(quarantine_io)?;
    let receipt_b = lifecycle
        .open_file(RECEIPT_B_NAME, false, RECEIPT_MAX_BYTES)
        .map_err(quarantine_io)?;
    let reset = lifecycle
        .open_file(RESET_NAME, false, 0)
        .map_err(quarantine_io)?;
    let enrollment = lifecycle
        .open_file(ENROLLMENT_NAME, false, 0)
        .map_err(quarantine_io)?;
    let expected = baseline_payload(profile, live, lifecycle, &reset, &enrollment)?;

    let mut valid = Vec::new();
    for receipt in [&receipt_a, &receipt_b] {
        let bytes = receipt
            .read_all(lifecycle, RECEIPT_MAX_BYTES)
            .map_err(quarantine_io)?;
        if bytes.is_empty() {
            continue;
        }
        match decode_envelope(&bytes) {
            Ok(payload) => valid.push(payload),
            Err(_) if is_self_consistent_unsupported_receipt(&bytes) => {
                return Err(ProfileLifecycleError::Quarantined);
            }
            Err(_) => {}
        }
    }
    if valid.len() != 1 || valid[0] != expected {
        return Err(ProfileLifecycleError::Quarantined);
    }
    Ok(ProfileLifecycleBaseline {
        receipt_sequence: expected.receipt_sequence,
        completed_reset_count: expected.completed_reset_count,
        profile_size: expected.live.size,
        profile_sha256: expected.live.sha256,
    })
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
    let payload_bytes =
        serde_json::to_vec_pretty(&payload).map_err(|_| ProfileLifecycleError::Quarantined)?;
    serde_json::to_vec_pretty(&BaselineEnvelope {
        schema: "profile-lifecycle-slot/1".into(),
        payload_sha256: format!("{:x}", Sha256::digest(payload_bytes)),
        payload,
    })
    .map_err(|_| ProfileLifecycleError::Quarantined)
}

fn decode_envelope(bytes: &[u8]) -> Result<BaselinePayload, ProfileLifecycleError> {
    let envelope: BaselineEnvelope =
        serde_json::from_slice(bytes).map_err(|_| ProfileLifecycleError::Quarantined)?;
    if envelope.schema != "profile-lifecycle-slot/1"
        || envelope.payload.schema != "profile-lifecycle/1"
        || envelope.payload.receipt_sequence != 0
        || envelope.payload.operation != "baseline"
        || envelope.payload.phase != "ready"
        || envelope.payload.completed_reset_count != 0
        || envelope.payload_sha256.len() != 64
        || !envelope
            .payload_sha256
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
    {
        return Err(ProfileLifecycleError::Quarantined);
    }
    let canonical = encode_envelope(envelope.payload.clone())?;
    if canonical != bytes {
        return Err(ProfileLifecycleError::Quarantined);
    }
    Ok(envelope.payload)
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
    use crate::storage::{create_private_dir, durable_create_new};

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

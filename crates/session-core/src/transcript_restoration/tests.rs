use std::collections::{HashMap, VecDeque};
use std::fs;
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};

use serde_json::json;
use tempfile::TempDir;

use super::*;
use crate::meeting::{
    AudioRetention, AudioRetentionRule, AudioState, MeetingArtifacts, MeetingSchema,
    PendingStorageOperation, artifact_ref, retention_policy_sha256,
};
use crate::operation_store::OperationReceiptState;
use crate::storage::{create_private_dir, durable_create_new, durable_replace};

const MEETING_ID: &str = "11111111-1111-4111-8111-111111111111";
const OPERATION_ID: &str = "22222222-2222-4222-8222-222222222222";

#[derive(Debug, Clone, Copy)]
enum WorkerMode {
    Normal,
    MissingSuccessor,
}

struct FakeWorker {
    meeting_dir: PathBuf,
    mode: Mutex<WorkerMode>,
    calls: Mutex<u32>,
}

impl FakeWorker {
    fn new(meeting_dir: PathBuf) -> Self {
        Self {
            meeting_dir,
            mode: Mutex::new(WorkerMode::Normal),
            calls: Mutex::new(0),
        }
    }

    fn calls(&self) -> u32 {
        *self.calls.lock().unwrap()
    }
}

impl TranscriptRestoreWorker for FakeWorker {
    fn restore(
        &self,
        arguments: &TranscriptRestoreWorkerArgs,
    ) -> Result<HashMap<String, String>, TranscriptRestoreWorkerError> {
        *self.calls.lock().unwrap() += 1;
        let source = StoredTranscriptArtifactInspector
            .inspect_revision(
                &self.meeting_dir,
                arguments.meeting_id,
                &arguments.source_transcript_sha256,
            )
            .map_err(|_| TranscriptRestoreWorkerError::Refused)?;
        if matches!(*self.mode.lock().unwrap(), WorkerMode::MissingSuccessor) {
            return Ok(HashMap::from([
                ("base-transcript".into(), source.base_transcript_sha256),
                (
                    "parent-transcript".into(),
                    arguments.source_transcript_sha256.clone(),
                ),
                ("transcript".into(), "f".repeat(64)),
            ]));
        }

        let mut restored = source.restored_source_turn_indices;
        restored.push(arguments.source_turn_index);
        restored.sort_unstable();
        let view = TranscriptView {
            schema: crate::operations::TranscriptViewSchema::V1,
            meeting_id: arguments.meeting_id,
            base_transcript_sha256: source.base_transcript_sha256.clone(),
            parent_transcript_sha256: arguments.source_transcript_sha256.clone(),
            restored_source_turn_indices: restored,
        };
        let bytes = serde_json::to_vec_pretty(&view).unwrap();
        let digest = digest_bytes(&bytes);
        let path = self
            .meeting_dir
            .join("transcript")
            .join(format!("{digest}.json"));
        match fs::symlink_metadata(&path) {
            Ok(_) => {
                let existing = read_private_bytes(&path, MAX_TRANSCRIPT_REVISION_BYTES)
                    .map_err(|_| TranscriptRestoreWorkerError::Refused)?;
                if existing != bytes {
                    return Err(TranscriptRestoreWorkerError::Refused);
                }
            }
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                durable_create_new(&path, &bytes)
                    .map_err(|_| TranscriptRestoreWorkerError::Unavailable)?;
            }
            Err(_) => return Err(TranscriptRestoreWorkerError::Unavailable),
        }
        Ok(HashMap::from([
            ("base-transcript".into(), source.base_transcript_sha256),
            (
                "parent-transcript".into(),
                arguments.source_transcript_sha256.clone(),
            ),
            ("transcript".into(), digest),
        ]))
    }
}

struct FixedIdentity {
    operation_id: Uuid,
    times: Mutex<VecDeque<u64>>,
}

impl FixedIdentity {
    fn new(operation_id: Uuid, times: impl IntoIterator<Item = u64>) -> Self {
        Self {
            operation_id,
            times: Mutex::new(times.into_iter().collect()),
        }
    }
}

impl RestorationIdentitySource for FixedIdentity {
    fn operation_id(&self) -> Uuid {
        self.operation_id
    }

    fn now_epoch_seconds(&self) -> u64 {
        self.times.lock().unwrap().pop_front().unwrap_or(999)
    }
}

struct CrashOnce {
    phase: RestorationDurablePhase,
    fired: Mutex<bool>,
}

impl CrashOnce {
    fn new(phase: RestorationDurablePhase) -> Self {
        Self {
            phase,
            fired: Mutex::new(false),
        }
    }
}

impl RestorationFailureInjection for CrashOnce {
    fn after_phase(
        &self,
        phase: RestorationDurablePhase,
    ) -> Result<(), RestorationInjectedFailure> {
        let mut fired = self.fired.lock().unwrap();
        if !*fired && phase == self.phase {
            *fired = true;
            return Err(RestorationInjectedFailure);
        }
        Ok(())
    }
}

struct FailSecondInspection {
    calls: Mutex<u32>,
}

impl TranscriptArtifactInspector for FailSecondInspection {
    fn inspect_revision(
        &self,
        meeting_dir: &Path,
        meeting_id: Uuid,
        transcript_sha256: &str,
    ) -> Result<InspectedTranscriptRevision, TranscriptArtifactError> {
        let mut calls = self.calls.lock().unwrap();
        *calls += 1;
        if *calls == 2 {
            return Err(TranscriptArtifactError::Cyclic);
        }
        StoredTranscriptArtifactInspector.inspect_revision(
            meeting_dir,
            meeting_id,
            transcript_sha256,
        )
    }
}

struct Fixture {
    _temporary: TempDir,
    storage: StorageRoot,
    meeting_dir: PathBuf,
    meeting_id: Uuid,
    base_sha256: String,
    prior_note: Option<NoteRevisionRef>,
    worker: Arc<FakeWorker>,
    coordination: Arc<MeetingStorageCoordination>,
}

impl Fixture {
    fn new(with_note: bool) -> Self {
        let temporary = TempDir::new().unwrap();
        let repository = temporary.path().join("repository");
        create_private_dir(&repository).unwrap();
        let storage = StorageRoot::create(&temporary.path().join("app-data"), &repository).unwrap();
        let meeting_id = Uuid::parse_str(MEETING_ID).unwrap();
        let meeting_dir = storage
            .resolve(&Path::new("meetings").join(MEETING_ID))
            .unwrap();
        for path in [
            meeting_dir.clone(),
            meeting_dir.join("capture"),
            meeting_dir.join("transcript"),
            meeting_dir.join("notes"),
        ] {
            create_private_dir(&path).unwrap();
        }
        for (path, bytes) in [
            ("attempt.json", b"attempt".as_slice()),
            ("ownership.json", b"ownership".as_slice()),
            ("capture/session.json", b"capture".as_slice()),
            ("capture/mic.wav", b"mic".as_slice()),
            ("capture/system.wav", b"system".as_slice()),
        ] {
            durable_create_new(&meeting_dir.join(path), bytes).unwrap();
        }

        let turns: Vec<_> = (0..8)
            .map(|index| {
                let mut turn = json!({
                    "start": index as f64,
                    "end": index as f64 + 0.5,
                    "speaker": if index % 2 == 0 { "Me" } else { "Them" },
                    "text": format!("turn {index}")
                });
                if index == 6 || index == 7 {
                    turn["gated"] = json!(true);
                    turn["gate_score"] = json!(0.1);
                    turn["gate_reason"] = json!("fixture");
                }
                turn
            })
            .collect();
        let base = json!({
            "schema": "capture-transcript/1",
            "source": "fixture",
            "attribution": "channel",
            "capture_health": {},
            "turns": turns
        });
        let base_bytes = serde_json::to_vec_pretty(&base).unwrap();
        let base_sha256 = digest_bytes(&base_bytes);
        durable_create_new(
            &meeting_dir
                .join("transcript")
                .join(format!("{base_sha256}.json")),
            &base_bytes,
        )
        .unwrap();

        let prior_note = with_note.then(|| write_note(&meeting_dir, &base_sha256, "prior"));
        let retention_rule = AudioRetentionRule::UntilManualDeletion;
        let meeting = MeetingRecord {
            schema: MeetingSchema::V2,
            meeting_id: MEETING_ID.into(),
            lifecycle: if with_note {
                MeetingLifecycle::Ready
            } else {
                MeetingLifecycle::TranscriptReady
            },
            retention: AudioRetention {
                rule: retention_rule.clone(),
                policy_sha256: retention_policy_sha256(&retention_rule),
                next_deletion_at_epoch_seconds: None,
                state: AudioState::Retained,
                deletion_receipt: None,
            },
            artifacts: MeetingArtifacts {
                attempt: artifact_ref(&meeting_dir, "attempt.json").unwrap(),
                ownership: Some(artifact_ref(&meeting_dir, "ownership.json").unwrap()),
                capture_session: Some(artifact_ref(&meeting_dir, "capture/session.json").unwrap()),
                microphone_audio: Some(artifact_ref(&meeting_dir, "capture/mic.wav").unwrap()),
                system_audio: Some(artifact_ref(&meeting_dir, "capture/system.wav").unwrap()),
                current_transcript: Some(
                    artifact_ref(&meeting_dir, &format!("transcript/{base_sha256}.json")).unwrap(),
                ),
                current_note: prior_note.clone(),
            },
            pending_storage_operation: None,
        };
        write_meeting(&meeting_dir, &meeting).unwrap();
        let worker = Arc::new(FakeWorker::new(meeting_dir.clone()));
        Self {
            _temporary: temporary,
            storage,
            meeting_dir,
            meeting_id,
            base_sha256,
            prior_note,
            worker,
            coordination: Arc::new(MeetingStorageCoordination::default()),
        }
    }

    fn arguments(&self, source_turn_index: u32) -> RestoreWithheldTurnUiArgs {
        RestoreWithheldTurnUiArgs {
            meeting_id: self.meeting_id,
            source_transcript_sha256: current_transcript(&self.meeting_dir),
            source_turn_index,
        }
    }

    fn coordinator(
        &self,
        failures: Arc<dyn RestorationFailureInjection>,
    ) -> TranscriptRestorationCoordinator {
        TranscriptRestorationCoordinator::with_runtime(
            self.storage.clone(),
            self.coordination.clone(),
            self.worker.clone(),
            Arc::new(StoredTranscriptArtifactInspector),
            Arc::new(FixedIdentity::new(
                Uuid::parse_str(OPERATION_ID).unwrap(),
                [100, 101, 102],
            )),
            failures,
        )
        .unwrap()
    }

    fn reconstructed(&self) -> TranscriptRestorationCoordinator {
        self.coordinator(Arc::new(NoRestorationFailureInjection))
    }
}

fn write_note(meeting_dir: &Path, source_sha256: &str, label: &str) -> NoteRevisionRef {
    let json_bytes = format!("note-json-{label}").into_bytes();
    let markdown_bytes = format!("note-markdown-{label}").into_bytes();
    let json_sha256 = digest_bytes(&json_bytes);
    let markdown_sha256 = digest_bytes(&markdown_bytes);
    durable_create_new(
        &meeting_dir
            .join("notes")
            .join(format!("{json_sha256}.json")),
        &json_bytes,
    )
    .unwrap();
    durable_create_new(
        &meeting_dir
            .join("notes")
            .join(format!("{markdown_sha256}.md")),
        &markdown_bytes,
    )
    .unwrap();
    NoteRevisionRef {
        json: artifact_ref(meeting_dir, &format!("notes/{json_sha256}.json")).unwrap(),
        markdown: artifact_ref(meeting_dir, &format!("notes/{markdown_sha256}.md")).unwrap(),
        source_transcript_sha256: source_sha256.into(),
    }
}

fn current_transcript(meeting_dir: &Path) -> String {
    load_meeting(meeting_dir)
        .unwrap()
        .artifacts
        .current_transcript
        .unwrap()
        .sha256
}

fn meeting_bytes(meeting_dir: &Path) -> Vec<u8> {
    read_private_bytes(&meeting_dir.join("meeting.json"), MAX_MEETING_RECORD_BYTES).unwrap()
}

fn begin_pending_audio_deletion(fixture: &Fixture) -> Vec<u8> {
    let mut meeting = load_meeting(&fixture.meeting_dir).unwrap();
    meeting.retention.state = AudioState::Deleting;
    meeting.pending_storage_operation = Some(PendingStorageOperation::AudioDeletionV1);
    write_meeting(&fixture.meeting_dir, &meeting).unwrap();
    meeting_bytes(&fixture.meeting_dir)
}

fn receipt(fixture: &Fixture) -> StoredOperationReceipt {
    OperationStore::open(&fixture.storage)
        .unwrap()
        .load(Uuid::parse_str(OPERATION_ID).unwrap())
        .unwrap()
}

fn assert_source_unchanged(fixture: &Fixture) {
    let meeting = load_meeting(&fixture.meeting_dir).unwrap();
    assert_eq!(
        meeting.artifacts.current_transcript.unwrap().sha256,
        fixture.base_sha256
    );
    assert_eq!(meeting.artifacts.current_note, fixture.prior_note);
}

fn assert_committed_successor(fixture: &Fixture) {
    let meeting = load_meeting(&fixture.meeting_dir).unwrap();
    assert_eq!(meeting.lifecycle, MeetingLifecycle::TranscriptReady);
    assert!(meeting.artifacts.current_note.is_none());
    assert_ne!(
        meeting.artifacts.current_transcript.unwrap().sha256,
        fixture.base_sha256
    );
    assert_eq!(receipt(fixture).state(), OperationReceiptState::Committed);
    let commit = receipt(fixture).commit.unwrap();
    let meeting_bytes = read_private_bytes(
        &fixture.meeting_dir.join("meeting.json"),
        MAX_MEETING_RECORD_BYTES,
    )
    .unwrap();
    assert_eq!(
        commit.committed_meeting_sha256,
        digest_bytes(&meeting_bytes)
    );
}

#[test]
fn happy_path_clears_the_exact_prior_note_then_commits_exact_meeting_bytes() {
    let fixture = Fixture::new(true);
    let coordinator = fixture.reconstructed();
    assert_eq!(
        coordinator
            .restore_withheld_turn(&fixture.arguments(7))
            .unwrap(),
        Uuid::parse_str(OPERATION_ID).unwrap()
    );
    assert_committed_successor(&fixture);
    assert_eq!(fixture.worker.calls(), 1);
}

#[test]
fn pending_audio_deletion_refuses_a_new_request_without_worker_or_mutation() {
    let fixture = Fixture::new(true);
    let before = begin_pending_audio_deletion(&fixture);

    assert!(matches!(
        fixture
            .reconstructed()
            .restore_withheld_turn(&fixture.arguments(7)),
        Err(TranscriptRestorationCoordinatorError::Ambiguous(
            "meeting has a pending storage operation"
        ))
    ));

    assert_eq!(fixture.worker.calls(), 0);
    assert_eq!(meeting_bytes(&fixture.meeting_dir), before);
    assert!(
        OperationStore::open(&fixture.storage)
            .unwrap()
            .scan()
            .unwrap()
            .is_empty()
    );
    let meeting = load_meeting(&fixture.meeting_dir).unwrap();
    assert_eq!(
        meeting.artifacts.current_transcript.unwrap().sha256,
        fixture.base_sha256
    );
    assert_eq!(meeting.artifacts.current_note, fixture.prior_note);
}

#[test]
fn pending_audio_deletion_quarantines_every_incomplete_recovery_state_untouched() {
    for phase in [
        RestorationDurablePhase::RequestStored,
        RestorationDurablePhase::ResultStored,
        RestorationDurablePhase::MeetingPublished,
    ] {
        let fixture = Fixture::new(true);
        let coordinator = fixture.coordinator(Arc::new(CrashOnce::new(phase)));
        assert!(matches!(
            coordinator.restore_withheld_turn(&fixture.arguments(7)),
            Err(TranscriptRestorationCoordinatorError::InjectedCrash(actual)) if actual == phase
        ));
        let worker_calls_before_recovery = fixture.worker.calls();
        let transcript_before_deletion = current_transcript(&fixture.meeting_dir);
        let note_before_deletion = load_meeting(&fixture.meeting_dir)
            .unwrap()
            .artifacts
            .current_note;
        let meeting_before_recovery = begin_pending_audio_deletion(&fixture);

        let report = fixture.reconstructed().recover_incomplete().unwrap();

        assert_eq!(
            report.operations,
            vec![RestorationRecoveryDisposition::Quarantined {
                meeting_id: fixture.meeting_id,
                operation_id: Some(Uuid::parse_str(OPERATION_ID).unwrap()),
                reason: RestorationQuarantineReason::SourceOrPriorNoteChanged,
            }]
        );
        assert_eq!(fixture.worker.calls(), worker_calls_before_recovery);
        assert_eq!(meeting_bytes(&fixture.meeting_dir), meeting_before_recovery);
        let meeting = load_meeting(&fixture.meeting_dir).unwrap();
        assert_eq!(
            meeting.artifacts.current_transcript.unwrap().sha256,
            transcript_before_deletion
        );
        assert_eq!(meeting.artifacts.current_note, note_before_deletion);
        let receipt = receipt(&fixture);
        assert!(receipt.commit.is_none());
        assert_eq!(
            receipt.state(),
            match phase {
                RestorationDurablePhase::RequestStored => OperationReceiptState::RequestOnly,
                RestorationDurablePhase::ResultStored
                | RestorationDurablePhase::MeetingPublished => OperationReceiptState::ResultStored,
                _ => unreachable!(),
            }
        );
    }
}

#[test]
fn every_durable_phase_recovers_from_a_fresh_coordinator() {
    for phase in [
        RestorationDurablePhase::RequestStored,
        RestorationDurablePhase::WorkerArtifactReturned,
        RestorationDurablePhase::ResultStored,
        RestorationDurablePhase::MeetingPublished,
        RestorationDurablePhase::CommitStored,
    ] {
        let fixture = Fixture::new(true);
        let coordinator = fixture.coordinator(Arc::new(CrashOnce::new(phase)));
        assert!(matches!(
            coordinator.restore_withheld_turn(&fixture.arguments(7)),
            Err(TranscriptRestorationCoordinatorError::InjectedCrash(actual)) if actual == phase
        ));

        let before = receipt(&fixture);
        match phase {
            RestorationDurablePhase::RequestStored
            | RestorationDurablePhase::WorkerArtifactReturned => {
                assert_eq!(before.state(), OperationReceiptState::RequestOnly);
                assert_source_unchanged(&fixture);
            }
            RestorationDurablePhase::ResultStored => {
                assert_eq!(before.state(), OperationReceiptState::ResultStored);
                assert_source_unchanged(&fixture);
            }
            RestorationDurablePhase::MeetingPublished => {
                assert_eq!(before.state(), OperationReceiptState::ResultStored);
                assert_ne!(
                    current_transcript(&fixture.meeting_dir),
                    fixture.base_sha256
                );
            }
            RestorationDurablePhase::CommitStored => {
                assert_eq!(before.state(), OperationReceiptState::Committed);
            }
        }

        let report = fixture.reconstructed().recover_incomplete().unwrap();
        if phase == RestorationDurablePhase::CommitStored {
            assert!(report.operations.is_empty());
        } else {
            let expected = match phase {
                RestorationDurablePhase::RequestStored
                | RestorationDurablePhase::WorkerArtifactReturned => {
                    RestorationRecoveryAction::RetriedRequest
                }
                RestorationDurablePhase::ResultStored => {
                    RestorationRecoveryAction::AppliedValidatedResult
                }
                RestorationDurablePhase::MeetingPublished => {
                    RestorationRecoveryAction::WroteMissingCommit
                }
                RestorationDurablePhase::CommitStored => unreachable!(),
            };
            assert_eq!(
                report.operations,
                vec![RestorationRecoveryDisposition::Recovered {
                    operation_id: Uuid::parse_str(OPERATION_ID).unwrap(),
                    action: expected,
                }]
            );
        }
        assert_committed_successor(&fixture);
        let expected_calls = match phase {
            RestorationDurablePhase::RequestStored => 1,
            RestorationDurablePhase::WorkerArtifactReturned => 2,
            _ => 1,
        };
        assert_eq!(fixture.worker.calls(), expected_calls);
    }
}

#[test]
fn a_stored_result_has_no_authority_after_the_view_is_tampered() {
    let fixture = Fixture::new(false);
    let coordinator = fixture.coordinator(Arc::new(CrashOnce::new(
        RestorationDurablePhase::ResultStored,
    )));
    assert!(
        coordinator
            .restore_withheld_turn(&fixture.arguments(7))
            .is_err()
    );
    let StoredOperationResult::Restoration(result) = receipt(&fixture).result.unwrap() else {
        unreachable!();
    };
    durable_replace(&fixture.meeting_dir.join(result.view.relative_path), b"{}").unwrap();

    let report = fixture.reconstructed().recover_incomplete().unwrap();
    assert_eq!(
        report.operations,
        vec![RestorationRecoveryDisposition::Quarantined {
            meeting_id: fixture.meeting_id,
            operation_id: Some(Uuid::parse_str(OPERATION_ID).unwrap()),
            reason: RestorationQuarantineReason::InvalidArtifact,
        }]
    );
    assert_source_unchanged(&fixture);
    assert_eq!(
        receipt(&fixture).state(),
        OperationReceiptState::ResultStored
    );
}

#[test]
fn multiple_nonterminal_operations_are_quarantined_without_ordering() {
    let fixture = Fixture::new(false);
    let coordinator = fixture.coordinator(Arc::new(CrashOnce::new(
        RestorationDurablePhase::RequestStored,
    )));
    assert!(
        coordinator
            .restore_withheld_turn(&fixture.arguments(7))
            .is_err()
    );
    let mut second = match receipt(&fixture).request {
        StoredOperationRequest::Restoration(request) => request,
        StoredOperationRequest::NoteGeneration(_) => unreachable!(),
    };
    second.operation_id = Uuid::parse_str("33333333-3333-4333-8333-333333333333").unwrap();
    second.source_turn_index = 6;
    OperationStore::open(&fixture.storage)
        .unwrap()
        .write_request(&StoredOperationRequest::Restoration(second))
        .unwrap();

    let report = fixture.reconstructed().recover_incomplete().unwrap();
    assert_eq!(
        report.operations,
        vec![RestorationRecoveryDisposition::Quarantined {
            meeting_id: fixture.meeting_id,
            operation_id: None,
            reason: RestorationQuarantineReason::MultipleNonterminalOperations,
        }]
    );
    assert_source_unchanged(&fixture);
    assert_eq!(fixture.worker.calls(), 0);
}

#[test]
fn request_recovery_refuses_a_changed_prior_note_or_source() {
    for change_note in [true, false] {
        let fixture = Fixture::new(change_note);
        let coordinator = fixture.coordinator(Arc::new(CrashOnce::new(
            RestorationDurablePhase::RequestStored,
        )));
        assert!(
            coordinator
                .restore_withheld_turn(&fixture.arguments(7))
                .is_err()
        );
        let mut meeting = load_meeting(&fixture.meeting_dir).unwrap();
        if change_note {
            meeting.artifacts.current_note = Some(write_note(
                &fixture.meeting_dir,
                &fixture.base_sha256,
                "changed",
            ));
        } else {
            let changed = json!({
                "schema": "capture-transcript/1",
                "source": "changed",
                "attribution": "channel",
                "capture_health": {},
                "turns": [{"start":0.0,"end":1.0,"speaker":"Me","text":"changed","gated":true}]
            });
            let bytes = serde_json::to_vec_pretty(&changed).unwrap();
            let digest = digest_bytes(&bytes);
            durable_create_new(
                &fixture
                    .meeting_dir
                    .join("transcript")
                    .join(format!("{digest}.json")),
                &bytes,
            )
            .unwrap();
            meeting.artifacts.current_transcript = Some(
                artifact_ref(&fixture.meeting_dir, &format!("transcript/{digest}.json")).unwrap(),
            );
            meeting.artifacts.current_note = None;
            meeting.lifecycle = MeetingLifecycle::TranscriptReady;
        }
        write_meeting(&fixture.meeting_dir, &meeting).unwrap();

        let report = fixture.reconstructed().recover_incomplete().unwrap();
        assert_eq!(
            report.operations,
            vec![RestorationRecoveryDisposition::Quarantined {
                meeting_id: fixture.meeting_id,
                operation_id: Some(Uuid::parse_str(OPERATION_ID).unwrap()),
                reason: RestorationQuarantineReason::InvalidReceipt,
            }]
        );
        assert_eq!(fixture.worker.calls(), 0);
        assert_eq!(
            receipt(&fixture).state(),
            OperationReceiptState::RequestOnly
        );
    }
}

#[test]
fn missing_and_cyclic_successor_inspections_never_publish() {
    let missing = Fixture::new(false);
    *missing.worker.mode.lock().unwrap() = WorkerMode::MissingSuccessor;
    assert!(matches!(
        missing
            .reconstructed()
            .restore_withheld_turn(&missing.arguments(7)),
        Err(TranscriptRestorationCoordinatorError::Artifact(
            TranscriptArtifactError::Missing
        ))
    ));
    assert_source_unchanged(&missing);
    assert_eq!(
        receipt(&missing).state(),
        OperationReceiptState::RequestOnly
    );

    let cyclic = Fixture::new(false);
    let coordinator = TranscriptRestorationCoordinator::with_runtime(
        cyclic.storage.clone(),
        cyclic.coordination.clone(),
        cyclic.worker.clone(),
        Arc::new(FailSecondInspection {
            calls: Mutex::new(0),
        }),
        Arc::new(FixedIdentity::new(
            Uuid::parse_str(OPERATION_ID).unwrap(),
            [100, 101],
        )),
        Arc::new(NoRestorationFailureInjection),
    )
    .unwrap();
    assert!(matches!(
        coordinator.restore_withheld_turn(&cyclic.arguments(7)),
        Err(TranscriptRestorationCoordinatorError::Artifact(
            TranscriptArtifactError::Cyclic
        ))
    ));
    assert_source_unchanged(&cyclic);
    assert_eq!(receipt(&cyclic).state(), OperationReceiptState::RequestOnly);
}

#[test]
fn non_withheld_and_already_restored_turns_are_refused_before_a_new_receipt() {
    let fixture = Fixture::new(false);
    assert!(matches!(
        fixture
            .reconstructed()
            .restore_withheld_turn(&fixture.arguments(1)),
        Err(TranscriptRestorationCoordinatorError::Artifact(
            TranscriptArtifactError::NonWithheld
        ))
    ));
    assert!(
        OperationStore::open(&fixture.storage)
            .unwrap()
            .scan()
            .unwrap()
            .is_empty()
    );

    fixture
        .reconstructed()
        .restore_withheld_turn(&fixture.arguments(7))
        .unwrap();
    let second = TranscriptRestorationCoordinator::with_runtime(
        fixture.storage.clone(),
        fixture.coordination.clone(),
        fixture.worker.clone(),
        Arc::new(StoredTranscriptArtifactInspector),
        Arc::new(FixedIdentity::new(
            Uuid::parse_str("33333333-3333-4333-8333-333333333333").unwrap(),
            [200, 201],
        )),
        Arc::new(NoRestorationFailureInjection),
    )
    .unwrap();
    assert!(matches!(
        second.restore_withheld_turn(&fixture.arguments(7)),
        Err(TranscriptRestorationCoordinatorError::Ambiguous(
            "requested turn is already restored"
        ))
    ));
    assert_eq!(
        OperationStore::open(&fixture.storage)
            .unwrap()
            .scan()
            .unwrap()
            .len(),
        1
    );
}

#[test]
fn operation_id_and_artifact_collisions_do_not_overwrite_existing_bytes() {
    let fixture = Fixture::new(false);
    fixture
        .reconstructed()
        .restore_withheld_turn(&fixture.arguments(7))
        .unwrap();
    let original_request = read_private_bytes(
        &fixture
            .storage
            .path()
            .join("operations")
            .join(OPERATION_ID)
            .join("request.json"),
        crate::meeting::MAX_RECEIPT_BYTES,
    )
    .unwrap();
    let collision = TranscriptRestorationCoordinator::with_runtime(
        fixture.storage.clone(),
        fixture.coordination.clone(),
        fixture.worker.clone(),
        Arc::new(StoredTranscriptArtifactInspector),
        Arc::new(FixedIdentity::new(
            Uuid::parse_str(OPERATION_ID).unwrap(),
            [300, 301],
        )),
        Arc::new(NoRestorationFailureInjection),
    )
    .unwrap();
    assert!(matches!(
        collision.restore_withheld_turn(&fixture.arguments(6)),
        Err(TranscriptRestorationCoordinatorError::OperationStore(
            OperationStoreError::ConflictingBytes
        ))
    ));
    assert_eq!(
        read_private_bytes(
            &fixture
                .storage
                .path()
                .join("operations")
                .join(OPERATION_ID)
                .join("request.json"),
            crate::meeting::MAX_RECEIPT_BYTES,
        )
        .unwrap(),
        original_request
    );
    assert_eq!(
        fs::metadata(
            fixture
                .storage
                .path()
                .join("operations")
                .join(OPERATION_ID)
                .join("request.json")
        )
        .unwrap()
        .permissions()
        .mode()
            & 0o777,
        0o600
    );
}

#[test]
fn successor_artifact_collision_is_refused_without_overwrite_or_publication() {
    let fixture = Fixture::new(false);
    let view = TranscriptView {
        schema: crate::operations::TranscriptViewSchema::V1,
        meeting_id: fixture.meeting_id,
        base_transcript_sha256: fixture.base_sha256.clone(),
        parent_transcript_sha256: fixture.base_sha256.clone(),
        restored_source_turn_indices: vec![7],
    };
    let desired_bytes = serde_json::to_vec_pretty(&view).unwrap();
    let desired_digest = digest_bytes(&desired_bytes);
    let collision_path = fixture
        .meeting_dir
        .join("transcript")
        .join(format!("{desired_digest}.json"));
    durable_create_new(&collision_path, b"existing different bytes").unwrap();

    assert!(matches!(
        fixture
            .reconstructed()
            .restore_withheld_turn(&fixture.arguments(7)),
        Err(TranscriptRestorationCoordinatorError::Worker(
            TranscriptRestoreWorkerError::Refused
        ))
    ));
    assert_eq!(
        read_private_bytes(&collision_path, MAX_TRANSCRIPT_REVISION_BYTES).unwrap(),
        b"existing different bytes"
    );
    assert_source_unchanged(&fixture);
    assert_eq!(
        receipt(&fixture).state(),
        OperationReceiptState::RequestOnly
    );
}

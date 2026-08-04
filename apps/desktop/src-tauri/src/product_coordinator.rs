//! Storage-backed coordinator and worker-process bridge for the frozen
//! product operations behind `product_facade`.
//!
//! This supplies the real machinery the facade was designed around: restore
//! requests cross the supervised worker process boundary and the session-core
//! coordinator re-verifies every artifact from storage before publication.
//! Nothing here widens the packaged runtime's admission — an operation the
//! worker's frozen set excludes is refused by the worker itself and surfaces
//! through the facade's generic copy. Registering the facade commands (and
//! pairing each accepted synchronous operation with
//! `ProductOperationFacade::finish`, since `accept_restore` returns only after
//! the coordinator's terminal receipt) remains a separate slice gated on the
//! operator's admission decision.
//!
//! Note regeneration stays truthfully unavailable: `note.create` has no
//! admitted note generator, so a coordinator here could only relabel that
//! refusal.

use std::collections::HashMap;
use std::path::Path;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use local_meeting_notes_session_core::meeting::load_meeting;
use local_meeting_notes_session_core::meeting_coordination::MeetingStorageCoordination;
use local_meeting_notes_session_core::operations::TranscriptRestoreWorkerArgs;
use local_meeting_notes_session_core::protocol::{
    Operation, ProtocolError, WorkerCommand, WorkerResult,
};
use local_meeting_notes_session_core::retention::AppDataWriterLock;
use local_meeting_notes_session_core::storage::StorageRoot;
use local_meeting_notes_session_core::supervision::OwnedChild;
use local_meeting_notes_session_core::transcript_restoration::{
    StoredTranscriptArtifactInspector, TranscriptRestorationCoordinator,
    TranscriptRestorationCoordinatorError, TranscriptRestoreWorker, TranscriptRestoreWorkerError,
};
use serde_json::Value;
use uuid::Uuid;

use crate::product_facade::{
    CoordinatorError, MeetingOperationSource, ProductOperationCoordinator,
};
use crate::{StorageContext, WORKER_REQUEST_TIMEOUT};

/// One request/response exchange with the worker process. The seam exists so
/// bridge translation can be exercised without a live subprocess; the real
/// port owns the take-on-supervision-error semantics for the shared child.
pub(crate) trait WorkerPort: Send + Sync {
    fn request(
        &self,
        operation: Operation,
        arguments: Value,
        timeout: Duration,
    ) -> Result<WorkerResult, WorkerPortUnavailable>;
}

/// The worker process could not serve the exchange at all. Carries the
/// supervisor's own description for diagnostics; never worker content.
#[derive(Debug)]
pub(crate) struct WorkerPortUnavailable(pub(crate) String);

pub(crate) struct ProcessWorkerPort {
    worker: Arc<Mutex<Option<OwnedChild>>>,
}

impl ProcessWorkerPort {
    pub(crate) fn new(worker: Arc<Mutex<Option<OwnedChild>>>) -> Self {
        Self { worker }
    }
}

impl WorkerPort for ProcessWorkerPort {
    fn request(
        &self,
        operation: Operation,
        arguments: Value,
        timeout: Duration,
    ) -> Result<WorkerResult, WorkerPortUnavailable> {
        let command = WorkerCommand::new(operation, arguments);
        let mut guard = self
            .worker
            .lock()
            .map_err(|_| WorkerPortUnavailable("worker process lock is poisoned".into()))?;
        let Some(worker) = guard.as_mut() else {
            return Err(WorkerPortUnavailable("worker is unavailable".into()));
        };
        match worker.request_until(&command, Instant::now() + timeout, |_| {
            Err(ProtocolError::InvalidEvent)
        }) {
            Ok(result) => Ok(result),
            Err(error) => {
                guard.take();
                Err(WorkerPortUnavailable(error.to_string()))
            }
        }
    }
}

/// Sends `transcript.restore` across the process boundary. The returned digest
/// map is a claim only; the coordinator re-reads and re-verifies the artifacts
/// it names before anything is published.
pub(crate) struct WorkerProcessRestoreBridge {
    port: Arc<dyn WorkerPort>,
}

impl WorkerProcessRestoreBridge {
    pub(crate) fn new(port: Arc<dyn WorkerPort>) -> Self {
        Self { port }
    }
}

impl TranscriptRestoreWorker for WorkerProcessRestoreBridge {
    fn restore(
        &self,
        arguments: &TranscriptRestoreWorkerArgs,
    ) -> Result<HashMap<String, String>, TranscriptRestoreWorkerError> {
        let arguments = serde_json::to_value(arguments)
            .map_err(|_| TranscriptRestoreWorkerError::Unavailable)?;
        let result = self
            .port
            .request(
                Operation::TranscriptRestore,
                arguments,
                WORKER_REQUEST_TIMEOUT,
            )
            .map_err(|_| TranscriptRestoreWorkerError::Unavailable)?;
        if result.ok {
            Ok(result.artifact_digests)
        } else {
            Err(TranscriptRestoreWorkerError::Refused)
        }
    }
}

/// The storage-backed `ProductOperationCoordinator`. Holds live handles to the
/// application's storage, writer-lock, and worker slots so every call reads
/// the current runtime state instead of a startup snapshot.
pub(crate) struct DesktopProductCoordinator {
    storage: Arc<Mutex<Option<StorageContext>>>,
    app_data_writer_lock: Arc<Mutex<Option<AppDataWriterLock>>>,
    port: Arc<dyn WorkerPort>,
}

impl DesktopProductCoordinator {
    pub(crate) fn new(
        storage: Arc<Mutex<Option<StorageContext>>>,
        app_data_writer_lock: Arc<Mutex<Option<AppDataWriterLock>>>,
        port: Arc<dyn WorkerPort>,
    ) -> Self {
        Self {
            storage,
            app_data_writer_lock,
            port,
        }
    }

    fn storage_root(&self) -> Result<StorageRoot, CoordinatorError> {
        self.storage
            .lock()
            .map_err(|_| CoordinatorError::Unavailable)?
            .as_ref()
            .map(|context| context.storage.clone())
            .ok_or(CoordinatorError::Unavailable)
    }

    fn coordination(&self) -> Result<Arc<MeetingStorageCoordination>, CoordinatorError> {
        self.app_data_writer_lock
            .lock()
            .map_err(|_| CoordinatorError::Unavailable)?
            .as_ref()
            .map(AppDataWriterLock::coordination)
            .ok_or(CoordinatorError::Unavailable)
    }

    fn restoration_coordinator(
        &self,
    ) -> Result<TranscriptRestorationCoordinator, CoordinatorError> {
        TranscriptRestorationCoordinator::new(
            self.storage_root()?,
            self.coordination()?,
            Arc::new(WorkerProcessRestoreBridge::new(self.port.clone())),
            Arc::new(StoredTranscriptArtifactInspector),
        )
        .map_err(|_| CoordinatorError::Unavailable)
    }
}

impl ProductOperationCoordinator for DesktopProductCoordinator {
    /// A lease-free read the facade uses as its optimistic pre-check. The
    /// coordinator repeats every check authoritatively under the meeting
    /// lease, so this reflects the stored record without re-hashing artifacts.
    fn source_for(&self, meeting_id: Uuid) -> Result<MeetingOperationSource, CoordinatorError> {
        let storage = self.storage_root()?;
        let meeting_dir = storage
            .resolve(&Path::new("meetings").join(meeting_id.to_string()))
            .map_err(|_| CoordinatorError::Unavailable)?;
        let meeting = load_meeting(&meeting_dir).map_err(|_| CoordinatorError::Unavailable)?;
        let record_meeting_id =
            Uuid::parse_str(&meeting.meeting_id).map_err(|_| CoordinatorError::Refused)?;
        let current = meeting
            .artifacts
            .current_transcript
            .as_ref()
            .ok_or(CoordinatorError::Refused)?;
        Ok(MeetingOperationSource {
            meeting_id: record_meeting_id,
            current_transcript_sha256: current.sha256.clone(),
            lifecycle: meeting.lifecycle,
            has_current_note: meeting.artifacts.current_note.is_some(),
        })
    }

    fn accept_restore(
        &self,
        args: &local_meeting_notes_session_core::operations::RestoreWithheldTurnUiArgs,
    ) -> Result<Uuid, CoordinatorError> {
        self.restoration_coordinator()?
            .restore_withheld_turn(args)
            .map_err(|error| match error {
                TranscriptRestorationCoordinatorError::Worker(
                    TranscriptRestoreWorkerError::Unavailable,
                )
                | TranscriptRestorationCoordinatorError::StorageUnavailable => {
                    CoordinatorError::Unavailable
                }
                _ => CoordinatorError::Refused,
            })
    }

    fn accept_regeneration(
        &self,
        _args: &local_meeting_notes_session_core::operations::RegenerateNoteUiArgs,
    ) -> Result<Uuid, CoordinatorError> {
        // No note generator is admitted (`note.create` refuses without one),
        // so regeneration cannot reach a terminal receipt yet. Report the
        // refusal here instead of relabeling it through a coordinator.
        Err(CoordinatorError::Unavailable)
    }
}

#[cfg(test)]
mod tests {
    use std::path::PathBuf;

    use local_meeting_notes_session_core::meeting::AudioState;
    use local_meeting_notes_session_core::meeting::MeetingLifecycle;
    use local_meeting_notes_session_core::operations::{
        RegenerateNoteUiArgs, RestoreWithheldTurnUiArgs,
    };
    use local_meeting_notes_session_core::protocol::ResultSchema;
    use serde_json::json;
    use sha2::{Digest, Sha256};

    use super::*;
    use crate::product_facade::{ProductOperationFacade, ProductOperationFacadeError};
    use crate::tests::{test_storage, write_transcript_fixture_with_turns};
    use crate::{ApplicationState, ensure_app_data_writer_lock};

    enum FakeOutcome {
        Accept(HashMap<String, String>),
        Refuse,
        Unavailable,
    }

    struct FakePort {
        requests: Mutex<Vec<(Operation, Value)>>,
        outcome: FakeOutcome,
    }

    impl FakePort {
        fn new(outcome: FakeOutcome) -> Self {
            Self {
                requests: Mutex::new(Vec::new()),
                outcome,
            }
        }
    }

    impl WorkerPort for FakePort {
        fn request(
            &self,
            operation: Operation,
            arguments: Value,
            _timeout: Duration,
        ) -> Result<WorkerResult, WorkerPortUnavailable> {
            self.requests.lock().unwrap().push((operation, arguments));
            match &self.outcome {
                FakeOutcome::Accept(digests) => Ok(worker_result(true, digests.clone())),
                FakeOutcome::Refuse => Ok(worker_result(false, HashMap::new())),
                FakeOutcome::Unavailable => {
                    Err(WorkerPortUnavailable("worker is unavailable".into()))
                }
            }
        }
    }

    fn worker_result(ok: bool, artifact_digests: HashMap<String, String>) -> WorkerResult {
        WorkerResult {
            schema: ResultSchema::V2,
            request_id: Uuid::new_v4(),
            ok,
            code: None,
            recoverable: None,
            artifact_digests,
        }
    }

    fn restore_args(meeting_id: Uuid, sha256: &str, index: u32) -> TranscriptRestoreWorkerArgs {
        TranscriptRestoreWorkerArgs {
            meeting_id,
            source_transcript_sha256: sha256.into(),
            source_turn_index: index,
        }
    }

    /// The bridge's serialized arguments are the Python contract's exact key
    /// set; drift here would be refused by the worker at runtime only.
    #[test]
    fn restore_bridge_pins_the_wire_shape_and_passes_digests_through() {
        let digests: HashMap<String, String> = [
            ("base-transcript", "a"),
            ("parent-transcript", "b"),
            ("transcript", "c"),
        ]
        .into_iter()
        .map(|(key, value)| (key.to_string(), value.repeat(64)))
        .collect();
        let port = Arc::new(FakePort::new(FakeOutcome::Accept(digests.clone())));
        let bridge = WorkerProcessRestoreBridge::new(port.clone());

        let meeting_id = Uuid::new_v4();
        let sha256 = "d".repeat(64);
        let returned = bridge
            .restore(&restore_args(meeting_id, &sha256, 3))
            .unwrap();
        assert_eq!(returned, digests);

        let requests = port.requests.lock().unwrap();
        assert_eq!(requests.len(), 1);
        assert_eq!(requests[0].0, Operation::TranscriptRestore);
        assert_eq!(
            requests[0].1,
            json!({
                "meeting_id": meeting_id.to_string(),
                "source_transcript_sha256": sha256,
                "source_turn_index": 3,
            })
        );
    }

    #[test]
    fn restore_bridge_maps_refusal_and_absence_to_typed_errors() {
        let refused = WorkerProcessRestoreBridge::new(Arc::new(FakePort::new(FakeOutcome::Refuse)));
        assert_eq!(
            refused.restore(&restore_args(Uuid::new_v4(), &"e".repeat(64), 0)),
            Err(TranscriptRestoreWorkerError::Refused)
        );

        let absent =
            WorkerProcessRestoreBridge::new(Arc::new(FakePort::new(FakeOutcome::Unavailable)));
        assert_eq!(
            absent.restore(&restore_args(Uuid::new_v4(), &"e".repeat(64), 0)),
            Err(TranscriptRestoreWorkerError::Unavailable)
        );
    }

    fn empty_runtime_coordinator() -> DesktopProductCoordinator {
        DesktopProductCoordinator::new(
            Arc::new(Mutex::new(None)),
            Arc::new(Mutex::new(None)),
            Arc::new(FakePort::new(FakeOutcome::Refuse)),
        )
    }

    #[test]
    fn coordinator_reports_unavailable_before_the_runtime_exists() {
        let coordinator = empty_runtime_coordinator();
        assert_eq!(
            coordinator.source_for(Uuid::new_v4()),
            Err(CoordinatorError::Unavailable)
        );
        assert_eq!(
            coordinator.accept_restore(&RestoreWithheldTurnUiArgs {
                meeting_id: Uuid::new_v4(),
                source_transcript_sha256: "f".repeat(64),
                source_turn_index: 0,
            }),
            Err(CoordinatorError::Unavailable)
        );
        assert_eq!(
            coordinator.accept_regeneration(&RegenerateNoteUiArgs {
                meeting_id: Uuid::new_v4(),
                source_transcript_sha256: "f".repeat(64),
            }),
            Err(CoordinatorError::Unavailable)
        );
    }

    struct RuntimeFixture {
        // Owns the tempdir for the fixture's lifetime.
        _temporary: tempfile::TempDir,
        state: ApplicationState,
        meeting_id: Uuid,
        transcript_sha256: String,
    }

    fn runtime_fixture(turns: Value) -> RuntimeFixture {
        let (temporary, storage) = test_storage();
        let meeting_id = Uuid::new_v4();
        let transcript_path = write_transcript_fixture_with_turns(
            &storage,
            &meeting_id.to_string(),
            1_700_000_000,
            AudioState::Retained,
            turns,
        );
        let transcript_sha256 = format!(
            "{:x}",
            Sha256::digest(std::fs::read(&transcript_path).unwrap())
        );
        let state = ApplicationState::default();
        ensure_app_data_writer_lock(&state, &storage).unwrap();
        *state.storage.lock().unwrap() = Some(StorageContext {
            storage,
            resource_root: PathBuf::from("/unused"),
            manifest_path: PathBuf::from("/unused"),
            diagnostics: temporary.path().join("diagnostics"),
        });
        RuntimeFixture {
            _temporary: temporary,
            state,
            meeting_id,
            transcript_sha256,
        }
    }

    fn coordinator_for(
        fixture: &RuntimeFixture,
        port: Arc<dyn WorkerPort>,
    ) -> DesktopProductCoordinator {
        DesktopProductCoordinator::new(
            fixture.state.storage.clone(),
            fixture.state.app_data_writer_lock.clone(),
            port,
        )
    }

    fn gated_turns() -> Value {
        json!([
            { "start": 0.0, "end": 1.0, "speaker": "Me", "text": "kept" },
            { "start": 1.0, "end": 2.0, "speaker": "Me", "text": "", "gated": true },
        ])
    }

    #[test]
    fn source_for_reflects_the_stored_meeting_record() {
        let fixture = runtime_fixture(gated_turns());
        let coordinator = coordinator_for(&fixture, Arc::new(FakePort::new(FakeOutcome::Refuse)));
        let source = coordinator.source_for(fixture.meeting_id).unwrap();
        assert_eq!(source.meeting_id, fixture.meeting_id);
        assert_eq!(source.current_transcript_sha256, fixture.transcript_sha256);
        assert_eq!(source.lifecycle, MeetingLifecycle::TranscriptReady);
        assert!(!source.has_current_note);
    }

    /// The full desktop assembly — storage handles, meeting lease, record
    /// verification, withheld-index sourcing — must carry a restore request
    /// all the way to the worker seam, and a worker refusal must come back as
    /// a typed refusal rather than a panic or a fabricated acceptance.
    #[test]
    fn accept_restore_drives_the_real_coordinator_to_the_worker_seam() {
        let fixture = runtime_fixture(gated_turns());
        let port = Arc::new(FakePort::new(FakeOutcome::Refuse));
        let coordinator = coordinator_for(&fixture, port.clone());

        let result = coordinator.accept_restore(&RestoreWithheldTurnUiArgs {
            meeting_id: fixture.meeting_id,
            source_transcript_sha256: fixture.transcript_sha256.clone(),
            source_turn_index: 1,
        });
        assert_eq!(result, Err(CoordinatorError::Refused));

        let requests = port.requests.lock().unwrap();
        assert_eq!(requests.len(), 1);
        assert_eq!(requests[0].0, Operation::TranscriptRestore);
        assert_eq!(
            requests[0].1,
            json!({
                "meeting_id": fixture.meeting_id.to_string(),
                "source_transcript_sha256": fixture.transcript_sha256,
                "source_turn_index": 1,
            })
        );
    }

    /// A turn that is not withheld must be refused before the worker is ever
    /// consulted — restoration of ordinary text is not a reachable request.
    #[test]
    fn accept_restore_refuses_a_non_withheld_turn_before_the_worker() {
        let fixture = runtime_fixture(gated_turns());
        let port = Arc::new(FakePort::new(FakeOutcome::Refuse));
        let coordinator = coordinator_for(&fixture, port.clone());

        let result = coordinator.accept_restore(&RestoreWithheldTurnUiArgs {
            meeting_id: fixture.meeting_id,
            source_transcript_sha256: fixture.transcript_sha256.clone(),
            source_turn_index: 0,
        });
        assert_eq!(result, Err(CoordinatorError::Refused));
        assert!(port.requests.lock().unwrap().is_empty());
    }

    /// The exact assembly main() manages: facade over the desktop coordinator.
    /// The pre-check passes against the stored record (so the failure is not
    /// SourceChanged) and the worker refusal surfaces as the generic copy.
    #[test]
    fn the_managed_facade_assembly_reaches_the_worker_seam() {
        let fixture = runtime_fixture(gated_turns());
        let port = Arc::new(FakePort::new(FakeOutcome::Refuse));
        let facade = ProductOperationFacade::new(Arc::new(coordinator_for(&fixture, port.clone())));

        let result = facade.restore_withheld_turn(RestoreWithheldTurnUiArgs {
            meeting_id: fixture.meeting_id,
            source_transcript_sha256: fixture.transcript_sha256.clone(),
            source_turn_index: 1,
        });
        assert_eq!(
            result,
            Err(ProductOperationFacadeError::OperationUnavailable)
        );
        assert_eq!(port.requests.lock().unwrap().len(), 1);
    }

    #[test]
    fn regeneration_stays_truthfully_unavailable_even_with_a_live_runtime() {
        let fixture = runtime_fixture(gated_turns());
        let port = Arc::new(FakePort::new(FakeOutcome::Accept(HashMap::new())));
        let coordinator = coordinator_for(&fixture, port.clone());
        assert_eq!(
            coordinator.accept_regeneration(&RegenerateNoteUiArgs {
                meeting_id: fixture.meeting_id,
                source_transcript_sha256: fixture.transcript_sha256.clone(),
            }),
            Err(CoordinatorError::Unavailable)
        );
        assert!(port.requests.lock().unwrap().is_empty());
    }
}

//! Internal command boundary for the frozen correction and note-regeneration shapes.
//!
//! This module is intentionally absent from `tauri::generate_handler!`. A later
//! storage-backed coordinator must be installed and the product surface must opt
//! into these commands only after its own contract and review are complete.

use std::sync::{Arc, Mutex};

use local_meeting_notes_session_core::meeting::MeetingLifecycle;
use local_meeting_notes_session_core::operations::{
    ProductOperationKind, RegenerateNoteUiArgs, RestoreWithheldTurnUiArgs, UiOperationAccepted,
    UiOperationSchema, UiOperationState,
};
use tauri::State;
use uuid::Uuid;

const SOURCE_CHANGED_COPY: &str = "The transcript changed. Refresh the meeting and try again.";
const OPERATION_UNAVAILABLE_COPY: &str = "This action is not available right now. Try again.";
const OPERATION_ACTIVE_COPY: &str = "Another meeting action is already in progress.";

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct MeetingOperationSource {
    pub meeting_id: Uuid,
    pub current_transcript_sha256: String,
    pub lifecycle: MeetingLifecycle,
    pub has_current_note: bool,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum CoordinatorError {
    Unavailable,
    Refused,
}

/// The future storage/worker owner. It must re-check the current source while
/// preparing its durable operation receipt; this facade deliberately owns none
/// of that persistence or worker protocol.
pub(crate) trait ProductOperationCoordinator: Send + Sync {
    fn source_for(&self, meeting_id: Uuid) -> Result<MeetingOperationSource, CoordinatorError>;

    fn accept_restore(&self, args: &RestoreWithheldTurnUiArgs) -> Result<Uuid, CoordinatorError>;

    fn accept_regeneration(&self, args: &RegenerateNoteUiArgs) -> Result<Uuid, CoordinatorError>;
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum ProductOperationFacadeError {
    SourceChanged,
    OperationUnavailable,
    OperationAlreadyActive,
}

impl ProductOperationFacadeError {
    fn safe_copy(self) -> &'static str {
        match self {
            Self::SourceChanged => SOURCE_CHANGED_COPY,
            Self::OperationUnavailable => OPERATION_UNAVAILABLE_COPY,
            Self::OperationAlreadyActive => OPERATION_ACTIVE_COPY,
        }
    }
}

pub(crate) struct ProductOperationFacade {
    coordinator: Arc<dyn ProductOperationCoordinator>,
    active: Mutex<Option<UiOperationAccepted>>,
}

impl ProductOperationFacade {
    pub(crate) fn new(coordinator: Arc<dyn ProductOperationCoordinator>) -> Self {
        Self {
            coordinator,
            active: Mutex::new(None),
        }
    }

    pub(crate) fn restore_withheld_turn(
        &self,
        args: RestoreWithheldTurnUiArgs,
    ) -> Result<UiOperationAccepted, ProductOperationFacadeError> {
        args.validate()
            .map_err(|_| ProductOperationFacadeError::SourceChanged)?;
        self.accept(
            args.meeting_id,
            &args.source_transcript_sha256,
            ProductOperationKind::RestoreWithheldTurn,
            UiOperationState::Correcting,
            |source| {
                matches!(
                    source.lifecycle,
                    MeetingLifecycle::TranscriptReady
                        | MeetingLifecycle::SummaryFailed
                        | MeetingLifecycle::Ready
                )
            },
            || self.coordinator.accept_restore(&args),
        )
    }

    pub(crate) fn regenerate_note(
        &self,
        args: RegenerateNoteUiArgs,
    ) -> Result<UiOperationAccepted, ProductOperationFacadeError> {
        args.validate()
            .map_err(|_| ProductOperationFacadeError::SourceChanged)?;
        self.accept(
            args.meeting_id,
            &args.source_transcript_sha256,
            ProductOperationKind::GenerateNote,
            UiOperationState::Summarizing,
            |source| {
                !source.has_current_note
                    && matches!(
                        source.lifecycle,
                        MeetingLifecycle::TranscriptReady | MeetingLifecycle::SummaryFailed
                    )
            },
            || self.coordinator.accept_regeneration(&args),
        )
    }

    fn accept(
        &self,
        meeting_id: Uuid,
        source_transcript_sha256: &str,
        kind: ProductOperationKind,
        state: UiOperationState,
        source_is_eligible: impl FnOnce(&MeetingOperationSource) -> bool,
        accept: impl FnOnce() -> Result<Uuid, CoordinatorError>,
    ) -> Result<UiOperationAccepted, ProductOperationFacadeError> {
        let mut active = self
            .active
            .lock()
            .map_err(|_| ProductOperationFacadeError::OperationUnavailable)?;
        if active.is_some() {
            return Err(ProductOperationFacadeError::OperationAlreadyActive);
        }

        let source = self
            .coordinator
            .source_for(meeting_id)
            .map_err(|_| ProductOperationFacadeError::OperationUnavailable)?;
        if source.meeting_id != meeting_id
            || source.current_transcript_sha256 != source_transcript_sha256
            || !source_is_eligible(&source)
        {
            return Err(ProductOperationFacadeError::SourceChanged);
        }

        let accepted = UiOperationAccepted {
            schema: UiOperationSchema::V1,
            operation_id: accept()
                .map_err(|_| ProductOperationFacadeError::OperationUnavailable)?,
            meeting_id,
            kind,
            state,
        };
        accepted
            .validate()
            .map_err(|_| ProductOperationFacadeError::OperationUnavailable)?;
        *active = Some(accepted.clone());
        Ok(accepted)
    }

    /// Called only by the future coordinator after it reaches a terminal receipt.
    pub(crate) fn finish(&self, operation_id: Uuid) {
        let Ok(mut active) = self.active.lock() else {
            return;
        };
        if active
            .as_ref()
            .is_some_and(|operation| operation.operation_id == operation_id)
        {
            *active = None;
        }
    }
}

/// Unregistered Tauri command. Do not add it to `invoke_handler` until a
/// storage-backed coordinator has joined the frozen operation receipts.
#[tauri::command]
pub(crate) fn restore_withheld_turn(
    args: RestoreWithheldTurnUiArgs,
    facade: State<'_, ProductOperationFacade>,
) -> Result<UiOperationAccepted, String> {
    facade
        .restore_withheld_turn(args)
        .map_err(ProductOperationFacadeError::safe_copy)
        .map_err(str::to_owned)
}

/// Unregistered Tauri command. See `restore_withheld_turn` above.
#[tauri::command]
pub(crate) fn regenerate_note(
    args: RegenerateNoteUiArgs,
    facade: State<'_, ProductOperationFacade>,
) -> Result<UiOperationAccepted, String> {
    facade
        .regenerate_note(args)
        .map_err(ProductOperationFacadeError::safe_copy)
        .map_err(str::to_owned)
}

#[cfg(test)]
mod tests {
    use std::sync::Mutex;

    use serde::de::DeserializeOwned;
    use serde_json::Value;

    use super::*;

    struct FakeCoordinator {
        source: Mutex<Result<MeetingOperationSource, CoordinatorError>>,
        restore_result: Mutex<Result<Uuid, CoordinatorError>>,
        regeneration_result: Mutex<Result<Uuid, CoordinatorError>>,
        restore_calls: Mutex<u32>,
        regeneration_calls: Mutex<u32>,
    }

    impl FakeCoordinator {
        fn accepting(
            source: MeetingOperationSource,
            restore_id: Uuid,
            regeneration_id: Uuid,
        ) -> Self {
            Self {
                source: Mutex::new(Ok(source)),
                restore_result: Mutex::new(Ok(restore_id)),
                regeneration_result: Mutex::new(Ok(regeneration_id)),
                restore_calls: Mutex::new(0),
                regeneration_calls: Mutex::new(0),
            }
        }
    }

    impl ProductOperationCoordinator for FakeCoordinator {
        fn source_for(&self, _: Uuid) -> Result<MeetingOperationSource, CoordinatorError> {
            self.source.lock().unwrap().clone()
        }

        fn accept_restore(&self, _: &RestoreWithheldTurnUiArgs) -> Result<Uuid, CoordinatorError> {
            *self.restore_calls.lock().unwrap() += 1;
            *self.restore_result.lock().unwrap()
        }

        fn accept_regeneration(&self, _: &RegenerateNoteUiArgs) -> Result<Uuid, CoordinatorError> {
            *self.regeneration_calls.lock().unwrap() += 1;
            *self.regeneration_result.lock().unwrap()
        }
    }

    fn fixture() -> Value {
        serde_json::from_str(include_str!(concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/../../../tests/fixtures/product-operations-v1.json"
        )))
        .unwrap()
    }

    fn at(root: &Value, path: &[&str]) -> Value {
        path.iter()
            .fold(root, |value, segment| &value[*segment])
            .clone()
    }

    fn parse<T: DeserializeOwned>(root: &Value, path: &[&str]) -> T {
        serde_json::from_value(at(root, path)).unwrap()
    }

    fn source_for(
        meeting_id: Uuid,
        current_transcript_sha256: String,
        lifecycle: MeetingLifecycle,
        has_current_note: bool,
    ) -> MeetingOperationSource {
        MeetingOperationSource {
            meeting_id,
            current_transcript_sha256,
            lifecycle,
            has_current_note,
        }
    }

    #[test]
    fn shared_fixture_freezes_the_accepted_facade_states() {
        let fixture = fixture();

        let restore_args: RestoreWithheldTurnUiArgs =
            parse(&fixture, &["restoration", "ui_arguments"]);
        let restore_expected: UiOperationAccepted =
            parse(&fixture, &["restoration", "ui_response"]);
        let restore_coordinator = Arc::new(FakeCoordinator::accepting(
            source_for(
                restore_args.meeting_id,
                restore_args.source_transcript_sha256.clone(),
                MeetingLifecycle::Ready,
                true,
            ),
            restore_expected.operation_id,
            Uuid::nil(),
        ));
        let restore_facade = ProductOperationFacade::new(restore_coordinator.clone());
        assert_eq!(
            restore_facade.restore_withheld_turn(restore_args).unwrap(),
            restore_expected
        );
        assert_eq!(*restore_coordinator.restore_calls.lock().unwrap(), 1);

        let note_args: RegenerateNoteUiArgs = parse(&fixture, &["accepted_note", "ui_arguments"]);
        let note_expected: UiOperationAccepted = parse(&fixture, &["accepted_note", "ui_response"]);
        let note_coordinator = Arc::new(FakeCoordinator::accepting(
            source_for(
                note_args.meeting_id,
                note_args.source_transcript_sha256.clone(),
                MeetingLifecycle::TranscriptReady,
                false,
            ),
            Uuid::nil(),
            note_expected.operation_id,
        ));
        let note_facade = ProductOperationFacade::new(note_coordinator.clone());
        assert_eq!(
            note_facade.regenerate_note(note_args).unwrap(),
            note_expected
        );
        assert_eq!(*note_coordinator.regeneration_calls.lock().unwrap(), 1);
    }

    #[test]
    fn stale_source_and_coordinator_refusal_do_not_start_an_operation() {
        let fixture = fixture();
        let args: RestoreWithheldTurnUiArgs = parse(&fixture, &["restoration", "ui_arguments"]);
        let expected: UiOperationAccepted = parse(&fixture, &["restoration", "ui_response"]);
        let coordinator = Arc::new(FakeCoordinator::accepting(
            source_for(
                args.meeting_id,
                "b".repeat(64),
                MeetingLifecycle::Ready,
                true,
            ),
            expected.operation_id,
            Uuid::nil(),
        ));
        let facade = ProductOperationFacade::new(coordinator.clone());
        assert_eq!(
            facade.restore_withheld_turn(args.clone()),
            Err(ProductOperationFacadeError::SourceChanged)
        );
        assert_eq!(*coordinator.restore_calls.lock().unwrap(), 0);

        *coordinator.source.lock().unwrap() = Ok(source_for(
            args.meeting_id,
            args.source_transcript_sha256.clone(),
            MeetingLifecycle::Ready,
            true,
        ));
        *coordinator.restore_result.lock().unwrap() = Err(CoordinatorError::Refused);
        assert_eq!(
            facade.restore_withheld_turn(args),
            Err(ProductOperationFacadeError::OperationUnavailable)
        );
        assert_eq!(*coordinator.restore_calls.lock().unwrap(), 1);
    }

    #[test]
    fn a_second_operation_is_refused_until_the_first_reaches_a_terminal_receipt() {
        let fixture = fixture();
        let args: RegenerateNoteUiArgs = parse(&fixture, &["accepted_note", "ui_arguments"]);
        let expected: UiOperationAccepted = parse(&fixture, &["accepted_note", "ui_response"]);
        let coordinator = Arc::new(FakeCoordinator::accepting(
            source_for(
                args.meeting_id,
                args.source_transcript_sha256.clone(),
                MeetingLifecycle::TranscriptReady,
                false,
            ),
            Uuid::nil(),
            expected.operation_id,
        ));
        let facade = ProductOperationFacade::new(coordinator.clone());
        let accepted = facade.regenerate_note(args.clone()).unwrap();
        assert_eq!(
            facade.regenerate_note(args.clone()),
            Err(ProductOperationFacadeError::OperationAlreadyActive)
        );
        assert_eq!(*coordinator.regeneration_calls.lock().unwrap(), 1);

        facade.finish(accepted.operation_id);
        assert_eq!(facade.regenerate_note(args).unwrap(), expected);
        assert_eq!(*coordinator.regeneration_calls.lock().unwrap(), 2);
    }

    #[test]
    fn coordinator_failures_have_generic_safe_copy() {
        let fixture = fixture();
        let args: RegenerateNoteUiArgs = parse(&fixture, &["accepted_note", "ui_arguments"]);
        let coordinator = Arc::new(FakeCoordinator::accepting(
            source_for(
                args.meeting_id,
                args.source_transcript_sha256.clone(),
                MeetingLifecycle::TranscriptReady,
                false,
            ),
            Uuid::nil(),
            Uuid::nil(),
        ));
        *coordinator.source.lock().unwrap() = Err(CoordinatorError::Unavailable);
        let facade = ProductOperationFacade::new(coordinator);

        assert_eq!(
            facade.regenerate_note(args).unwrap_err().safe_copy(),
            OPERATION_UNAVAILABLE_COPY
        );
    }
}

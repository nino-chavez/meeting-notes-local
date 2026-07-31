use serde::{Deserialize, Serialize};
use thiserror::Error;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum StartupState {
    ShellRendered,
    Checking,
    Ready,
    RuntimeMissing,
    ServiceTimeout,
    DiagnosticWritten,
    Retrying,
    ReinstallRequired,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum CaptureState {
    Idle,
    Arming,
    Recording,
    Stopping,
    Captured,
    Transcribing,
    Summarizing,
    Ready,
    TranscriptionFailed,
    SummaryFailed,
    RecoveredInterrupted,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ExclusiveOperation {
    StartupRecovery,
    CaptureTransition,
    DestructiveStorage,
}

#[derive(Debug, Error, PartialEq, Eq)]
pub enum ReducerError {
    #[error("another exclusive operation is already active")]
    DuplicateOperation,
    #[error("invalid startup transition from {from:?} to {to:?}")]
    InvalidStartupTransition {
        from: StartupState,
        to: StartupState,
    },
    #[error("invalid capture transition from {from:?} to {to:?}")]
    InvalidCaptureTransition {
        from: CaptureState,
        to: CaptureState,
    },
}

#[derive(Debug)]
pub struct Reducer {
    startup: StartupState,
    capture: CaptureState,
    exclusive: Option<ExclusiveOperation>,
}

impl Default for Reducer {
    fn default() -> Self {
        Self {
            startup: StartupState::ShellRendered,
            capture: CaptureState::Idle,
            exclusive: None,
        }
    }
}

impl Reducer {
    pub fn startup(&self) -> StartupState {
        self.startup
    }

    pub fn capture(&self) -> CaptureState {
        self.capture
    }

    pub fn begin(&mut self, operation: ExclusiveOperation) -> Result<(), ReducerError> {
        if self.exclusive.is_some() {
            return Err(ReducerError::DuplicateOperation);
        }
        self.exclusive = Some(operation);
        Ok(())
    }

    pub fn finish(&mut self, operation: ExclusiveOperation) {
        if self.exclusive == Some(operation) {
            self.exclusive = None;
        }
    }

    pub fn transition_startup(&mut self, to: StartupState) -> Result<(), ReducerError> {
        let valid = matches!(
            (self.startup, to),
            (StartupState::ShellRendered, StartupState::Checking)
                | (StartupState::Checking, StartupState::Ready)
                | (StartupState::Checking, StartupState::RuntimeMissing)
                | (StartupState::Checking, StartupState::ServiceTimeout)
                | (StartupState::Checking, StartupState::DiagnosticWritten)
                | (StartupState::RuntimeMissing, StartupState::Retrying)
                | (StartupState::ServiceTimeout, StartupState::Retrying)
                | (StartupState::DiagnosticWritten, StartupState::Retrying)
                | (StartupState::Retrying, StartupState::Ready)
                | (StartupState::Retrying, StartupState::RuntimeMissing)
                | (StartupState::Retrying, StartupState::ServiceTimeout)
                | (StartupState::Retrying, StartupState::ReinstallRequired)
        );
        if !valid {
            return Err(ReducerError::InvalidStartupTransition {
                from: self.startup,
                to,
            });
        }
        self.startup = to;
        Ok(())
    }

    pub fn transition_capture(&mut self, to: CaptureState) -> Result<(), ReducerError> {
        let valid = matches!(
            (self.capture, to),
            (CaptureState::Idle, CaptureState::Arming)
                | (CaptureState::Arming, CaptureState::Recording)
                | (CaptureState::Arming, CaptureState::RecoveredInterrupted)
                | (CaptureState::Recording, CaptureState::Stopping)
                | (CaptureState::Recording, CaptureState::RecoveredInterrupted)
                | (CaptureState::Stopping, CaptureState::Captured)
                | (CaptureState::Stopping, CaptureState::RecoveredInterrupted)
                | (CaptureState::Captured, CaptureState::Transcribing)
                | (CaptureState::Transcribing, CaptureState::Summarizing)
                | (
                    CaptureState::Transcribing,
                    CaptureState::TranscriptionFailed
                )
                | (
                    CaptureState::TranscriptionFailed,
                    CaptureState::Transcribing
                )
                | (CaptureState::Summarizing, CaptureState::Ready)
                | (CaptureState::Summarizing, CaptureState::SummaryFailed)
                | (CaptureState::SummaryFailed, CaptureState::Summarizing)
                | (CaptureState::Ready, CaptureState::Idle)
                | (CaptureState::RecoveredInterrupted, CaptureState::Idle)
        );
        if !valid {
            return Err(ReducerError::InvalidCaptureTransition {
                from: self.capture,
                to,
            });
        }
        self.capture = to;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn refuses_duplicate_exclusive_operation() {
        let mut reducer = Reducer::default();
        reducer
            .begin(ExclusiveOperation::CaptureTransition)
            .unwrap();
        assert_eq!(
            reducer.begin(ExclusiveOperation::StartupRecovery),
            Err(ReducerError::DuplicateOperation)
        );
    }

    #[test]
    fn rejected_summary_never_reaches_ready_directly() {
        let mut reducer = Reducer {
            capture: CaptureState::SummaryFailed,
            ..Reducer::default()
        };
        assert!(reducer.transition_capture(CaptureState::Ready).is_err());
        reducer
            .transition_capture(CaptureState::Summarizing)
            .unwrap();
        reducer.transition_capture(CaptureState::Ready).unwrap();
    }
}

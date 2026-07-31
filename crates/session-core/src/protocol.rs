use std::collections::{HashMap, HashSet};

use serde::{Deserialize, Serialize};
use serde_json::Value;
use thiserror::Error;
use uuid::Uuid;

pub const MAX_FRAME_BYTES: usize = 64 * 1024;
pub const MAX_PENDING_REQUESTS: usize = 16;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum Operation {
    #[serde(rename = "profile.inspect")]
    ProfileInspect,
    #[serde(rename = "profile.adopt")]
    ProfileAdopt,
    #[serde(rename = "capture.start")]
    CaptureStart,
    #[serde(rename = "capture.stop")]
    CaptureStop,
    #[serde(rename = "capture.inspect")]
    CaptureInspect,
    #[serde(rename = "transcript.create")]
    TranscriptCreate,
    #[serde(rename = "note.create")]
    NoteCreate,
    #[serde(rename = "note.inspect")]
    NoteInspect,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct WorkerReady {
    pub schema: WorkerEventSchema,
    pub event: ReadyEvent,
    pub protocol: u16,
    pub build: String,
    pub runtime: RuntimeStatus,
    pub tap: TapStatus,
    pub models: Vec<ResourceStatus>,
    pub operations: HashSet<Operation>,
}

#[derive(Debug, Deserialize, PartialEq, Eq)]
pub enum WorkerEventSchema {
    #[serde(rename = "worker-event/1")]
    V1,
}

#[derive(Debug, Deserialize, PartialEq, Eq)]
pub enum ReadyEvent {
    #[serde(rename = "worker.ready")]
    WorkerReady,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RuntimeStatus {
    pub kind: RuntimeKind,
    pub digest: String,
}

#[derive(Debug, Deserialize)]
pub enum RuntimeKind {
    #[serde(rename = "bundled")]
    Bundled,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct TapStatus {
    pub build: String,
    pub available: bool,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ResourceStatus {
    pub id: String,
    pub digest: String,
    pub available: bool,
}

#[derive(Debug, Serialize)]
pub struct WorkerCommand {
    pub schema: &'static str,
    pub request_id: Uuid,
    pub operation: Operation,
    pub arguments: Value,
}

impl WorkerCommand {
    pub fn new(operation: Operation, arguments: Value) -> Self {
        Self {
            schema: "worker-command/1",
            request_id: Uuid::new_v4(),
            operation,
            arguments,
        }
    }
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct WorkerResult {
    pub schema: ResultSchema,
    pub request_id: Uuid,
    pub ok: bool,
    pub code: Option<ResultCode>,
    pub recoverable: Option<bool>,
    #[serde(default)]
    pub artifact_digests: HashMap<String, String>,
}

#[derive(Debug, Deserialize, PartialEq, Eq)]
pub enum ResultSchema {
    #[serde(rename = "worker-result/1")]
    V1,
}

#[derive(Debug, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ResultCode {
    TapReadyTimeout,
    RuntimeMissing,
    InvalidProfile,
    InvalidCapture,
    TranscriptionFailed,
    NoteRejected,
    ProtocolFailure,
}

#[derive(Debug, Error, PartialEq, Eq)]
pub enum ProtocolError {
    #[error("protocol frame exceeds its byte limit")]
    FrameTooLarge,
    #[error("protocol frame is malformed or outside the closed schema")]
    Malformed,
    #[error("worker protocol version is unsupported")]
    UnsupportedProtocol,
    #[error("worker operation set differs from the application registry")]
    OperationMismatch,
    #[error("request limit reached")]
    RequestLimit,
    #[error("result refers to an unknown request")]
    UnknownRequest,
    #[error("request already produced a terminal result")]
    DuplicateTerminal,
}

pub fn parse_ready(
    frame: &[u8],
    expected: &HashSet<Operation>,
) -> Result<WorkerReady, ProtocolError> {
    if frame.len() > MAX_FRAME_BYTES {
        return Err(ProtocolError::FrameTooLarge);
    }
    let ready: WorkerReady = serde_json::from_slice(frame).map_err(|_| ProtocolError::Malformed)?;
    if ready.protocol != 1 {
        return Err(ProtocolError::UnsupportedProtocol);
    }
    if &ready.operations != expected {
        return Err(ProtocolError::OperationMismatch);
    }
    Ok(ready)
}

pub fn parse_result(frame: &[u8]) -> Result<WorkerResult, ProtocolError> {
    if frame.len() > MAX_FRAME_BYTES {
        return Err(ProtocolError::FrameTooLarge);
    }
    serde_json::from_slice(frame).map_err(|_| ProtocolError::Malformed)
}

#[derive(Default)]
pub struct RequestTracker {
    pending: HashSet<Uuid>,
    terminal: HashSet<Uuid>,
}

impl RequestTracker {
    pub fn register(&mut self, request_id: Uuid) -> Result<(), ProtocolError> {
        if self.pending.len() >= MAX_PENDING_REQUESTS {
            return Err(ProtocolError::RequestLimit);
        }
        if self.pending.contains(&request_id) || self.terminal.contains(&request_id) {
            return Err(ProtocolError::DuplicateTerminal);
        }
        self.pending.insert(request_id);
        Ok(())
    }

    pub fn terminal(&mut self, result: &WorkerResult) -> Result<(), ProtocolError> {
        if self.terminal.contains(&result.request_id) {
            return Err(ProtocolError::DuplicateTerminal);
        }
        if !self.pending.remove(&result.request_id) {
            return Err(ProtocolError::UnknownRequest);
        }
        self.terminal.insert(result.request_id);
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn unknown_ready_field_fails_closed() {
        let frame = br#"{"schema":"worker-event/1","event":"worker.ready","protocol":1,"build":"x","runtime":{"kind":"bundled","digest":"x"},"tap":{"build":"x","available":true},"models":[],"operations":[],"surprise":true}"#;
        assert_eq!(
            parse_ready(frame, &HashSet::new()).unwrap_err(),
            ProtocolError::Malformed
        );
    }

    #[test]
    fn duplicate_terminal_result_is_refused() {
        let request_id = Uuid::new_v4();
        let result = WorkerResult {
            schema: ResultSchema::V1,
            request_id,
            ok: true,
            code: None,
            recoverable: None,
            artifact_digests: HashMap::new(),
        };
        let mut tracker = RequestTracker::default();
        tracker.register(request_id).unwrap();
        tracker.terminal(&result).unwrap();
        assert_eq!(
            tracker.terminal(&result),
            Err(ProtocolError::DuplicateTerminal)
        );
    }

    #[test]
    fn result_with_unknown_field_fails_closed() {
        let request_id = Uuid::new_v4();
        let frame = format!(
            "{{\"schema\":\"worker-result/1\",\"request_id\":\"{request_id}\",\"ok\":true,\"code\":null,\"recoverable\":null,\"artifact_digests\":{{}},\"extra\":true}}"
        );
        assert_eq!(
            parse_result(frame.as_bytes()).unwrap_err(),
            ProtocolError::Malformed
        );
    }
}

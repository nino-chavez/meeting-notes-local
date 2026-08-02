//! Closed, read-only parsing for the worker-owned `note.project` projection.
//!
//! This module deliberately does not read a `note/2` artifact.  The worker is
//! the semantic authority; Rust only accepts a fully resolved, digest-bound
//! projection and keeps it inside an in-memory library snapshot.

use serde::de::{self, Deserialize, Deserializer, MapAccess, SeqAccess, Visitor};
use sha2::{Digest, Sha256};
use std::fmt;
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};
use uuid::Uuid;

#[cfg(test)]
use crate::meeting::valid_opaque_id;

pub const MAX_PROJECTION_FRAME_BYTES: usize = 64 * 1024;

/// The only process boundary required by the reader.  A production sidecar can
/// implement this without changing parsing or library authority.
pub trait NoteProjector: Send + Sync {
    fn project(&self, request: &ProjectRequest) -> Result<Vec<u8>, ProjectTransportError>;

    fn project_with_cancellation(
        &self,
        request: &ProjectRequest,
        cancellation: &ProjectionCancellation,
    ) -> Result<Vec<u8>, ProjectTransportError> {
        if cancellation.is_cancelled() {
            return Err(ProjectTransportError::Cancelled);
        }
        self.project(request)
    }
}

/// Cloneable, process-local cancellation authority for one read-only
/// projection. Cancellation never carries artifact or meeting content.
#[derive(Clone, Default)]
pub struct ProjectionCancellation(Arc<AtomicBool>);

impl ProjectionCancellation {
    pub fn cancel(&self) {
        self.0.store(true, Ordering::SeqCst);
    }

    pub fn is_cancelled(&self) -> bool {
        self.0.load(Ordering::SeqCst)
    }
}

/// Content-free transport failure.  Raw child stderr and protocol bytes never
/// cross into library diagnostics.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ProjectTransportError {
    Unavailable,
    Cancelled,
}

/// Default until a verifier-owned child transport is wired by a later slice.
pub struct UnavailableProjector;

impl NoteProjector for UnavailableProjector {
    fn project(&self, _: &ProjectRequest) -> Result<Vec<u8>, ProjectTransportError> {
        Err(ProjectTransportError::Unavailable)
    }
}

pub struct ProjectRequest {
    pub request_id: Uuid,
    pub meeting_id: String,
    pub note_json_sha256: String,
    pub note_markdown_sha256: String,
    pub transcript_sha256: String,
}

#[derive(Clone, PartialEq, Eq)]
pub(crate) struct ProjectedClaim {
    pub(crate) ordinal: u64,
    pub(crate) sha256: String,
    pub(crate) claim_type: ClaimType,
    pub(crate) text: String,
    pub(crate) locators: Vec<Locator>,
}

#[derive(Clone, Copy, PartialEq, Eq)]
pub enum ClaimType {
    Decision,
    Action,
    Proposal,
    Question,
}

#[derive(Clone, PartialEq, Eq)]
pub(crate) struct Locator {
    pub(crate) turn: u64,
    pub(crate) start: u64,
    pub(crate) end: u64,
    pub(crate) text_sha256: String,
}

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub(crate) enum ProjectionError {
    ArtifactMissing,
    ArtifactInvalid,
    ArtifactChanged,
    CapacityExceeded,
    Unavailable,
}

pub(crate) fn project_claims(
    projector: &dyn NoteProjector,
    request: &ProjectRequest,
    transcript_turns: &[String],
) -> Result<Vec<ProjectedClaim>, ProjectionError> {
    let frame = projector
        .project(request)
        .map_err(|_| ProjectionError::Unavailable)?;
    parse_result(&frame, request, transcript_turns)
}

fn parse_result(
    frame: &[u8],
    request: &ProjectRequest,
    transcript_turns: &[String],
) -> Result<Vec<ProjectedClaim>, ProjectionError> {
    if frame.len() > MAX_PROJECTION_FRAME_BYTES
        || !frame.ends_with(b"\n")
        || frame[..frame.len() - 1]
            .iter()
            .any(|byte| matches!(byte, b'\n' | b'\r'))
    {
        return Err(ProjectionError::Unavailable);
    }
    let root = strict_json(&frame[..frame.len() - 1])?;
    let values = exact_object(
        &root,
        [
            "schema",
            "request_id",
            "operation",
            "outcome",
            "projection",
            "failure",
        ],
    )?;
    if string(values[0])? != "note-projection-result/1"
        || canonical_uuid(string(values[1])?)? != request.request_id
        || string(values[2])? != "note.project"
    {
        return Err(ProjectionError::Unavailable);
    }
    match string(values[3])? {
        "succeeded" => {
            if !matches!(values[5], StrictJson::Null) {
                return Err(ProjectionError::Unavailable);
            }
            let projection = parse_projection(values[4], request, transcript_turns)?;
            Ok(projection)
        }
        "refused" => {
            if !matches!(values[4], StrictJson::Null) {
                return Err(ProjectionError::Unavailable);
            }
            parse_failure(values[5])
        }
        _ => Err(ProjectionError::Unavailable),
    }
}

fn parse_projection(
    value: &StrictJson,
    request: &ProjectRequest,
    transcript_turns: &[String],
) -> Result<Vec<ProjectedClaim>, ProjectionError> {
    let values = exact_object(
        value,
        [
            "schema",
            "note_json_sha256",
            "note_markdown_sha256",
            "transcript_sha256",
            "claims",
        ],
    )?;
    if string(values[0])? != "note-claim-projection/1"
        || digest(string(values[1])?)? != request.note_json_sha256
        || digest(string(values[2])?)? != request.note_markdown_sha256
        || digest(string(values[3])?)? != request.transcript_sha256
    {
        return Err(ProjectionError::Unavailable);
    }
    let claims = array(values[4])?;
    claims
        .iter()
        .enumerate()
        .map(|(ordinal, claim)| parse_claim(claim, ordinal as u64, transcript_turns))
        .collect()
}

fn parse_claim(
    value: &StrictJson,
    expected_ordinal: u64,
    transcript_turns: &[String],
) -> Result<ProjectedClaim, ProjectionError> {
    let values = exact_object(
        value,
        [
            "claim_ordinal",
            "claim_sha256",
            "claim_type",
            "evidence_state",
            "claim",
            "locators",
        ],
    )?;
    if u64_value(values[0])? != expected_ordinal || string(values[3])? != "located" {
        return Err(ProjectionError::Unavailable);
    }
    let text = string(values[4])?.to_owned();
    if text.is_empty() || text.chars().count() > 160 || text.chars().any(forbidden) {
        return Err(ProjectionError::Unavailable);
    }
    let sha256 = digest(string(values[1])?)?.to_owned();
    if sha256 != format!("{:x}", Sha256::digest(text.as_bytes())) {
        return Err(ProjectionError::Unavailable);
    }
    let claim_type = match string(values[2])? {
        "decision" => ClaimType::Decision,
        "action" => ClaimType::Action,
        "proposal" => ClaimType::Proposal,
        "question" => ClaimType::Question,
        _ => return Err(ProjectionError::Unavailable),
    };
    let locators: Vec<_> = array(values[5])?
        .iter()
        .map(|locator| parse_locator(locator, transcript_turns))
        .collect::<Result<_, _>>()?;
    if !(1..=3).contains(&locators.len()) || !strictly_sorted(&locators) {
        return Err(ProjectionError::Unavailable);
    }
    Ok(ProjectedClaim {
        ordinal: expected_ordinal,
        sha256,
        claim_type,
        text,
        locators,
    })
}

fn parse_locator(value: &StrictJson, turns: &[String]) -> Result<Locator, ProjectionError> {
    let values = exact_object(value, ["turn", "start", "end", "text_sha256"])?;
    let turn = u64_value(values[0])?;
    let start = u64_value(values[1])?;
    let end = u64_value(values[2])?;
    let text_sha256 = digest(string(values[3])?)?.to_owned();
    let text = turns
        .get(usize::try_from(turn).map_err(|_| ProjectionError::Unavailable)?)
        .ok_or(ProjectionError::Unavailable)?;
    let slice = scalar_slice(text, start, end).ok_or(ProjectionError::Unavailable)?;
    if text_sha256 != format!("{:x}", Sha256::digest(slice.as_bytes())) {
        return Err(ProjectionError::Unavailable);
    }
    Ok(Locator {
        turn,
        start,
        end,
        text_sha256,
    })
}

fn strictly_sorted(locators: &[Locator]) -> bool {
    locators.windows(2).all(|pair| {
        let left = &pair[0];
        let right = &pair[1];
        (left.turn, left.start, left.end, &left.text_sha256)
            < (right.turn, right.start, right.end, &right.text_sha256)
    })
}

fn parse_failure(value: &StrictJson) -> Result<Vec<ProjectedClaim>, ProjectionError> {
    let values = exact_object(value, ["code", "recoverable"])?;
    let recoverable = bool_value(values[1])?;
    match (string(values[0])?, recoverable) {
        ("artifact-missing", true) => Err(ProjectionError::ArtifactMissing),
        ("artifact-invalid", false) => Err(ProjectionError::ArtifactInvalid),
        ("artifact-changed", false) => Err(ProjectionError::ArtifactChanged),
        ("projection-capacity-exceeded", false) => Err(ProjectionError::CapacityExceeded),
        _ => Err(ProjectionError::Unavailable),
    }
}

fn canonical_uuid(value: &str) -> Result<Uuid, ProjectionError> {
    let parsed = Uuid::parse_str(value).map_err(|_| ProjectionError::Unavailable)?;
    (parsed.to_string() == value)
        .then_some(parsed)
        .ok_or(ProjectionError::Unavailable)
}

fn digest(value: &str) -> Result<&str, ProjectionError> {
    (value.len() == 64
        && value
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)))
    .then_some(value)
    .ok_or(ProjectionError::Unavailable)
}

fn scalar_slice(text: &str, start: u64, end: u64) -> Option<String> {
    if start >= end || end > text.chars().count() as u64 {
        return None;
    }
    Some(
        text.chars()
            .skip(usize::try_from(start).ok()?)
            .take(usize::try_from(end - start).ok()?)
            .collect(),
    )
}

fn forbidden(character: char) -> bool {
    character.is_control() || matches!(character, '\u{2028}' | '\u{2029}')
}

pub(crate) fn exact_object<'a, const N: usize>(
    value: &'a StrictJson,
    keys: [&str; N],
) -> Result<[&'a StrictJson; N], ProjectionError> {
    let StrictJson::Object(entries) = value else {
        return Err(ProjectionError::Unavailable);
    };
    if entries.len() != N
        || entries
            .iter()
            .zip(keys)
            .any(|((key, _), expected)| key != expected)
    {
        return Err(ProjectionError::Unavailable);
    }
    Ok(std::array::from_fn(|index| &entries[index].1))
}

pub(crate) fn string(value: &StrictJson) -> Result<&str, ProjectionError> {
    match value {
        StrictJson::String(value) => Ok(value),
        _ => Err(ProjectionError::Unavailable),
    }
}
pub(crate) fn bool_value(value: &StrictJson) -> Result<bool, ProjectionError> {
    match value {
        StrictJson::Bool(value) => Ok(*value),
        _ => Err(ProjectionError::Unavailable),
    }
}
pub(crate) fn u64_value(value: &StrictJson) -> Result<u64, ProjectionError> {
    match value {
        StrictJson::Number(value) => value.as_u64().ok_or(ProjectionError::Unavailable),
        _ => Err(ProjectionError::Unavailable),
    }
}
pub(crate) fn array(value: &StrictJson) -> Result<&[StrictJson], ProjectionError> {
    match value {
        StrictJson::Array(value) => Ok(value),
        _ => Err(ProjectionError::Unavailable),
    }
}

pub(crate) enum StrictJson {
    Null,
    Bool(bool),
    Number(serde_json::Number),
    String(String),
    Array(Vec<StrictJson>),
    Object(Vec<(String, StrictJson)>),
}

impl<'de> Deserialize<'de> for StrictJson {
    fn deserialize<D: Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        struct StrictVisitor;
        impl<'de> Visitor<'de> for StrictVisitor {
            type Value = StrictJson;
            fn expecting(&self, formatter: &mut fmt::Formatter) -> fmt::Result {
                formatter.write_str("JSON value")
            }
            fn visit_unit<E: de::Error>(self) -> Result<Self::Value, E> {
                Ok(StrictJson::Null)
            }
            fn visit_bool<E: de::Error>(self, value: bool) -> Result<Self::Value, E> {
                Ok(StrictJson::Bool(value))
            }
            fn visit_i64<E: de::Error>(self, value: i64) -> Result<Self::Value, E> {
                Ok(StrictJson::Number(value.into()))
            }
            fn visit_u64<E: de::Error>(self, value: u64) -> Result<Self::Value, E> {
                Ok(StrictJson::Number(value.into()))
            }
            fn visit_f64<E: de::Error>(self, value: f64) -> Result<Self::Value, E> {
                serde_json::Number::from_f64(value)
                    .map(StrictJson::Number)
                    .ok_or_else(|| E::custom("non-finite JSON number"))
            }
            fn visit_str<E: de::Error>(self, value: &str) -> Result<Self::Value, E> {
                Ok(StrictJson::String(value.to_owned()))
            }
            fn visit_string<E: de::Error>(self, value: String) -> Result<Self::Value, E> {
                Ok(StrictJson::String(value))
            }
            fn visit_seq<A: SeqAccess<'de>>(self, mut access: A) -> Result<Self::Value, A::Error> {
                let mut values = Vec::new();
                while let Some(value) = access.next_element()? {
                    values.push(value);
                }
                Ok(StrictJson::Array(values))
            }
            fn visit_map<A: MapAccess<'de>>(self, mut access: A) -> Result<Self::Value, A::Error> {
                let mut entries = Vec::new();
                while let Some((key, value)) = access.next_entry()? {
                    entries.push((key, value));
                }
                Ok(StrictJson::Object(entries))
            }
        }
        deserializer.deserialize_any(StrictVisitor)
    }
}

pub(crate) fn strict_json(bytes: &[u8]) -> Result<StrictJson, ProjectionError> {
    let mut deserializer = serde_json::Deserializer::from_slice(bytes);
    let value =
        StrictJson::deserialize(&mut deserializer).map_err(|_| ProjectionError::Unavailable)?;
    deserializer
        .end()
        .map_err(|_| ProjectionError::Unavailable)?;
    Ok(value)
}

/// Validates the closed project command at the process boundary.  It is kept
/// separate from result parsing so a future child transport can use it without
/// giving the reader a second note validator.
#[cfg(test)]
pub(crate) fn validate_project_command(frame: &[u8]) -> Result<(), ProjectionError> {
    if frame.len() > MAX_PROJECTION_FRAME_BYTES || !frame.ends_with(b"\n") {
        return Err(ProjectionError::Unavailable);
    }
    let root = strict_json(&frame[..frame.len() - 1])?;
    let values = exact_object(&root, ["schema", "request_id", "operation", "arguments"])?;
    if string(values[0])? != "note-bridge-command/1"
        || canonical_uuid(string(values[1])?).is_err()
        || string(values[2])? != "note.project"
    {
        return Err(ProjectionError::Unavailable);
    }
    let arguments = exact_object(values[3], ["meeting_id", "note_id", "transcript_id"])?;
    if !valid_opaque_id(string(arguments[0])?)
        || digest(string(arguments[1])?).is_err()
        || digest(string(arguments[2])?).is_err()
    {
        return Err(ProjectionError::Unavailable);
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use serde_json::Value;

    use super::*;

    fn fixture() -> Value {
        serde_json::from_str(include_str!(
            "../../../tests/fixtures/note-projection-v1.fixture"
        ))
        .unwrap()
    }
    fn request() -> ProjectRequest {
        ProjectRequest {
            request_id: Uuid::parse_str("11111111-1111-4111-8111-111111111111").unwrap(),
            meeting_id: "meeting-a".into(),
            note_json_sha256: "a".repeat(64),
            note_markdown_sha256: "b".repeat(64),
            transcript_sha256: "c".repeat(64),
        }
    }
    fn turns() -> Vec<String> {
        fixture()["transcript_turns"]
            .as_array()
            .unwrap()
            .iter()
            .map(|value| value.as_str().unwrap().to_owned())
            .collect()
    }
    fn frame(value: &Value) -> Vec<u8> {
        let mut bytes = ordered_json(value).into_bytes();
        bytes.push(b'\n');
        bytes
    }

    fn ordered_json(value: &Value) -> String {
        match value {
            Value::Null | Value::Bool(_) | Value::Number(_) | Value::String(_) => {
                serde_json::to_string(value).unwrap()
            }
            Value::Array(values) => format!(
                "[{}]",
                values
                    .iter()
                    .map(ordered_json)
                    .collect::<Vec<_>>()
                    .join(",")
            ),
            Value::Object(values) => {
                let keys: &[&str] = if values.contains_key("outcome") {
                    &[
                        "schema",
                        "request_id",
                        "operation",
                        "outcome",
                        "projection",
                        "failure",
                    ]
                } else if values.contains_key("note_json_sha256") {
                    &[
                        "schema",
                        "note_json_sha256",
                        "note_markdown_sha256",
                        "transcript_sha256",
                        "claims",
                    ]
                } else if values.contains_key("claim_ordinal") {
                    &[
                        "claim_ordinal",
                        "claim_sha256",
                        "claim_type",
                        "evidence_state",
                        "claim",
                        "locators",
                    ]
                } else if values.contains_key("text_sha256") {
                    &["turn", "start", "end", "text_sha256"]
                } else if values.contains_key("recoverable") {
                    &["code", "recoverable"]
                } else {
                    unreachable!("fixture has only closed projection objects")
                };
                format!(
                    "{{{}}}",
                    keys.iter()
                        .map(|key| format!(
                            "{}:{}",
                            serde_json::to_string(key).unwrap(),
                            ordered_json(&values[*key])
                        ))
                        .collect::<Vec<_>>()
                        .join(",")
                )
            }
        }
    }

    #[test]
    fn shared_fixture_accepts_valid_rows_and_preserves_duplicate_ordinals() {
        let fixture = fixture();
        for command in fixture["valid_commands"].as_array().unwrap() {
            assert!(
                validate_project_command(command["raw_frame"].as_str().unwrap().as_bytes()).is_ok()
            );
        }
        let results = fixture["valid_results"].as_array().unwrap();
        let empty = match parse_result(&frame(&results[0]["result"]), &request(), &turns()) {
            Ok(value) => value,
            Err(error) => panic!("fixture empty projection must parse: {error:?}"),
        };
        assert!(empty.is_empty());
        let claims = match parse_result(&frame(&results[1]["result"]), &request(), &turns()) {
            Ok(value) => value,
            Err(_) => panic!("fixture projection must parse"),
        };
        assert_eq!(claims.len(), 5);
        assert_eq!(claims[0].text, claims[1].text);
        assert_eq!((claims[0].ordinal, claims[1].ordinal), (0, 1));
    }

    #[test]
    fn shared_fixture_refuses_recursive_order_duplicates_unknowns_and_unicode_byte_offsets() {
        let fixture = fixture();
        for case in fixture["invalid_command_frames"].as_array().unwrap() {
            assert!(
                validate_project_command(case["raw_frame"].as_str().unwrap().as_bytes()).is_err()
            );
        }
        for case in fixture["invalid_result_frames"].as_array().unwrap() {
            assert!(
                parse_result(
                    case["raw_frame"].as_str().unwrap().as_bytes(),
                    &request(),
                    &turns()
                )
                .is_err()
            );
        }
        for case in fixture["invalid_nested_objects"].as_array().unwrap() {
            let object = match strict_json(case["raw_object"].as_str().unwrap().as_bytes()) {
                Ok(value) => value,
                Err(_) => panic!("fixture nested object must be JSON"),
            };
            let result = match case["boundary"].as_str().unwrap() {
                "projection" => parse_projection(&object, &request(), &turns()).map(|_| ()),
                "claim" => parse_claim(&object, 0, &turns()).map(|_| ()),
                "locator" => parse_locator(&object, &turns()).map(|_| ()),
                "failure" => parse_failure(&object).map(|_| ()),
                _ => unreachable!(),
            };
            assert!(result.is_err(), "{}", case["name"]);
        }
        let mut byte_offset = fixture["valid_results"][1]["result"].clone();
        byte_offset["projection"]["claims"][4]["locators"][1]["end"] = Value::from(7_u64);
        assert!(parse_result(&frame(&byte_offset), &request(), &turns()).is_err());
    }

    #[test]
    fn shared_fixture_maps_only_closed_refusals() {
        let fixture = fixture();
        let expected = [
            ProjectionError::Unavailable,
            ProjectionError::ArtifactMissing,
            ProjectionError::ArtifactInvalid,
            ProjectionError::ArtifactChanged,
            ProjectionError::CapacityExceeded,
        ];
        for (case, error) in fixture["refusal_results"]
            .as_array()
            .unwrap()
            .iter()
            .zip(expected)
        {
            assert!(
                matches!(parse_result(&frame(&case["result"]), &request(), &turns()), Err(actual) if actual == error)
            );
        }
    }

    #[test]
    fn result_requires_exactly_one_terminal_newline_and_no_second_frame_bytes() {
        let fixture = fixture();
        let valid = frame(&fixture["valid_results"][0]["result"]);
        for suffix in [b"\n".as_slice(), b" \n", b"{}\n", b"x"] {
            let mut invalid = valid.clone();
            invalid.extend_from_slice(suffix);
            assert!(parse_result(&invalid, &request(), &turns()).is_err());
        }
    }
}

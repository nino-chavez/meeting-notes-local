//! The shell boundary for folders and operator titles.
//!
//! Five named commands, not one `organize` command taking an operation name.
//! `vertical-slice.md` fixes that shape and the reason is legible from the
//! capability list a window is granted: a surface allowed to rename a meeting
//! is not thereby allowed to delete a folder.
//!
//! **Every mutation carries `expected_revision` and refuses on mismatch rather
//! than merging.** Two windows editing the same record silently is how one of
//! them loses a rename without being told, and there is no merge that could be
//! right — a title is not a value that can be averaged.
//!
//! Nothing here is destructive to meeting evidence. The record holds folder
//! names and the titles the operator typed; the transcript, note and audio are
//! untouched by every path in this file.

use local_meeting_notes_session_core::library_metadata::{OrganizationError, OrganizationOutcome};
use serde::Serialize;

/// The exact four fields the runtime contract names, plus the closed error
/// enum. `changed: false` is a success: a semantic no-op wrote nothing and the
/// revision did not move.
#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct OrganizationResponse {
    pub(crate) state: &'static str,
    pub(crate) revision: Option<u64>,
    pub(crate) changed: bool,
    pub(crate) folder_id: Option<String>,
    /// Present only on a revision conflict, which is the one refusal a surface
    /// can act on without asking the operator anything: refresh and retry.
    pub(crate) current_revision: Option<u64>,
    pub(crate) message: String,
}

impl OrganizationResponse {
    pub(crate) fn unavailable(message: &str) -> Self {
        Self {
            state: "unavailable",
            revision: None,
            changed: false,
            folder_id: None,
            current_revision: None,
            message: message.into(),
        }
    }
}

impl From<OrganizationOutcome> for OrganizationResponse {
    fn from(outcome: OrganizationOutcome) -> Self {
        Self {
            state: "ok",
            revision: Some(outcome.revision),
            changed: outcome.changed,
            folder_id: outcome.folder_id,
            current_revision: None,
            message: if outcome.changed {
                String::new()
            } else {
                // Said plainly rather than silently: a person who typed the
                // name that was already there should not be left wondering
                // whether the app took it.
                "That was already the name.".into()
            },
        }
    }
}

impl From<OrganizationError> for OrganizationResponse {
    fn from(error: OrganizationError) -> Self {
        match error {
            OrganizationError::InvalidRequest => Self {
                state: "invalid-request",
                revision: None,
                changed: false,
                folder_id: None,
                current_revision: None,
                message: "That name cannot be used. Names are up to 120 characters and cannot \
                          contain slashes or line breaks."
                    .into(),
            },
            OrganizationError::RevisionConflict { current_revision } => Self {
                state: "revision-conflict",
                revision: None,
                changed: false,
                folder_id: None,
                current_revision: Some(current_revision),
                message: "Your folders changed somewhere else. Reload Meetings and try again."
                    .into(),
            },
            OrganizationError::MetadataUnavailable => Self {
                state: "metadata-unavailable",
                revision: None,
                changed: false,
                folder_id: None,
                current_revision: None,
                message: "Your folders and titles could not be read, so nothing was changed. \
                          Your recordings and transcripts are not affected."
                    .into(),
            },
            OrganizationError::Internal => {
                Self::unavailable("That change could not be saved. Nothing was written.")
            }
        }
    }
}

pub(crate) fn from_result(
    result: Result<OrganizationOutcome, OrganizationError>,
) -> OrganizationResponse {
    match result {
        Ok(outcome) => outcome.into(),
        Err(error) => error.into(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_no_op_is_a_success_that_says_so_rather_than_a_silent_one() {
        let response = from_result(Ok(OrganizationOutcome {
            revision: 4,
            changed: false,
            folder_id: None,
        }));
        assert_eq!(response.state, "ok");
        assert!(!response.changed);
        assert_eq!(response.revision, Some(4));
        assert!(!response.message.is_empty());
    }

    #[test]
    fn only_a_revision_conflict_carries_the_current_revision() {
        let conflict = from_result(Err(OrganizationError::RevisionConflict {
            current_revision: 9,
        }));
        assert_eq!(conflict.state, "revision-conflict");
        assert_eq!(conflict.current_revision, Some(9));

        for error in [
            OrganizationError::InvalidRequest,
            OrganizationError::MetadataUnavailable,
            OrganizationError::Internal,
        ] {
            assert_eq!(from_result(Err(error)).current_revision, None);
        }
    }

    #[test]
    fn refusal_messages_carry_no_private_text_and_say_what_survived() {
        let unavailable = from_result(Err(OrganizationError::MetadataUnavailable));
        assert!(
            unavailable.message.contains("not affected"),
            "a person reading this must learn their recordings are safe"
        );
        for error in [
            OrganizationError::InvalidRequest,
            OrganizationError::MetadataUnavailable,
            OrganizationError::Internal,
        ] {
            let message = from_result(Err(error)).message;
            assert!(!message.is_empty());
            assert!(message.is_ascii(), "{message}");
        }
    }
}

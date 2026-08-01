pub mod diagnostic;
pub(crate) mod library_metadata;
pub mod library_read;
pub mod meeting;
pub mod meeting_coordination;
pub mod note_generation;
pub mod note_projection;
#[cfg(target_os = "macos")]
mod note_projector_process;
pub mod operation_store;
pub mod operations;
// This is deliberately private to session-core.  Desktop commands and guided
// enrolment are not admitted until they can hold the lifetime writer lock.
#[allow(dead_code)]
pub(crate) mod profile_lifecycle;
pub mod protocol;
pub mod recovery;
pub mod reducer;
pub mod retention;
pub mod runtime;
pub mod storage;
pub mod supervision;
pub mod transcript_restoration;

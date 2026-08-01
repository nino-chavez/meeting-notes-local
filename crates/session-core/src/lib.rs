pub mod diagnostic;
pub mod meeting;
pub mod meeting_coordination;
pub mod note_generation;
pub mod operation_store;
pub mod operations;
// This destructive authority remains unwired until a facade can prove it holds
// the process-lifetime writer lock. Its self-contained tests exercise it now.
#[allow(dead_code)]
pub(crate) mod profile_reset;
pub mod protocol;
pub mod recovery;
pub mod reducer;
pub mod retention;
pub mod runtime;
pub mod storage;
pub mod supervision;
pub mod transcript_restoration;

use std::collections::HashSet;
use std::sync::{Mutex, MutexGuard};

use thiserror::Error;

#[derive(Debug, Error, Clone, Copy, PartialEq, Eq)]
pub enum MeetingCoordinationError {
    #[error("meeting storage coordination is unavailable")]
    Unavailable,
    #[error("meeting is already active")]
    AlreadyActive,
}

/// One process-local authority for meeting mutation and retention scans.
///
/// Registering an active meeting and taking a storage sequence both acquire the
/// same sequence mutex first. A retention scan can therefore hold a sequence,
/// snapshot active IDs, and finish without racing a newly registered writer.
#[derive(Debug, Default)]
pub struct MeetingStorageCoordination {
    sequence: Mutex<()>,
    active_meetings: Mutex<HashSet<String>>,
}

#[derive(Debug)]
pub struct ActiveMeetingLease<'a> {
    coordination: &'a MeetingStorageCoordination,
    meeting_id: String,
}

pub struct MeetingStorageSequence<'a> {
    coordination: &'a MeetingStorageCoordination,
    _sequence: MutexGuard<'a, ()>,
}

impl MeetingStorageCoordination {
    pub fn acquire(
        &self,
        meeting_id: &str,
    ) -> Result<ActiveMeetingLease<'_>, MeetingCoordinationError> {
        let _sequence = self
            .sequence
            .lock()
            .map_err(|_| MeetingCoordinationError::Unavailable)?;
        let mut active = self
            .active_meetings
            .lock()
            .map_err(|_| MeetingCoordinationError::Unavailable)?;
        if !active.insert(meeting_id.to_owned()) {
            return Err(MeetingCoordinationError::AlreadyActive);
        }
        Ok(ActiveMeetingLease {
            coordination: self,
            meeting_id: meeting_id.to_owned(),
        })
    }

    pub fn lock_sequence(&self) -> Result<MeetingStorageSequence<'_>, MeetingCoordinationError> {
        let sequence = self
            .sequence
            .lock()
            .map_err(|_| MeetingCoordinationError::Unavailable)?;
        Ok(MeetingStorageSequence {
            coordination: self,
            _sequence: sequence,
        })
    }
}

impl MeetingStorageSequence<'_> {
    pub fn active_meeting_ids(&self) -> Result<HashSet<String>, MeetingCoordinationError> {
        self.coordination
            .active_meetings
            .lock()
            .map_err(|_| MeetingCoordinationError::Unavailable)
            .map(|active| active.clone())
    }
}

impl Drop for ActiveMeetingLease<'_> {
    fn drop(&mut self) {
        let Ok(_sequence) = self.coordination.sequence.lock() else {
            return;
        };
        if let Ok(mut active) = self.coordination.active_meetings.lock() {
            active.remove(&self.meeting_id);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn lease_is_exclusive_and_released_on_drop() {
        let coordination = MeetingStorageCoordination::default();
        let lease = coordination.acquire("meeting-a").unwrap();
        assert_eq!(
            coordination.acquire("meeting-a").unwrap_err(),
            MeetingCoordinationError::AlreadyActive
        );
        assert_eq!(
            coordination
                .lock_sequence()
                .unwrap()
                .active_meeting_ids()
                .unwrap(),
            HashSet::from(["meeting-a".to_owned()])
        );

        drop(lease);

        assert!(
            coordination
                .lock_sequence()
                .unwrap()
                .active_meeting_ids()
                .unwrap()
                .is_empty()
        );
        assert!(coordination.acquire("meeting-a").is_ok());
    }
}

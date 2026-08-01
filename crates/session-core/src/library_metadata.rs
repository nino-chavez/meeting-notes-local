//! Descriptor-bound, optional organization metadata for the private library.
//!
//! This module deliberately has no writer.  A bad record is not repaired or
//! interpreted: callers receive an unavailable state and retain no label
//! authority.  Its identity is private and content-free, but changes whenever
//! absence, safety, bytes, or validity change.

use std::fs::{self, File, OpenOptions};
use std::io::{self, Read};
use std::os::fd::{AsRawFd, FromRawFd};
use std::os::unix::fs::{MetadataExt, OpenOptionsExt};
use std::path::Path;

use serde::de::{self, MapAccess, Visitor};
use serde::{Deserialize, Deserializer};
use sha2::{Digest, Sha256};
use uuid::Uuid;

use crate::storage::StorageRoot;

const MAX_METADATA_BYTES: u64 = 1024 * 1024;
const METADATA_NAME: &[u8] = b"metadata.json\0";
/// Darwin's `<sys/fcntl.h>` O_UNIQUE. libc 0.2.189 does not expose it.
#[cfg(target_os = "macos")]
const O_UNIQUE: libc::c_int = 0x2000;

#[derive(Clone, PartialEq, Eq)]
pub(crate) enum MetadataState {
    Missing { identity: MetadataIdentity },
    Valid(MetadataDocument),
    Unavailable { identity: MetadataIdentity },
}

impl MetadataState {
    pub(crate) fn identity(&self) -> MetadataIdentity {
        match self {
            Self::Missing { identity } | Self::Unavailable { identity } => identity.clone(),
            Self::Valid(document) => document.identity.clone(),
        }
    }
    pub(crate) fn document(&self) -> Option<&MetadataDocument> {
        match self {
            Self::Valid(document) => Some(document),
            _ => None,
        }
    }
    pub(crate) fn unavailable_after_relative_validation(&self) -> Self {
        let mut bytes = b"library-metadata/1:relative-validation-failed:".to_vec();
        bytes.extend_from_slice(&self.identity().0);
        Self::Unavailable {
            identity: identity(&bytes),
        }
    }
}

/// Never exposed through a library result.  It includes a digest so equal
/// revisions with different canonical bytes still invalidate old handles.
#[derive(Clone, PartialEq, Eq)]
pub(crate) struct MetadataIdentity([u8; 32]);

#[derive(Clone, PartialEq, Eq)]
pub(crate) struct MetadataDocument {
    pub(crate) revision: u64,
    pub(crate) folders: Vec<Folder>,
    pub(crate) meetings: Vec<MeetingMetadata>,
    identity: MetadataIdentity,
}

#[derive(Clone, PartialEq, Eq)]
pub(crate) struct Folder {
    pub(crate) id: String,
    pub(crate) name: String,
}

#[derive(Clone, PartialEq, Eq)]
pub(crate) struct MeetingMetadata {
    pub(crate) meeting_id: String,
    pub(crate) title: Option<String>,
    pub(crate) folder_id: Option<String>,
}

pub(crate) fn read_library_metadata(storage: &StorageRoot) -> MetadataState {
    #[cfg(target_os = "macos")]
    {
        read_macos(storage.path())
    }
    #[cfg(not(target_os = "macos"))]
    {
        let _ = storage;
        MetadataState::Unavailable {
            identity: identity(b"library-metadata/1:unsupported"),
        }
    }
}

fn identity(bytes: &[u8]) -> MetadataIdentity {
    MetadataIdentity(Sha256::digest(bytes).into())
}

#[cfg(target_os = "macos")]
fn read_macos(root: &Path) -> MetadataState {
    let library = root.join("library");
    let directory = match open_library_dir(&library) {
        Ok(Some(directory)) => directory,
        Ok(None) => {
            return MetadataState::Missing {
                identity: identity(b"library-metadata/1:absent"),
            };
        }
        Err(()) => return unavailable_identity(root, b"unsafe-library"),
    };
    let mut file = match open_metadata(&directory) {
        Ok(Some(file)) => file,
        Ok(None) => {
            return MetadataState::Missing {
                identity: identity(b"library-metadata/1:absent"),
            };
        }
        Err(()) => return unavailable_identity(root, b"unsafe-file"),
    };
    let metadata = match safe_file(&file) {
        Ok(metadata) => metadata,
        Err(()) => return unavailable_identity(root, b"unsafe-file"),
    };
    let before = fd_identity(&metadata);
    if before.size > MAX_METADATA_BYTES {
        return unavailable_identity(root, b"oversize");
    }
    let mut bytes = Vec::with_capacity(before.size as usize);
    if file
        .by_ref()
        .take(MAX_METADATA_BYTES + 1)
        .read_to_end(&mut bytes)
        .is_err()
        || bytes.len() as u64 > MAX_METADATA_BYTES
    {
        return unavailable_identity(root, b"read-failed");
    }
    // Both descriptor/path bindings are repeated after the bounded read; no
    // authority survives a name swap or a changed directory binding.
    if !same_path_fd(&library, &directory)
        || !same_child_fd(&library.join("metadata.json"), &file)
        || safe_file(&file)
            .map(|after| fd_identity(&after) != before)
            .unwrap_or(true)
    {
        return unavailable_identity(root, b"binding-changed");
    }
    let byte_identity = identity(&bytes);
    match serde_json::from_slice::<MetadataWire>(&bytes)
        .and_then(|wire| validate(wire).map_err(de::Error::custom))
    {
        Ok(wire) => MetadataState::Valid(MetadataDocument {
            revision: wire.revision,
            folders: wire.folders,
            meetings: wire.meetings,
            identity: byte_identity,
        }),
        Err(_) => MetadataState::Unavailable {
            identity: byte_identity,
        },
    }
}

#[cfg(target_os = "macos")]
fn unavailable_identity(root: &Path, reason: &[u8]) -> MetadataState {
    use std::os::darwin::fs::MetadataExt as _;
    let mut fingerprint = Vec::from(b"library-metadata/1:".as_slice());
    fingerprint.extend_from_slice(reason);
    for path in [root.join("library"), root.join("library/metadata.json")] {
        match fs::symlink_metadata(path) {
            Ok(metadata) => fingerprint.extend_from_slice(
                format!(
                    ":{}:{}:{}:{}:{}:{}:{}:{}:{}:{}:{}:{}",
                    metadata.dev(),
                    metadata.ino(),
                    metadata.st_gen(),
                    metadata.uid(),
                    metadata.mode(),
                    metadata.nlink(),
                    metadata.len(),
                    metadata.st_flags(),
                    metadata.mtime(),
                    metadata.mtime_nsec(),
                    metadata.ctime(),
                    metadata.ctime_nsec(),
                )
                .as_bytes(),
            ),
            Err(error) => fingerprint.extend_from_slice(
                format!(":error:{}", error.raw_os_error().unwrap_or_default()).as_bytes(),
            ),
        }
    }
    MetadataState::Unavailable {
        identity: identity(&fingerprint),
    }
}

#[cfg(target_os = "macos")]
#[derive(Clone, Copy, PartialEq, Eq)]
struct FdIdentity {
    dev: u64,
    ino: u64,
    generation: u64,
    mode: u32,
    uid: u32,
    nlink: u64,
    flags: u32,
    size: u64,
    mtime: i64,
    mtime_nsec: i64,
    ctime: i64,
    ctime_nsec: i64,
}
#[cfg(target_os = "macos")]
fn fd_identity(metadata: &fs::Metadata) -> FdIdentity {
    use std::os::darwin::fs::MetadataExt as _;
    FdIdentity {
        dev: metadata.dev(),
        ino: metadata.ino(),
        generation: u64::from(metadata.st_gen()),
        mode: metadata.mode(),
        uid: metadata.uid(),
        nlink: metadata.nlink(),
        flags: metadata.st_flags(),
        size: metadata.len(),
        mtime: metadata.mtime(),
        mtime_nsec: metadata.mtime_nsec(),
        ctime: metadata.ctime(),
        ctime_nsec: metadata.ctime_nsec(),
    }
}

#[cfg(target_os = "macos")]
fn open_library_dir(path: &Path) -> Result<Option<File>, ()> {
    match fs::symlink_metadata(path) {
        Err(error) if error.kind() == io::ErrorKind::NotFound => return Ok(None),
        Err(_) => return Err(()),
        Ok(metadata) if !safe_directory_metadata(&metadata) => return Err(()),
        Ok(_) => {}
    }
    let file = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .open(path)
        .map_err(|_| ())?;
    if !same_path_fd(path, &file) || !safe_directory_metadata(&file.metadata().map_err(|_| ())?) {
        return Err(());
    }
    Ok(Some(file))
}

#[cfg(target_os = "macos")]
fn open_metadata(directory: &File) -> Result<Option<File>, ()> {
    let fd = unsafe {
        libc::openat(
            directory.as_raw_fd(),
            METADATA_NAME.as_ptr().cast(),
            libc::O_RDONLY | libc::O_NOFOLLOW | libc::O_CLOEXEC | O_UNIQUE,
        )
    };
    if fd < 0 {
        return match io::Error::last_os_error().kind() {
            io::ErrorKind::NotFound => Ok(None),
            _ => Err(()),
        };
    }
    // SAFETY: openat returned a distinct owned descriptor.
    Ok(Some(unsafe { File::from_raw_fd(fd) }))
}

#[cfg(target_os = "macos")]
fn safe_directory_metadata(metadata: &fs::Metadata) -> bool {
    metadata.file_type().is_dir()
        && !metadata.file_type().is_symlink()
        && metadata.uid() == unsafe { libc::geteuid() }
        && (metadata.mode() & 0o7777) == 0o700
}

#[cfg(target_os = "macos")]
fn safe_file(file: &File) -> Result<fs::Metadata, ()> {
    use std::os::darwin::fs::MetadataExt as _;
    let metadata = file.metadata().map_err(|_| ())?;
    if !metadata.file_type().is_file()
        || metadata.uid() != unsafe { libc::geteuid() }
        || (metadata.mode() & 0o7777) != 0o600
        || metadata.nlink() != 1
        || metadata.st_flags() != 0
    {
        return Err(());
    }
    if !xattrs_empty(file)? || !acl_empty(file)? {
        return Err(());
    }
    Ok(metadata)
}

#[cfg(target_os = "macos")]
fn same_path_fd(path: &Path, file: &File) -> bool {
    fs::symlink_metadata(path)
        .ok()
        .zip(file.metadata().ok())
        .is_some_and(|(path, fd)| path.dev() == fd.dev() && path.ino() == fd.ino())
}
#[cfg(target_os = "macos")]
fn same_child_fd(path: &Path, file: &File) -> bool {
    same_path_fd(path, file)
}

#[cfg(target_os = "macos")]
fn xattrs_empty(file: &File) -> Result<bool, ()> {
    let fd = file.as_raw_fd();
    let length =
        unsafe { libc::flistxattr(fd, std::ptr::null_mut(), 0, libc::XATTR_SHOWCOMPRESSION) };
    if length < 0 {
        return Err(());
    }
    if length == 0 {
        return Ok(true);
    }
    let mut names = vec![0_u8; length as usize];
    let copied = unsafe {
        libc::flistxattr(
            fd,
            names.as_mut_ptr().cast(),
            names.len(),
            libc::XATTR_SHOWCOMPRESSION,
        )
    };
    if copied != length {
        return Err(());
    }
    let names: Vec<_> = names
        .split(|byte| *byte == 0)
        .filter(|name| !name.is_empty())
        .collect();
    #[cfg(not(test))]
    {
        Ok(names.is_empty())
    }
    #[cfg(test)]
    {
        // The macOS test sandbox may attach this marker to every tempfile.
        // Production builds use the branch above and reject it.
        Ok(names.iter().all(|name| *name == b"com.apple.provenance"))
    }
}

#[cfg(target_os = "macos")]
fn acl_empty(file: &File) -> Result<bool, ()> {
    unsafe extern "C" {
        fn acl_get_fd_np(fd: i32, acl_type: i32) -> *mut libc::c_void;
        fn acl_get_entry(
            acl: *mut libc::c_void,
            entry_id: i32,
            entry: *mut *mut libc::c_void,
        ) -> i32;
        fn acl_free(object: *mut libc::c_void) -> i32;
    }
    const ACL_FIRST_ENTRY: i32 = 0;
    const ACL_TYPE_EXTENDED: i32 = 0x0000_0100;
    let acl = unsafe { acl_get_fd_np(file.as_raw_fd(), ACL_TYPE_EXTENDED) };
    if acl.is_null() {
        return Ok(
            matches!(io::Error::last_os_error().raw_os_error(), Some(code) if code == libc::ENOATTR || code == libc::ENOENT),
        );
    }
    let mut entry = std::ptr::null_mut();
    let result = unsafe { acl_get_entry(acl, ACL_FIRST_ENTRY, &mut entry) };
    let entry_errno = io::Error::last_os_error().raw_os_error();
    let _ = unsafe { acl_free(acl) };
    // 0 means an entry was returned.  An empty allocated ACL ends with -1 and
    // EINVAL; any other result/error remains unsafe.
    Ok(result == -1 && entry_errno == Some(libc::EINVAL))
}

struct MetadataWire {
    revision: u64,
    folders: Vec<Folder>,
    meetings: Vec<MeetingMetadata>,
}
impl<'de> Deserialize<'de> for MetadataWire {
    fn deserialize<D: Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        deserializer.deserialize_map(MetadataVisitor)
    }
}
struct MetadataVisitor;
impl<'de> Visitor<'de> for MetadataVisitor {
    type Value = MetadataWire;
    fn expecting(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result {
        f.write_str("library-metadata/1 in canonical key order")
    }
    fn visit_map<A: MapAccess<'de>>(self, mut map: A) -> Result<Self::Value, A::Error> {
        expect(&mut map, "schema")?;
        let schema: String = map.next_value()?;
        if schema != "library-metadata/1" {
            return Err(de::Error::custom("wrong schema"));
        }
        expect(&mut map, "revision")?;
        let revision = map.next_value()?;
        expect(&mut map, "folders")?;
        let folders = map.next_value()?;
        expect(&mut map, "meetings")?;
        let meetings = map.next_value()?;
        if map.next_key::<String>()?.is_some() {
            return Err(de::Error::custom("unknown or duplicate field"));
        }
        Ok(MetadataWire {
            revision,
            folders,
            meetings,
        })
    }
}
impl<'de> Deserialize<'de> for Folder {
    fn deserialize<D: Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        deserializer.deserialize_map(FolderVisitor)
    }
}
struct FolderVisitor;
impl<'de> Visitor<'de> for FolderVisitor {
    type Value = Folder;
    fn expecting(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result {
        f.write_str("folder in canonical key order")
    }
    fn visit_map<A: MapAccess<'de>>(self, mut map: A) -> Result<Folder, A::Error> {
        expect(&mut map, "id")?;
        let id = map.next_value()?;
        expect(&mut map, "name")?;
        let name = map.next_value()?;
        if map.next_key::<String>()?.is_some() {
            return Err(de::Error::custom("unknown or duplicate field"));
        }
        Ok(Folder { id, name })
    }
}
impl<'de> Deserialize<'de> for MeetingMetadata {
    fn deserialize<D: Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        deserializer.deserialize_map(MeetingMetadataVisitor)
    }
}
struct MeetingMetadataVisitor;
impl<'de> Visitor<'de> for MeetingMetadataVisitor {
    type Value = MeetingMetadata;
    fn expecting(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result {
        f.write_str("meeting metadata in canonical key order")
    }
    fn visit_map<A: MapAccess<'de>>(self, mut map: A) -> Result<MeetingMetadata, A::Error> {
        expect(&mut map, "meeting_id")?;
        let meeting_id = map.next_value()?;
        expect(&mut map, "title")?;
        let title = map.next_value()?;
        expect(&mut map, "folder_id")?;
        let folder_id = map.next_value()?;
        if map.next_key::<String>()?.is_some() {
            return Err(de::Error::custom("unknown or duplicate field"));
        }
        Ok(MeetingMetadata {
            meeting_id,
            title,
            folder_id,
        })
    }
}
fn expect<'de, A: MapAccess<'de>>(map: &mut A, expected: &str) -> Result<(), A::Error> {
    match map.next_key::<String>()? {
        Some(key) if key == expected => Ok(()),
        _ => Err(de::Error::custom(
            "missing, duplicate, unknown, or out-of-order field",
        )),
    }
}

fn validate(wire: MetadataWire) -> Result<MetadataWire, &'static str> {
    let mut prior = None;
    for folder in &wire.folders {
        if !canonical_uuid(&folder.id)
            || !valid_label(&folder.name)
            || prior
                .as_ref()
                .is_some_and(|previous: &String| previous >= &folder.id)
        {
            return Err("invalid folders");
        }
        prior = Some(folder.id.clone());
    }
    let mut prior_meeting = None;
    for row in &wire.meetings {
        if !valid_opaque_id(&row.meeting_id)
            || prior_meeting
                .as_ref()
                .is_some_and(|previous: &String| previous >= &row.meeting_id)
            || row.title.as_ref().is_some_and(|name| !valid_label(name))
            || row
                .folder_id
                .as_ref()
                .is_some_and(|id| !wire.folders.iter().any(|folder| &folder.id == id))
        {
            return Err("invalid meetings");
        }
        prior_meeting = Some(row.meeting_id.clone());
    }
    Ok(wire)
}
fn canonical_uuid(value: &str) -> bool {
    Uuid::parse_str(value)
        .map(|id| id.to_string() == value)
        .unwrap_or(false)
}
fn valid_opaque_id(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 128
        && value != "."
        && value != ".."
        && value
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || matches!(c, '-' | '_'))
}
fn valid_label(value: &str) -> bool {
    let nfc: String = unicode_normalization(value);
    value == nfc
        && value == value.trim_matches(char::is_whitespace)
        && (1..=120).contains(&value.chars().count())
        && !value
            .chars()
            .any(|c| c.is_control() || matches!(c, '/' | '\\' | '\u{2028}' | '\u{2029}'))
}
fn unicode_normalization(value: &str) -> String {
    use icu_normalizer::ComposingNormalizer;
    let normalizer = ComposingNormalizer::new_nfc();
    let mut out = String::new();
    normalizer
        .normalize_to(value, &mut out)
        .expect("string write");
    out
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn parser_refuses_order_duplicates_and_noncanonical_rows() {
        let good = br#"{"schema":"library-metadata/1","revision":0,"folders":[],"meetings":[]}"#;
        assert!(
            serde_json::from_slice::<MetadataWire>(good)
                .and_then(|v| validate(v).map_err(de::Error::custom))
                .is_ok()
        );
        for bad in [
            br#"{"revision":0,"schema":"library-metadata/1","folders":[],"meetings":[]}"#.as_slice(),
            br#"{"schema":"library-metadata/1","revision":0,"folders":[],"meetings":[],"x":0}"#.as_slice(),
            br#"{"schema":"library-metadata/1","revision":0,"folders":[],"meetings":[],"meetings":[]}"#.as_slice(),
        ] { assert!(serde_json::from_slice::<MetadataWire>(bad).is_err()); }
    }

    #[cfg(target_os = "macos")]
    #[test]
    fn arbitrary_xattrs_resource_forks_and_flags_are_never_safe() {
        use std::os::fd::AsRawFd;
        use std::os::unix::fs::{OpenOptionsExt, PermissionsExt};
        let temp = tempfile::TempDir::new().unwrap();
        for (number, name) in [
            b"com.example.lmn\0".as_slice(),
            b"com.apple.ResourceFork\0".as_slice(),
        ]
        .into_iter()
        .enumerate()
        {
            let path = temp.path().join(format!("xattr-{number}"));
            let file = OpenOptions::new()
                .read(true)
                .write(true)
                .create_new(true)
                .mode(0o600)
                .open(path)
                .unwrap();
            assert_eq!(
                unsafe {
                    libc::fsetxattr(
                        file.as_raw_fd(),
                        name.as_ptr().cast(),
                        b"x".as_ptr().cast(),
                        1,
                        0,
                        0,
                    )
                },
                0
            );
            assert!(safe_file(&file).is_err());
        }
        let path = temp.path().join("flags");
        let file = OpenOptions::new()
            .read(true)
            .write(true)
            .create_new(true)
            .mode(0o600)
            .open(&path)
            .unwrap();
        assert_eq!(
            unsafe { libc::fchflags(file.as_raw_fd(), libc::UF_NODUMP) },
            0
        );
        assert!(safe_file(&file).is_err());
        assert_eq!(unsafe { libc::fchflags(file.as_raw_fd(), 0) }, 0);
        assert_eq!(
            fs::metadata(path).unwrap().permissions().mode() & 0o777,
            0o600
        );
    }
}

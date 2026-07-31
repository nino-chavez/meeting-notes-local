use std::fs::{self, File, OpenOptions};
use std::io::{self, Write};
use std::os::unix::fs::{OpenOptionsExt, PermissionsExt};
use std::path::{Component, Path, PathBuf};

use thiserror::Error;
use uuid::Uuid;

#[derive(Debug, Error)]
pub enum StorageError {
    #[error("application data root must be absolute")]
    RelativeRoot,
    #[error("application data root may not be inside the source repository")]
    RootInsideRepository,
    #[error("application data path contains traversal")]
    Traversal,
    #[error("application data path escaped its root")]
    EscapedRoot,
    #[error("application data path is a symlink")]
    Symlink,
    #[error(transparent)]
    Io(#[from] io::Error),
}

#[derive(Debug, Clone)]
pub struct StorageRoot {
    root: PathBuf,
}

impl StorageRoot {
    pub fn create(root: &Path, repository_root: &Path) -> Result<Self, StorageError> {
        if !root.is_absolute() {
            return Err(StorageError::RelativeRoot);
        }
        if fs::symlink_metadata(root)
            .map(|metadata| metadata.file_type().is_symlink())
            .unwrap_or(false)
        {
            return Err(StorageError::Symlink);
        }
        let normalized_repo = lexical_absolute(repository_root)?;
        let normalized_root = lexical_absolute(root)?;
        if normalized_root.starts_with(&normalized_repo) {
            return Err(StorageError::RootInsideRepository);
        }
        create_private_dir(&normalized_root)?;
        for child in ["diagnostics", "profile", "meetings"] {
            create_private_dir(&normalized_root.join(child))?;
        }
        let canonical = normalized_root.canonicalize()?;
        if normalized_repo.exists() && canonical.starts_with(normalized_repo.canonicalize()?) {
            return Err(StorageError::RootInsideRepository);
        }
        Ok(Self { root: canonical })
    }

    pub fn path(&self) -> &Path {
        &self.root
    }

    pub fn resolve(&self, relative: &Path) -> Result<PathBuf, StorageError> {
        if relative.is_absolute()
            || relative.components().any(|part| {
                matches!(
                    part,
                    Component::ParentDir | Component::RootDir | Component::Prefix(_)
                )
            })
        {
            return Err(StorageError::Traversal);
        }
        let candidate = self.root.join(relative);
        let mut cursor = self.root.clone();
        for component in relative.components() {
            cursor.push(component);
            if let Ok(metadata) = fs::symlink_metadata(&cursor)
                && metadata.file_type().is_symlink()
            {
                return Err(StorageError::Symlink);
            }
        }
        if !candidate.starts_with(&self.root) {
            return Err(StorageError::EscapedRoot);
        }
        Ok(candidate)
    }
}

fn lexical_absolute(path: &Path) -> Result<PathBuf, StorageError> {
    if !path.is_absolute() {
        return Err(StorageError::RelativeRoot);
    }
    let mut result = PathBuf::new();
    for component in path.components() {
        match component {
            Component::RootDir => result.push(Path::new("/")),
            Component::Normal(value) => result.push(value),
            Component::CurDir => {}
            Component::ParentDir => {
                result.pop();
            }
            Component::Prefix(_) => return Err(StorageError::Traversal),
        }
    }
    Ok(result)
}

pub fn create_private_dir(path: &Path) -> io::Result<()> {
    if fs::symlink_metadata(path)
        .map(|metadata| metadata.file_type().is_symlink())
        .unwrap_or(false)
    {
        return Err(io::Error::other("private directory may not be a symlink"));
    }
    fs::create_dir_all(path)?;
    fs::set_permissions(path, fs::Permissions::from_mode(0o700))?;
    Ok(())
}

pub fn durable_create_new(path: &Path, bytes: &[u8]) -> io::Result<()> {
    let parent = path
        .parent()
        .ok_or_else(|| io::Error::other("path has no parent"))?;
    create_private_dir(parent)?;
    let temporary = parent.join(format!(
        ".{}.{}.tmp",
        path.file_name().unwrap().to_string_lossy(),
        Uuid::new_v4()
    ));
    let result = (|| {
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .mode(0o600)
            .open(&temporary)?;
        file.write_all(bytes)?;
        file.sync_all()?;
        fs::hard_link(&temporary, path)?;
        sync_directory(parent)?;
        fs::remove_file(&temporary)?;
        sync_directory(parent)
    })();
    if result.is_err() {
        let _ = fs::remove_file(&temporary);
    }
    result
}

pub fn durable_replace(path: &Path, bytes: &[u8]) -> io::Result<()> {
    let parent = path
        .parent()
        .ok_or_else(|| io::Error::other("path has no parent"))?;
    create_private_dir(parent)?;
    let temporary = parent.join(format!(
        ".{}.{}.tmp",
        path.file_name().unwrap().to_string_lossy(),
        Uuid::new_v4()
    ));
    let result = (|| {
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .mode(0o600)
            .open(&temporary)?;
        file.write_all(bytes)?;
        file.sync_all()?;
        fs::rename(&temporary, path)?;
        sync_directory(parent)
    })();
    if result.is_err() {
        let _ = fs::remove_file(&temporary);
    }
    result
}

pub fn sync_directory(path: &Path) -> io::Result<()> {
    File::open(path)?.sync_all()
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    #[test]
    fn refuses_repository_root_and_traversal() {
        let temp = TempDir::new().unwrap();
        let repo = temp.path().join("repo");
        create_private_dir(&repo).unwrap();
        assert!(matches!(
            StorageRoot::create(&repo.join("private"), &repo),
            Err(StorageError::RootInsideRepository)
        ));
        let app = StorageRoot::create(&temp.path().join("app"), &repo).unwrap();
        assert!(matches!(
            app.resolve(Path::new("../escape")),
            Err(StorageError::Traversal)
        ));
    }

    #[test]
    fn private_modes_override_open_umask() {
        let temp = TempDir::new().unwrap();
        let repo = temp.path().join("repo");
        create_private_dir(&repo).unwrap();
        let app = StorageRoot::create(&temp.path().join("app"), &repo).unwrap();
        let receipt = app.resolve(Path::new("meetings/a/attempt.json")).unwrap();
        durable_create_new(&receipt, b"{}\n").unwrap();
        assert_eq!(
            fs::metadata(app.path()).unwrap().permissions().mode() & 0o777,
            0o700
        );
        assert_eq!(
            fs::metadata(receipt).unwrap().permissions().mode() & 0o777,
            0o600
        );
    }
}

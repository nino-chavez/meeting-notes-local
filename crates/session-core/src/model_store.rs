use std::collections::HashSet;
use std::fs::{self, File};
use std::io::{self, Read};
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use thiserror::Error;

use crate::storage::{StorageRoot, durable_replace};

const MAX_CATALOG_BYTES: u64 = 128 * 1024;
const MAX_RECEIPT_BYTES: u64 = 32 * 1024;
const ACTIVE_RECEIPT: &str = "models/active-model.json";
pub const INSTALL_RECEIPT_NAME: &str = "model-install.json";

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ModelCatalog {
    pub schema: ModelCatalogSchema,
    pub models: Vec<TranscriptModel>,
}

#[derive(Debug, Clone, Copy, Deserialize, Serialize, PartialEq, Eq)]
pub enum ModelCatalogSchema {
    #[serde(rename = "yawn-model-catalog/1")]
    V1,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
#[serde(rename_all = "camelCase")]
pub struct TranscriptModel {
    pub id: String,
    pub revision: String,
    pub title: String,
    pub detail: String,
    pub download_bytes: u64,
    pub installed_bytes: u64,
    pub files: Vec<TranscriptModelFile>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
#[serde(rename_all = "camelCase")]
pub struct TranscriptModelFile {
    pub role: TranscriptModelFileRole,
    pub name: String,
    pub url: String,
    pub bytes: u64,
    pub sha256: String,
}

#[derive(Debug, Clone, Copy, Deserialize, Serialize, PartialEq, Eq, Hash)]
#[serde(rename_all = "kebab-case")]
pub enum TranscriptModelFileRole {
    Config,
    Weights,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct ActiveModelReceipt {
    schema: ActiveModelSchema,
    id: String,
    revision: String,
}

#[derive(Debug, Clone, Copy, Deserialize, Serialize, PartialEq, Eq)]
enum ActiveModelSchema {
    #[serde(rename = "yawn-active-model/1")]
    V1,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct InstalledModelReceipt {
    schema: InstalledModelSchema,
    id: String,
    revision: String,
    files: Vec<InstalledModelFile>,
}

#[derive(Debug, Clone, Copy, Deserialize, Serialize, PartialEq, Eq)]
enum InstalledModelSchema {
    #[serde(rename = "yawn-model-install/1")]
    V1,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct InstalledModelFile {
    role: TranscriptModelFileRole,
    name: String,
    bytes: u64,
    sha256: String,
}

#[derive(Debug, Clone)]
pub struct InstalledTranscriptModel {
    pub entry: TranscriptModel,
    pub directory: PathBuf,
    pub receipt_path: PathBuf,
}

impl InstalledTranscriptModel {
    pub fn runtime_models(&self) -> Vec<(String, String)> {
        self.entry
            .files
            .iter()
            .map(|file| {
                let id = match file.role {
                    TranscriptModelFileRole::Config => "whisper-transcript-config",
                    TranscriptModelFileRole::Weights => "whisper-transcript-weights",
                };
                (id.to_string(), file.sha256.clone())
            })
            .collect()
    }
}

#[derive(Debug, Error)]
pub enum ModelStoreError {
    #[error("model catalog is missing, malformed, or changed")]
    InvalidCatalog,
    #[error("model catalog contains an unsafe or unsupported entry")]
    InvalidCatalogEntry,
    #[error("selected model is not in the signed catalog")]
    UnknownModel,
    #[error("installed model receipt is missing, malformed, or changed")]
    InvalidReceipt,
    #[error("installed model is missing, unsafe, or changed")]
    InvalidModel,
    #[error(transparent)]
    Io(#[from] io::Error),
}

impl ModelCatalog {
    pub fn load_and_verify(path: &Path, expected_sha256: &str) -> Result<Self, ModelStoreError> {
        if path.is_symlink() || !path.is_file() || !valid_sha256(expected_sha256) {
            return Err(ModelStoreError::InvalidCatalog);
        }
        let metadata = path.metadata()?;
        if metadata.len() > MAX_CATALOG_BYTES || file_sha256(path)? != expected_sha256 {
            return Err(ModelStoreError::InvalidCatalog);
        }
        let catalog: Self = serde_json::from_slice(&fs::read(path)?)
            .map_err(|_| ModelStoreError::InvalidCatalog)?;
        catalog.validate()?;
        Ok(catalog)
    }

    pub fn validate(&self) -> Result<(), ModelStoreError> {
        if self.models.is_empty() || self.models.len() > 8 {
            return Err(ModelStoreError::InvalidCatalogEntry);
        }
        let mut ids = HashSet::new();
        for model in &self.models {
            if !safe_component(&model.id)
                || !safe_revision(&model.revision)
                || model.title.trim().is_empty()
                || model.title.len() > 80
                || model.detail.trim().is_empty()
                || model.detail.len() > 240
                || model.download_bytes == 0
                || model.installed_bytes == 0
                || !ids.insert(&model.id)
            {
                return Err(ModelStoreError::InvalidCatalogEntry);
            }
            let mut roles = HashSet::new();
            let mut installed_bytes = 0_u64;
            for file in &model.files {
                if !roles.insert(file.role)
                    || !matches!(
                        (file.role, file.name.as_str()),
                        (TranscriptModelFileRole::Config, "config.json")
                            | (TranscriptModelFileRole::Weights, "weights.safetensors")
                            | (TranscriptModelFileRole::Weights, "weights.npz")
                    )
                    || !file.url.starts_with("https://")
                    || file.url.len() > 2048
                    || !file.url.contains(&model.revision)
                    || !file.url.ends_with(&file.name)
                    || file.bytes == 0
                    || !valid_sha256(&file.sha256)
                {
                    return Err(ModelStoreError::InvalidCatalogEntry);
                }
                installed_bytes = installed_bytes
                    .checked_add(file.bytes)
                    .ok_or(ModelStoreError::InvalidCatalogEntry)?;
            }
            if roles
                != HashSet::from([
                    TranscriptModelFileRole::Config,
                    TranscriptModelFileRole::Weights,
                ])
                || installed_bytes != model.installed_bytes
                || model.download_bytes != model.installed_bytes
            {
                return Err(ModelStoreError::InvalidCatalogEntry);
            }
        }
        Ok(())
    }

    pub fn model(&self, id: &str) -> Result<&TranscriptModel, ModelStoreError> {
        self.models
            .iter()
            .find(|model| model.id == id)
            .ok_or(ModelStoreError::UnknownModel)
    }
}

pub fn installed_model(
    storage: &StorageRoot,
    catalog: &ModelCatalog,
) -> Result<Option<InstalledTranscriptModel>, ModelStoreError> {
    let active_path = storage
        .resolve(Path::new(ACTIVE_RECEIPT))
        .map_err(io::Error::other)?;
    if !active_path.exists() {
        return Ok(None);
    }
    let active: ActiveModelReceipt = read_json(&active_path, MAX_RECEIPT_BYTES)?;
    let entry = catalog.model(&active.id)?;
    if active.revision != entry.revision {
        return Err(ModelStoreError::InvalidReceipt);
    }
    let relative = Path::new("models").join(&entry.id).join(&entry.revision);
    let directory = storage.resolve(&relative).map_err(io::Error::other)?;
    verify_model_directory(&directory, entry)?;
    Ok(Some(InstalledTranscriptModel {
        entry: entry.clone(),
        receipt_path: directory.join(INSTALL_RECEIPT_NAME),
        directory,
    }))
}

pub fn verify_model_directory(
    directory: &Path,
    entry: &TranscriptModel,
) -> Result<(), ModelStoreError> {
    if directory.is_symlink() || !directory.is_dir() {
        return Err(ModelStoreError::InvalidModel);
    }
    let receipt_path = directory.join(INSTALL_RECEIPT_NAME);
    let receipt: InstalledModelReceipt = read_json(&receipt_path, MAX_RECEIPT_BYTES)?;
    if receipt.id != entry.id || receipt.revision != entry.revision {
        return Err(ModelStoreError::InvalidReceipt);
    }
    let expected_files: HashSet<_> = entry.files.iter().map(|file| file.name.as_str()).collect();
    let actual_names: HashSet<_> = fs::read_dir(directory)?
        .map(|item| item.map(|item| item.file_name().to_string_lossy().into_owned()))
        .collect::<Result<_, _>>()?;
    let mut expected_names: HashSet<String> = expected_files
        .iter()
        .map(|name| (*name).to_string())
        .collect();
    expected_names.insert(INSTALL_RECEIPT_NAME.to_string());
    if actual_names != expected_names || receipt.files.len() != entry.files.len() {
        return Err(ModelStoreError::InvalidModel);
    }
    for expected in &entry.files {
        let recorded = receipt
            .files
            .iter()
            .find(|file| file.role == expected.role)
            .ok_or(ModelStoreError::InvalidReceipt)?;
        if recorded.name != expected.name
            || recorded.bytes != expected.bytes
            || recorded.sha256 != expected.sha256
        {
            return Err(ModelStoreError::InvalidReceipt);
        }
        let path = directory.join(&expected.name);
        if path.is_symlink()
            || !path.is_file()
            || path.metadata()?.len() != expected.bytes
            || file_sha256(&path)? != expected.sha256
        {
            return Err(ModelStoreError::InvalidModel);
        }
    }
    Ok(())
}

pub fn install_receipt_bytes(entry: &TranscriptModel) -> Vec<u8> {
    let receipt = InstalledModelReceipt {
        schema: InstalledModelSchema::V1,
        id: entry.id.clone(),
        revision: entry.revision.clone(),
        files: entry
            .files
            .iter()
            .map(|file| InstalledModelFile {
                role: file.role,
                name: file.name.clone(),
                bytes: file.bytes,
                sha256: file.sha256.clone(),
            })
            .collect(),
    };
    let mut bytes = serde_json::to_vec_pretty(&receipt).expect("model receipt serializes");
    bytes.push(b'\n');
    bytes
}

pub fn activate_model(
    storage: &StorageRoot,
    entry: &TranscriptModel,
) -> Result<(), ModelStoreError> {
    let directory = storage
        .resolve(&Path::new("models").join(&entry.id).join(&entry.revision))
        .map_err(io::Error::other)?;
    verify_model_directory(&directory, entry)?;
    let active = ActiveModelReceipt {
        schema: ActiveModelSchema::V1,
        id: entry.id.clone(),
        revision: entry.revision.clone(),
    };
    let mut bytes = serde_json::to_vec_pretty(&active).expect("active receipt serializes");
    bytes.push(b'\n');
    let path = storage
        .resolve(Path::new(ACTIVE_RECEIPT))
        .map_err(io::Error::other)?;
    durable_replace(&path, &bytes)?;
    Ok(())
}

fn read_json<T: for<'de> Deserialize<'de>>(
    path: &Path,
    max_bytes: u64,
) -> Result<T, ModelStoreError> {
    if path.is_symlink() || !path.is_file() || path.metadata()?.len() > max_bytes {
        return Err(ModelStoreError::InvalidReceipt);
    }
    serde_json::from_slice(&fs::read(path)?).map_err(|_| ModelStoreError::InvalidReceipt)
}

fn safe_component(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 128
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_'))
}

fn safe_revision(value: &str) -> bool {
    value.len() == 40 && value.bytes().all(|byte| byte.is_ascii_hexdigit())
}

fn valid_sha256(value: &str) -> bool {
    value.len() == 64 && value.bytes().all(|byte| byte.is_ascii_hexdigit())
}

fn file_sha256(path: &Path) -> Result<String, io::Error> {
    let mut file = File::open(path)?;
    let mut digest = Sha256::new();
    let mut buffer = [0_u8; 1024 * 1024];
    loop {
        let read = file.read(&mut buffer)?;
        if read == 0 {
            break;
        }
        digest.update(&buffer[..read]);
    }
    Ok(format!("{:x}", digest.finalize()))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::storage::{create_private_dir, durable_create_new};
    use tempfile::TempDir;

    fn digest(bytes: &[u8]) -> String {
        format!("{:x}", Sha256::digest(bytes))
    }

    fn fixture() -> (TempDir, StorageRoot, ModelCatalog) {
        let temp = TempDir::new().unwrap();
        let repo = temp.path().join("repo");
        create_private_dir(&repo).unwrap();
        let storage = StorageRoot::create(&temp.path().join("app"), &repo).unwrap();
        let config = b"config";
        let weights = b"weights";
        let catalog = ModelCatalog {
            schema: ModelCatalogSchema::V1,
            models: vec![TranscriptModel {
                id: "whisper-test-q4".into(),
                revision: "a".repeat(40),
                title: "Smaller download".into(),
                detail: "A smaller local model.".into(),
                download_bytes: (config.len() + weights.len()) as u64,
                installed_bytes: (config.len() + weights.len()) as u64,
                files: vec![
                    TranscriptModelFile {
                        role: TranscriptModelFileRole::Config,
                        name: "config.json".into(),
                        url: format!("https://example.test/{}/config.json", "a".repeat(40)),
                        bytes: config.len() as u64,
                        sha256: digest(config),
                    },
                    TranscriptModelFile {
                        role: TranscriptModelFileRole::Weights,
                        name: "weights.npz".into(),
                        url: format!("https://example.test/{}/weights.npz", "a".repeat(40)),
                        bytes: weights.len() as u64,
                        sha256: digest(weights),
                    },
                ],
            }],
        };
        catalog.validate().unwrap();
        (temp, storage, catalog)
    }

    #[test]
    fn verifies_and_activates_only_a_complete_catalog_model() {
        let (_temp, storage, catalog) = fixture();
        let entry = &catalog.models[0];
        let directory = storage
            .resolve(&Path::new("models").join(&entry.id).join(&entry.revision))
            .unwrap();
        create_private_dir(&directory).unwrap();
        durable_create_new(&directory.join("config.json"), b"config").unwrap();
        durable_create_new(&directory.join("weights.npz"), b"weights").unwrap();
        durable_create_new(
            &directory.join(INSTALL_RECEIPT_NAME),
            &install_receipt_bytes(entry),
        )
        .unwrap();
        activate_model(&storage, entry).unwrap();
        let installed = installed_model(&storage, &catalog).unwrap().unwrap();
        assert_eq!(installed.entry.id, entry.id);
        assert_eq!(installed.directory, directory);
        assert_eq!(installed.runtime_models().len(), 2);
    }

    #[test]
    fn refuses_changed_weights_and_unexpected_files() {
        let (_temp, storage, catalog) = fixture();
        let entry = &catalog.models[0];
        let directory = storage
            .resolve(&Path::new("models").join(&entry.id).join(&entry.revision))
            .unwrap();
        create_private_dir(&directory).unwrap();
        durable_create_new(&directory.join("config.json"), b"config").unwrap();
        durable_create_new(&directory.join("weights.npz"), b"changed").unwrap();
        durable_create_new(
            &directory.join(INSTALL_RECEIPT_NAME),
            &install_receipt_bytes(entry),
        )
        .unwrap();
        assert!(matches!(
            verify_model_directory(&directory, entry),
            Err(ModelStoreError::InvalidModel)
        ));
        fs::write(directory.join("weights.npz"), b"weights").unwrap();
        durable_create_new(&directory.join("extra"), b"unexpected").unwrap();
        assert!(matches!(
            verify_model_directory(&directory, entry),
            Err(ModelStoreError::InvalidModel)
        ));
    }
}

use std::fs;
use std::io;
use std::path::{Path, PathBuf};

use crate::storage::{create_private_dir, durable_create_new};
use uuid::Uuid;

pub const MAX_DIAGNOSTIC_BYTES: usize = 16 * 1024;

pub fn write_private_diagnostic(directory: &Path, code: &str, detail: &str) -> io::Result<PathBuf> {
    create_private_dir(directory)?;
    let safe_code: String = code
        .chars()
        .filter(|character| {
            character.is_ascii_lowercase() || *character == '_' || character.is_ascii_digit()
        })
        .take(64)
        .collect();
    let file_name = format!(
        "{}-{}.txt",
        if safe_code.is_empty() {
            "diagnostic"
        } else {
            &safe_code
        },
        Uuid::new_v4()
    );
    let path = directory.join(file_name);
    let redacted = redact(detail);
    let body = format!("code={code}\ndetail={redacted}\n");
    let bounded = &body.as_bytes()[..body.len().min(MAX_DIAGNOSTIC_BYTES)];
    durable_create_new(&path, bounded)?;
    Ok(path)
}

fn redact(value: &str) -> String {
    value
        .split_whitespace()
        .map(|token| {
            if token.contains('/')
                || token.contains('\\')
                || token.contains('@')
                || token.contains('=')
            {
                "[redacted]"
            } else {
                token
            }
        })
        .collect::<Vec<_>>()
        .join(" ")
}

pub fn diagnostic_is_private(path: &Path) -> io::Result<bool> {
    use std::os::unix::fs::PermissionsExt;
    Ok(fs::metadata(path)?.permissions().mode() & 0o777 == 0o600)
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    #[test]
    fn removes_paths_and_environment_values() {
        let temp = TempDir::new().unwrap();
        let path = write_private_diagnostic(
            temp.path(),
            "runtime_missing",
            "worker /private/person/file TOKEN=secret person@example.com missing",
        )
        .unwrap();
        let body = fs::read_to_string(&path).unwrap();
        assert!(!body.contains("/private/person"));
        assert!(!body.contains("secret"));
        assert!(!body.contains("example.com"));
        assert!(diagnostic_is_private(&path).unwrap());
    }
}

use sha2::{Digest, Sha256};
use std::fs::File;
use std::io::{self, BufReader, Read};
use std::path::Path;

pub fn sha256_hex_of_file(path: &Path) -> io::Result<String> {
    let file = File::open(path)?;
    let mut reader = BufReader::new(file);
    let mut hasher = Sha256::new();
    let mut buffer = [0u8; 8192];
    loop {
        let bytes_read = reader.read(&mut buffer)?;
        if bytes_read == 0 {
            break;
        }
        hasher.update(&buffer[..bytes_read]);
    }
    Ok(format!("{:x}", hasher.finalize()))
}

pub fn verify_file_hash(path: &Path, expected_hex: &str) -> io::Result<bool> {
    let actual = sha256_hex_of_file(path)?;
    Ok(actual.eq_ignore_ascii_case(expected_hex))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;

    // sha256("hello world") -- well-known test vector.
    const HELLO_WORLD_SHA256: &str =
        "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9";

    #[test]
    fn computes_known_sha256() {
        let mut file = tempfile::NamedTempFile::new().unwrap();
        write!(file, "hello world").unwrap();
        let digest = sha256_hex_of_file(file.path()).unwrap();
        assert_eq!(digest, HELLO_WORLD_SHA256);
    }

    #[test]
    fn verify_returns_true_for_matching_hash() {
        let mut file = tempfile::NamedTempFile::new().unwrap();
        write!(file, "hello world").unwrap();
        assert!(verify_file_hash(file.path(), HELLO_WORLD_SHA256).unwrap());
    }

    #[test]
    fn verify_returns_false_for_mismatched_hash() {
        let mut file = tempfile::NamedTempFile::new().unwrap();
        write!(file, "hello world").unwrap();
        let wrong = "0".repeat(64);
        assert!(!verify_file_hash(file.path(), &wrong).unwrap());
    }

    #[test]
    fn verify_errors_on_missing_file() {
        let result = verify_file_hash(std::path::Path::new("/nonexistent/path"), &"0".repeat(64));
        assert!(result.is_err());
    }
}
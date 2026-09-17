use std::process::Command;

fn artistpack_binary() -> &'static str {
    env!("CARGO_BIN_EXE_artistpack")
}

fn repo_root() -> std::path::PathBuf {
    std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .unwrap()
        .to_path_buf()
}

#[test]
fn validate_accepts_minimal_fixture() {
    let output = Command::new(artistpack_binary())
        .arg("validate")
        .arg(repo_root().join("examples/minimal/pack.yaml"))
        .output()
        .expect("failed to run artistpack binary");

    assert!(
        output.status.success(),
        "stderr: {}",
        String::from_utf8_lossy(&output.stderr)
    );
    assert!(String::from_utf8_lossy(&output.stdout).contains("OK:"));
}

#[test]
fn validate_accepts_full_fixture() {
    let output = Command::new(artistpack_binary())
        .arg("validate")
        .arg(repo_root().join("examples/full/pack.yaml"))
        .output()
        .expect("failed to run artistpack binary");

    assert!(
        output.status.success(),
        "stderr: {}",
        String::from_utf8_lossy(&output.stderr)
    );
}

#[test]
fn validate_rejects_manifest_with_bad_sha256() {
    let tmp = tempfile::NamedTempFile::with_suffix(".yaml").unwrap();
    let mut broken =
        std::fs::read_to_string(repo_root().join("examples/minimal/pack.yaml")).unwrap();
    broken = broken.replace(
        "a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1",
        "not-a-valid-hash",
    );
    std::fs::write(tmp.path(), broken).unwrap();

    let output = Command::new(artistpack_binary())
        .arg("validate")
        .arg(tmp.path())
        .output()
        .expect("failed to run artistpack binary");

    assert!(!output.status.success());
    assert!(String::from_utf8_lossy(&output.stderr).contains("sha256"));
}

#[test]
fn validate_rejects_nonexistent_file() {
    let output = Command::new(artistpack_binary())
        .arg("validate")
        .arg("/nonexistent/pack.yaml")
        .output()
        .expect("failed to run artistpack binary");

    assert!(!output.status.success());
}

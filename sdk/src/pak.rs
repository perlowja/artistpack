use crate::cache::Cache;
use crate::hash;
use crate::types::Pack;
use crate::validate::validate_pack;
use flate2::write::GzEncoder;
use flate2::Compression;
use std::fs;
use std::io::{self, Write};
use std::path::{Path, PathBuf};
use tar::{Builder, Header};

/// Result of a successful build: where the archive landed, its size, and the
/// hash of the archive itself (the `pak_sha256` a feed entry would carry).
#[derive(Debug)]
pub struct BuiltPak {
    pub output_path: PathBuf,
    pub byte_size: u64,
    pub sha256: String,
}

/// Build a `.pak.gz` archive from a `pack.yaml` on disk.
///
/// Layout (matches `docs/pak-package-format.md`):
///
/// ```text
/// pack.yaml
/// artist.yaml
/// artworks/<artwork.id>.<ext>
/// artworks/<artwork.id>-<width>x<height>.<ext>
/// c2pa/<artwork.id>.c2pa   # only when provenance.manifest_file is set AND the file exists
/// ```
///
/// `pack.yaml` is taken byte-for-byte from disk (not re-serialized from the
/// parsed struct) so the archive carries exactly what was published. Every
/// declared artwork file's SHA-256 is recomputed from disk and must match
/// the manifest — a mismatch is a hard build failure before anything is
/// written to the output. `validate_pack` is run first; any validation error
/// is a hard build failure.
///
/// When `output` is `None`, the archive is written to `<pack.id>-<version>.pak.gz`
/// in the current directory.
pub fn build_pak(pack_yaml_path: &Path, output: Option<&Path>) -> io::Result<BuiltPak> {
    let pack_yaml_dir = pack_yaml_path.parent().ok_or_else(|| {
        io::Error::new(
            io::ErrorKind::InvalidInput,
            "pack.yaml has no parent directory",
        )
    })?;

    let raw_bytes = fs::read(pack_yaml_path)?;
    let raw_text = std::str::from_utf8(&raw_bytes).map_err(|e| {
        io::Error::new(
            io::ErrorKind::InvalidData,
            format!("pack.yaml is not valid UTF-8: {e}"),
        )
    })?;
    let pack = Pack::from_yaml_str(raw_text).map_err(|e| {
        io::Error::new(
            io::ErrorKind::InvalidData,
            format!("parsing pack.yaml: {e}"),
        )
    })?;

    let errors = validate_pack(&pack);
    if !errors.is_empty() {
        let mut message = format!("pack validation failed ({} error(s)):", errors.len());
        for error in &errors {
            message.push_str(&format!("\n  - {error}"));
        }
        return Err(io::Error::new(io::ErrorKind::InvalidData, message));
    }

    let artist_yaml_path = pack_yaml_dir.join("artist.yaml");
    if !artist_yaml_path.is_file() {
        return Err(io::Error::new(
            io::ErrorKind::NotFound,
            format!(
                "artist.yaml not found at {} (required sibling of pack.yaml)",
                artist_yaml_path.display()
            ),
        ));
    }

    for artwork in &pack.artworks {
        verify_image(
            &artwork.original,
            &format!("artworks[{}].original", artwork.id),
            pack_yaml_dir,
        )?;
        for (j, variant) in artwork.variants.iter().enumerate() {
            verify_image(
                variant,
                &format!("artworks[{}.variants[{j}]]", artwork.id),
                pack_yaml_dir,
            )?;
        }
    }

    let output_path = match output {
        Some(p) => p.to_path_buf(),
        None => {
            std::env::current_dir()?.join(format!("{}-{}.pak.gz", pack.pack.id, pack.pack.version))
        }
    };

    let file = fs::File::create(&output_path)?;
    let gz = GzEncoder::new(file, Compression::default());
    let mut tar = Builder::new(gz);

    append_file_bytes(&mut tar, "pack.yaml", &raw_bytes)?;
    append_file_bytes(&mut tar, "artist.yaml", &fs::read(&artist_yaml_path)?)?;

    for artwork in &pack.artworks {
        let ext = extension_of(&artwork.original.file);
        let original_bytes = fs::read(pack_yaml_dir.join(&artwork.original.file))?;
        append_file_bytes(
            &mut tar,
            &format!("artworks/{}.{ext}", artwork.id),
            &original_bytes,
        )?;

        for variant in &artwork.variants {
            let variant_bytes = fs::read(pack_yaml_dir.join(&variant.file))?;
            let name = format!(
                "artworks/{}-{}x{}.{ext}",
                artwork.id, variant.width, variant.height
            );
            append_file_bytes(&mut tar, &name, &variant_bytes)?;
        }

        if let Some(manifest_rel) = &artwork.provenance.manifest_file {
            let manifest_path = pack_yaml_dir.join(manifest_rel);
            if manifest_path.is_file() {
                let bytes = fs::read(&manifest_path)?;
                append_file_bytes(&mut tar, &format!("c2pa/{}.c2pa", artwork.id), &bytes)?;
            }
        }
    }

    tar.finish()?;
    let gz = tar.into_inner()?;
    gz.finish()?;

    let byte_size = fs::metadata(&output_path)?.len();
    let sha256 = hash::sha256_hex_of_file(&output_path)?;

    Ok(BuiltPak {
        output_path,
        byte_size,
        sha256,
    })
}

/// Install a previously-built `.pak.gz` into a `Cache`: extract to staging,
/// verify every extracted artwork file's SHA-256 against the manifest, then
/// atomically activate. Any hash mismatch leaves the staging directory in
/// place (so a re-attempt is possible) and refuses to call `activate` — the
/// pack is never partially installed.
pub fn install_pak(archive_path: &Path, cache: &Cache) -> Result<PathBuf, String> {
    let archive_bytes =
        fs::read(archive_path).map_err(|e| format!("reading {}: {e}", archive_path.display()))?;

    let extract_dir =
        tempfile::tempdir().map_err(|e| format!("creating extraction tempdir: {e}"))?;
    let extract_root = extract_dir.path().to_path_buf();

    let cursor = std::io::Cursor::new(archive_bytes);
    let gz = flate2::read::GzDecoder::new(cursor);
    let mut archive = tar::Archive::new(gz);
    archive
        .unpack(&extract_root)
        .map_err(|e| format!("extracting archive: {e}"))?;

    let pack_yaml_path = extract_root.join("pack.yaml");
    let pack_yaml_text = fs::read_to_string(&pack_yaml_path)
        .map_err(|e| format!("reading extracted pack.yaml: {e}"))?;
    let pack = Pack::from_yaml_str(&pack_yaml_text)
        .map_err(|e| format!("parsing extracted pack.yaml: {e}"))?;

    let staging = cache
        .staging_dir(&pack.pack.id)
        .map_err(|e| format!("creating staging dir for {}: {e}", pack.pack.id))?;

    copy_file_to_staging(&extract_root.join("pack.yaml"), &staging.join("pack.yaml"))?;
    copy_file_to_staging(
        &extract_root.join("artist.yaml"),
        &staging.join("artist.yaml"),
    )?;

    for artwork in &pack.artworks {
        let ext = extension_of(&artwork.original.file);
        let original_dest_name = format!("artworks/{}.{ext}", artwork.id);
        copy_file_to_staging(
            &extract_root.join(&original_dest_name),
            &staging.join(&original_dest_name),
        )?;
        for variant in &artwork.variants {
            let variant_name = format!(
                "artworks/{}-{}x{}.{ext}",
                artwork.id, variant.width, variant.height
            );
            copy_file_to_staging(
                &extract_root.join(&variant_name),
                &staging.join(&variant_name),
            )?;
        }
    }

    for artwork in &pack.artworks {
        let ext = extension_of(&artwork.original.file);
        let original_dest_name = format!("artworks/{}.{ext}", artwork.id);
        let installed = staging.join(&original_dest_name);
        verify_against_manifest(
            &installed,
            &artwork.original.sha256,
            &format!("{} original", artwork.id),
        )?;

        for variant in &artwork.variants {
            let variant_name = format!(
                "artworks/{}-{}x{}.{ext}",
                artwork.id, variant.width, variant.height
            );
            let installed = staging.join(&variant_name);
            verify_against_manifest(
                &installed,
                &variant.sha256,
                &format!("{} variant", artwork.id),
            )?;
        }
    }

    let live = cache
        .activate(&pack.pack.id)
        .map_err(|e| format!("activating {}: {e}", pack.pack.id))?;
    Ok(live)
}

fn verify_image(image: &crate::types::ImageRef, field: &str, base_dir: &Path) -> io::Result<()> {
    let path = base_dir.join(&image.file);
    let actual = hash::sha256_hex_of_file(&path)?;
    if !actual.eq_ignore_ascii_case(&image.sha256) {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            format!(
                "{field} sha256 mismatch for {}: declared {} but file on disk is {}",
                path.display(),
                image.sha256,
                actual,
            ),
        ));
    }
    Ok(())
}

fn verify_against_manifest(path: &Path, expected: &str, label: &str) -> Result<(), String> {
    match hash::verify_file_hash(path, expected) {
        Ok(true) => Ok(()),
        Ok(false) => Err(format!(
            "integrity check failed for {label} at {}: declared sha256 {expected}",
            path.display(),
        )),
        Err(e) => Err(format!("verifying {label} at {}: {e}", path.display())),
    }
}

fn extension_of(file: &str) -> String {
    Path::new(file)
        .extension()
        .and_then(|e| e.to_str())
        .unwrap_or("")
        .to_string()
}

fn append_file_bytes<W: Write>(tar: &mut Builder<W>, name: &str, bytes: &[u8]) -> io::Result<()> {
    let mut header = Header::new_ustar();
    header.set_path(name)?;
    header.set_size(bytes.len() as u64);
    header.set_mode(0o644);
    header.set_entry_type(tar::EntryType::Regular);
    header.set_cksum();
    tar.append(&header, bytes)?;
    Ok(())
}

fn copy_file_to_staging(src: &Path, dest: &Path) -> Result<(), String> {
    if let Some(parent) = dest.parent() {
        fs::create_dir_all(parent).map_err(|e| format!("creating {}: {e}", parent.display()))?;
    }
    fs::copy(src, dest)
        .map_err(|e| format!("copying {} -> {}: {e}", src.display(), dest.display()))?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::cache::Cache;
    use std::io::{Read, Write};

    const HELLO_WORLD_SHA256: &str =
        "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9";

    fn make_image_bytes(tmp: &Path, name: &str, body: &[u8]) -> String {
        let path = tmp.join(name);
        let mut f = fs::File::create(&path).unwrap();
        f.write_all(body).unwrap();
        hash::sha256_hex_of_file(&path).unwrap()
    }

    fn write_minimal_pack(
        dir: &Path,
        original_sha: &str,
        variant_sha: &str,
        original_rel: &str,
        variant_rel: &str,
    ) -> PathBuf {
        let yaml = format!(
            r#"
artistpack: "0.1"
pack:
  id: "org.artistpack.example.minimal"
  title: "Minimal Example Pack"
  version: "1.0.0"
artist:
  id: "example-artist"
  name: "Example Artist"
rights:
  copyright: "Copyright 2026 Example Artist"
  license: "artistpack-display-license-1.0"
artworks:
  - id: "artwork-001"
    title: "Untitled"
    original:
      file: "{original_rel}"
      sha256: "{original_sha}"
      width: 1920
      height: 1080
      mime_type: "image/jpeg"
    variants:
      - file: "{variant_rel}"
        sha256: "{variant_sha}"
        width: 1920
        height: 1080
    attribution:
      display_name: "Example Artist"
    provenance:
      c2pa: false
"#,
        );
        let pack_yaml = dir.join("pack.yaml");
        fs::write(&pack_yaml, yaml).unwrap();

        let artist = dir.join("artist.yaml");
        fs::write(
            &artist,
            "artistpack: \"0.1\"\nartist:\n  id: \"example-artist\"\n  name: \"Example Artist\"\n",
        )
        .unwrap();
        pack_yaml
    }

    #[test]
    fn build_round_trips_and_contains_expected_layout() {
        let tmp = tempfile::tempdir().unwrap();
        let src_dir = tmp.path().join("src");
        fs::create_dir(&src_dir).unwrap();

        let original_sha = make_image_bytes(&src_dir, "art.jpg", b"original-bytes");
        let variant_sha = make_image_bytes(&src_dir, "art-1920.jpg", b"variant-bytes");
        let pack_yaml = write_minimal_pack(
            &src_dir,
            &original_sha,
            &variant_sha,
            "art.jpg",
            "art-1920.jpg",
        );

        let out_dir = tmp.path().join("out");
        fs::create_dir(&out_dir).unwrap();
        let out_path = out_dir.join("test.pak.gz");

        let built = build_pak(&pack_yaml, Some(&out_path)).unwrap();
        assert_eq!(built.output_path, out_path);
        assert!(built.byte_size > 0);
        assert_eq!(built.sha256.len(), 64);

        let file = fs::File::open(&out_path).unwrap();
        let gz = flate2::read::GzDecoder::new(file);
        let mut archive = tar::Archive::new(gz);
        let entries: Vec<(String, Vec<u8>)> = archive
            .entries()
            .unwrap()
            .map(|e| {
                let mut e = e.unwrap();
                let name = e.path().unwrap().to_string_lossy().to_string();
                let mut buf = Vec::new();
                e.read_to_end(&mut buf).unwrap();
                (name, buf)
            })
            .collect();
        let mut names: Vec<String> = entries.iter().map(|(n, _)| n.clone()).collect();
        names.sort();

        assert_eq!(
            names,
            vec![
                "artist.yaml".to_string(),
                "artworks/artwork-001-1920x1080.jpg".to_string(),
                "artworks/artwork-001.jpg".to_string(),
                "pack.yaml".to_string(),
            ],
        );

        let original = entries
            .iter()
            .find(|(n, _)| n == "artworks/artwork-001.jpg")
            .unwrap();
        assert_eq!(original.1, b"original-bytes");
    }

    #[test]
    fn build_uses_default_output_name_when_no_output_given() {
        let tmp = tempfile::tempdir().unwrap();
        let src_dir = tmp.path().join("src");
        fs::create_dir(&src_dir).unwrap();

        let sha = make_image_bytes(&src_dir, "art.jpg", b"data");
        let pack_yaml = write_minimal_pack(&src_dir, &sha, &sha, "art.jpg", "art.jpg");

        let prev = std::env::current_dir().unwrap();
        std::env::set_current_dir(tmp.path()).unwrap();
        let built = build_pak(&pack_yaml, None);
        std::env::set_current_dir(&prev).unwrap();
        let built = built.unwrap();

        assert_eq!(
            built.output_path.file_name().unwrap().to_str().unwrap(),
            "org.artistpack.example.minimal-1.0.0.pak.gz",
        );
        let expected = tmp
            .path()
            .join("org.artistpack.example.minimal-1.0.0.pak.gz");
        assert!(
            expected.exists(),
            "default output {} should exist",
            expected.display()
        );
        assert_eq!(built.output_path, expected);
    }

    #[test]
    fn build_hard_fails_on_tampered_artwork_file() {
        let tmp = tempfile::tempdir().unwrap();
        let src_dir = tmp.path().join("src");
        fs::create_dir(&src_dir).unwrap();

        let variant_sha = make_image_bytes(&src_dir, "art-1920.jpg", b"variant-original");
        let pack_yaml = write_minimal_pack(
            &src_dir,
            HELLO_WORLD_SHA256,
            &variant_sha,
            "art.jpg",
            "art-1920.jpg",
        );
        fs::write(src_dir.join("art.jpg"), b"tampered").unwrap();

        let out_dir = tmp.path().join("out");
        fs::create_dir(&out_dir).unwrap();
        let out_path = out_dir.join("test.pak.gz");

        let result = build_pak(&pack_yaml, Some(&out_path));
        assert!(result.is_err());
        let msg = format!("{}", result.err().unwrap());
        assert!(msg.contains("sha256 mismatch"));
        assert!(
            !out_path.exists(),
            "no partial archive should be produced on integrity failure"
        );
    }

    #[test]
    fn build_hard_fails_on_missing_artist_yaml() {
        let tmp = tempfile::tempdir().unwrap();
        let src_dir = tmp.path().join("src");
        fs::create_dir(&src_dir).unwrap();

        let sha = make_image_bytes(&src_dir, "art.jpg", b"data");
        let pack_yaml = write_minimal_pack(&src_dir, &sha, &sha, "art.jpg", "art.jpg");
        fs::remove_file(src_dir.join("artist.yaml")).unwrap();

        let out_dir = tmp.path().join("out");
        fs::create_dir(&out_dir).unwrap();
        let out_path = out_dir.join("test.pak.gz");

        let result = build_pak(&pack_yaml, Some(&out_path));
        assert!(result.is_err());
        let msg = format!("{}", result.err().unwrap());
        assert!(msg.contains("artist.yaml"));
        assert!(!out_path.exists());
    }

    #[test]
    fn build_includes_c2pa_when_manifest_file_present_and_skips_when_absent() {
        let tmp = tempfile::tempdir().unwrap();
        let src_dir = tmp.path().join("src");
        fs::create_dir(&src_dir).unwrap();

        let original_sha = make_image_bytes(&src_dir, "art.jpg", b"original");
        let variant_sha = make_image_bytes(&src_dir, "art-1920.jpg", b"variant");
        let c2pa_sha = make_image_bytes(&src_dir, "art.c2pa", b"c2pa-bytes");

        let yaml = format!(
            r#"
artistpack: "0.1"
pack:
  id: "org.artistpack.example.c2pa"
  title: "C2PA Pack"
  version: "1.0.0"
artist:
  id: "example-artist"
  name: "Example Artist"
rights:
  copyright: "Copyright 2026 Example Artist"
  license: "artistpack-display-license-1.0"
artworks:
  - id: "artwork-001"
    title: "Untitled"
    original:
      file: "art.jpg"
      sha256: "{original_sha}"
      width: 1920
      height: 1080
      mime_type: "image/jpeg"
    variants:
      - file: "art-1920.jpg"
        sha256: "{variant_sha}"
        width: 1920
        height: 1080
    attribution:
      display_name: "Example Artist"
    provenance:
      c2pa: true
      manifest_file: "art.c2pa"
"#,
        );
        let pack_yaml = src_dir.join("pack.yaml");
        fs::write(&pack_yaml, yaml).unwrap();
        fs::write(
            src_dir.join("artist.yaml"),
            "artistpack: \"0.1\"\nartist:\n  id: \"example-artist\"\n  name: \"Example Artist\"\n",
        )
        .unwrap();

        let out_dir = tmp.path().join("out");
        fs::create_dir(&out_dir).unwrap();
        let out_path = out_dir.join("with.pak.gz");
        let built = build_pak(&pack_yaml, Some(&out_path)).unwrap();
        assert!(built.byte_size > 0);

        let file = fs::File::open(&out_path).unwrap();
        let gz = flate2::read::GzDecoder::new(file);
        let mut archive = tar::Archive::new(gz);
        let mut names: Vec<String> = archive
            .entries()
            .unwrap()
            .map(|e| e.unwrap().path().unwrap().to_string_lossy().to_string())
            .collect();
        names.sort();
        assert!(names.iter().any(|n| n == "c2pa/artwork-001.c2pa"));

        let other_c2pa = c2pa_sha.clone();
        assert!(!other_c2pa.is_empty());

        fs::remove_file(src_dir.join("art.c2pa")).unwrap();
        let out_path2 = out_dir.join("without.pak.gz");
        build_pak(&pack_yaml, Some(&out_path2)).unwrap();
        let file2 = fs::File::open(&out_path2).unwrap();
        let gz2 = flate2::read::GzDecoder::new(file2);
        let mut archive2 = tar::Archive::new(gz2);
        let names2: Vec<String> = archive2
            .entries()
            .unwrap()
            .map(|e| e.unwrap().path().unwrap().to_string_lossy().to_string())
            .collect();
        assert!(!names2.iter().any(|n| n == "c2pa/artwork-001.c2pa"));
    }

    #[test]
    fn install_round_trip_build_then_install_activates_live() {
        let tmp = tempfile::tempdir().unwrap();
        let src_dir = tmp.path().join("src");
        fs::create_dir(&src_dir).unwrap();
        let original_sha = make_image_bytes(&src_dir, "art.jpg", b"original-body");
        let variant_sha = make_image_bytes(&src_dir, "art-1920.jpg", b"variant-body");
        let pack_yaml = write_minimal_pack(
            &src_dir,
            &original_sha,
            &variant_sha,
            "art.jpg",
            "art-1920.jpg",
        );

        let out_dir = tmp.path().join("out");
        fs::create_dir(&out_dir).unwrap();
        let out_path = out_dir.join("rt.pak.gz");
        build_pak(&pack_yaml, Some(&out_path)).unwrap();

        let cache_tmp = tempfile::tempdir().unwrap();
        let cache = Cache::new(cache_tmp.path());
        let live = install_pak(&out_path, &cache).unwrap();
        assert!(live.exists());

        let live_path = live;
        assert_eq!(
            fs::read(live_path.join("artworks/artwork-001.jpg")).unwrap(),
            b"original-body",
        );
        assert_eq!(
            fs::read(live_path.join("artworks/artwork-001-1920x1080.jpg")).unwrap(),
            b"variant-body",
        );
        assert!(live_path.join("pack.yaml").exists());
        assert!(live_path.join("artist.yaml").exists());
    }

    #[test]
    fn install_fails_cleanly_when_archive_contents_have_been_tampered() {
        let tmp = tempfile::tempdir().unwrap();
        let src_dir = tmp.path().join("src");
        fs::create_dir(&src_dir).unwrap();
        let original_sha = make_image_bytes(&src_dir, "art.jpg", b"original-body");
        let variant_sha = make_image_bytes(&src_dir, "art-1920.jpg", b"variant-body");
        let pack_yaml = write_minimal_pack(
            &src_dir,
            &original_sha,
            &variant_sha,
            "art.jpg",
            "art-1920.jpg",
        );

        let out_dir = tmp.path().join("out");
        fs::create_dir(&out_dir).unwrap();
        let out_path = out_dir.join("rt.pak.gz");
        build_pak(&pack_yaml, Some(&out_path)).unwrap();

        let cache_tmp = tempfile::tempdir().unwrap();
        let cache = Cache::new(cache_tmp.path());

        let file = fs::File::open(&out_path).unwrap();
        let gz = flate2::read::GzDecoder::new(file);
        let mut archive = tar::Archive::new(gz);
        let mut rebuilder = tar::Builder::new(Vec::new());
        let mut pack_yaml_bytes: Option<Vec<u8>> = None;
        for entry in archive.entries().unwrap() {
            let mut e = entry.unwrap();
            let path = e.path().unwrap().to_path_buf();
            let name = path.to_string_lossy().to_string();
            let mut buf = Vec::new();
            e.read_to_end(&mut buf).unwrap();
            if name == "artworks/artwork-001.jpg" {
                buf = b"tampered-body".to_vec();
            }
            if name == "pack.yaml" {
                pack_yaml_bytes = Some(buf.clone());
            }
            let mut header = tar::Header::new_ustar();
            header.set_size(buf.len() as u64);
            header.set_mode(0o644);
            header.set_entry_type(tar::EntryType::Regular);
            header.set_path(&path).unwrap();
            header.set_cksum();
            rebuilder.append(&header, buf.as_slice()).unwrap();
        }
        let new_bytes = rebuilder.into_inner().unwrap();
        let mut gz_out = GzEncoder::new(Vec::new(), Compression::default());
        gz_out.write_all(&new_bytes).unwrap();
        let gz_bytes = gz_out.finish().unwrap();
        fs::write(&out_path, gz_bytes).unwrap();
        drop(pack_yaml_bytes);

        let result = install_pak(&out_path, &cache);
        assert!(
            result.is_err(),
            "install must fail when archive contents don't match declared hashes"
        );

        let live = cache_tmp.path().join("live");
        assert!(
            !live.exists(),
            "no live/ directory must appear when install fails (no partial activation)",
        );
    }
}

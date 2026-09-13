use crate::types::Pack;
use std::fmt;

#[derive(Debug, PartialEq, Eq)]
pub struct ValidationError {
    pub path: String,
    pub message: String,
}

impl fmt::Display for ValidationError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}: {}", self.path, self.message)
    }
}

fn err(path: impl Into<String>, message: impl Into<String>) -> ValidationError {
    ValidationError { path: path.into(), message: message.into() }
}

fn is_pack_id(s: &str) -> bool {
    let mut chars = s.chars();
    let Some(first) = chars.next() else { return false };
    if !(first.is_ascii_lowercase() || first.is_ascii_digit() || first == '.') {
        return false;
    }
    chars.all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '.' || c == '-')
}

fn is_slug_id(s: &str) -> bool {
    let mut chars = s.chars();
    let Some(first) = chars.next() else { return false };
    if !(first.is_ascii_lowercase() || first.is_ascii_digit()) {
        return false;
    }
    chars.all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '-')
}

fn is_sha256(s: &str) -> bool {
    s.len() == 64 && s.chars().all(|c| c.is_ascii_hexdigit() && !c.is_ascii_uppercase())
}

fn is_semver(s: &str) -> bool {
    let parts: Vec<&str> = s.split('.').collect();
    parts.len() == 3 && parts.iter().all(|p| !p.is_empty() && p.chars().all(|c| c.is_ascii_digit()))
}

fn validate_image_ref(prefix: &str, image: &crate::types::ImageRef, errors: &mut Vec<ValidationError>) {
    if !is_sha256(&image.sha256) {
        errors.push(err(format!("{prefix}.sha256"), "must be 64 lowercase hex characters"));
    }
    if image.width == 0 {
        errors.push(err(format!("{prefix}.width"), "must be greater than 0"));
    }
    if image.height == 0 {
        errors.push(err(format!("{prefix}.height"), "must be greater than 0"));
    }
}

pub fn validate_pack(pack: &Pack) -> Vec<ValidationError> {
    let mut errors = Vec::new();

    if !is_pack_id(&pack.pack.id) {
        errors.push(err("pack.id", "must match ^[a-z0-9.][a-z0-9.-]*$"));
    }
    if !is_semver(&pack.pack.version) {
        errors.push(err("pack.version", "must match ^\\d+\\.\\d+\\.\\d+$"));
    }
    if !is_slug_id(&pack.artist.id) {
        errors.push(err("artist.id", "must match ^[a-z0-9][a-z0-9-]*$"));
    }

    if pack.artworks.is_empty() {
        errors.push(err("artworks", "must contain at least one artwork"));
    }

    for (i, artwork) in pack.artworks.iter().enumerate() {
        let base = format!("artworks[{i}]");

        if !is_slug_id(&artwork.id) {
            errors.push(err(format!("{base}.id"), "must match ^[a-z0-9][a-z0-9-]*$"));
        }

        validate_image_ref(&format!("{base}.original"), &artwork.original, &mut errors);

        if artwork.variants.is_empty() {
            errors.push(err(format!("{base}.variants"), "must contain at least one variant"));
        }
        for (j, variant) in artwork.variants.iter().enumerate() {
            validate_image_ref(&format!("{base}.variants[{j}]"), variant, &mut errors);
        }

        if artwork.provenance.c2pa && artwork.provenance.manifest_file.is_none() {
            errors.push(err(
                format!("{base}.provenance.manifest_file"),
                "required when provenance.c2pa is true",
            ));
        }

        if let Some(display) = &artwork.display {
            if let Some(fp) = &display.focal_point {
                if !(0.0..=1.0).contains(&fp.x) {
                    errors.push(err(format!("{base}.display.focal_point.x"), "must be between 0 and 1"));
                }
                if !(0.0..=1.0).contains(&fp.y) {
                    errors.push(err(format!("{base}.display.focal_point.y"), "must be between 0 and 1"));
                }
            }
        }
    }

    errors
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::types::Pack;

    fn fixture(rel: &str) -> String {
        let path = format!("{}/../examples/{}", env!("CARGO_MANIFEST_DIR"), rel);
        std::fs::read_to_string(&path).unwrap()
    }

    #[test]
    fn valid_minimal_pack_has_no_errors() {
        let pack = Pack::from_yaml_str(&fixture("minimal/pack.yaml")).unwrap();
        assert_eq!(validate_pack(&pack), Vec::new());
    }

    #[test]
    fn valid_full_pack_has_no_errors() {
        let pack = Pack::from_yaml_str(&fixture("full/pack.yaml")).unwrap();
        assert_eq!(validate_pack(&pack), Vec::new());
    }

    #[test]
    fn c2pa_true_without_manifest_file_is_rejected() {
        let yaml = r#"
artistpack: "0.1"
pack:
  id: "org.artistpack.example.broken"
  title: "Broken"
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
      file: "images/artwork-001.jpg"
      sha256: "a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1"
      width: 1920
      height: 1080
    variants:
      - file: "images/artwork-001.jpg"
        sha256: "a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1"
        width: 1920
        height: 1080
    attribution:
      display_name: "Example Artist"
    provenance:
      c2pa: true
"#;
        let pack = Pack::from_yaml_str(yaml).unwrap();
        let errors = validate_pack(&pack);
        assert_eq!(errors.len(), 1);
        assert!(errors[0].path.contains("provenance.manifest_file"));
    }

    #[test]
    fn bad_sha256_is_rejected() {
        let mut pack = Pack::from_yaml_str(&fixture("minimal/pack.yaml")).unwrap();
        pack.artworks[0].original.sha256 = "not-a-valid-hash".to_string();
        let errors = validate_pack(&pack);
        assert!(errors.iter().any(|e| e.path.contains("original.sha256")));
    }

    #[test]
    fn empty_variants_is_rejected() {
        let mut pack = Pack::from_yaml_str(&fixture("minimal/pack.yaml")).unwrap();
        pack.artworks[0].variants.clear();
        let errors = validate_pack(&pack);
        assert!(errors.iter().any(|e| e.path.contains("variants")));
    }

    #[test]
    fn empty_artworks_is_rejected() {
        let mut pack = Pack::from_yaml_str(&fixture("minimal/pack.yaml")).unwrap();
        pack.artworks.clear();
        let errors = validate_pack(&pack);
        assert!(errors.iter().any(|e| e.path == "artworks"));
    }

    #[test]
    fn bad_pack_id_is_rejected() {
        let mut pack = Pack::from_yaml_str(&fixture("minimal/pack.yaml")).unwrap();
        pack.pack.id = "Not A Valid Id!".to_string();
        let errors = validate_pack(&pack);
        assert!(errors.iter().any(|e| e.path == "pack.id"));
    }

    #[test]
    fn bad_version_is_rejected() {
        let mut pack = Pack::from_yaml_str(&fixture("minimal/pack.yaml")).unwrap();
        pack.pack.version = "v1".to_string();
        let errors = validate_pack(&pack);
        assert!(errors.iter().any(|e| e.path == "pack.version"));
    }

    #[test]
    fn out_of_range_focal_point_is_rejected() {
        use crate::types::FocalPoint;
        let mut pack = Pack::from_yaml_str(&fixture("full/pack.yaml")).unwrap();
        pack.artworks[0].display.as_mut().unwrap().focal_point = Some(FocalPoint { x: 1.5, y: 0.5 });
        let errors = validate_pack(&pack);
        assert!(errors.iter().any(|e| e.path.contains("focal_point")));
    }
}
# ArtistPack Rust SDK (core) + CLI Validator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the core ArtistPack Rust SDK (parse, structural + business-rule
validate, SHA-256 verify, local staging/atomic-activate cache) and a thin CLI
(`artistpack validate <path>`) on top of it, so `artistpack validate
examples/full/pack.yaml` works end to end, per `docs/mvp-plan.md` Tasks 5–6.

**Architecture:** Two-crate Cargo workspace. `sdk/` is the canonical
implementation every future consumer (CLI now, desktop clients later) builds
on — it never shells out, never touches the network, and never assumes
artistpack.org exists (`docs/architecture.md`'s self-hosting requirement).
`cli/` is a thin `clap`-based wrapper that does I/O and formatting only; all
actual logic lives in `sdk/`.

**Tech Stack:** Rust, edition 2021. `serde` + `serde_yaml` for manifest
parsing, `sha2` for hashing, `clap` (derive) for the CLI. No JSON-Schema
runtime validator crate — see Global Constraints below for why.

**Spec:** `spec/artistpack-0.1.md`, `schema/{artist,pack,feed}.schema.json`,
`docs/architecture.md`, `docs/mvp-plan.md`.

## Global Constraints

- **Unknown fields must be silently ignored, never rejected** — spec
  §8/§11 compatibility rule. Never add `#[serde(deny_unknown_fields)]` to
  any manifest type in this plan. A test in Task 2 asserts this directly.
- **`requires:` capability strings are out of scope for this plan.** Parsing
  them into `Vec<String>` is in scope (Task 2); *acting* on an unrecognized
  capability is a client concern for a later plan, not the SDK's parse/
  validate layer.
- **C2PA signature verification is explicitly out of scope for this plan.**
  `provenance.c2pa`/`provenance.manifest_file` are parsed and structurally
  validated (Task 3's conditional-requirement check), but no cryptographic
  verification of the `.c2pa` file's contents happens here — that is a
  separate, later plan once the signing-key infrastructure
  (`docs/security-model.md`) exists.
- **No network I/O anywhere in this plan.** Fetching a manifest or asset
  over HTTP is a later plan; everything here operates on local file paths.
- Every `id` matches `^[a-z0-9][a-z0-9-]*$` except `pack.id`/`feed.id`,
  which allow a leading dot-segment: `^[a-z0-9.][a-z0-9.-]*$` (matches
  `schema/pack.schema.json` / `schema/feed.schema.json` exactly).
- `sha256` fields match `^[a-f0-9]{64}$`. `pack.version` matches
  `^\d+\.\d+\.\d+$`.

## File Structure

```text
Cargo.toml                    # workspace root, members = ["sdk", "cli"]
sdk/Cargo.toml
sdk/src/lib.rs                # re-exports: types::*, validate::*, hash::*, cache::*
sdk/src/types.rs              # Pack, Artist, Feed manifest structs (serde)
sdk/src/validate.rs           # business-rule validation beyond what serde's types already enforce
sdk/src/hash.rs               # SHA-256 file verification
sdk/src/cache.rs              # local staging-dir -> atomic-activate cache
sdk/tests/fixtures.rs         # integration tests against ../examples/**/*.yaml
cli/Cargo.toml
cli/src/main.rs               # clap CLI, `artistpack validate <path>`
cli/tests/validate_cmd.rs     # integration test invoking the built binary
```

`sdk/src/types.rs` owns every struct; `validate.rs`, `hash.rs`, `cache.rs`
each own one responsibility and only depend on `types.rs`, never on each
other. `cli/` depends on `sdk` as a path dependency and contains no manifest
parsing or validation logic of its own.

---

### Task 1: Cargo workspace skeleton

**Files:**
- Create: `Cargo.toml` (workspace root)
- Create: `sdk/Cargo.toml`
- Create: `sdk/src/lib.rs`

**Interfaces:**
- Produces: `artistpack_sdk::FORMAT_VERSION: &str = "0.1"` — every later task
  and the CLI reference this constant rather than hardcoding the string.

- [ ] **Step 1: Write the workspace root `Cargo.toml`**

```toml
[workspace]
resolver = "2"
members = ["sdk", "cli"]
```

- [ ] **Step 2: Write `sdk/Cargo.toml`**

```toml
[package]
name = "artistpack-sdk"
version = "0.1.0"
edition = "2021"

[dependencies]
serde = { version = "1", features = ["derive"] }
serde_yaml = "0.9"
sha2 = "0.10"

[dev-dependencies]
tempfile = "3"
```

- [ ] **Step 3: Write `sdk/src/lib.rs` with the failing test**

```rust
pub const FORMAT_VERSION: &str = "0.1";

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn format_version_matches_spec() {
        assert_eq!(FORMAT_VERSION, "0.1");
    }
}
```

This is not a placeholder test — it pins the one value every manifest
parser in Task 2 checks against, so a future accidental edit to this
constant fails loudly here first.

- [ ] **Step 4: Run the test**

Run: `cargo test -p artistpack-sdk` from the repo root.
Expected: `test tests::format_version_matches_spec ... ok`, 1 passed.

- [ ] **Step 5: Commit**

```bash
git add Cargo.toml sdk/Cargo.toml sdk/src/lib.rs
git commit -m "feat(sdk): workspace skeleton with FORMAT_VERSION constant"
```

---

### Task 2: Manifest types + YAML parsing (`pack.yaml`, `artist.yaml`, `feed.yaml`)

**Files:**
- Create: `sdk/src/types.rs`
- Modify: `sdk/src/lib.rs` (add `pub mod types;` and re-export)
- Create: `sdk/tests/fixtures.rs`

**Interfaces:**
- Consumes: nothing beyond `serde`/`serde_yaml`.
- Produces (used by Task 3, Task 4, and the CLI):
  - `types::Pack { artistpack: String, requires: Option<Vec<String>>, pack: PackMeta, artist: PackArtist, rights: Rights, artworks: Vec<Artwork>, compatibility: Option<Compatibility> }`
  - `types::Artist { artistpack: String, artist: ArtistProfile }`
  - `types::Feed { artistpack_feed: String, feed: FeedMeta, packs: Vec<FeedPackRef> }`
  - `fn types::Pack::from_yaml_str(s: &str) -> Result<Pack, serde_yaml::Error>`
  - `fn types::Artist::from_yaml_str(s: &str) -> Result<Artist, serde_yaml::Error>`
  - `fn types::Feed::from_yaml_str(s: &str) -> Result<Feed, serde_yaml::Error>`

- [ ] **Step 1: Write the failing fixture-parsing test**

Create `sdk/tests/fixtures.rs`:

```rust
use artistpack_sdk::types::{Artist, Feed, Pack};

fn fixture(rel: &str) -> String {
    let path = format!("{}/../examples/{}", env!("CARGO_MANIFEST_DIR"), rel);
    std::fs::read_to_string(&path).unwrap_or_else(|e| panic!("reading {path}: {e}"))
}

#[test]
fn parses_minimal_pack() {
    let pack = Pack::from_yaml_str(&fixture("minimal/pack.yaml")).unwrap();
    assert_eq!(pack.artistpack, "0.1");
    assert_eq!(pack.pack.id, "org.artistpack.example.minimal");
    assert_eq!(pack.artworks.len(), 1);
    assert_eq!(pack.artworks[0].id, "artwork-001");
    assert_eq!(pack.artworks[0].provenance.c2pa, false);
    assert!(pack.artworks[0].provenance.manifest_file.is_none());
}

#[test]
fn parses_full_pack() {
    let pack = Pack::from_yaml_str(&fixture("full/pack.yaml")).unwrap();
    assert_eq!(pack.pack.id, "org.artistpack.novaashworth.worlds");
    assert_eq!(pack.artworks[0].variants.len(), 2);
    assert_eq!(pack.artworks[0].attribution.display_name, "Nova Ashworth");
    assert_eq!(pack.artworks[0].provenance.c2pa, true);
    assert_eq!(
        pack.artworks[0].provenance.manifest_file.as_deref(),
        Some("provenance/city-001.c2pa")
    );
    let compat = pack.compatibility.expect("compatibility block present");
    assert_eq!(compat.wallpaper, Some(true));
}

#[test]
fn parses_full_artist() {
    let artist = Artist::from_yaml_str(&fixture("full/artist.yaml")).unwrap();
    assert_eq!(artist.artist.id, "nova-ashworth");
    assert_eq!(artist.artist.packs.as_ref().unwrap().len(), 1);
}

#[test]
fn parses_full_feed() {
    let feed = Feed::from_yaml_str(&fixture("full/feed.yaml")).unwrap();
    assert_eq!(feed.artistpack_feed, "0.1");
    assert_eq!(feed.packs.len(), 1);
    assert!(feed.packs[0].url.contains("nova-ashworth"));
}

/// Compatibility rule (spec section 8/11): an unrecognized top-level field
/// must be ignored, never cause a parse failure. This test exists so nobody
/// "helpfully" adds #[serde(deny_unknown_fields)] to Pack later.
#[test]
fn unknown_top_level_field_is_ignored_not_rejected() {
    let mut yaml = fixture("minimal/pack.yaml");
    yaml.push_str("\nsome_future_field: \"a client from 2030 invented this\"\n");
    let pack = Pack::from_yaml_str(&yaml);
    assert!(pack.is_ok(), "unknown field must not break parsing: {pack:?}");
}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cargo test -p artistpack-sdk --test fixtures`
Expected: compile error — `artistpack_sdk::types` doesn't exist yet.

- [ ] **Step 3: Write `sdk/src/types.rs`**

```rust
use serde::Deserialize;

#[derive(Debug, Deserialize)]
pub struct Pack {
    pub artistpack: String,
    #[serde(default)]
    pub requires: Option<Vec<String>>,
    pub pack: PackMeta,
    pub artist: PackArtist,
    pub rights: Rights,
    pub artworks: Vec<Artwork>,
    #[serde(default)]
    pub compatibility: Option<Compatibility>,
}

impl Pack {
    pub fn from_yaml_str(s: &str) -> Result<Self, serde_yaml::Error> {
        serde_yaml::from_str(s)
    }
}

#[derive(Debug, Deserialize)]
pub struct PackMeta {
    pub id: String,
    pub title: String,
    pub version: String,
    #[serde(default)]
    pub description: Option<String>,
    #[serde(default)]
    pub created: Option<String>,
    #[serde(default)]
    pub updated: Option<String>,
}

#[derive(Debug, Deserialize)]
pub struct PackArtist {
    pub id: String,
    pub name: String,
    #[serde(default)]
    pub bio: Option<String>,
    #[serde(default)]
    pub website: Option<String>,
    #[serde(default)]
    pub patreon: Option<String>,
    #[serde(default)]
    pub support_url: Option<String>,
}

#[derive(Debug, Deserialize)]
pub struct Rights {
    pub copyright: String,
    pub license: String,
    #[serde(default = "default_true")]
    pub attribution_required: bool,
}

fn default_true() -> bool {
    true
}

#[derive(Debug, Deserialize)]
pub struct ImageRef {
    pub file: String,
    pub sha256: String,
    pub width: u32,
    pub height: u32,
    #[serde(default)]
    pub mime_type: Option<String>,
}

#[derive(Debug, Deserialize)]
pub struct Attribution {
    pub display_name: String,
    #[serde(default)]
    pub url: Option<String>,
}

#[derive(Debug, Deserialize)]
pub struct Provenance {
    pub c2pa: bool,
    #[serde(default)]
    pub manifest_file: Option<String>,
}

#[derive(Debug, Deserialize)]
pub struct FocalPoint {
    pub x: f64,
    pub y: f64,
}

#[derive(Debug, Deserialize)]
pub struct Display {
    #[serde(default)]
    pub crop_mode: Option<String>,
    #[serde(default)]
    pub focal_point: Option<FocalPoint>,
    #[serde(default)]
    pub allow_crop: Option<bool>,
    #[serde(default)]
    pub allow_scale: Option<bool>,
}

#[derive(Debug, Deserialize)]
pub struct Accessibility {
    #[serde(default)]
    pub alt_text: Option<String>,
}

#[derive(Debug, Deserialize)]
pub struct Creation {
    #[serde(default)]
    pub artist_declares_human_created: Option<bool>,
}

#[derive(Debug, Deserialize)]
pub struct Artwork {
    pub id: String,
    pub title: String,
    #[serde(default)]
    pub description: Option<String>,
    pub original: ImageRef,
    pub variants: Vec<ImageRef>,
    #[serde(default)]
    pub tags: Option<Vec<String>>,
    #[serde(default)]
    pub rights: Option<Rights>,
    pub attribution: Attribution,
    pub provenance: Provenance,
    #[serde(default)]
    pub display: Option<Display>,
    #[serde(default)]
    pub accessibility: Option<Accessibility>,
    #[serde(default)]
    pub creation: Option<Creation>,
}

#[derive(Debug, Deserialize)]
pub struct Compatibility {
    #[serde(default)]
    pub wallpaper: Option<bool>,
    #[serde(default)]
    pub lock_screen: Option<bool>,
}

#[derive(Debug, Deserialize)]
pub struct Artist {
    pub artistpack: String,
    pub artist: ArtistProfile,
}

impl Artist {
    pub fn from_yaml_str(s: &str) -> Result<Self, serde_yaml::Error> {
        serde_yaml::from_str(s)
    }
}

#[derive(Debug, Deserialize)]
pub struct ArtistProfile {
    pub id: String,
    pub name: String,
    #[serde(default)]
    pub bio: Option<String>,
    #[serde(default)]
    pub avatar: Option<String>,
    #[serde(default)]
    pub website: Option<String>,
    #[serde(default)]
    pub packs: Option<Vec<String>>,
}

#[derive(Debug, Deserialize)]
pub struct Feed {
    pub artistpack_feed: String,
    pub feed: FeedMeta,
    pub packs: Vec<FeedPackRef>,
}

impl Feed {
    pub fn from_yaml_str(s: &str) -> Result<Self, serde_yaml::Error> {
        serde_yaml::from_str(s)
    }
}

#[derive(Debug, Deserialize)]
pub struct FeedMeta {
    pub id: String,
    pub title: String,
    #[serde(default)]
    pub description: Option<String>,
    pub updated: String,
}

#[derive(Debug, Deserialize)]
pub struct FeedPackRef {
    pub url: String,
}
```

Note: `support`/`socials` (artist.yaml's nested maps) and `patreon`/
`support_url`/`socials` (pack.yaml's artist block) are deliberately omitted
from these structs for now — they're free-form optional metadata with no
validation rules attached to them yet, and adding them is a pure additive
change later. Omitting a field from a struct does not break parsing
(serde ignores it by default, matching the compatibility rule this task's
last test asserts).

- [ ] **Step 4: Wire the module in `sdk/src/lib.rs`**

```rust
pub mod types;

pub const FORMAT_VERSION: &str = "0.1";

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn format_version_matches_spec() {
        assert_eq!(FORMAT_VERSION, "0.1");
    }
}
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cargo test -p artistpack-sdk --test fixtures`
Expected: all 5 tests pass (`parses_minimal_pack`, `parses_full_pack`,
`parses_full_artist`, `parses_full_feed`,
`unknown_top_level_field_is_ignored_not_rejected`).

- [ ] **Step 6: Commit**

```bash
git add sdk/src/types.rs sdk/src/lib.rs sdk/tests/fixtures.rs
git commit -m "feat(sdk): manifest types and YAML parsing for pack/artist/feed"
```

---

### Task 3: Business-rule validation

**Files:**
- Create: `sdk/src/validate.rs`
- Modify: `sdk/src/lib.rs` (add `pub mod validate;`)

**Interfaces:**
- Consumes: `types::Pack`, `types::Artwork`, `types::ImageRef` (Task 2).
- Produces (used by Task 7's CLI):
  - `validate::ValidationError { path: String, message: String }` (implements
    `Display`)
  - `fn validate::validate_pack(pack: &types::Pack) -> Vec<ValidationError>`
    — empty vec means valid.

- [ ] **Step 1: Write the failing test**

Create the test module at the bottom of `sdk/src/validate.rs` (written in
this step even though the file doesn't exist yet — Step 3 adds the
implementation above it):

```rust
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cargo test -p artistpack-sdk --lib validate`
Expected: compile error — `validate_pack`/`ValidationError` don't exist.

- [ ] **Step 3: Write the implementation above the test module**

Prepend this to `sdk/src/validate.rs` (the test module from Step 1 stays
at the bottom of the same file):

```rust
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
```

- [ ] **Step 4: Wire the module in `sdk/src/lib.rs`**

```rust
pub mod types;
pub mod validate;

pub const FORMAT_VERSION: &str = "0.1";

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn format_version_matches_spec() {
        assert_eq!(FORMAT_VERSION, "0.1");
    }
}
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cargo test -p artistpack-sdk --lib validate`
Expected: all 9 tests in `validate::tests` pass.

- [ ] **Step 6: Commit**

```bash
git add sdk/src/validate.rs sdk/src/lib.rs
git commit -m "feat(sdk): business-rule validation beyond structural parsing"
```

---

### Task 4: SHA-256 file verification

**Files:**
- Create: `sdk/src/hash.rs`
- Modify: `sdk/src/lib.rs` (add `pub mod hash;`)

**Interfaces:**
- Consumes: `std::path::Path`.
- Produces (used by Task 6's cache and later network-fetch plans):
  - `fn hash::sha256_hex_of_file(path: &std::path::Path) -> std::io::Result<String>`
  - `fn hash::verify_file_hash(path: &std::path::Path, expected_hex: &str) -> std::io::Result<bool>`

- [ ] **Step 1: Write the failing test**

```rust
#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;

    // sha256("hello world") -- well-known test vector.
    const HELLO_WORLD_SHA256: &str =
        "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde";

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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cargo test -p artistpack-sdk --lib hash`
Expected: compile error — module doesn't exist.

- [ ] **Step 3: Write the implementation above the test module**

Prepend to `sdk/src/hash.rs`:

```rust
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
```

- [ ] **Step 4: Wire the module in `sdk/src/lib.rs`**

```rust
pub mod hash;
pub mod types;
pub mod validate;

pub const FORMAT_VERSION: &str = "0.1";

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn format_version_matches_spec() {
        assert_eq!(FORMAT_VERSION, "0.1");
    }
}
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cargo test -p artistpack-sdk --lib hash`
Expected: all 4 tests in `hash::tests` pass.

- [ ] **Step 6: Commit**

```bash
git add sdk/src/hash.rs sdk/src/lib.rs
git commit -m "feat(sdk): streaming SHA-256 file verification"
```

---

### Task 5: Local staging/atomic-activate cache

**Files:**
- Create: `sdk/src/cache.rs`
- Modify: `sdk/src/lib.rs` (add `pub mod cache;`)

**Interfaces:**
- Consumes: `std::path::{Path, PathBuf}`.
- Produces (used by later network-fetch plans and the desktop client):
  - `struct cache::Cache { base_dir: PathBuf }`
  - `fn cache::Cache::new(base_dir: impl Into<PathBuf>) -> Self`
  - `fn cache::Cache::staging_dir(&self, pack_id: &str) -> std::io::Result<PathBuf>`
    — creates and returns a fresh staging directory for `pack_id`.
  - `fn cache::Cache::activate(&self, pack_id: &str) -> std::io::Result<PathBuf>`
    — atomically renames the staging directory into place as the pack's
    live cache directory, returning its path. Errors if no staging
    directory exists for `pack_id`.

- [ ] **Step 1: Write the failing test**

```rust
#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;

    #[test]
    fn staging_dir_is_created_and_empty() {
        let tmp = tempfile::tempdir().unwrap();
        let cache = Cache::new(tmp.path());
        let staging = cache.staging_dir("org.artistpack.example.minimal").unwrap();
        assert!(staging.exists());
        assert_eq!(fs::read_dir(&staging).unwrap().count(), 0);
    }

    #[test]
    fn activate_moves_staging_to_live_and_content_survives() {
        let tmp = tempfile::tempdir().unwrap();
        let cache = Cache::new(tmp.path());
        let staging = cache.staging_dir("org.artistpack.example.minimal").unwrap();
        fs::write(staging.join("pack.yaml"), b"artistpack: \"0.1\"").unwrap();

        let live = cache.activate("org.artistpack.example.minimal").unwrap();

        assert!(!staging.exists(), "staging dir must not remain after activation");
        assert!(live.exists());
        assert_eq!(
            fs::read_to_string(live.join("pack.yaml")).unwrap(),
            "artistpack: \"0.1\""
        );
    }

    #[test]
    fn activate_without_staging_errors() {
        let tmp = tempfile::tempdir().unwrap();
        let cache = Cache::new(tmp.path());
        let result = cache.activate("never-staged");
        assert!(result.is_err());
    }

    #[test]
    fn reactivating_replaces_previous_live_content() {
        let tmp = tempfile::tempdir().unwrap();
        let cache = Cache::new(tmp.path());

        let staging1 = cache.staging_dir("pack-a").unwrap();
        fs::write(staging1.join("pack.yaml"), b"version: 1").unwrap();
        cache.activate("pack-a").unwrap();

        let staging2 = cache.staging_dir("pack-a").unwrap();
        fs::write(staging2.join("pack.yaml"), b"version: 2").unwrap();
        let live = cache.activate("pack-a").unwrap();

        assert_eq!(fs::read_to_string(live.join("pack.yaml")).unwrap(), "version: 2");
    }
}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cargo test -p artistpack-sdk --lib cache`
Expected: compile error — `Cache` doesn't exist.

- [ ] **Step 3: Write the implementation above the test module**

Prepend to `sdk/src/cache.rs`:

```rust
use std::fs;
use std::io;
use std::path::{Path, PathBuf};

pub struct Cache {
    base_dir: PathBuf,
}

impl Cache {
    pub fn new(base_dir: impl Into<PathBuf>) -> Self {
        Self { base_dir: base_dir.into() }
    }

    fn staging_path(&self, pack_id: &str) -> PathBuf {
        self.base_dir.join("staging").join(pack_id)
    }

    fn live_path(&self, pack_id: &str) -> PathBuf {
        self.base_dir.join("live").join(pack_id)
    }

    /// Creates a fresh, empty staging directory for `pack_id`. Removes any
    /// leftover staging directory from a previous, never-activated attempt
    /// first, so a caller always starts from a clean slate.
    pub fn staging_dir(&self, pack_id: &str) -> io::Result<PathBuf> {
        let path = self.staging_path(pack_id);
        if path.exists() {
            fs::remove_dir_all(&path)?;
        }
        fs::create_dir_all(&path)?;
        Ok(path)
    }

    /// Atomically moves the staging directory for `pack_id` into place as
    /// its live cache directory. A pack is never partially installed: this
    /// is the only path that touches the `live/` tree, and it's a single
    /// rename, not a copy-then-delete.
    pub fn activate(&self, pack_id: &str) -> io::Result<PathBuf> {
        let staging = self.staging_path(pack_id);
        if !staging.exists() {
            return Err(io::Error::new(
                io::ErrorKind::NotFound,
                format!("no staging directory for {pack_id}; call staging_dir first"),
            ));
        }
        let live = self.live_path(pack_id);
        if let Some(parent) = live.parent() {
            fs::create_dir_all(parent)?;
        }
        if live.exists() {
            fs::remove_dir_all(&live)?;
        }
        fs::rename(&staging, &live)?;
        Ok(live)
    }
}
```

Note on the "atomic" claim: `fs::rename` within the same filesystem is
atomic on POSIX systems. `self.base_dir` is expected to be a single
filesystem in practice (a per-user cache directory); crossing filesystems
would make `rename` fail rather than silently fall back to copy, which is
the correct failure mode here (loud, not silent partial-install).

- [ ] **Step 4: Wire the module in `sdk/src/lib.rs`**

```rust
pub mod cache;
pub mod hash;
pub mod types;
pub mod validate;

pub const FORMAT_VERSION: &str = "0.1";

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn format_version_matches_spec() {
        assert_eq!(FORMAT_VERSION, "0.1");
    }
}
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cargo test -p artistpack-sdk --lib cache`
Expected: all 4 tests in `cache::tests` pass.

- [ ] **Step 6: Run the full SDK test suite**

Run: `cargo test -p artistpack-sdk`
Expected: every test across `lib.rs`, `hash.rs`, `validate.rs`, `cache.rs`,
and `tests/fixtures.rs` passes — this is the checkpoint before starting
the CLI crate.

- [ ] **Step 7: Commit**

```bash
git add sdk/src/cache.rs sdk/src/lib.rs
git commit -m "feat(sdk): local staging/atomic-activate cache"
```

---

### Task 6: CLI crate skeleton + `validate` subcommand

**Files:**
- Create: `cli/Cargo.toml`
- Create: `cli/src/main.rs`

**Interfaces:**
- Consumes: `artistpack_sdk::types::Pack`, `artistpack_sdk::validate::validate_pack`
  (Tasks 2–3).
- Produces: the `artistpack` binary, subcommand `validate <path>`. Exit
  code `0` on a valid manifest, `1` on a validation failure or parse error.
  This is not consumed by a later task in this plan, but is the concrete
  deliverable `docs/mvp-plan.md` names: `artistpack validate pack.yaml`
  must work.

- [ ] **Step 1: Write `cli/Cargo.toml`**

```toml
[package]
name = "artistpack-cli"
version = "0.1.0"
edition = "2021"

[[bin]]
name = "artistpack"
path = "src/main.rs"

[dependencies]
artistpack-sdk = { path = "../sdk" }
clap = { version = "4", features = ["derive"] }
serde_yaml = "0.9"
```

- [ ] **Step 2: Write `cli/src/main.rs`**

```rust
use artistpack_sdk::types::Pack;
use artistpack_sdk::validate::validate_pack;
use clap::{Parser, Subcommand};
use std::path::PathBuf;
use std::process::ExitCode;

#[derive(Parser)]
#[command(name = "artistpack")]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Subcommand)]
enum Command {
    /// Validate a pack.yaml manifest against the ArtistPack 0.1 spec.
    Validate { path: PathBuf },
}

fn run_validate(path: &PathBuf) -> Result<(), String> {
    let contents = std::fs::read_to_string(path)
        .map_err(|e| format!("reading {}: {e}", path.display()))?;

    let pack = Pack::from_yaml_str(&contents)
        .map_err(|e| format!("parsing {}: {e}", path.display()))?;

    let errors = validate_pack(&pack);
    if errors.is_empty() {
        println!("OK: {}", path.display());
        Ok(())
    } else {
        eprintln!("FAIL: {}", path.display());
        for error in &errors {
            eprintln!("  - {error}");
        }
        Err(format!("{} validation error(s)", errors.len()))
    }
}

fn main() -> ExitCode {
    let cli = Cli::parse();
    match cli.command {
        Command::Validate { path } => match run_validate(&path) {
            Ok(()) => ExitCode::SUCCESS,
            Err(message) => {
                eprintln!("{message}");
                ExitCode::FAILURE
            }
        },
    }
}
```

This is the first step in this task rather than a separate TDD step
because `main.rs` for a CLI binary is not itself unit-testable in
isolation — Task 7 covers it with a real process-level integration test.

- [ ] **Step 3: Build and manually verify against the real fixtures**

Run: `cargo run -p artistpack-cli -- validate examples/minimal/pack.yaml`
Expected: prints `OK: examples/minimal/pack.yaml`, exits 0
(`echo $?` prints `0`).

Run: `cargo run -p artistpack-cli -- validate examples/full/pack.yaml`
Expected: prints `OK: examples/full/pack.yaml`, exits 0.

- [ ] **Step 4: Commit**

```bash
git add cli/Cargo.toml cli/src/main.rs
git commit -m "feat(cli): validate subcommand"
```

---

### Task 7: CLI integration tests

**Files:**
- Create: `cli/tests/validate_cmd.rs`

**Interfaces:**
- Consumes: the built `artistpack` binary via
  `env!("CARGO_BIN_EXE_artistpack")` (Cargo's standard mechanism for an
  integration test to invoke its own crate's binary — no extra
  dependency needed).

- [ ] **Step 1: Write the failing test**

```rust
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

    assert!(output.status.success(), "stderr: {}", String::from_utf8_lossy(&output.stderr));
    assert!(String::from_utf8_lossy(&output.stdout).contains("OK:"));
}

#[test]
fn validate_accepts_full_fixture() {
    let output = Command::new(artistpack_binary())
        .arg("validate")
        .arg(repo_root().join("examples/full/pack.yaml"))
        .output()
        .expect("failed to run artistpack binary");

    assert!(output.status.success(), "stderr: {}", String::from_utf8_lossy(&output.stderr));
}

#[test]
fn validate_rejects_manifest_with_bad_sha256() {
    let tmp = tempfile::NamedTempFile::with_suffix(".yaml").unwrap();
    let mut broken = std::fs::read_to_string(repo_root().join("examples/minimal/pack.yaml")).unwrap();
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
```

Add `tempfile` as a dev-dependency of `cli/Cargo.toml`:

```toml
[dev-dependencies]
tempfile = "3"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cargo test -p artistpack-cli`
Expected: fails or errors before Task 6 is committed; if Task 6 is already
committed, `validate_rejects_manifest_with_bad_sha256` and
`validate_rejects_nonexistent_file` should already pass and the first two
should already pass too — in which case this step confirms the existing
implementation rather than finding a gap. Either outcome is fine; the
point of running it now is to catch a mismatch before moving on.

- [ ] **Step 3: Fix anything the test run surfaces**

If any test fails, the most likely cause is a path issue (relative vs.
absolute) in `run_validate`'s error messages, or the exact substring
asserted against (`"sha256"`, `"OK:"`) not matching current output text —
adjust either the assertion or `cli/src/main.rs`'s message text to match,
whichever is actually wrong.

- [ ] **Step 4: Run the full workspace test suite**

Run: `cargo test --workspace`
Expected: every test in both crates passes. This is the final checkpoint
for this plan.

- [ ] **Step 5: Commit**

```bash
git add cli/tests/validate_cmd.rs cli/Cargo.toml
git commit -m "test(cli): integration tests for the validate subcommand"
```

---

## Self-Review

**Spec coverage:**
- `spec/artistpack-0.1.md` §2 (format versioning) → Task 1's
  `FORMAT_VERSION` constant, checked implicitly by every fixture parse.
- §3 (identifiers) → Task 3's `is_pack_id`/`is_slug_id`.
- §4/§5 (artist.yaml/pack.yaml shape) → Task 2's types, tested against
  real fixtures.
- §5.2 (required per-artwork fields) → Task 2's `Artwork` struct requires
  `title`, `original`, `variants`, `attribution`, `provenance` at the type
  level (non-`Option`).
- §6 (variants non-empty, no upscaling) → Task 3 checks non-empty; upscale
  prevention is a generation-time (backend) concern, not a client-side
  validation rule, so correctly out of scope here.
- §7 (integrity / SHA-256) → Task 4.
- §8 (capability negotiation) → `requires: Option<Vec<String>>` parses;
  acting on it is explicitly out of scope per Global Constraints.
- §9 (provenance required, conditional `manifest_file`) → Task 3's
  `c2pa_true_without_manifest_file_is_rejected` test.
- §10 (feed.yaml) → Task 2's `Feed` type and `parses_full_feed` test.
- §11 (unknown fields ignored) → Task 2's
  `unknown_top_level_field_is_ignored_not_rejected` test, and the Global
  Constraints note against `deny_unknown_fields`.
- `docs/architecture.md`'s "never leave a pack partially installed" /
  staging-then-atomic-activate → Task 5.
- `docs/mvp-plan.md`'s literal deliverable, `artistpack validate
  pack.yaml` must work → Tasks 6–7.

**Placeholder scan:** no TBD/TODO markers; every step has runnable code
and an exact command with an exact expected result.

**Type consistency check:** `Pack`/`Artist`/`Feed`/`ValidationError`
field and method names are identical everywhere they're referenced across
Tasks 2, 3, 6, and 7 (`from_yaml_str`, `validate_pack`, `.path`/.message`
on `ValidationError`, `pack.pack.id`, `pack.artist.id`,
`pack.artworks[i].provenance.{c2pa,manifest_file}`) — checked by re-reading
each task's Interfaces block against the ones before it.

## Execution note (fleet-specific, not the generic skill default)

Per this fleet's standing operating doctrine (`~/.claude/CLAUDE.md`
Orchestrator role / `~/.claude/rules/00-AGENT-DIRECTIVES.md` code
escalation ladder), the coding agent for this plan is **zoder**, not a
Claude Code subagent — Claude's role here is orchestrator/reviewer, not
implementer. Dispatch goes to rung 1 (zoder + TYDEUS local models /
MiniMax M3), authoring against this repository, with this plan file as
the task brief. zoder runs its own author → adversarial-review →
fix-in-place → re-review loop per commit (directive 6); Claude verifies
the final result (tests actually pass, `git log` matches the plan) before
reporting done, per `superpowers:verification-before-completion`.

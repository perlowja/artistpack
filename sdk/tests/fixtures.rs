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
    assert!(!pack.artworks[0].provenance.c2pa);
    assert!(pack.artworks[0].provenance.manifest_file.is_none());
}

#[test]
fn parses_full_pack() {
    let pack = Pack::from_yaml_str(&fixture("full/pack.yaml")).unwrap();
    assert_eq!(pack.pack.id, "org.artistpack.novaashworth.worlds");
    assert_eq!(pack.artworks[0].variants.len(), 2);
    assert_eq!(pack.artworks[0].attribution.display_name, "Nova Ashworth");
    assert!(pack.artworks[0].provenance.c2pa);
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
    assert!(
        pack.is_ok(),
        "unknown field must not break parsing: {pack:?}"
    );
}

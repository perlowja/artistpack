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
    #[serde(default)]
    pub pak_url: Option<String>,
    #[serde(default)]
    pub pak_sha256: Option<String>,
    #[serde(default)]
    pub pak_size: Option<u64>,
}

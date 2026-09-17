use std::fs;
use std::io;
use std::path::PathBuf;

pub struct Cache {
    base_dir: PathBuf,
}

impl Cache {
    pub fn new(base_dir: impl Into<PathBuf>) -> Self {
        Self {
            base_dir: base_dir.into(),
        }
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

        assert!(
            !staging.exists(),
            "staging dir must not remain after activation"
        );
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

        assert_eq!(
            fs::read_to_string(live.join("pack.yaml")).unwrap(),
            "version: 2"
        );
    }
}

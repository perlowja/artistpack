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
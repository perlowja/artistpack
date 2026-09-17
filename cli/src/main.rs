use artistpack_sdk::pak::build_pak;
use artistpack_sdk::types::Pack;
use artistpack_sdk::validate::validate_pack;
use clap::{Parser, Subcommand};
use std::path::{Path, PathBuf};
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
    /// Build a `.pak.gz` archive from a `pack.yaml` (see `docs/pak-package-format.md`).
    BuildPak {
        path: PathBuf,
        /// Output archive path. Defaults to `<pack.id>-<version>.pak.gz` in the current directory.
        #[arg(short = 'o', long = "output")]
        output: Option<PathBuf>,
    },
}

fn run_validate(path: &PathBuf) -> Result<(), String> {
    let contents =
        std::fs::read_to_string(path).map_err(|e| format!("reading {}: {e}", path.display()))?;

    let pack =
        Pack::from_yaml_str(&contents).map_err(|e| format!("parsing {}: {e}", path.display()))?;

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

fn run_build_pak(path: &Path, output: Option<&Path>) -> Result<(), String> {
    match build_pak(path, output) {
        Ok(built) => {
            println!("OK: {}", built.output_path.display());
            println!("  size: {} bytes", built.byte_size);
            println!("  sha256: {}", built.sha256);
            Ok(())
        }
        Err(e) => {
            eprintln!("FAIL: {}", path.display());
            eprintln!("  - {e}");
            Err(format!("build failed: {e}"))
        }
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
        Command::BuildPak { path, output } => match run_build_pak(&path, output.as_deref()) {
            Ok(()) => ExitCode::SUCCESS,
            Err(message) => {
                eprintln!("{message}");
                ExitCode::FAILURE
            }
        },
    }
}

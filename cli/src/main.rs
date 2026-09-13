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
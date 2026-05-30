mod claude;
mod cli;
mod codex;
mod config;
mod models;
mod ux;

fn main() {
    if let Err(err) = cli::run() {
        eprintln!("cxf: error: {err}");
        std::process::exit(1);
    }
}

fn main() {
    // 1. Get version from GITHUB_REF_NAME (e.g. "v0.1.2" -> "0.1.2")
    let version = std::env::var("GITHUB_REF_NAME")
        .map(|v| v.strip_prefix('v').unwrap_or(&v).to_string())
        // 2. Local development: try to run git describe
        .or_else(|_| {
            std::process::Command::new("git")
                .args(["describe", "--tags", "--always"])
                .output()
                .map(|o| String::from_utf8_lossy(&o.stdout).trim().to_string())
        })
        // 3. Fallback to Cargo.toml package version
        .unwrap_or_else(|_| env!("CARGO_PKG_VERSION").to_string());

    println!("cargo:rustc-env=CARGO_PKG_VERSION={}", version);
}

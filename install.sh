#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cargo build --release --manifest-path "$repo_dir/Cargo.toml"

bin_dir="${HOME}/.local/bin"
mkdir -p "$bin_dir"
install -m 0755 "$repo_dir/target/release/cxf" "$bin_dir/cxf"

completion_dir="${HOME}/.local/share/zsh/site-functions"
mkdir -p "$completion_dir"
"$bin_dir/cxf" completion zsh > "$completion_dir/_cxf" 2>/dev/null || true

rm -f "${ZDOTDIR:-$HOME}"/.zcompdump "${ZDOTDIR:-$HOME}"/.zcompdump.* 2>/dev/null || true

echo "installed: $bin_dir/cxf"
echo "completion: $completion_dir/_cxf"

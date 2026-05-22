#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if command -v pipx >/dev/null 2>&1; then
  pipx install --editable "$repo_dir" --force
else
  python -m pip install --user --break-system-packages -e "$repo_dir"
fi

completion_target="/usr/local/share/zsh/site-functions/_cxf"
if [ -d "$(dirname "$completion_target")" ]; then
  if [ -w "$(dirname "$completion_target")" ]; then
    cxf completion zsh > "$completion_target"
  elif command -v sudo >/dev/null 2>&1; then
    tmp_file="$(mktemp)"
    cxf completion zsh > "$tmp_file"
    sudo -S install -m 0644 "$tmp_file" "$completion_target"
    rm -f "$tmp_file"
  fi
fi

rm -f "${ZDOTDIR:-$HOME}"/.zcompdump "${ZDOTDIR:-$HOME}"/.zcompdump.* 2>/dev/null || true

echo "installed: $(command -v cxf)"
echo "completion: $completion_target"

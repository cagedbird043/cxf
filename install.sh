#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
venv_dir="$repo_dir/.venv"

python3 -m venv "$venv_dir"
"$venv_dir/bin/python" -m pip install -e "$repo_dir"

bin_dir="${HOME}/.local/bin"
mkdir -p "$bin_dir"
cat > "$bin_dir/cxf" <<WRAP
#!/usr/bin/env bash
exec "$venv_dir/bin/cxf" "\$@"
WRAP
chmod +x "$bin_dir/cxf"

completion_src="$repo_dir/src/cxf/completions/_cxf"
completion_target="/usr/local/share/zsh/site-functions/_cxf"
if [ -f "$completion_src" ] && [ -d "$(dirname "$completion_target")" ]; then
  if [ -w "$(dirname "$completion_target")" ]; then
    install -m 0644 "$completion_src" "$completion_target"
  elif command -v sudo >/dev/null 2>&1; then
    sudo -S install -m 0644 "$completion_src" "$completion_target"
  fi
fi

rm -f "${ZDOTDIR:-$HOME}"/.zcompdump "${ZDOTDIR:-$HOME}"/.zcompdump.* 2>/dev/null || true

echo "installed: $bin_dir/cxf"
echo "venv: $venv_dir"
echo "completion: $completion_target"

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

completion_dir="${HOME}/.local/share/zsh/site-functions"
mkdir -p "$completion_dir"
"$venv_dir/bin/cxf" completion zsh > "$completion_dir/_cxf" 2>/dev/null || true

rm -f "${ZDOTDIR:-$HOME}"/.zcompdump "${ZDOTDIR:-$HOME}"/.zcompdump.* 2>/dev/null || true

echo "installed: $bin_dir/cxf"
echo "venv: $venv_dir"
echo "completion: $completion_dir/_cxf"

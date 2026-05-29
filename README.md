# cxf — Codex / Claude provider manager

`cxf` manages LLM provider configurations for Codex and Claude Code.
It reads and writes TOML provider files and injects them into
`~/.codex/config.toml` and `~/.claude/settings.json`.

Zero network calls — purely local file operations.

## Install

### Go

```bash
go install github.com/cagedbird043/cxf@latest
```

### curl

```bash
curl -sfL https://cagedbird.cn/cxf/install.sh | sh
```

### Build from source

```bash
git clone https://github.com/cagedbird043/cxf.git
cd cxf
make install
```

## Quick start

```bash
# List all Codex providers
cxf list

# Switch to a provider
cxf use my-provider

# Show current provider
cxf current

# Add a new provider
cxf add

# Check for configuration drift
cxf status

# Claude providers
cxf claude list
cxf claude use my-claude-provider
```

## Commands

### Codex

| Command | Description |
|---------|-------------|
| `cxf list` | List all Codex providers |
| `cxf current` | Show active Codex provider |
| `cxf use <name>` | Switch to a provider |
| `cxf add` | Add a provider (interactive or flags) |
| `cxf edit <name>` | Edit a provider in $EDITOR |
| `cxf remove <name>` | Remove a provider |
| `cxf rename <old> <new>` | Rename a provider |
| `cxf status` | Check cxf controls the active provider |
| `cxf init [name]` | Import providers from Codex config |

### Claude

| Command | Description |
|---------|-------------|
| `cxf claude list` | List all Claude providers |
| `cxf claude current` | Show active Claude provider |
| `cxf claude use <name>` | Switch to a Claude provider |
| `cxf claude add` | Add a Claude provider (interactive or flags) |
| `cxf claude edit <name>` | Edit a Claude provider in $EDITOR |
| `cxf claude remove <name>` | Remove a Claude provider |
| `cxf claude rename <old> <new>` | Rename a Claude provider |
| `cxf claude status` | Check cxf controls the active provider |
| `cxf claude init [name]` | Import Claude provider from settings |

## Architecture

```
6 Go files, zero runtime deps (cobra + go-toml v1 + go-diff):

main.go     — CLI entry, cobra command tree, interactive prompts
models.go   — Provider / ClaudeProvider structs
config.go   — XDG paths, TOML/JSON file I/O, auth management
codex.go    — Codex config read/write, drift detection, provider injection
claude.go   — Claude settings read/write, drift detection, provider injection
ux.go       — ANSI colors, output helpers, diff rendering
```

### State model

- **`~/.config/cxf/providers/*.toml`** — managed Codex provider definitions
- **`~/.config/cxf/claude/providers/*.toml`** — managed Claude provider definitions
- **`~/.codex/config.toml`** — Codex config (cxf injects a `# cxf: provider = <name>` probe)
- **`~/.codex/auth.json`** — API key storage (merge-preserving, `chmod(0o600)`)
- **`~/.claude/settings.json`** — Claude settings (cxf controls the `env` block)
- **`~/.local/state/cxf/snapshots/`** — automatic pre-switch backups

### TOML handling

- Provider files: struct-based marshal/unmarshal (simple key=value)
- Codex config: go-toml v1 Tree API (preserves `#:schema` and comments)
- Probe injection: line-level surgery after serialization

## Security

- All files containing API keys are written with `chmod(0o600)`.
- `auth.json` preserves pre-existing fields (e.g. `OPENAI_ORG_ID`).
- API keys are displayed in plaintext in terminal (user preference for proxy keys).

## Configuration drift

`cxf status` detects when the active config has been manually edited.
`cxf use` warns before overwriting drifted config.

## Shell completion

```bash
cxf completion zsh > ~/.local/share/zsh/site-functions/_cxf
# add to .zshrc:
#   fpath=(~/.local/share/zsh/site-functions $fpath)
```

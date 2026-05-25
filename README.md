# cxf

`cxf` is a tiny Codex and Claude Code provider pointer manager.

It keeps provider switching low-entropy while leaving the rest of `~/.codex/config.toml` alone.

It stores managed providers under `~/.codex/cxf/` and only updates provider-related Codex fields:

- `# cxf: provider = <name>`
- `model_provider`
- `model`
- `review_model`
- `model_reasoning_effort`
- `model_context_window`
- `model_auto_compact_token_limit`
- `[model_providers.<name>]`
- `[features].responses_websockets_v2`
- `~/.codex/auth.json`

Default model settings live in `~/.codex/cxf/base.toml`; new installs default both `model` and `review_model` to `gpt-5.5`.

Commands:

```text
cxf init [name]
cxf add
cxf list
cxf current
cxf edit <provider>
cxf use <provider>
cxf doctor
cxf snapshot
cxf restore [snapshot]
cxf claude init [name]
cxf claude list
cxf claude current
cxf claude edit <provider>
cxf claude use <provider>
cxf claude doctor
```


## Claude Code providers

`cxf claude` manages Claude Code provider environment variables in `~/.claude/settings.json`.
It stores Claude provider profiles under `~/.codex/cxf/claude/providers/`.

The default Claude candidate is DeepSeek's Anthropic-compatible endpoint, following DeepSeek's official Claude Code integration guide:

```text
ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic
ANTHROPIC_MODEL=deepseek-v4-pro[1m]
ANTHROPIC_DEFAULT_OPUS_MODEL=deepseek-v4-pro[1m]
ANTHROPIC_DEFAULT_SONNET_MODEL=deepseek-v4-pro[1m]
ANTHROPIC_DEFAULT_HAIKU_MODEL=deepseek-v4-flash
CLAUDE_CODE_SUBAGENT_MODEL=deepseek-v4-flash
CLAUDE_CODE_EFFORT_LEVEL=max
```

Use:

```bash
cxf claude init anthropic
cxf claude edit deepseek
cxf claude use deepseek
cxf claude doctor
```

`cxf claude init` also preserves the current Claude settings as an `anthropic` candidate so switching back remains possible.

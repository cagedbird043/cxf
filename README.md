# cxf

`cxf` is a tiny Codex provider pointer manager.

It keeps provider switching low-entropy while leaving the rest of `~/.codex/config.toml` alone.

It stores managed providers under `~/.codex/cxf/` and only updates provider-related Codex fields:

- `cxf_provider`
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
```

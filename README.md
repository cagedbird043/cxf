# cxcfg

`cxcfg` is a terminal-first config manager for Codex CLI.

The goal is simple: keep `~/.codex/config.toml` understandable, reproducible, and easy to switch without a GUI.

Planned scope:

- Manage provider definitions outside `~/.codex/config.toml`
- Generate clean Codex runtime config from small source files
- Launch Codex with ephemeral config to avoid config rot
- Provide `doctor`, `snapshot`, `restore`, and `repair` commands
- Keep transport selection explicit: direct WebSocket, direct SSE, or local proxy

Initial command shape:

```text
cxcfg init
cxcfg doctor
cxcfg run <provider>
cxcfg snapshot
cxcfg restore
```

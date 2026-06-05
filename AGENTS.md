# cxf Agent 维护指南

cxf 是一个 Codex / Claude Code provider 切换工具。本文档给 AI agent 用，覆盖项目结构、硬规则、关键路径、常见操作。

## 项目概述

- **语言**：Rust 2024
- **依赖**：`clap`, `toml_edit`, `serde_json`, `anyhow`
- **测试**：`cargo test`，集成测试用临时 HOME / XDG 目录隔离真实配置
- **安装**：`brew install cagedbird043/tap/cxf`、`cargo install --git ...` 或 `./install.sh`（后者同时部署 zsh completion）
- **入口**：`src/main.rs` → `cli::run()`

## 架构

```
main.rs    — 入口
cli.rs     — clap 参数解析 + 命令分发
models.rs  — Provider / ClaudeProvider 数据结构
config.rs  — XDG 路径、TOML/JSON/secret 文件读写、snapshot
codex.rs   — Codex 配置 apply/status/extract/use
claude.rs  — Claude Code settings/env apply/status/use
ux.rs      — prompt / diff / 简单表格输出
```

## 关键路径

| 路径 | 说明 |
|------|------|
| `~/.config/cxf/base.toml` | 默认 model/review_model 设置（XDG_CONFIG_HOME） |
| `~/.config/cxf/providers/` | 每个 Codex provider 一个 `.toml` 文件 |
| `~/.config/cxf/auth/codex/` | 每个 Codex provider 的完整 `auth.json` profile |
| `~/.config/cxf/claude/providers/` | 每个 Claude provider 一个 `.toml` 文件 |
| `~/.local/state/cxf/snapshots/` | 切换前事故备份（XDG_STATE_HOME） |
| `~/.codex/config.toml` | Codex 主配置（cxf 注入 `# cxf: provider = <name>` 标记） |
| `~/.codex/auth.json` | Codex 认证状态；cxf 按 provider 做 whole-file profile 保存/恢复 |
| `~/.claude/settings.json` | Claude Code 配置（cxf 只改 managed env + 顶层 model） |

## 硬规则

### 安全

- 所有含 API key 的文件写入后必须 `chmod(0o600)`；通过 `config::write_secret` / `write_toml` / `write_json` 统一处理。
- API key 在终端输入和 diff 显示时不隐藏、不脱敏。用户偏好是明文可确认；磁盘权限仍要收紧。
- 不做全系统安装、不碰系统 Python、不做无关备份。

### Codex

- Codex `config.toml` 必须用 `toml_edit::DocumentMut` 做局部编辑；不要用 serde 全量重排。
- cxf 只管理：
  - probe 注释：`# cxf: provider = <name>`
  - `model_provider`
  - `model`, `review_model`, `model_reasoning_effort`
  - `model_context_window`, `model_auto_compact_token_limit`
  - `[model_providers.<name>]`
  - `[features].responses_websockets_v2`
  - `auth.json` whole-file provider profile（不解析 OAuth 字段；API-key provider 可由 `api_key` 生成最小 auth）
- 其他 Codex 配置必须保留。
- 用户当前倾向：`model_providers` 一般保持 `"OpenAI"`，避免 Codex 历史按 provider key 分裂；如要改，必须明确知道风险。

### Claude

- cxf 只清理/重写 `CLAUDE_MANAGED_KEYS` 和 `CXF_CLAUDE_PROVIDER`。
- 非托管 env，例如 `GITHUB_TOKEN`，必须保留。
- 如果 provider 没有 `ANTHROPIC_MODEL`，切换时要移除旧顶层 `model`，避免旧模型残留。

### 测试

- 新功能必须有测试。
- 改完必须跑：

```bash
cargo fmt
cargo clippy --all-targets -- -D warnings
cargo test
cargo build --release
```

## 常见操作

### 新增 provider 字段

1. `models.rs` — Provider / ClaudeProvider 增字段或 env 处理
2. `codex.rs` / `claude.rs` — apply + drift/status 同步
3. `cli.rs` — flag / prompt / handler 同步
4. `tests/integration.rs` — 加回归测试
5. `README.md` / `AGENTS.md` — 如影响用户接口或维护规则则同步

### 新增子命令

1. `cli.rs` — `CommandKind` 或 `ClaudeCommand` 增 variant
2. `cli.rs` — `run()` 分发
3. 对应模块实现 handler
4. `cmd_completion()` 更新补全
5. `tests/integration.rs` 加测试

## 文档同步规则

每次任务完成后检查：

- 模块/命令/安装方式变了：更新 README + AGENTS
- 测试/CI 方式变了：更新 README + AGENTS
- 配置路径或安全规则变了：更新 README + AGENTS
- 纯 bug 修复且接口不变：可不更新文档

## Git

- 提交信息遵循仓库上层 Lore Commit Protocol。
- 只提交和本次任务相关文件。
- 不改写历史，除非用户明确要求。

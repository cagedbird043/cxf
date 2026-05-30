[![CI](https://github.com/cagedbird043/cxf/actions/workflows/ci.yml/badge.svg)](https://github.com/cagedbird043/cxf/actions/workflows/ci.yml)
[![Rust](https://img.shields.io/badge/rust-2024-orange.svg)](https://www.rust-lang.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

# cxf — Codex Provider Pointer Manager

`cxf` 是一个极简的 [Codex](https://github.com/openai/codex) / [Claude Code](https://github.com/anthropics/claude-code) provider 切换工具。它只动 provider 相关字段，不动你其他配置，让你在多个 API 端点之间丝滑切换。

当前实现是 Rust 单二进制版本，Codex `config.toml` 使用 `toml_edit` 做局部编辑，尽量保留用户原文件结构、注释和无关配置。

## Install

### Homebrew（推荐）

```bash
brew install cagedbird043/tap/cxf
```

### Cargo

```bash
cargo install --git https://github.com/cagedbird043/cxf.git
```

### install.sh（含 zsh completion）

```bash
git clone https://github.com/cagedbird043/cxf.git
cd cxf
./install.sh
```

安装后执行 `cxf init` 从当前 Codex 配置提取已有 provider，然后就可以开始用了。

## Quick Start

```bash
# 查看所有命令
cxf

# 初始化：从当前 Codex 配置提取 providers
cxf init

# 列出已注册的 providers
cxf list

# 切换到某个 provider
cxf use <provider-name>

# 查看当前状态
cxf current

# 添加新 provider（交互式）
cxf add

# 添加新 provider（非交互，适合脚本）
cxf add --provider-id openrouter \
  --base-url https://openrouter.ai/api/v1 \
  --api-key sk-or-v1-xxxx \
  --wire-api chat

# 查看配置是否与 provider 定义一致
cxf status
```

## Claude Code 支持

`cxf claude` 子命令管理 Claude Code provider 的环境变量，零侵入——只改 `~/.claude/settings.json` 的 `env` 块。

```bash
# 初始化：提取当前 Claude 配置 + deepseek 候选
cxf claude init

# 列出所有 Claude providers
cxf claude list

# 切换到 DeepSeek 的 Anthropic 兼容端点
cxf claude use deepseek

# 切回官方 Anthropic
cxf claude use anthropic

# 查看当前 Claude 配置状态
cxf claude status
```

默认的 DeepSeek 候选配置：

| 变量 | 值 |
|------|-----|
| `ANTHROPIC_BASE_URL` | `https://api.deepseek.com/anthropic` |
| `ANTHROPIC_MODEL` | `deepseek-v4-pro[1m]` |
| `ANTHROPIC_DEFAULT_OPUS_MODEL` | `deepseek-v4-pro[1m]` |
| `ANTHROPIC_DEFAULT_SONNET_MODEL` | `deepseek-v4-pro[1m]` |
| `ANTHROPIC_DEFAULT_HAIKU_MODEL` | `deepseek-v4-flash` |
| `CLAUDE_CODE_SUBAGENT_MODEL` | `deepseek-v4-flash` |
| `CLAUDE_CODE_EFFORT_LEVEL` | `max` |

## Commands

### Codex 命令

| 命令 | 说明 |
|------|------|
| `cxf init [name]` | 从当前 Codex 配置提取 providers |
| `cxf list` | 列出所有已注册 provider |
| `cxf current` | 查看当前生效的 provider |
| `cxf use <provider>` | 切换到指定 provider |
| `cxf add` | 交互式添加新 provider |
| `cxf add --provider-id ...` | 非交互式添加（参见上方示例） |
| `cxf edit <provider>` | 用 `$EDITOR` 编辑 provider |
| `cxf remove <provider>` | 删除 provider |
| `cxf status` | 检查当前状态是否与 provider 定义一致 |

### Claude 命令

| 命令 | 说明 |
|------|------|
| `cxf claude init [name]` | 提取当前 Claude 配置 |
| `cxf claude list` | 列出所有 Claude providers |
| `cxf claude current` | 查看当前 Claude 配置 |
| `cxf claude use <provider>` | 切换 Claude provider |
| `cxf claude edit <provider>` | 编辑 Claude provider |
| `cxf claude remove <provider>` | 删除 Claude provider |
| `cxf claude status` | 检查 Claude 配置一致性 |

## 文件布局

```
~/.config/cxf/                     # XDG_CONFIG_HOME → cxf 自身配置
├── base.toml                      # 默认 model/review_model 设置
├── providers/                     # 每个 provider 一个 .toml 文件
│   ├── openai.toml
│   └── ...
└── claude/
    └── providers/                 # Claude provider 定义
        ├── deepseek.toml
        └── ...

~/.local/state/cxf/                # XDG_STATE_HOME → cxf 运行状态
└── snapshots/                     # 切换前自动备份
    └── ...
```

cxf 只操作以下 Codex 配置字段：
- 配置文件中注入 `# cxf: provider = <name>` 标记
- `model_provider`, `model`, `review_model`, `model_reasoning_effort`
- `model_context_window`, `model_auto_compact_token_limit`
- `[model_providers.<name>]` 块
- `[features].responses_websockets_v2`
- `auth.json` 中的 `OPENAI_API_KEY`

其他所有 Codex 配置保持不动。

## 重要说明

- **`model_providers` 必须始终为 `"OpenAI"`**。Codex 以 `model_provider` 字段作为 session key 关联历史记录，一旦改名字所有会话历史丢失。不同后端只能通过调整 `base_url` 和 API key 来切换，不要改动 `model_providers` 名称。
- 切换后端后 Codex 历史记录不会丢失（因为 `model_provider` 没变），但之前的对话上下文仍会保留。

## 架构

cxf 分为 6 个 Rust 模块：

```
main.rs    — 入口
cli.rs     — clap 参数解析 + 命令分发
models.rs  — Provider / ClaudeProvider 数据结构
config.rs  — XDG 路径、TOML/JSON/secret 文件读写
codex.rs   — Codex 配置 apply/status/extract/use
claude.rs  — Claude Code settings/env apply/status/use
ux.rs      — prompt / diff / 简单表格输出
```

## 开发者

- **AI Agent 说明**：参见 [`AGENTS.md`](AGENTS.md)
- 测试：`cargo test`
- 静态检查：`cargo clippy --all-targets -- -D warnings`
- 格式化：`cargo fmt`
- 关键依赖：`clap`, `toml_edit`, `serde_json`, `anyhow`

## License

MIT

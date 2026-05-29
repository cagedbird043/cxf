[![CI](https://github.com/cagedbird043/cxf/actions/workflows/ci.yml/badge.svg)](https://github.com/cagedbird043/cxf/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/cagedbird043/cxf/graph/badge.svg)](https://codecov.io/gh/cagedbird043/cxf)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

# cxf — Codex Provider Pointer Manager

`cxf` 是一个极简的 [Codex](https://github.com/openai/codex) / [Claude Code](https://github.com/anthropics/claude-code) provider 切换工具。它只动 provider 相关字段，不动你其他配置，让你在多个 API 端点之间丝滑切换。

## Install

### pip

```bash
pip install git+https://github.com/cagedbird043/cxf.git
```

### install.sh（推荐，含 zsh completion）

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
~/.codex/cxf/
├── base.toml          # 默认 model/review_model 设置
├── providers/         # 每个 provider 一个 .toml 文件
│   ├── openai.toml
│   └── ...
└── claude/
    └── providers/     # Claude provider 定义
        ├── deepseek.toml
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

## 安全模型

- 所有含 API key 的文件写入后自动 `chmod(0o600)`
- `cxf add` 非交互模式下，`--api-key` 为空会直接报错
- `cxf edit` 编辑后若 api_key 仍为空，拒绝切换并告警
- `auth.json` 写入时合并已有字段，不会覆盖其他 key

## 架构

cxf 分为 6 个模块：

```
cli.py      — 参数解析 + 命令分发（唯一入口）
models.py   — Provider 数据类
config.py   — 所有文件路径、读写、布局初始化
codex.py    — Codex 专有配置操作（diff/apply/extract）
claude.py   — Claude Code 专有配置操作
ux.py       — i18n 翻译、Rich 输出面板、diff 显示
```

## 开发者

- **AI Agent 说明**：参见 [`AGENTS.md`](AGENTS.md)
- 测试：`pytest tests/`（需要 `pytest`）
- 依赖：`tomlkit>=0.13`, `rich>=13.0`
- Python >= 3.11

## License

MIT

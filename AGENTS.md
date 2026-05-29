# cxf Agent 维护指南

cxf 是一个 Codex / Claude Code provider 切换工具。本文档给 AI agent 用，覆盖项目结构、硬规则、关键路径、常见操作。

## 项目概述

- **语言**：Python >= 3.11
- **依赖**：tomlkit, rich（纯 Python，无二进制依赖）
- **测试**：pytest，54+ 测试，全隔离（`_patch_paths` + `tmp_path`）
- **安装**：`pip install` 或 `./install.sh`（后者同时部署 zsh completion）
- **入口**：`src/cxf/cli.py:main()`

## 架构：6 模块

```
cli.py      — argparse 参数解析 + _CODEX_COMMANDS/_CLAUDE_COMMANDS 分发
models.py   — Provider dataclass（provider_id, base_url, api_key, wire_api 等）
config.py   — 所有文件路径常量、_ensure_layout/_ensure_claude_layout、读写函数
codex.py    — Codex 专有逻辑（_apply_provider/_provider_drift/_extract_all_providers 等）
claude.py   — Claude Code 专有逻辑（_apply_claude_provider 等）
ux.py       — i18n（`_()` 函数，60+ 翻译键）、Rich 输出面板、diff 显示、工具函数
```

**分派规则**：`cli.py` 的 `main()` 见 `argparse` 结果，Codex 命令走 `_CODEX_COMMANDS`，Claude 命令走 `_CLAUDE_COMMANDS`。

## 关键路径

| 路径 | 说明 |
|------|------|
| `~/.codex/cxf/base.toml` | 默认 model/review_model 设置 |
| `~/.codex/cxf/providers/` | 每个 provider 一个 .toml 文件 |
| `~/.codex/cxf/claude/providers/` | Claude provider .toml 文件 |
| `~/.codex/config.toml` | Codex 主配置（cxf 会注入 `# cxf: provider = <name>` 标记） |
| `~/.codex/auth.json` | API key 存储 |
| `~/.claude/settings.json` | Claude Code 配置（cxf 只改 `env` 块） |
| `src/cxf/completions/_cxf` | zsh completion 源码 |

## 硬规则

### 🛡️ 安全

- **所有含 API key 的文件写入后必须 `chmod(0o600)`**。已在 `config.py` 的 `_write_toml`/`_write_json`/`_write_auth` 和 `cli.py` 的 `_cmd_use` 中实现。新增写路径要同样处理。
- 所有文件操作必须指定 `encoding="utf-8"`。
- 不用 `sys.exit()`——统一用 `raise SystemExit(main())` 或 return int。
- 密码/密钥不在日志或异常信息中泄露。

### 📁 代码规范

- 新功能必须有测试。测试改完后跑 `pytest tests/ -q`，全绿才能提。
- 测试必须全隔离：用 `_patch_paths(monkeypatch, tmp_path)` 模拟所有路径。
- 不改 `ux.py` 的 `_()` 翻译字典结构（`(zh, en)` tuple），加新翻译键可以。
- i18n：提示/错误/帮助用 `_("key")`，用户可见的标签和布尔值用英文。
- Provider 数据类字段：`provider_id`, `model_providers`, `base_url`, `api_key`, `wire_api`, `requires_openai_auth`, `websocket`。新增需同步修改 Provider dataclass + toml 写入/解析 + _apply_provider。

### 🧪 测试

- 测试文件：`tests/test_cli.py`
- 工具函数：`conftest` 不在，直接用 `monkeypatch` + `tmp_path` + `_patch_paths`
- `_patch_paths` 会 patch 6 个模块里所有路径引用。新增模块时需要加入 patch。
- mock editor：`monkeypatch.setattr("subprocess.call", lambda _: 0)` 并结合文件写入模拟。
- mock `_cmd_use`：`monkeypatch.setattr("cxf.cli._cmd_use", lambda provider_id: 0)`。

### 🔧 常见操作

**新增 provider 字段**：
1. `models.py` — Provider dataclass 加字段
2. `config.py` — `_write_provider`/`_read_toml` 的处理逻辑
3. `codex.py` — `_apply_provider` 做字段映射
4. `cli.py` — `_cmd_add` 的 prompt/flag 处理
5. `ux.py` — 如果有新的翻译键

**新增子命令**：
1. `cli.py` — `build_parser()` 加 subparser
2. `cli.py` — `_CODEX_COMMANDS` 或 `_CLAUDE_COMMANDS` 加分发
3. `cli.py` — 写 handler 函数（`_cmd_xxx`）
4. `tests/test_cli.py` — 写测试
5. `src/cxf/completions/_cxf` — 更新补全

## 验证

```bash
pytest tests/ -q                          # 跑全部测试
python -m cxf.cli list                    # 不安装直接跑
cxf --version                              # 检查版本
cxf status                                 # 检查当前状态
cxf claude status                          # 检查 Claude 状态
```

## Git

- 提交信息用中文，简短说明变更
- 只提交和本次任务相关的文件
- 不改写历史

## 相关文档

- [`README.md`](README.md) — 用户文档，含快速入门、命令参考、安全模型
- [`CLAUDE.md`](CLAUDE.md) — 软链到本文件，供 Claude Code / AI 自动读取

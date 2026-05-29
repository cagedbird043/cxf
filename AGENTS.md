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
| `~/.config/cxf/base.toml` | 默认 model/review_model 设置（XDG_CONFIG_HOME） |
| `~/.config/cxf/providers/` | 每个 provider 一个 .toml 文件 |
| `~/.config/cxf/claude/providers/` | Claude provider .toml 文件 |
| `~/.local/state/cxf/snapshots/` | 切换前自动备份（XDG_STATE_HOME） |
| `~/.codex/config.toml` | Codex 主配置（cxf 会注入 `# cxf: provider = <name>` 标记） |
| `~/.codex/auth.json` | API key 存储 |
| `~/.claude/settings.json` | Claude Code 配置（cxf 只改 `env` 块） |
| `src/cxf/completions/_cxf` | zsh completion 源码 |

## 硬规则

### 🛡️ 安全

- **所有含 API key 的文件写入后必须 `chmod(0o600)`**。已在 `config.py` 的 `_write_toml`/`_write_json`/`_write_auth` 和 `cli.py` 的 `_cmd_use` 中实现。新增写路径要同样处理。
- 所有文件操作必须指定 `encoding="utf-8"`。
- 不用 `sys.exit()`——统一用 `raise SystemExit(main())` 或 return int。
- **API key 在终端输入和 diff 显示时不隐藏、不脱敏。** 用户观点：这些是中转站/代理的廉价 key，不是高价值密钥。隐藏输入反而让用户无法确认输入是否正确。不要用 `getpass`、不要做 `redact`。磁盘文件仍要 `chmod(0o600)` 防误读。

### 📁 代码规范

- **所有 Codex provider 的 `model_providers` 字段必须为 `"OpenAI"`**。Codex 以 `model_provider` 为 session key 关联历史记录，一旦改名所有历史丢失。不同后端只能通过改 `base_url`/`api_key` 区分，不要改 `model_providers` 名字。
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

## 📄 文档同步规则（Loop-back Check）

**每次任务完成后，必须检查 AGENTS.md 是否与变更同步。** 以下表格直接对应 AGENTS.md 各章节，方便定位：

### 触发条件与操作

| 变更类型 | 检查哪些章节 | 必须更新 Y / 可跳过 N |
|---------|-------------|----------------------|
| 新增/删除/重命名模块 | **架构：6 模块** — 增删行；**常见操作** — 如有扩展步骤 | Y |
| 新增/修改子命令、参数、parser 结构 | **cli.py 分析**（如有）、**常见操作 / 新增子命令** 步骤表 | Y |
| 新增硬规则（安全/代码/测试规范） | **硬规则** — 加入对应子段 | Y |
| 新增/变更依赖（pyproject.toml） | **项目概述** — 依赖列表 | Y |
| 新增路径常量、配置目录 | **关键路径** — 加入表格 | Y |
| 修改测试框架、测试工具、mock 模式 | **🧪 测试** — 更新说明 | Y |
| 修改 i18n 结构、增加翻译键类别 | **ux.py** 模块说明 | Y |
| 修改安装方式、入口、zsh completion | **项目概述**、**README.md** | Y |
| 纯 bug 修复，不改接口/模块/结构 | 无 | N |
| 重构，不新增/删除/重命名模块 | **架构** 段如有模块职责变化才更新 | N |
| 测试覆盖新增，不改变测试框架 | 无 | N |
| 翻译键增减，不改变字典结构/分类 | 无 | N |
| 变量/函数重命名，不改模块边界 | 无 | N |

### 执行流程

```
1. 跑完 pytest tests/ -q 确认全绿
2. 对照上表检查本次变更命中了哪些"必须更新"的条目
3. 更新 AGENTS.md 对应章节
4. `git diff` 确认改干净了
5. 提交时 CLAUDE.md（软链）自动同步，不需额外操作
```

### 判断原则

- **宁可多更新一行，不要漏更新。** 新增一条命令只改一行命令表，成本极低；漏了下次 AI 进来读到的就是过时的。
- 不确定是否匹配变更 → 按 Y 处理。
- 目录/文件路径、模块名、命令名必须精确，不要模糊描述。
- Symlink（CLAUDE.md → AGENTS.md）不需单独维护，操作系统级同步，但你修改 AGENTS.md 后 git status 里只会出现 AGENTS.md，CLAUDE.md 不会有变动记录——这是正常的。

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

# cxf Agent 维护指南

Go 重写版（2026-05）。6 个文件，单包，外部依赖 3 个。

## 架构

```
main.go     — Cobra 命令树 + 交互式提示 + snapshot 辅助
models.go   — Provider / ClaudeProvider 结构体
config.go   — XDG 路径、TOML/JSON 文件 IO、auth 管理
codex.go    — Codex config.toml 读写、漂移检测、provider 注入
claude.go   — Claude settings.json 读写、漂移检测、provider 注入
ux.go       — ANSI 颜色、输出 helper、diff 渲染
```

## 依赖

| 包 | 用途 |
|----|------|
| `spf13/cobra` | CLI 框架（二级子命令） |
| `pelletier/go-toml` v1 | TOML Tree API（Codex config 注释保留） |
| `sergi/go-diff` | unified diff 显示 |

## 关键路径

| 路径 | 说明 |
|------|------|
| `~/.config/cxf/providers/*.toml` | Codex provider 定义 |
| `~/.config/cxf/claude/providers/*.toml` | Claude provider 定义 |
| `~/.codex/config.toml` | Codex 配置（cxf 写入探测行 `# cxf: provider = xxx`） |
| `~/.codex/auth.json` | API key 存储（merge-preserving） |
| `~/.claude/settings.json` | Claude 配置（cxf 控制 env 块） |
| `~/.local/state/cxf/snapshots/` | 切换前自动备份 |

## 硬规则

### 🛡️ 安全

- 所有含 API key 的文件写入后必须 `chmod(0o600)`。
- `auth.json` 必须 read-merge-write，保留 `OPENAI_ORG_ID` 等外部字段。
- API key 在终端显示时不脱敏（代理 key 策略）。

### 📁 TOML 策略

- Provider 文件（自己的）：`toml.Marshal`/`Unmarshal` 结构体标签
- Codex config.toml：go-toml v1 Tree API 保留 `#:schema` 和用户注释
- 探测行 `# cxf: provider = xxx`：序列化后行级注入

### 漂移检测

- Codex：结构化字段比较（model、model_provider、review_model、context_window 等）
- Claude：env key 逐一比较
- 检测到漂移时显示 unified diff，询问是否覆盖

### 命令补全

所有 `use`/`edit`/`remove` 命令通过 `ValidArgsFunction` 动态补全 provider 名。
不需要手写补全脚本。

## 常见操作

### 新增 provider 字段

1. `models.go` — Provider struct 加字段和 toml tag
2. `config.go` — 读写逻辑（如果用结构化 marshal 则不需改）
3. `codex.go` — `applyProvider` 加 tree.Set，`detectCodexDrift` 加比较
4. `main.go` — `addCmd` 加 flag 和 prompt

### 验证

```bash
go build .
./cxf list
./cxf claude list
./cxf status
go vet ./...
```

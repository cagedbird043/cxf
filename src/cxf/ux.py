from __future__ import annotations

import difflib
import getpass
import json
import os
import sys
from pathlib import Path
from typing import Any, NoReturn

# ── locale detection ───────────────────────────────────────────────────

_IS_ZH = os.environ.get("LANG", "").startswith("zh")


# ── translation table ──────────────────────────────────────────────────
# Each entry: (english, chinese)
# Use {} for format placeholders.

_I18N: dict[str, tuple[str, str]] = {
    # -- argparse help --
    "help.init": (
        "Initialize managed providers from current config",
        "从当前配置初始化托管 provider",
    ),
    "help.list": (
        "List managed providers",
        "列出所有托管 provider",
    ),
    "help.current": (
        "Show active provider",
        "显示当前激活的 provider",
    ),
    "help.use": (
        "Switch to a managed provider",
        "切换到指定 provider",
    ),
    "help.add": (
        "Add a provider",
        "添加 provider",
    ),
    "help.edit": (
        "Open a provider in $EDITOR",
        "编辑 provider",
    ),
    "help.remove": (
        "Remove a managed provider",
        "删除 provider",
    ),
    "help.status": (
        "Check whether cxf controls the active provider",
        "检查 cxf 是否管控当前 provider",
    ),
    "help.claude": (
        "Manage Claude Code provider pointer",
        "管理 Claude Code provider 指针",
    ),
    "help.claude_init": (
        "Initialize Claude providers from current settings",
        "从当前设置初始化 Claude provider",
    ),
    "help.claude_list": (
        "List managed Claude providers",
        "列出所有托管 Claude provider",
    ),
    "help.claude_current": (
        "Show active Claude provider",
        "显示当前激活的 Claude provider",
    ),
    "help.claude_use": (
        "Switch Claude Code to a managed provider",
        "切换 Claude Code 到指定 provider",
    ),
    "help.claude_edit": (
        "Open a Claude provider in $EDITOR",
        "编辑 Claude provider",
    ),
    "help.claude_remove": (
        "Remove a managed Claude provider",
        "删除 Claude provider",
    ),
    "help.claude_status": (
        "Check whether cxf controls Claude settings",
        "检查 cxf 是否管控 Claude 设置",
    ),
    # -- argument help --
    "arg.name": (
        "Provider id (defaults to current provider)",
        "Provider 名称（默认当前 provider）",
    ),
    "arg.provider": (
        "Provider id",
        "Provider 名称",
    ),
    "arg.yes": (
        "Skip confirmation prompts",
        "跳过确认提示",
    ),
    "arg.add.provider_id": (
        "Provider id (interactive if omitted)",
        "Provider 名称（省略则交互式输入）",
    ),
    "arg.add.model_providers": (
        "Model provider name",
        "模型提供商名称",
    ),
    "arg.add.base_url": (
        "API base URL",
        "API 地址",
    ),
    "arg.add.api_key": (
        "API key",
        "API 密钥",
    ),
    "arg.add.wire_api": (
        "API wire format (responses or chat)",
        "API 格式（responses 或 chat）",
    ),
    "arg.add.no_websocket": (
        "Disable WebSocket support",
        "禁用 WebSocket",
    ),
    # -- output labels (config keys, always in English) --
    "lbl.provider": ("provider", "provider"),
    "lbl.model_provider": ("model_provider", "model_provider"),
    "lbl.model": ("model", "model"),
    "lbl.review_model": ("review_model", "review_model"),
    "lbl.base_url": ("base_url", "base_url"),
    "lbl.websocket": ("websocket", "websocket"),
    "lbl.auth": ("auth", "auth"),
    "lbl.claude_provider": ("claude_provider", "claude_provider"),
    "lbl.model_opus": ("opus", "opus"),
    "lbl.model_sonnet": ("sonnet", "sonnet"),
    "lbl.model_haiku": ("haiku", "haiku"),
    "lbl.subagent": ("subagent", "subagent"),
    "lbl.controlled": ("controlled", "controlled"),
    "lbl.unknown": ("unknown", "unknown"),
    # -- bool labels (config values, always in English) --
    "bool.on": ("on", "on"),
    "bool.off": ("off", "off"),
    # -- status output --
    "status.controlled_yes": (
        "controlled: yes",
        "管控中: 是",
    ),
    "status.controlled_no": (
        "controlled: no",
        "管控中: 否",
    ),
    "status.controlled_partial": (
        "controlled: partial",
        "管控中: 部分",
    ),
    "status.reason.missing_probe": (
        "cxf provider comment is missing",
        "cxf provider 标记缺失",
    ),
    "status.reason.missing_file": (
        "provider file is missing: {}",
        "provider 文件不存在: {}",
    ),
    "status.reason.missing_claude_env": (
        "env.CXF_CLAUDE_PROVIDER is missing",
        "缺少 env.CXF_CLAUDE_PROVIDER",
    ),
    "status.reason.missing_claude_file": (
        "claude provider file is missing: {}",
        "Claude provider 文件不存在: {}",
    ),
    "status.drift": (
        "drift: {}",
        "偏离: {}",
    ),
    "status.drift_auth": (
        "drift: auth OPENAI_API_KEY",
        "偏离: API 密钥",
    ),
    "status.fix_use": (
        "fix: cxf use {}",
        "修复: cxf use {}",
    ),
    "status.fix_claude_use": (
        "fix: cxf claude use {}",
        "修复: cxf claude use {}",
    ),
    # -- prompts --
    "p.provider_id": (
        "provider id",
        "provider 名称",
    ),
    "p.model_providers": (
        "model_providers",
        "模型提供商",
    ),
    "p.base_url": (
        "base_url",
        "API 地址",
    ),
    "p.api_key": (
        "api_key",
        "API 密钥",
    ),
    "p.wire_api": (
        "wire_api",
        "API 格式",
    ),
    "p.websocket": (
        "websocket",
        "WebSocket",
    ),
    "p.create_provider": (
        "provider '{}' does not exist. Create it?",
        "provider '{}' 不存在。是否创建？",
    ),
    "p.remove_provider": (
        "remove provider '{}'?",
        "确定删除 provider '{}'？",
    ),
    "p.remove_claude_provider": (
        "remove claude provider '{}'?",
        "确定删除 Claude provider '{}'？",
    ),
    "p.aborted": (
        "aborted",
        "已取消",
    ),
    "p.provider_id_required": (
        "provider id is required",
        "必须指定 provider 名称",
    ),
    # -- messages --
    "msg.initialized": (
        "initialized: {}",
        "已初始化: {}",
    ),
    "msg.provider_line": (
        "provider: {} -> {} {}",
        "provider: {} -> {} {}",
    ),
    "msg.current": (
        "current: {} -> {} {}",
        "当前: {} -> {} {}",
    ),
    "msg.claude_current": (
        "claude current: {} -> {} {}",
        "Claude 当前: {} -> {} {}",
    ),
    "msg.claude_initialized": (
        "initialized: {}",
        "已初始化: {}",
    ),
    "msg.claude_provider_line": (
        "claude provider: {} -> {} {}",
        "Claude provider: {} -> {} {}",
    ),
    "msg.removed": (
        "removed: {}",
        "已删除: {}",
    ),
    "msg.created": (
        "created: {}",
        "已创建: {}",
    ),
    # -- errors --
    "err.not_found": (
        "provider not found: {}",
        "provider 不存在: {}",
    ),
    "err.claude_not_found": (
        "claude provider not found: {}",
        "Claude provider 不存在: {}",
    ),
    "err.editor_not_set": (
        "EDITOR is not set",
        "未设置 EDITOR 环境变量",
    ),
    "err.unsupported_shell": (
        "unsupported shell: {}",
        "不支持的 shell: {}",
    ),
    "err.unknown_command": (
        "unknown command: {}",
        "未知命令: {}",
    ),
    "err.unknown_claude_command": (
        "unknown claude command: {}",
        "未知 claude 命令: {}",
    ),
    "err.unexpected_argument": (
        "unexpected argument: {}",
        "意外的参数: {}",
    ),
    # -- generic utility strings --
    "yes": ("yes", "是"),
    "no": ("no", "否"),
}


def _(key: str, *args: object) -> str:
    """Translate key to current locale with optional format args."""
    pair = _I18N.get(key)
    if pair is None:
        return key if not args else key.format(*args)
    text = pair[1] if _IS_ZH else pair[0]
    return text if not args else text.format(*args)


# ── error / warning output ─────────────────────────────────────────────


def _error(key: str, *args: object) -> NoReturn:
    """Print unified error message to stderr and exit."""
    print(f"cxf: error: {_(key, *args)}", file=sys.stderr)
    raise SystemExit(1)


def _warn(key: str, *args: object) -> None:
    """Print a warning to stderr."""
    print(f"cxf: warning: {_(key, *args)}", file=sys.stderr)


# ── prompts ────────────────────────────────────────────────────────────


def _prompt(key: str, default: str | None = None, secret: bool = False) -> str:
    suffix = f" [{default}]" if default is not None else ""
    label = _(key)
    try:
        if secret:
            value = getpass.getpass(f"{label}{suffix}: ").strip()
        else:
            value = input(f"{label}{suffix}: ").strip()
    except (KeyboardInterrupt, EOFError):
        raise SystemExit("\ncancelled")
    if not value and default is not None:
        return default
    return value


def _prompt_bool(key: str, default: bool) -> bool:
    default_text = _("yes") if default else _("no")
    value = _prompt(key, default_text).lower()
    return value in {"y", "yes", "true", "1", "on", "是"}


def _confirm(key: str, *args: object, yes: bool = False) -> bool:
    """Ask for confirmation. Return True if confirmed."""
    if yes:
        return True
    label = _(key, *args)
    ans = input(f"{label} [y/N]: ").strip().lower()
    return ans in {"y", "yes", "是"}


# ── output formatting ──────────────────────────────────────────────────


def _format_bool(value: Any) -> str:
    if value is True:
        return _("bool.on")
    if value is False:
        return _("bool.off")
    return "-"


# ── diff / redact ──────────────────────────────────────────────────────


def _diff(before: str, after: str, fromfile: str, tofile: str) -> str:
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=fromfile,
            tofile=tofile,
        )
    )


def _redact_key(text: str) -> str:
    try:
        data = json.loads(text)
    except Exception:
        return text
    if "OPENAI_API_KEY" in data and data["OPENAI_API_KEY"]:
        data["OPENAI_API_KEY"] = "sk-***"
    return json.dumps(data, indent=2) + "\n"


def _redact_claude_settings(text: str) -> str:
    try:
        data = json.loads(text) if text else {}
    except Exception:
        return _redact_key(text)
    env = data.get("env")
    if isinstance(env, dict):
        for key in ("ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY", "GITHUB_TOKEN"):
            if env.get(key):
                env[key] = "***"
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"

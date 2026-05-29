from __future__ import annotations

import difflib
import getpass
import json
import os
import sys
from typing import Any, NoReturn

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

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
    "help.claude_add": (
        "Add a Claude provider",
        "添加 Claude provider",
    ),
    "help.claude_remove": (
        "Remove a managed Claude provider",
        "删除 Claude provider",
    ),
    "help.claude_status": (
        "Check whether cxf controls Claude settings",
        "检查 cxf 是否管控 Claude 设置",
    ),
    "help.rename": (
        "Rename a provider",
        "重命名 provider",
    ),
    "help.claude_rename": (
        "Rename a Claude provider",
        "重命名 Claude provider",
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
    "arg.add.context_window": (
        "Context window size (e.g. 1000000 for 1M)",
        "上下文窗口大小（如 1000000 表示 1M）",
    ),
    "arg.add.auto_compact": (
        "Auto-compact token limit",
        "自动压缩的 token 阈值",
    ),
    "arg.rename.old": (
        "Current provider id",
        "当前 provider 名称",
    ),
    "arg.rename.new": (
        "New provider id",
        "新 provider 名称",
    ),
    "arg.claude_add.provider_id": (
        "Provider id (interactive if omitted)",
        "Provider 名称（省略则交互式输入）",
    ),
    "arg.claude_add.base_url": (
        "Anthropic-compatible base URL",
        "Anthropic 兼容 API 地址",
    ),
    "arg.claude_add.api_key": (
        "Anthropic API key",
        "Anthropic API 密钥",
    ),
    "arg.claude_add.model": (
        "Model name",
        "模型名称",
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
    # -- status output (always English) --
    "status.controlled_yes": ("controlled: yes", "controlled: yes"),
    "status.controlled_no": ("controlled: no", "controlled: no"),
    "status.controlled_partial": ("controlled: partial", "controlled: partial"),
    "status.reason.missing_probe": ("cxf provider comment is missing", "cxf provider comment is missing"),
    "status.reason.missing_file": ("provider file is missing: {}", "provider file is missing: {}"),
    "status.reason.missing_claude_env": (
        "env.CXF_CLAUDE_PROVIDER is missing",
        "env.CXF_CLAUDE_PROVIDER is missing",
    ),
    "status.reason.missing_claude_file": (
        "claude provider file is missing: {}",
        "claude provider file is missing: {}",
    ),
    "status.drift": ("drift: {}", "drift: {}"),
    "status.drift_auth": ("drift: auth OPENAI_API_KEY", "drift: auth OPENAI_API_KEY"),
    "status.fix_use": ("fix: cxf use {}", "fix: cxf use {}"),
    "status.fix_claude_use": ("fix: cxf claude use {}", "fix: cxf claude use {}"),
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
    "p.aborted": ("aborted", "aborted"),
    "p.provider_id_required": (
        "provider id is required",
        "必须指定 provider 名称",
    ),
    "p.claude_provider_id": (
        "provider id",
        "provider 名称",
    ),
    "p.claude_base_url": (
        "ANTHROPIC_BASE_URL",
        "API 地址",
    ),
    "p.claude_api_key": (
        "ANTHROPIC_AUTH_TOKEN",
        "API 密钥",
    ),
    "p.claude_model": (
        "ANTHROPIC_MODEL",
        "模型名称",
    ),
    # -- messages (always English) --
    "msg.initialized": ("initialized: {}", "initialized: {}"),
    "msg.provider_line": ("provider: {} -> {} {}", "provider: {} -> {} {}"),
    "msg.current": ("current: {} -> {} {}", "current: {} -> {} {}"),
    "msg.claude_current": ("claude current: {} -> {} {}", "claude current: {} -> {} {}"),
    "msg.claude_initialized": ("initialized: {}", "initialized: {}"),
    "msg.claude_provider_line": ("claude provider: {} -> {} {}", "claude provider: {} -> {} {}"),
    "msg.removed": ("removed: {}", "removed: {}"),
    "msg.created": ("created: {}", "created: {}"),
    "msg.renamed": ("renamed: {} -> {}", "renamed: {} -> {}"),
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
    "err.add.no_base_url": (
        "base_url is required in non-interactive mode",
        "非交互模式下必须指定 base_url",
    ),
    "err.add.no_api_key": (
        "api_key is required in non-interactive mode",
        "非交互模式下必须指定 api_key",
    ),
    "err.edit.no_api_key": (
        "api_key is empty in provider '{}'. Aborting apply.",
        "provider '{}' 的 api_key 为空，已中止切换。",
    ),
    "err.claude_edit.no_key": (
        "ANTHROPIC_AUTH_TOKEN is empty in claude provider '{}'. Aborting apply.",
        "Claude provider '{}' 的 ANTHROPIC_AUTH_TOKEN 为空，已中止切换。",
    ),
    "err.rename.not_found": (
        "provider not found: {}",
        "provider 不存在: {}",
    ),
    "err.rename.exists": (
        "provider already exists: {}",
        "provider 已存在: {}",
    ),
    "err.claude_rename.not_found": (
        "claude provider not found: {}",
        "Claude provider 不存在: {}",
    ),
    "err.claude_rename.exists": (
        "claude provider already exists: {}",
        "Claude provider 已存在: {}",
    ),
    "err.claude_add.no_base_url": (
        "base_url is required in non-interactive mode",
        "非交互模式下必须指定 base_url",
    ),
    "err.claude_add.no_api_key": (
        "api_key is required in non-interactive mode",
        "非交互模式下必须指定 api_key",
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


# ── rich output ────────────────────────────────────────────────────────


def print_provider_table(rows: list[tuple[str, str, str, str]]) -> None:
    """Print provider list as a rich table."""
    table = Table()
    table.add_column(_("lbl.provider"), style="cyan")
    table.add_column(_("lbl.model_provider"))
    table.add_column(_("lbl.base_url"))
    table.add_column(_("lbl.websocket"))
    for pid, mp, url, ws in rows:
        table.add_row(pid, mp, url, ws)
    console.print(table)


def print_claude_provider_table(rows: list[tuple[str, str, str]]) -> None:
    """Print claude provider list as a rich table."""
    table = Table()
    table.add_column(_("lbl.provider"), style="green")
    table.add_column(_("lbl.base_url"))
    table.add_column(_("lbl.model"))
    for pid, url, model in rows:
        table.add_row(pid, url, model)
    console.print(table)


def print_current_panel(
    provider_id: str,
    model_provider: str,
    model: str,
    review_model: str,
    base_url: str,
    websocket: str,
    auth: str,
) -> None:
    """Print current provider status as a rich panel."""
    from rich.table import Table as GridTable

    grid = GridTable.grid(padding=(0, 2))
    grid.add_column(style="bold")
    grid.add_column()

    def row(label_key: str, value: str) -> None:
        grid.add_row(_(label_key), value)

    row("lbl.provider", provider_id)
    row("lbl.model_provider", model_provider)
    row("lbl.model", model)
    row("lbl.review_model", review_model)
    row("lbl.base_url", base_url)
    row("lbl.websocket", websocket)
    row("lbl.auth", auth)
    console.print(Panel(grid, title="current", border_style="blue"))


def print_claude_current_panel(
    claude_provider: str,
    base_url: str,
    model: str,
    opus: str,
    sonnet: str,
    haiku: str,
    subagent: str,
) -> None:
    """Print current Claude provider as a rich panel."""
    from rich.table import Table as GridTable

    grid = GridTable.grid(padding=(0, 2))
    grid.add_column(style="bold")
    grid.add_column()

    def row(label_key: str, value: str) -> None:
        grid.add_row(_(label_key), value)

    row("lbl.claude_provider", claude_provider)
    row("lbl.base_url", base_url)
    row("lbl.model", model)
    row("lbl.model_opus", opus)
    row("lbl.model_sonnet", sonnet)
    row("lbl.model_haiku", haiku)
    row("lbl.subagent", subagent)
    console.print(Panel(grid, title="claude current", border_style="green"))


def print_status(
    status_text: str,
    provider: str,
    drift_items: list[str] | None = None,
    fix_cmd: str | None = None,
) -> None:
    """Print status with color coding."""
    style = "green" if status_text == "controlled: yes" else ("yellow" if "partial" in status_text else "red")
    console.print(f"[{style}]{status_text}[/]")
    console.print(f"  {_('lbl.provider')}: {provider}")
    if drift_items:
        for d in drift_items:
            console.print(f"  [yellow]{_('status.drift', d)}[/]")
    if fix_cmd:
        console.print(f"  [bold]{fix_cmd}[/]")


def print_diff(diff_text: str) -> None:
    """Print diff with syntax highlighting."""
    if diff_text:
        from rich.syntax import Syntax

        console.print(Syntax(diff_text, "diff", theme="ansi_dark"))

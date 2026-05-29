from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from typing import Callable

import tomlkit

from cxf import __version__
from cxf.claude import (
    _apply_claude_provider,
    _claude_provider_ids,
    _default_deepseek_claude_provider,
    _extract_current_claude_provider,
    _load_claude_provider,
    _write_claude_provider,
)
from cxf.codex import (
    _apply_provider,
    _extract_all_providers,
    _load_provider,
    _provider_drift,
    _provider_ids,
    _read_provider_probe,
    _set_provider_probe,
    _write_provider,
)
from cxf.config import (
    AUTH_PATH,
    CLAUDE_PROVIDER_ENV,
    CLAUDE_PROVIDERS_DIR,
    CLAUDE_SETTINGS_PATH,
    CODEX_CONFIG_PATH,
    CXF_HOME,
    PROVIDERS_DIR,
    _ensure_claude_layout,
    _ensure_layout,
    _is_table_like,
    _load_base,
    _read_auth,
    _read_json,
    _read_toml,
    _write_auth,
    _write_default_base,
    _write_json,
    _write_toml,
)
from cxf.models import ClaudeProvider, Provider
from cxf.ux import (
    _,
    _confirm,
    _error,
    _format_bool,
    _prompt,
    _prompt_bool,
    _warn,
    console,
    print_claude_current_panel,
    print_current_panel,
    print_diff,
    print_provider_table,
    print_status,
)
from cxf.ux import _diff as diff

# ── parser ─────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cxf", description="Codex provider pointer manager.")
    parser.add_argument("--version", action="version", version=f"cxf {__version__}")
    sub = parser.add_subparsers(dest="command")

    # init
    init_p = sub.add_parser("init", help=_("help.init"))
    init_p.add_argument("name", nargs="?", help=_("arg.name"))

    # list
    sub.add_parser("list", help=_("help.list"))

    # current
    sub.add_parser("current", help=_("help.current"))

    # use
    use_p = sub.add_parser("use", help=_("help.use"))
    use_p.add_argument("provider", nargs="?", help=_("arg.provider"))

    # add (supports both interactive and non-interactive)
    add_p = sub.add_parser("add", help=_("help.add"))
    add_p.add_argument("--provider-id", help=_("arg.add.provider_id"))
    add_p.add_argument("--model-providers", help=_("arg.add.model_providers"))
    add_p.add_argument("--base-url", help=_("arg.add.base_url"))
    add_p.add_argument("--api-key", help=_("arg.add.api_key"))
    add_p.add_argument("--wire-api", choices=("responses", "chat"), default=None, help=_("arg.add.wire_api"))
    add_p.add_argument("--no-websocket", action="store_true", help=_("arg.add.no_websocket"))

    # edit
    edit_p = sub.add_parser("edit", help=_("help.edit"))
    edit_p.add_argument("provider", nargs="?", help=_("arg.provider"))
    edit_p.add_argument("-y", "--yes", action="store_true", help=_("arg.yes"))

    # remove
    remove_p = sub.add_parser("remove", help=_("help.remove"))
    remove_p.add_argument("provider", nargs="?", help=_("arg.provider"))
    remove_p.add_argument("-y", "--yes", action="store_true", help=_("arg.yes"))

    # rename
    rename_p = sub.add_parser("rename", help=_("help.rename"))
    rename_p.add_argument("old", help=_("arg.rename.old"))
    rename_p.add_argument("new", help=_("arg.rename.new"))

    # status (was doctor)
    sub.add_parser("status", help=_("help.status"))

    # claude subcommand group
    claude_p = sub.add_parser("claude", help=_("help.claude"))
    claude_sub = claude_p.add_subparsers(dest="claude_command")

    claude_init = claude_sub.add_parser("init", help=_("help.claude_init"))
    claude_init.add_argument("name", nargs="?", help=_("arg.name"))

    claude_sub.add_parser("list", help=_("help.claude_list"))
    claude_sub.add_parser("current", help=_("help.claude_current"))

    claude_use = claude_sub.add_parser("use", help=_("help.claude_use"))
    claude_use.add_argument("provider", nargs="?", help=_("arg.provider"))

    claude_edit = claude_sub.add_parser("edit", help=_("help.claude_edit"))
    claude_edit.add_argument("provider", nargs="?", help=_("arg.provider"))

    claude_add = claude_sub.add_parser("add", help=_("help.claude_add"))
    claude_add.add_argument("--provider-id", help=_("arg.claude_add.provider_id"))
    claude_add.add_argument("--base-url", help=_("arg.claude_add.base_url"))
    claude_add.add_argument("--api-key", help=_("arg.claude_add.api_key"))
    claude_add.add_argument("--model", help=_("arg.claude_add.model"))

    claude_remove = claude_sub.add_parser("remove", help=_("help.claude_remove"))
    claude_remove.add_argument("provider", nargs="?", help=_("arg.provider"))
    claude_remove.add_argument("-y", "--yes", action="store_true", help=_("arg.yes"))

    claude_rename = claude_sub.add_parser("rename", help=_("help.claude_rename"))
    claude_rename.add_argument("old", help=_("arg.rename.old"))
    claude_rename.add_argument("new", help=_("arg.rename.new"))

    claude_sub.add_parser("status", help=_("help.claude_status"))

    return parser


# ── helpers ────────────────────────────────────────────────────────────


def _subcommand_help(name: str) -> None:
    """Print help for a subcommand by looking it up in argparse internals."""
    parser = build_parser()
    for action in parser._actions:
        if hasattr(action, "choices") and action.choices and name in action.choices:
            action.choices[name].print_help()
            break


def _claude_subcommand_help(name: str) -> None:
    """Print help for a claude sub-subcommand."""
    parser = build_parser()
    for action in parser._actions:
        if hasattr(action, "choices") and action.choices and "claude" in action.choices:
            claude_p = action.choices["claude"]
            for ca in claude_p._actions:
                if hasattr(ca, "choices") and ca.choices and name in ca.choices:
                    ca.choices[name].print_help()
                    return
            break


# ── command handlers ───────────────────────────────────────────────────


def _cmd_init(name: str | None) -> int:
    _ensure_layout()
    _write_default_base()
    providers = _extract_all_providers(name)
    for provider in providers:
        _write_provider(provider)
    print(_("msg.initialized", CXF_HOME))
    for provider in providers:
        print(_("msg.provider_line", provider.provider_id, provider.model_providers, provider.base_url))
    return 0


def _cmd_list() -> int:
    _ensure_layout()
    rows: list[tuple[str, str, str, str]] = []
    for provider_id in _provider_ids():
        provider = _load_provider(provider_id)
        ws = "ws" if provider.websocket else "sse"
        rows.append((provider.provider_id, provider.model_providers, provider.base_url, ws))
    print_provider_table(rows)
    return 0


def _cmd_current() -> int:
    raw_config = CODEX_CONFIG_PATH.read_text(encoding="utf-8") if CODEX_CONFIG_PATH.exists() else ""
    config = _read_toml(CODEX_CONFIG_PATH)
    provider_id = _read_provider_probe(raw_config)
    model_provider = config.get("model_provider", "")
    provider_table = config.get("model_providers", {}).get(model_provider, {})
    base = _load_base()
    provider: Provider | None = (
        _load_provider(str(provider_id)) if provider_id and (PROVIDERS_DIR / f"{provider_id}.toml").exists() else None
    )
    auth = _read_auth()
    base_url = provider_table.get("base_url", "") if _is_table_like(provider_table) else ""
    ws_val = provider_table.get("supports_websockets", "") if _is_table_like(provider_table) else ""
    auth_controlled = bool(provider and auth.get("OPENAI_API_KEY") == provider.api_key)

    print_current_panel(
        provider_id=provider_id or "-",
        model_provider=model_provider or "-",
        model=str(config.get("model", base.get("model", "-"))),
        review_model=str(config.get("review_model", base.get("review_model", "-"))),
        base_url=base_url or "-",
        websocket=_format_bool(ws_val),
        auth=_("lbl.controlled") if auth_controlled else _("lbl.unknown"),
    )
    return 0


def _cmd_use(provider_id: str | None) -> int:
    if provider_id is None:
        _subcommand_help("use")
        return 1
    _ensure_layout()
    provider = _load_provider(provider_id)
    base = _load_base()
    before_config = CODEX_CONFIG_PATH.read_text(encoding="utf-8") if CODEX_CONFIG_PATH.exists() else ""
    before_auth = AUTH_PATH.read_text(encoding="utf-8") if AUTH_PATH.exists() else ""
    config = _read_toml(CODEX_CONFIG_PATH)
    config = _apply_provider(config, base, provider)
    after_config = _set_provider_probe(tomlkit.dumps(config), provider.provider_id)
    CODEX_CONFIG_PATH.write_text(after_config, encoding="utf-8")
    CODEX_CONFIG_PATH.chmod(0o600)
    _write_auth(provider.api_key)
    after_auth = AUTH_PATH.read_text(encoding="utf-8")

    config_diff = diff(before_config, after_config, str(CODEX_CONFIG_PATH), str(CODEX_CONFIG_PATH))
    auth_diff = diff(before_auth, after_auth, str(AUTH_PATH), str(AUTH_PATH))
    if config_diff:
        print_diff(config_diff)
    if auth_diff:
        print_diff(auth_diff)
    console.print(_("msg.current", provider.provider_id, provider.model_providers, provider.base_url))
    return 0


def _cmd_add(args: argparse.Namespace) -> int:
    _ensure_layout()
    if args.provider_id:
        # non-interactive mode — use defaults for any flag not explicitly set
        provider_id = args.provider_id
        model_providers = args.model_providers or "OpenAI"
        base_url = args.base_url or ""
        api_key = args.api_key or ""
        wire_api = args.wire_api or "responses"
        websocket = not args.no_websocket
        if not base_url:
            _error("err.add.no_base_url")
        if not api_key:
            _error("err.add.no_api_key")
    else:
        # interactive mode
        provider_id = _prompt("p.provider_id")
        if not provider_id:
            _error("p.provider_id_required")
        model_providers = _prompt("p.model_providers", "OpenAI")
        base_url = _prompt("p.base_url")
        api_key = _prompt("p.api_key")
        wire_api = _prompt("p.wire_api", "responses")
        websocket = _prompt_bool("p.websocket", True)

    provider = Provider(
        provider_id=provider_id,
        model_providers=model_providers,
        base_url=base_url,
        api_key=api_key,
        wire_api=wire_api,
        requires_openai_auth=True,
        websocket=websocket,
    )
    _write_provider(provider)
    print(_("msg.created", provider.path))
    return 0


def _cmd_edit(provider_id: str | None, yes: bool = False) -> int:
    if provider_id is None:
        _subcommand_help("edit")
        return 0
    _ensure_layout()
    target = PROVIDERS_DIR / f"{provider_id}.toml"
    if not target.exists():
        if not _confirm("p.create_provider", provider_id, yes=yes):
            print(_("p.aborted"))
            return 1
        # write a minimal stub with defaults; user will edit in $EDITOR
        stub = tomlkit.document()
        stub.add("model_providers", "OpenAI")
        stub.add("base_url", "")
        stub.add("api_key", "")
        stub.add("wire_api", "responses")
        stub.add("requires_openai_auth", True)
        stub.add("websocket", True)
        _write_toml(target, stub)

    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL")
    if not editor:
        _error("err.editor_not_set")
    result = subprocess.call([editor, str(target)])
    if result != 0:
        return result
    # reload after editing to validate
    edited = _load_provider(provider_id)
    if not edited.api_key:
        _warn("err.edit.no_api_key", provider_id)
        return 1
    return _cmd_use(provider_id)


def _cmd_remove(provider_id: str | None, yes: bool = False) -> int:
    if provider_id is None:
        _subcommand_help("remove")
        return 0
    _ensure_layout()
    path = PROVIDERS_DIR / f"{provider_id}.toml"
    if not path.exists():
        _error("err.not_found", provider_id)
    if not _confirm("p.remove_provider", provider_id, yes=yes):
        print(_("p.aborted"))
        return 1
    path.unlink()
    print(_("msg.removed", provider_id))
    return 0


def _cmd_rename(old: str, new: str) -> int:
    _ensure_layout()
    old_path = PROVIDERS_DIR / f"{old}.toml"
    new_path = PROVIDERS_DIR / f"{new}.toml"
    if not old_path.exists():
        _error("err.rename.not_found", old)
    if new_path.exists():
        _error("err.rename.exists", new)
    old_path.rename(new_path)
    print(_("msg.renamed", old, new))
    return 0


def _cmd_status() -> int:
    raw_config = CODEX_CONFIG_PATH.read_text(encoding="utf-8") if CODEX_CONFIG_PATH.exists() else ""
    config = _read_toml(CODEX_CONFIG_PATH)
    provider_id = _read_provider_probe(raw_config)
    if not provider_id:
        print_status(
            _("status.controlled_no"),
            "-",
            [_("status.reason.missing_probe")],
        )
        return 1
    try:
        provider = _load_provider(provider_id)
    except SystemExit:
        print_status(
            _("status.controlled_no"),
            "-",
            [_("status.reason.missing_file", provider_id)],
        )
        return 1

    auth = _read_auth()
    auth_ok = auth.get("OPENAI_API_KEY") == provider.api_key
    drift = _provider_drift(config, _load_base(), provider)
    provider_label = f"{provider.provider_id} -> {provider.model_providers}"

    if not drift and auth_ok:
        print_status(_("status.controlled_yes"), provider_label)
        return 0

    items: list[str] = list(drift)
    if not auth_ok:
        items.append(_("status.drift_auth"))
    print_status(
        _("status.controlled_partial"),
        provider_label,
        drift_items=items,
        fix_cmd=_("status.fix_use", provider.provider_id),
    )
    return 2


# ── claude command handlers ────────────────────────────────────────────


def _cmd_claude_init(name: str | None) -> int:
    _ensure_claude_layout()
    deepseek_path = CLAUDE_PROVIDERS_DIR / "deepseek.toml"
    if not deepseek_path.exists():
        _write_claude_provider(_default_deepseek_claude_provider())
    current_name = name or "anthropic"
    current_path = CLAUDE_PROVIDERS_DIR / f"{current_name}.toml"
    if not current_path.exists():
        _write_claude_provider(_extract_current_claude_provider(current_name))
    print(_("msg.claude_initialized", CLAUDE_PROVIDERS_DIR.parent))
    for pid in _claude_provider_ids():
        prov = _load_claude_provider(pid)
        print(
            _(
                "msg.claude_provider_line",
                prov.provider_id,
                prov.env.get("ANTHROPIC_BASE_URL", "-"),
                prov.env.get("ANTHROPIC_MODEL", "-"),
            )
        )
    return 0


def _cmd_claude_list() -> int:
    _ensure_claude_layout()
    rows: list[tuple[str, str, str]] = []
    for pid in _claude_provider_ids():
        prov = _load_claude_provider(pid)
        rows.append(
            (
                prov.provider_id,
                prov.env.get("ANTHROPIC_BASE_URL", "-"),
                prov.env.get("ANTHROPIC_MODEL", "-"),
            )
        )
    from cxf.ux import print_claude_provider_table

    print_claude_provider_table(rows)
    return 0


def _cmd_claude_add(args: argparse.Namespace) -> int:
    _ensure_claude_layout()
    if args.provider_id:
        # non-interactive mode
        provider_id = args.provider_id
        base_url = args.base_url or ""
        api_key = args.api_key or ""
        model = args.model or ""
        if not base_url:
            _error("err.claude_add.no_base_url")
        if not api_key:
            _error("err.claude_add.no_api_key")
    else:
        # interactive mode
        provider_id = _prompt("p.claude_provider_id")
        if not provider_id:
            _error("p.provider_id_required")
        base_url = _prompt("p.claude_base_url")
        api_key = _prompt("p.claude_api_key")
        model = _prompt("p.claude_model", "deepseek-v4-flash")

    env = {
        "ANTHROPIC_BASE_URL": base_url,
        "ANTHROPIC_AUTH_TOKEN": api_key,
    }
    if model:
        env["ANTHROPIC_MODEL"] = model
    provider = ClaudeProvider(provider_id=provider_id, env=env)
    _write_claude_provider(provider)
    print(_("msg.created", provider.path))
    return 0


def _cmd_claude_current() -> int:
    settings = _read_json(CLAUDE_SETTINGS_PATH)
    env = settings.get("env", {}) if isinstance(settings.get("env"), dict) else {}

    def v(key: str) -> str:
        val = env.get(key)
        return str(val) if val else "-"

    print_claude_current_panel(
        claude_provider=v(CLAUDE_PROVIDER_ENV),
        base_url=v("ANTHROPIC_BASE_URL"),
        model=v("ANTHROPIC_MODEL") or str(settings.get("model", "-")),
        opus=v("ANTHROPIC_DEFAULT_OPUS_MODEL"),
        sonnet=v("ANTHROPIC_DEFAULT_SONNET_MODEL"),
        haiku=v("ANTHROPIC_DEFAULT_HAIKU_MODEL"),
        subagent=v("CLAUDE_CODE_SUBAGENT_MODEL"),
    )
    return 0


def _cmd_claude_edit(provider_id: str | None) -> int:
    if provider_id is None:
        _claude_subcommand_help("edit")
        return 0
    _ensure_claude_layout()
    target = CLAUDE_PROVIDERS_DIR / f"{provider_id}.toml"
    if not target.exists():
        _write_claude_provider(_extract_current_claude_provider(provider_id))
    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL")
    if not editor:
        _error("err.editor_not_set")
    result = subprocess.call([editor, str(target)])
    if result != 0:
        return result
    # reload after editing to validate
    edited = _load_claude_provider(provider_id)
    token = edited.env.get("ANTHROPIC_AUTH_TOKEN", "")
    if not token:
        _warn("err.claude_edit.no_key", provider_id)
        return 1
    return _cmd_claude_use(provider_id)


def _cmd_claude_use(provider_id: str | None) -> int:
    if provider_id is None:
        _claude_subcommand_help("use")
        return 1
    _ensure_claude_layout()
    provider = _load_claude_provider(provider_id)
    before = CLAUDE_SETTINGS_PATH.read_text(encoding="utf-8") if CLAUDE_SETTINGS_PATH.exists() else ""
    settings = _read_json(CLAUDE_SETTINGS_PATH)
    after_doc = _apply_claude_provider(settings, provider)
    after = json.dumps(after_doc, ensure_ascii=False, indent=2) + "\n"
    _write_json(CLAUDE_SETTINGS_PATH, after_doc)
    d = diff(
        before,
        after,
        str(CLAUDE_SETTINGS_PATH),
        str(CLAUDE_SETTINGS_PATH),
    )
    if d:
        print(d, end="")
    print(
        _(
            "msg.claude_current",
            provider.provider_id,
            provider.env.get("ANTHROPIC_BASE_URL", "-"),
            provider.env.get("ANTHROPIC_MODEL", "-"),
        )
    )
    return 0


def _cmd_claude_remove(provider_id: str | None, yes: bool = False) -> int:
    if provider_id is None:
        _claude_subcommand_help("remove")
        return 0
    _ensure_claude_layout()
    path = CLAUDE_PROVIDERS_DIR / f"{provider_id}.toml"
    if not path.exists():
        _error("err.claude_not_found", provider_id)
    if not _confirm("p.remove_claude_provider", provider_id, yes=yes):
        print(_("p.aborted"))
        return 1
    path.unlink()
    print(_("msg.removed", provider_id))
    return 0


def _cmd_claude_rename(old: str, new: str) -> int:
    _ensure_claude_layout()
    old_path = CLAUDE_PROVIDERS_DIR / f"{old}.toml"
    new_path = CLAUDE_PROVIDERS_DIR / f"{new}.toml"
    if not old_path.exists():
        _error("err.claude_rename.not_found", old)
    if new_path.exists():
        _error("err.claude_rename.exists", new)
    old_path.rename(new_path)
    print(_("msg.renamed", old, new))
    return 0


def _cmd_claude_status() -> int:
    settings = _read_json(CLAUDE_SETTINGS_PATH)
    env = settings.get("env", {}) if isinstance(settings.get("env"), dict) else {}
    provider_id = str(env.get(CLAUDE_PROVIDER_ENV, ""))
    if not provider_id:
        print_status(
            _("status.controlled_no"),
            "-",
            [_("status.reason.missing_claude_env")],
        )
        return 1
    try:
        provider = _load_claude_provider(provider_id)
    except SystemExit:
        print_status(
            _("status.controlled_no"),
            "-",
            [_("status.reason.missing_claude_file", provider_id)],
        )
        return 1
    drift = [key for key, value in provider.env.items() if value and env.get(key) != value]
    provider_label = f"{provider.provider_id} -> {provider.env.get('ANTHROPIC_BASE_URL', '-')}"
    if not drift:
        print_status(_("status.controlled_yes"), provider_label)
        return 0
    print_status(
        _("status.controlled_partial"),
        provider_label,
        drift_items=[f"env.{k}" for k in drift],
        fix_cmd=_("status.fix_claude_use", provider.provider_id),
    )
    return 2


# ── dispatch ───────────────────────────────────────────────────────────

_CODEX_COMMANDS: dict[str, Callable[..., int]] = {
    "init": lambda args: _cmd_init(args.name),
    "list": lambda _: _cmd_list(),
    "current": lambda _: _cmd_current(),
    "use": lambda args: _cmd_use(args.provider),
    "add": lambda args: _cmd_add(args),
    "edit": lambda args: _cmd_edit(args.provider, args.yes),
    "remove": lambda args: _cmd_remove(args.provider, args.yes),
    "rename": lambda args: _cmd_rename(args.old, args.new),
    "status": lambda _: _cmd_status(),
}

_CLAUDE_COMMANDS: dict[str, Callable[..., int]] = {
    "init": lambda args: _cmd_claude_init(args.name),
    "list": lambda _: _cmd_claude_list(),
    "current": lambda _: _cmd_claude_current(),
    "add": lambda args: _cmd_claude_add(args),
    "use": lambda args: _cmd_claude_use(args.provider),
    "edit": lambda args: _cmd_claude_edit(args.provider),
    "remove": lambda args: _cmd_claude_remove(args.provider, args.yes),
    "rename": lambda args: _cmd_claude_rename(args.old, args.new),
    "status": lambda _: _cmd_claude_status(),
}


def _reject_extra_args(args: argparse.Namespace) -> bool:
    extra = getattr(args, "extra", None)
    if extra:
        print(f"cxf: error: {_('err.unexpected_argument', extra[0])}", file=sys.stderr)
        return True
    return False


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args, extra = parser.parse_known_args(argv)
    args.extra = extra
    if _reject_extra_args(args):
        return 2

    if not args.command:
        parser.print_help()
        return 0

    if args.command == "claude":
        if not args.claude_command:
            # show claude subcommand help
            parser = build_parser()
            # access the claude subparser via argparse internals
            actions = [a for a in parser._actions if hasattr(a, "choices") and a.choices]
            for action in actions:
                if "claude" in action.choices:
                    action.choices["claude"].print_help()
                    break
            return 0
        handler = _CLAUDE_COMMANDS.get(args.claude_command)
        if handler is None:
            _error("err.unknown_claude_command", args.claude_command)
        return handler(args)
    else:
        handler = _CODEX_COMMANDS.get(args.command)
        if handler is None:
            _error("err.unknown_command", args.command)
        return handler(args)


if __name__ == "__main__":
    raise SystemExit(main())

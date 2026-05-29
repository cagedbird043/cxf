from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

import tomlkit

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
)
from cxf.models import Provider
from cxf.ux import _, _confirm, _error, _format_bool, _prompt, _prompt_bool
from cxf.ux import _diff as diff
from cxf.ux import _redact_claude_settings as redact_claude_settings
from cxf.ux import _redact_key as redact_key

# ── parser ─────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cxf", description="Codex provider pointer manager.")
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
    use_p.add_argument("provider", help=_("arg.provider"))

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
    remove_p.add_argument("provider", help=_("arg.provider"))
    remove_p.add_argument("-y", "--yes", action="store_true", help=_("arg.yes"))

    # status (was doctor)
    sub.add_parser("status", help=_("help.status"))

    # claude subcommand group
    claude_p = sub.add_parser("claude", help=_("help.claude"))
    claude_sub = claude_p.add_subparsers(dest="claude_command", required=True)

    claude_init = claude_sub.add_parser("init", help=_("help.claude_init"))
    claude_init.add_argument("name", nargs="?", help=_("arg.name"))

    claude_sub.add_parser("list", help=_("help.claude_list"))
    claude_sub.add_parser("current", help=_("help.claude_current"))

    claude_use = claude_sub.add_parser("use", help=_("help.claude_use"))
    claude_use.add_argument("provider", help=_("arg.provider"))

    claude_edit = claude_sub.add_parser("edit", help=_("help.claude_edit"))
    claude_edit.add_argument("provider", nargs="?", help=_("arg.provider"))

    claude_remove = claude_sub.add_parser("remove", help=_("help.claude_remove"))
    claude_remove.add_argument("provider", help=_("arg.provider"))
    claude_remove.add_argument("-y", "--yes", action="store_true", help=_("arg.yes"))

    claude_sub.add_parser("status", help=_("help.claude_status"))

    return parser


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
    for provider_id in _provider_ids():
        provider = _load_provider(provider_id)
        ws = "ws" if provider.websocket else "sse"
        print(f"{provider.provider_id}\t{provider.model_providers}\t{provider.base_url}\t{ws}")
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

    print(f"{_('lbl.provider')}: {provider_id or '-'}")
    print(f"{_('lbl.model_provider')}: {model_provider or '-'}")
    print(f"{_('lbl.model')}: {config.get('model', base.get('model', '-'))}")
    print(f"{_('lbl.review_model')}: {config.get('review_model', base.get('review_model', '-'))}")
    print(f"{_('lbl.base_url')}: {base_url or '-'}")
    print(f"{_('lbl.websocket')}: {_format_bool(ws_val)}")
    print(f"{_('lbl.auth')}: {_('lbl.controlled') if auth_controlled else _('lbl.unknown')}")
    return 0


def _cmd_use(provider_id: str) -> int:
    _ensure_layout()
    provider = _load_provider(provider_id)
    base = _load_base()
    before_config = CODEX_CONFIG_PATH.read_text(encoding="utf-8") if CODEX_CONFIG_PATH.exists() else ""
    before_auth = AUTH_PATH.read_text(encoding="utf-8") if AUTH_PATH.exists() else ""
    config = _read_toml(CODEX_CONFIG_PATH)
    config = _apply_provider(config, base, provider)
    after_config = _set_provider_probe(tomlkit.dumps(config), provider.provider_id)
    CODEX_CONFIG_PATH.write_text(after_config, encoding="utf-8")
    _write_auth(provider.api_key)
    after_auth = AUTH_PATH.read_text(encoding="utf-8")

    config_diff = diff(before_config, after_config, str(CODEX_CONFIG_PATH), str(CODEX_CONFIG_PATH))
    auth_diff = diff(redact_key(before_auth), redact_key(after_auth), str(AUTH_PATH), str(AUTH_PATH))
    if config_diff:
        print(config_diff, end="")
    if auth_diff:
        print(auth_diff, end="")
    print(_("msg.current", provider.provider_id, provider.model_providers, provider.base_url))
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
    else:
        # interactive mode
        provider_id = _prompt("p.provider_id")
        if not provider_id:
            _error("p.provider_id_required")
        model_providers = _prompt("p.model_providers", "OpenAI")
        base_url = _prompt("p.base_url")
        api_key = _prompt("p.api_key", secret=True)
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
    _ensure_layout()
    if provider_id:
        target = PROVIDERS_DIR / f"{provider_id}.toml"
        if not target.exists():
            if not _confirm("p.create_provider", provider_id, yes=yes):
                print(_("p.aborted"))
                return 1
            _write_provider(
                Provider(
                    provider_id=provider_id,
                    model_providers=_prompt("p.model_providers", "OpenAI"),
                    base_url=_prompt("p.base_url"),
                    api_key=_prompt("p.api_key", secret=True),
                    wire_api=_prompt("p.wire_api", "responses"),
                    requires_openai_auth=True,
                    websocket=_prompt_bool("p.websocket", True),
                )
            )
    else:
        target = CXF_HOME

    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL")
    if not editor:
        _error("err.editor_not_set")
    result = subprocess.call([editor, str(target)])
    if result != 0 or not provider_id:
        return result
    return _cmd_use(provider_id)


def _cmd_remove(provider_id: str, yes: bool = False) -> int:
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


def _cmd_status() -> int:
    raw_config = CODEX_CONFIG_PATH.read_text(encoding="utf-8") if CODEX_CONFIG_PATH.exists() else ""
    config = _read_toml(CODEX_CONFIG_PATH)
    provider_id = _read_provider_probe(raw_config)
    if not provider_id:
        print(_("status.controlled_no"))
        print(f"  reason: {_('status.reason.missing_probe')}")
        return 1
    try:
        provider = _load_provider(provider_id)
    except SystemExit:
        print(_("status.controlled_no"))
        print(f"  reason: {_('status.reason.missing_file', provider_id)}")
        return 1

    auth = _read_auth()
    auth_ok = auth.get("OPENAI_API_KEY") == provider.api_key
    drift = _provider_drift(config, _load_base(), provider)
    if not drift and auth_ok:
        print(_("status.controlled_yes"))
        print(f"  {_('lbl.provider')}: {provider.provider_id} -> {provider.model_providers}")
        return 0
    print(_("status.controlled_partial"))
    print(f"  {_('lbl.provider')}: {provider.provider_id} -> {provider.model_providers}")
    for key in drift:
        print(f"  {_('status.drift', key)}")
    if not auth_ok:
        print(f"  {_('status.drift_auth')}")
    print(f"  {_('status.fix_use', provider.provider_id)}")
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
    for pid in _claude_provider_ids():
        prov = _load_claude_provider(pid)
        print(f"{prov.provider_id}\t{prov.env.get('ANTHROPIC_BASE_URL', '-')}\t{prov.env.get('ANTHROPIC_MODEL', '-')}")
    return 0


def _cmd_claude_current() -> int:
    settings = _read_json(CLAUDE_SETTINGS_PATH)
    env = settings.get("env", {}) if isinstance(settings.get("env"), dict) else {}

    def v(key: str) -> str:
        val = env.get(key)
        return str(val) if val else "-"

    print(f"{_('lbl.claude_provider')}: {v(CLAUDE_PROVIDER_ENV)}")
    print(f"{_('lbl.base_url')}: {v('ANTHROPIC_BASE_URL')}")
    print(f"{_('lbl.model')}: {v('ANTHROPIC_MODEL') or settings.get('model', '-')}")
    print(f"{_('lbl.model_opus')}: {v('ANTHROPIC_DEFAULT_OPUS_MODEL')}")
    print(f"{_('lbl.model_sonnet')}: {v('ANTHROPIC_DEFAULT_SONNET_MODEL')}")
    print(f"{_('lbl.model_haiku')}: {v('ANTHROPIC_DEFAULT_HAIKU_MODEL')}")
    print(f"{_('lbl.subagent')}: {v('CLAUDE_CODE_SUBAGENT_MODEL')}")
    return 0


def _cmd_claude_edit(provider_id: str | None) -> int:
    _ensure_claude_layout()
    if provider_id:
        target = CLAUDE_PROVIDERS_DIR / f"{provider_id}.toml"
        if not target.exists():
            _write_claude_provider(_extract_current_claude_provider(provider_id))
    else:
        target = CLAUDE_PROVIDERS_DIR.parent
    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL")
    if not editor:
        _error("err.editor_not_set")
    result = subprocess.call([editor, str(target)])
    if result != 0 or not provider_id:
        return result
    return _cmd_claude_use(provider_id)


def _cmd_claude_use(provider_id: str) -> int:
    _ensure_claude_layout()
    provider = _load_claude_provider(provider_id)
    before = CLAUDE_SETTINGS_PATH.read_text(encoding="utf-8") if CLAUDE_SETTINGS_PATH.exists() else ""
    settings = _read_json(CLAUDE_SETTINGS_PATH)
    after_doc = _apply_claude_provider(settings, provider)
    after = json.dumps(after_doc, ensure_ascii=False, indent=2) + "\n"
    _write_json(CLAUDE_SETTINGS_PATH, after_doc)
    d = diff(redact_claude_settings(before), redact_claude_settings(after), str(CLAUDE_SETTINGS_PATH), str(CLAUDE_SETTINGS_PATH))
    if d:
        print(d, end="")
    print(_("msg.claude_current", provider.provider_id, provider.env.get("ANTHROPIC_BASE_URL", "-"), provider.env.get("ANTHROPIC_MODEL", "-")))
    return 0


def _cmd_claude_remove(provider_id: str, yes: bool = False) -> int:
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


def _cmd_claude_status() -> int:
    settings = _read_json(CLAUDE_SETTINGS_PATH)
    env = settings.get("env", {}) if isinstance(settings.get("env"), dict) else {}
    provider_id = str(env.get(CLAUDE_PROVIDER_ENV, ""))
    if not provider_id:
        print(_("status.controlled_no"))
        print(f"  reason: {_('status.reason.missing_claude_env')}")
        return 1
    try:
        provider = _load_claude_provider(provider_id)
    except SystemExit:
        print(_("status.controlled_no"))
        print(f"  reason: {_('status.reason.missing_claude_file', provider_id)}")
        return 1
    drift = [key for key, value in provider.env.items() if value and env.get(key) != value]
    if not drift:
        print(_("status.controlled_yes"))
        print(f"  {_('lbl.claude_provider')}: {provider.provider_id} -> {provider.env.get('ANTHROPIC_BASE_URL', '-')}")
        return 0
    print(_("status.controlled_partial"))
    print(f"  {_('lbl.claude_provider')}: {provider.provider_id} -> {provider.env.get('ANTHROPIC_BASE_URL', '-')}")
    for key in drift:
        print(f"  {_('status.drift', f'env.{key}')}")
    print(f"  {_('status.fix_claude_use', provider.provider_id)}")
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
    "status": lambda _: _cmd_status(),
}

_CLAUDE_COMMANDS: dict[str, Callable[..., int]] = {
    "init": lambda args: _cmd_claude_init(args.name),
    "list": lambda _: _cmd_claude_list(),
    "current": lambda _: _cmd_claude_current(),
    "use": lambda args: _cmd_claude_use(args.provider),
    "edit": lambda args: _cmd_claude_edit(args.provider),
    "remove": lambda args: _cmd_claude_remove(args.provider, args.yes),
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

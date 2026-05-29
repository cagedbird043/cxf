from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from importlib.resources import files
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
    _extract_current_provider,
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
    SNAPSHOTS_DIR,
    _diff,
    _ensure_claude_layout,
    _ensure_layout,
    _format_bool,
    _is_table_like,
    _latest_snapshot,
    _load_base,
    _prompt,
    _prompt_bool,
    _read_auth,
    _read_json,
    _read_toml,
    _redact_claude_settings,
    _redact_key,
    _snapshot_path,
    _write_auth,
    _write_default_base,
    _write_json,
)
from cxf.models import Provider

# ── parser ─────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cxf", description="Codex provider pointer manager.")
    sub = parser.add_subparsers(dest="command", required=True)

    init_parser = sub.add_parser("init", help="Initialize ~/.codex/cxf from existing Codex providers.")
    init_parser.add_argument("name", nargs="?", help="Provider id for the current Codex provider.")

    for command, help_text in (
        ("add", "Interactively add a provider."),
        ("list", "List managed providers."),
        ("current", "Show current managed provider pointer."),
        ("doctor", "Check whether the provider pointer is still controlled by cxf."),
        ("snapshot", "Snapshot Codex and cxf config files."),
    ):
        sub.add_parser(command, help=help_text)

    edit_parser = sub.add_parser("edit", help="Open a provider file in $EDITOR.")
    edit_parser.add_argument("provider", nargs="?", help="Provider id. Opens the cxf directory when omitted.")

    use_parser = sub.add_parser("use", help="Switch Codex to a managed provider.")
    use_parser.add_argument("provider", help="Provider id.")

    restore_parser = sub.add_parser("restore", help="Restore a snapshot.")
    restore_parser.add_argument("snapshot", nargs="?", help="Snapshot name. Defaults to latest.")

    completion_parser = sub.add_parser("completion", help="Print shell completion.")
    completion_parser.add_argument("shell", choices=("zsh",))

    claude_parser = sub.add_parser("claude", help="Manage Claude Code provider pointer.")
    claude_sub = claude_parser.add_subparsers(dest="claude_command", required=True)
    claude_init = claude_sub.add_parser("init", help="Initialize Claude providers from current settings plus DeepSeek default.")
    claude_init.add_argument("name", nargs="?", help="Provider id for current Claude settings.")
    for command, help_text in (
        ("list", "List managed Claude providers."),
        ("current", "Show current Claude provider pointer."),
        ("doctor", "Check whether Claude settings are controlled by cxf."),
    ):
        claude_sub.add_parser(command, help=help_text)
    claude_edit = claude_sub.add_parser("edit", help="Open a Claude provider file in $EDITOR.")
    claude_edit.add_argument("provider", nargs="?", help="Provider id. Opens the Claude cxf directory when omitted.")
    claude_use = claude_sub.add_parser("use", help="Switch Claude Code to a managed provider.")
    claude_use.add_argument("provider", help="Provider id.")

    return parser


# ── command handlers ───────────────────────────────────────────────────


def _cmd_init(name: str | None) -> int:
    _ensure_layout()
    _write_default_base()
    providers = _extract_all_providers(name)
    for provider in providers:
        _write_provider(provider)
    print(f"initialized: {CXF_HOME}")
    for provider in providers:
        print(f"provider: {provider.provider_id} -> {provider.model_providers} {provider.base_url}")
    return 0


def _cmd_add() -> int:
    _ensure_layout()
    provider_id = _prompt("provider id")
    if not provider_id:
        raise SystemExit("provider id is required")
    provider = Provider(
        provider_id=provider_id,
        model_providers=_prompt("model_providers", "OpenAI"),
        base_url=_prompt("base_url"),
        api_key=_prompt("api_key", secret=True),
        wire_api=_prompt("wire_api", "responses"),
        requires_openai_auth=_prompt_bool("requires_openai_auth", True),
        websocket=_prompt_bool("websocket", True),
    )
    _write_provider(provider)
    print(provider.path)
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
    provider = _load_provider(str(provider_id)) if provider_id and (PROVIDERS_DIR / f"{provider_id}.toml").exists() else None
    auth = _read_auth()
    base_url = provider_table.get("base_url", "") if _is_table_like(provider_table) else ""
    websocket = provider_table.get("supports_websockets", "") if _is_table_like(provider_table) else ""
    auth_controlled = bool(provider and auth.get("OPENAI_API_KEY") == provider.api_key)
    print(f"provider: {provider_id or '-'}")
    print(f"model_provider: {model_provider or '-'}")
    print(f"model: {config.get('model', base.get('model', '-'))}")
    print(f"review_model: {config.get('review_model', base.get('review_model', '-'))}")
    print(f"base_url: {base_url or '-'}")
    print(f"websocket: {_format_bool(websocket)}")
    print(f"auth: {'controlled' if auth_controlled else 'unknown'}")
    return 0


def _cmd_edit(provider_id: str | None) -> int:
    _ensure_layout()
    if provider_id:
        target = PROVIDERS_DIR / f"{provider_id}.toml"
        if not target.exists():
            ans = _prompt(f"provider '{provider_id}' does not exist. Create it?", default="n")
            if ans.lower() not in ("y", "yes"):
                print("aborted")
                return 1
            _write_provider(
                Provider(
                    provider_id=provider_id,
                    model_providers=_prompt("model_providers", "OpenAI"),
                    base_url=_prompt("base_url"),
                    api_key=_prompt("api_key", secret=True),
                    wire_api=_prompt("wire_api", "responses"),
                    requires_openai_auth=_prompt_bool("requires_openai_auth", True),
                    websocket=_prompt_bool("websocket", True),
                )
            )
    else:
        target = CXF_HOME

    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL")
    if not editor:
        raise SystemExit("EDITOR is not set")
    result = subprocess.call([editor, str(target)])
    if result != 0 or not provider_id:
        return result
    return _cmd_use(provider_id)


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

    # only write auth if key actually changed
    existing_auth = _read_auth()
    if existing_auth.get("OPENAI_API_KEY") != provider.api_key:
        _write_auth(provider.api_key)

    after_auth = AUTH_PATH.read_text(encoding="utf-8")

    config_diff = _diff(before_config, after_config, str(CODEX_CONFIG_PATH), str(CODEX_CONFIG_PATH))
    auth_diff = _diff(_redact_key(before_auth), _redact_key(after_auth), str(AUTH_PATH), str(AUTH_PATH))
    if config_diff:
        print(config_diff, end="")
    if auth_diff:
        print(auth_diff, end="")
    print(f"current: {provider.provider_id} -> {provider.model_providers} {provider.base_url}")
    return 0


def _cmd_doctor() -> int:
    raw_config = CODEX_CONFIG_PATH.read_text(encoding="utf-8") if CODEX_CONFIG_PATH.exists() else ""
    config = _read_toml(CODEX_CONFIG_PATH)
    provider_id = _read_provider_probe(raw_config)
    if not provider_id:
        print("controlled: no")
        print("reason: cxf provider comment is missing")
        return 1
    try:
        provider = _load_provider(provider_id)
    except SystemExit:
        print("controlled: no")
        print(f"reason: provider file is missing: {provider_id}")
        return 1

    auth = _read_auth()
    auth_ok = auth.get("OPENAI_API_KEY") == provider.api_key
    drift = _provider_drift(config, _load_base(), provider)
    if not drift and auth_ok:
        print("controlled: yes")
        print(f"provider: {provider.provider_id} -> {provider.model_providers}")
        return 0
    print("controlled: partial")
    print(f"provider: {provider.provider_id} -> {provider.model_providers}")
    for key in drift:
        print(f"drift: {key}")
    if not auth_ok:
        print("drift: auth OPENAI_API_KEY")
    print("fix: cxf use " + provider.provider_id)
    return 2


def _cmd_snapshot() -> int:
    target = _snapshot_path()
    for path in (CODEX_CONFIG_PATH, AUTH_PATH):
        if path.exists():
            shutil.copy2(path, target / path.name)
    if CXF_HOME.exists():
        shutil.copytree(CXF_HOME, target / "cxf", ignore=shutil.ignore_patterns("snapshots"))
    print(target)
    return 0


def _cmd_restore(snapshot: str | None) -> int:
    target = _latest_snapshot() if snapshot is None else SNAPSHOTS_DIR / snapshot
    if not target.exists():
        raise SystemExit(f"snapshot not found: {target}")
    if (target / "config.toml").exists():
        shutil.copy2(target / "config.toml", CODEX_CONFIG_PATH)
    if (target / "auth.json").exists():
        shutil.copy2(target / "auth.json", AUTH_PATH)
    if (target / "cxf").exists():
        if CXF_HOME.exists():
            shutil.rmtree(CXF_HOME)
        shutil.copytree(target / "cxf", CXF_HOME, ignore=shutil.ignore_patterns("snapshots"))
    print(target)
    return 0


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
    print(f"initialized: {CLAUDE_PROVIDERS_DIR.parent}")
    for provider_id in _claude_provider_ids():
        provider = _load_claude_provider(provider_id)
        print(f"claude provider: {provider.provider_id} -> {provider.env.get('ANTHROPIC_BASE_URL', '-')} {provider.env.get('ANTHROPIC_MODEL', '-')}")
    return 0


def _cmd_claude_list() -> int:
    _ensure_claude_layout()
    for provider_id in _claude_provider_ids():
        provider = _load_claude_provider(provider_id)
        print(f"{provider.provider_id}\t{provider.env.get('ANTHROPIC_BASE_URL', '-')}\t{provider.env.get('ANTHROPIC_MODEL', '-')}")
    return 0


def _cmd_claude_current() -> int:
    settings = _read_json(CLAUDE_SETTINGS_PATH)
    env = settings.get("env", {}) if isinstance(settings.get("env"), dict) else {}
    print(f"claude_provider: {env.get(CLAUDE_PROVIDER_ENV, '-') or '-'}")
    print(f"base_url: {env.get('ANTHROPIC_BASE_URL', '-') or '-'}")
    print(f"model: {env.get('ANTHROPIC_MODEL', settings.get('model', '-')) or '-'}")
    print(f"opus: {env.get('ANTHROPIC_DEFAULT_OPUS_MODEL', '-') or '-'}")
    print(f"sonnet: {env.get('ANTHROPIC_DEFAULT_SONNET_MODEL', '-') or '-'}")
    print(f"haiku: {env.get('ANTHROPIC_DEFAULT_HAIKU_MODEL', '-') or '-'}")
    print(f"subagent: {env.get('CLAUDE_CODE_SUBAGENT_MODEL', '-') or '-'}")
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
        raise SystemExit("EDITOR is not set")
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
    diff = _diff(_redact_claude_settings(before), _redact_claude_settings(after), str(CLAUDE_SETTINGS_PATH), str(CLAUDE_SETTINGS_PATH))
    if diff:
        print(diff, end="")
    print(f"claude current: {provider.provider_id} -> {provider.env.get('ANTHROPIC_BASE_URL', '-')} {provider.env.get('ANTHROPIC_MODEL', '-')}")
    return 0


def _cmd_claude_doctor() -> int:
    settings = _read_json(CLAUDE_SETTINGS_PATH)
    env = settings.get("env", {}) if isinstance(settings.get("env"), dict) else {}
    provider_id = str(env.get(CLAUDE_PROVIDER_ENV, ""))
    if not provider_id:
        print("controlled: no")
        print(f"reason: env.{CLAUDE_PROVIDER_ENV} is missing")
        return 1
    try:
        provider = _load_claude_provider(provider_id)
    except SystemExit:
        print("controlled: no")
        print(f"reason: claude provider file is missing: {provider_id}")
        return 1
    drift = [key for key, value in provider.env.items() if value and env.get(key) != value]
    if not drift:
        print("controlled: yes")
        print(f"claude provider: {provider.provider_id} -> {provider.env.get('ANTHROPIC_BASE_URL', '-')}")
        return 0
    print("controlled: partial")
    print(f"claude provider: {provider.provider_id} -> {provider.env.get('ANTHROPIC_BASE_URL', '-')}")
    for key in drift:
        print(f"drift: env.{key}")
    print("fix: cxf claude use " + provider.provider_id)
    return 2


def _cmd_completion(shell: str) -> int:
    if shell != "zsh":
        raise SystemExit(f"unsupported shell: {shell}")
    print(files("cxf").joinpath("completions/_cxf").read_text(), end="")
    return 0


# ── dispatch ───────────────────────────────────────────────────────────

_CODEX_COMMANDS: dict[str, Callable[..., int]] = {
    "init": lambda args: _cmd_init(args.name),
    "add": lambda _: _cmd_add(),
    "list": lambda _: _cmd_list(),
    "current": lambda _: _cmd_current(),
    "edit": lambda args: _cmd_edit(args.provider),
    "use": lambda args: _cmd_use(args.provider),
    "doctor": lambda _: _cmd_doctor(),
    "snapshot": lambda _: _cmd_snapshot(),
    "restore": lambda args: _cmd_restore(args.snapshot),
    "completion": lambda args: _cmd_completion(args.shell),
}

_CLAUDE_COMMANDS: dict[str, Callable[..., int]] = {
    "init": lambda args: _cmd_claude_init(args.name),
    "list": lambda _: _cmd_claude_list(),
    "current": lambda _: _cmd_claude_current(),
    "edit": lambda args: _cmd_claude_edit(args.provider),
    "use": lambda args: _cmd_claude_use(args.provider),
    "doctor": lambda _: _cmd_claude_doctor(),
}


def _reject_extra_args(args: argparse.Namespace) -> bool:
    extra = getattr(args, "extra", None)
    if extra:
        print(f"error: unexpected argument: {extra[0]}", file=sys.stderr)
        return True
    return False


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args, extra = parser.parse_known_args(argv)
    args.extra = extra
    if _reject_extra_args(args):
        return 2

    if args.command == "claude":
        handler = _CLAUDE_COMMANDS.get(args.claude_command)
        if handler is None:
            raise SystemExit(f"unknown claude command: {args.claude_command}")
        return handler(args)
    else:
        handler = _CODEX_COMMANDS.get(args.command)
        if handler is None:
            raise SystemExit(f"unknown command: {args.command}")
        return handler(args)


if __name__ == "__main__":
    raise SystemExit(main())

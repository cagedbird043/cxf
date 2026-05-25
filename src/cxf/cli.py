from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import shutil
import subprocess
from importlib.resources import files
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import tomlkit
from tomlkit.items import Table


CODEX_HOME = Path.home() / ".codex"
CXF_HOME = CODEX_HOME / "cxf"
PROVIDERS_DIR = CXF_HOME / "providers"
SNAPSHOTS_DIR = CXF_HOME / "snapshots"
BASE_PATH = CXF_HOME / "base.toml"
CODEX_CONFIG_PATH = CODEX_HOME / "config.toml"
AUTH_PATH = CODEX_HOME / "auth.json"
CLAUDE_HOME = Path.home() / ".claude"
CLAUDE_SETTINGS_PATH = CLAUDE_HOME / "settings.json"
CLAUDE_CXF_HOME = CXF_HOME / "claude"
CLAUDE_PROVIDERS_DIR = CLAUDE_CXF_HOME / "providers"
CLAUDE_PROVIDER_ENV = "CXF_CLAUDE_PROVIDER"

BASE_KEYS = (
    "model",
    "review_model",
    "model_reasoning_effort",
    "model_context_window",
    "model_auto_compact_token_limit",
)

PROBE_PREFIX = "# cxf: provider = "


@dataclass(frozen=True)
class Provider:
    provider_id: str
    model_providers: str
    base_url: str
    api_key: str
    wire_api: str
    requires_openai_auth: bool
    websocket: bool

    @property
    def path(self) -> Path:
        return PROVIDERS_DIR / f"{self.provider_id}.toml"


@dataclass(frozen=True)
class ClaudeProvider:
    provider_id: str
    env: dict[str, str]

    @property
    def path(self) -> Path:
        return CLAUDE_PROVIDERS_DIR / f"{self.provider_id}.toml"


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


def _read_toml(path: Path) -> Any:
    if not path.exists():
        return tomlkit.document()
    return tomlkit.parse(path.read_text())


def _is_table_like(value: Any) -> bool:
    return hasattr(value, "get") and hasattr(value, "items")


def _write_toml(path: Path, doc: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(tomlkit.dumps(doc))


def _read_provider_probe(text: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if line.startswith(PROBE_PREFIX):
            return line[len(PROBE_PREFIX) :].strip()
    return ""


def _set_provider_probe(text: str, provider_id: str) -> str:
    lines = [line for line in text.splitlines() if not line.strip().startswith(PROBE_PREFIX)]
    probe = f"{PROBE_PREFIX}{provider_id}"
    if lines and lines[0].startswith("#:schema"):
        lines.insert(1, probe)
    else:
        lines.insert(0, probe)
    return "\n".join(lines) + "\n"


def _prompt(name: str, default: str | None = None, secret: bool = False) -> str:
    suffix = f" [{default}]" if default is not None else ""
    try:
        value = input(f"{name}{suffix}: ").strip()
    except (KeyboardInterrupt, EOFError):
        raise SystemExit("\ncancelled")
    if not value and default is not None:
        return default
    if not value and secret:
        return ""
    return value


def _prompt_bool(name: str, default: bool) -> bool:
    default_text = "yes" if default else "no"
    value = _prompt(name, default_text).lower()
    return value in {"y", "yes", "true", "1", "on"}


def _ensure_layout() -> None:
    PROVIDERS_DIR.mkdir(parents=True, exist_ok=True)
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)


def _load_base() -> Any:
    return _read_toml(BASE_PATH)


def _load_provider(provider_id: str) -> Provider:
    path = PROVIDERS_DIR / f"{provider_id}.toml"
    if not path.exists():
        raise SystemExit(f"provider not found: {provider_id}")
    doc = _read_toml(path)
    return Provider(
        provider_id=provider_id,
        model_providers=str(doc.get("model_providers", "OpenAI")),
        base_url=str(doc.get("base_url", "")),
        api_key=str(doc.get("api_key", "")),
        wire_api=str(doc.get("wire_api", "responses")),
        requires_openai_auth=bool(doc.get("requires_openai_auth", True)),
        websocket=bool(doc.get("websocket", True)),
    )


def _provider_ids() -> list[str]:
    if not PROVIDERS_DIR.exists():
        return []
    return sorted(path.stem for path in PROVIDERS_DIR.glob("*.toml") if path.is_file())


def _managed_model_provider_names() -> set[str]:
    names: set[str] = set()
    for provider_id in _provider_ids():
        try:
            names.add(_load_provider(provider_id).model_providers)
        except Exception:
            continue
    return names


def _provider_doc(provider: Provider) -> Any:
    doc = tomlkit.document()
    doc.add("model_providers", provider.model_providers)
    doc.add("base_url", provider.base_url)
    doc.add("api_key", provider.api_key)
    doc.add("wire_api", provider.wire_api)
    doc.add("requires_openai_auth", provider.requires_openai_auth)
    doc.add("websocket", provider.websocket)
    return doc


def _write_provider(provider: Provider) -> None:
    _write_toml(provider.path, _provider_doc(provider))


def _extract_current_provider(name: str) -> Provider:
    config = _read_toml(CODEX_CONFIG_PATH)
    model_provider = str(config.get("model_provider", "OpenAI"))
    providers = config.get("model_providers", {})
    provider_table = providers.get(model_provider, {}) if _is_table_like(providers) else {}
    auth = _read_auth()
    return Provider(
        provider_id=name,
        model_providers=model_provider,
        base_url=str(provider_table.get("base_url", "")),
        api_key=str(auth.get("OPENAI_API_KEY", "")),
        wire_api=str(provider_table.get("wire_api", "responses")),
        requires_openai_auth=bool(provider_table.get("requires_openai_auth", True)),
        websocket=bool(provider_table.get("supports_websockets", False)),
    )


def _provider_id_from_model_provider(name: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_-]+", "-", name.strip()).strip("-").lower()
    return value or "provider"


def _extract_all_providers(current_name: str | None) -> list[Provider]:
    config = _read_toml(CODEX_CONFIG_PATH)
    current_model_provider = str(config.get("model_provider", "OpenAI"))
    providers = config.get("model_providers", {})
    auth = _read_auth()
    if not _is_table_like(providers):
        provider_id = current_name or _provider_id_from_model_provider(current_model_provider)
        return [_extract_current_provider(provider_id)]

    result: list[Provider] = []
    used_ids: set[str] = set()
    for model_provider, provider_table in providers.items():
        if not _is_table_like(provider_table):
            continue
        provider_id = (
            current_name
            if current_name and str(model_provider) == current_model_provider
            else _provider_id_from_model_provider(str(model_provider))
        )
        original_id = provider_id
        suffix = 2
        while provider_id in used_ids:
            provider_id = f"{original_id}-{suffix}"
            suffix += 1
        used_ids.add(provider_id)
        result.append(
            Provider(
                provider_id=provider_id,
                model_providers=str(model_provider),
                base_url=str(provider_table.get("base_url", "")),
                api_key=str(auth.get("OPENAI_API_KEY", "")),
                wire_api=str(provider_table.get("wire_api", "responses")),
                requires_openai_auth=bool(provider_table.get("requires_openai_auth", True)),
                websocket=bool(provider_table.get("supports_websockets", False)),
            )
        )
    return result


def _read_auth() -> dict[str, Any]:
    if not AUTH_PATH.exists():
        return {}
    try:
        return json.loads(AUTH_PATH.read_text())
    except json.JSONDecodeError:
        return {}


def _write_auth(api_key: str) -> None:
    AUTH_PATH.parent.mkdir(parents=True, exist_ok=True)
    AUTH_PATH.write_text(json.dumps({"OPENAI_API_KEY": api_key}, indent=2) + "\n")
    AUTH_PATH.chmod(0o600)


def _write_default_base() -> None:
    if BASE_PATH.exists():
        return
    config = _read_toml(CODEX_CONFIG_PATH)
    doc = tomlkit.document()
    for key in BASE_KEYS:
        if key in config:
            doc.add(key, config[key])
    if "model" not in doc:
        doc.add("model", "gpt-5.5")
    if "review_model" not in doc:
        doc.add("review_model", "gpt-5.5")
    if "model_reasoning_effort" not in doc:
        doc.add("model_reasoning_effort", "high")
    if "model_context_window" not in doc:
        doc.add("model_context_window", 272000)
    if "model_auto_compact_token_limit" not in doc:
        doc.add("model_auto_compact_token_limit", 240000)
    _write_toml(BASE_PATH, doc)


def _set_table(parent: Any, key: str) -> Table:
    if key not in parent or not isinstance(parent[key], Table):
        parent[key] = tomlkit.table()
    return parent[key]


def _apply_provider(config: Any, base: Any, provider: Provider) -> Any:
    config.pop("cxf_provider", None)
    config["model_provider"] = provider.model_providers
    for key in BASE_KEYS:
        if key in base:
            config[key] = base[key]

    model_providers = _set_table(config, "model_providers")
    managed_names = _managed_model_provider_names()
    for name in managed_names:
        if name != provider.model_providers and name in model_providers:
            del model_providers[name]

    table = tomlkit.table()
    table.add("name", provider.model_providers)
    table.add("base_url", provider.base_url)
    table.add("wire_api", provider.wire_api)
    table.add("supports_websockets", provider.websocket)
    table.add("requires_openai_auth", provider.requires_openai_auth)
    model_providers[provider.model_providers] = table

    features = _set_table(config, "features")
    features["responses_websockets_v2"] = provider.websocket
    return config


def _provider_drift(config: Any, base: Any, provider: Provider) -> list[str]:
    drift: list[str] = []
    if config.get("model_provider") != provider.model_providers:
        drift.append("model_provider")
    for key in BASE_KEYS:
        if key in base and config.get(key) != base.get(key):
            drift.append(key)

    model_providers = config.get("model_providers", {})
    provider_table = model_providers.get(provider.model_providers, {}) if _is_table_like(model_providers) else {}
    expected_provider = {
        "name": provider.model_providers,
        "base_url": provider.base_url,
        "wire_api": provider.wire_api,
        "supports_websockets": provider.websocket,
        "requires_openai_auth": provider.requires_openai_auth,
    }
    for key, value in expected_provider.items():
        if not _is_table_like(provider_table) or provider_table.get(key) != value:
            drift.append(f"model_providers.{provider.model_providers}.{key}")

    features = config.get("features", {})
    if not _is_table_like(features) or features.get("responses_websockets_v2") != provider.websocket:
        drift.append("features.responses_websockets_v2")
    return drift


def _diff(before: str, after: str, fromfile: str, tofile: str) -> str:
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=fromfile,
            tofile=tofile,
        )
    )


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def _ensure_claude_layout() -> None:
    CLAUDE_PROVIDERS_DIR.mkdir(parents=True, exist_ok=True)


def _default_deepseek_claude_provider(api_key: str = "") -> ClaudeProvider:
    return ClaudeProvider("deepseek", {
        "ANTHROPIC_BASE_URL": "https://api.deepseek.com/anthropic",
        "ANTHROPIC_AUTH_TOKEN": api_key,
        "ANTHROPIC_MODEL": "deepseek-v4-pro[1m]",
        "ANTHROPIC_DEFAULT_OPUS_MODEL": "deepseek-v4-pro[1m]",
        "ANTHROPIC_DEFAULT_SONNET_MODEL": "deepseek-v4-pro[1m]",
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": "deepseek-v4-flash",
        "CLAUDE_CODE_SUBAGENT_MODEL": "deepseek-v4-flash",
        "CLAUDE_CODE_EFFORT_LEVEL": "max",
    })


def _claude_provider_doc(provider: ClaudeProvider) -> Any:
    doc = tomlkit.document()
    env = tomlkit.table()
    for key, value in provider.env.items():
        env.add(key, value)
    doc.add("env", env)
    return doc


def _write_claude_provider(provider: ClaudeProvider) -> None:
    _write_toml(provider.path, _claude_provider_doc(provider))


def _load_claude_provider(provider_id: str) -> ClaudeProvider:
    path = CLAUDE_PROVIDERS_DIR / f"{provider_id}.toml"
    if not path.exists():
        raise SystemExit(f"claude provider not found: {provider_id}")
    doc = _read_toml(path)
    raw_env = doc.get("env", {})
    env = {str(k): str(v) for k, v in raw_env.items()} if _is_table_like(raw_env) else {}
    return ClaudeProvider(provider_id, env)


def _claude_provider_ids() -> list[str]:
    if not CLAUDE_PROVIDERS_DIR.exists():
        return []
    return sorted(path.stem for path in CLAUDE_PROVIDERS_DIR.glob("*.toml") if path.is_file())


def _extract_current_claude_provider(name: str) -> ClaudeProvider:
    settings = _read_json(CLAUDE_SETTINGS_PATH)
    env = settings.get("env", {}) if isinstance(settings.get("env"), dict) else {}
    keys = [
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_BASE_URL",
        "ANTHROPIC_MODEL",
        "ANTHROPIC_DEFAULT_OPUS_MODEL",
        "ANTHROPIC_DEFAULT_SONNET_MODEL",
        "ANTHROPIC_DEFAULT_HAIKU_MODEL",
        "ANTHROPIC_CUSTOM_MODEL_OPTION",
        "CLAUDE_CODE_SUBAGENT_MODEL",
        "CLAUDE_CODE_EFFORT_LEVEL",
        "CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY",
        "CLAUDE_CODE_MAX_CONTEXT_TOKENS",
        "ENABLE_TOOL_SEARCH",
    ]
    provider_env = {key: str(env[key]) for key in keys if key in env and str(env[key])}
    if "ANTHROPIC_MODEL" not in provider_env and settings.get("model"):
        provider_env["ANTHROPIC_MODEL"] = str(settings["model"])
    return ClaudeProvider(name, provider_env)


def _apply_claude_provider(settings: dict[str, Any], provider: ClaudeProvider) -> dict[str, Any]:
    env = settings.get("env")
    if not isinstance(env, dict):
        env = {}
        settings["env"] = env
    managed = {
        "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL", "ANTHROPIC_MODEL",
        "ANTHROPIC_DEFAULT_OPUS_MODEL", "ANTHROPIC_DEFAULT_SONNET_MODEL", "ANTHROPIC_DEFAULT_HAIKU_MODEL",
        "ANTHROPIC_CUSTOM_MODEL_OPTION", "CLAUDE_CODE_SUBAGENT_MODEL", "CLAUDE_CODE_EFFORT_LEVEL",
        "CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY", "CLAUDE_CODE_MAX_CONTEXT_TOKENS", "ENABLE_TOOL_SEARCH",
        CLAUDE_PROVIDER_ENV,
    }
    for key in managed:
        env.pop(key, None)
    env[CLAUDE_PROVIDER_ENV] = provider.provider_id
    for key, value in provider.env.items():
        if value:
            env[key] = value
    if provider.env.get("ANTHROPIC_MODEL"):
        settings["model"] = provider.env["ANTHROPIC_MODEL"]
    return settings


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


def cmd_init(name: str | None) -> int:
    _ensure_layout()
    _write_default_base()
    providers = _extract_all_providers(name)
    for provider in providers:
        _write_provider(provider)
    print(f"initialized: {CXF_HOME}")
    for provider in providers:
        print(f"provider: {provider.provider_id} -> {provider.model_providers} {provider.base_url}")
    return 0


def cmd_add() -> int:
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


def cmd_list() -> int:
    _ensure_layout()
    for provider_id in _provider_ids():
        provider = _load_provider(provider_id)
        ws = "ws" if provider.websocket else "sse"
        print(f"{provider.provider_id}\t{provider.model_providers}\t{provider.base_url}\t{ws}")
    return 0


def cmd_current() -> int:
    raw_config = CODEX_CONFIG_PATH.read_text() if CODEX_CONFIG_PATH.exists() else ""
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


def _format_bool(value: Any) -> str:
    if value is True:
        return "on"
    if value is False:
        return "off"
    return "-"


def cmd_edit(provider_id: str | None) -> int:
    _ensure_layout()
    target = PROVIDERS_DIR / f"{provider_id}.toml" if provider_id else CXF_HOME
    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL")
    if not editor:
        raise SystemExit("EDITOR is not set")
    if provider_id and not target.exists():
        _write_provider(
            Provider(
                provider_id=provider_id,
                model_providers="OpenAI",
                base_url="",
                api_key="",
                wire_api="responses",
                requires_openai_auth=True,
                websocket=True,
            )
        )
    result = subprocess.call([editor, str(target)])
    if result != 0 or not provider_id:
        return result
    return cmd_use(provider_id)


def cmd_use(provider_id: str) -> int:
    _ensure_layout()
    provider = _load_provider(provider_id)
    base = _load_base()
    before_config = CODEX_CONFIG_PATH.read_text() if CODEX_CONFIG_PATH.exists() else ""
    before_auth = AUTH_PATH.read_text() if AUTH_PATH.exists() else ""
    config = _read_toml(CODEX_CONFIG_PATH)
    config = _apply_provider(config, base, provider)
    after_config = _set_provider_probe(tomlkit.dumps(config), provider.provider_id)
    CODEX_CONFIG_PATH.write_text(after_config)
    _write_auth(provider.api_key)
    after_auth = AUTH_PATH.read_text()

    config_diff = _diff(before_config, after_config, str(CODEX_CONFIG_PATH), str(CODEX_CONFIG_PATH))
    auth_diff = _diff(_redact_key(before_auth), _redact_key(after_auth), str(AUTH_PATH), str(AUTH_PATH))
    if config_diff:
        print(config_diff, end="")
    if auth_diff:
        print(auth_diff, end="")
    print(f"current: {provider.provider_id} -> {provider.model_providers} {provider.base_url}")
    return 0


def _redact_key(text: str) -> str:
    try:
        data = json.loads(text)
    except Exception:
        return text
    if "OPENAI_API_KEY" in data and data["OPENAI_API_KEY"]:
        data["OPENAI_API_KEY"] = "sk-***"
    return json.dumps(data, indent=2) + "\n"


def cmd_doctor() -> int:
    raw_config = CODEX_CONFIG_PATH.read_text() if CODEX_CONFIG_PATH.exists() else ""
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


def cmd_snapshot() -> int:
    _ensure_layout()
    name = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = SNAPSHOTS_DIR / name
    target.mkdir(parents=True)
    for path in (CODEX_CONFIG_PATH, AUTH_PATH):
        if path.exists():
            shutil.copy2(path, target / path.name)
    if CXF_HOME.exists():
        shutil.copytree(CXF_HOME, target / "cxf", ignore=shutil.ignore_patterns("snapshots"))
    print(target)
    return 0


def cmd_restore(snapshot: str | None) -> int:
    if not SNAPSHOTS_DIR.exists():
        raise SystemExit("no snapshots")
    target = SNAPSHOTS_DIR / snapshot if snapshot else sorted(SNAPSHOTS_DIR.iterdir())[-1]
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


def cmd_claude_init(name: str | None) -> int:
    _ensure_claude_layout()
    if not (CLAUDE_PROVIDERS_DIR / "deepseek.toml").exists():
        _write_claude_provider(_default_deepseek_claude_provider())
    current_name = name or "anthropic"
    if not (CLAUDE_PROVIDERS_DIR / f"{current_name}.toml").exists():
        _write_claude_provider(_extract_current_claude_provider(current_name))
    print(f"initialized: {CLAUDE_CXF_HOME}")
    for provider_id in _claude_provider_ids():
        provider = _load_claude_provider(provider_id)
        print(f"claude provider: {provider.provider_id} -> {provider.env.get('ANTHROPIC_BASE_URL', '-')} {provider.env.get('ANTHROPIC_MODEL', '-')}")
    return 0


def cmd_claude_list() -> int:
    _ensure_claude_layout()
    for provider_id in _claude_provider_ids():
        provider = _load_claude_provider(provider_id)
        print(f"{provider.provider_id}\t{provider.env.get('ANTHROPIC_BASE_URL', '-')}\t{provider.env.get('ANTHROPIC_MODEL', '-')}")
    return 0


def cmd_claude_current() -> int:
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


def cmd_claude_edit(provider_id: str | None) -> int:
    _ensure_claude_layout()
    target = CLAUDE_PROVIDERS_DIR / f"{provider_id}.toml" if provider_id else CLAUDE_CXF_HOME
    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL")
    if not editor:
        raise SystemExit("EDITOR is not set")
    if provider_id and not target.exists():
        _write_claude_provider(_extract_current_claude_provider(provider_id))
    result = subprocess.call([editor, str(target)])
    if result != 0 or not provider_id:
        return result
    return cmd_claude_use(provider_id)


def cmd_claude_use(provider_id: str) -> int:
    _ensure_claude_layout()
    provider = _load_claude_provider(provider_id)
    before = CLAUDE_SETTINGS_PATH.read_text() if CLAUDE_SETTINGS_PATH.exists() else ""
    settings = _read_json(CLAUDE_SETTINGS_PATH)
    after_doc = _apply_claude_provider(settings, provider)
    after = json.dumps(after_doc, ensure_ascii=False, indent=2) + "\n"
    _write_json(CLAUDE_SETTINGS_PATH, after_doc)
    diff = _diff(_redact_claude_settings(before), _redact_claude_settings(after), str(CLAUDE_SETTINGS_PATH), str(CLAUDE_SETTINGS_PATH))
    if diff:
        print(diff, end="")
    print(f"claude current: {provider.provider_id} -> {provider.env.get('ANTHROPIC_BASE_URL', '-')} {provider.env.get('ANTHROPIC_MODEL', '-')}")
    return 0


def cmd_claude_doctor() -> int:
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


def cmd_completion(shell: str) -> int:
    if shell != "zsh":
        raise SystemExit(f"unsupported shell: {shell}")
    print(files("cxf").joinpath("completions/_cxf").read_text(), end="")
    return 0


def _reject_extra_args(args: argparse.Namespace) -> bool:
    extra = getattr(args, "extra", None)
    if extra:
        print(f"error: unexpected argument: {extra[0]}", file=os.sys.stderr)
        return True
    return False


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args, extra = parser.parse_known_args(argv)
    args.extra = extra
    if _reject_extra_args(args):
        return 2
    if args.command == "init":
        return cmd_init(args.name)
    if args.command == "add":
        return cmd_add()
    if args.command == "list":
        return cmd_list()
    if args.command == "current":
        return cmd_current()
    if args.command == "edit":
        return cmd_edit(args.provider)
    if args.command == "use":
        return cmd_use(args.provider)
    if args.command == "doctor":
        return cmd_doctor()
    if args.command == "snapshot":
        return cmd_snapshot()
    if args.command == "restore":
        return cmd_restore(args.snapshot)
    if args.command == "completion":
        return cmd_completion(args.shell)
    if args.command == "claude":
        if args.claude_command == "init":
            return cmd_claude_init(args.name)
        if args.claude_command == "list":
            return cmd_claude_list()
        if args.claude_command == "current":
            return cmd_claude_current()
        if args.claude_command == "edit":
            return cmd_claude_edit(args.provider)
        if args.claude_command == "use":
            return cmd_claude_use(args.provider)
        if args.claude_command == "doctor":
            return cmd_claude_doctor()
    raise SystemExit(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())

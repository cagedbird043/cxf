from __future__ import annotations

from typing import Any

import tomlkit

from cxf.config import (
    CLAUDE_PROVIDER_ENV,
    CLAUDE_PROVIDERS_DIR,
    CLAUDE_SETTINGS_PATH,
    _is_table_like,
    _read_json,
    _read_toml,
    _write_json,
    _write_toml,
)
from cxf.models import ClaudeProvider


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


CLAUDED_MANAGED_KEYS = {
    "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL", "ANTHROPIC_MODEL",
    "ANTHROPIC_DEFAULT_OPUS_MODEL", "ANTHROPIC_DEFAULT_SONNET_MODEL", "ANTHROPIC_DEFAULT_HAIKU_MODEL",
    "ANTHROPIC_CUSTOM_MODEL_OPTION", "CLAUDE_CODE_SUBAGENT_MODEL", "CLAUDE_CODE_EFFORT_LEVEL",
    "CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY", "CLAUDE_CODE_MAX_CONTEXT_TOKENS", "ENABLE_TOOL_SEARCH",
    CLAUDE_PROVIDER_ENV,
}


def _apply_claude_provider(settings: dict[str, Any], provider: ClaudeProvider) -> dict[str, Any]:
    env = settings.get("env")
    if not isinstance(env, dict):
        env = {}
        settings["env"] = env
    for key in CLAUDED_MANAGED_KEYS:
        env.pop(key, None)
    env[CLAUDE_PROVIDER_ENV] = provider.provider_id
    for key, value in provider.env.items():
        if value:
            env[key] = value
    if provider.env.get("ANTHROPIC_MODEL"):
        settings["model"] = provider.env["ANTHROPIC_MODEL"]
    return settings

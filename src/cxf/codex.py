from __future__ import annotations

import re
from typing import Any

import tomlkit
from tomlkit.items import Table

from cxf.config import (
    BASE_KEYS,
    CODEX_CONFIG_PATH,
    PROVIDERS_DIR,
    _is_table_like,
    _read_auth,
    _read_toml,
    _write_toml,
)
from cxf.models import PROBE_PREFIX, Provider, provider_table_mapping

# ── helpers ────────────────────────────────────────────────────────────


def _provider_id_from_model_provider(name: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_-]+", "-", name.strip()).strip("-").lower()
    return value or "provider"


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


def _set_table(parent: Any, key: str) -> Table:
    if key not in parent or not isinstance(parent[key], Table):
        parent[key] = tomlkit.table()
    return parent[key]


# ── provider CRUD ──────────────────────────────────────────────────────


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
        context_window=_optional_int(doc.get("context_window")),
        auto_compact_token_limit=_optional_int(doc.get("auto_compact_token_limit")),
    )


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float, str)):
        try:
            return int(value)
        except (ValueError, TypeError):
            return None
    return None


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
    if provider.context_window is not None:
        doc.add("context_window", provider.context_window)
    if provider.auto_compact_token_limit is not None:
        doc.add("auto_compact_token_limit", provider.auto_compact_token_limit)
    return doc


def _write_provider(provider: Provider) -> None:
    _write_toml(provider.path, _provider_doc(provider))


# ── extract from live config ──────────────────────────────────────────


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


# ── apply / drift ─────────────────────────────────────────────────────


def _apply_provider(config: Any, base: Any, provider: Provider) -> Any:
    config.pop("cxf_provider", None)
    config["model_provider"] = provider.model_providers
    for key in BASE_KEYS:
        if key in base:
            config[key] = base[key]
    # per-provider overrides for context window
    if provider.context_window is not None:
        config["model_context_window"] = provider.context_window
    if provider.auto_compact_token_limit is not None:
        config["model_auto_compact_token_limit"] = provider.auto_compact_token_limit

    model_providers = _set_table(config, "model_providers")
    managed_names = _managed_model_provider_names()
    for name in managed_names:
        if name != provider.model_providers and name in model_providers:
            del model_providers[name]

    table = tomlkit.table()
    for key, value in provider_table_mapping(provider).items():
        table.add(key, value)
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
    for key, value in provider_table_mapping(provider).items():
        if not _is_table_like(provider_table) or provider_table.get(key) != value:
            drift.append(f"model_providers.{provider.model_providers}.{key}")

    features = config.get("features", {})
    if not _is_table_like(features) or features.get("responses_websockets_v2") != provider.websocket:
        drift.append("features.responses_websockets_v2")
    return drift

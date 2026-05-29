from __future__ import annotations

import difflib
import getpass
import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import tomlkit

# ── paths ──────────────────────────────────────────────────────────────

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

# ── base keys ──────────────────────────────────────────────────────────

BASE_KEYS = (
    "model",
    "review_model",
    "model_reasoning_effort",
    "model_context_window",
    "model_auto_compact_token_limit",
)

# ── TOML helpers ───────────────────────────────────────────────────────


def _read_toml(path: Path) -> Any:
    if not path.exists():
        return tomlkit.document()
    return tomlkit.parse(path.read_text(encoding="utf-8"))


def _is_table_like(value: Any) -> bool:
    return hasattr(value, "get") and hasattr(value, "items")


def _write_toml(path: Path, doc: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(tomlkit.dumps(doc), encoding="utf-8")


# ── JSON helpers ───────────────────────────────────────────────────────


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


# ── auth helpers ───────────────────────────────────────────────────────


def _read_auth() -> dict[str, Any]:
    return _read_json(AUTH_PATH)


def _write_auth(api_key: str) -> None:
    AUTH_PATH.parent.mkdir(parents=True, exist_ok=True)
    AUTH_PATH.write_text(
        json.dumps({"OPENAI_API_KEY": api_key, "source": "cxf"}, indent=2) + "\n",
        encoding="utf-8",
    )
    AUTH_PATH.chmod(0o600)


# ── layout ─────────────────────────────────────────────────────────────


def _ensure_layout() -> None:
    PROVIDERS_DIR.mkdir(parents=True, exist_ok=True)
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)


def _ensure_claude_layout() -> None:
    CLAUDE_PROVIDERS_DIR.mkdir(parents=True, exist_ok=True)


# ── prompts ────────────────────────────────────────────────────────────


def _prompt(name: str, default: str | None = None, secret: bool = False) -> str:
    suffix = f" [{default}]" if default is not None else ""
    try:
        if secret:
            value = getpass.getpass(f"{name}{suffix}: ").strip()
        else:
            value = input(f"{name}{suffix}: ").strip()
    except (KeyboardInterrupt, EOFError):
        raise SystemExit("\ncancelled")
    if not value and default is not None:
        return default
    return value


def _prompt_bool(name: str, default: bool) -> bool:
    default_text = "yes" if default else "no"
    value = _prompt(name, default_text).lower()
    return value in {"y", "yes", "true", "1", "on"}


# ── diff / redact ──────────────────────────────────────────────────────


def _format_bool(value: Any) -> str:
    if value is True:
        return "on"
    if value is False:
        return "off"
    return "-"


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


# ── base ───────────────────────────────────────────────────────────────


def _load_base() -> Any:
    return _read_toml(BASE_PATH)


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


# ── snapshot ───────────────────────────────────────────────────────────


def _snapshot_path(name: str | None = None) -> Path:
    _ensure_layout()
    name = name or datetime.now().strftime("%Y%m%d-%H%M%S")
    target = SNAPSHOTS_DIR / name
    target.mkdir(parents=True)
    return target


def _latest_snapshot() -> Path:
    if not SNAPSHOTS_DIR.exists():
        raise SystemExit("no snapshots")
    return sorted(SNAPSHOTS_DIR.iterdir())[-1]

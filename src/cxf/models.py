from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from cxf.config import CLAUDE_PROVIDERS_DIR, PROVIDERS_DIR

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
    context_window: int | None = None
    auto_compact_token_limit: int | None = None

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


def provider_table_mapping(p: Provider) -> dict[str, str | bool]:
    """Canonical mapping used by both apply and drift detection."""
    return {
        "name": p.model_providers,
        "base_url": p.base_url,
        "wire_api": p.wire_api,
        "supports_websockets": p.websocket,
        "requires_openai_auth": p.requires_openai_auth,
    }

import json

import tomlkit

import pytest

from cxf.claude import (
    _apply_claude_provider,
    _default_deepseek_claude_provider,
)
from cxf.cli import (
    _cmd_edit,
    _cmd_remove,
    _cmd_status,
    build_parser,
    main,
)
from cxf.codex import (
    _apply_provider,
    _read_provider_probe,
    _set_provider_probe,
)
from cxf.models import Provider
from cxf.ux import (
    _,
    _confirm,
    _diff,
    _error,
    _format_bool,
    _prompt,
    _redact_claude_settings,
    _redact_key,
)

# ── helpers ────────────────────────────────────────────────────────────


def _patch_paths(monkeypatch, tmp_path) -> None:
    """Patch PROVIDERS_DIR in modules that import it."""
    provider_dir = tmp_path / "providers"
    provider_dir.mkdir(exist_ok=True)
    for mod in ("cxf.config", "cxf.codex", "cxf.cli", "cxf.models"):
        monkeypatch.setattr(f"{mod}.PROVIDERS_DIR", provider_dir)
    # ensure layout uses our temp paths
    monkeypatch.setattr("cxf.config.SNAPSHOTS_DIR", tmp_path / "snapshots")


# ── parser ─────────────────────────────────────────────────────────────


def test_parser_accepts_use_provider() -> None:
    args = build_parser().parse_args(["use", "timi"])
    assert args.command == "use"
    assert args.provider == "timi"


def test_parser_accepts_claude_use() -> None:
    args = build_parser().parse_args(["claude", "use", "deepseek"])
    assert args.command == "claude"
    assert args.claude_command == "use"
    assert args.provider == "deepseek"


def test_parser_accepts_remove() -> None:
    args = build_parser().parse_args(["remove", "timi", "-y"])
    assert args.command == "remove"
    assert args.provider == "timi"
    assert args.yes is True


def test_parser_accepts_claude_remove() -> None:
    args = build_parser().parse_args(["claude", "remove", "deepseek", "-y"])
    assert args.command == "claude"
    assert args.claude_command == "remove"
    assert args.provider == "deepseek"
    assert args.yes is True


def test_parser_accepts_status() -> None:
    args = build_parser().parse_args(["status"])
    assert args.command == "status"


def test_parser_accepts_claude_status() -> None:
    args = build_parser().parse_args(["claude", "status"])
    assert args.command == "claude"
    assert args.claude_command == "status"


def test_parser_accepts_add_noninteractive() -> None:
    args = build_parser().parse_args([
        "add",
        "--provider-id", "test",
        "--base-url", "https://example.com",
        "--api-key", "sk-test",
    ])
    assert args.command == "add"
    assert args.provider_id == "test"
    assert args.base_url == "https://example.com"
    assert args.api_key == "sk-test"


def test_extra_arguments_are_rejected(capsys) -> None:
    assert main(["list", "extra"]) == 2
    captured = capsys.readouterr()
    assert "extra" in captured.err


def test_missing_command_shows_help(capsys) -> None:
    rc = main([])
    assert rc == 0
    captured = capsys.readouterr()
    assert "usage: cxf" in captured.out


# ── prompts ────────────────────────────────────────────────────────────


def test_prompt_cancel_is_short_error(monkeypatch) -> None:
    def raise_keyboard_interrupt(_: str) -> str:
        raise KeyboardInterrupt

    monkeypatch.setattr("builtins.input", raise_keyboard_interrupt)
    with pytest.raises(SystemExit) as exc:
        _prompt("p.provider_id")
    assert str(exc.value) == "\ncancelled"


def test_confirm_yes_returns_True(monkeypatch) -> None:
    monkeypatch.setattr("builtins.input", lambda _="": "y")
    assert _confirm("p.remove_provider", "timi") is True


def test_confirm_no_returns_False(monkeypatch) -> None:
    monkeypatch.setattr("builtins.input", lambda _="": "n")
    assert _confirm("p.remove_provider", "timi") is False


def test_confirm_yes_flag_skips_prompt() -> None:
    assert _confirm("p.remove_provider", "timi", yes=True) is True


# ── _error ─────────────────────────────────────────────────────────────


def test_error_prints_prefix_and_exits(capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        _error("err.not_found", "test")
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "cxf: error:" in captured.err
    assert "test" in captured.err


# ── apply_provider ─────────────────────────────────────────────────────


def test_apply_provider_keeps_unrelated_config(monkeypatch, tmp_path) -> None:
    (tmp_path / "providers").mkdir()
    (tmp_path / "providers" / "a.toml").write_text('model_providers = "OpenAI"\n')
    (tmp_path / "providers" / "b.toml").write_text('model_providers = "Other"\n')

    _patch_paths(monkeypatch, tmp_path)

    config = tomlkit.parse(
        """
model_provider = "Other"

[model_providers.OpenAI]
base_url = "https://old.example"

[model_providers.Other]
base_url = "https://other.example"

[projects."/home/user/project"]
trust_level = "trusted"

[features]
shell_tool = true
"""
    )
    base = tomlkit.parse(
        """
model = "gpt-5.5"
review_model = "gpt-5.4"
"""
    )
    provider = Provider(
        provider_id="timi",
        model_providers="OpenAI",
        base_url="https://timicc.com",
        api_key="sk-test",
        wire_api="responses",
        requires_openai_auth=True,
        websocket=True,
    )

    result = _apply_provider(config, base, provider)

    assert "cxf_provider" not in result
    assert result["model_provider"] == "OpenAI"
    assert result["model_providers"]["OpenAI"]["base_url"] == "https://timicc.com"
    assert "Other" not in result["model_providers"]
    assert result["projects"]["/home/user/project"]["trust_level"] == "trusted"
    assert result["features"]["shell_tool"] is True
    assert result["features"]["responses_websockets_v2"] is True


# ── provider probe ─────────────────────────────────────────────────────


def test_provider_probe_is_comment() -> None:
    text = '#:schema https://example.test/schema.json\nmodel = "gpt-5.5"\n'
    updated = _set_provider_probe(text, "timi")
    assert updated.splitlines()[1] == "# cxf: provider = timi"
    assert _read_provider_probe(updated) == "timi"


# ── edit ───────────────────────────────────────────────────────────────


def test_edit_reapplies_provider_after_successful_editor(monkeypatch, tmp_path) -> None:
    _patch_paths(monkeypatch, tmp_path)
    target = tmp_path / "providers" / "timi.toml"
    target.write_text(
        """
model_providers = "OpenAI"
base_url = "https://timicc.com"
api_key = "sk-test"
wire_api = "responses"
requires_openai_auth = true
websocket = true
"""
    )
    monkeypatch.setenv("EDITOR", "true")
    monkeypatch.setattr("subprocess.call", lambda _: 0)

    called: list[str] = []
    monkeypatch.setattr("cxf.cli._cmd_use", lambda provider_id: called.append(provider_id) or 0)

    assert _cmd_edit("timi") == 0
    assert called == ["timi"]


def test_edit_does_not_reapply_on_editor_failure(monkeypatch, tmp_path) -> None:
    _patch_paths(monkeypatch, tmp_path)
    (tmp_path / "providers" / "timi.toml").write_text('model_providers = "OpenAI"\n')
    monkeypatch.setenv("EDITOR", "false")
    monkeypatch.setattr("subprocess.call", lambda _: 7)

    called: list[str] = []
    monkeypatch.setattr("cxf.cli._cmd_use", lambda provider_id: called.append(provider_id) or 0)

    assert _cmd_edit("timi") == 7
    assert called == []


def test_edit_prompts_before_creating_new_provider(monkeypatch, tmp_path) -> None:
    _patch_paths(monkeypatch, tmp_path)
    monkeypatch.setenv("EDITOR", "true")
    monkeypatch.setattr("subprocess.call", lambda _: 0)
    monkeypatch.setattr("builtins.input", lambda _="": "n")

    assert _cmd_edit("nonexistent") == 1


def test_edit_yes_flag_creates_without_prompt(monkeypatch, tmp_path) -> None:
    _patch_paths(monkeypatch, tmp_path)
    monkeypatch.setenv("EDITOR", "true")
    monkeypatch.setattr("subprocess.call", lambda _: 0)
    # mock prompts including getpass for api_key (secret=True)
    # order: model_providers, base_url, getpass(api_key), wire_api, websocket_bool
    prompts = iter(["OpenAI", "https://example.com", "sk-test", "responses", "yes"])
    monkeypatch.setattr("builtins.input", lambda _="": next(prompts))
    monkeypatch.setattr("getpass.getpass", lambda _="": next(prompts))
    # prevent _cmd_edit from writing to real Codex config via _cmd_use
    monkeypatch.setattr("cxf.cli._cmd_use", lambda provider_id: 0)

    assert _cmd_edit("newprov", yes=True) == 0


# ── remove ─────────────────────────────────────────────────────────────


def test_remove_deletes_provider_when_confirmed(monkeypatch, tmp_path) -> None:
    _patch_paths(monkeypatch, tmp_path)
    target = tmp_path / "providers" / "timi.toml"
    target.write_text('model_providers = "OpenAI"\n')

    monkeypatch.setattr("builtins.input", lambda _="": "y")

    assert _cmd_remove("timi") == 0
    assert not target.exists()


def test_remove_aborts_when_declined(monkeypatch, tmp_path) -> None:
    _patch_paths(monkeypatch, tmp_path)
    target = tmp_path / "providers" / "timi.toml"
    target.write_text('model_providers = "OpenAI"\n')

    monkeypatch.setattr("builtins.input", lambda _="": "n")

    assert _cmd_remove("timi") == 1
    assert target.exists()


def test_remove_yes_flag_skips_confirmation(monkeypatch, tmp_path) -> None:
    _patch_paths(monkeypatch, tmp_path)
    target = tmp_path / "providers" / "timi.toml"
    target.write_text('model_providers = "OpenAI"\n')

    assert _cmd_remove("timi", yes=True) == 0
    assert not target.exists()


def test_remove_errors_on_missing_provider() -> None:
    with pytest.raises(SystemExit):
        _cmd_remove("nonexistent")


# ── status ─────────────────────────────────────────────────────────────


def test_status_no_provider_probe(monkeypatch, tmp_path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text('model = "gpt-5.5"\n')
    _patch_paths(monkeypatch, tmp_path)
    monkeypatch.setattr("cxf.config.CODEX_CONFIG_PATH", config_path)
    monkeypatch.setattr("cxf.codex.CODEX_CONFIG_PATH", config_path)
    monkeypatch.setattr("cxf.cli.CODEX_CONFIG_PATH", config_path)

    rc = _cmd_status()
    assert rc == 1


# ── Claude provider ────────────────────────────────────────────────────


def test_deepseek_claude_provider_defaults() -> None:
    provider = _default_deepseek_claude_provider("sk-test")
    assert provider.provider_id == "deepseek"
    assert provider.env["ANTHROPIC_BASE_URL"] == "https://api.deepseek.com/anthropic"
    assert provider.env["ANTHROPIC_AUTH_TOKEN"] == "sk-test"
    assert provider.env["ANTHROPIC_MODEL"] == "deepseek-v4-pro[1m]"
    assert provider.env["ANTHROPIC_DEFAULT_HAIKU_MODEL"] == "deepseek-v4-flash"
    assert provider.env["CLAUDE_CODE_EFFORT_LEVEL"] == "max"


def test_apply_claude_provider_preserves_unmanaged_env() -> None:
    settings = {
        "env": {
            "GITHUB_TOKEN": "gh-test",
            "ANTHROPIC_BASE_URL": "https://old.example",
            "ANTHROPIC_API_KEY": "old-key",
        },
        "permissions": {"allow": ["Read(*)"]},
        "model": "old-model",
    }
    provider = _default_deepseek_claude_provider("sk-test")
    result = _apply_claude_provider(settings, provider)
    assert result["env"]["GITHUB_TOKEN"] == "gh-test"
    assert result["env"]["CXF_CLAUDE_PROVIDER"] == "deepseek"
    assert result["env"]["ANTHROPIC_BASE_URL"] == "https://api.deepseek.com/anthropic"
    assert result["env"]["ANTHROPIC_AUTH_TOKEN"] == "sk-test"
    assert "ANTHROPIC_API_KEY" not in result["env"]
    assert result["model"] == "deepseek-v4-pro[1m]"
    assert result["permissions"] == {"allow": ["Read(*)"]}


# ── formatting ─────────────────────────────────────────────────────────


def test_format_bool() -> None:
    # _format_bool uses _() internally, returns translated text
    on_text = _("bool.on")
    off_text = _("bool.off")
    assert _format_bool(True) == on_text
    assert _format_bool(False) == off_text
    assert _format_bool(None) == "-"
    assert _format_bool("") == "-"


# ── redact ─────────────────────────────────────────────────────────────


def test_redact_key_hides_api_key() -> None:
    clean = _redact_key('{"OPENAI_API_KEY": "sk-real-deal"}')
    assert "sk-real-deal" not in clean
    assert "sk-***" in clean


def test_redact_key_handles_invalid_json() -> None:
    assert _redact_key("not json") == "not json"


def test_redact_claude_settings_hides_multiple_keys() -> None:
    raw = json.dumps({
        "env": {
            "ANTHROPIC_AUTH_TOKEN": "secret-1",
            "GITHUB_TOKEN": "secret-2",
            "ANTHROPIC_MODEL": "claude-4",
        }
    })
    clean = _redact_claude_settings(raw)
    data = json.loads(clean)
    assert data["env"]["ANTHROPIC_AUTH_TOKEN"] == "***"
    assert data["env"]["GITHUB_TOKEN"] == "***"
    assert data["env"]["ANTHROPIC_MODEL"] == "claude-4"


# ── diff ───────────────────────────────────────────────────────────────


def test_diff_shows_changes() -> None:
    before = "a\nb\nc\n"
    after = "a\nb\nx\nc\n"
    d = _diff(before, after, "old", "new")
    assert "+x" in d


def test_diff_empty_for_identical() -> None:
    d = _diff("same\n", "same\n", "f", "f")
    assert d == ""

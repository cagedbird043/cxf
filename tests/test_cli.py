import json

import tomlkit

import pytest

from cxf.claude import (
    _apply_claude_provider,
    _default_deepseek_claude_provider,
)
from cxf.cli import (
    _cmd_edit,
    _cmd_use,
    _cmd_current,
    _cmd_doctor,
    _cmd_claude_use,
    _cmd_claude_current,
    _cmd_claude_doctor,
    build_parser,
    main,
)
from cxf.codex import (
    _apply_provider,
    _read_provider_probe,
    _set_provider_probe,
)
from cxf.config import (
    _prompt,
    _diff,
    _format_bool,
    _redact_key,
    _redact_claude_settings,
)
from cxf.models import Provider


def test_parser_accepts_run_provider() -> None:
    args = build_parser().parse_args(["use", "timi"])
    assert args.command == "use"
    assert args.provider == "timi"


def test_parser_accepts_zsh_completion() -> None:
    args = build_parser().parse_args(["completion", "zsh"])
    assert args.command == "completion"
    assert args.shell == "zsh"


def test_extra_arguments_are_short_errors(capsys) -> None:
    assert main(["completion", "zsh", "zsh"]) == 2
    captured = capsys.readouterr()
    assert "unexpected argument: zsh" in captured.err


def test_prompt_cancel_is_short_error(monkeypatch) -> None:
    def raise_keyboard_interrupt(_: str) -> str:
        raise KeyboardInterrupt

    monkeypatch.setattr("builtins.input", raise_keyboard_interrupt)
    with pytest.raises(SystemExit) as exc:
        _prompt("provider id")
    assert str(exc.value) == "\ncancelled"


def test_apply_provider_keeps_unrelated_config(monkeypatch, tmp_path) -> None:
    provider_a = tmp_path / "a.toml"
    provider_b = tmp_path / "b.toml"
    provider_a.write_text('model_providers = "OpenAI"\n')
    provider_b.write_text('model_providers = "Other"\n')
    monkeypatch.setattr("cxf.config.PROVIDERS_DIR", tmp_path)
    monkeypatch.setattr("cxf.codex.PROVIDERS_DIR", tmp_path)

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


def test_provider_probe_is_comment() -> None:
    text = '#:schema https://example.test/schema.json\nmodel = "gpt-5.5"\n'
    updated = _set_provider_probe(text, "timi")
    assert updated.splitlines()[1] == "# cxf: provider = timi"
    assert _read_provider_probe(updated) == "timi"


def test_edit_reapplies_provider_after_successful_editor(monkeypatch, tmp_path) -> None:
    provider_dir = tmp_path / "providers"
    provider_dir.mkdir()
    provider_path = provider_dir / "timi.toml"
    provider_path.write_text(
        """
model_providers = "OpenAI"
base_url = "https://timicc.com"
api_key = "sk-test"
wire_api = "responses"
requires_openai_auth = true
websocket = true
"""
    )

    monkeypatch.setattr("cxf.config.PROVIDERS_DIR", provider_dir)
    monkeypatch.setattr("cxf.codex.PROVIDERS_DIR", provider_dir)
    monkeypatch.setattr("cxf.config.CXF_HOME", tmp_path)
    monkeypatch.setenv("EDITOR", "true")
    monkeypatch.setattr("subprocess.call", lambda _: 0)

    called: list[str] = []
    monkeypatch.setattr("cxf.cli._cmd_use", lambda provider_id: called.append(provider_id) or 0)

    assert _cmd_edit("timi") == 0
    assert called == ["timi"]


def test_edit_does_not_reapply_on_editor_failure(monkeypatch, tmp_path) -> None:
    provider_dir = tmp_path / "providers"
    provider_dir.mkdir()
    (provider_dir / "timi.toml").write_text('model_providers = "OpenAI"\n')

    monkeypatch.setattr("cxf.config.PROVIDERS_DIR", provider_dir)
    monkeypatch.setattr("cxf.codex.PROVIDERS_DIR", provider_dir)
    monkeypatch.setattr("cxf.config.CXF_HOME", tmp_path)
    monkeypatch.setenv("EDITOR", "false")
    monkeypatch.setattr("subprocess.call", lambda _: 7)

    called: list[str] = []
    monkeypatch.setattr("cxf.cli._cmd_use", lambda provider_id: called.append(provider_id) or 0)

    assert _cmd_edit("timi") == 7
    assert called == []


def test_edit_prompts_before_creating_new_provider(monkeypatch, tmp_path) -> None:
    provider_dir = tmp_path / "providers"
    provider_dir.mkdir()

    monkeypatch.setattr("cxf.config.PROVIDERS_DIR", provider_dir)
    monkeypatch.setattr("cxf.codex.PROVIDERS_DIR", provider_dir)
    monkeypatch.setattr("cxf.config.CXF_HOME", tmp_path)
    monkeypatch.setenv("EDITOR", "true")
    monkeypatch.setattr("subprocess.call", lambda _: 0)
    monkeypatch.setattr("builtins.input", lambda _="": "n")

    result = _cmd_edit("nonexistent")
    assert result == 1


def test_parser_accepts_claude_use_provider() -> None:
    args = build_parser().parse_args(["claude", "use", "deepseek"])
    assert args.command == "claude"
    assert args.claude_command == "use"
    assert args.provider == "deepseek"


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


def test_format_bool() -> None:
    assert _format_bool(True) == "on"
    assert _format_bool(False) == "off"
    assert _format_bool(None) == "-"
    assert _format_bool("") == "-"


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


def test_diff_shows_changes() -> None:
    before = "a\nb\nc\n"
    after = "a\nb\nx\nc\n"
    d = _diff(before, after, "old", "new")
    assert "+x" in d


def test_diff_empty_for_identical() -> None:
    d = _diff("same\n", "same\n", "f", "f")
    assert d == ""

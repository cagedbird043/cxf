import argparse
import json
from pathlib import Path

import tomlkit

import pytest

from cxf.claude import (
    _apply_claude_provider,
    _default_deepseek_claude_provider,
)
from cxf.cli import (
    _cmd_add,
    _cmd_claude_init,
    _cmd_claude_remove,
    _cmd_claude_status,
    _cmd_claude_use,
    _cmd_current,
    _cmd_edit,
    _cmd_init,
    _cmd_remove,
    _cmd_status,
    _cmd_use,
    build_parser,
    main,
)
from cxf.codex import (
    _apply_provider,
    _read_provider_probe,
    _set_provider_probe,
    _write_provider,
)
from cxf.models import ClaudeProvider, Provider
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


def _patch_paths(monkeypatch, tmp_path) -> dict:
    """Patch ALL config paths in all relevant modules to point under tmp_path.

    Returns a dict of paths so tests can set up specific files.
    """
    cxf_home = tmp_path / "cxf"
    provider_dir = cxf_home / "providers"
    snapshots_dir = cxf_home / "snapshots"
    base_path = cxf_home / "base.toml"
    config_path = tmp_path / "config.toml"
    auth_path = tmp_path / "auth.json"
    claude_cxf_home = cxf_home / "claude"
    claude_provider_dir = claude_cxf_home / "providers"
    claude_settings_path = tmp_path / "claude_settings.json"

    # -- config (source of truth) --
    monkeypatch.setattr("cxf.config.CXF_HOME", cxf_home)
    monkeypatch.setattr("cxf.config.PROVIDERS_DIR", provider_dir)
    monkeypatch.setattr("cxf.config.SNAPSHOTS_DIR", snapshots_dir)
    monkeypatch.setattr("cxf.config.BASE_PATH", base_path)
    monkeypatch.setattr("cxf.config.CODEX_CONFIG_PATH", config_path)
    monkeypatch.setattr("cxf.config.AUTH_PATH", auth_path)
    monkeypatch.setattr("cxf.config.CLAUDE_CXF_HOME", claude_cxf_home)
    monkeypatch.setattr("cxf.config.CLAUDE_PROVIDERS_DIR", claude_provider_dir)
    monkeypatch.setattr("cxf.config.CLAUDE_SETTINGS_PATH", claude_settings_path)

    # -- codex: CODEX_CONFIG_PATH, PROVIDERS_DIR --
    monkeypatch.setattr("cxf.codex.CODEX_CONFIG_PATH", config_path)
    monkeypatch.setattr("cxf.codex.PROVIDERS_DIR", provider_dir)

    # -- claude: CLAUDE_PROVIDERS_DIR, CLAUDE_SETTINGS_PATH --
    monkeypatch.setattr("cxf.claude.CLAUDE_PROVIDERS_DIR", claude_provider_dir)
    monkeypatch.setattr("cxf.claude.CLAUDE_SETTINGS_PATH", claude_settings_path)

    # -- cli: AUTH_PATH, CLAUDE_PROVIDERS_DIR, CLAUDE_SETTINGS_PATH, CODEX_CONFIG_PATH, CXF_HOME, PROVIDERS_DIR --
    monkeypatch.setattr("cxf.cli.AUTH_PATH", auth_path)
    monkeypatch.setattr("cxf.cli.CLAUDE_PROVIDERS_DIR", claude_provider_dir)
    monkeypatch.setattr("cxf.cli.CLAUDE_SETTINGS_PATH", claude_settings_path)
    monkeypatch.setattr("cxf.cli.CODEX_CONFIG_PATH", config_path)
    monkeypatch.setattr("cxf.cli.CXF_HOME", cxf_home)
    monkeypatch.setattr("cxf.cli.PROVIDERS_DIR", provider_dir)

    # -- models: PROVIDERS_DIR, CLAUDE_PROVIDERS_DIR --
    monkeypatch.setattr("cxf.models.PROVIDERS_DIR", provider_dir)
    monkeypatch.setattr("cxf.models.CLAUDE_PROVIDERS_DIR", claude_provider_dir)

    provider_dir.mkdir(parents=True, exist_ok=True)
    claude_provider_dir.mkdir(parents=True, exist_ok=True)

    return {
        "cxf_home": cxf_home,
        "provider_dir": provider_dir,
        "config_path": config_path,
        "auth_path": auth_path,
        "base_path": base_path,
        "claude_provider_dir": claude_provider_dir,
        "claude_settings_path": claude_settings_path,
    }


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
    args = build_parser().parse_args(
        [
            "add",
            "--provider-id",
            "test",
            "--base-url",
            "https://example.com",
            "--api-key",
            "sk-test",
        ]
    )
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
    paths = _patch_paths(monkeypatch, tmp_path)
    (paths["provider_dir"] / "a.toml").write_text('model_providers = "OpenAI"\n')
    (paths["provider_dir"] / "b.toml").write_text('model_providers = "Other"\n')

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
    paths = _patch_paths(monkeypatch, tmp_path)
    target = paths["provider_dir"] / "timi.toml"
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
    paths = _patch_paths(monkeypatch, tmp_path)
    (paths["provider_dir"] / "timi.toml").write_text('model_providers = "OpenAI"\n')
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
    paths = _patch_paths(monkeypatch, tmp_path)
    monkeypatch.setenv("EDITOR", "true")
    monkeypatch.setattr("cxf.cli._cmd_use", lambda provider_id: 0)

    # simulate user filling in api_key after editing
    def mock_editor(args):
        path = Path(args[-1])
        doc = tomlkit.parse(path.read_text(encoding="utf-8"))
        doc["api_key"] = "sk-edited"
        path.write_text(tomlkit.dumps(doc), encoding="utf-8")
        return 0

    monkeypatch.setattr("subprocess.call", mock_editor)

    assert _cmd_edit("newprov", yes=True) == 0
    # stub file should be written with defaults
    target = paths["provider_dir"] / "newprov.toml"
    assert target.exists()
    doc = tomlkit.parse(target.read_text(encoding="utf-8"))
    assert doc["model_providers"] == "OpenAI"
    assert doc["wire_api"] == "responses"
    assert doc["websocket"] is True
    assert doc["api_key"] == "sk-edited"


def test_edit_empty_api_key_aborts(monkeypatch, tmp_path) -> None:
    paths = _patch_paths(monkeypatch, tmp_path)
    monkeypatch.setenv("EDITOR", "true")
    # editor returns success but user left api_key empty in stub
    monkeypatch.setattr("subprocess.call", lambda _: 0)
    monkeypatch.setattr("cxf.cli._cmd_use", lambda provider_id: 0)

    assert _cmd_edit("emptykey-prov", yes=True) == 1
    # stub should still exist on disk, just not applied
    target = paths["provider_dir"] / "emptykey-prov.toml"
    assert target.exists()
    doc = tomlkit.parse(target.read_text(encoding="utf-8"))
    assert doc["api_key"] == ""


# ── remove ─────────────────────────────────────────────────────────────


def test_remove_deletes_provider_when_confirmed(monkeypatch, tmp_path) -> None:
    paths = _patch_paths(monkeypatch, tmp_path)
    target = paths["provider_dir"] / "timi.toml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('model_providers = "OpenAI"\n')

    monkeypatch.setattr("builtins.input", lambda _="": "y")

    assert _cmd_remove("timi") == 0
    assert not target.exists()


def test_remove_aborts_when_declined(monkeypatch, tmp_path) -> None:
    paths = _patch_paths(monkeypatch, tmp_path)
    target = paths["provider_dir"] / "timi.toml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('model_providers = "OpenAI"\n')

    monkeypatch.setattr("builtins.input", lambda _="": "n")

    assert _cmd_remove("timi") == 1
    assert target.exists()


def test_remove_yes_flag_skips_confirmation(monkeypatch, tmp_path) -> None:
    paths = _patch_paths(monkeypatch, tmp_path)
    target = paths["provider_dir"] / "timi.toml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('model_providers = "OpenAI"\n')

    assert _cmd_remove("timi", yes=True) == 0
    assert not target.exists()


def test_remove_errors_on_missing_provider() -> None:
    with pytest.raises(SystemExit):
        _cmd_remove("nonexistent")


# ── status ─────────────────────────────────────────────────────────────


def test_status_no_provider_probe(monkeypatch, tmp_path) -> None:
    paths = _patch_paths(monkeypatch, tmp_path)
    paths["config_path"].write_text('model = "gpt-5.5"\n')

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
    raw = json.dumps(
        {
            "env": {
                "ANTHROPIC_AUTH_TOKEN": "secret-1",
                "GITHUB_TOKEN": "secret-2",
                "ANTHROPIC_MODEL": "claude-4",
            }
        }
    )
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


# ── init ────────────────────────────────────────────────────────────────


def test_cmd_init_creates_providers_from_config(monkeypatch, tmp_path) -> None:
    paths = _patch_paths(monkeypatch, tmp_path)
    paths["config_path"].write_text(
        'model_provider = "OpenAI"\n[model_providers.OpenAI]\nbase_url = "https://api.openai.com"\n'
    )
    assert _cmd_init(None) == 0
    assert (paths["provider_dir"] / "openai.toml").exists()


def test_cmd_init_with_name(monkeypatch, tmp_path) -> None:
    paths = _patch_paths(monkeypatch, tmp_path)
    paths["config_path"].write_text(
        'model_provider = "OpenAI"\n[model_providers.OpenAI]\nbase_url = "https://api.openai.com"\n'
    )
    assert _cmd_init("my-provider") == 0
    assert (paths["provider_dir"] / "my-provider.toml").exists()


def test_cmd_init_with_model_providers_section(monkeypatch, tmp_path) -> None:
    paths = _patch_paths(monkeypatch, tmp_path)
    paths["config_path"].write_text(
        'model_provider = "OpenAI"\n[model_providers.OpenAI]\nbase_url = "https://api.openai.com"\n'
    )
    assert _cmd_init(None) == 0
    assert (paths["provider_dir"] / "openai.toml").exists()


# ── current ─────────────────────────────────────────────────────────────


def test_cmd_current_with_probe(monkeypatch, tmp_path, capsys) -> None:
    paths = _patch_paths(monkeypatch, tmp_path)
    paths["config_path"].write_text(
        '# cxf: provider = timi\nmodel_provider = "OpenAI"\n[model_providers.OpenAI]\nbase_url = "https://timicc.com"\n'
    )
    _write_provider(
        Provider(
            provider_id="timi",
            model_providers="OpenAI",
            base_url="https://timicc.com",
            api_key="sk-test",
            wire_api="responses",
            requires_openai_auth=True,
            websocket=True,
        )
    )
    assert _cmd_current() == 0
    captured = capsys.readouterr()
    assert "timi" in captured.out
    assert "OpenAI" in captured.out


def test_cmd_current_no_probe(monkeypatch, tmp_path, capsys) -> None:
    paths = _patch_paths(monkeypatch, tmp_path)
    paths["config_path"].write_text('model_provider = "OpenAI"\n')
    assert _cmd_current() == 0
    captured = capsys.readouterr()
    assert "-" in captured.out


# ── use ─────────────────────────────────────────────────────────────────


def test_cmd_use_switches_provider(monkeypatch, tmp_path, capsys) -> None:
    paths = _patch_paths(monkeypatch, tmp_path)
    paths["config_path"].write_text('model_provider = "Other"\n')
    paths["base_path"].write_text('model = "gpt-5.5"\nreview_model = "gpt-5.4"\n')
    paths["auth_path"].write_text('{"OPENAI_API_KEY": "sk-test", "source": "cxf"}\n')
    _write_provider(
        Provider(
            provider_id="timi",
            model_providers="OpenAI",
            base_url="https://timicc.com",
            api_key="sk-test",
            wire_api="responses",
            requires_openai_auth=True,
            websocket=True,
        )
    )

    assert _cmd_use("timi") == 0
    config = tomlkit.parse(paths["config_path"].read_text(encoding="utf-8"))
    assert config["model_provider"] == "OpenAI"
    assert config["model_providers"]["OpenAI"]["base_url"] == "https://timicc.com"


def test_cmd_use_no_arg_returns_1(capsys) -> None:
    rc = _cmd_use(None)
    assert rc == 1
    captured = capsys.readouterr()
    assert "usage:" in captured.out


# ── add (non-interactive) ───────────────────────────────────────────────


def test_cmd_add_noninteractive(monkeypatch, tmp_path) -> None:
    paths = _patch_paths(monkeypatch, tmp_path)
    args = argparse.Namespace(
        provider_id="test-provider",
        model_providers="MyModel",
        base_url="https://example.com",
        api_key="sk-valid",
        wire_api="responses",
        no_websocket=False,
    )
    assert _cmd_add(args) == 0
    target = paths["provider_dir"] / "test-provider.toml"
    assert target.exists()
    doc = tomlkit.parse(target.read_text(encoding="utf-8"))
    assert doc["base_url"] == "https://example.com"
    assert doc["api_key"] == "sk-valid"
    assert doc["model_providers"] == "MyModel"
    assert doc["wire_api"] == "responses"
    assert doc["websocket"] is True


def test_cmd_add_noninteractive_missing_base_url(monkeypatch, tmp_path) -> None:
    _patch_paths(monkeypatch, tmp_path)
    args = argparse.Namespace(
        provider_id="test",
        model_providers=None,
        base_url="",
        api_key="sk-key",
        wire_api=None,
        no_websocket=False,
    )
    with pytest.raises(SystemExit):
        _cmd_add(args)


def test_cmd_add_noninteractive_missing_api_key(monkeypatch, tmp_path) -> None:
    _patch_paths(monkeypatch, tmp_path)
    args = argparse.Namespace(
        provider_id="test",
        model_providers=None,
        base_url="https://example.com",
        api_key="",
        wire_api=None,
        no_websocket=False,
    )
    with pytest.raises(SystemExit):
        _cmd_add(args)


# ── add (interactive) ───────────────────────────────────────────────────


def test_cmd_add_interactive(monkeypatch, tmp_path) -> None:
    paths = _patch_paths(monkeypatch, tmp_path)
    prompts = iter(["my-provider", "MyModel", "https://test.com", "sk-int-key", "responses", "yes"])
    monkeypatch.setattr("builtins.input", lambda _="": next(prompts))
    monkeypatch.setattr("getpass.getpass", lambda _="": next(prompts))

    args = argparse.Namespace(
        provider_id=None,
        model_providers=None,
        base_url=None,
        api_key=None,
        wire_api=None,
        no_websocket=False,
    )
    assert _cmd_add(args) == 0
    target = paths["provider_dir"] / "my-provider.toml"
    assert target.exists()
    doc = tomlkit.parse(target.read_text(encoding="utf-8"))
    assert doc["base_url"] == "https://test.com"


# ── claude init ─────────────────────────────────────────────────────────


def test_cmd_claude_init_creates_default_providers(monkeypatch, tmp_path, capsys) -> None:
    _patch_paths(monkeypatch, tmp_path)
    monkeypatch.setattr("cxf.cli._write_claude_provider", lambda p: None)

    assert _cmd_claude_init(None) == 0
    captured = capsys.readouterr()
    assert "initialized" in captured.out.lower()


def test_cmd_claude_init_with_name(monkeypatch, tmp_path, capsys) -> None:
    _patch_paths(monkeypatch, tmp_path)
    monkeypatch.setattr("cxf.cli._write_claude_provider", lambda p: None)

    assert _cmd_claude_init("custom") == 0
    captured = capsys.readouterr()
    assert "initialized" in captured.out.lower()


# ── claude use ──────────────────────────────────────────────────────────


def test_cmd_claude_use_switches_provider(monkeypatch, tmp_path, capsys) -> None:
    paths = _patch_paths(monkeypatch, tmp_path)
    _write_provider(
        Provider(
            provider_id="deepseek",
            model_providers="OpenAI",
            base_url="https://api.deepseek.com/anthropic",
            api_key="sk-test",
            wire_api="responses",
            requires_openai_auth=True,
            websocket=True,
        )
    )

    # Write a claude provider toml
    claude_path = paths["claude_provider_dir"] / "deepseek.toml"
    claude_path.parent.mkdir(parents=True, exist_ok=True)
    toml_doc = tomlkit.document()
    env_tbl = tomlkit.table()
    env_tbl.add("ANTHROPIC_BASE_URL", "https://api.deepseek.com/anthropic")
    env_tbl.add("ANTHROPIC_AUTH_TOKEN", "sk-test")
    env_tbl.add("ANTHROPIC_MODEL", "deepseek-v4-pro[1m]")
    toml_doc.add("env", env_tbl)
    claude_path.write_text(tomlkit.dumps(toml_doc), encoding="utf-8")

    monkeypatch.setattr("cxf.cli._write_json", lambda path, data: None)

    assert _cmd_claude_use("deepseek") == 0


def test_cmd_claude_use_no_arg_returns_1(capsys) -> None:
    rc = _cmd_claude_use(None)
    assert rc == 1
    captured = capsys.readouterr()
    assert "usage:" in captured.out


# ── claude status ───────────────────────────────────────────────────────


def test_cmd_claude_status_controlled(monkeypatch, tmp_path, capsys) -> None:
    paths = _patch_paths(monkeypatch, tmp_path)
    # Write settings with CXF_CLAUDE_PROVIDER
    claude_settings = {
        "env": {
            "CXF_CLAUDE_PROVIDER": "deepseek",
            "ANTHROPIC_BASE_URL": "https://api.deepseek.com/anthropic",
            "ANTHROPIC_AUTH_TOKEN": "sk-test",
        }
    }
    paths["claude_settings_path"].write_text(json.dumps(claude_settings), encoding="utf-8")

    # Write claude provider file
    claude_prov = ClaudeProvider(
        "deepseek",
        {
            "ANTHROPIC_BASE_URL": "https://api.deepseek.com/anthropic",
            "ANTHROPIC_AUTH_TOKEN": "sk-test",
        },
    )
    from cxf.claude import _write_claude_provider

    _write_claude_provider(claude_prov)

    assert _cmd_claude_status() == 0
    captured = capsys.readouterr()
    assert "yes" in captured.out


def test_cmd_claude_status_no_env(monkeypatch, tmp_path, capsys) -> None:
    paths = _patch_paths(monkeypatch, tmp_path)
    paths["claude_settings_path"].write_text('{"env": {}}', encoding="utf-8")
    assert _cmd_claude_status() == 1
    captured = capsys.readouterr()
    assert "no" in captured.out


# ── claude remove ───────────────────────────────────────────────────────


def test_cmd_claude_remove_deletes_provider(monkeypatch, tmp_path) -> None:
    paths = _patch_paths(monkeypatch, tmp_path)
    target = paths["claude_provider_dir"] / "deepseek.toml"
    target.write_text('[env]\nANTHROPIC_BASE_URL = "https://example.com"\n', encoding="utf-8")

    monkeypatch.setattr("builtins.input", lambda _="": "y")
    assert _cmd_claude_remove("deepseek") == 0
    assert not target.exists()


def test_cmd_claude_remove_aborts(monkeypatch, tmp_path) -> None:
    paths = _patch_paths(monkeypatch, tmp_path)
    target = paths["claude_provider_dir"] / "deepseek.toml"
    target.write_text('[env]\nANTHROPIC_BASE_URL = "https://example.com"\n', encoding="utf-8")

    monkeypatch.setattr("builtins.input", lambda _="": "n")
    assert _cmd_claude_remove("deepseek") == 1
    assert target.exists()


def test_cmd_claude_remove_yes_flag(monkeypatch, tmp_path) -> None:
    paths = _patch_paths(monkeypatch, tmp_path)
    target = paths["claude_provider_dir"] / "deepseek.toml"
    target.write_text('[env]\nANTHROPIC_BASE_URL = "https://example.com"\n', encoding="utf-8")

    assert _cmd_claude_remove("deepseek", yes=True) == 0
    assert not target.exists()

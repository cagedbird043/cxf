import tomlkit

import pytest

from cxf.cli import Provider, _apply_provider, _prompt, _read_provider_probe, _set_provider_probe, build_parser, main


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
    monkeypatch.setattr("cxf.cli.PROVIDERS_DIR", tmp_path)

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

import tomlkit

from cxf.cli import Provider, _apply_provider, build_parser


def test_parser_accepts_run_provider() -> None:
    args = build_parser().parse_args(["use", "timi"])
    assert args.command == "use"
    assert args.provider == "timi"


def test_parser_accepts_zsh_completion() -> None:
    args = build_parser().parse_args(["completion", "zsh"])
    assert args.command == "completion"
    assert args.shell == "zsh"


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

    assert result["cxf_provider"] == "timi"
    assert result["model_provider"] == "OpenAI"
    assert result["model_providers"]["OpenAI"]["base_url"] == "https://timicc.com"
    assert "Other" not in result["model_providers"]
    assert result["projects"]["/home/user/project"]["trust_level"] == "trusted"
    assert result["features"]["shell_tool"] is True
    assert result["features"]["responses_websockets_v2"] is True

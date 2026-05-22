from cxcfg.cli import build_parser


def test_parser_accepts_run_provider() -> None:
    args = build_parser().parse_args(["run", "timi"])
    assert args.command == "run"
    assert args.provider == "timi"

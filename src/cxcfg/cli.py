from __future__ import annotations

import argparse
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cxcfg",
        description="Terminal-first Codex config manager.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="Create the local cxcfg config skeleton.")
    sub.add_parser("doctor", help="Inspect the current Codex config state.")

    run_parser = sub.add_parser("run", help="Launch Codex with a selected provider.")
    run_parser.add_argument("provider", help="Provider identifier.")

    sub.add_parser("snapshot", help="Snapshot the current Codex config state.")
    sub.add_parser("restore", help="Restore the latest Codex config snapshot.")
    return parser


def _config_root() -> Path:
    return Path.home() / ".config" / "cxcfg"


def _handle_init() -> int:
    root = _config_root()
    root.mkdir(parents=True, exist_ok=True)
    providers = root / "providers.toml"
    config = root / "config.toml"
    if not providers.exists():
        providers.write_text(
            "# cxcfg providers\n"
            "# Example:\n"
            "# [providers.timi]\n"
            '# base_url = "https://timicc.com"\n'
            '# model = "gpt-5.4"\n'
            '# wire_api = "responses"\n'
            "# supports_websockets = true\n"
        )
    if not config.exists():
        config.write_text(
            "[runtime]\n"
            'mode = "ephemeral"\n'
            'default_provider = ""\n'
        )
    print(root)
    return 0


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "init":
        return _handle_init()
    if args.command == "doctor":
        print("not implemented yet")
        return 0
    if args.command == "run":
        print(f"not implemented yet: {args.provider}")
        return 0
    if args.command == "snapshot":
        print("not implemented yet")
        return 0
    if args.command == "restore":
        print("not implemented yet")
        return 0
    raise SystemExit(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())

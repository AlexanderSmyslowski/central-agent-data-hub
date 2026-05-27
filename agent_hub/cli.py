"""Command line interface for Central Agent Data Hub."""

from __future__ import annotations

import argparse
import os
import sys

from agent_hub.export_obsidian import export_all


def run_export(_args: argparse.Namespace) -> int:
    missing = [
        name
        for name in ("DATABASE_URL", "OBSIDIAN_EXPORT_DIR")
        if not os.environ.get(name)
    ]
    if missing:
        print(
            "Error: missing required environment variable(s): "
            + ", ".join(missing),
            file=sys.stderr,
        )
        print(
            "Set DATABASE_URL to your PostgreSQL connection string and "
            "OBSIDIAN_EXPORT_DIR to the target Obsidian export directory.",
            file=sys.stderr,
        )
        return 2

    try:
        written = export_all()
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    print(f"Export complete: wrote {len(written)} Markdown files.")
    for path in written:
        print(path)
    return 0


def not_implemented(args: argparse.Namespace) -> int:
    print(f"Command '{args.command}' is not implemented yet.", file=sys.stderr)
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-hub",
        description="Central Agent Data Hub command line tools.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    export_parser = subparsers.add_parser(
        "export",
        help="Export database rows to Obsidian Markdown files.",
    )
    export_parser.set_defaults(func=run_export)

    for name in ("init", "import", "check", "status"):
        placeholder = subparsers.add_parser(
            name,
            help="Not implemented yet.",
        )
        placeholder.set_defaults(func=not_implemented)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

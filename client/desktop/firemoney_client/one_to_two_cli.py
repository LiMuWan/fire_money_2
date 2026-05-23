"""Local command entry point for the one-to-two strategy workflow."""

from __future__ import annotations

from .cli.parser import build_one_to_two_parser
from .cli.runtime import run_one_to_two_command


def main() -> None:
    args = build_one_to_two_parser().parse_args()
    run_one_to_two_command(args)


if __name__ == "__main__":
    main()

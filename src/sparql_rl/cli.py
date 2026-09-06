"""Command-line package information."""
import argparse

from .spec_version import SPEC_DATE, __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sparql-rl")
    parser.add_argument(
        "--version",
        action="version",
        version=f"sparql-rl {__version__}; SPARQL 1.2 RL target: {SPEC_DATE}",
    )
    parser.parse_args(argv)
    return 0

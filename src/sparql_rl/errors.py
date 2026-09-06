"""Processor errors, kept separate from per-solution expression failures."""

from sparql_rl.rdf.parser import ParseError


class WellFormednessError(ValueError):
    pass


class StratificationError(ValueError):
    pass


class ImportResolutionError(ValueError):
    pass


class ExpressionError(ValueError):
    pass


__all__ = [
    "ExpressionError",
    "ImportResolutionError",
    "ParseError",
    "StratificationError",
    "WellFormednessError",
]

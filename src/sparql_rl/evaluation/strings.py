"""SPARQL string argument kinds and language compatibility."""

from sparql_rl.errors import ExpressionError
from sparql_rl.rdf.parser import XSD_NS, Literal, Node


def require_string_literal(node: Node) -> str:
    if not isinstance(node, Literal) or (
        not node.lang and node.datatype not in (None, XSD_NS + "string")
    ):
        raise ExpressionError("string literal required")
    return node.value


def require_xsd_string(node: Node) -> str:
    require_string_literal(node)
    assert isinstance(node, Literal)
    if node.lang is not None or node.direction is not None:
        raise ExpressionError("xsd:string required")
    return node.value


def compatible_strings(first: Node, second: Node) -> tuple[str, str]:
    a, b = require_string_literal(first), require_string_literal(second)
    assert isinstance(first, Literal) and isinstance(second, Literal)
    if second.lang is not None and (first.lang, first.direction) != (
        second.lang,
        second.direction,
    ):
        raise ExpressionError("incompatible string arguments")
    return a, b

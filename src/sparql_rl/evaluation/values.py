"""SPARQL sameValue fallback, distinct from RDF term identity and numeric '='."""

import math

from sparql_rl.errors import ExpressionError
from sparql_rl.rdf.parser import IRI, XSD_NS, BNode, Literal, Node, TripleTerm

from .datatypes import (
    NUMERIC,
    boolean_value,
    number,
    promoted,
    temporal_value,
)


def literal_kind(node: Literal) -> str:
    if node.datatype in NUMERIC:
        number(node)
        return "numeric"
    if node.datatype == XSD_NS + "boolean":
        boolean_value(node)
        return "boolean"
    for name in ("dateTime", "date", "time", "duration", "dayTimeDuration", "yearMonthDuration"):
        if node.datatype == XSD_NS + name:
            temporal_value(name, node.value)
            return name
    if node.lang:
        return "language"
    if node.datatype in (None, XSD_NS + "string"):
        return "string"
    return "unknown"


def same_value(a: Node, b: Node) -> bool:
    if a == b:
        return True
    if isinstance(a, (IRI, BNode)) or isinstance(b, (IRI, BNode)):
        return False
    if isinstance(a, TripleTerm) and isinstance(b, TripleTerm):
        # Evaluate all pairs: an error takes precedence over a false component.
        pairs = [
            same_value(x, y)
            for x, y in zip(
                (a.subject, a.predicate, a.object), (b.subject, b.predicate, b.object)
            )
        ]
        return all(pairs)
    if isinstance(a, TripleTerm) or isinstance(b, TripleTerm):
        return False
    assert isinstance(a, Literal) and isinstance(b, Literal)
    kind_a, kind_b = literal_kind(a), literal_kind(b)
    if "unknown" in (kind_a, kind_b):
        raise ExpressionError(
            "cannot determine equality of unrecognized datatype values"
        )
    if kind_a != kind_b:
        return False
    if kind_a == "numeric":
        x, y = promoted(a, b)
        return x == y or (
            isinstance(x, float)
            and isinstance(y, float)
            and math.isnan(x)
            and math.isnan(y)
        )
    if kind_a == "boolean":
        return boolean_value(a) == boolean_value(b)
    if kind_a in {"dateTime", "date", "time", "duration", "dayTimeDuration", "yearMonthDuration"}:
        return temporal_value(kind_a, a.value) == temporal_value(kind_b, b.value)
    return a == b

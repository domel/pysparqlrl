"""SPARQL expressions with explicit dispatch and per-solution errors."""

import math
import operator
import re
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from decimal import Decimal
from urllib.parse import quote
from uuid import uuid4

import regex as safe_regex

from sparql_rl.errors import ExpressionError
from sparql_rl.model import Expression, Variable
from sparql_rl.rdf.parser import (
    IRI,
    XSD_NS,
    BNode,
    Literal,
    Node,
    TripleTerm,
    resolve_iri_reference,
    validate_iri,
)
from sparql_rl.rdf.terms import make_triple_term

from .datatypes import (
    INTEGER_RANGES,
    NUMERIC,
    arithmetic,
    boolean_value,
    cast_literal,
    datetime_parts,
    datetime_value,
    floating_lexical,
    number,
    promoted,
)
from .strings import compatible_strings, require_string_literal, require_xsd_string
from .values import same_value


class FunctionRegistry:
    def __init__(self) -> None:
        self.functions: dict[str, Callable[..., Node]] = {}

    def register(self, iri: str, function: Callable[..., Node]) -> None:
        self.functions[iri] = function


@dataclass
class Context:
    now: Literal = field(
        default_factory=lambda: Literal(
            datetime.now(UTC).isoformat(), datatype=XSD_NS + "dateTime"
        )
    )
    functions: FunctionRegistry = field(default_factory=FunctionRegistry)
    base_iri: str | None = None
    # Retain mappings for this rule invocation so their identities cannot be reused.
    blank_nodes: dict[int, tuple[dict[Variable, Node], dict[str, BNode]]] = field(
        default_factory=dict
    )

    def for_rule(self, base_iri: str | None) -> "Context":
        return replace(self, base_iri=base_iri, blank_nodes={})


def literal(value: object) -> Literal:
    if isinstance(value, bool):
        return Literal("true" if value else "false", datatype=XSD_NS + "boolean")
    if isinstance(value, int):
        return Literal(str(value), datatype=XSD_NS + "integer")
    if isinstance(value, float):
        return Literal(floating_lexical(value), datatype=XSD_NS + "double")
    if isinstance(value, Decimal):
        return Literal(str(value), datatype=XSD_NS + "decimal")
    return Literal(str(value))


def ebv(node: Node) -> bool:
    if not isinstance(node, Literal):
        raise ExpressionError("term has no effective boolean value")
    if node.datatype == XSD_NS + "boolean":
        if node.value not in {"true", "false", "1", "0"}:
            raise ExpressionError("invalid boolean")
        return node.value in {"true", "1"}
    if node.datatype in NUMERIC:
        value = number(node)
        return not (isinstance(value, float) and math.isnan(value)) and value != 0
    if node.datatype in (None, XSD_NS + "string") and node.lang is None:
        return bool(node.value)
    raise ExpressionError("literal has no effective boolean value")


def string_result(value: str, original: Node) -> Literal:
    assert isinstance(original, Literal)
    return Literal(
        value,
        lang=original.lang,
        direction=original.direction,
        datatype=original.datatype,
    )


def equal(a: Node, b: Node) -> bool:
    if isinstance(a, Literal) and isinstance(b, Literal):
        if a.datatype in NUMERIC and b.datatype in NUMERIC:
            return operator.eq(*promoted(a, b))
        if a.datatype == b.datatype == XSD_NS + "boolean":
            return ebv(a) == ebv(b)
        if a.datatype == b.datatype == XSD_NS + "dateTime":
            return datetime_value(a.value) == datetime_value(b.value)
    return same_value(a, b)


def evaluate(
    expr: Expression | Node, solution: dict[Variable, Node], context: Context
) -> Node:
    try:
        return _evaluate(expr, solution, context)
    except (
        ArithmeticError,
        ValueError,
        TypeError,
        IndexError,
        KeyError,
        re.error,
        safe_regex.error,
        TimeoutError,
    ) as error:
        if isinstance(error, ExpressionError):
            raise
        raise ExpressionError(str(error)) from error


def _evaluate(
    expr: Expression | Node, solution: dict[Variable, Node], context: Context
) -> Node:
    if isinstance(expr, Variable):
        return solution[expr]
    if isinstance(expr, TripleTerm):
        predicate = evaluate(expr.predicate, solution, context)
        if not isinstance(predicate, IRI):
            raise ExpressionError("triple predicate must be an IRI")
        return make_triple_term(
            evaluate(expr.subject, solution, context),
            predicate,
            evaluate(expr.object, solution, context),
        )
    if not isinstance(expr, Expression):
        return expr
    op, args = expr.operator, expr.arguments

    def ev(index: int) -> Node:
        return evaluate(args[index], solution, context)

    if op == "IF":
        if len(args) != 3:
            raise ExpressionError("IF requires three arguments")
        return ev(1 if ebv(ev(0)) else 2)
    if op in {"&&", "||"}:
        left_error = None
        try:
            left = ebv(ev(0))
            if left == (op == "||"):
                return literal(left)
        except ExpressionError as error:
            left_error = error
        right = ebv(ev(1))
        if right == (op == "||"):
            return literal(right)
        if left_error:
            raise left_error
        return literal(right)
    if op in {"IN", "NOT IN"}:
        member = ev(0)
        failure = None
        for index in range(1, len(args)):
            try:
                if equal(member, ev(index)):
                    return literal(op == "IN")
            except ExpressionError as error:
                failure = error
        if failure:
            raise failure
        return literal(op == "NOT IN")
    values = [ev(i) for i in range(len(args))]
    if op == "NOW":
        return context.now
    if op in {"UUID", "STRUUID"}:
        uuid_value = str(uuid4())
        return IRI("urn:uuid:" + uuid_value) if op == "UUID" else Literal(uuid_value)
    if op == "BNODE":
        if not values:
            return BNode(uuid4().hex)
        _, nodes = context.blank_nodes.setdefault(id(solution), (solution, {}))
        return nodes.setdefault(require_xsd_string(values[0]), BNode(uuid4().hex))
    if op == "CONCAT":
        joined = "".join(require_string_literal(v) for v in values)
        if values and all(
            isinstance(v, Literal)
            and isinstance(values[0], Literal)
            and v.lang == values[0].lang
            and v.direction == values[0].direction
            for v in values
        ):
            return string_result(joined, values[0])
        return Literal(joined)
    if op in context.functions.functions:
        return context.functions.functions[op](*values)
    a = values[0]
    if op.startswith(XSD_NS):
        if len(values) != 1:
            raise ExpressionError("constructor requires one argument")
        return cast_literal(op, a)
    if op == "unary!":
        return literal(not ebv(a))
    if op in {"unary+", "unary-"}:
        numeric = number(a)
        if op == "unary-":
            numeric = (
                numeric.copy_negate() if isinstance(numeric, Decimal) else -numeric
            )
        return literal(numeric)
    if op in {"+", "-", "*", "/"}:
        return arithmetic(op, a, values[1])
    if op in {"=", "!="}:
        return literal(equal(a, values[1]) == (op == "="))
    if op in {"<", ">", "<=", ">="}:
        b = values[1]
        compare = {
            "<": operator.lt,
            ">": operator.gt,
            "<=": operator.le,
            ">=": operator.ge,
        }[op]
        if isinstance(a, Literal) and isinstance(b, Literal):
            if a.datatype in NUMERIC and b.datatype in NUMERIC:
                return literal(compare(*promoted(a, b)))
            if a.datatype == b.datatype == XSD_NS + "boolean":
                return literal(compare(boolean_value(a), boolean_value(b)))
            if a.datatype == b.datatype == XSD_NS + "dateTime":
                return literal(
                    compare(datetime_value(a.value), datetime_value(b.value))
                )
        return literal(compare(require_xsd_string(a), require_xsd_string(b)))
    if op == "SAMETERM":
        return literal(a == values[1])
    tests = {
        "ISIRI": IRI,
        "ISURI": IRI,
        "ISBLANK": BNode,
        "ISLITERAL": Literal,
        "ISTRIPLE": TripleTerm,
    }
    if op in tests:
        return literal(isinstance(a, tests[op]))
    if op == "ISNUMERIC":
        try:
            number(a)
            return literal(True)
        except ExpressionError:
            return literal(False)
    if op in {"HASLANG", "HASLANGDIR"}:
        return literal(
            isinstance(a, Literal) and bool(a.lang if op == "HASLANG" else a.direction)
        )
    if op == "TRIPLE":
        if not isinstance(values[1], IRI):
            raise ExpressionError("invalid triple term")
        return make_triple_term(a, values[1], values[2])
    if op in {"SUBJECT", "PREDICATE", "OBJECT"}:
        if not isinstance(a, TripleTerm):
            raise ExpressionError("triple term required")
        return {"SUBJECT": a.subject, "PREDICATE": a.predicate, "OBJECT": a.object}[op]
    if op == "STR":
        if not isinstance(a, (IRI, Literal)):
            raise ExpressionError("STR requires IRI or literal")
        return Literal(a.value)
    if op in {"IRI", "URI"}:
        if isinstance(a, IRI):
            return a
        iri_value = require_xsd_string(a)
        validate_iri(iri_value, require_absolute=False, allow_empty=True)
        if context.base_iri is not None:
            iri_value = resolve_iri_reference(context.base_iri, iri_value)
        validate_iri(iri_value, require_absolute=True, allow_empty=False)
        return IRI(iri_value)
    if op in {"LANG", "LANGDIR", "DATATYPE"}:
        if not isinstance(a, Literal):
            raise ExpressionError("literal required")
        if op == "LANG":
            return Literal(a.lang or "")
        if op == "LANGDIR":
            return Literal(a.direction or "")
        return IRI(
            a.datatype
            or (
                "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
                + ("dirLangString" if a.direction else "langString")
                if a.lang
                else XSD_NS + "string"
            )
        )
    if op in {"STRLANG", "STRLANGDIR"}:
        text = require_xsd_string(a)
        lang = require_xsd_string(values[1]).lower()
        direction = require_xsd_string(values[2]) if op == "STRLANGDIR" else None
        if not lang or (direction is not None and direction not in {"ltr", "rtl"}):
            raise ExpressionError("invalid language tag or base direction")
        return Literal(text, lang=lang, direction=direction)
    if op == "STRDT":
        if not isinstance(values[1], IRI):
            raise ExpressionError("datatype must be an IRI")
        return Literal(require_xsd_string(a), datatype=values[1].value)
    if op in {"ABS", "CEIL", "FLOOR", "ROUND"}:
        value = number(a)
        rounded = (
            abs(value)
            if op == "ABS"
            else math.ceil(value)
            if op == "CEIL"
            else math.floor(value)
            if op == "FLOOR"
            else math.floor(
                value + Decimal("0.5") if isinstance(value, Decimal) else value + 0.5
            )
        )
        assert isinstance(a, Literal)
        return Literal(str(rounded), datatype=a.datatype)
    if op in {"YEAR", "MONTH", "DAY", "HOURS", "MINUTES", "SECONDS", "TIMEZONE", "TZ"}:
        if not isinstance(a, Literal) or a.datatype != XSD_NS + "dateTime":
            raise ExpressionError("xsd:dateTime required")
        date, fraction = datetime_parts(a.value.strip())
        offset = date.utcoffset()
        if op == "TZ":
            return Literal(
                ""
                if offset is None
                else "Z"
                if offset.total_seconds() == 0
                else date.strftime("%z")[:3] + ":" + date.strftime("%z")[3:]
            )
        if op == "TIMEZONE":
            offset = date.utcoffset()
            if offset is None:
                raise ExpressionError("no timezone")
            minutes = int(offset.total_seconds() / 60)
            return Literal(
                ("-" if minutes < 0 else "")
                + f"PT{abs(minutes) // 60}H{abs(minutes) % 60}M",
                datatype=XSD_NS + "dayTimeDuration",
            )
        return literal(
            {
                "YEAR": date.year,
                "MONTH": date.month,
                "DAY": date.day,
                "HOURS": date.hour,
                "MINUTES": date.minute,
                "SECONDS": Decimal(str(date.second) + format(fraction, "f")[1:]),
            }[op]
        )
    text = require_string_literal(a)
    if op == "STRLEN":
        return literal(len(text))
    if op in {"UCASE", "LCASE"}:
        return string_result(text.upper() if op == "UCASE" else text.lower(), a)
    if op == "ENCODE_FOR_URI":
        return Literal(quote(text, safe="-._~"))
    if op == "SUBSTR":

        def position(node: Node) -> int:
            if not isinstance(node, Literal) or node.datatype not in {
                XSD_NS + t for t in INTEGER_RANGES
            }:
                raise ExpressionError("substring positions require an integer datatype")
            return int(number(node))

        start = position(values[1]) - 1
        end = start + position(values[2]) if len(values) == 3 else len(text)
        return string_result(text[max(0, start) : max(0, end)], a)
    if op in {"CONTAINS", "STRSTARTS", "STRENDS", "STRBEFORE", "STRAFTER"}:
        text, other = compatible_strings(a, values[1])
    else:
        other = require_xsd_string(values[1])
    if op == "LANGMATCHES":
        text = require_xsd_string(a)
        return literal(
            bool(text)
            if other == "*"
            else text.lower() == other.lower()
            or text.lower().startswith(other.lower() + "-")
        )
    if op in {"CONTAINS", "STRSTARTS", "STRENDS"}:
        return literal(
            other in text
            if op == "CONTAINS"
            else text.startswith(other)
            if op == "STRSTARTS"
            else text.endswith(other)
        )
    if op in {"STRBEFORE", "STRAFTER"}:
        if other not in text:
            return Literal("")
        return string_result(text.partition(other)[0 if op == "STRBEFORE" else 2], a)
    if op in {"REGEX", "REPLACE"}:
        flags_index = 2 if op == "REGEX" else 3
        flags_text = (
            require_xsd_string(values[flags_index]) if len(values) > flags_index else ""
        )
        flags = sum(
            {"i": re.IGNORECASE, "m": re.MULTILINE, "s": re.DOTALL, "x": re.VERBOSE}[f]
            for f in set(flags_text)
        )
        if op == "REGEX":
            return literal(
                safe_regex.search(other, text, flags, timeout=0.1) is not None
            )
        replacement = re.sub(r"\$(\d+)", r"\\g<\1>", require_xsd_string(values[2]))
        return string_result(
            safe_regex.sub(other, replacement, text, flags=flags, timeout=0.1), a
        )
    raise ExpressionError(f"unknown function: {op}")

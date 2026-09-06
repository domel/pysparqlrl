"""SPARQL expressions with explicit dispatch and per-solution errors."""

import math
import operator
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import quote
from uuid import uuid4

from sparql_rl.errors import ExpressionError
from sparql_rl.model import Expression, Variable
from sparql_rl.rdf.parser import IRI, XSD_NS, BNode, Literal, Node, TripleTerm

NUMERIC = {
    XSD_NS + x
    for x in (
        "integer",
        "decimal",
        "double",
        "float",
        "int",
        "long",
        "short",
        "byte",
        "nonNegativeInteger",
        "positiveInteger",
        "nonPositiveInteger",
        "negativeInteger",
        "unsignedInt",
        "unsignedLong",
        "unsignedShort",
        "unsignedByte",
    )
}


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
    blank_nodes: dict[tuple[int, str], BNode] = field(default_factory=dict)


def number(node: Node) -> Decimal | float:
    if not isinstance(node, Literal) or node.datatype not in NUMERIC:
        raise ExpressionError("numeric operand required")
    try:
        return (
            float(node.value)
            if node.datatype in {XSD_NS + "double", XSD_NS + "float"}
            else Decimal(node.value)
        )
    except (ValueError, InvalidOperation) as error:
        raise ExpressionError("invalid numeric literal") from error


def literal(value: object) -> Literal:
    if isinstance(value, bool):
        return Literal("true" if value else "false", datatype=XSD_NS + "boolean")
    if isinstance(value, int):
        return Literal(str(value), datatype=XSD_NS + "integer")
    if isinstance(value, float):
        return Literal(str(value), datatype=XSD_NS + "double")
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
        return not math.isnan(value) and value != 0
    if node.datatype in (None, XSD_NS + "string") or node.lang:
        return bool(node.value)
    raise ExpressionError("literal has no effective boolean value")


def string(node: Node) -> str:
    if not isinstance(node, Literal) or (
        node.datatype not in (None, XSD_NS + "string") and not node.lang
    ):
        raise ExpressionError("string literal required")
    return node.value


def equal(a: Node, b: Node) -> bool:
    if isinstance(a, Literal) and isinstance(b, Literal):
        if a.datatype in NUMERIC and b.datatype in NUMERIC:
            return number(a) == number(b)
        if a.datatype == b.datatype == XSD_NS + "boolean":
            return ebv(a) == ebv(b)
        if a == b:
            return True
        if a.datatype not in (None, XSD_NS + "string") and a.datatype != b.datatype:
            raise ExpressionError("incomparable literals")
    return a == b


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
        return TripleTerm(
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
        key = (id(solution), string(values[0]))
        return context.blank_nodes.setdefault(key, BNode(uuid4().hex))
    if op == "CONCAT":
        return Literal("".join(string(v) for v in values))
    if op in context.functions.functions:
        return context.functions.functions[op](*values)
    a = values[0]
    if op.startswith(XSD_NS):
        if not isinstance(a, (Literal, IRI)):
            raise ExpressionError("invalid cast")
        datatype = op[len(XSD_NS) :]
        text = a.value
        if datatype in {"integer", "int", "long"}:
            text = str(int(Decimal(text)))
        elif datatype in {"decimal", "double", "float"}:
            text = str(Decimal(text))
        elif datatype == "boolean":
            return literal(ebv(a))
        return Literal(text, datatype=None if datatype == "string" else op)
    if op == "unary!":
        return literal(not ebv(a))
    if op in {"unary+", "unary-"}:
        numeric = number(a) * (-1 if op == "unary-" else 1)
        return literal(
            int(numeric)
            if isinstance(a, Literal) and a.datatype == XSD_NS + "integer"
            else numeric
        )
    if op in {"+", "-", "*", "/"}:
        x, y = number(a), number(values[1])
        if isinstance(x, float) or isinstance(y, float):
            x, y = float(x), float(y)
        result = {
            "+": operator.add,
            "-": operator.sub,
            "*": operator.mul,
            "/": operator.truediv,
        }[op](x, y)
        if op != "/" and all(
            isinstance(v, Literal) and v.datatype == XSD_NS + "integer" for v in values
        ):
            return literal(int(result))
        return literal(result)
    if op in {"=", "!="}:
        return literal(equal(a, values[1]) == (op == "="))
    if op in {"<", ">", "<=", ">="}:
        b = values[1]
        cmp_x, cmp_y = (
            (number(a), number(b))
            if isinstance(a, Literal) and a.datatype in NUMERIC
            else (string(a), string(b))
        )
        return literal(
            {"<": operator.lt, ">": operator.gt, "<=": operator.le, ">=": operator.ge}[
                op
            ](cmp_x, cmp_y)
        )
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
        return TripleTerm(a, values[1], values[2])
    if op in {"SUBJECT", "PREDICATE", "OBJECT"}:
        if not isinstance(a, TripleTerm):
            raise ExpressionError("triple term required")
        return {"SUBJECT": a.subject, "PREDICATE": a.predicate, "OBJECT": a.object}[op]
    if op == "STR":
        if not isinstance(a, (IRI, Literal)):
            raise ExpressionError("STR requires IRI or literal")
        return Literal(a.value)
    if op in {"IRI", "URI"}:
        return a if isinstance(a, IRI) else IRI(string(a))
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
        return Literal(
            string(a),
            lang=string(values[1]).lower(),
            direction=string(values[2]) if op == "STRLANGDIR" else None,
        )
    if op == "STRDT":
        if not isinstance(values[1], IRI):
            raise ExpressionError("datatype must be an IRI")
        return Literal(string(a), datatype=values[1].value)
    if op in {"ABS", "CEIL", "FLOOR", "ROUND"}:
        value = number(a)
        return literal(
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
    if op in {"YEAR", "MONTH", "DAY", "HOURS", "MINUTES", "SECONDS", "TIMEZONE", "TZ"}:
        if not isinstance(a, Literal):
            raise ExpressionError("date/time literal required")
        date = datetime.fromisoformat(a.value)
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
                "SECONDS": date.second,
            }[op]
        )
    text = string(a)
    if op == "STRLEN":
        return literal(len(text))
    if op in {"UCASE", "LCASE"}:
        return Literal(
            text.upper() if op == "UCASE" else text.lower(),
            lang=a.lang if isinstance(a, Literal) else None,
        )
    if op == "ENCODE_FOR_URI":
        return Literal(quote(text, safe="-._~"))
    if op == "SUBSTR":
        start = math.floor(float(number(values[1])) + 0.5) - 1
        end = (
            start + math.floor(float(number(values[2])) + 0.5)
            if len(values) == 3
            else len(text)
        )
        return Literal(text[max(0, start) : max(0, end)])
    other = string(values[1])
    if op == "LANGMATCHES":
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
        return Literal(text.partition(other)[0 if op == "STRBEFORE" else 2])
    if op in {"REGEX", "REPLACE"}:
        flags_index = 2 if op == "REGEX" else 3
        flags_text = string(values[flags_index]) if len(values) > flags_index else ""
        flags = sum(
            {"i": re.IGNORECASE, "m": re.MULTILINE, "s": re.DOTALL, "x": re.VERBOSE}[f]
            for f in set(flags_text)
        )
        if op == "REGEX":
            return literal(re.search(other, text, flags) is not None)
        replacement = re.sub(r"\$(\d+)", r"\\g<\1>", string(values[2]))
        return Literal(re.sub(other, replacement, text, flags=flags))
    raise ExpressionError(f"unknown function: {op}")

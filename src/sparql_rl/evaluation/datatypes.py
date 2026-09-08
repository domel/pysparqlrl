"""Typed values, numeric promotion and XSD constructor validation."""

import math
import operator
import re
import struct
from datetime import UTC, datetime, timedelta
from decimal import (
    ROUND_CEILING,
    ROUND_FLOOR,
    ROUND_HALF_DOWN,
    ROUND_HALF_UP,
    Context,
    Decimal,
    localcontext,
)

from sparql_rl.errors import ExpressionError
from sparql_rl.rdf.parser import IRI, XSD_NS, Literal, Node

INTEGER_RANGES: dict[str, tuple[int | None, int | None]] = {
    "integer": (None, None),
    "long": (-(2**63), 2**63 - 1),
    "int": (-(2**31), 2**31 - 1),
    "short": (-(2**15), 2**15 - 1),
    "byte": (-128, 127),
    "nonNegativeInteger": (0, None),
    "positiveInteger": (1, None),
    "nonPositiveInteger": (None, 0),
    "negativeInteger": (None, -1),
    "unsignedLong": (0, 2**64 - 1),
    "unsignedInt": (0, 2**32 - 1),
    "unsignedShort": (0, 65535),
    "unsignedByte": (0, 255),
}
NUMERIC = {XSD_NS + name for name in (*INTEGER_RANGES, "decimal", "float", "double")}
DECIMAL_PATTERN = r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)"
ZONE = r"(?:Z|[+-](?:(?:0[0-9]|1[0-3]):[0-5][0-9]|14:00))?"
DATE = r"[0-9]{4}-[0-9]{2}-[0-9]{2}"
TIME = r"(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9](?:\.[0-9]+)?"
TIME = rf"(?:{TIME}|24:00:00(?:\.0+)?)"


def integer_value(text: str, datatype: str) -> int:
    if not re.fullmatch(r"[+-]?[0-9]+", text):
        raise ExpressionError("invalid integer lexical form")
    value = int(text)
    lower, upper = INTEGER_RANGES[datatype]
    if (lower is not None and value < lower) or (upper is not None and value > upper):
        raise ExpressionError("integer outside datatype range")
    return value


def number(node: Node) -> int | Decimal | float:
    if not isinstance(node, Literal) or node.datatype not in NUMERIC:
        raise ExpressionError("numeric operand required")
    name = node.datatype[len(XSD_NS) :]
    text = node.value.strip()
    if name in INTEGER_RANGES:
        return integer_value(text, name)
    if name == "decimal":
        if not re.fullmatch(DECIMAL_PATTERN, text):
            raise ExpressionError("invalid decimal lexical form")
        return Decimal(text)
    if not re.fullmatch(
        rf"(?:{DECIMAL_PATTERN}(?:[eE][+-]?[0-9]+)?|[+-]?INF|NaN)", text
    ):
        raise ExpressionError("invalid floating point lexical form")
    return binary32(float(text)) if name == "float" else float(text)


def promoted(a: Node, b: Node) -> tuple[int | Decimal | float, int | Decimal | float]:
    x, y = number(a), number(b)
    if isinstance(x, float) or isinstance(y, float):
        double = any(
            isinstance(v, Literal) and v.datatype == XSD_NS + "double" for v in (a, b)
        )
        return (
            (as_float(x), as_float(y))
            if double
            else (binary32(as_float(x)), binary32(as_float(y)))
        )
    return x, y


def as_float(value: Decimal | float) -> float:
    try:
        return float(value)
    except OverflowError:
        return -math.inf if value < 0 else math.inf


def binary32(value: float) -> float:
    try:
        return struct.unpack("!f", struct.pack("!f", value))[0]
    except OverflowError:
        return math.copysign(math.inf, value)


def numeric_result(value: Decimal | float, datatype: str) -> Literal:
    if datatype in (XSD_NS + "float", XSD_NS + "double"):
        floating = as_float(value)
        if datatype == XSD_NS + "float":
            floating = binary32(floating)
        return Literal(floating_lexical(floating), datatype=datatype)
    return Literal(str(value), datatype=datatype)


def unary_numeric(op: str, node: Node) -> Literal:
    n = number(node)
    assert isinstance(node, Literal) and node.datatype is not None
    if op == "unary-":
        n = n.copy_negate() if isinstance(n, Decimal) else -n
    datatype = (
        XSD_NS + "integer"
        if node.datatype[len(XSD_NS) :] in INTEGER_RANGES
        else node.datatype
    )
    return numeric_result(n, datatype)


def numeric_function(op: str, node: Node) -> Literal:
    n = number(node)
    assert isinstance(node, Literal) and node.datatype is not None
    if op == "ABS":
        result = n.copy_abs() if isinstance(n, Decimal) else abs(n)
    elif isinstance(n, float):
        if not math.isfinite(n) or n == 0:
            result = n
        else:
            rounded = math.ceil(n) if op == "CEIL" else math.floor(n)
            if op == "ROUND" and n - rounded >= 0.5:
                rounded += 1
            result = math.copysign(0.0, n) if rounded == 0 else float(rounded)
    elif isinstance(n, Decimal):
        rounding = (
            ROUND_CEILING
            if op == "CEIL"
            else ROUND_FLOOR
            if op == "FLOOR"
            else ROUND_HALF_DOWN
            if n < 0
            else ROUND_HALF_UP
        )
        result = n.to_integral_value(rounding=rounding)
    else:
        result = n
    return numeric_result(result, node.datatype)


def floating_lexical(value: float) -> str:
    if math.isnan(value):
        return "NaN"
    if math.isinf(value):
        return "INF" if value > 0 else "-INF"
    return str(value)


def arithmetic(op: str, a: Node, b: Node) -> Literal:
    x, y = promoted(a, b)
    function = {
        "+": operator.add,
        "-": operator.sub,
        "*": operator.mul,
        "/": operator.truediv,
    }[op]
    if isinstance(x, int) and isinstance(y, int) and op != "/":
        return Literal(str(function(x, y)), datatype=XSD_NS + "integer")
    if isinstance(x, float) or isinstance(y, float):
        if op == "/" and y == 0:
            result = (
                math.nan
                if x == 0 or math.isnan(x)
                else math.copysign(
                    math.inf, math.copysign(1.0, x) * math.copysign(1.0, y)
                )
            )
        else:
            result = function(float(x), float(y))
        datatype = (
            "double"
            if any(
                isinstance(v, Literal) and v.datatype == XSD_NS + "double"
                for v in (a, b)
            )
            else "float"
        )
        return numeric_result(result, XSD_NS + datatype)
    dx, dy = Decimal(x), Decimal(y)
    # Exact addition/subtraction/multiplication; division has at least 34 digits.
    precision = max(
        34,
        len(dx.as_tuple().digits) + len(dy.as_tuple().digits) + 2,
        max(dx.adjusted(), dy.adjusted())
        - min(int(dx.as_tuple().exponent), int(dy.as_tuple().exponent))
        + 3,
    )
    with localcontext(Context(prec=precision)):
        return Literal(str(function(dx, dy)), datatype=XSD_NS + "decimal")


def datetime_parts(text: str) -> tuple[datetime, Decimal]:
    if not re.fullmatch(rf"{DATE}T{TIME}{ZONE}", text):
        raise ExpressionError("invalid dateTime lexical form")
    fraction = re.search(r"\.[0-9]+", text)
    seconds = Decimal(fraction.group()) if fraction else Decimal(0)
    whole = re.sub(r"\.[0-9]+", "", text)
    midnight = "T24:" in whole
    whole = whole.replace("T24:", "T00:")
    date = datetime.fromisoformat(whole)
    if midnight:
        date += timedelta(days=1)
    return date, seconds


def datetime_value(text: str) -> tuple[datetime, Decimal]:
    date, seconds = datetime_parts(text)
    return date.replace(tzinfo=UTC) if date.tzinfo is None else date.astimezone(
        UTC
    ), seconds


def validate_temporal(name: str, text: str) -> None:
    if name == "dateTime":
        datetime_value(text)
    elif name == "date":
        if not re.fullmatch(rf"{DATE}{ZONE}", text):
            raise ExpressionError("invalid date lexical form")
        datetime_value(text[:10] + "T00:00:00" + text[10:])
    elif name == "time":
        datetime_value("2000-01-01T" + text)
    else:
        date_part = (
            r"(?:[0-9]+D)?"
            if name == "dayTimeDuration"
            else r"(?:[0-9]+Y)?(?:[0-9]+M)?(?:[0-9]+D)?"
        )
        pattern = (
            rf"-?P{date_part}(?:T(?:[0-9]+H)?(?:[0-9]+M)?(?:[0-9]+(?:\.[0-9]+)?S)?)?"
        )
        if (
            not re.fullmatch(pattern, text)
            or not re.search(r"[0-9]", text)
            or text.endswith("T")
        ):
            raise ExpressionError("invalid duration lexical form")


def cast_literal(datatype: str, node: Node) -> Literal:
    name = datatype[len(XSD_NS) :]
    if not isinstance(node, (Literal, IRI)):
        raise ExpressionError("invalid cast operand")
    if name == "string":
        return Literal(node.value)
    if not isinstance(node, Literal) or node.lang:
        raise ExpressionError("invalid cast operand")
    source = node.datatype
    text = node.value.strip()
    from_string = source in (None, XSD_NS + "string")
    if name in INTEGER_RANGES:
        if from_string:
            value = integer_value(text, name)
        elif source in NUMERIC or source == XSD_NS + "boolean":
            numeric = (
                boolean_value(node) if source == XSD_NS + "boolean" else number(node)
            )
            value = integer_value(str(int(numeric)), name)
        else:
            raise ExpressionError("invalid integer cast")
        return Literal(str(value), datatype=datatype)
    if name in ("decimal", "double", "float"):
        if from_string:
            number(Literal(text, datatype=datatype))
        elif source in NUMERIC or source == XSD_NS + "boolean":
            numeric = (
                boolean_value(node) if source == XSD_NS + "boolean" else number(node)
            )
            if isinstance(numeric, bool):
                numeric = int(numeric)
            if name == "decimal":
                if isinstance(numeric, float) and not math.isfinite(numeric):
                    raise ExpressionError("non-finite decimal cast")
                text = format(Decimal(str(numeric)), "f")
            else:
                text = (
                    floating_lexical(numeric)
                    if isinstance(numeric, float)
                    else str(numeric)
                )
        else:
            raise ExpressionError("invalid numeric cast")
        if name == "float":
            return numeric_result(number(Literal(text, datatype=datatype)), datatype)
        return Literal(text, datatype=datatype)
    if name == "boolean":
        if from_string or source == XSD_NS + "boolean":
            result = boolean_value(Literal(text, datatype=datatype))
        elif source in NUMERIC:
            n = number(node)
            result = n != 0 and not (isinstance(n, float) and math.isnan(n))
        else:
            raise ExpressionError("invalid boolean cast")
        return Literal("true" if result else "false", datatype=datatype)
    if name in ("dateTime", "date", "time", "duration", "dayTimeDuration"):
        if not from_string and source != datatype:
            raise ExpressionError("invalid temporal cast")
        validate_temporal(name, text)
        return Literal(text, datatype=datatype)
    raise ExpressionError(f"unknown constructor: {datatype}")


def boolean_value(node: Literal) -> bool:
    if node.value.strip() not in ("true", "false", "1", "0"):
        raise ExpressionError("invalid boolean lexical form")
    return node.value.strip() in ("true", "1")

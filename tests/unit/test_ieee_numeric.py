import pytest

from sparql_rl.evaluation.expressions import Context, evaluate
from sparql_rl.rdf.parser import XSD_NS, Literal
from sparql_rl.syntax.parser import RuleParser


def value(text):
    return evaluate(RuleParser(text).expression(), {}, Context())


def f(text, kind="float"):
    return f'"{text}"^^<{XSD_NS}{kind}>'


def test_binary32_arithmetic_and_promotions():
    assert value(f"{f('16777216')} + {f('1')}") == Literal(
        "16777216.0", datatype=XSD_NS + "float"
    )
    assert value(f"{f('16777217')} = {f('16777216')}").value == "true"
    assert value(f"{f('16777216')} + 1").value == "16777216.0"
    assert value(f"{f('16777216')} + 1e0").value == "16777217.0"
    assert value(f"{f('3.4e38')} * {f('2')}").value == "INF"


@pytest.mark.parametrize("kind", ["float", "double"])
@pytest.mark.parametrize(
    "a,b,expected",
    [
        ("1", "0", "INF"),
        ("1", "-0", "-INF"),
        ("-1", "-0", "INF"),
        ("0", "0", "NaN"),
        ("NaN", "0", "NaN"),
    ],
)
def test_ieee_division_by_zero(kind, a, b, expected):
    assert value(f"{f(a, kind)} / {f(b, kind)}") == Literal(
        expected, datatype=XSD_NS + kind
    )


@pytest.mark.parametrize("operator", ["+", "-"])
def test_unary_float_preserves_type(operator):
    result = value(f"{operator}{f('1.5')}")
    assert result.datatype == XSD_NS + "float"
    assert result.value == ("-1.5" if operator == "-" else "1.5")


@pytest.mark.parametrize("kind", ["float", "double"])
@pytest.mark.parametrize(
    "function,text,expected",
    [
        ("ABS", "-INF", "INF"),
        ("ABS", "-0", "0.0"),
        ("ABS", "NaN", "NaN"),
        ("ROUND", "NaN", "NaN"),
        ("ROUND", "INF", "INF"),
        ("ROUND", "-0.5", "-0.0"),
        ("ROUND", "-0", "-0.0"),
        ("CEIL", "-0.1", "-0.0"),
        ("CEIL", "INF", "INF"),
        ("FLOOR", "-INF", "-INF"),
        ("FLOOR", "-0", "-0.0"),
    ],
)
def test_numeric_functions_special_values(kind, function, text, expected):
    assert value(f"{function}({f(text, kind)})") == Literal(
        expected, datatype=XSD_NS + kind
    )

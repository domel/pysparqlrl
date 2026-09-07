import pytest

from sparql_rl.errors import ExpressionError
from sparql_rl.evaluation.expressions import Context, evaluate, literal
from sparql_rl.rdf.parser import XSD_NS, Literal
from sparql_rl.syntax.parser import RuleParser


def expression(text):
    parser = RuleParser(text)
    parser.context = "body"
    return evaluate(parser.expression(), {}, Context())


@pytest.mark.parametrize(
    "call",
    [
        'UCASE("hello"@en--ltr)',
        'SUBSTR("hello"@en--ltr,1)',
        'REPLACE("hello"@en--ltr,"e","E")',
        'CONCAT("hello"@en--ltr,"world"@en--ltr)',
    ],
)
def test_string_functions_preserve_language_and_direction(call):
    result = expression(call)
    assert result.lang == "en"
    assert result.direction == "ltr"


def test_boolean_datatype_constructor_uses_lexical_boolean():
    assert expression('<http://www.w3.org/2001/XMLSchema#boolean>("false")') == literal(
        False
    )
    with pytest.raises(ExpressionError):
        expression('<http://www.w3.org/2001/XMLSchema#boolean>("invalid")')


def test_unknown_datatype_function_is_expression_error():
    with pytest.raises(ExpressionError):
        expression('<http://www.w3.org/2001/XMLSchema#notAType>("x")')


def test_seconds_preserve_fraction():
    result = expression(
        'SECONDS("2026-09-02T10:20:30.125Z"^^<http://www.w3.org/2001/XMLSchema#dateTime>)'
    )
    assert result == Literal("30.125", datatype=XSD_NS + "decimal")


@pytest.mark.parametrize("call", ["ABS(-1)", "CEIL(1)", "FLOOR(1)", "ROUND(1)"])
def test_numeric_functions_preserve_integer(call):
    assert expression(call) == literal(1)


@pytest.mark.parametrize(
    "call,expected",
    [
        ('DATATYPE("x")', "http://www.w3.org/2001/XMLSchema#string"),
        ("STR(<urn:x>)", "urn:x"),
        ("STRUUID()", None),
        ("UUID()", None),
        ("BNODE()", None),
        ('BNODE("same")', None),
        ('IRI("urn:x")', "urn:x"),
        ("URI(<urn:x>)", "urn:x"),
        ('STRLANG("hello","EN")', "hello"),
        ('STRLANGDIR("hello","en","rtl")', "hello"),
        ('STRDT("x",<urn:datatype>)', "x"),
        ("SUBJECT(TRIPLE(<urn:a>,<urn:p>,1))", "urn:a"),
        ("PREDICATE(TRIPLE(<urn:a>,<urn:p>,1))", "urn:p"),
        ("OBJECT(TRIPLE(<urn:a>,<urn:p>,1))", "1"),
        ("isTRIPLE(TRIPLE(<urn:a>,<urn:p>,1))", "true"),
        ('<http://www.w3.org/2001/XMLSchema#double>("2")', "2"),
        ('<http://www.w3.org/2001/XMLSchema#decimal>("2")', "2"),
        (
            'TZ("2026-09-02T12:00:00Z"^^<http://www.w3.org/2001/XMLSchema#dateTime>)',
            "Z",
        ),
        (
            'TIMEZONE("2026-09-02T12:00:00+02:00"^^<http://www.w3.org/2001/XMLSchema#dateTime>)',
            "PT2H0M",
        ),
        ('"true"^^<http://www.w3.org/2001/XMLSchema#boolean> = true', "true"),
        ('"x" = "y"', "false"),
        ('STRBEFORE("a","z")', ""),
        ("(1/0) || false", ExpressionError),
        ("1 IN (1/0)", ExpressionError),
    ],
)
def test_function_families(call, expected):
    if expected is ExpressionError:
        with pytest.raises(ExpressionError):
            expression(call)
    else:
        result = expression(call)
        if expected is not None:
            assert result.value == expected


@pytest.mark.parametrize(
    "call",
    [
        "STR(<<(<urn:s> <urn:p> 1)>>)",
        "DATATYPE(<urn:x>)",
        "LANG(<urn:x>)",
        'STRDT("x","y")',
        "SUBJECT(1)",
        "TRIPLE(<urn:s>,1,2)",
        'ABS("x")',
        "STRLEN(<urn:x>)",
        "<urn:unknown>(1)",
        "<http://www.w3.org/2001/XMLSchema#integer>(TRIPLE(<urn:s>,<urn:p>,1))",
        '1 = "x"^^<urn:unknown>',
        'TIMEZONE("2026-09-02T12:00:00"^^<http://www.w3.org/2001/XMLSchema#dateTime>)',
        "YEAR(<urn:x>)",
        'REGEX("x","[")',
    ],
)
def test_function_type_errors(call):
    with pytest.raises(ExpressionError):
        expression(call)

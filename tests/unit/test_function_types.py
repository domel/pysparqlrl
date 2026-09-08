import pytest

from sparql_rl import infer
from sparql_rl.errors import ExpressionError
from sparql_rl.evaluation.expressions import Context, evaluate, literal
from sparql_rl.syntax.parser import RuleParser


def expression(text):
    parser = RuleParser(text)
    return evaluate(parser.expression(), {}, Context(base_iri="http://example/"))


@pytest.mark.parametrize(
    "call",
    [
        'IF("x"@en, 1, 2)',
        '!"x"@en--ltr',
        'IRI("path"@en)',
        'BNODE("x"@en)',
        'STRDT("x"@en, <urn:type>)',
        'STRLANG("abc", "")',
        'STRLANG("abc"@en, "en")',
        'STRLANGDIR("abc", "en", "LTR")',
        'STRLANGDIR("abc", "en", "sideways")',
        'STRLANGDIR("abc", "", "ltr")',
        'STRLANGDIR("abc", "en"@en, "ltr")',
        'LANGMATCHES("en"@en, "en")',
        'LANGMATCHES("en", "en"@en)',
        '"a"@en < "b"@fr',
        '"a"@en <= "b"@en',
        'REGEX("a", "a"@en)',
        'REGEX("a", "a", "i"@en)',
        'REPLACE("abc", "a", "b"@en)',
        'SUBSTR("abc", 2.4)',
        'SUBSTR("abc", 2e0)',
        'SUBSTR("abc", 1, 1.0)',
    ],
)
def test_function_argument_type_errors(call):
    with pytest.raises(ExpressionError):
        expression(call)
    assert not len(
        infer(f"RULE {{ <urn:s> <urn:p> ?v }} WHERE {{ SET(?v := {call}) }}")
    )


@pytest.mark.parametrize(
    "function",
    ["YEAR", "MONTH", "DAY", "HOURS", "MINUTES", "SECONDS", "TZ", "TIMEZONE"],
)
def test_date_extractors_require_datetime(function):
    with pytest.raises(ExpressionError):
        expression(f'{function}("2020-01-02T03:04:05Z")')


@pytest.mark.parametrize(
    "function", ["CONTAINS", "STRSTARTS", "STRENDS", "STRBEFORE", "STRAFTER"]
)
@pytest.mark.parametrize(
    "first,second,valid",
    [
        ('"abc"', '"b"', True),
        ('"abc"@en', '"b"', True),
        ('"abc"@en', '"b"@en', True),
        ('"abc"@en', '"b"@ja', False),
        ('"abc"', '"b"@en', False),
        ('"abc"@en--ltr', '"b"', True),
        ('"abc"@en--ltr', '"b"@en--ltr', True),
        ('"abc"@en--ltr', '"b"@en', False),
        ('"abc"@en--ltr', '"b"@en--rtl', False),
        ('"abc"@en', '"b"@en--ltr', False),
    ],
)
def test_string_compatibility_table(function, first, second, valid):
    call = f"{function}({first}, {second})"
    if valid:
        expression(call)
    else:
        with pytest.raises(ExpressionError):
            expression(call)


def test_date_extraction_retains_local_offset_and_fraction():
    date = '"2026-09-08T01:02:03.123456789+02:00"^^<http://www.w3.org/2001/XMLSchema#dateTime>'
    assert expression(f"HOURS({date})") == literal(1)
    assert expression(f"DAY({date})") == literal(8)
    assert expression(f"SECONDS({date})").value == "3.123456789"


def test_substr_integer_subtypes_and_negative_start():
    assert (
        expression('SUBSTR("abc", "2"^^<http://www.w3.org/2001/XMLSchema#int>)').value
        == "bc"
    )
    assert expression('SUBSTR("abc", -1, 3)').value == "a"

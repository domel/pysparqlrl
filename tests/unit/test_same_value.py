import pytest

from sparql_rl.errors import ExpressionError
from sparql_rl.evaluation.expressions import Context, evaluate
from sparql_rl.syntax.parser import RuleParser


def value(text):
    return evaluate(RuleParser(text).expression(), {}, Context()).value


@pytest.mark.parametrize(
    "text,expected",
    [
        ("<<( <urn:s> <urn:p> 123 )>> = <<( <urn:s> <urn:p> 123.0 )>>", "true"),
        (
            '<<( <urn:s> <urn:p> true )>> = <<( <urn:s> <urn:p> "1"^^<http://www.w3.org/2001/XMLSchema#boolean> )>>',
            "true",
        ),
        (
            '<<( <urn:s> <urn:p> "2026-09-09T01:00:00+01:00"^^<http://www.w3.org/2001/XMLSchema#dateTime> )>> = <<( <urn:s> <urn:p> "2026-09-09T00:00:00Z"^^<http://www.w3.org/2001/XMLSchema#dateTime> )>>',
            "true",
        ),
        (
            "sameTerm(<<( <urn:s> <urn:p> 123 )>>, <<( <urn:s> <urn:p> 123.0 )>>)",
            "false",
        ),
        (
            '"NaN"^^<http://www.w3.org/2001/XMLSchema#double> = "NaN"^^<http://www.w3.org/2001/XMLSchema#double>',
            "false",
        ),
        (
            '<<( <urn:s> <urn:p> "NaN"^^<http://www.w3.org/2001/XMLSchema#double> )>> = <<( <urn:s> <urn:p> "NaN"^^<http://www.w3.org/2001/XMLSchema#float> )>>',
            "true",
        ),
        ('"a"^^<urn:unknown> = "a"^^<urn:unknown>', "true"),
        ('"a"@en = "a"@fr', "false"),
        ('"a"@en = "a"', "false"),
        ('1 = "1"', "false"),
        ('<urn:s> = "a"^^<urn:unknown>', "false"),
        ("<<( <urn:s> <urn:p> 1 )>> = 1", "false"),
    ],
)
def test_same_value_and_same_term_are_distinct(text, expected):
    assert value(text) == expected


@pytest.mark.parametrize(
    "a,b",
    [
        ('"a"^^<urn:unknown>', '"b"^^<urn:unknown>'),
        ('"a"^^<urn:unknown>', '"a"'),
        ('"a"^^<urn:unknown>', "1"),
        (
            '<<( <urn:a> <urn:p> "a"^^<urn:unknown> )>>',
            '<<( <urn:b> <urn:q> "b"^^<urn:unknown> )>>',
        ),
        ('"bad"^^<http://www.w3.org/2001/XMLSchema#integer>', '"bad"'),
        ('"invalid"^^<http://www.w3.org/2001/XMLSchema#date>', '"invalid"'),
    ],
)
def test_same_value_errors_are_symmetric(a, b):
    for text in (f"{a} = {b}", f"{b} = {a}"):
        with pytest.raises(ExpressionError):
            value(text)

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


def test_bnode_is_fresh_across_rule_solutions():
    from sparql_rl import infer

    rules = "\n".join(
        f'RULE {{ <urn:s{i}> <urn:p> ?b }} WHERE {{ SET(?b := BNODE("key")) }}'
        for i in range(1000)
    )
    graph = infer(rules)
    assert len(graph) == 1000
    assert len({o for s, p, o in graph}) == 1000
    assert expression('sameTerm(BNODE("x"), BNODE("x"))') == literal(True)
    assert expression('sameTerm(BNODE("x"), BNODE("y"))') == literal(False)


def test_iri_uses_sequential_rule_base():
    from sparql_rl import infer
    from sparql_rl.rdf.parser import IRI

    graph = infer("""
        BASE <http://example/first/>
        RULE { <urn:a> <urn:p> ?v } WHERE { SET(?v := IRI("child")) }
        BASE <http://example/second/>
        RULE { <urn:b> <urn:p> ?v } WHERE { SET(?v := URI("../child")) }
    """)
    assert set(graph) == {
        (IRI("urn:a"), IRI("urn:p"), IRI("http://example/first/child")),
        (IRI("urn:b"), IRI("urn:p"), IRI("http://example/child")),
    }


@pytest.mark.parametrize("value", ["child", "http://example/a b", "http://[bad"])
def test_iri_requires_a_valid_absolute_result(value):
    with pytest.raises(ExpressionError):
        expression(f'IRI("{value}")')


def test_imported_rule_and_query_goal_keep_their_own_base(tmp_path):
    from sparql_rl import infer, parse_rules, query
    from sparql_rl.rdf.parser import IRI

    imported = tmp_path / "imported.srl"
    imported.write_text(
        'BASE <http://imported/> RULE { <urn:s> <urn:p> ?v } WHERE { SET(?v := IRI("child")) }'
    )
    rules = parse_rules(f"BASE <http://root/> IMPORTS <{imported.as_uri()}>")
    assert set(infer(rules)) == {
        (IRI("urn:s"), IRI("urn:p"), IRI("http://imported/child"))
    }
    result = query(rules, None, 'BASE <http://goal/> { SET(?v := IRI("child")) }')
    assert next(iter(result.bindings[0].values())) == IRI("http://goal/child")


@pytest.mark.parametrize(
    "call,expected",
    [
        ("1000000000000000000000000000001 + 1", 1000000000000000000000000000002),
        ("1000000000000000000000000000001 - 1", 1000000000000000000000000000000),
        ("1000000000000000000000000000001 * 2", 2000000000000000000000000000002),
        ("-1000000000000000000000000000001", -1000000000000000000000000000001),
        ('"2"^^<http://www.w3.org/2001/XMLSchema#int> + 1', 3),
    ],
)
def test_integer_arithmetic_is_exact(call, expected):
    assert expression(call) == literal(expected)


def test_decimal_arithmetic_does_not_inherit_caller_precision():
    from decimal import localcontext

    with localcontext() as context:
        context.prec = 2
        assert expression("12345.67 + 0.01") == Literal(
            "12345.68", datatype=XSD_NS + "decimal"
        )
        assert context.prec == 2


@pytest.mark.parametrize(
    "call",
    [
        "0.1e0 = 0.1",
        "0.1e0 <= 0.1",
        "false < true",
        "true >= false",
        '"2026-09-07T10:00:00Z"^^<http://www.w3.org/2001/XMLSchema#dateTime> = "2026-09-07T12:00:00+02:00"^^<http://www.w3.org/2001/XMLSchema#dateTime>',
        '"2026-09-07T10:00:00Z"^^<http://www.w3.org/2001/XMLSchema#dateTime> < "2026-09-07T12:01:00+02:00"^^<http://www.w3.org/2001/XMLSchema#dateTime>',
    ],
)
def test_typed_comparisons(call):
    assert expression(call) == literal(True)


@pytest.mark.parametrize(
    "call",
    [
        'integer("1.9")',
        'integer("1e2")',
        'int("2147483648")',
        'long("9223372036854775808")',
        'dateTime("not-a-date")',
        'dateTime("2026-02-30T12:00:00Z")',
        'dateTime("2026-09-07 12:00:00")',
        'date("2026-13-01")',
        'time("25:00:00")',
        'duration("bad")',
        'dayTimeDuration("P1Y")',
        'decimal("1e2")',
    ],
)
def test_invalid_constructor_fails_per_solution(call):
    from sparql_rl import infer

    rules = (
        "PREFIX xsd: <http://www.w3.org/2001/XMLSchema#> RULE { <urn:s> <urn:p> ?v } WHERE { SET(?v := xsd:"
        + call
        + ") }"
    )
    assert len(infer(rules)) == 0


@pytest.mark.parametrize(
    "call,expected",
    [
        ("integer(1.9)", "1"),
        ("integer(true)", "1"),
        ('int("-2147483648")', "-2147483648"),
        ('long("9223372036854775807")', "9223372036854775807"),
        ("boolean(0)", "false"),
        ("boolean(1)", "true"),
        ('boolean("1")', "true"),
        ("decimal(1e2)", "100.0"),
        ("decimal(true)", "1"),
        ("double(2)", "2"),
        ('dateTime("2026-09-07T24:00:00Z")', "2026-09-07T24:00:00Z"),
        ('date("2026-09-07+02:00")', "2026-09-07+02:00"),
        ('time("10:20:30.123Z")', "10:20:30.123Z"),
        ('duration("P1Y2M3DT4H5M6.7S")', "P1Y2M3DT4H5M6.7S"),
        ('dayTimeDuration("-P3DT1H")', "-P3DT1H"),
    ],
)
def test_valid_constructor_values(call, expected):
    name, arguments = call.split("(", 1)
    result = expression(f"<{XSD_NS}{name}>({arguments}")
    assert result == Literal(expected, datatype=XSD_NS + name)


@pytest.mark.parametrize(
    "call",
    [
        "integer(<urn:x>)",
        'integer("2"@en)',
        'integer("2026-09-07"^^<http://www.w3.org/2001/XMLSchema#date>)',
        'decimal("2026-09-07"^^<http://www.w3.org/2001/XMLSchema#date>)',
        'decimal("NaN"^^<http://www.w3.org/2001/XMLSchema#double>)',
        'boolean("2026-09-07"^^<http://www.w3.org/2001/XMLSchema#date>)',
        "dateTime(1)",
        "integer(1, 2)",
    ],
)
def test_constructor_rejects_incompatible_source_types(call):
    name, arguments = call.split("(", 1)
    with pytest.raises(ExpressionError):
        expression(f"<{XSD_NS}{name}>({arguments}")

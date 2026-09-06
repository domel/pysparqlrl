import pytest

from sparql_rl.analysis import PreparedRuleSet, build_dependency_graph, stratify
from sparql_rl.errors import ExpressionError
from sparql_rl.evaluation.engine import evaluate_rules
from sparql_rl.evaluation.expressions import Context, ebv, evaluate, literal
from sparql_rl.model import Expression
from sparql_rl.rdf.io import parse_data
from sparql_rl.rdf.parser import IRI, XSD_NS, Literal
from sparql_rl.syntax.parser import RuleParser, parse_rules
from sparql_rl.validation import validate_rules

P = "PREFIX : <urn:example:> "


def run(rules, data=""):
    rs = parse_rules(P + rules)
    validate_rules(rs)
    deps = build_dependency_graph(rs)
    return evaluate_rules(
        PreparedRuleSet(rs, deps, stratify(rs, deps)), parse_data(P + data)
    )


def test_recursive_closure_excludes_base():
    inferred = run(
        "RULE {?x :p ?z} WHERE {?x :p ?y . ?y :p ?z}", ":a :p :b . :b :p :c ."
    )
    assert set(inferred) == set(parse_data(P + ":a :p :c ."))


def test_run_once_blank_node_sharing():
    inferred = run("RULE {[] :p ?x; :q ?x} WHERE {?x :in 1}", ":a :in 1 . :b :in 1 .")
    assert len(inferred) == 4
    assert len({s for s, p, o in inferred}) == 2


def test_data_restricted_matching():
    rules = "DATA {:a :p :b} RULE {?x :q ?y} WHERE DATA {?x :p ?y}"
    assert len(run(rules)) == 1
    assert len(run(rules, ":a :p :b .")) == 1


def test_negation_after_lower_stratum():
    rules = "RULE {?s :ok ?o} WHERE {?s :p ?o NOT {?s :blocked ?o}} RULE {?s :blocked ?o} WHERE {?s :p ?o}"
    assert set(run(rules, ":a :p :b .")) == set(parse_data(P + ":a :blocked :b ."))


@pytest.mark.parametrize(
    "expression,expected",
    [
        ("1+2*3", 7),
        ("IF(true,2,1/0)", 2),
        ("1 IN (2,1)", True),
        ("1 NOT IN (2,3)", True),
        ("false && (1/0)", False),
        ("(1/0) && false", False),
        ("true || (1/0)", True),
        ("(1/0) || true", True),
        ('STRLEN("abc")', 3),
        ('CONTAINS("abc","b")', True),
        ('STRSTARTS("abc","a")', True),
        ('STRENDS("abc","c")', True),
        ('STRBEFORE("abc","b")', "a"),
        ('STRAFTER("abc","b")', "c"),
        ('UCASE("ab")', "AB"),
        ('LCASE("AB")', "ab"),
        ('CONCAT("a","b")', "ab"),
        ('SUBSTR("abcd",2,2)', "bc"),
        ('ENCODE_FOR_URI("a b")', "a%20b"),
        ('REGEX("abc","^a")', True),
        ('REPLACE("abc","b","x")', "axc"),
        ('LANG("hi"@en)', "en"),
        ('LANGDIR("hi"@en--rtl)', "rtl"),
        ('LANGMATCHES("en-US","en")', True),
        ("isIRI(<urn:x>)", True),
        ("isLiteral(1)", True),
        ('isNumeric("x")', False),
        ("sameTerm(<urn:x>,<urn:x>)", True),
        ('hasLANG("x"@en)', True),
        ('hasLANGDIR("x"@en--ltr)', True),
        (
            'YEAR("2026-09-02T10:20:30Z"^^<http://www.w3.org/2001/XMLSchema#dateTime>)',
            2026,
        ),
    ],
)
def test_expressions(expression, expected):
    parser = RuleParser(expression)
    parser.context = "body"
    result = evaluate(parser.expression(), {}, Context())
    assert result == literal(expected)


def test_now_is_stable():
    context = Context()
    assert evaluate(Expression("NOW", ()), {}, context) is evaluate(
        Expression("NOW", ()), {}, context
    )


@pytest.mark.parametrize(
    "node",
    [
        IRI("urn:x"),
        Literal("bad", datatype=XSD_NS + "integer"),
        Literal("bad", datatype=XSD_NS + "boolean"),
        Literal("x", datatype="urn:unknown"),
    ],
)
def test_ebv_errors(node):
    with pytest.raises(ExpressionError):
        ebv(node)

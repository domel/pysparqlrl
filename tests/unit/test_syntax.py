import pytest

from sparql_rl.errors import ParseError
from sparql_rl.model import AssignmentElement, Variable, variables
from sparql_rl.syntax.parser import parse_rules

P = "PREFIX : <urn:example:> "


def test_sequential_prologue_and_paths():
    rules = parse_rules(
        P
        + "RULE {?s :out ?o} WHERE {?s ^(:p/:q) ?o} PREFIX : <urn:other:> DATA {:a :p :b}"
    )
    assert len(rules.rules[0].body) == 2
    assert rules.data[0][0].value == "urn:other:a"
    assert any(
        v.value.startswith("@path")
        for e in rules.rules[0].body
        for v in variables(e.pattern)
    )


def test_set_expression_tree():
    rules = parse_rules(
        P + "RULE {?s :out ?v} WHERE {?s :p ?x SET(?v := IF(?x > 0, ?x*2, 0))}"
    )
    assert isinstance(rules.rules[0].body[-1], AssignmentElement)


@pytest.mark.parametrize(
    "text",
    [
        "DATA {?s <urn:p> <urn:o>}",
        "RULE {?s <urn:p> ?o} WHERE {?s <urn:p>* ?o}",
        "RULE {} WHERE {NOT {NOT {}}}",
        "RULE {} WHERE {SET(<urn:x> := 1)}",
        "RULE {} WHERE {FILTER(BOUND(?x))}",
        'VERSION "1.1"',
        "PREFIX : <relative>",
        "RULE {} WHERE {? <urn:p> <urn:o>}",
    ],
)
def test_invalid_syntax(text):
    with pytest.raises(ParseError):
        parse_rules(text)


def test_source_location():
    with pytest.raises(ParseError, match="rules.srl:2:"):
        parse_rules("\nINVALID", source_name="rules.srl")


def test_dollar_and_question_variables_are_identical():
    rule = parse_rules(P + "RULE {$s :out ?o} WHERE {?s :p $o}").rules[0]
    assert variables(rule.head) == {Variable("s"), Variable("o")}


@pytest.mark.parametrize("body", ["FILTER(true) .", "SET(?x := 1) .", "NOT {} ."])
def test_dot_after_non_triple_element(body):
    parse_rules(f"RULE {{}} WHERE {{{body}}}")


@pytest.mark.parametrize(
    "body",
    [
        "FILTER true",
        "FILTER ?x",
        'FILTER STR(1) = "1"',
        "SET(?x := [])",
        "SET(?x := (1 < 2 < 3))",
        "?s ?p/<urn:q> ?o",
        "?s <urn:p> <<( <urn:a> <urn:p>/<urn:q> <urn:b> )>>",
    ],
)
def test_reject_non_grammar_forms(body):
    with pytest.raises(ParseError):
        parse_rules(f"RULE {{}} WHERE {{{body}}}")


def test_nested_symmetric_triple_terms():
    parse_rules("DATA {<urn:s> <urn:p> <<( <<( 1 <urn:p> 2 )>> <urn:p> 3 )>>}")


def test_boolean_keywords_case_insensitive():
    parse_rules("DATA {<urn:s> <urn:p> TRUE, FALSE}")

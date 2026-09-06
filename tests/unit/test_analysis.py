import pytest

from sparql_rl.analysis import build_dependency_graph, stratify
from sparql_rl.analysis.dependency import Label, compatible
from sparql_rl.errors import StratificationError, WellFormednessError
from sparql_rl.model import Variable
from sparql_rl.rdf.parser import IRI
from sparql_rl.syntax.parser import parse_rules
from sparql_rl.validation import validate_rules

P = "PREFIX : <urn:example:> "


@pytest.mark.parametrize(
    "body,head",
    [
        ("?s :p ?o FILTER(?x > 1)", "?s :out ?o"),
        ("?s :p ?o SET(?s := 1)", "?s :out ?o"),
        ("?s :p ?o SET(?x := ?unbound)", "?s :out ?o"),
        ("?s :p ?o NOT {?s :p ?x}", "?s :out ?x"),
        ("?s :p ?o NOT {FILTER(?x > 0) ?s :p ?x}", "?s :out ?o"),
    ],
)
def test_variable_flow(body, head):
    rules = parse_rules(P + f"RULE {{{head}}} WHERE {{{body}}}")
    with pytest.raises(WellFormednessError):
        validate_rules(rules)


def test_repeated_variables_in_compatibility():
    x = Variable("x")
    assert not compatible(
        (x, IRI("urn:p"), x), (IRI("urn:a"), IRI("urn:p"), IRI("urn:b"))
    )
    assert compatible((x, IRI("urn:p"), x), (IRI("urn:a"), IRI("urn:p"), IRI("urn:a")))


def test_closed_cycle():
    rules = parse_rules(P + "RULE {?x :p ?y} WHERE {?x :p ?y SET(?z := 1)}")
    graph = build_dependency_graph(rules)
    assert graph.edges == ((0, 0, Label.CLOSED),)
    with pytest.raises(StratificationError):
        stratify(rules, graph)


def test_data_matching_has_no_runtime_dependencies():
    rules = parse_rules(P + "RULE {?x :p ?v} WHERE DATA {?x :p ?o SET(?v := 1)}")
    assert not build_dependency_graph(rules).edges

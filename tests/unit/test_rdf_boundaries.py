import pytest

from sparql_rl import (
    IRI,
    BNode,
    Graph,
    Literal,
    TripleTerm,
    Variable,
    infer,
    parse_rules,
)
from sparql_rl.errors import RDFInputError


@pytest.mark.parametrize(
    "subject",
    [
        Literal("bad"),
        TripleTerm(IRI("urn:s"), IRI("urn:p"), Literal("x")),
        Variable("s"),
    ],
)
def test_graph_rejects_non_rdf_subject(subject):
    with pytest.raises(RDFInputError):
        Graph([(subject, IRI("urn:p"), Literal("x"))])


def test_graph_rejects_non_rdf_nested_term_and_predicate():
    for triple in [
        (IRI("urn:s"), Variable("p"), Literal("x")),
        (
            IRI("urn:s"),
            IRI("urn:p"),
            TripleTerm(Literal("bad"), IRI("urn:p"), Literal("x")),
        ),
    ]:
        with pytest.raises(RDFInputError):
            Graph([triple])


@pytest.mark.parametrize("subject", ['"bad"', "<<( <urn:s> <urn:p> 1 )>>"])
def test_invalid_template_is_parsed_but_not_generated(subject):
    rules = parse_rules(
        f"RULE {{ {subject} <urn:p> 1 . <urn:s> <urn:p> 2 }} WHERE {{}}"
    )
    assert len(rules.rules[0].head) == 2
    assert len(infer(rules)) == 1


@pytest.mark.parametrize(
    "expr",
    [
        'TRIPLE("bad", <urn:p>, 1)',
        '<<( "bad" <urn:p> 1 )>>',
        "TRIPLE(<<( <urn:s> <urn:p> 1 )>>, <urn:p>, 1)",
    ],
)
def test_invalid_triple_constructor_removes_solution(expr):
    assert not len(
        infer(f"RULE {{ <urn:s> <urn:p> ?t }} WHERE {{ SET(?t := {expr}) }}")
    )


def test_valid_nested_rdf_triples_remain_supported():
    b = BNode("b")
    assert (
        len(Graph([(b, IRI("urn:p"), TripleTerm(b, IRI("urn:p"), Literal("ok")))])) == 1
    )


def test_nested_turtle_reification_uses_reifier_subject():
    from sparql_rl.rdf.canonical import isomorphic
    from sparql_rl.rdf.io import parse_data

    actual = parse_data(
        "<< << <urn:s> <urn:p> <urn:o> >> <urn:q> <urn:z> >> <urn:r> 1 ."
    )
    expected = parse_data("""
        _:inner <http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies> <<( <urn:s> <urn:p> <urn:o> )>> .
        _:outer <http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies> <<( _:inner <urn:q> <urn:z> )>> ; <urn:r> 1 .
    """)
    assert isomorphic(actual, expected)

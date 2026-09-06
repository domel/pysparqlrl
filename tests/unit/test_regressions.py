import pytest

from sparql_rl import infer, parse_rules, query
from sparql_rl.errors import ParseError
from sparql_rl.rdf.parser import IRI, XSD_NS, Literal, TripleTerm


@pytest.mark.parametrize(
    "call", ["STR()", "NOW(1)", "IF(true,1)", 'REGEX("a")', "ABS(1,2)"]
)
def test_builtin_arity_is_syntax_error(call):
    with pytest.raises(ParseError):
        parse_rules(f"RULE {{}} WHERE {{FILTER({call})}}")


def test_symmetric_head_instantiation():
    result = infer("RULE {1 <urn:p> 2} WHERE {}")
    assert len(result) == 1
    assert next(iter(result))[0] == Literal("1", datatype=XSD_NS + "integer")


def test_triple_expression_substitution():
    result = infer(
        "RULE {<urn:s> <urn:p> ?t} WHERE {SET(?x := <urn:x>) SET(?t := <<( ?x <urn:p> 1 )>>)}"
    )
    assert next(iter(result))[2] == TripleTerm(
        IRI("urn:x"), IRI("urn:p"), Literal("1", datatype=XSD_NS + "integer")
    )


def test_numeric_unary_preserves_integer():
    result = infer("RULE {<urn:s> <urn:p> ?v} WHERE {SET(?v := -1)}")
    assert next(iter(result))[2] == Literal("-1", datatype=XSD_NS + "integer")


def test_language_tags_and_string_datatypes_compare_by_rdf_equality():
    result = infer(
        'RULE {<urn:s> <urn:q> 1} WHERE {<urn:s> <urn:p> "x"^^<http://www.w3.org/2001/XMLSchema#string>}',
        '<urn:s> <urn:p> "x" .',
    )
    assert len(result) == 1
    assert query(
        "DATA {}", '<urn:s> <urn:p> "hi"@EN .', '{<urn:s> <urn:p> "hi"@en}'
    ).boolean


def test_blank_node_generation_cannot_collide_with_later_label():
    rules = parse_rules("DATA {[] <urn:p> 1 . _:genid0 <urn:p> 2}")
    assert len({s for s, p, o in rules.data}) == 2

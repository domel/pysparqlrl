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


def test_data_blank_nodes_are_distinct_from_base():
    result = infer("DATA {_:same <urn:p> 1}", "_:same <urn:p> 2 .", include_base=True)
    assert len({s for s, p, o in result}) == 2


def test_triple_term_in_head_preserves_nested_variables():
    result = infer(
        "RULE {<urn:s> <urn:p> <<( ?x <urn:p> ?y )>>} WHERE {?x <urn:q> ?y}",
        "<urn:a> <urn:q> <urn:b> .",
    )
    assert next(iter(result))[2] == TripleTerm(IRI("urn:a"), IRI("urn:p"), IRI("urn:b"))


def test_import_cycle_uses_retrieval_uri_despite_declared_base(tmp_path):
    from sparql_rl.imports import ImportResolver

    source = tmp_path / "rules.srl"
    source.write_text(
        f"BASE <urn:other:> IMPORTS <{source.as_uri()}> DATA {{[] <urn:p> 1}}"
    )
    rules = parse_rules(source.read_text(), base_iri=source.as_uri())
    assert len(ImportResolver().resolve(rules).data) == 1

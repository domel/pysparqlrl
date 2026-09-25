from sparql_rl.api import QueryResult
from sparql_rl.model import Variable
from sparql_rl.rdf.parser import IRI, Literal, TripleTerm
from sparql_rl.serialization import binding_json, query_result_json


def test_triple_term_and_directional_literal_serialization():
    triple = TripleTerm(IRI("urn:s"), IRI("urn:p"), Literal("hello", lang="en", direction="ltr"))
    value = binding_json(triple)
    assert value["type"] == "triple"
    assert value["value"]["object"]["its:dir"] == "ltr"


def test_query_result_serialization():
    variable = Variable("x")
    result = query_result_json(QueryResult((variable,), ({variable: IRI("urn:x")},)))
    assert result["boolean"] is True
    assert result["results"]["bindings"][0]["x"] == {
        "type": "uri",
        "value": "urn:x",
    }

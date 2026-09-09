from sparql_rl import FunctionRegistry, Literal, query


def test_query_accepts_data_format_and_external_base():
    xml = '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns:e="urn:"><rdf:Description rdf:about="child"><e:p>value</e:p></rdf:Description></rdf:RDF>'
    assert query(
        "DATA {}",
        xml,
        '{ <http://example/child> <urn:p> "value" }',
        data_format="rdfxml",
        data_base_iri="http://example/",
    ).boolean


def test_query_shares_registry_and_now_between_rules_and_goal():
    registry = FunctionRegistry()
    registry.register("urn:label", lambda node: Literal(node.value.upper()))
    rules = 'RULE { <urn:s> <urn:p> ?v ; <urn:time> ?t } WHERE { SET(?v := <urn:label>("hello")) SET(?t := NOW()) }'
    goal = '{ <urn:s> <urn:p> ?v ; <urn:time> ?t FILTER(?v = <urn:label>("hello")) FILTER(?t = NOW()) }'
    assert query(rules, None, goal, function_registry=registry).boolean


def test_query_parses_data_once(monkeypatch):
    from sparql_rl import api
    from sparql_rl.rdf.io import parse_data

    calls = []

    def parse_once(data, **kwargs):
        calls.append(data)
        return parse_data(data, **kwargs)

    monkeypatch.setattr(api, "as_graph", parse_once)
    data = "[] <urn:p> <urn:o> ."
    result = query(
        "RULE { ?s <urn:q> ?o } WHERE { ?s <urn:p> ?o }",
        data,
        "{ ?s <urn:q> <urn:o> NOT DATA { ?s <urn:p> <urn:other> } }",
    )
    assert result.boolean
    assert calls == [data]

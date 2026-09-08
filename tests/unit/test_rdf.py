from sparql_rl.rdf.io import merge_graphs, parse_data
from sparql_rl.rdf.parser import TripleTerm


def test_rdf12_roundtrip():
    graph = parse_data('<urn:s> <urn:p> <<( <urn:a> <urn:b> "hello"@en--ltr )>> .')
    assert isinstance(next(iter(graph))[2], TripleTerm)
    assert set(parse_data(graph.serialize())) == set(graph)


def test_merge_blank_nodes():
    graph = parse_data('[] <urn:p> "x" .')
    assert len(merge_graphs([graph, graph])) == 2


def test_graph_indexes_stay_consistent():
    from sparql_rl.rdf.parser import IRI

    graph = parse_data("<urn:a> <urn:p> <urn:b> . <urn:c> <urn:p> <urn:d> .")
    triple = (IRI("urn:a"), IRI("urn:q"), IRI("urn:d"))
    graph.add(triple)
    graph.add(triple)
    assert list(graph.triples(triple)) == [triple]
    assert len(list(graph.triples((None, IRI("urn:p"), None)))) == 2
    assert not list(graph.triples((None, IRI("urn:absent"), None)))


def test_rdflib_and_serialization_formats():
    import rdflib

    from sparql_rl.rdf.canonical import isomorphic
    from sparql_rl.rdf.io import as_graph

    graph = parse_data('<urn:a> <urn:p> "x" . [] <urn:p> "hi"@en .')
    for format in ("rdfxml", "jsonld"):
        assert isomorphic(graph, parse_data(graph.serialize(format), format=format))
    library = rdflib.Graph().parse(data='<urn:a> <urn:p> "x" .', format="turtle")
    assert len(as_graph(library)) == 1
    assert len(library) == 1


def test_unsafe_external_rdf_references_are_rejected():
    import pytest

    with pytest.raises(ValueError, match="contexts"):
        parse_data('{"@context":"https://example.org/context"}', format="jsonld")
    with pytest.raises(ValueError, match="entity"):
        parse_data("<!DOCTYPE doc []>", format="rdfxml")
    with pytest.raises(ValueError, match="cannot represent"):
        parse_data('<urn:s> <urn:p> "hi"@en--ltr .').serialize("rdfxml")


def test_merge_preserves_nested_blank_node_sharing():
    from sparql_rl import infer, parse_rules
    from sparql_rl.rdf.canonical import isomorphic
    from sparql_rl.rdf.io import Graph

    rules = parse_rules("DATA { _:b <urn:q> <<( _:b <urn:p> <urn:o> )>> }")
    source = Graph(rules.data)
    assert isomorphic(source, infer(rules))
    merged = merge_graphs([source, source])
    assert len(merged) == 2
    assert len({o for s, p, o in merged}) == 2
    assert all(o.subject == s for s, p, o in merged)


def test_adapters_preserve_literal_lexical_forms():
    import json

    import rdflib

    from sparql_rl import query
    from sparql_rl.rdf.parser import XSD_NS, Literal

    xml = '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns:e="urn:"><rdf:Description rdf:about="urn:s"><e:p rdf:datatype="http://www.w3.org/2001/XMLSchema#integer">01</e:p></rdf:Description></rdf:RDF>'
    jsonld = json.dumps(
        {
            "@context": {"p": {"@id": "urn:p", "@type": XSD_NS + "integer"}},
            "@id": "urn:s",
            "p": "01",
        }
    )
    triple = '<urn:s> <urn:p> "01"^^<http://www.w3.org/2001/XMLSchema#integer> .'
    setting = rdflib.NORMALIZE_LITERALS
    for format, text in [
        ("rdfxml", xml),
        ("jsonld", jsonld),
        ("trig", triple),
        ("nquads", triple),
    ]:
        graph = parse_data(text, format=format)
        assert {o for s, p, o in graph} == {Literal("01", datatype=XSD_NS + "integer")}
        assert query("DATA {}", graph, "{" + triple + "}").boolean
        assert rdflib.NORMALIZE_LITERALS is setting


def test_jsonld_expanded_aliased_and_json_values():
    import json

    from sparql_rl.rdf.parser import XSD_NS, Literal

    document = {
        "@context": {"v": "@value", "t": "@type", "xsd": XSD_NS, "p": "urn:p"},
        "@id": "urn:s",
        "p": [
            {"v": "001", "t": "xsd:integer"},
            {"@value": "01", "@type": XSD_NS + "integer"},
            {"@value": "hello", "@language": "en"},
            {"@value": "hello", "@type": "@json"},
        ],
    }
    graph = parse_data(json.dumps(document), format="jsonld")
    assert {o for s, p, o in graph} == {
        Literal("001", datatype=XSD_NS + "integer"),
        Literal("01", datatype=XSD_NS + "integer"),
        Literal("hello", lang="en"),
        Literal('"hello"', datatype="http://www.w3.org/1999/02/22-rdf-syntax-ns#JSON"),
    }


def test_dataset_union_keeps_shared_blank_nodes_and_lexical_forms():
    from sparql_rl.rdf.parser import IRI, XSD_NS, Literal

    for format, text in [
        (
            "trig",
            '@prefix xsd: <http://www.w3.org/2001/XMLSchema#> . <urn:g> { _:b <urn:p> "01"^^xsd:integer } _:b <urn:q> "1"^^xsd:boolean .',
        ),
        (
            "nquads",
            '_:b <urn:p> "01"^^<http://www.w3.org/2001/XMLSchema#integer> <urn:g> .\n_:b <urn:q> "1"^^<http://www.w3.org/2001/XMLSchema#boolean> .',
        ),
    ]:
        graph = parse_data(text, format=format, dataset_policy="union")
        assert len({s for s, p, o in graph}) == 1
        subject = next(iter(graph))[0]
        assert set(graph) == {
            (subject, IRI("urn:p"), Literal("01", datatype=XSD_NS + "integer")),
            (subject, IRI("urn:q"), Literal("1", datatype=XSD_NS + "boolean")),
        }

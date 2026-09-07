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

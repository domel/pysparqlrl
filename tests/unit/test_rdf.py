from sparql_rl.rdf.io import merge_graphs, parse_data
from sparql_rl.rdf.parser import TripleTerm


def test_rdf12_roundtrip():
    graph = parse_data('<urn:s> <urn:p> <<( <urn:a> <urn:b> "hello"@en--ltr )>> .')
    assert isinstance(next(iter(graph))[2], TripleTerm)
    assert set(parse_data(graph.serialize())) == set(graph)


def test_merge_blank_nodes():
    graph = parse_data('[] <urn:p> "x" .')
    assert len(merge_graphs([graph, graph])) == 2

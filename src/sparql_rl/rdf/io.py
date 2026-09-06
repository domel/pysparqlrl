"""RDF 1.2 graph I/O and RDFLib interoperability."""

from collections.abc import Iterable, Iterator
from uuid import uuid4

import rdflib

from .parser import (
    IRI,
    BNode,
    Literal,
    Node,
    NTriplesParser,
    Triple,
    TripleTerm,
    TurtleParser,
    serialize_ntriples,
)


class Graph:
    def __init__(self, triples: Iterable[Triple] = ()):
        self._triples = dict.fromkeys(triples)

    def __iter__(self) -> Iterator[Triple]:
        return iter(self._triples)

    def __len__(self) -> int:
        return len(self._triples)

    def __contains__(self, triple: object) -> bool:
        return triple in self._triples

    def add(self, triple: Triple) -> None:
        self._triples[triple] = None

    def update(self, triples: Iterable[Triple]) -> None:
        self._triples.update(dict.fromkeys(triples))

    def serialize(self, format: str = "turtle") -> str:
        if format not in {"turtle", "ttl", "nt", "ntriples"}:
            raise ValueError(f"unsupported output format: {format}")
        return serialize_ntriples(list(self))


def parse_data(
    text: str,
    *,
    format: str = "turtle",
    base_iri: str | None = None,
    source_name: str = "<data>",
) -> Graph:
    if format in {"turtle", "ttl"}:
        return Graph(TurtleParser(text, source_name, base_iri).parse())
    if format in {"nt", "ntriples"}:
        return Graph(NTriplesParser(text, source_name).parse())
    raise ValueError(f"unsupported data format: {format}")


def adapt_node(node: rdflib.term.Node) -> Node:
    if isinstance(node, rdflib.URIRef):
        return IRI(str(node))
    if isinstance(node, rdflib.BNode):
        return BNode(str(node))
    if isinstance(node, rdflib.Literal):
        datatype = str(node.datatype) if node.datatype else None
        if datatype == "http://www.w3.org/2001/XMLSchema#string":
            datatype = None
        return Literal(str(node), lang=node.language, datatype=datatype)
    raise TypeError(f"unsupported RDF term: {type(node).__name__}")


def as_graph(
    data: Graph | rdflib.Graph | str | None,
    *,
    format: str = "turtle",
    base_iri: str | None = None,
) -> Graph:
    if data is None:
        return Graph()
    if isinstance(data, str):
        return parse_data(data, format=format, base_iri=base_iri)
    if isinstance(data, Graph):
        return Graph(data)
    triples = []
    for s, p, o in data:
        subject, predicate, obj = adapt_node(s), adapt_node(p), adapt_node(o)
        if not isinstance(subject, (IRI, BNode)) or not isinstance(predicate, IRI):
            raise TypeError("invalid RDF triple")
        triples.append((subject, predicate, obj))
    return Graph(triples)


def merge_graphs(graphs: Iterable[Graph]) -> Graph:
    result = Graph()
    for graph in graphs:
        scope = uuid4().hex

        def rename(node: Node, scope: str = scope) -> Node:
            if isinstance(node, BNode):
                return BNode(scope + node.label)
            if isinstance(node, TripleTerm):
                return TripleTerm(
                    rename(node.subject), node.predicate, rename(node.object)
                )
            return node

        def rename_subject(node: Node, scope: str = scope) -> Node:
            return BNode(scope + node.label) if isinstance(node, BNode) else node

        result.update((rename_subject(s), p, rename(o)) for s, p, o in graph)
    return result

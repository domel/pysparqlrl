"""RDF 1.2 graph I/O and RDFLib interoperability."""

import json
from collections.abc import Iterable, Iterator
from uuid import uuid4
from xml.sax import SAXParseException

import rdflib

from sparql_rl.errors import RDFInputError

from .adapters import parse_rdflib
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
        self._triples: dict[Triple, None] = {}
        self._indexes: tuple[dict[Node, dict[Triple, None]], ...] = ({}, {}, {})
        self.update(triples)

    def __iter__(self) -> Iterator[Triple]:
        return iter(self._triples)

    def __len__(self) -> int:
        return len(self._triples)

    def __contains__(self, triple: object) -> bool:
        return triple in self._triples

    def add(self, triple: Triple) -> None:
        if triple in self._triples:
            return
        self._triples[triple] = None
        for index, term in zip(self._indexes, triple):
            index.setdefault(term, {})[triple] = None

    def update(self, triples: Iterable[Triple]) -> None:
        for triple in triples:
            self.add(triple)

    def triples(
        self, pattern: tuple[Node | None, Node | None, Node | None]
    ) -> Iterator[Triple]:
        buckets = [
            index.get(term, {})
            for index, term in zip(self._indexes, pattern)
            if term is not None
        ]
        candidates = min(buckets, key=len) if buckets else self._triples
        return (
            triple
            for triple in candidates
            if all(
                wanted is None or wanted == actual
                for wanted, actual in zip(pattern, triple)
            )
        )

    def serialize(self, format: str = "turtle") -> str:
        if format in {"turtle", "ttl", "nt", "ntriples"}:
            return serialize_ntriples(list(self))
        formats = {
            "rdfxml": "xml",
            "xml": "xml",
            "jsonld": "json-ld",
            "json-ld": "json-ld",
        }
        if format not in formats:
            raise ValueError(f"unsupported output format: {format}")
        graph = rdflib.Graph()
        for subject, predicate, obj in self:
            graph.add((to_rdflib(subject), to_rdflib(predicate), to_rdflib(obj)))
        return graph.serialize(format=formats[format])


def parse_data(
    text: str,
    *,
    format: str = "turtle",
    base_iri: str | None = None,
    source_name: str = "<data>",
    dataset_policy: str = "error",
) -> Graph:
    try:
        return _parse_data(
            text,
            format=format,
            base_iri=base_iri,
            source_name=source_name,
            dataset_policy=dataset_policy,
        )
    except (SAXParseException, rdflib.exceptions.ParserError, SyntaxError) as error:
        raise RDFInputError(f"{source_name}: {error}") from error


def _parse_data(
    text: str,
    *,
    format: str = "turtle",
    base_iri: str | None = None,
    source_name: str = "<data>",
    dataset_policy: str = "error",
) -> Graph:
    if format in {"turtle", "ttl"}:
        return Graph(TurtleParser(text, source_name, base_iri).parse())
    if format in {"nt", "ntriples"}:
        return Graph(NTriplesParser(text, source_name).parse())
    formats = {
        "rdfxml": "xml",
        "xml": "xml",
        "jsonld": "json-ld",
        "json-ld": "json-ld",
        "trig": "trig",
        "nquads": "nquads",
        "nq": "nquads",
    }
    if format not in formats:
        raise ValueError(f"unsupported data format: {format}")
    if formats[format] == "xml" and (
        "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper()
    ):
        raise ValueError("DTD and entity declarations are forbidden")
    if formats[format] == "json-ld":

        def check_context(value: object) -> None:
            if isinstance(value, list):
                for item in value:
                    check_context(item)
            elif isinstance(value, dict):
                for key, child in value.items():
                    if key == "@import" or (
                        key == "@context" and isinstance(child, str)
                    ):
                        raise ValueError("remote JSON-LD contexts are disabled")
                    if (
                        key == "@context"
                        and isinstance(child, list)
                        and any(isinstance(item, str) for item in child)
                    ):
                        raise ValueError("remote JSON-LD contexts are disabled")
                    check_context(child)

        check_context(json.loads(text))
    if format in {"trig", "nquads", "nq"}:
        if dataset_policy not in {"error", "union"}:
            raise ValueError("dataset policy must be error or union")
        dataset = parse_rdflib(text, formats[format], base_iri)
        assert isinstance(dataset, rdflib.Dataset)
        named = [
            g
            for g in dataset.graphs()
            if g.identifier != dataset.default_graph.identifier and len(g)
        ]
        if named and dataset_policy == "error":
            raise ValueError("named graphs require dataset_policy=union")
        result = Graph()
        for graph in dataset.graphs():
            result.update(as_graph(graph))
        return result
    return as_graph(parse_rdflib(text, formats[format], base_iri))


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

        result.update((rename(s), p, rename(o)) for s, p, o in graph)
    return result


def to_rdflib(node: Node) -> rdflib.term.Identifier:
    if isinstance(node, IRI):
        return rdflib.URIRef(node.value)
    if isinstance(node, BNode):
        return rdflib.BNode(node.label)
    if isinstance(node, Literal) and node.direction is None:
        return rdflib.Literal(
            node.value,
            lang=node.lang,
            datatype=rdflib.URIRef(node.datatype) if node.datatype else None,
            normalize=False,
        )
    raise ValueError(
        "selected format cannot represent this RDF 1.2 term; use turtle or nt"
    )

"""Graph isomorphism including blank nodes nested in triple terms."""

import rdflib
from rdflib.compare import isomorphic as rdf_isomorphic

from .io import Graph
from .parser import IRI, BNode, Literal, Node, TripleTerm


def encoded_graph(graph: Graph) -> rdflib.Graph:
    """Injectively encode RDF 1.2 terms as a labeled incidence graph."""
    result = rdflib.Graph()
    nodes: dict[Node, rdflib.BNode] = {}
    ns = rdflib.Namespace("urn:sparql-rl:isomorphism:")

    def encode(node: Node) -> rdflib.BNode:
        if node in nodes:
            return nodes[node]
        identity = rdflib.BNode()
        nodes[node] = identity
        if isinstance(node, BNode):
            result.add((identity, ns.kind, ns.blank))
        elif isinstance(node, IRI):
            result.add((identity, ns.iri, rdflib.Literal(node.value)))
        elif isinstance(node, Literal):
            result.add((identity, ns.lexical, rdflib.Literal(node.value)))
            for key, value in (
                ("language", node.lang),
                ("direction", node.direction),
                ("datatype", node.datatype),
            ):
                if value is not None:
                    result.add((identity, ns[key], rdflib.Literal(value)))
        elif isinstance(node, TripleTerm):
            result.add((identity, ns.kind, ns["term"]))
            for key, component in zip(
                ("subject", "predicate", "object"),
                (node.subject, node.predicate, node.object),
            ):
                result.add((identity, ns[key], encode(component)))
        return identity

    for triple in graph:
        statement = rdflib.BNode()
        result.add((statement, ns.kind, ns.asserted))
        for key, node in zip(("subject", "predicate", "object"), triple):
            result.add((statement, ns[key], encode(node)))
    return result


def isomorphic(left: Graph, right: Graph) -> bool:
    return len(left) == len(right) and rdf_isomorphic(
        encoded_graph(left), encoded_graph(right)
    )

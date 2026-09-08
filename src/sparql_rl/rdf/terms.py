"""Boundary between permissive rule patterns and concrete RDF triples."""

from typing import TypeGuard

from .parser import IRI, BNode, Literal, Node, TripleTerm

RDFTriple = tuple[IRI | BNode, IRI, Node]


def is_rdf_term(node: object) -> TypeGuard[Node]:
    if type(node) in (IRI, BNode, Literal):
        return True
    return isinstance(node, TripleTerm) and is_rdf_triple(
        (node.subject, node.predicate, node.object)
    )


def is_rdf_triple(triple: tuple[object, object, object]) -> TypeGuard[RDFTriple]:
    s, p, o = triple
    return type(s) in (IRI, BNode) and type(p) is IRI and is_rdf_term(o)


def make_triple_term(subject: Node, predicate: Node, obj: Node) -> TripleTerm:
    triple = (subject, predicate, obj)
    if not is_rdf_triple(triple):
        raise ValueError("invalid RDF triple term")
    return TripleTerm(*triple)

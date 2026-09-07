"""Ordered solution joins and recursive RDF 1.2 term matching."""

from sparql_rl.model import Variable, has_blank, variables
from sparql_rl.rdf.io import Graph
from sparql_rl.rdf.parser import BNode, Node, Triple, TripleTerm

SolutionMapping = dict[Variable, Node]


def match_node(pattern: Node, value: Node, solution: SolutionMapping) -> bool:
    if isinstance(pattern, BNode):
        pattern = Variable("@blank:" + pattern.label)
    if isinstance(pattern, Variable):
        if pattern in solution:
            return solution[pattern] == value
        solution[pattern] = value
        return True
    if isinstance(pattern, TripleTerm) and isinstance(value, TripleTerm):
        return all(
            match_node(p, v, solution)
            for p, v in zip(
                (pattern.subject, pattern.predicate, pattern.object),
                (value.subject, value.predicate, value.object),
            )
        )
    return pattern == value


def graph_match(
    graph: Graph, pattern: Triple, incoming: list[SolutionMapping]
) -> list[SolutionMapping]:
    results = []
    for solution in incoming:
        constrained = tuple(
            solution.get(term)
            if isinstance(term, Variable)
            else None
            if isinstance(term, BNode) or variables(term) or has_blank(term)
            else term
            for term in pattern
        )
        for triple in graph.triples((constrained[0], constrained[1], constrained[2])):
            candidate = solution.copy()
            if all(match_node(p, v, candidate) for p, v in zip(pattern, triple)):
                results.append(candidate)
    return results

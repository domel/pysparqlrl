"""W3C section 4.3: structural pattern/template dependencies."""

from dataclasses import dataclass
from enum import Enum

from sparql_rl.model import (
    NegationElement,
    RuleSet,
    TriplePatternElement,
    Variable,
    is_run_once,
)
from sparql_rl.rdf.parser import BNode, Node, Triple, TripleTerm


class Label(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


@dataclass(frozen=True)
class DependencyGraph:
    edges: tuple[tuple[int, int, Label], ...]


def compatible(pattern: Triple, template: Triple) -> bool:
    """Unify with disjoint variable scopes, preserving repeated occurrences."""
    bindings: dict[tuple[int, Node], tuple[int, Node]] = {}

    def resolve(item: tuple[int, Node]) -> tuple[int, Node]:
        while item in bindings:
            item = bindings[item]
        return item

    def occurs(variable: tuple[int, Node], item: tuple[int, Node]) -> bool:
        item = resolve(item)
        if variable == item:
            return True
        node = item[1]
        return isinstance(node, TripleTerm) and any(
            occurs(variable, (item[0], child))
            for child in (node.subject, node.predicate, node.object)
        )

    def unify(left: tuple[int, Node], right: tuple[int, Node]) -> bool:
        left, right = resolve(left), resolve(right)
        if left == right:
            return True
        for blank, other in ((left, right), (right, left)):
            if (
                blank[0] == 1
                and isinstance(blank[1], BNode)
                and not isinstance(other[1], (Variable, BNode))
            ):
                return False
        if isinstance(left[1], (Variable, BNode)):
            if occurs(left, right):
                return False
            bindings[left] = right
            return True
        if isinstance(right[1], (Variable, BNode)):
            if occurs(right, left):
                return False
            bindings[right] = left
            return True
        a, b = left[1], right[1]
        if isinstance(a, TripleTerm) and isinstance(b, TripleTerm):
            return all(
                unify((left[0], x), (right[0], y))
                for x, y in zip(
                    (a.subject, a.predicate, a.object),
                    (b.subject, b.predicate, b.object),
                )
            )
        return a == b

    return all(unify((0, a), (1, b)) for a, b in zip(pattern, template))


def build_dependency_graph(rule_set: RuleSet) -> DependencyGraph:
    edges: dict[tuple[int, int], Label] = {}
    for i, consumer in enumerate(rule_set.rules):
        if consumer.data_only:
            continue
        patterns = []
        for element in consumer.body:
            if isinstance(element, TriplePatternElement):
                patterns.append((element.pattern, is_run_once(consumer)))
            elif isinstance(element, NegationElement) and not element.data_only:
                patterns.extend(
                    (e.pattern, True)
                    for e in element.body
                    if isinstance(e, TriplePatternElement)
                )
        for pattern, closed in patterns:
            for j, producer in enumerate(rule_set.rules):
                if any(compatible(pattern, head) for head in producer.head):
                    label = Label.CLOSED if closed else Label.OPEN
                    if edges.get((i, j)) != Label.CLOSED:
                        edges[i, j] = label
    return DependencyGraph(
        tuple((i, j, label) for (i, j), label in sorted(edges.items()))
    )

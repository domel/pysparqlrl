"""Immutable rule and expression model."""

from dataclasses import dataclass

from sparql_rl.rdf.parser import IRI, BNode, Node, Triple, TripleTerm


@dataclass(frozen=True)
class Variable(IRI):
    """Variable identifier; the runtime type distinguishes it from an RDF IRI."""


@dataclass(frozen=True)
class Expression:
    operator: str
    arguments: tuple["Expression | Node", ...]


@dataclass(frozen=True)
class TriplePatternElement:
    pattern: Triple


@dataclass(frozen=True)
class FilterElement:
    expression: Expression | Node


@dataclass(frozen=True)
class AssignmentElement:
    variable: Variable
    expression: Expression | Node


@dataclass(frozen=True)
class NegationElement:
    body: tuple["RuleElement", ...]
    data_only: bool = False


RuleElement = TriplePatternElement | FilterElement | AssignmentElement | NegationElement


@dataclass(frozen=True)
class Rule:
    head: tuple[Triple, ...]
    body: tuple[RuleElement, ...]
    data_only: bool = False
    identifier: IRI | None = None
    source: str | None = None


@dataclass(frozen=True)
class RuleSet:
    rules: tuple[Rule, ...] = ()
    data: tuple[Triple, ...] = ()
    imports: tuple[str, ...] = ()
    source: str | None = None
    source_iris: tuple[str, ...] = ()


def variables(value: object) -> set[Variable]:
    if isinstance(value, Variable):
        return {value}
    if isinstance(value, TripleTerm):
        return variables((value.subject, value.predicate, value.object))
    if isinstance(value, Expression):
        return variables(value.arguments)
    if isinstance(value, (list, tuple)):
        return set().union(*(variables(x) for x in value))
    return set()


def has_blank(value: object) -> bool:
    if isinstance(value, BNode):
        return True
    if isinstance(value, TripleTerm):
        return has_blank((value.subject, value.predicate, value.object))
    return isinstance(value, (tuple, list)) and any(has_blank(x) for x in value)


def is_run_once(rule: Rule) -> bool:
    return has_blank(rule.head) or any(
        isinstance(x, AssignmentElement) for x in rule.body
    )

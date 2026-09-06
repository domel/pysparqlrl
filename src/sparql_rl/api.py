"""Public library operations shared by the CLI."""

from dataclasses import dataclass

import rdflib

from sparql_rl.analysis import PreparedRuleSet, build_dependency_graph, stratify
from sparql_rl.evaluation.engine import evaluate_body, evaluate_rules
from sparql_rl.evaluation.expressions import Context
from sparql_rl.evaluation.matcher import SolutionMapping
from sparql_rl.imports import ImportResolver
from sparql_rl.model import RuleElement, RuleSet, Variable
from sparql_rl.rdf.io import Graph, as_graph
from sparql_rl.syntax.parser import RuleParser, parse_rules
from sparql_rl.validation import validate_body, validate_rules


def prepare_rules(
    rule_set: RuleSet, *, import_resolver: ImportResolver | None = None
) -> PreparedRuleSet:
    if rule_set.imports:
        rule_set = (import_resolver or ImportResolver()).resolve(rule_set)
    validate_rules(rule_set)
    dependencies = build_dependency_graph(rule_set)
    return PreparedRuleSet(rule_set, dependencies, stratify(rule_set, dependencies))


def infer(
    rule_set: RuleSet | PreparedRuleSet | str,
    data: Graph | rdflib.Graph | str | None = None,
    *,
    rule_base_iri: str | None = None,
    data_format: str | None = None,
    data_base_iri: str | None = None,
    include_base: bool = False,
    import_resolver: ImportResolver | None = None,
) -> Graph:
    if isinstance(rule_set, str):
        rule_set = parse_rules(rule_set, base_iri=rule_base_iri)
    prepared = (
        rule_set
        if isinstance(rule_set, PreparedRuleSet)
        else prepare_rules(rule_set, import_resolver=import_resolver)
    )
    base = as_graph(data, format=data_format or "turtle", base_iri=data_base_iri)
    result = evaluate_rules(prepared, base)
    if include_base:
        result.update(base)
    return result


@dataclass(frozen=True)
class QueryResult:
    variables: tuple[Variable, ...]
    bindings: tuple[SolutionMapping, ...]

    @property
    def boolean(self) -> bool:
        return bool(self.bindings)

    def __bool__(self) -> bool:
        return self.boolean


def query(
    rule_set: RuleSet | PreparedRuleSet | str,
    data: Graph | rdflib.Graph | str | None,
    goal: str | tuple[RuleElement, ...],
    *,
    rule_base_iri: str | None = None,
    goal_base_iri: str | None = None,
    import_resolver: ImportResolver | None = None,
) -> QueryResult:
    graph = infer(
        rule_set,
        data,
        rule_base_iri=rule_base_iri,
        include_base=True,
        import_resolver=import_resolver,
    )
    if isinstance(goal, str):
        parser = RuleParser(goal, "<goal>", goal_base_iri)
        parser.ws()
        while parser.parse_directive_if_present():
            parser.ws()
        body = parser.block("body")
        if not parser.scanner.eof():
            parser.scanner.error("unexpected text after goal")
    else:
        body = goal
    defined = validate_body(body, set())
    solutions = evaluate_body(body, graph, as_graph(data), [{}], Context())
    public = tuple(
        sorted(
            (v for v in defined if not v.value.startswith("@")), key=lambda v: v.value
        )
    )
    return QueryResult(public, tuple({v: s[v] for v in public} for s in solutions))

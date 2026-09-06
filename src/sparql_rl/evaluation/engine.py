"""W3C section 6: stratified reference evaluation."""

from uuid import uuid4

from sparql_rl.analysis import PreparedRuleSet
from sparql_rl.errors import ExpressionError
from sparql_rl.model import (
    AssignmentElement,
    FilterElement,
    NegationElement,
    Rule,
    RuleElement,
    TriplePatternElement,
    Variable,
)
from sparql_rl.rdf.io import Graph, merge_graphs
from sparql_rl.rdf.parser import IRI, BNode, Node, TripleTerm

from .expressions import Context, ebv, evaluate
from .matcher import SolutionMapping, graph_match


def evaluate_body(
    body: tuple[RuleElement, ...],
    evaluation_graph: Graph,
    base_graph: Graph,
    solutions: list[SolutionMapping],
    context: Context,
) -> list[SolutionMapping]:
    for element in body:
        if isinstance(element, TriplePatternElement):
            solutions = graph_match(evaluation_graph, element.pattern, solutions)
        elif isinstance(element, NegationElement):
            graph = base_graph if element.data_only else evaluation_graph
            solutions = [
                s
                for s in solutions
                if not evaluate_body(element.body, graph, base_graph, [s], context)
            ]
        else:
            updated = []
            for solution in solutions:
                try:
                    value = evaluate(element.expression, solution, context)
                    if isinstance(element, AssignmentElement):
                        updated.append({**solution, element.variable: value})
                    elif isinstance(element, FilterElement) and ebv(value):
                        updated.append(solution)
                except ExpressionError:
                    continue
            solutions = updated
    return solutions


def evaluate_rule(
    rule: Rule, evaluation_graph: Graph, base_graph: Graph, context: Context
) -> Graph:
    graph = base_graph if rule.data_only else evaluation_graph
    solutions = evaluate_body(rule.body, graph, base_graph, [{}], context)
    output = Graph()
    for solution in solutions:
        blanks: dict[BNode, BNode] = {}

        def substitute(
            term: Node,
            solution: SolutionMapping = solution,
            blanks: dict[BNode, BNode] = blanks,
        ) -> Node:
            if isinstance(term, Variable):
                return solution[term]
            if isinstance(term, BNode):
                return blanks.setdefault(term, BNode(uuid4().hex))
            if isinstance(term, TripleTerm):
                s, p, o = (
                    substitute(term.subject),
                    substitute(term.predicate),
                    substitute(term.object),
                )
                if not isinstance(p, IRI):
                    raise ExpressionError("invalid instantiated triple term")
                return TripleTerm(s, p, o)
            return term

        for head in rule.head:
            try:
                s, p, o = (substitute(t) for t in head)
                if isinstance(p, IRI):
                    output.add((s, p, o))
            except ExpressionError:
                continue
    return output


def evaluate_rules(prepared: PreparedRuleSet, base_graph: Graph) -> Graph:
    data_graph = merge_graphs([Graph(prepared.rule_set.data)])
    evaluation_graph = Graph(base_graph)
    evaluation_graph.update(data_graph)
    inference_graph = Graph(t for t in data_graph if t not in base_graph)
    context = Context()

    def run(rule: Rule) -> bool:
        generated = evaluate_rule(rule, evaluation_graph, base_graph, context)
        fresh = [t for t in generated if t not in evaluation_graph]
        inference_graph.update(fresh)
        evaluation_graph.update(fresh)
        return bool(fresh)

    for stratum in prepared.stratification:
        for rule in stratum.once:
            run(rule)
        while True:
            changed = False
            for rule in stratum.general:
                changed = run(rule) or changed
            if not changed:
                break
    return inference_graph

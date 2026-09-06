"""W3C section 4.4: bounded stratum constraints."""

from dataclasses import dataclass

from sparql_rl.errors import StratificationError
from sparql_rl.model import Rule, RuleSet, is_run_once

from .dependency import DependencyGraph, Label


@dataclass(frozen=True)
class Stratum:
    once: tuple[Rule, ...]
    general: tuple[Rule, ...]


@dataclass(frozen=True)
class PreparedRuleSet:
    rule_set: RuleSet
    dependency_graph: DependencyGraph
    stratification: tuple[Stratum, ...]


def stratify(rule_set: RuleSet, graph: DependencyGraph) -> tuple[Stratum, ...]:
    levels = [0] * len(rule_set.rules)
    while True:
        changed = False
        for consumer, producer, label in graph.edges:
            required = levels[producer] + (label == Label.CLOSED)
            if required > len(levels):
                raise StratificationError(
                    f"closed dependency participates in a recursive cycle near rules {consumer + 1} -> {producer + 1}"
                )
            if levels[consumer] < required:
                levels[consumer] = required
                changed = True
        if not changed:
            break
    result = []
    for level in sorted(set(levels)):
        rules = [r for i, r in enumerate(rule_set.rules) if levels[i] == level]
        result.append(
            Stratum(
                tuple(r for r in rules if is_run_once(r)),
                tuple(r for r in rules if not is_run_once(r)),
            )
        )
    return tuple(result)

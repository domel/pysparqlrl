"""Standalone SPARQL 1.2 RL library and command-line processor."""

from .analysis import PreparedRuleSet
from .api import QueryResult, infer, prepare_rules, query
from .model import Rule, RuleSet, Variable
from .rdf.io import Graph
from .syntax.parser import parse_rules
from .validation import validate_rules

__all__ = [
    "Graph",
    "PreparedRuleSet",
    "QueryResult",
    "Rule",
    "RuleSet",
    "Variable",
    "infer",
    "parse_rules",
    "prepare_rules",
    "query",
    "validate_rules",
]

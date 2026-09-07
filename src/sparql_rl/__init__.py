"""Standalone SPARQL 1.2 RL library and command-line processor."""

from .analysis import PreparedRuleSet
from .api import QueryResult, infer, prepare_rules, query
from .evaluation.expressions import FunctionRegistry
from .imports import ImportResolver
from .model import Rule, RuleSet, Variable
from .rdf.io import Graph
from .rdf.parser import IRI, BNode, Literal, TripleTerm
from .syntax.parser import parse_rules
from .validation import validate_rules

__all__ = [
    "IRI",
    "BNode",
    "FunctionRegistry",
    "Graph",
    "ImportResolver",
    "Literal",
    "PreparedRuleSet",
    "QueryResult",
    "Rule",
    "RuleSet",
    "TripleTerm",
    "Variable",
    "infer",
    "parse_rules",
    "prepare_rules",
    "query",
    "validate_rules",
]

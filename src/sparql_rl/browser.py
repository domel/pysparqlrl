"""String-oriented browser adapter for the shared SPARQL-RL engine.

This module intentionally contains no SPARQL-RL semantics. It adapts the public
Python API to JSON-compatible values suitable for a Pyodide Web Worker.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, Mapping

from sparql_rl import infer, parse_rules, prepare_rules, query, validate_rules
from sparql_rl.errors import (
    ImportResolutionError,
    ParseError,
    RDFInputError,
    StratificationError,
    WellFormednessError,
)
from sparql_rl.imports import MappingImportResolver
from sparql_rl.model import is_run_once
from sparql_rl.rdf.io import Graph, parse_data
from sparql_rl.serialization import query_result_json


def _resolver(imports: Mapping[str, str] | None) -> MappingImportResolver:
    return MappingImportResolver(imports or {})


def parse_text(rules: str, *, rules_base: str | None = None) -> dict[str, Any]:
    """Parse a rule document and return the same lowered model used by the CLI."""
    return asdict(parse_rules(rules, base_iri=rules_base))


def check_text(
    rules: str,
    *,
    rules_base: str | None = None,
    level: str = "all",
    imports: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Run the requested validation stage and return explicit check status."""
    if level not in {"syntax", "wellformed", "stratification", "all"}:
        raise ValueError("check level must be syntax, wellformed, stratification or all")
    rule_set = parse_rules(rules, base_iri=rules_base)
    checks = {
        "syntax": True,
        "imports": False,
        "wellFormedness": False,
        "dependencyGraph": False,
        "stratification": False,
    }
    if level == "syntax":
        return {"ok": True, "level": level, "checks": checks}

    resolved = _resolver(imports).resolve(rule_set) if rule_set.imports else rule_set
    checks["imports"] = True
    validate_rules(resolved)
    checks["wellFormedness"] = True
    if level == "wellformed":
        return {"ok": True, "level": level, "checks": checks}

    prepared = prepare_rules(resolved)
    checks["dependencyGraph"] = True
    checks["stratification"] = True
    return {
        "ok": True,
        "level": level,
        "checks": checks,
        "strata": len(prepared.stratification),
    }


def explain_text(
    rules: str,
    *,
    rules_base: str | None = None,
    imports: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Return the rule/dependency information exposed by CLI ``explain``."""
    rule_set = parse_rules(rules, base_iri=rules_base)
    prepared = prepare_rules(rule_set, import_resolver=_resolver(imports))
    levels = {
        id(rule): index
        for index, stratum in enumerate(prepared.stratification)
        for rule in (*stratum.once, *stratum.general)
    }
    return {
        "rules": [
            {
                "index": index + 1,
                "identifier": rule.identifier.value if rule.identifier else None,
                "run_once": is_run_once(rule),
                "stratum": levels[id(rule)],
            }
            for index, rule in enumerate(prepared.rule_set.rules)
        ],
        "dependencies": [
            {"consumer": a + 1, "producer": b + 1, "label": label.value}
            for a, b, label in prepared.dependency_graph.edges
        ],
        "imports": list(rule_set.imports),
        "data_triples": len(prepared.rule_set.data),
    }


def _infer_graph(
    rules: str,
    data: str = "",
    *,
    rules_base: str | None = None,
    data_base: str | None = None,
    data_format: str = "turtle",
    include_base: bool = False,
    dataset_policy: str = "error",
    imports: Mapping[str, str] | None = None,
) -> Graph:
    graph = parse_data(
        data, format=data_format, base_iri=data_base, dataset_policy=dataset_policy
    )
    return infer(
        rules,
        graph,
        rule_base_iri=rules_base,
        include_base=include_base,
        import_resolver=_resolver(imports),
    )


def infer_text(
    rules: str,
    data: str = "",
    *,
    rules_base: str | None = None,
    data_base: str | None = None,
    data_format: str = "turtle",
    output_format: str = "turtle",
    include_base: bool = False,
    dataset_policy: str = "error",
    imports: Mapping[str, str] | None = None,
) -> str:
    """Run inference from textual browser inputs and serialize the result graph."""
    return _infer_graph(
        rules,
        data,
        rules_base=rules_base,
        data_base=data_base,
        data_format=data_format,
        include_base=include_base,
        dataset_policy=dataset_policy,
        imports=imports,
    ).serialize(output_format)


def query_text(
    rules: str,
    data: str,
    goal: str,
    *,
    rules_base: str | None = None,
    data_base: str | None = None,
    goal_base: str | None = None,
    data_format: str = "turtle",
    dataset_policy: str = "error",
    imports: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Run a goal query and return SPARQL Results JSON-compatible data."""
    graph = parse_data(
        data, format=data_format, base_iri=data_base, dataset_policy=dataset_policy
    )
    result = query(
        rules,
        graph,
        goal,
        rule_base_iri=rules_base,
        goal_base_iri=goal_base,
        import_resolver=_resolver(imports),
    )
    return query_result_json(result)


def error_to_dict(error: BaseException) -> dict[str, Any]:
    """Convert expected processor failures to a browser-friendly error object."""
    if isinstance(error, ParseError):
        error_type = "RDFInputError" if error.source == "<data>" else "ParseError"
        return {
            "type": error_type,
            "message": error.message,
            "source": error.source,
            "line": error.line,
            "column": error.column,
        }
    if isinstance(
        error,
        (
            ImportResolutionError,
            WellFormednessError,
            StratificationError,
            RDFInputError,
        ),
    ):
        return {"type": type(error).__name__, "message": str(error)}
    if isinstance(error, ValueError):
        return {"type": type(error).__name__, "message": str(error)}
    return {"type": "InternalError", "message": str(error) or type(error).__name__}


def dispatch(request: Mapping[str, Any]) -> dict[str, Any]:
    """Execute one worker-protocol request and always return a structured envelope."""
    action = str(request.get("action", ""))
    request_id = request.get("id")
    options = request.get("options") or {}
    imports = request.get("imports") or {}
    if not isinstance(options, Mapping):
        return {
            "id": request_id,
            "ok": False,
            "error": {"type": "ValueError", "message": "options must be an object"},
        }
    if not isinstance(imports, Mapping):
        return {
            "id": request_id,
            "ok": False,
            "error": {"type": "ValueError", "message": "imports must be an object"},
        }
    try:
        rules = str(request.get("rules", ""))
        rules_base = options.get("rulesBase")
        if action == "parse":
            result: Any = parse_text(rules, rules_base=rules_base)
        elif action == "check":
            result = check_text(
                rules,
                rules_base=rules_base,
                level=str(options.get("level", "all")),
                imports=imports,
            )
        elif action == "explain":
            result = explain_text(rules, rules_base=rules_base, imports=imports)
        elif action == "infer":
            graph = _infer_graph(
                rules,
                str(request.get("data", "")),
                rules_base=rules_base,
                data_base=options.get("dataBase"),
                data_format=str(options.get("dataFormat", "turtle")),
                dataset_policy=str(options.get("datasetPolicy", "error")),
                include_base=bool(options.get("includeBase", False)),
                imports=imports,
            )
            result = {
                "triples": len(graph),
                "data": graph.serialize(str(options.get("outputFormat", "turtle"))),
            }
        elif action == "query":
            result = query_text(
                rules,
                str(request.get("data", "")),
                str(request.get("goal", "")),
                rules_base=rules_base,
                data_base=options.get("dataBase"),
                goal_base=options.get("goalBase"),
                data_format=str(options.get("dataFormat", "turtle")),
                dataset_policy=str(options.get("datasetPolicy", "error")),
                imports=imports,
            )
        else:
            raise ValueError(f"unsupported browser action: {action or '<empty>'}")
        return {"id": request_id, "ok": True, "result": result}
    except Exception as error:  # worker boundary: never leak normal tracebacks
        return {"id": request_id, "ok": False, "error": error_to_dict(error)}


def handle_request_json(request_json: str) -> str:
    """JSON-string bridge used by JavaScript to avoid Python proxy objects."""
    try:
        request = json.loads(request_json)
        if not isinstance(request, dict):
            raise ValueError("request must be a JSON object")
        response = dispatch(request)
    except Exception as error:
        response = {"id": None, "ok": False, "error": error_to_dict(error)}
    return json.dumps(response, ensure_ascii=False)


__all__ = [
    "check_text",
    "dispatch",
    "error_to_dict",
    "explain_text",
    "handle_request_json",
    "infer_text",
    "parse_text",
    "query_text",
]

"""Command-line interface to the public SPARQL-RL library."""

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from time import perf_counter

from sparql_rl import infer, parse_rules, prepare_rules, query, validate_rules
from sparql_rl.errors import (
    ImportResolutionError,
    ParseError,
    StratificationError,
    WellFormednessError,
)
from sparql_rl.imports import ImportResolver
from sparql_rl.model import RuleSet, is_run_once
from sparql_rl.rdf.io import Graph, merge_graphs, merge_triples, parse_data
from sparql_rl.rdf.parser import IRI, BNode, Node, TripleTerm, format_node_nt
from sparql_rl.spec_version import SPEC_DATE, __version__


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="sparql-rl", description="Standalone SPARQL 1.2 RL processor"
    )
    root.add_argument(
        "--version",
        action="version",
        version=f"sparql-rl {__version__}\nSPARQL 1.2 RL target: W3C Working Draft {SPEC_DATE}",
    )
    commands = root.add_subparsers(dest="command", required=True)
    for command in ("infer", "query", "check", "parse", "explain"):
        sub = commands.add_parser(command)
        sub.add_argument("-r", "--rules", action="append", default=[], metavar="FILE")
        sub.add_argument(
            "-R", "--rules-string", action="append", default=[], metavar="TEXT"
        )
        sub.add_argument("-d", "--data", action="append", default=[], metavar="FILE")
        sub.add_argument(
            "-D", "--data-string", action="append", default=[], metavar="TEXT"
        )
        sub.add_argument("--rules-base")
        sub.add_argument("--data-base")
        sub.add_argument("--data-format", choices=("turtle", "ttl", "nt", "ntriples"))
        sub.add_argument(
            "--data-string-format",
            choices=("turtle", "nt", "rdfxml", "jsonld", "trig", "nquads"),
        )
        sub.add_argument(
            "--dataset-policy", choices=("error", "union"), default="error"
        )
        sub.add_argument("--stats", action="store_true")
        sub.add_argument("--allow-network-imports", action="store_true")
        sub.add_argument("--import-root", type=Path)
        sub.add_argument("--debug", action="store_true")
        sub.add_argument("-o", "--output", type=Path)
        if command == "infer":
            sub.add_argument("--include-base", action="store_true")
            sub.add_argument(
                "-f",
                "--output-format",
                default="turtle",
                choices=("turtle", "nt", "rdfxml", "jsonld"),
            )
        elif command == "query":
            goals = sub.add_mutually_exclusive_group(required=True)
            goals.add_argument("-g", "--goal")
            goals.add_argument("--goal-file")
            sub.add_argument("--goal-base")
            sub.add_argument(
                "--format",
                "--result-format",
                "--output-format",
                default="table",
                choices=("table", "json", "boolean", "tsv"),
            )
        elif command == "check":
            sub.add_argument(
                "--level",
                choices=("syntax", "wellformed", "stratification", "all"),
                default="all",
            )
        elif command == "parse":
            sub.add_argument("--ast", action="store_true")
            sub.add_argument("--normalized", action="store_true")
            sub.add_argument("--json", action="store_true")
        else:
            sub.add_argument(
                "--format", default="text", choices=("text", "json", "dot")
            )
    return root


def read_text(filename: str) -> str:
    return (
        sys.stdin.read()
        if filename == "-"
        else Path(filename).read_text(encoding="utf-8")
    )


def read_rules(args: argparse.Namespace) -> RuleSet:
    inputs = [
        parse_rules(
            read_text(f),
            base_iri=args.rules_base
            or (Path(f).resolve().as_uri() if f != "-" else None),
            source_name=f,
            document_iri=Path(f).resolve().as_uri() if f != "-" else None,
        )
        for f in args.rules
    ]
    inputs.extend(parse_rules(t, base_iri=args.rules_base) for t in args.rules_string)
    return RuleSet(
        tuple(r for rs in inputs for r in rs.rules),
        tuple(merge_triples(rs.data for rs in inputs)),
        tuple(i for rs in inputs for i in rs.imports),
        source_iris=tuple(rs.source for rs in inputs if rs.source),
    )


def read_data(args: argparse.Namespace) -> Graph:
    graphs = []
    for filename in args.data:
        format = args.data_format or {
            ".nt": "nt",
            ".rdf": "rdfxml",
            ".xml": "rdfxml",
            ".jsonld": "jsonld",
            ".json": "jsonld",
            ".trig": "trig",
            ".nq": "nquads",
        }.get(Path(filename).suffix, "turtle")
        graphs.append(
            parse_data(
                read_text(filename),
                format=format,
                base_iri=args.data_base
                or (Path(filename).resolve().as_uri() if filename != "-" else None),
                source_name=filename,
                dataset_policy=args.dataset_policy,
            )
        )
    graphs.extend(
        parse_data(
            t,
            format=args.data_string_format or args.data_format or "turtle",
            base_iri=args.data_base,
            dataset_policy=args.dataset_policy,
        )
        for t in args.data_string
    )
    return merge_graphs(graphs)


def binding_json(node: Node) -> dict:
    if isinstance(node, IRI):
        return {"type": "uri", "value": node.value}
    if isinstance(node, BNode):
        return {"type": "bnode", "value": node.label}
    if isinstance(node, TripleTerm):
        return {
            "type": "triple",
            "value": {
                "subject": binding_json(node.subject),
                "predicate": binding_json(node.predicate),
                "object": binding_json(node.object),
            },
        }
    result = {"type": "literal", "value": node.value}
    if node.lang:
        result["xml:lang"] = node.lang
    if node.direction:
        result["its:dir"] = node.direction
    if node.datatype:
        result["datatype"] = node.datatype
    return result


def execute(args: argparse.Namespace) -> tuple[str, int]:
    rules = read_rules(args)
    if args.command == "parse":
        return json.dumps(asdict(rules), ensure_ascii=False, indent=2), 0
    resolver = ImportResolver(args.allow_network_imports, args.import_root)
    if args.command == "check" and args.level == "syntax":
        return "OK: syntax", 0
    if args.command == "check" and args.level == "wellformed":
        validate_rules(resolver.resolve(rules) if rules.imports else rules)
        return "OK: syntax, imports, well-formedness", 0
    prepared = prepare_rules(rules, import_resolver=resolver)
    if args.command == "check":
        return (
            f"OK: syntax, imports, well-formedness, dependency graph, stratification ({len(prepared.stratification)} strata)",
            0,
        )
    if args.command == "explain":
        levels = {
            id(r): i
            for i, s in enumerate(prepared.stratification)
            for r in (*s.once, *s.general)
        }
        info = {
            "rules": [
                {
                    "index": i + 1,
                    "identifier": r.identifier.value if r.identifier else None,
                    "run_once": is_run_once(r),
                    "stratum": levels[id(r)],
                }
                for i, r in enumerate(prepared.rule_set.rules)
            ],
            "dependencies": [
                {"consumer": a + 1, "producer": b + 1, "label": label.value}
                for a, b, label in prepared.dependency_graph.edges
            ],
            "imports": list(rules.imports),
            "data_triples": len(prepared.rule_set.data),
        }
        if args.format == "json":
            return json.dumps(info, indent=2), 0
        if args.format == "dot":
            lines = ["digraph rules {"]
            lines.extend(f"  R{i + 1};" for i in range(len(prepared.rule_set.rules)))
            lines.extend(
                f'  R{a + 1} -> R{b + 1} [label="{label.value}"];'
                for a, b, label in prepared.dependency_graph.edges
            )
            return "\n".join([*lines, "}"]), 0
        return "\n".join(
            [
                *(
                    f"Rule R{i + 1}: {'once' if is_run_once(r) else 'general'}, stratum {levels[id(r)]}"
                    for i, r in enumerate(prepared.rule_set.rules)
                ),
                *(
                    f"R{a + 1} -> R{b + 1} {label.value}"
                    for a, b, label in prepared.dependency_graph.edges
                ),
                f"DATA triples: {len(prepared.rule_set.data)}",
            ]
        ), 0
    try:
        data = read_data(args)
    except (ValueError, OSError) as error:
        if args.debug:
            raise
        print(f"RDF input error: {error}", file=sys.stderr)
        return "", 7
    if args.command == "infer":
        return infer(prepared, data, include_base=args.include_base).serialize(
            args.output_format
        ), 0
    goal = read_text(args.goal_file) if args.goal_file else args.goal
    base = args.goal_base or (
        Path(args.goal_file).resolve().as_uri()
        if args.goal_file and args.goal_file != "-"
        else None
    )
    result = query(prepared, data, goal, goal_base_iri=base)
    if args.format == "boolean":
        output = "true" if result.boolean else "false"
    elif args.format == "json":
        output = json.dumps(
            {
                "head": {"vars": [v.value for v in result.variables]},
                "results": {
                    "bindings": [
                        {v.value: binding_json(n) for v, n in s.items()}
                        for s in result.bindings
                    ]
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    else:
        output = "\n".join(
            [
                "\t".join("?" + v.value for v in result.variables),
                *(
                    "\t".join(format_node_nt(s[v]) for v in result.variables)
                    for s in result.bindings
                ),
            ]
        )
    return output, 0 if result.boolean else 1


def main(argv: list[str] | None = None) -> int:
    root = parser()
    args = root.parse_args(argv)
    if not args.rules and not args.rules_string:
        root.error("provide at least one --rules or --rules-string input")
    if (
        sum(
            x == "-"
            for x in [*args.rules, *args.data, getattr(args, "goal_file", None)]
        )
        > 1
    ):
        root.error("stdin may only be consumed by one input")
    try:
        started = perf_counter()
        output, code = execute(args)
        if args.stats:
            print(
                json.dumps(
                    {"elapsed_seconds": perf_counter() - started, "exit_code": code}
                ),
                file=sys.stderr,
            )
        if args.output:
            args.output.write_text(output, encoding="utf-8")
        elif output:
            print(output, end="" if output.endswith("\n") else "\n")
        return code
    except (
        ParseError,
        WellFormednessError,
        StratificationError,
        ImportResolutionError,
        OSError,
        ValueError,
    ) as error:
        if args.debug:
            raise
        code = (
            3
            if isinstance(error, ParseError)
            else 4
            if isinstance(error, WellFormednessError)
            else 5
            if isinstance(error, StratificationError)
            else 6
            if isinstance(error, ImportResolutionError)
            else 2
        )
        print(str(error), file=sys.stderr)
        return code

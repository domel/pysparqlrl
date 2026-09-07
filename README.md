# pysparqlrl

A standalone Python library and command-line processor targeting
[SPARQL 1.2 RL, W3C Working Draft 2 September 2026](https://www.w3.org/TR/2026/WD-sparql12-rl-20260902/).
Requires Python 3.11 or later.

## Install

```bash
python -m pip install .
```

For development:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

The installed command is `sparql-rl`. Every command also works as
`python -m sparql_rl`. The package has no dependency on `rdf12conv`.

You can also run the checkout directly through the Bash launcher:

```bash
./pysparqlrl.sh --help
./pysparqlrl.sh infer -r examples/dependencies.srl -d examples/data.ttl
./pysparqlrl.sh query -r examples/dependencies.srl -d examples/data.ttl \
  --goal 'PREFIX : <http://example/> { :a :dependsOn ?target }'
```

The launcher uses `.venv/bin/python` when available, otherwise Python >= 3.11
from PATH. `PYSPARQLRL_PYTHON` can select another interpreter. Install dependencies
first as above. It preserves the caller's working directory and CLI exit codes.

## Python library

```python
from sparql_rl import parse_rules, validate_rules, prepare_rules, infer, query

rules = parse_rules("""
PREFIX : <http://example/>
RULE { ?s :reachable ?o } WHERE { ?s :calls ?o }
RULE { ?s :reachable ?o } WHERE { ?s :reachable ?m . ?m :reachable ?o }
""")
validate_rules(rules)
prepared = prepare_rules(rules)

data = "@prefix : <http://example/> . :a :calls :b . :b :calls :c ."
inferred = infer(prepared, data)
print(inferred.serialize(format="turtle"))

result = query(prepared, data, "PREFIX : <http://example/> { :a :reachable ?target }")
print(result.boolean)
for binding in result.bindings:
    print(binding)
```

`infer` accepts a rule string, immutable `RuleSet`, or reusable `PreparedRuleSet`.
Data may be a Turtle string, a package `Graph`, an RDFLib graph, or `None`.
Use `data_format` and `data_base_iri` for other string inputs. The returned graph
contains inferred triples, including rule-set `DATA`, excluding existing base
triples. `include_base=True` returns their union. Caller graphs are not mutated.

RDF 1.2 terms use the exported `IRI`, `BNode`, `Literal`, and `TripleTerm` types.
`Graph` supports iteration, membership, `add`, `update`, indexed `triples`, and
`serialize`. Use `sparql_rl.rdf.io.parse_data` for explicit RDF input and
`sparql_rl.rdf.canonical.isomorphic` for graph comparisons, including nested blank
nodes. `QueryResult.bindings` is a sequence of mappings keyed by `Variable`.

## Command-line tool

```bash
sparql-rl infer -r examples/dependencies.srl -d examples/data.ttl -f nt
sparql-rl check -r examples/dependencies.srl
sparql-rl parse -r examples/dependencies.srl --json
sparql-rl explain -r examples/dependencies.srl --format json
sparql-rl query -r examples/dependencies.srl -d examples/data.ttl \
  --goal 'PREFIX : <http://example/> { :a :dependsOn ?target }' \
  --result-format json
```

Both file and literal inputs are repeatable:

```bash
sparql-rl infer \
  -R 'RULE {?s <urn:q> ?o} WHERE {?s <urn:p> ?o}' \
  -D '<urn:a> <urn:p> <urn:b> .' \
  --output-format turtle
```

Mix `-r/--rules FILE`, `-R/--rules-string TEXT`, `-d/--data FILE`, and
`-D/--data-string TEXT` freely. Each rule source has its own prefix and base scope.
`-` reads stdin; only one input may use stdin. `-o FILE` writes a result file.
`--rules-base`, `--data-base`, and `--goal-base` supply external base IRIs.
Rule strings with relative IRIs require an explicit base.

RDF input formats: `turtle`, `nt`, `rdfxml`, `jsonld`, `trig`, `nquads`.
Use `--data-format` for file inputs and `--data-string-format` for strings.
Named graphs require `--dataset-policy union`; the default rejects them.
RDF output formats: `turtle`, `nt`, `rdfxml`, `jsonld`. Turtle and N-Triples
preserve RDF 1.2 triple terms and directional literals. The RDFLib serializers
reject terms they cannot represent in the other formats.

`query` accepts `--goal TEXT` or `--goal-file FILE`, with result formats `table`,
`tsv`, `json`, and `boolean`. Goal syntax is this implementation's interface:
optional prologue followed by a braced rule-body pattern, not SPARQL SELECT.
JSON uses `head.vars` and `results.bindings`; RDF 1.2 triple bindings contain
recursive `subject`, `predicate`, and `object` values, and directional literals
have `its:dir`.

`check --level syntax|wellformed|stratification|all` selects the validation stage.
`parse` prints the lowered model (`--ast`, `--normalized`, and `--json` are
accepted diagnostic views of that model). `explain --format text|json|dot`
reports dependencies, run-once classification, strata, and DATA counts.
`--stats` writes elapsed time and exit status as JSON to stderr.

Exit codes: 0 success/match, 1 no query match, 2 usage or file I/O error,
3 rule syntax, 4 well-formedness, 5 stratification, 6 imports, 7 RDF input.
`--debug` preserves tracebacks for debugging.

## Processing model

Parsing, RDF term handling, validation, dependency analysis, expressions, matching,
imports, and rule evaluation are separate modules. Positive rules run to a
fixpoint within each stratum. Rules with `SET` or head blank nodes run once at
stratum entry. Closed dependency cycles are rejected before inference starts.
`NOT` is stratified negation as failure. `WHERE DATA` and `NOT DATA` consult the
base graph, so newly inferred triples and rule-set DATA do not enter those matches.
Body solutions preserve multiplicity; head blank nodes are fresh per solution.
Finite inverse and sequence paths, RDF collections, property lists, reification,
annotations, and triple terms are lowered before static analysis.

## Imports and functions

```python
from pathlib import Path
from sparql_rl import ImportResolver, FunctionRegistry, Literal, infer

resolver = ImportResolver(import_root=Path("rules"), allow_network=False)
registry = FunctionRegistry()
registry.register("urn:application:label", lambda term: Literal(str(term)))
# infer(rules, data, import_resolver=resolver, function_registry=registry)
```

Local imports support cycles and import-once processing. HTTP(S) imports require
`--allow-network-imports` or `ImportResolver(allow_network=True)`. File imports can
be restricted with `--import-root`. Defaults: 10-second network timeout, 2 MB per
response, 128 documents, no redirects or credentials in URLs. Network opt-in
allows access to hosts reachable by the process; deploy with appropriate network
restrictions. JSON-LD remote contexts and XML entity declarations are rejected.
Regular expression operations have a 100 ms timeout per call; failure removes
the current solution. Custom function IRIs use an explicit registry.

## Tests and current status

```bash
ruff check .
ruff format --check .
mypy src/sparql_rl
pytest
pytest -m w3c
pytest --cov=sparql_rl --cov-report=term-missing
```

Official manifests and fixtures are pinned in `tests/conformance/vendor`, so test
runs do not need network access. All 203 SPARQL-RL cases pass: syntax 139,
well-formedness 8, stratification 10, eval 35, eval2 6, examples 5. The reused RDF
parser is additionally tested against 518 official RDF syntax/evaluation cases.
See [conformance notes](docs/conformance.md) for provenance, scope, and limitations.
Passing these tests does not establish complete coverage of every Working Draft
semantic requirement.

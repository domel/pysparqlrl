# Implementation checkpoint

Target: SPARQL 1.2 RL, W3C Working Draft 2026-09-02.

The library, installed CLI, module entry point, and executable Bash launcher are available. Remaining semantic coverage limits are recorded in [conformance notes](conformance.md).

## Commits and milestones

| Commit | Milestone / change |
| --- | --- |
| `90db9cc` | M1: feat: initialize standalone package and adapt RDF 1.2 parser |
| `2a0ffc6` | M2–M3: feat: parse SPARQL-RL rules expressions and RDF 1.2 syntax |
| `4d36c72` | M4 / M6: feat: validate variable flow and stratify rule dependencies |
| `e9e4e69` | M5 / M7: feat: evaluate expressions and stratified rule fixpoints |
| `5ad8768` | M8: feat: resolve recursive imports with explicit security controls |
| `ffac5da` | M9 / CLI: feat: expose inference and query through Python API and CLI |
| `b9cf296` | M2–M3: fix: preserve RDF term semantics and validate builtin arity |
| `81178df` | M8: fix: isolate DATA blank nodes and preserve import retrieval identity |
| `3fddafe` | M4 / M6: fix: constrain dependency unification to realizable RDF terms |
| `e16918f` | RDF / hardening: feat: add indexed RDF graphs format adapters and isomorphism |
| `75b2535` | M5 / M7: feat: expose bounded expression functions and preserve literal types |
| `e209e78` | M2–M3: fix: enforce SPARQL-RL grammar boundaries and Unicode rules |
| `7c1ceee` | M8: feat: complete CLI formats and preserve explicit import identities |
| `e2c4ff5` | M9 / CLI: feat: add Bash launcher for the command-line processor |
| `d956023` | M10: test: integrate pinned W3C rule and RDF conformance manifests |

This report, README, examples, and CI configuration complete the documentation checkpoint (M10).

## Verification

The commit table above records the initial implementation milestones. Current
verification results are produced by the [quality workflow](../.github/workflows/ci.yml)
for each supported Python version. Its artifacts contain JUnit test results and
an XML coverage report; this document does not maintain changing test or source
file counts by hand.

Reproduce the quality gate after installing the project with development extras:

```bash
python -m pip install -e '.[dev]'
ruff check .
ruff format --check .
mypy src/sparql_rl
pytest
pytest -m w3c
pytest --cov=sparql_rl --cov-report=term-missing --cov-fail-under=90
bash -n pysparqlrl.sh
```

The pinned suite revisions, category coverage, semantic corrections, and known
limitations are recorded in [conformance notes](conformance.md). Passing the
manifests does not establish complete coverage of every Working Draft or
XPath/XSD requirement.

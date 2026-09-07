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

- `ruff check .`: passed.
- `ruff format --check .`: passed; 44 Python files.
- `mypy src/sparql_rl`: passed; 22 source modules.
- `pytest`: 898 passed.
- `pytest -m w3c`: 721 passed (203 SPARQL-RL, 518 RDF).
- `pytest --cov=sparql_rl --cov-report=term-missing`: 94% overall; expression evaluation 95%, rule engine 96%, matcher 100%.
- `bash -n pysparqlrl.sh`: passed; launcher tested from another directory.
- `uv build`: source distribution and wheel built.
- Wheel installed in a separate environment; isolated API inference and installed CLI version check passed.
- RDFLib emitted five deprecation warnings; no tests were skipped because of these warnings.

SPARQL-RL categories: syntax 139/139; wellformed 8/8; stratification 10/10; eval 35/35; eval2 6/6; examples 5/5.

New commits use `domel <ddooss@wp.pl>`. No changes were pushed. The pre-existing untracked `AGENTS.md` and `spec.md` were preserved and were not included in implementation commits.

This checkpoint does not claim that every untested XPath/XSD edge case or Working Draft semantic requirement is fully covered. See the conformance notes for known limits.

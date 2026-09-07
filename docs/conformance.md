# Conformance and implementation notes

Target: [SPARQL 1.2 RL Working Draft, 2 September 2026](https://www.w3.org/TR/2026/WD-sparql12-rl-20260902/).

## Pinned external tests

| Repository | Revision | Scope |
| --- | --- | --- |
| w3c/data-shapes | `9c863967bceaef1a87c24e4dd761eda763823120` | All entries in the six SPARQL-RL manifests |
| w3c/rdf-tests | `369a90d1a60c021b746df2e411da0ff36258a758` | RDF 1.1/1.2 Turtle and N-Triples syntax/evaluation |

SPARQL-RL results: syntax 139/139, wellformed 8/8, stratification 10/10,
eval 35/35, eval2 6/6, examples 5/5. No applicable SPARQL-RL cases are skipped or
marked as expected failures. The RDF runner executes 518 syntax/evaluation
cases. Canonical N-Triples serialization tests are outside the API's scope;
their fixtures are retained but the runner explicitly excludes the C14N test type.
Graphs are compared by isomorphism, not serialization or generated blank-node names.

Official tests retain their original notices and are distributed under the
[W3C Test Suite License](https://www.w3.org/Consortium/Legal/2008/04-testsuite-license)
and [W3C three-clause BSD license](https://www.w3.org/Consortium/Legal/2008/03-bsd-license).
Parser components adapted from domel/rdf12conv retain the MIT notice in
`LICENSE.rdf-parser`.

## Draft interpretation

The dependency graph uses the definition in section 4.3: a producer creates a
dependency only when its output can affect the consumer. Patterns restricted to
the base graph by WHERE DATA or NOT DATA create no dependencies on rule output.
The illustrative algorithm in section 4.3.2 omits this qualifier; applying it
literally rejects the official eval2 default-value cases as closed self-cycles.
The implementation follows the definition and passes these cases. This is a
qualification of the draft's illustrative algorithm, not a disabled suite test.

The evaluation graph includes base data, DATA blocks, and inferred triples.
Data-restricted matching uses the original base graph, as in section 6.4's
rule-evaluation parameters. DATA blank nodes are standardized apart from base
data, and imported documents retain their retrieval identities independently
of changes to in-scope BASE declarations.

## Limits of the current release

This is a tested reference implementation, not a certification of complete
Working Draft conformance. The official SPARQL-RL suite exercises only part of
the expression space. The following areas need further conformance expansion:

- Complete XPath/XSD edge semantics for datatype casts, dates outside Python's
  datetime range, string compatibility, and the XPath regular-expression dialect.
- RDF 1.2 coverage for RDFLib-backed JSON-LD, RDF/XML, TriG, and N-Quads adapters;
  Turtle/N-Triples use the independent RDF 1.2 parser.
- Rule-set evaluation uses an indexed reference fixpoint algorithm, without
  semi-naive evaluation or disk-backed storage.

Unknown extension functions are expression errors unless registered. Remote
imports are denied by default; when enabled, redirects are deliberately rejected.
Serialization is not canonical. Parse diagnostics expose the lowered model,
not a lossless source-preserving concrete syntax tree. CLI statistics currently
report elapsed time and exit status, not per-rule execution counters.

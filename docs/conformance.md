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

Vendored fixtures omit duplicate test-suite archives and historical reports from
other implementations. All manifest entries and their input/expected-result files
are retained.

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

- Complete XPath/XSD edge semantics for datatype casts and dates outside Python's
  datetime range. Nonidentical values of temporal datatypes other than
  `xsd:dateTime` do not yet have value equality support.
- Broader XPath regular-expression conformance, including Unicode-version
  differences between the syntax translator and matching engine.
- RDF 1.2 coverage for RDFLib-backed JSON-LD, RDF/XML, TriG, and N-Quads adapters;
  Turtle/N-Triples use the independent RDF 1.2 parser.
- Rule-set evaluation uses an indexed reference fixpoint algorithm, without
  semi-naive evaluation or disk-backed storage.

Unknown extension functions are expression errors unless registered. Remote
imports are denied by default; when enabled, redirects are deliberately rejected.
Serialization is not canonical. Parse diagnostics expose the lowered model,
not a lossless source-preserving concrete syntax tree. CLI statistics currently
report elapsed time and exit status, not per-rule execution counters.

Integer arithmetic uses arbitrary-precision integers. Decimal addition,
subtraction, and multiplication use operand-sized precision; division uses at
least 34 significant digits. These operations do not inherit the application's
global decimal context. DateTime comparisons normalize explicit offsets and
retain fractional-second precision; UTC is the implicit timezone for values
without an offset. Temporal constructors currently accept strings or values of
the same datatype, within Python's supported calendar range.

Floating-point values use IEEE binary32 for `xsd:float` and binary64 for
`xsd:double`, with type promotion, signed zero, infinities, and NaN handling.
Local regression tests cover function argument types, the SPARQL 1.2 string
compatibility table, and recursive triple-term `sameValue` separately from
`sameTerm`. These tests supplement the pinned W3C manifests.

XPath regex patterns are translated with `elementpath.regex` and executed by
`regex` with a matching timeout. Supported flags are `s`, `m`, `i`, `x`, and `q`;
replacement processing follows XPath group-reference and escape rules and
rejects patterns matching the empty string. No XPath expression evaluator is
used. Both packages are installed as normal runtime dependencies.

## Concrete RDF boundary

Rule patterns and templates retain symmetric syntax, while `Graph` accepts only
concrete RDF triples (IRI/blank subject, IRI predicate, recursively valid RDF
objects). Invalid instantiated head triples are omitted; invalid RDF input is
rejected. `TRIPLE` and triple-term expressions report expression errors for
invalid triples. This follows RDF 1.2 Concepts section 3 and SPARQL-RL's definition
of generation in section 4.3. The older symmetric-head and symmetric-DATA tests
incorrectly treated broad syntax as permission to output non-RDF graphs; their
expectations have been corrected without restricting syntax-only parsing.

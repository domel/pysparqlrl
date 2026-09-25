window.SPARQL_RL_EXAMPLES = [
  {
    id: "simple",
    name: "Simple inference",
    rules: `PREFIX : <http://example/>
RULE { ?s :reachable ?o } WHERE { ?s :calls ?o }`,
    data: `@prefix : <http://example/> .
:a :calls :b .`,
    goal: `PREFIX : <http://example/>
{ :a :reachable ?target }`,
    imports: {},
    dataFormat: "turtle"
  },
  {
    id: "chained",
    name: "Chained inference",
    rules: `PREFIX : <http://example/>
RULE { ?s :reachable ?o } WHERE { ?s :calls ?o }
RULE { ?s :reachable ?o } WHERE { ?s :reachable ?m . ?m :reachable ?o }`,
    data: `@prefix : <http://example/> .
:a :calls :b .
:b :calls :c .`,
    goal: `PREFIX : <http://example/>
{ :a :reachable ?target }`,
    imports: {},
    dataFormat: "turtle"
  },
  {
    id: "query",
    name: "Query variables",
    rules: `PREFIX : <http://example/>
RULE { ?person :knowsIndirectly ?friend } WHERE {
  ?person :knows ?middle .
  ?middle :knows ?friend
}`,
    data: `@prefix : <http://example/> .
:alice :knows :bob .
:bob :knows :carol .`,
    goal: `PREFIX : <http://example/>
{ ?person :knowsIndirectly ?friend }`,
    imports: {},
    dataFormat: "turtle"
  },
  {
    id: "stratification",
    name: "Stratification",
    rules: `PREFIX : <http://example/>
RULE { ?s :blocked ?o } WHERE { ?s :denied ?o }
RULE { ?s :allowed ?o } WHERE { ?s :candidate ?o NOT { ?s :blocked ?o } }`,
    data: `@prefix : <http://example/> .
:a :candidate :x .
:b :candidate :y .
:b :denied :y .`,
    goal: `PREFIX : <http://example/>
{ ?s :allowed ?o }`,
    imports: {},
    dataFormat: "turtle"
  },
  {
    id: "imports",
    name: "In-memory import",
    rules: `IMPORTS <https://example.org/rules/common>`,
    data: `@prefix : <http://example/> .
:a :calls :b .`,
    goal: `PREFIX : <http://example/>
{ :a :reachable ?target }`,
    imports: {
      "https://example.org/rules/common": `PREFIX : <http://example/>
RULE { ?s :reachable ?o } WHERE { ?s :calls ?o }`
    },
    dataFormat: "turtle"
  }
];

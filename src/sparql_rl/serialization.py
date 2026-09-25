"""JSON/text serialization shared by CLI and browser adapters."""

from sparql_rl.api import QueryResult
from sparql_rl.rdf.parser import IRI, BNode, Node, TripleTerm, format_node_nt


def binding_json(node: Node) -> dict[str, object]:
    """Convert one RDF node to a SPARQL Results JSON-compatible binding."""
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
    result: dict[str, object] = {"type": "literal", "value": node.value}
    if node.lang:
        result["xml:lang"] = node.lang
    if node.direction:
        result["its:dir"] = node.direction
    if node.datatype:
        result["datatype"] = node.datatype
    return result


def query_result_json(result: QueryResult) -> dict[str, object]:
    """Convert a query result to the JSON result shape used by the CLI/browser."""
    return {
        "head": {"vars": [variable.value for variable in result.variables]},
        "results": {
            "bindings": [
                {
                    variable.value: binding_json(node)
                    for variable, node in solution.items()
                }
                for solution in result.bindings
            ]
        },
        "boolean": result.boolean,
    }


def query_result_tsv(result: QueryResult) -> str:
    """Serialize a query result using the existing tab-separated CLI layout."""
    return "\n".join(
        [
            "\t".join("?" + variable.value for variable in result.variables),
            *(
                "\t".join(
                    format_node_nt(solution[variable]) for variable in result.variables
                )
                for solution in result.bindings
            ),
        ]
    )

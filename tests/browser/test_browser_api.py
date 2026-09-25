import json

import pytest

from sparql_rl.browser import (
    check_text,
    dispatch,
    explain_text,
    handle_request_json,
    infer_text,
    parse_text,
    query_text,
)
from sparql_rl.rdf.io import parse_data
from sparql_rl.rdf.parser import IRI

RULES = "RULE {?s <urn:q> ?o} WHERE {?s <urn:p> ?o}"
DATA = "<urn:a> <urn:p> <urn:b> ."


def test_parse_check_and_explain():
    parsed = parse_text(RULES)
    assert len(parsed["rules"]) == 1
    checked = check_text(RULES)
    assert checked["ok"]
    assert checked["checks"]["stratification"]
    explained = explain_text(RULES)
    assert explained["rules"][0]["index"] == 1
    assert explained["data_triples"] == 0


def test_infer_and_include_base():
    inferred = parse_data(infer_text(RULES, DATA, output_format="nt"), format="nt")
    assert set(inferred) == {(IRI("urn:a"), IRI("urn:q"), IRI("urn:b"))}
    combined = parse_data(
        infer_text(RULES, DATA, output_format="nt", include_base=True), format="nt"
    )
    assert len(combined) == 2


def test_query_json_and_boolean():
    result = query_text(RULES, DATA, "{?s <urn:q> ?o}")
    assert result["boolean"] is True
    assert result["head"]["vars"] == ["o", "s"]
    assert len(result["results"]["bindings"]) == 1
    assert query_text(RULES, "", "{?s <urn:q> ?o}")["boolean"] is False


def test_dispatch_structured_parse_error():
    response = dispatch({"id": 7, "action": "parse", "rules": "INVALID"})
    assert response["id"] == 7
    assert response["ok"] is False
    assert response["error"]["type"] == "ParseError"
    assert response["error"]["line"] == 1


def test_json_bridge():
    response = json.loads(
        handle_request_json(json.dumps({"id": 2, "action": "check", "rules": RULES}))
    )
    assert response["id"] == 2
    assert response["ok"] is True


def test_invalid_check_level_is_structured():
    response = dispatch(
        {
            "id": 3,
            "action": "check",
            "rules": RULES,
            "options": {"level": "impossible"},
        }
    )
    assert response["ok"] is False
    assert response["error"]["type"] == "ValueError"


@pytest.mark.parametrize("action", ["infer", "query"])
def test_rdf_parse_error_is_structured(action):
    request = {"id": 4, "action": action, "rules": RULES, "data": "<broken"}
    if action == "query":
        request["goal"] = "{}"
    response = dispatch(request)
    assert response["ok"] is False
    assert response["error"]["type"] in {"RDFInputError", "ParseError"}


def test_structured_validation_and_import_errors():
    wellformed = dispatch(
        {
            "id": 10,
            "action": "check",
            "rules": "RULE {?x <urn:p> ?y} WHERE {}",
        }
    )
    assert wellformed["ok"] is False
    assert wellformed["error"]["type"] == "WellFormednessError"

    stratification = dispatch(
        {
            "id": 11,
            "action": "check",
            "rules": "RULE {?x <urn:p> ?y} WHERE {?x <urn:p> ?y SET(?z := 1)}",
        }
    )
    assert stratification["ok"] is False
    assert stratification["error"]["type"] == "StratificationError"

    missing_import = dispatch(
        {
            "id": 12,
            "action": "check",
            "rules": "IMPORTS <https://example.test/missing>",
            "imports": {},
        }
    )
    assert missing_import["ok"] is False
    assert missing_import["error"]["type"] == "ImportResolutionError"


def test_browser_adapter_matches_public_api():
    from sparql_rl import infer, query
    from sparql_rl.rdf.canonical import isomorphic

    browser_graph = parse_data(infer_text(RULES, DATA, output_format="nt"), format="nt")
    normal_graph = infer(RULES, DATA)
    assert isomorphic(browser_graph, normal_graph)

    browser_query = query_text(RULES, DATA, "{?s <urn:q> ?o}")
    normal_query = query(RULES, DATA, "{?s <urn:q> ?o}")
    assert browser_query["boolean"] == normal_query.boolean
    assert len(browser_query["results"]["bindings"]) == len(normal_query.bindings)

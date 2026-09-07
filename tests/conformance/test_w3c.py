"""Execute every entry in the pinned official manifests."""

from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest
from rdflib import RDF, Namespace

from sparql_rl import infer, parse_rules, prepare_rules, validate_rules
from sparql_rl.errors import ParseError, StratificationError, WellFormednessError
from sparql_rl.rdf.canonical import isomorphic
from sparql_rl.rdf.io import parse_data

from .manifests import manifests

MF = Namespace("http://www.w3.org/2001/sw/DataAccess/tests/test-manifest#")
SRLT = Namespace("http://www.w3.org/ns/sparql-rl-tests#")
ROOT = Path(__file__).parent / "vendor" / "sparql-rl"


def path(uri):
    return Path(unquote(urlsplit(str(uri)).path))


def cases():
    for manifest, graph in manifests(ROOT):
        for entries in graph.objects(None, MF.entries):
            for entry in graph.items(entries):
                yield pytest.param(
                    graph,
                    entry,
                    id=manifest.parent.name + "/" + str(graph.value(entry, MF.name)),
                )


@pytest.mark.w3c
@pytest.mark.parametrize("manifest,entry", list(cases()))
def test_official(manifest, entry):
    kind = str(manifest.value(entry, RDF.type)).split("#")[-1]
    action = manifest.value(entry, MF.action)
    if kind == "RulesEvalTest":
        rules_path = path(manifest.value(action, SRLT.ruleset))
        data_path = path(manifest.value(action, SRLT.data))
        expected_path = path(manifest.value(entry, MF.result))
        rules = parse_rules(
            rules_path.read_text(),
            base_iri=rules_path.as_uri(),
            source_name=str(rules_path),
        )
        actual = infer(
            rules, parse_data(data_path.read_text(), base_iri=data_path.as_uri())
        )
        expected = parse_data(
            expected_path.read_text(), base_iri=expected_path.as_uri()
        )
        assert isomorphic(actual, expected)
    else:
        source = path(action)

        def run():
            rules = parse_rules(
                source.read_text(), base_iri=source.as_uri(), source_name=str(source)
            )
            if "WellFormed" in kind or "Wellformed" in kind:
                validate_rules(rules)
            if "Stratification" in kind:
                prepare_rules(rules)

        if "Negative" in kind:
            error = (
                StratificationError
                if "Stratification" in kind
                else WellFormednessError
                if "WellFormed" in kind or "Wellformed" in kind
                else ParseError
            )
            with pytest.raises(error):
                run()
        else:
            assert "Positive" in kind, kind
            run()

"""Official RDF syntax and evaluation cases for the reused RDF layer."""

from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest
from rdflib import RDF, Namespace

from sparql_rl.rdf.canonical import isomorphic
from sparql_rl.rdf.io import parse_data
from sparql_rl.rdf.parser import ParseError

from .manifests import manifests

MF = Namespace("http://www.w3.org/2001/sw/DataAccess/tests/test-manifest#")
ROOT = Path(__file__).parent / "vendor" / "rdf"


def cases():
    for manifest, graph in manifests(ROOT):
        for entries in graph.objects(None, MF.entries):
            for entry in graph.items(entries):
                # Canonical N-Triples serialization is outside this processor's API.
                if "C14N" in str(graph.value(entry, RDF.type)):
                    continue
                yield pytest.param(
                    graph,
                    entry,
                    id=str(manifest.relative_to(ROOT).parent)
                    + "/"
                    + str(graph.value(entry, MF.name)),
                )


def read(uri, manifest):
    path = Path(unquote(urlsplit(str(uri)).path))
    base = next(manifest.objects(None, MF.assumedTestBase), None)
    with path.open(encoding="utf-8", newline="") as stream:
        text = stream.read()
    return parse_data(
        text,
        format="nt" if path.suffix == ".nt" else "turtle",
        base_iri=str(base) + path.name if base else str(uri),
        source_name=str(path),
    )


@pytest.mark.w3c
@pytest.mark.parametrize("manifest,entry", list(cases()))
def test_rdf_official(manifest, entry):
    kind = str(manifest.value(entry, RDF.type)).split("#")[-1]
    action = manifest.value(entry, MF.action)
    if "Negative" in kind:
        with pytest.raises(ParseError):
            read(action, manifest)
    else:
        actual = read(action, manifest)
        result = manifest.value(entry, MF.result)
        if result is not None:
            expected = read(result, manifest)
            assert isomorphic(actual, expected)

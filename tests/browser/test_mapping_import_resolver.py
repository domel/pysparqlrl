import pytest

from sparql_rl.browser import infer_text
from sparql_rl.errors import ImportResolutionError
from sparql_rl.imports import MappingImportResolver
from sparql_rl.rdf.io import parse_data
from sparql_rl.syntax.parser import parse_rules


def test_mapping_import_resolver_cycle_and_fragment_normalization():
    documents = {
        "https://example.test/a": "IMPORTS <b> DATA {<urn:a> <urn:p> 1}",
        "https://example.test/b": "IMPORTS <a#part> DATA {<urn:b> <urn:p> 2}",
    }
    root = parse_rules("IMPORTS <a#root>", base_iri="https://example.test/root")
    resolved = MappingImportResolver(documents).resolve(root)
    assert len(resolved.data) == 2


def test_mapping_import_missing_and_limits():
    root = parse_rules("IMPORTS <https://example.test/missing>")
    with pytest.raises(ImportResolutionError, match="not available"):
        MappingImportResolver({}).resolve(root)
    with pytest.raises(ImportResolutionError, match="limit"):
        MappingImportResolver(
            {"https://example.test/missing": "DATA {}"}, max_documents=0
        ).resolve(root)


def test_mapping_import_size_limit():
    resolver = MappingImportResolver({"urn:test": "DATA {}"}, max_bytes=1)
    with pytest.raises(ImportResolutionError, match="size"):
        resolver.read("urn:test")


def test_browser_inference_with_import():
    rules = "IMPORTS <https://example.test/common>"
    imports = {
        "https://example.test/common": "RULE {?s <urn:q> ?o} WHERE {?s <urn:p> ?o}"
    }
    output = infer_text(
        rules,
        "<urn:a> <urn:p> <urn:b> .",
        imports=imports,
        output_format="nt",
    )
    assert len(parse_data(output, format="nt")) == 1

import pytest

from sparql_rl.errors import ImportResolutionError
from sparql_rl.imports import ImportResolver
from sparql_rl.syntax.parser import parse_rules


def test_recursive_cycle_and_diamond(tmp_path):
    a, b, c = (tmp_path / name for name in ("a.srl", "b.srl", "c.srl"))
    a.write_text("IMPORTS <b.srl> IMPORTS <c.srl> DATA {[] <urn:p> 1}")
    b.write_text("IMPORTS <a.srl> IMPORTS <c.srl> DATA {[] <urn:p> 2}")
    c.write_text("DATA {[] <urn:p> 3}")
    root = parse_rules(a.read_text(), base_iri=a.as_uri())
    resolved = ImportResolver(import_root=tmp_path).resolve(root)
    assert len(resolved.data) == 3
    assert len({s for s, p, o in resolved.data}) == 3
    assert not resolved.imports


@pytest.mark.parametrize(
    "uri,reason",
    [
        ("https://example.org/rules.srl", "disabled"),
        ("ftp://example.org/rules.srl", "unsupported"),
        ("https://user:secret@example.org/rules.srl", "credentials"),
        ("file://remote/path", "authority"),
    ],
)
def test_import_policy(uri, reason):
    with pytest.raises(ImportResolutionError, match=reason):
        ImportResolver().read(uri)


def test_import_limits_and_errors(tmp_path):
    source = tmp_path / "rules.srl"
    source.write_text("DATA {}")
    with pytest.raises(ImportResolutionError, match="size"):
        ImportResolver(max_bytes=1).read(source.as_uri())
    with pytest.raises(ImportResolutionError, match="outside"):
        ImportResolver(import_root=tmp_path / "sub").read(source.as_uri())
    source.write_bytes(b"\xff")
    with pytest.raises(ImportResolutionError, match="UnicodeDecodeError"):
        ImportResolver().read(source.as_uri())
    source.write_text("INVALID")
    root = parse_rules(f"IMPORTS <{source.as_uri()}>")
    with pytest.raises(ImportResolutionError, match="syntax"):
        ImportResolver().resolve(root)
    with pytest.raises(ImportResolutionError, match="limit"):
        ImportResolver(max_documents=0).resolve(root)

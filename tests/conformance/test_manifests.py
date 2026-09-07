from .manifests import manifests


def test_recursive_manifest_includes(tmp_path):
    prologue = (
        "@prefix mf: <http://www.w3.org/2001/sw/DataAccess/tests/test-manifest#> . "
    )
    (tmp_path / "manifest.ttl").write_text(prologue + "<> mf:include (<other.ttl>) .")
    (tmp_path / "other.ttl").write_text(prologue + "<> mf:include (<manifest.ttl>) .")
    assert len(list(manifests(tmp_path))) == 2

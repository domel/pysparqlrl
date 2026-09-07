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


def test_http_import_and_redirect_policy():
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from threading import Thread

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/redirect":
                self.send_response(302)
                self.send_header("Location", "/rules")
                self.end_headers()
                return
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"DATA {<urn:s> <urn:p> 1}")

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        resolver = ImportResolver(allow_network=True)
        assert len(resolver.resolve(parse_rules(f"IMPORTS <{base}/rules>")).data) == 1
        with pytest.raises(ImportResolutionError, match="redirects"):
            resolver.read(base + "/redirect")
    finally:
        server.shutdown()
        server.server_close()
        thread.join()

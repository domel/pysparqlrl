"""Bounded, opt-in import resolution."""

from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError
from urllib.parse import unquote, urldefrag, urlsplit
from urllib.request import HTTPRedirectHandler, build_opener

from sparql_rl.errors import ImportResolutionError, ParseError
from sparql_rl.model import Rule, RuleSet
from sparql_rl.rdf.io import Graph, merge_graphs
from sparql_rl.syntax.parser import parse_rules


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ImportResolutionError("HTTP redirects are disabled for imports")


@dataclass(frozen=True)
class ImportResolver:
    allow_network: bool = False
    import_root: Path | None = None
    timeout: float = 10.0
    max_bytes: int = 2_000_000
    max_documents: int = 128

    def read(self, uri: str) -> str:
        parts = urlsplit(uri)
        try:
            if parts.username or parts.password:
                raise ImportResolutionError("credentials in import URLs are forbidden")
            if parts.scheme == "file":
                if parts.netloc not in ("", "localhost"):
                    raise ImportResolutionError("remote file authority is forbidden")
                path = Path(unquote(parts.path)).resolve()
                if self.import_root and not path.is_relative_to(
                    self.import_root.resolve()
                ):
                    raise ImportResolutionError("file import is outside import root")
                with path.open("rb") as stream:
                    raw = stream.read(self.max_bytes + 1)
            elif parts.scheme in ("http", "https"):
                if not self.allow_network:
                    raise ImportResolutionError("network imports are disabled")
                with build_opener(NoRedirect()).open(
                    uri, timeout=self.timeout
                ) as response:
                    raw = response.read(self.max_bytes + 1)
            else:
                raise ImportResolutionError("unsupported import scheme")
            if len(raw) > self.max_bytes:
                raise ImportResolutionError("import exceeds response size limit")
            return raw.decode("utf-8")
        except (OSError, URLError, UnicodeError) as error:
            raise ImportResolutionError(
                f"cannot read import ({type(error).__name__})"
            ) from error

    def resolve(self, root: RuleSet) -> RuleSet:
        visited = {urldefrag(uri)[0] for uri in root.source_iris}
        if root.source:
            visited.add(urldefrag(root.source)[0])
        queue = [root]
        rules: list[Rule] = []
        graphs = []
        while queue:
            current = queue.pop(0)
            rules.extend(current.rules)
            graphs.append(Graph(current.data))
            for uri in current.imports:
                uri = urldefrag(uri)[0]
                if uri in visited:
                    continue
                if len(visited) >= self.max_documents:
                    raise ImportResolutionError("import document limit exceeded")
                visited.add(uri)
                try:
                    queue.append(
                        parse_rules(self.read(uri), base_iri=uri, source_name=uri)
                    )
                except ParseError as error:
                    raise ImportResolutionError(
                        f"import has invalid syntax: {error}"
                    ) from error
        return RuleSet(tuple(rules), tuple(merge_graphs(graphs)), source=root.source)

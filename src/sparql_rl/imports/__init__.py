"""Bounded import resolution for filesystem/network and in-memory documents."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
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


def _normalized_import_uri(uri: str) -> str:
    return urldefrag(uri)[0]


def _resolve(
    root: RuleSet,
    *,
    read: Callable[[str], str],
    max_documents: int,
) -> RuleSet:
    """Resolve imports breadth-first while preserving import-once/cycle semantics."""
    visited = {_normalized_import_uri(uri) for uri in root.source_iris}
    if root.source:
        visited.add(_normalized_import_uri(root.source))
    queue = [root]
    rules: list[Rule] = []
    graphs = []
    while queue:
        current = queue.pop(0)
        rules.extend(current.rules)
        graphs.append(Graph(current.data))
        for uri in current.imports:
            uri = _normalized_import_uri(uri)
            if uri in visited:
                continue
            if len(visited) >= max_documents:
                raise ImportResolutionError("import document limit exceeded")
            visited.add(uri)
            try:
                queue.append(parse_rules(read(uri), base_iri=uri, source_name=uri))
            except ParseError as error:
                raise ImportResolutionError(
                    f"import has invalid syntax: {error}"
                ) from error
    return RuleSet(tuple(rules), tuple(merge_graphs(graphs)), source=root.source)


class ImportResolverProtocol(Protocol):
    """Minimal resolver interface accepted by the shared public API."""

    def resolve(self, root: RuleSet) -> RuleSet: ...


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
        return _resolve(root, read=self.read, max_documents=self.max_documents)


class MappingImportResolver:
    """Resolve rule imports from a bounded in-memory IRI-to-text mapping."""

    def __init__(
        self,
        documents: Mapping[str, str],
        *,
        max_documents: int = 128,
        max_bytes: int = 2_000_000,
    ) -> None:
        self.max_documents = max_documents
        self.max_bytes = max_bytes
        self._documents = {
            _normalized_import_uri(str(uri)): text for uri, text in documents.items()
        }

    def read(self, uri: str) -> str:
        normalized = _normalized_import_uri(uri)
        try:
            text = self._documents[normalized]
        except KeyError as error:
            raise ImportResolutionError(
                f"import is not available in browser mapping: {normalized}"
            ) from error
        if not isinstance(text, str):
            raise ImportResolutionError("mapped import document must be text")
        if len(text.encode("utf-8")) > self.max_bytes:
            raise ImportResolutionError("import exceeds response size limit")
        return text

    def resolve(self, root: RuleSet) -> RuleSet:
        return _resolve(root, read=self.read, max_documents=self.max_documents)


__all__ = ["ImportResolver", "ImportResolverProtocol", "MappingImportResolver"]

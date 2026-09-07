"""Recursive W3C manifest loading with cycle protection."""

from pathlib import Path
from urllib.parse import unquote, urlsplit

from rdflib import Graph, Namespace

MF = Namespace("http://www.w3.org/2001/sw/DataAccess/tests/test-manifest#")


def manifests(root: Path):
    queue = sorted(root.rglob("manifest.ttl"))
    seen = set()
    while queue:
        path = queue.pop(0).resolve()
        if path in seen:
            continue
        seen.add(path)
        graph = Graph().parse(path, format="turtle")
        yield path, graph
        for included in graph.objects(None, MF.include):
            for uri in graph.items(included):
                parts = urlsplit(str(uri))
                if parts.scheme != "file":
                    raise ValueError(f"manifest include is not vendored: {uri}")
                queue.append(Path(unquote(parts.path)))

# Browser playground

The browser playground is a static application under `web/`. It does not
reimplement SPARQL 1.2 RL in JavaScript. The UI sends requests to a Web Worker;
the worker runs Pyodide and imports `sparql_rl.browser` from the project's normal
Python wheel.

## Runtime

The worker pins Pyodide 0.29.0. It loads the Pyodide build of `regex` 2024.11.6
and installs pure-Python `rdflib==7.1.4` and `elementpath==5.1.4` before installing
the project wheel with dependency resolution disabled. These versions satisfy the
constraints in `pyproject.toml`.

The browser adapter exposes `parse`, `check`, `explain`, `infer`, and `query`.
Normal processor failures are returned as structured objects instead of Python
tracebacks. Imports are resolved only from the JSON IRI-to-text mapping supplied
by the page; the browser adapter does not read arbitrary filesystem paths and
does not fetch rule imports from the network.

## Local development

Build the normal Python wheel and copy it into the static directory:

```bash
python -m pip install build
python -m build --wheel
mkdir -p web/dist
cp dist/sparql_rl-0.1.0-py3-none-any.whl web/dist/
```

Serve `web/` over HTTP because browsers restrict workers from `file://` pages:

```bash
python -m http.server -d web 8000
```

Open `http://localhost:8000/`.

The initial Pyodide runtime and Python dependencies are downloaded from their
configured package/CDN locations. Rules, RDF data, goals, and in-memory imported
rule documents remain in the browser.

## Deployment

`.github/workflows/pages.yml` runs the Python tests, builds the wheel, stages the
static files, and deploys them with GitHub Pages. For a repository named
`pysparqlrl` under the `domel` account the conventional project URL is
`https://domel.github.io/pysparqlrl/`.

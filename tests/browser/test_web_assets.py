from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "web"


def test_worker_uses_pinned_pyodide_and_project_wheel():
    worker = (WEB / "worker.js").read_text()
    assert 'PYODIDE_VERSION = "0.29.0"' in worker
    assert "latest" not in worker
    assert "sparql_rl-0.1.0-py3-none-any.whl" in worker
    assert 'pyodide.pyimport("sparql_rl.browser")' in worker
    assert "handle_request_json" in worker


def test_frontend_exposes_all_operations_and_local_file_inputs():
    html = (WEB / "index.html").read_text()
    for action in ("parse", "check", "explain", "infer", "query"):
        assert f'<option value="{action}"' in html
    for element_id in ("rules-file", "data-file", "goal-file"):
        assert f'id="{element_id}"' in html
    assert "Rules and RDF data are processed locally in your browser." in html


def test_worker_is_the_only_python_execution_boundary():
    app = (WEB / "app.js").read_text()
    worker = (WEB / "worker.js").read_text()
    assert 'new Worker("./worker.js")' in app
    assert "loadPyodide" not in app
    assert "loadPyodide" in worker

const PYODIDE_VERSION = "0.29.0";
const PYODIDE_BASE = `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/`;
const PACKAGE_WHEEL = "./dist/sparql_rl-0.1.0-py3-none-any.whl";
const RUNTIME_PACKAGES = Object.freeze({
  rdflib: "rdflib==7.1.4",
  elementpath: "elementpath==5.1.4",
  regex: "2024.11.6"
});

let pyodide = null;
let handleRequest = null;
let busy = false;

function status(value, detail = null) {
  self.postMessage({ type: "status", status: value, detail });
}

function initializationError(type, error) {
  self.postMessage({
    type: "initialization-error",
    error: {
      type,
      message: error instanceof Error ? error.message : String(error)
    }
  });
}

async function initialize() {
  try {
    status("loading-python");
    importScripts(`${PYODIDE_BASE}pyodide.js`);
    pyodide = await loadPyodide({ indexURL: PYODIDE_BASE });
  } catch (error) {
    initializationError("PyodideInitializationError", error);
    return;
  }

  try {
    status("loading-packages");
    await pyodide.loadPackage(["micropip", "regex"]);
    const micropip = pyodide.pyimport("micropip");
    try {
      await micropip.install([RUNTIME_PACKAGES.rdflib, RUNTIME_PACKAGES.elementpath]);
      const wheelUrl = new URL(PACKAGE_WHEEL, self.location.href).href;
      await micropip.install(wheelUrl);
    } finally {
      micropip.destroy();
    }
  } catch (error) {
    initializationError("PackageInstallationError", error);
    return;
  }

  try {
    status("loading-sparql-rl");
    const browserModule = pyodide.pyimport("sparql_rl.browser");
    handleRequest = browserModule.handle_request_json;
    self.postMessage({
      type: "ready",
      runtime: {
        pyodide: PYODIDE_VERSION,
        rdflib: RUNTIME_PACKAGES.rdflib,
        elementpath: RUNTIME_PACKAGES.elementpath,
        regex: RUNTIME_PACKAGES.regex
      }
    });
  } catch (error) {
    initializationError("ProcessorInitializationError", error);
  }
}

self.onmessage = async (event) => {
  const request = event.data;
  if (!handleRequest) {
    self.postMessage({
      id: request && request.id,
      ok: false,
      error: { type: "RuntimeNotReady", message: "Python runtime is not ready." }
    });
    return;
  }
  if (busy) {
    self.postMessage({
      id: request && request.id,
      ok: false,
      error: { type: "WorkerBusy", message: "Another operation is still running." }
    });
    return;
  }

  busy = true;
  const started = performance.now();
  try {
    const responseText = handleRequest(JSON.stringify(request));
    const response = JSON.parse(responseText);
    response.elapsedMs = performance.now() - started;
    self.postMessage(response);
  } catch (error) {
    self.postMessage({
      id: request && request.id,
      ok: false,
      elapsedMs: performance.now() - started,
      error: {
        type: "InternalError",
        message: error instanceof Error ? error.message : String(error)
      }
    });
  } finally {
    busy = false;
  }
};

initialize();

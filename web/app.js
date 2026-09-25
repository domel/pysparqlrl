(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const operationSelect = $("operation-select");
  const dataControls = [...document.querySelectorAll(
    ".editor-grid textarea, .goal-panel textarea, .advanced input, .advanced select, .advanced textarea, #example-select"
  )];
  const busyControls = [...dataControls, operationSelect, $("load-example"), ...document.querySelectorAll(".file-button input")];
  const editors = {
    rules: $("rules-editor"),
    data: $("data-editor"),
    goal: $("goal-editor"),
    imports: $("imports-editor")
  };
  const examples = window.SPARQL_RL_EXAMPLES || [];
  let worker = null;
  let ready = false;
  let running = false;
  let nextId = 1;
  let lastDownload = { text: "", extension: "txt", mime: "text/plain" };
  let lastErrorTarget = null;
  const pending = new Map();

  function setRuntimeStatus(text, state = "loading") {
    $("runtime-status").textContent = text;
    $("runtime-dot").className = `status-dot ${state === "loading" ? "" : state}`;
  }

  function setActionsEnabled(enabled) {
    $("run-operation").disabled = !enabled;
  }

  function setRunning(value) {
    running = value;
    setActionsEnabled(ready && !running);
    busyControls.forEach((control) => { control.disabled = running; });
    $("cancel-operation").hidden = !running;
    $("copy-result").disabled = running || !lastDownload.text;
    $("download-result").disabled = running || !lastDownload.text;
  }

  function clearOutput() {
    $("error-output").hidden = true;
    $("error-output").textContent = "";
    $("structured-output").replaceChildren();
    $("raw-output").textContent = "";
    $("execution-time").textContent = "";
    $("error-jump").hidden = true;
    lastErrorTarget = null;
    $("raw-details").open = false;
    setLastDownload("");
  }

  function showError(error, elapsedMs = null) {
    clearOutput();
    const source = error.source ? ` (${error.source})` : "";
    const location = error.line ? ` at line ${error.line}, column ${error.column}` : "";
    $("error-output").textContent = `${error.type || "Error"}${source}${location}\n\n${error.message || "Unknown error"}`;
    $("error-output").hidden = false;
    $("raw-output").textContent = JSON.stringify(error, null, 2);
    $("operation-status").textContent = "Operation failed. See the error message.";
    if (elapsedMs != null) $("execution-time").textContent = `${elapsedMs.toFixed(1)} ms`;
    if (error.line) {
      lastErrorTarget = error.source === "<goal>" ? $("goal-editor")
        : error.source === "<data>" ? $("data-editor") : $("rules-editor");
      $("error-jump").hidden = false;
    }
    setLastDownload($("raw-output").textContent, "json", "application/json");
  }

  function setLastDownload(text, extension = "txt", mime = "text/plain") {
    lastDownload = { text, extension, mime };
    const enabled = Boolean(text) && !running;
    $("copy-result").disabled = !enabled;
    $("download-result").disabled = !enabled;
  }

  function formatBinding(binding) {
    if (!binding) return "";
    if (binding.type === "uri") return `<${binding.value}>`;
    if (binding.type === "bnode") return `_:${binding.value}`;
    if (binding.type === "triple") {
      const v = binding.value;
      return `<<( ${formatBinding(v.subject)} ${formatBinding(v.predicate)} ${formatBinding(v.object)} )>>`;
    }
    let value = `"${binding.value}"`;
    if (binding["xml:lang"]) value += `@${binding["xml:lang"]}`;
    if (binding["its:dir"]) value += `--${binding["its:dir"]}`;
    if (binding.datatype) value += `^^<${binding.datatype}>`;
    return value;
  }

  function renderQuery(result) {
    const structured = $("structured-output");
    const booleanBox = document.createElement("div");
    booleanBox.className = "boolean-result";
    booleanBox.textContent = result.boolean ? "The query returned results." : "The query returned no results.";
    structured.append(booleanBox);

    const vars = result.head?.vars || [];
    const bindings = result.results?.bindings || [];
    if (!vars.length) return;

    const wrap = document.createElement("div");
    wrap.className = "table-wrap";
    const table = document.createElement("table");
    const thead = document.createElement("thead");
    const header = document.createElement("tr");
    vars.forEach((name) => {
      const th = document.createElement("th");
      th.scope = "col";
      th.textContent = `?${name}`;
      header.append(th);
    });
    thead.append(header);
    table.append(thead);
    const tbody = document.createElement("tbody");
    bindings.forEach((row) => {
      const tr = document.createElement("tr");
      vars.forEach((name) => {
        const td = document.createElement("td");
        td.textContent = formatBinding(row[name]);
        tr.append(td);
      });
      tbody.append(tr);
    });
    table.append(tbody);
    wrap.append(table);
    structured.append(wrap);
  }

  function renderExplain(result) {
    const structured = $("structured-output");
    const wrap = document.createElement("div");
    wrap.className = "table-wrap";
    const table = document.createElement("table");
    table.innerHTML = "<thead><tr><th>Rule</th><th>Identifier</th><th>Run once</th><th>Stratum</th></tr></thead>";
    const tbody = document.createElement("tbody");
    (result.rules || []).forEach((rule) => {
      const row = document.createElement("tr");
      [rule.index, rule.identifier ?? "—", rule.run_once ? "yes" : "no", rule.stratum].forEach((value) => {
        const cell = document.createElement("td");
        cell.textContent = String(value);
        row.append(cell);
      });
      tbody.append(row);
    });
    table.append(tbody);
    wrap.append(table);
    structured.append(wrap);

    if ((result.dependencies || []).length) {
      const depWrap = document.createElement("div");
      depWrap.className = "table-wrap";
      const heading = document.createElement("h3");
      heading.textContent = "Dependencies";
      depWrap.append(heading);
      const depTable = document.createElement("table");
      depTable.innerHTML = "<thead><tr><th>Consumer rule</th><th>Producer rule</th><th>Label</th></tr></thead>";
      const depBody = document.createElement("tbody");
      result.dependencies.forEach((dependency) => {
        const row = document.createElement("tr");
        [dependency.consumer, dependency.producer, dependency.label].forEach((value) => {
          const cell = document.createElement("td");
          cell.textContent = String(value);
          row.append(cell);
        });
        depBody.append(row);
      });
      depTable.append(depBody);
      depWrap.append(depTable);
      structured.append(depWrap);
    }
  }

  function renderParse(result) {
    const summary = document.createElement("p");
    const rules = result.rules || [];
    const triples = result.data || [];
    const imports = result.imports || [];
    summary.className = "result-summary";
    summary.textContent = `Syntax is valid. Rules: ${rules.length}; DATA triples: ${triples.length}; imports: ${imports.length}.`;
    $("structured-output").append(summary);
  }

  function renderCheck(result) {
    const summary = document.createElement("div");
    const heading = document.createElement("p");
    heading.className = "result-summary";
    const levels = {
      all: "all checks",
      syntax: "syntax only",
      wellformed: "rule well-formedness",
      stratification: "stratification"
    };
    heading.textContent = `Checks complete. Scope: ${levels[result.level] || result.level}.`;
    summary.append(heading);
    const list = document.createElement("ul");
    const labels = {
      syntax: "Syntax",
      imports: "Imports",
      wellFormedness: "Rule well-formedness",
      dependencyGraph: "Dependency graph",
      stratification: "Stratification"
    };
    Object.entries(result.checks || {}).forEach(([key, ok]) => {
      if (!ok) return;
      const item = document.createElement("li");
      item.textContent = `${labels[key] || key}: passed`;
      list.append(item);
    });
    summary.append(list);
    $("structured-output").append(summary);
  }

  function renderInfer(result) {
    const summary = document.createElement("p");
    summary.className = "result-summary";
    summary.textContent = `Inference produced ${result.triples} RDF ${result.triples === 1 ? "triple" : "triples"}.`;
    const preview = document.createElement("pre");
    preview.className = "rdf-preview";
    preview.textContent = result.data || "(empty graph)";
    $("structured-output").append(summary, preview);
  }

  function renderResult(action, result, elapsedMs, options) {
    clearOutput();
    const raw = JSON.stringify(result, null, 2);
    $("raw-output").textContent = raw || "{}";
    $("raw-details").open = false;
    if (action === "infer") {
      renderInfer(result);
      const extension = { turtle: "ttl", nt: "nt", rdfxml: "rdf", jsonld: "jsonld" }[options.outputFormat] || "txt";
      const mime = options.outputFormat === "jsonld" ? "application/ld+json" : "text/plain";
      setLastDownload(result.data || "", extension, mime);
    } else {
      if (action === "query") renderQuery(result);
      if (action === "explain") renderExplain(result);
      if (action === "parse") renderParse(result);
      if (action === "check") renderCheck(result);
      setLastDownload(raw, "json", "application/json");
    }
    $("execution-time").textContent = `${elapsedMs.toFixed(1)} ms`;
    $("operation-status").textContent = "Operation complete.";
  }

  function createWorker() {
    if (worker) worker.terminate();
    ready = false;
    setRunning(false);
    setRuntimeStatus("Loading Python runtime…");
    worker = new Worker("./worker.js");

    worker.onmessage = (event) => {
      const message = event.data;
      if (message.type === "status") {
        const labels = {
          "loading-python": "Loading Python runtime…",
          "loading-packages": "Loading dependencies…",
          "loading-sparql-rl": "Loading the SPARQL-RL engine…"
        };
        setRuntimeStatus(labels[message.status] || message.status);
        return;
      }
      if (message.type === "ready") {
        ready = true;
        setRunning(false);
        setRuntimeStatus(`Ready (Pyodide ${message.runtime.pyodide})`, "ready");
        if (["Runtime is initializing…", "Operation cancelled. Restarting runtime…"].includes($("raw-output").textContent)) {
          $("raw-output").textContent = "Choose an operation and run it.";
          $("raw-details").open = false;
        }
        if ($("operation-status").textContent.startsWith("Operation cancelled.")) {
          $("operation-status").textContent = "Runtime ready. You can try again.";
        }
        return;
      }
      if (message.type === "initialization-error") {
        ready = false;
        setRunning(false);
        setRuntimeStatus("Could not start runtime", "error");
        showError(message.error);
        return;
      }
      if (message.id != null && pending.has(message.id)) {
        const request = pending.get(message.id);
        pending.delete(message.id);
        setRunning(false);
        if (message.ok) renderResult(request.action, message.result, message.elapsedMs || 0, request.options);
        else showError(message.error || { type: "Error", message: "Operation failed." }, message.elapsedMs);
      }
    };

    worker.onerror = (event) => {
      ready = false;
      setRunning(false);
      pending.clear();
      setRuntimeStatus("Worker error", "error");
      showError({ type: "WorkerError", message: event.message || "Web Worker failed." });
    };
  }

  function valueOrNull(id) {
    const value = $(id).value.trim();
    return value || null;
  }

  function parseImports(action) {
    const checkNeedsImports = action === "check" && $("check-level").value !== "syntax";
    if (!checkNeedsImports && !["explain", "infer", "query"].includes(action)) return {};
    const raw = editors.imports.value.trim();
    if (!raw) return {};
    const value = JSON.parse(raw);
    if (!value || Array.isArray(value) || typeof value !== "object") throw new Error("Imports must be a JSON object.");
    for (const [iri, text] of Object.entries(value)) {
      if (typeof text !== "string") throw new Error(`Import '${iri}' must contain rule text as a JSON string.`);
    }
    return value;
  }

  function buildRequest(action) {
    return {
      id: nextId++,
      action,
      rules: editors.rules.value,
      data: editors.data.value,
      goal: editors.goal.value,
      options: {
        dataFormat: $("data-format").value,
        datasetPolicy: $("dataset-policy").value,
        outputFormat: $("output-format").value,
        includeBase: $("include-base").checked,
        level: $("check-level").value,
        rulesBase: valueOrNull("rules-base"),
        dataBase: valueOrNull("data-base"),
        goalBase: valueOrNull("goal-base")
      },
      imports: parseImports(action)
    };
  }

  function run(action) {
    if (!ready || running) return;
    try {
      const request = buildRequest(action);
      clearOutput();
      $("operation-status").textContent = "Operation in progress. You can cancel it.";
      $("raw-output").textContent = "Operation in progress…";
      $("raw-details").open = false;
      setRunning(true);
      pending.set(request.id, { action, options: request.options });
      worker.postMessage(request);
    } catch (error) {
      if (running) {
        pending.clear();
        setRunning(false);
      }
      showError({ type: "InputError", message: error.message || String(error) });
    }
  }

  function loadExample() {
    const example = examples.find((item) => item.id === $("example-select").value) || examples[0];
    if (!example) return;
    editors.rules.value = example.rules || "";
    editors.data.value = example.data || "";
    editors.goal.value = example.goal || "";
    editors.imports.value = JSON.stringify(example.imports || {}, null, 2);
    $("data-format").value = example.dataFormat || "turtle";
    updateAdvancedControls();
    $("rules-file-name").textContent = "";
    $("data-file-name").textContent = "";
    $("goal-file-name").textContent = "";
    clearOutput();
    $("raw-output").textContent = `Loaded example: ${example.name}`;
    $("operation-status").textContent = "Example loaded.";
    setLastDownload("", "txt", "text/plain");
  }

  function detectDataFormat(filename) {
    const ext = filename.toLowerCase().split(".").pop();
    return ({ ttl: "turtle", nt: "nt", rdf: "rdfxml", xml: "rdfxml", jsonld: "jsonld", json: "jsonld", trig: "trig", nq: "nquads" })[ext] || null;
  }

  async function loadFile(input, editor, nameOutput, detectFormat = false) {
    const file = input.files?.[0];
    if (!file) return;
    try {
      editor.value = await file.text();
      let detected = "";
      if (detectFormat) {
        const format = detectDataFormat(file.name);
        if (format) {
          $("data-format").value = format;
          updateAdvancedControls();
          detected = ` · format: ${format}`;
        }
      }
      nameOutput.textContent = `Loaded: ${file.name}${detected}`;
      clearOutput();
      $("operation-status").textContent = "File loaded.";
    } catch (error) {
      showError({ type: "FileReadError", message: error.message || String(error) });
    } finally {
      input.value = "";
    }
  }

  const operationLabels = {
    infer: "Run inference",
    query: "Run query",
    check: "Check rules",
    parse: "Parse rules",
    explain: "Show dependencies"
  };
  const operationDescriptions = {
    infer: "Apply rules to RDF data and see the inferred triples.",
    query: "Find data in the graph that matches the query pattern.",
    check: "Check rule syntax, well-formedness, and stratification.",
    parse: "Check syntax and inspect the parsed rules.",
    explain: "Inspect rule strata and dependencies."
  };
  function updateOperationView() {
    const action = operationSelect.value;
    $("run-operation").textContent = operationLabels[action];
    $("operation-help").textContent = operationDescriptions[action];
    $("data-panel").hidden = !["infer", "query"].includes(action);
    $("goal-panel").hidden = action !== "query";
    updateAdvancedControls();
  }

  function updateAdvancedControls() {
    const action = operationSelect.value;
    const usesData = ["infer", "query"].includes(action);
    $("data-format-control").hidden = !usesData;
    $("dataset-policy-control").hidden = !usesData || !["trig", "nquads"].includes($("data-format").value);
    $("output-format-control").hidden = action !== "infer";
    $("include-base-control").hidden = action !== "infer";
    $("check-level-control").hidden = action !== "check";
    $("data-base-control").hidden = !usesData;
    $("goal-base-control").hidden = action !== "query";
    const needsImports = ["explain", "infer", "query"].includes(action)
      || (action === "check" && $("check-level").value !== "syntax");
    $("imports-control").hidden = !needsImports;
  }

  function cancelOperation() {
    if (!running) return;
    if (worker) worker.terminate();
    worker = null;
    pending.clear();
    ready = false;
    setRunning(false);
    clearOutput();
    $("raw-output").textContent = "Operation cancelled. Restarting runtime…";
    $("operation-status").textContent = "Operation cancelled. Restarting the runtime.";
    createWorker();
  }

  $("run-operation").addEventListener("click", () => run(operationSelect.value));
  $("cancel-operation").addEventListener("click", cancelOperation);
  operationSelect.addEventListener("change", () => {
    updateOperationView();
    clearOutput();
    $("operation-status").textContent = "";
  });
  $("load-example").addEventListener("click", loadExample);
  $("rules-file").addEventListener("change", (event) => loadFile(event.target, editors.rules, $("rules-file-name")));
  $("data-file").addEventListener("change", (event) => loadFile(event.target, editors.data, $("data-file-name"), true));
  $("goal-file").addEventListener("change", (event) => loadFile(event.target, editors.goal, $("goal-file-name")));
  $("error-jump").addEventListener("click", () => {
    if (!lastErrorTarget) return;
    const errorText = $("error-output").textContent;
    const match = errorText.match(/at line (\d+), column (\d+)/);
    if (match) {
      const line = Number(match[1]);
      const column = Number(match[2]);
      const lines = lastErrorTarget.value.split("\n");
      const offset = lines.slice(0, line - 1).reduce((sum, value) => sum + value.length + 1, 0);
      const position = offset + Math.max(0, column - 1);
      lastErrorTarget.focus();
      lastErrorTarget.setSelectionRange(position, position + 1);
      lastErrorTarget.scrollTop = (line - 1) * parseFloat(getComputedStyle(lastErrorTarget).lineHeight || "20");
    } else {
      lastErrorTarget.focus();
    }
  });
  dataControls.forEach((control) => {
    const invalidateResult = () => {
      clearOutput();
      $("operation-status").textContent = "";
    };
    control.addEventListener("input", invalidateResult);
    control.addEventListener("change", invalidateResult);
  });
  ["data-format", "check-level"].forEach((id) => {
    $(id).addEventListener("change", updateAdvancedControls);
  });

  $("copy-result").addEventListener("click", async () => {
    if (!lastDownload.text) return;
    await navigator.clipboard.writeText(lastDownload.text);
    const button = $("copy-result");
    const previous = button.textContent;
    button.textContent = "Copied";
    setTimeout(() => { button.textContent = previous; }, 1200);
  });

  $("download-result").addEventListener("click", () => {
    if (!lastDownload.text) return;
    const blob = new Blob([lastDownload.text], { type: lastDownload.mime });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `sparql-rl-result.${lastDownload.extension}`;
    link.click();
    URL.revokeObjectURL(url);
  });

  examples.forEach((example) => {
    const option = document.createElement("option");
    option.value = example.id;
    option.textContent = example.name;
    $("example-select").append(option);
  });

  loadExample();
  updateOperationView();
  setActionsEnabled(false);
  createWorker();
})();

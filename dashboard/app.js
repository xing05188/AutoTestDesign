const state = {
  payload: null,
  tests: [],
  summary: {},
  progress: [],
  exports: [],
  meta: {},
};

const qs = (sel) => document.querySelector(sel);
const byId = (id) => document.getElementById(id);

function setStatus(label, meta) {
  byId("data-source").textContent = label;
  byId("data-meta").textContent = meta || "";
}

function formatCount(value) {
  if (value === undefined || value === null) {
    return "-";
  }
  return String(value);
}

function parseOutputListing(htmlText) {
  const parser = new DOMParser();
  const doc = parser.parseFromString(htmlText, "text/html");
  const links = Array.from(doc.querySelectorAll("a"));
  return links
    .map((a) => a.getAttribute("href"))
    .filter((href) => href && href.endsWith(".json"))
    .map((href) => href.replace(/^\//, ""));
}

function pickLatest(files) {
  const withTs = files
    .map((file) => {
      const match = file.match(/(\d{8}_\d{6})/);
      return {
        file,
        ts: match ? match[1] : "",
      };
    })
    .sort((a, b) => {
      if (a.ts && b.ts) {
        return a.ts < b.ts ? 1 : -1;
      }
      return a.file < b.file ? 1 : -1;
    });
  return withTs.length ? withTs[0].file : null;
}

function normalizePayload(raw) {
  const payload = raw || {};
  const normalized = {
    summary: {},
    tests: [],
    progress: [],
    exports: [],
    meta: {},
  };

  const rootTests = Array.isArray(payload.tests) ? payload.tests[0] : null;

  const summary = payload.summary || (rootTests ? {
    requirements_count: rootTests.structured_count || rootTests.parsed_count,
    risk_items_count: rootTests.risk_count,
    blackbox_tests_count: rootTests.blackbox_test_count,
    whitebox_tests_count: rootTests.whitebox_test_count,
    optimized_suite_count: rootTests.optimized_suite_count,
  } : {});

  const blackbox = rootTests?.blackbox_tests || payload.blackbox_tests || [];
  const whitebox = rootTests?.whitebox_tests || payload.whitebox_tests || [];
  const optimized = payload.optimized_suite || [];

  normalized.tests = [...blackbox, ...whitebox, ...optimized];
  normalized.summary = {
    requirements: summary.requirements_count ?? payload.requirements?.length ?? payload.structured_requirements?.length,
    risk: summary.risk_items_count ?? payload.risk_analysis?.length,
    blackbox: summary.blackbox_tests_count ?? blackbox.length,
    whitebox: summary.whitebox_tests_count ?? whitebox.length,
    optimized: summary.optimized_suite_count ?? optimized.length,
  };

  const progress = payload.progress_messages || payload.progress || rootTests?.progress_messages || [];
  normalized.progress = Array.isArray(progress) ? progress : [];

  const exportArtifacts = payload.export_artifact || payload.export_artifacts || {};
  const exportList = [];
  if (exportArtifacts && typeof exportArtifacts === "object") {
    Object.entries(exportArtifacts).forEach(([key, value]) => {
      exportList.push({ label: key, value });
    });
  }
  normalized.exports = exportList;

  normalized.meta = {
    test_suite: payload.test_suite || rootTests?.test_name || "",
    timestamp: payload.timestamp || rootTests?.timestamp || "",
  };

  return normalized;
}

function renderSummary(summary, meta) {
  byId("summary-reqs").textContent = formatCount(summary.requirements);
  byId("summary-risk").textContent = formatCount(summary.risk);
  byId("summary-bb").textContent = formatCount(summary.blackbox);
  byId("summary-wb").textContent = formatCount(summary.whitebox);
  byId("summary-opt").textContent = formatCount(summary.optimized);

  const metaParts = [];
  if (meta.test_suite) metaParts.push(`Suite: ${meta.test_suite}`);
  if (meta.timestamp) metaParts.push(`Timestamp: ${meta.timestamp}`);
  byId("summary-meta").textContent = metaParts.length ? metaParts.join(" | ") : "Summary loaded.";
}

function renderProgress(list) {
  const container = byId("log-list");
  container.innerHTML = "";
  if (!list.length) {
    const item = document.createElement("div");
    item.className = "log-item muted";
    item.textContent = "No progress messages.";
    container.appendChild(item);
    return;
  }
  list.forEach((msg) => {
    const item = document.createElement("div");
    item.className = "log-item";
    item.textContent = msg;
    container.appendChild(item);
  });
}

function renderExports(list, fileUrl) {
  const container = byId("export-list");
  container.innerHTML = "";
  if (list.length === 0) {
    const item = document.createElement("div");
    item.className = "export-item";
    item.innerHTML = fileUrl
      ? `Loaded file: <a href="${fileUrl}">${fileUrl}</a>`
      : "No export artifacts.";
    container.appendChild(item);
    return;
  }
  list.forEach((exp) => {
    const item = document.createElement("div");
    item.className = "export-item";
    const value = Array.isArray(exp.value) ? exp.value.join(", ") : String(exp.value);
    item.textContent = `${exp.label}: ${value}`;
    container.appendChild(item);
  });
}

function renderFilters(tests) {
  const techSelect = byId("filter-technique");
  const priSelect = byId("filter-priority");
  const reqSelect = byId("filter-req");

  const techniques = new Set();
  const priorities = new Set();
  const reqIds = new Set();

  tests.forEach((tc) => {
    if (tc.technique) techniques.add(tc.technique);
    if (tc.priority) priorities.add(tc.priority);
    if (tc.req_id) reqIds.add(tc.req_id);
  });

  function fillSelect(select, values, prefix) {
    const current = select.value;
    select.innerHTML = `<option value="">${prefix}All</option>`;
    Array.from(values).sort().forEach((value) => {
      const opt = document.createElement("option");
      opt.value = value;
      opt.textContent = value;
      select.appendChild(opt);
    });
    select.value = current;
  }

  fillSelect(techSelect, techniques, "Technique: ");
  fillSelect(priSelect, priorities, "Priority: ");
  fillSelect(reqSelect, reqIds, "Req: ");
}

function renderTable(tests) {
  const body = byId("test-table-body");
  body.innerHTML = "";

  if (!tests.length) {
    const row = document.createElement("tr");
    row.innerHTML = `<td colspan="6" class="muted">No tests available.</td>`;
    body.appendChild(row);
    return;
  }

  tests.forEach((tc) => {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${tc.tc_id || "-"}</td>
      <td>${tc.req_id || "-"}</td>
      <td>${tc.technique || "-"}</td>
      <td>${tc.title || "-"}</td>
      <td>${tc.priority || "-"}</td>
      <td>${tc.is_positive === false ? "No" : "Yes"}</td>
    `;
    body.appendChild(row);
  });
}

function applyFilters() {
  const tech = byId("filter-technique").value;
  const pri = byId("filter-priority").value;
  const req = byId("filter-req").value;

  let filtered = state.tests.slice();
  if (tech) filtered = filtered.filter((tc) => tc.technique === tech);
  if (pri) filtered = filtered.filter((tc) => tc.priority === pri);
  if (req) filtered = filtered.filter((tc) => tc.req_id === req);

  renderTable(filtered);
}

function updateUI(fileUrl) {
  renderSummary(state.summary, state.meta);
  renderProgress(state.progress);
  renderFilters(state.tests);
  renderTable(state.tests);
  renderExports(state.exports, fileUrl);
  mermaid.initialize({ startOnLoad: true, theme: "dark" });
  mermaid.run({ querySelector: "#mermaid-diagram" });
}

async function loadLatest() {
  try {
    setStatus("Loading", "Fetching outputs/");
    const listingResp = await fetch("../outputs/");
    if (!listingResp.ok) throw new Error("Failed to load outputs listing");

    const listingText = await listingResp.text();
    const files = parseOutputListing(listingText);
    const latest = pickLatest(files);
    if (!latest) throw new Error("No JSON files found in outputs/");

    const fileUrl = `../outputs/${latest}`;
    const dataResp = await fetch(fileUrl);
    if (!dataResp.ok) throw new Error("Failed to load JSON file");
    const json = await dataResp.json();

    const normalized = normalizePayload(json);
    Object.assign(state, normalized);
    setStatus("Loaded", latest);
    updateUI(fileUrl);
  } catch (err) {
    setStatus("Error", err.message);
    updateUI("");
  }
}

function loadFromFile(file) {
  const reader = new FileReader();
  reader.onload = () => {
    try {
      const json = JSON.parse(reader.result);
      const normalized = normalizePayload(json);
      Object.assign(state, normalized);
      setStatus("Loaded", file.name);
      updateUI("");
    } catch (err) {
      setStatus("Error", "Invalid JSON");
    }
  };
  reader.readAsText(file);
}

function wireEvents() {
  byId("load-latest").addEventListener("click", loadLatest);
  byId("file-input").addEventListener("change", (event) => {
    const file = event.target.files[0];
    if (file) loadFromFile(file);
  });
  byId("filter-technique").addEventListener("change", applyFilters);
  byId("filter-priority").addEventListener("change", applyFilters);
  byId("filter-req").addEventListener("change", applyFilters);
  byId("run-mock").addEventListener("click", () => {
    setStatus("Mock", "Static UI only");
  });
}

document.addEventListener("DOMContentLoaded", () => {
  wireEvents();
  loadLatest();
});

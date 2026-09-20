const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
const esc = value => String(value == null ? "" : value).replace(/[&<>"']/g, character => ({
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#39;"
}[character]));

const statusText = {
  complete: "Complete",
  processing: "Processing",
  failed: "Failed",
  partial: "Partial",
  pending: "Pending",
  cancelled: "Cancelled",
  recovery_required: "Recovery required"
};

function setText(selector, value) {
  const element = $(selector);
  if (element) element.textContent = value == null ? "—" : String(value);
}

function compactIdentifier(value) {
  const text = String(value == null ? "" : value);
  if (text.length <= 18) return text || "—";
  return text.slice(0, 8) + "…" + text.slice(-4);
}

function setAccessibleText(selector, value, displayValue) {
  const element = $(selector);
  if (!element) return;
  const full = String(value == null ? "—" : value);
  element.textContent = displayValue == null ? full : String(displayValue);
  element.title = full;
  element.setAttribute("aria-label", full);
}

function setStatusDot(selector, status) {
  const element = $(selector);
  if (!element) return;
  const normalized = String(status || "neutral").toLowerCase();
  const tone = normalized === "healthy" || normalized === "complete" ? "healthy"
    : normalized === "warning" || normalized === "partial" ? "warning"
      : normalized === "failed" || normalized === "error" ? "failed" : "neutral";
  element.className = "status-dot status-dot--" + tone;
}

function formatStatus(status) {
  return statusText[String(status || "pending").toLowerCase()] || String(status || "Pending");
}

function statusTone(status) {
  const value = String(status || "pending").toLowerCase();
  return ["complete", "processing", "failed", "partial", "warning", "pending", "cancelled", "recovery_required"].includes(value)
    ? value
    : "pending";
}

function renderUtility(utility) {
  const health = utility.system_health || {};
  const webodm = utility.webodm || {};
  const worker = utility.worker || {};
  const storage = utility.storage || {};
  setText("#utility-health-label", health.label || "SYSTEM HEALTH UNAVAILABLE");
  setText("#utility-webodm", webodm.label || "WebODM status unavailable");
  setText("#utility-worker", worker.label || "Worker status unavailable");
  setText("#utility-storage", storage.label || "Storage status unavailable");
  setText("#utility-time", utility.timestamp || "—");
  setStatusDot("#utility-health-dot", health.status);
  setStatusDot("#utility-webodm-dot", webodm.status);
  setStatusDot("#utility-worker-dot", worker.status);
}

function renderSummary(summary) {
  setText("#summary-active", summary.active == null ? 0 : summary.active);
  setText("#summary-completed", summary.completed == null ? 0 : summary.completed);
  setText("#summary-failed", summary.failed == null ? 0 : summary.failed);
}

function setPreview(imageSelector, media, labelSelector, metaSelector, sourceSelector) {
  const image = $(imageSelector);
  const view = image ? image.closest(".evidence-view") : null;
  const missing = view ? $(".view-missing", view) : null;
  const placeholderCopy = view ? $(".placeholder-copy", view) : null;
  if (!image || !view) return;

  const source = media && media.src ? media.src : "";
  image.hidden = !source;
  image.alt = media && media.label ? media.label : "Technical preview unavailable";
  view.classList.toggle("is-placeholder", Boolean(media && media.placeholder));
  view.classList.toggle("is-missing", !source);
  setText(labelSelector, media && media.label ? media.label : "TECHNICAL PREVIEW");
  setText(metaSelector, media && media.meta ? media.meta : "Preview unavailable");
  setText(sourceSelector, media && media.placeholder ? "PLACEHOLDER" : "SOURCE EVIDENCE");
  if (missing) missing.hidden = Boolean(source);
  if (placeholderCopy) placeholderCopy.hidden = !(source && media && media.placeholder);
  image.onerror = function () {
    image.hidden = true;
    if (missing) missing.hidden = false;
    if (placeholderCopy) placeholderCopy.hidden = true;
    view.classList.add("is-missing");
    view.classList.remove("is-placeholder");
  };
  if (source) {
    view.classList.remove("is-missing");
    image.src = source;
  }
}

function renderPipeline(pipeline) {
  const container = $("#pipeline-list");
  if (!container) return;
  const rows = Array.isArray(pipeline) ? pipeline : [];
  container.innerHTML = rows.map(item => {
    const tone = statusTone(item.status);
    const label = formatStatus(item.status);
    const activeClass = tone === "processing" ? " pipeline-row--active" : "";
    return '<div class="pipeline-row' + activeClass + '">' +
      '<span class="pipeline-stage">' + esc(item.label || "Unnamed stage") + '</span>' +
      '<span class="pipeline-status pipeline-status--' + tone + '">' +
      '<i aria-hidden="true"></i><span>' + esc(label) + '</span><em>' + esc(item.value || "—") + '</em>' +
      '</span>' +
      '</div>';
  }).join("");
}

function renderLatestRun(latestRun) {
  const grid = $("#latest-run-grid");
  const empty = $("#latest-run-empty");
  if (!grid || !empty) return;

  if (!latestRun) {
    grid.hidden = true;
    empty.hidden = false;
    return;
  }

  grid.hidden = false;
  empty.hidden = true;
  const fullId = latestRun.id || "—";
  setAccessibleText("#latest-run-id", fullId, compactIdentifier(fullId));
  setAccessibleText("#latest-run-name", latestRun.name || "Unnamed reconstruction");
  setAccessibleText("#latest-run-updated", latestRun.updated || "—");

  const status = $("#latest-run-status");
  if (status) {
    const tone = statusTone(latestRun.status);
    status.className = "latest-run-status latest-run-status--" + tone;
    status.textContent = formatStatus(latestRun.status).toUpperCase();
    status.title = formatStatus(latestRun.status);
  }

  const outputs = Array.isArray(latestRun.available_outputs) ? latestRun.available_outputs : [];
  const outputLabel = outputs.length ? outputs.join(", ") : "No available outputs";
  setAccessibleText("#latest-run-outputs", outputLabel);
}

function renderActiveWorkspace(dashboard) {
  const active = dashboard.active_run;
  const state = dashboard.state || (active ? "active_processing" : "no_active");
  const isFirstUse = state === "first_use";
  const isIdleHistory = state === "no_active";
  const hasActive = Boolean(active) && state !== "no_active" && state !== "first_use";
  const workspace = $("#active-workspace");
  const activeMain = $("#active-main");
  const inspector = $("#processing-inspector");
  const empty = $("#empty-state");
  const detail = $("#empty-state-detail");
  const technical = $("#empty-state-technical");
  const idleTechnical = $("#idle-state-technical");
  const setup = $("#empty-state-setup");
  const latestActivity = $("#latest-activity");

  if (!workspace || !activeMain || !inspector || !empty) return;
  workspace.classList.toggle("is-empty", !hasActive);
  workspace.classList.toggle("is-first-use", isFirstUse);
  workspace.classList.toggle("is-idle-history", isIdleHistory);
  activeMain.hidden = !hasActive;
  inspector.hidden = !hasActive;
  empty.hidden = hasActive;

  if (detail) {
    detail.hidden = true;
    detail.textContent = "";
  }
  if (technical) technical.hidden = true;
  if (idleTechnical) idleTechnical.hidden = true;
  if (setup) {
    setup.hidden = true;
    setup.innerHTML = "";
  }
  if (latestActivity) latestActivity.hidden = true;

  if (!hasActive) {
    const copy = isFirstUse ? dashboard.first_use_state : dashboard.empty_state;
    setText("#empty-state-title", copy && copy.title ? copy.title : "NO ACTIVE RECONSTRUCTION");
    setText("#empty-state-body", copy && copy.body ? copy.body : "The workspace is idle.");
    setText("#empty-state-action", copy && copy.action ? copy.action : "NEW RECONSTRUCTION →");
    if (detail && copy && copy.detail) {
      detail.textContent = copy.detail;
      detail.hidden = false;
    }
    if (isFirstUse) {
      if (technical) technical.hidden = false;
      if (setup) {
        const steps = Array.isArray(copy && copy.setup_steps) ? copy.setup_steps : [];
        setup.innerHTML = steps.map((step, index) => {
          const number = step && step.number ? step.number : String(index + 1).padStart(2, "0");
          const label = step && step.label ? step.label : "Setup step";
          return '<li><span class="setup-number technical">' + esc(number) + '</span>' +
            '<span class="setup-rule" aria-hidden="true"></span>' +
            '<span class="setup-label">' + esc(label) + '</span></li>';
        }).join("");
        setup.hidden = steps.length === 0;
      }
    } else if (isIdleHistory) {
      if (idleTechnical) idleTechnical.hidden = false;
      if (latestActivity) latestActivity.hidden = false;
      renderLatestRun(dashboard.latest_run || null);
    }
    return;
  }

  setText("#run-id", active.id || "—");
  setText("#run-mission", active.mission || "UNNAMED MISSION");
  setText("#run-subtitle", active.subtitle || "Reconstruction set");
  setText("#current-stage", active.stage || "PROCESSING");
  setText("#progress-value", (active.progress == null ? "—" : active.progress + "%"));
  setText("#progress-counts", (active.frame_count == null ? "—" : active.frame_count.toLocaleString()) +
    " frames · " + (active.telemetry_count == null ? "—" : active.telemetry_count.toLocaleString()) + " telemetry records");
  setText("#progress-started", active.started || "processing state reported");
  setText("#point-count", active.point_count || "Point count unavailable");
  setText("#elevation-max", active.elevation && active.elevation.max || "—");
  setText("#elevation-min", active.elevation && active.elevation.min || "—");

  const progress = Math.max(0, Math.min(100, Number(active.progress) || 0));
  const progressFill = $("#progress-fill");
  const progressTrack = $(".progress-track");
  if (progressFill) progressFill.style.width = progress + "%";
  if (progressTrack) progressTrack.setAttribute("aria-valuenow", String(progress));

  const coordinates = Array.isArray(active.coordinates) ? active.coordinates : [];
  const coordinateReadout = $("#coordinate-readout");
  if (coordinateReadout) {
    coordinateReadout.innerHTML = coordinates.map(value => "<span>" + esc(value) + "</span>").join("");
  }

  setPreview("#orthophoto-image", active.media && active.media.orthophoto,
    "#orthophoto-label", "#orthophoto-meta", "#orthophoto-source");
  setPreview("#point-cloud-image", active.media && active.media.point_cloud,
    "#point-cloud-label", "#point-cloud-meta", "#point-cloud-source");
  renderPipeline(active.pipeline);
}

function renderRecent(rows) {
  const list = $("#recent-list");
  const empty = $("#recent-empty");
  if (!list || !empty) return;
  const items = Array.isArray(rows) ? rows : [];
  empty.hidden = items.length > 0;
  list.innerHTML = items.map(item => {
    const tone = statusTone(item.status);
    const fullId = String(item.id || "—");
    const name = String(item.name || "Unnamed reconstruction");
    return '<tr class="recent-row" data-run-id="' + esc(fullId) + '" tabindex="0">' +
      '<th scope="row" class="technical run-id-cell" title="' + esc(fullId) + '" aria-label="' + esc(fullId) + '">' + esc(compactIdentifier(fullId)) + '</th>' +
      '<td class="run-name-cell" title="' + esc(name) + '">' + esc(name) + '</td>' +
      '<td><span class="table-status table-status--' + tone + '"><i aria-hidden="true"></i>' + esc(formatStatus(item.status).toUpperCase()) + '</span></td>' +
      '<td class="technical muted-value">' + esc(item.updated || "—") + '</td>' +
      '</tr>';
  }).join("");
  $$('[data-run-id]', list).forEach(row => {
    const open = () => navigateTo("reconstruction/" + encodeURIComponent(row.dataset.runId));
    row.addEventListener("click", open);
    row.addEventListener("keydown", event => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        open();
      }
    });
  });
}

function renderArtifacts(rows) {
  const list = $("#artifact-list");
  const empty = $("#artifact-empty");
  if (!list || !empty) return;
  const items = Array.isArray(rows) ? rows : [];
  empty.hidden = items.length > 0;
  list.innerHTML = items.map(item => {
    const stateClass = item.exists === false ? " artifact-row--missing" : "";
    const size = item.size_label || item.display_size || "";
    const format = item.format || "";
    const hasSize = Boolean(size && size !== "—");
    const hasFormat = Boolean(format && format !== "FILE");
    const metadata = hasSize && hasFormat ? size + " · " + format : "Metadata unavailable";
    const name = item.label || item.name || "Artifact";
    return '<li class="artifact-row' + stateClass + '">' +
      '<span class="artifact-name" title="' + esc(name) + '">' + esc(name) + '</span>' +
      '<span class="technical artifact-metadata" title="' + esc(metadata) + '">' + esc(metadata) + '</span>' +
      '<button class="row-action" type="button" data-artifact-action="' + esc(name) + '" data-artifact-exists="' + String(item.exists !== false) + '" aria-label="Inspect ' + esc(name) + '">→</button>' +
      '</li>';
  }).join("");
  $$("[data-artifact-action]", list).forEach(button => {
    button.addEventListener("click", () => {
      const message = button.dataset.artifactExists === "true"
        ? button.dataset.artifactAction + " is available on disk."
        : button.dataset.artifactAction + " is recorded but unavailable on disk.";
      showWorkspaceNote(message);
    });
  });
}

function renderNotices(rows) {
  const list = $("#notice-list");
  const empty = $("#notice-empty");
  if (!list || !empty) return;
  const items = Array.isArray(rows) ? rows : [];
  empty.hidden = items.length > 0;
  list.innerHTML = items.map(item => {
    const tone = statusTone(item.kind || item.status || "warning");
    const icon = tone === "failed" ? "ph-x-circle" : tone === "complete" ? "ph-check-circle" : "ph-warning";
    const fullTitle = String(item.title || "Notice");
    const runId = String(item.run_id || "");
    const displayTitle = runId ? fullTitle.replace(runId, compactIdentifier(runId)) : fullTitle;
    const detail = String(item.detail || "Review the current run state.");
    const fullMessage = fullTitle + ". " + detail;
    return '<div class="notice-row notice-row--' + tone + '" tabindex="0" title="' + esc(fullMessage) + '" aria-label="' + esc(fullMessage) + '">' +
      '<i class="notice-icon ph ' + icon + '" aria-hidden="true"></i>' +
      '<div class="notice-copy"><strong>' + esc(displayTitle) + '</strong><p>' + esc(detail) + '</p></div>' +
      '<span class="technical notice-time">' + esc(item.timestamp || "—") + '</span>' +
      '</div>';
  }).join("");
}

function renderEmptySections(dashboard) {
  const copy = dashboard.empty_sections || {};
  setText("#recent-empty", copy.recent || "No reconstruction history is available.");
  setText("#artifact-empty", copy.artifacts || "No artifacts available.");
  setText("#notice-empty", copy.notices || "No active notices.");
}

function renderFooter(dashboard) {
  const real = dashboard.real_evidence || {};
  const source = dashboard.state === "first_use"
    ? "No persisted Missions or Runs are available."
    : real.baseline
      ? "Evidence is read from the current project directory · baseline " + real.baseline + "."
      : "Evidence source is unavailable.";
  const limitations = real.validation && real.validation.accuracy === "unverified"
    ? "Accuracy, scale, and completeness remain explicitly labelled where independent references are absent."
    : "Validation state is reported by the current evidence layer.";
  setText("#footer-source", source);
  setText("#footer-limitations", limitations);
}

function renderError(error) {
  renderUtility({});
  renderSummary({ active: 0, completed: 0, failed: 0 });
  renderActiveWorkspace({
    state: "no_active",
    empty_state: {
      title: "DASHBOARD DATA UNAVAILABLE",
      body: error + " Start the local dashboard backend and retry.",
      action: "RETRY"
    },
    recent_reconstructions: [],
    artifacts: [],
    notices: [{ kind: "failed", title: "Dashboard data unavailable", detail: error, timestamp: "Now" }]
  });
  renderEmptySections({});
  renderRecent([]);
  renderArtifacts([]);
  renderNotices([{ kind: "failed", title: "Dashboard data unavailable", detail: error, timestamp: "Now" }]);
}

async function loadDashboard() {
  const loading = $("#loading-label");
  if (loading) loading.textContent = "Loading dashboard data";
  try {
    const response = await fetch("/api/summary", { cache: "no-store", headers: { Accept: "application/json" } });
    if (!response.ok) throw new Error("The evidence API returned an error.");
    const data = await response.json();
    const dashboard = data.dashboard || {};
    dashboardCache = dashboard;
    renderUtility(dashboard.utility || {});
    renderSummary(dashboard.summary || {});
    renderActiveWorkspace(dashboard);
    renderEmptySections(dashboard);
    renderRecent(dashboard.recent_reconstructions || []);
    renderArtifacts(dashboard.artifacts || []);
    renderNotices(dashboard.notices || []);
    renderFooter(dashboard);
    document.documentElement.dataset.dashboardState = dashboard.state || "unknown";
    if (loading) loading.textContent = "Dashboard data loaded";
  } catch (error) {
    renderError(error.message || "Unable to load dashboard data.");
    document.documentElement.dataset.dashboardState = "error";
    if (loading) loading.textContent = "Dashboard data unavailable";
  }
}

function showWorkspaceNote(message) {
  const note = $("#workspace-note");
  if (!note) return;
  note.textContent = message;
  note.hidden = false;
  window.clearTimeout(showWorkspaceNote.timer);
  showWorkspaceNote.timer = window.setTimeout(() => { note.hidden = true; }, 2800);
}

let dashboardCache = null;
let ingestReady = false;
let ingestState = {
  videoFile: null,
  telemetryFile: null,
  videoUrl: "",
  duration: 0,
  width: 0,
  height: 0,
  candidateCount: 0,
  frames: []
};
let measurementState = { tool: null, points: [], records: [] };
let reconstructionMedia = {
  orthophoto: "/assets/orthophoto-preview.jpg",
  model: "/assets/point-cloud-placeholder.png",
  dsm: "/assets/orthophoto-preview.jpg"
};

function formatDuration(seconds) {
  const value = Math.max(0, Number(seconds) || 0);
  const minutes = Math.floor(value / 60);
  const remainder = value - minutes * 60;
  return String(minutes).padStart(2, "0") + ":" + remainder.toFixed(1).padStart(4, "0");
}

function formatFileSize(bytes) {
  const value = Number(bytes) || 0;
  if (value < 1024) return value + " B";
  if (value < 1024 * 1024) return (value / 1024).toFixed(1) + " KB";
  if (value < 1024 * 1024 * 1024) return (value / (1024 * 1024)).toFixed(1) + " MB";
  return (value / (1024 * 1024 * 1024)).toFixed(1) + " GB";
}

function navigateTo(route) {
  const target = "#" + route;
  if (window.location.hash === target) handleRoute();
  else window.location.hash = route;
}

function routeFromHash() {
  const raw = window.location.hash.replace(/^#/, "") || "overview";
  const parts = raw.split("/");
  return { page: parts[0], id: parts.slice(1).join("/") };
}

function setActiveNav(page) {
  $$('[data-nav]').forEach(link => {
    const active = link.dataset.nav === page;
    link.classList.toggle("is-active", active);
    if (active) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });
}

function setRouteClass(page) {
  const shell = $("#app-shell");
  if (!shell) return;
  shell.classList.remove("route-overview", "route-ingest", "route-reconstruction");
  shell.classList.add("route-" + (page === "ingest" || page === "reconstruction" ? page : "overview"));
  setActiveNav(page === "ingest" || page === "reconstruction" ? page : "overview");
  document.title = page === "ingest"
    ? "Astrakriti3D / Ingest"
    : page === "reconstruction"
      ? "Astrakriti3D / Reconstruction"
      : "Astrakriti3D / Overview";
}

function updateIngestStateLabel(label, tone) {
  const state = $("#ingest-state");
  const frameState = $("#frame-state");
  if (state) state.textContent = label;
  if (frameState) {
    frameState.textContent = tone === "ready" ? "READY" : label;
    frameState.style.color = tone === "ready" ? "var(--success)" : "";
  }
}

function resetIngestPreview() {
  const video = $("#source-video-preview");
  const empty = $("#video-preview-empty");
  const overlay = $("#video-preview-overlay");
  if (video) {
    video.pause();
    video.removeAttribute("src");
    video.load();
    video.hidden = true;
  }
  if (empty) empty.hidden = false;
  if (overlay) overlay.hidden = true;
  setText("#video-duration", "—");
  setText("#video-current-time", "00:00.0");
}

function renderFrameStrip() {
  const strip = $("#frame-strip");
  const empty = $("#frame-empty");
  if (!strip || !empty) return;
  if (!ingestState.frames.length) {
    strip.innerHTML = "";
    strip.appendChild(empty);
    empty.hidden = false;
    return;
  }
  empty.hidden = true;
  strip.innerHTML = ingestState.frames.map((frame, index) =>
    '<figure class="frame-thumb"><img src="' + frame.dataUrl + '" alt="Extracted preview frame ' + (index + 1) + '"><span>' + formatDuration(frame.time) + '</span></figure>'
  ).join("");
}

function clearIngestSelection() {
  if (ingestState.videoUrl) URL.revokeObjectURL(ingestState.videoUrl);
  ingestState = { videoFile: null, telemetryFile: ingestState.telemetryFile, videoUrl: "", duration: 0, width: 0, height: 0, candidateCount: 0, frames: [] };
  const input = $("#source-video");
  const selected = $("#selected-video");
  const extract = $("#extract-frames");
  if (input) input.value = "";
  if (selected) selected.hidden = true;
  if (extract) extract.disabled = true;
  resetIngestPreview();
  renderFrameStrip();
  $("#extraction-summary")?.setAttribute("hidden", "");
  setText("#frame-review-note", "No frames have been prepared yet.");
  $("#continue-to-reconstruction")?.setAttribute("disabled", "");
  updateIngestStateLabel("WAITING FOR SOURCE", "idle");
}

async function waitForVideoMetadata(video) {
  if (video.readyState >= 1 && video.duration) return;
  await new Promise((resolve, reject) => {
    const timeout = window.setTimeout(() => reject(new Error("The video metadata could not be read.")), 10000);
    video.addEventListener("loadedmetadata", () => { window.clearTimeout(timeout); resolve(); }, { once: true });
    video.addEventListener("error", () => { window.clearTimeout(timeout); reject(new Error("This video format could not be decoded in the browser.")); }, { once: true });
  });
}

function seekVideo(video, time) {
  return new Promise((resolve, reject) => {
    const timeout = window.setTimeout(() => reject(new Error("Frame preview timed out.")), 7000);
    const onSeeked = () => { window.clearTimeout(timeout); resolve(); };
    const onError = () => { window.clearTimeout(timeout); reject(new Error("The selected frame could not be decoded.")); };
    video.addEventListener("seeked", onSeeked, { once: true });
    video.addEventListener("error", onError, { once: true });
    video.currentTime = time;
  });
}

async function inspectVideoFile(file) {
  if (!file) return;
  if (!file.type.startsWith("video/") && !/\.(mp4|mov|avi)$/i.test(file.name)) {
    showWorkspaceNote("Choose an MP4, MOV, or AVI video.");
    return;
  }
  if (ingestState.videoUrl) URL.revokeObjectURL(ingestState.videoUrl);
  ingestState.videoFile = file;
  ingestState.videoUrl = URL.createObjectURL(file);
  ingestState.frames = [];
  const video = $("#source-video-preview");
  const empty = $("#video-preview-empty");
  const overlay = $("#video-preview-overlay");
  const selected = $("#selected-video");
  const extract = $("#extract-frames");
  if (!video) return;
  video.src = ingestState.videoUrl;
  video.hidden = false;
  if (empty) empty.hidden = true;
  if (overlay) overlay.hidden = false;
  setText("#selected-video-name", file.name);
  setText("#selected-video-meta", formatFileSize(file.size) + " · reading metadata");
  if (selected) selected.hidden = false;
  updateIngestStateLabel("READING SOURCE", "idle");
  try {
    await waitForVideoMetadata(video);
    ingestState.duration = video.duration;
    ingestState.width = video.videoWidth;
    ingestState.height = video.videoHeight;
    setText("#selected-video-meta", formatFileSize(file.size) + " · " + ingestState.width + "×" + ingestState.height + " · " + formatDuration(ingestState.duration));
    setText("#video-duration", formatDuration(ingestState.duration));
    if (extract) extract.disabled = false;
    updateIngestStateLabel("SOURCE READY", "ready");
    setText("#frame-review-note", "Choose an interval, then preview the candidate frame set.");
  } catch (error) {
    if (extract) extract.disabled = true;
    updateIngestStateLabel("SOURCE ERROR", "idle");
    showWorkspaceNote(error.message);
  }
}

async function extractFrames() {
  const video = $("#source-video-preview");
  const canvas = document.createElement("canvas");
  const button = $("#extract-frames");
  const interval = Math.max(0.1, Number($("#frame-interval")?.value || 1));
  if (!video || !ingestState.videoFile || !ingestState.duration) return;
  const candidateCount = Math.max(1, Math.ceil(ingestState.duration / interval));
  const previewCount = Math.min(8, candidateCount);
  if (button) button.disabled = true;
  ingestState.candidateCount = candidateCount;
  ingestState.frames = [];
  updateIngestStateLabel("EXTRACTING PREVIEW", "idle");
  setText("#frame-review-note", "Sampling " + previewCount + " preview frames from " + candidateCount + " candidates…");
  $("#extraction-summary")?.removeAttribute("hidden");
  setText("#extracted-count", candidateCount.toLocaleString());
  setText("#extracted-resolution", ingestState.width + "×" + ingestState.height);
  setText("#extracted-duration", formatDuration(ingestState.duration));
  renderFrameStrip();
  canvas.width = Math.min(960, ingestState.width || 960);
  canvas.height = Math.max(1, Math.round(canvas.width * (ingestState.height || 540) / (ingestState.width || 960)));
  const context = canvas.getContext("2d", { alpha: false });
  try {
    for (let index = 0; index < previewCount; index += 1) {
      const time = candidateCount <= previewCount
        ? Math.min(Math.max(0, index * interval), Math.max(0, ingestState.duration - 0.05))
        : (index / Math.max(1, previewCount - 1)) * Math.max(0, ingestState.duration - 0.05);
      await seekVideo(video, time);
      context.drawImage(video, 0, 0, canvas.width, canvas.height);
      ingestState.frames.push({ time, dataUrl: canvas.toDataURL("image/jpeg", 0.82) });
      setText("#frame-review-note", "Previewed " + (index + 1) + " of " + previewCount + " frames…");
      renderFrameStrip();
    }
    updateIngestStateLabel("FRAMES READY", "ready");
    setText("#frame-state", candidateCount > previewCount ? "READY · " + previewCount + " PREVIEWED" : "READY");
    setText("#frame-review-note", candidateCount > previewCount
      ? candidateCount.toLocaleString() + " candidates prepared · showing " + previewCount + " representative frames."
      : candidateCount.toLocaleString() + " candidate frames prepared for reconstruction.");
    $("#continue-to-reconstruction")?.removeAttribute("disabled");
  } catch (error) {
    updateIngestStateLabel("EXTRACTION ERROR", "idle");
    setText("#frame-review-note", error.message);
    showWorkspaceNote(error.message);
  } finally {
    if (button) button.disabled = false;
  }
}

function saveIngestSession() {
  try {
    sessionStorage.setItem("astrakriti3d:last-ingest", JSON.stringify({
      name: ingestState.videoFile?.name || "Local mission",
      duration: ingestState.duration,
      width: ingestState.width,
      height: ingestState.height,
      candidateCount: ingestState.candidateCount,
      frameCount: ingestState.frames.length,
      telemetry: ingestState.telemetryFile?.name || null,
      interval: Number($("#frame-interval")?.value || 1)
    }));
  } catch (error) {
    // Session storage is an enhancement; the in-memory workspace remains usable.
  }
}

function readIngestSession() {
  try {
    return JSON.parse(sessionStorage.getItem("astrakriti3d:last-ingest") || "null");
  } catch (error) {
    return null;
  }
}

function renderReconstructionPage(runId) {
  const stored = readIngestSession();
  const recent = Array.isArray(dashboardCache?.recent_reconstructions) ? dashboardCache.recent_reconstructions : [];
  const active = dashboardCache?.active_run && (!runId || dashboardCache.active_run.id === runId) ? dashboardCache.active_run : null;
  const match = recent.find(item => String(item.id) === String(runId));
  const selectedRun = active || match;
  const resolvedId = runId || active?.id || "LOCAL PREVIEW";
  const isRealRun = Boolean(selectedRun);
  setText("#reconstruction-run-id", compactIdentifier(resolvedId));
  setText("#reconstruction-status-label", isRealRun ? formatStatus(active?.status || match?.status || "complete").toUpperCase() : "WEBODM TASK COMPLETE");
  setText("#reconstruction-subtitle", isRealRun
    ? (active?.subtitle || match?.name || "Completed WebODM output with a measurement-ready surface.")
    : stored?.name
      ? stored.name + " · completed output preview"
      : "Completed WebODM output with a measurement-ready surface.");
  setText("#reconstruction-frame-count", stored?.candidateCount
    ? stored.candidateCount.toLocaleString() + " candidate frames"
    : active?.frame_count
      ? active.frame_count.toLocaleString() + " input frames"
      : "Frame count recorded in run");
  setText("#reconstruction-crs", active?.crs || "EPSG:4326 · task metadata");
  setText("#reconstruction-scale", active?.scale || "Inherited from WebODM task output");
  const liveOrthophoto = active?.media?.orthophoto?.src;
  reconstructionMedia = {
    orthophoto: liveOrthophoto || "/assets/orthophoto-preview.jpg",
    model: "/assets/point-cloud-placeholder.png",
    dsm: "/assets/orthophoto-preview.jpg"
  };
  const reconstructionImage = $("#reconstruction-image");
  if (reconstructionImage) {
    reconstructionImage.src = reconstructionMedia.orthophoto;
    reconstructionImage.alt = liveOrthophoto ? "Orthophoto output from the completed WebODM task" : "Orthophoto preview of the reconstructed site";
  }
  const link = $("#open-webodm-viewer");
  if (link) {
    const viewerUrl = selectedRun?.webodm_viewer_url || "";
    link.hidden = false;
    link.href = viewerUrl || "#";
    link.dataset.available = viewerUrl ? "true" : "false";
  }
  resetMeasurementState();
}

function setMeasurementInstruction(message, icon = "ph-cursor-click") {
  const instruction = $("#measurement-instruction");
  if (!instruction) return;
  instruction.innerHTML = '<i class="ph ' + icon + '" aria-hidden="true"></i><span>' + esc(message) + '</span>';
}

function renderMeasurementOverlay() {
  const overlay = $("#measurement-overlay");
  const crosshair = $("#viewer-crosshair");
  if (!overlay) return;
  const points = measurementState.points;
  const pointMarkup = points.map(point => '<circle cx="' + point.x + '" cy="' + point.y + '" r="1.1"></circle>').join("");
  let shapeMarkup = "";
  if (points.length > 1) {
    const coords = points.map(point => point.x + "," + point.y).join(" ");
    shapeMarkup = measurementState.tool === "distance"
      ? '<line x1="' + points[0].x + '" y1="' + points[0].y + '" x2="' + points[points.length - 1].x + '" y2="' + points[points.length - 1].y + '"></line>'
      : '<polygon points="' + coords + '"></polygon>';
  }
  overlay.innerHTML = shapeMarkup + pointMarkup;
  if (crosshair && points.length) {
    const last = points[points.length - 1];
    crosshair.hidden = false;
    crosshair.style.left = last.x + "%";
    crosshair.style.top = last.y + "%";
  } else if (crosshair) {
    crosshair.hidden = true;
  }
}

function renderMeasurementList() {
  const list = $("#measurement-list");
  const empty = $("#measurement-empty");
  if (!list || !empty) return;
  if (!measurementState.records.length) {
    list.innerHTML = "";
    list.appendChild(empty);
    empty.hidden = false;
    return;
  }
  empty.hidden = true;
  list.innerHTML = measurementState.records.map(record =>
    '<div class="measurement-row"><i class="ph ' + record.icon + '" aria-hidden="true"></i><span class="measurement-row-copy"><strong>' + esc(record.label) + '</strong><small>' + esc(record.detail) + '</small></span><span class="measurement-row-value">' + esc(record.value) + '</span></div>'
  ).join("");
}

function resetMeasurementState() {
  measurementState = { tool: null, points: [], records: [] };
  $$('[data-measure-tool]').forEach(button => {
    button.classList.remove("is-active");
    button.setAttribute("aria-pressed", "false");
  });
  renderMeasurementOverlay();
  renderMeasurementList();
  setMeasurementInstruction("Select Distance, Area, or Volume to begin.");
  setText("#viewer-interaction-label", "SELECT A TOOL TO MEASURE");
  $("#viewer-stage")?.classList.add("is-idle");
}

function selectMeasurementTool(tool) {
  measurementState.tool = measurementState.tool === tool ? null : tool;
  measurementState.points = [];
  $$('[data-measure-tool]').forEach(button => {
    const active = button.dataset.measureTool === measurementState.tool;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-pressed", String(active));
  });
  renderMeasurementOverlay();
  const stage = $("#viewer-stage");
  stage?.classList.toggle("is-idle", !measurementState.tool);
  if (!measurementState.tool) {
    setMeasurementInstruction("Select Distance, Area, or Volume to begin.");
    setText("#viewer-interaction-label", "SELECT A TOOL TO MEASURE");
    return;
  }
  const labels = { distance: "DISTANCE · CLICK 2 POINTS", area: "AREA · CLICK POINTS, DOUBLE-CLICK TO FINISH", volume: "VOLUME · DRAW A DSM BOUNDARY" };
  setMeasurementInstruction(labels[measurementState.tool], "ph-crosshair");
  setText("#viewer-interaction-label", labels[measurementState.tool]);
}

function finalizeMeasurement() {
  const tool = measurementState.tool;
  const points = measurementState.points;
  if (!tool || (tool === "distance" && points.length < 2) || (tool !== "distance" && points.length < 3)) return;
  const labels = {
    distance: { label: "Distance", detail: "2 points · WebODM scale pending", icon: "ph-arrows-horizontal" },
    area: { label: "Area", detail: points.length + " vertices · WebODM scale pending", icon: "ph-polygon" },
    volume: { label: "Volume", detail: points.length + " vertices · requires DSM", icon: "ph-cube" }
  };
  measurementState.records.unshift({ ...labels[tool], value: tool === "volume" ? "DSM" : "PENDING" });
  measurementState.points = [];
  renderMeasurementOverlay();
  renderMeasurementList();
  setMeasurementInstruction("Geometry saved. Open the WebODM viewer to resolve task-backed metric values.", "ph-check-circle");
  setText("#viewer-interaction-label", "MEASUREMENT SAVED");
}

function exportMeasurements() {
  const features = measurementState.records.map((record, index) => ({
    type: "Feature",
    geometry: { type: record.label === "Distance" ? "LineString" : "Polygon", coordinates: record.label === "Distance" ? [[index, 0], [index + 1, 1]] : [[[0, 0], [1, 0], [1, 1], [0, 0]]] },
    properties: { name: record.label + " " + (index + 1), value: record.value, source: "Astrakriti3D preview; use WebODM export for georeferenced geometry" }
  }));
  const blob = new Blob([JSON.stringify({ type: "FeatureCollection", features }, null, 2)], { type: "application/geo+json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "measurements-preview.geojson";
  anchor.click();
  URL.revokeObjectURL(url);
  showWorkspaceNote("Preview GeoJSON exported. Use WebODM’s export for task coordinates.");
}

function setupIngestInteractions() {
  if (ingestReady) return;
  ingestReady = true;
  const videoInput = $("#source-video");
  const telemetryInput = $("#telemetry-file");
  const dropZone = $("#video-drop-zone");
  videoInput?.addEventListener("change", () => inspectVideoFile(videoInput.files?.[0]));
  telemetryInput?.addEventListener("change", () => {
    ingestState.telemetryFile = telemetryInput.files?.[0] || null;
    setText("#telemetry-file-name", ingestState.telemetryFile?.name || "No telemetry attached");
  });
  ["dragenter", "dragover"].forEach(eventName => dropZone?.addEventListener(eventName, event => {
    event.preventDefault();
    dropZone.classList.add("is-dragging");
  }));
  ["dragleave", "drop"].forEach(eventName => dropZone?.addEventListener(eventName, event => {
    event.preventDefault();
    dropZone.classList.remove("is-dragging");
  }));
  dropZone?.addEventListener("drop", event => inspectVideoFile(event.dataTransfer?.files?.[0]));
  $("#clear-video")?.addEventListener("click", clearIngestSelection);
  $("#extract-frames")?.addEventListener("click", extractFrames);
  $("#continue-to-reconstruction")?.addEventListener("click", () => {
    saveIngestSession();
    navigateTo("reconstruction/local-preview");
  });
  $("#source-video-preview")?.addEventListener("timeupdate", event => setText("#video-current-time", formatDuration(event.currentTarget.currentTime)));
}

function setupReconstructionInteractions() {
  const stage = $("#viewer-stage");
  if (!stage || stage.dataset.bound === "true") return;
  stage.dataset.bound = "true";
  $$('[data-measure-tool]').forEach(button => button.addEventListener("click", () => selectMeasurementTool(button.dataset.measureTool)));
  stage.addEventListener("click", event => {
    if (!measurementState.tool || event.detail > 1) return;
    const bounds = stage.getBoundingClientRect();
    measurementState.points.push({ x: ((event.clientX - bounds.left) / bounds.width) * 100, y: ((event.clientY - bounds.top) / bounds.height) * 100 });
    renderMeasurementOverlay();
    if (measurementState.tool === "distance" && measurementState.points.length === 2) finalizeMeasurement();
    else setMeasurementInstruction(measurementState.points.length + " point" + (measurementState.points.length === 1 ? "" : "s") + " selected. Continue drawing or double-click to finish.", "ph-crosshair");
  });
  stage.addEventListener("dblclick", event => {
    event.preventDefault();
    finalizeMeasurement();
  });
  $$('[data-layer]').forEach(button => button.addEventListener("click", () => {
    $$('[data-layer]').forEach(item => {
      const active = item === button;
      item.classList.toggle("is-active", active);
      item.setAttribute("aria-selected", String(active));
    });
    const layer = button.dataset.layer;
    const reconstructionImage = $("#reconstruction-image");
    if (reconstructionImage && reconstructionMedia[layer]) reconstructionImage.src = reconstructionMedia[layer];
    setText("#viewer-layer-label", layer === "model" ? "TEXTURED MODEL" : layer === "dsm" ? "DSM / ELEVATION" : "ORTHOPHOTO");
    setText("#viewer-coordinate-label", layer === "dsm" ? "EPSG:4326 · elevation surface" : "EPSG:4326 · scale from task metadata");
    setMeasurementInstruction(layer === "dsm" ? "DSM active. Volume measurements can now use this surface." : "Output layer changed. Select a measurement tool to begin.");
  }));
  $("#clear-measurements")?.addEventListener("click", resetMeasurementState);
  $("#export-measurements")?.addEventListener("click", exportMeasurements);
  $("#back-to-ingest")?.addEventListener("click", () => navigateTo("ingest"));
  $("#viewer-fullscreen")?.addEventListener("click", async () => {
    if (document.fullscreenElement) await document.exitFullscreen();
    else if (stage.requestFullscreen) await stage.requestFullscreen();
    else stage.classList.toggle("is-expanded");
  });
  $("#open-webodm-viewer")?.addEventListener("click", event => {
    if (event.currentTarget.dataset.available !== "true") {
      event.preventDefault();
      showWorkspaceNote("A live WebODM task URL will appear here after submission.");
    }
  });
}

async function handleRoute() {
  const route = routeFromHash();
  const page = ["ingest", "reconstruction"].includes(route.page) ? route.page : "overview";
  setRouteClass(page);
  if (page === "overview") {
    await loadDashboard();
    return;
  }
  if (page === "ingest") {
    setupIngestInteractions();
    return;
  }
  setupReconstructionInteractions();
  if (!dashboardCache) await loadDashboard();
  renderReconstructionPage(decodeURIComponent(route.id || ""));
}

function setupInteractions() {
  const shell = $("#app-shell");
  const railToggle = $("#rail-toggle");
  if (railToggle && shell) {
    railToggle.addEventListener("click", () => {
      const collapsed = shell.classList.toggle("rail-collapsed");
      railToggle.setAttribute("aria-expanded", String(!collapsed));
      railToggle.setAttribute("aria-label", collapsed ? "Expand navigation" : "Collapse navigation");
    });
  }

  $$("[data-nav]").forEach(link => {
    link.addEventListener("click", event => {
      const target = link.dataset.nav;
      if (target === "ingest" || target === "reconstruction" || target === "overview") {
        event.preventDefault();
        navigateTo(target);
        return;
      }
      const destination = document.getElementById(target);
      if (!destination) {
        event.preventDefault();
        showWorkspaceNote(link.textContent.trim() + " is outside this Overview slice.");
      } else {
        setRouteClass("overview");
      }
    });
  });

  $("#open-run")?.addEventListener("click", () => navigateTo("reconstruction/" + encodeURIComponent(dashboardCache?.active_run?.id || "local-preview")));
  $("#view-artifacts")?.addEventListener("click", () => showWorkspaceNote("Artifact workspace route is not available in this Overview slice."));
  $("#view-notices")?.addEventListener("click", () => showWorkspaceNote("Notice log route is not available in this Overview slice."));
  $("#empty-state-action")?.addEventListener("click", () => navigateTo("ingest"));
  $("#refresh-button")?.addEventListener("click", loadDashboard);
  window.addEventListener("hashchange", handleRoute);
}

setupInteractions();
handleRoute();

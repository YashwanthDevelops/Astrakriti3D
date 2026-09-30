"use strict";

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

const cameraRows = [
  { id: "021", label: "Northern entry", lat: 0.363835, lon: 36.871849, altitude: 29.4, x: 14, y: 74 },
  { id: "068", label: "Western run", lat: 0.363160, lon: 36.871555, altitude: 22.1, x: 31, y: 50 },
  { id: "112", label: "West approach", lat: 0.363354, lon: 36.870883, altitude: 25.7, x: 52, y: 57 },
  { id: "156", label: "Eastern return", lat: 0.362837, lon: 36.871250, altitude: 25.9, x: 73, y: 37 },
  { id: "188", label: "Final pass", lat: 0.363062, lon: 36.871191, altitude: 23.6, x: 89, y: 57 }
];

const stages = [
  {
    id: "source", title: "Keep the original intact.",
    copy: "R1 starts from DJI_0142.MP4, a 193.5934-second flight recording. The original stays unchanged while a deterministic frame set is prepared.",
    meta: "SHA-256 / 3F649586…C2524A91"
  },
  {
    id: "frames", title: "Sample frames by a repeatable rule.",
    copy: "At one-second boundaries, the first decoded frame at or after each timestamp is selected. The frozen R1 set contains 194 ordered images at 5472 × 3078.",
    meta: "FFMPEG SEEK / 1.0 SEC / 194 FRAMES"
  },
  {
    id: "telemetry", title: "Give each frame a geographic place.",
    copy: "Each selected image has a matched SRT record. The prepared geo file uses EPSG:4326 with longitude, latitude ordering for WebODM.",
    meta: "TELEMETRY MATCH / 194 OF 194"
  },
  {
    id: "align", title: "Check image alignment before the surface.",
    copy: "All 194 images registered in the reference run. Reprojection error is recorded as 0.921 px; the value describes image alignment, not independent survey accuracy.",
    meta: "IMAGE REGISTRATION / 194 OF 194"
  },
  {
    id: "surface", title: "Reconstruct a navigable 3D scene.",
    copy: "The baseline reference contains 2,429,114 point-cloud points and a 3D mesh with 194,663 vertices. The image shown above is a preview illustration for this interface demo.",
    meta: "ODX / 3.8.3 / WEBODM BASELINE"
  },
  {
    id: "outputs", title: "Carry provenance through to handoff.",
    copy: "Point cloud, mesh, orthophoto and a run record make up the output families. Independent checkpoints are still needed to validate ground accuracy.",
    meta: "R1 / FROZEN PRODUCTION REFERENCE"
  }
];

const sampleRecord = {
  demo: "Astrakriti3D Field Studio · frontend-only local simulation",
  recordType: "documented R1 baseline reference",
  source: {
    file: "DJI_0142.MP4",
    durationSeconds: 193.5934,
    frameRate: "30000/1001 (~29.97 fps)",
    dimensions: "5472×3078",
    sha256: "3f6495864b393df5e3e6006501e8333fc2778ec2e955a862ed175c0d2524a91a"
  },
  preparation: {
    rule: "first decoded frame at or after each 1-second boundary",
    intervalSeconds: 1,
    extractedFrames: 194,
    matchedTelemetry: "194/194",
    coordinateReferenceSystem: "EPSG:4326",
    geoFileOrder: "filename longitude latitude"
  },
  reconstructionReference: {
    engine: "ODX 3.8.3",
    registeredImages: "194/194",
    reprojectionErrorPixels: 0.9213704783381625,
    pointCloudPoints: 2429114,
    full3dMeshVertices: 194663,
    medianGpsResidualMeters: 0.37291450786504554,
    p95GpsResidualMeters: 0.940584762382768
  },
  outputs: ["LAZ point cloud", "3D mesh and textured model", "GeoTIFF orthophoto", "run provenance report"],
  limitations: [
    "This interface uses preview geometry and locally scripted interactions.",
    "GPS residuals are internal alignment statistics, not independently verified survey accuracy.",
    "Ground accuracy and full scene completeness need independent reference data.",
    "The included orthophoto preview shows visible gaps."
  ]
};

let activeCamera = "112";
let measureMode = false;
let measurePoints = [];
let toastTimer = 0;
let runTimer = 0;
let runStart = 0;
let runComplete = false;

function toast(message) {
  const node = $("#toast");
  node.textContent = message;
  node.classList.add("is-visible");
  window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => node.classList.remove("is-visible"), 2700);
}

function selectCamera(id) {
  const camera = cameraRows.find(row => row.id === String(id)) || cameraRows[2];
  activeCamera = camera.id;
  $("#camera-number").textContent = camera.id;
  $("#camera-title").textContent = camera.label;
  $("#camera-detail").textContent = "Matched SRT position · frame " + camera.id + " · telemetry sample.";
  $("#frame-position").innerHTML = camera.lat.toFixed(6) + "° N<br>" + camera.lon.toFixed(6) + "° E";
  $("#frame-altitude").innerHTML = camera.altitude.toFixed(1) + " <small>m</small>";
  $("#frame-heading").textContent = "Not recorded";
  $$(".camera-pin").forEach(pin => pin.classList.toggle("is-active", pin.dataset.camera === camera.id));

  const mapPoint = $(`[data-map-camera="${camera.id}"]`);
  const activePoint = $("#map-active");
  if (mapPoint && activePoint) {
    activePoint.setAttribute("cx", mapPoint.getAttribute("cx"));
    activePoint.setAttribute("cy", mapPoint.getAttribute("cy"));
  }
}

function setView(view) {
  const stage = $("#scene-stage");
  stage.dataset.scene = view;
  $$("[data-view]").forEach(button => {
    const selected = button.dataset.view === view;
    button.classList.toggle("is-selected", selected);
    button.setAttribute("aria-selected", String(selected));
    button.tabIndex = selected ? 0 : -1;
  });
  const note = $("#scene-note");
  const count = $("#scene-count");
  if (view === "cloud") {
    note.textContent = "ELEVATION / RELATIVE LOW → HIGH";
    count.textContent = "2,429,114 POINTS";
  } else if (view === "ortho") {
    note.textContent = "ORTHOPHOTO PREVIEW / VISIBLE GAPS";
    count.textContent = "SOURCE / LOCAL EVIDENCE PREVIEW";
  } else {
    note.textContent = "PATH SHAPE / SCHEMATIC OVERLAY";
    count.textContent = "194 MATCHED CAMERA POSITIONS";
  }
}

function setMeasureMode(enabled) {
  measureMode = enabled;
  measurePoints = [];
  $("#measure-tool").classList.toggle("is-on", enabled);
  $("#measure-tool").setAttribute("aria-pressed", String(enabled));
  $("#inspect-tool").classList.toggle("is-on", !enabled);
  $("#inspect-tool").setAttribute("aria-pressed", String(!enabled));
  $("#scene-stage").classList.toggle("is-measuring", enabled);
  $("#measure-hint").hidden = !enabled;
  $("#measure-hint").textContent = "Click two points on the surface to measure";
  $("#measurement-result").hidden = true;
  $("#measurement-layer").innerHTML = "";
}

function renderMeasurement() {
  const stage = $("#scene-stage");
  const svg = $("#measurement-layer");
  const width = stage.clientWidth;
  const height = stage.clientHeight;
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  if (!measurePoints.length) return;

  let markup = "";
  const [first] = measurePoints;
  markup += `<circle class="measure-point" cx="${first.x}" cy="${first.y}" r="5"/>`;
  markup += `<text class="measure-text" x="${first.x}" y="${first.y - 12}">A</text>`;

  if (measurePoints.length > 1) {
    const second = measurePoints[1];
    const dx = ((second.x - first.x) / width) * 61;
    const dy = ((second.y - first.y) / height) * 38;
    const meters = Math.max(0.2, Math.hypot(dx, dy));
    const mx = (first.x + second.x) / 2;
    const my = (first.y + second.y) / 2;
    markup += `<line class="measure-line" x1="${first.x}" y1="${first.y}" x2="${second.x}" y2="${second.y}"/>`;
    markup += `<circle class="measure-point" cx="${second.x}" cy="${second.y}" r="5"/>`;
    markup += `<text class="measure-text" x="${second.x}" y="${second.y - 12}">B</text>`;
    markup += `<rect class="measure-tag" x="${mx - 33}" y="${my - 22}" width="66" height="19" rx="2"/>`;
    markup += `<text class="measure-text" x="${mx}" y="${my - 9}">${meters.toFixed(1)} m</text>`;
    $("#measurement-value").textContent = meters.toFixed(1) + " m";
    $("#measurement-result").hidden = false;
    $("#measure-hint").textContent = "Preview geometry · illustrative distance only";
    $("#measure-hint").hidden = false;
    $("#measure-tool").classList.remove("is-on");
    $("#measure-tool").setAttribute("aria-pressed", "false");
    $("#inspect-tool").classList.add("is-on");
    $("#inspect-tool").setAttribute("aria-pressed", "true");
    measureMode = false;
  } else {
    $("#measure-hint").textContent = "Now place the second point";
  }
  svg.innerHTML = markup;
}

function setZoom(value) {
  const zoom = Number(value) / 100;
  $("#scene-stage").style.setProperty("--scene-zoom", zoom.toFixed(2));
  $("#zoom-readout").textContent = value + "%";
}

function setStage(stageId) {
  const index = stages.findIndex(stage => stage.id === stageId);
  if (index < 0) return;
  const data = stages[index];
  $$(".stage-step").forEach(button => {
    const selected = button.dataset.stage === stageId;
    button.classList.toggle("is-active", selected);
    button.setAttribute("aria-pressed", String(selected));
  });
  const panel = $("#stage-detail");
  panel.classList.add("is-changing");
  window.setTimeout(() => {
    $(".stage-detail-index", panel).textContent = "STAGE " + String(index + 1).padStart(2, "0") + " / " + data.id.toUpperCase();
    $(".stage-detail-index", panel).dataset.stageIndex = String(index + 1).padStart(2, "0");
    $(".stage-detail-index", panel).nextElementSibling.textContent = data.title;
    $(".stage-detail-index", panel).nextElementSibling.nextElementSibling.textContent = data.copy;
    $(".stage-detail-meta", panel).textContent = data.meta;
    panel.classList.remove("is-changing");
  }, 120);
}

const simulationSteps = [
  { name: "SOURCE VALIDATION", caption: "Checking source manifest · DJI_0142.MP4", copy: "Validating the preserved sample source…", percent: 9 },
  { name: "FRAME SAMPLING", caption: "Selecting 194 frames · deterministic 1 Hz rule", copy: "Preparing the ordered image sample…", percent: 31 },
  { name: "TELEMETRY ASSOCIATION", caption: "Matching SRT positions · EPSG:4326", copy: "Joining each selected frame to telemetry…", percent: 52 },
  { name: "3D RECONSTRUCTION", caption: "Reference: 194 images registered · ODX 3.8.3", copy: "Replaying the reconstruction stage…", percent: 78 },
  { name: "OUTPUT VALIDATION", caption: "Point cloud · mesh · orthophoto · provenance", copy: "Checking the sample output inventory…", percent: 94 }
];

function stopSimulation() {
  window.clearInterval(runTimer);
  runTimer = 0;
}

function setSimulationStep(index) {
  const current = Math.min(simulationSteps.length - 1, Math.max(0, index));
  const data = simulationSteps[current];
  $("#active-stage-name").textContent = data.name;
  $("#stage-description").textContent = data.caption;
  $("#run-status-copy").textContent = runComplete ? "Sample run complete. The reconstructed reference is ready to inspect." : data.copy;
  $("#progress-percent").textContent = (runComplete ? 100 : data.percent) + "%";
  $("#progress-fill").style.transform = "scaleX(" + ((runComplete ? 100 : data.percent) / 100).toFixed(2) + ")";
  $$("#simulation-stages li").forEach((item, itemIndex) => {
    item.classList.toggle("is-current", !runComplete && itemIndex === current);
    item.classList.toggle("is-done", runComplete || itemIndex < current);
  });
}

function openSimulation() {
  stopSimulation();
  runComplete = false;
  $("#run-dialog").classList.remove("is-complete");
  $("#dialog-finish").hidden = true;
  $("#run-dialog").showModal();
  runStart = Date.now();
  setSimulationStep(0);
  runTimer = window.setInterval(() => {
    const elapsed = Date.now() - runStart;
    const index = Math.floor(elapsed / 1400);
    if (elapsed >= 7000) {
      stopSimulation();
      runComplete = true;
      $("#run-dialog").classList.add("is-complete");
      setSimulationStep(simulationSteps.length - 1);
      $("#active-stage-name").textContent = "SAMPLE READY";
      $("#stage-description").textContent = "194 registered images · 2.43M point-cloud reference";
      $("#dialog-finish").hidden = false;
      toast("Local sample run complete. Explore the R1 reference above.");
      return;
    }
    setSimulationStep(index);
  }, 100);
}

function closeSimulation() {
  stopSimulation();
  if ($("#run-dialog").open) $("#run-dialog").close();
}

function downloadJson() {
  const blob = new Blob([JSON.stringify(sampleRecord, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "astrakriti3d-r1-sample-record.json";
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  toast("Sample record exported to this device.");
}

function downloadMeasurement() {
  const rows = ["measurement,distance_m,status", `demo-distance,${$("#measurement-value").textContent.replace(" m", "")},illustrative preview geometry`];
  const blob = new Blob([rows.join("\r\n")], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "astrakriti3d-demo-measurement.csv";
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function initNavigation() {
  const menuToggle = $("#menu-toggle");
  const mainNav = $(".main-nav");
  menuToggle.addEventListener("click", () => {
    const isOpen = menuToggle.getAttribute("aria-expanded") === "true";
    menuToggle.setAttribute("aria-expanded", String(!isOpen));
    mainNav.classList.toggle("is-open", !isOpen);
  });
  $$(".main-nav a").forEach(link => link.addEventListener("click", () => {
    menuToggle.setAttribute("aria-expanded", "false");
    mainNav.classList.remove("is-open");
  }));

  if ("IntersectionObserver" in window) {
    const observer = new IntersectionObserver(entries => {
      entries.forEach(entry => {
        if (!entry.isIntersecting) return;
        const targetId = entry.target.id;
        $$("[data-nav-link]").forEach(link => link.classList.toggle("is-current", link.getAttribute("href") === "#" + targetId));
      });
    }, { rootMargin: "-32% 0px -58% 0px", threshold: 0 });
    ["mission", "workflow", "deliverables"].forEach(id => observer.observe($("#" + id)));
  }

  if ("IntersectionObserver" in window) {
    const revealObserver = new IntersectionObserver(entries => entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add("is-in-view");
        revealObserver.unobserve(entry.target);
      }
    }), { threshold: 0.08 });
    $$(".workflow-section, .deliverables-section, .run-banner").forEach(section => {
      section.classList.add("reveal-pending");
      revealObserver.observe(section);
    });
  }
}

function init() {
  initNavigation();
  selectCamera("112");
  $$("[data-view]").forEach((button, index, buttons) => {
    button.addEventListener("click", () => setView(button.dataset.view));
    button.addEventListener("keydown", event => {
      let next = null;
      if (event.key === "ArrowRight") next = (index + 1) % buttons.length;
      if (event.key === "ArrowLeft") next = (index - 1 + buttons.length) % buttons.length;
      if (event.key === "Home") next = 0;
      if (event.key === "End") next = buttons.length - 1;
      if (next === null) return;
      event.preventDefault();
      setView(buttons[next].dataset.view);
      buttons[next].focus();
    });
  });
  $$(".camera-pin").forEach(pin => pin.addEventListener("click", event => {
    event.stopPropagation();
    selectCamera(pin.dataset.camera);
    if ($("#scene-stage").dataset.scene !== "flight") setView("flight");
  }));

  $("#scene-stage").addEventListener("click", event => {
    if (!measureMode) {
      const stageRect = $("#scene-stage").getBoundingClientRect();
      const x = event.clientX - stageRect.left;
      const y = event.clientY - stageRect.top;
      const xPct = (x / stageRect.width) * 100;
      const yPct = (y / stageRect.height) * 100;
      const nearest = cameraRows.reduce((best, row) => {
        const distance = Math.hypot(row.x - xPct, row.y - yPct);
        return distance < best.distance ? { row, distance } : best;
      }, { row: cameraRows[2], distance: Infinity });
      selectCamera(nearest.row.id);
      if ($("#scene-stage").dataset.scene !== "flight") setView("flight");
      toast("Frame " + nearest.row.id + " · matched SRT position");
      return;
    }
    const rect = $("#scene-stage").getBoundingClientRect();
    measurePoints.push({ x: event.clientX - rect.left, y: event.clientY - rect.top });
    if (measurePoints.length > 2) measurePoints = [measurePoints[measurePoints.length - 1]];
    renderMeasurement();
  });

  $("#inspect-tool").addEventListener("click", () => setMeasureMode(false));
  $("#measure-tool").addEventListener("click", () => setMeasureMode(!measureMode));
  $("#clear-measurement").addEventListener("click", () => setMeasureMode(true));
  $("#camera-toggle").addEventListener("change", event => $("#scene-wrap").classList.toggle("hide-cameras", !event.target.checked));
  $("#path-toggle").addEventListener("change", event => $("#scene-wrap").classList.toggle("hide-path", !event.target.checked));
  $("#zoom-range").addEventListener("input", event => setZoom(event.target.value));
  $("#next-camera").addEventListener("click", () => {
    const index = cameraRows.findIndex(row => row.id === activeCamera);
    selectCamera(cameraRows[(index + 1) % cameraRows.length].id);
  });
  $$(".stage-step").forEach(button => {
    const activate = () => setStage(button.dataset.stage);
    button.addEventListener("pointerup", event => {
      if (event.button === 0) activate();
    });
    button.addEventListener("click", event => {
      if (event.detail === 0) activate();
    });
  });
  $("#run-demo-top").addEventListener("click", openSimulation);
  $("#run-demo-bottom").addEventListener("click", openSimulation);
  $("#close-dialog").addEventListener("click", closeSimulation);
  $("#dialog-finish").addEventListener("click", () => {
    closeSimulation();
    $("#model").scrollIntoView({ behavior: "smooth", block: "center" });
  });
  $("#run-dialog").addEventListener("cancel", stopSimulation);
  $("#run-dialog").addEventListener("close", stopSimulation);
  $("#export-report").addEventListener("click", downloadJson);
  $("#export-measurement").addEventListener("click", downloadMeasurement);
  $$("[data-output]").forEach(button => button.addEventListener("click", () => {
    const output = button.dataset.output;
    if (output === "Point cloud") setView("cloud");
    else if (output === "Orthophoto") setView("ortho");
    else if (output === "Textured surface") setView("cloud");
    else setStage("outputs");
    $("#model").scrollIntoView({ behavior: "smooth", block: "center" });
    toast(output + " · R1 sample output reference");
  }));
  $("#focus-view").addEventListener("click", () => {
    const expanded = $("[data-viewer-shell]");
    expanded.classList.toggle("is-focused");
    const isFocused = expanded.classList.contains("is-focused");
    $("#focus-view").setAttribute("aria-label", isFocused ? "Close expanded model view" : "Expand model view");
    $("#focus-view").title = isFocused ? "Close expanded model view" : "Expand model view";
    $("#focus-view").textContent = isFocused ? "×" : "⤢";
  });
  $("#inspector-menu").addEventListener("click", () => {
    const camera = cameraRows.find(row => row.id === activeCamera);
    const coords = `${camera.lat.toFixed(6)}, ${camera.lon.toFixed(6)}`;
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(coords).then(() => toast("Frame coordinates copied."), () => toast("Frame " + activeCamera + " · " + coords));
    else toast("Frame " + activeCamera + " · " + coords);
  });
  window.addEventListener("keydown", event => {
    if (event.key === "Escape") $("[data-viewer-shell]").classList.remove("is-focused");
  });
  window.addEventListener("resize", () => {
    if (measurePoints.length) renderMeasurement();
  });
}

document.addEventListener("DOMContentLoaded", init);

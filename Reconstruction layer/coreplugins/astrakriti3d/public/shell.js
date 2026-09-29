(function () {
    "use strict";

    var root = document.getElementById("astrakriti-shell");
    var dataNode = document.getElementById("astrakriti-data");
    if (!root || !dataNode) return;

    var data;
    try {
        data = JSON.parse(dataNode.textContent || "{}");
    } catch (error) {
        console.error("Astrakriti data could not be read", error);
        return;
    }

    var page = root.getAttribute("data-page") || data.page || "overview";
    var task = data.task;
    var endpoint = task ? "/api/plugins/astrakriti3d/measurements/task/" + task.id : null;

    function escapeHtml(value) {
        return String(value == null ? "" : value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function formatDate(value) {
        if (!value) return "—";
        var date = new Date(value);
        return isNaN(date.getTime()) ? String(value) : date.toLocaleString();
    }

    function formatBytes(value) {
        if (value == null) return "—";
        var units = ["B", "KB", "MB", "GB", "TB"];
        var number = Number(value);
        var index = 0;
        while (number >= 1024 && index < units.length - 1) {
            number /= 1024;
            index += 1;
        }
        return number.toFixed(index ? 1 : 0) + " " + units[index];
    }

    function status(value) {
        var normalized = String(value || "unknown").toLowerCase();
        return '<span class="status-label status-' + escapeHtml(normalized) + '">' + escapeHtml(normalized) + "</span>";
    }

    function metric(label, value) {
        return '<div class="metric-line-item"><span class="metric-line-label">' + escapeHtml(label) + '</span><span class="metric-line-value">' + escapeHtml(value) + "</span></div>";
    }

    function progressValue(value) {
        if (value == null || value === "") return "—";
        var number = Number(value);
        return isFinite(number) ? Math.round(number * 100) + "%" : "—";
    }

    function section(title, content, meta) {
        return '<section class="ruled-section"><div class="ruled-section-heading"><h2>' + escapeHtml(title) + '</h2><span>' + escapeHtml(meta || "") + "</span></div>" + content + "</section>";
    }

    function taskLink(item) {
        return '<a href="/astrakriti/runs/' + encodeURIComponent(item.id) + '/">' + escapeHtml(item.name) + '</a>';
    }

    function taskRows(tasks) {
        if (!tasks || !tasks.length) {
            return '<div class="empty-state"><h2>No reconstructions recorded</h2><p>WebODM has no visible tasks for this account yet. Start with the native task intake when you have authorized source inputs.</p></div>';
        }
        return '<div style="overflow-x:auto"><table class="astra-table"><thead><tr><th>Run</th><th>Mission</th><th>Status</th><th>Frames</th><th>Created</th></tr></thead><tbody>' + tasks.map(function (item) {
            return '<tr><td>' + taskLink(item) + '<div class="mono">' + escapeHtml(item.id) + '</div></td><td>' + escapeHtml(item.project_name) + '</td><td>' + status(item.status) + '</td><td class="mono">' + escapeHtml(item.images_count) + '</td><td class="mono">' + escapeHtml(formatDate(item.created_at)) + '</td></tr>';
        }).join("") + "</tbody></table></div>";
    }

    function artifactRows(tasks) {
        var rows = [];
        (tasks || []).forEach(function (item) {
            (item.available_assets || []).forEach(function (asset) {
                if (asset.available) {
                    rows.push('<tr><td class="mono">' + escapeHtml(asset.name) + '</td><td>' + taskLink(item) + '</td><td class="mono">' + escapeHtml(formatBytes(asset.size)) + '</td><td><a href="' + escapeHtml(asset.download_url) + '">Download</a></td></tr>');
                }
            });
        });
        if (!rows.length) return '<div class="empty-state"><h2>No available artifacts</h2><p>Only files that exist in the authorized WebODM task storage are listed here.</p></div>';
        return '<div style="overflow-x:auto"><table class="astra-table"><thead><tr><th>Artifact</th><th>Run</th><th>Size</th><th>Action</th></tr></thead><tbody>' + rows.join("") + "</tbody></table></div>";
    }

    function renderOverview(workspace) {
        var active = data.active_task;
        var tasks = data.tasks || [];
        var projectCount = (data.projects || []).length;
        var activeBlock = active ? '<div class="metric-line">' + metric("Mission", active.project_name) + metric("Run", active.name) + metric("Stage", active.status_label) + metric("Progress", progressValue(active.progress)) + '</div><p class="state-copy">The current state is read from the WebODM Task record. Open the run to inspect native viewers, logs, outputs, and recovery actions.</p><p><a class="button button-secondary" href="/astrakriti/runs/' + encodeURIComponent(active.id) + '/">Open active run</a></p>' : '<div class="empty-state"><h2>' + (projectCount ? 'No active reconstruction' : 'First use: connect a real reconstruction') + '</h2><p>' + (projectCount ? 'Completed, failed, and cancelled WebODM tasks remain available below. Start a new task only through the native WebODM intake.' : 'Create a WebODM Project and submit authorized source images to begin. No sample names, outputs, or progress are shown here.') + '</p><p><a class="button button-primary" href="/astrakriti/new-reconstruction/">New reconstruction</a></p></div>';
        workspace.innerHTML = section("Active reconstruction", activeBlock, active ? "LIVE TASK STATE" : "IDLE") + section("Recent reconstructions", taskRows(tasks.slice(0, 12)), String(tasks.length) + " visible tasks") + section("Latest artifacts", artifactRows(tasks.slice(0, 12)), "FILES ON DISK ONLY");
    }

    function renderMissions(workspace) {
        var projects = data.projects || [];
        var params = new URLSearchParams(window.location.search);
        var initialQuery = params.get("q") || "";
        var initialSort = params.get("sort") || "created_desc";
        workspace.innerHTML = section("Missions", '<div class="list-tools"><label>Search missions<input id="astrakriti-mission-search" type="search" value="' + escapeHtml(initialQuery) + '" placeholder="Project name or description"></label><label>Sort<select id="astrakriti-mission-sort"><option value="created_desc">Newest first</option><option value="name_asc">Name A–Z</option><option value="runs_desc">Most runs</option></select></label></div><div id="astrakriti-mission-results"></div>', String(projects.length) + " visible");
        var search = document.getElementById("astrakriti-mission-search");
        var sort = document.getElementById("astrakriti-mission-sort");
        var results = document.getElementById("astrakriti-mission-results");
        sort.value = ["created_desc", "name_asc", "runs_desc"].indexOf(initialSort) >= 0 ? initialSort : "created_desc";

        function syncUrl() {
            var next = new URLSearchParams();
            if (search.value.trim()) next.set("q", search.value.trim());
            if (sort.value !== "created_desc") next.set("sort", sort.value);
            var query = next.toString();
            window.history.replaceState(null, "", window.location.pathname + (query ? "?" + query : ""));
        }

        function draw() {
            var query = search.value.trim().toLowerCase();
            var filtered = projects.filter(function (project) { return !query || (String(project.name || "") + " " + String(project.description || "")).toLowerCase().indexOf(query) >= 0; });
            filtered.sort(function (left, right) {
                if (sort.value === "name_asc") return String(left.name || "").localeCompare(String(right.name || ""));
                if (sort.value === "runs_desc") return Number(right.task_count || 0) - Number(left.task_count || 0);
                return new Date(right.created_at || 0).getTime() - new Date(left.created_at || 0).getTime();
            });
            if (!filtered.length) {
                results.innerHTML = query ? '<div class="empty-state"><h2>No Missions match</h2><p>Try a different search term. The result is based on authorized WebODM Project data.</p></div>' : '<div class="empty-state"><h2>No Missions visible</h2><p>Projects are the authoritative WebODM mission grouping. Create one through WebODM before submitting a reconstruction.</p><p><a class="button button-primary" href="/astrakriti/new-reconstruction/">New reconstruction</a></p></div>';
                return;
            }
            results.innerHTML = '<div style="overflow-x:auto"><table class="astra-table"><thead><tr><th>Mission / Project</th><th>Runs</th><th>Latest run</th><th>Created</th></tr></thead><tbody>' + filtered.map(function (project) {
                var latest = project.tasks && project.tasks[0];
                return '<tr><td><a href="/astrakriti/missions/' + encodeURIComponent(project.id) + '/">' + escapeHtml(project.name) + '</a><div>' + escapeHtml(project.description || "") + '</div></td><td class="mono">' + escapeHtml(project.task_count) + '</td><td>' + (latest ? taskLink(latest) + " " + status(latest.status) : "—") + '</td><td class="mono">' + escapeHtml(formatDate(project.created_at)) + '</td></tr>';
            }).join("") + '</tbody></table></div>';
        }
        search.addEventListener("input", function () { syncUrl(); draw(); });
        sort.addEventListener("change", function () { syncUrl(); draw(); });
        draw();
    }

    function renderMission(workspace) {
        var project = data.project;
        if (!project) {
            workspace.innerHTML = '<div class="error-state"><h2>Mission unavailable</h2><p>The requested Project is missing or you do not have permission to view it.</p></div>';
            return;
        }
        var metadata = project.mission_metadata || {};
        var legacy = project.legacy_mission_mappings || [];
        var legacyCopy = legacy.length ? legacy.map(function (item) { return '<li>' + escapeHtml(item.legacy_label || item.legacy_id) + ' — ' + escapeHtml(item.mapping_state) + '</li>'; }).join("") : '<li>No linked legacy Mission identity recorded.</li>';
        var canEdit = Boolean(project.permissions && project.permissions.change);
        var provenance = metadata.provenance && Object.keys(metadata.provenance).length ? JSON.stringify(metadata.provenance) : "Not recorded";
        workspace.innerHTML = '<div class="metric-line">' + metric("Mission", project.name) + metric("Runs", project.task_count) + metric("Created", formatDate(project.created_at)) + '</div>' +
            section("Mission context", '<p class="state-copy">The WebODM Project remains authoritative for Mission name and description. Location and capture context are Astrakriti metadata.</p><p><strong>Project description:</strong> ' + escapeHtml(project.description || "Not recorded") + '</p><form id="astrakriti-mission-metadata" class="astrakriti-form"><div class="form-grid"><label>Location<input name="location" maxlength="255" value="' + escapeHtml(metadata.location || "") + '"' + (canEdit ? "" : " disabled") + '></label><label class="file-field">Capture context<textarea name="capture_context" rows="4"' + (canEdit ? "" : " disabled") + '>' + escapeHtml(metadata.capture_context || "") + '</textarea></label></div><div class="form-actions">' + (canEdit ? '<button class="button button-secondary" type="submit">Save Mission context</button>' : '') + '<span class="state-copy" id="astrakriti-mission-save-status" aria-live="polite">' + (metadata.recorded ? "Metadata recorded" : "Context not recorded") + '</span></div></form><p class="state-copy">Provenance: <span class="mono">' + escapeHtml(provenance) + '</span></p><ul class="state-copy">' + legacyCopy + '</ul>', metadata.recorded ? "ASTRAKRITI METADATA" : "NOT YET RECORDED") +
            section("Run history", taskRows(project.tasks), "WEBODM TASKS") + section("Actions", '<p class="state-copy">New runs are created by WebODM. The Astrakriti shell keeps the Project/Task context for viewers and evidence.</p><p><a class="button button-primary" href="/dashboard/">Open native task intake</a></p>', "NATIVE FLOW");
        var form = document.getElementById("astrakriti-mission-metadata");
        if (form && canEdit) form.addEventListener("submit", function (event) {
            event.preventDefault();
            var button = form.querySelector('button[type="submit"]');
            var message = document.getElementById("astrakriti-mission-save-status");
            button.disabled = true;
            message.textContent = "Saving…";
            fetch("/api/plugins/astrakriti3d/mission/" + encodeURIComponent(project.id) + "/metadata/", {
                method: "PATCH", credentials: "same-origin",
                headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken(), Accept: "application/json" },
                body: JSON.stringify({ location: form.elements.location.value, capture_context: form.elements.capture_context.value })
            }).then(readJsonOrError).then(function (saved) {
                project.mission_metadata = saved;
                message.textContent = "Saved";
            }).catch(function () {
                message.textContent = "Save failed. Check Project change permission and retry.";
            }).finally(function () { button.disabled = false; });
        });
    }

    function renderRun(workspace) {
        if (!task) {
            workspace.innerHTML = '<div class="error-state"><h2>Run unavailable</h2><p>The requested WebODM Task is missing or you do not have permission to view it.</p></div>';
            return;
        }
        var actions = '<p><a class="button button-secondary" href="' + task.viewer_urls.map + '">Open Map</a> <a class="button button-secondary" href="' + task.viewer_urls.model + '">Open 3D Model</a> <a class="button button-secondary" href="' + task.native_urls.output + '">Open logs</a></p>' + taskActions(task);
        var error = task.last_error ? '<div class="error-state"><h2>WebODM reported a task error</h2><p>' + escapeHtml(task.last_error) + '</p><p class="state-copy">Existing inputs and outputs are preserved according to native WebODM task semantics. Use native task actions when retry or cancellation is supported.</p></div>' : '';
        workspace.innerHTML = '<div class="metric-line">' + metric("Mission", task.project_name) + metric("Run", task.name) + metric("State", task.status_label) + metric("Frames", task.images_count) + metric("Created", formatDate(task.created_at)) + '</div>' + error + section("Lifecycle", '<p class="state-copy">' + status(task.status) + ' <span class="mono">' + escapeHtml(task.id) + '</span></p>' + actions, "NATIVE TASK STATE") + section("Available outputs", artifactRows([task]), String((task.available_assets || []).filter(function (item) { return item.available; }).length) + " files");
        bindTaskActions(workspace);
    }

    function formatVideoTime(value) {
        if (value == null || value === "") return "—";
        var seconds = Number(value);
        if (!isFinite(seconds) || seconds < 0) return "—";
        var milliseconds = Math.round(seconds * 1000);
        var hours = Math.floor(milliseconds / 3600000);
        milliseconds -= hours * 3600000;
        var minutes = Math.floor(milliseconds / 60000);
        milliseconds -= minutes * 60000;
        var wholeSeconds = Math.floor(milliseconds / 1000);
        var fraction = milliseconds - wholeSeconds * 1000;
        function pad(number, width) { return String(number).padStart(width, "0"); }
        return pad(hours, 2) + ":" + pad(minutes, 2) + ":" + pad(wholeSeconds, 2) + "." + pad(fraction, 3);
    }

    function reviewRequest(view, state) {
        var query = new URLSearchParams();
        query.set("view", view);
        query.set("offset", String(state.offset));
        query.set("limit", String(state.limit));
        if (state.query) query.set("q", state.query);
        if (state.association && state.association !== "all") query.set("association", state.association);
        return fetch("/api/plugins/astrakriti3d/preparation/task/" + encodeURIComponent(task.id) + "/?" + query.toString(), {
            credentials: "same-origin",
            headers: { Accept: "application/json" }
        }).then(readJsonOrError);
    }

    function reviewControls(view, query, association, associationOptions, total, offset, count) {
        var filterLabel = view === "frames" ? "Filter frames" : "Filter telemetry records";
        var associationControl = associationOptions ? '<label>Association<select data-review-association>' + associationOptions.map(function (option) {
            return '<option value="' + escapeHtml(option.value) + '"' + (association === option.value ? " selected" : "") + '>' + escapeHtml(option.label) + '</option>';
        }).join("") + '</select></label>' : "";
        var first = count ? offset + 1 : 0;
        var last = count ? Math.min(offset + count, total) : 0;
        return '<div class="review-controls"><label>' + escapeHtml(filterLabel) + '<input type="search" data-review-query value="' + escapeHtml(query) + '" autocomplete="off" placeholder="Search real task data"></label>' + associationControl + '<span class="review-count mono" aria-live="polite">' + escapeHtml(first + "–" + last + " of " + total) + '</span></div>';
    }

    function bindReviewFilters(workspace, state, view, reload) {
        var queryInput = workspace.querySelector("[data-review-query]");
        var association = workspace.querySelector("[data-review-association]");
        if (queryInput) queryInput.addEventListener("input", function () {
            state.query = queryInput.value.trim();
            state.offset = 0;
            window.clearTimeout(state.debounce);
            state.debounce = window.setTimeout(reload, 220);
        });
        if (association) association.addEventListener("change", function () {
            state.association = association.value;
            state.offset = 0;
            reload();
        });
    }

    function fallbackFramePage() {
        var frames = task && task.frames ? task.frames : [];
        return {
            status: frames.length ? "partial" : "unavailable",
            detail: frames.length ? "Only the source images exposed by WebODM are available; original timestamps, GPS association, and quality scoring were not imported." : "No readable source images are available for this Task.",
            total: frames.length,
            offset: 0,
            limit: frames.length || 48,
            items: frames.map(function (frame) {
                return {
                    filename: frame.name,
                    timestamp_seconds: null,
                    dimensions: null,
                    sha256: null,
                    metadata_status: "partial",
                    quality_status: "not_measured",
                    telemetry: { status: "unknown" },
                    preview_available: true,
                    thumbnail_url: frame.thumbnail_url,
                    download_url: frame.download_url
                };
            })
        };
    }

    function renderFrameReview(workspace) {
        var state = { offset: 0, limit: 48, query: "", association: "all", selected: 0, payload: null, request: 0, debounce: null };
        var associationOptions = [
            { value: "all", label: "All frames" },
            { value: "matched", label: "Telemetry matched" },
            { value: "unmatched", label: "Telemetry unmatched" }
        ];

        function draw() {
            var payload = state.payload || {};
            var items = payload.items || [];
            var total = Number(payload.total || 0);
            if (!items.length) {
                var empty = payload.status === "error" ? '<div class="error-state"><h2>Frame review unavailable</h2><p>' + escapeHtml(payload.detail || "The frame evidence could not be read.") + '</p><button class="button button-secondary" type="button" data-review-retry>Retry</button></div>' : '<div class="empty-state"><h2>No source frames available</h2><p>' + escapeHtml(payload.detail || "No readable source images or imported frame manifest are available for this Task.") + '</p></div>';
                workspace.innerHTML = section("Frame review", reviewControls("frames", state.query, state.association, payload.mode === "unknown" ? null : associationOptions, total, state.offset, 0) + empty, payload.status === "error" ? "ERROR" : "EMPTY");
                bindReviewFilters(workspace, state, "frames", load);
                var retryEmpty = workspace.querySelector("[data-review-retry]");
                if (retryEmpty) retryEmpty.addEventListener("click", load);
                return;
            }

            state.selected = Math.max(0, Math.min(state.selected, items.length - 1));
            var frame = items[state.selected];
            var dimensions = frame.dimensions ? frame.dimensions.width + " × " + frame.dimensions.height + " px" : "NOT AVAILABLE";
            var telemetry = frame.telemetry || {};
            var associationText = telemetry.status === "matched" ? "Matched · " + coordinateText(telemetry.latitude, telemetry.longitude) : telemetry.status === "unmatched" ? "No frame match" : telemetry.status === "not_used" ? "Not used in local mode" : "UNKNOWN";
            var altitude = telemetry.altitude == null ? "—" : String(telemetry.altitude) + " (units and vertical datum unknown)";
            var preview = frame.preview_available && frame.thumbnail_url ? '<img data-frame-preview src="' + escapeHtml(frame.thumbnail_url) + '" alt="Source frame ' + escapeHtml(frame.filename) + '"><figcaption class="mono">' + escapeHtml(frame.filename) + '</figcaption>' : '<div class="frame-preview-unavailable" role="status"><strong>PREVIEW UNAVAILABLE</strong><span>The source image is missing or its preview could not be loaded.</span></div>';
            var hash = frame.sha256 ? '<span class="mono" title="' + escapeHtml(frame.sha256) + '">' + escapeHtml(frame.sha256.slice(0, 16)) + '…</span>' : "NOT AVAILABLE";
            var quality = frame.quality_metrics || {};
            var qualitySummary = Object.keys(quality).length ? Object.keys(quality).map(function (key) { return key.replace(/_/g, " ") + ": " + (typeof quality[key] === "number" ? Number(quality[key]).toFixed(2) : quality[key]); }).join(" · ") : "No measured selector metrics are available.";
            if (frame.quality_warning) qualitySummary += " — " + frame.quality_warning;
            var selectionSummary = frame.selection_recommendation ? "R2 advisory: " + frame.selection_recommendation + (frame.selection_reason ? " — " + frame.selection_reason.replace(/_/g, " ") : "") : "R2 advisory unavailable";
            var coverageSummary = frame.coverage_recommendation ? "Coverage advisory: " + frame.coverage_recommendation + (frame.coverage_reason ? " — " + frame.coverage_reason.replace(/_/g, " ") : "") : "Coverage advisory unavailable for this frame";
            var details = '<h2>' + escapeHtml(frame.filename) + '</h2><dl class="review-details">' +
                '<div><dt>Video time</dt><dd class="mono">' + escapeHtml(formatVideoTime(frame.timestamp_seconds)) + '</dd></div>' +
                '<div><dt>Source frame index</dt><dd class="mono">' + escapeHtml(frame.source_frame_index == null ? "NOT AVAILABLE" : frame.source_frame_index) + '</dd></div>' +
                '<div><dt>Resolution</dt><dd class="mono">' + escapeHtml(dimensions) + '</dd></div>' +
                '<div><dt>GPS association</dt><dd>' + escapeHtml(associationText) + '</dd></div>' +
                '<div><dt>Altitude</dt><dd class="mono">' + escapeHtml(altitude) + '</dd></div>' +
                '<div><dt>Selection quality</dt><dd>' + escapeHtml(String(frame.quality_status || "not_measured").replace(/_/g, " ").toUpperCase()) + '</dd></div>' +
                '<div><dt>Measured proxies</dt><dd>' + escapeHtml(qualitySummary) + '</dd></div>' +
                '<div><dt>R2 recommendation</dt><dd>' + escapeHtml(selectionSummary) + '</dd></div>' +
                '<div><dt>Coverage recommendation</dt><dd>' + escapeHtml(coverageSummary) + '</dd></div>' +
                '<div><dt>Frame hash</dt><dd>' + hash + '</dd></div>' +
                '</dl><p class="state-copy">Recommendations are experimental diagnostics only. R1 remains the production baseline and all source frames remain included; no quality or reconstruction-accuracy guarantee is implied.</p>' +
                (frame.download_url ? '<p><a class="button button-secondary" href="' + escapeHtml(frame.download_url) + '">Download source frame</a></p>' : "");
            var strip = '<ol class="frame-strip" aria-label="Source frame filmstrip">' + items.map(function (item, index) {
                var image = item.preview_available && item.thumbnail_url ? '<img loading="lazy" src="' + escapeHtml(item.thumbnail_url) + '" alt="">' : '<span class="frame-thumb-placeholder" aria-hidden="true">NO PREVIEW</span>';
                var current = index === state.selected;
                return '<li><button type="button" class="frame-thumb' + (current ? ' is-selected' : '') + '" data-frame-index="' + index + '" aria-pressed="' + (current ? 'true' : 'false') + '">' + image + '<span class="mono">' + escapeHtml(item.filename) + '</span><small>' + escapeHtml(item.timestamp_seconds == null ? "TIME UNKNOWN" : formatVideoTime(item.timestamp_seconds)) + '</small></button></li>';
            }).join("") + '</ol>';
            var previousPage = state.offset > 0;
            var nextPage = state.offset + items.length < total;
            var pager = '<div class="review-pager"><button class="button button-secondary" type="button" data-frame-page="previous"' + (previousPage ? "" : " disabled") + '>Previous page</button><span class="mono">' + escapeHtml(items.length ? (state.offset + 1) + "–" + Math.min(state.offset + items.length, total) : 0) + ' / ' + escapeHtml(total) + '</span><button class="button button-secondary" type="button" data-frame-page="next"' + (nextPage ? "" : " disabled") + '>Next page</button></div>';
            var partialNote = payload.status === "partial" ? '<p class="state-copy" role="status">' + escapeHtml(payload.detail || "Some source metadata is unavailable; no values have been inferred.") + '</p>' : "";
            var selection = payload.selection || {};
            var sourceFrameCount = payload.frame_count == null ? total : payload.frame_count;
            var selectionNote = '<p class="state-copy" role="status">R1 production baseline: all ' + escapeHtml(sourceFrameCount) + ' imported source frames are retained. Experimental diagnostics: ' + escapeHtml(String(selection.status || "unavailable").replace(/_/g, " ")) + '. Recommendations do not alter the WebODM input set.</p>';
            workspace.innerHTML = section("Frame review", reviewControls("frames", state.query, state.association, payload.mode === "unknown" ? null : associationOptions, total, state.offset, items.length) + selectionNote + partialNote + '<div class="frame-review-layout"><nav class="frame-filmstrip" aria-label="Frame navigation">' + strip + pager + '</nav><div class="frame-inspection"><figure class="frame-preview">' + preview + '</figure><section class="frame-metadata" aria-label="Selected frame metadata">' + details + '<div class="frame-step-controls"><button class="button button-secondary" type="button" data-frame-step="previous"' + (state.selected > 0 ? "" : " disabled") + ' aria-label="Previous frame">Previous frame</button><button class="button button-secondary" type="button" data-frame-step="next"' + (state.selected < items.length - 1 ? "" : " disabled") + ' aria-label="Next frame">Next frame</button></div></section></div></div>', payload.status === "available" ? "PREPARED INPUT" : "PARTIAL METADATA");
            bindReviewFilters(workspace, state, "frames", function () { state.selected = 0; load(); });
            workspace.querySelectorAll("[data-frame-index]").forEach(function (button) {
                button.addEventListener("click", function () { state.selected = Number(button.getAttribute("data-frame-index")); draw(); var next = workspace.querySelector('[data-frame-index="' + state.selected + '"]'); if (next) next.focus(); });
            });
            workspace.querySelectorAll("[data-frame-step]").forEach(function (button) {
                button.addEventListener("click", function () { state.selected += button.getAttribute("data-frame-step") === "next" ? 1 : -1; draw(); var next = workspace.querySelector('[data-frame-index="' + state.selected + '"]'); if (next) next.focus(); });
            });
            workspace.querySelectorAll("[data-frame-page]").forEach(function (button) {
                button.addEventListener("click", function () { state.offset = Math.max(0, state.offset + (button.getAttribute("data-frame-page") === "next" ? state.limit : -state.limit)); state.selected = 0; load(); });
            });
            var selectedImage = workspace.querySelector("[data-frame-preview]");
            if (selectedImage) selectedImage.addEventListener("error", function () {
                state.payload.items[state.selected].preview_available = false;
                draw();
            }, { once: true });
        }

        function load() {
            var generation = ++state.request;
            workspace.innerHTML = section("Frame review", '<p class="review-loading" role="status">Loading authorized frame and preparation metadata…</p>', "LOADING");
            reviewRequest("frames", state).then(function (payload) {
                if (generation !== state.request) return;
                if (payload.status === "unavailable") payload = fallbackFramePage();
                state.payload = payload;
                state.selected = 0;
                draw();
            }).catch(function (error) {
                if (generation !== state.request) return;
                state.payload = { status: "error", detail: error.message || "Frame evidence could not be loaded. Existing Task inputs remain unchanged.", total: 0, items: [] };
                draw();
            });
        }
        load();
    }

    function coordinateText(latitude, longitude) {
        if (latitude == null || longitude == null || !isFinite(Number(latitude)) || !isFinite(Number(longitude))) return "coordinates unavailable";
        return Number(latitude).toFixed(6) + ", " + Number(longitude).toFixed(6);
    }

    function fallbackTelemetryPage() {
        var media = (task && task.media ? task.media : []).filter(function (item) { return item && item.geolocation; });
        return {
            status: media.length ? "partial" : "unavailable",
            detail: media.length ? "Only WebODM media geolocation is available. Parsed SRT records, timestamps, and frame associations were not imported for this Task." : "No imported telemetry manifest or WebODM media geolocation is available for this Task.",
            mode: null,
            summary: { record_count: null, valid_record_count: null, invalid_record_count: null, parser_error_count: null, matched_frame_count: null, unmatched_frame_count: null, warnings: [], errors: [], unknowns: [] },
            total: media.length,
            offset: 0,
            limit: 100,
            items: media.map(function (item) {
                return { record_id: item.filename || item.type || "Media geolocation", timestamp_seconds: null, wall_clock_time: null, latitude: null, longitude: null, altitude: null, speed: null, associated_frames: [], legacy_location: item.geolocation, diagnostics: [] };
            })
        };
    }

    function renderTelemetryReview(workspace) {
        var state = { offset: 0, limit: 100, query: "", association: "all", payload: null, request: 0, debounce: null };
        var associationOptions = [
            { value: "all", label: "All records" },
            { value: "associated", label: "Associated with a frame" },
            { value: "unassociated", label: "No selected-frame association" }
        ];

        function draw() {
            var payload = state.payload || {};
            var summary = payload.summary || {};
            var items = payload.items || [];
            var total = Number(payload.total || 0);
            if (payload.status === "not_applicable") {
                workspace.innerHTML = section("Telemetry review", '<div class="empty-state"><h2>Telemetry not used</h2><p>This Run was prepared in local/unreferenced mode. No telemetry records or geographic camera positions are claimed.</p></div>', "NOT APPLICABLE");
                return;
            }
            if (!items.length) {
                var empty = payload.status === "error" ? '<div class="error-state"><h2>Telemetry review unavailable</h2><p>' + escapeHtml(payload.detail || "The telemetry evidence could not be read.") + '</p><button class="button button-secondary" type="button" data-review-retry>Retry</button></div>' : '<div class="empty-state"><h2>Telemetry unavailable</h2><p>' + escapeHtml(payload.detail || "No parsed telemetry records are linked to this Task.") + '</p></div>';
                workspace.innerHTML = section("Telemetry review", empty, payload.status === "error" ? "ERROR" : "UNAVAILABLE");
                var retry = workspace.querySelector("[data-review-retry]");
                if (retry) retry.addEventListener("click", load);
                return;
            }
            var metrics = '<div class="metric-line">' + metric("Parsed records", summary.record_count == null ? "NOT AVAILABLE" : summary.record_count) + metric("Invalid records", summary.invalid_record_count == null ? "NOT AVAILABLE" : summary.invalid_record_count) + metric("Ignored blocks", summary.ignored_block_count == null ? "NOT AVAILABLE" : summary.ignored_block_count) + metric("Matched frames", summary.matched_frame_count == null ? "NOT AVAILABLE" : summary.matched_frame_count) + metric("Unmatched frames", summary.unmatched_frame_count == null ? "NOT AVAILABLE" : summary.unmatched_frame_count) + '</div>';
            var range = summary.timestamp_range_seconds && summary.timestamp_range_seconds.length === 2 ? '<p class="telemetry-range"><span>Video-relative record range</span><strong class="mono">' + escapeHtml(formatVideoTime(summary.timestamp_range_seconds[0]) + " → " + formatVideoTime(summary.timestamp_range_seconds[1])) + '</strong></p>' : "";
            var notices = [];
            (summary.warnings || []).forEach(function (item) { notices.push('<li>' + escapeHtml(item) + '</li>'); });
            (summary.errors || []).forEach(function (item) { notices.push('<li class="is-error">' + escapeHtml(item) + '</li>'); });
            (summary.unknowns || []).forEach(function (item) { notices.push('<li>UNKNOWN — ' + escapeHtml(item) + '</li>'); });
            var warningBlock = notices.length ? '<div class="telemetry-warnings"><h3>Parser warnings and limitations</h3><ul>' + notices.join("") + '</ul></div>' : "";
            var rows = items.map(function (record, index) {
                var time = record.wall_clock_time || (record.timestamp_seconds == null ? "—" : formatVideoTime(record.timestamp_seconds));
                var associated = record.associated_frames && record.associated_frames.length ? record.associated_frames.join(", ") : "No selected-frame association";
                var diagnostics = record.diagnostics && record.diagnostics.length ? record.diagnostics.join("; ") : record.valid === false ? "Invalid record" : record.legacy_location ? "WebODM media GPS only" : "OK";
                var location = record.legacy_location ? JSON.stringify(record.legacy_location) : "";
                return '<tr><td class="mono">' + escapeHtml(record.record_id || (state.offset + index + 1)) + '</td><td class="mono">' + escapeHtml(time) + '</td><td class="mono">' + escapeHtml(record.latitude == null ? "—" : record.latitude) + '</td><td class="mono">' + escapeHtml(record.longitude == null ? "—" : record.longitude) + '</td><td class="mono">' + escapeHtml(record.altitude == null ? "— (units unknown)" : record.altitude + " (units/datum unknown)") + '</td><td class="mono">' + escapeHtml(record.speed == null ? "—" : record.speed + " (units unknown)") + '</td><td class="mono">' + escapeHtml(associated) + (location ? '<small class="review-subvalue">' + escapeHtml(location) + '</small>' : '') + '</td><td>' + escapeHtml(diagnostics) + '</td></tr>';
            }).join("");
            var table = '<div class="review-table-wrap"><table class="astra-table"><thead><tr><th>Record</th><th>Source time</th><th>Latitude</th><th>Longitude</th><th>Altitude</th><th>Speed</th><th>Frame association</th><th>Parser status</th></tr></thead><tbody>' + rows + '</tbody></table></div>';
            var previous = state.offset > 0;
            var next = state.offset + items.length < total;
            var pager = '<div class="review-pager"><button class="button button-secondary" type="button" data-telemetry-page="previous"' + (previous ? "" : " disabled") + '>Previous page</button><span class="mono">' + escapeHtml((state.offset + 1) + "–" + Math.min(state.offset + items.length, total) + " / " + total) + '</span><button class="button button-secondary" type="button" data-telemetry-page="next"' + (next ? "" : " disabled") + '>Next page</button></div>';
            var coordinateAction = payload.coordinate_reference === "EPSG:4326" ? '<p><a class="button button-secondary" href="' + escapeHtml(task.viewer_urls.map) + '">Open native Map workspace</a></p>' : "";
            var partialNote = payload.status === "partial" ? '<p class="state-copy" role="status">' + escapeHtml(payload.detail || "Only partial telemetry metadata is available; missing values are not inferred.") + '</p>' : "";
            workspace.innerHTML = section("Telemetry review", metrics + range + warningBlock + reviewControls("telemetry", state.query, state.association, payload.status === "available" ? associationOptions : null, total, state.offset, items.length) + partialNote + table + pager + coordinateAction, payload.status === "available" ? String(total) + " PARSED RECORDS" : "PARTIAL DATA");
            bindReviewFilters(workspace, state, "telemetry", function () { load(); });
            workspace.querySelectorAll("[data-telemetry-page]").forEach(function (button) {
                button.addEventListener("click", function () { state.offset = Math.max(0, state.offset + (button.getAttribute("data-telemetry-page") === "next" ? state.limit : -state.limit)); load(); });
            });
        }

        function load() {
            var generation = ++state.request;
            workspace.innerHTML = section("Telemetry review", '<p class="review-loading" role="status">Loading authenticated telemetry and frame associations…</p>', "LOADING");
            reviewRequest("telemetry", state).then(function (payload) {
                if (generation !== state.request) return;
                if (payload.status === "unavailable") payload = fallbackTelemetryPage();
                state.payload = payload;
                draw();
            }).catch(function (error) {
                if (generation !== state.request) return;
                state.payload = { status: "error", detail: error.message || "Telemetry evidence could not be loaded. Existing Task data remains unchanged.", total: 0, items: [] };
                draw();
            });
        }
        load();
    }

    function renderGeneric(workspace) {
        if (page === "artifacts" || page === "reports" || page === "reconstructions" || page === "files") {
            var artifactTasks = page === "reports" || page === "files" ? (task ? [task] : data.tasks || []) : data.tasks || [];
            var reportExport = page === "reports" && task ? '<p class="state-copy">Saved task measurements: <a href="' + endpoint + '/export/?format=geojson">GeoJSON</a> · <a href="' + endpoint + '/export/">coordinate-preserving JSON</a></p>' : '';
            workspace.innerHTML = page === "reconstructions" ? section("Reconstructions", taskRows(data.tasks || []), "WEBODM TASKS") : section(page === "reports" ? "Reports and exports" : page === "files" ? "Task files" : "Artifacts", artifactRows(artifactTasks) + reportExport, task ? "TASK-SCOPED FILES" : "AUTHORIZED FILES");
            return;
        }
        if (page === "runs") {
            var project = data.project;
            workspace.innerHTML = project ? section("Mission runs", taskRows(project.tasks || []), "WEBODM TASKS") : '<div class="error-state"><h2>Mission unavailable</h2><p>The requested Project is missing or you do not have permission to view it.</p></div>';
            return;
        }
        if (page === "system" || page === "settings") {
            renderHealth(workspace);
            return;
        }
        if (page === "new-reconstruction") {
            renderNewReconstruction(workspace);
            return;
        }
        if (page === "processing" && !task) {
            var visibleTasks = data.tasks || [];
            workspace.innerHTML = section("Processing / recovery", taskRows(visibleTasks), "WEBODM TASKS") + '<p class="state-copy">Open a Task to inspect authoritative progress, logs, cancellation, restart, and recovery actions. No parallel lifecycle state is maintained here.</p>';
            return;
        }
        if (!task) {
            workspace.innerHTML = '<div class="notice-state"><h2>Run context required</h2><p>This workspace is available from a Run after a real WebODM Task exists.</p><p><a class="button button-secondary" href="/astrakriti/reconstructions/">Browse reconstructions</a></p></div>';
            return;
        }
        if (page === "validation") {
            var availableCount = (task.available_assets || []).filter(function (item) { return item.available; }).length;
            var srsName = task.srs && task.srs.name ? task.srs.name : "unknown CRS";
            workspace.innerHTML = section("Validation / evidence", '<div class="metric-line">' + metric("Artifact revision", task.artifact_revision) + metric("Available outputs", availableCount) + metric("CRS", srsName) + '</div><div class="health-grid"><div class="health-block"><h3>Accuracy</h3><p>NOT VERIFIED — WebODM task completion does not establish independent survey accuracy.</p></div><div class="health-block"><h3>Scale</h3><p>NOT VERIFIED — inspect the task CRS, units, and independent control evidence.</p></div><div class="health-block"><h3>Completeness</h3><p>PARTIAL FACT — ' + escapeHtml(availableCount) + ' output files are present; availability is not a completeness claim.</p></div></div><p class="state-copy">The revision is derived from the Task status, CRS, and real output file stat records. It is provenance for this workspace, not an artifact content hash.</p>', "FACTUAL STATES");
        } else if (page === "frames") {
            renderFrameReview(workspace);
        } else if (page === "telemetry") {
            renderTelemetryReview(workspace);
        } else if (page === "measurements") {
            workspace.innerHTML = section("Measurements", '<p class="state-copy">Open the Map or 3D Model workspace to draw native measurements. Saved map measurements are stored against this Task; Potree scene data remains native WebODM state.</p><p><a class="button button-secondary" href="' + task.viewer_urls.map + '">Open Map</a> <a class="button button-secondary" href="' + task.viewer_urls.model + '">Open 3D Model</a></p><div id="astrakriti-measurement-list" class="measurement-list"><p class="state-copy">Loading saved measurements…</p></div>', "TASK-SCOPED");
        } else if (page === "processing") {
            workspace.innerHTML = section("Processing / recovery", '<div class="metric-line">' + metric("Task status", task.status_label) + metric("Progress", progressValue(task.progress)) + metric("Last error", task.last_error || "—") + '</div><p class="state-copy">Cancellation, restart, logs, and recovery are native WebODM task actions. This shell reports the authoritative task state and does not create a parallel lifecycle.</p>' + taskActions(task) + '<p><a class="button button-secondary" href="/map/project/' + encodeURIComponent(task.project_id) + '/task/' + encodeURIComponent(task.id) + '/">Open native Map route</a></p>', "AUTHORITATIVE WEBODM STATE");
            bindTaskActions(workspace);
        } else {
            workspace.innerHTML = '<div class="notice-state"><h2>' + escapeHtml(data.page_label || page) + '</h2><p>UNAVAILABLE — this workspace has no configured Astrakriti companion data for the selected WebODM Task.</p></div>';
        }
    }

    function taskActions(item) {
        var permissions = item.permissions || {};
        if (!permissions.change) return '<p class="state-copy">This account has view access only; native task mutations are unavailable.</p>';
        var buttons = [];
        if (item.status === "queued" || item.status === "processing") {
            buttons.push('<button class="button button-secondary" type="button" data-task-action="cancel" data-action-url="' + escapeHtml(item.native_urls.cancel) + '">Cancel task</button>');
        }
        if (item.status === "failed" || item.status === "cancelled") {
            buttons.push('<button class="button button-secondary" type="button" data-task-action="restart" data-action-url="' + escapeHtml(item.native_urls.restart) + '">Restart task</button>');
        }
        return buttons.length ? '<p class="astrakriti-task-actions">' + buttons.join(" ") + ' <span class="state-copy" data-task-action-status aria-live="polite"></span></p>' : '<p class="state-copy">No native recovery action is available for this Task state.</p>';
    }

    function bindTaskActions(scope) {
        scope.querySelectorAll("button[data-task-action]").forEach(function (button) {
            button.addEventListener("click", function () {
                var action = button.getAttribute("data-task-action");
                if (!window.confirm((action === "cancel" ? "Cancel" : "Restart") + " this WebODM Task?")) return;
                button.disabled = true;
                var statusNode = scope.querySelector("[data-task-action-status]");
                if (statusNode) statusNode.textContent = "Submitting native action…";
                fetch(button.getAttribute("data-action-url"), { method: "POST", credentials: "same-origin", headers: { "X-CSRFToken": csrfToken(), Accept: "application/json" } }).then(function (response) {
                    if (!response.ok) return response.json().catch(function () { return {}; }).then(function (body) { throw new Error(body.detail || body.error || "Native task action failed"); });
                    if (statusNode) statusNode.textContent = "Accepted. Refreshing task state…";
                    window.setTimeout(function () { window.location.reload(); }, 500);
                }).catch(function (error) {
                    button.disabled = false;
                    if (statusNode) statusNode.textContent = error.message || "Action failed; retry is safe.";
                });
            });
        });
    }

    function renderNewReconstruction(workspace) {
        var projects = data.projects || [];
        var options = projects.map(function (project) {
            var writable = project.permissions && project.permissions.change;
            return '<option value="' + escapeHtml(project.id) + '"' + (writable ? "" : " disabled") + '>' + escapeHtml(project.name) + (writable ? "" : " — view only") + '</option>';
        }).join("");
        var companionAvailable = data.health && data.health.astrakriti_companion && data.health.astrakriti_companion.status === "connected";
        var videoOption = '<option value="video"' + (companionAvailable ? "" : " disabled") + '>Source video + SRT' + (companionAvailable ? "" : " — companion unavailable") + '</option>';
        workspace.innerHTML = '<form id="astrakriti-new-reconstruction" class="astrakriti-form" novalidate>' +
            '<div class="notice-state"><h2>Native WebODM reconstruction intake</h2><p>Mission, Task identity, permissions, upload, and processing remain native WebODM state. Select prepared stills for the direct path, or use source video/SRT preparation when the protected Astrakriti companion reports CONNECTED.</p><p class="mono">Astrakriti companion: ' + escapeHtml(companionAvailable ? "CONNECTED" : ((data.health || {}).astrakriti_companion || {}).status || "UNKNOWN") + '</p></div>' +
            '<div class="form-grid"><label>Mission / Project<select name="project"><option value="new">Create a new WebODM Project</option>' + options + '</select></label><label class="new-project-field">New mission name<input name="project_name" maxlength="100" autocomplete="off"></label><label>Run name<input name="task_name" maxlength="100" required autocomplete="off"></label><label>Input path<select name="input_kind"><option value="stills">Prepared still images</option>' + videoOption + '</select></label><label class="file-field still-input">Prepared still images<input name="images" type="file" accept="image/*" multiple required><small>WebODM requires at least two authorized image files.</small></label><label class="file-field video-input" hidden>Source video<input name="video" type="file" accept="video/*"><small>The protected companion extracts and validates frames before native Task upload.</small></label><label class="file-field video-input" hidden>Telemetry SRT<input name="srt" type="file" accept=".srt,text/plain"><small>Required only for georeferenced preparation.</small></label><label class="video-input" hidden>Preparation mode<select name="source_mode"><option value="local">Local / unreferenced</option><option value="georeferenced">Georeferenced / telemetry</option></select></label></div>' +
            '<div class="intake-frame-review" data-intake-frame-review hidden></div><div class="form-actions"><button class="button button-primary" type="submit">Validate and prepare inputs</button><button class="button button-secondary" type="button" data-reset-intake>Use a new submission identity</button><span class="state-copy" data-submit-state aria-live="polite"></span></div><div class="error-state" data-submit-error hidden></div></form>';
        var form = document.getElementById("astrakriti-new-reconstruction");
        var projectSelect = form.querySelector("[name=project]");
        var inputKind = form.querySelector("[name=input_kind]");
        var sourceMode = form.querySelector("[name=source_mode]");
        var newProjectField = form.querySelector(".new-project-field");
        var stateNode = form.querySelector("[data-submit-state]");
        var errorNode = form.querySelector("[data-submit-error]");
        var storageKey = "astrakriti3d.pending-intake-key";
        var pendingSubmissionKey = storageKey + ".submission";
        var submissionKey = "";
        try { submissionKey = window.localStorage.getItem(storageKey) || ""; } catch (error) {}
        if (!submissionKey) {
            submissionKey = window.crypto && window.crypto.randomUUID ? window.crypto.randomUUID() : "astra-" + Date.now() + "-" + Math.random().toString(36).slice(2);
            try { window.localStorage.setItem(storageKey, submissionKey); } catch (error) {}
        }
        function clearSubmissionKey() {
            try { window.localStorage.removeItem(storageKey); window.localStorage.removeItem(pendingSubmissionKey); } catch (error) {}
        }
        function fileFingerprint(files) {
            return Array.prototype.map.call(files, function (file) {
                return [file.name, file.size, file.lastModified].join(":");
            }).sort().join("|").slice(0, 512);
        }
        function syncProjectField() { newProjectField.hidden = projectSelect.value !== "new"; newProjectField.querySelector("input").required = projectSelect.value === "new"; }
        function syncInputKind() {
            var video = inputKind.value === "video";
            form.querySelectorAll(".still-input").forEach(function (node) { node.hidden = video; });
            form.querySelectorAll(".video-input").forEach(function (node) { node.hidden = !video; });
            form.querySelector("[name=images]").required = !video;
            form.querySelector("[name=video]").required = video;
            form.querySelector("[name=srt]").required = video && sourceMode.value === "georeferenced";
        }
        projectSelect.addEventListener("change", syncProjectField);
        inputKind.addEventListener("change", syncInputKind);
        sourceMode.addEventListener("change", syncInputKind);
        form.querySelector("[data-reset-intake]").addEventListener("click", function () {
            clearSubmissionKey();
            window.location.reload();
        });
        syncProjectField();
        syncInputKind();
        var preparationTimer = null;
        function pollPreparation(identity, submitState) {
            return new Promise(function (resolve, reject) {
                function poll() {
                    if (document.hidden) {
                        preparationTimer = window.setTimeout(poll, 3000);
                        return;
                    }
                    fetch("/api/plugins/astrakriti3d/intake/" + encodeURIComponent(identity.submission_id) + "/prepare/", { credentials: "same-origin", headers: { Accept: "application/json" } }).then(readJsonOrError).then(function (body) {
                        var current = String(body.status || "unknown").toLowerCase();
                        submitState.textContent = "Preparing source video — " + current.toUpperCase();
                        if (current === "imported") {
                            resolve(body);
                            return;
                        }
                        if (current === "completed") {
                            submitState.textContent = "Importing validated frames into the native WebODM Task…";
                            return fetch("/api/plugins/astrakriti3d/intake/" + encodeURIComponent(identity.submission_id) + "/import/", { method: "POST", credentials: "same-origin", headers: { "X-CSRFToken": csrfToken(), Accept: "application/json" } }).then(readJsonOrError).then(resolve);
                        }
                        if (["failed", "cancelled", "recovery_required", "unavailable"].indexOf(current) >= 0) {
                            throw new Error("Astrakriti preparation entered " + current + ". Inspect the preparation evidence and retry with a new identity if the source changed.");
                        }
                        preparationTimer = window.setTimeout(poll, 1500);
                    }).catch(reject);
                }
                poll();
            });
        }
        function reviewAndCommit(identity) {
            var review = form.querySelector("[data-intake-frame-review]");
            var formGrid = form.querySelector(".form-grid");
            var startButton = form.querySelector("button[type=submit]");
            var selected = new Set();
            var strategy = "r1_all";
            var selectionInitialized = false;
            var offset = 0;
            var query = "";
            var latest = null;
            var reviewError = "";

            function requestPage(nextOffset) {
                var url = "/api/plugins/astrakriti3d/intake/" + encodeURIComponent(identity.submission_id) + "/selection/?offset=" + nextOffset + "&limit=48";
                stateNode.textContent = "Loading candidate-frame review…";
                return fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" } }).then(readJsonOrError).then(function (payload) {
                    if (payload.status !== "available") throw new Error("The uploaded inputs are not ready for frame review. Check the submission status or start a new identity.");
                    latest = payload;
                    if (!selectionInitialized) {
                        selected = new Set(payload.selected_filenames || []);
                        strategy = payload.strategy || strategy;
                        selectionInitialized = true;
                    }
                    offset = payload.offset || 0;
                    draw();
                });
            }

            function draw() {
                var items = (latest.items || []).filter(function (item) {
                    return !query || (String(item.filename || "") + " " + String(item.source_frame_index || "") + " " + String(item.timestamp_seconds || "")).toLowerCase().indexOf(query) >= 0;
                });
                var rows = items.map(function (item) {
                    var checked = selected.has(item.filename);
                    var image = item.preview_available && item.thumbnail_url ? '<img loading="lazy" src="' + escapeHtml(item.thumbnail_url) + '" alt="" class="intake-frame-thumb">' : '<span class="frame-thumb-placeholder" aria-hidden="true">NO PREVIEW</span>';
                    var timestamp = item.timestamp_seconds == null ? "TIME UNKNOWN" : formatVideoTime(item.timestamp_seconds);
                    var gps = item.telemetry && item.telemetry.status === "matched" ? coordinateText(item.telemetry.latitude, item.telemetry.longitude) : (latest.mode === "local" ? "LOCAL / UNREFERENCED" : "GPS UNMATCHED");
                    var quality = item.quality_metrics || {};
                    var blur = quality.blur_score == null ? "QUALITY NOT MEASURED" : "BLUR PROXY " + Number(quality.blur_score).toFixed(1);
                    var warning = item.selection_recommendation === "reject" ? "R2 REDUNDANCY ADVISORY" : item.coverage_recommendation === "reject" ? "COVERAGE REDUNDANCY ADVISORY" : "";
                    return '<label class="intake-frame-choice' + (checked ? ' is-included' : '') + '"><input type="checkbox" data-intake-frame="' + escapeHtml(item.filename) + '"' + (checked ? ' checked' : '') + '><span class="intake-frame-choice-preview">' + image + '</span><span class="intake-frame-choice-meta"><strong class="mono">' + escapeHtml(item.filename) + '</strong><small>' + escapeHtml(timestamp) + ' · ' + escapeHtml(gps) + '</small><small>' + escapeHtml(blur) + (warning ? ' · ' + escapeHtml(warning) : '') + '</small></span></label>';
                }).join("");
                var count = selected.size;
                var previousDisabled = offset <= 0;
                var nextDisabled = offset + (latest.items || []).length >= latest.total;
                var diagnostics = latest.selection_diagnostics || {};
                var recommendationSummary = '<p class="state-copy">R1 includes every candidate by default. R2 and coverage sets are experimental suggestions; the frame checkboxes below determine the exact submitted inputs. ' + escapeHtml(String(diagnostics.status || "diagnostics unavailable").replace(/_/g, " ")) + '.</p>';
                var projectLabel = latest.project_id + " · " + (latest.mode || "still images");
                review.innerHTML = section("Review prepared inputs", '<div class="metric-line">' + metric("Mission / Project", projectLabel) + metric("Run", latest.task_name) + metric("Candidates", latest.total) + metric("Selected", count) + '</div>' + recommendationSummary + '<div class="intake-selection-presets"><button type="button" class="button button-secondary" data-intake-strategy="r1_all">Use all R1 frames</button><button type="button" class="button button-secondary" data-intake-strategy="r2_advisory"' + ((latest.r2_filenames || []).length >= 2 ? '' : ' disabled title="No usable R2 recommendation is available"') + '>Use R2 suggestion (' + (latest.r2_filenames || []).length + ')</button><button type="button" class="button button-secondary" data-intake-strategy="coverage_advisory"' + ((latest.coverage_filenames || []).length >= 2 ? '' : ' disabled title="No usable coverage recommendation is available"') + '>Use coverage suggestion (' + (latest.coverage_filenames || []).length + ')</button></div><label class="intake-frame-filter">Filter this page<input type="search" data-intake-frame-filter value="' + escapeHtml(query) + '" placeholder="Filename or frame number"></label><div class="intake-frame-choice-list" aria-label="Select candidate frames">' + (rows || '<p class="empty-state">No candidate frames match this filter.</p>') + '</div><div class="review-pager"><button class="button button-secondary" type="button" data-intake-page="previous"' + (previousDisabled ? ' disabled' : '') + '>Previous frames</button><span class="mono">' + escapeHtml(latest.total ? (offset + 1) + '–' + Math.min(offset + (latest.items || []).length, latest.total) + ' / ' + latest.total : '0 / 0') + '</span><button class="button button-secondary" type="button" data-intake-page="next"' + (nextDisabled ? ' disabled' : '') + '>Next frames</button></div>' + (reviewError ? '<div class="error-state" role="alert"><p>' + escapeHtml(reviewError) + '</p></div>' : '') + '<div class="form-actions"><button class="button button-primary" type="button" data-intake-confirm' + (count < 2 ? ' disabled' : '') + '>Save selection and start reconstruction</button><span class="state-copy" data-intake-confirm-status aria-live="polite"></span></div>', latest.total + ' CANDIDATE FRAMES');
                review.hidden = false;
                stateNode.textContent = "Review the exact candidate images before WebODM processing starts.";

                review.querySelectorAll("[data-intake-frame]").forEach(function (checkbox) {
                    checkbox.addEventListener("change", function () {
                        var name = checkbox.getAttribute("data-intake-frame");
                        if (checkbox.checked) selected.add(name); else selected.delete(name);
                        strategy = "manual";
                        draw();
                        var refocus = review.querySelector('[data-intake-frame="' + CSS.escape(name) + '"]');
                        if (refocus) refocus.focus();
                    });
                });
                review.querySelectorAll("[data-intake-strategy]").forEach(function (button) {
                    button.addEventListener("click", function () {
                        strategy = button.getAttribute("data-intake-strategy");
                        var source = strategy === "r1_all" ? latest.candidate_filenames : strategy === "r2_advisory" ? latest.r2_filenames : latest.coverage_filenames;
                        selected = new Set(source || []);
                        reviewError = selected.size < 2 ? "This suggestion contains fewer than two frames. Keep all frames or make a manual selection." : "";
                        draw();
                    });
                });
                var filterInput = review.querySelector("[data-intake-frame-filter]");
                filterInput.addEventListener("input", function () { query = filterInput.value.trim().toLowerCase(); draw(); var next = review.querySelector("[data-intake-frame-filter]"); if (next) { next.focus(); next.setSelectionRange(query.length, query.length); } });
                review.querySelectorAll("[data-intake-page]").forEach(function (button) {
                    button.addEventListener("click", function () {
                        var nextOffset = Math.max(0, offset + (button.getAttribute("data-intake-page") === "next" ? 48 : -48));
                        requestPage(nextOffset).catch(function (error) { reviewError = error.message; draw(); });
                    });
                });
                var confirm = review.querySelector("[data-intake-confirm]");
                confirm.addEventListener("click", function () {
                    if (selected.size < 2) { reviewError = "Select at least two frames before continuing."; draw(); return; }
                    confirm.disabled = true;
                    var confirmStatus = review.querySelector("[data-intake-confirm-status]");
                    confirmStatus.textContent = "Saving the selected frame set…";
                    var selectionUrl = "/api/plugins/astrakriti3d/intake/" + encodeURIComponent(identity.submission_id) + "/selection/";
                    fetch(selectionUrl, { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken(), Accept: "application/json" }, body: JSON.stringify({ strategy: strategy, selected_filenames: Array.from(selected) }) }).then(readJsonOrError).then(function () {
                        confirmStatus.textContent = "Selection saved. Committing one native WebODM Task…";
                        var commitUrl = "/api/plugins/astrakriti3d/intake/" + encodeURIComponent(identity.submission_id) + "/commit/";
                        return fetch(commitUrl, { method: "POST", credentials: "same-origin", headers: { "X-CSRFToken": csrfToken(), Accept: "application/json" } }).then(readJsonOrError);
                    }).then(function (result) {
                        clearSubmissionKey();
                        window.location.href = "/astrakriti/runs/" + encodeURIComponent(result.task_id) + "/";
                    }).catch(function (error) {
                        reviewError = error.message || "The frame selection could not be committed. Your saved choice remains available for a safe retry.";
                        draw();
                    });
                });
            }

            formGrid.hidden = true;
            startButton.hidden = true;
            review.hidden = false;
            review.innerHTML = section("Review prepared inputs", '<p class="review-loading" role="status">Loading authorized candidate frames…</p>', "LOADING");
            return requestPage(0).catch(function (error) {
                review.innerHTML = section("Frame selection unavailable", '<div class="error-state"><p>' + escapeHtml(error.message || "Prepared inputs could not be reviewed.") + '</p><button type="button" class="button button-secondary" data-intake-review-retry>Retry review</button></div>', "ERROR");
                review.hidden = false;
                review.querySelector("[data-intake-review-retry]").addEventListener("click", function () { reviewAndCommit(identity); });
            });
        }
        form.addEventListener("submit", function (event) {
            event.preventDefault();
            var submit = form.querySelector("button[type=submit]");
            var files = form.querySelector("[name=images]").files;
            var videoFile = form.querySelector("[name=video]").files[0];
            var srtFile = form.querySelector("[name=srt]").files[0];
            var videoMode = inputKind.value === "video";
            var taskName = form.querySelector("[name=task_name]").value.trim();
            var projectName = form.querySelector("[name=project_name]").value.trim();
            var mode = sourceMode.value;
            var inputFiles = videoMode ? [videoFile].concat(srtFile ? [srtFile] : []) : Array.prototype.slice.call(files);
            if ((!videoMode && files.length < 2) || (videoMode && !videoFile) || (videoMode && mode === "georeferenced" && !srtFile) || !taskName || (projectSelect.value === "new" && !projectName)) {
                errorNode.hidden = false;
                errorNode.innerHTML = "<h2>Input needs attention</h2><p>Choose the selected input path, provide a Run name, and name a new Project when creating one. Still input requires at least two images; georeferenced video input requires an SRT.</p>";
                return;
            }
            submit.disabled = true;
            errorNode.hidden = true;
            stateNode.textContent = "Reserving one native WebODM Project/Task identity…";
            fetch("/api/plugins/astrakriti3d/intake/reserve/", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken(), Accept: "application/json" }, body: JSON.stringify({ idempotency_key: submissionKey, project_id: projectSelect.value === "new" ? "" : projectSelect.value, project_name: projectName, task_name: taskName, file_fingerprint: fileFingerprint(inputFiles) }) }).then(readJsonOrError).then(function (identity) {
                try { window.localStorage.setItem(pendingSubmissionKey, identity.submission_id); } catch (error) {}
                if (identity.state === "orphaned" || !identity.project_id || !identity.task_id) throw new Error("The previous intake reservation is no longer attached to a native WebODM Task. Use a new submission identity.");
                if (!identity.task_partial) {
                    clearSubmissionKey();
                    window.location.href = "/astrakriti/runs/" + encodeURIComponent(identity.task_id) + "/";
                    return null;
                }
                if (videoMode) {
                    stateNode.textContent = "Sending the source video to the protected Astrakriti companion…";
                    var preparationData = new FormData();
                    preparationData.append("mode", mode);
                    preparationData.append("video", videoFile, videoFile.name);
                    if (srtFile) preparationData.append("srt", srtFile, srtFile.name);
                    return xhrJson("/api/plugins/astrakriti3d/intake/" + encodeURIComponent(identity.submission_id) + "/prepare/", "POST", preparationData, function (loaded, total) { stateNode.textContent = total ? "Sending source video — " + Math.round(loaded / total * 100) + "%" : "Sending source video…"; }).then(function () { return pollPreparation(identity, stateNode); }).then(function () { return identity; });
                }
                stateNode.textContent = "Uploading prepared images to WebODM…";
                var uploadData = new FormData();
                Array.prototype.forEach.call(files, function (file) { uploadData.append("images", file, file.name); });
                return xhrJson("/api/projects/" + encodeURIComponent(identity.project_id) + "/tasks/" + encodeURIComponent(identity.task_id) + "/upload/", "POST", uploadData, function (loaded, total) { stateNode.textContent = total ? "Uploading prepared images — " + Math.round(loaded / total * 100) + "%" : "Uploading prepared images…"; }).then(function () { return identity; });
            }).then(function (identity) {
                if (!identity) return;
                return reviewAndCommit(identity);
            }).catch(function (error) {
                window.clearTimeout(preparationTimer);
                submit.disabled = false;
                stateNode.textContent = "";
                errorNode.hidden = false;
                errorNode.innerHTML = "<h2>Native submission needs attention</h2><p>" + escapeHtml(error.message || "WebODM rejected the request") + "</p><p>The server-side submission identity is retained so retrying cannot create a second Project/Task. Use the reset button only when you intentionally want a new reconstruction.</p>";
            });
        });
        var pendingSubmissionId = null;
        try { pendingSubmissionId = window.localStorage.getItem(pendingSubmissionKey); } catch (error) {}
        if (pendingSubmissionId) {
            fetch("/api/plugins/astrakriti3d/intake/" + encodeURIComponent(pendingSubmissionId) + "/selection/", { credentials: "same-origin", headers: { Accept: "application/json" } }).then(readJsonOrError).then(function (pending) {
                if (!pending.task_id) return;
                if (!pending.partial) {
                    clearSubmissionKey();
                    window.location.href = "/astrakriti/runs/" + encodeURIComponent(pending.task_id) + "/";
                    return;
                }
                if (pending.status === "available") {
                    submit.disabled = true;
                    reviewAndCommit({ submission_id: pendingSubmissionId });
                }
            }).catch(function () { /* An unavailable or unrelated stale reservation must not block a fresh form. */ });
        }
    }

    function readJsonOrError(response) {
        return response.json().catch(function () { return {}; }).then(function (body) { if (!response.ok) throw new Error(body.detail || body.error || "WebODM request failed"); return body; });
    }

    function xhrJson(url, method, body, onProgress) {
        return new Promise(function (resolve, reject) {
            var request = new XMLHttpRequest();
            request.open(method, url, true);
            request.withCredentials = true;
            request.setRequestHeader("X-CSRFToken", csrfToken());
            request.setRequestHeader("Accept", "application/json");
            request.upload.onprogress = function (event) { if (onProgress && event.lengthComputable) onProgress(event.loaded, event.total); };
            request.onload = function () { var response = {}; try { response = JSON.parse(request.responseText || "{}"); } catch (error) {} if (request.status >= 200 && request.status < 300) resolve(response); else reject(new Error(response.detail || response.error || "WebODM upload failed")); };
            request.onerror = function () { reject(new Error("WebODM upload could not be reached.")); };
            request.send(body);
        });
    }

    function startTaskRefresh() {
        if (!task || !task.native_urls || page === "map" || page === "model") return;
        var timer = null;
        var inFlight = false;
        var requestGeneration = 0;
        var interval = 5000;

        function schedule(delay) {
            window.clearTimeout(timer);
            timer = window.setTimeout(refresh, delay);
        }

        function refresh() {
            if (document.hidden || inFlight) {
                schedule(interval);
                return;
            }
            inFlight = true;
            var generation = ++requestGeneration;
            fetch(task.native_urls.task, { credentials: "same-origin", headers: { Accept: "application/json" } }).then(readJsonOrError).then(function (next) {
                if (generation !== requestGeneration || String(next.id) !== String(task.id)) {
                    inFlight = false;
                    schedule(interval);
                    return;
                }
                var assetsChanged = JSON.stringify(next.available_assets || []) !== JSON.stringify(task.available_assets || []);
                var progressChanged = next.running_progress !== task.running_progress || next.upload_progress !== task.upload_progress;
                var changed = next.status !== task.status_code || (next.last_error || "") !== (task.last_error || "") || assetsChanged || progressChanged;
                if (changed) {
                    window.location.reload();
                    return;
                }
                inFlight = false;
                schedule(interval);
            }).catch(function () {
                inFlight = false;
                schedule(10000);
            });
        }

        document.addEventListener("visibilitychange", function () {
            if (document.hidden) {
                window.clearTimeout(timer);
            } else {
                schedule(0);
            }
        });
        window.addEventListener("beforeunload", function () {
            requestGeneration += 1;
            window.clearTimeout(timer);
        });
        schedule(interval);
    }

    function renderHealth(workspace) {
        function healthBlock(label, value, detail) {
            return '<div class="health-block"><h3>' + escapeHtml(label) + '</h3><p>' + status(value) + '</p><p>' + escapeHtml(detail || "") + '</p></div>';
        }
        var health = data.health || {};
        var nodes = health.processing_nodes || {};
        var worker = health.worker || {};
        var nodeDetail = nodes.nodes && nodes.nodes.length ? nodes.nodes.map(function (node) { return node.label + ": " + node.status; }).join(" · ") : "No authorized processing node is configured.";
        var storage = health.storage || {};
        var isAdmin = Boolean((health.webodm || {}).admin_available);
        var runtime = page === "settings" ? section("Runtime configuration", '<div class="metric-line">' + metric("WebODM version", (health.webodm || {}).version || "unknown") + metric("Companion", (health.astrakriti_companion || {}).status || "unknown") + metric("Admin", isAdmin ? "available" : "not available") + '</div><p class="state-copy">Authentication, Project permissions, Task lifecycle, processing-node assignment, and native viewer configuration remain owned by WebODM. Astrakriti preprocessing is only enabled when a protected companion service is configured.</p><p><a class="button button-secondary" href="/about/">Open WebODM product information</a></p>', "NATIVE CONFIGURATION") : "";
        var reconciliationPanel = page === "settings" && isAdmin ? section("Legacy reconciliation", '<p class="state-copy">Unlinked and conflicting legacy identities are listed for review. Source paths and original payloads are intentionally withheld. This panel is read-only; reconciliation is performed through the documented management command after explicit identity review.</p><div id="astrakriti-legacy-reconciliation" aria-live="polite"><p class="review-loading" role="status">Loading reconciliation records…</p></div>', "STAFF ONLY") : "";
        workspace.innerHTML = section("System health", '<div class="health-grid">' + healthBlock("WebODM session", (health.webodm || {}).status, (health.webodm || {}).detail) + healthBlock("Workers", worker.status, worker.detail) + healthBlock("Processing nodes", nodes.status, nodeDetail) + healthBlock("Storage", storage.status, storage.free_bytes != null ? formatBytes(storage.free_bytes) + " free of " + formatBytes(storage.total_bytes) : storage.detail) + healthBlock("Astrakriti companion", (health.astrakriti_companion || {}).status, (health.astrakriti_companion || {}).detail) + '</div><p><button class="button button-secondary" id="astrakriti-refresh-health" type="button">Refresh health</button></p>', "LAST CHECK " + formatDate(health.checked_at)) + runtime + reconciliationPanel;
        var refresh = document.getElementById("astrakriti-refresh-health");
        if (refresh) refresh.addEventListener("click", function () {
            refresh.disabled = true;
            fetch("/api/plugins/astrakriti3d/health", { credentials: "same-origin" }).then(function (response) { if (!response.ok) throw new Error("Health request failed"); return response.json(); }).then(function (next) { data.health = next; renderHealth(workspace); updateUtility(next); }).catch(function () { refresh.disabled = false; });
        });
        var queue = document.getElementById("astrakriti-legacy-reconciliation");
        if (queue) {
            function loadQueue(offset) {
                queue.innerHTML = '<p class="review-loading" role="status">Loading reconciliation records…</p>';
                fetch("/api/plugins/astrakriti3d/legacy/reconciliation/?offset=" + offset + "&limit=50", { credentials: "same-origin", headers: { Accept: "application/json" } })
                    .then(readJsonOrError)
                    .then(function (payload) {
                        var counts = payload.counts || {};
                        if (!payload.count) {
                            queue.innerHTML = '<p class="empty-state">No unresolved or conflicting legacy identities are recorded.</p>';
                            return;
                        }
                        var rows = (payload.items || []).map(function (item) {
                            var native = [item.project_id ? "Project " + item.project_id : "", item.task_id ? "Task " + item.task_id : ""].filter(Boolean).join(" · ") || "Unlinked";
                            var reasons = (item.reasons || []).join(", ") || "Explicit identity review required";
                            return '<tr><td>' + escapeHtml(item.entity_type) + '</td><td><strong>' + escapeHtml(item.legacy_label || item.legacy_id) + '</strong><div class="mono">' + escapeHtml(item.legacy_id) + '</div></td><td>' + status(item.mapping_state) + '<div class="state-copy">' + escapeHtml(reasons) + '</div></td><td class="mono">' + escapeHtml(native) + '</td><td>' + escapeHtml(item.legacy_status || "—") + '</td></tr>';
                        }).join("");
                        var previous = offset > 0 ? '<button class="button button-secondary" type="button" data-legacy-offset="' + Math.max(0, offset - 50) + '">Previous</button>' : "";
                        var next = offset + payload.limit < payload.count ? '<button class="button button-secondary" type="button" data-legacy-offset="' + (offset + payload.limit) + '">Next</button>' : "";
                        queue.innerHTML = '<p class="state-copy">' + escapeHtml(counts.reconciliation_required || 0) + ' need reconciliation · ' + escapeHtml(counts.conflict || 0) + ' conflict · showing ' + (offset + 1) + '–' + Math.min(offset + payload.limit, payload.count) + ' of ' + payload.count + '</p><div class="review-table-wrap"><table class="astra-table"><thead><tr><th>Record type</th><th>Legacy identity</th><th>Mapping state / reason</th><th>Native association</th><th>Legacy status</th></tr></thead><tbody>' + rows + '</tbody></table></div><div class="form-actions">' + previous + next + '</div>';
                    })
                    .catch(function (error) {
                        queue.innerHTML = '<div class="error-state"><h3>Reconciliation records unavailable</h3><p>' + escapeHtml(error.message) + '</p><button class="button button-secondary" type="button" data-legacy-retry>Retry</button></div>';
                    });
            }
            queue.addEventListener("click", function (event) {
                var button = event.target.closest("button[data-legacy-offset],button[data-legacy-retry]");
                if (!button) return;
                loadQueue(button.hasAttribute("data-legacy-retry") ? 0 : Number(button.getAttribute("data-legacy-offset")));
            });
            loadQueue(0);
        }
    }

    function updateUtility(health) {
        health = health || data.health || {};
        var nodeStatus = (health.processing_nodes || {}).status || "unknown";
        var storageStatus = (health.storage || {}).status || "unknown";
        var processing = document.getElementById("astrakriti-utility-processing");
        var storage = document.getElementById("astrakriti-utility-storage");
        var time = document.getElementById("astrakriti-utility-time");
        if (processing) processing.textContent = nodeStatus.toUpperCase();
        if (storage) storage.textContent = storageStatus.toUpperCase();
        if (time) time.textContent = formatDate(health.checked_at);
    }

    function measurementList(items) {
        var node = document.getElementById("astrakriti-measurement-list");
        if (!node) return;
        if (!items || !items.length) {
            node.innerHTML = '<p class="state-copy">No saved measurements for this Task.</p>';
            return;
        }
        var canEdit = Boolean(data.task && data.task.permissions && data.task.permissions.change);
        node.innerHTML = items.map(function (item) {
            var stale = item.stale ? " · STALE ARTIFACT" : "";
            var value = item.result && item.result.value != null ? item.result.value + " " + (item.units || "") : "geometry restored";
            var limitation = item.result && item.result.unit_context && item.result.unit_context.limitation ? '<small class="state-copy">' + escapeHtml(item.result.unit_context.limitation) + '</small>' : "";
            var actions = canEdit ? '<div class="measurement-actions"><button type="button" data-action="rename">Rename</button><button class="danger" type="button" data-action="delete">Delete</button></div><small class="state-copy measurement-action-status" aria-live="polite"></small>' : '<small class="state-copy">READ-ONLY — change permission is required to edit or delete.</small>';
            return '<div class="measurement-row" data-measurement-id="' + escapeHtml(item.id) + '" data-updated-at="' + escapeHtml(item.updated_at || '') + '"><strong>' + escapeHtml(item.name) + '</strong><small>' + escapeHtml(item.measurement_type) + ' · ' + escapeHtml(value) + '</small><small>' + escapeHtml(item.method || "method unavailable") + escapeHtml(stale) + '</small>' + limitation + actions + '</div>';
        }).join("");
        function reportMeasurementActionError(row, error) {
            var status = row && row.querySelector(".measurement-action-status");
            if (status) status.textContent = error && error.message ? error.message : "Action failed; retry is safe.";
        }
        function readMeasurementActionResponse(response, fallback) {
            return response.json().catch(function () { return {}; }).then(function (body) {
                if (!response.ok) throw new Error(body.detail || body.error || fallback);
                return body;
            });
        }
        node.querySelectorAll("button[data-action]").forEach(function (button) {
            button.addEventListener("click", function () {
                var row = button.closest("[data-measurement-id]");
                var id = row && row.getAttribute("data-measurement-id");
                if (!id) return;
                if (button.getAttribute("data-action") === "delete") {
                    if (!window.confirm("Delete this saved measurement?")) return;
                    fetch(endpoint + "/" + encodeURIComponent(id), { method: "DELETE", credentials: "same-origin", headers: { "X-CSRFToken": csrfToken() } }).then(function (response) { if (!response.ok) throw new Error("Delete failed"); window.dispatchEvent(new CustomEvent("astrakriti:measurement-changed", { detail: { action: "delete", id: id } })); return loadMeasurements(); }).catch(function (error) { reportMeasurementActionError(row, error); });
                } else {
                    var current = items.filter(function (item) { return item.id === id; })[0];
                    var name = window.prompt("Measurement name", current ? current.name : "Measurement");
                    if (!name) return;
                    fetch(endpoint + "/" + encodeURIComponent(id), { method: "PATCH", credentials: "same-origin", headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() }, body: JSON.stringify({ name: name, expected_updated_at: current && current.updated_at }) }).then(function (response) { return readMeasurementActionResponse(response, "Rename failed"); }).then(function () { window.dispatchEvent(new CustomEvent("astrakriti:measurement-changed", { detail: { action: "rename", id: id, name: name } })); return loadMeasurements(); }).catch(function (error) { reportMeasurementActionError(row, error); });
                }
            });
        });
    }

    function csrfToken() {
        var match = document.cookie.match(/(?:^|; )csrftoken=([^;]*)/);
        if (match) return decodeURIComponent(match[1]);
        var meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute("content") : "";
    }

    function loadMeasurements() {
        if (!endpoint) return Promise.resolve([]);
        return fetch(endpoint, { credentials: "same-origin", headers: { Accept: "application/json" } }).then(function (response) { if (!response.ok) throw new Error("Measurements unavailable"); return response.json(); }).then(function (items) { measurementList(items); return items; }).catch(function () { var node = document.getElementById("astrakriti-measurement-list"); if (node) node.innerHTML = '<p class="state-copy">UNAVAILABLE — saved measurements could not be loaded. Retry after checking the authenticated WebODM session.</p>'; return []; });
    }

    var measurementNode = document.getElementById("astrakriti-measurement-list");
    if (measurementNode) measurementNode.addEventListener("astrakriti:reload-measurements", loadMeasurements);

    var workspace = document.getElementById("astrakriti-workspace");
    if (workspace) {
        if (page === "overview") renderOverview(workspace);
        else if (page === "missions") renderMissions(workspace);
        else if (page === "mission") renderMission(workspace);
        else if (page === "run") renderRun(workspace);
        else renderGeneric(workspace);
    }
    updateUtility(data.health);
    if (task) loadMeasurements();
    startTaskRefresh();
})();

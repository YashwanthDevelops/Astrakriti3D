(function () {
    "use strict";

    if (!window.PluginsAPI || !window.PluginsAPI.Map) return;

    var savedMeasurementLayers = {};

    function csrfToken() {
        var match = document.cookie.match(/(?:^|; )csrftoken=([^;]*)/);
        if (match) return decodeURIComponent(match[1]);
        var meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute("content") : "";
    }

    function shellContext() {
        var shell = document.getElementById("astrakriti-shell");
        if (!shell || !shell.getAttribute("data-task-id")) return null;
        var taskId = shell.getAttribute("data-task-id");
        return {
            taskId: taskId,
            endpoint: "/api/plugins/astrakriti3d/measurements/task/" + taskId,
            dsmAvailable: shell.getAttribute("data-dsm-available") === "true"
        };
    }

    function waitForWorker(parentTaskId, taskId, resultToken, attempts) {
        if (attempts <= 0) return Promise.reject(new Error("DSM volume calculation timed out; the measurement was not saved."));
        var jobHeaders = { "X-Volume-Job-Token": resultToken };
        return fetch("/api/plugins/measure/task/" + encodeURIComponent(parentTaskId) + "/volume/check/" + encodeURIComponent(taskId), { credentials: "same-origin", headers: jobHeaders }).then(function (response) {
            if (!response.ok) throw new Error("DSM volume worker status could not be read.");
            return response.json();
        }).then(function (state) {
            if (state.error) throw new Error(state.error);
            if (state.ready) return fetch("/api/plugins/measure/task/" + encodeURIComponent(parentTaskId) + "/volume/get/" + encodeURIComponent(taskId), { credentials: "same-origin", headers: jobHeaders }).then(function (response) {
                if (!response.ok) throw new Error("DSM volume result could not be read.");
                return response.json();
            }).then(function (result) {
                if (result.error || result.output == null) throw new Error(result.error || "DSM volume result did not include a numeric value.");
                return { value: Number(result.output), unitContext: result.unit_context || null };
            });
            return new Promise(function (resolve) { window.setTimeout(function () { resolve(waitForWorker(parentTaskId, taskId, resultToken, attempts - 1)); }, 1000); });
        });
    }

    function calculateDsmVolume(context, feature) {
        return fetch("/api/plugins/measure/task/" + encodeURIComponent(context.taskId) + "/volume", {
            method: "POST",
            credentials: "same-origin",
            headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken(), Accept: "application/json" },
            body: JSON.stringify({ area: feature, method: "triangulate" })
        }).then(function (response) {
            if (!response.ok) throw new Error("DSM volume request failed.");
            return response.json();
        }).then(function (result) {
            if (result.error) throw new Error(result.error);
            if (!result.celery_task_id) throw new Error("DSM volume worker was not started.");
            if (!result.result_token) throw new Error("DSM volume job was not bound to its Task.");
            return waitForWorker(context.taskId, result.celery_task_id, result.result_token, 90);
        });
    }

    function saveMeasurement(context, event) {
        var feature = event.resultFeature && event.resultFeature.toGeoJSON ? event.resultFeature.toGeoJSON(14) : null;
        if (!feature || !feature.geometry) return Promise.reject(new Error("The native measurement has no exportable geometry."));
        var type = feature.geometry.type === "LineString" ? "distance" : "area";
        var result = {};
        if (event.model && typeof event.model.length === "number" && isFinite(event.model.length)) result.value = event.model.length;
        if (event.model && typeof event.model.area === "number" && isFinite(event.model.area)) result.area = event.model.area;
        var defaultName = type === "distance" ? "Map distance" : "Map area";
        var name = defaultName;
        try {
            var promptedName = window.prompt("Measurement name", defaultName);
            if (promptedName === null) return Promise.resolve(null);
            if (promptedName.trim()) name = promptedName.trim();
        } catch (dialogError) {
            // Some embedded browsers do not implement JavaScript prompt dialogs.
            // Keep the documented default so saving remains durable and explicit.
        }

        var saveType = type;
        var method = "WebODM native Leaflet measurement";
        var units = type === "distance" ? "m" : "m²";
        var calculation = Promise.resolve();
        // The acceptance workflow requires a valid DSM measurement to retain its
        // base-surface method and volume. Keep this decision in the result popup
        // instead of relying on a blocking browser confirm dialog.
        var calculateVolume = type === "area" && context.dsmAvailable;
        if (calculateVolume) {
            calculation = calculateDsmVolume(context, feature).then(function (volumeResult) {
                saveType = "volume";
                units = "m³";
                var unitContext = volumeResult.unitContext || {};
                method = "WebODM DSM volume / triangulate base surface";
                if (unitContext.vertical_unit_source && unitContext.vertical_unit_source.indexOf("assumed") === 0) method += "; Z assumed " + unitContext.vertical_unit + " from CRS; datum unknown";
                else if (unitContext.vertical_unit_source) method += "; Z " + unitContext.vertical_unit + " from band; datum unknown";
                result = { value: volumeResult.value, base_method: "triangulate", source: "WebODM DSM", unit_context: unitContext };
            });
        }

        return calculation.then(function () { return fetch(context.endpoint, {
            method: "POST",
            credentials: "same-origin",
            headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken(), Accept: "application/json" },
            body: JSON.stringify({
                name: name,
                measurement_type: saveType,
                geometry: feature.geometry,
                result: result,
                units: units,
                crs: "EPSG:4326",
                method: method
            })
        }).then(function (response) {
            if (!response.ok) return response.json().catch(function () { return {}; }).then(function (body) { throw new Error(body.detail || body.error || "Measurement save failed"); });
            return response.json();
        }); });
    }

    function restoreMeasurements(context, map, Leaflet) {
        fetch(context.endpoint, { credentials: "same-origin", headers: { Accept: "application/json" } }).then(function (response) { return response.ok ? response.json() : []; }).then(function (items) {
            Leaflet = Leaflet || window.L;
            if (!Leaflet || !map || !Leaflet.geoJSON) return;
            items.forEach(function (item) {
                if (!item.geometry) return;
                var layer = Leaflet.geoJSON({ type: "Feature", geometry: item.geometry }, { style: { color: "#2f6e79", weight: 3, dashArray: "5 4" } }).addTo(map);
                layer.bindTooltip(item.name || "Saved measurement");
                layer._astrakritiMeasurementId = item.id;
                savedMeasurementLayers[item.id] = layer;
            });
        }).catch(function () {});
    }

    window.PluginsAPI.Map.willAddControls(["leaflet"], function (args, Leaflet) {
        var context = shellContext();
        if (!context || !args.map) return;
        restoreMeasurements(context, args.map, Leaflet && Leaflet.default ? Leaflet.default : Leaflet);
        window.addEventListener("astrakriti:measurement-changed", function (event) {
            var detail = event.detail || {};
            var layer = savedMeasurementLayers[detail.id];
            if (!layer) return;
            if (detail.action === "delete") {
                args.map.removeLayer(layer);
                delete savedMeasurementLayers[detail.id];
            } else if (detail.action === "rename") {
                layer.unbindTooltip();
                layer.bindTooltip(detail.name || "Saved measurement");
            }
        });
        args.map.on("measurepopupshown", function (event) {
            var container = event.popupContainer;
            if (!container || container.querySelector(".astrakriti-save-measurement")) return;
            var button = document.createElement("button");
            button.type = "button";
            button.className = "astrakriti-save-measurement";
            button.textContent = "Save to task";
            button.addEventListener("click", function () {
                button.disabled = true;
                saveMeasurement(context, event).then(function (saved) {
                    if (!saved) {
                        button.disabled = false;
                        return;
                    }
                    button.textContent = "Saved";
                    window.dispatchEvent(new CustomEvent("astrakriti:measurement-changed", { detail: { action: "save", id: saved && saved.id } }));
                    var list = document.getElementById("astrakriti-measurement-list");
                    if (list) list.dispatchEvent(new CustomEvent("astrakriti:reload-measurements"));
                }).catch(function (error) {
                    button.disabled = false;
                    button.textContent = error.message || "Retry save";
                });
            });
            container.appendChild(button);
        });
    });
})();

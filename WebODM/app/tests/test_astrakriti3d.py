import json
import hashlib
import io
import os
import shutil
import sqlite3
import subprocess
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth.models import Group, Permission, User
from django.contrib.gis.geos import Polygon
from django.core import signing
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import Client, override_settings
from guardian.shortcuts import assign_perm
import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.transform import from_origin
from rest_framework.test import APIRequestFactory, force_authenticate

from app.models import (
    AstrakritiLegacyLink,
    AstrakritiMissionMetadata,
    AstrakritiSubmission,
    Project,
    Task,
)
from app.tests.classes import BootTestCase
from coreplugins.measure.api import (
    TaskVolume,
    TaskVolumeCheck,
    TaskVolumeResult,
    VOLUME_JOB_TOKEN_SALT,
    _volume_job_token,
)
from coreplugins.measure.volume import calc_volume, get_volume_unit_context
from coreplugins.astrakriti3d.api import (
    _preparation_review_documents,
    _stage_companion_upload,
    _write_task_preparation_review,
)


class TestAstrakriti3D(BootTestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.get(username="testuser")
        self.user.groups.add(Group.objects.get(name="Default"))
        self.user.user_permissions.add(Permission.objects.get(codename="add_project"))
        self.user = User.objects.get(pk=self.user.pk)
        self.project = Project.objects.get(owner=self.user)
        self.task = Task.objects.create(project=self.project, name="real-task-test")
        self.client.login(username="testuser", password="test1234")

    def test_shell_uses_webodm_context(self):
        response = self.client.get("/astrakriti/overview/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "coreplugins/astrakriti3d/templates/app.html")
        self.assertContains(response, "ASTRAKRITI3D")
        self.assertContains(response, 'data-page="overview"')

        mission_runs = self.client.get("/astrakriti/missions/{}/runs/".format(self.project.id))
        self.assertEqual(mission_runs.status_code, 200)
        self.assertContains(mission_runs, 'data-page="runs"')

        processing = self.client.get("/astrakriti/processing/")
        self.assertEqual(processing.status_code, 200)
        self.assertNotContains(processing, "Run context required")

    def test_health_storage_error_does_not_disclose_internal_path(self):
        class FakeCompanion:
            def health_payload(self):
                return {"status": "not_configured", "detail": "Optional companion is not configured."}

        private_path = "C:\\private\\webodm\\media"
        with patch(
            "coreplugins.astrakriti3d.views.shutil.disk_usage",
            side_effect=OSError("Permission denied: '{}'".format(private_path)),
        ), patch(
            "coreplugins.astrakriti3d.views.AstrakritiCompanionClient",
            return_value=FakeCompanion(),
        ):
            response = self.client.get("/api/plugins/astrakriti3d/health")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["storage"]["status"], "unavailable")
        self.assertIn("could not read storage capacity", payload["storage"]["detail"])
        self.assertNotIn(private_path, payload["storage"]["detail"])

    def test_mission_metadata_is_project_scoped_and_keeps_native_name_authority(self):
        endpoint = "/api/plugins/astrakriti3d/mission/{}/metadata/".format(self.project.id)
        initial = self.client.get(endpoint)
        self.assertEqual(initial.status_code, 200)
        self.assertFalse(initial.json()["recorded"])
        self.assertFalse(AstrakritiMissionMetadata.objects.filter(project=self.project).exists())

        response = self.client.patch(
            endpoint,
            data=json.dumps({
                "location": "North ridge",
                "capture_context": "Inspection capture",
                "provenance": {"source": "field log", "revision": 2},
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["recorded"])
        self.assertEqual(response.json()["location"], "North ridge")
        self.assertEqual(response.json()["provenance"]["revision"], 2)
        self.assertEqual(Project.objects.get(pk=self.project.pk).name, self.project.name)
        self.assertEqual(AstrakritiMissionMetadata.objects.filter(project=self.project).count(), 1)

        invalid = self.client.patch(
            endpoint,
            data=json.dumps({"provenance": ["not", "an", "object"]}),
            content_type="application/json",
        )
        self.assertEqual(invalid.status_code, 400)

    def test_mission_metadata_requires_project_change_permission(self):
        assign_perm("view_project", User.objects.get(username="testuser2"), self.project)
        self.client.logout()
        self.client.login(username="testuser2", password="test1234")
        endpoint = "/api/plugins/astrakriti3d/mission/{}/metadata/".format(self.project.id)
        self.assertEqual(self.client.get(endpoint).status_code, 200)
        denied = self.client.patch(
            endpoint,
            data=json.dumps({"location": "Unauthorized write"}),
            content_type="application/json",
        )
        self.assertEqual(denied.status_code, 404)
        self.assertFalse(AstrakritiMissionMetadata.objects.filter(project=self.project).exists())

    def test_legacy_reconciliation_queue_is_staff_only_and_redacted(self):
        link = AstrakritiLegacyLink.objects.create(
            source_path="C:/private/jobs.sqlite3",
            entity_type=AstrakritiLegacyLink.MISSION,
            legacy_id="legacy-mission-17",
            legacy_label="Old hillside survey",
            mapping_state=AstrakritiLegacyLink.RECONCILIATION_REQUIRED,
            legacy_payload={"private_video_path": "C:/private/source.mp4"},
            reconciliation={"reasons": ["no_exact_native_identity"]},
        )
        endpoint = "/api/plugins/astrakriti3d/legacy/reconciliation/"
        user = User.objects.get(pk=self.user.pk)
        user.is_staff = False
        user.save(update_fields=("is_staff",))
        self.assertEqual(self.client.get(endpoint).status_code, 403)

        user.is_staff = True
        user.save(update_fields=("is_staff",))
        response = self.client.get(endpoint + "?limit=1")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["counts"]["reconciliation_required"], 1)
        self.assertEqual(payload["items"][0]["id"], str(link.id))
        self.assertEqual(payload["items"][0]["reasons"], ["no_exact_native_identity"])
        serialized = json.dumps(payload)
        self.assertNotIn("source_path", serialized)
        self.assertNotIn("C:/private", serialized)
        self.assertNotIn("legacy_payload", serialized)

        invalid_page = self.client.get(endpoint + "?offset=not-an-integer")
        self.assertEqual(invalid_page.status_code, 400)

    def test_private_task_workspace_returns_not_found(self):
        other_user = User.objects.get(username="testuser2")
        other_project = Project.objects.get(owner=other_user)
        private_task = Task.objects.create(project=other_project, name="private-map-task")

        response = self.client.get("/astrakriti/runs/{}/map/".format(private_task.id))

        self.assertEqual(response.status_code, 404)

    def test_task_measurement_crud_is_scoped_and_exportable(self):
        endpoint = "/api/plugins/astrakriti3d/measurements/task/{}/".format(self.task.id)
        geometry = {
            "type": "LineString",
            "coordinates": [[12.0, 45.0], [12.001, 45.001]],
        }

        response = self.client.post(
            endpoint,
            data=json.dumps(
                {
                    "name": "Control distance",
                    "geometry": geometry,
                    "measurement_type": "distance",
                    "result": {"value": 10.0},
                    "units": "m",
                    "crs": "EPSG:4326",
                    "method": "test control geometry",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        measurement_id = response.json()["id"]

        response = self.client.get(endpoint)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["task_id"], str(self.task.id))

        detail = endpoint + measurement_id + "/"
        response = self.client.patch(
            detail,
            data=json.dumps({"name": "Renamed control distance"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["name"], "Renamed control distance")

        response = self.client.get(endpoint + "export/?format=geojson")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content)["features"][0]["geometry"], geometry)

        response = self.client.delete(detail)
        self.assertEqual(response.status_code, 204)
        self.assertEqual(self.client.get(endpoint).json(), [])

    def test_measurement_cannot_cross_task_project_boundary(self):
        other_user = User.objects.get(username="testuser2")
        other_project = Project.objects.get(owner=other_user)
        other_task = Task.objects.create(project=other_project, name="private-task")
        endpoint = "/api/plugins/astrakriti3d/measurements/task/{}/".format(other_task.id)

        response = self.client.get(endpoint)
        self.assertEqual(response.status_code, 404)

    def test_stale_measurement_update_returns_conflict(self):
        endpoint = "/api/plugins/astrakriti3d/measurements/task/{}/".format(self.task.id)
        geometry = {
            "type": "LineString",
            "coordinates": [[12.0, 45.0], [12.001, 45.001]],
        }
        created = self.client.post(
            endpoint,
            data=json.dumps({"name": "Concurrent control", "geometry": geometry}),
            content_type="application/json",
        )
        self.assertEqual(created.status_code, 201)
        measurement_id = created.json()["id"]
        revision = created.json()["updated_at"]
        detail = endpoint + measurement_id + "/"

        first = self.client.patch(
            detail,
            data=json.dumps({"name": "First editor", "expected_updated_at": revision}),
            content_type="application/json",
        )
        self.assertEqual(first.status_code, 200)

        stale = self.client.patch(
            detail,
            data=json.dumps({"name": "Stale editor", "expected_updated_at": revision}),
            content_type="application/json",
        )
        self.assertEqual(stale.status_code, 409)
        self.assertIn("changed in another editor", stale.json()["detail"])
        self.assertEqual(self.client.get(endpoint).json()[0]["name"], "First editor")

    def test_view_permission_does_not_grant_measurement_write(self):
        other_user = User.objects.get(username="testuser2")
        other_project = Project.objects.get(owner=other_user)
        other_task = Task.objects.create(project=other_project, name="view-only-task")
        assign_perm("view_project", self.user, other_project)
        endpoint = "/api/plugins/astrakriti3d/measurements/task/{}/".format(other_task.id)
        geometry = {
            "type": "LineString",
            "coordinates": [[12.0, 45.0], [12.001, 45.001]],
        }

        self.assertEqual(self.client.get(endpoint).status_code, 200)
        response = self.client.post(
            endpoint,
            data=json.dumps({"name": "must fail", "geometry": geometry}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 404)

    def test_polygon_geometry_must_be_closed(self):
        endpoint = "/api/plugins/astrakriti3d/measurements/task/{}/".format(self.task.id)
        polygon = {
            "type": "Polygon",
            "coordinates": [[[12.0, 45.0], [12.001, 45.0], [12.001, 45.001], [12.0, 45.001]]],
        }
        response = self.client.post(
            endpoint,
            data=json.dumps({"name": "Open polygon", "geometry": polygon}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_volume_requires_a_real_dsm_extent(self):
        endpoint = "/api/plugins/astrakriti3d/measurements/task/{}/".format(self.task.id)
        polygon = {
            "type": "Polygon",
            "coordinates": [[[12.0, 45.0], [12.001, 45.0], [12.001, 45.001], [12.0, 45.0]]],
        }
        response = self.client.post(
            endpoint,
            data=json.dumps(
                {
                    "name": "Invalid volume",
                    "geometry": polygon,
                    "measurement_type": "volume",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_volume_rejects_nodata_footprint(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nodata.tif"
            raster = np.full((4, 4), 10, dtype="float32")
            raster[0, 0] = -9999
            with rasterio.open(
                path,
                "w",
                driver="GTiff",
                height=4,
                width=4,
                count=1,
                dtype="float32",
                crs="EPSG:32615",
                transform=from_origin(500000, 4100004, 1, 1),
                nodata=-9999,
            ) as dataset:
                dataset.write(raster, 1)

            to_lonlat = Transformer.from_crs(32615, 4326, always_xy=True)
            projected_polygon = [
                (500000.1, 4100000.1),
                (500003.9, 4100000.1),
                (500003.9, 4100003.9),
                (500000.1, 4100003.9),
                (500000.1, 4100000.1),
            ]
            polygon = [
                [lon, lat]
                for lon, lat in (to_lonlat.transform(x, y) for x, y in projected_polygon)
            ]
            result = calc_volume(
                str(path), pts=polygon, pts_epsg=4326, base_method="triangulate"
            )

            self.assertEqual(
                result,
                {"error": "Selected footprint intersects NoData or incomplete DSM coverage"},
            )

    def test_volume_unit_context_qualifies_missing_vertical_unit_and_datum(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "projected-dsm.tif"
            with rasterio.open(
                path,
                "w",
                driver="GTiff",
                height=2,
                width=2,
                count=1,
                dtype="float32",
                crs="EPSG:32615",
                transform=from_origin(500000, 4100000, 1, 1),
            ) as dataset:
                dataset.write(np.ones((2, 2), dtype="float32"), 1)

            with rasterio.open(path) as dataset:
                context = get_volume_unit_context(dataset)
                self.assertEqual(context["units"], "m³")
                self.assertEqual(context["horizontal_unit"], "metre")
                self.assertEqual(context["vertical_unit_source"], "assumed from projected CRS; DSM band unit is absent")
                self.assertEqual(context["vertical_datum"], "unknown")
                self.assertIn("assumed", context["limitation"])

            with rasterio.open(path, "r+") as dataset:
                dataset.units = ("furlong",)
            with rasterio.open(path) as dataset:
                with self.assertRaisesRegex(ValueError, "vertical unit is unsupported"):
                    get_volume_unit_context(dataset)

    def test_volume_unit_context_scales_horizontal_and_vertical_units_separately(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "feet-crs-metre-z.tif"
            with rasterio.open(
                path,
                "w",
                driver="GTiff",
                height=2,
                width=2,
                count=1,
                dtype="float32",
                crs="EPSG:2263",
                transform=from_origin(1000000, 200000, 1, 1),
            ) as dataset:
                dataset.write(np.ones((2, 2), dtype="float32"), 1)
                dataset.units = ("m",)

            with rasterio.open(path) as dataset:
                context = get_volume_unit_context(dataset)
            self.assertAlmostEqual(context["xy_to_m"], 1200.0 / 3937.0)
            self.assertEqual(context["z_to_m"], 1.0)
            self.assertEqual(context["vertical_unit_source"], "DSM band metadata")

    def test_volume_result_carries_unit_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "known-coverage-dsm.tif"
            surface = np.array(
                [[11, 12, 13, 14], [12, 13, 14, 15], [13, 14, 15, 16], [14, 15, 16, 17]],
                dtype="float32",
            )
            with rasterio.open(
                path,
                "w",
                driver="GTiff",
                height=4,
                width=4,
                count=1,
                dtype="float32",
                crs="EPSG:32615",
                transform=from_origin(500000, 4100004, 1, 1),
            ) as dataset:
                dataset.write(surface, 1)

            to_lonlat = Transformer.from_crs(32615, 4326, always_xy=True)
            projected_polygon = [
                (500000.1, 4100000.1),
                (500003.9, 4100000.1),
                (500003.9, 4100003.9),
                (500000.1, 4100003.9),
                (500000.1, 4100000.1),
            ]
            polygon = [
                [lon, lat]
                for lon, lat in (to_lonlat.transform(x, y) for x, y in projected_polygon)
            ]
            result = calc_volume(
                str(path), pts=polygon, pts_epsg=4326, base_method="highest"
            )

            self.assertGreater(result["output"], 0)
            self.assertEqual(result["unit_context"]["units"], "m³")
            self.assertEqual(result["unit_context"]["vertical_datum"], "unknown")
            self.assertIn("assumed", result["unit_context"]["limitation"])

    def test_volume_result_endpoint_preserves_numeric_output_and_adds_unit_context(self):
        unit_context = {
            "units": "m³",
            "vertical_unit_source": "assumed from projected CRS; DSM band unit is absent",
            "vertical_datum": "unknown",
            "limitation": "DSM vertical datum is unknown.",
        }

        class CompletedResult:
            def ready(self):
                return True

            def get(self):
                return {"output": 12.5, "unit_context": unit_context}

        completed = CompletedResult()
        with patch("app.api.workers.TestSafeAsyncResult", return_value=completed), patch(
            "worker.tasks.TestSafeAsyncResult", return_value=completed
        ):
            request = APIRequestFactory().get(
                "/volume/get/synthetic-celery-id/",
                HTTP_X_VOLUME_JOB_TOKEN=_volume_job_token(self.task.pk, "synthetic-celery-id"),
            )
            force_authenticate(request, user=self.user)
            response = TaskVolumeResult.as_view()(
                request,
                pk=str(self.task.pk),
                celery_task_id="synthetic-celery-id",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["output"], 12.5)
        self.assertEqual(response.data["unit_context"], unit_context)

    def test_volume_result_endpoint_denies_another_users_private_task(self):
        other_user = User.objects.get(username="testuser2")
        private_project = Project.objects.create(owner=other_user, name="foreign-private-volume-project")
        private_task = Task.objects.create(project=private_project, name="foreign-private-volume-task")

        response = self.client.get(
            "/api/plugins/measure/task/{}/volume/get/{}/".format(private_task.pk, uuid4())
        )

        self.assertEqual(response.status_code, 404)

    def test_volume_check_endpoint_denies_another_users_private_task(self):
        other_user = User.objects.get(username="testuser2")
        private_project = Project.objects.create(owner=other_user, name="foreign-private-check-project")
        private_task = Task.objects.create(project=private_project, name="foreign-private-check-task")

        response = self.client.get(
            "/api/plugins/measure/task/{}/volume/check/{}/".format(private_task.pk, uuid4())
        )

        self.assertEqual(response.status_code, 404)

    def test_volume_check_endpoint_polls_after_task_access_check(self):
        from rest_framework.response import Response
        from app.api.workers import CheckTask

        request = APIRequestFactory().get(
            "/volume/check/synthetic-celery-id/",
            HTTP_X_VOLUME_JOB_TOKEN=_volume_job_token(self.task.pk, "synthetic-celery-id"),
        )
        force_authenticate(request, user=self.user)
        with patch.object(CheckTask, "get", return_value=Response({"ready": False})) as poll:
            response = TaskVolumeCheck.as_view()(
                request,
                pk=str(self.task.pk),
                celery_task_id="synthetic-celery-id",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {"ready": False})
        poll.assert_called_once()

    def test_volume_result_rejects_a_job_token_bound_to_another_task(self):
        celery_task_id = str(uuid4())
        request = APIRequestFactory().get(
            "/volume/get/cross-task-job/",
            HTTP_X_VOLUME_JOB_TOKEN=_volume_job_token(uuid4(), celery_task_id),
        )
        force_authenticate(request, user=self.user)
        with patch("coreplugins.measure.api.GetTaskResult.get") as read_result:
            response = TaskVolumeResult.as_view()(
                request,
                pk=str(self.task.pk),
                celery_task_id=celery_task_id,
            )

        self.assertEqual(response.status_code, 404)
        read_result.assert_not_called()

    def test_volume_start_returns_task_bound_result_token(self):
        self.task.dsm_extent = Polygon.from_bbox((-93.1, 37.0, -93.0, 37.1))
        self.task.save(update_fields=["dsm_extent"])
        celery_task_id = str(uuid4())
        area = {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[-93.09, 37.01], [-93.08, 37.01], [-93.08, 37.02], [-93.09, 37.01]]],
            },
        }

        async_job = SimpleNamespace(task_id=celery_task_id)

        # Exercise the mounted endpoint through Django's test client; the
        # asynchronous calculation itself is mocked.
        with patch("coreplugins.measure.api.run_function_async", return_value=async_job):
            response = self.client.post(
                "/api/plugins/measure/task/{}/volume".format(self.task.pk),
                data=json.dumps({"area": area, "method": "triangulate"}),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["celery_task_id"], celery_task_id)
        self.assertEqual(
            signing.loads(body["result_token"], salt=VOLUME_JOB_TOKEN_SALT),
            {"task_id": str(self.task.pk), "celery_task_id": celery_task_id},
        )

    def test_volume_rejects_geographic_crs_without_linear_area_units(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "geographic-dsm.tif"
            with rasterio.open(
                path,
                "w",
                driver="GTiff",
                height=2,
                width=2,
                count=1,
                dtype="float32",
                crs="EPSG:4326",
                transform=from_origin(-93, 45, 0.0001, 0.0001),
            ) as dataset:
                dataset.write(np.ones((2, 2), dtype="float32"), 1)

            with rasterio.open(path) as dataset:
                with self.assertRaisesRegex(ValueError, "requires a projected CRS"):
                    get_volume_unit_context(dataset)

    def test_companion_upload_stages_a_closed_temporary_file(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "capture.mp4"
            source.write_bytes(b"closed-upload-source")

            class ClosedTemporaryUpload:
                name = "capture.mp4"

                def temporary_file_path(self):
                    return str(source)

            staged = _stage_companion_upload(ClosedTemporaryUpload())
            try:
                self.assertEqual(staged.suffix, ".mp4")
                self.assertEqual(staged.read_bytes(), b"closed-upload-source")
            finally:
                staged.unlink(missing_ok=True)

    def test_preparation_import_persists_path_free_frame_and_telemetry_review(self):
        frame_bytes = b"prepared-frame-content"
        frame_hash = hashlib.sha256(frame_bytes).hexdigest()
        manifest = {
            "schema_version": "1.1",
            "mode": "local",
            "georeferenced": False,
            "sampling": {
                "rule": "first decoded frame at or after each interval boundary",
                "interval_seconds": 1.0,
                "extraction_mode": "seek",
            },
            "frames": [
                {
                    "output_filename": "frame_000001.jpg",
                    "source_frame_index": 30,
                    "source_timestamp_seconds": 1.25,
                    "dimensions": {"width": 640, "height": 480},
                    "source_dimensions": {"width": 1920, "height": 1080},
                    "transformations": {"rotation": 0},
                    "sha256": frame_hash,
                    "output_path": "C:/private/companion/frames/frame_000001.jpg",
                }
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            bundle_path = Path(directory) / "prepared-input.zip"
            with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
                bundle.writestr("manifest.json", json.dumps(manifest))
                bundle.writestr("frames/frame_000001.jpg", frame_bytes)
                bundle.writestr("selection/advisory.json", json.dumps({
                    "schema_version": "astrakriti3d.selection-advisory.v1",
                    "status": "available",
                    "baseline": "R1",
                    "policy": "advisory_only_all_source_frames_retained",
                    "candidate_count": 1,
                    "recommended_count": 1,
                    "warnings": ["Experimental proxy metrics only."],
                    "rows": [{
                        "frame_number": 1,
                        "timestamp": 1.25,
                        "blur_score": 42.5,
                        "feature_count": 210,
                        "decision": "keep",
                        "rejection_reason": None,
                        "source_path": "C:/private/companion/frames/frame_000001.jpg",
                    }],
                }))

            task = Task.objects.create(
                project=self.project,
                name="Preparation evidence run",
                partial=True,
            )
            submission = AstrakritiSubmission.objects.create(
                idempotency_key=str(uuid4()),
                request_fingerprint="preparation-evidence-fingerprint",
                owner=self.user,
                project=self.project,
                task=task,
                task_name=task.name,
                state="reserved",
                source_mode="local",
                companion_job_id=str(uuid4()),
                preparation_state="completed",
            )

            class FakeCompanionClient:
                configured = True

                def preparation_status(self, job_id):
                    return {
                        "job_id": job_id,
                        "status": "completed",
                        "mode": "local",
                        "result": {
                            "source_video_sha256": "a" * 64,
                            "source_video": "C:/private/companion/source/capture.mp4",
                        },
                    }

                def download_bundle(self, job_id, destination):
                    destination = Path(destination)
                    destination.write_bytes(bundle_path.read_bytes())
                    return destination

            import_url = "/api/plugins/astrakriti3d/intake/{}/import/".format(submission.id)
            with patch(
                "coreplugins.astrakriti3d.api.AstrakritiCompanionClient",
                return_value=FakeCompanionClient(),
            ):
                imported = self.client.post(import_url)

            self.assertEqual(imported.status_code, 200, imported.content)
            self.assertTrue(imported.json()["imported"])
            imported_json = json.dumps(imported.json())
            self.assertNotIn("C:/private/companion", imported_json)
            self.assertEqual(imported.json()["metadata"]["frame_count"], 1)

            frame_review = self.client.get(
                "/api/plugins/astrakriti3d/preparation/task/{}/?view=frames&limit=1".format(task.id)
            )
            self.assertEqual(frame_review.status_code, 200)
            frame_payload = frame_review.json()
            self.assertEqual(frame_payload["status"], "available")
            self.assertEqual(frame_payload["total"], 1)
            self.assertEqual(frame_payload["items"][0]["timestamp_seconds"], 1.25)
            self.assertEqual(frame_payload["items"][0]["quality_status"], "measured")
            self.assertEqual(frame_payload["items"][0]["quality_metrics"]["blur_score"], 42.5)
            self.assertEqual(frame_payload["items"][0]["selection_recommendation"], "keep")
            self.assertEqual(frame_payload["selection"]["baseline"], "R1")
            self.assertEqual(frame_payload["selection"]["policy"], "advisory_only_all_source_frames_retained")
            self.assertTrue(frame_payload["items"][0]["preview_available"])
            self.assertNotIn("output_path", json.dumps(frame_payload))
            self.assertNotIn("source_path", json.dumps(frame_payload))

            telemetry_review = self.client.get(
                "/api/plugins/astrakriti3d/preparation/task/{}/?view=telemetry".format(task.id)
            )
            self.assertEqual(telemetry_review.status_code, 200)
            self.assertEqual(telemetry_review.json()["status"], "not_applicable")
            self.assertEqual(telemetry_review.json()["total"], 0)

    def test_georeferenced_review_exposes_real_associations_without_paths_or_raw_srt(self):
        frame_bytes = b"georeferenced-frame-content"
        frame_hash = hashlib.sha256(frame_bytes).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            extracted = Path(directory)
            frames_root = extracted / "frames"
            telemetry_root = extracted / "telemetry"
            frames_root.mkdir()
            telemetry_root.mkdir()
            frame_path = frames_root / "frame_000001.jpg"
            frame_path.write_bytes(frame_bytes)
            manifest = {
                "schema_version": "1.1",
                "mode": "georeferenced",
                "georeferenced": True,
                "sampling": {"interval_seconds": 1.0, "extraction_mode": "seek"},
                "frames": [
                    {
                        "output_filename": frame_path.name,
                        "source_frame_index": 30,
                        "source_timestamp_seconds": 1.25,
                        "dimensions": {"width": 640, "height": 480},
                        "sha256": frame_hash,
                        "output_path": "C:/private/companion/frames/frame_000001.jpg",
                    }
                ],
            }
            (extracted / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            report = {
                "schema_version": "phase3.telemetry.v1",
                "source_video": {"path": "C:/private/companion/source/capture.mp4", "sha256": "b" * 64},
                "srt": {
                    "sha256": "c" * 64,
                    "record_count": 1,
                    "valid_record_count": 1,
                    "invalid_record_count": 0,
                    "errors": [],
                    "duplicates": [],
                    "non_monotonic": [],
                    "gaps_seconds": [],
                    "altitude_units": "unknown",
                    "time_offset_seconds": 0,
                    "timestamp_range_seconds": [1.25, 1.25],
                },
                "association": {
                    "frame_count": 1,
                    "matched_count": 1,
                    "unmatched_count": 0,
                    "configured_tolerance_seconds": 0.5,
                },
                "warnings": ["Altitude meaning is unknown."],
                "assumptions": ["Subtitle cue start is video-relative time."],
                "unknowns": ["Altitude vertical datum/reference."],
            }
            (telemetry_root / "telemetry_report.json").write_text(json.dumps(report), encoding="utf-8")
            (telemetry_root / "association_manifest.json").write_text(
                json.dumps(
                    {
                        "schema_version": "phase3.telemetry.v1",
                        "rows": [
                            {
                                "frame_filename": frame_path.name,
                                "frame_timestamp_seconds": 1.25,
                                "matched_telemetry_timestamp_seconds": 1.25,
                                "signed_time_difference_seconds": 0.0,
                                "telemetry_record_id": "srt-000001",
                                "association_status": "matched",
                                "latitude": 47.5,
                                "longitude": -122.3,
                                "altitude": 122.0,
                                "heading": 90.0,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (telemetry_root / "telemetry_ordered.json").write_text(
                json.dumps(
                    [
                        {
                            "record_id": "srt-000001",
                            "cue_start_seconds": 1.25,
                            "wall_clock_time": "2026-09-18 12:00:01",
                            "latitude": 47.5,
                            "longitude": -122.3,
                            "altitude": 122.0,
                            "heading": 90.0,
                            "fields": {"speed": "5.2"},
                            "raw_text": "PRIVATE RAW SRT CONTENT",
                            "valid": True,
                            "diagnostics": [],
                        }
                    ]
                ),
                encoding="utf-8",
            )

            frames_document, telemetry_document = _preparation_review_documents(
                extracted,
                manifest,
                [frame_path],
                "georeferenced",
                {"result": {"source_video_sha256": "b" * 64}},
            )
            _write_task_preparation_review(self.task, frames_document, telemetry_document)

        endpoint = "/api/plugins/astrakriti3d/preparation/task/{}/".format(self.task.id)
        telemetry_response = self.client.get(endpoint + "?view=telemetry&limit=1")
        self.assertEqual(telemetry_response.status_code, 200)
        telemetry = telemetry_response.json()
        self.assertEqual(telemetry["status"], "available")
        self.assertEqual(telemetry["summary"]["matched_frame_count"], 1)
        self.assertEqual(telemetry["items"][0]["speed"], 5.2)
        self.assertEqual(telemetry["items"][0]["associated_frames"], ["frame_000001.jpg"])
        telemetry_json = json.dumps(telemetry)
        self.assertNotIn("C:/private/companion", telemetry_json)
        self.assertNotIn("PRIVATE RAW SRT CONTENT", telemetry_json)

        frame_response = self.client.get(endpoint + "?view=frames&association=matched")
        self.assertEqual(frame_response.status_code, 200)
        frame = frame_response.json()["items"][0]
        self.assertEqual(frame["telemetry"]["latitude"], 47.5)
        self.assertEqual(frame["telemetry"]["longitude"], -122.3)

        other_user = User.objects.get(username="testuser2")
        private_project = Project.objects.get(owner=other_user)
        private_task = Task.objects.create(project=private_project, name="private-evidence-task")
        private_response = self.client.get(
            "/api/plugins/astrakriti3d/preparation/task/{}/".format(private_task.id)
        )
        self.assertEqual(private_response.status_code, 404)

    def test_intake_reservation_reuses_the_same_native_task(self):
        endpoint = "/api/plugins/astrakriti3d/intake/reserve/"
        key = str(uuid4())
        payload = {
            "idempotency_key": key,
            "project_name": "Retry-safe Project",
            "task_name": "Retry-safe Run",
            "file_fingerprint": "a.jpg:10:1|b.jpg:10:1",
        }

        first = self.client.post(
            endpoint, data=json.dumps(payload), content_type="application/json"
        )
        self.assertEqual(first.status_code, 201)
        second = self.client.post(
            endpoint, data=json.dumps(payload), content_type="application/json"
        )
        self.assertEqual(second.status_code, 200)
        self.assertTrue(second.json()["reused"])
        self.assertEqual(first.json()["task_id"], second.json()["task_id"])
        self.assertEqual(
            AstrakritiSubmission.objects.filter(idempotency_key=key).count(), 1
        )
        self.assertEqual(
            Task.objects.filter(id=first.json()["task_id"]).count(), 1
        )

        conflict = dict(payload, task_name="A different run")
        response = self.client.post(
            endpoint, data=json.dumps(conflict), content_type="application/json"
        )
        self.assertEqual(response.status_code, 409)

    def test_intake_commit_is_idempotent_after_response_loss(self):
        endpoint = "/api/plugins/astrakriti3d/intake/reserve/"
        reservation = self.client.post(
            endpoint,
            data=json.dumps(
                {
                    "idempotency_key": str(uuid4()),
                    "project_name": "Commit Project",
                    "task_name": "Commit Run",
                    "file_fingerprint": "a.jpg:10:1",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(reservation.status_code, 201)
        body = reservation.json()
        task = Task.objects.get(pk=body["task_id"])
        Path(task.task_path()).mkdir(parents=True, exist_ok=True)
        Path(task.task_path("frame.jpg")).write_bytes(b"test image")

        commit_endpoint = "/api/plugins/astrakriti3d/intake/{}/commit/".format(
            body["submission_id"]
        )
        with patch("coreplugins.astrakriti3d.api.worker_tasks.process_task.delay") as delay:
            with patch(
                "coreplugins.astrakriti3d.api.transaction.on_commit",
                side_effect=lambda callback: callback(),
            ):
                first = self.client.post(commit_endpoint)
                second = self.client.post(commit_endpoint)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertFalse(first.json()["reused"])
        self.assertTrue(second.json()["reused"])
        self.assertEqual(delay.call_count, 1)
        self.assertFalse(Task.objects.get(pk=task.id).partial)

    def test_frame_selection_is_persisted_applied_and_commit_retry_is_safe(self):
        reservation = self.client.post(
            "/api/plugins/astrakriti3d/intake/reserve/",
            data=json.dumps({
                "idempotency_key": str(uuid4()),
                "project_id": str(self.project.id),
                "task_name": "Selected local frames",
                "file_fingerprint": "three-candidate-frames",
            }),
            content_type="application/json",
        )
        self.assertEqual(reservation.status_code, 201, reservation.content)
        identity = reservation.json()
        task = Task.objects.get(pk=identity["task_id"], partial=True)
        root = Path(task.task_path())
        root.mkdir(parents=True, exist_ok=True)
        contents = {
            "frame_000001.jpg": b"selected-one",
            "frame_000002.jpg": b"excluded-two",
            "frame_000003.jpg": b"selected-three",
        }
        for name, value in contents.items():
            Path(task.get_image_path(name)).write_bytes(value)

        selection_url = "/api/plugins/astrakriti3d/intake/{}/selection/".format(identity["submission_id"])
        initial = self.client.get(selection_url)
        self.assertEqual(initial.status_code, 200, initial.content)
        self.assertEqual(initial.json()["status"], "available")
        self.assertEqual(initial.json()["total"], 3)
        self.assertEqual(initial.json()["selected_filenames"], sorted(contents))

        selected = ["frame_000001.jpg", "frame_000003.jpg"]
        payload = {"strategy": "manual", "selected_filenames": selected}
        saved = self.client.post(selection_url, data=json.dumps(payload), content_type="application/json")
        repeated = self.client.post(selection_url, data=json.dumps(payload), content_type="application/json")
        self.assertEqual(saved.status_code, 200, saved.content)
        self.assertFalse(saved.json()["reused"])
        self.assertTrue(repeated.json()["reused"])
        self.assertEqual(self.client.get(selection_url).json()["selected_filenames"], selected)

        commit_url = "/api/plugins/astrakriti3d/intake/{}/commit/".format(identity["submission_id"])
        with patch("coreplugins.astrakriti3d.api.worker_tasks.process_task.delay") as delay:
            with patch("coreplugins.astrakriti3d.api.transaction.on_commit", side_effect=lambda callback: callback()):
                first = self.client.post(commit_url)
                retry = self.client.post(commit_url)

        self.assertEqual(first.status_code, 200, first.content)
        self.assertFalse(first.json()["reused"])
        self.assertTrue(retry.json()["reused"])
        self.assertEqual(delay.call_count, 1)
        self.assertFalse(Task.objects.get(pk=task.id).partial)
        self.assertEqual(Task.objects.get(pk=task.id).images_count, 2)
        self.assertEqual(sorted(p.name for p in root.glob("*.jpg")), selected)
        archived = Path(task.data_path("astrakriti3d", "excluded", "frame_000002.jpg"))
        self.assertEqual(archived.read_bytes(), contents["frame_000002.jpg"])
        saved_selection = AstrakritiSubmission.objects.get(pk=identity["submission_id"]).preparation_metadata["frame_selection"]
        self.assertTrue(saved_selection["applied"])
        self.assertEqual(saved_selection["selected_count"], 2)

    def test_georeferenced_selection_keeps_source_geo_and_filters_authoritative_geo(self):
        reservation = self.client.post(
            "/api/plugins/astrakriti3d/intake/reserve/",
            data=json.dumps({
                "idempotency_key": str(uuid4()),
                "project_id": str(self.project.id),
                "task_name": "Selected georeferenced frames",
                "file_fingerprint": "three-georeferenced-frames",
            }),
            content_type="application/json",
        )
        self.assertEqual(reservation.status_code, 201, reservation.content)
        identity = reservation.json()
        task = Task.objects.get(pk=identity["task_id"], partial=True)
        task_root = Path(task.task_path())
        task_root.mkdir(parents=True, exist_ok=True)
        names = ["frame_000001.jpg", "frame_000002.jpg", "frame_000003.jpg"]
        for index, name in enumerate(names, start=1):
            Path(task.get_image_path(name)).write_bytes(("frame-{}".format(index)).encode("ascii"))
        source_geo = "EPSG:4326\n{}\n{}\n{}\n".format(
            "frame_000001.jpg 2.000000000000 1.000000000000",
            "frame_000002.jpg 2.100000000000 1.100000000000",
            "frame_000003.jpg 2.200000000000 1.200000000000",
        ).encode("utf-8")
        Path(task.get_image_path("geo.txt")).write_bytes(source_geo)
        submission = AstrakritiSubmission.objects.get(pk=identity["submission_id"])
        submission.source_mode = "georeferenced"
        submission.preparation_state = "imported"
        submission.save(update_fields=("source_mode", "preparation_state", "updated_at"))

        selection_url = "/api/plugins/astrakriti3d/intake/{}/selection/".format(identity["submission_id"])
        selected = [names[0], names[2]]
        saved = self.client.post(
            selection_url,
            data=json.dumps({"strategy": "manual", "selected_filenames": selected}),
            content_type="application/json",
        )
        self.assertEqual(saved.status_code, 200, saved.content)
        archived_source_geo = Path(task.data_path("astrakriti3d", "source_geo.txt"))
        self.assertEqual(archived_source_geo.read_bytes(), source_geo)

        commit_url = "/api/plugins/astrakriti3d/intake/{}/commit/".format(identity["submission_id"])
        with patch("coreplugins.astrakriti3d.api.worker_tasks.process_task.delay"):
            committed = self.client.post(commit_url)
        self.assertEqual(committed.status_code, 200, committed.content)
        resulting_geo = Path(task.get_image_path("geo.txt")).read_text(encoding="utf-8").splitlines()
        self.assertEqual(resulting_geo, [
            "EPSG:4326",
            "frame_000001.jpg 2.000000000000 1.000000000000",
            "frame_000003.jpg 2.200000000000 1.200000000000",
        ])
        self.assertEqual(
            sorted(p.name for p in task_root.glob("*.jpg")),
            selected,
        )
        self.assertEqual(
            Path(task.data_path("astrakriti3d", "excluded", "frame_000002.jpg")).read_bytes(),
            b"frame-2",
        )

    def test_frame_selection_rejects_stale_images_and_other_owners(self):
        reservation = self.client.post(
            "/api/plugins/astrakriti3d/intake/reserve/",
            data=json.dumps({
                "idempotency_key": str(uuid4()),
                "project_id": str(self.project.id),
                "task_name": "Stale frame selection",
                "file_fingerprint": "two-candidate-frames",
            }),
            content_type="application/json",
        )
        identity = reservation.json()
        task = Task.objects.get(pk=identity["task_id"])
        Path(task.task_path()).mkdir(parents=True, exist_ok=True)
        for name in ("frame_000001.jpg", "frame_000002.jpg"):
            Path(task.get_image_path(name)).write_bytes(name.encode("ascii"))
        url = "/api/plugins/astrakriti3d/intake/{}/selection/".format(identity["submission_id"])
        saved = self.client.post(
            url,
            data=json.dumps({"strategy": "manual", "selected_filenames": ["frame_000001.jpg", "frame_000002.jpg"]}),
            content_type="application/json",
        )
        self.assertEqual(saved.status_code, 200, saved.content)
        Path(task.get_image_path("frame_000002.jpg")).write_bytes(b"changed after review")
        with patch("coreplugins.astrakriti3d.api.worker_tasks.process_task.delay") as delay:
            response = self.client.post("/api/plugins/astrakriti3d/intake/{}/commit/".format(identity["submission_id"]))
        self.assertEqual(response.status_code, 409, response.content)
        self.assertTrue(Task.objects.get(pk=task.id).partial)
        delay.assert_not_called()

        submission = AstrakritiSubmission.objects.get(pk=identity["submission_id"])
        submission.owner = User.objects.get(username="testuser2")
        submission.save(update_fields=("owner", "updated_at"))
        denied = self.client.get(url)
        self.assertEqual(denied.status_code, 404)

    @unittest.skipUnless(
        os.environ.get("ASTRAKRITI_COMPANION_TEST_ISOLATED") == "1"
        and os.environ.get("ASTRAKRITI_COMPANION_URL")
        and os.environ.get("ASTRAKRITI_COMPANION_TOKEN"),
        "requires explicit opt-in to a disposable isolated Astrakriti companion",
    )
    def test_live_companion_video_to_native_intake(self):
        """Exercise the real HTTP companion contract against an isolated test DB."""
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            self.skipTest("ffmpeg is unavailable in this test image")

        with tempfile.TemporaryDirectory(prefix="astrakriti-intake-e2e-") as directory:
            root = Path(directory)
            media_root = root / "media"
            media_tmp = root / "media-tmp"
            media_root.mkdir()
            media_tmp.mkdir()
            source_video = root / "synthetic-capture.mp4"
            source_srt = root / "synthetic-capture.srt"
            subprocess.run(
                [
                    ffmpeg,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    "testsrc2=size=640x480:rate=2:duration=8",
                    "-c:v",
                    "mpeg4",
                    "-q:v",
                    "5",
                    "-y",
                    str(source_video),
                ],
                check=True,
                capture_output=True,
                timeout=60,
            )
            source_srt.write_text(
                "\n\n".join(
                    "{0}\n00:00:{1:02d},000 --> 00:00:{1:02d},900\n"
                    "[latitude: {2:.6f}] [longitude: {3:.6f}] [altitude: 4.0]".format(
                        index + 1, index, 1.0 + index * 0.0001, 2.0 + index * 0.0001
                    )
                    for index in range(8)
                )
                + "\n",
                encoding="utf-8",
            )
            with override_settings(MEDIA_ROOT=str(media_root), MEDIA_TMP=str(media_tmp)):
                identity_key = str(uuid4())
                reserve = self.client.post(
                    "/api/plugins/astrakriti3d/intake/reserve/",
                    data=json.dumps(
                        {
                            "idempotency_key": identity_key,
                            "project_id": str(self.project.id),
                            "task_name": "Isolated companion acceptance",
                            "file_fingerprint": "synthetic-capture.mp4:{}:1|synthetic-capture.srt:{}:1".format(
                                source_video.stat().st_size, source_srt.stat().st_size
                            ),
                        }
                    ),
                    content_type="application/json",
                )
                self.assertEqual(reserve.status_code, 201, reserve.content)
                submission_id = reserve.json()["submission_id"]
                task_id = reserve.json()["task_id"]
                preparation_url = "/api/plugins/astrakriti3d/intake/{}/prepare/".format(
                    submission_id
                )

                response = self.client.post(
                    preparation_url,
                    {
                        "mode": "georeferenced",
                        "video": SimpleUploadedFile(
                            "synthetic-capture.mp4",
                            source_video.read_bytes(),
                            content_type="video/mp4",
                        ),
                        "srt": SimpleUploadedFile(
                            "synthetic-capture.srt",
                            source_srt.read_bytes(),
                            content_type="text/plain",
                        ),
                    },
                )
                self.assertEqual(response.status_code, 202, response.content)

                deadline = time.monotonic() + 120
                while time.monotonic() < deadline:
                    status_response = self.client.get(preparation_url)
                    self.assertEqual(status_response.status_code, 200, status_response.content)
                    state = status_response.json()["status"]
                    if state in {"completed", "failed", "cancelled", "recovery_required"}:
                        break
                    time.sleep(0.5)
                self.assertEqual(state, "completed", status_response.content)

                import_url = "/api/plugins/astrakriti3d/intake/{}/import/".format(
                    submission_id
                )
                imported = self.client.post(import_url)
                self.assertEqual(imported.status_code, 200, imported.content)
                self.assertTrue(imported.json()["imported"])
                self.assertEqual(imported.json()["frame_count"], 8)
                task = Task.objects.get(pk=task_id, project=self.project)
                self.assertEqual(task.images_count, 8)
                self.assertTrue(task.partial)  # stays reserved until explicit commit
                self.assertEqual(len(list(Path(task.task_path()).glob("*.jpg"))), 8)
                geo_path = Path(task.get_image_path("geo.txt"))
                self.assertTrue(geo_path.is_file())
                self.assertEqual(len(geo_path.read_text(encoding="utf-8").splitlines()), 9)

                repeated_import = self.client.post(import_url)
                self.assertEqual(repeated_import.status_code, 200)
                self.assertTrue(repeated_import.json()["reused"])

                commit_url = "/api/plugins/astrakriti3d/intake/{}/commit/".format(
                    submission_id
                )
                with patch("coreplugins.astrakriti3d.api.worker_tasks.process_task.delay") as delay:
                    with patch(
                        "coreplugins.astrakriti3d.api.transaction.on_commit",
                        side_effect=lambda callback: callback(),
                    ):
                        committed = self.client.post(commit_url)
                        repeated_commit = self.client.post(commit_url)
                self.assertEqual(committed.status_code, 200, committed.content)
                self.assertFalse(committed.json()["reused"])
                self.assertEqual(repeated_commit.status_code, 200)
                self.assertTrue(repeated_commit.json()["reused"])
                self.assertEqual(delay.call_count, 1)
                self.assertFalse(Task.objects.get(pk=task_id).partial)

                review = self.client.get(
                    "/api/plugins/astrakriti3d/preparation/task/{}/?view=frames".format(
                        task_id
                    )
                )
                self.assertEqual(review.status_code, 200, review.content)
                self.assertEqual(review.json()["status"], "available")
                self.assertEqual(review.json()["total"], 8)
                self.assertEqual(review.json()["items"][0]["telemetry"]["status"], "matched")
                telemetry = self.client.get(
                    "/api/plugins/astrakriti3d/preparation/task/{}/?view=telemetry".format(
                        task_id
                    )
                )
                self.assertEqual(telemetry.status_code, 200, telemetry.content)
                self.assertEqual(telemetry.json()["status"], "available")
                self.assertEqual(telemetry.json()["summary"]["matched_frame_count"], 8)

    def test_legacy_reconciliation_is_additive_explicit_and_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "jobs.sqlite3"
            connection = sqlite3.connect(source)
            connection.execute(
                "CREATE TABLE jobs (local_id TEXT PRIMARY KEY, project_id TEXT, task_id TEXT, "
                "fingerprint TEXT, image_manifest TEXT NOT NULL, options TEXT NOT NULL, "
                "state TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, "
                "progress REAL, diagnostics TEXT, artifacts TEXT NOT NULL, event_history TEXT NOT NULL)"
            )
            connection.execute(
                "INSERT INTO jobs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "legacy-job-1",
                    str(self.project.id),
                    str(self.task.id),
                    "fingerprint",
                    json.dumps([{"name": "frame.jpg", "sha256": "abc"}]),
                    json.dumps([]),
                    "completed",
                    "2026-09-18T00:00:00Z",
                    "2026-09-18T00:01:00Z",
                    1.0,
                    None,
                    "[]",
                    "[]",
                ),
            )
            connection.commit()
            connection.close()

            preview = io.StringIO()
            call_command("astrakriti_reconcile", "--source", str(source), stdout=preview)
            self.assertEqual(AstrakritiLegacyLink.objects.count(), 0)
            self.assertIn('"mode": "preview"', preview.getvalue())

            call_command("astrakriti_reconcile", "--source", str(source), "--apply", stdout=io.StringIO())
            link = AstrakritiLegacyLink.objects.get(legacy_id="legacy-job-1")
            self.assertEqual(link.mapping_state, AstrakritiLegacyLink.LINKED)
            self.assertEqual(link.project_id, self.project.id)
            self.assertEqual(link.task_id, self.task.id)
            self.assertEqual(link.legacy_payload["image_manifest"][0]["sha256"], "abc")

            call_command("astrakriti_reconcile", "--source", str(source), "--apply", stdout=io.StringIO())
            self.assertEqual(AstrakritiLegacyLink.objects.count(), 1)

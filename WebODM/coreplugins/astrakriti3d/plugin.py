from app.plugins import Menu, MountPoint, PluginBase

from .api import (
    AstrakritiHealthView,
    IntakeCommitView,
    IntakeFrameSelectionView,
    IntakePreparationImportView,
    IntakePreparationView,
    IntakeReservationView,
    LegacyReconciliationView,
    MeasurementDetailView,
    MeasurementExportView,
    MissionMetadataView,
    TaskPreparationEvidenceView,
    TaskMeasurementsView,
)
from .views import shell_view


class Plugin(PluginBase):
    """Mount the Astrakriti shell without replacing WebODM's native viewers."""

    def main_menu(self):
        return [Menu("ASTRAKRITI3D", "/astrakriti/overview/", "fa fa-crosshairs fa-fw")]

    def include_js_files(self):
        # This file only registers viewer hooks. It is intentionally safe to
        # load on native WebODM pages and activates only inside the Astrakriti
        # shell.
        return ["main.js"]

    def root_mount_points(self):
        return [
            MountPoint(r"^astrakriti/?$", shell_view, {"page": "overview"}),
            MountPoint(
                r"^astrakriti/(?P<page>overview|missions|reconstructions|artifacts|reports|processing|system|settings|new-reconstruction)/?$",
                shell_view,
            ),
            MountPoint(
                r"^astrakriti/missions/(?P<project_pk>[^/.]+)/?$",
                shell_view,
                {"page": "mission"},
            ),
            MountPoint(
                r"^astrakriti/missions/(?P<project_pk>[^/.]+)/(?P<page>overview|runs|artifacts|reports|files)/?$",
                shell_view,
            ),
            MountPoint(
                r"^astrakriti/runs/(?P<task_pk>[^/.]+)/?$",
                shell_view,
                {"page": "run"},
            ),
            MountPoint(
                r"^astrakriti/runs/(?P<task_pk>[^/.]+)/(?P<page>overview|processing|frames|telemetry|map|model|measurements|validation|reports|files)/?$",
                shell_view,
            ),
        ]

    def api_mount_points(self):
        return [
            MountPoint(r"health/?$", AstrakritiHealthView.as_view()),
            MountPoint(
                r"legacy/reconciliation/?$",
                LegacyReconciliationView.as_view(),
            ),
            MountPoint(
                r"mission/(?P<pk>[^/.]+)/metadata/?$",
                MissionMetadataView.as_view(),
            ),
            MountPoint(
                r"preparation/task/(?P<pk>[^/.]+)/?$",
                TaskPreparationEvidenceView.as_view(),
            ),
            MountPoint(r"intake/reserve/?$", IntakeReservationView.as_view()),
            MountPoint(
                r"intake/(?P<submission_id>[^/.]+)/selection/?$",
                IntakeFrameSelectionView.as_view(),
            ),
            MountPoint(
                r"intake/(?P<submission_id>[^/.]+)/commit/?$",
                IntakeCommitView.as_view(),
            ),
            MountPoint(
                r"intake/(?P<submission_id>[^/.]+)/prepare/?$",
                IntakePreparationView.as_view(),
            ),
            MountPoint(
                r"intake/(?P<submission_id>[^/.]+)/import/?$",
                IntakePreparationImportView.as_view(),
            ),
            MountPoint(r"measurements/task/(?P<pk>[^/.]+)/?$", TaskMeasurementsView.as_view()),
            MountPoint(
                r"measurements/task/(?P<pk>[^/.]+)/export/?$",
                MeasurementExportView.as_view(),
            ),
            MountPoint(
                r"measurements/task/(?P<pk>[^/.]+)/(?P<measurement_id>[^/.]+)/?$",
                MeasurementDetailView.as_view(),
            ),
        ]

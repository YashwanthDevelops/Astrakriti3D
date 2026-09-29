"""Safely reconcile legacy Astrakriti records with native WebODM identities."""

import json
import sqlite3
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from app.models import AstrakritiLegacyLink, Project, Task


JSON_COLUMNS = {
    "input_hashes",
    "reconstruction_config",
    "image_manifest",
    "options",
    "diagnostics",
    "artifacts",
    "event_history",
}


def _json_value(value):
    if isinstance(value, (bytes, bytearray)):
        return value.hex()
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return value
    return value


def _payload(row):
    return {
        key: _json_value(value) if key in JSON_COLUMNS else value
        for key, value in dict(row).items()
    }


def _tables(connection):
    return {
        row[0]
        for row in connection.execute(
            "select name from sqlite_master where type = 'table'"
        )
    }


def _rows_from_source(source):
    """Yield normalized records without mutating the source SQLite database."""

    source = Path(source).resolve()
    if not source.is_file():
        raise CommandError("Legacy source does not exist: {}".format(source))

    try:
        connection = sqlite3.connect(str(source))
        connection.row_factory = sqlite3.Row
        tables = _tables(connection)
        found = False

        if "missions" in tables:
            found = True
            for row in connection.execute("select * from missions order by created_at, mission_id"):
                data = _payload(row)
                yield {
                    "source_path": str(source),
                    "entity_type": AstrakritiLegacyLink.MISSION,
                    "legacy_id": str(row["mission_id"]),
                    "legacy_parent_id": "",
                    "legacy_label": str(row["name"] or row["mission_id"]),
                    "legacy_status": "",
                    "project_hint": data.get("project_id"),
                    "task_hint": data.get("task_id"),
                    "payload": data,
                }

        if "runs" in tables:
            found = True
            artifacts = {}
            evidence = {}
            if "artifacts" in tables:
                for row in connection.execute("select * from artifacts"):
                    artifacts.setdefault(str(row["run_id"]), []).append(_payload(row))
            if "evidence" in tables:
                for row in connection.execute("select * from evidence"):
                    evidence.setdefault(str(row["owner_id"]), []).append(_payload(row))
            for row in connection.execute("select * from runs order by created_at, run_id"):
                data = _payload(row)
                run_id = str(row["run_id"])
                run_artifacts = artifacts.get(run_id, [])
                data["artifacts"] = run_artifacts
                artifact_ids = [str(item.get("artifact_id")) for item in run_artifacts]
                data["evidence"] = evidence.get(run_id, []) + [
                    item
                    for artifact_id in artifact_ids
                    for item in evidence.get(artifact_id, [])
                ]
                yield {
                    "source_path": str(source),
                    "entity_type": AstrakritiLegacyLink.RUN,
                    "legacy_id": run_id,
                    "legacy_parent_id": str(row["mission_id"] or ""),
                    "legacy_label": str(row["label"] or run_id),
                    "legacy_status": str(row["status"] or ""),
                    "project_hint": data.get("project_id"),
                    "task_hint": data.get("webodm_task_id"),
                    "payload": data,
                }

        if "jobs" in tables:
            found = True
            for row in connection.execute("select * from jobs order by created_at, local_id"):
                data = _payload(row)
                job_id = str(row["local_id"])
                yield {
                    "source_path": str(source),
                    "entity_type": AstrakritiLegacyLink.JOB,
                    "legacy_id": job_id,
                    "legacy_parent_id": "",
                    "legacy_label": job_id,
                    "legacy_status": str(row["state"] or ""),
                    "project_hint": data.get("project_id"),
                    "task_hint": data.get("task_id"),
                    "payload": data,
                }

        if not found:
            raise CommandError(
                "Legacy source has no supported missions, runs, or jobs tables: {}".format(source)
            )
    except sqlite3.DatabaseError as exc:
        raise CommandError("Cannot read legacy SQLite source {}: {}".format(source, exc)) from exc
    finally:
        if "connection" in locals():
            connection.close()


def _load_identity_map(path):
    if path is None:
        return {}
    path = Path(path).resolve()
    if not path.is_file():
        raise CommandError("Identity map does not exist: {}".format(path))
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CommandError("Identity map is not valid JSON: {}".format(path)) from exc
    if not isinstance(value, dict):
        raise CommandError("Identity map must contain a JSON object.")
    return value


def _mapped_value(identity_map, section, key):
    values = identity_map.get(section, {})
    if not isinstance(values, dict):
        return None
    value = values.get(str(key))
    return str(value) if value not in (None, "") else None


def _native_project(value):
    if value in (None, ""):
        return None
    try:
        return Project.objects.get(pk=value, deleting=False)
    except (Project.DoesNotExist, TypeError, ValueError):
        return None


def _native_task(value):
    if value in (None, ""):
        return None
    try:
        return Task.objects.select_related("project").get(pk=value)
    except (Task.DoesNotExist, TypeError, ValueError):
        return None


def _resolve(record, identity_map, existing=None):
    entity_type = record["entity_type"]
    legacy_id = record["legacy_id"]
    project_hint = (
        _mapped_value(identity_map, "missions", legacy_id)
        if entity_type == AstrakritiLegacyLink.MISSION
        else _mapped_value(identity_map, "projects", record.get("project_hint"))
        or record.get("project_hint")
    ) or record.get("project_hint")
    task_hint = (
        _mapped_value(identity_map, "runs", legacy_id)
        if entity_type == AstrakritiLegacyLink.RUN
        else _mapped_value(identity_map, "jobs", legacy_id)
        if entity_type == AstrakritiLegacyLink.JOB
        else record.get("task_hint")
    ) or record.get("task_hint")

    project = _native_project(project_hint)
    task = _native_task(task_hint)
    reasons = []

    if task is not None:
        if project_hint not in (None, "") and str(task.project_id) != str(project_hint):
            reasons.append("task_project_mismatch")
        project = task.project
    elif project_hint not in (None, ""):
        reasons.append("project_identity_not_found")

    if entity_type == AstrakritiLegacyLink.MISSION and task is not None:
        reasons.append("mission_task_identity_not_allowed")
        task = None
    if entity_type in (AstrakritiLegacyLink.RUN, AstrakritiLegacyLink.JOB) and task is None:
        reasons.append("task_identity_not_found")

    if not reasons and (
        project is None
        if entity_type == AstrakritiLegacyLink.MISSION
        else task is None
    ):
        reasons.append("no_exact_native_identity")

    state = AstrakritiLegacyLink.LINKED if not reasons else AstrakritiLegacyLink.RECONCILIATION_REQUIRED

    if existing is not None and existing.mapping_state == AstrakritiLegacyLink.LINKED and reasons:
        # A later dry run must not silently detach a previously reconciled link
        # merely because the source hint is temporarily unavailable.
        project = existing.project
        task = existing.task
        state = AstrakritiLegacyLink.LINKED
        reasons.append("previous_link_preserved")

    if task is not None:
        competing = AstrakritiLegacyLink.objects.filter(
            task=task,
            mapping_state=AstrakritiLegacyLink.LINKED,
        )
        if existing is not None:
            competing = competing.exclude(pk=existing.pk)
        if competing.exists():
            state = AstrakritiLegacyLink.CONFLICT
            reasons.append("task_already_linked_to_another_legacy_record")
    if entity_type == AstrakritiLegacyLink.MISSION and project is not None:
        competing = AstrakritiLegacyLink.objects.filter(
            project=project,
            entity_type=AstrakritiLegacyLink.MISSION,
            mapping_state=AstrakritiLegacyLink.LINKED,
        )
        if existing is not None:
            competing = competing.exclude(pk=existing.pk)
        if competing.exists():
            state = AstrakritiLegacyLink.CONFLICT
            reasons.append("project_already_linked_to_another_legacy_mission")

    return {
        "project": project,
        "task": task,
        "mapping_state": state,
        "reconciliation": {
            "project_hint": str(project_hint) if project_hint not in (None, "") else None,
            "task_hint": str(task_hint) if task_hint not in (None, "") else None,
            "reasons": reasons,
            "method": "explicit_identity_map_or_exact_native_id",
        },
    }


def _summary_item(record, resolution):
    return {
        "source_path": record["source_path"],
        "entity_type": record["entity_type"],
        "legacy_id": record["legacy_id"],
        "mapping_state": resolution["mapping_state"],
        "project_id": str(resolution["project"].id) if resolution["project"] else None,
        "task_id": str(resolution["task"].id) if resolution["task"] else None,
        "reasons": resolution["reconciliation"]["reasons"],
    }


class Command(BaseCommand):
    help = "Preview or apply an additive Astrakriti legacy-to-WebODM reconciliation."

    def add_arguments(self, parser):
        parser.add_argument(
            "--source",
            action="append",
            required=True,
            help="Legacy SQLite path; repeat for ProductStore and JobStore sources.",
        )
        parser.add_argument(
            "--identity-map",
            help="JSON file with explicit missions/runs/jobs/projects identity mappings.",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Persist links. Without this flag the command is a read-only preview.",
        )

    def handle(self, *args, **options):
        identity_map = _load_identity_map(options.get("identity_map"))
        records = []
        for source in options["source"]:
            records.extend(_rows_from_source(source))

        summary = {
            "mode": "apply" if options["apply"] else "preview",
            "records": len(records),
            "created": 0,
            "updated": 0,
            "linked": 0,
            "reconciliation_required": 0,
            "conflict": 0,
            "items": [],
        }

        for record in records:
            existing = AstrakritiLegacyLink.objects.filter(
                source_path=record["source_path"],
                entity_type=record["entity_type"],
                legacy_id=record["legacy_id"],
            ).first()
            resolution = _resolve(record, identity_map, existing=existing)
            summary[resolution["mapping_state"]] += 1
            if len(summary["items"]) < 100:
                summary["items"].append(_summary_item(record, resolution))

            if not options["apply"]:
                continue

            defaults = {
                "legacy_parent_id": record["legacy_parent_id"],
                "legacy_label": record["legacy_label"],
                "legacy_status": record["legacy_status"],
                "mapping_state": resolution["mapping_state"],
                "project": resolution["project"],
                "task": resolution["task"],
                "legacy_payload": record["payload"],
                "reconciliation": resolution["reconciliation"],
            }
            with transaction.atomic():
                _, created = AstrakritiLegacyLink.objects.update_or_create(
                    source_path=record["source_path"],
                    entity_type=record["entity_type"],
                    legacy_id=record["legacy_id"],
                    defaults=defaults,
                )
            summary["created" if created else "updated"] += 1

        self.stdout.write(json.dumps(summary, indent=2, sort_keys=True, default=str))

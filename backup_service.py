from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from pathlib import PurePosixPath
from typing import Any

import db


BACKUP_FORMAT = "intopia-dss-cloud-backup"
BACKUP_VERSION = 1
APP_VERSION = "1.9.1-data-loading-hotfix"


class BackupError(ValueError):
    pass


def _safe_archive_name(name: str) -> str:
    clean = re.sub(r"[^\w.\-\u0590-\u05FF]+", "_", PurePosixPath(name or "file").name)
    return (clean[:160] or "file").strip(".") or "file"


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def create_backup() -> tuple[bytes, dict[str, Any]]:
    database = db.export_all_data()
    manifest: dict[str, Any] = {
        "format": BACKUP_FORMAT,
        "format_version": BACKUP_VERSION,
        "app_version": APP_VERSION,
        "created_at": db.utc_now(),
        "table_counts": {table: len(rows) for table, rows in database.items()},
        "files": [],
    }

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for record in database.get("uploads", []):
            storage_path = str(record.get("storage_path") or "")
            if not storage_path:
                raise BackupError(f"Upload {record.get('id')} has no Storage path.")
            content = db.storage_download(storage_path)
            actual_hash = _sha256(content)
            expected_hash = str(record.get("sha256") or "")
            if expected_hash and expected_hash != actual_hash:
                raise BackupError(f"Checksum mismatch for {record.get('original_name')}; backup stopped.")
            archive_name = f"files/{record.get('id')}/{_safe_archive_name(str(record.get('original_name') or 'file'))}"
            archive.writestr(archive_name, content)
            manifest["files"].append(
                {
                    "record_id": str(record.get("id")),
                    "archive_name": archive_name,
                    "storage_path": storage_path,
                    "size_bytes": len(content),
                    "sha256": actual_hash,
                    "mime_type": record.get("mime_type") or "application/octet-stream",
                }
            )

        archive.writestr("database.json", json.dumps(database, ensure_ascii=False, indent=2, default=str))
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2, default=str))

    return output.getvalue(), manifest


def _validate_member_name(name: str) -> None:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "\\" in name:
        raise BackupError(f"Unsafe ZIP member: {name}")


def _load_backup(content: bytes, max_uncompressed_bytes: int) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]], dict[str, bytes]]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(content), "r")
    except zipfile.BadZipFile as exc:
        raise BackupError("The restore file is not a valid ZIP backup.") from exc

    with archive:
        infos = archive.infolist()
        total_size = sum(info.file_size for info in infos)
        if total_size > max_uncompressed_bytes:
            raise BackupError("The uncompressed backup exceeds the configured restore limit.")
        for info in infos:
            _validate_member_name(info.filename)
        names = {info.filename for info in infos}
        if not {"manifest.json", "database.json"}.issubset(names):
            raise BackupError("The backup is missing manifest.json or database.json.")
        try:
            manifest = json.loads(archive.read("manifest.json"))
            database = json.loads(archive.read("database.json"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise BackupError("The backup metadata is invalid.") from exc

        if manifest.get("format") != BACKUP_FORMAT or manifest.get("format_version") != BACKUP_VERSION:
            raise BackupError("Unsupported backup format or version.")
        if not isinstance(database, dict):
            raise BackupError("database.json must contain a JSON object.")

        normalized: dict[str, list[dict[str, Any]]] = {}
        for table, rows in database.items():
            if table not in db.TABLES:
                raise BackupError(f"Unsupported table in backup: {table}")
            if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                raise BackupError(f"Invalid rows for table: {table}")
            normalized[table] = rows
        for table in db.TABLES:
            normalized.setdefault(table, [])

        files: dict[str, bytes] = {}
        seen_ids: set[str] = set()
        for entry in manifest.get("files", []):
            record_id = str(entry.get("record_id") or "")
            archive_name = str(entry.get("archive_name") or "")
            if not record_id or record_id in seen_ids or archive_name not in names:
                raise BackupError("The backup file manifest is inconsistent.")
            file_content = archive.read(archive_name)
            if len(file_content) != int(entry.get("size_bytes") or -1):
                raise BackupError(f"Size mismatch for {archive_name}.")
            if _sha256(file_content) != str(entry.get("sha256") or ""):
                raise BackupError(f"Checksum mismatch for {archive_name}.")
            files[record_id] = file_content
            seen_ids.add(record_id)

        upload_ids = {str(row.get("id")) for row in normalized.get("uploads", [])}
        if upload_ids != set(files):
            raise BackupError("Every upload metadata record must have exactly one file in the backup.")
        return manifest, normalized, files


def restore_backup(content: bytes, *, mode: str, max_uncompressed_bytes: int) -> dict[str, Any]:
    if mode not in {"replace", "merge"}:
        raise BackupError("Restore mode must be 'replace' or 'merge'.")
    manifest, database, files = _load_backup(content, max_uncompressed_bytes)
    upload_rows = database.get("uploads", [])
    upload_by_id = {str(row["id"]): row for row in upload_rows}

    # Validate and upload all objects before changing database rows.
    for entry in manifest.get("files", []):
        record_id = str(entry["record_id"])
        row = upload_by_id[record_id]
        db.storage_upload(
            str(row["storage_path"]),
            files[record_id],
            str(row.get("mime_type") or "application/octet-stream"),
            upsert=True,
        )

    if mode == "replace":
        incoming_paths = {str(row.get("storage_path") or "") for row in upload_rows}
        for current in db.list_uploads():
            old_path = str(current.get("storage_path") or "")
            if old_path and old_path not in incoming_paths:
                try:
                    db.storage_delete(old_path)
                except Exception:
                    pass
        db.clear_all_tables()

    restore_order = [
        "settings",
        "rule_sources",
        "rulebook_versions",
        "rules",
        "reference_area_product",
        "market_research_catalog",
        "strategy_principles",
        "milestones",
        "quarter_finance",
        "finance_by_area",
        "operations",
        "facts",
        "uploads",
        "strategy_profiles",
        "decisions",
        "scenarios",
        "strategic_assessments",
        "research_results",
        "report_imports",
        "scenario_portfolios",
        "quarter_snapshots",
        "tests",
        "research_plan",
        "agent_threads",
        "agent_messages",
        "rule_conflicts",
        "document_chunks",
        "ai_runs",
        "forecasts",
        "forecast_evaluations",
        "calibration_proposals",
        "decision_packs",
        "recommendation_evidence",
        "evidence_gate_runs",
        "optimization_runs",
        "digital_twin_snapshots",
        "digital_twin_runs",
        "market_intelligence_runs",
        "decision_sessions",
        "decision_votes",
        "audit_log",
    ]
    counts: dict[str, int] = {}
    for table in restore_order:
        counts[table] = db.restore_table_rows(table, database.get(table, []))

    db.init_db()
    db.audit(
        "restore",
        "backup",
        details={"mode": mode, "backup_created_at": manifest.get("created_at"), "records": sum(counts.values())},
    )
    return {
        "status": "ok",
        "mode": mode,
        "backup_created_at": manifest.get("created_at"),
        "restored_records": sum(counts.values()),
        "restored_files": len(files),
        "table_counts": counts,
    }

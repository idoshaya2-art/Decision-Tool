from __future__ import annotations

import copy
import threading
import uuid
from abc import ABC, abstractmethod
from functools import lru_cache
from typing import Any, Iterable

from config import AppConfig, get_config


class CloudConfigurationError(RuntimeError):
    pass


class CloudStore(ABC):
    @abstractmethod
    def select(
        self,
        table: str,
        filters: dict[str, Any] | None = None,
        *,
        order: str | None = None,
        descending: bool = False,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def insert(self, table: str, row: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def upsert(self, table: str, rows: dict[str, Any] | list[dict[str, Any]], on_conflict: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def update(self, table: str, filters: dict[str, Any], values: dict[str, Any]) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def delete(self, table: str, filters: dict[str, Any]) -> None:
        raise NotImplementedError

    @abstractmethod
    def clear_table(self, table: str, key_columns: Iterable[str]) -> None:
        raise NotImplementedError

    @abstractmethod
    def upload_file(self, path: str, content: bytes, content_type: str, *, upsert: bool = False) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def download_file(self, path: str) -> bytes:
        raise NotImplementedError

    @abstractmethod
    def delete_file(self, path: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def health(self) -> dict[str, Any]:
        raise NotImplementedError


class SupabaseCloudStore(CloudStore):
    def __init__(self, config: AppConfig | None = None):
        self.config = config or get_config()
        errors = self.config.validation_errors()
        if errors:
            raise CloudConfigurationError(" ".join(errors))
        try:
            from supabase import Client, create_client
            from supabase.client import ClientOptions
        except ImportError as exc:
            raise CloudConfigurationError("The 'supabase' package is not installed.") from exc
        self.client: Client = create_client(
            self.config.supabase_url,
            self.config.supabase_secret_key,
            options=ClientOptions(
                auto_refresh_token=False,
                persist_session=False,
                postgrest_client_timeout=30,
                storage_client_timeout=60,
                schema="public",
            ),
        )
        self.bucket = self.config.supabase_bucket

    def select(
        self,
        table: str,
        filters: dict[str, Any] | None = None,
        *,
        order: str | None = None,
        descending: bool = False,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        query = self.client.table(table).select("*")
        for key, value in (filters or {}).items():
            query = query.eq(key, value)
        if order:
            query = query.order(order, desc=descending)
        if limit is not None:
            query = query.limit(limit)
        return list(query.execute().data or [])

    def insert(self, table: str, row: dict[str, Any]) -> dict[str, Any]:
        data = self.client.table(table).insert(row).execute().data or []
        if not data:
            raise RuntimeError(f"Insert into {table} returned no row.")
        return dict(data[0])

    def upsert(self, table: str, rows: dict[str, Any] | list[dict[str, Any]], on_conflict: str) -> list[dict[str, Any]]:
        data = self.client.table(table).upsert(rows, on_conflict=on_conflict).execute().data or []
        return [dict(row) for row in data]

    def update(self, table: str, filters: dict[str, Any], values: dict[str, Any]) -> list[dict[str, Any]]:
        query = self.client.table(table).update(values)
        for key, value in filters.items():
            query = query.eq(key, value)
        return [dict(row) for row in (query.execute().data or [])]

    def delete(self, table: str, filters: dict[str, Any]) -> None:
        query = self.client.table(table).delete()
        for key, value in filters.items():
            query = query.eq(key, value)
        query.execute()

    def clear_table(self, table: str, key_columns: Iterable[str]) -> None:
        keys = tuple(key_columns)
        rows = self.client.table(table).select(",".join(keys)).execute().data or []
        for row in rows:
            self.delete(table, {key: row[key] for key in keys})

    def upload_file(self, path: str, content: bytes, content_type: str, *, upsert: bool = False) -> dict[str, Any]:
        result = self.client.storage.from_(self.bucket).upload(
            path=path,
            file=content,
            file_options={
                "content-type": content_type or "application/octet-stream",
                "cache-control": "3600",
                "upsert": str(upsert).lower(),
            },
        )
        if isinstance(result, dict):
            return result
        return {"path": getattr(result, "path", path), "full_path": getattr(result, "full_path", "")}

    def download_file(self, path: str) -> bytes:
        result = self.client.storage.from_(self.bucket).download(path)
        return bytes(result)

    def delete_file(self, path: str) -> None:
        self.client.storage.from_(self.bucket).remove([path])

    def health(self) -> dict[str, Any]:
        self.client.table("settings").select("id").limit(1).execute()
        self.client.storage.get_bucket(self.bucket)
        return {"database": "ok", "storage": "ok", "storage_bucket": self.bucket}


UUID_TABLES = {
    "operations",
    "facts",
    "uploads",
    "decisions",
    "scenarios",
    "tests",
    "research_plan",
    "audit_log",
    "report_imports",
    "research_results",
    "scenario_portfolios",
    "agent_threads",
    "agent_messages",
}


class InMemoryCloudStore(CloudStore):
    """Test-only implementation with the same semantics as the cloud adapter."""

    def __init__(self, bucket: str = "intopia-files"):
        self.bucket = bucket
        self.tables: dict[str, list[dict[str, Any]]] = {}
        self.files: dict[str, bytes] = {}
        self._lock = threading.RLock()

    def select(
        self,
        table: str,
        filters: dict[str, Any] | None = None,
        *,
        order: str | None = None,
        descending: bool = False,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        with self._lock:
            rows = [copy.deepcopy(row) for row in self.tables.get(table, [])]
        for key, value in (filters or {}).items():
            rows = [row for row in rows if row.get(key) == value]
        if order:
            rows.sort(key=lambda row: (row.get(order) is None, str(row.get(order, ""))), reverse=descending)
        return rows[:limit] if limit is not None else rows

    def insert(self, table: str, row: dict[str, Any]) -> dict[str, Any]:
        new_row = copy.deepcopy(row)
        if table in UUID_TABLES and not new_row.get("id"):
            new_row["id"] = str(uuid.uuid4())
        with self._lock:
            self.tables.setdefault(table, []).append(new_row)
        return copy.deepcopy(new_row)

    def upsert(self, table: str, rows: dict[str, Any] | list[dict[str, Any]], on_conflict: str) -> list[dict[str, Any]]:
        incoming = [rows] if isinstance(rows, dict) else rows
        keys = [key.strip() for key in on_conflict.split(",") if key.strip()]
        results: list[dict[str, Any]] = []
        with self._lock:
            target = self.tables.setdefault(table, [])
            for raw in incoming:
                row = copy.deepcopy(raw)
                if table in UUID_TABLES and not row.get("id"):
                    row["id"] = str(uuid.uuid4())
                existing = next((item for item in target if all(item.get(key) == row.get(key) for key in keys)), None)
                if existing is None:
                    target.append(row)
                    results.append(copy.deepcopy(row))
                else:
                    existing.update(row)
                    results.append(copy.deepcopy(existing))
        return results

    def update(self, table: str, filters: dict[str, Any], values: dict[str, Any]) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        with self._lock:
            for row in self.tables.get(table, []):
                if all(row.get(key) == value for key, value in filters.items()):
                    row.update(copy.deepcopy(values))
                    results.append(copy.deepcopy(row))
        return results

    def delete(self, table: str, filters: dict[str, Any]) -> None:
        with self._lock:
            self.tables[table] = [
                row for row in self.tables.get(table, []) if not all(row.get(key) == value for key, value in filters.items())
            ]

    def clear_table(self, table: str, key_columns: Iterable[str]) -> None:
        with self._lock:
            self.tables[table] = []

    def upload_file(self, path: str, content: bytes, content_type: str, *, upsert: bool = False) -> dict[str, Any]:
        with self._lock:
            if path in self.files and not upsert:
                raise RuntimeError("Asset already exists")
            self.files[path] = bytes(content)
        return {"path": path, "full_path": f"{self.bucket}/{path}"}

    def download_file(self, path: str) -> bytes:
        with self._lock:
            if path not in self.files:
                raise FileNotFoundError(path)
            return bytes(self.files[path])

    def delete_file(self, path: str) -> None:
        with self._lock:
            self.files.pop(path, None)

    def health(self) -> dict[str, Any]:
        return {"database": "ok", "storage": "ok", "storage_bucket": self.bucket, "mode": "memory-test"}


_store_override: CloudStore | None = None


@lru_cache(maxsize=1)
def _configured_store() -> CloudStore:
    config = get_config()
    if config.backend == "memory":
        return InMemoryCloudStore(config.supabase_bucket)
    return SupabaseCloudStore(config)


def get_store() -> CloudStore:
    return _store_override or _configured_store()


def set_store_for_tests(store: CloudStore | None) -> None:
    global _store_override
    _store_override = store


def reset_store_cache() -> None:
    global _store_override
    _store_override = None
    _configured_store.cache_clear()

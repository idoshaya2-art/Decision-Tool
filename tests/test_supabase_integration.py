from __future__ import annotations

import os
import uuid

import pytest


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_SUPABASE_INTEGRATION") != "1",
    reason="Set RUN_SUPABASE_INTEGRATION=1 with Supabase server credentials to run.",
)


def test_real_supabase_database_and_storage_persist_across_clients():
    from cloud import SupabaseCloudStore
    from config import AppConfig

    config = AppConfig.from_env()
    first = SupabaseCloudStore(config)
    token = uuid.uuid4().hex
    fact = first.insert(
        "facts",
        {
            "quarter": "Q1",
            "source_type": "integration-test",
            "metric": f"persistence-{token}",
            "created_at": "2026-01-01T00:00:00+00:00",
        },
    )
    path = f"integration-tests/{token}.txt"
    first.upload_file(path, token.encode(), "text/plain")

    try:
        second = SupabaseCloudStore(config)
        rows = second.select("facts", {"id": fact["id"]})
        assert rows[0]["metric"] == f"persistence-{token}"
        assert second.download_file(path) == token.encode()
    finally:
        first.delete("facts", {"id": fact["id"]})
        first.delete_file(path)

from __future__ import annotations

import pytest

import db


class MissingTableStore:
    def select(self, *args, **kwargs):
        raise RuntimeError(
            "PGRST205: Could not find the table 'public.market_intelligence_runs' in the schema cache"
        )


class BrokenStore:
    def select(self, *args, **kwargs):
        raise RuntimeError("network unavailable")


def test_optional_select_treats_only_missing_schema_table_as_empty(monkeypatch):
    monkeypatch.setattr(db, "_store", lambda: MissingTableStore())
    assert db._optional_select("market_intelligence_runs") == []


def test_optional_select_does_not_hide_operational_errors(monkeypatch):
    monkeypatch.setattr(db, "_store", lambda: BrokenStore())
    with pytest.raises(RuntimeError, match="network unavailable"):
        db._optional_select("market_intelligence_runs")

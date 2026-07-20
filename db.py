from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Iterable

from cloud import CloudStore, get_store
from seed_data import AREA_PRODUCT_DEFAULTS, MARKET_RESEARCH, MILESTONES, QUARTERS, STRATEGY_PRINCIPLES
from analytics import DEFAULT_SCORE_MODEL
from rulebook import CANONICAL_RULES, RULEBOOK_STATUS, RULEBOOK_VERSION, RULE_SOURCES


TABLES = [
    "settings",
    "reference_area_product",
    "quarter_finance",
    "operations",
    "facts",
    "uploads",
    "decisions",
    "scenarios",
    "tests",
    "market_research_catalog",
    "research_plan",
    "strategy_principles",
    "milestones",
    "audit_log",
    "finance_by_area",
    "report_imports",
    "research_results",
    "strategy_profiles",
    "strategic_assessments",
    "scenario_portfolios",
    "quarter_snapshots",
    "agent_threads",
    "agent_messages",
    "rule_sources",
    "rulebook_versions",
    "rules",
    "rule_conflicts",
    "document_chunks",
    "ai_runs",
    "recommendation_evidence",
    "evidence_gate_runs",
    "forecasts",
    "forecast_evaluations",
    "calibration_proposals",
    "decision_packs",
    "optimization_runs",
    "digital_twin_snapshots",
    "digital_twin_runs",
    "market_intelligence_runs",
    "decision_sessions",
    "decision_votes",
]

CONFLICT_COLUMNS = {
    "settings": "id",
    "reference_area_product": "area,product",
    "quarter_finance": "quarter",
    "operations": "quarter,area,product,model",
    "facts": "id",
    "uploads": "id",
    "decisions": "id",
    "scenarios": "id",
    "tests": "id",
    "market_research_catalog": "study_id",
    "research_plan": "quarter,study_id",
    "strategy_principles": "id",
    "milestones": "quarter",
    "audit_log": "id",
    "finance_by_area": "quarter,area",
    "report_imports": "id",
    "research_results": "id",
    "strategy_profiles": "id",
    "strategic_assessments": "quarter",
    "scenario_portfolios": "id",
    "quarter_snapshots": "quarter",
    "agent_threads": "id",
    "agent_messages": "id",
    "rule_sources": "source_id",
    "rulebook_versions": "version",
    "rules": "rule_id,version",
    "rule_conflicts": "id",
    "document_chunks": "id",
    "ai_runs": "id",
    "recommendation_evidence": "id",
    "evidence_gate_runs": "id",
    "forecasts": "id",
    "forecast_evaluations": "id",
    "calibration_proposals": "id",
    "decision_packs": "id",
    "optimization_runs": "id",
    "digital_twin_snapshots": "quarter,as_of_quarter,source_type",
    "digital_twin_runs": "id",
    "market_intelligence_runs": "id",
    "decision_sessions": "id",
    "decision_votes": "session_id,role",
}

KEY_COLUMNS = {
    table: tuple(column.strip() for column in columns.split(",")) for table, columns in CONFLICT_COLUMNS.items()
}

COMPANY_TABLES_DELETE_ORDER = [
    "decision_votes",
    "decision_sessions",
    "market_intelligence_runs",
    "digital_twin_runs",
    "digital_twin_snapshots",
    "evidence_gate_runs",
    "recommendation_evidence",
    "calibration_proposals",
    "forecast_evaluations",
    "optimization_runs",
    "decision_packs",
    "forecasts",
    "ai_runs",
    "document_chunks",
    "rule_conflicts",
    "agent_messages",
    "agent_threads",
    "quarter_snapshots",
    "scenario_portfolios",
    "strategic_assessments",
    "research_results",
    "strategy_profiles",
    "report_imports",
    "finance_by_area",
    "audit_log",
    "research_plan",
    "tests",
    "scenarios",
    "decisions",
    "uploads",
    "facts",
    "operations",
    "quarter_finance",
    "settings",
]

ALL_TABLES_DELETE_ORDER = [
    "decision_votes",
    "decision_sessions",
    "market_intelligence_runs",
    "digital_twin_runs",
    "digital_twin_snapshots",
    "evidence_gate_runs",
    "recommendation_evidence",
    "calibration_proposals",
    "forecast_evaluations",
    "optimization_runs",
    "decision_packs",
    "forecasts",
    "ai_runs",
    "document_chunks",
    "rule_conflicts",
    "agent_messages",
    "agent_threads",
    "quarter_snapshots",
    "scenario_portfolios",
    "strategic_assessments",
    "research_results",
    "strategy_profiles",
    "report_imports",
    "finance_by_area",
    "audit_log",
    "research_plan",
    "tests",
    "scenarios",
    "decisions",
    "uploads",
    "facts",
    "operations",
    "quarter_finance",
    "milestones",
    "strategy_principles",
    "market_research_catalog",
    "reference_area_product",
    "rules",
    "rulebook_versions",
    "rule_sources",
    "settings",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _store() -> CloudStore:
    return get_store()


def _first(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return dict(rows[0]) if rows else {}


def _sorted(rows: Iterable[dict[str, Any]], *keys: str, reverse: bool = False) -> list[dict[str, Any]]:
    return sorted((dict(row) for row in rows), key=lambda row: tuple(str(row.get(key, "")) for key in keys), reverse=reverse)


def init_db() -> None:
    """Verify the Supabase schema and seed structural, non-company data."""
    store = _store()
    try:
        store.health()
    except Exception as exc:
        raise RuntimeError(
            "Supabase is not ready. Run supabase/schema.sql in the Supabase SQL Editor and verify the server credentials."
        ) from exc

    now = utc_now()
    existing = store.select("settings", {"id": 1}, limit=1)
    if not existing:
        store.upsert(
            "settings",
            {
                "id": 1,
                "company_name": "",
                "selected_quarter": "Q4",
                "startup_quarter": "Q4",
                "cash_buffer_sf": 0,
                "min_rd_sf": 0,
                "score_model": DEFAULT_SCORE_MODEL,
                "created_at": now,
                "updated_at": now,
            },
            "id",
        )
    elif not store.select("quarter_finance", limit=1) and not store.select("operations", limit=1):
        current = existing[0]
        if not current.get("company_name") and current.get("selected_quarter") == "Q1":
            store.update("settings", {"id": 1}, {"selected_quarter": "Q4", "startup_quarter": "Q4", "updated_at": now})

    if AREA_PRODUCT_DEFAULTS:
        store.upsert("reference_area_product", AREA_PRODUCT_DEFAULTS, "area,product")

    catalog = [
        {
            "study_id": row[0],
            "name": row[1],
            "description": row[2],
            "cost_k_sf": row[3],
            "use_case": row[4],
            "default_priority": row[5],
            "note": row[6],
        }
        for row in MARKET_RESEARCH
    ]
    if catalog:
        store.upsert("market_research_catalog", catalog, "study_id")

    principles = [
        {
            "id": row[0],
            "principle": row[1],
            "rationale": row[2],
            "leading_metric": row[3],
            "decision_gate": row[4],
            "status": row[5],
        }
        for row in STRATEGY_PRINCIPLES
    ]
    if principles:
        store.upsert("strategy_principles", principles, "id")

    milestones = [
        {
            "quarter": row[0],
            "strategic_goal": row[1],
            "required_signal": row[2],
            "positive_action": row[3],
            "negative_action": row[4],
        }
        for row in MILESTONES
    ]
    if milestones:
        store.upsert("milestones", milestones, "quarter")

    source_rows = [{**row, "updated_at": now} for row in RULE_SOURCES]
    store.upsert("rule_sources", source_rows, "source_id")
    store.upsert(
        "rulebook_versions",
        {
            "version": RULEBOOK_VERSION,
            "status": RULEBOOK_STATUS,
            "name": "INTOPIA current-run approved baseline",
            "source_priority": [row["source_id"] for row in RULE_SOURCES],
            "approved_by": "system baseline",
            "approved_at": now,
            "created_at": now,
        },
        "version",
    )
    rule_rows = [
        {
            **row,
            "is_blocking": row.get("enforcement") == "block",
            "updated_at": now,
        }
        for row in CANONICAL_RULES
    ]
    store.upsert("rules", rule_rows, "rule_id,version")


def health() -> dict[str, Any]:
    return _store().health()


def audit(action: str, entity: str, record_id: str = "", details: dict[str, Any] | None = None, actor: str = "team") -> None:
    try:
        _store().insert(
            "audit_log",
            {
                "action": action,
                "entity": entity,
                "record_id": str(record_id or ""),
                "actor": actor,
                "details": details or {},
                "created_at": utc_now(),
            },
        )
    except Exception:
        # Audit logging must not turn a successful business save into a failure.
        return


def get_settings() -> dict[str, Any]:
    result = _first(_store().select("settings", {"id": 1}, limit=1))
    result.setdefault("startup_quarter", "Q4")
    if not result.get("score_model"):
        result["score_model"] = DEFAULT_SCORE_MODEL
    return result


def update_settings(payload: dict[str, Any]) -> dict[str, Any]:
    allowed = {"company_name", "selected_quarter", "startup_quarter", "cash_buffer_sf", "min_rd_sf", "score_model"}
    fields = {key: payload[key] for key in allowed if key in payload}
    if fields.get("selected_quarter") and fields["selected_quarter"] not in QUARTERS:
        raise ValueError("Invalid quarter")
    if fields.get("startup_quarter") and fields["startup_quarter"] not in QUARTERS:
        raise ValueError("Invalid startup quarter")
    if not fields:
        return get_settings()
    fields["updated_at"] = utc_now()
    rows = _store().update("settings", {"id": 1}, fields)
    if not rows:
        init_db()
        rows = _store().update("settings", {"id": 1}, fields)
    result = _first(rows) or get_settings()
    audit("autosave", "settings", "1", {"fields": sorted(key for key in fields if key != "updated_at")})
    return result


def get_reference_data() -> list[dict[str, Any]]:
    return _sorted(_store().select("reference_area_product"), "area", "product")


FINANCE_FIELDS = [
    "revenue_sf",
    "gross_profit_sf",
    "net_profit_sf",
    "ending_cash_sf",
    "debt_sf",
    "ar_sf",
    "ap_sf",
    "research_budget_sf",
    "rd_x_sf",
    "rd_y_sf",
    "partnership_score",
    "dividends_sf",
    "notes",
]


def get_finance(quarter: str) -> dict[str, Any]:
    return _first(_store().select("quarter_finance", {"quarter": quarter}, limit=1))


def list_finance() -> list[dict[str, Any]]:
    return _sorted(_store().select("quarter_finance"), "quarter")


def upsert_finance(quarter: str, payload: dict[str, Any]) -> dict[str, Any]:
    if quarter not in QUARTERS:
        raise ValueError("Invalid quarter")
    existing = get_finance(quarter)
    values: dict[str, Any] = {"quarter": quarter}
    for key in FINANCE_FIELDS:
        default: Any = "" if key == "notes" else 0
        values[key] = payload.get(key, existing.get(key, default))
    values["updated_at"] = utc_now()
    result = _first(_store().upsert("quarter_finance", values, "quarter")) or get_finance(quarter)
    audit("autosave", "quarter_finance", quarter, {"quarter": quarter})
    return result


AREA_FINANCE_FIELDS = [
    "quarter",
    "area",
    "currency",
    "fx_to_sf",
    "revenue_lc",
    "gross_profit_lc",
    "net_profit_lc",
    "ending_cash_lc",
    "debt_lc",
    "ar_lc",
    "ap_lc",
    "inventory_value_lc",
    "current_assets_lc",
    "current_liabilities_lc",
    "equity_lc",
    "total_investment_lc",
    "operating_cash_flow_lc",
    "capex_commitments_lc",
    "source",
    "confidence",
    "notes",
]


def list_finance_by_area(quarter: str | None = None) -> list[dict[str, Any]]:
    filters = {"quarter": quarter} if quarter else None
    return _sorted(_store().select("finance_by_area", filters), "quarter", "area")


def upsert_finance_by_area(payload: dict[str, Any]) -> dict[str, Any]:
    quarter = str(payload.get("quarter") or "")
    area = str(payload.get("area") or "").strip()
    if quarter not in QUARTERS or not area:
        raise ValueError("quarter and area are required")
    existing = _first(_store().select("finance_by_area", {"quarter": quarter, "area": area}, limit=1))
    text_fields = {"quarter", "area", "currency", "source", "confidence", "notes"}
    values: dict[str, Any] = {}
    for key in AREA_FINANCE_FIELDS:
        default: Any = "" if key in text_fields else (1 if key == "fx_to_sf" else 0)
        values[key] = payload.get(key, existing.get(key, default))
    values["confidence"] = values.get("confidence") or "בינונית"
    values["updated_at"] = utc_now()
    result = _first(_store().upsert("finance_by_area", values, "quarter,area"))
    audit("autosave", "finance_by_area", f"{quarter}:{area}", {"quarter": quarter, "area": area})
    return result


OPERATION_FIELDS = [
    "quarter",
    "area",
    "product",
    "model",
    "fx_to_sf",
    "grade",
    "plants",
    "plant_capacity",
    "planned_production",
    "actual_production",
    "opening_inventory",
    "planned_sales",
    "actual_sales",
    "ending_inventory",
    "forecast_demand",
    "planned_price_lc",
    "actual_price_lc",
    "advertising_lc",
    "variable_cost_lc",
    "fixed_cost_lc",
    "methods_improvement_lc",
    "sales_channel",
    "actual_market_share",
    "source",
    "confidence",
    "notes",
]


def get_operations(quarter: str) -> list[dict[str, Any]]:
    return _sorted(_store().select("operations", {"quarter": quarter}), "area", "product", "model")


def list_operations() -> list[dict[str, Any]]:
    return _sorted(_store().select("operations"), "quarter", "area", "product", "model")


def upsert_operation(payload: dict[str, Any]) -> dict[str, Any]:
    required = ["quarter", "area", "product", "model"]
    for field in required:
        if not payload.get(field):
            raise ValueError(f"Missing required field: {field}")
    if payload["quarter"] not in QUARTERS:
        raise ValueError("Invalid quarter")
    filters = {field: payload[field] for field in required}
    existing = _first(_store().select("operations", filters, limit=1))
    text_fields = {"quarter", "area", "product", "model", "sales_channel", "source", "confidence", "notes"}
    values: dict[str, Any] = {}
    for key in OPERATION_FIELDS:
        default: Any = "" if key in text_fields else 0
        values[key] = payload.get(key, existing.get(key, default))
    if existing.get("id"):
        values["id"] = existing["id"]
    values["updated_at"] = utc_now()
    result = _first(_store().upsert("operations", values, "quarter,area,product,model"))
    audit("autosave", "operations", str(result.get("id", "")), filters)
    return result


def list_facts(quarter: str | None = None, limit: int = 500) -> list[dict[str, Any]]:
    rows = _store().select("facts", {"quarter": quarter} if quarter else None, order="created_at", descending=True, limit=limit)
    return [dict(row) for row in rows]


def add_fact(payload: dict[str, Any]) -> dict[str, Any]:
    values = {
        "quarter": payload.get("quarter", "Q1"),
        "source_type": payload.get("source_type", "ידני"),
        "source_name": payload.get("source_name", ""),
        "area": payload.get("area", ""),
        "product": payload.get("product", ""),
        "company": payload.get("company", ""),
        "metric": payload.get("metric", ""),
        "value": payload.get("value"),
        "text_value": payload.get("text_value", ""),
        "unit": payload.get("unit", ""),
        "confidence": payload.get("confidence", "בינונית"),
        "notes": payload.get("notes", ""),
        "created_at": utc_now(),
    }
    if not values["metric"]:
        raise ValueError("metric is required")
    result = _store().insert("facts", values)
    audit("create", "facts", str(result["id"]), {"metric": values["metric"], "quarter": values["quarter"]})
    return result


def delete_fact(fact_id: str) -> None:
    _store().delete("facts", {"id": fact_id})
    audit("delete", "facts", fact_id)


def list_uploads(quarter: str | None = None) -> list[dict[str, Any]]:
    return _store().select("uploads", {"quarter": quarter} if quarter else None, order="created_at", descending=True)


def get_upload(upload_id: str) -> dict[str, Any]:
    return _first(_store().select("uploads", {"id": upload_id}, limit=1))


def add_upload(payload: dict[str, Any]) -> dict[str, Any]:
    required = {"quarter", "category", "original_name", "storage_bucket", "storage_path", "mime_type", "size_bytes", "sha256"}
    missing = sorted(field for field in required if payload.get(field) in {None, ""})
    if missing:
        raise ValueError(f"Missing upload metadata: {', '.join(missing)}")
    values = {
        "quarter": payload["quarter"],
        "category": payload["category"],
        "original_name": payload["original_name"],
        "storage_bucket": payload["storage_bucket"],
        "storage_path": payload["storage_path"],
        "mime_type": payload["mime_type"],
        "size_bytes": int(payload["size_bytes"]),
        "sha256": payload["sha256"],
        "etag": payload.get("etag", ""),
        "notes": payload.get("notes", ""),
        "uploaded_by": payload.get("uploaded_by", "team"),
        "metadata": payload.get("metadata", {}),
        "created_at": payload.get("created_at", utc_now()),
    }
    result = _store().insert("uploads", values)
    audit("upload", "uploads", str(result["id"]), {"name": values["original_name"], "sha256": values["sha256"]})
    return result


def upsert_upload_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    result = _first(_store().upsert("uploads", payload, "id"))
    return result


def delete_upload_record(upload_id: str) -> None:
    # Supabase cascades these relations. Explicit deletion keeps the in-memory
    # backend and restore/test behaviour identical to production.
    _store().delete("report_imports", {"upload_id": upload_id})
    _store().delete("research_results", {"source_upload_id": upload_id})
    _store().update("strategy_profiles", {"source_upload_id": upload_id}, {"source_upload_id": None, "updated_at": utc_now()})
    _store().delete("uploads", {"id": upload_id})
    audit("delete", "uploads", upload_id)


def list_report_imports(quarter: str | None = None) -> list[dict[str, Any]]:
    return _store().select("report_imports", {"quarter": quarter} if quarter else None, order="created_at", descending=True)


def get_report_import(import_id: str) -> dict[str, Any]:
    return _first(_store().select("report_imports", {"id": import_id}, limit=1))


def add_report_import(payload: dict[str, Any]) -> dict[str, Any]:
    values = {
        "upload_id": payload.get("upload_id"),
        "quarter": payload.get("quarter", "Setup"),
        "parser_type": payload.get("parser_type", ""),
        "status": payload.get("status", "נדרשת בדיקה"),
        "confidence": payload.get("confidence", "נמוכה"),
        "extracted_data": payload.get("extracted_data", {}),
        "issues": payload.get("issues", []),
        "rule_validation": payload.get("rule_validation", {}),
        "reviewed_by": "",
        "created_at": utc_now(),
    }
    if not values["upload_id"]:
        raise ValueError("upload_id is required")
    result = _store().insert("report_imports", values)
    audit("extract", "report_imports", str(result["id"]), {"upload_id": values["upload_id"], "quarter": values["quarter"]})
    return result


def mark_report_import_committed(import_id: str, reviewed_by: str = "team") -> dict[str, Any]:
    now = utc_now()
    result = _first(
        _store().update(
            "report_imports",
            {"id": import_id},
            {"status": "נקלט", "reviewed_by": reviewed_by, "reviewed_at": now, "committed_at": now},
        )
    )
    if not result:
        raise KeyError("report import not found")
    audit("commit", "report_imports", import_id)
    return result


def storage_upload(path: str, content: bytes, content_type: str, *, upsert: bool = False) -> dict[str, Any]:
    return _store().upload_file(path, content, content_type, upsert=upsert)


def storage_download(path: str) -> bytes:
    return _store().download_file(path)


def storage_delete(path: str) -> None:
    _store().delete_file(path)


def list_rule_sources() -> list[dict[str, Any]]:
    return _store().select("rule_sources", order="priority")


def list_rulebook_versions() -> list[dict[str, Any]]:
    return _store().select("rulebook_versions", order="created_at", descending=True)


def list_rules(
    *,
    version: str = RULEBOOK_VERSION,
    domain: str = "",
    knowledge_type: str = "",
    approval_status: str = "",
) -> list[dict[str, Any]]:
    rows = _store().select("rules", {"version": version}, order="rule_id")
    if domain:
        rows = [row for row in rows if str(row.get("domain") or "").casefold() == domain.casefold()]
    if knowledge_type:
        rows = [row for row in rows if str(row.get("knowledge_type") or "").casefold() == knowledge_type.casefold()]
    if approval_status:
        rows = [row for row in rows if str(row.get("approval_status") or "").casefold() == approval_status.casefold()]
    return rows


def get_rule(rule_id: str, version: str = RULEBOOK_VERSION) -> dict[str, Any]:
    return _first(_store().select("rules", {"rule_id": rule_id, "version": version}, limit=1))


def add_rule_conflict(payload: dict[str, Any]) -> dict[str, Any]:
    values = {
        "rule_id": payload.get("rule_id", ""),
        "existing_version": payload.get("existing_version", RULEBOOK_VERSION),
        "candidate_source_id": payload.get("candidate_source_id", ""),
        "candidate_value": payload.get("candidate_value", {}),
        "description": payload.get("description", ""),
        "status": payload.get("status", "open"),
        "resolution": payload.get("resolution", ""),
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }
    result = _store().insert("rule_conflicts", values)
    audit("create", "rule_conflicts", str(result["id"]), {"rule_id": values["rule_id"]})
    return result


def list_rule_conflicts(status: str | None = None) -> list[dict[str, Any]]:
    return _store().select("rule_conflicts", {"status": status} if status else None, order="created_at", descending=True)


def resolve_rule_conflict(conflict_id: str, status: str, resolution: str, reviewed_by: str = "team") -> dict[str, Any]:
    if status not in {"approved_for_next_version", "rejected", "deferred"}:
        raise ValueError("Unsupported conflict resolution status.")
    result = _first(
        _store().update(
            "rule_conflicts",
            {"id": conflict_id},
            {
                "status": status,
                "resolution": resolution,
                "updated_at": utc_now(),
            },
        )
    )
    if result:
        audit(
            "resolve",
            "rule_conflicts",
            conflict_id,
            {"status": status, "resolution": resolution, "reviewed_by": reviewed_by},
        )
    return result


def add_document_chunk(payload: dict[str, Any]) -> dict[str, Any]:
    content = str(payload.get("content") or "").strip()
    if not content:
        raise ValueError("Document chunk content is required.")
    values = {
        "upload_id": payload.get("upload_id"),
        "source_id": str(payload.get("source_id") or ""),
        "page": payload.get("page"),
        "section": str(payload.get("section") or ""),
        "content": content,
        "content_hash": str(payload.get("content_hash") or hashlib.sha256(content.encode("utf-8")).hexdigest()),
        "metadata": payload.get("metadata") or {},
        "created_at": utc_now(),
    }
    return _store().insert("document_chunks", values)


def list_document_chunks(
    *,
    upload_id: str | None = None,
    source_id: str | None = None,
    query: str = "",
    limit: int = 50,
) -> list[dict[str, Any]]:
    filters: dict[str, Any] = {}
    if upload_id:
        filters["upload_id"] = upload_id
    if source_id:
        filters["source_id"] = source_id
    rows = _store().select("document_chunks", filters or None, order="created_at", descending=True)
    terms = [term.casefold() for term in query.split() if term.strip()]
    if terms:
        rows = [
            row
            for row in rows
            if all(
                term in " ".join(
                    [
                        str(row.get("source_id") or ""),
                        str(row.get("section") or ""),
                        str(row.get("content") or ""),
                    ]
                ).casefold()
                for term in terms
            )
        ]
    return rows[: max(1, min(limit, 100))]


def add_ai_run(payload: dict[str, Any]) -> dict[str, Any]:
    return _store().insert(
        "ai_runs",
        {
            "run_type": payload.get("run_type", "chat"),
            "quarter": payload.get("quarter", ""),
            "model": payload.get("model", ""),
            "status": payload.get("status", "completed"),
            "input_summary": payload.get("input_summary", ""),
            "output_summary": payload.get("output_summary", ""),
            "tool_calls": payload.get("tool_calls", []),
            "sources": payload.get("sources", []),
            "error": payload.get("error", ""),
            "created_at": utc_now(),
        },
    )


def add_forecast(payload: dict[str, Any]) -> dict[str, Any]:
    return _store().insert(
        "forecasts",
        {
            "quarter": payload.get("quarter", "Q4"),
            "source_actual_quarter": payload.get("source_actual_quarter", ""),
            "target_quarter": payload.get("target_quarter", payload.get("quarter", "Q4")),
            "forecast_type": payload.get("forecast_type", "q9"),
            "rulebook_version": payload.get("rulebook_version", RULEBOOK_VERSION),
            "assumptions": payload.get("assumptions", []),
            "result": payload.get("result", {}),
            "confidence": payload.get("confidence", "medium"),
            "status": payload.get("status", "open"),
            "created_at": utc_now(),
        },
    )


def list_forecasts(
    quarter: str | None = None,
    target_quarter: str | None = None,
    status: str | None = None,
) -> list[dict[str, Any]]:
    filters = {
        key: value
        for key, value in {
            "quarter": quarter,
            "target_quarter": target_quarter,
            "status": status,
        }.items()
        if value
    }
    return _store().select("forecasts", filters or None, order="created_at", descending=True)


def get_forecast(forecast_id: str) -> dict[str, Any]:
    return _first(_store().select("forecasts", {"id": forecast_id}, limit=1))


def update_forecast(forecast_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    values = {key: value for key, value in payload.items() if key in {
        "status", "confidence", "result", "assumptions", "source_actual_quarter", "target_quarter"
    }}
    result = _first(_store().update("forecasts", {"id": forecast_id}, values))
    if not result:
        raise KeyError("forecast not found")
    return result


def add_forecast_evaluation(payload: dict[str, Any]) -> dict[str, Any]:
    existing = _first(_store().select("forecast_evaluations", {"forecast_id": payload.get("forecast_id")}, limit=1))
    values = {
        "forecast_id": payload.get("forecast_id"),
        "source_actual_quarter": payload.get("source_actual_quarter", ""),
        "target_quarter": payload.get("target_quarter", ""),
        "status": payload.get("status", "evaluated"),
        "summary": payload.get("summary", {}),
        "metric_errors": payload.get("metric_errors", {}),
        "driver_analysis": payload.get("driver_analysis", []),
        "actual_snapshot": payload.get("actual_snapshot", {}),
        "evaluated_at": payload.get("evaluated_at", utc_now()),
        "created_at": existing.get("created_at", utc_now()),
    }
    if existing.get("id"):
        result = _first(_store().update("forecast_evaluations", {"id": existing["id"]}, values))
    else:
        result = _store().insert("forecast_evaluations", values)
    audit("evaluate", "forecast_evaluations", str(result.get("id", "")), {"forecast_id": values["forecast_id"], "target_quarter": values["target_quarter"]})
    return result


def list_forecast_evaluations(quarter: str | None = None) -> list[dict[str, Any]]:
    filters = {"target_quarter": quarter} if quarter else None
    return _store().select("forecast_evaluations", filters, order="evaluated_at", descending=True)


def add_calibration_proposal(payload: dict[str, Any]) -> dict[str, Any]:
    now = utc_now()
    return _store().insert(
        "calibration_proposals",
        {
            "evaluation_id": payload.get("evaluation_id"),
            "parameter_key": payload.get("parameter_key", ""),
            "metric_key": payload.get("metric_key", ""),
            "scope": payload.get("scope", {"level": "global"}),
            "previous_value": payload.get("previous_value", 1.0),
            "proposed_value": payload.get("proposed_value", 1.0),
            "confidence": payload.get("confidence", "low"),
            "status": payload.get("status", "draft"),
            "reason": payload.get("reason", ""),
            "evidence": payload.get("evidence", {}),
            "reviewed_by": payload.get("reviewed_by", ""),
            "approved_at": payload.get("approved_at"),
            "created_at": now,
            "updated_at": now,
        },
    )


def list_calibration_proposals(status: str | None = None) -> list[dict[str, Any]]:
    return _store().select(
        "calibration_proposals",
        {"status": status} if status else None,
        order="created_at",
        descending=True,
    )


def update_calibration_proposal(proposal_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    status = str(payload.get("status") or "")
    if status not in {"draft", "approved", "rejected"}:
        raise ValueError("status must be draft, approved or rejected")
    values = {
        "status": status,
        "reviewed_by": payload.get("reviewed_by", "team"),
        "approved_at": utc_now() if status == "approved" else None,
        "updated_at": utc_now(),
    }
    result = _first(_store().update("calibration_proposals", {"id": proposal_id}, values))
    if not result:
        raise KeyError("calibration proposal not found")
    audit("review", "calibration_proposals", proposal_id, {"status": status, "parameter_key": result.get("parameter_key")})
    return result


def add_decision_pack(payload: dict[str, Any]) -> dict[str, Any]:
    now = utc_now()
    values = {
        "quarter": payload.get("quarter", "Q4"),
        "name": payload.get("name", "Decision pack"),
        "status": payload.get("status", "draft"),
        "rulebook_version": payload.get("rulebook_version", RULEBOOK_VERSION),
        "scenario_portfolio_id": payload.get("scenario_portfolio_id"),
        "actions": payload.get("actions", []),
        "validation": payload.get("validation", {}),
        "financial_impact": payload.get("financial_impact", {}),
        "q9_impact": payload.get("q9_impact", {}),
        "recommendation": payload.get("recommendation", ""),
        "created_by": payload.get("created_by", "team"),
        "created_at": now,
        "updated_at": now,
    }
    result = _store().insert("decision_packs", values)
    audit("create", "decision_packs", str(result["id"]), {"quarter": values["quarter"], "status": values["status"]})
    return result


def list_decision_packs(quarter: str | None = None) -> list[dict[str, Any]]:
    return _store().select("decision_packs", {"quarter": quarter} if quarter else None, order="created_at", descending=True)


def get_decision_pack(pack_id: str) -> dict[str, Any]:
    return _first(_store().select("decision_packs", {"id": pack_id}, limit=1))


def add_recommendation_evidence(payload: dict[str, Any]) -> dict[str, Any]:
    return _store().insert(
        "recommendation_evidence",
        {
            "decision_pack_id": payload.get("decision_pack_id"),
            "recommendation_key": payload.get("recommendation_key", ""),
            "evidence_type": payload.get("evidence_type", "rule"),
            "source_id": payload.get("source_id", ""),
            "source_page": str(payload.get("source_page", "")),
            "rule_id": payload.get("rule_id", ""),
            "payload": payload.get("payload", {}),
            "created_at": utc_now(),
        },
    )


def list_recommendation_evidence(decision_pack_id: str) -> list[dict[str, Any]]:
    return _store().select(
        "recommendation_evidence",
        {"decision_pack_id": decision_pack_id},
        order="created_at",
    )


def add_evidence_gate_run(payload: dict[str, Any]) -> dict[str, Any]:
    result = _store().insert(
        "evidence_gate_runs",
        {
            "quarter": payload.get("quarter", "Q4"),
            "decision_pack_id": payload.get("decision_pack_id"),
            "recommendation_key": payload.get("recommendation_key", ""),
            "status": payload.get("status", "blocked"),
            "score": payload.get("score", 0),
            "summary": payload.get("summary", {}),
            "claims": payload.get("claims", []),
            "gaps": payload.get("gaps", []),
            "contradictions": payload.get("contradictions", []),
            "created_at": utc_now(),
        },
    )
    audit(
        "create",
        "evidence_gate_runs",
        str(result.get("id") or ""),
        {"quarter": result.get("quarter"), "status": result.get("status")},
    )
    return result


def list_evidence_gate_runs(
    quarter: str | None = None,
    recommendation_key: str | None = None,
) -> list[dict[str, Any]]:
    filters: dict[str, Any] = {}
    if quarter:
        filters["quarter"] = quarter
    if recommendation_key:
        filters["recommendation_key"] = recommendation_key
    return _store().select("evidence_gate_runs", filters or None, order="created_at", descending=True)


def update_decision_pack(pack_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    values = {key: value for key, value in payload.items() if key in {
        "name", "status", "actions", "validation", "financial_impact", "q9_impact", "recommendation"
    }}
    values["updated_at"] = utc_now()
    result = _first(_store().update("decision_packs", {"id": pack_id}, values))
    if not result:
        raise KeyError("decision pack not found")
    audit("update", "decision_packs", pack_id, {"status": result.get("status")})
    return result


def add_optimization_run(payload: dict[str, Any]) -> dict[str, Any]:
    return _store().insert(
        "optimization_runs",
        {
            "quarter": payload.get("quarter", "Q4"),
            "optimization_type": payload.get("optimization_type", "budget"),
            "rulebook_version": payload.get("rulebook_version", RULEBOOK_VERSION),
            "constraints": payload.get("constraints", {}),
            "candidates": payload.get("candidates", []),
            "result": payload.get("result", {}),
            "created_at": utc_now(),
        },
    )


def list_optimization_runs(
    quarter: str | None = None,
    optimization_type: str | None = None,
) -> list[dict[str, Any]]:
    filters: dict[str, Any] = {}
    if quarter:
        filters["quarter"] = quarter
    if optimization_type:
        filters["optimization_type"] = optimization_type
    return _store().select("optimization_runs", filters or None, order="created_at", descending=True)


def add_decision_session(payload: dict[str, Any]) -> dict[str, Any]:
    now = utc_now()
    result = _store().insert(
        "decision_sessions",
        {
            "quarter": payload.get("quarter", "Q4"),
            "name": payload.get("name", "Team decision session"),
            "status": payload.get("status", "draft"),
            "decision_pack_id": payload.get("decision_pack_id"),
            "optimization_run_id": payload.get("optimization_run_id"),
            "rulebook_version": payload.get("rulebook_version", RULEBOOK_VERSION),
            "snapshot": payload.get("snapshot", {}),
            "validation": payload.get("validation", {}),
            "facilitator": payload.get("facilitator", ""),
            "approved_by": payload.get("approved_by", []),
            "approved_at": payload.get("approved_at"),
            "locked": bool(payload.get("locked", False)),
            "created_at": now,
            "updated_at": now,
        },
    )
    audit("create", "decision_sessions", str(result.get("id") or ""), {"quarter": result.get("quarter")})
    return result


def list_decision_sessions(quarter: str | None = None) -> list[dict[str, Any]]:
    return _store().select(
        "decision_sessions",
        {"quarter": quarter} if quarter else None,
        order="created_at",
        descending=True,
    )


def get_decision_session(session_id: str) -> dict[str, Any]:
    return _first(_store().select("decision_sessions", {"id": session_id}, limit=1))


def update_decision_session(session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    current = get_decision_session(session_id)
    if not current:
        raise KeyError("decision session not found")
    if current.get("locked") and any(key not in {"status"} for key in payload):
        raise ValueError("approved decision session is locked")
    allowed = {"status", "validation", "approved_by", "approved_at", "locked", "facilitator"}
    values = {key: value for key, value in payload.items() if key in allowed}
    values["updated_at"] = utc_now()
    result = _first(_store().update("decision_sessions", {"id": session_id}, values))
    audit("update", "decision_sessions", session_id, {"status": result.get("status")})
    return result


def upsert_decision_vote(payload: dict[str, Any]) -> dict[str, Any]:
    now = utc_now()
    values = {
        "session_id": payload.get("session_id"),
        "role": payload.get("role", ""),
        "voter_name": payload.get("voter_name", ""),
        "vote": payload.get("vote", "abstain"),
        "rationale": payload.get("rationale", ""),
        "concerns": payload.get("concerns", []),
        "created_at": payload.get("created_at") or now,
        "updated_at": now,
    }
    result = _first(_store().upsert("decision_votes", values, "session_id,role"))
    audit("vote", "decision_votes", str(result.get("id") or ""), {"session_id": result.get("session_id"), "role": result.get("role"), "vote": result.get("vote")})
    return result


def list_decision_votes(session_id: str) -> list[dict[str, Any]]:
    return _store().select("decision_votes", {"session_id": session_id}, order="updated_at")


def upsert_digital_twin_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    quarter = str(payload.get("quarter") or "")
    if quarter not in QUARTERS:
        raise ValueError("Invalid quarter")
    now = utc_now()
    source_type = payload.get("source_type", "approved_actual")
    as_of_quarter = str(payload.get("as_of_quarter") or "none")
    existing = _store().select(
        "digital_twin_snapshots",
        {"quarter": quarter, "as_of_quarter": as_of_quarter, "source_type": source_type},
        limit=1,
    )
    values = {
        "quarter": quarter,
        "as_of_quarter": as_of_quarter,
        "source_type": source_type,
        "state": payload.get("state", {}),
        "locked": bool(payload.get("locked", True)),
        "rulebook_version": payload.get("rulebook_version", RULEBOOK_VERSION),
        "created_at": payload.get("created_at") or (existing[0].get("created_at") if existing else now),
        "updated_at": now,
    }
    result = _first(
        _store().upsert(
            "digital_twin_snapshots",
            values,
            "quarter,as_of_quarter,source_type",
        )
    )
    audit("snapshot", "digital_twin_snapshots", quarter, {"as_of_quarter": values["as_of_quarter"], "locked": values["locked"]})
    return result


def list_digital_twin_snapshots(quarter: str | None = None) -> list[dict[str, Any]]:
    return _store().select(
        "digital_twin_snapshots",
        {"quarter": quarter} if quarter else None,
        order="updated_at",
        descending=True,
    )


def add_digital_twin_run(payload: dict[str, Any]) -> dict[str, Any]:
    quarter = str(payload.get("quarter") or "")
    if quarter not in QUARTERS:
        raise ValueError("Invalid quarter")
    result = _store().insert(
        "digital_twin_runs",
        {
            "quarter": quarter,
            "scenario_name": payload.get("scenario_name", f"{quarter} scenario"),
            "baseline_as_of": payload.get("baseline_as_of"),
            "actions": payload.get("actions", []),
            "assumptions": payload.get("assumptions", []),
            "result": payload.get("result", {}),
            "feasible": bool(payload.get("feasible", False)),
            "rulebook_version": payload.get("rulebook_version", RULEBOOK_VERSION),
            "created_at": utc_now(),
        },
    )
    audit("simulate", "digital_twin_runs", str(result["id"]), {"quarter": quarter, "feasible": result["feasible"]})
    return result


def list_digital_twin_runs(quarter: str | None = None) -> list[dict[str, Any]]:
    return _store().select(
        "digital_twin_runs",
        {"quarter": quarter} if quarter else None,
        order="created_at",
        descending=True,
    )


def add_market_intelligence_run(payload: dict[str, Any]) -> dict[str, Any]:
    quarter = str(payload.get("quarter") or "")
    if quarter not in QUARTERS:
        raise ValueError("Invalid quarter")
    result = _store().insert(
        "market_intelligence_runs",
        {
            "quarter": quarter,
            "result": payload.get("result", {}),
            "input_fingerprint": payload.get("input_fingerprint", ""),
            "created_at": utc_now(),
        },
    )
    audit("analyze", "market_intelligence_runs", str(result["id"]), {"quarter": quarter})
    return result


def list_market_intelligence_runs(quarter: str | None = None) -> list[dict[str, Any]]:
    return _store().select(
        "market_intelligence_runs",
        {"quarter": quarter} if quarter else None,
        order="created_at",
        descending=True,
    )


def list_decisions(quarter: str | None = None) -> list[dict[str, Any]]:
    return _store().select("decisions", {"quarter": quarter} if quarter else None, order="created_at", descending=True)


def add_decision(payload: dict[str, Any]) -> dict[str, Any]:
    now = utc_now()
    values = {
        "quarter": payload.get("quarter", "Q1"),
        "domain": payload.get("domain", "אסטרטגיה"),
        "title": payload.get("title", ""),
        "question": payload.get("question", ""),
        "selected_option": payload.get("selected_option", ""),
        "rationale": payload.get("rationale", ""),
        "owner": payload.get("owner", ""),
        "status": payload.get("status", "פתוח"),
        "expected_result": payload.get("expected_result", ""),
        "actual_result": payload.get("actual_result", ""),
        "confidence": payload.get("confidence", "בינונית"),
        "created_at": now,
        "updated_at": now,
    }
    if not values["title"]:
        raise ValueError("title is required")
    result = _store().insert("decisions", values)
    audit("create", "decisions", str(result["id"]), {"quarter": values["quarter"], "title": values["title"]})
    return result


def update_decision(decision_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "domain",
        "title",
        "question",
        "selected_option",
        "rationale",
        "owner",
        "status",
        "expected_result",
        "actual_result",
        "confidence",
    }
    values = {key: payload[key] for key in allowed if key in payload}
    values["updated_at"] = utc_now()
    result = _first(_store().update("decisions", {"id": decision_id}, values))
    if not result:
        raise KeyError("decision not found")
    audit("autosave", "decisions", decision_id, {"fields": sorted(key for key in values if key != "updated_at")})
    return result


SCENARIO_FIELDS = [
    "quarter",
    "name",
    "area",
    "product",
    "grade",
    "price_lc",
    "demand",
    "production",
    "opening_inventory",
    "variable_cost_lc",
    "advertising_lc",
    "fixed_cost_lc",
    "transport_per_unit_lc",
    "inventory_cost_per_unit_lc",
    "tax_rate",
    "fx_to_sf",
    "notes",
]


def list_scenarios(quarter: str) -> list[dict[str, Any]]:
    return _sorted(_store().select("scenarios", {"quarter": quarter}), "name", "area", "product", "created_at")


def add_scenario(payload: dict[str, Any]) -> dict[str, Any]:
    now = utc_now()
    text_fields = {"quarter", "name", "area", "product", "notes"}
    values = {key: payload.get(key, "" if key in text_fields else 0) for key in SCENARIO_FIELDS}
    if not values["name"]:
        raise ValueError("name is required")
    values.update({"created_at": now, "updated_at": now})
    result = _store().insert("scenarios", values)
    audit("create", "scenarios", str(result["id"]), {"quarter": values["quarter"], "name": values["name"]})
    return result


def delete_scenario(scenario_id: str) -> None:
    _store().delete("scenarios", {"id": scenario_id})
    audit("delete", "scenarios", scenario_id)


def list_tests(quarter: str | None = None) -> list[dict[str, Any]]:
    return _store().select("tests", {"quarter": quarter} if quarter else None, order="created_at", descending=True)


def add_test(payload: dict[str, Any]) -> dict[str, Any]:
    now = utc_now()
    values = {
        "quarter": payload.get("quarter", "Q1"),
        "name": payload.get("name", ""),
        "hypothesis": payload.get("hypothesis", ""),
        "changed_variables": payload.get("changed_variables", ""),
        "expected_result": payload.get("expected_result", ""),
        "actual_result": payload.get("actual_result", ""),
        "decision": payload.get("decision", ""),
        "confidence": payload.get("confidence", "בינונית"),
        "created_at": now,
        "updated_at": now,
    }
    if not values["name"]:
        raise ValueError("name is required")
    result = _store().insert("tests", values)
    audit("create", "tests", str(result["id"]), {"quarter": values["quarter"], "name": values["name"]})
    return result


def get_market_research_catalog() -> list[dict[str, Any]]:
    rows = _store().select("market_research_catalog")
    return sorted(rows, key=lambda row: int(row.get("study_id") or 0))


def get_research_plan(quarter: str) -> list[dict[str, Any]]:
    catalog = {int(row["study_id"]): row for row in get_market_research_catalog()}
    result: list[dict[str, Any]] = []
    for row in _store().select("research_plan", {"quarter": quarter}, order="created_at"):
        details = catalog.get(int(row.get("study_id") or 0), {})
        result.append({**row, **{key: details.get(key) for key in ("name", "cost_k_sf", "description", "use_case", "default_priority")}})
    return result


def upsert_research_plan(payload: dict[str, Any]) -> dict[str, Any]:
    now = utc_now()
    values = {
        "quarter": payload.get("quarter", "Q1"),
        "study_id": int(payload.get("study_id")),
        "decision_supported": payload.get("decision_supported", ""),
        "key_result": payload.get("key_result", ""),
        "action": payload.get("action", ""),
        "status": payload.get("status", "מתוכנן"),
        "created_at": payload.get("created_at", now),
        "updated_at": now,
    }
    existing = _first(_store().select("research_plan", {"quarter": values["quarter"], "study_id": values["study_id"]}, limit=1))
    if existing.get("id"):
        values["id"] = existing["id"]
        values["created_at"] = existing.get("created_at", now)
    _store().upsert("research_plan", values, "quarter,study_id")
    return next(row for row in get_research_plan(values["quarter"]) if int(row["study_id"]) == values["study_id"])


def list_research_results(quarter: str | None = None) -> list[dict[str, Any]]:
    return _store().select("research_results", {"quarter": quarter} if quarter else None, order="created_at", descending=True)


def add_research_result(payload: dict[str, Any]) -> dict[str, Any]:
    now = utc_now()
    values = {
        "quarter": payload.get("quarter", "Q4"),
        "study_id": int(payload["study_id"]) if payload.get("study_id") not in (None, "") else None,
        "title": payload.get("title", "מחקר שוק"),
        "area": payload.get("area", ""),
        "product": payload.get("product", ""),
        "key_result": payload.get("key_result", ""),
        "numeric_data": payload.get("numeric_data", {}),
        "relevance_domains": payload.get("relevance_domains", []),
        "source_upload_id": payload.get("source_upload_id"),
        "confidence": payload.get("confidence", "בינונית"),
        "status": payload.get("status", "מאושר"),
        "created_at": payload.get("created_at", now),
        "updated_at": now,
    }
    if values["quarter"] not in QUARTERS:
        raise ValueError("Invalid quarter")
    result = _store().insert("research_results", values)
    audit("create", "research_results", str(result["id"]), {"quarter": values["quarter"], "title": values["title"]})
    return result


def get_strategy_profile() -> dict[str, Any]:
    return _first(_store().select("strategy_profiles", {"id": 1}, limit=1))


def upsert_strategy_profile(payload: dict[str, Any]) -> dict[str, Any]:
    existing = get_strategy_profile()
    def merged_list(key: str) -> list[Any]:
        result: list[Any] = []
        for item in [*(existing.get(key) or []), *(payload.get(key) or [])]:
            if item not in result:
                result.append(item)
        return result

    values = {
        "id": 1,
        "thesis": payload.get("thesis") or existing.get("thesis", ""),
        "priorities": merged_list("priorities"),
        "goals": merged_list("goals"),
        "constraints": merged_list("constraints"),
        "source_upload_id": payload.get("source_upload_id", existing.get("source_upload_id")),
        "source_excerpt": "\n\n".join(part for part in [existing.get("source_excerpt", ""), payload.get("source_excerpt", "")] if part)[-16000:],
        "updated_at": utc_now(),
    }
    result = _first(_store().upsert("strategy_profiles", values, "id"))
    audit("autosave", "strategy_profiles", "1", {"source_upload_id": values.get("source_upload_id")})
    return result


def get_strategic_assessment(quarter: str) -> dict[str, Any]:
    return _first(_store().select("strategic_assessments", {"quarter": quarter}, limit=1))


def upsert_strategic_assessment(quarter: str, payload: dict[str, Any]) -> dict[str, Any]:
    if quarter not in QUARTERS:
        raise ValueError("Invalid quarter")
    existing = get_strategic_assessment(quarter)
    fields = ["reputation_score", "ethics_score", "partnerships_score", "market_trend_score", "source", "notes"]
    values = {"quarter": quarter, **{key: payload.get(key, existing.get(key)) for key in fields}, "updated_at": utc_now()}
    result = _first(_store().upsert("strategic_assessments", values, "quarter"))
    audit("autosave", "strategic_assessments", quarter)
    return result


def list_scenario_portfolios(quarter: str | None = None) -> list[dict[str, Any]]:
    return _store().select("scenario_portfolios", {"quarter": quarter} if quarter else None, order="created_at", descending=True)


def add_scenario_portfolio(payload: dict[str, Any]) -> dict[str, Any]:
    now = utc_now()
    values = {
        "quarter": payload.get("quarter", "Q4"),
        "name": payload.get("name", "תרחיש חדש"),
        "objective": payload.get("objective", "מקסום ציון Q9"),
        "budget_sf": payload.get("budget_sf", 0),
        "cash_buffer_sf": payload.get("cash_buffer_sf", 0),
        "actions": payload.get("actions", []),
        "result": payload.get("result", {}),
        "status": payload.get("status", "טיוטה"),
        "created_at": now,
        "updated_at": now,
    }
    result = _store().insert("scenario_portfolios", values)
    audit("create", "scenario_portfolios", str(result["id"]), {"quarter": values["quarter"], "name": values["name"]})
    return result


def delete_scenario_portfolio(portfolio_id: str) -> None:
    _store().delete("scenario_portfolios", {"id": portfolio_id})
    audit("delete", "scenario_portfolios", portfolio_id)


def upsert_quarter_snapshot(quarter: str, payload: dict[str, Any], locked: bool = False) -> dict[str, Any]:
    now = utc_now()
    existing = _first(_store().select("quarter_snapshots", {"quarter": quarter}, limit=1))
    values = {
        "quarter": quarter,
        "payload": payload,
        "locked": bool(locked),
        "created_at": existing.get("created_at", now),
        "updated_at": now,
    }
    result = _first(_store().upsert("quarter_snapshots", values, "quarter"))
    audit("snapshot", "quarter_snapshots", quarter, {"locked": bool(locked)})
    return result


def list_agent_threads() -> list[dict[str, Any]]:
    return _store().select("agent_threads", order="updated_at", descending=True)


def add_agent_thread(title: str, quarter: str) -> dict[str, Any]:
    now = utc_now()
    return _store().insert("agent_threads", {"title": title or "שיחה חדשה", "quarter": quarter, "created_at": now, "updated_at": now})


def list_agent_messages(thread_id: str) -> list[dict[str, Any]]:
    return _store().select("agent_messages", {"thread_id": thread_id}, order="created_at")


def add_agent_message(thread_id: str, role: str, content: str, citations: list[str] | None = None) -> dict[str, Any]:
    if role not in {"user", "assistant"}:
        raise ValueError("Invalid agent message role")
    result = _store().insert(
        "agent_messages",
        {"thread_id": thread_id, "role": role, "content": content, "citations": citations or [], "created_at": utc_now()},
    )
    _store().update("agent_threads", {"id": thread_id}, {"updated_at": utc_now()})
    return result


def get_strategy() -> dict[str, Any]:
    return {
        "profile": get_strategy_profile(),
        "principles": _sorted(_store().select("strategy_principles"), "id"),
        "milestones": _sorted(_store().select("milestones"), "quarter"),
    }


def dashboard_for_quarter(quarter: str) -> dict[str, Any]:
    finance = get_finance(quarter)
    operations = get_operations(quarter)
    dashboard: dict[str, Any] = {
        "quarter": quarter,
        "has_finance": bool(finance),
        "has_operations": bool(operations),
        "has_any_data": bool(finance) or bool(operations),
        "revenue_sf": finance.get("revenue_sf", 0),
        "gross_profit_sf": finance.get("gross_profit_sf", 0),
        "net_profit_sf": finance.get("net_profit_sf", 0),
        "ending_cash_sf": finance.get("ending_cash_sf", 0),
        "debt_sf": finance.get("debt_sf", 0),
        "units_sold": sum(float(row.get("actual_sales") or 0) for row in operations),
        "ending_inventory": sum(float(row.get("ending_inventory") or 0) for row in operations),
        "planned_sales": sum(float(row.get("planned_sales") or 0) for row in operations),
        "planned_production": sum(float(row.get("planned_production") or 0) for row in operations),
        "actual_production": sum(float(row.get("actual_production") or 0) for row in operations),
        "max_x_grade": max([int(row.get("grade") or 0) for row in operations if row.get("product") == "X"] or [0]),
        "max_y_grade": max([int(row.get("grade") or 0) for row in operations if row.get("product") == "Y"] or [0]),
    }
    by_area: list[dict[str, Any]] = []
    for area in ("US", "EU", "Brazil", "Liechtenstein"):
        rows = [row for row in operations if row.get("area") == area]
        by_area.append(
            {
                "area": area,
                "has_data": bool(rows),
                "units_sold": sum(float(row.get("actual_sales") or 0) for row in rows),
                "ending_inventory": sum(float(row.get("ending_inventory") or 0) for row in rows),
                "actual_production": sum(float(row.get("actual_production") or 0) for row in rows),
                "advertising_lc": sum(float(row.get("advertising_lc") or 0) for row in rows),
                "avg_market_share": (sum(float(row.get("actual_market_share") or 0) for row in rows) / len(rows)) if rows else 0,
            }
        )
    dashboard["by_area"] = by_area
    return dashboard


def onboarding_status(quarter: str) -> dict[str, Any]:
    settings = get_settings()
    uploads = list_uploads()
    categories = {str(row.get("category") or "") for row in uploads}
    steps = [
        {"key": "company", "label": "הגדרת שם החברה", "done": bool((settings.get("company_name") or "").strip()), "target": "settings"},
        {"key": "strategy", "label": "העלאת אסטרטגיה ראשונית", "done": "אסטרטגיה ראשונית" in categories, "target": "data"},
        {"key": "goals", "label": "העלאת יעדי Q9", "done": "יעדי Q9" in categories, "target": "data"},
        {"key": "rules", "label": "העלאת Datalog / כללי המשחק", "done": "Datalog / כללי משחק" in categories, "target": "data"},
        *[
            {
                "key": f"report-{item}",
                "label": f"העלאת ואישור פלט {item}",
                "done": bool(get_finance(item)) or bool(get_operations(item)),
                "target": "files",
            }
            for item in ("Q1", "Q2", "Q3")
        ],
        {
            "key": "structured",
            "label": "תמונת פתיחה לתכנון Q4",
            "done": all(bool(get_finance(item)) or bool(get_operations(item)) for item in ("Q1", "Q2", "Q3")),
            "target": "quarter",
        },
    ]
    approved_profile = get_strategy_profile()
    for step in steps:
        if step["key"] == "strategy":
            step["done"] = bool(approved_profile.get("thesis"))
        elif step["key"] == "goals":
            step["done"] = bool(approved_profile.get("goals"))
    completed = sum(1 for step in steps if step["done"])
    return {"steps": steps, "completed": completed, "total": len(steps), "ready": completed == len(steps)}


def dashboard_history() -> list[dict[str, Any]]:
    return [dashboard_for_quarter(quarter) for quarter in QUARTERS]


def export_all_data() -> dict[str, list[dict[str, Any]]]:
    return {table: _store().select(table) for table in TABLES}


def restore_table_rows(table: str, rows: list[dict[str, Any]]) -> int:
    if table not in TABLES:
        raise ValueError(f"Unsupported table in backup: {table}")
    if not rows:
        return 0
    conflict = CONFLICT_COLUMNS[table]
    for start in range(0, len(rows), 200):
        _store().upsert(table, rows[start : start + 200], conflict)
    return len(rows)


def clear_all_tables() -> None:
    for table in ALL_TABLES_DELETE_ORDER:
        _store().clear_table(table, KEY_COLUMNS[table])


def reset_company_data(delete_files: bool = True) -> None:
    if delete_files:
        for record in list_uploads():
            try:
                storage_delete(str(record.get("storage_path") or ""))
            except Exception:
                continue
    for table in COMPANY_TABLES_DELETE_ORDER:
        _store().clear_table(table, KEY_COLUMNS[table])
    init_db()

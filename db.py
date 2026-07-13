from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from seed_data import AREA_PRODUCT_DEFAULTS, MARKET_RESEARCH, MILESTONES, QUARTERS, STRATEGY_PRINCIPLES

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("INTOPIA_DATA_DIR", BASE_DIR / "data"))
DB_PATH = DATA_DIR / "intopia.db"
UPLOAD_DIR = DATA_DIR / "uploads"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connect():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def rows_to_dicts(rows: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(r) for r in rows]


def init_db() -> None:
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                company_name TEXT NOT NULL DEFAULT '',
                selected_quarter TEXT NOT NULL DEFAULT 'Q1',
                cash_buffer_sf REAL NOT NULL DEFAULT 0,
                min_rd_sf REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS reference_area_product (
                area TEXT NOT NULL,
                product TEXT NOT NULL,
                currency TEXT NOT NULL,
                fx_to_sf REAL NOT NULL,
                tax_rate REAL NOT NULL,
                plant_capacity REAL NOT NULL,
                plant_cost_lc REAL NOT NULL,
                initial_price_lc REAL NOT NULL,
                inventory_cost REAL NOT NULL,
                PRIMARY KEY (area, product)
            );

            CREATE TABLE IF NOT EXISTS quarter_finance (
                quarter TEXT PRIMARY KEY,
                revenue_sf REAL NOT NULL DEFAULT 0,
                gross_profit_sf REAL NOT NULL DEFAULT 0,
                net_profit_sf REAL NOT NULL DEFAULT 0,
                ending_cash_sf REAL NOT NULL DEFAULT 0,
                debt_sf REAL NOT NULL DEFAULT 0,
                ar_sf REAL NOT NULL DEFAULT 0,
                ap_sf REAL NOT NULL DEFAULT 0,
                research_budget_sf REAL NOT NULL DEFAULT 0,
                rd_x_sf REAL NOT NULL DEFAULT 0,
                rd_y_sf REAL NOT NULL DEFAULT 0,
                partnership_score REAL NOT NULL DEFAULT 0,
                dividends_sf REAL NOT NULL DEFAULT 0,
                notes TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS operations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                quarter TEXT NOT NULL,
                area TEXT NOT NULL,
                product TEXT NOT NULL,
                model TEXT NOT NULL,
                grade INTEGER NOT NULL DEFAULT 0,
                plants REAL NOT NULL DEFAULT 0,
                plant_capacity REAL NOT NULL DEFAULT 0,
                planned_production REAL NOT NULL DEFAULT 0,
                actual_production REAL NOT NULL DEFAULT 0,
                opening_inventory REAL NOT NULL DEFAULT 0,
                planned_sales REAL NOT NULL DEFAULT 0,
                actual_sales REAL NOT NULL DEFAULT 0,
                ending_inventory REAL NOT NULL DEFAULT 0,
                forecast_demand REAL NOT NULL DEFAULT 0,
                planned_price_lc REAL NOT NULL DEFAULT 0,
                actual_price_lc REAL NOT NULL DEFAULT 0,
                advertising_lc REAL NOT NULL DEFAULT 0,
                variable_cost_lc REAL NOT NULL DEFAULT 0,
                fixed_cost_lc REAL NOT NULL DEFAULT 0,
                methods_improvement_lc REAL NOT NULL DEFAULT 0,
                sales_channel TEXT NOT NULL DEFAULT 'Agents',
                actual_market_share REAL NOT NULL DEFAULT 0,
                source TEXT NOT NULL DEFAULT '',
                confidence TEXT NOT NULL DEFAULT 'בינונית',
                notes TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL,
                UNIQUE (quarter, area, product, model)
            );

            CREATE TABLE IF NOT EXISTS facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                quarter TEXT NOT NULL,
                source_type TEXT NOT NULL,
                source_name TEXT NOT NULL DEFAULT '',
                area TEXT NOT NULL DEFAULT '',
                product TEXT NOT NULL DEFAULT '',
                company TEXT NOT NULL DEFAULT '',
                metric TEXT NOT NULL,
                value REAL,
                text_value TEXT NOT NULL DEFAULT '',
                unit TEXT NOT NULL DEFAULT '',
                confidence TEXT NOT NULL DEFAULT 'בינונית',
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS uploads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                quarter TEXT NOT NULL,
                category TEXT NOT NULL,
                original_name TEXT NOT NULL,
                stored_name TEXT NOT NULL,
                stored_path TEXT NOT NULL,
                mime_type TEXT NOT NULL DEFAULT '',
                size_bytes INTEGER NOT NULL DEFAULT 0,
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                quarter TEXT NOT NULL,
                domain TEXT NOT NULL,
                title TEXT NOT NULL,
                question TEXT NOT NULL DEFAULT '',
                selected_option TEXT NOT NULL DEFAULT '',
                rationale TEXT NOT NULL DEFAULT '',
                owner TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'פתוח',
                expected_result TEXT NOT NULL DEFAULT '',
                actual_result TEXT NOT NULL DEFAULT '',
                confidence TEXT NOT NULL DEFAULT 'בינונית',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS scenarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                quarter TEXT NOT NULL,
                name TEXT NOT NULL,
                area TEXT NOT NULL,
                product TEXT NOT NULL,
                grade INTEGER NOT NULL DEFAULT 0,
                price_lc REAL NOT NULL DEFAULT 0,
                demand REAL NOT NULL DEFAULT 0,
                production REAL NOT NULL DEFAULT 0,
                opening_inventory REAL NOT NULL DEFAULT 0,
                variable_cost_lc REAL NOT NULL DEFAULT 0,
                advertising_lc REAL NOT NULL DEFAULT 0,
                fixed_cost_lc REAL NOT NULL DEFAULT 0,
                transport_per_unit_lc REAL NOT NULL DEFAULT 0,
                inventory_cost_per_unit_lc REAL NOT NULL DEFAULT 0,
                tax_rate REAL NOT NULL DEFAULT 0,
                fx_to_sf REAL NOT NULL DEFAULT 1,
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                quarter TEXT NOT NULL,
                name TEXT NOT NULL,
                hypothesis TEXT NOT NULL DEFAULT '',
                changed_variables TEXT NOT NULL DEFAULT '',
                expected_result TEXT NOT NULL DEFAULT '',
                actual_result TEXT NOT NULL DEFAULT '',
                decision TEXT NOT NULL DEFAULT '',
                confidence TEXT NOT NULL DEFAULT 'בינונית',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS market_research_catalog (
                study_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                cost_k_sf REAL,
                use_case TEXT NOT NULL,
                default_priority TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS research_plan (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                quarter TEXT NOT NULL,
                study_id INTEGER NOT NULL,
                decision_supported TEXT NOT NULL DEFAULT '',
                key_result TEXT NOT NULL DEFAULT '',
                action TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'מתוכנן',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE (quarter, study_id),
                FOREIGN KEY (study_id) REFERENCES market_research_catalog(study_id)
            );

            CREATE TABLE IF NOT EXISTS strategy_principles (
                id INTEGER PRIMARY KEY,
                principle TEXT NOT NULL,
                rationale TEXT NOT NULL,
                leading_metric TEXT NOT NULL,
                decision_gate TEXT NOT NULL,
                status TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS milestones (
                quarter TEXT PRIMARY KEY,
                strategic_goal TEXT NOT NULL,
                required_signal TEXT NOT NULL,
                positive_action TEXT NOT NULL,
                negative_action TEXT NOT NULL,
                investment_sf REAL NOT NULL DEFAULT 0,
                owner TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'לא התחיל',
                result TEXT NOT NULL DEFAULT '',
                strategic_update TEXT NOT NULL DEFAULT ''
            );
            """
        )

        now = utc_now()
        conn.execute(
            "INSERT OR IGNORE INTO settings (id, company_name, selected_quarter, cash_buffer_sf, min_rd_sf, created_at, updated_at) VALUES (1, '', 'Q1', 0, 0, ?, ?)",
            (now, now),
        )
        # Clean profile: no finance rows, operational rows, strategy or pricing
        # assumptions are created until the user uploads or enters them.
        if AREA_PRODUCT_DEFAULTS:
            conn.executemany(
                """
                INSERT OR IGNORE INTO reference_area_product
                (area, product, currency, fx_to_sf, tax_rate, plant_capacity, plant_cost_lc, initial_price_lc, inventory_cost)
                VALUES (:area, :product, :currency, :fx_to_sf, :tax_rate, :plant_capacity, :plant_cost_lc, :initial_price_lc, :inventory_cost)
                """,
                AREA_PRODUCT_DEFAULTS,
            )
        conn.executemany(
            "INSERT OR IGNORE INTO market_research_catalog (study_id, name, description, cost_k_sf, use_case, default_priority, note) VALUES (?, ?, ?, ?, ?, ?, ?)",
            MARKET_RESEARCH,
        )
        conn.executemany(
            "INSERT OR IGNORE INTO strategy_principles (id, principle, rationale, leading_metric, decision_gate, status) VALUES (?, ?, ?, ?, ?, ?)",
            STRATEGY_PRINCIPLES,
        )
        conn.executemany(
            "INSERT OR IGNORE INTO milestones (quarter, strategic_goal, required_signal, positive_action, negative_action) VALUES (?, ?, ?, ?, ?)",
            MILESTONES,
        )


def get_settings() -> dict[str, Any]:
    with connect() as conn:
        return dict(conn.execute("SELECT * FROM settings WHERE id=1").fetchone())


def update_settings(payload: dict[str, Any]) -> dict[str, Any]:
    allowed = {"company_name", "selected_quarter", "cash_buffer_sf", "min_rd_sf"}
    fields = {k: payload[k] for k in allowed if k in payload}
    if not fields:
        return get_settings()
    fields["updated_at"] = utc_now()
    set_sql = ", ".join(f"{k} = :{k}" for k in fields)
    with connect() as conn:
        conn.execute(f"UPDATE settings SET {set_sql} WHERE id=1", fields)
    return get_settings()


def get_reference_data() -> list[dict[str, Any]]:
    with connect() as conn:
        return rows_to_dicts(conn.execute("SELECT * FROM reference_area_product ORDER BY area, product"))


def get_finance(quarter: str) -> dict[str, Any]:
    with connect() as conn:
        row = conn.execute("SELECT * FROM quarter_finance WHERE quarter = ?", (quarter,)).fetchone()
        return dict(row) if row else {}


def upsert_finance(quarter: str, payload: dict[str, Any]) -> dict[str, Any]:
    allowed = [
        "revenue_sf", "gross_profit_sf", "net_profit_sf", "ending_cash_sf", "debt_sf", "ar_sf", "ap_sf",
        "research_budget_sf", "rd_x_sf", "rd_y_sf", "partnership_score", "dividends_sf", "notes",
    ]
    values = {k: payload.get(k, 0 if k != "notes" else "") for k in allowed}
    values.update({"quarter": quarter, "updated_at": utc_now()})
    columns = ", ".join(values)
    placeholders = ", ".join(f":{k}" for k in values)
    updates = ", ".join(f"{k}=excluded.{k}" for k in allowed + ["updated_at"])
    with connect() as conn:
        conn.execute(
            f"INSERT INTO quarter_finance ({columns}) VALUES ({placeholders}) ON CONFLICT(quarter) DO UPDATE SET {updates}", values
        )
    return get_finance(quarter)


def get_operations(quarter: str) -> list[dict[str, Any]]:
    with connect() as conn:
        return rows_to_dicts(conn.execute("SELECT * FROM operations WHERE quarter=? ORDER BY area, product, model", (quarter,)))


def upsert_operation(payload: dict[str, Any]) -> dict[str, Any]:
    required = ["quarter", "area", "product", "model"]
    for field in required:
        if not payload.get(field):
            raise ValueError(f"Missing required field: {field}")
    allowed = [
        "quarter", "area", "product", "model", "grade", "plants", "plant_capacity", "planned_production",
        "actual_production", "opening_inventory", "planned_sales", "actual_sales", "ending_inventory", "forecast_demand",
        "planned_price_lc", "actual_price_lc", "advertising_lc", "variable_cost_lc", "fixed_cost_lc",
        "methods_improvement_lc", "sales_channel", "actual_market_share", "source", "confidence", "notes",
    ]
    values = {k: payload.get(k, "" if k in {"sales_channel", "source", "confidence", "notes"} else 0) for k in allowed}
    values["updated_at"] = utc_now()
    columns = ", ".join(values)
    placeholders = ", ".join(f":{k}" for k in values)
    update_fields = [k for k in allowed if k not in required] + ["updated_at"]
    updates = ", ".join(f"{k}=excluded.{k}" for k in update_fields)
    with connect() as conn:
        conn.execute(
            f"INSERT INTO operations ({columns}) VALUES ({placeholders}) ON CONFLICT(quarter, area, product, model) DO UPDATE SET {updates}",
            values,
        )
        row = conn.execute("SELECT * FROM operations WHERE quarter=? AND area=? AND product=? AND model=?", tuple(values[k] for k in required)).fetchone()
        return dict(row)


def list_facts(quarter: str | None = None, limit: int = 500) -> list[dict[str, Any]]:
    with connect() as conn:
        if quarter:
            rows = conn.execute("SELECT * FROM facts WHERE quarter=? ORDER BY id DESC LIMIT ?", (quarter, limit))
        else:
            rows = conn.execute("SELECT * FROM facts ORDER BY id DESC LIMIT ?", (limit,))
        return rows_to_dicts(rows)


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
    with connect() as conn:
        cur = conn.execute(
            """INSERT INTO facts (quarter, source_type, source_name, area, product, company, metric, value, text_value, unit, confidence, notes, created_at)
               VALUES (:quarter, :source_type, :source_name, :area, :product, :company, :metric, :value, :text_value, :unit, :confidence, :notes, :created_at)""",
            values,
        )
        values["id"] = cur.lastrowid
    return values


def delete_fact(fact_id: int) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM facts WHERE id=?", (fact_id,))


def list_uploads(quarter: str | None = None) -> list[dict[str, Any]]:
    with connect() as conn:
        if quarter:
            rows = conn.execute("SELECT * FROM uploads WHERE quarter=? ORDER BY id DESC", (quarter,))
        else:
            rows = conn.execute("SELECT * FROM uploads ORDER BY id DESC")
        return rows_to_dicts(rows)


def add_upload(payload: dict[str, Any]) -> dict[str, Any]:
    values = {**payload, "created_at": utc_now()}
    with connect() as conn:
        cur = conn.execute(
            """INSERT INTO uploads (quarter, category, original_name, stored_name, stored_path, mime_type, size_bytes, notes, created_at)
               VALUES (:quarter, :category, :original_name, :stored_name, :stored_path, :mime_type, :size_bytes, :notes, :created_at)""",
            values,
        )
        values["id"] = cur.lastrowid
    return values


def list_decisions(quarter: str | None = None) -> list[dict[str, Any]]:
    with connect() as conn:
        if quarter:
            rows = conn.execute("SELECT * FROM decisions WHERE quarter=? ORDER BY id DESC", (quarter,))
        else:
            rows = conn.execute("SELECT * FROM decisions ORDER BY id DESC")
        return rows_to_dicts(rows)


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
    with connect() as conn:
        cur = conn.execute(
            """INSERT INTO decisions (quarter, domain, title, question, selected_option, rationale, owner, status, expected_result, actual_result, confidence, created_at, updated_at)
               VALUES (:quarter, :domain, :title, :question, :selected_option, :rationale, :owner, :status, :expected_result, :actual_result, :confidence, :created_at, :updated_at)""",
            values,
        )
        values["id"] = cur.lastrowid
    return values


def update_decision(decision_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    allowed = {"domain", "title", "question", "selected_option", "rationale", "owner", "status", "expected_result", "actual_result", "confidence"}
    values = {k: payload[k] for k in allowed if k in payload}
    values["updated_at"] = utc_now()
    values["id"] = decision_id
    set_sql = ", ".join(f"{k}=:{k}" for k in values if k != "id")
    with connect() as conn:
        conn.execute(f"UPDATE decisions SET {set_sql} WHERE id=:id", values)
        row = conn.execute("SELECT * FROM decisions WHERE id=?", (decision_id,)).fetchone()
        if not row:
            raise KeyError("decision not found")
        return dict(row)


def list_scenarios(quarter: str) -> list[dict[str, Any]]:
    with connect() as conn:
        return rows_to_dicts(conn.execute("SELECT * FROM scenarios WHERE quarter=? ORDER BY name, area, product, id", (quarter,)))


def add_scenario(payload: dict[str, Any]) -> dict[str, Any]:
    now = utc_now()
    text_fields = {"quarter", "name", "area", "product", "notes"}
    allowed = [
        "quarter", "name", "area", "product", "grade", "price_lc", "demand", "production", "opening_inventory",
        "variable_cost_lc", "advertising_lc", "fixed_cost_lc", "transport_per_unit_lc", "inventory_cost_per_unit_lc",
        "tax_rate", "fx_to_sf", "notes",
    ]
    values = {k: payload.get(k, "" if k in text_fields else 0) for k in allowed}
    values["created_at"] = now
    values["updated_at"] = now
    if not values["name"]:
        raise ValueError("name is required")
    columns = ", ".join(values)
    placeholders = ", ".join(f":{k}" for k in values)
    with connect() as conn:
        cur = conn.execute(f"INSERT INTO scenarios ({columns}) VALUES ({placeholders})", values)
        values["id"] = cur.lastrowid
    return values


def delete_scenario(scenario_id: int) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM scenarios WHERE id=?", (scenario_id,))


def list_tests(quarter: str | None = None) -> list[dict[str, Any]]:
    with connect() as conn:
        if quarter:
            rows = conn.execute("SELECT * FROM tests WHERE quarter=? ORDER BY id DESC", (quarter,))
        else:
            rows = conn.execute("SELECT * FROM tests ORDER BY id DESC")
        return rows_to_dicts(rows)


def add_test(payload: dict[str, Any]) -> dict[str, Any]:
    now = utc_now()
    values = {
        "quarter": payload.get("quarter", "Q1"), "name": payload.get("name", ""), "hypothesis": payload.get("hypothesis", ""),
        "changed_variables": payload.get("changed_variables", ""), "expected_result": payload.get("expected_result", ""),
        "actual_result": payload.get("actual_result", ""), "decision": payload.get("decision", ""),
        "confidence": payload.get("confidence", "בינונית"), "created_at": now, "updated_at": now,
    }
    if not values["name"]:
        raise ValueError("name is required")
    with connect() as conn:
        cur = conn.execute(
            """INSERT INTO tests (quarter, name, hypothesis, changed_variables, expected_result, actual_result, decision, confidence, created_at, updated_at)
               VALUES (:quarter, :name, :hypothesis, :changed_variables, :expected_result, :actual_result, :decision, :confidence, :created_at, :updated_at)""",
            values,
        )
        values["id"] = cur.lastrowid
    return values


def get_market_research_catalog() -> list[dict[str, Any]]:
    with connect() as conn:
        return rows_to_dicts(conn.execute("SELECT * FROM market_research_catalog ORDER BY study_id"))


def get_research_plan(quarter: str) -> list[dict[str, Any]]:
    with connect() as conn:
        return rows_to_dicts(
            conn.execute(
                """SELECT rp.*, c.name, c.cost_k_sf, c.description, c.use_case, c.default_priority
                   FROM research_plan rp JOIN market_research_catalog c ON c.study_id=rp.study_id
                   WHERE rp.quarter=? ORDER BY rp.id""", (quarter,)
            )
        )


def upsert_research_plan(payload: dict[str, Any]) -> dict[str, Any]:
    now = utc_now()
    values = {
        "quarter": payload.get("quarter", "Q1"), "study_id": int(payload.get("study_id")),
        "decision_supported": payload.get("decision_supported", ""), "key_result": payload.get("key_result", ""),
        "action": payload.get("action", ""), "status": payload.get("status", "מתוכנן"),
        "created_at": now, "updated_at": now,
    }
    with connect() as conn:
        conn.execute(
            """INSERT INTO research_plan (quarter, study_id, decision_supported, key_result, action, status, created_at, updated_at)
               VALUES (:quarter, :study_id, :decision_supported, :key_result, :action, :status, :created_at, :updated_at)
               ON CONFLICT(quarter, study_id) DO UPDATE SET decision_supported=excluded.decision_supported, key_result=excluded.key_result,
               action=excluded.action, status=excluded.status, updated_at=excluded.updated_at""", values
        )
        row = conn.execute(
            """SELECT rp.*, c.name, c.cost_k_sf FROM research_plan rp JOIN market_research_catalog c ON c.study_id=rp.study_id
               WHERE rp.quarter=? AND rp.study_id=?""", (values["quarter"], values["study_id"])
        ).fetchone()
        return dict(row)


def get_strategy() -> dict[str, Any]:
    with connect() as conn:
        return {
            "principles": rows_to_dicts(conn.execute("SELECT * FROM strategy_principles ORDER BY id")),
            "milestones": rows_to_dicts(conn.execute("SELECT * FROM milestones ORDER BY quarter")),
        }


def dashboard_for_quarter(quarter: str) -> dict[str, Any]:
    finance = get_finance(quarter)
    operations = get_operations(quarter)
    has_finance = bool(finance)
    has_operations = bool(operations)
    dashboard = {
        "quarter": quarter,
        "has_finance": has_finance,
        "has_operations": has_operations,
        "has_any_data": has_finance or has_operations,
        "revenue_sf": finance.get("revenue_sf", 0),
        "gross_profit_sf": finance.get("gross_profit_sf", 0),
        "net_profit_sf": finance.get("net_profit_sf", 0),
        "ending_cash_sf": finance.get("ending_cash_sf", 0),
        "debt_sf": finance.get("debt_sf", 0),
        "units_sold": sum(float(o.get("actual_sales") or 0) for o in operations),
        "ending_inventory": sum(float(o.get("ending_inventory") or 0) for o in operations),
        "planned_sales": sum(float(o.get("planned_sales") or 0) for o in operations),
        "planned_production": sum(float(o.get("planned_production") or 0) for o in operations),
        "actual_production": sum(float(o.get("actual_production") or 0) for o in operations),
        "max_x_grade": max([int(o.get("grade") or 0) for o in operations if o.get("product") == "X"] or [0]),
        "max_y_grade": max([int(o.get("grade") or 0) for o in operations if o.get("product") == "Y"] or [0]),
    }
    by_area: list[dict[str, Any]] = []
    for area in ("US", "EU", "Brazil", "Liechtenstein"):
        rows = [o for o in operations if o.get("area") == area]
        by_area.append({
            "area": area,
            "has_data": bool(rows),
            "units_sold": sum(float(o.get("actual_sales") or 0) for o in rows),
            "ending_inventory": sum(float(o.get("ending_inventory") or 0) for o in rows),
            "actual_production": sum(float(o.get("actual_production") or 0) for o in rows),
            "advertising_lc": sum(float(o.get("advertising_lc") or 0) for o in rows),
            "avg_market_share": (sum(float(o.get("actual_market_share") or 0) for o in rows) / len(rows)) if rows else 0,
        })
    dashboard["by_area"] = by_area
    return dashboard


def onboarding_status(quarter: str) -> dict[str, Any]:
    settings = get_settings()
    uploads = list_uploads()
    categories = {str(r.get("category") or "") for r in uploads}
    quarter_uploads = [r for r in uploads if r.get("quarter") in {quarter, "Setup"}]
    finance = get_finance(quarter)
    operations = get_operations(quarter)
    steps = [
        {"key": "company", "label": "הגדרת שם החברה", "done": bool((settings.get("company_name") or "").strip()), "target": "settings"},
        {"key": "strategy", "label": "העלאת אסטרטגיה ראשונית", "done": "אסטרטגיה ראשונית" in categories, "target": "data"},
        {"key": "goals", "label": "העלאת יעדי Q9", "done": "יעדי Q9" in categories, "target": "data"},
        {"key": "rules", "label": "העלאת Datalog / כללי המשחק", "done": "Datalog / כללי משחק" in categories, "target": "data"},
        {"key": "quarter", "label": f"העלאת פלט {quarter} או Q1–Q3", "done": any(r.get("category") in {"Q1–Q3 משולב", "דוח רבעוני"} for r in quarter_uploads), "target": "data"},
        {"key": "structured", "label": "אישור נתונים מובנים לרבעון", "done": bool(finance) or bool(operations), "target": "quarter"},
    ]
    completed = sum(1 for step in steps if step["done"])
    return {"steps": steps, "completed": completed, "total": len(steps), "ready": completed == len(steps)}

def dashboard_history() -> list[dict[str, Any]]:
    return [dashboard_for_quarter(q) for q in QUARTERS]


def export_all_data() -> dict[str, Any]:
    with connect() as conn:
        tables = [
            "settings", "reference_area_product", "quarter_finance", "operations", "facts", "uploads", "decisions",
            "scenarios", "tests", "market_research_catalog", "research_plan", "strategy_principles", "milestones",
        ]
        return {table: rows_to_dicts(conn.execute(f"SELECT * FROM {table}")) for table in tables}


init_db()

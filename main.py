from __future__ import annotations

import csv
import io
import json
import mimetypes
import os
import re
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles

import db
from logic import build_summary, decision_gates, loan_plan, scenario_calculation, unit_economics_calculation
from seed_data import AREAS, CHANNELS, CONFIDENCE_LEVELS, MODELS, PRODUCTS, QUARTERS, STATUS_LEVELS, XY_CONVERSION, PRICING_DEFAULTS

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="INTOPIA DSS", version="0.3.0-clean")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def safe_filename(name: str) -> str:
    base = Path(name or "file").name
    base = re.sub(r"[^\w.\-\u0590-\u05FF]+", "_", base, flags=re.UNICODE)
    return base[:160] or "file"


@app.get("/", response_class=HTMLResponse)
def index():
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")


@app.get("/api/meta")
def meta():
    return {
        "quarters": QUARTERS,
        "areas": AREAS,
        "products": PRODUCTS,
        "models": MODELS,
        "confidence": CONFIDENCE_LEVELS,
        "statuses": STATUS_LEVELS,
        "channels": CHANNELS,
        "xy_conversion": XY_CONVERSION,
        "reference": db.get_reference_data(),
        "pricing_defaults": PRICING_DEFAULTS,
        "upload_periods": ["Setup", *QUARTERS],
        "upload_categories": [
            "אסטרטגיה ראשונית", "יעדי Q9", "Datalog / כללי משחק", "Q1–Q3 משולב",
            "דוח רבעוני", "מחקר שוק", "Gazette", "הסכם / עסקה", "צילום / מסמך", "אחר"
        ],
    }


@app.get("/api/settings")
def get_settings():
    return db.get_settings()


@app.put("/api/settings")
def put_settings(payload: dict[str, Any]):
    return db.update_settings(payload)


@app.get("/api/dashboard/{quarter}")
def dashboard(quarter: str):
    if quarter not in QUARTERS:
        raise HTTPException(400, "רבעון לא תקין")
    dash = db.dashboard_for_quarter(quarter)
    operations = db.get_operations(quarter)
    finance = db.get_finance(quarter)
    gates = decision_gates(db.get_settings(), finance, operations)
    return {
        "dashboard": dash,
        "gates": gates,
        "history": db.dashboard_history(),
        "onboarding": db.onboarding_status(quarter),
    }


@app.get("/api/finance/{quarter}")
def get_finance(quarter: str):
    return db.get_finance(quarter)


@app.put("/api/finance/{quarter}")
def put_finance(quarter: str, payload: dict[str, Any]):
    try:
        return db.upsert_finance(quarter, payload)
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/operations/{quarter}")
def get_operations(quarter: str):
    return db.get_operations(quarter)


@app.put("/api/operations")
def put_operation(payload: dict[str, Any]):
    try:
        return db.upsert_operation(payload)
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/facts")
def get_facts(quarter: str | None = None):
    return db.list_facts(quarter)


@app.post("/api/facts")
def post_fact(payload: dict[str, Any]):
    try:
        return db.add_fact(payload)
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc


@app.delete("/api/facts/{fact_id}", status_code=204)
def remove_fact(fact_id: int):
    db.delete_fact(fact_id)
    return Response(status_code=204)


@app.get("/api/uploads")
def get_uploads(quarter: str | None = None):
    return db.list_uploads(quarter)


@app.post("/api/uploads")
async def upload_file(
    file: UploadFile = File(...),
    quarter: str = Form("Setup"),
    category: str = Form("דוח"),
    notes: str = Form(""),
):
    if quarter not in ["Setup", *QUARTERS]:
        raise HTTPException(400, "תקופה לא תקינה")
    original = safe_filename(file.filename or "file")
    stored = f"{uuid.uuid4().hex}_{original}"
    path = db.UPLOAD_DIR / stored
    content = await file.read()
    path.write_bytes(content)
    record = db.add_upload({
        "quarter": quarter,
        "category": category,
        "original_name": original,
        "stored_name": stored,
        "stored_path": str(path),
        "mime_type": file.content_type or mimetypes.guess_type(original)[0] or "application/octet-stream",
        "size_bytes": len(content),
        "notes": notes,
    })
    return record


@app.get("/api/uploads/{upload_id}/download")
def download_upload(upload_id: int):
    records = [r for r in db.list_uploads() if r["id"] == upload_id]
    if not records:
        raise HTTPException(404, "קובץ לא נמצא")
    record = records[0]
    path = Path(record["stored_path"])
    if not path.exists():
        raise HTTPException(404, "הקובץ הפיזי לא נמצא")
    return FileResponse(path, filename=record["original_name"], media_type=record["mime_type"])


@app.get("/api/decisions")
def get_decisions(quarter: str | None = None):
    return db.list_decisions(quarter)


@app.post("/api/decisions")
def post_decision(payload: dict[str, Any]):
    try:
        return db.add_decision(payload)
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc


@app.put("/api/decisions/{decision_id}")
def put_decision(decision_id: int, payload: dict[str, Any]):
    try:
        return db.update_decision(decision_id, payload)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/gates/{quarter}")
def get_gates(quarter: str):
    return decision_gates(db.get_settings(), db.get_finance(quarter), db.get_operations(quarter))


@app.get("/api/scenarios/{quarter}")
def get_scenarios(quarter: str):
    rows = db.list_scenarios(quarter)
    return [{**row, "result": scenario_calculation(row)} for row in rows]


@app.post("/api/scenarios")
def post_scenario(payload: dict[str, Any]):
    try:
        row = db.add_scenario(payload)
        return {**row, "result": scenario_calculation(row)}
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/scenarios/calculate")
def calculate_scenario(payload: dict[str, Any]):
    return scenario_calculation(payload)


@app.delete("/api/scenarios/{scenario_id}", status_code=204)
def remove_scenario(scenario_id: int):
    db.delete_scenario(scenario_id)
    return Response(status_code=204)




@app.post("/api/economics/calculate")
def calculate_unit_economics(payload: dict[str, Any]):
    try:
        return unit_economics_calculation(payload)
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc

@app.post("/api/loan/calculate")
def calculate_loan(payload: dict[str, Any]):
    return loan_plan(payload.get("amount", 0), bool(payload.get("balloon", False)))


@app.get("/api/tests")
def get_tests(quarter: str | None = None):
    return db.list_tests(quarter)


@app.post("/api/tests")
def post_test(payload: dict[str, Any]):
    try:
        return db.add_test(payload)
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/research/catalog")
def get_research_catalog():
    return db.get_market_research_catalog()


@app.get("/api/research/plan/{quarter}")
def get_research_plan(quarter: str):
    return db.get_research_plan(quarter)


@app.put("/api/research/plan")
def put_research_plan(payload: dict[str, Any]):
    try:
        return db.upsert_research_plan(payload)
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/strategy")
def get_strategy():
    return db.get_strategy()


@app.get("/api/summary/{quarter}", response_class=PlainTextResponse)
def get_summary(quarter: str):
    settings = db.get_settings()
    dashboard_data = db.dashboard_for_quarter(quarter)
    operations = db.get_operations(quarter)
    gates = decision_gates(settings, db.get_finance(quarter), operations)
    return build_summary(settings["company_name"], quarter, dashboard_data, gates, operations)


@app.get("/api/export/json")
def export_json():
    content = json.dumps(db.export_all_data(), ensure_ascii=False, indent=2)
    return Response(
        content=content,
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=intopia_dss_export.json"},
    )


@app.get("/api/export/operations.csv")
def export_operations_csv(quarter: str | None = None):
    rows = db.get_operations(quarter) if quarter else [r for q in QUARTERS for r in db.get_operations(q)]
    if not rows:
        return PlainTextResponse("")
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return Response(
        content="\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=intopia_operations_{quarter or 'all'}.csv"},
    )


@app.get("/api/health")
def health():
    return {"status": "ok", "db": str(db.DB_PATH)}

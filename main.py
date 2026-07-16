from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import mimetypes
import re
import secrets
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

import db
from agent_service import agent_status, run_agent
from analytics import build_scorecard, financial_position, q9_forecast, recommendations, simulate_portfolio
from backup_service import APP_VERSION, BackupError, create_backup, restore_backup
from config import get_config
from import_service import extract_document
from logic import build_summary, decision_gates, loan_plan, scenario_calculation, unit_economics_calculation
from seed_data import (
    AREAS,
    CHANNELS,
    CONFIDENCE_LEVELS,
    MODELS,
    PRICING_DEFAULTS,
    PRODUCTS,
    QUARTERS,
    STATUS_LEVELS,
    XY_CONVERSION,
)


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"


def _basic_credentials(header: str) -> tuple[str, str] | None:
    if not header.lower().startswith("basic "):
        return None
    try:
        decoded = base64.b64decode(header.split(" ", 1)[1], validate=True).decode("utf-8")
        return tuple(decoded.split(":", 1))  # type: ignore[return-value]
    except (ValueError, UnicodeDecodeError):
        return None


class AccessProtectionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/api/health":
            return await call_next(request)
        config = get_config()
        if not config.require_auth:
            return await call_next(request)
        if not config.access_password:
            return JSONResponse({"detail": "APP_ACCESS_PASSWORD is not configured."}, status_code=503)
        credentials = _basic_credentials(request.headers.get("authorization", ""))
        if not credentials or not (
            secrets.compare_digest(credentials[0], config.access_user)
            and secrets.compare_digest(credentials[1], config.access_password)
        ):
            return Response(status_code=401, headers={"WWW-Authenticate": 'Basic realm="INTOPIA DSS", charset="UTF-8"'})
        return await call_next(request)


class BackendReadinessMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        allowed = {"/api/health", "/api/configuration"}
        if request.url.path.startswith("/api/") and request.url.path not in allowed:
            error = getattr(request.app.state, "startup_error", "")
            if error:
                return JSONResponse({"detail": error}, status_code=503)
        return await call_next(request)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.startup_error = ""
    try:
        errors = get_config().validation_errors()
        if errors:
            raise RuntimeError(" ".join(errors))
        db.init_db()
    except Exception as exc:
        app.state.startup_error = str(exc)
    yield


app = FastAPI(title="EMBA TAU Simulation", version=APP_VERSION, lifespan=lifespan)
app.add_middleware(BackendReadinessMiddleware)
app.add_middleware(AccessProtectionMiddleware)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def safe_filename(name: str) -> str:
    base = Path(name or "file").name
    base = re.sub(r"[^\w.\-\u0590-\u05FF]+", "_", base, flags=re.UNICODE)
    return base[:160] or "file"


def _quarter(value: str) -> str:
    if value not in QUARTERS:
        raise HTTPException(400, "רבעון לא תקין")
    return value


def _error(status: int, exc: Exception) -> HTTPException:
    return HTTPException(status, str(exc) or exc.__class__.__name__)


def _intelligence(quarter: str) -> dict[str, Any]:
    _quarter(quarter)
    settings = db.get_settings()
    finance_rows = db.list_finance()
    operations = db.list_operations()
    area_finance = db.list_finance_by_area()
    assessment = db.get_strategic_assessment(quarter)
    strategy_profile = db.get_strategy_profile()
    score = build_scorecard(quarter, finance_rows, operations, area_finance, assessment, settings.get("score_model"))
    financial = financial_position(quarter, finance_rows, area_finance, float(settings.get("cash_buffer_sf") or 0))
    forecast = q9_forecast(quarter, finance_rows, operations, score)
    research = [row for row in db.list_research_results() if 0 < int(str(row.get("quarter", "Q0"))[1:] or 0) <= int(quarter[1:])]
    recs = recommendations(quarter, financial, score, operations, research, strategy_profile)
    return {"quarter": quarter, "financial": financial, "scorecard": score, "forecast_q9": forecast, "recommendations": recs, "research_results": research, "strategy_profile": strategy_profile}


def _latest_operations_as_of(quarter: str) -> list[dict[str, Any]]:
    """Use the most recent actual operating quarter while planning the next one."""
    end = int(quarter[1:])
    rows = [
        row
        for row in db.list_operations()
        if str(row.get("quarter", "")) in QUARTERS and int(str(row["quarter"])[1:]) <= end
    ]
    latest = max((int(str(row["quarter"])[1:]) for row in rows), default=0)
    return [row for row in rows if int(str(row["quarter"])[1:]) == latest]


@app.get("/", response_class=HTMLResponse)
def index():
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")


@app.get("/api/configuration")
def configuration():
    return {"version": APP_VERSION, **get_config().public_status()}


@app.get("/api/meta")
def meta():
    config = get_config()
    return {
        "version": APP_VERSION,
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
            "אסטרטגיה ראשונית",
            "יעדי Q9",
            "Datalog / כללי משחק",
            "פלט רבעוני",
            "מחקר שוק",
            "Gazette",
            "הסכם / עסקה",
            "צילום / מסמך",
            "אחר",
        ],
        "storage_bucket": config.supabase_bucket,
        "max_upload_mb": config.max_upload_bytes // (1024 * 1024),
        "decision_agent": agent_status(config),
    }


@app.get("/api/settings")
def get_settings():
    return db.get_settings()


@app.put("/api/settings")
def put_settings(payload: dict[str, Any]):
    try:
        return db.update_settings(payload)
    except Exception as exc:
        raise _error(400, exc) from exc


@app.get("/api/dashboard/{quarter}")
def dashboard(quarter: str):
    _quarter(quarter)
    operations = db.get_operations(quarter)
    finance = db.get_finance(quarter)
    return {
        "dashboard": db.dashboard_for_quarter(quarter),
        "gates": decision_gates(db.get_settings(), finance, operations),
        "history": db.dashboard_history(),
        "onboarding": db.onboarding_status(quarter),
    }


@app.get("/api/finance/{quarter}")
def get_finance(quarter: str):
    return db.get_finance(_quarter(quarter))


@app.put("/api/finance/{quarter}")
def put_finance(quarter: str, payload: dict[str, Any]):
    try:
        return db.upsert_finance(_quarter(quarter), payload)
    except HTTPException:
        raise
    except Exception as exc:
        raise _error(400, exc) from exc


@app.get("/api/finance/{quarter}/areas")
def get_finance_areas(quarter: str):
    return db.list_finance_by_area(_quarter(quarter))


@app.put("/api/finance/{quarter}/areas/{area}")
def put_finance_area(quarter: str, area: str, payload: dict[str, Any]):
    try:
        return db.upsert_finance_by_area({**payload, "quarter": _quarter(quarter), "area": area})
    except Exception as exc:
        raise _error(400, exc) from exc


@app.get("/api/operations/{quarter}")
def get_operations(quarter: str):
    return db.get_operations(_quarter(quarter))


@app.put("/api/operations")
def put_operation(payload: dict[str, Any]):
    try:
        return db.upsert_operation(payload)
    except Exception as exc:
        raise _error(400, exc) from exc


@app.get("/api/facts")
def get_facts(quarter: str | None = None):
    return db.list_facts(quarter)


@app.post("/api/facts")
def post_fact(payload: dict[str, Any]):
    try:
        return db.add_fact(payload)
    except Exception as exc:
        raise _error(400, exc) from exc


@app.delete("/api/facts/{fact_id}", status_code=204)
def remove_fact(fact_id: str):
    db.delete_fact(fact_id)
    return Response(status_code=204)


@app.get("/api/uploads")
def get_uploads(quarter: str | None = None):
    return db.list_uploads(quarter)


@app.post("/api/uploads")
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    quarter: str = Form("Setup"),
    category: str = Form("דוח"),
    notes: str = Form(""),
):
    config = get_config()
    if quarter not in ["Setup", *QUARTERS]:
        raise HTTPException(400, "תקופה לא תקינה")
    content = await file.read(config.max_upload_bytes + 1)
    if len(content) > config.max_upload_bytes:
        raise HTTPException(413, f"הקובץ גדול מהמגבלה: {config.max_upload_bytes // (1024 * 1024)}MB")
    if not content:
        raise HTTPException(400, "הקובץ ריק")
    original = safe_filename(file.filename or "file")
    mime_type = file.content_type or mimetypes.guess_type(original)[0] or "application/octet-stream"
    date_path = datetime.now(timezone.utc).strftime("%Y/%m/%d")
    storage_path = f"{quarter.lower()}/{date_path}/{uuid.uuid4().hex}_{original}"
    checksum = hashlib.sha256(content).hexdigest()
    upload_result: dict[str, Any] = {}
    record: dict[str, Any] = {}
    try:
        upload_result = db.storage_upload(storage_path, content, mime_type)
        record = db.add_upload(
            {
                "quarter": quarter,
                "category": category,
                "original_name": original,
                "storage_bucket": config.supabase_bucket,
                "storage_path": storage_path,
                "mime_type": mime_type,
                "size_bytes": len(content),
                "sha256": checksum,
                "etag": str(upload_result.get("etag") or ""),
                "notes": notes,
                "uploaded_by": config.access_user,
                "metadata": {
                    "source_filename": file.filename or original,
                    "user_agent": request.headers.get("user-agent", "")[:300],
                    "app_version": APP_VERSION,
                },
            }
        )
        extraction = extract_document(content, original, mime_type, quarter, category)
        import_run = db.add_report_import({"upload_id": record["id"], "quarter": quarter, **extraction})
        return {**record, "import_run": import_run}
    except Exception as exc:
        if record.get("id"):
            try:
                db.delete_upload_record(str(record["id"]))
            except Exception:
                pass
        try:
            db.storage_delete(storage_path)
        except Exception:
            pass
        raise _error(502, exc) from exc


@app.get("/api/uploads/{upload_id}/download")
def download_upload(upload_id: str):
    record = db.get_upload(upload_id)
    if not record:
        raise HTTPException(404, "קובץ לא נמצא")
    try:
        content = db.storage_download(str(record["storage_path"]))
    except Exception as exc:
        raise _error(404, exc) from exc
    filename = str(record.get("original_name") or "file")
    return Response(
        content=content,
        media_type=str(record.get("mime_type") or "application/octet-stream"),
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@app.get("/api/imports")
def get_imports(quarter: str | None = None):
    return db.list_report_imports(quarter)


@app.post("/api/imports/{import_id}/commit")
def commit_import(import_id: str):
    run = db.get_report_import(import_id)
    if not run:
        raise HTTPException(404, "תהליך קליטה לא נמצא")
    if run.get("committed_at"):
        return {"status": "already_committed", "import": run, "counts": {}}
    quarter = str(run.get("quarter") or "")
    data = run.get("extracted_data") or {}
    if quarter not in QUARTERS and not data.get("strategy_profile"):
        raise HTTPException(400, "יש לקשר את הקובץ לרבעון Q1–Q9 לפני אישור הקליטה")
    upload = db.get_upload(str(run.get("upload_id") or ""))
    counts = {"finance": 0, "finance_by_area": 0, "operations": 0, "research_results": 0, "strategy_profile": 0}
    try:
        if quarter in QUARTERS and data.get("finance"):
            db.upsert_finance(quarter, data["finance"])
            counts["finance"] = 1
        for row in data.get("finance_by_area", []) if quarter in QUARTERS else []:
            db.upsert_finance_by_area({**row, "quarter": quarter, "source": upload.get("original_name", ""), "confidence": run.get("confidence", "בינונית")})
            counts["finance_by_area"] += 1
        for row in data.get("operations", []) if quarter in QUARTERS else []:
            db.upsert_operation({**row, "quarter": quarter, "source": upload.get("original_name", ""), "confidence": run.get("confidence", "בינונית")})
            counts["operations"] += 1
        for row in data.get("research_results", []) if quarter in QUARTERS else []:
            db.add_research_result({**row, "quarter": quarter, "source_upload_id": run.get("upload_id")})
            counts["research_results"] += 1
        if data.get("strategy_profile"):
            db.upsert_strategy_profile({**data["strategy_profile"], "source_upload_id": run.get("upload_id")})
            counts["strategy_profile"] = 1
        committed = db.mark_report_import_committed(import_id, get_config().access_user)
        return {"status": "ok", "import": committed, "counts": counts}
    except Exception as exc:
        raise _error(400, exc) from exc


@app.delete("/api/uploads/{upload_id}", status_code=204)
def delete_upload(upload_id: str):
    record = db.get_upload(upload_id)
    if not record:
        raise HTTPException(404, "קובץ לא נמצא")
    try:
        db.storage_delete(str(record["storage_path"]))
        db.delete_upload_record(upload_id)
    except Exception as exc:
        raise _error(502, exc) from exc
    return Response(status_code=204)


@app.get("/api/decisions")
def get_decisions(quarter: str | None = None):
    return db.list_decisions(quarter)


@app.post("/api/decisions")
def post_decision(payload: dict[str, Any]):
    try:
        return db.add_decision(payload)
    except Exception as exc:
        raise _error(400, exc) from exc


@app.put("/api/decisions/{decision_id}")
def put_decision(decision_id: str, payload: dict[str, Any]):
    try:
        return db.update_decision(decision_id, payload)
    except KeyError as exc:
        raise _error(404, exc) from exc
    except Exception as exc:
        raise _error(400, exc) from exc


@app.get("/api/gates/{quarter}")
def get_gates(quarter: str):
    return decision_gates(db.get_settings(), db.get_finance(_quarter(quarter)), db.get_operations(quarter))


@app.get("/api/scenarios/{quarter}")
def get_scenarios(quarter: str):
    rows = db.list_scenarios(_quarter(quarter))
    return [{**row, "result": scenario_calculation(row)} for row in rows]


@app.post("/api/scenarios")
def post_scenario(payload: dict[str, Any]):
    try:
        row = db.add_scenario(payload)
        return {**row, "result": scenario_calculation(row)}
    except Exception as exc:
        raise _error(400, exc) from exc


@app.post("/api/scenarios/calculate")
def calculate_scenario(payload: dict[str, Any]):
    return scenario_calculation(payload)


@app.delete("/api/scenarios/{scenario_id}", status_code=204)
def remove_scenario(scenario_id: str):
    db.delete_scenario(scenario_id)
    return Response(status_code=204)


@app.post("/api/economics/calculate")
def calculate_unit_economics(payload: dict[str, Any]):
    try:
        return unit_economics_calculation(payload)
    except Exception as exc:
        raise _error(400, exc) from exc


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
        raise _error(400, exc) from exc


@app.get("/api/research/catalog")
def get_research_catalog():
    return db.get_market_research_catalog()


@app.get("/api/research/plan/{quarter}")
def get_research_plan(quarter: str):
    return db.get_research_plan(_quarter(quarter))


@app.put("/api/research/plan")
def put_research_plan(payload: dict[str, Any]):
    try:
        return db.upsert_research_plan(payload)
    except Exception as exc:
        raise _error(400, exc) from exc


@app.get("/api/research/results")
def get_research_results(quarter: str | None = None):
    return db.list_research_results(quarter)


@app.post("/api/research/results")
def post_research_result(payload: dict[str, Any]):
    try:
        return db.add_research_result(payload)
    except Exception as exc:
        raise _error(400, exc) from exc


@app.get("/api/research/relevant/{quarter}")
def relevant_research(quarter: str, domain: str = ""):
    bundle = _intelligence(_quarter(quarter))
    needle = domain.strip().lower()
    decisions = " ".join(f"{item.get('domain', '')} {item.get('title', '')}" for item in bundle["recommendations"]).lower()
    results = []
    for row in db.list_research_results():
        if int(str(row.get("quarter", "Q0"))[1:] or 0) > int(quarter[1:]):
            continue
        haystack = f"{row.get('title', '')} {row.get('key_result', '')} {' '.join(row.get('relevance_domains') or [])}".lower()
        relevant = not needle or needle in haystack or any(token in haystack for token in decisions.split() if len(token) > 3)
        results.append({**row, "relevant": relevant})
    return {"quarter": quarter, "domain": domain, "results": sorted(results, key=lambda row: (not row["relevant"], str(row.get("title", "")))), "catalog": db.get_market_research_catalog()}


@app.get("/api/assessment/{quarter}")
def get_assessment(quarter: str):
    return db.get_strategic_assessment(_quarter(quarter))


@app.put("/api/assessment/{quarter}")
def put_assessment(quarter: str, payload: dict[str, Any]):
    try:
        return db.upsert_strategic_assessment(_quarter(quarter), payload)
    except Exception as exc:
        raise _error(400, exc) from exc


@app.get("/api/intelligence/{quarter}")
def intelligence(quarter: str):
    return _intelligence(_quarter(quarter))


@app.get("/api/reports/quarter/{quarter}")
def quarter_report(quarter: str):
    quarter = _quarter(quarter)
    bundle = _intelligence(quarter)
    return {
        **bundle,
        "finance": db.get_finance(quarter),
        "finance_by_area": db.list_finance_by_area(quarter),
        "operations": db.get_operations(quarter),
        "imports": db.list_report_imports(quarter),
        "decisions": db.list_decisions(quarter),
        "report_type": "quarter",
    }


@app.get("/api/reports/cumulative/{quarter}")
def cumulative_report(quarter: str):
    quarter = _quarter(quarter)
    end = int(quarter[1:])
    bundle = _intelligence(quarter)
    return {
        **bundle,
        "history": [db.dashboard_for_quarter(f"Q{i}") for i in range(1, end + 1)],
        "finance_history": [row for row in db.list_finance() if int(str(row.get("quarter", "Q0"))[1:] or 0) <= end],
        "area_finance_history": [row for row in db.list_finance_by_area() if int(str(row.get("quarter", "Q0"))[1:] or 0) <= end],
        "decisions": [row for row in db.list_decisions() if int(str(row.get("quarter", "Q0"))[1:] or 0) <= end],
        "report_type": "cumulative",
    }


@app.post("/api/simulation/{quarter}")
def simulate_actions(quarter: str, payload: dict[str, Any]):
    quarter = _quarter(quarter)
    bundle = _intelligence(quarter)
    return simulate_portfolio(quarter, payload, bundle["financial"], bundle["forecast_q9"], _latest_operations_as_of(quarter))


@app.get("/api/scenario-portfolios")
def get_scenario_portfolios(quarter: str | None = None):
    return db.list_scenario_portfolios(quarter)


@app.post("/api/scenario-portfolios")
def post_scenario_portfolio(payload: dict[str, Any]):
    try:
        quarter = _quarter(str(payload.get("quarter") or ""))
        bundle = _intelligence(quarter)
        result = simulate_portfolio(quarter, payload, bundle["financial"], bundle["forecast_q9"], _latest_operations_as_of(quarter))
        return db.add_scenario_portfolio({**payload, "quarter": quarter, "result": result})
    except Exception as exc:
        raise _error(400, exc) from exc


@app.delete("/api/scenario-portfolios/{portfolio_id}", status_code=204)
def remove_scenario_portfolio(portfolio_id: str):
    db.delete_scenario_portfolio(portfolio_id)
    return Response(status_code=204)


@app.post("/api/snapshots/{quarter}")
def create_snapshot(quarter: str, payload: dict[str, Any]):
    quarter = _quarter(quarter)
    snapshot = {"intelligence": _intelligence(quarter), "finance": db.get_finance(quarter), "finance_by_area": db.list_finance_by_area(quarter), "operations": db.get_operations(quarter), "decisions": db.list_decisions(quarter)}
    return db.upsert_quarter_snapshot(quarter, snapshot, bool(payload.get("locked", False)))


@app.get("/api/agent/status")
def get_agent_status():
    return agent_status(get_config())


@app.get("/api/agent/threads")
def get_agent_threads():
    return db.list_agent_threads()


@app.post("/api/agent/threads")
def post_agent_thread(payload: dict[str, Any]):
    return db.add_agent_thread(str(payload.get("title") or "שיחה חדשה"), _quarter(str(payload.get("quarter") or "Q4")))


@app.get("/api/agent/threads/{thread_id}/messages")
def get_agent_messages(thread_id: str):
    return db.list_agent_messages(thread_id)


@app.post("/api/agent/chat")
def agent_chat(payload: dict[str, Any]):
    question = str(payload.get("question") or "").strip()
    if not question:
        raise HTTPException(400, "question is required")
    quarter = _quarter(str(payload.get("quarter") or "Q4"))
    thread_id = str(payload.get("thread_id") or "")
    if not thread_id:
        thread_id = str(db.add_agent_thread(question[:70], quarter)["id"])
    history = db.list_agent_messages(thread_id)
    db.add_agent_message(thread_id, "user", question)

    def tool_handler(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        selected = str(arguments.get("quarter") or quarter)
        bundle = _intelligence(_quarter(selected))
        if name == "get_scorecard":
            return bundle["scorecard"]
        if name == "get_financial_position":
            return bundle["financial"]
        if name == "get_q9_forecast":
            return bundle["forecast_q9"]
        if name == "get_recommendations":
            return {"recommendations": bundle["recommendations"], "sources": [f"{selected} recommendations"]}
        if name == "get_relevant_research":
            return relevant_research(selected, str(arguments.get("domain") or ""))
        if name == "simulate_actions":
            simulation_payload = {"name": arguments.get("name", "Agent simulation"), "actions": arguments.get("actions", [])}
            return simulate_portfolio(selected, simulation_payload, bundle["financial"], bundle["forecast_q9"], _latest_operations_as_of(selected))
        return {"error": "Unknown read-only tool"}

    try:
        result = run_agent(get_config(), question, quarter, history, tool_handler)
    except Exception as exc:
        raise _error(503, exc) from exc
    db.add_agent_message(thread_id, "assistant", result["answer"], result.get("sources", []))
    return {**result, "thread_id": thread_id}


@app.get("/api/strategy")
def get_strategy():
    return db.get_strategy()


@app.get("/api/summary/{quarter}", response_class=PlainTextResponse)
def get_summary(quarter: str):
    _quarter(quarter)
    settings = db.get_settings()
    operations = db.get_operations(quarter)
    gates = decision_gates(settings, db.get_finance(quarter), operations)
    return build_summary(settings.get("company_name", ""), quarter, db.dashboard_for_quarter(quarter), gates, operations)


@app.get("/api/export/json")
def export_json():
    content = json.dumps(db.export_all_data(), ensure_ascii=False, indent=2, default=str)
    return Response(
        content=content,
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=intopia_dss_cloud_export.json"},
    )


@app.get("/api/export/operations.csv")
def export_operations_csv(quarter: str | None = None):
    rows = db.get_operations(quarter) if quarter else [row for item in QUARTERS for row in db.get_operations(item)]
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


@app.get("/api/backup")
def backup():
    try:
        content, manifest = create_backup()
    except Exception as exc:
        raise _error(502, exc) from exc
    stamp = str(manifest["created_at"]).replace(":", "-")[:19]
    return Response(
        content=content,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=INTOPIA_DSS_Backup_{stamp}.zip"},
    )


@app.post("/api/restore")
async def restore(
    file: UploadFile = File(...),
    mode: str = Form("replace"),
    confirmation: str = Form(""),
):
    config = get_config()
    if mode == "replace" and confirmation != "RESTORE":
        raise HTTPException(400, "Replace restore requires confirmation=RESTORE")
    content = await file.read(config.max_restore_bytes + 1)
    if len(content) > config.max_restore_bytes:
        raise HTTPException(413, "Backup exceeds MAX_RESTORE_MB")
    try:
        return restore_backup(content, mode=mode, max_uncompressed_bytes=config.max_restore_bytes)
    except BackupError as exc:
        raise _error(400, exc) from exc
    except Exception as exc:
        raise _error(502, exc) from exc


@app.post("/api/admin/reset")
def reset_data(payload: dict[str, Any]):
    if payload.get("confirmation") != "RESET":
        raise HTTPException(400, "Reset requires confirmation=RESET")
    db.reset_company_data(delete_files=True)
    return {"status": "ok", "message": "Company data and uploaded files were removed."}


@app.get("/api/health")
def health(request: Request):
    config = get_config()
    errors = config.validation_errors()
    startup_error = getattr(request.app.state, "startup_error", "")
    if startup_error:
        errors.append(startup_error)
    try:
        cloud_status = db.health() if not errors else {}
    except Exception as exc:
        errors.append(str(exc))
        cloud_status = {}
    payload = {
        "status": "ok" if not errors else "degraded",
        "version": APP_VERSION,
        "backend": config.backend,
        "database": cloud_status.get("database", "unavailable"),
        "storage": cloud_status.get("storage", "unavailable"),
        "storage_bucket": config.supabase_bucket,
        "errors": errors,
    }
    return JSONResponse(payload, status_code=200 if not errors else 503)

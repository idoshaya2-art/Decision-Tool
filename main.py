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
from agent_service import agent_status, analyze_rule_candidates, run_agent
from analytics import (
    analyze_decision_dependencies,
    build_execution_blueprint,
    build_scorecard,
    financial_position,
    q9_forecast,
    recommendations,
    review_decision_catalog,
    simulate_portfolio,
)
from backup_service import APP_VERSION, BackupError, create_backup, restore_backup
from config import get_config
from import_service import extract_document
from insights import build_cumulative_trends, enrich_research_results
from intopia_rules import DECISION_ACTIONS
from logic import build_summary, decision_gates, loan_plan, scenario_calculation, unit_economics_calculation
from rulebook import (
    RULEBOOK_VERSION,
    evaluate_action as evaluate_rulebook_action,
    rulebook_summary,
    search_rules,
    validate_report,
)
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
from strategy_optimizer import build_strategy_optimization


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"


def _chunks_from_extraction(extraction: dict[str, Any]) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    previews = (extraction.get("extracted_data") or {}).get("previews") or []
    for index, preview in enumerate(previews, start=1):
        if not isinstance(preview, dict):
            continue
        section = str(preview.get("sheet") or preview.get("section") or f"section-{index}")
        content = str(preview.get("text") or "").strip()
        if not content and preview.get("rows"):
            content = json.dumps(preview.get("rows"), ensure_ascii=False, default=str)
        if len(content) < 10:
            continue
        chunks.append(
            {
                "page": preview.get("page"),
                "section": section,
                "content": content[:12000],
                "metadata": {
                    "parser_type": extraction.get("parser_type"),
                    "confidence": extraction.get("confidence"),
                    "preview_index": index,
                },
            }
        )
    return chunks


def _analyze_uploaded_rule_source(upload: dict[str, Any], *, force: bool = False) -> dict[str, Any]:
    upload_id = str(upload.get("id") or "")
    source_id = f"upload:{upload_id}"
    chunks = db.list_document_chunks(upload_id=upload_id, limit=100)
    if not chunks:
        return {"status": "no_readable_text", "candidates": [], "conflicts": []}
    existing = [
        row
        for row in db.list_rule_conflicts()
        if str(row.get("candidate_source_id") or "") == source_id
    ]
    if existing and not force:
        return {"status": "already_analyzed", "candidates": [], "conflicts": existing}
    combined = "\n\n".join(
        f"[{row.get('section') or 'section'}"
        f"{f' p.{row.get('page')}' if row.get('page') else ''}]\n{row.get('content') or ''}"
        for row in chunks
    )
    analysis = analyze_rule_candidates(
        get_config(),
        filename=str(upload.get("original_name") or "uploaded source"),
        source_id=source_id,
        content=combined,
        existing_rules=db.list_rules(),
    )
    created: list[dict[str, Any]] = []
    for candidate in analysis.get("candidates", []):
        matched = str(candidate.get("matched_rule_id") or "").strip()
        created.append(
            db.add_rule_conflict(
                {
                    "rule_id": matched or f"CANDIDATE-{uuid.uuid4().hex[:10].upper()}",
                    "existing_version": RULEBOOK_VERSION if matched else "",
                    "candidate_source_id": source_id,
                    "candidate_value": candidate,
                    "description": str(candidate.get("reason") or candidate.get("name") or "Rule candidate requires review."),
                    "status": "open",
                }
            )
        )
    db.add_ai_run(
        {
            "run_type": "rule_candidate_analysis",
            "quarter": str(upload.get("quarter") or "Setup"),
            "model": str(analysis.get("model") or get_config().openai_model),
            "status": str(analysis.get("status") or "completed"),
            "input_summary": str(upload.get("original_name") or "")[:500],
            "output_summary": f"{len(created)} rule candidates created for human review.",
            "sources": [source_id],
        }
    )
    return {**analysis, "conflicts": created}


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


def _detected_company_number() -> int | None:
    for run in db.list_report_imports():
        metadata = (run.get("extracted_data") or {}).get("metadata") or {}
        try:
            value = int(metadata.get("company_number"))
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return None


def _research_source_names() -> dict[str, str]:
    return {
        str(row.get("id")): str(row.get("original_name") or "")
        for row in db.list_uploads()
        if row.get("id")
    }


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
    research_raw = [row for row in db.list_research_results() if 0 < int(str(row.get("quarter", "Q0"))[1:] or 0) <= int(quarter[1:])]
    research = enrich_research_results(research_raw, _detected_company_number(), _research_source_names())
    recs = recommendations(quarter, financial, score, operations, research_raw, strategy_profile)
    latest_operations = _latest_operations_as_of(quarter)
    baseline = financial.get("consolidated", {})
    baseline_score = forecast.get("score", {}).get("base")
    for recommendation in recs:
        action = {**recommendation.get("action_template", {}), "title": recommendation.get("title", "")}
        simulation = simulate_portfolio(
            quarter,
            {
                "name": f"בדיקת המלצה: {recommendation.get('title', '')}",
                "budget_sf": baseline.get("available_budget_sf"),
                "cash_buffer_sf": baseline.get("cash_buffer_sf"),
                "actions": [action],
            },
            financial,
            forecast,
            latest_operations,
        )
        base_case = simulation.get("scenarios", {}).get("base", {})
        sequence = (simulation.get("recommended_sequence") or [{}])[0]
        score_delta = None
        if base_case.get("q9_score") is not None and baseline_score is not None:
            score_delta = round(float(base_case["q9_score"]) - float(baseline_score), 2)
        profit_delta = round(float(base_case.get("net_profit_sf") or 0) - float(baseline.get("net_profit_sf") or 0), 2)
        cash_delta = round(float(base_case.get("ending_cash_sf") or 0) - float(baseline.get("ending_cash_sf") or 0), 2)
        debt_delta = round(float(base_case.get("debt_sf") or 0) - float(baseline.get("debt_sf") or 0), 2)
        impact = {
            "cost_sf": simulation.get("budget", {}).get("planned_cost_sf", 0),
            "budget_remaining_sf": simulation.get("budget", {}).get("remaining_sf", 0),
            "profit_delta_sf": profit_delta,
            "cash_delta_sf": cash_delta,
            "debt_delta_sf": debt_delta,
            "q9_score_delta": score_delta,
            "past_score_delta": sequence.get("past_score_delta"),
            "future_score_delta": sequence.get("future_score_delta"),
            "feasible": simulation.get("feasible", False),
            "violations": simulation.get("violations", []),
            "warnings": simulation.get("warnings", []),
            "next_quarter": {
                "profit_delta_sf": profit_delta,
                "cash_delta_sf": cash_delta,
                "debt_delta_sf": debt_delta,
            },
            "to_q9": {
                "q9_score_delta": score_delta,
                "past_score_delta": sequence.get("past_score_delta"),
                "future_score_delta": sequence.get("future_score_delta"),
            },
            "rulebook_version": simulation.get("rulebook_version", RULEBOOK_VERSION),
            "applied_rules": simulation.get("applied_rules", []),
        }
        action_is_specific = bool(action.get("area") or action.get("product") or action.get("amount_sf") or action.get("cost_sf"))
        confidence = "בינונית" if len(recommendation.get("evidence", [])) >= 2 and action_is_specific else "נמוכה"
        if not impact["feasible"]:
            verdict = "לא לבצע לפני תיקון"
            explanation = "הפעולה מפרה את מגבלת התקציב, רצפת המזומן או כלל משחק."
            verdict_level = "critical"
        elif action.get("type") in {"strategy_review", "cash_protection"}:
            verdict = "לביצוע מיידי"
            explanation = "זוהי פעולת בקרה מקדימה שמגינה על איכות ההחלטות ועל הנזילות."
            verdict_level = "good"
        elif score_delta is not None and score_delta > 0:
            verdict = "מומלץ לבחינה"
            explanation = "בתרחיש הבסיס הפעולה משפרת את אומדן Q9 ונשארת במסגרת התקציב."
            verdict_level = "good"
        elif profit_delta > 0 and cash_delta >= 0:
            verdict = "מומלץ פיננסית"
            explanation = "ההשפעה הכספית החזויה חיובית, אך תרומת Q9 עדיין אינה ודאית."
            verdict_level = "good"
        elif not action_is_specific:
            verdict = "נדרשים פרטים"
            explanation = "יש להשלים אזור, מוצר, כמות או עלות לפני החלטה."
            verdict_level = "warning"
        else:
            verdict = "לבחון חלופה"
            explanation = "התרחיש הנוכחי אינו מציג יתרון כלכלי מובהק ביחס למצב הקיים."
            verdict_level = "warning"
        recommendation["economic_impact"] = impact
        recommendation["ai_recommendation"] = {
            "verdict": verdict,
            "level": verdict_level,
            "explanation": explanation,
            "confidence": confidence,
            "what_changes_it": "נתוני מחיר, ביקוש, עלות, תזמון או מחקר שוק חדש עשויים לשנות את ההמלצה.",
            "rulebook_version": RULEBOOK_VERSION,
            "rule_citations": simulation.get("applied_rules", []),
        }
        recommendation["agent_prompt"] = (
            f"נתח את ההחלטה '{recommendation.get('title', '')}' עבור {quarter}. "
            "הסבר את ההשפעה על רווח, מזומן, חוב, תקציב וציון Q9; "
            "השווה לחלופה שמרנית והצע סדר פעולות."
        )
    liquidity_actions = []
    for transfer in financial.get("liquidity_allocation", {}).get("transfers", []):
        action = {
            **transfer.get("action_template", {}),
            **{
                key: value
                for key, value in transfer.items()
                if key not in {"action_template"}
            },
            "_recommendation_id": f"{quarter}-liquidity-{transfer.get('priority')}",
            "title": (
                f"העברת נזילות {transfer.get('source_area')} → "
                f"{transfer.get('target_area')}"
            ),
            "expected_outcome": (
                f"יתרת היעד לאחר ההעברה: "
                f"{float(transfer.get('target_cash_after_sf') or 0):,.2f} SF"
            ),
        }
        liquidity_actions.append(action)

    recommendation_actions = liquidity_actions + [
        {
            **recommendation.get("action_template", {}),
            "_recommendation_id": recommendation.get("id"),
            "title": recommendation.get("title", ""),
        }
        for recommendation in recs
    ]
    decision_dependencies = analyze_decision_dependencies(
        quarter,
        recommendation_actions,
        latest_operations,
        available_budget_sf=float(baseline.get("available_budget_sf") or 0),
    )
    execution_blueprint = build_execution_blueprint(
        quarter,
        recommendation_actions,
        decision_dependencies,
        recommendations=recs,
    )
    action_review = review_decision_catalog(
        quarter,
        financial,
        operations,
        research,
        recs,
        execution_blueprint,
    )
    dependency_nodes = {
        str(node.get("id")): node
        for node in decision_dependencies.get("nodes", [])
    }
    for recommendation in recs:
        recommendation_id = str(recommendation.get("id") or "")
        prerequisites = []
        enables = []
        coordinates = []
        for edge in decision_dependencies.get("edges", []):
            if edge.get("to") == recommendation_id:
                source = dependency_nodes.get(str(edge.get("from")), {})
                entry = {
                    "id": edge.get("from"),
                    "title": source.get("title", edge.get("from")),
                    "kind": edge.get("kind"),
                    "hard": edge.get("hard", False),
                    "reason": edge.get("reason", ""),
                    "timing": edge.get("timing", ""),
                }
                if edge.get("kind") == "coordination":
                    coordinates.append(entry)
                else:
                    prerequisites.append(entry)
            elif edge.get("from") == recommendation_id:
                target = dependency_nodes.get(str(edge.get("to")), {})
                entry = {
                    "id": edge.get("to"),
                    "title": target.get("title", edge.get("to")),
                    "kind": edge.get("kind"),
                    "hard": edge.get("hard", False),
                    "reason": edge.get("reason", ""),
                    "timing": edge.get("timing", ""),
                }
                if edge.get("kind") == "coordination":
                    coordinates.append(entry)
                else:
                    enables.append(entry)
        recommendation["dependencies"] = {
            "prerequisites": prerequisites,
            "enables": enables,
            "coordinates_with": coordinates,
            "gaps": [
                gap
                for gap in decision_dependencies.get("gaps", [])
                if gap.get("action_id") == recommendation_id
            ],
            "conflicts": [
                conflict
                for conflict in decision_dependencies.get("conflicts", [])
                if recommendation_id in conflict.get("actions", [])
            ],
            "sequence_step": next(
                (
                    row.get("step")
                    for row in decision_dependencies.get("recommended_sequence", [])
                    if row.get("id") == recommendation_id
                ),
                None,
            ),
        }
        recommendation["agent_prompt"] += (
            " אתר תלויות בהחלטות אחרות, תנאים מקדימים, התנגשויות וסדר ביצוע; "
            "אל תנתח את ההחלטה כאילו היא עומדת לבדה."
        )
    for recommendation in recs:
        recommendation["execution_steps"] = [
            row
            for row in execution_blueprint.get("rows", [])
            if row.get("recommendation_id") == recommendation.get("id")
        ]

    return {
        "quarter": quarter,
        "financial": financial,
        "scorecard": score,
        "forecast_q9": forecast,
        "recommendations": recs,
        "action_review": action_review,
        "decision_dependencies": decision_dependencies,
        "execution_blueprint": execution_blueprint,
        "latest_operations": latest_operations,
        "optimization_objective": {
            "primary": "מקסום ביצועי המשחק בכל נקודת זמן ועד Q9",
            "score_model": "50% ביצועי עבר + 50% פוטנציאל עתידי",
            "constraints": [
                "שמירה על חוקי המשחק",
                "שמירה על רצפת מזומן",
                "מימון מלא של סל הפעולות",
                "סדר ביצוע התואם לזמני ההשפעה",
                "התאמה לאסטרטגיה המעודכנת",
            ],
        },
        "research_results": research,
        "strategy_profile": strategy_profile,
    }


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


def _strategy_optimization(quarter: str) -> dict[str, Any]:
    """Create a fresh rolling strategy draft without mutating approved data."""
    quarter = _quarter(quarter)
    intelligence = _intelligence(quarter)
    financial = intelligence.get("financial", {})
    forecast = intelligence.get("forecast_q9", {})
    baseline = financial.get("consolidated", {})
    operations = _latest_operations_as_of(quarter)
    recommendation_rows = intelligence.get("recommendations", [])

    def action_for(row: dict[str, Any]) -> dict[str, Any]:
        return {
            **(row.get("action_template") or {}),
            "_recommendation_id": row.get("id"),
            "title": row.get("title", ""),
        }

    def value(row: dict[str, Any]) -> float:
        impact = row.get("economic_impact") or {}
        q9_delta = impact.get("q9_score_delta")
        if q9_delta is not None:
            return float(q9_delta)
        past = float(impact.get("past_score_delta") or 0)
        future = float(impact.get("future_score_delta") or 0)
        return 0.5 * past + 0.5 * future

    ranked = sorted(
        recommendation_rows,
        key=lambda row: (
            not bool((row.get("economic_impact") or {}).get("feasible", False)),
            -value(row),
            -float(row.get("priority") or 0),
        ),
    )
    control_types = {"strategy_review", "cash_protection", "price_change", "market_research"}
    recommended_rows = [
        row
        for row in ranked
        if bool((row.get("economic_impact") or {}).get("feasible", False))
        and (value(row) > 0 or str((row.get("action_template") or {}).get("type")) in control_types)
    ][:5]
    if not recommended_rows:
        recommended_rows = [
            row
            for row in ranked
            if str((row.get("action_template") or {}).get("type")) in control_types
        ][:3]

    growth_types = {
        "rd",
        "grade_license",
        "capacity",
        "plant_construction",
        "advertising",
        "price_advertising",
        "sales_offices",
        "partnership",
    }
    defensive_types = {
        "cash_protection",
        "price_change",
        "market_research",
        "money_transfer",
        "invest_borrow",
        "loan",
        "currency_conversion",
    }
    growth_rows = [
        row
        for row in ranked
        if bool((row.get("economic_impact") or {}).get("feasible", False))
        and str((row.get("action_template") or {}).get("type")) in growth_types
    ][:5]
    defensive_rows = [
        row
        for row in ranked
        if bool((row.get("economic_impact") or {}).get("feasible", False))
        and str((row.get("action_template") or {}).get("type")) in defensive_types
    ][:5]

    def run(name: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
        return simulate_portfolio(
            quarter,
            {
                "name": name,
                "budget_sf": baseline.get("available_budget_sf"),
                "cash_buffer_sf": baseline.get("cash_buffer_sf"),
                "actions": [action_for(row) for row in rows],
            },
            financial,
            forecast,
            operations,
        )

    scenarios = {
        "original": run("המשך האסטרטגיה המקורית", []),
        "recommended": run("התאמה אסטרטגית מומלצת", recommended_rows),
        "growth": run("תרחיש צמיחה", growth_rows),
        "defensive": run("תרחיש הגנה", defensive_rows),
    }
    return build_strategy_optimization(quarter, intelligence, scenarios)


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
        "decision_actions": DECISION_ACTIONS,
        "rulebook_version": RULEBOOK_VERSION,
    }


@app.get("/api/rulebook")
def get_rulebook(
    query: str = "",
    domain: str = "",
    area: str = "",
    product: str = "",
    knowledge_type: str = "",
    enforcement: str = "",
):
    rows = search_rules(
        db.list_rules(),
        query=query,
        domain=domain,
        area=area,
        product=product,
        knowledge_type=knowledge_type,
        enforcement=enforcement,
    )
    return {
        "summary": rulebook_summary(db.list_rules()),
        "sources": db.list_rule_sources(),
        "conflicts": db.list_rule_conflicts("open"),
        "rules": rows,
    }


@app.get("/api/rulebook/{rule_id}")
def get_rulebook_rule(rule_id: str):
    row = db.get_rule(rule_id)
    if not row:
        raise HTTPException(404, "Rule not found")
    return row


@app.post("/api/rulebook/check")
def check_rulebook_action(payload: dict[str, Any]):
    quarter = _quarter(str(payload.get("quarter") or "Q4"))
    action = payload.get("action") if isinstance(payload.get("action"), dict) else payload
    checks = evaluate_rulebook_action(
        action,
        quarter=quarter,
        operations=_latest_operations_as_of(quarter),
        strict=bool(payload.get("strict", True)),
    )
    violations = [item for item in checks if item.get("blocking") and item.get("status") == "fail"]
    return {
        "quarter": quarter,
        "rulebook_version": RULEBOOK_VERSION,
        "allowed": not violations,
        "checks": checks,
        "violations": violations,
    }


@app.post("/api/rulebook/conflicts/{conflict_id}/resolve")
def resolve_rulebook_conflict(conflict_id: str, payload: dict[str, Any]):
    status = str(payload.get("status") or "")
    resolution = str(payload.get("resolution") or "").strip()
    try:
        row = db.resolve_rule_conflict(
            conflict_id,
            status,
            resolution,
            reviewed_by=str(payload.get("reviewed_by") or get_config().access_user),
        )
    except ValueError as exc:
        raise _error(400, exc) from exc
    if not row:
        raise HTTPException(404, "Rule conflict not found")
    return {
        "conflict": row,
        "note": (
            "The candidate was reviewed. Approval marks it for the next Rulebook version; "
            "it does not mutate the active version automatically."
        ),
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
    extraction = extract_document(content, original, mime_type, quarter, category)
    detected_quarter = str((extraction.get("extracted_data") or {}).get("metadata", {}).get("detected_quarter") or "")
    effective_quarter = detected_quarter if quarter == "Setup" and detected_quarter in QUARTERS else quarter
    extraction["rule_validation"] = validate_report(
        extraction.get("extracted_data") or {},
        effective_quarter if effective_quarter in QUARTERS else "",
    )
    date_path = datetime.now(timezone.utc).strftime("%Y/%m/%d")
    storage_path = f"{effective_quarter.lower()}/{date_path}/{uuid.uuid4().hex}_{original}"
    checksum = hashlib.sha256(content).hexdigest()
    upload_result: dict[str, Any] = {}
    record: dict[str, Any] = {}
    try:
        upload_result = db.storage_upload(storage_path, content, mime_type)
        record = db.add_upload(
            {
                "quarter": effective_quarter,
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
                    "detected_quarter": detected_quarter,
                    "parser_type": extraction.get("parser_type"),
                },
            }
        )
        import_run = db.add_report_import({"upload_id": record["id"], "quarter": effective_quarter, **extraction})
        chunk_records: list[dict[str, Any]] = []
        for chunk in _chunks_from_extraction(extraction):
            chunk_records.append(
                db.add_document_chunk(
                    {
                        **chunk,
                        "upload_id": record["id"],
                        "source_id": f"upload:{record['id']}",
                    }
                )
            )
        rule_analysis: dict[str, Any] = {"status": "not_applicable", "candidates": [], "conflicts": []}
        if effective_quarter == "Setup" and chunk_records:
            try:
                rule_analysis = _analyze_uploaded_rule_source(record)
            except Exception as analysis_exc:
                db.add_ai_run(
                    {
                        "run_type": "rule_candidate_analysis",
                        "quarter": "Setup",
                        "model": get_config().openai_model,
                        "status": "failed",
                        "input_summary": original[:500],
                        "error": str(analysis_exc)[:1000],
                        "sources": [f"upload:{record['id']}"],
                    }
                )
                rule_analysis = {
                    "status": "analysis_failed",
                    "candidates": [],
                    "conflicts": [],
                    "reason": str(analysis_exc)[:300],
                }
        return {
            **record,
            "import_run": import_run,
            "document_chunks": len(chunk_records),
            "rule_analysis": rule_analysis,
        }
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


@app.post("/api/uploads/{upload_id}/analyze-rules")
def analyze_uploaded_rules(upload_id: str, payload: dict[str, Any] | None = None):
    record = db.get_upload(upload_id)
    if not record:
        raise HTTPException(404, "Uploaded source not found")
    try:
        return _analyze_uploaded_rule_source(record, force=bool((payload or {}).get("force", False)))
    except Exception as exc:
        raise _error(503, exc) from exc


@app.get("/api/document-chunks")
def get_document_chunks(
    upload_id: str | None = None,
    source_id: str | None = None,
    query: str = "",
    limit: int = 30,
):
    return db.list_document_chunks(upload_id=upload_id, source_id=source_id, query=query, limit=limit)


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
    validation = run.get("rule_validation") or validate_report(data, quarter if quarter in QUARTERS else "")
    blocking = [item for item in validation.get("checks", []) if item.get("blocking") and item.get("status") == "fail"]
    if blocking:
        raise HTTPException(
            409,
            {
                "message": "הדוח חסום לאישור עד לתיקון סתירות או נתונים בלתי אפשריים.",
                "rulebook_version": validation.get("rulebook_version", RULEBOOK_VERSION),
                "violations": blocking,
            },
        )
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
        forecast_record = None
        if quarter in QUARTERS:
            planning_number = min(int(quarter[1:]) + 1, 9)
            planning_quarter = f"Q{planning_number}"
            intelligence = _intelligence(planning_quarter)
            forecast_record = db.add_forecast(
                {
                    "quarter": planning_quarter,
                    "forecast_type": "q9_after_actuals",
                    "rulebook_version": RULEBOOK_VERSION,
                    "assumptions": [
                        {"type": "Actual", "source_quarter": quarter, "source_upload_id": run.get("upload_id")},
                        {"type": "Rulebook", "version": RULEBOOK_VERSION},
                    ],
                    "result": intelligence.get("forecast_q9", {}),
                    "confidence": "high" if run.get("confidence") == "גבוהה" else "medium",
                }
            )
        return {"status": "ok", "import": committed, "counts": counts, "forecast": forecast_record}
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
    research_rows = enrich_research_results(db.list_research_results(), _detected_company_number(), _research_source_names())
    for row in research_rows:
        if int(str(row.get("quarter", "Q0"))[1:] or 0) > int(quarter[1:]):
            continue
        haystack = (
            f"{row.get('title', '')} {row.get('key_result', '')} {row.get('decision_area', '')} "
            f"{row.get('recommendation', '')} {' '.join(row.get('relevance_domains') or [])}"
        ).lower()
        relevant = not needle or needle in haystack or any(token in haystack for token in decisions.split() if len(token) > 3)
        results.append({**row, "relevant": relevant})
    return {"quarter": quarter, "domain": domain, "results": sorted(results, key=lambda row: (not row["relevant"], str(row.get("title", "")))), "catalog": db.get_market_research_catalog()}


@app.get("/api/insights/{quarter}")
def cumulative_insights(quarter: str):
    quarter = _quarter(quarter)
    end = int(quarter[1:])
    raw_research = [
        row
        for row in db.list_research_results()
        if 0 < int(str(row.get("quarter", "Q0"))[1:] or 0) <= end
    ]
    enriched_research = enrich_research_results(
        raw_research,
        _detected_company_number(),
        _research_source_names(),
    )
    trends = build_cumulative_trends(
        db.list_finance(),
        db.list_operations(),
        raw_research,
        quarter,
    )
    return {
        "quarter": quarter,
        "company_number": _detected_company_number(),
        "trends": trends,
        "research": enriched_research,
        "research_count": len(enriched_research),
        "decisions": [
            row
            for row in db.list_decisions()
            if 0 < int(str(row.get("quarter", "Q0"))[1:] or 0) <= end
        ],
    }


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


@app.get("/api/strategy-optimization/{quarter}")
def strategy_optimization(quarter: str):
    return _strategy_optimization(_quarter(quarter))


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
    finance_history = [
        row
        for row in db.list_finance()
        if int(str(row.get("quarter", "Q0"))[1:] or 0) <= end
    ]
    actual_quarters = sorted(
        {str(row.get("quarter")) for row in finance_history},
        key=lambda value: int(value[1:]),
    )
    data_as_of = actual_quarters[-1] if actual_quarters else None
    return {
        **bundle,
        "history": [db.dashboard_for_quarter(value) for value in actual_quarters],
        "finance_history": finance_history,
        "area_finance_history": [row for row in db.list_finance_by_area() if int(str(row.get("quarter", "Q0"))[1:] or 0) <= end],
        "decisions": [row for row in db.list_decisions() if int(str(row.get("quarter", "Q0"))[1:] or 0) <= end],
        "report_type": "cumulative",
        "data_as_of": data_as_of,
        "planning_quarter": quarter if data_as_of != quarter else None,
    }


@app.post("/api/simulation/{quarter}")
def simulate_actions(quarter: str, payload: dict[str, Any]):
    quarter = _quarter(quarter)
    bundle = _intelligence(quarter)
    result = simulate_portfolio(quarter, payload, bundle["financial"], bundle["forecast_q9"], _latest_operations_as_of(quarter))
    db.add_optimization_run(
        {
            "quarter": quarter,
            "optimization_type": "scenario_budget_sequence",
            "rulebook_version": RULEBOOK_VERSION,
            "constraints": {
                "available_budget_sf": result.get("budget", {}).get("available_sf"),
                "cash_buffer_sf": result.get("budget", {}).get("cash_buffer_sf"),
            },
            "candidates": payload.get("actions", []),
            "result": result,
        }
    )
    return result


@app.get("/api/scenario-actions")
def scenario_actions():
    """Official decision-form catalog used by the scenario laboratory."""
    return DECISION_ACTIONS


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


@app.get("/api/decision-packs")
def get_decision_packs(quarter: str | None = None):
    return db.list_decision_packs(quarter)


@app.post("/api/decision-packs")
def create_decision_pack(payload: dict[str, Any]):
    try:
        quarter = _quarter(str(payload.get("quarter") or "Q4"))
        actions = [dict(row) for row in payload.get("actions", []) if isinstance(row, dict)]
        bundle = _intelligence(quarter)
        consolidated = bundle.get("financial", {}).get("consolidated", {})
        simulation = simulate_portfolio(
            quarter,
            {
                "name": payload.get("name", f"{quarter} decision pack"),
                "actions": actions,
                "budget_sf": consolidated.get("available_budget_sf", 0),
                "cash_buffer_sf": consolidated.get("cash_buffer_sf", 0),
                "decision_pack": True,
            },
            bundle["financial"],
            bundle["forecast_q9"],
            _latest_operations_as_of(quarter),
        )
        validation = simulation.get("rule_validation", {})
        status = "ready_for_team_review" if simulation.get("feasible") else "blocked"
        pack = db.add_decision_pack(
            {
                "quarter": quarter,
                "name": payload.get("name", f"{quarter} decision pack"),
                "status": status,
                "rulebook_version": RULEBOOK_VERSION,
                "scenario_portfolio_id": payload.get("scenario_portfolio_id"),
                "actions": actions,
                "validation": validation,
                "financial_impact": {
                    "budget": simulation.get("budget", {}),
                    "operating_effects": simulation.get("operating_effects", {}),
                    "scenarios": simulation.get("scenarios", {}),
                    "decision_dependencies": simulation.get("dependency_analysis", {}),
                },
                "q9_impact": {
                    key: value.get("q9_score")
                    for key, value in simulation.get("scenarios", {}).items()
                },
                "recommendation": payload.get("recommendation", ""),
                "created_by": get_config().access_user,
            }
        )
        evidence = []
        for citation in simulation.get("applied_rules", []):
            evidence.append(
                db.add_recommendation_evidence(
                    {
                        "decision_pack_id": pack["id"],
                        "recommendation_key": payload.get("name", f"{quarter} decision pack"),
                        "evidence_type": "rule",
                        "source_id": citation.get("source_id", ""),
                        "source_page": citation.get("page", ""),
                        "rule_id": citation.get("rule_id", ""),
                        "payload": citation,
                    }
                )
            )
        return {**pack, "evidence": evidence}
    except Exception as exc:
        raise _error(400, exc) from exc


@app.get("/api/decision-packs/{pack_id}")
def get_decision_pack(pack_id: str):
    row = db.get_decision_pack(pack_id)
    if not row:
        raise HTTPException(404, "Decision pack not found")
    return {**row, "evidence": db.list_recommendation_evidence(pack_id)}


@app.get("/api/decision-packs/{pack_id}/export")
def export_decision_pack(pack_id: str):
    row = db.get_decision_pack(pack_id)
    if not row:
        raise HTTPException(404, "Decision pack not found")
    row = {**row, "evidence": db.list_recommendation_evidence(pack_id)}
    content = json.dumps(row, ensure_ascii=False, indent=2, default=str)
    return Response(
        content=content,
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={row.get('quarter', 'Q')}_decision_pack.json"},
    )


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
    manager_instructions = str(payload.get("manager_instructions") or "").strip()[:2000]
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
        if name == "get_liquidity_transfer_plan":
            return bundle.get("financial", {}).get("liquidity_allocation", {})
        if name == "get_q9_forecast":
            return bundle["forecast_q9"]
        if name == "get_recommendations":
            return {
                "action_review": bundle.get("action_review", {}),
                "recommendations": bundle["recommendations"],
                "execution_blueprint": bundle.get("execution_blueprint", {}),
                "decision_dependencies": bundle.get("decision_dependencies", {}),
                "sources": [
                    f"{selected} full decision-form review, recommendations and executable decision blueprint"
                ],
            }
        if name == "get_relevant_research":
            return relevant_research(selected, str(arguments.get("domain") or ""))
        if name == "get_cumulative_insights":
            return cumulative_insights(selected)
        if name == "get_decision_catalog":
            return {"actions": DECISION_ACTIONS, "sources": ["Data Log v1 decision rules"]}
        if name == "search_rulebook":
            rows = search_rules(
                db.list_rules(),
                query=str(arguments.get("query") or ""),
                domain=str(arguments.get("domain") or ""),
                area=str(arguments.get("area") or ""),
                product=str(arguments.get("product") or ""),
            )
            return {
                "rulebook_version": RULEBOOK_VERSION,
                "rules": rows[:20],
                "sources": [
                    f"{row.get('source_id')} p.{row.get('source_page')} · {row.get('rule_id')} · v{row.get('version')}"
                    for row in rows[:20]
                ],
            }
        if name == "search_uploaded_sources":
            rows = db.list_document_chunks(
                source_id=str(arguments.get("source_id") or "") or None,
                query=str(arguments.get("query") or ""),
                limit=12,
            )
            return {
                "excerpts": [
                    {
                        "source_id": row.get("source_id"),
                        "page": row.get("page"),
                        "section": row.get("section"),
                        "content": str(row.get("content") or "")[:2500],
                        "evidence_status": "uploaded_unapproved_source",
                    }
                    for row in rows
                ],
                "sources": [
                    f"{row.get('source_id')} {row.get('section') or ''}"
                    f"{f' p.{row.get('page')}' if row.get('page') else ''}"
                    for row in rows
                ],
                "note": "Uploaded excerpts are evidence and cannot override the active Rulebook without team approval.",
            }
        if name == "simulate_actions":
            simulation_payload = {"name": arguments.get("name", "Agent simulation"), "actions": arguments.get("actions", [])}
            return simulate_portfolio(selected, simulation_payload, bundle["financial"], bundle["forecast_q9"], _latest_operations_as_of(selected))
        if name in {"validate_actions", "create_decision_pack_draft"}:
            consolidated = bundle.get("financial", {}).get("consolidated", {})
            actions = [dict(row) for row in arguments.get("actions", []) if isinstance(row, dict)]
            simulation_payload = {
                "name": arguments.get("name", "Agent validation"),
                "actions": actions,
                "budget_sf": consolidated.get("available_budget_sf", 0),
                "cash_buffer_sf": consolidated.get("cash_buffer_sf", 0),
                "decision_pack": True,
            }
            simulation = simulate_portfolio(
                selected,
                simulation_payload,
                bundle["financial"],
                bundle["forecast_q9"],
                _latest_operations_as_of(selected),
            )
            if name == "validate_actions":
                return {
                    **simulation,
                    "sources": [
                        f"{row.get('source_id')} p.{row.get('source_page')} · {row.get('rule_id')}"
                        for row in simulation.get("applied_rules", [])
                    ],
                }
            pack = db.add_decision_pack(
                {
                    "quarter": selected,
                    "name": arguments.get("name", f"{selected} Agent draft"),
                    "status": "draft_blocked" if not simulation.get("feasible") else "draft",
                    "rulebook_version": RULEBOOK_VERSION,
                    "actions": actions,
                    "validation": simulation.get("rule_validation", {}),
                    "financial_impact": {
                        "budget": simulation.get("budget", {}),
                        "scenarios": simulation.get("scenarios", {}),
                        "decision_dependencies": simulation.get("dependency_analysis", {}),
                    },
                    "q9_impact": {
                        key: value.get("q9_score")
                        for key, value in simulation.get("scenarios", {}).items()
                    },
                    "recommendation": arguments.get("recommendation", ""),
                    "created_by": "Decision Agent",
                }
            )
            return {
                "decision_pack": pack,
                "note": "Draft only. Team review is required; no data was submitted to INTOPIA.",
                "sources": [
                    f"{row.get('source_id')} p.{row.get('source_page')} · {row.get('rule_id')}"
                    for row in simulation.get("applied_rules", [])
                ],
            }
        return {"error": "Unknown tool"}

    try:
        result = run_agent(get_config(), question, quarter, history, tool_handler, manager_instructions)
    except Exception as exc:
        db.add_ai_run(
            {
                "run_type": "chat",
                "quarter": quarter,
                "model": get_config().openai_model,
                "status": "failed",
                "input_summary": question[:500],
                "error": str(exc)[:1000],
            }
        )
        raise _error(503, exc) from exc
    db.add_agent_message(thread_id, "assistant", result["answer"], result.get("sources", []))
    db.add_ai_run(
        {
            "run_type": "chat",
            "quarter": quarter,
            "model": result.get("model", get_config().openai_model),
            "input_summary": question[:500],
            "output_summary": result.get("answer", "")[:1000],
            "tool_calls": result.get("tool_calls", []),
            "sources": result.get("sources", []),
        }
    )
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

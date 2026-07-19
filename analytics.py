from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from statistics import mean
from typing import Any, Iterable

from intopia_rules import (
    BASELINE_FX_TO_SF,
    DECISION_ACTIONS,
    FX_COMMISSION,
    MINIMUM_RD_SF,
    PLANT_CAPACITY,
    PLANT_COST_LC,
    compatible_x_units,
    decision_action,
)
from rulebook import evaluate_portfolio as evaluate_rulebook_portfolio


QUARTER_NUMBERS = {f"Q{i}": i for i in range(1, 10)}

DEFAULT_SCORE_MODEL: dict[str, Any] = {
    "name": "EMBA internal balanced model",
    "past_weight": 0.5,
    "future_weight": 0.5,
    "past": {
        "net_profit": 0.25,
        "ros": 0.20,
        "roi": 0.15,
        "roe": 0.15,
        "trend": 0.25,
    },
    "future": {
        "technology": 0.20,
        "market_segments": 0.15,
        "share_capacity": 0.20,
        "trend": 0.15,
        "reputation": 0.10,
        "partnerships": 0.10,
        "ethics": 0.10,
    },
    "targets": {"ros": 0.12, "roi": 0.15, "roe": 0.18, "max_grade": 9},
}


def num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value if value not in (None, "") else default)
    except (TypeError, ValueError):
        return default


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def quarter_number(value: str) -> int:
    return QUARTER_NUMBERS.get(str(value).upper(), 0)


def through_quarter(rows: Iterable[dict[str, Any]], quarter: str) -> list[dict[str, Any]]:
    end = quarter_number(quarter)
    return sorted(
        (dict(row) for row in rows if 0 < quarter_number(str(row.get("quarter", ""))) <= end),
        key=lambda row: quarter_number(str(row.get("quarter", ""))),
    )


def slope(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    x_mean = (len(values) - 1) / 2
    y_mean = mean(values)
    denominator = sum((index - x_mean) ** 2 for index in range(len(values)))
    if denominator == 0:
        return 0.0
    return sum((index - x_mean) * (value - y_mean) for index, value in enumerate(values)) / denominator


def target_score(value: float | None, target: float) -> float | None:
    if value is None or target <= 0:
        return None
    return round(clamp(value / target * 100), 1)


def weighted_available(values: dict[str, float | None], weights: dict[str, float]) -> tuple[float | None, float]:
    available = [(key, value) for key, value in values.items() if value is not None and key in weights]
    available_weight = sum(weights[key] for key, _ in available)
    total_weight = sum(weights.values()) or 1
    if not available or available_weight <= 0:
        return None, 0.0
    score = sum(num(value) * weights[key] for key, value in available) / available_weight
    return round(score, 1), round(available_weight / total_weight, 3)


def _ratio(value: float, denominator: float) -> float | None:
    return value / denominator if denominator else None


def _embedded_balance(row: dict[str, Any]) -> dict[str, float]:
    match = re.search(r"\[\[BALANCE:(\{.*?\})\]\]", str(row.get("notes") or ""))
    if not match:
        return {}
    try:
        payload = json.loads(match.group(1))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return {str(key): num(value) for key, value in payload.items()}


def _financial_health(
    values: dict[str, Any],
    *,
    cash_buffer_sf: float = 0.0,
    consolidated: bool = False,
) -> dict[str, Any]:
    revenue = num(values.get("revenue_sf"))
    gross_profit = num(values.get("gross_profit_sf"))
    net_profit = num(values.get("net_profit_sf"))
    cash = num(values.get("ending_cash_sf"))
    debt = num(values.get("debt_sf"))
    current_assets = num(values.get("current_assets_sf"))
    current_liabilities = num(values.get("current_liabilities_sf"))
    equity = num(values.get("equity_sf"))
    working_capital = num(values.get("working_capital_sf"))
    operating_cash_flow_available = values.get("operating_cash_flow_sf") is not None
    operating_cash_flow = num(values.get("operating_cash_flow_sf"))
    available_budget = num(values.get("available_budget_sf"))
    commitments = num(values.get("capex_commitments_sf"))
    data_available = any(
        abs(value) > 0.000001
        for value in (
            revenue,
            gross_profit,
            net_profit,
            cash,
            debt,
            current_assets,
            current_liabilities,
            equity,
            operating_cash_flow,
            commitments,
        )
    )
    if not data_available:
        return {
            "status": "אין מספיק נתונים",
            "level": "unknown",
            "score": None,
            "headline": "יש לאשר דוח כספי לפני אבחון מצב החברה.",
            "checks": [],
            "alerts": ["לא נמצאו נתוני רווח והפסד, מאזן או תזרים מאושרים."],
            "ratios": {},
        }

    current_ratio = _ratio(current_assets, current_liabilities)
    debt_to_equity = _ratio(debt, equity)
    gross_margin = _ratio(gross_profit, revenue)
    net_margin = _ratio(net_profit, revenue)
    cash_buffer_coverage = _ratio(cash, cash_buffer_sf) if cash_buffer_sf > 0 else None
    checks: list[dict[str, Any]] = []

    def add_check(check_id: str, label: str, level: str, value: str, explanation: str) -> None:
        checks.append({"id": check_id, "label": label, "level": level, "value": value, "explanation": explanation})

    liquidity_level = "good"
    liquidity_notes: list[str] = []
    if cash < 0 or working_capital < 0 or (current_ratio is not None and current_ratio < 0.8):
        liquidity_level = "critical"
    elif (
        (consolidated and cash_buffer_sf > 0 and cash < cash_buffer_sf)
        or cash <= 0
        or (current_ratio is not None and current_ratio < 1.1)
    ):
        liquidity_level = "warning"
    if consolidated and cash_buffer_sf > 0:
        liquidity_notes.append(f"מזומן מול רצפה: {cash:,.0f} / {cash_buffer_sf:,.0f} SF")
    if current_ratio is not None:
        liquidity_notes.append(f"יחס שוטף {current_ratio:.2f}")
    if working_capital:
        liquidity_notes.append(f"הון חוזר {working_capital:,.0f} SF")
    add_check("liquidity", "נזילות", liquidity_level, f"{cash:,.0f} SF", " · ".join(liquidity_notes) or "מזומן נוכחי")

    if revenue == 0 and net_profit == 0:
        profitability_level = "unknown"
        profitability_text = "חסרים נתוני הכנסות ורווח."
    elif net_profit < 0:
        profitability_level = "critical"
        profitability_text = f"הפסד נקי {net_profit:,.0f} SF"
    elif net_margin is not None and net_margin < 0.05:
        profitability_level = "warning"
        profitability_text = f"רווחיות נקייה {net_margin * 100:.1f}% — מרווח ביטחון נמוך."
    else:
        profitability_level = "good"
        profitability_text = f"רווחיות נקייה {net_margin * 100:.1f}%" if net_margin is not None else f"רווח נקי {net_profit:,.0f} SF"
    add_check("profitability", "רווח והפסד", profitability_level, f"{net_profit:,.0f} SF", profitability_text)

    if equity == 0 and debt == 0:
        leverage_level = "unknown"
        leverage_text = "חסרים הון עצמי וחוב לצורך בדיקת מינוף."
    elif equity <= 0 and debt > 0:
        leverage_level = "critical"
        leverage_text = "הון עצמי אינו חיובי מול חוב קיים."
    elif debt_to_equity is not None and debt_to_equity > 2:
        leverage_level = "critical"
        leverage_text = f"חוב להון {debt_to_equity:.2f} — מינוף גבוה."
    elif debt_to_equity is not None and debt_to_equity > 1:
        leverage_level = "warning"
        leverage_text = f"חוב להון {debt_to_equity:.2f} — דורש מעקב."
    else:
        leverage_level = "good"
        leverage_text = f"חוב להון {debt_to_equity:.2f}" if debt_to_equity is not None else "אין חוב מהותי שזוהה."
    add_check("leverage", "מאזן ומינוף", leverage_level, f"{debt:,.0f} SF חוב", leverage_text)

    if not operating_cash_flow_available:
        cashflow_level = "unknown"
        cashflow_text = "תזרים מפעילות שוטפת לא זוהה בדוח."
    elif operating_cash_flow < 0:
        cashflow_level = "critical"
        cashflow_text = "הפעילות השוטפת צורכת מזומן."
    else:
        cashflow_level = "good"
        cashflow_text = "הפעילות השוטפת מייצרת מזומן."
    cashflow_value = f"{operating_cash_flow:,.0f} SF" if operating_cash_flow_available else "לא זמין בדוח"
    add_check("cashflow", "תזרים תפעולי", cashflow_level, cashflow_value, cashflow_text)

    if consolidated:
        if available_budget <= 0:
            budget_level = "critical"
            budget_text = "אין תקציב פנוי לאחר התחייבויות ורצפת מזומן."
        elif commitments > available_budget:
            budget_level = "warning"
            budget_text = "התחייבויות ההשקעה גבוהות מהתקציב הפנוי."
        else:
            budget_level = "good"
            budget_text = "קיים תקציב לפעולות, בכפוף לבדיקת תרחיש."
        add_check("budget", "יכולת פעולה", budget_level, f"{available_budget:,.0f} SF", budget_text)

    scored_levels = [item["level"] for item in checks if item["level"] != "unknown"]
    weights = {"good": 100.0, "warning": 55.0, "critical": 15.0}
    health_score = round(mean(weights[level] for level in scored_levels), 0) if scored_levels else None
    critical_count = scored_levels.count("critical")
    warning_count = scored_levels.count("warning")
    if critical_count:
        status, level = "לא תקין", "critical"
        headline = f"זוהו {critical_count} מוקדי סיכון פיננסיים הדורשים פעולה לפני השקעה חדשה."
    elif warning_count:
        status, level = "דורש תשומת לב", "warning"
        headline = f"המצב מאפשר פעילות, אך {warning_count} מדדים דורשים בקרה בתקציב ובתרחישים."
    else:
        status, level = "תקין", "good"
        headline = "המדדים הזמינים אינם מצביעים על בעיה פיננסית מהותית."
    alerts = [f"{item['label']}: {item['explanation']}" for item in checks if item["level"] in {"critical", "warning"}]
    return {
        "status": status,
        "level": level,
        "score": health_score,
        "headline": headline,
        "checks": checks,
        "alerts": alerts,
        "ratios": {
            "gross_margin": gross_margin,
            "net_margin": net_margin,
            "current_ratio": current_ratio,
            "debt_to_equity": debt_to_equity,
            "cash_buffer_coverage": cash_buffer_coverage,
        },
    }


def financial_position(
    quarter: str,
    finance_rows: list[dict[str, Any]],
    area_rows: list[dict[str, Any]],
    cash_buffer_sf: float,
) -> dict[str, Any]:
    history = through_quarter(finance_rows, quarter)
    latest = history[-1] if history else {}
    available_area_rows = through_quarter(area_rows, quarter)
    latest_area_quarter = max(
        (str(row.get("quarter")) for row in available_area_rows),
        key=quarter_number,
        default="",
    )
    current_areas = [row for row in available_area_rows if row.get("quarter") == latest_area_quarter]
    # A planning quarter is not an Actual. Keep the value empty until a
    # consolidated or area-level result has really been stored.
    data_as_of = str(latest.get("quarter") or latest_area_quarter or "")

    def area_sf(row: dict[str, Any], field: str) -> float:
        return num(row.get(field)) * max(num(row.get("fx_to_sf"), 1), 0.000001)

    area_cash = sum(area_sf(row, "ending_cash_lc") for row in current_areas)
    ending_cash = num(latest.get("ending_cash_sf")) or area_cash
    commitments = sum(area_sf(row, "capex_commitments_lc") for row in current_areas)
    debt = num(latest.get("debt_sf")) or sum(area_sf(row, "debt_lc") for row in current_areas)
    inventory = sum(area_sf(row, "inventory_value_lc") for row in current_areas)
    current_assets = sum(area_sf(row, "current_assets_lc") for row in current_areas)
    current_liabilities = sum(area_sf(row, "current_liabilities_lc") for row in current_areas)
    equity = sum(area_sf(row, "equity_lc") for row in current_areas)
    total_investment = sum(area_sf(row, "total_investment_lc") for row in current_areas)
    official_balance = _embedded_balance(latest)
    inventory = official_balance.get("inventory_value_sf", inventory)
    current_assets = official_balance.get("current_assets_sf", current_assets)
    current_liabilities = official_balance.get("current_liabilities_sf", current_liabilities)
    equity = official_balance.get("equity_sf", equity)
    total_investment = official_balance.get("total_assets_sf", total_investment)
    operating_cash_flow_values = [area_sf(row, "operating_cash_flow_lc") for row in current_areas]
    operating_cash_flow_available = any(abs(value) > 0.000001 for value in operating_cash_flow_values)
    operating_cash_flow = sum(operating_cash_flow_values) if operating_cash_flow_available else None
    ar = sum(area_sf(row, "ar_lc") for row in current_areas) or num(latest.get("ar_sf"))
    ap = sum(area_sf(row, "ap_lc") for row in current_areas) or num(latest.get("ap_sf"))
    working_capital = current_assets - current_liabilities if current_assets or current_liabilities else num(latest.get("ar_sf")) - num(latest.get("ap_sf")) + inventory
    available_budget = max(0.0, ending_cash - commitments - max(0.0, cash_buffer_sf))

    by_area = []
    for row in current_areas:
        cash_sf = area_sf(row, "ending_cash_lc")
        area_commitments = area_sf(row, "capex_commitments_lc")
        area_values = {
                **row,
                "revenue_sf": round(area_sf(row, "revenue_lc"), 2),
                "gross_profit_sf": round(area_sf(row, "gross_profit_lc"), 2),
                "net_profit_sf": round(area_sf(row, "net_profit_lc"), 2),
                "ending_cash_sf": round(cash_sf, 2),
                "debt_sf": round(area_sf(row, "debt_lc"), 2),
                "ar_sf": round(area_sf(row, "ar_lc"), 2),
                "ap_sf": round(area_sf(row, "ap_lc"), 2),
                "inventory_value_sf": round(area_sf(row, "inventory_value_lc"), 2),
                "current_assets_sf": round(area_sf(row, "current_assets_lc"), 2),
                "current_liabilities_sf": round(area_sf(row, "current_liabilities_lc"), 2),
                "equity_sf": round(area_sf(row, "equity_lc"), 2),
                "total_investment_sf": round(area_sf(row, "total_investment_lc"), 2),
                "operating_cash_flow_sf": (
                    round(area_sf(row, "operating_cash_flow_lc"), 2)
                    if abs(area_sf(row, "operating_cash_flow_lc")) > 0.000001
                    else None
                ),
                "working_capital_sf": round(area_sf(row, "current_assets_lc") - area_sf(row, "current_liabilities_lc"), 2),
                "capex_commitments_sf": round(area_commitments, 2),
                "available_budget_sf": round(max(0.0, cash_sf - area_commitments), 2),
            }
        area_values["health"] = _financial_health(area_values)
        by_area.append(area_values)

    consolidated_values = {
        "revenue_sf": num(latest.get("revenue_sf")),
        "gross_profit_sf": num(latest.get("gross_profit_sf")),
        "net_profit_sf": num(latest.get("net_profit_sf")),
        "ending_cash_sf": round(ending_cash, 2),
        "debt_sf": round(debt, 2),
        "ar_sf": round(ar, 2),
        "ap_sf": round(ap, 2),
        "inventory_value_sf": round(inventory, 2),
        "current_assets_sf": round(current_assets, 2),
        "current_liabilities_sf": round(current_liabilities, 2),
        "equity_sf": round(equity, 2),
        "total_investment_sf": round(total_investment, 2),
        "operating_cash_flow_sf": round(operating_cash_flow, 2) if operating_cash_flow is not None else None,
        "working_capital_sf": round(working_capital, 2),
        "capex_commitments_sf": round(commitments, 2),
        "cash_buffer_sf": round(max(0.0, cash_buffer_sf), 2),
        "cash_buffer_configured": cash_buffer_sf > 0,
        "available_budget_sf": round(available_budget, 2),
    }
    health = _financial_health(consolidated_values, cash_buffer_sf=max(0.0, cash_buffer_sf), consolidated=True)
    consolidated_values["health"] = health

    requested_number = quarter_number(quarter)
    data_number = quarter_number(data_as_of) if data_as_of else 0
    expected_number = requested_number if data_number >= requested_number else max(1, requested_number - 1)
    expected_as_of = f"Q{expected_number}"
    actual_quarters = {
        str(row.get("quarter"))
        for row in [*history, *available_area_rows]
        if quarter_number(str(row.get("quarter", ""))) > 0
    }
    missing_quarters = [
        f"Q{number}"
        for number in range(1, expected_number + 1)
        if f"Q{number}" not in actual_quarters
    ]
    coverage_complete = bool(data_as_of) and not missing_quarters and data_number >= expected_number
    if not data_as_of:
        coverage_message = "לא אושר עדיין דוח Actual. אין להסתמך על המסך לקבלת החלטות."
        coverage_level = "critical"
    elif coverage_complete:
        coverage_message = f"נתוני Actual מלאים עד {data_as_of}."
        coverage_level = "good"
    else:
        missing_text = ", ".join(missing_quarters) or expected_as_of
        coverage_message = (
            f"המסך מציג נתונים מאושרים עד {data_as_of} בלבד. "
            f"חסרים {missing_text}; אין לראות בהם מצב פתיחה מלא ל-{quarter}."
        )
        coverage_level = "warning"

    return {
        "quarter": quarter,
        "data_as_of": data_as_of,
        "area_data_as_of": latest_area_quarter or None,
        "actual_coverage": {
            "complete": coverage_complete,
            "level": coverage_level,
            "message": coverage_message,
            "data_as_of": data_as_of or None,
            "expected_as_of": expected_as_of,
            "missing_quarters": missing_quarters,
        },
        "consolidated": consolidated_values,
        "health": health,
        "areas": sorted(by_area, key=lambda row: str(row.get("area", ""))),
        "sources": (
            ([f"{data_as_of} consolidated finance"] if data_as_of else [])
            + [f"{latest_area_quarter} finance: {row.get('area')}" for row in by_area]
        ),
    }


def build_scorecard(
    quarter: str,
    finance_rows: list[dict[str, Any]],
    operations: list[dict[str, Any]],
    area_finance: list[dict[str, Any]],
    assessment: dict[str, Any] | None = None,
    score_model: dict[str, Any] | None = None,
) -> dict[str, Any]:
    model = score_model or DEFAULT_SCORE_MODEL
    finance = through_quarter(finance_rows, quarter)
    ops = through_quarter(operations, quarter)
    assessment = assessment or {}
    latest_finance = finance[-1] if finance else {}
    latest_q = str(latest_finance.get("quarter") or quarter)
    latest_ops = [row for row in ops if row.get("quarter") == latest_q]
    latest_area = [row for row in area_finance if row.get("quarter") == latest_q]

    revenue_total = sum(num(row.get("revenue_sf")) for row in finance)
    profit_total = sum(num(row.get("net_profit_sf")) for row in finance)
    ros = _ratio(profit_total, revenue_total)
    investment_sf = sum(num(row.get("total_investment_lc")) * num(row.get("fx_to_sf"), 1) for row in latest_area)
    equity_sf = sum(num(row.get("equity_lc")) * num(row.get("fx_to_sf"), 1) for row in latest_area)
    roi = _ratio(profit_total, investment_sf)
    roe = _ratio(num(latest_finance.get("net_profit_sf")), equity_sf)
    profit_values = [num(row.get("net_profit_sf")) for row in finance]
    profit_trend = slope(profit_values)
    trend_base = mean(abs(value) for value in profit_values) if profit_values else 0
    trend_score = clamp(50 + (profit_trend / trend_base * 100 if trend_base else 0)) if len(profit_values) >= 2 else None
    positive_quarters = sum(1 for value in profit_values if value > 0)
    net_profit_score = round(positive_quarters / len(profit_values) * 100, 1) if profit_values else None

    targets = model.get("targets", DEFAULT_SCORE_MODEL["targets"])
    past_metrics: dict[str, float | None] = {
        "net_profit": net_profit_score,
        "ros": target_score(ros, num(targets.get("ros"), 0.12)),
        "roi": target_score(roi, num(targets.get("roi"), 0.15)),
        "roe": target_score(roe, num(targets.get("roe"), 0.18)),
        "trend": round(trend_score, 1) if trend_score is not None else None,
    }
    past_score, past_coverage = weighted_available(past_metrics, model.get("past", {}))

    max_x = max((int(num(row.get("grade"))) for row in latest_ops if row.get("product") == "X"), default=0)
    max_y = max((int(num(row.get("grade"))) for row in latest_ops if row.get("product") == "Y"), default=0)
    technology = clamp(mean([max_x, max_y]) / max(num(targets.get("max_grade"), 9), 1) * 100) if max_x or max_y else None
    active_pairs = {(str(row.get("area")), str(row.get("product"))) for row in latest_ops if num(row.get("actual_sales")) > 0}
    all_pairs = {(str(row.get("area")), str(row.get("product"))) for row in ops if row.get("area") and row.get("product")}
    market_segments = len(active_pairs) / len(all_pairs) * 100 if all_pairs else None
    shares = [num(row.get("actual_market_share")) for row in latest_ops if num(row.get("actual_market_share")) > 0]
    shares = [value * 100 if value <= 1 else value for value in shares]
    utilizations = [num(row.get("actual_production")) / num(row.get("plant_capacity")) for row in latest_ops if num(row.get("plant_capacity")) > 0]
    readiness = mean(clamp(100 - abs(value - 0.80) * 180) for value in utilizations) if utilizations else None
    share_capacity = None
    if shares and readiness is not None:
        share_capacity = mean([clamp(mean(shares)), readiness])
    elif shares:
        share_capacity = clamp(mean(shares))
    elif readiness is not None:
        share_capacity = readiness
    sales_by_q = [sum(num(row.get("actual_sales")) for row in ops if row.get("quarter") == f"Q{i}") for i in range(1, quarter_number(quarter) + 1)]
    sales_by_q = [value for value in sales_by_q if value or len(sales_by_q) <= 1]
    sales_trend = slope(sales_by_q)
    sales_base = mean(abs(value) for value in sales_by_q) if sales_by_q else 0
    future_trend = clamp(50 + (sales_trend / sales_base * 100 if sales_base else 0)) if len(sales_by_q) >= 2 else None
    partnerships = assessment.get("partnerships_score")
    if partnerships in (None, "") and latest_finance:
        partnerships = latest_finance.get("partnership_score")

    future_metrics: dict[str, float | None] = {
        "technology": round(technology, 1) if technology is not None else None,
        "market_segments": round(market_segments, 1) if market_segments is not None else None,
        "share_capacity": round(share_capacity, 1) if share_capacity is not None else None,
        "trend": round(future_trend, 1) if future_trend is not None else None,
        "reputation": num(assessment.get("reputation_score")) if assessment.get("reputation_score") not in (None, "") else None,
        "partnerships": num(partnerships) if partnerships not in (None, "") else None,
        "ethics": num(assessment.get("ethics_score")) if assessment.get("ethics_score") not in (None, "") else None,
    }
    future_score, future_coverage = weighted_available(future_metrics, model.get("future", {}))
    combined = None
    if past_score is not None and future_score is not None:
        combined = round(past_score * num(model.get("past_weight"), 0.5) + future_score * num(model.get("future_weight"), 0.5), 1)

    coverage = round((past_coverage + future_coverage) / 2, 3)
    width = round(4 + (1 - coverage) * 16 + (2 if len(finance) < 3 else 0), 1)
    confidence = "גבוהה" if coverage >= 0.85 and len(finance) >= 3 else "בינונית" if coverage >= 0.55 else "נמוכה"
    missing = [f"past.{key}" for key, value in past_metrics.items() if value is None] + [f"future.{key}" for key, value in future_metrics.items() if value is None]

    return {
        "quarter": quarter,
        "label": "אומדן ניהולי פנימי — לא הציון הרשמי של המשחק",
        "past": {"score": past_score, "coverage": past_coverage, "metrics": past_metrics, "values": {"net_profit_sf": round(profit_total, 2), "ros": ros, "roi": roi, "roe": roe, "profit_trend_sf": round(profit_trend, 2)}},
        "future": {"score": future_score, "coverage": future_coverage, "metrics": future_metrics, "values": {"max_x_grade": max_x, "max_y_grade": max_y, "active_segments": len(active_pairs), "capacity_utilization": mean(utilizations) if utilizations else None}},
        "combined": combined,
        "range": {"low": round(clamp((combined or 0) - width), 1) if combined is not None else None, "high": round(clamp((combined or 0) + width), 1) if combined is not None else None},
        "confidence": confidence,
        "coverage": coverage,
        "missing": missing,
        "model": model,
        "sources": [f"finance Q1–{quarter}", f"operations Q1–{quarter}", f"strategic assessment {quarter}"],
    }


def q9_forecast(
    quarter: str,
    finance_rows: list[dict[str, Any]],
    operations: list[dict[str, Any]],
    scorecard: dict[str, Any],
) -> dict[str, Any]:
    finance = through_quarter(finance_rows, quarter)
    # The selected quarter can be a planning quarter without actual results yet
    # (for example: Q1-Q3 are actual and the team is currently planning Q4).
    # Forecast distance must therefore start at the latest actual quarter, not at
    # the planning-quarter selector.
    data_as_of = str(finance[-1].get("quarter") or quarter) if finance else quarter
    remaining = max(0, 9 - quarter_number(data_as_of))

    def project(field: str) -> dict[str, float | None]:
        values = [num(row.get(field)) for row in finance]
        if not values:
            return {"low": None, "base": None, "high": None}
        step = slope(values)
        base = values[-1] + step * remaining
        uncertainty = abs(step) * remaining * 0.55 + abs(base) * (0.08 + 0.02 * max(0, 3 - len(values)))
        return {"low": round(base - uncertainty, 2), "base": round(base, 2), "high": round(base + uncertainty, 2)}

    current_score = scorecard.get("combined")
    profit_values = [num(row.get("net_profit_sf")) for row in finance]
    profit_momentum = slope(profit_values)
    denominator = mean(abs(value) for value in profit_values) if profit_values else 0
    score_momentum = clamp(profit_momentum / denominator * 8, -8, 8) if denominator else 0
    score_base = clamp(num(current_score) + score_momentum) if current_score is not None else None
    width = 7 + (1 - num(scorecard.get("coverage"))) * 12
    score_range = {
        "low": round(clamp(num(score_base) - width), 1) if score_base is not None else None,
        "base": round(score_base, 1) if score_base is not None else None,
        "high": round(clamp(num(score_base) + width), 1) if score_base is not None else None,
    }
    return {
        "from_quarter": data_as_of,
        "planning_quarter": quarter,
        "to_quarter": "Q9",
        "remaining_quarters": remaining,
        "revenue_sf": project("revenue_sf"),
        "net_profit_sf": project("net_profit_sf"),
        "ending_cash_sf": project("ending_cash_sf"),
        "score": score_range,
        "confidence": scorecard.get("confidence", "נמוכה"),
        "assumptions": [
            "התחזית ממשיכה את המגמות שנצפו ברבעונים שאושרו.",
            "הטווח מתרחב כאשר חסרים נתונים או קיימות מעט תצפיות.",
            "זהו אומדן ניהולי ולא חיזוי של אלגוריתם הציון הרשמי.",
        ],
    }


def recommendations(
    quarter: str,
    financial: dict[str, Any],
    scorecard: dict[str, Any],
    operations: list[dict[str, Any]],
    research_results: list[dict[str, Any]],
    strategy_profile: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    consolidated = financial.get("consolidated", {})
    budget = num(consolidated.get("available_budget_sf"))
    buffer = num(consolidated.get("cash_buffer_sf"))
    cash = num(consolidated.get("ending_cash_sf"))
    available_ops = through_quarter(operations, quarter)
    latest_ops_quarter = max(
        (str(row.get("quarter")) for row in available_ops),
        key=quarter_number,
        default="",
    )
    latest_ops = [row for row in available_ops if row.get("quarter") == latest_ops_quarter]
    strategy_profile = strategy_profile or {}
    has_strategy = bool(strategy_profile.get("thesis") or strategy_profile.get("goals") or strategy_profile.get("constraints"))

    def add(priority: int, domain: str, title: str, rationale: str, action: dict[str, Any], evidence: list[str], risk: str = "בינוני") -> None:
        result.append({"id": f"{quarter}-{len(result)+1}", "priority": priority, "domain": domain, "title": title, "rationale": rationale, "action_template": action, "evidence": evidence, "risk": risk})

    if not has_strategy:
        result.append({
            "id": f"{quarter}-strategy",
            "priority": 95,
            "domain": "אסטרטגיה",
            "title": "אישור חוזה אסטרטגיה ויעדי Q9",
            "rationale": "נדרש לאשר את התזה, היעדים והקווים האדומים לפני אופטימיזציה של החלטות Q4.",
            "action_template": {"type": "strategy_review", "cost_sf": 0},
            "evidence": ["strategy upload and review"],
            "risk": "גבוה",
        })

    if cash <= buffer or budget <= 0:
        add(100, "מימון", "הגנת מזומן לפני השקעות חדשות", "המזומן הפנוי אינו עובר את רצפת הביטחון לאחר התחייבויות.", {"type": "cash_protection", "cost_sf": 0}, [f"{quarter} cash", "cash buffer"], "גבוה")

    ros = scorecard.get("past", {}).get("values", {}).get("ros")
    if ros is not None and num(ros) < 0.08:
        add(85, "תמחור", "בדיקת מחיר ועלות ליחידה", "שיעור הרווח הנקי נמוך ולכן יש לבדוק מחיר, תמהיל ועלות לפני הגדלת נפח.", {"type": "price_change", "change_pct": 0.03, "elasticity": 1.0, "cost_sf": 0}, [f"ROS Q1–{quarter}", "Unit Economics"], "בינוני")

    for row in latest_ops:
        sales = num(row.get("actual_sales"))
        inventory = num(row.get("ending_inventory"))
        capacity = num(row.get("plant_capacity"))
        production = num(row.get("actual_production"))
        label = f"{row.get('product')} {row.get('model')} · {row.get('area')}"
        if inventory > max(1, sales * 0.45):
            add(75, "תמחור", f"צמצום לחץ מלאי: {label}", "המלאי הסופי גבוה ביחס למכירות בפועל; יש לבדוק מחיר והיקף ייצור יחד.", {"type": "price_change", "area": row.get("area"), "product": row.get("product"), "model": row.get("model"), "change_pct": -0.03, "elasticity": 1.0, "cost_sf": 0}, [f"{quarter} inventory", f"{quarter} sales"], "בינוני")
        if capacity > 0 and production / capacity > 0.90:
            add(70, "ייצור", f"בדיקת קיבולת: {label}", "הניצולת גבוהה ועלולה להגביל מכירות עתידיות; נדרש להשוות הרחבה, שותף או דחייה.", {"type": "capacity", "area": row.get("area"), "product": row.get("product"), "cost_sf": 0, "capacity_units": capacity * 0.2}, [f"{quarter} production", f"{quarter} capacity"], "גבוה")

    if scorecard.get("future", {}).get("metrics", {}).get("technology") is not None and num(scorecard["future"]["metrics"]["technology"]) < 55:
        add(65, "מו״פ", "סגירת פער טכנולוגי תחת התקציב", "הרמה הטכנולוגית מגבילה את רכיב הפוטנציאל; יש לתעדף השקעה שנכנסת לתוקף לפני Q9.", {"type": "rd", "cost_sf": min(budget, max(0.0, budget * 0.2))}, [f"{quarter} X/Y grades", "Q9 potential model"], "בינוני")

    if not research_results:
        add(55, "מחקר", "רכישת מידע לפני החלטה בלתי הפיכה", "לא נמצאו מחקרי שוק מאושרים לרבעון. יש לבחור מחקר לפי החלטת התמחור, הקיבולת או הטכנולוגיה הקרובה.", {"type": "market_research", "cost_sf": 0}, ["research center"], "נמוך")

    alignment = "נבדק מול היעדים והמגבלות שחולצו מהאסטרטגיה המאושרת." if has_strategy else "טרם אושר פרופיל אסטרטגיה מובנה; ההתאמה האסטרטגית חלקית."
    for item in result:
        item["strategy_alignment"] = alignment
        if has_strategy:
            item.setdefault("evidence", []).append("approved strategy profile")
    result.sort(key=lambda item: (-int(item["priority"]), item["title"]))
    return result[:5]


@dataclass
class ActionImpact:
    cost_sf: float = 0.0
    revenue_delta_sf: float = 0.0
    profit_delta_sf: float = 0.0
    past_score_delta: float = 0.0
    future_score_delta: float = 0.0
    confidence_delta: float = 0.0
    cash_delta_sf: float = 0.0
    debt_delta_sf: float = 0.0
    inventory_delta_units: float = 0.0
    capacity_delta_units: float = 0.0
    timing: str = ""
    warnings: list[str] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)

    @property
    def score_delta(self) -> float:
        return 0.5 * self.past_score_delta + 0.5 * self.future_score_delta


def _action_impact(action: dict[str, Any], operations: list[dict[str, Any]]) -> ActionImpact:
    catalog = decision_action(str(action.get("code") or ""))
    action_type = str(action.get("type") or catalog.get("type") or "generic")
    if not action.get("product") and catalog.get("product"):
        action = {**action, "product": catalog["product"]}
    cost = max(0.0, num(action.get("cost_sf")))
    matching = [row for row in operations if (not action.get("area") or row.get("area") == action.get("area")) and (not action.get("product") or row.get("product") == action.get("product")) and (not action.get("model") or row.get("model") == action.get("model"))]
    area = str(action.get("area") or "")
    product = str(action.get("product") or "")
    fx = mean([max(num(row.get("fx_to_sf"), 1), 0.000001) for row in matching]) if matching else BASELINE_FX_TO_SF.get(area, 1.0)
    revenue_base = sum(num(row.get("actual_sales")) * num(row.get("actual_price_lc")) * max(num(row.get("fx_to_sf"), fx), 0.000001) for row in matching)
    timing = str(catalog.get("timing") or "")
    if action_type in {"price_change", "price_advertising", "advertising"}:
        current_prices = [num(row.get("actual_price_lc")) for row in matching if num(row.get("actual_price_lc")) > 0]
        current_price = mean(current_prices) if current_prices else 0
        proposed_price = num(action.get("price_lc"))
        change = num(action.get("change_pct"))
        if proposed_price > 0 and current_price > 0:
            change = proposed_price / current_price - 1
        elasticity = max(0.0, num(action.get("elasticity"), 1.0))
        demand_change = -elasticity * change
        advertising_lc = max(0.0, num(action.get("advertising_lc")))
        if not cost and advertising_lc:
            cost = advertising_lc * fx
        advertising_uplift = clamp(num(action.get("expected_sales_uplift"), min(0.12, advertising_lc / max(revenue_base / max(fx, 0.000001), 1) * 0.6)), 0, 0.5)
        revenue_delta = revenue_base * ((1 + change) * (1 + demand_change + advertising_uplift) - 1)
        past_delta = clamp((revenue_delta * 0.5 - cost) / max(abs(revenue_base), 100_000) * 8, -6, 6)
        future_delta = clamp(max(0.0, demand_change + advertising_uplift) * 8, -3, 5)
        return ActionImpact(cost, revenue_delta, revenue_delta * 0.50 - cost, past_delta, future_delta, 0, timing=timing)
    if action_type == "production":
        units = num(action.get("units"))
        variable_cost = num(action.get("variable_cost_sf")) or (mean([num(row.get("variable_cost_lc")) * max(num(row.get("fx_to_sf"), fx), 0.000001) for row in matching]) if matching else 0)
        price = num(action.get("price_sf")) or num(action.get("price_lc")) * fx or (mean([num(row.get("actual_price_lc")) * max(num(row.get("fx_to_sf"), fx), 0.000001) for row in matching]) if matching else 0)
        sales_ratio = clamp(num(action.get("sell_through"), 0.75), 0, 1)
        cost = cost or max(0.0, units * variable_cost)
        revenue_delta = max(0.0, units * sales_ratio * price)
        capacity = sum(num(row.get("plant_capacity")) for row in matching)
        violations = []
        warnings = ["הייצור נכנס למלאי בסוף הרבעון; הכנסות המכירה מיוחסות לרבעונים הבאים."]
        if capacity and units > capacity:
            violations.append(f"כמות הייצור {units:,.0f} גבוהה מהקיבולת הזמינה {capacity:,.0f}.")
        if product == "Y":
            x_grade = int(num(action.get("x_grade"), -1))
            y_grade = int(num(action.get("grade"), -1))
            if x_grade >= 0 and y_grade >= 0 and compatible_x_units(x_grade, y_grade) == 0:
                violations.append(f"X{x_grade} אינו תואם לייצור Y{y_grade}.")
        return ActionImpact(cost, revenue_delta, revenue_delta - cost, clamp((revenue_delta - cost) / max(cost, 1) * 2, -5, 5), clamp(units / max(capacity, 1) * 2, 0, 3), 0, inventory_delta_units=units * (1 - sales_ratio), timing=timing, warnings=warnings, violations=violations)
    if action_type == "plant_construction":
        plants = max(0.0, num(action.get("plant_count"), 1))
        if not cost and area in PLANT_COST_LC and product in PLANT_COST_LC[area]:
            cost = plants * PLANT_COST_LC[area][product] * fx
        capacity_delta = plants * PLANT_CAPACITY.get(area, {}).get(product, 0)
        existing = max([num(row.get("plants")) for row in matching], default=0)
        violations = ["לא ניתן להחזיק יותר משלושה מפעלים למוצר באזור."] if existing + plants > 3 else []
        return ActionImpact(cost, 0, -cost * 0.06, -clamp(cost / 1_000_000, 0, 3), clamp(capacity_delta / 25_000, 0, 8), 0, capacity_delta_units=capacity_delta, timing=timing, violations=violations)
    if action_type == "sales_offices":
        delta = num(action.get("office_delta"))
        return ActionImpact(cost, revenue_base * 0.04 * max(delta, 0), revenue_base * 0.02 * max(delta, 0) - cost, -clamp(cost / 300_000, 0, 2), clamp(delta * 1.5, -4, 4), 0, timing=timing)
    if action_type == "rd":
        amount = max(cost, num(action.get("amount_sf")))
        cost = amount
        minimum = MINIMUM_RD_SF.get(product, 0)
        warnings = [f"השקעה מתחת לסף המינימלי הידוע של {minimum:,.0f} SF ל-{product}."] if product and 0 < amount < minimum else []
        return ActionImpact(cost, 0, -cost, -clamp(cost / 300_000, 0, 3), clamp(cost / max(minimum or 100_000, 1) * 2.5, 0, 8), 0, timing=timing, warnings=warnings)
    if action_type == "capacity":
        return ActionImpact(cost, 0, -cost, -clamp(cost / 500_000, 0, 2), clamp(num(action.get("capacity_units")) / 100_000, 0, 5), 0, capacity_delta_units=num(action.get("capacity_units")), timing=timing)
    if action_type == "market_research":
        return ActionImpact(cost, 0, -cost, -clamp(cost / 100_000, 0, 1), 0, 0.15, timing=timing)
    if action_type in {"loan", "invest_borrow", "home_office_finance", "intercompany_loan"}:
        amount = max(0.0, num(action.get("amount_sf")))
        rate = max(0.0, num(action.get("interest_rate")))
        interest = max(0.0, num(action.get("interest_sf"))) or amount * (rate / 100 if rate > 1 else rate)
        direction = str(action.get("direction") or "borrow").lower()
        borrowing = direction in {"borrow", "loan", "הלוואה", "גיוס", "receive", "קבלה"}
        if borrowing:
            return ActionImpact(cost, 0, -interest, -clamp(interest / max(amount, 1) * 10, 0, 3), clamp(amount / 1_000_000, 0, 2), 0, cash_delta_sf=amount, debt_delta_sf=amount, timing=timing)
        return ActionImpact(cost or amount, interest, interest, clamp(interest / max(amount, 1) * 4, 0, 2), -clamp(amount / 1_000_000, 0, 2), 0, timing=timing)
    if action_type in {"money_transfer", "currency_conversion", "local_currency_exchange"}:
        amount = max(0.0, num(action.get("amount_sf")))
        commission = amount * FX_COMMISSION.get(area, 0.006)
        cost = cost or commission
        return ActionImpact(cost, 0, -cost, -clamp(cost / max(amount, 1) * 8, 0, 1), clamp(amount / 1_000_000, 0, 1), 0, timing=timing)
    if action_type == "component_transfer":
        units = max(0.0, num(action.get("units")))
        mode = str(action.get("transport_mode") or "surface").lower()
        warnings = ["העברה רגילה מגיעה רק בסוף הרבעון."] if mode not in {"air", "אוויר", "airfreight"} else []
        return ActionImpact(cost, 0, -cost, -clamp(cost / 200_000, 0, 1), clamp(units / 50_000, 0, 3), 0, inventory_delta_units=-units, timing=timing, warnings=warnings)
    if action_type == "grade_license":
        amount = max(cost, num(action.get("amount_sf")))
        grade = max(0.0, num(action.get("grade")))
        return ActionImpact(amount, 0, -amount, -clamp(amount / 400_000, 0, 3), clamp(grade * 0.9, 0, 8), 0, timing=timing)
    if action_type in {"industrial_sale", "factory_sale"}:
        units = max(0.0, num(action.get("units")))
        price = max(0.0, num(action.get("price_lc"))) * fx
        proceeds = max(0.0, num(action.get("amount_sf"))) or units * price
        capacity_loss = 0.0
        if action_type == "factory_sale":
            capacity_loss = -max(0.0, num(action.get("plant_count"), 1)) * PLANT_CAPACITY.get(area, {}).get(product, 0)
            proceeds = proceeds or max(0.0, num(action.get("plant_count"), 1)) * PLANT_COST_LC.get(area, {}).get(product, 0) * fx
        return ActionImpact(cost, proceeds, proceeds - cost, clamp(proceeds / 1_000_000, 0, 5), clamp(capacity_loss / 25_000, -8, 2), 0, cash_delta_sf=proceeds, inventory_delta_units=-units, capacity_delta_units=capacity_loss, timing=timing)
    if action_type == "services_payment":
        amount = max(cost, num(action.get("amount_sf")))
        return ActionImpact(amount, 0, -amount, -clamp(amount / 250_000, 0, 4), 0, 0, timing=timing, warnings=["יש לתעד את השירות והערך העסקי; תשלום כשלעצמו אינו מגדיל ציון."])
    if action_type == "partnership":
        delta = clamp(num(action.get("score_delta"), 2), -5, 8)
        return ActionImpact(cost, num(action.get("revenue_delta_sf")), num(action.get("profit_delta_sf")) - cost, delta * 0.4, delta * 1.6, 0, timing=timing)
    delta = num(action.get("score_delta"))
    return ActionImpact(cost, num(action.get("revenue_delta_sf")), num(action.get("profit_delta_sf")) - cost, delta, delta, 0, timing=timing)


def analyze_decision_dependencies(
    quarter: str,
    actions: list[dict[str, Any]],
    operations: list[dict[str, Any]],
    *,
    impacts: list[ActionImpact] | None = None,
    available_budget_sf: float = 0.0,
) -> dict[str, Any]:
    """Build an explainable dependency graph for a portfolio of decisions."""
    normalized_actions = [dict(action) for action in actions if isinstance(action, dict)]
    impacts = impacts or [_action_impact(action, operations) for action in normalized_actions]
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    seen_edges: set[tuple[str, str, str]] = set()

    def action_type(action: dict[str, Any]) -> str:
        catalog = decision_action(str(action.get("code") or ""))
        return str(action.get("type") or catalog.get("type") or "generic")

    def action_title(action: dict[str, Any], index: int) -> str:
        catalog = decision_action(str(action.get("code") or ""))
        return str(action.get("title") or catalog.get("title") or action_type(action) or f"פעולה {index + 1}")

    def action_id(action: dict[str, Any], index: int) -> str:
        return str(action.get("_recommendation_id") or action.get("id") or f"action-{index + 1}")

    for index, (action, impact) in enumerate(zip(normalized_actions, impacts)):
        catalog = decision_action(str(action.get("code") or ""))
        nodes.append(
            {
                "id": action_id(action, index),
                "index": index,
                "code": str(action.get("code") or catalog.get("code") or ""),
                "type": action_type(action),
                "title": action_title(action, index),
                "area": str(action.get("area") or ""),
                "target_area": str(action.get("target_area") or ""),
                "product": str(action.get("product") or catalog.get("product") or ""),
                "cost_sf": round(impact.cost_sf, 2),
                "score_delta": round(impact.score_delta, 2),
                "timing": impact.timing,
            }
        )

    def same_scope(left: dict[str, Any], right: dict[str, Any]) -> bool:
        area_match = not left["area"] or not right["area"] or left["area"] == right["area"]
        product_match = not left["product"] or not right["product"] or left["product"] == right["product"]
        return area_match and product_match

    def add_edge(
        source: dict[str, Any],
        target: dict[str, Any],
        *,
        kind: str,
        reason: str,
        hard: bool = False,
        timing: str = "",
    ) -> None:
        if source["id"] == target["id"]:
            return
        key = (source["id"], target["id"], kind)
        if key in seen_edges:
            return
        seen_edges.add(key)
        edges.append(
            {
                "from": source["id"],
                "to": target["id"],
                "kind": kind,
                "hard": hard,
                "reason": reason,
                "timing": timing,
            }
        )

    financing_types = {
        "loan",
        "invest_borrow",
        "home_office_finance",
        "intercompany_loan",
        "money_transfer",
        "currency_conversion",
        "local_currency_exchange",
    }
    research_types = {"market_research"}
    technology_types = {"rd", "grade_license"}
    capacity_types = {"plant_construction", "capacity"}
    supply_types = {"production", "component_transfer", "industrial_sale"}
    demand_types = {"price_change", "price_advertising", "advertising", "sales_offices"}
    irreversible_types = {"plant_construction", "grade_license", "factory_sale"}
    expensive_types = {"plant_construction", "capacity", "rd", "grade_license", "sales_offices"}

    research_nodes = [node for node in nodes if node["type"] in research_types]
    financing_nodes = [node for node in nodes if node["type"] in financing_types]
    x_supply_nodes = [node for node in nodes if node["type"] in supply_types and node["product"] == "X"]
    technology_nodes = [node for node in nodes if node["type"] in technology_types]

    total_cost = sum(node["cost_sf"] for node in nodes)
    funding_inflow = sum(
        max(0.0, impact.cash_delta_sf)
        for node, impact in zip(nodes, impacts)
        if node["type"] in financing_types or node["type"] == "factory_sale"
    )

    for node in nodes:
        if node["type"] in irreversible_types | expensive_types:
            matching_research = [candidate for candidate in research_nodes if same_scope(candidate, node)]
            if matching_research:
                for candidate in matching_research:
                    add_edge(
                        candidate,
                        node,
                        kind="prerequisite",
                        hard=node["type"] in irreversible_types,
                        reason="יש לצמצם אי־ודאות באמצעות מחקר רלוונטי לפני התחייבות יקרה או בלתי הפיכה.",
                        timing="מחקר ואישור תוצאה לפני קיבוע ההחלטה.",
                    )
            elif node["type"] in irreversible_types:
                gaps.append(
                    {
                        "action_id": node["id"],
                        "severity": "high",
                        "missing": "מחקר שוק או הוכחת ביקוש/עלות מאושרת",
                        "reason": "החלטה בלתי הפיכה דורשת בסיס מידע לפני ביצוע.",
                    }
                )

        if node["type"] == "production" and node["product"] == "Y":
            matching_x = [
                candidate
                for candidate in x_supply_nodes
                if not node["area"]
                or candidate["area"] in {"", node["area"]}
                or candidate["target_area"] == node["area"]
            ]
            if matching_x:
                for candidate in matching_x:
                    add_edge(
                        candidate,
                        node,
                        kind="prerequisite",
                        hard=True,
                        reason="ייצור Y תלוי בזמינות שבבי X תואמים באזור ובמועד הנדרש.",
                        timing="העברה אווירית יכולה לתמוך באותו רבעון; ייצור או הובלה רגילים זמינים רק בהמשך.",
                    )
            else:
                gaps.append(
                    {
                        "action_id": node["id"],
                        "severity": "high",
                        "missing": "אימות מלאי וזמינות X תואם",
                        "reason": "אין בתיק הפעולות מקור מפורש לשבבי X הדרושים לייצור Y.",
                    }
                )

        if node["type"] == "production":
            for candidate in technology_nodes:
                if candidate["product"] in {"", node["product"]}:
                    add_edge(
                        candidate,
                        node,
                        kind="timing",
                        reason="רמת הייצור חייבת להתאים לטכנולוגיה שבבעלות החברה או לרישיון שנכנס לתוקף.",
                        timing="מו״פ ורישיון עשויים להבשיל רק ברבעון הבא; אין להניח זמינות מיידית.",
                    )
            for candidate in nodes:
                if candidate["type"] in capacity_types and same_scope(candidate, node):
                    add_edge(
                        candidate,
                        node,
                        kind="timing",
                        reason="היקף הייצור תלוי בקיבולת הפעילה.",
                        timing="מפעל חדש אינו מגדיל את קיבולת הייצור של הרבעון שבו הוקם.",
                    )

        if node["type"] in demand_types:
            for candidate in nodes:
                if candidate["type"] in supply_types | capacity_types and same_scope(candidate, node):
                    add_edge(
                        candidate,
                        node,
                        kind="coordination",
                        reason="מחיר, פרסום ומכירה צריכים להיקבע מול המלאי והייצור כדי למנוע מחסור או עודף.",
                        timing="יש לאשר יחד את תחזית הביקוש, הכמות והמחיר.",
                    )
                if candidate["type"] == "sales_offices" and same_scope(candidate, node):
                    add_edge(
                        candidate,
                        node,
                        kind="coordination",
                        reason="אפקט המחיר והפרסום תלוי גם בכיסוי ובעלות ערוץ המכירה.",
                        timing="בחינת הערוץ לפני קיבוע תקציב השיווק.",
                    )

        if node["cost_sf"] > 0 and total_cost > max(0.0, available_budget_sf):
            for candidate in financing_nodes:
                add_edge(
                    candidate,
                    node,
                    kind="funding",
                    hard=True,
                    reason="סל הפעולות חורג מהתקציב הזמין ללא מקור מימון או העברת מזומן.",
                    timing="יש לאשר מקור מימון לפני התחייבות להוצאה.",
                )

    for left_index, left in enumerate(nodes):
        for right in nodes[left_index + 1 :]:
            if not same_scope(left, right):
                continue
            types = {left["type"], right["type"]}
            if "factory_sale" in types and types.intersection({"plant_construction", "capacity", "production"}):
                conflicts.append(
                    {
                        "actions": [left["id"], right["id"]],
                        "severity": "high",
                        "reason": "מכירת קיבולת והרחבה או ייצור באותו מוצר ואזור פועלות בכיוונים מנוגדים.",
                    }
                )

    order_edges = [edge for edge in edges if edge["kind"] in {"prerequisite", "funding", "timing"}]
    incoming: dict[str, set[str]] = {node["id"]: set() for node in nodes}
    outgoing: dict[str, set[str]] = {node["id"]: set() for node in nodes}
    for edge in order_edges:
        incoming[edge["to"]].add(edge["from"])
        outgoing[edge["from"]].add(edge["to"])

    stage_by_type = {
        "market_research": 1,
        "loan": 1,
        "invest_borrow": 1,
        "home_office_finance": 1,
        "intercompany_loan": 1,
        "money_transfer": 1,
        "currency_conversion": 1,
        "local_currency_exchange": 1,
        "rd": 2,
        "grade_license": 2,
        "plant_construction": 2,
        "capacity": 2,
        "component_transfer": 3,
        "production": 4,
        "sales_offices": 4,
        "price_change": 5,
        "price_advertising": 5,
        "advertising": 5,
        "industrial_sale": 5,
    }
    remaining = {node["id"] for node in nodes}
    ordered_ids: list[str] = []
    while remaining:
        ready = [node for node in nodes if node["id"] in remaining and not (incoming[node["id"]] & remaining)]
        if not ready:
            ready = [node for node in nodes if node["id"] in remaining]
        ready.sort(
            key=lambda node: (
                stage_by_type.get(node["type"], 6),
                -(node["score_delta"] / max(abs(node["cost_sf"]), 1)),
                node["index"],
            )
        )
        selected = ready[0]
        ordered_ids.append(selected["id"])
        remaining.remove(selected["id"])

    node_by_id = {node["id"]: node for node in nodes}
    sequence = [
        {
            "step": index + 1,
            **node_by_id[node_id],
            "depends_on": sorted(incoming[node_id]),
            "coordinates_with": sorted(
                {
                    edge["from"] if edge["to"] == node_id else edge["to"]
                    for edge in edges
                    if edge["kind"] == "coordination" and node_id in {edge["from"], edge["to"]}
                }
            ),
        }
        for index, node_id in enumerate(ordered_ids)
    ]
    effective_budget = available_budget_sf + funding_inflow
    return {
        "quarter": quarter,
        "nodes": nodes,
        "edges": edges,
        "conflicts": conflicts,
        "gaps": gaps,
        "recommended_sequence": sequence,
        "critical_path": [node_id for node_id in ordered_ids if incoming[node_id] or outgoing[node_id]],
        "budget_coordination": {
            "available_budget_sf": round(available_budget_sf, 2),
            "funding_inflow_sf": round(funding_inflow, 2),
            "effective_budget_sf": round(effective_budget, 2),
            "planned_cost_sf": round(total_cost, 2),
            "remaining_after_plan_sf": round(effective_budget - total_cost, 2),
            "requires_funding_first": total_cost > available_budget_sf,
        },
        "summary": {
            "dependency_count": len(edges),
            "hard_dependency_count": sum(1 for edge in edges if edge["hard"]),
            "conflict_count": len(conflicts),
            "missing_prerequisite_count": len(gaps),
            "message": (
                "ההמלצות יוצרות מהלך משולב; יש לבצע את התנאים המקדימים לפי הסדר לפני קיבוע פעולות השיווק והייצור."
                if edges
                else "לא זוהו תלויות מחייבות; עדיין יש לבדוק את הפעולות יחד מול התקציב ויעד Q9."
            ),
        },
    }


def simulate_portfolio(
    quarter: str,
    payload: dict[str, Any],
    financial: dict[str, Any],
    score_forecast: dict[str, Any],
    operations: list[dict[str, Any]],
) -> dict[str, Any]:
    actions = [dict(action) for action in payload.get("actions", []) if isinstance(action, dict)]
    baseline = financial.get("consolidated", {})
    available_budget = num(payload.get("budget_sf"), num(baseline.get("available_budget_sf")))
    cash_buffer = num(payload.get("cash_buffer_sf"), num(baseline.get("cash_buffer_sf")))
    impacts = [_action_impact(action, operations) for action in actions]
    total_cost = sum(item.cost_sf for item in impacts)
    base_revenue = num(baseline.get("revenue_sf"))
    base_profit = num(baseline.get("net_profit_sf"))
    base_cash = num(baseline.get("ending_cash_sf"))
    base_score = score_forecast.get("score", {}).get("base")

    def scenario(multiplier: float) -> dict[str, Any]:
        revenue_delta = sum(item.revenue_delta_sf for item in impacts) * multiplier
        profit_delta = sum(item.profit_delta_sf for item in impacts) * multiplier
        past_delta = sum(item.past_score_delta for item in impacts) * multiplier
        future_delta = sum(item.future_score_delta for item in impacts) * multiplier
        score_delta = 0.5 * past_delta + 0.5 * future_delta
        cash = base_cash - total_cost + sum(item.cash_delta_sf for item in impacts) * multiplier + max(0.0, revenue_delta) * 0.35
        debt = num(baseline.get("debt_sf")) + sum(item.debt_delta_sf for item in impacts) * multiplier
        return {
            "revenue_sf": round(base_revenue + revenue_delta, 2),
            "net_profit_sf": round(base_profit + profit_delta, 2),
            "ending_cash_sf": round(cash, 2),
            "debt_sf": round(debt, 2),
            "past_performance_score": round(clamp(num(base_score) + past_delta), 1) if base_score is not None else None,
            "future_potential_score": round(clamp(num(base_score) + future_delta), 1) if base_score is not None else None,
            "q9_score": round(clamp(num(base_score) + score_delta), 1) if base_score is not None else None,
        }

    dependency_analysis = analyze_decision_dependencies(
        quarter,
        actions,
        operations,
        impacts=impacts,
        available_budget_sf=available_budget,
    )
    effective_budget = num(
        dependency_analysis.get("budget_coordination", {}).get("effective_budget_sf"),
        available_budget,
    )
    impact_by_index = {index: impact for index, impact in enumerate(impacts)}
    sequence = []
    for row in dependency_analysis["recommended_sequence"]:
        action_index = int(row["index"])
        impact = impact_by_index[action_index]
        sequence.append(
            {
                "step": row["step"],
                "action": actions[action_index],
                "cost_sf": round(impact.cost_sf, 2),
                "expected_score_delta": round(impact.score_delta, 2),
                "past_score_delta": round(impact.past_score_delta, 2),
                "future_score_delta": round(impact.future_score_delta, 2),
                "value_per_100k_sf": round(
                    impact.score_delta / max(abs(impact.cost_sf), 1) * 100_000,
                    2,
                ),
                "timing": impact.timing,
                "warnings": impact.warnings,
                "depends_on": row["depends_on"],
                "coordinates_with": row["coordinates_with"],
            }
        )

    base_case = scenario(1.0)
    rule_validation = evaluate_rulebook_portfolio(
        actions,
        quarter=quarter,
        operations=operations,
        available_budget_sf=effective_budget,
        base_cash_sf=base_cash,
        cash_buffer_sf=cash_buffer,
        strict=bool(payload.get("decision_pack", False)),
    )
    violations = []
    if total_cost > effective_budget:
        violations.append("עלות הפעולות גבוהה מהתקציב הזמין.")
    if base_case["ending_cash_sf"] < cash_buffer:
        violations.append("התרחיש יורד מתחת לרצפת המזומן.")
    for impact in impacts:
        violations.extend(impact.violations)
    violations.extend(
        str(item.get("message") or item.get("rule_id") or "Rule violation")
        for item in rule_validation.get("violations", [])
    )
    return {
        "quarter": quarter,
        "name": payload.get("name", "תרחיש חדש"),
        "actions": actions,
        "budget": {
            "available_sf": round(available_budget, 2),
            "funding_inflow_sf": round(
                num(dependency_analysis.get("budget_coordination", {}).get("funding_inflow_sf")),
                2,
            ),
            "effective_available_sf": round(effective_budget, 2),
            "planned_cost_sf": round(total_cost, 2),
            "cash_buffer_sf": round(cash_buffer, 2),
            "remaining_sf": round(effective_budget - total_cost, 2),
        },
        "feasible": not violations and bool(rule_validation.get("feasible", True)),
        "violations": violations,
        "rule_validation": rule_validation,
        "rulebook_version": rule_validation.get("rulebook_version"),
        "applied_rules": rule_validation.get("applied_rules", []),
        "scenarios": {"low": scenario(0.65), "base": base_case, "high": scenario(1.25)},
        "recommended_sequence": sequence,
        "dependency_analysis": dependency_analysis,
        "catalog_coverage": {"available_actions": len(DECISION_ACTIONS), "selected_actions": len(actions)},
        "operating_effects": {"inventory_delta_units": round(sum(item.inventory_delta_units for item in impacts), 2), "capacity_delta_units": round(sum(item.capacity_delta_units for item in impacts), 2)},
        "warnings": [warning for item in impacts for warning in item.warnings],
        "confidence_change": round(sum(item.confidence_delta for item in impacts), 2),
        "assumptions": ["השפעות נמוך/בסיס/גבוה נגזרות מהנתונים שאושרו ומהנחות הפעולה, לא מהאלגוריתם הרשמי.", "הציון מפוצל תמיד ל-50% ביצועי עבר ו-50% פוטנציאל עתידי; משקלי המשנה הם מודל ניהולי פנימי.", "סימולציה אינה משנה נתוני אמת עד לאישור."],
    }

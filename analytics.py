from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from statistics import mean
from typing import Any, Iterable

from intopia_rules import (
    AREA_CURRENCIES,
    BASELINE_FX_TO_SF,
    DECISION_ACTIONS,
    FX_COMMISSION,
    MINIMUM_RD_SF,
    PLANT_CAPACITY,
    PLANT_COST_LC,
    compatible_x_units,
    decision_action,
)
from digital_twin import build_digital_twin_state, project_digital_twin
from rulebook import (
    RULEBOOK_VERSION,
    evaluate_action as evaluate_rulebook_action,
    evaluate_portfolio as evaluate_rulebook_portfolio,
)


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


def liquidity_allocation_plan(
    areas: list[dict[str, Any]],
    consolidated: dict[str, Any],
    *,
    configured_cash_buffer_sf: float = 0.0,
    reserve_rate: float = 0.25,
    minimum_active_area_reserve_sf: float = 50_000.0,
) -> dict[str, Any]:
    """Build a deterministic, auditable cross-area liquidity recommendation.

    The plan is a management policy, not an INTOPIA hard rule. It protects each
    active area with a minimum reserve plus 25% of short-term obligations, then
    moves only the surplus above that reserve. Cross-currency recommendations
    gross up the source amount for the Data Log FX commission.
    """
    active_rows: list[dict[str, Any]] = []
    for row in areas:
        cash = num(row.get("ending_cash_sf"))
        liabilities = max(num(row.get("current_liabilities_sf")), num(row.get("ap_sf")))
        commitments = num(row.get("capex_commitments_sf"))
        active = any(
            abs(num(row.get(field))) > 0.000001
            for field in (
                "revenue_sf",
                "net_profit_sf",
                "ending_cash_sf",
                "debt_sf",
                "inventory_value_sf",
                "current_assets_sf",
                "current_liabilities_sf",
                "ap_sf",
                "capex_commitments_sf",
            )
        )
        if not active:
            continue
        reserve = max(
            minimum_active_area_reserve_sf,
            commitments + reserve_rate * liabilities,
        )
        fx_to_sf = max(num(row.get("fx_to_sf"), 1.0), 0.000001)
        area = str(row.get("area") or "")
        currency_aliases = {"US": "USD", "USA": "USD", "EU": "EUR", "Europe": "EUR"}
        active_rows.append(
            {
                "area": area,
                "currency": str(
                    row.get("currency")
                    or AREA_CURRENCIES.get(area)
                    or currency_aliases.get(area, "")
                ),
                "fx_to_sf": fx_to_sf,
                "cash_sf": round(cash, 2),
                "short_term_obligations_sf": round(liabilities, 2),
                "commitments_sf": round(commitments, 2),
                "recommended_reserve_sf": round(reserve, 2),
                "funding_gap_sf": round(max(0.0, reserve - cash), 2),
                "transferable_surplus_sf": round(max(0.0, cash - reserve), 2),
            }
        )

    sources = sorted(
        (dict(row) for row in active_rows if row["transferable_surplus_sf"] > 0),
        key=lambda row: row["transferable_surplus_sf"],
        reverse=True,
    )
    destinations = sorted(
        (dict(row) for row in active_rows if row["funding_gap_sf"] > 0),
        key=lambda row: (row["funding_gap_sf"], row["short_term_obligations_sf"]),
        reverse=True,
    )
    transfers: list[dict[str, Any]] = []
    for destination in destinations:
        remaining_gap = float(destination["funding_gap_sf"])
        for source in sources:
            available = float(source["transferable_surplus_sf"])
            if remaining_gap <= 0.01 or available <= 0.01:
                continue
            cross_currency = source["currency"] != destination["currency"]
            commission_area_aliases = {"US": "USA", "EU": "Europe"}
            commission_area = commission_area_aliases.get(source["area"], source["area"])
            commission_rate = FX_COMMISSION.get(commission_area, 0.0) if cross_currency else 0.0
            net_amount = min(available * max(1.0 - commission_rate, 0.0), remaining_gap)
            gross_source_sf = net_amount / max(1.0 - commission_rate, 0.000001)
            fee_sf = gross_source_sf - net_amount
            source_after = float(source["cash_sf"]) - gross_source_sf
            transfer = {
                "priority": len(transfers) + 1,
                "source_area": source["area"],
                "source_currency": source["currency"],
                "target_area": destination["area"],
                "target_currency": destination["currency"],
                "net_amount_sf": round(net_amount, 2),
                "gross_source_amount_sf": round(gross_source_sf, 2),
                "estimated_fx_fee_sf": round(fee_sf, 2),
                "commission_rate": commission_rate,
                "source_amount_lc": round(gross_source_sf / float(source["fx_to_sf"]), 2),
                "target_amount_lc": round(net_amount / float(destination["fx_to_sf"]), 2),
                "source_cash_after_sf": round(source_after, 2),
                "target_cash_after_sf": round(float(destination["cash_sf"]) + net_amount, 2),
                "covers_gap_pct": round(min(1.0, net_amount / max(remaining_gap, 0.000001)), 4),
                "action_template": {
                    "code": "A3-1",
                    "type": "money_transfer",
                    "area": source["area"],
                    "target_area": destination["area"],
                    "currency": source["currency"],
                    "amount_sf": round(net_amount, 2),
                    "cost_sf": round(fee_sf, 2),
                },
            }
            transfers.append(transfer)
            source["transferable_surplus_sf"] = round(max(0.0, available - gross_source_sf), 2)
            source["cash_sf"] = round(source_after, 2)
            destination["cash_sf"] = round(float(destination["cash_sf"]) + net_amount, 2)
            remaining_gap = round(max(0.0, remaining_gap - net_amount), 2)

    total_cash = num(consolidated.get("ending_cash_sf"))
    top_cash_area = max(active_rows, key=lambda row: row["cash_sf"], default={})
    concentration = (
        num(top_cash_area.get("cash_sf")) / total_cash
        if total_cash > 0 and top_cash_area
        else None
    )
    policy_buffer = (
        configured_cash_buffer_sf
        if configured_cash_buffer_sf > 0
        else max(
            100_000.0,
            reserve_rate * num(consolidated.get("current_liabilities_sf")),
        )
    )
    uncovered_gap = round(
        max(
            0.0,
            sum(row["funding_gap_sf"] for row in active_rows)
            - sum(row["net_amount_sf"] for row in transfers),
        ),
        2,
    )
    return {
        "status": "action_required" if transfers or uncovered_gap > 0 else "balanced",
        "as_of": consolidated.get("data_as_of"),
        "policy": {
            "kind": "management_assumption",
            "reserve_rate": reserve_rate,
            "minimum_active_area_reserve_sf": minimum_active_area_reserve_sf,
            "configured_cash_buffer_sf": round(max(0.0, configured_cash_buffer_sf), 2),
            "recommended_consolidated_cash_buffer_sf": round(policy_buffer, 2),
            "explanation_he": (
                "רזרבה ניהולית: לפחות 50,000 SF לכל אזור פעיל ועוד 25% "
                "מההתחייבויות השוטפות, בתוספת התחייבויות השקעה. זו הנחת עבודה "
                "שקופה ולא חוק משחק."
            ),
        },
        "cash_concentration": {
            "area": top_cash_area.get("area"),
            "currency": top_cash_area.get("currency"),
            "share": round(concentration, 4) if concentration is not None else None,
            "cash_sf": top_cash_area.get("cash_sf"),
        },
        "areas": active_rows,
        "transfers": transfers,
        "uncovered_gap_sf": uncovered_gap,
        "confidence": "medium" if active_rows else "low",
        "missing_inputs": [
            item
            for item, missing in (
                ("רצפת מזומן מאושרת של הצוות", configured_cash_buffer_sf <= 0),
                ("מועדי פירעון מדויקים של ספקים והתחייבויות", any(row["short_term_obligations_sf"] > 0 for row in active_rows)),
            )
            if missing
        ],
        "sources": [
            "Approved area financial Actuals",
            "Data Log v1 · DL-FX-COMMISSION",
            "Management reserve policy (explicit assumption)",
        ],
    }


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
    liquidity_plan = liquidity_allocation_plan(
        by_area,
        {**consolidated_values, "data_as_of": data_as_of},
        configured_cash_buffer_sf=max(0.0, cash_buffer_sf),
    )

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
        "liquidity_allocation": liquidity_plan,
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
    official_balance = _embedded_balance(latest_finance)
    regional_investment_sf = sum(num(row.get("total_investment_lc")) * num(row.get("fx_to_sf"), 1) for row in latest_area)
    regional_equity_sf = sum(num(row.get("equity_lc")) * num(row.get("fx_to_sf"), 1) for row in latest_area)
    # Regional control accounts are not additive consolidated equity/assets.
    # Prefer the official consolidated balance embedded by the exact parser.
    investment_sf = num(official_balance.get("total_assets_sf")) or regional_investment_sf
    equity_sf = num(official_balance.get("equity_sf")) or regional_equity_sf
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
    # Convert generic recommendation types into ready-to-simulate INTOPIA
    # actions whenever the latest approved Actuals provide a concrete scope.
    pricing_focus = max(
        latest_ops,
        key=lambda row: (
            num(row.get("actual_sales"))
            * num(row.get("actual_price_lc"))
            * max(num(row.get("fx_to_sf"), 1.0), 0.000001)
        ),
        default={},
    )
    technology_focus = min(
        (row for row in latest_ops if row.get("product") in {"X", "Y"}),
        key=lambda row: num(row.get("grade"), 99),
        default=pricing_focus,
    )
    for item in result:
        action = item.get("action_template") or {}
        action_type = str(action.get("type") or "")
        if action_type == "price_change":
            focus = next(
                (
                    row
                    for row in latest_ops
                    if (not action.get("area") or row.get("area") == action.get("area"))
                    and (not action.get("product") or row.get("product") == action.get("product"))
                    and (not action.get("model") or row.get("model") == action.get("model"))
                ),
                pricing_focus,
            )
            current_price = num(focus.get("actual_price_lc"))
            change = num(action.get("change_pct"))
            product = str(action.get("product") or focus.get("product") or "")
            action.update(
                {
                    "code": action.get("code") or ("A1-1" if product == "X" else "A1-2"),
                    "area": action.get("area") or focus.get("area"),
                    "product": product,
                    "model": action.get("model") or focus.get("model"),
                    "current_price_lc": current_price,
                    "price_lc": round(current_price * (1 + change), 2) if current_price > 0 else None,
                }
            )
        elif action_type == "rd":
            product = str(action.get("product") or technology_focus.get("product") or "Y")
            minimum = MINIMUM_RD_SF.get(product, 70_000)
            amount = max(minimum, num(action.get("cost_sf")))
            if budget > 0:
                amount = min(amount, budget)
            action.update(
                {
                    "code": "H1-1",
                    "area": "Liechtenstein",
                    "product": product,
                    "amount_sf": round(amount, 2),
                    "cost_sf": round(amount, 2),
                }
            )
        elif action_type == "market_research":
            product = str(pricing_focus.get("product") or "Y")
            cost_study = 51 if product == "X" else 61
            action.update(
                {
                    "code": "H1-2",
                    "area": "Liechtenstein",
                    "product": product,
                    "study_ids": [28, cost_study],
                    "cost_sf": 10_000,
                    "research_purpose": (
                        f"אימות מחיר שוק ועלות משתנה למוצר {product} לפני נעילת מחיר וכמות."
                    ),
                }
            )
        elif action_type == "capacity":
            action.setdefault("code", "A2-1")
        item["action_template"] = action

    for item in result:
        item["strategy_alignment"] = alignment
        if has_strategy:
            item.setdefault("evidence", []).append("approved strategy profile")
    result.sort(key=lambda item: (-int(item["priority"]), item["title"]))
    return result[:5]


DECISION_CATEGORY_SPECS: tuple[dict[str, Any], ...] = (
    {
        "key": "strategy",
        "label": "החלטות אסטרטגיות",
        "label_en": "Strategic Decisions",
        "catalog_category": "אסטרטגיה",
        "order": 1,
    },
    {
        "key": "finance",
        "label": "מימון",
        "label_en": "Financial",
        "catalog_category": "מימון",
        "order": 2,
    },
    {
        "key": "operations",
        "label": "ייצור ותפעול",
        "label_en": "Operation & Production",
        "catalog_category": "ייצור ותפעול",
        "order": 3,
    },
    {
        "key": "marketing",
        "label": "שיווק",
        "label_en": "Marketing",
        "catalog_category": "שיווק",
        "order": 4,
    },
)

_CATEGORY_BY_CATALOG = {
    str(item["catalog_category"]): item
    for item in DECISION_CATEGORY_SPECS
}

_RECURRING_DECISION_CODES = {
    "A1-1",
    "A1-2",
    "A2-3",
    "A2-4",
    "H1-1",
}

_RESEARCH_BY_ACTION: dict[str, set[int]] = {
    "A1-1": {17, 28, *range(31, 50)},
    "A1-2": {17, 28, *range(31, 50)},
    "A1-3": {11, 81},
    "A2-1": {10, 18, 19, 24, 40},
    "A2-3": {18, 19, 23, 24, *range(51, 60)},
    "A2-4": {18, 19, 23, 24, *range(61, 70)},
    "A3-1": {74, 79},
    "A3-2": {74, 79},
    "A3-3": {74, 79},
    "A4": {19, 23, 24},
    "H1-1": {12, 13, 14, 17, 21, 22},
    "H1-2": set(range(1, 82)),
    "H2": {20, 74, 79},
    "H4": {74, 79},
    "H5": {17, 21, 22, *range(31, 70)},
    "H6": {17, 23, 28, 74},
    "W1": {74, 79},
    "W2": {10, 18, 24, 40, 74},
    "W3": {74, 79},
}


def _action_current_state(
    action: dict[str, Any],
    latest_operations: list[dict[str, Any]],
    financial: dict[str, Any],
    research_results: list[dict[str, Any]],
) -> str:
    code = str(action.get("code") or "")
    product = str(action.get("product") or "")
    rows = [
        row
        for row in latest_operations
        if not product or str(row.get("product") or "") == product
    ]
    consolidated = financial.get("consolidated", {})
    areas = financial.get("areas", [])

    if code in {"A1-1", "A1-2"}:
        priced = [row for row in rows if num(row.get("actual_price_lc")) > 0]
        sales = sum(num(row.get("actual_sales")) for row in rows)
        inventory = sum(num(row.get("ending_inventory")) for row in rows)
        if not priced:
            return f"לא נקלטו מחירי Actual למוצר {product}; לא ניתן לכייל מחיר ופרסום."
        return (
            f"{len(priced)} פלחים מתומחרים; מכירות {sales:,.0f} יחידות ומלאי סופי "
            f"{inventory:,.0f} יחידות במוצר {product}."
        )
    if code == "A1-3":
        office_values = [
            num(row.get("sales_offices"))
            for row in latest_operations
            if row.get("sales_offices") not in (None, "")
        ]
        return (
            f"נקלטו {len(office_values)} תצפיות של משרדי מכירות."
            if office_values
            else "מספר משרדי המכירות והעלות האופטימלית לא זוהו ב-Actuals."
        )
    if code == "H6":
        return "לא זוהתה עסקת מכירה תעשייתית חתומה; נבחנת כחלופת מלאי/אספקה בלבד."
    if code == "A2-1":
        capacity = sum(num(row.get("plant_capacity")) for row in latest_operations)
        production = sum(num(row.get("actual_production")) for row in latest_operations)
        utilization = production / capacity if capacity else 0
        return (
            f"קיבולת כוללת {capacity:,.0f}; ייצור {production:,.0f}; ניצולת "
            f"{utilization:.1%}."
            if capacity
            else "לא נקלטה קיבולת מפעלים; אי אפשר להצדיק הרחבה."
        )
    if code in {"A2-3", "A2-4"}:
        capacity = sum(num(row.get("plant_capacity")) for row in rows)
        production = sum(num(row.get("actual_production")) for row in rows)
        inventory = sum(num(row.get("ending_inventory")) for row in rows)
        return (
            f"מוצר {product}: ייצור {production:,.0f}, קיבולת {capacity:,.0f}, "
            f"מלאי {inventory:,.0f}."
            if rows
            else f"לא נקלטו נתוני ייצור למוצר {product}."
        )
    if code == "A4":
        x_inventory = sum(
            num(row.get("ending_inventory"))
            for row in latest_operations
            if str(row.get("product") or "") == "X"
        )
        y_production = sum(
            num(row.get("actual_production"))
            for row in latest_operations
            if str(row.get("product") or "") == "Y"
        )
        return f"מלאי X זמין {x_inventory:,.0f}; ייצור Y אחרון {y_production:,.0f}."
    if code in {"A3-1", "A3-2", "A3-3", "W3"}:
        gaps = financial.get("liquidity_allocation", {}).get("funding_gaps", [])
        transfers = financial.get("liquidity_allocation", {}).get("transfers", [])
        return (
            f"מזומן מאוחד {num(consolidated.get('ending_cash_sf')):,.0f} SF; "
            f"{len(gaps)} פערי נזילות ו-{len(transfers)} העברות מחושבות."
        )
    if code in {"H2", "H4", "W1"}:
        return (
            f"תקציב החלטות {num(consolidated.get('available_budget_sf')):,.0f} SF; "
            f"חוב {num(consolidated.get('debt_sf')):,.0f} SF."
        )
    if code == "H1-1":
        grades = [
            int(num(row.get("grade")))
            for row in latest_operations
            if row.get("grade") not in (None, "")
        ]
        return (
            f"רמה טכנולוגית מרבית שנקלטה: {max(grades)}; נדרשת בחינת רציפות עד Q9."
            if grades
            else "לא נקלטו רמות טכנולוגיות המאפשרות לכייל השקעת מו״פ."
        )
    if code == "H1-2":
        studies = sorted(
            {
                int(num(row.get("study_id")))
                for row in research_results
                if num(row.get("study_id")) > 0
            }
        )
        return (
            f"נקלטו {len(studies)} מחקרים מאושרים: "
            + ", ".join(f"MR{value}" for value in studies[:8])
            + ("…" if len(studies) > 8 else "")
            if studies
            else "לא נקלטו מחקרי שוק מאושרים."
        )
    if code == "H5":
        grades = [
            int(num(row.get("grade")))
            for row in latest_operations
            if row.get("grade") not in (None, "")
        ]
        return (
            f"רמה מרבית בבעלות/מכירה: {max(grades)}; אין רישיון שותף מאושר בנתונים."
            if grades
            else "לא נקלטו רמות טכנולוגיות או הצעת רישיון."
        )
    if code == "W2":
        plants = sum(num(row.get("plants")) for row in latest_operations)
        return f"נרשמו {plants:,.0f} מפעלים; לא זוהתה הצעת רכישה או מכירה חתומה."
    if areas:
        return f"נבדקו נתונים מאוחדים ו-{len(areas)} אזורי פעילות."
    return "אין די נתונים ספציפיים; הפעולה נבדקה ברמת הקטלוג והחוקים בלבד."


def review_decision_catalog(
    quarter: str,
    financial: dict[str, Any],
    operations: list[dict[str, Any]],
    research_results: list[dict[str, Any]],
    candidate_recommendations: list[dict[str, Any]],
    execution_blueprint: dict[str, Any],
) -> dict[str, Any]:
    """Audit every official form before exposing category recommendations.

    Candidate recommendations are treated as signals only. Every catalog form
    receives a deterministic state/rule/research assessment, so the UI can
    show which alternatives were considered and why they were not selected.
    """

    latest_quarter = max(
        (str(row.get("quarter") or "") for row in through_quarter(operations, quarter)),
        key=quarter_number,
        default="",
    )
    latest_operations = [
        row
        for row in through_quarter(operations, quarter)
        if str(row.get("quarter") or "") == latest_quarter
    ]
    blueprint_rows = list(execution_blueprint.get("rows") or [])
    research_by_id = {
        int(num(row.get("study_id"))): row
        for row in research_results
        if num(row.get("study_id")) > 0
    }
    recommendation_by_code: dict[str, list[dict[str, Any]]] = {}
    for recommendation in candidate_recommendations:
        code = str((recommendation.get("action_template") or {}).get("code") or "")
        if code:
            recommendation_by_code.setdefault(code, []).append(recommendation)
    blueprint_by_code: dict[str, list[dict[str, Any]]] = {}
    for row in blueprint_rows:
        code = str(row.get("form_code") or "")
        if code:
            blueprint_by_code.setdefault(code, []).append(row)

    reviewed: list[dict[str, Any]] = []
    for catalog in DECISION_ACTIONS:
        code = str(catalog["code"])
        category = _CATEGORY_BY_CATALOG.get(
            str(catalog.get("category") or ""),
            DECISION_CATEGORY_SPECS[-1],
        )
        recommendations_for_form = recommendation_by_code.get(code, [])
        blueprint_for_form = blueprint_by_code.get(code, [])
        concrete_action = {}
        if blueprint_for_form:
            concrete_action = dict(blueprint_for_form[0].get("action") or {})
        elif recommendations_for_form:
            concrete_action = dict(
                recommendations_for_form[0].get("action_template") or {}
            )
        concrete_action = {
            "code": code,
            "type": catalog.get("type"),
            **({"product": catalog.get("product")} if catalog.get("product") else {}),
            **concrete_action,
        }
        checks = evaluate_rulebook_action(
            concrete_action,
            quarter=quarter,
            operations=latest_operations,
            strict=False,
        )
        blocking_checks = [
            check
            for check in checks
            if check.get("blocking") and check.get("status") == "fail"
        ]
        relevant_research = [
            research_by_id[study_id]
            for study_id in sorted(_RESEARCH_BY_ACTION.get(code, set()))
            if study_id in research_by_id
        ]
        current_state = _action_current_state(
            catalog,
            latest_operations,
            financial,
            research_results,
        )
        missing_inputs: list[str] = []
        if code in {"A1-1", "A1-2"} and not any(
            str(row.get("product") or "") == str(catalog.get("product") or "")
            and num(row.get("actual_price_lc")) > 0
            for row in latest_operations
        ):
            missing_inputs.append("מחיר ומכירות Actual לפי פלח")
        if code == "A1-3" and not any(
            row.get("sales_offices") not in (None, "")
            for row in latest_operations
        ):
            missing_inputs.append("מספר ועלות משרדי המכירות")
        if code in {"A2-1", "A2-3", "A2-4"} and not any(
            num(row.get("plant_capacity")) > 0
            for row in latest_operations
            if not catalog.get("product")
            or row.get("product") == catalog.get("product")
        ):
            missing_inputs.append("קיבולת מפעלים מאושרת")
        if code in {"H4", "H5", "H6", "W1", "W2"} and not recommendations_for_form:
            missing_inputs.append("הסכם או הצעה קונקרטית מצד שותף")

        if blocking_checks:
            status = "blocked"
            status_label = "חסום לפי חוק"
            reason = blocking_checks[0].get("message") or "זוהתה הפרת חוק חוסמת."
        elif blueprint_for_form or recommendations_for_form:
            statuses = {str(row.get("status") or "") for row in blueprint_for_form}
            if "blocked" in statuses:
                status = "blocked"
                status_label = "חסום עד תיקון"
            elif "conditional" in statuses:
                status = "recommended"
                status_label = "מומלץ בכפוף לתנאי"
            else:
                status = "recommended"
                status_label = "מומלץ לביצוע"
            reason = (
                recommendations_for_form[0].get("rationale")
                if recommendations_for_form
                else blueprint_for_form[0].get("gate")
            ) or "הפעולה נכללה בתכנית הביצוע לאחר בדיקת מצב, חוק ותקציב."
        elif code in _RECURRING_DECISION_CODES and not missing_inputs:
            status = "required"
            status_label = "נדרשת החלטה רבעונית"
            reason = (
                "זהו טופס מחזורי שיש לקבוע בכל רבעון; לא זוהה טריגר לשינוי חריג, "
                "אך יש לאשר את הערך מול התקציב והתחזית."
            )
        elif missing_inputs:
            status = "missing_data"
            status_label = "חסר מידע"
            reason = "אין בסיס מספק להמלצה מספרית: " + ", ".join(missing_inputs) + "."
        elif relevant_research:
            status = "monitor"
            status_label = "למעקב"
            reason = "נמצא מחקר רלוונטי, אך התוצאה אינה יוצרת כרגע טריגר לפעולה."
        else:
            status = "not_required"
            status_label = "לא נדרש כרגע"
            reason = "לא זוהו טריגר, התחייבות או יתרון כלכלי המצדיקים את הפעולה ברבעון זה."

        next_step = ""
        if blueprint_for_form:
            next_step = " | ".join(
                str(row.get("input_instruction") or row.get("recommended_value") or "")
                for row in blueprint_for_form[:2]
                if row.get("input_instruction") or row.get("recommended_value")
            )
        elif recommendations_for_form:
            next_step = str(recommendations_for_form[0].get("title") or "")
        elif status == "required":
            next_step = f"לאשר את ערכי {code} לאחר בדיקת המחיר, הכמות והתקציב."
        elif missing_inputs:
            next_step = "להשלים: " + ", ".join(missing_inputs) + "."
        else:
            next_step = "אין הזנה נדרשת; לבדוק מחדש לאחר Actual או מחקר חדש."

        research_evidence = [
            {
                "study_id": row.get("study_id"),
                "source_label": row.get("source_label")
                or f"{row.get('quarter', '')} · MR{row.get('study_id', '')}",
                "headline": row.get("headline") or row.get("key_result") or "",
                "recommendation": row.get("recommendation") or "",
            }
            for row in relevant_research[:4]
        ]
        rule_evidence = [
            {
                "rule_id": f"FORM-{code}",
                "status": "pass",
                "message": str(catalog.get("timing") or ""),
                "source": f"ממשק INTOPIA · טופס {code}",
            },
            *[
                {
                    "rule_id": check.get("rule_id"),
                    "status": check.get("status"),
                    "message": check.get("message"),
                    "source": (check.get("citation") or {}).get("source", ""),
                }
                for check in checks
            ],
        ]
        reviewed.append(
            {
                "code": code,
                "type": catalog.get("type"),
                "title": catalog.get("title"),
                "category": category["key"],
                "category_label": category["label"],
                "category_label_en": category["label_en"],
                "category_order": category["order"],
                "status": status,
                "status_label": status_label,
                "priority": max(
                    [
                        int(row.get("priority") or 0)
                        for row in recommendations_for_form
                    ]
                    or [0]
                ),
                "reason": reason,
                "current_state": current_state,
                "next_step": next_step,
                "timing": catalog.get("timing"),
                "areas": catalog.get("areas") or [],
                "product": catalog.get("product"),
                "rules_checked": rule_evidence,
                "research_used": research_evidence,
                "missing_information": missing_inputs,
                "recommendation_ids": [
                    row.get("id")
                    for row in recommendations_for_form
                ],
                "execution_steps": [
                    row.get("order")
                    for row in blueprint_for_form
                    if row.get("order") is not None
                ],
                "rulebook_version": RULEBOOK_VERSION,
            }
        )

    reviewed.sort(
        key=lambda row: (
            int(row["category_order"]),
            {
                "recommended": 0,
                "required": 1,
                "blocked": 2,
                "missing_data": 3,
                "monitor": 4,
                "not_required": 5,
            }.get(str(row["status"]), 9),
            -int(row["priority"]),
            str(row["code"]),
        )
    )
    categories = []
    for spec in DECISION_CATEGORY_SPECS:
        actions = [
            row
            for row in reviewed
            if row["category"] == spec["key"]
        ]
        categories.append(
            {
                **spec,
                "actions": actions,
                "counts": {
                    status: sum(
                        1
                        for row in actions
                        if row["status"] == status
                    )
                    for status in (
                        "recommended",
                        "required",
                        "blocked",
                        "missing_data",
                        "monitor",
                        "not_required",
                    )
                },
            }
        )
    return {
        "quarter": quarter,
        "actual_as_of": latest_quarter or None,
        "rulebook_version": RULEBOOK_VERSION,
        "evaluation_order": "full_catalog_before_recommendation_filter",
        "summary": {
            "evaluated_count": len(reviewed),
            "catalog_count": len(DECISION_ACTIONS),
            "coverage_pct": round(
                100 * len(reviewed) / max(1, len(DECISION_ACTIONS)),
                1,
            ),
            "recommended_count": sum(
                1 for row in reviewed if row["status"] == "recommended"
            ),
            "required_count": sum(
                1 for row in reviewed if row["status"] == "required"
            ),
            "blocked_count": sum(
                1 for row in reviewed if row["status"] == "blocked"
            ),
            "missing_data_count": sum(
                1 for row in reviewed if row["status"] == "missing_data"
            ),
            "headline": (
                f"נבדקו כל {len(reviewed)} טפסי ההחלטה מול מצב החברה, "
                "ה-Rulebook ומחקרי השוק לפני סינון ההמלצות."
            ),
        },
        "categories": categories,
        "actions": reviewed,
    }


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

    def research_matches(research: dict[str, Any], decision: dict[str, Any]) -> bool:
        """Head-office research can inform every operating area for the same product."""
        research_area = str(research.get("area") or "")
        decision_area = str(decision.get("area") or "")
        area_match = (
            not research_area
            or research_area == "Liechtenstein"
            or not decision_area
            or research_area == decision_area
        )
        research_product = str(research.get("product") or "")
        decision_product = str(decision.get("product") or "")
        product_match = (
            not research_product
            or not decision_product
            or research_product == decision_product
        )
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
        if node["type"] == "money_transfer":
            for candidate in nodes:
                if (
                    candidate["type"] in {"currency_conversion", "local_currency_exchange"}
                    and candidate["area"] in {"", node["area"]}
                ):
                    add_edge(
                        candidate,
                        node,
                        kind="funding",
                        hard=True,
                        reason="יש להכין את מטבע המקור לפני ביצוע העברה בין אזורים.",
                        timing="המרת המטבע קודמת להעברה; אחרת סכום הנטו והעמלה אינם ניתנים לביצוע.",
                    )
            for candidate in nodes:
                if (
                    candidate["id"] != node["id"]
                    and node["target_area"]
                    and candidate["area"] == node["target_area"]
                    and (
                        candidate["cost_sf"] > 0
                        or candidate["type"]
                        in {
                            "services_payment",
                            "production",
                            "rd",
                            "plant_construction",
                            "sales_offices",
                            "advertising",
                            "price_advertising",
                        }
                    )
                ):
                    add_edge(
                        node,
                        candidate,
                        kind="funding",
                        hard=True,
                        reason=f"הפעולה ב-{node['target_area']} תלויה בנזילות שהועברה מאזור המקור.",
                        timing="יש להשלים את ההעברה ולאמת את יתרת היעד לפני אישור ההוצאה.",
                    )

        if node["type"] in irreversible_types | expensive_types:
            matching_research = [
                candidate for candidate in research_nodes if research_matches(candidate, node)
            ]
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

        if node["type"] == "production":
            for candidate in nodes:
                if candidate["type"] == "industrial_sale" and same_scope(node, candidate):
                    add_edge(
                        node,
                        candidate,
                        kind="prerequisite",
                        hard=True,
                        reason="מכירה תעשייתית מחייבת מלאי זמין; הייצור או המלאי הקיים צריכים להקדים אותה.",
                        timing="יש לאמת את הכמות הזמינה לאחר הייצור ולפני התחייבות לכמות מכירה.",
                    )

        if node["type"] == "component_transfer":
            for candidate in nodes:
                if (
                    candidate["type"] == "production"
                    and candidate["product"] == "X"
                    and (
                        candidate["area"] in {"", node["area"]}
                        or candidate["target_area"] == node["area"]
                    )
                ):
                    add_edge(
                        candidate,
                        node,
                        kind="prerequisite",
                        hard=True,
                        reason="העברת שבבי X תלויה בייצור או במלאי X זמין באזור המקור.",
                        timing="ייצור X → אימות מלאי → העברת X → ייצור Y.",
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

        if node["type"] in demand_types:
            for candidate in research_nodes:
                if research_matches(candidate, node):
                    add_edge(
                        candidate,
                        node,
                        kind="prerequisite",
                        hard=False,
                        reason="מחקר המחיר, הביקוש או המתחרים צריך לעדכן את החלטת המחיר והפרסום.",
                        timing="יש לקרוא את תוצאת המחקר לפני נעילת המחיר; ללא מחקר ההמלצה נשארת בטווח ולא בנקודה.",
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


def build_execution_blueprint(
    quarter: str,
    actions: list[dict[str, Any]],
    dependency_analysis: dict[str, Any],
    *,
    recommendations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Translate a decision graph into an executable, auditable INTOPIA plan.

    The recommendation cards answer "why".  This blueprint answers "what do
    we enter, in which form, in what order, and what must happen first".
    Values remain explicit assumptions when the available evidence is not
    strong enough for a ready-to-enter number.
    """
    recommendations = recommendations or []
    recommendation_by_id = {
        str(row.get("id") or ""): row
        for row in recommendations
        if row.get("id")
    }
    nodes = dependency_analysis.get("nodes", [])
    node_by_id = {str(row.get("id")): row for row in nodes}
    action_by_id = {
        str(node.get("id")): dict(actions[int(node.get("index") or 0)])
        for node in nodes
        if 0 <= int(node.get("index") or 0) < len(actions)
    }
    sequence_rows = dependency_analysis.get("recommended_sequence", [])
    step_by_id = {
        str(row.get("id")): int(row.get("step") or 0)
        for row in sequence_rows
    }
    incoming_by_id: dict[str, list[dict[str, Any]]] = {}
    outgoing_by_id: dict[str, list[dict[str, Any]]] = {}
    for edge in dependency_analysis.get("edges", []):
        incoming_by_id.setdefault(str(edge.get("to")), []).append(edge)
        outgoing_by_id.setdefault(str(edge.get("from")), []).append(edge)
    gaps_by_id: dict[str, list[dict[str, Any]]] = {}
    for gap in dependency_analysis.get("gaps", []):
        gaps_by_id.setdefault(str(gap.get("action_id")), []).append(gap)

    phase_by_type = {
        "market_research": "1 · מידע ואימות",
        "currency_conversion": "1 · נזילות ומימון",
        "local_currency_exchange": "1 · נזילות ומימון",
        "money_transfer": "1 · נזילות ומימון",
        "loan": "1 · נזילות ומימון",
        "invest_borrow": "1 · נזילות ומימון",
        "home_office_finance": "1 · נזילות ומימון",
        "intercompany_loan": "1 · נזילות ומימון",
        "services_payment": "2 · סגירת התחייבויות",
        "rd": "2 · טכנולוגיה וקיבולת",
        "grade_license": "2 · טכנולוגיה וקיבולת",
        "plant_construction": "2 · טכנולוגיה וקיבולת",
        "capacity": "2 · טכנולוגיה וקיבולת",
        "component_transfer": "3 · שרשרת אספקה",
        "production": "4 · ייצור",
        "sales_offices": "5 · מסחור",
        "price_change": "5 · מסחור",
        "price_advertising": "5 · מסחור",
        "advertising": "5 · מסחור",
        "industrial_sale": "5 · מסחור",
        "factory_sale": "5 · מסחור",
    }

    def number(value: Any, decimals: int = 0) -> str:
        amount = num(value)
        return f"{amount:,.{decimals}f}"

    def base_row(
        node_id: str,
        action: dict[str, Any],
        node: dict[str, Any],
    ) -> dict[str, Any]:
        action_type = str(node.get("type") or action.get("type") or "generic")
        catalog = decision_action(str(action.get("code") or node.get("code") or ""))
        code = str(action.get("code") or node.get("code") or catalog.get("code") or "—")
        area = str(action.get("area") or node.get("area") or "Liechtenstein")
        recommendation = recommendation_by_id.get(node_id, {})
        dependencies = []
        for edge in incoming_by_id.get(node_id, []):
            source_id = str(edge.get("from"))
            source = node_by_id.get(source_id, {})
            dependencies.append(
                {
                    "id": source_id,
                    "step": step_by_id.get(source_id),
                    "title": source.get("title") or source_id,
                    "kind": edge.get("kind"),
                    "hard": bool(edge.get("hard")),
                    "reason": edge.get("reason") or "",
                    "timing": edge.get("timing") or "",
                }
            )
        gaps = gaps_by_id.get(node_id, [])
        is_specific = any(
            action.get(field) not in (None, "", [])
            for field in (
                "amount_sf",
                "source_amount_lc",
                "price_lc",
                "units",
                "cost_sf",
                "study_id",
                "study_ids",
                "plant_count",
                "office_delta",
                "grade",
            )
        )
        blocked = bool(gaps) or any(
            dep.get("hard") and dep.get("step") is None
            for dep in dependencies
        )
        conditional_types = {
            "capacity",
            "plant_construction",
            "grade_license",
            "factory_sale",
            "strategy_review",
        }
        status = "blocked" if blocked else (
            "conditional" if action_type in conditional_types or not is_specific else "ready"
        )
        decision_type = "חובה" if status == "ready" and (
            action_type in {"money_transfer", "currency_conversion", "services_payment"}
            or any(dep.get("hard") for dep in dependencies)
        ) else ("מותנה" if status == "conditional" else ("חסום" if status == "blocked" else "מומלץ"))
        return {
            "id": node_id,
            "sequence": step_by_id.get(node_id, 0),
            "phase": phase_by_type.get(action_type, "6 · החלטות משלימות"),
            "recommendation_id": node_id if node_id in recommendation_by_id else "",
            "area": area,
            "target_area": str(action.get("target_area") or node.get("target_area") or ""),
            "form_code": code,
            "action_name": str(
                action.get("title")
                or node.get("title")
                or catalog.get("title")
                or action_type
            ),
            "action_type": action_type,
            "decision_type": decision_type,
            "status": status,
            "status_label": {
                "ready": "מוכן להזנה",
                "conditional": "מותנה באישור",
                "blocked": "חסום עד השלמה",
            }[status],
            "gate": (
                "יש להשלים תחילה את התלויות המסומנות."
                if dependencies
                else "אין תלות מוקדמת שזוהתה."
            ),
            "dependencies": dependencies,
            "coordinates_with": [
                {
                    "id": other_id,
                    "step": step_by_id.get(other_id),
                    "title": node_by_id.get(other_id, {}).get("title") or other_id,
                }
                for other_id in (
                    next(
                        (
                            row.get("coordinates_with", [])
                            for row in sequence_rows
                            if str(row.get("id")) == node_id
                        ),
                        [],
                    )
                )
            ],
            "unlocks": [
                {
                    "id": str(edge.get("to")),
                    "step": step_by_id.get(str(edge.get("to"))),
                    "title": node_by_id.get(str(edge.get("to")), {}).get("title") or edge.get("to"),
                }
                for edge in outgoing_by_id.get(node_id, [])
                if edge.get("kind") != "coordination"
            ],
            "gaps": gaps,
            "source": " · ".join(str(item) for item in recommendation.get("evidence", []) if item)
            or "נתוני Actual, Rulebook ומודל החלטות",
            "confidence": (
                recommendation.get("ai_recommendation", {}).get("confidence")
                or ("גבוהה" if status == "ready" else "בינונית")
            ),
            "cost_sf": round(max(0.0, num(action.get("cost_sf"))), 2),
            "action": action,
        }

    rows: list[dict[str, Any]] = []
    for sequence in sequence_rows:
        node_id = str(sequence.get("id"))
        node = node_by_id.get(node_id, {})
        action = action_by_id.get(node_id, {})
        if not node or not action:
            continue
        row = base_row(node_id, action, node)
        action_type = row["action_type"]
        area = row["area"]
        target_area = row["target_area"]

        if action_type == "money_transfer":
            source_currency = str(action.get("source_currency") or action.get("currency") or "")
            source_amount = num(action.get("source_amount_lc"))
            net_sf = num(action.get("net_amount_sf"), num(action.get("amount_sf")))
            gross_sf = num(action.get("gross_source_amount_sf"), net_sf + num(action.get("cost_sf")))
            fee_sf = num(action.get("estimated_fx_fee_sf"), num(action.get("cost_sf")))
            recommended_transfer_value = (
                f"{number(source_amount, 2)} {source_currency}"
                if source_amount > 0 and source_currency
                else f"{number(net_sf, 2)} SF נטו"
            )
            row.update(
                {
                    "field_name": "סכום העברה בין אזורים",
                    "recommended_value": recommended_transfer_value,
                    "raw_value": source_amount if source_amount > 0 else net_sf,
                    "unit": source_currency or "SF",
                    "gate": (
                        f"העברה {area} → {target_area}. יש לבצע לפני הוצאה באזור היעד; "
                        f"כולל עמלת מט״ח משוערת {number(fee_sf, 2)} SF."
                    ),
                    "expected_outcome": (
                        f"{number(net_sf, 2)} SF נטו יעמדו ב-{target_area}; "
                        f"ב-{area} יישארו {number(action.get('source_cash_after_sf'), 2)} SF."
                    ),
                    "input_instruction": (
                        f"בטופס {row['form_code']} בחר מקור {area}, יעד {target_area}, "
                        f"מטבע {source_currency or 'המקור'} והזן {recommended_transfer_value}."
                    ),
                    "cost_sf": round(fee_sf, 2),
                }
            )
        elif action_type in {"currency_conversion", "local_currency_exchange"}:
            value = num(action.get("amount_lc"), num(action.get("amount_sf")))
            row.update(
                {
                    "field_name": "המרת מטבע",
                    "recommended_value": f"{number(value, 2)} {action.get('currency') or 'מטבע מקומי'}",
                    "raw_value": value,
                    "unit": str(action.get("currency") or ""),
                    "expected_outcome": "הכנת המטבע הנדרש להעברה או לתשלום הבא בשרשרת.",
                    "input_instruction": f"בטופס {row['form_code']} המר את הסכום לפני פעולת ההעברה התלויה בו.",
                }
            )
        elif action_type in {"price_change", "price_advertising", "advertising"}:
            current_price = num(action.get("current_price_lc"))
            proposed_price = num(action.get("price_lc"))
            change = num(action.get("change_pct"))
            if proposed_price <= 0 and current_price > 0:
                proposed_price = current_price * (1 + change)
            row.update(
                {
                    "field_name": f"מחיר {action.get('product') or ''} {action.get('model') or ''}".strip(),
                    "recommended_value": (
                        f"{number(proposed_price, 2)} במטבע מקומי"
                        if proposed_price > 0
                        else f"שינוי של {change:+.1%}"
                    ),
                    "raw_value": proposed_price if proposed_price > 0 else change,
                    "unit": "מטבע מקומי",
                    "gate": "יש לתאם עם כמות הייצור, המלאי והפרסום באותו שוק.",
                    "expected_outcome": (
                        f"שינוי מחיר של {change:+.1%}; ההשפעה הסופית תלויה באלסטיות ובמחירי המתחרים."
                    ),
                    "input_instruction": f"בטופס {row['form_code']} הזן את המחיר המומלץ ובדוק במקביל את תקציב הפרסום.",
                }
            )
        elif action_type == "market_research":
            study_ids = action.get("study_ids") or [action.get("study_id")]
            study_ids = [item for item in study_ids if item not in (None, "")]
            if not study_ids:
                study_ids = ["נדרש לבחור מחקר רלוונטי"]
                row["status"] = "conditional"
                row["status_label"] = "מותנה בבחירת מחקר"
                row["decision_type"] = "מותנה"
            for position, study_id in enumerate(study_ids, start=1):
                study_row = dict(row)
                study_row["id"] = f"{node_id}-mr-{position}"
                study_row.update(
                    {
                        "field_name": f"Market Research {position}",
                        "recommended_value": f"MR{study_id}" if str(study_id).isdigit() else str(study_id),
                        "raw_value": study_id,
                        "unit": "מספר מחקר",
                        "gate": "יש להזמין לפני החלטה יקרה או בלתי הפיכה שהמחקר עשוי לשנות.",
                        "expected_outcome": str(
                            action.get("research_purpose")
                            or "צמצום אי-הוודאות והגדרת נקודת היפוך להחלטה."
                        ),
                        "input_instruction": f"בטופס {row['form_code']} בחר מחקר {study_id}.",
                    }
                )
                rows.append(study_row)
            continue
        elif action_type == "rd":
            amount = max(num(action.get("amount_sf")), num(action.get("cost_sf")))
            row.update(
                {
                    "field_name": f"מו״פ למוצר {action.get('product') or 'X/Y'}",
                    "recommended_value": f"{number(amount, 0)} SF" if amount > 0 else "נדרש תקציב מאושר",
                    "raw_value": amount if amount > 0 else None,
                    "unit": "SF",
                    "gate": "יש להבטיח מימון ורצפת מזומן לפני ההשקעה.",
                    "expected_outcome": "שיפור פוטנציאל הטכנולוגיה והיכולת להגיע ליעד Q9.",
                    "input_instruction": f"בטופס {row['form_code']} הזן את תקציב המו״פ לאחר אישור מקורות המימון.",
                }
            )
        elif action_type in {"production", "component_transfer", "industrial_sale"}:
            units = num(action.get("units"))
            row.update(
                {
                    "field_name": (
                        "כמות ייצור"
                        if action_type == "production"
                        else ("כמות שבבים להעברה" if action_type == "component_transfer" else "כמות מכירה תעשייתית")
                    ),
                    "recommended_value": f"{number(units, 0)} יחידות" if units > 0 else "נדרש חישוב כמות",
                    "raw_value": units if units > 0 else None,
                    "unit": "יחידות",
                    "gate": (
                        "ייצור Y מותנה בזמינות X מתאים ובקיבולת; מכירה מותנית במלאי זמין."
                        if str(action.get("product") or "") == "Y" or action_type == "industrial_sale"
                        else "יש לבדוק קיבולת, מלאי וביקוש לפני אישור הכמות."
                    ),
                    "expected_outcome": str(action.get("expected_outcome") or "איזון בין זמינות, מכירות ומלאי סוף רבעון."),
                    "input_instruction": f"בטופס {row['form_code']} הזן את הכמות רק לאחר השלמת התלויות המוצגות.",
                }
            )
        else:
            candidates = [
                ("amount_sf", "סכום", "SF"),
                ("plant_count", "מספר מפעלים", "מפעלים"),
                ("office_delta", "שינוי במספר משרדים", "משרדים"),
                ("grade", "רמה טכנולוגית", "רמה"),
                ("capacity_units", "תוספת קיבולת", "יחידות"),
            ]
            field, label, unit = next(
                ((field, label, unit) for field, label, unit in candidates if action.get(field) not in (None, "")),
                ("", "פרמטר החלטה", ""),
            )
            value = action.get(field) if field else None
            row.update(
                {
                    "field_name": label,
                    "recommended_value": number(value, 2) if value is not None else "נדרש אישור מספרי",
                    "raw_value": value,
                    "unit": unit,
                    "expected_outcome": str(action.get("expected_outcome") or "השפעה תיבדק בסימולציה לפני אישור."),
                    "input_instruction": f"פתח את טופס {row['form_code']}, אמת את התנאי והזן את הערך המאושר.",
                }
            )
        rows.append(row)

    rows.sort(key=lambda row: (int(row.get("sequence") or 0), str(row.get("id"))))
    for index, row in enumerate(rows, start=1):
        row["order"] = index
    ready_count = sum(1 for row in rows if row.get("status") == "ready")
    conditional_count = sum(1 for row in rows if row.get("status") == "conditional")
    blocked_count = sum(1 for row in rows if row.get("status") == "blocked")
    return {
        "quarter": quarter,
        "rows": rows,
        "summary": {
            "row_count": len(rows),
            "ready_count": ready_count,
            "conditional_count": conditional_count,
            "blocked_count": blocked_count,
            "dependency_count": len(dependency_analysis.get("edges", [])),
            "planned_cash_out_sf": round(sum(num(row.get("cost_sf")) for row in rows), 2),
            "headline": (
                f"{ready_count} פעולות מוכנות להזנה, {conditional_count} מותנות ו-{blocked_count} חסומות. "
                "יש לעבוד לפי הסדר; כל שורה מסבירה מה מזינים ומה היא פותחת."
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
    validated_actions = [
        {
            **action,
            "cost_sf": max(
                num(action.get("cost_sf")),
                impacts[index].cost_sf,
            ),
        }
        for index, action in enumerate(actions)
    ]
    rule_validation = evaluate_rulebook_portfolio(
        validated_actions,
        quarter=quarter,
        operations=operations,
        available_budget_sf=effective_budget,
        base_cash_sf=base_cash,
        cash_buffer_sf=cash_buffer,
        strict=bool(payload.get("decision_pack", False)),
    )
    area_aliases = {
        "usa": "USA",
        "united states": "USA",
        "ארהב": "USA",
        'ארה"ב': "USA",
        "europe": "Europe",
        "אירופה": "Europe",
        "brazil": "Brazil",
        "ברזיל": "Brazil",
        "liechtenstein": "Liechtenstein",
        "ליכטנשטיין": "Liechtenstein",
        "home office": "Liechtenstein",
        "מטה": "Liechtenstein",
    }

    def canonical_area(value: Any) -> str:
        text = str(value or "").strip()
        return area_aliases.get(text.lower(), text)

    area_rows = {
        canonical_area(row.get("area")): row
        for row in financial.get("areas", [])
        if row.get("area")
    }
    area_outflows: dict[str, float] = {}
    for index, action in enumerate(actions):
        area = canonical_area(action.get("area"))
        if not area:
            continue
        catalog = decision_action(str(action.get("code") or ""))
        action_type = str(action.get("type") or catalog.get("type") or "")
        outflow = max(0.0, impacts[index].cost_sf)
        if action_type == "money_transfer":
            outflow += max(0.0, num(action.get("amount_sf")))
        if outflow:
            area_outflows[area] = area_outflows.get(area, 0.0) + outflow

    area_checks: list[dict[str, Any]] = []
    strict_pack = bool(payload.get("decision_pack", False))
    for area, outflow in sorted(area_outflows.items()):
        row = area_rows.get(area)
        if row is None:
            area_checks.append(
                {
                    "rule_id": "AREA-LIQUIDITY-SOURCE",
                    "status": "fail" if strict_pack else "warn",
                    "message": f"לא קיימת יתרת מזומן מאושרת עבור {area}; לא ניתן לאמת הוצאה של {outflow:,.0f} SF.",
                    "blocking": strict_pack,
                    "field": "area",
                    "remediation": f"השלימו ואשרו מזומן והתחייבויות עבור {area} לפני אישור החבילה.",
                }
            )
            continue
        cash = num(row.get("ending_cash_sf"))
        commitments = num(row.get("capex_commitments_sf"))
        available = max(0.0, cash - commitments)
        area_checks.append(
            {
                "rule_id": "AREA-LIQUIDITY-SOURCE",
                "status": "fail" if outflow > available + 0.01 else "pass",
                "message": (
                    f"הוצאות מתוכננות ב-{area}: {outflow:,.0f} SF; "
                    f"מזומן פנוי מקומי: {available:,.0f} SF."
                ),
                "blocking": outflow > available + 0.01,
                "field": "amount_sf",
                "remediation": (
                    f"העבירו לפחות {outflow - available:,.0f} SF אל {area}, "
                    "הקטינו את הפעולות או דחו אותן."
                    if outflow > available + 0.01
                    else ""
                ),
            }
        )
    if area_checks:
        rule_validation["checks"].extend(area_checks)
        area_blocking = [
            row for row in area_checks
            if row.get("blocking") and row.get("status") == "fail"
        ]
        area_warnings = [
            row for row in area_checks
            if not row.get("blocking") and row.get("status") != "pass"
        ]
        rule_validation["violations"].extend(area_blocking)
        rule_validation["warnings"].extend(
            row for row in area_checks if not row.get("blocking")
        )
        rule_validation["feasible"] = not rule_validation["violations"]
        readiness = rule_validation.get("readiness", {})
        readiness["blocking_count"] = len(rule_validation["violations"])
        readiness["warning_count"] = len(
            [
                row for row in rule_validation["warnings"]
                if row.get("status") != "pass"
            ]
        )
        readiness["status"] = (
            "blocked"
            if readiness["blocking_count"]
            else ("conditional" if readiness["warning_count"] else "ready")
        )
        readiness["label"] = {
            "ready": "מוכן להגשה",
            "conditional": "מוכן בכפוף לתיקונים",
            "blocked": "חסום",
        }[readiness["status"]]
        readiness["required_fixes"] = list(
            dict.fromkeys(
                [
                    *readiness.get("required_fixes", []),
                    *[
                        str(row.get("remediation") or row.get("message") or "")
                        for row in area_blocking
                    ],
                ]
            )
        )
        rule_validation["readiness"] = readiness
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
    twin_baseline = build_digital_twin_state(quarter, financial, operations)
    impact_payloads = [asdict(item) for item in impacts]
    twin_scenarios = {
        "low": project_digital_twin(
            quarter, twin_baseline, actions, impact_payloads, multiplier=0.65
        ),
        "base": project_digital_twin(
            quarter, twin_baseline, actions, impact_payloads, multiplier=1.0
        ),
        "high": project_digital_twin(
            quarter, twin_baseline, actions, impact_payloads, multiplier=1.25
        ),
    }
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
        "digital_twin": {
            "baseline": twin_baseline,
            "scenarios": twin_scenarios,
            "base": twin_scenarios["base"],
            "actuals_mutated": False,
        },
        "warnings": [warning for item in impacts for warning in item.warnings],
        "confidence_change": round(sum(item.confidence_delta for item in impacts), 2),
        "assumptions": ["השפעות נמוך/בסיס/גבוה נגזרות מהנתונים שאושרו ומהנחות הפעולה, לא מהאלגוריתם הרשמי.", "הציון מפוצל תמיד ל-50% ביצועי עבר ו-50% פוטנציאל עתידי; משקלי המשנה הם מודל ניהולי פנימי.", "סימולציה אינה משנה נתוני אמת עד לאישור."],
    }

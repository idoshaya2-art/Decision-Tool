from __future__ import annotations

from dataclasses import dataclass
from statistics import mean
from typing import Any, Iterable


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
    data_as_of = str(latest.get("quarter") or latest_area_quarter or quarter)

    def area_sf(row: dict[str, Any], field: str) -> float:
        return num(row.get(field)) * max(num(row.get("fx_to_sf"), 1), 0.000001)

    area_cash = sum(area_sf(row, "ending_cash_lc") for row in current_areas)
    ending_cash = num(latest.get("ending_cash_sf")) or area_cash
    commitments = sum(area_sf(row, "capex_commitments_lc") for row in current_areas)
    debt = num(latest.get("debt_sf")) or sum(area_sf(row, "debt_lc") for row in current_areas)
    inventory = sum(area_sf(row, "inventory_value_lc") for row in current_areas)
    current_assets = sum(area_sf(row, "current_assets_lc") for row in current_areas)
    current_liabilities = sum(area_sf(row, "current_liabilities_lc") for row in current_areas)
    working_capital = current_assets - current_liabilities if current_assets or current_liabilities else num(latest.get("ar_sf")) - num(latest.get("ap_sf")) + inventory
    available_budget = max(0.0, ending_cash - commitments - max(0.0, cash_buffer_sf))

    by_area = []
    for row in current_areas:
        cash_sf = area_sf(row, "ending_cash_lc")
        area_commitments = area_sf(row, "capex_commitments_lc")
        by_area.append(
            {
                **row,
                "revenue_sf": round(area_sf(row, "revenue_lc"), 2),
                "net_profit_sf": round(area_sf(row, "net_profit_lc"), 2),
                "ending_cash_sf": round(cash_sf, 2),
                "debt_sf": round(area_sf(row, "debt_lc"), 2),
                "inventory_value_sf": round(area_sf(row, "inventory_value_lc"), 2),
                "working_capital_sf": round(area_sf(row, "current_assets_lc") - area_sf(row, "current_liabilities_lc"), 2),
                "capex_commitments_sf": round(area_commitments, 2),
                "available_budget_sf": round(max(0.0, cash_sf - area_commitments), 2),
            }
        )

    return {
        "quarter": quarter,
        "data_as_of": data_as_of,
        "area_data_as_of": latest_area_quarter or None,
        "consolidated": {
            "revenue_sf": num(latest.get("revenue_sf")),
            "gross_profit_sf": num(latest.get("gross_profit_sf")),
            "net_profit_sf": num(latest.get("net_profit_sf")),
            "ending_cash_sf": round(ending_cash, 2),
            "debt_sf": round(debt, 2),
            "inventory_value_sf": round(inventory, 2),
            "working_capital_sf": round(working_capital, 2),
            "capex_commitments_sf": round(commitments, 2),
            "cash_buffer_sf": round(max(0.0, cash_buffer_sf), 2),
            "available_budget_sf": round(available_budget, 2),
        },
        "areas": sorted(by_area, key=lambda row: str(row.get("area", ""))),
        "sources": [f"{data_as_of} consolidated finance", *[f"{latest_area_quarter} finance: {row.get('area')}" for row in by_area]],
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
    remaining = max(0, 9 - quarter_number(quarter))

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
        "from_quarter": quarter,
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
    score_delta: float = 0.0
    confidence_delta: float = 0.0


def _action_impact(action: dict[str, Any], operations: list[dict[str, Any]]) -> ActionImpact:
    action_type = str(action.get("type") or "generic")
    cost = max(0.0, num(action.get("cost_sf")))
    matching = [row for row in operations if (not action.get("area") or row.get("area") == action.get("area")) and (not action.get("product") or row.get("product") == action.get("product")) and (not action.get("model") or row.get("model") == action.get("model"))]
    revenue_base = sum(num(row.get("actual_sales")) * num(row.get("actual_price_lc")) / max(num(row.get("fx_to_sf"), 1), 1) for row in matching)
    if action_type == "price_change":
        change = num(action.get("change_pct"))
        elasticity = max(0.0, num(action.get("elasticity"), 1.0))
        demand_change = -elasticity * change
        revenue_delta = revenue_base * ((1 + change) * (1 + demand_change) - 1)
        return ActionImpact(cost, revenue_delta, revenue_delta * 0.55 - cost, clamp(abs(revenue_delta) / max(abs(revenue_base), 1) * 6, 0, 4), 0)
    if action_type == "production":
        units = num(action.get("units"))
        variable_cost = num(action.get("variable_cost_sf"))
        price = num(action.get("price_sf"))
        sales_ratio = clamp(num(action.get("sell_through"), 0.75), 0, 1)
        cost = cost or max(0.0, units * variable_cost)
        revenue_delta = max(0.0, units * sales_ratio * price)
        return ActionImpact(cost, revenue_delta, revenue_delta - cost, clamp(revenue_delta / max(cost, 1) * 1.5, 0, 5), 0)
    if action_type == "advertising":
        uplift = clamp(num(action.get("expected_sales_uplift"), 0.04), 0, 0.5)
        revenue_delta = revenue_base * uplift
        return ActionImpact(cost, revenue_delta, revenue_delta * 0.45 - cost, clamp(uplift * 20, 0, 4), 0)
    if action_type == "rd":
        return ActionImpact(cost, 0, -cost, clamp(cost / 250_000 * 4, 0, 6), 0)
    if action_type == "capacity":
        return ActionImpact(cost, 0, -cost, clamp(num(action.get("capacity_units")) / 100_000, 0, 5), 0)
    if action_type == "market_research":
        return ActionImpact(cost, 0, -cost, 0, 0.12)
    if action_type == "loan":
        amount = max(0.0, num(action.get("amount_sf")))
        interest = max(0.0, num(action.get("interest_sf")))
        return ActionImpact(-amount, 0, -interest, -clamp(interest / max(amount, 1) * 10, 0, 3), 0)
    if action_type == "partnership":
        return ActionImpact(cost, num(action.get("revenue_delta_sf")), num(action.get("profit_delta_sf")) - cost, clamp(num(action.get("score_delta"), 2), -5, 8), 0)
    return ActionImpact(cost, num(action.get("revenue_delta_sf")), num(action.get("profit_delta_sf")) - cost, num(action.get("score_delta")), 0)


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
        score_delta = sum(item.score_delta for item in impacts) * multiplier
        cash = base_cash - total_cost + max(0.0, revenue_delta) * 0.35
        return {
            "revenue_sf": round(base_revenue + revenue_delta, 2),
            "net_profit_sf": round(base_profit + profit_delta, 2),
            "ending_cash_sf": round(cash, 2),
            "q9_score": round(clamp(num(base_score) + score_delta), 1) if base_score is not None else None,
        }

    sequence = []
    for action, impact in sorted(zip(actions, impacts), key=lambda pair: (pair[1].cost_sf > available_budget, -(pair[1].score_delta / max(abs(pair[1].cost_sf), 1)))):
        sequence.append({"action": action, "cost_sf": round(impact.cost_sf, 2), "expected_score_delta": round(impact.score_delta, 2), "value_per_100k_sf": round(impact.score_delta / max(abs(impact.cost_sf), 1) * 100_000, 2)})

    base_case = scenario(1.0)
    violations = []
    if total_cost > available_budget:
        violations.append("עלות הפעולות גבוהה מהתקציב הזמין.")
    if base_case["ending_cash_sf"] < cash_buffer:
        violations.append("התרחיש יורד מתחת לרצפת המזומן.")
    return {
        "quarter": quarter,
        "name": payload.get("name", "תרחיש חדש"),
        "actions": actions,
        "budget": {"available_sf": round(available_budget, 2), "planned_cost_sf": round(total_cost, 2), "cash_buffer_sf": round(cash_buffer, 2), "remaining_sf": round(available_budget - total_cost, 2)},
        "feasible": not violations,
        "violations": violations,
        "scenarios": {"low": scenario(0.65), "base": base_case, "high": scenario(1.25)},
        "recommended_sequence": sequence,
        "confidence_change": round(sum(item.confidence_delta for item in impacts), 2),
        "assumptions": ["השפעות נמוך/בסיס/גבוה נגזרות מאותה פעולה ומטווח תגובה, לא מהאלגוריתם הרשמי.", "סימולציה אינה משנה נתוני אמת עד לאישור."],
    }

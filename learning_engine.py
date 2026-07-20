from __future__ import annotations

from statistics import mean
from typing import Any


FORECAST_METRICS = {
    "revenue_sf": {"label": "הכנסות", "weight": 0.20, "driver": "demand"},
    "gross_profit_sf": {"label": "רווח גולמי", "weight": 0.15, "driver": "margin"},
    "net_profit_sf": {"label": "רווח נקי", "weight": 0.20, "driver": "profitability"},
    "ending_cash_sf": {"label": "מזומן סופי", "weight": 0.20, "driver": "liquidity"},
    "units_sold": {"label": "יחידות שנמכרו", "weight": 0.10, "driver": "demand"},
    "actual_production": {"label": "ייצור בפועל", "weight": 0.05, "driver": "operations"},
    "ending_inventory": {"label": "מלאי סופי", "weight": 0.05, "driver": "inventory"},
    "market_share": {"label": "נתח שוק", "weight": 0.05, "driver": "market"},
}


CALIBRATION_KEYS = {
    "revenue_sf": "revenue_level_factor",
    "gross_profit_sf": "gross_profit_level_factor",
    "net_profit_sf": "net_profit_level_factor",
    "ending_cash_sf": "cash_level_factor",
    "units_sold": "demand_level_factor",
    "actual_production": "production_level_factor",
    "ending_inventory": "inventory_level_factor",
    "market_share": "market_share_level_factor",
}


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _quarter_number(value: str) -> int:
    try:
        return int(str(value).upper().replace("Q", ""))
    except (TypeError, ValueError):
        return 0


def _slope(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    xs = list(range(len(values)))
    x_mean = mean(xs)
    y_mean = mean(values)
    denominator = sum((x - x_mean) ** 2 for x in xs)
    if not denominator:
        return 0.0
    return sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, values)) / denominator


def _metric_range(base: float, history: list[float], minimum: float | None = None) -> dict[str, float]:
    changes = [history[index] - history[index - 1] for index in range(1, len(history))]
    volatility = mean(abs(value) for value in changes) if changes else abs(base) * 0.12
    width = max(abs(base) * (0.08 if len(history) >= 3 else 0.16), volatility * 0.75)
    low = base - width
    high = base + width
    if minimum is not None:
        low = max(minimum, low)
        high = max(minimum, high)
        base = max(minimum, base)
    return {"low": round(low, 2), "base": round(base, 2), "high": round(high, 2)}


def _latest_approved_factors(calibrations: list[dict[str, Any]]) -> dict[str, float]:
    result: dict[str, float] = {}
    rows = sorted(calibrations, key=lambda row: str(row.get("approved_at") or row.get("updated_at") or row.get("created_at") or ""))
    for row in rows:
        if row.get("status") != "approved":
            continue
        key = str(row.get("parameter_key") or "")
        if key:
            result[key] = max(0.5, min(1.5, _number(row.get("proposed_value"), 1.0)))
    return result


def aggregate_actual_metrics(
    quarter: str,
    finance_rows: list[dict[str, Any]],
    operations: list[dict[str, Any]],
) -> dict[str, float | None]:
    finance = next((row for row in finance_rows if str(row.get("quarter")) == quarter), {})
    ops = [row for row in operations if str(row.get("quarter")) == quarter]
    market_shares = [_number(row.get("actual_market_share")) for row in ops if row.get("actual_market_share") not in (None, "")]
    return {
        "revenue_sf": _number(finance.get("revenue_sf")) if finance else None,
        "gross_profit_sf": _number(finance.get("gross_profit_sf")) if finance else None,
        "net_profit_sf": _number(finance.get("net_profit_sf")) if finance else None,
        "ending_cash_sf": _number(finance.get("ending_cash_sf")) if finance else None,
        "units_sold": round(sum(_number(row.get("actual_sales")) for row in ops), 2) if ops else None,
        "actual_production": round(sum(_number(row.get("actual_production")) for row in ops), 2) if ops else None,
        "ending_inventory": round(sum(_number(row.get("ending_inventory")) for row in ops), 2) if ops else None,
        "market_share": round(mean(market_shares), 4) if market_shares else None,
    }


def build_next_quarter_forecast(
    target_quarter: str,
    finance_rows: list[dict[str, Any]],
    operations: list[dict[str, Any]],
    calibrations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    target_number = _quarter_number(target_quarter)
    source_number = max(0, target_number - 1)
    source_quarter = f"Q{source_number}" if source_number else ""
    eligible_finance = sorted(
        [row for row in finance_rows if 0 < _quarter_number(str(row.get("quarter"))) <= source_number],
        key=lambda row: _quarter_number(str(row.get("quarter"))),
    )
    eligible_operations = [row for row in operations if 0 < _quarter_number(str(row.get("quarter"))) <= source_number]
    factors = _latest_approved_factors(calibrations or [])
    metrics: dict[str, dict[str, float] | None] = {}

    for field in ("revenue_sf", "gross_profit_sf", "net_profit_sf", "ending_cash_sf"):
        values = [_number(row.get(field)) for row in eligible_finance]
        if not values:
            metrics[field] = None
            continue
        base = values[-1] + _slope(values)
        base *= factors.get(CALIBRATION_KEYS[field], 1.0)
        metrics[field] = _metric_range(base, values, 0.0 if field in {"revenue_sf", "ending_cash_sf"} else None)

    operation_history: dict[str, list[float]] = {key: [] for key in ("units_sold", "actual_production", "ending_inventory", "market_share")}
    for q_number in range(1, source_number + 1):
        quarter_rows = [row for row in eligible_operations if _quarter_number(str(row.get("quarter"))) == q_number]
        if not quarter_rows:
            continue
        operation_history["units_sold"].append(sum(_number(row.get("actual_sales")) for row in quarter_rows))
        operation_history["actual_production"].append(sum(_number(row.get("actual_production")) for row in quarter_rows))
        operation_history["ending_inventory"].append(sum(_number(row.get("ending_inventory")) for row in quarter_rows))
        shares = [_number(row.get("actual_market_share")) for row in quarter_rows if row.get("actual_market_share") not in (None, "")]
        if shares:
            operation_history["market_share"].append(mean(shares))

    for field, values in operation_history.items():
        if not values:
            metrics[field] = None
            continue
        base = (values[-1] + _slope(values)) * factors.get(CALIBRATION_KEYS[field], 1.0)
        metrics[field] = _metric_range(base, values, 0.0)

    available = sum(1 for value in metrics.values() if value is not None)
    observations = len(eligible_finance)
    confidence = "high" if observations >= 3 and available >= 6 else "medium" if observations >= 2 else "low"
    return {
        "source_actual_quarter": source_quarter,
        "target_quarter": target_quarter,
        "metrics": metrics,
        "confidence": confidence,
        "coverage": round(available / len(FORECAST_METRICS), 3),
        "approved_calibrations": factors,
        "method": "trend-plus-approved-calibration-v1",
        "warnings": [] if available >= 6 else ["חסרים Actuals לחלק מהמדדים; הטווח הורחב והוודאות נמוכה יותר."],
    }


def evaluate_forecast(
    forecast: dict[str, Any],
    actual_metrics: dict[str, float | None],
    prior_evaluations: int = 0,
) -> dict[str, Any]:
    forecast_result = forecast.get("result") or {}
    expected = forecast_result.get("q_plus_1") or forecast_result.get("next_quarter") or {}
    predicted_metrics = expected.get("metrics") or {}
    errors: dict[str, Any] = {}
    weighted_error = 0.0
    weight_used = 0.0

    for key, definition in FORECAST_METRICS.items():
        forecast_range = predicted_metrics.get(key)
        actual = actual_metrics.get(key)
        if not forecast_range or actual is None:
            continue
        base = _number(forecast_range.get("base"))
        absolute_error = _number(actual) - base
        percentage_error = absolute_error / abs(base) if base else None
        low = _number(forecast_range.get("low"), base)
        high = _number(forecast_range.get("high"), base)
        within_range = low <= _number(actual) <= high
        errors[key] = {
            "label": definition["label"],
            "forecast": round(base, 2),
            "range": {"low": round(low, 2), "high": round(high, 2)},
            "actual": round(_number(actual), 2),
            "absolute_error": round(absolute_error, 2),
            "percentage_error": round(percentage_error, 4) if percentage_error is not None else None,
            "within_range": within_range,
            "direction": "above" if absolute_error > 0 else "below" if absolute_error < 0 else "on_target",
            "driver": definition["driver"],
        }
        if percentage_error is not None:
            weight = _number(definition["weight"])
            weighted_error += min(abs(percentage_error), 2.0) * weight
            weight_used += weight

    wmape = weighted_error / weight_used if weight_used else None
    accuracy_score = max(0.0, 100.0 * (1.0 - min(wmape or 1.0, 1.0))) if errors else None
    within_count = sum(1 for row in errors.values() if row.get("within_range"))
    drivers = _diagnose_drivers(errors)
    calibration_proposals = _calibration_proposals(errors, prior_evaluations)
    return {
        "forecast_id": forecast.get("id"),
        "source_actual_quarter": forecast.get("source_actual_quarter") or expected.get("source_actual_quarter"),
        "target_quarter": forecast.get("target_quarter") or expected.get("target_quarter") or forecast.get("quarter"),
        "metric_errors": errors,
        "summary": {
            "metrics_evaluated": len(errors),
            "within_range": within_count,
            "within_range_ratio": round(within_count / len(errors), 3) if errors else None,
            "weighted_absolute_percentage_error": round(wmape, 4) if wmape is not None else None,
            "accuracy_score": round(accuracy_score, 1) if accuracy_score is not None else None,
        },
        "driver_analysis": drivers,
        "calibration_proposals": calibration_proposals,
        "status": "evaluated" if errors else "insufficient_actuals",
    }


def _diagnose_drivers(errors: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    revenue = errors.get("revenue_sf", {})
    units = errors.get("units_sold", {})
    gross = errors.get("gross_profit_sf", {})
    profit = errors.get("net_profit_sf", {})
    cash = errors.get("ending_cash_sf", {})
    inventory = errors.get("ending_inventory", {})

    if revenue and units and revenue.get("direction") == units.get("direction") and revenue.get("direction") != "on_target":
        result.append({
            "driver": "demand",
            "severity": "high" if abs(_number(units.get("percentage_error"))) >= 0.15 else "medium",
            "finding": "סטיית ההכנסות נעה יחד עם סטיית הכמות שנמכרה; הביקוש הוא הסבר מרכזי.",
            "evidence": ["revenue_sf", "units_sold"],
        })
    if revenue and gross:
        forecast_margin = _number(gross.get("forecast")) / _number(revenue.get("forecast"), 1.0)
        actual_margin = _number(gross.get("actual")) / _number(revenue.get("actual"), 1.0)
        if abs(actual_margin - forecast_margin) >= 0.03:
            result.append({
                "driver": "margin",
                "severity": "high" if actual_margin < forecast_margin - 0.05 else "medium",
                "finding": f"המרווח הגולמי בפועל ({actual_margin:.1%}) שונה מהתחזית ({forecast_margin:.1%}); בדקו מחיר, עלות ותמהיל.",
                "evidence": ["revenue_sf", "gross_profit_sf"],
            })
    if profit and gross and profit.get("direction") != gross.get("direction"):
        result.append({
            "driver": "operating_costs",
            "severity": "medium",
            "finding": "הרווח הנקי והרווח הגולמי סטו בכיוונים שונים; הוצאות תפעול, מימון או מס הן חשודות מרכזיות.",
            "evidence": ["gross_profit_sf", "net_profit_sf"],
        })
    if cash and profit and abs(_number(cash.get("percentage_error"))) > abs(_number(profit.get("percentage_error"))) + 0.1:
        result.append({
            "driver": "working_capital",
            "severity": "high",
            "finding": "סטיית המזומן גדולה משמעותית מסטיית הרווח; בדקו חייבים, זכאים, מלאי, השקעות והעברות בין אזורים.",
            "evidence": ["ending_cash_sf", "net_profit_sf"],
        })
    if inventory and abs(_number(inventory.get("percentage_error"))) >= 0.15:
        result.append({
            "driver": "inventory",
            "severity": "high" if inventory.get("direction") == "above" else "medium",
            "finding": "המלאי בפועל מחוץ לטווח התחזית; נדרש לכייל יחד ביקוש, ייצור ותמחור.",
            "evidence": ["ending_inventory", "units_sold", "actual_production"],
        })
    if not result and errors:
        result.append({
            "driver": "model_fit",
            "severity": "low",
            "finding": "לא זוהה driver יחיד דומיננטי; רוב הסטיות קטנות או מפוזרות בין המדדים.",
            "evidence": list(errors),
        })
    return result


def _calibration_proposals(errors: dict[str, Any], prior_evaluations: int) -> list[dict[str, Any]]:
    confidence = "high" if prior_evaluations >= 3 else "medium" if prior_evaluations >= 1 else "low"
    proposals: list[dict[str, Any]] = []
    for metric_key, row in errors.items():
        percentage_error = row.get("percentage_error")
        forecast = _number(row.get("forecast"))
        actual = _number(row.get("actual"))
        if percentage_error is None or not forecast or abs(_number(percentage_error)) < 0.05:
            continue
        factor = max(0.75, min(1.25, actual / forecast))
        proposals.append({
            "parameter_key": CALIBRATION_KEYS[metric_key],
            "metric_key": metric_key,
            "previous_value": 1.0,
            "proposed_value": round(factor, 4),
            "confidence": confidence,
            "status": "draft",
            "reason": f"תחזית {row['label']} הייתה {abs(_number(percentage_error)):.1%} {'נמוכה' if _number(percentage_error) > 0 else 'גבוהה'} מה-Actual.",
            "evidence": {"forecast": forecast, "actual": actual, "percentage_error": percentage_error},
        })
    return proposals

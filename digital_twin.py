from __future__ import annotations

import copy
from collections import defaultdict
from typing import Any


QUARTERS = tuple(f"Q{index}" for index in range(1, 10))
COLLECTION_PROFILE = {
    "USA": (0.40, 0.60, 0.00),
    "US": (0.40, 0.60, 0.00),
    "Europe": (0.50, 0.20, 0.30),
    "EU": (0.50, 0.20, 0.30),
    "Brazil": (0.30, 0.30, 0.40),
    "Liechtenstein": (1.00, 0.00, 0.00),
}


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value if value not in (None, "") else default)
    except (TypeError, ValueError):
        return float(default)


def _quarter_number(value: str) -> int:
    try:
        return int(str(value).upper().replace("Q", ""))
    except (TypeError, ValueError):
        return 0


def _next_quarter(value: str, offset: int = 1) -> str:
    return f"Q{min(9, max(1, _quarter_number(value) + offset))}"


def _round_state(state: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(state)
    for group in ("consolidated", "technology"):
        for key, value in result.get(group, {}).items():
            if isinstance(value, float):
                result[group][key] = round(value, 2)
    for collection in ("areas", "segments"):
        for row in result.get(collection, []):
            for key, value in row.items():
                if isinstance(value, float):
                    row[key] = round(value, 2)
    return result


def build_digital_twin_state(
    planning_quarter: str,
    financial: dict[str, Any],
    operations: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build an immutable planning baseline from approved Actuals only."""
    consolidated = financial.get("consolidated", {}) or {}
    data_as_of = str(financial.get("data_as_of") or "")
    segments: list[dict[str, Any]] = []
    for row in operations:
        segments.append(
            {
                "key": "|".join(
                    str(row.get(field) or "")
                    for field in ("area", "product", "model", "grade")
                ),
                "area": row.get("area", ""),
                "product": row.get("product", ""),
                "model": row.get("model", ""),
                "grade": int(_number(row.get("grade"))),
                "plants": _number(row.get("plants")),
                "capacity_units": _number(row.get("plant_capacity")),
                "inventory_units": _number(row.get("ending_inventory")),
                "last_production_units": _number(row.get("actual_production")),
                "last_sales_units": _number(row.get("actual_sales")),
                "price_lc": _number(row.get("actual_price_lc")),
                "market_share": _number(row.get("actual_market_share")),
                "variable_cost_lc": _number(row.get("variable_cost_lc")),
                "fixed_cost_lc": _number(row.get("fixed_cost_lc")),
                "advertising_lc": _number(row.get("advertising_lc")),
                "sales_channel": row.get("channel", ""),
                "fx_to_sf": _number(row.get("fx_to_sf"), 1.0),
            }
        )
    max_x = max((int(row["grade"]) for row in segments if row["product"] == "X"), default=0)
    max_y = max((int(row["grade"]) for row in segments if row["product"] == "Y"), default=0)
    areas = []
    for row in financial.get("areas", []) or []:
        areas.append(
            {
                "area": row.get("area", ""),
                "currency": row.get("currency", ""),
                "fx_to_sf": _number(row.get("fx_to_sf"), 1.0),
                "cash_sf": _number(row.get("ending_cash_sf")),
                "debt_sf": _number(row.get("debt_sf")),
                "ar_sf": _number(row.get("ar_sf")),
                "ap_sf": _number(row.get("ap_sf")),
                "inventory_value_sf": _number(row.get("inventory_value_sf")),
                "current_assets_sf": _number(row.get("current_assets_sf")),
                "current_liabilities_sf": _number(row.get("current_liabilities_sf")),
                "equity_sf": _number(row.get("equity_sf")),
                "commitments_sf": _number(row.get("capex_commitments_sf")),
            }
        )
    return _round_state(
        {
            "twin_version": "1.0",
            "as_of_quarter": data_as_of or None,
            "planning_quarter": planning_quarter,
            "source_type": "approved_actual",
            "locked_actual": True,
            "consolidated": {
                "revenue_sf": _number(consolidated.get("revenue_sf")),
                "gross_profit_sf": _number(consolidated.get("gross_profit_sf")),
                "net_profit_sf": _number(consolidated.get("net_profit_sf")),
                "cash_sf": _number(consolidated.get("ending_cash_sf")),
                "debt_sf": _number(consolidated.get("debt_sf")),
                "ar_sf": _number(consolidated.get("ar_sf")),
                "ap_sf": _number(consolidated.get("ap_sf")),
                "inventory_value_sf": _number(consolidated.get("inventory_value_sf")),
                "equity_sf": _number(consolidated.get("equity_sf")),
                "working_capital_sf": _number(consolidated.get("working_capital_sf")),
                "operating_cash_flow_sf": _number(consolidated.get("operating_cash_flow_sf")),
                "commitments_sf": _number(consolidated.get("capex_commitments_sf")),
                "available_budget_sf": _number(consolidated.get("available_budget_sf")),
                "cash_buffer_sf": _number(consolidated.get("cash_buffer_sf")),
            },
            "areas": areas,
            "segments": segments,
            "technology": {
                "max_x_grade": max_x,
                "max_y_grade": max_y,
                "rd_x_sf": 0.0,
                "rd_y_sf": 0.0,
            },
            "sales_offices": {},
            "pipeline": [],
            "sources": list(financial.get("sources", [])),
            "confidence": "high" if financial.get("actual_coverage", {}).get("complete") else "medium",
        }
    )


def _area_row(state: dict[str, Any], area: str) -> dict[str, Any] | None:
    aliases = {"US": "USA", "EU": "Europe", "Home Office": "Liechtenstein"}
    canonical = aliases.get(area, area)
    return next(
        (row for row in state.get("areas", []) if aliases.get(str(row.get("area")), row.get("area")) == canonical),
        None,
    )


def _segments(state: dict[str, Any], action: dict[str, Any]) -> list[dict[str, Any]]:
    matches = []
    for row in state.get("segments", []):
        if action.get("area") and row.get("area") != action.get("area"):
            continue
        if action.get("product") and row.get("product") != action.get("product"):
            continue
        if action.get("model") and row.get("model") != action.get("model"):
            continue
        if action.get("grade") not in (None, "") and int(_number(row.get("grade"))) != int(_number(action.get("grade"))):
            continue
        matches.append(row)
    return matches


def _action_type(action: dict[str, Any]) -> str:
    value = str(action.get("type") or "").strip().lower()
    code = str(action.get("code") or "").strip().upper()
    code_types = {
        "A1-1": "price_advertising", "A1-2": "price_advertising", "A1-3": "sales_offices",
        "A2-1": "plant_construction", "A2-3": "production", "A2-4": "production",
        "A3-1": "money_transfer", "A3-2": "invest_borrow", "A3-3": "currency_conversion",
        "A4": "component_transfer", "H1-1": "rd", "H1-2": "market_research",
        "H2": "home_office_finance", "H4": "intercompany_loan", "H5": "grade_license",
        "H6": "industrial_sale", "W1": "services_payment", "W2": "factory_sale",
        "W3": "local_currency_exchange",
    }
    return value or code_types.get(code, "generic")


def project_digital_twin(
    planning_quarter: str,
    baseline_state: dict[str, Any],
    actions: list[dict[str, Any]],
    impacts: list[dict[str, Any]],
    *,
    multiplier: float = 1.0,
    through_quarter: str = "Q9",
) -> dict[str, Any]:
    """Project transparent state transitions without mutating Actuals."""
    start = _quarter_number(planning_quarter)
    end = max(start, _quarter_number(through_quarter))
    schedule: dict[int, list[dict[str, Any]]] = defaultdict(list)
    assumptions = [
        "התחזית היא Digital Twin ניהולי ולא האלגוריתם הרשמי של המשחק.",
        "השפעות פעולה נעות לפי תזמון ה-Rulebook; רכיבים ללא פרמטר רשמי מסומנים כהנחה.",
        "גביית מכירות מדומה לפי פרופיל האשראי האזורי ב-Data Log.",
    ]

    def add_event(qn: int, kind: str, action_index: int, **payload: Any) -> None:
        if qn <= end:
            schedule[max(start, qn)].append({"kind": kind, "action_index": action_index, **payload})

    for index, action in enumerate(actions):
        impact = impacts[index] if index < len(impacts) else {}
        kind = _action_type(action)
        cost = max(0.0, _number(impact.get("cost_sf")))
        add_event(start, "cash_cost", index, amount_sf=cost)
        cash_delta = _number(impact.get("cash_delta_sf")) * multiplier
        debt_delta = _number(impact.get("debt_delta_sf")) * multiplier
        if cash_delta or debt_delta:
            add_event(start, "funding", index, cash_delta_sf=cash_delta, debt_delta_sf=debt_delta)
        effect_q = start + (1 if kind in {"production", "plant_construction", "grade_license", "component_transfer"} else 0)
        if kind == "component_transfer" and str(action.get("shipping_mode") or action.get("transport") or "surface").lower() in {"air", "airfreight"}:
            effect_q = start
        add_event(
            effect_q,
            "economic_effect",
            index,
            revenue_delta_sf=_number(impact.get("revenue_delta_sf")) * multiplier,
            profit_delta_sf=_number(impact.get("profit_delta_sf")) * multiplier,
            area=str(action.get("area") or ""),
        )
        if kind == "plant_construction":
            add_event(start + 1, "capacity_online", index, capacity_units=_number(impact.get("capacity_delta_units")), plants=_number(action.get("plant_count"), 1))
        elif kind == "production":
            units = max(0.0, _number(action.get("units")))
            sell_through = min(1.0, max(0.0, _number(action.get("sell_through"), 0.75)))
            add_event(start, "inventory_produced", index, units=units)
            add_event(start + 1, "inventory_sold", index, units=units * sell_through)
        elif kind == "rd":
            add_event(start, "rd_investment", index, amount_sf=max(cost, _number(action.get("amount_sf"))), product=str(action.get("product") or ""))
            if action.get("new_grade") not in (None, ""):
                add_event(start + 1, "technology_available", index, product=str(action.get("product") or ""), grade=int(_number(action.get("new_grade"))))
        elif kind == "grade_license":
            add_event(start + 1, "technology_available", index, product=str(action.get("product") or ""), grade=int(_number(action.get("grade"))))
        elif kind == "sales_offices":
            add_event(start, "sales_offices", index, delta=_number(action.get("office_delta")))
        elif kind == "money_transfer":
            add_event(
                start,
                "money_transfer",
                index,
                amount_sf=max(
                    0.0,
                    _number(action.get("net_amount_sf"), _number(action.get("amount_sf"))),
                ),
                source_area=str(action.get("source_area") or action.get("area") or ""),
                target_area=str(action.get("target_area") or ""),
            )
        elif kind == "factory_sale":
            add_event(start, "factory_sale", index, plants=max(0.0, _number(action.get("plant_count"), 1)))
        elif kind == "component_transfer":
            add_event(effect_q, "component_transfer", index, units=max(0.0, _number(action.get("units"))))
        elif kind == "industrial_sale":
            add_event(start, "inventory_sold", index, units=max(0.0, _number(action.get("units"))))
        elif kind == "market_research":
            add_event(start + 1, "confidence_update", index, delta=_number(impact.get("confidence_delta")))

    current = copy.deepcopy(baseline_state)
    current["locked_actual"] = False
    current["source_type"] = "scenario_projection"
    timeline: list[dict[str, Any]] = []
    transition_log: list[dict[str, Any]] = []
    pending_ar: dict[int, float] = defaultdict(float)

    for qn in range(start, end + 1):
        quarter = f"Q{qn}"
        quarter_events: list[dict[str, Any]] = []
        metrics = current["consolidated"]
        metrics["revenue_sf"] = _number(baseline_state.get("consolidated", {}).get("revenue_sf"))
        metrics["net_profit_sf"] = _number(baseline_state.get("consolidated", {}).get("net_profit_sf"))
        if pending_ar.get(qn):
            amount = pending_ar[qn]
            metrics["cash_sf"] += amount
            metrics["ar_sf"] = max(0.0, metrics["ar_sf"] - amount)
            quarter_events.append({"kind": "receivables_collected", "amount_sf": round(amount, 2)})
        for event in schedule.get(qn, []):
            action = actions[event["action_index"]]
            kind = event["kind"]
            area = str(action.get("area") or "")
            area_row = _area_row(current, area)
            if kind == "cash_cost":
                amount = _number(event.get("amount_sf"))
                metrics["cash_sf"] -= amount
                if area_row:
                    area_row["cash_sf"] -= amount
            elif kind == "funding":
                metrics["cash_sf"] += _number(event.get("cash_delta_sf"))
                metrics["debt_sf"] += _number(event.get("debt_delta_sf"))
                if area_row:
                    area_row["cash_sf"] += _number(event.get("cash_delta_sf"))
                    area_row["debt_sf"] += _number(event.get("debt_delta_sf"))
            elif kind == "economic_effect":
                revenue = _number(event.get("revenue_delta_sf"))
                profit = _number(event.get("profit_delta_sf"))
                metrics["revenue_sf"] += revenue
                metrics["net_profit_sf"] += profit
                collection = COLLECTION_PROFILE.get(area, (0.35, 0.45, 0.20))
                immediate = revenue * collection[0]
                metrics["cash_sf"] += immediate
                metrics["ar_sf"] += revenue - immediate
                pending_ar[qn + 1] += revenue * collection[1]
                pending_ar[qn + 2] += revenue * collection[2]
                metrics["equity_sf"] += profit
            elif kind in {"inventory_produced", "inventory_sold"}:
                sign = 1 if kind == "inventory_produced" else -1
                for row in _segments(current, action):
                    row["inventory_units"] = max(0.0, _number(row.get("inventory_units")) + sign * _number(event.get("units")))
            elif kind == "capacity_online":
                matches = _segments(current, action)
                if matches:
                    matches[0]["capacity_units"] += _number(event.get("capacity_units"))
                    matches[0]["plants"] += _number(event.get("plants"))
            elif kind == "factory_sale":
                matches = _segments(current, action)
                if matches:
                    sold = min(matches[0]["plants"], _number(event.get("plants")))
                    per_plant = matches[0]["capacity_units"] / max(matches[0]["plants"], 1)
                    matches[0]["plants"] -= sold
                    matches[0]["capacity_units"] = max(0.0, matches[0]["capacity_units"] - sold * per_plant)
            elif kind == "rd_investment":
                product = str(event.get("product") or "").upper()
                if product in {"X", "Y"}:
                    current["technology"][f"rd_{product.lower()}_sf"] += _number(event.get("amount_sf"))
            elif kind == "technology_available":
                product = str(event.get("product") or "").upper()
                if product in {"X", "Y"}:
                    key = f"max_{product.lower()}_grade"
                    current["technology"][key] = max(int(current["technology"].get(key, 0)), int(_number(event.get("grade"))))
            elif kind == "sales_offices":
                current["sales_offices"][area or "company"] = _number(current["sales_offices"].get(area or "company")) + _number(event.get("delta"))
            elif kind == "money_transfer":
                amount = _number(event.get("amount_sf"))
                source = _area_row(current, str(event.get("source_area") or area))
                target = _area_row(current, str(event.get("target_area") or ""))
                if source:
                    source["cash_sf"] -= amount
                if target:
                    target["cash_sf"] += amount
            elif kind == "component_transfer":
                targets = _segments(current, action)
                if targets:
                    targets[0]["inventory_units"] += _number(event.get("units"))
            current["pipeline"] = [row for row in current.get("pipeline", []) if row.get("effective_quarter") != quarter]
            enriched = {**event, "quarter": quarter, "code": action.get("code"), "title": action.get("title") or action.get("type")}
            quarter_events.append(enriched)
            transition_log.append(enriched)
        metrics["working_capital_sf"] = metrics["ar_sf"] + metrics["inventory_value_sf"] - metrics["ap_sf"]
        metrics["available_budget_sf"] = max(0.0, metrics["cash_sf"] - metrics["commitments_sf"] - metrics["cash_buffer_sf"])
        current["as_of_quarter"] = quarter
        timeline.append({"quarter": quarter, "state": _round_state(current), "events": quarter_events})

    final_state = timeline[-1]["state"] if timeline else _round_state(current)
    baseline = baseline_state.get("consolidated", {})
    final = final_state.get("consolidated", {})
    return {
        "twin_version": "1.0",
        "planning_quarter": planning_quarter,
        "through_quarter": through_quarter,
        "baseline_as_of": baseline_state.get("as_of_quarter"),
        "multiplier": multiplier,
        "timeline": timeline,
        "transition_log": transition_log,
        "summary": {
            "ending_cash_sf": round(_number(final.get("cash_sf")), 2),
            "ending_debt_sf": round(_number(final.get("debt_sf")), 2),
            "ending_ar_sf": round(_number(final.get("ar_sf")), 2),
            "ending_inventory_units": round(sum(_number(row.get("inventory_units")) for row in final_state.get("segments", [])), 2),
            "ending_capacity_units": round(sum(_number(row.get("capacity_units")) for row in final_state.get("segments", [])), 2),
            "max_x_grade": final_state.get("technology", {}).get("max_x_grade", 0),
            "max_y_grade": final_state.get("technology", {}).get("max_y_grade", 0),
            "cash_change_sf": round(_number(final.get("cash_sf")) - _number(baseline.get("cash_sf")), 2),
            "debt_change_sf": round(_number(final.get("debt_sf")) - _number(baseline.get("debt_sf")), 2),
        },
        "assumptions": assumptions,
        "actuals_mutated": False,
    }

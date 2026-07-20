from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable


MATERIAL_ACTION_FIELDS = {
    "price_lc",
    "current_price_lc",
    "change_pct",
    "elasticity",
    "amount_sf",
    "cost_sf",
    "capacity_units",
    "units",
    "net_amount_sf",
    "gross_source_amount_sf",
    "source_amount_lc",
}


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value if value not in (None, "") else default)
    except (TypeError, ValueError):
        return default


def _quarter_number(value: Any) -> int:
    text = str(value or "Q0").upper().strip()
    try:
        return int(text[1:]) if text.startswith("Q") else int(text)
    except (TypeError, ValueError):
        return 0


def _claim_id(recommendation_key: str, metric: str, value: Any) -> str:
    raw = json.dumps([recommendation_key, metric, value], ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:18]


def _source(
    source_type: str,
    source_id: str,
    label: str,
    *,
    quarter: str = "",
    area: str = "",
    field: str = "",
    page: str = "",
) -> dict[str, Any]:
    return {
        "type": source_type,
        "id": source_id,
        "label": label,
        "quarter": quarter,
        "area": area,
        "field": field,
        "page": page,
    }


def _claim(
    recommendation_key: str,
    metric: str,
    label: str,
    value: Any,
    unit: str,
    claim_type: str,
    *,
    sources: list[dict[str, Any]] | None = None,
    formula: str = "",
    assumptions: list[str] | None = None,
    value_range: dict[str, Any] | None = None,
    confidence: str = "low",
    status: str = "blocked",
    gaps: list[str] | None = None,
    material: bool = True,
) -> dict[str, Any]:
    return {
        "claim_id": _claim_id(recommendation_key, metric, value),
        "metric": metric,
        "label": label,
        "value": value,
        "unit": unit,
        "claim_type": claim_type,
        "source_refs": sources or [],
        "formula": formula,
        "assumptions": assumptions or [],
        "range": value_range or {"low": value, "base": value, "high": value},
        "confidence": confidence,
        "status": status,
        "gaps": gaps or [],
        "material": material,
    }


def _latest_matching_operation(
    quarter: str,
    action: dict[str, Any],
    operations: Iterable[dict[str, Any]],
) -> dict[str, Any] | None:
    candidates = []
    for row in operations:
        if _quarter_number(row.get("quarter")) > _quarter_number(quarter):
            continue
        if action.get("area") and str(row.get("area") or "") != str(action.get("area")):
            continue
        if action.get("product") and str(row.get("product") or "") != str(action.get("product")):
            continue
        if action.get("model") and str(row.get("model") or "") != str(action.get("model")):
            continue
        candidates.append(row)
    return max(candidates, key=lambda row: _quarter_number(row.get("quarter")), default=None)


def _operation_source(row: dict[str, Any], field: str) -> dict[str, Any]:
    quarter = str(row.get("quarter") or "")
    area = str(row.get("area") or "")
    product = str(row.get("product") or "")
    model = str(row.get("model") or "")
    source_id = str(row.get("source") or f"operations:{quarter}:{area}:{product}:{model}")
    return _source(
        "Actual",
        source_id,
        f"Actual {quarter} · {area} · {product} {model}".strip(),
        quarter=quarter,
        area=area,
        field=field,
    )


def _finance_source(quarter: str, field: str, *, area: str = "") -> dict[str, Any]:
    source_id = f"finance_by_area:{quarter}:{area}" if area else f"quarter_finance:{quarter}"
    label = f"Actual {quarter} · {area}" if area else f"Actual {quarter} · מאוחד"
    return _source("Actual", source_id, label, quarter=quarter, area=area, field=field)


def _rule_sources(applied_rules: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for row in applied_rules:
        rule_id = str(row.get("rule_id") or "")
        source_id = str(row.get("source_id") or "")
        page = str(row.get("page") or row.get("source_page") or "")
        if not (rule_id or source_id):
            continue
        result.append(
            _source(
                "Rule",
                source_id or rule_id,
                f"{rule_id or 'Rule'} · {source_id}" + (f" · עמ׳ {page}" if page else ""),
                page=page,
                field=rule_id,
            )
        )
    return result


def _research_sources(research_results: Iterable[dict[str, Any]], action: dict[str, Any]) -> list[dict[str, Any]]:
    area = str(action.get("area") or "")
    product = str(action.get("product") or "")
    result = []
    for row in research_results:
        row_area = str(row.get("area") or "")
        row_product = str(row.get("product") or "")
        if area and row_area and row_area != area:
            continue
        if product and row_product and row_product != product:
            continue
        study_id = int(_num(row.get("study_id")))
        if not study_id:
            continue
        quarter = str(row.get("quarter") or "")
        source_id = str(row.get("source_upload_id") or f"research:{quarter}:MR{study_id}")
        result.append(
            _source(
                "Market Research",
                source_id,
                str(row.get("source_label") or f"{quarter} · MR{study_id}"),
                quarter=quarter,
                area=row_area,
                field=f"MR{study_id}",
            )
        )
    return result


def _scenario_range(simulation: dict[str, Any], metric: str, fallback: Any) -> dict[str, Any]:
    values = simulation.get("scenarios", {}) if isinstance(simulation, dict) else {}
    return {
        "low": (values.get("downside") or {}).get(metric, fallback),
        "base": (values.get("base") or {}).get(metric, fallback),
        "high": (values.get("upside") or {}).get(metric, fallback),
    }


def audit_recommendation_numbers(
    quarter: str,
    recommendation: dict[str, Any],
    *,
    operations: Iterable[dict[str, Any]],
    finance: dict[str, Any],
    area_finance: Iterable[dict[str, Any]] = (),
    research_results: Iterable[dict[str, Any]] = (),
    simulation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Audit every material number without pretending that an assumption is evidence."""
    simulation = simulation or {}
    action = dict(recommendation.get("action_template") or recommendation.get("action") or recommendation)
    key = str(recommendation.get("id") or recommendation.get("recommendation_key") or recommendation.get("title") or "recommendation")
    action_type = str(action.get("type") or "")
    claims: list[dict[str, Any]] = []
    contradictions: list[str] = []
    gaps: list[str] = []
    operation = _latest_matching_operation(quarter, action, operations)
    actual_quarter = str((operation or {}).get("quarter") or quarter)
    rules = _rule_sources(simulation.get("applied_rules", []))
    research = _research_sources(research_results, action)
    consolidated = finance.get("consolidated", {}) if isinstance(finance, dict) else {}

    if action_type == "price_change" or action.get("price_lc") not in (None, ""):
        actual_price = _num((operation or {}).get("actual_price_lc"))
        supplied_current = _num(action.get("current_price_lc"))
        if operation and actual_price > 0:
            claims.append(
                _claim(
                    key, "current_price_lc", "מחיר Actual נוכחי", supplied_current or actual_price, "LC",
                    "actual", sources=[_operation_source(operation, "actual_price_lc")], confidence="high", status="supported",
                )
            )
            if supplied_current > 0 and abs(supplied_current - actual_price) / actual_price > 0.01:
                contradictions.append(
                    f"המחיר הנוכחי בפעולה ({supplied_current:,.2f}) אינו תואם ל-Actual האחרון ({actual_price:,.2f})."
                )
        else:
            message = "חסר מחיר Actual מדויק לאותו אזור, מוצר ודגם."
            gaps.append(message)
            claims.append(_claim(key, "current_price_lc", "מחיר Actual נוכחי", supplied_current or None, "LC", "actual", gaps=[message]))

        change = _num(action.get("change_pct"))
        if action.get("change_pct") not in (None, ""):
            change_sources = research
            status = "conditional" if change_sources else "blocked"
            message = "שיעור השינוי הוא הנחת הנהלה; נדרש מחקר מחיר/ביקוש או החלטה מפורשת." if not change_sources else "שיעור השינוי עדיין הנחה, אך קיימת ראיית מחקר רלוונטית."
            if not change_sources:
                gaps.append(message)
            claims.append(
                _claim(
                    key, "change_pct", "שינוי מחיר מוצע", change, "%", "assumption",
                    sources=change_sources, assumptions=[message], confidence="medium" if change_sources else "low",
                    status=status, gaps=[] if change_sources else [message],
                )
            )
        target = action.get("price_lc")
        if target not in (None, ""):
            formula_ok = actual_price > 0 and action.get("change_pct") not in (None, "")
            expected = round(actual_price * (1 + change), 2) if formula_ok else None
            if expected is not None and abs(_num(target) - expected) > 0.02:
                contradictions.append(f"מחיר היעד {_num(target):,.2f} אינו שווה למחיר Actual × שינוי ({expected:,.2f}).")
            target_status = "supported" if formula_ok else "blocked"
            if formula_ok and not research:
                target_status = "conditional"
            claims.append(
                _claim(
                    key, "price_lc", "מחיר מומלץ להזנה", target, "LC", "derived",
                    sources=([_operation_source(operation, "actual_price_lc")] if operation and actual_price > 0 else []) + research,
                    formula="מחיר Actual × (1 + שיעור שינוי)", assumptions=["תגובת הביקוש תלויה באלסטיות שטרם אושרה"] if not research else [],
                    value_range={"low": round(_num(target) * 0.97, 2), "base": target, "high": round(_num(target) * 1.03, 2)},
                    confidence="medium" if formula_ok else "low", status=target_status,
                    gaps=[] if formula_ok else ["לא ניתן לשחזר את נוסחת מחיר היעד מנתוני Actual."],
                )
            )
        if action.get("elasticity") not in (None, ""):
            elasticity_status = "conditional" if research else "blocked"
            message = "אלסטיות המחיר אינה Actual ואינה חוק; יש לאמוד אותה מתצפיות או מחקר שוק."
            if not research:
                gaps.append(message)
            claims.append(
                _claim(
                    key, "elasticity", "אלסטיות ביקוש", action.get("elasticity"), "ratio", "assumption",
                    sources=research, assumptions=[message], confidence="low", status=elasticity_status,
                    gaps=[] if research else [message],
                )
            )

    if action_type == "rd" or action.get("code") == "H1-1":
        amount = _num(action.get("amount_sf"), _num(action.get("cost_sf")))
        budget = _num(consolidated.get("available_budget_sf"))
        sources = [_finance_source(quarter, "available_budget_sf")] + rules
        status = "supported" if amount > 0 and rules and amount <= budget else "conditional"
        local_gaps = []
        if not rules:
            local_gaps.append("חסר חוק/פרמטר מאושר שמסביר את מינימום או גובה השקעת המו״פ.")
        if amount > budget:
            contradictions.append(f"השקעת המו״פ ({amount:,.0f} SF) גבוהה מהתקציב הפנוי ({budget:,.0f} SF).")
            status = "blocked"
        claims.append(
            _claim(
                key, "amount_sf", "השקעת מו״פ", amount, "SF", "derived", sources=sources,
                formula="max(מינימום מו״פ מאושר, שיעור התקציב שהוגדר) ועד גובה התקציב הפנוי",
                assumptions=["שיעור הקצאת התקציב הוא החלטת הנהלה"], confidence="medium" if rules else "low",
                status=status, gaps=local_gaps,
            )
        )
        gaps.extend(local_gaps)

    if action_type == "capacity" or action.get("capacity_units") not in (None, ""):
        capacity = _num((operation or {}).get("plant_capacity"))
        production = _num((operation or {}).get("actual_production"))
        proposed = _num(action.get("capacity_units"), _num(action.get("units")))
        if operation and capacity > 0:
            claims.append(
                _claim(
                    key, "capacity_units", "תוספת קיבולת מוצעת", proposed, "units", "derived",
                    sources=[_operation_source(operation, "plant_capacity"), _operation_source(operation, "actual_production")] + rules,
                    formula="20% מהקיבולת האחרונה כאשר ניצולת Actual גבוהה מ-90%",
                    assumptions=["20% הוא גודל בדיקה ניהולי ולא אופטימום מוכח"],
                    value_range={"low": round(proposed * 0.5, 2), "base": proposed, "high": round(proposed * 1.5, 2)},
                    confidence="medium", status="conditional",
                    gaps=["נדרש MR24 או אומדן ביקוש/עלות מאושר לפני החלטת מפעל בלתי הפיכה."],
                )
            )
            gaps.append("נדרש MR24 או אומדן ביקוש/עלות מאושר לפני החלטת מפעל בלתי הפיכה.")
            if production > capacity * 1.01:
                contradictions.append("הייצור ב-Actual גבוה מהקיבולת הרשומה; יש לאמת את מיפוי הדוח.")
        else:
            message = "חסרים Actuals של קיבולת וייצור לאותו אזור ומוצר."
            gaps.append(message)
            claims.append(_claim(key, "capacity_units", "תוספת קיבולת מוצעת", proposed, "units", "derived", gaps=[message]))

    if action_type in {"money_transfer", "cash_transfer"} or action.get("net_amount_sf") not in (None, ""):
        source_area = str(action.get("source_area") or action.get("area") or "")
        source_row = max(
            (
                row for row in area_finance
                if str(row.get("area") or "") == source_area and _quarter_number(row.get("quarter")) <= _quarter_number(quarter)
            ),
            key=lambda row: _quarter_number(row.get("quarter")),
            default=None,
        )
        amount = _num(action.get("net_amount_sf"), _num(action.get("amount_sf")))
        gross = _num(action.get("gross_source_amount_sf"), amount + _num(action.get("cost_sf")))
        source_cash = _num((source_row or {}).get("cash_lc")) * max(_num((source_row or {}).get("fx_to_sf"), 1), 0.000001)
        if source_row:
            status = "supported" if gross <= source_cash else "blocked"
            claims.append(
                _claim(
                    key, "net_amount_sf", "העברת נזילות נטו", amount, "SF", "derived",
                    sources=[_finance_source(str(source_row.get("quarter") or quarter), "cash_lc", area=source_area)] + rules,
                    formula="פער נזילות ביעד, מגולם לעמלת מטבע ושומר רצבה באזור המקור",
                    confidence="high" if rules else "medium", status=status,
                    gaps=[] if rules else ["חסר מקור חוק מאושר לעמלת ההמרה/העברה."],
                )
            )
            if gross > source_cash:
                contradictions.append(f"סכום ההעברה ברוטו ({gross:,.0f} SF) גבוה מהמזומן באזור המקור ({source_cash:,.0f} SF).")
        else:
            message = f"חסר Actual מזומן לאזור המקור {source_area or 'שלא הוגדר'}."
            gaps.append(message)
            claims.append(_claim(key, "net_amount_sf", "העברת נזילות נטו", amount, "SF", "derived", gaps=[message]))

    if action_type == "market_research" or action.get("study_ids"):
        ids = [int(_num(value)) for value in action.get("study_ids", []) if _num(value) > 0]
        sources = research + rules
        status = "supported" if ids and rules else "conditional"
        local_gaps = [] if rules else ["יש לאמת את מספרי ועלויות המחקרים מול קטלוג המחקר המאושר."]
        claims.append(
            _claim(
                key, "study_ids", "מחקרי שוק מוצעים", ids, "MR", "parameter", sources=sources,
                formula="בחירה לפי החלטת המחיר/עלות/קיבולת הקרובה", confidence="medium", status=status,
                gaps=local_gaps,
            )
        )
        gaps.extend(local_gaps)

    impact = recommendation.get("economic_impact") or {}
    base_scenario = (simulation.get("scenarios") or {}).get("base", {})
    impact_metrics = (
        ("cost_sf", "עלות סל הפעולות", "SF", "planned_cost_sf"),
        ("profit_delta_sf", "השפעת רווח חזויה", "SF", "net_profit_sf"),
        ("cash_delta_sf", "השפעת מזומן חזויה", "SF", "ending_cash_sf"),
        ("q9_score_delta", "השפעה חזויה על ציון Q9", "points", "q9_score"),
    )
    for metric, label, unit, scenario_metric in impact_metrics:
        value = impact.get(metric)
        if value is None:
            continue
        source_refs = [_finance_source(quarter, "baseline")] + rules
        confidence = "medium" if base_scenario else "low"
        local_gaps = [] if base_scenario else ["חסר פלט תרחישים מלא לשחזור הטווח."
        ]
        claims.append(
            _claim(
                key, metric, label, value, unit, "forecast", sources=source_refs,
                formula="מודל תרחישים דטרמיניסטי: תוצאת הפעולה פחות מצב הבסיס",
                assumptions=["פונקציית הביקוש והציון הפנימי הן אומדן ניהולי"],
                value_range=_scenario_range(simulation, scenario_metric, value), confidence=confidence,
                status="conditional", gaps=local_gaps, material=False,
            )
        )

    if not claims:
        claims.append(
            _claim(
                key, "non_numeric_action", "פעולת בקרה ללא מספר מהותי", None, "", "qualitative",
                sources=rules, confidence="medium" if rules else "low",
                status="supported" if rules or action_type in {"strategy_review", "cash_protection"} else "conditional",
                material=False,
            )
        )

    if contradictions:
        status = "blocked"
    elif any(row["status"] == "blocked" and row.get("material", True) for row in claims):
        status = "blocked"
    elif any(row["status"] == "conditional" and row.get("material", True) for row in claims):
        status = "conditional"
    else:
        status = "pass"

    supported = sum(row["status"] == "supported" for row in claims)
    conditional = sum(row["status"] == "conditional" for row in claims)
    blocked = sum(row["status"] == "blocked" for row in claims)
    score = round(max(0.0, min(100.0, (supported + conditional * 0.45) / max(len(claims), 1) * 100)), 1)
    if contradictions:
        score = min(score, 20.0)
    unique_gaps = list(dict.fromkeys(gap for gap in gaps + [item for row in claims for item in row.get("gaps", [])] if gap))
    return {
        "recommendation_key": key,
        "status": status,
        "score": score,
        "claim_count": len(claims),
        "supported_claim_count": supported,
        "conditional_claim_count": conditional,
        "blocked_claim_count": blocked,
        "claims": claims,
        "gaps": unique_gaps,
        "contradictions": contradictions,
        "summary": {
            "pass": "כל המספרים המהותיים ניתנים לשחזור ממקור מאושר.",
            "conditional": "קיימים מספרים המבוססים על הנחה או תחזית; יש לאשרם לפני הזנה.",
            "blocked": "אין להשתמש במספרים המוצעים עד השלמת הראיות או תיקון הסתירה.",
        }[status],
    }


def audit_decision_pack_numbers(
    quarter: str,
    actions: Iterable[dict[str, Any]],
    *,
    operations: Iterable[dict[str, Any]],
    finance: dict[str, Any],
    area_finance: Iterable[dict[str, Any]] = (),
    research_results: Iterable[dict[str, Any]] = (),
    simulation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    audits = []
    for index, action in enumerate(actions, start=1):
        audits.append(
            audit_recommendation_numbers(
                quarter,
                {"id": str(action.get("_recommendation_id") or action.get("id") or f"action-{index}"), "title": action.get("title", ""), "action_template": action},
                operations=operations,
                finance=finance,
                area_finance=area_finance,
                research_results=research_results,
                simulation=simulation,
            )
        )
    return build_evidence_gate_summary(audits)


def build_evidence_gate_summary(audits: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = list(audits)
    blocked = [row for row in rows if row.get("status") == "blocked"]
    conditional = [row for row in rows if row.get("status") == "conditional"]
    status = "blocked" if blocked else "conditional" if conditional else "pass"
    gaps = list(dict.fromkeys(gap for row in rows for gap in row.get("gaps", []) if gap))
    contradictions = list(dict.fromkeys(item for row in rows for item in row.get("contradictions", []) if item))
    return {
        "status": status,
        "score": round(sum(_num(row.get("score")) for row in rows) / max(len(rows), 1), 1) if rows else 100.0,
        "recommendation_count": len(rows),
        "passed_count": sum(row.get("status") == "pass" for row in rows),
        "conditional_count": len(conditional),
        "blocked_count": len(blocked),
        "gaps": gaps,
        "contradictions": contradictions,
        "recommendations": rows,
        "ready_for_decision_pack": bool(rows) and not blocked and not conditional,
        "summary": {
            "pass": "שער הראיות עבר: כל המספרים המהותיים ניתנים לשחזור.",
            "conditional": "נדרש אישור הנחות או מידע נוסף לפני נעילת המספרים.",
            "blocked": "חבילת ההחלטות חסומה בגלל מספר ללא בסיס או סתירה בנתונים.",
        }[status],
    }

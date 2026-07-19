from __future__ import annotations

from typing import Any


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value if value not in (None, "") else default)
    except (TypeError, ValueError):
        return default


def _quarter_number(value: str | None) -> int:
    text = str(value or "").upper()
    return int(text[1:]) if len(text) == 2 and text.startswith("Q") and text[1:].isdigit() else 0


def build_strategy_optimization(
    quarter: str,
    intelligence: dict[str, Any],
    scenario_results: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Create a rolling, evidence-bound strategy draft from approved actuals to Q9.

    The result is deliberately read-only: it never changes the approved strategy,
    actual results, or a scenario portfolio.
    """

    financial = intelligence.get("financial", {})
    consolidated = financial.get("consolidated", {})
    scorecard = intelligence.get("scorecard", {})
    forecast = intelligence.get("forecast_q9", {})
    strategy = intelligence.get("strategy_profile") or {}
    actual_as_of = str(financial.get("data_as_of") or "")
    actual_number = _quarter_number(actual_as_of)
    horizon = [f"Q{index}" for index in range(actual_number + 1, 10)] if actual_number else []
    next_quarter = horizon[0] if horizon else None
    has_strategy = bool(strategy.get("thesis") or strategy.get("goals") or strategy.get("constraints"))

    past_score = scorecard.get("past", {}).get("score")
    future_score = scorecard.get("future", {}).get("score")
    combined_score = scorecard.get("combined")
    forecast_score = forecast.get("score", {})
    past_metrics = scorecard.get("past", {}).get("metrics", {})
    future_metrics = scorecard.get("future", {}).get("metrics", {})

    metric_labels = {
        "net_profit": "רווח נקי",
        "ros": "ROS",
        "roi": "ROI",
        "roe": "ROE",
        "trend": "מגמה",
        "technology": "טכנולוגיה",
        "market_segments": "פלחי שוק",
        "share_capacity": "נתח שוק מול קיבולת",
        "reputation": "מוניטין",
        "partnerships": "שיתופי פעולה",
        "ethics": "אתיקה",
    }
    known_metrics: list[tuple[str, str, float]] = []
    for group, values in (("past", past_metrics), ("future", future_metrics)):
        for key, value in values.items():
            if value is not None:
                known_metrics.append((group, metric_labels.get(key, key), _number(value)))
    bottlenecks = [
        {"group": group, "metric": label, "score": round(value, 1)}
        for group, label, value in sorted(known_metrics, key=lambda item: item[2])[:5]
    ]

    if past_score is None and future_score is None:
        emphasis = "השלמת נתונים לפני שינוי אסטרטגיה"
        emphasis_reason = "אין כיסוי מספיק לביצועים ולפוטנציאל."
    elif future_score is None or (past_score is not None and _number(past_score) + 4 < _number(future_score)):
        emphasis = "שיפור רווחיות, נזילות ומשמעת תקציבית"
        emphasis_reason = "רכיב ביצועי העבר חלש יחסית לפוטנציאל העתידי."
    elif past_score is None or _number(future_score) + 4 < _number(past_score):
        emphasis = "האצת טכנולוגיה, שוק וקיבולת מוכחת"
        emphasis_reason = "רכיב הפוטנציאל העתידי חלש יחסית לביצועים שכבר נוצרו."
    else:
        emphasis = "איזון בין רווח רבעוני לבניית פוטנציאל Q9"
        emphasis_reason = "שני חצאי הציון קרובים ולכן נכון לשמור על תיק מאוזן."

    def scenario_row(key: str, label: str, description: str) -> dict[str, Any]:
        result = scenario_results.get(key, {})
        base = result.get("scenarios", {}).get("base", {})
        low = result.get("scenarios", {}).get("low", {})
        high = result.get("scenarios", {}).get("high", {})
        budget = result.get("budget", {})
        if key == "original":
            base_score = forecast_score.get("base")
            low_score = forecast_score.get("low")
            high_score = forecast_score.get("high")
        else:
            base_score = base.get("q9_score")
            low_score = low.get("q9_score")
            high_score = high.get("q9_score")
        uplift = None
        if base_score is not None and forecast_score.get("base") is not None:
            uplift = round(_number(base_score) - _number(forecast_score.get("base")), 1)
        return {
            "key": key,
            "label": label,
            "description": description,
            "recommended": key == "recommended",
            # A numerical scenario is not decision-ready until both the
            # approved strategy and at least one Actual quarter exist.
            "feasible": bool(result.get("feasible", True)) and bool(actual_number) and has_strategy,
            "q9_score": {"low": low_score, "base": base_score, "high": high_score},
            "q9_score_uplift": uplift,
            "next_quarter": {
                "net_profit_sf": base.get("net_profit_sf", consolidated.get("net_profit_sf")),
                "ending_cash_sf": base.get("ending_cash_sf", consolidated.get("ending_cash_sf")),
                "debt_sf": base.get("debt_sf", consolidated.get("debt_sf")),
            },
            "budget": budget,
            "actions": result.get("actions", []),
            "violations": result.get("violations", []),
            "warnings": result.get("warnings", []),
            "confidence": forecast.get("confidence"),
        }

    scenarios = [
        scenario_row("original", "המשך האסטרטגיה המקורית", "ללא שינוי יזום; המשך המגמות והיעדים שאושרו."),
        scenario_row("recommended", "התאמה מומלצת", "סל הפעולות בעל האיזון הטוב ביותר בין 50% ביצועים ו־50% פוטנציאל תחת התקציב."),
        scenario_row("growth", "צמיחה / Upside", "העדפת פעולות שמגדילות טכנולוגיה, שוק וקיבולת עתידית."),
        scenario_row("defensive", "הגנה / Downside", "העדפת נזילות, רווחיות והפחתת סיכון כאשר התרחיש השלילי מתממש."),
    ]
    recommended = next(row for row in scenarios if row["key"] == "recommended")
    recommended_result = scenario_results.get("recommended", {})
    dependency = recommended_result.get("dependency_analysis", {})
    sequence = recommended_result.get("recommended_sequence", [])

    original_thesis = str(strategy.get("thesis") or "טרם אושרה תזה אסטרטגית במערכת")
    goals = [str(item) for item in strategy.get("goals", [])]
    constraints = [str(item) for item in strategy.get("constraints", [])]
    priorities = [str(item) for item in strategy.get("priorities", [])]
    deltas = [
        {
            "dimension": "מוקד ניהולי",
            "original": original_thesis,
            "recommended": emphasis,
            "reason": emphasis_reason,
        },
        {
            "dimension": "הקצאת תקציב",
            "original": "המשך ההקצאה שנקבעה במסמך המקורי",
            "recommended": (
                f"סל ממומן עד {_number(recommended.get('budget', {}).get('effective_available_sf')):,.0f} SF, "
                "תוך שמירה על רצפת המזומן"
            ),
            "reason": "כל פעולה נבדקת יחד עם התלויות וההשפעה על המזומן, ולא בנפרד.",
        },
        {
            "dimension": "שיטת בקרה",
            "original": "יעדי Q9 וקווים אדומים",
            "recommended": f"Rolling Plan המתעדכן לאחר כל Actual; האיטרציה הנוכחית מתחילה ב־{next_quarter or '—'}",
            "reason": "תוצאות חדשות משנות את נקודת הפתיחה אך אינן מוחקות את האסטרטגיה המקורית.",
        },
    ]

    action_by_quarter: dict[str, list[dict[str, Any]]] = {item: [] for item in horizon}
    if next_quarter:
        for item in sequence:
            action = item.get("action", {})
            action_by_quarter[next_quarter].append(
                {
                    "step": item.get("step"),
                    "title": action.get("title") or action.get("code") or action.get("type"),
                    "type": action.get("type"),
                    "cost_sf": item.get("cost_sf"),
                    "timing": item.get("timing"),
                    "depends_on": item.get("depends_on", []),
                }
            )

    roadmap: list[dict[str, Any]] = []
    for index, item in enumerate(horizon):
        if index == 0:
            theme = "החלטה וביצוע"
            gate = "אישור תקציב, חוקים, מקורות מידע וסדר הפעולות."
        elif index == 1:
            theme = "מדידה וכיול"
            gate = "השוואת תחזית לביצוע ועדכון מחיר, כמות והנחות."
        elif item in {"Q8", "Q9"}:
            theme = "מקסום נקודת הסיום"
            gate = "שיפור כסף ופוטנציאל ללא השקעה שלא תבשיל עד Q9."
        else:
            theme = "Rolling optimization"
            gate = "המשך רק אם תנאי המעבר של ביקוש, רווחיות, קיבולת ונזילות מתקיימים."
        roadmap.append(
            {
                "quarter": item,
                "theme": theme,
                "actions": action_by_quarter.get(item, []),
                "gate": gate,
                "review": f"לאחר אישור תוצאות {item}, לבנות מחדש תכנית עד Q9.",
            }
        )

    gates = [
        {
            "level": "critical" if item.get("severity") == "high" else "warning",
            "title": item.get("missing", "מידע מקדים חסר"),
            "reason": item.get("reason", ""),
        }
        for item in dependency.get("gaps", [])
    ]
    gates.extend(
        {
            "level": "critical",
            "title": "התנגשות בין פעולות",
            "reason": item.get("reason", ""),
        }
        for item in dependency.get("conflicts", [])
    )
    if not has_strategy:
        gates.insert(
            0,
            {
                "level": "critical",
                "title": "לא אושרה אסטרטגיה ראשונית",
                "reason": "יש להעלות ולאשר את מסמך האסטרטגיה כדי למדוד סטייה אמיתית.",
            },
        )
    if not actual_number:
        gates.insert(
            0,
            {
                "level": "critical",
                "title": "אין Actual מאושר",
                "reason": "יש לאשר לפחות פלט רבעוני אחד לפני יצירת Rolling Plan.",
            },
        )

    status = "ready"
    if not actual_number:
        status = "needs_data"
    elif not has_strategy:
        status = "needs_strategy"
    elif not recommended.get("feasible"):
        status = "blocked"

    return {
        "status": status,
        "planning_quarter": quarter,
        "actual_as_of": actual_as_of or None,
        "next_decision_quarter": next_quarter,
        "horizon": horizon,
        "objective": {
            "past_weight": 0.5,
            "future_weight": 0.5,
            "statement": "מקסום 50% ביצועי עבר + 50% פוטנציאל עתידי עד Q9, תחת חוקי המשחק, תקציב ורצפת מזומן.",
        },
        "source_strategy": {
            "approved": has_strategy,
            "thesis": original_thesis,
            "priorities": priorities,
            "goals": goals,
            "constraints": constraints,
            "source_upload_id": strategy.get("source_upload_id"),
            "updated_at": strategy.get("updated_at"),
        },
        "current_position": {
            "combined_score": combined_score,
            "past_score": past_score,
            "future_score": future_score,
            "forecast_q9": forecast_score,
            "available_budget_sf": consolidated.get("available_budget_sf"),
            "cash_buffer_sf": consolidated.get("cash_buffer_sf"),
            "ending_cash_sf": consolidated.get("ending_cash_sf"),
            "financial_health": consolidated.get("health"),
        },
        "recommended_emphasis": {
            "title": emphasis,
            "reason": emphasis_reason,
            "bottlenecks": bottlenecks,
        },
        "strategy_deltas": deltas,
        "scenarios": scenarios,
        "recommended_plan": {
            "scenario": recommended,
            "sequence": sequence,
            "dependencies": dependency,
            "roadmap": roadmap,
            "decision_gates": gates,
        },
        "evidence": {
            "score_sources": scorecard.get("sources", []),
            "financial_sources": financial.get("sources", []),
            "research_results": intelligence.get("research_results", []),
            "recommendation_count": len(intelligence.get("recommendations", [])),
        },
        "model_limits": [
            "זהו אומדן ניהולי פנימי ולא הציון הרשמי של המשחק.",
            "המלצה מספרית מוצגת רק על בסיס Actuals, מחקרים והנחות שמופיעים במערכת.",
            "האסטרטגיה המומלצת היא טיוטה; היא אינה משנה את האסטרטגיה המאושרת או את נתוני האמת.",
            "לאחר אישור כל רבעון האופק נבנה מחדש מהרבעון הבא עד Q9.",
        ],
        "agent_prompt": (
            f"נתח את טיוטת אופטימיזציית האסטרטגיה על בסיס Actual עד {actual_as_of or 'ללא נתונים'} "
            f"ולאופק {next_quarter or '—'}–Q9. השווה בין האסטרטגיה המקורית, ההתאמה המומלצת, "
            "צמיחה והגנה; אתגר את ההנחות, מצא תלויות והצע שיפור ממומן שממקסם 50% ביצועים ו־50% פוטנציאל."
        ),
    }

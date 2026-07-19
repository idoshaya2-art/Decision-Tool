from __future__ import annotations

from collections import defaultdict
from statistics import median
from typing import Any


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _quarter_number(value: Any) -> int:
    text = str(value or "")
    return int(text[1:]) if text.startswith("Q") and text[1:].isdigit() else 0


def _round(value: Any, digits: int = 2) -> float:
    return round(_number(value), digits)


def _fmt(value: Any, digits: int = 0) -> str:
    return f"{_number(value):,.{digits}f}"


def _direction(delta: float) -> str:
    if delta > 0.001:
        return "up"
    if delta < -0.001:
        return "down"
    return "flat"


def _group_entries(entries: list[dict[str, Any]], value_key: str) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for entry in entries:
        if entry.get(value_key) in (None, ""):
            continue
        key = (str(entry.get("area") or ""), str(entry.get("product") or ""), str(entry.get("model") or ""))
        groups[key].append(entry)
    result: list[dict[str, Any]] = []
    for (area, product, model), rows in sorted(groups.items()):
        values = [_number(row.get(value_key)) for row in rows]
        result.append(
            {
                "area": area,
                "product": product,
                "model": model,
                "minimum": min(values),
                "median": median(values),
                "maximum": max(values),
                "count": len(values),
                "rows": rows,
            }
        )
    return result


def _research_mr28(row: dict[str, Any], company_number: int | None) -> dict[str, Any]:
    entries = list((row.get("numeric_data") or {}).get("entries") or [])
    if not entries:
        return {
            "decision_area": "תמחור ומתחרים",
            "headline": "הדוח קיים, אך לא נמצאו בו תצפיות מחיר מספריות.",
            "exact_metrics": [{"label": "מחירים שנקלטו", "value": 0}],
            "recommendation": "אין להסיק מסקנת תמחור מדוח זה. השתמשו ברבעון שבו קיימות תצפיות MR28 או הזמינו מידע עדכני.",
            "opportunities": [],
            "risks": ["אין בסיס מספרי להשוואת מחירים ברבעון זה."],
            "table": {"columns": [], "rows": []},
        }
    groups = _group_entries(entries, "price_lc")
    table_rows: list[dict[str, Any]] = []
    opportunities: list[str] = []
    risks: list[str] = []
    for group in groups:
        own = next((entry for entry in group["rows"] if company_number and int(entry.get("company") or 0) == company_number), None)
        own_price = _number(own.get("price_lc")) if own else None
        gap = ((own_price / group["median"]) - 1) if own_price is not None and group["median"] else None
        segment = f"{group['area']} · {group['product']} {group['model']}"
        if gap is not None and gap <= -0.08:
            opportunities.append(f"{segment}: המחיר שלנו נמוך בכ-{abs(gap) * 100:.0f}% מחציון השוק.")
        elif gap is not None and gap >= 0.08:
            risks.append(f"{segment}: המחיר שלנו גבוה בכ-{gap * 100:.0f}% מחציון השוק.")
        table_rows.append(
            {
                "segment": segment,
                "market_min": _round(group["minimum"]),
                "market_median": _round(group["median"]),
                "market_max": _round(group["maximum"]),
                "our_value": _round(own_price) if own_price is not None else None,
                "gap_pct": _round(gap * 100, 1) if gap is not None else None,
            }
        )
    recommendation = (
        "בדקו העלאת מחיר מדורגת רק בפלחים שבהם המחיר נמוך מחציון השוק והמלאי נמכר היטב; "
        "בפלחים שבהם המחיר גבוה מהחציון, ודאו שהרמה הטכנולוגית והביקוש מצדיקים את הפרמיה."
    )
    return {
        "decision_area": "תמחור ומתחרים",
        "headline": f"נמדדו {len(entries)} מחירי מתחרים ב-{len(groups)} פלחים.",
        "exact_metrics": [
            {"label": "מחירים שנקלטו", "value": len(entries)},
            {"label": "פלחים מכוסים", "value": len(groups)},
            {"label": "הזדמנויות תמחור", "value": len(opportunities)},
            {"label": "סיכוני מחיר", "value": len(risks)},
        ],
        "recommendation": recommendation,
        "opportunities": opportunities[:5],
        "risks": risks[:5],
        "table": {
            "columns": [
                {"key": "segment", "label": "פלח"},
                {"key": "market_min", "label": "מינימום שוק"},
                {"key": "market_median", "label": "חציון שוק"},
                {"key": "market_max", "label": "מקסימום שוק"},
                {"key": "our_value", "label": "המחיר שלנו"},
                {"key": "gap_pct", "label": "פער מהחציון %"},
            ],
            "rows": table_rows,
        },
    }


def _research_mr17(row: dict[str, Any], company_number: int | None) -> dict[str, Any]:
    entries = list((row.get("numeric_data") or {}).get("entries") or [])
    if not entries:
        return {
            "decision_area": "טכנולוגיה ומיצוב",
            "headline": "הדוח קיים, אך לא נמצאו בו תצפיות רמה מספריות.",
            "exact_metrics": [{"label": "רמות שנקלטו", "value": 0}],
            "recommendation": "אין להסיק פער טכנולוגי מדוח זה. הסתמכו רק על רבעון שבו קיימות תצפיות MR17.",
            "opportunities": [],
            "risks": ["אין בסיס מספרי להשוואת רמות ברבעון זה."],
            "table": {"columns": [], "rows": []},
        }
    groups = _group_entries(entries, "grade")
    table_rows: list[dict[str, Any]] = []
    gaps: list[str] = []
    for group in groups:
        own = next((entry for entry in group["rows"] if company_number and int(entry.get("company") or 0) == company_number), None)
        own_grade = _number(own.get("grade")) if own else None
        gap = group["maximum"] - own_grade if own_grade is not None else None
        segment = f"{group['area']} · {group['product']} {group['model']}"
        if gap is not None and gap >= 1:
            gaps.append(f"{segment}: פער של {gap:.0f} רמות מהמוביל.")
        table_rows.append(
            {
                "segment": segment,
                "market_median": _round(group["median"], 1),
                "market_max": _round(group["maximum"], 1),
                "our_value": _round(own_grade, 1) if own_grade is not None else None,
                "gap": _round(gap, 1) if gap is not None else None,
            }
        )
    return {
        "decision_area": "טכנולוגיה ומיצוב",
        "headline": f"נמדדו {len(entries)} רמות מוצר פעילות ב-{len(groups)} פלחים.",
        "exact_metrics": [
            {"label": "הצעות שנקלטו", "value": len(entries)},
            {"label": "פלחים מכוסים", "value": len(groups)},
            {"label": "פערים מול המוביל", "value": len(gaps)},
        ],
        "recommendation": (
            "התמקדו בסגירת פער טכנולוגי רק בפלחים אסטרטגיים. אין לגבות מחיר פרמיום בפלח שבו "
            "הרמה שלנו נמוכה מהמוביל, אלא אם מחקר ביקוש מוכיח יתרון אחר."
        ),
        "opportunities": [],
        "risks": gaps[:6],
        "table": {
            "columns": [
                {"key": "segment", "label": "פלח"},
                {"key": "market_median", "label": "רמה חציונית"},
                {"key": "market_max", "label": "רמה מובילה"},
                {"key": "our_value", "label": "הרמה שלנו"},
                {"key": "gap", "label": "פער מהמוביל"},
            ],
            "rows": table_rows,
        },
    }


def _research_mr74(row: dict[str, Any], company_number: int | None) -> dict[str, Any]:
    companies = list((row.get("numeric_data") or {}).get("companies") or [])
    sorted_profit = sorted(companies, key=lambda item: _number(item.get("net_earnings_k_sf")), reverse=True)
    own = next((item for item in companies if company_number and int(item.get("company") or 0) == company_number), None)
    own_rank = next((index + 1 for index, item in enumerate(sorted_profit) if own is item), None)
    median_profit = median([_number(item.get("net_earnings_k_sf")) for item in companies]) if companies else 0
    own_profit = _number(own.get("net_earnings_k_sf")) if own else None
    own_cash = _number(own.get("cash_k_sf")) if own else None
    table_rows = [
        {
            "company": int(item.get("company") or 0),
            "cash": _round(item.get("cash_k_sf")),
            "inventory": _round(item.get("inventory_k_sf")),
            "sales": _round(item.get("consumer_sales_k_sf")),
            "operating": _round(item.get("operating_earnings_k_sf")),
            "net": _round(item.get("net_earnings_k_sf")),
        }
        for item in sorted_profit
    ]
    if own_profit is None:
        recommendation = "השתמשו בחציון הענפי כנקודת ייחוס לרווחיות ולנזילות ובדקו את מיקום החברה לאחר זיהוי מספרה."
    elif own_profit < median_profit:
        recommendation = "הרווח הנקי נמוך מחציון הענף; תעדפו פעולות המשפרות תרומה ותזרים לפני הרחבת קיבולת עתירת מזומן."
    else:
        recommendation = "הרווחיות מעל חציון הענף; ניתן לבחון השקעה מבוקרת בפוטנציאל עתידי, בתנאי שרצפת המזומן נשמרת."
    return {
        "decision_area": "ביצועים מול הענף",
        "headline": (
            f"החברה מדורגת {own_rank} מתוך {len(companies)} ברווח נקי; "
            f"חציון הענף הוא {_fmt(median_profit)}K SF."
            if own_rank
            else f"הושוו {len(companies)} חברות; חציון הרווח הנקי הוא {_fmt(median_profit)}K SF."
        ),
        "exact_metrics": [
            {"label": "חברות בהשוואה", "value": len(companies)},
            {"label": "דירוג רווח נקי", "value": own_rank},
            {"label": "רווח נקי שלנו K SF", "value": _round(own_profit) if own_profit is not None else None},
            {"label": "מזומן שלנו K SF", "value": _round(own_cash) if own_cash is not None else None},
            {"label": "חציון רווח ענפי K SF", "value": _round(median_profit)},
        ],
        "recommendation": recommendation,
        "opportunities": [],
        "risks": [],
        "table": {
            "columns": [
                {"key": "company", "label": "חברה"},
                {"key": "cash", "label": "מזומן K SF"},
                {"key": "inventory", "label": "מלאי K SF"},
                {"key": "sales", "label": "מכירות K SF"},
                {"key": "operating", "label": "רווח תפעולי K SF"},
                {"key": "net", "label": "רווח נקי K SF"},
            ],
            "rows": table_rows,
        },
    }


def _research_mr40(row: dict[str, Any], company_number: int | None) -> dict[str, Any]:
    entries = list((row.get("numeric_data") or {}).get("entries") or [])
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for entry in entries:
        groups[(str(entry.get("area") or ""), str(entry.get("product") or ""))].append(entry)
    table_rows: list[dict[str, Any]] = []
    for (area, product), rows in sorted(groups.items()):
        values = [_number(item.get("plants")) for item in rows]
        own = next((item for item in rows if company_number and int(item.get("company") or 0) == company_number), None)
        table_rows.append(
            {
                "segment": f"{area} · {product}",
                "market_total": _round(sum(values)),
                "market_average": _round(sum(values) / len(values), 1) if values else 0,
                "our_value": _round(own.get("plants")) if own else None,
            }
        )
    return {
        "decision_area": "קיבולת ותחרות",
        "headline": f"מופו {len(entries)} נתוני מפעלים ב-{len(groups)} שילובי אזור ומוצר.",
        "exact_metrics": [
            {"label": "רשומות מפעלים", "value": len(entries)},
            {"label": "שווקים מכוסים", "value": len(groups)},
        ],
        "recommendation": (
            "אל תרחיבו מפעל רק משום שהמתחרים מחזיקים קיבולת. הרחבה מומלצת רק כאשר תחזית הביקוש, "
            "ניצולת הקיבולת, כלכלת היחידה וזמן ההחזר עד Q9 תומכים בה."
        ),
        "opportunities": [],
        "risks": [],
        "table": {
            "columns": [
                {"key": "segment", "label": "אזור ומוצר"},
                {"key": "market_total", "label": "סה״כ מפעלים בענף"},
                {"key": "market_average", "label": "ממוצע לחברה"},
                {"key": "our_value", "label": "המפעלים שלנו"},
            ],
            "rows": table_rows,
        },
    }


def _research_range(row: dict[str, Any]) -> dict[str, Any]:
    data = row.get("numeric_data") or {}
    ranges = list(data.get("ranges") or [])
    measure = str(data.get("measure") or "")
    product = str(data.get("product") or row.get("product") or "")
    grade = data.get("grade")
    is_price = measure == "price_premium_pct"
    table_rows = [
        {
            "area": item.get("area"),
            "low": _round(item.get("low_pct"), 1),
            "high": _round(item.get("high_pct"), 1),
            "midpoint": _round((_number(item.get("low_pct")) + _number(item.get("high_pct"))) / 2, 1),
        }
        for item in ranges
    ]
    label = "פרמיית מחיר" if is_price else "תוספת עלות"
    recommendation = (
        "השתמשו בטווח כקלט לתרחיש נמוך–בסיס–גבוה. מעבר רמה כדאי רק לאחר השוואת פרמיית המחיר "
        "לתוספת העלות באותו מוצר, רמה ואזור."
    )
    return {
        "decision_area": "תמחור וכלכלת רמה",
        "headline": f"{label} עבור {product}{grade}: נמצאו טווחים מדויקים ב-{len(ranges)} אזורים.",
        "exact_metrics": [
            {"label": "מוצר ורמה", "value": f"{product}{grade}"},
            {"label": "סוג מדד", "value": label},
            {"label": "אזורים מכוסים", "value": len(ranges)},
        ],
        "recommendation": recommendation,
        "opportunities": [],
        "risks": [] if ranges else ["לא זוהה טווח מספרי מלא; יש לבדוק את קובץ המקור."],
        "table": {
            "columns": [
                {"key": "area", "label": "אזור"},
                {"key": "low", "label": "טווח נמוך %"},
                {"key": "high", "label": "טווח גבוה %"},
                {"key": "midpoint", "label": "נקודת בסיס %"},
            ],
            "rows": table_rows,
        },
    }


def _research_generic(row: dict[str, Any]) -> dict[str, Any]:
    data = row.get("numeric_data") or {}
    raw_rows = list(data.get("rows") or [])
    table_rows = [
        {"line": index + 1, "values": " | ".join(str(value) for value in raw[:12] if value not in (None, ""))}
        for index, raw in enumerate(raw_rows[:30])
    ]
    return {
        "decision_area": "מחקר שוק",
        "headline": str(row.get("key_result") or "נקלט מחקר ללא סיכום מספרי מובנה."),
        "exact_metrics": [{"label": "שורות נתונים שנקלטו", "value": len(raw_rows)}],
        "recommendation": "יש לקשור את התוצאה להחלטה ספציפית לפני פעולה; ה-Agent יכול להסביר את טבלת המקור ולבנות בדיקת רגישות.",
        "opportunities": [],
        "risks": ["מבנה המחקר אינו ממופה עדיין למדד החלטה ייעודי."] if raw_rows else [],
        "table": {
            "columns": [{"key": "line", "label": "שורה"}, {"key": "values", "label": "ערכים מדויקים מהמקור"}],
            "rows": table_rows,
        },
    }


def enrich_research_results(
    rows: list[dict[str, Any]],
    company_number: int | None = None,
    source_names: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    source_names = source_names or {}
    enriched: list[dict[str, Any]] = []
    for row in sorted(rows, key=lambda item: (_quarter_number(item.get("quarter")), int(item.get("study_id") or 999))):
        study_id = int(row.get("study_id") or 0)
        if study_id == 28:
            interpretation = _research_mr28(row, company_number)
        elif study_id == 17:
            interpretation = _research_mr17(row, company_number)
        elif study_id == 74:
            interpretation = _research_mr74(row, company_number)
        elif study_id == 40:
            interpretation = _research_mr40(row, company_number)
        elif 31 <= study_id <= 69 and (row.get("numeric_data") or {}).get("ranges") is not None:
            interpretation = _research_range(row)
        else:
            interpretation = _research_generic(row)
        source_id = str(row.get("source_upload_id") or "")
        enriched.append(
            {
                **row,
                **interpretation,
                "source_name": source_names.get(source_id, ""),
                "source_label": f"{row.get('quarter', '')} · MR{study_id}" if study_id else str(row.get("quarter") or ""),
            }
        )
    return enriched


def build_cross_research_insights(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    range_rows: dict[tuple[str, int, str, str], dict[str, float]] = defaultdict(dict)
    for row in rows:
        data = row.get("numeric_data") or {}
        measure = str(data.get("measure") or "")
        if measure not in {"price_premium_pct", "cost_premium_pct"}:
            continue
        product = str(data.get("product") or row.get("product") or "")
        grade = int(data.get("grade") or 0)
        for item in data.get("ranges") or []:
            area = str(item.get("area") or "")
            midpoint = (_number(item.get("low_pct")) + _number(item.get("high_pct"))) / 2
            range_rows[(product, grade, area, str(row.get("quarter") or ""))][measure] = midpoint
    insights: list[dict[str, Any]] = []
    for (product, grade, area, quarter), values in sorted(range_rows.items()):
        if "price_premium_pct" not in values or "cost_premium_pct" not in values:
            continue
        spread = values["price_premium_pct"] - values["cost_premium_pct"]
        insights.append(
            {
                "type": "grade_economics",
                "title": f"כדאיות מעבר ל-{product}{grade} · {area}",
                "quarter": quarter,
                "evidence": (
                    f"פרמיית מחיר בסיסית {values['price_premium_pct']:.1f}% מול תוספת עלות "
                    f"{values['cost_premium_pct']:.1f}%; פער {spread:+.1f} נקודות אחוז."
                ),
                "direction": "up" if spread > 0 else "down",
                "recommendation": (
                    "קיימת אינדיקציה כלכלית חיובית למעבר רמה; יש להשלים בדיקת ביקוש, מלאי ישן ותזמון."
                    if spread > 0
                    else "אין הצדקת מרווח למעבר רמה בתרחיש הבסיס; בדקו מחיר גבוה יותר או עלות נמוכה יותר."
                ),
                "confidence": "בינונית",
            }
        )
    return insights


def build_cumulative_trends(
    finance_rows: list[dict[str, Any]],
    operations: list[dict[str, Any]],
    research_rows: list[dict[str, Any]],
    through_quarter: str,
) -> dict[str, Any]:
    end = _quarter_number(through_quarter)
    finances = sorted(
        [row for row in finance_rows if 0 < _quarter_number(row.get("quarter")) <= end],
        key=lambda row: _quarter_number(row.get("quarter")),
    )
    ops = [row for row in operations if 0 < _quarter_number(row.get("quarter")) <= end]
    cards: list[dict[str, Any]] = []
    if len(finances) >= 2:
        first, last = finances[0], finances[-1]
        for field, title, unit in (
            ("revenue_sf", "מגמת הכנסות", "SF"),
            ("net_profit_sf", "מגמת רווח נקי", "SF"),
            ("ending_cash_sf", "מגמת מזומן", "SF"),
        ):
            start = _number(first.get(field))
            finish = _number(last.get(field))
            delta = finish - start
            cards.append(
                {
                    "type": "financial",
                    "title": title,
                    "direction": _direction(delta),
                    "evidence": f"{first.get('quarter')}: {_fmt(start)} {unit} → {last.get('quarter')}: {_fmt(finish)} {unit}. שינוי {delta:+,.0f} {unit}.",
                    "recommendation": (
                        "המגמה חיובית; שמרו על הגורמים שהובילו לשיפור ובדקו שאינה נרכשה באמצעות שחיקת מזומן או מלאי."
                        if delta > 0
                        else "המגמה שלילית; דרושה פעולה ממוקדת ברווחיות, הוצאות או הון חוזר לפני הרחבה."
                    ),
                    "confidence": "גבוהה",
                }
            )
    grouped_ops: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in ops:
        grouped_ops[(str(row.get("area") or ""), str(row.get("product") or ""), str(row.get("model") or ""))].append(row)
    pricing: list[dict[str, Any]] = []
    for (area, product, model), rows in sorted(grouped_ops.items()):
        rows.sort(key=lambda item: _quarter_number(item.get("quarter")))
        # A zero price in an imported INTOPIA row means "not reported", not a
        # valid market price. Do not create a pricing trend from missing values.
        priced_rows = [row for row in rows if _number(row.get("actual_price_lc")) > 0]
        if len(priced_rows) < 2:
            continue
        first, last = priced_rows[0], priced_rows[-1]
        price_delta = _number(last.get("actual_price_lc")) - _number(first.get("actual_price_lc"))
        sales_delta = _number(last.get("actual_sales")) - _number(first.get("actual_sales"))
        inventory_delta = _number(last.get("ending_inventory")) - _number(first.get("ending_inventory"))
        pricing.append(
            {
                "segment": f"{area} · {product} {model}",
                "from_quarter": first.get("quarter"),
                "to_quarter": last.get("quarter"),
                "price_from": _round(first.get("actual_price_lc")),
                "price_to": _round(last.get("actual_price_lc")),
                "price_delta": _round(price_delta),
                "sales_delta": _round(sales_delta),
                "inventory_delta": _round(inventory_delta),
                "signal": (
                    "מחיר עלה והמכירות לא נשחקו"
                    if price_delta > 0 and sales_delta >= 0
                    else "מחיר עלה והמכירות נשחקו"
                    if price_delta > 0 and sales_delta < 0
                    else "מחיר ירד אך המלאי עדיין גדל"
                    if price_delta < 0 and inventory_delta > 0
                    else "נדרשות תצפיות נוספות"
                ),
                "recommendation": (
                    "בדקו העלאה נוספת קטנה בתרחיש; האות הראשוני תומך בכוח תמחור."
                    if price_delta > 0 and sales_delta >= 0
                    else "בדקו רגישות מחיר מול השפעת מתחרים ורמה לפני שינוי נוסף."
                ),
            }
        )
    competitor_series: dict[tuple[str, str, str], dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for row in research_rows:
        if int(row.get("study_id") or 0) != 28:
            continue
        quarter = str(row.get("quarter") or "")
        for entry in (row.get("numeric_data") or {}).get("entries") or []:
            if entry.get("price_lc") in (None, ""):
                continue
            key = (str(entry.get("area") or ""), str(entry.get("product") or ""), str(entry.get("model") or ""))
            competitor_series[key][quarter].append(_number(entry.get("price_lc")))
    competitors: list[dict[str, Any]] = []
    for (area, product, model), by_quarter in sorted(competitor_series.items()):
        points = sorted(
            [{"quarter": quarter, "median": median(values), "minimum": min(values), "maximum": max(values)} for quarter, values in by_quarter.items()],
            key=lambda item: _quarter_number(item["quarter"]),
        )
        if not points:
            continue
        delta = points[-1]["median"] - points[0]["median"]
        competitors.append(
            {
                "segment": f"{area} · {product} {model}",
                "from_quarter": points[0]["quarter"],
                "to_quarter": points[-1]["quarter"],
                "median_from": _round(points[0]["median"]),
                "median_to": _round(points[-1]["median"]),
                "delta": _round(delta),
                "direction": _direction(delta),
                "observations": sum(len(values) for values in by_quarter.values()),
            }
        )
    return {
        "cards": cards,
        "pricing": pricing,
        "competitors": competitors,
        "cross_research": build_cross_research_insights(research_rows),
    }

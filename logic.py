from __future__ import annotations

from dataclasses import dataclass, asdict
from math import isfinite
from typing import Any, Iterable

from seed_data import LOAN_OPTIONS, XY_CONVERSION


def num(value: Any, default: float = 0.0) -> float:
    try:
        n = float(value)
        return n if isfinite(n) else default
    except (TypeError, ValueError):
        return default


def scenario_calculation(row: dict[str, Any]) -> dict[str, float | str]:
    price = num(row.get("price_lc"))
    demand = max(0.0, num(row.get("demand")))
    production = max(0.0, num(row.get("production")))
    opening_inventory = max(0.0, num(row.get("opening_inventory")))
    variable_cost = max(0.0, num(row.get("variable_cost_lc")))
    advertising = max(0.0, num(row.get("advertising_lc")))
    fixed_cost = max(0.0, num(row.get("fixed_cost_lc")))
    transport = max(0.0, num(row.get("transport_per_unit_lc")))
    inventory_cost = max(0.0, num(row.get("inventory_cost_per_unit_lc")))
    tax_rate = min(1.0, max(0.0, num(row.get("tax_rate"))))
    fx = max(0.000001, num(row.get("fx_to_sf"), 1.0))

    available = opening_inventory + production
    sold = min(available, demand)
    revenue_lc = sold * price
    cogs_lc = sold * (variable_cost + transport)
    ending_inventory = max(0.0, available - sold)
    inventory_charge = ending_inventory * inventory_cost
    gross_profit = revenue_lc - cogs_lc
    operating_profit = gross_profit - advertising - fixed_cost - inventory_charge
    net_profit_lc = operating_profit * (1 - tax_rate) if operating_profit > 0 else operating_profit
    net_profit_sf = net_profit_lc / fx
    cash_impact_sf = (revenue_lc - cogs_lc - advertising - fixed_cost - inventory_charge - production * variable_cost) / fx
    unit_contribution = price - variable_cost - transport
    break_even = (advertising + fixed_cost) / unit_contribution if unit_contribution > 0 else 0
    margin = net_profit_lc / revenue_lc if revenue_lc > 0 else 0

    warning = "תקין"
    if price <= variable_cost + transport:
        warning = "מחיר מתחת לעלות שולית"
    elif ending_inventory > max(sold * 1.5, 1):
        warning = "מלאי גבוה"
    elif operating_profit < 0:
        warning = "הפסד תפעולי"

    return {
        "available_units": round(available, 2),
        "units_sold": round(sold, 2),
        "revenue_lc": round(revenue_lc, 2),
        "cogs_lc": round(cogs_lc, 2),
        "ending_inventory": round(ending_inventory, 2),
        "inventory_charge_lc": round(inventory_charge, 2),
        "gross_profit_lc": round(gross_profit, 2),
        "operating_profit_lc": round(operating_profit, 2),
        "net_profit_lc": round(net_profit_lc, 2),
        "net_profit_sf": round(net_profit_sf, 2),
        "cash_impact_sf": round(cash_impact_sf, 2),
        "break_even_units": round(break_even, 2),
        "net_margin": round(margin, 4),
        "warning": warning,
    }


def loan_plan(amount: float, balloon: bool = False) -> dict[str, float | int | str]:
    amount = num(amount)
    option = next((x for x in LOAN_OPTIONS if x["amount"] == amount), None)
    if option is None:
        return {"legal": False, "message": "במשחק מותר לבחור 0 או 1–5 מיליון SF בלבד."}
    if amount == 0:
        return {"legal": True, "amount": 0, "quarterly_payment": 0, "total_interest": 0, "total_cost": 0, "message": "ללא הלוואה"}

    rate = option["balloon_rate"] if balloon else option["annuity_rate"]
    n = option["quarters"]
    if balloon:
        total_interest = amount * rate
        return {
            "legal": True,
            "amount": amount,
            "rate": rate,
            "quarters": n,
            "quarterly_payment": 0,
            "final_payment": amount + total_interest,
            "total_interest": total_interest,
            "total_cost": amount + total_interest,
            "message": "הלוואת בלון",
        }

    r = rate
    payment = amount / n if r == 0 else amount * (r * (1 + r) ** n) / ((1 + r) ** n - 1)
    total_cost = payment * n
    return {
        "legal": True,
        "amount": amount,
        "rate": rate,
        "quarters": n,
        "quarterly_payment": payment,
        "total_interest": total_cost - amount,
        "total_cost": total_cost,
        "message": "לוח שפיצר",
    }


def required_chips(x_grade: int, y_grade: int, y_units: float) -> float | None:
    if x_grade not in XY_CONVERSION or not 0 <= y_grade <= 9:
        return None
    chips_per_pc = XY_CONVERSION[x_grade][y_grade]
    if chips_per_pc == 0:
        return None
    return chips_per_pc * max(0.0, num(y_units))


def _find_operation(operations: Iterable[dict[str, Any]], area: str, product: str, model: str | None = None) -> list[dict[str, Any]]:
    return [o for o in operations if o.get("area") == area and o.get("product") == product and (model is None or o.get("model") == model)]


def decision_gates(settings: dict[str, Any], finance: dict[str, Any], operations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # An empty platform must not manufacture red alerts from missing data.
    if not finance and not operations:
        return []
    buffer = max(0.0, num(settings.get("cash_buffer_sf"), 0))
    min_rd = max(0.0, num(settings.get("min_rd_sf"), 0))
    closing_cash = num(finance.get("ending_cash_sf"))
    net_profit = num(finance.get("net_profit_sf"))
    research_budget = num(finance.get("research_budget_sf"))
    rd_total = num(finance.get("rd_x_sf")) + num(finance.get("rd_y_sf"))
    partnership_score = num(finance.get("partnership_score"))

    total_forecast = sum(num(o.get("forecast_demand")) for o in operations)
    total_sales = sum(num(o.get("actual_sales")) for o in operations)
    total_planned_sales = sum(num(o.get("planned_sales")) for o in operations)
    total_inventory = sum(num(o.get("ending_inventory")) for o in operations)
    total_production = sum(num(o.get("actual_production")) for o in operations)
    total_capacity = sum(num(o.get("plants")) * num(o.get("plant_capacity")) for o in operations)

    demand_ratio = total_sales / total_forecast if total_forecast > 0 else 0
    sales_plan_ratio = total_sales / total_planned_sales if total_planned_sales > 0 else 0
    inventory_cover = total_inventory / total_sales if total_sales > 0 else (999 if total_inventory > 0 else 0)
    capacity_util = total_production / total_capacity if total_capacity > 0 else 0

    gates: list[dict[str, Any]] = []

    def add(domain: str, name: str, metric: str, value: float, green: bool, yellow: bool, action: str, formatted: str | None = None):
        status = "ירוק" if green else ("צהוב" if yellow else "אדום")
        gates.append({"domain": domain, "name": name, "metric": metric, "value": value, "display_value": formatted or f"{value:,.2f}", "status": status, "action": action})

    add("פיננסים", "נזילות", "מזומן סגירה מול כרית", closing_cash, closing_cash >= buffer, closing_cash >= 0, "שמרו כרית מזומן לפני השקעות.", f"{closing_cash:,.0f} SF")
    add("פיננסים", "רווחיות", "רווח נקי ב-SF", net_profit, net_profit >= 0, net_profit >= -0.25 * buffer, "פרקו סטייה למחיר, נפח, עלות והוצאות.", f"{net_profit:,.0f} SF")
    add("שוק", "אימות ביקוש", "מכירות בפועל / תחזית", demand_ratio, demand_ratio >= 0.90, demand_ratio >= 0.70, "עדכנו תחזית, מחיר וייצור לפי הביקוש בפועל.", f"{demand_ratio:.0%}")
    add("תפעול", "מלאי", "מלאי סופי / מכירות", inventory_cover, inventory_cover <= 1.0, inventory_cover <= 1.5, "עצרו ייצור עודף וסלקו רמות מתיישנות.", f"{inventory_cover:.2f} רבעונים")
    add("תפעול", "קיבולת", "ייצור בפועל / קיבולת", capacity_util, 0.65 <= capacity_util <= 1.05, 0.40 <= capacity_util <= 1.15, "ייצרו קרוב לאופטימום והימנעו משינויים חדים.", f"{capacity_util:.0%}")
    add("מו״פ", "רציפות מו״פ", "השקעת X+Y ב-SF", rd_total, rd_total >= min_rd, rd_total > 0, "עדיפות לתכנית רציפה; הימנעו מהשקעות קופצניות.", f"{rd_total:,.0f} SF")
    add("שיווק", "ביצוע מכירות", "מכירות בפועל / תכנית", sales_plan_ratio, sales_plan_ratio >= 0.90, sales_plan_ratio >= 0.70, "בדקו מחיר, פרסום, ערוץ ומלאי זמין.", f"{sales_plan_ratio:.0%}")
    add("מידע", "משמעת מחקר", "תקציב מחקרי שוק", research_budget, research_budget >= 10000, research_budget > 0, "לפני רמה חדשה, מפעל או שינוי מחיר מהותי – רכשו מידע ממוקד.", f"{research_budget:,.0f} SF")
    add("שותפויות", "איכות שותפות", "ציון הנהלה 1–5", partnership_score, partnership_score >= 4, partnership_score >= 2, "ודאו Win-Win, תנאים, לוחות זמנים וסיכון נגד-צד.", f"{partnership_score:.1f}/5")

    # X-Y compatibility: evaluate each Y row against same-area X inventory/production rows.
    coverage_values: list[float] = []
    for y in [o for o in operations if o.get("product") == "Y" and num(o.get("actual_production")) > 0]:
        y_grade = int(num(y.get("grade")))
        y_units = num(y.get("actual_production"))
        candidates = _find_operation(operations, y.get("area", ""), "X")
        best_coverage = 0.0
        for x in candidates:
            x_grade = int(num(x.get("grade")))
            needed = required_chips(x_grade, y_grade, y_units)
            if needed:
                available = num(x.get("opening_inventory")) + num(x.get("actual_production")) - num(x.get("actual_sales"))
                best_coverage = max(best_coverage, available / needed)
        coverage_values.append(best_coverage)
    coverage = min(coverage_values) if coverage_values else 1.0
    add("ייצור", "התאמת X–Y", "כיסוי רכיבים לייצור Y", coverage, coverage >= 1.0, coverage >= 0.90, "אל תאשרו ייצור מחשבים ללא רכיבים תואמים ומספיקים.", f"{coverage:.0%}")
    return gates


def build_summary(company_name: str, quarter: str, dashboard: dict[str, Any], gates: list[dict[str, Any]], operations: list[dict[str, Any]]) -> str:
    display_name = company_name.strip() if company_name else "חברה שטרם הוגדרה"
    if not dashboard.get("has_any_data"):
        return "\n".join([
            f"# סיכום הנהלה — {display_name} | {quarter}",
            "",
            "טרם הוזנו נתונים מובנים לרבעון זה.",
            "",
            "## הפעולות הבאות",
            "- העלאת אסטרטגיה ראשונית ויעדי Q9.",
            "- העלאת Datalog / כללי המשחק.",
            "- העלאת פלט רבעוני או קובץ Q1–Q3 משולב.",
            "- אישור המיפוי והנתונים לפני הפעלת מודל ההחלטות.",
        ])
    company_name = display_name
    red = [g for g in gates if g["status"] == "אדום"]
    yellow = [g for g in gates if g["status"] == "צהוב"]
    top_actions = red[:3] + yellow[: max(0, 3 - len(red[:3]))]
    lines = [
        f"# סיכום הנהלה — {company_name} | {quarter}",
        "",
        "## תמונת מצב",
        f"- הכנסות: {num(dashboard.get('revenue_sf')):,.0f} SF",
        f"- רווח נקי: {num(dashboard.get('net_profit_sf')):,.0f} SF",
        f"- מזומן סגירה: {num(dashboard.get('ending_cash_sf')):,.0f} SF",
        f"- חוב: {num(dashboard.get('debt_sf')):,.0f} SF",
        f"- יחידות שנמכרו: {num(dashboard.get('units_sold')):,.0f}",
        f"- מלאי סופי: {num(dashboard.get('ending_inventory')):,.0f}",
        "",
        "## צמתי החלטה",
    ]
    if top_actions:
        for gate in top_actions:
            lines.append(f"- **{gate['status']} — {gate['domain']} / {gate['name']}**: {gate['display_value']}. {gate['action']}")
    else:
        lines.append("- אין התראות מהותיות ברבעון זה.")
    lines.extend(["", "## תמונת פעילות לפי אזור ומוצר"])
    for row in operations:
        if any(num(row.get(k)) for k in ("planned_production", "actual_production", "planned_sales", "actual_sales", "ending_inventory")):
            lines.append(
                f"- {row.get('area')} / {row.get('product')} {row.get('model')} רמה {int(num(row.get('grade')))}: "
                f"ייצור בפועל {num(row.get('actual_production')):,.0f}, מכירות {num(row.get('actual_sales')):,.0f}, מלאי {num(row.get('ending_inventory')):,.0f}."
            )
    lines.extend(["", "## החלטת הנהלה", "- יש להשלים במערכת את ההחלטות, ההנחות והאחראים לפני סגירת הרבעון."])
    return "\n".join(lines)


def _clamp(value: float, low: float, high: float) -> float:
    return min(high, max(low, value))


def _round_to_step(value: float, step: float) -> float:
    step = max(0.000001, step)
    return round(round(value / step) * step, 6)


def _economics_at_price(row: dict[str, Any], price: float) -> dict[str, float | str]:
    """Calculate unit economics for one price point.

    Demand uses a constant-elasticity curve around a user-supplied market anchor.
    This is a decision model, not a claim about the hidden INTOPIA demand function.
    """
    base_price = max(0.000001, num(row.get("base_price_lc"), price or 1.0))
    base_demand = max(0.0, num(row.get("base_demand_units")))
    elasticity = max(0.0, num(row.get("elasticity"), 1.0))
    demand_multiplier = max(0.0, num(row.get("demand_multiplier"), 1.0))
    available_units = max(0.0, num(row.get("available_units"), base_demand))

    manufacturing = max(0.0, num(row.get("manufacturing_cost_lc")))
    component = max(0.0, num(row.get("component_cost_lc")))
    freight = max(0.0, num(row.get("freight_cost_lc")))
    variable_selling = max(0.0, num(row.get("variable_selling_cost_lc")))
    inventory_risk = max(0.0, num(row.get("inventory_risk_cost_lc")))
    other_variable = max(0.0, num(row.get("other_variable_cost_lc")))
    unit_variable_cost = manufacturing + component + freight + variable_selling + inventory_risk + other_variable

    bad_debt = _clamp(num(row.get("bad_debt_rate")), 0.0, 1.0)
    payment_delay = max(0.0, num(row.get("payment_delay_quarters")))
    financing_rate = max(0.0, num(row.get("quarterly_financing_rate")))
    credit_cost_per_unit = price * (bad_debt + payment_delay * financing_rate)
    realized_net_price = price - credit_cost_per_unit
    contribution_per_unit = realized_net_price - unit_variable_cost

    if price <= 0 or base_demand <= 0:
        expected_demand = 0.0
    else:
        expected_demand = base_demand * (price / base_price) ** (-elasticity) * demand_multiplier
    units_sold = min(available_units, expected_demand)
    ending_inventory = max(0.0, available_units - units_sold)

    fixed_cost = max(0.0, num(row.get("fixed_cost_lc")))
    advertising = max(0.0, num(row.get("advertising_lc")))
    research_allocation = max(0.0, num(row.get("research_allocation_lc")))
    inventory_carry = max(0.0, num(row.get("inventory_carry_cost_lc")))
    inventory_charge = ending_inventory * inventory_carry
    total_fixed = fixed_cost + advertising + research_allocation

    gross_revenue = units_sold * price
    net_revenue = units_sold * realized_net_price
    total_variable_cost = units_sold * unit_variable_cost
    contribution = units_sold * contribution_per_unit
    operating_profit = contribution - total_fixed - inventory_charge
    tax_rate = _clamp(num(row.get("tax_rate")), 0.0, 1.0)
    net_profit = operating_profit * (1 - tax_rate) if operating_profit > 0 else operating_profit
    fx_to_sf = max(0.000001, num(row.get("fx_to_sf"), 1.0))

    contribution_margin = contribution_per_unit / realized_net_price if realized_net_price > 0 else 0.0
    operating_margin = operating_profit / gross_revenue if gross_revenue > 0 else 0.0
    profit_per_unit = operating_profit / units_sold if units_sold > 0 else 0.0
    break_even_units = total_fixed / contribution_per_unit if contribution_per_unit > 0 else 0.0

    return {
        "price_lc": round(price, 4),
        "expected_demand_units": round(expected_demand, 2),
        "available_units": round(available_units, 2),
        "units_sold": round(units_sold, 2),
        "ending_inventory": round(ending_inventory, 2),
        "gross_revenue_lc": round(gross_revenue, 2),
        "realized_net_price_lc": round(realized_net_price, 4),
        "credit_cost_per_unit_lc": round(credit_cost_per_unit, 4),
        "unit_variable_cost_lc": round(unit_variable_cost, 4),
        "contribution_per_unit_lc": round(contribution_per_unit, 4),
        "contribution_margin": round(contribution_margin, 6),
        "total_contribution_lc": round(contribution, 2),
        "inventory_charge_lc": round(inventory_charge, 2),
        "operating_profit_lc": round(operating_profit, 2),
        "operating_profit_sf": round(operating_profit / fx_to_sf, 2),
        "net_profit_lc": round(net_profit, 2),
        "net_profit_sf": round(net_profit / fx_to_sf, 2),
        "operating_margin": round(operating_margin, 6),
        "profit_per_unit_lc": round(profit_per_unit, 4),
        "break_even_units": round(break_even_units, 2),
    }


def unit_economics_calculation(row: dict[str, Any]) -> dict[str, Any]:
    current_price = max(0.0, num(row.get("price_lc")))
    step = max(0.000001, num(row.get("price_step_lc"), 1.0))
    current = _economics_at_price(row, current_price)

    variable_cost = num(current.get("unit_variable_cost_lc"))
    credit_fraction = _clamp(num(row.get("bad_debt_rate")), 0.0, 1.0) + max(0.0, num(row.get("payment_delay_quarters"))) * max(0.0, num(row.get("quarterly_financing_rate")))
    effective_revenue_fraction = max(0.000001, 1.0 - credit_fraction)
    expected_units = max(1.0, min(max(0.0, num(row.get("available_units"))), max(0.0, num(row.get("base_demand_units"))) * max(0.0, num(row.get("demand_multiplier"), 1.0))))
    total_fixed = max(0.0, num(row.get("fixed_cost_lc"))) + max(0.0, num(row.get("advertising_lc"))) + max(0.0, num(row.get("research_allocation_lc")))
    target_margin = _clamp(num(row.get("target_operating_margin"), 0.15), 0.0, 0.90)

    cash_floor = variable_cost / effective_revenue_fraction
    break_even_price = (variable_cost + total_fixed / expected_units) / effective_revenue_fraction
    target_margin_price = (variable_cost + total_fixed / expected_units) / max(0.000001, effective_revenue_fraction - target_margin)

    price_min = max(step, num(row.get("price_min_lc"), current_price * 0.7))
    price_max = max(price_min, num(row.get("price_max_lc"), current_price * 1.3))
    legal_cap = num(row.get("legal_price_cap_lc"))
    if legal_cap > 0:
        price_max = min(price_max, legal_cap)
    price_min = _round_to_step(price_min, step)
    price_max = _round_to_step(price_max, step)

    grid: list[dict[str, float | str]] = []
    max_points = 101
    p = price_min
    count = 0
    while p <= price_max + step / 2 and count < max_points:
        result = _economics_at_price(row, p)
        status = "רווחי"
        if num(result["contribution_per_unit_lc"]) <= 0:
            status = "מתחת לעלות משתנה"
        elif num(result["operating_profit_lc"]) < 0:
            status = "לא מכסה קבועות"
        elif num(result["ending_inventory"]) > num(result["units_sold"]):
            status = "סיכון מלאי"
        result["status"] = status
        grid.append(result)
        p = _round_to_step(p + step, step)
        count += 1

    if not grid:
        grid = [{**current, "status": "לא חושב"}]
    best = max(grid, key=lambda item: num(item.get("operating_profit_lc")))
    max_profit = num(best.get("operating_profit_lc"))
    near_optimal = [x for x in grid if max_profit > 0 and num(x.get("operating_profit_lc")) >= 0.90 * max_profit]
    safe_low = min((num(x.get("price_lc")) for x in near_optimal), default=num(best.get("price_lc")))
    safe_high = max((num(x.get("price_lc")) for x in near_optimal), default=num(best.get("price_lc")))

    best_price = num(best.get("price_lc"))
    delta = best_price - current_price
    if abs(delta) < step / 2:
        recommendation = "להחזיק מחיר"
    elif delta > 0:
        recommendation = "לבחון העלאת מחיר"
    else:
        recommendation = "לבחון הורדת מחיר"

    warnings: list[str] = []
    if current_price < cash_floor:
        warnings.append("המחיר הנוכחי אינו מכסה את העלות המשתנה והאשראי")
    elif current_price < break_even_price:
        warnings.append("המחיר הנוכחי תורם ליחידה אך אינו מכסה את העלויות הקבועות בנפח המתוכנן")
    if num(current.get("ending_inventory")) > num(current.get("units_sold")):
        warnings.append("המלאי הצפוי גבוה מהמכירות הצפויות")
    if num(row.get("elasticity")) <= 0:
        warnings.append("לא הוזנה אלסטיות; אופטימיזציית המחיר אינה אמינה")
    if legal_cap > 0 and current_price > legal_cap:
        warnings.append("המחיר חורג מתקרת המחיר שהוזנה")
    if abs(best_price - price_max) < step / 2:
        warnings.append("המחיר המיטבי נמצא בגבול העליון של הטווח; הרחיבו את הטווח או אמתו את הנחת האלסטיות")
    elif abs(best_price - price_min) < step / 2:
        warnings.append("המחיר המיטבי נמצא בגבול התחתון של הטווח; הרחיבו את הטווח או אמתו את הנחת האלסטיות")

    cost_stack = [
        {"name": "ייצור", "value": round(max(0.0, num(row.get("manufacturing_cost_lc"))), 4)},
        {"name": "רכיב X", "value": round(max(0.0, num(row.get("component_cost_lc"))), 4)},
        {"name": "הובלה", "value": round(max(0.0, num(row.get("freight_cost_lc"))), 4)},
        {"name": "מכירה משתנה", "value": round(max(0.0, num(row.get("variable_selling_cost_lc"))), 4)},
        {"name": "סיכון מלאי", "value": round(max(0.0, num(row.get("inventory_risk_cost_lc"))), 4)},
        {"name": "עלות אחרת", "value": round(max(0.0, num(row.get("other_variable_cost_lc"))), 4)},
        {"name": "אשראי/חדלות פירעון", "value": round(num(current.get("credit_cost_per_unit_lc")), 4)},
    ]

    return {
        "current": current,
        "price_floors": {
            "cash_floor_lc": round(_round_to_step(cash_floor, step), 4),
            "operating_break_even_price_lc": round(_round_to_step(break_even_price, step), 4),
            "target_margin_price_lc": round(_round_to_step(target_margin_price, step), 4),
        },
        "recommendation": {
            "action": recommendation,
            "recommended_price_lc": round(best_price, 4),
            "safe_range_low_lc": round(safe_low, 4),
            "safe_range_high_lc": round(safe_high, 4),
            "expected_operating_profit_lc": round(max_profit, 2),
            "expected_units_sold": num(best.get("units_sold")),
            "expected_ending_inventory": num(best.get("ending_inventory")),
        },
        "cost_stack": cost_stack,
        "pricing_grid": grid,
        "warnings": warnings,
        "model_note": "הביקוש מחושב סביב מחיר וביקוש בסיס שהוזנו, באמצעות אלסטיות קבועה. יש לעדכן את ההנחות בכל רבעון לפי מחקרי שוק ותוצאות בפועל.",
    }

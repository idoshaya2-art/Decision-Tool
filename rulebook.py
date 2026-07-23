from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Iterable

from intopia_rules import (
    AREA_CURRENCIES,
    BASELINE_FX_TO_SF,
    DECISION_ACTIONS,
    FX_COMMISSION,
    INITIAL_STANDARD_PRICE_LC,
    MINIMUM_PRICE_STEP_LC,
    MINIMUM_RD_SF,
    PLANT_CAPACITY,
    PLANT_COST_LC,
    X_Y_CONVERSION,
    compatible_x_units,
    decision_action,
)


RULEBOOK_VERSION = "1.3.0"
RULEBOOK_STATUS = "approved_baseline"

AREA_ALIASES = {
    "us": "USA",
    "usa": "USA",
    "u.s.": "USA",
    "united states": "USA",
    "eu": "Europe",
    "ec/eu": "Europe",
    "europe": "Europe",
    "brazil": "Brazil",
    "brasil": "Brazil",
    "liechtenstein": "Liechtenstein",
    "home office": "Liechtenstein",
    "ho": "Liechtenstein",
}


RULE_SOURCES: list[dict[str, Any]] = [
    {
        "source_id": "game_admin_current",
        "name": "Current game administrator instructions",
        "source_type": "game_admin",
        "priority": 1,
        "status": "awaiting_documents",
        "version_label": "current run",
        "notes": "Highest-priority source. New instructions require human review before activation.",
    },
    {
        "source_id": "data_log_v1",
        "name": "Data Log v1",
        "source_type": "official_datalog",
        "priority": 2,
        "status": "approved",
        "version_label": "v1",
        "notes": "Official cost, charge, conversion and time-lag baseline for the current game.",
    },
    {
        "source_id": "intopia_ui",
        "name": "INTOPIA decision forms and UI constraints",
        "source_type": "official_interface",
        "priority": 3,
        "status": "approved",
        "version_label": "Q1-Q3 observed",
        "notes": "Decision-form availability, required fields and UI limits observed in the current run.",
    },
    {
        "source_id": "quarterly_actuals",
        "name": "Official quarterly result workbooks",
        "source_type": "official_results",
        "priority": 4,
        "status": "approved",
        "version_label": "Q1-Q3",
        "notes": "Actual results and current-quarter parameters override baseline values where applicable.",
    },
    {
        "source_id": "course_helper",
        "name": "Course helper booklet",
        "source_type": "course_document",
        "priority": 5,
        "status": "approved",
        "version_label": "current course",
        "notes": "Q9 targets, market-research catalog, contracts and final-report requirements.",
    },
    {
        "source_id": "opening_presentation",
        "name": "Opening course presentation",
        "source_type": "course_presentation",
        "priority": 5,
        "status": "approved",
        "version_label": "current course",
        "notes": "Evaluation framework and explicit warning that parameters differ between game runs.",
    },
    {
        "source_id": "market_research",
        "name": "Purchased market research in current run",
        "source_type": "market_research",
        "priority": 6,
        "status": "dynamic",
        "version_label": "by quarter",
        "notes": "Evidence, not a hard rule. Only approved research results may affect recommendations.",
    },
    {
        "source_id": "approved_contract",
        "name": "Approved inter-company contracts",
        "source_type": "contract",
        "priority": 7,
        "status": "dynamic",
        "version_label": "by contract",
        "notes": "Contract terms apply only after team approval and source-file retention.",
    },
    {
        "source_id": "team_strategy",
        "name": "Approved team strategy and red lines",
        "source_type": "strategy",
        "priority": 8,
        "status": "dynamic",
        "version_label": "versioned",
        "notes": "Strategy constraints cannot override official hard rules.",
    },
    {
        "source_id": "system_inference",
        "name": "System inference and calibrated assumptions",
        "source_type": "inference",
        "priority": 9,
        "status": "dynamic",
        "version_label": "model run",
        "notes": "Never treated as a rule or an Actual.",
    },
]


def _rule(
    rule_id: str,
    name_he: str,
    name_en: str,
    knowledge_type: str,
    domain: str,
    *,
    source_id: str = "data_log_v1",
    source_page: str = "",
    pdf_page: int | None = None,
    enforcement: str = "warning",
    condition: dict[str, Any] | None = None,
    effect: dict[str, Any] | None = None,
    areas: Iterable[str] = (),
    products: Iterable[str] = (),
    quarters: Iterable[str] = (),
    units: str = "",
    currency: str = "",
    exceptions: Iterable[str] = (),
    dependencies: Iterable[str] = (),
    confidence: str = "high",
    description: str = "",
) -> dict[str, Any]:
    return {
        "rule_id": rule_id,
        "version": RULEBOOK_VERSION,
        "name_he": name_he,
        "name_en": name_en,
        "knowledge_type": knowledge_type,
        "domain": domain,
        "areas": list(areas),
        "products": list(products),
        "quarters": list(quarters),
        "condition": condition or {},
        "effect": effect or {},
        "units": units,
        "currency": currency,
        "exceptions": list(exceptions),
        "dependencies": list(dependencies),
        "source_id": source_id,
        "source_page": source_page,
        "pdf_page": pdf_page,
        "source_section": "",
        "confidence": confidence,
        "enforcement": enforcement,
        "approval_status": "approved",
        "effective_from": "Q1",
        "effective_to": "Q9",
        "description": description,
        "test_cases": [],
    }


BASE_RULES: list[dict[str, Any]] = [
    _rule(
        "DL-FX-BASELINE",
        "שערי חליפין בסיסיים",
        "Baseline exchange rates",
        "Parameter",
        "finance",
        source_page="54",
        pdf_page=1,
        condition={"current_quarter_rate_available": False},
        effect={"fx_to_sf": BASELINE_FX_TO_SF, "override": "Currency sheet or Gazette"},
        units="SF per local currency",
        description="Baseline only. Current-quarter official Currency output overrides these values.",
    ),
    _rule(
        "DL-XY-COMPATIBILITY",
        "התאמת רמות X–Y",
        "X–Y grade compatibility",
        "Hard Rule",
        "production",
        source_page="54",
        pdf_page=1,
        enforcement="block",
        condition={"action_type": "production", "product": "Y"},
        effect={"conversion_table": [list(row) for row in X_Y_CONVERSION], "zero_means": "incompatible"},
        products=("X", "Y"),
        units="X units per Y unit",
        description="A Y unit may only use a compatible X grade and the required component quantity.",
    ),
    _rule(
        "DL-PLANT-CAPACITY",
        "קיבולת מרבית למפעל",
        "Maximum plant capacity",
        "Parameter",
        "production",
        source_page="55",
        pdf_page=2,
        enforcement="block",
        effect={"capacity_per_plant": PLANT_CAPACITY},
        areas=("USA", "Europe", "Brazil"),
        products=("X", "Y"),
        units="units per quarter",
    ),
    _rule(
        "DL-PLANT-COST",
        "עלות רכישת מפעל",
        "Plant acquisition cost",
        "Parameter",
        "production",
        source_page="55",
        pdf_page=2,
        effect={"cost_lc": PLANT_COST_LC},
        areas=("USA", "Europe", "Brazil"),
        products=("X", "Y"),
        units="local currency",
    ),
    _rule(
        "DL-PLANT-CASH-PAYMENT",
        "מפעל משולם במזומן ברבעון ההקמה",
        "Plant is paid in cash in construction quarter",
        "Hard Rule",
        "finance",
        source_page="55",
        pdf_page=2,
        enforcement="block",
        condition={"action_type": "plant_construction"},
        effect={"cash_timing": "current_quarter", "production_start": "next_quarter"},
        dependencies=("DL-PLANT-LAG",),
    ),
    _rule(
        "UI-MAX-THREE-PLANTS",
        "עד שלושה מפעלים למוצר באזור",
        "Maximum three plants per product and area",
        "Decision Constraint",
        "production",
        source_id="intopia_ui",
        source_page="A2-1",
        enforcement="block",
        condition={"action_type": "plant_construction"},
        effect={"maximum_plants": 3},
        areas=("USA", "Europe", "Brazil"),
        products=("X", "Y"),
    ),
    _rule(
        "DL-PRICE-BASELINE",
        "מחירי צרכן התחלתיים",
        "Initial standard consumer prices",
        "Parameter",
        "marketing",
        source_page="56",
        pdf_page=3,
        effect={"initial_standard_price_lc": INITIAL_STANDARD_PRICE_LC},
        units="local currency per unit",
    ),
    _rule(
        "DL-PRICE-STEP",
        "מדרגת שינוי מחיר מינימלית",
        "Minimum permissible price step",
        "Decision Constraint",
        "pricing",
        source_page="56",
        pdf_page=3,
        enforcement="block",
        condition={"action_type": "price_advertising"},
        effect={"minimum_step_lc": MINIMUM_PRICE_STEP_LC},
        areas=("USA", "Europe", "Brazil"),
        products=("X", "Y"),
        units="local currency",
    ),
    _rule(
        "DL-Y03-PRICE-CAP",
        "תקרת מחיר למחשבי Y0–Y3",
        "Maximum price for Y0–Y3",
        "Hard Rule",
        "pricing",
        source_page="56",
        pdf_page=3,
        enforcement="block",
        condition={"product": "Y", "grade_lte": 3},
        effect={"maximum_price_lc": 1400},
        products=("Y",),
        units="local currency",
    ),
    _rule(
        "DL-SALES-OFFICE-RANGE",
        "טווח משרדי מכירות",
        "Captive sales office range",
        "Decision Constraint",
        "marketing",
        source_page="56",
        pdf_page=3,
        enforcement="block",
        effect={"minimum": {"central": 1, "regional": 1}, "maximum": {"central": 1, "regional": 9}},
    ),
    _rule(
        "DL-FREIGHT-COST",
        "עלויות הובלה לפי מסלול ונפח",
        "Freight cost by route and volume",
        "Formula",
        "logistics",
        source_page="57",
        pdf_page=4,
        condition={"action_types": ["component_transfer", "industrial_sale"]},
        effect={"surface_discount_above_breakpoint": 0.50, "air_discount_above_breakpoint": 1 / 3},
        units="shipper local currency per unit",
        description="High-volume discount applies to each individual shipment.",
    ),
    _rule(
        "DL-INVENTORY-CARRYING",
        "עלות אחזקת מלאי",
        "Inventory carrying charge",
        "Formula",
        "inventory",
        source_page="57",
        pdf_page=4,
        effect={
            "minimum_lc_per_unit": {
                "USA": {"X": 1, "Y": 10},
                "Europe": {"X": 0.8, "Y": 8},
                "Brazil": {"X": 1, "Y": 16},
            },
            "current_quarter_production_exempt": True,
            "unsold_airfreight_charged": True,
        },
        units="local currency per unit",
    ),
    _rule(
        "DL-RD-MINIMUM",
        "השקעת מו״פ מינימלית",
        "Minimum R&D investment",
        "Decision Constraint",
        "technology",
        source_page="57",
        pdf_page=4,
        enforcement="block",
        condition={"action_type": "rd", "amount_gt": 0},
        effect={"minimum_sf": MINIMUM_RD_SF},
        products=("X", "Y"),
        units="SF per quarter",
    ),
    _rule(
        "DL-TAX-RATES",
        "שיעורי מס חברות",
        "Corporation tax rates",
        "Parameter",
        "finance",
        source_page="58",
        pdf_page=5,
        effect={"tax_rate": {"USA": 0.50, "Europe": 0.40, "Brazil": 0.30, "Liechtenstein": 0.15}},
        units="rate",
    ),
    _rule(
        "DL-LOSS-CARRYFORWARD",
        "קיזוז הפסד לרבעון אחד",
        "One-quarter operating loss carryforward",
        "Formula",
        "finance",
        source_page="58",
        pdf_page=5,
        effect={"one_quarter_rate": {"USA": 0.60, "Europe": 0.30, "Brazil": 0.0, "Liechtenstein": 1.0}},
        units="share of operating loss",
    ),
    _rule(
        "DL-AREA-BANK-RATES",
        "ריבית הלוואות והשקעות אזוריות",
        "Area loan and security rates",
        "Parameter",
        "finance",
        source_page="58",
        pdf_page=5,
        effect={
            "loan_rate": {"USA": 0.040, "Europe": 0.035, "Brazil": 0.060},
            "security_rate": {"USA": 0.020, "Europe": 0.015, "Brazil": 0.045},
            "explicit_renewal_required": True,
        },
        units="quarterly rate",
    ),
    _rule(
        "DL-HO-FINANCE-RATES",
        "ריבית מימון במטה",
        "Home Office finance rates",
        "Parameter",
        "finance",
        source_page="58",
        pdf_page=5,
        effect={
            "minimum_loan_rate": {"BRL": 0.065, "other": 0.055},
            "security_rate": {"CHF": 0.020, "EUR": 0.020, "USD": 0.0225, "BRL": 0.030},
            "explicit_renewal_required": True,
        },
        units="quarterly rate",
    ),
    _rule(
        "DL-FX-COMMISSION",
        "עמלת המרת מטבע",
        "Foreign-exchange commission",
        "Formula",
        "finance",
        source_page="58",
        pdf_page=5,
        effect={"commission_rate": FX_COMMISSION},
        units="share of converted amount",
    ),
    _rule(
        "DL-PLANT-LAG",
        "הקמת מפעל נכנסת לייצור ברבעון הבא",
        "Plant construction to production lag",
        "Time Lag",
        "production",
        source_page="59",
        pdf_page=6,
        enforcement="block",
        condition={"action_type": "plant_construction"},
        effect={"production_available_after_quarters": 1},
    ),
    _rule(
        "DL-PRODUCTION-SALES-LAG",
        "ייצור נמכר רק מהרבעון הבא",
        "Production-to-sale lag",
        "Time Lag",
        "production",
        source_page="59",
        pdf_page=6,
        enforcement="block",
        condition={"action_type": "production"},
        effect={"consumer_sale_available_after_quarters": 1},
    ),
    _rule(
        "DL-SURFACE-TRANSFER-LAG",
        "העברה רגילה אורכת רבעון",
        "Surface transfer lag",
        "Time Lag",
        "logistics",
        source_page="59",
        pdf_page=6,
        enforcement="block",
        condition={"transport_mode": "surface"},
        effect={"arrival_after_quarters": 1, "same_quarter_use": False},
    ),
    _rule(
        "DL-AIRFREIGHT-SAME-Q",
        "הובלה אווירית מאפשרת שימוש באותו רבעון",
        "Airfreight permits same-quarter use",
        "Decision Constraint",
        "logistics",
        source_page="59",
        pdf_page=6,
        condition={"transport_mode": "air"},
        effect={"same_quarter_resale": True, "second_airfreight": False},
        exceptions=("Goods may not be airfreighted a second time in the same quarter.",),
    ),
    _rule(
        "DL-BRAZIL-PLANT-DEPOSIT",
        "פיקדון ממשלתי למפעל חדש בברזיל",
        "Brazil new-plant government deposit",
        "Hard Rule",
        "finance",
        source_page="59",
        pdf_page=6,
        enforcement="block",
        condition={"action_type": "plant_construction", "area": "Brazil", "quarters": ["Q1", "Q2", "Q3"]},
        effect={"deposit_brl_per_plant": 1_000_000, "redeposit_through": "Q3"},
        areas=("Brazil",),
        quarters=("Q1", "Q2", "Q3"),
        units="BRL per plant",
    ),
    _rule(
        "DL-LICENSE-LAG",
        "תזמון רישיון פטנט",
        "Patent-license timing",
        "Hard Rule",
        "technology",
        source_page="59",
        pdf_page=6,
        enforcement="block",
        condition={"action_type": "grade_license"},
        effect={"licensor_wait_quarters": 1, "licensee_wait_quarters": 1, "minimum_license_quarters": 2},
    ),
    _rule(
        "DL-AR-ROUTINE",
        "פריסת תקבולי מכירות לצרכן",
        "Consumer-sales receivables routine",
        "Formula",
        "finance",
        source_page="60",
        pdf_page=7,
        effect={
            "USA": {"cash": 0.40, "ar1": 0.60, "ar2": 0.0},
            "Europe": {"cash": 0.50, "ar1": 0.20, "ar2": 0.30},
            "Brazil": {"cash": 0.30, "ar1": 0.30, "ar2": 0.40},
        },
        units="share of revenue",
    ),
    _rule(
        "DL-AP-ROUTINE",
        "סיווג זכאים ותשלום הוצאות",
        "Accounts-payable routine",
        "Formula",
        "finance",
        source_page="60",
        pdf_page=7,
        effect={
            "taxes_to": "AP1",
            "variable_manufacturing_to": "local AP routine",
            "fixed_plant_expense_to": "cash",
            "other_expense_to": "cash",
        },
    ),
    _rule(
        "DL-AD-METHODS-EFFECT",
        "השפעה מיידית ודועכת לפרסום ולשיפור שיטות",
        "Advertising and methods timing",
        "Time Lag",
        "marketing",
        source_page="60",
        pdf_page=7,
        effect={"major_effect": "current_quarter", "future_effect": "diminishing"},
    ),
    _rule(
        "COURSE-MR-CATALOG",
        "קטלוג מחקרי השוק",
        "Market-research catalog",
        "Market Research Definition",
        "research",
        source_id="course_helper",
        source_page="4–6",
        pdf_page=4,
        effect={"catalog": "market_research_catalog table", "cost_unit": "thousand SF"},
    ),
    _rule(
        "UI-MR-MAX-THREE",
        "עד שלושה מחקרי שוק ברבעון",
        "Maximum three market-research studies per quarter",
        "Decision Constraint",
        "research",
        source_id="intopia_ui",
        source_page="H1-2",
        enforcement="block",
        condition={"action_type": "market_research"},
        effect={"maximum_per_quarter": 3},
    ),
    _rule(
        "COURSE-Q9-TARGETS",
        "יעדי החברה לסוף Q9",
        "Required Q9 targets",
        "Strategy Constraint",
        "strategy",
        source_id="course_helper",
        source_page="2",
        pdf_page=2,
        effect={"required_targets": ["X/Y grades", "market share by product and market", "sales units and SF", "revenue and profit"]},
    ),
    _rule(
        "COURSE-SCORE-50-50",
        "הערכת סוף המשחק: 50% עבר ו־50% עתיד",
        "End-game evaluation: 50% past and 50% future",
        "Formula",
        "strategy",
        source_id="opening_presentation",
        source_page="60",
        pdf_page=60,
        effect={
            "past_weight": 0.50,
            "future_weight": 0.50,
            "past_metrics": ["net profit", "ROS", "ROI", "ROE"],
            "future_metrics": ["technology", "segments and market share vs capacity", "trends", "reputation", "partnerships", "ethics"],
            "internal_subweights_official": False,
        },
    ),
    _rule(
        "COURSE-RUN-SPECIFIC",
        "אין לייבא פרמטרים ממשחקים אחרים",
        "Do not import parameters from other runs",
        "Hard Rule",
        "governance",
        source_id="opening_presentation",
        source_page="course warning",
        enforcement="block",
        effect={"allowed_external_parameter_sources": []},
        description="Parameters vary between simulations; internet and past games are not official inputs.",
    ),
]


FORM_RULES: list[dict[str, Any]] = [
    _rule(
        f"FORM-{item['code']}",
        f"טופס החלטה {item['code']}",
        f"Decision form {item['code']}",
        "Decision Constraint",
        str(item.get("category") or "decision"),
        source_id="intopia_ui",
        source_page=str(item["code"]),
        enforcement="block",
        condition={"decision_code": item["code"], "action_type": item.get("type")},
        effect={
            "required_fields": list(item.get("fields") or []),
            "available_areas": list(item.get("areas") or []),
            "fixed_product": item.get("product"),
            "timing": item.get("timing", ""),
        },
        areas=item.get("areas") or (),
        products=(item["product"],) if item.get("product") else (),
    )
    for item in DECISION_ACTIONS
]


CANONICAL_RULES: list[dict[str, Any]] = BASE_RULES + FORM_RULES
RULE_INDEX = {rule["rule_id"]: rule for rule in CANONICAL_RULES}


def normalize_area(value: Any) -> str:
    text = str(value or "").strip()
    return AREA_ALIASES.get(text.lower(), text)


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value if value not in (None, "") else default)
    except (TypeError, ValueError):
        return default


def _quarter_number(value: Any) -> int:
    text = str(value or "").strip().upper()
    return int(text[1:]) if len(text) == 2 and text.startswith("Q") and text[1:].isdigit() else 0


def rule_citation(rule: dict[str, Any]) -> dict[str, Any]:
    source = next((row for row in RULE_SOURCES if row["source_id"] == rule.get("source_id")), {})
    return {
        "rule_id": rule.get("rule_id"),
        "name": rule.get("name_he") or rule.get("name_en"),
        "source_id": rule.get("source_id"),
        "source": source.get("name", rule.get("source_id")),
        "page": rule.get("source_page"),
        "pdf_page": rule.get("pdf_page"),
        "version": rule.get("version"),
        "knowledge_type": rule.get("knowledge_type"),
        "enforcement": rule.get("enforcement"),
    }


@dataclass
class RuleCheck:
    rule_id: str
    status: str
    message: str
    blocking: bool = False
    field: str = ""
    remediation: str = ""

    def as_dict(self) -> dict[str, Any]:
        rule = RULE_INDEX.get(self.rule_id, {})
        return {
            "rule_id": self.rule_id,
            "status": self.status,
            "message": self.message,
            "blocking": self.blocking,
            "field": self.field,
            "remediation": self.remediation,
            "citation": rule_citation(rule) if rule else {},
        }


def _action_operations(action: dict[str, Any], operations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    area = normalize_area(action.get("area"))
    product = str(action.get("product") or "")
    model = str(action.get("model") or "")
    return [
        row
        for row in operations
        if (not area or normalize_area(row.get("area")) == area)
        and (not product or str(row.get("product") or "") == product)
        and (not model or str(row.get("model") or "") == model)
    ]


def evaluate_action(
    action: dict[str, Any],
    *,
    quarter: str,
    operations: list[dict[str, Any]] | None = None,
    strict: bool = False,
) -> list[dict[str, Any]]:
    operations = operations or []
    checks: list[RuleCheck] = []
    code = str(action.get("code") or "")
    catalog = decision_action(code)
    action_type = str(action.get("type") or catalog.get("type") or "")
    area = normalize_area(action.get("area"))
    product = str(action.get("product") or catalog.get("product") or "")
    grade = int(_number(action.get("grade"), -1))
    matching = _action_operations({**action, "area": area, "product": product}, operations)

    # Values that may never be negative in an INTOPIA decision.  This check is
    # intentionally performed before type-specific calculations so invalid
    # inputs cannot be silently normalised with max(0, value).
    nonnegative_fields = {
        "units",
        "price_lc",
        "price_sf",
        "advertising_lc",
        "cost_sf",
        "variable_cost_sf",
        "amount_sf",
        "final_payment_sf",
        "interest_rate",
        "plant_count",
        "brazil_deposit_brl",
        "available_x_units",
        "available_inventory_units",
    }
    for field in sorted(nonnegative_fields):
        if action.get(field) not in (None, "") and _number(action.get(field)) < 0:
            checks.append(
                RuleCheck(
                    f"FORM-{code}" if catalog else "COURSE-RUN-SPECIFIC",
                    "fail",
                    f"השדה {field} אינו יכול להיות שלילי.",
                    True,
                    field,
                    "הזינו ערך אפס או ערך חיובי בהתאם לטופס הרשמי.",
                )
            )

    if code and not catalog:
        checks.append(RuleCheck("COURSE-RUN-SPECIFIC", "fail", f"קוד החלטה לא מוכר: {code}.", True, "code", "בחרו טופס מהקטלוג הרשמי."))
    if catalog:
        allowed_areas = [normalize_area(value) for value in catalog.get("areas", [])]
        if area and allowed_areas and area not in allowed_areas:
            checks.append(RuleCheck(f"FORM-{code}", "fail", f"הטופס {code} אינו זמין באזור {area}.", True, "area", "בחרו אזור חוקי לטופס."))
        fixed_product = str(catalog.get("product") or "")
        if product and fixed_product and product != fixed_product:
            checks.append(RuleCheck(f"FORM-{code}", "fail", f"הטופס {code} מיועד למוצר {fixed_product}.", True, "product", f"שנו את המוצר ל-{fixed_product}."))
        if strict:
            ignored_required = {"cost_sf"}
            missing = [
                field
                for field in catalog.get("fields", [])
                if field not in ignored_required and action.get(field) in (None, "")
            ]
            if missing:
                checks.append(
                    RuleCheck(
                        f"FORM-{code}",
                        "fail",
                        "חסרים שדות חובה: " + ", ".join(missing),
                        True,
                        ",".join(missing),
                        "השלימו את השדות לפני יצירת חבילת ההחלטות.",
                    )
                )

    if action_type == "plant_construction":
        plants = _number(action.get("plant_count"), 1)
        if strict and plants <= 0:
            checks.append(RuleCheck(f"FORM-{code}", "fail", "הקמת מפעל מחייבת מספר מפעלים גדול מאפס.", True, "plant_count", "הזינו לפחות מפעל אחד או הסירו את הפעולה מהחבילה."))
        existing = max((_number(row.get("plants")) for row in matching), default=0.0)
        if existing + plants > 3:
            checks.append(RuleCheck("UI-MAX-THREE-PLANTS", "fail", f"לאחר הפעולה יהיו {existing + plants:g} מפעלים; המקסימום הוא 3.", True, "plant_count", "הקטינו את מספר המפעלים או בחרו אזור אחר."))
        if area == "Brazil" and 1 <= _quarter_number(quarter) <= 3:
            deposit = plants * 1_000_000
            declared = _number(action.get("brazil_deposit_brl"))
            if declared + 0.01 < deposit:
                checks.append(RuleCheck("DL-BRAZIL-PLANT-DEPOSIT", "fail", f"נדרש פיקדון של {deposit:,.0f} BRL למפעלים החדשים.", True, "brazil_deposit_brl", "הוסיפו את הפיקדון לתקציב ולפעולה."))
        checks.append(RuleCheck("DL-PLANT-LAG", "pass", "המפעל יוכל לייצר החל מהרבעון הבא."))

    if action_type == "production":
        units = _number(action.get("units"))
        if strict and units <= 0:
            checks.append(RuleCheck(f"FORM-{code}", "fail", "פעולת ייצור מחייבת כמות גדולה מאפס.", True, "units", "הזינו כמות ייצור חיובית או הסירו את הפעולה מהחבילה."))
        capacity = sum(_number(row.get("plant_capacity")) for row in matching)
        capacity_known = any(row.get("plant_capacity") not in (None, "") for row in matching)
        if strict and units > 0 and not capacity_known:
            checks.append(RuleCheck("DL-PLANT-CAPACITY", "fail", "לא ניתן לאשר ייצור ללא נתון קיבולת מאושר לאזור, למוצר ולדגם.", True, "units", "אשרו את דוח הרבעון או השלימו את נתון הקיבולת לפני יצירת החבילה."))
        if capacity and units > capacity + 0.01:
            checks.append(RuleCheck("DL-PLANT-CAPACITY", "fail", f"הייצור המתוכנן {units:,.0f} גבוה מהקיבולת הזמינה {capacity:,.0f}.", True, "units", "הקטינו ייצור או הפעילו קיבולת חוקית שכבר נכנסה לתוקף."))
        if product == "Y":
            x_grade = int(_number(action.get("x_grade"), -1))
            if grade >= 0 and x_grade >= 0:
                required = compatible_x_units(x_grade, grade)
                if required == 0:
                    checks.append(RuleCheck("DL-XY-COMPATIBILITY", "fail", f"X{x_grade} אינו תואם לייצור Y{grade}.", True, "x_grade", "בחרו רמת X תואמת לפי טבלת ההמרה."))
                else:
                    explicit_available_x = action.get("available_x_units") not in (None, "")
                    x_rows = [
                        row
                        for row in operations
                        if normalize_area(row.get("area")) == area
                        and str(row.get("product") or "") == "X"
                        and (
                            x_grade < 0
                            or int(_number(row.get("grade"), -1)) == x_grade
                        )
                    ]
                    x_inventory_known = any(row.get("ending_inventory") not in (None, "") for row in x_rows)
                    available_x = (
                        _number(action.get("available_x_units"))
                        if explicit_available_x
                        else sum(_number(row.get("ending_inventory")) for row in x_rows)
                    )
                    required_x = units * required
                    if strict and units > 0 and not explicit_available_x and not x_inventory_known:
                        checks.append(RuleCheck("DL-XY-COMPATIBILITY", "fail", "לא ניתן לאשר ייצור Y ללא מלאי X מאושר וזמין בזמן.", True, "available_x_units", "אשרו מלאי X לפי רמה או הגדירו אספקת X חוקית לפני ייצור Y."))
                    elif (explicit_available_x or x_inventory_known) and available_x + 0.01 < required_x:
                        checks.append(RuleCheck("DL-XY-COMPATIBILITY", "fail", f"נדרשות {required_x:,.0f} יחידות X{x_grade}, אך הוגדרו {available_x:,.0f}.", True, "available_x_units", "הקטינו ייצור Y או ספקו X תואם בזמן."))
            elif strict:
                checks.append(RuleCheck("DL-XY-COMPATIBILITY", "fail", "ייצור Y מחייב ציון רמת X ורמת Y.", True, "x_grade,grade", "הגדירו את שתי הרמות."))
        if action.get("same_quarter_sales"):
            checks.append(RuleCheck("DL-PRODUCTION-SALES-LAG", "fail", "מוצר שיוצר ברבעון הנוכחי אינו יכול להימכר לצרכן באותו רבעון.", True, "same_quarter_sales", "העבירו את המכירה לרבעון הבא."))

    if action_type in {"price_advertising", "price_change"}:
        price = _number(action.get("price_lc"))
        if price <= 0:
            checks.append(RuleCheck(f"FORM-{code}" if code else "DL-PRICE-BASELINE", "fail", "מחיר מכירה חייב להיות גדול מאפס.", True, "price_lc", "הזינו מחיר חוקי וחיובי במטבע המקומי."))
        if product == "Y" and 0 <= grade <= 3 and price > 1400:
            checks.append(RuleCheck("DL-Y03-PRICE-CAP", "fail", f"מחיר {price:,.0f} חורג מתקרת 1,400 לרמות Y0–Y3.", True, "price_lc", "הורידו את המחיר ל-1,400 או פחות."))
        previous = _number(action.get("current_price_lc"))
        if area and product and price > 0 and previous > 0:
            step = _number(MINIMUM_PRICE_STEP_LC.get(area, {}).get(product))
            difference = abs(price - previous)
            if step and difference > 0 and abs(difference / step - round(difference / step)) > 1e-8:
                checks.append(RuleCheck("DL-PRICE-STEP", "fail", f"שינוי המחיר חייב להיות במדרגות של {step:g} במטבע המקומי.", True, "price_lc", "עגלו את השינוי למדרגת המחיר החוקית."))

    if action_type == "rd":
        amount = max(_number(action.get("amount_sf")), _number(action.get("cost_sf")))
        if strict and amount <= 0:
            checks.append(RuleCheck(f"FORM-{code}", "fail", "פעולת מו״פ מחייבת השקעה חיובית.", True, "amount_sf", "הזינו השקעה חוקית או הסירו את הפעולה מהחבילה."))
        minimum = _number(MINIMUM_RD_SF.get(product))
        if amount > 0 and minimum and amount < minimum:
            checks.append(RuleCheck("DL-RD-MINIMUM", "fail", f"השקעת מו״פ ב-{product} חייבת להיות לפחות {minimum:,.0f} SF.", True, "amount_sf", f"הגדילו ל-{minimum:,.0f} SF לפחות או אל תשקיעו ברבעון זה."))

    transport_mode = str(action.get("transport_mode") or "").lower()
    if transport_mode in {"surface", "sea", "regular", "ימית", "רגילה"} and action.get("same_quarter_use"):
        checks.append(RuleCheck("DL-SURFACE-TRANSFER-LAG", "fail", "העברה רגילה מגיעה רק בסוף הרבעון ואינה זמינה לשימוש באותו רבעון.", True, "same_quarter_use", "עברו להובלה אווירית או דחו את השימוש."))
    if transport_mode in {"air", "airfreight", "אווירית"} and action.get("second_airfreight"):
        checks.append(RuleCheck("DL-AIRFREIGHT-SAME-Q", "fail", "לא ניתן לבצע הובלה אווירית שנייה לאותן יחידות באותו רבעון.", True, "second_airfreight", "השתמשו או מכרו ללא הובלה אווירית נוספת."))

    if action_type == "grade_license":
        license_amount = max(
            _number(action.get("amount_sf")),
            _number(action.get("cost_sf")),
        )
        if strict and license_amount <= 0:
            checks.append(
                RuleCheck(
                    f"FORM-{code}",
                    "fail",
                    "רישיון לרמה טכנולוגית מחייב תמורה חיובית.",
                    True,
                    "amount_sf",
                    "הזינו סכום רישיון מאושר או הסירו את הפעולה.",
                )
            )
        duration = int(_number(action.get("license_quarters"), 0))
        if duration and duration < 2:
            checks.append(RuleCheck("DL-LICENSE-LAG", "fail", "תקופת רישיון מינימלית היא שני רבעונים.", True, "license_quarters", "הגדילו את התקופה לשני רבעונים לפחות."))
        obtained_q = _quarter_number(action.get("licensor_obtained_quarter"))
        current_q = _quarter_number(quarter)
        if obtained_q and current_q <= obtained_q:
            checks.append(RuleCheck("DL-LICENSE-LAG", "fail", "ניתן להעניק רישיון רק רבעון לאחר שהמעניק קיבל את הרמה.", True, "licensor_obtained_quarter", "דחו את הרישיון לרבעון הבא."))

    if action_type in {"currency_conversion", "local_currency_exchange"} and area:
        local_currency = AREA_CURRENCIES.get(area)
        source_currency = str(action.get("currency") or "")
        if action_type == "local_currency_exchange" and local_currency and source_currency == local_currency:
            checks.append(RuleCheck(f"FORM-{code}" if code else "DL-FX-COMMISSION", "fail", f"לא ניתן למכור לבנק המקומי את המטבע המקומי {local_currency}.", True, "currency", "בחרו מטבע זר להמרה."))

    positive_amount_types = {
        "money_transfer",
        "invest_borrow",
        "currency_conversion",
        "local_currency_exchange",
        "home_office_finance",
        "intercompany_loan",
        "services_payment",
    }
    if strict and action_type in positive_amount_types and _number(action.get("amount_sf")) <= 0:
        checks.append(RuleCheck(f"FORM-{code}", "fail", "הפעולה מחייבת סכום גדול מאפס.", True, "amount_sf", "הזינו סכום חיובי או הסירו את הפעולה מהחבילה."))

    if action_type == "market_research":
        raw_study_id = action.get("study_id")
        study_id = int(_number(raw_study_id, -1))
        if (
            isinstance(raw_study_id, bool)
            or study_id < 1
            or study_id > 81
            or str(raw_study_id).strip() not in {str(study_id), f"{study_id}.0"}
        ):
            checks.append(
                RuleCheck(
                    f"FORM-{code}",
                    "fail",
                    "מזהה מחקר השוק אינו חוקי; נדרש מספר מחקר רשמי 1–81.",
                    True,
                    "study_id",
                    "בחרו את המחקר מתוך קטלוג מחקרי השוק המאושר.",
                )
            )
        if strict and _number(action.get("cost_sf")) <= 0:
            checks.append(
                RuleCheck(
                    f"FORM-{code}",
                    "fail",
                    "מחקר שוק מחייב עלות מאושרת גדולה מאפס.",
                    True,
                    "cost_sf",
                    "טענו את העלות מהקטלוג המאושר לפני יצירת החבילה.",
                )
            )

    if action_type == "intercompany_loan":
        principal = _number(action.get("amount_sf"))
        final_payment = _number(action.get("final_payment_sf"))
        payment_quarter = _quarter_number(action.get("payment_quarter"))
        if strict and final_payment <= 0:
            checks.append(
                RuleCheck(
                    f"FORM-{code}",
                    "fail",
                    "הלוואה בין חברות מחייבת תשלום סופי חיובי.",
                    True,
                    "final_payment_sf",
                    "הזינו את סכום הפירעון המלא לפי ההסכם.",
                )
            )
        elif final_payment > 0 and principal > 0 and final_payment + 0.01 < principal:
            checks.append(
                RuleCheck(
                    f"FORM-{code}",
                    "fail",
                    "התשלום הסופי נמוך מקרן ההלוואה.",
                    True,
                    "final_payment_sf",
                    "הגדילו את התשלום הסופי לפחות לגובה הקרן או תקנו את סכום הקרן.",
                )
            )
        if strict and (
            payment_quarter <= _quarter_number(quarter)
            or payment_quarter > 9
        ):
            checks.append(
                RuleCheck(
                    f"FORM-{code}",
                    "fail",
                    "רבעון הפירעון חייב להיות לאחר הרבעון הנוכחי ועד Q9.",
                    True,
                    "payment_quarter",
                    "בחרו רבעון פירעון חוקי בטווח שנותר למשחק.",
                )
            )

    # Outgoing stock decisions must be backed by approved ending inventory.
    if action_type in {"component_transfer", "industrial_sale"}:
        units = _number(action.get("units"))
        explicit_inventory = action.get("available_inventory_units") not in (None, "")
        inventory_rows = [
            row
            for row in matching
            if grade < 0 or int(_number(row.get("grade"), -1)) == grade
        ]
        inventory_known = any(row.get("ending_inventory") not in (None, "") for row in inventory_rows)
        available_inventory = (
            _number(action.get("available_inventory_units"))
            if explicit_inventory
            else sum(_number(row.get("ending_inventory")) for row in inventory_rows)
        )
        if strict and units <= 0:
            checks.append(RuleCheck(f"FORM-{code}", "fail", "מכירה או העברה מחייבת כמות גדולה מאפס.", True, "units", "הזינו כמות חיובית או הסירו את הפעולה מהחבילה."))
        if strict and units > 0 and not explicit_inventory and not inventory_known:
            checks.append(RuleCheck("DL-INVENTORY-CARRYING", "fail", "לא ניתן לאשר מכירה או העברה ללא מלאי סופי מאושר.", True, "available_inventory_units", "אשרו את דוח המלאי או הגדירו מלאי זמין ממקור מאושר."))
        elif units > available_inventory + 0.01:
            checks.append(RuleCheck("DL-INVENTORY-CARRYING", "fail", f"הפעולה דורשת {units:,.0f} יחידות אך זמינות רק {available_inventory:,.0f}.", True, "units", f"הקטינו את הכמות ל-{available_inventory:,.0f} לכל היותר או הבטיחו אספקה חוקית מוקדמת יותר."))

    if action_type == "industrial_sale" and _number(action.get("price_lc")) <= 0:
        checks.append(RuleCheck(f"FORM-{code}", "fail", "מכירה תעשייתית מחייבת מחיר חיובי.", True, "price_lc", "הזינו מחיר עסקה חיובי במטבע המקומי."))

    if action_type == "factory_sale":
        plants = _number(action.get("plant_count"), 1)
        existing_plants = max((_number(row.get("plants")) for row in matching), default=0.0)
        plants_known = any(row.get("plants") not in (None, "") for row in matching)
        if strict and plants <= 0:
            checks.append(RuleCheck(f"FORM-{code}", "fail", "מכירת מפעל מחייבת מספר מפעלים גדול מאפס.", True, "plant_count", "הזינו לפחות מפעל אחד או הסירו את הפעולה."))
        if strict and plants > 0 and not plants_known:
            checks.append(RuleCheck("UI-MAX-THREE-PLANTS", "fail", "לא ניתן לאשר מכירת מפעל ללא מצב מפעלים מאושר.", True, "plant_count", "אשרו את מצב המפעלים בדוח הרבעוני."))
        elif plants > existing_plants + 0.01:
            checks.append(RuleCheck("UI-MAX-THREE-PLANTS", "fail", f"נבחרה מכירה של {plants:g} מפעלים אך קיימים רק {existing_plants:g}.", True, "plant_count", f"הקטינו את המכירה ל-{existing_plants:g} מפעלים לכל היותר."))
        if _number(action.get("price_lc")) <= 0:
            checks.append(RuleCheck(f"FORM-{code}", "fail", "מכירת מפעל מחייבת מחיר חיובי.", True, "price_lc", "הזינו מחיר עסקה חיובי במטבע המקומי."))

    return [check.as_dict() for check in checks]


def evaluate_portfolio(
    actions: list[dict[str, Any]],
    *,
    quarter: str,
    operations: list[dict[str, Any]] | None = None,
    available_budget_sf: float = 0.0,
    base_cash_sf: float = 0.0,
    cash_buffer_sf: float = 0.0,
    strict: bool = False,
) -> dict[str, Any]:
    operations = operations or []
    checks = [
        check
        for action in actions
        for check in evaluate_action(action, quarter=quarter, operations=operations, strict=strict)
    ]
    if strict and not actions:
        checks.append(
            RuleCheck(
                "COURSE-RUN-SPECIFIC",
                "fail",
                "חבילת החלטות ריקה אינה מוכנה להגשה.",
                True,
                "actions",
                "הוסיפו לפחות פעולה אחת שנבדקה ואושרה.",
            ).as_dict()
        )
    total_cost = sum(max(0.0, _number(action.get("cost_sf"))) for action in actions)
    total_cost += sum(
        max(0.0, _number(action.get("brazil_deposit_brl"))) * BASELINE_FX_TO_SF["Brazil"]
        for action in actions
        if normalize_area(action.get("area")) == "Brazil"
    )
    if total_cost > available_budget_sf + 0.01:
        checks.append(
            RuleCheck(
                "DL-PLANT-CASH-PAYMENT",
                "fail",
                f"עלות חבילת הפעולות {total_cost:,.0f} SF גבוהה מהתקציב הזמין {available_budget_sf:,.0f} SF.",
                True,
                "cost_sf",
                "הסירו או דחו פעולות לפי סדר העדיפות.",
            ).as_dict()
        )
    projected_cash = base_cash_sf - total_cost
    if base_cash_sf and projected_cash < cash_buffer_sf - 0.01:
        checks.append(
            {
                "rule_id": "STRATEGY-CASH-FLOOR",
                "status": "fail",
                "message": f"החבילה מורידה מזומן ל-{projected_cash:,.0f} SF, מתחת לרצפה {cash_buffer_sf:,.0f} SF.",
                "blocking": True,
                "field": "cost_sf",
                "remediation": "הקטינו הוצאה, דחו פעולה או צרפו מימון חוקי.",
                "citation": {
                    "rule_id": "STRATEGY-CASH-FLOOR",
                    "name": "רצפת המזומן שאושרה בהגדרות",
                    "source_id": "team_strategy",
                    "source": "Approved team strategy and red lines",
                    "version": "active",
                    "knowledge_type": "Strategy Constraint",
                    "enforcement": "block",
                },
            }
        )
    research_count = sum(
        1
        for action in actions
        if str(action.get("type") or decision_action(str(action.get("code") or "")).get("type") or "") == "market_research"
    )
    if research_count > 3:
        checks.append(
            RuleCheck(
                "UI-MR-MAX-THREE",
                "fail",
                f"נבחרו {research_count} מחקרי שוק; המקסימום לרבעון הוא 3.",
                True,
                "study_id",
                "השאירו את שלושת המחקרים בעלי ערך המידע הגבוה ביותר.",
            ).as_dict()
        )
    blocking = [check for check in checks if check.get("blocking") and check.get("status") == "fail"]
    advisory = [check for check in checks if not check.get("blocking") and check.get("status") != "pass"]
    applied = sorted(
        {check.get("rule_id") for check in checks if check.get("rule_id")},
    )
    readiness_status = "blocked" if blocking else ("conditional" if advisory else "ready")
    return {
        "rulebook_version": RULEBOOK_VERSION,
        "feasible": not blocking,
        "checks": checks,
        "violations": blocking,
        "warnings": [check for check in checks if not check.get("blocking")],
        "readiness": {
            "status": readiness_status,
            "label": {
                "ready": "מוכן להגשה",
                "conditional": "מוכן בכפוף לתיקונים",
                "blocked": "חסום",
            }[readiness_status],
            "blocking_count": len(blocking),
            "warning_count": len(advisory),
            "required_fixes": list(
                dict.fromkeys(
                    str(check.get("remediation") or check.get("message") or "")
                    for check in blocking
                    if check.get("remediation") or check.get("message")
                )
            ),
        },
        "applied_rules": [rule_citation(RULE_INDEX[rule_id]) for rule_id in applied if rule_id in RULE_INDEX],
        "budget": {
            "available_sf": round(available_budget_sf, 2),
            "planned_cost_sf": round(total_cost, 2),
            "projected_cash_sf": round(projected_cash, 2),
            "cash_buffer_sf": round(cash_buffer_sf, 2),
        },
    }


def validate_report(extracted_data: dict[str, Any], expected_quarter: str = "") -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    metadata = extracted_data.get("metadata") or {}
    detected = str(metadata.get("detected_quarter") or "")
    # The exact workbook parser performs structural reconciliations (for
    # example Assets = Liabilities + Equity). Those checks are part of the
    # approval contract, not merely preview messages.
    for source_check in extracted_data.get("validation", []) or []:
        if not isinstance(source_check, dict):
            continue
        source_status = str(source_check.get("status") or "").lower()
        if source_status not in {"error", "warning"}:
            continue
        checks.append(
            {
                "rule_id": f"REPORT-{str(source_check.get('code') or 'STRUCTURE').upper()}",
                "status": "fail" if source_status == "error" else "warning",
                "blocking": source_status == "error",
                "message": str(source_check.get("message") or "The quarterly report failed a structural check."),
                "remediation": (
                    "Do not approve the report. Verify the original workbook, quarter and consolidated totals."
                    if source_status == "error"
                    else "Review the source row before approving the report."
                ),
                "citation": {
                    "source": "Official quarterly result workbook",
                    "source_id": "quarterly_actuals",
                },
            }
        )
    if expected_quarter.startswith("Q") and detected and detected != expected_quarter:
        checks.append(
            {
                "rule_id": "REPORT-QUARTER-MATCH",
                "status": "fail",
                "blocking": True,
                "message": f"הדוח זוהה כ-{detected} אך הועלה ל-{expected_quarter}.",
                "remediation": "תקנו את שיוך הרבעון לפני אישור הדוח.",
                "citation": {"source": "Official quarterly result workbook", "source_id": "quarterly_actuals"},
            }
        )
    operations = [row for row in extracted_data.get("operations", []) if isinstance(row, dict)]
    keys = [
        (
            str(row.get("quarter") or expected_quarter),
            normalize_area(row.get("area")),
            str(row.get("product") or ""),
            str(row.get("model") or ""),
        )
        for row in operations
    ]
    duplicates = [key for key, count in Counter(keys).items() if count > 1]
    if duplicates:
        checks.append(
            {
                "rule_id": "REPORT-UNIQUE-OPERATION",
                "status": "fail",
                "blocking": True,
                "message": f"זוהו {len(duplicates)} כפילויות באזור/מוצר/דגם.",
                "remediation": "בדקו את מיפוי הגיליונות לפני אישור.",
                "citation": {"source": "Actuals data model", "source_id": "quarterly_actuals"},
            }
        )
    for index, row in enumerate(operations):
        for field in ("plants", "plant_capacity", "actual_production", "actual_sales", "ending_inventory"):
            if _number(row.get(field)) < 0:
                checks.append(
                    {
                        "rule_id": "REPORT-NONNEGATIVE-OPERATIONS",
                        "status": "fail",
                        "blocking": True,
                        "message": f"שדה {field} שלילי בשורת פעילות {index + 1}.",
                        "remediation": "בדקו יחידות, סימן ושורת מקור.",
                        "citation": {"source": row.get("source") or "Official quarterly output", "source_id": "quarterly_actuals"},
                    }
                )
        grade = int(_number(row.get("grade"), -1))
        if grade < 0 or grade > 9:
            checks.append(
                {
                    "rule_id": "REPORT-GRADE-RANGE",
                    "status": "fail",
                    "blocking": True,
                    "message": f"רמה {grade} מחוץ לטווח 0–9 בשורת פעילות {index + 1}.",
                    "remediation": "בדקו את מיפוי רמת המוצר.",
                    "citation": rule_citation(RULE_INDEX["DL-XY-COMPATIBILITY"]),
                }
            )
    finance = extracted_data.get("finance") or {}
    if metadata.get("source_format") == "INTOPIA quarterly output":
        if not finance:
            checks.append(
                {
                    "rule_id": "REPORT-MISSING-FINANCE",
                    "status": "fail",
                    "blocking": True,
                    "message": "The official quarterly workbook did not produce a consolidated financial statement.",
                    "remediation": "Verify that Balance Sheet and Income Statement are present and use the supported template.",
                    "citation": {"source": "Official quarterly result workbook", "source_id": "quarterly_actuals"},
                }
            )
        if not operations:
            checks.append(
                {
                    "rule_id": "REPORT-MISSING-OPERATIONS",
                    "status": "fail",
                    "blocking": True,
                    "message": "The official quarterly workbook did not produce operating rows.",
                    "remediation": "Verify that Management Info is present and uses the supported template.",
                    "citation": {"source": "Official quarterly result workbook", "source_id": "quarterly_actuals"},
                }
            )
    if finance:
        for field in ("revenue_sf", "gross_profit_sf", "ending_cash_sf", "debt_sf", "ar_sf", "ap_sf"):
            value = finance.get(field)
            if value is not None and not isinstance(value, (int, float)):
                checks.append(
                    {
                        "rule_id": "REPORT-NUMERIC-FINANCE",
                        "status": "fail",
                        "blocking": True,
                        "message": f"השדה הפיננסי {field} אינו מספר.",
                        "remediation": "בדקו את תא המקור והמטבע.",
                        "citation": {"source": "Official quarterly financial statements", "source_id": "quarterly_actuals"},
                    }
                )
    blocking = [check for check in checks if check.get("blocking")]
    return {
        "rulebook_version": RULEBOOK_VERSION,
        "status": "blocked" if blocking else "passed",
        "checks": checks,
        "blocking_issues": blocking,
        "checked_sections": {
            "finance": bool(finance),
            "finance_by_area": len(extracted_data.get("finance_by_area", [])),
            "operations": len(operations),
            "research_results": len(extracted_data.get("research_results", [])),
        },
    }


def search_rules(
    rules: Iterable[dict[str, Any]],
    *,
    query: str = "",
    domain: str = "",
    area: str = "",
    product: str = "",
    knowledge_type: str = "",
    enforcement: str = "",
) -> list[dict[str, Any]]:
    query = query.strip().lower()
    area = normalize_area(area)
    result = []
    for row in rules:
        haystack = " ".join(
            str(row.get(key) or "")
            for key in ("rule_id", "name_he", "name_en", "description", "source_page", "domain", "knowledge_type")
        ).lower()
        if query and query not in haystack:
            continue
        if domain and str(row.get("domain") or "") != domain:
            continue
        if area and row.get("areas") and area not in [normalize_area(item) for item in row.get("areas", [])]:
            continue
        if product and row.get("products") and product not in row.get("products", []):
            continue
        if knowledge_type and str(row.get("knowledge_type") or "") != knowledge_type:
            continue
        if enforcement and str(row.get("enforcement") or "") != enforcement:
            continue
        result.append(dict(row))
    return sorted(result, key=lambda row: (str(row.get("domain")), str(row.get("rule_id"))))


def rulebook_summary(rules: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = [dict(row) for row in rules]
    approved = [row for row in rows if row.get("approval_status") == "approved"]
    hard = [row for row in approved if row.get("enforcement") == "block"]
    return {
        "version": RULEBOOK_VERSION,
        "status": RULEBOOK_STATUS,
        "total_rules": len(rows),
        "approved_rules": len(approved),
        "blocking_rules": len(hard),
        "by_type": dict(Counter(str(row.get("knowledge_type") or "Unknown") for row in rows)),
        "by_domain": dict(Counter(str(row.get("domain") or "other") for row in rows)),
        "source_count": len(RULE_SOURCES),
        "missing_high_priority_sources": [
            source["source_id"]
            for source in RULE_SOURCES
            if source["priority"] <= 3 and source["status"] == "awaiting_documents"
        ],
    }

from __future__ import annotations

from typing import Any


AREAS = ("USA", "Europe", "Brazil", "Liechtenstein")
PRODUCTS = ("X", "Y")
MODELS = ("Standard", "Deluxe")

AREA_CURRENCIES = {
    "USA": "USD",
    "Europe": "EUR",
    "Brazil": "BRL",
    "Liechtenstein": "CHF",
}

# Baseline values from Data Log v1. Current-quarter exchange rates still come
# from the uploaded Currency sheet and override the baseline conversion.
PLANT_CAPACITY = {
    "USA": {"X": 50_000, "Y": 25_000},
    "Europe": {"X": 35_000, "Y": 18_000},
    "Brazil": {"X": 14_000, "Y": 12_000},
}

PLANT_COST_LC = {
    "USA": {"X": 2_000_000, "Y": 1_800_000},
    "Europe": {"X": 1_000_000, "Y": 800_000},
    "Brazil": {"X": 1_600_000, "Y": 1_600_000},
}

BASELINE_FX_TO_SF = {"USA": 1.0, "Europe": 1.5, "Brazil": 0.5, "Liechtenstein": 1.0}

INITIAL_STANDARD_PRICE_LC = {
    "USA": {"X": 45, "Y": 155},
    "Europe": {"X": 40, "Y": 130},
    "Brazil": {"X": 150, "Y": 800},
}

MINIMUM_PRICE_STEP_LC = {
    "USA": {"X": 1, "Y": 5},
    "Europe": {"X": 1, "Y": 10},
    "Brazil": {"X": 10, "Y": 20},
}

MINIMUM_RD_SF = {"X": 40_000, "Y": 70_000}
FX_COMMISSION = {"USA": 0.006, "Europe": 0.006, "Brazil": 0.008, "Liechtenstein": 0.004}

# Rows are X grades; columns are Y grades. Zero means incompatible. A positive
# value is the number of X units needed for one Y unit.
X_Y_CONVERSION = (
    (1, 2, 3, 0, 0, 0, 0, 0, 0, 0),
    (1, 1, 2, 3, 4, 0, 0, 0, 0, 0),
    (1, 1, 2, 2, 3, 0, 0, 0, 0, 0),
    (0, 1, 1, 2, 2, 3, 3, 5, 0, 0),
    (0, 1, 1, 1, 2, 3, 3, 4, 0, 0),
    (0, 0, 0, 1, 1, 2, 2, 3, 0, 0),
    (0, 0, 0, 0, 0, 2, 2, 2, 3, 0),
    (0, 0, 0, 0, 0, 1, 1, 2, 3, 0),
    (0, 0, 0, 0, 0, 0, 0, 1, 2, 3),
    (0, 0, 0, 0, 0, 0, 0, 0, 1, 2),
)


DECISION_ACTIONS: list[dict[str, Any]] = [
    {
        "code": "A1-1",
        "type": "price_advertising",
        "title": "מחיר ופרסום שבבים",
        "category": "שיווק",
        "product": "X",
        "areas": ["USA", "Europe", "Brazil"],
        "fields": ["area", "model", "price_lc", "advertising_lc", "cost_sf"],
        "timing": "השפעה עיקרית ברבעון הנוכחי; לפרסום השפעה דועכת בהמשך.",
    },
    {
        "code": "A1-2",
        "type": "price_advertising",
        "title": "מחיר ופרסום מחשבים",
        "category": "שיווק",
        "product": "Y",
        "areas": ["USA", "Europe", "Brazil"],
        "fields": ["area", "model", "price_lc", "advertising_lc", "cost_sf"],
        "timing": "השפעה עיקרית ברבעון הנוכחי; לפרסום השפעה דועכת בהמשך.",
    },
    {
        "code": "A1-3",
        "type": "sales_offices",
        "title": "פתיחה או סגירה של משרדי מכירות",
        "category": "שיווק",
        "areas": ["USA", "Europe", "Brazil"],
        "fields": ["area", "office_delta", "cost_sf"],
        "timing": "משפיע על יכולת המכירה והוצאות המסחר באזור.",
    },
    {
        "code": "A2-1",
        "type": "plant_construction",
        "title": "הקמת מפעלים",
        "category": "ייצור ותפעול",
        "areas": ["USA", "Europe", "Brazil"],
        "fields": ["area", "product", "plant_count", "cost_sf"],
        "timing": "התשלום במזומן כעת; המפעל נכנס לייצור ברבעון הבא.",
    },
    {
        "code": "A2-3",
        "type": "production",
        "title": "ייצור שבבים",
        "category": "ייצור ותפעול",
        "product": "X",
        "areas": ["USA", "Europe", "Brazil"],
        "fields": ["area", "model", "grade", "units", "variable_cost_sf", "price_sf", "cost_sf"],
        "timing": "הייצור נכנס למלאי בסוף הרבעון ונמכר החל מהרבעון הבא.",
    },
    {
        "code": "A2-4",
        "type": "production",
        "title": "ייצור מחשבים",
        "category": "ייצור ותפעול",
        "product": "Y",
        "areas": ["USA", "Europe", "Brazil"],
        "fields": ["area", "model", "grade", "units", "x_grade", "variable_cost_sf", "price_sf", "cost_sf"],
        "timing": "דורש שבבי X תואמים; הייצור נכנס למלאי בסוף הרבעון.",
    },
    {
        "code": "A3-1",
        "type": "money_transfer",
        "title": "העברת כסף בין אזורים",
        "category": "מימון",
        "areas": ["USA", "Europe", "Brazil"],
        "fields": ["area", "target_area", "currency", "amount_sf", "cost_sf"],
        "timing": "משנה את הנזילות לפי מדינה; אינו יוצר רווח כלכלי בפני עצמו.",
    },
    {
        "code": "A3-2",
        "type": "invest_borrow",
        "title": "השקעה או הלוואה מקומית",
        "category": "מימון",
        "areas": ["USA", "Europe", "Brazil"],
        "fields": ["area", "direction", "amount_sf", "interest_rate", "cost_sf"],
        "timing": "הלוואה מגדילה מזומן וחוב; השקעה קושרת מזומן ומייצרת ריבית.",
    },
    {
        "code": "A3-3",
        "type": "currency_conversion",
        "title": "המרת מטבע זר",
        "category": "מימון",
        "areas": ["USA", "Europe", "Brazil"],
        "fields": ["area", "currency", "target_currency", "amount_sf", "cost_sf"],
        "timing": "עמלת ההמרה נגבית ברבעון ההחלטה.",
    },
    {
        "code": "A4",
        "type": "component_transfer",
        "title": "העברת רכיבים וסדרי עדיפויות",
        "category": "ייצור ותפעול",
        "product": "X",
        "areas": ["USA", "Europe", "Brazil"],
        "fields": ["area", "target_area", "grade", "units", "transport_mode", "priority", "cost_sf"],
        "timing": "העברה ימית מגיעה בסוף הרבעון; אווירית יכולה לשמש באותו רבעון.",
    },
    {
        "code": "H1-1",
        "type": "rd",
        "title": "מחקר ופיתוח",
        "category": "אסטרטגיה",
        "areas": ["Liechtenstein"],
        "fields": ["product", "amount_sf", "cost_sf"],
        "timing": "למו״פ זמן הבשלה; רציפות חשובה לפוטנציאל Q9.",
    },
    {
        "code": "H1-2",
        "type": "market_research",
        "title": "הזמנת מחקרי שוק",
        "category": "אסטרטגיה",
        "areas": ["Liechtenstein"],
        "fields": ["study_id", "cost_sf"],
        "timing": "מעלה ודאות ומשרת החלטה מוגדרת; עד שלושה מחקרים ברבעון.",
    },
    {
        "code": "H2",
        "type": "home_office_finance",
        "title": "החלטות השקעה ומימון במטה",
        "category": "אסטרטגיה",
        "areas": ["Liechtenstein"],
        "fields": ["direction", "currency", "amount_sf", "interest_rate", "cost_sf"],
        "timing": "כולל השקעות, הלוואות ואיגרות חוב לפי תנאי המטה.",
    },
    {
        "code": "H4",
        "type": "intercompany_loan",
        "title": "הלוואה בין חברות",
        "category": "אסטרטגיה",
        "areas": ["Liechtenstein"],
        "fields": ["partner_company", "direction", "currency", "amount_sf", "final_payment_sf", "payment_quarter", "interest_rate", "cost_sf"],
        "timing": "יש לבדוק סיכון צד נגדי ומועד פירעון לפני Q9.",
    },
    {
        "code": "H5",
        "type": "grade_license",
        "title": "רישיון לרמה טכנולוגית",
        "category": "אסטרטגיה",
        "areas": ["Liechtenstein"],
        "fields": ["partner_company", "product", "grade", "restricted", "amount_sf", "cost_sf"],
        "timing": "השימוש ברישיון מתחיל רבעון לאחר קבלתו; תקופת מינימום שני רבעונים.",
    },
    {
        "code": "H6",
        "type": "industrial_sale",
        "title": "מכירה תעשייתית בין חברות",
        "category": "שיווק",
        "areas": ["USA", "Europe", "Brazil"],
        "fields": ["area", "target_area", "partner_company", "product", "model", "grade", "units", "price_lc", "transport_mode", "cost_sf"],
        "timing": "הובלה ימית אורכת רבעון; אווירית מאפשרת שימוש ומכירה באותו רבעון.",
    },
    {
        "code": "W1",
        "type": "services_payment",
        "title": "תשלום עבור שירותים",
        "category": "מימון",
        "areas": list(AREAS),
        "fields": ["area", "target_area", "partner_company", "currency", "amount_sf", "cost_sf"],
        "timing": "תשלום בין חברות; אינו יוצר ערך ללא שירות מתועד.",
    },
    {
        "code": "W2",
        "type": "factory_sale",
        "title": "מכירת מפעל בין חברות",
        "category": "אסטרטגיה",
        "areas": ["USA", "Europe", "Brazil"],
        "fields": ["area", "partner_company", "product", "plant_count", "price_lc", "direction", "cost_sf"],
        "timing": "משנה מזומן וקיבולת; יש לבחון את ההשפעה על יכולת Q9.",
    },
    {
        "code": "W3",
        "type": "local_currency_exchange",
        "title": "המרת מטבע מול בנק מקומי",
        "category": "מימון",
        "areas": list(AREAS),
        "fields": ["area", "currency", "target_currency", "amount_sf", "cost_sf"],
        "timing": "עמלת ההמרה תלויה באזור ומקטינה מזומן.",
    },
]


def decision_action(code: str) -> dict[str, Any]:
    return next((dict(item) for item in DECISION_ACTIONS if item["code"] == code), {})


def compatible_x_units(x_grade: int, y_grade: int) -> int:
    if not 0 <= x_grade <= 9 or not 0 <= y_grade <= 9:
        return 0
    return int(X_Y_CONVERSION[x_grade][y_grade])


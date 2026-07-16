from __future__ import annotations

import csv
import io
import re
from pathlib import Path
from typing import Any, Iterable


FINANCE_ALIASES = {
    "revenue_sf": ["revenue", "sales revenue", "net sales", "הכנסות", "מכירות"],
    "gross_profit_sf": ["gross profit", "רווח גולמי"],
    "net_profit_sf": ["net profit", "net income", "רווח נקי"],
    "ending_cash_sf": ["ending cash", "cash balance", "cash", "מזומן סופי", "יתרת מזומן", "מזומן"],
    "debt_sf": ["debt", "loans", "חוב", "הלוואות"],
    "ar_sf": ["accounts receivable", "receivables", "חייבים", "לקוחות"],
    "ap_sf": ["accounts payable", "payables", "זכאים", "ספקים"],
    "research_budget_sf": ["market research", "research budget", "תקציב מחקר", "מחקרי שוק"],
    "rd_x_sf": ["r&d x", "rd x", "מו״פ x", "מופ x"],
    "rd_y_sf": ["r&d y", "rd y", "מו״פ y", "מופ y"],
}

AREA_FINANCE_ALIASES = {
    "area": ["area", "country", "region", "אזור", "מדינה"],
    "currency": ["currency", "מטבע"],
    "fx_to_sf": ["fx", "exchange rate", "fx to sf", "שער חליפין"],
    "revenue_lc": ["revenue", "sales", "הכנסות", "מכירות"],
    "gross_profit_lc": ["gross profit", "רווח גולמי"],
    "net_profit_lc": ["net profit", "net income", "רווח נקי"],
    "ending_cash_lc": ["ending cash", "cash", "מזומן סופי", "מזומן"],
    "debt_lc": ["debt", "loans", "חוב", "הלוואות"],
    "ar_lc": ["accounts receivable", "receivables", "חייבים", "לקוחות"],
    "ap_lc": ["accounts payable", "payables", "זכאים", "ספקים"],
    "inventory_value_lc": ["inventory value", "inventory", "ערך מלאי", "מלאי"],
    "current_assets_lc": ["current assets", "נכסים שוטפים"],
    "current_liabilities_lc": ["current liabilities", "התחייבויות שוטפות"],
    "equity_lc": ["equity", "shareholders equity", "הון עצמי"],
    "total_investment_lc": ["total investment", "invested capital", "השקעה כוללת", "הון מושקע"],
    "operating_cash_flow_lc": ["operating cash flow", "תזרים מפעילות"],
    "capex_commitments_lc": ["capex commitments", "capital commitments", "התחייבויות השקעה"],
}

OPERATION_ALIASES = {
    "area": ["area", "country", "region", "אזור", "מדינה"],
    "product": ["product", "מוצר"],
    "model": ["model", "segment", "דגם", "פלח"],
    "grade": ["grade", "technology", "level", "רמה", "טכנולוגיה"],
    "plants": ["plants", "מפעלים"],
    "plant_capacity": ["capacity", "plant capacity", "קיבולת"],
    "planned_production": ["planned production", "production plan", "ייצור מתוכנן"],
    "actual_production": ["actual production", "production", "ייצור בפועל", "ייצור"],
    "opening_inventory": ["opening inventory", "מלאי פתיחה"],
    "planned_sales": ["planned sales", "sales plan", "מכירות מתוכננות"],
    "actual_sales": ["actual sales", "units sold", "sales units", "מכירות בפועל", "יחידות שנמכרו"],
    "ending_inventory": ["ending inventory", "closing inventory", "מלאי סופי"],
    "forecast_demand": ["forecast demand", "demand forecast", "תחזית ביקוש"],
    "planned_price_lc": ["planned price", "מחיר מתוכנן"],
    "actual_price_lc": ["actual price", "price", "מחיר בפועל", "מחיר"],
    "advertising_lc": ["advertising", "promotion", "פרסום", "קידום"],
    "variable_cost_lc": ["variable cost", "unit cost", "עלות משתנה", "עלות ליחידה"],
    "fixed_cost_lc": ["fixed cost", "עלויות קבועות"],
    "actual_market_share": ["market share", "נתח שוק"],
}


def _clean(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[\s_\-:/()]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace("\u200f", "").replace("\u200e", "")
    negative = text.startswith("(") and text.endswith(")")
    text = re.sub(r"[^0-9.,\-]", "", text)
    if text.count(",") > 0 and text.count(".") == 0:
        parts = text.split(",")
        text = "".join(parts) if len(parts[-1]) == 3 else ".".join(parts)
    else:
        text = text.replace(",", "")
    try:
        number = float(text)
        return -abs(number) if negative else number
    except ValueError:
        return None


def _match_field(label: Any, aliases: dict[str, list[str]]) -> str | None:
    normalized = _clean(label)
    if not normalized:
        return None
    for field, options in aliases.items():
        for option in options:
            candidate = _clean(option)
            if normalized == candidate or candidate in normalized:
                return field
    return None


def _decode(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1255", "windows-1252"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def _csv_rows(content: bytes) -> list[list[Any]]:
    text = _decode(content)
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    return [list(row) for row in csv.reader(io.StringIO(text), dialect=dialect)]


def _xlsx_tables(content: bytes) -> list[tuple[str, list[list[Any]]]]:
    try:
        from openpyxl import load_workbook
    except ImportError as exc:
        raise RuntimeError("openpyxl is required to read Excel files") from exc
    workbook = load_workbook(io.BytesIO(content), data_only=True, read_only=True)
    tables: list[tuple[str, list[list[Any]]]] = []
    for sheet in workbook.worksheets:
        rows = [list(row) for row in sheet.iter_rows(values_only=True)]
        tables.append((sheet.title, rows))
    return tables


def _pdf_text(content: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("pypdf is required to read PDF files") from exc
    reader = PdfReader(io.BytesIO(content))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _metric_pairs(rows: Iterable[list[Any]]) -> dict[str, float]:
    values: dict[str, float] = {}
    for row in rows:
        cells = [cell for cell in row if cell not in (None, "")]
        if len(cells) < 2:
            continue
        field = _match_field(cells[0], FINANCE_ALIASES)
        value = next((_number(cell) for cell in cells[1:] if _number(cell) is not None), None)
        if field and value is not None:
            values[field] = value
    return values


def _header_map(row: list[Any], aliases: dict[str, list[str]]) -> dict[int, str]:
    result: dict[int, str] = {}
    for index, cell in enumerate(row):
        field = _match_field(cell, aliases)
        if field and field not in result.values():
            result[index] = field
    return result


def _table_records(rows: list[list[Any]], aliases: dict[str, list[str]], required: set[str]) -> list[dict[str, Any]]:
    best_index = -1
    best_map: dict[int, str] = {}
    for index, row in enumerate(rows[:40]):
        mapping = _header_map(row, aliases)
        if len(mapping) > len(best_map):
            best_index, best_map = index, mapping
    if best_index < 0 or not required.issubset(set(best_map.values())):
        return []
    records: list[dict[str, Any]] = []
    text_fields = {"area", "product", "model", "currency"}
    for raw in rows[best_index + 1 :]:
        record: dict[str, Any] = {}
        for column, field in best_map.items():
            if column >= len(raw):
                continue
            value = raw[column]
            if value in (None, ""):
                continue
            record[field] = str(value).strip() if field in text_fields else _number(value)
        if required.issubset({key for key, value in record.items() if value not in (None, "")}):
            records.append(record)
    return records


def _pdf_finance(text: str) -> dict[str, float]:
    result: dict[str, float] = {}
    for line in text.splitlines():
        field = _match_field(line, FINANCE_ALIASES)
        if not field:
            continue
        numbers = re.findall(r"\(?-?[\d][\d,]*(?:\.\d+)?\)?", line)
        if numbers:
            value = _number(numbers[-1])
            if value is not None:
                result[field] = value
    return result


def _strategy_profile_from_text(text: str, filename: str) -> dict[str, Any]:
    lines = [re.sub(r"\s+", " ", line).strip(" \t•-–—") for line in text.splitlines()]
    lines = [line for line in lines if len(line) >= 4]
    if not lines:
        return {}

    def select(*needles: str, limit: int = 12) -> list[str]:
        lowered = [needle.lower() for needle in needles]
        return [line for line in lines if any(needle in line.lower() for needle in lowered)][:limit]

    goals = select("q9", "יעד", "מטרה", "target", "goal", "%", limit=15)
    constraints = select("אין ", "לא ", "מינימום", "מקסימום", "must", "minimum", "maximum", "cash", "מזומן", limit=12)
    priorities = select("מיקוד", "אסטרטג", "עדיפות", "priority", "focus", "טכנולוג", "technology", "שוק", "market", limit=12)
    thesis_lines = [line for line in lines if line not in goals and line not in constraints][:6] or lines[:6]
    return {
        "thesis": " · ".join(thesis_lines)[:2000],
        "priorities": priorities,
        "goals": goals,
        "constraints": constraints,
        "source_name": filename,
        "source_excerpt": "\n".join(lines)[:8000],
    }


def extract_document(content: bytes, filename: str, mime_type: str, quarter: str, category: str) -> dict[str, Any]:
    extension = Path(filename).suffix.lower()
    extracted: dict[str, Any] = {"finance": {}, "finance_by_area": [], "operations": [], "research_results": [], "strategy_profile": {}, "previews": []}
    issues: list[str] = []
    parser = "unsupported"
    category_key = category.lower()
    is_strategy = "אסטרטג" in category_key or "strategy" in category_key or "יעדי q9" in category_key or "q9 goals" in category_key

    try:
        if extension in {".xlsx", ".xlsm"} or "spreadsheet" in mime_type:
            parser = "excel"
            tables = _xlsx_tables(content)
            strategy_text: list[str] = []
            for sheet_name, rows in tables:
                extracted["finance"].update(_metric_pairs(rows))
                extracted["finance_by_area"].extend(_table_records(rows, AREA_FINANCE_ALIASES, {"area"}))
                extracted["operations"].extend(_table_records(rows, OPERATION_ALIASES, {"area", "product", "model"}))
                extracted["previews"].append({"sheet": sheet_name, "rows": rows[:8]})
                if is_strategy:
                    strategy_text.extend(str(cell) for row in rows[:250] for cell in row if cell not in (None, ""))
            if is_strategy:
                extracted["strategy_profile"] = _strategy_profile_from_text("\n".join(strategy_text), filename)
        elif extension in {".csv", ".tsv"} or mime_type.startswith("text/csv"):
            parser = "csv"
            rows = _csv_rows(content)
            extracted["finance"].update(_metric_pairs(rows))
            extracted["finance_by_area"].extend(_table_records(rows, AREA_FINANCE_ALIASES, {"area"}))
            extracted["operations"].extend(_table_records(rows, OPERATION_ALIASES, {"area", "product", "model"}))
            extracted["previews"].append({"sheet": "CSV", "rows": rows[:12]})
        elif extension == ".pdf" or mime_type == "application/pdf":
            parser = "pdf-text"
            text = _pdf_text(content)
            if not text.strip():
                issues.append("לא נמצא טקסט קריא. ייתכן שזה PDF סרוק ונדרש פענוח AI/OCR.")
            extracted["finance"].update(_pdf_finance(text))
            extracted["previews"].append({"sheet": "PDF", "text": text[:4000]})
            if is_strategy:
                extracted["strategy_profile"] = _strategy_profile_from_text(text, filename)
            if "מחקר" in category or "research" in category.lower():
                extracted["research_results"].append({"quarter": quarter, "title": filename, "key_result": text[:2000], "confidence": "בינונית" if text.strip() else "נמוכה"})
        elif mime_type.startswith("text/") or extension in {".txt", ".md"}:
            parser = "text"
            text = _decode(content)
            extracted["finance"].update(_pdf_finance(text))
            extracted["previews"].append({"sheet": "Text", "text": text[:4000]})
            if is_strategy:
                extracted["strategy_profile"] = _strategy_profile_from_text(text, filename)
            if "מחקר" in category or "research" in category.lower():
                extracted["research_results"].append({"quarter": quarter, "title": filename, "key_result": text[:2000], "confidence": "בינונית"})
        elif mime_type.startswith("image/"):
            parser = "image"
            issues.append("התמונה נשמרה, אך נדרש פענוח AI/OCR כדי לחלץ ממנה נתונים.")
        else:
            issues.append("סוג הקובץ נשמר אך אינו נתמך עדיין בחילוץ אוטומטי.")
    except Exception as exc:
        issues.append(f"החילוץ נכשל: {exc}")

    if quarter not in {f"Q{i}" for i in range(1, 10)} and (extracted["finance"] or extracted["operations"]):
        issues.append("נמצאו נתונים רבעוניים אך הקובץ לא קושר לרבעון Q1–Q9.")
    if not extracted["finance"] and not extracted["operations"] and not extracted["research_results"] and not extracted["strategy_profile"]:
        issues.append("לא זוהו שדות מובנים. הקובץ נשמר ויופיע לבדיקה ידנית.")

    extracted_count = len(extracted["finance"]) + len(extracted["finance_by_area"]) + len(extracted["operations"]) + len(extracted["research_results"]) + (1 if extracted["strategy_profile"] else 0)
    confidence = "גבוהה" if extracted_count >= 8 and not issues else "בינונית" if extracted_count >= 2 else "נמוכה"
    status = "מוכן לאישור" if extracted_count else "נדרשת בדיקה"
    return {"parser_type": parser, "status": status, "confidence": confidence, "extracted_data": extracted, "issues": issues, "extracted_count": extracted_count}

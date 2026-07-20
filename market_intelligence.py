from __future__ import annotations

from collections import defaultdict
from statistics import median
from typing import Any


def _mapping(study_id: int) -> dict[str, Any]:
    """Return the deterministic decision contract for an INTOPIA MR study."""
    if study_id in {2, 3, 11}:
        return {"knowledge_type": "descriptive", "variables": ["consumer_sales", "market_share", "market_size"], "actions": ["A1-1", "A1-2", "A2-3", "A2-4"], "domains": ["marketing", "production"]}
    if study_id in {4, 5, 6}:
        return {"knowledge_type": "descriptive", "variables": ["competitor_advertising", "advertising_intensity"], "actions": ["A1-1", "A1-2"], "domains": ["marketing"]}
    if study_id in {7, 8, 9, 18}:
        return {"knowledge_type": "descriptive", "variables": ["methods_investment", "plant_obsolescence", "unit_cost"], "actions": ["H2", "A2-3", "A2-4"], "domains": ["operations", "strategy"]}
    if study_id in {10, 19, 23, 24, 29, 30, 40}:
        kind = "direct_parameter" if study_id == 24 else "descriptive"
        return {"knowledge_type": kind, "variables": ["capacity", "inventory", "optimal_production", "competitor_supply"], "actions": ["A2-1", "A2-3", "A2-4", "A4"], "domains": ["production", "operations"]}
    if study_id in {12, 13, 14, 21, 22}:
        return {"knowledge_type": "descriptive", "variables": ["rd_intensity", "patent_probability", "technology_lead"], "actions": ["H1-1", "H5"], "domains": ["rd", "technology", "strategy"]}
    if study_id in {15, 16}:
        return {"knowledge_type": "descriptive", "variables": ["competitor_information_spend"], "actions": ["H1-2"], "domains": ["market_research", "strategy"]}
    if study_id == 17:
        return {"knowledge_type": "direct_parameter", "variables": ["sold_grade", "technology_position"], "actions": ["A1-1", "A1-2", "H1-1", "H5"], "domains": ["technology", "marketing"]}
    if study_id == 20:
        return {"knowledge_type": "direct_parameter", "variables": ["shareholder_payout_floor"], "actions": ["H2", "A3-2"], "domains": ["finance", "strategy"]}
    if study_id in {25, 81}:
        return {"knowledge_type": "direct_parameter" if study_id == 81 else "descriptive", "variables": ["sales_offices", "optimal_sales_offices", "channel_cost"], "actions": ["A1-3"], "domains": ["marketing", "distribution"]}
    if study_id in {27, 71, 72, 73, 74, 75, 79}:
        return {"knowledge_type": "direct_parameter" if study_id in {27, 79} else "descriptive", "variables": ["competitor_financials", "ratios", "market_share", "technology"], "actions": ["A3-1", "A3-2", "A3-3", "H2"], "domains": ["finance", "strategy"]}
    if study_id == 28:
        return {"knowledge_type": "direct_parameter", "variables": ["competitor_price", "price_position"], "actions": ["A1-1", "A1-2"], "domains": ["pricing", "marketing"]}
    if 31 <= study_id <= 49:
        product = "X" if study_id <= 39 else "Y"
        grade = study_id - 30 if product == "X" else study_id - 40
        return {"knowledge_type": "direct_parameter", "variables": ["price_premium", f"{product}{grade}_willingness_to_pay"], "actions": ["A1-1" if product == "X" else "A1-2", "H1-1", "H5"], "domains": ["pricing", "technology"]}
    if 51 <= study_id <= 69:
        product = "X" if study_id <= 59 else "Y"
        grade = study_id - 50 if product == "X" else study_id - 60
        return {"knowledge_type": "direct_parameter", "variables": ["variable_cost_premium", f"{product}{grade}_unit_cost"], "actions": ["A2-3" if product == "X" else "A2-4", "H1-1", "H5"], "domains": ["unit_economics", "production", "technology"]}
    if study_id in {76, 77}:
        return {"knowledge_type": "descriptive", "variables": ["trade_volume", "trade_price", "logistics_demand"], "actions": ["A4", "H6", "W1"], "domains": ["logistics", "production", "marketing"]}
    if study_id == 80:
        return {"knowledge_type": "descriptive", "variables": ["intercompany_sales", "partner_network"], "actions": ["H4", "H5", "H6", "W1", "W2"], "domains": ["partnerships", "strategy"]}
    return {"knowledge_type": "descriptive", "variables": [], "actions": [], "domains": []}


def research_decision_map(catalog: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "study_id": int(row.get("study_id") or 0),
            "name": row.get("name", ""),
            "cost_k_sf": row.get("cost_k_sf"),
            **_mapping(int(row.get("study_id") or 0)),
        }
        for row in catalog
    ]


def _quarter_number(value: Any) -> int:
    try:
        return int(str(value or "Q0").upper().replace("Q", ""))
    except ValueError:
        return 0


def _numeric(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _operation_observations(operations: list[dict[str, Any]], quarter: str) -> list[dict[str, Any]]:
    end = _quarter_number(quarter)
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in operations:
        if not (0 < _quarter_number(row.get("quarter")) <= end):
            continue
        price = _numeric(row.get("price_lc"))
        sales = _numeric(row.get("sales"))
        if price is None or price <= 0 or sales is None or sales < 0:
            continue
        key = (str(row.get("area") or ""), str(row.get("product") or ""), str(row.get("model") or ""))
        groups[key].append({"quarter": row.get("quarter"), "price": price, "sales": sales})
    calibrations: list[dict[str, Any]] = []
    for key, rows in groups.items():
        rows.sort(key=lambda row: _quarter_number(row["quarter"]))
        elasticities: list[float] = []
        price_changes = 0
        for left, right in zip(rows, rows[1:]):
            avg_price = (left["price"] + right["price"]) / 2
            avg_sales = (left["sales"] + right["sales"]) / 2
            if avg_price <= 0 or avg_sales <= 0:
                continue
            price_change = (right["price"] - left["price"]) / avg_price
            if abs(price_change) < 0.01:
                continue
            price_changes += 1
            sales_change = (right["sales"] - left["sales"]) / avg_sales
            elasticities.append(abs(sales_change / price_change))
        sufficient = len(rows) >= 3 and price_changes >= 2 and len(elasticities) >= 2
        calibrations.append({
            "segment": " / ".join(part or "—" for part in key),
            "observation_count": len(rows),
            "independent_price_changes": price_changes,
            "status": "sufficient_for_draft" if sufficient else "insufficient_observations",
            "knowledge_type": "inference",
            "elasticity_estimate": round(median(elasticities), 3) if sufficient else None,
            "range": [round(min(elasticities), 3), round(max(elasticities), 3)] if sufficient else None,
            "warning": (
                "Draft inference only; competitor, advertising and technology effects are not isolated."
                if sufficient else
                "At least 3 observations and 2 material price changes are required; no elasticity is inferred."
            ),
            "source_quarters": [row["quarter"] for row in rows],
        })
    return calibrations


def _recommendation_exposure(recommendations: list[dict[str, Any]], actions: list[str]) -> tuple[float | None, str, str]:
    matched = [row for row in recommendations if str((row.get("action_template") or {}).get("code") or row.get("form_code") or "") in actions]
    candidates: list[float] = []
    for row in matched:
        for container in (row, row.get("action_template") or {}, row.get("simulation") or {}):
            for key in ("cost_sf", "amount_sf", "cash_impact_sf", "investment_sf", "projected_profit_sf"):
                value = _numeric(container.get(key))
                if value is not None:
                    candidates.append(abs(value))
    if candidates:
        return max(candidates), "linked recommendation / simulation", "medium"
    return None, "no approved numeric exposure", "low"


def build_market_intelligence(
    quarter: str,
    catalog: list[dict[str, Any]],
    research_results: list[dict[str, Any]],
    operations: list[dict[str, Any]],
    recommendations: list[dict[str, Any]],
) -> dict[str, Any]:
    end = _quarter_number(quarter)
    catalog_by_id = {int(row.get("study_id") or 0): row for row in catalog}
    approved = [
        row for row in research_results
        if 0 < _quarter_number(row.get("quarter")) <= end
        and str(row.get("status") or "").lower() not in {"rejected", "draft", "נדחה", "טיוטה"}
    ]
    available_ids = {int(row.get("study_id") or 0) for row in approved if row.get("study_id") not in (None, "")}
    mapped_results: list[dict[str, Any]] = []
    for row in approved:
        study_id = int(row.get("study_id") or 0)
        mapping = _mapping(study_id)
        numeric_data = row.get("numeric_data") or {}
        mapped_results.append({
            "id": row.get("id"),
            "study_id": study_id or None,
            "label": f"MR{study_id}" if study_id else "Unnumbered research",
            "title": row.get("title", ""),
            "quarter": row.get("quarter"),
            "key_result": row.get("key_result", ""),
            "numeric_data": numeric_data,
            "knowledge_type": mapping["knowledge_type"] if study_id else "descriptive",
            "decision_variables": mapping["variables"],
            "affected_actions": mapping["actions"],
            "domains": mapping["domains"],
            "source": {"type": "market_research", "upload_id": row.get("source_upload_id"), "quarter": row.get("quarter"), "study_id": study_id or None},
            "confidence": row.get("confidence") or "medium",
            "interpretation_rule": "Observed research result; any recommendation derived from it is separately labelled as inference.",
        })

    voi_candidates: list[dict[str, Any]] = []
    for study_id, catalog_row in catalog_by_id.items():
        if study_id in available_ids or catalog_row.get("cost_k_sf") is None:
            continue
        mapping = _mapping(study_id)
        if not mapping["actions"]:
            continue
        exposure, exposure_source, exposure_confidence = _recommendation_exposure(recommendations, mapping["actions"])
        linked_count = sum(
            1 for row in recommendations
            if str((row.get("action_template") or {}).get("code") or row.get("form_code") or "") in mapping["actions"]
        )
        cost_sf = float(catalog_row.get("cost_k_sf") or 0) * 1000
        urgency = 1.0 if end >= 7 else 1.25 if end >= 4 else 1.1
        decision_change_probability = min(0.75, 0.30 + 0.12 * linked_count)
        expected_value = None
        net_value = None
        if exposure is not None:
            expected_value = exposure * decision_change_probability * 0.25
            net_value = expected_value - cost_sf
        score = (linked_count + 1) * urgency * decision_change_probability / max(cost_sf / 1000, 1)
        voi_candidates.append({
            "study_id": study_id,
            "label": f"MR{study_id}",
            "name": catalog_row.get("name", ""),
            "cost_sf": cost_sf,
            "affected_actions": mapping["actions"],
            "decision_variables": mapping["variables"],
            "linked_decisions": linked_count,
            "decision_change_probability": round(decision_change_probability, 2),
            "decision_exposure_sf": exposure,
            "exposure_source": exposure_source,
            "expected_information_value_sf": round(expected_value, 2) if expected_value is not None else None,
            "net_voi_sf": round(net_value, 2) if net_value is not None else None,
            "value_status": "quantified" if net_value is not None else "qualitative_only",
            "confidence": exposure_confidence,
            "priority_score": round(score, 5),
            "recommendation": (
                "Order only if the linked decision remains open and the study can arrive before its execution deadline."
            ),
        })
    voi_candidates.sort(key=lambda row: (
        row["net_voi_sf"] is None,
        -(row["net_voi_sf"] or 0),
        -row["priority_score"],
        row["cost_sf"],
    ))

    calibrations = _operation_observations(operations, quarter)
    unavailable = []
    if not any(row["status"] == "sufficient_for_draft" for row in calibrations):
        unavailable.append("Price elasticity cannot be calibrated yet: no segment has 3 observations with 2 material price changes.")
    if 28 not in available_ids:
        unavailable.append("Competitor price position is unknown without an approved MR28 result.")
    if 17 not in available_ids:
        unavailable.append("Competitor technology grades sold are unknown without an approved MR17 result.")
    if 24 not in available_ids:
        unavailable.append("Optimal production volume is not a known parameter without an approved MR24 result.")
    if not approved:
        unavailable.append("No approved market-research result is available through the selected quarter.")

    mapped_catalog = research_decision_map(catalog)
    covered = sum(1 for row in mapped_catalog if row["actions"] or row["variables"])
    return {
        "quarter": quarter,
        "status": "ready" if approved else "awaiting_research",
        "approved_result_count": len(approved),
        "available_studies": sorted(available_ids),
        "mapped_results": mapped_results,
        "decision_map": mapped_catalog,
        "mapping_coverage": {"mapped": covered, "catalog_total": len(mapped_catalog), "percent": round(100 * covered / max(len(mapped_catalog), 1), 1)},
        "calibration_signals": calibrations,
        "recommended_research": voi_candidates[:3],
        "voi_method": {
            "formula": "decision exposure × probability of changing decision × 25% avoided-loss factor − study cost",
            "guardrail": "A monetary VOI is shown only when a linked recommendation contains an auditable numeric exposure; otherwise the ranking is qualitative.",
            "currency": "SF",
        },
        "cannot_conclude": unavailable,
        "knowledge_contract": {
            "descriptive": "Observed market description; does not prove causality.",
            "direct_parameter": "An official research parameter that may be used directly within its stated scope.",
            "inference": "Model-derived signal; requires sufficient observations and remains distinct from a game rule.",
        },
    }

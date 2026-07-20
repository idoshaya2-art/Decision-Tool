from __future__ import annotations

import db
from rulebook import (
    CANONICAL_RULES,
    RULEBOOK_VERSION,
    evaluate_action,
    evaluate_portfolio,
    validate_report,
)


def _failures(checks):
    return {row["rule_id"] for row in checks if row["status"] == "fail" and row["blocking"]}


def test_canonical_rulebook_has_sources_versions_and_blocking_rules():
    assert len(CANONICAL_RULES) >= 50
    assert all(row["rule_id"] and row["source_id"] and row["version"] for row in CANONICAL_RULES)
    assert any(row["knowledge_type"] == "Hard Rule" for row in CANONICAL_RULES)
    assert any(row["enforcement"] == "block" for row in CANONICAL_RULES)


def test_xy_compatibility_accepts_legal_combination_and_blocks_illegal_one():
    legal = evaluate_action(
        {"code": "A2-4", "area": "Europe", "product": "Y", "grade": 4, "x_grade": 4, "units": 100},
        quarter="Q4",
    )
    illegal = evaluate_action(
        {"code": "A2-4", "area": "Europe", "product": "Y", "grade": 7, "x_grade": 0, "units": 100},
        quarter="Q4",
    )
    assert "DL-XY-COMPATIBILITY" not in _failures(legal)
    assert "DL-XY-COMPATIBILITY" in _failures(illegal)


def test_production_capacity_and_same_quarter_sale_are_blocked():
    operations = [
        {
            "area": "Europe",
            "product": "Y",
            "model": "Standard",
            "plant_capacity": 1_000,
        }
    ]
    checks = evaluate_action(
        {
            "code": "A2-4",
            "area": "Europe",
            "product": "Y",
            "model": "Standard",
            "grade": 2,
            "x_grade": 2,
            "units": 1_200,
            "same_quarter_sales": True,
        },
        quarter="Q4",
        operations=operations,
    )
    failures = _failures(checks)
    assert "DL-PLANT-CAPACITY" in failures
    assert "DL-PRODUCTION-SALES-LAG" in failures


def test_maximum_three_plants_has_positive_and_negative_case():
    operations = [{"area": "USA", "product": "X", "plants": 2}]
    allowed = evaluate_action(
        {"code": "A2-1", "area": "USA", "product": "X", "plant_count": 1},
        quarter="Q4",
        operations=operations,
    )
    blocked = evaluate_action(
        {"code": "A2-1", "area": "USA", "product": "X", "plant_count": 2},
        quarter="Q4",
        operations=operations,
    )
    assert "UI-MAX-THREE-PLANTS" not in _failures(allowed)
    assert "UI-MAX-THREE-PLANTS" in _failures(blocked)


def test_price_cap_steps_and_rd_minimum_are_enforced():
    price_checks = evaluate_action(
        {
            "code": "A1-2",
            "area": "Europe",
            "product": "Y",
            "grade": 2,
            "current_price_lc": 1_300,
            "price_lc": 1_405,
        },
        quarter="Q4",
    )
    assert {"DL-Y03-PRICE-CAP", "DL-PRICE-STEP"}.issubset(_failures(price_checks))

    low_rd = evaluate_action(
        {"code": "H1-1", "area": "Liechtenstein", "product": "Y", "amount_sf": 69_999},
        quarter="Q4",
    )
    valid_rd = evaluate_action(
        {"code": "H1-1", "area": "Liechtenstein", "product": "Y", "amount_sf": 70_000},
        quarter="Q4",
    )
    assert "DL-RD-MINIMUM" in _failures(low_rd)
    assert "DL-RD-MINIMUM" not in _failures(valid_rd)


def test_zero_price_and_negative_production_are_blocked():
    zero_price = evaluate_action(
        {
            "code": "A1-1",
            "area": "Europe",
            "product": "X",
            "model": "Standard",
            "price_lc": 0,
            "advertising_lc": 0,
        },
        quarter="Q4",
        strict=True,
    )
    negative_production = evaluate_action(
        {
            "code": "A2-3",
            "area": "Europe",
            "product": "X",
            "model": "Standard",
            "grade": 2,
            "units": -1,
            "variable_cost_sf": 1,
            "price_sf": 2,
        },
        quarter="Q4",
        operations=[
            {
                "area": "Europe",
                "product": "X",
                "model": "Standard",
                "grade": 2,
                "plant_capacity": 1_000,
            }
        ],
        strict=True,
    )
    assert "FORM-A1-1" in _failures(zero_price)
    assert "FORM-A2-3" in _failures(negative_production)


def test_outgoing_stock_cannot_exceed_approved_inventory():
    operations = [
        {
            "area": "Europe",
            "product": "X",
            "model": "Standard",
            "grade": 2,
            "ending_inventory": 80,
        }
    ]
    allowed = evaluate_action(
        {
            "code": "H6",
            "area": "Europe",
            "target_area": "USA",
            "partner_company": "3",
            "product": "X",
            "model": "Standard",
            "grade": 2,
            "units": 80,
            "price_lc": 45,
            "transport_mode": "air",
        },
        quarter="Q4",
        operations=operations,
        strict=True,
    )
    blocked = evaluate_action(
        {
            "code": "H6",
            "area": "Europe",
            "target_area": "USA",
            "partner_company": "3",
            "product": "X",
            "model": "Standard",
            "grade": 2,
            "units": 81,
            "price_lc": 45,
            "transport_mode": "air",
        },
        quarter="Q4",
        operations=operations,
        strict=True,
    )
    assert "DL-INVENTORY-CARRYING" not in _failures(allowed)
    assert "DL-INVENTORY-CARRYING" in _failures(blocked)


def test_strict_production_requires_approved_capacity_and_y_requires_x_inventory():
    missing_capacity = evaluate_action(
        {
            "code": "A2-3",
            "area": "Europe",
            "product": "X",
            "model": "Standard",
            "grade": 2,
            "units": 100,
            "variable_cost_sf": 1,
            "price_sf": 2,
        },
        quarter="Q4",
        strict=True,
    )
    missing_x = evaluate_action(
        {
            "code": "A2-4",
            "area": "Europe",
            "product": "Y",
            "model": "Standard",
            "grade": 4,
            "x_grade": 4,
            "units": 100,
            "variable_cost_sf": 1,
            "price_sf": 2,
        },
        quarter="Q4",
        operations=[
            {
                "area": "Europe",
                "product": "Y",
                "model": "Standard",
                "grade": 4,
                "plant_capacity": 1_000,
            }
        ],
        strict=True,
    )
    assert "DL-PLANT-CAPACITY" in _failures(missing_capacity)
    assert "DL-XY-COMPATIBILITY" in _failures(missing_x)


def test_portfolio_exposes_unambiguous_readiness_and_numeric_fixes():
    result = evaluate_portfolio(
        [
            {
                "code": "A1-1",
                "area": "Europe",
                "product": "X",
                "model": "Standard",
                "price_lc": 0,
                "advertising_lc": 0,
                "cost_sf": 0,
            }
        ],
        quarter="Q4",
        available_budget_sf=100_000,
        base_cash_sf=100_000,
        strict=True,
    )
    assert result["readiness"]["status"] == "blocked"
    assert result["readiness"]["label"] == "חסום"
    assert result["readiness"]["blocking_count"] >= 1
    assert result["readiness"]["required_fixes"]


def test_market_research_license_and_intercompany_loan_require_real_terms():
    fake_study = evaluate_action(
        {
            "code": "H1-2",
            "area": "Liechtenstein",
            "study_id": "FAKE",
            "cost_sf": 0,
        },
        quarter="Q4",
        strict=True,
    )
    free_license = evaluate_action(
        {
            "code": "H5",
            "area": "Liechtenstein",
            "partner_company": "7",
            "product": "X",
            "grade": 9,
            "restricted": False,
            "amount_sf": 0,
        },
        quarter="Q4",
        strict=True,
    )
    invalid_loan = evaluate_action(
        {
            "code": "H4",
            "area": "Liechtenstein",
            "partner_company": "7",
            "direction": "lend",
            "currency": "SF",
            "amount_sf": 1_000_000,
            "final_payment_sf": 0,
            "payment_quarter": "Q4",
            "interest_rate": 0,
        },
        quarter="Q4",
        strict=True,
    )

    assert any(row["field"] == "study_id" and row["blocking"] for row in fake_study)
    assert any(row["field"] == "cost_sf" and row["blocking"] for row in fake_study)
    assert any(row["field"] == "amount_sf" and row["blocking"] for row in free_license)
    assert any(row["field"] == "final_payment_sf" and row["blocking"] for row in invalid_loan)
    assert any(row["field"] == "payment_quarter" and row["blocking"] for row in invalid_loan)


def test_transport_and_license_time_lags_are_enforced():
    surface = evaluate_action(
        {"code": "A4", "area": "USA", "target_area": "Europe", "transport_mode": "surface", "same_quarter_use": True},
        quarter="Q4",
    )
    license_checks = evaluate_action(
        {
            "code": "H5",
            "area": "Liechtenstein",
            "product": "Y",
            "grade": 5,
            "license_quarters": 1,
            "licensor_obtained_quarter": "Q4",
        },
        quarter="Q4",
    )
    assert "DL-SURFACE-TRANSFER-LAG" in _failures(surface)
    assert "DL-LICENSE-LAG" in _failures(license_checks)


def test_portfolio_blocks_budget_cash_floor_and_fourth_market_research():
    actions = [
        {"code": "H1-2", "type": "market_research", "study_id": index, "cost_sf": 25_000}
        for index in range(1, 5)
    ]
    result = evaluate_portfolio(
        actions,
        quarter="Q4",
        available_budget_sf=90_000,
        base_cash_sf=150_000,
        cash_buffer_sf=75_000,
    )
    failures = {row["rule_id"] for row in result["violations"]}
    assert result["feasible"] is False
    assert "UI-MR-MAX-THREE" in failures
    assert "DL-PLANT-CASH-PAYMENT" in failures
    assert "STRATEGY-CASH-FLOOR" in failures


def test_report_validation_blocks_quarter_mismatch_and_negative_actuals():
    invalid = validate_report(
        {
            "metadata": {"detected_quarter": "Q2"},
            "operations": [
                {
                    "quarter": "Q2",
                    "area": "Europe",
                    "product": "X",
                    "model": "Standard",
                    "grade": 2,
                    "actual_sales": -1,
                }
            ],
        },
        "Q3",
    )
    valid = validate_report(
        {
            "metadata": {"detected_quarter": "Q3"},
            "operations": [
                {
                    "quarter": "Q3",
                    "area": "Europe",
                    "product": "X",
                    "model": "Standard",
                    "grade": 2,
                    "actual_sales": 1,
                }
            ],
        },
        "Q3",
    )
    assert invalid["status"] == "blocked"
    assert {row["rule_id"] for row in invalid["blocking_issues"]} >= {
        "REPORT-QUARTER-MATCH",
        "REPORT-NONNEGATIVE-OPERATIONS",
    }
    assert valid == {
        "rulebook_version": RULEBOOK_VERSION,
        "status": "passed",
        "checks": [],
        "blocking_issues": [],
        "checked_sections": {
            "finance": False,
            "finance_by_area": 0,
            "operations": 1,
            "research_results": 0,
        },
    }


def test_rulebook_and_decision_pack_apis_apply_the_same_rules(client):
    rulebook = client.get("/api/rulebook")
    assert rulebook.status_code == 200
    assert rulebook.json()["summary"]["version"] == RULEBOOK_VERSION
    assert rulebook.json()["summary"]["total_rules"] >= 50

    legality = client.post(
        "/api/rulebook/check",
        json={
            "quarter": "Q4",
            "action": {
                "code": "A2-4",
                "area": "Europe",
                "product": "Y",
                "grade": 7,
                "x_grade": 0,
                "units": 100,
            },
        },
    )
    assert legality.status_code == 200
    assert legality.json()["allowed"] is False
    assert any(row["rule_id"] == "DL-XY-COMPATIBILITY" for row in legality.json()["violations"])

    pack = client.post(
        "/api/decision-packs",
        json={
            "quarter": "Q4",
            "name": "Illegal Y production",
            "actions": [
                {
                    "code": "A2-4",
                    "area": "Europe",
                    "product": "Y",
                    "model": "Standard",
                    "grade": 7,
                    "x_grade": 0,
                    "units": 100,
                    "variable_cost_sf": 1,
                    "price_sf": 2,
                    "cost_sf": 0,
                }
            ],
        },
    )
    assert pack.status_code == 200, pack.text
    assert pack.json()["status"] == "blocked"
    assert pack.json()["validation"]["readiness"]["status"] == "blocked"
    assert pack.json()["validation"]["readiness"]["required_fixes"]
    assert any(
        row["rule_id"] == "DL-XY-COMPATIBILITY"
        for row in pack.json()["validation"]["violations"]
    )


def test_uploaded_source_chunks_are_searchable_and_candidates_require_human_resolution(client):
    chunk = db.add_document_chunk(
        {
            "source_id": "upload:test-source",
            "section": "Manager instructions",
            "content": "A new plant becomes productive in the following quarter.",
            "metadata": {"evidence_status": "uploaded_unapproved_source"},
        }
    )
    search = client.get("/api/document-chunks", params={"query": "following quarter"})
    assert search.status_code == 200
    assert search.json()[0]["id"] == chunk["id"]

    conflict = db.add_rule_conflict(
        {
            "rule_id": "DL-PLANT-LAG",
            "candidate_source_id": "upload:test-source",
            "candidate_value": {"candidate_kind": "clarification", "name": "Plant timing"},
            "description": "Candidate clarification requires review.",
        }
    )
    assert any(row["id"] == conflict["id"] for row in client.get("/api/rulebook").json()["conflicts"])

    resolved = client.post(
        f"/api/rulebook/conflicts/{conflict['id']}/resolve",
        json={
            "status": "approved_for_next_version",
            "resolution": "Verified against the current game manager instruction.",
        },
    )
    assert resolved.status_code == 200
    assert resolved.json()["conflict"]["status"] == "approved_for_next_version"
    assert all(row["id"] != conflict["id"] for row in client.get("/api/rulebook").json()["conflicts"])

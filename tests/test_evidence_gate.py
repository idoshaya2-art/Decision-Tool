from __future__ import annotations

from evidence_engine import audit_decision_pack_numbers, audit_recommendation_numbers


def _finance(budget: float = 500_000) -> dict:
    return {
        "consolidated": {
            "available_budget_sf": budget,
            "ending_cash_sf": 800_000,
            "cash_buffer_sf": 200_000,
        }
    }


def _operation(price: float = 900) -> dict:
    return {
        "quarter": "Q3",
        "area": "US",
        "product": "Y",
        "model": "Standard",
        "actual_price_lc": price,
        "actual_sales": 850,
        "actual_production": 920,
        "plant_capacity": 1_000,
        "ending_inventory": 70,
    }


def _simulation() -> dict:
    return {
        "scenarios": {
            "downside": {"net_profit_sf": 80_000, "ending_cash_sf": 700_000, "q9_score": 60},
            "base": {"net_profit_sf": 100_000, "ending_cash_sf": 740_000, "q9_score": 64},
            "upside": {"net_profit_sf": 130_000, "ending_cash_sf": 780_000, "q9_score": 68},
        },
        "applied_rules": [
            {"rule_id": "PRICE-STEP", "source_id": "Data Log v1", "page": "12"}
        ],
    }


def test_price_claim_has_actual_source_formula_range_and_assumption_gate():
    result = audit_recommendation_numbers(
        "Q4",
        {
            "id": "Q4-price",
            "action_template": {
                "type": "price_change",
                "area": "US",
                "product": "Y",
                "model": "Standard",
                "current_price_lc": 900,
                "change_pct": 0.03,
                "price_lc": 927,
                "elasticity": 1.0,
            },
        },
        operations=[_operation()],
        finance=_finance(),
        simulation=_simulation(),
    )

    target = next(row for row in result["claims"] if row["metric"] == "price_lc")
    assert target["formula"] == "מחיר Actual × (1 + שיעור שינוי)"
    assert target["source_refs"][0]["field"] == "actual_price_lc"
    assert target["range"]["base"] == 927
    assert result["status"] == "blocked"  # elasticity/change assumptions have no research evidence


def test_price_without_matching_actual_is_blocked():
    result = audit_recommendation_numbers(
        "Q4",
        {
            "id": "Q4-price",
            "action_template": {
                "type": "price_change",
                "area": "Europe",
                "product": "X",
                "model": "Deluxe",
                "change_pct": 0.03,
                "price_lc": 1_030,
            },
        },
        operations=[_operation()],
        finance=_finance(),
        simulation=_simulation(),
    )
    assert result["status"] == "blocked"
    assert any("מחיר Actual" in gap for gap in result["gaps"])


def test_price_contradiction_is_blocked():
    result = audit_recommendation_numbers(
        "Q4",
        {
            "id": "Q4-price",
            "action_template": {
                "type": "price_change",
                "area": "US",
                "product": "Y",
                "model": "Standard",
                "current_price_lc": 700,
                "change_pct": 0.03,
                "price_lc": 927,
            },
        },
        operations=[_operation()],
        finance=_finance(),
        simulation=_simulation(),
    )
    assert result["status"] == "blocked"
    assert result["contradictions"]


def test_decision_pack_gate_blocks_unsupported_numeric_action():
    result = audit_decision_pack_numbers(
        "Q4",
        [{"type": "price_change", "area": "Europe", "product": "X", "price_lc": 1_100}],
        operations=[],
        finance=_finance(),
        simulation=_simulation(),
    )
    assert result["ready_for_decision_pack"] is False
    assert result["blocked_count"] == 1


def test_evidence_gate_api_and_persistence(client):
    assert client.put(
        "/api/finance/Q3",
        json={"revenue_sf": 1_000_000, "net_profit_sf": 50_000, "ending_cash_sf": 700_000},
    ).status_code == 200
    assert client.put(
        "/api/operations",
        json=_operation(),
    ).status_code == 200

    intelligence = client.get("/api/evidence-gate/Q4")
    assert intelligence.status_code == 200
    assert "status" in intelligence.json()
    assert "recommendations" in intelligence.json()

    audited = client.post(
        "/api/evidence-gate/Q4/audit",
        json={
            "name": "Unsupported price",
            "actions": [{"type": "price_change", "area": "Europe", "product": "X", "price_lc": 1_100}],
        },
    )
    assert audited.status_code == 200, audited.text
    assert audited.json()["status"] == "blocked"
    runs = client.get("/api/evidence-gate-runs?quarter=Q4").json()
    assert len(runs) == 1
    assert runs[0]["status"] == "blocked"


def test_decision_pack_is_not_ready_when_number_evidence_is_missing(client):
    assert client.put(
        "/api/finance/Q3",
        json={"revenue_sf": 1_000_000, "net_profit_sf": 50_000, "ending_cash_sf": 700_000},
    ).status_code == 200
    response = client.post(
        "/api/decision-packs",
        json={
            "quarter": "Q4",
            "name": "Evidence blocked pack",
            "actions": [{"type": "price_change", "area": "Europe", "product": "X", "price_lc": 1_100}],
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "blocked_evidence"
    assert data["evidence_gate"]["status"] == "blocked"
    assert data["evidence_gate_run"]["decision_pack_id"] == data["id"]

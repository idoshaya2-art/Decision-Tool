from __future__ import annotations

import copy

from digital_twin import build_digital_twin_state, project_digital_twin


def _baseline():
    financial = {
        "data_as_of": "Q3",
        "actual_coverage": {"complete": True},
        "sources": ["Q3 consolidated finance"],
        "consolidated": {
            "revenue_sf": 1_000_000,
            "net_profit_sf": 100_000,
            "ending_cash_sf": 900_000,
            "debt_sf": 100_000,
            "ar_sf": 200_000,
            "ap_sf": 120_000,
            "inventory_value_sf": 150_000,
            "equity_sf": 1_200_000,
            "working_capital_sf": 230_000,
            "available_budget_sf": 700_000,
            "cash_buffer_sf": 200_000,
        },
        "areas": [
            {"area": "Europe", "currency": "EUR", "ending_cash_sf": 400_000},
            {"area": "USA", "currency": "USD", "ending_cash_sf": 0},
        ],
    }
    operations = [{
        "area": "Europe", "product": "Y", "model": "Standard", "grade": 4,
        "plants": 1, "plant_capacity": 10_000, "ending_inventory": 1_000,
        "actual_production": 8_000, "actual_sales": 7_500, "actual_price_lc": 1_000,
    }]
    return build_digital_twin_state("Q4", financial, operations)


def test_digital_twin_respects_production_and_capacity_lags_without_mutating_actual():
    baseline = _baseline()
    original = copy.deepcopy(baseline)
    actions = [
        {"code": "A2-1", "type": "plant_construction", "area": "Europe", "product": "Y", "plant_count": 1},
        {"code": "A2-4", "type": "production", "area": "Europe", "product": "Y", "model": "Standard", "grade": 4, "units": 2_000, "sell_through": 0.75},
    ]
    impacts = [
        {"cost_sf": 300_000, "profit_delta_sf": -18_000, "capacity_delta_units": 10_000},
        {"cost_sf": 100_000, "revenue_delta_sf": 240_000, "profit_delta_sf": 140_000, "inventory_delta_units": 500},
    ]
    result = project_digital_twin("Q4", baseline, actions, impacts)

    assert baseline == original
    assert result["actuals_mutated"] is False
    q4, q5 = result["timeline"][0], result["timeline"][1]
    assert q4["state"]["consolidated"]["cash_sf"] == 500_000
    assert q4["state"]["segments"][0]["capacity_units"] == 10_000
    assert q4["state"]["segments"][0]["inventory_units"] == 3_000
    assert q5["state"]["segments"][0]["capacity_units"] == 20_000
    assert q5["state"]["segments"][0]["inventory_units"] == 1_500
    assert any(event["kind"] == "capacity_online" for event in q5["events"])


def test_money_transfer_moves_area_cash_without_inflating_consolidated_cash():
    baseline = _baseline()
    result = project_digital_twin(
        "Q4",
        baseline,
        [{
            "code": "A3-1",
            "type": "money_transfer",
            "area": "Europe",
            "target_area": "USA",
            "amount_sf": 100_000,
        }],
        [{"cost_sf": 600, "profit_delta_sf": -600}],
    )

    q4 = result["timeline"][0]["state"]
    areas = {row["area"]: row for row in q4["areas"]}
    assert q4["consolidated"]["cash_sf"] == 899_400
    assert areas["Europe"]["cash_sf"] == 299_400
    assert areas["USA"]["cash_sf"] == 100_000


def test_simulation_api_persists_digital_twin_run(client):
    response = client.post(
        "/api/simulation/Q4",
        json={
            "name": "Twin test",
            "budget_sf": 500_000,
            "cash_buffer_sf": 0,
            "actions": [{"code": "H1-1", "type": "rd", "product": "X", "cost_sf": 100_000}],
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["digital_twin"]["actuals_mutated"] is False
    assert payload["digital_twin"]["base"]["timeline"][0]["quarter"] == "Q4"

    runs = client.get("/api/digital-twin-runs?quarter=Q4")
    assert runs.status_code == 200
    assert runs.json()[0]["scenario_name"] == "Twin test"

    baseline = client.get("/api/digital-twin/Q4")
    assert baseline.status_code == 200
    assert baseline.json()["baseline"]["locked"] is True
    assert baseline.json()["actuals_mutated"] is False

from __future__ import annotations

import db
from learning_engine import build_next_quarter_forecast, evaluate_forecast


def _seed_history(client):
    finance_rows = (
        ("Q1", 1_000_000, 320_000, 80_000, 500_000),
        ("Q2", 1_100_000, 355_000, 90_000, 540_000),
        ("Q3", 1_200_000, 390_000, 100_000, 580_000),
    )
    for quarter, revenue, gross, profit, cash in finance_rows:
        assert client.put(
            f"/api/finance/{quarter}",
            json={
                "revenue_sf": revenue,
                "gross_profit_sf": gross,
                "net_profit_sf": profit,
                "ending_cash_sf": cash,
                "debt_sf": 100_000,
            },
        ).status_code == 200
        assert client.put(
            "/api/operations",
            json={
                "quarter": quarter,
                "area": "Europe",
                "product": "Y",
                "model": "Standard",
                "actual_production": 900 + int(quarter[1:]) * 50,
                "actual_sales": 800 + int(quarter[1:]) * 50,
                "ending_inventory": 100,
                "actual_market_share": 0.18 + int(quarter[1:]) * 0.01,
            },
        ).status_code == 200


def test_learning_engine_builds_ranged_q_plus_one_forecast():
    forecast = build_next_quarter_forecast(
        "Q4",
        [
            {"quarter": "Q1", "revenue_sf": 100, "gross_profit_sf": 30, "net_profit_sf": 10, "ending_cash_sf": 40},
            {"quarter": "Q2", "revenue_sf": 120, "gross_profit_sf": 36, "net_profit_sf": 12, "ending_cash_sf": 45},
            {"quarter": "Q3", "revenue_sf": 140, "gross_profit_sf": 42, "net_profit_sf": 14, "ending_cash_sf": 50},
        ],
        [],
    )
    assert forecast["source_actual_quarter"] == "Q3"
    assert forecast["target_quarter"] == "Q4"
    assert forecast["metrics"]["revenue_sf"]["base"] == 160
    assert forecast["metrics"]["revenue_sf"]["low"] < 160 < forecast["metrics"]["revenue_sf"]["high"]


def test_forecast_evaluation_identifies_demand_driver_and_draft_calibration():
    forecast = {
        "id": "forecast-1",
        "target_quarter": "Q4",
        "source_actual_quarter": "Q3",
        "result": {
            "q_plus_1": {
                "metrics": {
                    "revenue_sf": {"low": 90, "base": 100, "high": 110},
                    "units_sold": {"low": 90, "base": 100, "high": 110},
                }
            }
        },
    }
    result = evaluate_forecast(forecast, {"revenue_sf": 130, "units_sold": 135}, prior_evaluations=1)
    assert result["status"] == "evaluated"
    assert result["summary"]["within_range"] == 0
    assert any(row["driver"] == "demand" for row in result["driver_analysis"])
    assert all(row["status"] == "draft" for row in result["calibration_proposals"])


def test_learning_ledger_api_freezes_evaluates_and_requires_calibration_approval(client):
    _seed_history(client)
    frozen = client.post("/api/learning/forecasts/Q4")
    assert frozen.status_code == 200, frozen.text
    frozen_data = frozen.json()
    assert frozen_data["target_quarter"] == "Q4"
    assert frozen_data["status"] == "open"
    assert frozen_data["result"]["q_plus_1"]["metrics"]["revenue_sf"]["base"] > 0
    assert frozen_data["result"]["q9"]["to_quarter"] == "Q9"

    assert client.put(
        "/api/finance/Q4",
        json={
            "revenue_sf": 1_750_000,
            "gross_profit_sf": 500_000,
            "net_profit_sf": 135_000,
            "ending_cash_sf": 720_000,
            "debt_sf": 100_000,
        },
    ).status_code == 200
    assert client.put(
        "/api/operations",
        json={
            "quarter": "Q4",
            "area": "Europe",
            "product": "Y",
            "model": "Standard",
            "actual_production": 1_250,
            "actual_sales": 1_200,
            "ending_inventory": 50,
            "actual_market_share": 0.28,
        },
    ).status_code == 200

    evaluated = client.post("/api/learning/evaluate/Q4")
    assert evaluated.status_code == 200, evaluated.text
    evaluation = evaluated.json()["evaluations"][0]
    assert evaluation["summary"]["metrics_evaluated"] >= 6
    assert evaluation["driver_analysis"]

    ledger = client.get("/api/learning-ledger?quarter=Q4")
    assert ledger.status_code == 200
    ledger_data = ledger.json()
    assert ledger_data["summary"]["forecast_snapshots"] == 1
    assert ledger_data["summary"]["evaluated_forecasts"] == 1
    proposals = ledger_data["calibration_proposals"]
    assert proposals
    assert all(row["status"] == "draft" for row in proposals)

    proposal = proposals[0]
    reviewed = client.patch(f"/api/calibration-proposals/{proposal['id']}", json={"status": "approved", "reviewed_by": "CFO"})
    assert reviewed.status_code == 200
    assert reviewed.json()["status"] == "approved"
    assert reviewed.json()["reviewed_by"] == "CFO"

    next_forecast = client.post("/api/learning/forecasts/Q5")
    assert next_forecast.status_code == 200, next_forecast.text
    approved_factors = next_forecast.json()["result"]["q_plus_1"]["approved_calibrations"]
    assert proposal["parameter_key"] in approved_factors

    exported = db.export_all_data()
    assert len(exported["forecast_evaluations"]) == 1
    assert len(exported["calibration_proposals"]) >= 1

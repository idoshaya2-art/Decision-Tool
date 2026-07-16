from __future__ import annotations

import io
import zipfile


def _seed_q1_to_q3(client):
    for index, revenue, profit, cash in (
        (1, 1_000_000, 80_000, 600_000),
        (2, 1_200_000, 110_000, 680_000),
        (3, 1_450_000, 155_000, 790_000),
    ):
        assert client.put(
            f"/api/finance/Q{index}",
            json={"revenue_sf": revenue, "gross_profit_sf": revenue * 0.35, "net_profit_sf": profit, "ending_cash_sf": cash, "debt_sf": 120_000},
        ).status_code == 200

    assert client.put(
        "/api/finance/Q3/areas/US",
        json={
            "currency": "USD",
            "fx_to_sf": 1.2,
            "revenue_lc": 500_000,
            "gross_profit_lc": 170_000,
            "net_profit_lc": 55_000,
            "ending_cash_lc": 300_000,
            "debt_lc": 50_000,
            "inventory_value_lc": 40_000,
            "current_assets_lc": 420_000,
            "current_liabilities_lc": 160_000,
            "equity_lc": 300_000,
            "total_investment_lc": 400_000,
            "capex_commitments_lc": 25_000,
        },
    ).status_code == 200
    assert client.put(
        "/api/operations",
        json={
            "quarter": "Q3",
            "area": "US",
            "product": "Y",
            "model": "Standard",
            "grade": 5,
            "plant_capacity": 1000,
            "actual_production": 920,
            "actual_sales": 850,
            "ending_inventory": 70,
            "actual_price_lc": 900,
            "variable_cost_lc": 480,
            "actual_market_share": 0.22,
        },
    ).status_code == 200


def test_q4_planning_uses_q1_to_q3_actuals(client):
    _seed_q1_to_q3(client)

    result = client.get("/api/intelligence/Q4")
    assert result.status_code == 200, result.text
    data = result.json()
    assert data["financial"]["data_as_of"] == "Q3"
    assert data["financial"]["area_data_as_of"] == "Q3"
    assert data["financial"]["consolidated"]["revenue_sf"] == 1_450_000
    assert data["financial"]["areas"][0]["area"] == "US"
    assert data["scorecard"]["past"]["values"]["net_profit_sf"] == 345_000
    assert data["forecast_q9"]["to_quarter"] == "Q9"
    assert data["recommendations"]


def test_file_import_review_commit_and_persistence(client):
    content = b"metric,value\nrevenue,250000\nnet profit,30000\nending cash,90000\n"
    uploaded = client.post(
        "/api/uploads",
        data={"quarter": "Q2", "category": "Quarter output"},
        files={"file": ("Q2.csv", content, "text/csv")},
    )
    assert uploaded.status_code == 200, uploaded.text
    run = uploaded.json()["import_run"]
    assert run["parser_type"] == "csv"
    assert run["extracted_data"]["finance"]["revenue_sf"] == 250000

    committed = client.post(f"/api/imports/{run['id']}/commit")
    assert committed.status_code == 200, committed.text
    assert committed.json()["counts"]["finance"] == 1
    assert client.get("/api/finance/Q2").json()["net_profit_sf"] == 30000

    # Metadata and extracted values must also be part of the complete backup.
    backup = client.get("/api/backup")
    with zipfile.ZipFile(io.BytesIO(backup.content)) as archive:
        database = archive.read("database.json").decode("utf-8")
        assert "report_imports" in database
        assert "Q2.csv" in database


def test_setup_strategy_is_extracted_reviewed_and_used(client):
    content = """אסטרטגיית החברה
יעד Q9: רמת Y7 ונתח שוק 25%
מיקוד: טכנולוגיה ורווחיות
אין להקים מפעל ללא הוכחת ביקוש
מינימום מזומן: 300000 SF
""".encode("utf-8")
    uploaded = client.post(
        "/api/uploads",
        data={"quarter": "Setup", "category": "אסטרטגיה ראשונית"},
        files={"file": ("strategy.txt", content, "text/plain")},
    )
    assert uploaded.status_code == 200, uploaded.text
    run = uploaded.json()["import_run"]
    assert run["extracted_data"]["strategy_profile"]["goals"]
    assert run.get("committed_at") is None

    committed = client.post(f"/api/imports/{run['id']}/commit")
    assert committed.status_code == 200, committed.text
    assert committed.json()["counts"]["strategy_profile"] == 1
    profile = client.get("/api/strategy").json()["profile"]
    assert "Q9" in " ".join(profile["goals"])

    recs = client.get("/api/intelligence/Q4").json()["recommendations"]
    assert all("אסטרטגיה המאושרת" in item["strategy_alignment"] for item in recs)


def test_simulation_enforces_budget_and_returns_three_outcomes(client):
    _seed_q1_to_q3(client)
    client.put("/api/settings", json={"cash_buffer_sf": 700_000})
    response = client.post(
        "/api/simulation/Q4",
        json={
            "name": "Expansion",
            "actions": [
                {"type": "rd", "cost_sf": 250_000},
                {"type": "advertising", "area": "US", "product": "Y", "cost_sf": 120_000, "expected_sales_uplift": 0.08},
            ],
        },
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["feasible"] is False
    assert result["violations"]
    assert set(result["scenarios"]) == {"low", "base", "high"}
    assert result["recommended_sequence"]


def test_decision_agent_is_optional_and_never_requires_a_browser_key(client):
    status = client.get("/api/agent/status")
    assert status.status_code == 200
    assert status.json()["enabled"] is False
    assert "api_key" not in status.text.lower()

    chat = client.post("/api/agent/chat", json={"quarter": "Q4", "question": "What should we do?"})
    assert chat.status_code == 503

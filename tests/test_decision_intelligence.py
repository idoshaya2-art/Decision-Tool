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
    assert data["financial"]["actual_coverage"]["complete"] is True
    assert data["financial"]["actual_coverage"]["expected_as_of"] == "Q3"
    assert data["financial"]["consolidated"]["revenue_sf"] == 1_450_000
    assert data["financial"]["consolidated"]["operating_cash_flow_sf"] is None
    assert data["financial"]["consolidated"]["cash_buffer_configured"] is False
    assert data["financial"]["areas"][0]["area"] == "US"
    assert data["scorecard"]["past"]["values"]["net_profit_sf"] == 345_000
    assert data["forecast_q9"]["to_quarter"] == "Q9"
    assert data["recommendations"]


def test_q4_finance_warns_when_only_q1_actual_is_available(client):
    assert client.put(
        "/api/finance/Q1",
        json={
            "revenue_sf": 0,
            "net_profit_sf": -821_543,
            "ending_cash_sf": 6_562_577,
            "debt_sf": 0,
        },
    ).status_code == 200

    data = client.get("/api/intelligence/Q4").json()["financial"]
    coverage = data["actual_coverage"]
    assert data["data_as_of"] == "Q1"
    assert coverage["complete"] is False
    assert coverage["expected_as_of"] == "Q3"
    assert coverage["missing_quarters"] == ["Q2", "Q3"]
    assert "Q1" in coverage["message"]
    assert "Q4" in coverage["message"]


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


def test_decisions_expose_dependencies_and_execution_order(client):
    _seed_q1_to_q3(client)
    intelligence = client.get("/api/intelligence/Q4")
    assert intelligence.status_code == 200, intelligence.text
    graph = intelligence.json()["decision_dependencies"]
    assert graph["recommended_sequence"]
    assert graph["budget_coordination"]["planned_cost_sf"] >= 0
    assert all("dependencies" in row for row in intelligence.json()["recommendations"])

    response = client.post(
        "/api/simulation/Q4",
        json={
            "name": "Coordinated X-Y launch",
            "actions": [
                {"code": "A2-3", "type": "production", "area": "US", "product": "X", "units": 600, "cost_sf": 60_000},
                {"code": "A2-4", "type": "production", "area": "US", "product": "Y", "units": 300, "x_grade": 5, "grade": 5, "cost_sf": 120_000},
                {"code": "A1-2", "type": "price_advertising", "area": "US", "product": "Y", "change_pct": 0.02, "cost_sf": 20_000},
            ],
        },
    )
    assert response.status_code == 200, response.text
    result = response.json()
    dependencies = result["dependency_analysis"]
    x_node = next(row for row in dependencies["nodes"] if row["code"] == "A2-3")
    y_node = next(row for row in dependencies["nodes"] if row["code"] == "A2-4")
    marketing_node = next(row for row in dependencies["nodes"] if row["code"] == "A1-2")
    assert any(
        edge["from"] == x_node["id"]
        and edge["to"] == y_node["id"]
        and edge["kind"] == "prerequisite"
        for edge in dependencies["edges"]
    )
    assert any(
        edge["from"] == y_node["id"]
        and edge["to"] == marketing_node["id"]
        and edge["kind"] == "coordination"
        for edge in dependencies["edges"]
    )
    ordered_ids = [row["action"]["code"] for row in result["recommended_sequence"]]
    assert ordered_ids.index("A2-3") < ordered_ids.index("A2-4")


def test_strategy_optimization_rolls_from_latest_actual_to_q9(client):
    strategy_text = """אסטרטגיית החברה
יעד Q9: רמת Y7 ונתח שוק 25%
מיקוד: טכנולוגיה ורווחיות
אין להקים מפעל ללא הוכחת ביקוש
מינימום מזומן: 300000 SF
""".encode("utf-8")
    uploaded = client.post(
        "/api/uploads",
        data={"quarter": "Setup", "category": "אסטרטגיה ראשונית"},
        files={"file": ("strategy.txt", strategy_text, "text/plain")},
    )
    assert uploaded.status_code == 200, uploaded.text
    assert client.post(f"/api/imports/{uploaded.json()['import_run']['id']}/commit").status_code == 200

    assert client.put(
        "/api/finance/Q1",
        json={
            "revenue_sf": 1_000_000,
            "gross_profit_sf": 350_000,
            "net_profit_sf": 80_000,
            "ending_cash_sf": 600_000,
            "debt_sf": 120_000,
        },
    ).status_code == 200
    first = client.get("/api/strategy-optimization/Q4")
    assert first.status_code == 200, first.text
    first_data = first.json()
    assert first_data["status"] in {"ready", "blocked"}
    assert first_data["actual_as_of"] == "Q1"
    assert first_data["next_decision_quarter"] == "Q2"
    assert first_data["horizon"] == [f"Q{index}" for index in range(2, 10)]
    assert first_data["objective"]["past_weight"] == 0.5
    assert first_data["objective"]["future_weight"] == 0.5
    assert first_data["source_strategy"]["approved"] is True
    assert len(first_data["scenarios"]) == 4
    assert len(first_data["recommended_plan"]["roadmap"]) == 8

    assert client.put(
        "/api/finance/Q2",
        json={
            "revenue_sf": 1_200_000,
            "gross_profit_sf": 420_000,
            "net_profit_sf": 110_000,
            "ending_cash_sf": 680_000,
            "debt_sf": 110_000,
        },
    ).status_code == 200
    second = client.get("/api/strategy-optimization/Q4")
    assert second.status_code == 200, second.text
    second_data = second.json()
    assert second_data["actual_as_of"] == "Q2"
    assert second_data["next_decision_quarter"] == "Q3"
    assert second_data["horizon"][0] == "Q3"
    assert len(second_data["recommended_plan"]["roadmap"]) == 7


def test_strategy_optimization_is_read_only_and_explains_missing_strategy(client):
    assert client.put(
        "/api/finance/Q1",
        json={"revenue_sf": 500_000, "net_profit_sf": 20_000, "ending_cash_sf": 200_000},
    ).status_code == 200
    before = client.get("/api/finance/Q1").json()
    response = client.get("/api/strategy-optimization/Q4")
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "needs_strategy"
    assert result["source_strategy"]["approved"] is False
    assert any(gate["title"] == "לא אושרה אסטרטגיה ראשונית" for gate in result["recommended_plan"]["decision_gates"])
    assert client.get("/api/finance/Q1").json() == before


def test_strategy_optimization_does_not_treat_planning_quarter_as_actual(client):
    response = client.get("/api/strategy-optimization/Q4")
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "needs_data"
    assert result["actual_as_of"] is None
    assert result["next_decision_quarter"] is None
    assert result["horizon"] == []
    assert all(scenario["feasible"] is False for scenario in result["scenarios"])
    assert any("Actual" in gate["title"] for gate in result["recommended_plan"]["decision_gates"])


def test_decision_agent_is_optional_and_never_requires_a_browser_key(client):
    status = client.get("/api/agent/status")
    assert status.status_code == 200
    assert status.json()["enabled"] is False
    # The readiness response may name the missing server-side environment
    # variable, but it must never expose an actual secret value.
    assert "sk-" not in status.text.lower()
    assert "openai_api_key" in [item.lower() for item in status.json()["missing"]]

    chat = client.post("/api/agent/chat", json={"quarter": "Q4", "question": "What should we do?"})
    assert chat.status_code == 503

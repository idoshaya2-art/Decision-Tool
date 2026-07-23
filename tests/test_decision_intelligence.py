from __future__ import annotations

import io
import zipfile

from analytics import (
    analyze_decision_dependencies,
    build_execution_blueprint,
    financial_position,
    liquidity_allocation_plan,
    review_decision_catalog,
    simulate_portfolio,
)
from intopia_rules import DECISION_ACTIONS


def test_decision_pack_blocks_outflow_above_source_area_cash():
    result = simulate_portfolio(
        "Q4",
        {
            "decision_pack": True,
            "budget_sf": 1_000_000,
            "cash_buffer_sf": 0,
            "actions": [
                {
                    "code": "A3-1",
                    "type": "money_transfer",
                    "area": "Europe",
                    "target_area": "Liechtenstein",
                    "amount_sf": 900_000,
                }
            ],
        },
        {
            "consolidated": {
                "ending_cash_sf": 1_200_000,
                "available_budget_sf": 1_000_000,
            },
            "areas": [
                {
                    "area": "Europe",
                    "ending_cash_sf": 100_000,
                    "capex_commitments_sf": 0,
                }
            ],
        },
        {"score": {"base": 50}},
        [],
    )

    assert result["feasible"] is False
    assert result["rule_validation"]["readiness"]["status"] == "blocked"
    assert any(
        row["rule_id"] == "AREA-LIQUIDITY-SOURCE"
        for row in result["rule_validation"]["violations"]
    )


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
    assert "liquidity_allocation" in data["financial"]
    assert data["latest_operations"][0]["product"] == "Y"
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


def test_consolidated_balance_uses_official_total_instead_of_summing_internal_controls():
    result = financial_position(
        "Q4",
        [
            {
                "quarter": "Q3",
                "ending_cash_sf": 1_067_452,
                "debt_sf": 643_433,
                "notes": (
                    'Official. [[BALANCE:{"inventory_value_sf":2251199,'
                    '"current_assets_sf":3318651,"current_liabilities_sf":2144512,'
                    '"total_assets_sf":8358651,"total_liabilities_sf":2787945,'
                    '"equity_sf":5570707}]]'
                ),
            }
        ],
        [
            {
                "quarter": "Q3",
                "area": "Europe",
                "fx_to_sf": 1.5,
                "equity_lc": 3_717_001,
                "current_assets_lc": 1_500_800,
                "current_liabilities_lc": 1_143_798,
                "inventory_value_lc": 1_500_800,
                "total_investment_lc": 4_860_800,
            },
            {
                "quarter": "Q3",
                "area": "Liechtenstein",
                "fx_to_sf": 1,
                "equity_lc": 6_162_397,
                "current_assets_lc": 20_000,
                "current_liabilities_lc": 424_170,
                "total_investment_lc": 7_230_000,
            },
        ],
        0,
    )
    consolidated = result["consolidated"]
    assert consolidated["equity_sf"] == 5_570_707
    assert consolidated["total_investment_sf"] == 8_358_651
    assert consolidated["current_assets_sf"] == 3_318_651


def test_liquidity_plan_finds_cross_area_transfer_and_keeps_source_reserve():
    plan = liquidity_allocation_plan(
        [
            {
                "area": "Brazil",
                "currency": "BRL",
                "fx_to_sf": 0.5,
                "ending_cash_sf": 1_047_452,
                "current_liabilities_sf": 4_644,
            },
            {
                "area": "Europe",
                "currency": "EUR",
                "fx_to_sf": 1.5,
                "ending_cash_sf": 0,
                "current_liabilities_sf": 1_715_697,
                "ap_sf": 1_715_697,
            },
            {
                "area": "Liechtenstein",
                "currency": "CHF",
                "fx_to_sf": 1,
                "ending_cash_sf": 20_000,
                "current_liabilities_sf": 424_170,
                "debt_sf": 643_433,
            },
        ],
        {
            "ending_cash_sf": 1_067_452,
            "current_liabilities_sf": 2_144_512,
            "data_as_of": "Q3",
        },
    )
    assert plan["status"] == "action_required"
    assert plan["cash_concentration"]["area"] == "Brazil"
    assert plan["cash_concentration"]["share"] > 0.98
    assert [row["target_area"] for row in plan["transfers"]] == ["Europe", "Liechtenstein"]
    europe = plan["transfers"][0]
    assert europe["source_area"] == "Brazil"
    assert europe["net_amount_sf"] == 428_924.25
    assert europe["estimated_fx_fee_sf"] > 0
    brazil = next(row for row in plan["areas"] if row["area"] == "Brazil")
    assert plan["transfers"][-1]["source_cash_after_sf"] >= brazil["recommended_reserve_sf"]


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


def test_ai_recommendation_and_scenario_lab_share_the_same_numeric_engine(client):
    _seed_q1_to_q3(client)
    intelligence = client.get("/api/intelligence/Q4")
    assert intelligence.status_code == 200, intelligence.text
    bundle = intelligence.json()
    recommendation = next(
        row for row in bundle["recommendations"]
        if row.get("action_template")
    )
    action = {
        **recommendation["action_template"],
        "title": recommendation["title"],
    }
    baseline = bundle["financial"]["consolidated"]

    simulated = client.post(
        "/api/simulation/Q4",
        json={
            "name": f"Regression: {recommendation['title']}",
            "budget_sf": baseline["available_budget_sf"],
            "cash_buffer_sf": baseline["cash_buffer_sf"],
            "actions": [action],
        },
    )
    assert simulated.status_code == 200, simulated.text
    result = simulated.json()
    base_case = result["scenarios"]["base"]
    impact = recommendation["economic_impact"]

    assert impact["cost_sf"] == result["budget"]["planned_cost_sf"]
    assert impact["budget_remaining_sf"] == result["budget"]["remaining_sf"]
    assert impact["feasible"] == result["feasible"]
    assert impact["profit_delta_sf"] == round(
        float(base_case.get("net_profit_sf") or 0)
        - float(baseline.get("net_profit_sf") or 0),
        2,
    )
    assert impact["cash_delta_sf"] == round(
        float(base_case.get("ending_cash_sf") or 0)
        - float(baseline.get("ending_cash_sf") or 0),
        2,
    )


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


def test_execution_blueprint_has_exact_values_and_hard_dependencies():
    actions = [
        {
            "code": "A3-1",
            "type": "money_transfer",
            "area": "Brazil",
            "target_area": "Europe",
            "source_currency": "BRL",
            "target_currency": "EUR",
            "source_amount_lc": 864_766.63,
            "net_amount_sf": 428_924.25,
            "gross_source_amount_sf": 432_383.32,
            "estimated_fx_fee_sf": 3_459.07,
            "amount_sf": 428_924.25,
            "cost_sf": 3_459.07,
            "source_cash_after_sf": 615_068.68,
            "target_cash_after_sf": 428_924.25,
            "_recommendation_id": "transfer-eu",
            "title": "Brazil → Europe liquidity",
        },
        {
            "code": "H1-1",
            "type": "rd",
            "area": "Europe",
            "product": "Y",
            "amount_sf": 120_000,
            "cost_sf": 120_000,
            "_recommendation_id": "rd-y",
            "title": "Y research and development",
        },
    ]
    graph = analyze_decision_dependencies(
        "Q4",
        actions,
        [],
        available_budget_sf=500_000,
    )
    assert any(
        edge["from"] == "transfer-eu"
        and edge["to"] == "rd-y"
        and edge["kind"] == "funding"
        and edge["hard"] is True
        for edge in graph["edges"]
    )
    blueprint = build_execution_blueprint("Q4", actions, graph)
    transfer = next(row for row in blueprint["rows"] if row["id"] == "transfer-eu")
    rd = next(row for row in blueprint["rows"] if row["id"] == "rd-y")
    assert transfer["form_code"] == "A3-1"
    assert transfer["recommended_value"] == "864,766.63 BRL"
    assert "864,766.63 BRL" in transfer["input_instruction"]
    assert "None" not in transfer["input_instruction"]
    assert "428,924.25 SF" in transfer["expected_outcome"]
    assert rd["recommended_value"] == "120,000 SF"
    assert rd["dependencies"][0]["id"] == "transfer-eu"
    assert transfer["order"] < rd["order"]


def test_execution_blueprint_links_x_supply_to_y_and_industrial_sale():
    actions = [
        {
            "code": "A2-3",
            "type": "production",
            "area": "US",
            "product": "X",
            "units": 1_000,
            "cost_sf": 50_000,
            "id": "x-production",
        },
        {
            "code": "A4",
            "type": "component_transfer",
            "area": "US",
            "target_area": "Europe",
            "product": "X",
            "units": 800,
            "cost_sf": 10_000,
            "id": "x-transfer",
        },
        {
            "code": "A2-4",
            "type": "production",
            "area": "Europe",
            "product": "Y",
            "units": 400,
            "x_grade": 5,
            "grade": 5,
            "cost_sf": 100_000,
            "id": "y-production",
        },
        {
            "code": "H6",
            "type": "industrial_sale",
            "area": "Europe",
            "product": "Y",
            "units": 300,
            "id": "y-sale",
        },
    ]
    graph = analyze_decision_dependencies(
        "Q4",
        actions,
        [],
        available_budget_sf=500_000,
    )
    edges = {(row["from"], row["to"], row["kind"]) for row in graph["edges"]}
    assert ("x-production", "x-transfer", "prerequisite") in edges
    assert ("x-transfer", "y-production", "prerequisite") in edges
    assert ("y-production", "y-sale", "prerequisite") in edges
    order = [row["id"] for row in graph["recommended_sequence"]]
    assert order.index("x-production") < order.index("x-transfer")
    assert order.index("x-transfer") < order.index("y-production")
    assert order.index("y-production") < order.index("y-sale")


def test_head_office_market_research_informs_regional_pricing():
    actions = [
        {
            "code": "H1-2",
            "type": "market_research",
            "area": "Liechtenstein",
            "product": "Y",
            "studies": [28, 61],
            "id": "research-y",
        },
        {
            "code": "A1-2",
            "type": "price_advertising",
            "area": "Europe",
            "product": "Y",
            "id": "price-y-europe",
        },
    ]
    graph = analyze_decision_dependencies(
        "Q4",
        actions,
        [],
        available_budget_sf=100_000,
    )
    edges = {(row["from"], row["to"], row["kind"]) for row in graph["edges"]}
    assert ("research-y", "price-y-europe", "prerequisite") in edges


def test_intelligence_returns_execution_blueprint(client):
    _seed_q1_to_q3(client)
    data = client.get("/api/intelligence/Q4").json()
    blueprint = data["execution_blueprint"]
    assert blueprint["rows"]
    assert blueprint["summary"]["row_count"] == len(blueprint["rows"])
    assert all(
        {
            "order",
            "form_code",
            "field_name",
            "recommended_value",
            "status",
            "gate",
            "expected_outcome",
            "input_instruction",
            "dependencies",
        }.issubset(row)
        for row in blueprint["rows"]
    )


def test_intelligence_reviews_every_official_action_before_recommending(client):
    _seed_q1_to_q3(client)
    data = client.get("/api/intelligence/Q4").json()
    review = data["action_review"]

    assert review["evaluation_order"] == "full_catalog_before_recommendation_filter"
    assert review["summary"]["evaluated_count"] == len(DECISION_ACTIONS) == 19
    assert review["summary"]["catalog_count"] == len(DECISION_ACTIONS)
    assert review["summary"]["coverage_pct"] == 100
    assert {category["key"] for category in review["categories"]} == {
        "strategy",
        "finance",
        "operations",
        "marketing",
    }
    assert {action["code"] for action in review["actions"]} == {
        action["code"] for action in DECISION_ACTIONS
    }
    assert all(action["rules_checked"] for action in review["actions"])
    assert all(
        action["status"]
        in {
            "recommended",
            "required",
            "blocked",
            "missing_data",
            "monitor",
            "not_required",
        }
        for action in review["actions"]
    )


def test_decision_catalog_links_market_research_to_relevant_category():
    review = review_decision_catalog(
        "Q4",
        {
            "consolidated": {
                "ending_cash_sf": 900_000,
                "available_budget_sf": 500_000,
                "debt_sf": 100_000,
            },
            "areas": [],
            "liquidity_allocation": {"funding_gaps": [], "transfers": []},
        },
        [
            {
                "quarter": "Q3",
                "area": "Europe",
                "product": "Y",
                "actual_price_lc": 900,
                "actual_sales": 850,
                "ending_inventory": 70,
                "plant_capacity": 1_000,
                "actual_production": 920,
                "grade": 5,
            }
        ],
        [
            {
                "quarter": "Q3",
                "study_id": 28,
                "source_label": "Q3 · MR28",
                "headline": "מחירי המתחרים באירופה",
            },
            {
                "quarter": "Q3",
                "study_id": 61,
                "source_label": "Q3 · MR61",
                "headline": "עלות משתנה למוצר Y1",
            },
        ],
        [],
        {"rows": [], "summary": {}},
    )

    pricing = next(action for action in review["actions"] if action["code"] == "A1-2")
    production = next(action for action in review["actions"] if action["code"] == "A2-4")
    assert [row["study_id"] for row in pricing["research_used"]] == [28]
    assert [row["study_id"] for row in production["research_used"]] == [61]
    assert pricing["category"] == "marketing"
    assert production["category"] == "operations"


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

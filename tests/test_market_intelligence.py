from market_intelligence import build_market_intelligence, research_decision_map


def test_all_catalog_studies_are_mapped_to_decisions_or_variables():
    catalog = [
        {"study_id": 28, "name": "Prices", "cost_k_sf": 0},
        {"study_id": 24, "name": "Optimal capacity", "cost_k_sf": 24},
        {"study_id": 65, "name": "Y5 cost", "cost_k_sf": 10},
        {"study_id": 81, "name": "Sales offices", "cost_k_sf": 60},
    ]
    mapped = research_decision_map(catalog)
    assert all(row["actions"] and row["variables"] for row in mapped)
    assert mapped[0]["knowledge_type"] == "direct_parameter"


def test_elasticity_is_blocked_without_three_observations_and_two_price_changes():
    result = build_market_intelligence(
        "Q3",
        [{"study_id": 28, "name": "Prices", "cost_k_sf": 0}],
        [],
        [
            {"quarter": "Q1", "area": "EU", "product": "Y", "model": "Standard", "price_lc": 100, "sales": 1000},
            {"quarter": "Q2", "area": "EU", "product": "Y", "model": "Standard", "price_lc": 110, "sales": 900},
        ],
        [],
    )
    signal = result["calibration_signals"][0]
    assert signal["status"] == "insufficient_observations"
    assert signal["elasticity_estimate"] is None


def test_voi_is_not_monetized_without_auditable_decision_exposure():
    result = build_market_intelligence(
        "Q4",
        [{"study_id": 24, "name": "Optimal production", "cost_k_sf": 24}],
        [],
        [],
        [{"title": "Production decision", "action_template": {"code": "A2-4"}}],
    )
    recommendation = result["recommended_research"][0]
    assert recommendation["study_id"] == 24
    assert recommendation["value_status"] == "qualitative_only"
    assert recommendation["net_voi_sf"] is None


def test_approved_research_is_classified_and_linked_to_actions():
    result = build_market_intelligence(
        "Q3",
        [{"study_id": 28, "name": "Prices", "cost_k_sf": 0}],
        [{"id": "r1", "quarter": "Q3", "study_id": 28, "title": "MR28", "status": "approved", "numeric_data": {"entries": []}}],
        [],
        [],
    )
    mapped = result["mapped_results"][0]
    assert mapped["knowledge_type"] == "direct_parameter"
    assert "A1-1" in mapped["affected_actions"]
    assert result["available_studies"] == [28]

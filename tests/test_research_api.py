def test_relevant_research_reuses_market_intelligence_bundle(client):
    response = client.get("/api/research/relevant/Q4")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["quarter"] == "Q4"
    assert isinstance(payload["results"], list)
    assert isinstance(payload["catalog"], list)
    assert "market_intelligence" in payload
    assert isinstance(payload["market_intelligence"], dict)

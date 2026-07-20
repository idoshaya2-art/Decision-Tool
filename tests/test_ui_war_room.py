from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
APP = (ROOT / "static" / "app.js").read_text(encoding="utf-8")


def test_war_room_uses_single_hamburger_navigation_and_progressive_disclosure():
    assert 'id="menuButton"' in INDEX
    assert 'id="sideNav"' in INDEX
    assert '<nav class="primary-tabs"' not in INDEX
    assert 'class="analyst-disclosure"' in INDEX


def test_q9_strip_exposes_score_liquidity_and_blocking_signals():
    for element_id in (
        "q9Score",
        "pastScore",
        "futureScore",
        "liquidityPosition",
        "decisionBlockers",
    ):
        assert f'id="{element_id}"' in INDEX
    assert 'id="decisionGateBanner"' in INDEX


def test_recommendations_require_actuals_and_compare_ai_with_team():
    assert "אין עדיין בסיס מאושר להמלצות" in APP
    assert "actualCoverage.data_as_of" in APP
    assert 'class="team-ai-compare"' in APP
    assert "הצעת AI המספרית" in APP
    assert "החלטת הצוות" in APP
    assert "data-adopt-recommendation" in APP
    assert "data-save-team-recommendation" in APP
    assert 'status: adoptIndex != null ? "מוכן לאישור" : "טיוטה"' in APP


def test_decision_pack_ui_explains_blocking_fixes():
    assert "pack.validation?.readiness" in APP
    assert "מה בדיוק לתקן לפני אישור" in APP
    assert "required_fixes" in APP


def test_navigation_manages_focus_when_the_hamburger_is_closed():
    assert "sideNav.inert = true" in APP
    assert "sideNav.inert = false" in APP
    assert "menuReturnFocus" in APP

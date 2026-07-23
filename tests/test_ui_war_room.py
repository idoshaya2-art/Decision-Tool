from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
APP = (ROOT / "static" / "app.js").read_text(encoding="utf-8")


def test_war_room_uses_single_hamburger_navigation_and_progressive_disclosure():
    assert 'id="menuButton"' in INDEX
    assert 'id="sideNav"' in INDEX
    assert '<nav class="primary-tabs"' not in INDEX
    assert 'class="analyst-disclosure"' in INDEX
    assert 'id="moreToolsNav"' in INDEX
    assert 'class="supporting-insights"' in INDEX


def test_dashboard_has_a_clear_five_step_operating_flow():
    assert 'class="decision-flow"' in INDEX
    for target in ("decisionSnapshot", "decisionPriority", "decisionImpact", "decisionApproval"):
        assert f'data-scroll-target="{target}"' in INDEX
        assert f'id="{target}"' in INDEX
    assert 'id="flowDataStep"' in INDEX
    assert 'data-go="files"' in INDEX
    assert "קליטה ואישור" in INDEX
    assert "סימולציה ובחירה" in INDEX
    assert 'dataStep.classList.toggle("complete", Boolean(actual))' in APP
    assert '$$("[data-scroll-target]")' in APP


def test_dashboard_prioritizes_three_recommendations_and_preserves_the_rest():
    assert "indexedRows.slice(0, 3)" in APP
    assert 'class="more-recommendations"' in APP
    assert "המלצות נוספות" in APP


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


def test_dashboard_context_is_dynamic_and_has_no_fixed_q1_q3_copy():
    assert 'id="dashboardQuarterEyebrow"' in INDEX
    assert 'id="dashboardContextText"' in INDEX
    assert "renderDynamicQuarterContext" in APP
    assert "actualDataQuarter" in APP
    assert "Q4 PLANNING ROOM" not in INDEX
    assert "תמונת פתיחה המבוססת על Q1–Q3" not in INDEX


def test_optional_history_modules_do_not_hide_primary_data():
    assert "for (const [label, loader] of modules)" in APP
    assert "Promise.allSettled(modules.map" not in APP
    assert "state.currentReport" in APP
    assert "data.market_intelligence" in APP
    assert "if (decisionsResult.status === \"rejected\") throw decisionsResult.reason" in APP


def test_static_app_cache_key_is_advanced_for_truth_foundation_release():
    assert '/static/app.js?v=2.1.0' in INDEX
    assert '/static/styles.css?v=2.1.0' in INDEX

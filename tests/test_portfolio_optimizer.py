from portfolio_optimizer import optimize_q9_portfolio


def _candidate(key: str, *, delta: float, cost: float = 0, gate: str = "ready"):
    return {
        "id": key,
        "title": key,
        "priority": delta,
        "number_gate": {"status": gate},
        "economic_impact": {
            "q9_score_delta": delta,
            "past_score_delta": delta / 2,
            "future_score_delta": delta,
        },
        "action_template": {"type": key, "code": key, "cost_sf": cost},
    }


def _simulator(_name, actions):
    codes = {action["code"] for action in actions}
    cost = sum(float(action.get("cost_sf") or 0) for action in actions)
    feasible = cost <= 100
    gaps = []
    if "growth" in codes and "research" not in codes:
        gaps.append({"missing": "research", "reason": "growth requires research"})
    uplift = (5 if "research" in codes else 0) + (12 if "growth" in codes else 0)
    return {
        "feasible": feasible,
        "scenarios": {
            "low": {"q9_score": 50 + uplift * 0.5},
            "base": {"q9_score": 50 + uplift},
            "high": {"q9_score": 50 + uplift * 1.2},
        },
        "budget": {"planned_cost_sf": cost, "remaining_sf": 100 - cost},
        "dependency_analysis": {
            "gaps": gaps,
            "conflicts": [],
            "recommended_sequence": [
                {"step": index + 1, "action": action, "depends_on": []}
                for index, action in enumerate(actions)
            ],
        },
        "violations": [] if feasible else ["over budget"],
        "warnings": [],
    }


def test_optimizer_selects_integrated_feasible_basket_with_prerequisite():
    result = optimize_q9_portfolio(
        "Q4",
        [_candidate("growth", delta=12, cost=60), _candidate("research", delta=3, cost=10)],
        _simulator,
        50,
    )
    assert result["status"] == "optimized"
    assert set(result["winner"]["action_ids"]) == {"growth", "research"}
    assert result["winner"]["feasible"] is True


def test_optimizer_excludes_evidence_blocked_number():
    result = optimize_q9_portfolio(
        "Q4",
        [_candidate("blocked", delta=99, gate="blocked"), _candidate("research", delta=3)],
        _simulator,
        50,
    )
    assert result["excluded_candidates"][0]["reason"] == "numeric_evidence_blocked"
    assert "blocked" not in result["winner"]["action_ids"]


def test_optimizer_rejects_over_budget_and_dependency_gap():
    result = optimize_q9_portfolio(
        "Q4",
        [_candidate("growth", delta=12, cost=120)],
        _simulator,
        50,
    )
    assert result["winner"]["action_count"] == 0
    rejected = [row for row in result["alternatives"] if "growth" in row["action_ids"]]
    assert not rejected


def test_optimizer_reports_weight_sensitivity_for_approved_50_50_objective():
    result = optimize_q9_portfolio(
        "Q4",
        [_candidate("research", delta=3, cost=10)],
        _simulator,
        50,
    )
    assert [(row["past_weight"], row["future_weight"]) for row in result["weight_sensitivity"]] == [
        (0.4, 0.6),
        (0.5, 0.5),
        (0.6, 0.4),
    ]
    assert isinstance(result["robust_to_weight_sensitivity"], bool)

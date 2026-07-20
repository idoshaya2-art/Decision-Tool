import pytest

from group_governance import build_session_gate, build_validation_snapshot, validate_vote


PASSING_VALIDATION = {
    "optimizer_feasible": True,
    "evidence_status": "pass",
    "rules_pass": True,
    "budget_pass": True,
    "dependencies_pass": True,
    "timing_pass": True,
}


def _votes(*, reject_role=None):
    roles = ["finance", "marketing", "operations", "strategy", "chair"]
    return [
        {"role": role, "voter_name": role, "vote": "reject" if role == reject_role else "approve", "rationale": "reviewed"}
        for role in roles
    ]


def test_session_gate_requires_machine_controls_and_all_roles():
    gate = build_session_gate(PASSING_VALIDATION, _votes()[:-1])
    assert gate["can_approve"] is False
    assert gate["status"] == "awaiting_roles"
    assert gate["missing_roles"] == ["chair"]


def test_session_gate_allows_four_of_five_only_when_non_blocking_role_dissents():
    gate = build_session_gate(PASSING_VALIDATION, _votes(reject_role="marketing"))
    assert gate["can_approve"] is True
    assert gate["status"] == "ready_to_approve"
    assert gate["rejections"] == ["marketing"]


def test_finance_rejection_blocks_even_with_four_approvals():
    gate = build_session_gate(PASSING_VALIDATION, _votes(reject_role="finance"))
    assert gate["can_approve"] is False
    assert gate["status"] == "changes_requested"
    assert gate["blocking_rejections"] == ["finance"]


def test_evidence_failure_blocks_unanimous_human_vote():
    gate = build_session_gate({**PASSING_VALIDATION, "evidence_status": "conditional"}, _votes())
    assert gate["can_approve"] is False
    assert gate["status"] == "blocked_by_controls"
    assert "evidence_pass" in gate["failed_machine_checks"]


def test_validation_snapshot_checks_budget_dependencies_and_rules():
    optimization = {
        "status": "optimized",
        "winner": {
            "feasible": True,
            "simulation": {
                "feasible": True,
                "budget": {"remaining_sf": 10},
                "dependency_analysis": {"gaps": [], "conflicts": []},
                "rule_validation": {"allowed": True, "violations": []},
                "violations": [],
                "rulebook_version": "1.0",
            },
        },
    }
    snapshot = build_validation_snapshot(optimization, {"status": "pass", "score": 100})
    assert snapshot["optimizer_feasible"] is True
    assert snapshot["budget_pass"] is True
    assert snapshot["dependencies_pass"] is True
    assert snapshot["rules_pass"] is True


def test_reject_vote_requires_rationale():
    with pytest.raises(ValueError):
        validate_vote({"role": "finance", "voter_name": "Dana", "vote": "reject", "rationale": ""})

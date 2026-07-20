from __future__ import annotations

from typing import Any


REQUIRED_ROLES = (
    ("finance", "כספים ונזילות"),
    ("marketing", "שיווק ותמחור"),
    ("operations", "תפעול ושרשרת אספקה"),
    ("strategy", "אסטרטגיה ו־Q9"),
    ("chair", "מוביל/ת הישיבה"),
)

BLOCKING_ROLES = {"finance", "operations", "strategy", "chair"}
VALID_VOTES = {"approve", "reject", "abstain"}


def role_catalog() -> list[dict[str, str]]:
    return [{"role": role, "label": label} for role, label in REQUIRED_ROLES]


def build_session_gate(
    validation: dict[str, Any],
    votes: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return an explainable, deterministic approval gate for a team session."""
    latest_by_role: dict[str, dict[str, Any]] = {}
    for row in votes:
        role = str(row.get("role") or "")
        if role in dict(REQUIRED_ROLES):
            latest_by_role[role] = row

    missing_roles = [role for role, _label in REQUIRED_ROLES if role not in latest_by_role]
    approvals = [role for role, row in latest_by_role.items() if row.get("vote") == "approve"]
    rejections = [role for role, row in latest_by_role.items() if row.get("vote") == "reject"]
    blocking_rejections = [role for role in rejections if role in BLOCKING_ROLES]
    abstentions = [role for role, row in latest_by_role.items() if row.get("vote") == "abstain"]

    machine_checks = {
        "optimizer_feasible": bool(validation.get("optimizer_feasible")),
        "evidence_pass": validation.get("evidence_status") == "pass",
        "rules_pass": bool(validation.get("rules_pass")),
        "budget_pass": bool(validation.get("budget_pass")),
        "dependencies_pass": bool(validation.get("dependencies_pass")),
        "timing_pass": bool(validation.get("timing_pass", True)),
    }
    failed_machine_checks = [key for key, passed in machine_checks.items() if not passed]
    human_ready = (
        not missing_roles
        and len(approvals) >= 4
        and not blocking_rejections
        and latest_by_role.get("chair", {}).get("vote") == "approve"
    )
    can_approve = not failed_machine_checks and human_ready
    if failed_machine_checks:
        status = "blocked_by_controls"
    elif missing_roles:
        status = "awaiting_roles"
    elif blocking_rejections:
        status = "changes_requested"
    elif not human_ready:
        status = "awaiting_consensus"
    else:
        status = "ready_to_approve"

    return {
        "status": status,
        "can_approve": can_approve,
        "machine_checks": machine_checks,
        "failed_machine_checks": failed_machine_checks,
        "required_roles": role_catalog(),
        "missing_roles": missing_roles,
        "approvals": approvals,
        "rejections": rejections,
        "blocking_rejections": blocking_rejections,
        "abstentions": abstentions,
        "vote_count": len(latest_by_role),
        "approval_count": len(approvals),
        "policy": {
            "quorum": "all five roles must record a vote",
            "majority": "at least four approvals",
            "blocking_roles": sorted(BLOCKING_ROLES),
            "chair_approval_required": True,
            "dissent_is_preserved": True,
            "approval_never_submits_to_intopia": True,
        },
    }


def build_validation_snapshot(
    optimization: dict[str, Any],
    evidence_gate: dict[str, Any],
) -> dict[str, Any]:
    winner = optimization.get("winner") or {}
    simulation = winner.get("simulation") or {}
    dependencies = simulation.get("dependency_analysis") or {}
    validation = simulation.get("rule_validation") or {}
    violations = simulation.get("violations") or []
    return {
        "optimizer_status": optimization.get("status"),
        "optimizer_feasible": bool(winner) and bool(winner.get("feasible")),
        "evidence_status": evidence_gate.get("status", "blocked"),
        "evidence_score": evidence_gate.get("score", 0),
        "evidence_gaps": evidence_gate.get("gaps", []),
        "rules_pass": bool(validation.get("allowed", not violations)),
        "rule_violations": validation.get("violations", violations),
        "budget_pass": bool(simulation.get("feasible")) and float((simulation.get("budget") or {}).get("remaining_sf") or 0) >= 0,
        "dependencies_pass": not dependencies.get("gaps") and not dependencies.get("conflicts"),
        "dependency_gaps": dependencies.get("gaps", []),
        "dependency_conflicts": dependencies.get("conflicts", []),
        "timing_pass": not any("timing" in str(item).lower() or "מוקדם" in str(item) for item in violations),
        "rulebook_version": simulation.get("rulebook_version"),
    }


def validate_vote(payload: dict[str, Any]) -> dict[str, str]:
    role = str(payload.get("role") or "")
    vote = str(payload.get("vote") or "")
    voter_name = str(payload.get("voter_name") or "").strip()
    if role not in dict(REQUIRED_ROLES):
        raise ValueError("Unknown governance role")
    if vote not in VALID_VOTES:
        raise ValueError("vote must be approve, reject or abstain")
    if not voter_name:
        raise ValueError("voter_name is required")
    if vote in {"reject", "abstain"} and not str(payload.get("rationale") or "").strip():
        raise ValueError("A rationale is required for reject or abstain")
    return {"role": role, "vote": vote, "voter_name": voter_name}

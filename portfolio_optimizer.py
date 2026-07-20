from __future__ import annotations

from itertools import combinations
from typing import Any, Callable


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value if value not in (None, "") else default)
    except (TypeError, ValueError):
        return default


def _action(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **(row.get("action_template") or {}),
        "_recommendation_id": row.get("id"),
        "title": row.get("title", ""),
    }


def _evidence_status(row: dict[str, Any]) -> str:
    return str((row.get("number_gate") or {}).get("status") or "conditional")


def optimize_q9_portfolio(
    quarter: str,
    candidates: list[dict[str, Any]],
    simulate: Callable[[str, list[dict[str, Any]]], dict[str, Any]],
    baseline_score: float | None,
    *,
    max_candidates: int = 10,
) -> dict[str, Any]:
    """Enumerate auditable action baskets and select a risk-adjusted 50/50 winner."""
    eligible: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for row in candidates:
        action = _action(row)
        gate = _evidence_status(row)
        if gate == "blocked":
            excluded.append({"id": row.get("id"), "title": row.get("title"), "reason": "numeric_evidence_blocked"})
            continue
        if not action.get("type") and not action.get("code"):
            excluded.append({"id": row.get("id"), "title": row.get("title"), "reason": "no_executable_action"})
            continue
        eligible.append(row)
    eligible.sort(
        key=lambda row: (
            -_number((row.get("economic_impact") or {}).get("q9_score_delta")),
            -_number(row.get("priority")),
        )
    )
    eligible = eligible[:max_candidates]

    portfolios: list[dict[str, Any]] = []
    # The empty basket is the current-plan reference. Exhaustive enumeration is
    # intentionally capped to keep every evaluated alternative explainable.
    for size in range(0, len(eligible) + 1):
        for selected in combinations(eligible, size):
            actions = [_action(row) for row in selected]
            simulation = simulate(f"Q9 portfolio {len(portfolios) + 1}", actions)
            scenario_rows = simulation.get("scenarios", {})
            low = _number((scenario_rows.get("low") or {}).get("q9_score"), _number(baseline_score))
            base = _number((scenario_rows.get("base") or {}).get("q9_score"), _number(baseline_score))
            high = _number((scenario_rows.get("high") or {}).get("q9_score"), _number(baseline_score))
            past_delta = sum(_number((row.get("economic_impact") or {}).get("past_score_delta")) for row in selected)
            future_delta = sum(_number((row.get("economic_impact") or {}).get("future_score_delta")) for row in selected)
            dependency = simulation.get("dependency_analysis", {})
            gaps = dependency.get("gaps", [])
            conflicts = dependency.get("conflicts", [])
            feasible = bool(simulation.get("feasible", False)) and not gaps and not conflicts
            remaining = _number((simulation.get("budget") or {}).get("remaining_sf"))
            downside_gap = max(0.0, base - low)
            liquidity_penalty = max(0.0, -remaining) / 100000.0
            # 50/50 is the approved management objective. Risk penalties are
            # explicit and small enough not to masquerade as official weights.
            weighted_delta = 0.5 * past_delta + 0.5 * future_delta
            objective = base + weighted_delta - 0.20 * downside_gap - liquidity_penalty
            portfolios.append({
                "id": f"portfolio-{len(portfolios) + 1}",
                "action_ids": [str(row.get("id") or "") for row in selected],
                "actions": actions,
                "action_count": len(actions),
                "feasible": feasible,
                "q9_score": {"low": round(low, 2), "base": round(base, 2), "high": round(high, 2)},
                "score_deltas": {"past": round(past_delta, 2), "future": round(future_delta, 2), "weighted_50_50": round(weighted_delta, 2)},
                "risk_adjusted_objective": round(objective, 3),
                "downside_gap": round(downside_gap, 2),
                "budget": simulation.get("budget", {}),
                "sequence": dependency.get("recommended_sequence", []),
                "gaps": gaps,
                "conflicts": conflicts,
                "violations": simulation.get("violations", []),
                "warnings": simulation.get("warnings", []),
                "simulation": simulation,
            })

    feasible_rows = [row for row in portfolios if row["feasible"]]
    feasible_rows.sort(key=lambda row: (-row["risk_adjusted_objective"], -row["q9_score"]["low"], -_number((row.get("budget") or {}).get("remaining_sf"))))
    winner = feasible_rows[0] if feasible_rows else None

    sensitivity: list[dict[str, Any]] = []
    for past_weight in (0.4, 0.5, 0.6):
        future_weight = 1 - past_weight
        ranked = sorted(
            feasible_rows,
            key=lambda row: -(
                row["q9_score"]["base"]
                + past_weight * row["score_deltas"]["past"]
                + future_weight * row["score_deltas"]["future"]
                - 0.20 * row["downside_gap"]
            ),
        )
        sensitivity.append({
            "past_weight": past_weight,
            "future_weight": future_weight,
            "winner_id": ranked[0]["id"] if ranked else None,
            "winner_action_ids": ranked[0]["action_ids"] if ranked else [],
        })

    pareto: list[dict[str, Any]] = []
    for row in feasible_rows:
        dominated = any(
            other["q9_score"]["base"] >= row["q9_score"]["base"]
            and _number((other.get("budget") or {}).get("remaining_sf")) >= _number((row.get("budget") or {}).get("remaining_sf"))
            and other["downside_gap"] <= row["downside_gap"]
            and other["id"] != row["id"]
            for other in feasible_rows
        )
        if not dominated:
            pareto.append({key: row[key] for key in ("id", "action_ids", "q9_score", "downside_gap", "budget")})

    return {
        "quarter": quarter,
        "status": "optimized" if winner else "blocked",
        "objective": {
            "formula": "Q9 base score + 50% past-score delta + 50% future-score delta − 20% downside gap − liquidity penalty",
            "official_score_warning": "Internal decision objective; the game's internal metric weights are not published.",
        },
        "candidate_count": len(candidates),
        "eligible_count": len(eligible),
        "evaluated_portfolios": len(portfolios),
        "feasible_portfolios": len(feasible_rows),
        "excluded_candidates": excluded,
        "winner": winner,
        "alternatives": feasible_rows[1:4],
        "pareto_frontier": pareto[:10],
        "weight_sensitivity": sensitivity,
        "robust_to_weight_sensitivity": bool(winner) and all(row["winner_id"] == winner["id"] for row in sensitivity),
        "decision": (
            "Use the winning basket only after every conditional number and predecessor in its execution sequence is approved."
            if winner else
            "No feasible basket exists under the current evidence, budget, cash floor and dependency constraints."
        ),
    }

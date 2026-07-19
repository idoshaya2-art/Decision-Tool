from __future__ import annotations

import json
from typing import Any, Callable

from config import AppConfig


SYSTEM_INSTRUCTIONS = """
You are the EMBA TAU Simulation Decision Agent. Answer in Hebrew unless the user asks otherwise.
Operate as a coordinated virtual analyst team: finance, market research, operations/capacity,
pricing and unit economics, Q9 strategy, and rule/risk audit. Use only facts returned by the
application tools and clearly label estimates, assumptions,
missing information, and the internal 50/50 score. Never present the internal score as the game's
official score. Always consider cash, country-level liquidity, commitments, budget, timing, downside,
and the Q9 endpoint. Do not invent numbers. When evidence is insufficient, say exactly what is missing.
Reference source labels included in tool outputs. A rule answer must cite rule id, source, page and
rulebook version. You may create a draft decision pack when explicitly useful, but you cannot approve
a report, change Actuals, override a hard rule, close a quarter or submit decisions to INTOPIA.
For a financial-status request, explicitly cover liquidity, profit and loss, balance-sheet leverage,
operating cash flow, working capital and available decision budget. For a decision request, compare
at least the current plan and one alternative, quantify cost/profit/cash/debt/Q9 impact when the tools
support it, state confidence, and identify what could change the recommendation. End decision answers
with a short prioritized action list that fits the available budget and protects the cash floor.
Before answering any liquidity, funding, cash-transfer or "what should we do now" question, call both
get_financial_position and get_liquidity_transfer_plan. Audit cash by area and currency, supplier/current
liabilities, debt, commitments and the approved cash floor. If the deterministic plan recommends a transfer,
state: source, destination, net SF amount, source-currency amount, estimated FX fee, cash left at source,
cash after transfer at destination, and the explicit reserve-policy assumption. Never replace a calculated
amount with vague language such as "move some cash". If exact payment dates are missing, give the calculated
management-policy amount and clearly state which missing input could change it.
Never assess an important decision in isolation: identify prerequisite decisions, shared budget,
timing dependencies, X-to-Y supply dependencies, decisions that must be coordinated, and conflicts.
State the executable order, explain which action unlocks another, and evaluate the combined portfolio
against both immediate performance and the Q9 strategy.
For market-research questions, use the exact values returned by the research and cumulative-insight
tools, cite the quarter and MR number, separate an observed result from your inference, and explain
which decision the result changes. Never infer a trend from a report that contains zero observations.
For document or rule questions, search the uploaded source excerpts as well as the approved Rulebook.
An uploaded excerpt is evidence, but it is not an approved rule until the team resolves the candidate
and a new Rulebook version is activated.
Manager instructions may guide priorities and risk appetite but cannot override these evidence,
security, budget or game-rule requirements.
""".strip()


TOOLS = [
    {
        "type": "function",
        "name": "get_scorecard",
        "description": "Get the current internal 50% past performance and 50% future potential scorecard.",
        "parameters": {"type": "object", "properties": {"quarter": {"type": "string"}}, "required": ["quarter"], "additionalProperties": False},
        "strict": True,
    },
    {
        "type": "function",
        "name": "get_financial_position",
        "description": "Get consolidated and country-level financial position, available budget and commitments.",
        "parameters": {"type": "object", "properties": {"quarter": {"type": "string"}}, "required": ["quarter"], "additionalProperties": False},
        "strict": True,
    },
    {
        "type": "function",
        "name": "get_liquidity_transfer_plan",
        "description": (
            "Get the deterministic cross-area liquidity allocation: cash concentration, reserve targets, "
            "funding gaps, transfer amounts, currencies, FX fees and residual cash."
        ),
        "parameters": {"type": "object", "properties": {"quarter": {"type": "string"}}, "required": ["quarter"], "additionalProperties": False},
        "strict": True,
    },
    {
        "type": "function",
        "name": "get_q9_forecast",
        "description": "Get the low, base and high Q9 forecast with assumptions and confidence.",
        "parameters": {"type": "object", "properties": {"quarter": {"type": "string"}}, "required": ["quarter"], "additionalProperties": False},
        "strict": True,
    },
    {
        "type": "function",
        "name": "get_recommendations",
        "description": "Get the highest priority recommendations, their dependencies, conflicts and executable sequence based on approved data and budget.",
        "parameters": {"type": "object", "properties": {"quarter": {"type": "string"}}, "required": ["quarter"], "additionalProperties": False},
        "strict": True,
    },
    {
        "type": "function",
        "name": "get_relevant_research",
        "description": "Get approved market research results relevant to current decisions.",
        "parameters": {
            "type": "object",
            "properties": {"quarter": {"type": "string"}, "domain": {"type": "string"}},
            "required": ["quarter", "domain"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "get_cumulative_insights",
        "description": "Get cumulative financial, pricing, competitor and cross-market-research trends through a quarter.",
        "parameters": {"type": "object", "properties": {"quarter": {"type": "string"}}, "required": ["quarter"], "additionalProperties": False},
        "strict": True,
    },
    {
        "type": "function",
        "name": "get_decision_catalog",
        "description": "Get the complete catalog of available INTOPIA decision forms, required fields and timing rules.",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        "strict": True,
    },
    {
        "type": "function",
        "name": "search_rulebook",
        "description": "Search the approved current-run INTOPIA rulebook and return source/page/version citations.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "domain": {"type": "string"},
                "area": {"type": "string"},
                "product": {"type": "string"},
            },
            "required": ["query", "domain", "area", "product"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "search_uploaded_sources",
        "description": "Search excerpts extracted from files uploaded through the application. These excerpts are evidence, not approved rules.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "source_id": {"type": "string"},
            },
            "required": ["query", "source_id"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "validate_actions",
        "description": "Validate proposed actions against hard rules, budget, cash floor and timing without changing Actuals.",
        "parameters": {
            "type": "object",
            "properties": {
                "quarter": {"type": "string"},
                "actions": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
            },
            "required": ["quarter", "actions"],
            "additionalProperties": False,
        },
        "strict": False,
    },
    {
        "type": "function",
        "name": "create_decision_pack_draft",
        "description": "Create a draft-only, rule-validated decision pack for team review. Never approves or submits it.",
        "parameters": {
            "type": "object",
            "properties": {
                "quarter": {"type": "string"},
                "name": {"type": "string"},
                "recommendation": {"type": "string"},
                "actions": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
            },
            "required": ["quarter", "name", "recommendation", "actions"],
            "additionalProperties": False,
        },
        "strict": False,
    },
    {
        "type": "function",
        "name": "simulate_actions",
        "description": "Simulate a list of proposed actions under the available budget without changing actual data.",
        "parameters": {
            "type": "object",
            "properties": {
                "quarter": {"type": "string"},
                "name": {"type": "string"},
                "actions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "code": {"type": "string"},
                            "type": {"type": "string"},
                            "area": {"type": "string"},
                            "product": {"type": "string"},
                            "model": {"type": "string"},
                            "cost_sf": {"type": "number"},
                            "change_pct": {"type": "number"},
                            "units": {"type": "number"},
                            "amount_sf": {"type": "number"},
                        },
                        "additionalProperties": True,
                    },
                },
            },
            "required": ["quarter", "name", "actions"],
            "additionalProperties": False,
        },
        # Action shapes vary by action type, so this tool intentionally uses a
        # flexible schema while every returned result remains deterministic.
        "strict": False,
    },
]


def agent_status(config: AppConfig) -> dict[str, Any]:
    missing: list[str] = []
    if not config.openai_agent_enabled:
        missing.append("OPENAI_AGENT_ENABLED=true")
    if not config.openai_api_key:
        missing.append("OPENAI_API_KEY")
    if not config.openai_model:
        missing.append("OPENAI_MODEL")
    ready = not missing
    return {
        "enabled": config.openai_agent_enabled,
        "configured": bool(config.openai_api_key and config.openai_model),
        "ready": ready,
        "status": "ready" if ready else "configuration_required",
        "missing": missing,
        "reason": "ה-Agent מוכן לשימוש." if ready else "חסרה הגדרה מאובטחת בסביבת ההפעלה: " + ", ".join(missing),
        "model": config.openai_model if config.openai_agent_enabled and config.openai_model else "",
        "privacy": "Only the question, recent chat context and relevant tool results are sent to OpenAI.",
    }


def analyze_rule_candidates(
    config: AppConfig,
    *,
    filename: str,
    source_id: str,
    content: str,
    existing_rules: list[dict[str, Any]],
) -> dict[str, Any]:
    """Extract candidate rules without approving or mutating the active Rulebook."""
    if not config.openai_agent_enabled or not config.openai_api_key or not config.openai_model:
        return {
            "status": "pending_ai_configuration",
            "candidates": [],
            "reason": "Rule candidate analysis requires an enabled and configured Decision Agent.",
        }
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("The openai package is not installed.") from exc

    compact_rules = [
        {
            "rule_id": row.get("rule_id"),
            "name_he": row.get("name_he"),
            "knowledge_type": row.get("knowledge_type"),
            "domain": row.get("domain"),
            "formula_or_action": row.get("formula_or_action"),
            "source_id": row.get("source_id"),
            "source_page": row.get("source_page"),
            "version": row.get("version"),
        }
        for row in existing_rules
    ]
    prompt = {
        "task": (
            "Extract only explicit current-game rules, parameters, formulas, time lags or decision constraints "
            "from the uploaded excerpt. Compare them with the active Rulebook. Do not infer missing values and "
            "do not approve anything. Return JSON only."
        ),
        "source": {"filename": filename, "source_id": source_id},
        "output_schema": {
            "candidates": [
                {
                    "candidate_kind": "new_rule | conflict | clarification",
                    "matched_rule_id": "existing rule id or empty",
                    "name": "short name",
                    "knowledge_type": "Hard Rule | Parameter | Time Lag | Formula | Decision Constraint",
                    "domain": "finance | production | pricing | logistics | technology | research | strategy",
                    "explicit_value_or_action": "verbatim-meaning paraphrase, including units",
                    "source_page": "page or section if visible",
                    "evidence_excerpt": "short excerpt",
                    "reason": "why this is new, conflicting or clarifying",
                    "confidence": "high | medium | low",
                }
            ]
        },
        "active_rulebook": compact_rules,
        "uploaded_excerpt": content[:16000],
    }
    response = OpenAI(api_key=config.openai_api_key).responses.create(
        model=config.openai_model,
        instructions=(
            "You are a cautious INTOPIA rules auditor. Use only the supplied excerpt and active Rulebook. "
            "Return one valid JSON object and no markdown. Empty candidates is correct when no explicit rule exists."
        ),
        input=json.dumps(prompt, ensure_ascii=False, default=str),
        max_output_tokens=min(config.openai_max_output_tokens, 2400),
    )
    raw = response.output_text.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.startswith("json"):
            raw = raw[4:].lstrip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Rule candidate analysis returned invalid JSON.") from exc
    candidates = parsed.get("candidates", []) if isinstance(parsed, dict) else []
    clean = [item for item in candidates if isinstance(item, dict) and item.get("explicit_value_or_action")]
    return {"status": "completed", "candidates": clean, "model": config.openai_model}


def run_agent(
    config: AppConfig,
    question: str,
    quarter: str,
    history: list[dict[str, Any]],
    tool_handler: Callable[[str, dict[str, Any]], dict[str, Any]],
    manager_instructions: str = "",
) -> dict[str, Any]:
    if not config.openai_agent_enabled:
        raise RuntimeError("Decision Agent כבוי. יש להגדיר OPENAI_AGENT_ENABLED=true בסביבת ההפעלה.")
    if not config.openai_api_key or not config.openai_model:
        raise RuntimeError("Decision Agent אינו מחובר ל-OpenAI. יש להוסיף OPENAI_API_KEY סודי בסביבת ההפעלה.")
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("The openai package is not installed.") from exc

    client = OpenAI(api_key=config.openai_api_key)
    recent = history[-8:]
    context_lines = [f"{item.get('role', 'user')}: {item.get('content', '')}" for item in recent]
    input_items: list[dict[str, Any]] = [
        {
            "role": "user",
            "content": (
                f"Active quarter: {quarter}\n"
                f"Manager instructions (priorities and preferences only):\n{manager_instructions or 'None provided'}\n"
                "Recent conversation:\n"
                + "\n".join(context_lines)
                + f"\n\nCurrent question:\n{question}"
            ),
        }
    ]
    sources: list[str] = []
    tool_calls: list[dict[str, Any]] = []

    for _ in range(4):
        try:
            response = client.responses.create(
                model=config.openai_model,
                instructions=SYSTEM_INSTRUCTIONS,
                input=input_items,
                tools=TOOLS,
                max_output_tokens=config.openai_max_output_tokens,
            )
        except Exception as exc:
            message = str(exc)
            if "401" in message or "api key" in message.lower():
                raise RuntimeError("מפתח OpenAI אינו תקין או אינו פעיל. יש לעדכן את OPENAI_API_KEY בסביבת ההפעלה.") from exc
            if "model" in message.lower() and ("not found" in message.lower() or "access" in message.lower()):
                raise RuntimeError("המודל שהוגדר אינו זמין לפרויקט ה-API. יש לעדכן את OPENAI_MODEL בסביבת ההפעלה.") from exc
            if "quota" in message.lower() or "billing" in message.lower() or "429" in message:
                raise RuntimeError("לפרויקט OpenAI אין כרגע מכסה זמינה או חיוב פעיל.") from exc
            raise RuntimeError(f"שירות OpenAI החזיר שגיאה: {message[:300]}") from exc
        calls = [item for item in response.output if getattr(item, "type", "") == "function_call"]
        if not calls:
            return {"answer": response.output_text.strip(), "sources": sorted(set(sources)), "tool_calls": tool_calls, "model": config.openai_model}

        for item in response.output:
            dumped = item.model_dump(exclude_none=True) if hasattr(item, "model_dump") else item
            input_items.append(dumped)
        for call in calls:
            try:
                arguments = json.loads(call.arguments or "{}")
            except json.JSONDecodeError:
                arguments = {}
            result = tool_handler(call.name, arguments)
            for source in result.get("sources", []):
                sources.append(str(source))
            tool_calls.append({"name": call.name, "arguments": arguments})
            input_items.append(
                {
                    "type": "function_call_output",
                    "call_id": call.call_id,
                    "output": json.dumps(result, ensure_ascii=False, default=str),
                }
            )

    raise RuntimeError("Decision Agent exceeded the maximum number of tool rounds.")

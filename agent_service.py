from __future__ import annotations

import json
from typing import Any, Callable

from config import AppConfig


SYSTEM_INSTRUCTIONS = """
You are the EMBA TAU Simulation Decision Agent. Answer in Hebrew unless the user asks otherwise.
Use only facts returned by the application's read-only tools and clearly label estimates, assumptions,
missing information, and the internal 50/50 score. Never present the internal score as the game's
official score. Always consider cash, country-level liquidity, commitments, budget, timing, downside,
and the Q9 endpoint. Do not invent numbers. When evidence is insufficient, say exactly what is missing.
Reference source labels included in tool outputs. You cannot approve or write official decisions.
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
        "name": "get_q9_forecast",
        "description": "Get the low, base and high Q9 forecast with assumptions and confidence.",
        "parameters": {"type": "object", "properties": {"quarter": {"type": "string"}}, "required": ["quarter"], "additionalProperties": False},
        "strict": True,
    },
    {
        "type": "function",
        "name": "get_recommendations",
        "description": "Get the highest priority decision recommendations based on approved data and budget.",
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
                            "type": {"type": "string"},
                            "area": {"type": "string"},
                            "product": {"type": "string"},
                            "model": {"type": "string"},
                            "cost_sf": {"type": "number"},
                            "change_pct": {"type": "number"},
                            "units": {"type": "number"},
                            "amount_sf": {"type": "number"},
                        },
                        "required": ["type"],
                        "additionalProperties": False,
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
    return {
        "enabled": config.openai_agent_enabled,
        "configured": bool(config.openai_api_key and config.openai_model),
        "model": config.openai_model if config.openai_agent_enabled and config.openai_model else "",
        "privacy": "Only the question, recent chat context and relevant tool results are sent to OpenAI.",
    }


def run_agent(
    config: AppConfig,
    question: str,
    quarter: str,
    history: list[dict[str, Any]],
    tool_handler: Callable[[str, dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    if not config.openai_agent_enabled:
        raise RuntimeError("Decision Agent is disabled. Set OPENAI_AGENT_ENABLED=true in Render.")
    if not config.openai_api_key or not config.openai_model:
        raise RuntimeError("Decision Agent is not configured. Add OPENAI_API_KEY and OPENAI_MODEL in Render.")
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
            "content": f"Active quarter: {quarter}\nRecent conversation:\n" + "\n".join(context_lines) + f"\n\nCurrent question:\n{question}",
        }
    ]
    sources: list[str] = []
    tool_calls: list[dict[str, Any]] = []

    for _ in range(4):
        response = client.responses.create(
            model=config.openai_model,
            instructions=SYSTEM_INSTRUCTIONS,
            input=input_items,
            tools=TOOLS,
            max_output_tokens=config.openai_max_output_tokens,
        )
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

"""
AI provider adapter with model routing and cost tracking (spec sections 3, 26, 34).

If ANTHROPIC_API_KEY / OPENAI_API_KEY are configured, real calls are made and
real cost is computed from the provider's token usage and recorded as an
ACTUAL expense. If no key is configured, every call falls back to a
deterministic, clearly-labeled MOCK_LLM generator -- it produces structurally
valid output so the rest of the pipeline is exercisable end-to-end, but it is
never represented as a real model's output or as verified market research.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.budget.ledger import record_expense
from app.config import settings
from app.models.models import AIUsageRecord

# Approximate public per-token pricing used only to ESTIMATE cost of real calls.
# These are illustrative defaults -- verify against the provider's current
# pricing page before relying on them for real financial reporting.
PRICE_PER_1K_TOKENS = {
    "claude-haiku-4-5-20251001": {"input": 0.001, "output": 0.005},
    "claude-opus-5": {"input": 0.015, "output": 0.075},
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
}


@dataclass
class AIResponse:
    text: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    is_mock: bool
    raw: dict = field(default_factory=dict)


def _mock_complete(system_prompt: str, user_prompt: str, task_hint: str) -> str:
    """
    Deterministic, template-based stand-in for an LLM call. Used only when no
    real API key is configured. Output is clearly structural, not claimed to
    be real research or a real creative judgment.
    """
    return json.dumps(
        {
            "mock": True,
            "note": (
                "MOCK_LLM fallback -- no ANTHROPIC_API_KEY/OPENAI_API_KEY configured. "
                "This output is a structural placeholder for pipeline testing, not a "
                "real model inference or verified research finding."
            ),
            "task_hint": task_hint,
            "prompt_excerpt": user_prompt[:300],
        }
    )


def complete(
    db: Session,
    *,
    agent_key: str,
    system_prompt: str,
    user_prompt: str,
    task_hint: str = "",
    complexity: str = "routine",  # "routine" -> cheap model, "complex" -> capable model
    workflow_run_id: int | None = None,
) -> AIResponse:
    model = settings.default_model_routine if complexity == "routine" else settings.default_model_complex

    if settings.anthropic_configured:
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        msg = client.messages.create(
            model=model,
            max_tokens=1024,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        text = "".join(block.text for block in msg.content if hasattr(block, "text"))
        input_tokens = msg.usage.input_tokens
        output_tokens = msg.usage.output_tokens
        pricing = PRICE_PER_1K_TOKENS.get(model, {"input": 0.01, "output": 0.03})
        cost = (input_tokens / 1000) * pricing["input"] + (output_tokens / 1000) * pricing["output"]
        response = AIResponse(text, "anthropic", model, input_tokens, output_tokens, cost, False, {"id": msg.id})
    elif settings.openai_configured:
        from openai import OpenAI

        client = OpenAI(api_key=settings.openai_api_key)
        oa_model = "gpt-4o-mini"
        resp = client.chat.completions.create(
            model=oa_model,
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
        )
        text = resp.choices[0].message.content or ""
        input_tokens = resp.usage.prompt_tokens if resp.usage else 0
        output_tokens = resp.usage.completion_tokens if resp.usage else 0
        pricing = PRICE_PER_1K_TOKENS.get(oa_model, {"input": 0.01, "output": 0.03})
        cost = (input_tokens / 1000) * pricing["input"] + (output_tokens / 1000) * pricing["output"]
        response = AIResponse(text, "openai", oa_model, input_tokens, output_tokens, cost, False, {})
    else:
        text = _mock_complete(system_prompt, user_prompt, task_hint)
        response = AIResponse(text, "mock", "mock-llm-v1", 0, 0, 0.0, True, {})

    db.add(
        AIUsageRecord(
            agent_key=agent_key,
            provider=response.provider,
            model=response.model,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            cost_usd=response.cost_usd,
            is_mock=response.is_mock,
        )
    )
    db.commit()

    if response.cost_usd > 0:
        record_expense(
            db,
            category="ai_api",
            amount_usd=response.cost_usd,
            basis="ACTUAL",
            description=f"{agent_key} call to {response.provider}:{response.model}",
            workflow_run_id=workflow_run_id,
            agent_key=agent_key,
        )

    return response

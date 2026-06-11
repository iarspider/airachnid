from typing import Annotated

from loguru import logger
from pydantic import BaseModel, Field
from pydantic_ai import Agent, UnexpectedModelBehavior
from pydantic_ai.output import NativeOutput

from config import agent_settings
from control_plane.validator import (
    validate_request_with_llm,
    normalize_text,
    validate_request,
)
from graph.state import AgentState
from llm import get_pydantic_ai_model
from prompts import VALIDATE_OUTPUT_PROMPT, VALIDATE_OUTPUT_TEMPLATE


async def node_validate_request(state: AgentState) -> AgentState:
    raw = state.get("raw_message", "")

    normalized = normalize_text(raw)

    res, reason = validate_request(normalized)

    if not res:
        return {
            **state,
            "normalized_message": normalized,
            "validation_passed": res,
            "error": f"Плохой запрос: {reason}",
        }

    logger.info(f"1st validation passed.")

    if not agent_settings.llm_prompt_validation:
        logger.warning("LLM prompt validation skipped - disabled in config")
    else:
        safe, reason = await validate_request_with_llm(normalized)

        if not safe:
            logger.warning(f"Validation failed: {reason}")
            return {
                **state,
                "normalized_message": normalized,
                "validation_passed": False,
                "error": reason,
            }

        logger.info(f"2nd validation passed.")

    return {
        **state,
        "normalized_message": normalized,
        "validation_passed": True,
    }


class OutputValidationResult(BaseModel):
    score: Annotated[float, Field(ge=0.0, le=1.0)]
    relevance: Annotated[float, Field(ge=0.0, le=1.0)]
    completeness: Annotated[float, Field(ge=0.0, le=1.0)]
    reason: str


async def node_validate_output(state: AgentState) -> AgentState:
    """Validate the generated reply for safety and correctness."""
    post = state.get("final_answer", "")

    if not post or len(post.strip()) < 30:
        return {
            **state,
            "success": False,
            "error": "Ответ слишком короткий или пустой.",
        }

    # Basic safety checks on output
    danger_phrases = [
        "ignore previous",
        "system prompt",
        "jailbreak",
        "as an AI, I cannot",
    ]
    post_lower = post.lower()
    for phrase in danger_phrases:
        if phrase in post_lower:
            logger.warning(f"Unsafe phrase in output: {phrase}")
            return {
                **state,
                "success": False,
                "error": "Сгенерированный контент небезопасен.",
            }

    # Additional LLM-as-a-judge validation, with autoretry via pydantic-ai
    model = get_pydantic_ai_model(
        agent_settings.ollama.model,
    )

    agent = Agent(model, output_type=NativeOutput(OutputValidationResult))
    try:
        res = await agent.run(
            VALIDATE_OUTPUT_TEMPLATE.format(
                user_request=state.get("normalized_message", ""),
                assistant_response=state.get("final_answer", ""),
            ),
            instructions=VALIDATE_OUTPUT_PROMPT,
            retries=5,
        )
    except UnexpectedModelBehavior:
        return {
            **state,
            "success": False,
            "error": "LLM-as-a-judge не вернул корректный json",
            "retry": False,
        }

    res = res.output

    if res.score < agent_settings.final_validation_threshold:
        return {
            **state,
            "success": False,
            "validation_score": res.score,
            "validation_relevance": res.relevance,
            "validation_completeness": res.completeness,
            "retry": True,
            "error": "LLM-as-a-judge забраковал ответ: " + str(res.reason),
        }

    return {
        **state,
        "success": True,
        "validation_score": res.score,
        "validation_relevance": res.relevance,
        "validation_completeness": res.completeness,
        "error": "",
    }

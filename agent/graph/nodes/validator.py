import re
import unicodedata
from typing import Annotated

from loguru import logger
from pydantic import BaseModel, Field
from pydantic_ai import Agent, UnexpectedModelBehavior
from pydantic_ai.capabilities import Instrumentation
from pydantic_ai.models.ollama import OllamaModel
from pydantic_ai.output import NativeOutput
from pydantic_ai.providers.ollama import OllamaProvider

from config import agent_settings
from graph.state import AgentState
from prompts import VALIDATE_OUTPUT_PROMPT, VALIDATE_OUTPUT_TEMPLATE, ANTI_PI_PROMPT

# Prompt injection patterns
_INJECTION_PATTERNS = [
    # English patterns
    r"ignore\s+(previous|prior|above|all)\s+(instructions?|prompts?|rules?|constraints?)",
    r"forget\s+(everything|all|previous|prior)",
    r"you\s+are\s+now\s+(a|an)\s+\w+",
    r"act\s+as\s+(if\s+you\s+are|a|an)\s+",
    r"new\s+(instructions?|system\s+prompt|role|persona)",
    r"disregard\s+(your|the|all)\s+",
    r"override\s+(your|the|all)\s+",
    r"do\s+not\s+follow\s+(your|the)\s+",
    r"jailbreak",
    r"prompt\s+injection",
    r"</?(system|instruction|prompt)>",
    r"\[INST\]",
    r"<\|im_start\|>",
    r"dan\s*mode",
    r"mode\s*dan",
    # Russian — ignore/forget instructions
    r"игнорир\w+\s+(все|предыдущие|прежние|прошлые)?\s*(инструкции|правила|ограничения|указания)",
    r"забудь\s+(все|всё|предыдущее|прошлое|инструкции|правила)",
    r"не\s+следуй\s+(своим|этим|прежним)?\s*(инструкциям|правилам|указаниям)",
    r"отмени\s+(все|свои|предыдущие)\s*(инструкции|правила|ограничения)",
    r"сбрось\s+(настройки|инструкции|ограничения|правила)",
    # Russian — persona/role switch
    r"ты\s+теперь\s+(являешься|есть|стал)?\s*\w+",
    r"притворись\s+(что\s+ты)?\s*(являешься)?\s*\w+",
    r"представь\s+(что\s+ты|себя)\s*(являешься)?\s*\w+",
    r"веди\s+себя\s+как\s+",
    r"действуй\s+как\s+(будто\s+ты)?\s*",
    r"сыграй\s+роль\s+",
    r"войди\s+в\s+роль\s+",
    r"новая\s+(роль|личность|персона|инструкция)",
    # Russian — override/bypass
    r"обойди\s+(защиту|ограничения|фильтры|правила)",
    r"отключи\s+(фильтры|ограничения|защиту|цензуру)",
    r"без\s+(ограничений|цензуры|фильтров|правил)",
    r"в\s+режиме\s+(разработчика|developer|без\s+ограничений|бога)",
    r"разблокируй\s+(себя|свои\s+возможности|режим)",
    # Russian — system prompt manipulation
    r"системный\s+промпт",
    r"системная\s+инструкция",
    r"начало\s+диалога",
    r"твои\s+(настоящие|скрытые|реальные)\s+(инструкции|правила|цели)",
    # Russian — jailbreak terminology (often used as-is)
    r"джейлбрейк",
    r"дан\s*мод",  # DAN mode
    r"режим\s+дан\b",
]

_COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE) for p in _INJECTION_PATTERNS]


class ValidationResult(BaseModel):
    safe: bool
    reason: str | None = Field(None)


class OutputValidationResult(BaseModel):
    score: Annotated[float, Field(ge=0.0, le=1.0)]
    relevance: Annotated[float, Field(ge=0.0, le=1.0)]
    completeness: Annotated[float, Field(ge=0.0, le=1.0)]
    reason: str


def check_injection(text: str) -> tuple[bool, str]:
    """Returns (is_safe, reason). is_safe=True means no injection detected."""
    for pattern in _COMPILED_PATTERNS:
        if pattern.search(text):
            logger.warning(
                "injection_detected", pattern=pattern.pattern, text_snippet=text[:100]
            )
            return (
                False,
                f"Запрос содержит потенциально опасный паттерн: '{pattern.pattern}'",
            )
    return True, ""


def validate_request(text: str, max_length: int = 1000) -> tuple[bool, str]:
    """Быстрая, но грубая, проверка на явные попытки PI"""
    if not text or not text.strip():
        logger.error("Пустой запрос")
        return False, "Запрос не может быть пустым."

    if len(text) > max_length:
        logger.error("Слишком длинный запрос")
        return False, f"Запрос слишком длинный. Максимум {max_length} символов."

    safe, reason = check_injection(text)
    if not safe:
        return False, reason

    return True, ""


def normalize_text(text: str) -> str:
    """Normalize user input: unicode, whitespace, strip control chars."""
    if not text:
        return ""
    # Normalize unicode
    text = unicodedata.normalize("NFKC", text)
    # Remove control characters (except newline/tab)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    # Collapse multiple whitespace into single space
    text = re.sub(r"[ \t]+", " ", text)
    # Collapse multiple newlines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


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
        model = OllamaModel(
            agent_settings.ollama.classifier_model,
            provider=OllamaProvider(
                base_url=agent_settings.ollama.pydantic_ai_base_url
            ),
        )

        agent = Agent(
            model=model,
            system_prompt=ANTI_PI_PROMPT,
            retries=3,
            output_type=NativeOutput(ValidationResult),
            capabilities=[Instrumentation()],
        )

        async with agent:
            try:
                result = await agent.run(normalized, retries=5)
            except UnexpectedModelBehavior as e:
                logger.error(f"Anti-PI failure: {e}")
                return {
                    **state,
                    "error": "Ошибка Anti-PI",
                    "success": False,
                    "retry": False,
                }

        jres = result.output

        reason = jres.reason or "Unknown"

        if not jres.safe:
            logger.warning(f"Validation failed: {reason}")
            return {
                **state,
                "normalized_message": normalized,
                "validation_passed": False,
                "error": jres.reason,
            }

        logger.info(f"2nd validation passed.")

    return {
        **state,
        "normalized_message": normalized,
        "validation_passed": True,
    }


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
    model = OllamaModel(
        agent_settings.ollama.model,
        provider=OllamaProvider(base_url=agent_settings.ollama.pydantic_ai_base_url),
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

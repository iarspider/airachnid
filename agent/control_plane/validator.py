import re
import unicodedata
from typing import Annotated

from loguru import logger
from pydantic import BaseModel, Field
from pydantic_ai import Agent, NativeOutput, UnexpectedModelBehavior
from pydantic_ai.capabilities import Instrumentation
from pydantic_ai.models.ollama import OllamaModel
from pydantic_ai.providers.ollama import OllamaProvider

from config import agent_settings
from prompts import ANTI_PI_PROMPT

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


async def validate_request_with_llm(text: str) -> tuple[bool, str]:
    model = OllamaModel(
        agent_settings.ollama.classifier_model,
        provider=OllamaProvider(
            base_url=agent_settings.ollama.pydantic_ai_ollama_base_url
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
            result = await agent.run(text, retries=5)
        except UnexpectedModelBehavior as e:
            logger.error(f"Anti-PI failure: {e}")
            return False, "Сбой LLM-based Anti-PI"

    jres = result.output

    safe = jres.safe
    reason = jres.reason or "Unknown"

    return safe, reason

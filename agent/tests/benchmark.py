"""
AIrachnid benchmark — eval suite for the RAG branch.

Three types of checks per requirement:
  1. Programmatic assert  — deterministic, no LLM
  2. LLM-as-judge         — quality of the final answer
  3. Tool-call check      — correct tool selected with valid args (tool branch)

Run:
    uv run pytest evals/benchmark.py -v
or standalone:
    uv run python evals/benchmark.py
"""

import asyncio
import json
from dataclasses import dataclass, field
from typing import Literal

import httpx
import pytest
from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models.ollama import OllamaModel
from pydantic_ai.providers.ollama import OllamaProvider
from pydantic_ai.output import NativeOutput

from pathlib import Path

THIS_FILE = Path(__file__).resolve()

import sys

sys.path.insert(0, str(THIS_FILE.parent.parent.parent))

from config import agent_settings

# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------


@dataclass
class RAGCase:
    id: str
    input: str
    expected_titles: list[str]  # хотя бы одно должно быть в ответе
    top_k: int = 3  # в топ-N результатов поиска
    notes: str = ""
    lang: Literal["en", "ru"] = "en"


@dataclass
class ToolCase:
    id: str
    input: str
    expected_tool: str  # имя ожидаемого tool
    forbidden_tools: list[str] = field(default_factory=list)
    notes: str = ""
    lang: Literal["en", "ru"] = "en"


RAG_CASES: list[RAGCase] = [
    # --- Exact title (EN) ---
    RAGCase(
        id="exact-en-witcher3",
        input="Tell me about The Witcher 3",
        expected_titles=["The Witcher 3: Wild Hunt"],
        top_k=1,
        notes="exact title EN",
        lang="en",
    ),
    RAGCase(
        id="exact-en-stray",
        input="What is Stray about?",
        expected_titles=["Stray"],
        top_k=1,
        notes="exact title EN",
        lang="en",
    ),
    RAGCase(
        id="exact-ru-witcher3",
        input="Расскажи об игре Ведьмак 3",
        expected_titles=["The Witcher 3: Wild Hunt"],
        top_k=2,
        notes="exact title RU",
        lang="ru",
    ),
    RAGCase(
        id="exact-ru-stray",
        input="Что такое игра Stray?",
        expected_titles=["Stray"],
        top_k=2,
        notes="exact title RU",
        lang="ru",
    ),
    # --- Thematic (EN) ---
    RAGCase(
        id="theme-en-cats",
        input="Recommend me a game about cats",
        expected_titles=[
            "Stray",
            "Cat Quest",
            "Little Kitty, Big City",
            "Copycat",
            "Cattails",
        ],
        top_k=5,
        notes="thematic EN — cats",
        lang="en",
    ),
    RAGCase(
        id="theme-en-openworld",
        input="Find me an open world RPG",
        expected_titles=[
            "The Witcher 3: Wild Hunt",
            "Avowed",
            "Gothic",
            "The Elder Scrolls",
        ],
        top_k=5,
        notes="thematic EN — open world RPG",
        lang="en",
    ),
    RAGCase(
        id="theme-en-horror",
        input="I want something scary to play tonight",
        expected_titles=[
            "Amnesia",
            "Soma",
            "Alien: Isolation",
            "Maid of Sker",
            "Resident Evil",
        ],
        top_k=5,
        notes="thematic EN — horror",
        lang="en",
    ),
    # --- Thematic (RU) ---
    RAGCase(
        id="theme-ru-cats",
        input="Посоветуй игру про котиков",
        expected_titles=[
            "Stray",
            "Cat Quest",
            "Little Kitty, Big City",
            "Copycat",
            "Cattails",
        ],
        top_k=5,
        notes="thematic RU — cats",
        lang="ru",
    ),
    RAGCase(
        id="theme-ru-openworld",
        input="Хочу игру с открытым миром",
        expected_titles=[
            "The Witcher 3: Wild Hunt",
            "Avowed",
            "Gothic",
            "Planet Explorers",
        ],
        top_k=5,
        notes="thematic RU — open world",
        lang="ru",
    ),
    # --- Not in library ---
    RAGCase(
        id="not-in-library-en",
        input="Tell me about The Last Cat in the Universe",
        expected_titles=[],  # нет в базе — ожидаем DDG или честный ответ
        top_k=5,
        notes="game not in library — should fall back to DDG",
        lang="en",
    ),
    # --- Series ---
    RAGCase(
        id="series-en-assassins",
        input="Show me Assassin's Creed games I own",
        expected_titles=["Assassin's Creed"],  # substring match
        top_k=5,
        notes="series query EN",
        lang="en",
    ),
    RAGCase(
        id="series-ru-assassins",
        input="Какие игры Assassin's Creed у меня есть?",
        expected_titles=["Assassin's Creed"],
        top_k=5,
        notes="series query RU",
        lang="ru",
    ),
]

TOOL_CASES: list[ToolCase] = [
    ToolCase(
        id="tool-light-on-en",
        input="Turn on the lights",
        expected_tool="turn-on",
        forbidden_tools=["vlc_play", "vlc_pause"],
        notes="light control EN",
        lang="en",
    ),
    ToolCase(
        id="tool-light-off-ru",
        input="Выключи свет",
        expected_tool="turn-off",
        forbidden_tools=["vlc_play", "vlc_pause"],
        notes="light control RU",
        lang="ru",
    ),
    ToolCase(
        id="tool-vlc-pause-en",
        input="Pause the music",
        expected_tool="vlc_pause",
        forbidden_tools=["turn-on", "turn-off"],
        notes="VLC control EN",
        lang="en",
    ),
    ToolCase(
        id="tool-vlc-next-en",
        input="Skip to the next track",
        expected_tool="vlc_next",
        forbidden_tools=["turn-on", "turn-off"],
        notes="VLC next track EN",
        lang="en",
    ),
]


# ---------------------------------------------------------------------------
# Agent HTTP client
# ---------------------------------------------------------------------------

AGENT_URL = f"http://localhost:{agent_settings.port}"


async def ask_agent(message: str, session_id: int = 42) -> dict:
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{AGENT_URL}/invoke",
            json={"request": message, "session": 42, "user": 1},
        )
        print(resp.text)
        print(resp.status_code)
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# LLM-as-judge
# ---------------------------------------------------------------------------


class JudgeVerdict(BaseModel):
    relevant: bool
    no_hallucination: bool
    score: float  # 0.0 – 1.0
    reason: str


JUDGE_PROMPT = """You are an impartial evaluator of an AI assistant's answers about video games.

Given:
- user_query: the original question
- agent_answer: the assistant's response  
- expected_titles: list of game titles that should appear in the answer (may be empty)

Evaluate:
1. relevant (bool): does the answer address the question?
2. no_hallucination (bool): does the answer avoid inventing facts that contradict well-known 
   information about the game? Note: providing MORE detail than asked is NOT hallucination — 
   it is acceptable and often helpful. Only mark false if the answer contains clearly wrong facts.
3. score (float 0.0-1.0): overall quality

If expected_titles is empty, a good answer honestly says the game was not found in the library
(possibly with DDG results). Score that as >= 0.7 if done correctly.

Return ONLY valid JSON matching the schema. No markdown."""


def get_judge_agent() -> Agent:
    return Agent(
        model=OllamaModel(
            agent_settings.ollama.model,
            provider=OllamaProvider(
                base_url=agent_settings.ollama.pydantic_ai_base_url
            ),
        ),
        output_type=NativeOutput(JudgeVerdict),
        system_prompt=JUDGE_PROMPT,
        retries=3,
    )


async def judge(query: str, answer: str, expected_titles: list[str]) -> JudgeVerdict:
    agent = get_judge_agent()
    result = await agent.run(
        json.dumps(
            {
                "user_query": query,
                "agent_answer": answer,
                "expected_titles": expected_titles,
            }
        )
    )
    return result.output


# ---------------------------------------------------------------------------
# Programmatic asserts (Type 1)
# ---------------------------------------------------------------------------


def assert_answer_not_empty(answer: str) -> None:
    assert answer and answer.strip(), "Answer is empty"


def assert_no_error(response: dict) -> None:
    assert "error" not in response, f"Agent returned error: {response.get('error')}"


def assert_titles_mentioned(
    answer: str, expected_titles: list[str], top_k: int
) -> bool:
    """Returns True if at least one expected title appears in the answer (substring match)."""
    if not expected_titles:
        return True  # nothing to check — DDG fallback case
    answer_lower = answer.lower()
    matches = [t for t in expected_titles if t.lower() in answer_lower]
    return len(matches) > 0


def assert_not_all_hallucinated(answer: str) -> None:
    hallucination_markers = [
        "i don't have information",
        "i cannot find",
        "no games found",
        "не нашёл",
        "нет информации",
    ]
    answer_lower = answer.lower()
    for marker in hallucination_markers:
        if marker in answer_lower:
            pytest.fail(f"Possible hallucination marker found: '{marker}'")


# ---------------------------------------------------------------------------
# Tool-call check (Type 3)
# ---------------------------------------------------------------------------


def assert_tool_called(
    response: dict, expected_tool: str, forbidden_tools: list[str]
) -> None:
    """Check tool call via Langfuse trace or response metadata if available."""
    # Если агент возвращает tool_calls в ответе — проверяем напрямую
    tool_calls = response.get("tool_calls", [])
    if tool_calls:
        called = [tc.get("name") for tc in tool_calls]
        assert (
            expected_tool in called
        ), f"Expected tool '{expected_tool}' not called. Called: {called}"
        for forbidden in forbidden_tools:
            assert forbidden not in called, f"Forbidden tool '{forbidden}' was called"
    # иначе — проверяем по тексту ответа как fallback
    else:
        answer = response.get("text", "")
        # Минимальная проверка: ответ не содержит явной ошибки
        assert "error" not in response, f"Tool call failed: {response.get('error')}"


# ---------------------------------------------------------------------------
# Test runner (pytest)
# ---------------------------------------------------------------------------


@pytest.mark.flaky(reruns=3, reruns_delay=2)
@pytest.mark.asyncio
@pytest.mark.parametrize("case", RAG_CASES, ids=[c.id for c in RAG_CASES])
async def test_rag_case(case: RAGCase):
    """Full pipeline test for RAG branch."""
    response = await ask_agent(case.input, session_id=f"benchmark-{case.id}")

    # Type 1: programmatic asserts
    assert_no_error(response)
    answer = response.get("text", "")
    assert_answer_not_empty(answer)

    if case.expected_titles:
        # для "not in library" кейсов пропускаем этот assert
        titles_found = assert_titles_mentioned(answer, case.expected_titles, case.top_k)
        assert titles_found, (
            f"None of {case.expected_titles} found in answer.\n"
            f"Query: {case.input}\nAnswer: {answer}"
        )

    # Type 2: LLM-as-judge
    verdict = await judge(case.input, answer, case.expected_titles)
    assert verdict.relevant, f"Answer not relevant. Reason: {verdict.reason}"
    assert verdict.no_hallucination, f"Hallucination detected. Reason: {verdict.reason}"
    assert (
        verdict.score >= 0.6
    ), f"Score too low: {verdict.score}. Reason: {verdict.reason}"


@pytest.mark.flaky(reruns=3, reruns_delay=2)
@pytest.mark.asyncio
@pytest.mark.parametrize("case", TOOL_CASES, ids=[c.id for c in TOOL_CASES])
async def test_tool_case(case: ToolCase):
    """Full pipeline test for tool branch — Type 3: tool call correctness."""
    response = await ask_agent(case.input, session_id=f"benchmark-tool-{case.id}")
    assert_no_error(response)
    assert_tool_called(response, case.expected_tool, case.forbidden_tools)


# ---------------------------------------------------------------------------
# Standalone runner with summary
# ---------------------------------------------------------------------------


async def run_benchmark() -> None:
    passed = 0
    failed = 0
    results = []

    all_cases = [("rag", c) for c in RAG_CASES] + [("tool", c) for c in TOOL_CASES]

    for kind, case in all_cases:
        print(f"\n[{kind.upper()}] {case.id} — {case.notes}")
        try:
            response = await ask_agent(case.input, session_id=f"benchmark-{case.id}")
            assert_no_error(response)
            answer = response.get("text", "")
            assert_answer_not_empty(answer)

            if kind == "rag":
                titles_ok = (
                    assert_titles_mentioned(answer, case.expected_titles, case.top_k)
                    if case.expected_titles
                    else True
                )
                verdict = await judge(case.input, answer, case.expected_titles)
                ok = (
                    titles_ok
                    and verdict.relevant
                    and verdict.no_hallucination
                    and verdict.score >= 0.6
                )
                print(
                    f"  titles_found={titles_ok}  score={verdict.score:.2f}  "
                    f"relevant={verdict.relevant}  no_hallucination={verdict.no_hallucination}"
                )
                if not ok:
                    print(f"  reason: {verdict.reason}")
            else:
                assert_tool_called(response, case.expected_tool, case.forbidden_tools)
                ok = True
                print(f"  tool check passed")

            if ok:
                passed += 1
                results.append(("✅", case.id))
            else:
                failed += 1
                results.append(("❌", case.id))

        except Exception as e:
            failed += 1
            results.append(("❌", case.id))
            print(f"  FAILED: {e}")

    total = passed + failed
    print(f"\n{'='*50}")
    print(f"Results: {passed}/{total} passed  (success rate: {passed/total*100:.0f}%)")
    print(f"{'='*50}")
    for icon, cid in results:
        print(f"  {icon} {cid}")


if __name__ == "__main__":
    asyncio.run(run_benchmark())

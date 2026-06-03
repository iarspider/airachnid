from graph.state import AgentState
from llm import invoke_llm
from prompts import TRANSLATION_PROMPT


def node_query_rewriter(state: AgentState) -> AgentState:
    ans = invoke_llm(
        system_message="Generate search query from user request. Return ONLY search query. Return only one query. Maxiumu 10 words. No explanations.",
        user_message=state.get("translated_message", ""),
    )
    return {**state, "ddg_query": ans}


def node_rag_query_rewriter(state: AgentState) -> AgentState:
    QUERY_REWRITE_PROMPT = """
    Extract the game title or search keywords from the user's question.
    Return ONLY 3-5 keywords or the game title. Maximum 10 words. No sentences.
    Examples:
    - "Do I have Assassin's Creed?" → "Assassin's Creed"
    - "Find me open world games" → "open world exploration"
    - "Something atmospheric for the evening" → "atmospheric calm relaxing"
    """

    res = invoke_llm(QUERY_REWRITE_PROMPT, state.get("translated_message", ""))[:500]
    return {**state, "rag_query": res}


def node_translate_query(state: AgentState) -> AgentState:
    english_query = invoke_llm(
        TRANSLATION_PROMPT,
        state.get("normalized_message", ""),
    )

    return {**state, "translated_message": english_query}

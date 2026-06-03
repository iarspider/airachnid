from graph.state import AgentState
from llm import invoke_llm


def format_ddg_context(results: list) -> str:
    parts = []
    for r in results:
        parts.append(f"**{r['title']}**\n{r['body']}\nSource: {r['href']}")
    return "\n\n---\n\n".join(parts)


def format_context(docs: list[str]) -> str:
    if not docs:
        return "No results found."
    return "\n\n---\n\n".join(docs)


def node_generate_output(state: AgentState) -> AgentState:
    prompt = """You are a helpful assistant that helps the user find games from their personal game library.
You MUST base your answer ONLY on the provided context. Do not use your own knowledge about games.
If the context does not contain enough information to answer, say so honestly.
Always answer in the same language the user used.

Context:
{context}"""

    if state.get("need_search", False):
        final_prompt = prompt.format(
            context=format_ddg_context(state.get("search_results", []))
        )
    else:
        final_prompt = prompt.format(
            context=format_context(state.get("retrieved_docs", []))
        )

    final_answer = invoke_llm(final_prompt, state.get("translated_message", ""))
    return {**state, "final_answer": final_answer}

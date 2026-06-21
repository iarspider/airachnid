from langfuse import propagate_attributes
from langfuse.langchain import CallbackHandler
from langgraph.graph.state import CompiledStateGraph
from loguru import logger

from graph.state import AgentState


async def run_agent(
    message: str, user: str, session: str, graph: CompiledStateGraph, langfuse_client
) -> str:

    state: AgentState = {
        "raw_message": message,
        "normalized_message": "",
        "translated_message": "",
        "session_id": session,
        #
        "intent": "invalid",
        # "messages": [],
        #
        "validation_passed": False,
        #
        "ddg_query": "",
        "rag_query": "",
        "retrieved_docs": [],
        "need_search": False,
        "search_results": [],
        #
        "final_answer": "",
        "success": True,
        "error": "",
        "retry": False,
        "retries": 0,
    }

    print(graph.get_graph().draw_mermaid())
    print("=" * 80)

    with langfuse_client.start_as_current_observation(
        as_type="span",
        name="agent-invoke",
        input={"text": message},
    ) as root:
        with propagate_attributes(user_id=str(user), session_id=str(session)):
            handler = CallbackHandler()

            try:
                result = await graph.ainvoke(
                    state,
                    config={
                        "configurable": {"thread_id": str(session)},
                        "callbacks": [handler],
                    },
                )  # type: ignore
                state["final_answer"] = result.get("final_answer", "Нет ответа.")
                root.update(output={"text": state["final_answer"]})
            except Exception as exc:
                logger.opt(exception=exc).error("Внутренняя ошибка агента")
                state["success"] = False
                state["error"] = f"Внутренняя ошибка агента ({type(exc)}: {str(exc)})"
                root.update(output={"error": state["error"]}, level="ERROR")

    if state.get("success", False):
        return {"text": state["final_answer"]}
    else:
        return {"error": state["error"]}

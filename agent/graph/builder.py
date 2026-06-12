from langfuse.langchain import CallbackHandler
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from graph.nodes.misc import node_error_handler, node_increment_retry
from graph.nodes.output import node_generate_output
from graph.nodes.query_rewriter import (
    node_query_rewriter,
    node_rag_query_rewriter,
    node_translate_query,
)
from graph.nodes.rag import node_rag
from graph.nodes.router import (
    route_after_route_rag_or_tool,
    router_after_validate,
    router_ddg_or_return,
    node_rag_or_tool,
    router_after_validate_output,
    route_after_call_tools,
)
from graph.nodes.tool import node_call_tools
from graph.nodes.search import node_ddg_search
from graph.nodes.validator import node_validate_request, node_validate_output
from graph.state import AgentState


async def build_graph(checkpointer=None) -> CompiledStateGraph:
    """Build and compile the LangGraph agent."""
    graph = StateGraph(AgentState)

    # Add nodes
    graph.add_node("validate_request", node_validate_request)
    graph.add_node("route_rag_or_tool", node_rag_or_tool)
    graph.add_node("call_tools", node_call_tools)
    graph.add_node("ddg_rewriter", node_query_rewriter)
    graph.add_node("rag_rewriter", node_rag_query_rewriter)
    graph.add_node("query_translator", node_translate_query)
    graph.add_node("ddg", node_ddg_search)
    graph.add_node("rag", node_rag)
    graph.add_node("generate_output", node_generate_output)
    graph.add_node("validate_output", node_validate_output)
    graph.add_node("error_handler", node_error_handler)
    graph.add_node("increment_retry", node_increment_retry)

    # Linear edges
    graph.set_entry_point("validate_request")
    graph.add_edge(START, "validate_request")
    graph.add_edge("error_handler", END)
    graph.add_edge("ddg_rewriter", "ddg")
    graph.add_edge("ddg", "generate_output")
    graph.add_edge("generate_output", "validate_output")
    graph.add_edge("rag_rewriter", "rag")
    graph.add_edge("query_translator", "route_rag_or_tool")
    graph.add_edge("increment_retry", "route_rag_or_tool")

    ## graph.add_edge("validate_output", END)

    # Conditional edges (branching points)
    graph.add_conditional_edges(
        "validate_request",
        router_after_validate,
        {"error_handler": "error_handler", "route_request": "query_translator"},
    )

    graph.add_conditional_edges(
        "route_rag_or_tool",
        route_after_route_rag_or_tool,
        {"invalid": "error_handler", "rag": "rag_rewriter", "tool": "call_tools"},
    )

    graph.add_conditional_edges(
        "rag",
        router_ddg_or_return,
        {"ddg": "ddg_rewriter", "generate_output": "generate_output"},
    )

    graph.add_conditional_edges(
        "validate_output",
        router_after_validate_output,
        {"retry": "increment_retry", "success": END, "error": "error_handler"},
    )

    graph.add_conditional_edges(
        "call_tools", route_after_call_tools, {"success": END, "error": "error_handler"}
    )

    langfuse_handler = CallbackHandler()

    return graph.compile(checkpointer=checkpointer).with_config(
        {"callbacks": [langfuse_handler]}
    )

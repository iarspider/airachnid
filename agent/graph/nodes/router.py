import json
import re

from loguru import logger
from pydantic import BaseModel
from pydantic_ai import Agent, UnexpectedModelBehavior, TextOutput
from pydantic_ai.capabilities import Instrumentation
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.models.ollama import OllamaModel
from pydantic_ai.providers.ollama import OllamaProvider

from config import agent_settings
from graph.state import AgentState
from llm import invoke_llm, get_pydantic_ai_model
from prompts import RAG_OR_TOOL_PROMPT, TOOL_CALL_PROMPT
from tools.mcp_client import get_client


class ToolCallResult(BaseModel):
    called: bool
    tool_name: str | None = None
    result: str | None = None


def router_after_validate(state: AgentState) -> str:
    if state.get("validation_passed"):
        return "route_request"
    return "error_handler"


def route_after_route_rag_or_tool(state: AgentState) -> str:
    return state.get("intent", "invalid")


def router_after_validate_output(state: AgentState) -> str:
    if state["success"]:
        return "success"

    if state["retry"] and state["retries"] < agent_settings.graph_max_retries:
        # state["retries"] += 1
        return "retry"

    return "error"


def router_ddg_or_return(state: AgentState) -> str:
    return "ddg" if state.get("need_search") else "generate_output"


def node_rag_or_tool(state: AgentState) -> AgentState:
    res = invoke_llm(
        RAG_OR_TOOL_PROMPT,
        state.get("translated_message", ""),
        model=agent_settings.ollama.classifier_model,
    )

    res = re.sub("[^a-z]", "", res.strip().lower())

    if res not in ("tool", "rag"):
        logger.warning(f"Router returned invalid response: {res}")
        res = "invalid"
        state["success"] = False
        state["error"] = f"Router returned invalid response: {res}"

    logger.info(f"Classified request as {res}")

    return {**state, "intent": res}


def format_light_state(state: dict) -> str:
    if not state.get("result"):
        return "Lights: unavailable"

    bulbs = state.get("state", {}).values()
    online = [b for b in bulbs if b["state"] != "Offline"]

    if not online:
        return "Lights: all offline"

    # Берём состояние первой онлайн-лампочки как репрезентативное
    b = online[0]
    status = b["state"]  # "On" / "Off"
    brightness = (
        f", brightness {round(b['brightness']/255*100)}%" if b.get("brightness") else ""
    )
    color = f", RGB({b['r']},{b['g']},{b['b']})" if b.get("r") is not None else ""

    return f"Lights: {status}{brightness}{color}"


def format_vlc_state(state: dict) -> str:
    if not state.get("result"):
        return "VLC status unavailable."

    playback_state = state.get("state", "unknown")
    filename = state.get("file", "unknown")
    volume = state.get("volume_percent", 0)
    time = state.get("time", 0)
    length = state.get("length", 0)

    time_str = _format_seconds(time)
    length_str = _format_seconds(length)

    lines = [
        f"VLC state: {playback_state}",
        f"Now playing: {filename}",
        f"Position: {time_str} / {length_str}",
        f"Volume: {volume}%",
    ]
    return "\n".join(lines)


def _format_seconds(seconds: int) -> str:
    if not seconds:
        return "0:00"
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


async def node_call_tools(state: AgentState) -> AgentState:
    client = get_client()
    light_state_s = (await client.get_resources(uris="light://state"))[0].as_string()
    light_state = format_light_state(json.loads(light_state_s))

    vlc_state_s = (await client.get_resources(uris="vlc://status"))[0].as_string()
    vlc_state = format_vlc_state(json.loads(vlc_state_s))

    mcp_server = MCPToolset(
        f"http://{agent_settings.mcp.host}:{agent_settings.mcp.port}/mcp"
    )

    model = get_pydantic_ai_model(agent_settings.ollama.model)

    agent = Agent(
        model=model,
        toolsets=[mcp_server],
        system_prompt=TOOL_CALL_PROMPT.format(
            light_state=light_state, vlc_state=vlc_state
        ),
        output_type=TextOutput(str),
        retries=agent_settings.tool_call_max_retries,
        capabilities=[Instrumentation()],
    )

    async with agent:
        try:
            result = await agent.run(state.get("translated_message", ""), retries=5)
        except UnexpectedModelBehavior as e:
            logger.error(f"Tool call failed after retries: {e}")
            return {
                **state,
                "error": "Ошибка вызова инструментов",
                "success": False,
                "retry": False,
            }

    return {**state, "final_answer": result.output}

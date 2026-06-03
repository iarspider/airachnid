from langchain_mcp_adapters.client import MultiServerMCPClient

from config import agent_settings

_client: MultiServerMCPClient | None = None
_tools: list | None = None


async def init_mcp_client() -> None:
    global _client, _tools
    _client = MultiServerMCPClient(
        {
            "airachnid": {
                "url": f"http://{agent_settings.mcp.host}:{agent_settings.mcp.port}/mcp",
                "transport": "http",
            }
        }  # type: ignore
    )

    _tools = await _client.get_tools()


def get_tools() -> list:
    if _tools is None:
        raise RuntimeError("MCP client not initialized")
    return _tools


def get_client() -> MultiServerMCPClient:
    if _client is None:
        raise RuntimeError("MCP client not initialized")
    return _client

import logging

from fastmcp import Context, FastMCP
from fastmcp.server.lifespan import lifespan
from starlette.requests import Request
from starlette.responses import PlainTextResponse

import tools.vlc
import tools.wiz
from settings import mcp_settings


class HealthCheckFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return "GET /healthz" not in record.getMessage()


logging.getLogger("uvicorn.access").addFilter(HealthCheckFilter())


# Initialize FastMCP server
mcp = FastMCP(
    "airachnid_mcp",
)


@mcp.custom_route("/healthz", methods=["GET"])
async def health_check(request: Request) -> PlainTextResponse:
    return PlainTextResponse("OK")


tools.wiz.register(mcp)

tools.vlc.register(mcp)

if __name__ == "__main__":
    mcp.run(transport="http")

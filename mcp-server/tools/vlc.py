import json

import httpx
from fastmcp import Context, FastMCP
from fastmcp.dependencies import CurrentContext

from settings import mcp_settings

_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    global _client
    if not _client:
        _client = httpx.AsyncClient(
            auth=httpx.BasicAuth(username="", password=mcp_settings.vlc_http_password)
        )
    return _client


async def request(endpoint: str, params: dict | None = None) -> tuple[bool, str, str]:
    url = f"http://{mcp_settings.vlc_host}:{mcp_settings.vlc_port}/requests/{endpoint}"
    try:
        response = await get_client().get(url, params=params, timeout=10)
        response.raise_for_status()
        return True, response.text, ""
    except httpx.HTTPError as e:
        return False, "", str(e)


async def vlc_command(
    command: str, val=None, option=None, input=None
) -> tuple[bool, str]:
    params = {"command": command}
    if val is not None:
        params["val"] = val
    if option is not None:
        params["option"] = option
    if input is not None:
        params["input"] = input
    success, _, error = await request("status.xml", params=params)
    return success, error


async def get_status_json() -> tuple[bool, dict, str]:
    success, body, error = await request("status.json")
    if not success:
        return False, {}, error
    try:
        return True, json.loads(body), ""
    except json.JSONDecodeError as e:
        return False, {}, f"Failed to parse VLC response: {e}"


def register(mcp: FastMCP):

    # --- Resources ---

    @mcp.resource("vlc://status")
    async def get_status(ctx: Context = CurrentContext()) -> str:
        """Get the current VLC playback status including state, position, filename and volume."""
        await ctx.info("Fetching VLC status")
        success, status, error = await get_status_json()
        if not success:
            await ctx.error(f"Failed to get VLC status: {error}")
            return json.dumps({"result": False, "error": error})

        filename = (
            status.get("information", {})
            .get("category", {})
            .get("meta", {})
            .get("filename", "unknown")
        )

        title = (
            status.get("information", {})
            .get("category", {})
            .get("meta", {})
            .get("title", "без названия")
        )

        artist = (
            status.get("information", {})
            .get("category", {})
            .get("meta", {})
            .get("artist", "автор неизвестен")
        )

        return json.dumps(
            {
                "result": True,
                "error": "",
                "state": status.get("state", "unknown"),
                "time": status.get("time", 0),
                "length": status.get("length", 0),
                "file": filename,
                "title": title,
                "artist": artist,
                "volume_percent": int(status.get("volume", 0) * 100 / 256),
            }
        )

    # --- Playback tools ---

    @mcp.tool()
    async def vlc_play(ctx: Context = CurrentContext()) -> dict:
        """Start VLC playback."""
        await ctx.info("Starting VLC playback")
        success, error = await vlc_command("pl_play")
        if not success:
            await ctx.error(f"Failed to start playback: {error}")
        return {"result": success, "error": error, "status": get_status(ctx)}

    @mcp.tool()
    async def vlc_resume(ctx: Context = CurrentContext()) -> dict:
        """Resume VLC playback."""
        await ctx.info("Resuming VLC playback")
        success, error = await vlc_command("pl_forceresume")
        if not success:
            await ctx.error(f"Failed to resume playback: {error}")
        return {"result": success, "error": error, "status": get_status(ctx)}

    @mcp.tool()
    async def vlc_pause(ctx: Context = CurrentContext()) -> dict:
        """Pause VLC playback."""
        await ctx.info("Pausing VLC playback")
        success, error = await vlc_command("pl_forcepause")
        if not success:
            await ctx.error(f"Failed to pause playback: {error}")
        return {"result": success, "error": error, "status": get_status(ctx)}

    @mcp.tool()
    async def vlc_stop(ctx: Context = CurrentContext()) -> dict:
        """Stop VLC playback."""
        await ctx.info("Stopping VLC playback")
        success, error = await vlc_command("pl_stop")
        if not success:
            await ctx.error(f"Failed to stop playback: {error}")
        return {"result": success, "error": error, "status": get_status(ctx)}

    @mcp.tool()
    async def vlc_next(ctx: Context = CurrentContext()) -> dict:
        """Skip to the next track in VLC playlist."""
        await ctx.info("Skipping to next track")
        success, error = await vlc_command("pl_next")
        if not success:
            await ctx.error(f"Failed to skip to next track: {error}")
        return {"result": success, "error": error, "status": get_status(ctx)}

    @mcp.tool()
    async def vlc_prev(ctx: Context = CurrentContext()) -> dict:
        """Skip to the previous track in VLC playlist."""
        await ctx.info("Skipping to previous track")
        success, error = await vlc_command("pl_previous")
        if not success:
            await ctx.error(f"Failed to skip to previous track: {error}")
        return {"result": success, "error": error, "status": get_status(ctx)}

    @mcp.tool()
    async def seek(value: str, ctx: Context = CurrentContext()) -> dict:
        """Seek to a position. Format: [+/-][Xh][Xm][Xs]. Example: +30s, -1m, 1h30m."""
        await ctx.info(f"Seeking to {value}")
        success, error = await vlc_command("seek", val=value)
        if not success:
            await ctx.error(f"Failed to seek: {error}")
        return {"result": success, "error": error, "status": get_status(ctx)}

    # --- Volume tools ---

    @mcp.tool()
    async def set_volume(volume_level: int, ctx: Context = CurrentContext()) -> dict:
        """Set VLC volume (0-200, where 100 is normal).

        Args:
            volume_level: volume percentage between 0 and 200
        """
        if not 0 <= volume_level <= 200:
            await ctx.error(f"Invalid volume level: {volume_level}")
            return {
                "result": False,
                "error": f"Invalid volume: {volume_level}. Use 0-200.",
            }
        await ctx.info(f"Setting volume to {volume_level}%")
        success, error = await vlc_command("volume", val=int(volume_level * 256 / 100))
        if not success:
            await ctx.error(f"Failed to set volume: {error}")
        return {"result": success, "error": error}

    @mcp.tool()
    async def adjust_volume(change: int, ctx: Context = CurrentContext()) -> dict:
        """Increase or decrease VLC volume by a percentage. Positive = louder, negative = quieter.

        Args:
            change: percentage to change volume by (e.g. +10 or -20)
        """
        success, status, error = await get_status_json()
        if not success:
            await ctx.error(f"Failed to get current volume: {error}")
            return {"result": False, "error": f"Failed to get volume: {error}"}

        current = int(status.get("volume", 0) * 100 / 256)
        new = max(0, min(200, current + change))
        await ctx.info(f"Adjusting volume from {current}% to {new}%")
        success, error = await vlc_command("volume", val=int(new * 256 / 100))
        if not success:
            await ctx.error(f"Failed to adjust volume: {error}")
            return {"result": False, "error": error}

        return {"result": True, "error": "", "volume_from": current, "volume_to": new}

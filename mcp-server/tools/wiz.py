import json
from typing import Callable, Literal

from fastmcp import Context, FastMCP
from fastmcp.dependencies import CurrentContext
from pydantic import BaseModel
from pywizlight import PilotBuilder, PilotParser, wizlight

from settings import mcp_settings


class BulbState(BaseModel):
    state: Literal["Offline", "On", "Off"]
    brightness: int | None
    r: int | None
    g: int | None
    b: int | None


_bulbs: list[wizlight] | None = None


def get_bulbs() -> list[wizlight]:
    global _bulbs
    if _bulbs is None:
        _bulbs = [wizlight(b["ip"], mac=b["mac"]) for b in mcp_settings.wiz_bulbs_list]
    return _bulbs


async def _apply_to_all_bulbs(
    pilot: PilotBuilder | Callable[[PilotParser], PilotBuilder],
    ctx: Context = CurrentContext(),
) -> dict:
    bulbs = get_bulbs()
    ret: dict = {"result": False, "errors": []}
    for bulb in bulbs:
        state = await bulb.updateState()
        if not state:
            msg = f"Bulb {bulb.ip} not found"
            await ctx.error(msg)
            ret["errors"].append(msg)
            continue
        cmd: PilotBuilder = pilot if isinstance(pilot, PilotBuilder) else pilot(state)
        if cmd.pilot_params.get("state", True):
            await bulb.turn_on(cmd)
        else:
            await bulb.turn_off()
        ret["result"] = True
    return ret


def register(mcp: FastMCP):

    @mcp.resource(
        "light://state",
        title="get_state",
        description="Get current lights state",
    )
    async def get_state(ctx: Context = CurrentContext()) -> str:
        """Get current state of all WiZ bulbs."""
        await ctx.info("Fetching WiZ bulbs state")
        bulbs = get_bulbs()
        # result=True означает "хотя бы одна лампочка ответила"
        ret: dict = {"state": {}, "errors": [], "result": False}

        for bulb in bulbs:
            state = await bulb.updateState()
            if not state:
                msg = f"Bulb {bulb.ip} not found"
                await ctx.error(msg)
                ret["errors"].append(msg)
                ret["state"][bulb.ip] = BulbState(
                    state="Offline", brightness=None, r=None, g=None, b=None
                ).model_dump()
                continue

            ret["state"][bulb.ip] = BulbState(
                state="On" if state.get_state() else "Off",
                brightness=state.get_brightness(),
                r=state.get_rgb()[0],  # type: ignore
                g=state.get_rgb()[1],  # type: ignore
                b=state.get_rgb()[2],  # type: ignore
            ).model_dump()
            ret["result"] = True

        return json.dumps(ret)

    @mcp.tool("toggle", description="Toggle light state")
    async def toggle(ctx: Context = CurrentContext()) -> dict:
        """Toggle light on/off."""
        await ctx.info("Toggling lights")
        return await _apply_to_all_bulbs(
            lambda s: PilotBuilder(state=not s.get_state()), ctx
        )

    @mcp.tool("turn-on", description="Turn on the light")
    async def turn_on(ctx: Context = CurrentContext()) -> dict:
        """Turn the light on."""
        await ctx.info("Turning lights on")
        return await _apply_to_all_bulbs(PilotBuilder(state=True), ctx)

    @mcp.tool("turn-off", description="Turn off the light")
    async def turn_off(ctx: Context = CurrentContext()) -> dict:
        """Turn the light off."""
        await ctx.info("Turning lights off")
        return await _apply_to_all_bulbs(PilotBuilder(state=False), ctx)

    @mcp.tool("set-brightness", description="Set brightness level [0-255]")
    async def set_brightness(level: int, ctx: Context = CurrentContext()) -> dict:
        """Set light brightness.

        Args:
            level: desired brightness, valid range [0, 255]
        """
        if not (0 <= level <= 255):
            await ctx.error(f"Invalid brightness: {level}")
            return {"result": False, "errors": [f"Invalid brightness {level}"]}
        await ctx.info(f"Setting brightness to {level}")
        return await _apply_to_all_bulbs(
            PilotBuilder(state=True, brightness=level), ctx
        )

    @mcp.tool("set-rgb", description="Set light RGB color [0-255]")
    async def set_rgb(r: int, g: int, b: int, ctx: Context = CurrentContext()) -> dict:
        """Set light RGB color.

        Args:
            r: level of red (0-255)
            g: level of green (0-255)
            b: level of blue (0-255)
        """
        for val, name in [(r, "red"), (g, "green"), (b, "blue")]:
            if not (0 <= val <= 255):
                await ctx.error(f"Invalid {name} level: {val}")
                return {"result": False, "errors": [f"Invalid {name} level {val}"]}
        await ctx.info(f"Setting RGB to ({r}, {g}, {b})")
        return await _apply_to_all_bulbs(PilotBuilder(state=True, rgb=(r, g, b)), ctx)

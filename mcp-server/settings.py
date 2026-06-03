from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class MCPSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    wiz_bulbs: str = Field(alias="WIZ_BULBS", default="")
    vlc_host: str = Field(alias="VLC_HTTP_HOST", default="localhost")
    vlc_port: int = Field(alias="VLC_HTTP_PORT", default=8080)
    vlc_http_password: str = Field(alias="VLC_HTTP_PASSWORD", default="password")

    @property
    def wiz_bulbs_list(self) -> list[dict]:
        result = []
        for bulb in self.wiz_bulbs.split(","):
            ip, mac = bulb.strip().split(":")
            result.append({"ip": ip, "mac": mac})
        return result


mcp_settings = MCPSettings()

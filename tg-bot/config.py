from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class BotSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    token: str = Field(alias="TELEGRAM_BOT_TOKEN")
    whitelist_s: str = Field(alias="WHITELIST", default="")
    agent_host: str = Field(alias="AGENT_HOST")
    agent_port: int = Field(alias="AGENT_PORT", default=8000)

    @property
    def invoke_url(self) -> str:
        return f"http://{self.agent_host}:{self.agent_port}/invoke"

    @property
    def reindex_url(self) -> str:
        return f"http://{self.agent_host}:{self.agent_port}/reindex"

    @property
    def whitelist(self) -> list[str]:
        return self.whitelist_s.split(",")


bot_settings = BotSettings()

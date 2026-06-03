from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    host: str = Field(alias="POSTGRES_HOST")
    port: int = Field(alias="POSTGRES_PORT", default=5432)
    db: str = Field(alias="POSTGRES_DB")
    user: str = Field(alias="AGENT_DB_USER")
    password: str = Field(alias="AGENT_DB_PASSWORD")
    table_name: str = Field(alias="TABLE_NAME")
    # vector_size: int = Field(alias="VECTOR_SIZE") - hardcoded

    @property
    def url(self) -> str:
        return f"postgresql+psycopg://{self.user}:{self.password}@{self.host}:{self.port}/{self.db}"


class RedisSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    host: str = Field(alias="REDIS_HOST")
    port: int = Field(alias="REDIS_PORT", default=6379)
    password: str = Field(alias="REDIS_PASSWORD")

    @property
    def url(self) -> str:
        return f"redis://:{self.password}@{self.host}:{self.port}"


class OllamaSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    base_url: str = Field(alias="OLLAMA_BASE_URL")
    model: str = Field(alias="OLLAMA_MODEL")
    classifier_model: str = Field(alias="CLASSIFIER_MODEL")

    @property
    def pydantic_ai_base_url(self):
        return f"{self.base_url}/v1"


class MCPSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    host: str = Field(alias="MCP_SERVER_HOST")
    port: int = Field(alias="MCP_SERVER_PORT", default=8000)

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"


class LangfuseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    host: str = Field(alias="LANGFUSE_BASE_URL")
    public_key: str = Field(alias="LANGFUSE_PUBLIC_KEY")
    secret_key: str = Field(alias="LANGFUSE_SECRET_KEY")


class AgentSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    host: str = Field(alias="AGENT_HOST", default="0.0.0.0")
    port: int = Field(alias="AGENT_PORT", default=8000)
    tool_call_max_retries: int = Field(default=3)
    graph_max_retries: int = Field(default=3)

    search_alpha: float = Field(default=0.5)  # weight on vector vs BM25
    search_threshold: float = Field(default=0.45)
    final_validation_threshold: float = Field(default=0.8)

    llm_prompt_validation: bool = Field(True)

    db: DatabaseSettings = DatabaseSettings()
    redis: RedisSettings = RedisSettings()
    ollama: OllamaSettings = OllamaSettings()
    mcp: MCPSettings = MCPSettings()
    langfuse: LangfuseSettings = LangfuseSettings()


agent_settings = AgentSettings()

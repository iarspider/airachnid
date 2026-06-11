from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_ollama import ChatOllama
from langchain_openrouter import ChatOpenRouter
from pydantic_ai import Agent
from pydantic_ai.models.ollama import OllamaModel
from pydantic_ai.models.openrouter import OpenRouterModel
from pydantic_ai.providers.ollama import OllamaProvider
from pydantic_ai.providers.openrouter import OpenRouterProvider

from config import agent_settings


def invoke_llm(
    system_message: str,
    user_message: str,
    model: str | None = None,
    extra_messages: list | None = None,
) -> str:
    model = model or agent_settings.ollama.model

    if agent_settings.ollama.provider == "ollama":
        ollama = ChatOllama(
            model=model,
            base_url=agent_settings.ollama.base_url,
            temperature=0,
        )
    else:
        ollama = ChatOpenRouter(
            model=agent_settings.ollama.openrouter_model, temperature=0
        )

    messages = [
        SystemMessage(content=system_message),
        HumanMessage(content=user_message),
    ]
    if extra_messages:
        messages.extend(extra_messages)

    resp = ollama.invoke(messages)

    answer_text = resp.content

    return str(answer_text)


def get_agent(*args, **kwargs):
    return Agent(*args, **kwargs)


def get_pydantic_ai_model(model_name: str, temperature: float = 0.0):
    if agent_settings.ollama.provider == "ollama":
        return OllamaModel(
            model_name,
            provider=OllamaProvider(
                base_url=agent_settings.ollama.pydantic_ai_ollama_base_url
            ),
            settings={"temperature": temperature},
        )
    else:
        return OpenRouterModel(
            agent_settings.ollama.openrouter_model,
            provider=OpenRouterProvider(
                api_key=agent_settings.ollama.openrouter_api_key
            ),
            settings={"temperature": temperature},
        )

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_ollama import ChatOllama
from pydantic_ai import Agent

from config import agent_settings


def invoke_llm(
    system_message: str,
    user_message: str,
    model: str | None = None,
    extra_messages: list | None = None,
) -> str:
    model = model or agent_settings.ollama.model

    ollama = ChatOllama(
        model=model,
        base_url=agent_settings.ollama.base_url,
        temperature=0,
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


def get_agent(self, *args, **kwargs):
    return Agent(*args, **kwargs)

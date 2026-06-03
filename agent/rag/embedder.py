from langchain_ollama import OllamaEmbeddings

from config import agent_settings
from models.game import Game


def get_embedding_service() -> OllamaEmbeddings:
    return OllamaEmbeddings(
        model="mxbai-embed-large", base_url=agent_settings.ollama.base_url
    )

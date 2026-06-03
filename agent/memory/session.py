def make_config(session_id: int, user_id: int, callbacks: list) -> dict:
    """Build the LangGraph thread config for a given session."""
    return {
        "configurable": {
            "thread_id": str(session_id),
            "user_id": str(user_id),
        },
        "callbacks": callbacks,
    }

import os

from langfuse import LangfuseOtelSpanAttributes
from langfuse.langchain import \
    CallbackHandler as LangfuseCallbackHandler  # noqa: F401
from loguru import logger
from opentelemetry import trace as otel_trace


def get_langfuse_handler(
    session_id: str, user_id: str
) -> LangfuseCallbackHandler | None:
    """Return a Langfuse v4 callback handler, or None if not configured.

    Langfuse v4: auth is configured via env vars (LANGFUSE_SECRET_KEY,
    LANGFUSE_PUBLIC_KEY, LANGFUSE_HOST). session_id and user_id are attached
    as OpenTelemetry span attributes on the current span.
    """
    try:
        from config import agent_settings

        if (
            not agent_settings.langfuse.secret_key
            or not agent_settings.langfuse.public_key
        ):
            logger.warning("langfuse_not_configured", session_id=session_id)
            return None

        # Propagate auth to env so Langfuse SDK picks it up automatically
        os.environ.setdefault("LANGFUSE_SECRET_KEY", agent_settings.langfuse.secret_key)
        os.environ.setdefault("LANGFUSE_PUBLIC_KEY", agent_settings.langfuse.public_key)
        os.environ.setdefault("LANGFUSE_HOST", agent_settings.langfuse.host)

        # Attach session / user context to the current OTEL span
        span = otel_trace.get_current_span()
        if span and span.is_recording():
            span.set_attribute(LangfuseOtelSpanAttributes.TRACE_SESSION_ID, session_id)
            span.set_attribute(LangfuseOtelSpanAttributes.TRACE_USER_ID, user_id)

        return LangfuseCallbackHandler()
    except Exception as exc:
        logger.opt(exception=exc).error("LangFuse handler error!")
        return None

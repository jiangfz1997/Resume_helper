"""
Studio routing helper.

When settings.langgraph_studio_url is set, pipeline invocations are routed
through the LangGraph Studio Server so runs appear as live animations in Studio.
Otherwise falls back to local graph execution.
"""
import logging
import uuid
from typing import Any

logger = logging.getLogger(__name__)


async def _invoke(graph_name: str, local_graph: Any, state: dict) -> dict:
    from app.core.config import settings

    if not settings.langgraph_studio_url:
        logger.info("_studio | LANGGRAPH_STUDIO_URL not set, running %s locally", graph_name)
        return await local_graph.ainvoke(state)

    thread_id = str(uuid.uuid4())
    logger.info("_studio | routing %s through Studio @ %s thread_id=%s", graph_name, settings.langgraph_studio_url, thread_id)
    try:
        from langgraph.pregel.remote import RemoteGraph

        remote = RemoteGraph(graph_name, url=settings.langgraph_studio_url, timeout=600)
        result = await remote.ainvoke(state)
        logger.info("_studio | %s completed via Studio thread_id=%s", graph_name, thread_id)
        return result
    except ImportError:
        logger.warning("_studio | langgraph-sdk not installed, running %s locally", graph_name)
        return await local_graph.ainvoke(state)
    except Exception as exc:
        logger.warning("_studio | Studio unreachable (%s), running %s locally: %s", graph_name, graph_name, exc)
        return await local_graph.ainvoke(state)

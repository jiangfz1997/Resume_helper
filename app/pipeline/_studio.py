"""
Studio routing helper.

When settings.langgraph_studio_url is set, pipeline invocations are routed
through the LangGraph Studio Server so runs appear as live animations in Studio.
Otherwise falls back to local graph execution.
"""
import logging
from typing import Any

logger = logging.getLogger(__name__)


async def _invoke(graph_name: str, local_graph: Any, state: dict) -> dict:
    from app.core.config import settings

    if not settings.langgraph_studio_url:
        return await local_graph.ainvoke(state)

    try:
        from langgraph.pregel.remote import RemoteGraph

        logger.debug("_studio | routing %s through Studio @ %s", graph_name, settings.langgraph_studio_url)
        remote = RemoteGraph(graph_name, url=settings.langgraph_studio_url)
        return await remote.ainvoke(state)
    except ImportError:
        logger.warning("_studio | langgraph-sdk not installed, falling back to local execution")
        return await local_graph.ainvoke(state)
    except Exception as exc:
        logger.warning("_studio | Studio unreachable (%s), falling back to local execution", exc)
        return await local_graph.ainvoke(state)

import asyncio
import os

_MAX_LLM_CONCURRENCY = int(os.getenv("MAX_LLM_CONCURRENCY", "4"))

_llm_semaphore: asyncio.Semaphore | None = None


def get_llm_semaphore() -> asyncio.Semaphore:
    global _llm_semaphore
    if _llm_semaphore is None:
        _llm_semaphore = asyncio.Semaphore(_MAX_LLM_CONCURRENCY)
    return _llm_semaphore

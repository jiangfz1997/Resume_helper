import hashlib
import logging
from collections import OrderedDict
from pathlib import Path

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.core.model_factory import get_model_factory
from app.interfaces.base import IJDAnalyzer
from app.models.data_models import JobDescription

logger = logging.getLogger(__name__)

_prompt_text = (Path(__file__).parent.parent / "prompts" / "jd_analyzer.txt").read_text(encoding="utf-8")

_CACHE_MAX_SIZE = 128


class _LRUCache:
    def __init__(self, maxsize: int) -> None:
        self._cache: OrderedDict[str, JobDescription] = OrderedDict()
        self._maxsize = maxsize

    def get(self, key: str) -> JobDescription | None:
        if key not in self._cache:
            return None
        self._cache.move_to_end(key)
        return self._cache[key]

    def set(self, key: str, value: JobDescription) -> None:
        if key in self._cache:
            self._cache.move_to_end(key)
        else:
            if len(self._cache) >= self._maxsize:
                self._cache.popitem(last=False)
            self._cache[key] = value


_jd_cache = _LRUCache(_CACHE_MAX_SIZE)


def _cache_key(jd_text: str) -> str:
    return hashlib.sha256(jd_text.strip().encode()).hexdigest()


class OllamaJDAnalyzer(IJDAnalyzer):
    def __init__(self) -> None:
        model = get_model_factory().build("jd_analyzer")
        prompt = ChatPromptTemplate.from_template(_prompt_text)
        self._chain = prompt | model | JsonOutputParser()

    async def analyze(self, jd_text: str) -> JobDescription:
        key = _cache_key(jd_text)
        cached = _jd_cache.get(key)
        if cached is not None:
            logger.debug("jd_analyzer | cache hit | key=%.8s", key)
            return cached

        result = await self._chain.ainvoke({"jd_text": jd_text})
        logger.debug(
            "jd_analyzer | raw result | title=%r req=%s pref=%s n2h=%s",
            result.get("title"), result.get("tech_required"), result.get("tech_preferred"), result.get("nice_to_have"),
        )
        jd = JobDescription.model_validate(result)
        _jd_cache.set(key, jd)
        logger.debug("jd_analyzer | cached | key=%.8s", key)
        return jd

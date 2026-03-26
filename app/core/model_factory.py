from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml
from langchain_ollama import ChatOllama

_CONFIG_PATH = Path(__file__).parent.parent.parent / "agents.yaml"


@dataclass(frozen=True)
class AgentModelConfig:
    model: str
    temperature: float
    base_url: str
    format: Optional[str] = None
    num_predict: Optional[int] = None


class ModelFactory:
    def __init__(self, config_path: Path = _CONFIG_PATH) -> None:
        raw: dict = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        default_base_url: str = raw.get("base_url", "http://localhost:11434")
        self._configs: dict[str, AgentModelConfig] = {}
        for name, params in (raw.get("agents") or {}).items():
            self._configs[name] = AgentModelConfig(
                model=params["model"],
                temperature=float(params.get("temperature", 0.3)),
                base_url=params.get("base_url", default_base_url),
                format=params.get("format"),
                num_predict=params.get("num_predict"),
            )

    def build(self, agent_name: str) -> ChatOllama:
        cfg = self._get(agent_name)
        kwargs: dict = {
            "model": cfg.model,
            "temperature": cfg.temperature,
            "base_url": cfg.base_url,
        }
        if cfg.format is not None:
            kwargs["format"] = cfg.format
        if cfg.num_predict is not None:
            kwargs["num_predict"] = cfg.num_predict
        return ChatOllama(**kwargs)

    def _get(self, agent_name: str) -> AgentModelConfig:
        cfg = self._configs.get(agent_name)
        if cfg is None:
            raise KeyError(
                f"No model config for agent {agent_name!r}. "
                f"Add it to agents.yaml. Available: {sorted(self._configs)}"
            )
        return cfg


_factory: Optional[ModelFactory] = None


def get_model_factory() -> ModelFactory:
    global _factory
    if _factory is None:
        _factory = ModelFactory()
    return _factory

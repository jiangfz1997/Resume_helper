from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml
from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import Runnable

_CONFIG_PATH = Path(__file__).parent.parent.parent / "agents.yaml"


@dataclass(frozen=True)
class AgentModelConfig:
    provider: str          # "ollama" | "google" | "openai"
    model: str
    temperature: float
    # Ollama-specific
    base_url: str = "http://localhost:11434"
    format: Optional[str] = None
    num_predict: Optional[int] = None
    # Google-specific
    api_key_env: str = "GOOGLE_API_KEY"
    thinking_level: Optional[str] = None
    max_retries: int = 3
    timeout: int = 30
    max_tokens: Optional[int] = None
    # OpenAI-specific
    openai_api_key_env: str = "OPENAI_API_KEY"


class ModelFactory:
    def __init__(self, config_path: Path = _CONFIG_PATH) -> None:
        raw: dict = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        default_provider: str = raw.get("default_provider", "ollama")
        default_base_url: str = raw.get("base_url", "http://localhost:11434")
        google_defaults: dict = raw.get("google", {})
        openai_defaults: dict = raw.get("openai", {})

        # If LLM_PROVIDER=openai, all agents whose provider would be "google"
        # are transparently rerouted to OpenAI using the openai.agents model map.
        self._active_provider: str = os.environ.get("LLM_PROVIDER", "").lower() or default_provider
        self._openai_agent_models: dict[str, str] = openai_defaults.get("agents", {})
        self._openai_defaults = openai_defaults

        self._configs: dict[str, AgentModelConfig] = {}
        for name, params in (raw.get("agents") or {}).items():
            provider = params.get("provider", default_provider)
            self._configs[name] = AgentModelConfig(
                provider=provider,
                model=params["model"],
                temperature=float(params.get("temperature", 0.3)),
                base_url=params.get("base_url", default_base_url),
                format=params.get("format"),
                num_predict=params.get("num_predict"),
                api_key_env=google_defaults.get("api_key_env", "GOOGLE_API_KEY"),
                thinking_level=params.get(
                    "thinking_level", google_defaults.get("thinking_level")
                ),
                max_retries=int(google_defaults.get("max_retries", 3)),
                timeout=int(google_defaults.get("timeout", 30)),
                max_tokens=params.get("max_tokens"),
                openai_api_key_env=openai_defaults.get("api_key_env", "OPENAI_API_KEY"),
            )

    def build(self, agent_name: str, max_tokens_override: Optional[int] = None) -> Runnable:
        cfg = self._resolve(agent_name)
        if max_tokens_override is not None:
            from dataclasses import replace
            cfg = replace(cfg, max_tokens=max_tokens_override)
        if cfg.provider == "openai":
            return self._build_openai(cfg)
        if cfg.provider == "google":
            return self._build_google(cfg)
        return self._build_ollama(cfg)

    def build_chat_model(self, agent_name: str) -> BaseChatModel:
        """Return the raw BaseChatModel without any retry wrapper.

        Required when the caller needs to call with_structured_output(),
        which is not available on RunnableRetry.
        """
        cfg = self._resolve(agent_name)
        if cfg.provider == "openai":
            return self._build_openai_raw(cfg)
        if cfg.provider == "google":
            return self._build_google_raw(cfg)
        return self._build_ollama(cfg)

    # ── provider resolution ─────────────────────────────────────────────────

    def _resolve(self, agent_name: str) -> AgentModelConfig:
        """Return config, swapping to OpenAI when LLM_PROVIDER=openai."""
        cfg = self._get(agent_name)
        if self._active_provider == "openai" and cfg.provider == "google":
            from dataclasses import replace
            openai_model = self._openai_agent_models.get(agent_name)
            if not openai_model:
                raise KeyError(
                    f"LLM_PROVIDER=openai but no model mapping found for agent {agent_name!r}. "
                    f"Add it under openai.agents in agents.yaml."
                )
            timeout = int(self._openai_defaults.get("timeout", 60))
            max_retries = int(self._openai_defaults.get("max_retries", 3))
            cfg = replace(cfg, provider="openai", model=openai_model,
                          timeout=timeout, max_retries=max_retries)
        return cfg

    # ── builders ────────────────────────────────────────────────────────────

    def _build_ollama(self, cfg: AgentModelConfig) -> BaseChatModel:
        from langchain_ollama import ChatOllama

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

    def _build_google_raw(self, cfg: AgentModelConfig) -> BaseChatModel:
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
        except ImportError as exc:
            raise RuntimeError(
                "langchain-google-genai is not installed. "
                "Run: pip install langchain-google-genai"
            ) from exc

        api_key = os.environ.get(cfg.api_key_env)
        model_name = os.environ.get(cfg.model)
        if not api_key:
            raise RuntimeError(
                f"Google API key not found. Set the {cfg.api_key_env!r} environment variable."
            )

        kwargs: dict = {
            "model": model_name,
            "google_api_key": api_key,
            "temperature": cfg.temperature,
            "max_retries": cfg.max_retries,
            "timeout": cfg.timeout,
        }
        if cfg.thinking_level is not None:
            kwargs["thinking_level"] = cfg.thinking_level
        if cfg.max_tokens is not None:
            kwargs["max_tokens"] = cfg.max_tokens

        return ChatGoogleGenerativeAI(**kwargs)

    def _build_google(self, cfg: AgentModelConfig) -> Runnable:
        model = self._build_google_raw(cfg)
        try:
            from google.genai.errors import ServerError
            return model.with_retry(
                retry_if_exception_type=(ServerError,),
                wait_exponential_jitter=True,
                stop_after_attempt=cfg.max_retries,
            )
        except ImportError:
            return model

    def _build_openai_raw(self, cfg: AgentModelConfig) -> BaseChatModel:
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as exc:
            raise RuntimeError(
                "langchain-openai is not installed. "
                "Run: pip install langchain-openai"
            ) from exc

        api_key = os.environ.get(cfg.openai_api_key_env)
        if not api_key:
            raise RuntimeError(
                f"OpenAI API key not found. Set the {cfg.openai_api_key_env!r} environment variable."
            )

        model_name = os.environ.get(cfg.model) or cfg.model
        kwargs: dict = {
            "model": model_name,
            "openai_api_key": api_key,
            "temperature": cfg.temperature,
            "max_retries": cfg.max_retries,
            "timeout": cfg.timeout,
        }
        if cfg.max_tokens is not None:
            kwargs["max_tokens"] = cfg.max_tokens

        return ChatOpenAI(**kwargs)

    def _build_openai(self, cfg: AgentModelConfig) -> Runnable:
        # ChatOpenAI has built-in retry via max_retries; no additional wrapper needed.
        return self._build_openai_raw(cfg)

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

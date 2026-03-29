"""
LangGraph Studio visualization entry point.

Each module-level variable is a compiled CompiledGraph exposed for graph visualization.
LangGraph API handles persistence and checkpointing automatically -- do not pass a
custom checkpointer here.
"""
from app.agents.experience_summarizer import ExperienceSummarizer
from app.agents.jd_analyzer import OllamaJDAnalyzer
from app.agents.profile_enricher import CodeProfileEnricher
from app.agents.profile_parser import TwoPhaseProfileParser
from app.agents.skill_matcher import OllamaSkillMatcher
from app.agents.top_n_selector import TopNSelector
from app.models.data_models import MasterProfile, Skill
from app.pipeline.pipeline import ResumePipeline
from app.pipeline.profile_pipeline import ProfileParsePipeline
from app.services.profile_manager import ProfileManager


# Profile PDF parse pipeline: parse -> enrich -> summarize -> END
profile_parse_graph = ProfileParsePipeline(
    parser=TwoPhaseProfileParser(),
    enricher=CodeProfileEnricher(),
    summarizer=ExperienceSummarizer(),
)._graph


class _StubProfileRepo:
    """No-op repository used only for LangGraph Studio graph structure visualization."""

    async def get_profile(self, *_: object) -> MasterProfile | None:
        return None

    async def upsert_profile(self, *_: object) -> None:
        pass

    async def append_profile_data(self, *_: object) -> None:
        pass

    async def append_skills(self, *_: object) -> None:
        pass

    async def replace_skills(self, *_: object) -> None:
        pass

    async def get_skills(self, *_: object) -> list[Skill]:
        return []


# JD analysis pipeline: load_profile -> analyze_jd -> select_top_n -> match_skills -> END
resume_pipeline_graph = ResumePipeline(
    profile_manager=ProfileManager(_StubProfileRepo()),  # type: ignore[arg-type]
    jd_analyzer=OllamaJDAnalyzer(),
    skill_matcher=OllamaSkillMatcher(),
    top_n_selector=TopNSelector(),
)._graph

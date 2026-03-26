"""
LangGraph Studio visualization entry point.

Each module-level variable is a compiled CompiledGraph exposed for graph visualization.
Agents are instantiated with real model configs (agents.yaml) but Ollama does not need
to be running — instantiation is lightweight, no LLM calls are made here.
"""
from app.agents.content_auditor import OllamaContentAuditor
from app.agents.content_drafter import OllamaContentDrafter
from app.agents.jd_analyzer import OllamaJDAnalyzer
from app.agents.profile_enricher import CodeProfileEnricher
from app.agents.profile_parser import TwoPhaseProfileParser
from app.agents.resume_auditor import OllamaResumeAuditor
from app.agents.resume_generator import OllamaResumeGenerator
from app.agents.skill_matcher import OllamaSkillMatcher
from app.pipeline.profile_pipeline import ProfileParsePipeline
from app.pipeline.v2_pipeline import V2ResumePipeline

# Profile PDF parse pipeline: parse → enrich → END
profile_parse_graph = ProfileParsePipeline(
    parser=TwoPhaseProfileParser(),
    enricher=CodeProfileEnricher(),
)._graph

# V2 resume generation pipeline: draft → audit → (approve → END | retry → draft)
v2_resume_graph = V2ResumePipeline(
    drafter=OllamaContentDrafter(),
    auditor=OllamaContentAuditor(),
)._graph

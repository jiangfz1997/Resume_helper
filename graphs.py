"""
LangGraph Studio visualization entry point.

Each module-level variable is a compiled CompiledGraph exposed for graph visualization.
LangGraph API handles persistence and checkpointing automatically -- do not pass a
custom checkpointer here.
"""
from app.agents.content_auditor import OllamaContentAuditor
from app.agents.content_drafter import OllamaContentDrafter
from app.agents.profile_enricher import CodeProfileEnricher
from app.agents.profile_parser import TwoPhaseProfileParser
from app.pipeline.profile_pipeline import ProfileParsePipeline
from app.pipeline.v2_pipeline import V2ResumePipeline
from app.services.phrase_filter import LocalPhraseFilter

# Profile PDF parse pipeline: parse -> enrich -> END
profile_parse_graph = ProfileParsePipeline(
    parser=TwoPhaseProfileParser(),
    enricher=CodeProfileEnricher(),
)._graph

# V2 resume generation pipeline: draft -> audit -> (approve -> END | retry -> draft)
# Post-processors run in order after the loop exits.
v2_resume_graph = V2ResumePipeline(
    drafter=OllamaContentDrafter(),
    auditor=OllamaContentAuditor(),
    post_processors=[
        LocalPhraseFilter(),
        # KeywordInjector(),     # P2: to be added
        # AlignmentValidator(),  # P4: to be added
    ],
)._graph

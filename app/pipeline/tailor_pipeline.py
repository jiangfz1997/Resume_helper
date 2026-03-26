from app.agents.jd_analyzer import OllamaJDAnalyzer
from app.agents.resume_tailor import OllamaResumeTailor
from app.agents.skill_matcher import OllamaSkillMatcher
from app.models.data_models import JobDescription, MatchingReport, MasterProfile, TailoredResumeDraft


class TailorPipeline:
    def __init__(
        self,
        jd_analyzer: OllamaJDAnalyzer,
        skill_matcher: OllamaSkillMatcher,
        tailor: OllamaResumeTailor,
    ) -> None:
        self._jd_analyzer = jd_analyzer
        self._skill_matcher = skill_matcher
        self._tailor = tailor

    async def run(
        self,
        profile: MasterProfile,
        base_resume: TailoredResumeDraft,
        jd_text: str,
    ) -> tuple[TailoredResumeDraft, JobDescription, MatchingReport]:
        jd = await self._jd_analyzer.analyze(jd_text)
        matching_report = await self._skill_matcher.match(profile, jd)
        tailored = await self._tailor.tailor(base_resume, jd, matching_report)
        tailored = tailored.model_copy(update={
            "template_id": base_resume.template_id,
            "template_source": base_resume.template_source,
        })
        return tailored, jd, matching_report

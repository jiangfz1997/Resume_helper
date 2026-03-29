"""
Rule-based Tier-1 diagnostic checker.

Detects missing or thin profile fields without any LLM calls.
Each check returns a DiagnosticTask with tier=tier1 when the condition fails.
"""

from app.models.data_models import (
    DiagnosticTask,
    DiagnosticTier,
    MasterProfile,
    TailoredResumeDraft,
)


def _task(task_id: str, title: str, description: str, section: str, action_label: str) -> DiagnosticTask:
    return DiagnosticTask(
        id=task_id,
        tier=DiagnosticTier.tier1,
        title=title,
        description=description,
        section=section,
        action_label=action_label,
    )


def run(profile: MasterProfile, draft: TailoredResumeDraft) -> list[DiagnosticTask]:
    """Return a list of Tier-1 tasks for every detected gap.  Empty list means all clear."""
    tasks: list[DiagnosticTask] = []
    ci = draft.contact_info or profile.contact_info

    # ── Contact info ────────────────────────────────────────────
    if ci is None or not (ci.email or ci.phone):
        tasks.append(_task(
            "t1_contact_missing",
            "Contact info missing",
            "Your resume has no email or phone number. Recruiters need at least one way to reach you.",
            section="contact_info",
            action_label="Add contact info",
        ))
    else:
        if not ci.email:
            tasks.append(_task(
                "t1_email_missing",
                "Email address missing",
                "No email address detected. Add one so recruiters can contact you.",
                section="contact_info.email",
                action_label="Add email",
            ))
        if not ci.phone:
            tasks.append(_task(
                "t1_phone_missing",
                "Phone number missing",
                "No phone number detected. Many recruiters prefer a phone screen as the first step.",
                section="contact_info.phone",
                action_label="Add phone",
            ))
        if not ci.linkedin:
            tasks.append(_task(
                "t1_linkedin_missing",
                "LinkedIn profile missing",
                "Adding a LinkedIn URL significantly improves recruiter confidence.",
                section="contact_info.linkedin",
                action_label="Add LinkedIn",
            ))

    # ── Summary ─────────────────────────────────────────────────
    if not draft.summary or len(draft.summary.strip()) < 40:
        tasks.append(_task(
            "t1_summary_thin",
            "Summary is missing or too short",
            "A strong 2–3 sentence summary at the top of your resume boosts ATS scores and human readability.",
            section="summary",
            action_label="Edit summary",
        ))

    # ── Work experience ─────────────────────────────────────────
    if not draft.experiences:
        tasks.append(_task(
            "t1_no_experience",
            "No work experience",
            "Your resume contains no work experience entries. Add at least one position.",
            section="experiences",
            action_label="Add experience",
        ))
    else:
        for i, exp in enumerate(draft.experiences):
            empty_bullets = [b for b in exp.bullets if not b.text.strip()]
            if len(exp.bullets) - len(empty_bullets) < 2:
                tasks.append(_task(
                    f"t1_exp_{i}_thin_bullets",
                    f"Thin bullets: {exp.company}",
                    f"'{exp.title} @ {exp.company}' has fewer than 2 bullet points. Add specific achievements.",
                    section=f"experiences[{i}]",
                    action_label="Edit experience",
                ))

    # ── Education ───────────────────────────────────────────────
    if not draft.education:
        tasks.append(_task(
            "t1_no_education",
            "No education entries",
            "Education section is empty. Add your highest qualification.",
            section="education",
            action_label="Add education",
        ))

    # ── Skills ──────────────────────────────────────────────────
    if len(draft.skills) < 3:
        tasks.append(_task(
            "t1_few_skills",
            "Skills section is sparse",
            f"Only {len(draft.skills)} skill(s) listed. ATS systems rely heavily on the skills section for keyword matching.",
            section="skills",
            action_label="Edit skills",
        ))

    return tasks

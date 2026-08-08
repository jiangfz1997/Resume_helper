from pathlib import Path

import yaml


TEMPLATE_PATH = Path(__file__).parents[2] / "infra" / "dashboard-api.yaml"


def _template() -> dict[str, object]:
    return yaml.load(TEMPLATE_PATH.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def test_dashboard_stack_does_not_own_discovery_schedules() -> None:
    resources = _template()["Resources"]

    assert "DiscoverySchedulerRole" not in resources
    assert "WorkdayDiscoverySchedule" not in resources
    assert "JobSpyDiscoverySchedule" not in resources


def test_scoring_schedule_runs_after_discovery() -> None:
    resources = _template()["Resources"]
    properties = resources["PersonalizedScoringFunction"]["Properties"]["Events"]["ScheduledScoring"]["Properties"]

    assert properties["ScheduleExpression"] == "cron(45 10,14,20 * * ? *)"
    assert properties["ScheduleExpressionTimezone"] == "America/Toronto"
    assert properties["Input"] == '{"limit":20}'

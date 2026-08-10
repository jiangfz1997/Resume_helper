import re
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

    assert properties["ScheduleExpression"] == "cron(45 10 * * ? *)"
    assert properties["ScheduleExpressionTimezone"] == "America/Toronto"
    # max_age_days keeps the daily run on fresh postings; without it a profile
    # edit sends it back through weeks of invalidated scores.
    assert properties["Input"] == '{"limit":30,"max_age_days":2}'


def test_template_routes_match_the_handler() -> None:
    """A route implemented in the handler but missing from Events 404s at the
    API Gateway, and one wired in Events with no handler branch falls through
    to 'route not found' -- neither shows up until deploy."""
    handler_source = (Path(__file__).parents[2] / "lambda_dashboard" / "lambda_function.py").read_text(encoding="utf-8")
    handler_routes = set(re.findall(r'route_key == "([^"]+)"', handler_source))

    events = _template()["Resources"]["DashboardReadFunction"]["Properties"]["Events"]
    template_routes = {
        f"{event['Properties']['Method']} {event['Properties']['Path']}"
        for event in events.values()
        if event["Type"] == "HttpApi"
    }

    assert handler_routes == template_routes


def test_bootstrap_route_is_wired() -> None:
    events = _template()["Resources"]["DashboardReadFunction"]["Properties"]["Events"]

    assert events["GetBootstrap"]["Properties"]["Path"] == "/bootstrap"
    assert events["GetBootstrap"]["Properties"]["Method"] == "GET"

from pathlib import Path

import yaml


TEMPLATE_PATH = Path(__file__).parents[2] / "infra" / "dashboard-api.yaml"


def _template() -> dict[str, object]:
    return yaml.load(TEMPLATE_PATH.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def test_discovery_schedules_invoke_existing_crawlers_in_toronto_time() -> None:
    resources = _template()["Resources"]

    expected_targets = {
        "WorkdayDiscoverySchedule": "${WorkdayFunctionName}",
        "JobSpyDiscoverySchedule": "${JobSpyFunctionName}",
    }
    for logical_id, function_parameter in expected_targets.items():
        schedule = resources[logical_id]
        properties = schedule["Properties"]
        target = properties["Target"]

        assert schedule["Type"] == "AWS::Scheduler::Schedule"
        assert properties["ScheduleExpression"] == "cron(0 10,14,20 * * ? *)"
        assert properties["ScheduleExpressionTimezone"] == "America/Toronto"
        assert properties["FlexibleTimeWindow"] == {"Mode": "OFF"}
        assert properties["State"] == "ENABLED"
        assert target["Arn"].endswith(f"function:{function_parameter}")
        assert target["Input"] == "{}"
        assert target["RetryPolicy"] == {
            "MaximumEventAgeInSeconds": "3600",
            "MaximumRetryAttempts": "1",
        }


def test_scoring_schedule_runs_after_discovery() -> None:
    resources = _template()["Resources"]
    properties = resources["PersonalizedScoringFunction"]["Properties"]["Events"]["ScheduledScoring"]["Properties"]

    assert properties["ScheduleExpression"] == "cron(45 10,14,20 * * ? *)"
    assert properties["ScheduleExpressionTimezone"] == "America/Toronto"
    assert properties["Input"] == '{"limit":20}'


def test_scheduler_role_can_only_invoke_configured_crawlers() -> None:
    resources = _template()["Resources"]
    statements = resources["DiscoverySchedulerRole"]["Properties"]["Policies"][0]["PolicyDocument"]["Statement"]

    assert statements == [
        {
            "Effect": "Allow",
            "Action": "lambda:InvokeFunction",
            "Resource": [
                "arn:${AWS::Partition}:lambda:${AWS::Region}:${AWS::AccountId}:function:${WorkdayFunctionName}",
                "arn:${AWS::Partition}:lambda:${AWS::Region}:${AWS::AccountId}:function:${JobSpyFunctionName}",
            ],
        }
    ]

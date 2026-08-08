from pathlib import Path

import yaml


TEMPLATE_PATH = Path(__file__).parents[2] / "infra" / "discovery.yaml"


def _template() -> dict[str, object]:
    return yaml.load(TEMPLATE_PATH.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def test_discovery_stack_owns_retained_scheduler_resources() -> None:
    resources = _template()["Resources"]

    assert set(resources) == {
        "DiscoverySchedulerRole",
        "WorkdayDiscoverySchedule",
        "JobSpyDiscoverySchedule",
    }
    for resource in resources.values():
        assert resource["DeletionPolicy"] == "Retain"
        assert resource["UpdateReplacePolicy"] == "Retain"


def test_discovery_schedules_match_retained_resources() -> None:
    resources = _template()["Resources"]
    expected_targets = {
        "WorkdayDiscoverySchedule": ("job-discovery-workday-managed", "${WorkdayFunctionName}"),
        "JobSpyDiscoverySchedule": ("job-discovery-jobspy-managed", "${JobSpyFunctionName}"),
    }

    for logical_id, (schedule_name, function_parameter) in expected_targets.items():
        properties = resources[logical_id]["Properties"]
        target = properties["Target"]

        assert properties["Name"] == schedule_name
        assert properties["GroupName"] == "default"
        assert properties["ScheduleExpression"] == "cron(0 10,14,20 * * ? *)"
        assert properties["ScheduleExpressionTimezone"] == "America/Toronto"
        assert properties["State"] == "ENABLED"
        assert target["Arn"].endswith(f"function:{function_parameter}")
        assert target["RoleArn"] == "DiscoverySchedulerRole.Arn"
        assert target["Input"] == "{}"


def test_scheduler_role_name_is_supplied_for_import() -> None:
    template = _template()
    role = template["Resources"]["DiscoverySchedulerRole"]

    assert template["Parameters"]["SchedulerRoleName"]["Type"] == "String"
    assert role["Properties"]["RoleName"] == "SchedulerRoleName"


def test_initial_import_template_does_not_declare_outputs() -> None:
    assert "Outputs" not in _template()

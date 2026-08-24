from job_discovery.maintenance.reclassify_years import has_years_change, reclassify_years_item


def test_reclassify_excludes_range_whose_upper_bound_exceeds_cap() -> None:
    item = {
        "description": "Requires 5-8 years of professional experience.",
        "filter_codes": [], "eligibility_status": "eligible", "is_new_grad": False,
    }
    result = reclassify_years_item(item, 5)
    assert (result.minimum, result.maximum) == (5, 8)
    assert result.eligibility_status == "excluded"
    assert result.filter_codes == ["years_too_high"]
    assert has_years_change(item, result) is True


def test_reclassify_removes_stale_years_code_when_requirement_drops() -> None:
    item = {
        "description": "Requires 3 years of professional experience.",
        "required_years_min": 8, "years_mentioned": True,
        "filter_codes": ["years_too_high"], "eligibility_status": "excluded", "is_new_grad": False,
    }
    result = reclassify_years_item(item, 5)
    assert result.minimum == 3
    assert result.filter_codes == []
    assert result.eligibility_status == "eligible"


def test_reclassify_preserves_non_years_filter_codes() -> None:
    item = {
        "description": "No experience requirement is stated.",
        "filter_codes": ["review_title", "years_too_high"],
        "eligibility_status": "excluded", "is_new_grad": False,
    }
    result = reclassify_years_item(item, 5)
    assert result.filter_codes == ["review_title"]
    assert result.eligibility_status == "review"

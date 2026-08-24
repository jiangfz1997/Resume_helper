from __future__ import annotations

from dataclasses import dataclass

from job_discovery.domain.models import EligibilityStatus, FilterCode
from job_discovery.domain.years import extract_years

_EXCLUDING_CODES = {
    FilterCode.LOCATION_MISMATCH.value,
    FilterCode.EXCLUDED_TITLE.value,
    FilterCode.TITLE_NOT_RELEVANT.value,
    FilterCode.YEARS_TOO_HIGH.value,
}
_REVIEW_CODES = {
    FilterCode.REVIEW_TITLE.value,
    FilterCode.DESCRIPTION_TOO_SHORT.value,
    FilterCode.DESCRIPTION_MISSING.value,
    FilterCode.YEARS_UNPARSED.value,
}
_YEARS_CODES = {FilterCode.YEARS_TOO_HIGH.value, FilterCode.YEARS_UNPARSED.value}


@dataclass(frozen=True)
class YearsReclassification:
    minimum: int | None
    maximum: int | None
    mentioned: bool
    filter_codes: list[str]
    eligibility_status: str


def reclassify_years_item(item: dict, max_required_years: int) -> YearsReclassification:
    years = extract_years(item.get("description"))
    codes = [str(code) for code in item.get("filter_codes", []) if str(code) not in _YEARS_CODES]
    effective_years = years.maximum if years.maximum is not None else years.minimum
    if effective_years is not None and effective_years > max_required_years:
        codes.append(FilterCode.YEARS_TOO_HIGH.value)
    elif years.unparsed_mention and not bool(item.get("is_new_grad", False)):
        codes.append(FilterCode.YEARS_UNPARSED.value)

    codes = list(dict.fromkeys(codes))
    if any(code in _EXCLUDING_CODES for code in codes):
        status = EligibilityStatus.EXCLUDED.value
    elif any(code in _REVIEW_CODES for code in codes):
        status = EligibilityStatus.REVIEW.value
    else:
        status = EligibilityStatus.ELIGIBLE.value
    return YearsReclassification(
        minimum=years.minimum,
        maximum=years.maximum,
        mentioned=years.mentioned,
        filter_codes=codes,
        eligibility_status=status,
    )


def has_years_change(item: dict, result: YearsReclassification) -> bool:
    return any((
        _optional_int(item.get("required_years_min")) != result.minimum,
        _optional_int(item.get("required_years_max")) != result.maximum,
        bool(item.get("years_mentioned", False)) != result.mentioned,
        list(item.get("filter_codes", [])) != result.filter_codes,
        item.get("eligibility_status") != result.eligibility_status,
    ))


def _optional_int(value: object) -> int | None:
    return int(value) if value is not None else None

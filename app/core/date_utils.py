from datetime import date


def parse_ym(s: str) -> date:
    """Parse a YYYY-MM or YYYY date string. Returns today for 'present' / unparseable input."""
    s = s.strip().lower()
    if not s or s in ("present", "current", "now"):
        return date.today()
    parts = s.split("-")
    try:
        if len(parts) >= 2:
            return date(int(parts[0]), int(parts[1]), 1)
        return date(int(parts[0]), 1, 1)
    except (ValueError, IndexError):
        return date.today()


def duration_months(start_date: str, end_date: str | None) -> float:
    """Return the number of months between start_date and end_date (or today)."""
    try:
        start = parse_ym(start_date or "")
        end = parse_ym(end_date or "present")
        days = (end - start).days
        return max(days / 30.44, 0.0)
    except Exception:
        return 0.0

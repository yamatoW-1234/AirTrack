"""Input checks. Every function raises ApiError(400) on bad input, so routes stay short."""
import re
from datetime import date

from config import Config
from errors import ApiError

_DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


def parse_date(value, name="date"):
    """'YYYY-MM-DD' -> date. Missing/empty -> None (caller decides the default)."""
    if value is None or value == "":
        return None
    if not _DATE_RE.fullmatch(value):
        raise ApiError(f"{name} must be in YYYY-MM-DD format", 400)
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ApiError(f"{name} is not a real calendar date", 400)


def parse_int(value, name, minimum=None, maximum=None, default=None):
    if value is None or value == "":
        return default
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ApiError(f"{name} must be an integer", 400)
    if minimum is not None and number < minimum:
        raise ApiError(f"{name} must be at least {minimum}", 400)
    if maximum is not None and number > maximum:
        raise ApiError(f"{name} must be at most {maximum}", 400)
    return number


def parse_paging(args):
    """limit (default 100, max 500) and offset (default 0) from request.args."""
    limit = parse_int(args.get("limit"), "limit", 1, Config.MAX_LIMIT, Config.DEFAULT_LIMIT)
    offset = parse_int(args.get("offset"), "offset", 0, None, 0)
    return limit, offset


def parse_choice(value, name, allowed, default=None):
    """value must be one of `allowed` (e.g. period in daily/monthly)."""
    if value is None or value == "":
        return default
    if value not in allowed:
        raise ApiError(f"{name} must be one of: {', '.join(allowed)}", 400)
    return value


def check_range(start, end, start_name="from", end_name="to"):
    if start and end and start > end:
        raise ApiError(f"{start_name} must not be after {end_name}", 400)

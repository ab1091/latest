"""
Shared "what day/time is it for the customer" helper.

Every lead-facing day/time resolution (SMS "today"/"tomorrow"/weekday
references, the Vapi voice-call date lookup table, quiet-hours checks) needs
to reason in the business's local time, not the server's UTC clock — a
caller texting "call me at 5pm" at 11pm UTC means 5pm Central, not 5pm UTC.
Centralized here so every call site anchors on the same timezone instead of
each file picking its own default.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

# Matches the businesses.timezone / communication_rules.timezone default —
# used whenever a business hasn't explicitly configured its own timezone.
BUSINESS_TIMEZONE = "America/Chicago"


def now_local(tz_name: str = BUSINESS_TIMEZONE) -> datetime:
    """
    Current wall-clock time in the given timezone, returned as a NAIVE
    datetime (tzinfo stripped) — matches how appointments.start_time and
    every other "local time" column in this codebase is stored: the number
    everyone reads/writes is the local wall-clock number, just without a
    tzinfo attached. Keeping it naive here means it drops straight into the
    existing naive-datetime arithmetic (strftime, weekday(), timedelta
    comparisons) without every call site needing its own tz-stripping step.
    """
    return datetime.now(ZoneInfo(tz_name)).replace(tzinfo=None)


def local_to_utc(naive_local: datetime, tz_name: str = BUSINESS_TIMEZONE) -> datetime:
    """
    Convert a naive local wall-clock datetime (e.g. "the customer said 3pm
    Central") into a naive UTC instant, for the few places that actually
    compare a scheduled time against a true UTC clock (e.g.
    scheduled_callbacks.scheduled_at, checked against Postgres NOW()).
    Naive in, naive out — the input has no tzinfo (it's a local wall-clock
    reading), the output has no tzinfo either (it's a UTC instant, matching
    the `timestamp without time zone` column convention used everywhere
    else in this schema).
    """
    return naive_local.replace(tzinfo=ZoneInfo(tz_name)).astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

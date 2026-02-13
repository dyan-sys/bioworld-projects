"""
Google Calendar Event Reader

Fetches and normalizes calendar events for a given day.
Handles all-day events vs timed events, multiple calendars, and SGT timezone.
"""

from datetime import datetime, timedelta, timezone

SGT = timezone(timedelta(hours=8))


def fetch_todays_events(
    service: object,
    calendar_ids: list[str] | None = None,
    target_date: datetime | None = None,
) -> list[dict]:
    """
    Fetch all events for a given day across one or more calendars.

    Args:
        service: Authenticated Google Calendar API service.
        calendar_ids: List of calendar IDs to query. Defaults to ["primary"].
        target_date: Date to fetch events for (SGT). Defaults to today.

    Returns:
        Sorted list of event dicts:
            {title, start, end, location, is_all_day}
        where start/end are datetime objects (SGT) for timed events,
        or date strings "YYYY-MM-DD" for all-day events.
    """
    if calendar_ids is None:
        calendar_ids = ["primary"]

    if target_date is None:
        target_date = datetime.now(SGT)

    # Build time bounds: 00:00 - 24:00 SGT
    day_start = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)

    time_min = day_start.isoformat()
    time_max = day_end.isoformat()

    all_events = []

    for cal_id in calendar_ids:
        events_result = (
            service.events()
            .list(
                calendarId=cal_id,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )

        for event in events_result.get("items", []):
            # Skip cancelled events
            if event.get("status") == "cancelled":
                continue

            parsed = _parse_event(event)
            if parsed:
                all_events.append(parsed)

    # Sort: all-day events first, then by start time
    all_events.sort(key=_sort_key)

    return all_events


def _parse_event(event: dict) -> dict | None:
    """Parse a single Google Calendar event into our normalized format."""
    title = event.get("summary", "(No title)")
    location = event.get("location", "")

    start_raw = event.get("start", {})
    end_raw = event.get("end", {})

    if "date" in start_raw:
        # All-day event
        return {
            "title": title,
            "start": start_raw["date"],
            "end": end_raw.get("date", start_raw["date"]),
            "location": location,
            "is_all_day": True,
        }
    elif "dateTime" in start_raw:
        # Timed event
        start_dt = datetime.fromisoformat(start_raw["dateTime"]).astimezone(SGT)
        end_dt = datetime.fromisoformat(end_raw["dateTime"]).astimezone(SGT)
        return {
            "title": title,
            "start": start_dt,
            "end": end_dt,
            "location": location,
            "is_all_day": False,
        }

    return None


def _sort_key(event: dict) -> tuple:
    """Sort key: all-day events first (0), then by start time (1, timestamp)."""
    if event["is_all_day"]:
        return (0, event["start"])
    return (1, event["start"].isoformat())


def compute_free_blocks(
    events: list[dict],
    work_start: int = 9,
    work_end: int = 18,
    target_date: datetime | None = None,
) -> list[tuple[str, str]]:
    """
    Compute free time blocks within work hours by subtracting busy intervals.

    Args:
        events: List of event dicts from fetch_todays_events.
        work_start: Work day start hour (default 9).
        work_end: Work day end hour (default 18).
        target_date: Reference date for building work-hour bounds. Defaults to today SGT.

    Returns:
        List of (start_str, end_str) tuples like [("11:30", "14:00"), ("15:00", "18:00")].
        The last block uses "onwards" instead of end time if it extends to work_end.
    """
    if target_date is None:
        target_date = datetime.now(SGT)

    day_base = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
    ws = day_base.replace(hour=work_start)
    we = day_base.replace(hour=work_end)

    # Collect busy intervals (only timed events)
    busy = []
    for ev in events:
        if ev["is_all_day"]:
            continue
        start = max(ev["start"], ws)
        end = min(ev["end"], we)
        if start < end:
            busy.append((start, end))

    if not busy:
        return [(_fmt_time(ws), "onwards")]

    # Sort and merge overlapping intervals
    busy.sort()
    merged = [busy[0]]
    for start, end in busy[1:]:
        prev_start, prev_end = merged[-1]
        if start <= prev_end:
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))

    # Compute gaps
    free = []
    cursor = ws

    for busy_start, busy_end in merged:
        if cursor < busy_start:
            free.append((cursor, busy_start))
        cursor = max(cursor, busy_end)

    if cursor < we:
        free.append((cursor, we))

    # Format
    result = []
    for start, end in free:
        start_str = _fmt_time(start)
        if end == we:
            result.append((start_str, "onwards"))
        else:
            result.append((start_str, _fmt_time(end)))

    return result


def _fmt_time(dt: datetime) -> str:
    """Format datetime as HH:MM."""
    return dt.strftime("%H:%M")

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from gcal import list_events
from settings import load as load_settings

TZ = ZoneInfo("Asia/Kuala_Lumpur")
CLASS_RE = re.compile(r"^(LC|C) [A-Z]{2}\d{3}|\b(Lecture|Tutorial|Lab)\b", re.I)
QUIET_FROM, QUIET_TO = 23, 6   # no reminders from 11 PM to 6 AM

reminded = set()


def clock(dt):
    return dt.strftime("%I:%M %p").lstrip("0")


def due_reminders():
    cfg = load_settings()
    lead_class, lead_other = cfg["lead_class"], cfg["lead_other"]
    now = datetime.now(TZ)
    if now.hour >= QUIET_FROM or now.hour < QUIET_TO:
        return None
    events = list_events(now.isoformat(), (now + timedelta(minutes=max(lead_class, lead_other) + 5)).isoformat())
    due = []
    for e in events:
        s = e["start"].get("dateTime")
        if not s:
            continue  # skip all-day events
        st = datetime.fromisoformat(s).astimezone(TZ)
        mins = (st - now).total_seconds() / 60
        if mins <= 0:
            continue  # already started
        lead = lead_class if CLASS_RE.search(e.get("summary", "")) else lead_other
        key = f"{e['id']}|{s}"
        if mins <= lead and key not in reminded:
            reminded.add(key)
            due.append((st, e, round(mins)))
    if len(reminded) > 500:
        reminded.clear()
    if not due:
        return None
    due.sort(key=lambda x: x[0])
    lines = []
    for st, e, mins in due:
        line = f"• {clock(st)}: {e.get('summary', '(no title)')} (in {mins} min)"
        if e.get("location"):
            line += f" @ {e['location']}"
        if e.get("description"):
            line += f"\n   📝 {e['description'][:150]}"
        lines.append(line)
    return "Heads up 👀\n" + "\n".join(lines)
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from gcal import list_events

TZ = ZoneInfo("Asia/Kuala_Lumpur")

def clock(dt):
    return dt.strftime("%I:%M %p").lstrip("0")

def morning_brief(offset):
    now = datetime.now(TZ) + timedelta(days=offset)
    day = "today" if offset == 0 else now.strftime("%A")
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    events = list_events(start.isoformat(), end.isoformat())

    header = f"{'Morning ☀️' if offset == 0 else 'Heads up 👀'} {now.strftime('%a %d %b')}"
    if not events:
        return header + f"\nNothing on {day}, free day 🙌"
    
    lines = []
    for e in events:
        s = e["start"].get("dateTime")
        if s:
            st = datetime.fromisoformat(s).astimezone(TZ)
            en = datetime.fromisoformat(e["end"]["dateTime"]).astimezone(TZ)
            when = f"{clock(st)} – {clock(en)}"
        else:
            when = "All day"
        line = f"• {when}: {e.get('summary', '(no title)')}"
        if e.get("location"):
            line += f" @ {e['location']}"
        lines.append(line)

    return header + "\n" + "\n".join(lines) + f"\n\n{len(events)} things {day}."

import re
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from gcal import list_events, delete_event

# matches course-code titles like "C IT6114 DATABASE FUNDAMENTALS (Lecture)"
PATTERN = re.compile(r"^(LC|C) [A-Z]{2}\d{3}[A-Z0-9]")

now = datetime.now(ZoneInfo("Asia/Kuala_Lumpur"))
start = now.isoformat()
end = (now + timedelta(days=120)).isoformat()

events = [e for e in list_events(start, end) if PATTERN.match(e.get("summary", ""))]
print(f"Found {len(events)} matching events:")
for e in events[:10]:
    print(" -", e["start"].get("dateTime", e["start"].get("date")), e["summary"])
if len(events) > 10:
    print(f"   ...and {len(events) - 10} more")

if events and input("Delete all of these? (y/n): ").strip().lower() == "y":
    for e in events:
        delete_event(e["id"])
        time.sleep(0.2)
    print("Done.")
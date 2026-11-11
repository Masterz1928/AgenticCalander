import json
from pathlib import Path

FILE = Path(__file__).parent / "settings.json"
DEFAULTS = {"brief_hour": 7, "brief_min": 30, "lead_class": 30, "lead_other": 60}


def load():
    try:
        data = json.loads(FILE.read_text())
    except Exception:
        data = {}
    return {**DEFAULTS, **data}


def save(s):
    FILE.write_text(json.dumps(s))


def time_label(h, m):
    suffix = "AM" if h < 12 else "PM"
    return f"{(h % 12) or 12}:{m:02d} {suffix}"
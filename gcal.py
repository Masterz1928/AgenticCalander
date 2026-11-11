import os.path
import threading
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
TZ = "Asia/Kuala_Lumpur"


def _build_service():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as f:
            f.write(creds.to_json())
    return build("calendar", "v3", credentials=creds)


_local = threading.local()


def get_service():
    if not hasattr(_local, "service"):
        _local.service = _build_service()
    return _local.service

def create_event(title, start, end, location=None, description=None, recurrence=None):
    """start/end like '2026-10-27T10:00:00'. recurrence like 'RRULE:FREQ=WEEKLY;COUNT=14'."""
    event = {
        "summary": title,
        "start": {"dateTime": start, "timeZone": TZ},
        "end": {"dateTime": end, "timeZone": TZ},
    }
    if location:
        event["location"] = location
    if description:
        event["description"] = description
    if recurrence:
        event["recurrence"] = [recurrence]
    return get_service().events().insert(calendarId="primary", body=event).execute()

def update_event(event_id, title=None, start=None, end=None, location=None, description=None):
    body = {}
    if title:
        body["summary"] = title
    if start:
        body["start"] = {"dateTime": start, "timeZone": TZ}
    if end:
        body["end"] = {"dateTime": end, "timeZone": TZ}
    if location:
        body["location"] = location
    if description:
        body["description"] = description
    return get_service().events().patch(
        calendarId="primary", eventId=event_id, body=body
    ).execute()


def delete_event(event_id):
    get_service().events().delete(calendarId="primary", eventId=event_id).execute()

def get_event(event_id):
    return get_service().events().get(calendarId="primary", eventId=event_id).execute()

def list_events(time_min, time_max):
    """time_min/max need a timezone offset, like '2026-10-24T00:00:00+08:00'."""
    result = get_service().events().list(
        calendarId="primary",
        timeMin=time_min,
        timeMax=time_max,
        singleEvents=True,
        orderBy="startTime",
        maxResults=2500,
    ).execute()
    return result.get("items", [])


if __name__ == "__main__":
    # quick test, we'll delete this later
    ev = create_event(
        "DB class",
        "2026-10-27T10:00:00",
        "2026-10-27T12:00:00",
        location="CQCR3001",
        description="Bring laptop",
        recurrence="RRULE:FREQ=WEEKLY;COUNT=3",
    )
    print("Created:", ev["htmlLink"])

    for e in list_events("2026-10-24T00:00:00+08:00", "2026-11-30T00:00:00+08:00"):
        print(e["start"].get("dateTime"), "-", e["summary"])
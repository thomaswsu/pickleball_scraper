"""API endpoint tests using FastAPI's TestClient."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.config import get_settings
from app.models import AvailabilitySlot

settings = get_settings()


def test_locations_endpoint_returns_slots(client, db_session, sample_location):
    tz = ZoneInfo("America/Los_Angeles")
    slot_time = (datetime.now(tz) + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    slot = AvailabilitySlot(
        location_id=sample_location.id,
        court_id="court-1",
        court_name="Court 1",
        sport_id=settings.pickleball_sport_id,
        duration_minutes=90,
        slot_time_local=slot_time,
        slot_time_utc=slot_time.astimezone(ZoneInfo("UTC")),
    )
    db_session.add(slot)
    db_session.commit()

    response = client.get("/api/locations")
    payload = response.json()

    assert response.status_code == 200
    assert payload["locations"][0]["name"] == sample_location.name
    assert payload["locations"][0]["slots"][0]["court_id"] == "court-1"
    assert payload["locations"][0]["slots"][0]["duration_minutes"] == 90
    assert payload["locations"][0]["slots"][0]["court_count"] == 1


def test_locations_endpoint_dedupes_matching_times(client, db_session, sample_location):
    tz = ZoneInfo("America/Los_Angeles")
    slot_time = datetime(2025, 10, 27, 9, 0, tzinfo=tz)
    slots = [
        AvailabilitySlot(
            location_id=sample_location.id,
            court_id="court-1",
            court_name="Court A",
            sport_id=settings.pickleball_sport_id,
            duration_minutes=90,
            slot_time_local=slot_time,
            slot_time_utc=slot_time.astimezone(ZoneInfo("UTC")),
        ),
        AvailabilitySlot(
            location_id=sample_location.id,
            court_id="court-2",
            court_name="Court B",
            sport_id=settings.pickleball_sport_id,
            duration_minutes=90,
            slot_time_local=slot_time,
            slot_time_utc=slot_time.astimezone(ZoneInfo("UTC")),
        ),
    ]
    db_session.add_all(slots)
    db_session.commit()

    payload = client.get("/api/locations").json()
    slot_payload = payload["locations"][0]["slots"]
    assert len(slot_payload) == 1
    data = slot_payload[0]
    assert data["court_count"] == 2
    assert sorted(data["court_names"]) == ["Court A", "Court B"]


def test_locations_endpoint_filters_non_pickleball(client, db_session, sample_location):
    tz = ZoneInfo("America/Los_Angeles")
    slot_time = datetime(2025, 10, 27, 9, 0, tzinfo=tz)
    slot = AvailabilitySlot(
        location_id=sample_location.id,
        court_id="court-3",
        court_name="Court C",
        sport_id="not-pickleball",
        duration_minutes=60,
        slot_time_local=slot_time,
        slot_time_utc=slot_time.astimezone(ZoneInfo("UTC")),
    )
    db_session.add(slot)
    db_session.commit()

    payload = client.get("/api/locations").json()
    assert payload["locations"][0]["slots"] == []


def test_locations_endpoint_filters_by_court_query(client, db_session, sample_location):
    tz = ZoneInfo("America/Los_Angeles")
    slot_time = datetime(2025, 10, 27, 9, 0, tzinfo=tz)
    slots = [
        AvailabilitySlot(
            location_id=sample_location.id,
            court_id="court-1",
            court_name="Sunrise Court",
            sport_id=settings.pickleball_sport_id,
            duration_minutes=60,
            slot_time_local=slot_time,
            slot_time_utc=slot_time.astimezone(ZoneInfo("UTC")),
        ),
        AvailabilitySlot(
            location_id=sample_location.id,
            court_id="court-2",
            court_name="Evening Court",
            sport_id=settings.pickleball_sport_id,
            duration_minutes=60,
            slot_time_local=slot_time,
            slot_time_utc=slot_time.astimezone(ZoneInfo("UTC")),
        ),
    ]
    db_session.add_all(slots)
    db_session.commit()

    payload = client.get("/api/locations?court=Sunrise").json()
    slot_payload = payload["locations"][0]["slots"]
    assert len(slot_payload) == 1
    assert slot_payload[0]["court_count"] == 1
    assert slot_payload[0]["court_names"] == ["Sunrise Court"]


def test_watch_crud_flow(client, sample_location):
    watch_payload = {
        "location_id": sample_location.id,
        "label": "Morning crew",
        "court_query": "Court 1",
        "contact": "crew@example.com",
        "notes": "bring balls",
    }

    create_resp = client.post("/api/watchers", json=watch_payload)
    assert create_resp.status_code == 200
    watch_id = create_resp.json()["id"]

    list_resp = client.get("/api/watchers")
    assert list_resp.status_code == 200
    assert list_resp.json()[0]["label"] == "Morning crew"
    assert list_resp.json()[0]["contact"] == "crew@example.com"

    toggle_resp = client.post(f"/api/watchers/{watch_id}/toggle")
    assert toggle_resp.status_code == 200
    assert toggle_resp.json()["active"] is False

    delete_resp = client.delete(f"/api/watchers/{watch_id}")
    assert delete_resp.status_code == 200
    assert delete_resp.json()["status"] == "deleted"

    assert client.get("/api/watchers").json() == []


def test_create_watch_fails_for_unknown_location(client):
    response = client.post(
        "/api/watchers",
        json={"location_id": "missing", "label": "bad"},
    )
    assert response.status_code == 404

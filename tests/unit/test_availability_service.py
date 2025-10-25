"""Unit tests for availability synchronization logic."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.availability_service import (
    SlotRecord,
    create_alerts,
    match_watch,
    sync_availability,
)
from app.models import AvailabilitySlot, Location, WatchRule


def sample_payload(slot_time: str) -> list[dict]:
    return [
        {
            "location": {
                "id": "loc-123",
                "name": "Mission Dolores Courts",
                "formattedAddress": "19th & Dolores St, San Francisco",
                "timezone": "America/Los_Angeles",
                "images": {"thumbnail": "https://example.com/thumb.jpg"},
                "courts": [
                    {
                        "id": "court-1",
                        "name": "Court 1",
                        "availableSlots": [slot_time],
                        "sports": [{"id": "bd745b6e-1dd6-43e2-a69f-06f094808a96", "sportId": "bd745b6e-1dd6-43e2-a69f-06f094808a96"}],
                    }
                ],
            }
        }
    ]


def test_sync_availability_creates_and_removes_slots(db_session):
    payload = sample_payload("2025-10-27 09:00:00")

    new_slots = sync_availability(db_session, payload)
    db_session.commit()

    assert len(new_slots) == 1
    assert db_session.query(AvailabilitySlot).count() == 1

    # Re-running with same payload should not duplicate entries
    new_slots = sync_availability(db_session, payload)
    db_session.commit()
    assert len(new_slots) == 0
    assert db_session.query(AvailabilitySlot).count() == 1

    # Removing slots should clear the table
    payload[0]["location"]["courts"][0]["availableSlots"] = []
    sync_availability(db_session, payload)
    db_session.commit()
    assert db_session.query(AvailabilitySlot).count() == 0


def test_create_alerts_emits_when_watch_matches(db_session):
    location = Location(
        id="loc-123",
        name="Mission Dolores Courts",
        address="19th & Dolores St",
        timezone="America/Los_Angeles",
    )
    db_session.add(location)
    db_session.commit()

    watch = WatchRule(
        location_id=location.id,
        label="Morning session",
        court_query="Court 1",
        active=True,
    )
    db_session.add(watch)
    db_session.commit()

    tz = ZoneInfo("America/Los_Angeles")
    slot_local = datetime(2025, 10, 27, 9, 0, tzinfo=tz)
    slot = SlotRecord(
        location_id=location.id,
        location_name=location.name,
        location_address=location.address,
        image_url=None,
        timezone=str(tz),
        court_id="court-1",
        court_name="Court 1",
        sport_id="sport-1",
        slot_time_local=slot_local,
        slot_time_utc=slot_local.astimezone(ZoneInfo("UTC")),
        duration_minutes=90,
    )

    alerts = create_alerts(db_session, [slot])
    db_session.commit()

    assert len(alerts) == 1
    assert alerts[0].watch_id == watch.id
    assert alerts[0].court_id == "court-1"


def test_match_watch_respects_filters(db_session):
    watch = WatchRule(
        location_id="loc-123",
        label="Evening",
        court_query="Court 2",
        target_date=datetime(2025, 10, 27).date(),
        time_from=datetime(2025, 10, 27, 17, 0).time(),
        time_to=datetime(2025, 10, 27, 19, 0).time(),
        active=True,
    )

    tz = ZoneInfo("America/Los_Angeles")
    good_slot = SlotRecord(
        location_id="loc-123",
        location_name="Loc",
        location_address="",
        image_url=None,
        timezone=str(tz),
        court_id="court-2",
        court_name="Court 2",
        sport_id=None,
        slot_time_local=datetime(2025, 10, 27, 18, 0, tzinfo=tz),
        slot_time_utc=datetime(2025, 10, 27, 18, 0, tzinfo=tz).astimezone(ZoneInfo("UTC")),
        duration_minutes=90,
    )

    bad_slot = SlotRecord(
        location_id="loc-123",
        location_name="Loc",
        location_address="",
        image_url=None,
        timezone=str(tz),
        court_id="court-1",
        court_name="Court 1",
        sport_id=None,
        slot_time_local=datetime(2025, 10, 27, 12, 0, tzinfo=tz),
        slot_time_utc=datetime(2025, 10, 27, 12, 0, tzinfo=tz).astimezone(ZoneInfo("UTC")),
        duration_minutes=90,
    )

    assert match_watch(good_slot, watch) is True
    assert match_watch(bad_slot, watch) is False

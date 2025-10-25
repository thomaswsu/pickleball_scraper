"""FastAPI entrypoint and API surface for the pickleball scraper."""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from datetime import date, datetime, time
from collections import defaultdict
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session

from .availability_service import create_alerts, sync_availability, update_status
from .config import get_settings
from .db import Base, SessionLocal, engine, ensure_schema, get_session
from .models import Alert, AvailabilitySlot, Location, SystemStatus, WatchRule
from .rec_client import RecClient
from .schemas import (
    AlertResponse,
    LocationAvailabilityResponse,
    LocationsEnvelope,
    SlotResponse,
    StatusResponse,
    WatchRuleCreate,
    WatchRuleResponse,
)

settings = get_settings()
logger = logging.getLogger("pickleball_scraper")

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

app = FastAPI(title="Pickleball Court Watcher", version="1.0.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
DEFAULT_DURATION_MINUTES = 60


def _ensure_timezone(value: datetime | None, tz_name: str | None) -> datetime | None:
    """Attach timezone info to naive datetimes."""
    if value is None:
        return None
    if value.tzinfo is not None:
        return value
    tz = ZoneInfo(tz_name or settings.timezone)
    return value.replace(tzinfo=tz)


def _slot_to_response(
    slot: AvailabilitySlot,
    tz_name: str | None,
    *,
    court_count: int | None = None,
    court_names: list[str] | None = None,
) -> SlotResponse:
    """Convert a slot ORM object into the API response model."""
    duration = slot.duration_minutes or DEFAULT_DURATION_MINUTES
    return SlotResponse(
        court_id=slot.court_id,
        court_name=slot.court_name,
        sport_id=slot.sport_id,
        duration_minutes=duration,
        slot_time_local=_ensure_timezone(slot.slot_time_local, tz_name),
        slot_time_utc=_ensure_timezone(slot.slot_time_utc, "UTC"),
        court_count=court_count or 1,
        court_names=court_names or ([slot.court_name] if slot.court_name else None),
    )


def _watch_to_response(watch: WatchRule) -> WatchRuleResponse:
    """Convert a watch ORM object into the API response model."""
    location_name = watch.location.name if watch.location else watch.location_id
    trigger_count = watch.trigger_count or 0
    return WatchRuleResponse(
        id=watch.id,
        location_id=watch.location_id,
        location_name=location_name,
        label=watch.label,
        court_query=watch.court_query,
        target_date=watch.target_date,
        time_from=watch.time_from,
        time_to=watch.time_to,
        contact=watch.contact,
        notes=watch.notes,
        active=watch.active,
        trigger_count=trigger_count,
        created_at=watch.created_at,
        last_triggered_at=watch.last_triggered_at,
    )


def _alert_to_response(alert: Alert) -> AlertResponse:
    """Convert an alert row into its API representation."""
    location_tz = alert.location.timezone if alert.location else settings.timezone
    return AlertResponse(
        id=alert.id,
        watch_id=alert.watch_id,
        location_id=alert.location_id,
        court_id=alert.court_id,
        court_name=alert.court_name,
        slot_time_local=_ensure_timezone(alert.slot_time_local, location_tz),
        slot_time_utc=_ensure_timezone(alert.slot_time_utc, "UTC"),
        created_at=_ensure_timezone(alert.created_at, "UTC"),
        watch_label=alert.watch.label if alert.watch else None,
    )


async def _run_scrape_cycle(client: RecClient) -> None:
    """Fetch availability from Rec, persist changes, and fire alerts."""
    with SessionLocal() as db:
        try:
            payload = await client.fetch_locations()
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to fetch Rec availability: %s", exc)
            db.rollback()
            update_status(db, error=str(exc))
            db.commit()
            return

        try:
            new_slots = sync_availability(db, payload)
            create_alerts(db, new_slots)
            update_status(db)
            db.commit()
            logger.info("Synced %s new slots", len(new_slots))
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to persist availability: %s", exc)
            db.rollback()
            update_status(db, error=str(exc))
            db.commit()


async def _scraper_worker() -> None:
    """Background loop that keeps the database in sync."""
    client = RecClient()
    interval = max(15, int(settings.scrape_interval_seconds))
    try:
        while True:
            await _run_scrape_cycle(client)
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        raise
    finally:
        await client.close()


@app.on_event("startup")
async def on_startup() -> None:
    """Create schema and launch the scraper if enabled."""
    Base.metadata.create_all(bind=engine)
    ensure_schema()
    app.state.scraper_task = None
    if settings.scraper_enabled:
        app.state.scraper_task = asyncio.create_task(_scraper_worker())


@app.on_event("shutdown")
async def on_shutdown() -> None:
    """Stop the background scraper cleanly."""
    task: asyncio.Task | None = getattr(app.state, "scraper_task", None)
    if task:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request) -> HTMLResponse:
    """Serve the dashboard shell."""
    return templates.TemplateResponse("index.html", {"request": request})


def _filter_slots(
    slots: Iterable[AvailabilitySlot],
    *,
    day: date | None,
    time_from: time | None,
    time_to: time | None,
    sport_filter: str | None,
    court_query: str | None,
) -> list[AvailabilitySlot]:
    """Apply date/time filters to a list of slots."""
    filtered: list[AvailabilitySlot] = []
    normalized_court_query = court_query.lower() if court_query else None
    for slot in slots:
        stamp = slot.slot_time_local
        if stamp is None:
            continue
        if sport_filter and slot.sport_id != sport_filter:
            continue
        if normalized_court_query:
            name = (slot.court_name or slot.court_id or "").lower()
            if normalized_court_query not in name:
                continue
        if day and stamp.date() != day:
            continue
        slot_time = stamp.time()
        if time_from and slot_time < time_from:
            continue
        if time_to and slot_time > time_to:
            continue
        filtered.append(slot)
    return filtered


def _dedupe_slots(
    slots: Iterable[AvailabilitySlot],
    tz_name: str | None,
) -> list[SlotResponse]:
    """Collapse slots to unique times while tracking court counts."""
    grouped: dict[datetime, list[AvailabilitySlot]] = defaultdict(list)
    for slot in slots:
        stamp = slot.slot_time_local
        if not stamp:
            continue
        canonical = stamp.replace(tzinfo=None)
        grouped[canonical].append(slot)

    responses: list[SlotResponse] = []
    for stamp, items in sorted(grouped.items(), key=lambda entry: entry[0]):
        ordered = sorted(
            items,
            key=lambda s: (s.court_name or s.court_id or ""),
        )
        names = [
            name
            for name in [(slot.court_name or slot.court_id) for slot in ordered]
            if name
        ]
        response = _slot_to_response(
            ordered[0],
            tz_name,
            court_count=len(ordered),
            court_names=names or None,
        )
        if len(names) > 1:
            response.court_name = f"{names[0]} (+{len(names) - 1} more)"
        responses.append(response)
    return responses


@app.get("/api/locations", response_model=LocationsEnvelope)
def api_locations(
    date_filter: date | None = Query(None, alias="date"),
    time_from: time | None = Query(None, alias="time_from"),
    time_to: time | None = Query(None, alias="time_to"),
    court_query: str | None = Query(None, alias="court"),
    db: Session = Depends(get_session),
) -> LocationsEnvelope:
    """Return current availability grouped by location."""
    locations = db.query(Location).order_by(Location.name.asc()).all()

    payload: list[LocationAvailabilityResponse] = []
    target_sport_id = settings.pickleball_sport_id
    normalized_court_query = court_query.strip() if court_query else None
    for location in locations:
        ordered_slots = sorted(
            (slot for slot in location.slots if slot.slot_time_local is not None),
            key=lambda slot: slot.slot_time_local,
        )
        filtered_slots = _filter_slots(
            ordered_slots,
            day=date_filter,
            time_from=time_from,
            time_to=time_to,
            sport_filter=target_sport_id,
            court_query=normalized_court_query,
        )
        deduped_slots = _dedupe_slots(filtered_slots, location.timezone)
        payload.append(
            LocationAvailabilityResponse(
                id=location.id,
                name=location.name,
                address=location.address,
                image_url=location.image_url,
                slots=deduped_slots,
            )
        )

    status = db.get(SystemStatus, 1)
    last_updated = status.last_successful_sync if status else None
    if not last_updated:
        last_fetch = db.query(func.max(AvailabilitySlot.fetched_at)).scalar()
        last_updated = last_fetch

    return LocationsEnvelope(last_updated=last_updated, locations=payload)


@app.get("/api/watchers", response_model=list[WatchRuleResponse])
def list_watchers(db: Session = Depends(get_session)) -> list[WatchRuleResponse]:
    """List saved alert rules."""
    watches = (
        db.query(WatchRule)
        .order_by(WatchRule.created_at.desc())
        .all()
    )
    return [_watch_to_response(watch) for watch in watches]


@app.post("/api/watchers", response_model=WatchRuleResponse)
def create_watch(
    payload: WatchRuleCreate,
    db: Session = Depends(get_session),
) -> WatchRuleResponse:
    """Create a new alert rule."""
    location = db.get(Location, payload.location_id)
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")

    watch = WatchRule(
        location_id=payload.location_id,
        label=payload.label,
        court_query=payload.court_query,
        target_date=payload.target_date,
        time_from=payload.time_from,
        time_to=payload.time_to,
        contact=payload.contact,
        notes=payload.notes,
        active=True,
    )
    db.add(watch)
    db.commit()
    db.refresh(watch)
    return _watch_to_response(watch)


@app.post("/api/watchers/{watch_id}/toggle", response_model=WatchRuleResponse)
def toggle_watch(
    watch_id: int,
    db: Session = Depends(get_session),
) -> WatchRuleResponse:
    """Toggle a watch between active/paused."""
    watch = db.get(WatchRule, watch_id)
    if not watch:
        raise HTTPException(status_code=404, detail="Watch not found")
    watch.active = not bool(watch.active)
    db.add(watch)
    db.commit()
    db.refresh(watch)
    return _watch_to_response(watch)


@app.delete("/api/watchers/{watch_id}")
def delete_watch(watch_id: int, db: Session = Depends(get_session)) -> dict[str, str]:
    """Remove a saved watch rule."""
    watch = db.get(WatchRule, watch_id)
    if not watch:
        raise HTTPException(status_code=404, detail="Watch not found")
    db.delete(watch)
    db.commit()
    return {"status": "deleted"}


@app.get("/api/alerts", response_model=list[AlertResponse])
def list_alerts(
    limit: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_session),
) -> list[AlertResponse]:
    """Return most recent alert firings."""
    alerts = (
        db.query(Alert)
        .order_by(Alert.created_at.desc())
        .limit(limit)
        .all()
    )
    return [_alert_to_response(alert) for alert in alerts]


@app.get("/api/status", response_model=StatusResponse)
def status(db: Session = Depends(get_session)) -> StatusResponse:
    """Return scraper heartbeat information."""
    record = db.get(SystemStatus, 1)
    if not record:
        return StatusResponse()
    return StatusResponse(
        last_successful_sync=record.last_successful_sync,
        last_error=record.last_error,
        last_error_at=record.last_error_at,
    )

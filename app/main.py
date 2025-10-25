"""FastAPI entrypoint for the pickleball scraper web app."""

from __future__ import annotations

import asyncio
import logging
from typing import List

from fastapi import Depends, FastAPI, HTTPException, Path, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from .availability_service import create_alerts, sync_availability, update_status
from .config import get_settings
from .db import Base, SessionLocal, engine, get_session, ensure_schema
from .models import Alert, AvailabilitySlot, Location, SystemStatus, WatchRule
from .rec_client import RecClient
from .schemas import (
    AlertResponse,
    LocationsEnvelope,
    SlotResponse,
    StatusResponse,
    WatchRuleCreate,
    WatchRuleResponse,
    LocationAvailabilityResponse,
)

logger = logging.getLogger("pickleball_scraper")
logging.basicConfig(level=logging.INFO)

settings = get_settings()
Base.metadata.create_all(bind=engine)
ensure_schema()

app = FastAPI(title="SF Pickleball Availability")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

rec_client = RecClient()
scrape_task: asyncio.Task | None = None


def watch_to_schema(watch: WatchRule) -> WatchRuleResponse:
    """Convert model to schema."""
    return WatchRuleResponse(
        id=watch.id,
        location_id=watch.location_id,
        location_name=watch.location.name if watch.location else watch.location_id,
        label=watch.label,
        court_query=watch.court_query,
        target_date=watch.target_date,
        time_from=watch.time_from,
        time_to=watch.time_to,
        contact=watch.contact,
        notes=watch.notes,
        active=watch.active,
        trigger_count=watch.trigger_count,
        created_at=watch.created_at,
        last_triggered_at=watch.last_triggered_at,
    )


async def poll_once() -> None:
    """Fetch the latest availability and persist it."""
    try:
        payload = await rec_client.fetch_locations()
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to fetch Rec data: %s", exc, exc_info=True)
        with SessionLocal() as db:
            update_status(db, error=str(exc))
            db.commit()
        return

    with SessionLocal() as db:
        try:
            new_slots = sync_availability(db, payload)
            if new_slots:
                create_alerts(db, new_slots)
            update_status(db)
            db.commit()
            if new_slots:
                logger.info("Recorded %s new slots", len(new_slots))
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            logger.error("Failed to persist availability: %s", exc, exc_info=True)
            update_status(db, error=str(exc))
            db.commit()


async def scraper_loop() -> None:
    """Background task that continuously pulls availability."""
    interval = max(60, settings.scrape_interval_seconds)
    while True:
        try:
            await poll_once()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error("Background scraper crashed: %s", exc, exc_info=True)
        await asyncio.sleep(interval)


@app.on_event("startup")
async def on_startup() -> None:
    """Start background scraper on startup."""
    if not settings.scraper_enabled:
        logger.info("Scraper disabled; startup loop skipped.")
        return
    global scrape_task  # noqa: PLW0603
    scrape_task = asyncio.create_task(scraper_loop())


@app.on_event("shutdown")
async def on_shutdown() -> None:
    """Clean up background task and HTTP client."""
    if scrape_task:
        scrape_task.cancel()
        try:
            await scrape_task
        except asyncio.CancelledError:
            pass
    await rec_client.close()


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    """Serve the single page frontend."""
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "org_slug": settings.organization_slug},
    )


@app.get("/api/status", response_model=StatusResponse)
def get_status(db: Session = Depends(get_session)) -> StatusResponse:
    """Return last sync info."""
    status = db.get(SystemStatus, 1)
    if not status:
        return StatusResponse()
    return StatusResponse(
        last_successful_sync=status.last_successful_sync,
        last_error=status.last_error,
        last_error_at=status.last_error_at,
    )


@app.get("/api/locations", response_model=LocationsEnvelope)
def list_locations(db: Session = Depends(get_session)) -> LocationsEnvelope:
    """Return aggregated availability by location."""
    locations = db.query(Location).order_by(Location.name).all()
    response_locations: List[LocationAvailabilityResponse] = []
    for loc in locations:
        slots = (
            db.query(AvailabilitySlot)
            .filter(AvailabilitySlot.location_id == loc.id)
            .order_by(AvailabilitySlot.slot_time_local.asc())
            .all()
        )
        slot_payload = [SlotResponse.model_validate(slot) for slot in slots]
        response_locations.append(
            LocationAvailabilityResponse(
                id=loc.id,
                name=loc.name,
                address=loc.address,
                image_url=loc.image_url,
                slots=slot_payload,
            )
        )
    status = db.get(SystemStatus, 1)
    last_updated = status.last_successful_sync if status else None
    return LocationsEnvelope(last_updated=last_updated, locations=response_locations)


@app.get("/api/watchers", response_model=list[WatchRuleResponse])
def list_watchers(db: Session = Depends(get_session)) -> list[WatchRuleResponse]:
    """Return all active watch rules."""
    watches = db.query(WatchRule).order_by(WatchRule.created_at.desc()).all()
    return [watch_to_schema(w) for w in watches]


@app.post("/api/watchers", response_model=WatchRuleResponse)
def create_watch(
    payload: WatchRuleCreate,
    db: Session = Depends(get_session),
) -> WatchRuleResponse:
    """Persist a new watch rule."""
    if payload.time_from and payload.time_to and payload.time_from > payload.time_to:
        raise HTTPException(status_code=400, detail="time_from must be before time_to")

    location = db.get(Location, payload.location_id)
    if not location:
        raise HTTPException(status_code=404, detail="Unknown location")

    watch = WatchRule(
        location_id=payload.location_id,
        label=payload.label,
        court_query=payload.court_query,
        target_date=payload.target_date,
        time_from=payload.time_from,
        time_to=payload.time_to,
        contact=payload.contact,
        notes=payload.notes,
    )
    db.add(watch)
    db.commit()
    db.refresh(watch)
    return watch_to_schema(watch)


@app.delete("/api/watchers/{watch_id}", response_model=dict)
def delete_watch(
    watch_id: int = Path(..., ge=1),
    db: Session = Depends(get_session),
) -> dict[str, str]:
    """Delete a watch by id."""
    watch = db.get(WatchRule, watch_id)
    if not watch:
        raise HTTPException(status_code=404, detail="Watch not found")
    db.delete(watch)
    db.commit()
    return {"status": "deleted"}


@app.post("/api/watchers/{watch_id}/toggle", response_model=WatchRuleResponse)
def toggle_watch(
    watch_id: int = Path(..., ge=1),
    db: Session = Depends(get_session),
) -> WatchRuleResponse:
    """Flip the active flag for a watch rule."""
    watch = db.get(WatchRule, watch_id)
    if not watch:
        raise HTTPException(status_code=404, detail="Watch not found")
    watch.active = not watch.active
    db.commit()
    db.refresh(watch)
    return watch_to_schema(watch)


@app.get("/api/alerts", response_model=list[AlertResponse])
def list_alerts(
    limit: int = 25,
    db: Session = Depends(get_session),
) -> list[AlertResponse]:
    """Return the most recent alerts."""
    limit = max(1, min(limit, 100))
    alerts = (
        db.query(Alert)
        .order_by(Alert.created_at.desc())
        .limit(limit)
        .all()
    )
    response: list[AlertResponse] = []
    for alert in alerts:
        response.append(
            AlertResponse(
                id=alert.id,
                watch_id=alert.watch_id,
                location_id=alert.location_id,
                court_id=alert.court_id,
                court_name=alert.court_name,
                slot_time_local=alert.slot_time_local,
                slot_time_utc=alert.slot_time_utc,
                created_at=alert.created_at,
                watch_label=alert.watch.label if alert.watch else None,
            )
        )
    return response

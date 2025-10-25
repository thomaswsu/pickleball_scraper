"""Playwright test fixtures."""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta
from multiprocessing import Process
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import AvailabilitySlot, Location


def _run_test_server(port: int) -> None:
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=port, log_level="warning")


@pytest.fixture(scope="session")
def e2e_base_url(tmp_path_factory) -> str:
    """Spin up a live server pointing at a temporary SQLite database."""

    tmp_dir = tmp_path_factory.mktemp("e2e")
    db_path = tmp_dir / "app.db"
    port = 8765
    base_url = f"http://127.0.0.1:{port}"

    original_env = {k: os.environ.get(k) for k in ["DATABASE_URL", "SCRAPER_ENABLED"]}
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    os.environ["SCRAPER_ENABLED"] = "false"

    engine = create_engine(os.environ["DATABASE_URL"], connect_args={"check_same_thread": False})
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)

    with Session() as session:
        location = Location(
            id="e2e-location",
            name="Playwright Courts",
            address="1 Market St, San Francisco",
            timezone="America/Los_Angeles",
        )
        session.add(location)

        tz = ZoneInfo("America/Los_Angeles")
        slot_local = (datetime.now(tz) + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        slot = AvailabilitySlot(
            location_id=location.id,
            court_id="court-1",
            court_name="Court 1",
            sport_id=None,
            slot_time_local=slot_local.replace(tzinfo=None),
            slot_time_utc=slot_local.astimezone(ZoneInfo("UTC")),
        )
        session.add(slot)
        session.commit()

    process = Process(target=_run_test_server, args=(port,), daemon=True)
    process.start()

    try:
        deadline = time.time() + 20
        while time.time() < deadline:
            try:
                response = httpx.get(f"{base_url}/api/status", timeout=1.0)
                if response.status_code == 200:
                    break
            except Exception:
                time.sleep(0.2)
        else:
            raise RuntimeError("Failed to start test server")

        yield base_url
    finally:
        process.terminate()
        process.join(timeout=5)

        for key, value in original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

        (db_path if isinstance(db_path, Path) else Path(db_path)).unlink(missing_ok=True)

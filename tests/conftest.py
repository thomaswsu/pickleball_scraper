"""Shared pytest fixtures for unit tests."""

from __future__ import annotations

from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base, get_session
from app.main import app, settings
from app.models import Location

TEST_DATABASE_URL = "sqlite:///./test_app.db"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


@pytest.fixture(scope="function")
def db_session():
    """Provide a clean database for each test."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="function")
def client(db_session):
    """FastAPI TestClient bound to the temporary database."""

    def override_session():
        try:
            yield db_session
        finally:
            pass

    original_flag = settings.scraper_enabled
    settings.scraper_enabled = False
    app.dependency_overrides[get_session] = override_session

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    settings.scraper_enabled = original_flag


@pytest.fixture
def sample_location(db_session):
    """Insert a sample location for API tests."""
    location = Location(
        id="loc-123",
        name="Mission Dolores Courts",
        address="19th & Dolores St, San Francisco",
        timezone="America/Los_Angeles",
        image_url=None,
    )
    db_session.add(location)
    db_session.commit()
    return location

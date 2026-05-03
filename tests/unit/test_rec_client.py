"""Rec API client tests."""

from __future__ import annotations

from app.rec_client import RecClient


def test_rec_client_uses_rec_compatible_headers(monkeypatch):
    captured_kwargs = {}

    class DummyAsyncClient:
        def __init__(self, **kwargs):
            captured_kwargs.update(kwargs)

    monkeypatch.setattr("app.rec_client.httpx.AsyncClient", DummyAsyncClient)

    RecClient()

    assert captured_kwargs["headers"]["Accept"] == "application/json"
    assert "Mozilla/5.0" in captured_kwargs["headers"]["User-Agent"]

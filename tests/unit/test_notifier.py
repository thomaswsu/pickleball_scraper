"""Notifier tests."""

from app import notifier


class DummySettings:
    smtp_enabled = False
    smtp_host = None
    smtp_port = 587
    smtp_username = None
    smtp_password = None
    smtp_from_address = "alerts@example.com"
    smtp_use_tls = True


class DummyWatch:
    def __init__(self, contact: str | None):
        self.contact = contact


def test_send_email_alert_disabled(monkeypatch):
    monkeypatch.setattr(notifier, "get_settings", lambda: DummySettings())
    watch = DummyWatch(contact="user@example.com")
    assert notifier.send_email_alert(watch=watch, subject="Test", body="Body") is False


def test_send_email_alert_no_contact(monkeypatch):
    settings = DummySettings()
    settings.smtp_enabled = True
    settings.smtp_host = "smtp.example.com"
    monkeypatch.setattr(notifier, "get_settings", lambda: settings)
    watch = DummyWatch(contact=None)
    assert notifier.send_email_alert(watch=watch, subject="Test", body="Body") is False

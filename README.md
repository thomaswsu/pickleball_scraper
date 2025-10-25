# Pickleball Court Watcher

A minimal FastAPI application that scrapes public availability data from [rec.us](https://www.rec.us/organizations/san-francisco-rec-park?tab=locations) and surfaces it in a phone-friendly dashboard with configurable alerts. The backend polls the Rec API on a schedule, stores new slots in SQLite, and fires alerts whenever a watch rule matches a newly released reservation.

## Features

- 🚀 **Live scrape loop** – pulls `/v1/locations/availability` from `api.rec.us` and keeps the local database synced.
- 🗺️ **Availability view** – responsive UI with date/time quick filters that surfaces upcoming pickleball slots grouped by location.
- 🔔 **Alerting rules** – save filters for location, court substring, date, and time windows; alerts are logged each time a matching slot appears.
- 📱 **Mobile-first UI** – Tailwind-based single page optimized for small screens.
- 📡 **REST API** – JSON endpoints for locations, watchers, alerts, and system status.

## Getting started

1. **Install dependencies**

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Run the app**

   ```bash
   uvicorn app.main:app --reload
   ```

3. Visit http://127.0.0.1:8000 to access the dashboard. The scraper kicks off immediately; the first sync usually takes a few seconds.

## Configuration

The app reads settings from environment variables (see `app/config.py` for defaults):

| Variable | Description | Default |
| --- | --- | --- |
| `REC_BASE_URL` | Rec API root | `https://api.rec.us` |
| `ORGANIZATION_SLUG` | Rec organization slug to target | `san-francisco-rec-park` |
| `SCRAPE_INTERVAL_SECONDS` | Poll interval for background scraper | `300` |
| `HTTP_TIMEOUT_SECONDS` | HTTP timeout for Rec requests | `30` |
| `TIMEZONE` | Fallback timezone for slots | `America/Los_Angeles` |
| `DATABASE_URL` | SQLAlchemy connection string | `sqlite:///./app.db` |
| `SCRAPER_ENABLED` | Toggle background polling (handy for tests) | `true` |
| `SMTP_ENABLED` | Enable email notifications when alerts fire | `false` |
| `SMTP_HOST` | SMTP server hostname | _required if SMTP enabled_ |
| `SMTP_PORT` | SMTP server port | `587` |
| `SMTP_USERNAME` | SMTP username | optional |
| `SMTP_PASSWORD` | SMTP password | optional |
| `SMTP_FROM_ADDRESS` | From address used in outbound mail | `alerts@example.com` |
| `SMTP_USE_TLS` | Whether to start TLS before sending | `true` |
| `PICKLEBALL_SPORT_ID` | Rec sport UUID to keep (others are dropped) | `bd745b6e-1dd6-43e2-a69f-06f094808a96` |

You can override any value via a `.env` file in the repo root, for example:

```
ORGANIZATION_SLUG=san-francisco-rec-park
SCRAPE_INTERVAL_SECONDS=120
```

## API overview

- `GET /api/locations` – latest availability grouped by location
- `GET /api/watchers` – list alert rules
- `POST /api/watchers` – create a rule
- `POST /api/watchers/{id}/toggle` – enable/disable a rule
- `DELETE /api/watchers/{id}` – remove a rule
- `GET /api/alerts` – recent alert firings
- `GET /api/status` – heartbeat / last sync info

All payloads are JSON and documented in `app/schemas.py`.

## Testing

Unit and service tests live under `tests/unit`, while browser-based end-to-end checks live in `tests/e2e`.

```bash
# run quick unit/service tests
pytest -m \"not e2e\"

# install browsers once, then execute the Playwright suite
playwright install
pytest -m e2e
```

The E2E suite boots a temporary uvicorn server against an isolated SQLite DB, drives the web UI via Playwright, and tears everything down automatically.

## Email alerts

Each watch now includes an email address. When the scraper detects a matching slot:

1. An `Alert` row is stored (as before), and
2. If SMTP settings are configured and the watch has an email, a message is sent via `smtplib`.

To activate email delivery set `SMTP_ENABLED=true` plus the SMTP connection settings described above (for example, a Gmail app password, Fastmail account, or a free-tier provider). The app uses TLS by default and only attempts to authenticate if username/password are provided.

## Next steps

- Wire alerts into email/SMS providers.
- Add push notifications or webhooks.
- Package the scraper logic for reuse in an eventual native iOS client.

---

Built with ❤️ using FastAPI, httpx, and Tailwind CSS.

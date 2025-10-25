from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Project layout this file expects:
# .
# ├── app/
# │   └── main.py        (this file)
# ├── templates/
# │   └── index.html     (references /static/styles.css and /static/app.js)
# └── static/
#     ├── styles.css
#     └── app.js

app: FastAPI = FastAPI()

# Ensure these folders exist (no-op if they already do).
# Helpful during first run so you don't get confusing 404s.
Path("templates").mkdir(parents=True, exist_ok=True)
Path("static").mkdir(parents=True, exist_ok=True)

# Mount /static so /static/styles.css and /static/app.js resolve instead of 404.
app.mount("/static", StaticFiles(directory="static"), name="static")

# Point templates to the /templates directory.
templates: Jinja2Templates = Jinja2Templates(directory="templates")


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request) -> HTMLResponse:
    """
    Serve the main page. Your templates/index.html should link to:
      <link rel="stylesheet" href="/static/styles.css" />
      <script src="/static/app.js" defer></script>
    """
    return templates.TemplateResponse("index.html", {"request": request})

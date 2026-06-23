from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .api import router

STATIC = Path(__file__).parent / "static"

_PLACEHOLDER = """<!doctype html><meta charset="utf-8">
<title>qliff</title>
<body style="font-family:system-ui;background:#0f1115;color:#e6e8ec;padding:40px">
<h1>qliff</h1>
<p>The frontend isn't built yet. From the repo root run:</p>
<pre>./do studio</pre>
<p>then restart <code>qliff-server</code>. The API is live under <code>/api</code>.</p>
</body>"""


def create_app() -> FastAPI:
    app = FastAPI(title="qliff studio", version="1.0.0")

    # No CORS: the SPA and the API share one origin. In production the built SPA
    # is served from `/` here; in dev the Vite server proxies `/api` (REST + WS)
    # to this server (studio/vite.config.ts), so the browser only ever sees one
    # origin and never makes a cross-origin request.
    app.include_router(router, prefix="/api")

    # serve the built SPA at root; fall back to a "build me" page if absent.
    if (STATIC / "index.html").exists():
        app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")
    else:

        @app.get("/", response_class=HTMLResponse)
        def _placeholder() -> str:
            return _PLACEHOLDER

    return app


app = create_app()

"""
app.py
Titik masuk utama ARDIVA. Hanya merakit router — jangan tambahkan logika di sini.
"""

import os
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from config import SECRET_KEY
from routers import auth, index
from routers.bidang import base as bidang_router

app = FastAPI(title="ARDIVA — ARsip DInamis serVice Automation", docs_url=None)

# ── Middleware ───────────────────────────────────────────────────────────────
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, max_age=86400)

# ── Static files ─────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(__file__)
static_dir = os.path.join(BASE_DIR, "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(index.router)
app.include_router(auth.router)
app.include_router(bidang_router.router)


# ── 404 fallback ──────────────────────────────────────────────────────────────
@app.exception_handler(404)
async def not_found(request: Request, exc):
    from core import templates
    return templates.TemplateResponse(
        "partials/404.html",
        {"request": request},
        status_code=404
    )

"""
routers/index.py
Landing page ARDIVA.
"""

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from core import templates

router = APIRouter()

@router.get("/")
async def index(request: Request):
    # Kalau sudah login langsung ke dashboard bidang
    user = request.session.get("user")
    if user:
        return RedirectResponse(f"/b/{user['bidang_id']}/dashboard")
    return templates.TemplateResponse("index/index.html", {"request": request})

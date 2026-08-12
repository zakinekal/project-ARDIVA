"""
core.py
Utilitas bersama: template engine, session helper, matcher loader.
"""

import os
from functools import lru_cache
from fastapi import Request
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from config import SECRET_KEY

BASE_DIR   = os.path.dirname(__file__)
DATA_DIR   = os.path.join(BASE_DIR, "data")
templates  = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))
_original_template_response = templates.TemplateResponse


def _template_response_compat(name, context=None, status_code=200, headers=None, media_type=None, background=None, **kwargs):
    """Kompatibel dengan pemanggilan lama dan baru untuk TemplateResponse."""
    request = kwargs.pop("request", None)
    if isinstance(name, Request):
        request = name
        template_name = kwargs.pop("name", None)
        template_context = dict(context or {})
    else:
        template_name = name
        template_context = dict(context or {})
        if request is None:
            request = template_context.get("request")

    if request is None:
        raise TypeError("request is required for template rendering")
    if template_name is None:
        raise TypeError("template name is required")

    return _original_template_response(
        request=request,
        name=template_name,
        context=template_context,
        status_code=status_code,
        headers=headers,
        media_type=media_type,
        background=background,
    )


# Monkey-patch agar kode lama tetap bekerja dengan Starlette versi baru.
templates.TemplateResponse = _template_response_compat


# ── Session helper ───────────────────────────────────────────────────────────
def get_user(request: Request) -> dict | None:
    """Kembalikan data user dari session, atau None jika belum login."""
    return request.session.get("user")


def require_login(request: Request) -> dict:
    """
    Gunakan di route yang butuh login.
    Raise redirect ke /login kalau belum login.
    """
    from fastapi.responses import RedirectResponse
    user = get_user(request)
    if not user:
        raise _redirect("/login")
    return user


class _redirect(Exception):
    def __init__(self, url: str):
        self.url = url


# ── Matcher loader (cached) ───────────────────────────────────────────────────
@lru_cache(maxsize=1)
def get_matcher():
    from matcher import KlasifikasiMatcher
    JRA_PATH   = os.path.join(DATA_DIR, "lampiran_ii_jra.json")
    SKKD_PATH  = os.path.join(DATA_DIR, "lampiran_iii_skkd.json")
    KAMUS_PATH = os.path.join(DATA_DIR, "kamus_istilah_pencocokan.xlsx")
    return KlasifikasiMatcher(JRA_PATH, SKKD_PATH, KAMUS_PATH)

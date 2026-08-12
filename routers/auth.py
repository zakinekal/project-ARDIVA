"""
routers/auth.py
Menangani Google OAuth: login, callback, logout.
"""

import httpx
import secrets
from urllib.parse import urlencode
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from config import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, get_bidang_by_email
from core import templates

router = APIRouter()

# ── Google OAuth Configuration ───────────────────────────────────────────────
GOOGLE_OAUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"

if GOOGLE_CLIENT_ID == "ISI_NANTI" or GOOGLE_CLIENT_SECRET == "ISI_NANTI":
    raise ValueError(
        "GOOGLE_CLIENT_ID atau GOOGLE_CLIENT_SECRET belum diisi di .env. "
        "Silakan isi .env dengan credentials dari Google Cloud Console."
    )


# ── Halaman login ────────────────────────────────────────────────────────────
@router.get("/login")
async def login_page(request: Request):
    """Tampilkan halaman login."""
    if request.session.get("user"):
        return RedirectResponse("/dashboard")
    return templates.TemplateResponse(
        "auth/login.html",
        {"request": request}
    )


# ── Mulai OAuth flow ─────────────────────────────────────────────────────────
@router.get("/auth/google")
async def auth_google(request: Request):
    """Redirect ke Google login page."""
    redirect_uri = str(request.url_for("auth_callback"))
    
    # Generate state untuk CSRF protection
    state = secrets.token_urlsafe(32)
    request.session["oauth_state"] = state
    
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "offline",
    }
    
    auth_url = f"{GOOGLE_OAUTH_URL}?{urlencode(params)}"
    print(f"[AUTH] Redirecting to: {auth_url[:80]}...")
    return RedirectResponse(auth_url)


# ── Callback dari Google ─────────────────────────────────────────────────────
@router.get("/auth/callback", name="auth_callback")
async def auth_callback(request: Request):
    """Handle callback dari Google OAuth."""
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    error = request.query_params.get("error")
    
    print(f"[AUTH] Callback - Code: {code[:20] if code else 'None'}... State: {state[:20] if state else 'None'}... Error: {error}")
    
    # Check for OAuth errors
    if error:
        print(f"[AUTH] Google OAuth error: {error}")
        return RedirectResponse("/login?error=google_error")
    
    # Verify state token
    stored_state = request.session.get("oauth_state")
    if not state or state != stored_state:
        print(f"[AUTH] State mismatch! Stored: {stored_state}, Received: {state}")
        return RedirectResponse("/login?error=state_mismatch")
    
    if not code:
        print("[AUTH] No authorization code received")
        return RedirectResponse("/login?error=no_code")
    
    # Exchange code for token
    redirect_uri = str(request.url_for("auth_callback"))
    token_data = {
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
    }
    
    try:
        async with httpx.AsyncClient() as client:
            token_response = await client.post(GOOGLE_TOKEN_URL, data=token_data)
            token_response.raise_for_status()
            token_data_response = token_response.json()
            print(f"[AUTH] Token received successfully")
    except Exception as e:
        print(f"[AUTH] Failed to exchange code for token: {e}")
        return RedirectResponse("/login?error=token_exchange_failed")
    
    # Get user info
    access_token = token_data_response.get("access_token")
    if not access_token:
        print("[AUTH] No access token in response")
        return RedirectResponse("/login?error=no_token")
    
    try:
        async with httpx.AsyncClient() as client:
            headers = {"Authorization": f"Bearer {access_token}"}
            userinfo_response = await client.get(GOOGLE_USERINFO_URL, headers=headers)
            userinfo_response.raise_for_status()
            user_info = userinfo_response.json()
            print(f"[AUTH] User info received")
    except Exception as e:
        print(f"[AUTH] Failed to get user info: {e}")
        return RedirectResponse("/login?error=userinfo_failed")
    
    # Get user email and check if registered
    email = user_info.get("email", "")
    print(f"[AUTH] User email: {email}")
    
    bidang = get_bidang_by_email(email)
    if not bidang:
        print(f"[AUTH] Email {email} not registered in BIDANG_CONFIG")
        return templates.TemplateResponse(
            "auth/tidak_diizinkan.html",
            {"request": request, "email": email},
            status_code=403
        )
    
    # Save user to session
    request.session["user"] = {
        "email": email,
        "nama": user_info.get("name", email),
        "foto": user_info.get("picture", ""),
        "bidang_id": bidang["id"],
        "bidang_nama": bidang["nama"],
        "bidang_pendek": bidang["nama_pendek"],
    }
    
    # Clean up state
    if "oauth_state" in request.session:
        del request.session["oauth_state"]
    
    print(f"[AUTH] ✓ User {email} logged in successfully (bidang: {bidang['id']})")
    return RedirectResponse(f"/b/{bidang['id']}/dashboard")


# ── Logout ───────────────────────────────────────────────────────────────────
@router.get("/logout")
async def logout(request: Request):
    """Logout dan clear session."""
    request.session.clear()
    return RedirectResponse("/")


# ── Redirect /dashboard ke bidang masing-masing ──────────────────────────────
@router.get("/dashboard")
async def dashboard_redirect(request: Request):
    """Redirect ke dashboard bidang user."""
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/login")
    return RedirectResponse(f"/b/{user['bidang_id']}/dashboard")

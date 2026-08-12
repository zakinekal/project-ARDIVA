"""
config.py
Satu-satunya file yang perlu diubah saat email/spreadsheet sudah diterima dari instansi.
Ganti nilai "ISI_NANTI" dengan data yang sebenarnya.
"""

import os
import warnings
from dotenv import load_dotenv

# Load local .env for development (ignored in repo)
load_dotenv()


def _env(key: str, default: str | None = None, required: bool = False) -> str | None:
    """Helper to read environment vars and warn if required ones are missing."""
    val = os.getenv(key, default)
    if required and (val is None or val == ""):
        warnings.warn(f"Required environment variable '{key}' is not set.")
    return val


# ── Google OAuth ────────────────────────────────────────────────────────────
# Put sensitive values into environment variables (see .env.example)
GOOGLE_CLIENT_ID = _env("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = _env("GOOGLE_CLIENT_SECRET", required=True)
SECRET_KEY = _env("SECRET_KEY", required=True)

# ── Apps Script ─────────────────────────────────────────────────────────────
# URL deployment Apps Script (milik akun Sekretariat)
APPS_SCRIPT_URL = _env("APPS_SCRIPT_URL")
SECRET_TOKEN = _env("SECRET_TOKEN", required=True)

# ── Mapping bidang ───────────────────────────────────────────────────────────
# Format: "email@gmail.com" -> konfigurasi bidang
# Ganti email placeholder dengan email asli dari instansi
BIDANG_CONFIG = {

    # ── Bidang Sekretariat ───────────────────────────────────────────────
    "bidangsekretariatkaltim@gmail.com": {
        "id":             "sekretariat",
        "nama":           "Bidang Sekretariat",
        "nama_pendek":    "Sekretariat",
        "spreadsheet_id": os.getenv("SPREADSHEET_SEKRETARIAT", "1I19z81sarxqCVwLQUoRZ7o6g86xqa7wFHdKPs8iDrBU"),
        "sub_kegiatan":   ["."],
        "warna":          "#0D6B52",   # hijau teal (default)
    },

    # ── Bidang Pemerintahan Desa dan Kelurahan (Bidang I) ────────────────
    "pemdeskaltim@gmail.com": {
        "id":             "pemdes",
        "nama":           "Bidang Pemerintahan Desa dan Kelurahan",
        "nama_pendek":    "Bidang I — PEMDES",
        "spreadsheet_id": os.getenv("SPREADSHEET_PEMDES", "1AJTg_sjxZzbXpl1pXR4eDQZEnf80F2uz-eACtvGWmV0"),
        "sub_kegiatan":   ["."],
        "warna":          "#0D6B52",
    },

    # ── Bidang Pembangunan Desa dan Kawasan Pedesaan (Bidang II) ─────────
    "bidangpdkpkaltim@gmail.com": {
        "id":             "bidang2",
        "nama":           "Bidang Pembangunan Desa dan Kawasan Pedesaan",
        "nama_pendek":    "Bidang II — Pembangunan Desa",
        "spreadsheet_id": os.getenv("SPREADSHEET_BIDANG2", "18Mq46A21h-NbStpU5Tcx0qSDJVBeoOHqbt-RxjxtKpo"),
        "sub_kegiatan":   ["."],
        "warna":          "#0D6B52",
    },

    # ── Bidang Pemberdayaan Kelembagaan dan Sosial Budaya (Bidang III) ───
    "bidangpksbmkaltim@gmail.com": {
        "id":             "bidang3",
        "nama":           "Bidang Pemberdayaan Kelembagaan dan Sosial Budaya Masyarakat",
        "nama_pendek":    "Bidang III — Pemberdayaan",
        "spreadsheet_id": os.getenv("SPREADSHEET_BIDANG3", "1snbvI9iThS-51Mw-wMuLKQlnjIMTlR2sa9BzO41sKdE"),
        "sub_kegiatan":   ["."],
        "warna":          "#0D6B52",
    },

    # ── Bidang Usaha Ekonomi Masyarakat, SDA dan TTG (Bidang IV) ─────────
    "bidangukmsdattgkaltim@gmail.com": {
        "id":             "bidang4",
        "nama":           "Bidang Usaha Ekonomi Masyarakat, SDA dan Teknologi Tepat Guna",
        "nama_pendek":    "Bidang IV — Usaha Ekonomi",
        "spreadsheet_id": os.getenv("SPREADSHEET_BIDANG4", "10q-uMCvd_4e1dI8Gx_4qz9Ww2uIJUW6mcB_ZKjz8Lnc"),
        "sub_kegiatan":   ["."],
        "warna":          "#0D6B52",
    },
}

def get_bidang_by_email(email: str) -> dict | None:
    """Kembalikan config bidang berdasarkan email. None jika tidak terdaftar."""
    return BIDANG_CONFIG.get(email)

def is_authorized(email: str) -> bool:
    return email in BIDANG_CONFIG

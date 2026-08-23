"""
sheets_client.py
Semua komunikasi ke Google Apps Script.
Setiap fungsi menerima spreadsheet_id untuk menentukan bidang tujuan.
"""

import requests
from config import APPS_SCRIPT_URL, SECRET_TOKEN

TIMEOUT = (5, 20)


def _post(payload: dict) -> dict:
    """Kirim POST ke Apps Script dan kembalikan respons JSON."""
    if APPS_SCRIPT_URL == "ISI_NANTI":
        return {"status": "error", "message": "Apps Script belum dikonfigurasi."}
    try:
        payload["token"] = SECRET_TOKEN
        r = requests.post(APPS_SCRIPT_URL, json=payload, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.Timeout:
        return {"status": "error", "message": "Koneksi ke Google Sheets timeout. Coba lagi."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def cek_status(spreadsheet_id: str) -> dict:
    return _post({"action": "cek_status", "spreadsheet_id": spreadsheet_id})


def simpan_arsip(data: dict, spreadsheet_id: str, force: bool = False) -> dict:
    return _post({
        "action":         "simpan",
        "spreadsheet_id": spreadsheet_id,
        "data":           data,
        "force":          force,
    })


def ambil_semua_data(spreadsheet_id: str) -> dict:
    return _post({
        "action":         "ambil_semua",
        "spreadsheet_id": spreadsheet_id,
    })


def update_arsip(baris: int, data: dict, spreadsheet_id: str) -> dict:
    return _post({
        "action":         "update",
        "spreadsheet_id": spreadsheet_id,
        "baris":          baris,
        "data":           data,
    })


def hapus_arsip(baris: int, spreadsheet_id: str) -> dict:
    return _post({
        "action":         "hapus",
        "spreadsheet_id": spreadsheet_id,
        "baris":          baris,
    })

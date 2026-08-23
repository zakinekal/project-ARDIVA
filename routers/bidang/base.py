"""
routers/bidang/base.py
Router generik yang menangani semua 5 bidang dengan logika identik.
URL pattern: /b/{bidang_id}/...
"""

import os
import tempfile
from fastapi import APIRouter, Request, UploadFile, File, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from starlette.concurrency import run_in_threadpool
from typing import Optional
from core import templates, get_matcher
from sheets_client import (
    simpan_arsip, ambil_semua_data, update_arsip,
    hapus_arsip
)
from baca_surat import ekstrak_surat
from config import get_bidang_by_email, BIDANG_CONFIG

router = APIRouter(prefix="/b/{bidang_id}")

VALID_IDS = {"sekretariat", "pemdes", "bidang2", "bidang3", "bidang4"}


def _cek_akses(request: Request, bidang_id: str):
    """Pastikan user login dan hanya akses bidang miliknya sendiri."""
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/login"), None
    if user["bidang_id"] != bidang_id:
        return RedirectResponse(f"/b/{user['bidang_id']}/dashboard"), None
    if bidang_id not in VALID_IDS:
        return RedirectResponse("/login"), None
    # Ambil config bidang dari email
    email   = user["email"]
    bidang  = get_bidang_by_email(email)
    return None, {"user": user, "bidang": bidang}


def _ctx(request, bidang_id, user, bidang, **extra):
    """Buat context dasar untuk semua template bidang."""
    return {
        "request":     request,
        "bidang_id":   bidang_id,
        "user":        user,
        "bidang":      bidang,
        "active_page": extra.get("active_page", ""),
        **extra
    }


# ═══════════════════════════════════════════════════════════════════════════
# DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════
@router.get("/dashboard")
async def dashboard(request: Request, bidang_id: str):
    redir, ctx = _cek_akses(request, bidang_id)
    if redir:
        return redir
    spreadsheet_id = ctx["bidang"]["spreadsheet_id"]
    hasil = await run_in_threadpool(ambil_semua_data, spreadsheet_id)
    status = {
        "status": hasil.get("status", "error"),
        "jumlah_data": len(hasil.get("data", [])),
        "message": hasil.get("message", ""),
    }
    rows  = hasil.get("data", []) if hasil.get("status") == "success" else []
    return templates.TemplateResponse(
        "bidang/dashboard.html",
        _ctx(request, bidang_id, ctx["user"], ctx["bidang"],
             active_page="dashboard", status=status, rows=rows)
    )


# ═══════════════════════════════════════════════════════════════════════════
# INPUT SURAT
# ═══════════════════════════════════════════════════════════════════════════
@router.get("/input")
async def input_page(request: Request, bidang_id: str):
    redir, ctx = _cek_akses(request, bidang_id)
    if redir:
        return redir
    return templates.TemplateResponse(
        "bidang/input.html",
        _ctx(request, bidang_id, ctx["user"], ctx["bidang"],
             active_page="input")
    )

@router.get("/input/manual")
async def input_manual_page(request: Request, bidang_id: str):
    redir, ctx = _cek_akses(request, bidang_id)
    if redir:
        return redir
    return templates.TemplateResponse(
        "bidang/input_manual.html",
        _ctx(request, bidang_id, ctx["user"], ctx["bidang"],
             active_page="input",
             sub_list=ctx["bidang"]["sub_kegiatan"])
    )



@router.post("/input/proses")
async def input_proses(request: Request, bidang_id: str, file: UploadFile = File(...)):
    redir, ctx = _cek_akses(request, bidang_id)
    if redir:
        return redir

    matcher = await run_in_threadpool(get_matcher)
    sub_list = ctx["bidang"]["sub_kegiatan"]

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(await file.read())
            tmp_path = tmp.name
        try:
            data = await run_in_threadpool(ekstrak_surat, tmp_path)
        finally:
            os.remove(tmp_path)
    except Exception as e:
        return templates.TemplateResponse(
            "partials/error_proses.html",
            {"request": request, "error": str(e)}
        )

    teks_klas = data.get("perihal") or data.get("uraian_arsip", "")
    kandidat_sub = matcher.classify_sub_kegiatan(teks_klas, top_n=3)
    sub_terpilih = kandidat_sub[0][0] if kandidat_sub and kandidat_sub[0][1] > 0 else sub_list[0]

    kode_dari_nomor = data.get("kode_klas", "")
    kandidat_kode = _kandidat_kode(matcher, teks_klas, sub_terpilih, kode_dari_nomor)

    return templates.TemplateResponse(
        "bidang/partials/form_konfirmasi.html",
        _ctx(request, bidang_id, ctx["user"], ctx["bidang"],
             data=data,
             sub_list=sub_list,
             sub_terpilih=sub_terpilih,
             kandidat_kode=kandidat_kode,
             uraian_untuk_klasifikasi=teks_klas,
             nama_file=file.filename)
    )


@router.post("/input/kandidat")
async def input_kandidat(
    request: Request, bidang_id: str,
    sub_kegiatan: str = Form(""),
    uraian_untuk_klasifikasi: str = Form(""),
    kode_dari_nomor: str = Form(""),
    nama_file: str = Form(""),
):
    redir, ctx = _cek_akses(request, bidang_id)
    if redir:
        return redir
    matcher = await run_in_threadpool(get_matcher)
    kandidat_kode = _kandidat_kode(matcher, uraian_untuk_klasifikasi, sub_kegiatan, kode_dari_nomor)
    return templates.TemplateResponse(
        "bidang/partials/kode_area.html",
        _ctx(request, bidang_id, ctx["user"], ctx["bidang"],
             kandidat_kode=kandidat_kode)
    )


@router.post("/input/simpan")
async def input_simpan(request: Request, bidang_id: str):
    redir, ctx = _cek_akses(request, bidang_id)
    if redir:
        return redir

    form = await request.form()
    row  = dict(form)
    force = row.pop("force", "false") == "true"
    spreadsheet_id = ctx["bidang"]["spreadsheet_id"]
    unit_pengolah  = ctx["bidang"]["nama"]

    row["unit_pengolah"] = unit_pengolah
    hasil = await run_in_threadpool(simpan_arsip, row, spreadsheet_id, force)

    return templates.TemplateResponse(
        "bidang/partials/simpan_hasil.html",
        _ctx(request, bidang_id, ctx["user"], ctx["bidang"],
             hasil=hasil, row=row)
    )


# ═══════════════════════════════════════════════════════════════════════════
# LIHAT DATA
# ═══════════════════════════════════════════════════════════════════════════
@router.get("/data")
async def data_page(
    request: Request, bidang_id: str,
    q: str = "", sub: str = "", tahun: str = "", hal: int = 1
):
    redir, ctx = _cek_akses(request, bidang_id)
    if redir:
        return redir

    spreadsheet_id = ctx["bidang"]["spreadsheet_id"]
    hasil = await run_in_threadpool(ambil_semua_data, spreadsheet_id)
    rows  = hasil.get("data", []) if hasil.get("status") == "success" else []

    # Filter
    if q:
        q_low = q.lower()
        rows = [r for r in rows if
                q_low in (r.get("no_surat","")).lower() or
                q_low in (r.get("uraian_arsip","")).lower() or
                q_low in (r.get("pengirim","")).lower()]
    if sub:
        rows = [r for r in rows if r.get("sub_kegiatan","") == sub]
    if tahun:
        rows = [r for r in rows if r.get("tahun","") == tahun]

    # Pagination
    PER_HAL = 15
    total   = len(rows)
    total_hal = max(1, (total + PER_HAL - 1) // PER_HAL)
    hal     = max(1, min(hal, total_hal))
    rows_hal = rows[(hal-1)*PER_HAL : hal*PER_HAL]

    # Daftar unik untuk filter dropdown
    semua = hasil.get("data", [])
    sub_list  = sorted({r.get("sub_kegiatan","") for r in semua if r.get("sub_kegiatan","")})
    tahun_list = sorted({r.get("tahun","") for r in semua if r.get("tahun","")}, reverse=True)

    return templates.TemplateResponse(
        "bidang/data.html",
        _ctx(request, bidang_id, ctx["user"], ctx["bidang"],
             active_page="data",
             rows=rows_hal, total=total,
             hal=hal, total_hal=total_hal,
             q=q, sub=sub, tahun=tahun,
             sub_list=sub_list, tahun_list=tahun_list,
             status=hasil)
    )


# ═══════════════════════════════════════════════════════════════════════════
# DETAIL & EDIT
# ═══════════════════════════════════════════════════════════════════════════
@router.get("/data/{baris}/detail")
async def data_detail(request: Request, bidang_id: str, baris: int):
    redir, ctx = _cek_akses(request, bidang_id)
    if redir:
        return redir
    spreadsheet_id = ctx["bidang"]["spreadsheet_id"]
    hasil = await run_in_threadpool(ambil_semua_data, spreadsheet_id)
    rows  = hasil.get("data", [])
    row   = next((r for r in rows if r.get("_baris") == baris), None)
    return templates.TemplateResponse(
        "bidang/partials/detail_modal.html",
        _ctx(request, bidang_id, ctx["user"], ctx["bidang"], row=row, baris=baris)
    )


@router.get("/data/{baris}/edit")
async def data_edit_form(request: Request, bidang_id: str, baris: int):
    redir, ctx = _cek_akses(request, bidang_id)
    if redir:
        return redir
    spreadsheet_id = ctx["bidang"]["spreadsheet_id"]
    hasil = await run_in_threadpool(ambil_semua_data, spreadsheet_id)
    rows  = hasil.get("data", [])
    row   = next((r for r in rows if r.get("_baris") == baris), None)
    matcher  = await run_in_threadpool(get_matcher)
    sub_list = ctx["bidang"]["sub_kegiatan"]
    return templates.TemplateResponse(
        "bidang/partials/form_edit.html",
        _ctx(request, bidang_id, ctx["user"], ctx["bidang"],
             row=row, baris=baris, sub_list=sub_list,
             matcher=matcher)
    )


@router.post("/data/{baris}/edit")
async def data_edit_simpan(request: Request, bidang_id: str, baris: int):
    redir, ctx = _cek_akses(request, bidang_id)
    if redir:
        return redir
    form = dict(await request.form())
    spreadsheet_id = ctx["bidang"]["spreadsheet_id"]
    hasil = await run_in_threadpool(update_arsip, baris, form, spreadsheet_id)
    return templates.TemplateResponse(
        "bidang/partials/edit_hasil.html",
        _ctx(request, bidang_id, ctx["user"], ctx["bidang"],
             hasil=hasil, baris=baris)
    )


# ═══════════════════════════════════════════════════════════════════════════
# HAPUS
# ═══════════════════════════════════════════════════════════════════════════
@router.get("/data/{baris}/konfirmasi-hapus")
async def hapus_konfirmasi(request: Request, bidang_id: str, baris: int):
    redir, ctx = _cek_akses(request, bidang_id)
    if redir:
        return redir
    spreadsheet_id = ctx["bidang"]["spreadsheet_id"]
    hasil = await run_in_threadpool(ambil_semua_data, spreadsheet_id)
    rows  = hasil.get("data", [])
    row   = next((r for r in rows if r.get("_baris") == baris), None)
    return templates.TemplateResponse(
        "bidang/partials/hapus_konfirmasi.html",
        _ctx(request, bidang_id, ctx["user"], ctx["bidang"],
             row=row, baris=baris)
    )


@router.post("/data/{baris}/hapus")
async def hapus_eksekusi(request: Request, bidang_id: str, baris: int):
    redir, ctx = _cek_akses(request, bidang_id)
    if redir:
        return redir
    spreadsheet_id = ctx["bidang"]["spreadsheet_id"]
    hasil = await run_in_threadpool(hapus_arsip, baris, spreadsheet_id)
    return templates.TemplateResponse(
        "bidang/partials/hapus_hasil.html",
        _ctx(request, bidang_id, ctx["user"], ctx["bidang"],
             hasil=hasil)
    )

# ═══════════════════════════════════════════════════════════════════════════
# PANDUAN
# ═══════════════════════════════════════════════════════════════════════════
@router.get("/panduan")
async def panduan_page(request: Request, bidang_id: str):
    redir, ctx = _cek_akses(request, bidang_id)
    if redir:
        return redir
    return templates.TemplateResponse(
        "bidang/panduan.html",
        _ctx(request, bidang_id, ctx["user"], ctx["bidang"], active_page="panduan")
    )

# ═══════════════════════════════════════════════════════════════════════════
# HELPER
# ═══════════════════════════════════════════════════════════════════════════
def _kandidat_kode(matcher, uraian, sub_kegiatan, kode_dari_nomor, top_n=3):
    hasil = []
    if kode_dari_nomor and kode_dari_nomor.strip():
        kode = kode_dari_nomor.strip()
        if kode in matcher.jra_map or kode in matcher.skkd_map:
            hasil.append({**matcher.get_retensi_skkd(kode),
                          "skor": 1.0, "sumber": "dari No Surat"})
    for k in matcher.cari_kandidat(uraian, sub_kegiatan=sub_kegiatan, top_n=top_n):
        if not hasil or k["kode_klasifikasi"] != hasil[0]["kode_klasifikasi"]:
            hasil.append(k)
        if len(hasil) >= top_n:
            break
    return hasil[:top_n]

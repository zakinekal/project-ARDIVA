# ARDIVA — ARsip DInamis serVice Automation

Sistem pengarsipan digital untuk DPMPD Provinsi Kalimantan Timur.
Mendukung 5 bidang dengan akses terpisah melalui Google OAuth.

---

## Teknologi

- **Backend**: FastAPI + Python
- **Frontend**: Jinja2 + htmx + Tailwind CSS
- **Database**: Google Sheets (via Apps Script)
- **Auth**: Google OAuth 2.0
- **Hosting**: Render (Docker)

---

## Setup Lokal

### 1. Install dependensi
```bash
pip install -r requirements.txt
```

### 2. Buat file .env
```bash
cp .env.example .env
```
Isi semua nilai di `.env` (lihat panduan di bawah).

### 3. Jalankan
```bash
uvicorn app:app --reload --port 8000
```

Buka `http://localhost:8000`

---

## Konfigurasi

### A. Google OAuth (Google Cloud Console)
1. Buka [console.cloud.google.com](https://console.cloud.google.com)
2. Buat project baru atau pilih yang sudah ada
3. Aktifkan **Google+ API** dan **Google Identity**
4. Buat **OAuth 2.0 Client ID** (tipe: Web Application)
5. Tambahkan Authorized Redirect URIs:
   - `http://localhost:8000/auth/callback` (untuk lokal)
   - `https://YOUR-RAILWAY-URL/auth/callback` (untuk production)
6. Tambahkan Authorized JavaScript Origins:
   - `http://localhost:8000`
   - `https://YOUR-RAILWAY-URL`
7. Salin **Client ID** dan **Client Secret** ke `.env`

### B. Apps Script (Google Sheets)
1. Buka Google Sheets milik akun Sekretariat
2. Klik **Extensions → Apps Script**
3. Salin seluruh isi `AppsScript_Kode.gs` ke editor Apps Script
4. Ganti `SECRET_TOKEN` dengan token rahasia yang sama dengan di `.env`
5. Klik **Deploy → New deployment**
   - Type: **Web App**
   - Execute as: **Me**
   - Who has access: **Anyone**
6. Salin URL deployment ke `APPS_SCRIPT_URL` di `.env`

### C. Daftarkan email & spreadsheet bidang
Buka `config.py` dan isi:
- Email resmi masing-masing bidang
- Spreadsheet ID masing-masing bidang (dari URL Google Sheets: `docs.google.com/spreadsheets/d/INI-SPREADSHEET-ID/edit`)
- Sub kegiatan masing-masing bidang (setelah diterima dari instansi)

Berikan akses **Editor** ke akun pemilik Apps Script untuk semua spreadsheet bidang.

---

## Deploy ke Render

1. Push kode ke GitHub
2. Buka [render.com](https://render.com) → Sign in with GitHub
3. Pilih **New +** → **Web Service** → repo ARDIVA
4. Render otomatis mendeteksi `Dockerfile` di root dan akan menggunakan environment **Docker**
5. Pilih plan **Free**
6. Di tab **Environment**, isi variabel dari `.env` seperti:
   - `GOOGLE_CLIENT_ID`
   - `GOOGLE_CLIENT_SECRET`
   - `SECRET_KEY`
   - `APPS_SCRIPT_URL`
   - `SECRET_TOKEN`
7. Setelah service aktif, salin URL Render yang baru dibuat dan tambahkan ke Authorized Redirect URIs di Google Cloud Console
8. Pastikan juga domain Render dipakai untuk callback login Google, misalnya: `https://<nama-app>.onrender.com/auth/callback`

---

## Struktur Project

```
app.py                      ← Titik masuk utama
config.py                   ← Konfigurasi email & spreadsheet per bidang
core.py                     ← Utilitas bersama
sheets_client.py            ← Komunikasi ke Apps Script
baca_surat.py               ← Ekstraksi teks dari PDF
matcher.py                  ← Klasifikasi kode & sub kegiatan
AppsScript_Kode.gs          ← Kode Google Apps Script
routers/
  auth.py                   ← Google OAuth login/logout
  index.py                  ← Landing page
  bidang/base.py            ← Router generik semua bidang
templates/
  index/                    ← Landing page
  auth/                     ← Halaman login
  bidang/                   ← Template semua halaman bidang
data/                       ← File JRA, SKKD, kamus dari Pergub
```

---

## Skenario Error Umum

| Error | Penyebab | Solusi |
|-------|----------|--------|
| "Google Sheets belum terhubung" | Apps Script belum dikonfigurasi | Isi APPS_SCRIPT_URL di .env |
| "Token tidak valid" | SECRET_TOKEN tidak cocok | Samakan token di .env dan AppsScript_Kode.gs |
| "Spreadsheet ID belum dikonfigurasi" | config.py belum diisi | Isi spreadsheet_id di config.py |
| Login redirect error | Redirect URI tidak terdaftar | Tambahkan URL ke Google Cloud Console |
| Railway sleep | Trial $5 habis | Upgrade plan atau redeploy |

---

## Tim Pengembang

ARDIVA dikembangkan oleh mahasiswa PKL Teknik Informatika UMKT  
di DPMPD Provinsi Kalimantan Timur — 2026

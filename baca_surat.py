#baca_surat.py
"""
baca_surat.py
Ekstraksi data mentah (No Surat, Tanggal, Pengirim, Kode Klas, Uraian) dari file PDF surat masuk.
Support untuk PDF digital dan PDF hasil scan (OCR otomatis).
"""
import os
import re
from datetime import datetime
import pdfplumber
import cv2
import numpy as np
from PIL import Image
import io
import logging

# Setup logging
logger = logging.getLogger(__name__)

# Lazy load OCR reader (load hanya saat diperlukan)
_ocr_reader = None

def _get_ocr_reader():
    """Lazy load EasyOCR reader untuk bahasa Indonesia."""
    global _ocr_reader
    if _ocr_reader is None:
        try:
            import easyocr
            logger.info("Loading EasyOCR model for Indonesian language...")
            _ocr_reader = easyocr.Reader(['id'], gpu=False)
        except ImportError:
            logger.error("EasyOCR not installed. Install with: pip install easyocr")
            return None
    return _ocr_reader

MONTHS = {
    "januari": 1, "februari": 2, "maret": 3, "april": 4, "mei": 5, "juni": 6,
    "juli": 7, "agustus": 8, "september": 9, "oktober": 10, "november": 11, "desember": 12,
}

# ---------------------------------------------------------------------------
# LAPISAN 0: Deteksi dan OCR untuk surat hasil scan
#
# Jika PDF tidak memiliki text layer (hasil scan), sistem akan:
# 1. Ekstrak setiap halaman sebagai gambar
# 2. Lakukan preprocessing gambar (kontras, brightness)
# 3. Gunakan EasyOCR untuk ekstrak teks
# 4. Gabungkan teks dari semua halaman
# ---------------------------------------------------------------------------

def _has_text_layer(pdf_path):
    """
    Deteksi apakah PDF memiliki text layer (teks digital).
    Return True jika text tersedia, False jika hanya gambar (scan).
    """
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for halaman in pdf.pages:
                # Jika ada character objects dengan 'size' > 0, berarti ada text layer
                if halaman.chars:
                    teks = halaman.extract_text()
                    if teks and len(teks.strip()) > 50:  # threshold minimal teks
                        return True
        return False
    except Exception as e:
        logger.warning(f"Error saat deteksi text layer: {e}")
        return False


def _preprocess_image(image_cv):
    """
    Preprocessing gambar untuk meningkatkan kualitas OCR:
    - Grayscale conversion
    - Contrast/brightness adjustment
    - Denoising
    """
    try:
        # Convert ke grayscale jika masih color
        if len(image_cv.shape) == 3:
            gray = cv2.cvtColor(image_cv, cv2.COLOR_BGR2GRAY)
        else:
            gray = image_cv
        
        # Improve contrast dengan CLAHE (Contrast Limited Adaptive Histogram Equalization)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)
        
        # Denoise
        denoised = cv2.fastNlMeansDenoising(enhanced, None, h=10, templateWindowSize=7, searchWindowSize=21)
        
        return denoised
    except Exception as e:
        logger.warning(f"Error preprocessing image: {e}")
        return image_cv if len(image_cv.shape) == 2 else cv2.cvtColor(image_cv, cv2.COLOR_BGR2GRAY)


def _extract_text_via_ocr(pdf_path):
    """
    Ekstrak teks dari PDF scan menggunakan EasyOCR.
    Return tuple (teks_lengkap, jumlah_halaman).
    """
    try:
        reader = _get_ocr_reader()
        if reader is None:
            return "", 0
        
        teks_semua_halaman = []
        halaman_count = 0
        
        with pdfplumber.open(pdf_path) as pdf:
            halaman_count = len(pdf.pages)
            
            for idx, halaman in enumerate(pdf.pages):
                logger.info(f"OCR processing halaman {idx + 1}/{halaman_count}...")
                
                # Convert halaman PDF ke image
                try:
                    image = halaman.to_image(resolution=300)
                    image_np = np.array(image)
                    
                    # Preprocessing
                    image_processed = _preprocess_image(image_np)
                    
                    # OCR
                    results = reader.readtext(image_processed, detail=0)  # detail=0 untuk hanya teks
                    
                    # Gabungkan baris
                    if results:
                        teks_halaman = "\n".join(results)
                        teks_semua_halaman.append(teks_halaman)
                        logger.info(f"Halaman {idx + 1} OCR berhasil, {len(results)} baris teks ditemukan")
                    else:
                        logger.warning(f"Halaman {idx + 1} tidak ada teks yang terdeteksi")
                        
                except Exception as e:
                    logger.error(f"Error OCR halaman {idx + 1}: {e}")
                    continue
        
        teks_lengkap = "\n".join(teks_semua_halaman).strip()
        return teks_lengkap, halaman_count
        
    except Exception as e:
        logger.error(f"Error extract text via OCR: {e}")
        return "", 0

# ---------------------------------------------------------------------------
# LAPISAN 1: pembersih artefak template merge-field (mis. e-sign/DOCX->PDF)
#
# Beberapa sistem persuratan (khususnya hasil e-sign) menghasilkan PDF di mana
# nilai asli field dinamis (tanggal, nomor surat, sifat, dst.) dirender TEPAT
# di posisi yang sama dengan placeholder mentahnya yang belum ter-replace,
# mis. "${tanggal_naskah}", hanya beda font/layer. pdfplumber mengurutkan
# karakter satu baris murni berdasarkan posisi X, sehingga dua string yang
# bertumpuk itu ke-interleave karakter-per-karakter dan jadi teks acak
# (mis. "Samarinda, $1{5t aJnuglig 2a0l_2n6askah}").
#
# Strategi: kelompokkan karakter per baris (toleransi posisi Y), lalu per
# font dalam baris yang sama. Kalau teks salah satu font-run di baris itu
# cocok pola "${nama_variabel}", buang HANYA span karakter placeholder itu
# (bukan seluruh baris/font), sisanya (nilai asli + teks statis lain di
# baris yang sama) dibiarkan utuh sehingga baris tetap bisa direkonstruksi
# secara normal oleh pdfplumber setelahnya.
# ---------------------------------------------------------------------------

_POLA_PLACEHOLDER = re.compile(r"\$\{[A-Za-z_][A-Za-z0-9_]*\}")


def _kelompokkan_baris(chars, toleransi=2.5):
    """Kelompokkan karakter yang posisi 'top'-nya berdekatan jadi satu baris kasar."""
    chars_terurut = sorted(chars, key=lambda c: c["top"])
    baris_list = []
    for c in chars_terurut:
        ditempatkan = False
        for baris in baris_list:
            if abs(baris[0]["top"] - c["top"]) <= toleransi:
                baris.append(c)
                ditempatkan = True
                break
        if not ditempatkan:
            baris_list.append([c])
    return baris_list


def _bersihkan_karakter_placeholder(chars):
    """
    Dari seluruh karakter satu halaman, kembalikan daftar karakter dengan
    span '${...}' yang bertumpuk di baris yang sama dengan konten lain
    sudah dibuang. Aman dipanggil pada halaman tanpa masalah ini sekalipun
    (tidak akan mengubah apa-apa jika tidak ada tumpang tindih font).
    """
    id_dibuang = set()
    for baris in _kelompokkan_baris(chars):
        per_font = {}
        for c in baris:
            per_font.setdefault(c["fontname"], []).append(c)
        if len(per_font) < 2:
            continue  # baris normal, cuma 1 layer font -> tidak mungkin tumpang tindih
        for font, fchars in per_font.items():
            fchars_terurut = sorted(fchars, key=lambda c: c["x0"])
            # Guard: kalau ada unit karakter multi-huruf (ligature dsb.),
            # index string tidak 1:1 dengan index list -> lewati span-removal
            # halus, buang seluruh font-run ini saja demi keamanan jika
            # run itu murni placeholder (tidak ada teks lain tercampur).
            multi_char = any(len(c["text"]) != 1 for c in fchars_terurut)
            teks = "".join(c["text"] for c in fchars_terurut)
            if multi_char:
                if _POLA_PLACEHOLDER.fullmatch(teks.strip()):
                    id_dibuang.update(id(c) for c in fchars_terurut)
                continue
            for m in _POLA_PLACEHOLDER.finditer(teks):
                for c in fchars_terurut[m.start():m.end()]:
                    id_dibuang.add(id(c))
    return [c for c in chars if id(c) not in id_dibuang]


def extract_text_from_pdf(path_pdf):
    """
    Ekstrak teks dari PDF dengan deteksi otomatis:
    - Coba baca teks digital dulu (fast path)
    - Jika gagal atau minimal, fallback ke OCR (slow path)
    
    Return tuple (teks, halaman_count).
    """
    teks, halaman_count = [], 0
    butuh_ocr = False
    
    try:
        with pdfplumber.open(path_pdf) as pdf:
            halaman_count = len(pdf.pages)
            for halaman in pdf.pages:
                chars_asli = halaman.chars
                # Fast path: kalau tidak ada indikasi placeholder mentah sama
                # sekali di halaman ini, tidak perlu proses tambahan.
                if not any(c["text"] == "$" for c in chars_asli):
                    halaman_teks = halaman.extract_text()
                else:
                    chars_bersih = _bersihkan_karakter_placeholder(chars_asli)
                    id_simpan = {id(c) for c in chars_bersih}
                    halaman_bersih = halaman.filter(
                        lambda obj: obj.get("object_type") != "char" or id(obj) in id_simpan
                    )
                    halaman_teks = halaman_bersih.extract_text()
                if halaman_teks:
                    teks.append(halaman_teks)
    except Exception as e:
        logger.warning(f"Error extracting digital text from PDF: {e}")
        butuh_ocr = True
    
    teks_hasil = "\n".join(teks).strip()
    
    # Jika teks sangat minimal (< 100 karakter), kemungkinan hasil scan
    if len(teks_hasil) < 100:
        logger.info("Teks minimal terdeteksi, mencoba OCR...")
        butuh_ocr = True
        teks_ocr, halaman_count = _extract_text_via_ocr(path_pdf)
        if teks_ocr:
            teks_hasil = teks_ocr
            butuh_ocr = False
        else:
            butuh_ocr = True
    
    return teks_hasil, halaman_count, butuh_ocr


# ---------------------------------------------------------------------------
# LAPISAN 2: sanitasi terakhir pada nilai field hasil parsing.
#
# Jaring pengaman kalau suatu saat ada pola korupsi lain (font tak dikenal,
# placeholder dengan sintaks beda, dsb.) yang lolos dari Lapisan 1: setiap
# field akhir tetap disaring dari sisa karakter '$ { }' dan spasi ganda yang
# tidak wajar sebelum dikembalikan ke caller.
# ---------------------------------------------------------------------------

def _sanitasi_field(value):
    if not value:
        return value
    if re.search(r"\$\{|\}", value):
        value = re.sub(r"\$\{[^}]*\}?", "", value)
        value = re.sub(r"[\{\}\$]", "", value)
    value = re.sub(r"\s{2,}", " ", value).strip()
    return value


def normalize_date(value):
    value = value.strip().lower().replace('.', '/')
    value = re.sub(r"\s+", " ", value)

    match = re.search(r"(\d{1,2})[\/\-\s]+(\d{1,2}|[a-z]+)[\/\-\s]+(\d{2,4})", value)
    if match:
        day, month_raw, year = match.groups()
        year = year if len(year) == 4 else ("20" + year if len(year) == 2 else year)
        month = int(month_raw) if month_raw.isdigit() else MONTHS.get(month_raw)
        if month:
            try:
                return datetime(int(year), int(month), int(day)).strftime("%d/%m/%Y")
            except Exception:
                pass

    match = re.search(r"(\d{1,2})\s+([a-z]+)\s+(\d{4})", value)
    if match:
        day, month_name, year = match.groups()
        month = MONTHS.get(month_name)
        if month:
            try:
                return datetime(int(year), month, int(day)).strftime("%d/%m/%Y")
            except Exception:
                pass
    return ""


def clean_text(value):
    if not value:
        return ""
    value = re.sub(r"[\s\n\r]+$", "", value.strip())
    return re.sub(r"[\.,;:]+$", "", value)


def find_no_surat(text):
    lines = text.splitlines()
    for i, line in enumerate(lines):
        # Hanya anggap ini baris field "Nomor" kalau kata "Nomor" ada di AWAL
        # baris (setelah spasi/tab). Ini untuk menghindari salah tangkap kata
        # "Nomor" yang muncul di tengah kalimat lain, misalnya pada alamat di
        # kop surat: "Jalan Gajah Mada Nomor 2, Samarinda, ..." - di situ kata
        # "Nomor" bukan label field, melainkan bagian dari nama jalan.
        if not re.match(r"^\s*nomor\b", line, re.IGNORECASE):
            continue

        m = re.search(r"(?:Nomor\s*(?:Surat)?\s*[:\-]?\s*)(.+)", line, re.IGNORECASE)
        candidate = m.group(1).strip() if m and m.group(1) else ""
        candidate = candidate.lstrip(": \t-")

        j = i + 1
        while not candidate and j < len(lines):
            nxt = lines[j].strip()
            if nxt:
                candidate = nxt
                j += 1
                break
            j += 1

        merge_count = 0
        while j < len(lines) and merge_count < 2:
            nxt = lines[j].strip()
            if not nxt:
                break
            if candidate.endswith('/') or nxt.startswith('/'):
                candidate = candidate.rstrip('/') + '/' + nxt.lstrip('/')
                j += 1
                merge_count += 1
            else:
                break

        candidate = re.sub(r"[\s\.,;:]+$", "", candidate)

        if not candidate:
            continue
        # Nomor surat asli tidak pernah mengandung spasi di tengah kode -
        # kalau lolos dari Lapisan 1 masih ada spasi nyasar antar
        # token yang jelas menyambung (huruf/angka|/), rapatkan dulu
        # sebelum divalidasi, supaya tidak salah terpotong di bawah.
        candidate_rapat = re.sub(r"(?<=[A-Za-z0-9/.\-])\s+(?=[A-Za-z0-9])", "", candidate)
        if re.match(r"^[0-9A-Za-z\./\-]+$", candidate_rapat):
            candidate = candidate_rapat

        if " " not in candidate:
            return _sanitasi_field(candidate)
        candidate_aman = candidate.split(" ")[0].strip("/.,;:")
        if candidate_aman:
            return _sanitasi_field(candidate_aman)

    m = re.search(r"\b[0-9]+(?:\.[0-9]+)*/[0-9]+/[A-Za-z0-9\-]+/\d{4}\b", text)
    if m:
        return _sanitasi_field(clean_text(m.group(0)))
    m = re.search(r"\b[0-9A-Za-z\./\-]+/\d{4}\b", text)
    if m:
        return _sanitasi_field(clean_text(m.group(0)))
    return "TIDAK ADA NOMOR"


BULAN = r"(?:januari|februari|maret|april|mei|juni|juli|agustus|september|oktober|november|desember)"
_KOTA_TGL_TEKS = re.compile(rf"^[A-Za-z\s]+(?:,\s*|\s+)(\d{{1,2}}\s+{BULAN}\s+\d{{4}})$", re.IGNORECASE)
_KOTA_TGL_ANGKA = re.compile(r"^[A-Za-z\s]+(?:,\s*|\s+)(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4})$", re.IGNORECASE)
_KOTA_TGL_BLOK = re.compile(
    rf"(?im)([A-Za-z][A-Za-z\s]{{1,40}})(?:,|\s+)(\d{{1,2}}\s+{BULAN}\s+\d{{4}}|\d{{1,2}}[\/\-]\d{{1,2}}[\/\-]\d{{2,4}})",
    re.IGNORECASE,
)
_TGL_TEKS = re.compile(rf"\b(\d{{1,2}}\s+{BULAN}\s+\d{{4}})\b", re.IGNORECASE)
_TGL_ANGKA = re.compile(r"\b(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}|\d{1,2}\s+\d{1,2}\s+\d{2,4})\b")

_PENANDA_RUJUKAN = re.compile(
    r"(menindaklanjuti|sehubungan\s+dengan|berdasarkan\s+surat|sesuai\s+(?:dengan\s+)?surat|"
    r"merujuk\s+(?:pada\s+)?surat|memperhatikan\s+surat|"
    r"surat\s+[^\n]{0,120}?\bnomor\b[^\n]{0,120}?\btanggal\b)",
    re.IGNORECASE,
)

_PENANDA_BODI = re.compile(
    r"^(?:menindaklanjuti|sehubungan\s+dengan|berdasarkan|sesuai\s+(?:dengan\s+)?surat|"
    r"merujuk\s+(?:pada\s+)?surat|memperhatikan\s+surat|demikian|dengan\s+hormat)",
    re.IGNORECASE,
)


def _cari_kota_tanggal(lines):
    for line in lines:
        line = line.strip()
        m = _KOTA_TGL_TEKS.match(line)
        if m:
            return normalize_date(m.group(1))
        m = _KOTA_TGL_ANGKA.match(line)
        if m:
            return normalize_date(m.group(1))
    return None


def _cari_kota_tanggal_blok(text):
    m = _KOTA_TGL_BLOK.search(text)
    if m:
        return normalize_date(m.group(2))
    return None


def _cari_tanggal_header_blok(text):
    for line in text.splitlines()[:25]:
        line = re.sub(r"\s+", " ", line.strip())
        if not line:
            continue
        if re.match(r"^(\d+|nomor|tanggal|tgl|hal|perihal|kepada|yth\.?|dari|di\s+tempat|lampiran)", line, re.IGNORECASE):
            continue
        m = re.search(r"\b(\d{1,2}\s+[A-Za-z]+\s+\d{4}|\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}|\d{1,2}\s+\d{1,2}\s+\d{2,4})\b", line)
        if m:
            return normalize_date(m.group(1))
    return None


def _cari_tanggal_label(lines):
    for line in lines:
        stripped = re.sub(r"\s+", " ", line.strip())
        if _PENANDA_BODI.match(stripped):
            continue
        m = re.search(
            r"\b(?:tanggal|tgl)\b\s*[:\-]?\s*(\d{1,2}\s+[A-Za-z]+\s+\d{4}|\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}|\d{1,2}\s+\d{1,2}\s+\d{2,4})",
            stripped,
            re.IGNORECASE,
        )
        if m:
            return normalize_date(m.group(1))
    return None


def _cari_tanggal_bebas(text, filter_rujukan=False):
    hasil = []
    for pattern in (_TGL_TEKS, _TGL_ANGKA):
        for m in pattern.finditer(text):
            window = text[max(0, m.start() - 220):min(len(text), m.end() + 220)]
            if filter_rujukan and _PENANDA_RUJUKAN.search(window):
                continue
            tanggal = normalize_date(m.group(1))
            if tanggal:
                hasil.append(tanggal)
    return hasil[0] if hasil else None


def _score_tanggal_candidate(line, is_header=False, is_tail=False):
    score = 0
    stripped = re.sub(r"\s+", " ", line.strip())
    if not stripped:
        return score
    if re.search(r"\b(?:tanggal|tgl)\b", stripped, re.IGNORECASE):
        score += 40
    if re.search(r"^[A-Za-z\s]+(?:,|\s+)\d{1,2}\s+[A-Za-z]+\s+\d{4}$", stripped, re.IGNORECASE):
        score += 60
    if is_header:
        score += 30
    if is_tail:
        score -= 10
    if _PENANDA_RUJUKAN.search(stripped):
        score -= 80
    return score


def find_tanggal(text):
    lines = text.splitlines()

    hasil = _cari_kota_tanggal(lines)
    if hasil:
        return hasil

    idx_salam = len(lines)
    for i, line in enumerate(lines):
        stripped = line.strip()
        if re.match(r"^(Yth\.?|Kepada|Menindaklanjuti|Sehubungan\s+dengan|Berdasarkan|Sesuai\s+(?:dengan\s+)?surat|Demikian|Dengan\s+hormat)\b", stripped, re.IGNORECASE):
            idx_salam = i
            break

    teks_kepala = "\n".join(lines[:idx_salam]) if idx_salam < len(lines) else "\n".join(lines[:min(25, len(lines))])
    head_lines = teks_kepala.splitlines()

    candidates = []
    for idx, line in enumerate(head_lines[:30]):
        stripped = re.sub(r"\s+", " ", line.strip())
        if not stripped:
            continue
        if _PENANDA_BODI.match(stripped):
            break
        score = _score_tanggal_candidate(stripped, is_header=True)
        if score <= 0:
            continue
        m = re.search(r"\b(\d{1,2}\s+[A-Za-z]+\s+\d{4}|\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}|\d{1,2}\s+\d{1,2}\s+\d{2,4})\b", stripped)
        if not m:
            continue
        tanggal = normalize_date(m.group(1))
        if tanggal:
            candidates.append((score, tanggal, stripped))

    if candidates:
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1]

    hasil = _cari_kota_tanggal_blok(teks_kepala)
    if hasil:
        return hasil

    hasil = _cari_tanggal_header_blok(teks_kepala)
    if hasil:
        return hasil

    hasil = _cari_tanggal_bebas(teks_kepala, filter_rujukan=False)
    if hasil:
        return hasil

    hasil = _cari_tanggal_label(head_lines)
    if hasil:
        return hasil

    baris_akhir = lines[-25:]
    tail_candidates = []
    for idx, line in enumerate(baris_akhir):
        stripped = re.sub(r"\s+", " ", line.strip())
        if not stripped:
            continue
        score = _score_tanggal_candidate(stripped, is_tail=True)
        if score <= 0:
            continue
        m = re.search(r"\b(\d{1,2}\s+[A-Za-z]+\s+\d{4}|\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}|\d{1,2}\s+\d{1,2}\s+\d{2,4})\b", stripped)
        if not m:
            continue
        tanggal = normalize_date(m.group(1))
        if tanggal:
            tail_candidates.append((score, tanggal, stripped))

    if tail_candidates:
        tail_candidates.sort(key=lambda item: item[0], reverse=True)
        return tail_candidates[0][1]

    hasil = _cari_tanggal_bebas(text, filter_rujukan=True)
    if hasil:
        return hasil

    return ""


def find_pengirim(text):
    m = re.search(r"\b(?:Pengirim|Dari)\b\s*[:\-]\s*(.+?)\n", text, re.IGNORECASE)
    if m:
        return _sanitasi_field(clean_text(m.group(1)))

    def is_non_sender_line(line: str) -> bool:
        if re.search(r"^(surat|nomor|tanggal|lampiran|hal|perihal|kepada|dari|pada|yt[hj]|di\s+tempat|kepala|instansi|desa|bapak|ibu)", line, re.IGNORECASE):
            return True
        if re.search(r"^[A-Za-z\s]+,\s*\d{1,2}\s+(?:januari|februari|maret|april|mei|juni|juli|agustus|september|oktober|november|desember)\s+\d{4}$", line, re.IGNORECASE):
            return True
        if re.search(r"^[A-Za-z\s]+,\s*\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}$", line):
            return True
        if re.search(r"^\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}$", line):
            return True
        if re.search(r"^\d+$", line):
            return True
        return False

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    candidates = [line for line in lines if not is_non_sender_line(line)]

    def bersihkan_kurung(line: str) -> str:
        return _sanitasi_field(clean_text(re.sub(r"\s*\([^)]*\)\s*$", "", line)))

    def terlihat_seperti_alamat(line: str) -> bool:
        return bool(re.search(r"\b(jl\.?|jalan|no\.?\s*\d|rt\.?\s*\d|rw\.?\s*\d|kec\.?|kel\.?)\b", line, re.IGNORECASE))

    if candidates:
        if not terlihat_seperti_alamat(candidates[0]):
            for line in candidates[:6]:
                if re.search(r"\b(pemerintah|provinsi|kabupaten|kota|desa|sekretariat|departemen|din[as]|kantor|badan|instansi)\b", line, re.IGNORECASE) and not terlihat_seperti_alamat(line):
                    return bersihkan_kurung(line)
            return bersihkan_kurung(candidates[0])
        for line in candidates[:6]:
            if re.search(r"\b(pemerintah|provinsi|kabupaten|kota|desa|sekretariat|departemen|din[as]|kantor|badan|instansi)\b", line, re.IGNORECASE) and not terlihat_seperti_alamat(line):
                return bersihkan_kurung(line)
        return bersihkan_kurung(candidates[0])

    return ""


def find_perihal(text):
    lines = text.splitlines()
    for i, line in enumerate(lines):
        m = re.search(r"\b(?:Perihal|Hal)\b\s*[:\-]\s*(.+)", line, re.IGNORECASE)
        if not m or not m.group(1).strip():
            continue
        hasil = m.group(1).strip()

        j = i + 1
        while j < len(lines):
            nxt = lines[j].strip()
            if not nxt:
                break
            kalimat_baru = re.match(
                r"^(Yth\.?|Kepada|di\s+Tempat|Sehubungan|Dalam\s+rangka|Berdasarkan|Demikian)",
                nxt, re.IGNORECASE
            )
            if ":" in nxt or len(nxt) > 40 or kalimat_baru or hasil.endswith((')', '.', ';')):
                break
            hasil = hasil + " " + nxt
            j += 1
            break

        return _sanitasi_field(clean_text(hasil))

    for baris in text.splitlines():
        if re.search(r"\b(?:perihal|hal)\b", baris, re.IGNORECASE):
            return _sanitasi_field(clean_text(re.sub(r"^(?:perihal|hal)\s*[:\-]?\s*", "", baris, flags=re.IGNORECASE)))
    return ""


def find_kode_klas(no_surat, text):
    if not no_surat or no_surat == "TIDAK ADA NOMOR":
        return ""
    candidate = no_surat.split('/')[0].strip()
    if re.match(r"^[0-9]+(?:\.[0-9]+)+$", candidate):
        return clean_text(candidate)
    return ""


def find_uraian(text):
    lines = [b.strip() for b in text.splitlines() if b.strip()]
    return lines[0][:200] if lines else ""


def find_jumlah(text, pages):
    m = re.search(r"Lampiran\s*[:\-]?\s*(\d+)\s*(?:\([^)]*\))?\s*([A-Za-z]+)?", text, re.IGNORECASE)
    if m:
        angka, satuan = m.group(1), (m.group(2) or "").lower()
        if satuan in ("lembar", "halaman", "hal"):
            return angka
    if pages:
        return str(pages)
    m = re.search(r"(\d+)\s*(?:halaman|lembar)", text, re.IGNORECASE)
    return m.group(1) if m else ""


def ekstrak_surat(path_pdf):
    """Ekstrak semua field mentah dari satu file PDF surat masuk."""
    text, pages, butuh_ocr = extract_text_from_pdf(path_pdf)
    if not text:
        pesan_error = "Gagal ekstrak teks"
        if butuh_ocr:
            pesan_error += " - OCR diperlukan tapi model tidak tersedia/gagal"
        return {
            "no_surat": "TIDAK ADA NOMOR", "tanggal_surat": "", "pengirim": "",
            "perihal": "", "uraian_arsip": pesan_error,
            "jumlah": str(pages or ""), "kode_klas": "", "teks_lengkap": "", "butuh_ocr": butuh_ocr,
        }
    no_surat = find_no_surat(text)
    perihal = find_perihal(text)
    return {
        "no_surat": no_surat,
        "tanggal_surat": find_tanggal(text),
        "pengirim": find_pengirim(text),
        "perihal": perihal,
        "uraian_arsip": perihal or find_uraian(text),
        "jumlah": find_jumlah(text, pages),
        "kode_klas": find_kode_klas(no_surat, text),
        "teks_lengkap": text,
        "butuh_ocr": butuh_ocr,
    }
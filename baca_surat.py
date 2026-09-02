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
import pytesseract


def _resolve_tesseract_binary():
    """Temukan lokasi binari Tesseract yang terinstal di Windows."""
    candidates = []

    env_path = os.environ.get("PATH", "")
    for entry in env_path.split(os.pathsep):
        if not entry:
            continue
        candidates.append(os.path.join(entry, "tesseract.exe"))

    candidates.extend([
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ])

    seen = set()
    for candidate in candidates:
        normalized = os.path.normpath(candidate)
        if normalized not in seen and os.path.exists(normalized):
            seen.add(normalized)
            return normalized
    return None


_TESSERACT_BIN = _resolve_tesseract_binary()
if _TESSERACT_BIN:
    pytesseract.pytesseract.tesseract_cmd = _TESSERACT_BIN
    os.environ["PATH"] = os.path.dirname(_TESSERACT_BIN) + os.pathsep + os.environ.get("PATH", "")

logger = logging.getLogger(__name__)

_ocr_reader = None

def _get_ocr_reader():
    """Lazy load Tesseract OCR backend untuk bahasa Indonesia."""
    global _ocr_reader
    if _ocr_reader is None:
        try:
            if _TESSERACT_BIN:
                pytesseract.pytesseract.tesseract_cmd = _TESSERACT_BIN
            pytesseract.get_tesseract_version()
            logger.info("Tesseract OCR backend detected and ready.")
            _ocr_reader = "tesseract"
        except Exception as exc:
            logger.error(f"Tesseract not installed or not on PATH. Install Tesseract OCR and retry. Error: {exc}")
            return None
    return _ocr_reader

MONTHS = {
    "januari": 1, "februari": 2, "maret": 3, "april": 4, "mei": 5, "juni": 6,
    "juli": 7, "agustus": 8, "september": 9, "oktober": 10, "november": 11, "desember": 12,
}

def _has_text_layer(pdf_path):
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for halaman in pdf.pages:
                if halaman.chars:
                    teks = halaman.extract_text()
                    if teks and len(teks.strip()) > 50:
                        return True
        return False
    except Exception as e:
        logger.warning(f"Error saat deteksi text layer: {e}")
        return False


def _preprocess_image(image_cv):
    try:
        if len(image_cv.shape) == 3:
            gray = cv2.cvtColor(image_cv, cv2.COLOR_BGR2GRAY)
        else:
            gray = image_cv
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)
        denoised = cv2.fastNlMeansDenoising(enhanced, None, h=10, templateWindowSize=7, searchWindowSize=21)
        return denoised
    except Exception as e:
        logger.warning(f"Error preprocessing image: {e}")
        return image_cv if len(image_cv.shape) == 2 else cv2.cvtColor(image_cv, cv2.COLOR_BGR2GRAY)


def _extract_text_via_ocr(pdf_path):
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
                try:
                    image = halaman.to_image(resolution=300)
                    # PENTING: halaman.to_image() mengembalikan objek wrapper
                    # pdfplumber.display.PageImage, BUKAN gambar mentah/piksel.
                    # np.array(image) langsung menghasilkan array KOSONG
                    # (shape=(), dtype=object) yang cuma membungkus objeknya,
                    # bukan piksel gambarnya. Harus ambil .original dulu (PIL
                    # Image asli di dalamnya) baru dikonversi ke numpy array.
                    # Tanpa ini, _preprocess_image() dan OCR di bawah selalu
                    # gagal - tapi gagalnya KETELAN diam-diam oleh try/except
                    # per halaman, sehingga hasil akhirnya cuma teks kosong
                    # tanpa exception yang kelihatan ke pemanggil.
                    image_np = np.array(image.original)

                    image_processed = _preprocess_image(image_np)

                    pil_image = Image.fromarray(image_processed)
                    config = "--psm 6"
                    hasil = pytesseract.image_to_string(pil_image, config=config)

                    if hasil and hasil.strip():
                        teks_semua_halaman.append(hasil.strip())
                        logger.info(f"Halaman {idx + 1} OCR berhasil, teks terdeteksi via Tesseract")
                    else:
                        logger.warning(f"Halaman {idx + 1} tidak ada teks yang terdeteksi oleh Tesseract")

                except Exception as e:
                    logger.error(f"Error OCR halaman {idx + 1}: {e}")
                    continue

        teks_lengkap = "\n".join(teks_semua_halaman).strip()
        return teks_lengkap, halaman_count

    except Exception as e:
        logger.error(f"Error extract text via OCR: {e}")
        return "", 0

_POLA_PLACEHOLDER = re.compile(r"\$\{[A-Za-z_][A-Za-z0-9_]*\}")


def _kelompokkan_baris(chars, toleransi=2.5):
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
    id_dibuang = set()
    for baris in _kelompokkan_baris(chars):
        per_font = {}
        for c in baris:
            per_font.setdefault(c["fontname"], []).append(c)
        if len(per_font) < 2:
            continue
        for font, fchars in per_font.items():
            fchars_terurut = sorted(fchars, key=lambda c: c["x0"])
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
    teks, halaman_count = [], 0
    butuh_ocr = False

    try:
        with pdfplumber.open(path_pdf) as pdf:
            halaman_count = len(pdf.pages)
            for halaman in pdf.pages:
                chars_asli = halaman.chars
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
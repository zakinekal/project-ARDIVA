#baca_surat.py
"""
baca_surat.py
Ekstraksi data mentah (No Surat, Tanggal, Pengirim, Kode Klas, Uraian) dari file PDF surat masuk.
Hanya baca teks digital (belum termasuk OCR untuk surat hasil scan - lihat catatan di README).
"""
import os
import re
from datetime import datetime
import pdfplumber

MONTHS = {
    "januari": 1, "februari": 2, "maret": 3, "april": 4, "mei": 5, "juni": 6,
    "juli": 7, "agustus": 8, "september": 9, "oktober": 10, "november": 11, "desember": 12,
}


def extract_text_from_pdf(path_pdf):
    teks, halaman_count = [], 0
    try:
        with pdfplumber.open(path_pdf) as pdf:
            halaman_count = len(pdf.pages)
            for halaman in pdf.pages:
                halaman_teks = halaman.extract_text()
                if halaman_teks:
                    teks.append(halaman_teks)
    except Exception as e:
        print(f"[ERROR EXTRACT PDF]: {e}")
    return "\n".join(teks).strip(), halaman_count


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
        if not re.search(r"\bnomor\b", line, re.IGNORECASE):
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
        if " " not in candidate:
            return candidate
        candidate_aman = candidate.split(" ")[0].strip("/.,;:")
        if candidate_aman:
            return candidate_aman

    m = re.search(r"\b[0-9]+(?:\.[0-9]+)*/[0-9]+/[A-Za-z0-9\-]+/\d{4}\b", text)
    if m:
        return clean_text(m.group(0))
    m = re.search(r"\b[0-9A-Za-z\./\-]+/\d{4}\b", text)
    if m:
        return clean_text(m.group(0))
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
    """
    Strategi berlapis:
    1. Pola baku "Kota, tanggal" - di baris manapun.
    2. Label "Tanggal/Tgl" di kepala surat - sangat penting untuk file hasil scan
       yang teksnya terpotong atau teracak.
    3. Tanggal polos tanpa nama kota, HANYA di kepala surat (sebelum Yth./Kepada).
    4. Blok tanda tangan (25 baris terakhir dokumen).
    5. Upaya terakhir: seluruh teks, tetap menyaring tanggal berkonteks rujukan.
    """
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
        return clean_text(m.group(1))

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
        return clean_text(re.sub(r"\s*\([^)]*\)\s*$", "", line))

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

        return clean_text(hasil)

    for baris in text.splitlines():
        if re.search(r"\b(?:perihal|hal)\b", baris, re.IGNORECASE):
            return clean_text(re.sub(r"^(?:perihal|hal)\s*[:\-]?\s*", "", baris, flags=re.IGNORECASE))
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
    text, pages = extract_text_from_pdf(path_pdf)
    if not text:
        return {
            "no_surat": "TIDAK ADA NOMOR", "tanggal_surat": "", "pengirim": "",
            "perihal": "", "uraian_arsip": "Tidak dapat mengekstrak teks - kemungkinan hasil scan/gambar.",
            "jumlah": str(pages or ""), "kode_klas": "", "teks_lengkap": "", "butuh_ocr": True,
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
        "butuh_ocr": False,
    }
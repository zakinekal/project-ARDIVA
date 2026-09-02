from matcher import KlasifikasiMatcher


def test_skkd_uses_terbuka_tertutup_and_removes_akses_field():
    matcher = object.__new__(KlasifikasiMatcher)
    matcher.jra_map = {
        "100.1": {"retensi_aktif": "2 tahun", "retensi_inaktif": "5 tahun", "keterangan": "Dokumen"},
        "101.1": {"retensi_aktif": "2 tahun", "retensi_inaktif": "5 tahun", "keterangan": "Dokumen"},
    }
    matcher.skkd_map = {
        "100.1": {"klasifikasi_keamanan": "Biasa", "hak_akses": "Internal", "unit_pengolah": "Bagian A"},
        "101.1": {"klasifikasi_keamanan": "Terbatas", "hak_akses": "Internal", "unit_pengolah": "Bagian A"},
    }
    matcher.docs_original = {"100.1": "Dokumen", "101.1": "Dokumen"}

    terbuka = matcher.get_retensi_skkd("100.1")
    tertutup = matcher.get_retensi_skkd("101.1")

    assert terbuka["klasifikasi_keamanan"] == "TERBUKA"
    assert tertutup["klasifikasi_keamanan"] == "TERTUTUP"
    assert "klasifikasi_akses" not in terbuka
    assert "klasifikasi_akses" not in tertutup

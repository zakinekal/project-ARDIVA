from pathlib import Path

from routers.bidang.base import _normalize_kategori_arsip, _normalize_kondisi_arsip


def test_input_manual_allows_manual_typing_for_key_fields():
    html = Path("templates/bidang/input_manual.html").read_text(encoding="utf-8")

    assert 'name="keterangan_jra"' in html
    assert 'name="skkd"' in html
    assert 'name="tk_perkembangan"' in html
    assert 'name="kondisi_arsip"' in html
    assert 'name="kategori_arsip"' in html

    for field_name, list_id in [
        ("keterangan_jra", "keterangan-options"),
        ("skkd", "skkd-options"),
        ("tk_perkembangan", "tk-options"),
        ("kondisi_arsip", "kondisi-options"),
        ("kategori_arsip", "kategori-options"),
    ]:
        assert f'name="{field_name}"' in html
        assert f'list="{list_id}"' in html
        assert f'id="{list_id}"' in html


def test_dashboard_value_normalization_handles_case_and_whitespace():
    assert _normalize_kategori_arsip("Surat Masuk ") == "Surat Masuk"
    assert _normalize_kategori_arsip("surat keluar") == "Surat Keluar"
    assert _normalize_kondisi_arsip(" baik ") == "BAIK"
    assert _normalize_kondisi_arsip("rusak") == "RUSAK"
    assert _normalize_kondisi_arsip("RUSAK RINGAN") == "RUSAK"
    assert _normalize_kondisi_arsip("rusak berat") == "RUSAK"
    assert _normalize_kategori_arsip("") == "Surat Masuk"
    assert _normalize_kondisi_arsip("") == "BAIK"

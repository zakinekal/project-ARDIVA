// AppsScript_Kode.gs
// Deploy sebagai Web App: Execute as "Me", Who has access: "Anyone"
// Salin seluruh kode ini ke Apps Script editor, lalu deploy.

const SECRET_TOKEN = "ISI_DENGAN_TOKEN_RAHASIA_YANG_SAMA_DENGAN_DI_ENV";

// Nama sheet/tab yang dipakai sistem di setiap spreadsheet
const NAMA_SHEET = "ARDIVA_DATA";

// Header kolom — urutan ini yang menentukan kolom di Sheets
const HEADERS = [
  "nomor", "no_surat", "uraian_arsip", "sub_kegiatan",
  "tanggal_surat", "kode_klas", "pengirim", "tahun",
  "tk_perkembangan", "jumlah", "kondisi_arsip",
  "retensi_aktif", "retensi_inaktif", "keterangan_jra",
  "skkd", "klasifikasi_akses", "unit_pengolah",
  "kategori_arsip", "nama_file_pdf"
];

function doPost(e) {
  try {
    var body   = JSON.parse(e.postData.contents);
    var token  = body.token;
    var action = body.action;
    var ssId   = body.spreadsheet_id;

    if (token !== SECRET_TOKEN) {
      return _json({ status: "error", message: "Token tidak valid." });
    }
    if (!ssId || ssId === "ISI_NANTI") {
      return _json({ status: "error", message: "Spreadsheet ID belum dikonfigurasi." });
    }

    var ss    = SpreadsheetApp.openById(ssId);
    var sheet = _getOrCreateSheet(ss);

    if (action === "cek_status") {
      var lastRow = sheet.getLastRow();
      var jumlah  = lastRow <= 1 ? 0 : lastRow - 1;
      return _json({ status: "success", jumlah_data: jumlah });
    }

    if (action === "simpan") {
      return _simpan(sheet, body.data, body.force);
    }

    if (action === "ambil_semua") {
      return _ambilSemua(sheet);
    }

    if (action === "update") {
      return _update(sheet, body.baris, body.data);
    }

    if (action === "hapus") {
      return _hapus(sheet, body.baris);
    }

    return _json({ status: "error", message: "Action tidak dikenal: " + action });

  } catch (err) {
    return _json({ status: "error", message: err.toString() });
  }
}

// ── Pastikan sheet ARDIVA_DATA ada, buat jika belum ──────────────────────────
function _getOrCreateSheet(ss) {
  var sheet = ss.getSheetByName(NAMA_SHEET);
  if (!sheet) {
    sheet = ss.insertSheet(NAMA_SHEET);
    // Tulis header di baris pertama
    sheet.getRange(1, 1, 1, HEADERS.length).setValues([HEADERS]);
    sheet.getRange(1, 1, 1, HEADERS.length)
      .setBackground("#0D6B52")
      .setFontColor("white")
      .setFontWeight("bold");
    sheet.setFrozenRows(1);
  }
  return sheet;
}

// ── Simpan data baru ──────────────────────────────────────────────────────────
function _simpan(sheet, data, force) {
  // Cek duplikat by no_surat
  if (!force && data.no_surat && data.no_surat !== "TIDAK ADA NOMOR") {
    var existing = _cariNoSurat(sheet, data.no_surat);
    if (existing > 0) {
      return _json({
        status: "duplikat",
        message: "No Surat '" + data.no_surat + "' sudah tersimpan sebelumnya (baris " + existing + ")."
      });
    }
  }

  var lastRow = sheet.getLastRow();
  var nomor   = lastRow <= 1 ? 1 : lastRow; // nomor urut
  var row     = HEADERS.map(function(h) {
    if (h === "nomor") return nomor;
    return data[h] || "";
  });

  sheet.appendRow(row);
  var newRow = sheet.getLastRow();
  return _json({ status: "success", nomor: nomor, nomor_baris: newRow });
}

// ── Ambil semua data ──────────────────────────────────────────────────────────
function _ambilSemua(sheet) {
  var lastRow = sheet.getLastRow();
  if (lastRow <= 1) {
    return _json({ status: "success", data: [] });
  }
  var values = sheet.getRange(2, 1, lastRow - 1, HEADERS.length).getValues();
  var result = values.map(function(row, idx) {
    var obj = { _baris: idx + 2 };
    HEADERS.forEach(function(h, i) { obj[h] = row[i] !== undefined ? String(row[i]) : ""; });
    return obj;
  });
  return _json({ status: "success", data: result });
}

// ── Update baris tertentu ─────────────────────────────────────────────────────
function _update(sheet, baris, data) {
  if (!baris || baris < 2) {
    return _json({ status: "error", message: "Nomor baris tidak valid." });
  }
  var row = HEADERS.map(function(h) { return data[h] !== undefined ? data[h] : ""; });
  sheet.getRange(baris, 1, 1, HEADERS.length).setValues([row]);
  return _json({ status: "success", baris: baris });
}

// ── Hapus baris tertentu ──────────────────────────────────────────────────────
function _hapus(sheet, baris) {
  if (!baris || baris < 2) {
    return _json({ status: "error", message: "Nomor baris tidak valid." });
  }
  sheet.deleteRow(baris);
  return _json({ status: "success", baris: baris });
}

// ── Cari no surat (kembalikan nomor baris atau 0 jika tidak ada) ──────────────
function _cariNoSurat(sheet, noSurat) {
  var lastRow = sheet.getLastRow();
  if (lastRow <= 1) return 0;
  var colIdx  = HEADERS.indexOf("no_surat") + 1;
  var values  = sheet.getRange(2, colIdx, lastRow - 1, 1).getValues();
  for (var i = 0; i < values.length; i++) {
    if (values[i][0] === noSurat) return i + 2;
  }
  return 0;
}

// ── Helper JSON response ──────────────────────────────────────────────────────
function _json(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

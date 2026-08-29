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
  "kategori_arsip", "nama_file"
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
  } else {
    var headerMap = _headerMap(sheet);
    if (!headerMap.nama_file) {
      var namaFileCol = sheet.getLastColumn() + 1;
      sheet.getRange(1, namaFileCol).setValue("NAMA FILE");
    }
  }
  return sheet;
}

function _normalisasiHeader(value) {
  return String(value || "").toLowerCase().replace(/[^a-z0-9]/g, "");
}

function _headerMap(sheet) {
  var lastColumn = Math.max(sheet.getLastColumn(), HEADERS.length);
  var headers = sheet.getRange(1, 1, 1, lastColumn).getValues()[0];
  var aliases = {
    no_surat: ["nosurat", "nomorsurat"],
    uraian_arsip: ["uraianarsip", "perihal"],
    tanggal_surat: ["tanggalsurat", "tanggal"],
    kode_klas: ["kodeklas", "kodeklasifikasi"],
    tk_perkembangan: ["tkperkembangan", "tingkatperkembangan"],
    kondisi_arsip: ["kondisiarsip"],
    retensi_aktif: ["retensiaktif", "aktif"],
    retensi_inaktif: ["retensiinaktif", "inaktif"],
    keterangan_jra: ["keterangan", "keteranganjra"],
    klasifikasi_akses: ["klasifikasiakses"],
    unit_pengolah: ["unitpengolah"],
    kategori_arsip: ["kategoriarsip"],
    nama_file: ["namafile", "namafilepdf"]
  };
  var map = {};
  headers.forEach(function(header, index) {
    var normalized = _normalisasiHeader(header);
    HEADERS.forEach(function(key) {
      if (normalized === _normalisasiHeader(key)) map[key] = index + 1;
      if ((aliases[key] || []).indexOf(normalized) >= 0) map[key] = index + 1;
    });
  });
  return map;
}

// ── Simpan data baru ──────────────────────────────────────────────────────────
function _simpan(sheet, data, force) {
  // Cek duplikat by no_surat
  if (!force && data.no_surat && data.no_surat !== "TIDAK ADA NOMOR") {
    var existing = _cariNoSurat(sheet, data.no_surat);
    if (existing > 0) {
      return _json({
        status: "duplikat",
        no_surat: data.no_surat,
        baris_lama: existing,
        message: "Nomor surat ini sudah terdaftar di Google Sheets."
      });
    }
  }

  var lastRow = sheet.getLastRow();
  var nomor   = lastRow <= 1 ? 1 : lastRow; // nomor urut
  var headerMap = _headerMap(sheet);
  var nextRow = lastRow + 1;
  var rowValues = Array(sheet.getLastColumn()).fill("");
  HEADERS.forEach(function(h) {
    var col = headerMap[h];
    if (!col) return;
    rowValues[col - 1] = h === "nomor" ? nomor : (data[h] || "");
  });
  var kodeKlasCol = headerMap.kode_klas;
  if (kodeKlasCol) sheet.getRange(nextRow, kodeKlasCol).setNumberFormat("@");
  sheet.getRange(nextRow, 1, 1, rowValues.length).setValues([rowValues]);
  var newRow = sheet.getLastRow();
  return _json({ status: "success", nomor: nomor, nomor_baris: newRow });
}

// ── Ambil semua data ──────────────────────────────────────────────────────────
function _ambilSemua(sheet) {
  var lastRow = sheet.getLastRow();
  if (lastRow <= 1) {
    return _json({ status: "success", data: [] });
  }
  var headerMap = _headerMap(sheet);
  var values = sheet.getRange(2, 1, lastRow - 1, sheet.getLastColumn()).getValues();
  var result = [];
  values.forEach(function(row, index) {
    var obj = { _baris: index + 2 };
    HEADERS.forEach(function(h) {
      var col = headerMap[h];
      obj[h] = col ? String(row[col - 1] || "") : "";
    });
    result.push(obj);
  });
  return _json({ status: "success", data: result });
}

// ── Update baris tertentu ─────────────────────────────────────────────────────
function _update(sheet, baris, data) {
  if (!baris || baris < 2) {
    return _json({ status: "error", message: "Nomor baris tidak valid." });
  }
  var headerMap = _headerMap(sheet);
  if (headerMap.kode_klas) sheet.getRange(baris, headerMap.kode_klas).setNumberFormat("@");
  HEADERS.forEach(function(h) {
    var col = headerMap[h];
    if (col && data[h] !== undefined) sheet.getRange(baris, col).setValue(data[h]);
  });
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
  var colIdx  = _headerMap(sheet).no_surat;
  if (!colIdx) return 0;
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

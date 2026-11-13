"""
master.py - Data Master (bab 6) dan Informasi Usaha (bab 7)
Satu mesin CRUD sederhana untuk semua tabel master dan catatan operasional.
Hak akses diperiksa di sini (backend). Semua perubahan dicatat di audit trail dengan nilai lama dan baru.
Tidak ada kode tampilan di file ini.
"""

import json
import re

from database import (EMAIL_REGEX, KELOMPOK_AKUN, LOG_MASTER, LOG_TRANSAKSI, TIDAK_BERHAK, catat, get_conn, kode_otomatis,
                      nomor_berikut, owner, semua, satu, tolak_akses, hari_ini)

STATUS = ["Aktif", "Nonaktif"]
TERMIN = ["Tunai", "Kredit"]
KATEGORI_ITEM = ["Benih", "Pakan", "Pupuk, kapur, dan obat", "Ikan hasil panen", "Perlengkapan"]
SATUAN_DEFAULT = {"Benih": "Ekor", "Pakan": "Kg", "Pupuk, kapur, dan obat": "Kg", "Ikan hasil panen": "Kg", "Perlengkapan": "Unit"}
AKUN_PERSEDIAAN_ITEM = {"Benih": "1104", "Pakan": "1105", "Pupuk, kapur, dan obat": "1106", "Ikan hasil panen": "1107",
                        "Perlengkapan": "1108"}
KATEGORI_CUSTOMER = ["Pengepul", "Pedagang", "Pengolah", "Pembeli langsung"]
KELOMPOK_ASET = {"Bangunan": ("1202", "1203"), "Pompa dan mesin": ("1204", "1205"), "Peralatan": ("1206", "1207"),
                 "Kendaraan": ("1208", "1209")}
JENIS_LOG = ["Pakan", "Pupuk", "Kapur", "Obat", "Ikan mati"]


# ------------------------------------------------------------------ opsi pilihan dari database
def _opsi(sql, kosong=False):
    def f():
        o = [(None, "-")] if kosong else []
        return o + [(r["id"] if "id" in r else r["kode"], r["label"]) for r in semua(sql)]
    return f


opsi_supplier = _opsi("SELECT id, kode || ' - ' || nama AS label FROM suppliers WHERE status='Aktif' ORDER BY kode", True)
opsi_customer = _opsi("SELECT id, kode || ' - ' || nama AS label FROM customers WHERE status='Aktif' ORDER BY kode", True)
opsi_tambak = _opsi("SELECT id, kode || ' - ' || nama AS label FROM ponds ORDER BY kode")
opsi_item = _opsi("SELECT id, kode || ' - ' || nama AS label FROM items WHERE status='Aktif' ORDER BY kode", True)
opsi_siklus = _opsi("SELECT c.id, c.kode || ' - ' || p.nama AS label FROM cultivation_cycles c JOIN ponds p ON p.id=c.pond_id "
                    "ORDER BY c.id DESC", True)
opsi_penjualan = _opsi("SELECT id, no || ' - Rp ' || CAST(total AS INTEGER) AS label FROM transactions "
                       "WHERE jenis LIKE 'penjualan%' AND status IN ('Draft','Diposting') ORDER BY tanggal DESC, id DESC", True)


def opsi_akun_persediaan():
    return [(None, "-")] + [(r["kode"], f'{r["kode"]} - {r["nama"]}') for r in
                            semua("SELECT kode, nama FROM accounts WHERE status='Aktif' AND kode BETWEEN '1104' AND '1108' ORDER BY kode")]


def opsi_akun_semua():
    return [(None, "-")] + [(r["kode"], f'{r["kode"]} - {r["nama"]}') for r in
                            semua("SELECT kode, nama FROM accounts WHERE status='Aktif' ORDER BY kode")]


def F(k, label, tipe="teks", wajib=False, opsi=None, default=None, bantuan="", unik=False, rahasia=False):
    return dict(k=k, label=label, tipe=tipe, wajib=wajib, opsi=opsi, default=default, bantuan=bantuan, unik=unik, rahasia=rahasia)


# ------------------------------------------------------------------ definisi entitas
# tipe isian: teks | area | angka | uang | pilihan | tanggal | kode
# kelola: "owner" (hanya Owner mengubah) atau "karyawan" (Karyawan boleh input dan ubah miliknya sendiri)
ENT = {
    "akun": dict(
        tabel="accounts", judul="Daftar Akun", tunggal="akun", kelola="owner", urut="t.kode", kode="manual",
        sql="SELECT t.* FROM accounts t",
        medan=[F("kode", "Kode akun", "kode", True, unik=True), F("nama", "Nama akun", wajib=True),
               F("kelompok", "Kelompok", "pilihan", True, KELOMPOK_AKUN),
               F("saldo_normal", "Saldo normal", "pilihan", True, ["Debit", "Kredit"]),
               F("status", "Status", "pilihan", True, STATUS, "Aktif"), F("keterangan", "Keterangan", "area")],
        kolom=["kode", "nama", "kelompok", "saldo_normal", "status", "keterangan"],
        rujukan=[("journal_lines", "kode_akun", "kode"), ("opening_balances", "kode_akun", "kode")],
        catatan="Akun yang sudah dipakai transaksi tidak boleh dihapus, hanya dinonaktifkan. Daftar awal adalah usulan, bukan nomor akun wajib.",
        sembunyi_karyawan=True),
    "karyawan": dict(
        tabel="employees", judul="Karyawan", tunggal="karyawan", kelola="owner", urut="t.kode", kode=("EMP-", 3),
        sql="SELECT t.* FROM employees t",
        medan=[F("nama", "Nama", wajib=True), F("email", "Email (dipakai untuk akun login)", unik=True),
               F("kontak", "Kontak"), F("jabatan", "Jabatan", "pilihan", True, ["Karyawan", "Owner"], "Karyawan"),
               F("tarif_harian", "Tarif harian (Rp)", "uang", True, default=150000, rahasia=True),
               F("periode_gaji", "Periode gaji", "pilihan", True, ["Mingguan"], "Mingguan"),
               F("tanggal_masuk", "Tanggal masuk", "tanggal"), F("status", "Status", "pilihan", True, STATUS, "Aktif")],
        kolom=["kode", "nama", "email", "kontak", "jabatan", "tarif_harian", "periode_gaji", "status"],
        rujukan=[("transactions", "employee_id", "id")], catatan="Tarif dan gaji hanya terlihat oleh Owner. Gaji mingguan = jumlah hari hadir x tarif harian.",
        sembunyi_karyawan=True),
    "item": dict(
        tabel="items", judul="Persediaan", tunggal="item", kelola="owner", urut="t.kode", kode=("ITM-", 3),
        sql="SELECT t.*, s.nama AS supplier FROM items t LEFT JOIN suppliers s ON s.id = t.supplier_id",
        medan=[F("nama", "Nama item", wajib=True), F("kategori", "Kategori", "pilihan", True, KATEGORI_ITEM),
               F("satuan", "Satuan", wajib=True, bantuan="Ekor, Kg, Sak, Liter, Unit"),
               F("supplier_id", "Supplier utama", "pilihan", opsi=opsi_supplier),
               F("harga_beli_ref", "Harga beli referensi (Rp)", "uang", rahasia=True),
               F("harga_jual_standar", "Harga jual standar (Rp, untuk ikan)", "uang"),
               F("stok_minimum", "Stok minimum", "angka", True, default=0),
               F("akun_persediaan", "Akun persediaan", "pilihan", opsi=opsi_akun_persediaan),
               F("status", "Status", "pilihan", True, STATUS, "Aktif")],
        kolom=["kode", "nama", "kategori", "satuan", "supplier", "harga_beli_ref", "harga_jual_standar", "stok_minimum", "status"],
        rujukan=[("transaction_lines", "item_id", "id"), ("stock_counts", "item_id", "id"), ("cultivation_logs", "item_id", "id")],
        catatan="Stok resmi akhir periode berasal dari stok opname. Angka stok di antara dua stok opname hanya estimasi."),
    "customer": dict(
        tabel="customers", judul="Customer", tunggal="customer", kelola="owner", urut="t.kode", kode=("CUS-", 4),
        sql="SELECT t.* FROM customers t",
        medan=[F("nama", "Nama", wajib=True), F("kategori", "Kategori", "pilihan", opsi=KATEGORI_CUSTOMER),
               F("kontak", "Kontak"), F("alamat", "Alamat", "area"),
               F("harga_khusus", "Harga khusus (Rp/kg, bila ada)", "uang"),
               F("termin", "Termin", "pilihan", True, TERMIN, "Tunai"),
               F("pengiriman", "Pengambilan", "pilihan", opsi=["Ambil sendiri", "Dikirim"]),
               F("saldo_awal_piutang", "Saldo awal piutang (Rp)", "uang", default=0, rahasia=True),
               F("status", "Status", "pilihan", True, STATUS, "Aktif")],
        kolom=["kode", "nama", "kategori", "kontak", "harga_khusus", "termin", "pengiriman", "saldo_awal_piutang", "status"],
        rujukan=[("transactions", "customer_id", "id")]),
    "supplier": dict(
        tabel="suppliers", judul="Supplier", tunggal="supplier", kelola="owner", urut="t.kode", kode=("SUP-", 4),
        sql="SELECT t.* FROM suppliers t",
        medan=[F("nama", "Nama", wajib=True),
               F("jenis_pasokan", "Barang yang dipasok", "pilihan", opsi=["Benih", "Pakan", "Pupuk dan obat", "Jasa angkut", "Lainnya"]),
               F("kontak", "Kontak"), F("alamat", "Alamat", "area"),
               F("harga_beli_terakhir", "Harga beli terakhir (Rp)", "uang", rahasia=True),
               F("termin", "Termin", "pilihan", True, TERMIN, "Tunai"),
               F("saldo_awal_utang", "Saldo awal utang (Rp)", "uang", default=0, rahasia=True),
               F("status", "Status", "pilihan", True, STATUS, "Aktif")],
        kolom=["kode", "nama", "jenis_pasokan", "kontak", "alamat", "harga_beli_terakhir", "termin", "saldo_awal_utang", "status"],
        rujukan=[("transactions", "supplier_id", "id"), ("items", "supplier_id", "id")]),
    "tambak": dict(
        tabel="ponds", judul="Tambak (Petak)", tunggal="petak", kelola="owner", urut="t.kode", kode=("TBK-", 2),
        sql="SELECT t.* FROM ponds t",
        medan=[F("nama", "Nama petak", wajib=True), F("luas_m2", "Luas (m2)", "angka", bantuan="1 hektar = 10.000 m2. Total seluruh petak sekitar 2 ha."),
               F("status", "Status", "pilihan", True, ["Kosong", "Persiapan", "Budidaya", "Panen"], "Kosong")],
        kolom=["kode", "nama", "luas_m2", "status"], rujukan=[("cultivation_cycles", "pond_id", "id"), ("cultivation_logs", "pond_id", "id")],
        catatan="Jumlah dan luas tiap petak diisi Owner. Total luas seluruh petak sekitar 2 ha."),
    "aset": dict(
        tabel="fixed_assets", judul="Aset Tetap", tunggal="aset tetap", kelola="owner", urut="t.kode", kode=("AST-", 3),
        sql="SELECT t.* FROM fixed_assets t",
        medan=[F("nama", "Nama aset", wajib=True), F("kelompok", "Kelompok", "pilihan", True, list(KELOMPOK_ASET)),
               F("tgl_perolehan", "Tanggal perolehan", "tanggal"), F("harga_perolehan", "Harga perolehan (Rp)", "uang", rahasia=True),
               F("umur_tahun", "Umur manfaat (tahun)", "angka"), F("nilai_sisa", "Nilai sisa (Rp)", "uang", rahasia=True),
               F("akumulasi_awal", "Akumulasi penyusutan awal (Rp)", "uang", rahasia=True),
               F("status", "Status", "pilihan", True, STATUS, "Aktif")],
        kolom=["kode", "nama", "kelompok", "tgl_perolehan", "harga_perolehan", "umur_tahun", "nilai_sisa", "akumulasi_awal", "konfirmasi", "status"],
        rujukan=[("depreciation_log", "asset_id", "id")],
        catatan="Metode penyusutan garis lurus. Jika data belum diketahui, kosongkan: aset ditandai belum dikonfirmasi dan tidak disusutkan. Jangan mengisi angka karangan."),
    "tarif": dict(
        tabel="shipping_rates", judul="Ongkos Kirim", tunggal="tarif ongkir", kelola="owner", urut="t.id", kode=None,
        sql="SELECT t.* FROM shipping_rates t",
        medan=[F("nama", "Nama tarif", wajib=True), F("dasar", "Dasar tarif", "pilihan", True, ["Per kg", "Per trip", "Per tujuan"]),
               F("tujuan", "Tujuan"), F("tarif", "Tarif (Rp)", "uang", True),
               F("ditanggung", "Ditanggung oleh", "pilihan", True, ["Belum ditentukan", "Penjual (usaha)", "Pembeli"], "Belum ditentukan"),
               F("status", "Status", "pilihan", True, STATUS, "Aktif")],
        kolom=["nama", "dasar", "tujuan", "tarif", "ditanggung", "status"], rujukan=[]),
    # ---- Informasi Usaha
    "siklus": dict(
        tabel="cultivation_cycles", judul="Siklus Budidaya", tunggal="siklus", kelola="karyawan", pemilik="dibuat_oleh", urut="t.id DESC", kode=("SBD-", 3),
        sql="SELECT t.*, p.nama AS petak FROM cultivation_cycles t JOIN ponds p ON p.id = t.pond_id",
        medan=[F("pond_id", "Petak", "pilihan", True, opsi_tambak), F("tgl_tebar", "Tanggal tebar", "tanggal"),
               F("jumlah_benih", "Jumlah benih (ekor)", "angka"),
               F("item_benih_id", "Item benih (untuk estimasi stok)", "pilihan", opsi=opsi_item),
               F("perkiraan_panen", "Perkiraan panen", "tanggal"),
               F("status", "Status", "pilihan", True, ["Persiapan", "Berjalan", "Selesai"], "Persiapan"), F("keterangan", "Keterangan", "area")],
        kolom=["kode", "petak", "tgl_tebar", "jumlah_benih", "perkiraan_panen", "status"],
        rujukan=[("cultivation_logs", "cycle_id", "id")],
        catatan="Dasar menghitung biaya per siklus. Tidak langsung menjadi jurnal."),
    "catatan": dict(
        tabel="cultivation_logs", judul="Catatan Harian", tunggal="catatan", kelola="karyawan", urut="t.tanggal DESC, t.id DESC", kode=None,
        sql="SELECT t.*, i.nama AS item, p.nama AS petak, i.satuan FROM cultivation_logs t LEFT JOIN items i ON i.id = t.item_id "
            "LEFT JOIN ponds p ON p.id = t.pond_id", filter_sql="t.jenis != 'Panen'",
        medan=[F("tanggal", "Tanggal", "tanggal", True, default="hari_ini"), F("pond_id", "Petak", "pilihan", opsi=opsi_tambak),
               F("cycle_id", "Siklus", "pilihan", opsi=opsi_siklus), F("jenis", "Jenis", "pilihan", True, JENIS_LOG),
               F("item_id", "Item (kosongkan untuk ikan mati)", "pilihan", opsi=opsi_item), F("jumlah", "Jumlah (kg, liter, atau ekor)", "angka", True),
               F("keterangan", "Keterangan", "area")],
        kolom=["tanggal", "petak", "jenis", "item", "jumlah", "satuan", "keterangan"], rujukan=[], pemilik="dibuat_oleh",
        catatan="Pembanding hasil stok opname, bukan dasar jurnal."),
    "panen": dict(
        tabel="cultivation_logs", judul="Panen", tunggal="panen", kelola="karyawan", urut="t.tanggal DESC, t.id DESC", kode=None,
        sql="SELECT t.*, p.nama AS petak FROM cultivation_logs t LEFT JOIN ponds p ON p.id = t.pond_id", filter_sql="t.jenis = 'Panen'",
        tetap={"jenis": "Panen"},
        medan=[F("tanggal", "Tanggal", "tanggal", True, default="hari_ini"), F("pond_id", "Petak", "pilihan", True, opsi_tambak),
               F("cycle_id", "Siklus", "pilihan", opsi=opsi_siklus), F("jumlah", "Berat (kg)", "angka", True),
               F("ukuran", "Ukuran (ekor per kg)"), F("keterangan", "Keterangan", "area")],
        kolom=["tanggal", "petak", "jumlah", "ukuran", "keterangan"], rujukan=[], pemilik="dibuat_oleh",
        catatan="Menjadi dasar stok ikan siap jual dan penjualan."),
    "pengiriman": dict(
        tabel="deliveries", judul="Pengiriman", tunggal="pengiriman", kelola="karyawan", urut="t.tanggal DESC, t.id DESC", kode=None,
        sql="SELECT t.*, c.nama AS customer, x.no AS penjualan FROM deliveries t LEFT JOIN customers c ON c.id = t.customer_id "
            "LEFT JOIN transactions x ON x.id = t.transaction_id",
        medan=[F("tanggal", "Tanggal", "tanggal", True, default="hari_ini"), F("customer_id", "Customer", "pilihan", opsi=opsi_customer),
               F("transaction_id", "Penjualan terkait", "pilihan", opsi=opsi_penjualan),
               F("kendaraan", "Kendaraan"), F("pengemudi", "Pengemudi"), F("berat", "Berat (kg)", "angka"),
               F("status", "Status", "pilihan", True, ["Disiapkan", "Dikirim", "Diterima"], "Disiapkan"),
               F("biaya_angkut", "Biaya angkut (Rp)", "uang", rahasia=True)],
        kolom=["no_surat_jalan", "tanggal", "customer", "penjualan", "kendaraan", "pengemudi", "berat", "status", "biaya_angkut"],
        rujukan=[], pemilik="dibuat_oleh", surat_jalan=True,
        catatan="Biaya angkut dicatat lewat transaksi biaya. Penjualan terkait tetap dari transaksi penjualan."),
}


# ------------------------------------------------------------------ hak akses
def boleh_lihat(user: dict, ent: str) -> bool:
    sp = ENT[ent]
    return owner(user) or not sp.get("sembunyi_karyawan")


def boleh_tulis(user: dict, ent: str, baris: dict | None = None) -> bool:
    sp = ENT[ent]
    if owner(user):
        return True
    if sp["kelola"] != "karyawan":
        return False
    return baris is None or baris.get(sp.get("pemilik", "dibuat_oleh")) == user["id"]


def _rahasia(sp) -> set:
    return {m["k"] for m in sp["medan"] if m["rahasia"]}


def daftar(user: dict, ent: str, cari: str = "") -> list:
    """Daftar baris. Kolom rahasia tidak dikirim ke Karyawan sama sekali."""
    sp = ENT[ent]
    if not boleh_lihat(user, ent):
        return []
    where = f"WHERE {sp['filter_sql']}" if sp.get("filter_sql") else ""
    rows = semua(f"{sp['sql']} {where} ORDER BY {sp['urut']}")
    if ent == "aset":
        for r in rows:
            r["konfirmasi"] = "Terkonfirmasi" if all(r[k] is not None for k in ("tgl_perolehan", "harga_perolehan", "umur_tahun")) else "Belum dikonfirmasi"
    if cari.strip():
        q = cari.strip().lower()
        rows = [r for r in rows if any(q in str(v).lower() for v in r.values() if v is not None)]
    if not owner(user):
        for r in rows:
            for k in _rahasia(sp):
                r.pop(k, None)
            if ent == "pengiriman":
                r.pop("biaya_angkut", None)
    return rows


def ambil(user: dict, ent: str, id_: int):
    sp = ENT[ent]
    if not boleh_lihat(user, ent):
        return None
    r = satu(f"SELECT * FROM {sp['tabel']} WHERE id = ?", (id_,))
    if r and not owner(user):
        for k in _rahasia(sp):
            r.pop(k, None)
    return r


def satu_baris(ent: str, id_: int):
    """Baris mentah (untuk formulir ubah). Pemanggil wajib sudah memeriksa hak akses."""
    return satu(f"SELECT * FROM {ENT[ent]['tabel']} WHERE id = ?", (id_,))


def opsi_dari(m: dict) -> list:
    """Daftar pilihan sebuah isian sebagai [(nilai, label)]."""
    o = m["opsi"]
    if callable(o):
        return o()
    if o is None:
        return []
    return [(x, x) for x in o]


# ------------------------------------------------------------------ validasi dan simpan
def _bersihkan(sp, ent, d: dict, id_):
    """Return (data_bersih, pesan_error)."""
    out = {}
    for m in sp["medan"]:
        k = m["k"]; v = d.get(k)
        if isinstance(v, str):
            v = v.strip() or None
        if v is None and m["default"] is not None and id_ is None:   # nilai bawaan juga berlaku di backend
            v = hari_ini() if m["default"] == "hari_ini" else m["default"]
        if m["tipe"] == "tanggal" and v is not None and not isinstance(v, str):
            v = v.isoformat()
        if v is None and m["wajib"]:
            return None, f'{m["label"]} wajib diisi.'
        if m["tipe"] in ("angka", "uang") and v is not None:
            try:
                v = float(v)
            except (TypeError, ValueError):
                return None, f'{m["label"]} harus berupa angka.'
            if v < 0:
                return None, f'{m["label"]} tidak boleh negatif.'
        if m["tipe"] == "pilihan" and v is not None and m["opsi"] is not None:
            if v not in [x[0] for x in opsi_dari(m)]:
                return None, f'{m["label"]} tidak valid.'
        if k == "email" and v:
            v = v.lower()
            if not EMAIL_REGEX.match(v):
                return None, "Format email tidak valid."
        if k == "kode" and v and not re.match(r"^[A-Za-z0-9\-]+$", v):
            return None, "Kode hanya boleh huruf, angka, dan tanda hubung."
        if m["unik"] and v:
            ada = satu(f"SELECT id FROM {sp['tabel']} WHERE {k} = ? AND id IS NOT ?", (v, id_))
            if ada:
                return None, f'{m["label"]} sudah dipakai (tidak boleh duplikat).'
        out[k] = v
    for k, v in sp.get("tetap", {}).items():
        out[k] = v
    if ent == "item" and not out.get("akun_persediaan"):
        out["akun_persediaan"] = AKUN_PERSEDIAAN_ITEM.get(out.get("kategori"))
    if ent == "aset":
        out["akun_aset"], out["akun_akumulasi"] = KELOMPOK_ASET[out["kelompok"]]
    if ent == "siklus":
        if out.get("tgl_tebar") and out.get("perkiraan_panen") and out["perkiraan_panen"] < out["tgl_tebar"]:
            return None, "Perkiraan panen tidak boleh sebelum tanggal tebar."
    if sp["tabel"] == "cultivation_logs":
        if out.get("tanggal") and out["tanggal"] > hari_ini().isoformat():
            return None, "Tanggal tidak boleh di masa depan."
        if out.get("jenis") in ("Pakan", "Pupuk", "Kapur", "Obat") and not out.get("item_id"):
            return None, "Pilih item untuk pakan, pupuk, kapur, atau obat."
        if (out.get("jumlah") or 0) <= 0:
            return None, "Jumlah harus lebih dari 0."
    if ent == "panen" and (out.get("jumlah") or 0) <= 0:
        return None, "Berat harus lebih dari 0."
    if ent == "karyawan" and out.get("email"):
        u = satu("SELECT id FROM users WHERE email = ?", (out["email"],))
        out["user_id"] = u["id"] if u else None
    return out, None


def _ringkas(d: dict) -> str:
    return json.dumps(d, ensure_ascii=False, default=str)


def simpan(user: dict, ent: str, d: dict, id_: int | None = None):
    """Tambah atau ubah. Return (ok, pesan)."""
    sp = ENT[ent]
    jenis_log = LOG_MASTER if sp["kelola"] == "owner" else LOG_TRANSAKSI
    lama_row = satu(f"SELECT * FROM {sp['tabel']} WHERE id = ?", (id_,)) if id_ else None
    if not boleh_tulis(user, ent, lama_row):
        return tolak_akses(user, sp["judul"])
    bersih, salah = _bersihkan(sp, ent, d, id_)
    if salah:
        return False, salah
    if not owner(user):   # Karyawan tidak pernah menerima atau mengubah kolom rahasia
        for k in _rahasia(sp):
            bersih.pop(k, None)
    try:
        with get_conn() as c:
            if id_:
                if not lama_row:
                    return False, "Data tidak ditemukan."
                ubah = {k: v for k, v in bersih.items() if (lama_row.get(k) if k in lama_row.keys() else None) != v}
                if not ubah:
                    return True, "Tidak ada perubahan."
                c.execute(f"UPDATE {sp['tabel']} SET {', '.join(k + ' = ?' for k in ubah)} WHERE id = ?", [*ubah.values(), id_])
                catat(c, jenis_log, f"ubah {sp['tunggal']}", "Berhasil", user=user, objek=f"{sp['tabel']}#{id_}",
                      nilai_lama=_ringkas({k: lama_row[k] for k in ubah}), nilai_baru=_ringkas(ubah))
                return True, f"{sp['judul']} diperbarui."
            kol = dict(bersih)
            kd = sp.get("kode")
            if isinstance(kd, tuple):
                kol["kode"] = kode_otomatis(c, sp["tabel"], kd[0], kd[1])
            if sp.get("surat_jalan"):
                bln = (kol["tanggal"] or "")[:7].replace("-", "")
                kol["no_surat_jalan"] = f"SJ-{bln}-{nomor_berikut(c, 'sj:' + bln):04d}"
            if sp.get("pemilik"):
                kol[sp["pemilik"]] = user["id"]
            cur = c.execute(f"INSERT INTO {sp['tabel']} ({', '.join(kol)}) VALUES ({', '.join('?' * len(kol))})", list(kol.values()))
            catat(c, jenis_log, f"tambah {sp['tunggal']}", "Berhasil", user=user, objek=f"{sp['tabel']}#{cur.lastrowid}",
                  nilai_baru=_ringkas(kol))
            return True, f"{sp['judul']} ditambahkan."
    except Exception as e:
        return False, f"Gagal menyimpan: {e}"


def hapus(user: dict, ent: str, id_: int):
    """Hapus bila belum dipakai; bila sudah dipakai hanya boleh dinonaktifkan."""
    sp = ENT[ent]
    row = satu(f"SELECT * FROM {sp['tabel']} WHERE id = ?", (id_,))
    if not row:
        return False, "Data tidak ditemukan."
    if not boleh_tulis(user, ent, row):
        return tolak_akses(user, sp["judul"])
    for tabel, kol, ref in sp["rujukan"]:
        if satu(f"SELECT 1 AS x FROM {tabel} WHERE {kol} = ?", (row[ref],)):
            if "status" in row:
                return False, "Data ini sudah dipakai, jadi tidak boleh dihapus. Ubah statusnya menjadi Nonaktif."
            return False, "Data ini sudah dipakai, jadi tidak boleh dihapus."
    try:
        with get_conn() as c:
            c.execute(f"DELETE FROM {sp['tabel']} WHERE id = ?", (id_,))
            catat(c, LOG_MASTER if sp["kelola"] == "owner" else LOG_TRANSAKSI, f"hapus {sp['tunggal']}", "Berhasil", user=user,
                  objek=f"{sp['tabel']}#{id_}", nilai_lama=_ringkas(row))
        return True, "Data dihapus."
    except Exception as e:
        return False, f"Gagal menghapus: {e}"


# ------------------------------------------------------------------ profil usaha
PROFIL_KUNCI = [("nama_usaha", "Nama usaha"), ("alamat", "Alamat"), ("luas_tambak", "Luas tambak"), ("kontak", "Kontak"),
                ("jenis_usaha", "Jenis usaha")]
PROFIL_AWAL = {"jenis_usaha": "Budidaya dan penjualan ikan bandeng", "luas_tambak": "Sekitar 2 hektar"}


def ambil_profil() -> dict:
    d = {r["kunci"]: r["nilai"] for r in semua("SELECT * FROM business_profile")}
    for k, v in PROFIL_AWAL.items():
        d.setdefault(k, v)
    return d


def simpan_profil(user: dict, d: dict):
    if not owner(user):
        return tolak_akses(user, "Profil usaha")
    lama = ambil_profil()
    with get_conn() as c:
        for k, _ in PROFIL_KUNCI:
            c.execute("INSERT INTO business_profile (kunci,nilai) VALUES (?,?) ON CONFLICT(kunci) DO UPDATE SET nilai=excluded.nilai",
                      (k, (d.get(k) or "").strip()))
        catat(c, LOG_MASTER, "ubah profil usaha", "Berhasil", user=user, objek="business_profile",
              nilai_lama=_ringkas(lama), nilai_baru=_ringkas(d))
    return True, "Profil usaha disimpan."


# ------------------------------------------------------------------ saldo awal (6.9)
def ambil_saldo_awal() -> dict:
    ob = {r["kode_akun"]: r for r in semua("SELECT * FROM opening_balances")}
    tgl = next(iter(ob.values()))["tanggal"] if ob else None
    return {"baris": ob, "tanggal": tgl, "final": satu("SELECT nilai FROM app_settings WHERE kunci='saldo_awal_final'") is not None
            and satu("SELECT nilai FROM app_settings WHERE kunci='saldo_awal_final'")["nilai"] == "Ya"}


def simpan_saldo_awal(user: dict, tanggal, baris: list, finalisasi: bool):
    """baris = [(kode, debit, kredit)]. Final hanya bila debit = kredit dan rincian piutang/utang/persediaan cocok."""
    if not owner(user):
        return tolak_akses(user, "Saldo awal")
    if ambil_saldo_awal()["final"]:
        return False, "Saldo awal sudah final dan tidak bisa diubah."
    baris = [(k, float(d or 0), float(kr or 0)) for k, d, kr in baris if (d or 0) or (kr or 0)]
    if any(d < 0 or kr < 0 for _, d, kr in baris):
        return False, "Nilai tidak boleh negatif."
    td, tk = sum(b[1] for b in baris), sum(b[2] for b in baris)
    if finalisasi:
        if abs(td - tk) > 0.005:
            return False, f"Total debit (Rp {td:,.0f}) harus sama dengan total kredit (Rp {tk:,.0f}) sebelum difinalisasi.".replace(",", ".")
        peta = {k: d - kr for k, d, kr in baris}
        piu = satu("SELECT COALESCE(SUM(saldo_awal_piutang),0) AS n FROM customers")["n"]
        utg = satu("SELECT COALESCE(SUM(saldo_awal_utang),0) AS n FROM suppliers")["n"]
        if abs(peta.get("1103", 0) - piu) > 0.005:
            return False, "Rincian piutang per customer harus sama dengan akun Piutang Usaha."
        if abs(-peta.get("2101", 0) - utg) > 0.005:
            return False, "Rincian utang per supplier harus sama dengan akun Utang Usaha."
        # persediaan awal: kuantitas dan nilai per item harus sama dengan akun persediaan
        for kode in ("1104", "1105", "1106", "1107"):
            nilai = satu("SELECT COALESCE(SUM(o.nilai),0) AS n FROM opening_stock o JOIN items i ON i.id=o.item_id WHERE i.akun_persediaan = ?", (kode,))["n"]
            if abs(peta.get(kode, 0) - nilai) > 0.005:
                return False, f"Nilai persediaan awal per item harus sama dengan saldo awal akun {kode}."
    try:
        with get_conn() as c:
            c.execute("DELETE FROM opening_balances")
            for k, d, kr in baris:
                c.execute("INSERT INTO opening_balances (kode_akun,debit,kredit,tanggal) VALUES (?,?,?,?)",
                          (k, d, kr, tanggal.isoformat()))
            if finalisasi:
                c.execute("INSERT INTO app_settings (kunci,nilai) VALUES ('saldo_awal_final','Ya') ON CONFLICT(kunci) DO UPDATE SET nilai='Ya'")
            catat(c, LOG_MASTER, "finalisasi saldo awal" if finalisasi else "simpan saldo awal", "Berhasil", user=user,
                  objek="opening_balances", nilai_baru=f"debit {td:,.0f}, kredit {tk:,.0f}")
        return True, "Saldo awal difinalisasi." if finalisasi else "Saldo awal disimpan sebagai draft."
    except Exception as e:
        return False, str(e)


def simpan_stok_awal(user: dict, item_id: int, jumlah: float, nilai: float):
    if not owner(user):
        return tolak_akses(user, "Persediaan awal")
    if ambil_saldo_awal()["final"]:
        return False, "Saldo awal sudah final."
    if jumlah < 0 or nilai < 0:
        return False, "Kuantitas dan nilai tidak boleh negatif."
    with get_conn() as c:
        c.execute("INSERT INTO opening_stock (item_id,jumlah,nilai) VALUES (?,?,?) ON CONFLICT(item_id) DO UPDATE SET "
                  "jumlah=excluded.jumlah, nilai=excluded.nilai", (item_id, jumlah, nilai))
        catat(c, LOG_MASTER, "simpan persediaan awal", "Berhasil", user=user, objek=f"items#{item_id}",
              nilai_baru=f"{jumlah} / Rp{nilai:,.0f}")
    return True, "Persediaan awal disimpan."


# ------------------------------------------------------------------ profil karyawan sendiri
def profil_saya(user: dict):
    """Karyawan hanya melihat profilnya sendiri, tanpa tarif atau gaji."""
    return satu("SELECT kode, nama, email, kontak, jabatan, periode_gaji, tanggal_masuk, status FROM employees "
                "WHERE user_id = ? OR email = ?", (user["id"], user["email"]))

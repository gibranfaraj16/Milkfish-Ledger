"""
transaksi.py - Modul Transaksi (Modul bab 8)
Alur: Draft -> Posting (jurnal otomatis) -> Hapus = Dibatalkan (jurnal pembalik).
Transaksi, jurnal, dan audit trail disimpan dalam satu proses: bila gagal, tidak ada yang tersimpan.
Hak akses diperiksa di sini (backend), bukan hanya lewat tampilan.
"""

from datetime import date

from database import (LOG_TRANSAKSI, TIDAK_BERHAK, ambil_set, catat, catat_sendiri, get_conn, hari_ini, nomor_berikut,
                      owner, satu, semua, tolak_akses, waktu_teks)

KAS = {"Kas": "1101", "Bank": "1102"}

KAT_PEMBELIAN = {"Benih": "5101", "Pakan": "5102", "Pupuk, kapur, dan obat": "5103", "Ongkos angkut": "5104"}
KAT_ITEM = {"Benih": "Benih", "Pakan": "Pakan", "Pupuk, kapur, dan obat": "Pupuk, kapur, dan obat"}
KAT_BIAYA = {"Listrik dan BBM": "6102", "Perawatan tambak dan mesin": "6103", "Pengiriman": "6104",
             "Perlengkapan": "6105", "Administrasi": "6107", "Lain-lain": "6108"}
KAT_ASET = {"Tanah dan tambak": "1201", "Bangunan dan gubuk jaga": "1202", "Pompa, mesin, dan kincir": "1204",
            "Peralatan budidaya": "1206", "Kendaraan": "1208"}

# label, boleh Karyawan, pihak, pihak wajib, pilihan sumber, kategori, mode isian, jatuh tempo
SPEC = {
    "penjualan_tunai": dict(label="Penjualan tunai", karyawan=True, pihak="customer", wajib=False,
                            sumber=["Kas", "Bank"], kategori=None, mode="qty", item="Ikan hasil panen"),
    "penjualan_kredit": dict(label="Penjualan kredit", karyawan=True, pihak="customer", wajib=True,
                             sumber=["Kredit"], kategori=None, mode="qty", item="Ikan hasil panen", tempo=True),
    "penerimaan_piutang": dict(label="Penerimaan piutang", karyawan=True, pihak="customer", wajib=True,
                               sumber=["Kas", "Bank"], kategori=None, mode="nominal"),
    "pembelian_tunai": dict(label="Pembelian tunai", karyawan=True, pihak="supplier", wajib=True,
                            sumber=["Kas", "Bank"], kategori=KAT_PEMBELIAN, mode="qty"),
    "pembelian_kredit": dict(label="Pembelian kredit", karyawan=True, pihak="supplier", wajib=True,
                             sumber=["Kredit"], kategori=KAT_PEMBELIAN, mode="qty", tempo=True),
    "pembayaran_utang": dict(label="Pembayaran utang", karyawan=True, pihak="supplier", wajib=True,
                             sumber=["Kas", "Bank"], kategori=None, mode="nominal"),
    "biaya_operasional": dict(label="Biaya operasional", karyawan=True, pihak=None, wajib=False,
                              sumber=["Kas", "Bank"], kategori=KAT_BIAYA, mode="nominal"),
    "penggajian": dict(label="Penggajian mingguan", karyawan=False, pihak="employee", wajib=True,
                       sumber=["Kas", "Bank", "Utang gaji"], kategori=None, mode="gaji"),
    "retur_penjualan": dict(label="Retur penjualan", karyawan=False, pihak="customer", wajib=False,
                            sumber=["Kas", "Bank", "Piutang"], kategori=None, mode="nominal"),
    "retur_pembelian": dict(label="Retur pembelian", karyawan=False, pihak="supplier", wajib=False,
                            sumber=["Kas", "Bank", "Utang"], kategori=None, mode="nominal"),
    "aset_tetap": dict(label="Pembelian aset tetap", karyawan=False, pihak="supplier", wajib=False,
                       sumber=["Kas", "Bank", "Kredit"], kategori=KAT_ASET, mode="nominal"),
    "prive": dict(label="Prive", karyawan=False, pihak=None, wajib=False,
                  sumber=["Kas", "Bank"], kategori=None, mode="nominal"),
    "tambahan_modal": dict(label="Tambahan modal", karyawan=False, pihak=None, wajib=False,
                           sumber=["Kas", "Bank"], kategori=None, mode="nominal"),
}


def jenis_boleh(user: dict) -> list:
    return [k for k, v in SPEC.items() if owner(user) or v["karyawan"]]


# ------------------------------------------------------------------ template jurnal
def susun_jurnal(jenis: str, sumber: str, kategori, total: float) -> list:
    """Kembalikan [(kode_akun, debit, kredit)]. Total debit selalu sama dengan total kredit."""
    kas = KAS.get(sumber)
    if jenis == "penjualan_tunai":
        return [(kas, total, 0), ("4101", 0, total)]
    if jenis == "penjualan_kredit":
        return [("1103", total, 0), ("4101", 0, total)]
    if jenis == "penerimaan_piutang":
        return [(kas, total, 0), ("1103", 0, total)]
    if jenis in ("pembelian_tunai", "pembelian_kredit"):
        lawan = "2101" if jenis == "pembelian_kredit" else kas
        return [(KAT_PEMBELIAN[kategori], total, 0), (lawan, 0, total)]
    if jenis == "pembayaran_utang":
        return [("2101", total, 0), (kas, 0, total)]
    if jenis == "biaya_operasional":
        return [(KAT_BIAYA[kategori], total, 0), (kas, 0, total)]
    if jenis == "penggajian":
        return [("6101", total, 0), ("2102" if sumber == "Utang gaji" else kas, 0, total)]
    if jenis == "retur_penjualan":
        return [("4102", total, 0), ("1103" if sumber == "Piutang" else kas, 0, total)]
    if jenis == "retur_pembelian":
        return [("2101" if sumber == "Utang" else kas, total, 0), ("5105", 0, total)]
    if jenis == "aset_tetap":
        return [(KAT_ASET[kategori], total, 0), ("2101" if sumber == "Kredit" else kas, 0, total)]
    if jenis == "prive":
        return [("3102", total, 0), (kas, 0, total)]
    if jenis == "tambahan_modal":
        return [(kas, total, 0), ("3101", 0, total)]
    raise ValueError("Jenis transaksi tidak dikenal.")


def periode_terbuka(conn, tgl_iso: str) -> bool:
    conn.execute("INSERT OR IGNORE INTO periods (bulan) VALUES (?)", (tgl_iso[:7],))
    return conn.execute("SELECT status FROM periods WHERE bulan = ?", (tgl_iso[:7],)).fetchone()["status"] == "Terbuka"


def harga_acuan(item_id, customer_id):
    """Harga jual acuan: harga khusus customer, bila tidak ada harga standar item."""
    if customer_id:
        c = satu("SELECT harga_khusus FROM customers WHERE id = ?", (customer_id,))
        if c and c["harga_khusus"]:
            return c["harga_khusus"]
    if item_id:
        i = satu("SELECT harga_jual_standar FROM items WHERE id = ?", (item_id,))
        if i and i["harga_jual_standar"]:
            return i["harga_jual_standar"]
    return None


# ------------------------------------------------------------------ validasi
def validasi(user: dict, d: dict):
    """Return (data_bersih, pesan_error)."""
    jenis = d.get("jenis")
    sp = SPEC.get(jenis)
    if not sp:
        return None, "Pilih jenis transaksi."
    if not owner(user) and not sp["karyawan"]:
        return None, TIDAK_BERHAK
    tgl = d.get("tanggal")
    tgl = tgl.isoformat() if isinstance(tgl, date) else tgl
    try:
        dt = date.fromisoformat(tgl)
    except (TypeError, ValueError):
        return None, "Tanggal tidak valid."
    if dt > hari_ini():
        return None, "Tanggal transaksi tidak boleh di masa depan."
    sumber = d.get("sumber")
    if sumber not in sp["sumber"]:
        return None, "Pilih cara pembayaran."
    kategori = d.get("kategori")
    if sp["kategori"] and kategori not in sp["kategori"]:
        return None, "Pilih kategori."
    pihak = sp["pihak"]
    cid, sid, eid = d.get("customer_id"), d.get("supplier_id"), d.get("employee_id")
    wajib_pihak = sp["wajib"] or (jenis == "retur_penjualan" and sumber == "Piutang") \
        or (jenis == "retur_pembelian" and sumber == "Utang") or (jenis == "aset_tetap" and sumber == "Kredit")
    if wajib_pihak and not {"customer": cid, "supplier": sid, "employee": eid}.get(pihak):
        return None, {"customer": "Pilih customer.", "supplier": "Pilih supplier.", "employee": "Pilih karyawan."}[pihak]
    try:
        jumlah, harga = float(d.get("jumlah") or 0), float(d.get("harga") or 0)
    except (TypeError, ValueError):
        return None, "Jumlah dan harga harus berupa angka."
    if sp["mode"] == "nominal":
        jumlah = 1.0
    if jumlah <= 0 or harga <= 0:
        return None, "Jumlah dan nominal harus lebih dari 0 (tidak boleh kosong atau negatif)."
    total = round(jumlah * harga, 2)
    ket = (d.get("keterangan") or "").strip()
    if not ket:
        return None, "Keterangan wajib diisi."
    if len(ket) > 300:
        return None, "Keterangan maksimal 300 karakter."
    tempo = d.get("jatuh_tempo")
    tempo = tempo.isoformat() if isinstance(tempo, date) else (tempo or None)
    if sp.get("tempo") and tempo and tempo < dt.isoformat():
        return None, "Jatuh tempo tidak boleh sebelum tanggal transaksi."
    item_id = d.get("item_id") or None
    if sp["mode"] == "qty" and jenis.startswith("penjualan") and not item_id:
        return None, "Pilih barang (ikan hasil panen)."
    if sp["mode"] == "qty" and jenis.startswith("pembelian") and kategori != "Ongkos angkut" and not item_id:
        return None, "Pilih barang yang dibeli."
    # Harga jual: Karyawan hanya boleh mengubah bila Owner mengizinkan (Modul 6.8)
    if jenis.startswith("penjualan") and not owner(user) and ambil_set("karyawan_ubah_harga", "Tidak") != "Ya":
        acuan = harga_acuan(item_id, cid)
        if acuan and abs(acuan - harga) > 0.005:
            return None, f"Harga jual mengikuti harga acuan (Rp {acuan:,.0f}). Karyawan tidak diizinkan mengubah harga.".replace(",", ".")
    return {"jenis": jenis, "tanggal": dt.isoformat(), "sumber": sumber, "kategori": kategori, "customer_id": cid or None,
            "supplier_id": sid or None, "employee_id": eid or None, "jumlah": jumlah, "harga": harga, "total": total,
            "keterangan": ket, "jatuh_tempo": tempo if sp.get("tempo") else None, "item_id": item_id}, None


def _uraian(b: dict) -> str:
    """Teks pendek yang disimpan bersama baris transaksi: sumber bayar dan kategori."""
    return " | ".join(x for x in (b["sumber"], b["kategori"]) if x)


# ------------------------------------------------------------------ draft
def simpan_draft(user: dict, d: dict, id_: int | None = None):
    """Buat draft baru, atau ubah draft (id_). Return (ok, pesan, id)."""
    b, salah = validasi(user, d)
    if salah:
        return False, salah, None
    try:
        with get_conn() as c:
            if not periode_terbuka(c, b["tanggal"]):
                return False, "Periode transaksi sudah ditutup. Transaksi di periode tertutup tidak bisa dibuat atau diubah.", None
            if id_:
                r = c.execute("SELECT * FROM transactions WHERE id = ?", (id_,)).fetchone()
                if not r:
                    return False, "Transaksi tidak ditemukan.", None
                if r["status"] != "Draft":
                    return False, "Hanya draft yang bisa diedit. Transaksi yang sudah diposting tidak diedit langsung: hapus lalu input ulang.", None
                if not owner(user) and r["dibuat_oleh"] != user["id"]:
                    c.rollback()
                    tolak_akses(user, r["no"])
                    return False, TIDAK_BERHAK, None
                lama = f'{r["jenis"]} Rp{r["total"]:,.0f}'
                c.execute("UPDATE transactions SET tanggal=?, jenis=?, customer_id=?, supplier_id=?, employee_id=?, keterangan=?, "
                          "jatuh_tempo=?, total=? WHERE id=?",
                          (b["tanggal"], b["jenis"], b["customer_id"], b["supplier_id"], b["employee_id"], b["keterangan"],
                           b["jatuh_tempo"], b["total"], id_))
                c.execute("DELETE FROM transaction_lines WHERE transaction_id = ?", (id_,))
                tid, nomor, aksi = id_, r["no"], "ubah draft"
            else:
                nomor = f"TRX-{b['tanggal'][:4]}{b['tanggal'][5:7]}-{nomor_berikut(c, 'trx:' + b['tanggal'][:7]):04d}"
                tid = c.execute(
                    "INSERT INTO transactions (no,tanggal,jenis,customer_id,supplier_id,employee_id,keterangan,jatuh_tempo,total,"
                    "status,dibuat_oleh,dibuat_pada) VALUES (?,?,?,?,?,?,?,?,?,'Draft',?,?)",
                    (nomor, b["tanggal"], b["jenis"], b["customer_id"], b["supplier_id"], b["employee_id"], b["keterangan"],
                     b["jatuh_tempo"], b["total"], user["id"], waktu_teks())).lastrowid
                lama, aksi = None, "buat draft"
            c.execute("INSERT INTO transaction_lines (transaction_id,item_id,akun,uraian,jumlah,harga,subtotal) VALUES (?,?,?,?,?,?,?)",
                      (tid, b["item_id"], b["kategori"], _uraian(b), b["jumlah"], b["harga"], b["total"]))
            catat(c, LOG_TRANSAKSI, aksi, "Berhasil", user=user, objek=nomor, nilai_lama=lama,
                  nilai_baru=f'{b["jenis"]} Rp{b["total"]:,.0f}')
            return True, f"Draft {nomor} tersimpan.", tid
    except Exception as e:  # gagal = tidak ada yang tersimpan
        catat_sendiri(LOG_TRANSAKSI, "simpan draft", "Gagal", user=user, keterangan=str(e)[:200])
        return False, f"Gagal menyimpan: {e}", None


def _baca(c, id_):
    return c.execute("SELECT * FROM transactions WHERE id = ?", (id_,)).fetchone()


# ------------------------------------------------------------------ posting
def posting(user: dict, id_: int):
    """Draft -> Diposting. Jurnal debit-kredit dibuat otomatis dalam satu proses."""
    try:
        with get_conn() as c:
            r = _baca(c, id_)
            if not r:
                return False, "Transaksi tidak ditemukan."
            if not owner(user) and r["dibuat_oleh"] != user["id"]:
                c.rollback()
                return tolak_akses(user, r["no"])
            if r["status"] != "Draft":
                return False, "Hanya draft yang bisa diposting."
            if not periode_terbuka(c, r["tanggal"]):
                catat(c, LOG_TRANSAKSI, "posting", "Ditolak", user=user, objek=r["no"], keterangan="Periode sudah ditutup")
                c.commit()
                return False, "Periode transaksi sudah ditutup."
            ln = c.execute("SELECT * FROM transaction_lines WHERE transaction_id = ?", (id_,)).fetchone()
            sumber = (ln["uraian"] or "").split(" | ")[0]
            jurnal = susun_jurnal(r["jenis"], sumber, ln["akun"], r["total"])
            if abs(sum(x[1] for x in jurnal) - sum(x[2] for x in jurnal)) > 0.001:
                raise ValueError("Total debit tidak sama dengan total kredit.")
            e = c.execute("INSERT INTO journal_entries (transaction_id,tanggal,jenis,keterangan,dibuat_oleh,dibuat_pada) "
                          "VALUES (?,?,'otomatis',?,?,?)",
                          (id_, r["tanggal"], f'{r["no"]} - {r["keterangan"]}', user["id"], waktu_teks())).lastrowid
            for kode, dr, kr in jurnal:
                c.execute("INSERT INTO journal_lines (entry_id,kode_akun,debit,kredit) VALUES (?,?,?,?)", (e, kode, dr, kr))
            c.execute("UPDATE transactions SET status='Diposting', diposting_pada=? WHERE id=?", (waktu_teks(), id_))
            catat(c, LOG_TRANSAKSI, "posting", "Berhasil", user=user, objek=r["no"], nilai_lama="Draft", nilai_baru="Diposting")
            return True, f'Transaksi {r["no"]} diposting dan jurnal terbentuk.'
    except Exception as e:
        catat_sendiri(LOG_TRANSAKSI, "posting", "Gagal", user=user, objek=str(id_), keterangan=str(e)[:200])
        return False, f"Gagal memposting: {e}"


# ------------------------------------------------------------------ hapus (draft = permanen, diposting = batal)
def hapus(user: dict, id_: int, alasan: str = ""):
    try:
        with get_conn() as c:
            r = _baca(c, id_)
            if not r:
                return False, "Transaksi tidak ditemukan."
            milik = r["dibuat_oleh"] == user["id"]
            if not owner(user):
                if not milik:
                    c.rollback()
                    return tolak_akses(user, r["no"])
                if r["status"] == "Diposting" and ambil_set("karyawan_hapus", "Milik sendiri") not in ("Milik sendiri", "Semua"):
                    c.rollback()
                    return tolak_akses(user, r["no"])
            if r["status"] == "Dibatalkan":
                return False, "Transaksi ini sudah dibatalkan."
            if r["status"] == "Draft":
                c.execute("DELETE FROM transaction_lines WHERE transaction_id = ?", (id_,))
                c.execute("DELETE FROM transactions WHERE id = ?", (id_,))
                catat(c, LOG_TRANSAKSI, "hapus draft", "Berhasil", user=user, objek=r["no"],
                      nilai_lama=f'{r["jenis"]} Rp{r["total"]:,.0f}')
                return True, f'Draft {r["no"]} dihapus permanen (tercatat di audit trail).'
            alasan = (alasan or "").strip()
            if not alasan:
                return False, "Alasan penghapusan wajib diisi."
            if not periode_terbuka(c, r["tanggal"]):
                catat(c, LOG_TRANSAKSI, "hapus (batal)", "Ditolak", user=user, objek=r["no"], keterangan="Periode sudah ditutup")
                c.commit()
                return False, "Periode transaksi sudah ditutup, tidak bisa dihapus."
            e = c.execute("INSERT INTO journal_entries (transaction_id,tanggal,jenis,keterangan,dibuat_oleh,dibuat_pada) "
                          "VALUES (?,?,'pembalik',?,?,?)",
                          (id_, r["tanggal"], f'Pembatalan {r["no"]}: {alasan}', user["id"], waktu_teks())).lastrowid
            for ln in c.execute("SELECT kode_akun,debit,kredit FROM journal_lines WHERE entry_id IN "
                                "(SELECT id FROM journal_entries WHERE transaction_id = ? AND jenis = 'otomatis')", (id_,)).fetchall():
                c.execute("INSERT INTO journal_lines (entry_id,kode_akun,debit,kredit) VALUES (?,?,?,?)",
                          (e, ln["kode_akun"], ln["kredit"], ln["debit"]))
            c.execute("UPDATE transactions SET status='Dibatalkan', alasan_batal=?, dibatalkan_oleh=? WHERE id=?",
                      (alasan, user["id"], id_))
            catat(c, LOG_TRANSAKSI, "hapus (batal)", "Berhasil", user=user, objek=r["no"],
                  nilai_lama="Diposting", nilai_baru="Dibatalkan", keterangan=alasan)
            return True, f'Transaksi {r["no"]} dibatalkan. Jurnal pembalik dibuat dan data asli tetap tampil.'
    except Exception as e:
        catat_sendiri(LOG_TRANSAKSI, "hapus", "Gagal", user=user, objek=str(id_), keterangan=str(e)[:200])
        return False, f"Gagal menghapus: {e}"


# ------------------------------------------------------------------ baca
def boleh_hapus(user: dict, r: dict) -> bool:
    if r["status"] == "Dibatalkan":
        return False
    if owner(user):
        return True
    if r["dibuat_oleh"] != user["id"]:
        return False
    return r["status"] == "Draft" or ambil_set("karyawan_hapus", "Milik sendiri") in ("Milik sendiri", "Semua")


def daftar(user: dict, status: str | None = None, cari: str = "", mulai: str | None = None, akhir: str | None = None) -> list:
    """Karyawan hanya melihat transaksi miliknya (dipaksa di backend)."""
    kond, par = ["1=1"], []
    if not owner(user):
        kond.append("t.dibuat_oleh = ?")
        par.append(user["id"])
    if status:
        kond.append("t.status = ?")
        par.append(status)
    if cari.strip():
        kond.append("(t.no LIKE ? OR t.keterangan LIKE ?)")
        par += [f"%{cari.strip()}%"] * 2
    if mulai:
        kond.append("t.tanggal >= ?")
        par.append(mulai)
    if akhir:
        kond.append("t.tanggal <= ?")
        par.append(akhir)
    return semua("SELECT t.*, u.nama AS pembuat, COALESCE(c.nama, s.nama, e.nama) AS pihak FROM transactions t "
                 "LEFT JOIN users u ON u.id = t.dibuat_oleh LEFT JOIN customers c ON c.id = t.customer_id "
                 "LEFT JOIN suppliers s ON s.id = t.supplier_id LEFT JOIN employees e ON e.id = t.employee_id "
                 f"WHERE {' AND '.join(kond)} ORDER BY t.tanggal DESC, t.id DESC", par)


def ambil(user: dict, id_: int):
    """Detail satu transaksi. Jurnal hanya dikirim untuk Owner (Karyawan tidak boleh membuka jurnal)."""
    r = satu("SELECT t.*, u.nama AS pembuat FROM transactions t LEFT JOIN users u ON u.id = t.dibuat_oleh WHERE t.id = ?", (id_,))
    if not r or (not owner(user) and r["dibuat_oleh"] != user["id"]):
        return None
    r["baris"] = semua("SELECT l.*, i.nama AS item_nama, i.satuan FROM transaction_lines l LEFT JOIN items i ON i.id = l.item_id "
                       "WHERE l.transaction_id = ?", (id_,))
    r["sumber"] = (r["baris"][0]["uraian"] or "").split(" | ")[0] if r["baris"] else ""
    r["kategori"] = r["baris"][0]["akun"] if r["baris"] else None
    r["jurnal"] = []
    if owner(user):
        r["jurnal"] = semua("SELECT e.jenis, l.kode_akun, a.nama AS akun, l.debit, l.kredit FROM journal_entries e "
                            "JOIN journal_lines l ON l.entry_id = e.id LEFT JOIN accounts a ON a.kode = l.kode_akun "
                            "WHERE e.transaction_id = ? ORDER BY e.id, l.id", (id_,))
    return r

"""
akuntansi.py - Modul Akuntansi (Modul bab 9, khusus Owner)
Jurnal umum, buku besar, neraca saldo, jurnal penyesuaian (persediaan fisik, penyusutan, dll),
laporan keuangan, penutupan bulanan, jurnal penutup akhir tahun, dan jurnal pembalik.
Semua angka dibaca dari tabel jurnal dan saldo awal (satu sumber data).
"""

from calendar import monthrange
from datetime import date, timedelta

from database import (LOG_TRANSAKSI, TIDAK_BERHAK, ambil_set, catat, catat_sendiri, get_conn, hari_ini, owner, semua,
                      satu, tolak_akses, waktu_teks)
from transaksi import periode_terbuka

TOLERANSI = 0.5
KEL_ASET = ("Aset lancar", "Aset tetap", "Kontra aset")
KEL_LIAB = ("Liabilitas jangka pendek", "Liabilitas jangka panjang")
KEL_PENJUALAN = ("Pendapatan", "Kontra pendapatan")
KEL_BELI = ("Pembelian (metode fisik)", "Kontra pembelian")
KEL_BEBAN = ("Beban operasional",)
KEL_SEMENTARA = ("Pendapatan", "Kontra pendapatan", "Pendapatan lain", "Pembelian (metode fisik)", "Kontra pembelian",
                 "Beban operasional", "Akun sementara")
PERSEDIAAN_BAHAN = ("1104", "1105", "1106")
PERSEDIAAN_IKAN = "1107"
PERSEDIAAN = PERSEDIAAN_BAHAN + (PERSEDIAAN_IKAN,)
KAS_BANK = ("1101", "1102")
IKHTISAR, MODAL, PRIVE = "3103", "3101", "3102"

MODE = {"semua": "", "sebelum_penyesuaian": "AND e.jenis NOT IN ('penyesuaian','penutup')",
        "setelah_penyesuaian": "AND e.jenis != 'penutup'"}


def waktu_sekarang_iso() -> str:
    from database import sekarang
    return sekarang().isoformat()


def nomor_jurnal(id_: int) -> str:
    return f"JV-{id_:04d}"


def rentang_bulan(bulan: str):
    y, m = map(int, bulan.split("-"))
    return date(y, m, 1), date(y, m, monthrange(y, m)[1])


def tgl_penyesuaian(bulan: str) -> date:
    """Jurnal penyesuaian bertanggal akhir bulan, atau hari ini bila bulan itu masih berjalan."""
    return min(rentang_bulan(bulan)[1], hari_ini())


def bulan_berikut(bulan: str) -> str:
    y, m = map(int, bulan.split("-"))
    return f"{y + (m == 12)}-{(m % 12) + 1:02d}"


def rentang_tahun_buku(tahun: int):
    m = int(ambil_set("tahun_buku_mulai", "1") or 1)
    if m == 1:
        return date(tahun, 1, 1), date(tahun, 12, 31)
    awal = date(tahun, m, 1)
    return awal, date(tahun + 1, m, 1) - timedelta(days=1)


# ------------------------------------------------------------------ saldo dasar
def net_hingga(conn, tgl: date, mode: str = "semua", eksklusif: bool = False) -> dict:
    """{kode_akun: debit - kredit}: saldo awal (tanggal <= tgl) ditambah jurnal sampai tgl."""
    op = "<" if eksklusif else "<="
    sql = f"""SELECT kode_akun AS k, SUM(n) AS n FROM (
        SELECT kode_akun, debit - kredit AS n FROM opening_balances WHERE tanggal <= :t
        UNION ALL
        SELECT l.kode_akun, l.debit - l.kredit FROM journal_lines l JOIN journal_entries e ON e.id = l.entry_id
        WHERE e.tanggal {op} :t {MODE[mode]}) GROUP BY kode_akun"""
    return {r["k"]: r["n"] for r in conn.execute(sql, {"t": tgl.isoformat()})}


def gerak(conn, mulai: date, akhir: date, mode: str = "semua") -> dict:
    """{kode_akun: (debit, kredit)} di dalam rentang."""
    sql = f"""SELECT kode_akun AS k, SUM(dr) AS dr, SUM(kr) AS kr FROM (
        SELECT kode_akun, debit AS dr, kredit AS kr FROM opening_balances WHERE tanggal > :m AND tanggal <= :a
        UNION ALL
        SELECT l.kode_akun, l.debit, l.kredit FROM journal_lines l JOIN journal_entries e ON e.id = l.entry_id
        WHERE e.tanggal >= :m AND e.tanggal <= :a {MODE[mode]}) GROUP BY kode_akun"""
    return {r["k"]: (r["dr"], r["kr"]) for r in conn.execute(sql, {"m": mulai.isoformat(), "a": akhir.isoformat()})}


def _akun(conn, aktif_saja=True) -> list:
    w = "WHERE status='Aktif'" if aktif_saja else ""
    return [dict(r) for r in conn.execute(f"SELECT kode, nama, kelompok, saldo_normal FROM accounts {w} ORDER BY kode")]


def _kelompok(conn) -> dict:
    return {r["kode"]: r["kelompok"] for r in conn.execute("SELECT kode, kelompok FROM accounts")}


def saldo_akun(kode: str, tgl: date, mode: str = "semua") -> float:
    with get_conn() as c:
        return net_hingga(c, tgl, mode).get(kode, 0.0)


# ------------------------------------------------------------------ buku besar & neraca saldo
def buku_besar(mulai: date, akhir: date):
    """Baris per akun: saldo awal, debit, kredit, saldo akhir (mengikuti saldo normal)."""
    with get_conn() as c:
        akun = _akun(c, False)
        awal = net_hingga(c, mulai, "semua", True)
        g = gerak(c, mulai, akhir)
    out = []
    for a in akun:
        s = 1 if a["saldo_normal"] == "Debit" else -1
        n0 = awal.get(a["kode"], 0.0)
        dr, kr = g.get(a["kode"], (0.0, 0.0))
        if abs(n0) < 0.005 and not dr and not kr:
            continue
        out.append({**a, "awal": s * n0, "debit": dr, "kredit": kr, "akhir": s * (n0 + dr - kr)})
    return out


def rincian_akun(kode: str, mulai: date, akhir: date) -> dict:
    """Mutasi satu akun dengan saldo berjalan."""
    with get_conn() as c:
        a = c.execute("SELECT kode, nama, saldo_normal FROM accounts WHERE kode = ?", (kode,)).fetchone()
        if not a:
            return {}
        s = 1 if a["saldo_normal"] == "Debit" else -1
        n0 = net_hingga(c, mulai, "semua", True).get(kode, 0.0)
        baris = [dict(r) for r in c.execute(
            """SELECT tanggal, 0 AS urut, 'Saldo awal' AS keterangan, '' AS no_jurnal, debit, kredit
               FROM opening_balances WHERE kode_akun = ? AND tanggal > ? AND tanggal <= ?
               UNION ALL
               SELECT e.tanggal, 1, e.keterangan, printf('JV-%04d', e.id), l.debit, l.kredit
               FROM journal_lines l JOIN journal_entries e ON e.id = l.entry_id
               WHERE l.kode_akun = ? AND e.tanggal >= ? AND e.tanggal <= ? ORDER BY 1, 2, 4""",
            (kode, mulai.isoformat(), akhir.isoformat(), kode, mulai.isoformat(), akhir.isoformat()))]
    saldo = s * n0
    for b in baris:
        saldo += s * (b["debit"] - b["kredit"])
        b["saldo"] = saldo
    return {"kode": a["kode"], "nama": a["nama"], "awal": s * n0, "baris": baris, "akhir": saldo}


def neraca_saldo(sampai: date, mode: str):
    """([{kode,nama,kelompok,debit,kredit}], total debit, total kredit). Akun bersaldo nol tidak ditampilkan."""
    with get_conn() as c:
        akun = _akun(c, False)
        n = net_hingga(c, sampai, mode)
    out, td, tk = [], 0.0, 0.0
    for a in akun:
        v = n.get(a["kode"], 0.0)
        if abs(v) < 0.005:
            continue
        dr, kr = (v, 0.0) if v > 0 else (0.0, -v)
        td, tk = td + dr, tk + kr
        out.append({**a, "debit": dr, "kredit": kr})
    return out, td, tk


# ------------------------------------------------------------------ jurnal umum
def daftar_jurnal(mulai: date, akhir: date, jenis: tuple | None = None, cari: str = "") -> list:
    kond, par = ["e.tanggal BETWEEN ? AND ?"], [mulai.isoformat(), akhir.isoformat()]
    if jenis:
        kond.append(f"e.jenis IN ({','.join('?' * len(jenis))})")
        par += list(jenis)
    if cari.strip():
        kond.append("(e.keterangan LIKE ? OR printf('JV-%04d', e.id) LIKE ? OR t.no LIKE ?)")
        par += [f"%{cari.strip()}%"] * 3
    return semua(
        "SELECT e.id, printf('JV-%04d', e.id) AS no_jurnal, e.tanggal, e.jenis, e.keterangan, t.no AS no_transaksi, "
        "(SELECT COALESCE(SUM(debit),0) FROM journal_lines WHERE entry_id = e.id) AS debit, "
        "(SELECT COALESCE(SUM(kredit),0) FROM journal_lines WHERE entry_id = e.id) AS kredit "
        f"FROM journal_entries e LEFT JOIN transactions t ON t.id = e.transaction_id WHERE {' AND '.join(kond)} "
        "ORDER BY e.tanggal DESC, e.id DESC", par)


def baris_jurnal(entry_id: int) -> list:
    return semua("SELECT l.kode_akun, a.nama AS akun, l.debit, l.kredit FROM journal_lines l "
                 "LEFT JOIN accounts a ON a.kode = l.kode_akun WHERE l.entry_id = ? ORDER BY l.id", (entry_id,))


def _buat_jurnal(conn, user, tgl_iso: str, jenis: str, ket: str, baris: list, kunci: str | None = None,
                 transaction_id=None) -> int:
    """Tulis satu jurnal. baris = [(kode, debit, kredit)]. Debit harus sama dengan kredit."""
    baris = [(k, round(float(d or 0), 2), round(float(kr or 0), 2)) for k, d, kr in baris if (d or 0) or (kr or 0)]
    if len(baris) < 2:
        raise ValueError("Jurnal minimal memiliki dua baris.")
    if any(d < 0 or kr < 0 for _, d, kr in baris) or any(d and kr for _, d, kr in baris):
        raise ValueError("Satu baris hanya boleh diisi debit atau kredit, dan tidak boleh negatif.")
    if abs(sum(b[1] for b in baris) - sum(b[2] for b in baris)) > 0.005:
        raise ValueError("Total debit harus sama dengan total kredit.")
    for k, _, _ in baris:
        if not conn.execute("SELECT 1 FROM accounts WHERE kode = ? AND status = 'Aktif'", (k,)).fetchone():
            raise ValueError(f"Akun {k} tidak ditemukan atau tidak aktif.")
    e = conn.execute("INSERT INTO journal_entries (transaction_id,tanggal,jenis,keterangan,kunci,dibuat_oleh,dibuat_pada) "
                     "VALUES (?,?,?,?,?,?,?)", (transaction_id, tgl_iso, jenis, ket, kunci, user["id"] if user else None,
                                                waktu_teks())).lastrowid
    for k, d, kr in baris:
        conn.execute("INSERT INTO journal_lines (entry_id,kode_akun,debit,kredit) VALUES (?,?,?,?)", (e, k, d, kr))
    return e


def jurnal_manual(user: dict, tgl: date, ket: str, baris: list, jenis: str = "manual"):
    """Jurnal manual Owner. baris = [(kode, debit, kredit)]."""
    if not owner(user):
        return tolak_akses(user, "Jurnal manual")
    ket = (ket or "").strip()
    if not ket:
        return False, "Keterangan jurnal wajib diisi."
    try:
        with get_conn() as c:
            if not periode_terbuka(c, tgl.isoformat()):
                return False, "Periode sudah ditutup."
            e = _buat_jurnal(c, user, tgl.isoformat(), jenis, ket, baris)
            catat(c, LOG_TRANSAKSI, f"jurnal {jenis}", "Berhasil", user=user, objek=nomor_jurnal(e), nilai_baru=ket)
            return True, f"Jurnal {nomor_jurnal(e)} tersimpan."
    except Exception as ex:
        catat_sendiri(LOG_TRANSAKSI, f"jurnal {jenis}", "Gagal", user=user, keterangan=str(ex)[:200])
        return False, str(ex)


def batalkan_jurnal(user: dict, entry_id: int, alasan: str):
    """Jurnal manual/penyesuaian tidak dihapus: dibatalkan dengan jurnal pembalik (jejak tetap ada)."""
    if not owner(user):
        return tolak_akses(user, nomor_jurnal(entry_id))
    if not (alasan or "").strip():
        return False, "Alasan wajib diisi."
    try:
        with get_conn() as c:
            e = c.execute("SELECT * FROM journal_entries WHERE id = ?", (entry_id,)).fetchone()
            if not e or e["jenis"] not in ("manual", "penyesuaian") or e["transaction_id"]:
                return False, "Hanya jurnal manual atau penyesuaian yang bisa dibatalkan di sini."
            if c.execute("SELECT 1 FROM journal_entries WHERE kunci = ?", (f"batal:{entry_id}",)).fetchone():
                return False, "Jurnal ini sudah dibatalkan."
            if not periode_terbuka(c, e["tanggal"]):
                return False, "Periode sudah ditutup."
            lines = c.execute("SELECT kode_akun,debit,kredit FROM journal_lines WHERE entry_id = ?", (entry_id,)).fetchall()
            n = _buat_jurnal(c, user, e["tanggal"], "pembalik", f'Pembatalan {nomor_jurnal(entry_id)}: {alasan.strip()}',
                             [(x["kode_akun"], x["kredit"], x["debit"]) for x in lines], kunci=f"batal:{entry_id}")
            if e["kunci"]:  # kunci dilepas agar jurnal yang sama bisa dibuat ulang dengan benar
                c.execute("UPDATE journal_entries SET kunci = ? WHERE id = ?", (f'{e["kunci"]}#batal{entry_id}', entry_id))
            c.execute("DELETE FROM depreciation_log WHERE entry_id = ?", (entry_id,))
            catat(c, LOG_TRANSAKSI, "batal jurnal", "Berhasil", user=user, objek=nomor_jurnal(entry_id),
                  nilai_baru=nomor_jurnal(n), keterangan=alasan.strip())
            return True, f"Jurnal {nomor_jurnal(entry_id)} dibatalkan dengan jurnal pembalik {nomor_jurnal(n)}."
    except Exception as ex:
        return False, str(ex)


# ------------------------------------------------------------------ jurnal penyesuaian (9.3)
def nilai_stok_final(bulan: str) -> dict:
    """{kode_akun_persediaan: nilai} dari stok opname FINAL terakhir tiap item dalam bulan itu."""
    mulai, akhir = rentang_bulan(bulan)
    rows = semua("SELECT s.item_id, s.nilai, i.akun_persediaan AS akun FROM stock_counts s JOIN items i ON i.id = s.item_id "
                 "WHERE s.status = 'Final' AND s.tanggal BETWEEN ? AND ? ORDER BY s.tanggal, s.id",
                 (mulai.isoformat(), akhir.isoformat()))
    per_item = {}
    for r in rows:
        per_item[r["item_id"]] = (r["akun"], r["nilai"] or 0)   # yang terakhir menimpa
    out = {}
    for akun, nilai in per_item.values():
        if akun:
            out[akun] = out.get(akun, 0) + nilai
    return out


def _perlu_persediaan(saldo_awal: float, akhir: float) -> bool:
    return abs(saldo_awal) >= 0.005 or abs(akhir) >= 0.005


def jurnal_persediaan(user: dict, bulan: str):
    """Persediaan akhir dari stok opname final (metode fisik, pendekatan Ikhtisar Laba Rugi, Modul 9.2)."""
    if not owner(user):
        return tolak_akses(user, "Penyesuaian persediaan")
    if bulan > hari_ini().strftime("%Y-%m"):
        return False, "Periode belum berjalan."
    tgl = tgl_penyesuaian(bulan)
    nilai = nilai_stok_final(bulan)
    if not nilai:
        return False, "Belum ada stok opname yang final pada bulan ini."
    dibuat = []
    try:
        with get_conn() as c:
            if not periode_terbuka(c, tgl.isoformat()):
                return False, "Periode sudah ditutup."
            saldo = net_hingga(c, rentang_bulan(bulan)[1], "sebelum_penyesuaian")
            for kode, akhir in sorted(nilai.items()):
                kunci = f"persediaan:{kode}:{bulan}"
                if c.execute("SELECT 1 FROM journal_entries WHERE kunci = ?", (kunci,)).fetchone():
                    continue
                awal = saldo.get(kode, 0.0)
                if not _perlu_persediaan(awal, akhir):
                    continue   # persediaan awal dan akhir sama-sama nol: tidak ada yang disesuaikan
                baris = [(IKHTISAR, awal, 0), (kode, 0, awal), (kode, akhir, 0), (IKHTISAR, 0, akhir)]
                nm = c.execute("SELECT nama FROM accounts WHERE kode = ?", (kode,)).fetchone()["nama"]
                e = _buat_jurnal(c, user, tgl.isoformat(), "penyesuaian",
                                 f"Persediaan akhir {nm} (stok opname {bulan}): hapus persediaan awal lalu catat persediaan akhir",
                                 baris, kunci=kunci)
                dibuat.append(nomor_jurnal(e))
            catat(c, LOG_TRANSAKSI, "jurnal penyesuaian persediaan", "Berhasil", user=user, objek=bulan,
                  nilai_baru=", ".join(dibuat) or "tidak ada yang baru")
    except Exception as ex:
        return False, str(ex)
    return True, ("Jurnal dibuat: " + ", ".join(dibuat)) if dibuat else "Semua jurnal persediaan bulan ini sudah ada atau tidak perlu dibuat."


def penyusutan_bulanan(asset: dict) -> float | None:
    """Garis lurus. None bila data aset belum dikonfirmasi (tidak diisi angka karangan)."""
    if asset["harga_perolehan"] is None or asset["umur_tahun"] is None or asset["tgl_perolehan"] is None:
        return None
    return round((asset["harga_perolehan"] - (asset["nilai_sisa"] or 0)) / (asset["umur_tahun"] * 12), 2)


def jurnal_penyusutan(user: dict, bulan: str):
    if not owner(user):
        return tolak_akses(user, "Penyusutan")
    if bulan > hari_ini().strftime("%Y-%m"):
        return False, "Periode belum berjalan."
    mulai, akhir = rentang_bulan(bulan)
    tgl = tgl_penyesuaian(bulan)
    lewat, dibuat = [], 0
    try:
        with get_conn() as c:
            if not periode_terbuka(c, akhir.isoformat()):
                return False, "Periode sudah ditutup."
            for a in c.execute("SELECT * FROM fixed_assets WHERE status='Aktif' ORDER BY kode").fetchall():
                a = dict(a)
                bulanan = penyusutan_bulanan(a)
                if bulanan is None or not a["akun_aset"] or not a["akun_akumulasi"]:
                    lewat.append(a["nama"])
                    continue
                if a["tgl_perolehan"] > akhir.isoformat():
                    continue
                if c.execute("SELECT 1 FROM depreciation_log WHERE asset_id=? AND bulan=?", (a["id"], bulan)).fetchone():
                    continue
                total_susut = (a["harga_perolehan"] or 0) - (a["nilai_sisa"] or 0)
                terpakai = (a["akumulasi_awal"] or 0) + (c.execute(
                    "SELECT COALESCE(SUM(jumlah),0) FROM depreciation_log WHERE asset_id = ?", (a["id"],)).fetchone()[0])
                jumlah = round(min(bulanan, max(total_susut - terpakai, 0)), 2)
                if jumlah <= 0:
                    continue
                e = _buat_jurnal(c, user, tgl.isoformat(), "penyesuaian", f'Penyusutan {a["nama"]} bulan {bulan}',
                                 [("6106", jumlah, 0), (a["akun_akumulasi"], 0, jumlah)], kunci=f'susut:{a["id"]}:{bulan}')
                c.execute("INSERT INTO depreciation_log (asset_id,bulan,jumlah,entry_id) VALUES (?,?,?,?)", (a["id"], bulan, jumlah, e))
                dibuat += 1
            catat(c, LOG_TRANSAKSI, "jurnal penyusutan", "Berhasil", user=user, objek=bulan, nilai_baru=f"{dibuat} jurnal")
    except Exception as ex:
        return False, str(ex)
    pesan = f"{dibuat} jurnal penyusutan dibuat."
    if lewat:
        pesan += " Dilewati karena data belum dikonfirmasi: " + ", ".join(lewat) + "."
    return True, pesan


def jurnal_penyesuaian_lain(user: dict, bulan: str, jenis: str, jumlah: float, ket: str, akun_beban: str | None = None):
    """jenis: perlengkapan | muka | utang_gaji. Keterangan wajib."""
    if not owner(user):
        return tolak_akses(user, "Penyesuaian")
    if jumlah <= 0:
        return False, "Jumlah harus lebih dari 0."
    if not (ket or "").strip():
        return False, "Keterangan jurnal penyesuaian wajib diisi."
    if bulan > hari_ini().strftime("%Y-%m"):
        return False, "Periode belum berjalan."
    akhir = tgl_penyesuaian(bulan).isoformat()
    peta = {"perlengkapan": ("6105", "1108", "Perlengkapan terpakai"),
            "muka": (akun_beban or "6107", "1109", "Biaya dibayar di muka yang sudah terpakai"),
            "utang_gaji": ("6101", "2102", "Utang gaji hari kerja yang belum dibayar")}
    dr, kr, nama = peta[jenis]
    try:
        with get_conn() as c:
            if not periode_terbuka(c, akhir):
                return False, "Periode sudah ditutup."
            n = c.execute("SELECT COUNT(*) FROM journal_entries WHERE kunci LIKE ?", (f"{jenis}:{bulan}:%",)).fetchone()[0]
            e = _buat_jurnal(c, user, akhir, "penyesuaian", f"{nama}: {ket.strip()}", [(dr, jumlah, 0), (kr, 0, jumlah)],
                             kunci=f"{jenis}:{bulan}:{n + 1}")
            catat(c, LOG_TRANSAKSI, f"jurnal penyesuaian {jenis}", "Berhasil", user=user, objek=nomor_jurnal(e), nilai_baru=jumlah,
                  keterangan=ket.strip())
            return True, f"Jurnal {nomor_jurnal(e)} tersimpan."
    except Exception as ex:
        return False, str(ex)


# ------------------------------------------------------------------ piutang & utang
def _fifo(saldo_awal: float, faktur: list, bayar: float):
    """Alokasikan pembayaran ke tagihan tertua. faktur = [(tgl, tempo, jumlah)]. Return sisa tagihan [(tempo, sisa)]."""
    sisa = []
    if saldo_awal > 0:
        sisa.append([None, saldo_awal])
    sisa += [[t, j] for _, t, j in sorted(faktur)]
    for s in sisa:
        pakai = min(s[1], bayar)
        s[1] -= pakai
        bayar -= pakai
    return [(t, j) for t, j in sisa if j > 0.005]


def rincian_pihak(jenis: str) -> list:
    """jenis: 'piutang' (customer) atau 'utang' (supplier). [{id,kode,nama,saldo,terlambat}]."""
    if jenis == "piutang":
        tabel, kol, awal, tj, tb, tr, sr = "customers", "customer_id", "saldo_awal_piutang", "penjualan_kredit", "penerimaan_piutang", "retur_penjualan", "Piutang"
    else:
        tabel, kol, awal, tj, tb, tr, sr = "suppliers", "supplier_id", "saldo_awal_utang", "pembelian_kredit", "pembayaran_utang", "retur_pembelian", "Utang"
    out = []
    hari = hari_ini().isoformat()
    for p in semua(f"SELECT id, kode, nama, {awal} AS awal FROM {tabel} ORDER BY kode"):
        trx = semua(f"SELECT t.jenis, t.tanggal, t.jatuh_tempo, t.total, "
                    f"(SELECT uraian FROM transaction_lines WHERE transaction_id = t.id LIMIT 1) AS uraian "
                    f"FROM transactions t WHERE t.{kol} = ? AND t.status = 'Diposting'", (p["id"],))
        faktur = [(t["tanggal"], t["jatuh_tempo"], t["total"]) for t in trx if t["jenis"] == tj]
        bayar = sum(t["total"] for t in trx if t["jenis"] == tb)
        bayar += sum(t["total"] for t in trx if t["jenis"] == tr and (t["uraian"] or "").startswith(sr))
        sisa = _fifo(p["awal"] or 0, faktur, bayar)
        saldo = sum(j for _, j in sisa)
        telat = sum(j for t, j in sisa if t and t < hari)
        if saldo > 0.005 or telat:
            out.append({"id": p["id"], "kode": p["kode"], "nama": p["nama"], "saldo": saldo, "terlambat": telat})
    return out


# ------------------------------------------------------------------ laporan keuangan (9.4)
def _daftar_nilai(akun: list, n: dict, kel: tuple, tanda: int) -> list:
    out = []
    for a in akun:
        if a["kelompok"] in kel:
            v = tanda * n.get(a["kode"], 0.0)
            if abs(v) >= 0.005:
                out.append({"kode": a["kode"], "nama": a["nama"], "nilai": v})
    return out


def laba_rugi(mulai: date, akhir: date) -> dict:
    """Laba rugi periode: penjualan bersih, HPP (metode fisik), laba kotor, beban, laba bersih."""
    with get_conn() as c:
        akun = _akun(c, False)
        g = gerak(c, mulai, akhir, "setelah_penyesuaian")
        awal = net_hingga(c, mulai, "setelah_penyesuaian", True)
        sampai = net_hingga(c, akhir, "setelah_penyesuaian")

    def mut(kode):  # debit - kredit dalam periode
        dr, kr = g.get(kode, (0.0, 0.0))
        return dr - kr

    def daftar(kel, tanda):
        out = []
        for a in akun:
            if a["kelompok"] in kel and abs(mut(a["kode"])) >= 0.005:
                out.append({"kode": a["kode"], "nama": a["nama"], "nilai": tanda * mut(a["kode"])})
        return out

    pendapatan = daftar(("Pendapatan",), -1)
    kontra = daftar(("Kontra pendapatan",), 1)
    penjualan_bersih = sum(x["nilai"] for x in pendapatan) - sum(x["nilai"] for x in kontra)
    pembelian = daftar(("Pembelian (metode fisik)",), 1)
    kontra_beli = daftar(("Kontra pembelian",), 1)   # kontra pembelian bersaldo kredit: mut negatif -> kurangi
    pembelian_bersih = sum(mut(a["kode"]) for a in akun if a["kelompok"] in KEL_BELI)
    persediaan_awal = sum(awal.get(k, 0.0) for k in PERSEDIAAN)
    persediaan_akhir = sum(sampai.get(k, 0.0) for k in PERSEDIAAN)
    awal_bahan = sum(awal.get(k, 0.0) for k in PERSEDIAAN_BAHAN)
    akhir_bahan = sum(sampai.get(k, 0.0) for k in PERSEDIAAN_BAHAN)
    pemakaian_bahan = awal_bahan + pembelian_bersih - akhir_bahan
    awal_ikan, akhir_ikan = awal.get(PERSEDIAAN_IKAN, 0.0), sampai.get(PERSEDIAAN_IKAN, 0.0)
    beban = daftar(KEL_BEBAN, 1)
    upah_produksi = 0.0
    if ambil_set("upah_ke_produksi", "Tidak") == "Ya":
        upah_produksi = mut("6101")
        beban = [b for b in beban if b["kode"] != "6101"]
    biaya_produksi = pemakaian_bahan + upah_produksi
    hpp = awal_ikan + biaya_produksi - akhir_ikan
    laba_kotor = penjualan_bersih - hpp
    total_beban = sum(b["nilai"] for b in beban)
    lain = daftar(("Pendapatan lain",), -1)
    total_lain = sum(x["nilai"] for x in lain)
    laba = laba_kotor - total_beban + total_lain
    return {"pendapatan": pendapatan, "kontra": kontra, "penjualan_bersih": penjualan_bersih,
            "pembelian": pembelian, "kontra_beli": kontra_beli, "pembelian_bersih": pembelian_bersih,
            "persediaan_awal": persediaan_awal, "persediaan_akhir": persediaan_akhir,
            "awal_bahan": awal_bahan, "akhir_bahan": akhir_bahan, "pemakaian_bahan": pemakaian_bahan,
            "upah_produksi": upah_produksi, "biaya_produksi": biaya_produksi, "awal_ikan": awal_ikan,
            "akhir_ikan": akhir_ikan, "hpp": hpp, "laba_kotor": laba_kotor, "beban": beban, "total_beban": total_beban,
            "lain": lain, "total_lain": total_lain, "laba": laba}


def neraca(tgl: date, eksklusif: bool = False) -> dict:
    """Neraca per tanggal. Ekuitas = Modal - Prive + laba berjalan (akun sementara yang belum ditutup)."""
    with get_conn() as c:
        akun = _akun(c, False)
        n = net_hingga(c, tgl, "semua", eksklusif)
    lancar = _daftar_nilai(akun, n, ("Aset lancar",), 1)
    tetap = _daftar_nilai(akun, n, ("Aset tetap",), 1)
    kontra = _daftar_nilai(akun, n, ("Kontra aset",), 1)   # saldo kontra aset bernilai kredit -> negatif
    liab = _daftar_nilai(akun, n, KEL_LIAB, -1)
    modal = n.get(MODAL, 0.0) * -1
    prive = n.get(PRIVE, 0.0)
    sementara = sum(n.get(a["kode"], 0.0) for a in akun if a["kelompok"] in KEL_SEMENTARA)
    laba_berjalan = -sementara
    eq_lain = sum(-n.get(a["kode"], 0.0) for a in akun if a["kelompok"] == "Ekuitas" and a["kode"] != MODAL)
    total_aset = sum(x["nilai"] for x in lancar + tetap + kontra)
    total_liab = sum(x["nilai"] for x in liab)
    ekuitas = modal + eq_lain - prive + laba_berjalan
    return {"lancar": lancar, "tetap": tetap, "kontra": kontra, "liab": liab, "modal": modal + eq_lain, "prive": prive,
            "laba_berjalan": laba_berjalan, "ekuitas": ekuitas, "total_aset": total_aset, "total_liab": total_liab,
            "aset_neto_tetap": sum(x["nilai"] for x in tetap + kontra),
            "seimbang": abs(total_aset - total_liab - ekuitas) <= TOLERANSI,
            "selisih": total_aset - total_liab - ekuitas}


def perubahan_ekuitas(mulai: date, akhir: date) -> dict:
    ekuitas_awal = neraca(mulai, True)["ekuitas"]   # saldo awal bertanggal <= mulai dihitung sebagai awal
    lr = laba_rugi(mulai, akhir)
    with get_conn() as c:
        g = gerak(c, mulai, akhir, "setelah_penyesuaian")
    dr_m, kr_m = g.get(MODAL, (0.0, 0.0))
    dr_p, kr_p = g.get(PRIVE, (0.0, 0.0))
    tambahan = kr_m - dr_m
    prive = dr_p - kr_p
    akhir_hitung = ekuitas_awal + lr["laba"] + tambahan - prive
    akhir_neraca = neraca(akhir)["ekuitas"]
    return {"awal": ekuitas_awal, "laba": lr["laba"], "prive": prive, "tambahan": tambahan, "akhir": akhir_hitung,
            "akhir_neraca": akhir_neraca, "sama": abs(akhir_hitung - akhir_neraca) <= TOLERANSI}


def arus_kas(mulai: date, akhir: date) -> dict:
    """Arus kas langsung dari jurnal yang menyentuh Kas/Bank, dikelompokkan menurut akun lawannya."""
    rows = semua(
        "SELECT e.id, e.keterangan, l.kode_akun, l.debit, l.kredit, a.kelompok FROM journal_entries e "
        "JOIN journal_lines l ON l.entry_id = e.id JOIN accounts a ON a.kode = l.kode_akun "
        "WHERE e.tanggal BETWEEN ? AND ? AND e.jenis != 'penutup' ORDER BY e.id, l.id", (mulai.isoformat(), akhir.isoformat()))
    per = {}
    for r in rows:
        per.setdefault(r["id"], []).append(r)
    kegiatan = {"Operasi": [], "Investasi": [], "Pendanaan": []}
    for eid, ls in per.items():
        kas = sum(x["debit"] - x["kredit"] for x in ls if x["kode_akun"] in KAS_BANK)
        if abs(kas) < 0.005:
            continue
        lawan = [x for x in ls if x["kode_akun"] not in KAS_BANK]
        kodes = {x["kode_akun"] for x in lawan}
        kel = {x["kelompok"] for x in lawan}
        if "Aset tetap" in kel or "Kontra aset" in kel:
            k = "Investasi"
        elif kodes & {MODAL, PRIVE, "2201"}:
            k = "Pendanaan"
        else:
            k = "Operasi"
        kegiatan[k].append({"keterangan": ls[0]["keterangan"], "nilai": kas})
    ringkas = {}
    for k, isi in kegiatan.items():
        masuk = sum(x["nilai"] for x in isi if x["nilai"] > 0)
        keluar = -sum(x["nilai"] for x in isi if x["nilai"] < 0)
        ringkas[k] = {"masuk": masuk, "keluar": keluar, "bersih": masuk - keluar}
    with get_conn() as c:
        awal = sum(net_hingga(c, mulai, "semua", True).get(k, 0.0) for k in KAS_BANK)
        akhir_buku = sum(net_hingga(c, akhir, "semua").get(k, 0.0) for k in KAS_BANK)
    perubahan = sum(v["bersih"] for v in ringkas.values())
    return {"ringkas": ringkas, "awal": awal, "perubahan": perubahan, "akhir": awal + perubahan, "akhir_buku": akhir_buku,
            "sama": abs(awal + perubahan - akhir_buku) <= TOLERANSI}


def neraca_lajur(sampai: date) -> dict:
    """Kertas kerja akhir periode: neraca saldo, penyesuaian, neraca saldo setelah penyesuaian, laba rugi, neraca."""
    with get_conn() as c:
        akun = _akun(c, False)
        sebelum = net_hingga(c, sampai, "sebelum_penyesuaian")
        sesudah = net_hingga(c, sampai, "setelah_penyesuaian")
    def dk(v):
        return (v, 0.0) if v > 0.005 else ((0.0, -v) if v < -0.005 else (0.0, 0.0))
    baris, tot = [], {k: [0.0, 0.0] for k in ("ns", "adj", "nss", "lr", "nr")}
    for a in akun:
        b, s = sebelum.get(a["kode"], 0.0), sesudah.get(a["kode"], 0.0)
        if abs(b) < 0.005 and abs(s) < 0.005:
            continue
        ns, adj, nss = dk(b), dk(s - b), dk(s)
        lr = nss if a["kelompok"] in KEL_SEMENTARA else (0.0, 0.0)
        nr = (0.0, 0.0) if a["kelompok"] in KEL_SEMENTARA else nss
        baris.append({"kode": a["kode"], "nama": a["nama"], "ns": ns, "adj": adj, "nss": nss, "lr": lr, "nr": nr})
        for k, v in (("ns", ns), ("adj", adj), ("nss", nss), ("lr", lr), ("nr", nr)):
            tot[k][0] += v[0]
            tot[k][1] += v[1]
    laba = tot["lr"][1] - tot["lr"][0]          # kredit - debit pada kolom laba rugi
    return {"baris": baris, "total": tot, "laba": laba, "seimbang": abs(tot["ns"][0] - tot["ns"][1]) <= 0.005
            and abs(tot["nss"][0] - tot["nss"][1]) <= 0.005}


def ringkasan(tgl: date) -> dict:
    """Angka pokok untuk dashboard (dari jurnal yang sama dengan laporan)."""
    nr = neraca(tgl)
    with get_conn() as c:
        n = net_hingga(c, tgl, "semua")
    kas_bank = sum(n.get(k, 0.0) for k in KAS_BANK)
    persediaan = sum(n.get(k, 0.0) for k in PERSEDIAAN)
    return {"aset": nr["total_aset"], "liabilitas": nr["total_liab"], "kas_bank": kas_bank, "persediaan": persediaan,
            "aset_tetap": nr["aset_neto_tetap"], "lainnya": nr["total_aset"] - kas_bank - persediaan - nr["aset_neto_tetap"],
            "piutang": n.get("1103", 0.0), "utang": -n.get("2101", 0.0)}


def seimbang_saldo_awal() -> bool:
    r = satu("SELECT COALESCE(SUM(debit),0) AS d, COALESCE(SUM(kredit),0) AS k FROM opening_balances")
    return abs(r["d"] - r["k"]) <= 0.005


# ------------------------------------------------------------------ periode (9.5)
def daftar_periode() -> list:
    with get_conn() as c:
        c.execute("INSERT OR IGNORE INTO periods (bulan) VALUES (?)", (hari_ini().strftime("%Y-%m"),))
    return semua("SELECT p.*, u.nama AS penutup FROM periods p LEFT JOIN users u ON u.id = p.ditutup_oleh ORDER BY bulan DESC")


def cek_penutupan(bulan: str) -> list:
    """Daftar syarat penutupan: [(teks, lolos)]."""
    mulai, akhir = rentang_bulan(bulan)
    hasil = []
    n = satu("SELECT COUNT(*) AS n FROM transactions WHERE status='Draft' AND tanggal BETWEEN ? AND ?",
             (mulai.isoformat(), akhir.isoformat()))["n"]
    hasil.append((f"Tidak ada draft transaksi ({n} draft)", n == 0))
    d = satu("SELECT COUNT(*) AS n FROM stock_counts WHERE status='Draft' AND tanggal BETWEEN ? AND ?",
             (mulai.isoformat(), akhir.isoformat()))["n"]
    hasil.append((f"Tidak ada stok opname yang masih draft ({d} draft)", d == 0))
    items = semua("SELECT id, nama, akun_persediaan FROM items WHERE status='Aktif' AND akun_persediaan IN ('1104','1105','1106','1107')")
    belum = [i["nama"] for i in items if not satu(
        "SELECT 1 AS x FROM stock_counts WHERE item_id=? AND status='Final' AND tanggal BETWEEN ? AND ?",
        (i["id"], mulai.isoformat(), akhir.isoformat()))]
    hasil.append(("Stok opname final untuk semua item persediaan" + (f" (belum: {', '.join(belum[:4])}{'...' if len(belum) > 4 else ''})" if belum else ""),
                  not belum))
    with get_conn() as c:
        saldo = net_hingga(c, akhir, "sebelum_penyesuaian")
    kurang = [k for k, v in nilai_stok_final(bulan).items()
              if _perlu_persediaan(saldo.get(k, 0.0), v) and not satu("SELECT 1 AS x FROM journal_entries WHERE kunci = ?", (f"persediaan:{k}:{bulan}",))]
    hasil.append(("Jurnal penyesuaian persediaan akhir sudah dibuat" + (f" (belum: akun {', '.join(kurang)})" if kurang else ""), not kurang))
    aset = semua("SELECT a.id, a.nama FROM fixed_assets a WHERE a.status='Aktif' AND a.harga_perolehan IS NOT NULL AND a.umur_tahun IS NOT NULL "
                 "AND a.tgl_perolehan IS NOT NULL AND a.tgl_perolehan <= ? AND a.akun_akumulasi IS NOT NULL", (akhir.isoformat(),))
    lewat = []
    for a in aset:
        if not satu("SELECT 1 AS x FROM depreciation_log WHERE asset_id=? AND bulan=?", (a["id"], bulan)):
            full = satu("SELECT harga_perolehan - COALESCE(nilai_sisa,0) - COALESCE(akumulasi_awal,0) - "
                        "(SELECT COALESCE(SUM(jumlah),0) FROM depreciation_log WHERE asset_id = ?) AS sisa FROM fixed_assets WHERE id = ?",
                        (a["id"], a["id"]))
            if full and full["sisa"] > 0.005:
                lewat.append(a["nama"])
    hasil.append(("Penyusutan aset tetap sudah dibuat" + (f" (belum: {', '.join(lewat[:3])})" if lewat else ""), not lewat))
    _, td, tk = neraca_saldo(akhir, "setelah_penyesuaian")
    hasil.append((f"Neraca saldo seimbang (debit {td:,.0f} / kredit {tk:,.0f})".replace(",", "."), abs(td - tk) <= 0.005))
    return hasil


def tutup_periode(user: dict, bulan: str):
    if not owner(user):
        return tolak_akses(user, f"Tutup periode {bulan}")
    try:
        with get_conn() as c:
            p = c.execute("SELECT * FROM periods WHERE bulan = ?", (bulan,)).fetchone()
            if not p:
                return False, "Periode tidak ditemukan."
            if p["status"] == "Tertutup":
                return False, "Periode sudah tertutup."
            if bulan > hari_ini().strftime("%Y-%m"):
                return False, "Periode belum berjalan."
            lebih_awal = c.execute("SELECT bulan FROM periods WHERE bulan < ? AND status='Terbuka' ORDER BY bulan LIMIT 1", (bulan,)).fetchone()
            if lebih_awal:
                return False, f"Tutup dulu periode {lebih_awal['bulan']} (urutkan dari bulan paling awal)."
        gagal = [t for t, ok in cek_penutupan(bulan) if not ok]
        if gagal:
            return False, "Syarat penutupan belum terpenuhi: " + "; ".join(gagal)
        with get_conn() as c:
            c.execute("UPDATE periods SET status='Tertutup', ditutup_oleh=?, tgl_tutup=? WHERE bulan=?", (user["id"], waktu_teks(), bulan))
            catat(c, LOG_TRANSAKSI, "tutup periode", "Berhasil", user=user, objek=bulan, nilai_lama="Terbuka", nilai_baru="Tertutup")
            c.execute("INSERT OR IGNORE INTO periods (bulan) VALUES (?)", (bulan_berikut(bulan),))
        return True, f"Periode {bulan} ditutup dan terkunci."
    except Exception as ex:
        return False, str(ex)


def buka_periode(user: dict, bulan: str, alasan: str):
    if not owner(user):
        return tolak_akses(user, f"Buka periode {bulan}")
    if not (alasan or "").strip():
        return False, "Alasan tertulis wajib diisi untuk membuka kembali periode."
    with get_conn() as c:
        p = c.execute("SELECT status FROM periods WHERE bulan = ?", (bulan,)).fetchone()
        if not p or p["status"] != "Tertutup":
            return False, "Periode ini tidak sedang tertutup."
        if c.execute("SELECT 1 FROM periods WHERE bulan > ? AND status='Tertutup'", (bulan,)).fetchone():
            return False, "Buka dulu periode yang lebih baru."
        if c.execute("SELECT 1 FROM journal_entries WHERE jenis='penutup' AND tanggal >= ?", (rentang_bulan(bulan)[0].isoformat(),)).fetchone():
            return False, "Tahun buku sudah ditutup dengan jurnal penutup. Periode ini tidak bisa dibuka."
        c.execute("UPDATE periods SET status='Terbuka', ditutup_oleh=NULL, tgl_tutup=NULL WHERE bulan=?", (bulan,))
        catat(c, LOG_TRANSAKSI, "buka kembali periode", "Berhasil", user=user, objek=bulan, nilai_lama="Tertutup",
              nilai_baru="Terbuka", keterangan=alasan.strip())
    return True, f"Periode {bulan} dibuka kembali."


# ------------------------------------------------------------------ penutupan akhir tahun (tahap 9-11)
def tutup_tahun(user: dict, tahun: int):
    """Jurnal penutup: pendapatan, pembelian, beban -> Ikhtisar Laba Rugi -> Modal; Prive -> Modal."""
    if not owner(user):
        return tolak_akses(user, f"Penutupan tahun {tahun}")
    awal, akhir = rentang_tahun_buku(tahun)
    if hari_ini() <= akhir:
        return False, f"Tahun buku {tahun} baru berakhir pada {akhir.isoformat()}. Jurnal penutup dibuat setelah tahun buku berakhir."
    try:
        with get_conn() as c:
            if c.execute("SELECT 1 FROM journal_entries WHERE kunci = ?", (f"penutup:{tahun}:1",)).fetchone():
                return False, "Tahun buku ini sudah ditutup."
            terbuka = c.execute("SELECT bulan FROM periods WHERE bulan BETWEEN ? AND ? AND status='Terbuka' ORDER BY bulan",
                                (awal.strftime("%Y-%m"), akhir.strftime("%Y-%m"))).fetchall()
            if terbuka:
                return False, "Tutup dulu semua periode bulanan di tahun buku ini (masih terbuka: " + ", ".join(r["bulan"] for r in terbuka) + ")."
            if not c.execute("SELECT 1 FROM periods WHERE bulan BETWEEN ? AND ?", (awal.strftime("%Y-%m"), akhir.strftime("%Y-%m"))).fetchone():
                return False, "Tidak ada periode pada tahun buku ini."
            akun = _akun(c, False)
            n = net_hingga(c, akhir, "semua")
            tutup = [a for a in akun if a["kelompok"] in KEL_SEMENTARA and a["kode"] != IKHTISAR and abs(n.get(a["kode"], 0)) >= 0.005]
            baris1 = []
            for a in tutup:
                v = n[a["kode"]]
                baris1.append((a["kode"], -v if v < 0 else 0, v if v > 0 else 0))   # nolkan saldo
            sv = sum(n[a["kode"]] for a in tutup)   # selisih bersih akun sementara (debit - kredit)
            baris1.append((IKHTISAR, sv if sv > 0 else 0, -sv if sv < 0 else 0))
            e1 = _buat_jurnal(c, user, akhir.isoformat(), "penutup", f"Penutupan akun sementara tahun {tahun} ke Ikhtisar Laba Rugi",
                              baris1, kunci=f"penutup:{tahun}:1") if tutup else None
            if not tutup:   # tidak ada aktivitas: tetap beri tanda tahun sudah ditutup
                c.execute("INSERT INTO journal_entries (tanggal,jenis,keterangan,kunci,dibuat_oleh,dibuat_pada) VALUES (?,?,?,?,?,?)",
                          (akhir.isoformat(), "penutup", f"Penutupan tahun {tahun} (tidak ada saldo akun sementara)",
                           f"penutup:{tahun}:1", user["id"], waktu_teks()))
            n2 = n.get(IKHTISAR, 0.0) + sv   # saldo Ikhtisar setelah jurnal 1 (debit - kredit); negatif = laba
            # n2 > 0 berarti rugi: kreditkan Ikhtisar, debitkan Modal. n2 < 0 berarti laba: sebaliknya.
            baris2 = [(IKHTISAR, 0, n2) if n2 > 0 else (IKHTISAR, -n2, 0), (MODAL, n2, 0) if n2 > 0 else (MODAL, 0, -n2)]
            e2 = _buat_jurnal(c, user, akhir.isoformat(), "penutup", f"Penutupan Ikhtisar Laba Rugi tahun {tahun} ke Modal Pemilik",
                              baris2, kunci=f"penutup:{tahun}:2") if abs(n2) >= 0.005 else None
            pv = n.get(PRIVE, 0.0)
            e3 = _buat_jurnal(c, user, akhir.isoformat(), "penutup", f"Penutupan Prive tahun {tahun} ke Modal Pemilik",
                              [(MODAL, pv, 0), (PRIVE, 0, pv)], kunci=f"penutup:{tahun}:3") if abs(pv) >= 0.005 else None
            catat(c, LOG_TRANSAKSI, "jurnal penutup tahun", "Berhasil", user=user, objek=str(tahun),
                  nilai_baru=", ".join(nomor_jurnal(x) for x in (e1, e2, e3) if x))
        return True, f"Jurnal penutup tahun {tahun} dibuat. Saldo akun sementara dan Prive menjadi nol, Modal Pemilik diperbarui."
    except Exception as ex:
        return False, str(ex)


def kandidat_pembalik(tahun: int) -> list:
    """Jurnal penyesuaian akrual (utang gaji) yang belum dibalik, untuk tahap 11 (opsional)."""
    _, akhir = rentang_tahun_buku(tahun)
    return semua("SELECT e.id, e.tanggal, e.keterangan, printf('JV-%04d', e.id) AS no_jurnal FROM journal_entries e "
                 "WHERE e.kunci LIKE 'utang_gaji:%' AND e.tanggal <= ? AND NOT EXISTS "
                 "(SELECT 1 FROM journal_entries x WHERE x.kunci = 'balik:' || e.id) ORDER BY e.id", (akhir.isoformat(),))


def jurnal_pembalik(user: dict, entry_id: int):
    if not owner(user):
        return tolak_akses(user, nomor_jurnal(entry_id))
    try:
        with get_conn() as c:
            e = c.execute("SELECT * FROM journal_entries WHERE id = ?", (entry_id,)).fetchone()
            if not e or e["jenis"] != "penyesuaian":
                return False, "Pilih jurnal penyesuaian."
            baru = (date.fromisoformat(e["tanggal"]) + timedelta(days=1)).isoformat()
            if not periode_terbuka(c, baru):
                return False, "Periode awal berikutnya sudah ditutup."
            lines = c.execute("SELECT kode_akun,debit,kredit FROM journal_lines WHERE entry_id = ?", (entry_id,)).fetchall()
            n = _buat_jurnal(c, user, baru, "pembalik", f"Jurnal pembalik {nomor_jurnal(entry_id)}: {e['keterangan']}",
                             [(x["kode_akun"], x["kredit"], x["debit"]) for x in lines], kunci=f"balik:{entry_id}")
            catat(c, LOG_TRANSAKSI, "jurnal pembalik", "Berhasil", user=user, objek=nomor_jurnal(entry_id), nilai_baru=nomor_jurnal(n))
        return True, f"Jurnal pembalik {nomor_jurnal(n)} dibuat tanggal {baru}."
    except Exception as ex:
        return False, str(ex)

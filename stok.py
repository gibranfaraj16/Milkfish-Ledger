"""
stok.py - Stok opname (metode fisik) dan estimasi stok di antara dua stok opname (Modul 6.3, 7, 9.2).
Stok resmi hanya dari stok opname final. Estimasi = stok awal + pembelian - pemakaian tercatat, bukan dasar jurnal.
"""

from datetime import date

from database import LOG_MASTER, TIDAK_BERHAK, catat, get_conn, hari_ini, owner, satu, semua, tolak_akses
from transaksi import periode_terbuka


def dasar_stok(item_id: int, sampai: date):
    """(jumlah, tanggal_dasar, sumber): stok opname final terakhir, atau persediaan awal bila belum ada."""
    f = satu("SELECT jumlah_fisik, tanggal FROM stock_counts WHERE item_id=? AND status='Final' AND tanggal <= ? "
             "ORDER BY tanggal DESC, id DESC LIMIT 1", (item_id, sampai.isoformat()))
    if f:
        return f["jumlah_fisik"], f["tanggal"], "stok opname final"
    o = satu("SELECT jumlah FROM opening_stock WHERE item_id = ?", (item_id,))
    return (o["jumlah"] if o else 0.0), None, "persediaan awal"


def estimasi(item_id: int, sampai: date | None = None) -> dict | None:
    """Estimasi stok saat ini. None bila item tidak ditemukan."""
    sampai = sampai or hari_ini()
    it = satu("SELECT * FROM items WHERE id = ?", (item_id,))
    if not it:
        return None
    dasar, d0, sumber = dasar_stok(item_id, sampai)
    awal = d0 or "0000-00-00"
    s = sampai.isoformat()
    masuk = satu("SELECT COALESCE(SUM(l.jumlah),0) AS n FROM transaction_lines l JOIN transactions t ON t.id=l.transaction_id "
                 "WHERE l.item_id=? AND t.status='Diposting' AND t.jenis LIKE 'pembelian%' AND t.tanggal > ? AND t.tanggal <= ?",
                 (item_id, awal, s))["n"]
    keluar = satu("SELECT COALESCE(SUM(jumlah),0) AS n FROM cultivation_logs WHERE item_id=? AND tanggal > ? AND tanggal <= ?",
                  (item_id, awal, s))["n"]
    catatan = ""
    if it["kategori"] == "Benih":
        keluar += satu("SELECT COALESCE(SUM(jumlah_benih),0) AS n FROM cultivation_cycles WHERE item_benih_id=? AND tgl_tebar > ? AND tgl_tebar <= ?",
                       (item_id, awal, s))["n"]
    if it["kategori"] == "Ikan hasil panen":
        keluar += satu("SELECT COALESCE(SUM(l.jumlah),0) AS n FROM transaction_lines l JOIN transactions t ON t.id=l.transaction_id "
                       "WHERE l.item_id=? AND t.status='Diposting' AND t.jenis LIKE 'penjualan%' AND t.tanggal > ? AND t.tanggal <= ?",
                       (item_id, awal, s))["n"]
        if satu("SELECT COUNT(*) AS n FROM items WHERE kategori='Ikan hasil panen' AND status='Aktif'")["n"] == 1:
            masuk += satu("SELECT COALESCE(SUM(jumlah),0) AS n FROM cultivation_logs WHERE jenis='Panen' AND tanggal > ? AND tanggal <= ?",
                          (awal, s))["n"]
        else:
            catatan = "Panen tidak ditambahkan otomatis karena ada lebih dari satu item ikan."
    return {"item": it, "dasar": dasar, "sumber": sumber, "masuk": masuk, "keluar": keluar, "estimasi": dasar + masuk - keluar,
            "catatan": catatan}


def daftar_opname(user: dict, mulai: str | None = None, akhir: str | None = None) -> list:
    """Karyawan tidak menerima nilai persediaan sama sekali."""
    kond, par = ["1=1"], []
    if mulai:
        kond.append("s.tanggal >= ?")
        par.append(mulai)
    if akhir:
        kond.append("s.tanggal <= ?")
        par.append(akhir)
    rows = semua("SELECT s.*, i.kode AS item_kode, i.nama AS item_nama, i.satuan, u.nama AS pembuat FROM stock_counts s "
                 "JOIN items i ON i.id = s.item_id LEFT JOIN users u ON u.id = s.dibuat_oleh "
                 f"WHERE {' AND '.join(kond)} ORDER BY s.tanggal DESC, i.kode", par)
    for r in rows:
        e = estimasi(r["item_id"], date.fromisoformat(r["tanggal"]))
        r["estimasi"] = e["estimasi"] if e else None
        r["selisih"] = r["jumlah_fisik"] - r["estimasi"] if e else None
        if not owner(user):
            r.pop("nilai", None)
    return rows


def simpan_hitungan(user: dict, tanggal: date, item_id: int, jumlah_fisik: float, nilai: float | None = None, id_: int | None = None):
    """Owner: hitungan dan nilai. Karyawan: hitungan fisik saja (nilai diabaikan)."""
    if tanggal > hari_ini():
        return False, "Tanggal tidak boleh di masa depan."
    if jumlah_fisik is None or jumlah_fisik < 0 or (nilai is not None and nilai < 0):
        return False, "Hitungan dan nilai tidak boleh negatif atau kosong."
    try:
        with get_conn() as c:
            if not periode_terbuka(c, tanggal.isoformat()):
                return False, "Periode sudah ditutup."
            ada = c.execute("SELECT * FROM stock_counts WHERE tanggal=? AND item_id=?", (tanggal.isoformat(), item_id)).fetchone()
            if id_ and not ada:
                ada = c.execute("SELECT * FROM stock_counts WHERE id = ?", (id_,)).fetchone()
            if ada:
                if ada["status"] == "Final":
                    return False, "Stok opname yang sudah final tidak bisa diubah."
                if not owner(user) and ada["dibuat_oleh"] != user["id"]:
                    c.rollback()
                    return tolak_akses(user, f"stock_counts#{ada['id']}")
                if owner(user):
                    c.execute("UPDATE stock_counts SET jumlah_fisik=?, nilai=? WHERE id=?", (jumlah_fisik, nilai, ada["id"]))
                else:
                    c.execute("UPDATE stock_counts SET jumlah_fisik=? WHERE id=?", (jumlah_fisik, ada["id"]))
                catat(c, LOG_MASTER, "ubah hitungan stok opname", "Berhasil", user=user, objek=f"stock_counts#{ada['id']}",
                      nilai_lama=f'{ada["jumlah_fisik"]}', nilai_baru=f"{jumlah_fisik}")
                return True, "Hitungan diperbarui."
            n = c.execute("INSERT INTO stock_counts (tanggal,item_id,jumlah_fisik,nilai,status,dibuat_oleh) VALUES (?,?,?,?, 'Draft', ?)",
                          (tanggal.isoformat(), item_id, jumlah_fisik, nilai if owner(user) else None, user["id"])).lastrowid
            catat(c, LOG_MASTER, "input hitungan stok opname", "Berhasil", user=user, objek=f"stock_counts#{n}", nilai_baru=f"{jumlah_fisik}")
            return True, "Hitungan fisik disimpan sebagai draft. Owner yang memfinalisasi."
    except Exception as e:
        return False, str(e)


def hapus_hitungan(user: dict, id_: int):
    r = satu("SELECT * FROM stock_counts WHERE id = ?", (id_,))
    if not r:
        return False, "Data tidak ditemukan."
    if r["status"] == "Final":
        return False, "Stok opname final tidak bisa dihapus."
    if not owner(user) and r["dibuat_oleh"] != user["id"]:
        return tolak_akses(user, f"stock_counts#{id_}")
    with get_conn() as c:
        c.execute("DELETE FROM stock_counts WHERE id = ?", (id_,))
        catat(c, LOG_MASTER, "hapus hitungan stok opname", "Berhasil", user=user, objek=f"stock_counts#{id_}",
              nilai_lama=f'{r["jumlah_fisik"]}')
    return True, "Hitungan dihapus."


def finalisasi(user: dict, ids: list):
    """Hanya Owner. Setiap hitungan harus punya nilai (tidak ada nilai karangan)."""
    if not owner(user):
        return tolak_akses(user, "Finalisasi stok opname")
    if not ids:
        return False, "Pilih hitungan yang akan difinalisasi."
    try:
        with get_conn() as c:
            n = 0
            for i in ids:
                r = c.execute("SELECT * FROM stock_counts WHERE id = ?", (i,)).fetchone()
                if not r or r["status"] == "Final":
                    continue
                if r["nilai"] is None:
                    return False, "Isi nilai persediaan dulu sebelum difinalisasi."
                if not periode_terbuka(c, r["tanggal"]):
                    return False, "Periode sudah ditutup."
                c.execute("UPDATE stock_counts SET status='Final' WHERE id = ?", (i,))
                catat(c, LOG_MASTER, "finalisasi stok opname", "Berhasil", user=user, objek=f"stock_counts#{i}",
                      nilai_lama="Draft", nilai_baru=f'Final, nilai Rp{r["nilai"]:,.0f}')
                n += 1
        return True, f"{n} hitungan difinalisasi."
    except Exception as e:
        return False, str(e)


def stok_di_bawah_minimum() -> list:
    """Item benih dan pakan yang estimasinya di bawah batas minimum."""
    out = []
    for it in semua("SELECT id, nama, satuan, stok_minimum FROM items WHERE status='Aktif' AND kategori IN ('Benih','Pakan') AND stok_minimum > 0"):
        e = estimasi(it["id"])
        if e and e["estimasi"] < it["stok_minimum"]:
            out.append({**it, "estimasi": e["estimasi"]})
    return out

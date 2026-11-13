"""dashboard.py - data Dashboard (bab 5) dan Audit Trail (bab 10). Dashboard hanya membaca, tidak menyimpan angka sendiri."""

from datetime import date, timedelta

import pandas as pd

import akuntansi as ak
import stok
from database import ambil_set, hari_ini, owner, semua, satu

FILTER = ["Hari ini", "7 hari", "Bulan ini", "Bulan lalu", "Tahun ini", "Rentang khusus"]


def rentang(pilihan: str, khusus=None):
    h = hari_ini()
    if pilihan == "Hari ini":
        return h, h
    if pilihan == "7 hari":
        return h - timedelta(days=6), h
    if pilihan == "Bulan ini":
        return h.replace(day=1), h
    if pilihan == "Bulan lalu":
        akhir = h.replace(day=1) - timedelta(days=1)
        return akhir.replace(day=1), akhir
    if pilihan == "Tahun ini":
        return date(h.year, 1, 1), h
    if khusus and len(khusus) == 2:
        return khusus[0], khusus[1]
    return h.replace(day=1), h


def seri_transaksi(mulai: date, akhir: date, skala: str) -> pd.DataFrame:
    """Jumlah transaksi aktif (diposting) per hari, minggu, atau bulan. Draft dan yang dibatalkan tidak dihitung."""
    rows = semua("SELECT tanggal, total FROM transactions WHERE status='Diposting' AND tanggal BETWEEN ? AND ?",
                 (mulai.isoformat(), akhir.isoformat()))
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["tanggal"] = pd.to_datetime(df["tanggal"])
    rule = {"Hari": "D", "Minggu": "W-MON", "Bulan": "MS"}[skala]
    g = df.set_index("tanggal").resample(rule).agg(Jumlah=("total", "count"), Nilai=("total", "sum"))
    g.index = g.index.strftime("%d %b %Y" if skala != "Bulan" else "%b %Y")
    return g


def peringatan_owner() -> list:
    """Daftar peringatan (teks). Kosong berarti tidak ada."""
    out = []
    pi, ut = ak.rincian_pihak("piutang"), ak.rincian_pihak("utang")
    for p in ut:
        if p["terlambat"] > 0:
            out.append(f'Utang jatuh tempo: {p["nama"]} (Rp {p["terlambat"]:,.0f})'.replace(",", "."))
    for p in pi:
        if p["terlambat"] > 0:
            out.append(f'Piutang terlambat: {p["nama"]} (Rp {p["terlambat"]:,.0f})'.replace(",", "."))
    batas = ambil_set("batas_kas")
    if batas:
        kas = ak.ringkasan(hari_ini())["kas_bank"]
        if kas < float(batas):
            out.append(f'Kas dan bank (Rp {kas:,.0f}) di bawah batas Rp {float(batas):,.0f}'.replace(",", "."))
    for it in stok.stok_di_bawah_minimum():
        out.append(f'Stok {it["nama"]} (estimasi {it["estimasi"]:,.0f} {it["satuan"]}) di bawah batas {it["stok_minimum"]:,.0f}'.replace(",", "."))
    n = satu("SELECT COUNT(*) AS n FROM transactions WHERE status='Draft'")["n"]
    if n:
        out.append(f"{n} draft transaksi belum diposting")
    bulan = hari_ini().strftime("%Y-%m")
    mulai, akhir = ak.rentang_bulan(bulan)
    if satu("SELECT 1 AS x FROM items WHERE status='Aktif' AND akun_persediaan IN ('1104','1105','1106','1107')") and not satu(
            "SELECT 1 AS x FROM stock_counts WHERE status='Final' AND tanggal BETWEEN ? AND ?", (mulai.isoformat(), akhir.isoformat())):
        out.append(f"Stok opname bulan {bulan} belum dilakukan")
    lalu = [p["bulan"] for p in semua("SELECT bulan FROM periods WHERE status='Terbuka' AND bulan < ? ORDER BY bulan", (bulan,))]
    if lalu:
        out.append("Periode belum ditutup: " + ", ".join(lalu))
    return out


def ringkasan_owner(mulai: date, akhir: date) -> dict:
    s = ak.ringkasan(akhir)
    lr = ak.laba_rugi(mulai, akhir)
    return {
        "karyawan": satu("SELECT COUNT(*) AS n FROM employees WHERE status='Aktif'")["n"],
        "supplier": satu("SELECT COUNT(*) AS n FROM suppliers WHERE status='Aktif'")["n"],
        "aset": s["aset"], "liabilitas": s["liabilitas"], "kas_bank": s["kas_bank"],
        "penjualan": lr["penjualan_bersih"], "pembelian": lr["pembelian_bersih"],
        "piutang": sum(p["saldo"] for p in ak.rincian_pihak("piutang")),
        "utang": sum(p["saldo"] for p in ak.rincian_pihak("utang")),
        "laba": lr["laba"], "donat": {"Kas dan bank": s["kas_bank"], "Persediaan": s["persediaan"],
                                      "Aset tetap (neto)": s["aset_tetap"], "Lainnya": s["lainnya"]},
        "sudah_disesuaikan": bool(satu("SELECT 1 AS x FROM journal_entries WHERE jenis='penyesuaian' AND tanggal BETWEEN ? AND ?",
                                       (mulai.isoformat(), akhir.isoformat()))),
    }


def ringkasan_karyawan(user: dict) -> dict:
    h = hari_ini().isoformat()
    return {
        "hari_ini": semua("SELECT no, jenis, total, status FROM transactions WHERE dibuat_oleh=? AND tanggal=? ORDER BY id DESC", (user["id"], h)),
        "draft": semua("SELECT no, tanggal, jenis, total FROM transactions WHERE dibuat_oleh=? AND status='Draft' ORDER BY id DESC", (user["id"],)),
        "pengiriman": semua("SELECT d.no_surat_jalan, d.tanggal, c.nama AS customer, d.status FROM deliveries d LEFT JOIN customers c ON c.id=d.customer_id "
                            "WHERE d.status != 'Diterima' ORDER BY d.tanggal LIMIT 8"),
        "stok": [{"item": it["nama"], "satuan": it["satuan"], "estimasi": (stok.estimasi(it["id"]) or {}).get("estimasi"),
                  "minimum": it["stok_minimum"]}
                 for it in semua("SELECT id, nama, satuan, stok_minimum FROM items WHERE status='Aktif' AND kategori IN ('Benih','Pakan') ORDER BY kode")],
    }


def transaksi_terbaru(user: dict, n: int = 10) -> list:
    kond, par = "", []
    if not owner(user):
        kond, par = "WHERE t.dibuat_oleh = ?", [user["id"]]
    return semua("SELECT t.id, t.tanggal, t.no, t.jenis, t.total, t.status, u.nama AS pembuat FROM transactions t "
                 f"LEFT JOIN users u ON u.id = t.dibuat_oleh {kond} ORDER BY t.tanggal DESC, t.id DESC LIMIT {int(n)}", par)


# ------------------------------------------------------------------ audit trail (hanya baca, hanya Owner)
def log_audit(user: dict, mulai: date, akhir: date, jenis: str | None = None, email: str | None = None, hasil: str | None = None) -> list:
    if not owner(user):
        return []
    kond, par = ["substr(waktu,1,10) BETWEEN ? AND ?"], [mulai.isoformat(), akhir.isoformat()]
    if jenis:
        kond.append("jenis_log = ?")
        par.append(jenis)
    if email:
        kond.append("(email LIKE ? OR nama_input LIKE ?)")
        par += [f"%{email}%"] * 2
    if hasil:
        kond.append("hasil = ?")
        par.append(hasil)
    return semua(f"SELECT waktu, jenis_log, email, nama_input, role, aksi, objek, nilai_lama, nilai_baru, hasil, keterangan "
                 f"FROM audit_log WHERE {' AND '.join(kond)} ORDER BY id DESC LIMIT 2000", par)

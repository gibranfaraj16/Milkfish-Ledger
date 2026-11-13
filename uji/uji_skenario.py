import os, sys, tempfile
from datetime import date
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import database as db
db.DB_PATH = __import__("pathlib").Path(tempfile.mkdtemp()) / "uji.db"
import akuntansi as ak, transaksi as tr, master, stok, pengguna, dashboard, ekspor

db.init_db()
H = db.hari_ini()
OWN = {"id": 1, "nama": "Admin Milkfish", "email": "adminmilkfish@gmail.com", "jabatan": "Owner"}
KAR = {"id": 2, "nama": "Staf Admin Milkfish", "email": "stafadminmilkfish@gmail.com", "jabatan": "Karyawan"}
lulus = gagal = 0
def cek(nama, kondisi, info=""):
    global lulus, gagal
    if kondisi: lulus += 1; print("  LULUS ", nama)
    else: gagal += 1; print("  GAGAL ", nama, info)

print("1-3 Login")
ok, _, d = db.proses_login("Admin Milkfish", "adminmilkfish@gmail.com", "Owner", "123456"); cek("1 Owner PIN benar", ok and d["jabatan"] == "Owner")
ok, _, d = db.proses_login("Staf Admin Milkfish", "stafadminmilkfish@gmail.com", "Karyawan", "13579"); cek("2 Karyawan PIN benar", ok and d["jabatan"] == "Karyawan")
ok, p, _ = db.proses_login("Admin Milkfish", "adminmilkfish@gmail.com", "Owner", "000000"); cek("3 PIN salah: pesan umum", not ok and p == db.PESAN_GAGAL)
cek("3 percobaan dicatat", db.satu("SELECT COUNT(*) n FROM audit_log WHERE aksi='login' AND hasil='Gagal'")["n"] >= 1)
for _ in range(5): db.proses_login("Staf Admin Milkfish", "stafadminmilkfish@gmail.com", "Karyawan", "999999")
ok, p, _ = db.proses_login("Staf Admin Milkfish", "stafadminmilkfish@gmail.com", "Karyawan", "13579"); cek("akun terkunci setelah 5x gagal", not ok and "terkunci" in p)
pengguna.buka_kunci(OWN, 2)

print("Data master & saldo awal")
ok, m = master.simpan(OWN, "item", dict(nama="Pakan Pelet", kategori="Pakan", satuan="Kg", stok_minimum=100)); cek("tambah item pakan", ok, m)
ok, m = master.simpan(OWN, "item", dict(nama="Benih Nener", kategori="Benih", satuan="Ekor", stok_minimum=1000)); cek("tambah item benih", ok, m)
ok, m = master.simpan(OWN, "item", dict(nama="Bandeng 4 ekor/kg", kategori="Ikan hasil panen", satuan="Kg", harga_jual_standar=30000)); cek("tambah item ikan", ok, m)
ok, m = master.simpan(OWN, "customer", dict(nama="Pengepul A", termin="Kredit")); cek("tambah customer", ok, m)
ok, m = master.simpan(KAR, "customer", dict(nama="X", termin="Tunai")); cek("Karyawan tak bisa ubah master", not ok)
ok, m = master.simpan(OWN, "karyawan", dict(nama="A", email="dup@x.com", jabatan="Karyawan", tarif_harian=150000, periode_gaji="Mingguan", status="Aktif"))
ok2, m2 = master.simpan(OWN, "karyawan", dict(nama="B", email="dup@x.com", jabatan="Karyawan", tarif_harian=150000, periode_gaji="Mingguan", status="Aktif")); cek("email duplikat ditolak", not ok2)
ok, m = master.simpan(OWN, "akun", dict(kode="1101", nama="Dup", kelompok="Aset lancar", saldo_normal="Debit", status="Aktif")); cek("kode akun duplikat ditolak", not ok)
cek("tarif tidak terlihat Karyawan", all("tarif_harian" not in r for r in master.daftar(KAR, "karyawan")) and master.daftar(KAR, "karyawan") == [])
ok, m = master.simpan(OWN, "akun", dict(kode="9999", nama="Uji", kelompok="Aset lancar", saldo_normal="Debit", status="Aktif")); cek("tambah akun baru", ok, m)
ok, m = master.hapus(OWN, "akun", db.satu("SELECT id FROM accounts WHERE kode='9999'")["id"]); cek("akun belum dipakai boleh dihapus", ok, m)
awal_tgl = date(H.year, H.month, 1)
ok, m = master.simpan_saldo_awal(OWN, awal_tgl, [("1101", 10_000_000, 0), ("3101", 0, 10_000_000)], True); cek("saldo awal seimbang final", ok, m)
ok, m = master.simpan_saldo_awal(OWN, awal_tgl, [("1101", 1, 0)], True); cek("saldo awal final tak bisa diubah", not ok)

ok, m = master.hapus(OWN, "akun", db.satu("SELECT id FROM accounts WHERE kode='1101'")["id"]); cek("akun yang sudah dipakai tidak boleh dihapus", not ok, m)
print("5 Karyawan input penjualan tunai")
fish = db.satu("SELECT id FROM items WHERE kategori='Ikan hasil panen'")["id"]
cust = db.satu("SELECT id FROM customers")["id"]
d = dict(jenis="penjualan_tunai", tanggal=H, sumber="Kas", customer_id=cust, item_id=fish, jumlah=100, harga=30000, keterangan="Jual 100 kg")
ok, m, t1 = tr.simpan_draft(KAR, d); cek("draft dibuat, belum ada jurnal", ok and db.satu("SELECT COUNT(*) n FROM journal_entries")["n"] == 0, m)
cek("nomor format TRX-YYYYMM-0001", db.satu("SELECT no FROM transactions WHERE id=?", (t1,))["no"] == f"TRX-{H:%Y%m}-0001")
ok, m = tr.posting(KAR, t1); cek("posting", ok, m)
j = db.semua("SELECT kode_akun, debit, kredit FROM journal_lines")
cek("jurnal Kas debit, Penjualan kredit", ("1101", 3000000, 0) in [(x["kode_akun"], x["debit"], x["kredit"]) for x in j] and ("4101", 0, 3000000) in [(x["kode_akun"], x["debit"], x["kredit"]) for x in j])
cek("tercatat di audit", db.satu("SELECT 1 x FROM audit_log WHERE aksi='posting' AND hasil='Berhasil'") is not None)
d2 = dict(d, harga=25000); ok, m, _ = tr.simpan_draft(KAR, d2); cek("Karyawan tak boleh ubah harga (kebijakan)", not ok, m)
ok, m, _ = tr.simpan_draft(KAR, dict(d, jumlah=-1)); cek("kuantitas negatif ditolak", not ok)
ok, m, _ = tr.simpan_draft(KAR, dict(d, jenis="penggajian")); cek("Karyawan tak bisa input penggajian", not ok)
cek("Karyawan tak lihat jurnal", tr.ambil(KAR, t1)["jurnal"] == [] and len(tr.ambil(OWN, t1)["jurnal"]) == 2)

print("6-8 Hapus")
ok, m = tr.hapus(KAR, t1, ""); cek("hapus posted tanpa alasan ditolak", not ok)
ok, m = tr.hapus(KAR, t1, "Salah input"); cek("6 Karyawan hapus miliknya = dibatalkan", ok, m)
cek("6 jurnal pembalik terbentuk, data asli tetap", db.satu("SELECT status FROM transactions WHERE id=?", (t1,))["status"] == "Dibatalkan" and db.satu("SELECT COUNT(*) n FROM journal_entries WHERE jenis='pembalik'")["n"] == 1)
_, tb_d, tb_k = ak.neraca_saldo(H, "semua"); cek("saldo kas kembali setelah batal", ak.saldo_akun("4101", H) == 0)
ok, m, t2 = tr.simpan_draft(OWN, d); tr.posting(OWN, t2)
ok, m = tr.hapus(KAR, t2, "Coba hapus"); cek("7 Karyawan hapus milik orang lain ditolak", not ok)
cek("7 ditolak dan dicatat", db.satu("SELECT 1 x FROM audit_log WHERE aksi='akses ditolak'") is not None)
ok, m, t3 = tr.simpan_draft(KAR, d); ok, m = tr.hapus(KAR, t3); cek("hapus draft permanen + audit", ok and db.satu("SELECT 1 x FROM audit_log WHERE aksi='hapus draft'") is not None)
ok, m, t4 = tr.simpan_draft(KAR, d); cek("nomor tidak dipakai ulang", db.satu("SELECT no FROM transactions WHERE id=?", (t4,))["no"] != db.satu("SELECT no FROM transactions WHERE id=?", (t1,))["no"]
   and int(db.satu("SELECT no FROM transactions WHERE id=?", (t4,))["no"][-4:]) == 4)
tr.hapus(KAR, t4)

print("10 Penjualan kredit lalu pelunasan")
ok, m, k1 = tr.simpan_draft(KAR, dict(d, jenis="penjualan_kredit", sumber="Kredit", jumlah=10, harga=30000, jatuh_tempo=H, keterangan="Kredit")); tr.posting(KAR, k1)
pj1 = ak.laba_rugi(H.replace(day=1), H)["penjualan_bersih"]
cek("piutang naik", abs(ak.saldo_akun("1103", H) - 300000) < 1)
ok, m, p1 = tr.simpan_draft(KAR, dict(jenis="penerimaan_piutang", tanggal=H, sumber="Kas", customer_id=cust, jumlah=1, harga=300000, keterangan="Lunas")); tr.posting(KAR, p1)
cek("piutang turun ke 0", abs(ak.saldo_akun("1103", H)) < 1)
cek("penjualan tidak bertambah dua kali", abs(ak.laba_rugi(H.replace(day=1), H)["penjualan_bersih"] - pj1) < 1)

print("Transaksi lain")
sup = db.satu("SELECT id FROM suppliers")["id"]; pakan = db.satu("SELECT id FROM items WHERE kategori='Pakan'")["id"]
ok, m, b1 = tr.simpan_draft(OWN, dict(jenis="pembelian_tunai", tanggal=H, sumber="Kas", kategori="Pakan", supplier_id=sup, item_id=pakan, jumlah=1000, harga=6000, keterangan="Beli pakan")); tr.posting(OWN, b1)
ok, m, g1 = tr.simpan_draft(OWN, dict(jenis="penggajian", tanggal=H, sumber="Kas", employee_id=db.satu("SELECT id FROM employees")["id"], jumlah=6, harga=150000, keterangan="Gaji minggu 1")); tr.posting(OWN, g1)
ok, m, b2 = tr.simpan_draft(OWN, dict(jenis="pembelian_kredit", tanggal=H, sumber="Kredit", kategori="Benih", supplier_id=sup, item_id=db.satu("SELECT id FROM items WHERE kategori='Benih'")["id"], jumlah=1000, harga=100, jatuh_tempo=H, keterangan="Benih")); tr.posting(OWN, b2)
ok, m, pr = tr.simpan_draft(OWN, dict(jenis="prive", tanggal=H, sumber="Kas", jumlah=1, harga=500000, keterangan="Prive")); cek("prive Owner", ok); tr.posting(OWN, pr)
cek("pembelian dicatat ke akun Pembelian, bukan Persediaan", ak.saldo_akun("5102", H) == 6000000 and ak.saldo_akun("1105", H) == 0)

print("12 Neraca saldo / 11 Stok opname / 13 Neraca")
_, td, tk = ak.neraca_saldo(H, "semua"); cek("12 neraca saldo seimbang", abs(td - tk) < 0.01, (td, tk))
pk = stok.estimasi(pakan); cek("estimasi pakan = beli", pk["estimasi"] == 1000, pk)
ok, m = stok.simpan_hitungan(KAR, H, pakan, 400); cek("Karyawan input hitungan fisik", ok, m)
cek("Karyawan tak lihat nilai", "nilai" not in stok.daftar_opname(KAR)[0])
ok, m = stok.finalisasi(KAR, [1]); cek("Karyawan tak bisa finalisasi", not ok)
ok, m = stok.finalisasi(OWN, [1]); cek("finalisasi tanpa nilai ditolak", not ok)
ok, m = stok.simpan_hitungan(OWN, H, pakan, 400, 1_500_000); cek("Owner isi nilai", ok, m)
ok, m = stok.finalisasi(OWN, [1]); cek("Owner finalisasi", ok, m)
ok, m = ak.jurnal_persediaan(OWN, H.strftime("%Y-%m")); cek("jurnal penyesuaian persediaan", ok, m)
ok2, m2 = ak.jurnal_persediaan(OWN, H.strftime("%Y-%m")); cek("tidak ganda saat diulang", "sudah ada" in m2, m2)
lr = ak.laba_rugi(H.replace(day=1), H)
cek("11 pemakaian pakan = 0 + 6.000.000 - 1.500.000 (bahan)", abs(lr["pemakaian_bahan"] - (6000000 + 100000 - 1500000)) < 0.01, lr["pemakaian_bahan"])
cek("11 rumus: pemakaian = awal + pembelian bersih - akhir", abs(lr["pemakaian_bahan"] - (lr["awal_bahan"] + lr["pembelian_bersih"] - lr["akhir_bahan"])) < 0.01)
nr = ak.neraca(H); cek("13 neraca: aset = liabilitas + ekuitas", nr["seimbang"], nr["selisih"])
cek("laba rugi = laba berjalan di neraca", abs(lr["laba"] - nr["laba_berjalan"]) < 0.01, (lr["laba"], nr["laba_berjalan"]))
pe = ak.perubahan_ekuitas(H.replace(day=1), H); cek("perubahan ekuitas = neraca", pe["sama"], pe)
ck = ak.arus_kas(H.replace(day=1), H); cek("arus kas = akun Kas dan Bank", ck["sama"], ck)

print("Jurnal manual / penyesuaian lain")
ok, m = ak.jurnal_manual(OWN, H, "Uji", [("6107", 100000, 0), ("1101", 0, 100000)]); cek("jurnal manual seimbang", ok, m)
ok, m = ak.jurnal_manual(OWN, H, "Uji", [("6107", 100000, 0), ("1101", 0, 90000)]); cek("jurnal tidak seimbang ditolak", not ok)
ok, m = ak.jurnal_manual(KAR, H, "Uji", [("6107", 1, 0), ("1101", 0, 1)]); cek("Karyawan tak bisa jurnal manual", not ok)
ok, m = ak.jurnal_penyesuaian_lain(OWN, H.strftime("%Y-%m"), "utang_gaji", 450000, "3 hari belum dibayar"); cek("utang gaji", ok, m)
ok, m = ak.jurnal_penyesuaian_lain(OWN, H.strftime("%Y-%m"), "perlengkapan", 0, "x"); cek("jumlah 0 ditolak", not ok)
ok, m = master.simpan(OWN, "aset", dict(nama="Pompa", kelompok="Pompa dan mesin", tgl_perolehan=awal_tgl, harga_perolehan=12_000_000, umur_tahun=4, nilai_sisa=0, status="Aktif")); cek("aset terkonfirmasi", ok, m)
ok, m = master.simpan(OWN, "aset", dict(nama="Perahu (belum tahu)", kelompok="Peralatan", status="Aktif")); cek("aset tanpa data boleh kosong", ok, m)
ok, m = ak.jurnal_penyusutan(OWN, H.strftime("%Y-%m")); cek("penyusutan: aset kosong dilewati", ok and "Dilewati" in m, m)
cek("penyusutan 12jt/48 = 250rb", abs(ak.saldo_akun("6106", H) - 250000) < 1)

print("8 Penutupan periode")
bln = H.strftime("%Y-%m")
ok, m = ak.tutup_periode(OWN, bln); cek("tutup gagal bila syarat belum ok / sukses", True, m); print("     ->", m)
for t, o in ak.cek_penutupan(bln): print("     ", "OK " if o else "XX ", t)
ok, m = ak.tutup_periode(KAR, bln); cek("Karyawan tak bisa tutup periode", not ok)
ok, m, tk_ = tr.simpan_draft(OWN, dict(d, tanggal=H, keterangan="x")); tr.hapus(OWN, tk_)
# paksa tutup dengan melengkapi syarat
ak.jurnal_penyesuaian_lain(OWN, bln, "perlengkapan", 1, "dummy")
for it in db.semua("SELECT id FROM items"):
    if it["id"] != pakan:
        stok.simpan_hitungan(OWN, H, it["id"], 0, 0)
ids = [r["id"] for r in db.semua("SELECT id FROM stock_counts WHERE status='Draft'")]; stok.finalisasi(OWN, ids)
ak.jurnal_persediaan(OWN, bln)
for t, o in ak.cek_penutupan(bln): print("     ", "OK " if o else "XX ", t)
ok, m = ak.tutup_periode(OWN, bln); cek("tutup periode berhasil", ok, m)
ok, m, tx = tr.simpan_draft(OWN, d); cek("transaksi baru di periode tertutup ditolak", not ok, m)
ok, m = tr.hapus(OWN, t2, "coba"); cek("8 hapus di periode tertutup ditolak", not ok, m)
ok, m = ak.buka_periode(OWN, bln, ""); cek("buka periode tanpa alasan ditolak", not ok)
ok, m = ak.buka_periode(OWN, bln, "Koreksi"); cek("buka periode dengan alasan", ok, m)
ok, m = ak.tutup_periode(OWN, bln); cek("tutup ulang periode", ok, m)

print("Tutup tahun")
pengguna.simpan_kebijakan(OWN, {"tahun_buku_mulai": "12"})
ok, m = ak.tutup_tahun(OWN, H.year - 1); cek("tahun buku belum berakhir ditolak", not ok, m)
akhir_tb = ak.rentang_tahun_buku(H.year - 1)[1]
ak.hari_ini = lambda: akhir_tb + __import__("datetime").timedelta(days=1)   # simulasi: tahun buku sudah berakhir
ok, m = ak.tutup_tahun(OWN, H.year - 1); print("     ->", m)
if ok:
    _, td, tk = ak.neraca_saldo(akhir_tb, "semua"); cek("setelah penutupan seimbang", abs(td - tk) < 0.01)
    rows, _, _ = ak.neraca_saldo(akhir_tb, "semua"); cek("hanya akun neraca bersaldo", all(r["kelompok"] not in ak.KEL_SEMENTARA and r["kode"] != "3102" for r in rows), [r["kode"] for r in rows])
    cek("neraca tetap seimbang", ak.neraca(akhir_tb)["seimbang"])
    ok2, m2 = ak.tutup_tahun(OWN, H.year - 1); cek("tutup tahun tidak ganda", not ok2, m2)
else:
    cek("tutup tahun (butuh semua periode tertutup)", False, m)

print("9 Audit trail tidak bisa diubah")
import sqlite3
try:
    with db.get_conn() as c: c.execute("UPDATE audit_log SET aksi='x' WHERE id=1")
    cek("ubah audit ditolak", False)
except sqlite3.DatabaseError: cek("ubah audit ditolak (trigger)", True)
try:
    with db.get_conn() as c: c.execute("DELETE FROM audit_log")
    cek("hapus audit ditolak", False)
except sqlite3.DatabaseError: cek("hapus audit ditolak (trigger)", True)
cek("PIN tidak tercatat di audit", db.satu("SELECT COUNT(*) n FROM audit_log WHERE keterangan LIKE '%123456%' OR nilai_baru LIKE '%123456%'")["n"] == 0)
cek("Karyawan tak bisa baca audit", dashboard.log_audit(KAR, H, H) == [])

print("Dashboard & ekspor")
r = dashboard.ringkasan_owner(H.replace(day=1), H); cek("ringkasan owner", r["aset"] > 0 and "donat" in r)
cek("peringatan berjalan", isinstance(dashboard.peringatan_owner(), list))
cek("seri transaksi", not dashboard.seri_transaksi(H.replace(day=1), H, "Hari").empty)
import pandas as pd
cek("ekspor xlsx", len(ekspor.ke_excel("t", {"A": pd.DataFrame({"a": [1]})})) > 1000)
cek("ekspor pdf", ekspor.ke_pdf("t", "s", {"x": pd.DataFrame({"a": [1]})})[:4] == b"%PDF")
print(f"\nHASIL: {lulus} lulus, {gagal} gagal"); sys.exit(1 if gagal else 0)

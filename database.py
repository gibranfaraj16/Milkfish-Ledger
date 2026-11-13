"""
database.py - Milkfish Ledger
Database SQLite (milkfish.db), hash PIN, login, audit trail, dan fungsi dasar yang dipakai semua modul.
Semua kode di proyek ini ditulis dalam Python. Perintah SQL hanya dipakai sebagai teks untuk bicara dengan SQLite.
"""

import hashlib
import hmac
import os
import re
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "milkfish.db"
JABATAN = ["Owner", "Karyawan"]
MAX_GAGAL = 5            # kunci akun setelah 5 kali salah berturut-turut (Modul 4.1)
KUNCI_MENIT = 5
HASH_ITERASI = 200_000
ZONA = timezone(timedelta(hours=7))  # Asia/Jakarta
TIDAK_BERHAK = "Anda tidak memiliki akses."

USERS_AWAL = [
    ("Admin Milkfish", "adminmilkfish@gmail.com", "Owner", "123456"),
    ("Staf Admin Milkfish", "stafadminmilkfish@gmail.com", "Karyawan", "13579"),
]

# Daftar akun usulan (Modul 6.1): kode, nama, kelompok, saldo normal
AKUN_AWAL = [
    ("1101", "Kas", "Aset lancar", "Debit"), ("1102", "Bank", "Aset lancar", "Debit"),
    ("1103", "Piutang Usaha", "Aset lancar", "Debit"),
    ("1104", "Persediaan Benih Bandeng", "Aset lancar", "Debit"),
    ("1105", "Persediaan Pakan", "Aset lancar", "Debit"),
    ("1106", "Persediaan Pupuk, Kapur, dan Obat", "Aset lancar", "Debit"),
    ("1107", "Persediaan Ikan Bandeng Hasil Panen", "Aset lancar", "Debit"),
    ("1108", "Perlengkapan", "Aset lancar", "Debit"), ("1109", "Biaya Dibayar di Muka", "Aset lancar", "Debit"),
    ("1201", "Tanah dan Tambak", "Aset tetap", "Debit"), ("1202", "Bangunan dan Gubuk Jaga", "Aset tetap", "Debit"),
    ("1203", "Akumulasi Penyusutan Bangunan", "Kontra aset", "Kredit"),
    ("1204", "Pompa, Mesin, dan Kincir", "Aset tetap", "Debit"),
    ("1205", "Akumulasi Penyusutan Pompa dan Mesin", "Kontra aset", "Kredit"),
    ("1206", "Peralatan Budidaya", "Aset tetap", "Debit"),
    ("1207", "Akumulasi Penyusutan Peralatan", "Kontra aset", "Kredit"),
    ("1208", "Kendaraan", "Aset tetap", "Debit"), ("1209", "Akumulasi Penyusutan Kendaraan", "Kontra aset", "Kredit"),
    ("2101", "Utang Usaha", "Liabilitas jangka pendek", "Kredit"),
    ("2102", "Utang Gaji", "Liabilitas jangka pendek", "Kredit"),
    ("2103", "Utang Lain-lain", "Liabilitas jangka pendek", "Kredit"),
    ("2201", "Utang Bank", "Liabilitas jangka panjang", "Kredit"),
    ("3101", "Modal Pemilik", "Ekuitas", "Kredit"), ("3102", "Prive", "Pengurang ekuitas", "Debit"),
    ("3103", "Ikhtisar Laba Rugi", "Akun sementara", "Kredit"),
    ("4101", "Penjualan Ikan Bandeng", "Pendapatan", "Kredit"),
    ("4102", "Retur Penjualan", "Kontra pendapatan", "Debit"),
    ("4103", "Potongan Penjualan", "Kontra pendapatan", "Debit"),
    ("4201", "Pendapatan Lain-lain", "Pendapatan lain", "Kredit"),
    ("5101", "Pembelian Benih", "Pembelian (metode fisik)", "Debit"),
    ("5102", "Pembelian Pakan", "Pembelian (metode fisik)", "Debit"),
    ("5103", "Pembelian Pupuk, Kapur, dan Obat", "Pembelian (metode fisik)", "Debit"),
    ("5104", "Ongkos Angkut Pembelian", "Pembelian (metode fisik)", "Debit"),
    ("5105", "Retur Pembelian", "Kontra pembelian", "Kredit"),
    ("5106", "Potongan Pembelian", "Kontra pembelian", "Kredit"),
    ("6101", "Beban Gaji dan Upah", "Beban operasional", "Debit"),
    ("6102", "Beban Listrik dan BBM", "Beban operasional", "Debit"),
    ("6103", "Beban Perawatan Tambak dan Mesin", "Beban operasional", "Debit"),
    ("6104", "Beban Pengiriman", "Beban operasional", "Debit"),
    ("6105", "Beban Perlengkapan", "Beban operasional", "Debit"),
    ("6106", "Beban Penyusutan", "Beban operasional", "Debit"),
    ("6107", "Beban Administrasi", "Beban operasional", "Debit"),
    ("6108", "Beban Lain-lain", "Beban operasional", "Debit"),
]

KELOMPOK_AKUN = [
    "Aset lancar", "Aset tetap", "Kontra aset", "Liabilitas jangka pendek", "Liabilitas jangka panjang",
    "Ekuitas", "Pengurang ekuitas", "Akun sementara", "Pendapatan", "Kontra pendapatan", "Pendapatan lain",
    "Pembelian (metode fisik)", "Kontra pembelian", "Beban operasional",
]

# Pengaturan awal (menu Pengaturan > Kebijakan)
KEBIJAKAN_AWAL = {
    "batas_kas": "", "karyawan_ubah_harga": "Tidak", "karyawan_hapus": "Milik sendiri",
    "tahun_buku_mulai": "1", "termin_kredit": "Ya", "tarif_harian": "150000",
}


# ------------------------------------------------------------------ waktu & koneksi
def sekarang() -> datetime:
    return datetime.now(ZONA).replace(tzinfo=None)


def hari_ini() -> date:
    return sekarang().date()


def waktu_teks() -> str:
    return sekarang().strftime("%Y-%m-%d %H:%M:%S")


def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def semua(sql: str, par=()) -> list:
    with get_conn() as c:
        return [dict(r) for r in c.execute(sql, par)]


def satu(sql: str, par=()):
    with get_conn() as c:
        r = c.execute(sql, par).fetchone()
    return dict(r) if r else None


# ------------------------------------------------------------------ hash PIN
def hash_pin(pin: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, HASH_ITERASI)
    return f"pbkdf2_sha256${HASH_ITERASI}${salt.hex()}${dk.hex()}"


def cek_pin(pin: str, tersimpan: str) -> bool:
    try:
        _, it, salt, h = tersimpan.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(salt), int(it))
        return hmac.compare_digest(dk.hex(), h)
    except (ValueError, AttributeError):
        return False


# ------------------------------------------------------------------ skema (Modul bab 11)
SKEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT, nama TEXT NOT NULL, email TEXT NOT NULL UNIQUE,
    role TEXT NOT NULL CHECK (role IN ('Owner','Karyawan')), pin_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'Aktif' CHECK (status IN ('Aktif','Nonaktif')),
    jumlah_gagal INTEGER NOT NULL DEFAULT 0, dikunci_sampai TEXT);
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT, kode TEXT NOT NULL UNIQUE, nama TEXT NOT NULL, kelompok TEXT NOT NULL,
    saldo_normal TEXT NOT NULL CHECK (saldo_normal IN ('Debit','Kredit')),
    status TEXT NOT NULL DEFAULT 'Aktif' CHECK (status IN ('Aktif','Nonaktif')), keterangan TEXT);
CREATE TABLE IF NOT EXISTS employees (
    id INTEGER PRIMARY KEY AUTOINCREMENT, kode TEXT NOT NULL UNIQUE, nama TEXT NOT NULL, email TEXT UNIQUE,
    kontak TEXT, jabatan TEXT NOT NULL DEFAULT 'Karyawan' CHECK (jabatan IN ('Owner','Karyawan')),
    tarif_harian REAL NOT NULL DEFAULT 150000 CHECK (tarif_harian >= 0),
    periode_gaji TEXT NOT NULL DEFAULT 'Mingguan', tanggal_masuk TEXT,
    status TEXT NOT NULL DEFAULT 'Aktif' CHECK (status IN ('Aktif','Nonaktif')),
    user_id INTEGER REFERENCES users(id));
CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT, kode TEXT NOT NULL UNIQUE, nama TEXT NOT NULL, kategori TEXT,
    kontak TEXT, alamat TEXT, harga_khusus REAL CHECK (harga_khusus IS NULL OR harga_khusus >= 0),
    termin TEXT NOT NULL DEFAULT 'Tunai' CHECK (termin IN ('Tunai','Kredit')), pengiriman TEXT,
    saldo_awal_piutang REAL NOT NULL DEFAULT 0 CHECK (saldo_awal_piutang >= 0),
    status TEXT NOT NULL DEFAULT 'Aktif' CHECK (status IN ('Aktif','Nonaktif')));
CREATE TABLE IF NOT EXISTS suppliers (
    id INTEGER PRIMARY KEY AUTOINCREMENT, kode TEXT NOT NULL UNIQUE, nama TEXT NOT NULL, jenis_pasokan TEXT,
    kontak TEXT, alamat TEXT, harga_beli_terakhir REAL CHECK (harga_beli_terakhir IS NULL OR harga_beli_terakhir >= 0),
    termin TEXT NOT NULL DEFAULT 'Tunai' CHECK (termin IN ('Tunai','Kredit')),
    saldo_awal_utang REAL NOT NULL DEFAULT 0 CHECK (saldo_awal_utang >= 0),
    status TEXT NOT NULL DEFAULT 'Aktif' CHECK (status IN ('Aktif','Nonaktif')));
CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT, kode TEXT NOT NULL UNIQUE, nama TEXT NOT NULL, kategori TEXT NOT NULL,
    satuan TEXT NOT NULL, supplier_id INTEGER REFERENCES suppliers(id),
    harga_beli_ref REAL CHECK (harga_beli_ref IS NULL OR harga_beli_ref >= 0),
    harga_jual_standar REAL CHECK (harga_jual_standar IS NULL OR harga_jual_standar >= 0),
    stok_minimum REAL NOT NULL DEFAULT 0 CHECK (stok_minimum >= 0), akun_persediaan TEXT REFERENCES accounts(kode),
    status TEXT NOT NULL DEFAULT 'Aktif' CHECK (status IN ('Aktif','Nonaktif')));
CREATE TABLE IF NOT EXISTS ponds (
    id INTEGER PRIMARY KEY AUTOINCREMENT, kode TEXT NOT NULL UNIQUE, nama TEXT NOT NULL,
    luas_m2 REAL CHECK (luas_m2 IS NULL OR luas_m2 >= 0),
    status TEXT NOT NULL DEFAULT 'Kosong' CHECK (status IN ('Kosong','Persiapan','Budidaya','Panen')));
CREATE TABLE IF NOT EXISTS fixed_assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT, kode TEXT NOT NULL UNIQUE, nama TEXT NOT NULL,
    kelompok TEXT NOT NULL CHECK (kelompok IN ('Bangunan','Pompa dan mesin','Peralatan','Kendaraan')),
    tgl_perolehan TEXT, harga_perolehan REAL CHECK (harga_perolehan IS NULL OR harga_perolehan >= 0),
    umur_tahun REAL CHECK (umur_tahun IS NULL OR umur_tahun > 0),
    nilai_sisa REAL CHECK (nilai_sisa IS NULL OR nilai_sisa >= 0), metode TEXT NOT NULL DEFAULT 'Garis lurus',
    akumulasi_awal REAL CHECK (akumulasi_awal IS NULL OR akumulasi_awal >= 0),
    akun_aset TEXT REFERENCES accounts(kode), akun_akumulasi TEXT REFERENCES accounts(kode),
    status TEXT NOT NULL DEFAULT 'Aktif' CHECK (status IN ('Aktif','Nonaktif')));
CREATE TABLE IF NOT EXISTS shipping_rates (
    id INTEGER PRIMARY KEY AUTOINCREMENT, nama TEXT NOT NULL,
    dasar TEXT NOT NULL CHECK (dasar IN ('Per kg','Per trip','Per tujuan')), tujuan TEXT,
    tarif REAL NOT NULL CHECK (tarif >= 0), ditanggung TEXT NOT NULL DEFAULT 'Belum ditentukan',
    status TEXT NOT NULL DEFAULT 'Aktif');
CREATE TABLE IF NOT EXISTS opening_stock (
    id INTEGER PRIMARY KEY AUTOINCREMENT, item_id INTEGER NOT NULL UNIQUE REFERENCES items(id),
    jumlah REAL NOT NULL DEFAULT 0 CHECK (jumlah >= 0), nilai REAL NOT NULL DEFAULT 0 CHECK (nilai >= 0));
CREATE TABLE IF NOT EXISTS opening_balances (
    id INTEGER PRIMARY KEY AUTOINCREMENT, kode_akun TEXT NOT NULL REFERENCES accounts(kode),
    debit REAL NOT NULL DEFAULT 0 CHECK (debit >= 0), kredit REAL NOT NULL DEFAULT 0 CHECK (kredit >= 0),
    tanggal TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS periods (
    id INTEGER PRIMARY KEY AUTOINCREMENT, bulan TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'Terbuka' CHECK (status IN ('Terbuka','Tertutup')),
    ditutup_oleh INTEGER REFERENCES users(id), tgl_tutup TEXT);
CREATE TABLE IF NOT EXISTS app_settings (kunci TEXT PRIMARY KEY, nilai TEXT);
CREATE TABLE IF NOT EXISTS counters (kunci TEXT PRIMARY KEY, nilai INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS business_profile (kunci TEXT PRIMARY KEY, nilai TEXT);
CREATE TABLE IF NOT EXISTS cultivation_cycles (
    id INTEGER PRIMARY KEY AUTOINCREMENT, kode TEXT NOT NULL UNIQUE, pond_id INTEGER NOT NULL REFERENCES ponds(id),
    tgl_tebar TEXT, jumlah_benih REAL CHECK (jumlah_benih IS NULL OR jumlah_benih >= 0),
    item_benih_id INTEGER REFERENCES items(id), perkiraan_panen TEXT,
    status TEXT NOT NULL DEFAULT 'Persiapan' CHECK (status IN ('Persiapan','Berjalan','Selesai')), keterangan TEXT,
    dibuat_oleh INTEGER REFERENCES users(id));
CREATE TABLE IF NOT EXISTS cultivation_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, cycle_id INTEGER REFERENCES cultivation_cycles(id),
    pond_id INTEGER REFERENCES ponds(id), tanggal TEXT NOT NULL,
    jenis TEXT NOT NULL CHECK (jenis IN ('Pakan','Pupuk','Kapur','Obat','Ikan mati','Panen')),
    item_id INTEGER REFERENCES items(id), jumlah REAL NOT NULL CHECK (jumlah > 0), ukuran TEXT, keterangan TEXT,
    dibuat_oleh INTEGER REFERENCES users(id));
CREATE TABLE IF NOT EXISTS deliveries (
    id INTEGER PRIMARY KEY AUTOINCREMENT, no_surat_jalan TEXT NOT NULL UNIQUE, tanggal TEXT NOT NULL,
    customer_id INTEGER REFERENCES customers(id), transaction_id INTEGER REFERENCES transactions(id),
    kendaraan TEXT, pengemudi TEXT, berat REAL CHECK (berat IS NULL OR berat >= 0),
    status TEXT NOT NULL DEFAULT 'Disiapkan' CHECK (status IN ('Disiapkan','Dikirim','Diterima')),
    biaya_angkut REAL CHECK (biaya_angkut IS NULL OR biaya_angkut >= 0), dibuat_oleh INTEGER REFERENCES users(id));
CREATE TABLE IF NOT EXISTS stock_counts (
    id INTEGER PRIMARY KEY AUTOINCREMENT, tanggal TEXT NOT NULL, item_id INTEGER NOT NULL REFERENCES items(id),
    jumlah_fisik REAL NOT NULL CHECK (jumlah_fisik >= 0), nilai REAL CHECK (nilai IS NULL OR nilai >= 0),
    status TEXT NOT NULL DEFAULT 'Draft' CHECK (status IN ('Draft','Final')),
    dibuat_oleh INTEGER REFERENCES users(id), UNIQUE (tanggal, item_id));
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, no TEXT NOT NULL UNIQUE, tanggal TEXT NOT NULL,
    jenis TEXT NOT NULL, customer_id INTEGER REFERENCES customers(id), supplier_id INTEGER REFERENCES suppliers(id),
    employee_id INTEGER REFERENCES employees(id), keterangan TEXT, jatuh_tempo TEXT,
    total REAL NOT NULL CHECK (total > 0),
    status TEXT NOT NULL DEFAULT 'Draft' CHECK (status IN ('Draft','Diposting','Dibatalkan')),
    dibuat_oleh INTEGER NOT NULL REFERENCES users(id), alasan_batal TEXT, dibatalkan_oleh INTEGER REFERENCES users(id),
    dibuat_pada TEXT NOT NULL, diposting_pada TEXT);
CREATE TABLE IF NOT EXISTS transaction_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT, transaction_id INTEGER NOT NULL REFERENCES transactions(id),
    item_id INTEGER REFERENCES items(id), akun TEXT, uraian TEXT,
    jumlah REAL NOT NULL CHECK (jumlah > 0), harga REAL NOT NULL CHECK (harga >= 0), subtotal REAL NOT NULL);
CREATE TABLE IF NOT EXISTS journal_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT, transaction_id INTEGER REFERENCES transactions(id), tanggal TEXT NOT NULL,
    jenis TEXT NOT NULL CHECK (jenis IN ('otomatis','manual','penyesuaian','penutup','pembalik')),
    keterangan TEXT NOT NULL, kunci TEXT UNIQUE, dibuat_oleh INTEGER REFERENCES users(id), dibuat_pada TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS journal_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT, entry_id INTEGER NOT NULL REFERENCES journal_entries(id),
    kode_akun TEXT NOT NULL REFERENCES accounts(kode),
    debit REAL NOT NULL DEFAULT 0 CHECK (debit >= 0), kredit REAL NOT NULL DEFAULT 0 CHECK (kredit >= 0));
CREATE TABLE IF NOT EXISTS depreciation_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT, asset_id INTEGER NOT NULL REFERENCES fixed_assets(id),
    bulan TEXT NOT NULL, jumlah REAL NOT NULL, entry_id INTEGER REFERENCES journal_entries(id),
    UNIQUE (asset_id, bulan));
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT, waktu TEXT NOT NULL, jenis_log TEXT NOT NULL, email TEXT,
    nama_input TEXT, role TEXT, aksi TEXT NOT NULL, objek TEXT, nilai_lama TEXT, nilai_baru TEXT,
    hasil TEXT NOT NULL CHECK (hasil IN ('Berhasil','Gagal','Ditolak')), keterangan TEXT);
CREATE TRIGGER IF NOT EXISTS audit_tolak_ubah BEFORE UPDATE ON audit_log
BEGIN SELECT RAISE(ABORT, 'Audit trail hanya boleh ditambah'); END;
CREATE TRIGGER IF NOT EXISTS audit_tolak_hapus BEFORE DELETE ON audit_log
BEGIN SELECT RAISE(ABORT, 'Audit trail hanya boleh ditambah'); END;
"""

LOG_AUTENTIKASI = "Autentikasi"
LOG_TRANSAKSI = "Aktivitas transaksi"
LOG_MASTER = "Perubahan admin dan master"


def init_db():
    """Buat tabel yang belum ada dan isi data awal. Aman dijalankan berulang."""
    with get_conn() as c:
        c.executescript(SKEMA)
        if c.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
            for nama, email, role, pin in USERS_AWAL:
                c.execute("INSERT INTO users (nama,email,role,pin_hash) VALUES (?,?,?,?)",
                          (nama, email, role, hash_pin(pin)))
        if c.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == 0:
            c.executemany("INSERT INTO accounts (kode,nama,kelompok,saldo_normal) VALUES (?,?,?,?)", AKUN_AWAL)
        for k, v in KEBIJAKAN_AWAL.items():
            c.execute("INSERT OR IGNORE INTO app_settings (kunci,nilai) VALUES (?,?)", (k, v))
        if c.execute("SELECT COUNT(*) FROM employees").fetchone()[0] == 0:
            # Data awal 5 karyawan (Modul 6.2). Nama diganti Owner di Data Master; tarif Rp150.000/hari.
            for i in range(1, 6):
                c.execute("INSERT INTO employees (kode,nama,tarif_harian) VALUES (?,?,150000)",
                          (f"EMP-{i:03d}", f"Karyawan {i} (isi nama)"))
        if c.execute("SELECT COUNT(*) FROM suppliers").fetchone()[0] == 0:
            c.execute("INSERT INTO suppliers (kode,nama,jenis_pasokan,alamat) VALUES ('SUP-0001','Supplier Benih Bali (isi nama)','Benih','Bali')")
            c.execute("INSERT INTO suppliers (kode,nama,jenis_pasokan,alamat) VALUES ('SUP-0002','Supplier Benih Jepara (isi nama)','Benih','Jepara')")
        c.execute("INSERT OR IGNORE INTO periods (bulan) VALUES (?)", (hari_ini().strftime("%Y-%m"),))


# ------------------------------------------------------------------ pengaturan sederhana
def ambil_set(kunci: str, default: str = "") -> str:
    r = satu("SELECT nilai FROM app_settings WHERE kunci = ?", (kunci,))
    return r["nilai"] if r and r["nilai"] is not None else default


def simpan_set(conn, kunci: str, nilai: str):
    conn.execute("INSERT INTO app_settings (kunci,nilai) VALUES (?,?) ON CONFLICT(kunci) DO UPDATE SET nilai=excluded.nilai",
                 (kunci, nilai))


def nomor_berikut(conn, kunci: str) -> int:
    """Penghitung yang tidak pernah turun, jadi nomor tidak dipakai ulang."""
    conn.execute("INSERT OR IGNORE INTO counters (kunci,nilai) VALUES (?,0)", (kunci,))
    conn.execute("UPDATE counters SET nilai = nilai + 1 WHERE kunci = ?", (kunci,))
    return conn.execute("SELECT nilai FROM counters WHERE kunci = ?", (kunci,)).fetchone()[0]


def kode_otomatis(conn, tabel: str, awalan: str, lebar: int) -> str:
    n = nomor_berikut(conn, f"kode:{tabel}")
    kode = f"{awalan}{n:0{lebar}d}"
    while conn.execute(f"SELECT 1 FROM {tabel} WHERE kode = ?", (kode,)).fetchone():
        n = nomor_berikut(conn, f"kode:{tabel}")
        kode = f"{awalan}{n:0{lebar}d}"
    return kode


# ------------------------------------------------------------------ audit trail (hanya menambah)
def catat(conn, jenis_log, aksi, hasil, user=None, objek=None, nilai_lama=None, nilai_baru=None,
          keterangan=None, email=None, nama_input=None, role=None):
    """Tambah satu baris audit. PIN dan data rahasia tidak pernah dicatat."""
    if user:
        email, nama_input, role = user.get("email"), user.get("nama"), user.get("jabatan")
    conn.execute(
        "INSERT INTO audit_log (waktu,jenis_log,email,nama_input,role,aksi,objek,nilai_lama,nilai_baru,hasil,keterangan) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (waktu_teks(), jenis_log, email, nama_input, role, aksi, objek,
         None if nilai_lama is None else str(nilai_lama), None if nilai_baru is None else str(nilai_baru),
         hasil, keterangan))


def catat_sendiri(jenis_log, aksi, hasil, **kolom):
    with get_conn() as c:
        catat(c, jenis_log, aksi, hasil, **kolom)


def tolak_akses(user: dict, objek: str):
    """Dipakai backend saat pengguna tidak berhak: dicatat sebagai Ditolak."""
    catat_sendiri(LOG_TRANSAKSI, "akses ditolak", "Ditolak", user=user, objek=objek)
    return False, TIDAK_BERHAK


def owner(user: dict) -> bool:
    return bool(user) and user.get("jabatan") == "Owner"


# ------------------------------------------------------------------ login
EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PESAN_GAGAL = "Data login tidak sesuai. Periksa kembali nama, email, jabatan, dan PIN."


def proses_login(nama: str, email: str, jabatan, pin: str):
    """Return (berhasil, pesan, data_user). Pesan gagal sengaja umum."""
    email = (email or "").strip().lower()
    info = dict(email=email, nama_input=(nama or "").strip(), role=jabatan)
    if not (nama or "").strip() or not email or not jabatan or not pin:
        catat_sendiri(LOG_AUTENTIKASI, "login", "Gagal", keterangan="Kolom belum lengkap", **info)
        return False, "Semua kolom wajib diisi.", None
    if not EMAIL_REGEX.match(email):
        catat_sendiri(LOG_AUTENTIKASI, "login", "Gagal", keterangan="Format email salah", **info)
        return False, "Format email tidak valid.", None
    if not (pin.isdigit() and 4 <= len(pin) <= 6):
        catat_sendiri(LOG_AUTENTIKASI, "login", "Gagal", keterangan="Format PIN salah", **info)
        return False, "PIN harus berupa 4 sampai 6 angka.", None

    with get_conn() as c:
        u = c.execute("SELECT * FROM users WHERE email = ? AND status = 'Aktif'", (email,)).fetchone()
        if u is None:
            catat(c, LOG_AUTENTIKASI, "login", "Gagal", keterangan="Data tidak cocok", **info)
            return False, PESAN_GAGAL, None
        if u["dikunci_sampai"]:
            batas = datetime.fromisoformat(u["dikunci_sampai"])
            if sekarang() < batas:
                sisa = int((batas - sekarang()).total_seconds() // 60) + 1
                catat(c, LOG_AUTENTIKASI, "login", "Ditolak", keterangan="Akun terkunci", **info)
                return False, f"Akun terkunci sementara. Coba lagi dalam {sisa} menit.", None
        cocok = (u["nama"].strip().lower() == nama.strip().lower() and u["role"] == jabatan
                 and cek_pin(pin, u["pin_hash"]))
        if cocok:
            c.execute("UPDATE users SET jumlah_gagal = 0, dikunci_sampai = NULL WHERE id = ?", (u["id"],))
            catat(c, LOG_AUTENTIKASI, "login", "Berhasil", **info)
            return True, "Login berhasil.", {"id": u["id"], "nama": u["nama"], "email": u["email"], "jabatan": u["role"]}
        gagal = u["jumlah_gagal"] + 1
        catat(c, LOG_AUTENTIKASI, "login", "Gagal", keterangan="Data tidak cocok", **info)
        if gagal >= MAX_GAGAL:
            kunci = (sekarang() + timedelta(minutes=KUNCI_MENIT)).isoformat()
            c.execute("UPDATE users SET jumlah_gagal = 0, dikunci_sampai = ? WHERE id = ?", (kunci, u["id"]))
            catat(c, LOG_AUTENTIKASI, "akun terkunci", "Berhasil",
                  keterangan=f"Dikunci {KUNCI_MENIT} menit setelah {MAX_GAGAL} kali gagal", **info)
            return False, f"Terlalu banyak percobaan gagal. Akun dikunci {KUNCI_MENIT} menit.", None
        c.execute("UPDATE users SET jumlah_gagal = ? WHERE id = ?", (gagal, u["id"]))
        return False, PESAN_GAGAL, None

import re

from database import (EMAIL_REGEX, JABATAN, KEBIJAKAN_AWAL, LOG_AUTENTIKASI, LOG_MASTER, ambil_set, catat, get_conn, hash_pin, owner,
                      semua, satu, simpan_set, tolak_akses)


def daftar_pengguna(user: dict) -> list:
    if not owner(user):
        return []
    return semua("SELECT id, nama, email, role, status, jumlah_gagal, dikunci_sampai FROM users ORDER BY id")


def _pin_valid(pin: str) -> bool:
    return bool(pin) and pin.isdigit() and 4 <= len(pin) <= 6


def buat_pengguna(user: dict, nama: str, email: str, role: str, pin: str):
    if not owner(user):
        return tolak_akses(user, "Pengguna")
    nama, email = (nama or "").strip(), (email or "").strip().lower()
    if not nama or not email:
        return False, "Nama dan email wajib diisi."
    if not EMAIL_REGEX.match(email):
        return False, "Format email tidak valid."
    if role not in JABATAN:
        return False, "Pilih jabatan."
    if not _pin_valid(pin):
        return False, "PIN harus berupa 4 sampai 6 angka."
    if satu("SELECT 1 AS x FROM users WHERE email = ?", (email,)):
        return False, "Email sudah dipakai."
    with get_conn() as c:
        n = c.execute("INSERT INTO users (nama,email,role,pin_hash) VALUES (?,?,?,?)", (nama, email, role, hash_pin(pin))).lastrowid
        c.execute("UPDATE employees SET user_id = ? WHERE email = ? AND user_id IS NULL", (n, email))
        catat(c, LOG_MASTER, "tambah pengguna", "Berhasil", user=user, objek=f"users#{n}", nilai_baru=f"{nama} / {email} / {role}")
    return True, "Pengguna dibuat. PIN tersimpan sebagai hash dan tidak dicatat."


def ubah_pin(user: dict, id_: int, pin: str):
    if not owner(user):
        return tolak_akses(user, "Ubah PIN")
    if not _pin_valid(pin):
        return False, "PIN harus berupa 4 sampai 6 angka."
    with get_conn() as c:
        if not c.execute("SELECT 1 FROM users WHERE id = ?", (id_,)).fetchone():
            return False, "Pengguna tidak ditemukan."
        c.execute("UPDATE users SET pin_hash=?, jumlah_gagal=0, dikunci_sampai=NULL WHERE id=?", (hash_pin(pin), id_))
        catat(c, LOG_MASTER, "ubah PIN pengguna", "Berhasil", user=user, objek=f"users#{id_}")   # PIN tidak dicatat
    return True, "PIN diubah."


def ubah_status(user: dict, id_: int, aktif: bool):
    if not owner(user):
        return tolak_akses(user, "Status pengguna")
    if id_ == user["id"]:
        return False, "Anda tidak bisa menonaktifkan akun sendiri."
    baru = "Aktif" if aktif else "Nonaktif"
    with get_conn() as c:
        r = c.execute("SELECT status, role FROM users WHERE id = ?", (id_,)).fetchone()
        if not r:
            return False, "Pengguna tidak ditemukan."
        if not aktif and r["role"] == "Owner" and c.execute("SELECT COUNT(*) FROM users WHERE role='Owner' AND status='Aktif'").fetchone()[0] <= 1:
            return False, "Harus ada minimal satu Owner aktif."
        c.execute("UPDATE users SET status = ? WHERE id = ?", (baru, id_))
        catat(c, LOG_MASTER, "ubah status pengguna", "Berhasil", user=user, objek=f"users#{id_}", nilai_lama=r["status"], nilai_baru=baru)
    return True, f"Status pengguna menjadi {baru}."


def buka_kunci(user: dict, id_: int):
    if not owner(user):
        return tolak_akses(user, "Buka kunci akun")
    with get_conn() as c:
        c.execute("UPDATE users SET jumlah_gagal=0, dikunci_sampai=NULL WHERE id=?", (id_,))
        catat(c, LOG_AUTENTIKASI, "buka kunci akun", "Berhasil", user=user, objek=f"users#{id_}")
    return True, "Kunci akun dibuka."


KEBIJAKAN_ISIAN = [
    ("batas_kas", "Batas minimum kas dan bank untuk peringatan (Rp, kosong = tidak ada peringatan)", "angka"),
    ("karyawan_ubah_harga", "Karyawan boleh mengubah harga saat transaksi penjualan?", ["Tidak", "Ya"]),
    ("karyawan_hapus", "Karyawan boleh menghapus transaksi", ["Milik sendiri", "Semua"]),
    ("upah_ke_produksi", "Upah karyawan dialokasikan ke biaya produksi (harga pokok)?", ["Tidak", "Ya"]),
    ("tahun_buku_mulai", "Tahun buku mulai bulan ke- (1 = Januari-Desember)", [str(i) for i in range(1, 13)]),
    ("termin_kredit", "Memakai termin kredit?", ["Ya", "Tidak"]),
]


def ambil_kebijakan() -> dict:
    d = dict(KEBIJAKAN_AWAL)
    d.setdefault("upah_ke_produksi", "Tidak")
    return {k: ambil_set(k, d.get(k, "")) for k in [x[0] for x in KEBIJAKAN_ISIAN]}


def simpan_kebijakan(user: dict, d: dict):
    if not owner(user):
        return tolak_akses(user, "Kebijakan")
    batas = (d.get("batas_kas") or "").strip()
    if batas:
        try:
            if float(batas) < 0:
                return False, "Batas kas tidak boleh negatif."
        except ValueError:
            return False, "Batas kas harus berupa angka."
    lama = ambil_kebijakan()
    with get_conn() as c:
        for k, v in d.items():
            if str(lama.get(k, "")) != str(v):
                simpan_set(c, k, str(v))
                catat(c, LOG_MASTER, "ubah kebijakan", "Berhasil", user=user, objek=k, nilai_lama=lama.get(k), nilai_baru=v)
    return True, "Kebijakan disimpan."

MILKFISH LEDGER - aplikasi web akuntansi budidaya ikan bandeng (Python + Streamlit + SQLite)

CARA MENJALANKAN
1. pip install -r requirements.txt
2. python jalankan.py        (memberi warna tema biru #025A95, kuning #FEE307, putih)
   Alternatif: streamlit run main.py  (warna tema mengikuti bawaan Streamlit)
Database milkfish.db dibuat otomatis di folder ini (bisa dibuka dengan DB Browser for SQLite).

AKUN AWAL (ganti PIN lewat Pengaturan > Pengguna dan PIN)
Owner     : Admin Milkfish       | adminmilkfish@gmail.com      | PIN 123456
Karyawan  : Staf Admin Milkfish  | stafadminmilkfish@gmail.com  | PIN 13579

ISI FOLDER
main.py            pengatur utama: sesi, menu per jabatan, cek hak akses di backend
jalankan.py        peluncur dengan warna tema
database.py        skema SQLite, hash PIN, login, audit trail (hanya tambah, dijaga trigger)
transaksi.py       draft -> posting (jurnal otomatis) -> hapus = dibatalkan (jurnal pembalik)
akuntansi.py       jurnal, buku besar, neraca saldo, penyesuaian, neraca lajur, laporan, penutupan
master.py          Data Master dan Informasi Usaha (satu mesin CRUD)
stok.py            stok opname dan estimasi stok
pengguna.py        pengguna, PIN, kebijakan
dashboard.py       data dashboard dan audit trail
ekspor.py          ekspor laporan ke Excel dan PDF
tampilan.py, hal_*.py   tampilan (hanya komponen bawaan Streamlit)
uji/               uji_skenario.py (skenario bab 12 modul) dan uji_halaman.py (uji asap tampilan)

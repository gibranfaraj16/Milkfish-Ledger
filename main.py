import os
import time

import streamlit as st
from PIL import Image

import hal_admin
import hal_akuntansi
import hal_dashboard
import hal_login
import hal_master
import hal_transaksi
import hal_usaha
from database import TIDAK_BERHAK, catat_sendiri, init_db, LOG_AUTENTIKASI, LOG_TRANSAKSI

BASE = os.path.dirname(os.path.abspath(__file__))
SESI_MAKS_DIAM = 30 * 60   # sesi berakhir bila 30 menit tidak aktif

# Warna tema (biru #025A95, kuning #FEE307, putih). jalankan.py memberi nilai yang sama lewat opsi baris perintah.
TEMA = {"theme.base": "light", "theme.primaryColor": "#025A95", "theme.backgroundColor": "#FFFFFF",
        "theme.secondaryBackgroundColor": "#EAF2F8", "theme.textColor": "#1B2A3A"}
try:
    for _k, _v in TEMA.items():
        st._config.set_option(_k, _v)
except Exception:
    pass

DATA_MASTER_OWNER = ["Daftar Akun", "Karyawan", "Persediaan", "Customer", "Supplier", "Tambak", "Aset Tetap", "Harga dan Ongkir", "Saldo Awal"]
DATA_MASTER_KARYAWAN = ["Persediaan", "Customer", "Supplier", "Tambak", "Aset Tetap", "Harga dan Ongkir", "Profil Saya"]
INFO_USAHA = ["Profil Usaha", "Siklus Budidaya", "Catatan Harian", "Panen", "Pengiriman", "Stok Opname"]

# Susunan menu dan hak akses per jabatan (Modul bab 2). (judul grup, daftar menu); judul None = tombol tunggal.
MENU_JABATAN = {
    "Owner": [(None, ["Dashboard"]), ("Data Master", DATA_MASTER_OWNER), ("Informasi Usaha", INFO_USAHA), (None, ["Transaksi"]),
              ("Akuntansi", hal_akuntansi.MENU), (None, ["Pengaturan"])],
    "Karyawan": [(None, ["Dashboard"]), ("Data Master", DATA_MASTER_KARYAWAN), ("Informasi Usaha", INFO_USAHA), (None, ["Transaksi"])],
}


def menu_boleh(jabatan: str) -> list:
    return [m for _, daftar in MENU_JABATAN.get(jabatan, []) for m in daftar]


def boleh_akses(jabatan: str, menu: str) -> bool:
    return menu in menu_boleh(jabatan)


# ------------------------------------------------------------------ sesi
def logout(pesan: str = "Anda telah logout.", aksi: str = "logout"):
    u = st.session_state.get("user")
    if u:
        catat_sendiri(LOG_AUTENTIKASI, aksi, "Berhasil", email=u["email"], nama_input=u["nama"], role=u["jabatan"])
    st.session_state.clear()
    st.session_state["info_login"] = pesan


def cek_sesi_habis():
    if "user" not in st.session_state:
        return
    if time.time() - st.session_state.get("terakhir_aktif", 0) > SESI_MAKS_DIAM:
        logout("Sesi berakhir karena tidak ada aktivitas. Silakan login kembali.", "sesi berakhir")
        st.rerun()
    st.session_state["terakhir_aktif"] = time.time()


def _pilih(menu: str):
    st.session_state["menu"] = menu


def sidebar(user: dict) -> str:
    aktif = st.session_state.get("menu", "Dashboard")   # bila menu tidak diizinkan, halaman_utama menolak dan mencatatnya
    with st.sidebar:
        logo = os.path.join(BASE, "assets", "logo_icon.png")
        if os.path.exists(logo):
            st.image(logo, width=64)
        st.markdown("### Milkfish Ledger")
        st.caption(f'{user["nama"]} ({user["jabatan"]})')
        for judul, daftar in MENU_JABATAN[user["jabatan"]]:
            if judul is None:
                for m in daftar:
                    st.button(("● " if m == aktif else "") + m, key=f"nav_{m}", on_click=_pilih, args=(m,))
            else:
                with st.expander(judul, expanded=aktif in daftar):
                    for m in daftar:
                        st.button(("● " if m == aktif else "") + m, key=f"nav_{m}", on_click=_pilih, args=(m,))
        st.divider()
        st.button("Logout", key="nav_logout", icon=":material/logout:", on_click=logout)
    return aktif


def halaman_utama():
    user = st.session_state["user"]
    menu = sidebar(user)
    # Pemeriksaan hak akses di server: berlaku walau menu sudah difilter
    if not boleh_akses(user["jabatan"], menu):
        catat_sendiri(LOG_TRANSAKSI, "akses ditolak", "Ditolak", user=user, objek=menu)
        st.error(TIDAK_BERHAK)
        return
    if menu == "Dashboard":
        hal_dashboard.render(user)
    elif menu == "Transaksi":
        hal_transaksi.render(user)
    elif menu == "Pengaturan":
        hal_admin.pengaturan(user)
    else:
        st.title(menu)
        if menu in hal_akuntansi.MENU:
            hal_akuntansi.render(user, menu)
        elif menu in INFO_USAHA:
            hal_usaha.render(user, menu)
        else:
            hal_master.render(user, menu)


# ------------------------------------------------------------------ titik masuk
_ikon = os.path.join(BASE, "assets", "logo_icon.png")
st.set_page_config(page_title="Milkfish Ledger", page_icon=Image.open(_ikon) if os.path.exists(_ikon) else None,
                   layout="wide", initial_sidebar_state="expanded")
init_db()
cek_sesi_habis()
if "user" in st.session_state:
    halaman_utama()
else:
    hal_login.render()


import time
import streamlit as st

from database import JABATAN, proses_login
from tampilan import BIRU
import os

LOGO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "logo.png")

def render():
    kiri, kanan = st.columns([1.1, 1], gap="large")
    with kiri:
        with st.container(border=True):
            st.markdown("## :blue[Milkfish] Ledger")
            st.markdown("### Angka lebih jelas. Keputusan lebih cerdas.")
            st.write("Satu ruang untuk merapikan transaksi tambak, memantau arus kas, dan melihat kesehatan usaha budidaya ikan bandeng.")
            a, b, c = st.columns(3)
            a.markdown("**Laporan terarah**")
            a.caption("Laporan keuangan yang jelas kapan saja.")
            b.markdown("**Arus kas terkontrol**")
            b.caption("Pantau pemasukan dan pengeluaran.")
            c.markdown("**Data lebih aman**")
            c.caption("Akses dibatasi sesuai jabatan, semua aktivitas tercatat.")
    with kanan:
        if os.path.exists(LOGO):
            st.image(LOGO, width=260)
        st.markdown("#### :blue[Masuk untuk melanjutkan ke sistem.]")
        info = st.session_state.pop("info_login", None)
        if info:
            st.info(info)
        with st.form("form_login"):
            nama = st.text_input("Nama Lengkap", placeholder="Masukkan nama lengkap")
            email = st.text_input("Email", placeholder="Masukkan email")
            jabatan = st.selectbox("Jabatan", JABATAN, index=None, placeholder="Pilih jabatan")
            pin = st.text_input("PIN Password", type="password", max_chars=6, placeholder="Masukkan 4-6 digit PIN",
                                help="Klik ikon mata untuk menampilkan atau menyembunyikan PIN.")
            kirim = st.form_submit_button("Masuk", type="primary")
        if kirim:
            ok, pesan, data = proses_login(nama, email, jabatan, pin)   # semua pengecekan di server
            if ok:
                st.session_state["user"] = data
                st.session_state["terakhir_aktif"] = time.time()
                st.session_state["menu"] = "Dashboard"
                st.rerun()
            else:
                st.error(pesan)
        st.caption("Belum punya akun? Hubungi administrator sistem.")

"""hal_admin.py - Pengaturan (pengguna dan PIN, periode, kebijakan). Hanya Owner."""

import pandas as pd
import streamlit as st

import akuntansi as ak
import pengguna as pg
from database import JABATAN, owner
from tampilan import label_bulan, munculkan_pesan, tabel, tampil_hasil


def pengaturan(user: dict):
    if not owner(user):
        st.error("Anda tidak memiliki akses.")
        return
    st.title("Pengaturan")
    munculkan_pesan()
    t1, t2, t3 = st.tabs(["Pengguna dan PIN", "Periode", "Kebijakan"])
    with t1:
        rows = pg.daftar_pengguna(user)
        tabel(pd.DataFrame([{"Nama": r["nama"], "Email": r["email"], "Jabatan": r["role"], "Status": r["status"],
                             "Terkunci": "Ya" if r["dikunci_sampai"] and r["dikunci_sampai"] > ak.waktu_sekarang_iso() else "Tidak"} for r in rows]))
        with st.expander("Tambah pengguna"):
            with st.form("form_user"):
                n = st.text_input("Nama lengkap")
                e = st.text_input("Email")
                j = st.selectbox("Jabatan", JABATAN)
                p = st.text_input("PIN (4-6 angka)", type="password", max_chars=6)
                if st.form_submit_button("Buat akun", type="primary"):
                    tampil_hasil(pg.buat_pengguna(user, n, e, j, p), rerun=True)
        if rows:
            st.markdown("**Kelola pengguna**")
            pilih = st.selectbox("Pengguna", [r["id"] for r in rows], format_func={r["id"]: f'{r["nama"]} ({r["email"]})' for r in rows}.get, key="pg_pilih")
            sel = next(r for r in rows if r["id"] == pilih)
            pin = st.text_input("PIN baru (4-6 angka)", type="password", max_chars=6, key="pg_pin")
            a, b, c = st.columns(3)
            if a.button("Ubah PIN", key="pg_ubah"):
                tampil_hasil(pg.ubah_pin(user, pilih, pin), rerun=True)
            if b.button("Nonaktifkan" if sel["status"] == "Aktif" else "Aktifkan", key="pg_status"):
                tampil_hasil(pg.ubah_status(user, pilih, sel["status"] != "Aktif"), rerun=True)
            if c.button("Buka kunci akun", key="pg_kunci"):
                tampil_hasil(pg.buka_kunci(user, pilih), rerun=True)
    with t2:
        st.caption("Bulan yang sudah ditutup terkunci. Membuka kembali periode hanya oleh Owner, dengan alasan tertulis yang tercatat di audit trail. Menutup periode dilakukan di Akuntansi > Penutupan.")
        per = ak.daftar_periode()
        tabel(pd.DataFrame([{"Periode": label_bulan(p["bulan"]), "Status": p["status"], "Ditutup oleh": p["penutup"] or "-", "Waktu tutup": p["tgl_tutup"] or "-"} for p in per]))
        tertutup = [p["bulan"] for p in per if p["status"] == "Tertutup"]
        if tertutup:
            bulan = st.selectbox("Buka kembali periode", tertutup, format_func=label_bulan, key="pr_bulan")
            alasan = st.text_input("Alasan tertulis (wajib)", key="pr_alasan")
            if st.button("Buka kembali", key="pr_buka"):
                tampil_hasil(ak.buka_periode(user, bulan, alasan), rerun=True)
    with t3:
        st.caption("Pengaturan ini menjawab hal yang masih perlu dikonfirmasi pada modul (bab 14). Setiap perubahan tercatat dengan nilai lama dan baru.")
        k = pg.ambil_kebijakan()
        with st.form("form_kebijakan"):
            nilai = {}
            for kunci, label, tipe in pg.KEBIJAKAN_ISIAN:
                if isinstance(tipe, list):
                    nilai[kunci] = st.selectbox(label, tipe, index=tipe.index(k[kunci]) if k[kunci] in tipe else 0)
                else:
                    nilai[kunci] = st.text_input(label, value=k[kunci])
            if st.form_submit_button("Simpan kebijakan", type="primary"):
                tampil_hasil(pg.simpan_kebijakan(user, nilai), rerun=True)

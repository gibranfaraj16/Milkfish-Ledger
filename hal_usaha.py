"""hal_usaha.py - Informasi Usaha (Modul bab 7): profil usaha, siklus budidaya, catatan harian, panen, pengiriman, stok opname."""

from datetime import date

import pandas as pd
import streamlit as st

import master
import stok
from database import hari_ini, owner, semua
from hal_master import crud
from tampilan import angka, munculkan_pesan, rupiah, status_badge, tabel, tampil_hasil, tgl

MENU_ENTITAS = {"Siklus Budidaya": "siklus", "Catatan Harian": "catatan", "Panen": "panen", "Pengiriman": "pengiriman"}


def _profil(user: dict):
    st.subheader("Profil Usaha")
    st.caption("Dipakai pada surat jalan dan kuitansi.")
    munculkan_pesan()
    p = master.ambil_profil()
    if owner(user):
        with st.form("form_profil"):
            nilai = {k: st.text_input(label, value=p.get(k, "")) for k, label in master.PROFIL_KUNCI}
            if st.form_submit_button("Simpan profil", type="primary"):
                tampil_hasil(master.simpan_profil(user, nilai), rerun=True)
    else:
        tabel(pd.DataFrame([{"Keterangan": label, "Isi": p.get(k) or "-"} for k, label in master.PROFIL_KUNCI]))


def _stok_opname(user: dict):
    st.subheader("Stok Opname")
    if owner(user):
        st.caption("Owner menginput hitungan, menilai persediaan, lalu memfinalisasi. Stok resmi akhir periode berasal dari stok opname final.")
    else:
        st.caption("Karyawan hanya menginput hitungan fisik. Penilaian dan finalisasi dilakukan Owner.")
    munculkan_pesan()
    rows = stok.daftar_opname(user)
    df = pd.DataFrame([{"Tanggal": tgl(r["tanggal"]), "Item": r["item_nama"], "Hitungan fisik": f'{angka(r["jumlah_fisik"], 0)} {r["satuan"]}',
                        "Estimasi": angka(r["estimasi"], 0), "Selisih": angka(r["selisih"], 0),
                        **({"Nilai": rupiah(r.get("nilai"))} if owner(user) else {}), "Status": r["status"], "Pencatat": r["pembuat"] or "-"} for r in rows])
    idx = tabel(df, key="tb_opname", pilih=True)

    items = semua("SELECT id, kode, nama, satuan FROM items WHERE status='Aktif' ORDER BY kode")
    if not items:
        st.info("Belum ada item persediaan. Tambahkan di Data Master > Persediaan.")
        return
    with st.expander("Input hitungan fisik", expanded=False):
        pilihan = {i["id"]: f'{i["kode"]} - {i["nama"]} ({i["satuan"]})' for i in items}
        a, b = st.columns(2)
        tanggal = a.date_input("Tanggal hitung", value=hari_ini(), max_value=hari_ini(), key="so_tgl", format="DD/MM/YYYY")
        item = b.selectbox("Item", list(pilihan), format_func=pilihan.get, key="so_item")
        e = stok.estimasi(item)
        if e:
            st.caption(f'Estimasi stok: {angka(e["estimasi"], 0)} (dasar {angka(e["dasar"], 0)} dari {e["sumber"]}, masuk {angka(e["masuk"], 0)}, keluar {angka(e["keluar"], 0)}). '
                       f'{e["catatan"]}')
        c, d = st.columns(2)
        fisik = c.number_input("Hitungan fisik", min_value=0.0, value=None, key="so_fisik")
        nilai = d.number_input("Nilai persediaan (Rp)", min_value=0.0, value=None, step=1000.0, key="so_nilai", disabled=not owner(user),
                               help="Hanya Owner yang menilai persediaan." if not owner(user) else "Nilai total persediaan item ini pada tanggal hitung.")
        if st.button("Simpan hitungan", type="primary", key="so_simpan"):
            if fisik is None:
                tampil_hasil((False, "Isi hitungan fisik."), rerun=True)
            tampil_hasil(stok.simpan_hitungan(user, tanggal, item, fisik, nilai), rerun=True)
    if idx is not None:
        r = rows[idx]
        st.markdown(f'**Terpilih:** {r["item_nama"]}, {tgl(r["tanggal"])}, status {r["status"]}')
        if r["status"] == "Draft":
            a, b, c = st.columns(3)
            fisik = a.number_input("Ubah hitungan fisik", min_value=0.0, value=float(r["jumlah_fisik"]), key=f'so_u_{r["id"]}')
            nilai = b.number_input("Ubah nilai (Rp)", min_value=0.0, value=r.get("nilai"), step=1000.0, key=f'so_n_{r["id"]}', disabled=not owner(user))
            with c:
                st.write("")
                if st.button("Simpan perubahan", key=f'so_sv_{r["id"]}'):
                    tampil_hasil(stok.simpan_hitungan(user, date.fromisoformat(r["tanggal"]), r["item_id"], fisik, nilai if owner(user) else None), rerun=True)
                if st.button("Hapus hitungan", key=f'so_del_{r["id"]}'):
                    tampil_hasil(stok.hapus_hitungan(user, r["id"]), rerun=True)
            if owner(user):
                if st.button("Finalisasi hitungan ini", type="primary", key=f'so_fin_{r["id"]}'):
                    tampil_hasil(stok.finalisasi(user, [r["id"]]), rerun=True)
        else:
            st.info("Stok opname yang sudah final tidak bisa diubah.")
    if owner(user):
        draft = [r for r in rows if r["status"] == "Draft" and r.get("nilai") is not None]
        if draft and st.button(f"Finalisasi semua draft yang sudah bernilai ({len(draft)})", key="so_fin_semua"):
            tampil_hasil(stok.finalisasi(user, [r["id"] for r in draft]), rerun=True)


def render(user: dict, menu: str):
    if menu == "Profil Usaha":
        _profil(user)
    elif menu in MENU_ENTITAS:
        crud(user, MENU_ENTITAS[menu])
    elif menu == "Stok Opname":
        _stok_opname(user)

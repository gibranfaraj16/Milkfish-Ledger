"""hal_master.py - Data Master (Modul bab 6) dan mesin halaman CRUD yang dipakai juga oleh Informasi Usaha."""

from datetime import date

import pandas as pd
import streamlit as st

import akuntansi as ak
import master
import stok
from database import owner, semua
from tampilan import (angka, df_entitas, formulir, kunci_form, munculkan_pesan, reset_form, rupiah, tabel, tampil_hasil, tgl)

MENU_ENTITAS = {"Daftar Akun": "akun", "Karyawan": "karyawan", "Persediaan": "item", "Customer": "customer", "Supplier": "supplier",
                "Tambak": "tambak", "Aset Tetap": "aset"}


def crud(user: dict, ent: str, judul: bool = True):
    """Daftar + tambah + ubah + hapus untuk satu entitas master. Hak akses diperiksa lagi di backend."""
    sp = master.ENT[ent]
    if judul:
        st.subheader(sp["judul"])
    if sp.get("catatan"):
        st.caption(sp["catatan"])
    if not master.boleh_lihat(user, ent):
        st.error("Anda tidak memiliki akses.")
        return
    munculkan_pesan()
    cari = st.text_input("Cari", key=f"cari_{ent}", placeholder="Ketik untuk mencari")
    rows = master.daftar(user, ent, cari)
    idx = tabel(df_entitas(ent, rows), key=f"tb_{ent}", pilih=True)
    if not owner(user):
        sembunyi = {m["k"] for m in sp["medan"] if m["rahasia"]}
    else:
        sembunyi = set()
    if master.boleh_tulis(user, ent):
        with st.expander(f"Tambah {sp['tunggal']}", expanded=False):
            kp = f"tambah_{ent}"
            with st.form(kunci_form(kp)):
                nilai = formulir(ent, None, kunci_form(kp), sembunyi)
                kirim = st.form_submit_button("Simpan", type="primary")
            if kirim:
                ok, p = master.simpan(user, ent, nilai)
                if ok:
                    reset_form(kp)
                tampil_hasil((ok, p), rerun=True)
    if idx is not None:
        row = rows[idx]
        mentah = master.ambil(user, ent, row["id"])   # kolom rahasia sudah dibuang untuk Karyawan
        st.markdown("**Ubah data terpilih**")
        if master.boleh_tulis(user, ent, mentah):
            with st.form(f"ubah_{ent}_{row['id']}"):
                nilai = formulir(ent, mentah, f"u_{ent}_{row['id']}", sembunyi)
                kirim = st.form_submit_button("Simpan perubahan", type="primary")
            if kirim:
                tampil_hasil(master.simpan(user, ent, nilai, row["id"]), rerun=True)
            ya = st.checkbox("Saya yakin ingin menghapus data ini", key=f"yakin_{ent}_{row['id']}")
            if st.button("Hapus", key=f"hapus_{ent}_{row['id']}", disabled=not ya):
                tampil_hasil(master.hapus(user, ent, row["id"]), rerun=True)
        else:
            st.info("Anda hanya bisa melihat data ini.")
    elif master.boleh_tulis(user, ent):
        st.caption("Pilih satu baris pada tabel untuk mengubah atau menghapusnya.")


def _persediaan(user: dict):
    crud(user, "item")
    st.markdown("**Estimasi stok saat ini**")
    st.caption("Estimasi = stok dasar + pembelian - pemakaian tercatat. Hanya perkiraan di antara dua stok opname dan bukan dasar jurnal.")
    baris = []
    for r in master.daftar(user, "item"):
        e = stok.estimasi(r["id"])
        if e:
            baris.append({"Item": r["nama"], "Dasar": f'{angka(e["dasar"], 0)} ({e["sumber"]})', "Masuk": angka(e["masuk"], 0),
                          "Keluar": angka(e["keluar"], 0), "Estimasi": f'{angka(e["estimasi"], 0)} {r["satuan"]}',
                          "Minimum": angka(r["stok_minimum"], 0)})
    tabel(pd.DataFrame(baris))


def _harga_ongkir(user: dict):
    st.subheader("Harga dan Ongkir")
    st.caption("Perubahan harga tidak mengubah transaksi lama yang sudah diposting. Harga beli mengikuti harga aktual saat transaksi.")
    munculkan_pesan()
    t1, t2, t3 = st.tabs(["Harga jual standar", "Harga khusus customer", "Ongkos kirim"])
    with t1:
        ikan = [r for r in master.daftar(user, "item") if r["kategori"] == "Ikan hasil panen"]
        tabel(pd.DataFrame([{"Ikan (ukuran)": r["nama"], "Harga jual standar": rupiah(r.get("harga_jual_standar")), "Satuan": r["satuan"]} for r in ikan]))
        if owner(user) and ikan:
            with st.form("form_harga_ikan"):
                pilih = st.selectbox("Item ikan", [r["id"] for r in ikan], format_func={r["id"]: r["nama"] for r in ikan}.get)
                harga = st.number_input("Harga jual standar (Rp/kg)", min_value=0.0, step=500.0, value=None)
                if st.form_submit_button("Simpan harga", type="primary"):
                    if harga is None:
                        tampil_hasil((False, "Isi harga."), rerun=True)
                    mentah = master.satu_baris("item", pilih)
                    mentah["harga_jual_standar"] = harga
                    tampil_hasil(master.simpan(user, "item", mentah, pilih), rerun=True)
        elif not ikan:
            st.caption("Tambahkan item kategori Ikan hasil panen di menu Persediaan lebih dulu.")
    with t2:
        cs = master.daftar(user, "customer")
        tabel(pd.DataFrame([{"Customer": r["nama"], "Harga khusus": rupiah(r.get("harga_khusus"))} for r in cs]))
        if owner(user) and cs:
            with st.form("form_harga_cust"):
                pilih = st.selectbox("Customer", [r["id"] for r in cs], format_func={r["id"]: r["nama"] for r in cs}.get)
                harga = st.number_input("Harga khusus (Rp/kg, kosong = ikut harga standar)", min_value=0.0, step=500.0, value=None)
                if st.form_submit_button("Simpan harga khusus", type="primary"):
                    mentah = master.satu_baris("customer", pilih)
                    mentah["harga_khusus"] = harga
                    tampil_hasil(master.simpan(user, "customer", mentah, pilih), rerun=True)
    with t3:
        crud(user, "tarif", judul=False)


def _profil_saya(user: dict):
    st.subheader("Profil Saya")
    p = master.profil_saya(user)
    if not p:
        st.info("Profil karyawan Anda belum dihubungkan. Minta Owner mengisi email Anda di Data Master > Karyawan.")
        return
    st.caption("Tarif dan gaji hanya terlihat oleh Owner.")
    tabel(pd.DataFrame([{"Keterangan": k.replace("_", " ").capitalize(), "Isi": (v or "-")} for k, v in p.items()]))


def _saldo_awal(user: dict):
    st.subheader("Saldo Awal")
    st.caption("Total debit harus sama dengan total kredit sebelum difinalisasi. Rincian piutang per customer dan utang per supplier harus sama dengan akun "
               "Piutang Usaha dan Utang Usaha. Persediaan awal diisi lengkap dengan kuantitas dan nilainya.")
    munculkan_pesan()
    sa = master.ambil_saldo_awal()
    if sa["final"]:
        st.success("Saldo awal sudah final dan tidak bisa diubah.")
    tanggal = st.date_input("Tanggal saldo awal", value=date.fromisoformat(sa["tanggal"]) if sa["tanggal"] else date.today().replace(day=1),
                            key="sa_tgl", format="DD/MM/YYYY", disabled=sa["final"])
    akun = [a for a in semua("SELECT kode, nama FROM accounts WHERE status='Aktif' AND kelompok != 'Akun sementara' ORDER BY kode")]
    awal = sa["baris"]
    df = pd.DataFrame([{"Kode": a["kode"], "Akun": a["nama"], "Debit": float(awal.get(a["kode"], {}).get("debit", 0) or 0),
                        "Kredit": float(awal.get(a["kode"], {}).get("kredit", 0) or 0)} for a in akun])
    ed = st.data_editor(df, hide_index=True, disabled=["Kode", "Akun"] + (["Debit", "Kredit"] if sa["final"] else []), key="sa_editor",
                        column_config={"Debit": st.column_config.NumberColumn(min_value=0, step=1000, format="%.0f"),
                                       "Kredit": st.column_config.NumberColumn(min_value=0, step=1000, format="%.0f")})
    td, tk = float(ed["Debit"].fillna(0).sum()), float(ed["Kredit"].fillna(0).sum())
    a, b, c = st.columns(3)
    a.metric("Total debit", rupiah(td))
    b.metric("Total kredit", rupiah(tk))
    c.metric("Selisih", rupiah(td - tk))
    if abs(td - tk) > 0.005:
        st.warning("Total debit belum sama dengan total kredit.")
    piu = sum(r.get("saldo_awal_piutang") or 0 for r in master.daftar(user, "customer"))
    utg = sum(r.get("saldo_awal_utang") or 0 for r in master.daftar(user, "supplier"))
    d1 = float(ed.loc[ed["Kode"] == "1103", "Debit"].sum()) - float(ed.loc[ed["Kode"] == "1103", "Kredit"].sum())
    d2 = float(ed.loc[ed["Kode"] == "2101", "Kredit"].sum()) - float(ed.loc[ed["Kode"] == "2101", "Debit"].sum())
    st.caption(f"Rincian piutang per customer: {rupiah(piu)} (akun Piutang Usaha: {rupiah(d1)}). Rincian utang per supplier: {rupiah(utg)} (akun Utang Usaha: {rupiah(d2)}). "
               "Isi saldo awal piutang dan utang di Data Master > Customer dan Supplier.")

    st.markdown("**Persediaan awal (kuantitas dan nilai per item)**")
    items = semua("SELECT i.id, i.kode, i.nama, i.satuan, i.akun_persediaan FROM items i WHERE i.status='Aktif' AND i.akun_persediaan IN ('1104','1105','1106','1107') ORDER BY i.kode")
    os_ = {r["item_id"]: r for r in semua("SELECT * FROM opening_stock")}
    dfi = pd.DataFrame([{"ID": i["id"], "Item": f'{i["kode"]} - {i["nama"]}', "Akun": i["akun_persediaan"], "Satuan": i["satuan"],
                         "Jumlah": float(os_.get(i["id"], {}).get("jumlah", 0)), "Nilai (Rp)": float(os_.get(i["id"], {}).get("nilai", 0))} for i in items])
    if dfi.empty:
        st.info("Belum ada item persediaan. Tambahkan di Data Master > Persediaan.")
        edi = dfi
    else:
        edi = st.data_editor(dfi, hide_index=True, disabled=["ID", "Item", "Akun", "Satuan"] + (["Jumlah", "Nilai (Rp)"] if sa["final"] else []),
                             key="sa_item", column_config={"ID": None, "Jumlah": st.column_config.NumberColumn(min_value=0),
                                                           "Nilai (Rp)": st.column_config.NumberColumn(min_value=0, format="%.0f")})
    if not sa["final"]:
        k1, k2 = st.columns(2)
        simpan = k1.button("Simpan draft saldo awal", key="sa_simpan")
        final = k2.button("Finalisasi saldo awal", type="primary", key="sa_final")
        if simpan or final:
            baris = [(r["Kode"], r["Debit"], r["Kredit"]) for _, r in ed.iterrows()]
            for _, r in edi.iterrows():
                master.simpan_stok_awal(user, int(r["ID"]), float(r["Jumlah"] or 0), float(r["Nilai (Rp)"] or 0))
            tampil_hasil(master.simpan_saldo_awal(user, tanggal, baris, bool(final)), rerun=True)


def render(user: dict, menu: str):
    if menu in ("Persediaan",):
        _persediaan(user)
    elif menu in MENU_ENTITAS:
        crud(user, MENU_ENTITAS[menu])
    elif menu == "Harga dan Ongkir":
        _harga_ongkir(user)
    elif menu == "Saldo Awal":
        if not owner(user):
            st.error("Anda tidak memiliki akses.")
        else:
            _saldo_awal(user)
    elif menu == "Profil Saya":
        _profil_saya(user)

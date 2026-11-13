"""hal_transaksi.py - Transaksi operasional (Modul bab 8): draft, posting, hapus (batal dengan jejak)."""

import uuid
from datetime import date, timedelta

import pandas as pd
import streamlit as st

import master
import transaksi as tr
from database import hari_ini, owner, semua
from tampilan import (angka, kunci_form, munculkan_pesan, reset_form, rupiah, status_badge, tabel, tampil_hasil, tgl)


def _opsi_barang(jenis: str, kategori):
    sp = tr.SPEC[jenis]
    if jenis.startswith("penjualan"):
        kat = "Ikan hasil panen"
    else:
        kat = tr.KAT_ITEM.get(kategori)
    if not kat:
        return []
    return [(i["id"], f'{i["kode"]} - {i["nama"]} ({i["satuan"]})') for i in
            semua("SELECT id, kode, nama, satuan FROM items WHERE status='Aktif' AND kategori = ? ORDER BY kode", (kat,))]


def _form(user: dict, awal: dict | None, prefix: str):
    """Formulir transaksi. Tidak memakai st.form agar isian berubah mengikuti jenis. Kembalikan (dict, simpan?, simpan+posting?)."""
    boleh = tr.jenis_boleh(user)
    jenis_awal = (awal or {}).get("jenis") or st.session_state.pop("trx_jenis_awal", None) or boleh[0]
    k = lambda n: f"{prefix}_{n}"
    jenis = st.selectbox("Jenis transaksi", boleh, index=boleh.index(jenis_awal) if jenis_awal in boleh else 0,
                         format_func=lambda x: tr.SPEC[x]["label"], key=k("jenis"))
    sp = tr.SPEC[jenis]
    a, b = st.columns(2)
    tanggal = a.date_input("Tanggal", value=date.fromisoformat((awal or {}).get("tanggal") or hari_ini().isoformat()), max_value=hari_ini(),
                           key=k("tgl"), format="DD/MM/YYYY")
    sumber = b.selectbox("Cara pembayaran / penerimaan" if sp["sumber"] != ["Kredit"] else "Pembayaran", sp["sumber"],
                         index=sp["sumber"].index(awal["sumber"]) if awal and awal.get("sumber") in sp["sumber"] else 0, key=k("sumber"))
    d = dict(jenis=jenis, tanggal=tanggal, sumber=sumber)
    kategori = None
    if sp["kategori"]:
        kats = list(sp["kategori"])
        kategori = st.selectbox("Kategori", kats, index=kats.index(awal["kategori"]) if awal and awal.get("kategori") in kats else 0, key=k("kat"))
        d["kategori"] = kategori
    if sp["pihak"]:
        fn = {"customer": master.opsi_customer, "supplier": master.opsi_supplier,
              "employee": lambda: [(r["id"], f'{r["kode"]} - {r["nama"]}') for r in semua("SELECT id,kode,nama FROM employees WHERE status='Aktif' ORDER BY kode")]}[sp["pihak"]]
        o = fn()
        wajib = sp["wajib"] or (jenis == "retur_penjualan" and sumber == "Piutang") or (jenis == "retur_pembelian" and sumber == "Utang") \
            or (jenis == "aset_tetap" and sumber == "Kredit")
        if not wajib and not any(v is None for v, _ in o):
            o = [(None, "-")] + o
        ids = [v for v, _ in o]
        kunci_awal = {"customer": "customer_id", "supplier": "supplier_id", "employee": "employee_id"}[sp["pihak"]]
        cur = (awal or {}).get(kunci_awal)
        pil = st.selectbox({"customer": "Customer", "supplier": "Supplier", "employee": "Karyawan"}[sp["pihak"]] + (" *" if wajib else ""), ids,
                           index=ids.index(cur) if cur in ids else 0, format_func=dict(o).get, key=k("pihak"))
        d[kunci_awal] = pil
    if sp["mode"] == "qty":
        o = _opsi_barang(jenis, kategori)
        if o:
            ids = [v for v, _ in o]
            cur = (awal or {}).get("baris", [{}])[0].get("item_id") if awal else None
            d["item_id"] = st.selectbox("Barang *", ids, index=ids.index(cur) if cur in ids else 0, format_func=dict(o).get, key=k("item"))
        elif kategori != "Ongkos angkut":
            st.warning("Belum ada item untuk kategori ini. Tambahkan di Data Master > Persediaan.")
        acuan = tr.harga_acuan(d.get("item_id"), d.get("customer_id")) if jenis.startswith("penjualan") else None
        c1, c2 = st.columns(2)
        ln = (awal or {}).get("baris", [{}])[0] if awal else {}
        d["jumlah"] = c1.number_input("Jumlah (kg/ekor/unit)", min_value=0.0, value=ln.get("jumlah"), key=k("jml"))
        harga_awal = ln.get("harga") if ln.get("harga") else acuan
        d["harga"] = c2.number_input("Harga satuan (Rp)", min_value=0.0, step=500.0, value=float(harga_awal) if harga_awal else None, key=k("hrg") + str(acuan),
                                     help=f"Harga acuan {rupiah(acuan)}" if acuan else None)
        if acuan and not owner(user):
            st.caption("Harga mengikuti harga acuan kecuali Owner mengizinkan Karyawan mengubahnya (Pengaturan > Kebijakan).")
    elif sp["mode"] == "gaji":
        emp = semua("SELECT tarif_harian FROM employees WHERE id = ?", (d.get("employee_id") or 0,))
        tarif = emp[0]["tarif_harian"] if emp else None
        ln = (awal or {}).get("baris", [{}])[0] if awal else {}
        d["jumlah"] = st.number_input("Jumlah hari hadir", min_value=0.0, step=1.0, value=ln.get("jumlah"), key=k("hari"))
        d["harga"] = tarif
        st.caption(f"Tarif harian: {rupiah(tarif)}. Gaji = hari hadir x tarif harian.")
    else:
        ln = (awal or {}).get("baris", [{}])[0] if awal else {}
        d["harga"] = st.number_input("Nominal (Rp)", min_value=0.0, step=1000.0, value=ln.get("harga"), key=k("nom"))
        d["jumlah"] = 1
    if sp.get("tempo"):
        d["jatuh_tempo"] = st.date_input("Jatuh tempo", value=date.fromisoformat((awal or {}).get("jatuh_tempo") or (hari_ini() + timedelta(days=14)).isoformat()),
                                         key=k("tempo"), format="DD/MM/YYYY")
    d["keterangan"] = st.text_input("Keterangan *", value=(awal or {}).get("keterangan") or "", max_chars=300, key=k("ket"))
    total = (d.get("jumlah") or 0) * (d.get("harga") or 0)
    st.info(f"Total: {rupiah(total)}")
    c1, c2 = st.columns(2)
    return d, c1.button("Simpan sebagai draft", key=k("draft")), c2.button("Simpan dan posting", type="primary", key=k("posting"))


def _input_baru(user: dict):
    pref = kunci_form("trx_baru")
    token = st.session_state.setdefault("trx_token", str(uuid.uuid4()))
    d, draft, post = _form(user, None, pref)
    if draft or post:
        terpakai = st.session_state.setdefault("trx_token_terpakai", set())
        if token in terpakai:   # menekan ulang tidak boleh menggandakan transaksi
            st.warning("Transaksi ini sudah disimpan.")
            return
        ok, p, tid = tr.simpan_draft(user, d)
        if ok and post:
            ok, p = tr.posting(user, tid)
            p = p if ok else f"Draft tersimpan tetapi belum diposting: {p}"
        if ok:
            terpakai.add(token)
            st.session_state["trx_token"] = str(uuid.uuid4())
            reset_form("trx_baru")
        tampil_hasil((ok, p), rerun=True)


def _detail(user: dict, id_: int):
    r = tr.ambil(user, id_)
    if not r:
        st.error("Transaksi tidak ditemukan atau bukan milik Anda.")
        return
    with st.container(border=True):
        a, b = st.columns([3, 1])
        a.markdown(f'**{r["no"]}** - {tr.SPEC[r["jenis"]]["label"]}')
        with b:
            status_badge(r["status"])
        st.write(f'Tanggal: {tgl(r["tanggal"])} | Dibuat oleh: {r["pembuat"]} | Total: {rupiah(r["total"])}')
        st.write(f'Keterangan: {r["keterangan"]}')
        if r["baris"]:
            ln = r["baris"][0]
            st.caption(f'Pembayaran: {r["sumber"] or "-"} | Kategori: {r["kategori"] or "-"} | Barang: {ln["item_nama"] or "-"} | '
                       f'Jumlah: {angka(ln["jumlah"], 0 if float(ln["jumlah"]).is_integer() else 2)} x {rupiah(ln["harga"])}')
        if r["status"] == "Dibatalkan":
            st.error(f'Dibatalkan. Alasan: {r["alasan_batal"]}. Jurnal pembalik dibuat dan data asli tetap tampil.')
        if owner(user) and r["jurnal"]:
            st.markdown("Jurnal")
            tabel(pd.DataFrame([{"Jenis": j["jenis"], "Akun": f'{j["kode_akun"]} {j["akun"]}', "Debit": rupiah(j["debit"]) if j["debit"] else "",
                                 "Kredit": rupiah(j["kredit"]) if j["kredit"] else ""} for j in r["jurnal"]]))
        elif not owner(user):
            st.caption("Jurnal, buku besar, dan laporan keuangan hanya dibuka oleh Owner.")

        if r["status"] == "Draft" and (owner(user) or r["dibuat_oleh"] == user["id"]):
            if st.button("Posting transaksi ini", type="primary", key=f"post_{id_}"):
                tampil_hasil(tr.posting(user, id_), rerun=True)
            if st.toggle("Edit draft", key=f"edit_{id_}"):
                d, draft, post = _form(user, r, f"trx_e{id_}")
                if draft or post:
                    ok, p, _ = tr.simpan_draft(user, d, id_)
                    if ok and post:
                        ok, p = tr.posting(user, id_)
                    tampil_hasil((ok, p), rerun=True)
        if tr.boleh_hapus(user, r):
            with st.expander("Hapus transaksi"):
                if r["status"] == "Draft":
                    st.caption("Draft dihapus permanen, dan penghapusan tetap dicatat di audit trail.")
                    alasan = ""
                else:
                    st.caption("Transaksi yang sudah diposting dibatalkan: jurnal pembalik dibuat otomatis dan data asli tetap terlihat dengan label dibatalkan.")
                    alasan = st.text_input("Alasan (wajib)", key=f"alasan_{id_}")
                ya = st.checkbox("Saya yakin ingin menghapus transaksi ini", key=f"yakin_{id_}")
                if st.button("Hapus", key=f"hapus_{id_}", disabled=not ya):
                    tampil_hasil(tr.hapus(user, id_, alasan), rerun=True)


def render(user: dict):
    st.title("Transaksi")
    munculkan_pesan()
    t1, t2 = st.tabs(["Daftar transaksi", "Input transaksi"])
    with t1:
        a, b, c = st.columns([1, 2, 2])
        status = a.selectbox("Status", ["Semua", "Draft", "Diposting", "Dibatalkan"], key="trx_status")
        cari = b.text_input("Cari nomor atau keterangan", key="trx_cari")
        rentang = c.date_input("Rentang tanggal", value=(hari_ini().replace(day=1) - timedelta(days=60), hari_ini()), key="trx_rentang", format="DD/MM/YYYY")
        mulai, akhir = (rentang if isinstance(rentang, tuple) and len(rentang) == 2 else (None, None))
        rows = tr.daftar(user, None if status == "Semua" else status, cari, mulai.isoformat() if mulai else None, akhir.isoformat() if akhir else None)
        if not owner(user):
            st.caption("Anda hanya melihat transaksi yang Anda buat sendiri.")
        df = pd.DataFrame([{"Nomor": r["no"], "Tanggal": tgl(r["tanggal"]), "Jenis": tr.SPEC[r["jenis"]]["label"], "Pihak": r["pihak"] or "-",
                            "Keterangan": r["keterangan"], "Nominal": rupiah(r["total"]), "Status": r["status"], "Pembuat": r["pembuat"]} for r in rows])
        idx = tabel(df, key="tb_trx", pilih=True)
        pilih_id = rows[idx]["id"] if idx is not None else st.session_state.pop("trx_pilih", None)
        if pilih_id:
            _detail(user, pilih_id)
    with t2:
        _input_baru(user)

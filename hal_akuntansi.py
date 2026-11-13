"""hal_akuntansi.py - Modul Akuntansi (Modul bab 9, khusus Owner). Tiap fungsi memeriksa jabatan lagi di backend."""

from datetime import date

import pandas as pd
import streamlit as st

import akuntansi as ak
import ekspor
from database import hari_ini, owner, semua
from tampilan import (angka, label_bulan, munculkan_pesan, rupiah, status_badge, tabel, tampil_hasil, tgl)

MENU = ["Jurnal Umum", "Buku Besar", "Neraca Saldo", "Penyesuaian", "Neraca Lajur", "Laporan Keuangan", "Penutupan"]


def _bulan_pilihan(key: str, hanya_terbuka: bool = False):
    p = [x for x in ak.daftar_periode() if x["bulan"] <= hari_ini().strftime("%Y-%m") and (not hanya_terbuka or x["status"] == "Terbuka")]
    if not p:
        st.info("Belum ada periode.")
        return None
    return st.selectbox("Periode", [x["bulan"] for x in p], format_func=label_bulan, key=key)


def _akun_opsi():
    return [f'{a["kode"]} - {a["nama"]}' for a in semua("SELECT kode, nama FROM accounts WHERE status='Aktif' ORDER BY kode")]


# ------------------------------------------------------------------ Jurnal Umum
def jurnal_umum(user):
    st.subheader("Jurnal Umum")
    st.caption("Jurnal otomatis dari transaksi, jurnal manual, penyesuaian, penutup, dan pembalik.")
    munculkan_pesan()
    a, b, c = st.columns([2, 2, 2])
    r = a.date_input("Rentang tanggal", value=(hari_ini().replace(day=1), hari_ini()), key="ju_r", format="DD/MM/YYYY")
    jenis = b.multiselect("Jenis jurnal", ["otomatis", "manual", "penyesuaian", "penutup", "pembalik"], key="ju_j")
    cari = c.text_input("Cari", key="ju_c")
    if not (isinstance(r, tuple) and len(r) == 2):
        return
    rows = ak.daftar_jurnal(r[0], r[1], tuple(jenis) or None, cari)
    df = pd.DataFrame([{"No. jurnal": x["no_jurnal"], "Tanggal": tgl(x["tanggal"]), "Jenis": x["jenis"], "Keterangan": x["keterangan"],
                        "Transaksi": x["no_transaksi"] or "-", "Debit": rupiah(x["debit"]), "Kredit": rupiah(x["kredit"])} for x in rows])
    idx = tabel(df, key="tb_ju", pilih=True)
    st.caption(f'Total debit {rupiah(sum(x["debit"] for x in rows))} | Total kredit {rupiah(sum(x["kredit"] for x in rows))}')
    if idx is not None:
        j = rows[idx]
        st.markdown(f'**{j["no_jurnal"]}** - {j["keterangan"]}')
        tabel(pd.DataFrame([{"Akun": f'{x["kode_akun"]} {x["akun"]}', "Debit": rupiah(x["debit"]) if x["debit"] else "", "Kredit": rupiah(x["kredit"]) if x["kredit"] else ""}
                            for x in ak.baris_jurnal(j["id"])]))
        if j["jenis"] in ("manual", "penyesuaian") and not j["no_transaksi"]:
            alasan = st.text_input("Alasan pembatalan jurnal", key=f'jb_{j["id"]}')
            if st.button("Batalkan jurnal ini", key=f'jbb_{j["id"]}'):
                tampil_hasil(ak.batalkan_jurnal(user, j["id"], alasan), rerun=True)
            st.caption("Jurnal tidak dihapus: dibatalkan dengan jurnal pembalik sehingga jejaknya tetap ada.")
    with st.expander("Buat jurnal manual"):
        t = st.date_input("Tanggal jurnal", value=hari_ini(), key="jm_t", format="DD/MM/YYYY")
        ket = st.text_input("Keterangan *", key="jm_k")
        akun = _akun_opsi()
        df = pd.DataFrame({"Akun": pd.Series([None, None], dtype="object"), "Debit": [0.0, 0.0], "Kredit": [0.0, 0.0]})
        ed = st.data_editor(df, num_rows="dynamic", hide_index=True, key="jm_ed",
                            column_config={"Akun": st.column_config.SelectboxColumn(options=akun, required=True),
                                           "Debit": st.column_config.NumberColumn(min_value=0, format="%.0f"),
                                           "Kredit": st.column_config.NumberColumn(min_value=0, format="%.0f")})
        td, tk = float(ed["Debit"].fillna(0).sum()), float(ed["Kredit"].fillna(0).sum())
        st.caption(f"Total debit {rupiah(td)} | Total kredit {rupiah(tk)} | Selisih {rupiah(td - tk)}")
        if st.button("Simpan jurnal manual", type="primary", key="jm_s"):
            baris = [(str(x["Akun"]).split(" - ")[0], x["Debit"], x["Kredit"]) for _, x in ed.iterrows() if x["Akun"]]
            tampil_hasil(ak.jurnal_manual(user, t, ket, baris), rerun=True)


# ------------------------------------------------------------------ Buku Besar
def buku_besar(user):
    st.subheader("Buku Besar")
    r = st.date_input("Rentang tanggal", value=(hari_ini().replace(day=1), hari_ini()), key="bb_r", format="DD/MM/YYYY")
    if not (isinstance(r, tuple) and len(r) == 2):
        return
    rows = ak.buku_besar(r[0], r[1])
    df = pd.DataFrame([{"Kode": x["kode"], "Akun": x["nama"], "Saldo awal": rupiah(x["awal"]), "Debit": rupiah(x["debit"]), "Kredit": rupiah(x["kredit"]),
                        "Saldo akhir": rupiah(x["akhir"])} for x in rows])
    idx = tabel(df, key="tb_bb", pilih=True)
    if idx is not None:
        d = ak.rincian_akun(rows[idx]["kode"], r[0], r[1])
        st.markdown(f'**{d["kode"]} - {d["nama"]}** (saldo awal {rupiah(d["awal"])})')
        tabel(pd.DataFrame([{"Tanggal": tgl(b["tanggal"]), "No. jurnal": b["no_jurnal"], "Keterangan": b["keterangan"], "Debit": rupiah(b["debit"]) if b["debit"] else "",
                             "Kredit": rupiah(b["kredit"]) if b["kredit"] else "", "Saldo": rupiah(b["saldo"])} for b in d["baris"]]))
    else:
        st.caption("Pilih sebuah akun untuk melihat mutasi dengan saldo berjalan.")


# ------------------------------------------------------------------ Neraca Saldo
MODE_LABEL = {"sebelum_penyesuaian": "Sebelum penyesuaian", "setelah_penyesuaian": "Setelah penyesuaian",
              "semua": "Setelah penutupan (semua jurnal)"}


def neraca_saldo(user):
    st.subheader("Neraca Saldo")
    a, b = st.columns(2)
    sampai = a.date_input("Sampai tanggal", value=hari_ini(), key="ns_t", format="DD/MM/YYYY")
    mode = b.selectbox("Tampilan", list(MODE_LABEL), format_func=MODE_LABEL.get, key="ns_m")
    rows, td, tk = ak.neraca_saldo(sampai, mode)
    tabel(pd.DataFrame([{"Kode": x["kode"], "Akun": x["nama"], "Debit": rupiah(x["debit"]) if x["debit"] else "", "Kredit": rupiah(x["kredit"]) if x["kredit"] else ""} for x in rows]))
    c1, c2 = st.columns(2)
    c1.metric("Total debit", rupiah(td))
    c2.metric("Total kredit", rupiah(tk))
    (st.success if abs(td - tk) <= 0.005 else st.error)("Neraca saldo seimbang." if abs(td - tk) <= 0.005 else f"Tidak seimbang, selisih {rupiah(td - tk)}.")
    if mode == "semua":
        st.caption("Setelah penutupan tahun, hanya akun neraca yang bersaldo.")


# ------------------------------------------------------------------ Penyesuaian
def penyesuaian(user):
    st.subheader("Jurnal Penyesuaian")
    st.caption("Persediaan akhir dari stok opname final, penyusutan, perlengkapan, biaya dibayar di muka, dan utang gaji. Setiap jurnal wajib punya keterangan dan tercatat di audit trail.")
    munculkan_pesan()
    bulan = _bulan_pilihan("pen_bulan", hanya_terbuka=True)
    if not bulan:
        return
    t1, t2, t3, t4, t5 = st.tabs(["Persediaan akhir", "Penyusutan", "Perlengkapan", "Biaya dibayar di muka", "Utang gaji"])
    with t1:
        nilai = ak.nilai_stok_final(bulan)
        st.caption("Nilai persediaan akhir diambil dari stok opname yang sudah final (Informasi Usaha > Stok Opname).")
        nm = {r["kode"]: r["nama"] for r in semua("SELECT kode, nama FROM accounts")}
        tabel(pd.DataFrame([{"Akun": f"{k} {nm.get(k, '')}", "Persediaan akhir (stok opname)": rupiah(v)} for k, v in sorted(nilai.items())]))
        if st.button("Buat jurnal persediaan akhir", type="primary", key="pen_p"):
            tampil_hasil(ak.jurnal_persediaan(user, bulan), rerun=True)
        st.caption("Jurnal: hapus persediaan awal (Dr Ikhtisar Laba Rugi, Cr Persediaan), lalu catat persediaan akhir (Dr Persediaan, Cr Ikhtisar Laba Rugi).")
    with t2:
        aset = semua("SELECT * FROM fixed_assets WHERE status='Aktif' ORDER BY kode")
        baris = []
        for a in aset:
            m = ak.penyusutan_bulanan(a)
            baris.append({"Aset": a["nama"], "Penyusutan per bulan": rupiah(m) if m is not None else "Belum dikonfirmasi (dilewati)"})
        tabel(pd.DataFrame(baris))
        if st.button("Buat jurnal penyusutan", type="primary", key="pen_s"):
            tampil_hasil(ak.jurnal_penyusutan(user, bulan), rerun=True)
    with t3:
        j = st.number_input("Perlengkapan yang terpakai (Rp)", min_value=0.0, step=1000.0, value=None, key="pen_pl_j")
        k = st.text_input("Keterangan *", key="pen_pl_k")
        if st.button("Simpan jurnal perlengkapan", key="pen_pl"):
            tampil_hasil(ak.jurnal_penyesuaian_lain(user, bulan, "perlengkapan", j or 0, k), rerun=True)
    with t4:
        beban = [f'{a["kode"]} - {a["nama"]}' for a in semua("SELECT kode, nama FROM accounts WHERE status='Aktif' AND kelompok='Beban operasional' ORDER BY kode")]
        akun = st.selectbox("Akun beban", beban, key="pen_dm_a")
        j = st.number_input("Biaya dibayar di muka yang sudah terpakai (Rp)", min_value=0.0, step=1000.0, value=None, key="pen_dm_j")
        k = st.text_input("Keterangan *", key="pen_dm_k")
        if st.button("Simpan jurnal biaya dibayar di muka", key="pen_dm"):
            tampil_hasil(ak.jurnal_penyesuaian_lain(user, bulan, "muka", j or 0, k, akun.split(" - ")[0]), rerun=True)
    with t5:
        st.caption("Gaji dibayar mingguan, jadi akhir bulan bisa jatuh di tengah minggu. Isi hari kerja yang belum dibayar per karyawan.")
        emp = semua("SELECT id, kode, nama, tarif_harian FROM employees WHERE status='Aktif' ORDER BY kode")
        total = 0.0
        for e in emp:
            h = st.number_input(f'{e["kode"]} - {e["nama"]} (hari belum dibayar)', min_value=0.0, step=1.0, value=0.0, key=f'pen_ug_{e["id"]}')
            total += h * e["tarif_harian"]
        st.info(f"Utang gaji: {rupiah(total)}")
        k = st.text_input("Keterangan *", key="pen_ug_k")
        if st.button("Simpan jurnal utang gaji", key="pen_ug"):
            tampil_hasil(ak.jurnal_penyesuaian_lain(user, bulan, "utang_gaji", total, k), rerun=True)


# ------------------------------------------------------------------ Neraca Lajur
def neraca_lajur(user):
    st.subheader("Neraca Lajur")
    st.caption("Kertas kerja akhir periode yang merangkum neraca saldo, penyesuaian, neraca saldo setelah penyesuaian, laba rugi, dan neraca.")
    sampai = st.date_input("Sampai tanggal", value=hari_ini(), key="nl_t", format="DD/MM/YYYY")
    d = ak.neraca_lajur(sampai)

    def f(v):
        return rupiah(v) if v else ""
    baris = [{"Kode": x["kode"], "Akun": x["nama"], "NS Debit": f(x["ns"][0]), "NS Kredit": f(x["ns"][1]), "Penyesuaian Dr": f(x["adj"][0]),
              "Penyesuaian Kr": f(x["adj"][1]), "NSS Debit": f(x["nss"][0]), "NSS Kredit": f(x["nss"][1]), "L/R Debit": f(x["lr"][0]),
              "L/R Kredit": f(x["lr"][1]), "Neraca Debit": f(x["nr"][0]), "Neraca Kredit": f(x["nr"][1])} for x in d["baris"]]
    t = d["total"]
    baris.append({"Kode": "", "Akun": "TOTAL", "NS Debit": f(t["ns"][0]), "NS Kredit": f(t["ns"][1]), "Penyesuaian Dr": f(t["adj"][0]), "Penyesuaian Kr": f(t["adj"][1]),
                  "NSS Debit": f(t["nss"][0]), "NSS Kredit": f(t["nss"][1]), "L/R Debit": f(t["lr"][0]), "L/R Kredit": f(t["lr"][1]),
                  "Neraca Debit": f(t["nr"][0]), "Neraca Kredit": f(t["nr"][1])})
    tabel(pd.DataFrame(baris))
    st.metric("Laba (rugi) bersih menurut kolom laba rugi", rupiah(d["laba"]))
    (st.success if d["seimbang"] else st.error)("Neraca saldo dan neraca saldo setelah penyesuaian seimbang." if d["seimbang"] else "Ada ketidakseimbangan, periksa jurnal.")


# ------------------------------------------------------------------ Laporan Keuangan
def _df(baris: list) -> pd.DataFrame:
    """baris = [(keterangan, nilai | None)] -> tabel dua kolom."""
    return pd.DataFrame([{"Keterangan": k, "Jumlah": ("" if v is None else rupiah(v))} for k, v in baris])


def _bagian_laba_rugi(lr):
    b = [("PENJUALAN", None)]
    b += [(f'  {x["nama"]}', x["nilai"]) for x in lr["pendapatan"]]
    b += [(f'  Dikurangi: {x["nama"]}', -x["nilai"]) for x in lr["kontra"]]
    b += [("Penjualan bersih", lr["penjualan_bersih"]), ("HARGA POKOK PENJUALAN", None), ("  Persediaan awal ikan", lr["awal_ikan"]),
          ("  Biaya produksi (pemakaian bahan budidaya)", lr["biaya_produksi"]), ("  Dikurangi: persediaan akhir ikan", -lr["akhir_ikan"]),
          ("Harga pokok penjualan", lr["hpp"]), ("LABA KOTOR", lr["laba_kotor"]), ("BEBAN OPERASIONAL", None)]
    b += [(f'  {x["nama"]}', x["nilai"]) for x in lr["beban"]]
    b += [("Total beban operasional", lr["total_beban"])]
    if lr["lain"]:
        b += [("PENDAPATAN DAN BEBAN LAIN", None)] + [(f'  {x["nama"]}', x["nilai"]) for x in lr["lain"]]
    b += [("LABA (RUGI) BERSIH", lr["laba"])]
    return b


def _bagian_hpp(lr):
    return [("Persediaan awal bahan budidaya", lr["awal_bahan"]), ("Pembelian bersih (pembelian + ongkos angkut - retur - potongan)", lr["pembelian_bersih"]),
            ("Persediaan akhir bahan budidaya (stok opname)", -lr["akhir_bahan"]), ("Pemakaian bahan budidaya", lr["pemakaian_bahan"]),
            ("Upah produksi (bila dialokasikan)", lr["upah_produksi"]), ("Biaya produksi", lr["biaya_produksi"]),
            ("Persediaan ikan awal", lr["awal_ikan"]), ("Persediaan ikan akhir", -lr["akhir_ikan"]), ("Harga pokok penjualan", lr["hpp"])]


def _bagian_neraca(n):
    b = [("ASET LANCAR", None)] + [(f'  {x["nama"]}', x["nilai"]) for x in n["lancar"]]
    b += [("ASET TETAP", None)] + [(f'  {x["nama"]}', x["nilai"]) for x in n["tetap"] + n["kontra"]] + [("Aset tetap (neto)", n["aset_neto_tetap"])]
    b += [("TOTAL ASET", n["total_aset"]), ("LIABILITAS", None)] + [(f'  {x["nama"]}', x["nilai"]) for x in n["liab"]] + [("Total liabilitas", n["total_liab"])]
    b += [("EKUITAS", None), ("  Modal pemilik", n["modal"]), ("  Prive", -n["prive"]), ("  Laba (rugi) berjalan", n["laba_berjalan"]), ("Total ekuitas", n["ekuitas"]),
          ("TOTAL LIABILITAS + EKUITAS", n["total_liab"] + n["ekuitas"])]
    return b


def laporan(user):
    st.subheader("Laporan Keuangan")
    st.caption("Laporan hanya memakai transaksi berstatus diposting (lewat jurnal). Laba bersih di laba rugi sama dengan yang masuk ke perubahan ekuitas dan neraca.")
    r = st.date_input("Periode laporan", value=(hari_ini().replace(day=1), hari_ini()), key="lap_r", format="DD/MM/YYYY")
    if not (isinstance(r, tuple) and len(r) == 2):
        return
    mulai, akhir = r
    lr, pe, nr, ck = ak.laba_rugi(mulai, akhir), ak.perubahan_ekuitas(mulai, akhir), ak.neraca(akhir), ak.arus_kas(mulai, akhir)
    sub = f"Periode {tgl(mulai)} sampai {tgl(akhir)}"
    t1, t2, t3, t4, t5 = st.tabs(["Laba Rugi", "Perubahan Ekuitas", "Neraca", "Arus Kas", "Rincian Harga Pokok"])
    bagian = {}
    with t1:
        df = _df(_bagian_laba_rugi(lr))
        tabel(df)
        bagian["Laba Rugi"] = df
        st.caption("Bila jurnal penyesuaian persediaan akhir belum dibuat, pembelian dihitung penuh sebagai biaya.")
    with t2:
        df = _df([("Modal awal", pe["awal"]), ("Ditambah: laba bersih", pe["laba"]), ("Ditambah: tambahan modal", pe["tambahan"]),
                  ("Dikurangi: prive", -pe["prive"]), ("Modal akhir", pe["akhir"])])
        tabel(df)
        bagian["Perubahan Ekuitas"] = df
        (st.success if pe["sama"] else st.error)("Modal akhir sama dengan ekuitas di neraca." if pe["sama"] else f'Selisih dengan neraca: {rupiah(pe["akhir"] - pe["akhir_neraca"])}')
    with t3:
        df = _df(_bagian_neraca(nr))
        st.caption(f"Neraca per {tgl(akhir)}")
        tabel(df)
        bagian["Neraca"] = df
        (st.success if nr["seimbang"] else st.error)("Total aset sama dengan liabilitas + ekuitas." if nr["seimbang"] else f'Tidak seimbang, selisih {rupiah(nr["selisih"])}')
    with t4:
        rg = ck["ringkas"]
        df = _df([("Saldo kas dan bank awal", ck["awal"]), ("Kegiatan operasi: kas masuk", rg["Operasi"]["masuk"]), ("Kegiatan operasi: kas keluar", -rg["Operasi"]["keluar"]),
                  ("Arus kas bersih operasi", rg["Operasi"]["bersih"]), ("Kegiatan investasi: bersih", rg["Investasi"]["bersih"]),
                  ("Kegiatan pendanaan: bersih", rg["Pendanaan"]["bersih"]), ("Kenaikan (penurunan) kas", ck["perubahan"]), ("Saldo kas dan bank akhir", ck["akhir"])])
        tabel(df)
        bagian["Arus Kas"] = df
        (st.success if ck["sama"] else st.error)("Saldo akhir sama dengan akun Kas dan Bank." if ck["sama"] else f'Berbeda dari akun Kas dan Bank ({rupiah(ck["akhir_buku"])}).')
    with t5:
        df = _df(_bagian_hpp(lr))
        tabel(df)
        bagian["Rincian HPP"] = df
        st.caption("Pemakaian bahan = persediaan awal + pembelian bersih - persediaan akhir. HPP = persediaan ikan awal + biaya produksi - persediaan ikan akhir.")
    st.markdown("**Ekspor laporan**")
    a, b = st.columns(2)
    a.download_button("Unduh Excel", ekspor.ke_excel("Laporan Keuangan", bagian), file_name=f"laporan_{mulai}_{akhir}.xlsx",
                      mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="dl_xlsx")
    b.download_button("Unduh PDF", ekspor.ke_pdf("Milkfish Ledger - Laporan Keuangan", sub, bagian), file_name=f"laporan_{mulai}_{akhir}.pdf",
                      mime="application/pdf", key="dl_pdf")


# ------------------------------------------------------------------ Penutupan
def penutupan(user):
    st.subheader("Penutupan")
    munculkan_pesan()
    t1, t2 = st.tabs(["Penutupan bulanan", "Akhir tahun buku"])
    with t1:
        st.caption("Tiap bulan: stok opname final, jurnal penyesuaian lengkap, neraca saldo seimbang, lalu periode dikunci.")
        bulan = _bulan_pilihan("tp_bulan", hanya_terbuka=True)
        if bulan:
            for teks, ok in ak.cek_penutupan(bulan):
                (st.success if ok else st.error)(teks)
            if st.button("Tutup Periode", type="primary", key="tp_tutup"):
                tampil_hasil(ak.tutup_periode(user, bulan), rerun=True)
        tabel(pd.DataFrame([{"Periode": label_bulan(p["bulan"]), "Status": p["status"], "Ditutup oleh": p["penutup"] or "-", "Waktu": p["tgl_tutup"] or "-"} for p in ak.daftar_periode()]))
    with t2:
        st.caption("Pada akhir tahun buku: pendapatan, pembelian, dan beban dipindah ke Ikhtisar Laba Rugi, lalu ke Modal Pemilik. Prive ditutup ke Modal Pemilik.")
        tahun = st.selectbox("Tahun buku", [hari_ini().year - 1, hari_ini().year], index=0, key="tp_tahun")
        awal, akhir = ak.rentang_tahun_buku(tahun)
        st.write(f"Tahun buku {tahun}: {tgl(awal)} sampai {tgl(akhir)}")
        if st.button("Buat jurnal penutup", type="primary", key="tp_tahun_b"):
            tampil_hasil(ak.tutup_tahun(user, tahun), rerun=True)
        st.markdown("**Jurnal pembalik (opsional)**")
        st.caption("Untuk membalik penyesuaian akrual (utang gaji) di awal periode baru.")
        kand = ak.kandidat_pembalik(tahun)
        if not kand:
            st.info("Tidak ada jurnal akrual yang perlu dibalik.")
        for k in kand:
            c1, c2 = st.columns([4, 1])
            c1.write(f'{k["no_jurnal"]} - {k["keterangan"]}')
            if c2.button("Balik", key=f'tp_balik_{k["id"]}'):
                tampil_hasil(ak.jurnal_pembalik(user, k["id"]), rerun=True)
        st.caption("Neraca saldo setelah penutupan: buka Akuntansi > Neraca Saldo, pilih tampilan 'Setelah penutupan'.")


HALAMAN = {"Jurnal Umum": jurnal_umum, "Buku Besar": buku_besar, "Neraca Saldo": neraca_saldo, "Penyesuaian": penyesuaian,
           "Neraca Lajur": neraca_lajur, "Laporan Keuangan": laporan, "Penutupan": penutupan}


def render(user: dict, menu: str):
    if not owner(user):   # pemeriksaan backend, bukan hanya menu yang disembunyikan
        st.error("Anda tidak memiliki akses.")
        return
    HALAMAN[menu](user)

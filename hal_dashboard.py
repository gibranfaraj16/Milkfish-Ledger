"""hal_dashboard.py - Dashboard Owner (lengkap) dan Karyawan (terbatas). Hanya membaca data dari modul sumber."""

import pandas as pd
import streamlit as st

import dashboard as dd
import transaksi as tr
from database import hari_ini, owner
from tampilan import BIRU, KUNING, angka, donat, kartu, label_bulan, rupiah, status_badge, tabel, tgl


def _ke(menu: str):
    st.session_state["menu"] = menu


def render(user: dict):
    if owner(user):
        _owner(user)
    else:
        _karyawan(user)


def _akses_cepat(user: dict):
    st.markdown("**Akses cepat**")
    kol = st.columns(4)
    for k, (label, jenis) in zip(kol, [("Input penjualan", "penjualan_tunai"), ("Input pembelian", "pembelian_tunai"),
                                       ("Input biaya", "biaya_operasional"), ("Input penerimaan", "penerimaan_piutang")]):
        if jenis in tr.jenis_boleh(user):
            if k.button(label, key=f"cepat_{jenis}"):
                st.session_state["trx_jenis_awal"] = jenis
                _ke("Transaksi")
                st.rerun()


def _terbaru(user: dict):
    st.markdown("**Transaksi terbaru**")
    rows = dd.transaksi_terbaru(user)
    df = pd.DataFrame([{"Tanggal": tgl(r["tanggal"]), "Nomor": r["no"], "Jenis": tr.SPEC[r["jenis"]]["label"], "Nominal": rupiah(r["total"]),
                        "Status": r["status"], "Pembuat": r["pembuat"]} for r in rows])
    idx = tabel(df, key="dash_terbaru", pilih=True)
    if idx is not None:
        st.session_state["trx_pilih"] = rows[idx]["id"]
        _ke("Transaksi")
        st.rerun()
    st.caption("Klik sebuah baris untuk membuka detail transaksi.")


def _owner(user: dict):
    st.title(f"Selamat datang, {user['nama']}")
    st.caption("Ringkasan usaha. Semua angka dibaca dari jurnal yang sama dengan laporan keuangan.")
    c1, c2 = st.columns([1, 2])
    pilih = c1.selectbox("Filter periode", dd.FILTER, index=2, key="dash_filter")
    khusus = None
    if pilih == "Rentang khusus":
        khusus = c2.date_input("Rentang", value=(hari_ini().replace(day=1), hari_ini()), key="dash_khusus", format="DD/MM/YYYY")
    mulai, akhir = dd.rentang(pilih, khusus)
    try:
        d = dd.ringkasan_owner(mulai, akhir)
        peringatan = dd.peringatan_owner()
    except Exception as e:   # data gagal dimuat: tampilkan kesalahan, bukan angka nol
        st.error(f"Data dashboard gagal dimuat: {e}")
        return
    st.caption(f"Periode: {tgl(mulai)} sampai {tgl(akhir)}")

    baris1 = st.columns(4)
    with baris1[0]:
        kartu("Total Karyawan", str(d["karyawan"]))
    with baris1[1]:
        kartu("Total Supplier", str(d["supplier"]))
    with baris1[2]:
        kartu("Total Aset", rupiah(d["aset"]))
    with baris1[3]:
        kartu("Total Liabilitas", rupiah(d["liabilitas"]))
    baris2 = st.columns(3)
    with baris2[0]:
        kartu("Kas dan Bank", rupiah(d["kas_bank"]))
    with baris2[1]:
        kartu("Penjualan periode", rupiah(d["penjualan"]))
    with baris2[2]:
        kartu("Pembelian periode", rupiah(d["pembelian"]))
    baris3 = st.columns(3)
    with baris3[0]:
        kartu("Piutang", rupiah(d["piutang"]))
    with baris3[1]:
        kartu("Utang", rupiah(d["utang"]))
    with baris3[2]:
        kartu("Laba Bersih", rupiah(d["laba"]), None if d["sudah_disesuaikan"] else "Belum ada jurnal penyesuaian persediaan pada periode ini, jadi pembelian dihitung penuh sebagai biaya.")

    g1, g2 = st.columns([3, 2])
    with g1:
        with st.container(border=True):
            st.markdown("**Total Transaksi**")
            skala = st.radio("Per", ["Hari", "Minggu", "Bulan"], horizontal=True, key="dash_skala")
            seri = dd.seri_transaksi(mulai, akhir, skala)
            if seri.empty:
                st.info("Belum ada data.")
            else:
                st.bar_chart(seri[["Jumlah"]], color=BIRU)
    with g2:
        with st.container(border=True):
            st.markdown("**Komposisi Total Aset**")
            donat(d["donat"])

    with st.container(border=True):
        st.markdown("**Peringatan**")
        if not peringatan:
            st.success("Tidak ada peringatan.")
        for p in peringatan:
            st.warning(p)
    _akses_cepat(user)
    _terbaru(user)


def _karyawan(user: dict):
    st.title(f"Halo, {user['nama']}")
    st.caption("Ringkasan kerja Anda hari ini. Laba, kas, utang, piutang, dan total aset tidak ditampilkan untuk Karyawan.")
    try:
        d = dd.ringkasan_karyawan(user)
    except Exception as e:
        st.error(f"Data dashboard gagal dimuat: {e}")
        return
    a, b = st.columns(2)
    with a:
        kartu("Transaksi saya hari ini", str(len(d["hari_ini"])))
    with b:
        kartu("Draft yang belum selesai", str(len(d["draft"])))
    _akses_cepat(user)
    k1, k2 = st.columns(2)
    with k1:
        with st.container(border=True):
            st.markdown("**Draft saya**")
            tabel(pd.DataFrame([{"Nomor": r["no"], "Tanggal": tgl(r["tanggal"]), "Jenis": tr.SPEC[r["jenis"]]["label"]} for r in d["draft"]]))
        with st.container(border=True):
            st.markdown("**Jadwal pengiriman**")
            tabel(pd.DataFrame([{"Surat jalan": r["no_surat_jalan"], "Tanggal": tgl(r["tanggal"]), "Customer": r["customer"] or "-", "Status": r["status"]} for r in d["pengiriman"]]))
    with k2:
        with st.container(border=True):
            st.markdown("**Stok pakan dan benih** (estimasi, lihat saja)")
            tabel(pd.DataFrame([{"Item": r["item"], "Estimasi": f'{angka(r["estimasi"], 0)} {r["satuan"]}', "Minimum": angka(r["minimum"])} for r in d["stok"]]))
    _terbaru(user)

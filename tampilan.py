from datetime import date, datetime
from typing import Literal

import altair as alt
import pandas as pd
import streamlit as st

import master

BadgeColor = Literal["red", "orange", "yellow", "blue", "green", "violet", "gray", "grey", "primary"]

BIRU, KUNING, BIRU_MUDA, ABU = "#025A95", "#FEE307", "#7FB2D9", "#B8C4CE"
PALET = [BIRU, KUNING, BIRU_MUDA, ABU]
BULAN = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"]
BULAN_PENDEK = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]

WARNA_STATUS: dict[str, BadgeColor] = {"Draft": "gray", "Diposting": "green", "Dibatalkan": "red", "Aktif": "green", "Nonaktif": "gray",
                "Final": "green", "Terbuka": "green", "Tertutup": "red", "Berhasil": "green", "Gagal": "red", "Ditolak": "red",
                "Disiapkan": "blue", "Dikirim": "yellow", "Diterima": "green", "Budidaya": "green", "Panen": "yellow",
                "Persiapan": "blue", "Kosong": "gray", "Berjalan": "green", "Selesai": "gray"}


def rupiah(n) -> str:
    if n is None:
        return "-"
    v = int(round(n))
    return ("-" if v < 0 else "") + "Rp " + f"{abs(v):,}".replace(",", ".")


def angka(n, desimal: int = 0) -> str:
    if n is None:
        return "-"
    return f"{n:,.{desimal}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def tgl(s) -> str:
    if not s:
        return "-"
    if isinstance(s, (date, datetime)):
        s = s.isoformat()[:10]
    y, m, d = s[:10].split("-")
    return f"{int(d):02d} {BULAN_PENDEK[int(m) - 1]} {y}"


def label_bulan(bulan: str) -> str:
    y, m = bulan.split("-")
    return f"{BULAN[int(m) - 1]} {y}"


def status_badge(status: str):
    st.badge(status, color=WARNA_STATUS.get(status, "gray"))

 
def pesan(ok: bool, teks: str):
    (st.success if ok else st.error)(teks)


def tampil_hasil(hasil, rerun: bool = False):
    """hasil = (ok, pesan[, ...]). Simpan pesan agar tetap tampil setelah halaman disegarkan."""
    st.session_state["_pesan"] = (bool(hasil[0]), hasil[1])
    if rerun:
        st.rerun()


def munculkan_pesan():
    p = st.session_state.pop("_pesan", None)
    if p:
        pesan(*p)


def tabel(df: pd.DataFrame, key: str | None = None, pilih: bool = False, tinggi: int | None = None):
    """Tampilkan tabel. Bila pilih=True kembalikan indeks baris yang dipilih (atau None)."""
    if df is None or df.empty:
        st.info("Belum ada data.")
        return None
    kw = dict(hide_index=True)
    if tinggi:
        kw["height"] = tinggi
    if pilih:
        kw.update(on_select="rerun", selection_mode="single-row", key=key)
    try:
        ev = st.dataframe(df, width="stretch", **kw)
    except Exception:
        ev = st.dataframe(df, use_container_width=True, **kw)
    if pilih and ev is not None and ev.selection.rows:
        return ev.selection.rows[0]
    return None


def kartu(judul: str, nilai: str, ket: str | None = None):
    with st.container(border=True):
        st.metric(judul, nilai)
        if ket:
            st.caption(ket)


def donat(data: dict, judul: str = ""):
    """Grafik donat komposisi (Altair, ditulis dengan Python)."""
    df = pd.DataFrame({"Komponen": list(data), "Nilai": [max(v, 0) for v in data.values()]})
    if df["Nilai"].sum() <= 0:
        st.info("Belum ada data.")
        return
    g = alt.Chart(df).mark_arc(innerRadius=60).encode(
        theta="Nilai:Q", color=alt.Color("Komponen:N", scale=alt.Scale(domain=list(data), range=PALET[:len(data)]), legend=alt.Legend(orient="bottom", title=None)),
        tooltip=["Komponen", alt.Tooltip("Nilai:Q", format=",.0f")])
    st.altair_chart(g)


def pilih_rentang_bulan(key: str):
    """Dua tanggal (mulai, akhir) lewat input tanggal."""
    h = date.today()
    r = st.date_input("Rentang tanggal", value=(h.replace(day=1), h), key=key, format="DD/MM/YYYY")
    if isinstance(r, tuple) and len(r) == 2:
        return r
    return None


# ------------------------------------------------------------------ formulir dari definisi master
def _opsi_pilihan(m: dict, wajib: bool):
    o = master.opsi_dari(m)
    if not wajib and not any(v is None for v, _ in o):
        o = [(None, "-")] + o
    return o


def isian(m: dict, awal, kunci: str):
    """Satu isian formulir menurut definisi master. Kembalikan nilainya."""
    tipe, label = m["tipe"], m["label"] + (" *" if m["wajib"] else "")
    bantu = m["bantuan"] or None
    if awal is None and m["default"] is not None:
        awal = date.today() if m["default"] == "hari_ini" else m["default"]
    if tipe in ("teks", "kode"):
        return st.text_input(label, value=awal or "", key=kunci, help=bantu)
    if tipe == "area":
        return st.text_area(label, value=awal or "", key=kunci, help=bantu)
    if tipe in ("angka", "uang"):
        langkah = 1000.0 if tipe == "uang" else 1.0
        return st.number_input(label, value=None if awal is None else float(awal), min_value=0.0, step=langkah,
                               key=kunci, help=bantu)
    if tipe == "tanggal":
        v = awal
        if isinstance(v, str) and v:
            v = date.fromisoformat(v[:10])
        return st.date_input(label, value=v or None, key=kunci, format="DD/MM/YYYY", help=bantu)
    if tipe == "pilihan":
        o = _opsi_pilihan(m, m["wajib"])
        nilai = [v for v, _ in o]
        idx = nilai.index(awal) if awal in nilai else 0
        return st.selectbox(label, nilai, index=idx, format_func=dict(o).get, key=kunci, help=bantu)
    return None


def formulir(ent: str, awal: dict | None, kunci: str, sembunyi: set | None = None) -> dict:
    """Tampilkan semua isian entitas. Kembalikan dict nilai. 'sembunyi' = kolom yang tidak boleh tampil."""
    sp = master.ENT[ent]
    out = {}
    kol = st.columns(2)
    medan = [m for m in sp["medan"] if m["k"] not in (sembunyi or set())]
    for i, m in enumerate(medan):
        with kol[i % 2]:
            out[m["k"]] = isian(m, (awal or {}).get(m["k"]), f"{kunci}_{m['k']}")
    return out


def df_entitas(ent: str, rows: list) -> pd.DataFrame:
    """Ubah baris master menjadi tabel dengan judul kolom dan format Rupiah/tanggal."""
    sp = master.ENT[ent]
    label = {m["k"]: m["label"].split(" (")[0] for m in sp["medan"]}
    label.update({"kode": "Kode", "supplier": "Supplier", "petak": "Petak", "item": "Item", "satuan": "Satuan", "customer": "Customer",
                  "penjualan": "Penjualan", "no_surat_jalan": "No. surat jalan", "konfirmasi": "Data aset"})
    tipe = {m["k"]: m["tipe"] for m in sp["medan"]}
    data = []
    for r in rows:
        baris = {}
        for k in sp["kolom"]:
            if k not in r:
                continue
            v = r[k]
            if v is None:
                v = "-"
            elif tipe.get(k) == "uang" or k in ("biaya_angkut", "harga_perolehan"):
                v = rupiah(v)
            elif tipe.get(k) == "angka" or isinstance(v, float):
                v = angka(v, 0 if float(v).is_integer() else 2)
            elif tipe.get(k) == "tanggal" or k.startswith("tgl_") or k == "tanggal":
                v = tgl(v)
            baris[label.get(k, k.replace("_", " ").capitalize())] = v
        data.append(baris)
    return pd.DataFrame(data)


def kunci_form(prefix: str) -> str:
    """Kunci widget yang berganti setelah simpan berhasil, agar formulir kosong kembali."""
    return f"{prefix}_{st.session_state.get(prefix + '_v', 0)}"


def reset_form(prefix: str):
    st.session_state[prefix + "_v"] = st.session_state.get(prefix + "_v", 0) + 1

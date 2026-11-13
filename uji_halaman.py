"""
Uji asap tampilan: menjalankan setiap halaman dengan Streamlit pengganti (stub) untuk menangkap kesalahan Python.
Ini BUKAN pengganti uji di browser dengan Streamlit asli. Jalankan: python uji/uji_halaman.py
"""
import os, sys, types, tempfile, pathlib, runpy, traceback
from datetime import date
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
MODE = {"klik": False, "pilih_baris": False}

WIDGET = {"selectbox","radio","multiselect","text_input","text_area","number_input","date_input","button","form_submit_button","checkbox","toggle","download_button","dataframe","data_editor"}
class Rerun(Exception): pass
class Ctx:
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def __getattr__(self, n):
        if n in WIDGET: return getattr(sys.modules["streamlit"], n)
        return lambda *a, **k: Ctx()
    def __iter__(self): return iter([Ctx(), Ctx(), Ctx(), Ctx()])
class State(dict):
    __getattr__ = dict.get
    def __setattr__(self, k, v): self[k] = v
class Sel: rows = []
class Ev:
    @property
    def selection(self):
        s = Sel(); s.rows = [0] if MODE["pilih_baris"] else []; return s

def kolom(spec, **k):
    n = spec if isinstance(spec, int) else len(spec)
    return [Ctx() for _ in range(n)]

class ColCfg:
    def __getattr__(self, n): return lambda *a, **k: None

def buat_stub():
    st = types.ModuleType("streamlit")
    st.session_state = State()
    st._config = types.SimpleNamespace(set_option=lambda *a: None)
    st.column_config = ColCfg()
    def pilih(label, options=(), index=0, format_func=None, **k):
        o = list(options); 
        if format_func:
            for x in o: format_func(x)
        return o[index] if o and index is not None and index < len(o) else (o[0] if o else None)
    st.selectbox = pilih
    st.radio = lambda label, options, **k: list(options)[0]
    st.multiselect = lambda *a, **k: []
    st.text_input = lambda label, value="", **k: value
    st.text_area = lambda label, value="", **k: value
    st.number_input = lambda label, value=None, **k: value
    st.date_input = lambda label, value=None, **k: value if value is not None else date.today()
    st.button = lambda *a, **k: MODE["klik"] and not k.get("disabled")
    st.form_submit_button = lambda *a, **k: MODE["klik"]
    st.checkbox = lambda *a, **k: MODE["klik"]
    st.toggle = lambda *a, **k: MODE["klik"]
    st.download_button = lambda *a, **k: False
    st.columns = kolom
    st.tabs = lambda t: [Ctx() for _ in t]
    for n in ("container", "expander", "form", "sidebar", "empty", "spinner"):
        setattr(st, n, lambda *a, **k: Ctx())
    st.sidebar = Ctx()
    def rerun(): raise Rerun()
    st.rerun = rerun
    st.dataframe = lambda *a, **k: Ev() if k.get("on_select") else None
    st.data_editor = lambda df, *a, **k: df
    st.set_page_config = lambda **k: None
    st.cache_data = lambda *a, **k: (lambda f: f)
    for n in ("title", "subheader", "header", "markdown", "caption", "write", "info", "warning", "error", "success", "metric", "badge", "divider",
              "bar_chart", "line_chart", "altair_chart", "image", "text", "code", "toast"):
        setattr(st, n, lambda *a, **k: None)
    return st

try:
    import altair
except ImportError:   # altair ikut terpasang bersama Streamlit di komputer pengguna
    alt = types.ModuleType("altair")
    class _A:
        def __getattr__(self, n): return lambda *a, **k: _A()
    alt.__getattr__ = lambda n: (lambda *a, **k: _A())
    sys.modules["altair"] = alt
st = buat_stub()
sys.modules["streamlit"] = st
import database as db
db.DB_PATH = pathlib.Path(tempfile.mkdtemp()) / "halaman.db"
db.init_db()
import master, transaksi as tr, akuntansi as ak, stok
H = db.hari_ini()
OWN = {"id": 1, "nama": "Admin Milkfish", "email": "adminmilkfish@gmail.com", "jabatan": "Owner"}
KAR = {"id": 2, "nama": "Staf Admin Milkfish", "email": "stafadminmilkfish@gmail.com", "jabatan": "Karyawan"}
# data contoh agar tabel terisi
master.simpan(OWN, "item", dict(nama="Pakan", kategori="Pakan", satuan="Kg", stok_minimum=100))
master.simpan(OWN, "item", dict(nama="Bandeng 4/kg", kategori="Ikan hasil panen", satuan="Kg", harga_jual_standar=30000))
master.simpan(OWN, "customer", dict(nama="Pengepul", termin="Kredit"))
master.simpan(OWN, "tambak", dict(nama="Petak 1", luas_m2=10000))
master.simpan(OWN, "siklus", dict(pond_id=1, status="Berjalan"))
master.simpan(OWN, "aset", dict(nama="Pompa", kelompok="Pompa dan mesin"))
master.simpan(OWN, "tarif", dict(nama="Kaligawe", dasar="Per trip", tarif=100000))
master.simpan(KAR, "catatan", dict(tanggal=H, jenis="Ikan mati", jumlah=5))
master.simpan(KAR, "panen", dict(tanggal=H, pond_id=1, jumlah=200))
master.simpan(KAR, "pengiriman", dict(tanggal=H, status="Dikirim"))
master.simpan_saldo_awal(OWN, H.replace(day=1), [("1101", 5_000_000, 0), ("3101", 0, 5_000_000)], True)
fish = db.satu("SELECT id FROM items WHERE kategori='Ikan hasil panen'")["id"]
_, _, t = tr.simpan_draft(KAR, dict(jenis="penjualan_tunai", tanggal=H, sumber="Kas", item_id=fish, jumlah=10, harga=30000, keterangan="jual")); tr.posting(KAR, t)
tr.simpan_draft(KAR, dict(jenis="biaya_operasional", tanggal=H, sumber="Kas", kategori="Listrik dan BBM", harga=50000, keterangan="draft"))
stok.simpan_hitungan(KAR, H, db.satu("SELECT id FROM items")["id"], 10)

MENU = {}
import importlib
gagal = 0; jumlah = 0
def jalankan(user, menu):
    global gagal, jumlah
    st.session_state.clear(); st.session_state["user"] = user; st.session_state["menu"] = menu; st.session_state["terakhir_aktif"] = __import__("time").time()
    for modul in [m for m in list(sys.modules) if m.startswith("hal_") or m in ("main", "tampilan", "dashboard")]:
        sys.modules.pop(modul, None)
    jumlah += 1
    try:
        runpy.run_path(os.path.join(ROOT, "main.py"), run_name="__main__")
    except Rerun:
        pass
    except Exception:
        gagal += 1
        print(f"GAGAL [{user['jabatan']}] {menu} (klik={MODE['klik']}, baris={MODE['pilih_baris']})"); traceback.print_exc(limit=4)

# ambil daftar menu dari main tanpa menjalankan halaman
st.session_state.clear()
src = runpy.run_path(os.path.join(ROOT, "main.py"), run_name="modul")
for jab, user in (("Owner", OWN), ("Karyawan", KAR)):
    menus = src["menu_boleh"](jab)
    for klik in (False, True):
        for baris in (False, True):
            MODE.update(klik=klik, pilih_baris=baris)
            for m in menus:
                jalankan(user, m)
# karyawan menembus menu terlarang
MODE.update(klik=False, pilih_baris=False)
for m in ["Jurnal Umum", "Audit Trail", "Pengaturan", "Saldo Awal", "Daftar Akun", "Penutupan"]:
    jalankan(KAR, m)
cek = db.satu("SELECT COUNT(*) n FROM audit_log WHERE aksi='akses ditolak'")["n"]
print(f"\n{jumlah} halaman dijalankan, {gagal} gagal. Akses ditolak tercatat: {cek}")
sys.exit(1 if gagal else 0)

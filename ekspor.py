"""ekspor.py - ekspor laporan ke Excel dan PDF (Modul 9.4). Memakai pustaka Python openpyxl dan reportlab."""

import io

import pandas as pd


def ke_excel(judul: str, tabel: dict) -> bytes:
    """tabel = {nama_lembar: DataFrame}."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        for nama, df in tabel.items():
            df.to_excel(w, sheet_name=nama[:31], index=False)
            ws = w.sheets[nama[:31]]
            for col in ws.columns:
                ws.column_dimensions[col[0].column_letter].width = min(max(len(str(c.value or "")) for c in col) + 3, 60)
    return buf.getvalue()


def ke_pdf(judul: str, subjudul: str, tabel: dict) -> bytes:
    """tabel = {judul_bagian: DataFrame}. Warna mengikuti biru #025A95 dan kuning #FEE307."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    biru, kuning = colors.HexColor("#025A95"), colors.HexColor("#FEE307")
    st = getSampleStyleSheet()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36, title=judul)
    isi = [Paragraph(f"<b>{judul}</b>", st["Title"]), Paragraph(subjudul, st["Normal"]), Spacer(1, 12)]
    for nama, df in tabel.items():
        if nama:
            isi.append(Paragraph(f"<b>{nama}</b>", st["Heading3"]))
        data = [list(df.columns)] + [[("" if v is None else str(v)) for v in r] for r in df.values.tolist()]
        t = Table(data, repeatRows=1)
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), biru), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                               ("LINEBELOW", (0, 0), (-1, 0), 2, kuning), ("FONTSIZE", (0, 0), (-1, -1), 8),
                               ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#EAF2F8")]),
                               ("ALIGN", (1, 0), (-1, -1), "RIGHT"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
        isi += [t, Spacer(1, 12)]
    doc.build(isi)
    return buf.getvalue()

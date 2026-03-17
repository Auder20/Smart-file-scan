from __future__ import annotations

import io
import csv
import logging
from datetime import datetime
from typing import Literal, Generator

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.core.scan_store import scan_store
from app.db.database import get_scan, get_db_cursor

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/export", tags=["export"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt_size(size_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"


def _get_meta(scan_id: str) -> dict:
    """Metadatos del scan desde SQLite o memoria."""
    scan_meta = get_scan(scan_id)
    if scan_meta:
        return {
            "scan_id":      scan_id,
            "root_path":    scan_meta.get("root_path", ""),
            "total_files":  scan_meta.get("total_files", 0),
            "total_size":   scan_meta.get("total_size", 0),
            "duration_sec": scan_meta.get("duration_sec", 0),
            "scanned_at":   str(scan_meta.get("scanned_at", datetime.now().isoformat())),
        }
    result = scan_store.get_scan_result(scan_id)
    if result:
        return {
            "scan_id":      scan_id,
            "root_path":    result.root_path,
            "total_files":  result.total_files,
            "total_size":   result.total_size,
            "duration_sec": result.duration_sec,
            "scanned_at":   result.scanned_at.isoformat(),
        }
    raise HTTPException(404, detail=f"Scan '{scan_id}' no encontrado")


def _iter_files(scan_id: str) -> Generator[dict, None, None]:
    offset = 0
    batch_size = 2000
    while True:
        try:
            with get_db_cursor() as cursor:
                cursor.execute(
                    "SELECT name, path, size, extension, category, modified "
                    "FROM scan_files WHERE scan_id=? ORDER BY path LIMIT ? OFFSET ?",
                    (scan_id, batch_size, offset)
                )
                rows = cursor.fetchall()
        except Exception as e:
            raise HTTPException(500, detail=f"Error leyendo archivos: {e}")
        if not rows:
            break
        for r in rows:
            yield {
                "name":      r["name"] or "",
                "path":      r["path"] or "",
                "size":      r["size"] or 0,
                "extension": r["extension"] or "",
                "category":  r["category"] or "other",
                "modified":  str(r["modified"] or "")[:19],
            }
        offset += batch_size
        if len(rows) < batch_size:
            break


def _get_categories(scan_id: str, total_size: int) -> list[dict]:
    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT category, COUNT(*) as c, COALESCE(SUM(size),0) as s
            FROM scan_files WHERE scan_id=? GROUP BY category ORDER BY s DESC
        """, (scan_id,))
        return [
            {"category":   r["category"] or "other",
             "file_count": r["c"],
             "total_size": r["s"],
             "percentage": round(r["s"] * 100.0 / total_size, 1) if total_size > 0 else 0}
            for r in cursor.fetchall()
        ]


# ── CSV (streaming real) ──────────────────────────────────────────────────────

def _export_csv(scan_id: str) -> StreamingResponse:
    meta = _get_meta(scan_id)

    def generate():
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["# Smart File Organizer — Reporte de Escaneo"])
        w.writerow(["# Ruta escaneada", meta["root_path"]])
        w.writerow(["# Fecha", meta["scanned_at"]])
        w.writerow(["# Total archivos", meta["total_files"]])
        w.writerow(["# Tamaño total", _fmt_size(meta["total_size"])])
        w.writerow(["# Duración (s)", meta["duration_sec"]])
        w.writerow([])
        w.writerow(["Nombre", "Ruta", "Tamaño (bytes)", "Tamaño", "Extensión", "Categoría", "Modificado"])
        yield buf.getvalue().encode("utf-8-sig")
        for f in _iter_files(scan_id):
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow([f["name"], f["path"], f["size"], _fmt_size(f["size"]),
                        f["extension"], f["category"], f["modified"]])
            yield buf.getvalue().encode("utf-8-sig")

    filename = f"scan_{scan_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(generate(), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'})


# ── Excel scan ────────────────────────────────────────────────────────────────

def _export_excel(scan_id: str) -> StreamingResponse:
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side, GradientFill
        from openpyxl.utils import get_column_letter
        from openpyxl.cell import WriteOnlyCell
        from openpyxl.worksheet.dimensions import ColumnDimension
    except ImportError:
        raise HTTPException(500, detail="openpyxl no instalado.")

    meta       = _get_meta(scan_id)
    categories = _get_categories(scan_id, meta["total_size"])

    # Paleta premium — azul medianoche + slate + acentos esmeralda
    C_NAVY    = "0F172A"   # encabezado principal
    C_SLATE   = "1E293B"   # encabezado secundario
    C_BLUE    = "3B82F6"   # acento principal
    C_EMERALD = "10B981"   # acento positivo
    C_ALT     = "F8FAFC"   # fila alternada
    C_ALT2    = "EFF6FF"   # fila alternada azul suave
    C_FG      = "FFFFFF"
    C_MUTED   = "94A3B8"
    C_BORDER  = "E2E8F0"
    C_TEXT    = "1E293B"

    def _border(color=C_BORDER, style="thin"):
        s = Side(style=style, color=color)
        return Border(left=s, right=s, top=s, bottom=s)

    def _hdr(cell, text, bg=C_SLATE, fg=C_FG, size=11, bold=True):
        cell.value = text
        cell.font  = Font(name="Calibri", bold=bold, color=fg, size=size)
        cell.fill  = PatternFill("solid", fgColor=bg)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = _border(C_BORDER)

    wb = openpyxl.Workbook(write_only=False)

    # ── Hoja Resumen ──────────────────────────────────────────────────────────
    ws = wb.active; ws.title = "Resumen"
    ws.sheet_view.showGridLines = False
    ws.sheet_view.zoomScale = 100

    # Banda de título con doble fila
    ws.merge_cells("A1:F1")
    ws["A1"].value     = "SMART FILE ORGANIZER"
    ws["A1"].font      = Font(name="Calibri", size=20, bold=True, color=C_FG)
    ws["A1"].fill      = PatternFill("solid", fgColor=C_NAVY)
    ws["A1"].alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 42

    ws.merge_cells("A2:F2")
    ws["A2"].value     = "Reporte de Escaneo de Archivos"
    ws["A2"].font      = Font(name="Calibri", size=11, color="93C5FD")
    ws["A2"].fill      = PatternFill("solid", fgColor=C_NAVY)
    ws["A2"].alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[2].height = 22

    ws.merge_cells("A3:F3")
    ws["A3"].value     = f"Generado el {datetime.now().strftime('%d de %B de %Y — %H:%M:%S')}"
    ws["A3"].font      = Font(name="Calibri", size=9, color=C_MUTED, italic=True)
    ws["A3"].fill      = PatternFill("solid", fgColor="0F1F38")
    ws["A3"].alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[3].height = 18
    ws.append([])
    ws.row_dimensions[4].height = 8

    # Sección: Información del escaneo
    ws.append(["  INFORMACIÓN DEL ESCANEO"])
    r = ws.max_row
    ws.merge_cells(f"A{r}:F{r}")
    ws[f"A{r}"].font      = Font(name="Calibri", size=10, bold=True, color=C_FG)
    ws[f"A{r}"].fill      = PatternFill("solid", fgColor=C_BLUE)
    ws[f"A{r}"].alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws.row_dimensions[r].height = 22

    meta_rows = [
        ("📁  Ruta escaneada",    meta["root_path"]),
        ("📅  Fecha de escaneo",  str(meta["scanned_at"])[:19].replace("T", " ")),
        ("📊  Total de archivos", f"{meta['total_files']:,} archivos"),
        ("💾  Tamaño total",      _fmt_size(meta["total_size"])),
        ("⏱   Duración",          f"{meta['duration_sec']:.2f} segundos"),
        ("🔑  Scan ID",           meta["scan_id"]),
    ]
    for i, (label, val) in enumerate(meta_rows):
        ws.append([label, val])
        r = ws.max_row
        bg = C_ALT if i % 2 == 0 else C_FG
        ws[f"A{r}"].font      = Font(name="Calibri", bold=True, size=10, color=C_TEXT)
        ws[f"A{r}"].fill      = PatternFill("solid", fgColor=bg)
        ws[f"A{r}"].border    = _border()
        ws[f"A{r}"].alignment = Alignment(vertical="center", indent=1)
        ws[f"B{r}"].font      = Font(name="Calibri", size=10, color=C_TEXT)
        ws[f"B{r}"].fill      = PatternFill("solid", fgColor=bg)
        ws[f"B{r}"].border    = _border()
        ws[f"B{r}"].alignment = Alignment(vertical="center")
        ws.row_dimensions[r].height = 20
        # Extender fondo a columnas C-F para estética limpia
        for col in range(3, 7):
            c = ws.cell(r, col)
            c.fill   = PatternFill("solid", fgColor=bg)
            c.border = _border()

    ws.append([])
    ws.row_dimensions[ws.max_row].height = 10

    # Sección: categorías
    ws.append(["  DISTRIBUCIÓN POR CATEGORÍA"])
    r = ws.max_row
    ws.merge_cells(f"A{r}:F{r}")
    ws[f"A{r}"].font      = Font(name="Calibri", size=10, bold=True, color=C_FG)
    ws[f"A{r}"].fill      = PatternFill("solid", fgColor=C_EMERALD)
    ws[f"A{r}"].alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws.row_dimensions[r].height = 22

    cat_hdr_row = ws.max_row + 1
    for col, (txt, w) in enumerate(
        [("Categoría", 22), ("Archivos", 14), ("Tamaño total", 18), ("% del total", 14),
         ("Proporción por tamaño", 30), ("", 6)], 1
    ):
        _hdr(ws.cell(cat_hdr_row, col), txt, bg=C_SLATE)
    ws.row_dimensions[cat_hdr_row].height = 22

    CAT_COLORS = ["3B82F6","10B981","F59E0B","EF4444",
                  "8B5CF6","EC4899","14B8A6","F97316","6366F1","84CC16"]
    total_files_n  = max(meta["total_files"], 1)
    max_cat_size   = max((cat["total_size"]  for cat in categories), default=1)
    max_cat_count  = max((cat["file_count"]  for cat in categories), default=1)

    for i, cat in enumerate(categories):
        pct_files = cat["file_count"] / total_files_n * 100
        # Barra proporcional al tamaño (no a la cantidad de archivos)
        bar_filled = int(cat["total_size"]  / max_cat_size  * 25)
        bar_empty  = 25 - bar_filled
        bar_str    = "█" * bar_filled + "░" * bar_empty
        row_vals = [
            f"  {cat['category'].capitalize()}",
            cat["file_count"],
            _fmt_size(cat["total_size"]),
            f"{cat['percentage']:.1f}%",
            bar_str,
            "",
        ]
        ws.append(row_vals)
        r   = ws.max_row
        bg  = C_ALT2 if i % 2 == 0 else C_FG
        clr = CAT_COLORS[i % len(CAT_COLORS)]
        for col in range(1, 7):
            c = ws.cell(r, col)
            c.fill   = PatternFill("solid", fgColor=bg)
            c.border = _border()
            c.font   = Font(name="Calibri", size=10,
                            color=(clr if col == 5 else C_TEXT),
                            bold=(col == 1))
            if col in (2, 3, 4): c.alignment = Alignment(horizontal="center", vertical="center")
            if col == 1:          c.alignment = Alignment(vertical="center", indent=1)
            if col == 5:          c.alignment = Alignment(vertical="center")
        ws.row_dimensions[r].height = 20

    for col, w in enumerate([22, 14, 18, 14, 32, 6], 1):
        ws.column_dimensions[get_column_letter(col)].width = w

    # ── Hoja Archivos (write_only) ────────────────────────────────────────────
    ws_files = wb.create_sheet("Archivos")
    headers  = ["#", "Nombre", "Extensión", "Categoría",
                "Tamaño (bytes)", "Tamaño", "Ruta", "Modificado"]

    hdr_row = []
    for h in headers:
        c = WriteOnlyCell(ws_files, value=h)
        c.font      = Font(name="Calibri", bold=True, color=C_FG, size=10)
        c.fill      = PatternFill("solid", fgColor=C_NAVY)
        c.alignment = Alignment(horizontal="center", vertical="center")
        c.border    = _border()
        hdr_row.append(c)
    ws_files.append(hdr_row)

    alt_fill = PatternFill("solid", fgColor=C_ALT)
    wht_fill = PatternFill("solid", fgColor=C_FG)
    body_fnt = Font(name="Calibri", size=9, color=C_TEXT)
    bold_fnt = Font(name="Calibri", size=9, color=C_TEXT, bold=True)
    ctr_aln  = Alignment(horizontal="center", vertical="center")
    lft_aln  = Alignment(vertical="center", indent=1)

    for i, f in enumerate(_iter_files(scan_id), 1):
        fill = alt_fill if i % 2 == 0 else wht_fill
        size = f["size"]
        row  = []
        for val, center, bold in [
            (i, True, False), (f["name"], False, True), (f["extension"], True, False),
            (f["category"].capitalize(), True, False), (size, True, False),
            (_fmt_size(size), True, False), (f["path"], False, False),
            (f["modified"][:19] if f["modified"] else "", True, False),
        ]:
            c = WriteOnlyCell(ws_files, value=val)
            c.font  = bold_fnt if bold else body_fnt
            c.fill  = fill
            c.border = _border()
            c.alignment = ctr_aln if center else lft_aln
            row.append(c)
        ws_files.append(row)

    from openpyxl.worksheet.dimensions import ColumnDimension as CD
    for col_idx, w in enumerate([6, 30, 10, 14, 16, 12, 55, 20], 1):
        col_letter = get_column_letter(col_idx)
        ws_files.column_dimensions[col_letter] = CD(ws_files, index=col_letter, width=w)

    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    filename = f"scan_{scan_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return StreamingResponse(iter([buf.read()]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'})


# ── PDF scan ──────────────────────────────────────────────────────────────────

def _export_pdf(scan_id: str) -> StreamingResponse:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                         Paragraph, Spacer, HRFlowable, PageBreak, Flowable)
        from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
    except ImportError:
        raise HTTPException(500, detail="reportlab no instalado.")

    meta       = _get_meta(scan_id)
    categories = _get_categories(scan_id, meta["total_size"])

    # Paleta premium
    NAVY      = colors.HexColor("#0F172A")
    SLATE     = colors.HexColor("#1E293B")
    BLUE      = colors.HexColor("#3B82F6")
    BLUE_SOFT = colors.HexColor("#EFF6FF")
    EMERALD   = colors.HexColor("#10B981")
    EMLD_SOFT = colors.HexColor("#ECFDF5")
    ALT       = colors.HexColor("#F8FAFC")
    WHITE     = colors.white
    MUTED     = colors.HexColor("#64748B")
    BORDER    = colors.HexColor("#E2E8F0")
    TEXT      = colors.HexColor("#1E293B")

    CAT_COLORS_HEX = ["#3B82F6","#10B981","#F59E0B","#EF4444",
                      "#8B5CF6","#EC4899","#14B8A6","#F97316","#6366F1","#84CC16"]

    st_title   = ParagraphStyle("t",   fontSize=24, fontName="Helvetica-Bold",
                                 textColor=WHITE, alignment=TA_CENTER, leading=30)
    st_sub     = ParagraphStyle("s",   fontSize=9.5, fontName="Helvetica",
                                 textColor=colors.HexColor("#93C5FD"), alignment=TA_CENTER, leading=14)
    st_ts      = ParagraphStyle("ts",  fontSize=8, fontName="Helvetica",
                                 textColor=MUTED, alignment=TA_CENTER, leading=12)
    st_section = ParagraphStyle("sec", fontSize=12, fontName="Helvetica-Bold",
                                 textColor=NAVY, spaceBefore=4, leading=16)
    st_cell    = ParagraphStyle("c",   fontSize=7.5, fontName="Helvetica",
                                 textColor=TEXT, leading=10, wordWrap="CJK")
    st_center  = ParagraphStyle("cc",  fontSize=7.5, fontName="Helvetica",
                                 textColor=TEXT, leading=10, alignment=TA_CENTER)
    st_right   = ParagraphStyle("cr",  fontSize=7.5, fontName="Helvetica",
                                 textColor=TEXT, leading=10, alignment=TA_RIGHT)
    st_muted   = ParagraphStyle("m",   fontSize=7, fontName="Helvetica",
                                 textColor=MUTED, leading=10, alignment=TA_CENTER)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4),
        leftMargin=1.8*cm, rightMargin=1.8*cm,
        topMargin=2.2*cm, bottomMargin=2*cm,
        title="Smart File Organizer Report")
    story = []

    # ── Cover header block ────────────────────────────────────────────────────
    hdr_data = [[
        Paragraph("SMART FILE ORGANIZER", st_title),
    ]]
    hdr = Table(hdr_data, colWidths=[doc.width])
    hdr.setStyle(TableStyle([
        ("BACKGROUND",     (0,0), (-1,-1), NAVY),
        ("TOPPADDING",     (0,0), (-1,-1), 18),
        ("BOTTOMPADDING",  (0,0), (-1,-1), 6),
        ("LEFTPADDING",    (0,0), (-1,-1), 0),
        ("RIGHTPADDING",   (0,0), (-1,-1), 0),
    ]))
    story.append(hdr)

    sub_data = [[Paragraph("Reporte de Escaneo de Archivos", st_sub)]]
    sub = Table(sub_data, colWidths=[doc.width])
    sub.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), NAVY),
        ("TOPPADDING",    (0,0), (-1,-1), 2),
        ("BOTTOMPADDING", (0,0), (-1,-1), 14),
    ]))
    story.append(sub)

    ts_data = [[Paragraph(
        f"Generado el {datetime.now().strftime('%d de %B de %Y  |  %H:%M:%S')}  ·  Scan ID: {scan_id}",
        st_ts)]]
    ts_tbl = Table(ts_data, colWidths=[doc.width])
    ts_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), colors.HexColor("#0F1F38")),
        ("TOPPADDING",    (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
    ]))
    story.append(ts_tbl)
    story.append(Spacer(1, 0.5*cm))

    # ── KPI cards row ─────────────────────────────────────────────────────────
    st_kpi_label = ParagraphStyle("kl", fontSize=7.5, fontName="Helvetica",
                                   textColor=colors.HexColor("#93C5FD"), alignment=TA_CENTER)
    st_kpi_val   = ParagraphStyle("kv", fontSize=18, fontName="Helvetica-Bold",
                                   textColor=WHITE, alignment=TA_CENTER, leading=22)
    st_kpi_unit  = ParagraphStyle("ku", fontSize=8, fontName="Helvetica",
                                   textColor=colors.HexColor("#93C5FD"), alignment=TA_CENTER)

    kpi_w = doc.width / 4
    kpi_data = [[
        Table([[Paragraph("TOTAL ARCHIVOS", st_kpi_label)],
               [Paragraph(f"{meta['total_files']:,}", st_kpi_val)],
               [Paragraph("archivos encontrados", st_kpi_unit)]],
              colWidths=[kpi_w - 0.4*cm]),
        Table([[Paragraph("TAMAÑO TOTAL", st_kpi_label)],
               [Paragraph(_fmt_size(meta['total_size']), st_kpi_val)],
               [Paragraph("espacio ocupado", st_kpi_unit)]],
              colWidths=[kpi_w - 0.4*cm]),
        Table([[Paragraph("CATEGORÍAS", st_kpi_label)],
               [Paragraph(str(len(categories)), st_kpi_val)],
               [Paragraph("tipos de archivo", st_kpi_unit)]],
              colWidths=[kpi_w - 0.4*cm]),
        Table([[Paragraph("DURACIÓN", st_kpi_label)],
               [Paragraph(f"{meta['duration_sec']:.1f}s", st_kpi_val)],
               [Paragraph("tiempo de escaneo", st_kpi_unit)]],
              colWidths=[kpi_w - 0.4*cm]),
    ]]
    kpi_tbl = Table(kpi_data, colWidths=[kpi_w]*4)
    kpi_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), SLATE),
        ("TOPPADDING",    (0,0), (-1,-1), 10),
        ("BOTTOMPADDING", (0,0), (-1,-1), 10),
        ("LEFTPADDING",   (0,0), (-1,-1), 8),
        ("RIGHTPADDING",  (0,0), (-1,-1), 8),
        ("LINEAFTER",     (0,0), (2,-1), 0.5, colors.HexColor("#334155")),
        ("ROUNDEDCORNERS",(0,0), (-1,-1), 4),
    ]))
    story.append(kpi_tbl)
    story.append(Spacer(1, 0.6*cm))

    # ── Sección: Información del escaneo ─────────────────────────────────────
    story.append(_section_header("Información del Escaneo", BLUE, doc.width))
    story.append(Spacer(1, 0.2*cm))

    hw = doc.width / 2
    info_rows = [
        ["Ruta escaneada",   meta["root_path"]],
        ["Fecha de escaneo", str(meta["scanned_at"])[:19].replace("T", " ")],
        ["Total de archivos",f"{meta['total_files']:,}"],
        ["Tamaño total",     _fmt_size(meta["total_size"])],
        ["Duración",         f"{meta['duration_sec']:.2f} segundos"],
        ["Scan ID",          meta["scan_id"]],
    ]
    info_tbl = Table(info_rows, colWidths=[hw*0.32, hw*0.68])
    info_tbl.setStyle(TableStyle([
        ("ROWBACKGROUNDS",  (0,0), (-1,-1), [WHITE, ALT]),
        ("FONTNAME",        (0,0), (0,-1), "Helvetica-Bold"),
        ("FONTNAME",        (1,0), (1,-1), "Helvetica"),
        ("FONTSIZE",        (0,0), (-1,-1), 9),
        ("TEXTCOLOR",       (0,0), (-1,-1), TEXT),
        ("LEFTPADDING",     (0,0), (-1,-1), 10),
        ("RIGHTPADDING",    (0,0), (-1,-1), 10),
        ("TOPPADDING",      (0,0), (-1,-1), 6),
        ("BOTTOMPADDING",   (0,0), (-1,-1), 6),
        ("GRID",            (0,0), (-1,-1), 0.5, BORDER),
        ("LEFTPADDING",     (0,0), (0,-1), 12),
    ]))
    story.append(info_tbl)
    story.append(Spacer(1, 0.7*cm))

    # ── Sección: Categorías ───────────────────────────────────────────────────
    story.append(_section_header("Distribución por Categoría", EMERALD, doc.width))
    story.append(Spacer(1, 0.2*cm))

    total_files_n = max(meta["total_files"], 1)
    max_cat_size  = max((cat["total_size"] for cat in categories), default=1)
    max_cat_count = max((cat["file_count"] for cat in categories), default=1)

    class _ScanBar(Flowable):
        """Barra canvas proporcional para _export_pdf."""
        def __init__(self, ratio, color_hex, bg_hex="#E2E8F0", w=100, h=9):
            super().__init__()
            self.ratio   = max(0.0, min(1.0, float(ratio)))
            self.bar_clr = colors.HexColor(color_hex)
            self.bg_clr  = colors.HexColor(bg_hex)
            self.width   = w
            self.height  = h
        def draw(self):
            self.canv.setFillColor(self.bg_clr)
            self.canv.roundRect(0, 1, self.width, self.height - 2, 2, fill=1, stroke=0)
            if self.ratio > 0.005:
                fw = max(self.ratio * self.width, 4)
                self.canv.setFillColor(self.bar_clr)
                self.canv.roundRect(0, 1, fw, self.height - 2, 2, fill=1, stroke=0)
            pct = f"{self.ratio * 100:.1f}%"
            fill_px = self.ratio * self.width
            self.canv.setFont("Helvetica-Bold", 5.5)
            if fill_px > 22:
                self.canv.setFillColor(colors.white)
                self.canv.drawCentredString(fill_px / 2, 2.5, pct)
            else:
                self.canv.setFillColor(colors.HexColor("#475569"))
                self.canv.drawString(fill_px + 2, 2.5, pct)
        def wrap(self, aw, ah): return self.width, self.height

    BAR_W_SCAN = doc.width * 0.24
    cat_hdr = [
        Paragraph("Categoría",    ParagraphStyle("ch",  fontSize=9, fontName="Helvetica-Bold", textColor=WHITE, alignment=TA_LEFT)),
        Paragraph("Archivos",     ParagraphStyle("ch2", fontSize=9, fontName="Helvetica-Bold", textColor=WHITE, alignment=TA_CENTER)),
        Paragraph("Tamaño",       ParagraphStyle("ch3", fontSize=9, fontName="Helvetica-Bold", textColor=WHITE, alignment=TA_CENTER)),
        Paragraph("% Tamaño",     ParagraphStyle("ch4", fontSize=9, fontName="Helvetica-Bold", textColor=WHITE, alignment=TA_CENTER)),
        Paragraph("Por archivos", ParagraphStyle("ch5", fontSize=9, fontName="Helvetica-Bold", textColor=WHITE, alignment=TA_CENTER)),
        Paragraph("Por tamaño",   ParagraphStyle("ch6", fontSize=9, fontName="Helvetica-Bold", textColor=WHITE, alignment=TA_CENTER)),
    ]
    cat_rows = [cat_hdr]
    col_cat_w = [doc.width*0.16, doc.width*0.09, doc.width*0.12,
                 doc.width*0.09, BAR_W_SCAN, BAR_W_SCAN]

    for i, cat in enumerate(categories):
        clr       = CAT_COLORS_HEX[i % len(CAT_COLORS_HEX)]
        r_count   = cat["file_count"] / max_cat_count if max_cat_count > 0 else 0
        r_size    = cat["total_size"]  / max_cat_size  if max_cat_size  > 0 else 0
        cat_rows.append([
            Paragraph(f"  {cat['category'].capitalize()}",
                      ParagraphStyle(f"ci{i}", fontSize=8.5, fontName="Helvetica-Bold",
                                     textColor=colors.HexColor(clr), leading=11)),
            Paragraph(f"{cat['file_count']:,}", st_center),
            Paragraph(_fmt_size(cat["total_size"]), st_center),
            Paragraph(f"{cat['percentage']:.1f}%", st_center),
            _ScanBar(r_count, clr, w=BAR_W_SCAN - 14),
            _ScanBar(r_size,  clr, w=BAR_W_SCAN - 14),
        ])

    cat_tbl = Table(cat_rows, colWidths=col_cat_w)
    cat_style = [
        ("BACKGROUND",    (0,0), (-1,0), SLATE),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [WHITE, ALT]),
        ("GRID",          (0,0), (-1,-1), 0.4, BORDER),
        ("TOPPADDING",    (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ("LEFTPADDING",   (0,0), (-1,-1), 8),
        ("RIGHTPADDING",  (0,0), (-1,-1), 8),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
    ]
    cat_tbl.setStyle(TableStyle(cat_style))
    story.append(cat_tbl)

    # ── Página de archivos ────────────────────────────────────────────────────
    MAX_FILES_IN_PDF = 5000
    story.append(PageBreak())

    title_txt = (f"Lista de Archivos — primeros {MAX_FILES_IN_PDF:,} de {meta['total_files']:,}"
                 if meta["total_files"] > MAX_FILES_IN_PDF else "Lista de Archivos")
    story.append(_section_header(title_txt, BLUE, doc.width))
    story.append(Spacer(1, 0.2*cm))

    file_hdr_style = ParagraphStyle("fh", fontSize=8, fontName="Helvetica-Bold",
                                     textColor=WHITE, alignment=TA_CENTER)
    file_rows = [[
        Paragraph("#", file_hdr_style),
        Paragraph("Nombre", file_hdr_style),
        Paragraph("Ext.", file_hdr_style),
        Paragraph("Categoría", file_hdr_style),
        Paragraph("Tamaño", file_hdr_style),
        Paragraph("Modificado", file_hdr_style),
        Paragraph("Ruta completa", file_hdr_style),
    ]]
    count = 0
    for f in _iter_files(scan_id):
        if count >= MAX_FILES_IN_PDF: break
        path = f["path"]
        if len(path) > 72: path = "…" + path[-69:]
        file_rows.append([
            Paragraph(str(count + 1), st_muted),
            Paragraph(f["name"],      ParagraphStyle("fn", fontSize=7.5,
                      fontName="Helvetica-Bold", textColor=TEXT, leading=10)),
            Paragraph(f["extension"].upper() or "—", st_center),
            Paragraph(f["category"].capitalize(), st_center),
            Paragraph(_fmt_size(f["size"]), st_right),
            Paragraph(f["modified"][:10] if f["modified"] else "—", st_center),
            Paragraph(path, st_cell),
        ])
        count += 1

    c_widths = [0.9*cm, 5.2*cm, 1.6*cm, 2.4*cm, 2.0*cm, 2.4*cm, None]
    c_widths[-1] = doc.width - sum(w for w in c_widths if w)
    files_tbl = Table(file_rows, colWidths=c_widths, repeatRows=1)
    files_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,0), NAVY),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [WHITE, ALT]),
        ("GRID",          (0,0), (-1,-1), 0.3, BORDER),
        ("TOPPADDING",    (0,0), (-1,-1), 3),
        ("BOTTOMPADDING", (0,0), (-1,-1), 3),
        ("LEFTPADDING",   (0,0), (-1,-1), 4),
        ("RIGHTPADDING",  (0,0), (-1,-1), 4),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
    ]))
    story.append(files_tbl)

    def on_page(canvas, doc):
        canvas.saveState()
        # Footer bar
        canvas.setFillColor(NAVY)
        canvas.rect(0, 0, doc.pagesize[0], 1.4*cm, fill=1, stroke=0)
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(colors.HexColor("#64748B"))
        canvas.drawString(1.8*cm, 0.5*cm,
            f"Smart File Organizer  ·  Scan {scan_id}  ·  {datetime.now().strftime('%d/%m/%Y')}")
        canvas.setFillColor(colors.HexColor("#93C5FD"))
        canvas.drawRightString(doc.pagesize[0] - 1.8*cm, 0.5*cm,
            f"Página {doc.page}")
        # Top accent line
        canvas.setFillColor(BLUE)
        canvas.rect(0, doc.pagesize[1] - 0.18*cm, doc.pagesize[0], 0.18*cm, fill=1, stroke=0)
        canvas.restoreState()

    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    buf.seek(0)
    filename = f"scan_{scan_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return StreamingResponse(iter([buf.read()]), media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'})


# ── Helper: section header ────────────────────────────────────────────────────

def _section_header(title: str, color, width):
    from reportlab.platypus import Table, TableStyle, Paragraph
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib import colors as rl_colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.units import cm

    WHITE = rl_colors.white
    st = ParagraphStyle("sh", fontSize=10, fontName="Helvetica-Bold",
                        textColor=WHITE, alignment=TA_LEFT, leading=14)
    tbl = Table([[Paragraph(f"  {title.upper()}", st)]], colWidths=[width])
    tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), color),
        ("TOPPADDING",    (0,0), (-1,-1), 7),
        ("BOTTOMPADDING", (0,0), (-1,-1), 7),
        ("LEFTPADDING",   (0,0), (-1,-1), 4),
    ]))
    return tbl


# ── Stats data (SQL puro) ─────────────────────────────────────────────────────

def _get_stats_data(scan_id: str) -> tuple[dict, list[dict], list[dict]]:
    scan_meta = get_scan(scan_id)
    result    = scan_store.get_scan_result(scan_id)
    if not scan_meta and not result:
        raise HTTPException(404, detail=f"Scan '{scan_id}' no encontrado")

    try:
        with get_db_cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) as cnt, COALESCE(SUM(size),0) as total "
                "FROM scan_files WHERE scan_id=?", (scan_id,))
            row = cursor.fetchone()
            total_files = row["cnt"]; total_size = row["total"]

            cursor.execute("""
                SELECT category, COUNT(*) as c, COALESCE(SUM(size),0) as s
                FROM scan_files WHERE scan_id=? GROUP BY category ORDER BY s DESC
            """, (scan_id,))
            categories = [
                {"category": r["category"] or "other", "file_count": r["c"],
                 "total_size": r["s"],
                 "percentage": round(r["s"] * 100.0 / total_size, 1) if total_size > 0 else 0}
                for r in cursor.fetchall()
            ]

            cursor.execute(
                "SELECT name, path, size, modified FROM scan_files "
                "WHERE scan_id=? ORDER BY size DESC LIMIT 20", (scan_id,))
            largest = [
                {"rank": i+1, "name": r["name"], "path": r["path"],
                 "size": r["size"] or 0, "modified": str(r["modified"] or "")[:10]}
                for i, r in enumerate(cursor.fetchall())
            ]

            cursor.execute("""
                SELECT UPPER(COALESCE(NULLIF(extension,''),'SIN EXT')) as ext,
                       COUNT(*) as cnt, COALESCE(SUM(size),0) as sz
                FROM scan_files WHERE scan_id=? GROUP BY ext ORDER BY cnt DESC LIMIT 20
            """, (scan_id,))
            extensions = [
                {"extension": r["ext"], "count": r["cnt"], "total_size": r["sz"],
                 "percentage": round(r["cnt"] * 100.0 / total_files, 1) if total_files > 0 else 0}
                for r in cursor.fetchall()
            ]
    except Exception as e:
        raise HTTPException(500, detail=f"Error obteniendo estadísticas: {e}")

    root_path = (scan_meta.get("root_path", "") if scan_meta else
                 result.root_path if result else "")
    return (
        {"scan_id": scan_id, "total_files": total_files,
         "total_size": total_size, "categories": categories, "root_path": root_path},
        largest,
        extensions,
    )


# ── Stats PDF — rediseño premium ──────────────────────────────────────────────

def _export_stats_pdf(scan_id: str) -> StreamingResponse:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                         Paragraph, Spacer, HRFlowable, Flowable)
        from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
    except ImportError:
        raise HTTPException(500, detail="reportlab no instalado.")

    stats, largest, extensions = _get_stats_data(scan_id)

    # ── Barra proporcional real — dibujada con canvas, nunca se corta ─────────
    class _Bar(Flowable):
        """Rectángulo horizontal proporcional. ratio in [0,1]."""
        def __init__(self, ratio, color_hex, bg_hex="#E2E8F0", w=110, h=9):
            super().__init__()
            self.ratio   = max(0.0, min(1.0, float(ratio)))
            self.bar_clr = colors.HexColor(color_hex)
            self.bg_clr  = colors.HexColor(bg_hex)
            self.width   = w
            self.height  = h
        def draw(self):
            # Track (fondo)
            self.canv.setFillColor(self.bg_clr)
            self.canv.roundRect(0, 1, self.width, self.height - 2, 2, fill=1, stroke=0)
            # Fill proporcional
            if self.ratio > 0.005:
                fw = max(self.ratio * self.width, 4)
                self.canv.setFillColor(self.bar_clr)
                self.canv.roundRect(0, 1, fw, self.height - 2, 2, fill=1, stroke=0)
            # Etiqueta porcentaje
            pct = f"{self.ratio * 100:.1f}%"
            fill_px = self.ratio * self.width
            txt_x   = fill_px / 2 if fill_px > 22 else fill_px + 4
            txt_color = colors.white if fill_px > 22 else colors.HexColor("#475569")
            self.canv.setFillColor(txt_color)
            self.canv.setFont("Helvetica-Bold", 5.5)
            if fill_px > 22:
                self.canv.drawCentredString(fill_px / 2, 2.5, pct)
            else:
                self.canv.drawString(fill_px + 2, 2.5, pct)
        def wrap(self, aw, ah):
            return self.width, self.height

    # Paleta premium — azul medianoche + matices fríos
    NAVY      = colors.HexColor("#0F172A")
    SLATE     = colors.HexColor("#1E293B")
    SLATE2    = colors.HexColor("#334155")
    BLUE      = colors.HexColor("#3B82F6")
    BLUE_SOFT = colors.HexColor("#EFF6FF")
    BLUE_MID  = colors.HexColor("#BFDBFE")
    EMERALD   = colors.HexColor("#10B981")
    EMLD_SOFT = colors.HexColor("#ECFDF5")
    AMBER     = colors.HexColor("#F59E0B")
    AMBD_SOFT = colors.HexColor("#FFFBEB")
    ALT       = colors.HexColor("#F8FAFC")
    ALT2      = colors.HexColor("#F1F5F9")
    WHITE     = colors.white
    MUTED     = colors.HexColor("#64748B")
    BORDER    = colors.HexColor("#E2E8F0")
    TEXT      = colors.HexColor("#1E293B")
    TEXT_SOFT = colors.HexColor("#475569")

    CAT_COLORS = ["#3B82F6","#10B981","#F59E0B","#EF4444",
                  "#8B5CF6","#EC4899","#14B8A6","#F97316","#6366F1","#84CC16"]

    # Estilos tipográficos ─────────────────────────────────────────────────────
    def sty(name, size=9, bold=False, italic=False, color=None, align=TA_LEFT, leading=None):
        return ParagraphStyle(name,
            fontSize=size,
            fontName=("Helvetica-Bold" if bold else "Helvetica-BoldOblique" if italic else "Helvetica"),
            textColor=color or TEXT,
            alignment=align,
            leading=leading or (size * 1.35),
        )

    st_cell   = sty("cell",  7.5)
    st_ctr    = sty("ctr",   7.5, align=TA_CENTER)
    st_rgt    = sty("rgt",   7.5, align=TA_RIGHT)
    st_muted  = sty("mut",   7.5, color=MUTED, align=TA_CENTER)
    st_bold   = sty("bld",   8,   bold=True)
    st_bold_c = sty("bldc",  8,   bold=True, align=TA_CENTER)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2.5*cm, bottomMargin=2*cm,
        title="Smart File Organizer — Estadísticas")
    story = []
    W = doc.width

    # ── COVER HEADER ─────────────────────────────────────────────────────────
    # Banda principal (azul medianoche)
    st_main_title = ParagraphStyle("mt", fontSize=22, fontName="Helvetica-Bold",
                                    textColor=WHITE, alignment=TA_CENTER, leading=28)
    st_main_sub   = ParagraphStyle("ms", fontSize=10, fontName="Helvetica",
                                    textColor=colors.HexColor("#93C5FD"),
                                    alignment=TA_CENTER, leading=14)
    st_main_ts    = ParagraphStyle("mts", fontSize=8, fontName="Helvetica",
                                    textColor=colors.HexColor("#64748B"),
                                    alignment=TA_CENTER, leading=12)

    hdr_inner = Table([
        [Paragraph("SMART FILE ORGANIZER", st_main_title)],
        [Paragraph("Informe de Estadísticas de Archivo", st_main_sub)],
    ], colWidths=[W])
    hdr_inner.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), NAVY),
        ("TOPPADDING",    (0,0), (0,0), 18),
        ("BOTTOMPADDING", (0,0), (0,0), 4),
        ("TOPPADDING",    (0,1), (0,1), 2),
        ("BOTTOMPADDING", (0,1), (0,1), 14),
        ("LEFTPADDING",   (0,0), (-1,-1), 0),
        ("RIGHTPADDING",  (0,0), (-1,-1), 0),
    ]))
    story.append(hdr_inner)

    ts_row = Table([
        [Paragraph(
            f"Scan ID: <b>{scan_id}</b>  ·  Generado el {datetime.now().strftime('%d de %B de %Y, %H:%M:%S')}",
            st_main_ts)],
    ], colWidths=[W])
    ts_row.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), colors.HexColor("#0F1F38")),
        ("TOPPADDING",    (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
    ]))
    story.append(ts_row)
    story.append(Spacer(1, 0.55*cm))

    # ── KPI CARDS (4 tarjetas en una fila) ───────────────────────────────────
    st_kpi_lbl = ParagraphStyle("kl", fontSize=7, fontName="Helvetica",
                                 textColor=colors.HexColor("#93C5FD"),
                                 alignment=TA_CENTER, leading=10)
    st_kpi_val = ParagraphStyle("kv", fontSize=20, fontName="Helvetica-Bold",
                                 textColor=WHITE, alignment=TA_CENTER, leading=24)
    st_kpi_sub = ParagraphStyle("ks", fontSize=7.5, fontName="Helvetica",
                                 textColor=colors.HexColor("#CBD5E1"),
                                 alignment=TA_CENTER, leading=10)

    def _kpi_card(label, value, subtitle, accent_color):
        inner = Table([
            [Paragraph(label, st_kpi_lbl)],
            [Paragraph(value, st_kpi_val)],
            [Paragraph(subtitle, st_kpi_sub)],
        ], colWidths=[W/4 - 0.6*cm])
        inner.setStyle(TableStyle([
            ("BACKGROUND",    (0,0), (-1,-1), SLATE),
            ("TOPPADDING",    (0,0), (0,0), 8),
            ("BOTTOMPADDING", (0,0), (0,0), 2),
            ("TOPPADDING",    (0,1), (0,1), 2),
            ("BOTTOMPADDING", (0,1), (0,1), 2),
            ("TOPPADDING",    (0,2), (0,2), 2),
            ("BOTTOMPADDING", (0,2), (0,2), 8),
            ("LINEBELOW",     (0,0), (-1,0), 2, accent_color),
        ]))
        return inner

    kpi_row = [[
        _kpi_card("ARCHIVOS TOTALES",  f"{stats['total_files']:,}",   "archivos encontrados", BLUE),
        _kpi_card("ESPACIO OCUPADO",   _fmt_size(stats['total_size']), "en disco",             EMERALD),
        _kpi_card("CATEGORÍAS",        str(len(stats['categories'])),  "tipos detectados",     AMBER),
        _kpi_card("TOP EXTENSIÓN",
                  extensions[0]["extension"] if extensions else "—",
                  f"{extensions[0]['count']:,} archivos" if extensions else "",
                  colors.HexColor("#8B5CF6")),
    ]]
    kpi_tbl = Table(kpi_row, colWidths=[W/4]*4, hAlign="CENTER")
    kpi_tbl.setStyle(TableStyle([
        ("LEFTPADDING",  (0,0), (-1,-1), 4),
        ("RIGHTPADDING", (0,0), (-1,-1), 4),
        ("TOPPADDING",   (0,0), (-1,-1), 0),
        ("BOTTOMPADDING",(0,0), (-1,-1), 0),
    ]))
    story.append(kpi_tbl)
    story.append(Spacer(1, 0.65*cm))

    # ── SECCIÓN: Distribución por Categoría ──────────────────────────────────
    story.append(_section_header("Distribución por Categoría", BLUE, W))
    story.append(Spacer(1, 0.25*cm))

    st_cat_name = lambda clr: ParagraphStyle(f"cn{clr}", fontSize=8.5,
                                              fontName="Helvetica-Bold",
                                              textColor=colors.HexColor(clr), leading=11)

    max_size  = max((c["total_size"] for c in stats["categories"]), default=1)
    max_count = max((c["file_count"] for c in stats["categories"]), default=1)
    cat_hdr_p = [
        sty("ch",  8.5, bold=True, color=WHITE, align=TA_LEFT),
        sty("ch2", 8.5, bold=True, color=WHITE, align=TA_CENTER),
        sty("ch3", 8.5, bold=True, color=WHITE, align=TA_CENTER),
        sty("ch4", 8.5, bold=True, color=WHITE, align=TA_CENTER),
        sty("ch5", 8.5, bold=True, color=WHITE, align=TA_CENTER),
        sty("ch6", 8.5, bold=True, color=WHITE, align=TA_CENTER),
    ]
    # Barra cols: 110pt cada una — ancho fijo pasado al Flowable
    BAR_W = W * 0.24
    cat_col_w = [W*0.18, W*0.10, W*0.13, W*0.09, BAR_W, BAR_W]
    cat_rows = [[
        Paragraph("  Categoría",              cat_hdr_p[0]),
        Paragraph("Archivos",                 cat_hdr_p[1]),
        Paragraph("Tamaño total",             cat_hdr_p[2]),
        Paragraph("% tamaño",                 cat_hdr_p[3]),
        Paragraph("Proporción por archivos",  cat_hdr_p[4]),
        Paragraph("Proporción por tamaño",    cat_hdr_p[5]),
    ]]
    for i, c in enumerate(stats["categories"]):
        clr = CAT_COLORS[i % len(CAT_COLORS)]
        ratio_count = c["file_count"] / max_count if max_count > 0 else 0
        ratio_size  = c["total_size"] / max_size  if max_size  > 0 else 0
        cat_rows.append([
            Paragraph(f"  {c['category'].capitalize()}", st_cat_name(clr)),
            Paragraph(f"{c['file_count']:,}", st_ctr),
            Paragraph(_fmt_size(c["total_size"]), st_ctr),
            Paragraph(f"{c['percentage']:.1f}%", st_ctr),
            _Bar(ratio_count, clr, w=BAR_W - 12),
            _Bar(ratio_size,  clr, w=BAR_W - 12),
        ])

    cat_tbl = Table(cat_rows, colWidths=cat_col_w)
    cat_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,0), SLATE),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [WHITE, ALT]),
        ("GRID",          (0,0), (-1,-1), 0.4, BORDER),
        ("TOPPADDING",    (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING",   (0,0), (-1,-1), 6),
        ("RIGHTPADDING",  (0,0), (-1,-1), 6),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
    ]))
    story.append(cat_tbl)
    story.append(Spacer(1, 0.65*cm))

    # ── SECCIÓN: Archivos más grandes ─────────────────────────────────────────
    story.append(_section_header("Archivos más Grandes", EMERALD, W))
    story.append(Spacer(1, 0.25*cm))

    lg_col_w = [0.55*cm, W*0.27, W*0.12, W*0.11, W*0.50 - 0.55*cm]
    lg_hdr_p = sty("lgh", 8.5, bold=True, color=WHITE, align=TA_CENTER)
    lg_rows = [[
        Paragraph("#",           lg_hdr_p),
        Paragraph("Nombre",      lg_hdr_p),
        Paragraph("Tamaño",      lg_hdr_p),
        Paragraph("Modificado",  lg_hdr_p),
        Paragraph("Ruta",        lg_hdr_p),
    ]]
    for f in largest:
        path = f["path"]
        if len(path) > 58: path = "…" + path[-55:]
        rank_color = (["#F59E0B","#94A3B8","#CD7F32"] + ["#64748B"]*17)[f["rank"]-1]
        lg_rows.append([
            Paragraph(str(f["rank"]),
                      ParagraphStyle(f"rk{f['rank']}", fontSize=8.5, fontName="Helvetica-Bold",
                                     textColor=colors.HexColor(rank_color),
                                     alignment=TA_CENTER, leading=11)),
            Paragraph(f["name"],
                      ParagraphStyle("ln", fontSize=8, fontName="Helvetica-Bold",
                                     textColor=TEXT, leading=11)),
            Paragraph(_fmt_size(f["size"]), st_rgt),
            Paragraph(f["modified"], st_muted),
            Paragraph(path, st_cell),
        ])

    lg_tbl = Table(lg_rows, colWidths=lg_col_w, repeatRows=1)
    lg_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,0), SLATE),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [WHITE, ALT]),
        ("GRID",          (0,0), (-1,-1), 0.3, BORDER),
        ("TOPPADDING",    (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ("LEFTPADDING",   (0,0), (-1,-1), 5),
        ("RIGHTPADDING",  (0,0), (-1,-1), 5),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
        # Top 3 highlight subtle
        ("BACKGROUND",    (0,1), (-1,1), colors.HexColor("#FFFBEB")),
        ("BACKGROUND",    (0,2), (-1,2), colors.HexColor("#F9FAFB")),
        ("BACKGROUND",    (0,3), (-1,3), colors.HexColor("#FFF7F0")),
    ]))
    story.append(lg_tbl)
    story.append(Spacer(1, 0.65*cm))

    # ── SECCIÓN: Top Extensiones ──────────────────────────────────────────────
    story.append(_section_header("Top Extensiones de Archivo", AMBER, W))
    story.append(Spacer(1, 0.25*cm))

    # Dos columnas lado a lado (extensiones A y B)
    half = len(extensions) // 2 + len(extensions) % 2
    ext_left  = extensions[:half]
    ext_right = extensions[half:]

    ext_hdr_p = sty("exh", 8.5, bold=True, color=WHITE, align=TA_CENTER)
    COL_W = (W - 0.4*cm) / 2
    sub_col = [COL_W*0.25, COL_W*0.25, COL_W*0.28, COL_W*0.22]

    def _ext_block(ext_list, all_ext):
        rows = [[
            Paragraph("Ext.", ext_hdr_p),
            Paragraph("Archivos", ext_hdr_p),
            Paragraph("Tamaño", ext_hdr_p),
            Paragraph("%", ext_hdr_p),
        ]]
        max_c = max((e["count"] for e in all_ext), default=1)
        for i, e in enumerate(ext_list):
            bar_n = int(e["count"] / max_c * 8)
            clr = CAT_COLORS[i % len(CAT_COLORS)]
            rows.append([
                Paragraph(e["extension"],
                          ParagraphStyle(f"ext{i}", fontSize=8.5, fontName="Helvetica-Bold",
                                         textColor=colors.HexColor(clr),
                                         alignment=TA_CENTER, leading=11)),
                Paragraph(f"{e['count']:,}", st_ctr),
                Paragraph(_fmt_size(e["total_size"]), st_ctr),
                Paragraph(f"{e['percentage']:.1f}%", st_ctr),
            ])
        t = Table(rows, colWidths=sub_col)
        t.setStyle(TableStyle([
            ("BACKGROUND",    (0,0), (-1,0), SLATE2),
            ("ROWBACKGROUNDS",(0,1), (-1,-1), [WHITE, ALT]),
            ("GRID",          (0,0), (-1,-1), 0.4, BORDER),
            ("TOPPADDING",    (0,0), (-1,-1), 5),
            ("BOTTOMPADDING", (0,0), (-1,-1), 5),
            ("LEFTPADDING",   (0,0), (-1,-1), 6),
            ("RIGHTPADDING",  (0,0), (-1,-1), 6),
            ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
        ]))
        return t

    ext_dual = Table(
        [[_ext_block(ext_left, extensions), _ext_block(ext_right, extensions)]],
        colWidths=[COL_W, COL_W],
        hAlign="CENTER",
    )
    ext_dual.setStyle(TableStyle([
        ("LEFTPADDING",  (0,0), (-1,-1), 0),
        ("RIGHTPADDING", (0,0), (-1,-1), 0),
        ("TOPPADDING",   (0,0), (-1,-1), 0),
        ("BOTTOMPADDING",(0,0), (-1,-1), 0),
        ("LINEAFTER",    (0,0), (0,-1), 0.5, BORDER),
    ]))
    story.append(ext_dual)

    # ── FOOTER ────────────────────────────────────────────────────────────────
    def on_page(canvas, doc):
        canvas.saveState()
        # Barra inferior
        canvas.setFillColor(NAVY)
        canvas.rect(0, 0, A4[0], 1.5*cm, fill=1, stroke=0)
        # Línea de acento izquierda
        canvas.setFillColor(BLUE)
        canvas.rect(0, 0, 0.35*cm, 1.5*cm, fill=1, stroke=0)
        # Texto footer izquierdo
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(colors.HexColor("#64748B"))
        canvas.drawString(0.65*cm, 0.85*cm, "Smart File Organizer")
        canvas.setFillColor(colors.HexColor("#334155"))
        canvas.drawString(0.65*cm, 0.4*cm, f"Scan ID: {scan_id}")
        # Texto footer derecho
        canvas.setFillColor(colors.HexColor("#475569"))
        canvas.drawRightString(A4[0] - 2*cm, 0.85*cm,
            datetime.now().strftime("%d/%m/%Y"))
        canvas.setFillColor(colors.HexColor("#3B82F6"))
        canvas.drawRightString(A4[0] - 2*cm, 0.4*cm,
            f"Página {doc.page}")
        # Línea azul top
        canvas.setFillColor(BLUE)
        canvas.rect(0, A4[1] - 0.2*cm, A4[0], 0.2*cm, fill=1, stroke=0)
        canvas.restoreState()

    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    buf.seek(0)
    filename = f"estadisticas_{scan_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return StreamingResponse(iter([buf.read()]), media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'})


# ── Stats Excel — rediseño premium ───────────────────────────────────────────

def _export_stats_excel(scan_id: str) -> StreamingResponse:
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter
        from openpyxl.chart import BarChart, Reference
        from openpyxl.chart import PieChart as XLPie
        from openpyxl.chart.series import DataPoint
    except ImportError:
        raise HTTPException(500, detail="openpyxl no instalado.")

    stats, largest, extensions = _get_stats_data(scan_id)

    # Paleta premium
    C_NAVY    = "0F172A"
    C_SLATE   = "1E293B"
    C_SLATE2  = "334155"
    C_BLUE    = "3B82F6"
    C_EMLD    = "10B981"
    C_AMBER   = "F59E0B"
    C_VIOLET  = "8B5CF6"
    C_ALT     = "F8FAFC"
    C_ALT2    = "EFF6FF"
    C_FG      = "FFFFFF"
    C_BORDER  = "E2E8F0"
    C_TEXT    = "1E293B"
    C_MUTED   = "64748B"
    C_BLUE_LT = "BFDBFE"
    CAT_COLORS = ["3B82F6","10B981","F59E0B","EF4444",
                  "8B5CF6","EC4899","14B8A6","F97316","6366F1","84CC16"]

    def _brd(color=C_BORDER, style="thin"):
        s = Side(style=style, color=color)
        return Border(left=s, right=s, top=s, bottom=s)

    def _hdr(cell, text, bg=C_SLATE, fg=C_FG, size=10, bold=True, align="center"):
        cell.value     = text
        cell.font      = Font(name="Calibri", bold=bold, color=fg, size=size)
        cell.fill      = PatternFill("solid", fgColor=bg)
        cell.alignment = Alignment(horizontal=align, vertical="center", wrap_text=True)
        cell.border    = _brd()

    def _data(cell, value, bg=C_ALT, bold=False, align="left", size=10,
              color=C_TEXT, number_format=None):
        cell.value     = value
        cell.font      = Font(name="Calibri", bold=bold, color=color, size=size)
        cell.fill      = PatternFill("solid", fgColor=bg)
        cell.alignment = Alignment(horizontal=align, vertical="center", indent=(1 if align=="left" else 0))
        cell.border    = _brd()
        if number_format: cell.number_format = number_format

    wb = openpyxl.Workbook()

    # ═══════════════════════════════════════════════════════════════════════════
    # HOJA 1 — RESUMEN
    # ═══════════════════════════════════════════════════════════════════════════
    ws = wb.active
    ws.title = "Resumen"
    ws.sheet_view.showGridLines = False
    ws.sheet_view.zoomScale = 100
    ws.sheet_properties.tabColor = C_BLUE

    # Título principal
    ws.merge_cells("A1:G1")
    ws["A1"].value     = "SMART FILE ORGANIZER — Estadísticas"
    ws["A1"].font      = Font(name="Calibri", size=18, bold=True, color=C_FG)
    ws["A1"].fill      = PatternFill("solid", fgColor=C_NAVY)
    ws["A1"].alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 44

    ws.merge_cells("A2:G2")
    ws["A2"].value     = "Informe de Estadísticas de Archivo"
    ws["A2"].font      = Font(name="Calibri", size=10, color="93C5FD")
    ws["A2"].fill      = PatternFill("solid", fgColor=C_NAVY)
    ws["A2"].alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[2].height = 20

    ws.merge_cells("A3:G3")
    ws["A3"].value     = f"Scan ID: {scan_id}   ·   Generado el {datetime.now().strftime('%d/%m/%Y — %H:%M:%S')}"
    ws["A3"].font      = Font(name="Calibri", size=8.5, color=C_MUTED, italic=True)
    ws["A3"].fill      = PatternFill("solid", fgColor="0D1929")
    ws["A3"].alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[3].height = 16

    ws.append([]); ws.row_dimensions[4].height = 8

    # ── KPI Cards (4 tarjetas en una fila de 2+2 columnas cada una) ──────────
    # Tarjeta 1: Total archivos
    def _kpi_block(ws, start_col, label, value, subtitle, accent_color, label_color="93C5FD"):
        sc = start_col
        # Fila etiqueta
        r = 5
        c = ws.cell(r, sc); c.value = label
        c.font = Font(name="Calibri", size=8, color=label_color, bold=True)
        c.fill = PatternFill("solid", fgColor=C_SLATE)
        c.alignment = Alignment(horizontal="center", vertical="center")
        c.border = Border(top=Side(style="thin", color=C_SLATE),
                         left=Side(style="thin", color=C_SLATE),
                         right=Side(style="thin", color=C_SLATE))
        ws.merge_cells(start_row=r, start_column=sc, end_row=r, end_column=sc+1)

        # Fila valor
        r = 6
        c = ws.cell(r, sc); c.value = value
        c.font = Font(name="Calibri", size=16, color=C_FG, bold=True)
        c.fill = PatternFill("solid", fgColor=C_SLATE)
        c.alignment = Alignment(horizontal="center", vertical="center")
        c.border = Border(left=Side(style="thin", color=C_SLATE),
                         right=Side(style="thin", color=C_SLATE))
        ws.merge_cells(start_row=r, start_column=sc, end_row=r, end_column=sc+1)

        # Fila subtítulo
        r = 7
        c = ws.cell(r, sc); c.value = subtitle
        c.font = Font(name="Calibri", size=7.5, color="CBD5E1")
        c.fill = PatternFill("solid", fgColor=C_SLATE)
        c.alignment = Alignment(horizontal="center", vertical="center")
        c.border = Border(bottom=Side(style="medium", color=accent_color),
                         left=Side(style="thin", color=C_SLATE),
                         right=Side(style="thin", color=C_SLATE))
        ws.merge_cells(start_row=r, start_column=sc, end_row=r, end_column=sc+1)

    top_ext = extensions[0]["extension"] if extensions else "—"
    top_ext_cnt = f"{extensions[0]['count']:,} archivos" if extensions else ""
    _kpi_block(ws, 1, "ARCHIVOS TOTALES",   f"{stats['total_files']:,}",       "archivos encontrados", C_BLUE)
    _kpi_block(ws, 3, "ESPACIO OCUPADO",    _fmt_size(stats['total_size']),     "en disco",             C_EMLD,  label_color="6EE7B7")
    _kpi_block(ws, 5, "CATEGORÍAS",         str(len(stats['categories'])),      "tipos detectados",     C_AMBER, label_color="FCD34D")
    _kpi_block(ws, 7, "TOP EXTENSIÓN",      top_ext,                           top_ext_cnt,            C_VIOLET, label_color="C4B5FD")

    ws.row_dimensions[5].height = 18
    ws.row_dimensions[6].height = 30
    ws.row_dimensions[7].height = 16

    ws.append([]); ws.row_dimensions[8].height = 10

    # ── Sección: Distribución por categoría ──────────────────────────────────
    r_sec = 9
    ws.merge_cells(f"A{r_sec}:H{r_sec}")
    ws[f"A{r_sec}"].value     = "  DISTRIBUCIÓN POR CATEGORÍA"
    ws[f"A{r_sec}"].font      = Font(name="Calibri", size=10, bold=True, color=C_FG)
    ws[f"A{r_sec}"].fill      = PatternFill("solid", fgColor=C_BLUE)
    ws[f"A{r_sec}"].alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws.row_dimensions[r_sec].height = 22

    r_cat_hdr = r_sec + 1
    for col, txt in enumerate(["Categoría","Archivos","Tamaño total",
                                "% tamaño","% archivos","Barras proporcionales (tamaño)","",""], 1):
        _hdr(ws.cell(r_cat_hdr, col), txt, bg=C_SLATE2)
    ws.row_dimensions[r_cat_hdr].height = 22

    cat_start_row = r_cat_hdr + 1
    total_files_n = max(stats["total_files"], 1)
    max_cat_size  = max((c["total_size"] for c in stats["categories"]), default=1)
    max_cat_count = max((c["file_count"] for c in stats["categories"]), default=1)
    for i, c in enumerate(stats["categories"]):
        r = cat_start_row + i
        pct_files = c["file_count"] / total_files_n * 100
        # Barras: cadena de bloques proporcionales a cada métrica
        n_size  = int(c["total_size"]  / max_cat_size  * 24) if max_cat_size  > 0 else 0
        n_count = int(c["file_count"]  / max_cat_count * 24) if max_cat_count > 0 else 0
        bar_size  = "█" * n_size  + "░" * (24 - n_size)
        bar_count = "█" * n_count + "░" * (24 - n_count)
        clr = CAT_COLORS[i % len(CAT_COLORS)]
        bg = C_ALT if i % 2 == 0 else C_FG

        ws.cell(r, 1).value = f"  {c['category'].capitalize()}"
        ws.cell(r, 1).font  = Font(name="Calibri", bold=True, size=10, color=clr)
        ws.cell(r, 1).fill  = PatternFill("solid", fgColor=bg)
        ws.cell(r, 1).border = _brd()
        ws.cell(r, 1).alignment = Alignment(vertical="center", indent=1)

        for col, (val, fmt_align) in enumerate([
            (c["file_count"], "center"),
            (_fmt_size(c["total_size"]), "center"),
            (f"{c['percentage']:.1f}%", "center"),
            (f"{pct_files:.1f}%", "center"),
            (bar_size, "left"),
            ("", "center"),
            ("", "center"),
        ], 2):
            cell = ws.cell(r, col)
            cell.value     = val
            cell.font      = Font(name="Calibri", size=10,
                                  color=(clr if col == 6 else C_TEXT))
            cell.fill      = PatternFill("solid", fgColor=bg)
            cell.border    = _brd()
            cell.alignment = Alignment(horizontal=fmt_align, vertical="center")
        ws.row_dimensions[r].height = 20

    cat_end_row = cat_start_row + len(stats["categories"]) - 1

    # Pie chart a la derecha
    pie = XLPie()
    pie.title  = "Distribución por categoría"
    pie.style  = 10
    pie.add_data(Reference(ws, min_col=3, min_row=r_cat_hdr, max_row=cat_end_row),
                 titles_from_data=True)
    pie.set_categories(Reference(ws, min_col=1, min_row=cat_start_row, max_row=cat_end_row))
    pie.width  = 14
    pie.height = 12
    ws.add_chart(pie, "J9")

    ws.append([]); ws.row_dimensions[cat_end_row + 1].height = 10

    for col, w in enumerate([22, 12, 16, 12, 12, 30, 8, 8], 1):
        ws.column_dimensions[get_column_letter(col)].width = w

    # ═══════════════════════════════════════════════════════════════════════════
    # HOJA 2 — ARCHIVOS MÁS GRANDES
    # ═══════════════════════════════════════════════════════════════════════════
    ws2 = wb.create_sheet("Archivos más grandes")
    ws2.sheet_view.showGridLines = False
    ws2.sheet_properties.tabColor = C_EMLD

    ws2.merge_cells("A1:F1")
    ws2["A1"].value     = "ARCHIVOS MÁS GRANDES"
    ws2["A1"].font      = Font(name="Calibri", size=14, bold=True, color=C_FG)
    ws2["A1"].fill      = PatternFill("solid", fgColor=C_NAVY)
    ws2["A1"].alignment = Alignment(horizontal="center", vertical="center")
    ws2.row_dimensions[1].height = 36

    ws2.merge_cells("A2:F2")
    ws2["A2"].value     = f"Top 20 archivos por tamaño  ·  Scan {scan_id}"
    ws2["A2"].font      = Font(name="Calibri", size=9, color="93C5FD")
    ws2["A2"].fill      = PatternFill("solid", fgColor=C_NAVY)
    ws2["A2"].alignment = Alignment(horizontal="center", vertical="center")
    ws2.row_dimensions[2].height = 18
    ws2.append([])
    ws2.row_dimensions[3].height = 6

    headers2 = ["#", "Nombre del archivo", "Tamaño", "Modificado", "Ruta completa", ""]
    for col, h in enumerate(headers2, 1):
        _hdr(ws2.cell(4, col), h, bg=C_SLATE)
    ws2.row_dimensions[4].height = 22
    ws2.freeze_panes = "A5"

    RANK_COLORS = [C_AMBER, "94A3B8", "CD7F32"] + [C_MUTED] * 17
    for i, f in enumerate(largest):
        r = i + 5
        bg = C_ALT if i % 2 == 0 else C_FG
        if i == 0: bg = "FFFBEB"
        elif i == 1: bg = "F9FAFB"
        elif i == 2: bg = "FFF7F0"

        ws2.cell(r, 1).value     = f["rank"]
        ws2.cell(r, 1).font      = Font(name="Calibri", bold=True, size=11,
                                        color=RANK_COLORS[i])
        ws2.cell(r, 1).fill      = PatternFill("solid", fgColor=bg)
        ws2.cell(r, 1).border    = _brd()
        ws2.cell(r, 1).alignment = Alignment(horizontal="center", vertical="center")

        ws2.cell(r, 2).value     = f["name"]
        ws2.cell(r, 2).font      = Font(name="Calibri", bold=True, size=10, color=C_TEXT)
        ws2.cell(r, 2).fill      = PatternFill("solid", fgColor=bg)
        ws2.cell(r, 2).border    = _brd()
        ws2.cell(r, 2).alignment = Alignment(vertical="center", indent=1)

        ws2.cell(r, 3).value     = _fmt_size(f["size"])
        ws2.cell(r, 3).font      = Font(name="Calibri", size=10, color=C_TEXT)
        ws2.cell(r, 3).fill      = PatternFill("solid", fgColor=bg)
        ws2.cell(r, 3).border    = _brd()
        ws2.cell(r, 3).alignment = Alignment(horizontal="right", vertical="center")

        ws2.cell(r, 4).value     = f["modified"]
        ws2.cell(r, 4).font      = Font(name="Calibri", size=9, color=C_MUTED)
        ws2.cell(r, 4).fill      = PatternFill("solid", fgColor=bg)
        ws2.cell(r, 4).border    = _brd()
        ws2.cell(r, 4).alignment = Alignment(horizontal="center", vertical="center")

        ws2.cell(r, 5).value     = f["path"]
        ws2.cell(r, 5).font      = Font(name="Calibri", size=8.5, color=C_MUTED)
        ws2.cell(r, 5).fill      = PatternFill("solid", fgColor=bg)
        ws2.cell(r, 5).border    = _brd()
        ws2.cell(r, 5).alignment = Alignment(vertical="center", indent=1)

        ws2.cell(r, 6).fill   = PatternFill("solid", fgColor=bg)
        ws2.cell(r, 6).border = _brd()
        ws2.row_dimensions[r].height = 22

    for col, w in enumerate([6, 32, 14, 14, 58, 4], 1):
        ws2.column_dimensions[get_column_letter(col)].width = w

    # ═══════════════════════════════════════════════════════════════════════════
    # HOJA 3 — TOP EXTENSIONES
    # ═══════════════════════════════════════════════════════════════════════════
    ws3 = wb.create_sheet("Top extensiones")
    ws3.sheet_view.showGridLines = False
    ws3.sheet_properties.tabColor = C_AMBER

    ws3.merge_cells("A1:E1")
    ws3["A1"].value     = "TOP EXTENSIONES DE ARCHIVO"
    ws3["A1"].font      = Font(name="Calibri", size=14, bold=True, color=C_FG)
    ws3["A1"].fill      = PatternFill("solid", fgColor=C_NAVY)
    ws3["A1"].alignment = Alignment(horizontal="center", vertical="center")
    ws3.row_dimensions[1].height = 36

    ws3.merge_cells("A2:E2")
    ws3["A2"].value     = f"Top 20 extensiones por cantidad de archivos  ·  Scan {scan_id}"
    ws3["A2"].font      = Font(name="Calibri", size=9, color="93C5FD")
    ws3["A2"].fill      = PatternFill("solid", fgColor=C_NAVY)
    ws3["A2"].alignment = Alignment(horizontal="center", vertical="center")
    ws3.row_dimensions[2].height = 18
    ws3.append([])
    ws3.row_dimensions[3].height = 6

    headers3 = ["Extensión", "Archivos", "Tamaño total", "%", ""]
    for col, h in enumerate(headers3, 1):
        _hdr(ws3.cell(4, col), h, bg=C_SLATE)
    ws3.row_dimensions[4].height = 22
    ws3.freeze_panes = "A5"

    max_ext_count = max((e["count"] for e in extensions), default=1)
    for i, e in enumerate(extensions):
        r = i + 5
        clr = CAT_COLORS[i % len(CAT_COLORS)]
        bg  = C_ALT if i % 2 == 0 else C_FG
        bar_n = int(e["count"] / max_ext_count * 20)
        bar   = "█" * bar_n + "░" * (20 - bar_n)

        ws3.cell(r, 1).value     = e["extension"]
        ws3.cell(r, 1).font      = Font(name="Calibri", bold=True, size=11, color=clr)
        ws3.cell(r, 1).fill      = PatternFill("solid", fgColor=bg)
        ws3.cell(r, 1).border    = _brd()
        ws3.cell(r, 1).alignment = Alignment(horizontal="center", vertical="center")

        ws3.cell(r, 2).value     = e["count"]
        ws3.cell(r, 2).font      = Font(name="Calibri", size=10, color=C_TEXT)
        ws3.cell(r, 2).fill      = PatternFill("solid", fgColor=bg)
        ws3.cell(r, 2).border    = _brd()
        ws3.cell(r, 2).alignment = Alignment(horizontal="center", vertical="center")

        ws3.cell(r, 3).value     = _fmt_size(e["total_size"])
        ws3.cell(r, 3).font      = Font(name="Calibri", size=10, color=C_TEXT)
        ws3.cell(r, 3).fill      = PatternFill("solid", fgColor=bg)
        ws3.cell(r, 3).border    = _brd()
        ws3.cell(r, 3).alignment = Alignment(horizontal="right", vertical="center")

        ws3.cell(r, 4).value     = f"{e['percentage']:.1f}%"
        ws3.cell(r, 4).font      = Font(name="Calibri", size=10, color=C_TEXT)
        ws3.cell(r, 4).fill      = PatternFill("solid", fgColor=bg)
        ws3.cell(r, 4).border    = _brd()
        ws3.cell(r, 4).alignment = Alignment(horizontal="center", vertical="center")

        ws3.cell(r, 5).value     = bar
        ws3.cell(r, 5).font      = Font(name="Calibri", size=9, color=clr)
        ws3.cell(r, 5).fill      = PatternFill("solid", fgColor=bg)
        ws3.cell(r, 5).border    = _brd()
        ws3.cell(r, 5).alignment = Alignment(vertical="center")
        ws3.row_dimensions[r].height = 20

    for col, w in enumerate([14, 12, 16, 10, 26], 1):
        ws3.column_dimensions[get_column_letter(col)].width = w

    # Bar chart
    bar = BarChart()
    bar.type    = "col"
    bar.title   = "Top extensiones — Cantidad de archivos"
    bar.style   = 10
    bar.y_axis.title = "Archivos"
    bar.grouping = "clustered"
    bar.add_data(
        Reference(ws3, min_col=2, min_row=4, max_row=min(len(extensions)+4, 14)),
        titles_from_data=True)
    bar.set_categories(
        Reference(ws3, min_col=1, min_row=5, max_row=min(len(extensions)+4, 14)))
    bar.width  = 20
    bar.height = 14
    ws3.add_chart(bar, "G4")

    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    filename = f"estadisticas_{scan_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return StreamingResponse(iter([buf.read()]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'})


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/{scan_id}")
def export_scan(
    scan_id: str,
    format: Literal["pdf", "excel", "csv"] = Query(default="pdf"),
) -> StreamingResponse:
    logger.info(f"Export requested: scan_id={scan_id} format={format}")
    if format == "pdf":   return _export_pdf(scan_id)
    if format == "excel": return _export_excel(scan_id)
    return _export_csv(scan_id)


@router.get("/{scan_id}/stats")
def export_stats(
    scan_id: str,
    format: Literal["pdf", "excel"] = Query(default="pdf"),
) -> StreamingResponse:
    logger.info(f"Stats export: scan_id={scan_id} format={format}")
    if format == "excel": return _export_stats_excel(scan_id)
    return _export_stats_pdf(scan_id)
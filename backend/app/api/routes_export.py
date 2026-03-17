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
    """Itera archivos en batches desde SQLite — sin cargarlos todos en RAM."""
    try:
        with get_db_cursor() as cursor:
            cursor.execute(
                "SELECT name, path, size, extension, category, modified "
                "FROM scan_files WHERE scan_id=? ORDER BY path",
                (scan_id,)
            )
            while True:
                rows = cursor.fetchmany(2000)
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
    except Exception as e:
        raise HTTPException(500, detail=f"Error leyendo archivos: {e}")


def _get_categories(scan_id: str, total_size: int) -> list[dict]:
    """Categorías agregadas con GROUP BY — O(1) en memoria."""
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


# ── Excel scan (write_only + estilos pre-creados) ─────────────────────────────

def _export_excel(scan_id: str) -> StreamingResponse:
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter
        from openpyxl.cell import WriteOnlyCell
        from openpyxl.worksheet.dimensions import ColumnDimension
    except ImportError:
        raise HTTPException(500, detail="openpyxl no instalado. Ejecuta: pip install openpyxl")

    meta       = _get_meta(scan_id)
    categories = _get_categories(scan_id, meta["total_size"])

    C_HEADER = "1E3A5F"; C_ACCENT = "2E86AB"; C_ALT = "F0F4F8"
    C_FG = "FFFFFF";     C_LABEL = "E8EEF4";  C_BORDER = "CCCCCC"
    thin = Side(style="thin", color=C_BORDER)
    brd  = Border(left=thin, right=thin, top=thin, bottom=thin)

    wb = openpyxl.Workbook(write_only=False)

    # ── Hoja Resumen (pequeña, modo normal) ───────────────────────────────────
    ws_sum = wb.active; ws_sum.title = "Resumen"
    ws_sum.sheet_view.showGridLines = False

    ws_sum.merge_cells("A1:D1")
    ws_sum["A1"].value     = "Smart File Organizer — Reporte de Escaneo"
    ws_sum["A1"].font      = Font(name="Calibri", size=16, bold=True, color=C_FG)
    ws_sum["A1"].fill      = PatternFill("solid", fgColor=C_HEADER)
    ws_sum["A1"].alignment = Alignment(horizontal="center", vertical="center")
    ws_sum.row_dimensions[1].height = 36
    ws_sum.merge_cells("A2:D2")
    ws_sum["A2"].value     = f"Generado el {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"
    ws_sum["A2"].font      = Font(name="Calibri", size=10, color="666666")
    ws_sum["A2"].fill      = PatternFill("solid", fgColor="EAF0F6")
    ws_sum["A2"].alignment = Alignment(horizontal="center")
    ws_sum.row_dimensions[2].height = 20
    ws_sum.append([])

    for label, value in [
        ("Ruta escaneada",    meta["root_path"]),
        ("Fecha de escaneo",  str(meta["scanned_at"])[:19].replace("T", " ")),
        ("Total de archivos", f"{meta['total_files']:,}"),
        ("Tamaño total",      _fmt_size(meta["total_size"])),
        ("Duración",          f"{meta['duration_sec']:.2f} segundos"),
        ("Scan ID",           meta["scan_id"]),
    ]:
        ws_sum.append([label, value])
        r = ws_sum.max_row
        ws_sum[f"A{r}"].font   = Font(name="Calibri", bold=True, size=11)
        ws_sum[f"A{r}"].fill   = PatternFill("solid", fgColor=C_LABEL)
        ws_sum[f"A{r}"].border = brd
        ws_sum[f"B{r}"].font   = Font(name="Calibri", size=11)
        ws_sum[f"B{r}"].border = brd

    ws_sum.append([])
    ws_sum.append(["Categoría", "Archivos", "Tamaño total", "% del total"])
    hr = ws_sum.max_row
    for col in range(1, 5):
        c = ws_sum.cell(hr, col)
        c.font = Font(name="Calibri", bold=True, color=C_FG, size=11)
        c.fill = PatternFill("solid", fgColor=C_ACCENT)
        c.alignment = Alignment(horizontal="center"); c.border = brd

    total_files_n = max(meta["total_files"], 1)
    for i, cat in enumerate(categories):
        ws_sum.append([cat["category"].capitalize(), cat["file_count"],
                       _fmt_size(cat["total_size"]),
                       f"{cat['file_count'] / total_files_n * 100:.1f}%"])
        r = ws_sum.max_row
        fill = PatternFill("solid", fgColor=C_ALT if i % 2 == 0 else "FFFFFF")
        for col in range(1, 5):
            c = ws_sum.cell(r, col)
            c.fill = fill; c.font = Font(name="Calibri", size=10); c.border = brd
            if col == 2: c.alignment = Alignment(horizontal="center")

    for col, w in zip("ABCD", [22, 40, 18, 14]):
        ws_sum.column_dimensions[col].width = w

    # ── Hoja Archivos (write_only = rápido para grandes volúmenes) ────────────
    ws_files = wb.create_sheet("Archivos")
    headers  = ["#", "Nombre", "Extensión", "Categoría",
                "Tamaño (bytes)", "Tamaño", "Ruta", "Modificado"]

    # Cabecera
    hdr_row = []
    for h in headers:
        c = WriteOnlyCell(ws_files, value=h)
        c.font = Font(name="Calibri", bold=True, color=C_FG, size=11)
        c.fill = PatternFill("solid", fgColor=C_HEADER)
        c.alignment = Alignment(horizontal="center"); c.border = brd
        hdr_row.append(c)
    ws_files.append(hdr_row)

    # Estilos pre-creados una sola vez
    alt_fill = PatternFill("solid", fgColor=C_ALT)
    wht_fill = PatternFill("solid", fgColor="FFFFFF")
    body_fnt = Font(name="Calibri", size=9)
    ctr_aln  = Alignment(horizontal="center")

    for i, f in enumerate(_iter_files(scan_id), 1):
        fill = alt_fill if i % 2 == 0 else wht_fill
        size = f["size"]
        row  = []
        for val, center in [
            (i, True), (f["name"], False), (f["extension"], True),
            (f["category"], True), (size, True), (_fmt_size(size), True),
            (f["path"], False), (f["modified"][:19] if f["modified"] else "", True),
        ]:
            c = WriteOnlyCell(ws_files, value=val)
            c.font = body_fnt; c.fill = fill; c.border = brd
            if center: c.alignment = ctr_aln
            row.append(c)
        ws_files.append(row)

    for col_idx, w in enumerate([6, 30, 10, 14, 16, 12, 55, 20], 1):
        col_letter = get_column_letter(col_idx)
        ws_files.column_dimensions[col_letter] = ColumnDimension(
            ws_files, index=col_letter, width=w)

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
                                         Paragraph, Spacer, HRFlowable, PageBreak)
        from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    except ImportError:
        raise HTTPException(500, detail="reportlab no instalado. Ejecuta: pip install reportlab")

    meta       = _get_meta(scan_id)
    categories = _get_categories(scan_id, meta["total_size"])

    DARK_BLUE = colors.HexColor("#1E3A5F"); MED_BLUE  = colors.HexColor("#2E86AB")
    LIGHT_BLU = colors.HexColor("#EAF0F6"); ALT_ROW   = colors.HexColor("#F4F8FC")
    WHITE     = colors.white;               GRAY      = colors.HexColor("#555555")
    BORDER    = colors.HexColor("#CCCCCC")

    style_title   = ParagraphStyle("t",   fontSize=22, fontName="Helvetica-Bold",
                                    textColor=WHITE, alignment=TA_CENTER, leading=28)
    style_sub     = ParagraphStyle("s",   fontSize=10, fontName="Helvetica",
                                    textColor=GRAY, alignment=TA_CENTER, leading=14)
    style_section = ParagraphStyle("sec", fontSize=13, fontName="Helvetica-Bold",
                                    textColor=DARK_BLUE, leading=18, spaceBefore=10)
    style_cell    = ParagraphStyle("c",   fontSize=7.5, fontName="Helvetica",
                                    leading=10, wordWrap="CJK")
    style_center  = ParagraphStyle("cc",  fontSize=7.5, fontName="Helvetica",
                                    leading=10, alignment=TA_CENTER)
    style_right   = ParagraphStyle("cr",  fontSize=7.5, fontName="Helvetica",
                                    leading=10, alignment=TA_RIGHT)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4),
        leftMargin=1.5*cm, rightMargin=1.5*cm,
        topMargin=2*cm, bottomMargin=2*cm,
        title="Smart File Organizer Report")
    story = []

    hdr = Table([[Paragraph("Smart File Organizer — Reporte de Escaneo", style_title)]],
                colWidths=[doc.width])
    hdr.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), DARK_BLUE),
        ("TOPPADDING", (0,0), (-1,-1), 14), ("BOTTOMPADDING", (0,0), (-1,-1), 14),
    ]))
    story.append(hdr)
    story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph(
        f"Generado el {datetime.now().strftime('%d/%m/%Y a las %H:%M:%S')}", style_sub))
    story.append(Spacer(1, 0.5*cm))

    story.append(Paragraph("Información del Escaneo", style_section))
    story.append(HRFlowable(width="100%", thickness=1, color=MED_BLUE, spaceAfter=6))
    hw = doc.width / 2
    sum_tbl = Table([
        ["Campo", "Valor"],
        ["Ruta escaneada",    meta["root_path"]],
        ["Fecha de escaneo",  str(meta["scanned_at"])[:19].replace("T", " ")],
        ["Total de archivos", f"{meta['total_files']:,}"],
        ["Tamaño total",      _fmt_size(meta["total_size"])],
        ["Duración",          f"{meta['duration_sec']:.2f}s"],
        ["Scan ID",           meta["scan_id"]],
    ], colWidths=[hw*0.35, hw*0.65])
    sum_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,0), MED_BLUE), ("TEXTCOLOR", (0,0), (-1,0), WHITE),
        ("FONTNAME",      (0,0), (-1,0), "Helvetica-Bold"), ("FONTSIZE", (0,0), (-1,0), 10),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [WHITE, LIGHT_BLU]),
        ("FONTNAME",      (0,1), (-1,-1), "Helvetica"), ("FONTSIZE", (0,1), (-1,-1), 9),
        ("FONTNAME",      (0,1), (0,-1),  "Helvetica-Bold"),
        ("GRID",          (0,0), (-1,-1), 0.5, BORDER),
        ("TOPPADDING",    (0,0), (-1,-1), 6), ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ("LEFTPADDING",   (0,0), (-1,-1), 10), ("RIGHTPADDING", (0,0), (-1,-1), 10),
    ]))
    story.append(sum_tbl); story.append(Spacer(1, 0.8*cm))

    story.append(Paragraph("Distribución por Categoría", style_section))
    story.append(HRFlowable(width="100%", thickness=1, color=MED_BLUE, spaceAfter=6))
    total_files_n = max(meta["total_files"], 1)
    cat_rows = [["Categoría", "Archivos", "Tamaño total", "% del total"]] + [
        [c["category"].capitalize(), f"{c['file_count']:,}",
         _fmt_size(c["total_size"]),
         f"{c['file_count'] / total_files_n * 100:.1f}%"]
        for c in categories
    ]
    col_w = doc.width / 4
    cat_tbl = Table(cat_rows, colWidths=[col_w]*4)
    cat_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,0), MED_BLUE), ("TEXTCOLOR", (0,0), (-1,0), WHITE),
        ("FONTNAME",      (0,0), (-1,0), "Helvetica-Bold"), ("FONTSIZE", (0,0), (-1,0), 10),
        ("ALIGN",         (0,0), (-1,0), "CENTER"),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [WHITE, ALT_ROW]),
        ("FONTNAME",      (0,1), (-1,-1), "Helvetica"), ("FONTSIZE", (0,1), (-1,-1), 9),
        ("ALIGN",         (1,1), (-1,-1), "CENTER"),
        ("GRID",          (0,0), (-1,-1), 0.5, BORDER),
        ("TOPPADDING",    (0,0), (-1,-1), 5), ("BOTTOMPADDING", (0,0), (-1,-1), 5),
    ]))
    story.append(cat_tbl)

    # Archivos: leer en batches, máx 5000 en PDF
    MAX_FILES_IN_PDF = 5000
    story.append(PageBreak())
    title_txt = (f"Lista de Archivos (primeros {MAX_FILES_IN_PDF:,} de {meta['total_files']:,})"
                 if meta["total_files"] > MAX_FILES_IN_PDF else "Lista de Archivos")
    story.append(Paragraph(title_txt, style_section))
    story.append(HRFlowable(width="100%", thickness=1, color=MED_BLUE, spaceAfter=6))

    file_rows = [["#", "Nombre", "Extensión", "Categoría", "Tamaño", "Modificado", "Ruta"]]
    count = 0
    for f in _iter_files(scan_id):
        if count >= MAX_FILES_IN_PDF: break
        path = f["path"]
        if len(path) > 70: path = "…" + path[-67:]
        file_rows.append([
            Paragraph(str(count + 1), style_center),
            Paragraph(f["name"], style_cell),
            Paragraph(f["extension"], style_center),
            Paragraph(f["category"], style_center),
            Paragraph(_fmt_size(f["size"]), style_right),
            Paragraph(f["modified"][:10] if f["modified"] else "", style_center),
            Paragraph(path, style_cell),
        ])
        count += 1

    c_widths = [1.0*cm, 5.5*cm, 1.8*cm, 2.5*cm, 2.0*cm, 2.5*cm, None]
    c_widths[-1] = doc.width - sum(w for w in c_widths if w)
    files_tbl = Table(file_rows, colWidths=c_widths, repeatRows=1)
    files_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,0), DARK_BLUE), ("TEXTCOLOR", (0,0), (-1,0), WHITE),
        ("FONTNAME",      (0,0), (-1,0), "Helvetica-Bold"), ("FONTSIZE", (0,0), (-1,0), 8),
        ("ALIGN",         (0,0), (-1,0), "CENTER"), ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [WHITE, ALT_ROW]),
        ("GRID",          (0,0), (-1,-1), 0.3, BORDER),
        ("TOPPADDING",    (0,0), (-1,-1), 3), ("BOTTOMPADDING", (0,0), (-1,-1), 3),
        ("LEFTPADDING",   (0,0), (-1,-1), 4), ("RIGHTPADDING", (0,0), (-1,-1), 4),
    ]))
    story.append(files_tbl)

    def on_page(canvas, doc):
        canvas.saveState(); canvas.setFont("Helvetica", 8); canvas.setFillColor(GRAY)
        canvas.drawString(1.5*cm, 1*cm,
            f"Smart File Organizer  •  Scan {scan_id}  •  {datetime.now().strftime('%d/%m/%Y')}")
        canvas.drawRightString(doc.pagesize[0] - 1.5*cm, 1*cm, f"Página {doc.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    buf.seek(0)
    filename = f"scan_{scan_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return StreamingResponse(iter([buf.read()]), media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'})


# ── Stats data (SQL puro) ─────────────────────────────────────────────────────

def _get_stats_data(scan_id: str) -> tuple[dict, list[dict], list[dict]]:
    """Estadísticas con GROUP BY — O(1) en memoria, funciona post-reinicio."""
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


# ── Stats PDF ─────────────────────────────────────────────────────────────────

def _export_stats_pdf(scan_id: str) -> StreamingResponse:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                         Paragraph, Spacer, HRFlowable)
        from reportlab.lib.enums import TA_CENTER, TA_RIGHT
        from reportlab.graphics.shapes import Drawing
        from reportlab.graphics.charts.piecharts import Pie
    except ImportError:
        raise HTTPException(500, detail="reportlab no instalado. Ejecuta: pip install reportlab")

    stats, largest, extensions = _get_stats_data(scan_id)

    DARK_BLUE = colors.HexColor("#1E3A5F"); MED_BLUE  = colors.HexColor("#2E86AB")
    LIGHT_BLU = colors.HexColor("#EAF0F6"); ALT_ROW   = colors.HexColor("#F4F8FC")
    WHITE     = colors.white;               GRAY      = colors.HexColor("#555555")
    BORDER    = colors.HexColor("#CCCCCC")
    CHART_CLR = ["#3B82F6","#10B981","#F59E0B","#EF4444",
                 "#8B5CF6","#EC4899","#14B8A6","#F97316","#6366F1","#84CC16"]

    style_title   = ParagraphStyle("t",   fontSize=20, fontName="Helvetica-Bold",
                                    textColor=WHITE, alignment=TA_CENTER, leading=26)
    style_sub     = ParagraphStyle("s",   fontSize=9,  fontName="Helvetica",
                                    textColor=GRAY, alignment=TA_CENTER)
    style_section = ParagraphStyle("sec", fontSize=13, fontName="Helvetica-Bold",
                                    textColor=DARK_BLUE, spaceBefore=10, leading=18)
    style_cell    = ParagraphStyle("c",   fontSize=8.5, fontName="Helvetica", leading=11)
    style_center  = ParagraphStyle("cc",  fontSize=8.5, fontName="Helvetica",
                                    alignment=TA_CENTER, leading=11)
    style_right   = ParagraphStyle("cr",  fontSize=8.5, fontName="Helvetica",
                                    alignment=TA_RIGHT, leading=11)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm,
        title="Smart File Organizer — Estadísticas")
    story = []

    hdr = Table([[Paragraph("Smart File Organizer — Estadísticas", style_title)]],
                colWidths=[doc.width])
    hdr.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), DARK_BLUE),
        ("TOPPADDING", (0,0), (-1,-1), 14), ("BOTTOMPADDING", (0,0), (-1,-1), 14),
    ]))
    story.append(hdr); story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph(
        f"Scan ID: {scan_id}  •  Generado el {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}",
        style_sub))
    story.append(Spacer(1, 0.6*cm))

    story.append(Paragraph("Resumen General", style_section))
    story.append(HRFlowable(width="100%", thickness=1, color=MED_BLUE, spaceAfter=6))
    hw = doc.width / 2
    sum_tbl = Table([
        ["Total de archivos", f"{stats['total_files']:,}"],
        ["Tamaño total",      _fmt_size(stats["total_size"])],
        ["Categorías",        str(len(stats["categories"]))],
    ], colWidths=[hw*0.45, hw*0.55])
    sum_tbl.setStyle(TableStyle([
        ("ROWBACKGROUNDS", (0,0), (-1,-1), [WHITE, LIGHT_BLU]),
        ("FONTNAME", (0,0), (0,-1), "Helvetica-Bold"), ("FONTSIZE", (0,0), (-1,-1), 10),
        ("GRID", (0,0), (-1,-1), 0.5, BORDER),
        ("TOPPADDING", (0,0), (-1,-1), 6), ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ("LEFTPADDING", (0,0), (-1,-1), 10),
    ]))
    story.append(sum_tbl); story.append(Spacer(1, 0.8*cm))

    story.append(Paragraph("Distribución por Categoría", style_section))
    story.append(HRFlowable(width="100%", thickness=1, color=MED_BLUE, spaceAfter=6))

    pie_draw = Drawing(200, 180)
    pie = Pie(); pie.x = 10; pie.y = 10; pie.width = 160; pie.height = 160
    pie.data   = [c["file_count"] for c in stats["categories"]]
    pie.labels = [c["category"] for c in stats["categories"]]
    pie.sideLabels = True; pie.simpleLabels = False
    for i, sl in enumerate(pie.slices):
        sl.fillColor = colors.HexColor(CHART_CLR[i % len(CHART_CLR)])
        sl.strokeColor = WHITE; sl.strokeWidth = 1
    pie_draw.add(pie)

    cat_w = doc.width - 220
    cat_rows = [["Categoría", "Archivos", "Tamaño", "%"]] + [
        [c["category"].capitalize(), f"{c['file_count']:,}",
         _fmt_size(c["total_size"]), f"{c['percentage']:.1f}%"]
        for c in stats["categories"]
    ]
    cat_tbl = Table(cat_rows, colWidths=[cat_w*0.35, cat_w*0.18, cat_w*0.28, cat_w*0.19])
    cat_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), MED_BLUE), ("TEXTCOLOR", (0,0), (-1,0), WHITE),
        ("FONTNAME",   (0,0), (-1,0), "Helvetica-Bold"), ("FONTSIZE", (0,0), (-1,-1), 8.5),
        ("ALIGN",      (1,0), (-1,-1), "CENTER"),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [WHITE, ALT_ROW]),
        ("GRID", (0,0), (-1,-1), 0.5, BORDER),
        ("TOPPADDING", (0,0), (-1,-1), 4), ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ("LEFTPADDING", (0,0), (-1,-1), 6),
    ]))
    combo = Table([[pie_draw, cat_tbl]], colWidths=[220, doc.width - 220])
    combo.setStyle(TableStyle([("VALIGN", (0,0), (-1,-1), "TOP")]))
    story.append(combo); story.append(Spacer(1, 0.8*cm))

    story.append(Paragraph("Archivos Más Grandes", style_section))
    story.append(HRFlowable(width="100%", thickness=1, color=MED_BLUE, spaceAfter=6))
    lg_w = doc.width
    lg_rows = [["#", "Nombre", "Tamaño", "Modificado", "Ruta"]] + [
        [Paragraph(str(f["rank"]), style_center),
         Paragraph(f["name"], style_cell),
         Paragraph(_fmt_size(f["size"]), style_right),
         Paragraph(f["modified"], style_center),
         Paragraph(("…" + f["path"][-50:]) if len(f["path"]) > 53 else f["path"], style_cell)]
        for f in largest
    ]
    lg_tbl = Table(lg_rows,
        colWidths=[0.6*cm, lg_w*0.28, lg_w*0.12, lg_w*0.13, lg_w*0.42 - 0.6*cm],
        repeatRows=1)
    lg_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), DARK_BLUE), ("TEXTCOLOR", (0,0), (-1,0), WHITE),
        ("FONTNAME",   (0,0), (-1,0), "Helvetica-Bold"), ("FONTSIZE", (0,0), (-1,0), 9),
        ("ALIGN",      (0,0), (-1,0), "CENTER"), ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [WHITE, ALT_ROW]),
        ("GRID", (0,0), (-1,-1), 0.3, BORDER),
        ("TOPPADDING", (0,0), (-1,-1), 3), ("BOTTOMPADDING", (0,0), (-1,-1), 3),
        ("LEFTPADDING", (0,0), (-1,-1), 4),
    ]))
    story.append(lg_tbl); story.append(Spacer(1, 0.8*cm))

    story.append(Paragraph("Top Extensiones", style_section))
    story.append(HRFlowable(width="100%", thickness=1, color=MED_BLUE, spaceAfter=6))
    ew = doc.width / 4
    ext_rows = [["Extensión", "Archivos", "Tamaño total", "%"]] + [
        [e["extension"], f"{e['count']:,}", _fmt_size(e["total_size"]), f"{e['percentage']:.1f}%"]
        for e in extensions
    ]
    ext_tbl = Table(ext_rows, colWidths=[ew]*4)
    ext_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), MED_BLUE), ("TEXTCOLOR", (0,0), (-1,0), WHITE),
        ("FONTNAME",   (0,0), (-1,0), "Helvetica-Bold"), ("FONTSIZE", (0,0), (-1,-1), 9),
        ("ALIGN",      (1,0), (-1,-1), "CENTER"),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [WHITE, ALT_ROW]),
        ("GRID", (0,0), (-1,-1), 0.5, BORDER),
        ("TOPPADDING", (0,0), (-1,-1), 4), ("BOTTOMPADDING", (0,0), (-1,-1), 4),
    ]))
    story.append(ext_tbl)

    def on_page(canvas, doc):
        canvas.saveState(); canvas.setFont("Helvetica", 8); canvas.setFillColor(GRAY)
        canvas.drawString(2*cm, 1.2*cm,
            f"Smart File Organizer  •  Estadísticas  •  Scan {scan_id}")
        canvas.drawRightString(A4[0] - 2*cm, 1.2*cm, f"Página {doc.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    buf.seek(0)
    filename = f"estadisticas_{scan_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return StreamingResponse(iter([buf.read()]), media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'})


# ── Stats Excel ───────────────────────────────────────────────────────────────

def _export_stats_excel(scan_id: str) -> StreamingResponse:
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter
        from openpyxl.chart import BarChart, Reference
        from openpyxl.chart import PieChart as XLPie
    except ImportError:
        raise HTTPException(500, detail="openpyxl no instalado. Ejecuta: pip install openpyxl")

    stats, largest, extensions = _get_stats_data(scan_id)

    C_HEADER = "1E3A5F"; C_ACCENT = "2E86AB"; C_ALT = "F0F4F8"
    C_FG = "FFFFFF";     C_BORDER = "CCCCCC"
    thin = Side(style="thin", color=C_BORDER)
    brd  = Border(left=thin, right=thin, top=thin, bottom=thin)

    def hdr_cell(cell, text):
        cell.value = text
        cell.font  = Font(name="Calibri", bold=True, color=C_FG, size=11)
        cell.fill  = PatternFill("solid", fgColor=C_ACCENT)
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = brd

    wb = openpyxl.Workbook()
    ws = wb.active; ws.title = "Resumen"
    ws.sheet_view.showGridLines = False

    ws.merge_cells("A1:D1")
    ws["A1"].value = "Smart File Organizer — Estadísticas"
    ws["A1"].font  = Font(name="Calibri", size=16, bold=True, color=C_FG)
    ws["A1"].fill  = PatternFill("solid", fgColor=C_HEADER)
    ws["A1"].alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 36
    ws.merge_cells("A2:D2")
    ws["A2"].value = f"Scan: {scan_id}  |  {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    ws["A2"].font  = Font(name="Calibri", size=10, color="666666")
    ws["A2"].fill  = PatternFill("solid", fgColor="EAF0F6")
    ws["A2"].alignment = Alignment(horizontal="center")
    ws.append([])

    for label, val in [("Total archivos", f"{stats['total_files']:,}"),
                       ("Tamaño total",   _fmt_size(stats["total_size"])),
                       ("Categorías",     str(len(stats["categories"])))]:
        ws.append([label, val])
        r = ws.max_row
        ws[f"A{r}"].font = Font(name="Calibri", bold=True, size=11)
        ws[f"A{r}"].fill = PatternFill("solid", fgColor="E8EEF4"); ws[f"A{r}"].border = brd
        ws[f"B{r}"].font = Font(name="Calibri", size=11);          ws[f"B{r}"].border = brd

    ws.append([])
    start_cat = ws.max_row + 1
    ws.append(["Categoría", "Archivos", "Tamaño", "%"])
    r = ws.max_row
    for col in range(1, 5): hdr_cell(ws.cell(r, col), ws.cell(r, col).value)

    for i, c in enumerate(stats["categories"]):
        ws.append([c["category"].capitalize(), c["file_count"],
                   _fmt_size(c["total_size"]), f"{c['percentage']:.1f}%"])
        r = ws.max_row
        fill = PatternFill("solid", fgColor=C_ALT if i % 2 == 0 else "FFFFFF")
        for col in range(1, 5):
            ws.cell(r, col).fill = fill
            ws.cell(r, col).font = Font(name="Calibri", size=10)
            ws.cell(r, col).border = brd
            if col > 1: ws.cell(r, col).alignment = Alignment(horizontal="center")
    end_cat = ws.max_row

    pie = XLPie(); pie.title = "Por categoría"; pie.style = 10
    pie.add_data(Reference(ws, min_col=2, min_row=start_cat, max_row=end_cat),
                 titles_from_data=True)
    pie.set_categories(Reference(ws, min_col=1, min_row=start_cat+1, max_row=end_cat))
    pie.width = 14; pie.height = 14; ws.add_chart(pie, "F3")

    for col, w in zip("ABCD", [20, 14, 16, 10]):
        ws.column_dimensions[col].width = w

    ws2 = wb.create_sheet("Archivos más grandes")
    ws2.sheet_view.showGridLines = False
    hdrs = ["#", "Nombre", "Tamaño", "Modificado", "Ruta"]
    ws2.append(hdrs)
    for col in range(1, 6): hdr_cell(ws2.cell(1, col), hdrs[col-1])
    ws2.freeze_panes = "A2"
    for i, f in enumerate(largest):
        ws2.append([f["rank"], f["name"], _fmt_size(f["size"]), f["modified"], f["path"]])
        r = ws2.max_row
        fill = PatternFill("solid", fgColor=C_ALT if i % 2 == 0 else "FFFFFF")
        for col in range(1, 6):
            ws2.cell(r, col).fill = fill
            ws2.cell(r, col).font = Font(name="Calibri", size=9)
            ws2.cell(r, col).border = brd
    for col, w in zip(range(1, 6), [6, 30, 12, 14, 55]):
        ws2.column_dimensions[get_column_letter(col)].width = w

    ws3 = wb.create_sheet("Top extensiones")
    ws3.sheet_view.showGridLines = False
    hdrs3 = ["Extensión", "Archivos", "Tamaño total", "%"]
    ws3.append(hdrs3)
    for col in range(1, 5): hdr_cell(ws3.cell(1, col), hdrs3[col-1])
    ws3.freeze_panes = "A2"
    for i, e in enumerate(extensions):
        ws3.append([e["extension"], e["count"], _fmt_size(e["total_size"]),
                    f"{e['percentage']:.1f}%"])
        r = ws3.max_row
        fill = PatternFill("solid", fgColor=C_ALT if i % 2 == 0 else "FFFFFF")
        for col in range(1, 5):
            ws3.cell(r, col).fill = fill
            ws3.cell(r, col).font = Font(name="Calibri", size=10)
            ws3.cell(r, col).border = brd
            if col > 1: ws3.cell(r, col).alignment = Alignment(horizontal="center")
    for col, w in zip(range(1, 5), [16, 12, 16, 10]):
        ws3.column_dimensions[get_column_letter(col)].width = w

    bar = BarChart(); bar.type = "col"; bar.title = "Top extensiones"; bar.style = 10
    bar.y_axis.title = "Archivos"
    bar.add_data(Reference(ws3, min_col=2, min_row=1,
                           max_row=min(len(extensions)+1, 11)), titles_from_data=True)
    bar.set_categories(Reference(ws3, min_col=1, min_row=2,
                                 max_row=min(len(extensions)+1, 11)))
    bar.width = 18; bar.height = 12; ws3.add_chart(bar, "F2")

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
from __future__ import annotations

import io
import os
import csv
import json
import logging
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.core.scan_store import scan_store
from app.db.database import get_files_paginated, get_scan

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/export", tags=["export"])


def _get_all_files(scan_id: str) -> tuple[list[dict], dict]:
    """Obtiene todos los archivos del scan paginando desde SQLite."""
    scan_meta = get_scan(scan_id)
    if not scan_meta:
        # Intentar desde el store en memoria
        result = scan_store.get_scan_result(scan_id)
        if not result:
            raise HTTPException(404, detail=f"Scan '{scan_id}' no encontrado")
        files = [f.dict() for f in result.files]
        meta = {
            "scan_id": scan_id,
            "root_path": result.root_path,
            "total_files": result.total_files,
            "total_size": result.total_size,
            "duration_sec": result.duration_sec,
            "scanned_at": result.scanned_at.isoformat(),
        }
        return files, meta

    # Cargar desde SQLite paginado
    all_files = []
    page = 1
    page_size = 2000
    while True:
        paginated = get_files_paginated(scan_id, page, page_size)
        batch = paginated.get("files", [])
        for f in batch:
            all_files.append(f.dict() if hasattr(f, "dict") else f)
        total_pages = paginated.get("total_pages", 1)
        if page >= total_pages:
            break
        page += 1

    meta = {
        "scan_id": scan_id,
        "root_path": scan_meta.get("root_path", ""),
        "total_files": scan_meta.get("total_files", len(all_files)),
        "total_size": scan_meta.get("total_size", 0),
        "duration_sec": scan_meta.get("duration_sec", 0),
        "scanned_at": scan_meta.get("scanned_at", datetime.now().isoformat()),
    }
    return all_files, meta


def _fmt_size(size_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"


# ── CSV ──────────────────────────────────────────────────────────────────────

def _export_csv(scan_id: str) -> StreamingResponse:
    files, meta = _get_all_files(scan_id)
    buf = io.StringIO()
    writer = csv.writer(buf)

    writer.writerow(["# Smart File Organizer — Reporte de Escaneo"])
    writer.writerow(["# Ruta escaneada", meta["root_path"]])
    writer.writerow(["# Fecha", meta["scanned_at"]])
    writer.writerow(["# Total archivos", meta["total_files"]])
    writer.writerow(["# Tamaño total", _fmt_size(meta["total_size"])])
    writer.writerow(["# Duración (s)", meta["duration_sec"]])
    writer.writerow([])
    writer.writerow(["Nombre", "Ruta", "Tamaño (bytes)", "Tamaño", "Extensión", "Categoría", "Modificado"])

    for f in files:
        size = int(f.get("size", 0))
        writer.writerow([
            f.get("name", ""),
            f.get("path", ""),
            size,
            _fmt_size(size),
            f.get("extension", ""),
            f.get("category", ""),
            str(f.get("modified", "")),
        ])

    buf.seek(0)
    filename = f"scan_{scan_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([buf.getvalue().encode("utf-8-sig")]),  # utf-8-sig para Excel
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Excel (XLSX) ──────────────────────────────────────────────────────────────

def _export_excel(scan_id: str) -> StreamingResponse:
    try:
        import openpyxl
        from openpyxl.styles import (Font, PatternFill, Alignment,
                                      Border, Side, numbers)
        from openpyxl.utils import get_column_letter
    except ImportError:
        raise HTTPException(500, detail=(
            "openpyxl no está instalado. "
            "Ejecuta: pip install openpyxl"
        ))

    files, meta = _get_all_files(scan_id)

    wb = openpyxl.Workbook()

    # ── Hoja 1: Resumen ───────────────────────────────────────────────────────
    ws_summary = wb.active
    ws_summary.title = "Resumen"
    ws_summary.sheet_view.showGridLines = False

    # Colores
    COLOR_HEADER_BG  = "1E3A5F"
    COLOR_HEADER_FG  = "FFFFFF"
    COLOR_ACCENT     = "2E86AB"
    COLOR_ALT_ROW    = "F0F4F8"
    COLOR_LABEL_BG   = "E8EEF4"

    def h_border():
        thin = Side(style="thin", color="CCCCCC")
        return Border(left=thin, right=thin, top=thin, bottom=thin)

    # Título
    ws_summary.merge_cells("A1:D1")
    title_cell = ws_summary["A1"]
    title_cell.value = "Smart File Organizer — Reporte de Escaneo"
    title_cell.font = Font(name="Calibri", size=16, bold=True, color=COLOR_HEADER_FG)
    title_cell.fill = PatternFill("solid", fgColor=COLOR_HEADER_BG)
    title_cell.alignment = Alignment(horizontal="center", vertical="center")
    ws_summary.row_dimensions[1].height = 36

    # Subtítulo con fecha
    ws_summary.merge_cells("A2:D2")
    sub = ws_summary["A2"]
    sub.value = f"Generado el {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"
    sub.font = Font(name="Calibri", size=10, color="666666")
    sub.fill = PatternFill("solid", fgColor="EAF0F6")
    sub.alignment = Alignment(horizontal="center")
    ws_summary.row_dimensions[2].height = 20

    ws_summary.append([])

    # Datos de resumen
    summary_data = [
        ("Ruta escaneada",   meta["root_path"]),
        ("Fecha de escaneo", str(meta["scanned_at"])[:19].replace("T", " ")),
        ("Total de archivos", f"{meta['total_files']:,}"),
        ("Tamaño total",      _fmt_size(meta["total_size"])),
        ("Duración",          f"{meta['duration_sec']:.2f} segundos"),
        ("Scan ID",           meta["scan_id"]),
    ]

    for label, value in summary_data:
        row = ws_summary.append([label, value])
        r = ws_summary.max_row
        ws_summary[f"A{r}"].font = Font(name="Calibri", size=11, bold=True)
        ws_summary[f"A{r}"].fill = PatternFill("solid", fgColor=COLOR_LABEL_BG)
        ws_summary[f"A{r}"].border = h_border()
        ws_summary[f"B{r}"].font = Font(name="Calibri", size=11)
        ws_summary[f"B{r}"].border = h_border()

    # Distribución por categoría
    ws_summary.append([])
    ws_summary.append(["Categoría", "Archivos", "Tamaño total", "% del total"])
    header_row = ws_summary.max_row
    for col in range(1, 5):
        cell = ws_summary.cell(header_row, col)
        cell.font = Font(name="Calibri", size=11, bold=True, color=COLOR_HEADER_FG)
        cell.fill = PatternFill("solid", fgColor=COLOR_ACCENT)
        cell.alignment = Alignment(horizontal="center")
        cell.border = h_border()

    from collections import defaultdict
    by_cat: dict[str, dict] = defaultdict(lambda: {"count": 0, "size": 0})
    for f in files:
        cat = f.get("category", "other")
        by_cat[cat]["count"] += 1
        by_cat[cat]["size"] += int(f.get("size", 0))

    total_files = max(meta["total_files"], 1)
    for i, (cat, stats) in enumerate(sorted(by_cat.items())):
        ws_summary.append([
            cat.capitalize(),
            stats["count"],
            _fmt_size(stats["size"]),
            f'{stats["count"] / total_files * 100:.1f}%',
        ])
        r = ws_summary.max_row
        bg = COLOR_ALT_ROW if i % 2 == 0 else "FFFFFF"
        for col in range(1, 5):
            cell = ws_summary.cell(r, col)
            cell.fill = PatternFill("solid", fgColor=bg)
            cell.font = Font(name="Calibri", size=10)
            cell.border = h_border()
            if col == 2:
                cell.alignment = Alignment(horizontal="center")

    ws_summary.column_dimensions["A"].width = 22
    ws_summary.column_dimensions["B"].width = 40
    ws_summary.column_dimensions["C"].width = 18
    ws_summary.column_dimensions["D"].width = 14

    # ── Hoja 2: Archivos ─────────────────────────────────────────────────────
    ws_files = wb.create_sheet("Archivos")
    ws_files.sheet_view.showGridLines = False

    # Cabecera
    headers = ["#", "Nombre", "Extensión", "Categoría", "Tamaño (bytes)", "Tamaño", "Ruta", "Modificado"]
    ws_files.append(headers)
    h_row = 1
    for col, _ in enumerate(headers, 1):
        cell = ws_files.cell(h_row, col)
        cell.font = Font(name="Calibri", size=11, bold=True, color=COLOR_HEADER_FG)
        cell.fill = PatternFill("solid", fgColor=COLOR_HEADER_BG)
        cell.alignment = Alignment(horizontal="center")
        cell.border = h_border()

    ws_files.row_dimensions[1].height = 24
    ws_files.freeze_panes = "A2"

    for i, f in enumerate(files, 1):
        size = int(f.get("size", 0))
        ws_files.append([
            i,
            f.get("name", ""),
            f.get("extension", ""),
            f.get("category", ""),
            size,
            _fmt_size(size),
            f.get("path", ""),
            str(f.get("modified", ""))[:19],
        ])
        r = ws_files.max_row
        bg = COLOR_ALT_ROW if i % 2 == 0 else "FFFFFF"
        for col in range(1, len(headers) + 1):
            cell = ws_files.cell(r, col)
            cell.fill = PatternFill("solid", fgColor=bg)
            cell.font = Font(name="Calibri", size=9)
            cell.border = h_border()
            if col in (1, 3, 4, 5, 6):
                cell.alignment = Alignment(horizontal="center")

    col_widths = [6, 30, 10, 14, 16, 12, 55, 20]
    for col, width in enumerate(col_widths, 1):
        ws_files.column_dimensions[get_column_letter(col)].width = width

    # ── Serializar ────────────────────────────────────────────────────────────
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    filename = f"scan_{scan_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return StreamingResponse(
        iter([buf.read()]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── PDF ───────────────────────────────────────────────────────────────────────

def _export_pdf(scan_id: str) -> StreamingResponse:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                         Paragraph, Spacer, HRFlowable,
                                         PageBreak)
        from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    except ImportError:
        raise HTTPException(500, detail=(
            "reportlab no está instalado. "
            "Ejecuta: pip install reportlab"
        ))

    files, meta = _get_all_files(scan_id)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(A4),
        leftMargin=1.5*cm, rightMargin=1.5*cm,
        topMargin=2*cm, bottomMargin=2*cm,
        title="Smart File Organizer Report",
        author="Smart File Organizer",
    )

    # ── Estilos ────────────────────────────────────────────────────────────────
    DARK_BLUE  = colors.HexColor("#1E3A5F")
    MED_BLUE   = colors.HexColor("#2E86AB")
    LIGHT_BLUE = colors.HexColor("#EAF0F6")
    ALT_ROW    = colors.HexColor("#F4F8FC")
    WHITE      = colors.white
    GRAY_TEXT  = colors.HexColor("#555555")
    BORDER_CLR = colors.HexColor("#CCCCCC")

    styles = getSampleStyleSheet()
    style_title = ParagraphStyle("title",
        fontSize=22, fontName="Helvetica-Bold",
        textColor=WHITE, alignment=TA_CENTER, leading=28)
    style_subtitle = ParagraphStyle("subtitle",
        fontSize=10, fontName="Helvetica",
        textColor=GRAY_TEXT, alignment=TA_CENTER, leading=14)
    style_section = ParagraphStyle("section",
        fontSize=13, fontName="Helvetica-Bold",
        textColor=DARK_BLUE, leading=18, spaceBefore=10)
    style_cell = ParagraphStyle("cell",
        fontSize=7.5, fontName="Helvetica", leading=10,
        wordWrap="CJK")
    style_cell_center = ParagraphStyle("cell_c",
        fontSize=7.5, fontName="Helvetica", leading=10,
        alignment=TA_CENTER)
    style_cell_right = ParagraphStyle("cell_r",
        fontSize=7.5, fontName="Helvetica", leading=10,
        alignment=TA_RIGHT)

    story = []

    # ── Portada / encabezado ───────────────────────────────────────────────────
    header_data = [[Paragraph("Smart File Organizer — Reporte de Escaneo", style_title)]]
    header_table = Table(header_data, colWidths=[doc.width])
    header_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), DARK_BLUE),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [DARK_BLUE]),
        ("TOPPADDING", (0, 0), (-1, -1), 14),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
        ("LEFTPADDING", (0, 0), (-1, -1), 20),
        ("RIGHTPADDING", (0, 0), (-1, -1), 20),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph(
        f"Generado el {datetime.now().strftime('%d/%m/%Y a las %H:%M:%S')}",
        style_subtitle))
    story.append(Spacer(1, 0.5*cm))

    # ── Resumen ────────────────────────────────────────────────────────────────
    story.append(Paragraph("Información del Escaneo", style_section))
    story.append(HRFlowable(width="100%", thickness=1, color=MED_BLUE,
                             spaceAfter=6))

    summary_rows = [
        ["Campo", "Valor"],
        ["Ruta escaneada",    meta["root_path"]],
        ["Fecha de escaneo",  str(meta["scanned_at"])[:19].replace("T", " ")],
        ["Total de archivos", f"{meta['total_files']:,}"],
        ["Tamaño total",      _fmt_size(meta["total_size"])],
        ["Duración",          f"{meta['duration_sec']:.2f}s"],
        ["Scan ID",           meta["scan_id"]],
    ]

    half_w = doc.width / 2
    summary_tbl = Table(summary_rows, colWidths=[half_w * 0.35, half_w * 0.65])
    summary_tbl.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, 0), MED_BLUE),
        ("TEXTCOLOR",    (0, 0), (-1, 0), WHITE),
        ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",     (0, 0), (-1, 0), 10),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT_BLUE]),
        ("FONTNAME",     (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE",     (0, 1), (-1, -1), 9),
        ("FONTNAME",     (0, 1), (0, -1), "Helvetica-Bold"),
        ("GRID",         (0, 0), (-1, -1), 0.5, BORDER_CLR),
        ("TOPPADDING",   (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 6),
        ("LEFTPADDING",  (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(summary_tbl)
    story.append(Spacer(1, 0.8*cm))

    # ── Distribución por categoría ─────────────────────────────────────────────
    from collections import defaultdict
    by_cat: dict[str, dict] = defaultdict(lambda: {"count": 0, "size": 0})
    for f in files:
        cat = f.get("category", "other")
        by_cat[cat]["count"] += 1
        by_cat[cat]["size"] += int(f.get("size", 0))

    story.append(Paragraph("Distribución por Categoría", style_section))
    story.append(HRFlowable(width="100%", thickness=1, color=MED_BLUE,
                             spaceAfter=6))

    cat_rows = [["Categoría", "Archivos", "Tamaño total", "% del total"]]
    total_files_n = max(meta["total_files"], 1)
    for cat, stats in sorted(by_cat.items()):
        cat_rows.append([
            cat.capitalize(),
            f"{stats['count']:,}",
            _fmt_size(stats["size"]),
            f"{stats['count'] / total_files_n * 100:.1f}%",
        ])

    col_w = doc.width / 4
    cat_tbl = Table(cat_rows, colWidths=[col_w] * 4)
    cat_tbl.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, 0), MED_BLUE),
        ("TEXTCOLOR",    (0, 0), (-1, 0), WHITE),
        ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",     (0, 0), (-1, 0), 10),
        ("ALIGN",        (0, 0), (-1, 0), "CENTER"),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [WHITE, ALT_ROW]),
        ("FONTNAME",     (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE",     (0, 1), (-1, -1), 9),
        ("ALIGN",        (1, 1), (-1, -1), "CENTER"),
        ("GRID",         (0, 0), (-1, -1), 0.5, BORDER_CLR),
        ("TOPPADDING",   (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 5),
    ]))
    story.append(cat_tbl)

    # ── Lista de archivos ──────────────────────────────────────────────────────
    MAX_FILES_IN_PDF = 5000
    files_to_show = files[:MAX_FILES_IN_PDF]
    truncated = len(files) > MAX_FILES_IN_PDF

    story.append(PageBreak())
    title_txt = "Lista de Archivos"
    if truncated:
        title_txt += f" (primeros {MAX_FILES_IN_PDF:,} de {len(files):,})"
    story.append(Paragraph(title_txt, style_section))
    story.append(HRFlowable(width="100%", thickness=1, color=MED_BLUE,
                             spaceAfter=6))

    file_header = ["#", "Nombre", "Extensión", "Categoría", "Tamaño", "Modificado", "Ruta"]
    file_rows = [file_header]
    for i, f in enumerate(files_to_show, 1):
        size = int(f.get("size", 0))
        path = f.get("path", "")
        # Truncar rutas muy largas
        if len(path) > 70:
            path = "…" + path[-67:]
        file_rows.append([
            Paragraph(str(i), style_cell_center),
            Paragraph(f.get("name", ""), style_cell),
            Paragraph(f.get("extension", ""), style_cell_center),
            Paragraph(f.get("category", ""), style_cell_center),
            Paragraph(_fmt_size(size), style_cell_right),
            Paragraph(str(f.get("modified", ""))[:10], style_cell_center),
            Paragraph(path, style_cell),
        ])

    # Anchos de columna para A4 landscape
    c_widths = [1.0*cm, 5.5*cm, 1.8*cm, 2.5*cm, 2.0*cm, 2.5*cm, None]
    fixed = sum(w for w in c_widths if w)
    c_widths[-1] = doc.width - fixed

    files_tbl = Table(file_rows, colWidths=c_widths, repeatRows=1)
    files_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), DARK_BLUE),
        ("TEXTCOLOR",     (0, 0), (-1, 0), WHITE),
        ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, 0), 8),
        ("ALIGN",         (0, 0), (-1, 0), "CENTER"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [WHITE, ALT_ROW]),
        ("GRID",          (0, 0), (-1, -1), 0.3, BORDER_CLR),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING",   (0, 0), (-1, -1), 4),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
    ]))
    story.append(files_tbl)

    # ── Pie de página ──────────────────────────────────────────────────────────
    def on_page(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(GRAY_TEXT)
        canvas.drawString(1.5*cm, 1*cm,
            f"Smart File Organizer  •  Scan {scan_id}  •  "
            f"{datetime.now().strftime('%d/%m/%Y')}")
        canvas.drawRightString(doc.pagesize[0] - 1.5*cm, 1*cm,
            f"Página {doc.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    buf.seek(0)

    filename = f"scan_{scan_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return StreamingResponse(
        iter([buf.read()]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Endpoint principal ────────────────────────────────────────────────────────

@router.get("/{scan_id}")
def export_scan(
    scan_id: str,
    format: Literal["pdf", "excel", "csv"] = Query(default="pdf"),
) -> StreamingResponse:
    """
    Exporta los resultados de un scan al formato indicado.
    - pdf:   Reporte PDF profesional con resumen, categorías y lista de archivos
    - excel: Libro Excel con hoja de resumen y hoja detalle
    - csv:   CSV con encabezado de metadatos y todos los archivos
    """
    logger.info(f"Export requested: scan_id={scan_id} format={format}")

    if format == "pdf":
        return _export_pdf(scan_id)
    elif format == "excel":
        return _export_excel(scan_id)
    else:
        return _export_csv(scan_id)


# ── Stats export ──────────────────────────────────────────────────────────────

def _get_stats_data(scan_id: str) -> tuple[dict, list[dict], list[dict]]:
    """Obtiene stats, archivos más grandes y extensiones para un scan."""
    import httpx
    # Llamada interna: reusar la lógica de los endpoints existentes
    from app.core.stats import compute_stats
    from app.core.scan_store import scan_store
    from app.db.database import get_files_paginated
    from app.models.file_info import FileInfo, FileCategory
    from datetime import datetime as dt

    result = scan_store.get_scan_result(scan_id)
    if not result:
        # Intentar desde SQLite
        scan_meta = get_scan(scan_id)
        if not scan_meta:
            raise HTTPException(404, detail=f"Scan '{scan_id}' no encontrado")
        # Cargar primeras 5000 para stats
        paginated = get_files_paginated(scan_id, 1, 5000)
        files = paginated.get("files", [])
    else:
        files = result.files

    # Estadísticas generales
    total_files = len(files)
    total_size = sum(f.size if hasattr(f, "size") else f.get("size", 0) for f in files)
    
    # Por categoría
    from collections import defaultdict
    by_cat: dict[str, dict] = defaultdict(lambda: {"count": 0, "size": 0})
    for f in files:
        cat = (f.category.value if hasattr(f, "category") and hasattr(f.category, "value")
               else str(f.get("category", "other")) if isinstance(f, dict) else "other")
        sz  = f.size if hasattr(f, "size") else f.get("size", 0)
        by_cat[cat]["count"] += 1
        by_cat[cat]["size"]  += sz

    categories = sorted(
        [{"category": k, "file_count": v["count"], "total_size": v["size"],
          "percentage": round(v["count"] / max(total_files, 1) * 100, 1)}
         for k, v in by_cat.items()],
        key=lambda x: x["file_count"], reverse=True
    )

    # Archivos más grandes (top 20)
    def get_size(f):
        return f.size if hasattr(f, "size") else f.get("size", 0)
    def get_name(f):
        return f.name if hasattr(f, "name") else f.get("name", "")
    def get_path(f):
        return f.path if hasattr(f, "path") else f.get("path", "")
    def get_mod(f):
        m = f.modified if hasattr(f, "modified") else f.get("modified", "")
        return str(m)[:10] if m else ""

    largest = sorted(files, key=get_size, reverse=True)[:20]
    largest_data = [{"rank": i+1, "name": get_name(f), "path": get_path(f),
                     "size": get_size(f), "modified": get_mod(f)}
                    for i, f in enumerate(largest)]

    # Top extensiones
    ext_stats: dict[str, dict] = defaultdict(lambda: {"count": 0, "size": 0})
    for f in files:
        ext = (f.extension if hasattr(f, "extension") else f.get("extension", "")) or "sin ext"
        ext_stats[ext.upper()]["count"] += 1
        ext_stats[ext.upper()]["size"]  += get_size(f)

    extensions = sorted(
        [{"extension": k, "count": v["count"], "total_size": v["size"],
          "percentage": round(v["count"] / max(total_files, 1) * 100, 1)}
         for k, v in ext_stats.items()],
        key=lambda x: x["count"], reverse=True
    )[:20]

    stats = {
        "scan_id": scan_id,
        "total_files": total_files,
        "total_size": total_size,
        "categories": categories,
    }
    return stats, largest_data, extensions


def _export_stats_pdf(scan_id: str) -> StreamingResponse:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                         Paragraph, Spacer, HRFlowable, PageBreak)
        from reportlab.lib.enums import TA_CENTER, TA_RIGHT
        from reportlab.graphics.shapes import Drawing, Wedge, String
        from reportlab.graphics.charts.piecharts import Pie
        from reportlab.graphics import renderPDF
    except ImportError:
        raise HTTPException(500, detail="reportlab no instalado. Ejecuta: pip install reportlab")

    stats, largest, extensions = _get_stats_data(scan_id)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm,
        title="Smart File Organizer — Estadísticas")

    DARK_BLUE  = colors.HexColor("#1E3A5F")
    MED_BLUE   = colors.HexColor("#2E86AB")
    LIGHT_BLUE = colors.HexColor("#EAF0F6")
    ALT_ROW    = colors.HexColor("#F4F8FC")
    WHITE      = colors.white
    GRAY       = colors.HexColor("#555555")
    BORDER     = colors.HexColor("#CCCCCC")

    CHART_COLORS = [
        "#3B82F6","#10B981","#F59E0B","#EF4444",
        "#8B5CF6","#EC4899","#14B8A6","#F97316",
        "#6366F1","#84CC16",
    ]

    styles = getSampleStyleSheet()
    style_title   = ParagraphStyle("t", fontSize=20, fontName="Helvetica-Bold",
                                    textColor=WHITE, alignment=TA_CENTER, leading=26)
    style_sub     = ParagraphStyle("s", fontSize=9,  fontName="Helvetica",
                                    textColor=GRAY, alignment=TA_CENTER)
    style_section = ParagraphStyle("sec", fontSize=13, fontName="Helvetica-Bold",
                                    textColor=DARK_BLUE, spaceBefore=10, leading=18)
    style_cell    = ParagraphStyle("c", fontSize=8.5, fontName="Helvetica", leading=11)
    style_center  = ParagraphStyle("cc", fontSize=8.5, fontName="Helvetica",
                                    alignment=TA_CENTER, leading=11)
    style_right   = ParagraphStyle("cr", fontSize=8.5, fontName="Helvetica",
                                    alignment=TA_RIGHT, leading=11)

    def tborder():
        t = colors.HexColor("#CCCCCC")
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import TableStyle
        from reportlab.lib.pagesizes import A4
        s = reportlab.platypus.TableStyle  # avoid re-import
        side = colors.HexColor("#CCCCCC")
        from reportlab.platypus import TableStyle as TS
        from reportlab.lib import colors as C
        from reportlab.platypus.tables import TableStyle as TStyle
        thin = C.HexColor("#CCCCCC")
        from reportlab.lib.styles import getSampleStyleSheet as gss
        from reportlab.platypus import Table as T
        # Just return the standard grid style
        return [("GRID", (0,0), (-1,-1), 0.5, BORDER),
                ("TOPPADDING", (0,0), (-1,-1), 5),
                ("BOTTOMPADDING", (0,0), (-1,-1), 5),
                ("LEFTPADDING", (0,0), (-1,-1), 8),
                ("RIGHTPADDING", (0,0), (-1,-1), 8)]

    story = []

    # Header
    hdr = Table([[Paragraph("Smart File Organizer — Estadísticas", style_title)]],
                colWidths=[doc.width])
    hdr.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), DARK_BLUE),
        ("TOPPADDING", (0,0), (-1,-1), 14),
        ("BOTTOMPADDING", (0,0), (-1,-1), 14),
    ]))
    story.append(hdr)
    story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph(
        f"Scan ID: {scan_id}  •  Generado el {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}",
        style_sub))
    story.append(Spacer(1, 0.6*cm))

    # Resumen general
    story.append(Paragraph("Resumen General", style_section))
    story.append(HRFlowable(width="100%", thickness=1, color=MED_BLUE, spaceAfter=6))

    hw = doc.width / 2
    summary_rows = [
        ["Total de archivos", f"{stats['total_files']:,}"],
        ["Tamaño total",      _fmt_size(stats["total_size"])],
        ["Categorías",        str(len(stats["categories"]))],
    ]
    sum_tbl = Table(summary_rows, colWidths=[hw*0.45, hw*0.55])
    sum_tbl.setStyle(TableStyle([
        ("ROWBACKGROUNDS", (0,0), (-1,-1), [WHITE, LIGHT_BLUE]),
        ("FONTNAME", (0,0), (0,-1), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 10),
        ("GRID", (0,0), (-1,-1), 0.5, BORDER),
        ("TOPPADDING", (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ("LEFTPADDING", (0,0), (-1,-1), 10),
    ]))
    story.append(sum_tbl)
    story.append(Spacer(1, 0.8*cm))

    # Gráfico de tarta + tabla de categorías lado a lado
    story.append(Paragraph("Distribución por Categoría", style_section))
    story.append(HRFlowable(width="100%", thickness=1, color=MED_BLUE, spaceAfter=6))

    # Gráfico de tarta
    pie_draw = Drawing(200, 180)
    pie = Pie()
    pie.x = 10; pie.y = 10
    pie.width = 160; pie.height = 160
    pie.data  = [c["file_count"] for c in stats["categories"]]
    pie.labels = [c["category"] for c in stats["categories"]]
    pie.sideLabels = True
    pie.simpleLabels = False
    for i, slice_ in enumerate(pie.slices):
        slice_.fillColor = colors.HexColor(CHART_COLORS[i % len(CHART_COLORS)])
        slice_.strokeColor = WHITE
        slice_.strokeWidth = 1
    pie_draw.add(pie)

    # Tabla de categorías
    cat_hdr = [["Categoría", "Archivos", "Tamaño", "%"]]
    cat_rows = cat_hdr + [
        [c["category"].capitalize(),
         f"{c['file_count']:,}",
         _fmt_size(c["total_size"]),
         f"{c['percentage']:.1f}%"]
        for c in stats["categories"]
    ]
    cat_w = doc.width - 220
    cat_tbl = Table(cat_rows, colWidths=[cat_w*0.35, cat_w*0.18, cat_w*0.28, cat_w*0.19])
    cat_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), MED_BLUE),
        ("TEXTCOLOR", (0,0), (-1,0), WHITE),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 8.5),
        ("ALIGN", (1,0), (-1,-1), "CENTER"),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [WHITE, ALT_ROW]),
        ("GRID", (0,0), (-1,-1), 0.5, BORDER),
        ("TOPPADDING", (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ("LEFTPADDING", (0,0), (-1,-1), 6),
    ]))

    combo = Table([[pie_draw, cat_tbl]], colWidths=[220, doc.width - 220])
    combo.setStyle(TableStyle([("VALIGN", (0,0), (-1,-1), "TOP")]))
    story.append(combo)
    story.append(Spacer(1, 0.8*cm))

    # Archivos más grandes
    story.append(Paragraph("Archivos Más Grandes", style_section))
    story.append(HRFlowable(width="100%", thickness=1, color=MED_BLUE, spaceAfter=6))

    lg_hdr  = [["#", "Nombre", "Tamaño", "Modificado", "Ruta"]]
    lg_rows = lg_hdr + [
        [Paragraph(str(f["rank"]), style_center),
         Paragraph(f["name"], style_cell),
         Paragraph(_fmt_size(f["size"]), style_right),
         Paragraph(f["modified"], style_center),
         Paragraph(("…" + f["path"][-50:]) if len(f["path"]) > 53 else f["path"], style_cell)]
        for f in largest
    ]
    lg_w = doc.width
    lg_tbl = Table(lg_rows,
        colWidths=[0.6*cm, lg_w*0.28, lg_w*0.12, lg_w*0.13, lg_w*0.42 - 0.6*cm],
        repeatRows=1)
    lg_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), DARK_BLUE),
        ("TEXTCOLOR", (0,0), (-1,0), WHITE),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,0), 9),
        ("ALIGN", (0,0), (-1,0), "CENTER"),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [WHITE, ALT_ROW]),
        ("GRID", (0,0), (-1,-1), 0.3, BORDER),
        ("TOPPADDING", (0,0), (-1,-1), 3),
        ("BOTTOMPADDING", (0,0), (-1,-1), 3),
        ("LEFTPADDING", (0,0), (-1,-1), 4),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
    ]))
    story.append(lg_tbl)
    story.append(Spacer(1, 0.8*cm))

    # Top extensiones
    story.append(Paragraph("Top Extensiones", style_section))
    story.append(HRFlowable(width="100%", thickness=1, color=MED_BLUE, spaceAfter=6))

    ext_hdr  = [["Extensión", "Archivos", "Tamaño total", "%"]]
    ext_rows = ext_hdr + [
        [e["extension"], f"{e['count']:,}", _fmt_size(e["total_size"]), f"{e['percentage']:.1f}%"]
        for e in extensions
    ]
    ew = doc.width / 4
    ext_tbl = Table(ext_rows, colWidths=[ew]*4)
    ext_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), MED_BLUE),
        ("TEXTCOLOR", (0,0), (-1,0), WHITE),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 9),
        ("ALIGN", (1,0), (-1,-1), "CENTER"),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [WHITE, ALT_ROW]),
        ("GRID", (0,0), (-1,-1), 0.5, BORDER),
        ("TOPPADDING", (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
    ]))
    story.append(ext_tbl)

    def on_page(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(GRAY)
        canvas.drawString(2*cm, 1.2*cm,
            f"Smart File Organizer  •  Estadísticas  •  Scan {scan_id}")
        canvas.drawRightString(A4[0] - 2*cm, 1.2*cm, f"Página {doc.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    buf.seek(0)
    filename = f"estadisticas_{scan_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return StreamingResponse(iter([buf.read()]), media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'})


def _export_stats_excel(scan_id: str) -> StreamingResponse:
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter
        from openpyxl.chart import BarChart, Reference, PieChart as XLPie
        from openpyxl.chart.label import DataLabelList
    except ImportError:
        raise HTTPException(500, detail="openpyxl no instalado. Ejecuta: pip install openpyxl")

    stats, largest, extensions = _get_stats_data(scan_id)

    COLOR_HEADER = "1E3A5F"; COLOR_ACCENT = "2E86AB"
    COLOR_ALT    = "F0F4F8"; COLOR_FG = "FFFFFF"
    BORDER_CLR   = "CCCCCC"

    def brd():
        s = Side(style="thin", color=BORDER_CLR)
        return Border(left=s, right=s, top=s, bottom=s)

    def header_cell(cell, text):
        cell.value = text
        cell.font  = Font(name="Calibri", bold=True, color=COLOR_FG, size=11)
        cell.fill  = PatternFill("solid", fgColor=COLOR_ACCENT)
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = brd()

    wb = openpyxl.Workbook()

    # ── Hoja 1: Resumen ───────────────────────────────────────────────────────
    ws = wb.active; ws.title = "Resumen"
    ws.sheet_view.showGridLines = False

    # Título
    ws.merge_cells("A1:D1")
    ws["A1"].value = "Smart File Organizer — Estadísticas"
    ws["A1"].font  = Font(name="Calibri", size=16, bold=True, color=COLOR_FG)
    ws["A1"].fill  = PatternFill("solid", fgColor=COLOR_HEADER)
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
        ws[f"A{r}"].font   = Font(name="Calibri", bold=True, size=11)
        ws[f"A{r}"].fill   = PatternFill("solid", fgColor="E8EEF4")
        ws[f"A{r}"].border = brd()
        ws[f"B{r}"].font   = Font(name="Calibri", size=11)
        ws[f"B{r}"].border = brd()

    # Tabla categorías
    ws.append([])
    start_cat = ws.max_row + 1
    ws.append(["Categoría", "Archivos", "Tamaño", "%"])
    r = ws.max_row
    for col in range(1, 5): header_cell(ws.cell(r, col), ws.cell(r, col).value)

    for i, c in enumerate(stats["categories"]):
        ws.append([c["category"].capitalize(), c["file_count"],
                   _fmt_size(c["total_size"]), f"{c['percentage']:.1f}%"])
        r = ws.max_row
        bg = COLOR_ALT if i % 2 == 0 else "FFFFFF"
        for col in range(1, 5):
            ws.cell(r, col).fill   = PatternFill("solid", fgColor=bg)
            ws.cell(r, col).font   = Font(name="Calibri", size=10)
            ws.cell(r, col).border = brd()
            if col > 1: ws.cell(r, col).alignment = Alignment(horizontal="center")

    end_cat = ws.max_row

    # Gráfico de tarta para categorías
    pie = XLPie()
    pie.title = "Por categoría"
    pie.style = 10
    labels = Reference(ws, min_col=1, min_row=start_cat+1, max_row=end_cat)
    data   = Reference(ws, min_col=2, min_row=start_cat,   max_row=end_cat)
    pie.add_data(data, titles_from_data=True)
    pie.set_categories(labels)
    pie.width = 14; pie.height = 14
    ws.add_chart(pie, "F3")

    ws.column_dimensions["A"].width = 20
    ws.column_dimensions["B"].width = 14
    ws.column_dimensions["C"].width = 16
    ws.column_dimensions["D"].width = 10

    # ── Hoja 2: Archivos más grandes ─────────────────────────────────────────
    ws2 = wb.create_sheet("Archivos más grandes")
    ws2.sheet_view.showGridLines = False
    hdrs = ["#", "Nombre", "Tamaño", "Modificado", "Ruta"]
    ws2.append(hdrs)
    for col in range(1, 6): header_cell(ws2.cell(1, col), hdrs[col-1])
    ws2.freeze_panes = "A2"

    for i, f in enumerate(largest):
        ws2.append([f["rank"], f["name"], _fmt_size(f["size"]), f["modified"], f["path"]])
        r = ws2.max_row
        bg = COLOR_ALT if i % 2 == 0 else "FFFFFF"
        for col in range(1, 6):
            ws2.cell(r, col).fill   = PatternFill("solid", fgColor=bg)
            ws2.cell(r, col).font   = Font(name="Calibri", size=9)
            ws2.cell(r, col).border = brd()

    for col, w in zip(range(1, 6), [6, 30, 12, 14, 55]):
        ws2.column_dimensions[get_column_letter(col)].width = w

    # ── Hoja 3: Top extensiones ───────────────────────────────────────────────
    ws3 = wb.create_sheet("Top extensiones")
    ws3.sheet_view.showGridLines = False
    hdrs3 = ["Extensión", "Archivos", "Tamaño total", "%"]
    ws3.append(hdrs3)
    for col in range(1, 5): header_cell(ws3.cell(1, col), hdrs3[col-1])
    ws3.freeze_panes = "A2"

    for i, e in enumerate(extensions):
        ws3.append([e["extension"], e["count"], _fmt_size(e["total_size"]), f"{e['percentage']:.1f}%"])
        r = ws3.max_row
        bg = COLOR_ALT if i % 2 == 0 else "FFFFFF"
        for col in range(1, 5):
            ws3.cell(r, col).fill   = PatternFill("solid", fgColor=bg)
            ws3.cell(r, col).font   = Font(name="Calibri", size=10)
            ws3.cell(r, col).border = brd()
            if col > 1: ws3.cell(r, col).alignment = Alignment(horizontal="center")

    for col, w in zip(range(1, 5), [16, 12, 16, 10]):
        ws3.column_dimensions[get_column_letter(col)].width = w

    # Gráfico de barras extensiones
    bar = BarChart()
    bar.type = "col"; bar.title = "Top extensiones"
    bar.style = 10; bar.y_axis.title = "Archivos"
    data_ref  = Reference(ws3, min_col=2, min_row=1, max_row=min(len(extensions)+1, 11))
    cats_ref  = Reference(ws3, min_col=1, min_row=2, max_row=min(len(extensions)+1, 11))
    bar.add_data(data_ref, titles_from_data=True)
    bar.set_categories(cats_ref)
    bar.width = 18; bar.height = 12
    ws3.add_chart(bar, "F2")

    buf = io.BytesIO()
    wb.save(buf); buf.seek(0)
    filename = f"estadisticas_{scan_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return StreamingResponse(iter([buf.read()]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/{scan_id}/stats")
def export_stats(
    scan_id: str,
    format: Literal["pdf", "excel"] = Query(default="pdf"),
) -> StreamingResponse:
    """
    Exporta estadísticas del scan (gráfica, categorías, archivos más grandes, extensiones).
    - pdf:   Reporte PDF con gráfico de tarta, tablas y top archivos
    - excel: Libro Excel con 3 hojas + gráficos nativos
    """
    logger.info(f"Stats export: scan_id={scan_id} format={format}")
    if format == "excel":
        return _export_stats_excel(scan_id)
    return _export_stats_pdf(scan_id)
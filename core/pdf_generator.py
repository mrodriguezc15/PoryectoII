"""
core/pdf_generator.py
Genera un informe PDF profesional con los resultados del EDA.
Diseño ejecutivo con encabezado de color, tablas y gráficos.
"""
from __future__ import annotations
import os
import datetime
import tempfile

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate,
    Paragraph, Spacer, Table, TableStyle,
    Image, HRFlowable, KeepTogether, PageBreak,
)
from reportlab.platypus.flowables import Flowable

from core.eda import EDAResult
from config.settings import settings

# Paleta de colores corporativa
PRIMARY   = colors.HexColor("#1A73E8")   # Azul Google-like
SECONDARY = colors.HexColor("#0D47A1")   # Azul oscuro
ACCENT    = colors.HexColor("#34A853")   # Verde
LIGHT_BG  = colors.HexColor("#F8F9FA")  # Gris claro
DARK_TEXT = colors.HexColor("#202124")
GRAY_TEXT = colors.HexColor("#5F6368")
WHITE     = colors.white
RED_WARN  = colors.HexColor("#EA4335")

PAGE_W, PAGE_H = LETTER


# ---------------------------------------------------------------------------
# Encabezado / Pie de página
# ---------------------------------------------------------------------------

def _header_footer(canvas, doc):
    canvas.saveState()
    # Banda superior de color
    canvas.setFillColor(PRIMARY)
    canvas.rect(0, PAGE_H - 0.75 * inch, PAGE_W, 0.75 * inch, fill=True, stroke=False)

    # Título en banda
    canvas.setFillColor(WHITE)
    canvas.setFont("Helvetica-Bold", 11)
    canvas.drawString(0.5 * inch, PAGE_H - 0.45 * inch, "INFORME DE ANÁLISIS EXPLORATORIO DE DATOS")

    # Nombre del autor (derecha)
    canvas.setFont("Helvetica", 9)
    author = settings.REPORT_AUTHOR
    canvas.drawRightString(PAGE_W - 0.4 * inch, PAGE_H - 0.45 * inch, author)

    # Línea inferior de encabezado
    canvas.setStrokeColor(SECONDARY)
    canvas.setLineWidth(1.5)
    canvas.line(0, PAGE_H - 0.76 * inch, PAGE_W, PAGE_H - 0.76 * inch)

    # Pie de página
    canvas.setFillColor(GRAY_TEXT)
    canvas.setFont("Helvetica", 8)
    date_str = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
    canvas.drawString(0.5 * inch, 0.4 * inch, f"Generado: {date_str}")
    canvas.drawRightString(PAGE_W - 0.4 * inch, 0.4 * inch, f"Página {doc.page}")
    canvas.setStrokeColor(colors.HexColor("#DADCE0"))
    canvas.setLineWidth(0.5)
    canvas.line(0.5 * inch, 0.55 * inch, PAGE_W - 0.5 * inch, 0.55 * inch)

    canvas.restoreState()


# ---------------------------------------------------------------------------
# Estilos
# ---------------------------------------------------------------------------

def _build_styles():
    base = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle(
            "ReportTitle",
            parent=base["Title"],
            fontSize=22,
            textColor=SECONDARY,
            spaceAfter=4,
            fontName="Helvetica-Bold",
            alignment=TA_CENTER,
        ),
        "subtitle": ParagraphStyle(
            "ReportSubtitle",
            parent=base["Normal"],
            fontSize=11,
            textColor=GRAY_TEXT,
            spaceAfter=18,
            alignment=TA_CENTER,
        ),
        "section": ParagraphStyle(
            "SectionHeader",
            parent=base["Heading1"],
            fontSize=13,
            textColor=WHITE,
            fontName="Helvetica-Bold",
            spaceBefore=16,
            spaceAfter=8,
            backColor=PRIMARY,
            leftIndent=-6,
            rightIndent=-6,
            borderPad=6,
        ),
        "subsection": ParagraphStyle(
            "SubSection",
            parent=base["Heading2"],
            fontSize=11,
            textColor=PRIMARY,
            fontName="Helvetica-Bold",
            spaceBefore=10,
            spaceAfter=4,
            borderWidth=0,
            borderPadding=0,
        ),
        "body": ParagraphStyle(
            "BodyText",
            parent=base["Normal"],
            fontSize=9,
            textColor=DARK_TEXT,
            spaceAfter=6,
            leading=14,
            alignment=TA_JUSTIFY,
        ),
        "caption": ParagraphStyle(
            "Caption",
            parent=base["Normal"],
            fontSize=8,
            textColor=GRAY_TEXT,
            alignment=TA_CENTER,
            spaceAfter=10,
        ),
        "highlight_box": ParagraphStyle(
            "HighlightBox",
            parent=base["Normal"],
            fontSize=9,
            textColor=DARK_TEXT,
            backColor=LIGHT_BG,
            borderWidth=1,
            borderColor=colors.HexColor("#DADCE0"),
            borderPadding=8,
            spaceAfter=10,
            leading=14,
        ),
    }
    return styles


# ---------------------------------------------------------------------------
# Helpers para tablas
# ---------------------------------------------------------------------------

_TABLE_HEADER_STYLE = TableStyle([
    ("BACKGROUND",   (0, 0), (-1, 0), PRIMARY),
    ("TEXTCOLOR",    (0, 0), (-1, 0), WHITE),
    ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
    ("FONTSIZE",     (0, 0), (-1, 0), 9),
    ("ALIGN",        (0, 0), (-1, -1), "CENTER"),
    ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT_BG]),
    ("FONTSIZE",     (0, 1), (-1, -1), 8),
    ("TEXTCOLOR",    (0, 1), (-1, -1), DARK_TEXT),
    ("GRID",         (0, 0), (-1, -1), 0.25, colors.HexColor("#DADCE0")),
    ("TOPPADDING",   (0, 0), (-1, -1), 4),
    ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
])


def _df_to_table(df, col_widths=None, max_rows=20):
    """Convierte un DataFrame en una tabla ReportLab."""
    import pandas as pd
    sub = df.head(max_rows)
    header = [str(c) for c in sub.columns]
    rows = [[str(v)[:40] for v in row] for row in sub.itertuples(index=False)]
    data = [header] + rows
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(_TABLE_HEADER_STYLE)
    return t


# ---------------------------------------------------------------------------
# Función principal
# ---------------------------------------------------------------------------

def generate_pdf(
    result: EDAResult,
    user_name: str,
    dataset_url: str,
    output_path: str | None = None,
) -> str:
    """
    Genera el informe PDF ejecutivo.

    Args:
        result: EDAResult con todos los análisis.
        user_name: Nombre del usuario (para personalizar el informe).
        dataset_url: URL del dataset analizado.
        output_path: Ruta de destino. Si None, usa un archivo temporal.

    Returns:
        Ruta absoluta del PDF generado.
    """
    if output_path is None:
        tmp = tempfile.mktemp(suffix=".pdf", prefix="eda_informe_")
        output_path = tmp

    styles = _build_styles()

    # Márgenes: 0.5" lados, 1" arriba (para el header), 0.65" abajo
    frame = Frame(
        0.5 * inch, 0.65 * inch,
        PAGE_W - 1.0 * inch, PAGE_H - 1.45 * inch,
        id="main",
    )
    template = PageTemplate(id="main", frames=[frame], onPage=_header_footer)
    doc = BaseDocTemplate(
        output_path,
        pagesize=LETTER,
        pageTemplates=[template],
        leftMargin=0.5 * inch,
        rightMargin=0.5 * inch,
        topMargin=0.9 * inch,
        bottomMargin=0.65 * inch,
    )

    story = []
    _W = PAGE_W - 1.0 * inch  # Ancho útil

    # ── Portada ──────────────────────────────────────────────────────────────
    story.append(Spacer(1, 0.5 * inch))
    story.append(Paragraph("Análisis Exploratorio de Datos", styles["title"]))
    story.append(Paragraph(
        f"Preparado para: <b>{user_name}</b> &nbsp;|&nbsp; {datetime.datetime.now().strftime('%d de %B de %Y')}",
        styles["subtitle"],
    ))
    story.append(HRFlowable(width=_W, thickness=2, color=PRIMARY, spaceAfter=14))

    # Recuadro de metadatos
    meta_text = (
        f"<b>Autor del informe:</b> {settings.REPORT_AUTHOR}<br/>"
        f"<b>Dataset:</b> {dataset_url[:80]}{'...' if len(dataset_url) > 80 else ''}<br/>"
        f"<b>Registros:</b> {result.shape[0]:,} &nbsp;&nbsp; "
        f"<b>Columnas:</b> {result.shape[1]} &nbsp;&nbsp; "
        f"<b>Variables cuantitativas:</b> {len(result.quantitative_cols)} &nbsp;&nbsp; "
        f"<b>Variables cualitativas:</b> {len(result.qualitative_cols)}"
    )
    story.append(Paragraph(meta_text, styles["highlight_box"]))
    story.append(Spacer(1, 0.3 * inch))

    # ── 1. Estructura del dataset ─────────────────────────────────────────
    story.append(Paragraph("1. Estructura del Dataset", styles["section"]))
    story.append(Spacer(1, 4))

    col_data = [["Columna", "Tipo", "Nulos", "% Nulos"]]
    for col in result.columns:
        pct = result.null_pct.get(col, 0)
        color_flag = "🔴" if pct > 20 else "🟡" if pct > 5 else "🟢"
        col_data.append([col, result.dtypes.get(col, ""), str(result.null_counts.get(col, 0)), f"{pct:.1f}% {color_flag}"])

    cw = [_W * 0.35, _W * 0.20, _W * 0.20, _W * 0.25]
    t = Table(col_data, colWidths=cw, repeatRows=1)
    t.setStyle(_TABLE_HEADER_STYLE)
    story.append(t)
    story.append(Spacer(1, 8))

    # Gráfico de nulos
    null_chart = next((p for p in result.chart_paths if "nulls" in p), None)
    if null_chart and os.path.exists(null_chart):
        story.append(Paragraph("Visualización de Campos Nulos", styles["subsection"]))
        story.append(Image(null_chart, width=_W, height=2 * inch))
        story.append(Paragraph("Figura 1. Porcentaje de valores nulos por columna.", styles["caption"]))

    # ── 2. Estadísticas Descriptivas ─────────────────────────────────────
    if result.descriptive_stats is not None:
        story.append(Paragraph("2. Estadísticas Descriptivas (Variables Cuantitativas)", styles["section"]))
        story.append(Spacer(1, 4))
        desc = result.descriptive_stats.reset_index()
        desc.columns = ["Estadístico"] + list(result.descriptive_stats.columns)
        n_cols = len(desc.columns)
        col_w = [_W / n_cols] * n_cols
        story.append(_df_to_table(desc, col_widths=col_w))
        story.append(Spacer(1, 6))

    # ── 3. Análisis Cuantitativo ──────────────────────────────────────────
    quant_charts = [p for p in result.chart_paths if "/quant_" in p]
    if quant_charts:
        story.append(Paragraph("3. Distribución de Variables Cuantitativas", styles["section"]))
        for i, chart_path in enumerate(quant_charts):
            if not os.path.exists(chart_path):
                continue
            col_name = result.quantitative_cols[i] if i < len(result.quantitative_cols) else f"Variable {i+1}"
            story.append(KeepTogether([
                Paragraph(f"Variable: {col_name}", styles["subsection"]),
                Image(chart_path, width=_W, height=3 * inch),
                Paragraph(f"Figura. Histograma y boxplot de '{col_name}'.", styles["caption"]),
            ]))

    # ── 4. Análisis Cualitativo ───────────────────────────────────────────
    qual_charts = [p for p in result.chart_paths if "/qual_" in p]
    if qual_charts:
        story.append(Paragraph("4. Distribución de Variables Cualitativas", styles["section"]))
        for i, chart_path in enumerate(qual_charts):
            if not os.path.exists(chart_path):
                continue
            col_name = result.qualitative_cols[i] if i < len(result.qualitative_cols) else f"Variable {i+1}"
            story.append(KeepTogether([
                Paragraph(f"Variable: {col_name}", styles["subsection"]),
                Image(chart_path, width=_W, height=3.2 * inch),
                Paragraph(f"Figura. Frecuencia y proporción de '{col_name}'.", styles["caption"]),
            ]))

    # ── 5. Tablas de Frecuencia ───────────────────────────────────────────
    if result.frequency_tables:
        story.append(Paragraph("5. Tablas de Frecuencia", styles["section"]))
        for col, freq_df in result.frequency_tables.items():
            story.append(Paragraph(f"Columna: {col}", styles["subsection"]))
            cw2 = [_W * 0.5, _W * 0.25, _W * 0.25]
            story.append(_df_to_table(freq_df, col_widths=cw2))
            story.append(Spacer(1, 6))

    # ── 6. Tablas de Contingencia ─────────────────────────────────────────
    if result.contingency_tables:
        story.append(Paragraph("6. Tablas de Contingencia", styles["section"]))
        for ca, cb, ct_df in result.contingency_tables:
            story.append(Paragraph(f"{ca} × {cb}", styles["subsection"]))
            ct_reset = ct_df.reset_index()
            n = len(ct_reset.columns)
            cw3 = [_W / n] * n
            story.append(_df_to_table(ct_reset, col_widths=cw3, max_rows=15))
            story.append(Spacer(1, 6))

    # ── 7. Mapa de Correlación ────────────────────────────────────────────
    corr_chart = next((p for p in result.chart_paths if "correlation" in p), None)
    if corr_chart and os.path.exists(corr_chart):
        story.append(Paragraph("7. Mapa de Correlación", styles["section"]))
        story.append(Image(corr_chart, width=_W, height=min(_W * 0.75, 4 * inch)))
        story.append(Paragraph("Figura. Matriz de correlación entre variables cuantitativas.", styles["caption"]))

    # ── 8. Interpretación General ─────────────────────────────────────────
    story.append(Paragraph("8. Interpretación y Conclusiones", styles["section"]))
    story.append(Spacer(1, 4))
    for paragraph in result.interpretation.split("\n\n"):
        if paragraph.strip():
            story.append(Paragraph(paragraph.strip(), styles["body"]))
            story.append(Spacer(1, 4))

    # Nota final
    story.append(Spacer(1, 0.2 * inch))
    story.append(HRFlowable(width=_W, thickness=1, color=ACCENT, spaceAfter=8))
    story.append(Paragraph(
        f"<i>Este informe fue generado automáticamente por el sistema de análisis de datos. "
        f"Elaborado por: <b>{settings.REPORT_AUTHOR}</b>. "
        f"Fecha: {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}.</i>",
        styles["caption"],
    ))

    doc.build(story)
    return output_path
from io import BytesIO
import pandas as pd

try:
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib.colors import HexColor, white
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
    HAS_REPORTLAB = True
except Exception:
    HAS_REPORTLAB = False


if HAS_REPORTLAB:
    TEAL = HexColor("#0A8B8D")
    TEAL_LIGHT = HexColor("#14A3A5")
    TEAL_PALE = HexColor("#E6F5F5")
    DARK = HexColor("#1a1a2e")
    GRAY = HexColor("#555555")

    def build_styles():
        """Cria estilos customizados para o PDF."""
        ss = getSampleStyleSheet()
        
        ss.add(ParagraphStyle(
            "Title2", parent=ss["Title"],
            fontSize=20, leading=24, textColor=TEAL,
            alignment=TA_CENTER, spaceAfter=12,
            fontName="Helvetica-Bold",
        ))
        ss.add(ParagraphStyle(
            "H1Custom", parent=ss["Heading1"],
            fontSize=16, leading=19, textColor=TEAL,
            spaceBefore=12, spaceAfter=8,
            fontName="Helvetica-Bold",
        ))
        ss.add(ParagraphStyle(
            "H2Custom", parent=ss["Heading2"],
            fontSize=12, leading=15, textColor=DARK,
            spaceBefore=10, spaceAfter=6,
            fontName="Helvetica-Bold",
        ))
        ss.add(ParagraphStyle(
            "BodyCustom", parent=ss["Normal"],
            fontSize=9, leading=12, textColor=DARK,
            alignment=TA_JUSTIFY, spaceAfter=6,
            fontName="Helvetica",
        ))
        ss.add(ParagraphStyle(
            "TableHeader", parent=ss["Normal"],
            fontSize=8, leading=10, textColor=white,
            alignment=TA_CENTER, fontName="Helvetica-Bold",
        ))
        ss.add(ParagraphStyle(
            "TableCell", parent=ss["Normal"],
            fontSize=7.5, leading=9, textColor=DARK,
            alignment=TA_LEFT, fontName="Helvetica",
        ))
        return ss

    def styled_table(header, rows, col_widths=None, max_rows=None):
        """Cria tabela estilizada com header teal e múltiplas páginas se necessário."""
        s = build_styles()
        
        # Limitar linhas se necessário
        if max_rows and len(rows) > max_rows:
            rows = rows[:max_rows]
        
        data = [[Paragraph(str(h), s["TableHeader"]) for h in header]]
        for row in rows:
            data.append([Paragraph(str(c)[:40], s["TableCell"]) for c in row])

        t = Table(data, colWidths=col_widths, repeatRows=1, splitByRow=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), TEAL),
            ("TEXTCOLOR", (0, 0), (-1, 0), white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 8),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
            ("TOPPADDING", (0, 0), (-1, 0), 5),
            ("BACKGROUND", (0, 1), (-1, -1), white),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, TEAL_PALE]),
            ("GRID", (0, 0), (-1, -1), 0.4, HexColor("#CCCCCC")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 1), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 1), (-1, -1), 3),
        ]))
        return t


    def gerar_relatorio_chamados_abertos_pdf(df: pd.DataFrame) -> bytes:
        """Gera relatório PDF de chamados abertos com formatação profissional."""
        if df is None or df.empty:
            df = pd.DataFrame()

        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=landscape(A4),
            leftMargin=1.2 * cm,
            rightMargin=1.2 * cm,
            topMargin=1.5 * cm,
            bottomMargin=1.5 * cm,
            title="Relatório de Chamados Abertos",
        )

        elements = []
        s = build_styles()

        # Título principal
        title = Paragraph("Relatório de Chamados Abertos", s["Title2"])
        elements.append(title)
        elements.append(Spacer(1, 0.3 * cm))

        # Informações gerais
        total = len(df) if not df.empty else 0
        info_text = f"Total de Registros: <b>{total}</b>"
        elements.append(Paragraph(info_text, s["BodyCustom"]))
        elements.append(Spacer(1, 0.3 * cm))

        # Tabela principal
        if not df.empty:
            header = [str(c) for c in df.columns.tolist()]
            rows = df.fillna("-").astype(str).values.tolist()
            
            # Calcular largura das colunas (distribuir igualmente)
            available_width = 25.6 * cm  # landscape A4 - margens
            col_width = available_width / len(header)
            col_widths = [col_width] * len(header)
            
            table = styled_table(header, rows, col_widths)
            elements.append(table)

        doc.build(elements)
        pdf_bytes = buffer.getvalue()
        buffer.close()
        return pdf_bytes

else:
    def gerar_relatorio_chamados_abertos_pdf(df: pd.DataFrame) -> bytes:
        raise RuntimeError("Para exportar PDF, instale a dependência reportlab (pip install reportlab).")

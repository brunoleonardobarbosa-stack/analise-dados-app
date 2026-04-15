from io import BytesIO
import pandas as pd

try:
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib.colors import HexColor, white
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    HAS_REPORTLAB = True
except Exception:
    HAS_REPORTLAB = False


if HAS_REPORTLAB:
    TEAL = HexColor("#0A8B8D")
    TEAL_PALE = HexColor("#E6F5F5")
    DARK = HexColor("#1a1a2e")

    def styled_table(header, rows, col_widths=None):
        """Cria tabela estilizada com header teal."""
        s = getSampleStyleSheet()
        s.add(ParagraphStyle(
            "TableHeader", parent=s["Normal"],
            fontSize=8, leading=10, textColor=white,
            alignment=TA_CENTER, fontName="Helvetica-Bold",
            wordWrap='LTR', splitLongWords=True,
        ))
        s.add(ParagraphStyle(
            "TableCell", parent=s["Normal"],
            fontSize=7, leading=9, textColor=DARK,
            alignment=TA_LEFT, fontName="Helvetica",
            wordWrap='LTR', splitLongWords=True,
        ))
        
        # Truncar texto muito longo
        max_cell_length = 50
        header_truncated = [str(h)[:max_cell_length] for h in header]
        data = [[Paragraph(h, s["TableHeader"]) for h in header_truncated]]
        for row in rows:
            truncated_row = [str(c)[:max_cell_length] for c in row]
            data.append([Paragraph(t, s["TableCell"]) for t in truncated_row])

        # Calcular larguras automáticas se não fornecidas
        if col_widths is None:
            # Largura disponível em landscape: ~280mm - margens 3mm = 274mm
            available_width = 274 * 0.28 * 100 / 2.54  # converter para pontos
            num_cols = len(header)
            col_widths = [available_width / num_cols] * num_cols

        t = Table(data, colWidths=col_widths, repeatRows=1, splitByRow=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), TEAL),
            ("TEXTCOLOR", (0, 0), (-1, 0), white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 8),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 4),
            ("TOPPADDING", (0, 0), (-1, 0), 4),
            ("BACKGROUND", (0, 1), (-1, -1), white),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, TEAL_PALE]),
            ("GRID", (0, 0), (-1, -1), 0.4, HexColor("#CCCCCC")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 1), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 1), (-1, -1), 2),
        ]))
        return t


    def gerar_relatorio_chamados_abertos_pdf(df: pd.DataFrame) -> bytes:
        if df is None:
            df = pd.DataFrame()

        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=landscape(A4),
            leftMargin=1.5 * cm,
            rightMargin=1.5 * cm,
            topMargin=1.5 * cm,
            bottomMargin=1.5 * cm,
            title="Relatório de Chamados Abertos",
        )

        elements = []
        styles = getSampleStyleSheet()

        title = Paragraph("Relatório de Chamados Abertos", styles.get('Title', styles['Normal']))
        elements.append(title)
        elements.append(Spacer(1, 0.5 * cm))

        # Preparar dados para a tabela
        header = [str(c) for c in df.columns.tolist()]
        rows = df.fillna("-").astype(str).values.tolist()

        # Adicionar tabela
        table = styled_table(header, rows)
        elements.append(table)

        doc.build(elements)
        pdf_bytes = buffer.getvalue()
        buffer.close()
        return pdf_bytes

else:
    def gerar_relatorio_chamados_abertos_pdf(df: pd.DataFrame) -> bytes:
        raise RuntimeError("Para exportar PDF, instale a dependência reportlab (pip install reportlab).")

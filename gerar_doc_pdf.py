"""
Gera PDF de documentaÃ§Ã£o do Dashboard DASA Engenharia ClÃ­nica.
Uso: python gerar_doc_pdf.py
SaÃ­da: documentacao_dashboard_dasa.pdf
"""

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.lib.colors import HexColor, white, black
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak,
    KeepTogether, HRFlowable,
)

TEAL = HexColor("#0A8B8D")
TEAL_LIGHT = HexColor("#14A3A5")
TEAL_PALE = HexColor("#E6F5F5")
DARK = HexColor("#1a1a2e")
GRAY = HexColor("#555555")
LIGHT_BG = HexColor("#F5F7FA")

OUTPUT = "documentacao_dashboard_dasa.pdf"


def build_styles():
    ss = getSampleStyleSheet()

    ss.add(ParagraphStyle(
        "CoverTitle", parent=ss["Title"],
        fontSize=28, leading=34, textColor=white,
        alignment=TA_CENTER, spaceAfter=6,
        fontName="Helvetica-Bold",
    ))
    ss.add(ParagraphStyle(
        "CoverSub", parent=ss["Normal"],
        fontSize=14, leading=18, textColor=HexColor("#d0f0f0"),
        alignment=TA_CENTER, spaceAfter=4,
        fontName="Helvetica",
    ))
    ss.add(ParagraphStyle(
        "H1", parent=ss["Heading1"],
        fontSize=18, leading=22, textColor=TEAL,
        spaceBefore=18, spaceAfter=8,
        fontName="Helvetica-Bold",
        borderWidth=0, borderPadding=0,
    ))
    ss.add(ParagraphStyle(
        "H2", parent=ss["Heading2"],
        fontSize=14, leading=17, textColor=DARK,
        spaceBefore=12, spaceAfter=6,
        fontName="Helvetica-Bold",
    ))
    ss.add(ParagraphStyle(
        "H3", parent=ss["Heading3"],
        fontSize=11, leading=14, textColor=TEAL,
        spaceBefore=8, spaceAfter=4,
        fontName="Helvetica-BoldOblique",
    ))
    ss.add(ParagraphStyle(
        "Body", parent=ss["Normal"],
        fontSize=10, leading=14, textColor=GRAY,
        alignment=TA_JUSTIFY, spaceAfter=6,
        fontName="Helvetica",
    ))
    ss.add(ParagraphStyle(
        "BodyBold", parent=ss["Normal"],
        fontSize=10, leading=14, textColor=DARK,
        alignment=TA_LEFT, spaceAfter=4,
        fontName="Helvetica-Bold",
    ))
    ss.add(ParagraphStyle(
        "BulletCustom", parent=ss["Normal"],
        fontSize=10, leading=14, textColor=GRAY,
        alignment=TA_LEFT, spaceAfter=3,
        fontName="Helvetica",
        leftIndent=16, bulletIndent=6,
    ))
    ss.add(ParagraphStyle(
        "TableHeader", parent=ss["Normal"],
        fontSize=9, leading=11, textColor=white,
        alignment=TA_CENTER, fontName="Helvetica-Bold",
    ))
    ss.add(ParagraphStyle(
        "TableCell", parent=ss["Normal"],
        fontSize=8.5, leading=11, textColor=DARK,
        alignment=TA_LEFT, fontName="Helvetica",
    ))
    ss.add(ParagraphStyle(
        "TableCellCenter", parent=ss["Normal"],
        fontSize=8.5, leading=11, textColor=DARK,
        alignment=TA_CENTER, fontName="Helvetica",
    ))
    ss.add(ParagraphStyle(
        "Footer", parent=ss["Normal"],
        fontSize=8, leading=10, textColor=HexColor("#999999"),
        alignment=TA_CENTER,
    ))
    return ss


def divider():
    return HRFlowable(width="100%", thickness=1, color=TEAL_LIGHT, spaceBefore=6, spaceAfter=6)


def styled_table(header, rows, col_widths=None):
    """Cria tabela estilizada com header teal."""
    s = build_styles()
    data = [[Paragraph(h, s["TableHeader"]) for h in header]]
    for row in rows:
        data.append([Paragraph(str(c), s["TableCell"]) for c in row])

    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), TEAL),
        ("TEXTCOLOR", (0, 0), (-1, 0), white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
        ("TOPPADDING", (0, 0), (-1, 0), 6),
        ("BACKGROUND", (0, 1), (-1, -1), white),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, TEAL_PALE]),
        ("GRID", (0, 0), (-1, -1), 0.4, HexColor("#CCCCCC")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 1), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
    ]))
    return t


def cover_page():
    """Retorna elementos da capa."""
    s = build_styles()
    # Simula fundo teal com tabela de fundo
    cover_data = [[""]]
    cover_tbl = Table(cover_data, colWidths=[19 * cm], rowHeights=[26 * cm])
    cover_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), TEAL),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ]))

    elements = [
        Spacer(1, 5 * cm),
        Paragraph("DASA", s["CoverTitle"]),
        Paragraph("Engenharia ClÃ­nica â€” AC", s["CoverSub"]),
        Spacer(1, 1.2 * cm),
        Paragraph("DocumentaÃ§Ã£o do Dashboard AnalÃ­tico", ParagraphStyle(
            "coverDesc", parent=s["CoverSub"], fontSize=16, textColor=TEAL,
            fontName="Helvetica-Bold",
        )),
        Spacer(1, 0.6 * cm),
        Paragraph("Melhorias Visuais Â· GrÃ¡ficos Â· CÃ¡lculos Â· Racional", ParagraphStyle(
            "coverTags", parent=s["CoverSub"], fontSize=11, textColor=TEAL_LIGHT,
        )),
        Spacer(1, 2 * cm),
        divider(),
        Paragraph("VersÃ£o 2.4 â€” MarÃ§o 2026", ParagraphStyle(
            "coverVer", parent=s["Body"], alignment=TA_CENTER, textColor=TEAL,
            fontSize=10,
        )),
        Paragraph("Autor: Bruno Leonardo Barbosa", ParagraphStyle(
            "coverAuthor", parent=s["Body"], alignment=TA_CENTER, textColor=GRAY,
            fontSize=10,
        )),
        PageBreak(),
    ]
    return elements


def build_pdf():
    s = build_styles()
    doc = SimpleDocTemplate(
        OUTPUT,
        pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=1.8 * cm, bottomMargin=1.8 * cm,
        title="DocumentaÃ§Ã£o Dashboard DASA Engenharia ClÃ­nica",
        author="Bruno Leonardo Barbosa",
    )

    elements = []

    # â”€â”€ CAPA â”€â”€
    elements += cover_page()

    # â”€â”€ SUMÃRIO â”€â”€
    elements.append(Paragraph("SumÃ¡rio", s["H1"]))
    sumario = [
        "1. VisÃ£o Geral do Projeto",
        "2. Arquitetura e Tecnologias",
        "3. Melhorias Visuais (Design Arkmeds)",
        "4. Filtros DisponÃ­veis",
        "5. CartÃµes KPI â€” Indicadores Principais",
        "6. GrÃ¡ficos e VisualizaÃ§Ãµes",
        "7. Tabelas de Dados",
        "8. Abas do Dashboard",
        "9. Motor de InteligÃªncia AnalÃ­tica (Local)",
        "10. Chat Interativo (Pergunte sobre seus dados)",
        "11. FunÃ§Ãµes Principais e Racional de CÃ¡lculo",
        "12. ExportaÃ§Ãµes (PDF, CSV, Excel)",
    ]
    for item in sumario:
        elements.append(Paragraph(f"â€¢ {item}", s["BulletCustom"]))
    elements.append(PageBreak())

    # â”€â”€ 1. VISÃƒO GERAL â”€â”€
    elements.append(Paragraph("1. VisÃ£o Geral do Projeto", s["H1"]))
    elements.append(Paragraph(
        "O Dashboard DASA Engenharia ClÃ­nica Ã© uma aplicaÃ§Ã£o web construÃ­da em Streamlit "
        "para anÃ¡lise operacional de chamados de manutenÃ§Ã£o de equipamentos mÃ©dicos. "
        "Ele permite o upload de planilhas Excel com dados de ordens de serviÃ§o e gera "
        "automaticamente KPIs, grÃ¡ficos, tabelas de diagnÃ³stico e relatÃ³rios exportÃ¡veis.",
        s["Body"],
    ))
    elements.append(Paragraph(
        "O sistema foi projetado para apoiar a tomada de decisÃ£o da equipe de Engenharia "
        "ClÃ­nica da DASA (unidade Acre), oferecendo visibilidade sobre backlog, criticidade, "
        "eficiÃªncia de atendimento, reincidÃªncia pÃ³s-preventiva e anÃ¡lise de causa raiz.",
        s["Body"],
    ))
    elements.append(Spacer(1, 6))

    # â”€â”€ 2. ARQUITETURA â”€â”€
    elements.append(Paragraph("2. Arquitetura e Tecnologias", s["H1"]))
    tech_rows = [
        ["Streamlit", "Framework web para dashboards interativos em Python"],
        ["Pandas", "ManipulaÃ§Ã£o e anÃ¡lise de dados tabulares"],
        ["Plotly Express", "GrÃ¡ficos interativos (barras, cores, tooltips)"],
        ["ReportLab", "GeraÃ§Ã£o de PDFs executivos e relatÃ³rios"],
        ["Openpyxl / Xlrd", "Leitura de arquivos Excel (.xlsx e .xls)"],
        ["Streamlit Cloud", "Deploy e hospedagem da aplicaÃ§Ã£o"],
        ["GitHub", "Versionamento de cÃ³digo (repositÃ³rio privado)"],
    ]
    elements.append(styled_table(["Tecnologia", "Uso"], tech_rows, [4.5 * cm, 12.5 * cm]))
    elements.append(Spacer(1, 6))
    elements.append(Paragraph(
        "<b>Arquivo principal:</b> app.py (~4.200 linhas)<br/>"
        "<b>Deploy:</b> Streamlit Cloud (branch main)<br/>"
        "<b>Paleta:</b> Teal / Turquesa estilo Arkmeds",
        s["Body"],
    ))
    elements.append(PageBreak())

    # â”€â”€ 3. MELHORIAS VISUAIS â”€â”€
    elements.append(Paragraph("3. Melhorias Visuais (Design Arkmeds)", s["H1"]))
    elements.append(Paragraph(
        "O layout foi completamente redesenhado para seguir a identidade visual do sistema "
        "Arkmeds (dasa.arkmeds.com), substituindo a paleta anterior azul/laranja por tons de "
        "teal/turquesa com design limpo e flat.",
        s["Body"],
    ))

    elements.append(Paragraph("3.1 Paleta de Cores", s["H2"]))
    colors_rows = [
        ["--dasa-blue (PrimÃ¡ria)", "#0A8B8D", "Teal principal â€” headers, bordas, destaques"],
        ["--dasa-blue-light", "#14A3A5", "Teal claro â€” hovers, acentos"],
        ["--dasa-blue-pale", "#E6F5F5", "Background pÃ¡lido â€” alternÃ¢ncia de linhas"],
        ["--dasa-orange", "#0E7C7B", "Teal secundÃ¡rio (antigo laranja)"],
        ["--ec-bg", "#F5F7FA", "Fundo geral da aplicaÃ§Ã£o"],
        ["--ec-border", "#D2E3E3", "Bordas de cards e painÃ©is"],
    ]
    elements.append(styled_table(
        ["VariÃ¡vel CSS", "Hex", "Uso"],
        colors_rows, [5 * cm, 2.5 * cm, 9.5 * cm],
    ))

    elements.append(Paragraph("3.2 Componentes Visuais", s["H2"]))
    visual_items = [
        ("<b>Header/Brand:</b> Gradiente teal (#0A8B8D â†’ #067375 â†’ #056d6f) com duas engrenagens "
         "SVG animadas â€” uma grande girando no sentido horÃ¡rio (8s) e uma menor girando no "
         "sentido anti-horÃ¡rio (5s). TÃ­tulo 'DASA' 38px bold + subtÃ­tulo 'Engenharia ClÃ­nica â€” AC'."),
        ("<b>KPI Cards:</b> Fundo branco, borda esquerda 3px teal, tÃ­tulo uppercase 0.8rem, "
         "valor grande 1.5rem bold, subtÃ­tulo trend 0.78rem. Hover amplia sombra. "
         "BotÃ£o 'i' circular com tooltip detalhado de cada mÃ©trica."),
        ("<b>Sidebar:</b> Gradiente vertical teal, inputs com fundo semi-transparente, textos brancos."),
        ("<b>PainÃ©is (ec-panel):</b> Fundo branco, barra teal 3px no topo, border-radius 12px, sombra sutil."),
        ("<b>CartÃµes de chamados:</b> Borda esquerda 4px teal, grid responsivo de items com fundo pÃ¡lido."),
        ("<b>Abas:</b> Sem background, borda inferior 3px teal na aba ativa, font-weight 900."),
        ("<b>Upload Panel:</b> Borda 2px dashed teal, centralizado, com Ã­cone SVG."),
        ("<b>Pills de Status:</b> Vermelho (risco alto), amarelo (atenÃ§Ã£o), verde (ok)."),
    ]
    for item in visual_items:
        elements.append(Paragraph(f"â€¢ {item}", s["BulletCustom"]))

    elements.append(Paragraph("3.3 AnimaÃ§Ãµes", s["H2"]))
    anim_rows = [
        ["fadeInUp", "Entrada de seÃ§Ãµes de baixo p/ cima"],
        ["fadeIn", "Aparecimento gradual"],
        ["slideInLeft", "Entrada lateral de cards"],
        ["spinGear (8s)", "RotaÃ§Ã£o horÃ¡ria da engrenagem grande"],
        ["spinGearReverse (5s)", "RotaÃ§Ã£o anti-horÃ¡ria da engrenagem pequena"],
        ["pulseGlow", "Brilho pulsante em elementos de foco"],
        ["shimmer", "Efeito shimmer no header"],
        ["gradientFlow", "Gradiente animado no brand card"],
    ]
    elements.append(styled_table(["AnimaÃ§Ã£o", "Efeito"], anim_rows, [5 * cm, 12 * cm]))

    elements.append(Paragraph("3.4 Responsividade", s["H2"]))
    elements.append(Paragraph(
        "3 breakpoints adaptam o layout: 1200px (grid 2â†’1 coluna), 760px (sidebar compacta), "
        "680px (KPI cards em coluna Ãºnica). Grid CSS <code>auto-fit minmax(210px, 1fr)</code>.",
        s["Body"],
    ))
    elements.append(PageBreak())

    # â”€â”€ 4. FILTROS â”€â”€
    elements.append(Paragraph("4. Filtros DisponÃ­veis", s["H1"]))
    elements.append(Paragraph(
        "A sidebar lateral oferece filtros que sÃ£o aplicados globalmente a todas as abas e grÃ¡ficos:",
        s["Body"],
    ))
    filtros_rows = [
        ["Quadro de Trabalho", "Checkboxes com busca textual",
         "Lista todos os quadros da planilha. Suporta busca por texto, botÃµes 'Todos'/'Nenhum'. Container scrollÃ¡vel."],
        ["Tipo de ServiÃ§o", "Radio horizontal",
         "OpÃ§Ãµes: Todos, Corretiva, Preventiva, CalibraÃ§Ã£o. Filtra pela coluna TIPO_SERVICO normalizada."],
        ["PerÃ­odo (De / AtÃ©)", "2 date_input",
         "Range de datas detectado automaticamente da planilha. Filtra por DATA_ABERTURA."],
        ["Pesquisa Global", "Text input + selectbox",
         "Busca em 11 colunas: TAG, Modelo, Fabricante, Falha, Quadro, Tipo Equipamento, "
         "Solicitante, ObservaÃ§Ã£o, NÂº Chamado, Origem, Criticidade. Autocomplete de TAGs."],
        ["Limpar Filtros", "BotÃ£o",
         "Reseta todos os filtros para o estado padrÃ£o e recarrega a pÃ¡gina."],
    ]
    elements.append(styled_table(
        ["Filtro", "Widget", "Comportamento"],
        filtros_rows, [3.8 * cm, 3.5 * cm, 9.7 * cm],
    ))
    elements.append(PageBreak())

    # â”€â”€ 5. KPI CARDS â”€â”€
    elements.append(Paragraph("5. CartÃµes KPI â€” Indicadores Principais", s["H1"]))
    elements.append(Paragraph(
        "9 cartÃµes dispostos em grid responsivo no topo da aba 'Dashboard Gerencial'. "
        "Cada cartÃ£o exibe tÃ­tulo, valor numÃ©rico e subtÃ­tulo descritivo, alÃ©m de tooltip "
        "com a fÃ³rmula de cÃ¡lculo.",
        s["Body"],
    ))

    kpi_rows = [
        ["<b>Disponibilidade Global</b>",
         "100% âˆ’ (cancelados / total) Ã— 100",
         "Mede a estabilidade operacional geral. Quanto mais prÃ³ximo de 100%, menos cancelamentos."],
        ["<b>Chamados CrÃ­ticos em Aberto</b>",
         "count(STATUS=ABERTO AND CRITICIDADE=ALTA)",
         "Destaca urgÃªncias para priorizaÃ§Ã£o imediata. Valor alto = atenÃ§Ã£o."],
        ["<b>Tempo MÃ©dio de Atendimento</b>",
         "mÃ©dia(DATA_FECHAMENTO âˆ’ DATA_ABERTURA) em dias, para fechados",
         "Controla eficiÃªncia de resoluÃ§Ã£o. Meta operacional â‰¤ 15 dias. Exibe 'N/D' se nÃ£o hÃ¡ fechados."],
        ["<b>Volume de Chamados</b>",
         "abertos / fechados",
         "Compara carga atual (demanda) vs. capacidade de resoluÃ§Ã£o. Se abertos > fechados, fila crescendo."],
        ["<b>Backlog &gt;30 dias</b>",
         "count(abertos com Faixa = '>30 dias')",
         "Chamados envelhecidos com maior risco de impacto operacional. Fila crÃ­tica."],
        ["<b>Taxa de Fechamento</b>",
         "(fechados / total) Ã— 100",
         "Indica efetividade do time na conversÃ£o de chamados em resoluÃ§Ãµes."],
        ["<b>Corretiva em Aberto</b>",
         "count(STATUS=ABERTO AND tipo_normalizado=CORRETIVA)",
         "Volume de manutenÃ§Ãµes corretivas (reparo de falhas) ainda pendentes."],
        ["<b>Preventiva em Aberto</b>",
         "count(STATUS=ABERTO AND tipo_normalizado=PREVENTIVA)",
         "Volume de manutenÃ§Ãµes preventivas (programadas) ainda pendentes."],
        ["<b>CalibraÃ§Ã£o em Aberto</b>",
         "count(STATUS=ABERTO AND tipo_normalizado=CALIBRACAO)",
         "CalibraÃ§Ãµes e verificaÃ§Ãµes metrolÃ³gicas pendentes. Inclui verificaÃ§Ãµes."],
    ]
    elements.append(styled_table(
        ["CartÃ£o", "FÃ³rmula / LÃ³gica", "Racional"],
        kpi_rows, [4.2 * cm, 6 * cm, 6.8 * cm],
    ))
    elements.append(PageBreak())

    # â”€â”€ 6. GRÃFICOS â”€â”€
    elements.append(Paragraph("6. GrÃ¡ficos e VisualizaÃ§Ãµes", s["H1"]))

    elements.append(Paragraph("6.1 Aging de Chamados (Barras)", s["H2"]))
    elements.append(Paragraph(
        "<b>Tipo:</b> Barras verticais (px.bar)<br/>"
        "<b>LocalizaÃ§Ã£o:</b> Tab 1 â€” Dashboard Gerencial<br/>"
        "<b>Dados:</b> DataFrame aging com 4 faixas: 0-7 dias, 7-14 dias, 14-30 dias, >30 dias<br/>"
        "<b>Cores:</b> Verde (0-7) â†’ Amarelo (7-14) â†’ Laranja (14-30) â†’ Vermelho (>30)<br/>"
        "<b>Interatividade:</b> Clique em uma barra filtra a tabela de detalhes abaixo",
        s["Body"],
    ))
    elements.append(Paragraph(
        "<b>Racional:</b> O aging mostra a distribuiÃ§Ã£o dos chamados abertos por tempo de espera. "
        "Permite identificar rapidamente se hÃ¡ acÃºmulo de chamados envelhecidos (>30 dias) que "
        "representam maior risco operacional. A escala de cores age como semÃ¡foro visual.",
        s["Body"],
    ))
    elements.append(divider())

    elements.append(Paragraph("6.2 Pareto de Custos Ã— Falhas (Barras)", s["H2"]))
    elements.append(Paragraph(
        "<b>Tipo:</b> Barras verticais (px.bar)<br/>"
        "<b>LocalizaÃ§Ã£o:</b> Tab 1 â€” Dashboard Gerencial<br/>"
        "<b>Dados:</b> Top 8 falhas por frequÃªncia de ocorrÃªncia<br/>"
        "<b>Cor:</b> Teal fixo<br/>"
        "<b>Interatividade:</b> Clique em uma barra filtra detalhes daquela falha",
        s["Body"],
    ))
    elements.append(Paragraph(
        "<b>Racional:</b> Baseado no PrincÃ­pio de Pareto (80/20), identifica as falhas mais "
        "recorrentes que concentram o maior volume de chamados. Permite focar esforÃ§os nas "
        "causas que geram mais impacto. Limitado a top 8 para clareza visual.",
        s["Body"],
    ))
    elements.append(divider())

    elements.append(Paragraph("6.3 Faixas PÃ³s-Preventiva (Barras)", s["H2"]))
    elements.append(Paragraph(
        "<b>Tipo:</b> Barras verticais (px.bar)<br/>"
        "<b>LocalizaÃ§Ã£o:</b> Tab 4 â€” PÃ³s-Preventiva<br/>"
        "<b>Dados:</b> Corretivas agrupadas por faixa de intervalo apÃ³s preventiva (0-2, 3-10, 11-20, 21-30 dias)<br/>"
        "<b>Cores:</b> Verde â†’ Vermelho proporcional Ã  proximidade com a preventiva",
        s["Body"],
    ))
    elements.append(Paragraph(
        "<b>Racional:</b> Quando uma manutenÃ§Ã£o corretiva ocorre poucos dias apÃ³s uma preventiva "
        "no mesmo equipamento (TAG), indica falha na prevenÃ§Ã£o ou problema crÃ´nico. "
        "Faixa 0-2 dias Ã© a mais crÃ­tica â€” sugere que a preventiva nÃ£o foi eficaz. "
        "O limite de 30 dias garante relaÃ§Ã£o causal plausÃ­vel entre os dois eventos.",
        s["Body"],
    ))
    elements.append(divider())

    elements.append(Paragraph("6.4 Ranking TAGs PÃ³s-Preventiva (Barras Horizontais)", s["H2"]))
    elements.append(Paragraph(
        "<b>Tipo:</b> Barras horizontais (px.bar)<br/>"
        "<b>LocalizaÃ§Ã£o:</b> Tab 4 â€” PÃ³s-Preventiva<br/>"
        "<b>Dados:</b> Top 15 TAGs com mais reincidÃªncia corretiva pÃ³s-preventiva<br/>"
        "<b>Cor:</b> Escala contÃ­nua Blues â€” quanto menor o intervalo mÃ©dio, mais escuro",
        s["Body"],
    ))
    elements.append(Paragraph(
        "<b>Racional:</b> Identifica os equipamentos especÃ­ficos (por TAG) que mais apresentam "
        "falhas logo apÃ³s a manutenÃ§Ã£o preventiva. Um equipamento no topo com intervalo mÃ©dio "
        "curto Ã© candidato a revisÃ£o do plano de manutenÃ§Ã£o ou possÃ­vel substituiÃ§Ã£o.",
        s["Body"],
    ))
    elements.append(PageBreak())

    # â”€â”€ 7. TABELAS â”€â”€
    elements.append(Paragraph("7. Tabelas de Dados", s["H1"]))

    tabelas_rows = [
        ["<b>Radar de Risco Operacional</b>", "Tab 1",
         "Top 12 chamados abertos ranqueados por score de risco. Score = (criticidade Ã— 10) + (dias_parado / 3). "
         "Colunas: Modelo, Setor, Status/SLA, NÃ­vel/Risco, RecomendaÃ§Ã£o."],
        ["<b>Lista de Chamados Abertos</b>", "Tab 2",
         "Todos os chamados com status ABERTO. Colunas: Quadro, NÂº Chamado, Tipo Equipamento, TAG, Modelo, "
         "Fabricante, Solicitante, ObservaÃ§Ã£o, Dias Parado, Falha."],
        ["<b>MTBF Top 10</b>", "Tab 3",
         "Equipamentos com menor MTBF (Mean Time Between Failures). Quanto menor o MTBF, mais frequente a falha. "
         "Colunas: Modelo, Fabricante, TAG, Falhas, MTBF (dias)."],
        ["<b>Problema Ã— Origem</b>", "Tab 3",
         "Cruza problema relatado com origem do problema para equipamento selecionado. "
         "Permite anÃ¡lise de causa raiz por equipamento."],
        ["<b>Tabela PÃ³s-Preventiva</b>", "Tab 4",
         "Detalhamento de corretivas que ocorreram atÃ© 30 dias apÃ³s preventiva no mesmo TAG. "
         "Colunas: TAG, Modelo, Data Prev., Data Corr., Intervalo, Faixa, Falha, Criticidade."],
        ["<b>Quadros Sobrecarregados</b>", "Tab 5",
         "Ranking de Quadros de Trabalho por carga operacional. "
         "Colunas: Quadro, Abertos, MÃ©dia Dias, Alta Criticidade."],
        ["<b>Detalhes por Aging/Pareto</b>", "Tab 1 (toggle)",
         "Ao clicar em barra do grÃ¡fico de Aging ou Pareto, exibe lista detalhada de chamados correspondentes."],
    ]
    elements.append(styled_table(
        ["Tabela", "LocalizaÃ§Ã£o", "DescriÃ§Ã£o e Colunas"],
        tabelas_rows, [4.5 * cm, 2 * cm, 10.5 * cm],
    ))
    elements.append(PageBreak())

    # â”€â”€ 8. ABAS â”€â”€
    elements.append(Paragraph("8. Abas do Dashboard", s["H1"]))

    tabs_data = [
        ("Tab 1 â€” Dashboard Gerencial", [
            "9 KPI Cards (Disponibilidade, CrÃ­ticos, MTTR, Volume, Backlog, Taxa Fechamento, "
            "Corretiva/Preventiva/CalibraÃ§Ã£o em Aberto)",
            "GrÃ¡fico de Aging (barras por faixa de dias)",
            "GrÃ¡fico Pareto (top 8 falhas por frequÃªncia)",
            "Painel de Risco Operacional (pills vermelho/amarelo/verde)",
            "AÃ§Ãµes Recomendadas (atÃ© 4 aÃ§Ãµes prioritÃ¡rias baseadas nos KPIs)",
            "Tabela Radar de Risco (top 12 chamados por score)",
            "Toggle de detalhes por clique nos grÃ¡ficos",
            "BotÃ£o download PDF executivo",
        ]),
        ("Tab 2 â€” RelatÃ³rio Detalhado (Abertos)", [
            "Cards-resumo: total abertos, mÃ©dia dias parado, pior SLA",
            "Tabela completa de todos os chamados abertos",
            "Download CSV e Excel",
            "Download PDF agrupado por quadro de trabalho",
            "VisualizaÃ§Ã£o em cartÃµes HTML (todos ou por quadro)",
        ]),
        ("Tab 3 â€” Fiabilidade e HistÃ³rico (MTBF)", [
            "Tabela MTBF Top 10 â€” equipamentos com menor tempo entre falhas",
            "Selectbox para escolher equipamento especÃ­fico",
            "Tabela Problema Ã— Origem â€” anÃ¡lise de causa raiz",
            "BotÃ£o drill-down para modal de detalhes do chamado",
        ]),
        ("Tab 4 â€” PÃ³s-Preventiva (â‰¤30 dias)", [
            "4 mÃ©tricas-resumo por faixa de intervalo",
            "GrÃ¡fico de barras por faixa (0-2, 3-10, 11-20, 21-30 dias)",
            "Ranking horizontal Top 15 TAGs reincidentes",
            "Selectbox para filtrar por faixa especÃ­fica",
            "Tabela completa de chamados pÃ³s-preventiva",
            "CartÃµes HTML de detalhes por clique",
        ]),
        ("Tab 5 â€” InteligÃªncia AnalÃ­tica", [
            "Nota Operacional (0-100) com cor e Ã­cone contextual",
            "Resumo Executivo textual gerado automaticamente",
            "Tabela de Quadros Mais Sobrecarregados",
            "Chat interativo â€” campo de pergunta livre",
            "5 botÃµes de sugestÃ£o rÃ¡pida (backlog, crÃ­ticos, falhas, equipes, preventiva)",
            "HistÃ³rico de conversa na sessÃ£o",
        ]),
    ]

    for tab_title, items in tabs_data:
        elements.append(Paragraph(tab_title, s["H2"]))
        for item in items:
            elements.append(Paragraph(f"â€¢ {item}", s["BulletCustom"]))
        elements.append(Spacer(1, 4))

    elements.append(PageBreak())

    # â”€â”€ 9. MOTOR IA LOCAL â”€â”€
    elements.append(Paragraph("9. Motor de InteligÃªncia AnalÃ­tica (Local)", s["H1"]))
    elements.append(Paragraph(
        "O motor de inteligÃªncia analÃ­tica Ã© 100% local â€” nÃ£o utiliza APIs externas nem LLMs. "
        "Toda a anÃ¡lise Ã© feita com cÃ¡lculos sobre os dados filtrados.",
        s["Body"],
    ))

    elements.append(Paragraph("9.1 Nota Operacional (0-100)", s["H2"]))
    elements.append(Paragraph(
        "A nota Ã© composta por 5 fatores ponderados:<br/><br/>"
        "<b>1. Nota de Backlog (peso 25):</b> Penaliza backlog >30 dias. "
        "Se >20% dos abertos estÃ£o nessa faixa â†’ 0 pontos. Se 0% â†’ 25 pontos.<br/>"
        "<b>2. Nota MTTR (peso 25):</b> Meta â‰¤ 15 dias. Se MTTR > 30 â†’ 0 pontos. "
        "Se â‰¤ 15 â†’ 25 pontos. InterpolaÃ§Ã£o linear entre 15-30.<br/>"
        "<b>3. Nota Fechamento (peso 20):</b> Se taxa >80% â†’ 20 pontos. Se <30% â†’ 0 pontos.<br/>"
        "<b>4. Nota Criticidade (peso 15):</b> Penaliza alta criticidade em aberto. "
        "Se >15% dos abertos sÃ£o ALTA â†’ 0 pontos. Se 0 â†’ 15 pontos.<br/>"
        "<b>5. Nota Cancelamento (peso 15):</b> Se <5% cancelados â†’ 15 pontos. "
        "Se >20% â†’ 0 pontos.",
        s["Body"],
    ))

    elements.append(Paragraph("9.2 Resumo Executivo", s["H2"]))
    elements.append(Paragraph(
        "Texto gerado automaticamente baseado nos KPIs filtrados. Inclui: total de chamados, "
        "abertos/fechados, mÃ©dia de atendimento, percentual de cancelamentos, alertas de "
        "criticidade, equipamentos mais problemÃ¡ticos e recomendaÃ§Ãµes priorizadas.",
        s["Body"],
    ))

    elements.append(Paragraph("9.3 Quadros Sobrecarregados", s["H2"]))
    elements.append(Paragraph(
        "Ranking dos Quadros de Trabalho ordenado por volume de abertos e mÃ©dia de dias parado. "
        "Permite identificar onde a carga operacional estÃ¡ mais concentrada.",
        s["Body"],
    ))
    elements.append(PageBreak())

    # â”€â”€ 10. CHAT â”€â”€
    elements.append(Paragraph("10. Chat Interativo (Pergunte sobre seus dados)", s["H1"]))
    elements.append(Paragraph(
        "O chat utiliza um engine de NLP local baseado em pattern matching com 10 categorias "
        "de intenÃ§Ã£o. NÃ£o requer API externa.",
        s["Body"],
    ))

    chat_rows = [
        ["Backlog", "backlog, fila, espera, aging, envelhecidos",
         "Detalhamento por faixa de aging e alertas sobre >30 dias"],
        ["CrÃ­ticos", "critico, urgente, alta criticidade, prioridade",
         "Quantidade e percentual de chamados ALTA criticidade em aberto"],
        ["Top Falhas", "falha, defeito, problema, pareto",
         "Top 5 falhas mais frequentes com quantidade e percentual"],
        ["Equipes", "quadro, equipe, time, setor, responsavel",
         "Top 5 quadros mais sobrecarregados com mÃ©tricas"],
        ["Preventiva", "preventiva, manutencao, prevencao",
         "Status das preventivas: total, percentual do total, em aberto"],
        ["CalibraÃ§Ã£o", "calibra, verific, metrolog",
         "Status das calibraÃ§Ãµes/verificaÃ§Ãµes em aberto"],
        ["Fechamento", "fechamento, resolvido, concluido, encerrado",
         "Taxa de fechamento e MTTR com indicaÃ§Ã£o de meta"],
        ["MTBF", "mtbf, confiabilidade, recorrencia, reincid",
         "Top 3 equipamentos com menor MTBF (maior reincidÃªncia)"],
        ["Geral", "resumo, geral, visao, panorama, status",
         "Nota operacional, resumo de indicadores, alertas"],
        ["Corretiva", "corretiva, reparo, conserto",
         "Volume de corretivas em aberto e percentual"],
    ]
    elements.append(styled_table(
        ["Categoria", "Palavras-Chave Detectadas", "Tipo de Resposta"],
        chat_rows, [2.5 * cm, 6 * cm, 8.5 * cm],
    ))

    elements.append(Paragraph(
        "5 botÃµes de sugestÃ£o rÃ¡pida aparecem abaixo do campo de input, facilitando perguntas comuns. "
        "O histÃ³rico da conversa Ã© mantido durante a sessÃ£o do usuÃ¡rio.",
        s["Body"],
    ))
    elements.append(PageBreak())

    # â”€â”€ 11. FUNÃ‡Ã•ES PRINCIPAIS â”€â”€
    elements.append(Paragraph("11. FunÃ§Ãµes Principais e Racional de CÃ¡lculo", s["H1"]))

    funcs = [
        ("compute_metrics(df)", "~L854",
         "Calcula todos os KPIs principais a partir do DataFrame filtrado.",
         "â€¢ <b>Abertos:</b> count(STATUS normalizado = ABERTO)<br/>"
         "â€¢ <b>Fechados:</b> count(STATUS normalizado = FECHADO)<br/>"
         "â€¢ <b>Cancelados:</b> count(STATUS normalizado = CANCELADO)<br/>"
         "â€¢ <b>Total:</b> len(df) â€” todos os registros no filtro<br/>"
         "â€¢ <b>% Cancelados:</b> (cancelados / total) Ã— 100<br/>"
         "â€¢ <b>Alta Criticidade:</b> count(ABERTO AND CRITICIDADE = ALTA)<br/>"
         "â€¢ <b>MTTR:</b> mÃ©dia de (DATA_FECHAMENTO âˆ’ DATA_ABERTURA).days para fechados com duraÃ§Ã£o â‰¥ 0<br/>"
         "â€¢ <b>Corretiva/Preventiva/CalibraÃ§Ã£o:</b> count(ABERTO AND tipo_normalizado = X)"),

        ("build_aging_dataframe(df)", "~L889",
         "Agrupa chamados abertos em 4 faixas de aging.",
         "â€¢ Filtra apenas STATUS = ABERTO<br/>"
         "â€¢ Calcula Dias_Parado = (hoje âˆ’ DATA_ABERTURA).days<br/>"
         "â€¢ Classifica em bins: [-1,7], (7,14], (14,30], (30,âˆž) â†’ labels 0-7, 7-14, 14-30, >30 dias"),

        ("build_pareto_dataframe(df)", "~L950",
         "Gera ranking de falhas mais frequentes.",
         "â€¢ Agrupa por coluna FALHA e conta ocorrÃªncias<br/>"
         "â€¢ Ordena decrescente por Quantidade<br/>"
         "â€¢ Limita top 8 para clareza visual"),

        ("build_mtbf_dataframe(df, top_n)", "~L966",
         "Calcula MTBF (Mean Time Between Failures) por equipamento.",
         "â€¢ Filtra fechados e agrupa por Modelo/Fabricante/TAG<br/>"
         "â€¢ Para cada grupo com â‰¥ 2 falhas: ordena por DATA_ABERTURA, calcula diffs entre consecutivas<br/>"
         "â€¢ MTBF = mÃ©dia dos intervalos em dias<br/>"
         "â€¢ Retorna top_n menores (equipamentos menos confiÃ¡veis)"),

        ("build_operational_radar_table(df)", "~L1641",
         "Ranqueia chamados abertos por risco operacional.",
         "â€¢ Score = (peso_criticidade Ã— 10) + (dias_parado / 3)<br/>"
         "â€¢ peso_criticidade: ALTA=3, MEDIA=2, BAIXA=1<br/>"
         "â€¢ Ordena decrescente e retorna top 12<br/>"
         "â€¢ Gera recomendaÃ§Ãµes automÃ¡ticas por nÃ­vel de risco"),

        ("build_preventiva_corretiva_intervalo(df)", "~L1161",
         "Identifica corretivas pÃ³s-preventiva no mesmo TAG.",
         "â€¢ Para cada TAG: busca preventivas e corretivas fechadas ou abertas<br/>"
         "â€¢ Para cada preventiva: verifica se hÃ¡ corretiva dentro de 30 dias apÃ³s<br/>"
         "â€¢ Calcula intervalo em dias e classifica em faixas (0-2, 3-10, 11-20, 21-30)<br/>"
         "â€¢ Faixa 0-2 dias = crÃ­tica (preventiva possÃ­vel ineficaz)"),

        ("normalize_service_group(value)", "~L245",
         "Normaliza tipo de serviÃ§o em categorias padronizadas.",
         "â€¢ ContÃ©m 'CORRET' â†’ CORRETIVA<br/>"
         "â€¢ ContÃ©m 'PREVENT' â†’ PREVENTIVA<br/>"
         "â€¢ ContÃ©m 'CALIBR' ou 'VERIFIC' â†’ CALIBRACAO<br/>"
         "â€¢ Outros â†’ OUTROS"),

        ("normalize_status(value)", "~L217",
         "Normaliza status de chamados em categorias padronizadas.",
         "â€¢ ContÃ©m 'ABERT'/'PENDENT'/'EM ANDAMENTO' â†’ ABERTO<br/>"
         "â€¢ ContÃ©m 'FECHAD'/'CONCLU'/'FINALIZ' â†’ FECHADO<br/>"
         "â€¢ ContÃ©m 'CANCEL' â†’ CANCELADO<br/>"
         "â€¢ Outros â†’ OUTROS"),

        ("gerar_diagnostico_inteligente(df)", "~L611",
         "Gera diagnÃ³stico completo com nota, alertas e recomendaÃ§Ãµes.",
         "â€¢ Calcula nota de 0-100 com 5 componentes ponderados<br/>"
         "â€¢ Gera lista de alertas baseados em thresholds<br/>"
         "â€¢ Produz resumo executivo textual<br/>"
         "â€¢ Identifica equipamentos e quadros mais problemÃ¡ticos"),

        ("parse_mixed_date_series(series)", "~L125",
         "Parse robusto de datas em planilhas com formatos mistos.",
         "â€¢ 1Âª tentativa: pd.to_datetime padrÃ£o (sem dayfirst) â€” captura YYYY-MM-DD<br/>"
         "â€¢ 2Âª tentativa: pd.to_datetime com dayfirst=True â€” captura DD/MM/YYYY<br/>"
         "â€¢ 3Âª tentativa: serial Excel (float) convertido para datetime<br/>"
         "â€¢ Garante que YYYY-MM-DD nÃ£o seja interpretado como YYYY-DD-MM"),
    ]

    for fname, line, desc, detail in funcs:
        elements.append(KeepTogether([
            Paragraph(f"{fname} <font color='#999999'>({line})</font>", s["H3"]),
            Paragraph(desc, s["BodyBold"]),
            Paragraph(detail, s["BulletCustom"]),
            Spacer(1, 4),
        ]))

    elements.append(PageBreak())

    # â”€â”€ 12. EXPORTAÃ‡Ã•ES â”€â”€
    elements.append(Paragraph("12. ExportaÃ§Ãµes (PDF, CSV, Excel)", s["H1"]))

    export_rows = [
        ["<b>PDF Executivo</b>", "Tab 1",
         "RelatÃ³rio com KPIs, Aging, Pareto, Radar e MTBF em formato profissional para apresentaÃ§Ã£o. "
         "Gerado via ReportLab com logo, cabeÃ§alho e rodapÃ©."],
        ["<b>PDF por Quadro</b>", "Tab 2",
         "RelatÃ³rio de chamados abertos agrupados por Quadro de Trabalho. "
         "Cada quadro em seÃ§Ã£o separada com tabela detalhada."],
        ["<b>CSV</b>", "Tab 2",
         "Exporta tabela completa de chamados abertos em CSV. Delimitador padrÃ£o. Encoding UTF-8."],
        ["<b>Excel (.xlsx)</b>", "Tab 2",
         "Exporta tabela completa de chamados abertos em Excel. Uma aba com todos os dados."],
    ]
    elements.append(styled_table(
        ["Formato", "Tab", "DescriÃ§Ã£o"],
        export_rows, [3.5 * cm, 1.5 * cm, 12 * cm],
    ))

    elements.append(Spacer(1, 1.5 * cm))
    elements.append(divider())
    elements.append(Paragraph(
        "DASA Â· Engenharia ClÃ­nica â€” DocumentaÃ§Ã£o do Dashboard AnalÃ­tico Â· v2.4",
        s["Footer"],
    ))

    doc.build(elements)
    return OUTPUT


if __name__ == "__main__":
    out = build_pdf()
    print(f"PDF gerado: {out}")


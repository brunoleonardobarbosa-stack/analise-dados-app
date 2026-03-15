from xml.sax.saxutils import escape

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from .metrics import build_open_with_aging, build_mtbf_dataframe, build_root_cause_dataframe

DASA_PLOTLY_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(240,248,248,0.35)",
    font=dict(family="'Segoe UI', system-ui, -apple-system, sans-serif", color="#1a3c4e", size=13),
    margin=dict(l=8, r=8, t=10, b=8),
    xaxis=dict(gridcolor="rgba(10,139,141,0.08)", zerolinecolor="rgba(10,139,141,0.12)"),
    yaxis=dict(gridcolor="rgba(10,139,141,0.08)", zerolinecolor="rgba(10,139,141,0.12)"),
    colorway=["#0A8B8D", "#14A3A5", "#067375", "#5CC0C2", "#03585A", "#8DD8D9", "#024B4D", "#A8E4E5"],
)


def apply_dasa_plotly_theme(fig: go.Figure) -> go.Figure:
    fig.update_layout(**DASA_PLOTLY_LAYOUT)
    return fig


def apply_executive_styles() -> None:
    st.markdown(
        """
        <style>
        @keyframes fadeInUp {
            from { opacity: 0; transform: translateY(22px); }
            to   { opacity: 1; transform: translateY(0); }
        }
        @keyframes fadeIn {
            from { opacity: 0; }
            to   { opacity: 1; }
        }
        :root {
            --dasa-blue: #0A8B8D;
            --dasa-blue-light: #14A3A5;
            --dasa-blue-pale: #e6f5f5;
            --dasa-orange: #0E7C7B;
            --dasa-orange-light: #5CC0C2;
            --dasa-orange-pale: #eaf8f8;
            --ec-bg: #f5f7fa;
            --ec-bg-2: #edf1f5;
            --ec-panel: #ffffff;
            --ec-panel-soft: #f8fbfb;
            --ec-border: #d4e0e0;
            --ec-title: #0a2e2f;
            --ec-muted: #2d5050;
            --ec-accent: var(--dasa-blue);
            --ec-risk: #b91c1c;
            --ec-risk-bg: #fef2f2;
            --ec-warn: #92400e;
            --ec-warn-bg: #fffbeb;
            --ec-ok: #166534;
            --ec-ok-bg: #f0fdf4;
        }

        .stApp {
            font-family: "Segoe UI", "Inter", "Calibri", sans-serif;
            background: linear-gradient(135deg, #f7f1e7 0%, #f2eadf 45%, #ebe5da 100%);
            margin-top: 0;
        }

        .hero-card {
            width: 100%;
            min-height: 250px;
            background: linear-gradient(135deg, #0a8b8d 0%, #0b6c74 100%);
            border-radius: 22px;
            margin-bottom: 1.25rem;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 12px 24px rgba(40, 50, 60, 0.28);
            position: relative;
            overflow: hidden;
        }

        .hero-card::before {
            content: "";
            position: absolute;
            inset: 0;
            background: radial-gradient(circle at 25% 30%, rgba(255, 255, 255, 0.16), transparent 55%);
            pointer-events: none;
        }

        .hero-card-content {
            position: relative;
            text-align: center;
            color: #fff;
            z-index: 1;
            padding: 0 1rem;
        }

        .hero-card-letter {
            font-size: clamp(2.5rem, 6vw, 4.4rem);
            font-weight: 900;
            letter-spacing: 0.12rem;
            margin-bottom: 0.55rem;
            opacity: 0.95;
        }

        .hero-card-title {
            font-size: clamp(2.6rem, 6vw, 4.2rem);
            font-weight: 900;
            letter-spacing: 0.16rem;
            margin-bottom: 0.25rem;
        }

        .hero-card-subtitle {
            font-size: clamp(0.95rem, 2vw, 1.2rem);
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.1rem;
            color: #f4f7f9;
        }

        .main .block-container {
            padding-top: 0.8rem;
            padding-bottom: 1.4rem;
            animation: fadeIn 0.6s ease-out;
        }

        /* Scrollbar */
        ::-webkit-scrollbar {
            width: 8px;
            height: 8px;
        }
        ::-webkit-scrollbar-track {
            background: var(--ec-bg);
            border-radius: 4px;
        }
        ::-webkit-scrollbar-thumb {
            background: linear-gradient(180deg, var(--dasa-blue-light), var(--dasa-blue));
            border-radius: 4px;
        }
        ::-webkit-scrollbar-thumb:hover {
            background: var(--dasa-blue);
        }

        .ec-title { font-size:1.6rem; color:var(--ec-title); font-weight:800; border-bottom:2px solid var(--ec-border); margin-bottom:14px; padding-bottom:4px; }
        .ec-subtitle { font-size:1.15rem; color:var(--ec-accent); font-weight:700; margin-bottom:12px; display:flex; align-items:center; gap:8px;}
        .ec-text { font-size:0.95rem; color:var(--ec-muted); margin-bottom:14px; line-height:1.6; }

        .metric-value { font-size: 2.1rem; font-weight: 900; color: var(--ec-accent); }
        .metric-label { font-size: 0.85rem; font-weight: 700; text-transform: uppercase; color: var(--ec-muted); opacity: 0.85; }

        .diagnostico-card {
            background: #ffffff;
            border: 1px solid var(--dasa-blue-pale);
            border-left: 6px solid var(--dasa-blue);
            border-radius: 12px;
            padding: 22px 28px;
            margin-bottom: 24px;
            box-shadow: 0 6px 16px rgba(10,139,141,0.06);
            transition: all 0.25s ease;
        }
        .diagnostico-card:hover {
            box-shadow: 0 8px 22px rgba(10,139,141,0.12);
        }

        .diagnostico-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid #eef3f3;
            padding-bottom: 14px;
            margin-bottom: 18px;
        }
        .v-score-container { text-align: right; }
        .v-score-val { font-size: 3.4rem; font-weight: 900; line-height: 1; letter-spacing: -1px;}
        .v-score-lbl { font-size: 1rem; font-weight: 800; text-transform: uppercase; letter-spacing: 1px; color: #5a7a7a; margin-top: 4px; }

        div[data-testid="stExpander"] div[role="button"] p {
            font-size: 1rem !important;
            font-weight: 700 !important;
            color: var(--ec-title) !important;
        }

        .badge {
            display: inline-block; padding: 3px 8px; border-radius: 12px; font-size: 0.72rem; font-weight: 800;
            text-transform: uppercase; margin-right: 6px; letter-spacing: 0.4px; margin-bottom: 4px;
        }
        .badge-critico { background: #fee2e2; color: #b91c1c; border: 1px solid #fecaca; }
        .badge-atencao { background: #fef3c7; color: #b45309; border: 1px solid #fde68a; }
        .badge-info { background: #e0f2fe; color: #0369a1; border: 1px solid #bae6fd; }

        .ia-user-msg { background: #f8fafc; border-left: 4px solid var(--ec-muted); padding: 12px 16px; border-radius: 0 8px 8px 0; margin-bottom: 16px; font-weight: 500; }
        .ia-bot-msg { background: #f0fdf4; border-left: 4px solid var(--ec-ok); padding: 14px 18px; border-radius: 0 8px 8px 0; margin-bottom: 20px; font-size:0.95rem; line-height:1.6;}

        div[data-testid="stSidebar"] {
            background: linear-gradient(180deg, #ffffff 0%, #f4f8f8 100%);
            border-right: 1px solid var(--ec-border);
        }

        table { width:100%; border-collapse: separate; border-spacing: 0; }
        th { background: var(--dasa-blue-pale) !important; color: var(--dasa-blue) !important; font-weight:800 !important; font-size: 0.85rem; padding: 10px 14px; text-transform: uppercase;}
        td { color: #2d4a66; font-size: 0.9rem; border-bottom: 1px solid #eef3f3; padding: 10px 14px;}
        tr:last-child td { border-bottom: none; }
        tr:hover td { background: rgba(10,139,141,0.02); }

        </style>
        """,
        unsafe_allow_html=True,
    )


def render_kpi_cards(metrics: dict[str, int | float | str | None], aging_df: pd.DataFrame) -> None:
    st.markdown(
        """
        <style>
        .kpi-grid-card {
            border: 1px solid var(--ec-border);
            border-radius: 10px;
            padding: 14px 16px;
            background: #ffffff;
            box-shadow: 0 2px 6px rgba(10,139,141,0.06);
            position: relative;
            overflow: hidden;
            min-height: 90px;
            transition: all 0.25s ease;
        }
        .kpi-grid-card:hover {
            box-shadow: 0 4px 14px rgba(10,139,141,0.12);
        }
        .kpi-grid-card::before {
            content: "";
            position: absolute;
            left: 0;
            top: 0;
            height: 100%;
            width: 3px;
            background: var(--dasa-blue);
        }
        .kpi-grid-title {
            font-size: 0.8rem;
            color: #5a7a7a;
            margin-bottom: 5px;
            font-weight: 700;
            display: flex;
            align-items: center;
            gap: 6px;
            text-transform: uppercase;
        }
        .kpi-info-dot {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 18px;
            height: 18px;
            border-radius: 50%;
            background: var(--dasa-blue-pale);
            border: 1.5px solid var(--dasa-blue-light);
            color: var(--dasa-blue);
            font-size: 11px;
            font-weight: 900;
            cursor: help;
        }
        .kpi-grid-value {
            font-size: 1.5rem;
            color: var(--dasa-blue);
            font-weight: 900;
            line-height: 1.1;
        }
        .kpi-grid-trend {
            margin-top: 6px;
            font-size: 0.78rem;
            color: #067375;
            font-weight: 700;
        }
        .kpi-responsive-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
            gap: 12px;
            margin: 4px 0 14px 0;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    def format_int_pt_br(value: int) -> str:
        return f"{int(value):,}".replace(",", ".")

    def format_percent_pt_br(value: float) -> str:
        return f"{value:.1f}".replace(".", ",")

    mttr = metrics["mttr"]
    mttr_text = f"{format_int_pt_br(mttr)} dias" if isinstance(mttr, int) else "N/D"
    cancelados = int(metrics.get("cancelados", 0))
    percentual_cancelados = float(metrics.get("percentual_cancelados", 0.0))
    cancelados_text = f"{format_int_pt_br(cancelados)} ({format_percent_pt_br(percentual_cancelados)}%)"

    backlog_30 = 0
    if not aging_df.empty and ">30 dias" in aging_df["Faixa"].astype("string").tolist():
        try:
            backlog_30 = int(aging_df.loc[aging_df["Faixa"] == ">30 dias", "Quantidade"].iloc[0])
        except Exception:
            pass

    total = int(metrics.get("total", 0))
    fechados = int(metrics.get("fechados", 0))
    taxa_fechamento = (fechados / total * 100.0) if total > 0 else 0.0

    cards = [
        ("abertos", "Chamados Abertos", format_int_pt_br(int(metrics['abertos'])), "Situação atual", "Total de chamados em aberto"),
        ("aguardando_relatorio", "Aguardando Relatorio", format_int_pt_br(int(metrics.get('aguardando_relatorio', 0))), "Status especial", "-"),
        ("criticos_aberto", "Criticos em Aberto", format_int_pt_br(int(metrics['alta_criticidade_abertos'])), "Criticidade ALTA ativa", "Prioridade"),
        ("backlog_30", "Backlog >30 dias", format_int_pt_br(backlog_30), "Fila engarrafada", "Risco operacional"),
        ("corretiva", "Corretiva", format_int_pt_br(int(metrics.get("corretiva", 0))), "Em aberto", "-"),
        ("preventiva", "Preventiva", format_int_pt_br(int(metrics.get("preventiva", 0))), "Em aberto", "-"),
        ("calibracao", "Calibracao", format_int_pt_br(int(metrics.get("calibracao", 0))), "Em aberto", "-"),
        ("mttr", "Tempo Medio Atendimento", mttr_text, "Meta: <= 15 dias", "MTTR"),
        ("taxa_fechamento", "Taxa de Fechamento", f"{format_percent_pt_br(taxa_fechamento)}%", "Fechados / Total", "Acompanhamento"),
        ("cancelados", "Cancelados", cancelados_text, "Cancelados", "Cancelados"),
    ]

    card_blocks: list[str] = []
    for key, title, value, trend, tip in cards:
        tooltip = escape(tip)
        href = f"?detalhe={key}"
        card_blocks.append(
            f"<a href='{href}' target='_blank' class='kpi-grid-card' title='{tooltip}'>"
            f"<div class='kpi-grid-title'>{title}<span class='kpi-info-dot' title='{tooltip}'>i</span></div>"
            f"<div class='kpi-grid-value'>{value}</div>"
            f"<div class='kpi-grid-trend'>{trend}</div>"
            f"</a>"
        )

    st.markdown("<div class='kpi-responsive-grid'>" + "".join(card_blocks) + "</div>", unsafe_allow_html=True)

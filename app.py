from __future__ import annotations

APP_VERSION = "2.4.0"  # Alterar a cada entrega

import io
import hashlib
import os
import re
import unicodedata
from typing import Iterable
from xml.sax.saxutils import escape

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

try:
    import openai
except ImportError:
    openai = None

try:
    from reportlab.lib import colors as rl_colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False

REQUIRED_COLUMNS: list[str] = [
    "REGIAO",
    "QUADRO",
    "STATUS",
    "TIPO_EQUIPAMENTO",
    "TAG",
    "MODELO",
    "FABRICANTE",
    "DATA_ABERTURA",
    "FALHA",
    "CRITICIDADE",
]

OPTIONAL_DATE_COLUMNS: list[str] = ["DATA_FECHAMENTO"]

COLUMN_ALIASES: dict[str, str] = {
    "REGIAO": "REGIAO",
    "REGIAO_ATENDIMENTO": "REGIAO",
    "LOCALIZACAO": "REGIAO",
    "QUADRO": "QUADRO",
    "QUADRO_TRABALHO": "QUADRO",
    "QUADRO_DE_TRABALHO": "QUADRO",
    "STATUS": "STATUS",
    "SITUACAO": "STATUS",
    "ESTADO": "STATUS",
    "TIPO_EQUIPAMENTO": "TIPO_EQUIPAMENTO",
    "TIPO_DE_EQUIPAMENTO": "TIPO_EQUIPAMENTO",
    "EQUIPAMENTO": "TIPO_EQUIPAMENTO",
    "TIPO_SERVICO": "TIPO_SERVICO",
    "TIPO_DE_SERVICO": "TIPO_SERVICO",
    "TIPO_MANUTENCAO": "TIPO_SERVICO",
    "TIPO_DE_MANUTENCAO": "TIPO_SERVICO",
    "MANUTENCAO": "TIPO_SERVICO",
    "SERVICO": "TIPO_SERVICO",
    "SERVICO_EXECUTADO": "TIPO_SERVICO",
    "TIPO_CHAMADO": "TIPO_SERVICO",
    "TAG": "TAG",
    "PATRIMONIO": "TAG",
    "NUMERO": "NUMERO_CHAMADO",
    "NUMERO_CHAMADO": "NUMERO_CHAMADO",
    "N_CHAMADO": "NUMERO_CHAMADO",
    "CHAMADO": "NUMERO_CHAMADO",
    "ID": "NUMERO_CHAMADO",
    "OS": "NUMERO_CHAMADO",
    "NUMERO_OS": "NUMERO_CHAMADO",
    "ORDEM_DE_SERVICO": "NUMERO_CHAMADO",
    "MODELO": "MODELO",
    "FABRICANTE": "FABRICANTE",
    "FORNECEDOR": "FABRICANTE",
    "NOME_FORNECEDOR": "FABRICANTE",
    "DATA_ABERTURA": "DATA_ABERTURA",
    "ABERTURA": "DATA_ABERTURA",
    "DATA_DE_CRIACAO": "DATA_ABERTURA",
    "DATA_FECHAMENTO": "DATA_FECHAMENTO",
    "FECHAMENTO": "DATA_FECHAMENTO",
    "DATA_DE_CONCLUSAO": "DATA_FECHAMENTO",
    "FALHA": "FALHA",
    "DESCRICAO_FALHA": "FALHA",
    "PROBLEMA_RELATADO": "FALHA",
    "ORIGEM_DO_PROBLEMA": "ORIGEM_PROBLEMA",
    "ORIGEM_PROBLEMA": "ORIGEM_PROBLEMA",
    "CAUSA_RAIZ": "ORIGEM_PROBLEMA",
    "CAUSA": "ORIGEM_PROBLEMA",
    "ORIGEM": "ORIGEM_PROBLEMA",
    "CRITICIDADE": "CRITICIDADE",
    "NIVEL_CRITICIDADE": "CRITICIDADE",
    "CRITICIDADE_DO_EQUIPAMENTO": "CRITICIDADE",
    "SOLICITANTE": "SOLICITANTE",
    "REQUISITANTE": "SOLICITANTE",
    "USUARIO_SOLICITANTE": "SOLICITANTE",
    "NOME_SOLICITANTE": "SOLICITANTE",
    "OBSERVACAO": "OBSERVACAO",
    "OBSERVACOES": "OBSERVACAO",
    "OBS": "OBSERVACAO",
    "COMENTARIO": "OBSERVACAO",
    "COMENTARIOS": "OBSERVACAO",
    "DESCRICAO": "OBSERVACAO",
}


def normalize_column_key(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.strip().upper()
    text = re.sub(r"[^A-Z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text


# ── Tema DASA unificado para Plotly ──
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
    """Aplica o tema DASA corporativo a qualquer figura Plotly."""
    fig.update_layout(**DASA_PLOTLY_LAYOUT)
    return fig


# Parse misto em duas etapas:
# 1) parse padrao para respeitar formatos ISO bem-formados
# 2) fallback dayfirst para datas locais que falharam
# Isso reduz erros de interpretacao em planilhas heterogeneas.
def parse_mixed_date_series(series: pd.Series) -> pd.Series:
    raw = series.astype("string").str.strip()
    parsed = pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]")

    # ISO (YYYY-MM-DD / YYYY/MM/DD) deve ser parseado sem dayfirst para evitar inversao de mes/dia.
    iso_mask = raw.str.match(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}($|\s+\d{1,2}:\d{1,2})", na=False)
    if iso_mask.any():
        parsed.loc[iso_mask] = pd.to_datetime(raw.loc[iso_mask], errors="coerce", dayfirst=False)

    # Formato local (DD/MM/AAAA ou DD-MM-AAAA) usa dayfirst=True explicitamente.
    br_mask = raw.str.match(r"^\d{1,2}[/-]\d{1,2}[/-]\d{2,4}($|\s+\d{1,2}:\d{1,2})", na=False)
    br_mask = br_mask & parsed.isna()
    if br_mask.any():
        parsed.loc[br_mask] = pd.to_datetime(raw.loc[br_mask], errors="coerce", dayfirst=True)

    # Datas em numero serial do Excel (ex.: 45231).
    excel_mask = raw.str.match(r"^\d{4,5}$", na=False) & parsed.isna()
    if excel_mask.any():
        serial_values = pd.to_numeric(raw.loc[excel_mask], errors="coerce")
        parsed.loc[excel_mask] = pd.to_datetime(serial_values, unit="D", origin="1899-12-30", errors="coerce")

    # Fallback em duas etapas para casos restantes.
    remaining = parsed.isna() & raw.notna() & raw.ne("")
    if remaining.any():
        parsed.loc[remaining] = pd.to_datetime(raw.loc[remaining], errors="coerce")

    remaining = parsed.isna() & raw.notna() & raw.ne("")
    if remaining.any():
        parsed.loc[remaining] = pd.to_datetime(raw.loc[remaining], errors="coerce", dayfirst=True)

    return parsed


def normalize_text_series(series: pd.Series) -> pd.Series:
    return (
        series.astype("string")
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
        .str.upper()
    )


def normalize_scalar_text(value) -> str:
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    return str(value).strip().upper()


def normalize_region_label(value: str) -> str:
    text = normalize_scalar_text(value)
    key = normalize_column_key(text)

    # Corrige todos os padrões para Centro-oeste, Nordeste e Sul
    if any(k in key for k in ["NTO_CO", "NTOCO", "NTO_C_O"]):
        return "CENTRO-OESTE"
    if any(k in key for k in ["NTO_NE", "NTONE", "NTO_N_E"]):
        return "NORDESTE"
    if any(k in key for k in ["NTO_SUL", "NTOSUL", "NTO_S"]):
        return "SUL"

    return text


def sanitize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    clean = df.copy()

    normalized_columns: list[str] = []
    for col in clean.columns:
        normalized = normalize_column_key(str(col))
        normalized_columns.append(COLUMN_ALIASES.get(normalized, normalized))
    clean.columns = normalized_columns

    # Mantem a primeira ocorrencia em caso de colunas equivalentes apos alias.
    if clean.columns.duplicated().any():
        clean = clean.loc[:, ~clean.columns.duplicated()]

    for col in clean.columns:
        if pd.api.types.is_string_dtype(clean[col]) or clean[col].dtype == object:
            clean[col] = normalize_text_series(clean[col])

    if "DATA_ABERTURA" in clean.columns:
        clean["DATA_ABERTURA"] = parse_mixed_date_series(clean["DATA_ABERTURA"])

    if "REGIAO" in clean.columns:
        clean["REGIAO"] = clean["REGIAO"].astype("string").map(normalize_region_label)

    for optional_col in OPTIONAL_DATE_COLUMNS:
        if optional_col in clean.columns:
            clean[optional_col] = parse_mixed_date_series(clean[optional_col])

    return clean


@st.cache_data(show_spinner=False)
def load_and_sanitize_excel(file_bytes: bytes) -> pd.DataFrame:
    raw_df = pd.read_excel(io.BytesIO(file_bytes))
    return sanitize_dataframe(raw_df)


def validate_required_columns(df: pd.DataFrame, required: Iterable[str]) -> list[str]:
    return [col for col in required if col not in df.columns]


def resolve_ticket_number_column(df: pd.DataFrame) -> str | None:
    candidates = ["NUMERO_CHAMADO", "NUMERO", "ID", "OS", "NUMERO_OS", "ORDEM_DE_SERVICO"]
    for col in candidates:
        if col in df.columns:
            return col
    return None


def resolve_requester_column(df: pd.DataFrame) -> str | None:
    candidates = ["SOLICITANTE", "REQUISITANTE", "USUARIO_SOLICITANTE", "NOME_SOLICITANTE"]
    for col in candidates:
        if col in df.columns:
            return col
    return None


def resolve_observation_column(df: pd.DataFrame) -> str | None:
    candidates = ["OBSERVACAO", "OBSERVACOES", "OBS", "COMENTARIO", "COMENTARIOS", "DESCRICAO"]
    for col in candidates:
        if col in df.columns:
            return col
    return None


def normalize_status(value: str) -> str:
    text = normalize_scalar_text(value)
    text_key = normalize_column_key(text)

    if text_key == "AGUARDANDO_RELATORIO":
        return "AGUARDANDO_RELATORIO"

    open_exact = {
        "ABERTO",
        "ABERTA",
        "EM_ABERTO",
        "OPEN",
        "AGUARDANDO",
        "EM_ESPERA",
        "EM_EXECUCAO",
        "EM_MANUTENCAO",
    }
    if text_key in open_exact:
        return "ABERTO"

    open_prefixes = (
        "AGUARDANDO",
        "EM_ESPERA",
        "EM_EXECUCAO",
        "EM_MANUTENCAO",
        "SERVICO_AG",
        "SERVICO_EM",
    )
    if any(text_key.startswith(prefix) for prefix in open_prefixes):
        return "ABERTO"

    if text_key in {
        "FECHADO",
        "FECHADA",
        "CLOSED",
        "ENCERRADO",
        "ENCERRADA",
        "CONCLUIDO",
        "CONCLUIDA",
        "FINALIZADO",
        "FINALIZADA",
    }:
        return "FECHADO"

    if text_key in {"CANCELADO", "CANCELADA", "CANCELED", "CANCELAMENTO", "CANCELAR"}:
        return "CANCELADO"

    return "OUTROS"


def generate_gemini_response(question: str) -> str:
    """Chama a API Gemini/OpenAI para respostas de linguagem natural."""
    if openai is None:
        return "Dependência openai não instalada. Rode 'pip install openai' e reinicie o app."

    api_key = (
        os.getenv("OPENAI_API_KEY")
        or (st.secrets.get("OPENAI_API_KEY", "") if hasattr(st, "secrets") else "")
    )
    if not api_key:
        return "OPENAI_API_KEY não configurada. Defina como variável de ambiente ou em st.secrets."

    try:
        openai.api_key = api_key
        openai.ChatCompletion.request_timeout = 20
        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",  # ou "gemini-1"/"gemini-pro" se disponível
            messages=[
                {"role": "system", "content": "Você é um assistente de análise de chamados de Engenharia Clínica."},
                {"role": "user", "content": question},
            ],
            max_tokens=350,
            temperature=0.3,
            n=1,
        )
        if not response or not getattr(response, 'choices', None):
            return "A API Gemini não retornou resultado. Verifique a conexão e a quota de uso."

        return response.choices[0].message.content.strip()

    except Exception as exc:
        msg = str(exc)
        if "Could not connect" in msg or "ConnectionError" in msg:
            return "Erro de comunicação: falha ao conectar à API Gemini. Verifique sua internet e proxy."
        if "401" in msg or "authentication" in msg.lower():
            return "Erro de autenticação Gemini: verifique sua OPENAI_API_KEY."
        return f"Erro ao chamar Gemini: {msg}"


def normalize_service_group(value: str) -> str:
    text = normalize_scalar_text(value)
    key = normalize_column_key(text)

    if "CORRET" in key:
        return "CORRETIVA"

    if "PREVENT" in key:
        return "PREVENTIVA"

    # Regra solicitada: Verificacao entra na contagem/filtro de Calibracao.
    if "CALIBR" in key or "VERIFIC" in key:
        return "CALIBRACAO"

    return "OUTROS"


def apply_filters(
    df: pd.DataFrame,
    regiao: str,
    quadros: list[str],
    criticidade: str,
    tipo_servico: str,
    data_inicial,
    data_final,
    tag_pesquisa: str = "",
) -> pd.DataFrame:
    filtered = df.copy()

    if regiao != "TODAS":
        filtered = filtered[filtered["REGIAO"] == regiao]

    if quadros:
        filtered = filtered[filtered["QUADRO"].isin(quadros)]

    if criticidade != "TODAS":
        filtered = filtered[filtered["CRITICIDADE"] == criticidade]

    if tipo_servico != "TODOS" and "TIPO_SERVICO" in filtered.columns:
        groups = filtered["TIPO_SERVICO"].map(normalize_service_group)
        filtered = filtered[groups == tipo_servico]

    if tag_pesquisa.strip():
        query = normalize_scalar_text(tag_pesquisa)
        # Pesquisa global: busca em todas as colunas de texto relevantes
        _search_cols = [
            "TAG", "MODELO", "FABRICANTE", "FALHA", "QUADRO",
            "TIPO_EQUIPAMENTO", "SOLICITANTE", "OBSERVACAO",
            "NUMERO_CHAMADO", "ORIGEM_PROBLEMA", "CRITICIDADE",
        ]
        mask = pd.Series(False, index=filtered.index)
        for _sc in _search_cols:
            if _sc in filtered.columns:
                col_norm = filtered[_sc].astype("string").fillna("").map(normalize_scalar_text)
                mask = mask | col_norm.str.contains(query, case=False, regex=False, na=False)
        filtered = filtered[mask]

    # Filtro de periodo aplicado por dia da data de abertura (ignora horario).
    if data_inicial is not None or data_final is not None:
        filtered = filtered[filtered["DATA_ABERTURA"].notna()]
        abertura_dia = filtered["DATA_ABERTURA"].dt.normalize()

        if data_inicial is not None:
            filtered = filtered[abertura_dia >= pd.Timestamp(data_inicial)]

        if data_final is not None:
            filtered = filtered[abertura_dia <= pd.Timestamp(data_final)]

    return filtered


# ── Engine de Inteligência Analítica (local, sem API externa) ──

_IA_PERGUNTAS = [
    {
        "padroes": ["situacao", "situação", "geral", "resumo", "como esta", "como está", "visao geral", "visão geral", "overview"],
        "chave": "resumo",
    },
    {
        "padroes": ["backlog", "atrasado", "antigo", "30 dia", "60 dia", "velho", "parado"],
        "chave": "backlog",
    },
    {
        "padroes": ["critico", "crítico", "criticidade", "alta", "urgente", "prioridade", "risco"],
        "chave": "criticidade",
    },
    {
        "padroes": ["falha", "defeito", "problema", "recorrente", "frequente", "quebra"],
        "chave": "falhas",
    },
    {
        "padroes": ["equipamento", "modelo", "aparelho", "maquina", "máquina", "demandado"],
        "chave": "equipamentos",
    },
    {
        "padroes": ["quadro", "equipe", "time", "sobrecarga", "carga", "distribuicao"],
        "chave": "quadros",
    },
    {
        "padroes": ["mttr", "tempo", "resolucao", "resolução", "sla", "media", "média", "atendimento", "demora"],
        "chave": "mttr",
    },
    {
        "padroes": ["cancelamento", "cancelado", "cancelar", "taxa"],
        "chave": "cancelamento",
    },
    {
        "padroes": ["recomend", "acao", "ação", "fazer", "priorizar", "sugestao", "sugestão", "plano"],
        "chave": "recomendacoes",
    },
    {
        "padroes": ["nota", "score", "pontuacao", "avaliacao", "avaliação"],
        "chave": "nota",
    },
]


def _ia_responder_pergunta(pergunta: str, diag: dict) -> str:
    """Responde perguntas sobre os dados com base no diagnóstico."""
    pergunta_lower = pergunta.lower().strip()
    m = diag["metricas"]

    # Detectar intenção
    chave_detectada = None
    for item in _IA_PERGUNTAS:
        for padrao in item["padroes"]:
            if padrao in pergunta_lower:
                chave_detectada = item["chave"]
                break
        if chave_detectada:
            break

    if chave_detectada == "resumo" or not chave_detectada:
        resp = f"**Resumo da Situacao Atual:**\n\n{diag['resumo_executivo']}\n\n"
        resp += f"**Nota operacional: {diag['nota']:.0f}/100 ({diag['nota_label']})**"
        return resp

    if chave_detectada == "backlog":
        resp = f"**Analise de Backlog:**\n\n"
        resp += f"- Chamados com mais de 30 dias: **{m['backlog_30']}**\n"
        resp += f"- Chamados com mais de 60 dias: **{m['backlog_60']}**\n"
        resp += f"- Idade media dos chamados abertos: **{m['media_aging']:.0f} dias**\n\n"
        if m["backlog_30"] >= 15:
            resp += "⚠️ **Situacao critica.** O backlog esta muito alto. Recomendo mutirao urgente para reducao."
        elif m["backlog_30"] >= 5:
            resp += "🟡 **Atencao.** Ha acumulo moderado. Sugiro agendar janela semanal para reducao."
        else:
            resp += "✅ **Backlog controlado.** Manter monitoramento regular."
        return resp

    if chave_detectada == "criticidade":
        resp = f"**Chamados de Alta Criticidade:**\n\n"
        resp += f"- Alta criticidade em aberto: **{m['alta_abertos']}**\n"
        resp += f"- Total de abertos: **{m['abertos']}**\n\n"
        if m["alta_abertos"] >= 10:
            resp += "🔴 **Alerta maximo.** Mobilizar equipe imediatamente para estes chamados."
        elif m["alta_abertos"] >= 5:
            resp += "🟡 **Atencao.** Priorizar atendimento no primeiro turno."
        elif m["alta_abertos"] > 0:
            resp += "🟢 Quantidade gerenciavel. Manter prioridade no atendimento."
        else:
            resp += "✅ Sem chamados de alta criticidade pendentes."
        return resp

    if chave_detectada == "falhas":
        resp = f"**Top Falhas Recorrentes (Chamados Abertos):**\n\n"
        if diag["top_falhas"]:
            for i, (falha, qtd) in enumerate(diag["top_falhas"], 1):
                resp += f"{i}. **{falha}** — {qtd} ocorrencias\n"
            resp += f"\n💡 A falha mais frequente e **{diag['top_falhas'][0][0]}** com {diag['top_falhas'][0][1]} casos. Avaliar causa raiz."
        else:
            resp += "Nenhuma falha registrada nos chamados abertos."
        return resp

    if chave_detectada == "equipamentos":
        resp = f"**Equipamentos Mais Demandados:**\n\n"
        if diag["equip_problematicos"]:
            for i, eq in enumerate(diag["equip_problematicos"], 1):
                resp += f"{i}. **{eq['modelo']}** ({eq['fabricante']}) — {eq['chamados']} chamados, media {eq['media_dias']} dias"
                if eq["alta_crit"] > 0:
                    resp += f", {eq['alta_crit']} criticos"
                resp += "\n"
            top = diag["equip_problematicos"][0]
            if top["chamados"] >= 5:
                resp += f"\n⚠️ **{top['modelo']}** e o mais critico. Considerar contrato de manutencao ou substituicao."
        else:
            resp += "Nenhum equipamento com chamados abertos no momento."
        return resp

    if chave_detectada == "quadros":
        resp = f"**Carga por Quadro de Trabalho:**\n\n"
        if diag["quadros_ranking"]:
            for i, q in enumerate(diag["quadros_ranking"], 1):
                resp += f"{i}. **{q['quadro']}** — {q['abertos']} abertos, media {q['media_dias']} dias"
                if q["alta_crit"] > 0:
                    resp += f", {q['alta_crit']} criticos"
                resp += "\n"
            top_q = diag["quadros_ranking"][0]
            resp += f"\n📊 **{top_q['quadro']}** esta com maior carga. Avaliar redistribuicao se necessario."
        else:
            resp += "Nenhum quadro com chamados abertos."
        return resp

    if chave_detectada == "mttr":
        resp = f"**Tempo de Resolucao (MTTR):**\n\n"
        if m["mttr"]:
            resp += f"- MTTR atual: **{int(m['mttr'])} dias**\n"
            resp += f"- Meta operacional: **15 dias**\n\n"
            if m["mttr"] > 25:
                resp += "🔴 **Muito acima da meta.** Revisar fluxo de atendimento, disponibilidade de pecas e escalar gargalos."
            elif m["mttr"] > 15:
                resp += "🟡 **Acima da meta.** Identificar os tipos de servico mais demorados e otimizar."
            else:
                resp += "✅ **Dentro da meta.** Manter controle e buscar melhoria continua."
        else:
            resp += "Nao ha dados de fechamento suficientes para calcular o MTTR."
        return resp

    if chave_detectada == "cancelamento":
        resp = f"**Analise de Cancelamentos:**\n\n"
        resp += f"- Cancelados: **{m['cancelados']}** de **{m['total']}** total\n"
        resp += f"- Taxa: **{m['taxa_cancelamento']:.1f}%**\n\n"
        if m["taxa_cancelamento"] >= 15:
            resp += "🔴 **Taxa muito alta.** Revisar criterios de abertura e treinamento dos solicitantes."
        elif m["taxa_cancelamento"] >= 8:
            resp += "🟡 **Acima do esperado.** Monitorar e padronizar fluxo de abertura."
        else:
            resp += "✅ Taxa de cancelamento dentro do esperado."
        return resp

    if chave_detectada == "recomendacoes":
        resp = f"**Recomendacoes para Acao:**\n\n"
        for i, (prioridade, texto) in enumerate(diag["recomendacoes"], 1):
            resp += f"{i}. **[{prioridade}]** {texto}\n"
        return resp

    if chave_detectada == "nota":
        resp = f"**Nota Operacional: {diag['nota']:.0f}/100 — {diag['nota_label']}**\n\n"
        resp += "A nota e calculada com base em:\n"
        resp += "- Backlog >30 dias\n- Criticidade alta em aberto\n- MTTR vs meta\n- Taxa de cancelamento\n- Idade media dos chamados\n\n"
        if diag["nota"] >= 80:
            resp += "✅ Operacao saudavel. Foco em prevencao."
        elif diag["nota"] >= 60:
            resp += "🟢 Boa performance, com pontos de melhoria."
        elif diag["nota"] >= 40:
            resp += "🟡 Atencao necessaria em indicadores chave."
        else:
            resp += "🔴 Situacao critica. Acoes imediatas necessarias."
        return resp

    return f"**Resumo da Situacao Atual:**\n\n{diag['resumo_executivo']}"


def _ia_classificar_severidade(valor: float, limites: tuple[float, float]) -> str:
    if valor >= limites[1]:
        return "CRITICO"
    elif valor >= limites[0]:
        return "ATENCAO"
    return "OK"


def _ia_icone_severidade(sev: str) -> str:
    return {"CRITICO": "🔴", "ATENCAO": "🟡", "OK": "🟢"}.get(sev, "⚪")


def gerar_diagnostico_inteligente(df: pd.DataFrame) -> dict:
    """Analisa o DataFrame filtrado e retorna um diagnóstico completo."""
    today = pd.Timestamp.now().normalize()
    status_norm = df["STATUS"].map(normalize_status)

    abertos_mask = status_norm == "ABERTO"
    aguardando_relatorio_mask = status_norm == "AGUARDANDO_RELATORIO"
    fechados_mask = status_norm == "FECHADO"
    cancelados_mask = status_norm == "CANCELADO"

    abertos = df[abertos_mask].copy()
    fechados = df[fechados_mask].copy()
    total = len(df)
    n_abertos = int(abertos_mask.sum())
    n_aguardando_relatorio = int(aguardando_relatorio_mask.sum())
    n_fechados = int(fechados_mask.sum())
    n_cancelados = int(cancelados_mask.sum())

    # ── Aging ──
    if not abertos.empty:
        abertos["_DIAS"] = (today - abertos["DATA_ABERTURA"]).dt.days.fillna(0).clip(lower=0)
    else:
        abertos["_DIAS"] = pd.Series(dtype="int64")

    backlog_30 = int((abertos["_DIAS"] > 30).sum()) if not abertos.empty else 0
    backlog_60 = int((abertos["_DIAS"] > 60).sum()) if not abertos.empty else 0
    media_aging = float(abertos["_DIAS"].mean()) if not abertos.empty else 0.0

    # ── Criticidade ──
    alta_abertos = int((abertos["CRITICIDADE"] == "ALTA").sum()) if not abertos.empty else 0

    # ── MTTR ──
    mttr = None
    if "DATA_FECHAMENTO" in df.columns and not fechados.empty:
        dur = (fechados["DATA_FECHAMENTO"] - fechados["DATA_ABERTURA"]).dt.days
        dur_valida = dur[dur.notna() & (dur >= 0)]
        if not dur_valida.empty:
            mttr = float(dur_valida.mean())

    # ── Taxa fechamento ──
    taxa_fechamento = (n_fechados / total * 100) if total > 0 else 0.0
    taxa_cancelamento = (n_cancelados / total * 100) if total > 0 else 0.0

    # ── Top falhas recorrentes ──
    top_falhas = []
    if "FALHA" in df.columns and not abertos.empty:
        falha_counts = abertos["FALHA"].value_counts().head(5)
        top_falhas = [(str(f), int(c)) for f, c in falha_counts.items()]

    # ── Equipamentos mais problemáticos ──
    equip_problematicos = []
    if not abertos.empty:
        eq = abertos.groupby(["MODELO", "FABRICANTE"], as_index=False).agg(
            Chamados=("MODELO", "size"),
            Media_Dias=("_DIAS", "mean"),
            Alta_Crit=("CRITICIDADE", lambda s: int((s == "ALTA").sum())),
        ).sort_values(["Chamados", "Media_Dias"], ascending=False).head(5)
        for _, row in eq.iterrows():
            equip_problematicos.append({
                "modelo": str(row["MODELO"]),
                "fabricante": str(row["FABRICANTE"]),
                "chamados": int(row["Chamados"]),
                "media_dias": round(float(row["Media_Dias"]), 1),
                "alta_crit": int(row["Alta_Crit"]),
            })

    # ── Quadros sobrecarregados ──
    quadros_ranking = []
    if not abertos.empty and "QUADRO" in abertos.columns:
        qr = abertos.groupby("QUADRO", as_index=False).agg(
            Abertos=("QUADRO", "size"),
            Media_Dias=("_DIAS", "mean"),
            Alta_Crit=("CRITICIDADE", lambda s: int((s == "ALTA").sum())),
        ).sort_values(["Abertos", "Alta_Crit"], ascending=False).head(5)
        for _, row in qr.iterrows():
            quadros_ranking.append({
                "quadro": str(row["QUADRO"]),
                "abertos": int(row["Abertos"]),
                "media_dias": round(float(row["Media_Dias"]), 1),
                "alta_crit": int(row["Alta_Crit"]),
            })

    # ── Alertas ──
    alertas = []

    sev_backlog = _ia_classificar_severidade(backlog_30, (5, 15))
    alertas.append({
        "titulo": "Backlog > 30 dias",
        "valor": f"{backlog_30} chamados",
        "severidade": sev_backlog,
        "detalhe": f"{backlog_60} deles com mais de 60 dias" if backlog_60 else "Nenhum acima de 60 dias",
    })

    sev_crit = _ia_classificar_severidade(alta_abertos, (5, 10))
    alertas.append({
        "titulo": "Alta Criticidade em Aberto",
        "valor": f"{alta_abertos} chamados",
        "severidade": sev_crit,
        "detalhe": "Equipamentos criticos aguardando atendimento" if alta_abertos > 0 else "Sem pendencias criticas",
    })

    sev_mttr = _ia_classificar_severidade(mttr if mttr else 0, (15, 25))
    alertas.append({
        "titulo": "Tempo Medio de Resolucao (MTTR)",
        "valor": f"{int(mttr)} dias" if mttr else "N/A",
        "severidade": sev_mttr,
        "detalhe": "Acima da meta de 15 dias" if mttr and mttr > 15 else "Dentro da meta operacional",
    })

    sev_cancel = _ia_classificar_severidade(taxa_cancelamento, (8, 15))
    alertas.append({
        "titulo": "Taxa de Cancelamento",
        "valor": f"{taxa_cancelamento:.1f}%",
        "severidade": sev_cancel,
        "detalhe": f"{n_cancelados} chamados cancelados de {total} total",
    })

    sev_aging = _ia_classificar_severidade(media_aging, (14, 25))
    alertas.append({
        "titulo": "Idade Media dos Chamados Abertos",
        "valor": f"{media_aging:.0f} dias",
        "severidade": sev_aging,
        "detalhe": "Indica velocidade geral de atendimento",
    })

    # ── Recomendações inteligentes ──
    recomendacoes = []

    if backlog_60 >= 5:
        recomendacoes.append(("URGENTE", "Executar forca-tarefa imediata para os {0} chamados com mais de 60 dias. Priorizar por criticidade.".format(backlog_60)))
    if backlog_30 >= 15:
        recomendacoes.append(("ALTA", "Criar mutirao semanal para reduzir backlog >30 dias (atualmente {0} chamados).".format(backlog_30)))
    elif backlog_30 >= 5:
        recomendacoes.append(("MEDIA", "Agendar janela para reducao gradual do backlog >30 dias ({0} chamados).".format(backlog_30)))

    if alta_abertos >= 10:
        recomendacoes.append(("URGENTE", "Mobilizar equipe para atender {0} chamados de alta criticidade hoje.".format(alta_abertos)))
    elif alta_abertos >= 5:
        recomendacoes.append(("ALTA", "Priorizar atendimento dos {0} chamados de alta criticidade no primeiro turno.".format(alta_abertos)))

    if mttr and mttr > 25:
        recomendacoes.append(("ALTA", "MTTR em {0} dias esta muito acima da meta. Revisar checklists e disponibilidade de pecas.".format(int(mttr))))
    elif mttr and mttr > 15:
        recomendacoes.append(("MEDIA", "MTTR em {0} dias. Avaliar gargalos no fluxo de atendimento.".format(int(mttr))))

    if taxa_cancelamento >= 15:
        recomendacoes.append(("ALTA", "Taxa de cancelamento em {0:.1f}%. Revisar criterios de abertura com a operacao.".format(taxa_cancelamento)))

    if equip_problematicos and equip_problematicos[0]["chamados"] >= 5:
        eq = equip_problematicos[0]
        recomendacoes.append(("MEDIA", "Equipamento {0} ({1}) lidera com {2} chamados abertos. Avaliar substituicao ou contrato de manutencao.".format(eq["modelo"], eq["fabricante"], eq["chamados"])))

    if not recomendacoes:
        recomendacoes.append(("INFO", "Operacao estavel. Manter rotina de prevencao e monitoramento."))

    # ── Nota geral (0-100) ──
    nota = 100.0
    if backlog_30 >= 15:
        nota -= 25
    elif backlog_30 >= 5:
        nota -= 12
    if alta_abertos >= 10:
        nota -= 25
    elif alta_abertos >= 5:
        nota -= 12
    if mttr and mttr > 25:
        nota -= 20
    elif mttr and mttr > 15:
        nota -= 10
    if taxa_cancelamento >= 15:
        nota -= 15
    elif taxa_cancelamento >= 8:
        nota -= 7
    if media_aging > 25:
        nota -= 15
    elif media_aging > 14:
        nota -= 7
    nota = max(0, min(100, nota))

    if nota >= 80:
        nota_label = "Excelente"
        nota_cor = "#22c55e"
    elif nota >= 60:
        nota_label = "Bom"
        nota_cor = "#84cc16"
    elif nota >= 40:
        nota_label = "Atencao"
        nota_cor = "#facc15"
    elif nota >= 20:
        nota_label = "Critico"
        nota_cor = "#fb923c"
    else:
        nota_label = "Emergencial"
        nota_cor = "#ef4444"

    # ── Resumo executivo textual ──
    resumo_partes = []
    resumo_partes.append(f"A operacao possui **{n_abertos} chamados abertos** de um total de **{total}** no periodo filtrado.")
    resumo_partes.append(f"A taxa de fechamento e de **{taxa_fechamento:.1f}%** e a taxa de cancelamento e de **{taxa_cancelamento:.1f}%**.")
    if backlog_30 > 0:
        resumo_partes.append(f"Ha **{backlog_30} chamados com mais de 30 dias** em aberto, representando risco de backlog.")
    if alta_abertos > 0:
        resumo_partes.append(f"Existem **{alta_abertos} chamados de alta criticidade** aguardando atendimento.")
    if n_aguardando_relatorio > 0:
        resumo_partes.append(f"Ha **{n_aguardando_relatorio} chamados aguardando relatorio** (não entram em aberto).")
    if mttr:
        meta_txt = "dentro da meta" if mttr <= 15 else "**acima da meta de 15 dias**"
        resumo_partes.append(f"O tempo medio de resolucao (MTTR) e de **{int(mttr)} dias**, {meta_txt}.")
    if equip_problematicos:
        eq = equip_problematicos[0]
        resumo_partes.append(f"O equipamento mais demandado e **{eq['modelo']}** ({eq['fabricante']}) com **{eq['chamados']} chamados abertos**.")
    resumo_executivo = " ".join(resumo_partes)

    return {
        "nota": nota,
        "nota_label": nota_label,
        "nota_cor": nota_cor,
        "resumo_executivo": resumo_executivo,
        "alertas": alertas,
        "recomendacoes": recomendacoes,
        "top_falhas": top_falhas,
        "equip_problematicos": equip_problematicos,
        "quadros_ranking": quadros_ranking,
        "metricas": {
            "abertos": n_abertos,
            "aguardando_relatorio": n_aguardando_relatorio,
            "fechados": n_fechados,
            "cancelados": n_cancelados,
            "total": total,
            "backlog_30": backlog_30,
            "backlog_60": backlog_60,
            "media_aging": media_aging,
            "alta_abertos": alta_abertos,
            "mttr": mttr,
            "taxa_fechamento": taxa_fechamento,
            "taxa_cancelamento": taxa_cancelamento,
        },
    }


@st.cache_data(show_spinner=False)
def compute_metrics(df: pd.DataFrame) -> dict[str, int | float | str | None]:
    status_norm = df["STATUS"].map(normalize_status)

    abertos = int((status_norm == "ABERTO").sum())
    aguardando_relatorio = int((status_norm == "AGUARDANDO_RELATORIO").sum())
    fechados = int((status_norm == "FECHADO").sum())
    cancelados = int((status_norm == "CANCELADO").sum())

    # Total Geral considera todos os chamados no filtro.
    total = int(len(df))
    percentual_cancelados = float((cancelados / total) * 100.0) if total > 0 else 0.0

    alta_criticidade_abertos = int(((status_norm == "ABERTO") & (df["CRITICIDADE"] == "ALTA")).sum())

    mttr = None
    if "DATA_FECHAMENTO" in df.columns:
        fechamento = df["DATA_FECHAMENTO"]
        abertura = df["DATA_ABERTURA"]
        duracao = (fechamento - abertura).dt.days
        duracao_valida = duracao[(status_norm == "FECHADO") & duracao.notna() & (duracao >= 0)]
        if not duracao_valida.empty:
            mttr = int(round(float(duracao_valida.mean())))

    # Contagens por tipo de serviço (apenas abertos)
    corretiva = 0
    preventiva = 0
    calibracao = 0
    if "TIPO_SERVICO" in df.columns:
        mask_aberto = status_norm == "ABERTO"
        grupos = df["TIPO_SERVICO"].map(normalize_service_group)
        corretiva = int((mask_aberto & (grupos == "CORRETIVA")).sum())
        preventiva = int((mask_aberto & (grupos == "PREVENTIVA")).sum())
        calibracao = int((mask_aberto & (grupos == "CALIBRACAO")).sum())

    return {
        "abertos": abertos,
        "aguardando_relatorio": aguardando_relatorio,
        "fechados": fechados,
        "total": total,
        "cancelados": cancelados,
        "percentual_cancelados": percentual_cancelados,
        "alta_criticidade_abertos": alta_criticidade_abertos,
        "mttr": mttr,
        "corretiva": corretiva,
        "preventiva": preventiva,
        "calibracao": calibracao,
    }


@st.cache_data(show_spinner=False)
def build_aging_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    abertos = build_open_with_aging(df)
    labels = ["0-7 dias", "7-14 dias", "14-30 dias", ">30 dias"]

    if abertos.empty:
        return pd.DataFrame({"Faixa": labels, "Quantidade": [0, 0, 0, 0]})

    grouped = (
        abertos.groupby("Faixa", observed=False)
        .size()
        .reindex(labels, fill_value=0)
        .reset_index(name="Quantidade")
    )

    return grouped


def build_open_with_aging(df: pd.DataFrame) -> pd.DataFrame:
    status_norm = df["STATUS"].map(normalize_status)
    abertos = df[status_norm == "ABERTO"].copy()
    if abertos.empty:
        return abertos

    today = pd.Timestamp.now().normalize()
    abertos["Dias_Parado"] = (today - abertos["DATA_ABERTURA"]).dt.days
    abertos["Dias_Parado"] = abertos["Dias_Parado"].fillna(0).clip(lower=0)

    bins = [-1, 7, 14, 30, 10_000]
    labels = ["0-7 dias", "7-14 dias", "14-30 dias", ">30 dias"]
    abertos["Faixa"] = pd.cut(abertos["Dias_Parado"], bins=bins, labels=labels)

    return abertos


def build_call_detail_table(df: pd.DataFrame) -> pd.DataFrame:
    details = df.copy()
    requester_col = resolve_requester_column(details)

    details["FORNECEDOR_OUT"] = details["FABRICANTE"].astype("string").fillna("-")
    details["SOLICITANTE_OUT"] = (
        details[requester_col].astype("string").fillna("Solicitante nao encontrado")
        if requester_col
        else "Solicitante nao encontrado"
    )

    return details[
        [
            "MODELO",
            "FORNECEDOR_OUT",
            "TAG",
            "SOLICITANTE_OUT",
            "FALHA",
            "QUADRO",
            "DATA_ABERTURA",
            "Dias_Parado",
        ]
    ].rename(
        columns={
            "MODELO": "Modelo",
            "FORNECEDOR_OUT": "Fornecedor",
            "TAG": "TAG",
            "SOLICITANTE_OUT": "Solicitante",
            "FALHA": "Falha",
            "QUADRO": "Quadro",
            "DATA_ABERTURA": "Data de Abertura",
            "Dias_Parado": "Dias Parado",
        }
    )


def extract_selected_point_value(selection: dict | None, key_name: str) -> str | None:
    if not selection:
        return None
    points = selection.get("selection", {}).get("points", [])
    if not points:
        return None
    point = points[0]
    value = point.get(key_name)
    if value is None:
        return None
    return str(value)


@st.cache_data(show_spinner=False)
def build_pareto_dataframe(df: pd.DataFrame, top_n: int = 8) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame({"Falha": ["SEM DADOS"], "Quantidade": [1]})

    counts = (
        df["FALHA"]
        .fillna("NAO INFORMADO")
        .astype("string")
        .replace("", "NAO INFORMADO")
        .value_counts()
        .head(top_n)
        .reset_index()
    )
    counts.columns = ["Falha", "Quantidade"]

    if counts.empty:
        return pd.DataFrame({"Falha": ["SEM DADOS"], "Quantidade": [1]})

    return counts


def build_mtbf_dataframe(df: pd.DataFrame, top_n: int = 12) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(
            columns=[
                "Modelo",
                "Fabricante",
                "TAG",
                "Falhas",
                "MTBF (dias)",
            ]
        )

    work = df.copy()
    status_norm = work["STATUS"].map(normalize_status)
    work = work[status_norm != "CANCELADO"]
    work = work[work["DATA_ABERTURA"].notna()]

    if work.empty:
        return pd.DataFrame(
            columns=[
                "Modelo",
                "Fabricante",
                "TAG",
                "Falhas",
                "MTBF (dias)",
            ]
        )

    group_cols = ["MODELO", "FABRICANTE", "TAG"]
    rows: list[dict[str, int | str | None]] = []

    grouped = work.sort_values("DATA_ABERTURA", kind="stable").groupby(group_cols, dropna=False)
    for (modelo, fabricante, tag), g in grouped:
        count = int(len(g))
        diffs = g["DATA_ABERTURA"].sort_values().diff().dt.days.dropna()
        diffs = diffs[diffs >= 0]
        mtbf = int(round(float(diffs.mean()))) if not diffs.empty else None

        rows.append(
            {
                "Modelo": str(modelo) if pd.notna(modelo) else "-",
                "Fabricante": str(fabricante) if pd.notna(fabricante) else "-",
                "TAG": str(tag) if pd.notna(tag) else "-",
                "Falhas": count,
                "MTBF (dias)": mtbf,
            }
        )

    result = pd.DataFrame(rows)
    if result.empty:
        return result

    # Converte de forma defensiva para evitar quebra com valores invalidos (ex.: "-").
    result["Falhas"] = pd.to_numeric(result["Falhas"], errors="coerce").fillna(0).astype("Int64")
    result["MTBF (dias)"] = pd.to_numeric(result["MTBF (dias)"], errors="coerce").round().astype("Int64")
    result = result.sort_values(by=["Falhas", "MTBF (dias)"], ascending=[False, True], na_position="last", kind="stable").head(top_n)
    return result


def build_root_cause_dataframe(df: pd.DataFrame, modelo: str, fabricante: str, tag: str, top_n: int = 10) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["Problema Relatado", "Origem do Problema", "Ocorrencias"])

    subset = df[
        (df["MODELO"].astype("string") == modelo)
        & (df["FABRICANTE"].astype("string") == fabricante)
        & (df["TAG"].astype("string") == tag)
    ].copy()

    if subset.empty:
        return pd.DataFrame(columns=["Problema Relatado", "Origem do Problema", "Ocorrencias"])

    origem_col = "ORIGEM_PROBLEMA" if "ORIGEM_PROBLEMA" in subset.columns else None
    if origem_col is None:
        subset["ORIGEM_PROBLEMA"] = "NAO INFORMADO"
        origem_col = "ORIGEM_PROBLEMA"

    summary = (
        subset.assign(
            FALHA=subset["FALHA"].fillna("NAO INFORMADO").astype("string"),
            ORIGEM=subset[origem_col].fillna("NAO INFORMADO").astype("string"),
        )
        .groupby(["FALHA", "ORIGEM"], as_index=False)
        .size()
        .rename(columns={"FALHA": "Problema Relatado", "ORIGEM": "Origem do Problema", "size": "Ocorrencias"})
        .sort_values(by="Ocorrencias", ascending=False, kind="stable")
        .head(top_n)
    )

    return summary


def extract_selected_dataframe_row(selection: object | None) -> int | None:
    if selection is None:
        return None

    rows: object | None = None
    cells: object | None = None

    # Streamlit pode retornar dict-like ou objeto DataframeState.
    if hasattr(selection, "get"):
        selected = selection.get("selection", {})
        if hasattr(selected, "get"):
            rows = selected.get("rows", [])
            cells = selected.get("cells", [])
    else:
        selected = getattr(selection, "selection", None)
        rows = getattr(selected, "rows", None) if selected is not None else None
        cells = getattr(selected, "cells", None) if selected is not None else None

    if rows is None:
        return None

    if not isinstance(rows, list):
        try:
            rows = list(rows)
        except TypeError:
            return None

    if not rows:
        # Fallback para selecao por celula (single-cell).
        if cells is None:
            return None

        if not isinstance(cells, list):
            try:
                cells = list(cells)
            except TypeError:
                return None

        if not cells:
            return None

        first_cell = cells[0]
        if isinstance(first_cell, dict):
            row_idx = first_cell.get("row")
            if row_idx is None:
                return None
            try:
                return int(row_idx)
            except (TypeError, ValueError):
                return None

        if isinstance(first_cell, (list, tuple)) and first_cell:
            try:
                return int(first_cell[0])
            except (TypeError, ValueError):
                return None

        row_attr = getattr(first_cell, "row", None)
        if row_attr is not None:
            try:
                return int(row_attr)
            except (TypeError, ValueError):
                return None

        return None

    try:
        return int(rows[0])
    except (TypeError, ValueError, IndexError):
        return None


def build_root_cause_details_dataframe(
    df: pd.DataFrame,
    modelo: str,
    fabricante: str,
    tag: str,
    problema_relatado: str,
    origem_problema: str,
) -> pd.DataFrame:
    if df.empty:
        return df

    origem_col = "ORIGEM_PROBLEMA" if "ORIGEM_PROBLEMA" in df.columns else None
    work = df.copy()
    if origem_col is None:
        work["ORIGEM_PROBLEMA"] = "NAO INFORMADO"
        origem_col = "ORIGEM_PROBLEMA"

    falha_norm = work["FALHA"].fillna("NAO INFORMADO").astype("string")
    origem_norm = work[origem_col].fillna("NAO INFORMADO").astype("string")

    return work[
        (work["MODELO"].astype("string") == modelo)
        & (work["FABRICANTE"].astype("string") == fabricante)
        & (work["TAG"].astype("string") == tag)
        & (falha_norm == problema_relatado)
        & (origem_norm == origem_problema)
    ].copy()

def build_preventiva_corretiva_intervalo(df: pd.DataFrame, max_interval_days: int = 30) -> pd.DataFrame:
    columns = [
        "TAG",
        "Modelo",
        "Fabricante",
        "Quadro",
        "Data Preventiva",
        "Data Corretiva",
        "Faixa de Dias",
        "Intervalo (dias)",
        "Falha Corretiva",
        "Criticidade",
    ]

    def resolve_faixa(delta_days: float) -> str | None:
        if delta_days <= 2:
            return "0-2 dias"
        if delta_days <= 10:
            return "3-10 dias"
        if delta_days <= 20:
            return "11-20 dias"
        if delta_days <= 30:
            return "21-30 dias"
        return None

    if df.empty or "TIPO_SERVICO" not in df.columns:
        return pd.DataFrame(columns=columns)

    work = df.copy()
    work = work[work["DATA_ABERTURA"].notna()]
    work = work[work["TAG"].notna()]

    if work.empty:
        return pd.DataFrame(columns=columns)

    status_norm = work["STATUS"].map(normalize_status)
    work = work[status_norm != "CANCELADO"]
    if work.empty:
        return pd.DataFrame(columns=columns)

    work = work.assign(SERVICO_GRP=work["TIPO_SERVICO"].map(normalize_service_group))
    work = work.sort_values(by=["TAG", "DATA_ABERTURA"], ascending=[True, True], kind="stable")

    rows: list[dict[str, object]] = []
    grouped = work.groupby("TAG", dropna=False, sort=False)
    for tag, group in grouped:
        g = group.reset_index(drop=True)
        for i in range(len(g)):
            if g.loc[i, "SERVICO_GRP"] != "PREVENTIVA":
                continue

            data_prev = g.loc[i, "DATA_ABERTURA"]
            for j in range(i + 1, len(g)):
                data_evento = g.loc[j, "DATA_ABERTURA"]
                delta_days = (data_evento - data_prev).total_seconds() / 86400.0
                if delta_days < 0:
                    continue

                # Como os eventos estao ordenados por data, apos exceder o limite nao ha mais
                # chance de encontrar corretivas dentro da janela desta preventiva.
                if delta_days > float(max_interval_days):
                    break

                if g.loc[j, "SERVICO_GRP"] != "CORRETIVA":
                    continue

                data_corr = data_evento

                faixa = resolve_faixa(delta_days)
                if faixa is None:
                    continue
                rows.append(
                    {
                        "TAG": str(tag),
                        "Modelo": str(g.loc[j, "MODELO"]) if pd.notna(g.loc[j, "MODELO"]) else "-",
                        "Fabricante": str(g.loc[j, "FABRICANTE"]) if pd.notna(g.loc[j, "FABRICANTE"]) else "-",
                        "Quadro": str(g.loc[j, "QUADRO"]) if pd.notna(g.loc[j, "QUADRO"]) else "-",
                        "Data Preventiva": data_prev.strftime("%d/%m/%Y %H:%M"),
                        "Data Corretiva": data_corr.strftime("%d/%m/%Y %H:%M"),
                        "Faixa de Dias": faixa,
                        "Intervalo (dias)": round(delta_days, 2),
                        "Falha Corretiva": str(g.loc[j, "FALHA"]) if pd.notna(g.loc[j, "FALHA"]) else "NAO INFORMADO",
                        "Criticidade": str(g.loc[j, "CRITICIDADE"]) if pd.notna(g.loc[j, "CRITICIDADE"]) else "-",
                    }
                )

    if not rows:
        return pd.DataFrame(columns=columns)

    result = pd.DataFrame(rows)
    result = result.sort_values(by=["Intervalo (dias)", "Data Corretiva"], ascending=[True, True], kind="stable")
    return result


def build_root_cause_modal_table(details_df: pd.DataFrame) -> pd.DataFrame:
    if details_df.empty:
        return pd.DataFrame(columns=["TAG", "Quadro de Trabalho", "Problema"])

    return (
        details_df[["TAG", "QUADRO", "FALHA"]]
        .rename(columns={"QUADRO": "Quadro de Trabalho", "FALHA": "Problema"})
        .fillna("-")
    )


def render_mtbf_section(filtered: pd.DataFrame) -> None:
    st.markdown(
        """
        <span style='font-size:1.45rem;font-weight:800;'>Fiabilidade e Historico de Equipamentos (MTBF) - Top 10
            <span title='Lógica: calcula média dos intervalos entre falhas para cada equipamento (MTBF).' style='display:inline-block;vertical-align:middle;cursor:help;'><svg width='18' height='18' viewBox='0 0 18 18'><circle cx='9' cy='9' r='8' fill='#e6effa' stroke='#b8c8dd'/><text x='9' y='13' text-anchor='middle' font-size='11' font-weight='bold' fill='#1e4b7a'>i</text></svg></span>
        </span>
        """,
        unsafe_allow_html=True,
    )
    st.caption(
        "Analisa recorrencia de falhas por equipamento e ajuda a focar causa raiz em ORIGEM DO PROBLEMA."
    )
    st.caption(f"Base usada (filtros globais): {len(filtered)} registro(s)")

    mtbf_df = build_mtbf_dataframe(filtered, top_n=10)
    if mtbf_df.empty:
        st.info("Nao ha dados suficientes para calcular MTBF nos filtros selecionados.")
        return

    c1, c2 = st.columns([1.3, 1])

    with c1:
        st.markdown("""
            <span style='font-size:1.1rem;font-weight:700;'>Modelos com maior recorrencia de falhas
                <span title='Lógica: ordena modelos por quantidade de falhas para priorizar manutenção.' style='display:inline-block;vertical-align:middle;cursor:help;'><svg width='16' height='16' viewBox='0 0 18 18'><circle cx='9' cy='9' r='8' fill='#e6effa' stroke='#b8c8dd'/><text x='9' y='13' text-anchor='middle' font-size='10' font-weight='bold' fill='#1e4b7a'>i</text></svg></span>
            </span>
        """, unsafe_allow_html=True)
        st.dataframe(mtbf_df, use_container_width=True, hide_index=True)

    with c2:
        eq_options = (
            mtbf_df.apply(
                lambda r: f"{r['Modelo']} | {r['Fabricante']} | {r['TAG']}",
                axis=1,
            )
            .tolist()
        )
        selected_eq = st.selectbox("Modelo para causa raiz", options=eq_options, key="mtbf_equipment_selector")

        modelo, fabricante, tag = [x.strip() for x in selected_eq.split("|")]
        root_df = build_root_cause_dataframe(filtered, modelo, fabricante, tag)

        st.markdown("""
            <span style='font-size:1.1rem;font-weight:700;'>Problema Relatado x Origem do Problema
                <span title='Lógica: agrupa falhas por origem para identificar causas recorrentes.' style='display:inline-block;vertical-align:middle;cursor:help;'><svg width='16' height='16' viewBox='0 0 18 18'><circle cx='9' cy='9' r='8' fill='#e6effa' stroke='#b8c8dd'/><text x='9' y='13' text-anchor='middle' font-size='10' font-weight='bold' fill='#1e4b7a'>i</text></svg></span>
            </span>
        """, unsafe_allow_html=True)
        if root_df.empty:
            st.info("Sem dados de causa raiz para o equipamento selecionado.")
        else:
            root_sel = st.dataframe(
                root_df,
                use_container_width=True,
                hide_index=True,
                key="root_cause_table",
                on_select="rerun",
                selection_mode=["single-cell"],
            )

            selected_row_idx = extract_selected_dataframe_row(root_sel)
            if selected_row_idx is not None and 0 <= selected_row_idx < len(root_df):
                row = root_df.iloc[selected_row_idx]
                problema = str(row["Problema Relatado"])
                origem = str(row["Origem do Problema"])
                selection_key = f"{modelo}|{fabricante}|{tag}|{problema}|{origem}"

                st.session_state["selected_root_modelo"] = modelo
                st.session_state["selected_root_fabricante"] = fabricante
                st.session_state["selected_root_tag"] = tag
                st.session_state["selected_root_problema"] = problema
                st.session_state["selected_root_origem"] = origem

                st.caption(f"Linha selecionada: {problema} | {origem}")

                if st.session_state.get("selected_root_row_key") != selection_key:
                    st.session_state["selected_root_row_key"] = selection_key
                    st.session_state["details_modal_kind"] = "root_cause"
                    st.session_state["details_modal_open"] = True

                if st.button("Abrir detalhes da linha selecionada", key="open_root_details_manual"):
                    st.session_state["details_modal_kind"] = "root_cause"
                    st.session_state["details_modal_open"] = True
                    st.rerun()


def open_calls_table(df: pd.DataFrame) -> pd.DataFrame:
    status_norm = df["STATUS"].map(normalize_status)
    abertos = df[status_norm == "ABERTO"].copy()

    today = pd.Timestamp.now().normalize()
    abertos["DIAS_PARADO"] = (today - abertos["DATA_ABERTURA"]).dt.days
    abertos["DIAS_PARADO"] = abertos["DIAS_PARADO"].fillna(0).clip(lower=0).astype(int)

    ticket_number_col = resolve_ticket_number_column(abertos)
    if ticket_number_col:
        abertos["NUMERO_CHAMADO_OUT"] = abertos[ticket_number_col].astype("string").fillna("-")
    else:
        abertos["NUMERO_CHAMADO_OUT"] = "-"

    requester_col = resolve_requester_column(abertos)
    if requester_col:
        abertos["SOLICITANTE_OUT"] = abertos[requester_col].astype("string").fillna("Solicitante nao encontrado")
    else:
        abertos["SOLICITANTE_OUT"] = "Solicitante nao encontrado"

    observation_col = resolve_observation_column(abertos)
    if observation_col:
        abertos["OBSERVACAO_OUT"] = abertos[observation_col].astype("string").fillna("Observacao nao encontrada")
    else:
        abertos["OBSERVACAO_OUT"] = "Observacao nao encontrada"

    result = abertos[
        [
            "QUADRO",
            "NUMERO_CHAMADO_OUT",
            "TIPO_EQUIPAMENTO",
            "TAG",
            "MODELO",
            "FABRICANTE",
            "SOLICITANTE_OUT",
            "OBSERVACAO_OUT",
            "DIAS_PARADO",
            "FALHA",
        ]
    ].rename(
        columns={
            "QUADRO": "Quadro de Trabalho",
            "NUMERO_CHAMADO_OUT": "Numero do Chamado",
            "TIPO_EQUIPAMENTO": "Tipo de Equipamento",
            "TAG": "TAG",
            "MODELO": "Modelo",
            "FABRICANTE": "Fabricante",
            "SOLICITANTE_OUT": "Solicitante",
            "OBSERVACAO_OUT": "Observacao",
            "DIAS_PARADO": "Dias Parado",
            "FALHA": "Falha",
        }
    )

    return result.sort_values(by="Tipo de Equipamento", ascending=True, kind="stable")


def get_detail_dataframe(df: pd.DataFrame, category: str) -> pd.DataFrame:
    status_norm = df["STATUS"].map(normalize_status)

    if category == "abertos":
        subset = df[status_norm == "ABERTO"].copy()
    elif category == "aguardando_relatorio":
        subset = df[status_norm == "AGUARDANDO_RELATORIO"].copy()
    elif category == "criticos_aberto":
        subset = df[(status_norm == "ABERTO") & (df.get("CRITICIDADE", "") == "ALTA")].copy()
    elif category == "backlog_30":
        subset = build_open_with_aging(df)
        subset = subset[subset["Dias_Parado"] > 30].copy()
    elif category == "corretiva":
        service_normalized = df["TIPO_SERVICO"].map(normalize_service_group) if "TIPO_SERVICO" in df.columns else pd.Series([], dtype="object")
        subset = df[(status_norm == "ABERTO") & (service_normalized == "CORRETIVA")].copy()
    elif category == "preventiva":
        service_normalized = df["TIPO_SERVICO"].map(normalize_service_group) if "TIPO_SERVICO" in df.columns else pd.Series([], dtype="object")
        subset = df[(status_norm == "ABERTO") & (service_normalized == "PREVENTIVA")].copy()
    elif category == "calibracao":
        service_normalized = df["TIPO_SERVICO"].map(normalize_service_group) if "TIPO_SERVICO" in df.columns else pd.Series([], dtype="object")
        subset = df[(status_norm == "ABERTO") & (service_normalized == "CALIBRACAO")].copy()
    else:
        subset = df.copy()

    if subset.empty:
        return subset

    if "Dias_Parado" not in subset.columns and "DATA_ABERTURA" in subset.columns:
        today = pd.Timestamp.now().normalize()
        subset["Dias_Parado"] = (today - subset["DATA_ABERTURA"]).dt.days.fillna(0).clip(lower=0)

    return build_call_detail_table(subset)


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
            letter-spacing: 0.3px;
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
            user-select: none;
            transition: all 0.2s ease;
        }
        .kpi-info-dot:hover {
            background: var(--dasa-blue);
            color: #ffffff;
            border-color: var(--dasa-blue);
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
            align-items: stretch;
            margin: 4px 0 14px 0;
        }
        .dashboard-block {
            background: #ffffff;
            border: 1px solid var(--ec-border);
            border-radius: 10px;
            padding: 10px 12px;
            box-shadow: 0 2px 6px rgba(10,139,141,0.05);
            transition: all 0.25s ease;
        }
        .dashboard-block:hover {
            box-shadow: 0 4px 12px rgba(10,139,141,0.1);
        }

        .upload-panel {
            background: #ffffff;
            border: 2px dashed var(--dasa-blue-light);
            border-radius: 12px;
            padding: 20px 20px;
            box-shadow: 0 2px 8px rgba(10,139,141,0.06);
            margin-bottom: 8px;
            transition: all 0.25s ease;
            text-align: center;
        }
        .upload-panel:hover {
            border-color: var(--dasa-blue);
            box-shadow: 0 4px 12px rgba(10,139,141,0.1);
        }
        .upload-panel h3 {
            margin: 0 0 4px 0;
            color: var(--dasa-blue);
            font-size: 1.1rem;
            font-weight: 900;
        }
        .upload-panel p {
            margin: 0;
            color: #2d4a66;
            font-size: 0.86rem;
            font-weight: 600;
        }

        @media (max-width: 680px) {
            .kpi-responsive-grid {
                grid-template-columns: 1fr;
            }

            .kpi-grid-value {
                font-size: 1.35rem;
            }
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
            backlog_30 = 0

    total = int(metrics.get("total", 0))
    fechados = int(metrics.get("fechados", 0))
    taxa_fechamento = (fechados / total * 100.0) if total > 0 else 0.0

    cards = [
        (
            "abertos",
            "Chamados Abertos",
            format_int_pt_br(int(metrics['abertos'])),
            "Situação atual",
            "Função: total de chamados ABERTOS. Lógica: STATUS normalizado = ABERTO",
        ),
        (
            "aguardando_relatorio",
            "Aguardando Relatório",
            format_int_pt_br(int(metrics.get('aguardando_relatorio', 0))),
            "Status especial",
            "Função: chamados que estão em AGUARDANDO_RELATORIO e não entram em abertos.",
        ),
        (
            "criticos_aberto",
            "Chamados Críticos em Aberto",
            format_int_pt_br(int(metrics['alta_criticidade_abertos'])),
            "Criticidade ALTA ativa",
            "Função: destaca urgências em aberto para priorização imediata.\nLógica: STATUS=ABERTO e CRITICIDADE=ALTA",
        ),
        (
            "backlog_30",
            "Backlog >30 dias",
            format_int_pt_br(backlog_30),
            "Fila com maior risco",
            "Função: mostra chamados envelhecidos com maior risco de impacto operacional.\nLógica: quantidade de chamados abertos com Faixa '>30 dias'",
        ),
        (
            "corretiva",
            "Corretiva em Aberto",
            format_int_pt_br(int(metrics.get("corretiva", 0))),
            "Chamados corretivos abertos",
            "Função: chamados corretivos com status ABERTO no período filtrado.\nLógica: STATUS=ABERTO e TIPO_SERVICO normalizado = CORRETIVA",
        ),
        (
            "preventiva",
            "Preventiva em Aberto",
            format_int_pt_br(int(metrics.get("preventiva", 0))),
            "Chamados preventivos abertos",
            "Função: chamados preventivos com status ABERTO no período filtrado.\nLógica: STATUS=ABERTO e TIPO_SERVICO normalizado = PREVENTIVA",
        ),
        (
            "calibracao",
            "Calibração em Aberto",
            format_int_pt_br(int(metrics.get("calibracao", 0))),
            "Chamados de calibração abertos",
            "Função: chamados de calibração (inclui verificação) com status ABERTO no período filtrado.\nLógica: STATUS=ABERTO e TIPO_SERVICO normalizado = CALIBRACAO",
        ),
        (
            "mttr",
            "Tempo Médio de Atendimento (MTTR)",
            mttr_text,
            "Meta operacional: <= 15 dias",
            "Função: acompanha o tempo médio para concluir chamados e controlar eficiência.\nLógica: média dos dias entre DATA_ABERTURA e DATA_FECHAMENTO para chamados fechados",
        ),
        (
            "taxa_fechamento",
            "Taxa de Fechamento",
            f"{format_percent_pt_br(taxa_fechamento)}%",
            "Fechados sobre total",
            "Função: indica efetividade do time na conversão de chamados em resoluções.\nLógica: (fechados/total)*100",
        ),
        (
            "disponibilidade",
            "Disponibilidade Global",
            f"{format_percent_pt_br(max(0.0, 100.0 - percentual_cancelados))}%",
            "Baseado em cancelamentos",
            "Função: mede a estabilidade operacional com percentual de chamados não cancelados.\nLógica: 100% - percentual_cancelados",
        ),
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


@st.cache_data(show_spinner=False)
def build_operational_radar_table(df: pd.DataFrame, max_rows: int = 12) -> pd.DataFrame:
    status_norm = df["STATUS"].map(normalize_status)
    abertos = df[status_norm == "ABERTO"].copy()
    if abertos.empty:
        return pd.DataFrame(columns=["Modelo", "Setor", "Status/SLA", "Nivel/Risco", "Recomendacao"])

    today = pd.Timestamp.now().normalize()
    abertos["DIAS_PARADO"] = (today - abertos["DATA_ABERTURA"]).dt.days
    abertos["DIAS_PARADO"] = abertos["DIAS_PARADO"].fillna(0).clip(lower=0).astype(int)

    criticidade_norm = abertos["CRITICIDADE"].astype("string").str.upper().fillna("NAO INFORMADO")
    base_risco = criticidade_norm.map({"ALTA": 3, "MEDIA": 2, "BAIXA": 1}).fillna(1).astype(int)
    score = (base_risco * 10) + (abertos["DIAS_PARADO"] // 3)

    requester_col = resolve_requester_column(abertos)
    if requester_col:
        solicitante = abertos[requester_col].astype("string").fillna("Solicitante nao encontrado")
    else:
        solicitante = pd.Series("Solicitante nao encontrado", index=abertos.index, dtype="string")

    observation_col = resolve_observation_column(abertos)
    if observation_col:
        observacao = abertos[observation_col].astype("string").fillna("Observacao nao encontrada")
    else:
        observacao = pd.Series("Observacao nao encontrada", index=abertos.index, dtype="string")

    abertos = abertos.assign(
        MODELO_OUT=abertos["MODELO"].astype("string").fillna("-"),
        SETOR_OUT=abertos["QUADRO"].astype("string").fillna("-"),
        SOLICITANTE_OUT=solicitante,
        OBSERVACAO_OUT=observacao,
        STATUS_SLA=abertos["DIAS_PARADO"].map(lambda d: f"Parado - {int(d)}d"),
        NIVEL_RISCO=score.map(lambda s: f"Risco {int(s):02d}"),
        SCORE_INT=score.astype(int),
    )

    def recomendacao(row) -> str:
        s = row["SCORE_INT"]
        d = row["DIAS_PARADO"]
        if s >= 50 or d >= 180:
            return "Critico - Escalonar gestao"
        if s >= 30 or d >= 90:
            return "Urgente - Cobrar fornecedor"
        if s >= 20 or d >= 30:
            return "Atencao - Acompanhar SLA"
        if d >= 7:
            return "Monitorar prazo"
        return "Dentro do esperado"

    abertos["ACOES"] = abertos.apply(recomendacao, axis=1)

    # Top 12 real: ordena pelo maior risco e, em empate, maior dias parado.
    ranked = abertos.sort_values(by=["SCORE_INT", "DIAS_PARADO"], ascending=[False, False], kind="stable")

    table = ranked[["MODELO_OUT", "SETOR_OUT", "SOLICITANTE_OUT", "OBSERVACAO_OUT", "STATUS_SLA", "NIVEL_RISCO", "ACOES"]].rename(
        columns={
            "MODELO_OUT": "Modelo",
            "SETOR_OUT": "Setor",
            "SOLICITANTE_OUT": "Solicitante",
            "OBSERVACAO_OUT": "Observacao",
            "STATUS_SLA": "Status/SLA",
            "NIVEL_RISCO": "Nivel/Risco",
            "ACOES": "Recomendacao",
        }
    )

    return table.head(max_rows)


def apply_executive_styles() -> None:
    st.markdown(
        """
        <style>
        /* ═══════════════════════════════════════════════════
           TEMA DASA — Azul Corporativo + Laranja Energia
           ═══════════════════════════════════════════════════ */

        @keyframes fadeInUp {
            from { opacity: 0; transform: translateY(22px); }
            to   { opacity: 1; transform: translateY(0); }
        }
        @keyframes fadeIn {
            from { opacity: 0; }
            to   { opacity: 1; }
        }
        @keyframes slideInLeft {
            from { opacity: 0; transform: translateX(-30px); }
            to   { opacity: 1; transform: translateX(0); }
        }
        @keyframes pulseGlow {
            0%, 100% { box-shadow: 0 0 0 0 rgba(255, 106, 19, 0.0); }
            50%      { box-shadow: 0 0 18px 4px rgba(255, 106, 19, 0.18); }
        }
        @keyframes shimmer {
            0%   { background-position: -200% 0; }
            100% { background-position: 200% 0; }
        }
        @keyframes brandPulse {
            0%, 100% { transform: scale(1); }
            50%      { transform: scale(1.015); }
        }
        @keyframes barGrow {
            from { width: 0%; }
            to   { width: 100%; }
        }
        @keyframes gradientFlow {
            0%   { background-position: 0% 50%; }
            50%  { background-position: 100% 50%; }
            100% { background-position: 0% 50%; }
        }
        @keyframes float {
            0%, 100% { transform: translateY(0); }
            50%      { transform: translateY(-4px); }
        }
        @keyframes spinGear {
            from { transform: rotate(0deg); }
            to   { transform: rotate(360deg); }
        }
        @keyframes spinGearReverse {
            from { transform: rotate(0deg); }
            to   { transform: rotate(-360deg); }
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


        .hero-title {
            margin: 0;
            font-size: clamp(2.1rem, 5vw, 3.8rem);
            font-weight: 900;
            letter-spacing: 1px;
            color: #ffffff;
            z-index: 2;
            text-shadow: 0 10px 28px rgba(0, 0, 0, 0.36);
        }

        .hero-subtitle {
            margin: 0;
            color: #ecf8f9;
            font-size: clamp(1.1rem, 2.1vw, 1.3rem);
            font-weight: 600;
            line-height: 1.4;
            z-index: 2;
            text-shadow: 0 6px 18px rgba(0, 0, 0, 0.28);
        }



        /* ── Scrollbar personalizada ── */
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

        .main .block-container {
            padding-top: 0.8rem;
            padding-bottom: 1.4rem;
            animation: fadeIn 0.6s ease-out;
        }

        /* ── Painéis (clean) ── */
        .ec-panel {
            background: #ffffff;
            border: 1px solid var(--ec-border);
            border-radius: 12px;
            padding: 14px 16px;
            box-shadow: 0 2px 8px rgba(10,139,141,0.06);
            animation: fadeInUp 0.5s ease-out;
            position: relative;
            overflow: hidden;
        }
        .ec-panel::before {
            content: "";
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 3px;
            background: var(--dasa-blue);
        }

        .ec-section-title {
            color: var(--dasa-blue);
            font-weight: 900;
            font-size: 1.1rem;
            margin-bottom: 6px;
            letter-spacing: 0.3px;
            text-shadow: none;
        }

        .ec-section-subtitle {
            color: #3a5a78;
            font-size: 0.88rem;
            font-weight: 600;
            margin-bottom: 0;
        }

        /* ── Status pills ── */
        .ec-status-row {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
            margin: 8px 0 14px 0;
        }

        .ec-pill {
            border-radius: 12px;
            padding: 10px 12px;
            border: 1px solid transparent;
            font-size: 0.9rem;
            font-weight: 700;
            animation: fadeInUp 0.4s ease-out;
        }

        .ec-pill-risk {
            background: var(--ec-risk-bg);
            border-color: #fecaca;
            color: var(--ec-risk);
        }

        .ec-pill-warn {
            background: var(--ec-warn-bg);
            border-color: #fed7aa;
            color: var(--ec-warn);
        }

        .ec-pill-ok {
            background: var(--ec-ok-bg);
            border-color: #bbf7d0;
            color: var(--ec-ok);
        }

        .ec-small-muted {
            color: #3a5570;
            font-size: 0.84rem;
            font-weight: 500;
            margin-top: 2px;
        }

        /* ── Detail cards ── */
        .ec-detail-card {
            background: #ffffff;
            border: 1px solid var(--ec-border);
            border-left: 4px solid var(--dasa-blue);
            border-radius: 10px;
            padding: 12px 14px;
            box-shadow: 0 2px 8px rgba(10,139,141,0.05);
            margin-bottom: 8px;
            animation: fadeInUp 0.4s ease-out;
            transition: all 0.25s ease;
        }
        .ec-detail-card:hover {
            box-shadow: 0 4px 16px rgba(10,139,141,0.12);
            border-left-color: var(--dasa-blue-light);
        }

        .ec-detail-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 8px;
            margin: 6px 0;
        }

        .ec-detail-item {
            background: var(--dasa-blue-pale);
            border: 1px solid #c8dede;
            border-radius: 8px;
            padding: 8px 10px;
            font-size: 0.92rem;
            color: #0a2e2f;
            line-height: 1.35;
            font-weight: 500;
        }

        .ec-detail-item strong {
            color: var(--dasa-blue);
            font-weight: 800;
        }

        .ec-detail-note {
            margin-top: 6px;
            color: #3a5570;
            font-size: 0.84rem;
            font-weight: 500;
        }

        /* ── Summary grid ── */
        .ec-summary-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 10px;
            margin: 8px 0 12px 0;
        }

        .ec-summary-item {
            background: #ffffff;
            border: 1px solid var(--ec-border);
            border-radius: 10px;
            padding: 10px 12px;
            box-shadow: 0 2px 6px rgba(10,139,141,0.05);
            animation: fadeInUp 0.5s ease-out;
            transition: all 0.25s ease;
            position: relative;
            overflow: hidden;
        }
        .ec-summary-item:hover {
            box-shadow: 0 4px 12px rgba(10,139,141,0.1);
        }

        .ec-summary-label {
            color: #2d4a66;
            font-size: 0.84rem;
            font-weight: 800;
            margin-bottom: 4px;
            text-transform: uppercase;
            letter-spacing: 0.3px;
        }

        .ec-summary-value {
            color: var(--dasa-blue);
            font-size: 1.25rem;
            font-weight: 900;
            line-height: 1.1;
        }

        .ec-modal-panel {
            background: #f8fbfb;
            border: 1px solid var(--ec-border);
            border-radius: 10px;
            padding: 10px 12px;
            margin-bottom: 8px;
        }

        /* ── SIDEBAR ARKMEDS ── */
        section[data-testid="stSidebar"] {
            background: linear-gradient(180deg, #067375 0%, #0A8B8D 30%, #056d6f 100%);
            border-right: none;
            box-shadow: 2px 0 12px rgba(10,139,141,0.2);
            position: relative;
        }
        section[data-testid="stSidebar"]::after {
            content: "";
            position: absolute;
            top: 0;
            right: 0;
            width: 2px;
            height: 100%;
            background: rgba(255,255,255,0.15);
        }

        section[data-testid="stSidebar"] h2,
        section[data-testid="stSidebar"] h3,
        section[data-testid="stSidebar"] label,
        section[data-testid="stSidebar"] p,
        section[data-testid="stSidebar"] span {
            color: #e8f0fe !important;
        }

        section[data-testid="stSidebar"] .stCaption p {
            color: #9cb8d8 !important;
        }

        section[data-testid="stSidebar"] div[data-testid="stExpander"] details {
            border: 1px solid rgba(255,255,255,0.12);
            border-radius: 10px;
            background: rgba(255,255,255,0.06);
            transition: all 0.3s ease;
        }
        section[data-testid="stSidebar"] div[data-testid="stExpander"] details:hover {
            background: rgba(255,255,255,0.10);
            border-color: rgba(255,255,255,0.25);
        }
        section[data-testid="stSidebar"] div[data-testid="stExpander"] details[open] {
            border-color: rgba(255,255,255,0.3);
            background: rgba(255,255,255,0.08);
        }

        section[data-testid="stSidebar"] div[data-testid="stExpander"] summary {
            font-weight: 800;
            color: #ffffff !important;
        }

        section[data-testid="stSidebar"] div[data-testid="stExpander"] summary span {
            color: #ffffff !important;
        }

        section[data-testid="stSidebar"] .stTextInput input {
            background: rgba(255,255,255,0.92);
            border: 1px solid rgba(255,255,255,0.18);
            color: #0a2e2f;
            border-radius: 8px;
            transition: all 0.3s ease;
        }
        section[data-testid="stSidebar"] .stTextInput input:focus {
            border-color: var(--dasa-blue-light);
            box-shadow: 0 0 8px rgba(20,163,165,0.25);
            background: rgba(255,255,255,0.96);
        }
        section[data-testid="stSidebar"] .stTextInput input::placeholder {
            color: #8cb8b8;
        }

        section[data-testid="stSidebar"] .stButton > button {
            background: rgba(255,255,255,0.15);
            color: #ffffff;
            border: 1px solid rgba(255,255,255,0.3);
            font-weight: 700;
            border-radius: 8px;
            transition: all 0.25s ease;
        }
        section[data-testid="stSidebar"] .stButton > button:hover {
            background: rgba(255,255,255,0.25);
            border-color: rgba(255,255,255,0.5);
            box-shadow: 0 4px 12px rgba(10,139,141,0.25);
        }

        section[data-testid="stSidebar"] .stDateInput input {
            background: rgba(255,255,255,0.92);
            border: 1px solid rgba(255,255,255,0.18);
            color: #0a1e3d;
            border-radius: 10px;
        }

        section[data-testid="stSidebar"] .stCheckbox label span {
            color: #d0e0f0 !important;
        }

        section[data-testid="stSidebar"] .stRadio label p {
            color: #d0e0f0 !important;
        }

        section[data-testid="stSidebar"] hr {
            border-color: rgba(255,255,255,0.12);
        }

        section[data-testid="stSidebar"] .stSelectbox > div > div {
            background: rgba(255,255,255,0.10);
            border: 1px solid rgba(255,255,255,0.18);
            color: #ffffff;
            border-radius: 8px;
            transition: all 0.3s ease;
        }
        section[data-testid="stSidebar"] .stSelectbox > div > div:hover {
            border-color: rgba(255,255,255,0.4);
        }

        /* ── Headings & Metrics ── */
        div[data-testid="stMetricValue"] {
            color: var(--dasa-blue);
            font-weight: 900;
            text-shadow: 0 1px 2px rgba(0,0,0,0.05);
        }
        h1, h2, h3 {
            color: var(--dasa-blue) !important;
            font-weight: 800 !important;
        }

        /* ── DataFrames ── */
        div[data-testid="stDataFrame"] {
            border: 1px solid var(--ec-border);
            border-radius: 10px;
            background: #ffffff;
            box-shadow: 0 2px 8px rgba(10,139,141,0.05);
            animation: fadeIn 0.5s ease-out;
            overflow: hidden;
        }
        div[data-testid="stDataFrame"]::before {
            content: "";
            display: block;
            height: 3px;
            background: var(--dasa-blue);
        }

        /* ── Buttons ── */
        .stButton > button,
        .stDownloadButton > button {
            border-radius: 8px;
            border: 1px solid var(--ec-border);
            background: #ffffff;
            color: var(--dasa-blue);
            font-weight: 700;
            transition: all 0.25s ease;
        }

        .stButton > button:hover,
        .stDownloadButton > button:hover {
            border-color: var(--dasa-blue);
            background: var(--dasa-blue-pale);
            color: var(--dasa-blue);
            box-shadow: 0 2px 8px rgba(10,139,141,0.12);
        }

        .stDownloadButton > button {
            border-left: 3px solid var(--dasa-blue);
            background: var(--dasa-blue-pale);
        }
        .stDownloadButton > button:hover {
            background: #d0eded;
            border-left-color: #067375;
        }

        /* ── Inputs premium ── */
        div[data-testid="stRadio"] label p {
            white-space: nowrap;
            word-break: normal;
            overflow-wrap: normal;
            font-size: 1rem;
            letter-spacing: 0.1px;
        }

        .stTextInput > div > div > input,
        .stNumberInput > div > div > input {
            border-radius: 10px;
            border: 1px solid var(--ec-border);
            transition: all 0.3s ease;
        }
        .stTextInput > div > div > input:focus,
        .stNumberInput > div > div > input:focus {
            border-color: var(--dasa-blue-light);
            box-shadow: 0 0 0 3px rgba(10,139,141,0.1);
        }

        .stSelectbox > div > div {
            border-radius: 10px !important;
            transition: all 0.3s ease;
        }
        .stSelectbox > div > div:hover {
            border-color: var(--dasa-blue-light);
        }

        .stMultiSelect > div > div {
            border-radius: 10px !important;
        }

        div[data-testid="stPopover"] button {
            min-height: 44px;
            font-size: 0.98rem;
            font-weight: 600;
            border-radius: 10px;
        }

        div[data-testid="stPopover"] button p {
            white-space: nowrap;
            word-break: normal;
            overflow-wrap: normal;
        }

        div[data-testid="stDateInput"] input {
            font-size: 1rem;
            border-radius: 10px;
        }

        /* ── Alertas redesenhados ── */
        div[data-testid="stAlert"] {
            border-radius: 12px;
            border: none;
            animation: fadeInUp 0.3s ease-out;
        }
        .stAlert [data-testid="stNotificationContentInfo"] {
            background: linear-gradient(135deg, #e8f4fd 0%, #d4ecfc 100%);
            border-left: 4px solid var(--dasa-blue-light);
            border-radius: 12px;
        }
        .stAlert [data-testid="stNotificationContentSuccess"] {
            background: linear-gradient(135deg, #e8fdf0 0%, #d0f5df 100%);
            border-left: 4px solid #16a34a;
            border-radius: 12px;
        }
        .stAlert [data-testid="stNotificationContentWarning"] {
            background: linear-gradient(135deg, #fef9e8 0%, #fdf0c8 100%);
            border-left: 4px solid #d97706;
            border-radius: 12px;
        }
        .stAlert [data-testid="stNotificationContentError"] {
            background: linear-gradient(135deg, #fde8e8 0%, #fcd4d4 100%);
            border-left: 4px solid #dc2626;
            border-radius: 12px;
        }

        /* ── Expanders ── */
        div[data-testid="stExpander"] details {
            border: 1px solid var(--ec-border);
            border-radius: 10px !important;
            background: #ffffff;
            transition: all 0.25s ease;
            overflow: hidden;
        }
        div[data-testid="stExpander"] details:hover {
            box-shadow: 0 2px 8px rgba(10,139,141,0.08);
        }
        div[data-testid="stExpander"] details[open] {
            border-color: var(--dasa-blue-light);
            box-shadow: 0 6px 20px rgba(0, 59, 113, 0.1);
        }
        div[data-testid="stExpander"] summary {
            font-weight: 800;
            color: var(--dasa-blue);
            border-radius: 14px;
            transition: background 0.2s ease;
        }
        div[data-testid="stExpander"] summary:hover {
            background: rgba(10,139,141,0.04);
        }

        /* ── Header ── */
        header[data-testid="stHeader"] {
            background: var(--dasa-blue);
            border-bottom: none;
            height: 3px;
            min-height: 3px;
        }

        [data-testid="stSidebarCollapsedControl"] {
            display: flex !important;
            visibility: visible !important;
            opacity: 1 !important;
            z-index: 1000;
        }

        /* ── BRAND HEADER ARKMEDS ── */
        .brand-wrap {
            display: flex;
            justify-content: center;
            margin: 0 0 16px 0;
            animation: fadeInUp 0.5s ease-out;
        }
        .brand-card {
            background: linear-gradient(135deg, #0A8B8D 0%, #067375 50%, #056d6f 100%);
            border: none;
            border-radius: 16px;
            padding: 20px 32px;
            box-shadow: 0 4px 16px rgba(10,139,141,0.2);
            text-align: center;
            width: min(580px, 96vw);
            min-height: 120px;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            position: relative;
            overflow: hidden;
        }
        .brand-card::before {
            content: "";
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 3px;
            background: rgba(255,255,255,0.2);
        }
        .brand-card::after {
            content: "";
            position: absolute;
            bottom: 0;
            left: 0;
            right: 0;
            height: 3px;
            background: rgba(255,255,255,0.1);
        }
        .brand-card .brand-glow {
            position: absolute;
            top: -60%;
            left: -20%;
            width: 140%;
            height: 200%;
            background: radial-gradient(ellipse at center, rgba(255,255,255,0.04) 0%, transparent 60%);
            pointer-events: none;
        }
        .brand-logo-icon {
            width: 64px;
            height: 64px;
            margin-bottom: 10px;
        }
        .gear-main {
            transform-origin: 50px 50px;
            animation: spinGear 8s linear infinite;
        }
        .gear-small {
            transform-origin: 78px 74px;
            animation: spinGearReverse 5s linear infinite;
        }
        .brand-title {
            margin: 0 !important;
            font-weight: 900;
            letter-spacing: 6px;
            font-size: 38px !important;
            color: #ffffff;
            line-height: 1;
            text-transform: uppercase;
        }
        .brand-divider {
            width: 60px;
            height: 2px;
            background: rgba(255,255,255,0.35);
            border-radius: 2px;
            margin: 10px auto;
        }
        .brand-subtitle {
            margin: 0 !important;
            font-weight: 600;
            font-size: 14px !important;
            color: rgba(255,255,255,0.8);
            line-height: 1.3;
            letter-spacing: 3px;
            text-transform: uppercase;
        }

        /* ── Tabs Arkmeds ── */
        .stTabs [data-baseweb="tab-list"] {
            gap: 2px;
            background: #ffffff;
            border-bottom: 2px solid var(--ec-border);
            border-radius: 0;
            padding: 0;
        }
        .stTabs [data-baseweb="tab"] {
            background: transparent;
            border: none;
            border-radius: 0;
            border-bottom: 3px solid transparent;
            color: #5a7a7a;
            font-weight: 700;
            font-size: 0.95rem;
            padding: 10px 20px;
            transition: all 0.2s ease;
        }
        .stTabs [data-baseweb="tab"]:hover {
            color: var(--dasa-blue);
            border-bottom-color: rgba(10,139,141,0.3);
        }
        .stTabs [aria-selected="true"] {
            color: var(--dasa-blue) !important;
            background: transparent !important;
            font-weight: 900;
            border-bottom: 3px solid var(--dasa-blue) !important;
        }

        /* ── Charts ── */
        div[data-testid="stPlotlyChart"] {
            width: 100%;
            animation: fadeIn 0.4s ease-out;
            border-radius: 10px;
            overflow: hidden;
            box-shadow: 0 2px 8px rgba(10,139,141,0.05);
            border: 1px solid var(--ec-border);
            background: #ffffff;
        }

        /* ── Section dividers ── */
        .section-divider {
            height: 1px;
            background: var(--ec-border);
            margin: 16px 0;
            border: none;
        }

        /* ── Footer ── */
        .app-footer {
            text-align: center;
            padding: 16px 0 8px 0;
            margin-top: 24px;
            border-top: 2px solid var(--ec-border);
            animation: fadeIn 1s ease-out;
        }
        .app-footer-text {
            color: var(--ec-muted);
            font-size: 0.78rem;
            font-weight: 600;
            letter-spacing: 0.5px;
        }
        .app-footer-brand {
            color: var(--dasa-blue);
            font-weight: 800;
        }
        .app-footer-accent {
            color: var(--dasa-orange);
        }

        /* ── Responsive ── */
        @media (max-width: 1200px) {
            .main .block-container {
                padding-left: 0.9rem;
                padding-right: 0.9rem;
            }

            div[data-testid="stHorizontalBlock"] {
                flex-wrap: wrap;
                row-gap: 0.7rem;
            }

            div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {
                flex: 1 1 calc(50% - 0.7rem) !important;
                min-width: 280px !important;
            }
        }

        @media (max-width: 760px) {
            .main .block-container {
                padding-left: 0.6rem;
                padding-right: 0.6rem;
            }

            div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {
                flex-basis: 100% !important;
                min-width: 100% !important;
            }

            .brand-card {
                min-height: 110px;
                padding: 16px 20px;
                border-radius: 16px;
            }

            .brand-title {
                font-size: 30px !important;
                letter-spacing: 4px;
            }

            .brand-subtitle {
                font-size: 12px !important;
                letter-spacing: 1.5px;
            }

            .ec-detail-grid {
                grid-template-columns: 1fr;
            }

            .ec-detail-item {
                font-size: 0.88rem;
            }

            .ec-summary-value {
                font-size: 1.1rem;
            }
        }

        /* ── Tipografia DASA para st.caption ── */
        [data-testid="stCaptionContainer"] p,
        .stCaption p {
            color: #4a6a8a !important;
            font-size: 0.82rem !important;
            font-weight: 500 !important;
            letter-spacing: 0.3px !important;
            line-height: 1.5 !important;
            opacity: 0.88 !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_risk_panel(metrics: dict[str, int | float | str | None], aging_df: pd.DataFrame) -> None:
    maiores_30 = 0
    if not aging_df.empty and ">30 dias" in aging_df["Faixa"].astype("string").tolist():
        try:
            maiores_30 = int(aging_df.loc[aging_df["Faixa"] == ">30 dias", "Quantidade"].iloc[0])
        except Exception:
            maiores_30 = 0

    alta_crit = int(metrics.get("alta_criticidade_abertos", 0))
    cancelados = int(metrics.get("cancelados", 0))

    if maiores_30 >= 15 or alta_crit >= 10:
        classe = "ec-pill ec-pill-risk"
        msg = "Risco alto: priorizar backlog antigo e alta criticidade."
    elif maiores_30 >= 5 or alta_crit >= 5:
        classe = "ec-pill ec-pill-warn"
        msg = "Atencao: existe acumulo relevante em chamados sensiveis."
    else:
        classe = "ec-pill ec-pill-ok"
        msg = "Cenario controlado para os filtros selecionados."

    st.markdown("<div class='ec-panel'>", unsafe_allow_html=True)
    st.markdown("""
        <span style='font-size:1.45rem;font-weight:800;'>Painel de Risco Operacional
            <span title='Lógica: destaca chamados com maior risco operacional para decisão rápida.' style='display:inline-block;vertical-align:middle;cursor:help;'><svg width='18' height='18' viewBox='0 0 18 18'><circle cx='9' cy='9' r='8' fill='#e6effa' stroke='#b8c8dd'/><text x='9' y='13' text-anchor='middle' font-size='11' font-weight='bold' fill='#1e4b7a'>i</text></svg></span>
        </span>
    """, unsafe_allow_html=True)
    st.markdown("<div class='ec-section-subtitle'>Sinalizacao rapida para tomada de decisao.</div>", unsafe_allow_html=True)
    st.markdown(
        (
            "<div class='ec-status-row'>"
            f"<div class='{classe}'>{msg}<div class='ec-small-muted'>Chamados >30 dias: {maiores_30}</div></div>"
            f"<div class='ec-pill ec-pill-warn'>Alta criticidade em aberto: {alta_crit}<div class='ec-small-muted'>Cancelados no periodo: {cancelados}</div></div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)


def build_recommended_actions(metrics: dict[str, int | float | str | None], aging_df: pd.DataFrame) -> list[str]:
    actions: list[str] = []

    maiores_30 = 0
    if not aging_df.empty and ">30 dias" in aging_df["Faixa"].astype("string").tolist():
        try:
            maiores_30 = int(aging_df.loc[aging_df["Faixa"] == ">30 dias", "Quantidade"].iloc[0])
        except Exception:
            maiores_30 = 0

    abertos = int(metrics.get("abertos", 0))
    alta_crit = int(metrics.get("alta_criticidade_abertos", 0))
    cancelados = int(metrics.get("cancelados", 0))
    percentual_cancelados = float(metrics.get("percentual_cancelados", 0.0))
    mttr = metrics.get("mttr")

    if alta_crit >= 10:
        actions.append("Abrir forca-tarefa para chamados de alta criticidade ainda hoje.")
    elif alta_crit >= 5:
        actions.append("Priorizar atendimento de criticidade ALTA no primeiro turno.")

    if maiores_30 >= 15:
        actions.append("Executar mutirao para backlog >30 dias com meta diaria de reducao.")
    elif maiores_30 >= 5:
        actions.append("Reservar janela semanal para reduzir chamados antigos (>30 dias).")

    if percentual_cancelados >= 15:
        actions.append("Revisar causa de cancelamentos com Operacao e padronizar criterio de abertura.")
    elif cancelados >= 1 and percentual_cancelados >= 8:
        actions.append("Monitorar taxa de cancelamento e validar qualidade das aberturas.")

    if isinstance(mttr, int) and mttr >= 20:
        actions.append("Atuar no MTTR com checklists por tipo de servico e reposicao de insumos criticos.")

    if abertos == 0:
        actions.append("Cenario sem pendencias abertas: manter rotina de prevencao e auditoria leve.")

    if not actions:
        actions.append("Operacao estavel: manter monitoramento diario e foco em prevencao.")

    return actions[:4]


def render_recommended_actions(actions: list[str]) -> None:
    st.markdown("<div class='ec-panel'>", unsafe_allow_html=True)
    st.markdown("<div class='ec-section-title'>Acoes Recomendadas</div>", unsafe_allow_html=True)
    st.markdown("<div class='ec-section-subtitle'>Prioridades sugeridas automaticamente para o contexto filtrado.</div>", unsafe_allow_html=True)
    for idx, action in enumerate(actions, start=1):
        st.markdown(f"{idx}. {action}")
    st.markdown("</div>", unsafe_allow_html=True)


def render_summary_cards(summary_items: list[tuple[str, str]]) -> None:
    blocks: list[str] = []
    for label, value in summary_items:
        blocks.append(
            (
                "<div class='ec-summary-item'>"
                f"<div class='ec-summary-label'>{escape(label)}</div>"
                f"<div class='ec-summary-value'>{escape(value)}</div>"
                "</div>"
            )
        )

    st.markdown("<div class='ec-summary-grid'>" + "".join(blocks) + "</div>", unsafe_allow_html=True)


@st.dialog("Detalhes dos Chamados")
def show_call_details_dialog(title: str, details_df: pd.DataFrame, preformatted: bool = False) -> None:
    st.markdown(
        (
            "<div class='ec-modal-panel'>"
            f"<div class='ec-section-title'>{escape(title)}</div>"
            "<div class='ec-section-subtitle'>Detalhamento com base na selecao atual dos filtros e graficos.</div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )
    if details_df.empty:
        st.info("Nenhum chamado encontrado para a selecao.")
    else:
        show_df = details_df if preformatted else build_call_detail_table(details_df)
        st.dataframe(show_df, use_container_width=True, hide_index=True)

    c1, c2 = st.columns(2)
    if c1.button("Fechar janela", key="close_details_modal"):
        st.session_state["details_modal_open"] = False
        st.rerun()
    if c2.button("Limpar selecao", key="clear_details_modal"):
        st.session_state.pop("selected_aging_faixa", None)
        st.session_state.pop("selected_pareto_falha", None)
        st.session_state.pop("selected_root_modelo", None)
        st.session_state.pop("selected_root_fabricante", None)
        st.session_state.pop("selected_root_tag", None)
        st.session_state.pop("selected_root_problema", None)
        st.session_state.pop("selected_root_origem", None)
        st.session_state.pop("selected_root_row_key", None)
        st.session_state.pop("details_modal_kind", None)
        st.session_state["details_modal_open"] = False
        st.rerun()


def render_open_call_cards(df_open: pd.DataFrame, max_cards: int, show_caption: bool = True) -> None:
    if df_open.empty:
        st.info("Nao ha chamados abertos para os filtros selecionados.")
        return

    if show_caption:
        st.caption("Visualizacao em cartoes para leitura rapida dos chamados abertos.")
    show_df = df_open.head(max_cards)

    for _, row in show_df.iterrows():
        st.markdown(
            (
                "<div class='ec-detail-card'>"
                "<div class='ec-detail-grid'>"
                f"<div class='ec-detail-item'><strong>Equipamento:</strong> {escape(str(row['Tipo de Equipamento']))}</div>"
                f"<div class='ec-detail-item'><strong>Chamado:</strong> {escape(str(row['Numero do Chamado']))}</div>"
                f"<div class='ec-detail-item'><strong>Dias Parado:</strong> {escape(str(row['Dias Parado']))}</div>"
                f"<div class='ec-detail-item'><strong>Quadro:</strong> {escape(str(row['Quadro de Trabalho']))}</div>"
                f"<div class='ec-detail-item'><strong>TAG:</strong> {escape(str(row['TAG']))}</div>"
                f"<div class='ec-detail-item'><strong>Fabricante:</strong> {escape(str(row['Fabricante']))}</div>"
                "</div>"
                "<div class='ec-detail-grid'>"
                f"<div class='ec-detail-item'><strong>Modelo:</strong> {escape(str(row['Modelo']))}</div>"
                f"<div class='ec-detail-item'><strong>Solicitante:</strong> {escape(str(row['Solicitante']))}</div>"
                "</div>"
                f"<div class='ec-detail-item'><strong>Observacao:</strong> {escape(str(row['Observacao']))}</div>"
                f"<div class='ec-detail-item'><strong>Falha:</strong> {escape(str(row['Falha']))}</div>"
                "</div>"
            ),
            unsafe_allow_html=True,
        )


def render_open_call_cards_by_quadro(df_open: pd.DataFrame, max_cards_per_quadro: int) -> None:
    if df_open.empty:
        st.info("Nao ha chamados abertos para os filtros selecionados.")
        return

    st.caption("Cartoes organizados por Quadro de Trabalho.")
    grouped = df_open.groupby("Quadro de Trabalho", dropna=False, sort=True)
    for quadro, g in grouped:
        quadro_nome = str(quadro) if pd.notna(quadro) else "-"
        st.markdown(f"#### Quadro: {quadro_nome} ({len(g)} chamados)")
        limit = min(max_cards_per_quadro, len(g))
        render_open_call_cards(g, max_cards=limit, show_caption=False)


def get_app_build_id() -> str:
        app_path = os.path.abspath(__file__)
        stat = os.stat(app_path)
        return f"{int(stat.st_mtime)}-{stat.st_size}"


def get_build_label(build_id: str) -> str:
    try:
        ts_raw, size_raw = build_id.split("-", 1)
        ts_txt = pd.to_datetime(int(ts_raw), unit="s").strftime("%d/%m %H:%M")
        return f"{ts_txt} | {size_raw}"
    except Exception:
        return build_id


def render_client_build_sync(build_id: str) -> None:
        # Evita web antiga em cache: quando build muda, forca reload com query versionada.
        st.markdown(
                f"""
                <script>
                (function() {{
                    const buildId = {build_id!r};
                    const storageKey = 'engclinica_build_id';
                    const url = new URL(window.location.href);
                    const currentBuild = localStorage.getItem(storageKey);
                    const queryBuild = url.searchParams.get('v');

                    if (currentBuild !== buildId || queryBuild !== buildId) {{
                        localStorage.setItem(storageKey, buildId);
                        url.searchParams.set('v', buildId);
                        window.location.replace(url.toString());
                    }}
                }})();
                </script>
                """,
                unsafe_allow_html=True,
        )


def build_filter_id(filter_state: tuple) -> str:
    raw = repr(filter_state).encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:10].upper()


def to_csv_bytes(df: pd.DataFrame) -> bytes:
    # UTF-8 BOM facilita abertura correta no Excel em ambiente Windows.
    return df.to_csv(index=False, sep=";", encoding="utf-8-sig").encode("utf-8-sig")


def to_excel_bytes(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Dados")
    return buf.getvalue()


def build_open_calls_by_quadro_export(df_open: pd.DataFrame) -> pd.DataFrame:
    if df_open.empty:
        return df_open

    export_df = df_open.copy()
    export_df = export_df.sort_values(
        by=["Quadro de Trabalho", "Dias Parado", "Tipo de Equipamento"],
        ascending=[True, False, True],
        kind="stable",
    )
    export_df.insert(0, "Grupo", export_df["Quadro de Trabalho"].astype("string").fillna("-"))
    return export_df


def to_executive_pdf_bytes(
    metrics: dict[str, int | float | str | None],
    aging_df: pd.DataFrame,
    pareto_df: pd.DataFrame,
    prioridade_df: pd.DataFrame,
    mtbf_df: pd.DataFrame,
    filtros_texto: str,
) -> bytes:
    if not HAS_REPORTLAB:
        raise RuntimeError("Para exportar PDF, instale a dependencia reportlab (pip install reportlab).")

    colors = rl_colors

    def add_footer(canvas, doc) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#5a6d83"))
        canvas.drawRightString(doc.pagesize[0] - 10 * mm, 6 * mm, f"Pagina {canvas.getPageNumber()}")
        canvas.restoreState()

    def fmt_int(value: int) -> str:
        return f"{int(value):,}".replace(",", ".")

    def fmt_pct(value: float) -> str:
        return f"{value:.1f}".replace(".", ",") + "%"

    styles = getSampleStyleSheet()

    cell_style = ParagraphStyle(
        "ExecCell",
        parent=styles["Normal"],
        fontSize=7,
        leading=8,
        textColor=colors.HexColor("#1b2a41"),
    )

    def clamp_text(value: object, max_len: int) -> str:
        text = str(value) if value is not None else "-"
        if len(text) <= max_len:
            return text
        return text[: max_len - 3] + "..."

    def make_pdf_table(
        df: pd.DataFrame,
        col_widths_mm: list[int],
        max_rows: int,
        font_size: int,
        clip_rules: dict[str, int] | None = None,
    ) -> object:
        if df.empty:
            t = Table([["Sem dados"]], colWidths=[sum(col_widths_mm) * mm])
            t.setStyle(
                TableStyle(
                    [
                        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cfd8e6")),
                        ("FONTSIZE", (0, 0), (-1, -1), font_size),
                    ]
                )
            )
            return t

        # Corrige valores '-' em colunas numéricas para evitar erro de conversão
        view = df.head(max_rows).copy()
        for col in view.columns:
            if pd.api.types.is_numeric_dtype(view[col]):
                view[col] = pd.to_numeric(view[col], errors="coerce").fillna(0)
        view = view.fillna("-").astype("string")
        clip_rules = clip_rules or {}
        for col_name, max_len in clip_rules.items():
            if col_name in view.columns:
                view[col_name] = view[col_name].map(lambda v: clamp_text(v, max_len))

        headers = view.columns.tolist()
        rows: list[list[object]] = []
        for row in view.values.tolist():
            rows.append([Paragraph(escape(str(v)), cell_style) for v in row])

        data: list[list[object]] = [headers] + rows
        table = Table(data, colWidths=[w * mm for w in col_widths_mm], repeatRows=1, hAlign="LEFT")
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dce8f7")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cfd8e6")),
                    ("FONTSIZE", (0, 0), (-1, -1), font_size),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 3),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                    ("TOPPADDING", (0, 0), (-1, -1), 2),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ]
            )
        )
        return table

    total = int(metrics.get("total", 0))
    fechados = int(metrics.get("fechados", 0))
    cancelados = int(metrics.get("cancelados", 0))
    percentual_cancelados = float(metrics.get("percentual_cancelados", 0.0))
    disponibilidade = max(0.0, 100.0 - percentual_cancelados)
    mttr = metrics.get("mttr")
    mttr_text = f"{fmt_int(mttr)} dias" if isinstance(mttr, int) else "N/D"
    taxa_fechamento = (fechados / total * 100.0) if total > 0 else 0.0

    kpi_rows = [
        ["Disponibilidade", fmt_pct(disponibilidade), "Chamados Criticos", fmt_int(int(metrics.get("alta_criticidade_abertos", 0)))],
        ["Tempo Medio", mttr_text, "Taxa de Fechamento", fmt_pct(taxa_fechamento)],
        ["Abertos", fmt_int(int(metrics.get("abertos", 0))), "Cancelados", f"{fmt_int(cancelados)} ({fmt_pct(percentual_cancelados)})"],
    ]

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=10 * mm,
        rightMargin=10 * mm,
        topMargin=10 * mm,
        bottomMargin=10 * mm,
        title="Relatorio Executivo - Engenharia Clinica",
    )

    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Heading1"],
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#1b2a41"),
        spaceAfter=6,
    )
    subtitle_style = ParagraphStyle(
        "ReportSubtitle",
        parent=styles["Normal"],
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#4c6179"),
    )
    section_style = ParagraphStyle(
        "SectionTitle",
        parent=styles["Heading2"],
        fontSize=12,
        leading=14,
        textColor=colors.HexColor("#1f3552"),
        spaceBefore=4,
        spaceAfter=4,
    )
    brand_box_style = ParagraphStyle(
        "PdfBrandBox",
        parent=styles["Normal"],
        alignment=1,
        fontSize=10,
        leading=12,
        textColor=colors.HexColor("#1b2a41"),
    )

    elements: list[object] = []
    brand_header = Paragraph(
        "<font color='#07155f'><b>DASA</b></font><br/><font color='#ff5a1f'><b>Engenharia Clínica - AC</b></font>",
        brand_box_style,
    )
    brand_table = Table([[brand_header]], colWidths=[110 * mm], hAlign="CENTER")
    brand_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#cfd8e6")),
                ("ROUNDEDCORNERS", [8, 8, 8, 8]),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    elements.append(brand_table)
    elements.append(Spacer(1, 3 * mm))

    elements.append(Paragraph("Relatorio Executivo de Engenharia Clinica", title_style))
    elements.append(Paragraph(f"Filtros aplicados: {filtros_texto}", subtitle_style))
    elements.append(Paragraph(f"Gerado em: {pd.Timestamp.now().strftime('%d/%m/%Y %H:%M')}", subtitle_style))
    elements.append(Spacer(1, 4 * mm))

    elements.append(Paragraph("Resumo Executivo", section_style))
    kpi_table = Table(kpi_rows, colWidths=[45 * mm, 35 * mm, 45 * mm, 35 * mm])
    kpi_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f4f8fd")),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#1b2a41")),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("GRID", (0, 0), (-1, -1), 0.7, colors.HexColor("#cfd8e6")),
                ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.HexColor("#f8fbff"), colors.white]),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    elements.append(kpi_table)
    elements.append(Spacer(1, 4 * mm))

    elements.append(Paragraph("Aging de Chamados (Top 10)", section_style))
    elements.append(make_pdf_table(aging_df, col_widths_mm=[120, 40], max_rows=10, font_size=8))
    elements.append(Spacer(1, 3 * mm))

    elements.append(Paragraph("Pareto de Falhas (Top 10)", section_style))
    elements.append(make_pdf_table(pareto_df, col_widths_mm=[205, 60], max_rows=10, font_size=8, clip_rules={"Falha": 70}))
    elements.append(Spacer(1, 3 * mm))

    elements.append(Paragraph("Radar de Risco (Top 12)", section_style))
    elements.append(
        make_pdf_table(
            prioridade_df,
            col_widths_mm=[28, 28, 30, 42, 58, 20, 40],
            max_rows=12,
            font_size=7,
            clip_rules={"Observacao": 80, "Recomendacao": 30},
        )
    )
    elements.append(Spacer(1, 3 * mm))

    elements.append(Paragraph("Fiabilidade e Historico (MTBF) - Top 10", section_style))
    elements.append(make_pdf_table(mtbf_df, col_widths_mm=[56, 40, 42, 22, 28], max_rows=10, font_size=8))

    doc.build(elements, onFirstPage=add_footer, onLaterPages=add_footer)
    return buffer.getvalue()


def to_open_calls_by_quadro_pdf_bytes(df_open: pd.DataFrame, filtros_texto: str) -> bytes:
    if not HAS_REPORTLAB:
        raise RuntimeError("Para exportar PDF, instale a dependencia reportlab (pip install reportlab).")

    colors = rl_colors

    def add_footer(canvas, doc) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#5a6d83"))
        canvas.drawRightString(doc.pagesize[0] - 10 * mm, 6 * mm, f"Pagina {canvas.getPageNumber()}")
        canvas.restoreState()

    if df_open.empty:
        raise RuntimeError("Nao ha chamados abertos para exportar no PDF por quadro.")

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=10 * mm,
        rightMargin=10 * mm,
        topMargin=10 * mm,
        bottomMargin=10 * mm,
        title="Relatorio de Abertos por Quadro",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "QuadroTitle",
        parent=styles["Heading1"],
        fontSize=16,
        leading=20,
        textColor=colors.HexColor("#1b2a41"),
        spaceAfter=4,
    )
    subtitle_style = ParagraphStyle(
        "QuadroSubtitle",
        parent=styles["Normal"],
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#4c6179"),
        spaceAfter=4,
    )
    section_style = ParagraphStyle(
        "QuadroSection",
        parent=styles["Heading3"],
        fontSize=11,
        leading=13,
        textColor=colors.HexColor("#1f3552"),
        spaceBefore=5,
        spaceAfter=3,
    )
    brand_box_style = ParagraphStyle(
        "PdfBrandBoxQuadro",
        parent=styles["Normal"],
        alignment=1,
        fontSize=10,
        leading=12,
        textColor=colors.HexColor("#1b2a41"),
    )
    cell_style = ParagraphStyle(
        "QuadroCell",
        parent=styles["Normal"],
        fontSize=7,
        leading=8,
        textColor=colors.HexColor("#1b2a41"),
    )

    def clamp_text(value: object, max_len: int) -> str:
        text = str(value) if value is not None else "-"
        if len(text) <= max_len:
            return text
        return text[: max_len - 3] + "..."

    elements: list[object] = []
    brand_header = Paragraph(
        "<font color='#07155f'><b>DASA</b></font><br/><font color='#ff5a1f'><b>Engenharia Clínica - AC</b></font>",
        brand_box_style,
    )
    brand_table = Table([[brand_header]], colWidths=[110 * mm], hAlign="CENTER")
    brand_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#cfd8e6")),
                ("ROUNDEDCORNERS", [8, 8, 8, 8]),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    elements.append(brand_table)
    elements.append(Spacer(1, 3 * mm))

    elements.append(Paragraph("Relatorio de Chamados Abertos por Quadro de Trabalho", title_style))
    elements.append(Paragraph(f"Filtros aplicados: {filtros_texto}", subtitle_style))
    elements.append(Paragraph(f"Gerado em: {pd.Timestamp.now().strftime('%d/%m/%Y %H:%M')}", subtitle_style))
    elements.append(Spacer(1, 3 * mm))

    # Extrai prefixo do quadro (ex: "NTO NE - GASPAR" de "NTO NE - GASPAR HEMATOLOGIA").
    # Padrao: CODIGO REGIAO - CIDADE (tudo antes do primeiro espaco apos a cidade).
    _pfx_re = re.compile(r'^(\S+\s+\S+\s*-\s*\S+)')

    def _quadro_prefix(val: object) -> str:
        text = str(val).strip() if pd.notna(val) else "-"
        m = _pfx_re.match(text)
        return m.group(1).strip() if m else text

    df_open = df_open.copy()
    df_open["_grupo_quadro"] = df_open["Quadro de Trabalho"].map(_quadro_prefix)
    grouped_items = list(df_open.groupby("_grupo_quadro", dropna=False, sort=True))

    for idx, (grupo, g_grupo) in enumerate(grouped_items):
        grupo_nome = str(grupo) if pd.notna(grupo) else "-"
        g_sorted = g_grupo.sort_values(by=["Quadro de Trabalho", "Dias Parado", "Tipo de Equipamento"], ascending=[True, False, True], kind="stable")
        media_dias = int(g_sorted["Dias Parado"].mean()) if not g_sorted.empty else 0

        section_header = Paragraph(f"Quadro: {grupo_nome}", section_style)
        section_sub = Paragraph(f"Total de chamados: {len(g_sorted)} | Media Dias Parado: {media_dias}", subtitle_style)

        table_df = g_sorted[["Quadro de Trabalho", "Tipo de Equipamento", "TAG", "Modelo", "Solicitante", "Observacao", "Dias Parado", "Falha"]].fillna("-").astype("string")
        table_df["Observacao"] = table_df["Observacao"].map(lambda v: clamp_text(v, 120))
        table_df["Falha"] = table_df["Falha"].map(lambda v: clamp_text(v, 80))

        headers = table_df.columns.tolist()
        body_rows: list[list[object]] = []
        for row in table_df.values.tolist():
            body_rows.append([Paragraph(escape(str(v)), cell_style) for v in row])

        table_data: list[list[object]] = [headers] + body_rows
        table = Table(
            table_data,
            repeatRows=1,
            colWidths=[40 * mm, 36 * mm, 24 * mm, 26 * mm, 28 * mm, 55 * mm, 16 * mm, 42 * mm],
        )
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dce8f7")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#1b2a41")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cfd8e6")),
                    ("FONTSIZE", (0, 0), (-1, -1), 7),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (6, 1), (6, -1), "CENTER"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 3),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                    ("TOPPADDING", (0, 0), (-1, -1), 2),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fbff")]),
                ]
            )
        )

        # Cada grupo comeca em nova folha (exceto o primeiro).
        if idx > 0:
            elements.append(PageBreak())
        elements.append(section_header)
        elements.append(section_sub)
        elements.append(table)

    doc.build(elements, onFirstPage=add_footer, onLaterPages=add_footer)
    return buffer.getvalue()


# ── E-MAIL ──────────────────────────────────────────────────────
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage

try:
    import fitz  # PyMuPDF
    HAS_FITZ = True
except ImportError:
    HAS_FITZ = False
    fitz = None


def _get_email_config() -> dict | None:
    """Retorna config de e-mail do secrets.toml, session_state ou fallback padrao."""
    # 1) Tenta secrets.toml / Streamlit Cloud secrets
    try:
        cfg = st.secrets["email"]
        return {
            "smtp_server": cfg["smtp_server"],
            "smtp_port": int(cfg["smtp_port"]),
            "sender": cfg["sender"],
            "app_password": cfg["app_password"],
        }
    except Exception:
        pass
    # 2) Fallback: credenciais inseridas via UI (session_state)
    ss = st.session_state.get("_email_cfg_manual")
    if ss and ss.get("sender") and ss.get("app_password"):
        return ss
    # 3) Fallback padrao embutido
    return {
        "smtp_server": "smtp.gmail.com",
        "smtp_port": 587,
        "sender": "eng.clinica.bot@gmail.com",
        "app_password": "bnos ciki szyh klof",
    }


def _pdf_pages_to_images(pdf_bytes: bytes, dpi: int = 150) -> list[bytes]:
    """Converte cada pagina do PDF em uma imagem PNG usando PyMuPDF."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    images: list[bytes] = []
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    for page in doc:
        pix = page.get_pixmap(matrix=mat)
        images.append(pix.tobytes("png"))
    doc.close()
    return images


def send_email_report(
    destinatarios: list[str],
    assunto: str,
    pdf_bytes: bytes,
) -> str:
    """Envia e-mail com imagens das paginas do PDF embutidas no corpo. Retorna 'ok' ou mensagem de erro."""
    cfg = _get_email_config()
    if cfg is None:
        return "Credenciais de e-mail nao configuradas em .streamlit/secrets.toml"

    try:
        page_images = _pdf_pages_to_images(pdf_bytes)
    except Exception as exc:
        return f"Erro ao converter PDF em imagens: {exc}"

    # Monta HTML com imagens inline via CID
    imgs_html = ""
    for i in range(len(page_images)):
        imgs_html += (
            f"<div style='margin-bottom:12px'>"
            f"<img src='cid:page_{i}' style='width:100%;max-width:700px;border:1px solid #ddd;border-radius:4px' />"
            f"</div>"
        )

    html_body = f"""
    <div style="font-family:Arial,sans-serif;max-width:720px;margin:0 auto">
        <div style="background:linear-gradient(135deg,#0A8B8D,#067375);padding:18px 20px;border-radius:8px 8px 0 0">
            <h1 style="color:#fff;margin:0;font-size:20px">DASA — Engenharia Clinica</h1>
            <p style="color:#d0f0f0;margin:4px 0 0;font-size:13px">Relatorio de Chamados</p>
        </div>
        <div style="padding:16px 20px;background:#f9f9f9;border:1px solid #e0e0e0;border-top:0;border-radius:0 0 8px 8px">
            {imgs_html}
            <hr style="border:0;border-top:1px solid #ddd;margin:16px 0">
            <p style="color:#999;font-size:11px;text-align:center">
                Enviado pelo Dashboard DASA Engenharia Clinica
            </p>
        </div>
    </div>
    """

    msg = MIMEMultipart("related")
    msg["From"] = cfg["sender"]
    msg["To"] = ", ".join(destinatarios)
    msg["Subject"] = assunto
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    for i, img_bytes in enumerate(page_images):
        img_part = MIMEImage(img_bytes, _subtype="png")
        img_part.add_header("Content-ID", f"<page_{i}>")
        img_part.add_header("Content-Disposition", "inline", filename=f"pagina_{i + 1}.png")
        msg.attach(img_part)

    try:
        pwd = cfg["app_password"].replace(" ", "")
        with smtplib.SMTP(cfg["smtp_server"], cfg["smtp_port"], timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(cfg["sender"], pwd)
            server.sendmail(cfg["sender"], destinatarios, msg.as_string())
        return "ok"
    except smtplib.SMTPAuthenticationError as exc:
        return f"Falha de autenticacao ({exc.smtp_code}). Verifique e-mail/senha de app."
    except smtplib.SMTPException as exc:
        return f"Erro SMTP: {exc}"
    except Exception as exc:
        return f"Erro ao enviar: {exc}"


def main() -> None:
    st.set_page_config(page_title="Engenharia Clinica", page_icon="🛠️", layout="wide")
    apply_executive_styles()
    app_build_id = get_app_build_id()
    build_label = get_build_label(app_build_id)
    render_client_build_sync(app_build_id)

    if "uploaded_file_bytes" not in st.session_state:
        st.session_state["uploaded_file_bytes"] = None
    if "uploaded_file_name" not in st.session_state:
        st.session_state["uploaded_file_name"] = ""

    st.markdown(
        """
        <div class='hero-card'>
            <div class='hero-card-content'>
                <div class='hero-card-letter'>D</div>
                <div class='hero-card-title'>DASA</div>
                <div class='hero-card-subtitle'>ENGENHARIA CLÍNICA — AC</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.session_state["uploaded_file_bytes"] is None:
        st.markdown(
            """
            <div class='upload-panel'>
                <svg width='48' height='48' viewBox='0 0 24 24' fill='none' style='margin-bottom:8px;opacity:0.7;'>
                  <path d='M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4' stroke='#0A8B8D' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'/>
                  <path d='M17 8l-5-5-5 5' stroke='#0A8B8D' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'/>
                  <path d='M12 3v12' stroke='#14A3A5' stroke-width='1.5' stroke-linecap='round'/>
                </svg>
                <h3>Enviar Planilha</h3>
                <p>Arraste ou selecione seu arquivo .xlsx / .xls para iniciar a análise</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        uploaded_file = st.file_uploader("Enviar planilha (.xlsx ou .xls)", type=["xlsx", "xls"], key="main_file_uploader")

        if uploaded_file is not None:
            uploaded_bytes = uploaded_file.getvalue()
            if not uploaded_bytes:
                st.error("Arquivo vazio ou invalido.")
                return
            st.session_state["uploaded_file_bytes"] = uploaded_bytes
            st.session_state["uploaded_file_name"] = uploaded_file.name
            st.rerun()
        st.info("Envie um arquivo .xlsx ou .xls para iniciar a analise.")
        return

    try:
        file_bytes = st.session_state["uploaded_file_bytes"]
        df = load_and_sanitize_excel(file_bytes)
    except Exception as exc:
        st.error(f"Erro ao ler o arquivo Excel: {exc}")
        return

    missing = validate_required_columns(df, REQUIRED_COLUMNS)
    if missing:
        st.warning(
            "A planilha nao contem todas as colunas obrigatorias. "
            f"Ausentes: {', '.join(missing)}"
        )
        st.caption("Colunas detectadas no arquivo: " + ", ".join(df.columns.tolist()))
        st.caption("Modelo esperado: Regiao, Quadro, Status, Tipo_Equipamento, Tag, Modelo, Fabricante, Data_Abertura, Falha, Criticidade")
        # Não bloqueia a extração, segue com o processamento

    with st.sidebar:
        # ── Cabecalho ──
        st.markdown("### :bar_chart: Painel de Filtros")
        c_info1, c_info2 = st.columns(2)
        c_info1.caption(f"v{APP_VERSION} · {build_label}")
        c_info2.caption(st.session_state.get("uploaded_file_name", "-"))
        if st.button(":arrows_counterclockwise: Trocar arquivo", use_container_width=True):
            st.session_state["uploaded_file_bytes"] = None
            st.session_state["uploaded_file_name"] = ""
            st.rerun()

        st.divider()

        # ── Opcoes disponiveis ──
        regiao_options = ["TODAS"] + sorted([x for x in df["REGIAO"].dropna().unique().tolist() if x])
        quadro_options = sorted([x for x in df["QUADRO"].dropna().unique().tolist() if x])
        tag_options = sorted([x for x in df["TAG"].dropna().astype("string").tolist() if str(x).strip()])
        criticidade_options = ["TODAS"] + sorted([x for x in df["CRITICIDADE"].dropna().unique().tolist() if x])
        tipo_servico_options = ["TODOS", "CORRETIVA", "PREVENTIVA", "CALIBRACAO"]
        has_tipo_servico = "TIPO_SERVICO" in df.columns

        data_validas = df["DATA_ABERTURA"].dropna()
        min_data = data_validas.min().date() if not data_validas.empty else None
        max_data = data_validas.max().date() if not data_validas.empty else None

        # ── Inicializacao de session_state ──
        if "regiao_filter" not in st.session_state:
            st.session_state["regiao_filter"] = "TODAS"
        if st.session_state["regiao_filter"] not in regiao_options:
            st.session_state["regiao_filter"] = "TODAS"
        if "quadro_filter" not in st.session_state:
            st.session_state["quadro_filter"] = []
        if "criticidade_filter" not in st.session_state:
            st.session_state["criticidade_filter"] = "TODAS"
        if st.session_state["criticidade_filter"] not in criticidade_options:
            st.session_state["criticidade_filter"] = "TODAS"
        if "tipo_servico_filter" not in st.session_state:
            st.session_state["tipo_servico_filter"] = "TODOS"
        if "tag_search_filter" not in st.session_state:
            st.session_state["tag_search_filter"] = ""
        if "tag_search_suggestion" not in st.session_state:
            st.session_state["tag_search_suggestion"] = ""
        if not isinstance(st.session_state["quadro_filter"], list):
            st.session_state["quadro_filter"] = []
        st.session_state["quadro_filter"] = [q for q in st.session_state["quadro_filter"] if q in quadro_options]
        if st.session_state["tipo_servico_filter"] not in tipo_servico_options:
            st.session_state["tipo_servico_filter"] = "TODOS"

        if min_data and max_data:
            if "data_inicial" not in st.session_state or st.session_state["data_inicial"] is None:
                st.session_state["data_inicial"] = min_data
            if "data_final" not in st.session_state or st.session_state["data_final"] is None:
                st.session_state["data_final"] = max_data
            if st.session_state["data_inicial"] < min_data or st.session_state["data_inicial"] > max_data:
                st.session_state["data_inicial"] = min_data
            if st.session_state["data_final"] < min_data or st.session_state["data_final"] > max_data:
                st.session_state["data_final"] = max_data

        # ── Assistente Gemini / Chatbot ──
        with st.expander(":robot_face: Assistente Gemini", expanded=False):
            st.markdown("Digite uma pergunta rápida sobre os dados de chamados e métricas.")
            user_question = st.text_area("Pergunta para o assistente", key="gemini_question", height=100)
            if st.button("Perguntar ao Assistente", key="gemini_ask"):
                if not user_question.strip():
                    st.warning("Escreva uma pergunta antes de enviar.")
                else:
                    with st.spinner("Consultando o assistente Gemini..."):
                        answer = generate_gemini_response(user_question)
                        st.markdown(f"**Resposta:** {answer}")

        # ── Secao 1: Quadro de Trabalho ──
        with st.expander(":clipboard: Quadro de Trabalho", expanded=True):
            quadro_search = st.text_input(
                "Buscar quadro",
                key="quadro_search",
                placeholder="Digite para filtrar...",
                label_visibility="collapsed",
            )
            quadro_search_norm = normalize_scalar_text(quadro_search) if quadro_search else ""
            quadro_visible = [q for q in quadro_options if quadro_search_norm in normalize_scalar_text(q)] if quadro_search_norm else quadro_options

            # Quando ha busca ativa, marca apenas os visiveis e desmarca o resto
            if quadro_search_norm:
                prev_search = st.session_state.get("_prev_quadro_search", "")
                if quadro_search_norm != prev_search:
                    for q in quadro_options:
                        st.session_state[f"chk_quadro_{q}"] = q in quadro_visible
                    st.session_state["_prev_quadro_search"] = quadro_search_norm
                    st.rerun()
            else:
                if st.session_state.get("_prev_quadro_search", ""):
                    st.session_state["_prev_quadro_search"] = ""

            bcol1, bcol2 = st.columns(2)
            if bcol1.button("Todos", key="btn_quadro_all", use_container_width=True):
                for q in quadro_visible:
                    st.session_state[f"chk_quadro_{q}"] = True
                st.rerun()
            if bcol2.button("Nenhum", key="btn_quadro_clear", use_container_width=True):
                for q in quadro_visible:
                    st.session_state[f"chk_quadro_{q}"] = False
                st.rerun()

            # Container com scroll para a lista de checkboxes
            chk_container = st.container(height=300)

            selected_quadros = []
            with chk_container:
                for q in quadro_visible:
                    key = f"chk_quadro_{q}"
                    if key not in st.session_state:
                        st.session_state[key] = not quadro_search_norm
                    if st.checkbox(q, key=key):
                        selected_quadros.append(q)
            # Quadros fora da busca: so incluir se marcados E sem busca ativa
            for q in quadro_options:
                if q not in quadro_visible:
                    key = f"chk_quadro_{q}"
                    if not quadro_search_norm and st.session_state.get(key, True):
                        selected_quadros.append(q)

            qtd_sel = len(selected_quadros)
            if qtd_sel == 0 or qtd_sel == len(quadro_options):
                st.caption(f":white_check_mark: Todos os quadros ({len(quadro_options)})")
            else:
                st.caption(f":dart: {qtd_sel} de {len(quadro_options)} quadro(s)")
            if quadro_search_norm:
                st.caption(f":mag: Filtrando: apenas {len(quadro_visible)} quadro(s) correspondente(s)")

            st.session_state["quadro_filter"] = selected_quadros if qtd_sel < len(quadro_options) else []

        # ── Secao 2: Tipo de Servico ──
        with st.expander(":wrench: Tipo de Servico", expanded=False):
            st.radio(
                "Tipo de servico",
                options=tipo_servico_options,
                horizontal=True,
                format_func=lambda x: {
                    "TODOS": "Todos",
                    "CORRETIVA": "Corretiva",
                    "PREVENTIVA": "Preventiva",
                    "CALIBRACAO": "Calibracao",
                }.get(x, x),
                key="tipo_servico_filter",
                disabled=not has_tipo_servico,
                label_visibility="collapsed",
            )
            if not has_tipo_servico:
                st.caption(":warning: Coluna TIPO_SERVICO nao encontrada.")

        # ── Secao 4: Periodo ──
        with st.expander(":calendar: Periodo", expanded=True):
            if min_data and max_data:
                di = st.date_input(
                    "De",
                    value=st.session_state["data_inicial"],
                    min_value=min_data,
                    max_value=max_data,
                    format="DD/MM/YYYY",
                    key="data_inicial",
                )
                dfim = st.date_input(
                    "Ate",
                    value=st.session_state["data_final"],
                    min_value=min_data,
                    max_value=max_data,
                    format="DD/MM/YYYY",
                    key="data_final",
                )
                if di > dfim:
                    st.session_state["data_final"] = di
                delta = (dfim - di).days
                st.caption(f":clock3: {delta} dia(s) selecionado(s)")
            else:
                st.caption(":warning: Datas indisponiveis na planilha.")

        # ── Secao 5: Pesquisa Global ──
        with st.expander(":mag: Pesquisa Global", expanded=True):
            st.caption(":earth_americas: Busca em TAG, Modelo, Fabricante, Falha, Quadro, Tipo Equipamento, Solicitante, Observacao e mais.")
            st.text_input(
                "Pesquisa",
                key="tag_search_filter",
                placeholder="Digite qualquer termo...",
                label_visibility="collapsed",
            )
            tag_query = st.session_state.get("tag_search_filter", "")
            tag_query_norm = normalize_scalar_text(tag_query)
            if tag_query_norm:
                matching_tags = [
                    t for t in tag_options if tag_query_norm in normalize_scalar_text(t)
                ]
                if matching_tags:
                    suggestion = st.selectbox(
                        "Sugestoes de TAG",
                        options=[""] + matching_tags[:30],
                        key="tag_search_suggestion",
                        format_func=lambda x: "Selecione para refinar" if x == "" else x,
                        label_visibility="collapsed",
                    )
                    if suggestion and suggestion != st.session_state.get("tag_search_filter", ""):
                        st.session_state["tag_search_filter"] = suggestion
                        st.rerun()

        st.divider()

        # ── Botao Limpar Tudo ──
        if st.button(":wastebasket: Limpar todos os filtros", use_container_width=True, type="secondary"):
            st.session_state["quadro_filter"] = []
            st.session_state["tipo_servico_filter"] = "TODOS"
            st.session_state["tag_search_filter"] = ""
            st.session_state["tag_search_suggestion"] = ""
            st.session_state["quadro_search"] = ""
            st.session_state["_prev_quadro_search"] = ""
            for q in quadro_options:
                st.session_state[f"chk_quadro_{q}"] = True
            if min_data and max_data:
                st.session_state["data_inicial"] = min_data
                st.session_state["data_final"] = max_data
            st.rerun()

        if not has_tipo_servico:
            st.session_state["tipo_servico_filter"] = "TODOS"

        quadro_filter_selected = st.session_state.get("quadro_filter", [])
        quadro_filter = quadro_options.copy() if not quadro_filter_selected else quadro_filter_selected

        tipo_servico_filter = st.session_state.get("tipo_servico_filter", "TODOS")
        tag_search_filter = st.session_state.get("tag_search_filter", "")
        data_inicial = st.session_state.get("data_inicial") if min_data and max_data else None
        data_final = st.session_state.get("data_final") if min_data and max_data else None

    filtered = apply_filters(
        df,
        "TODAS",
        quadro_filter,
        "TODAS",
        tipo_servico_filter,
        data_inicial,
        data_final,
        tag_search_filter,
    )

    # Evita manter selecoes antigas de grafico quando filtros mudam.
    filter_state = (
        tuple(sorted(quadro_filter)),
        tipo_servico_filter,
        data_inicial,
        data_final,
        normalize_scalar_text(tag_search_filter),
    )

    # Indicador global de filtros aplicados
    filtros_ativos_count = sum([
        bool(quadro_filter and len(quadro_filter) < len(quadro_options)),
        tipo_servico_filter != "TODOS",
        tag_search_filter.strip() != "",
        data_inicial != min_data if data_inicial and min_data else False,
        data_final != max_data if data_final and max_data else False,
    ])
    filter_id = build_filter_id(filter_state)
    if st.session_state.get("last_filter_state") != filter_state:
        st.session_state["last_filter_state"] = filter_state
        st.session_state.pop("selected_aging_faixa", None)
        st.session_state.pop("selected_pareto_falha", None)
        st.session_state.pop("mtbf_equipment_selector", None)
        st.session_state.pop("selected_root_modelo", None)
        st.session_state.pop("selected_root_fabricante", None)
        st.session_state.pop("selected_root_tag", None)
        st.session_state.pop("selected_root_problema", None)
        st.session_state.pop("selected_root_origem", None)
        st.session_state.pop("selected_root_row_key", None)
        st.session_state.pop("details_modal_open", None)
        st.session_state.pop("details_modal_kind", None)

    if filtros_ativos_count > 0:
        st.markdown(
            f"""
            <div style='
                display:flex; align-items:center; gap:14px; padding:10px 18px;
                background:rgba(10,139,141,0.08);
                border-left:4px solid var(--dasa-blue); border-radius:8px;
                margin-bottom:8px;
            '>
                <span style='font-size:1.6rem;'>🔍</span>
                <span style='font-weight:700;color:#0A8B8D;font-size:0.95rem;'>
                    {filtros_ativos_count} filtro(s) ativo(s)
                </span>
                <span style='color:#2d5050;font-size:0.88rem;'>
                    {len(filtered)} de {len(df)} registros
                </span>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f"""
            <div style='
                display:flex; align-items:center; gap:14px; padding:10px 18px;
                background:rgba(10,139,141,0.05); border-left:4px solid #0A8B8D;
                border-radius:8px; margin-bottom:8px;
            '>
                <span style='font-size:1.6rem;'>📊</span>
                <span style='color:#2d5050;font-size:0.9rem;'>
                    {len(df)} registros · Nenhum filtro ativo — exibindo todos os dados
                </span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    def truncate_display(value: str, max_len: int = 34) -> str:
        txt = str(value)
        if len(txt) <= max_len:
            return txt
        return txt[: max_len - 3] + "..."

    def fmt_date_display(value) -> str:
        if value is None:
            return "-"
        try:
            return pd.Timestamp(value).strftime("%d/%m/%Y")
        except Exception:
            return str(value)

    if not quadro_filter or len(quadro_filter) == len(quadro_options):
        quadro_resumo = f"TODOS ({len(quadro_options)})"
    elif len(quadro_filter) <= 2:
        quadro_resumo = ", ".join(quadro_filter)
    else:
        quadro_resumo = ", ".join(quadro_filter[:2]) + f" +{len(quadro_filter) - 2}"

    pesquisa_resumo = truncate_display(tag_search_filter, max_len=28) if tag_search_filter else "-"
    periodo_resumo = f"{fmt_date_display(data_inicial)} a {fmt_date_display(data_final)}"

    filtros_texto_display_l1 = (
        f"Quadro={quadro_resumo} | Servico={tipo_servico_filter}"
    )
    filtros_texto_display_l2 = f"Periodo={periodo_resumo} | Pesquisa={pesquisa_resumo}"

    filtros_texto_pdf = (
        f"Quadro={', '.join(quadro_filter) if quadro_filter else 'TODOS'} | "
        f"Servico={tipo_servico_filter} | "
        f"Periodo={periodo_resumo} | Pesquisa={tag_search_filter if tag_search_filter else '-'} | "
        f"ID={filter_id}"
    )

    st.caption(f"v{APP_VERSION} · Build {build_label} · Filtro {filter_id} · {filtros_texto_display_l1} · {filtros_texto_display_l2}")

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "Dashboard Gerencial",
        "Relatorio Detalhado (Abertos)",
        "Fiabilidade e Historico (MTBF)",
        "Pos-Preventiva (<=30 dias)",
        "Inteligencia Analitica",
    ])

    with tab1:
        st.subheader("Painel Executivo Operacional")

        # Caso a URL venha com ?detalhe=<chave>, abre a seção de detalhe em outra aba
        detalhe_query = st.query_params.get("detalhe")
        if detalhe_query:
            st.session_state["detalhe_categoria"] = detalhe_query
            st.session_state["open_analiseProfunda"] = True

        metrics = compute_metrics(filtered)
        aging_df = build_aging_dataframe(filtered)
        pareto_df = build_pareto_dataframe(filtered)
        prioridade_df = build_operational_radar_table(filtered)
        mtbf_report_df = build_mtbf_dataframe(filtered, top_n=10)
        actions = build_recommended_actions(metrics, aging_df)

        pdf_error = None
        pdf_bytes: bytes | None = None
        try:
            pdf_bytes = to_executive_pdf_bytes(
                metrics=metrics,
                aging_df=aging_df,
                pareto_df=pareto_df,
                prioridade_df=prioridade_df,
                mtbf_df=mtbf_report_df,
                filtros_texto=filtros_texto_pdf,
            )
        except RuntimeError as exc:
            pdf_error = str(exc)

        if pdf_bytes is not None:
            st.download_button(
                label="Baixar relatorio executivo (PDF)",
                data=pdf_bytes,
                file_name=f"relatorio_executivo_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.pdf",
                mime="application/pdf",
                use_container_width=False,
            )
        elif pdf_error:
            st.info(pdf_error)

        render_kpi_cards(metrics, aging_df)

        # Detalhamento de equipamentos removido conforme solicitação

        st.markdown("<div class='section-divider'></div>", unsafe_allow_html=True)

        col1, col2 = st.columns(2)
        selected_faixa = None
        selected_falha = None

        with col1:
            st.markdown("""
                <span style='font-size:1.45rem;font-weight:800;'>Analise de Aging de Chamados
                    <span title='Lógica: distribui chamados por faixa de dias para identificar gargalos e backlog.' style='display:inline-block;vertical-align:middle;cursor:help;'><svg width='18' height='18' viewBox='0 0 18 18'><circle cx='9' cy='9' r='8' fill='#e6effa' stroke='#b8c8dd'/><text x='9' y='13' text-anchor='middle' font-size='11' font-weight='bold' fill='#1e4b7a'>i</text></svg></span>
                </span>
            """, unsafe_allow_html=True)
            color_map = {
                "0-7 dias": "#22c55e",
                "7-14 dias": "#facc15",
                "14-30 dias": "#fb923c",
                ">30 dias": "#ef4444",
            }
            fig_aging = px.bar(
                aging_df,
                x="Faixa",
                y="Quantidade",
                color="Faixa",
                color_discrete_map=color_map,
                text_auto=True,
            )
            apply_dasa_plotly_theme(fig_aging)
            fig_aging.update_layout(
                showlegend=False,
                xaxis_title="Faixa de Dias",
                yaxis_title="Chamados",
            )
            fig_aging.update_traces(
                hovertemplate=(
                    "Faixa: %{x}<br>Quantidade: %{y}"
                    "<br><br>Funcao: distribui chamados por envelhecimento para identificar gargalos."
                    "<extra></extra>"
                )
            )
            aging_sel = st.plotly_chart(
                fig_aging,
                use_container_width=True,
                key="aging_chart",
                on_select="rerun",
                selection_mode=["points"],
            )
            selected_faixa = extract_selected_point_value(aging_sel, "x")
            if selected_faixa:
                st.session_state["selected_aging_faixa"] = selected_faixa

        with col2:
            st.markdown("""
                <span style='font-size:1.45rem;font-weight:800;'>Pareto de Custos x Falhas
                    <span title='Lógica: ordena falhas por quantidade para priorizar causas e custos mais relevantes.' style='display:inline-block;vertical-align:middle;cursor:help;'><svg width='18' height='18' viewBox='0 0 18 18'><circle cx='9' cy='9' r='8' fill='#e6effa' stroke='#b8c8dd'/><text x='9' y='13' text-anchor='middle' font-size='11' font-weight='bold' fill='#1e4b7a'>i</text></svg></span>
                </span>
            """, unsafe_allow_html=True)
            fig_pareto = px.bar(
                pareto_df,
                x="Falha",
                y="Quantidade",
                color="Falha",
                color_discrete_sequence=["#1e63a9"],
            )
            apply_dasa_plotly_theme(fig_pareto)
            fig_pareto.update_layout(
                showlegend=False,
                xaxis_title="Falha",
                yaxis_title="Ocorrencias",
            )
            fig_pareto.update_traces(
                hovertemplate=(
                    "Falha: %{x}<br>Ocorrencias: %{y}"
                    "<br><br>Funcao: mostra quais falhas concentram maior volume para orientar prioridades."
                    "<extra></extra>"
                )
            )
            pareto_sel = st.plotly_chart(
                fig_pareto,
                use_container_width=True,
                key="pareto_chart",
                on_select="rerun",
                selection_mode=["points"],
            )
            selected_falha = extract_selected_point_value(pareto_sel, "x")
            if selected_falha:
                st.session_state["selected_pareto_falha"] = selected_falha

        c_risk, c_actions = st.columns([1.2, 1])
        with c_risk:
            render_risk_panel(metrics, aging_df)
        with c_actions:
            render_recommended_actions(actions)

        st.caption("Clique no grafico para selecionar; os detalhes podem ser exibidos abaixo quando voce quiser.")

        selected_faixa = st.session_state.get("selected_aging_faixa")
        selected_falha = st.session_state.get("selected_pareto_falha")

        show_click_details = st.checkbox(
            "Mostrar detalhes por clique nos graficos",
            value=False,
            key="show_click_details_toggle",
        )

        if selected_faixa or selected_falha:
            if st.button("Limpar selecao dos graficos", use_container_width=True):
                st.session_state.pop("selected_aging_faixa", None)
                st.session_state.pop("selected_pareto_falha", None)
                st.rerun()

        if show_click_details and (selected_faixa or selected_falha):
            with st.expander("Detalhes da selecao dos graficos", expanded=True):
                if selected_faixa:
                    st.markdown(f"**Aging selecionado:** {selected_faixa}")
                    open_aging = build_open_with_aging(filtered)
                    details_aging = open_aging[open_aging["Faixa"].astype("string") == selected_faixa]
                    st.dataframe(build_call_detail_table(details_aging), use_container_width=True, hide_index=True)

                if selected_falha:
                    st.markdown(f"**Pareto selecionado:** {selected_falha}")
                    details_pareto = filtered[filtered["FALHA"].fillna("NAO INFORMADO") == selected_falha]
                    st.dataframe(build_call_detail_table(details_pareto), use_container_width=True, hide_index=True)

        st.markdown("### Tabela de Radar de Risco e Aprovacao")
        status_norm_filtered = filtered["STATUS"].map(normalize_status)
        radar_base = int((status_norm_filtered == "ABERTO").sum())
        st.caption(f"Base usada (filtros globais): {radar_base} chamado(s) aberto(s) | Exibindo Top 12")
        if prioridade_df.empty:
            st.info("Sem chamados abertos para montar o ranking de prioridade.")
        else:
            st.dataframe(prioridade_df, use_container_width=True, hide_index=True)

    with tab2:
        st.subheader("Relatorio de Chamados Abertos")
        open_df = open_calls_table(filtered)
        open_by_quadro_df = build_open_calls_by_quadro_export(open_df)

        pdf_quadro_error = None
        pdf_quadro_bytes: bytes | None = None
        try:
            pdf_quadro_bytes = to_open_calls_by_quadro_pdf_bytes(open_df, filtros_texto=filtros_texto_pdf)
        except RuntimeError as exc:
            pdf_quadro_error = str(exc)

        total_abertos = int(len(open_df))
        media_parado = int(open_df["Dias Parado"].mean()) if not open_df.empty else 0
        max_parado = int(open_df["Dias Parado"].max()) if not open_df.empty else 0

        render_summary_cards(
            [
                ("Chamados em Aberto", f"{total_abertos}"),
                ("Media de Dias Parado", f"{media_parado} dias"),
                ("Pior SLA Atual", f"{max_parado} dias"),
            ]
        )

        st.markdown("### Lista Operacional")
        st.dataframe(open_df, use_container_width=True, hide_index=True)

        d1, d2 = st.columns(2)
        d1.download_button(
            label="Baixar relatorio de abertos (CSV)",
            data=to_csv_bytes(open_df),
            file_name="relatorio_chamados_abertos.csv",
            mime="text/csv",
            use_container_width=True,
        )
        d2.download_button(
            label="Baixar relatorio por quadro de trabalho (CSV)",
            data=to_csv_bytes(open_by_quadro_df),
            file_name="relatorio_abertos_por_quadro.csv",
            mime="text/csv",
            use_container_width=True,
        )

        d3, d4 = st.columns(2)
        d3.download_button(
            label="Baixar relatorio de abertos (Excel)",
            data=to_excel_bytes(open_df),
            file_name="relatorio_chamados_abertos.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
        d4.download_button(
            label="Baixar relatorio por quadro (Excel)",
            data=to_excel_bytes(open_by_quadro_df),
            file_name="relatorio_abertos_por_quadro.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

        if pdf_quadro_bytes is not None:
            st.download_button(
                label="Baixar relatorio por quadro de trabalho (PDF)",
                data=pdf_quadro_bytes,
                file_name=f"relatorio_abertos_por_quadro_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
        elif pdf_quadro_error:
            st.info(pdf_quadro_error)

        # ── Envio de e-mail ──
        # Mapeamento automatico: padrao no nome do quadro → destinatarios
        _EMAIL_MAP = {
            "D969": "bruno.barbosa@dasa.com.br, yasmim.maria@dasa.com.br, claudemir.cruz@dasa.com.br, manfred.rees@dasa.com.br, daniele.aguiar@dasa.com.br, suzy.santos@dasa.com.br",
        }

        def _resolve_default_dest(quadros: list[str]) -> str:
            """Retorna destinatarios pre-preenchidos com base nos quadros filtrados."""
            emails: list[str] = []
            for pattern, addr in _EMAIL_MAP.items():
                if any(pattern.upper() in q.upper() for q in quadros):
                    if addr not in emails:
                        emails.append(addr)
            return ", ".join(emails)

        default_dest = _resolve_default_dest(quadro_filter)

        with st.expander("Enviar relatorio por e-mail", expanded=False, icon="📧"):
            email_cfg = _get_email_config()
            if email_cfg is None:
                st.markdown(
                    "<p style='font-size:0.88rem;color:#555'>Configure as credenciais SMTP para habilitar o envio.</p>",
                    unsafe_allow_html=True,
                )
                c1, c2 = st.columns(2)
                _smtp_sender = c1.text_input("E-mail remetente", placeholder="bot@gmail.com", key="_smtp_sender")
                _smtp_pass = c2.text_input("Senha de App", type="password", key="_smtp_pass")
                if st.button("Salvar credenciais", key="btn_save_smtp", use_container_width=True):
                    if _smtp_sender and _smtp_pass:
                        st.session_state["_email_cfg_manual"] = {
                            "smtp_server": "smtp.gmail.com",
                            "smtp_port": 587,
                            "sender": _smtp_sender.strip(),
                            "app_password": _smtp_pass.strip(),
                        }
                        st.rerun()
                    else:
                        st.warning("Preencha ambos os campos.")
            else:
                st.markdown(
                    "<p style='font-size:0.88rem;color:#555'>Envie o relatorio como imagens das "
                    "paginas do PDF diretamente no corpo do e-mail.</p>",
                    unsafe_allow_html=True,
                )
                if "email_destinatarios" not in st.session_state and default_dest:
                    st.session_state["email_destinatarios"] = default_dest
                dest_input = st.text_input(
                    "Destinatarios",
                    placeholder="email1@exemplo.com, email2@exemplo.com",
                    key="email_destinatarios",
                    help="Separe multiplos e-mails por virgula. Apague e digite novos se quiser enviar para outros.",
                )

                if st.button("Enviar e-mail", type="primary", use_container_width=True, key="btn_send_email"):
                    final_dest = dest_input.strip() if dest_input.strip() else default_dest
                    destinatarios = [d.strip() for d in final_dest.split(",") if d.strip() and "@" in d]
                    if not destinatarios:
                        st.warning("Informe ao menos um e-mail valido.")
                    elif pdf_quadro_bytes is None:
                        st.warning("PDF do relatorio nao disponivel. Verifique se ha chamados abertos.")
                    else:
                        with st.spinner("Enviando..."):
                            ts = pd.Timestamp.now().strftime("%d/%m/%Y %H:%M")
                            assunto = f"DASA Eng. Clinica — Relatorio ({ts})"
                            result = send_email_report(destinatarios, assunto, pdf_quadro_bytes)
                            if result == "ok":
                                st.success(f"E-mail enviado para {', '.join(destinatarios)}")
                            else:
                                st.error(result)

        with st.expander("Visualizacao em cartoes", expanded=False):
            modo_cartoes = st.radio(
                "Organizacao dos cartoes",
                options=["Todos os chamados", "Por quadro de trabalho"],
                horizontal=True,
                key="cards_mode",
            )

            if modo_cartoes == "Todos os chamados":
                qtd_cards = st.slider(
                    "Quantidade de cartoes para visualizar",
                    min_value=5,
                    max_value=100,
                    value=20,
                    step=5,
                    key="cards_total_limit",
                )
                render_open_call_cards(open_df, qtd_cards)
            else:
                qtd_cards_quadro = st.slider(
                    "Quantidade maxima de cartoes por quadro",
                    min_value=3,
                    max_value=50,
                    value=10,
                    step=1,
                    key="cards_quadro_limit",
                )
                render_open_call_cards_by_quadro(open_df, qtd_cards_quadro)

    with tab3:
        render_mtbf_section(filtered)

    with tab4:
        st.subheader("Falhas Corretivas em ate 30 dias apos Preventiva")
        st.caption(
            "Analise por TAG: identifica equipamentos que tiveram chamado corretivo nas faixas 0-2, 3-10, 11-20 e 21-30 dias apos preventiva."
        )

        if "TIPO_SERVICO" not in filtered.columns:
            st.info("A coluna TIPO_SERVICO nao foi encontrada na planilha atual.")
        else:
            p2c_df = build_preventiva_corretiva_intervalo(filtered, max_interval_days=30)
            if p2c_df.empty:
                st.success("Nenhum equipamento com corretiva em ate 30 dias apos preventiva nos filtros atuais.")
            else:
                faixa_order = ["0-2 dias", "3-10 dias", "11-20 dias", "21-30 dias"]
                eq_count = p2c_df["TAG"].nunique()
                st.caption(f"Casos encontrados: {len(p2c_df)} | Equipamentos impactados: {eq_count}")

                faixa_counts = (
                    p2c_df["Faixa de Dias"]
                    .value_counts()
                    .reindex(faixa_order, fill_value=0)
                    .rename_axis("Faixa")
                    .reset_index(name="Quantidade")
                )
                f1, f2, f3, f4 = st.columns(4)
                f1.metric("0-2 dias", int(faixa_counts.loc[faixa_counts["Faixa"] == "0-2 dias", "Quantidade"].iloc[0]))
                f2.metric("3-10 dias", int(faixa_counts.loc[faixa_counts["Faixa"] == "3-10 dias", "Quantidade"].iloc[0]))
                f3.metric("11-20 dias", int(faixa_counts.loc[faixa_counts["Faixa"] == "11-20 dias", "Quantidade"].iloc[0]))
                f4.metric("21-30 dias", int(faixa_counts.loc[faixa_counts["Faixa"] == "21-30 dias", "Quantidade"].iloc[0]))

                fig_faixas = px.bar(
                    faixa_counts,
                    x="Faixa",
                    y="Quantidade",
                    text_auto=True,
                    color="Faixa",
                    color_discrete_map={
                        "0-2 dias": "#22c55e",
                        "3-10 dias": "#facc15",
                        "11-20 dias": "#fb923c",
                        "21-30 dias": "#ef4444",
                    },
                )
                apply_dasa_plotly_theme(fig_faixas)
                fig_faixas.update_layout(
                    showlegend=False,
                    xaxis_title="Faixa de dias",
                    yaxis_title="Quantidade de falhas",
                )
                fig_faixas.update_traces(
                    hovertemplate=(
                        "Faixa: %{x}<br>Quantidade: %{y}"
                        "<br><br>Funcao: compara reincidencia de corretivas por janela apos preventiva."
                        "<extra></extra>"
                    )
                )
                faixa_sel = st.plotly_chart(
                    fig_faixas,
                    use_container_width=True,
                    key="p2c_faixas_chart",
                    on_select="rerun",
                    selection_mode=["points"],
                )
                selected_p2c_faixa = extract_selected_point_value(faixa_sel, "x")
                if selected_p2c_faixa in faixa_order:
                    st.session_state["selected_p2c_faixa"] = selected_p2c_faixa

                faixa_filter = st.selectbox(
                    "Filtrar por faixa",
                    options=["TODAS"] + faixa_order,
                    key="p2c_faixa_filter",
                )
                if faixa_filter == "TODAS":
                    p2c_view = p2c_df.copy()
                else:
                    p2c_view = p2c_df[p2c_df["Faixa de Dias"] == faixa_filter].copy()

                ranking_df = (
                    p2c_view.groupby("TAG", as_index=False)
                    .agg(
                        Modelo=("Modelo", lambda s: next((str(v) for v in s if pd.notna(v) and str(v).strip()), "-")),
                        Fabricante=("Fabricante", lambda s: next((str(v) for v in s if pd.notna(v) and str(v).strip()), "-")),
                        Casos=("TAG", "size"),
                        Intervalo_Medio_Dias=("Intervalo (dias)", "mean"),
                        Menor_Intervalo_Dias=("Intervalo (dias)", "min"),
                    )
                    .sort_values(by=["Casos", "Intervalo_Medio_Dias"], ascending=[False, True], kind="stable")
                )

                st.markdown("### Ranking de TAGs com recorrencia pos-preventiva")
                top_rank = ranking_df.head(15).sort_values(by=["Casos", "TAG"], ascending=[True, True], kind="stable")
                fig_rank = px.bar(
                    top_rank,
                    x="Casos",
                    y="TAG",
                    orientation="h",
                    color="Intervalo_Medio_Dias",
                    color_continuous_scale="Blues",
                    text_auto=True,
                    custom_data=["Modelo", "Fabricante"],
                    labels={
                        "TAG": "TAG",
                        "Casos": "Quantidade de casos",
                        "Intervalo_Medio_Dias": "Intervalo medio (dias)",
                    },
                )
                apply_dasa_plotly_theme(fig_rank)
                fig_rank.update_layout(
                    xaxis_title="Quantidade de casos",
                    yaxis_title="TAG",
                )
                fig_rank.update_traces(
                    hovertemplate=(
                        "TAG: %{y}<br>Modelo: %{customdata[0]}<br>Fabricante: %{customdata[1]}<br>Casos: %{x}<br>Intervalo medio: %{marker.color:.2f} dias"
                        "<br><br>Funcao: ranqueia equipamentos com maior reincidencia pos-preventiva."
                        "<extra></extra>"
                    )
                )
                rank_sel = st.plotly_chart(
                    fig_rank,
                    use_container_width=True,
                    key="p2c_ranking_chart",
                    on_select="rerun",
                    selection_mode=["points"],
                )
                selected_p2c_tag = extract_selected_point_value(rank_sel, "y")
                if selected_p2c_tag:
                    st.session_state["selected_p2c_tag"] = selected_p2c_tag

                clicked_faixa = st.session_state.get("selected_p2c_faixa")
                clicked_tag = st.session_state.get("selected_p2c_tag")
                if clicked_faixa or clicked_tag:
                    click_details = p2c_df.copy()
                    if clicked_faixa:
                        click_details = click_details[click_details["Faixa de Dias"] == clicked_faixa]
                    if clicked_tag:
                        click_details = click_details[click_details["TAG"].astype("string") == str(clicked_tag)]

                    # Ordena os cartoes da falha mais recente para a mais antiga.
                    click_details = click_details.copy()
                    click_details["_DataCorretivaSort"] = pd.to_datetime(
                        click_details["Data Corretiva"],
                        format="%d/%m/%Y %H:%M",
                        errors="coerce",
                        dayfirst=True,
                    )
                    click_details = click_details.sort_values(
                        by="_DataCorretivaSort",
                        ascending=False,
                        kind="stable",
                    )
                    click_details = click_details.drop(columns=["_DataCorretivaSort"], errors="ignore")

                    st.markdown("### Cartoes de chamados por clique nas colunas")
                    filtros_ativos = []
                    if clicked_faixa:
                        filtros_ativos.append(f"Faixa: {clicked_faixa}")
                    if clicked_tag:
                        filtros_ativos.append(f"TAG: {clicked_tag}")
                    st.caption(" | ".join(filtros_ativos))

                    if click_details.empty:
                        st.info("Nenhum chamado encontrado para a selecao por clique.")
                    else:
                        st.caption("Ordenacao: Data de Abertura da Corretiva (mais nova -> mais antiga).")
                        for _, row in click_details.head(50).iterrows():
                            st.markdown(
                                (
                                    "<div class='ec-detail-card'>"
                                    "<div class='ec-detail-grid'>"
                                    "<div class='ec-detail-item'><strong>Tipo de Servico:</strong> CORRETIVA</div>"
                                    f"<div class='ec-detail-item'><strong>Data de Abertura:</strong> {escape(str(row['Data Corretiva']))}</div>"
                                    f"<div class='ec-detail-item'><strong>Modelo:</strong> {escape(str(row['Modelo']))}</div>"
                                    f"<div class='ec-detail-item'><strong>TAG:</strong> {escape(str(row['TAG']))}</div>"
                                    f"<div class='ec-detail-item'><strong>Fabricante:</strong> {escape(str(row['Fabricante']))}</div>"
                                    "</div>"
                                    f"<div class='ec-detail-item'><strong>Falha Corretiva:</strong> {escape(str(row['Falha Corretiva']))}</div>"
                                    f"<div class='ec-detail-note'>Quadro: {escape(str(row['Quadro']))} | Data Preventiva: {escape(str(row['Data Preventiva']))} | Intervalo: {escape(str(row['Intervalo (dias)']))} dias</div>"
                                    "</div>"
                                ),
                                unsafe_allow_html=True,
                            )

                    if st.button("Limpar selecao por clique", key="clear_p2c_click_selection"):
                        st.session_state.pop("selected_p2c_faixa", None)
                        st.session_state.pop("selected_p2c_tag", None)
                        st.rerun()

                st.dataframe(p2c_view, use_container_width=True, hide_index=True)

    with tab5:
        st.subheader("Inteligencia Analitica — Diagnostico Automatico")
        st.markdown(
            "<div class='ec-section-subtitle'>"
            "Analise inteligente baseada nos dados filtrados. Sem dependencia de APIs externas."
            "</div>",
            unsafe_allow_html=True,
        )

        diag = gerar_diagnostico_inteligente(filtered)

        # ── Nota Geral ──
        st.markdown(
            f"<div style='text-align:center;padding:1.5rem 0;'>"
            f"<div style='font-size:1.1rem;color:#64748b;font-weight:600;'>NOTA OPERACIONAL</div>"
            f"<div style='font-size:4rem;font-weight:900;color:{diag['nota_cor']};line-height:1.1;'>{diag['nota']:.0f}</div>"
            f"<div style='font-size:1.3rem;font-weight:700;color:{diag['nota_cor']};'>{diag['nota_label']}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

        # ── Resumo Executivo ──
        st.markdown("### Resumo Executivo")
        st.markdown(diag["resumo_executivo"])

        st.markdown("---")

        # ── Quadros Sobrecarregados ──
        st.markdown("### Quadros Mais Sobrecarregados")
        if diag["quadros_ranking"]:
            qr_df = pd.DataFrame(diag["quadros_ranking"])
            qr_df.columns = ["Quadro", "Abertos", "Media Dias", "Alta Crit."]
            st.dataframe(qr_df, use_container_width=True, hide_index=True)
        else:
            st.info("Nenhum quadro com chamados abertos.")

        st.markdown("---")

        # ── Campo de Perguntas ──
        st.markdown("---")
        st.markdown("### Pergunte sobre seus dados")
        st.markdown(
            "<div class='ec-section-subtitle'>"
            "Digite uma pergunta sobre a operacao. Exemplos: "
            "<em>\"qual a situacao geral?\", \"quais falhas mais recorrentes?\", \"como esta o backlog?\", "
            "\"quais equipamentos mais demandam?\", \"qual o tempo de resolucao?\"</em>"
            "</div>",
            unsafe_allow_html=True,
        )

        if "ia_historico" not in st.session_state:
            st.session_state["ia_historico"] = []

        # Sugestões rápidas
        sug_cols = st.columns(5)
        sugestoes = [
            ("Situacao geral", "Qual a situacao geral da operacao?"),
            ("Backlog", "Como esta o backlog de chamados antigos?"),
            ("Criticidade", "Quantos chamados criticos estao abertos?"),
            ("Falhas", "Quais as falhas mais recorrentes?"),
            ("Recomendacoes", "O que devo priorizar agora?"),
        ]
        for col_sug, (label_sug, pergunta_sug) in zip(sug_cols, sugestoes):
            if col_sug.button(label_sug, key=f"ia_sug_{label_sug}"):
                st.session_state["ia_pending_q"] = pergunta_sug

        # Historico
        for msg in st.session_state["ia_historico"]:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        # Input
        pending_q = st.session_state.pop("ia_pending_q", None)
        user_q = st.chat_input("Pergunte algo sobre seus dados...", key="ia_chat_input")
        pergunta = pending_q or user_q

        if pergunta:
            st.session_state["ia_historico"].append({"role": "user", "content": pergunta})
            with st.chat_message("user"):
                st.markdown(pergunta)

            with st.chat_message("assistant"):
                resposta = _ia_responder_pergunta(pergunta, diag)
                st.markdown(resposta)
                st.session_state["ia_historico"].append({"role": "assistant", "content": resposta})

        if st.session_state.get("ia_historico"):
            if st.button("Limpar conversa", key="ia_limpar_hist"):
                st.session_state["ia_historico"] = []
                st.rerun()

    if st.session_state.get("details_modal_open") and st.session_state.get("details_modal_kind") == "root_cause":
        modelo = st.session_state.get("selected_root_modelo")
        fabricante = st.session_state.get("selected_root_fabricante")
        tag = st.session_state.get("selected_root_tag")
        problema = st.session_state.get("selected_root_problema")
        origem = st.session_state.get("selected_root_origem")

        if all([modelo, fabricante, tag, problema, origem]):
            details_root = build_root_cause_details_dataframe(
                filtered,
                modelo=str(modelo),
                fabricante=str(fabricante),
                tag=str(tag),
                problema_relatado=str(problema),
                origem_problema=str(origem),
            )
            show_call_details_dialog(
                title=f"Detalhes do erro: {problema} | Origem: {origem}",
                details_df=build_root_cause_modal_table(details_root),
                preformatted=True,
            )

    # ── Footer profissional ──
    st.markdown(
        """
        <div class='section-divider'></div>
        <div class='app-footer'>
            <p class='app-footer-text'>
                <span class='app-footer-brand'>DASA</span>
                <span class='app-footer-accent'> · </span>
                Engenharia Clínica — Painel Analítico
                <span class='app-footer-accent'> · </span>
                Desenvolvido com Streamlit
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()

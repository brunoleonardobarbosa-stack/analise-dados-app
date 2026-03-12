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
    "CRITICIDADE"]

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


# â”€â”€ Tema DASA unificado para Plotly â”€â”€
DASA_PLOTLY_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(240,245,250,0.35)",
    font=dict(family="'Segoe UI', system-ui, -apple-system, sans-serif", color="#1a3c5e", size=13),
    margin=dict(l=8, r=8, t=10, b=8),
    xaxis=dict(gridcolor="rgba(0,59,113,0.08)", zerolinecolor="rgba(0,59,113,0.12)"),
    yaxis=dict(gridcolor="rgba(0,59,113,0.08)", zerolinecolor="rgba(0,59,113,0.12)"),
    colorway=["#003B71", "#FF6A13", "#1e63a9", "#e85d04", "#4a90c4", "#f4845f", "#7fb3d8", "#ff9a5c"],
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

    # Corrige todos os padrÃµes para Centro-oeste, Nordeste e Sul
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
            "NUMERO_CHAMADO", "ORIGEM_PROBLEMA", "CRITICIDADE"]
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


@st.cache_data(show_spinner=False)
def compute_metrics(df: pd.DataFrame) -> dict[str, int | float | str | None]:
    status_norm = df["STATUS"].map(normalize_status)

    abertos = int((status_norm == "ABERTO").sum())
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

    return {
        "abertos": abertos,
        "fechados": fechados,
        "total": total,
        "cancelados": cancelados,
        "percentual_cancelados": percentual_cancelados,
        "alta_criticidade_abertos": alta_criticidade_abertos,
        "mttr": mttr,
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
            "Dias_Parado"]
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
                "MTBF (dias)"]
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
                "MTBF (dias)"]
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
        "Criticidade"]

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
            <span title='LÃ³gica: calcula mÃ©dia dos intervalos entre falhas para cada equipamento (MTBF).' style='display:inline-block;vertical-align:middle;cursor:help;'><svg width='18' height='18' viewBox='0 0 18 18'><circle cx='9' cy='9' r='8' fill='#e6effa' stroke='#b8c8dd'/><text x='9' y='13' text-anchor='middle' font-size='11' font-weight='bold' fill='#1e4b7a'>i</text></svg></span>
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
                <span title='LÃ³gica: ordena modelos por quantidade de falhas para priorizar manutenÃ§Ã£o.' style='display:inline-block;vertical-align:middle;cursor:help;'><svg width='16' height='16' viewBox='0 0 18 18'><circle cx='9' cy='9' r='8' fill='#e6effa' stroke='#b8c8dd'/><text x='9' y='13' text-anchor='middle' font-size='10' font-weight='bold' fill='#1e4b7a'>i</text></svg></span>
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
                <span title='LÃ³gica: agrupa falhas por origem para identificar causas recorrentes.' style='display:inline-block;vertical-align:middle;cursor:help;'><svg width='16' height='16' viewBox='0 0 18 18'><circle cx='9' cy='9' r='8' fill='#e6effa' stroke='#b8c8dd'/><text x='9' y='13' text-anchor='middle' font-size='10' font-weight='bold' fill='#1e4b7a'>i</text></svg></span>
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
            "FALHA"]
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


def closed_calls_table(df: pd.DataFrame) -> pd.DataFrame:
    """Retorna DataFrame formatado dos chamados FECHADOS com tempo de resolucao."""
    status_norm = df["STATUS"].map(normalize_status)
    fechados = df[status_norm == "FECHADO"].copy()

    if fechados.empty:
        return pd.DataFrame()

    # Tempo de resolucao em dias
    if "DATA_FECHAMENTO" in fechados.columns:
        duracao = (fechados["DATA_FECHAMENTO"] - fechados["DATA_ABERTURA"]).dt.days
        fechados["DIAS_RESOLUCAO"] = pd.to_numeric(duracao, errors="coerce").fillna(-1).astype(int)
    else:
        fechados["DIAS_RESOLUCAO"] = -1

    ticket_number_col = resolve_ticket_number_column(fechados)
    fechados["NUMERO_CHAMADO_OUT"] = (
        fechados[ticket_number_col].astype("string").fillna("-") if ticket_number_col else "-"
    )

    requester_col = resolve_requester_column(fechados)
    fechados["SOLICITANTE_OUT"] = (
        fechados[requester_col].astype("string").fillna("-") if requester_col else "-"
    )

    def _fmt_date(s):
        if s.empty:
            return s
        return pd.to_datetime(s, errors="coerce").dt.strftime("%d/%m/%Y").fillna("-")

    cols_out = ["QUADRO", "NUMERO_CHAMADO_OUT", "TIPO_EQUIPAMENTO", "TAG", "MODELO", "FABRICANTE"]
    rename_map = {
        "QUADRO": "Quadro", "NUMERO_CHAMADO_OUT": "Chamado",
        "TIPO_EQUIPAMENTO": "Tipo Equipamento", "TAG": "TAG",
        "MODELO": "Modelo", "FABRICANTE": "Fabricante",
    }

    if "DATA_ABERTURA" in fechados.columns:
        fechados["ABERTURA_FMT"] = _fmt_date(fechados["DATA_ABERTURA"])
        cols_out.append("ABERTURA_FMT")
        rename_map["ABERTURA_FMT"] = "Abertura"

    if "DATA_FECHAMENTO" in fechados.columns:
        fechados["FECHAMENTO_FMT"] = _fmt_date(fechados["DATA_FECHAMENTO"])
        cols_out.append("FECHAMENTO_FMT")
        rename_map["FECHAMENTO_FMT"] = "Fechamento"

    cols_out += ["DIAS_RESOLUCAO", "SOLICITANTE_OUT", "FALHA"]
    rename_map["DIAS_RESOLUCAO"] = "Dias p/ Resolver"
    rename_map["SOLICITANTE_OUT"] = "Solicitante"
    rename_map["FALHA"] = "Falha"

    available = [c for c in cols_out if c in fechados.columns]
    result = fechados[available].rename(columns=rename_map)
    return result.sort_values(by="Dias p/ Resolver", ascending=False, kind="stable")



def render_kpi_cards(metrics: dict[str, int | float | str | None], aging_df: pd.DataFrame) -> None:
    st.markdown(
        """
        <style>
        .kpi-grid-card {
            border: 1px solid var(--ec-border);
            border-radius: 16px;
            padding: 14px 16px;
            background: linear-gradient(180deg, #ffffff 0%, var(--dasa-blue-pale) 100%);
            box-shadow: 0 4px 16px rgba(0, 59, 113, 0.08);
            position: relative;
            overflow: hidden;
            min-height: 100px;
            animation: fadeInUp 0.5s ease-out;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .kpi-grid-card:hover {
            transform: translateY(-4px) scale(1.01);
            box-shadow: 0 12px 32px rgba(0, 59, 113, 0.16);
        }
        .kpi-grid-card::before {
            content: "";
            position: absolute;
            left: 0;
            top: 0;
            height: 100%;
            width: 4px;
            background: linear-gradient(180deg, var(--dasa-blue) 0%, var(--dasa-orange) 100%);
        }
        .kpi-grid-card::after {
            content: "";
            position: absolute;
            right: 10px;
            bottom: 10px;
            width: 40px;
            height: 40px;
            border-radius: 50%;
            background: linear-gradient(135deg, rgba(0,59,113,0.04), rgba(255,106,19,0.06));
        }
        .kpi-grid-title {
            font-size: 0.82rem;
            color: #2d4a66;
            margin-bottom: 5px;
            font-weight: 800;
            letter-spacing: 0.3px;
            display: flex;
            align-items: center;
            gap: 6px;
        }
        .kpi-info-dot {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 18px;
            height: 18px;
            border-radius: 50%;
            background: linear-gradient(135deg, var(--dasa-blue-pale), #d4e4f7);
            border: 1.5px solid var(--dasa-blue-light);
            color: var(--dasa-blue);
            font-size: 11px;
            font-weight: 900;
            cursor: help;
            user-select: none;
            transition: all 0.3s ease;
        }
        .kpi-info-dot:hover {
            background: var(--dasa-blue);
            color: #ffffff;
            border-color: var(--dasa-blue);
            transform: scale(1.2);
            box-shadow: 0 2px 8px rgba(0,59,113,0.25);
        }
        .kpi-grid-value {
            font-size: 1.55rem;
            color: var(--dasa-blue);
            font-weight: 900;
            line-height: 1.1;
            text-shadow: 0 1px 2px rgba(0,59,113,0.1);
        }
        .kpi-grid-trend {
            margin-top: 6px;
            font-size: 0.78rem;
            color: #d45500;
            font-weight: 800;
        }
        .kpi-responsive-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
            gap: 12px;
            align-items: stretch;
            margin: 4px 0 14px 0;
        }
        .dashboard-block {
            background: rgba(255,255,255,0.85);
            backdrop-filter: blur(8px);
            -webkit-backdrop-filter: blur(8px);
            border: 1px solid var(--ec-border);
            border-radius: 14px;
            padding: 10px 12px;
            box-shadow: 0 4px 12px rgba(0, 59, 113, 0.06);
            transition: all 0.3s ease;
        }
        .dashboard-block:hover {
            box-shadow: 0 8px 24px rgba(0, 59, 113, 0.1);
        }

        .upload-panel {
            background: linear-gradient(135deg, #ffffff 0%, var(--dasa-blue-pale) 50%, var(--dasa-orange-pale) 100%);
            border: 2px dashed var(--dasa-blue-light);
            border-radius: 16px;
            padding: 20px 20px;
            box-shadow: 0 8px 24px rgba(0, 59, 113, 0.08);
            margin-bottom: 8px;
            animation: fadeInUp 0.6s ease-out;
            transition: all 0.3s ease;
            text-align: center;
        }
        .upload-panel:hover {
            border-color: var(--dasa-orange);
            box-shadow: 0 8px 28px rgba(255, 106, 19, 0.12);
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
            "Disponibilidade Global",
            f"{format_percent_pt_br(max(0.0, 100.0 - percentual_cancelados))}%",
            "Baseado em cancelamentos",
            "Funcao: mede a estabilidade operacional usando o percentual de chamados nao cancelados.\nLÃ³gica: 100% - percentual_cancelados = 100% - (cancelados/total)*100",
        ),
        (
            "Chamados Criticos em Aberto",
            format_int_pt_br(int(metrics["alta_criticidade_abertos"])),
            "Criticidade ALTA ativa",
            "Funcao: destaca urgencias em aberto para priorizacao imediata.\nLÃ³gica: quantidade de chamados com STATUS=ABERTO e CRITICIDADE=ALTA",
        ),
        (
            "Tempo Medio de Atendimento",
            mttr_text,
            "Meta operacional: <= 15 dias",
            "Funcao: acompanha o tempo medio para concluir chamados e controlar eficiencia.\nLÃ³gica: mÃ©dia dos dias entre DATA_ABERTURA e DATA_FECHAMENTO para chamados fechados",
        ),
        (
            "Volume de Chamados",
            f"{format_int_pt_br(int(metrics['abertos']))} / {format_int_pt_br(fechados)}",
            "Abertos / Fechados",
            "Funcao: compara carga atual (abertos) com capacidade de resolucao (fechados).\nLÃ³gica: abertos = STATUS=ABERTO, fechados = STATUS=FECHADO",
        ),
        (
            "Backlog >30 dias",
            format_int_pt_br(backlog_30),
            "Fila com maior risco",
            "Funcao: mostra chamados envelhecidos com maior risco de impacto operacional.\nLÃ³gica: quantidade de chamados abertos com Faixa '>30 dias'",
        ),
        (
            "Taxa de Fechamento",
            f"{format_percent_pt_br(taxa_fechamento)}%",
            "Fechados sobre total",
            "Funcao: indica efetividade do time na conversao de chamados em resolucoes.\nLÃ³gica: (fechados/total)*100",
        )]

    card_blocks: list[str] = []
    for title, value, trend, tip in cards:
        tooltip = escape(tip)
        card_blocks.append(
            f"<div class='kpi-grid-card' title='{tooltip}'>"
            f"<div class='kpi-grid-title'>{title}<span class='kpi-info-dot' title='{tooltip}'>i</span></div>"
            f"<div class='kpi-grid-value'>{value}</div>"
            f"<div class='kpi-grid-trend'>{trend}</div>"
            f"</div>"
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
        /* â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
           TEMA DASA â€” Azul Corporativo + Laranja Energia
           â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â• */

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

        :root {
            --dasa-blue: #003B71;
            --dasa-blue-light: #1565C0;
            --dasa-blue-pale: #e8f0fe;
            --dasa-orange: #FF6A13;
            --dasa-orange-light: #FF8F4C;
            --dasa-orange-pale: #fff3eb;
            --ec-bg: #f0f4f8;
            --ec-bg-2: #e8edf5;
            --ec-panel: #ffffff;
            --ec-panel-soft: #f8fbff;
            --ec-border: #d0dae8;
            --ec-title: #051225;
            --ec-muted: #2d4a66;
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
            background:
                radial-gradient(900px 300px at 5% 0%, rgba(0,59,113,0.07) 0%, transparent 60%),
                radial-gradient(700px 250px at 95% 0%, rgba(255,106,19,0.06) 0%, transparent 50%),
                linear-gradient(180deg, var(--ec-bg) 0%, var(--ec-bg-2) 100%);
            margin-top: 0;
        }

        /* â”€â”€ Scrollbar personalizada â”€â”€ */
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
            background: var(--dasa-orange);
        }

        .main .block-container {
            padding-top: 0.8rem;
            padding-bottom: 1.4rem;
            animation: fadeIn 0.6s ease-out;
        }

        /* â”€â”€ PainÃ©is (glassmorphism) â”€â”€ */
        .ec-panel {
            background: rgba(255, 255, 255, 0.82);
            backdrop-filter: blur(12px) saturate(1.6);
            -webkit-backdrop-filter: blur(12px) saturate(1.6);
            border: 1px solid rgba(208, 218, 232, 0.65);
            border-radius: 16px;
            padding: 14px 16px;
            box-shadow:
                0 8px 32px rgba(0, 59, 113, 0.08),
                inset 0 1px 0 rgba(255,255,255,0.7);
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
            background: linear-gradient(90deg, var(--dasa-blue) 0%, var(--dasa-orange) 100%);
        }

        .ec-section-title {
            color: var(--dasa-blue);
            font-weight: 900;
            font-size: 1.1rem;
            margin-bottom: 6px;
            letter-spacing: 0.3px;
            text-shadow: 0 1px 2px rgba(0,59,113,0.08);
        }

        .ec-section-subtitle {
            color: #3a5a78;
            font-size: 0.88rem;
            font-weight: 600;
            margin-bottom: 0;
        }

        /* â”€â”€ Status pills â”€â”€ */
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

        /* â”€â”€ Detail cards â”€â”€ */
        .ec-detail-card {
            background: linear-gradient(135deg, #ffffff 0%, #f8fbff 100%);
            border: 1px solid var(--ec-border);
            border-left: 4px solid var(--dasa-blue);
            border-radius: 14px;
            padding: 12px 14px;
            box-shadow: 0 4px 14px rgba(0, 59, 113, 0.06);
            margin-bottom: 8px;
            animation: fadeInUp 0.4s ease-out;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .ec-detail-card:hover {
            transform: translateY(-3px) scale(1.005);
            box-shadow: 0 12px 28px rgba(0, 59, 113, 0.14);
            border-left-color: var(--dasa-orange);
        }

        .ec-detail-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 8px;
            margin: 6px 0;
        }

        .ec-detail-item {
            background: var(--dasa-blue-pale);
            border: 1px solid #c8d8ec;
            border-radius: 10px;
            padding: 8px 10px;
            font-size: 0.92rem;
            color: #0d1f3c;
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

        /* â”€â”€ Summary grid â”€â”€ */
        .ec-summary-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 10px;
            margin: 8px 0 12px 0;
        }

        .ec-summary-item {
            background: linear-gradient(180deg, #ffffff 0%, var(--dasa-blue-pale) 100%);
            border: 1px solid var(--ec-border);
            border-radius: 12px;
            padding: 10px 12px;
            box-shadow: 0 4px 10px rgba(0, 59, 113, 0.06);
            animation: fadeInUp 0.5s ease-out;
            transition: all 0.3s ease;
            position: relative;
            overflow: hidden;
        }
        .ec-summary-item::after {
            content: "";
            position: absolute;
            bottom: 0;
            left: 0;
            right: 0;
            height: 2px;
            background: linear-gradient(90deg, var(--dasa-blue) 0%, var(--dasa-orange) 100%);
            transform: scaleX(0);
            transition: transform 0.3s ease;
        }
        .ec-summary-item:hover::after {
            transform: scaleX(1);
        }
        .ec-summary-item:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 18px rgba(0, 59, 113, 0.12);
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
            background: rgba(248, 251, 255, 0.9);
            backdrop-filter: blur(8px);
            -webkit-backdrop-filter: blur(8px);
            border: 1px solid var(--ec-border);
            border-radius: 12px;
            padding: 10px 12px;
            margin-bottom: 8px;
        }

        /* â”€â”€ SIDEBAR PREMIUM â”€â”€ */
        section[data-testid="stSidebar"] {
            background: linear-gradient(180deg, #00274d 0%, var(--dasa-blue) 30%, #002952 100%);
            border-right: none;
            box-shadow: 4px 0 24px rgba(0, 59, 113, 0.25);
            position: relative;
        }
        section[data-testid="stSidebar"]::after {
            content: "";
            position: absolute;
            top: 0;
            right: 0;
            width: 3px;
            height: 100%;
            background: linear-gradient(180deg, var(--dasa-orange), var(--dasa-blue-light), var(--dasa-orange));
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
            border-radius: 14px;
            background: rgba(255,255,255,0.06);
            backdrop-filter: blur(8px);
            -webkit-backdrop-filter: blur(8px);
            transition: all 0.3s ease;
        }
        section[data-testid="stSidebar"] div[data-testid="stExpander"] details:hover {
            background: rgba(255,255,255,0.10);
            border-color: rgba(255,106,19,0.3);
        }
        section[data-testid="stSidebar"] div[data-testid="stExpander"] details[open] {
            border-color: rgba(255,106,19,0.4);
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
            color: #0a1e3d;
            border-radius: 10px;
            transition: all 0.3s ease;
        }
        section[data-testid="stSidebar"] .stTextInput input:focus {
            border-color: var(--dasa-orange);
            box-shadow: 0 0 12px rgba(255,106,19,0.2);
            background: rgba(255,255,255,0.96);
        }
        section[data-testid="stSidebar"] .stTextInput input::placeholder {
            color: #8cadc8;
        }

        section[data-testid="stSidebar"] .stButton > button {
            background: linear-gradient(135deg, var(--dasa-orange) 0%, var(--dasa-orange-light) 100%);
            color: #ffffff;
            border: none;
            font-weight: 700;
            border-radius: 10px;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            position: relative;
            overflow: hidden;
        }
        section[data-testid="stSidebar"] .stButton > button::after {
            content: "";
            position: absolute;
            top: 0;
            left: -100%;
            width: 100%;
            height: 100%;
            background: linear-gradient(90deg, transparent, rgba(255,255,255,0.25), transparent);
            transition: left 0.5s ease;
        }
        section[data-testid="stSidebar"] .stButton > button:hover::after {
            left: 100%;
        }
        section[data-testid="stSidebar"] .stButton > button:hover {
            background: linear-gradient(135deg, #e85d0c 0%, var(--dasa-orange) 100%);
            transform: translateY(-2px);
            box-shadow: 0 6px 18px rgba(255, 106, 19, 0.35);
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
            border-radius: 10px;
            transition: all 0.3s ease;
        }
        section[data-testid="stSidebar"] .stSelectbox > div > div:hover {
            border-color: rgba(255,106,19,0.4);
        }

        /* â”€â”€ Headings & Metrics â”€â”€ */
        div[data-testid="stMetricValue"] {
            color: var(--dasa-blue);
            font-weight: 900;
            text-shadow: 0 1px 2px rgba(0,0,0,0.05);
        }
        h1, h2, h3 {
            color: var(--dasa-blue) !important;
            font-weight: 800 !important;
        }

        /* â”€â”€ DataFrames â”€â”€ */
        div[data-testid="stDataFrame"] {
            border: 1px solid var(--ec-border);
            border-radius: 14px;
            background: #ffffff;
            box-shadow: 0 4px 16px rgba(0, 59, 113, 0.06);
            animation: fadeIn 0.5s ease-out;
            overflow: hidden;
        }
        div[data-testid="stDataFrame"]::before {
            content: "";
            display: block;
            height: 3px;
            background: linear-gradient(90deg, var(--dasa-blue) 0%, var(--dasa-orange) 100%);
        }

        /* â”€â”€ Buttons â”€â”€ */
        .stButton > button,
        .stDownloadButton > button {
            border-radius: 10px;
            border: 1px solid var(--ec-border);
            background: linear-gradient(180deg, #ffffff 0%, #f0f5fc 100%);
            color: var(--dasa-blue);
            font-weight: 700;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            position: relative;
            overflow: hidden;
        }

        .stButton > button::after,
        .stDownloadButton > button::after {
            content: "";
            position: absolute;
            top: 0;
            left: -100%;
            width: 100%;
            height: 100%;
            background: linear-gradient(90deg, transparent, rgba(255,255,255,0.4), transparent);
            transition: left 0.5s ease;
        }
        .stButton > button:hover::after,
        .stDownloadButton > button:hover::after {
            left: 100%;
        }

        .stButton > button:hover,
        .stDownloadButton > button:hover {
            border-color: var(--dasa-blue-light);
            background: linear-gradient(180deg, #fefefe 0%, #e3edfa 100%);
            color: var(--dasa-blue);
            transform: translateY(-2px);
            box-shadow: 0 6px 16px rgba(0, 59, 113, 0.15);
        }

        .stDownloadButton > button {
            border-left: 4px solid var(--dasa-orange);
            background: linear-gradient(135deg, #fff8f3 0%, #fff0e6 100%);
        }
        .stDownloadButton > button:hover {
            background: linear-gradient(135deg, #fff0e6 0%, #ffe4d4 100%);
            border-left-color: #e05500;
            box-shadow: 0 6px 16px rgba(255, 106, 19, 0.15);
        }

        /* â”€â”€ Inputs premium â”€â”€ */
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
            box-shadow: 0 0 0 3px rgba(0,59,113,0.1);
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

        /* â”€â”€ Alertas redesenhados â”€â”€ */
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

        /* â”€â”€ Expanders â”€â”€ */
        div[data-testid="stExpander"] details {
            border: 1px solid var(--ec-border);
            border-radius: 14px !important;
            background: rgba(255,255,255,0.85);
            backdrop-filter: blur(6px);
            -webkit-backdrop-filter: blur(6px);
            transition: all 0.3s ease;
            overflow: hidden;
        }
        div[data-testid="stExpander"] details:hover {
            box-shadow: 0 4px 16px rgba(0, 59, 113, 0.08);
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
            background: rgba(0,59,113,0.04);
        }

        /* â”€â”€ Header â”€â”€ */
        header[data-testid="stHeader"] {
            background: linear-gradient(90deg, var(--dasa-blue) 0%, #004d8f 60%, var(--dasa-orange) 100%);
            background-size: 200% 100%;
            animation: gradientFlow 6s ease infinite;
            border-bottom: none;
            height: 4px;
            min-height: 4px;
        }

        [data-testid="stSidebarCollapsedControl"] {
            display: flex !important;
            visibility: visible !important;
            opacity: 1 !important;
            z-index: 1000;
        }

        /* â”€â”€ BRAND HEADER PROFISSIONAL â”€â”€ */
        .brand-wrap {
            display: flex;
            justify-content: center;
            margin: 0 0 16px 0;
            animation: fadeInUp 0.7s ease-out;
        }
        .brand-card {
            background: linear-gradient(135deg, var(--dasa-blue) 0%, #004d8f 40%, #003060 70%, #002040 100%);
            border: none;
            border-radius: 20px;
            padding: 24px 36px;
            box-shadow:
                0 16px 48px rgba(0, 59, 113, 0.25),
                0 6px 16px rgba(0, 0, 0, 0.1),
                inset 0 1px 0 rgba(255,255,255,0.12);
            text-align: center;
            width: min(580px, 96vw);
            min-height: 140px;
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
            height: 4px;
            background: linear-gradient(90deg, var(--dasa-orange), var(--dasa-orange-light), var(--dasa-orange));
            animation: shimmer 3s infinite linear;
            background-size: 200% auto;
        }
        .brand-card::after {
            content: "";
            position: absolute;
            bottom: 0;
            left: 0;
            right: 0;
            height: 4px;
            background: linear-gradient(90deg, var(--dasa-orange-light), var(--dasa-orange), var(--dasa-orange-light));
            animation: shimmer 3s infinite linear;
            background-size: 200% auto;
        }
        .brand-card .brand-glow {
            position: absolute;
            top: -60%;
            left: -20%;
            width: 140%;
            height: 200%;
            background: radial-gradient(ellipse at center, rgba(255,106,19,0.06) 0%, transparent 60%);
            pointer-events: none;
        }
        .brand-logo-icon {
            width: 48px;
            height: 48px;
            margin-bottom: 8px;
            animation: float 3s ease-in-out infinite;
        }
        .brand-title {
            margin: 0 !important;
            font-weight: 900;
            letter-spacing: 8px;
            font-size: 42px !important;
            color: #ffffff;
            line-height: 1;
            text-transform: uppercase;
            text-shadow: 0 2px 12px rgba(0,0,0,0.35);
        }
        .brand-divider {
            width: 80px;
            height: 3px;
            background: linear-gradient(90deg, var(--dasa-orange), var(--dasa-orange-light));
            border-radius: 2px;
            margin: 10px auto;
        }
        .brand-subtitle {
            margin: 0 !important;
            font-weight: 700;
            font-size: 15px !important;
            color: var(--dasa-orange-light);
            line-height: 1.3;
            letter-spacing: 3px;
            text-transform: uppercase;
        }

        /* â”€â”€ Tabs premium â”€â”€ */
        .stTabs [data-baseweb="tab-list"] {
            gap: 4px;
            background: rgba(255,255,255,0.6);
            backdrop-filter: blur(6px);
            -webkit-backdrop-filter: blur(6px);
            border-bottom: none;
            border-radius: 12px;
            padding: 4px;
        }
        .stTabs [data-baseweb="tab"] {
            background: transparent;
            border: none;
            border-radius: 10px;
            color: #3a5570;
            font-weight: 800;
            font-size: 0.95rem;
            padding: 8px 20px;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .stTabs [data-baseweb="tab"]:hover {
            color: var(--dasa-blue);
            background: rgba(0,59,113,0.06);
        }
        .stTabs [aria-selected="true"] {
            color: #ffffff !important;
            background: linear-gradient(135deg, var(--dasa-blue) 0%, #004d8f 100%) !important;
            font-weight: 900;
            box-shadow: 0 4px 12px rgba(0,59,113,0.2);
        }

        /* â”€â”€ Charts â”€â”€ */
        div[data-testid="stPlotlyChart"] {
            width: 100%;
            animation: fadeIn 0.6s ease-out;
            border-radius: 14px;
            overflow: hidden;
            box-shadow: 0 4px 16px rgba(0, 59, 113, 0.06);
            border: 1px solid var(--ec-border);
            background: #ffffff;
        }

        /* â”€â”€ Section dividers â”€â”€ */
        .section-divider {
            height: 2px;
            background: linear-gradient(90deg, transparent, var(--dasa-blue-light), var(--dasa-orange), transparent);
            margin: 16px 0;
            border: none;
            animation: fadeIn 0.8s ease-out;
        }

        /* â”€â”€ Footer â”€â”€ */
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

        /* â”€â”€ Responsive â”€â”€ */
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

        /* â”€â”€ Tipografia DASA para st.caption â”€â”€ */
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
            <span title='LÃ³gica: destaca chamados com maior risco operacional para decisÃ£o rÃ¡pida.' style='display:inline-block;vertical-align:middle;cursor:help;'><svg width='18' height='18' viewBox='0 0 18 18'><circle cx='9' cy='9' r='8' fill='#e6effa' stroke='#b8c8dd'/><text x='9' y='13' text-anchor='middle' font-size='11' font-weight='bold' fill='#1e4b7a'>i</text></svg></span>
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


def build_priority_table(df: pd.DataFrame) -> pd.DataFrame:
    status_norm = df["STATUS"].map(normalize_status)
    abertos = df[status_norm == "ABERTO"].copy()
    if abertos.empty:
        return pd.DataFrame(columns=["Quadro de Trabalho", "Abertos", "Alta Criticidade", "Backlog >30 dias"])

    today = pd.Timestamp.now().normalize()
    abertos["DIAS_PARADO"] = (today - abertos["DATA_ABERTURA"]).dt.days
    abertos["DIAS_PARADO"] = abertos["DIAS_PARADO"].fillna(0).clip(lower=0)

    resumo = (
        abertos.groupby("QUADRO", as_index=False)
        .agg(
            Abertos=("QUADRO", "size"),
            AltaCrit=("CRITICIDADE", lambda s: int((s == "ALTA").sum())),
            Backlog30=("DIAS_PARADO", lambda s: int((s > 30).sum())),
        )
        .sort_values(by=["AltaCrit", "Backlog30", "Abertos"], ascending=False, kind="stable")
        .head(8)
        .rename(
            columns={
                "QUADRO": "Quadro de Trabalho",
                "AltaCrit": "Alta Criticidade",
                "Backlog30": "Backlog >30 dias",
            }
        )
    )
    return resumo


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
                        ("FONTSIZE", (0, 0), (-1, -1), font_size)]
                )
            )
            return t

        # Corrige valores '-' em colunas numÃ©ricas para evitar erro de conversÃ£o
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
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]
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
        ["Abertos", fmt_int(int(metrics.get("abertos", 0))), "Cancelados", f"{fmt_int(cancelados)} ({fmt_pct(percentual_cancelados)})"]]

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
        "<font color='#07155f'><b>DASA</b></font><br/><font color='#ff5a1f'><b>Engenharia ClÃ­nica - AC</b></font>",
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
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]
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
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]
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
        "<font color='#07155f'><b>DASA</b></font><br/><font color='#ff5a1f'><b>Engenharia ClÃ­nica - AC</b></font>",
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
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]
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
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fbff")])]
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


def main() -> None:
    st.set_page_config(page_title="Engenharia Clinica", page_icon="ðŸ› ï¸", layout="wide")
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
        <div class='brand-wrap'>
            <div class='brand-card'>
                <div class='brand-glow'></div>
                <svg class='brand-logo-icon' viewBox='0 0 100 100' fill='none' xmlns='http://www.w3.org/2000/svg'>
                  <rect x='10' y='10' width='80' height='80' rx='16' fill='rgba(255,255,255,0.12)' stroke='rgba(255,255,255,0.3)' stroke-width='2'/>
                  <rect x='42' y='22' width='16' height='56' rx='4' fill='white'/>
                  <rect x='22' y='42' width='56' height='16' rx='4' fill='white'/>
                </svg>
                <p class='brand-title'>DASA</p>
                <div class='brand-divider'></div>
                <p class='brand-subtitle'>Engenharia ClÃ­nica â€” AC</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.session_state["uploaded_file_bytes"] is None:
        st.markdown(
            """
            <div class='upload-panel'>
                <svg width='36' height='36' viewBox='0 0 24 24' fill='none' style='margin-bottom:6px;'>
                  <path d='M12 16V4m0 0L8 8m4-4l4 4' stroke='#003B71' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'/>
                  <path d='M20 16v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2' stroke='#FF6A13' stroke-width='2' stroke-linecap='round'/>
                </svg>
                <h3>Entrada de Arquivo</h3>
                <p>Arraste ou selecione sua planilha</p>
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
        # NÃ£o bloqueia a extraÃ§Ã£o, segue com o processamento

    with st.sidebar:
        # â”€â”€ Cabecalho â”€â”€
        st.markdown("### :bar_chart: Painel de Filtros")
        c_info1, c_info2 = st.columns(2)
        c_info1.caption(f"v{APP_VERSION} Â· {build_label}")
        c_info2.caption(st.session_state.get("uploaded_file_name", "-"))
        if st.button(":arrows_counterclockwise: Trocar arquivo", use_container_width=True):
            st.session_state["uploaded_file_bytes"] = None
            st.session_state["uploaded_file_name"] = ""
            st.rerun()

        st.divider()

        # â”€â”€ Opcoes disponiveis â”€â”€
        regiao_options = ["TODAS"] + sorted([x for x in df["REGIAO"].dropna().unique().tolist() if x])
        quadro_options = sorted([x for x in df["QUADRO"].dropna().unique().tolist() if x])
        tag_options = sorted([x for x in df["TAG"].dropna().astype("string").tolist() if str(x).strip()])
        criticidade_options = ["TODAS"] + sorted([x for x in df["CRITICIDADE"].dropna().unique().tolist() if x])
        tipo_servico_options = ["TODOS", "CORRETIVA", "PREVENTIVA", "CALIBRACAO"]
        has_tipo_servico = "TIPO_SERVICO" in df.columns

        data_validas = df["DATA_ABERTURA"].dropna()
        min_data = data_validas.min().date() if not data_validas.empty else None
        max_data = data_validas.max().date() if not data_validas.empty else None

        # â”€â”€ Inicializacao de session_state â”€â”€
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

        # â”€â”€ Secao 1: Quadro de Trabalho â”€â”€
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

        # â”€â”€ Secao 2: Tipo de Servico â”€â”€
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

        # â”€â”€ Secao 4: Periodo â”€â”€
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

        # â”€â”€ Secao 5: Pesquisa Global â”€â”€
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

        # â”€â”€ Botao Limpar Tudo â”€â”€
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
        data_final != max_data if data_final and max_data else False])
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
                background:linear-gradient(135deg, rgba(0,59,113,0.10), rgba(255,106,19,0.08));
                border-left:4px solid #FF6A13; border-radius:8px;
                backdrop-filter:blur(6px); margin-bottom:8px;
            '>
                <span style='font-size:1.6rem;'>ðŸ”</span>
                <span style='font-weight:700;color:#003B71;font-size:0.95rem;'>
                    {filtros_ativos_count} filtro(s) ativo(s)
                </span>
                <span style='color:#1a3c5e;font-size:0.88rem;'>
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
                background:rgba(0,59,113,0.05); border-left:4px solid #003B71;
                border-radius:8px; margin-bottom:8px;
            '>
                <span style='font-size:1.6rem;'>ðŸ“Š</span>
                <span style='color:#1a3c5e;font-size:0.9rem;'>
                    {len(df)} registros Â· Nenhum filtro ativo â€” exibindo todos os dados
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

    st.caption(f"v{APP_VERSION} Â· Build {build_label} Â· Filtro {filter_id} Â· {filtros_texto_display_l1} Â· {filtros_texto_display_l2}")

    tab1, tab2, tab3, tab4 = st.tabs([
        "Dashboard Gerencial",
        "Relatorio Detalhado (Abertos)",
        "Fiabilidade e Historico (MTBF)",
        "Pos-Preventiva (<=30 dias)"])

    with tab1:
        st.subheader("Painel Executivo Operacional")

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

        st.markdown("<div class='section-divider'></div>", unsafe_allow_html=True)

        col1, col2 = st.columns(2)
        selected_faixa = None
        selected_falha = None

        with col1:
            st.markdown("""
                <span style='font-size:1.45rem;font-weight:800;'>Analise de Aging de Chamados
                    <span title='LÃ³gica: distribui chamados por faixa de dias para identificar gargalos e backlog.' style='display:inline-block;vertical-align:middle;cursor:help;'><svg width='18' height='18' viewBox='0 0 18 18'><circle cx='9' cy='9' r='8' fill='#e6effa' stroke='#b8c8dd'/><text x='9' y='13' text-anchor='middle' font-size='11' font-weight='bold' fill='#1e4b7a'>i</text></svg></span>
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
                    <span title='LÃ³gica: ordena falhas por quantidade para priorizar causas e custos mais relevantes.' style='display:inline-block;vertical-align:middle;cursor:help;'><svg width='18' height='18' viewBox='0 0 18 18'><circle cx='9' cy='9' r='8' fill='#e6effa' stroke='#b8c8dd'/><text x='9' y='13' text-anchor='middle' font-size='11' font-weight='bold' fill='#1e4b7a'>i</text></svg></span>
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

        show_click_details = st.toggle(
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
                ("Pior SLA Atual", f"{max_parado} dias")]
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

    # â”€â”€ Footer profissional â”€â”€
    st.markdown(
        """
        <div class='section-divider'></div>
        <div class='app-footer'>
            <p class='app-footer-text'>
                <span class='app-footer-brand'>DASA</span>
                <span class='app-footer-accent'> Â· </span>
                Engenharia ClÃ­nica â€” Painel AnalÃ­tico
                <span class='app-footer-accent'> Â· </span>
                Desenvolvido com Streamlit
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()

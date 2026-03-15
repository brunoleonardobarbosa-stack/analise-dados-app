import io
import re
import unicodedata
from typing import Iterable

import pandas as pd
import streamlit as st

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


def parse_mixed_date_series(series: pd.Series) -> pd.Series:
    raw = series.astype("string").str.strip()
    parsed = pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]")

    iso_mask = raw.str.match(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}($|\s+\d{1,2}:\d{1,2})", na=False)
    if iso_mask.any():
        parsed.loc[iso_mask] = pd.to_datetime(raw.loc[iso_mask], errors="coerce", dayfirst=False)

    br_mask = raw.str.match(r"^\d{1,2}[/-]\d{1,2}[/-]\d{2,4}($|\s+\d{1,2}:\d{1,2})", na=False)
    br_mask = br_mask & parsed.isna()
    if br_mask.any():
        parsed.loc[br_mask] = pd.to_datetime(raw.loc[br_mask], errors="coerce", dayfirst=True)

    excel_mask = raw.str.match(r"^\d{4,5}$", na=False) & parsed.isna()
    if excel_mask.any():
        serial_values = pd.to_numeric(raw.loc[excel_mask], errors="coerce")
        parsed.loc[excel_mask] = pd.to_datetime(serial_values, unit="D", origin="1899-12-30", errors="coerce")

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
        "ABERTO", "ABERTA", "EM_ABERTO", "OPEN", "AGUARDANDO",
        "EM_ESPERA", "EM_EXECUCAO", "EM_MANUTENCAO",
    }
    if text_key in open_exact:
        return "ABERTO"

    open_prefixes = (
        "AGUARDANDO", "EM_ESPERA", "EM_EXECUCAO", "EM_MANUTENCAO",
        "SERVICO_AG", "SERVICO_EM",
    )
    if any(text_key.startswith(prefix) for prefix in open_prefixes):
        return "ABERTO"

    if text_key in {
        "FECHADO", "FECHADA", "CLOSED", "ENCERRADO", "ENCERRADA",
        "CONCLUIDO", "CONCLUIDA", "FINALIZADO", "FINALIZADA",
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
    if "CALIBR" in key or "VERIFIC" in key:
        return "CALIBRACAO"

    return "OUTROS"


@st.cache_data(show_spinner=False)
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

    if data_inicial is not None or data_final is not None:
        filtered = filtered[filtered["DATA_ABERTURA"].notna()]
        abertura_dia = filtered["DATA_ABERTURA"].dt.normalize()

        if data_inicial is not None:
            filtered = filtered[abertura_dia >= pd.Timestamp(data_inicial)]

        if data_final is not None:
            filtered = filtered[abertura_dia <= pd.Timestamp(data_final)]

    return filtered

import pandas as pd
import streamlit as st
from .data_processing import (
    normalize_status,
    normalize_service_group,
    normalize_scalar_text,
    resolve_requester_column,
)


@st.cache_data(show_spinner=False)
def compute_metrics(df: pd.DataFrame) -> dict[str, int | float | str | None]:
    status_norm = df["STATUS"].map(normalize_status)

    abertos = int((status_norm == "ABERTO").sum())
    aguardando_relatorio = int((status_norm == "AGUARDANDO_RELATORIO").sum())
    fechados = int((status_norm == "FECHADO").sum())
    cancelados = int((status_norm == "CANCELADO").sum())

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


@st.cache_data(show_spinner=False)
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

    subset["FALHA"] = subset["FALHA"].fillna("NAO INFORMADO")
    subset[origem_col] = subset[origem_col].fillna("NAO INFORMADO")

    counts = (
        subset.groupby(["FALHA", origem_col], dropna=False)
        .size()
        .reset_index(name="Ocorrencias")
    )
    counts = counts.sort_values("Ocorrencias", ascending=False).head(top_n)

    counts.columns = ["Problema Relatado", "Origem do Problema", "Ocorrencias"]
    return counts

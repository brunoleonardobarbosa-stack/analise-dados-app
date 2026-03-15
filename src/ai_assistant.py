import os
import pandas as pd
import streamlit as st
from functools import lru_cache

try:
    import openai
except ImportError:
    openai = None

from .data_processing import normalize_status

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


@st.cache_data(show_spinner=False, ttl=300)
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
            model="gpt-4o-mini",
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


def _ia_responder_pergunta(pergunta: str, diag: dict) -> str:
    """Responde perguntas sobre os dados com base no diagnóstico."""
    pergunta_lower = pergunta.lower().strip()
    m = diag["metricas"]

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


@st.cache_data(show_spinner=False)
def gerar_diagnostico_inteligente(df: pd.DataFrame) -> dict:
    """Analisa o DataFrame filtrado e retorna um diagnóstico completo."""
    today = pd.Timestamp.now().normalize()
    status_norm = df["STATUS"].map(normalize_status)

    abertos_mask = status_norm == "ABERTO"
    fechados_mask = status_norm == "FECHADO"
    cancelados_mask = status_norm == "CANCELADO"

    abertos = df[abertos_mask].copy()
    fechados = df[fechados_mask].copy()
    total = len(df)

    if not abertos.empty:
        abertos["dias_parado"] = (today - abertos["DATA_ABERTURA"]).dt.days
        abertos["dias_parado"] = abertos["dias_parado"].clip(lower=0)
    else:
        abertos["dias_parado"] = pd.Series(dtype=float)

    if not fechados.empty and "DATA_FECHAMENTO" in fechados.columns:
        valid_fechados = fechados.dropna(subset=["DATA_ABERTURA", "DATA_FECHAMENTO"]).copy()
        if not valid_fechados.empty:
            valid_fechados["duracao"] = (valid_fechados["DATA_FECHAMENTO"] - valid_fechados["DATA_ABERTURA"]).dt.days
            valid_fechados["duracao"] = valid_fechados["duracao"].clip(lower=0)
            mttr = valid_fechados["duracao"].mean()
        else:
            mttr = 0
    else:
        mttr = 0

    metricas = {
        "total": total,
        "abertos": len(abertos),
        "fechados": len(fechados),
        "cancelados": df[cancelados_mask].shape[0],
        "mttr": mttr,
        "alta_abertos": df[abertos_mask & (df["CRITICIDADE"] == "ALTA")].shape[0],
        "taxa_cancelamento": (df[cancelados_mask].shape[0] / total * 100) if total > 0 else 0,
        "media_aging": abertos["dias_parado"].mean() if not abertos.empty else 0,
        "backlog_30": (abertos["dias_parado"] > 30).sum() if not abertos.empty else 0,
        "backlog_60": (abertos["dias_parado"] > 60).sum() if not abertos.empty else 0,
    }

    pontos = 100

    pct_backlog = (metricas["backlog_30"] / metricas["abertos"] * 100) if metricas["abertos"] > 0 else 0
    if pct_backlog == 0:
        nota_backlog = 25
    elif pct_backlog >= 20:
        nota_backlog = 0
    else:
        nota_backlog = 25 - (pct_backlog / 20 * 25)

    if metricas["mttr"] <= 15:
        nota_mttr = 25
    elif metricas["mttr"] >= 30:
        nota_mttr = 0
    else:
        nota_mttr = 25 - ((metricas["mttr"] - 15) / 15 * 25)

    taxa_fechamento = (metricas["fechados"] / total * 100) if total > 0 else 0
    if taxa_fechamento >= 80:
        nota_fechamento = 20
    elif taxa_fechamento <= 30:
        nota_fechamento = 0
    else:
        nota_fechamento = ((taxa_fechamento - 30) / 50) * 20

    pct_critico = (metricas["alta_abertos"] / metricas["abertos"] * 100) if metricas["abertos"] > 0 else 0
    if pct_critico == 0:
        nota_critico = 15
    elif pct_critico >= 15:
        nota_critico = 0
    else:
        nota_critico = 15 - (pct_critico / 15 * 15)

    if metricas["taxa_cancelamento"] <= 5:
        nota_canc = 15
    elif metricas["taxa_cancelamento"] >= 20:
        nota_canc = 0
    else:
        nota_canc = 15 - ((metricas["taxa_cancelamento"] - 5) / 15 * 15)

    nota_final = nota_backlog + nota_mttr + nota_fechamento + nota_critico + nota_canc
    
    if nota_final >= 80:
        label = "Excelente"
    elif nota_final >= 65:
        label = "Bom"
    elif nota_final >= 50:
        label = "Regular"
    else:
        label = "Critico"

    alertas = []
    if metricas["backlog_60"] > 0:
        alertas.append({"tipo": "CRITICO", "texto": f"{metricas['backlog_60']} chamados abertos ha mais de 60 dias."})
    elif metricas["backlog_30"] > 0:
        alertas.append({"tipo": "ATENCAO", "texto": f"{metricas['backlog_30']} chamados compoem backlog de 30 dias."})

    if metricas["alta_abertos"] > 0:
        alertas.append({"tipo": "CRITICO", "texto": f"{metricas['alta_abertos']} equipamentos de ALTA criticidade parados."})
    
    if metricas["mttr"] > 20:
        alertas.append({"tipo": "ATENCAO", "texto": f"MTTR de {metricas['mttr']:.1f} dias esta acima da meta aceitavel."})

    if metricas["taxa_cancelamento"] > 10:
        alertas.append({"tipo": "ATENCAO", "texto": f"Taxa de cancelamento elevada ({metricas['taxa_cancelamento']:.1f}%)."})

    top_falhas = []
    if not abertos.empty and "FALHA" in abertos.columns:
        falhas = abertos["FALHA"].value_counts().head(3)
        top_falhas = [(str(k), int(v)) for k, v in falhas.items()]

    recomendacoes = []
    if metricas["alta_abertos"] > 0:
        recomendacoes.append(("Alta", "Priorizar atendimento imediato dos equipamentos de alta criticidade identificados no painel."))
    if metricas["backlog_30"] >= 5:
        recomendacoes.append(("Alta", "Organizar mutirao para inspecao e avaliacao basica do backlog >30 dias."))
    if metricas["mttr"] > 15:
        recomendacoes.append(("Media", "Revisar gargalos nos chamados fechados recentes para entender o alto tempo de resolucao (MTTR)."))
    if not recomendacoes:
        recomendacoes.append(("Baixa", "Manter ritmo de atendimento e realizar avaliacoes preventivas rotineiras."))

    resumo = (
        f"Foram analisados {total} registros. No momento, ha {metricas['abertos']} chamados em aberto "
        f"e {metricas['fechados']} ja resolvidos (taxa de resolucao de {taxa_fechamento:.1f}%). "
    )
    if metricas["mttr"] > 0:
        resumo += f"O tempo medio de atendimento tem sido de {metricas['mttr']:.1f} dias. "
    
    if metricas["abertos"] > 0:
        resumo += f"A idade media dos chamados abertos e de {metricas['media_aging']:.1f} dias. "
        if metricas["backlog_30"] > 0:
            resumo += f"Preocupa o fato de haver {metricas['backlog_30']} chamados com mais de 30 dias de espera. "
        if metricas["alta_abertos"] > 0:
            resumo += f"Adicionalmente, ha {metricas['alta_abertos']} chamados marcados como alta criticidade que exigem atencao imediata."
        else:
            resumo += "Uma boa noticia e que nan ha pendencias de alta criticidade neste filtro."
    else:
        resumo += "A situacao esta totalmente sob controle (fila zerada neste filtro)."

    return {
        "nota": nota_final,
        "nota_label": label,
        "metricas": metricas,
        "alertas": alertas,
        "top_falhas": top_falhas,
        "recomendacoes": recomendacoes,
        "resumo_executivo": resumo,
        "equip_problematicos": [],
        "quadros_ranking": []
    }

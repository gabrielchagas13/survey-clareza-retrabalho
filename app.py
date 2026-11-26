"""Dashboard do survey: Clareza dos requisitos e retrabalho percebido.

Rodar: streamlit run app.py
O CSV bruto padrão é dados/respostas_brutas.csv (pode ser trocado pela
variável de ambiente SURVEY_CSV).
"""
import os
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import analysis as an

BASE = Path(__file__).parent
CSV = Path(os.environ.get("SURVEY_CSV", BASE / "dados" / "respostas_brutas.csv"))
DESVIOS = BASE / "desvios.md"
CORES = ["#b2182b", "#ef8a62", "#d9d9d9", "#67a9cf", "#2166ac"]

st.set_page_config(page_title="Survey: clareza e retrabalho", layout="wide")

import plotly.io as pio
pio.templates["survey"] = go.layout.Template(layout=dict(
    font=dict(size=13, color="#222"),
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    colorway=["#1f3a5f", "#7a9cc6", "#c0504d", "#9bbb59", "#8064a2"],
    xaxis=dict(gridcolor="#e6e8f0", zerolinecolor="#c9cde0"),
    yaxis=dict(gridcolor="#e6e8f0", zerolinecolor="#c9cde0"),
    title=dict(font=dict(size=16))))
pio.templates.default = "plotly_white+survey"

st.markdown("""
<style>
.block-container { padding-top: 2rem; max-width: 1300px; }
h1 { font-weight: 700; margin-bottom: 0; }
div[data-testid="stMetric"] { border-left: 3px solid #1f3a5f; padding-left: 12px; }
.check { display:flex; justify-content:space-between; border-bottom:1px solid #e3e3e3;
  padding:8px 2px; font-size:.95rem; }
.check.total { border-bottom:none; border-top:2px solid #333; font-weight:700; }
.muted { color:#888; }
</style>
""", unsafe_allow_html=True)
st.title("Clareza dos requisitos e retrabalho percebido")
st.caption("Medição e Experimentação em Engenharia de Software · PUC Minas · "
           "dados lidos do CSV bruto do Google Forms")

# ---------------------------------------------------------------- dados
st.sidebar.header("Dados")
upload = st.sidebar.file_uploader("Exportação bruta do Google Forms (.csv)", type="csv",
                                  help="Arraste o CSV baixado do Forms. Sem upload, o app lê "
                                       "dados/respostas_brutas.csv.")
if upload is not None:
    conteudo, nome_csv = upload.getvalue(), upload.name
elif CSV.exists():
    conteudo, nome_csv = CSV.read_bytes(), CSV.name
else:
    st.warning("Nenhum CSV carregado. Arraste a exportação do Google Forms na barra lateral "
               "ou salve-a em `dados/respostas_brutas.csv`.")
    st.stop()
st.sidebar.caption(f"Arquivo: `{nome_csv}`")


@st.cache_data
def carregar(conteudo: bytes):
    import io
    bruto, m = an.carregar(io.BytesIO(conteudo))
    df = an.preparar(bruto, m)
    df["Motivo"] = an.aplicar_descartes(bruto, df, m)
    cod = an.codificar_e2(bruto, m)
    for c in cod.columns:
        df["E2::" + c] = cod[c]
    return df, m


try:
    df_all, mapa = carregar(conteudo)
except Exception as e:  # CSV ilegível
    st.error(f"Não foi possível ler o CSV: {e}")
    st.stop()

if "SIMULA" in nome_csv.upper():
    st.error("⚠️ DADOS SIMULADOS (fictícios), apenas para demonstração do dashboard. "
             "Não são respostas reais e não podem ser usados como resultado do trabalho.")

if mapa.faltando:
    st.warning("Colunas esperadas pelo protocolo não encontradas no CSV: "
               f"**{', '.join(mapa.faltando)}**. As análises que dependem delas ficam "
               "indisponíveis. Ajuste o formulário/CSV ou o mapeamento em `analysis.PADROES`.")
if mapa.duplicadas:
    st.warning(f"Mais de uma coluna casou com o mesmo código: {mapa.duplicadas}. "
               "Foi usada a primeira; confira o CSV.")

validos_all = df_all[df_all["Motivo"].isna()]

# ---------------------------------------------------------------- filtros
st.sidebar.header("Filtros por segmento")
st.sidebar.caption("Aplicam-se às respostas válidas. O n e a margem de erro se atualizam.")
df = validos_all.copy()
for col, rotulo in [("Faixa", "Experiência"), ("P3", "Porte da organização"),
                    ("P4", "Forma de trabalho"), ("P1", "Função")]:
    if col in df:
        opcoes = [o for o in (df[col].cat.categories if col == "Faixa"
                              else sorted(df[col].dropna().unique()))]
        escolha = st.sidebar.multiselect(rotulo, opcoes, default=opcoes)
        if set(escolha) != set(opcoes):
            df = df[df[col].isin(escolha)]

n = len(df)
me = an.margem_erro(n)
def f2(x, d=2):
    return "—" if pd.isna(x) else f"{x:.{d}f}".replace(".", ",")


st.sidebar.metric("n válido (filtrado)", n)
st.sidebar.metric("Margem de erro (95%, p = 0,5)",
                  f"±{f2(me * 100, 1)} p.p." if n else "—")

st.info("**Amostra não probabilística** (conveniência + bola de neve). Os resultados "
        "valem para esta amostra e não se generalizam para a população. As análises "
        "medem **percepção** e **associação**, nunca causalidade. "
        f"n = {n} · margem de erro de referência ±{f2(me * 100, 1)} p.p." if n else
        "Nenhuma resposta válida com os filtros atuais.")
if 0 < n < 10:
    st.warning("Menos de 10 respostas no segmento: testes com poder muito baixo.")


def fmt_p(p):
    return "—" if pd.isna(p) else ("< 0,001" if p < 0.001 else f"{p:.3f}".replace(".", ","))


def barras_divergentes(dados: pd.DataFrame, itens, rotulos, titulo):
    fig = go.Figure()
    dist = {i: an.distribuicao(dados, i) for i in itens}
    nomes = [an.ENUNCIADOS[i] for i in itens]
    # neutro dividido ao meio em torno do zero
    for nivel, sinal, frac in [(2, -1, 1), (1, -1, 1), (3, -1, .5), (3, 1, .5), (4, 1, 1), (5, 1, 1)]:
        vals = [sinal * dist[i][nivel] * frac for i in itens]
        texto = [f"{dist[i][nivel]:.0f}%" if (nivel != 3 or sinal > 0) and dist[i][nivel] >= 5
                 else "" for i in itens]
        fig.add_bar(y=nomes, x=vals, orientation="h", name=rotulos[nivel - 1],
                    marker_color=CORES[nivel - 1], text=texto, textposition="inside",
                    showlegend=not (nivel == 3 and sinal > 0), legendgroup=str(nivel),
                    hovertemplate="%{y}<br>" + rotulos[nivel - 1] +
                    f": %{{customdata:.1f}}%<extra></extra>",
                    customdata=[dist[i][nivel] for i in itens])
    fig.update_layout(barmode="relative", title=titulo, height=110 + 55 * len(itens),
                      xaxis=dict(title="% de respondentes", range=[-100, 100],
                                 tickvals=[-100, -50, 0, 50, 100],
                                 ticktext=["100", "50", "0", "50", "100"]),
                      legend=dict(orientation="h", y=-0.25, traceorder="normal"),
                      margin=dict(l=10, r=10, t=50, b=10))
    fig.update_yaxes(autorange="reversed")
    return fig


SEGMENTOS = {"Experiência": "Faixa", "Função": "P1", "Estagiário × demais": "Funcao2",
             "Porte": "P3", "Forma de trabalho": "P4"}
SEGMENTOS = {k: v for k, v in SEGMENTOS.items() if v in df_all}
VARIAVEIS = {"M1 Clareza": "M1", "M2 Retrabalho": "M2", "M3 Instabilidade": "M3",
             **{an.ENUNCIADOS[i]: i for i in an.ITENS_ESCALA}}
VARIAVEIS = {k: v for k, v in VARIAVEIS.items() if v in df_all}
if "P2" in df_all:
    VARIAVEIS["Anos de experiência"] = "P2"

aba_resumo, *abas = st.tabs(["Resumo", "Perfil da amostra", "Itens Likert",
                             "Confiabilidade", "Questões de pesquisa", "Explorar",
                             "Metodologia e desvios", "Questionário", "Evidências da coleta"])


def card(titulo, grande, texto, tags=()):
    det = " · ".join(x for x, _ in tags)
    return f"**{titulo}**\n\n### {grande}\n\n{texto}\n\n<span class='muted'>{det}</span>"


with aba_resumo:
    rec_r = len(df_all)
    val_r = int(df_all["Motivo"].isna().sum())
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Respostas recebidas", rec_r)
    k2.metric("Respostas válidas", val_r, f"{rec_r - val_r} descartada(s)", delta_color="off")
    k3.metric("Margem de erro (95%)", f"±{f2(an.margem_erro(val_r) * 100, 1)} p.p.")
    if "TS" in df_all and df_all["TS"].notna().any():
        k4.metric("Período de coleta", f"{df_all['TS'].min():%d/%m} → {df_all['TS'].max():%d/%m}")
    st.write("")
    if n >= 4:
        r1 = an.spearman_boot(df["M1"], df["M2"], n_boot=500)
        kw2 = an.kruskal(df, "M2", "Faixa") if "Faixa" in df else {"p": np.nan, "eps2": np.nan}
        pr = an.praticas(df) if "E1_respondeu" in df else pd.DataFrame()
        sig1 = r1["p"] < an.ALPHA
        c1, c2, c3 = st.columns(3)
        c1.markdown(card(
            "QP1 · Clareza × Retrabalho", f"ρ = {f2(r1['rho'])}",
            "Quanto mais claros os requisitos, menos retrabalho percebido." if r1["rho"] < 0 and sig1
            else "Sem evidência de associação na amostra.",
            [("Spearman", "info"), (f"p {fmt_p(r1['p'])}", "ok" if sig1 else "no"),
             (f"efeito {an.magnitude_r(r1['rho'])}", "warn")]), unsafe_allow_html=True)
        sig2 = kw2["p"] < an.ALPHA
        c2.markdown(card(
            "QP2 · Retrabalho por experiência", f"p = {fmt_p(kw2['p'])}",
            "O retrabalho percebido difere entre as faixas de experiência." if sig2
            else "Retrabalho percebido parecido entre as faixas de experiência.",
            [("Kruskal-Wallis", "info"), ("significativo" if sig2 else "não significativo",
                                          "ok" if sig2 else "no"),
             (f"ε² = {f2(kw2['eps2'], 2)}", "warn")]), unsafe_allow_html=True)
        if len(pr):
            top = pr.iloc[0]
            c3.markdown(card(
                "QP3 · Prática mais usada", top["Prática"],
                f"{top['k']} de {top['n']} respondentes ({f2(top['Proporção'] * 100, 0)}%), "
                f"IC 95% {f2(top['IC inf'] * 100, 0)}–{f2(top['IC sup'] * 100, 0)}%.",
                [("Wilson IC 95%", "info")]), unsafe_allow_html=True)
        st.write("")
        g1, g2 = st.columns([3, 2])
        with g1:
            if len(pr):
                pp = pr[pr["k"] > 0].sort_values("Proporção")
                fig = go.Figure(go.Bar(x=pp["Proporção"] * 100, y=pp["Prática"], orientation="h",
                                       marker_color="#1f3a5f", text=[f"{v*100:.0f}%" for v in pp["Proporção"]],
                                       textposition="outside",
                                       error_x=dict(type="data", array=(pp["IC sup"] - pp["Proporção"]) * 100,
                                                    arrayminus=(pp["Proporção"] - pp["IC inf"]) * 100,
                                                    color="#7a9cc6")))
                fig.update_layout(title="Práticas usadas para esclarecer requisitos (% e IC 95%)",
                                  height=360, xaxis=dict(range=[0, 100], title="%"),
                                  margin=dict(l=10, r=10, t=50, b=10))
                st.plotly_chart(fig, width="stretch")
        with g2:
            dd = df[["M1", "M2"]].dropna()
            fig = go.Figure(go.Scatter(
                x=dd["M1"] + np.random.default_rng(1).uniform(-.06, .06, len(dd)),
                y=dd["M2"] + np.random.default_rng(2).uniform(-.06, .06, len(dd)),
                mode="markers", marker=dict(size=10, opacity=.65, color="#1f3a5f",
                                            )))
            fig.update_layout(title="Clareza (M1) × Retrabalho (M2)", height=360,
                              xaxis=dict(title="Clareza", range=[.8, 5.2]),
                              yaxis=dict(title="Retrabalho", range=[.8, 5.2]),
                              margin=dict(l=10, r=10, t=50, b=10))
            st.plotly_chart(fig, width="stretch")
    st.caption("Amostra não probabilística: resultados descrevem a amostra, indicam associação "
               "(não causalidade). Detalhes na aba Questões de pesquisa.")

# ================================================================ 1 Perfil
with abas[0]:
    rec = len(df_all)
    desc = int(df_all["Motivo"].notna().sum())
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Respostas recebidas", rec)
    c2.metric("Descartadas", desc)
    c3.metric("Válidas", rec - desc)
    c4.metric("Meta do protocolo", "60 (mín. 50)")
    if "TS" in df_all and df_all["TS"].notna().any():
        st.caption(f"Período das respostas: {df_all['TS'].min():%d/%m/%Y %H:%M} a "
                   f"{df_all['TS'].max():%d/%m/%Y %H:%M}")

    st.progress(min(1.0, (rec - desc) / 60),
                text=f"{rec - desc} de 60 respostas válidas pretendidas "
                     f"({'mínimo de 50 atingido' if rec - desc >= 50 else f'faltam {50 - (rec - desc)} para o mínimo'})")

    esq, dir_ = st.columns(2)
    with esq:
        st.subheader("Limpeza dos dados")
        st.caption("Cada resposta passa pelas verificações na ordem abaixo; é descartada no "
                   "primeiro critério em que falha.")
        vc_m = df_all["Motivo"].value_counts()
        passos = [("a", "Aceitaram o termo de consentimento"),
                  ("b", "Têm 18+ anos e são da população-alvo"),
                  ("c", "Acertaram a pergunta de atenção"),
                  ("e", "Não marcaram a mesma opção em tudo (straight-lining)"),
                  ("f", "Não são respostas duplicadas")]
        restam = rec
        html = ""
        for cod, txt in passos:
            if cod == "c" and "A1" not in df_all:
                html += (f'<div class="check"><span>{txt}</span>'
                         f'<span class="muted">não aplicado (A1 ausente no formulário)</span></div>')
                continue
            fora = int(vc_m.get(an.MOTIVOS[cod], 0))
            restam -= fora
            html += (f'<div class="check"><span>{txt}</span>'
                     f'<span>{restam + fora} → {restam} '
                     f'<span class="muted">({fora} descartada(s))</span></span></div>')
        html += ('<div class="check"><span>Tempo de preenchimento</span>'
                 '<span class="muted">não aplicado (Forms não exporta duração)</span></div>')
        html += f'<div class="check total"><span>Respostas válidas</span><span>{rec - desc}</span></div>'
        
        st.markdown(html, unsafe_allow_html=True)
    with dir_:
        st.subheader("Evolução da coleta")
        if "TS" in df_all and df_all["TS"].notna().any():
            t = df_all.dropna(subset=["TS"]).sort_values("TS")
            t["Válida"] = t["Motivo"].isna()
            dia = t.groupby(t["TS"].dt.date).agg(Recebidas=("Válida", "size"),
                                                 Válidas=("Válida", "sum")).cumsum()
            fig = go.Figure()
            fig.add_scatter(x=dia.index, y=dia["Recebidas"], name="Recebidas (acum.)",
                            mode="lines+markers", line_color="#7a9cc6")
            fig.add_scatter(x=dia.index, y=dia["Válidas"], name="Válidas (acum.)",
                            mode="lines+markers", line_color="#1f3a5f")
            fig.add_hline(y=50, line_dash="dot", annotation_text="mínimo 50")
            fig.add_hline(y=60, line_dash="dash", annotation_text="meta 60")
            fig.update_layout(height=330, margin=dict(t=10, l=10, r=10, b=10),
                              legend=dict(orientation="h", y=-0.2), hovermode="x unified")
            st.plotly_chart(fig, width="stretch")
            st.caption("Útil como evidência da coleta: mostra o ritmo de respostas por dia.")
        else:
            st.write("O CSV não tem carimbo de data/hora.")

    st.subheader(f"Perfil das respostas válidas (n = {n})")
    if n:
        cols = st.columns(3)
        for box, (col, rotulo) in zip(cols, [("P1", "Função"), ("P3", "Porte"),
                                             ("P4", "Forma de trabalho")]):
            if col in df:
                vc = df[col].value_counts().sort_values()
                fig = go.Figure(go.Bar(x=vc.values, y=vc.index, orientation="h",
                                       marker_color="#1f3a5f",
                                       text=[f"{v} ({v / n * 100:.0f}%)" for v in vc.values],
                                       textposition="auto"))
                fig.update_layout(title=rotulo, height=280, margin=dict(l=10, r=10, t=40, b=10),
                                  xaxis_title="respostas")
                box.plotly_chart(fig, width="stretch")
        if "Faixa" in df:
            vc = df["Faixa"].value_counts().reindex(an.FAIXAS_EXP, fill_value=0)
            st.markdown(f"**Experiência**: mediana {f2(df['P2'].median(), 1)} anos "
                        f"(mín. {f2(df['P2'].min(), 1)}, máx. {f2(df['P2'].max(), 1)})")
            fig = go.Figure(go.Bar(x=vc.index.astype(str), y=vc.values, marker_color="#1f3a5f",
                                   text=vc.values, textposition="outside"))
            fig.update_layout(height=300, margin=dict(l=10, r=10, t=20, b=10),
                              yaxis_title="respostas", xaxis_title="anos de experiência")
            st.plotly_chart(fig, width="stretch")

        st.subheader("Índices (mediana e intervalo interquartil)")
        fig = go.Figure()
        for k, nm in [("M1", "Clareza"), ("M2", "Retrabalho"), ("M3", "Instabilidade")]:
            fig.add_box(y=df[k], name=nm, boxpoints="all", jitter=.4, marker_color="#1f3a5f")
        fig.update_layout(height=340, showlegend=False, yaxis=dict(range=[.8, 5.2], title="1–5"),
                          margin=dict(l=10, r=10, t=20, b=10))
        st.plotly_chart(fig, width="stretch")
        st.dataframe(pd.DataFrame({
            "Índice": ["M1 Clareza (C1–C4)", "M2 Retrabalho (R1–R3)", "M3 Instabilidade (D1–D2)"],
            "Mediana (IIQ)": [an.resumo_iqr(df[k]) for k in ("M1", "M2", "M3")],
            "n": [int(df[k].notna().sum()) for k in ("M1", "M2", "M3")],
        }), hide_index=True, width="stretch")

        st.subheader("Dados faltantes por item (respostas válidas)")
        itens = [i for i in an.ITENS_ESCALA + ["P2"] if i in df]
        falt = pd.DataFrame({"Item": itens, "Faltantes": [int(df[i].isna().sum()) for i in itens]})
        if falt["Faltantes"].sum() == 0:
            st.markdown("Nenhum dado faltante: todos os itens de escala e a experiência (P2) "
                        "eram obrigatórios no formulário, então as respostas válidas estão completas.")
        else:
            st.dataframe(falt, hide_index=True, width="stretch")

# ================================================================ 2 Likert
with abas[1]:
    if n:
        comparar = st.selectbox("Comparar por segmento", ["(amostra toda)", *SEGMENTOS],
                                help="Mostra as barras divergentes separadas por grupo.")
        if comparar == "(amostra toda)":
            grupos = [("", df)]
        else:
            col = SEGMENTOS[comparar]
            cats = (list(df[col].cat.categories) if hasattr(df[col], "cat")
                    else sorted(df[col].dropna().unique()))
            grupos = [(f" · {g} (n={int((df[col] == g).sum())})", df[df[col] == g])
                      for g in cats if (df[col] == g).any()]
        blocos = [([i for i in an.CLAREZA if i in df], an.ROTULOS_CONC, "Clareza (concordância)"),
                  ([i for i in an.ITENS_FREQUENCIA if i in df], an.ROTULOS_FREQ,
                   "Dúvidas, mudanças e retrabalho (frequência, últimos 3 meses)")]
        for itens, rot, titulo in blocos:
            if not itens:
                continue
            cols = st.columns(min(len(grupos), 2))
            for k, (suf, dg) in enumerate(grupos):
                cols[k % len(cols)].plotly_chart(barras_divergentes(dg, itens, rot, titulo + suf),
                                                 width="stretch", key=f"lk{titulo}{k}")
        if comparar != "(amostra toda)":
            st.caption("Grupos pequenos (n < 10) têm percentuais muito instáveis.")
        med = pd.DataFrame({"Item": [an.ENUNCIADOS[i] for i in an.ITENS_ESCALA if i in df],
                            "Mediana (IIQ)": [an.resumo_iqr(df[i]) for i in an.ITENS_ESCALA if i in df]})
        st.dataframe(med, hide_index=True, width="stretch")
    else:
        st.write("Sem respostas válidas.")

# ================================================================ 3 Cronbach
with abas[2]:
    st.markdown("Alfa de Cronbach por construto (critério do protocolo: α ≥ 0,70). "
                "R1–R3 estão todos na escala de frequência (1–5).")
    linhas = []
    for nome, itens in [("Clareza (M1)", an.CLAREZA), ("Retrabalho (M2)", an.RETRABALHO),
                        ("Instabilidade (M3)", an.INSTABILIDADE)]:
        itens = [i for i in itens if i in df]
        a, nn = an.cronbach(df, itens)
        linhas.append({"Construto": nome, "Itens": ", ".join(itens), "α": f2(a),
                       "n (casos completos)": nn,
                       "Situação": "—" if pd.isna(a) else ("Aceitável" if a >= .70 else "Abaixo de 0,70")})
        if not pd.isna(a) and a < .70:
            st.warning(f"{nome}: α = {f2(a)} < 0,70. Pelo protocolo, os itens devem ser "
                       "analisados isoladamente e o desvio declarado.")
    st.dataframe(pd.DataFrame(linhas), hide_index=True, width="stretch")
    vals = [float(str(l["α"]).replace(",", ".")) if l["α"] != "—" else 0 for l in linhas]
    fig = go.Figure(go.Bar(x=[l["Construto"] for l in linhas], y=vals,
                           marker_color=["#1f3a5f" if v >= .7 else "#c0504d" for v in vals],
                           text=[l["α"] for l in linhas], textposition="outside"))
    fig.add_hline(y=.7, line_dash="dash", annotation_text="mínimo 0,70")
    fig.update_layout(height=320, yaxis=dict(range=[0, 1.05], title="α de Cronbach"),
                      margin=dict(l=10, r=10, t=20, b=10))
    st.plotly_chart(fig, width="stretch")

    st.subheader("Diagnóstico por item")
    cons = st.radio("Construto", ["Clareza (C1–C4)", "Retrabalho (R1–R3)"], horizontal=True)
    itens = [i for i in (an.CLAREZA if cons.startswith("Clareza") else an.RETRABALHO) if i in df]
    a_tot, _ = an.cronbach(df, itens)
    diag = []
    for i in itens:
        resto = [j for j in itens if j != i]
        a_sem, _ = an.cronbach(df, resto) if len(resto) >= 2 else (np.nan, 0)
        x = df[itens].dropna()
        r_it = x[i].corr(x[resto].sum(axis=1), method="spearman") if len(x) > 3 else np.nan
        diag.append({"Item": an.ENUNCIADOS[i], "Correlação item-resto": f2(r_it),
                     "α se removido": f2(a_sem),
                     "Efeito de remover": "—" if pd.isna(a_sem) or pd.isna(a_tot) else
                     ("melhora α" if a_sem > a_tot else "piora α")})
    st.dataframe(pd.DataFrame(diag), hide_index=True, width="stretch")
    x = df[itens].dropna()
    if len(x) > 3:
        cm = x.corr(method="spearman")
        fig = go.Figure(go.Heatmap(z=cm.values, x=cm.columns, y=cm.index, zmin=-1, zmax=1,
                                   colorscale="RdBu", text=cm.round(2).values,
                                   texttemplate="%{text}"))
        fig.update_layout(height=320, title="Correlações de Spearman entre os itens",
                          margin=dict(t=40, l=10, r=10, b=10))
        st.plotly_chart(fig, width="stretch")
    st.caption("Com 2 itens (instabilidade), o α é limitado e equivale a uma correlação "
               "entre os itens ajustada; interprete com cautela.")

# ================================================================ 4 QPs
with abas[3]:
    # ---------- QP1
    st.header("QP1: a clareza percebida se associa ao retrabalho percebido?")
    st.caption("H1: associação negativa entre M1 e M2 (rho < 0). Spearman, IC 95% por "
               f"bootstrap ({an.N_BOOT} reamostragens). Família QP1 corrigida por Holm.")
    r12 = an.spearman_boot(df["M1"], df["M2"])
    r32 = an.spearman_boot(df["M3"], df["M2"])
    p_adj = an.holm([r12["p"], r32["p"]])
    qp1 = pd.DataFrame([
        {"Par": "M1 Clareza × M2 Retrabalho (principal)", **r12, "p Holm": p_adj[0]},
        {"Par": "M3 Instabilidade × M2 Retrabalho (complementar)", **r32, "p Holm": p_adj[1]},
    ])
    st.dataframe(pd.DataFrame({
        "Par": qp1["Par"], "n": qp1["n"], "rho": qp1["rho"].map(f2),
        "IC 95%": qp1["ic"].map(lambda t: f"[{f2(t[0])}; {f2(t[1])}]"),
        "p bruto": qp1["p"].map(fmt_p), "p Holm": qp1["p Holm"].map(fmt_p),
        "Efeito |rho|": qp1["rho"].map(an.magnitude_r),
        "Margem de erro": qp1["n"].map(lambda k: f"±{f2(an.margem_erro(k) * 100, 1)} p.p."),
    }), hide_index=True, width="stretch")
    d = df[["M1", "M2"]].dropna()
    if len(d):
        fig = go.Figure(go.Scatter(
            x=d["M1"] + np.random.default_rng(1).uniform(-.06, .06, len(d)),
            y=d["M2"] + np.random.default_rng(2).uniform(-.06, .06, len(d)),
            mode="markers", marker=dict(size=9, opacity=.6, color="#1f3a5f"),
            hovertemplate="M1 %{x:.2f}<br>M2 %{y:.2f}<extra></extra>"))
        fig.update_layout(xaxis_title="M1 Clareza (1–5)", yaxis_title="M2 Retrabalho (1–5)",
                          height=380, margin=dict(t=20), title=None)
        fig.update_xaxes(range=[.8, 5.2]); fig.update_yaxes(range=[.8, 5.2])
        st.plotly_chart(fig, width="stretch")
        st.caption("Pontos com pequeno deslocamento aleatório (jitter) para mostrar sobreposições.")
    if not pd.isna(r12["rho"]):
        sentido = "negativa" if r12["rho"] < 0 else "positiva"
        sig = p_adj[0] < an.ALPHA
        st.markdown(
            f"**Leitura:** na amostra, a associação entre clareza e retrabalho percebidos é "
            f"{sentido} e de efeito **{an.magnitude_r(r12['rho'])}** "
            f"(rho = {f2(r12['rho'])}), {'estatisticamente significativa' if sig else 'sem significância estatística'} "
            f"após Holm (p {'< 0,001' if p_adj[0] < .001 else '= ' + fmt_p(p_adj[0])}). "
            f"{'Os dados são compatíveis com H1.' if sig and r12['rho'] < 0 else 'H1 não é sustentada por estes dados.'} "
            "Isso não indica causa: quem sofre mais retrabalho pode avaliar a clareza pior.")

    # ---------- QP2
    st.divider()
    st.header("QP2: clareza e retrabalho variam com a experiência? (exploratória)")
    st.caption("Kruskal-Wallis por faixa (ε²), post-hoc de Dunn com Holm; Mann-Whitney "
               "estagiário × demais (correlação bisserial por postos); qui-quadrado (V de "
               "Cramér) de porte e forma de trabalho × nível de retrabalho. Família QP2 "
               "corrigida por Holm.")
    tests = []
    kw = {}
    for y in ("M1", "M2"):
        if "Faixa" in df:
            kw[y] = an.kruskal(df, y, "Faixa")
            tests.append({"Teste": f"Kruskal-Wallis {y} × faixa de experiência", "n": kw[y]["n"],
                          "Estatística": f"H = {f2(kw[y]['H'])}", "p": kw[y]["p"],
                          "Efeito": f"ε² = {f2(kw[y]['eps2'], 3)} ({an.magnitude_eps2(kw[y]['eps2'])})"})
    for y in ("M1", "M2"):
        if "Funcao2" in df:
            mw = an.mann_whitney(df, y, "Funcao2")
            tests.append({"Teste": f"Mann-Whitney {y}: estagiários (n={mw['n1']}) × demais (n={mw['n2']})",
                          "n": mw["n1"] + mw["n2"], "Estatística": f"U = {f2(mw['U'], 1)}",
                          "p": mw["p"],
                          "Efeito": f"r bisserial = {f2(mw['rbis'])} ({an.magnitude_r(mw['rbis'])})"})
    df_q = df.copy()
    df_q["Nível de retrabalho"] = np.where(df_q["M2"] >= 3, "M2 ≥ 3 (às vezes ou mais)",
                                           "M2 < 3")
    df_q.loc[df_q["M2"].isna(), "Nível de retrabalho"] = np.nan
    tabs_chi = {}
    for seg, nome in (("P3", "Porte"), ("P4", "Forma de trabalho")):
        if seg in df_q:
            q = an.qui_quadrado(df_q.dropna(subset=[seg, "Nível de retrabalho"]), seg,
                                "Nível de retrabalho")
            tabs_chi[nome] = q["tab"]
            tests.append({"Teste": f"{q['teste']}: {nome} × nível de retrabalho", "n": q["n"],
                          "Estatística": f"χ² = {f2(q['chi2'])}", "p": q["p"],
                          "Efeito": f"V = {f2(q['V'])} ({an.magnitude_r(q['V'])})"})
    if tests:
        t = pd.DataFrame(tests)
        t["p Holm"] = an.holm(t["p"])
        t["Margem de erro"] = t["n"].map(lambda k: f"±{f2(an.margem_erro(k) * 100, 1)} p.p.")
        t["p bruto"] = t["p"].map(fmt_p)
        t["p Holm"] = t["p Holm"].map(fmt_p)
        st.dataframe(t[["Teste", "n", "Estatística", "p bruto", "p Holm", "Efeito",
                        "Margem de erro"]], hide_index=True, width="stretch")

    if "Faixa" in df and n:
        cols = st.columns(2)
        for box, y, nome in zip(cols, ("M1", "M2"), ("M1 Clareza", "M2 Retrabalho")):
            fig = go.Figure()
            for fx in an.FAIXAS_EXP:
                v = df.loc[df["Faixa"] == fx, y].dropna()
                fig.add_box(y=v, name=f"{fx} (n={len(v)})", boxpoints="all", jitter=.4,
                            marker_color="#1f3a5f", line_color="#1f3a5f")
            fig.update_layout(title=f"{nome} por faixa de experiência", showlegend=False,
                              height=380, yaxis=dict(range=[.8, 5.2], title=nome))
            box.plotly_chart(fig, width="stretch")
        with st.expander("Post-hoc de Dunn (Holm)"):
            for y in ("M1", "M2"):
                st.markdown(f"**{y}**")
                dn = an.dunn(df, y, "Faixa")
                if len(dn):
                    dn["z"] = dn["z"].map(f2)
                    dn["p bruto"] = dn["p bruto"].map(fmt_p)
                    dn["p Holm"] = dn["p Holm"].map(fmt_p)
                st.dataframe(dn, hide_index=True, width="stretch")
    if tabs_chi:
        with st.expander("Tabelas de contingência"):
            for nome, tb in tabs_chi.items():
                st.markdown(f"**{nome}**")
                st.dataframe(tb, width="stretch")
    st.caption("QP2 é exploratória (sem direção pré-definida): resultados servem para gerar "
               "hipóteses, não para confirmá-las.")

    # ---------- QP3
    st.divider()
    st.header("QP3: quais práticas de esclarecimento são mais usadas?")
    st.caption("Proporção de respondentes que marcaram cada prática (múltipla escolha), "
               "com intervalo de Wilson 95%. Descritiva, sem hipótese. As respostas abertas "
               "(E2) não são exibidas; a análise temática é feita fora do dashboard.")
    pr = an.praticas(df) if any(c.startswith("E1::") for c in df.columns) else pd.DataFrame()
    if len(pr) and pr["n"].iloc[0] > 0:
        pr = pr[pr["k"] > 0].sort_values("Proporção")
        fig = go.Figure(go.Bar(
            y=pr["Prática"], x=pr["Proporção"] * 100, orientation="h", marker_color="#1f3a5f",
            error_x=dict(type="data", symmetric=False,
                         array=(pr["IC sup"] - pr["Proporção"]) * 100,
                         arrayminus=(pr["Proporção"] - pr["IC inf"]) * 100, color="#555"),
            text=[f"{p * 100:.0f}%" for p in pr["Proporção"]], textposition="outside",
            hovertemplate="%{y}: %{x:.1f}%<extra></extra>"))
        fig.update_layout(xaxis=dict(title="% dos respondentes", range=[0, 110]),
                          height=120 + 45 * len(pr), margin=dict(t=20, l=10))
        st.plotly_chart(fig, width="stretch")
        tbl = pr.sort_values("Proporção", ascending=False).copy()
        tbl["%"] = (tbl["Proporção"] * 100).map(lambda v: f2(v, 1))
        tbl["IC 95% (Wilson)"] = [f"[{f2(lo * 100, 1)}; {f2(hi * 100, 1)}]" for lo, hi in
                                  zip(tbl["IC inf"], tbl["IC sup"])]
        st.dataframe(tbl[["Prática", "k", "n", "%", "IC 95% (Wilson)"]], hide_index=True,
                     width="stretch")
    else:
        st.write("Sem respostas para E1 no segmento.")

    # ---------- E2 (aberta) codificada
    st.subheader("Respostas abertas (E2): qual prática mais ajuda a evitar retrabalho?")
    if "E2::_respondeu" in df and df["E2::_respondeu"].any():
        base = df[df["E2::_respondeu"]]
        ne2 = len(base)
        cods = [c for c in df.columns if c.startswith("E2::") and c != "E2::_respondeu"]
        linhas = []
        for c in cods:
            k = int(base[c].sum())
            lo, hi = an.wilson(k, ne2)
            linhas.append({"Código": c[4:], "k": k, "p": k / ne2, "lo": lo, "hi": hi})
        e2 = pd.DataFrame(linhas)
        e2 = e2[(e2["k"] > 0) | (e2["Código"] != "Não codificada")].sort_values("p")
        fig = go.Figure(go.Bar(
            y=e2["Código"], x=e2["p"] * 100, orientation="h", marker_color="#7a9cc6",
            error_x=dict(type="data", symmetric=False, array=(e2["hi"] - e2["p"]) * 100,
                         arrayminus=(e2["p"] - e2["lo"]) * 100, color="#555"),
            text=[f"{k} ({v * 100:.0f}%)" for k, v in zip(e2["k"], e2["p"])],
            textposition="outside"))
        fig.update_layout(xaxis=dict(title=f"% das {ne2} respostas abertas", range=[0, 100]),
                          height=120 + 42 * len(e2), margin=dict(t=20, l=10))
        st.plotly_chart(fig, width="stretch")
        st.caption(f"{ne2} de {len(df)} respondentes válidos escreveram algo em E2 (pergunta "
                   "opcional). Codificação multi-rótulo: uma resposta pode citar mais de uma "
                   "prática, então os percentuais somam mais de 100%. IC 95% de Wilson.")
        with st.expander("Livro de códigos (regra de codificação)"):
            st.markdown("Codificação por dicionário de termos aplicada ao texto normalizado "
                        "(minúsculas, sem acento). O texto das respostas não é exibido, para "
                        "preservar o anonimato.")
            st.dataframe(pd.DataFrame({"Código": list(an.CODIGOS_E2),
                                       "Termos que ativam o código": [", ".join(t) for t in
                                                                      an.CODIGOS_E2.values()]}),
                         hide_index=True, width="stretch")
    else:
        st.info("A coluna E2 não está presente neste CSV (na versão publicada ela é removida "
                "por LGPD).")

# ================================================================ 5 Explorar
with abas[4]:
    st.warning("**Análise exploratória livre.** Os testes desta aba NÃO são os do pré-registro "
               "e não têm correção para múltiplas comparações: servem para entender os dados "
               "e preparar a defesa, não para tirar conclusões. As respostas oficiais estão em "
               "\"Questões de pesquisa\".")
    if n < 4:
        st.write("Poucas respostas no filtro atual.")
    else:
        st.subheader("Associação entre duas variáveis")
        c1, c2, c3 = st.columns(3)
        nomes_v = list(VARIAVEIS)
        vx = c1.selectbox("Eixo X", nomes_v, index=nomes_v.index("M1 Clareza") if "M1 Clareza" in nomes_v else 0)
        vy = c2.selectbox("Eixo Y", nomes_v, index=nomes_v.index("M2 Retrabalho") if "M2 Retrabalho" in nomes_v else 1)
        cor = c3.selectbox("Colorir por", ["(nenhum)", *SEGMENTOS])
        x, y = VARIAVEIS[vx], VARIAVEIS[vy]
        cols_sel = list(dict.fromkeys([x, y] + ([SEGMENTOS[cor]] if cor != "(nenhum)" else [])))
        d = df[cols_sel].dropna(subset=[x, y]).copy()
        rng = np.random.default_rng(7)
        jit = lambda s: s + (rng.uniform(-.07, .07, len(s)) if s.name != "P2" else 0)
        fig = go.Figure()
        grupos = ([("Todos", d)] if cor == "(nenhum)" else
                  [(str(g), dg) for g, dg in d.groupby(SEGMENTOS[cor], observed=True)])
        paleta = ["#1f3a5f", "#c0392b", "#27ae60", "#8e44ad", "#d68910", "#7f8c8d"]
        for k, (g, dg) in enumerate(grupos):
            fig.add_scatter(x=jit(dg[x]), y=jit(dg[y]), mode="markers", name=f"{g} (n={len(dg)})",
                            marker=dict(size=9, opacity=.65, color=paleta[k % len(paleta)]))
        if len(d) > 3 and d[x].nunique() > 1:
            b, a0 = np.polyfit(d[x], d[y], 1)
            xs = np.linspace(d[x].min(), d[x].max(), 20)
            fig.add_scatter(x=xs, y=a0 + b * xs, mode="lines", name="tendência linear",
                            line=dict(color="#333", dash="dash"))
        fig.update_layout(xaxis_title=vx, yaxis_title=vy, height=430,
                          margin=dict(t=20), legend=dict(orientation="h", y=-0.2))
        st.plotly_chart(fig, width="stretch")
        r = an.spearman_boot(d[x], d[y], n_boot=1000)
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("rho de Spearman", f2(r["rho"]))
        k2.metric("IC 95% (bootstrap)", f"[{f2(r['ic'][0])}; {f2(r['ic'][1])}]")
        k3.metric("p (sem correção)", fmt_p(r["p"]))
        k4.metric("Efeito", an.magnitude_r(r["rho"]))
        if cor != "(nenhum)":
            linhas = []
            for g, dg in grupos:
                rg = an.spearman_boot(dg[x], dg[y], n_boot=500)
                linhas.append({"Grupo": g, "n": rg["n"], "rho": f2(rg["rho"]),
                               "IC 95%": f"[{f2(rg['ic'][0])}; {f2(rg['ic'][1])}]",
                               "p": fmt_p(rg["p"])})
            st.dataframe(pd.DataFrame(linhas), hide_index=True, width="stretch")

        st.divider()
        st.subheader("Comparação entre grupos")
        c1, c2 = st.columns(2)
        vv = c1.selectbox("Variável", nomes_v, key="cmp_v")
        sg = c2.selectbox("Agrupar por", list(SEGMENTOS), key="cmp_g")
        v, g = VARIAVEIS[vv], SEGMENTOS[sg]
        d = df[[v, g]].dropna()
        cats = (list(d[g].cat.categories) if hasattr(d[g], "cat") else sorted(d[g].unique()))
        fig = go.Figure()
        for cat in cats:
            vals = d.loc[d[g] == cat, v]
            if len(vals):
                fig.add_box(y=vals, name=f"{cat} (n={len(vals)})", boxpoints="all", jitter=.4,
                            boxmean=True, marker_color="#1f3a5f", line_color="#1f3a5f")
        fig.update_layout(showlegend=False, height=400, yaxis_title=vv, margin=dict(t=20))
        st.plotly_chart(fig, width="stretch")
        if d[g].nunique() == 2:
            a_, b_ = [c for c in cats if (d[g] == c).any()]
            mw = an.mann_whitney(d, v, g, a=a_, b=b_)
            st.markdown(f"Mann-Whitney: U = {f2(mw['U'], 1)}, p = {fmt_p(mw['p'])}, "
                        f"r bisserial = {f2(mw['rbis'])} ({an.magnitude_r(mw['rbis'])}).")
        else:
            kw = an.kruskal(d, v, g)
            st.markdown(f"Kruskal-Wallis: H = {f2(kw['H'])}, p = {fmt_p(kw['p'])}, "
                        f"ε² = {f2(kw['eps2'], 3)} ({an.magnitude_eps2(kw['eps2'])}).")

        st.divider()
        st.subheader("Práticas (E1) por segmento")
        if any(c.startswith("E1::") for c in df.columns):
            sg2 = st.selectbox("Segmento", list(SEGMENTOS), key="e1_g")
            gcol = SEGMENTOS[sg2]
            prat_cols = [c for c in df.columns if c.startswith("E1::") and df[c].any()]
            base = df[df["E1_respondeu"]].dropna(subset=[gcol])
            tab = base.groupby(gcol, observed=True)[prat_cols].mean() * 100
            tab.columns = [c[4:] for c in tab.columns]
            fig = go.Figure(go.Heatmap(z=tab.values, x=tab.columns,
                                       y=[f"{i} (n={(base[gcol] == i).sum()})" for i in tab.index],
                                       colorscale="Blues", zmin=0, zmax=100,
                                       text=tab.round(0).values, texttemplate="%{text}%"))
            fig.update_layout(height=120 + 50 * len(tab), margin=dict(t=10, l=10, r=10, b=10))
            st.plotly_chart(fig, width="stretch")
            st.caption("% de cada grupo que marcou a prática.")

# ================================================================ 6 Metodologia
with abas[5]:
    st.header("Metodologia")
    st.markdown(f"""
- **Instrumento:** Google Forms, português, ~5 min. Escalas de 5 pontos (concordância e frequência) tratadas como ordinais; índices = média dos itens.
- **Limpeza (em código, a partir do CSV bruto):** critérios (a), (b), (e), (f) do protocolo; (c) e (d) não aplicáveis: o formulário publicado não incluiu a pergunta de atenção A1 e o Forms não exporta duração (ver desvios).
- **Straight-lining:** mesma resposta nos 9 itens de escala (C1–C4, D1–D2, R1–R3).
- **Duplicata:** linhas idênticas em todas as colunas exceto o carimbo de data/hora (mantém a primeira).
- **Testes:** Spearman + bootstrap (QP1); Kruskal-Wallis + Dunn, Mann-Whitney, qui-quadrado/Fisher (QP2); Wilson (QP3). α = 0,05, Holm por família, p bruto e ajustado.
- **Margem de erro:** e = 1,96·√(0,25/n), recalculada com os filtros.
- **Respostas abertas (E2):** codificadas por dicionário de termos (livro de códigos na aba Questões de pesquisa), multi-rótulo; o dashboard mostra só contagens por código, nunca o texto.\n- **Privacidade:** o dashboard mostra apenas agregados.
""")
    st.header("Desvios em relação ao protocolo")
    if DESVIOS.exists():
        st.markdown(DESVIOS.read_text(encoding="utf-8"))
    else:
        st.warning("desvios.md não encontrado.")
    with st.expander("Mapeamento de colunas do CSV (diagnóstico)"):
        st.dataframe(pd.DataFrame({"Código": list(mapa.colunas),
                                   "Coluna no CSV": list(mapa.colunas.values())}),
                     hide_index=True, width="stretch")
        if mapa.nao_mapeadas:
            st.write("Colunas ignoradas:", mapa.nao_mapeadas)


# ================================================================ 7 Questionário
QUESTIONARIO = [
    ("Triagem", "—", "Você concorda em participar da pesquisa? (termo de consentimento)", "Nominal (sim/não)", "Critério (a)"),
    ("Triagem", "—", "Você tem mais de 18 anos?", "Nominal (sim/não)", "Critério (b)"),
    ("Triagem", "—", "Você atua ou atuou nos últimos 12 meses como desenvolvedor(a) ou estagiário(a)?", "Nominal (sim/não)", "Critério (b)"),
    ("P1", "QP2", "Função atual ou mais recente", "Nominal", "Segmento"),
    ("P2", "QP2", "Anos de experiência com desenvolvimento", "Ordinal (5 faixas)", "Segmento"),
    ("P3", "QP2", "Porte da organização", "Ordinal (4 faixas)", "Segmento"),
    ("P4", "QP2", "Forma de trabalho predominante", "Nominal", "Segmento"),
    ("C1", "QP1, QP2", "As tarefas chegam com critérios de aceitação claros.", "Ordinal (concordância 1–5)", "M1 Clareza"),
    ("C2", "QP1, QP2", "As informações recebidas antes de iniciar uma tarefa são completas.", "Ordinal (concordância 1–5)", "M1 Clareza"),
    ("C3", "QP1, QP2", "Entendo o que deve ser entregue sem precisar de muitas explicações adicionais.", "Ordinal (concordância 1–5)", "M1 Clareza"),
    ("C4", "QP1, QP2", "Os requisitos são descritos sem ambiguidades.", "Ordinal (concordância 1–5)", "M1 Clareza"),
    ("D1", "QP1", "Nos últimos 3 meses, com que frequência você teve dúvidas sobre o que deveria implementar?", "Ordinal (frequência 1–5)", "M3 Instabilidade"),
    ("D2", "QP1", "Nos últimos 3 meses, com que frequência os requisitos mudaram durante uma tarefa?", "Ordinal (frequência 1–5)", "M3 Instabilidade"),
    ("R1", "QP1, QP2", "Nos últimos 3 meses, com que frequência precisou refazer parte de uma tarefa por problemas nos requisitos?", "Ordinal (frequência 1–5)", "M2 Retrabalho"),
    ("R2", "QP1, QP2", "Nos últimos 3 meses, com que frequência teve retrabalho por interpretações diferentes de um requisito?", "Ordinal (frequência 1–5)", "M2 Retrabalho"),
    ("R3", "QP1, QP2", "O retrabalho relacionado aos requisitos consome parte significativa do meu tempo.", "Ordinal (frequência 1–5)", "M2 Retrabalho"),
    ("E1", "QP3", "Quais práticas são usadas na sua equipe para esclarecer requisitos?", "Nominal (múltipla escolha)", "Proporção por prática"),
    ("E2", "QP3", "Qual prática mais ajuda a evitar retrabalho? Por quê?", "Aberta (texto)", "Codificação temática"),
]
with abas[6]:
    st.header("Questionário aplicado")
    st.markdown("**Questões de pesquisa**\n\n"
                "- **QP1:** a clareza percebida dos requisitos está associada ao retrabalho percebido?\n"
                "- **QP2:** clareza e retrabalho variam com a experiência, a função, o porte e a forma de trabalho?\n"
                "- **QP3:** quais práticas de esclarecimento de requisitos são mais usadas?")
    st.dataframe(pd.DataFrame(QUESTIONARIO, columns=["Código", "QP", "Pergunta", "Escala", "Métrica"]),
                 hide_index=True, width="stretch", height=680)
    st.caption("Construtos com mais de um item: Clareza (4), Retrabalho (3), Instabilidade (2). "
               "A pergunta de atenção prevista no protocolo não foi incluída no formulário (ver desvios).")

# ================================================================ 8 Evidências
with abas[7]:
    st.header("Evidências da coleta: divulgação")
    st.markdown("Capturas das mensagens de divulgação do link do formulário "
                "(forms.gle/VEYSWsRxNvFKTAE17). Nomes de participantes dos grupos foram "
                "desfocados para não expor possíveis respondentes.")
    EVID = BASE / "evidencias"
    legendas = {
        "1_whatsapp_forceone.png": "WhatsApp: grupo de equipe de empresa (08:11)",
        "2_whatsapp_ti.png": "WhatsApp: grupo de TI",
        "3_discord_fab_software.png": "Discord: comunidade de desenvolvimento, 23/11/2026 16:29",
        "4_whatsapp_pinguins.png": "WhatsApp: grupo de amigos da área (10:38)",
    }
    if EVID.exists():
        imgs = sorted(EVID.glob("*.png"))
        largas = [i for i in imgs if i.name.startswith(("1_", "3_"))]
        altas = [i for i in imgs if i not in largas]
        for im in largas:
            st.image(str(im), caption=legendas.get(im.name, im.name), width="stretch")
        cols = st.columns(len(altas) or 1)
        for c, im in zip(cols, altas):
            c.image(str(im), caption=legendas.get(im.name, im.name), width="stretch")
    st.markdown("**Canais:** WhatsApp (3 grupos) e Discord (1 comunidade), com pedido de repasse "
                "(bola de neve). Na apresentação, o painel do Google Forms é aberto ao vivo.")

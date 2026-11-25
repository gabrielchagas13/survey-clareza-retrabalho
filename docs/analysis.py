"""Limpeza e análise do survey "Clareza dos requisitos e retrabalho percebido".

Fonte da verdade: protocolo.pdf (pré-registro). Todo número exibido no dashboard
sai daqui, calculado a partir do CSV bruto exportado do Google Forms.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy import stats

# ---------------------------------------------------------------------------
# Constantes do protocolo
# ---------------------------------------------------------------------------
CLAREZA = ["C1", "C2", "C3", "C4"]          # M1
RETRABALHO = ["R1", "R2", "R3"]             # M2
INSTABILIDADE = ["D1", "D2"]                # M3
ITENS_ESCALA = CLAREZA + INSTABILIDADE + RETRABALHO  # usados no straight-lining
ITENS_CONCORDANCIA = CLAREZA
# No formulário publicado R3 usa a escala de frequência (desvio, ver desvios.md).
ITENS_FREQUENCIA = INSTABILIDADE + ["R1", "R2", "R3"]

# No formulário publicado, "Concordo parcialmente" é o ponto 4 da escala.
# O protocolo dizia "(3)": desvio registrado em desvios.md.
A1_ESPERADO = 4

# Faixas exatamente como no formulário publicado (desvio, ver desvios.md).
FAIXAS_EXP = ["<1 ano", "1–2 anos", "3–6 anos", "7–9 anos", "≥10 anos"]
ALPHA = 0.05
N_BOOT = 2000
SEED = 2026

PRATICAS = {
    "Critérios de aceitação": "criterios de aceitacao",
    "Protótipos ou wireframes": "prototipos",
    "Histórias de usuário": "historias de usuario",
    "Conversa direta com PO/cliente": "comunicacao direta",
    "Documentação dos requisitos": "documentacao",
    "Refinamento": "refinamento",
    "Nenhuma": "nenhuma das praticas",
}

LIKERT_TXT = {
    "discordo totalmente": 1, "discordo parcialmente": 2,
    "nem concordo nem discordo": 3, "concordo parcialmente": 4,
    "concordo totalmente": 5,
}
FREQ_TXT = {"nunca": 1, "raramente": 2, "as vezes": 3, "frequentemente": 4, "sempre": 5}
ROTULOS_CONC = ["Discordo totalmente", "Discordo parcialmente", "Neutro",
                "Concordo parcialmente", "Concordo totalmente"]
ROTULOS_FREQ = ["Nunca", "Raramente", "Às vezes", "Frequentemente", "Sempre"]

ENUNCIADOS = {
    "C1": "C1 Critérios de aceitação claros",
    "C2": "C2 Informações completas antes da tarefa",
    "C3": "C3 Entendo sem muitas explicações",
    "C4": "C4 Requisitos sem ambiguidades",
    "D1": "D1 Dúvidas sobre o que implementar",
    "D2": "D2 Requisitos mudam durante a tarefa",
    "R1": "R1 Refazer parte de tarefa já feita",
    "R2": "R2 Retrabalho por interpretações diferentes",
    "R3": "R3 Retrabalho consome parte significativa do tempo",
}

# Identificação das colunas: primeiro pelo código no início do título
# ("C1 - ..."), depois por trechos do enunciado (sem acento, minúsculo).
PADROES = [
    ("TS", ["carimbo de data", "timestamp"]),
    ("TERMO", ["concorda em participar"]),
    ("IDADE", ["18 anos"]),
    ("POP", ["ultimos 12 meses"]),
    ("A1", ["mostrar atencao", "marque concordo"]),
    ("C1", ["criterios de aceitacao claros"]),
    ("C2", ["informacoes recebidas antes"]),
    ("C3", ["sem precisar de muitas explicacoes"]),
    ("C4", ["sem ambiguidade"]),
    ("D1", ["duvidas sobre o que"]),
    ("D2", ["requisitos mudaram", "mudancas nos requisitos"]),
    ("R1", ["refazer parte"]),
    ("R2", ["interpretacoes diferentes"]),
    ("R3", ["consome"]),
    ("E2", ["mais ajuda a evitar"]),
    ("E1", ["praticas sao utilizadas", "praticas usadas", "praticas utilizadas"]),
    ("P2", ["anos de experiencia"]),
    ("P1", ["funcao"]),
    ("P3", ["porte"]),
    ("P4", ["forma de trabalho"]),
]
# A1 não consta no formulário publicado (desvio): não é obrigatória.
OBRIGATORIAS = ["TERMO", "IDADE", "POP", *CLAREZA, *INSTABILIDADE, *RETRABALHO,
                "E1", "P1", "P2", "P3", "P4"]


def norm(txt) -> str:
    s = unicodedata.normalize("NFKD", str(txt)).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s.lower()).strip()


# ---------------------------------------------------------------------------
# Leitura e mapeamento
# ---------------------------------------------------------------------------
@dataclass
class Mapeamento:
    colunas: dict[str, str] = field(default_factory=dict)   # código -> coluna do CSV
    faltando: list[str] = field(default_factory=list)
    nao_mapeadas: list[str] = field(default_factory=list)
    duplicadas: dict[str, list[str]] = field(default_factory=dict)


def mapear_colunas(cols: list[str]) -> Mapeamento:
    m = Mapeamento()
    candidatos: dict[str, list[str]] = {}
    for col in cols:
        n = norm(col)
        cod = None
        hit = re.match(r"^\s*([pcadre]\d)\b", n)
        if hit:
            cod = hit.group(1).upper()
        else:
            for c, chaves in PADROES:
                if any(k in n for k in chaves):
                    cod = c
                    break
        if cod:
            candidatos.setdefault(cod, []).append(col)
        else:
            m.nao_mapeadas.append(col)
    for cod, lst in candidatos.items():
        m.colunas[cod] = lst[0]
        if len(lst) > 1:
            m.duplicadas[cod] = lst
    m.faltando = [c for c in OBRIGATORIAS if c not in m.colunas]
    return m


def _escala(v, tabela: dict[str, int]) -> float:
    if pd.isna(v) or str(v).strip() == "":
        return np.nan
    s = norm(v)
    d = re.match(r"^([1-5])\b", s)
    if d:
        return float(d.group(1))
    for k, val in tabela.items():
        if k in s:
            return float(val)
    return np.nan


def _sim(v) -> bool:
    return norm(v).startswith("sim")


def _anos(v) -> float:
    if pd.isna(v):
        return np.nan
    s = norm(v).replace(",", ".")
    # Categorias do formulário -> ponto médio da faixa (variável ordinal).
    if "menos de" in s or s.startswith("<"):
        return 0.5
    if "mais de 10" in s or s.startswith(">"):
        return 10.0
    tabela = {"1-2": 1.5, "3-6": 4.5, "7-9": 8.0}
    for k, val in tabela.items():
        if s.replace(" ", "").startswith(k):
            return val
    hit = re.search(r"\d+(\.\d+)?", s)
    return float(hit.group()) if hit else np.nan


def faixa_exp(anos: float):
    if pd.isna(anos):
        return np.nan
    if anos < 1:
        return FAIXAS_EXP[0]
    if anos < 3:
        return FAIXAS_EXP[1]
    if anos < 7:
        return FAIXAS_EXP[2]
    if anos < 10:
        return FAIXAS_EXP[3]
    return FAIXAS_EXP[4]


def carregar(caminho) -> tuple[pd.DataFrame, Mapeamento]:
    bruto = pd.read_csv(caminho, dtype=str, keep_default_na=False, na_values=[""])
    bruto.columns = [c.strip() for c in bruto.columns]
    return bruto, mapear_colunas(list(bruto.columns))


def preparar(bruto: pd.DataFrame, m: Mapeamento) -> pd.DataFrame:
    """Converte as colunas em códigos numéricos/categóricos. Não descarta nada."""
    c = m.colunas
    df = pd.DataFrame(index=bruto.index)
    if "TS" in c:
        ts = bruto[c["TS"]].str.replace(r"\s*GMT[+-]?\d*\s*$", "", regex=True)
        df["TS"] = pd.to_datetime(ts, format="%Y/%m/%d %I:%M:%S %p", errors="coerce")
        if df["TS"].isna().all():
            df["TS"] = pd.to_datetime(ts, dayfirst=True, errors="coerce", format="mixed")
    for cod in ("TERMO", "IDADE", "POP"):
        df[cod] = bruto[c[cod]].map(_sim) if cod in c else True
    for cod in ITENS_CONCORDANCIA + ["A1"]:
        if cod in c:
            df[cod] = bruto[c[cod]].map(lambda v: _escala(v, LIKERT_TXT))
    for cod in ITENS_FREQUENCIA:
        if cod in c:
            df[cod] = bruto[c[cod]].map(lambda v: _escala(v, FREQ_TXT))
    if "P1" in c:
        df["P1"] = bruto[c["P1"]].str.strip()
        df["Funcao2"] = np.where(bruto[c["P1"]].map(norm).str.contains("estagi"),
                                 "Estagiário", "Demais")
        df.loc[bruto[c["P1"]].isna(), "Funcao2"] = np.nan
    if "P2" in c:
        df["P2"] = bruto[c["P2"]].map(_anos)
        df["Faixa"] = pd.Categorical(df["P2"].map(faixa_exp), categories=FAIXAS_EXP,
                                     ordered=True)
    for cod in ("P3", "P4"):
        if cod in c:
            df[cod] = bruto[c[cod]].str.strip()
    if "E1" in c:
        e1 = bruto[c["E1"]].fillna("").map(norm)
        for rotulo, chave in PRATICAS.items():
            df[f"E1::{rotulo}"] = e1.str.contains(chave, regex=False)
        restante = e1.copy()
        for chave in PRATICAS.values():
            restante = restante.str.replace(r"[^,;]*" + re.escape(chave) + r"[^,;]*", "",
                                            regex=True)
        df["E1::Outra"] = restante.str.replace(r"[\s,;]", "", regex=True).str.len() > 0
        df["E1_respondeu"] = e1.str.len() > 0
    # E2 (aberta) não é carregada: não é exibida nem exportada pelo dashboard.
    df["M1"] = df[[i for i in CLAREZA if i in df]].mean(axis=1, skipna=False)
    df["M2"] = df[[i for i in RETRABALHO if i in df]].mean(axis=1, skipna=False)
    df["M3"] = df[[i for i in INSTABILIDADE if i in df]].mean(axis=1, skipna=False)
    return df


MOTIVOS = {
    "a": "(a) Não aceitou o termo",
    "b": "(b) Fora da população-alvo",
    "c": "(c) Errou a pergunta de atenção (A1)",
    "e": "(e) Straight-lining nos itens de escala",
    "f": "(f) Duplicata",
}


def aplicar_descartes(bruto: pd.DataFrame, df: pd.DataFrame, m: Mapeamento) -> pd.Series:
    """Retorna o motivo de descarte por linha (NaN = válida). Ordem: a, b, c, e, f;
    cada resposta recebe só o primeiro motivo em que cai."""
    motivo = pd.Series(np.nan, index=df.index, dtype=object)

    def marcar(mask, cod):
        motivo.loc[mask & motivo.isna()] = MOTIVOS[cod]

    marcar(~df["TERMO"].astype(bool), "a")
    marcar(~(df["IDADE"].astype(bool) & df["POP"].astype(bool)), "b")
    if "A1" in df:
        marcar(df["A1"] != A1_ESPERADO, "c")
    itens = [i for i in ITENS_ESCALA if i in df]
    if itens:
        bloco = df[itens]
        marcar(bloco.notna().all(axis=1) & (bloco.nunique(axis=1) == 1), "e")
    cols_resp = [c for c in bruto.columns if c != m.colunas.get("TS")]
    marcar(bruto[cols_resp].duplicated(keep="first"), "f")
    return motivo


# ---------------------------------------------------------------------------
# Estatística
# ---------------------------------------------------------------------------
def margem_erro(n: int, p: float = 0.5, z: float = 1.96) -> float:
    return z * np.sqrt(p * (1 - p) / n) if n > 0 else np.nan


def cronbach(df: pd.DataFrame, itens: list[str]) -> tuple[float, int]:
    x = df[itens].dropna()
    k, n = len(itens), len(x)
    if n < 3 or k < 2:
        return np.nan, n
    var_tot = x.sum(axis=1).var(ddof=1)
    if var_tot == 0:
        return np.nan, n
    return k / (k - 1) * (1 - x.var(ddof=1).sum() / var_tot), n


def holm(pvals) -> np.ndarray:
    p = np.asarray(pvals, dtype=float)
    out = np.full_like(p, np.nan)
    ok = ~np.isnan(p)
    pv = p[ok]
    m = len(pv)
    if m == 0:
        return out
    ordem = np.argsort(pv)
    adj = np.empty(m)
    acum = 0.0
    for r, i in enumerate(ordem):
        acum = max(acum, (m - r) * pv[i])
        adj[i] = min(1.0, acum)
    out[ok] = adj
    return out


def spearman_boot(x, y, n_boot=N_BOOT, seed=SEED) -> dict:
    d = pd.DataFrame({"x": x, "y": y}).dropna()
    n = len(d)
    if n < 4:
        return {"n": n, "rho": np.nan, "p": np.nan, "ic": (np.nan, np.nan)}
    res = stats.spearmanr(d["x"], d["y"])
    rng = np.random.default_rng(seed)
    xs, ys = d["x"].to_numpy(), d["y"].to_numpy()
    boots = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, n)
        r = stats.spearmanr(xs[idx], ys[idx]).statistic
        if not np.isnan(r):
            boots.append(r)
    ic = tuple(np.percentile(boots, [2.5, 97.5])) if boots else (np.nan, np.nan)
    return {"n": n, "rho": float(res.statistic), "p": float(res.pvalue), "ic": ic}


def magnitude_r(r: float) -> str:
    a = abs(r)
    if np.isnan(a):
        return "—"
    return "desprezível" if a < .1 else "pequeno" if a < .3 else "médio" if a < .5 else "grande"


def magnitude_eps2(e: float) -> str:
    if np.isnan(e):
        return "—"
    return "desprezível" if e < .01 else "pequeno" if e < .08 else "médio" if e < .26 else "grande"


def kruskal(df: pd.DataFrame, y: str, g: str) -> dict:
    d = df[[y, g]].dropna()
    grupos = {k: v[y].to_numpy() for k, v in d.groupby(g, observed=True) if len(v) > 0}
    n = len(d)
    if len(grupos) < 2 or n < 4:
        return {"n": n, "H": np.nan, "p": np.nan, "eps2": np.nan, "k": len(grupos)}
    try:
        H, p = stats.kruskal(*grupos.values())
    except ValueError:  # todos os valores iguais
        return {"n": n, "H": np.nan, "p": np.nan, "eps2": np.nan, "k": len(grupos)}
    return {"n": n, "H": H, "p": p, "eps2": H / (n - 1), "k": len(grupos)}


def dunn(df: pd.DataFrame, y: str, g: str) -> pd.DataFrame:
    """Post-hoc de Dunn (com correção de empates), p ajustado por Holm."""
    d = df[[y, g]].dropna().copy()
    d["r"] = stats.rankdata(d[y])
    n = len(d)
    _, cont = np.unique(d[y], return_counts=True)
    corr_emp = (cont ** 3 - cont).sum() / (12 * (n - 1)) if n > 1 else 0
    grp = d.groupby(g, observed=True)["r"].agg(["mean", "size"])
    linhas = []
    nomes = list(grp.index)
    for i in range(len(nomes)):
        for j in range(i + 1, len(nomes)):
            a, b = grp.loc[nomes[i]], grp.loc[nomes[j]]
            se = np.sqrt((n * (n + 1) / 12 - corr_emp) * (1 / a["size"] + 1 / b["size"]))
            z = (a["mean"] - b["mean"]) / se if se > 0 else np.nan
            p = 2 * stats.norm.sf(abs(z)) if not np.isnan(z) else np.nan
            linhas.append({"Comparação": f"{nomes[i]} × {nomes[j]}", "z": z, "p bruto": p})
    out = pd.DataFrame(linhas)
    if len(out):
        out["p Holm"] = holm(out["p bruto"])
    return out


def mann_whitney(df: pd.DataFrame, y: str, g: str, a="Estagiário", b="Demais") -> dict:
    d = df[[y, g]].dropna()
    xa, xb = d.loc[d[g] == a, y], d.loc[d[g] == b, y]
    n1, n2 = len(xa), len(xb)
    if n1 < 2 or n2 < 2:
        return {"n1": n1, "n2": n2, "U": np.nan, "p": np.nan, "rbis": np.nan}
    U, p = stats.mannwhitneyu(xa, xb, alternative="two-sided")
    rbis = 2 * U / (n1 * n2) - 1  # > 0: estagiários com valores maiores
    return {"n1": n1, "n2": n2, "U": U, "p": p, "rbis": rbis,
            "med1": xa.median(), "med2": xb.median()}


def qui_quadrado(df: pd.DataFrame, linha: str, coluna: str, seed=SEED) -> dict:
    tab = pd.crosstab(df[linha], df[coluna])
    tab = tab.loc[tab.sum(axis=1) > 0, tab.sum(axis=0) > 0]
    n = int(tab.to_numpy().sum())
    if tab.shape[0] < 2 or tab.shape[1] < 2:
        return {"tab": tab, "n": n, "teste": "—", "p": np.nan, "V": np.nan, "chi2": np.nan}
    chi2, p, _, esp = stats.chi2_contingency(tab, correction=False)
    V = np.sqrt(chi2 / (n * (min(tab.shape) - 1)))
    teste = "Qui-quadrado"
    if (esp < 5).any():
        if tab.shape == (2, 2):
            p = stats.fisher_exact(tab).pvalue
            teste = "Exato de Fisher (esperadas < 5)"
        else:
            # Tabela maior que 2×2: Fisher exato não está disponível no scipy;
            # usa-se o p de permutação (Monte Carlo) do qui-quadrado. Ver desvios.md.
            rng = np.random.default_rng(seed)
            x = np.repeat(np.arange(tab.shape[0]), tab.sum(axis=1))
            yv = np.concatenate([np.repeat(np.arange(tab.shape[1]), r) for r in tab.to_numpy()])
            obs = chi2
            maior = 0
            B = 5000
            for _ in range(B):
                t = pd.crosstab(x, rng.permutation(yv)).to_numpy()
                e = t.sum(1, keepdims=True) * t.sum(0, keepdims=True) / n
                maior += ((t - e) ** 2 / e).sum() >= obs - 1e-12
            p = (maior + 1) / (B + 1)
            teste = "Qui-quadrado por permutação (esperadas < 5)"
    return {"tab": tab, "n": n, "teste": teste, "p": p, "V": V, "chi2": chi2}


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return np.nan, np.nan
    ph = k / n
    den = 1 + z ** 2 / n
    centro = (ph + z ** 2 / (2 * n)) / den
    meia = z * np.sqrt(ph * (1 - ph) / n + z ** 2 / (4 * n ** 2)) / den
    return centro - meia, centro + meia


def praticas(df: pd.DataFrame) -> pd.DataFrame:
    base = df[df.get("E1_respondeu", pd.Series(False, index=df.index))]
    n = len(base)
    linhas = []
    for col in [c for c in df.columns if c.startswith("E1::")]:
        k = int(base[col].sum())
        lo, hi = wilson(k, n)
        linhas.append({"Prática": col[4:], "k": k, "n": n,
                       "Proporção": k / n if n else np.nan, "IC inf": lo, "IC sup": hi})
    return pd.DataFrame(linhas).sort_values("Proporção", ascending=False)


def distribuicao(df: pd.DataFrame, item: str) -> pd.Series:
    s = df[item].dropna()
    return s.value_counts(normalize=True).reindex([1, 2, 3, 4, 5], fill_value=0.0) * 100


def resumo_iqr(s: pd.Series) -> str:
    s = s.dropna()
    if s.empty:
        return "—"
    return f"{s.median():.2f} (IIQ {s.quantile(.25):.2f}–{s.quantile(.75):.2f})"

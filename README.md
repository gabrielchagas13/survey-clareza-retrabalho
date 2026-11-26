# Dashboard: clareza dos requisitos e retrabalho percebido

Dashboard do survey pré-registrado (ver `protocolo.pdf`). Lê sempre a exportação **bruta** do Google Forms e faz a limpeza, os descartes e as análises em código.

## Como rodar

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
# depois arraste o CSV do Forms na barra lateral
# (ou salve-o em dados/respostas_brutas.csv para abrir direto)
```

Para apontar para outro CSV: `SURVEY_CSV=caminho/arquivo.csv streamlit run app.py`.

## Arquivos

| Arquivo | Conteúdo |
|---|---|
| `analysis.py` | Mapeamento de colunas, conversão das escalas, descartes, testes estatísticos |
| `app.py` | Interface Streamlit (5 abas + filtros) |
| `desvios.md` | Desvios em relação ao protocolo (aparece na aba "Metodologia e desvios") |
| `dados/respostas_brutas.csv` | Exportação bruta (não versionar em repositório público) |

## Colunas do CSV

Cada coluna é identificada pelo código no início do título (`C1 - ...`) ou, se não houver código, por trechos do enunciado (ver `PADROES` em `analysis.py`). Colunas obrigatórias que não forem encontradas aparecem num aviso no topo do dashboard; a aba de metodologia mostra o mapeamento usado.

## Abas

1. **Perfil da amostra**: progresso até a meta, funil de descartes, evolução diária da coleta, recebidas, válidas, descartes por critério, perfil, índices, faltantes.
2. **Itens Likert**: barras divergentes, com opção de separar por segmento.
3. **Confiabilidade**: alfa de Cronbach, α se o item for removido, correlação item-resto e mapa de correlações.
4. **Questões de pesquisa**: QP1 (Spearman + bootstrap), QP2 (Kruskal-Wallis, Dunn, Mann-Whitney, qui-quadrado), QP3 (proporções com Wilson). Todas com p bruto, p Holm, efeito e margem de erro.
5. **Explorar**: dispersão com eixos escolhidos, comparação entre grupos e práticas por segmento (exploratório, sem correção).
6. **Metodologia e desvios**.

A resposta aberta E2 não é lida pelo dashboard.

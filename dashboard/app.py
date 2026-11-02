"""Dashboard de indicadores de mercado. Executar com `streamlit run dashboard/app.py` (a partir da raiz).

Só lê as tabelas da gold (data/processed/gold); nenhum cálculo do pipeline é refeito aqui. As métricas que
dependem do período escolhido (base 100, simulação de R$ 1.000.000,00 e drawdown máximo) são calculadas
no dashboard, a partir das séries diárias da gold.
"""

import os
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

GOLD_DIR = Path(os.environ.get("GOLD_DIR", Path(__file__).resolve().parent.parent / "data" / "processed" / "gold"))

NAMES = {"ibovespa": "Ibovespa", "cdi": "CDI", "dolar_ptax": "Dólar PTAX", "ipca": "IPCA"}
# Cores por série em ordem fixa (paleta de referência validada para pares adjacentes, claro e escuro).
COLORS = {
    "light": {"ibovespa": "#2a78d6", "cdi": "#eb6834", "dolar_ptax": "#1baf7a", "ipca": "#eda100"},
    "dark": {"ibovespa": "#3987e5", "cdi": "#d95926", "dolar_ptax": "#199e70", "ipca": "#c98500"},
}
CHROME = {
    "light": {"text": "#0b0b0b", "secondary": "#52514e", "muted": "#898781", "grid": "#e1e0d9", "axis": "#c3c2b7"},
    "dark": {"text": "#f0efec", "secondary": "#c3c2b7", "muted": "#898781", "grid": "#2c2c2a", "axis": "#383835"},
}
WINDOWS = {"mes": "Mês", "ano": "Ano", "12m": "12M", "24m": "24M", "36m": "36M"}
MONTHS_PT = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
DATE_COLUMNS = ["data", "data_inicio", "data_fim", "mes_referencia", "data_ultimo_dado", "data_referencia", "mes_referencia_ipca"]
SIMULATED_AMOUNT = 1_000_000
# Texto do "?" de cada cartão do Resumo: o que é o indicador, quem calcula, como é usado e o que o número mostra.
HELP = {
    "cdi": (
        "Taxa média dos empréstimos de um dia entre bancos, calculada pela B3 a cada dia útil. "
        "Acompanha de perto a Selic, cerca de 0,10 p.p. abaixo da meta.\n\n"
        "É a principal referência da renda fixa pós-fixada: CDBs, LCIs, LCAs e fundos são comparados em \"% do CDI\".\n\n"
        "Aqui: taxa diária do último dia útil, anualizada em 252 dias úteis."
    ),
    "ipca": (
        "Inflação oficial do Brasil, calculada pelo IBGE todo mês a partir dos preços de uma cesta de produtos e "
        "serviços consumidos por famílias com renda de 1 a 40 salários mínimos.\n\n"
        "Mostra a perda do poder de compra e é a base da rentabilidade real (o ganho acima da inflação).\n\n"
        "Aqui: inflação acumulada nos 12 últimos meses divulgados."
    ),
    "dolar_ptax": (
        "Taxa de câmbio de referência do Banco Central, em reais por dólar. É a média de quatro consultas que o "
        "Banco Central faz aos grandes bancos ao longo do dia, no mercado atacadista; não é o dólar turismo.\n\n"
        "Serve de referência para contratos, proteção cambial (hedge) e investimentos internacionais.\n\n"
        "Aqui: PTAX de venda, com a variação em relação ao dia útil anterior."
    ),
    "ibovespa": (
        "Principal índice de ações da B3: uma carteira teórica das ações mais negociadas, com peso pelo valor de "
        "mercado das ações em circulação (free float) e rebalanceada a cada 4 meses.\n\n"
        "É um índice de retorno total: considera o reinvestimento dos dividendos. "
        "É a referência para ações e fundos de ações.\n\n"
        "Aqui: fechamento em pontos, com a variação em relação ao pregão anterior."
    ),
}


# Formatação no padrão brasileiro

def fmt_num(value, decimals=2) -> str:
    if pd.isna(value):
        return "—"
    return f"{value:,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_pct(value, decimals=2, signed=True) -> str:
    if pd.isna(value):
        return "—"
    return f"{'+' if signed and value > 0 else ''}{fmt_num(value, decimals)}%"


def fmt_pp(value) -> str:
    return "—" if pd.isna(value) else f"{'+' if value > 0 else ''}{fmt_num(value)} p.p."


def fmt_brl(value, decimals=2) -> str:
    return "—" if pd.isna(value) else f"R$ {fmt_num(value, decimals)}"


def md(text: str) -> str:
    """Escapa o `$` para textos em markdown (dois `$` viram fórmula LaTeX no Streamlit, ex.: "R$ 1 e R$ 2")."""
    return text.replace("$", r"\$")


def fmt_date(value) -> str:
    return "—" if pd.isna(value) else f"{value:%d/%m/%Y}"


def fmt_month(value) -> str:
    return "—" if pd.isna(value) else f"{MONTHS_PT[value.month - 1]}/{value.year}"


# Dados

@st.cache_data(ttl=600)
def _read(path: str, modified: float) -> pd.DataFrame:  # `modified` invalida o cache quando o arquivo muda
    df = pd.read_parquet(path)
    for column in DATE_COLUMNS:
        if column in df.columns:
            df[column] = pd.to_datetime(df[column])
    return df


def gold(name: str) -> pd.DataFrame:
    path = GOLD_DIR / f"{name}.parquet"
    return _read(str(path), path.stat().st_mtime)


def asof_row(df: pd.DataFrame, column: str, when: pd.Timestamp) -> int:
    """Posição do último dado até `when` (ou a primeira linha, se `when` for anterior ao histórico)."""
    position = df[column].searchsorted(when, side="right") - 1
    return max(int(position), 0)


def period_slice(df: pd.DataFrame, column: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """Linhas do período, começando no valor-base (último dado até a data inicial)."""
    base = df[column].iloc[asof_row(df, column, start)]
    return df[(df[column] >= base) & (df[column] <= end)]


def ipca_index(ipca_mensal: pd.DataFrame) -> pd.DataFrame:
    """Número-índice do IPCA no fim de cada mês, com base 100 no fim do mês anterior ao histórico."""
    dates = ipca_mensal["mes_referencia"] + pd.offsets.MonthEnd(0)
    index = 100 * (1 + ipca_mensal["ipca_mensal_pct"] / 100).cumprod()
    start = pd.DataFrame({"data": [ipca_mensal["mes_referencia"].iloc[0] - pd.Timedelta(days=1)], "valor": [100.0]})
    return pd.concat([start, pd.DataFrame({"data": dates, "valor": index})], ignore_index=True)


def max_drawdown(values: pd.Series) -> float:
    return ((values / values.cummax() - 1) * 100).min()


# Gráficos

def style(fig: go.Figure, mode: str, y_suffix: str = "", height: int = 380, legend: bool = True) -> go.Figure:
    chrome = CHROME[mode]
    fig.update_layout(
        height=height,
        margin=dict(l=8, r=16, t=36 if legend else 12, b=8, autoexpand=True),
        hovermode="x unified",
        separators=",.",
        showlegend=legend,
        legend=dict(orientation="h", x=0, y=1.02, yanchor="bottom", font=dict(color=chrome["secondary"])),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="system-ui, -apple-system, Segoe UI, sans-serif", color=chrome["secondary"], size=13),
        hoverlabel=dict(font_size=13),
    )
    # automargin: a margem cresce para caber os rótulos dos eixos (sem isso, ficam cortados).
    fig.update_xaxes(showgrid=False, linecolor=chrome["axis"], tickformat="%m/%Y", hoverformat="%d/%m/%Y",
                     tickfont=dict(color=chrome["muted"]), automargin=True)
    fig.update_yaxes(gridcolor=chrome["grid"], gridwidth=1, zeroline=False, ticksuffix=y_suffix,
                     tickfont=dict(color=chrome["muted"]), automargin=True)
    return fig


def line(x, y, name, color, width=2, hover="%{y:,.2f}") -> go.Scatter:
    return go.Scatter(x=x, y=y, name=name, mode="lines", line=dict(color=color, width=width),
                      hovertemplate=f"{hover}<extra>{name}</extra>")


def show(fig: go.Figure) -> None:
    st.plotly_chart(fig, theme=None, config={"displaylogo": False, "modeBarButtonsToRemove": ["lasso2d", "select2d"]})


def data_view(df: pd.DataFrame, label: str = "Ver dados") -> None:
    with st.expander(label):
        st.dataframe(df, hide_index=True)


def price_chart(df: pd.DataFrame, column: str, name: str, color: str, mode: str, prefix: str = "") -> go.Figure:
    """Preço com as médias móveis de 50 e 200 pregões (médias em tons neutros, para destacar o preço)."""
    chrome = CHROME[mode]
    hover = f"{prefix}%{{y:,.2f}}"
    fig = go.Figure([
        line(df["data"], df["mm200"], "Média de 200", chrome["muted"], 1.5, hover),
        line(df["data"], df["mm50"], "Média de 50", chrome["secondary"], 1.5, hover),
        line(df["data"], df[column], name, color, 2, hover),
    ])
    fig = style(fig, mode)
    fig.update_yaxes(tickformat=",.0f" if df[column].max() >= 1000 else ",.2f", tickprefix=prefix)
    return fig


# Página

st.set_page_config(page_title="Indicadores de Mercado", layout="wide")
MODE = "dark" if st.context.theme.type == "dark" else "light"
COLOR = COLORS[MODE]

st.title("Indicadores de Mercado")

if not GOLD_DIR.exists():
    st.error(f"Dados não encontrados em `{GOLD_DIR}`. Rode o pipeline (`python -m src.main_daily`) antes do dashboard.")
    st.stop()

cdi = gold("cdi_diario")
ptax = gold("dolar_ptax_diario")
ibov = gold("ibovespa_diario")
ibov_usd = gold("ibovespa_usd_diario")
rent = gold("rentabilidade")
annual = gold("retorno_anual")
ipca = gold("ipca_mensal")
last_data = gold("ultimo_dado").set_index("serie")
real_rates = gold("juros_reais").iloc[0]
ipca_idx = ipca_index(ipca)

# Resumo: não depende do filtro de período. Seção expansível, aberta por padrão.
with st.expander("**Resumo**", expanded=True):
    cols = st.columns(4)
    cols[0].metric("CDI anualizado", fmt_pct(real_rates["cdi_anualizado_pct"], signed=False), border=True,
                   help=HELP["cdi"])
    cols[0].caption(f"Dado de {fmt_date(real_rates['data_referencia'])}")
    cols[1].metric("IPCA 12 meses", fmt_pct(real_rates["ipca_12m_pct"], signed=False), border=True,
                   help=HELP["ipca"])
    cols[1].caption(f"Até {fmt_month(real_rates['mes_referencia_ipca'])}")
    last_ptax, last_ibov = ptax.iloc[-1], ibov.iloc[-1]
    cols[2].metric("Dólar PTAX venda", fmt_brl(last_ptax["ptax_venda"], 4), fmt_pct(last_ptax["var_d1_pct"]),
                   delta_color="off", border=True, help=HELP["dolar_ptax"])
    cols[2].caption(f"Dado de {fmt_date(last_ptax['data'])}")
    cols[3].metric("Ibovespa", f"{fmt_num(last_ibov['fechamento'], 0)} pts", fmt_pct(last_ibov["var_d1_pct"]),
                   border=True, help=HELP["ibovespa"])
    cols[3].caption(f"Fechamento de {fmt_date(last_ibov['data'])}")

    st.subheader("Rentabilidade nominal")
    nominal = rent[rent["tipo"] == "nominal"]
    table = nominal.pivot(index="serie", columns="janela", values="retorno_pct").reindex(NAMES).reindex(columns=WINDOWS)
    table = table.map(fmt_pct).rename(index=NAMES, columns=WINDOWS)
    until = nominal.groupby("serie")["data_fim"].max().reindex(NAMES)
    table.insert(0, "Até", [fmt_month(d) if s == "ipca" else fmt_date(d) for s, d in until.items()])
    st.dataframe(table.rename_axis("Indicador").reset_index(), hide_index=True)
    st.caption("Mês e ano: desde o último dado do mês ou do ano anterior. O IPCA vai até o último mês divulgado.")

    st.subheader("Rentabilidade real (descontada a inflação)")
    real = rent[rent["tipo"] == "real"]
    real_table = real.pivot(index="serie", columns="janela", values="retorno_pct").reindex(["cdi", "ibovespa"])
    real_table = real_table.reindex(columns=WINDOWS).map(fmt_pct).rename(index=NAMES, columns=WINDOWS)
    st.dataframe(real_table.rename_axis("Indicador").reset_index(), hide_index=True)
    st.caption(f"Alinhada aos meses do último IPCA divulgado: até {fmt_month(real_rates['mes_referencia_ipca'])}.")

    st.subheader("Data do último dado")
    units = {"cdi": lambda v: f"{fmt_num(v, 6)}% ao dia", "ipca": lambda v: fmt_pct(v, signed=False) + " no mês",
             "dolar_ptax": lambda v: fmt_brl(v, 4), "ibovespa": lambda v: f"{fmt_num(v, 0)} pts"}
    st.dataframe(pd.DataFrame([
        {"Indicador": NAMES[s],
         "Data": fmt_month(last_data.loc[s, "data_ultimo_dado"]) if s == "ipca" else fmt_date(last_data.loc[s, "data_ultimo_dado"]),
         "Último valor": units[s](last_data.loc[s, "ultimo_valor"])}
        for s in NAMES if s in last_data.index
    ]), hide_index=True)


st.divider()
st.header("Análise por período")
# Filtro de período: vale só para as abas abaixo (gráficos, base 100, simulação e drawdown máximo).
last_day = max(cdi["data"].max(), ptax["data"].max(), ibov["data"].max())
first_day = min(cdi["data"].min(), ptax["data"].min(), ibov["data"].min())
presets = {
    "12M": last_day - pd.DateOffset(months=12),
    "24M": last_day - pd.DateOffset(months=24),
    "36M": last_day - pd.DateOffset(months=36),
    "No ano": pd.Timestamp(last_day.year - 1, 12, 31),
    "Tudo": first_day,
}
filter_col, custom_col = st.columns([3, 2])
with filter_col:
    choice = st.segmented_control("Período", [*presets, "Personalizado"], default="12M") or "12M"
if choice == "Personalizado":
    with custom_col:
        picked = st.date_input("Datas", value=(presets["12M"].date(), last_day.date()),
                               min_value=first_day.date(), max_value=last_day.date(), format="DD/MM/YYYY")
    start = pd.Timestamp(picked[0])
    end = pd.Timestamp(picked[1]) if len(picked) == 2 else last_day
else:
    start, end = presets[choice], last_day
st.caption(f"Período: {fmt_date(start)} a {fmt_date(end)}. Cada série usa o último dado disponível até a data inicial.")

tab_compare, tab_rates, tab_stocks, tab_fx = st.tabs(["Comparação", "Juros e inflação", "Bolsa", "Câmbio"])

# Comparação
with tab_compare:
    st.subheader("Comparação em base 100")
    st.caption("Todas as séries partem de 100 no início do período.")
    levels = {
        "ibovespa": ibov[["data", "fechamento"]].rename(columns={"fechamento": "valor"}),
        "cdi": cdi[["data", "indice"]].rename(columns={"indice": "valor"}),
        "dolar_ptax": ptax[["data", "ptax_venda"]].rename(columns={"ptax_venda": "valor"}),
        "ipca": ipca_idx,
    }
    fig, rebased, returns = go.Figure(), {}, {}
    for serie, df in levels.items():
        sliced = period_slice(df, "data", start, end)
        rebased[serie] = sliced.assign(valor=sliced["valor"] / sliced["valor"].iloc[0] * 100)
        # O valor-base vale para a data inicial do período: todas as linhas partem do mesmo ponto.
        rebased[serie].iloc[0, rebased[serie].columns.get_loc("data")] = max(start, sliced["data"].iloc[0])
        returns[serie] = rebased[serie]["valor"].iloc[-1] - 100
        fig.add_trace(line(rebased[serie]["data"], rebased[serie]["valor"], NAMES[serie], COLOR[serie]))
    show(style(fig, MODE))
    data_view(pd.concat([df.assign(Indicador=NAMES[s]) for s, df in rebased.items()])
              .pivot_table(index="data", columns="Indicador", values="valor").reset_index())

    st.subheader(md(f"Simulação: {fmt_brl(SIMULATED_AMOUNT, 0)} aplicados no início do período"))
    cols = st.columns(4)
    for col, serie in zip(cols, ["ibovespa", "cdi", "dolar_ptax"]):
        col.metric(NAMES[serie], fmt_brl(SIMULATED_AMOUNT * (1 + returns[serie] / 100), 0),
                   fmt_pct(returns[serie]), border=True, delta_color="off" if serie == "dolar_ptax" else "normal")
    # O IPCA não é um investimento: mostra quanto o valor inicial vale hoje, corrigido pela inflação.
    cols[3].metric("Corrigido pelo IPCA", fmt_brl(SIMULATED_AMOUNT * (1 + returns["ipca"] / 100), 0),
                   fmt_pct(returns["ipca"]), delta_color="off", border=True,
                   help="Quanto o valor inicial precisaria valer hoje só para manter o poder de compra.")
    st.caption(md(f"Retorno bruto, sem impostos nem custos. \"Corrigido pelo IPCA\": os {fmt_brl(SIMULATED_AMOUNT, 0)} "
                  "do início do período equivalem a esse valor hoje; um investimento abaixo dele perdeu poder de compra."))

    st.subheader("Retorno por ano")
    fig = go.Figure()
    for serie in NAMES:
        rows = annual[annual["serie"] == serie]
        fig.add_trace(go.Bar(x=rows["ano"].astype(str), y=rows["retorno_pct"], name=NAMES[serie],
                             marker=dict(color=COLOR[serie], cornerradius=4),
                             hovertemplate="%{y:,.2f}%<extra>" + NAMES[serie] + "</extra>"))
    fig = style(fig, MODE, "%")
    fig.update_layout(barmode="group", bargap=0.25, bargroupgap=0.08, hovermode="x unified")
    fig.update_xaxes(tickformat=None, hoverformat=None, type="category")
    show(fig)
    current = annual.loc[~annual["ano_completo"], "ano"]
    if not current.empty:
        st.caption(f"{current.iloc[0]}: ano em andamento, até o último dado disponível.")
    data_view(annual.assign(serie=annual["serie"].map(NAMES), retorno_pct=annual["retorno_pct"].map(fmt_pct))
              .pivot(index="ano", columns="serie", values="retorno_pct").reset_index())

# Juros e inflação
with tab_rates:
    ipca_last = ipca.dropna(subset=["ipca_12m_pct"]).iloc[-1] if ipca["ipca_12m_pct"].notna().any() else ipca.iloc[-1]
    cdi_real_12m = rent.query("serie == 'cdi' and tipo == 'real' and janela == '12m'")["retorno_pct"]
    cols = st.columns(4)
    cols[0].metric("Spread de juros reais", fmt_pct(real_rates["spread_juros_reais_pct"], signed=False), border=True,
                   help="(1 + CDI anualizado) ÷ (1 + IPCA 12M) − 1. É o juro real observado, não o esperado pelo mercado.")
    cols[1].metric("Ganho real do CDI em 12M", fmt_pct(cdi_real_12m.iloc[0] if len(cdi_real_12m) else float("nan")),
                   border=True, help="(1 + CDI) ÷ (1 + IPCA) − 1 nos mesmos 12 meses do último IPCA divulgado.")
    cols[2].metric(f"IPCA de {fmt_month(ipca.iloc[-1]['mes_referencia'])}", fmt_pct(ipca.iloc[-1]["ipca_mensal_pct"]),
                   border=True)
    cols[3].metric("IPCA do mês anualizado", fmt_pct(ipca.iloc[-1]["ipca_anualizado_mes_pct"]), border=True,
                   help="(1 + IPCA do mês)^12 − 1. Sofre com a sazonalidade: compare sempre com o IPCA 12M.")

    st.subheader("CDI anualizado e IPCA 12 meses")
    cdi_period = period_slice(cdi, "data", start, end)
    ipca_12m = ipca.dropna(subset=["ipca_12m_pct"]).assign(data=lambda d: d["mes_referencia"] + pd.offsets.MonthEnd(0))
    ipca_period = ipca_12m[(ipca_12m["data"] >= start) & (ipca_12m["data"] <= end)]
    fig = go.Figure([
        line(cdi_period["data"], cdi_period["cdi_anualizado_pct"], "CDI anualizado", COLOR["cdi"], hover="%{y:,.2f}%"),
        go.Scatter(x=ipca_period["data"], y=ipca_period["ipca_12m_pct"], name="IPCA 12 meses", mode="lines+markers",
                   line=dict(color=COLOR["ipca"], width=2, shape="hv"), marker=dict(size=8),
                   hovertemplate="%{y:,.2f}%<extra>IPCA 12 meses</extra>"),
    ])
    show(style(fig, MODE, "%"))
    st.caption("A distância entre as duas linhas é o juro real. O IPCA 12M é mensal e fica constante até a próxima divulgação.")
    data_view(ipca_period[["mes_referencia", "ipca_mensal_pct", "ipca_12m_pct", "ipca_anualizado_mes_pct"]]
              .rename(columns={"mes_referencia": "Mês", "ipca_mensal_pct": "IPCA mensal (%)",
                               "ipca_12m_pct": "IPCA 12M (%)", "ipca_anualizado_mes_pct": "IPCA anualizado (%)"}))

    st.subheader("IPCA mensal")
    monthly = ipca[(ipca["mes_referencia"] + pd.offsets.MonthEnd(0) >= start) & (ipca["mes_referencia"] <= end)]
    fig = go.Figure(go.Bar(x=monthly["mes_referencia"], y=monthly["ipca_mensal_pct"], name="IPCA mensal",
                           marker=dict(color=COLOR["ipca"], cornerradius=4), hovertemplate="%{y:,.2f}%<extra></extra>"))
    fig = style(fig, MODE, "%", height=300, legend=False)
    fig.update_xaxes(hoverformat="%m/%Y")
    show(fig)

# Bolsa
with tab_stocks:
    period = period_slice(ibov, "data", start, end)
    last = ibov.iloc[-1]
    cols = st.columns(5)
    cols[0].metric("Ibovespa", f"{fmt_num(last['fechamento'], 0)} pts", fmt_pct(last["var_d1_pct"]), border=True)
    cols[1].metric("Distância da média de 50", fmt_pct(last["dist_mm50_pct"]), border=True,
                   help="Fechamento em relação à média dos últimos 50 pregões.")
    cols[2].metric("Distância da média de 200", fmt_pct(last["dist_mm200_pct"]), border=True,
                   help="Fechamento em relação à média dos últimos 200 pregões.")
    cols[3].metric("Distância da máx. em 5 anos", fmt_pct(last["dist_max_5a_pct"]), border=True,
                   help="Fechamento em relação ao maior fechamento dos últimos 5 anos.")
    cols[4].metric("Drawdown máximo do período", fmt_pct(max_drawdown(period["fechamento"])), border=True,
                   help="Maior queda de um pico até o vale seguinte, dentro do período escolhido.")
    st.caption(f"Faixa de 12 meses: mínima de {fmt_num(last['min_12m'], 0)} pts e máxima de "
               f"{fmt_num(last['max_12m'], 0)} pts. Fechamento de {fmt_date(last['data'])}.")

    st.subheader("Ibovespa e médias móveis")
    show(price_chart(period, "fechamento", "Ibovespa", COLOR["ibovespa"], MODE))
    data_view(period[["data", "fechamento", "mm50", "mm200", "var_d1_pct"]])

    st.subheader("Ibovespa contra o CDI e a inflação")
    ibov_rows = rent[rent["serie"] == "ibovespa"]
    nominal_rows = ibov_rows[ibov_rows["tipo"] == "nominal"].set_index("janela").reindex(WINDOWS)
    real_rows = ibov_rows[ibov_rows["tipo"] == "real"].set_index("janela").reindex(WINDOWS)
    st.dataframe(pd.DataFrame({
        "Janela": list(WINDOWS.values()),
        "Ibovespa": nominal_rows["retorno_pct"].map(fmt_pct).values,
        "Excesso sobre o CDI": nominal_rows["excesso_cdi_pp"].map(fmt_pp).values,
        "% do CDI": nominal_rows["pct_do_cdi"].map(lambda v: "—" if pd.isna(v) else f"{fmt_num(v, 0)}%").values,
        "Retorno real": real_rows["retorno_pct"].map(fmt_pct).values,
    }), hide_index=True)
    st.caption("O Ibovespa é um índice de retorno total (considera o reinvestimento dos dividendos), então a comparação "
               "com o CDI é justa. % do CDI só aparece quando os dois retornos são positivos. O retorno real vai até o "
               "último IPCA divulgado.")

# Câmbio
with tab_fx:
    period = period_slice(ptax, "data", start, end)
    last = ptax.iloc[-1]
    cols = st.columns(4)
    cols[0].metric("Dólar PTAX venda", fmt_brl(last["ptax_venda"], 4), fmt_pct(last["var_d1_pct"]),
                   delta_color="off", border=True)
    cols[1].metric("Distância da média de 50", fmt_pct(last["dist_mm50_pct"]), border=True)
    cols[2].metric("Distância da média de 200", fmt_pct(last["dist_mm200_pct"]), border=True)
    cols[3].metric("Drawdown máximo do período", fmt_pct(max_drawdown(period["ptax_venda"])), border=True,
                   help="Maior queda de um pico até o vale seguinte, dentro do período escolhido.")
    st.caption(md(f"Faixa de 12 meses: mínima de {fmt_brl(last['min_12m'], 4)} e máxima de "
                  f"{fmt_brl(last['max_12m'], 4)}. Dado de {fmt_date(last['data'])}."))

    st.subheader("Dólar PTAX e médias móveis")
    show(price_chart(period, "ptax_venda", "Dólar PTAX", COLOR["dolar_ptax"], MODE, prefix="R$ "))
    data_view(period[["data", "ptax_venda", "mm50", "mm200", "var_d1_pct"]])

    st.subheader("Ibovespa em dólar")
    st.caption("Ibovespa ÷ PTAX da mesma data. Mostra se a bolsa subiu de fato ou só pela desvalorização do real.")
    usd = period_slice(ibov_usd, "data", start, end)
    fig = go.Figure(line(usd["data"], usd["ibovespa_usd"], "Ibovespa em dólar", COLOR["ibovespa"], hover="US$ %{y:,.0f}"))
    fig = style(fig, MODE, legend=False)
    fig.update_yaxes(tickformat=",.0f", tickprefix="US$ ")
    show(fig)
    data_view(usd)


st.divider()
st.caption(
    "Fontes: Banco Central do Brasil (SGS: CDI 12, IPCA 433, PTAX venda 1) e Yahoo Finance (Ibovespa, ^BVSP). "
    "Dados atualizados diariamente pelo pipeline no GitHub Actions. Retornos brutos, sem impostos."
)

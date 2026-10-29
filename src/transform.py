"""Transformação (T): camada silver a partir da bronze e camada gold a partir da silver."""

import json
import logging
from typing import Callable

import pandas as pd

from src import utils

logger = logging.getLogger(__name__)


def _read_raw(serie: str, key: str) -> pd.DataFrame:
    """Junta todos os arquivos bronze da série. Em data repetida, fica o arquivo de ingestão mais recente."""
    frames = []
    # O nome do arquivo termina em YYYYMMDD: a ordem alfabética é a ordem de ingestão.
    for path in sorted((utils.RAW_DIR / serie).glob(f"{serie}_*.json")):
        records = json.loads(path.read_text(encoding="utf-8"))
        if records:
            frames.append(pd.DataFrame(records))
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True).drop_duplicates(subset=key, keep="last")


def _to_number(values: pd.Series) -> pd.Series:
    return pd.to_numeric(values, errors="coerce").astype("float64")


def _drop_invalid(df: pd.DataFrame, serie: str) -> pd.DataFrame:
    """Remove linhas com data ou valor que não puderam ser convertidos."""
    valid = df.dropna()
    if len(valid) < len(df):
        logger.warning("%s: %d registro(s) inválido(s) descartado(s) na silver", serie, len(df) - len(valid))
    return valid


def _cumulative_index(rate_pct: pd.Series) -> pd.Series:
    """Índice base 100 acumulando (1 + taxa/100) até cada período, inclusive."""
    return 100 * (1 + rate_pct / 100).cumprod()


def _sgs_dates(values: pd.Series) -> pd.Series:
    return pd.to_datetime(values, format="%d/%m/%Y", errors="coerce")


def _silver_cdi(raw: pd.DataFrame) -> pd.DataFrame:
    df = pd.DataFrame({"data": _sgs_dates(raw["data"]), "taxa_diaria_pct": _to_number(raw["valor"])})
    df = _drop_invalid(df, "cdi").sort_values("data")
    df["indice"] = _cumulative_index(df["taxa_diaria_pct"])
    return df


def _silver_ipca(raw: pd.DataFrame) -> pd.DataFrame:
    df = pd.DataFrame(
        {"mes_referencia": _sgs_dates(raw["data"]), "variacao_mensal_pct": _to_number(raw["valor"])}
    )
    df = _drop_invalid(df, "ipca").sort_values("mes_referencia")
    df["indice"] = _cumulative_index(df["variacao_mensal_pct"])
    return df


def _silver_dolar_ptax(raw: pd.DataFrame) -> pd.DataFrame:
    df = pd.DataFrame({"data": _sgs_dates(raw["data"]), "ptax_venda": _to_number(raw["valor"])})
    return _drop_invalid(df, "dolar_ptax").sort_values("data")


def _silver_ibovespa(raw: pd.DataFrame) -> pd.DataFrame:
    df = pd.DataFrame(
        {
            "data": pd.to_datetime(raw["Date"], format="%Y-%m-%d", errors="coerce"),
            "fechamento": _to_number(raw["Close"]),
        }
    )
    return _drop_invalid(df, "ibovespa").sort_values("data")


# série → (chave de data na bronze, função que monta a tabela silver)
SILVER_TABLES: dict[str, tuple[str, Callable[[pd.DataFrame], pd.DataFrame]]] = {
    "cdi": ("data", _silver_cdi),
    "ipca": ("data", _silver_ipca),
    "dolar_ptax": ("data", _silver_dolar_ptax),
    "ibovespa": ("Date", _silver_ibovespa),
}


def _save_parquet(df: pd.DataFrame, directory, name: str) -> None:
    """Grava a tabela. Colunas de data viram `date` (sem hora) no parquet."""
    df = df.reset_index(drop=True).copy()
    for column in df.select_dtypes(include="datetime").columns:
        df[column] = df[column].dt.date
    directory.mkdir(parents=True, exist_ok=True)
    df.to_parquet(directory / f"{name}.parquet", index=False)


def build_silver() -> dict[str, pd.DataFrame]:
    """Recalcula todas as tabelas da silver a partir da bronze e grava em data/processed/silver.

    Série sem nenhum dado na bronze é pulada (com aviso no log) e não interrompe as outras.
    """
    tables = {}
    for serie, (key, build) in SILVER_TABLES.items():
        raw = _read_raw(serie, key)
        if raw.empty:
            logger.warning("%s: nenhum dado na bronze; tabela silver não gerada", serie)
            continue
        tables[serie] = build(raw).reset_index(drop=True)
        _save_parquet(tables[serie], utils.SILVER_DIR, serie)
        logger.info("%s: silver com %d linhas", serie, len(tables[serie]))
    return tables


# Gold

TRADING_DAYS_PER_YEAR = 252
MONTHS_PT = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]

# série → (coluna de data, coluna de valor) usada nas variações de período
PERIOD_VALUES = {
    "cdi": ("data", "indice"),
    "ipca": ("mes_referencia", "indice"),
    "dolar_ptax": ("data", "ptax_venda"),
    "ibovespa": ("data", "fechamento"),
}
WINDOWS = {"mes": "Mês", "ano": "Ano", "12m": "12M", "24m": "24M", "36m": "36M"}
REAL_SERIES = ("cdi", "ibovespa")


def _pct(ratio):
    """Razão (final ÷ inicial) → variação em %."""
    return (ratio - 1) * 100


def _month_label(day: pd.Timestamp) -> str:
    return f"{MONTHS_PT[day.month - 1]}/{day.year}"


def _month_end(day: pd.Timestamp) -> pd.Timestamp:
    return day + pd.offsets.MonthEnd(0)


def _window_base(window: str, end: pd.Timestamp) -> pd.Timestamp:
    """Data de referência do início da janela (o valor usado é o último dado até ela)."""
    if window == "mes":
        return end.replace(day=1) - pd.Timedelta(days=1)
    if window == "ano":
        return pd.Timestamp(end.year - 1, 12, 31)
    return end - pd.DateOffset(months=int(window.removesuffix("m")))


def _asof(df: pd.DataFrame, date_col: str, value_col: str, when: pd.Timestamp):
    """Último dado da série até `when`, inclusive: (data, valor) ou None se não houver."""
    eligible = df[df[date_col] <= when]
    if eligible.empty:
        return None
    row = eligible.iloc[-1]
    return row[date_col], row[value_col]


def _period_return(serie: str, df: pd.DataFrame, base: pd.Timestamp, end: pd.Timestamp):
    """(data_inicio, data_fim, retorno_pct) entre o último dado até `base` e o último dado até `end`."""
    date_col, value_col = PERIOD_VALUES[serie]
    start, finish = _asof(df, date_col, value_col, base), _asof(df, date_col, value_col, end)
    if start is None or finish is None:
        return None, None, float("nan")
    return start[0], finish[0], _pct(finish[1] / start[1])


def _trailing(df: pd.DataFrame, column: str, months: int, how: str, partial: bool = False) -> pd.Series:
    """Mínimo ou máximo de `column` na janela [data − `months` meses, data] de cada linha.

    Sem `partial`, linhas sem histórico completo na janela ficam vazias.
    """
    dates, values = df["data"].reset_index(drop=True), df[column].reset_index(drop=True)
    first = dates.iloc[0]
    result = []
    for i, day in enumerate(dates):
        window_start = day - pd.DateOffset(months=months)
        if not partial and window_start < first:
            result.append(float("nan"))
            continue
        start = dates.searchsorted(window_start)
        window = values.iloc[start : i + 1]
        result.append(window.min() if how == "min" else window.max())
    return pd.Series(result, index=df.index)


def _gold_cdi_diario(cdi: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "data": cdi["data"],
            "indice": cdi["indice"],
            "cdi_anualizado_pct": _pct((1 + cdi["taxa_diaria_pct"] / 100) ** TRADING_DAYS_PER_YEAR),
        }
    )


def _gold_price_diario(df: pd.DataFrame, column: str) -> pd.DataFrame:
    """Indicadores diários de uma série de preço (dólar ou Ibovespa), no calendário da própria série."""
    out = df[["data", column]].copy()
    out["var_d1_pct"] = df[column].pct_change() * 100
    out["mm50"] = df[column].rolling(50).mean()  # 50 pregões ou dias úteis, não dias corridos
    out["mm200"] = df[column].rolling(200).mean()
    out["dist_mm50_pct"] = _pct(df[column] / out["mm50"])
    out["dist_mm200_pct"] = _pct(df[column] / out["mm200"])
    out["min_12m"] = _trailing(df, column, 12, "min")
    out["max_12m"] = _trailing(df, column, 12, "max")
    return out


def _gold_ibovespa_diario(ibovespa: pd.DataFrame) -> pd.DataFrame:
    out = _gold_price_diario(ibovespa, "fechamento")
    # Máxima dos últimos 5 anos; no início do histórico, usa o que houver disponível.
    out["dist_max_5a_pct"] = _pct(ibovespa["fechamento"] / _trailing(ibovespa, "fechamento", 60, "max", partial=True))
    return out


def _gold_ibovespa_usd_diario(ibovespa: pd.DataFrame, ptax: pd.DataFrame) -> pd.DataFrame:
    """Só as datas com Ibovespa e PTAX (feriados que não coincidem ficam de fora)."""
    df = ibovespa.rename(columns={"fechamento": "ibovespa"}).merge(ptax, on="data", how="inner")
    df["ibovespa_usd"] = df["ibovespa"] / df["ptax_venda"]
    return df[["data", "ibovespa", "ptax_venda", "ibovespa_usd"]]


def _gold_rentabilidade(silver: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for serie, df in silver.items():
        date_col = PERIOD_VALUES[serie][0]
        end = df[date_col].iloc[-1]
        for window, label in WINDOWS.items():
            start, finish, ret = _period_return(serie, df, _window_base(window, end), end)
            until = _month_label(end) if serie == "ipca" else f"{end:%d/%m/%Y}"
            rows.append({"serie": serie, "janela": window, "tipo": "nominal", "data_inicio": start,
                         "data_fim": finish, "rotulo": f"{label} até {until}", "retorno_pct": ret})

    # Retorno real: CDI e Ibovespa cortados nos mesmos meses fechados do último IPCA divulgado.
    if "ipca" in silver:
        ipca = silver["ipca"]
        last_month = ipca["mes_referencia"].iloc[-1]
        end = _month_end(last_month)
        for serie in REAL_SERIES:
            if serie not in silver:
                continue
            for window, label in WINDOWS.items():
                base = _window_base(window, end)
                start, finish, nominal = _period_return(serie, silver[serie], base, end)
                _, _, inflation = _period_return("ipca", ipca, base, end)
                real = _pct((1 + nominal / 100) / (1 + inflation / 100))
                rows.append({"serie": serie, "janela": window, "tipo": "real", "data_inicio": start,
                             "data_fim": finish, "rotulo": f"{label} até {_month_label(last_month)}",
                             "retorno_pct": real})

    df = pd.DataFrame(rows)
    df["excesso_cdi_pp"] = float("nan")
    df["pct_do_cdi"] = float("nan")
    # Ibovespa contra o CDI, na mesma janela das linhas nominais.
    cdi = df[(df["serie"] == "cdi") & (df["tipo"] == "nominal")].set_index("janela")["retorno_pct"]
    for i in df.index[(df["serie"] == "ibovespa") & (df["tipo"] == "nominal")]:
        ibov, cdi_ret = df.at[i, "retorno_pct"], cdi.get(df.at[i, "janela"], float("nan"))
        df.at[i, "excesso_cdi_pp"] = ibov - cdi_ret
        if ibov > 0 and cdi_ret > 0:
            df.at[i, "pct_do_cdi"] = ibov / cdi_ret * 100
    return df


def _gold_retorno_anual(silver: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Retorno de cada ano-calendário. O primeiro ano do histórico, sem fechamento do ano anterior, fica de fora."""
    rows = []
    for serie, df in silver.items():
        date_col = PERIOD_VALUES[serie][0]
        last = df[date_col].iloc[-1]
        for year in range(df[date_col].iloc[0].year, last.year + 1):
            base, end = pd.Timestamp(year - 1, 12, 31), pd.Timestamp(year, 12, 31)
            start, _, ret = _period_return(serie, df, base, end)
            if start is None:
                continue
            rows.append({"serie": serie, "ano": year, "retorno_pct": ret, "ano_completo": year < last.year})
    return pd.DataFrame(rows, columns=["serie", "ano", "retorno_pct", "ano_completo"])


def _gold_ipca_mensal(ipca: pd.DataFrame) -> pd.DataFrame:
    factor = 1 + ipca["variacao_mensal_pct"] / 100
    twelve = factor.rolling(12).apply(lambda f: f.prod(), raw=True)
    # Só vale se as 12 linhas forem 12 meses seguidos.
    consecutive = ipca["mes_referencia"].shift(11) == ipca["mes_referencia"] - pd.DateOffset(months=11)
    return pd.DataFrame(
        {
            "mes_referencia": ipca["mes_referencia"],
            "ipca_mensal_pct": ipca["variacao_mensal_pct"],
            "ipca_12m_pct": _pct(twelve.where(consecutive)),
            "ipca_anualizado_mes_pct": _pct(factor**12),
        }
    )


def _gold_ultimo_dado(silver: dict[str, pd.DataFrame]) -> pd.DataFrame:
    # Valor principal de cada série na silver (unidades diferentes por série).
    main_value = {"cdi": "taxa_diaria_pct", "ipca": "variacao_mensal_pct", "dolar_ptax": "ptax_venda", "ibovespa": "fechamento"}
    rows = []
    for serie, df in silver.items():
        last = df.iloc[-1]
        rows.append({"serie": serie, "data_ultimo_dado": last[PERIOD_VALUES[serie][0]], "ultimo_valor": last[main_value[serie]]})
    return pd.DataFrame(rows)


def _gold_juros_reais(cdi_diario: pd.DataFrame, ipca_mensal: pd.DataFrame) -> pd.DataFrame:
    """CDI anualizado do último dia útil contra o IPCA 12M mais recente.

    Sem 12 meses de IPCA no histórico, os campos do IPCA e o spread ficam vazios.
    """
    cdi = cdi_diario.iloc[-1]
    with_12m = ipca_mensal.dropna(subset=["ipca_12m_pct"])
    month, ipca_12m = (with_12m["mes_referencia"].iloc[-1], with_12m["ipca_12m_pct"].iloc[-1]) if len(with_12m) else (pd.NaT, float("nan"))
    return pd.DataFrame(
        [{
            "data_referencia": cdi["data"],
            "cdi_anualizado_pct": cdi["cdi_anualizado_pct"],
            "mes_referencia_ipca": month,
            "ipca_12m_pct": ipca_12m,
            "spread_juros_reais_pct": _pct((1 + cdi["cdi_anualizado_pct"] / 100) / (1 + ipca_12m / 100)),
        }]
    )


def build_gold(silver: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Recalcula as tabelas da gold a partir da silver e grava em data/processed/gold.

    Tabela que depende de uma série ausente na silver é pulada, com aviso no log.
    """
    tables = {}
    if not silver:
        logger.warning("gold: silver vazia; nenhuma tabela gold gerada")
        return tables

    def add(name: str, needs: tuple[str, ...], build: Callable[[], pd.DataFrame]) -> None:
        missing = [serie for serie in needs if serie not in silver]
        if missing:
            logger.warning("%s: série(s) ausente(s) na silver (%s); tabela gold não gerada", name, ", ".join(missing))
            return
        tables[name] = build().reset_index(drop=True)
        _save_parquet(tables[name], utils.GOLD_DIR, name)
        logger.info("%s: gold com %d linhas", name, len(tables[name]))

    add("cdi_diario", ("cdi",), lambda: _gold_cdi_diario(silver["cdi"]))
    add("dolar_ptax_diario", ("dolar_ptax",), lambda: _gold_price_diario(silver["dolar_ptax"], "ptax_venda"))
    add("ibovespa_diario", ("ibovespa",), lambda: _gold_ibovespa_diario(silver["ibovespa"]))
    add("ibovespa_usd_diario", ("ibovespa", "dolar_ptax"),
        lambda: _gold_ibovespa_usd_diario(silver["ibovespa"], silver["dolar_ptax"]))
    add("rentabilidade", (), lambda: _gold_rentabilidade(silver))
    add("retorno_anual", (), lambda: _gold_retorno_anual(silver))
    add("ipca_mensal", ("ipca",), lambda: _gold_ipca_mensal(silver["ipca"]))
    add("ultimo_dado", (), lambda: _gold_ultimo_dado(silver))
    add("juros_reais", ("cdi", "ipca"), lambda: _gold_juros_reais(tables["cdi_diario"], tables["ipca_mensal"]))
    return tables


def run_transformation() -> None:
    """Etapa de transformação do pipeline, chamada no fim dos fluxos de ingestão.

    Uma falha é registrada no log da execução, sem afetar a bronze já gravada.
    """
    try:
        silver = build_silver()
    except Exception as error:
        logger.error("transformação: falha na silver (%s: %s)", type(error).__name__, error)
        return
    try:
        build_gold(silver)
    except Exception as error:
        logger.error("transformação: falha na gold (%s: %s)", type(error).__name__, error)

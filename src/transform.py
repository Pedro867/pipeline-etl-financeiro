"""Transformação (T): camada silver a partir da bronze."""

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

"""Fluxo diário: CDI, Dólar PTAX venda e Ibovespa. Executar com `python -m src.main_daily`."""

from functools import partial

from src.extract import fetch_sgs, fetch_yfinance, run_extraction

SERIES = {
    "cdi": partial(fetch_sgs, 12),
    "dolar_ptax": partial(fetch_sgs, 1),
    "ibovespa": partial(fetch_yfinance, "^BVSP"),
}

if __name__ == "__main__":
    run_extraction("daily", SERIES)

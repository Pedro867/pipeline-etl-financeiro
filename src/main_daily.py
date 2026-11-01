"""Fluxo diário: CDI, Dólar PTAX venda e Ibovespa. Executar com `python -m src.main_daily`."""

import sys
from functools import partial

from src.extract import fetch_sgs, fetch_yfinance, run_extraction
from src.transform import run_transformation

SERIES = {
    "cdi": partial(fetch_sgs, 12),
    "dolar_ptax": partial(fetch_sgs, 1),
    "ibovespa": partial(fetch_yfinance, "^BVSP"),
}

if __name__ == "__main__":
    failed = run_extraction("daily", SERIES)
    transformed = run_transformation()
    # Código de saída 1 quando houve erro: o GitHub Actions marca a execução como falha e avisa por e-mail.
    sys.exit(1 if failed or not transformed else 0)

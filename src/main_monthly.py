"""Fluxo mensal: IPCA. Executar com `python -m src.main_monthly`."""

from functools import partial

from src.extract import fetch_sgs, run_extraction
from src.transform import run_transformation

SERIES = {
    "ipca": partial(fetch_sgs, 433),
}

if __name__ == "__main__":
    run_extraction("monthly", SERIES, monthly=True)
    run_transformation()

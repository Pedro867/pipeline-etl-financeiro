"""Fluxo mensal: IPCA. Executar com `python -m src.main_monthly`."""

import sys
from functools import partial

from src.extract import fetch_sgs, run_extraction
from src.transform import run_transformation

SERIES = {
    "ipca": partial(fetch_sgs, 433),
}

if __name__ == "__main__":
    failed = run_extraction("monthly", SERIES, monthly=True)
    transformed = run_transformation()
    # Código de saída 1 quando houve erro: o GitHub Actions marca a execução como falha e avisa por e-mail.
    sys.exit(1 if failed or not transformed else 0)

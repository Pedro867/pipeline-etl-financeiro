import logging
import time
from datetime import date, datetime, timedelta
from typing import Callable

import requests
import yfinance as yf
from curl_cffi.requests import exceptions as curl_exceptions
from yfinance.exceptions import YFPricesMissingError, YFRateLimitError

from src.utils import configure_logging, dataframe_to_json, get_start_date, save_json

SGS_URL = (
    "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{code}/dados"
    "?formato=json&dataInicial={start}&dataFinal={end}"
)

MAX_ATTEMPTS = 3  # 1 tentativa + 2 retentativas
RETRY_INTERVAL_SECONDS = 10
TIMEOUT_SECONDS = 60

logger = logging.getLogger(__name__)


class TransientError(Exception):
    """Erro passageiro da fonte (HTTP 5xx ou 429): vale tentar de novo."""


# Só estes erros são retentados. Erros de código ou de configuração sobem direto.
TRANSIENT_ERRORS = (
    TransientError,
    requests.Timeout,
    requests.ConnectionError,
    curl_exceptions.Timeout,  # o yfinance usa curl_cffi, não requests
    curl_exceptions.ConnectionError,
    YFRateLimitError,
)

Fetcher = Callable[[date, date], list[dict]]


def _with_retry(request: Callable[[], list[dict]], source: str) -> list[dict]:
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return request()
        except TRANSIENT_ERRORS as error:
            if attempt == MAX_ATTEMPTS:
                raise
            logger.warning(
                "%s: tentativa %d/%d falhou (%s: %s); nova tentativa em %d s",
                source, attempt, MAX_ATTEMPTS, type(error).__name__, error, RETRY_INTERVAL_SECONDS,
            )
            time.sleep(RETRY_INTERVAL_SECONDS)


def fetch_sgs(code: int, start: date, end: date) -> list[dict]:
    """Busca uma série do SGS (Banco Central) como a API retorna. Retorna [] se o período não tem dado."""
    # O SGS recusa período de um dia só (HTTP 400 "DataFinal deve ser maior que dataInicial").
    # Uma dataFinal futura é aceita e a resposta traz só o que já existe.
    if start == end:
        end += timedelta(days=1)
    url = SGS_URL.format(code=code, start=f"{start:%d/%m/%Y}", end=f"{end:%d/%m/%Y}")

    def request() -> list[dict]:
        response = requests.get(url, timeout=TIMEOUT_SECONDS)
        # "Sem dado" pode vir com HTTP 404 ou com HTTP 200 e o erro no corpo.
        if "Value(s) not found" in response.text:
            return []
        if response.status_code == 429 or response.status_code >= 500:
            raise TransientError(f"HTTP {response.status_code}")
        response.raise_for_status()
        # Código de série inexistente responde HTTP 200 com uma página HTML.
        if "application/json" not in response.headers.get("Content-Type", ""):
            raise ValueError(f"resposta do SGS não é JSON (código {code} existe?)")
        data = response.json()
        if not isinstance(data, list):
            raise ValueError(f"formato inesperado na resposta do SGS: {str(data)[:200]}")
        return data

    return _with_retry(request, f"SGS {code}")


def fetch_yfinance(ticker: str, start: date, end: date) -> list[dict]:
    """Busca o histórico diário de um ticker e converte para JSON. Retorna [] se o período não tem pregão.

    Só traz pregões até o dia anterior a `end`: a linha do dia corrente vem
    provisória (ex.: `Volume = 0`) mesmo depois do fechamento.
    """
    if start >= end:
        return []

    def request() -> list[dict]:
        try:
            df = yf.Ticker(ticker).history(
                start=start,
                end=end,  # `end` do yfinance é exclusivo: vai até o dia anterior
                raise_errors=True,
                timeout=TIMEOUT_SECONDS,
            )
        except YFPricesMissingError:
            return []
        return dataframe_to_json(df)

    return _with_retry(request, ticker)


def run_extraction(flow: str, series: dict[str, Fetcher], monthly: bool = False) -> None:
    """Extrai cada série para a camada bronze. A falha de uma série não interrompe as outras."""
    started_at = datetime.now()
    configure_logging(flow, started_at)
    today = started_at.date()

    for serie, fetch in series.items():
        try:
            start = get_start_date(serie, today, monthly)
            logger.info("%s: buscando de %s a %s", serie, start, today)
            data = fetch(start, today)
        except Exception as error:
            logger.error("%s: falha na extração (%s: %s)", serie, type(error).__name__, error)
            continue

        if not data:
            logger.info("%s: sem dado no período; nenhum arquivo salvo", serie)
            continue

        path = save_json(data, serie, today)
        logger.info("%s: %d registros salvos em %s", serie, len(data), path)

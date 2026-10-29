"""Fixtures compartilhadas. Nenhum teste acessa a internet nem as pastas reais data/ e log/."""

import json
import logging
from datetime import datetime

import pandas as pd
import pytest
import requests

from src import extract, utils


@pytest.fixture(autouse=True)
def isolated_dirs(tmp_path, monkeypatch):
    """Redireciona data/raw, data/processed e log/ para uma pasta temporária."""
    raw_dir = tmp_path / "data" / "raw"
    log_dir = tmp_path / "log"
    monkeypatch.setattr(utils, "RAW_DIR", raw_dir)
    monkeypatch.setattr(utils, "SILVER_DIR", tmp_path / "data" / "processed" / "silver")
    monkeypatch.setattr(utils, "GOLD_DIR", tmp_path / "data" / "processed" / "gold")
    monkeypatch.setattr(utils, "LOG_DIR", log_dir)
    return raw_dir, log_dir


@pytest.fixture
def raw_dir(isolated_dirs):
    return isolated_dirs[0]


@pytest.fixture
def log_dir(isolated_dirs):
    return isolated_dirs[1]


@pytest.fixture(autouse=True)
def reset_src_logger():
    """Fecha e remove os handlers que `configure_logging` coloca no logger `src`."""
    yield
    logger = logging.getLogger("src")
    for handler in logger.handlers:
        handler.close()
    logger.handlers = []


@pytest.fixture
def sleeps(monkeypatch):
    """Substitui o `time.sleep` das retentativas e registra os intervalos pedidos."""
    calls = []
    monkeypatch.setattr(extract.time, "sleep", calls.append)
    return calls


@pytest.fixture
def fixed_now(monkeypatch):
    """Fixa o `datetime.now()` usado por `run_extraction`."""

    def _fix(moment: datetime):
        class FixedDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return moment

        monkeypatch.setattr(extract, "datetime", FixedDatetime)
        return moment

    return _fix


def make_response(status_code=200, body=None, content_type="application/json; charset=utf-8"):
    """Monta um `requests.Response` real, como o SGS devolveria."""
    response = requests.Response()
    response.status_code = status_code
    if body is None:
        body = []
    response._content = (body if isinstance(body, str) else json.dumps(body)).encode("utf-8")
    response.headers["Content-Type"] = content_type
    response.url = "https://api.bcb.gov.br/teste"
    return response


@pytest.fixture
def fake_get(monkeypatch):
    """Substitui `requests.get` por uma fila de respostas (ou exceções) e registra as chamadas."""

    def _install(*outcomes):
        queue = list(outcomes)
        calls = []

        def get(url, **kwargs):
            calls.append({"url": url, **kwargs})
            outcome = queue.pop(0) if len(queue) > 1 else queue[0]
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        monkeypatch.setattr(extract.requests, "get", get)
        return calls

    return _install


def make_history(dates, tz="America/Sao_Paulo"):
    """DataFrame no formato do `Ticker.history` do yfinance."""
    index = pd.DatetimeIndex(pd.to_datetime(dates), name="Date").tz_localize(tz)
    n = len(dates)
    return pd.DataFrame(
        {
            "Open": [100.0 + i for i in range(n)],
            "High": [110.0 + i for i in range(n)],
            "Low": [90.0 + i for i in range(n)],
            "Close": [105.0 + i for i in range(n)],
            "Volume": [1000 + i for i in range(n)],
            "Dividends": [0.0] * n,
            "Stock Splits": [0.0] * n,
        },
        index=index,
    )


@pytest.fixture
def fake_ticker(monkeypatch):
    """Substitui `yf.Ticker` por um objeto cujo `history` segue uma fila de resultados."""

    def _install(*outcomes):
        queue = list(outcomes)
        calls = []

        class FakeTicker:
            def __init__(self, ticker):
                self.ticker = ticker

            def history(self, **kwargs):
                calls.append({"ticker": self.ticker, **kwargs})
                outcome = queue.pop(0) if len(queue) > 1 else queue[0]
                if isinstance(outcome, Exception):
                    raise outcome
                return outcome

        monkeypatch.setattr(extract.yf, "Ticker", FakeTicker)
        return calls

    return _install

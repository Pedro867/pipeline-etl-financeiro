"""Testes de src/extract.py: fetch_sgs, fetch_yfinance, retentativas e run_extraction."""

import json
from datetime import date, datetime

import pytest
import requests
from curl_cffi.requests import exceptions as curl_exceptions
from yfinance.exceptions import YFPricesMissingError, YFRateLimitError, YFTzMissingError

from src import extract
from tests.conftest import make_history, make_response

START, END = date(2026, 10, 1), date(2026, 10, 28)
SGS_DATA = [{"data": "01/10/2026", "valor": "5.0140"}, {"data": "02/10/2026", "valor": "5.0277"}]
NOT_FOUND = {"erro": {"statusCode": 404, "detail": "SGSNegocioException: Value(s) not found"}}
HTML_PAGE = "<html><head><title>Requisição inválida!</title></head></html>"


# _with_retry

def test_retry_returns_on_first_success(sleeps):
    assert extract._with_retry(lambda: [1], "fonte") == [1]
    assert sleeps == []


def test_retry_recovers_after_transient_errors(sleeps):
    outcomes = [requests.Timeout("lento"), requests.ConnectionError("caiu"), [1]]

    def request():
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    assert extract._with_retry(request, "fonte") == [1]
    assert sleeps == [10, 10]


def test_retry_gives_up_after_three_attempts(sleeps):
    calls = []

    def request():
        calls.append(1)
        raise extract.TransientError("HTTP 503")

    with pytest.raises(extract.TransientError):
        extract._with_retry(request, "fonte")
    assert len(calls) == extract.MAX_ATTEMPTS == 3
    assert sleeps == [10, 10]  # não espera depois da última tentativa


def test_retry_does_not_retry_non_transient_errors(sleeps):
    calls = []

    def request():
        calls.append(1)
        raise ValueError("erro de configuração")

    with pytest.raises(ValueError):
        extract._with_retry(request, "fonte")
    assert len(calls) == 1
    assert sleeps == []


def test_retry_logs_warning_for_each_failed_attempt(sleeps, caplog):
    def request():
        raise requests.Timeout("lento")

    with pytest.raises(requests.Timeout):
        extract._with_retry(request, "SGS 12")
    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert len(warnings) == 2
    assert "SGS 12: tentativa 1/3 falhou" in warnings[0].getMessage()


@pytest.mark.parametrize(
    "error",
    [
        extract.TransientError("HTTP 500"),
        requests.Timeout("t"),
        requests.ConnectionError("c"),
        curl_exceptions.Timeout("t"),
        curl_exceptions.ConnectionError("c"),
        YFRateLimitError(),
    ],
)
def test_transient_errors_are_retried(error, sleeps):
    calls = []

    def request():
        calls.append(1)
        raise error

    with pytest.raises(type(error)):
        extract._with_retry(request, "fonte")
    assert len(calls) == 3


# fetch_sgs

def test_fetch_sgs_returns_api_json_as_is(fake_get, sleeps):
    fake_get(make_response(200, SGS_DATA))
    assert extract.fetch_sgs(1, START, END) == SGS_DATA


def test_fetch_sgs_builds_url_and_uses_timeout(fake_get):
    calls = fake_get(make_response(200, SGS_DATA))

    extract.fetch_sgs(433, date(2021, 3, 5), date(2026, 10, 28))

    assert calls[0]["url"] == (
        "https://api.bcb.gov.br/dados/serie/bcdata.sgs.433/dados"
        "?formato=json&dataInicial=05/03/2021&dataFinal=28/10/2026"
    )
    assert calls[0]["timeout"] == 60


def test_fetch_sgs_no_data_returns_empty_list_without_retry(fake_get, sleeps):
    calls = fake_get(make_response(404, NOT_FOUND))

    assert extract.fetch_sgs(1, START, END) == []
    assert len(calls) == 1
    assert sleeps == []


def test_fetch_sgs_no_data_with_status_200_returns_empty_list(fake_get, sleeps):
    # Observado em 29/10/2026 no IPCA: "Value(s) not found" no corpo, mas com HTTP 200.
    calls = fake_get(make_response(200, NOT_FOUND))

    assert extract.fetch_sgs(433, date(2026, 10, 1), date(2026, 10, 29)) == []
    assert len(calls) == 1
    assert sleeps == []


def test_fetch_sgs_single_day_period_sends_next_day_as_end(fake_get):
    # O SGS recusa dataInicial == dataFinal (HTTP 400); a dataFinal vai para o dia seguinte.
    calls = fake_get(make_response(200, [{"data": "29/10/2026", "valor": "5.3744"}]))

    data = extract.fetch_sgs(1, date(2026, 10, 29), date(2026, 10, 29))

    assert data == [{"data": "29/10/2026", "valor": "5.3744"}]
    assert "dataInicial=29/10/2026&dataFinal=30/10/2026" in calls[0]["url"]


def test_fetch_sgs_single_day_at_end_of_year(fake_get):
    calls = fake_get(make_response(200, SGS_DATA))

    extract.fetch_sgs(1, date(2026, 12, 31), date(2026, 12, 31))

    assert "dataInicial=31/12/2026&dataFinal=01/01/2027" in calls[0]["url"]


def test_fetch_sgs_multi_day_period_keeps_end(fake_get):
    calls = fake_get(make_response(200, SGS_DATA))

    extract.fetch_sgs(1, date(2026, 10, 28), date(2026, 10, 29))

    assert "dataInicial=28/10/2026&dataFinal=29/10/2026" in calls[0]["url"]


def test_fetch_sgs_single_day_rejected_message_is_an_error(fake_get, sleeps):
    # Se o SGS ainda assim responder o 400 de período, é erro (não "sem dado") e não é retentado.
    calls = fake_get(make_response(400, {"erro": "DataFinal deve ser maior que dataInicial."}))

    with pytest.raises(requests.HTTPError):
        extract.fetch_sgs(1, date(2026, 10, 28), date(2026, 10, 29))
    assert len(calls) == 1


def test_fetch_sgs_other_404_is_an_error(fake_get, sleeps):
    calls = fake_get(make_response(404, "Not Found", content_type="text/html"))

    with pytest.raises(requests.HTTPError):
        extract.fetch_sgs(1, START, END)
    assert len(calls) == 1


@pytest.mark.parametrize(
    "status, body",
    [
        (400, {"erro": {"statusCode": 400, "detail": "Invalid initial date"}}),
        (406, {"error": "O sistema aceita uma janela de consulta de, no máximo, 10 anos"}),
        (403, {"erro": "proibido"}),
    ],
)
def test_fetch_sgs_client_errors_are_not_retried(fake_get, sleeps, status, body):
    calls = fake_get(make_response(status, body))

    with pytest.raises(requests.HTTPError):
        extract.fetch_sgs(1, START, END)
    assert len(calls) == 1
    assert sleeps == []


def test_fetch_sgs_html_page_with_status_200_is_an_error(fake_get, sleeps):
    # Código de série inexistente: HTTP 200 com página HTML.
    calls = fake_get(make_response(200, HTML_PAGE, content_type="text/html; charset=pt-br"))

    with pytest.raises(ValueError, match="não é JSON"):
        extract.fetch_sgs(99999999, START, END)
    assert len(calls) == 1


def test_fetch_sgs_missing_content_type_is_an_error(fake_get, sleeps):
    response = make_response(200, SGS_DATA)
    del response.headers["Content-Type"]
    fake_get(response)

    with pytest.raises(ValueError, match="não é JSON"):
        extract.fetch_sgs(1, START, END)


def test_fetch_sgs_json_that_is_not_a_list_is_an_error(fake_get, sleeps):
    fake_get(make_response(200, {"inesperado": True}))

    with pytest.raises(ValueError, match="formato inesperado"):
        extract.fetch_sgs(1, START, END)


def test_fetch_sgs_invalid_json_body_is_an_error(fake_get, sleeps):
    fake_get(make_response(200, "[{quebrado"))

    with pytest.raises(requests.JSONDecodeError):
        extract.fetch_sgs(1, START, END)


def test_fetch_sgs_empty_list_with_status_200(fake_get, sleeps):
    fake_get(make_response(200, []))
    assert extract.fetch_sgs(1, START, END) == []


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_fetch_sgs_retries_server_errors_and_rate_limit(fake_get, sleeps, status):
    calls = fake_get(make_response(status, {"erro": "instável"}), make_response(200, SGS_DATA))

    assert extract.fetch_sgs(1, START, END) == SGS_DATA
    assert len(calls) == 2
    assert sleeps == [10]


def test_fetch_sgs_server_error_on_all_attempts(fake_get, sleeps):
    calls = fake_get(make_response(503, {"erro": "fora do ar"}))

    with pytest.raises(extract.TransientError, match="HTTP 503"):
        extract.fetch_sgs(1, START, END)
    assert len(calls) == 3


@pytest.mark.parametrize("error", [requests.Timeout("lento"), requests.ConnectionError("sem rede")])
def test_fetch_sgs_retries_network_errors(fake_get, sleeps, error):
    calls = fake_get(error, error, make_response(200, SGS_DATA))

    assert extract.fetch_sgs(1, START, END) == SGS_DATA
    assert len(calls) == 3


def test_fetch_sgs_network_error_on_all_attempts(fake_get, sleeps):
    calls = fake_get(requests.ConnectionError("sem rede"))

    with pytest.raises(requests.ConnectionError):
        extract.fetch_sgs(1, START, END)
    assert len(calls) == 3


# fetch_yfinance

def test_fetch_yfinance_converts_to_json(fake_ticker, sleeps):
    fake_ticker(make_history(["2026-10-26", "2026-10-27"]))

    records = extract.fetch_yfinance("^BVSP", START, END)

    assert [r["Date"] for r in records] == ["2026-10-26", "2026-10-27"]
    assert records[0]["Close"] == 105.0


def test_fetch_yfinance_parameters(fake_ticker):
    calls = fake_ticker(make_history(["2026-10-27"]))

    extract.fetch_yfinance("^BVSP", START, END)

    assert calls[0] == {
        "ticker": "^BVSP",
        "start": START,
        "end": END,  # exclusivo: só pregões até o dia anterior
        "raise_errors": True,
        "timeout": 60,
    }


@pytest.mark.parametrize("start", [END, date(2026, 10, 29)])
def test_fetch_yfinance_nothing_to_fetch_does_not_call_source(fake_ticker, start):
    calls = fake_ticker(make_history(["2026-10-27"]))

    assert extract.fetch_yfinance("^BVSP", start, END) == []
    assert calls == []


def test_fetch_yfinance_single_day_period(fake_ticker):
    calls = fake_ticker(make_history(["2026-10-27"]))

    assert len(extract.fetch_yfinance("^BVSP", date(2026, 10, 27), END)) == 1
    assert calls[0]["start"] == date(2026, 10, 27)


def test_fetch_yfinance_no_trading_session_returns_empty_list(fake_ticker, sleeps):
    calls = fake_ticker(YFPricesMissingError("^BVSP", "(1d 2026-10-24 -> 2026-10-26)"))

    assert extract.fetch_yfinance("^BVSP", START, END) == []
    assert len(calls) == 1
    assert sleeps == []


def test_fetch_yfinance_invalid_ticker_is_not_retried(fake_ticker, sleeps):
    calls = fake_ticker(YFTzMissingError("^XXXXZZ"))

    with pytest.raises(YFTzMissingError):
        extract.fetch_yfinance("^XXXXZZ", START, END)
    assert len(calls) == 1


@pytest.mark.parametrize(
    "error",
    [YFRateLimitError(), curl_exceptions.Timeout("lento"), curl_exceptions.ConnectionError("sem rede")],
)
def test_fetch_yfinance_retries_transient_errors(fake_ticker, sleeps, error):
    calls = fake_ticker(error, make_history(["2026-10-27"]))

    assert len(extract.fetch_yfinance("^BVSP", START, END)) == 1
    assert len(calls) == 2
    assert sleeps == [10]


def test_fetch_yfinance_transient_error_on_all_attempts(fake_ticker, sleeps):
    calls = fake_ticker(YFRateLimitError())

    with pytest.raises(YFRateLimitError):
        extract.fetch_yfinance("^BVSP", START, END)
    assert len(calls) == 3


def test_fetch_yfinance_unexpected_error_is_not_retried(fake_ticker, sleeps):
    calls = fake_ticker(KeyError("Close"))

    with pytest.raises(KeyError):
        extract.fetch_yfinance("^BVSP", START, END)
    assert len(calls) == 1


# run_extraction

NOW = datetime(2026, 10, 28, 21, 5, 9)
TODAY = NOW.date()


def recorder(result):
    """Fetcher falso que registra (start, end) e devolve `result` (ou levanta, se for exceção)."""
    calls = []

    def fetch(start, end):
        calls.append((start, end))
        if isinstance(result, Exception):
            raise result
        return result

    fetch.calls = calls
    return fetch


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_run_extraction_full_load_saves_each_serie(raw_dir, log_dir, fixed_now):
    fixed_now(NOW)
    cdi, ptax = recorder(SGS_DATA), recorder(SGS_DATA[:1])

    extract.run_extraction("daily", {"cdi": cdi, "dolar_ptax": ptax})

    assert cdi.calls == [(date(2021, 10, 28), TODAY)]
    assert read_json(raw_dir / "cdi" / "cdi_20261028.json") == SGS_DATA
    assert read_json(raw_dir / "dolar_ptax" / "dolar_ptax_20261028.json") == SGS_DATA[:1]
    assert list(log_dir.iterdir()) == []  # sem erro, sem arquivo de log


def test_run_extraction_incremental_uses_previous_file(raw_dir, fixed_now):
    fixed_now(NOW)
    (raw_dir / "cdi").mkdir(parents=True)
    (raw_dir / "cdi" / "cdi_20261027.json").write_text(json.dumps([{"data": "26/10/2026", "valor": "1"}]))
    cdi = recorder([{"data": "27/10/2026", "valor": "2"}])

    extract.run_extraction("daily", {"cdi": cdi})

    assert cdi.calls == [(date(2026, 10, 27), TODAY)]
    assert sorted(p.name for p in (raw_dir / "cdi").iterdir()) == ["cdi_20261027.json", "cdi_20261028.json"]


def test_run_extraction_monthly_flag(raw_dir, fixed_now):
    fixed_now(NOW)
    (raw_dir / "ipca").mkdir(parents=True)
    (raw_dir / "ipca" / "ipca_20261015.json").write_text(json.dumps([{"data": "01/09/2026", "valor": "0.82"}]))
    ipca = recorder([])

    extract.run_extraction("monthly", {"ipca": ipca}, monthly=True)

    assert ipca.calls == [(date(2026, 10, 1), TODAY)]


def test_run_extraction_no_data_saves_nothing_and_is_not_an_error(raw_dir, log_dir, fixed_now, caplog):
    fixed_now(NOW)

    extract.run_extraction("daily", {"cdi": recorder([])})

    assert not (raw_dir / "cdi").exists()
    assert list(log_dir.iterdir()) == []
    assert "cdi: sem dado no período; nenhum arquivo salvo" in caplog.text


def test_run_extraction_rerun_same_day_overwrites_file(raw_dir, fixed_now):
    fixed_now(NOW)

    extract.run_extraction("daily", {"ibovespa": recorder([{"Date": "2026-10-27", "Volume": 0}])})
    second = recorder([{"Date": "2026-10-27", "Volume": 25136900}])
    extract.run_extraction("daily", {"ibovespa": second})

    assert second.calls == [(date(2021, 10, 28), TODAY)]  # mesmo período da primeira execução
    files = list((raw_dir / "ibovespa").iterdir())
    assert [f.name for f in files] == ["ibovespa_20261028.json"]
    assert read_json(files[0]) == [{"Date": "2026-10-27", "Volume": 25136900}]


def test_run_extraction_failure_is_logged_and_other_series_continue(raw_dir, log_dir, fixed_now):
    fixed_now(NOW)
    failing = recorder(requests.ConnectionError("sem rede"))
    ok = recorder(SGS_DATA)

    extract.run_extraction("daily", {"cdi": failing, "dolar_ptax": ok})

    assert not (raw_dir / "cdi").exists()
    assert (raw_dir / "dolar_ptax" / "dolar_ptax_20261028.json").exists()
    log_file = log_dir / "daily_20261028_210509.log"
    lines = log_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert "cdi: falha na extração (ConnectionError: sem rede)" in lines[0]
    assert lines[0].startswith("2026-")  # cada linha traz a hora do erro


def test_run_extraction_one_log_file_for_all_errors_of_the_run(log_dir, fixed_now):
    fixed_now(NOW)

    extract.run_extraction("daily", {"cdi": recorder(ValueError("a")), "ibovespa": recorder(KeyError("b"))})

    files = list(log_dir.iterdir())
    assert [f.name for f in files] == ["daily_20261028_210509.log"]
    content = files[0].read_text(encoding="utf-8")
    assert "cdi: falha na extração (ValueError: a)" in content
    assert "ibovespa: falha na extração (KeyError: 'b')" in content


def test_run_extraction_corrupted_previous_file_is_logged(raw_dir, log_dir, fixed_now):
    fixed_now(NOW)
    (raw_dir / "cdi").mkdir(parents=True)
    (raw_dir / "cdi" / "cdi_20261027.json").write_text("{quebrado")
    cdi, ptax = recorder(SGS_DATA), recorder(SGS_DATA)

    extract.run_extraction("daily", {"cdi": cdi, "dolar_ptax": ptax})

    assert cdi.calls == []
    assert ptax.calls != []
    assert "cdi: falha na extração (JSONDecodeError" in (log_dir / "daily_20261028_210509.log").read_text()


def test_run_extraction_log_file_name_uses_flow(log_dir, fixed_now):
    fixed_now(NOW)

    extract.run_extraction("monthly", {"ipca": recorder(ValueError("x"))}, monthly=True)

    assert [f.name for f in log_dir.iterdir()] == ["monthly_20261028_210509.log"]


def test_run_extraction_with_real_fetchers_end_to_end(raw_dir, log_dir, fixed_now, fake_get, fake_ticker, sleeps):
    fixed_now(NOW)
    fake_get(make_response(200, SGS_DATA))
    fake_ticker(make_history(["2026-10-26", "2026-10-27"]))
    from src.main_daily import SERIES

    extract.run_extraction("daily", SERIES)

    assert read_json(raw_dir / "cdi" / "cdi_20261028.json") == SGS_DATA
    assert read_json(raw_dir / "dolar_ptax" / "dolar_ptax_20261028.json") == SGS_DATA
    assert [r["Date"] for r in read_json(raw_dir / "ibovespa" / "ibovespa_20261028.json")] == ["2026-10-26", "2026-10-27"]
    assert list(log_dir.iterdir()) == []

"""Testes de src/utils.py: datas, conversão, gravação e cálculo da data inicial."""

import json
import logging
from datetime import date, datetime

import pandas as pd
import pytest

from src import utils
from tests.conftest import make_history


def write_raw(raw_dir, serie, ingestion, records):
    path = raw_dir / serie / f"{serie}_{ingestion}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records), encoding="utf-8")
    return path


# five_years_before

@pytest.mark.parametrize(
    "today, expected",
    [
        (date(2026, 10, 28), date(2021, 10, 28)),
        (date(2026, 1, 1), date(2021, 1, 1)),
        (date(2026, 12, 31), date(2021, 12, 31)),
        (date(2028, 2, 28), date(2023, 2, 28)),
        (date(2028, 2, 29), date(2023, 2, 28)),  # 29/02 sem correspondente → 28/02
        (date(2029, 2, 28), date(2024, 2, 28)),  # destino bissexto, mas a data existe
    ],
)
def test_five_years_before(today, expected):
    assert utils.five_years_before(today) == expected


# dataframe_to_json

def test_dataframe_to_json_keeps_all_columns():
    records = utils.dataframe_to_json(make_history(["2026-10-26", "2026-10-27"]))

    assert len(records) == 2
    assert set(records[0]) == {"Date", "Open", "High", "Low", "Close", "Volume", "Dividends", "Stock Splits"}
    assert records[0] == {
        "Date": "2026-10-26", "Open": 100.0, "High": 110.0, "Low": 90.0,
        "Close": 105.0, "Volume": 1000, "Dividends": 0.0, "Stock Splits": 0.0,
    }


def test_dataframe_to_json_uses_local_trading_date():
    # Meia-noite em São Paulo é 03:00 UTC: a data não pode mudar na conversão.
    records = utils.dataframe_to_json(make_history(["2026-10-27"], tz="America/Sao_Paulo"))
    assert records[0]["Date"] == "2026-10-27"


def test_dataframe_to_json_late_hour_does_not_roll_to_next_day():
    index = pd.DatetimeIndex([pd.Timestamp("2026-10-27 23:30", tz="America/Sao_Paulo")], name="Date")
    df = pd.DataFrame({"Close": [1.0]}, index=index)
    assert utils.dataframe_to_json(df)[0]["Date"] == "2026-10-27"


def test_dataframe_to_json_output_is_json_serializable():
    records = utils.dataframe_to_json(make_history(["2026-10-27"]))
    assert json.loads(json.dumps(records)) == records


def test_dataframe_to_json_empty_dataframe():
    assert utils.dataframe_to_json(make_history([])) == []


# raw_file_path / save_json

def test_raw_file_path(raw_dir):
    path = utils.raw_file_path("cdi", date(2026, 3, 5))
    assert path == raw_dir / "cdi" / "cdi_20260305.json"


def test_save_json_creates_folders_and_writes_content(raw_dir):
    data = [{"data": "27/10/2026", "valor": "0.050788"}]

    path = utils.save_json(data, "cdi", date(2026, 10, 28))

    assert path == raw_dir / "cdi" / "cdi_20261028.json"
    assert json.loads(path.read_text(encoding="utf-8")) == data


def test_save_json_overwrites_file_of_the_same_day(raw_dir):
    utils.save_json([{"data": "01/01/2026", "valor": "1"}], "cdi", date(2026, 10, 28))
    path = utils.save_json([{"data": "02/01/2026", "valor": "2"}], "cdi", date(2026, 10, 28))

    assert json.loads(path.read_text(encoding="utf-8")) == [{"data": "02/01/2026", "valor": "2"}]
    assert len(list((raw_dir / "cdi").iterdir())) == 1


def test_save_json_keeps_non_ascii_text(raw_dir):
    path = utils.save_json([{"texto": "variação"}], "cdi", date(2026, 10, 28))
    assert "variação" in path.read_text(encoding="utf-8")


# _record_date / _first_day_of_next_month

def test_record_date_sgs_format():
    assert utils._record_date({"data": "01/09/2026", "valor": "0.82"}) == date(2026, 9, 1)


def test_record_date_yfinance_format():
    assert utils._record_date({"Date": "2026-10-27", "Close": 1.0}) == date(2026, 10, 27)


@pytest.mark.parametrize(
    "day, expected",
    [
        (date(2026, 9, 1), date(2026, 10, 1)),
        (date(2026, 1, 31), date(2026, 2, 1)),
        (date(2026, 12, 1), date(2027, 1, 1)),  # virada de ano
    ],
)
def test_first_day_of_next_month(day, expected):
    assert utils._first_day_of_next_month(day) == expected


# get_start_date

TODAY = date(2026, 10, 28)


def test_start_date_full_load_when_folder_does_not_exist():
    assert utils.get_start_date("cdi", TODAY) == date(2021, 10, 28)


def test_start_date_full_load_when_folder_is_empty(raw_dir):
    (raw_dir / "cdi").mkdir(parents=True)
    assert utils.get_start_date("cdi", TODAY) == date(2021, 10, 28)


def test_start_date_full_load_on_29_february():
    assert utils.get_start_date("cdi", date(2028, 2, 29)) == date(2023, 2, 28)


def test_start_date_incremental_day_after_last_data(raw_dir):
    write_raw(raw_dir, "cdi", "20261027", [{"data": "24/10/2026", "valor": "1"}, {"data": "26/10/2026", "valor": "1"}])
    assert utils.get_start_date("cdi", TODAY) == date(2026, 10, 27)


def test_start_date_uses_data_date_not_file_name(raw_dir):
    # Arquivo de 27/10 só com dado até 25/10 (ex.: CDI publicado em D+1): a busca recomeça em 26/10.
    write_raw(raw_dir, "cdi", "20261027", [{"data": "25/10/2026", "valor": "1"}])
    assert utils.get_start_date("cdi", TODAY) == date(2026, 10, 26)


def test_start_date_uses_max_date_even_if_records_are_unordered(raw_dir):
    write_raw(raw_dir, "cdi", "20261027", [{"data": "26/10/2026", "valor": "1"}, {"data": "20/10/2026", "valor": "1"}])
    assert utils.get_start_date("cdi", TODAY) == date(2026, 10, 27)


def test_start_date_uses_most_recent_previous_file(raw_dir):
    write_raw(raw_dir, "cdi", "20261020", [{"data": "17/10/2026", "valor": "1"}])
    write_raw(raw_dir, "cdi", "20261027", [{"data": "26/10/2026", "valor": "1"}])
    write_raw(raw_dir, "cdi", "20261023", [{"data": "22/10/2026", "valor": "1"}])
    assert utils.get_start_date("cdi", TODAY) == date(2026, 10, 27)


def test_start_date_orders_files_across_years(raw_dir):
    write_raw(raw_dir, "cdi", "20251231", [{"data": "30/12/2025", "valor": "1"}])
    write_raw(raw_dir, "cdi", "20260102", [{"data": "01/01/2026", "valor": "1"}])
    assert utils.get_start_date("cdi", date(2026, 1, 5)) == date(2026, 1, 2)


def test_start_date_ignores_todays_file_so_rerun_repeats_the_period(raw_dir):
    write_raw(raw_dir, "cdi", "20261027", [{"data": "26/10/2026", "valor": "1"}])
    write_raw(raw_dir, "cdi", "20261028", [{"data": "27/10/2026", "valor": "1"}])
    assert utils.get_start_date("cdi", TODAY) == date(2026, 10, 27)


def test_start_date_rerun_on_first_day_repeats_full_load(raw_dir):
    write_raw(raw_dir, "cdi", "20261028", [{"data": "27/10/2026", "valor": "1"}])
    assert utils.get_start_date("cdi", TODAY) == date(2021, 10, 28)


def test_start_date_ignores_files_after_today(raw_dir):
    write_raw(raw_dir, "cdi", "20261027", [{"data": "26/10/2026", "valor": "1"}])
    write_raw(raw_dir, "cdi", "20261101", [{"data": "31/10/2026", "valor": "1"}])
    assert utils.get_start_date("cdi", TODAY) == date(2026, 10, 27)


def test_start_date_ignores_other_files_in_folder(raw_dir):
    write_raw(raw_dir, "cdi", "20261027", [{"data": "26/10/2026", "valor": "1"}])
    (raw_dir / "cdi" / "anotacoes.txt").write_text("não é um arquivo da série")
    assert utils.get_start_date("cdi", TODAY) == date(2026, 10, 27)


def test_start_date_is_isolated_per_serie(raw_dir):
    write_raw(raw_dir, "dolar_ptax", "20261027", [{"data": "27/10/2026", "valor": "5"}])
    assert utils.get_start_date("cdi", TODAY) == date(2021, 10, 28)


def test_start_date_yfinance_records(raw_dir):
    write_raw(raw_dir, "ibovespa", "20261028", [{"Date": "2026-10-26"}, {"Date": "2026-10-27"}])
    assert utils.get_start_date("ibovespa", date(2026, 10, 29)) == date(2026, 10, 28)


def test_start_date_monthly_starts_on_next_month(raw_dir):
    write_raw(raw_dir, "ipca", "20261015", [{"data": "01/08/2026", "valor": "0.1"}, {"data": "01/09/2026", "valor": "0.82"}])
    assert utils.get_start_date("ipca", TODAY, monthly=True) == date(2026, 10, 1)


def test_start_date_monthly_year_rollover(raw_dir):
    write_raw(raw_dir, "ipca", "20270115", [{"data": "01/12/2026", "valor": "0.5"}])
    assert utils.get_start_date("ipca", date(2027, 2, 15), monthly=True) == date(2027, 1, 1)


def test_start_date_monthly_full_load():
    assert utils.get_start_date("ipca", TODAY, monthly=True) == date(2021, 10, 28)


def test_start_date_corrupted_file_raises(raw_dir):
    path = raw_dir / "cdi" / "cdi_20261027.json"
    path.parent.mkdir(parents=True)
    path.write_text("{não é json")
    with pytest.raises(json.JSONDecodeError):
        utils.get_start_date("cdi", TODAY)


# configure_logging

def test_configure_logging_creates_log_dir_but_no_file(log_dir):
    utils.configure_logging("daily", datetime(2026, 10, 28, 21, 0, 0))

    assert log_dir.is_dir()
    assert list(log_dir.iterdir()) == []


def test_configure_logging_info_and_warning_do_not_create_file(log_dir):
    logger = utils.configure_logging("daily", datetime(2026, 10, 28, 21, 0, 0))
    logger.info("tudo certo")
    logger.warning("retentativa")

    assert list(log_dir.iterdir()) == []


def test_configure_logging_error_creates_named_file(log_dir):
    logger = utils.configure_logging("monthly", datetime(2026, 10, 28, 21, 5, 9))
    logger.error("ipca: falha na extração")

    log_file = log_dir / "monthly_20261028_210509.log"
    assert log_file.exists()
    content = log_file.read_text(encoding="utf-8")
    assert "ERROR" in content and "ipca: falha na extração" in content


def test_configure_logging_does_not_duplicate_handlers():
    utils.configure_logging("daily", datetime(2026, 10, 28, 21, 0, 0))
    utils.configure_logging("daily", datetime(2026, 10, 28, 21, 0, 1))
    assert len(logging.getLogger("src").handlers) == 2

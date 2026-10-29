"""Testes da configuração dos pontos de entrada (main_daily e main_monthly)."""

import runpy

import pytest

from src import extract, main_daily, main_monthly


def test_daily_series_names_and_sources():
    assert list(main_daily.SERIES) == ["cdi", "dolar_ptax", "ibovespa"]
    assert main_daily.SERIES["cdi"].func is extract.fetch_sgs
    assert main_daily.SERIES["cdi"].args == (12,)
    assert main_daily.SERIES["dolar_ptax"].func is extract.fetch_sgs
    assert main_daily.SERIES["dolar_ptax"].args == (1,)
    assert main_daily.SERIES["ibovespa"].func is extract.fetch_yfinance
    assert main_daily.SERIES["ibovespa"].args == ("^BVSP",)


def test_monthly_series_names_and_sources():
    assert list(main_monthly.SERIES) == ["ipca"]
    assert main_monthly.SERIES["ipca"].func is extract.fetch_sgs
    assert main_monthly.SERIES["ipca"].args == (433,)


# Os módulos já foram importados acima; o runpy avisa ao executá-los de novo como __main__.
@pytest.mark.filterwarnings("ignore:.*found in sys.modules:RuntimeWarning")
def test_entry_points_call_run_extraction(monkeypatch):
    calls = []
    monkeypatch.setattr(extract, "run_extraction", lambda *args, **kwargs: calls.append((args, kwargs)))

    runpy.run_module("src.main_daily", run_name="__main__")
    runpy.run_module("src.main_monthly", run_name="__main__")

    assert calls[0][0][0] == "daily" and calls[0][1] == {}
    assert calls[1][0][0] == "monthly" and calls[1][1] == {"monthly": True}

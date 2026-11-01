"""Testes da configuração dos pontos de entrada (main_daily e main_monthly)."""

import runpy

import pytest

from src import extract, main_daily, main_monthly, transform


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
def test_entry_points_run_extraction_then_transformation(monkeypatch):
    calls = []

    def fake_extraction(*args, **kwargs):
        calls.append(("extract", args, kwargs))
        return []

    def fake_transformation():
        calls.append(("transform",))
        return True

    monkeypatch.setattr(extract, "run_extraction", fake_extraction)
    monkeypatch.setattr(transform, "run_transformation", fake_transformation)

    for module in ["src.main_daily", "src.main_monthly"]:
        with pytest.raises(SystemExit) as exit_info:
            runpy.run_module(module, run_name="__main__")
        assert exit_info.value.code == 0

    # O runpy recria o SERIES (e os `partial`), então comparamos o fluxo, as séries e os parâmetros.
    assert [c[0] for c in calls] == ["extract", "transform", "extract", "transform"]
    assert calls[0][1][0] == "daily" and list(calls[0][1][1]) == list(main_daily.SERIES) and calls[0][2] == {}
    assert calls[2][1][0] == "monthly" and list(calls[2][1][1]) == list(main_monthly.SERIES)
    assert calls[2][2] == {"monthly": True}


@pytest.mark.filterwarnings("ignore:.*found in sys.modules:RuntimeWarning")
@pytest.mark.parametrize("module", ["src.main_daily", "src.main_monthly"])
@pytest.mark.parametrize(
    "failed, transformed, code",
    [([], True, 0), (["cdi"], True, 1), ([], False, 1), (["cdi"], False, 1)],
)
def test_entry_points_exit_code(monkeypatch, module, failed, transformed, code):
    monkeypatch.setattr(extract, "run_extraction", lambda *args, **kwargs: failed)
    monkeypatch.setattr(transform, "run_transformation", lambda: transformed)

    with pytest.raises(SystemExit) as exit_info:
        runpy.run_module(module, run_name="__main__")

    assert exit_info.value.code == code


@pytest.mark.filterwarnings("ignore:.*found in sys.modules:RuntimeWarning")
def test_transformation_runs_even_when_extraction_fails(monkeypatch):
    calls = []
    monkeypatch.setattr(extract, "run_extraction", lambda *args, **kwargs: ["ibovespa"])
    monkeypatch.setattr(transform, "run_transformation", lambda: calls.append("transform") or True)

    with pytest.raises(SystemExit):
        runpy.run_module("src.main_daily", run_name="__main__")

    assert calls == ["transform"]

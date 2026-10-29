"""Testes de src/transform.py: camada gold (a partir de séries silver sintéticas)."""

import math
from datetime import datetime

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import pytest

from src import transform, utils

T = pd.Timestamp


def daily(column, dates, values):
    return pd.DataFrame({"data": pd.to_datetime(dates), column: values}).reset_index(drop=True)


def cdi_silver(dates, rate_pct):
    df = pd.DataFrame({"data": pd.to_datetime(dates), "taxa_diaria_pct": rate_pct})
    df["indice"] = 100 * (1 + df["taxa_diaria_pct"] / 100).cumprod()
    return df


def ipca_silver(months, values):
    df = pd.DataFrame({"mes_referencia": pd.to_datetime(months), "variacao_mensal_pct": values})
    df["indice"] = 100 * (1 + df["variacao_mensal_pct"] / 100).cumprod()
    return df


def sample_silver():
    days = pd.bdate_range("2022-01-03", "2026-10-28")
    months = pd.date_range("2022-01-01", "2026-09-01", freq="MS")
    return {
        "cdi": cdi_silver(days, 0.05),
        "ipca": ipca_silver(months, 0.4),
        "dolar_ptax": daily("ptax_venda", days, np.linspace(5.0, 5.5, len(days))),
        "ibovespa": daily("fechamento", days, np.linspace(100_000, 150_000, len(days))),
    }


# Funções de apoio

@pytest.mark.parametrize(
    "window, end, expected",
    [
        ("mes", T("2026-10-28"), T("2026-09-30")),
        ("mes", T("2026-03-01"), T("2026-02-28")),
        ("mes", T("2026-09-01"), T("2026-08-31")),  # IPCA: o mês anterior
        ("ano", T("2026-10-28"), T("2025-12-31")),
        ("12m", T("2026-10-28"), T("2025-10-28")),
        ("24m", T("2026-10-28"), T("2024-10-28")),
        ("36m", T("2026-10-28"), T("2023-10-28")),
        ("12m", T("2026-09-30"), T("2025-09-30")),
        ("12m", T("2028-02-29"), T("2027-02-28")),  # 29/02 sem correspondente
    ],
)
def test_window_base(window, end, expected):
    assert transform._window_base(window, end) == expected


def test_asof_uses_last_data_on_or_before_date():
    df = daily("v", ["2026-10-23", "2026-10-26"], [1.0, 2.0])  # sexta e segunda

    assert transform._asof(df, "data", "v", T("2026-10-25")) == (T("2026-10-23"), 1.0)  # domingo → sexta
    assert transform._asof(df, "data", "v", T("2026-10-26")) == (T("2026-10-26"), 2.0)  # inclusive
    assert transform._asof(df, "data", "v", T("2026-10-22")) is None  # antes do histórico


def test_month_label_and_end():
    assert transform._month_label(T("2026-09-01")) == "set/2026"
    assert transform._month_end(T("2026-02-01")) == T("2026-02-28")
    assert transform._month_end(T("2026-09-30")) == T("2026-09-30")


def test_trailing_requires_full_window_unless_partial():
    df = daily("v", ["2025-01-10", "2025-06-10", "2026-01-10", "2026-01-11"], [5.0, 1.0, 3.0, 4.0])

    full = transform._trailing(df, "v", 12, "min")
    partial = transform._trailing(df, "v", 12, "max", partial=True)

    assert full.isna().tolist() == [True, True, False, False]
    assert full.iloc[2] == 1.0  # janela de 10/01/2025 a 10/01/2026, inclusive nas pontas
    assert full.iloc[3] == 1.0  # 11/01/2025 em diante: o 5,0 de 10/01/2025 sai
    assert partial.tolist() == [5.0, 5.0, 5.0, 4.0]


# Indicadores diários

def test_cdi_diario_annualizes_daily_rate():
    df = transform._gold_cdi_diario(cdi_silver(["2026-10-27", "2026-10-28"], [0.050788, 0.050788]))

    assert list(df.columns) == ["data", "indice", "cdi_anualizado_pct"]
    assert df["cdi_anualizado_pct"].iloc[-1] == pytest.approx((1.00050788**252 - 1) * 100)


def test_price_diario_columns_and_d1():
    df = transform._gold_price_diario(daily("ptax_venda", ["2026-10-27", "2026-10-28"], [5.0, 5.5]), "ptax_venda")

    assert list(df.columns) == [
        "data", "ptax_venda", "var_d1_pct", "mm50", "mm200", "dist_mm50_pct", "dist_mm200_pct", "min_12m", "max_12m",
    ]
    assert math.isnan(df["var_d1_pct"].iloc[0])
    assert df["var_d1_pct"].iloc[1] == pytest.approx(10.0)


def test_price_diario_moving_averages_use_rows_not_calendar_days():
    days = pd.bdate_range("2025-01-01", periods=200)
    df = transform._gold_price_diario(daily("fechamento", days, np.arange(1, 201, dtype=float)), "fechamento")

    assert df["mm50"].iloc[:49].isna().all()
    assert df["mm50"].iloc[49] == pytest.approx(np.mean(range(1, 51)))
    assert df["mm200"].iloc[198:].tolist()[0] != df["mm200"].iloc[198:].tolist()[0]  # NaN antes de 200 linhas
    assert df["mm200"].iloc[199] == pytest.approx(100.5)
    assert df["dist_mm50_pct"].iloc[199] == pytest.approx((200 / np.mean(range(151, 201)) - 1) * 100)


def test_ibovespa_diario_distance_from_max():
    df = transform._gold_ibovespa_diario(daily("fechamento", ["2026-10-26", "2026-10-27", "2026-10-28"], [100.0, 120.0, 90.0]))

    assert df["dist_max_5a_pct"].tolist() == pytest.approx([0.0, 0.0, -25.0])


def test_ibovespa_diario_max_window_is_five_years():
    df = transform._gold_ibovespa_diario(daily("fechamento", ["2020-01-01", "2025-01-02", "2025-06-01"], [200.0, 100.0, 90.0]))

    # Em 01/06/2025 o pico de 2020 já saiu da janela de 5 anos.
    assert df["dist_max_5a_pct"].iloc[2] == pytest.approx(-10.0)


def test_ibovespa_usd_only_common_dates():
    ibov = daily("fechamento", ["2026-11-19", "2026-11-20", "2026-11-23"], [150_000.0, 151_000.0, 152_000.0])
    ptax = daily("ptax_venda", ["2026-11-19", "2026-11-23", "2026-11-24"], [5.0, 5.2, 5.3])

    df = transform._gold_ibovespa_usd_diario(ibov, ptax)

    assert list(df.columns) == ["data", "ibovespa", "ptax_venda", "ibovespa_usd"]
    assert df["data"].tolist() == [T("2026-11-19"), T("2026-11-23")]
    assert df["ibovespa_usd"].tolist() == pytest.approx([30_000.0, 152_000 / 5.2])


# Rentabilidade

def rent(silver):
    return transform._gold_rentabilidade(silver).set_index(["serie", "tipo", "janela"])


def test_rentabilidade_has_all_series_windows_and_types():
    df = transform._gold_rentabilidade(sample_silver())

    assert list(df.columns) == [
        "serie", "janela", "tipo", "data_inicio", "data_fim", "rotulo", "retorno_pct", "excesso_cdi_pp", "pct_do_cdi",
    ]
    assert len(df) == 4 * 5 + 2 * 5  # nominal para as 4 séries, real só para CDI e Ibovespa
    assert set(df[df["tipo"] == "real"]["serie"]) == {"cdi", "ibovespa"}


def test_nominal_return_uses_last_value_before_window_start():
    ptax = daily("ptax_venda", ["2025-12-30", "2026-01-02", "2026-10-28"], [5.0, 5.1, 5.5])

    df = rent({"dolar_ptax": ptax})

    row = df.loc[("dolar_ptax", "nominal", "ano")]
    assert row["data_inicio"] == T("2025-12-30")  # 31/12 sem dado → último dado anterior
    assert row["data_fim"] == T("2026-10-28")
    assert row["retorno_pct"] == pytest.approx(10.0)
    assert row["rotulo"] == "Ano até 28/10/2026"


def test_cdi_month_return_is_product_of_month_rates():
    days = pd.bdate_range("2026-09-01", "2026-10-30")
    df = rent({"cdi": cdi_silver(days, 0.05)})

    october_days = len(pd.bdate_range("2026-10-01", "2026-10-30"))
    assert df.loc[("cdi", "nominal", "mes"), "retorno_pct"] == pytest.approx((1.0005**october_days - 1) * 100)


def test_ipca_nominal_uses_months_and_month_label():
    months = pd.date_range("2025-09-01", "2026-09-01", freq="MS")
    df = rent({"ipca": ipca_silver(months, [1.0] * 13)})

    assert df.loc[("ipca", "nominal", "mes"), "retorno_pct"] == pytest.approx(1.0)
    assert df.loc[("ipca", "nominal", "12m"), "retorno_pct"] == pytest.approx((1.01**12 - 1) * 100)
    assert df.loc[("ipca", "nominal", "12m"), "rotulo"] == "12M até set/2026"


def test_window_without_history_is_empty():
    df = rent({"dolar_ptax": daily("ptax_venda", ["2026-01-02", "2026-10-28"], [5.0, 5.5])})

    row = df.loc[("dolar_ptax", "nominal", "36m")]
    assert math.isnan(row["retorno_pct"])
    assert pd.isna(row["data_inicio"])


def test_real_return_is_aligned_to_last_ipca_month():
    days = pd.bdate_range("2025-09-01", "2026-10-28")
    months = pd.date_range("2025-09-01", "2026-09-01", freq="MS")
    silver = {"cdi": cdi_silver(days, 0.05), "ipca": ipca_silver(months, [0.5] * 13)}

    df = rent(silver)

    real = df.loc[("cdi", "real", "mes")]
    assert real["data_fim"] == T("2026-09-30")  # fim do mês do último IPCA, não o último CDI
    assert real["data_inicio"] == T("2026-08-31")
    assert real["rotulo"] == "Mês até set/2026"
    september_days = len(pd.bdate_range("2026-09-01", "2026-09-30"))
    nominal = 1.0005**september_days
    assert real["retorno_pct"] == pytest.approx((nominal / 1.005 - 1) * 100)  # (1 + CDI) ÷ (1 + IPCA) − 1


def test_real_return_ytd_uses_ipca_from_january():
    days = pd.bdate_range("2025-12-01", "2026-10-28")
    months = pd.date_range("2025-12-01", "2026-09-01", freq="MS")
    silver = {"ibovespa": daily("fechamento", days, 100.0), "ipca": ipca_silver(months, [1.0] * 10)}

    row = rent(silver).loc[("ibovespa", "real", "ano")]

    # Ibovespa parado e 9 meses de IPCA (jan a set): perda real.
    assert row["retorno_pct"] == pytest.approx((1 / 1.01**9 - 1) * 100)


def test_no_real_rows_without_ipca():
    silver = sample_silver()
    del silver["ipca"]

    df = transform._gold_rentabilidade(silver)

    assert set(df["tipo"]) == {"nominal"}


def test_excess_and_pct_of_cdi_only_on_ibovespa_nominal_rows():
    df = transform._gold_rentabilidade(sample_silver())

    filled = df.dropna(subset=["excesso_cdi_pp"])
    assert set(zip(filled["serie"], filled["tipo"])) == {("ibovespa", "nominal")}


def test_excess_and_pct_of_cdi_values():
    days = pd.bdate_range("2025-10-28", "2026-10-28")
    silver = {"cdi": cdi_silver(days, 0.05), "ibovespa": daily("fechamento", days, np.linspace(100, 120, len(days)))}

    df = rent(silver)

    ibov, cdi = df.loc[("ibovespa", "nominal", "12m"), "retorno_pct"], df.loc[("cdi", "nominal", "12m"), "retorno_pct"]
    assert df.loc[("ibovespa", "nominal", "12m"), "excesso_cdi_pp"] == pytest.approx(ibov - cdi)
    assert df.loc[("ibovespa", "nominal", "12m"), "pct_do_cdi"] == pytest.approx(ibov / cdi * 100)


def test_pct_of_cdi_empty_when_ibovespa_is_negative():
    days = pd.bdate_range("2025-10-28", "2026-10-28")
    silver = {"cdi": cdi_silver(days, 0.05), "ibovespa": daily("fechamento", days, np.linspace(120, 100, len(days)))}

    row = rent(silver).loc[("ibovespa", "nominal", "12m")]

    assert row["excesso_cdi_pp"] < 0
    assert math.isnan(row["pct_do_cdi"])


# Retorno anual

def test_retorno_anual_skips_first_partial_year_and_flags_current():
    ptax = daily("ptax_venda", ["2024-10-28", "2024-12-31", "2025-12-31", "2026-10-28"], [4.0, 5.0, 6.0, 6.6])

    df = transform._gold_retorno_anual({"dolar_ptax": ptax})

    assert df["ano"].tolist() == [2025, 2026]  # 2024 não tem fechamento de 2023
    assert df["retorno_pct"].tolist() == pytest.approx([20.0, 10.0])
    assert df["ano_completo"].tolist() == [True, False]


def test_retorno_anual_ipca_uses_december_to_december():
    months = pd.date_range("2024-12-01", "2025-12-01", freq="MS")
    df = transform._gold_retorno_anual({"ipca": ipca_silver(months, [1.0] * 13)})

    assert df.loc[df["ano"] == 2025, "retorno_pct"].item() == pytest.approx((1.01**12 - 1) * 100)


# IPCA mensal, último dado e juros reais

def test_ipca_mensal_12m_and_annualized():
    months = pd.date_range("2025-01-01", "2026-01-01", freq="MS")
    df = transform._gold_ipca_mensal(ipca_silver(months, [1.0] * 13))

    assert list(df.columns) == ["mes_referencia", "ipca_mensal_pct", "ipca_12m_pct", "ipca_anualizado_mes_pct"]
    assert df["ipca_12m_pct"].iloc[:11].isna().all()
    assert df["ipca_12m_pct"].iloc[11] == pytest.approx((1.01**12 - 1) * 100)
    assert df["ipca_anualizado_mes_pct"].iloc[0] == pytest.approx((1.01**12 - 1) * 100)


def test_ipca_mensal_12m_empty_when_a_month_is_missing():
    months = list(pd.date_range("2025-01-01", "2025-12-01", freq="MS"))
    months.remove(T("2025-06-01"))
    months.append(T("2026-01-01"))
    df = transform._gold_ipca_mensal(ipca_silver(months, [1.0] * 12))

    assert df["ipca_12m_pct"].isna().all()


def test_ultimo_dado():
    df = transform._gold_ultimo_dado(sample_silver()).set_index("serie")

    assert df.loc["ipca", "data_ultimo_dado"] == T("2026-09-01")
    assert df.loc["ipca", "ultimo_valor"] == 0.4
    assert df.loc["ibovespa", "data_ultimo_dado"] == T("2026-10-28")
    assert df.loc["ibovespa", "ultimo_valor"] == pytest.approx(150_000)
    assert df.loc["cdi", "ultimo_valor"] == 0.05


def test_juros_reais_uses_fisher_and_latest_values():
    cdi = transform._gold_cdi_diario(cdi_silver(["2026-10-27", "2026-10-28"], [0.05, 0.05]))
    months = pd.date_range("2025-10-01", "2026-09-01", freq="MS")
    ipca = transform._gold_ipca_mensal(ipca_silver(months, [0.4] * 12))

    row = transform._gold_juros_reais(cdi, ipca).iloc[0]

    cdi_aa, ipca_12m = (1.0005**252 - 1) * 100, (1.004**12 - 1) * 100
    assert row["data_referencia"] == T("2026-10-28")
    assert row["mes_referencia_ipca"] == T("2026-09-01")
    assert row["spread_juros_reais_pct"] == pytest.approx(((1 + cdi_aa / 100) / (1 + ipca_12m / 100) - 1) * 100)


def test_juros_reais_without_12_months_of_ipca():
    cdi = transform._gold_cdi_diario(cdi_silver(["2026-10-28"], [0.05]))
    ipca = transform._gold_ipca_mensal(ipca_silver(["2026-09-01"], [0.82]))

    row = transform._gold_juros_reais(cdi, ipca).iloc[0]

    assert row["cdi_anualizado_pct"] == pytest.approx((1.0005**252 - 1) * 100)
    assert pd.isna(row["mes_referencia_ipca"])
    assert math.isnan(row["ipca_12m_pct"]) and math.isnan(row["spread_juros_reais_pct"])


# build_gold

GOLD_TABLES = [
    "cdi_diario", "dolar_ptax_diario", "ibovespa_diario", "ibovespa_usd_diario",
    "rentabilidade", "retorno_anual", "ipca_mensal", "ultimo_dado", "juros_reais",
]


def test_build_gold_writes_all_tables():
    tables = transform.build_gold(sample_silver())

    assert sorted(tables) == sorted(GOLD_TABLES)
    assert sorted(p.stem for p in utils.GOLD_DIR.iterdir()) == sorted(GOLD_TABLES)


def test_gold_parquet_types():
    transform.build_gold(sample_silver())

    rent_schema = pq.read_schema(utils.GOLD_DIR / "rentabilidade.parquet")
    assert str(rent_schema.field("data_inicio").type) == "date32[day]"
    assert str(rent_schema.field("retorno_pct").type) == "double"
    annual = pq.read_schema(utils.GOLD_DIR / "retorno_anual.parquet")
    assert str(annual.field("ano").type) == "int64"
    assert str(annual.field("ano_completo").type) == "bool"
    for name in ["cdi_diario", "ibovespa_diario", "ipca_mensal", "juros_reais"]:
        assert str(pq.read_schema(utils.GOLD_DIR / f"{name}.parquet").field(0).type) == "date32[day]"


def test_build_gold_skips_tables_of_missing_series(caplog):
    silver = sample_silver()
    del silver["ipca"]

    tables = transform.build_gold(silver)

    assert "ipca_mensal" not in tables and "juros_reais" not in tables
    assert "rentabilidade" in tables and "cdi_diario" in tables
    assert "ipca_mensal: série(s) ausente(s) na silver (ipca)" in caplog.text


def test_build_gold_with_empty_silver(caplog):
    assert transform.build_gold({}) == {}
    assert "silver vazia" in caplog.text


# run_transformation com a gold

def test_run_transformation_builds_silver_and_gold():
    for serie, records in {
        "cdi": [{"data": "27/10/2026", "valor": "0.05"}, {"data": "28/10/2026", "valor": "0.05"}],
        "ipca": [{"data": "01/09/2026", "valor": "0.82"}],
        "dolar_ptax": [{"data": "28/10/2026", "valor": "5.34"}],
        "ibovespa": [{"Date": "2026-10-28", "Close": 171006.0}],
    }.items():
        utils.save_json(records, serie, datetime(2026, 10, 28).date())

    transform.run_transformation()

    assert len(list(utils.SILVER_DIR.iterdir())) == 4
    assert len(list(utils.GOLD_DIR.iterdir())) == 9


def test_run_transformation_logs_gold_failure(monkeypatch, log_dir):
    monkeypatch.setattr(transform, "build_silver", lambda: {})

    def broken(silver):
        raise ValueError("conta errada")

    monkeypatch.setattr(transform, "build_gold", broken)
    utils.configure_logging("daily", datetime(2026, 10, 29, 9, 0, 0))

    transform.run_transformation()

    assert "transformação: falha na gold (ValueError: conta errada)" in (log_dir / "daily_20261029_090000.log").read_text()


def test_run_transformation_skips_gold_when_silver_fails(monkeypatch):
    calls = []
    monkeypatch.setattr(transform, "build_silver", lambda: (_ for _ in ()).throw(OSError("x")))
    monkeypatch.setattr(transform, "build_gold", lambda silver: calls.append(silver))

    transform.run_transformation()

    assert calls == []

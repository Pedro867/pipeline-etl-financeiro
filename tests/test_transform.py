"""Testes de src/transform.py: camada silver."""

from datetime import date

import pandas as pd
import pyarrow.parquet as pq
import pytest

from src import transform, utils


def bronze(serie, ingestion, records):
    utils.save_json(records, serie, ingestion)


def sgs(*pairs):
    return [{"data": d, "valor": v} for d, v in pairs]


def yf_rows(*pairs):
    return [
        {"Date": d, "Open": 1.0, "High": 2.0, "Low": 0.5, "Close": c, "Volume": 10, "Dividends": 0.0, "Stock Splits": 0.0}
        for d, c in pairs
    ]


def read_silver(name):
    return pd.read_parquet(utils.SILVER_DIR / f"{name}.parquet")


def full_bronze():
    bronze("cdi", date(2026, 10, 28), sgs(("27/10/2026", "0.050788"), ("28/10/2026", "0.050788")))
    bronze("ipca", date(2026, 10, 28), sgs(("01/08/2026", "-0.32"), ("01/09/2026", "0.82")))
    bronze("dolar_ptax", date(2026, 10, 28), sgs(("27/10/2026", "5.3346"), ("28/10/2026", "5.3420")))
    bronze("ibovespa", date(2026, 10, 28), yf_rows(("2026-10-26", 176608.0), ("2026-10-27", 175710.0)))


# Esquema e tipos

def test_build_silver_writes_four_tables():
    full_bronze()

    tables = transform.build_silver()

    assert set(tables) == {"cdi", "ipca", "dolar_ptax", "ibovespa"}
    assert sorted(p.name for p in utils.SILVER_DIR.iterdir()) == [
        "cdi.parquet", "dolar_ptax.parquet", "ibovespa.parquet", "ipca.parquet",
    ]


@pytest.mark.parametrize(
    "name, columns",
    [
        ("cdi", ["data", "taxa_diaria_pct", "indice"]),
        ("ipca", ["mes_referencia", "variacao_mensal_pct", "indice"]),
        ("dolar_ptax", ["data", "ptax_venda"]),
        ("ibovespa", ["data", "fechamento"]),
    ],
)
def test_silver_columns_match_approved_schema(name, columns):
    full_bronze()
    transform.build_silver()

    assert list(read_silver(name).columns) == columns


@pytest.mark.parametrize("name", ["cdi", "ipca", "dolar_ptax", "ibovespa"])
def test_silver_parquet_types(name):
    full_bronze()
    transform.build_silver()

    schema = pq.read_schema(utils.SILVER_DIR / f"{name}.parquet")
    assert str(schema.field(0).type) == "date32[day]"  # data sem hora
    for field in list(schema)[1:]:
        assert str(field.type) == "double"


def test_in_memory_tables_keep_datetime_for_calculations():
    full_bronze()

    tables = transform.build_silver()

    assert pd.api.types.is_datetime64_any_dtype(tables["cdi"]["data"])
    assert pd.api.types.is_datetime64_any_dtype(tables["ipca"]["mes_referencia"])


# Conversões de cada série

def test_cdi_keeps_rate_in_percent_and_builds_index():
    bronze("cdi", date(2026, 10, 28), sgs(("26/10/2026", "1.0"), ("27/10/2026", "2.0")))

    df = transform.build_silver()["cdi"]

    assert df["data"].tolist() == [pd.Timestamp("2026-10-26"), pd.Timestamp("2026-10-27")]
    assert df["taxa_diaria_pct"].tolist() == [1.0, 2.0]  # em %, como vem do SGS
    assert df["indice"].tolist() == pytest.approx([101.0, 101.0 * 1.02])  # inclui a taxa do próprio dia


def test_cdi_index_ratio_gives_period_return():
    bronze("cdi", date(2026, 10, 28), sgs(("26/10/2026", "0.05"), ("27/10/2026", "0.05"), ("28/10/2026", "0.05")))

    df = transform.build_silver()["cdi"]

    # Retorno de 26/10 (exclusive) a 28/10 (inclusive) = 2 dias de taxa.
    assert df["indice"].iloc[2] / df["indice"].iloc[0] - 1 == pytest.approx(1.0005**2 - 1)


def test_ipca_month_and_index():
    bronze("ipca", date(2026, 10, 15), sgs(("01/08/2026", "-0.32"), ("01/09/2026", "0.82")))

    df = transform.build_silver()["ipca"]

    assert df["mes_referencia"].tolist() == [pd.Timestamp("2026-08-01"), pd.Timestamp("2026-09-01")]
    assert df["variacao_mensal_pct"].tolist() == [-0.32, 0.82]
    assert df["indice"].tolist() == pytest.approx([99.68, 99.68 * 1.0082])


def test_dolar_ptax_values():
    bronze("dolar_ptax", date(2026, 10, 29), sgs(("29/10/2026", "5.3744")))

    df = transform.build_silver()["dolar_ptax"]

    assert df.to_dict("records") == [{"data": pd.Timestamp("2026-10-29"), "ptax_venda": 5.3744}]


def test_ibovespa_keeps_only_date_and_close():
    bronze("ibovespa", date(2026, 10, 29), yf_rows(("2026-10-28", 171006.0)))

    df = transform.build_silver()["ibovespa"]

    assert df.to_dict("records") == [{"data": pd.Timestamp("2026-10-28"), "fechamento": 171006.0}]


# União da bronze, deduplicação e ordenação

def test_silver_unions_all_bronze_files():
    bronze("cdi", date(2026, 10, 28), sgs(("27/10/2026", "0.05")))
    bronze("cdi", date(2026, 10, 29), sgs(("28/10/2026", "0.05")))

    df = transform.build_silver()["cdi"]

    assert df["data"].dt.strftime("%d/%m").tolist() == ["27/10", "28/10"]


def test_duplicate_date_keeps_most_recent_ingestion():
    # Linha provisória salva antes e a consolidada depois: fica a do arquivo mais recente.
    bronze("ibovespa", date(2026, 10, 28), yf_rows(("2026-10-28", 171006.09375)))
    bronze("ibovespa", date(2026, 10, 29), yf_rows(("2026-10-28", 171006.0)))

    df = transform.build_silver()["ibovespa"]

    assert df["fechamento"].tolist() == [171006.0]


def test_duplicate_resolution_follows_ingestion_date_not_write_order():
    bronze("cdi", date(2026, 10, 29), sgs(("28/10/2026", "0.2")))  # mais recente, gravado primeiro
    bronze("cdi", date(2026, 10, 28), sgs(("28/10/2026", "0.1")))

    assert transform.build_silver()["cdi"]["taxa_diaria_pct"].tolist() == [0.2]


def test_silver_is_sorted_by_date():
    bronze("dolar_ptax", date(2026, 10, 28), sgs(("28/10/2026", "5.3"), ("02/01/2026", "6.1"), ("15/05/2026", "5.7")))

    df = transform.build_silver()["dolar_ptax"]

    assert df["data"].is_monotonic_increasing
    assert df.index.tolist() == [0, 1, 2]


def test_index_is_accumulated_after_sorting():
    bronze("cdi", date(2026, 10, 28), sgs(("28/10/2026", "2.0"), ("27/10/2026", "1.0")))

    df = transform.build_silver()["cdi"]

    assert df["indice"].tolist() == pytest.approx([101.0, 101.0 * 1.02])


def test_no_gaps_are_filled():
    # Sexta e segunda: o fim de semana não vira linha na silver.
    bronze("dolar_ptax", date(2026, 10, 27), sgs(("23/10/2026", "5.03"), ("26/10/2026", "5.50")))

    assert len(transform.build_silver()["dolar_ptax"]) == 2


# Dados inválidos e séries ausentes

def test_invalid_values_are_dropped_with_warning(caplog):
    bronze("cdi", date(2026, 10, 28), sgs(("26/10/2026", "0.05"), ("27/10/2026", ""), ("28/10/2026", "abc")))

    df = transform.build_silver()["cdi"]

    assert len(df) == 1
    assert "cdi: 2 registro(s) inválido(s) descartado(s)" in caplog.text


def test_invalid_dates_are_dropped():
    bronze("dolar_ptax", date(2026, 10, 28), sgs(("31/02/2026", "5.0"), ("28/10/2026", "5.3")))

    assert len(transform.build_silver()["dolar_ptax"]) == 1


def test_missing_serie_is_skipped_and_others_are_built(caplog):
    bronze("cdi", date(2026, 10, 28), sgs(("28/10/2026", "0.05")))

    tables = transform.build_silver()

    assert set(tables) == {"cdi"}
    assert not (utils.SILVER_DIR / "ipca.parquet").exists()
    assert "ipca: nenhum dado na bronze; tabela silver não gerada" in caplog.text


def test_empty_bronze_file_is_ignored():
    bronze("cdi", date(2026, 10, 27), [])
    bronze("cdi", date(2026, 10, 28), sgs(("28/10/2026", "0.05")))

    assert len(transform.build_silver()["cdi"]) == 1


def test_no_bronze_at_all_builds_nothing():
    assert transform.build_silver() == {}
    assert not utils.SILVER_DIR.exists()


def test_other_files_in_bronze_folder_are_ignored():
    bronze("cdi", date(2026, 10, 28), sgs(("28/10/2026", "0.05")))
    (utils.RAW_DIR / "cdi" / "anotacoes.txt").write_text("não é bronze")

    assert len(transform.build_silver()["cdi"]) == 1


# run_transformation (etapa do pipeline)

def test_run_transformation_builds_silver():
    full_bronze()

    transform.run_transformation()

    assert len(list(utils.SILVER_DIR.iterdir())) == 4


def test_run_transformation_logs_failure_without_raising(monkeypatch, log_dir, caplog):
    from datetime import datetime

    def broken():
        raise OSError("disco cheio")

    monkeypatch.setattr(transform, "build_silver", broken)
    utils.configure_logging("daily", datetime(2026, 10, 29, 9, 0, 0))

    transform.run_transformation()  # não levanta exceção

    content = (log_dir / "daily_20261029_090000.log").read_text(encoding="utf-8")
    assert "transformação: falha na silver (OSError: disco cheio)" in content


# Recalculada a cada execução

def test_rebuild_overwrites_previous_silver():
    bronze("cdi", date(2026, 10, 28), sgs(("28/10/2026", "0.05")))
    transform.build_silver()
    bronze("cdi", date(2026, 10, 29), sgs(("29/10/2026", "0.05")))

    transform.build_silver()

    assert len(read_silver("cdi")) == 2

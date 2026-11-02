"""Teste de fumaça do dashboard: roda o app do Streamlit sobre uma gold sintética e confere que não quebra."""

import pytest
from streamlit.testing.v1 import AppTest

from src import transform, utils
from tests.test_gold import sample_silver

APP = str(utils.ROOT_DIR / "dashboard" / "app.py")


@pytest.fixture
def gold_dir(monkeypatch):
    transform.build_gold(sample_silver())
    monkeypatch.setenv("GOLD_DIR", str(utils.GOLD_DIR))
    return utils.GOLD_DIR


def run_app():
    return AppTest.from_file(APP, default_timeout=60).run()


def test_dashboard_renders_all_tabs_without_errors(gold_dir):
    at = run_app()

    assert not at.exception
    assert [t.label for t in at.tabs] == ["Comparação", "Juros e inflação", "Bolsa", "Câmbio"]
    assert at.metric[0].label == "CDI anualizado"
    assert len(at.get("plotly_chart")) == 7


@pytest.mark.parametrize("period", ["24M", "36M", "No ano", "Tudo", "Personalizado"])
def test_dashboard_period_filter(gold_dir, period):
    at = run_app()

    at.segmented_control[0].set_value(period).run()

    assert not at.exception
    assert any(c.value.startswith("Período:") for c in at.caption)


def test_dashboard_uses_brazilian_number_format(gold_dir):
    at = run_app()

    cdi = next(m for m in at.metric if m.label == "CDI anualizado")
    assert "," in cdi.value and cdi.value.endswith("%")


def test_dashboard_without_data_shows_error(tmp_path, monkeypatch):
    monkeypatch.setenv("GOLD_DIR", str(tmp_path / "nao_existe"))

    at = run_app()

    assert not at.exception
    assert "Dados não encontrados" in at.error[0].value


def test_summary_is_an_expander_opened_by_default(gold_dir):
    at = run_app()

    sections = [e for e in at.expander if e.label.startswith("**")]
    assert [e.label for e in sections] == ["**Resumo**"]
    assert sections[0].proto.expanded
    # A análise por período (com o filtro) continua como cabeçalho, depois do Resumo.
    assert [h.value for h in at.header] == ["Análise por período"]


def test_simulation_shows_ipca_as_inflation_correction(gold_dir):
    at = run_app()

    labels = [m.label for m in at.metric]
    assert "Corrigido pelo IPCA" in labels
    assert "IPCA" not in labels  # o IPCA não aparece como se fosse um investimento

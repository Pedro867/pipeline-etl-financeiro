"""Funções auxiliares do pipeline: datas, conversão, gravação de arquivos e logs."""

import json
import logging
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT_DIR / "data" / "raw"
LOG_DIR = ROOT_DIR / "log"

YEARS_OF_HISTORY = 5


def five_years_before(today: date) -> date:
    """Mesma data 5 anos antes. Se hoje for 29/02, retorna 28/02."""
    try:
        return today.replace(year=today.year - YEARS_OF_HISTORY)
    except ValueError:
        return today.replace(year=today.year - YEARS_OF_HISTORY, day=28)


def dataframe_to_json(df: pd.DataFrame) -> list[dict]:
    """Converte o DataFrame do yfinance em registros com todas as colunas.

    A data vai para a chave `Date` como data local do pregão (AAAA-MM-DD), sem fuso.
    """
    records = df.reset_index()
    records["Date"] = records["Date"].dt.strftime("%Y-%m-%d")
    return records.to_dict(orient="records")


def raw_file_path(serie: str, ingestion_date: date) -> Path:
    """Caminho do arquivo bronze: data/raw/<serie>/<serie>_YYYYMMDD.json."""
    return RAW_DIR / serie / f"{serie}_{ingestion_date:%Y%m%d}.json"


def save_json(data: list[dict], serie: str, ingestion_date: date) -> Path:
    """Salva os registros na camada bronze, sobrescrevendo o arquivo do dia se ele existir."""
    path = raw_file_path(serie, ingestion_date)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def _record_date(record: dict) -> date:
    """Data de um registro bruto: `data` em dd/mm/aaaa (SGS) ou `Date` em AAAA-MM-DD (yfinance)."""
    if "data" in record:
        return datetime.strptime(record["data"], "%d/%m/%Y").date()
    return date.fromisoformat(record["Date"])


def _first_day_of_next_month(day: date) -> date:
    if day.month == 12:
        return date(day.year + 1, 1, 1)
    return date(day.year, day.month + 1, 1)


def get_start_date(serie: str, today: date, monthly: bool = False) -> date:
    """Data inicial da extração.

    Sem arquivos anteriores a hoje: carga completa (5 anos). Caso contrário: o dia
    seguinte à maior data de dado do último arquivo anterior a hoje. Ignorar o
    arquivo de hoje faz uma reexecução no mesmo dia buscar o mesmo período e
    sobrescrever esse arquivo.

    Em séries mensais, o SGS devolve o mês que contém a data inicial; por isso a
    busca começa no 1º dia do mês seguinte ao último dado.
    """
    today_file = raw_file_path(serie, today).name
    previous_files = sorted(
        path for path in (RAW_DIR / serie).glob(f"{serie}_*.json") if path.name < today_file
    )
    if not previous_files:
        return five_years_before(today)

    records = json.loads(previous_files[-1].read_text(encoding="utf-8"))
    last_date = max(_record_date(record) for record in records)
    if monthly:
        return _first_day_of_next_month(last_date)
    return last_date + timedelta(days=1)


def configure_logging(flow: str, started_at: datetime) -> logging.Logger:
    """Configura o log do pacote `src`: tudo no terminal e erros em log/<fluxo>_YYYYMMDD_HHMMSS.log.

    O arquivo só é criado quando o primeiro erro é registrado (`delay=True`).
    """
    LOG_DIR.mkdir(exist_ok=True)
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s", "%Y-%m-%d %H:%M:%S")

    console = logging.StreamHandler()
    console.setFormatter(formatter)

    log_file = logging.FileHandler(
        LOG_DIR / f"{flow}_{started_at:%Y%m%d_%H%M%S}.log", encoding="utf-8", delay=True
    )
    log_file.setLevel(logging.ERROR)
    log_file.setFormatter(formatter)

    logger = logging.getLogger("src")
    logger.setLevel(logging.INFO)
    logger.handlers = [console, log_file]
    return logger

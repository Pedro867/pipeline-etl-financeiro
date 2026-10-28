# Pipeline de Indicadores de Mercado

Pipeline de dados (ETL) que coleta indicadores de mercado em fontes públicas, trata as séries e as organiza em uma base que alimenta um dashboard para a equipe de **Inteligência Comercial**.

---

## Contexto

A equipe de Inteligência Comercial acompanha diariamente juros, inflação, câmbio e bolsa para embasar conversas com clientes. Hoje esse acompanhamento é manual.

Este projeto automatiza o processo:

1. **Extração:** coleta das séries em fontes públicas.
2. **Transformação:** padronização e tratamento dos dados.
3. **Carga:** armazenamento em uma base organizada.
4. **Dashboard:** visualização final para a equipe comercial (o produto final do projeto).

## Indicadores

| Indicador | Frequência | O que representa | Fonte |
|---|---|---|---|
| **CDI** | Diária (dias úteis) | Taxa média dos empréstimos entre bancos; principal referência de rentabilidade da renda fixa ("% do CDI"). | API SGS · Banco Central |
| **IPCA** | Mensal | Índice oficial de inflação (IBGE); mostra se um investimento teve ganho real ou apenas nominal. | API SGS · Banco Central |
| **Dólar PTAX venda** | Diária (dias úteis) | Taxa de câmbio de referência do Banco Central; baliza contratos e investimentos internacionais. | API SGS · Banco Central |
| **Ibovespa** | Diária (pregões) | Principal índice de ações da B3; termômetro da renda variável brasileira. | `yfinance` · ticker `^BVSP` |

O período de coleta é dos **últimos 5 anos**.

As séries têm frequências (diária e mensal) e naturezas (taxa, índice e cotação) diferentes, além de calendários distintos (dias úteis do BCB e pregões da B3). Ainda falta decidir como conciliar essas diferenças.

## Escopo

| Etapa | O que precisa ser feito |
|---|---|
| **Extração (E)** | Coletar as quatro séries dos últimos 5 anos: as do Banco Central via API SGS e o Ibovespa via `yfinance`. |
| **Transformação (T)** | Padronizar datas e tipos, tratar dias sem dado (fins de semana, feriados, faltantes) e calcular as métricas que o dashboard usar (por exemplo, retorno acumulado, variação em 12 meses, base 100). |
| **Carga (L)** | Salvar os dados tratados em uma base organizada (SQLite, parquet ou CSVs estruturados). |
| **Dashboard** | Montar a visualização final com gráficos, indicadores e comparações escolhidos para atender a equipe comercial. |
| **Bônus** | Atualização incremental: baixar apenas os dados novos a cada execução. |

## Tecnologias

- **Python 3.12.3** com **PySpark** para o processamento dos dados (requer Java instalado).
- **requests** para as chamadas à API SGS do Banco Central.
- **yfinance** para a cotação do Ibovespa.
- **pytest** para os testes.
- Dados armazenados em **parquet**.
- Agendamento via **crontab**.

## Como executar

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m src.main_daily     # séries diárias (CDI, PTAX, Ibovespa), a partir da raiz do projeto
python -m src.main_monthly   # série mensal (IPCA), a partir da raiz do projeto
```

## Estrutura do projeto

```
pipeline-etl-financeiro/
├── data/
│   ├── raw/            # dados brutos extraídos
│   └── processed/      # dados tratados
├── docs/
│   ├── CONTEXT.md      # contexto do case e registro de decisões
│   └── ROADMAP.md      # fases e andamento
├── src/
│   ├── __init__.py
│   ├── extract.py      # extração (E)
│   ├── transform.py    # transformação (T)
│   ├── load.py         # carga (L)
│   ├── utils.py        # funções auxiliares (ex.: salvar arquivos)
│   ├── main_daily.py   # ponto de entrada: séries diárias
│   └── main_monthly.py # ponto de entrada: série mensal (IPCA)
├── .gitignore
├── README.md
└── requirements.txt
```

## Documentação

- [docs/CONTEXT.md](docs/CONTEXT.md): contexto do case, especificação e registro de decisões.
- [docs/ROADMAP.md](docs/ROADMAP.md): fases e andamento do projeto.

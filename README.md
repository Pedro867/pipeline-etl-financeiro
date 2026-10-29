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

- **Python 3.12.3** com **pandas** para a transformação dos dados.
- **requests** para as chamadas à API SGS do Banco Central.
- **yfinance** para a cotação do Ibovespa.
- **pyarrow** para gravar e ler os arquivos parquet.
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

## Agendamento

As execuções são agendadas com o `crontab`, no horário local da máquina (`America/Sao_Paulo`):

| Fluxo | Quando | Por quê |
|---|---|---|
| Diário (CDI, PTAX, Ibovespa) | Todos os dias, às 09:00 | Antes da abertura da B3, com todas as séries em D-1: o CDI sai em D+1, e o Ibovespa é buscado só até o dia anterior, já consolidado. Nos fins de semana a execução não encontra dado novo e não salva arquivo. |
| Mensal (IPCA) | Dias 8 a 20, às 10:00 | O IBGE divulga o IPCA por volta do dia 10, às 9h, mas o dia exato muda de mês para mês. Antes da divulgação, a execução não encontra dado e não salva arquivo; depois, entra no máximo 1 dia após a divulgação. |

Linhas do crontab (`crontab -e`), trocando `<caminho-do-projeto>` pelo caminho absoluto do projeto:

```cron
# Pipeline de indicadores: fluxo diário (CDI, PTAX, Ibovespa)
0 9 * * * cd <caminho-do-projeto> && .venv/bin/python -m src.main_daily > /dev/null 2>&1
# Pipeline de indicadores: fluxo mensal (IPCA)
0 10 8-20 * * cd <caminho-do-projeto> && .venv/bin/python -m src.main_monthly > /dev/null 2>&1
# Pipeline de indicadores: roda os dois fluxos ao ligar a máquina (espera 2 min pela internet)
@reboot sleep 120; cd <caminho-do-projeto> && .venv/bin/python -m src.main_daily > /dev/null 2>&1; .venv/bin/python -m src.main_monthly > /dev/null 2>&1
```

A saída do terminal é descartada. Os erros de extração ficam em `log/<fluxo>_YYYYMMDD_HHMMSS.log`. Se a máquina estiver desligada no horário, o cron não roda a execução depois. Por isso, a linha `@reboot` roda os dois fluxos sempre que a máquina liga, e a carga incremental busca os dias perdidos. O `@reboot` **não** roda ao voltar da suspensão (tampa fechada); nesse caso, os dados são atualizados na próxima execução agendada ou na próxima vez que a máquina for ligada.

## Testes

```bash
pytest          # a partir da raiz do projeto
```

Os testes ficam em `tests/` e **não acessam a internet**: as respostas do SGS e do yfinance são simuladas, e as pastas `data/` e `log/` são trocadas por pastas temporárias. Eles cobrem:

- **`tests/test_utils.py`:**
  - datas (5 anos antes, incluindo 29/02, e a virada de mês e de ano);
  - conversão do DataFrame do yfinance para JSON (colunas e fuso);
  - gravação e sobrescrita dos arquivos;
  - cálculo da data inicial: carga completa, incremental, reexecução no mesmo dia e série mensal;
  - criação do log só quando há erro.
- **`tests/test_extract.py`:**
  - `fetch_sgs`: sucesso, "sem dado" (HTTP 404 ou 200), período de um dia só, erros 4xx, página HTML com status 200, JSON inválido, erros 5xx/429 e de rede com retentativa;
  - `fetch_yfinance`: período sem pregão, ticker inválido, limite de requisições, erros de rede e busca só até o dia anterior;
  - retentativas: 3 tentativas com intervalo de 10 s;
  - `run_extraction`: falha de uma série sem interromper as outras, um arquivo de log por execução e o fluxo completo.
- **`tests/test_transform.py`:** silver: esquema e tipos do parquet, conversão de cada série, índices acumulados, união da bronze com deduplicação pela ingestão mais recente, ordenação, sem preenchimento de dias, descarte de valores inválidos e série ausente.
- **`tests/test_main.py`:** séries e códigos configurados em cada ponto de entrada.

## Estrutura do projeto

```
pipeline-etl-financeiro/
├── data/
│   ├── raw/            # dados brutos extraídos
│   └── processed/
│       ├── silver/     # séries limpas e tipadas (parquet)
│       └── gold/       # métricas (parquet)
├── docs/
│   ├── CONTEXT.md      # contexto do case e registro de decisões
│   └── ROADMAP.md      # fases e andamento
├── src/
│   ├── __init__.py
│   ├── extract.py      # extração (E)
│   ├── transform.py    # transformação (T): silver e gold
│   ├── load.py         # carga (L)
│   ├── utils.py        # funções auxiliares (ex.: salvar arquivos)
│   ├── main_daily.py   # ponto de entrada: séries diárias
│   └── main_monthly.py # ponto de entrada: série mensal (IPCA)
├── tests/              # testes com pytest (sem acesso à internet)
│   ├── conftest.py     # fixtures: pastas temporárias e fontes simuladas
│   ├── test_utils.py
│   ├── test_extract.py
│   ├── test_transform.py
│   └── test_main.py
├── log/                # logs de erro (fora do Git, criada pelo pipeline)
├── .gitignore
├── README.md
└── requirements.txt
```

## Documentação

- [docs/CONTEXT.md](docs/CONTEXT.md): contexto do case, especificação e registro de decisões.
- [docs/ROADMAP.md](docs/ROADMAP.md): fases e andamento do projeto.

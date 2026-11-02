# Pipeline de Indicadores de Mercado
[![Pipeline de indicadores](https://github.com/Pedro867/pipeline-etl-financeiro/actions/workflows/pipeline.yml/badge.svg)](https://github.com/Pedro867/pipeline-etl-financeiro/actions/workflows/pipeline.yml)

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

| Etapa | O que faz |
|---|---|
| **Extração (E)** | Coleta as quatro séries dos últimos 5 anos: as do Banco Central via API SGS e o Ibovespa via `yfinance`. Salva o retorno das fontes em JSON (camada bronze, `data/raw`). |
| **Transformação (T)** | Padroniza datas e tipos, trata os dias sem dado (fins de semana, feriados, faltantes) e calcula as métricas usadas no dashboard, como retorno acumulado, variação em 12 meses e retorno real (camadas silver e gold). |
| **Carga (L)** | Grava as tabelas tratadas em parquet (`data/processed/silver` e `data/processed/gold`). |
| **Dashboard** | Mostra indicadores, comparações e gráficos para a equipe comercial (Streamlit). |
| **Atualização incremental** | Depois da primeira carga, baixa apenas os dados novos a cada execução. |

## Tecnologias

- **Python 3.12.3** com **pandas** para a transformação dos dados.
- **requests** para as chamadas à API SGS do Banco Central.
- **yfinance** para a cotação do Ibovespa.
- **pyarrow** para gravar e ler os arquivos parquet.
- **Streamlit** e **Plotly** para o dashboard.
- **pytest** para os testes.
- Dados armazenados em **parquet**.
- Agendamento via **GitHub Actions**.

## Como executar

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m src.main_daily     # séries diárias (CDI, PTAX, Ibovespa), a partir da raiz do projeto
python -m src.main_monthly   # série mensal (IPCA), a partir da raiz do projeto
streamlit run dashboard/app.py   # dashboard local, em http://localhost:8501
```

Cada fluxo faz a extração (bronze) e, em seguida, recalcula a camada silver (`data/processed/silver/`) e a gold (`data/processed/gold/`).

## Agendamento

O pipeline roda no **GitHub Actions** ([.github/workflows/pipeline.yml](.github/workflows/pipeline.yml)), sem depender de uma máquina ligada. Ao fim de cada execução, o workflow faz commit de `data/` e `log/` no repositório. Assim, a bronze fica guardada para a carga incremental da próxima execução, e a gold fica disponível para o dashboard.

| Fluxo | Quando (Brasília) | Cron (UTC) | Por quê |
|---|---|---|---|
| Diário (CDI, PTAX, Ibovespa) | Todos os dias, 09:17 | `17 12 * * *` | Antes da abertura da B3, com todas as séries em D-1: o CDI sai em D+1, e o Ibovespa é buscado só até o dia anterior, já consolidado. Nos fins de semana a execução não encontra dado novo e não salva arquivo. |
| Mensal (IPCA) | Dias 8 a 20, 10:17 | `17 13 8-20 * *` | O IBGE divulga o IPCA por volta do dia 10, às 9h, mas o dia exato muda de mês para mês. Antes da divulgação, a execução não encontra dado e não salva arquivo; depois, entra no máximo 1 dia após a divulgação. |

- **Fuso horário:** o agendamento do GitHub é em UTC (Brasília = UTC−3). O workflow define `TZ=America/Sao_Paulo` para que os arquivos sejam nomeados com a data de Brasília.
- **Minuto 17:** o GitHub não garante o horário exato, e os horários cheios costumam atrasar mais. Se uma execução atrasar ou for pulada, a carga incremental busca os dias perdidos na seguinte.
- **Execução manual:** na aba **Actions** do GitHub, escolha "Pipeline de indicadores" → **Run workflow** e selecione o fluxo (`daily`, `monthly` ou `ambos`).
- **Falhas:** se alguma série falhar na extração, ou se a transformação falhar, a execução termina **marcada como falha** e o GitHub avisa por e-mail. Mesmo assim, os dados das séries que deram certo e o log do erro são versionados.
- **Uma execução por vez:** duas execuções nunca rodam ao mesmo tempo, para os commits de dados não se chocarem.
- **Logs:** o log completo de cada execução fica na aba Actions. Os erros de extração também ficam versionados em `log/<fluxo>_YYYYMMDD_HHMMSS.log`.

## Dashboard

O dashboard ([dashboard/app.py](dashboard/app.py)) usa Streamlit e Plotly. Ele lê as tabelas da gold e calcula só o que depende do período escolhido: a comparação em base 100, a simulação de R$ 1.000.000,00 e o drawdown máximo. O público e a justificativa das visualizações ainda serão definidos.

- **Local:** `streamlit run dashboard/app.py`, a partir da raiz do projeto.
- **Nuvem:** **[pipeline-etl-financeiro.streamlit.app](https://pipeline-etl-financeiro.streamlit.app/)**, no Streamlit Community Cloud, apontando para `dashboard/app.py`. O app lê a gold versionada no repositório e se atualiza a cada commit do pipeline.
- **Organização:** o **Resumo** fica no topo, numa seção expansível que começa aberta (indicadores do dia, rentabilidade nominal e real e data do último dado), e não depende de período. Abaixo dele, o filtro de período (12M, 24M, 36M, no ano, tudo ou personalizado) vale para as abas **Comparação**, **Juros e inflação**, **Bolsa** e **Câmbio**.
- **Simulação de R$ 1.000.000,00:** mostra quanto o valor aplicado no início do período vale hoje no Ibovespa, no CDI e no dólar. O IPCA aparece como **"Corrigido pelo IPCA"**: o valor que os R$ 1.000.000,00 precisariam ter hoje só para manter o poder de compra.
- **Cores:** cada indicador mantém a mesma cor em todos os gráficos (Ibovespa azul, CDI laranja, dólar verde, IPCA amarelo), nos temas claro e escuro. Todo gráfico tem legenda e uma tabela com os dados ("Ver dados").

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
  - `fetch_yfinance`: período sem pregão, ticker inválido, limite de requisições, erros de rede, busca só até o dia anterior e descarte de linhas fora do período pedido;
  - retentativas: 3 tentativas com intervalo de 10 s;
  - `run_extraction`: falha de uma série sem interromper as outras, um arquivo de log por execução e o fluxo completo.
- **`tests/test_transform.py`:** silver: esquema e tipos do parquet, conversão de cada série, índices acumulados, união da bronze com deduplicação pela ingestão mais recente, ordenação, sem preenchimento de dias, descarte de valores inválidos e série ausente.
- **`tests/test_gold.py`:** gold, com séries sintéticas: início das janelas e "último dado anterior", retornos nominais e reais (alinhados ao IPCA, pela fórmula de Fisher), excesso e % do CDI, médias móveis por linha, mínima/máxima com janela completa, distância da máxima em 5 anos, Ibovespa em dólar só nas datas em comum, retorno anual, IPCA 12M e anualizado, juros reais, tipos do parquet, séries ausentes e falhas registradas no log.
- **`tests/test_main.py`:** séries e códigos configurados em cada ponto de entrada.
- **`tests/test_dashboard.py`:** roda o dashboard sobre uma gold sintética (todas as abas e todos os períodos do filtro), confere o formato brasileiro dos números e a mensagem quando não há dados.

## Estrutura do projeto

```
pipeline-etl-financeiro/
├── data/
│   ├── raw/            # dados brutos extraídos
│   └── processed/
│       ├── silver/     # séries limpas e tipadas (parquet)
│       └── gold/       # métricas (parquet)
├── docs/
│   ├── CONTEXT.md      # contexto, requisitos e registro de decisões
│   └── ROADMAP.md      # fases e andamento
├── dashboard/
│   └── app.py          # dashboard (Streamlit): só lê a gold
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
│   ├── test_gold.py
│   ├── test_main.py
│   └── test_dashboard.py
├── log/                # logs de erro (versionados, criados pelo pipeline)
├── .github/workflows/
│   └── pipeline.yml    # agendamento no GitHub Actions
├── .gitignore
├── README.md
└── requirements.txt
```

## Documentação

- [docs/CONTEXT.md](docs/CONTEXT.md): contexto, requisitos, métricas, esquema das tabelas e registro de decisões.
- [docs/ROADMAP.md](docs/ROADMAP.md): fases e andamento do projeto.

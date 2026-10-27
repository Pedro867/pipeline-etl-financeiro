# Contexto do Projeto — Pipeline de Indicadores de Mercado

## ⚠️ Regra de governança

**Nenhuma decisão (técnica, de arquitetura, de ferramenta, de tratamento de dados ou de dashboard) deve ser tomada sem aprovação explícita.**

- Opções podem ser levantadas, pesquisadas e comparadas, mas devem ser registradas como **propostas**, nunca como definição.
- Toda decisão aprovada deve ser registrada na seção [Registro de decisões](#registro-de-decisões) com data e justificativa.
- Na dúvida, perguntar antes de agir.

---

## 1. O desafio

A equipe de **Inteligência Comercial** acompanha diariamente indicadores de mercado (juros, inflação, câmbio e bolsa) para embasar conversas com clientes. Hoje esse acompanhamento é **manual**.

Objetivo: construir um **pipeline de dados (ETL)** que:

1. Extrai as séries de fontes públicas;
2. Trata os dados;
3. Organiza-os em uma base;
4. Alimenta um **dashboard** que apresente essas informações.

O **produto final é o dashboard**. As decisões sobre ele (quais gráficos, quais comparações, como exibir cada informação e em qual ferramenta) são nossas. Não existe uma única resposta certa — existe uma **escolha bem justificada**.

---

## 2. Os dados

| Indicador | Frequência | Natureza | Fonte | Uso pela equipe comercial |
|---|---|---|---|---|
| **CDI** | Diária (dias úteis) | Taxa | API SGS · Banco Central | Principal referência de rentabilidade da renda fixa; investimentos conservadores são comparados em "% do CDI". |
| **IPCA** | Mensal | Índice de inflação (IBGE) | API SGS · Banco Central | Define se um investimento teve ganho **real** (acima da inflação) ou apenas nominal. |
| **Dólar PTAX venda** | Diária (dias úteis) | Cotação de câmbio | API SGS · Banco Central | Baliza contratos, investimentos internacionais e a leitura de cenário macroeconômico. |
| **Ibovespa** | Diária (pregões) | Índice de ações (B3) | `yfinance` · ticker `^BVSP` | Termômetro mais citado da renda variável brasileira. |

### Pontos de atenção

- As séries têm **frequências diferentes** (diárias e mensal) e **naturezas diferentes** (taxas, índices e cotações).
- Os calendários também diferem: dias úteis do BCB vs. pregões da B3 (feriados podem não coincidir).
- Como conciliar isso no tratamento e no dashboard **faz parte das decisões a serem tomadas** (pendente de aprovação).
### API SGS (Banco Central)

URL de consulta:

```
https://api.bcb.gov.br/dados/serie/bcdata.sgs.{CODE}/dados?formato=json&dataInicial={dd/mm/aaaa}&dataFinal={dd/mm/aaaa}
```

| Série | Código SGS | O que a API retorna (amostra de set/2026) |
|---|---|---|
| CDI | `12` | Taxa **diária** em % ao dia (ex.: `0.051660`), só em dias úteis. |
| IPCA | `433` | **Variação mensal** em % (ex.: `0.82`), não o número-índice. Um registro por mês, datado no dia 1. |
| Dólar PTAX venda | `1` | Cotação em R$/US$ (ex.: `5.1570`), só em dias úteis. |

Formato de retorno: lista JSON de `{"data": "dd/mm/aaaa", "valor": "<texto>"}`. Tanto a data quanto o valor vêm como **texto**.

**Período de coleta:** a data final é o dia atual da execução e a data inicial é a mesma data 5 anos antes. Se o dia atual for 29/02, a data inicial é 28/02.

### yfinance (Ibovespa)

Chamada usada para explorar a fonte: `yf.download("^BVSP", start=..., end=..., auto_adjust=False)`. Ela retorna um **DataFrame do pandas** (o pandas vem como dependência do yfinance).

| Aspecto | O que a consulta mostrou (out/2026) |
|---|---|
| Colunas | `Adj Close`, `Close`, `High`, `Low`, `Open`, `Volume`, como **MultiIndex** (preço × ticker), mesmo com um ticker só. |
| Índice | `Date` (`datetime64`, sem fuso), só em dias de pregão. |
| Tipos | Preços em `float64` (pontos do índice) e `Volume` em `int64`. |
| `Adj Close` vs `Close` | Iguais no `^BVSP` (índice não tem dividendos nem desdobramentos). |
| `end` | É **exclusivo**: para incluir o dia D, é preciso passar D+1. |
| Dia corrente | Se o pregão do dia ainda não fechou, vem uma linha **parcial**: valores intradiários que ainda mudam e `Volume = 0`. |
| Avisos | O yfinance 1.7.0 emite `Pandas4Warning` (uso de `inplace`). Não afeta os dados. |

**Ponto a verificar:** entre 23/10/2026 (205.083) e 26/10/2026 (176.608), o `Close` cai cerca de 14% em um dia, e o `Volume` de 26/10 é cerca de 4 vezes o normal. Pode ser um evento real de mercado ou um erro da fonte; isso precisa ser confirmado antes de usar o dado.

---

## 3. Especificação do pipeline

### Extração (E)
- Coletar as quatro séries cobrindo os **últimos 5 anos**.
- Séries do Banco Central: via API SGS (códigos a pesquisar).
- Ibovespa: via biblioteca `yfinance`.

### Transformação (T)
- Padronizar **datas e tipos**.
- Tratar **dias sem dado** (fins de semana, feriados, faltantes).
- Calcular o que for necessário para o dashboard — exemplos citados no case: retornos acumulados, variação em 12 meses, comparações em base 100.
- **Documentar cada decisão no README.**

### Carga (L)
- Salvar os dados tratados em uma base organizada — opções citadas: **SQLite, parquet ou CSVs estruturados** — que alimente o dashboard.

### Dashboard
- Ferramenta livre — opções citadas: Streamlit, Power BI, Excel, página HTML.
- Escolher gráficos e indicadores e como organizá-los.
- **Explicar no README**: para quem é o dashboard e por que as visualizações respondem bem às necessidades de quem o usa.

### Bônus (opcional)
- Suportar **atualização incremental**: baixar apenas os dados novos a cada execução.

---

## 4. Entregáveis esperados

- [ ] Pipeline ETL funcional (extração, transformação, carga).
- [ ] Base de dados tratada e organizada.
- [ ] Dashboard.
- [ ] README documentando as decisões de transformação, o público do dashboard e a justificativa das visualizações.
- [ ] (Bônus) Atualização incremental.

---

## Registro de decisões

> Somente decisões **aprovadas** entram aqui.

| Data | Decisão | Justificativa | Aprovado |
|---|---|---|---|
| 2026-10-27 | Estrutura de pastas do projeto: `data/raw/`, `data/processed/`, `docs/`, `src/` (`extract.py`, `transform.py`, `load.py`, `main.py`), `.gitignore`, `README.md` e `requirements.txt`. | Separa dados brutos dos tratados e organiza o código em um módulo por etapa do ETL, com `main.py` como ponto de entrada. | ✅ |
| 2026-10-27 | A pasta `data/` não é versionada (está no `.gitignore`). | O volume de dados será grande demais para o repositório. O pipeline precisa criar `data/raw/` e `data/processed/` ao rodar. | ✅ |
| 2026-10-27 | Stack: Python com **PySpark** (processamento), **requests** (chamadas HTTP) e **pytest** (testes). Dependências com versão fixa em `requirements.txt`, instaladas em um ambiente virtual `.venv`. | Escolha do responsável pelo projeto. | ✅ |
| 2026-10-27 | Formato dos dados: **parquet**. | É o formato nativo do PySpark. | ✅ |
| 2026-10-27 | O pipeline é executado por `src/main.py`, com o comando `python -m src.main` a partir da raiz do projeto. Os imports usam o pacote `src` (ex.: `from src.extract import ...`). | Um único ponto de entrada para rodar o ETL. O `-m` trata `src/` como pacote, o que deixa os imports iguais no `main.py` e nos testes com pytest. | ✅ |
| 2026-10-27 | Versão do Python: **3.12.3**. | Versão do ambiente de desenvolvimento. | ✅ |
| 2026-10-27 | Agendamento via **crontab**. | Escolha do responsável pelo projeto. | ✅ |
| 2026-10-27 | Códigos SGS: CDI = `12`, IPCA = `433`, Dólar PTAX venda = `1`. | Pesquisados no SGS e confirmados com uma consulta à API. | ✅ |
| 2026-10-27 | Período de extração: da data atual menos 5 anos até a data atual. Se o dia atual for 29/02, a data inicial é 28/02. | O case pede os últimos 5 anos. | ✅ |
| 2026-10-27 | Adicionar **yfinance** às dependências. | O case pede essa biblioteca para o Ibovespa. | ✅ |
| 2026-10-27 | O crontab só será configurado quando todo o ETL estiver pronto. | Escolha do responsável pelo projeto. | ✅ |

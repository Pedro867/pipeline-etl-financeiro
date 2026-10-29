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

**Período sem dado** (ex.: feriado de 07/09/2026, ou fim de semana + feriado de 05/09 a 07/09): a API responde **HTTP 404**, com o corpo abaixo, e não uma lista vazia `[]`. Com dado, a resposta é HTTP 200.

```json
{"erro": {"statusCode": 404, "detail": "br.gov.bcb.pec.sgs.comum.excecoes.SGSNegocioException: Value(s) not found"}}
```

**Observado na primeira carga (28/10/2026, às 21h):**
- O **CDI** mais recente era o de 27/10: o dado do dia sai em D+1.
- Na série **mensal (IPCA)**, a API devolve o mês que *contém* a `dataInicial`. Pedindo de 28/10/2021 em diante, o primeiro registro veio com data 01/10/2021, e pedir a partir de 02/09/2026 traz o de 01/09/2026.
- No **Ibovespa** (yfinance), a linha do dia atual veio **provisória** mesmo depois do fechamento: `Volume = 0` e `Close` fracionado. A linha de 27/10, consultada em 28/10, já estava consolidada (`Close` 175.710,0 e volume preenchido).

Por isso, um `raise_for_status()` do `requests` trataria "sem dado" como erro. Para diferenciar, o código precisa verificar o 404 junto com o texto `Value(s) not found`.

### Mapa de erros das fontes

Levantado com testes nas fontes em 28/10/2026. A coluna "Retentar?" foi aprovada em 28/10/2026 (ver registro de decisões).

**API SGS (`requests`)**

| Situação | Resposta observada | Retentar? |
|---|---|---|
| Sucesso | HTTP 200, lista JSON | — |
| Período sem dado (feriado, fim de semana) | HTTP 404, `Value(s) not found` | Não é erro (decidido: não salva arquivo) |
| Data em formato inválido | HTTP 400, `Invalid initial date` | Não: é erro no código |
| Janela maior que 10 anos (série diária) | HTTP 406, "janela de consulta de, no máximo, 10 anos" | Não: é erro no código (os 5 anos estão dentro do limite) |
| Código de série inexistente | ⚠️ **HTTP 200** com uma **página HTML** ("Requisição inválida!"), depois de cerca de 30 s | Não: é erro de configuração. O status 200 sozinho não basta; é preciso validar o `Content-Type` ou se o corpo é JSON. |
| Timeout ou falha de conexão (`requests.Timeout`, `ConnectionError`) | Não observado (esperado em instabilidade) | Sim |
| Erro do servidor (HTTP 5xx) ou excesso de requisições (429) | Não observado (esperado em instabilidade) | Sim |
| Corpo que não é JSON, ou JSON fora do formato `[{"data", "valor"}]` | Não observado | A definir |

**yfinance**

| Situação | `yf.download(...)` | `yf.Ticker(...).history(..., raise_errors=True)` | Retentar? |
|---|---|---|---|
| Ticker inválido | ⚠️ **Não lança exceção**: retorna DataFrame vazio e só imprime o erro no terminal | `YFTzMissingError` | Não: é erro de configuração |
| Período sem pregão (fim de semana, feriado) | ⚠️ **Não lança exceção**: retorna DataFrame vazio | `YFPricesMissingError` | Não é erro (equivale ao 404 do SGS) |
| Limite de requisições do Yahoo | — | `YFRateLimitError` | Sim |
| Timeout ou falha de conexão | — | Erro de rede | Sim |

Com o `yf.download`, um ticker inválido e um período sem pregão dão o **mesmo resultado** (DataFrame vazio), e o pipeline não teria como diferenciar os dois casos. Com o `Ticker.history(raise_errors=True)`, cada caso gera uma exceção diferente.

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

**Fuso horário:** o `Ticker.history` (a função adotada) devolve o índice **com fuso** (`America/Sao_Paulo` no `^BVSP`), diferente do `yf.download`, que devolve sem fuso. Na conversão para JSON, isso precisa ser levado em conta para a data não mudar.

**Queda de 26/10/2026, verificada em 28/10/2026:** o `Close` cai de 205.083 (23/10) para 176.608 (−13,88%). Cruzando com fontes independentes, a conclusão é que se trata de um **evento real de mercado**, e não de um erro da fonte:

| Fonte | Variação em 26/10 |
|---|---|
| `^BVSP` (Ibovespa) | −13,88% |
| BOVA11 (ETF do Ibovespa na B3) | −14,51% |
| EWZ (ETF de Brasil na bolsa de Nova York, outra bolsa) | −19,82% |
| ITUB4 / PETR4 | −13,66% / −8,18% |
| **PTAX venda (SGS 1, Banco Central)** | **+9,19%** (5,0377 → 5,5007) |

No intradiário de 30 em 30 minutos, a queda acontece toda na **abertura**: o índice vai de 205.070 a 169.516 nos primeiros 30 min e depois recupera parte. É o comportamento típico de um choque ocorrido no fim de semana. A causa não foi investigada.

Observação: o par `BRL=X` do Yahoo mostra o salto do dólar só em 27/10, um dia depois da PTAX oficial, provavelmente pelo fuso de Londres. Ele não é usado no pipeline, mas mostra que datas de fontes diferentes podem estar defasadas.

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
| 2026-10-28 | Extração com uma função por fonte: `fetch_sgs` (genérica, recebe o código SGS) e `fetch_yfinance`. | Nomes padronizados. As três séries do BCB usam a mesma API. | ✅ |
| 2026-10-28 | A função que salva os arquivos fica em `src/utils.py` (arquivo novo na estrutura). | Separa a gravação da busca, o que permite testar a busca sem gravar arquivo. | ✅ |
| 2026-10-28 | A conversão do retorno do `fetch_yfinance` (DataFrame) para JSON fica em `src/utils.py`. O `fetch_yfinance` chama essa conversão e já retorna JSON. | Funções auxiliares ficam concentradas em `utils.py`, e as duas buscas (`fetch_sgs` e `fetch_yfinance`) retornam o mesmo tipo, então os pontos de entrada tratam todas as séries do mesmo jeito. | ✅ |
| 2026-10-28 | Camada bronze (`data/raw`): um arquivo por execução, com uma subpasta por série: `data/raw/<serie>/<serie>_YYYYMMDD.json`, onde `YYYYMMDD` é a **data da ingestão**. | Arquivos imutáveis, só acrescentados, guardam o histórico do que foi baixado e permitem a carga incremental. | ✅ |
| 2026-10-28 | Carga completa (5 anos) na primeira execução e incremental nas seguintes. | Atende o bônus de atualização incremental. | ✅ |
| 2026-10-28 | O JSON é salvo como a fonte retorna, sem metadados. O retorno do yfinance (DataFrame) é convertido para JSON. | Todas as séries chegam à camada silver no mesmo formato. | ✅ |
| 2026-10-28 | As séries diárias (CDI, PTAX, Ibovespa) rodam em um fluxo, uma vez por dia. O IPCA (mensal) roda em um fluxo separado. | As frequências de publicação são diferentes. | ✅ |
| 2026-10-28 | Data inicial da carga incremental: o dia seguinte ao último arquivo salvo da série (até a data atual). | Em um dia normal é só o dia atual, e se uma execução falhar os dias perdidos entram automaticamente na seguinte. | ✅ |
| 2026-10-28 | **Revisão da decisão anterior:** a data inicial da carga incremental é o dia seguinte à **maior data de dado** dentro do último arquivo da série anterior a hoje. O nome do arquivo continua sendo a data de ingestão. | Pela data do nome do arquivo, dados publicados com atraso nunca entrariam. O IPCA de setembro, por exemplo, sai por volta de 10/10 com data 01/09, e o CDI costuma sair em D+1. Usar o último arquivo *anterior* a hoje mantém a sobrescrita no mesmo dia. | ✅ |
| 2026-10-28 | Nomes das séries (subpastas e arquivos): `cdi`, `ipca`, `dolar_ptax` e `ibovespa`. | Escolha do responsável pelo projeto. | ✅ |
| 2026-10-28 | Conversão do yfinance para JSON: uma lista de registros com **todas as colunas** como vêm do `Ticker.history` e a data local do pregão em `AAAA-MM-DD`, sem fuso, na chave `Date`. | É o mais fiel ao "salvar como vem". Tirar o fuso evita que a data mude na conversão. | ✅ |
| 2026-10-28 | O fluxo mensal (IPCA) tem um script de entrada próprio, `src/main_monthly.py`, executado com `python -m src.main_monthly`. O `src/main.py` fica com as séries diárias. | Facilita o agendamento separado no crontab. | ✅ |
| 2026-10-28 | `src/main.py` renomeado para `src/main_daily.py` (executado com `python -m src.main_daily`). Substitui o `main.py` das decisões anteriores. | Nomes simétricos para os dois pontos de entrada (`main_daily` e `main_monthly`). | ✅ |
| 2026-10-28 | Se uma série for executada mais de uma vez no mesmo dia, o arquivo do dia é sobrescrito. | Escolha do responsável pelo projeto. | ✅ |
| 2026-10-28 | Quando a fonte não tem dado para o período pedido (no SGS, HTTP 404 com `Value(s) not found`), nenhum arquivo é salvo e a execução segue normalmente. Cada execução faz uma única requisição por série. | Salvar `[]` faria a data inicial da próxima carga avançar, e um dia ainda não publicado seria perdido para sempre. Sem arquivo, o mesmo dia é pedido de novo na próxima execução. | ✅ |
| 2026-10-28 | Retentativa nas chamadas às fontes: **1 tentativa + 2 retentativas** (3 no total), com **intervalo fixo de 10 s** e **timeout de 60 s** por requisição. | Absorve instabilidades passageiras sem insistir demais. O timeout de 60 s deixa chegar a resposta de código SGS inexistente (cerca de 30 s), que assim é classificada como erro de configuração, e não como timeout. | ✅ |
| 2026-10-28 | Só os erros passageiros são retentados (timeout, falha de conexão, HTTP 5xx ou 429, `YFRateLimitError`). Erro de código ou de configuração não é retentado. "Sem dado" não é erro. | Tentar de novo um erro de código ou de configuração dá sempre o mesmo resultado. | ✅ |
| 2026-10-28 | Se todas as tentativas de uma série falharem, o erro é registrado em log e o fluxo segue para as outras séries. Os logs ficam em `log/` na raiz do projeto, fora do Git (`.gitignore`), com **um arquivo por execução**: `log/<fluxo>_YYYYMMDD_HHMMSS.log`, onde `<fluxo>` é `daily` ou `monthly` e a data e a hora são as do início da execução. O arquivo só é criado quando há erro. Cada linha registra a hora do erro e a série. | Uma fonte fora do ar não impede a coleta das outras. A série que falhou é pedida de novo na próxima execução, porque nenhum arquivo foi salvo. | ✅ |
| 2026-10-28 | No yfinance, usar `yf.Ticker(...).history(..., raise_errors=True)` no lugar de `yf.download`. | O `yf.download` não lança exceção e não diferencia ticker inválido de período sem pregão. | ✅ |
| 2026-10-28 | O fluxo diário é agendado para **depois do fechamento do pregão** da B3. O horário exato fica para a configuração do crontab. | Evita salvar a linha parcial do pregão em andamento do Ibovespa. Por enquanto não há proteção extra contra execução manual durante o pregão: nesse caso, a linha parcial é salva e só é corrigida se o fluxo rodar de novo no mesmo dia, depois do fechamento (o arquivo do dia é sobrescrito). | ✅ |
| 2026-10-28 | A queda de cerca de 14% do Ibovespa em 26/10/2026 é tratada como dado válido. | Foi confirmada por fontes independentes (BOVA11, EWZ, ações da carteira e a PTAX oficial). | ✅ |
| 2026-10-28 | Na série **mensal** (IPCA), a data inicial da carga incremental é o **1º dia do mês seguinte** ao último dado. | O SGS devolve o mês que contém a data inicial. Começar no dia seguinte ao último dado faria a busca trazer o último IPCA de novo a cada execução. | ✅ |
| 2026-10-28 | O **Ibovespa** é buscado só **até o dia anterior** à execução. | A linha do dia atual vem provisória (`Volume = 0`, valor não consolidado) mesmo depois do fechamento, e a carga incremental não volta em dias anteriores. Com isso, o horário do agendamento deixa de ser crítico para o Ibovespa. | ✅ |
| 2026-10-28 | Testes automatizados com pytest ficam para depois. | Escolha do responsável pelo projeto. | ✅ |
| 2026-10-28 | **Revisão da decisão anterior:** os testes foram criados na pasta `tests/`, na raiz do projeto (nova pasta na estrutura). Eles não acessam a internet: as fontes são simuladas, e `data/` e `log/` são trocadas por pastas temporárias. | Pedido do responsável pelo projeto. Testes sem internet são rápidos, determinísticos e não alteram os dados reais. | ✅ |
| 2026-10-28 | Fluxo diário agendado para **todos os dias, às 09:00** (`0 9 * * *`). | Antes da abertura da B3, com as três séries alinhadas em D-1. Nos fins de semana a execução não acha dado novo e não salva arquivo; o sábado já traz os dados de sexta. | ✅ |
| 2026-10-28 | Fluxo mensal (IPCA) agendado **todos os dias de 8 a 20 de cada mês, às 10:00** (`0 10 8-20 * *`). | A data de divulgação do IBGE muda de mês para mês, por volta do dia 10, às 9h. Repetir nessa janela pega o IPCA em até 1 dia após a divulgação, sem duplicar nada. | ✅ |
| 2026-10-28 | **Revisão de decisão anterior:** o crontab foi instalado na máquina antes de o ETL estar completo, por enquanto só com a extração. | O responsável pelo projeto instalou e testou o agendamento. A camada bronze já começa a acumular dados. | ✅ |
| 2026-10-28 | Além dos horários fixos, o crontab roda os dois fluxos **ao ligar a máquina** (`@reboot`), 2 minutos depois do boot. | A máquina nem sempre está ligada às 09:00. Rodar ao ligar atualiza os dados assim que possível; a carga incremental busca os dias perdidos. Os 2 minutos dão tempo para a rede conectar. Limitação: o `@reboot` não roda ao voltar da suspensão. | ✅ |
| 2026-10-28 | A saída do terminal das execuções do cron é descartada (`> /dev/null 2>&1`). | Os erros de extração já ficam em `log/`. | ✅ |
| 2026-10-28 | `requirements.txt` gerado de novo com as dependências **importadas diretamente** pelo código e pelos testes, todas com versão fixa: `pyspark`, `requests`, `pytest`, `yfinance`, `pandas` e `curl_cffi`. | `pandas` e `curl_cffi` vinham só como dependências do yfinance, mas passaram a ser importados direto pelo código: `pandas` na conversão para JSON e `curl_cffi` na detecção dos erros de rede do yfinance. | ✅ |
| 2026-10-28 | Os itens pendentes da Fase 0 (estudo dos indicadores, unidades e limites das fontes, calendários) ficam para depois que a camada silver estiver pronta. | Escolha do responsável pelo projeto. | ✅ |
| 2026-10-28 | A carga incremental não refaz dias anteriores para pegar correções. A defasagem do IPCA é resolvida pelo agendamento do crontab. | Simplicidade. | ✅ |

# Roadmap — Pipeline de Indicadores de Mercado

> Contexto completo em [CONTEXT.md](CONTEXT.md).
>
> **Nenhuma decisão é tomada sem aprovação.** Os itens marcados como 🔶 *Decisão pendente* listam apenas perguntas e opções em aberto — não representam escolhas feitas.

**Legenda:** ⬜ não iniciado · 🔄 em andamento · ✅ concluído · 🔶 decisão pendente

---

## Fase 0 — Entendimento dos dados ⬜

Objetivo: entender cada indicador antes de manipulá-lo.

> ⏸️ **Adiada:** os itens pendentes desta fase serão retomados quando a camada silver estiver pronta (decisão de 28/10/2026).

- ⬜ Estudar cada série: significado, forma de cálculo, uso no dia a dia de um assessor de investimentos e formas usuais de apresentação.
  - ⬜ CDI
  - ⬜ IPCA
  - ⬜ Dólar PTAX venda
  - ⬜ Ibovespa
- ✅ Pesquisar e confirmar os códigos das séries no SGS: CDI = 12, IPCA = 433, PTAX venda = 1.
- ✅ Definir o período de extração: data atual menos 5 anos até a data atual.
  - ✅ Se o dia atual for 29/02, a data inicial é 28/02.
- ✅ Explorar o retorno do `yfinance` para o `^BVSP` (ver [CONTEXT.md](CONTEXT.md#yfinance-ibovespa)).
  - ✅ Linha parcial do pregão em andamento: o fluxo diário roda depois do fechamento do pregão.
    - ✅ Sem proteção extra por enquanto: basta o agendamento. Uma execução manual durante o pregão salva a linha parcial, que só é corrigida se o fluxo rodar de novo no mesmo dia, depois do fechamento.
  - ✅ Verificar a queda de cerca de 14% do Ibovespa em 26/10/2026: é um evento real, confirmado por fontes independentes.
  - ⬜ Na conversão para JSON, considerar o fuso horário do índice do `Ticker.history`.
- ⬜ Verificar o formato de retorno, unidades e limitações das fontes (API SGS e `yfinance`).
- ⬜ Mapear diferenças de calendário entre as séries (dias úteis BCB, pregões B3, divulgação mensal do IPCA).

## Fase 1 — Definições de arquitetura 🔶

Todas as decisões abaixo dependem de aprovação.

- ✅ Estrutura de pastas (ver registro de decisões em [CONTEXT.md](CONTEXT.md#registro-de-decisões)).
- ✅ Linguagem e dependências: Python com PySpark, requests, yfinance, pandas, curl_cffi e pytest (`requirements.txt` + `.venv`).
- ✅ Formato da base de carga: parquet.
- 🔶 Modelagem dos dados (granularidade, tabelas/arquivos brutos vs. tratados).
- 🔶 Ferramenta do dashboard (Streamlit, Power BI, Excel, HTML ou outra).
- ✅ Forma de execução do pipeline, a partir da raiz do projeto: `python -m src.main_daily` (séries diárias) e `python -m src.main_monthly` (IPCA).
- ✅ Agendamento: crontab.
  - ⬜ Configurar o crontab (frequência e horário) depois que todo o ETL estiver pronto.

## Fase 2 — Extração (E) 🔄

- ✅ `fetch_sgs` em `src/extract.py` (genérica, recebe o código SGS e o período).
- ✅ `fetch_yfinance` em `src/extract.py` (chama a conversão do `utils.py` e retorna JSON, como o `fetch_sgs`).
- ✅ Em `src/utils.py`:
  - ✅ `dataframe_to_json`: converte o DataFrame do yfinance para JSON;
  - ✅ `save_json`: salva o JSON em `data/raw/<serie>/<serie>_YYYYMMDD.json`;
  - ✅ `get_start_date`: calcula a data inicial (carga completa ou incremental);
  - ✅ `configure_logging`: log no terminal e erros em `log/`.
- ✅ Carga completa (5 anos) na primeira execução e incremental nas seguintes: do dia seguinte à maior data de dado do último arquivo anterior a hoje até hoje.
- ✅ CDI, Dólar PTAX e Ibovespa (séries diárias) via `src/main_daily.py`.
- ✅ IPCA (série mensal) via `src/main_monthly.py`.
- ✅ Reexecução no mesmo dia sobrescreve o arquivo do dia (a data inicial é calculada pelo último arquivo **anterior** a hoje).
- ✅ Verificar o que a API SGS retorna quando o período pedido não tem dado (ex.: feriado): **HTTP 404** com `"Value(s) not found"` (ver [CONTEXT.md](CONTEXT.md#api-sgs-banco-central)).
  - ✅ Quando não há dado, nenhum arquivo é salvo. A próxima execução pede de novo a partir do mesmo ponto.
- ✅ Tratamento de erros e retentativas nas chamadas às fontes (ver [CONTEXT.md](CONTEXT.md#mapa-de-erros-das-fontes)).
  - ✅ Mapear os tipos de erro de cada fonte.
  - ✅ 1 tentativa + 2 retentativas (3 tentativas no total), com intervalo fixo de 10 s.
  - ✅ Timeout de 60 s por requisição.
  - ✅ Retentar só os erros passageiros (coluna "Retentar?" do mapa).
  - ✅ Se todas as tentativas falharem, registrar o erro em log e seguir para as outras séries.
  - ✅ Usar `yf.Ticker(...).history(..., raise_errors=True)` no yfinance.
- ✅ Registrar os erros em arquivos de log na pasta `log/` da raiz do projeto (fora do Git), criada pelo pipeline se não existir.
  - ✅ Um arquivo por execução, com a data e a hora do início no nome. Cada linha traz a hora do erro e a série.
  - ✅ Nome com o fluxo: `log/daily_YYYYMMDD_HHMMSS.log` e `log/monthly_YYYYMMDD_HHMMSS.log`.
  - ✅ O arquivo só é criado quando a execução tem erro.
- ✅ Validação manual (28/10/2026): carga completa das 4 séries, cálculo da data inicial (reexecução e dia seguinte), série inválida, falha passageira com 3 tentativas e criação do log só com erro.
- ✅ IPCA: como o SGS devolve o mês que **contém** a data inicial, na série mensal a busca começa no 1º dia do mês seguinte ao último dado.
- ✅ Ibovespa: a busca vai só **até ontem**, porque a linha do dia atual vem provisória mesmo depois do fechamento.
- ✅ Testes automatizados com pytest em `tests/` (99 testes, sem acesso à internet): `pytest` a partir da raiz.
- 🔶 Horário de execução: CDI, PTAX e o fechamento do Ibovespa são divulgados em horários diferentes.

## Fase 3 — Transformação (T) ⬜

- ⬜ Padronizar datas e tipos.
- 🔶 Tratamento de dias sem dado (fins de semana, feriados, faltantes).
- 🔶 Como conciliar séries diárias e mensal.
- 🔶 Quais métricas calcular (ex.: retornos acumulados, variação em 12 meses, base 100, ganho real etc.).
- ⬜ Documentar cada decisão no README.

## Fase 4 — Carga (L) ⬜

- ⬜ Criar `data/raw/` e `data/processed/` caso não existam (a pasta `data/` não é versionada).
- ⬜ Salvar os dados tratados no formato aprovado na Fase 1.
- ⬜ Garantir que a base alimenta o dashboard.

## Fase 5 — Dashboard ⬜

- 🔶 Público-alvo e perguntas que o dashboard deve responder.
- 🔶 Quais gráficos e indicadores exibir.
- 🔶 Quais comparações fazem sentido entre as séries.
- 🔶 Organização/layout e filtros.
- ⬜ Implementar o dashboard na ferramenta aprovada.

## Fase 6 — Documentação ⬜

- ⬜ README com:
  - ⬜ Como executar o pipeline e o dashboard.
  - ⬜ Decisões de transformação e suas justificativas.
  - ⬜ Para quem é o dashboard e por que as visualizações atendem esse público.

## Fase 7 — Bônus: atualização incremental ⬜

- 🔶 Estratégia para baixar apenas dados novos a cada execução.
- ⬜ Implementação e validação.

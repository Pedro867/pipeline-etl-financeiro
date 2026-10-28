# Roadmap — Pipeline de Indicadores de Mercado

> Contexto completo em [CONTEXT.md](CONTEXT.md).
>
> **Nenhuma decisão é tomada sem aprovação.** Os itens marcados como 🔶 *Decisão pendente* listam apenas perguntas e opções em aberto — não representam escolhas feitas.

**Legenda:** ⬜ não iniciado · 🔄 em andamento · ✅ concluído · 🔶 decisão pendente

---

## Fase 0 — Entendimento dos dados ⬜

Objetivo: entender cada indicador antes de manipulá-lo.

- ⬜ Estudar cada série: significado, forma de cálculo, uso no dia a dia de um assessor de investimentos e formas usuais de apresentação.
  - ⬜ CDI
  - ⬜ IPCA
  - ⬜ Dólar PTAX venda
  - ⬜ Ibovespa
- ✅ Pesquisar e confirmar os códigos das séries no SGS: CDI = 12, IPCA = 433, PTAX venda = 1.
- ✅ Definir o período de extração: data atual menos 5 anos até a data atual.
  - ✅ Se o dia atual for 29/02, a data inicial é 28/02.
- ✅ Explorar o retorno do `yfinance` para o `^BVSP` (ver [CONTEXT.md](CONTEXT.md#yfinance-ibovespa)).
  - 🔶 Tratamento da linha parcial do pregão em andamento.
  - ⬜ Verificar a queda de cerca de 14% do Ibovespa em 26/10/2026 (evento real ou erro da fonte).
- ⬜ Verificar o formato de retorno, unidades e limitações das fontes (API SGS e `yfinance`).
- ⬜ Mapear diferenças de calendário entre as séries (dias úteis BCB, pregões B3, divulgação mensal do IPCA).

## Fase 1 — Definições de arquitetura 🔶

Todas as decisões abaixo dependem de aprovação.

- ✅ Estrutura de pastas (ver registro de decisões em [CONTEXT.md](CONTEXT.md#registro-de-decisões)).
- ✅ Linguagem e dependências: Python com PySpark, requests e pytest (`requirements.txt` + `.venv`).
- ✅ Formato da base de carga: parquet.
- 🔶 Modelagem dos dados (granularidade, tabelas/arquivos brutos vs. tratados).
- 🔶 Ferramenta do dashboard (Streamlit, Power BI, Excel, HTML ou outra).
- ✅ Forma de execução do pipeline, a partir da raiz do projeto: `python -m src.main_daily` (séries diárias) e `python -m src.main_monthly` (IPCA).
- ✅ Agendamento: crontab.
  - ⬜ Configurar o crontab (frequência e horário) depois que todo o ETL estiver pronto.

## Fase 2 — Extração (E) ⬜

- ⬜ Implementar `fetch_sgs` em `src/extract.py` (genérica, recebe o código SGS e o período).
- ⬜ Implementar `fetch_yfinance` em `src/extract.py` (chama a conversão do `utils.py` e retorna JSON, como o `fetch_sgs`).
- ⬜ Implementar em `src/utils.py`:
  - ⬜ a função que converte o DataFrame do yfinance para JSON;
  - ⬜ a função que salva o JSON em `data/raw/<serie>/<serie>_YYYYMMDD.json`.
- ⬜ Carga completa (5 anos) na primeira execução e incremental nas seguintes: do dia seguinte ao último arquivo salvo até hoje.
- ⬜ Coletar CDI, PTAX venda e Ibovespa (séries diárias) via `src/main_daily.py`.
- ⬜ Coletar IPCA (série mensal) via `src/main_monthly.py`.
- ⬜ Se a série for executada de novo no mesmo dia, sobrescrever o arquivo do dia. Na reexecução, a data inicial é calculada pelo último arquivo **anterior** a hoje; caso contrário, ela cairia em amanhã e a busca viria vazia.
- 🔶 Horário de execução: CDI, PTAX e o fechamento do Ibovespa são divulgados em horários diferentes.
- ⬜ Verificar o que a API SGS retorna quando o período pedido não tem dado (ex.: feriado).
- 🔶 Tratamento de erros e retentativas nas chamadas às fontes.

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

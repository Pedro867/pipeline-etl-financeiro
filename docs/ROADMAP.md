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
- ⬜ Pesquisar e confirmar os códigos das séries no SGS (CDI, IPCA, PTAX venda).
- ⬜ Verificar o formato de retorno, unidades e limitações das fontes (API SGS e `yfinance`).
- ⬜ Mapear diferenças de calendário entre as séries (dias úteis BCB, pregões B3, divulgação mensal do IPCA).

## Fase 1 — Definições de arquitetura 🔶

Todas as decisões abaixo dependem de aprovação.

- ✅ Estrutura de pastas (ver registro de decisões em [CONTEXT.md](CONTEXT.md#registro-de-decisões)).
- ✅ Linguagem e dependências: Python com PySpark, requests e pytest (`requirements.txt` + `.venv`).
- ✅ Formato da base de carga: parquet.
- 🔶 Modelagem dos dados (granularidade, tabelas/arquivos brutos vs. tratados).
- 🔶 Ferramenta do dashboard (Streamlit, Power BI, Excel, HTML ou outra).
- ✅ Forma de execução do pipeline: `src/main.py`.
- ✅ Agendamento: crontab.
  - 🔶 Frequência e horário de execução.

## Fase 2 — Extração (E) ⬜

- ⬜ Coletar CDI via API SGS (últimos 5 anos).
- ⬜ Coletar IPCA via API SGS (últimos 5 anos).
- ⬜ Coletar Dólar PTAX venda via API SGS (últimos 5 anos).
- ⬜ Coletar Ibovespa via `yfinance` (`^BVSP`, últimos 5 anos).
- 🔶 Tratamento de erros e retentativas nas chamadas às fontes.
- 🔶 Se e como persistir os dados brutos antes da transformação.

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

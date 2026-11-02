# Roadmap — Pipeline de Indicadores de Mercado

> Contexto completo em [CONTEXT.md](CONTEXT.md).
>
> **Nenhuma decisão é tomada sem aprovação.** Os itens marcados como 🔶 *Decisão pendente* listam apenas perguntas e opções em aberto — não representam escolhas feitas.

**Legenda:** ⬜ não iniciado · 🔄 em andamento · ✅ concluído · 🔶 decisão pendente · ⏸️ adiado

---

## Fase 0 — Entendimento dos dados ⏸️

Objetivo: entender cada indicador antes de manipulá-lo.

> ⏸️ **Adiada:** os itens pendentes desta fase seriam retomados quando a camada silver estivesse pronta (decisão de 28/10/2026). A silver ficou pronta em 29/10/2026; falta decidir quando retomar.

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
  - ✅ Na conversão para JSON, considerar o fuso horário do índice do `Ticker.history`: `dataframe_to_json` usa a data local do pregão, com testes.
- ✅ Verificar o formato de retorno, unidades e limitações das fontes (API SGS e `yfinance`): documentado no [CONTEXT.md](CONTEXT.md#api-sgs-banco-central), inclusive o mapa de erros e a janela máxima de 10 anos do SGS.
- 🔄 Mapear diferenças de calendário entre as séries (dias úteis BCB, pregões B3, divulgação mensal do IPCA): o tratamento está decidido e implementado (cada série no próprio calendário; IPCA pelo mês de referência), mas não há um mapeamento dos feriados que não coincidem.

## Fase 1 — Definições de arquitetura 🔄

Todas as decisões abaixo dependem de aprovação.

- ✅ Estrutura de pastas (ver registro de decisões em [CONTEXT.md](CONTEXT.md#registro-de-decisões)).
- ✅ Linguagem e dependências: Python com pandas (transformação), pyarrow (parquet), requests, yfinance, curl_cffi e pytest (`requirements.txt` + `.venv`). O PySpark foi substituído pelo pandas em 29/10/2026.
- ✅ Formato da base de carga: parquet.
- ✅ Modelagem dos dados: bronze (JSON por execução), silver e gold (parquet). Ver [CONTEXT.md, seção 6](CONTEXT.md#6-esquema-das-tabelas-tratadas-parquet).
- ✅ Ferramenta do dashboard: **Streamlit** (decisão de 01/11/2026).
- ✅ Forma de execução do pipeline, a partir da raiz do projeto: `python -m src.main_daily` (séries diárias) e `python -m src.main_monthly` (IPCA).
- ✅ Agendamento: **GitHub Actions** (`.github/workflows/pipeline.yml`), substituindo o crontab em 01/11/2026.
  - ✅ Fluxo diário todos os dias às 09:17 de Brasília (`17 12 * * *` UTC). Fluxo mensal nos dias 8 a 20, às 10:17 (`17 13 8-20 * *` UTC).
  - ✅ `data/` e `log/` versionados no repositório; o workflow faz o commit ao fim de cada execução.
  - ✅ Botão de execução manual (`workflow_dispatch`), com escolha do fluxo.
  - ✅ Crontab local desativado: as linhas foram comentadas com `# DESATIVADO (GitHub Actions)`.
  - ✅ Commit e push do workflow e de `data/`/`log/`. Primeira execução manual em 01/11/2026 com sucesso (sem dado novo, por ser domingo).
  - ⬜ Confirmar a primeira execução **agendada** e o primeiro commit automático de `github-actions[bot]`.
  - ⬜ Nos primeiros dias, conferir nos arquivos se a execução das 09:17 já traz o CDI de D-1 e o Ibovespa de D-1 consolidado.
  - ⬜ Acompanhar o `YFRateLimitError` do Yahoo nos servidores do GitHub.
  - ✅ O pipeline termina com código de saída 1 quando alguma série falha na extração ou a transformação falha. O GitHub marca a execução como falha e avisa por e-mail. O fluxo mensal e o commit dos dados rodam mesmo assim.
  - ✅ Badge do workflow no topo do README.

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
- ✅ Registrar os erros em arquivos de log na pasta `log/` da raiz do projeto, criada pelo pipeline se não existir (versionada desde 01/11/2026).
  - ✅ Um arquivo por execução, com a data e a hora do início no nome. Cada linha traz a hora do erro e a série.
  - ✅ Nome com o fluxo: `log/daily_YYYYMMDD_HHMMSS.log` e `log/monthly_YYYYMMDD_HHMMSS.log`.
  - ✅ O arquivo só é criado quando a execução tem erro.
- ✅ Validação manual (28/10/2026): carga completa das 4 séries, cálculo da data inicial (reexecução e dia seguinte), série inválida, falha passageira com 3 tentativas e criação do log só com erro.
- ✅ Correções de 29/10/2026, a partir dos logs do `@reboot`: "sem dado" do SGS com HTTP 200 (IPCA) e recusa de período de um dia só (PTAX). Validadas com a API real; na mesma execução, um 503 passageiro do CDI se resolveu na 3ª tentativa.
- ✅ Confirmado em 29/10/2026: a linha do Ibovespa de D-1 chega consolidada no dia seguinte (28/10 com `Volume` 21.515.700).
- ✅ IPCA: como o SGS devolve o mês que **contém** a data inicial, na série mensal a busca começa no 1º dia do mês seguinte ao último dado.
- ✅ Ibovespa: a busca vai só **até ontem**, porque a linha do dia atual vem provisória mesmo depois do fechamento.
- ✅ Testes automatizados com pytest em `tests/` (204 testes, sem acesso à internet): `pytest` a partir da raiz.
- ✅ Horário de execução: fluxo diário todos os dias às 09:17 de Brasília, com todas as séries em D-1; IPCA nos dias 8 a 20, às 10:17 (GitHub Actions; ver Fase 1).
- ✅ Ibovespa provisório fora do período (corrigido em 02/11/2026): a execução de 01/11 pediu a partir de sábado (31/10), e o Yahoo devolveu a linha provisória de sexta (30/10), fora do período pedido. Ela substituiu na silver o valor consolidado salvo em 31/10. O `fetch_yfinance` passou a descartar linhas fora do período pedido.

## Fase 3 — Transformação (T) ✅

- ✅ Silver implementada em `src/transform.py` (`build_silver`): datas e tipos padronizados, deduplicação pela ingestão mais recente e índices acumulados. Validada com a bronze real em 29/10/2026.
- ✅ Gold implementada em `src/transform.py` (`build_gold`): 9 tabelas. Validada com os dados reais em 29/10/2026; os números conferem com o histórico conhecido do CDI, do IPCA e do dólar.
  - ✅ Avaliar a diferença do fechamento do Ibovespa de 29/12/2022 no Yahoo em relação ao oficial: confirmado que o Yahoo guardou a prévia do fim da tarde (110.031) em vez do fechamento oficial (109.734,60). Decisão: manter e documentar (ver CONTEXT.md, seção 6).
- ✅ Transformação chamada no fim de `main_daily` e `main_monthly` (`run_transformation`). Uma falha vai para o log da execução sem afetar a bronze. Roda a silver e depois a gold; se a silver falhar, a gold não roda.
- ✅ Testes da transformação: silver em `tests/test_transform.py` (30 testes) e gold em `tests/test_gold.py` (43 testes).
- ✅ Tratamento de dias sem dado (fins de semana, feriados, faltantes): é feito na camada silver, e cada série fica só com os dias em que tem dado, sem preenchimento.
  - ✅ Ibovespa em dólar só nas datas em comum entre Ibovespa e PTAX.
  - ✅ Quando a data de referência de uma janela cai em dia sem dado, usa-se o último dado anterior a ela.
- ✅ Como conciliar séries diárias e mensal: nas métricas reais, CDI e Ibovespa são cortados nos mesmos meses fechados do último IPCA divulgado.
- ✅ Quais métricas calcular: ver [CONTEXT.md, seção 5](CONTEXT.md#5-métricas-aprovadas-camada-silvergold).
  - ✅ CDI e IPCA convertidos em índice acumulado antes das variações.
  - ✅ Métricas com IPCA usam só os meses já divulgados, com o mês de referência exibido.
  - ✅ Base 100, simulação de R$ 1.000.000,00 e drawdown máximo calculados no dashboard (dependem do filtro).
  - ✅ Métricas reais em todas as janelas nominais (mês, ano, 12M, 24M, 36M), alinhadas aos meses do IPCA.
  - ✅ Spread de juros reais: CDI anualizado do último dia útil contra o IPCA 12M mais recente.
- ✅ Estrutura das tabelas tratadas em parquet.
  - ✅ Pastas `data/processed/silver/` e `data/processed/gold/`.
  - ✅ Silver e gold recalculadas inteiras a cada execução.
  - ✅ A transformação roda no fim de `main_daily` e de `main_monthly`.
  - ✅ Colunas com nomes em português.
  - ✅ Uma tabela de indicadores diários por série na gold.
  - ✅ Só dados úteis: saem `Dividends` e `Stock Splits` do Ibovespa.
  - ✅ Percentuais em %, com sufixo `_pct`.
  - ✅ Ibovespa na silver só com `data` e `fechamento`.
  - ✅ Esquema final das tabelas: ver [CONTEXT.md, seção 6](CONTEXT.md#6-esquema-das-tabelas-tratadas-parquet).

## Fase 4 — Carga (L) ✅

- ✅ Criar `data/raw/` e `data/processed/` caso não existam: `save_json` e a gravação dos parquet criam as pastas.
- ✅ Salvar os dados tratados no formato aprovado na Fase 1: parquet com pyarrow, em `data/processed/silver/` e `data/processed/gold/`.
- ✅ Garantir que a base alimenta o dashboard: o dashboard lê a gold versionada no repositório.

## Fase 5 — Dashboard 🔄

- 🔶 Público-alvo e perguntas que o dashboard deve responder (adiado em 01/11/2026).
- ✅ Ferramenta: Streamlit, com gráficos em Plotly, em `dashboard/app.py`.
- ✅ Primeira versão implementada (01/11/2026): filtro de período no topo e abas Resumo, Comparação, Juros e inflação, Bolsa e Câmbio. Usa todas as métricas aprovadas, inclusive as calculadas no dashboard (base 100, simulação de R$ 1.000.000,00 e drawdown máximo).
  - ✅ Conferida visualmente nos temas claro e escuro (capturas de tela de todas as abas).
  - ✅ Testes de fumaça em `tests/test_dashboard.py`.
- ✅ Publicado no Streamlit Community Cloud: https://pipeline-etl-financeiro.streamlit.app/ (público, conferido em 01/11/2026).
- ✅ Ajustes de 01/11/2026: o Resumo virou a parte fixa do topo, e o filtro passou a valer só para as abas abaixo dele. Na simulação, o IPCA virou "Corrigido pelo IPCA".
- ✅ Ajuste de 02/11/2026: o Resumo virou seção expansível, aberta por padrão.
- 🔶 Outros ajustes de conteúdo e layout.

## Fase 6 — Documentação 🔄

- 🔄 README com:
  - ✅ Como executar o pipeline e o dashboard (seções "Como executar", "Agendamento" e "Dashboard").
  - ✅ Principais decisões de tratamento e suas justificativas (seção "Tratamento dos dados"). As demais ficam no registro de decisões do CONTEXT.
  - ⬜ Para quem é o dashboard e por que as visualizações atendem esse público.

## Fase 7 — Atualização incremental ✅

- ✅ Estratégia para baixar apenas dados novos a cada execução: carga completa de 5 anos na primeira vez e, depois, a partir do dia seguinte ao último dado salvo (1º dia do mês seguinte no IPCA). Ver Fase 2.
- ✅ Implementação e validação: `get_start_date` em `src/utils.py`, com testes. Em produção desde 28/10/2026, primeiro no crontab e depois no GitHub Actions.

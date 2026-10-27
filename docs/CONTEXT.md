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
- Os códigos das séries no SGS precisam ser **pesquisados e confirmados** no site do SGS (Sistema Gerenciador de Séries Temporais).

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

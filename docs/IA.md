# Uso de IA no projeto

Relatório escrito pela própria IA (Claude, no Claude Code) a partir do histórico completo da conversa em que o projeto foi construído, de 27/10/2026 a 02/11/2026. Ele descreve como a pessoa responsável pelo projeto conduziu o trabalho, sem embelezar e sem omitir.

**Sobre a fonte:** a conversa foi longa. Uma parte dela foi resumida automaticamente pela ferramenta. Para escrever este relatório, reli o histórico gravado: todas as mensagens da pessoa responsável e as minhas respostas, estas lidas de forma condensada.

---

## 1. Como fui direcionada

**Regra de governança desde a primeira mensagem.** Antes de qualquer código, a pessoa responsável pediu só a organização do contexto e do roadmap. Disse explicitamente: "Nenhum código ou decisão será tomada nesse momento" e "Salve no contexto que nenhuma decisão deve ser tomada sem que eu tenha aprovado". Essa regra ficou no topo do [CONTEXT.md](CONTEXT.md) e valeu a conversa inteira. Toda decisão aprovada entrou no registro de decisões, com data e justificativa.

**Contexto e restrições.** A pessoa forneceu a descrição completa do problema e os requisitos. Ao longo do trabalho, foi dando restrições concretas:
- a estrutura de pastas exata;
- a versão do Python (3.12.3);
- a URL e os códigos das séries do SGS, que ela mesma pesquisou;
- o período de coleta;
- o uso de `fetch_sgs`/`fetch_yfinance` e de um `utils.py`;
- a nomenclatura dos arquivos da bronze;
- os nomes de colunas em português;
- a remoção das menções ao enunciado original, para os documentos terem tom profissional.

**Nível de detalhe das instruções.** Variou com a fase:
- **Arquitetura e dados:** instruções curtas e diretas. Exemplos: "Quero usar python com pyspark e a biblioteca requests", "subpastas por série", "Sobrescrever".
- **Escolhas abertas:** a pessoa pedia que eu levantasse e comparasse as opções. Exemplos: o mapa de erros das fontes, o formato de arquivo com pandas e o tratamento de feriados. Depois escolhia, quase sempre respondendo por número ("1. A / 2. A / 3. Ainda não").
- **Métricas e estudo dos indicadores:** a pessoa trouxe material próprio, extenso e estruturado, para eu analisar:
  - uma lista de métricas organizada em 4 blocos;
  - um estudo de cada indicador (significado, cálculo, uso pelo assessor e forma de apresentação).

**Planos antes do código.** Na maior parte do projeto, sim:
- **Extração:** foi planejada por várias rodadas, cobrindo funções, nomes de arquivo, carga incremental, erros, retentativas, timeout e logs. Só então veio o pedido "implemente o fluxo de extração".
- **Silver e gold:** as métricas, a regra de calendário, a conciliação diária × mensal e o esquema completo das tabelas foram aprovados antes da implementação. A implementação foi pedida em duas etapas ("implemente a camada silver" e depois "Pode implementar a gold").
- **Dashboard:** as escolhas principais foram aprovadas antes do código: hospedagem, local do arquivo, biblioteca de gráficos e abas. Os detalhes de layout, porém, ficaram para mim durante a implementação (ver seção 5).

**Verificação feita pela própria pessoa.** Ela não aceitou tudo de forma passiva. Alguns exemplos:
- testou a API com `curl` em dia útil e em feriado para responder uma dúvida do roadmap;
- conferiu o cron com `journalctl`;
- leu os logs de erro e reproduziu a falha da API no navegador;
- conferiu o fechamento do Ibovespa num site de notícias;
- abriu o dashboard publicado e apontou problemas de lógica.

Os commits e os pushes também foram feitos sempre por ela, nunca por mim.

---

## 2. Pedidos principais

1. **Organizar contexto, roadmap e regra de aprovação antes de qualquer código** (primeira mensagem). Daí saíram o [CONTEXT.md](CONTEXT.md), o [ROADMAP.md](ROADMAP.md) e a regra de que nada é decidido sem aprovação.
2. **Implementar a extração com carga incremental**, depois de planejada em detalhe:
   - camada bronze em JSON;
   - retentativas e logs de erro;
   - em seguida, **criar testes cobrindo "todos os casos possíveis"** e gerar de novo o `requirements.txt`.
3. **Definir as métricas e implementar a transformação (silver e gold).** A pessoa trouxe a lista de métricas, aprovou os ajustes, decidiu o tratamento de feriados e o esquema das tabelas. No meio do caminho, trocou o PySpark pelo pandas.
4. **Rodar o pipeline no GitHub Actions**, para não depender da máquina pessoal ligada:
   - com `data/` e `log/` versionados;
   - com o pipeline terminando em falha quando houver erro;
   - com um botão de execução manual.
5. **Construir o dashboard em Streamlit e documentar para o público-alvo**, os assessores de investimento:
   - publicação no Streamlit Community Cloud;
   - ajustes de lógica no dashboard;
   - textos explicativos dos indicadores;
   - no README, as principais decisões de tratamento e a justificativa de cada visualização.

---

## 3. Correções e questionamentos

Momentos em que a pessoa responsável corrigiu, questionou ou rejeitou algo que eu fiz ou sugeri:

| Momento | O que aconteceu | Por quê |
|---|---|---|
| Arquivos de entrada | Eu tinha criado o `main_monthly.py` e mantido o `main.py`, só oferecendo renomear. Ela apontou: "Você criou o arquivo main_monthly mas não o main_daily". | Os dois pontos de entrada deveriam ser simétricos. |
| Conversão do yfinance | Eu registrei a conversão para JSON fora do `fetch_yfinance`. Ela corrigiu: "quero que o fetch_yfinance converta chamando o utils.py". | Assim as duas buscas devolvem o mesmo tipo. |
| "Sem dado" no SGS | Recomendei não salvar arquivo quando a API não tem dado. Ela questionou: "A opção A não vai causar um loop de requisições sem dados?". | Queria entender a consequência antes de aprovar. Aprovou depois da explicação. |
| Retentativas | Recomendei intervalo crescente entre tentativas. Ela escolheu **intervalo fixo de 10 s**. | Preferência dela. |
| Timeout | Ela propôs 30 s. Eu apontei que um código de série inexistente leva cerca de 30 s para responder. Ela mudou para **60 s**. | Aqui a correção partiu de um alerta meu e foi aceita. |
| Métricas | Rejeitou várias sugestões minhas: volatilidade, índice de Sharpe, linha da meta de inflação e a janela de 60 meses. Mudou a simulação para R$ 1.000.000,00 e pediu para incluir a data do último dado. | Manter só o que tem uso claro. A janela de 60 meses não teria histórico. |
| Escopo da análise | Eu fui além e analisei a estrutura do dashboard. Ela freou: "Ainda não estou estruturando o dashboard, somente definindo quais dados serão metrificados". | Manter o foco na etapa em andamento. |
| PySpark → pandas | Iniciativa dela: "acho melhor usá-lo [o pandas] em vez do pyspark". Também perguntou se havia formato melhor que parquet. | Volume pequeno; o pandas já era usado. Manteve o parquet depois da comparação. |
| Versionar `data/` | Eu tinha recomendado um branch separado para os dados. Ela decidiu versionar na `main`, explicando que a decisão antiga de não versionar fora tomada "quando o diretório ainda estava sendo estruturado". | Simplicidade e coerência com o projeto. |
| Simulação com IPCA | Rejeitou o IPCA como se fosse um investimento na simulação: "Não faz sentido a comparação de 1.000.000 reais investidos com o IPCA". Propôs mostrar quanto o valor inicial precisaria valer hoje, corrigido pelo IPCA. | Erro de lógica meu. A correção veio dela. |
| Filtro no Resumo | Apontou que o filtro de período "não faz nada" no Resumo. | Erro de design meu. |
| Seções expansíveis | Ela perguntou se era possível deixar os cabeçalhos expansíveis. Eu já implementei nas duas seções. Ela pediu que só o Resumo fosse expansível. | Interpretei uma pergunta como pedido de implementação. |
| README com todas as decisões | Recusou listar todas no README: "são dezenas de decisões […] devamos registrar somente as principais". | Legibilidade. |
| Ideias fora do escopo | Rejeitou as sugestões de Selic, calculadora de produtos e PTAX compra: "não faz parte do escopo desse projeto […] nem documentar". | Escopo. |
| Aviso de fase adiada | Pediu para remover o aviso de "fase adiada", que eu tinha deixado desatualizado depois de concluir o estudo. | Inconsistência minha na documentação. |
| Roadmap | Pediu para eu entender por que um item do roadmap não estava marcado. Isso revelou que o README não documentava as decisões de tratamento. | Lacuna que eu não tinha percebido. |

Também houve o caminho inverso: momentos em que eu discordei de algo trazido por ela.
- **Explicação para o fechamento de 29/12/2022:** ela trouxe uma explicação para a diferença entre o Yahoo e a B3, com o valor da B3 como "preliminar". Eu contestei com evidências: o retorno oficial de 2022 é calculado com 109.734,60, e o ETF BOVA11 caiu mais que o Yahoo indica. Ela não respondeu. O README ficou com a versão neutra, só com os números.
- **Estudo dos indicadores:** corrigi pontos do texto dela, por exemplo "0,10%" no lugar de "0,10 p.p." na relação entre CDI e Selic.

---

## 4. Divisão das decisões

**Decidido pela pessoa responsável** (iniciativa ou escolha dela, mesmo entre opções que eu apresentei):
- **Estrutura e ferramentas:**
  - estrutura de pastas;
  - Python 3.12.3, requests, pytest e, inicialmente, PySpark;
  - **a troca para pandas**;
  - parquet com pyarrow;
  - Streamlit e Plotly.
- **Fontes e período:** códigos SGS (12, 433 e 1), período de 5 anos e a regra de 29/02 → 28/02.
- **Extração:**
  - nomes `fetch_sgs`/`fetch_yfinance`, `utils.py` e conversão dentro do `fetch_yfinance`;
  - subpastas por série, JSON "como vem" e fluxos diário e mensal separados;
  - sobrescrita no mesmo dia;
  - não refazer dias anteriores.
- **Retentativas e logs:** 3 tentativas com 10 s de intervalo e timeout de 60 s; logs em `log/`, com o nome do fluxo, criados só quando há erro.
- **Agendamento e repositório:**
  - agendar depois do pregão;
  - o `@reboot` na fase do crontab;
  - **a migração para o GitHub Actions**, com `data/` e `log/` versionados e o botão manual;
  - terminar em falha quando há erro;
  - repositório público.
- **Métricas:** quais entram e quais saem, e a simulação de R$ 1.000.000,00.
- **Convenções dos dados:** percentuais com sufixo `_pct`; remover colunas sem uso; manter só o `fechamento` do Ibovespa; uma tabela por série; tratar feriados na silver.
- **Dashboard:**
  - hospedagem em nuvem com execução local;
  - correções de lógica: "Corrigido pelo IPCA" e o filtro fora do Resumo;
  - só o Resumo expansível;
  - **público-alvo: assessores de investimento**.
- **Documentação:**
  - sem menções ao enunciado original;
  - no README, só as principais decisões;
  - o conteúdo do estudo dos indicadores;
  - manter o fechamento de 2022 sem correção manual.
- **Momento das etapas:** adiar a Fase 0 e, depois, adiar os testes automatizados para mais tarde.

**Sugerido por mim e aceito sem alteração:**
- `python -m src.main` como forma de execução.
- Um arquivo da bronze por execução, com a data de ingestão no nome.
- Não salvar arquivo quando não há dado. Foi aceita depois de uma pergunta.
- Carga incremental:
  - partindo do dia seguinte ao último dado;
  - depois, revista por mim para usar a **maior data de dado** do último arquivo anterior a hoje;
  - no IPCA, partindo do 1º dia do mês seguinte.
- Mapa de erros e regra de quais erros retentar. Uso do `Ticker.history(raise_errors=True)`.
- Um arquivo de log por execução, no lugar de um por erro.
- Buscar o Ibovespa só até o dia anterior.
- Horários do cron (09:00 e 10:00 nos dias 8 a 20) e depois do Actions (minuto 17).
- Na transformação:
  - converter CDI e IPCA em índice acumulado;
  - retorno real pela fórmula de Fisher;
  - YTD sobre o fechamento do ano anterior;
  - "% do CDI" só com retornos positivos;
  - "máxima em 5 anos" no lugar de "histórica".
- "Último dado anterior" como início das janelas e alinhamento das métricas reais aos meses do IPCA.
- Spread de juros reais com o CDI de hoje.
- O esquema completo das tabelas silver e gold, e a convenção do índice que inclui a taxa do próprio dia.
- Correções de bugs que encontrei: a API SGS mudou de comportamento e o yfinance devolveu linhas fora do período pedido.
- A organização em abas, as cores fixas por indicador e o badge do workflow.
- O critério para escolher as "principais decisões" do README e a lista de 9 itens.
- Os textos do "?" dos cartões e a legenda sobre retorno total do Ibovespa. Também o conteúdo das seções "Para quem é" e "Por que estas visualizações", no README.

**Decidido por mim sem aprovação explícita prévia** (registrado e só depois comunicado). Isso vai contra a regra de governança do projeto:
- **Agendamento do cron:** registrei os horários e o descarte da saída do terminal (`> /dev/null 2>&1`) como decididos, sem pedir confirmação.
- **Primeira versão do dashboard:**
  - coloquei o filtro no topo, e não na barra lateral, como estava aprovado; avisei e me ofereci para mudar;
  - escolhi as cores, as legendas, as tabelas "Ver dados" e o layout das abas.
- **Detalhes de cálculo da gold:** cinco pontos de interpretação. Exemplos: médias móveis vazias até haver histórico completo e o ano de 2021 fora do retorno anual. Registrei e pedi confirmação, mas **a pessoa não respondeu** e passou para outro assunto.
- **Seções expansíveis:** implementei direto quando a pergunta era "é possível?".
- **Revisão final dos documentos:** ao preencher lacunas, fiz pequenas mudanças de status além das pedidas. Exemplos: marcar as Fases 2 e 5 como concluídas e trocar o status da Fase 0 de adiada para em andamento.

---

## 5. Pontos de atenção

Pontos em que posso ter errado e que merecem verificação humana:

1. **Diagnóstico errado já corrigido.** No dia 01/11, eu disse que a linha provisória do Ibovespa de 30/10 era porque o Yahoo "ainda não tinha consolidado" o dado. O diagnóstico estava errado: a fonte devolveu uma linha fora do período pedido. Corrigi em 02/11. Isso mostra que diagnósticos meus foram aceitos e só revistos depois. Outros podem ter o mesmo problema.
2. **Fechamento do Ibovespa de 29/12/2022.** A conclusão de que o Yahoo guardou uma prévia se apoia em matérias de imprensa encontradas em busca na web. **Não conferi a série histórica oficial da B3.** A explicação alternativa da pessoa também não foi verificada.
3. **Regras de cálculo da gold nunca confirmadas.** São as cinco interpretações citadas na seção 4. Estão no CONTEXT, seção 6, como regras, mas não houve aprovação explícita.
4. **Textos do dashboard sobre os indicadores.** Partem do estudo da pessoa, com correções minhas, mas não foram checados em fontes oficiais nesta conversa. São afirmações como "cerca de 0,10 p.p. abaixo da Selic meta", "free float" e "rebalanceada a cada 4 meses".
5. **Justificativa das visualizações (README).** As "perguntas do assessor" e os motivos de cada visualização foram escritos por mim, a partir do público definido. **Não foram validados com assessores reais.**
6. **Público-alvo e Inteligência Comercial.** O enunciado fala na equipe de Inteligência Comercial; a pessoa definiu como público os assessores de investimento. Para conciliar, escrevi que a Inteligência Comercial acompanha os indicadores "para que os assessores embasem as conversas com clientes". É uma interpretação minha.
7. **GitHub Actions não confirmado em produção:**
   - Até o fim da conversa, **nenhuma execução agendada tinha disparado**, e não houve nenhum commit automático do `github-actions[bot]`.
   - Por isso, a permissão de push do workflow e o aviso de falha por e-mail **não foram testados de verdade**.
   - Também não foi confirmado que o CDI de D-1 já está disponível às 09:17.
8. **Testes sem internet.** Os 204 testes simulam as fontes. Eles não pegam mudanças reais de comportamento das APIs, como a do SGS entre 28/10 e 29/10, que só apareceu nos logs.
9. **Feriados que não coincidem entre BCB e B3.** O tratamento está implementado, mas os casos não foram mapeados.
10. **Paleta de cores não validada pelo script.** O script exigia Node.js, que não estava disponível; usei a ordem já validada da paleta de referência. A conferência foi visual, por capturas de tela.

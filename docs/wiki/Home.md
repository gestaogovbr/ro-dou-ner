# Documentação do Ro-DOU NER

O Ro-DOU NER enriquece publicações integrais INLABS com entidades e mantém resultados versionados. A documentação cobre o MVP implementado: regras determinísticas, GLiNER opcional, persistência PostgreSQL, projeção OpenSearch, API, CLI e integração Airflow.

## Comece pelo seu objetivo

| Se você precisa… | Leia |
| --- | --- |
| Experimentar sem serviços externos | [Início rápido](Inicio-rapido.md) |
| Configurar credenciais e pipeline | [Configuração](Configuracao.md) |
| Executar um lote ou avaliar JSONL | [CLI](CLI.md) |
| Consultar resultados | [API](API.md) |
| Entender o fluxo e os contratos | [Arquitetura](Arquitetura.md) |
| Operar Docker ou recuperar uma falha | [Operação](Operacao.md) |
| Integrar eventos de carga | [Airflow](Airflow.md) |
| Usar GLiNER ou medir qualidade | [Extração e avaliação](Extracao-e-avaliacao.md) |
| Explorar entidades visualmente | [Visualizador](Visualizador.md) |
| Testar a implementação | [Testes e validação](Testes-e-validacao.md) |

## Limites do MVP

A origem `dou_inlabs.article_raw` é somente de leitura. Os serviços PostgreSQL e OpenSearch pertencem ao ambiente Ro-DOU; o Compose inclui apenas a aplicação. Os resultados usam schema e índice próprios.

A qualidade do reconhecimento no corpus real permanece **pendente de avaliação**. O dataset de demonstração é sintético, e o checkpoint híbrido não representa um modelo aprovado para produção.

Querido Diário, DOE-SP, broker, outbox, Elasticsearch, linking de entidades, relações, resumos, classificação, embeddings e workflows genéricos de IA estão fora do MVP.

## Contribuição e fontes

Consulte [Como contribuir](../../CONTRIBUTING.md), a [apresentação do projeto](../../README.md) e as [convenções de documentação](../../docs/README.md). Código, configurações e testes são a referência para o comportamento executável.

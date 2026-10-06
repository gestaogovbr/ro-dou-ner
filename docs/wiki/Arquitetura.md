# Arquitetura

O projeto é um monólito modular com ports and adapters. O domínio define os contratos; a aplicação coordena o fluxo; adaptadores conectam fontes, extratores e serviços; o bootstrap injeta implementações.

## Módulos e dependências

| Módulo | Responsabilidade |
| --- | --- |
| `domain` | Publicações, identidade, menções, consolidação e validação sem SDKs |
| `application/ports` | Contratos por capacidade: origem, preparação, extração, persistência e projeção |
| `application/use_cases` | Enriquecimento e recuperação |
| `application/evaluation` | Avaliação por documento, span exato e label |
| `adapters` | INLABS, JSONL, regras, GLiNER, PostgreSQL, OpenSearch, API e Airflow |
| `bootstrap` | Configuração, composição, logging e CLI |

A direção é `adapters → application → domain`. O [teste de arquitetura](../../tests/unit/test_architecture.py) verifica importações. A composição está em [container.py](../../src/ro_dou_ner/bootstrap/container.py).

## Fluxo de enriquecimento

1. A origem fornece publicação integral e metadados.
2. O preparador gera texto canônico e revisão da origem.
3. O caso de uso calcula a identidade da versão e tenta adquirir a chave.
4. Se a versão existe, reutiliza o resultado e pode reenviar sua projeção.
5. Uma nova tentativa é registrada antes da extração.
6. Regras processam o documento inteiro; GLiNER opcional processa chunks.
7. Menções são remapeadas, consolidadas e validadas.
8. Resultado e sucesso são persistidos em transação; a projeção ocorre depois.

O [caso de uso](../../src/ro_dou_ner/application/use_cases/enrich_publications.py) é compartilhado pela CLI e Airflow. A API consulta resultados sem iniciar extrações.

## Texto e offsets

`html-nfc-lines-v1` remove markup, comentários e script/style, decodifica entidades HTML, aplica NFC, preserva acentos e normaliza whitespace e bordas de blocos.

Offsets são índices de caracteres Python no intervalo **`[start, end)`**, aplicados ao `body_text` canônico. A invariável é `surface == body_text[start:end]`. Eles não são bytes, unidades UTF-16 ou posições no HTML original. Não existe mapa reverso para HTML.

`character-overlap-v1` gera slices exatos com cobertura contínua. Palavras maiores que a janela podem ser divididas. GLiNER verifica também palavras/subwords e subdivide quando necessário. Regras usam o texto inteiro para evitar entidades estruturadas parciais nas fronteiras.

A consolidação deduplica `(label, start, end)`, dá prioridade às regras e compara scores apenas dentro do mesmo extrator. Sobreposições com spans ou labels distintos são preservadas. Labels devem pertencer à taxonomia; scores presentes devem ser finitos e estar em `[0, 1]`.

## Origem e armazenamento

INLABS espelha o contrato da tabela do Ro-DOU: `inlabs:<id>`, coluna `texto` integral e demais metadados. Usa SQL parametrizado, filtros por data/ID e transação somente de leitura. Não depende de Airflow ou do índice de busca do Ro-DOU.

| Recurso | Papel |
| --- | --- |
| `dou_inlabs.article_raw` | Fonte existente, somente leitura |
| `ro_dou_ner.enrichment_runs` | Histórico de tentativas e erros sanitizados |
| `ro_dou_ner.publication_enrichments` | Resultados JSONB únicos por publicação/revisão/pipeline |
| `ro-dou-ner-publications-v1` | Índice padrão, uma versão por documento |

O [schema SQL](../../src/ro_dou_ner/adapters/persistence/postgres/schema.sql) é inicializado explicitamente e de forma idempotente. Mudanças futuras exigem migração própria. O índice `dou` permanece independente.

## Identidade e proveniência

`source_revision` é SHA-256 do conteúdo bruto e metadados em JSON canônico. Uma mudança apenas no HTML pode gerar nova revisão, mesmo sem mudança de texto canônico.

`pipeline_version` deriva do hash de modelo/checkpoint, tokenizer, taxonomia, normalização, chunking, versões dos extratores, threshold, consolidação e bibliotecas relevantes. A chave lógica combina publicação, revisão da origem e versão do pipeline.

O resultado registra modelo, configuração completa, taxonomia, texto, menções, metadados e conclusão UTC. Credenciais não entram no fingerprint. Alterações locais exigem atualizar a versão do perfil/extrator ou pacote para invalidar resultados anteriores.

## Consumo e limites

PostgreSQL alimenta os endpoints individuais. OpenSearch preserva versões históricas, menções `nested` e campos exatos `keyword`; o texto permanece em `_source`, sem indexação textual no mapping atual. Mappings incompatíveis são rejeitados.

`search_entities(label, surface)` é uma capacidade do adaptador, não um endpoint HTTP: ambos os filtros devem corresponder à mesma menção nested. Não há seleção implícita da última versão na busca por entidades.

Advisory locks e unicidade protegem o efeito persistido, mas não prometem exactly-once de inferência. Há conexões por operação e uma sessão adicional para o lock; pooling e dimensionamento exigem medições futuras. Consulte [Operação](Operacao.md) para recuperação e [API](API.md) para consultas.

## Referências complementares

- [Transações Psycopg](https://www.psycopg.org/psycopg3/docs/basic/transactions.html)

[← Página inicial](Home.md)

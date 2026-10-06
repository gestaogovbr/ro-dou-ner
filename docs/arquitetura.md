# Arquitetura implementada

`domain` define publicação, revisão, texto canônico, chunk, candidatos, menções, pipeline e resultado usando dataclasses/funções sem SDKs. Validação exige spans `[start,end)`, `surface == body_text[start:end]`, labels conhecidos e scores finitos em `[0,1]` quando presentes.

`application/ports` contém contratos por capacidade. `EnrichPublications` coordena origem, preparação, extração, consolidação, tentativa durável, persistência e projeção. `bootstrap` injeta adaptadores; um teste verifica a direção das dependências.

## Texto e extração

O perfil `html-nfc-lines-v1` remove markup, comentários e script/style, decodifica entidades HTML, preserva acentos, aplica NFC e normaliza whitespace/bordas de blocos. Não há mapa reverso para HTML; os offsets referem-se ao texto canônico persistido. A revisão é do conteúdo bruto, logo mudança apenas de HTML também permite nova execução.

`character-overlap-v1` produz slices exatos com overlap e cobertura contínua. Palavras maiores que a janela podem ser divididas. GLiNER aplica segmentação adicional verificando palavras/subwords e cobertura antes de inferir. Regras processam o texto integral para impedir entidades estruturadas parciais nas fronteiras.

Consolidação deduplica `(label,start,end)`, prefere regras em duplicatas e compara scores somente dentro do mesmo extrator. Spans/labels diferentes e sobrepostos são preservados. A política é versionada na configuração.

## Persistência e origem

INLABS espelha o contrato encontrado em `Ro-dou/dag_load_inlabs/sql/init-db.sql`: `inlabs:<id>`, `texto` completo e metadados. Paginação keyset em transação read-only, SQL parametrizado e filtros por data/ID. Não depende do Airflow ou da busca do Ro-DOU.

`enrichment_runs` guarda tentativas `running/succeeded/failed/abandoned`, modelo, revisão, pipeline, timestamps e erro sanitizado. `publication_enrichments` guarda JSONB único por tripla, taxonomia e validação. Tentativas e resultados históricos são preservados. Inicialização é explícita e idempotente; evolução futura do schema exige migração própria.

Advisory locks não prometem exactly-once. Perda de sessão pode permitir inferência repetida; unicidade e transações protegem o efeito lógico persistido. O adaptador abre conexões por operação e mantém outra sessão para o lock. Pooling e dimensionamento dependem de medições futuras de volume.

## Consumo

O índice próprio OpenSearch usa menções nested, keywords exatas e ID lógico do resultado. Novas revisões/pipelines ficam preservados. Mapping existente incompatível é rejeitado; não há endpoint de busca avançada ou seleção implícita da última versão na busca por entidades.

Os serviços PostgreSQL/OpenSearch e a rede Docker pertencem ao Ro-DOU e são reutilizados. O Compose deste projeto contém apenas a aplicação, conectada à rede externa. O índice existente `dou` não é alterado; os enriquecimentos usam índice próprio. Testes locais usam um banco dedicado no PostgreSQL existente e índices temporários no OpenSearch existente.

API consulta PostgreSQL pela última persistência bem-sucedida ou revisão/pipeline específicos. Health verifica storage principal. O template Airflow é adaptador externo com OR dos eventos de carga normal/extra, preservando todas as datas recebidas e mantendo o produtor independente.

## Proveniência e avaliação

Resultado guarda hash/configuração completa. Modelo e tokenizer/configuração externa usam commits imutáveis; GLiNER/Torch/Transformers/Tokenizers entram no fingerprint híbrido. Mudanças locais devem incrementar versão do perfil/extrator ou do pacote para invalidar resultados anteriores.

A avaliação usa JSONL anotado no texto canônico, métricas exatas e cobertura incluindo falhas. O fixture sintético verifica contratos; prontidão de qualidade exige corpus real, escolha de checkpoint/prompts/threshold e avaliação própria.

Referências verificadas: [transações Psycopg](https://www.psycopg.org/psycopg3/docs/basic/transactions.html), [processamento GLiNER](https://github.com/urchade/GLiNER/blob/v0.2.29/gliner/data_processing/processor.py), [checkpoint GLiNER](https://huggingface.co/urchade/gliner_multi-v2.1/tree/443d26d654e0324125a96bebd8e796c14ff2efe6), [tokenizer/backbone](https://huggingface.co/microsoft/mdeberta-v3-base/tree/a0484667b22365f84929a935b5e50a51f71f159d) e [Datasets Airflow](https://airflow.apache.org/docs/apache-airflow/2.10.1/authoring-and-scheduling/datasets.html).

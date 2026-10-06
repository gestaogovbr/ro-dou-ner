# Operação

Este guia cobre Docker, persistência e recuperação. Configure primeiro os serviços conforme [Início rápido](Inicio-rapido.md) e [Configuração](Configuracao.md).

## Serviços compartilhados

PostgreSQL e OpenSearch são reutilizados do Ro-DOU. O [Compose](../../compose.yaml) contém apenas a aplicação, sem criar backends, volumes de banco ou rede própria. A rede externa padrão é `ro-dou_default`, configurável por `RO_DOU_NER_SHARED_NETWORK`.

No host, os exemplos usam `127.0.0.1:5432` e `127.0.0.1:9200`. Na rede Docker, usam `ro-dou-postgres-1` e `opensearch`. Ajuste os nomes ao ambiente real; dentro do container, `127.0.0.1` aponta para o próprio container.

## Executar com Docker

Com serviços e rede já disponíveis:

```bash
cp .env.docker.example .env.docker
# Edite as credenciais antes de executar.
docker compose --env-file .env.docker build api
docker compose --env-file .env.docker run --rm api init-db
docker compose --env-file .env.docker up -d api
```

A API fica em `http://127.0.0.1:18000`; `/docs` oferece a referência interativa. O healthcheck consulta `/health` a cada 30 segundos e verifica o armazenamento principal.

Para um lote manual:

```bash
docker compose --env-file .env.docker run --rm api process --date 2026-10-06
```

Para híbrido, defina `RO_DOU_NER_WITH_GLINER=true` e as variáveis de modelo/tokenizer em `.env.docker`, depois refaça o build. Essa variável controla o build do Compose, não o modo em runtime. Veja [Extração e avaliação](Extracao-e-avaliacao.md).

Build direto, quando necessário:

```bash
docker build -t ro-dou-ner .
docker build --build-arg WITH_GLINER=true -t ro-dou-ner:hybrid .
```

A imagem usa usuário não root e recebe configuração por ambiente ou arquivo montado. Arquivos `.env` não devem entrar na imagem. O visualizador exige o [override específico](Visualizador.md).

## Idempotência e tentativas

PostgreSQL usa advisory lock de sessão por chave e unicidade de `(publication_id, source_revision, pipeline_version)`. A tentativa começa antes da inferência, com modelo registrado; resultado e sucesso são transacionais.

| Estado | Significado |
| --- | --- |
| `running` | Tentativa iniciada, sem conclusão |
| `succeeded` | Resultado salvo com sucesso |
| `failed` | Falha registrada com etapa/tipo sanitizados |
| `abandoned` | Tentativa interrompida identificada ao retomar a chave |

Falhas são registradas antes do unlock. Perda da sessão libera o lock e pode permitir inferência repetida; unicidade e transações preservam o efeito lógico persistido. Uma chave ocupada conta como `skipped`.

## Recuperar falha de projeção

Falha OpenSearch preserva o resultado PostgreSQL. Corrija a causa e repita **o mesmo lote com a mesma configuração de pipeline**. Versões existentes são reutilizadas e reenviadas ao índice sem nova inferência.

Não existe outbox nem retry autônomo de projeção. O caller repete o lote; no Airflow, falhas reportadas causam retry da task. Mudanças de origem/pipeline geram outra versão, preservando o histórico.

A projeção usa `refresh=False` por padrão. Um resultado pode estar disponível no endpoint individual antes de aparecer na listagem OpenSearch.

## Diagnosticar falhas

| Sintoma | Verificação e ação |
| --- | --- |
| `init-db` falha | Confira DSN, permissões no schema e disponibilidade do índice |
| Origem não pode ser lida | Confira DSN INLABS, tabela e acesso de leitura; repita após corrigir |
| Lote retorna `failed` | Confira publicação, etapa e tipo de erro no relatório |
| Lote retorna `projection_failed` | Corrija OpenSearch e repita para reenviar resultados |
| API individual retorna 404 | Confirme enriquecimento bem-sucedido para a publicação/versão |
| Listagem retorna 503 | Confira URL, índice e disponibilidade OpenSearch |
| Listagem retorna 422 | Confira parâmetros e `index.max_result_window`; reduza a página |
| `/health` retorna 503 | Confira conexão PostgreSQL e tabelas de resultados |
| Modelo falha por limites/truncamento | Confira commits, tokenizer e orçamento do modelo |

Logs preservam contagens, publicação, etapa e tipo de erro. Mensagens brutas de SDKs não são persistidas. Não publique credenciais ou conteúdo sensível ao pedir suporte.

## Exposição e manutenção

A API é somente de leitura e não implementa autenticação. Autenticação, autorização e exposição externa pertencem ao ambiente de implantação. O Compose publica a porta somente no loopback do host.

`init-db` não substitui migrações ou reindexação. Backup, retenção, capacidade e acesso pertencem à operação dos serviços compartilhados.

[← Página inicial](Home.md)

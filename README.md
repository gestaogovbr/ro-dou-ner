# Ro-DOU NER

Enriquecimento versionado de publicações integrais INLABS, como monólito modular com ports and adapters. A origem `dou_inlabs.article_raw` é acessada somente para leitura; resultados e tentativas ficam no schema independente `ro_dou_ner`.

O MVP oferece regras determinísticas, GLiNER opcional, normalização, chunks com overlap, validação de offsets, PostgreSQL, projeção OpenSearch, API, CLI e gatilho Airflow. Dependências: `adapters → application → domain`. O bootstrap injeta explicitamente as implementações.

## Executar offline

Requisitos: Python 3.12 ou 3.13 e [uv](https://docs.astral.sh/uv/getting-started/installation/). O lockfile fixa as dependências.

```bash
uv sync --locked
uv run ro-dou-ner enrich-file tests/fixtures/evaluation-synthetic.jsonl --output /tmp/enrichments.jsonl
uv run ro-dou-ner benchmark tests/fixtures/evaluation-synthetic.jsonl --output /tmp/benchmark.json
```

`enrich-file` recebe JSONL com `publication_id`, `body_text` e `metadata` opcional; usa o mesmo caso de uso com repositório em memória e grava resultados JSONL. Persistência durável utiliza `process`.

O modo padrão `rules` extrai `PROCESS_NUMBER`, `IDENTIFIER`, `DATE`, `MONEY` e `LEGAL_REFERENCE`. CPF/CNPJ exigem dígitos verificadores válidos; datas exigem calendário válido; processos são reconhecidos por formato. `hybrid` acrescenta `PERSON`, `ORGANIZATION` e `LOCATION`. A taxonomia MVP exige os oito labels, mesmo quando regras não produzem os três labels do modelo.

## Serviços e INLABS

```bash
# Copie .env.example para .env e ajuste as credenciais existentes.
set -a
source .env
set +a
uv run ro-dou-ner init-db
```

PostgreSQL e OpenSearch são **reutilizados do Ro-DOU**, nas portas existentes 5432/9200. Este projeto não cria serviços, volumes nem redes para esses backends. O Compose contém somente a aplicação e usa a rede externa `ro-dou_default`, configurável por `RO_DOU_NER_SHARED_NETWORK`. O índice de publicações `dou` permanece independente: enriquecimentos usam um índice próprio. Configure `RO_DOU_NER_INLABS_DSN` para o banco real, preferencialmente com usuário read-only; o serviço não cria nem altera a tabela de origem.

```bash
export RO_DOU_NER_INLABS_DSN='postgresql://reader:YOUR_PASSWORD@YOUR_HOST:5432/inlabs'
uv run ro-dou-ner process --date 2026-10-06
uv run ro-dou-ner process --publication-id inlabs:123456 --page-size 100
uv run ro-dou-ner serve
```

`process` exige data ou IDs explícitos; ambos juntos são filtros cumulativos. A leitura usa paginação por ID, preserva texto integral e inclui os metadados na revisão. Falha de leitura aborta o lote; falhas individuais são reportadas e as demais publicações continuam. A CLI retorna código não zero para falhas de processamento/projeção.

`init-db` cria o schema e, com `RO_DOU_NER_OPENSEARCH_URL`, cria/verifica o índice. Projeção é opcional; `RO_DOU_NER_OPENSEARCH_INDEX` altera o nome padrão `ro-dou-ner-publications-v1`. Cada versão lógica tem um documento próprio. `search_entities(label,surface)` usa uma única cláusula nested para ambos os filtros.

## GLiNER híbrido

```bash
uv sync --locked --extra gliner
uv run --extra gliner ro-dou-ner --pipeline configs/pipelines/hybrid-example-v1.json enrich-file tests/fixtures/evaluation-synthetic.jsonl --output /tmp/hybrid.jsonl
uv run --extra gliner ro-dou-ner --pipeline configs/pipelines/hybrid-example-v1.json process --date 2026-10-06
```

O exemplo fixa commits do modelo multilíngue e do tokenizer/backbone. É um checkpoint ilustrativo, sem aprovação de qualidade no corpus de diários oficiais. O primeiro download exige acesso ao Hugging Face e espaço para os pesos. Inclua `--extra gliner` em `uv run` para manter a dependência opcional.

Modelos devem usar IDs do Hugging Face e commits imutáveis de 40 caracteres. Checkpoints sem tokenizer/configuração próprios exigem `tokenizer_id`/`tokenizer_revision` também fixados. Diretórios locais e fallback para artefatos remotos não fixados são rejeitados; pesos devem estar em safetensors. São suportados os processadores uni-encoder inspecionados do GLiNER 0.2.29.

O adaptador verifica limites de palavras e subwords, incluindo prompts dos labels. Subdivide chunks quando necessário e remapeia offsets. Orçamentos desconhecidos, tokens individuais que não cabem e avisos de truncamento causam falha explícita.

## API

```text
GET /health
GET /publications?page=1&page_size=10
GET /publications/inlabs:123456/enrichment
GET /publications/inlabs:123456/entities?label=PERSON
```

`GET /publications` pagina os documentos do índice configurado por `RO_DOU_NER_OPENSEARCH_INDEX`. Cada item contém `id` (o `_id` do OpenSearch) e `document` (o `_source` integral, incluindo metadados, texto, menções e todos os atributos adicionais). O envelope retorna `total`, `page`, `page_size`, `total_pages`, `has_next` e `has_previous`. `page` começa em 1; `page_size` aceita 1 a 100 e tem padrão 10. Total é exato, e a ordem é publicação crescente, conclusão decrescente, pipeline crescente e revisão crescente.

Cada item representa uma **versão indexada**, portanto uma publicação reprocessada pode aparecer mais de uma vez. A consulta não colapsa versões nem altera documentos. O índice pode crescer durante o processamento; páginas distintas não constituem um snapshot fixo. Páginas além de `index.max_result_window` retornam 422; índice/configuração/backend indisponíveis retornam 503. A listagem exige `RO_DOU_NER_OPENSEARCH_URL`.

Os endpoints individuais retornam a última versão persistida com sucesso; `source_revision`/`pipeline_version` filtram versões específicas. “Última” significa ordem de persistência, não data editorial. Não consulta INLABS para verificar atualização. Ausência retorna 404; storage indisponível retorna 503; health verifica conexão e tabelas. API somente de leitura; autenticação e exposição externa são responsabilidade do ambiente de implantação.

O resultado guarda texto canônico, menções, modelo/checkpoint, revisão, taxonomia, hash/configuração completa do pipeline e timestamp UTC. Offsets são índices de caracteres Python `[start,end)` no texto canônico, não bytes nem posições no HTML bruto.

A página temporária de inspeção é opcional: `RO_DOU_NER_PREVIEW_DIRECTORY` aponta para um diretório com `index.html` e seus assets. Quando configurada, a API serve `/preview` e `/preview-assets`; sem essa variável, essas rotas não existem. Veja [docs/visualizador-temporario.md](docs/visualizador-temporario.md) para executar a visualização local de teste.

## Airflow

Copie [integrations/airflow/ro_dou_ner_dag.py](integrations/airflow/ro_dou_ner_dag.py) para o diretório de DAGs e instale o pacote no runtime das tasks. O template contempla Dataset do Airflow 2.10+ e Asset do Airflow 3. O pacote exige Python 3.12+; workers Python 3.11 precisam de runtime separado para executar a CLI ou atualização do runtime.

A DAG `ro_dou_ner_inlabs` usa `inlabs` **ou** `inlabs_edicao_extra`, lê `reference_date` de todos os eventos coalescidos e deduplica datas. Reprocessa o dia completo de forma idempotente. Execução manual exige `{"reference_date":"2026-10-06"}`. Metadados inválidos e falhas de processamento/projeção causam retry. A DAG produtora do Ro-DOU permanece independente.

Configure `RO_DOU_NER_DATABASE_DSN`, `RO_DOU_NER_INLABS_DSN` e OpenSearch opcional no runtime. Para híbrido, configure `RO_DOU_NER_MODE=hybrid`, `RO_DOU_NER_MODEL_ID`, `RO_DOU_NER_MODEL_REVISION`, `RO_DOU_NER_TOKENIZER_ID` e `RO_DOU_NER_TOKENIZER_REVISION` conforme o exemplo JSON.

## Idempotência e recuperação

`source_revision` é SHA-256 do conteúdo bruto + metadados em JSON canônico. O hash do pipeline inclui modelo/checkpoint, tokenizer, taxonomia, normalização, chunking, extratores, threshold, consolidação e versões relevantes das bibliotecas. A chave lógica é SHA-256 da publicação e dessas revisões.

PostgreSQL mantém advisory lock de sessão por chave e unicidade de `(publication_id,source_revision,pipeline_version)`. Resultado e sucesso são transacionais. Tentativas começam antes da inferência com modelo registrado; falhas são gravadas antes do unlock. Perda da sessão libera o lock; tentativa interrompida passa a `abandoned` ao retomar a chave. Chave já em processamento é contabilizada como `skipped`.

Falha OpenSearch preserva o resultado PostgreSQL. Repetir o lote reenvia a projeção sem nova inferência. Não há outbox/retry autônomo: o caller repete o lote. Logs/relatórios incluem contagens, publicação, etapa e tipo de erro; mensagens brutas de SDKs não são persistidas.

## Testes e avaliação

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv build
# Com os backends existentes e variáveis de teste configuradas:
uv run pytest --cov=ro_dou_ner --cov-fail-under=90
# Descobre as credenciais locais em memória e cria apenas banco de teste no PostgreSQL existente:
uv run tools/test_shared_services.py
# Incluindo inferência real do checkpoint fixado:
uv run tools/test_shared_services.py --with-model
```

Integrações usam `RO_DOU_NER_TEST_POSTGRES_DSN`/`RO_DOU_NER_TEST_OPENSEARCH_URL`; banco deve conter `test` no nome. O helper usa o container existente `ro-dou-postgres-1`, o banco dedicado `ro_dou_ner_test` e índices temporários exclusivos no OpenSearch existente; não sobe containers nem grava credenciais em arquivos. Fixtures removem apenas seus registros/índices e nunca escrevem na origem real INLABS. Variáveis ausentes causam skip explícito; serviço configurado mas indisponível falha. Apenas nos runners efêmeros do GitHub Actions, que não têm acesso ao Ro-DOU local, a CI provisiona seus próprios backends de teste. Smoke GLiNER pode ser acionado por `workflow_dispatch`.

Testes cobrem contratos, Unicode, propriedades de cobertura dos chunks, offsets, entidades inválidas, consolidação, concorrência, crash, atomicidade, versões históricas, retries, nested e fluxo completo INLABS → extração → PostgreSQL → OpenSearch → API.

O benchmark compara documento + span exato + label: precision/recall/F1 por tipo, micro/macro, cobertura com falhas, latência, throughput, alocações Python e pico RSS. Anotações devem referir-se ao texto canônico; divergência é falha. Denominadores zero retornam zero; macro inclui os oito labels. Scores de extratores diferentes não são probabilidades comparáveis.

O fixture contém cinco documentos **sintéticos** anotados para verificar contratos. Ainda é necessário corpus real representativo anotado para escolher checkpoint/threshold e aprovar qualidade. Memória GPU não é medida; tracemalloc exclui alocações nativas e RSS é pico do processo inteiro. Timing inclui processamento/validação e exclui leitura do dataset.

## Docker e estrutura

```bash
docker build -t ro-dou-ner .
# Ajuste as credenciais em uma cópia de .env.docker.example:
docker compose --env-file .env.docker run --rm api init-db
docker compose --env-file .env.docker up -d api
# API em http://127.0.0.1:18000
```

Para GLiNER: `docker build --build-arg WITH_GLINER=true -t ro-dou-ner:hybrid .`. O container usa usuário não root, recebe configuração por ambiente/arquivo montado e não incorpora secrets. No host, use 127.0.0.1; na rede Docker compartilhada, use `ro-dou-postgres-1` e `opensearch`, conforme `.env.docker.example`.

Veja [docs/arquitetura.md](docs/arquitetura.md). Fora do MVP: Querido Diário, DOE-SP, broker, outbox, Elasticsearch, linking, relações, resumos, classificação, embeddings e workflows genéricos de IA.

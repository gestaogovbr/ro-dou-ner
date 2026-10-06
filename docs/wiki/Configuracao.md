# Configuração

O Ro-DOU NER recebe configuração por arquivo JSON, variáveis de ambiente e opções globais da [CLI](CLI.md). As configurações são validadas antes da execução.

## Precedência

A ordem abaixo vai da menor para a maior prioridade:

1. Valores padrão de `Settings`.
2. Arquivo indicado por `--pipeline`.
3. Variáveis de ambiente reconhecidas com valor não vazio.
4. Opções globais da CLI fornecidas explicitamente.

Variáveis vazias e opções CLI ausentes não substituem o arquivo. Não há leitura automática de `.env` pela aplicação: exporte as variáveis no shell ou use `docker compose --env-file`, conforme a [instalação](Inicio-rapido.md).

As opções globais devem aparecer **antes** do subcomando:

```bash
uv run ro-dou-ner --pipeline configs/pipelines/rules-v1.json benchmark \
  tests/fixtures/evaluation-synthetic.jsonl --output /tmp/benchmark.json
```

## Conexões e execução

| Campo JSON | Variável de ambiente | Padrão | Uso |
| --- | --- | --- | --- |
| `database_dsn` | `RO_DOU_NER_DATABASE_DSN` | Ausente | PostgreSQL de enriquecimento; obrigatório para `init-db`, `process` e `serve`. |
| `inlabs_dsn` | `RO_DOU_NER_INLABS_DSN` | Ausente | PostgreSQL de origem INLABS; obrigatório para `process`. |
| `opensearch_url` | `RO_DOU_NER_OPENSEARCH_URL` | Ausente | Habilita projeção e leitura do índice. Sem ele, `/publications` retorna 503. |
| `opensearch_index` | `RO_DOU_NER_OPENSEARCH_INDEX` | `ro-dou-ner-publications-v1` | Índice separado de enriquecimento. |
| `preview_directory` | `RO_DOU_NER_PREVIEW_DIRECTORY` | Ausente | Diretório do visualizador temporário; deve conter `index.html`. |
| `mode` | `RO_DOU_NER_MODE` | `rules` | `rules` ou `hybrid`; também aceita `--mode`. |

DSNs contêm credenciais. Use arquivos locais ignorados pelo Git ou o mecanismo de secrets do ambiente. Os arquivos `.env.example` e `.env.docker.example` usam valores substituíveis; ajuste-os à infraestrutura existente. A configuração de produção não é necessária para `enrich-file` e `benchmark`, que utilizam armazenamento em memória.

## Pipeline de extração

| Campo JSON | Variável de ambiente / opção CLI | Padrão | Validação |
| --- | --- | --- | --- |
| `model_id` | `RO_DOU_NER_MODEL_ID` / `--model-id` | Ausente | Obrigatório no modo `hybrid`. |
| `model_revision` | `RO_DOU_NER_MODEL_REVISION` / `--model-revision` | Ausente | No modo `hybrid`, SHA imutável de 40 caracteres hexadecimais minúsculos. |
| `tokenizer_id` | `RO_DOU_NER_TOKENIZER_ID` / `--tokenizer-id` | Ausente | Para checkpoints que precisam de tokenizer/backbone externo. |
| `tokenizer_revision` | `RO_DOU_NER_TOKENIZER_REVISION` / `--tokenizer-revision` | Ausente | Quando um tokenizer externo é informado, ID e SHA de 40 caracteres são obrigatórios em conjunto. |
| `threshold` | Somente JSON | `0.5` | Entre 0 e 1; limiar do GLiNER. |
| `max_chars` | Somente JSON | `700` | Inteiro positivo; tamanho de fragmento em caracteres. |
| `overlap` | Somente JSON | `100` | `0 <= overlap < max_chars`. |
| `taxonomy_version` | Somente JSON ou arquivo de taxonomia | `ner-v1` | Identifica a taxonomia. |
| `labels` | Somente JSON ou arquivo de taxonomia | Oito classes abaixo | Deve conter exatamente as oito classes, sem repetições. |

Classes suportadas: `PERSON`, `ORGANIZATION`, `LOCATION`, `PROCESS_NUMBER`, `IDENTIFIER`, `DATE`, `MONEY` e `LEGAL_REFERENCE`. A configuração não permite ampliar esse conjunto no MVP.

O modo `rules` aplica regras ao documento inteiro. O modo `hybrid` mantém essas regras e adiciona GLiNER sobre fragmentos sobrepostos. Instale o extra `gliner` para processar ou avaliar nesse modo; consulte [Extração e avaliação](Extracao-e-avaliacao.md).

## Arquivos versionados

O repositório inclui:

- `configs/pipelines/rules-v1.json`: regras com fragmentação e taxonomia explícitas.
- `configs/pipelines/hybrid-example-v1.json`: GLiNER e tokenizer/backbone com revisões fixadas.
- `configs/taxonomies/ner-v1.json`: versão e classes da taxonomia.

Exemplo mínimo equivalente ao pipeline de regras:

```json
{
  "mode": "rules",
  "max_chars": 700,
  "overlap": 100,
  "threshold": 0.5,
  "taxonomy": "../taxonomies/ner-v1.json"
}
```

`taxonomy` é uma chave especial do carregador: o caminho é relativo ao **arquivo de pipeline**, não ao diretório de execução. O carregador substitui `taxonomy_version` e `labels` pelo conteúdo dessa taxonomia. Os demais campos precisam corresponder aos campos de `Settings`; uma chave desconhecida causa falha.

## Docker Compose e testes

| Variável | Padrão / finalidade |
| --- | --- |
| `RO_DOU_NER_SHARED_NETWORK` | `ro-dou_default`; rede externa dos serviços Ro-DOU existentes. |
| `RO_DOU_NER_WITH_GLINER` | `false`; argumento de build que instala o extra `gliner` quando vale `true`. |
| `RO_DOU_NER_TEST_POSTGRES_DSN` | Banco exclusivo de testes no PostgreSQL existente. |
| `RO_DOU_NER_TEST_OPENSEARCH_URL` | OpenSearch usado pelas verificações de integração. |

Essas variáveis não são campos de `Settings`. O Compose principal exige o DSN de enriquecimento, define o URL padrão do OpenSearch como `http://opensearch:9200` e publica a API em `127.0.0.1:18000`. O servidor iniciado diretamente pela CLI usa `127.0.0.1:8000` por padrão. Consulte [Operação](Operacao.md) e [Testes e validação](Testes-e-validacao.md) para o fluxo completo.

## Identidade e reprodutibilidade

A versão do pipeline é um hash da especificação efetiva: modelo, taxonomia, normalização, fragmentação, versões dos extratores, configuração e versões de pacotes relevantes. Alterações nesses componentes podem gerar uma nova versão de enriquecimento.

Credenciais e endereços dos serviços não entram nessa identidade. Fixar o SHA do modelo e do tokenizer permite identificar os artefatos usados; isso não equivale a uma garantia de determinismo completo.

## Referências

- [`Settings` e carregador](../../src/ro_dou_ner/bootstrap/settings.py)
- [Composição do runtime](../../src/ro_dou_ner/bootstrap/container.py)
- [Compose principal](../../compose.yaml)

[← Home](Home.md) · [CLI](CLI.md) · [API](API.md)

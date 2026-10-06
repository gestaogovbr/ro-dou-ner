# API de consulta

A API FastAPI consulta enriquecimentos concluídos no PostgreSQL e versões indexadas no OpenSearch. O processamento é executado pela [CLI](CLI.md) ou pela integração de orquestração; não há endpoint de escrita ou de disparo de enriquecimento.

## Iniciar o servidor

Configure `RO_DOU_NER_DATABASE_DSN` e inicialize o esquema conforme [Início rápido](Inicio-rapido.md). Para listar documentos, configure também `RO_DOU_NER_OPENSEARCH_URL` e inicialize o índice.

```bash
uv run ro-dou-ner serve --host 127.0.0.1 --port 8000
```

Base dos exemplos: `http://127.0.0.1:8000`. No Compose principal, a porta publicada no host é `18000`.

A aplicação disponibiliza os recursos padrão do FastAPI:

- `/docs`: documentação interativa Swagger UI.
- `/redoc`: documentação ReDoc.
- `/openapi.json`: contrato OpenAPI gerado pela aplicação.

O código não implementa autenticação nem autorização. A publicação em outras redes deve ser definida pelo ambiente que hospeda a API; o Compose principal limita a porta ao loopback do host.

## Endpoints

| Método e caminho | Origem dos dados | Resposta |
| --- | --- | --- |
| `GET /health` | Repositório de enriquecimento | Disponibilidade do armazenamento. |
| `GET /publications` | OpenSearch | Página de versões de enriquecimento indexadas. |
| `GET /publications/{publication_id}/enrichment` | PostgreSQL | Enriquecimento completo mais recente que atende aos filtros. |
| `GET /publications/{publication_id}/entities` | PostgreSQL | Identidade da versão e lista de menções, com filtro opcional por classe. |

### Saúde do armazenamento

```bash
curl -sS http://127.0.0.1:8000/health
```

Com o repositório disponível, retorna HTTP 200:

```json
{"status": "ok"}
```

Quando a verificação retorna falso ou lança exceção, retorna HTTP 503 e `{"status": "unavailable"}`. Essa rota verifica somente o repositório de enriquecimento: não certifica a disponibilidade do INLABS, do OpenSearch ou do modelo.

### Listagem paginada

```bash
curl -sS 'http://127.0.0.1:8000/publications?page=1&page_size=10'
```

| Parâmetro de query | Padrão | Limites |
| --- | --- | --- |
| `page` | `1` | Inteiro maior ou igual a 1. |
| `page_size` | `10` | Inteiro entre 1 e 100. |

Resposta para um índice vazio:

```json
{
  "items": [],
  "total": 0,
  "page": 1,
  "page_size": 10,
  "total_pages": 0,
  "has_next": false,
  "has_previous": false
}
```

Cada item tem a forma `{"id": "<id do documento indexado>", "document": {...}}`. `document` preserva todos os atributos de `_source`, incluindo campos adicionais, metadados e menções. O `id` é o identificador do documento no índice, não necessariamente o `publication_id`.

A listagem inclui **todas as versões indexadas**, sem agrupar publicações. `total` conta documentos do índice. A ordenação é `publication_id` crescente, `completed_at` decrescente, `pipeline_version` crescente e `source_revision` crescente.

Páginas distintas não constituem um snapshot fixo: novos documentos podem alterar o índice entre requisições.

A paginação usa `from`/`size` e respeita a menor janela `index.max_result_window` retornada pelo OpenSearch. Se `(page - 1) * page_size + page_size` ultrapassar essa janela, a API retorna 422. Uma página além do total pode retornar `items: []` se ainda estiver dentro da janela.

### Enriquecimento completo

```bash
curl -sS 'http://127.0.0.1:8000/publications/inlabs:42/enrichment'
```

| Parâmetro | Local | Comportamento |
| --- | --- | --- |
| `publication_id` | Caminho | Identificador completo, por exemplo `inlabs:42`. |
| `source_revision` | Query opcional | Restringe a uma revisão da origem. |
| `pipeline_version` | Query opcional | Restringe a uma versão do pipeline. |

Sem filtros, retorna o enriquecimento concluído mais recente da publicação. “Mais recente” significa ordem de persistência bem-sucedida, não data editorial. A consulta não verifica na origem INLABS se a publicação foi atualizada. Os filtros podem ser usados isoladamente ou em conjunto; uma combinação inexistente retorna 404. Uma tentativa de processamento malsucedida não substitui um resultado concluído.

O objeto retornado contém:

| Campo | Conteúdo |
| --- | --- |
| `publication_id` | Identificador da publicação. |
| `source_revision` | Revisão da origem usada no processamento. |
| `pipeline_version` | Hash da especificação do pipeline. |
| `taxonomy_version` | Versão da taxonomia. |
| `model` | `provider`, `model_id` e `revision`. |
| `body_text` | Texto preparado, usado como referência dos offsets. |
| `mentions` | Menções extraídas e consolidadas. |
| `completed_at` | Data e hora de conclusão em ISO 8601, normalizada para UTC. |
| `metadata` | Metadados associados à publicação. |
| `pipeline_config` | Especificação do pipeline que gerou o resultado. |

### Menções por classe

```bash
curl -sS 'http://127.0.0.1:8000/publications/inlabs:42/entities?label=MONEY'
```

Aceita os mesmos filtros `source_revision` e `pipeline_version`, além de `label`. Sem `label`, retorna todas as menções. O filtro é uma comparação exata e diferencia maiúsculas de minúsculas; uma classe desconhecida retorna uma lista vazia, sem erro de validação.

A resposta contém `publication_id`, `source_revision`, `pipeline_version` e `mentions`. Cada menção contém:

| Campo | Significado |
| --- | --- |
| `label` | Classe da taxonomia. |
| `surface` | Trecho literal de `body_text`. |
| `start` | Offset inicial em caracteres, inclusivo. |
| `end` | Offset final em caracteres, exclusivo. |
| `score` | Pontuação do extrator, entre 0 e 1, ou `null`. |
| `extractor` | Extrator responsável, como `rules` ou `gliner`. |

Os offsets satisfazem `body_text[start:end] == surface`. Eles se referem ao texto preparado, não aos bytes nem ao HTML original. Menções aninhadas e sobrepostas podem coexistir; o pipeline consolida duplicatas com a mesma classe e os mesmos offsets. Consulte [Extração e avaliação](Extracao-e-avaliacao.md).

## Erros

| Status | Situação | Corpo / detalhe |
| --- | --- | --- |
| `404` | Enriquecimento inexistente para publicação ou filtros. | `{"detail": "Enrichment not found"}` |
| `422` | Parâmetros de paginação inválidos. | Erro de validação padrão do FastAPI, com `detail` em lista. |
| `422` | Página além da janela do OpenSearch. | `{"detail": "Requested page exceeds the OpenSearch result window"}` |
| `503` | Repositório indisponível na consulta de enriquecimento ou menções. | `{"detail": "Enrichment storage unavailable"}` |
| `503` | OpenSearch ausente, indisponível, resposta incompleta ou contagem não exata. | `{"detail": "Publication search unavailable"}` |
| `503` | Falha na verificação de saúde. | `{"status": "unavailable"}` |

As exceções dos serviços são traduzidas para mensagens fixas; seus detalhes internos não são expostos por essas rotas.

## Visualizador temporário

Quando `RO_DOU_NER_PREVIEW_DIRECTORY` aponta para um diretório com `index.html`, a aplicação também serve `/preview` e os arquivos em `/preview-assets`. `/preview` usa `Cache-Control: no-store` e não aparece no OpenAPI. Sem essa configuração, essas rotas não são registradas. Consulte [Visualizador de entidades](Visualizador.md).

## Referências

- [Rotas FastAPI](../../src/ro_dou_ner/adapters/api/app.py)
- [Leitor OpenSearch](../../src/ro_dou_ner/adapters/search/opensearch/reader.py)
- [DTO de paginação](../../src/ro_dou_ner/application/dto/publication_page.py)
- [Contrato de enriquecimento](../../src/ro_dou_ner/domain/enrichment.py)

[← Home](Home.md) · [Configuração](Configuracao.md) · [CLI](CLI.md)

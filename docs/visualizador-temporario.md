# Visualizador temporário de entidades

O visualizador é uma ferramenta de inspeção manual em `tools/preview`. Ele consulta a API de leitura e não executa extrações. Seus arquivos não fazem parte da imagem da API; o override opcional monta a pasta somente para leitura.

Com as credenciais dos serviços existentes em `.env.docker`:

```bash
docker compose --env-file .env.docker -f compose.yaml -f compose.preview.yaml up -d --build api
```

Acesse `http://localhost:18000/preview`. O endpoint paginado é `GET /publications?page=1&page_size=10`, e a documentação interativa está em `/docs`.

Cada item contém `id` e `document`, com todos os atributos do `_source` do índice configurado em `RO_DOU_NER_OPENSEARCH_INDEX`. O índice padrão é `ro-dou-ner-publications-v1`. Uma publicação pode aparecer em mais de uma versão, pois cada combinação de publicação, revisão da origem e versão do pipeline corresponde a um documento indexado. A contagem refere-se a esses documentos. A paginação lê o estado atual do índice; novos enriquecimentos podem alterar páginas entre requisições.

O texto exibido é `body_text`, com os offsets canônicos das menções. A interface aplica cores por tipo, permite ativar/desativar tipos e mostra as entidades sobrepostas. Os offsets são caracteres Unicode Python, convertidos corretamente no navegador inclusive quando há emojis. O conteúdo das publicações é apresentado como texto, sem executar HTML recebido do índice. O painel de JSON permite inspecionar o documento completo.

Bootstrap e Vue são servidos localmente, com versões e licenças na pasta `tools/preview/vendor`. Não é necessário acessar uma CDN para usar a página.

Para retirar a página de teste mantendo a API:

```bash
docker compose --env-file .env.docker -f compose.yaml up -d --force-recreate api
```

Sem o override, as rotas do visualizador não são disponibilizadas. PostgreSQL e OpenSearch continuam sendo os serviços existentes do Ro-DOU.

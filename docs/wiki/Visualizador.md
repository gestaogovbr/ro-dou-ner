# Visualizador de entidades

A página em [tools/preview](../../tools/preview/README.md) é uma ferramenta temporária de inspeção manual. Ela consulta a API sem executar extração e não faz parte da imagem padrão.

## Habilitar

Configure os serviços existentes em `.env.docker` e use o override:

```bash
docker compose --env-file .env.docker -f compose.yaml -f compose.preview.yaml up -d --build api
```

Acesse `http://127.0.0.1:18000/preview`. A referência da API está em `/docs`.

O override monta `tools/preview` somente para leitura e define `RO_DOU_NER_PREVIEW_DIRECTORY`. Fora do Compose, a variável deve apontar para um diretório com `index.html` e assets. A API serve `/preview` e `/preview-assets` somente com essa configuração.

## Inspecionar publicações

A interface consulta `GET /publications?page=1&page_size=10`, permite selecionar publicação, alternar tipos, navegar por páginas e abrir o documento completo em JSON.

Cada item representa uma versão indexada. A publicação pode aparecer mais de uma vez; o total é de documentos do índice. Novos enriquecimentos podem alterar páginas entre requisições. A listagem exige OpenSearch configurado e índice disponível; veja [API](API.md).

A interface usa `body_text` canônico, preserva sobreposições e converte offsets Python para pontos de código Unicode no navegador, incluindo emojis. Publicações e JSON são interpolados como texto, sem executar HTML do índice.

Bootstrap e Vue são locais, com versões e licenças em `tools/preview/vendor`; não é necessário acessar CDN em runtime.

## Desabilitar

```bash
docker compose --env-file .env.docker -f compose.yaml up -d --force-recreate api
```

Sem override ou variável de configuração, as rotas não existem. API e serviços compartilhados continuam disponíveis.

## Verificar

```bash
node --test tests/frontend/test_highlights.cjs
```

Com a API ativa, confira carregamento, outra publicação, filtros, sobreposições, JSON, tamanho de página e navegação. Testes de marcações não substituem inspeção visual.

[← Página inicial](Home.md)

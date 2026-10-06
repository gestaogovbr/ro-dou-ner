# Visualizador temporário de entidades

Ferramenta de inspeção local que consome `GET /publications` da mesma API. O [guia do visualizador](../../docs/wiki/Visualizador.md) centraliza habilitação, navegação e remoção; o [contrato da API](../../docs/wiki/API.md) define paginação e versões.

## Organização e contrato

`index.html` é servido em `/preview`; os demais arquivos ficam em `/preview-assets` quando a prévia está configurada. Os assets são locais e a ferramenta não exige frontend adicional ou CDN em runtime.

Os offsets seguem índices de pontos de código Unicode Python em `[start, end)`. A marcação usa `Array.from` antes de recortar o texto e preserva todas as menções sobrepostas. Cores combinadas e tooltips exibem os tipos de cada segmento.

Textos de publicações, nomes e JSON são interpolados pelo Vue, sem `v-html` ou inserção de HTML recebido do índice. Todos os atributos de `_source` permanecem disponíveis no painel JSON. O total conta versões indexadas, incluindo versões da mesma publicação.

## Verificar alterações

Execute a partir da raiz do projeto:

```bash
node --test tests/frontend/test_highlights.cjs
```

Com a API em execução, abra `/preview` e confira seleção de publicação, filtros de tipos, entidades sobrepostas, JSON, tamanho da página e navegação.

## Dependências locais

- Bootstrap CSS 5.3.8: [documentação oficial](https://getbootstrap.com/docs/5.3/getting-started/download/).
  Origem: `https://cdn.jsdelivr.net/npm/bootstrap@5.3.8/dist/css/bootstrap.min.css`.
  SHA384: `sRIl4kxILFvY47J16cr9ZwB07vP4J8+LH7qKQnuqkuIAvNWLzeN8tE5YBujZqJLB`.
  Conferido com o SRI publicado na documentação oficial.
- Vue 3.5.13, distribuição global de produção:
  [uso sem build](https://vuejs.org/guide/quick-start.html#using-vue-from-cdn).
  Origem: `https://cdn.jsdelivr.net/npm/vue@3.5.13/dist/vue.global.prod.js`.
  SHA256: `c459ba7cc8db65c982589fa5d64c7ff478877e8e5b0fd75683207cec6a4e89e8`.

Licenças MIT dos dois projetos preservadas em `vendor/`.

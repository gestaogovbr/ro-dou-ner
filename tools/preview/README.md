# Visualizador temporário

Página de inspeção para testes locais. Consome `GET /publications` da mesma API,
mostra o texto canônico com as entidades, permite alternar tipos e navegar pelas
páginas, e mantém todos os atributos de `_source` no painel JSON. O total representa
documentos do índice, incluindo versões diferentes de uma mesma publicação.

O servidor disponibiliza `index.html` em `/preview` e os demais arquivos em
`/preview-assets` quando a prévia está habilitada na configuração da API. A página
não depende de um serviço frontend adicional nem de CDNs em tempo de execução.

As posições seguem o contrato Python: índices de pontos de código Unicode,
intervalo `[start, end)`, usando `Array.from` antes de recortar o texto. Cada
segmento preserva todas as entidades sobrepostas; cores combinadas e o tooltip
exibem os tipos. O conteúdo de documentos, nomes e JSON é sempre interpolado como
texto pelo Vue, sem `v-html` ou inserção de HTML vindo do índice.

Testes das marcações: `node --test tests/frontend/test_highlights.cjs`.
O fluxo visual deve ser validado com a API em execução: carregar `/preview`,
selecionar outra publicação, filtrar tipos, abrir JSON, trocar o tamanho e a página.

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

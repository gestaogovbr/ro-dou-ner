# Como contribuir

Contribuições para código, testes e documentação são bem-vindas. Antes de implementar uma mudança ampla, descreva o problema e o comportamento esperado em uma [Issue](https://github.com/xxggabriel/ro-dou-ner/issues).

## Preparar o ambiente

Use Python 3.12 ou 3.13 e uv. Clone o repositório, entre no diretório e instale as dependências fixadas:

```bash
uv sync --locked
```

O [início rápido](docs/wiki/Inicio-rapido.md) funciona offline. Integrações exigem serviços existentes e recursos de teste isolados; veja [Testes e validação](docs/wiki/Testes-e-validacao.md).

## Fazer uma alteração

1. Crie uma branch descritiva a partir da base definida para a contribuição.
2. Inspecione código, configuração e testes relevantes antes de alterar o comportamento.
3. Mantenha o escopo em uma mudança coerente e preserve as convenções existentes.
4. Atualize testes quando o contrato mudar e documentação quando a interface ou operação mudar.
5. Revise o diff e envie commits pequenos, com mensagens que expliquem a alteração.

Respeite a direção `adapters → application → domain`. Não introduza SDKs no domínio. Alterações de normalização, extração ou configuração devem preservar a rastreabilidade do pipeline; veja [Arquitetura](docs/wiki/Arquitetura.md).

## Verificar antes de enviar

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
node --test tests/frontend/test_highlights.cjs
uv build
```

Testes de serviços e modelo podem ser ignorados quando as variáveis necessárias não estão configuradas. Informe os skips e não apresente esse resultado como validação completa. A CI exige cobertura de pelo menos 90% com os backends de teste disponíveis.

## Preparar o pull request

Explique o problema, a solução e as verificações realmente executadas. Relacione Issues confirmadas; use `Closes` somente quando a alteração concluir o trabalho. Informe limitações, mudanças de contrato e impactos de migração quando existirem.

Nunca inclua `.env`, credenciais, dumps de publicações reais ou mensagens de SDKs que exponham dados. Nos relatos de erro, use exemplos sintéticos e inclua comando, tipo de erro, ambiente e resultado esperado.

## Editar a documentação

O [índice da documentação](docs/wiki/Home.md) organiza os guias por tarefa. Mantenha uma fonte principal por assunto e atualize a navegação ao criar páginas. Consulte [docs/README.md](docs/README.md) para as convenções de escrita e publicação na GitHub Wiki.

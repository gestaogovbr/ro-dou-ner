# Início rápido

Este guia apresenta uma execução offline e uma execução com a origem INLABS. Execute os comandos na raiz do repositório.

## Pré-requisitos

- Python 3.12 ou 3.13, Git e [uv](https://docs.astral.sh/uv/getting-started/installation/).
- Para INLABS: PostgreSQL existente, tabela `dou_inlabs.article_raw` e credenciais de origem e resultados.
- Para projeção e listagem: OpenSearch existente.
- Para Docker: Docker Compose e a rede compartilhada do Ro-DOU já criada.

## Experimentar offline

```bash
git clone --branch feat/inlabs-ner-architecture https://github.com/xxggabriel/ro-dou-ner.git
cd ro-dou-ner
uv sync --locked
uv run ro-dou-ner enrich-file tests/fixtures/evaluation-synthetic.jsonl --output /tmp/enrichments.jsonl
uv run ro-dou-ner benchmark tests/fixtures/evaluation-synthetic.jsonl --output /tmp/benchmark.json
```

O modo padrão `rules` não baixa modelos. `enrich-file` usa um repositório em memória e exporta enriquecimentos; `benchmark` avalia as anotações sintéticas. Consulte [CLI](CLI.md) para os formatos de entrada e [Extração e avaliação](Extracao-e-avaliacao.md) para interpretar métricas.

Os caminhos `/tmp` são exemplos para Linux/macOS. Em outro sistema, use um diretório temporário existente. Se o shell já contém variáveis `RO_DOU_NER_*`, elas continuam ativas; use um ambiente limpo para reproduzir os padrões.

## Processar INLABS

Copie o exemplo e substitua os placeholders pelas credenciais do ambiente existente:

```bash
cp .env.example .env
# Edite .env antes de carregá-lo.
set -a
source .env
set +a
uv run ro-dou-ner init-db
uv run ro-dou-ner process --date 2026-10-06
uv run ro-dou-ner process --publication-id inlabs:123456 --page-size 100
uv run ro-dou-ner serve
```

`source` e `set -a` aplicam-se a shells como Bash e Zsh. A aplicação não carrega `.env` automaticamente. Configure `RO_DOU_NER_DATABASE_DSN` para resultados e `RO_DOU_NER_INLABS_DSN` para a origem, preferencialmente com usuário de leitura dedicado.

Data e ID são exemplos; use publicações disponíveis na sua origem. `init-db` inicializa o schema de resultados e o índice quando OpenSearch está configurado. Ele não cria o banco ou a tabela INLABS.

A API fica em `http://127.0.0.1:8000`, com documentação interativa em `/docs`. Confira `/health` e consulte uma publicação já enriquecida. Sem OpenSearch, os endpoints individuais continuam disponíveis, mas `GET /publications` retorna 503.

Para containers, consulte [Operação](Operacao.md#executar-com-docker). Para parâmetros e precedência, consulte [Configuração](Configuracao.md).

[← Página inicial](Home.md)

<div align="center">

# Ro-DOU NER

**Entidades reconhecidas. Publicações preservadas. Resultados rastreáveis.**

Enriquecimento de publicações integrais do Diário Oficial da União a partir do INLABS, com extração de entidades, histórico de versões e API de leitura.

[![Python 3.12–3.13](https://img.shields.io/badge/python-3.12%20%E2%80%93%203.13-3776AB?logo=python&logoColor=white)](pyproject.toml)
[![Licença AGPL v3](https://img.shields.io/badge/license-AGPL--3.0-blue)](LICENSE)
[![Documentação](https://img.shields.io/badge/docs-guia_do_projeto-0969DA)](docs/wiki/Home.md)

[Documentação](docs/wiki/Home.md) · [Primeiros passos](docs/wiki/Inicio-rapido.md) · [API](docs/wiki/API.md) · [Como contribuir](CONTRIBUTING.md)

</div>

## Sobre o projeto

O Ro-DOU NER lê o texto completo e os metadados de `dou_inlabs.article_raw`, prepara um texto canônico e identifica entidades com regras determinísticas ou um pipeline híbrido com GLiNER. Cada resultado registra a revisão da publicação e a configuração do pipeline, permitindo reprocessamento e consulta ao histórico.

A origem INLABS é acessada em modo somente de leitura. Os resultados ficam no schema `ro_dou_ner`, e a projeção opcional usa um índice OpenSearch próprio. PostgreSQL e OpenSearch são reutilizados do ambiente Ro-DOU.

> **Status:** MVP implementado. O checkpoint GLiNER é ilustrativo; a qualidade no corpus real de diários oficiais ainda precisa ser avaliada com anotações representativas.

## Recursos

- **Extração por regras:** processos, CPF/CNPJ, datas, valores monetários e referências legais.
- **Modo híbrido:** GLiNER opcional para pessoas, organizações e locais, com checkpoints imutáveis.
- **Texto integral:** normalização de HTML, chunks com sobreposição e validação de offsets Unicode.
- **Histórico e recuperação:** persistência versionada, tentativas auditáveis e repetição idempotente de lotes.
- **Consumo:** CLI, API de leitura, projeção OpenSearch e visualizador local opcional.
- **Integração:** gatilho Airflow por eventos de carga INLABS e avaliação por span exato.

## Experimente em poucos minutos

Requisitos: **Python 3.12 ou 3.13**, Git e [uv](https://docs.astral.sh/uv/getting-started/installation/). Este exemplo usa dados sintéticos e funciona sem banco, OpenSearch ou download de modelo.

```bash
git clone --branch feat/inlabs-ner-architecture https://github.com/xxggabriel/ro-dou-ner.git
cd ro-dou-ner
uv sync --locked
uv run ro-dou-ner enrich-file tests/fixtures/evaluation-synthetic.jsonl --output /tmp/enrichments.jsonl
uv run ro-dou-ner benchmark tests/fixtures/evaluation-synthetic.jsonl --output /tmp/benchmark.json
```

O primeiro comando gera resultados JSONL; o segundo gera métricas do fixture sintético. Para processar publicações INLABS e persistir resultados, siga o [guia de instalação](docs/wiki/Inicio-rapido.md#processar-inlabs).

## Encontre o que precisa

| Objetivo | Guia |
| --- | --- |
| Instalar e executar o primeiro lote | [Início rápido](docs/wiki/Inicio-rapido.md) |
| Ajustar ambiente, pipeline e taxonomia | [Configuração](docs/wiki/Configuracao.md) |
| Usar comandos e arquivos JSONL | [CLI](docs/wiki/CLI.md) |
| Consultar publicações e entidades | [API](docs/wiki/API.md) |
| Entender módulos, offsets e versões | [Arquitetura](docs/wiki/Arquitetura.md) |
| Operar Docker, persistência e recuperação | [Operação](docs/wiki/Operacao.md) |
| Acionar enriquecimento pelo Airflow | [Airflow](docs/wiki/Airflow.md) |
| Executar GLiNER e avaliar resultados | [Extração e avaliação](docs/wiki/Extracao-e-avaliacao.md) |
| Inspecionar entidades no navegador | [Visualizador](docs/wiki/Visualizador.md) |
| Executar testes e verificar evidências | [Testes e validação](docs/wiki/Testes-e-validacao.md) |

## Desenvolvimento

A arquitetura segue um monólito modular com ports and adapters: `adapters → application → domain`. O bootstrap conecta as implementações, e testes verificam a direção das dependências.

```text
src/ro_dou_ner/
├── domain/         # Publicações, menções, validação e identidade
├── application/    # Casos de uso, portas, DTOs e avaliação
├── adapters/       # INLABS, extração, PostgreSQL, OpenSearch e API
└── bootstrap/      # Configuração, composição e CLI
configs/            # Pipelines e taxonomia versionados
integrations/       # Template de DAG Airflow
tests/              # Contratos, unidades, aceitação, integração e modelo
docs/wiki/          # Documentação organizada em páginas de Wiki
tools/              # Testes com serviços compartilhados e visualizador
```

Veja [CONTRIBUTING.md](CONTRIBUTING.md) para preparar alterações e executar as verificações. Relate problemas nas [Issues](https://github.com/xxggabriel/ro-dou-ner/issues), incluindo passos de reprodução e versões, sem credenciais ou dados sensíveis.

## Licença

Distribuído sob a **GNU Affero General Public License v3.0 (AGPL-3.0-only)**. Consulte o texto completo em [LICENSE](LICENSE).

# Testes e validação

Execute os comandos na raiz do projeto. Verificações sem backends não substituem a suíte de integração completa.

## Verificações locais

```bash
uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run pytest
node --test tests/frontend/test_highlights.cjs
uv build
```

A suíte cobre contratos, Unicode, cobertura dos chunks, offsets, entidades inválidas, consolidação, arquitetura, concorrência, crash, atomicidade, histórico, retries, nested e fluxo INLABS → extração → PostgreSQL → OpenSearch → API.

## Integrações em recursos isolados

Configure `RO_DOU_NER_TEST_POSTGRES_DSN` e `RO_DOU_NER_TEST_OPENSEARCH_URL` para recursos de teste. O nome do banco deve conter `test`. Fixtures preparam uma origem INLABS sintética nesse banco e removem seus registros/índices; nunca aponte os testes para a origem real.

Variáveis ausentes causam skips explícitos. Serviços configurados, mas indisponíveis, fazem os testes falhar.

```bash
uv run pytest --cov=ro_dou_ner --cov-fail-under=90
```

O helper reutiliza os serviços locais, lê credenciais do container em memória e cria o banco dedicado caso ausente. Não cria containers nem grava credenciais em arquivos:

```bash
uv run tools/test_shared_services.py
uv run tools/test_shared_services.py --help
```

Padrões: container `ro-dou-postgres-1`, porta 5432, banco `ro_dou_ner_test` e OpenSearch `http://127.0.0.1:9200`. O helper precisa de Docker e permissão para criar o banco se necessário. Índices de teste têm nomes temporários exclusivos. Confira os alvos antes de executar.

## Smoke com modelo real

Ative explicitamente o download e execução dos artefatos imutáveis:

```bash
uv sync --locked --extra gliner
RO_DOU_NER_TEST_GLINER=1 uv run --extra gliner pytest tests/model -q
# Suíte com serviços compartilhados e modelo:
uv run tools/test_shared_services.py --with-model
```

O smoke verifica cobertura integral de documento longo, menções não vazias e spans válidos. Não aprova qualidade em corpus real.

## GitHub Actions

O [workflow validation](../../.github/workflows/ci.yml) executa lint, formato, testes com cobertura mínima de 90% e build. Apenas nos runners efêmeros são provisionados PostgreSQL e OpenSearch de teste próprios.

O job de modelo roda por `workflow_dispatch` com `run_model=true`. O workflow Python não executa atualmente os testes Node do visualizador; rode-os localmente quando alterar marcações.

Configuração de workflow não comprova execução remota bem-sucedida. Confira o run do commit antes de informar status de CI.

## Evidências e qualidade

O [registro de 2026-10-06](../../docs/validacao.md) preserva resultados históricos e limitações do MVP. Ele não garante commits posteriores. Registre comando, ambiente, resultado, skips e itens não verificados em cada entrega.

A avaliação disponível é sintética. Consulte [Extração e avaliação](Extracao-e-avaliacao.md) antes de interpretar métricas como qualidade.

[← Página inicial](Home.md)

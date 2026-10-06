# Validação de implementação — 2026-10-06

- `uv run tools/test_shared_services.py --with-model`: **209 testes passaram, sem skips; cobertura 94,04%**. Python 3.12.13 no host. PostgreSQL e OpenSearch existentes do Ro-DOU foram reutilizados; apenas banco dedicado `ro_dou_ner_test` e índices temporários próprios foram usados pelos testes.
- `uv run ruff check .` e `uv run ruff format --check .`: aprovados.
- `uv build`: wheel e sdist gerados; wheel contém o recurso `schema.sql`.
- `docker build -t ro-dou-ner:validation .`: imagem padrão aprovada.
- Compose validado com configuração de PostgreSQL existente; contém apenas a aplicação e rede externa.
- Template DAG importado no runtime Airflow 3 existente usando container transitório da mesma imagem: `ro_dou_ner_inlabs`, task `enrich_loaded_publications`, timetable por Asset. A task não foi implantada ou executada no scheduler ativo. O caminho de compatibilidade Airflow 2.10 não foi executado neste ambiente.
- Smoke GLiNER real: checkpoint/tokenizer fixados no exemplo; documento longo subdividido integralmente, menções não vazias e todos os spans válidos. Isso verifica contrato técnico, não qualidade de reconhecimento no corpus real.
- Fluxo com publicação real `inlabs:51596583`: leitura somente de leitura da origem, enriquecimento por regras com 10 menções, persistência em banco de teste, projeção em índice temporário, consulta pela API e segunda execução idempotente. Ao concluir, seus resultados de teste foram removidos. Origem e índice `dou` mantiveram **6.482 publicações/documentos**.

A suíte emite avisos de depreciação das bibliotecas Starlette/httpx e Torch/JIT; não houve falhas. A CI foi configurada, mas não houve execução remota de GitHub Actions nesta entrega.

O benchmark disponível é sintético. Falta um corpus representativo real anotado para aprovar modelo, threshold e qualidade do NER.

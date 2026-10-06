# Registro de validação — 2026-10-06

Este registro preserva as evidências documentadas na entrega do MVP, antes da reorganização da documentação. Os resultados são **históricos** e não foram repetidos integralmente na revisão documental. Para comandos atuais, veja [Testes e validação](wiki/Testes-e-validacao.md).

## Verificações registradas

| Verificação | Resultado registrado | Escopo |
| --- | --- | --- |
| `uv run tools/test_shared_services.py --with-model` | 209 testes passaram, sem skips; cobertura 94,04% | Python 3.12.13; serviços existentes, banco `ro_dou_ner_test` e índices temporários |
| `uv run ruff check .` | Aprovado | Lint |
| `uv run ruff format --check .` | Aprovado | Formatação |
| `uv build` | Wheel e sdist gerados | Wheel contendo `schema.sql` |
| `docker build -t ro-dou-ner:validation .` | Aprovado | Imagem padrão |
| Configuração Compose | Validada | Aplicação e rede externa com PostgreSQL existente |
| Importação da DAG em Airflow 3 | DAG `ro_dou_ner_inlabs`, task `enrich_loaded_publications`, timetable por Asset | Container transitório da mesma imagem do runtime existente |
| Smoke GLiNER real | Documento longo subdividido integralmente, menções não vazias e spans válidos | Checkpoint/tokenizer fixados no exemplo |

## Fluxo com publicação real

O registro original relata uso de `inlabs:51596583`: leitura da origem, regras com 10 menções, persistência em banco de teste, projeção em índice temporário, consulta pela API e segunda execução idempotente. Os resultados de teste foram removidos ao concluir. Origem e índice `dou` mantiveram 6.482 publicações/documentos naquele momento.

Esses números representam aquela execução, não o estado atual dos serviços.

## Limitações registradas

- A task não foi implantada ou executada no scheduler ativo.
- O caminho Airflow 2.10 não foi executado naquele ambiente.
- A CI estava configurada, sem execução remota registrada na entrega.
- Houve avisos de depreciação de Starlette/httpx e Torch/JIT, sem falhas reportadas.
- O benchmark era sintético; corpus representativo real anotado ainda era necessário para aprovar modelo, threshold e qualidade.

Smoke comprova contrato técnico, não qualidade. Confira evidências do commit e ambiente de interesse antes de decisões operacionais.

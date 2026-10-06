# Integração Airflow

O template [ro_dou_ner_dag.py](../../integrations/airflow/ro_dou_ner_dag.py) conecta eventos INLABS ao enriquecimento sem modificar a DAG produtora do Ro-DOU.

## Preparar o runtime

1. Disponibilize o pacote no runtime da task, com Python 3.12 ou 3.13.
2. Configure PostgreSQL de resultados, origem INLABS e OpenSearch opcional.
3. Execute `ro-dou-ner init-db` nesse ambiente antes do primeiro lote.
4. Copie o template para o diretório de DAGs.

Há caminhos de importação para Dataset no Airflow 2.10+ e Asset no Airflow 3. Workers Python 3.11 precisam de atualização ou runtime separado para executar a CLI; o pacote não suporta Python 3.11.

## Eventos e execução manual

A DAG `ro_dou_ner_inlabs` usa `inlabs` **ou** `inlabs_edicao_extra`. A task `enrich_loaded_publications` lê `reference_date` de todos os eventos coalescidos, deduplica datas e reprocessa o dia completo de forma idempotente.

Uma execução manual exige esta configuração:

```json
{"reference_date":"2026-10-06"}
```

Metadados inválidos, datas ausentes e falhas de processamento/projeção fazem a task falhar. O template configura dois retries, intervalo de dois minutos, `catchup=False` e `max_active_runs=1`.

## Configuração

Use `RO_DOU_NER_DATABASE_DSN`, `RO_DOU_NER_INLABS_DSN` e OpenSearch opcional. Para híbrido, instale o extra GLiNER e forneça modo, IDs e revisões imutáveis de modelo/tokenizer conforme o [exemplo de pipeline](../../configs/pipelines/hybrid-example-v1.json).

O template usa `Settings.from_environment()` e não recebe `--pipeline` pela CLI. Veja [Configuração](Configuracao.md) para os campos disponíveis no ambiente.

## Verificação e limites

Valide importação, metadados dos eventos e processamento de uma data em recursos de teste antes de instalar no scheduler. A importação no Airflow 3 foi registrada na [validação histórica](../../docs/validacao.md); isso não comprova implantação, execução no scheduler ou funcionamento do caminho Airflow 2.10 naquele ambiente.

O produtor permanece independente. Persistência idempotente permite repetir datas, e retries recuperam projeções a partir dos resultados salvos; veja [Operação](Operacao.md).

## Referência complementar

- [Datasets no Airflow 2.10.1](https://airflow.apache.org/docs/apache-airflow/2.10.1/authoring-and-scheduling/datasets.html)

[← Página inicial](Home.md)

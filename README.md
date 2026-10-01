# ro-dou-enrichment

Serviço GLiNER2 e orquestração do enriquecimento das publicações do INLABS
indexadas no OpenSearch pelo Ro-DOU. O modelo roda em um serviço HTTP separado;
a DAG roda no mesmo Airflow do Ro-DOU.

## Instalação

Mantenha os repositórios lado a lado:

```text
/opt/Ro-dou/
/opt/ro-dou-enrichment/
```

O Compose do Ro-DOU gerencia o Airflow; o Compose deste repositório gerencia
somente o serviço GLiNER. No diretório do Ro-DOU:

```bash
docker compose up -d
make gliner-up
make create-gliner-variables
```

O Compose monta estes diretórios em todos os serviços Airflow:

| Origem no ro-dou-enrichment | Destino no Airflow |
|---|---|
| `src/ro_dou_enrichment` | `/opt/airflow/dags/ro_dou_enrichment` |
| `dag` | `/opt/airflow/dags/ro_dou_enrichment_dags` |

O processador descobre a DAG e o scheduler com LocalExecutor encontra o pacote
ao executar as tasks. O API server recebe os mesmos arquivos. O pacote usa o
`PYTHONPATH` existente da imagem do Ro-DOU; não requer instalação adicional.
`requests` e `opensearch-py` já estão nessa imagem. PyTorch permanece apenas no
serviço de inferência, construído a partir do Dockerfile deste repositório.

O Compose do Ro-DOU cria a rede de nome fixo `ro-dou-network`. O Compose
deste repositório a utiliza como rede externa. Suba o Ro-DOU primeiro para
que ela exista; não é necessário criá-la manualmente nem configurar seu nome.
O Airflow acessa `http://gliner:8000` por essa rede, sem porta publicada no host. O enriquecimento continua desligado
por padrão; `make create-gliner-variables` habilita OpenSearch e enriquecimento.

A DAG mantém o ID `ro-dou_inlabs_gliner_enrich`. Atualize o Ro-DOU para a revisão
que remove a cópia antiga em `dag_load_inlabs/`: apenas um arquivo deve definir
esse ID. Os dois repositórios precisam estar presentes antes de habilitar o
recurso. Recrie os contêineres existentes com `docker compose up -d` para aplicar
os volumes.

Em CeleryExecutor, monte os mesmos diretórios também em todos os workers. Em
KubernetesExecutor, disponibilize o pacote e a DAG na imagem ou nos volumes dos
pods de tasks. Os executores devem usar a mesma revisão que o processador de DAGs.

## Configuração e contratos

A configuração do modelo fica em `config.yaml`. Para autenticar o serviço,
defina `GLINER_API_TOKEN` no `.env` deste repositório e o mesmo valor na variável
`RO_DOU_GLINER_API_TOKEN` do Airflow. Não versione credenciais.

A integração utiliza Airflow 3 e os contratos da branch `gliner2` do Ro-DOU
(commit `e032912`): índice `dou`, SHA-256 do `texto_plain` completo em UTF-8,
assets `inlabs` / `inlabs_edicao_extra` e metadado `reference_date`. O contrato
de hashing deve permanecer compatível com o indexador do Ro-DOU.

Os utilitários de conexão OpenSearch, datas e notificação de falhas vêm do
núcleo `ro_dou_src`. A DAG importa o enriquecedor exclusivamente de
`ro_dou_enrichment`; a lógica de enriquecimento não depende do antigo pacote
`ro_dou_src.utils.gliner`.

## Testes e operação

Neste repositório, `make gliner-tests` testa serviço e enriquecedor com mocks; o teste
de integração Airflow é ignorado na imagem de inferência, que não inclui Airflow.
`make gliner-down` para somente o serviço. Os alvos `gliner-up`, `gliner-down`
e `gliner-tests` do Ro-DOU encaminham os comandos para este repositório.
`make create-gliner-variables` continua configurando o Airflow pelo Ro-DOU.

Para testar a integração, copie `tests/` para `/tmp/enrichment-tests` e `dag/`
para `/tmp/dag` no contêiner Airflow, depois execute:

```bash
docker exec airflow-api-server sh -c 'PYTHONPATH=/opt/airflow/dags python -m pytest -q /tmp/enrichment-tests'
```

Os testes usam mocks e não exigem inferência real nem chamadas externas. A
documentação detalhada fica em
[Enriquecimento com GLiNER2](https://gestaogovbr.github.io/Ro-dou/como_utilizar/enriquecimento_gliner/).

Para desligar todo o ambiente e liberar a rede, execute `docker compose down`
primeiro no `ro-dou-enrichment` e depois no Ro-DOU, sem `--volumes`.

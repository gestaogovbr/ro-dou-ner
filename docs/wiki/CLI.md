# Referência da CLI

A CLI executa o mesmo caso de uso utilizado pelas integrações. Use `uv run ro-dou-ner --help` e `uv run ro-dou-ner <comando> --help` para consultar opções.

## Comandos

| Comando | Entrada | Resultado |
| --- | --- | --- |
| `init-db` | PostgreSQL e OpenSearch opcional | Inicializa schema e cria/verifica índice |
| `process` | Data e/ou IDs INLABS | Persiste resultados e projeta quando configurado |
| `enrich-file` | JSONL e `--output` obrigatório | Exporta enriquecimentos usando memória |
| `benchmark` | JSONL anotado e `--output` obrigatório | Exporta avaliação e imprime relatório |
| `serve` | `--host` e `--port` opcionais | Inicia API; padrões `127.0.0.1:8000` |

## Opções globais

Coloque as opções globais **antes** do subcomando: `--pipeline`, `--mode`, `--model-id`, `--model-revision`, `--tokenizer-id` e `--tokenizer-revision`.

```bash
uv run ro-dou-ner --pipeline configs/pipelines/rules-v1.json enrich-file tests/fixtures/evaluation-synthetic.jsonl --output /tmp/enrichments.jsonl
```

Veja [Configuração](Configuracao.md) para precedência. As opções específicas do subcomando vêm depois dele.

## Processar INLABS

```bash
uv run ro-dou-ner process --date 2026-10-06 --page-size 500
uv run ro-dou-ner process --publication-id inlabs:123456 --publication-id inlabs:123457
```

É obrigatório fornecer `--date` ou pelo menos um `--publication-id`. Data usa `AAAA-MM-DD`; IDs usam `inlabs:<inteiro não negativo>`. IDs podem ser repetidos. Ao combinar data e IDs, os filtros são cumulativos. `--page-size` é positivo e tem padrão 500.

A origem usa paginação keyset em ID crescente. Erro de leitura aborta o lote; falhas individuais ficam no relatório, e as demais publicações continuam.

## Arquivos offline

Cada linha não vazia deve ser um objeto JSON com `publication_id`, `body_text` e `metadata` opcional:

```json
{"publication_id":"demo:1","body_text":"Publicado em 06/10/2026.","metadata":{"dataset_kind":"synthetic"}}
```

`enrich-file` escreve um resultado por publicação com execução bem-sucedida. O armazenamento é temporário: use `process` para persistência durável. HTML é normalizado; offsets do resultado referem-se ao texto canônico.

`benchmark` também exige `mentions` com `label`, `surface`, `start` e `end`, anotados no texto canônico. O [guia de avaliação](Extracao-e-avaliacao.md#avaliar-um-dataset) explica as métricas.

## Saída e códigos de retorno

`process` e `enrich-file` imprimem JSON com `processed`, `skipped`, `failed`, `projection_failed` e `errors`. Uma versão existente conta como `skipped` e pode ser projetada novamente. Uma chave ocupada também conta como `skipped`.

- `0`: execução concluída sem falhas reportadas.
- `1`: falha de execução, processamento ou projeção; no benchmark, documentos com falha.
- Erros de sintaxe de argumentos são tratados pelo parser argparse.

Exceções capturadas no limite da CLI são emitidas em stderr como `status=failed` e `error_type`, sem a mensagem bruta do SDK. Logs distinguem publicação, etapa e tipo de erro. Consulte [Operação](Operacao.md#diagnosticar-falhas) antes de repetir o lote.

Fonte: [bootstrap/cli.py](../../src/ro_dou_ner/bootstrap/cli.py).

[← Página inicial](Home.md)

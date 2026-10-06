# Extração e avaliação

O pipeline oferece regras determinísticas por padrão e GLiNER opcional. Ambos produzem menções sujeitas ao contrato de texto canônico e offsets.

## Taxonomia

A [taxonomia `ner-v1`](../../configs/taxonomies/ner-v1.json) exige os oito labels, mesmo quando o extrator não produz todos eles.

| Label | Entidade | Modo |
| --- | --- | --- |
| `PERSON` | Pessoa | Híbrido |
| `ORGANIZATION` | Organização | Híbrido |
| `LOCATION` | Local | Híbrido |
| `PROCESS_NUMBER` | Número de processo | Regras e híbrido |
| `IDENTIFIER` | CPF/CNPJ | Regras e híbrido |
| `DATE` | Data | Regras e híbrido |
| `MONEY` | Valor monetário | Regras e híbrido |
| `LEGAL_REFERENCE` | Referência legal | Regras e híbrido |

Regras verificam dígitos de CPF/CNPJ e calendário das datas. Processos são reconhecidos por formato. O híbrido acrescenta pessoas, organizações e locais; regras continuam ativas no documento completo.

Scores entre extratores não são probabilidades comparáveis. A consolidação dá prioridade às regras e preserva sobreposições distintas; veja [Arquitetura](Arquitetura.md#texto-e-offsets).

## Executar GLiNER

```bash
uv sync --locked --extra gliner
uv run --extra gliner ro-dou-ner --pipeline configs/pipelines/hybrid-example-v1.json enrich-file tests/fixtures/evaluation-synthetic.jsonl --output /tmp/hybrid.jsonl
uv run --extra gliner ro-dou-ner --pipeline configs/pipelines/hybrid-example-v1.json process --date 2026-10-06
```

Mantenha `--extra gliner` em `uv run` para conservar a dependência opcional. O primeiro download exige Hugging Face e espaço para pesos. O checkpoint é **ilustrativo**, sem aprovação de qualidade no corpus de diários oficiais.

O [exemplo](../../configs/pipelines/hybrid-example-v1.json) fixa commits de modelo multilíngue e tokenizer/backbone. Use IDs Hugging Face e SHAs imutáveis de 40 caracteres. Checkpoints sem tokenizer/configuração próprios exigem `tokenizer_id` e `tokenizer_revision` também fixados.

Diretórios locais e fallback para artefatos remotos não fixados são rejeitados. Pesos devem ser safetensors. O adaptador suporta processadores uni-encoder inspecionados do GLiNER 0.2.29.

O adaptador considera limites de palavras/subwords, inclusive prompts dos labels, subdivide chunks e remapeia offsets. Orçamentos desconhecidos, tokens individuais que não cabem e avisos de truncamento causam falha explícita.

## Avaliar um dataset

Anote cada documento JSONL no **texto canônico**. Exemplo sintético de uma linha:

```json
{"publication_id":"demo:1","body_text":"Publicado em 06/10/2026.","metadata":{"dataset_kind":"synthetic"},"mentions":[{"label":"DATE","surface":"06/10/2026","start":13,"end":23}]}
```

```bash
uv run ro-dou-ner benchmark tests/fixtures/evaluation-synthetic.jsonl --output /tmp/benchmark.json
```

A avaliação compara **documento + span exato + label**. Duplicatas contam uma vez; documentos com falha continuam nos denominadores e contribuem falsos negativos. Denominadores zero retornam zero; macro inclui os oito labels.

O relatório inclui precision/recall/F1 por tipo e micro/macro, cobertura, falhas, latência, throughput, alocações Python e pico RSS. Registra SHA-256 do dataset e proveniência do pipeline. Divergência entre texto anotado e texto produzido é falha, evitando métricas com offsets incompatíveis.

## Interpretar desempenho e qualidade

O [fixture](../../tests/fixtures/evaluation-synthetic.jsonl) contém cinco documentos sintéticos para verificar contratos. Ele não demonstra qualidade em publicações reais. Para aprovar checkpoint, prompts ou threshold, prepare corpus representativo anotado e compare pipelines no mesmo protocolo.

Timing inclui processamento/validação e exclui leitura do dataset. `tracemalloc` exclui alocações nativas/GPU; RSS é o pico do processo inteiro, não memória exclusiva do modelo. Memória GPU não é medida.

Registre dataset/split, código, configuração, seed quando aplicável, ambiente, hardware e condições da medição. Um smoke confirma carregamento, cobertura e offsets, sem aprovar qualidade.

Fonte: [evaluation.py](../../src/ro_dou_ner/application/evaluation.py). Verificação: [Testes e validação](Testes-e-validacao.md).

## Artefatos e implementação de referência

- [Processamento do GLiNER 0.2.29](https://github.com/urchade/GLiNER/blob/v0.2.29/gliner/data_processing/processor.py)
- [Checkpoint multilíngue fixado no exemplo](https://huggingface.co/urchade/gliner_multi-v2.1/tree/443d26d654e0324125a96bebd8e796c14ff2efe6)
- [Tokenizer/backbone fixado no exemplo](https://huggingface.co/microsoft/mdeberta-v3-base/tree/a0484667b22365f84929a935b5e50a51f71f159d)

[← Página inicial](Home.md)

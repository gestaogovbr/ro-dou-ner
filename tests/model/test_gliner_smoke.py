"""Opt-in real-model contract; this checkpoint is illustrative, not quality-approved."""

import os

import pytest

from ro_dou_ner.adapters.extraction.gliner import GlinerExtractor
from ro_dou_ner.domain.mentions import validate_mention
from ro_dou_ner.domain.publications import TextChunk


@pytest.mark.model
@pytest.mark.skipif(
    os.getenv("RO_DOU_NER_TEST_GLINER") != "1",
    reason="set RO_DOU_NER_TEST_GLINER=1 to download and run the pinned checkpoint",
)
def test_pinned_multilingual_gliner_real_model_full_document_contract():
    # Official HuggingFace API commit, verified 2026-10-06:
    # https://huggingface.co/api/models/urchade/gliner_multi-v2.1
    adapter = GlinerExtractor(
        "urchade/gliner_multi-v2.1",
        "443d26d654e0324125a96bebd8e796c14ff2efe6",
        tokenizer_id="microsoft/mdeberta-v3-base",
        tokenizer_revision="a0484667b22365f84929a935b5e50a51f71f159d",
    )
    text = "Maria Silva trabalha no Ministério da Saúde em Brasília. " * 50
    text += "João Pereira trabalha na Universidade de São Paulo."
    model = adapter._load()
    windows = adapter._windows(model, text)
    assert len(windows) > 1
    assert windows[0][0] == 0
    assert windows[-1][0] + len(windows[-1][1]) == len(text)
    for (start, window), (next_start, _) in zip(windows, windows[1:], strict=False):
        assert next_start <= start + len(window)
    mentions = adapter.extract(TextChunk(0, len(text), text))
    assert mentions
    for mention in mentions:
        validate_mention(mention, text, adapter.labels.values())

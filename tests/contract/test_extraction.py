import json
import re
import sys
import warnings
from pathlib import Path
from types import SimpleNamespace

import pytest

from ro_dou_ner.adapters.extraction.gliner import GlinerExtractor
from ro_dou_ner.adapters.extraction.rules import RuleExtractor
from ro_dou_ner.domain.mentions import validate_mention
from ro_dou_ner.domain.publications import TextChunk


def chunk(text):
    return TextChunk(0, len(text), text)


def test_rules_cover_taxonomy_and_return_exact_local_spans():
    text = "Processo 0000001-00.2026.1.01.0001 e 12345.123456/2026-12. CPF: 52998224725. CNPJ 11.222.333/0001-81. Data 29/02/2024 ou 6 de outubro de 2026. R$ 1.234,56. Lei nº 14.133/2021 e Decreto 12.345."
    mentions = RuleExtractor().extract(chunk(text))
    assert {item.label for item in mentions} == {
        "PROCESS_NUMBER",
        "IDENTIFIER",
        "DATE",
        "MONEY",
        "LEGAL_REFERENCE",
    }
    assert {item.surface for item in mentions if item.label == "LEGAL_REFERENCE"} == {
        "Lei nº 14.133/2021",
        "Decreto 12.345",
    }
    assert len(mentions) == 9
    for mention in mentions:
        validate_mention(mention, text)
        assert mention.score is None


def test_invalid_dates_and_identifiers_are_ignored_and_boundaries_hold():
    text = "31/02/2024 29/02/2023 00/10/2026 32 de janeiro de 2026 CPF 11111111111 CPF 52998224724 CNPJ 11222333000182 x529.982.247-25x"
    assert RuleExtractor().extract(chunk(text)) == ()


def test_rules_context_and_calendar_validity():
    text = (
        "52998224725 CPF 52998224725 CNPJ 11222333000181 1º de MARÇO de 2024 29-02-2024 29/02-2024"
    )
    mentions = RuleExtractor().extract(chunk(text))
    assert [item.surface for item in mentions] == [
        "52998224725",
        "11222333000181",
        "1º de MARÇO de 2024",
        "29-02-2024",
    ]


class FakeTokenizer:
    def __init__(self, limit=60, subword_multiplier=1):
        self.model_max_length = limit
        self.subword_multiplier = subword_multiplier

    def __call__(self, batches, **kwargs):
        assert kwargs["truncation"] is False
        assert kwargs["is_split_into_words"] is True
        return {
            "input_ids": [[0] * (2 + len(words) * self.subword_multiplier) for words in batches]
        }


class FakeModel:
    def __init__(self, max_len=8, tokenizer_limit=60, subword_multiplier=1):
        self.config = SimpleNamespace(max_len=max_len)
        self.data_processor = SimpleNamespace(
            words_splitter=lambda text: (
                (match.group(), *match.span()) for match in re.finditer(r"\S+", text)
            ),
            transformer_tokenizer=FakeTokenizer(tokenizer_limit, subword_multiplier),
            prepare_inputs=lambda batches, labels: (
                [
                    ["[ENT]", "person", "[ENT]", "organization", "[ENT]", "location", "[SEP]"]
                    + words
                    for words in batches
                ],
                [7] * len(batches),
            ),
        )
        self.calls = []
        self.prediction = None

    def predict_entities(self, text, labels, threshold):
        self.calls.append(text)
        assert len(list(self.data_processor.words_splitter(text))) <= self.config.max_len
        if self.prediction is not None:
            return [self.prediction]
        return [
            {
                "label": "person",
                "text": match.group(),
                "start": match.start(),
                "end": match.end(),
                "score": 0.9,
            }
            for match in re.finditer(r"Maria", text)
        ]


def extractor(model, **kwargs):
    return GlinerExtractor("test/model", "a" * 40, model=model, **kwargs)


@pytest.mark.parametrize("max_len,token_limit,multiplier", [(8, 60, 1), (100, 16, 1), (100, 22, 2)])
def test_gliner_windows_preserve_tail_and_overlap_offsets(max_len, token_limit, multiplier):
    text = "Maria " + "word " * 50 + "Maria"
    model = FakeModel(max_len, token_limit, multiplier)
    mentions = extractor(model, overlap_words=3).extract(chunk(text))
    assert [(item.start, item.end) for item in mentions] == [(0, 5), (len(text) - 5, len(text))]
    assert len(model.calls) > 1
    assert model.calls[-1].endswith("Maria")
    for mention in mentions:
        validate_mention(mention, text)


@pytest.mark.parametrize(
    "prediction",
    [
        {"label": "person", "text": "Maria", "start": -1, "end": 5, "score": 0.9},
        {"label": "person", "text": "other", "start": 0, "end": 5, "score": 0.9},
        {"label": "person", "text": "Maria", "start": 0, "end": 100, "score": 0.9},
        {"label": "unknown", "text": "Maria", "start": 0, "end": 5, "score": 0.9},
        {"label": "person", "text": "Maria", "start": 0, "end": 5, "score": float("nan")},
        {"label": "person", "text": "Maria", "start": 0, "end": 5, "score": None},
    ],
)
def test_gliner_rejects_invalid_predictions(prediction):
    model = FakeModel()
    model.prediction = prediction
    with pytest.raises(ValueError):
        extractor(model).extract(chunk("Maria"))


def test_gliner_filters_below_threshold():
    model = FakeModel()
    model.prediction = {"label": "person", "text": "Maria", "start": 0, "end": 5, "score": 0.4}
    assert extractor(model).extract(chunk("Maria")) == ()


@pytest.mark.parametrize(
    "revision", ["", "main", "latest", "HEAD", "master", "v2.1", "a" * 39, "z" * 40, None]
)
def test_gliner_checkpoint_must_be_pinned(revision):
    with pytest.raises(ValueError):
        GlinerExtractor("test/model", revision)


@pytest.mark.parametrize("threshold", [-0.1, 1.1, float("nan"), True])
def test_gliner_validates_threshold(threshold):
    with pytest.raises(ValueError):
        extractor(FakeModel(), threshold=threshold)


def test_gliner_fails_before_inference_for_unknown_budget_and_oversized_word():
    for model in (FakeModel(tokenizer_limit=10**30), FakeModel(tokenizer_limit=9)):
        with pytest.raises(RuntimeError):
            extractor(model).extract(chunk("Maria"))
        assert model.calls == []


def test_gliner_fails_if_splitter_silently_drops_tail():
    model = FakeModel()
    model.data_processor.words_splitter = lambda text: iter((("Maria", 0, 5),))
    with pytest.raises(RuntimeError, match="omitted"):
        extractor(model).extract(chunk("Maria tail"))
    assert model.calls == []


def test_gliner_rejects_local_model_path_even_with_revision(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "test" / "model").mkdir(parents=True)
    with pytest.raises(ValueError):
        extractor(FakeModel())


@pytest.mark.parametrize(
    "tokenizer_id,revision",
    [("test/tokenizer", "main"), (None, "a" * 40), ("test/tokenizer", None)],
)
def test_gliner_rejects_unpinned_secondary_tokenizer(tokenizer_id, revision):
    with pytest.raises(ValueError):
        extractor(FakeModel(), tokenizer_id=tokenizer_id, tokenizer_revision=revision)


def test_gliner_uses_encoder_budget_when_tokenizer_limit_is_unknown():
    model = FakeModel(max_len=100, tokenizer_limit=10**30)
    model.model = SimpleNamespace(
        token_rep_layer=SimpleNamespace(
            bert_layer=SimpleNamespace(
                model=SimpleNamespace(config=SimpleNamespace(max_position_embeddings=16))
            )
        )
    )
    text = "word " * 25 + "Maria"
    mentions = extractor(model).extract(chunk(text))
    assert mentions[-1].surface == "Maria"
    assert len(model.calls) > 1


def test_gliner_converts_truncation_warnings_to_errors():
    model = FakeModel()

    def warn(*args, **kwargs):
        warnings.warn("Sentence has been truncated", UserWarning, stacklevel=1)
        return []

    model.predict_entities = warn
    with pytest.raises(UserWarning, match="truncated"):
        extractor(model).extract(chunk("Maria"))


def test_gliner_load_requires_pinned_backbone_instead_of_sdk_fallback(tmp_path, monkeypatch):
    checkpoint = tmp_path / "checkpoint"
    checkpoint.mkdir()
    (checkpoint / "gliner_config.json").write_text(json.dumps({"model_name": "mutable/backbone"}))
    calls = []
    monkeypatch.setitem(
        sys.modules,
        "huggingface_hub",
        SimpleNamespace(snapshot_download=lambda *args, **kwargs: str(checkpoint)),
    )
    monkeypatch.setitem(
        sys.modules,
        "gliner",
        SimpleNamespace(
            GLiNER=SimpleNamespace(from_pretrained=lambda *args, **kwargs: calls.append(args))
        ),
    )
    with pytest.raises(RuntimeError, match="separately pinned"):
        GlinerExtractor("test/model", "a" * 40)._load()
    assert calls == []


def test_gliner_load_fixes_tokenizer_and_encoder_to_same_snapshot(tmp_path, monkeypatch):
    checkpoint, backbone = tmp_path / "checkpoint", tmp_path / "backbone"
    checkpoint.mkdir()
    backbone.mkdir()
    (checkpoint / "gliner_config.json").write_text(json.dumps({"model_name": "mutable/backbone"}))
    (checkpoint / "model.safetensors").write_bytes(b"fake weights")
    # Explicit secondary snapshot must replace even a conflicting tokenizer
    # bundled in the model repository, keeping config and tokenizer together.
    (checkpoint / "tokenizer_config.json").write_text('{"conflicting":true}')
    (backbone / "config.json").write_text(
        json.dumps({"model_type": "deberta-v2", "max_position_embeddings": 512})
    )
    (backbone / "tokenizer_config.json").write_text("{}")
    (backbone / "spm.model").write_bytes(b"fake tokenizer")
    downloads = []

    def snapshot(model_id, **kwargs):
        downloads.append((model_id, kwargs))
        return str(checkpoint if model_id == "test/model" else backbone)

    model = FakeModel()
    model.eval = lambda: None

    def load(directory, **kwargs):
        directory = Path(directory)
        config = json.loads((directory / "gliner_config.json").read_text())
        assert config["model_name"] == str(backbone)
        assert config["encoder_config"]["max_position_embeddings"] == 512
        assert (directory / "tokenizer_config.json").resolve() == backbone / "tokenizer_config.json"
        assert (directory / "config.json").resolve() == backbone / "config.json"
        assert kwargs == {"local_files_only": True}
        return model

    monkeypatch.setitem(sys.modules, "huggingface_hub", SimpleNamespace(snapshot_download=snapshot))
    monkeypatch.setitem(
        sys.modules, "gliner", SimpleNamespace(GLiNER=SimpleNamespace(from_pretrained=load))
    )
    assert (
        GlinerExtractor(
            "test/model", "a" * 40, tokenizer_id="test/backbone", tokenizer_revision="b" * 40
        )._load()
        is model
    )
    assert all(
        kwargs["revision"] == ("a" * 40 if model_id == "test/model" else "b" * 40)
        for model_id, kwargs in downloads
    )
    assert all(
        "model.safetensors" not in kwargs["allow_patterns"]
        for model_id, kwargs in downloads
        if model_id == "test/backbone"
    )

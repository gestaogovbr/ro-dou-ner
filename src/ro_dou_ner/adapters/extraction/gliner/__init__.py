"""Lazy GLiNER adapter with explicit input budgets and checked local offsets.

Input preflight follows inspected GLiNER 0.2.29's word splitter and uni-encoder prompt
construction. Both config.max_len and transformer subword budgets are checked;
an unsupported processor fails before inference instead of risking truncation.
"""

import json
import math
import re
import tempfile
import warnings
from pathlib import Path
from typing import Any

from ro_dou_ner.domain.mentions import MentionCandidate, validate_mention
from ro_dou_ner.domain.publications import TextChunk


class GlinerExtractor:
    version = "gliner-budget-checked-v1"
    extractor = "gliner"
    labels = {"person": "PERSON", "organization": "ORGANIZATION", "location": "LOCATION"}

    def __init__(
        self,
        model_id: str,
        revision: str,
        threshold: float = 0.5,
        model: Any = None,
        overlap_words: int = 20,
        tokenizer_id: str | None = None,
        tokenizer_revision: str | None = None,
    ):
        if (
            not isinstance(model_id, str)
            or not re.fullmatch(r"[\w.-]+/[\w.-]+", model_id)
            or Path(model_id).exists()
            or not isinstance(revision, str)
            or not re.fullmatch(r"[0-9a-fA-F]{40}", revision)
        ):
            raise ValueError(
                "GLiNER requires a model_id and a pinned 40-character commit SHA revision"
            )
        if (
            isinstance(threshold, bool)
            or not isinstance(threshold, (int, float))
            or not math.isfinite(threshold)
            or not 0 <= threshold <= 1
        ):
            raise ValueError("threshold must be finite and between zero and one")
        if type(overlap_words) is not int or overlap_words < 0:
            raise ValueError("overlap_words must be a nonnegative integer")
        if tokenizer_id is not None or tokenizer_revision is not None:
            if (
                not isinstance(tokenizer_id, str)
                or not re.fullmatch(r"[\w.-]+/[\w.-]+", tokenizer_id)
                or Path(tokenizer_id).exists()
                or not isinstance(tokenizer_revision, str)
                or not re.fullmatch(r"[0-9a-fA-F]{40}", tokenizer_revision)
            ):
                raise ValueError("A separate tokenizer requires a Hub ID and immutable commit SHA")
        self.model_id = model_id
        self.revision = revision
        self.threshold = threshold
        self.overlap_words = overlap_words
        self.tokenizer_id = tokenizer_id
        self.tokenizer_revision = tokenizer_revision
        self._injected_model = model is not None
        self._model = model

    def _load(self):
        if self._model is None:
            try:
                from huggingface_hub import snapshot_download

                from gliner import GLiNER
            except ImportError as error:
                raise RuntimeError(
                    "Install the gliner optional dependency to run model extraction"
                ) from error
            patterns = [
                "gliner_config.json",
                "tokenizer*.json",
                "special_tokens_map.json",
                "*.model",
                "vocab.*",
                "merges.txt",
                "added_tokens.json",
            ]
            checkpoint = Path(
                snapshot_download(self.model_id, revision=self.revision, allow_patterns=patterns)
            )
            config = json.loads((checkpoint / "gliner_config.json").read_text())
            backbone = None
            if self.tokenizer_id is not None:
                backbone = Path(
                    snapshot_download(
                        self.tokenizer_id,
                        revision=self.tokenizer_revision,
                        allow_patterns=["config.json", *patterns],
                    )
                )
                if (
                    not (backbone / "config.json").is_file()
                    or not (backbone / "tokenizer_config.json").is_file()
                ):
                    raise RuntimeError("Pinned backbone snapshot lacks configuration or tokenizer")
                config["model_name"] = str(backbone)
                config["encoder_config"] = json.loads((backbone / "config.json").read_text())
            elif not (checkpoint / "tokenizer_config.json").is_file() or not config.get(
                "encoder_config"
            ):
                raise RuntimeError(
                    "Checkpoint needs a separately pinned tokenizer_id/tokenizer_revision; unpinned backbone fallback is forbidden"
                )
            checkpoint = Path(
                snapshot_download(
                    self.model_id,
                    revision=self.revision,
                    allow_patterns=[*patterns, "model.safetensors"],
                )
            )
            if not (checkpoint / "model.safetensors").is_file():
                raise RuntimeError("Checkpoint must provide model.safetensors")
            # Local snapshot references fix all downloaded artifacts; local-only loading
            # forbids the SDK's fallback to an unversioned remote backbone/config.
            with tempfile.TemporaryDirectory(prefix="ro-dou-ner-gliner-") as temporary:
                directory = Path(temporary)
                for source in checkpoint.iterdir():
                    if (
                        source.name != "gliner_config.json"
                        and source.is_file()
                        and (backbone is None or source.name == "model.safetensors")
                    ):
                        (directory / source.name).symlink_to(source)
                if backbone is not None:
                    for source in backbone.iterdir():
                        if source.is_file() and not (directory / source.name).exists():
                            (directory / source.name).symlink_to(source)
                (directory / "gliner_config.json").write_text(json.dumps(config))
                self._model = GLiNER.from_pretrained(str(directory), local_files_only=True)
            self._model.eval()
        return self._model

    def _windows(self, model, text: str):
        processor = getattr(model, "data_processor", None)
        word_limit = getattr(getattr(model, "config", None), "max_len", None)
        splitter = getattr(processor, "words_splitter", None)
        tokenizer = getattr(processor, "transformer_tokenizer", None)
        prepare_inputs = getattr(processor, "prepare_inputs", None)
        token_limit = getattr(tokenizer, "model_max_length", None)
        encoder = getattr(
            getattr(
                getattr(getattr(model, "model", None), "token_rep_layer", None), "bert_layer", None
            ),
            "model",
            None,
        )
        encoder_limit = getattr(getattr(encoder, "config", None), "max_position_embeddings", None)
        known_limits = [
            limit
            for limit in (token_limit, encoder_limit)
            if type(limit) is int and 1 < limit < 1_000_000
        ]
        token_limit = min(known_limits) if known_limits else None
        if type(word_limit) is not int or word_limit < 1 or not callable(splitter):
            raise RuntimeError(
                "Unsupported GLiNER word budget or splitter; cannot guarantee full input coverage"
            )
        if (
            "BiEncoder" in type(processor).__name__
            or (
                not self._injected_model
                and type(processor).__name__
                not in {"UniEncoderSpanProcessor", "UniEncoderTokenProcessor"}
            )
            or not callable(prepare_inputs)
            or not callable(tokenizer)
        ):
            raise RuntimeError("Only inspected uni-encoder GLiNER processors are supported")
        if type(token_limit) is not int or not 1 < token_limit < 1_000_000:
            raise RuntimeError("Unknown transformer input budget; cannot guarantee no truncation")
        tokens = list(splitter(text))
        previous_end = 0
        for item in tokens:
            if not isinstance(item, (list, tuple)) or len(item) != 3:
                raise RuntimeError("Unsupported GLiNER splitter output")
            surface, start, end = item
            if (
                type(start) is not int
                or type(end) is not int
                or not previous_end <= start < end <= len(text)
                or text[start:end] != surface
            ):
                raise RuntimeError("Invalid GLiNER splitter offsets")
            # Splitters must cover all non-whitespace content to avoid losing a tail.
            if text[previous_end:start].strip():
                raise RuntimeError("GLiNER splitter omitted non-whitespace input")
            previous_end = end
        if text[previous_end:].strip():
            raise RuntimeError("GLiNER splitter omitted non-whitespace input")
        if not tokens:
            return []

        def fits(start, end):
            words = [item[0] for item in tokens[start:end]]
            input_words, _ = prepare_inputs([words], list(self.labels))
            encoding = tokenizer(
                input_words,
                is_split_into_words=True,
                truncation=False,
                padding=False,
                add_special_tokens=True,
            )
            ids = encoding["input_ids"]
            if len(ids) != 1:
                raise RuntimeError("Unsupported GLiNER tokenizer batch encoding")
            return len(ids[0]) <= token_limit

        windows = []
        first = 0
        while first < len(tokens):
            low, high = first, min(first + word_limit, len(tokens))
            while low < high:
                middle = (low + high + 1) // 2
                if fits(first, middle):
                    low = middle
                else:
                    high = middle - 1
            last = low
            if last == first:
                raise RuntimeError("A single word exceeds the GLiNER transformer budget")
            start_char = 0 if first == 0 else tokens[first][1]
            end_char = len(text) if last == len(tokens) else tokens[last][1]
            windows.append((start_char, text[start_char:end_char]))
            if last == len(tokens):
                break
            overlap = min(self.overlap_words, max(0, (last - first) // 2))
            first = last - overlap
        return windows

    def extract(self, chunk: TextChunk) -> tuple[MentionCandidate, ...]:
        if not chunk.text.strip():
            return ()
        model = self._load()
        candidates = {}
        for offset, window in self._windows(model, chunk.text):
            with warnings.catch_warnings():
                warnings.filterwarnings("error", message=".*truncat.*", category=UserWarning)
                predictions = model.predict_entities(
                    window, list(self.labels), threshold=self.threshold
                )
            for prediction in predictions:
                try:
                    label = self.labels[prediction["label"]]
                    local = MentionCandidate(
                        label,
                        prediction["text"],
                        prediction["start"],
                        prediction["end"],
                        prediction["score"],
                        self.extractor,
                    )
                except (KeyError, TypeError) as error:
                    raise ValueError("Malformed GLiNER entity prediction") from error
                validate_mention(local, window, self.labels.values())
                if local.score is None:
                    raise ValueError("GLiNER entity prediction must include a numeric score")
                if local.score < self.threshold:
                    continue
                candidate = MentionCandidate(
                    label,
                    local.surface,
                    local.start + offset,
                    local.end + offset,
                    local.score,
                    self.extractor,
                )
                key = (label, candidate.start, candidate.end)
                previous = candidates.get(key)
                if previous is None or previous.score < candidate.score:
                    candidates[key] = candidate
        return tuple(
            sorted(candidates.values(), key=lambda item: (item.start, item.end, item.label))
        )

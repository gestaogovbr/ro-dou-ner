import math
from collections.abc import Iterable
from dataclasses import dataclass

from .publications import TextChunk


@dataclass(frozen=True)
class MentionCandidate:
    label: str
    surface: str
    start: int
    end: int
    score: float | None
    extractor: str


@dataclass(frozen=True)
class Mention:
    label: str
    surface: str
    start: int
    end: int
    score: float | None
    extractor: str


def validate_mention(
    mention: Mention | MentionCandidate, body_text: str, labels: Iterable[str] | None = None
) -> None:
    if type(mention.start) is not int or type(mention.end) is not int:
        raise ValueError("mention offsets must be integers")
    if not 0 <= mention.start < mention.end <= len(body_text):
        raise ValueError("mention offsets out of bounds")
    if mention.surface != body_text[mention.start : mention.end]:
        raise ValueError("mention surface does not match its offsets")
    if not isinstance(mention.label, str) or not mention.label:
        raise ValueError("mention label must be nonempty")
    if labels is not None and mention.label not in labels:
        raise ValueError("mention label is outside the taxonomy")
    if not isinstance(mention.extractor, str) or not mention.extractor:
        raise ValueError("mention extractor must be nonempty")
    if mention.score is not None:
        if isinstance(mention.score, bool) or not isinstance(mention.score, (int, float)):
            raise ValueError("mention score must be numeric")
        if not math.isfinite(mention.score) or not 0 <= mention.score <= 1:
            raise ValueError("mention score must be finite and between zero and one")


def globalize(candidate: MentionCandidate, chunk: TextChunk, labels: Iterable[str]) -> Mention:
    validate_mention(candidate, chunk.text, labels)
    return Mention(
        candidate.label,
        candidate.surface,
        candidate.start + chunk.start,
        candidate.end + chunk.start,
        candidate.score,
        candidate.extractor,
    )


def consolidate(
    mentions: Iterable[Mention],
    body_text: str,
    labels: Iterable[str],
    extractor_priority: tuple[str, ...] = ("rules", "gliner"),
) -> tuple[Mention, ...]:
    """Resolve identical spans/labels only; preserve nested and conflicting mentions.

    Scores choose a winner only within the same extractor. Across extractors,
    explicit priority then extractor name makes selection deterministic.
    """
    chosen: dict[tuple[str, int, int], Mention] = {}
    priorities = {name: index for index, name in enumerate(extractor_priority)}
    for mention in mentions:
        validate_mention(mention, body_text, labels)
        key = (mention.label, mention.start, mention.end)
        previous = chosen.get(key)
        if previous is None:
            chosen[key] = mention
        elif previous.extractor == mention.extractor:
            if (mention.score if mention.score is not None else -1) > (
                previous.score if previous.score is not None else -1
            ):
                chosen[key] = mention
        elif (priorities.get(mention.extractor, len(priorities)), mention.extractor) < (
            priorities.get(previous.extractor, len(priorities)),
            previous.extractor,
        ):
            chosen[key] = mention
    return tuple(
        sorted(chosen.values(), key=lambda item: (item.start, item.end, item.label, item.extractor))
    )

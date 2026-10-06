"""Conservative Brazilian publication patterns; scores are not probabilities."""

import re
from datetime import date

from ro_dou_ner.domain.mentions import MentionCandidate
from ro_dou_ner.domain.publications import TextChunk

_MONTHS = {
    name: number
    for number, name in enumerate(
        (
            "janeiro",
            "fevereiro",
            "março",
            "abril",
            "maio",
            "junho",
            "julho",
            "agosto",
            "setembro",
            "outubro",
            "novembro",
            "dezembro",
        ),
        1,
    )
}
_NUMERIC_DATE = re.compile(r"(?<![\w/.-])(\d{1,2})([/.-])(\d{1,2})\2(\d{4})(?!\w|[./-]\d)")
_WRITTEN_DATE = re.compile(
    r"(?<!\w)(\d{1,2})(?:º)?\s+de\s+(" + "|".join(_MONTHS) + r")\s+de\s+(\d{4})(?!\w)", re.I
)
_PROCESS = re.compile(
    r"(?<!\w)(?:\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}|\d{5}\.\d{6}/\d{4}-\d{2})(?!\w)"
)
_FORMATTED_ID = re.compile(
    r"(?<!\w)(?:\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}|\d{3}\.\d{3}\.\d{3}-\d{2})(?!\w)"
)
_CONTEXT_ID = re.compile(r"\b(CPF|CNPJ)\s*(?:n[º°o.]?\s*)?[:=]?\s*(\d{11}|\d{14})(?!\w)", re.I)
_MONEY = re.compile(r"(?<!\w)R\$\s*(?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d{2})?(?!\w|[.,]\d)")
_LEGAL = re.compile(
    r"\b(?:Lei(?:\s+Complementar)?|Decreto(?:-Lei)?|Portaria|Resolução|Instrução\s+Normativa)\s+(?:n(?:[.º°o]|úmero)*\s*)?\d+(?:\.\d{3})*(?:/\d{4})?(?!\w)",
    re.I,
)


def _valid_identifier(surface: str) -> bool:
    digits = [int(char) for char in surface if char.isdigit()]
    if len(digits) not in {11, 14} or len(set(digits)) == 1:
        return False
    if len(digits) == 11:
        for count in (9, 10):
            value = sum(digits[index] * (count + 1 - index) for index in range(count)) * 10 % 11
            if digits[count] != (0 if value == 10 else value):
                return False
    else:
        for count, weights in (
            (12, (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)),
            (13, (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)),
        ):
            remainder = sum(digits[index] * weight for index, weight in enumerate(weights)) % 11
            if digits[count] != (0 if remainder < 2 else 11 - remainder):
                return False
    return True


class RuleExtractor:
    version = "brazil-publication-rules-v1"
    extractor = "rules"

    def extract(self, chunk: TextChunk) -> tuple[MentionCandidate, ...]:
        text = chunk.text
        candidates: dict[tuple[str, int, int], MentionCandidate] = {}

        def add(label, start, end):
            candidates[label, start, end] = MentionCandidate(
                label, text[start:end], start, end, None, self.extractor
            )

        for label, pattern in (
            ("PROCESS_NUMBER", _PROCESS),
            ("MONEY", _MONEY),
            ("LEGAL_REFERENCE", _LEGAL),
        ):
            for match in pattern.finditer(text):
                add(label, *match.span())
        for pattern in (_FORMATTED_ID, _CONTEXT_ID):
            for match in pattern.finditer(text):
                group = 2 if pattern is _CONTEXT_ID else 0
                surface = match.group(group)
                if (
                    pattern is _CONTEXT_ID
                    and len(surface) != {"CPF": 11, "CNPJ": 14}[match.group(1).upper()]
                ):
                    continue
                if _valid_identifier(surface):
                    add("IDENTIFIER", *match.span(group))
        for pattern in (_NUMERIC_DATE, _WRITTEN_DATE):
            for match in pattern.finditer(text):
                if pattern is _NUMERIC_DATE:
                    day, month, year = int(match[1]), int(match[3]), int(match[4])
                else:
                    day, month, year = int(match[1]), _MONTHS[match[2].lower()], int(match[3])
                try:
                    date(year, month, day)
                except ValueError:
                    continue
                add("DATE", *match.span())
        return tuple(
            sorted(candidates.values(), key=lambda item: (item.start, item.end, item.label))
        )

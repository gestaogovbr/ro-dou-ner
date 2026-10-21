"""Versioned canonical text and lossless character windows."""

import re
import unicodedata
from html.parser import HTMLParser

from ro_dou_ner.domain.identity import source_revision
from ro_dou_ner.domain.publications import CanonicalDocument, Publication, TextChunk


class _PublicationHTMLParser(HTMLParser):
    BLOCKS = frozenset(
        {
            "p",
            "div",
            "br",
            "hr",
            "li",
            "ul",
            "ol",
            "table",
            "tr",
            "td",
            "th",
            "section",
            "article",
            "header",
            "footer",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "blockquote",
            "pre",
        }
    )

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.suppressed: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.suppressed.append(tag)
        elif not self.suppressed and tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if self.suppressed:
            if tag == self.suppressed[-1]:
                self.suppressed.pop()
        elif tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.suppressed:
            self.parts.append(data)


class HTMLTextPreparer:
    """Offsets address NFC text, with trimmed lines and one newline per boundary.

    The revision hashes the raw input and source metadata, before normalization.
    Inline markup does not add whitespace; structural tags add newline boundaries.
    """

    profile_version = "html-nfc-lines-v1"
    version = profile_version

    def prepare(self, publication: Publication) -> CanonicalDocument:
        parser = _PublicationHTMLParser()
        parser.feed(publication.body_text)
        parser.close()
        text = unicodedata.normalize("NFC", "".join(parser.parts))
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        lines = [re.sub(r"[^\S\n]+", " ", line).strip() for line in text.split("\n")]
        text = "\n".join(line for line in lines if line)
        return CanonicalDocument(
            publication.publication_id,
            text,
            source_revision(publication.body_text, publication.metadata),
            dict(publication.metadata),
        )


class OverlappingChunker:
    """Return exact slices with continuous coverage, including whitespace.

    Prefer an end boundary after whitespace when it leaves enough room to make
    forward progress. Oversized individual words use character boundaries.
    """

    profile_version = "character-overlap-v1"
    version = profile_version

    def __init__(self, max_chars: int = 700, overlap: int = 100):
        if type(max_chars) is not int or max_chars < 1:
            raise ValueError("max_chars must be a positive integer")
        if type(overlap) is not int or not 0 <= overlap < max_chars:
            raise ValueError("overlap must be an integer smaller than max_chars")
        self.max_chars = max_chars
        self.overlap = overlap

    def chunk(self, document: CanonicalDocument) -> tuple[TextChunk, ...]:
        text = document.body_text
        chunks = []
        start = 0
        while start < len(text):
            end = min(start + self.max_chars, len(text))
            if end < len(text):
                boundaries = [match.end() + start for match in re.finditer(r"\s+", text[start:end])]
                previous_end = chunks[-1].end if chunks else 0
                suitable = [
                    bound for bound in boundaries if bound > max(start + self.overlap, previous_end)
                ]
                if suitable:
                    end = suitable[-1]
            chunks.append(TextChunk(start, end, text[start:end]))
            if end == len(text):
                break
            next_start = end - self.overlap
            candidate_start = next_start
            while candidate_start > start + 1 and not text[candidate_start - 1].isspace():
                candidate_start -= 1
            if text[candidate_start - 1].isspace():
                next_start = candidate_start
            start = max(start + 1, next_start)
        return tuple(chunks)

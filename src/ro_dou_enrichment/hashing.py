"""Contrato de hashing compatível com o indexador do Ro-DOU."""

import hashlib
from typing import Optional

TEXT_HASH_FIELD = "texto_plain_hash"

def text_hash(text: Optional[str]) -> str:
    """SHA-256 do texto completo em UTF-8; None equivale a texto vazio."""
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()

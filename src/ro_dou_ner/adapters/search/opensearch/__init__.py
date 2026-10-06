"""Optional OpenSearch projection and exact entity lookup."""

from .projector import DEFAULT_INDEX, IncompatibleIndexMapping, OpenSearchProjector
from .reader import OpenSearchPublicationReader

__all__ = [
    "DEFAULT_INDEX",
    "IncompatibleIndexMapping",
    "OpenSearchProjector",
    "OpenSearchPublicationReader",
]

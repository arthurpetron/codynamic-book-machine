"""Canonical book object APIs."""

from .artifact_registry import ArtifactRegistry
from .repository import BookRepository
from .outline_service import OutlineService

__all__ = ["ArtifactRegistry", "BookRepository", "OutlineService"]

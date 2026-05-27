"""Canonical book object APIs."""

from .artifact_registry import ArtifactRegistry
from .app_state import BookAppState
from .authoring import (
    AuthoringLoop,
    CommunicationMemory,
    EditProposal,
    MediaRequestRegistry,
    ProposalStore,
    VerificationHistory,
)
from .importer import BookImporter, ImportResult
from .intake import BookIntakeService, IntakeQuestion, QUESTION_BANK
from .repository import BookRepository
from .outline_service import OutlineService
from .typesetting import (
    CompileResult,
    DesignSettingsService,
    DocumentStyle,
    DocumentStyleRegistry,
    LatexAssembler,
    LatexBuildService,
)

__all__ = [
    "ArtifactRegistry",
    "AuthoringLoop",
    "BookAppState",
    "CommunicationMemory",
    "BookImporter",
    "BookIntakeService",
    "BookRepository",
    "CompileResult",
    "DesignSettingsService",
    "DocumentStyle",
    "DocumentStyleRegistry",
    "EditProposal",
    "ImportResult",
    "IntakeQuestion",
    "LatexAssembler",
    "LatexBuildService",
    "MediaRequestRegistry",
    "OutlineService",
    "ProposalStore",
    "QUESTION_BANK",
    "VerificationHistory",
]

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
from .creative import ArtworkSpec, DiagramArtworkService, DiagramSpec
from .importer import BookImporter, ImportResult
from .intake import BookIntakeService, IntakeQuestion, QUESTION_BANK
from .knowledge_graph import GraphAnalysis, KnowledgeGraphAnalyzer
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
from .versioning import ChangeSet, ChangeSetManager

__all__ = [
    "ArtifactRegistry",
    "ArtworkSpec",
    "AuthoringLoop",
    "BookAppState",
    "CommunicationMemory",
    "ChangeSet",
    "ChangeSetManager",
    "BookImporter",
    "BookIntakeService",
    "BookRepository",
    "CompileResult",
    "DesignSettingsService",
    "DiagramArtworkService",
    "DiagramSpec",
    "DocumentStyle",
    "DocumentStyleRegistry",
    "EditProposal",
    "ImportResult",
    "IntakeQuestion",
    "GraphAnalysis",
    "KnowledgeGraphAnalyzer",
    "LatexAssembler",
    "LatexBuildService",
    "MediaRequestRegistry",
    "OutlineService",
    "ProposalStore",
    "QUESTION_BANK",
    "VerificationHistory",
]

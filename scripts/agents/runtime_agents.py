"""Concrete AgentController subclasses used by the Phase 2 runtime."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from scripts.agents.agent_controller import AgentController
from scripts.api import LLMProvider
from scripts.book.authoring import AuthoringLoop, EditProposal


class SectionAgent(AgentController):
    agent_kind = "section"

    def propose_section_draft(
        self,
        book_root: str | Path,
        section_id: str,
        content: str,
        rationale: str = "Draft section payload.",
        mode: str = "proposal",
    ) -> EditProposal:
        return AuthoringLoop(book_root, mode=mode).propose_section_draft(
            section_id=section_id,
            content=content,
            agent_id=self.agent_id,
            rationale=rationale,
        )


class OutlineAgentController(AgentController):
    agent_kind = "outline"


class GardenerAgent(AgentController):
    agent_kind = "gardener"

    def record_section_check(
        self,
        book_root: str | Path,
        section_id: str,
        checks: dict[str, str],
        rationale: str = "",
    ) -> dict:
        loop = AuthoringLoop(book_root)
        return loop.history.record_check(
            agent_id=self.agent_id,
            subject=section_id,
            checks=checks,
            rationale=rationale,
        )


class DocumentDesignAgent(AgentController):
    agent_kind = "document_design"

    def record_design_review(
        self,
        book_root: str | Path,
        subject: str,
        status: str,
        rationale: str,
        metadata: dict | None = None,
    ) -> dict:
        return AuthoringLoop(book_root).history.record_event(
            event_type="document_design_review",
            agent_id=self.agent_id,
            subject=subject,
            status=status,
            rationale=rationale,
            metadata=metadata,
        )


class DiagramAgent(AgentController):
    agent_kind = "diagram"

    def fulfill_media_request(
        self,
        book_root: str | Path,
        request_id: str,
        content: str,
        extension: str = ".tikz",
    ) -> dict:
        return AuthoringLoop(book_root).media.fulfill_request(
            request_id=request_id,
            diagram_agent=self.agent_id,
            content=content,
            extension=extension,
        )


class HypervisorAgentController(AgentController):
    agent_kind = "hypervisor"

    def record_global_drift(
        self,
        book_root: str | Path,
        subject: str,
        status: str,
        rationale: str,
        metadata: dict | None = None,
    ) -> dict:
        return AuthoringLoop(book_root).record_hypervisor_drift(
            subject=subject,
            status=status,
            rationale=rationale,
            metadata=metadata,
        )


AGENT_CLASS_BY_DEFINITION = {
    "section_agent": SectionAgent,
    "outline_agent": OutlineAgentController,
    "gardener_agent": GardenerAgent,
    "document_designer_agent": DocumentDesignAgent,
    "diagram_agent": DiagramAgent,
    "hypervisor_agent": HypervisorAgentController,
}


def controller_for_definition(
    agent_yaml_path: str | Path,
    agent_id: str,
    provider: Optional[LLMProvider] = None,
    provider_name: str = "openai",
    data_root: Optional[Path] = None,
) -> AgentController:
    """Instantiate the correct controller subclass for an agent definition."""
    from yaml import safe_load

    with open(agent_yaml_path, "r") as f:
        agent_def = safe_load(f)
    controller_class = AGENT_CLASS_BY_DEFINITION.get(agent_def.get("name"), AgentController)
    return controller_class(
        agent_yaml_path=str(agent_yaml_path),
        agent_id=agent_id,
        provider=provider,
        provider_name=provider_name,
        data_root=data_root,
    )

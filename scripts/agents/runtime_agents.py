"""Concrete AgentController subclasses used by the Phase 2 runtime."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from scripts.agents.agent_controller import AgentController
from scripts.api import LLMProvider


class SectionAgent(AgentController):
    agent_kind = "section"


class OutlineAgentController(AgentController):
    agent_kind = "outline"


class GardenerAgent(AgentController):
    agent_kind = "gardener"


class DocumentDesignAgent(AgentController):
    agent_kind = "document_design"


class DiagramAgent(AgentController):
    agent_kind = "diagram"


class HypervisorAgentController(AgentController):
    agent_kind = "hypervisor"


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

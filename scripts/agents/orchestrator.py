"""Agent runtime orchestrator."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from scripts.agents.lifecycle import AgentLifecycleState
from scripts.agents.runtime_agents import controller_for_definition
from scripts.messaging.message_router import MessageRouter
from scripts.utils.project_paths import get_cached_project_structure


@dataclass
class AgentRuntime:
    agent_id: str
    controller: object
    thread: threading.Thread | None = None


class AgentOrchestrator:
    """Launch, monitor, pause, resume, and stop runtime agents."""

    def __init__(
        self,
        definitions_dir: Optional[Path] = None,
        data_root: Optional[Path] = None,
        router: Optional[MessageRouter] = None,
    ):
        project = get_cached_project_structure()
        self.definitions_dir = Path(definitions_dir) if definitions_dir else project.scripts_dir / "agents" / "agent_definitions"
        self.data_root = Path(data_root) if data_root else project.data_dir
        self.router = router or MessageRouter(log_dir=self.data_root / "message_log")
        self.runtimes: dict[str, AgentRuntime] = {}

    def launch_from_yaml(self, yaml_path: Path, agent_id: str | None = None, start_thread: bool = False):
        """Create an agent from a YAML definition and move it to INIT."""
        yaml_path = Path(yaml_path)
        agent_id = agent_id or yaml_path.stem
        controller = controller_for_definition(
            yaml_path,
            agent_id=agent_id,
            data_root=self.data_root,
        )
        controller.message_router = self.router
        self._register_runtime_callbacks(controller)

        runtime = AgentRuntime(agent_id=agent_id, controller=controller)
        self.runtimes[agent_id] = runtime

        if start_thread:
            runtime.thread = threading.Thread(target=controller.loop, daemon=True)
            runtime.thread.start()

        return controller

    def launch_all(self, start_threads: bool = False) -> dict[str, object]:
        """Launch all agent definition YAML files in the definitions directory."""
        controllers = {}
        for path in sorted(self.definitions_dir.glob("*_agent.yaml")):
            controller = self.launch_from_yaml(path, start_thread=start_threads)
            controllers[controller.agent_id] = controller
        return controllers

    def _register_runtime_callbacks(self, controller):
        """Attach callbacks based on durable subscription config."""
        for subscriber_id, info in self.router.subscription_map.items():
            if subscriber_id != controller.agent_id:
                continue
            for target in info.get("listens_to", []):
                self.router.subscribe(subscriber_id, target, controller.receive_message)

    def health_checks(self) -> dict[str, dict]:
        """Return current health for every launched agent."""
        return {
            agent_id: runtime.controller.get_stats()
            for agent_id, runtime in self.runtimes.items()
        }

    def pause(self, agent_id: str):
        return self.runtimes[agent_id].controller.pause()

    def resume(self, agent_id: str, target_state: AgentLifecycleState | str = AgentLifecycleState.PRE_OPERATIONAL):
        return self.runtimes[agent_id].controller.resume(target_state)

    def sleep(self, agent_id: str):
        return self.runtimes[agent_id].controller.sleep()

    def shutdown(self, agent_id: str):
        runtime = self.runtimes[agent_id]
        runtime.controller.stop()
        return runtime.controller.transition_to(AgentLifecycleState.INIT, reason="orchestrator shutdown")

    def shutdown_all(self):
        for agent_id in list(self.runtimes.keys()):
            self.shutdown(agent_id)

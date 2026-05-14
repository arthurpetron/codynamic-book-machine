"""
Agents Package - Multi-Agent Orchestration System

Provides agent controllers and specialized implementations for
the Codynamic Book Machine.

Usage:
    from scripts.agents import AgentController, launch_agent_thread
    
    # Create agent
    controller = AgentController(
        agent_yaml_path="path/to/agent.yaml",
        agent_id="agent_001"
    )
    
    # Add tasks
    controller.add_task("action_id", {"context": "data"})
    
    # Execute
    controller.run_next_task()
    
    # Or launch in thread
    controller, thread = launch_agent_thread(
        agent_yaml_path="path/to/agent.yaml",
        agent_id="agent_001"
    )
"""

from .agent_controller import (
    AgentController,
    launch_agent_thread
)

__all__ = [
    "AgentController",
    "launch_agent_thread"
]

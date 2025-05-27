# runner.py

import os
import yaml
from pathlib import Path
from scripts.agents.agent_controller import launch_agent_thread

AGENT_DEF_DIR = Path("scripts/agents/agent_definitions")
OUTLINE_PATH = Path("data/outline.yaml")
DEFAULT_AGENTS = ["hypervisor_agent", "message_router"]


def load_required_agents_from_outline(outline_path):
    if not outline_path.exists():
        print(f"[Runner] Outline not found at {outline_path}")
        return []

    with open(outline_path) as f:
        outline = yaml.safe_load(f)

    required = set(DEFAULT_AGENTS)
    # Extract referenced agents from outline
    if "sections" in outline:
        for section in outline["sections"]:
            if "agent" in section:
                required.add(section["agent"])

    return list(required)


def main():
    required_agents = load_required_agents_from_outline(OUTLINE_PATH)
    print(f"[Runner] Required agents: {required_agents}")

    for yaml_file in AGENT_DEF_DIR.glob("*.yaml"):
        agent_name = yaml_file.stem
        if agent_name in required_agents:
            print(f"[Runner] Launching {agent_name}")
            launch_agent_thread(agent_yaml_path=str(yaml_file), agent_id=agent_name)


if __name__ == "__main__":
    main()

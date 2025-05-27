# scripts/agents/section_agent.py

import yaml
from pathlib import Path
from datetime import datetime
from scripts.prompts.prompt_generator import generate_prompt_bundle

class SectionAgent:
    def __init__(self, agent_yaml_path, agent_id):
        super().__init__(agent_yaml_path, agent_id)
        self.agent_yaml_path = Path(agent_yaml_path)
        self.prompt_bundle = generate_prompt_bundle(agent_yaml_path, context_dict={})
        self.log_path = Path("logs/section_agent_log.yaml")
        self.output_dir = Path("tex/sections")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def log(self, entry):
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        if self.log_path.exists():
            with open(self.log_path) as f:
                log = yaml.safe_load(f) or []
        else:
            log = []
        log.append({"timestamp": datetime.now().isoformat(), "entry": entry})
        with open(self.log_path, "w") as f:
            yaml.dump(log, f)

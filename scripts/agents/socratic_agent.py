# scripts/agents/socratic_agent.py

import yaml
from pathlib import Path
from datetime import datetime
from scripts.prompts.prompt_generator import generate_prompt_bundle
from scripts.api.openai_hook import call_openai

class SocraticAgent:
    def __init__(self, agent_yaml_path):
        self.agent_yaml_path = Path(agent_yaml_path)
        self.prompt_bundle = generate_prompt_bundle(agent_yaml_path, context_dict={})
        self.responses = []
        self.log_path = Path("logs/socratic_agent_log.yaml")
        self.outline_path = Path("data/outline.yaml")

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

    def conduct_dialogue(self):
        prompt = self.prompt_bundle["actions"]["conduct_initial_dialogue"]
        print("[Socratic Agent] Starting conversation...")
        print("""(You can end the conversation at any time by typing 'done')\n""")
        while True:
            response = input("User: ")
            if response.strip().lower() == "done":
                break
            self.responses.append(response)
            self.log({"user_response": response})

    def synthesize_outline(self):
        joined = "\n".join(self.responses)
        prompt = self.prompt_bundle["actions"]["synthesize_outline_from_responses"].format(user_responses=joined)
        result = call_openai(prompt)
        try:
            parsed = yaml.safe_load(result)
            with open(self.outline_path, "w") as f:
                yaml.dump(parsed, f)
            self.log({"outline_created": str(self.outline_path)})
            print(f"[Socratic Agent] Outline saved to {self.outline_path}")
        except Exception as e:
            self.log({"error": str(e), "raw": result})
            print("[Socratic Agent] Failed to write outline. See log for details.")

    def run(self):
        self.conduct_dialogue()
        self.synthesize_outline()

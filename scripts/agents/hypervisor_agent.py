# scripts/agents/hypervisor_agent.py

import yaml
from pathlib import Path
from datetime import datetime
from scripts.prompts.prompt_generator import generate_prompt_bundle
from scripts.api.openai_hook import call_openai

class HypervisorAgent:
    def __init__(self, agent_yaml_path):
        self.agent_yaml_path = Path(agent_yaml_path)
        self.prompt_bundle = generate_prompt_bundle(agent_yaml_path, context_dict={})
        self.log_path = Path("logs/hypervisor_log.yaml")
        self.task_state = {}
        self.recent_messages = []

    def load_agent_state(self, agent_id):
        task_path = Path(f"agents/{agent_id}/task_queue.yaml")
        if task_path.exists():
            with open(task_path) as f:
                self.task_state[agent_id] = yaml.safe_load(f)

    def log(self, entry):
        log_entry = {"timestamp": datetime.now().isoformat(), "entry": entry}
        self.log_path.parent.mkdir(exist_ok=True, parents=True)
        if self.log_path.exists():
            with open(self.log_path) as f:
                current = yaml.safe_load(f) or []
        else:
            current = []
        current.append(log_entry)
        with open(self.log_path, "w") as f:
            yaml.dump(current, f)

    def process_message(self, message_dict):
        self.recent_messages.append(message_dict)
        if len(self.recent_messages) > 100:
            self.recent_messages.pop(0)
        agent_id = message_dict.get("to")
        self.load_agent_state(agent_id)
        self.check_agent_status(agent_id)

    def check_agent_status(self, agent_id):
        task_summary = self.task_state.get(agent_id, {}).get("summary", "[no tasks found]")
        message_summary = "\n".join([
            f"{m['subject']} → {m['body'][:100]}…" for m in self.recent_messages if m["to"] == agent_id
        ])

        prompt = self.prompt_bundle["actions"]["evaluate_and_respond_to_agent"].format(
            agent_id=agent_id,
            task_summary=task_summary,
            message_summary=message_summary
        )
        response = call_openai(prompt)

        if "subject:" in response and "to:" in response:
            try:
                parsed = yaml.safe_load(response)
                from scripts.messaging.message_router import MessageRouter
                MessageRouter().publish(parsed)
                self.log({"type": "intervention", "agent": agent_id, "message": parsed})
            except Exception as e:
                self.log({"type": "error", "agent": agent_id, "error": str(e), "raw": response})
        else:
            self.log({"type": "observation", "agent": agent_id, "note": response})

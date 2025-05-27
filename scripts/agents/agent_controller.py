# scripts/agents/agent_controller.py

import threading
import time
import json
import yaml
from pathlib import Path
from datetime import datetime

from scripts.prompts.prompt_generator import generate_prompt_bundle, bootstrap_agent_prompt, compose_system_prompt
from scripts.api.openai_hook import call_openai
from scripts.messaging.message_router import MessageRouter


class AgentController:
    def __init__(self, agent_yaml_path, agent_id):
        self.agent_id = agent_id
        self.yaml_path = Path(agent_yaml_path)
        self.bootstrap_context = bootstrap_agent_prompt(agent_id)
        with open(f"agents/{agent_id}/bootstrap_context.json", "w") as f:
            json.dump(self.bootstrap_context, f, indent=2)
        self.prompt_bundle = generate_prompt_bundle(agent_yaml_path, context_dict={})
        self.full_system_prompt = compose_system_prompt(
            agent_id=agent_id,
            agent_name=self.prompt_bundle["agent_name"],
            intro_prompt=self.prompt_bundle["intro_prompt"],
            actions=self.prompt_bundle["actions"],
            introspect_actions=self.prompt_bundle["introspect"]
        )
        self.task_queue = self.load_task_queue()
        self.message_inbox = []
        self.router = MessageRouter()
        self.router.subscribe(agent_id, agent_id, self.receive_message)
        self.load_log_state()

    def load_task_queue(self):
        path = Path(f"agents/{self.agent_id}/task_queue.yaml")
        if not path.exists():
            return []
        with open(path, "r") as f:
            return yaml.safe_load(f) or []

    def load_log_state(self):
        path = Path(f"agents/{self.agent_id}/action_log.yaml")
        if not path.exists():
            return
        with open(path, "r") as f:
            log = yaml.safe_load(f) or []
        # Optional: Replay specific tasks (e.g., introspection triggers)
        for entry in log:
            if entry.get("action_id") == "evaluate_self_recent_activity":
                self.task_queue.append({
                    "action_id": "evaluate_self_recent_activity",
                    "context": {
                        "agent_id": self.agent_id
                    }
                })

    def receive_message(self, msg):
        self.message_inbox.append(msg)

    def call_llm(self, action_id, context):
        prompt_body = self.prompt_bundle["actions"][action_id].format(**context)
        full_prompt = f"{self.system_prompt}\n\n### Task: {action_id}\n{prompt_body}"
        return call_openai(full_prompt)

    def loop(self):
        while True:
            if self.message_inbox:
                self.process_message(self.message_inbox.pop(0))
            elif self.task_queue:
                self.run_next_task()
            else:
                self.task_queue.append({
                    "action_id": "optional_instrospect",
                    "context": {
                        "agent_id": self.agent_id,
                        "agent_name": self.prompt_bundle["agent_name"],
                        "prompt_preamble": self.prompt_bundle["intro_prompt"],
                        "prompt_body": """
                            You have some free cycles and no tasks in your queue.
                            Please introspect your current state and the tasks you can perform.
                            Analyze your conversation, task, and action history.
                            Choose from the introspect actions, `introspect_actions`, to improve your context of your current state.
                            Think carefully about what you can do next.
                            Add any new tasks to your queue.
                            If you have no tasks, consider introspecting your capabilities.
                            Otherwise, wait for new messages or tasks.
                        """,
                        "introspect_actions": self.prompt_bundle["introspect"]
                    }
                })
            time.sleep(0.5)

    def run_next_task(self):
        task = self.task_queue.pop(0)
        action_id = task.get("action_id")
        context = task.get("context", {})
        result = self.call_llm(action_id, context)
        self.log_action(action_id, result)

    def process_message(self, msg):
        print(f"[{self.agent_id}] Processing message: {msg['subject']}")
        # If message includes an action directive, add to task queue
        if "body" in msg and msg["body"].strip().startswith("action_id:"):
            try:
                payload = yaml.safe_load(msg["body"])
                self.task_queue.append(payload)
                self.log_action("message_appended_task", payload)
                print(f"[{self.agent_id}] Task added from message: {payload['action_id']}")
            except Exception as e:
                print(f"[{self.agent_id}] Failed to parse message task: {e}")
        else:
            self.log_action("message_received", msg["body"])

    def log_action(self, action_id, result):
        log_path = Path(f"agents/{self.agent_id}/action_log.yaml")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log = []
        if log_path.exists():
            with open(log_path) as f:
                log = yaml.safe_load(f) or []
        log.append({
            "timestamp": datetime.now().isoformat(),
            "action_id": action_id,
            "result": result
        })
        with open(log_path, "w") as f:
            yaml.dump(log, f)


# Example launcher for threading mode
def launch_agent_thread(agent_yaml_path, agent_id):
    controller = AgentController(agent_yaml_path, agent_id)
    thread = threading.Thread(target=controller.loop)
    thread.start()
    return controller, thread

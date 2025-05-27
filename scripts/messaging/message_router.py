# scripts/messaging/message_router.py

import yaml
import os
import jsonschema
from datetime import datetime
from pathlib import Path
from typing import Callable
SUBSCRIPTION_PATH = "scripts/messaging/agent_subscriptions.yaml"
SCHEMA_PATH = "scripts/messaging/message_schema.yaml"
MESSAGE_LOG_PATH = "message_log"

# --- Schema loading and validation ---
def load_schema(schema_path):
    with open(schema_path, "r") as f:
        return yaml.safe_load(f)

def validate_with_schema(message_dict, schema):
    try:
        jsonschema.validate(instance=message_dict, schema=schema)
        return True, None
    except jsonschema.ValidationError as ve:
        return False, ve

def load_subscriptions(sub_path):
    with open(sub_path, "r") as f:
        return yaml.safe_load(f).get("subscriptions", {})
    
class MessageRouter:
    def __init__(self, schema_path=SCHEMA_PATH, log_dir=MESSAGE_LOG_PATH):
        self.subscribers: Dict[
            str,  # target_agent_id
            Dict[
                str,  # subscribing_agent_id
                Callable[[dict], None]  # specific callback for this pair
            ]
        ] = {}
        self.log_path = Path(log_dir)
        self.log_path.mkdir(parents=True, exist_ok=True)
        self.schema = load_schema(schema_path)

        # Auto-subscribe based on config (agents must register callbacks separately)
        self.subscription_map = load_subscriptions(SUBSCRIPTION_PATH)
        # Initialize empty subscriber lists for every agent mentioned
        for agent_id, info in self.subscription_map.items():
            for target in info.get("listens_to", []):
                self.subscribers.setdefault(target, {})

    def publish(self, message_dict):
        valid, err = validate_with_schema(message_dict, self.schema)
        if not valid:
            print(f"[Router] Validation failed: {err}")
            return False

        self._log_message(message_dict)

        # Deliver to subscriber(s)
        recipient = message_dict["to"]
        if not self.subscribers[recipient] and recipient != "all_agents":
            print(f"\n\n[Router] Warning: No callbacks registered for '{recipient}'\n"
                   "This message will not be delivered!\n\n")
        if recipient == "all_agents":
            for recipient in self.subscribers.keys():  # Broadcast to all agents
                for callback in self.subscribers[recipient].values():
                    callback(message_dict)
        elif recipient in self.subscribers:
            for subscriber_id, callback in self.subscribers[recipient].items():
                callback(message_dict)
        else:
            print(f"[Router] No subscribers for agent_id: {recipient}")
        return True

    def subscribe(self, agent_id: str, target_agent_id: str, callback: Callable[[dict], None]):
        self.subscribers.setdefault(target_agent_id, {})[agent_id] = callback
        callback.__agent_id__ = agent_id

        print(f"[Router] Agent '{agent_id}' subscribed to {target_agent_id}.")

        try:
            if os.path.exists(SUBSCRIPTION_PATH):
                with open(SUBSCRIPTION_PATH, "r") as f:
                    subs = yaml.safe_load(f) or {}
            else:
                subs = {}

            subs.setdefault("subscriptions", {}).setdefault(agent_id, {}).setdefault("listens_to", [])
            if target_agent_id not in subs["subscriptions"][agent_id]["listens_to"]:
                subs["subscriptions"][agent_id]["listens_to"].append(target_agent_id)
            
            # Log last update timestamp
            subs["subscriptions"][agent_id]["last_updated"] = datetime.now().isoformat()

            with open(SUBSCRIPTION_PATH, "w") as f:
                yaml.dump(subs, f)
            print(f"[Router] Subscription saved: {agent_id} -> {target_agent_id}")

        except Exception as e:
            print(f"[Router] Failed to write subscription: {e}")

    def unsubscribe(self, agent_id: str, target_agent_id: str, path=SUBSCRIPTION_PATH):
        try:
            if not os.path.exists(path):
                print(f"[Router] No subscription file to update.")
                return

            with open(path, "r") as f:
                subs = yaml.safe_load(f) or {}

            if not self.subscribers[target_agent_id]:
                print(f"[Router] '{target_agent_id}' has no more active listeners.")
                return
            
            # Remove subscription from the YAML
            if agent_id in subs.get("subscriptions", {}):
                listens = subs["subscriptions"][agent_id].get("listens_to", [])
                if target_agent_id in listens:
                    listens.remove(target_agent_id)
                    subs["subscriptions"][agent_id]["last_updated"] = datetime.now().isoformat()

                    with open(path, "w") as f:
                        yaml.dump(subs, f)

                    print(f"[Router] Unsubscribed {agent_id} from {target_agent_id} (YAML updated)")

            # Remove the callback from in-memory subscriber mapping
            if target_agent_id in self.subscribers:
                if agent_id in self.subscribers[target_agent_id]:
                    del self.subscribers[target_agent_id][agent_id]
                    print(f"[Router] Callback for {agent_id} removed from {target_agent_id}")
                    
                    if not self.subscribers[target_agent_id]:
                        print(f"[Router] '{target_agent_id}' has no more active listeners.")
                else:
                    print(f"[Router] No registered callback from {agent_id} to {target_agent_id}")

        except Exception as e:
            print(f"[Router] Failed to unsubscribe: {e}")

    def _log_message(self, msg_dict):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        log_file = self.log_path / f"{msg_dict['to']}_{timestamp}.yaml"
        with open(log_file, "w") as f:
            yaml.dump(msg_dict, f)
        print(f"[Router] Message logged to {log_file}")

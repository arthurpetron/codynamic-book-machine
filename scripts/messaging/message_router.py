# scripts/messaging/message_router.py

import yaml
import jsonschema
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, Any
from uuid import uuid4

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
        return (yaml.safe_load(f) or {}).get("subscriptions", {})

def load_communication_policy(sub_path):
    with open(sub_path, "r") as f:
        return (yaml.safe_load(f) or {}).get("communication", {})
    
class MessageRouter:
    def __init__(self, schema_path=SCHEMA_PATH, subscription_path=SUBSCRIPTION_PATH, log_dir=MESSAGE_LOG_PATH):
        self.subscribers: Dict[
            str,  # target_agent_id
            Dict[
                str,  # subscribing_agent_id
                Callable[[dict], None]  # specific callback for this pair
            ]
        ] = {}
        self.log_path = Path(log_dir)
        self.log_path.mkdir(parents=True, exist_ok=True)
        self.audit_path = self.log_path / "audit.yaml"
        self.chat_path = self.log_path / "chat.log"
        self.schema = load_schema(schema_path)
        self.subscription_path = subscription_path

        # Durable config only; callbacks register at runtime.
        self.subscription_map = load_subscriptions(subscription_path)
        self.communication_policy = load_communication_policy(subscription_path)
        # Initialize empty subscriber lists for every agent mentioned
        for agent_id, info in self.subscription_map.items():
            for target in info.get("listens_to", []):
                self.subscribers.setdefault(target, {})

    def publish(self, message_dict):
        message_dict = self._normalize_message(message_dict)
        valid, err = validate_with_schema(message_dict, self.schema)
        if not valid:
            print(f"[Router] Validation failed: {err}")
            self._audit(message_dict, "failed", str(err))
            return False

        allowed, reason = self._is_allowed(message_dict["from"], message_dict["to"])
        if not allowed:
            print(f"[Router] Message blocked by communication policy: {reason}")
            message_dict["status"] = "failed"
            self._log_message(message_dict)
            self._audit(message_dict, "failed", reason)
            return False

        self._log_message(message_dict)

        # Deliver to subscriber(s)
        recipient = message_dict["to"]
        delivered = 0
        if recipient != "all_agents" and not self.subscribers.get(recipient):
            print(f"\n\n[Router] Warning: No callbacks registered for '{recipient}'\n"
                   "This message will not be delivered!\n\n")
        if recipient == "all_agents":
            for recipient in self.subscribers.keys():  # Broadcast to all agents
                for callback in self.subscribers[recipient].values():
                    callback(message_dict)
                    delivered += 1
        elif recipient in self.subscribers:
            for subscriber_id, callback in self.subscribers[recipient].items():
                callback(message_dict)
                delivered += 1
        else:
            print(f"[Router] No subscribers for agent_id: {recipient}")
        message_dict["status"] = "delivered" if delivered else "queued"
        message_dict["delivered_at"] = datetime.now().isoformat() if delivered else None
        self._audit(message_dict, message_dict["status"], f"delivered_to={delivered}")
        return True

    def subscribe(self, agent_id: str, target_agent_id: str, callback: Callable[[dict], None]):
        self.subscribers.setdefault(target_agent_id, {})[agent_id] = callback
        try:
            callback.__agent_id__ = agent_id
        except AttributeError:
            pass

        print(f"[Router] Agent '{agent_id}' subscribed to {target_agent_id}.")

    def unsubscribe(self, agent_id: str, target_agent_id: str):
        try:
            if target_agent_id not in self.subscribers or not self.subscribers[target_agent_id]:
                print(f"[Router] '{target_agent_id}' has no more active listeners.")
                return

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
        log_file = self.log_path / f"{msg_dict['to']}_{timestamp}_{msg_dict['message_id']}.yaml"
        with open(log_file, "w") as f:
            yaml.dump(msg_dict, f)
        with open(self.chat_path, "a") as f:
            f.write(self.chat_line(msg_dict) + "\n")
        print(f"[Router] Message logged to {log_file}")

    @staticmethod
    def chat_line(msg_dict: Dict[str, Any]) -> str:
        body = str(msg_dict.get("body") or msg_dict.get("subject") or "").strip()
        message = " ".join(body.split())
        return f"{msg_dict.get('from', 'unknown')} --> {msg_dict.get('to', 'unknown')}: {message}"

    def _normalize_message(self, msg: Dict[str, Any]) -> Dict[str, Any]:
        message = dict(msg)
        message.setdefault("message_id", f"msg_{uuid4().hex}")
        message.setdefault("correlation_id", message["message_id"])
        message.setdefault("parent_message_id", None)
        message.setdefault("status", "queued")
        message.setdefault("created_at", datetime.now().isoformat())
        message.setdefault("delivered_at", None)
        message.setdefault("reply_to", message.get("from", "unknown"))
        return message

    def _is_allowed(self, sender: str, recipient: str) -> tuple[bool, str]:
        """
        Check configurable communication policy.

        Policy shape in agent_subscriptions.yaml:
          communication:
            default: allow|deny
            allow:
              sender_agent: [recipient_agent, all_agents]
            deny:
              sender_agent: [recipient_agent]
        """
        default = self.communication_policy.get("default", "allow")
        allow = self.communication_policy.get("allow", {}) or {}
        deny = self.communication_policy.get("deny", {}) or {}

        if self._matches_policy(deny, sender, recipient):
            return False, f"{sender} -> {recipient} denied"
        if self._matches_policy(allow, sender, recipient):
            return True, f"{sender} -> {recipient} explicitly allowed"
        if default == "deny":
            return False, f"{sender} -> {recipient} not explicitly allowed"
        return True, f"{sender} -> {recipient} allowed by default"

    def _matches_policy(self, policy: Dict[str, Any], sender: str, recipient: str) -> bool:
        targets = []
        for key in (sender, "*", "all_agents"):
            value = policy.get(key, [])
            if isinstance(value, str):
                value = [value]
            targets.extend(value)
        return recipient in targets or "*" in targets or "all_agents" in targets

    def _audit(self, msg: Dict[str, Any], status: str, detail: str = ""):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "message_id": msg.get("message_id"),
            "correlation_id": msg.get("correlation_id"),
            "from": msg.get("from"),
            "to": msg.get("to"),
            "status": status,
            "detail": detail,
        }
        log = []
        if self.audit_path.exists():
            with open(self.audit_path, "r") as f:
                log = yaml.safe_load(f) or []
        log.append(entry)
        with open(self.audit_path, "w") as f:
            yaml.safe_dump(log, f, sort_keys=False)

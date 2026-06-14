"""Tests for Phase 2 agent runtime lifecycle and messaging."""

from pathlib import Path

import pytest
import yaml

from scripts.agents import AgentLifecycleState, AgentOrchestrator
from scripts.agents.agent_controller import AgentController
from scripts.api import LLMResponse
from scripts.messaging.message_router import MessageRouter


class MockProvider:
    def get_provider_name(self):
        return "mock"

    def get_stats(self):
        return {"call_count": 0}

    def call(self, **kwargs):
        return LLMResponse(content="ok", model="mock", provider="mock")


def write_agent(path: Path, name: str = "section_agent"):
    path.write_text(yaml.safe_dump({
        "name": name,
        "role": "Test runtime agent",
        "actions": [
            {"id": "plan", "prompt_template": "Plan {target}"},
        ],
    }))


def test_lifecycle_blocks_api_until_pre_operational(tmp_path):
    yaml_path = tmp_path / "agent.yaml"
    write_agent(yaml_path)
    controller = AgentController(
        str(yaml_path),
        "agent_1",
        provider=MockProvider(),
        data_root=tmp_path / "data",
    )

    assert controller.lifecycle_state == AgentLifecycleState.INIT
    with pytest.raises(RuntimeError):
        controller.execute_action("plan", {"target": "outline"})

    controller.activate_pre_operational()
    assert controller.execute_action("plan", {"target": "outline"}).content == "ok"


def test_operational_state_can_advance_task_pointer(tmp_path):
    yaml_path = tmp_path / "agent.yaml"
    write_agent(yaml_path)
    controller = AgentController(
        str(yaml_path),
        "agent_2",
        provider=MockProvider(),
        data_root=tmp_path / "data",
    )
    controller.add_task("plan", {"target": "chapter"})

    controller.activate_pre_operational()
    with pytest.raises(RuntimeError):
        controller.run_next_task()

    controller.activate_safe_operational()
    controller.activate_operational()
    assert controller.run_next_task() is True
    assert controller.task_queue == []


def test_message_router_adds_ids_and_audit_without_mutating_config(tmp_path):
    schema_path = tmp_path / "message_schema.yaml"
    schema_path.write_text(Path("scripts/messaging/message_schema.yaml").read_text())
    subscription_path = tmp_path / "subs.yaml"
    subscription_path.write_text(yaml.safe_dump({
        "subscriptions": {
            "listener": {"listens_to": ["target"]},
        }
    }))
    router = MessageRouter(
        schema_path=schema_path,
        subscription_path=subscription_path,
        log_dir=tmp_path / "message_log",
    )
    delivered = []
    router.subscribe("listener", "target", delivered.append)

    assert router.publish({
        "subject": "Hello",
        "from": "sender",
        "to": "target",
        "reply_to": "sender",
        "body": "payload",
    })

    assert delivered[0]["message_id"].startswith("msg_")
    assert delivered[0]["correlation_id"] == delivered[0]["message_id"]
    assert (tmp_path / "message_log" / "audit.yaml").exists()
    assert (tmp_path / "message_log" / "chat.log").read_text().strip() == "sender --> target: payload"
    assert yaml.safe_load(subscription_path.read_text()) == {
        "subscriptions": {
            "listener": {"listens_to": ["target"]},
        }
    }


def test_message_router_enforces_configured_send_permissions(tmp_path):
    schema_path = tmp_path / "message_schema.yaml"
    schema_path.write_text(Path("scripts/messaging/message_schema.yaml").read_text())
    subscription_path = tmp_path / "subs.yaml"
    subscription_path.write_text(yaml.safe_dump({
        "subscriptions": {},
        "communication": {
            "default": "deny",
            "allow": {"outline_agent": ["gardener_agent"]},
            "deny": {},
        },
    }))
    router = MessageRouter(
        schema_path=schema_path,
        subscription_path=subscription_path,
        log_dir=tmp_path / "message_log",
    )

    assert router.publish({
        "subject": "Allowed",
        "from": "outline_agent",
        "to": "gardener_agent",
        "reply_to": "outline_agent",
        "body": "payload",
    })
    assert not router.publish({
        "subject": "Blocked",
        "from": "section_agent",
        "to": "gardener_agent",
        "reply_to": "section_agent",
        "body": "payload",
    })


def test_agent_prompt_includes_allowed_message_recipients(tmp_path):
    yaml_path = tmp_path / "agent.yaml"
    write_agent(yaml_path, "outline_agent")
    subscription_path = tmp_path / "subs.yaml"
    subscription_path.write_text(yaml.safe_dump({
        "subscriptions": {},
        "communication": {
            "default": "deny",
            "allow": {"outline_agent": ["gardener_agent", "hypervisor_agent"]},
            "deny": {},
        },
    }))
    controller = AgentController(
        str(yaml_path),
        "outline_agent",
        provider=MockProvider(),
        data_root=tmp_path / "data",
    )
    controller.message_router = MessageRouter(
        subscription_path=subscription_path,
        log_dir=tmp_path / "message_log",
    )

    prompt = controller._build_system_prompt()
    assert "configured outbound recipients are:" in prompt
    assert "- gardener_agent" in prompt
    assert "- hypervisor_agent" in prompt


def test_orchestrator_launches_runtime_subclasses_and_health(tmp_path):
    definitions = tmp_path / "defs"
    definitions.mkdir()
    write_agent(definitions / "section_agent.yaml", "section_agent")
    write_agent(definitions / "diagram_agent.yaml", "diagram_agent")

    orchestrator = AgentOrchestrator(
        definitions_dir=definitions,
        data_root=tmp_path / "data",
        router=MessageRouter(log_dir=tmp_path / "messages"),
    )
    controllers = orchestrator.launch_all(start_threads=False)
    health = orchestrator.health_checks()

    assert set(controllers) == {"section_agent", "diagram_agent"}
    assert controllers["section_agent"].__class__.__name__ == "SectionAgent"
    assert controllers["diagram_agent"].__class__.__name__ == "DiagramAgent"
    assert health["section_agent"]["state"] == "init"

    controllers["section_agent"].activate_pre_operational()
    orchestrator.pause("section_agent")
    assert health["section_agent"]["state"] == "init"
    assert orchestrator.health_checks()["section_agent"]["state"] == "init"

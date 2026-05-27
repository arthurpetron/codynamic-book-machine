"""Tests for agent-to-user chat queue support."""

from pathlib import Path

import pytest
import yaml

from scripts.agents.agent_controller import AgentController
from scripts.user_chat import UserChatQueue, agent_can_talk_to_user


def write_agent(path: Path, permissions=None):
    path.write_text(yaml.safe_dump({
        "name": "test_agent",
        "role": "Test agent",
        "permissions": permissions or [],
        "actions": [],
    }))


def test_user_chat_queue_add_answer_and_dismiss(tmp_path):
    queue = UserChatQueue(data_root=tmp_path)
    first = queue.add_request(
        from_agent="hypervisor_agent",
        subject="Choose next task",
        body="Which section should be reviewed next?",
    )
    second = queue.add_request(
        from_agent="socratic_agent",
        subject="Clarify audience",
        body="Who is the target reader?",
    )

    assert queue.counts()["pending"] == 2
    assert [message["message_id"] for message in queue.pending()] == [
        first["message_id"],
        second["message_id"],
    ]

    answered = queue.answer(first["message_id"], "Review section 2.1.")
    dismissed = queue.dismiss(second["message_id"])

    assert answered["status"] == "answered"
    assert answered["answer"] == "Review section 2.1."
    assert dismissed["status"] == "dismissed"
    assert queue.counts()["pending"] == 0


def test_agent_controller_queues_user_message_when_permission_allows(tmp_path):
    yaml_path = tmp_path / "agent.yaml"
    write_agent(yaml_path, permissions=["queue_user_messages"])
    controller = AgentController(
        str(yaml_path),
        "hypervisor_agent",
        data_root=tmp_path / "data",
    )
    controller.activate_pre_operational()
    controller.activate_safe_operational()

    message = controller.queue_user_message(
        "Need direction",
        "Should the system ask the outline agent or wait for the user?",
        metadata={"reason": "routing_exhausted"},
    )

    assert message["from_agent"] == "hypervisor_agent"
    assert message["status"] == "pending"
    assert UserChatQueue(data_root=tmp_path / "data").counts()["pending"] == 1


def test_agent_controller_blocks_user_message_without_permission(tmp_path):
    yaml_path = tmp_path / "agent.yaml"
    write_agent(yaml_path, permissions=["read_outline"])
    controller = AgentController(
        str(yaml_path),
        "outline_agent",
        data_root=tmp_path / "data",
    )
    controller.activate_pre_operational()
    controller.activate_safe_operational()

    assert not agent_can_talk_to_user(controller.agent_def)
    with pytest.raises(PermissionError):
        controller.queue_user_message("Blocked", "This should not reach the user.")


def test_agent_controller_blocks_user_message_before_communication_state(tmp_path):
    yaml_path = tmp_path / "agent.yaml"
    write_agent(yaml_path, permissions=["queue_user_messages"])
    controller = AgentController(
        str(yaml_path),
        "hypervisor_agent",
        data_root=tmp_path / "data",
    )

    with pytest.raises(RuntimeError):
        controller.queue_user_message("Too early", "Init agents cannot communicate yet.")

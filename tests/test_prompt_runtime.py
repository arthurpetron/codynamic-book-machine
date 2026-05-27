"""Tests for runtime prompt creation tools."""

from pathlib import Path

import pytest
import yaml

from scripts.agents.agent_controller import AgentController
from scripts.prompts.runtime import (
    PromptContextBuilder,
    PromptComposer,
    PromptPolicyValidator,
    PromptSnapshotStore,
)
from scripts.messaging.message_router import MessageRouter


class MockProvider:
    def get_provider_name(self):
        return "mock"

    def get_stats(self):
        return {"call_count": 0}


def write_agent(path: Path):
    path.write_text(yaml.safe_dump({
        "name": "outline_agent",
        "role": "Maintains canonical outline structure.",
        "tasks": ["Check outline completeness"],
        "permissions": ["read_outline", "send_messages"],
        "actions": [{"id": "inspect", "description": "Inspect outline", "prompt_template": "Inspect"}],
    }))


def configured_router(tmp_path):
    subscription_path = tmp_path / "subs.yaml"
    subscription_path.write_text(yaml.safe_dump({
        "subscriptions": {},
        "communication": {
            "default": "deny",
            "allow": {"outline_agent": ["gardener_agent"]},
            "deny": {},
        },
    }))
    return MessageRouter(subscription_path=subscription_path, log_dir=tmp_path / "messages")


def test_prompt_context_builder_collects_runtime_facts(tmp_path):
    yaml_path = tmp_path / "outline_agent.yaml"
    write_agent(yaml_path)
    controller = AgentController(
        str(yaml_path),
        "outline_agent",
        provider=MockProvider(),
        data_root=tmp_path / "data",
    )
    controller.message_router = configured_router(tmp_path)

    context = PromptContextBuilder().build(controller)

    assert context["agent_id"] == "outline_agent"
    assert context["lifecycle_state"] == "init"
    assert context["allowed_recipients"] == ["gardener_agent"]
    assert context["role_contract"]["actions"][0]["id"] == "inspect"
    assert "work_queue" in context


def test_prompt_composer_and_policy_validator_respect_state(tmp_path):
    yaml_path = tmp_path / "outline_agent.yaml"
    write_agent(yaml_path)
    controller = AgentController(
        str(yaml_path),
        "outline_agent",
        provider=MockProvider(),
        data_root=tmp_path / "data",
    )
    controller.message_router = configured_router(tmp_path)

    context = PromptContextBuilder().build(controller)
    prompt = PromptComposer().compose(context)
    valid, errors = PromptPolicyValidator().validate(prompt, context)

    assert valid, errors
    assert "When messaging is enabled" in prompt
    assert "- gardener_agent" in prompt


def test_prompt_validator_rejects_messaging_grant_in_init():
    context = {"lifecycle_state": "init", "allowed_recipients": ["gardener_agent"]}
    prompt = "Messaging policy:\nYou may send messages only to:\n- gardener_agent\n"

    valid, errors = PromptPolicyValidator().validate(prompt, context)

    assert not valid
    assert "grants messaging" in errors[0]


def test_prompt_snapshot_store_persists_exact_prompt(tmp_path):
    store = PromptSnapshotStore(tmp_path / "agent_state")
    snapshot = store.save(
        agent_id="outline_agent",
        action_id="inspect",
        prompt="system prompt",
        context={"lifecycle_state": "init"},
    )

    saved = yaml.safe_load((tmp_path / "agent_state" / "prompt_snapshots" / f"{snapshot.snapshot_id}.yaml").read_text())
    assert saved["prompt"] == "system prompt"
    assert saved["prompt_sha256"] == snapshot.prompt_sha256

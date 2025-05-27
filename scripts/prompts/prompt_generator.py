# scripts/prompts/prompt_generator.py

import yaml
from pathlib import Path
from typing import DefaultDict

INSTROSPECT_PATH = Path("scripts/prompts/introspect_sub_prompts.yaml")
AGENT_YAML_PATH = Path("scripts/agents/agent_definitions")

def load_yaml(path):
    with open(path, "r") as f:
        return yaml.safe_load(f)

def load_agent_spec(agent_yaml_path):
    return load_yaml(agent_yaml_path)

def load_introspect_prompts(introspect_path):
    return load_yaml(introspect_path)

def generate_prompt_bundle(agent_yaml_path=AGENT_YAML_PATH, context_dict={}, introspect_path=INSTROSPECT_PATH):
    agent_spec = load_agent_spec(agent_yaml_path)
    introspect_spec = load_introspect_prompts(introspect_path)

    role_intro = f"You are {agent_spec['name']}, {agent_spec['role']}"

    actions = {}
    for action in agent_spec.get("actions", []):
        action_id = action["id"]
        template = action["prompt_template"]
        prompt_filled = template.format_map(DefaultDict(str, context_dict))
        actions[action_id] = prompt_filled

    introspect_actions = {entry["id"]: entry["prompt"] for entry in introspect_spec.get("actions", [])}

    return {
        "agent_name": agent_spec["name"],
        "intro_prompt": role_intro,
        "actions": actions,
        "introspect": introspect_actions,
        "permissions": agent_spec.get("permissions", []),
        "tasks": agent_spec.get("tasks", []),
    }

def bootstrap_agent_prompt(current_agent_id):
    agents_path = Path("scripts/agents/agent_definitions")
    agent_summaries = []

    for path in agents_path.glob("*.yaml"):
        with open(path) as f:
            spec = yaml.safe_load(f)
        name = spec.get("name", path.stem)
        agent_id = path.stem
        role = spec.get("role", "[no description]")
        task_summaries = [t.get("description", "") for t in spec.get("tasks", [])]
        action_ids = [a.get("id") for a in spec.get("actions", [])]
        agent_summaries.append({
            "name": name,
            "agent_id": agent_id,
            "role": role,
            "tasks": task_summaries,
            "actions": action_ids
        })

    message_format = {
        "subject": "<brief summary>",
        "to": "<agent_id>",
        "reply_to": "<receiving_agent_id>",
        "body": "<multi-line message body>"
    }

    return {
        "preamble": f"You are the agent '{current_agent_id}', a participant in a greater, augmentic network responsible for collaboratively creating manuscripts, books, and written artifacts using LaTeX.",
        "message_format": message_format,
        "agent_directory": agent_summaries,
        "footer": (
            "Each agent maintains a task queue, performs introspective reflection, and coordinates actions based on its role and the evolving "
            "structure of the document. Messages can be used to propose, request, notify, or instruct — but must always be purposeful and aligned "
            "with the agent's designated responsibilities and specific intent within the system."
        )
    }

def compose_system_prompt(agent_id, bootstrap_context, prompt_bundle):
    agent_name = prompt_bundle.get("agent_name", agent_id)
    role_description = prompt_bundle.get("intro_prompt", "")
    tasks = prompt_bundle.get("tasks", [])
    permissions = prompt_bundle.get("permissions", [])
    actions = prompt_bundle.get("actions", {})
    introspect = prompt_bundle.get("introspect", {})

    message_format = yaml.dump(bootstrap_context["message_format"], sort_keys=False)
    agent_directory = json.dumps(bootstrap_context["agent_directory"], indent=2)

    prompt = f"""

You are **{agent_name}**, an autonomous agent participating in a greater, 
augmentic network responsible for collaboratively creating manuscripts, books, 
and written artifacts using LaTeX.

## Your Role
{role_description}

## Your Responsibilities
You are responsible for:
{chr(10).join(f"- {t['description']}" for t in tasks)}

## Your Permissions
You are allowed to:
{chr(10).join(f"- {p}" for p in permissions)}

## Your Available Actions
You may choose to perform any of the following actions:
{chr(10).join(f"- {a_id}" for a_id in actions)}

## Your Introspective Capabilities
You may also reflect using introspective actions like:
{chr(10).join(f"- {i_id}" for i_id in introspect)}

## Messaging Protocol
All inter-agent messages must follow this format:
{message_format}

## Other Agents in the System
Here is the current agent network:
{agent_directory}

## Operating Principle
You maintain a task queue and update it based on introspection or inter-agent messages.
Always act in accordance with your role and the broader goal of producing a coherent document.
"""

    return prompt

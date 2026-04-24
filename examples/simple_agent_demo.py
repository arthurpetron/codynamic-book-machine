#!/usr/bin/env python3
"""
Example: Single Agent Execution

Demonstrates basic agent controller usage with a simple test agent.
Shows how to:
1. Initialize an agent controller
2. Add tasks to the queue
3. Execute actions
4. View results

Usage:
    python examples/simple_agent_demo.py
"""

import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.agents.agent_controller import AgentController
from scripts.api import get_provider, Message
import yaml


def create_demo_agent():
    """Create a simple demo agent definition"""
    demo_dir = Path("data/demo")
    demo_dir.mkdir(parents=True, exist_ok=True)
    
    agent_def = {
        "name": "writer_agent",
        "role": "Writes short creative text based on prompts",
        "tasks": [
            "Generate creative content",
            "Respond to writing requests"
        ],
        "permissions": [
            "read_prompts",
            "write_content"
        ],
        "actions": [
            {
                "id": "write_paragraph",
                "description": "Write a paragraph about a topic",
                "prompt_template": """Write a single paragraph about the following topic:

Topic: {topic}

Style: {style}

Write a clear, engaging paragraph that introduces the topic and provides key insights."""
            },
            {
                "id": "brainstorm_ideas",
                "description": "Brainstorm ideas for a topic",
                "prompt_template": """Brainstorm 5 creative ideas related to:

Topic: {topic}

List them as numbered items with brief explanations."""
            }
        ]
    }
    
    yaml_path = demo_dir / "writer_agent.yaml"
    with open(yaml_path, 'w') as f:
        yaml.dump(agent_def, f, default_flow_style=False)
    
    return yaml_path


def main():
    print("=" * 60)
    print("Codynamic Book Machine - Simple Agent Demo")
    print("=" * 60)
    print()
    
    # Create demo agent definition
    print("[1] Creating demo agent definition...")
    yaml_path = create_demo_agent()
    print(f"    Created: {yaml_path}")
    print()
    
    # Initialize provider
    print("[2] Initializing LLM provider...")
    try:
        # Try OpenAI first, fall back to Claude
        from scripts.api import get_provider_with_fallback
        provider = get_provider_with_fallback(["openai", "anthropic"])
        print(f"    Using provider: {provider.get_provider_name()}")
        print(f"    Default model: {provider.default_model}")
    except Exception as e:
        print(f"    ERROR: Failed to initialize provider: {e}")
        print("    Make sure you have set KEY_OPENAI_API or KEY_ANTHROPIC_API environment variable")
        return
    print()
    
    # Create agent controller
    print("[3] Initializing agent controller...")
    controller = AgentController(
        agent_yaml_path=str(yaml_path),
        agent_id="demo_writer_001",
        provider=provider,
        data_root=Path("data")
    )
    print(f"    Agent ID: {controller.agent_id}")
    print(f"    State directory: {controller.agent_state_dir}")
    print()
    
    # Add a task
    print("[4] Adding task: Write paragraph about Codynamic Theory...")
    controller.add_task(
        "write_paragraph",
        {
            "topic": "Codynamic Theory and recursive self-modification",
            "style": "Clear and engaging, suitable for an introduction"
        }
    )
    print(f"    Tasks in queue: {len(controller.task_queue)}")
    print()
    
    # Execute task
    print("[5] Executing task...")
    print("-" * 60)
    success = controller.run_next_task()
    
    if success:
        print("-" * 60)
        print()
        
        # Show stats
        print("[6] Agent statistics:")
        stats = controller.get_stats()
        for key, value in stats.items():
            if key != "provider_stats":
                print(f"    {key}: {value}")
        print()
        
        # Show where to find results
        print("[7] Results saved to:")
        print(f"    Action log: {controller.agent_state_dir}/action_log.yaml")
        print()
        
        # Read and display the result
        import yaml
        log_path = controller.agent_state_dir / "action_log.yaml"
        if log_path.exists():
            with open(log_path, 'r') as f:
                log = yaml.safe_load(f)
                if log:
                    latest = log[-1]
                    print("Latest action result:")
                    print("-" * 60)
                    print(latest['response']['content'])
                    print("-" * 60)
    else:
        print("Task execution failed!")
    
    print()
    print("Demo complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()

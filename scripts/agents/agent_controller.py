"""
Agent Controller - Core Execution Engine

Manages agent lifecycle, task execution, and LLM interactions.
Supports multiple LLM providers through polymorphic abstraction.
"""

import threading
import time
import json
import yaml
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any
import logging

from scripts.api import (
    get_provider,
    get_provider_with_fallback,
    Message,
    LLMResponse,
    LLMProvider,
    LLMProviderError
)


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AgentController:
    """
    Controls a single agent's execution loop.
    
    Responsibilities:
    - Load agent definition from YAML
    - Execute actions using LLM provider
    - Manage task queue and message inbox
    - Log all activities
    - Handle inter-agent communication
    """
    
    def __init__(
        self,
        agent_yaml_path: str,
        agent_id: str,
        provider: Optional[LLMProvider] = None,
        provider_name: str = "openai",
        data_root: Optional[Path] = None
    ):
        """
        Initialize agent controller.
        
        Args:
            agent_yaml_path: Path to agent definition YAML
            agent_id: Unique identifier for this agent
            provider: Optional pre-configured LLM provider
            provider_name: Provider to use if provider not given
            data_root: Root directory for agent data (default: ./data)
        """
        self.agent_id = agent_id
        self.yaml_path = Path(agent_yaml_path)
        
        # Set up directory structure
        self.data_root = Path(data_root) if data_root else Path("data")
        self.agent_state_dir = self.data_root / "agent_state" / agent_id
        self.agent_state_dir.mkdir(parents=True, exist_ok=True)
        
        # Load agent definition
        self.agent_def = self._load_agent_definition()
        
        # Initialize LLM provider
        if provider:
            self.provider = provider
        else:
            self.provider = self._initialize_provider(provider_name)
        
        # Initialize state
        self.task_queue = self._load_task_queue()
        self.message_inbox: List[Dict[str, Any]] = []
        self.running = False
        
        # Message router will be set externally
        self.message_router = None
        
        logger.info(f"[{self.agent_id}] Controller initialized with {self.provider.get_provider_name()} provider")
    
    def _load_agent_definition(self) -> Dict[str, Any]:
        """Load and validate agent definition from YAML"""
        if not self.yaml_path.exists():
            raise FileNotFoundError(f"Agent definition not found: {self.yaml_path}")
        
        with open(self.yaml_path, 'r') as f:
            agent_def = yaml.safe_load(f)
        
        # Validate required fields
        required_fields = ['name', 'role', 'actions']
        missing = [f for f in required_fields if f not in agent_def]
        if missing:
            raise ValueError(f"Agent definition missing fields: {missing}")
        
        return agent_def
    
    def _initialize_provider(self, provider_name: str) -> LLMProvider:
        """Initialize LLM provider with fallback"""
        try:
            return get_provider(provider_name)
        except Exception as e:
            logger.warning(f"[{self.agent_id}] Failed to initialize {provider_name}, trying fallback: {e}")
            return get_provider_with_fallback([provider_name, "openai", "anthropic"])
    
    def _load_task_queue(self) -> List[Dict[str, Any]]:
        """Load task queue from persistent storage"""
        queue_path = self.agent_state_dir / "task_queue.yaml"
        
        if not queue_path.exists():
            return []
        
        try:
            with open(queue_path, 'r') as f:
                queue = yaml.safe_load(f) or []
                logger.info(f"[{self.agent_id}] Loaded {len(queue)} tasks from queue")
                return queue
        except Exception as e:
            logger.error(f"[{self.agent_id}] Failed to load task queue: {e}")
            return []
    
    def _save_task_queue(self):
        """Save task queue to persistent storage"""
        queue_path = self.agent_state_dir / "task_queue.yaml"
        
        try:
            with open(queue_path, 'w') as f:
                yaml.dump(self.task_queue, f, default_flow_style=False)
        except Exception as e:
            logger.error(f"[{self.agent_id}] Failed to save task queue: {e}")
    
    def add_task(self, action_id: str, context: Optional[Dict[str, Any]] = None):
        """
        Add a task to the queue.
        
        Args:
            action_id: ID of the action to execute
            context: Context variables for action prompt template
        """
        task = {
            "action_id": action_id,
            "context": context or {},
            "added_at": datetime.now().isoformat()
        }
        
        self.task_queue.append(task)
        self._save_task_queue()
        logger.info(f"[{self.agent_id}] Task added: {action_id}")
    
    def execute_action(
        self,
        action_id: str,
        context: Optional[Dict[str, Any]] = None
    ) -> LLMResponse:
        """
        Execute a single agent action using LLM.
        
        Args:
            action_id: ID of action from agent definition
            context: Template variables for prompt
            
        Returns:
            LLMResponse from provider
            
        Raises:
            ValueError: If action_id not found
            LLMProviderError: If LLM call fails
        """
        # Get action definition
        actions = self.agent_def.get('actions', {})
        
        # Actions can be a list of dicts with 'id' field or a dict keyed by id
        if isinstance(actions, list):
            action = next((a for a in actions if a.get('id') == action_id), None)
            if not action:
                raise ValueError(f"Action '{action_id}' not found in agent definition")
            prompt_template = action.get('prompt_template', '')
        else:
            action = actions.get(action_id)
            if not action:
                raise ValueError(f"Action '{action_id}' not found in agent definition")
            prompt_template = action.get('prompt_template', action.get('description', ''))
        
        # Fill template
        context = context or {}
        try:
            prompt = prompt_template.format(**context)
        except KeyError as e:
            logger.error(f"[{self.agent_id}] Missing template variable: {e}")
            prompt = prompt_template
        
        # Build system message
        system_prompt = self._build_system_prompt()
        
        # Execute via provider
        messages = [
            Message(role="system", content=system_prompt),
            Message(role="user", content=prompt)
        ]
        
        logger.info(f"[{self.agent_id}] Executing action: {action_id}")
        
        try:
            response = self.provider.call(
                messages=messages,
                temperature=0.7,
                max_tokens=2000
            )
            
            logger.info(f"[{self.agent_id}] Action completed: {action_id} ({response.tokens_used} tokens)")
            return response
            
        except LLMProviderError as e:
            logger.error(f"[{self.agent_id}] LLM call failed: {e}")
            raise
    
    def _build_system_prompt(self) -> str:
        """Build system prompt from agent definition"""
        name = self.agent_def.get('name', self.agent_id)
        role = self.agent_def.get('role', 'Assistant')
        
        system_prompt = f"""You are {name}, an agent in the Codynamic Book Machine system.

Your role: {role}

Your responsibilities:
"""
        
        # Add tasks if defined
        tasks = self.agent_def.get('tasks', [])
        if tasks:
            for task in tasks:
                system_prompt += f"- {task}\n"
        
        # Add permissions if defined
        permissions = self.agent_def.get('permissions', [])
        if permissions:
            system_prompt += "\nYour permissions:\n"
            for perm in permissions:
                system_prompt += f"- {perm}\n"
        
        return system_prompt
    
    def run_next_task(self) -> bool:
        """
        Execute next task from queue.
        
        Returns:
            True if task was executed, False if queue empty
        """
        if not self.task_queue:
            return False
        
        task = self.task_queue.pop(0)
        action_id = task.get('action_id')
        context = task.get('context', {})
        
        try:
            response = self.execute_action(action_id, context)
            self._log_action(action_id, context, response)
            self._handle_action_output(action_id, response)
            self._save_task_queue()
            return True
            
        except Exception as e:
            logger.error(f"[{self.agent_id}] Task execution failed: {e}")
            self._log_error(action_id, context, str(e))
            return False
    
    def _handle_action_output(self, action_id: str, response: LLMResponse):
        """
        Process action output - write files, send messages, etc.
        
        Override or extend in subclasses for specific agent behaviors.
        """
        # Default: just log the output
        logger.debug(f"[{self.agent_id}] Action output: {response.content[:200]}...")
    
    def receive_message(self, message: Dict[str, Any]):
        """Add message to inbox for processing"""
        self.message_inbox.append(message)
        logger.info(f"[{self.agent_id}] Message received: {message.get('subject', 'no subject')}")
    
    def process_message(self, message: Dict[str, Any]):
        """
        Process a message from inbox.
        
        Can create tasks, respond to requests, etc.
        """
        logger.info(f"[{self.agent_id}] Processing message: {message.get('subject')}")
        
        # If message contains action directive, add to queue
        body = message.get('body', '')
        if isinstance(body, str) and body.strip().startswith('action_id:'):
            try:
                task = yaml.safe_load(body)
                self.add_task(task.get('action_id'), task.get('context'))
            except Exception as e:
                logger.error(f"[{self.agent_id}] Failed to parse message task: {e}")
        
        self._log_message(message)
    
    def _log_action(self, action_id: str, context: Dict, response: LLMResponse):
        """Log action execution to persistent storage"""
        log_path = self.agent_state_dir / "action_log.yaml"
        
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "action_id": action_id,
            "context": context,
            "response": {
                "content": response.content[:500],  # Truncate for logging
                "model": response.model,
                "provider": response.provider,
                "tokens_used": response.tokens_used
            }
        }
        
        self._append_to_log(log_path, log_entry)
    
    def _log_error(self, action_id: str, context: Dict, error: str):
        """Log action error"""
        log_path = self.agent_state_dir / "error_log.yaml"
        
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "action_id": action_id,
            "context": context,
            "error": error
        }
        
        self._append_to_log(log_path, log_entry)
    
    def _log_message(self, message: Dict):
        """Log received message"""
        log_path = self.agent_state_dir / "message_log.yaml"
        
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "message": message
        }
        
        self._append_to_log(log_path, log_entry)
    
    def _append_to_log(self, log_path: Path, entry: Dict):
        """Append entry to YAML log file"""
        try:
            log = []
            if log_path.exists():
                with open(log_path, 'r') as f:
                    log = yaml.safe_load(f) or []
            
            log.append(entry)
            
            with open(log_path, 'w') as f:
                yaml.dump(log, f, default_flow_style=False)
                
        except Exception as e:
            logger.error(f"[{self.agent_id}] Failed to write log: {e}")
    
    def loop(self, idle_sleep: float = 0.5):
        """
        Main execution loop.
        
        Processes messages and tasks until stopped.
        
        Args:
            idle_sleep: Seconds to sleep when idle
        """
        self.running = True
        logger.info(f"[{self.agent_id}] Starting execution loop")
        
        while self.running:
            # Process messages first
            if self.message_inbox:
                message = self.message_inbox.pop(0)
                self.process_message(message)
                continue
            
            # Then execute tasks
            if self.run_next_task():
                continue
            
            # Idle - could add introspection task here
            time.sleep(idle_sleep)
        
        logger.info(f"[{self.agent_id}] Execution loop stopped")
    
    def stop(self):
        """Stop the execution loop"""
        self.running = False
        logger.info(f"[{self.agent_id}] Stop requested")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get agent statistics"""
        return {
            "agent_id": self.agent_id,
            "provider": self.provider.get_provider_name(),
            "provider_stats": self.provider.get_stats(),
            "task_queue_length": len(self.task_queue),
            "message_inbox_length": len(self.message_inbox),
            "running": self.running
        }


def launch_agent_thread(
    agent_yaml_path: str,
    agent_id: str,
    **kwargs
) -> tuple[AgentController, threading.Thread]:
    """
    Launch an agent in a separate thread.
    
    Args:
        agent_yaml_path: Path to agent definition YAML
        agent_id: Unique agent identifier
        **kwargs: Additional args for AgentController
        
    Returns:
        (controller, thread) tuple
    """
    controller = AgentController(agent_yaml_path, agent_id, **kwargs)
    thread = threading.Thread(target=controller.loop, daemon=True)
    thread.start()
    
    return controller, thread

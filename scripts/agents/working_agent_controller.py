"""
WorkingAgentController - Agent with work management discipline.

This extends AgentController to integrate WorkManager, creating
agents that:
- Plan work against checkpoints
- Respect capacity constraints
- Track dependencies and blockers
- Make overcommitment visible

The intent is that agents behave as disciplined workers, not
unbounded task executors.
"""

import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

from scripts.agents.agent_controller import AgentController
from scripts.work import (
    WorkManager,
    WorkItem,
    WorkItemStatus,
    Blocker,
    BlockerType,
    Checkpoint,
    CheckpointType,
    CheckpointSchedule,
    CapacityReport
)
from scripts.api import LLMProvider


logger = logging.getLogger(__name__)


class WorkingAgentController(AgentController):
    """
    An AgentController with integrated work management.
    
    Key differences from base AgentController:
    1. Uses WorkManager instead of simple task queue
    2. Plans against checkpoints
    3. Can decline work when overcommitted
    4. Tracks blockers explicitly
    5. Exposes capacity to other agents/hypervisor
    """
    
    def __init__(
        self,
        agent_yaml_path: str,
        agent_id: str,
        provider: Optional[LLMProvider] = None,
        provider_name: str = "openai",
        data_root: Optional[Path] = None,
        default_effort_minutes: int = 30
    ):
        # Initialize base controller
        super().__init__(
            agent_yaml_path=agent_yaml_path,
            agent_id=agent_id,
            provider=provider,
            provider_name=provider_name,
            data_root=data_root
        )
        
        # Replace simple task queue with WorkManager
        self.work_manager = WorkManager(
            agent_id=agent_id,
            data_root=self.data_root,
            default_effort_minutes=default_effort_minutes
        )
        
        # Register callbacks
        self.work_manager.on_overcommit(self._handle_overcommit)
        self.work_manager.on_checkpoint_imminent(self._handle_checkpoint_imminent)
        
        # Configure default checkpoint schedule (gardener review every 2 hours)
        self._setup_default_checkpoints()
        
        logger.info(f"[{self.agent_id}] WorkingAgentController initialized")
    
    def _setup_default_checkpoints(self):
        """Set up default checkpoint schedule."""
        # Gardener review every 2 hours
        gardener_schedule = CheckpointSchedule(
            name="Gardener Review",
            checkpoint_type=CheckpointType.GARDENER_REVIEW,
            interval_minutes=120,
            constraint_template="All work-in-progress must be reviewable",
            owner_agent="gardener_agent",
            participant_agents=[self.agent_id]
        )
        
        self.work_manager.add_checkpoint_schedule(gardener_schedule)
    
    # =========================================================================
    # Work Management Interface (replaces task queue)
    # =========================================================================
    
    def add_work(
        self,
        action_id: str,
        target: str,
        context: Dict[str, Any] = None,
        estimated_effort_minutes: int = None,
        priority: int = 50,
        depends_on: List[str] = None
    ) -> WorkItem:
        """
        Add work to this agent's queue.
        
        Unlike add_task(), this:
        - Estimates effort
        - Plans against checkpoints
        - May decline if overcommitted
        """
        # Check capacity before accepting
        effort = estimated_effort_minutes or self.work_manager.default_effort_minutes
        can_accept, reason = self.work_manager.can_accept_work(effort)
        
        if not can_accept:
            logger.warning(f"[{self.agent_id}] Cannot accept work: {reason}")
            # Still add it, but log the overcommitment
            # (Agent may choose to defer or decline via message)
        
        item = self.work_manager.add_work(
            action_id=action_id,
            target=target,
            context=context,
            estimated_effort_minutes=effort,
            priority=priority,
            depends_on=depends_on
        )
        
        logger.info(f"[{self.agent_id}] Added work: {item.item_id} ({action_id} on {target})")
        return item
    
    def request_feedback(
        self,
        item_id: str,
        from_agent: str,
        question: str
    ) -> Blocker:
        """
        Block work pending feedback from another agent.
        
        This creates a blocker and (optionally) sends a message
        to the requested agent.
        """
        blocker = Blocker(
            blocker_type=BlockerType.AWAITING_FEEDBACK,
            description=question,
            waiting_on=from_agent
        )
        
        self.work_manager.block_work(item_id, blocker)
        
        # Send message requesting feedback
        if self.message_router:
            self.message_router.publish({
                "subject": f"Feedback requested on {item_id}",
                "from": self.agent_id,
                "to": from_agent,
                "reply_to": self.agent_id,
                "body": f"item_id: {item_id}\nquestion: {question}"
            })
        
        return blocker
    
    def receive_feedback(self, item_id: str, feedback: str):
        """
        Receive feedback that resolves a blocker.
        """
        item = self.work_manager.get_item(item_id)
        if not item:
            logger.warning(f"[{self.agent_id}] Feedback for unknown item: {item_id}")
            return
        
        # Find the awaiting_feedback blocker
        for i, blocker in enumerate(item.blockers):
            if (blocker.blocker_type == BlockerType.AWAITING_FEEDBACK 
                and not blocker.is_resolved):
                self.work_manager.resolve_blocker(item_id, i, feedback)
                break
    
    def get_capacity(self) -> CapacityReport:
        """Get current capacity report."""
        return self.work_manager.get_capacity_report()
    
    def get_work_summary(self) -> Dict[str, Any]:
        """Get summary of work queue."""
        return self.work_manager.get_queue_summary()
    
    # =========================================================================
    # Execution Loop Override
    # =========================================================================
    
    def run_next_task(self) -> bool:
        """
        Execute next work item (override of base method).
        
        Uses WorkManager to select and execute work.
        """
        # Run planning cycle first
        self.work_manager.run_planning_cycle()
        
        # Get next work item
        item = self.work_manager.get_next_work()
        if not item:
            return False
        
        try:
            # Mark as in progress
            self.work_manager.start_work(item.item_id)
            
            # Execute the action
            response = self.execute_action(item.action_id, item.context)
            
            # Mark as complete
            self.work_manager.complete_work(item.item_id, response.content)
            
            # Handle output
            self._handle_action_output(item.action_id, response)
            
            return True
            
        except Exception as e:
            logger.error(f"[{self.agent_id}] Work execution failed: {e}")
            self.work_manager.fail_work(item.item_id, str(e))
            return False
    
    def loop(self, idle_sleep: float = 0.5):
        """
        Main execution loop (override with planning awareness).
        """
        self.running = True
        logger.info(f"[{self.agent_id}] Starting work loop")
        
        while self.running:
            # Process messages first
            if self.message_inbox:
                message = self.message_inbox.pop(0)
                self._process_work_message(message)
                continue
            
            # Check capacity before executing
            report = self.get_capacity()
            if report.is_overcommitted:
                self._handle_overcommit(report)
            
            # Execute work
            if self.run_next_task():
                continue
            
            # Idle - run introspection or planning
            self._idle_cycle()
            
            import time
            time.sleep(idle_sleep)
        
        logger.info(f"[{self.agent_id}] Work loop stopped")
    
    def _idle_cycle(self):
        """What to do when there's no work."""
        report = self.get_capacity()
        
        # If truly idle (no pending, blocked, or ready work), could:
        # 1. Request new work from outline agent
        # 2. Offer to help sibling agents
        # 3. Run self-improvement introspection
        
        total_active = report.ready_count + report.blocked_count + report.pending_count
        
        if total_active == 0:
            logger.debug(f"[{self.agent_id}] Queue empty, could request work")
            # Subclasses can override to request work
    
    # =========================================================================
    # Message Processing
    # =========================================================================
    
    def _process_work_message(self, message: Dict[str, Any]):
        """Process messages with work-aware handling."""
        subject = message.get("subject", "")
        body = message.get("body", "")
        
        # Check for feedback responses
        if "feedback" in subject.lower() or "feedback:" in body.lower():
            # Parse feedback format
            lines = body.split("\n")
            item_id = None
            feedback_content = []
            
            for line in lines:
                if line.startswith("item_id:"):
                    item_id = line.split(":", 1)[1].strip()
                elif line.startswith("feedback:"):
                    feedback_content.append(line.split(":", 1)[1].strip())
                else:
                    feedback_content.append(line)
            
            if item_id:
                self.receive_feedback(item_id, "\n".join(feedback_content))
                return
        
        # Check for work assignments
        if "assign" in subject.lower() or "action_id:" in body:
            self._handle_work_assignment(message)
            return
        
        # Default: process as before
        self.process_message(message)
    
    def _handle_work_assignment(self, message: Dict[str, Any]):
        """Handle a work assignment message."""
        import yaml
        body = message.get("body", "")
        
        try:
            work_spec = yaml.safe_load(body)
            
            self.add_work(
                action_id=work_spec.get("action_id"),
                target=work_spec.get("target", ""),
                context=work_spec.get("context", {}),
                estimated_effort_minutes=work_spec.get("effort_minutes"),
                priority=work_spec.get("priority", 50),
                depends_on=work_spec.get("depends_on", [])
            )
            
        except Exception as e:
            logger.error(f"[{self.agent_id}] Failed to parse work assignment: {e}")
    
    # =========================================================================
    # Callbacks
    # =========================================================================
    
    def _handle_overcommit(self, report: CapacityReport):
        """
        Handle overcommitment situation.
        
        Default behavior: log warning and notify hypervisor.
        Subclasses can override for specific handling.
        """
        logger.warning(
            f"[{self.agent_id}] OVERCOMMITTED by {report.overcommit_minutes} minutes. "
            f"Items at risk: {report.items_at_risk}"
        )
        
        # Notify hypervisor
        if self.message_router:
            self.message_router.publish({
                "subject": f"Overcommit alert from {self.agent_id}",
                "from": self.agent_id,
                "to": "hypervisor_agent",
                "reply_to": self.agent_id,
                "body": f"""
status: overcommitted
overcommit_minutes: {report.overcommit_minutes}
items_at_risk: {report.items_at_risk}
next_checkpoint: {report.next_checkpoint.name if report.next_checkpoint else 'none'}
request: Please advise on prioritization or deferral
"""
            })
    
    def _handle_checkpoint_imminent(self, checkpoint: Checkpoint):
        """
        Handle imminent checkpoint warning.
        
        Default behavior: log and notify.
        """
        logger.info(
            f"[{self.agent_id}] Checkpoint imminent: {checkpoint.name} "
            f"in {checkpoint.minutes_until} minutes"
        )
        
        # Check if we're ready
        report = self.get_capacity()
        
        if report.in_progress_count > 0:
            logger.warning(
                f"[{self.agent_id}] Work in progress at checkpoint time!"
            )


def launch_working_agent_thread(
    agent_yaml_path: str,
    agent_id: str,
    **kwargs
):
    """
    Launch a working agent in a separate thread.
    """
    import threading
    
    controller = WorkingAgentController(agent_yaml_path, agent_id, **kwargs)
    thread = threading.Thread(target=controller.loop, daemon=True)
    thread.start()
    
    return controller, thread

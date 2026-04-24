"""
WorkManager - Manages an agent's work toward zero.

This is the core discipline layer that transforms agents from
"things that execute tasks" into "workers that manage commitments."

Key responsibilities:
1. Maintain the work queue with proper dependency ordering
2. Plan work against checkpoints (don't overcommit)
3. Track blockers and unblock when resolved
4. Defer work that can't fit before next checkpoint
5. Report capacity and commitment status

The fundamental intent: agents should not accumulate unbounded work.
They should plan realistically against checkpoints and make the
consequences of overcommitment visible.
"""

import yaml
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple, Callable
from dataclasses import dataclass, field

from scripts.work.work_item import WorkItem, WorkItemStatus, Blocker, BlockerType
from scripts.work.checkpoint import Checkpoint, CheckpointStatus, CheckpointType, CheckpointSchedule


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class CapacityReport:
    """Snapshot of an agent's capacity situation."""
    
    next_checkpoint: Optional[Checkpoint]
    minutes_until_checkpoint: int
    
    # Work totals
    total_committed_minutes: int
    total_ready_minutes: int
    total_blocked_minutes: int
    total_pending_minutes: int
    
    # Counts
    ready_count: int
    blocked_count: int
    pending_count: int
    in_progress_count: int
    
    # Capacity assessment
    available_minutes: int
    is_overcommitted: bool
    overcommit_minutes: int
    
    # Items at risk
    items_at_risk: List[str]  # item_ids that may miss checkpoint
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "next_checkpoint": self.next_checkpoint.to_dict() if self.next_checkpoint else None,
            "minutes_until_checkpoint": self.minutes_until_checkpoint,
            "total_committed_minutes": self.total_committed_minutes,
            "total_ready_minutes": self.total_ready_minutes,
            "total_blocked_minutes": self.total_blocked_minutes,
            "total_pending_minutes": self.total_pending_minutes,
            "ready_count": self.ready_count,
            "blocked_count": self.blocked_count,
            "pending_count": self.pending_count,
            "in_progress_count": self.in_progress_count,
            "available_minutes": self.available_minutes,
            "is_overcommitted": self.is_overcommitted,
            "overcommit_minutes": self.overcommit_minutes,
            "items_at_risk": self.items_at_risk
        }


class WorkManager:
    """
    Manages an agent's work queue with discipline.
    
    The WorkManager enforces the following invariants:
    1. Work items have proper dependency ordering
    2. Capacity is tracked against checkpoints
    3. Overcommitment is visible and actionable
    4. Blockers are tracked and resolved
    5. Work history is auditable
    """
    
    def __init__(
        self,
        agent_id: str,
        data_root: Optional[Path] = None,
        default_effort_minutes: int = 30
    ):
        self.agent_id = agent_id
        self.data_root = Path(data_root) if data_root else Path("data")
        self.default_effort_minutes = default_effort_minutes
        
        # State directories
        self.work_dir = self.data_root / "agent_state" / agent_id / "work"
        self.work_dir.mkdir(parents=True, exist_ok=True)
        
        # Work items indexed by id
        self.items: Dict[str, WorkItem] = {}
        
        # Checkpoints
        self.checkpoints: List[Checkpoint] = []
        self.checkpoint_schedules: List[CheckpointSchedule] = []
        
        # Callbacks for external events
        self._on_overcommit: Optional[Callable[[CapacityReport], None]] = None
        self._on_blocker_resolved: Optional[Callable[[WorkItem, Blocker], None]] = None
        self._on_checkpoint_imminent: Optional[Callable[[Checkpoint], None]] = None
        
        # Load persisted state
        self._load_state()
        
        logger.info(f"[{self.agent_id}] WorkManager initialized with {len(self.items)} items")
    
    # =========================================================================
    # Work Item Management
    # =========================================================================
    
    def add_work(
        self,
        action_id: str,
        target: str,
        context: Dict[str, Any] = None,
        estimated_effort_minutes: int = None,
        priority: int = 50,
        checkpoint_target: str = None,
        depends_on: List[str] = None
    ) -> WorkItem:
        """
        Add a new work item to the queue.
        
        Returns the created WorkItem. Raises if this would cause
        severe overcommitment (optional, configurable).
        """
        item = WorkItem(
            action_id=action_id,
            target=target,
            context=context or {},
            estimated_effort_minutes=estimated_effort_minutes or self.default_effort_minutes,
            priority=priority,
            checkpoint_target=checkpoint_target,
            depends_on=depends_on or []
        )
        
        # Validate dependencies exist
        for dep_id in item.depends_on:
            if dep_id not in self.items:
                logger.warning(f"[{self.agent_id}] Dependency {dep_id} not found for {item.item_id}")
        
        # Determine initial status
        if self._dependencies_met(item):
            item.status = WorkItemStatus.READY
        else:
            item.status = WorkItemStatus.PENDING
        
        self.items[item.item_id] = item
        self._save_state()
        
        # Check capacity
        report = self.get_capacity_report()
        if report.is_overcommitted and self._on_overcommit:
            self._on_overcommit(report)
        
        logger.info(f"[{self.agent_id}] Added work item: {item.item_id} ({action_id})")
        return item
    
    def get_item(self, item_id: str) -> Optional[WorkItem]:
        """Get a work item by ID."""
        return self.items.get(item_id)
    
    def get_next_work(self) -> Optional[WorkItem]:
        """
        Get the next work item to execute.
        
        Selection criteria:
        1. Status must be READY
        2. Highest priority first
        3. Oldest creation date as tiebreaker
        """
        ready_items = [
            item for item in self.items.values()
            if item.status == WorkItemStatus.READY
        ]
        
        if not ready_items:
            return None
        
        # Sort by priority (desc) then created_at (asc)
        ready_items.sort(key=lambda x: (-x.priority, x.created_at))
        return ready_items[0]
    
    def start_work(self, item_id: str) -> WorkItem:
        """Mark a work item as in progress."""
        item = self.items.get(item_id)
        if not item:
            raise ValueError(f"Work item {item_id} not found")
        
        item.mark_in_progress()
        self._save_state()
        
        logger.info(f"[{self.agent_id}] Started work on: {item_id}")
        return item
    
    def complete_work(self, item_id: str, result: str = None) -> WorkItem:
        """Mark a work item as completed."""
        item = self.items.get(item_id)
        if not item:
            raise ValueError(f"Work item {item_id} not found")
        
        item.mark_done(result)
        self._save_state()
        
        # Check if this unblocks other items
        self._update_dependencies()
        
        logger.info(f"[{self.agent_id}] Completed work: {item_id}")
        return item
    
    def fail_work(self, item_id: str, error: str) -> WorkItem:
        """Mark a work item as failed."""
        item = self.items.get(item_id)
        if not item:
            raise ValueError(f"Work item {item_id} not found")
        
        item.mark_failed(error)
        self._save_state()
        
        logger.error(f"[{self.agent_id}] Work failed: {item_id} - {error}")
        return item
    
    def defer_work(self, item_id: str, reason: str, new_checkpoint: str = None) -> WorkItem:
        """Defer work past the current checkpoint."""
        item = self.items.get(item_id)
        if not item:
            raise ValueError(f"Work item {item_id} not found")
        
        item.mark_deferred(reason, new_checkpoint)
        self._save_state()
        
        logger.info(f"[{self.agent_id}] Deferred work: {item_id} - {reason}")
        return item
    
    def cancel_work(self, item_id: str, reason: str) -> WorkItem:
        """Cancel a work item."""
        item = self.items.get(item_id)
        if not item:
            raise ValueError(f"Work item {item_id} not found")
        
        item.mark_cancelled(reason)
        self._save_state()
        
        logger.info(f"[{self.agent_id}] Cancelled work: {item_id} - {reason}")
        return item
    
    def block_work(self, item_id: str, blocker: Blocker) -> WorkItem:
        """Block a work item on external input."""
        item = self.items.get(item_id)
        if not item:
            raise ValueError(f"Work item {item_id} not found")
        
        item.mark_blocked(blocker)
        self._save_state()
        
        logger.info(f"[{self.agent_id}] Blocked work: {item_id} - {blocker.description}")
        return item
    
    def resolve_blocker(self, item_id: str, blocker_index: int, resolution: str) -> WorkItem:
        """Resolve a blocker on a work item."""
        item = self.items.get(item_id)
        if not item:
            raise ValueError(f"Work item {item_id} not found")
        
        blocker = item.blockers[blocker_index] if blocker_index < len(item.blockers) else None
        item.resolve_blocker(blocker_index, resolution)
        
        # If unblocked, check if ready
        if item.all_blockers_resolved and item.status == WorkItemStatus.PENDING:
            if self._dependencies_met(item):
                item.mark_ready()
        
        self._save_state()
        
        if blocker and self._on_blocker_resolved:
            self._on_blocker_resolved(item, blocker)
        
        logger.info(f"[{self.agent_id}] Resolved blocker on: {item_id}")
        return item
    
    # =========================================================================
    # Checkpoint Management  
    # =========================================================================
    
    def add_checkpoint(self, checkpoint: Checkpoint) -> Checkpoint:
        """Add a checkpoint to the schedule."""
        self.checkpoints.append(checkpoint)
        self.checkpoints.sort(key=lambda x: x.scheduled_at)
        self._save_state()
        
        logger.info(f"[{self.agent_id}] Added checkpoint: {checkpoint.name}")
        return checkpoint
    
    def add_checkpoint_schedule(self, schedule: CheckpointSchedule) -> CheckpointSchedule:
        """Add a recurring checkpoint schedule."""
        self.checkpoint_schedules.append(schedule)
        
        # Generate the next checkpoint immediately
        next_cp = schedule.generate_next()
        self.add_checkpoint(next_cp)
        
        self._save_state()
        logger.info(f"[{self.agent_id}] Added checkpoint schedule: {schedule.name}")
        return schedule
    
    def get_next_checkpoint(self) -> Optional[Checkpoint]:
        """Get the next upcoming checkpoint."""
        now = datetime.now()
        future_checkpoints = [
            cp for cp in self.checkpoints
            if cp.scheduled_at > now and cp.status in (
                CheckpointStatus.SCHEDULED, 
                CheckpointStatus.ACTIVE
            )
        ]
        
        if not future_checkpoints:
            return None
        
        return min(future_checkpoints, key=lambda x: x.scheduled_at)
    
    def complete_checkpoint(
        self,
        checkpoint_id: str,
        outcome: str,
        work_items_reviewed: List[str] = None,
        feedback_generated: List[Dict[str, Any]] = None
    ):
        """Mark a checkpoint as completed and generate next if scheduled."""
        checkpoint = next(
            (cp for cp in self.checkpoints if cp.checkpoint_id == checkpoint_id),
            None
        )
        
        if not checkpoint:
            raise ValueError(f"Checkpoint {checkpoint_id} not found")
        
        checkpoint.complete(outcome, work_items_reviewed, feedback_generated)
        
        # Generate next checkpoint from schedule if applicable
        for schedule in self.checkpoint_schedules:
            if schedule.checkpoint_type == checkpoint.checkpoint_type and schedule.is_active:
                next_cp = schedule.generate_next(after=datetime.now())
                self.checkpoints.append(next_cp)
                self.checkpoints.sort(key=lambda x: x.scheduled_at)
                break
        
        self._save_state()
        logger.info(f"[{self.agent_id}] Completed checkpoint: {checkpoint.name}")
    
    # =========================================================================
    # Capacity Analysis
    # =========================================================================
    
    def get_capacity_report(self) -> CapacityReport:
        """
        Generate a capacity report for this agent.
        
        This is the key visibility tool - it shows whether the agent
        is overcommitted and which items are at risk.
        """
        next_cp = self.get_next_checkpoint()
        minutes_until = next_cp.minutes_until if next_cp else 480  # Default 8h
        
        # Categorize items
        ready_items = [i for i in self.items.values() if i.status == WorkItemStatus.READY]
        blocked_items = [i for i in self.items.values() if i.status == WorkItemStatus.BLOCKED]
        pending_items = [i for i in self.items.values() if i.status == WorkItemStatus.PENDING]
        in_progress = [i for i in self.items.values() if i.status == WorkItemStatus.IN_PROGRESS]
        
        # Calculate effort
        ready_minutes = sum(i.estimated_effort_minutes for i in ready_items)
        blocked_minutes = sum(i.estimated_effort_minutes for i in blocked_items)
        pending_minutes = sum(i.estimated_effort_minutes for i in pending_items)
        in_progress_minutes = sum(i.estimated_effort_minutes for i in in_progress)
        
        # Committed = ready + in_progress (things we will/are doing)
        committed = ready_minutes + in_progress_minutes
        
        # Available capacity
        available = max(0, minutes_until - committed)
        
        # Overcommit assessment
        is_overcommitted = committed > minutes_until
        overcommit = max(0, committed - minutes_until)
        
        # Items at risk (committed but may not fit)
        items_at_risk = []
        if is_overcommitted:
            # Lowest priority items are at risk
            sorted_ready = sorted(ready_items, key=lambda x: x.priority)
            remaining_over = overcommit
            for item in sorted_ready:
                if remaining_over > 0:
                    items_at_risk.append(item.item_id)
                    remaining_over -= item.estimated_effort_minutes
        
        return CapacityReport(
            next_checkpoint=next_cp,
            minutes_until_checkpoint=minutes_until,
            total_committed_minutes=committed,
            total_ready_minutes=ready_minutes,
            total_blocked_minutes=blocked_minutes,
            total_pending_minutes=pending_minutes,
            ready_count=len(ready_items),
            blocked_count=len(blocked_items),
            pending_count=len(pending_items),
            in_progress_count=len(in_progress),
            available_minutes=available,
            is_overcommitted=is_overcommitted,
            overcommit_minutes=overcommit,
            items_at_risk=items_at_risk
        )
    
    def can_accept_work(self, estimated_minutes: int) -> Tuple[bool, str]:
        """
        Check if this agent can accept additional work.
        
        Returns (can_accept, reason).
        """
        report = self.get_capacity_report()
        
        if report.is_overcommitted:
            return False, f"Already overcommitted by {report.overcommit_minutes} minutes"
        
        if estimated_minutes > report.available_minutes:
            return False, f"Only {report.available_minutes} minutes available, need {estimated_minutes}"
        
        return True, "Capacity available"
    
    def get_queue_summary(self) -> Dict[str, Any]:
        """Get a summary of the work queue."""
        by_status = {}
        for item in self.items.values():
            status = item.status.value
            by_status.setdefault(status, []).append({
                "item_id": item.item_id,
                "action_id": item.action_id,
                "target": item.target,
                "priority": item.priority,
                "effort": item.estimated_effort_minutes
            })
        
        return {
            "agent_id": self.agent_id,
            "total_items": len(self.items),
            "by_status": by_status,
            "capacity": self.get_capacity_report().to_dict()
        }
    
    # =========================================================================
    # Planning Cycle
    # =========================================================================
    
    def run_planning_cycle(self) -> Dict[str, Any]:
        """
        Execute a planning cycle.
        
        This is called periodically to:
        1. Update dependency status
        2. Check for passed checkpoints
        3. Identify items at risk
        4. Trigger callbacks for events
        
        Returns a report of actions taken.
        """
        actions = []
        
        # 1. Update dependencies
        updated = self._update_dependencies()
        if updated:
            actions.append(f"Updated {len(updated)} items from dependency resolution")
        
        # 2. Check checkpoints
        now = datetime.now()
        for cp in self.checkpoints:
            if cp.status == CheckpointStatus.SCHEDULED and cp.is_past:
                cp.mark_passed()
                actions.append(f"Checkpoint {cp.name} has passed")
            
            # Trigger imminent warning
            if (cp.status == CheckpointStatus.SCHEDULED 
                and cp.minutes_until <= 30 
                and self._on_checkpoint_imminent):
                self._on_checkpoint_imminent(cp)
                actions.append(f"Checkpoint {cp.name} is imminent")
        
        # 3. Generate checkpoint report
        report = self.get_capacity_report()
        
        # 4. Trigger overcommit warning if needed
        if report.is_overcommitted and self._on_overcommit:
            self._on_overcommit(report)
            actions.append(f"Overcommit warning: {report.overcommit_minutes} minutes over")
        
        self._save_state()
        
        return {
            "timestamp": datetime.now().isoformat(),
            "actions": actions,
            "capacity": report.to_dict()
        }
    
    # =========================================================================
    # Internal Methods
    # =========================================================================
    
    def _dependencies_met(self, item: WorkItem) -> bool:
        """Check if all dependencies for an item are met."""
        for dep_id in item.depends_on:
            dep = self.items.get(dep_id)
            if not dep or dep.status != WorkItemStatus.DONE:
                return False
        return True
    
    def _update_dependencies(self) -> List[str]:
        """Update status of items whose dependencies may have changed."""
        updated = []
        
        for item in self.items.values():
            if item.status == WorkItemStatus.PENDING:
                if self._dependencies_met(item) and item.all_blockers_resolved:
                    item.mark_ready()
                    updated.append(item.item_id)
        
        return updated
    
    def _save_state(self):
        """Persist work state to disk."""
        state = {
            "agent_id": self.agent_id,
            "updated_at": datetime.now().isoformat(),
            "items": {k: v.to_dict() for k, v in self.items.items()},
            "checkpoints": [cp.to_dict() for cp in self.checkpoints],
            "checkpoint_schedules": [s.to_dict() for s in self.checkpoint_schedules]
        }
        
        state_path = self.work_dir / "work_state.yaml"
        with open(state_path, 'w') as f:
            yaml.dump(state, f, default_flow_style=False, sort_keys=False)
    
    def _load_state(self):
        """Load persisted work state."""
        state_path = self.work_dir / "work_state.yaml"
        
        if not state_path.exists():
            return
        
        try:
            with open(state_path, 'r') as f:
                state = yaml.safe_load(f) or {}
            
            # Load items
            for item_id, item_data in state.get("items", {}).items():
                self.items[item_id] = WorkItem.from_dict(item_data)
            
            # Load checkpoints
            for cp_data in state.get("checkpoints", []):
                self.checkpoints.append(Checkpoint.from_dict(cp_data))
            
            # Load schedules
            for sched_data in state.get("checkpoint_schedules", []):
                self.checkpoint_schedules.append(CheckpointSchedule.from_dict(sched_data))
            
            logger.info(f"[{self.agent_id}] Loaded state: {len(self.items)} items, {len(self.checkpoints)} checkpoints")
            
        except Exception as e:
            logger.error(f"[{self.agent_id}] Failed to load state: {e}")
    
    # =========================================================================
    # Callbacks
    # =========================================================================
    
    def on_overcommit(self, callback: Callable[[CapacityReport], None]):
        """Register callback for overcommit events."""
        self._on_overcommit = callback
    
    def on_blocker_resolved(self, callback: Callable[[WorkItem, Blocker], None]):
        """Register callback for blocker resolution events."""
        self._on_blocker_resolved = callback
    
    def on_checkpoint_imminent(self, callback: Callable[[Checkpoint], None]):
        """Register callback for imminent checkpoint warnings."""
        self._on_checkpoint_imminent = callback

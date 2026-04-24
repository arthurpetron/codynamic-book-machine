"""
WorkItem - The atomic unit of agent work.

A WorkItem is not just a task to execute, but a commitment with:
- Dependencies (what must complete before I can start)
- Blockers (external things I'm waiting on)
- Effort estimate (how much capacity this consumes)
- Checkpoint target (when this must be done by)
- Priority (for scheduling decisions)

The intent is that agents manage their WorkItems toward zero,
planning against checkpoints like gardener reviews.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum
import uuid


class WorkItemStatus(Enum):
    """Lifecycle states for a WorkItem."""
    PENDING = "pending"           # Not yet ready to start (has unmet dependencies)
    READY = "ready"               # All dependencies met, can be scheduled
    BLOCKED = "blocked"           # Waiting on external input (feedback, resource, etc.)
    IN_PROGRESS = "in_progress"   # Currently being worked on
    DONE = "done"                 # Completed successfully
    DEFERRED = "deferred"         # Pushed past current checkpoint
    FAILED = "failed"             # Attempted but failed
    CANCELLED = "cancelled"       # No longer needed


class BlockerType(Enum):
    """Types of external blockers."""
    AWAITING_FEEDBACK = "awaiting_feedback"
    AWAITING_RESOURCE = "awaiting_resource"
    AWAITING_APPROVAL = "awaiting_approval"
    AWAITING_SIBLING = "awaiting_sibling"
    EXTERNAL_DEPENDENCY = "external_dependency"


@dataclass
class Blocker:
    """
    An external blocker preventing work from proceeding.
    
    Unlike dependencies (other WorkItems), blockers are external:
    - Waiting for feedback from gardener
    - Waiting for a resource to become available
    - Waiting for human approval
    """
    blocker_type: BlockerType
    description: str
    waiting_on: str  # agent_id, resource_id, or description
    requested_at: datetime = field(default_factory=datetime.now)
    resolved_at: Optional[datetime] = None
    resolution: Optional[str] = None
    
    @property
    def is_resolved(self) -> bool:
        return self.resolved_at is not None
    
    def resolve(self, resolution: str):
        """Mark this blocker as resolved."""
        self.resolved_at = datetime.now()
        self.resolution = resolution
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "blocker_type": self.blocker_type.value,
            "description": self.description,
            "waiting_on": self.waiting_on,
            "requested_at": self.requested_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "resolution": self.resolution
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Blocker":
        return cls(
            blocker_type=BlockerType(data["blocker_type"]),
            description=data["description"],
            waiting_on=data["waiting_on"],
            requested_at=datetime.fromisoformat(data["requested_at"]),
            resolved_at=datetime.fromisoformat(data["resolved_at"]) if data.get("resolved_at") else None,
            resolution=data.get("resolution")
        )


@dataclass
class WorkItem:
    """
    A unit of work that an agent commits to completing.
    
    WorkItems are managed toward zero - agents should not accumulate
    unbounded work, but rather plan against checkpoints and defer
    or decline work that exceeds capacity.
    """
    
    # Identity
    item_id: str = field(default_factory=lambda: f"wi_{uuid.uuid4().hex[:8]}")
    
    # What to do
    action_id: str = ""                    # Maps to agent action
    target: str = ""                       # What this operates on (section_id, etc.)
    context: Dict[str, Any] = field(default_factory=dict)  # Action parameters
    
    # Effort and scheduling
    estimated_effort_minutes: int = 30     # How long this is expected to take
    priority: int = 50                     # 0-100, higher = more urgent
    checkpoint_target: Optional[str] = None  # Must complete before this checkpoint
    
    # Dependencies (other WorkItems that must complete first)
    depends_on: List[str] = field(default_factory=list)  # List of item_ids
    
    # Blockers (external things we're waiting on)
    blockers: List[Blocker] = field(default_factory=list)
    
    # State
    status: WorkItemStatus = WorkItemStatus.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # Results
    result: Optional[str] = None
    error: Optional[str] = None
    
    # Audit trail
    history: List[Dict[str, Any]] = field(default_factory=list)
    
    def __post_init__(self):
        self._record_event("created", {"status": self.status.value})
    
    def _record_event(self, event_type: str, details: Dict[str, Any] = None):
        """Record an event in the work item's history."""
        self.history.append({
            "timestamp": datetime.now().isoformat(),
            "event": event_type,
            "details": details or {}
        })
    
    # --- Status Transitions ---
    
    def mark_ready(self):
        """Dependencies are met, this item can be scheduled."""
        if self.status not in (WorkItemStatus.PENDING, WorkItemStatus.BLOCKED):
            raise ValueError(f"Cannot mark {self.status.value} item as ready")
        
        old_status = self.status
        self.status = WorkItemStatus.READY
        self._record_event("status_change", {"from": old_status.value, "to": "ready"})
    
    def mark_blocked(self, blocker: Blocker):
        """This item is blocked on external input."""
        old_status = self.status
        self.status = WorkItemStatus.BLOCKED
        self.blockers.append(blocker)
        self._record_event("blocked", {
            "from": old_status.value,
            "blocker": blocker.to_dict()
        })
    
    def mark_in_progress(self):
        """Work has started on this item."""
        if self.status != WorkItemStatus.READY:
            raise ValueError(f"Cannot start work on {self.status.value} item")
        
        self.status = WorkItemStatus.IN_PROGRESS
        self.started_at = datetime.now()
        self._record_event("started", {})
    
    def mark_done(self, result: str = None):
        """Work completed successfully."""
        old_status = self.status
        self.status = WorkItemStatus.DONE
        self.completed_at = datetime.now()
        self.result = result
        self._record_event("completed", {
            "from": old_status.value,
            "result_length": len(result) if result else 0
        })
    
    def mark_failed(self, error: str):
        """Work attempted but failed."""
        old_status = self.status
        self.status = WorkItemStatus.FAILED
        self.completed_at = datetime.now()
        self.error = error
        self._record_event("failed", {"from": old_status.value, "error": error})
    
    def mark_deferred(self, reason: str, new_checkpoint: str = None):
        """Push this work past the current checkpoint."""
        old_status = self.status
        old_checkpoint = self.checkpoint_target
        self.status = WorkItemStatus.DEFERRED
        self.checkpoint_target = new_checkpoint
        self._record_event("deferred", {
            "from": old_status.value,
            "reason": reason,
            "old_checkpoint": old_checkpoint,
            "new_checkpoint": new_checkpoint
        })
    
    def mark_cancelled(self, reason: str):
        """This work is no longer needed."""
        old_status = self.status
        self.status = WorkItemStatus.CANCELLED
        self.completed_at = datetime.now()
        self._record_event("cancelled", {"from": old_status.value, "reason": reason})
    
    def resolve_blocker(self, blocker_index: int, resolution: str):
        """Resolve a specific blocker."""
        if blocker_index >= len(self.blockers):
            raise ValueError(f"Blocker index {blocker_index} out of range")
        
        self.blockers[blocker_index].resolve(resolution)
        self._record_event("blocker_resolved", {
            "blocker_index": blocker_index,
            "resolution": resolution
        })
        
        # If all blockers resolved and was blocked, check if can move to ready
        if self.status == WorkItemStatus.BLOCKED and self.all_blockers_resolved:
            self.status = WorkItemStatus.PENDING  # Will be evaluated for READY
            self._record_event("unblocked", {})
    
    # --- Query Methods ---
    
    @property
    def all_blockers_resolved(self) -> bool:
        return all(b.is_resolved for b in self.blockers)
    
    @property
    def active_blockers(self) -> List[Blocker]:
        return [b for b in self.blockers if not b.is_resolved]
    
    @property
    def is_actionable(self) -> bool:
        """Can work begin on this item right now?"""
        return self.status == WorkItemStatus.READY
    
    @property
    def is_terminal(self) -> bool:
        """Has this item reached a final state?"""
        return self.status in (
            WorkItemStatus.DONE,
            WorkItemStatus.FAILED,
            WorkItemStatus.CANCELLED
        )
    
    @property
    def actual_effort_minutes(self) -> Optional[int]:
        """How long did this actually take?"""
        if self.started_at and self.completed_at:
            delta = self.completed_at - self.started_at
            return int(delta.total_seconds() / 60)
        return None
    
    # --- Serialization ---
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "item_id": self.item_id,
            "action_id": self.action_id,
            "target": self.target,
            "context": self.context,
            "estimated_effort_minutes": self.estimated_effort_minutes,
            "priority": self.priority,
            "checkpoint_target": self.checkpoint_target,
            "depends_on": self.depends_on,
            "blockers": [b.to_dict() for b in self.blockers],
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "result": self.result,
            "error": self.error,
            "history": self.history
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkItem":
        item = cls(
            item_id=data["item_id"],
            action_id=data["action_id"],
            target=data["target"],
            context=data.get("context", {}),
            estimated_effort_minutes=data.get("estimated_effort_minutes", 30),
            priority=data.get("priority", 50),
            checkpoint_target=data.get("checkpoint_target"),
            depends_on=data.get("depends_on", []),
            blockers=[Blocker.from_dict(b) for b in data.get("blockers", [])],
            status=WorkItemStatus(data["status"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            started_at=datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None,
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
            result=data.get("result"),
            error=data.get("error"),
            history=data.get("history", [])
        )
        return item
    
    def __repr__(self):
        return f"WorkItem({self.item_id}, {self.action_id}, {self.status.value}, priority={self.priority})"

"""
Checkpoint - A point in time by which work must be completed.

Checkpoints create the rhythm of agent work:
- Gardener reviews
- Sibling sync points  
- Delivery deadlines
- Hypervisor check-ins

Agents plan their work against checkpoints, ensuring they don't
commit to more than they can complete before the next checkpoint.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from enum import Enum
import uuid


class CheckpointType(Enum):
    """Types of checkpoints in the system."""
    GARDENER_REVIEW = "gardener_review"     # Validation/feedback cycle
    SIBLING_SYNC = "sibling_sync"           # Coordination with peer agents
    DELIVERY_DEADLINE = "delivery_deadline"  # External commitment
    HYPERVISOR_CHECKIN = "hypervisor_checkin"  # Supervisory review
    COMPILATION = "compilation"              # Document assembly point
    CUSTOM = "custom"


class CheckpointStatus(Enum):
    """Lifecycle states for a Checkpoint."""
    SCHEDULED = "scheduled"   # Future checkpoint
    ACTIVE = "active"         # Currently the next checkpoint
    PASSED = "passed"         # Time has passed, results pending
    COMPLETED = "completed"   # Checkpoint activities finished
    MISSED = "missed"         # Checkpoint passed without completion
    CANCELLED = "cancelled"   # No longer needed


@dataclass
class Checkpoint:
    """
    A point in time that constrains agent work planning.
    
    Checkpoints are not just deadlines - they are synchronization
    points where agents must have work ready for review, coordination,
    or delivery.
    """
    
    # Identity
    checkpoint_id: str = field(default_factory=lambda: f"cp_{uuid.uuid4().hex[:8]}")
    name: str = ""
    checkpoint_type: CheckpointType = CheckpointType.CUSTOM
    
    # Timing
    scheduled_at: datetime = field(default_factory=datetime.now)
    duration_minutes: int = 30  # How long the checkpoint activities take
    
    # Constraint
    constraint: str = ""  # What must be true by this checkpoint
    
    # Participants
    owner_agent: str = ""  # Who is responsible for this checkpoint
    participant_agents: List[str] = field(default_factory=list)
    
    # State
    status: CheckpointStatus = CheckpointStatus.SCHEDULED
    
    # Results (after checkpoint passes)
    outcome: Optional[str] = None
    work_items_reviewed: List[str] = field(default_factory=list)
    feedback_generated: List[Dict[str, Any]] = field(default_factory=list)
    
    # Audit
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    
    @property
    def is_past(self) -> bool:
        """Has the scheduled time passed?"""
        return datetime.now() > self.scheduled_at
    
    @property
    def is_imminent(self, threshold_minutes: int = 30) -> bool:
        """Is this checkpoint coming up soon?"""
        return datetime.now() + timedelta(minutes=threshold_minutes) > self.scheduled_at
    
    @property
    def time_until(self) -> timedelta:
        """Time remaining until checkpoint."""
        return self.scheduled_at - datetime.now()
    
    @property
    def minutes_until(self) -> int:
        """Minutes remaining until checkpoint."""
        delta = self.time_until
        return max(0, int(delta.total_seconds() / 60))
    
    def activate(self):
        """Mark this as the next active checkpoint."""
        if self.status != CheckpointStatus.SCHEDULED:
            raise ValueError(f"Cannot activate {self.status.value} checkpoint")
        self.status = CheckpointStatus.ACTIVE
    
    def mark_passed(self):
        """Time has passed, checkpoint activities beginning."""
        if self.status not in (CheckpointStatus.SCHEDULED, CheckpointStatus.ACTIVE):
            raise ValueError(f"Cannot pass {self.status.value} checkpoint")
        self.status = CheckpointStatus.PASSED
    
    def complete(self, outcome: str, work_items_reviewed: List[str] = None,
                 feedback_generated: List[Dict[str, Any]] = None):
        """Checkpoint activities finished."""
        self.status = CheckpointStatus.COMPLETED
        self.completed_at = datetime.now()
        self.outcome = outcome
        self.work_items_reviewed = work_items_reviewed or []
        self.feedback_generated = feedback_generated or []
    
    def mark_missed(self, reason: str):
        """Checkpoint passed without required work being ready."""
        self.status = CheckpointStatus.MISSED
        self.completed_at = datetime.now()
        self.outcome = f"MISSED: {reason}"
    
    def cancel(self, reason: str):
        """Checkpoint no longer needed."""
        self.status = CheckpointStatus.CANCELLED
        self.completed_at = datetime.now()
        self.outcome = f"CANCELLED: {reason}"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "name": self.name,
            "checkpoint_type": self.checkpoint_type.value,
            "scheduled_at": self.scheduled_at.isoformat(),
            "duration_minutes": self.duration_minutes,
            "constraint": self.constraint,
            "owner_agent": self.owner_agent,
            "participant_agents": self.participant_agents,
            "status": self.status.value,
            "outcome": self.outcome,
            "work_items_reviewed": self.work_items_reviewed,
            "feedback_generated": self.feedback_generated,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Checkpoint":
        return cls(
            checkpoint_id=data["checkpoint_id"],
            name=data["name"],
            checkpoint_type=CheckpointType(data["checkpoint_type"]),
            scheduled_at=datetime.fromisoformat(data["scheduled_at"]),
            duration_minutes=data.get("duration_minutes", 30),
            constraint=data.get("constraint", ""),
            owner_agent=data.get("owner_agent", ""),
            participant_agents=data.get("participant_agents", []),
            status=CheckpointStatus(data["status"]),
            outcome=data.get("outcome"),
            work_items_reviewed=data.get("work_items_reviewed", []),
            feedback_generated=data.get("feedback_generated", []),
            created_at=datetime.fromisoformat(data["created_at"]),
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None
        )
    
    def __repr__(self):
        return f"Checkpoint({self.checkpoint_id}, {self.name}, {self.status.value}, at={self.scheduled_at})"


@dataclass
class CheckpointSchedule:
    """
    A schedule of recurring checkpoints.
    
    For example, "gardener review every 2 hours" or
    "sibling sync at 9am and 3pm daily".
    """
    
    schedule_id: str = field(default_factory=lambda: f"sched_{uuid.uuid4().hex[:8]}")
    name: str = ""
    checkpoint_type: CheckpointType = CheckpointType.CUSTOM
    
    # Recurrence
    interval_minutes: Optional[int] = None  # Every N minutes
    times_of_day: List[str] = field(default_factory=list)  # ["09:00", "15:00"]
    days_of_week: List[int] = field(default_factory=list)  # 0=Monday, 6=Sunday
    
    # Template for generated checkpoints
    constraint_template: str = ""
    owner_agent: str = ""
    participant_agents: List[str] = field(default_factory=list)
    duration_minutes: int = 30
    
    # State
    is_active: bool = True
    last_generated: Optional[datetime] = None
    
    def generate_next(self, after: datetime = None) -> Checkpoint:
        """Generate the next checkpoint in this schedule."""
        after = after or datetime.now()
        
        if self.interval_minutes:
            # Interval-based: next checkpoint is interval_minutes from after
            scheduled_at = after + timedelta(minutes=self.interval_minutes)
        elif self.times_of_day:
            # Time-based: find next matching time
            scheduled_at = self._find_next_scheduled_time(after)
        else:
            # Default: 1 hour from now
            scheduled_at = after + timedelta(hours=1)
        
        checkpoint = Checkpoint(
            name=f"{self.name} @ {scheduled_at.strftime('%Y-%m-%d %H:%M')}",
            checkpoint_type=self.checkpoint_type,
            scheduled_at=scheduled_at,
            duration_minutes=self.duration_minutes,
            constraint=self.constraint_template,
            owner_agent=self.owner_agent,
            participant_agents=self.participant_agents.copy()
        )
        
        self.last_generated = datetime.now()
        return checkpoint
    
    def _find_next_scheduled_time(self, after: datetime) -> datetime:
        """Find the next time matching times_of_day and days_of_week."""
        candidate = after
        
        for _ in range(14):  # Look up to 2 weeks ahead
            # Check if day of week matches (empty = all days)
            if not self.days_of_week or candidate.weekday() in self.days_of_week:
                for time_str in sorted(self.times_of_day):
                    hour, minute = map(int, time_str.split(":"))
                    scheduled = candidate.replace(hour=hour, minute=minute, second=0, microsecond=0)
                    if scheduled > after:
                        return scheduled
            
            # Move to next day
            candidate = (candidate + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Fallback
        return after + timedelta(hours=24)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "schedule_id": self.schedule_id,
            "name": self.name,
            "checkpoint_type": self.checkpoint_type.value,
            "interval_minutes": self.interval_minutes,
            "times_of_day": self.times_of_day,
            "days_of_week": self.days_of_week,
            "constraint_template": self.constraint_template,
            "owner_agent": self.owner_agent,
            "participant_agents": self.participant_agents,
            "duration_minutes": self.duration_minutes,
            "is_active": self.is_active,
            "last_generated": self.last_generated.isoformat() if self.last_generated else None
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CheckpointSchedule":
        return cls(
            schedule_id=data["schedule_id"],
            name=data["name"],
            checkpoint_type=CheckpointType(data["checkpoint_type"]),
            interval_minutes=data.get("interval_minutes"),
            times_of_day=data.get("times_of_day", []),
            days_of_week=data.get("days_of_week", []),
            constraint_template=data.get("constraint_template", ""),
            owner_agent=data.get("owner_agent", ""),
            participant_agents=data.get("participant_agents", []),
            duration_minutes=data.get("duration_minutes", 30),
            is_active=data.get("is_active", True),
            last_generated=datetime.fromisoformat(data["last_generated"]) if data.get("last_generated") else None
        )

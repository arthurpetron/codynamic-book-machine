"""
Work Management Package

Provides disciplined work management for agents:
- WorkItem: Atomic unit of work with dependencies, blockers, effort
- Checkpoint: Synchronization points for reviews and coordination
- WorkManager: Enforces planning discipline against checkpoints

The intent is to make agents plan realistically and make
overcommitment visible, not hidden.
"""

from scripts.work.work_item import (
    WorkItem,
    WorkItemStatus,
    Blocker,
    BlockerType
)

from scripts.work.checkpoint import (
    Checkpoint,
    CheckpointStatus,
    CheckpointType,
    CheckpointSchedule
)

from scripts.work.work_manager import (
    WorkManager,
    CapacityReport
)

__all__ = [
    # Work Items
    'WorkItem',
    'WorkItemStatus', 
    'Blocker',
    'BlockerType',
    
    # Checkpoints
    'Checkpoint',
    'CheckpointStatus',
    'CheckpointType',
    'CheckpointSchedule',
    
    # Manager
    'WorkManager',
    'CapacityReport'
]

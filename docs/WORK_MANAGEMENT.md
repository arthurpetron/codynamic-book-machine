# Work Management System

## Overview

The Work Management System transforms agents from "task executors" into "disciplined workers" who:

- **Manage their queue toward zero** (don't accumulate unbounded work)
- **Plan against checkpoints** (gardener reviews, sync points)
- **Respect capacity constraints** (can't commit to more than fits)
- **Track dependencies and blockers** (work proceeds in order)
- **Make overcommitment visible** (consequences are real)

## Core Components

### WorkItem (`scripts/work/work_item.py`)

The atomic unit of work with:

- **Action & target**: What to do and what it operates on
- **Effort estimate**: How long this takes (minutes)
- **Priority**: For scheduling (0-100, higher = more urgent)
- **Dependencies**: Other WorkItems that must complete first
- **Blockers**: External inputs we're waiting for
- **Status lifecycle**: PENDING → READY → IN_PROGRESS → DONE/FAILED/DEFERRED

```python
item = WorkItem(
    action_id="draft_section",
    target="section_3.2",
    estimated_effort_minutes=45,
    priority=80,
    depends_on=["wi_intent_extraction"],
    checkpoint_target="gardener_review_1"
)
```

### Checkpoint (`scripts/work/checkpoint.py`)

Synchronization points that constrain planning:

- **Gardener reviews**: Validation cycles
- **Sibling syncs**: Coordination points
- **Delivery deadlines**: External commitments

```python
checkpoint = Checkpoint(
    name="Gardener Review 1",
    checkpoint_type=CheckpointType.GARDENER_REVIEW,
    scheduled_at=datetime.now() + timedelta(hours=2),
    constraint="All draft sections must be reviewable"
)
```

### WorkManager (`scripts/work/work_manager.py`)

The discipline enforcement layer that:

1. **Tracks all work items** with proper state management
2. **Manages checkpoints** and their schedules
3. **Computes capacity reports** showing commitment vs availability
4. **Detects overcommitment** and identifies items at risk
5. **Triggers callbacks** for important events

```python
manager = WorkManager(agent_id="section_agent")

# Add work
item = manager.add_work(
    action_id="draft_section",
    target="section_3.2",
    estimated_effort_minutes=45
)

# Check capacity
can_accept, reason = manager.can_accept_work(30)

# Get capacity report
report = manager.get_capacity_report()
if report.is_overcommitted:
    print(f"Over by {report.overcommit_minutes} minutes!")
    print(f"Items at risk: {report.items_at_risk}")
```

### WorkingAgentController (`scripts/agents/working_agent_controller.py`)

Integration of WorkManager with AgentController:

- Replaces simple task queue with WorkManager
- Plans work against checkpoints
- Handles work assignment messages
- Manages feedback request/response flow
- Alerts hypervisor on overcommit

## Key Behaviors

### 1. Dependencies Block Work

```python
item1 = manager.add_work(action_id="extract_intent", target="3.2")
item2 = manager.add_work(action_id="draft", target="3.2", depends_on=[item1.item_id])

# item2 is PENDING until item1 is DONE
manager.complete_work(item1.item_id)
# Now item2 is READY
```

### 2. Capacity Is Finite

```python
manager.add_checkpoint(Checkpoint(
    name="Review",
    scheduled_at=datetime.now() + timedelta(minutes=60)
))

# 60 minutes until checkpoint
manager.add_work(action_id="task1", target="t1", estimated_effort_minutes=40)

# Can I accept 30 more minutes?
can_accept, reason = manager.can_accept_work(30)
# False: "Only 20 minutes available, need 30"
```

### 3. Overcommitment Is Visible

```python
report = manager.get_capacity_report()

if report.is_overcommitted:
    # These items won't fit before checkpoint
    for item_id in report.items_at_risk:
        manager.defer_work(item_id, "Cannot complete before checkpoint")
```

### 4. Blockers Halt Progress

```python
item = manager.add_work(action_id="revise", target="section_3.2")
manager.start_work(item.item_id)

# Need feedback
manager.block_work(item.item_id, Blocker(
    blocker_type=BlockerType.AWAITING_FEEDBACK,
    description="Need gardener review on notation",
    waiting_on="gardener_agent"
))

# Item is now BLOCKED, not available for execution
# Until feedback arrives:
manager.resolve_blocker(item.item_id, 0, "Notation approved")
```

## Checkpoints as Cadence

The system uses checkpoints to create natural work rhythms:

```python
# Gardener review every 2 hours
schedule = CheckpointSchedule(
    name="Gardener Review",
    checkpoint_type=CheckpointType.GARDENER_REVIEW,
    interval_minutes=120,
    constraint_template="All work must be reviewable"
)
manager.add_checkpoint_schedule(schedule)
```

Agents plan their work to fit before the next checkpoint. If they can't, they must:
1. Defer lower-priority work
2. Alert the hypervisor
3. Negotiate with siblings for help

## Integration with Message System

Work assignments come via messages:

```yaml
subject: Assign work to section_agent
from: outline_agent
to: section_agent
body: |
  action_id: draft_section
  target: section_3.2
  effort_minutes: 45
  priority: 80
  context:
    intent: "Explain distributed coordination"
```

Feedback requests create blockers:

```yaml
subject: Feedback requested on wi_abc123
from: section_agent
to: gardener_agent
body: |
  item_id: wi_abc123
  question: Is this mathematical notation appropriate?
```

## Files Created

```
scripts/work/
├── __init__.py           # Package exports
├── work_item.py          # WorkItem, Blocker, BlockerType, WorkItemStatus
├── checkpoint.py         # Checkpoint, CheckpointSchedule, CheckpointType
└── work_manager.py       # WorkManager, CapacityReport

scripts/agents/
└── working_agent_controller.py  # Integration with AgentController

tests/
└── test_work_management.py      # 26 tests demonstrating behavior
```

## Running Tests

```bash
cd codynamic-book-machine
python3 -m pytest tests/test_work_management.py -v
```

## Design Intent

This system embodies the principle that **agents should work like disciplined professionals**:

1. **Know your capacity** - Don't agree to more than you can deliver
2. **Plan against deadlines** - Work backward from checkpoints
3. **Make blockers explicit** - Don't silently wait, communicate
4. **Defer consciously** - When overloaded, decide what to push out
5. **Track dependencies** - Know what must happen before you can proceed

The consequences are real: if an agent is overcommitted, the system knows. If work is blocked, it's visible. If dependencies aren't met, work can't proceed.

This is the foundation for agents that coordinate like a well-run team, not a chaotic swarm.

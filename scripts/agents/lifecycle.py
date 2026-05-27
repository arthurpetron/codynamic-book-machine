"""Agent lifecycle states inspired by EtherCAT state transitions."""

from __future__ import annotations

from enum import Enum


class AgentLifecycleState(str, Enum):
    BOOTSTRAP = "bootstrap"
    INIT = "init"
    PRE_OPERATIONAL = "pre_operational"
    SAFE_OPERATIONAL = "safe_operational"
    OPERATIONAL = "operational"


ALLOWED_TRANSITIONS = {
    AgentLifecycleState.BOOTSTRAP: {
        AgentLifecycleState.INIT,
    },
    AgentLifecycleState.INIT: {
        AgentLifecycleState.BOOTSTRAP,
        AgentLifecycleState.PRE_OPERATIONAL,
    },
    AgentLifecycleState.PRE_OPERATIONAL: {
        AgentLifecycleState.INIT,
        AgentLifecycleState.SAFE_OPERATIONAL,
    },
    AgentLifecycleState.SAFE_OPERATIONAL: {
        AgentLifecycleState.PRE_OPERATIONAL,
        AgentLifecycleState.OPERATIONAL,
    },
    AgentLifecycleState.OPERATIONAL: {
        AgentLifecycleState.SAFE_OPERATIONAL,
    },
}


API_STATES = {
    AgentLifecycleState.PRE_OPERATIONAL,
    AgentLifecycleState.SAFE_OPERATIONAL,
    AgentLifecycleState.OPERATIONAL,
}

COMMUNICATION_STATES = {
    AgentLifecycleState.SAFE_OPERATIONAL,
    AgentLifecycleState.OPERATIONAL,
}

OUTPUT_MUTATION_STATES = {
    AgentLifecycleState.OPERATIONAL,
}

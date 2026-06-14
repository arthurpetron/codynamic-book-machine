import type { useBookStore } from "../../state/bookStore";

interface MenuBarProps {
  store: ReturnType<typeof useBookStore>;
}

export function MenuBar({ store }: MenuBarProps) {
  const gardener = (store.state.agentStatus?.activeAgents ?? [])
    .find((agent) => agent.agent_id === "gardener_agent");
  const gardenerQueueLength = gardener?.task_queue_length ?? 0;
  const gardenerActive = Boolean(gardenerQueueLength > 0 || (store.hypervisorEnabled && gardener?.status === "running"));
  const diagramer = (store.state.agentStatus?.activeAgents ?? [])
    .find((agent) => agent.agent_id === "diagram_agent");
  const diagramerQueueLength = diagramer?.task_queue_length ?? 0;
  const diagramerActive = Boolean(diagramerQueueLength > 0 || (store.hypervisorEnabled && diagramer?.status === "running"));

  return (
    <header className="titlebar app-header" aria-label="Book workspace header">
      <div className="window-title">
        <strong>Codynamic Book Machine</strong>
        <span>{store.state.book?.title ?? "No book loaded"}</span>
      </div>
      <div className="user-badge" aria-label="Signed in user">
        <span className="avatar">AP</span>
        <span>Arthur</span>
        <button className="user-chat-button" type="button" aria-label="Pending user chat messages">
          User Chat
          <span className="queue-badge">0</span>
        </button>
        <button
          className={`hypervisor-toggle ${store.hypervisorEnabled ? "is-enabled" : ""}`}
          type="button"
          aria-pressed={store.hypervisorEnabled}
          onClick={store.toggleHypervisor}
        >
          Hypervisor
          <span className="queue-badge">{store.isHypervisorWorking ? "..." : store.hypervisorEnabled ? "on" : "off"}</span>
        </button>
        <span
          className={`agent-status-pill ${gardenerActive ? "is-active" : ""}`}
          title={`gardener_agent · ${gardenerQueueLength} queued`}
          aria-label={`Gardener ${gardenerActive ? "active" : "idle"}`}
        >
          Gardener
          <span className="queue-badge">{gardenerQueueLength > 0 ? gardenerQueueLength : gardenerActive ? "on" : "off"}</span>
        </span>
        <span
          className={`agent-status-pill ${diagramerActive ? "is-active" : ""}`}
          title={`diagram_agent · ${diagramerQueueLength} queued`}
          aria-label={`Diagramer ${diagramerActive ? "active" : "idle"}`}
        >
          Diagramer
          <span className="queue-badge">{diagramerQueueLength > 0 ? diagramerQueueLength : diagramerActive ? "on" : "off"}</span>
        </span>
      </div>
    </header>
  );
}

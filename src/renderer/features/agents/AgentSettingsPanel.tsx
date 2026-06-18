import type { BookAppState } from "../../api/types";

interface AgentSettingsPanelProps {
  state: BookAppState;
}

export function AgentSettingsPanel({ state }: AgentSettingsPanelProps) {
  const status = state.agentStatus;
  const latest = state.verification?.at(-1);
  const agents = [
    {
      name: "Section Agent",
      purpose: "Drafts and revises section payloads.",
      model: "default writer",
      tools: ["section payloads", "citations", "media requests"],
      approval: "Proposal required"
    },
    {
      name: "Gardener",
      purpose: "Checks intent, dependencies, claim clarity, and LaTeX.",
      model: "default reviewer",
      tools: ["verification history", "outline", "section payloads"],
      approval: "Can comment only"
    },
    {
      name: "Hypervisor",
      purpose: "Tracks global drift, queues work, and pauses on uncertainty.",
      model: "default planner",
      tools: ["agent state", "verification history", "book graph"],
      approval: "Can pause swarm"
    },
    {
      name: "Diagram Agent",
      purpose: "Creates all diagrams and artwork into media/diagrams.",
      model: "default visual",
      tools: ["media/diagrams", "structured specs"],
      approval: "Proposal required"
    },
    {
      name: "Document Design Agent",
      purpose: "Reviews LaTeX and compiled PDFs for typesetting problems.",
      model: "default design",
      tools: ["cls/style files", "PDF preview", "compile logs"],
      approval: "Global style edits require approval"
    },
    {
      name: "Citation Agent",
      purpose: "Checks missing citations, orphan claims, and reference links.",
      model: "default research",
      tools: ["references", "knowledge graph"],
      approval: "Can flag; cannot invent sources"
    }
  ];

  return (
    <div className="agent-settings-layout">
      <section className="settings-section" aria-label="Global app agent settings">
        <div className="detail-section-title">
          <p className="eyebrow">Global App Settings</p>
          <h3>Authoring loop</h3>
        </div>
        <div className="settings-grid">
          <div className="setting-field read-only-setting">
            <span>Execution mode</span>
            <strong>Proposal first</strong>
          </div>
          <div className="setting-field read-only-setting">
            <span>Review depth</span>
            <strong>Full semantic review</strong>
          </div>
          <div className="setting-field read-only-setting">
            <span>Memory scope</span>
            <strong>Project memory</strong>
          </div>
          <div className="setting-field read-only-setting">
            <span>Max parallel agents</span>
            <strong>{Math.max(1, status?.active ?? 1)}</strong>
          </div>
        </div>
        <div className="settings-checks">
          <span>Require approval for outline changes</span>
          <span>Require approval for global style changes</span>
          <span>Stop on unresolved citation errors</span>
          <span>Save traces and rationale</span>
        </div>
        <div className="runtime-summary">
          <span>{status?.active ?? 0}/{status?.total ?? 1} active</span>
          <span>{status?.pendingProposals ?? 0} pending proposals</span>
          <span>{status?.confidence ?? 0}% confidence</span>
          <span>{state.verification?.length ?? 0} verification events</span>
        </div>
        <p className="settings-note">{latest?.rationale ?? "No verification events recorded yet."}</p>
      </section>

      <section className="settings-section" aria-label="Per-agent settings">
        <div className="detail-section-title">
          <p className="eyebrow">Per-Agent Settings</p>
          <h3>{agents.length} roles</h3>
        </div>
        <div className="agent-card-grid">
          {agents.map((agent) => (
            <article className="agent-card" key={agent.name}>
              <div className="agent-card-header">
                <div>
                  <h4>{agent.name}</h4>
                  <p>{agent.purpose}</p>
                </div>
                <span className="agent-enabled">On</span>
              </div>
              <div className="agent-setting-row read-only-setting">
                <span>Model</span>
                <strong>{agent.model}</strong>
              </div>
              <div className="agent-setting-row read-only-setting">
                <span>Approval</span>
                <strong>{agent.approval}</strong>
              </div>
              <div className="tool-chips" aria-label={`${agent.name} tools`}>
                {agent.tools.map((tool) => <span key={tool}>{tool}</span>)}
              </div>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}

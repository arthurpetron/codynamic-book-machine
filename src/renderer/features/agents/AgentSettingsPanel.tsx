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
          <label className="setting-field">
            <span>Execution mode</span>
            <select defaultValue="proposal">
              <option value="manual">Manual</option>
              <option value="proposal">Proposal first</option>
              <option value="full-auto">Full auto</option>
            </select>
          </label>
          <label className="setting-field">
            <span>Review depth</span>
            <select defaultValue="full">
              <option value="quick">Quick pass</option>
              <option value="full">Full semantic review</option>
              <option value="latex">LaTeX only</option>
              <option value="citation">Citation review</option>
              <option value="design">Design review</option>
            </select>
          </label>
          <label className="setting-field">
            <span>Memory scope</span>
            <select defaultValue="project">
              <option value="none">Off</option>
              <option value="section">Section local</option>
              <option value="project">Project memory</option>
              <option value="accepted">Accepted/rejected proposal history</option>
            </select>
          </label>
          <label className="setting-field">
            <span>Max parallel agents</span>
            <input type="number" min={1} max={12} defaultValue={Math.max(1, status?.active ?? 1)} />
          </label>
        </div>
        <div className="settings-checks">
          <label><input type="checkbox" defaultChecked /> Require approval for outline changes</label>
          <label><input type="checkbox" defaultChecked /> Require approval for global style changes</label>
          <label><input type="checkbox" defaultChecked /> Stop on unresolved citation errors</label>
          <label><input type="checkbox" defaultChecked /> Save traces and rationale</label>
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
                <label className="agent-enabled">
                  <input type="checkbox" defaultChecked />
                  <span>On</span>
                </label>
              </div>
              <div className="agent-setting-row">
                <span>Model</span>
                <select defaultValue={agent.model}>
                  <option value={agent.model}>{agent.model}</option>
                  <option value="fast">fast</option>
                  <option value="deep">deep</option>
                </select>
              </div>
              <div className="agent-setting-row">
                <span>Approval</span>
                <select defaultValue={agent.approval}>
                  <option value={agent.approval}>{agent.approval}</option>
                  <option value="Manual only">Manual only</option>
                  <option value="Can write in full auto">Can write in full auto</option>
                </select>
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

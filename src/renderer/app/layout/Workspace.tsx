import { useState } from "react";
import { AgentSettingsPanel } from "../../features/agents/AgentSettingsPanel";
import { ProposalReviewPanel } from "../../features/agents/ProposalReviewPanel";
import { SectionEditor } from "../../features/editor/SectionEditor";
import { OutlinePane } from "../../features/outline/OutlinePane";
import { PdfPreviewPane } from "../../features/preview/PdfPreviewPane";
import { ArtifactBrowser } from "../../features/references/ArtifactBrowser";
import { ReferencesPanel } from "../../features/references/ReferencesPanel";
import type { useBookStore, WorkspaceTab } from "../../state/bookStore";

interface WorkspaceProps {
  store: ReturnType<typeof useBookStore>;
}

const tabs: { id: WorkspaceTab; label: string }[] = [
  { id: "editor", label: "Editor" },
  { id: "agents", label: "Agent Settings" },
  { id: "references", label: "References" }
];

export function Workspace({ store }: WorkspaceProps) {
  const section = store.selectedSection;
  const [outlineCollapsed, setOutlineCollapsed] = useState(false);

  return (
    <main className={`workspace ${outlineCollapsed ? "is-outline-collapsed" : ""}`} aria-label="Book authoring workspace">
      <OutlinePane store={store} collapsed={outlineCollapsed} onToggleCollapsed={() => setOutlineCollapsed((value) => !value)} />
      <section className="editor-pane" aria-label="Section editor">
        <div className="tabs" role="tablist" aria-label="Editor views">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              className={`tab ${store.activeTab === tab.id ? "is-active" : ""}`}
              type="button"
              role="tab"
              aria-selected={store.activeTab === tab.id}
              onClick={() => store.setActiveTab(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </div>
        {store.activeTab === "editor" ? (
          <div className="section-meta">
            <div>
              <p className="eyebrow">Current section</p>
              <h2>{section?.title ?? "No section selected"}</h2>
            </div>
            <div className="meta-pills">
              <span className={`status-pill ${section?.tone === "good" ? "good" : "neutral"}`}>
                {section?.score == null ? "Not drafted" : `${section.score}% coherent`}
              </span>
              <span className="status-pill neutral">{section?.agent ?? "Queued"}</span>
            </div>
          </div>
        ) : null}
        {store.activeTab === "editor" ? <SectionEditor store={store} /> : null}
        {store.activeTab === "agents" ? (
          <section className="tab-panel detail-panel" aria-label="Agent settings and proposals">
            <AgentSettingsPanel state={store.state} />
            <ProposalReviewPanel proposals={store.state.proposals ?? []} onReview={store.reviewProposal} onRevise={store.reviseProposal} />
          </section>
        ) : null}
        {store.activeTab === "references" ? (
          <section className="tab-panel detail-panel" aria-label="References and artifacts">
            <ReferencesPanel references={store.state.references ?? []} knowledgeGraph={store.state.knowledgeGraph} />
            <ArtifactBrowser artifacts={store.state.artifacts ?? []} />
          </section>
        ) : null}
      </section>
      <PdfPreviewPane store={store} />
    </main>
  );
}

import type { KnowledgeGraphState, ReferenceEntry } from "../../api/types";

interface ReferencesPanelProps {
  references: ReferenceEntry[];
  knowledgeGraph?: KnowledgeGraphState;
}

export function ReferencesPanel({ references, knowledgeGraph }: ReferencesPanelProps) {
  const missingCitations = knowledgeGraph?.missing_citations ?? [];
  const invalidDependencies = knowledgeGraph?.invalid_dependencies ?? [];
  const cycles = knowledgeGraph?.circular_dependencies ?? [];
  const orphanClaims = knowledgeGraph?.orphan_claims ?? [];
  const conceptViz = knowledgeGraph?.concept_graph_visualization;
  const diagnosticCount = missingCitations.length + invalidDependencies.length + cycles.length + orphanClaims.length;

  return (
    <div className="reference-list">
      <div className="detail-section-title">
        <p className="eyebrow">References</p>
        <h3>{references.length} entries</h3>
      </div>
      <section className="graph-diagnostics" aria-label="Knowledge graph diagnostics">
        <div className="detail-section-title">
          <p className="eyebrow">Graph diagnostics</p>
          <h3>{diagnosticCount === 0 ? "No issues" : `${diagnosticCount} issues`}</h3>
        </div>
        <div className="diagnostic-grid">
          <DiagnosticList
            title="Missing citations"
            empty="All cited keys resolve."
            items={missingCitations.map((item) => `${item.ref_id} in ${item.section_id}${item.line ? `:${item.line}` : ""}`)}
          />
          <DiagnosticList
            title="Invalid dependencies"
            empty="All dependency targets exist."
            items={invalidDependencies.map((item) => `${item.section_id} -> ${item.dependency_id}`)}
          />
          <DiagnosticList
            title="Cycles"
            empty="No dependency cycles."
            items={cycles.map((cycle) => cycle.join(" -> "))}
          />
          <DiagnosticList
            title="Orphan claims"
            empty="No unsupported claim-like paragraphs."
            items={orphanClaims.map((item) => `${item.section_id}${item.line ? `:${item.line}` : ""} ${item.excerpt ?? item.reason ?? ""}`)}
          />
        </div>
      </section>
      {references.length === 0 ? <p className="empty-state">No structured references are attached to this book yet.</p> : null}
      {references.map((reference) => (
        <article className="reference-item" key={reference.id ?? reference.title}>
          <strong>{reference.title ?? reference.id ?? "Untitled reference"}</strong>
          <span>{reference.author ?? reference.year ?? reference.id ?? ""}</span>
        </article>
      ))}
      {conceptViz?.mermaid ? (
        <section className="concept-graph-preview" aria-label="Concept graph visualization">
          <div className="detail-section-title">
            <p className="eyebrow">Concept graph</p>
            <h3>{conceptViz.nodes?.length ?? 0} concepts</h3>
          </div>
          <pre>{conceptViz.mermaid}</pre>
        </section>
      ) : null}
    </div>
  );
}

function DiagnosticList({ title, empty, items }: { title: string; empty: string; items: string[] }) {
  return (
    <article className={`diagnostic-card ${items.length ? "has-issues" : ""}`}>
      <strong>{title}</strong>
      {items.length === 0 ? <span>{empty}</span> : null}
      {items.length > 0 ? (
        <ul>
          {items.slice(0, 5).map((item) => <li key={item}>{item}</li>)}
        </ul>
      ) : null}
    </article>
  );
}

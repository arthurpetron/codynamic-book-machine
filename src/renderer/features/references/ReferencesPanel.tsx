import type { ReferenceEntry } from "../../api/types";

interface ReferencesPanelProps {
  references: ReferenceEntry[];
}

export function ReferencesPanel({ references }: ReferencesPanelProps) {
  return (
    <div className="reference-list">
      <div className="detail-section-title">
        <p className="eyebrow">References</p>
        <h3>{references.length} entries</h3>
      </div>
      {references.length === 0 ? <p className="empty-state">No structured references are attached to this book yet.</p> : null}
      {references.map((reference) => (
        <article className="reference-item" key={reference.id ?? reference.title}>
          <strong>{reference.title ?? reference.id ?? "Untitled reference"}</strong>
          <span>{reference.author ?? reference.year ?? reference.id ?? ""}</span>
        </article>
      ))}
    </div>
  );
}

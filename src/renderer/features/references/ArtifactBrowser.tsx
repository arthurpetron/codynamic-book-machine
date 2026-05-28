import type { Artifact } from "../../api/types";

interface ArtifactBrowserProps {
  artifacts: Artifact[];
}

export function ArtifactBrowser({ artifacts }: ArtifactBrowserProps) {
  return (
    <div className="artifact-browser">
      <div className="detail-section-title">
        <p className="eyebrow">Artifacts</p>
        <h3>{artifacts.length} files</h3>
      </div>
      {artifacts.length === 0 ? <p className="empty-state">No compiled PDFs, media, or export artifacts are visible yet.</p> : null}
      {artifacts.map((artifact) => (
        <article className="artifact-item" key={artifact.artifact_id ?? artifact.path}>
          <strong>{artifact.title ?? artifact.label ?? artifact.path}</strong>
          <span>{artifact.kind ?? "artifact"} · {artifact.path}</span>
        </article>
      ))}
    </div>
  );
}

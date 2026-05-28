import type { useBookStore } from "../../state/bookStore";
import { CompileDiagnostics } from "./CompileDiagnostics";

interface PdfPreviewPaneProps {
  store: ReturnType<typeof useBookStore>;
}

function summarizeSource(source: string) {
  return source
    .split("\n")
    .map((line) => line.trim())
    .find((line) => line && !line.startsWith("\\")) || "This section is ready for drafting.";
}

function fileUrlFromPath(filePath: string) {
  return `file://${filePath.split("/").map((part) => encodeURIComponent(part)).join("/")}`;
}

export function PdfPreviewPane({ store }: PdfPreviewPaneProps) {
  const section = store.selectedSection;
  const result = store.compileResult;
  const styles = store.styles.length > 0 ? store.styles : store.state.styles ?? [];
  const styleId = store.state.design?.style_id ?? "standard_article";
  const pdfPath = result?.pdf_path || "";
  const pdfUrl = pdfPath ? fileUrlFromPath(pdfPath) : "";
  const compileStatus = store.isCompilingBook ? "Compiling" : result?.status ?? "Ready";

  return (
    <aside className="preview-pane" aria-label="Live PDF preview">
      <div className="preview-header">
        <div>
          <p className="eyebrow">Live PDF Preview</p>
          <h2>Compiled spread</h2>
        </div>
        <div className="preview-controls">
          <label className="style-picker">
            <span className="sr-only">Document style</span>
            <select value={styleId} onChange={(event) => store.setDocumentStyle(event.target.value)} aria-label="Document style">
              {styles.map((style) => (
                <option key={style.styleId ?? style.style_id} value={style.styleId ?? style.style_id}>
                  {style.label}
                </option>
              ))}
            </select>
          </label>
          <button className="secondary-action" type="button" onClick={store.compileBook} disabled={store.isCompilingBook}>
            {store.isCompilingBook ? "Compiling" : "Compile Book"}
          </button>
          <span className="compile-state">{compileStatus}</span>
        </div>
      </div>
      <div className="pdf-stage" aria-label="Vertical PDF preview scrollbox">
        {store.isCompilingBook ? (
          <div className="preview-placeholder">
            <strong>Compiling book</strong>
            <span>Running latexmk and refreshing the preview.</span>
          </div>
        ) : pdfUrl ? (
          <iframe className="pdf-frame" src={pdfUrl} title="Compiled PDF preview" />
        ) : result?.errors?.length ? (
          <CompileDiagnostics errors={result.errors} />
        ) : (
          <article className="pdf-page">
            <p className="pdf-kicker">Chapter 1</p>
            <h3>{section?.title ?? "No section selected"}</h3>
            <p>{summarizeSource(section?.source ?? "")}</p>
            <div className="equation">S(t + 1) = refine(S(t), I, E)</div>
            <p>The resulting document workflow mirrors the theory: outline, agents, dependencies, and compiled pages remain visible as one coordinated surface.</p>
          </article>
        )}
      </div>
    </aside>
  );
}

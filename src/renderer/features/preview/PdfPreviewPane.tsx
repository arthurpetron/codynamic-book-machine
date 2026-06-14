import { useEffect, useState } from "react";
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

export function PdfPreviewPane({ store }: PdfPreviewPaneProps) {
  const section = store.selectedSection;
  const result = store.compileResult;
  const [pdfDataUrl, setPdfDataUrl] = useState("");
  const [pdfLoadError, setPdfLoadError] = useState("");
  const styles = store.styles.length > 0 ? store.styles : store.state.styles ?? [];
  const styleId = String(store.state.design?.style_id ?? "standard_article");
  const titlePageEnabled = Boolean(store.state.design?.title_page_enabled);
  const tocEnabled = Boolean(store.state.design?.table_of_contents_enabled);
  const pdfPath = result?.pdf_path || "";
  const isCompiling = store.isCompilingBook || store.isCompilingSection;
  const compileStatus = isCompiling ? "Compiling" : result?.status ?? "Ready";
  const errors = result?.errors ?? [];
  const hasCompileErrors = errors.length > 0 || result?.status === "failed";
  const responsibleSections = result?.responsible_section_titles ?? [];
  const fallbackDiagnostic = responsibleSections.length > 0
    ? `Compile failed in ${responsibleSections.join(", ")}. See the compile log for details.`
    : "Compile failed. See the compile log for details.";
  const diagnostics = result?.diagnostic_summary
    ? [result.diagnostic_summary, ...errors.slice(1)]
    : errors.length > 0
      ? errors
      : [fallbackDiagnostic];
  const pdfVersion = result?.log_path ?? `${compileStatus}:${pdfPath}`;

  useEffect(() => {
    let cancelled = false;
    setPdfDataUrl("");
    setPdfLoadError("");
    if (!pdfPath || hasCompileErrors || isCompiling) {
      return () => {
        cancelled = true;
      };
    }
    store.api.app.pdfDataUrl(pdfPath)
      .then((dataUrl) => {
        if (!cancelled) {
          setPdfDataUrl(dataUrl);
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setPdfLoadError((error as Error).message);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [store.api, pdfPath, pdfVersion, hasCompileErrors, isCompiling]);

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
          <label className="preview-toggle">
            <input
              type="checkbox"
              checked={titlePageEnabled}
              onChange={(event) => store.updateDesignSettings({ title_page_enabled: event.target.checked })}
            />
            <span>Title page</span>
          </label>
          <label className="preview-toggle">
            <input
              type="checkbox"
              checked={tocEnabled}
              onChange={(event) => store.updateDesignSettings({ table_of_contents_enabled: event.target.checked })}
            />
            <span>TOC</span>
          </label>
          <button className="secondary-action" type="button" onClick={store.compileBook} disabled={store.isCompilingBook}>
            {store.isCompilingBook ? "Compiling" : "Compile Book"}
          </button>
          <span className={`compile-state ${compileStatus}`}>{compileStatus}</span>
        </div>
      </div>
      <div className="compile-panel" aria-label="Compile status and history">
        <div className="compile-panel-row">
          <strong>{compileStatus}</strong>
          <span>{pdfPath ? pdfPath.split("/").at(-1) : "No compiled PDF loaded yet"}</span>
        </div>
        {hasCompileErrors ? (
          <div className="compile-error-summary">
            <strong>{Math.max(errors.length, 1)} compile issue{errors.length === 1 ? "" : "s"}</strong>
            <span>{diagnostics[0]}</span>
          </div>
        ) : null}
        {store.compileHistory.length > 0 ? (
          <ol className="compile-history" aria-label="Compile history">
            {store.compileHistory.map((item) => (
              <li key={item.id}>
                <span>{item.createdAt}</span>
                <strong>{item.target}</strong>
                <em>{item.status}</em>
                {item.errors > 0 ? <b>{item.errors} errors</b> : null}
              </li>
            ))}
          </ol>
        ) : null}
      </div>
      <div className="pdf-stage" aria-label="Vertical PDF preview scrollbox">
        {isCompiling ? (
          <div className="preview-placeholder">
            <strong>Compiling {store.isCompilingBook ? "book" : "section"}</strong>
            <span>Running latexmk and refreshing the preview.</span>
          </div>
        ) : hasCompileErrors ? (
          <CompileDiagnostics errors={diagnostics} />
        ) : pdfLoadError ? (
          <CompileDiagnostics errors={[`PDF preview failed to load: ${pdfLoadError}`]} />
        ) : pdfDataUrl ? (
          <iframe key={pdfVersion} className="pdf-frame" src={pdfDataUrl} title="Compiled PDF preview" />
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

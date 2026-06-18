interface EditorToolbarProps {
  isCompiling: boolean;
  liveSync: boolean;
  onLiveSyncChange: (enabled: boolean) => void;
  onSave: () => void;
  onCompile: () => void;
  onInsertCitation: () => void;
}

export function EditorToolbar({
  isCompiling,
  liveSync,
  onLiveSyncChange,
  onSave,
  onCompile,
  onInsertCitation
}: EditorToolbarProps) {
  return (
    <div className="editor-toolbar" aria-label="Editor toolbar">
      <button type="button" title="Save section" onClick={onSave}>Save</button>
      <button type="button" title="Compile selected section" onClick={onCompile} disabled={isCompiling}>
        {isCompiling ? "Compiling" : "Compile"}
      </button>
      <button type="button" title="Insert citation placeholder" onClick={onInsertCitation}>Cite</button>
      <span className="toolbar-spacer" />
      <label className="toggle">
        <input type="checkbox" checked={liveSync} onChange={(event) => onLiveSyncChange(event.target.checked)} />
        <span>Live sync</span>
      </label>
    </div>
  );
}

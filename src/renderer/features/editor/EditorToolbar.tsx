interface EditorToolbarProps {
  isCompiling: boolean;
  onCompile: () => void;
}

export function EditorToolbar({ isCompiling, onCompile }: EditorToolbarProps) {
  return (
    <div className="editor-toolbar" aria-label="Editor toolbar">
      <button type="button" title="Bold">B</button>
      <button type="button" title="Italic">I</button>
      <button type="button" title="Insert citation">Cite</button>
      <button type="button" title="Compile selected section" onClick={onCompile} disabled={isCompiling}>
        {isCompiling ? "Compiling" : "Compile"}
      </button>
      <span className="toolbar-spacer" />
      <label className="toggle">
        <input type="checkbox" defaultChecked />
        <span>Live sync</span>
      </label>
    </div>
  );
}

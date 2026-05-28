import { useEffect, useMemo, useRef, useState } from "react";
import type { useBookStore } from "../../state/bookStore";
import { EditorToolbar } from "./EditorToolbar";

interface SectionEditorProps {
  store: ReturnType<typeof useBookStore>;
}

export function SectionEditor({ store }: SectionEditorProps) {
  const [source, setSource] = useState(store.selectedSection?.source ?? "");
  const [liveSync, setLiveSync] = useState(true);
  const [isDirty, setIsDirty] = useState(false);
  const [isCompiling, setIsCompiling] = useState(false);
  const gutterRef = useRef<HTMLDivElement | null>(null);
  const lineNumbers = useMemo(() => {
    const count = Math.max(1, source.split("\n").length);
    return Array.from({ length: count }, (_, index) => index + 1);
  }, [source]);

  useEffect(() => {
    setSource(store.selectedSection?.source ?? "");
    setIsDirty(false);
  }, [store.selectedSection?.id, store.selectedSection?.source]);

  useEffect(() => {
    if (!liveSync || !isDirty || !store.selectedId || isCompiling || store.isCompilingSection) {
      return;
    }
    const timeout = window.setTimeout(() => {
      compile();
    }, 1800);
    return () => window.clearTimeout(timeout);
  }, [source, liveSync, isDirty, store.selectedId, isCompiling, store.isCompilingSection]);

  async function compile() {
    setIsCompiling(true);
    try {
      await store.compileSection(source);
      setIsDirty(false);
    } finally {
      setIsCompiling(false);
    }
  }

  return (
    <section className="tab-panel text-editor is-active" aria-label="LaTeX text editor">
      <EditorToolbar
        isCompiling={isCompiling || store.isCompilingSection}
        liveSync={liveSync}
        onLiveSyncChange={setLiveSync}
        onSave={() => {
          store.saveSection(source);
          setIsDirty(false);
        }}
        onCompile={compile}
      />
      <div className="source-editor">
        <div className="line-gutter" ref={gutterRef} aria-hidden="true">
          {lineNumbers.map((line) => <span key={line}>{line}</span>)}
        </div>
        <textarea
          value={source}
          onChange={(event) => {
            setSource(event.target.value);
            setIsDirty(true);
          }}
          onScroll={(event) => {
            if (gutterRef.current) {
              gutterRef.current.scrollTop = event.currentTarget.scrollTop;
            }
          }}
          onBlur={() => {
            if (isDirty) {
              store.saveSection(source);
            }
          }}
          onKeyDown={(event) => {
            if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "s") {
              event.preventDefault();
              store.saveSection(source);
            }
          }}
          spellCheck={false}
          aria-label="LaTeX source"
        />
      </div>
    </section>
  );
}

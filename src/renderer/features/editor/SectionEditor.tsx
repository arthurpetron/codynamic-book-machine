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
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const lastSavedSourceRef = useRef(store.selectedSection?.source ?? "");
  const lastCompiledSourceRef = useRef(store.selectedSection?.source ?? "");
  const lineNumbers = useMemo(() => {
    const count = Math.max(1, source.split("\n").length);
    return Array.from({ length: count }, (_, index) => index + 1);
  }, [source]);

  useEffect(() => {
    setSource(store.selectedSection?.source ?? "");
    lastSavedSourceRef.current = store.selectedSection?.source ?? "";
    lastCompiledSourceRef.current = store.selectedSection?.source ?? "";
    setIsDirty(false);
  }, [store.selectedSection?.id, store.selectedSection?.source]);

  useEffect(() => {
    if (!isDirty || !store.selectedId || source === lastSavedSourceRef.current) {
      return;
    }
    const timeout = window.setTimeout(() => {
      void store.saveSection(source).then(() => {
        lastSavedSourceRef.current = source;
      });
    }, 500);
    return () => window.clearTimeout(timeout);
  }, [source, isDirty, store.selectedId, store.saveSection]);

  useEffect(() => {
    if (!liveSync || !store.selectedId || source === lastCompiledSourceRef.current || isCompiling || store.isCompilingSection) {
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
      lastSavedSourceRef.current = source;
      lastCompiledSourceRef.current = source;
      setIsDirty(false);
    } finally {
      setIsCompiling(false);
    }
  }

  function insertCitationPlaceholder() {
    const citation = "\\cite{todo-citation}";
    const textarea = textareaRef.current;
    const start = textarea?.selectionStart ?? source.length;
    const end = textarea?.selectionEnd ?? source.length;
    const nextSource = `${source.slice(0, start)}${citation}${source.slice(end)}`;
    setSource(nextSource);
    setIsDirty(true);
    window.requestAnimationFrame(() => {
      textarea?.focus();
      textarea?.setSelectionRange(start + citation.length, start + citation.length);
    });
  }

  return (
    <section className="tab-panel text-editor is-active" aria-label="LaTeX text editor">
      <EditorToolbar
        isCompiling={isCompiling || store.isCompilingSection}
        liveSync={liveSync}
        onLiveSyncChange={setLiveSync}
        onSave={() => {
          void store.saveSection(source).then(() => {
            lastSavedSourceRef.current = source;
          });
          setIsDirty(false);
        }}
        onCompile={compile}
        onInsertCitation={insertCitationPlaceholder}
      />
      <div className="source-editor">
        <div className="line-gutter" ref={gutterRef} aria-hidden="true">
          {lineNumbers.map((line) => <span key={line}>{line}</span>)}
        </div>
        <textarea
          ref={textareaRef}
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
            if (isDirty && source !== lastSavedSourceRef.current) {
              void store.saveSection(source).then(() => {
                lastSavedSourceRef.current = source;
              });
            }
          }}
          onKeyDown={(event) => {
            if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "s") {
              event.preventDefault();
              void store.saveSection(source).then(() => {
                lastSavedSourceRef.current = source;
              });
              setIsDirty(false);
            }
          }}
          spellCheck={false}
          aria-label="LaTeX source"
        />
      </div>
    </section>
  );
}

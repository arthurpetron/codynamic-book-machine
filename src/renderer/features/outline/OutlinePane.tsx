import { useMemo, useState } from "react";
import type { useBookStore } from "../../state/bookStore";
import { NewSectionDialog } from "./NewSectionDialog";
import { OutlineTree } from "./OutlineTree";

interface OutlinePaneProps {
  store: ReturnType<typeof useBookStore>;
  collapsed: boolean;
  onToggleCollapsed: () => void;
}

export function OutlinePane({ store, collapsed, onToggleCollapsed }: OutlinePaneProps) {
  const [filter, setFilter] = useState("");
  const [isCreating, setIsCreating] = useState(false);
  const [isCreatingChapter, setIsCreatingChapter] = useState(false);
  const currentChapter = useMemo(() => {
    return store.state.outline.find((chapter) => chapter.items.some((item) => item.id === store.selectedId)) ?? store.state.outline[0];
  }, [store.state.outline, store.selectedId]);

  if (collapsed) {
    return (
      <aside className="outline-pane is-collapsed" aria-label="Outline">
        <button className="icon-button outline-restore-button" type="button" aria-label="Expand outline" title="Expand outline" onClick={onToggleCollapsed}>
          Outline
        </button>
      </aside>
    );
  }

  return (
    <aside className="outline-pane" aria-label="Outline">
      <div className="pane-header">
        <div>
          <p className="eyebrow">Outline</p>
          <h1>{store.state.book?.title ?? "Untitled Book"}</h1>
        </div>
        <button className="icon-button" type="button" aria-label="Collapse outline" title="Collapse outline" onClick={onToggleCollapsed}>-</button>
      </div>
      <div className="outline-tools">
        <label className="search-field">
          <span className="sr-only">Search outline</span>
          <input value={filter} onChange={(event) => setFilter(event.target.value)} type="search" placeholder="Search outline" />
        </label>
        <button className="primary-action" type="button" onClick={() => setIsCreating(true)}>New Section</button>
      </div>
      <div className="outline-secondary-tools">
        <button className="secondary-action" type="button" onClick={() => setIsCreatingChapter(true)}>New Chapter</button>
      </div>
      {isCreatingChapter ? (
        <NewSectionDialog
          parentTitle="book"
          onCancel={() => setIsCreatingChapter(false)}
          onCreate={async (title) => {
            await store.createChapter(title);
            setIsCreatingChapter(false);
          }}
        />
      ) : null}
      {isCreating ? (
        <NewSectionDialog
          parentTitle={currentChapter?.title}
          onCancel={() => setIsCreating(false)}
          onCreate={async (title) => {
            await store.createSection(currentChapter?.id, title);
            setIsCreating(false);
          }}
        />
      ) : null}
      <OutlineTree
        chapters={store.state.outline}
        selectedId={store.selectedId}
        filter={filter}
        onSelect={store.selectSection}
        agentRunState={store.sectionAgentRunState}
        onStartAgent={store.startSectionAgent}
        onOpenChat={store.openSectionAgentChat}
        onRename={async (nodeId, title) => {
          if (title.trim()) {
            await store.updateOutlineNode(nodeId, title.trim());
          }
        }}
      />
    </aside>
  );
}

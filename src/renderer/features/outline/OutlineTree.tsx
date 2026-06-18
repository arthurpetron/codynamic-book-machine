import { useState } from "react";
import type { OutlineChapter } from "../../api/types";
import type { SectionAgentRunState } from "../../state/bookStore";

interface OutlineTreeProps {
  chapters: OutlineChapter[];
  selectedId: string | null;
  filter: string;
  agentRunState: Record<string, SectionAgentRunState>;
  onSelect: (sectionId: string) => void;
  onStartAgent: (sectionId: string) => Promise<void>;
  onOpenChat: (sectionId: string, title: string) => Promise<void>;
  onRename: (nodeId: string, currentTitle: string) => void | Promise<void>;
}

export function OutlineTree({ chapters, selectedId, filter, agentRunState, onSelect, onStartAgent, onOpenChat, onRename }: OutlineTreeProps) {
  const normalized = filter.trim().toLowerCase();
  const [editing, setEditing] = useState<{ id: string; value: string } | null>(null);
  const [chapterExpansion, setChapterExpansion] = useState<Record<string, boolean>>({});
  const [openMenuId, setOpenMenuId] = useState<string | null>(null);

  async function commitEdit() {
    if (!editing) {
      return;
    }
    const nextTitle = editing.value.trim();
    const nodeId = editing.id;
    setEditing(null);
    if (nextTitle) {
      await onRename(nodeId, nextTitle);
    }
  }

  function titleEditor(nodeId: string, title: string, className: string) {
    if (editing?.id === nodeId) {
      return (
        <input
          className={`${className} inline-title-input`}
          value={editing.value}
          autoFocus
          onChange={(event) => setEditing({ id: nodeId, value: event.target.value })}
          onBlur={commitEdit}
          onClick={(event) => event.stopPropagation()}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              commitEdit();
            }
            if (event.key === "Escape") {
              event.preventDefault();
              setEditing(null);
            }
          }}
        />
      );
    }
    return (
      <span
        className={className}
        role="button"
        tabIndex={0}
        title="Click to rename"
        onClick={(event) => {
          event.stopPropagation();
          setEditing({ id: nodeId, value: title });
        }}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.preventDefault();
            setEditing({ id: nodeId, value: title });
          }
        }}
      >
        {title}
      </span>
    );
  }

  return (
    <div className="outline-tree" role="tree" aria-label="Book outline">
      {chapters.map((chapter) => {
        const chapterId = chapter.id ?? chapter.title;
        const isExpanded = Boolean(normalized) || (chapterExpansion[chapterId] ?? chapter.expanded !== false);
        const visibleItems = chapter.items.filter((item) => {
          return !normalized || `${chapter.title} ${item.number ?? ""} ${item.title}`.toLowerCase().includes(normalized);
        });
        if (normalized && visibleItems.length === 0) {
          return null;
        }
        return (
          <section className="chapter" key={chapter.id ?? chapter.title}>
            <button
              className="chapter-toggle"
              type="button"
              aria-expanded={isExpanded}
              onClick={() => {
                setChapterExpansion((current) => ({ ...current, [chapterId]: !isExpanded }));
              }}
            >
              <span>{isExpanded ? "v" : ">"}</span>
              {chapter.id ? titleEditor(chapter.id, chapter.title, "chapter-title") : <span>{chapter.chapter}: {chapter.title}</span>}
            </button>
            {isExpanded ? <ul className="section-list">
              {visibleItems.map((item) => (
                <li key={item.id}>
                  {(() => {
                    const runState = agentRunState[item.id] ?? "not-started";
                    const scoreLabel = runState === "working" ? "Running" : item.score == null ? "--" : `${item.score}%`;
                    return (
                      <>
                  <button
                    type="button"
                    className={`section-item ${item.id === selectedId ? "is-active" : ""}`}
                    role="treeitem"
                    aria-selected={item.id === selectedId}
                    onClick={() => onSelect(item.id)}
                  >
                    <span className="section-name-prefix">{item.number ? `${item.number} ` : ""}</span>
                    {titleEditor(item.id, item.title, "section-name")}
                  </button>
                  <span
                    className={`score agent-state ${runState}`}
                    title={`Agent state: ${runState}`}
                    aria-label={`Agent state: ${runState}`}
                  >
                    {scoreLabel}
                  </span>
                  <div className="outline-row-menu">
                    <button
                      type="button"
                      className="outline-menu-button"
                      aria-label={`Actions for ${item.title}`}
                      aria-expanded={openMenuId === item.id}
                      title="Section actions"
                      onClick={() => setOpenMenuId((current) => current === item.id ? null : item.id)}
                    >
                      ...
                    </button>
                    <div className={`outline-row-menu-panel ${openMenuId === item.id ? "is-open" : ""}`} role="menu">
                      <button
                        type="button"
                        role="menuitem"
                        disabled={agentRunState[item.id] === "working"}
                        onClick={() => {
                          setOpenMenuId(null);
                          onStartAgent(item.id);
                        }}
                      >
                        {runState === "working" ? "Working" : "Start Agent"}
                      </button>
                      <button
                        type="button"
                        role="menuitem"
                        onClick={() => {
                          setOpenMenuId(null);
                          onOpenChat(item.id, item.title);
                        }}
                      >
                        Chat
                      </button>
                    </div>
                  </div>
                      </>
                    );
                  })()}
                </li>
              ))}
            </ul> : null}
          </section>
        );
      })}
    </div>
  );
}

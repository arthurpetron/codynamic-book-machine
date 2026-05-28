import type { OutlineChapter } from "../../api/types";

interface OutlineTreeProps {
  chapters: OutlineChapter[];
  selectedId: string | null;
  filter: string;
  onSelect: (sectionId: string) => void;
}

export function OutlineTree({ chapters, selectedId, filter, onSelect }: OutlineTreeProps) {
  const normalized = filter.trim().toLowerCase();

  return (
    <div className="outline-tree" role="tree" aria-label="Book outline">
      {chapters.map((chapter) => {
        const visibleItems = chapter.items.filter((item) => {
          return !normalized || `${chapter.title} ${item.number ?? ""} ${item.title}`.toLowerCase().includes(normalized);
        });
        if (normalized && visibleItems.length === 0) {
          return null;
        }
        return (
          <section className="chapter" key={chapter.id ?? chapter.title}>
            <button className="chapter-toggle" type="button">
              <span>{chapter.expanded || normalized ? "v" : ">"}</span>
              <span>{chapter.chapter}: {chapter.title}</span>
            </button>
            <ul className="section-list">
              {visibleItems.map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    className={`section-item ${item.id === selectedId ? "is-active" : ""}`}
                    role="treeitem"
                    aria-selected={item.id === selectedId}
                    onClick={() => onSelect(item.id)}
                  >
                    <span className="section-name">{item.number ? `${item.number} ` : ""}{item.title}</span>
                    <span className={`score ${item.tone ?? "idle"}`}>{item.score == null ? "--" : `${item.score}%`}</span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        );
      })}
    </div>
  );
}

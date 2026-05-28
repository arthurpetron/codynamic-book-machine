import { useState } from "react";
import { BookCommands } from "../../features/library/BookCommands";
import type { useBookStore } from "../../state/bookStore";

interface MenuBarProps {
  store: ReturnType<typeof useBookStore>;
}

export function MenuBar({ store }: MenuBarProps) {
  const [showCommands, setShowCommands] = useState(false);

  return (
    <header className="titlebar" aria-label="Application menu">
      <div className="traffic-lights" aria-hidden="true">
        <span className="light red" />
        <span className="light amber" />
        <span className="light green" />
      </div>
      <nav className="menu" aria-label="Primary">
        <button type="button" onClick={() => setShowCommands((open) => !open)}>File</button>
        <button type="button">Edit</button>
        <button type="button">Review</button>
        <button type="button" onClick={() => store.setActiveTab("agents")}>Agents</button>
        <button type="button">Export</button>
        <button type="button">Git</button>
        <button type="button">Help</button>
      </nav>
      {showCommands ? <BookCommands store={store} onClose={() => setShowCommands(false)} /> : null}
      <div className="user-badge" aria-label="Signed in user">
        <span className="avatar">AP</span>
        <span>Arthur</span>
        <button className="user-chat-button" type="button" aria-label="Pending user chat messages">
          User Chat
          <span className="queue-badge">0</span>
        </button>
      </div>
    </header>
  );
}

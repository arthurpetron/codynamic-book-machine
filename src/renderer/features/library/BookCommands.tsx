import { useState } from "react";
import type { useBookStore } from "../../state/bookStore";
import { useBookLibrary } from "./useBookLibrary";

interface BookCommandsProps {
  store: ReturnType<typeof useBookStore>;
  onClose: () => void;
}

export function BookCommands({ store, onClose }: BookCommandsProps) {
  const { library, openBook, newBook } = useBookLibrary();
  const [title, setTitle] = useState("");

  async function createBook() {
    const name = title.trim() || `Untitled Book ${new Date().toISOString().slice(0, 10)}`;
    await newBook(name);
    await store.loadState(null);
    onClose();
  }

  async function chooseBook(bookId: string) {
    await openBook(bookId);
    await store.loadState(null);
    onClose();
  }

  return (
    <div className="command-popover" role="dialog" aria-label="Book commands">
      <div className="command-row">
        <input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="New book title" />
        <button className="primary-action" type="button" onClick={createBook}>New</button>
      </div>
      <div className="command-list">
        {library.books.length === 0 ? <p className="empty-state">No registered books.</p> : null}
        {library.books.map((book) => (
          <button
            key={book.book_id}
            className={book.book_id === library.active ? "command-item is-active" : "command-item"}
            type="button"
            onClick={() => chooseBook(book.book_id)}
          >
            <span>{book.title}</span>
            <small>{book.status}</small>
          </button>
        ))}
      </div>
    </div>
  );
}

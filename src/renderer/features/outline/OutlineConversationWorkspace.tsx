import { useMemo, useState } from "react";
import type { OutlineConversationMessage } from "../../api/types";
import type { useBookStore } from "../../state/bookStore";

interface OutlineConversationWorkspaceProps {
  store: ReturnType<typeof useBookStore>;
}

const starterMessages: OutlineConversationMessage[] = [
  {
    role: "assistant",
    content: "What book are we making, who is it for, and what should be true for the reader by the end?",
    createdAt: new Date().toISOString()
  }
];

export function OutlineConversationWorkspace({ store }: OutlineConversationWorkspaceProps) {
  const [messages, setMessages] = useState<OutlineConversationMessage[]>(starterMessages);
  const [draft, setDraft] = useState("");
  const [useLlm, setUseLlm] = useState<"auto" | "always" | "never">("auto");
  const [isCreating, setIsCreating] = useState(false);
  const [resultText, setResultText] = useState("");

  const canCreate = useMemo(
    () => messages.some((message) => message.role === "user" && message.content.trim().length > 0),
    [messages]
  );

  function sendMessage() {
    const content = draft.trim();
    if (!content) {
      return;
    }
    setMessages((current) => [
      ...current,
      { role: "user", content, createdAt: new Date().toISOString() },
      {
        role: "assistant",
        content: nextPrompt(content),
        createdAt: new Date().toISOString()
      }
    ]);
    setDraft("");
  }

  async function createOutline() {
    if (!canCreate || isCreating) {
      return;
    }
    setIsCreating(true);
    setResultText("");
    try {
      const result = await store.createBookFromOutlineConversation(messages, useLlm);
      if (result?.error) {
        setResultText(result.error);
      } else {
        setResultText(result?.message || "Created book from conversation.");
      }
    } catch (error) {
      setResultText((error as Error).message);
    } finally {
      setIsCreating(false);
    }
  }

  return (
    <main className="conversation-workspace" aria-label="Outline conversation workspace">
      <section className="conversation-thread" aria-label="Conversation">
        <div className="conversation-topbar">
          <div>
            <p className="eyebrow">File</p>
            <h1>New Book from Outline Conversation</h1>
          </div>
          <button className="secondary-action" type="button" onClick={store.closeOutlineConversation}>
            Back to Book
          </button>
        </div>
        <div className="chat-scroll" aria-live="polite">
          {messages.map((message, index) => (
            <article key={`${message.role}-${index}`} className={`chat-message ${message.role}`}>
              <span>{message.role === "user" ? "You" : "CBM"}</span>
              <p>{message.content}</p>
            </article>
          ))}
        </div>
        <div className="chat-composer">
          <textarea
            value={draft}
            rows={4}
            placeholder="Describe the book, argument, audience, structure, sources, diagrams, and constraints."
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
                sendMessage();
              }
            }}
          />
          <button className="primary-action" type="button" onClick={sendMessage} disabled={!draft.trim()}>
            Send
          </button>
        </div>
      </section>
      <aside className="conversation-actions" aria-label="Outline creation">
        <div className="conversation-action-panel">
          <p className="eyebrow">Synthesis</p>
          <h2>Conversation to Outline</h2>
          <label className="field-label" htmlFor="outline-llm-mode">LLM mode</label>
          <select id="outline-llm-mode" value={useLlm} onChange={(event) => setUseLlm(event.target.value as typeof useLlm)}>
            <option value="auto">Auto</option>
            <option value="always">Require LLM</option>
            <option value="never">Deterministic</option>
          </select>
          <button className="primary-action wide" type="button" onClick={createOutline} disabled={!canCreate || isCreating}>
            {isCreating ? "Creating..." : "Create Outline from Conversation"}
          </button>
          {resultText ? <p className="conversation-result">{resultText}</p> : null}
        </div>
      </aside>
    </main>
  );
}

function nextPrompt(content: string): string {
  const lower = content.toLowerCase();
  if (!lower.includes("audience") && !lower.includes("reader")) {
    return "Who is the reader, and what do they already understand before opening the book?";
  }
  if (!lower.includes("chapter") && !lower.includes("structure") && !lower.includes("section")) {
    return "What major parts or chapters should the book probably contain?";
  }
  if (!lower.includes("diagram") && !lower.includes("figure") && !lower.includes("visual")) {
    return "What visuals, diagrams, citations, or supporting artifacts should the outline reserve space for?";
  }
  return "What constraints, open questions, or source materials should the outline preserve?";
}

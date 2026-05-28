import { useEffect, useMemo, useState } from "react";
import type { UserChatMessage } from "../../api/types";
import type { useBookStore } from "../../state/bookStore";

interface AgentConsoleProps {
  store: ReturnType<typeof useBookStore>;
}

export function AgentConsole({ store }: AgentConsoleProps) {
  const [collapsed, setCollapsed] = useState(false);
  const [userMessages, setUserMessages] = useState<UserChatMessage[]>([]);
  const [reply, setReply] = useState("");
  const status = store.state.agentStatus;
  const messages = useMemo(() => [...store.activityMessages, ...(store.state.messages ?? [])].slice(0, 40), [store.activityMessages, store.state.messages]);
  const pending = userMessages.filter((message) => message.status === "pending");

  useEffect(() => {
    store.api.userChat?.list().then(setUserMessages).catch(() => setUserMessages([]));
  }, [store.api]);

  async function answer(messageId: string) {
    if (!reply.trim() || !store.api.userChat) {
      return;
    }
    await store.api.userChat.answer(messageId, reply.trim());
    setReply("");
    setUserMessages(await store.api.userChat.list());
  }

  async function dismiss(messageId: string) {
    if (!store.api.userChat) {
      return;
    }
    await store.api.userChat.dismiss(messageId);
    setUserMessages(await store.api.userChat.list());
  }

  return (
    <footer className="agent-console" aria-label="Agent console">
      <div className="agent-status">
        <div className="health-card">
          <span className="dot good" />
          <span>Hypervisor</span>
          <strong>{status?.confidence ?? 0}%</strong>
        </div>
        <div className="health-card">
          <span>Active</span>
          <strong>{status?.active ?? 0}/{status?.total ?? 1}</strong>
        </div>
        <div className="health-card">
          <span>Confidence</span>
          <strong>{status?.confidence ?? 0}%</strong>
        </div>
        <button className="secondary-action" type="button">Pause Swarm</button>
        <button className="primary-action" type="button" onClick={store.requestReview}>Request Full Review</button>
        <button className="icon-button" type="button" aria-expanded={!collapsed} onClick={() => setCollapsed((value) => !value)}>{collapsed ? "v" : "^"}</button>
      </div>
      {!collapsed ? (
        <div className="chat-panels">
          <section className="user-chat-panel" aria-label="User chat requests">
            <div className="chat-title">User Chat</div>
            <ol className="user-chat-list">
              {pending.length === 0 ? <li className="user-chat-empty">No user questions queued.</li> : null}
              {pending.map((message) => (
                <li className="user-chat-item pending" key={message.message_id}>
                  <div className="user-chat-header">
                    <strong>{message.subject}</strong>
                    <span>{message.from_agent ?? "agent"}</span>
                  </div>
                  <p>{message.body}</p>
                  <div className="user-chat-reply">
                    <textarea rows={2} value={reply} onChange={(event) => setReply(event.target.value)} placeholder="Reply to agent" />
                    <div className="user-chat-actions">
                      <button className="secondary-action" type="button" onClick={() => dismiss(message.message_id)}>Dismiss</button>
                      <button className="primary-action" type="button" onClick={() => answer(message.message_id)}>Send</button>
                    </div>
                  </div>
                </li>
              ))}
            </ol>
          </section>
          <section className="chat-log" aria-label="Inter-agent chat log">
            <div className="chat-title">Inter-agent chat log</div>
            <ol className="messages">
              {messages.map(([time, source, text], index) => (
                <li className="message" key={`${time}-${source}-${index}`}>
                  <span className="message-time">{time}</span>
                  <span className="message-source">{source}</span>
                  <span className="message-text">{text}</span>
                </li>
              ))}
            </ol>
          </section>
        </div>
      ) : null}
    </footer>
  );
}

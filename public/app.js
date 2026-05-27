const fallbackSections = [
  {
    chapter: "Chapter 1",
    title: "Foundations of Structure",
    expanded: true,
    items: [
      {
        id: "ch01_sec01",
        number: "1.1",
        title: "From Static to Codynamic",
        score: 94,
        tone: "good",
        agent: "Section-1.1 active",
        source: String.raw`\section{From Static to Codynamic}

Traditional static models fix the shape of a system before its interaction with the world is known. A codynamic model begins differently: structure is treated as something revised by local constraints, feedback, and intent.

\subsection{The constructive stance}
The authoring system mirrors this principle. The outline provides typed intent, section agents propose local refinements, gardeners validate coherence, and the hypervisor monitors drift across the whole work.

\[
  S(t + 1) = \operatorname{refine}(S(t), I, E)
\]

The important shift is not that structure disappears. It is that structure becomes accountable to the next interaction.`
      },
      {
        id: "ch01_sec02",
        number: "1.2",
        title: "Recursive Energy Paths",
        score: 67,
        tone: "warn",
        agent: "Gardener-02 reviewing",
        source: String.raw`\section{Recursive Energy Paths}

Energy, learning, and motion are locally reconfigurable. A path through the system is not only a trajectory; it is a record of constraints being selected, tested, and folded back into structure.

\subsection{Local revision}
The next pass should connect this section more explicitly to the dependency language in the outline schema.`
      }
    ]
  },
  {
    chapter: "Chapter 2",
    title: "Expressing Systems in Space and Time",
    expanded: true,
    items: [
      {
        id: "ch02_sec01",
        number: "2.1",
        title: "Typed Intent and Locality",
        score: null,
        tone: "idle",
        agent: "Queued",
        source: String.raw`\section{Typed Intent and Locality}

This section is queued for drafting. It should introduce the formal vocabulary used to describe codynamic systems across time, context, and local action.`
      },
      {
        id: "ch02_sec02",
        number: "2.2",
        title: "Monoidal Composition",
        score: 62,
        tone: "warn",
        agent: "Section-2.2 active",
        source: String.raw`\section{Monoidal Composition}

Composition lets independent local operations assemble into a coherent transformation. The current draft needs stronger examples and a clearer transition into document assembly.`
      }
    ]
  },
  {
    chapter: "Chapter 3",
    title: "Agents as Morphisms",
    expanded: false,
    items: [
      {
        id: "ch03_sec01",
        number: "3.1",
        title: "Section Agents",
        score: 80,
        tone: "good",
        agent: "Ready",
        source: String.raw`\section{Section Agents}

Section agents transform intent into local prose, notation, and reviewable claims.`
      },
      {
        id: "ch03_sec02",
        number: "3.2",
        title: "Gardener Validation",
        score: 78,
        tone: "good",
        agent: "Ready",
        source: String.raw`\section{Gardener Validation}

Gardener agents validate that local edits preserve the intended global structure.`
      }
    ]
  }
];

let sections = fallbackSections;

const fallbackMessages = [
  ["12:04", "Hypervisor -> All", "Coherence drop in 1.2; request dependency check from Outline Agent."],
  ["12:03", "Gardener-02 -> Section-1.2", "Validated. Minor drift around local reconfiguration language."],
  ["12:01", "Section 1.1 -> Hypervisor", "Completed: update static model contrast with new paragraph."],
  ["11:58", "Outline Agent -> Section-2.1", "Queued formal vocabulary pass after 1.2 stabilizes."]
];

const fallbackUserChat = [
  {
    message_id: "demo_user_msg_1",
    from_agent: "hypervisor_agent",
    subject: "Confirm next review target",
    body: "Several agents are ready to proceed. Which section should receive the next coordinated review?",
    status: "pending",
    created_at: new Date().toISOString()
  }
];

const root = document.getElementById("root");
const outlineTree = document.getElementById("outline-tree");
const search = document.getElementById("outline-search");
const editor = document.getElementById("latex-editor");
const title = document.getElementById("section-title");
const previewTitle = document.getElementById("pdf-heading");
const previewCopy = document.getElementById("pdf-copy");
const pdfStage = document.querySelector(".pdf-stage");
const sectionStatus = document.getElementById("section-status");
const sectionAgent = document.getElementById("section-agent");
const confidence = document.getElementById("confidence-score");
const messagesList = document.getElementById("messages");
const toggleChat = document.getElementById("toggle-chat");
const pauseSwarm = document.getElementById("pause-swarm");
const requestReview = document.getElementById("request-review");
const userChatButton = document.getElementById("user-chat-button");
const userChatCount = document.getElementById("user-chat-count");
const userChatList = document.getElementById("user-chat-list");
const compileSectionButton = document.getElementById("compile-section");
const compileState = document.getElementById("compile-state");
const documentStyle = document.getElementById("document-style");

let selectedId = "ch01_sec01";
let userChatMessages = [];
let activityMessages = [];
let currentAppState = null;

function getAllItems() {
  return sections.flatMap((chapter) => chapter.items);
}

function findSelected() {
  return getAllItems().find((item) => item.id === selectedId) || sections[0]?.items?.[0];
}

function renderOutline(filter = "") {
  const normalized = filter.trim().toLowerCase();
  outlineTree.innerHTML = "";

  sections.forEach((chapter, chapterIndex) => {
    const visibleItems = chapter.items.filter((item) => {
      return !normalized || `${chapter.title} ${item.number} ${item.title}`.toLowerCase().includes(normalized);
    });

    if (normalized && visibleItems.length === 0) {
      return;
    }

    const chapterNode = document.createElement("section");
    chapterNode.className = "chapter";

    const chapterButton = document.createElement("button");
    chapterButton.type = "button";
    chapterButton.className = "chapter-toggle";
    chapterButton.innerHTML = `<span>${chapter.expanded || normalized ? "v" : ">"}</span><span>${chapter.chapter}: ${chapter.title}</span>`;
    chapterButton.addEventListener("click", () => {
      sections[chapterIndex].expanded = !sections[chapterIndex].expanded;
      renderOutline(search.value);
    });
    chapterNode.appendChild(chapterButton);

    if (chapter.expanded || normalized) {
      const list = document.createElement("ul");
      list.className = "section-list";
      visibleItems.forEach((item) => {
        const row = document.createElement("li");
        const button = document.createElement("button");
        button.type = "button";
        button.className = `section-item ${item.id === selectedId ? "is-active" : ""}`;
        button.setAttribute("role", "treeitem");
        button.setAttribute("aria-selected", String(item.id === selectedId));
        button.dataset.sectionId = item.id;
        const score = item.score === null ? "--" : `${item.score}%`;
        button.innerHTML = `<span class="section-name">${item.number} ${item.title}</span><span class="score ${item.tone}">${score}</span>`;
        button.addEventListener("click", () => selectSectionFromApp(item.id));
        row.appendChild(button);
        list.appendChild(row);
      });
      chapterNode.appendChild(list);
    }

    outlineTree.appendChild(chapterNode);
  });
}

function selectSection(id) {
  selectedId = id;
  const item = findSelected();
  if (!item) {
    return;
  }
  editor.value = item.source;
  title.textContent = item.title;
  previewTitle.textContent = item.title;
  previewCopy.textContent = summarizeSource(item.source);
  sectionStatus.textContent = item.score === null ? "Not drafted" : `${item.score}% coherent`;
  sectionStatus.className = `status-pill ${item.tone === "good" ? "good" : "neutral"}`;
  sectionAgent.textContent = item.agent;
  confidence.textContent = item.score === null ? "Pending" : `${Math.max(58, item.score - 22)}%`;
  renderOutline(search.value);
}

async function selectSectionFromApp(id) {
  selectedId = id;
  if (window.cbm && window.cbm.app) {
    try {
      const section = await window.cbm.app.section(id);
      updateSelectedSection(section);
      renderOutline(search.value);
      return;
    } catch (error) {
      appendActivityMessage("Desktop -> Book", `Failed to load section: ${error.message}`);
    }
  }
  selectSection(id);
}

function updateSelectedSection(section) {
  const item = getAllItems().find((candidate) => candidate.id === section.id);
  if (item) {
    Object.assign(item, section);
  }
  selectedId = section.id;
  editor.value = section.source || "";
  title.textContent = section.title || section.id;
  previewTitle.textContent = section.title || section.id;
  previewCopy.textContent = summarizeSource(section.source || section.summary || "");
  const score = section.score;
  const tone = section.tone || "idle";
  sectionStatus.textContent = score === null || score === undefined ? "Not drafted" : `${score}% coherent`;
  sectionStatus.className = `status-pill ${tone === "good" ? "good" : "neutral"}`;
  sectionAgent.textContent = section.agent || "Queued";
  confidence.textContent = score === null || score === undefined ? "Pending" : `${Math.max(58, score - 22)}%`;
}

function renderCompiledPreview(result) {
  if (!pdfStage || !result) {
    return;
  }
  if (result.pdf_path) {
    const pdfUrl = `file://${result.pdf_path}`;
    pdfStage.innerHTML = `<iframe class="pdf-frame" src="${pdfUrl}" title="Compiled PDF preview"></iframe>`;
    return;
  }
  if (result.errors && result.errors.length) {
    pdfStage.innerHTML = `<pre class="compile-diagnostics">${result.errors.join("\n")}</pre>`;
  }
}

function summarizeSource(source) {
  const paragraph = source
    .split("\n")
    .map((line) => line.trim())
    .find((line) => line && !line.startsWith("\\"));
  return paragraph || "This section is ready for drafting.";
}

function renderMessages(extraMessage) {
  if (extraMessage) {
    activityMessages.unshift(extraMessage);
  }
  const baseMessages = currentAppState?.messages || fallbackMessages;
  const allMessages = [...activityMessages, ...baseMessages].slice(0, 40);
  messagesList.innerHTML = "";
  allMessages.forEach(([time, source, text]) => {
    const item = document.createElement("li");
    item.className = "message";
    item.innerHTML = `<span class="message-time">${time}</span><span class="message-source">${source}</span><span class="message-text">${text}</span>`;
    messagesList.appendChild(item);
  });
}

function appendActivityMessage(source, text) {
  renderMessages(["now", source, text]);
}

async function loadAppState() {
  if (!window.cbm || !window.cbm.app) {
    renderOutline();
    selectSection(selectedId);
    renderMessages();
    return;
  }

  try {
    const state = await window.cbm.app.state(selectedId);
    currentAppState = state;
    sections = state.outline || [];
    selectedId = state.selectedId || selectedId;
    document.querySelector(".outline-pane h1").textContent = state.book?.title || "Untitled Book";
    if (state.agentStatus) {
      document.getElementById("hypervisor-score").textContent = `${state.agentStatus.confidence || 0}%`;
      confidence.textContent = `${state.agentStatus.confidence || 0}%`;
      const activeCard = document.querySelectorAll(".health-card strong")[1];
      if (activeCard) {
        activeCard.textContent = `${state.agentStatus.active}/${state.agentStatus.total}`;
      }
    }
    renderOutline(search.value);
    if (state.selectedSection) {
      updateSelectedSection(state.selectedSection);
    } else {
      selectSection(selectedId);
    }
    renderCompiledPreview(state.compile);
    renderMessages();
  } catch (error) {
    appendActivityMessage("Desktop -> Book", `Failed to load app state: ${error.message}`);
    sections = fallbackSections;
    renderOutline();
    selectSection(selectedId);
  }
}

async function loadDocumentStyles() {
  if (!window.cbm || !window.cbm.typeset || !documentStyle) {
    return;
  }
  const styles = await window.cbm.typeset.styles();
  documentStyle.innerHTML = "";
  styles.forEach((style) => {
    const option = document.createElement("option");
    option.value = style.styleId;
    option.textContent = style.label;
    option.title = style.description || "";
    documentStyle.appendChild(option);
  });
}

async function setDocumentStyle(styleId) {
  if (!window.cbm || !window.cbm.typeset) {
    return;
  }
  compileState.textContent = "Saving style";
  const result = await window.cbm.typeset.setStyle(styleId);
  compileState.textContent = "Ready";
  appendActivityMessage("Document Design -> Typeset", result.output || `Document style set to ${styleId}.`);
}

async function compileSelectedSection() {
  if (!window.cbm || !window.cbm.app) {
    appendActivityMessage("Typeset -> Preview", "Section compile requires the desktop app bridge.");
    return;
  }
  compileState.textContent = "Compiling";
  try {
    await window.cbm.app.saveSection(selectedId, editor.value);
    const result = await window.cbm.app.compileSection(selectedId);
    compileState.textContent = result.status === "passed" ? "Compiled" : "Failed";
    const pdf = result.pdf_path ? ` PDF: ${result.pdf_path}` : "";
    appendActivityMessage("Typeset -> Preview", `Compile ${result.status}.${pdf}`);
    renderCompiledPreview(result);
    await loadAppState();
  } catch (error) {
    compileState.textContent = "Failed";
    appendActivityMessage("Typeset -> Preview", `Compile failed: ${error.message}`);
  }
}

async function saveSelectedSection() {
  if (!window.cbm || !window.cbm.app || !selectedId) {
    return;
  }
  try {
    await window.cbm.app.saveSection(selectedId, editor.value);
    appendActivityMessage("Editor -> Book", `Saved ${selectedId}.`);
    await loadAppState();
  } catch (error) {
    appendActivityMessage("Editor -> Book", `Save failed: ${error.message}`);
  }
}

function pendingUserMessages() {
  return userChatMessages.filter((message) => message.status === "pending");
}

function updateUserChatCount() {
  const count = pendingUserMessages().length;
  userChatCount.textContent = String(count);
  userChatButton.classList.toggle("has-pending", count > 0);
  userChatButton.setAttribute("aria-label", `${count} pending user chat message${count === 1 ? "" : "s"}`);
}

async function loadUserChat() {
  if (window.cbm && window.cbm.userChat) {
    userChatMessages = await window.cbm.userChat.list();
  } else {
    userChatMessages = fallbackUserChat;
  }
  renderUserChat();
}

function renderUserChat() {
  userChatList.innerHTML = "";
  updateUserChatCount();

  if (userChatMessages.length === 0) {
    const empty = document.createElement("li");
    empty.className = "user-chat-empty";
    empty.textContent = "No user questions queued.";
    userChatList.appendChild(empty);
    return;
  }

  userChatMessages.forEach((message) => {
    const item = document.createElement("li");
    item.className = `user-chat-item ${message.status || "pending"}`;

    const header = document.createElement("div");
    header.className = "user-chat-header";
    const subject = document.createElement("strong");
    subject.textContent = message.subject;
    const sender = document.createElement("span");
    sender.textContent = message.from_agent || "agent";
    header.append(subject, sender);

    const body = document.createElement("p");
    body.textContent = message.body;

    item.append(header, body);

    if (message.status === "pending") {
      const form = document.createElement("form");
      form.className = "user-chat-reply";

      const answer = document.createElement("textarea");
      answer.rows = 2;
      answer.placeholder = "Reply to agent";
      answer.setAttribute("aria-label", `Reply to ${message.subject}`);

      const actions = document.createElement("div");
      actions.className = "user-chat-actions";

      const dismiss = document.createElement("button");
      dismiss.type = "button";
      dismiss.className = "secondary-action";
      dismiss.textContent = "Dismiss";
      dismiss.addEventListener("click", () => dismissUserMessage(message.message_id));

      const submit = document.createElement("button");
      submit.type = "submit";
      submit.className = "primary-action";
      submit.textContent = "Send";

      actions.append(dismiss, submit);
      form.append(answer, actions);
      form.addEventListener("submit", (event) => {
        event.preventDefault();
        answerUserMessage(message.message_id, answer.value);
      });
      item.appendChild(form);
    } else {
      const status = document.createElement("div");
      status.className = "user-chat-status";
      status.textContent = message.status === "answered" ? `Answered: ${message.answer || ""}` : "Dismissed";
      item.appendChild(status);
    }

    userChatList.appendChild(item);
  });
}

async function answerUserMessage(messageId, answer) {
  const trimmed = answer.trim();
  if (!trimmed) {
    return;
  }

  if (window.cbm && window.cbm.userChat) {
    await window.cbm.userChat.answer(messageId, trimmed);
    await loadUserChat();
  } else {
    userChatMessages = userChatMessages.map((message) => (
      message.message_id === messageId
        ? { ...message, status: "answered", answer: trimmed, answered_at: new Date().toISOString() }
        : message
    ));
    renderUserChat();
  }
}

async function dismissUserMessage(messageId) {
  if (window.cbm && window.cbm.userChat) {
    await window.cbm.userChat.dismiss(messageId);
    await loadUserChat();
  } else {
    userChatMessages = userChatMessages.map((message) => (
      message.message_id === messageId
        ? { ...message, status: "dismissed", answered_at: new Date().toISOString() }
        : message
    ));
    renderUserChat();
  }
}

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((candidate) => {
      const isActive = candidate === tab;
      candidate.classList.toggle("is-active", isActive);
      candidate.setAttribute("aria-selected", String(isActive));
    });
  });
});

document.querySelectorAll(".thumb").forEach((thumb) => {
  thumb.addEventListener("click", () => {
    document.querySelectorAll(".thumb").forEach((candidate) => candidate.classList.remove("is-active"));
    thumb.classList.add("is-active");
  });
});

search.addEventListener("input", () => renderOutline(search.value));

toggleChat.addEventListener("click", () => {
  const next = root.dataset.chatCollapsed !== "true";
  root.dataset.chatCollapsed = String(next);
  toggleChat.setAttribute("aria-expanded", String(!next));
  toggleChat.textContent = next ? "v" : "^";
});

pauseSwarm.addEventListener("click", () => {
  const paused = pauseSwarm.dataset.paused === "true";
  pauseSwarm.dataset.paused = String(!paused);
  pauseSwarm.textContent = paused ? "Pause Swarm" : "Resume Swarm";
  renderMessages([paused ? "now" : "now", "Operator -> Hypervisor", paused ? "Swarm resumed." : "Swarm paused. Agents will finish current local actions only."]);
});

requestReview.addEventListener("click", () => {
  if (window.cbm && window.cbm.app) {
    window.cbm.app.requestReview("book").then(() => loadAppState());
  }
  appendActivityMessage("Operator -> Hypervisor", "Full review requested across outline, section drafts, dependencies, and PDF compile state.");
});

compileSectionButton.addEventListener("click", () => {
  compileSelectedSection();
});

documentStyle.addEventListener("change", () => {
  setDocumentStyle(documentStyle.value);
});

editor.addEventListener("keydown", (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "s") {
    event.preventDefault();
    saveSelectedSection();
  }
});

editor.addEventListener("blur", () => {
  saveSelectedSection();
});

userChatButton.addEventListener("click", () => {
  root.dataset.chatCollapsed = "false";
  toggleChat.setAttribute("aria-expanded", "true");
  toggleChat.textContent = "^";
  document.getElementById("user-chat").scrollIntoView({ block: "nearest" });
});

if (window.cbm && window.cbm.imports) {
  window.cbm.imports.onOutlineStarted(({ sourcePath }) => {
    appendActivityMessage("Importer -> Outline", `Importing outline from ${sourcePath}.`);
  });
  window.cbm.imports.onOutlineCompleted(({ output }) => {
    appendActivityMessage("Importer -> Outline", output || "Outline import completed.");
  });
  window.cbm.imports.onOutlineFailed(({ message }) => {
    appendActivityMessage("Importer -> Outline", `Import failed: ${message}`);
  });
}

loadAppState();
loadUserChat();
loadDocumentStyles();

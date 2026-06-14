import type { BookAppState, DocumentStyle, ElectronApi, SectionPayload, UserChatMessage } from "./types";

const fallbackSection: SectionPayload = {
  id: "ch01_sec01",
  number: "1.1",
  title: "From Static to Codynamic",
  score: 94,
  tone: "good",
  agent: "Section-1.1 active",
  source: String.raw`\section{From Static to Codynamic}

Traditional static models fix the shape of a system before its interaction with the world is known. A codynamic model begins differently: structure is treated as something revised by local constraints, feedback, and intent.

\[
  S(t + 1) = \operatorname{refine}(S(t), I, E)
\]`
};

export const fallbackState: BookAppState = {
  book: { title: "Codynamic Theory" },
  outline: [
    {
      id: "ch01",
      chapter: "Chapter 1",
      title: "Foundations of Structure",
      expanded: true,
      items: [fallbackSection]
    }
  ],
  selectedId: fallbackSection.id,
  selectedSection: fallbackSection,
  messages: ["desktop_app --> book: Loaded fallback renderer state."],
  agentStatus: { active: 0, total: 1, confidence: 72, hypervisorConfidence: 100, pendingProposals: 0, activeAgents: [] },
  proposals: [],
  artifacts: [],
  references: [],
  knowledgeGraph: {
    citation_network: {},
    dependency_graph: {},
    concept_graph: {},
    orphan_claims: [],
    missing_citations: [],
    invalid_dependencies: [],
    circular_dependencies: [],
    citation_occurrences: [],
    concept_graph_visualization: { nodes: [], edges: [], mermaid: "flowchart LR" }
  },
  verification: [],
  design: { style_id: "standard_article", page_size: "letter", margin: "1in", title_page_enabled: false, table_of_contents_enabled: false }
};

const fallbackStyles: DocumentStyle[] = [
  { styleId: "standard_article", label: "Standard Article", description: "Portable article layout." }
];

const fallbackUserChat: UserChatMessage[] = [
  {
    message_id: "demo_user_msg_1",
    from_agent: "hypervisor_agent",
    subject: "Confirm next review target",
    body: "Several agents are ready to proceed. Which section should receive the next coordinated review?",
    status: "pending"
  }
];

export function getElectronApi(): ElectronApi {
  if (window.cbm) {
    return window.cbm;
  }
  return {
    app: {
      async state() {
        return fallbackState;
      },
      async section() {
        return fallbackSection;
      },
      async saveSection(_sectionId, content) {
        return { ...fallbackSection, source: content };
      },
      async startSectionAgent(sectionId) {
        const section = { ...fallbackSection, id: sectionId, source: "\\section*{Draft}\\n\\nGenerated fallback LaTeX draft.\\n" };
        return { section, event: { event_type: "section_agent_started", status: "pass" } };
      },
      async runHypervisor(options) {
        if (options?.excludeSectionIds?.includes(fallbackSection.id)) {
          return {
            targetSectionId: null,
            complete: true,
            phase: options?.phase ?? "draft",
            event: { event_type: "hypervisor_idle", status: "pass" }
          };
        }
        const section = { ...fallbackSection, source: "Generated fallback LaTeX draft from Hypervisor.\\n" };
        return {
          targetSectionId: section.id,
          phase: options?.phase ?? "draft",
          event: { event_type: "hypervisor_section_agent_dispatched", status: "pass" },
          sectionAgent: { section, event: { event_type: "section_agent_started", status: "pass" } }
        };
      },
      async reviewHypervisorDocument() {
        return {
          selectedSectionIds: [fallbackSection.id],
          documentChars: fallbackSection.source.length,
          averageCompletenessPercent: fallbackSection.score ?? null,
          event: { event_type: "hypervisor_document_reviewed", status: "warn" }
        };
      },
      async compileSection() {
        return { status: "skipped" };
      },
      async compileBook() {
        return { status: "skipped" };
      },
      async updateDesignSettings(updates) {
        fallbackState.design = { ...(fallbackState.design ?? {}), ...updates };
        return fallbackState.design;
      },
      async pdfDataUrl() {
        return "";
      },
      async requestReview() {
        return { event_type: "review_requested", status: "warn", rationale: "Fallback review requested." };
      },
      async createSection(_parentId, title) {
        return { ...fallbackSection, id: title.toLowerCase().replace(/[^a-z0-9]+/g, "_"), title, source: `\\section{${title}}\n\nDraft this section.\n` };
      },
      async createChapter(title) {
        return { id: title.toLowerCase().replace(/[^a-z0-9]+/g, "_"), title };
      },
      async updateOutlineNode(nodeId, title) {
        return { id: nodeId, title };
      },
      async acceptProposal(proposalId) {
        return { proposal_id: proposalId, agent_id: "fallback", target_path: "", status: "accepted" };
      },
      async rejectProposal(proposalId) {
        return { proposal_id: proposalId, agent_id: "fallback", target_path: "", status: "rejected" };
      },
      async reviseProposal(proposalId) {
        return { proposal_id: proposalId, agent_id: "fallback", target_path: "", status: "revised" };
      },
      async importOutline() {
        return null;
      },
      async library() {
        return { active: "fallback", books: [] };
      },
      async openBook() {
        return { book_id: "fallback", title: "Fallback", root: "", status: "active" };
      },
      async newBook(title) {
        return { book_id: "fallback", title, root: "", status: "active" };
      },
      onBookChanged() {},
      onLibraryMessage() {}
    },
    typeset: {
      async styles() {
        return fallbackStyles;
      },
      async setStyle(styleId) {
        return { output: `Document style set to ${styleId}.` };
      }
    },
    userChat: {
      async list() {
        return fallbackUserChat;
      },
      async answer(messageId, answer) {
        return { ...fallbackUserChat[0], message_id: messageId, answer, status: "answered" };
      },
      async dismiss(messageId) {
        return { ...fallbackUserChat[0], message_id: messageId, status: "dismissed" };
      }
    }
  };
}

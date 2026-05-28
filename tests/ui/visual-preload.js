const fallbackSection = {
  id: 'ch01_sec01',
  number: '1.1',
  title: 'From Static to Codynamic',
  score: 94,
  tone: 'good',
  agent: 'Section-1.1 active',
  source: '\\section{From Static to Codynamic}\\n\\nTraditional static models fix the shape of a system before its interaction with the world is known.'
};

window.cbm = {
  app: {
    async state() {
      return {
        book: { title: 'Codynamic Theory' },
        outline: [
          {
            id: 'ch01',
            chapter: 'Chapter 1',
            title: 'Foundations of Structure',
            expanded: true,
            items: [fallbackSection]
          }
        ],
        selectedId: fallbackSection.id,
        selectedSection: fallbackSection,
        design: { style_id: 'standard_article', page_size: 'letter', margin: '1in' },
        styles: [{ styleId: 'standard_article', label: 'Standard Article' }],
        messages: [['now', 'Visual Test -> Renderer', 'Loaded mocked book state.']],
        agentStatus: { active: 7, total: 12, confidence: 72, pendingProposals: 1 },
        proposals: [
          {
            proposal_id: 'proposal_visual',
            agent_id: 'section_agent',
            target_path: 'content/sections/ch01_sec01.md',
            status: 'pending',
            rationale: 'Visual test proposal.',
            diff: '--- a/content/sections/ch01_sec01.md\\n+++ b/content/sections/ch01_sec01.md\\n@@\\n+Added line\\n'
          }
        ],
        references: [{ id: 'ref_demo', title: 'Demo Reference', author: 'A. Writer', year: 2026 }],
        artifacts: [{ artifact_id: 'pdf_demo', kind: 'pdf', path: 'build/pdf/demo.pdf' }],
        verification: [{ rationale: 'Visual test verification event.' }]
      };
    },
    async section() {
      return fallbackSection;
    },
    async saveSection(_sectionId, content) {
      return { ...fallbackSection, source: content };
    },
    async compileSection() {
      return { status: 'passed' };
    },
    async compileBook() {
      return { status: 'passed', pdf_path: '' };
    },
    async requestReview() {
      return { event_type: 'review_requested', status: 'warn', rationale: 'Visual test review.' };
    },
    async createSection(_parentId, title) {
      return { ...fallbackSection, id: title.toLowerCase().replace(/[^a-z0-9]+/g, '_'), title };
    },
    async createChapter(title) {
      return { id: title.toLowerCase().replace(/[^a-z0-9]+/g, '_'), title };
    },
    async updateOutlineNode(nodeId, title) {
      return { id: nodeId, title };
    },
    async acceptProposal(proposalId) {
      return { proposal_id: proposalId, agent_id: 'section_agent', target_path: '', status: 'accepted' };
    },
    async rejectProposal(proposalId) {
      return { proposal_id: proposalId, agent_id: 'section_agent', target_path: '', status: 'rejected' };
    },
    async reviseProposal(proposalId) {
      return { proposal_id: proposalId, agent_id: 'section_agent', target_path: '', status: 'revised' };
    },
    async importOutline() {
      return { sourcePath: '/tmp/outline.yaml', output: 'Imported outline.' };
    },
    async library() {
      return { active: 'demo', books: [{ book_id: 'demo', title: 'Codynamic Theory', root: '', status: 'active' }] };
    },
    async openBook() {
      return { book_id: 'demo', title: 'Codynamic Theory', root: '', status: 'active' };
    },
    async newBook(title) {
      return { book_id: 'new', title, root: '', status: 'active' };
    },
    onBookChanged() {},
    onLibraryMessage() {}
  },
  typeset: {
    async styles() {
      return [{ styleId: 'standard_article', label: 'Standard Article' }];
    },
    async setStyle(styleId) {
      return { output: `Document style set to ${styleId}.` };
    }
  },
  userChat: {
    async list() {
      return [];
    },
    async answer(messageId, answer) {
      return { message_id: messageId, subject: '', body: '', status: 'answered', answer };
    },
    async dismiss(messageId) {
      return { message_id: messageId, subject: '', body: '', status: 'dismissed' };
    }
  }
};

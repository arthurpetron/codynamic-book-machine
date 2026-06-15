const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('cbm', {
  app: {
    state: (selectedId) => ipcRenderer.invoke('app:state', { selectedId }),
    section: (sectionId) => ipcRenderer.invoke('app:section', { sectionId }),
    saveSection: (sectionId, content) => ipcRenderer.invoke('app:save-section', { sectionId, content }),
    startSectionAgent: (sectionId) => ipcRenderer.invoke('app:start-section-agent', { sectionId }),
    runHypervisor: (options) => ipcRenderer.invoke('app:run-hypervisor', options || {}),
    reviewHypervisorDocument: (limit) => ipcRenderer.invoke('app:review-hypervisor-document', { limit }),
    compileSection: (sectionId) => ipcRenderer.invoke('app:compile-section', { sectionId }),
    compileBook: () => ipcRenderer.invoke('app:compile-book'),
    updateDesignSettings: (updates) => ipcRenderer.invoke('app:update-design-settings', { updates }),
    pdfDataUrl: (pdfPath) => ipcRenderer.invoke('app:pdf-data-url', { pdfPath }),
    requestReview: (subject) => ipcRenderer.invoke('app:request-review', { subject }),
    createSection: (parentId, title) => ipcRenderer.invoke('app:create-section', { parentId, title }),
    createChapter: (title) => ipcRenderer.invoke('app:create-chapter', { title }),
    updateOutlineNode: (nodeId, title) => ipcRenderer.invoke('app:update-outline-node', { nodeId, title }),
    acceptProposal: (proposalId, note) => ipcRenderer.invoke('app:accept-proposal', { proposalId, note }),
    rejectProposal: (proposalId, note) => ipcRenderer.invoke('app:reject-proposal', { proposalId, note }),
    reviseProposal: (proposalId, content, note) => ipcRenderer.invoke('app:revise-proposal', { proposalId, content, note }),
    importOutline: (mode) => ipcRenderer.invoke('app:import-outline', { mode }),
    createVersionFromOutline: () => ipcRenderer.invoke('app:create-version-from-outline'),
    createBookFromOutlineConversation: (messages, useLlm) => ipcRenderer.invoke('app:create-book-from-outline-conversation', { messages, useLlm }),
    library: () => ipcRenderer.invoke('app:library'),
    openBook: (bookId) => ipcRenderer.invoke('app:open-book', { bookId }),
    newBook: (title) => ipcRenderer.invoke('app:new-book', { title }),
    onNewOutlineConversation: (callback) => ipcRenderer.on('app:outline-conversation:new', () => callback()),
    onBookChanged: (callback) => ipcRenderer.on('app:book:changed', (_event, payload) => callback(payload)),
    onLibraryMessage: (callback) => ipcRenderer.on('app:library:message', (_event, payload) => callback(payload))
  },
  imports: {
    onOutlineStarted: (callback) => ipcRenderer.on('import:outline:started', (_event, payload) => callback(payload)),
    onOutlineCompleted: (callback) => ipcRenderer.on('import:outline:completed', (_event, payload) => callback(payload)),
    onOutlineFailed: (callback) => ipcRenderer.on('import:outline:failed', (_event, payload) => callback(payload))
  },
  typeset: {
    styles: () => ipcRenderer.invoke('typeset:styles'),
    setStyle: (styleId, bookRoot) => ipcRenderer.invoke('typeset:set-style', { styleId, bookRoot }),
    compileSection: (sectionId, bookRoot) => ipcRenderer.invoke('typeset:compile-section', { sectionId, bookRoot })
  },
  userChat: {
    list: () => ipcRenderer.invoke('user-chat:list'),
    answer: (messageId, answer) => ipcRenderer.invoke('user-chat:answer', { messageId, answer }),
    dismiss: (messageId) => ipcRenderer.invoke('user-chat:dismiss', { messageId })
  }
});

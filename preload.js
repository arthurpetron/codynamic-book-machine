const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('cbm', {
  app: {
    state: (selectedId) => ipcRenderer.invoke('app:state', { selectedId }),
    section: (sectionId) => ipcRenderer.invoke('app:section', { sectionId }),
    saveSection: (sectionId, content) => ipcRenderer.invoke('app:save-section', { sectionId, content }),
    compileSection: (sectionId) => ipcRenderer.invoke('app:compile-section', { sectionId }),
    requestReview: (subject) => ipcRenderer.invoke('app:request-review', { subject }),
    library: () => ipcRenderer.invoke('app:library'),
    openBook: (bookId) => ipcRenderer.invoke('app:open-book', { bookId }),
    newBook: (title) => ipcRenderer.invoke('app:new-book', { title }),
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

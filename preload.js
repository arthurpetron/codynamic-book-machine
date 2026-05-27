const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('cbm', {
  userChat: {
    list: () => ipcRenderer.invoke('user-chat:list'),
    answer: (messageId, answer) => ipcRenderer.invoke('user-chat:answer', { messageId, answer }),
    dismiss: (messageId) => ipcRenderer.invoke('user-chat:dismiss', { messageId })
  }
});

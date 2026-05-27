const { app, BrowserWindow, ipcMain } = require('electron');
const fs = require('fs');
const path = require('path');

function getUserChatQueuePath() {
  return path.join(__dirname, 'data', 'user_chat', 'queue.json');
}

function readUserChatQueue() {
  const queuePath = getUserChatQueuePath();
  if (!fs.existsSync(queuePath)) {
    return [];
  }
  const raw = fs.readFileSync(queuePath, 'utf8').trim();
  if (!raw) {
    return [];
  }
  const messages = JSON.parse(raw);
  return Array.isArray(messages) ? messages : [];
}

function writeUserChatQueue(messages) {
  const queuePath = getUserChatQueuePath();
  fs.mkdirSync(path.dirname(queuePath), { recursive: true });
  fs.writeFileSync(queuePath, `${JSON.stringify(messages, null, 2)}\n`);
}

function updateUserChatMessage(messageId, updates) {
  const messages = readUserChatQueue();
  const message = messages.find((candidate) => candidate.message_id === messageId);
  if (!message) {
    throw new Error(`User chat message not found: ${messageId}`);
  }
  Object.assign(message, updates);
  writeUserChatQueue(messages);
  return message;
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1280,
    height: 900,
    minWidth: 1024,
    minHeight: 720,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js')
    }
  });

  win.loadFile(path.join(__dirname, 'public', 'index.html'));
}

app.whenReady().then(() => {
  ipcMain.handle('user-chat:list', () => readUserChatQueue());
  ipcMain.handle('user-chat:answer', (_event, { messageId, answer }) => {
    if (!answer || !answer.trim()) {
      throw new Error('Answer is required');
    }
    return updateUserChatMessage(messageId, {
      status: 'answered',
      answer: answer.trim(),
      answered_at: new Date().toISOString()
    });
  });
  ipcMain.handle('user-chat:dismiss', (_event, { messageId }) => {
    return updateUserChatMessage(messageId, {
      status: 'dismissed',
      answered_at: new Date().toISOString()
    });
  });

  createWindow();
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  }
});

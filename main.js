const { app, BrowserWindow, Menu, dialog, ipcMain } = require('electron');
const { execFile } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

function getUserChatQueuePath() {
  return path.join(__dirname, 'data', 'user_chat', 'queue.json');
}

function getDefaultBookRoot() {
  return path.join(__dirname, 'data', 'book_data', 'codynamic_theory_book');
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

function runPython(args) {
  return new Promise((resolve, reject) => {
    execFile('python3', args, { cwd: __dirname }, (error, stdout, stderr) => {
      if (error) {
        error.stdout = stdout;
        error.stderr = stderr;
        reject(error);
        return;
      }
      resolve({ stdout, stderr });
    });
  });
}

async function runAppJson(args) {
  const result = await runPython([
    path.join(__dirname, 'main.py'),
    'app',
    '--book-root',
    getDefaultBookRoot(),
    ...args
  ]);
  return JSON.parse(result.stdout);
}

async function importOutline(win) {
  const result = await dialog.showOpenDialog(win, {
    title: 'Import Outline',
    properties: ['openFile'],
    filters: [
      { name: 'Outlines', extensions: ['yaml', 'yml', 'json', 'md', 'markdown', 'txt'] },
      { name: 'All Files', extensions: ['*'] }
    ]
  });

  if (result.canceled || result.filePaths.length === 0) {
    return;
  }

  const sourcePath = result.filePaths[0];
  win.webContents.send('import:outline:started', { sourcePath });

  try {
    const importResult = await runPython([
      path.join(__dirname, 'main.py'),
      'import',
      'outline',
      sourcePath
    ]);
    win.webContents.send('import:outline:completed', {
      sourcePath,
      output: importResult.stdout.trim()
    });
  } catch (error) {
    win.webContents.send('import:outline:failed', {
      sourcePath,
      message: error.stderr || error.stdout || error.message
    });
  }
}

function parseStyles(stdout) {
  return stdout
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const [styleId, label, description] = line.split('\t');
      return { styleId, label, description };
    });
}

function createAppMenu(win) {
  const template = [
    {
      label: 'File',
      submenu: [
        {
          label: 'Import',
          submenu: [
            {
              label: 'Outline...',
              accelerator: 'CmdOrCtrl+Shift+O',
              click: () => importOutline(win)
            }
          ]
        },
        { type: 'separator' },
        process.platform === 'darwin'
          ? { role: 'close' }
          : { role: 'quit' }
      ]
    },
    {
      label: 'Edit',
      submenu: [
        { role: 'undo' },
        { role: 'redo' },
        { type: 'separator' },
        { role: 'cut' },
        { role: 'copy' },
        { role: 'paste' },
        { role: 'selectAll' }
      ]
    },
    {
      label: 'View',
      submenu: [
        { role: 'reload' },
        { role: 'toggleDevTools' },
        { type: 'separator' },
        { role: 'resetZoom' },
        { role: 'zoomIn' },
        { role: 'zoomOut' },
        { type: 'separator' },
        { role: 'togglefullscreen' }
      ]
    }
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
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
  createAppMenu(win);
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
  ipcMain.handle('typeset:styles', async () => {
    const result = await runPython([path.join(__dirname, 'main.py'), 'typeset', 'styles']);
    return parseStyles(result.stdout);
  });
  ipcMain.handle('typeset:set-style', async (_event, { styleId, bookRoot }) => {
    const result = await runPython([
      path.join(__dirname, 'main.py'),
      'typeset',
      bookRoot || getDefaultBookRoot(),
      'set-style',
      styleId
    ]);
    return { output: result.stdout.trim() };
  });
  ipcMain.handle('typeset:compile-section', async (_event, { sectionId, bookRoot }) => {
    const result = await runPython([
      path.join(__dirname, 'main.py'),
      'typeset',
      bookRoot || getDefaultBookRoot(),
      'compile',
      '--section-id',
      sectionId
    ]);
    return { output: result.stdout.trim() };
  });
  ipcMain.handle('app:state', async (_event, { selectedId } = {}) => {
    const args = ['state'];
    if (selectedId) {
      args.push('--selected-id', selectedId);
    }
    return runAppJson(args);
  });
  ipcMain.handle('app:section', async (_event, { sectionId }) => {
    return runAppJson(['section', sectionId]);
  });
  ipcMain.handle('app:save-section', async (_event, { sectionId, content }) => {
    const tmpPath = path.join(os.tmpdir(), `cbm-section-${Date.now()}.txt`);
    fs.writeFileSync(tmpPath, content || '');
    try {
      return await runAppJson(['save-section', sectionId, '--content-file', tmpPath]);
    } finally {
      fs.rmSync(tmpPath, { force: true });
    }
  });
  ipcMain.handle('app:compile-section', async (_event, { sectionId }) => {
    return runAppJson(['compile-section', sectionId]);
  });
  ipcMain.handle('app:request-review', async (_event, { subject } = {}) => {
    return runAppJson(['request-review', '--subject', subject || 'book']);
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

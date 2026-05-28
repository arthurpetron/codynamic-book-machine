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

function getBookDataDir() {
  return path.join(__dirname, 'data', 'book_data');
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
    '--book-data-dir',
    getBookDataDir(),
    ...args
  ]);
  return JSON.parse(result.stdout);
}

async function getActiveBookRoot() {
  const library = await runAppJson(['library']);
  const active = library.books.find((book) => book.book_id === library.active);
  return active?.root || getDefaultBookRoot();
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
      sourcePath,
      '--book-data-dir',
      getBookDataDir(),
      '--register'
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

async function importOutlineForMode(win, mode = 'new') {
  const dialogOptions = {
    title: mode === 'current' ? 'Import Outline Into Current Book' : 'Import Outline As New Book',
    properties: ['openFile'],
    filters: [
      { name: 'Outlines', extensions: ['yaml', 'yml', 'json', 'md', 'markdown', 'txt'] },
      { name: 'All Files', extensions: ['*'] }
    ]
  };
  const result = win
    ? await dialog.showOpenDialog(win, dialogOptions)
    : await dialog.showOpenDialog(dialogOptions);

  if (result.canceled || result.filePaths.length === 0) {
    return null;
  }

  const sourcePath = result.filePaths[0];
  const args = [
    path.join(__dirname, 'main.py'),
    'import',
    'outline',
    sourcePath,
    '--book-data-dir',
    getBookDataDir(),
    '--register'
  ];
  if (mode === 'current') {
    args.push('--book-root', await getActiveBookRoot());
  }
  const importResult = await runPython(args);
  return { sourcePath, output: importResult.stdout.trim() };
}

async function openBook(win) {
  const library = await runAppJson(['library']);
  const active = library.active;
  const candidates = library.books.filter((book) => book.status !== 'archived');
  if (candidates.length === 0) {
    win.webContents.send('app:library:message', { message: 'No registered books found.' });
    return;
  }
  const result = await dialog.showMessageBox(win, {
    type: 'question',
    title: 'Open Book',
    message: 'Choose a book to open.',
    buttons: candidates.map((book) => book.title),
    cancelId: candidates.findIndex((book) => book.book_id === active),
    noLink: true
  });
  if (result.response < 0 || !candidates[result.response]) {
    return;
  }
  await runAppJson(['open-book', candidates[result.response].book_id]);
  win.webContents.send('app:book:changed', { bookId: candidates[result.response].book_id });
}

async function newBook(win) {
  const result = await dialog.showMessageBox(win, {
    type: 'question',
    title: 'New Book',
    message: 'Create a new untitled intake book?',
    buttons: ['Create', 'Cancel'],
    cancelId: 1,
    noLink: true
  });
  if (result.response !== 0) {
    return;
  }
  const title = `Untitled Book ${new Date().toISOString().slice(0, 10)}`;
  const record = await runAppJson(['new-book', title]);
  win.webContents.send('app:book:changed', { bookId: record.book_id });
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
          label: 'New Book...',
          accelerator: 'CmdOrCtrl+N',
          click: () => newBook(win)
        },
        {
          label: 'Open Book...',
          accelerator: 'CmdOrCtrl+O',
          click: () => openBook(win)
        },
        { type: 'separator' },
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

  const rendererUrl = process.env.VITE_DEV_SERVER_URL;
  const builtRenderer = path.join(__dirname, 'dist', 'renderer', 'index.html');
  if (rendererUrl) {
    win.loadURL(rendererUrl);
  } else if (fs.existsSync(builtRenderer)) {
    win.loadFile(builtRenderer);
  } else {
    win.loadFile(path.join(__dirname, 'public', 'index.html'));
  }
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
      bookRoot || await getActiveBookRoot(),
      'set-style',
      styleId
    ]);
    return { output: result.stdout.trim() };
  });
  ipcMain.handle('typeset:compile-section', async (_event, { sectionId, bookRoot }) => {
    const result = await runPython([
      path.join(__dirname, 'main.py'),
      'typeset',
      bookRoot || await getActiveBookRoot(),
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
  ipcMain.handle('app:compile-book', async () => {
    return runAppJson(['compile-book']);
  });
  ipcMain.handle('app:request-review', async (_event, { subject } = {}) => {
    return runAppJson(['request-review', '--subject', subject || 'book']);
  });
  ipcMain.handle('app:create-section', async (_event, { parentId, title }) => {
    const args = ['create-section', title || 'Untitled Section'];
    if (parentId) {
      args.push('--parent-id', parentId);
    }
    return runAppJson(args);
  });
  ipcMain.handle('app:create-chapter', async (_event, { title }) => {
    return runAppJson(['create-chapter', title || 'Untitled Chapter']);
  });
  ipcMain.handle('app:update-outline-node', async (_event, { nodeId, title }) => {
    return runAppJson(['update-outline-node', nodeId, title]);
  });
  ipcMain.handle('app:accept-proposal', async (_event, { proposalId, note } = {}) => {
    return runAppJson(['accept-proposal', proposalId, '--note', note || 'Accepted from desktop app.']);
  });
  ipcMain.handle('app:reject-proposal', async (_event, { proposalId, note } = {}) => {
    return runAppJson(['reject-proposal', proposalId, '--note', note || 'Rejected from desktop app.']);
  });
  ipcMain.handle('app:revise-proposal', async (_event, { proposalId, content, note } = {}) => {
    const tmpPath = path.join(os.tmpdir(), `cbm-proposal-${Date.now()}.txt`);
    fs.writeFileSync(tmpPath, content || '');
    try {
      return await runAppJson(['revise-proposal', proposalId, '--content-file', tmpPath, '--note', note || 'Revised from desktop app.']);
    } finally {
      fs.rmSync(tmpPath, { force: true });
    }
  });
  ipcMain.handle('app:import-outline', async (_event, { mode } = {}) => {
    return importOutlineForMode(BrowserWindow.getFocusedWindow(), mode || 'new');
  });
  ipcMain.handle('app:library', async () => {
    return runAppJson(['library']);
  });
  ipcMain.handle('app:open-book', async (_event, { bookId }) => {
    return runAppJson(['open-book', bookId]);
  });
  ipcMain.handle('app:new-book', async (_event, { title }) => {
    return runAppJson(['new-book', title]);
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

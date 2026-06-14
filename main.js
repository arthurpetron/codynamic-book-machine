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

function getDefaultVersionOutlinePath() {
  return path.join(__dirname, 'data', 'book_book', 'meta_book.yaml');
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

function getPythonExecutable() {
  // Use venv python if available, fallback to system python3
  const venvPython = path.join(__dirname, '.venv', 'bin', 'python3');
  if (fs.existsSync(venvPython)) {
    return venvPython;
  }
  return 'python3';
}

function runPython(args) {
  return new Promise((resolve, reject) => {
    const pythonExe = getPythonExecutable();
    execFile(pythonExe, args, { cwd: __dirname, maxBuffer: 16 * 1024 * 1024 }, (error, stdout, stderr) => {
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

function pythonErrorMessage(error) {
  const stderr = (error && error.stderr) ? String(error.stderr).trim() : '';
  const stdout = (error && error.stdout) ? String(error.stdout).trim() : '';
  return stderr || stdout || (error && error.message) || 'Unknown Python command error';
}

async function runAppJson(args) {
  const result = await runPython([
    path.join(__dirname, 'main.py'),
    'app',
    '--book-data-dir',
    getBookDataDir(),
    ...args
  ]);
  return parseJsonFromStdout(result.stdout);
}

function parseJsonFromStdout(stdout) {
  const text = String(stdout || '').trim();
  try {
    return JSON.parse(text);
  } catch (_error) {
    const objectStart = text.lastIndexOf('\n{');
    const arrayStart = text.lastIndexOf('\n[');
    const start = Math.max(objectStart, arrayStart);
    if (start >= 0) {
      return JSON.parse(text.slice(start + 1));
    }
    const firstObject = text.indexOf('{');
    const firstArray = text.indexOf('[');
    const fallbackStart = [firstObject, firstArray].filter((index) => index >= 0).sort((a, b) => a - b)[0];
    if (fallbackStart != null) {
      return JSON.parse(text.slice(fallbackStart));
    }
    throw _error;
  }
}

async function getActiveBookRoot() {
  const library = await runAppJson(['library']);
  const active = library.books.find((book) => book.book_id === library.active);
  return active?.root || getDefaultBookRoot();
}

async function importOutlineForMode(win, mode = 'new') {
  const dialogOptions = {
    title: mode === 'current' ? 'Import Outline Into Current Book' : 'Import Outline As New Book',
    properties: ['openFile'],
    filters: [
      {
        name: 'Outline-like text sources',
        extensions: [
          'yaml', 'yml', 'json',
          'md', 'markdown', 'txt', 'text',
          'tex', 'latex', 'rst', 'adoc', 'org',
          'opml', 'xml', 'html', 'htm'
        ]
      },
      { name: 'All Files', extensions: ['*'] }
    ]
  };
  const result = win
    ? await dialog.showOpenDialog(win, dialogOptions)
    : await dialog.showOpenDialog(dialogOptions);

  if (result.canceled || result.filePaths.length === 0) {
    console.log(`[Import] ${mode} import canceled.`);
    return null;
  }

  const sourcePath = result.filePaths[0];
  console.log(`[Import] Starting ${mode} outline import: ${sourcePath}`);
  const args = [
    path.join(__dirname, 'main.py'),
    'import',
    'outline',
    sourcePath,
    '--book-data-dir',
    getBookDataDir(),
    '--use-llm',
    'auto',
    '--register'
  ];
  if (mode === 'current') {
    args.push('--book-root', await getActiveBookRoot());
  }
  const importResult = await runPython(args);
  const output = importResult.stdout.trim();
  console.log(`[Import] Completed ${mode} outline import: ${output || sourcePath}`);
  return { sourcePath, output };
}

function importedBookIdFromOutput(output) {
  const match = String(output || '').match(/\(([^()\s]+)\)\s*$/m);
  return match ? match[1] : null;
}

async function importOutlineFromNativeMenu(win, mode = 'new') {
  try {
    const result = await importOutlineForMode(win, mode);
    if (!result) {
      return;
    }
    const bookId = importedBookIdFromOutput(result.output);
    win.webContents.send('app:book:changed', { bookId });
    win.webContents.send('app:library:message', {
      message: result.output || `Imported outline from ${result.sourcePath}.`
    });
    await dialog.showMessageBox(win, {
      type: 'info',
      title: 'Outline Imported',
      message: mode === 'current' ? 'Imported outline into the current book.' : 'Imported outline as a new book.',
      detail: result.output || result.sourcePath,
      buttons: ['OK']
    });
  } catch (error) {
    const message = pythonErrorMessage(error);
    console.error(`[Import] Failed ${mode} outline import: ${message}`);
    win.webContents.send('app:library:message', {
      message: `Import failed: ${message}`
    });
    await dialog.showMessageBox(win, {
      type: 'error',
      title: 'Import Failed',
      message: 'Outline import failed.',
      detail: message,
      buttons: ['OK']
    });
  }
}

async function createVersionFromOutline(win) {
  try {
    const result = await runAppJson([
      'create-version-from-outline',
      '--outline-path',
      getDefaultVersionOutlinePath(),
      '--force'
    ]);
    const bookId = result.record?.book_id;
    win.webContents.send('app:book:changed', { bookId });
    win.webContents.send('app:library:message', {
      message: result.message || `Created clean version from ${getDefaultVersionOutlinePath()}.`
    });
    await dialog.showMessageBox(win, {
      type: 'info',
      title: 'Version Created',
      message: 'Created a clean book version from the outline.',
      detail: result.message || '',
      buttons: ['OK']
    });
    return result;
  } catch (error) {
    const message = pythonErrorMessage(error);
    win.webContents.send('app:library:message', {
      message: `Version creation failed: ${message}`
    });
    await dialog.showMessageBox(win, {
      type: 'error',
      title: 'Version Creation Failed',
      message: 'Could not create a clean version from the outline.',
      detail: message,
      buttons: ['OK']
    });
    throw error;
  }
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
  const fileMenu = {
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
        label: 'Import / Translate Outline as New Book...',
        accelerator: 'CmdOrCtrl+Shift+O',
        click: () => importOutlineFromNativeMenu(win, 'new')
      },
      {
        label: 'Import / Translate Outline into Current Book...',
        click: () => importOutlineFromNativeMenu(win, 'current')
      },
      {
        label: 'Create Version from Meta Outline...',
        click: () => createVersionFromOutline(win)
      },
      { type: 'separator' },
      process.platform === 'darwin'
        ? { role: 'close' }
        : { role: 'quit' }
    ]
  };

  const template = [
    ...(process.platform === 'darwin'
      ? [{
          label: app.name,
          submenu: [
            { role: 'about' },
            { type: 'separator' },
            { role: 'services' },
            { type: 'separator' },
            { role: 'hide' },
            { role: 'hideOthers' },
            { role: 'unhide' },
            { type: 'separator' },
            { role: 'quit' }
          ]
        }]
      : []),
    fileMenu,
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
    try {
      return await runAppJson(args);
    } catch (error) {
      const stdout = (error && error.stdout) ? String(error.stdout) : '';
      if (selectedId && stdout.includes('Unknown section id')) {
        return runAppJson(['state']);
      }
      throw error;
    }
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
  ipcMain.handle('app:start-section-agent', async (_event, { sectionId }) => {
    return runAppJson(['start-section-agent', sectionId]);
  });
  ipcMain.handle('app:run-hypervisor', async (_event, { excludeSectionIds, includeSectionIds, phase } = {}) => {
    const args = ['run-hypervisor'];
    if (Array.isArray(excludeSectionIds) && excludeSectionIds.length > 0) {
      args.push('--exclude-json', JSON.stringify(excludeSectionIds));
    }
    if (Array.isArray(includeSectionIds) && includeSectionIds.length > 0) {
      args.push('--include-json', JSON.stringify(includeSectionIds));
    }
    if (phase) {
      args.push('--phase', phase);
    }
    return runAppJson(args);
  });
  ipcMain.handle('app:review-hypervisor-document', async (_event, { limit } = {}) => {
    const args = ['review-hypervisor-document'];
    if (limit) {
      args.push('--limit', String(limit));
    }
    return runAppJson(args);
  });
  ipcMain.handle('app:compile-section', async (_event, { sectionId }) => {
    return runAppJson(['compile-section', sectionId]);
  });
  ipcMain.handle('app:compile-book', async () => {
    return runAppJson(['compile-book']);
  });
  ipcMain.handle('app:update-design-settings', async (_event, { updates } = {}) => {
    return runAppJson(['update-design-settings', JSON.stringify(updates || {})]);
  });
  ipcMain.handle('app:pdf-data-url', async (_event, { pdfPath }) => {
    if (!pdfPath) {
      throw new Error('PDF path is required');
    }
    const resolved = path.resolve(pdfPath);
    const bookRoot = path.resolve(await getActiveBookRoot());
    if (!resolved.startsWith(`${bookRoot}${path.sep}`)) {
      throw new Error('PDF path is outside the active book root.');
    }
    const bytes = fs.readFileSync(resolved);
    return `data:application/pdf;base64,${bytes.toString('base64')}`;
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
    try {
      const win = BrowserWindow.fromWebContents(_event.sender) || BrowserWindow.getFocusedWindow();
      const result = await importOutlineForMode(win, mode || 'new');
      if (result) {
        win?.webContents.send('app:book:changed', { bookId: importedBookIdFromOutput(result.output) });
      }
      return result;
    } catch (error) {
      const message = pythonErrorMessage(error);
      return {
        sourcePath: '',
        output: `Import failed: ${message}`
      };
    }
  });
  ipcMain.handle('app:create-version-from-outline', async (_event) => {
    try {
      const win = BrowserWindow.fromWebContents(_event.sender) || BrowserWindow.getFocusedWindow();
      const result = await runAppJson([
        'create-version-from-outline',
        '--outline-path',
        getDefaultVersionOutlinePath(),
        '--force'
      ]);
      win?.webContents.send('app:book:changed', { bookId: result.record?.book_id });
      return result;
    } catch (error) {
      return {
        error: pythonErrorMessage(error)
      };
    }
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

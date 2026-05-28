const { app, BrowserWindow } = require('electron');
const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..', '..');
const artifactsDir = path.join(root, 'tests', 'ui', 'artifacts');
const rendererPath = path.join(root, 'dist', 'renderer', 'index.html');

const failures = [];
const consoleErrors = [];

function assert(condition, message) {
  if (!condition) {
    failures.push(message);
  }
}

async function waitFor(win, expression, label) {
  const deadline = Date.now() + 5000;
  while (Date.now() < deadline) {
    const result = await win.webContents.executeJavaScript(expression);
    if (result) {
      return result;
    }
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  throw new Error(`Timed out waiting for ${label}`);
}

async function screenshot(win, name) {
  const image = await win.webContents.capturePage();
  const filePath = path.join(artifactsDir, `${name}.png`);
  fs.writeFileSync(filePath, image.toPNG());
  return filePath;
}

async function click(win, selector) {
  const bounds = await win.webContents.executeJavaScript(`
    (() => {
      const element = document.querySelector(${JSON.stringify(selector)});
      if (!element) return null;
      const rect = element.getBoundingClientRect();
      return { x: Math.round(rect.left + rect.width / 2), y: Math.round(rect.top + rect.height / 2) };
    })()
  `);
  if (!bounds) {
    throw new Error(`Missing clickable element: ${selector}`);
  }
  win.webContents.sendInputEvent({ type: 'mouseDown', x: bounds.x, y: bounds.y, button: 'left', clickCount: 1 });
  win.webContents.sendInputEvent({ type: 'mouseUp', x: bounds.x, y: bounds.y, button: 'left', clickCount: 1 });
}

async function hoverBackground(win, selector) {
  const data = await win.webContents.executeJavaScript(`
    (() => {
      const element = document.querySelector(${JSON.stringify(selector)});
      const rect = element.getBoundingClientRect();
      return {
        x: Math.round(rect.left + rect.width / 2),
        y: Math.round(rect.top + rect.height / 2),
        before: getComputedStyle(element).backgroundColor
      };
    })()
  `);
  win.webContents.sendInputEvent({ type: 'mouseMove', x: data.x, y: data.y });
  await new Promise((resolve) => setTimeout(resolve, 80));
  const after = await win.webContents.executeJavaScript(`
    getComputedStyle(document.querySelector(${JSON.stringify(selector)})).backgroundColor
  `);
  return { before: data.before, after };
}

async function run() {
  if (!fs.existsSync(rendererPath)) {
    throw new Error('Built renderer missing. Run `npm run build` before `npm run test:ui:visual`.');
  }
  fs.mkdirSync(artifactsDir, { recursive: true });

  const win = new BrowserWindow({
    width: 1440,
    height: 960,
    show: false,
    webPreferences: {
      contextIsolation: false,
      nodeIntegration: false,
      preload: path.join(__dirname, 'visual-preload.js')
    }
  });

  win.webContents.on('console-message', (_event, level, message) => {
    if (message.includes('Electron Security Warning')) {
      return;
    }
    if (level >= 2) {
      consoleErrors.push(message);
    }
  });

  await win.loadFile(rendererPath);
  await waitFor(win, '!!document.querySelector(".workspace")', 'workspace render');
  const screenshots = [];
  screenshots.push(await screenshot(win, '01-initial'));

  const initial = await win.webContents.executeJavaScript(`({
    outline: !!document.querySelector('.outline-pane'),
    editor: !!document.querySelector('.editor-pane'),
    preview: !!document.querySelector('.preview-pane'),
    compileBook: document.body.innerText.includes('Compile Book'),
    pageStrip: !!document.querySelector('.page-strip'),
    sectionMeta: !!document.querySelector('.section-meta'),
    selected: document.querySelector('.section-item.is-active')?.textContent || ''
  })`);
  assert(initial.outline && initial.editor && initial.preview, 'Initial three-pane layout did not render.');
  assert(initial.compileBook, 'PDF preview should expose a Compile Book action.');
  assert(!initial.pageStrip, 'PDF preview should not render the horizontal page gallery.');
  assert(initial.sectionMeta, 'Editor tab should show the current section title bar.');
  assert(initial.selected.includes('From Static'), 'Initial selected section is not visually active.');

  const hover = await hoverBackground(win, '.outline-tools .primary-action');
  assert(hover.before !== hover.after || hover.after.includes('31, 111, 91'), 'Primary action hover state did not resolve to the expected accent color.');
  screenshots.push(await screenshot(win, '02-primary-hover'));

  await click(win, '.tabs button:nth-of-type(2)');
  await waitFor(win, 'document.querySelector(".tab.is-active")?.textContent.includes("Agent Settings")', 'Agent Settings tab');
  const agentsVisible = await win.webContents.executeJavaScript(`
    (() => {
      const text = document.body.innerText.toLowerCase();
      return text.includes("global app settings") &&
        text.includes("per-agent settings") &&
        text.includes("section agent");
    })()
  `);
  assert(agentsVisible, 'Agent Settings tab did not show global and per-agent settings.');
  const agentMetaHidden = await win.webContents.executeJavaScript('!document.querySelector(".section-meta")');
  assert(agentMetaHidden, 'Agent Settings tab should not show the current section title bar.');
  screenshots.push(await screenshot(win, '03-agent-settings'));

  await click(win, '.tabs button:nth-of-type(3)');
  await waitFor(win, 'document.querySelector(".tab.is-active")?.textContent.includes("References")', 'References tab');
  const referencesVisible = await win.webContents.executeJavaScript('document.body.innerText.toLowerCase().includes("artifacts") && document.body.innerText.includes("Demo Reference")');
  assert(referencesVisible, 'References tab did not show references and artifacts.');
  const referencesMetaHidden = await win.webContents.executeJavaScript('!document.querySelector(".section-meta")');
  assert(referencesMetaHidden, 'References tab should not show the current section title bar.');
  screenshots.push(await screenshot(win, '04-references'));

  await click(win, '.outline-tools .primary-action');
  await waitFor(win, '!!document.querySelector(".inline-dialog")', 'new section dialog');
  const dialogVisible = await win.webContents.executeJavaScript(`
    !!document.querySelector(${JSON.stringify('.inline-dialog input[placeholder="Section title"]')})
  `);
  assert(dialogVisible, 'New Section did not open an inline creation dialog.');
  screenshots.push(await screenshot(win, '05-new-section-dialog'));

  await click(win, '.agent-status .icon-button');
  await waitFor(win, '!document.querySelector(".chat-panels")', 'collapsed agent console');
  screenshots.push(await screenshot(win, '06-console-collapsed'));

  assert(consoleErrors.length === 0, `Renderer console errors detected: ${consoleErrors.join(' | ')}`);

  const report = {
    status: failures.length === 0 ? 'passed' : 'failed',
    failures,
    consoleErrors,
    screenshots
  };
  fs.writeFileSync(path.join(artifactsDir, 'report.json'), `${JSON.stringify(report, null, 2)}\n`);
  win.destroy();
  if (failures.length > 0) {
    throw new Error(failures.join('\n'));
  }
}

app.whenReady()
  .then(run)
  .then(() => app.quit())
  .catch((error) => {
    console.error(error.message);
    app.exit(1);
  });

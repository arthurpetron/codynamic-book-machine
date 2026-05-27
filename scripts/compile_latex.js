#!/usr/bin/env node

const { execFile } = require('child_process');
const path = require('path');

function parseArgs(argv) {
  const args = {
    bookRoot: path.join(__dirname, '..', 'data', 'book_data', 'codynamic_theory_book'),
    sectionId: null,
    engine: null
  };
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === '--book-root') {
      args.bookRoot = argv[index + 1];
      index += 1;
    } else if (arg === '--section-id') {
      args.sectionId = argv[index + 1];
      index += 1;
    } else if (arg === '--engine') {
      args.engine = argv[index + 1];
      index += 1;
    }
  }
  return args;
}

function compileLatex() {
  const args = parseArgs(process.argv.slice(2));
  const projectRoot = path.join(__dirname, '..');
  const commandArgs = [
    path.join(projectRoot, 'main.py'),
    'typeset',
    args.bookRoot,
    'compile'
  ];
  if (args.sectionId) {
    commandArgs.push('--section-id', args.sectionId);
  }
  if (args.engine) {
    commandArgs.push('--engine', args.engine);
  }

  const child = execFile('python3', commandArgs, { cwd: projectRoot }, (error, stdout, stderr) => {
    if (stdout) {
      process.stdout.write(stdout);
    }
    if (stderr) {
      process.stderr.write(stderr);
    }
    if (error) {
      process.exitCode = error.code || 1;
    }
  });

  child.on('error', (error) => {
    process.stderr.write(`${error.message}\n`);
    process.exitCode = 1;
  });
}

compileLatex();

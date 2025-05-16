// LaTeX compile script placeholder
const { exec } = require('child_process');
exec('pdflatex tex/01_intro.tex', (error, stdout, stderr) => {
  if (error) {
    console.error(`exec error: ${error}`);
    return;
  }
  console.log(`stdout: ${stdout}`);
  console.error(`stderr: ${stderr}`);
});

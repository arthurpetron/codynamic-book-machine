# Codynamic Book Machine

A structured authoring engine for writing and evolving the book on Codynamic Theory.

## 🚀 Project Overview

The Codynamic Book Machine is an Electron-based desktop application designed to facilitate the creation and management of complex, structured documents. It integrates React for the frontend interface and LaTeX for high-quality typesetting, providing a seamless experience for authors and researchers.

## 🛠️ Current Work Plan

### Phase 1: Project Initialization

- [x] Scaffold Electron + React application structure
- [x] Set up LaTeX compilation pipeline using `pdflatex`
- [x] Implement live preview of compiled PDFs within the application
- [x] Initialize Git repository with appropriate `.gitignore`

### Phase 2: Core Functionality

- [ ] Develop a dynamic outline editor for structuring document sections
- [ ] Integrate a rich text editor with LaTeX syntax highlighting
- [ ] Enable real-time synchronization between editor and PDF preview
- [ ] Implement version control features with Git integration

### Phase 3: Advanced Features

- [ ] Incorporate LLM-based review system for automated feedback on pull requests
- [ ] Develop a plugin system for extensibility (e.g., citation management, glossary generation)
- [ ] Implement export options for different formats (PDF, HTML, ePub)

### Phase 4: Deployment and Distribution

- [ ] Package the application for cross-platform distribution (Windows, macOS, Linux)
- [ ] Create comprehensive documentation and user guides
- [ ] Set up continuous integration and deployment pipelines

## 📂 Project Structure

codynamic-book-machine/
├── src/                  # React components and frontend logic
├── tex/                  # LaTeX source files
├── public/               # Static assets and HTML templates
├── scripts/              # Utility scripts (e.g., LaTeX compilation)
├── data/                 # Application data and configuration files
├── main.js               # Electron main process script
├── package.json          # Project metadata and dependencies
└── README.md             # Project overview and work plan

## 📄 License

This project is licensed under the MIT License.

## 💻 How to Run Locally

### 📦 Prerequisites
- [Node.js](https://nodejs.org/) (v18+ recommended)
- [MacTeX](https://www.tug.org/mactex/) or another full LaTeX distribution
- `pdflatex` or `latexmk` accessible via command line
- Git (optional, but recommended)

### 🚀 Setup

```bash
# Clone the repository
git clone https://github.com/yourusername/codynamic-book-machine.git
cd codynamic-book-machine

# Install dependencies
npm install```

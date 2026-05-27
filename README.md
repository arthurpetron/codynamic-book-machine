# Codynamic Book Machine

A structured authoring engine for writing and evolving complex books, monographs, and long-form works.

## 🚀 Project Overview

The Codynamic Book Machine is an Electron-based desktop application designed to facilitate the creation and management of complex, structured documents. The machine is codynamic: outlines, dependencies, artifacts, agents, and compiled outputs evolve together as the work changes. It integrates React for the frontend interface and LaTeX for high-quality typesetting, providing a reusable authoring environment for authors and researchers.

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
- Python 3.12
- [Node.js](https://nodejs.org/) 18+
- [MacTeX](https://www.tug.org/mactex/), TeX Live, MiKTeX, or Tectonic
- At least one LaTeX compiler on `PATH`: `latexmk`, `pdflatex`, `xelatex`, `lualatex`, or `tectonic`
- Git

### 🚀 Setup

```bash
# Clone the repository
git clone https://github.com/yourusername/codynamic-book-machine.git
cd codynamic-book-machine

# Install pinned Python dependencies
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt

# Install pinned Electron dependencies
npm install

# Verify the baseline
./.venv/bin/python -m pytest tests -q
```

### Configuration

Copy `.env.example` to `.env` if you need non-default configuration.

Supported environment variables:

- `ENVIRONMENT` or `ENV`: runtime environment name; defaults to `development`
- `SCHEMA_DIR`: overrides the schema directory; defaults to `data/schemas`
- `SCHEMA_REGISTRY_FILE`: registry filename inside `SCHEMA_DIR`
- `SCHEMA_REGISTRY_PATH`: full path to a registry file; overrides the two schema settings above
- `LATEX_ENGINE`: optional compiler override; otherwise the app discovers `latexmk`, `pdflatex`, `xelatex`, `lualatex`, or `tectonic`
- `KEY_OPENAI_API` or `OPENAI_API_KEY`: enables OpenAI-backed features
- `KEY_ANTHROPIC_API` or `ANTHROPIC_API_KEY`: enables Anthropic-backed features

## Canonical Book Object

CBM uses one internal outline representation: Work Outline Schema v2.1, rooted at `work` with recursive `work.structure[*].content` nodes. Legacy `outline: chapters:` YAML, markdown outlines, numbered outlines, and supported text-like outlines are normalized behind the scenes before repository or GUI code reads them.

The current sample/workspace book lives under `data/book_data/codynamic_theory_book/`:

- `outline/codynamic_theory.yaml`: canonical v2.1 work outline
- `outline/legacy/codynamic_theory.v1.yaml`: preserved legacy source outline
- `outline/reports/codynamic_theory_migration.md`: human-readable migration report
- `artifacts/registry.yaml`: discovered TeX, render, log, image, diagram, and section payload artifacts
- `content/sections/`: canonical reusable section payload location for new section bodies

Useful commands:

```bash
# Migrate an outline-like input to canonical YAML and write a report
python3 -m scripts.migrate_outline input.yaml output.yaml --report migration.md

# Validate the canonical book outline
python3 main.py validate data/book_data/codynamic_theory_book/outline/codynamic_theory.yaml --skip-bootstrap
```

Outline migration uses deterministic parsers for known formats and can use the configured LLM provider for ambiguous or raw outline text. The default `--llm auto` mode calls the provider for unknown formats or repair attempts; `--llm always` forces model-assisted interpretation; `--llm never` keeps conversion fully deterministic.

## Agent Runtime

Agents follow the EtherCAT state model closely:

- `bootstrap`: agent creation or awakening; state and memory are loaded before configuration is complete.
- `init`: fully configured but offline; no API calls, messaging, tools, or output mutation.
- `pre_operational`: planning and introspection; API calls are allowed, but inter-agent communication is not.
- `safe_operational`: communication is allowed; agents can answer, request help, and coordinate.
- `operational`: work output may change, and the agent may advance its task/work queue pointer.

Pause, sleep, and shutdown are orchestrator controls, not separate lifecycle states; they return agents to `init` or stop their loop.

`AgentOrchestrator` launches lifecycle-aware controller subclasses from `scripts/agents/agent_definitions/*.yaml`. Runtime message callbacks are registered in memory, while `scripts/messaging/agent_subscriptions.yaml` remains durable subscription configuration. Routed messages receive message IDs, correlation IDs, parent reply links, status, delivery timestamps, and an audit log under the configured message log directory.

Communication permissions are configurable in `scripts/messaging/agent_subscriptions.yaml` under `communication`. The router enforces that policy, and each agent injects its allowed outbound recipients into its system prompt so model behavior and runtime enforcement use the same rules.

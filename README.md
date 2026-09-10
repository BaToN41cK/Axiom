# AXIOM

**Terminal-first AI coding agent**

Axiom is a powerful, extensible AI coding agent that runs directly in your terminal. Beautiful TUI, real AI chat, streaming, multi-provider support, and a comprehensive tool system.

```
    █████╗ ██╗  ██╗██╗ ██████╗ ███╗   ███╗
   ██╔══██╗╚██╗██╔╝██║██╔═══██╗████╗ ████║
   ███████║ ╚███╔╝ ██║██║   ██║██╔████╔██║
   ██╔══██║ ██╔██╗ ██║██║   ██║██║╚██╔╝██║
   ██║  ██║██╔╝ ██╗██║╚██████╔╝██║ ╚═╝ ██║
   ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝ ╚═════╝ ╚═╝     ╚═╝
```

## Features

- 🖥️ **Beautiful TUI** — Professional terminal interface with ASCII logo
- 💬 **Real AI Chat** — Streaming responses from AI models
- 🔒 **Permission Engine** — Granular control over agent actions
- 🔧 **Tool System** — 20+ tools for filesystem, terminal, web, git, code search
- 🤖 **Multi-Provider** — OpenAI-compatible APIs and Ollama local models
- 💾 **Sessions** — Save and resume conversations (SQLite)
- 🏗️ **Multiple Modes** — Build, Plan, Review, Explore
- 🛡️ **Workspace Security** — Path traversal protection
- 👁️ **Vision** — Screenshot and image analysis support
- 🎭 **Agent Roles** — Orchestrator, Planner, Coder, Reviewer, Researcher, Tester, Explorer
- 🔀 **Multi-Agent** — Parallel task execution with orchestrator

## Installation

### Requirements

- Python 3.10+
- Windows 10/11 (primary), Linux/macOS (supported)

### Install from source

```bash
git clone https://github.com/axiom/axiom.git
cd axiom
pip install -e .
```

## Quick Start

### 1. Configure API

```bash
# For OpenAI-compatible API (e.g., B.ai)
axiom configure --set-provider openai_compatible \
                 --set-model MiMo-V2.5 \
                 --set-base-url https://api.b.ai/v1 \
                 --set-api-key YOUR_API_KEY

# For Ollama (local)
axiom configure --set-provider ollama --set-model llama3

# Or use environment variable
$env:AXIOM_API_KEY = "your-api-key"
```

### 2. Run Axiom

```bash
# Interactive TUI mode
axiom

# Run with a task
axiom "fix the authentication bug in src/auth.py"

# Planning mode
axiom plan

# Review mode
axiom review

# Check models
axiom models
```

### 3. Check Installation

```bash
axiom doctor
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `axiom` | Interactive TUI mode |
| `axiom "task"` | Run with specific task |
| `axiom run "task"` | Run with task and mode |
| `axiom plan` | Planning mode |
| `axiom review` | Review mode |
| `axiom configure` | Configure settings |
| `axiom config` | Show configuration |
| `axiom doctor` | Check installation |
| `axiom models` | List available models |
| `axiom session` | List sessions |
| `axiom session <id>` | Show session details |
| `axiom version` | Show version |

## TUI Commands

| Command | Description |
|---------|-------------|
| `/help` | Show help |
| `/clear` | Clear conversation |
| `/quit` | Exit |
| `/status` | Show agent status |
| `/models` | List available models |
| `/agents` | List agent roles |

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Ctrl+Q` | Quit |
| `Ctrl+L` | Clear conversation |
| `Ctrl+N` | New session |

## Configuration

Axiom uses hierarchical configuration:

1. **Defaults** — Built-in sensible defaults
2. **Global config** — `%USERPROFILE%\.axiom\config.json`
3. **Project config** — `<project>\.axiom\config.json`
4. **Environment variables** — `AXIOM_*` prefixed variables

### Environment Variables

| Variable | Description |
|----------|-------------|
| `AXIOM_API_KEY` | API key for model provider |
| `AXIOM_MODEL` | Model name |
| `AXIOM_PROVIDER` | Provider name (openai_compatible, ollama) |
| `AXIOM_BASE_URL` | Base URL for API |
| `AXIOM_MOCK_MODEL` | Enable mock mode (for testing) |

## Modes

| Mode | Description |
|------|-------------|
| **BUILD** | Full agent capabilities (default) |
| **PLAN** | Analysis only, no modifications |
| **REVIEW** | Code review, no modifications |
| **EXPLORE** | Understanding codebases |

## Tools (20+)

- **Filesystem:** read_file, write_file, edit_file, delete_file, list_directory, search_files
- **Terminal:** execute_command, start_process, stop_process, get_process_output
- **Web:** web_search, web_fetch, download
- **Git:** git_status, git_diff, git_log, git_branch, git_checkout, git_commit
- **Code Search:** search_code, find_symbol, inspect_project, run_tests
- **Vision:** take_screenshot, read_image

## Agent Roles

| Role | Description |
|------|-------------|
| **Orchestrator** | Coordinates multiple agents |
| **Planner** | Analyzes and creates plans |
| **Coder** | Writes and edits code |
| **Reviewer** | Reviews code quality |
| **Researcher** | Investigates codebases |
| **Tester** | Writes and runs tests |
| **Explorer** | Helps understand code |

## License

MIT License

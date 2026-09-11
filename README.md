# AXIOM

**Local AI Terminal Client** — powered by Ollama.

AXIOM is a modern terminal interface for local AI models. It connects to Ollama and provides a beautiful, streaming chat experience with web search capabilities.

## Features

- **Interactive TUI** — Full-screen Textual interface: split layout, scrolling, mouse support
- **Command Palette** — `Ctrl+P` for quick commands
- **Live Agent Journal** — Thinking / Planning / Search / Research steps update in place
- **Chat** — Stream responses from your local model
- **Thinking/Reasoning** — Display model reasoning when available
- **Web Search** — Search the web for current information
- **Web Research** — Fetch and extract content from web pages
- **Session History** — Keep conversation context during session
- **Slash Commands** — `/help`, `/status`, `/model`, `/models`, `/clear`, `/new`, `/thinking`, `/web`, `/exit`

## Requirements

- Python 3.10+
- Ollama running locally
- A model installed (default: `qwen3:8b`)

## Installation

```bash
pip install -e .
```

## Usage

Make sure Ollama is running:

```bash
ollama serve
```

Pull the default model:

```bash
ollama pull qwen3:8b
```

Run AXIOM:

```bash
axiom
```

Or:

```bash
python -m src
```

## Configuration

Create a `.env` file (copy from `.env.example`):

```env
OLLAMA_HOST=http://localhost:11434
AXIOM_MODEL=qwen3:8b
AXIOM_WEB_ENABLED=true
AXIOM_REASONING_ENABLED=true
```

## Commands

| Command | Description |
|---------|-------------|
| `/help` | Show help |
| `/status` | Show connection status |
| `/model` | Show current model |
| `/models` | List available models |
| `/clear` | Clear session |
| `/thinking` | Toggle thinking display |
| `/web` | Toggle web tools |
| `/new` | New session |
| `/exit` | Exit AXIOM |

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Enter` | Send message |
| `Ctrl+C` | Cancel generation |
| `Ctrl+L` | Clear screen |
| `↑ / ↓` | Navigate input history |

## Architecture

```
src/
├── __init__.py      - Package info
├── __main__.py      - Entry point (python -m src)
├── app.py           - Main application & UI loop
├── config.py        - Configuration management
├── ollama.py        - Ollama API client
├── web_tools.py     - Web search & fetch
├── session.py       - Session & history
├── agent.py         - AI agent orchestration
├── commands.py      - Slash commands
├── utils.py         - Utilities
└── ui/
    ├── theme.py     - Color theme
    ├── renderer.py  - Rich rendering
    ├── startup.py   - Startup screen
    └── status.py    - Status tracking
```

## Current Scope

**Enabled:**
- Chat with streaming
- Thinking/Reasoning display
- Web Search (DuckDuckGo)
- Web Research (fetch & extract)
- Session history

**Disabled (future):**
- File access
- Terminal commands
- Memory
- PC control
- Browser automation

## License

MIT

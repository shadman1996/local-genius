# 🧠 Local Genius

> A 100% free, local-first agentic AI system with safety monitoring, persistent memory, and optional hardware control.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        USER INPUT                           │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│  🧠 THE BRAIN  (brain.py)                                    │
│  Ollama + Llama 3.2 — Local LLM inference                   │
│  System Prompt: "Core-OS" autonomous governor                │
│  Output: Structured JSON Action Blocks                       │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│  ⚙️  THE LOGIC  (orchestrator.py)                             │
│  Agentic loop with retry + feedback                          │
│  Brain → Safety Check → Execute → Feedback → Brain           │
│  Memory integration via ChromaDB                             │
└──────────┬───────────────────────────────────┬──────────────┘
           │                                   │
           ▼                                   ▼
┌─────────────────────┐          ┌──────────────────────────┐
│  🛡️ SAFETY MONITOR   │          │  💾 MEMORY  (memory.py)   │
│  (safety_monitor.py) │          │  ChromaDB vector store    │
│  Regex blacklist     │          │  "What did I do?"         │
│  Audit logging       │          │  Semantic recall          │
└──────────┬──────────┘          └──────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────┐
│  🌐 THE GATEWAY  (gateway.py)                                │
│  subprocess.run() for system commands                        │
│  MQTT publish/subscribe for hardware (optional)              │
│  Returns StatusReport → feeds back to Orchestrator           │
└──────────────────────────────────────────────────────────────┘
```

---

## Quickstart

### Prerequisites

- **Python 3.10+**
- **Ollama** — [Install from ollama.com](https://ollama.com)

### Setup

```bash
# 1. Clone the repository
git clone https://github.com/YOUR_USERNAME/local-genius.git
cd local-genius

# 2. Install everything (creates venv, installs deps, copies .env)
make setup

# 3. Pull the LLM model
ollama pull llama3.2:3b

# 4. Start Ollama (if not already running)
ollama serve &

# 5. Run the agent
make run
```

### One-Shot Mode

```bash
make run-goal GOAL="List all Python files in the current directory"
```

---

## Configuration

Copy `.env.example` to `.env` and edit:

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_MODEL` | `llama3.2:3b` | Which Ollama model to use |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama API endpoint |
| `CHROMA_DB_PATH` | `./chroma_db` | Where to persist vector memory |
| `MAX_RETRIES` | `3` | How many times the agent retries on failure |
| `MQTT_ENABLED` | `false` | Enable MQTT hardware gateway |
| `MQTT_BROKER` | `localhost` | MQTT broker address |
| `MQTT_PORT` | `1883` | MQTT broker port |

---

## Safety

Local Genius includes a **Safety Monitor** that intercepts every command before execution:

- 🚫 Blocks destructive patterns (`rm -rf /`, `mkfs`, `dd`, fork bombs)
- 📝 Logs every command (approved and blocked) to `safety_monitor.log`
- 🔄 Feeds rejection reasons back to the LLM so it self-corrects
- 🛑 Configurable: add your own patterns

> ⚠️ **WARNING:** This is a software safety layer. For production use with real hardware,
> always add a physical kill-switch or hardware interrupter.

---

## Development

```bash
make test       # Run test suite
make test-cov   # Run tests with coverage
make lint       # Lint with ruff
make lint-fix   # Auto-fix lint issues
make clean      # Remove venv and caches
```

---

## Docker (Optional)

```bash
docker-compose up --build
```

This starts both Ollama and the Local Genius agent in containers.

---

## License

MIT — see [LICENSE](LICENSE).

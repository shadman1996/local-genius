# 🧠 Local Genius

**Local Genius** is a 100% free, local-first agentic AI system designed to operate autonomously on your hardware. 

It functions as an advanced system governor (acting similarly to Antigravity) that features a conversational loop, native file editing tools, real-time safety monitoring, semantic memory, and internet/IoT access.

---

## 🚀 Quick Start for Developers

Follow these instructions to clone, setup, and run the agent on your local machine or GPU server.

### 1. Prerequisites
You need **Python 3.10+** and **Ollama** installed on your machine.

**Install Ollama (Linux):**
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

**Pull the Core Model:**
We recommend the `qwen2.5-coder` family for optimal coding agent performance.
- For CPU-only machines: `ollama pull qwen2.5-coder:7b`
- For GPU machines (Senior Dev Tier): `ollama pull qwen2.5-coder:32b`

Make sure the Ollama server is running in the background:
```bash
ollama serve
```

### 2. Clone the Repository
```bash
git clone https://github.com/shadman1996/local-genius.git
cd local-genius
```

### 3. Setup the Environment
The project uses standard Python `venv` and a `Makefile` for convenience.
```bash
# Create virtual environment and install dependencies
make setup

# Copy the environment template
cp .env.example .env
```

*Note: Open `.env` and verify `OLLAMA_MODEL` matches the model you pulled in Step 1.*

### 4. Run the Agent
To start the interactive conversational REPL:
```bash
make run
```
*(Alternatively: `source venv/bin/activate && python -m src.main --interactive`)*

---

## 🛠️ Features & Tools

### Conversational Memory
The agent maintains continuous context. You can attach files to its brain before asking a question:
```text
🗣️  You > /attach src/main.py
📎 Attached file: src/main.py (will be sent with next prompt)

🗣️  You > Refactor the interactive loop in this file.
```

### Native Tools (Antigravity Parity)
The agent operates via a secure Gateway with access to the following tools:
1. **File Operations:** `read_file`, `write_file`, `replace_file_content` (replaces exact text blocks), `list_directory`.
2. **System Control:** `bash_command` (synchronous execution), `run_background` (asynchronous servers/scripts).
3. **Web Search:** `web_search` (queries Wikipedia for instant context).
4. **IoT Control:** `mqtt_publish` (can control Home Assistant or GPIO bridges).

### Safety Monitor & Feedback Loop
All `bash_command` executions are intercepted by the **Safety Monitor** using regex patterns (preventing `rm -rf /`, fork bombs, etc.). 
If a command fails or is blocked, the Orchestrator initiates a **Self-Correction Feedback Loop**, feeding the error back to the LLM so it can try a safer alternative.

---

## 🧪 Testing

The project uses `pytest` and maintains over 60 tests covering the orchestrator loop, safety monitor, and ChromaDB memory.

```bash
make test
```

## 📜 Architecture Overview
- **Brain (`src/brain.py`)**: Ollama SDK wrapper.
- **Orchestrator (`src/orchestrator.py`)**: The central chat loop that parses JSON actions from the Brain and routes them.
- **Gateway (`src/gateway.py`)**: The bridge that executes tools (file reading, bash, web search, MQTT).
- **Safety Monitor (`src/safety_monitor.py`)**: Regex-based gatekeeper for bash commands.
- **Memory (`src/memory.py`)**: ChromaDB vector store that remembers past actions and blocks.

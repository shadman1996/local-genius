# Local Genius — Architecture

## System Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                           USER INPUT                                 │
│                    (CLI REPL or --goal flag)                          │
└─────────────────────────────┬────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│                     ORCHESTRATOR (orchestrator.py)                    │
│                                                                      │
│   The agentic loop that coordinates all layers:                      │
│                                                                      │
│   ┌──────────────┐     ┌───────────────┐     ┌────────────────┐     │
│   │  1. BRAIN     │────▶│ 2. SAFETY     │────▶│ 3. GATEWAY     │     │
│   │  (brain.py)   │     │   MONITOR     │     │  (gateway.py)  │     │
│   │              │     │(safety_mon.py)│     │               │     │
│   │  Ollama LLM  │     │ Regex filter  │     │ subprocess    │     │
│   │  JSON output │     │ Audit log     │     │ MQTT pub/sub  │     │
│   └──────▲───────┘     └───────────────┘     └───────┬────────┘     │
│          │                                           │               │
│          │            ┌───────────────┐               │               │
│          └────────────│ 4. FEEDBACK   │◀──────────────┘               │
│                       │    LOOP       │                               │
│                       │ Error → Brain │                               │
│                       └───────┬───────┘                               │
│                               │                                      │
│                       ┌───────▼───────┐                               │
│                       │ 5. MEMORY     │                               │
│                       │ (memory.py)   │                               │
│                       │ ChromaDB      │                               │
│                       │ Vector store  │                               │
│                       └───────────────┘                               │
└──────────────────────────────────────────────────────────────────────┘
```

## Data Flow

1. **User** provides a goal via CLI
2. **Orchestrator** enriches the prompt with relevant memories from ChromaDB
3. **Brain** (Ollama) reasons about the goal and produces a JSON Action Block
4. **Safety Monitor** evaluates the proposed command against the regex blacklist
5. If **blocked**: error reason is fed back to Brain (step 3) for self-correction
6. If **approved**: **Gateway** executes the command via `subprocess` or MQTT
7. **Gateway** returns a `StatusReport` (success/failure + output)
8. If **failed**: error is fed back to Brain (step 3)
9. If **succeeded**: Brain is asked if the goal is complete
10. **Memory** records every action (approved, blocked, failed) for future recall

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Ollama over LM Studio** | Ollama has a proper Python SDK and CLI for model management |
| **ChromaDB over SQLite** | Semantic (vector) search enables "what did I do yesterday?" queries |
| **Regex safety over LLM-based safety** | Regex is deterministic and zero-latency; LLMs can be jailbroken |
| **subprocess over os.system** | subprocess provides timeout, output capture, and return codes |
| **MQTT over GPIO directly** | MQTT decouples the software from specific hardware, enabling remote control |
| **Structured JSON output** | Separates LLM reasoning from execution, enabling reliable parsing |

## File Map

| File | Layer | Purpose |
|------|-------|---------|
| `src/config.py` | Config | Loads `.env`, exports constants, defines system prompt |
| `src/brain.py` | Brain | Ollama SDK wrapper, JSON parsing, conversation history |
| `src/safety_monitor.py` | Safety | Regex blacklist, audit logging, extensible patterns |
| `src/orchestrator.py` | Logic | Agentic loop, retry, feedback injection, memory context |
| `src/memory.py` | Memory | ChromaDB persistent storage, semantic recall |
| `src/gateway.py` | Gateway | subprocess execution, MQTT pub/sub, StatusReport |
| `src/main.py` | CLI | argparse entry point, REPL, status display |

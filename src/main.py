"""
Local Genius — Main Entry Point

CLI interface for the agentic system.

Usage:
    python -m src.main --interactive      # Start a REPL
    python -m src.main --goal "list files" # Execute a single goal
"""

import argparse
import logging
import signal
import sys

from src.brain import Brain
from src.config import LOG_LEVEL, OLLAMA_MODEL
from src.gateway import Gateway
from src.memory import Memory
from src.orchestrator import Orchestrator
from src.safety_monitor import SafetyMonitor

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s | %(name)-20s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------
BANNER = r"""
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║   🧠  L O C A L   G E N I U S                               ║
║                                                              ║
║   100% Free · Local-First · Agentic AI                       ║
║   Model: {model:<46s}  ║
║                                                              ║
║   Type your goal and press Enter.                            ║
║   Type 'quit', 'exit', or Ctrl+C to stop.                   ║
║   Type 'memory' to see past actions.                         ║
║   Type 'status' to check system health.                      ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
""".strip()


def print_banner() -> None:
    print(BANNER.format(model=OLLAMA_MODEL))


# ---------------------------------------------------------------------------
# Interactive REPL
# ---------------------------------------------------------------------------
def interactive_mode(orchestrator: Orchestrator) -> None:
    """Run the agent in interactive REPL mode."""
    print_banner()
    print()

    while True:
        try:
            user_input = input("🎯 Goal > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\n👋 Goodbye!")
            break

        if not user_input:
            continue

        if user_input.lower() in ("quit", "exit", "q"):
            print("👋 Goodbye!")
            break

        if user_input.lower() == "memory":
            _show_memory(orchestrator.memory)
            continue

        if user_input.lower() == "status":
            _show_status(orchestrator)
            continue

        if user_input.lower() == "clear":
            orchestrator.brain.reset()
            print("🧹 Conversation history cleared.\n")
            continue

        # Execute the goal
        print(f"\n{'─' * 60}")
        result = orchestrator.execute_goal(user_input)
        print(f"{'─' * 60}")
        print(
            f"📊 Result: {result['final_status']} "
            f"({result['total_steps']} step(s))\n"
        )


def _show_memory(memory: Memory) -> None:
    """Display recent actions from memory."""
    recent = memory.recall_recent(n=10)
    if not recent:
        print("📭 No actions in memory yet.\n")
        return

    print(f"\n📚 Recent Actions ({len(recent)} total):")
    for item in recent:
        meta = item.get("metadata", {})
        blocked = "🛡️ BLOCKED" if meta.get("was_blocked") else "✅"
        ts = meta.get("timestamp", "?")[:19]
        print(f"  {blocked} [{ts}] {meta.get('command', '?')}")
    print()


def _show_status(orchestrator: Orchestrator) -> None:
    """Display system health status."""
    print("\n📡 System Status:")

    # Brain / Ollama
    brain_ok = orchestrator.brain.is_alive()
    print(f"  🧠 Brain (Ollama):    {'✅ Online' if brain_ok else '❌ Offline'}")

    # Memory
    print(f"  💾 Memory:            {orchestrator.memory.total_actions} actions stored")

    # Safety
    print(f"  🛡️  Safety Monitor:   {orchestrator.safety.pattern_count} patterns loaded")

    print()


# ---------------------------------------------------------------------------
# One-Shot Mode
# ---------------------------------------------------------------------------
def oneshot_mode(orchestrator: Orchestrator, goal: str) -> None:
    """Execute a single goal and exit."""
    print(f"🎯 Goal: {goal}")
    print(f"{'─' * 60}")
    result = orchestrator.execute_goal(goal)
    print(f"{'─' * 60}")
    print(
        f"📊 Result: {result['final_status']} "
        f"({result['total_steps']} step(s))"
    )
    sys.exit(0 if result["final_status"] == "completed" else 1)


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        prog="local-genius",
        description="Local Genius — A 100% free, local-first agentic AI system.",
    )
    parser.add_argument(
        "--interactive", "-i",
        action="store_true",
        default=True,
        help="Start in interactive REPL mode (default).",
    )
    parser.add_argument(
        "--goal", "-g",
        type=str,
        default=None,
        help='Execute a single goal and exit. E.g.: --goal "list files"',
    )
    args = parser.parse_args()

    # Initialize all layers
    brain = Brain()
    safety = SafetyMonitor()
    gateway = Gateway()
    memory = Memory()
    orchestrator = Orchestrator(
        brain=brain,
        safety=safety,
        gateway=gateway,
        memory=memory,
    )

    # Graceful shutdown on SIGINT/SIGTERM
    def _shutdown(signum: int, frame: object) -> None:
        print("\n\n🛑 Shutting down gracefully...")
        orchestrator.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    # Run
    if args.goal:
        oneshot_mode(orchestrator, args.goal)
    else:
        interactive_mode(orchestrator)
        orchestrator.shutdown()


if __name__ == "__main__":
    main()

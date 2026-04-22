"""
Local Genius — API Server
Provides a FastAPI interface to the Orchestrator, allowing IDE integration
(like VSCode/Cursor) and external web dashboards to interact with the agent.
"""

import logging
from typing import Any, List, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from src.orchestrator import Orchestrator

# Initialize global orchestrator
orchestrator = Orchestrator()

app = FastAPI(
    title="Local Genius API",
    description="The Antigravity-killer local agent API",
    version="1.0.0"
)

logger = logging.getLogger(__name__)

# --- Models ---

class ChatRequest(BaseModel):
    user_input: str
    context_files: Optional[List[str]] = None

class ChatResponse(BaseModel):
    reply: str
    steps: List[dict]
    total_steps: int

# --- Endpoints ---

@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    """
    Send a message to the Local Genius agent.
    Optionally provide a list of absolute file paths to ingest as context.
    """
    try:
        result = orchestrator.chat_turn(
            user_input=request.user_input,
            context_files=request.context_files
        )
        return ChatResponse(
            reply=result.get("reply", ""),
            steps=result.get("steps", []),
            total_steps=result.get("total_steps", 0)
        )
    except Exception as e:
        logger.error(f"Error in chat endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/clear")
def clear_memory():
    """Clear the agent's short-term conversation memory."""
    orchestrator.brain.reset()
    return {"status": "memory cleared"}

@app.get("/health")
def health_check():
    """Check if the agent and Ollama backend are alive."""
    if orchestrator.brain.is_alive():
        return {"status": "healthy", "backend": "online"}
    return {"status": "unhealthy", "backend": "offline"}

# To run: uvicorn src.api:app --host 127.0.0.1 --port 8000

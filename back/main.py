"""
Endpoints:
  GET  /api/projects              → Lists all OpenProject projects
  POST /api/conversations         → Creates a new conversation
  GET  /api/conversations/{id}    → Gets conversation history
  POST /api/chat/stream           → Starts SSE chat stream with the AI agent
  POST /api/ingest                → Triggers document re-ingestion (admin)
"""

import asyncio
from typing import Optional
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import Base, _get_engine, get_db
from models import Conversation, Message
from openproject_service import get_projects
from agent import stream_agent_response

# Create tables on startup only if the database is configured.
# In production, use Alembic migrations instead.
try:
    engine = _get_engine()
    Base.metadata.create_all(bind=engine)
except Exception as e:
    import logging
    logging.warning(f"Could not connect to database on startup: {e}")
    logging.warning("Please set POSTGRES_URL in your .env file and run migrations.")

app = FastAPI(
    title="Ticket Maker API",
    description="AI-powered support assistant with OpenProject integration",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    project_id: int
    conversation_id: Optional[int] = None


class ConversationCreate(BaseModel):
    project_id: int


# ─────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/projects")
def list_projects():
    """Returns all active projects from OpenProject."""
    try:
        projects = get_projects()
        return {"projects": projects}
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.post("/api/conversations")
def create_conversation(body: ConversationCreate, db: Session = Depends(get_db)):
    """Creates a new conversation tied to a project."""
    conv = Conversation(project_id=str(body.project_id))
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return {"conversation_id": conv.id, "project_id": conv.project_id}


@app.get("/api/conversations/{conversation_id}")
def get_conversation(conversation_id: int, db: Session = Depends(get_db)):
    """Returns all messages in a conversation."""
    conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversa não encontrada")

    messages = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
        .all()
    )
    return {
        "conversation_id": conv.id,
        "project_id": conv.project_id,
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in messages
        ],
    }


@app.post("/api/chat/stream")
async def chat_stream(body: ChatRequest, db: Session = Depends(get_db)):
 
    async def event_generator():
        try:
            async for chunk in stream_agent_response(
                user_message=body.message,
                project_id=body.project_id,
                conversation_id=body.conversation_id,
                db=db,
            ):
                yield chunk
                # Small yield to prevent blocking
                await asyncio.sleep(0)
        except Exception as e:
            import json
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/ingest")
def trigger_ingestion():
    """
    Admin endpoint to re-run document ingestion.
    Runs the ingest pipeline synchronously.
    """
    from pathlib import Path
    from ingest import ingest

    docs_dir = Path(__file__).parent / "docs"
    try:
        ingest(docs_dir, clear=False)
        return {"status": "ok", "message": "Ingestão concluída com sucesso."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

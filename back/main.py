"""
Endpoints públicos:
  POST /api/auth/login            → autentica via SQL function e devolve token
  POST /api/auth/logout           → revoga o token
  GET  /api/auth/me               → dados do usuário corrente + projetos permitidos

  GET  /api/projects              → lista projetos do OpenProject filtrados pelo ACL
  POST /api/conversations         → cria conversa
  GET  /api/conversations         → lista conversas do usuário corrente
  GET  /api/conversations/{cod}   → histórico completo de uma conversa
  POST /api/chat/stream           → SSE com a resposta do agente
  POST /api/ingest                → re-roda a ingestão RAG (operacional)
"""
import asyncio
from typing import Optional
from uuid import UUID as UUIDType

from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from config import FRONTEND_URL, POSTGRES_SCHEMA
from database import _get_engine, get_db
from models import Conversa, Mensagem, Usuario
from openproject_service import get_projects
from agent import stream_agent_response
from auth import (
    authenticate,
    issue_token,
    revoke_token,
    get_current_user,
    get_user_project_ids,
    ensure_user_has_project,
)


# Garante que o schema exista (idempotente).
def _ensure_schema():
    from sqlalchemy import text
    engine = _get_engine()
    with engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS {POSTGRES_SCHEMA}'))


try:
    _ensure_schema()
except Exception as e:
    import logging
    logging.warning(f"Could not connect to database on startup: {e}")


app = FastAPI(
    title="Ticket Maker API",
    description="Assistente de suporte com OpenProject + RAG",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL, "http://localhost:4200"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: str
    senha: str


class ChatRequest(BaseModel):
    message: str
    project_id: int
    conversation_id: Optional[str] = None  # UUID em string
    project_name: Optional[str] = ""


class ConversationCreate(BaseModel):
    project_id: int
    project_name: Optional[str] = None


# ─────────────────────────────────────────────
# Util
# ─────────────────────────────────────────────

def _user_payload(user: Usuario) -> dict:
    return {
        "codigo": str(user.codigo),
        "nome": user.nome,
        "email": user.email,
    }


# ─────────────────────────────────────────────
# Healthcheck
# ─────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


# ─────────────────────────────────────────────
# Auth
# ─────────────────────────────────────────────

@app.post("/api/auth/login")
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = authenticate(db, body.email, body.senha)
    if not user:
        raise HTTPException(status_code=401, detail="E-mail ou senha inválidos.")
    token = issue_token(db, user.codigo)
    project_ids = get_user_project_ids(db, user.codigo)
    return {
        "token": token,
        "user": _user_payload(user),
        "project_ids": project_ids,
    }


@app.post("/api/auth/logout")
def logout(
    db: Session = Depends(get_db),
    x_auth_token: Optional[str] = Header(default=None, alias="X-Auth-Token"),
):
    if x_auth_token:
        revoke_token(db, x_auth_token)
    return {"status": "ok"}


@app.get("/api/auth/me")
def me(user: Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    return {
        "user": _user_payload(user),
        "project_ids": get_user_project_ids(db, user.codigo),
    }


# ─────────────────────────────────────────────
# Projetos (filtrados pelo ACL)
# ─────────────────────────────────────────────

@app.get("/api/projects")
def list_projects(
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
):
    try:
        all_projects = get_projects()
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
    allowed = set(get_user_project_ids(db, user.codigo))
    return {"projects": [p for p in all_projects if p["id"] in allowed]}


# ─────────────────────────────────────────────
# Conversas
# ─────────────────────────────────────────────

@app.post("/api/conversations")
def create_conversation(
    body: ConversationCreate,
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
):
    ensure_user_has_project(db, user, body.project_id)
    conv = Conversa(
        usuario=user.codigo,
        projeto_id=body.project_id,
        projeto_nome=body.project_name,
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return {
        "conversation_id": str(conv.codigo),
        "project_id": conv.projeto_id,
    }


@app.get("/api/conversations")
def list_conversations(
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
):
    convs = (
        db.query(Conversa)
        .filter(Conversa.usuario == user.codigo)
        .order_by(Conversa.atualizacao_dt.desc())
        .all()
    )
    return {
        "conversations": [
            {
                "codigo": str(c.codigo),
                "projeto_id": c.projeto_id,
                "projeto_nome": c.projeto_nome,
                "ticket_numero": c.ticket_numero,
                "criacao_dt": c.criacao_dt.isoformat() if c.criacao_dt else None,
                "atualizacao_dt": c.atualizacao_dt.isoformat() if c.atualizacao_dt else None,
            }
            for c in convs
        ]
    }


@app.get("/api/conversations/{codigo}")
def get_conversation(
    codigo: str,
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
):
    try:
        uid = UUIDType(codigo)
    except ValueError:
        raise HTTPException(status_code=400, detail="codigo inválido")

    conv = db.query(Conversa).filter(Conversa.codigo == uid).first()
    if not conv or conv.usuario != user.codigo:
        raise HTTPException(status_code=404, detail="Conversa não encontrada")

    msgs = (
        db.query(Mensagem)
        .filter(Mensagem.conversa == conv.codigo)
        .order_by(Mensagem.criacao_dt)
        .all()
    )
    return {
        "conversation_id": str(conv.codigo),
        "projeto_id": conv.projeto_id,
        "projeto_nome": conv.projeto_nome,
        "ticket_numero": conv.ticket_numero,
        "messages": [
            {
                "codigo": str(m.codigo),
                "role": m.papel,
                "content": m.conteudo,
                "tools": m.ferramentas,
                "created_at": m.criacao_dt.isoformat() if m.criacao_dt else None,
            }
            for m in msgs
        ],
    }


# ─────────────────────────────────────────────
# Chat SSE
# ─────────────────────────────────────────────

@app.post("/api/chat/stream")
async def chat_stream(
    body: ChatRequest,
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
):
    ensure_user_has_project(db, user, body.project_id)

    conv_uuid: Optional[UUIDType] = None
    if body.conversation_id:
        try:
            conv_uuid = UUIDType(body.conversation_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="conversation_id inválido")

    async def event_generator():
        try:
            async for chunk in stream_agent_response(
                user_message=body.message,
                project_id=body.project_id,
                conversation_id=conv_uuid,
                db=db,
                user=user,
                project_name=body.project_name or "",
            ):
                yield chunk
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


# ─────────────────────────────────────────────
# Ingestão RAG
# ─────────────────────────────────────────────

@app.post("/api/ingest")
def trigger_ingestion(user: Usuario = Depends(get_current_user)):
    from pathlib import Path
    from ingest import ingest

    docs_dir = Path(__file__).parent / "documentacoes_projetos"
    try:
        ingest(docs_dir, clear=False)
        return {"status": "ok", "message": "Ingestão concluída com sucesso."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

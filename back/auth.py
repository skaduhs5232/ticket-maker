import secrets
from typing import Optional, List
from datetime import datetime, timedelta, timezone
from uuid import UUID as UUIDType

from fastapi import Header, HTTPException, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text

from database import get_db
from models import Usuario, UsuarioProjeto, Sessao


TOKEN_TTL_DAYS = 30



def authenticate(db: Session, email: str, senha: str) -> Optional[Usuario]:
    """
    Retorna o Usuario se as credenciais forem válidas; None caso contrário.
    Lança HTTPException 403 se o usuário existir mas estiver desativado.
    """
    try:
        ok = db.execute(
            text("SELECT ticket_maker.usuario_autenticar(:email, :senha)"),
            {"email": email, "senha": senha},
        ).scalar()
    except Exception as e:
        # A função SQL lança "usuário desativado"
        msg = str(e)
        if "desativado" in msg.lower():
            raise HTTPException(status_code=403, detail="Usuário desativado.")
        raise
    if not ok:
        return None
    return (
        db.query(Usuario)
        .filter(text("upper(usuario.email) = upper(:e)"))
        .params(e=email)
        .first()
    )


# ─────────────────────────────────────────────
# Token de sessão
# ─────────────────────────────────────────────
def issue_token(db: Session, user_id: UUIDType) -> str:
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(days=TOKEN_TTL_DAYS)
    db.add(Sessao(token=token, usuario=user_id, expira_dt=expires))
    db.commit()
    return token


def revoke_token(db: Session, token: str) -> None:
    db.query(Sessao).filter(Sessao.token == token).delete()
    db.commit()


def get_user_by_token(db: Session, token: str) -> Optional[Usuario]:
    row = db.query(Sessao).filter(Sessao.token == token).first()
    if not row:
        return None

    if row.expira_dt is not None:
        exp = row.expira_dt
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp < datetime.now(timezone.utc):
            db.delete(row)
            db.commit()
            return None

    user = db.query(Usuario).filter(Usuario.codigo == row.usuario).first()
    if not user or user.desativacao_dt is not None:
        return None
    return user


# ─────────────────────────────────────────────
# Dependências FastAPI
# ─────────────────────────────────────────────
def get_current_user(
    x_auth_token: Optional[str] = Header(default=None, alias="X-Auth-Token"),
    db: Session = Depends(get_db),
) -> Usuario:
    if not x_auth_token:
        raise HTTPException(status_code=401, detail="Token de autenticação ausente")
    user = get_user_by_token(db, x_auth_token)
    if not user:
        raise HTTPException(status_code=401, detail="Token inválido ou expirado")
    return user


def get_user_project_ids(db: Session, user_id: UUIDType) -> List[int]:
    rows = (
        db.query(UsuarioProjeto.projeto_id)
        .filter(UsuarioProjeto.usuario == user_id)
        .all()
    )
    return [int(r[0]) for r in rows]


def ensure_user_has_project(db: Session, user: Usuario, project_id: int) -> None:
    allowed = get_user_project_ids(db, user.codigo)
    if project_id not in allowed:
        raise HTTPException(status_code=403, detail="Você não tem acesso a este projeto.")

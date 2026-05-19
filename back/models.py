from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func, text
from sqlalchemy.orm import relationship

from database import Base


class Usuario(Base):
    __tablename__ = "usuario"

    codigo = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    nome = Column(String, nullable=False)
    email = Column(String, nullable=False, unique=True, index=True)
    senha = Column(Text, nullable=False)  # hash bcrypt gerado por crypt(...)
    perfil = Column(Integer, nullable=False, default=1)
    criacao_dt = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    desativacao_dt = Column(DateTime(timezone=True), nullable=True)

    projetos = relationship("UsuarioProjeto", back_populates="usuario_rel", cascade="all, delete-orphan")
    conversas = relationship("Conversa", back_populates="usuario_rel", cascade="all, delete-orphan")


class UsuarioProjeto(Base):
    __tablename__ = "usuario_projeto"
    __table_args__ = (UniqueConstraint("usuario", "projeto_id", name="usuario_projeto_usuario_projeto_id_key"),)

    codigo = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    usuario = Column(UUID(as_uuid=True), ForeignKey("usuario.codigo", ondelete="CASCADE"), nullable=False, index=True)
    projeto_id = Column(Integer, nullable=False, index=True)
    criacao_dt = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    usuario_rel = relationship("Usuario", back_populates="projetos", foreign_keys=[usuario])


class Sessao(Base):
    __tablename__ = "sessao"

    codigo = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    token = Column(Text, nullable=False, unique=True, index=True)
    usuario = Column(UUID(as_uuid=True), ForeignKey("usuario.codigo", ondelete="CASCADE"), nullable=False, index=True)
    criacao_dt = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expira_dt = Column(DateTime(timezone=True), nullable=True)


class Conversa(Base):
    __tablename__ = "conversa"

    codigo = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    usuario = Column(UUID(as_uuid=True), ForeignKey("usuario.codigo", ondelete="CASCADE"), nullable=False, index=True)
    projeto_id = Column(Integer, nullable=False, index=True)
    projeto_nome = Column(String, nullable=True)
    ticket_numero = Column(Integer, nullable=True)
    criacao_dt = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    atualizacao_dt = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    usuario_rel = relationship("Usuario", back_populates="conversas", foreign_keys=[usuario])
    mensagens = relationship(
        "Mensagem",
        back_populates="conversa_rel",
        cascade="all, delete-orphan",
        order_by="Mensagem.criacao_dt",
    )


class Mensagem(Base):
    __tablename__ = "mensagem"

    codigo = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    conversa = Column(UUID(as_uuid=True), ForeignKey("conversa.codigo", ondelete="CASCADE"), nullable=False, index=True)
    papel = Column(String, nullable=False)  # 'user' | 'ai'
    conteudo = Column(Text, nullable=False)
    ferramentas = Column(JSONB, nullable=True)
    criacao_dt = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    conversa_rel = relationship("Conversa", back_populates="mensagens", foreign_keys=[conversa])

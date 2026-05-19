

CREATE SCHEMA IF NOT EXISTS ticket_maker;
SET search_path TO ticket_maker, extensions, public;

-- Necessária para crypt() / gen_salt() (hash de senhas com bcrypt) e gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS pgcrypto;


-- ─────────────────────────────────────────────────────────────────────────────
-- USUÁRIOS
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ticket_maker.usuario (
    codigo            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nome              VARCHAR(120) NOT NULL,
    email             VARCHAR(160) NOT NULL UNIQUE,
    senha             TEXT NOT NULL,
    perfil            INTEGER NOT NULL DEFAULT 1,
    criacao_dt        TIMESTAMPTZ NOT NULL DEFAULT now(),
    desativacao_dt    TIMESTAMPTZ NULL
);

COMMENT ON TABLE  ticket_maker.usuario IS 'Usuários do Ticket Maker. Insira manualmente via ticket_maker.usuario_inserir().';
COMMENT ON COLUMN ticket_maker.usuario.codigo         IS 'Identificador único do usuário (UUID).';
COMMENT ON COLUMN ticket_maker.usuario.nome           IS 'Nome de exibição do usuário.';
COMMENT ON COLUMN ticket_maker.usuario.email          IS 'E-mail usado como login (case-insensitive na autenticação).';
COMMENT ON COLUMN ticket_maker.usuario.senha          IS 'Hash bcrypt da senha gerado por crypt(...,gen_salt(''bf'')).';
COMMENT ON COLUMN ticket_maker.usuario.perfil         IS '1=usuário comum, 2=admin (reservado para uso futuro).';
COMMENT ON COLUMN ticket_maker.usuario.desativacao_dt IS 'Quando não-nulo, o usuário está desativado e não pode autenticar.';


-- ─────────────────────────────────────────────────────────────────────────────
-- ACL: projetos do OpenProject permitidos por usuário
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ticket_maker.usuario_projeto (
    codigo       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    usuario      UUID NOT NULL REFERENCES ticket_maker.usuario(codigo) ON DELETE CASCADE,
    projeto_id   INTEGER NOT NULL,
    criacao_dt   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (usuario, projeto_id)
);

COMMENT ON TABLE  ticket_maker.usuario_projeto IS 'Associação N:N entre usuário e projetos do OpenProject (ACL).';
COMMENT ON COLUMN ticket_maker.usuario_projeto.usuario    IS 'FK para ticket_maker.usuario.codigo';
COMMENT ON COLUMN ticket_maker.usuario_projeto.projeto_id IS
'ID numérico do projeto no OpenProject. Valores possíveis (snapshot 2026-05-19):
  3  = exitus (Exitus Institucional)
  4  = sigeu (Sigeu)
  5  = painel-de-eventos-unichristus (Painel de Eventos)
  10 = christus-online (Christus Online)
  14 = exitus-educacional (Exitus Educacional)
  16 = christus-online-app (Christus Online APP)
  17 = medsystem (MedSystem)
  20 = inovacao (Inovação)
  21 = suporte (Suporte)
  23 = exitus-livros (Exitus - Livros)';

CREATE INDEX IF NOT EXISTS idx_usuario_projeto_usuario ON ticket_maker.usuario_projeto(usuario);
CREATE INDEX IF NOT EXISTS idx_usuario_projeto_projeto ON ticket_maker.usuario_projeto(projeto_id);


-- ─────────────────────────────────────────────────────────────────────────────
-- Tokens de sessão (login retorna token opaco)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ticket_maker.sessao (
    codigo       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    token        TEXT NOT NULL UNIQUE,
    usuario      UUID NOT NULL REFERENCES ticket_maker.usuario(codigo) ON DELETE CASCADE,
    criacao_dt   TIMESTAMPTZ NOT NULL DEFAULT now(),
    expira_dt    TIMESTAMPTZ NULL
);

COMMENT ON TABLE  ticket_maker.sessao IS 'Tokens opacos de sessão emitidos no login. Use revoke = DELETE.';
COMMENT ON COLUMN ticket_maker.sessao.token     IS 'Token opaco (secrets.token_urlsafe) enviado pelo cliente como header X-Auth-Token.';
COMMENT ON COLUMN ticket_maker.sessao.expira_dt IS 'Quando não-nulo, sessão expira nesta data.';

CREATE INDEX IF NOT EXISTS idx_sessao_usuario ON ticket_maker.sessao(usuario);


-- ─────────────────────────────────────────────────────────────────────────────
-- Histórico de conversas
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ticket_maker.conversa (
    codigo          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    usuario         UUID NOT NULL REFERENCES ticket_maker.usuario(codigo) ON DELETE CASCADE,
    projeto_id      INTEGER NOT NULL,
    projeto_nome    VARCHAR(160) NULL,
    ticket_numero   INTEGER NULL,
    criacao_dt      TIMESTAMPTZ NOT NULL DEFAULT now(),
    atualizacao_dt  TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE  ticket_maker.conversa IS 'Histórico de conversas: cada sessão de chat de um usuário em um projeto.';
COMMENT ON COLUMN ticket_maker.conversa.usuario       IS 'Usuário autor da conversa.';
COMMENT ON COLUMN ticket_maker.conversa.projeto_id    IS 'ID do projeto OpenProject ao qual a conversa se refere (ver ticket_maker.usuario_projeto.projeto_id para a lista).';
COMMENT ON COLUMN ticket_maker.conversa.projeto_nome  IS 'Nome do projeto no momento da conversa (cache).';
COMMENT ON COLUMN ticket_maker.conversa.ticket_numero IS 'Se um ticket foi efetivamente aberto durante a conversa, este é o número (#id) do work_package no OpenProject.';

CREATE INDEX IF NOT EXISTS idx_conversa_usuario ON ticket_maker.conversa(usuario);
CREATE INDEX IF NOT EXISTS idx_conversa_projeto ON ticket_maker.conversa(projeto_id);


-- ─────────────────────────────────────────────────────────────────────────────
-- Mensagens da conversa
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ticket_maker.mensagem (
    codigo       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversa     UUID NOT NULL REFERENCES ticket_maker.conversa(codigo) ON DELETE CASCADE,
    papel        VARCHAR(20) NOT NULL,
    conteudo     TEXT NOT NULL,
    ferramentas  JSONB NULL,
    criacao_dt   TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE  ticket_maker.mensagem IS 'Mensagens trocadas em uma conversa, em ordem cronológica.';
COMMENT ON COLUMN ticket_maker.mensagem.conversa    IS 'FK para ticket_maker.conversa.codigo';
COMMENT ON COLUMN ticket_maker.mensagem.papel       IS 'Papel emissor: user (usuário humano) ou ai (assistente).';
COMMENT ON COLUMN ticket_maker.mensagem.conteudo    IS 'Texto da mensagem.';
COMMENT ON COLUMN ticket_maker.mensagem.ferramentas IS 'JSON com as ferramentas (RAG, busca de tickets, criação de ticket) acionadas pela IA nesta resposta.';
COMMENT ON COLUMN ticket_maker.mensagem.criacao_dt  IS 'Data e hora da mensagem.';

CREATE INDEX IF NOT EXISTS idx_mensagem_conversa ON ticket_maker.mensagem(conversa, criacao_dt);


-- ════════════════════════════════════════════════════════════════════════════
-- FUNÇÕES de administração / autenticação de usuários
-- ════════════════════════════════════════════════════════════════════════════

-- ─── inserir usuário ──────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION ticket_maker.usuario_inserir(
    p_nome    VARCHAR,
    p_email   VARCHAR,
    p_senha   VARCHAR,
    p_perfil  INTEGER DEFAULT 1
)
RETURNS UUID
LANGUAGE plpgsql
AS $function$
DECLARE
    v_codigo UUID;
BEGIN
    INSERT INTO ticket_maker.usuario (nome, email, senha, perfil)
    VALUES (p_nome, p_email, crypt(p_senha, gen_salt('bf')), p_perfil)
    RETURNING codigo INTO v_codigo;

    RETURN v_codigo;
EXCEPTION
    WHEN unique_violation THEN
        RAISE EXCEPTION 'E-mail já cadastrado: %', p_email;
    WHEN OTHERS THEN
        RAISE EXCEPTION 'Erro ao inserir usuário: %', SQLERRM;
END;
$function$;

COMMENT ON FUNCTION ticket_maker.usuario_inserir(VARCHAR, VARCHAR, VARCHAR, INTEGER) IS
'Insere um novo usuário, aplicando hash bcrypt na senha. Retorna o UUID gerado.
Exemplo:
  SELECT ticket_maker.usuario_inserir(''Maria Silva'', ''maria@empresa.com'', ''senha123'');
Depois associe os projetos do OpenProject que ela pode acessar:
  INSERT INTO ticket_maker.usuario_projeto (usuario, projeto_id) VALUES (<uuid>, 17);';


-- ─── autenticar ───────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION ticket_maker.usuario_autenticar(
    p_email VARCHAR,
    p_senha VARCHAR
)
RETURNS BOOLEAN
LANGUAGE plpgsql
AS $function$
DECLARE
    v_hash           TEXT;
    v_desativacao_dt TIMESTAMPTZ;
BEGIN
    SELECT senha, desativacao_dt
      INTO v_hash, v_desativacao_dt
      FROM ticket_maker.usuario
     WHERE upper(email) = upper(p_email);

    IF v_desativacao_dt IS NOT NULL THEN
        RAISE EXCEPTION 'usuário desativado';
    END IF;

    IF v_hash IS NULL THEN
        RETURN FALSE;
    END IF;

    RETURN v_hash = crypt(p_senha, v_hash);
END;
$function$;

COMMENT ON FUNCTION ticket_maker.usuario_autenticar(VARCHAR, VARCHAR) IS
'Retorna TRUE se a senha bate com o hash do usuário identificado pelo e-mail.
Lança exceção se o usuário estiver desativado.';


-- ─── atualizar senha ──────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION ticket_maker.usuario_atualizar_senha(
    p_codigo       UUID,
    p_senha_atual  VARCHAR,
    p_nova_senha   VARCHAR
)
RETURNS BOOLEAN
LANGUAGE plpgsql
AS $function$
DECLARE
    v_senha_hash TEXT;
BEGIN
    SELECT senha INTO v_senha_hash
      FROM ticket_maker.usuario
     WHERE codigo = p_codigo;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Usuário com código % não encontrado.', p_codigo;
    END IF;

    IF crypt(p_senha_atual, v_senha_hash) != v_senha_hash THEN
        RAISE EXCEPTION 'Senha atual incorreta.';
    END IF;

    UPDATE ticket_maker.usuario
       SET senha = crypt(p_nova_senha, gen_salt('bf'))
     WHERE codigo = p_codigo;

    RETURN TRUE;
EXCEPTION
    WHEN OTHERS THEN
        RAISE EXCEPTION 'Erro ao atualizar senha: %', SQLERRM;
END;
$function$;

COMMENT ON FUNCTION ticket_maker.usuario_atualizar_senha(UUID, VARCHAR, VARCHAR) IS
'Atualiza a senha de um usuário se a senha atual conferir.';

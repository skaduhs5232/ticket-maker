import json
import re
import asyncio
from typing import AsyncGenerator, List

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import (
    HumanMessage,
    AIMessage,
    SystemMessage,
    BaseMessage,
)
from langchain_core.tools import tool
from sqlalchemy.orm import Session

from rag import search_documents, format_context
from openproject_service import (
    search_work_packages,
    create_work_package,
)
from models import Conversa, Mensagem, Usuario
from config import GEMINI_API_KEY, OPENPROJECT_SUPPORT_PROJECT_ID

SYSTEM_PROMPT = """Você é um assistente de suporte técnico inteligente chamado **Ticket Maker**.
Seu objetivo é ajudar os usuários a resolver problemas relacionados aos sistemas da empresa.

## ⚠️ REGRAS CRÍTICAS DE FORMATO DE SAÍDA — NUNCA VIOLAR

Você tem acesso a ferramentas (function calling) que são invocadas pela plataforma. Você JAMAIS deve:
- Escrever blocos como ```tool_code, ```python, ```default_api, ou qualquer pseudo-código simulando chamadas de função (ex.: `print(default_api.create_ticket(...))`).
- Mencionar nomes de ferramentas, nomes de funções, parâmetros, ou IDs internos na sua resposta visível ao usuário.
- Expor URLs internas (como `http://openproject...`), identificadores do OpenProject, ou estrutura do sistema.

Quando precisar usar uma ferramenta, simplesmente invoque-a pelo mecanismo de tool calling (não escreva nada sobre isso ao usuário). Quando responder ao usuário, escreva apenas linguagem natural em português do Brasil, sem código.

## ⚠️ REGRA CRÍTICA — NUNCA INVENTE NÚMEROS DE TICKET

É **proibido** mencionar um número de ticket (ex.: "#813", "ticket 813") antes de a ferramenta `create_ticket` ter sido executada com sucesso E ter retornado o número real. Você só pode citar um número de ticket DEPOIS de receber a confirmação da ferramenta com aquele número específico.

Sequência obrigatória ao criar um ticket:
1. Pedir confirmação ao usuário.
2. Após o "sim", chamar `create_ticket` (sem dizer nada antes).
3. Esperar o retorno da ferramenta com o número real.
4. Só então responder ao usuário citando esse número.

Se a ferramenta falhar, NÃO invente número — diga ao usuário que houve uma falha e ofereça tentar novamente.

## ⚠️ REGRA OBRIGATÓRIA — Sempre consultar a base de conhecimento PRIMEIRO

Na PRIMEIRA mensagem do usuário (e sempre que ele descrever um novo problema), você DEVE chamar a ferramenta `search_knowledge_base` ANTES de qualquer outra coisa — antes mesmo de pedir esclarecimentos. A base de conhecimento já contém o contexto do sistema que o usuário está utilizando (o produto vem pré-definido pelo projeto selecionado). NÃO pergunte ao usuário qual sistema ele está usando — você já sabe.

Use o conteúdo retornado pela `search_knowledge_base` para:
- Entender qual é o produto/sistema do usuário e suas funcionalidades.
- Tentar responder a dúvida diretamente.
- Só então, se precisar de mais detalhes, faça perguntas direcionadas.

## Fluxo de investigação e abertura de ticket

1. **Investigar profundamente antes de criar o ticket**: Sua missão é coletar TODO o contexto necessário para que o time de suporte resolva o problema sem precisar entrar em contato com o usuário. Antes de abrir um chamado, conduza uma conversa de investigação cobrindo, no mínimo:
   - **O que o usuário estava tentando fazer** (objetivo / fluxo).
   - **O que aconteceu** (comportamento observado, mensagem de erro literal, screenshot mental dos campos preenchidos).
   - **O que ele esperava que acontecesse**.
   - **Quando começou e com que frequência ocorre** (sempre, intermitente, primeira vez).
   - **Passos para reproduzir** (sequência exata de telas/cliques).
   - **Ambiente** (navegador/dispositivo, se relevante).
   - **Impacto** (bloqueia o trabalho, é incômodo, urgência).
   Faça perguntas em rodadas curtas (1 a 3 perguntas por vez) até ter uma visão completa.

2. **Verificar duplicatas**: Antes de criar, SEMPRE use `search_existing_tickets` para verificar se já existe uma demanda similar em aberto no projeto do produto.

3. **Confirmar com o usuário** antes de criar o ticket: pergunte se ele autoriza a abertura.

4. **Criar ticket com descrição RICA**: ao chamar `create_ticket`, a descrição DEVE estar formatada em Markdown com seções claras. Use o seguinte template:

   ```
   ## Resumo
   <uma frase descrevendo o problema>

   ## Comportamento observado
   <o que está acontecendo, com detalhes coletados na conversa>

   ## Comportamento esperado
   <o que o usuário esperava>

   ## Passos para reproduzir
   1. ...
   2. ...
   3. ...

   ## Mensagem de erro / evidências
   <transcrever literalmente qualquer mensagem de erro mencionada>

   ## Frequência
   <sempre / intermitente / primeira vez>

   ## Impacto
   <bloqueio / incômodo / sugestão>

   ## Contexto adicional
   <ambiente, navegador, módulo afetado, qualquer informação extra que ajude>
   ```

   Nunca crie um ticket com descrição curta ou genérica. Se faltar informação, continue investigando antes de chamar a ferramenta.

5. **Onde os tickets são criados**: TODOS os tickets são abertos automaticamente no projeto central **"Suporte"** do OpenProject. Você não precisa (nem pode) especificar projeto — a ferramenta cuida disso.

6. **Comunicar o resultado**: Após criar um ticket, escreva uma resposta natural confirmando a abertura e informando APENAS o número (ex.: "#681"). Não inclua URL, link, status técnico ou nomes de ferramentas.

## Diretrizes de comportamento
- Seja empático, profissional e direto.
- Responda sempre em **português do Brasil**.
- Se a base de conhecimento não tiver informações suficientes, seja honesto e siga investigando.
- Nunca crie tickets duplicados.
- NUNCA exponha URLs, IDs internos, nomes de ferramentas ou blocos de código de chamada de função.
- NUNCA pergunte qual sistema/software o usuário está usando — você já sabe pelo contexto do projeto.
"""


#funções e tools para o gemni acessar

def make_tools(
    project_id: int,
    project_name: str = "",
    user_name: str | None = None,
    user_email: str | None = None,
):
    """Create tool instances bound to the current project + user context."""

    @tool
    def search_knowledge_base(query: str) -> str:
        """
        Searches the internal knowledge base (RAG) for information about the system.
        Use this tool BEFORE creating a ticket to try to solve the user's problem.
        Also use it whenever you need technical information about how the system works.

        Args:
            query: The question or topic to search for in the knowledge base.
        """
        try:
            docs = search_documents(query, project_id=str(project_id), k=4)
            return format_context(docs)
        except Exception as e:
            return f"Erro ao consultar base de conhecimento: {e}"

    @tool
    def search_existing_tickets(query: str) -> str:
        """
        Searches for existing tickets/work packages related to the product the user
        is currently asking about (the project bound to this conversation).
        ALWAYS use this before creating a new ticket to avoid duplicates.

        Args:
            query: Keywords describing the problem to search for in existing tickets.
        """
        try:
            results = search_work_packages(project_id, query, limit=5)
            if not results:
                return "Nenhum ticket similar encontrado."
            lines = ["Tickets similares encontrados:"]
            for t in results:
                # NÃO incluir URL — ela é interna e não deve ser exposta ao usuário final.
                lines.append(f"- #{t['id']} [{t['status']}] {t['subject']}")
            return "\n".join(lines)
        except Exception as e:
            return f"Erro ao buscar tickets: {e}"

    @tool
    def create_ticket(subject: str, description: str) -> str:
        """
        Creates a new ticket (work package) in the OpenProject "Suporte" project.
        All tickets are always created in the central Suporte project, regardless
        of which product the user is asking about. The product context is included
        in the ticket description.

        Only use this after:
        1. Confirming the knowledge base cannot solve the issue.
        2. Confirming no similar ticket already exists.
        3. Getting the user's confirmation to open a ticket.

        Args:
            subject: A clear, concise title for the ticket (max 120 chars).
            description: A detailed description of the problem, including steps to reproduce,
                         expected behavior, and actual behavior. Use Markdown formatting.
        """
        try:
            # Prefixa contexto do projeto-fonte e identificação do usuário na
            # descrição para que o time de suporte saiba quem abriu e sobre qual sistema.
            header_lines = []
            if user_name:
                contact = user_name
                if user_email:
                    contact += f" ({user_email})"
                header_lines.append(f"**Solicitante:** {contact}")
            project_label = f"#{project_id}"
            if project_name:
                project_label = f"{project_name} (#{project_id})"
            header_lines.append(f"**Sistema relacionado:** {project_label}")
            header = "\n".join(header_lines)

            full_description = f"{header}\n\n---\n\n{description}"
            result = create_work_package(
                OPENPROJECT_SUPPORT_PROJECT_ID, subject, full_description
            )
            # IMPORTANTE: NÃO retornar URL do OpenProject — o usuário final não deve vê-la.
            return (
                f"✅ Ticket criado com sucesso no projeto Suporte!\n"
                f"- Número: #{result['id']}\n"
                f"- Título: {result['subject']}\n"
                f"- Status: {result['status']}"
            )
        except Exception as e:
            return f"Erro ao criar ticket: {e}"

    return [search_knowledge_base, search_existing_tickets, create_ticket]




def _load_history(db: Session, conversa_id) -> List[BaseMessage]:
    """Carrega o histórico de mensagens de uma conversa."""
    rows = (
        db.query(Mensagem)
        .filter(Mensagem.conversa == conversa_id)
        .order_by(Mensagem.criacao_dt)
        .all()
    )
    history: List[BaseMessage] = []
    for msg in rows:
        if msg.papel == "user":
            history.append(HumanMessage(content=msg.conteudo))
        else:
            history.append(AIMessage(content=msg.conteudo))
    return history


def _save_message(db: Session, conversa_id, role: str, content: str, tools_used: list | None = None):
    msg = Mensagem(
        conversa=conversa_id,
        papel=role,
        conteudo=content,
        ferramentas=tools_used,
    )
    db.add(msg)
    # Atualiza o atualizacao_dt da conversa
    from sqlalchemy.sql import func
    db.query(Conversa).filter(Conversa.codigo == conversa_id).update(
        {"atualizacao_dt": func.now()}
    )
    db.commit()


def get_or_create_conversation(
    db: Session,
    conversation_id,
    project_id: int,
    user: Usuario,
    project_name: str = "",
) -> Conversa:
    if conversation_id:
        conv = db.query(Conversa).filter(Conversa.codigo == conversation_id).first()
        if conv:
            # Garante que a conversa pertence ao usuário corrente.
            if conv.usuario != user.codigo:
                raise PermissionError("Conversa pertence a outro usuário.")
            return conv

    conv = Conversa(
        usuario=user.codigo,
        projeto_id=project_id,
        projeto_nome=project_name or None,
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


# ─────────────────────────────────────────────
# Streaming agent
# ─────────────────────────────────────────────

async def stream_agent_response(
    user_message: str,
    project_id: int,
    conversation_id,
    db: Session,
    user: Usuario,
    project_name: str = "",
) -> AsyncGenerator[str, None]:
    """
    Run the LangChain + Gemini agent with tool calling and yield SSE chunks.
    Saves user message and full AI response to the database.
    """
    # 1. Get/Create conversation
    conv = get_or_create_conversation(db, conversation_id, project_id, user=user, project_name=project_name)

    # 2. Save user message
    _save_message(db, conv.codigo, "user", user_message)

    # 3. Build message history
    history = _load_history(db, conv.codigo)

    # 4. Configure LLM with tools
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.0-flash",
        google_api_key=GEMINI_API_KEY,
        temperature=0.3,
        streaming=True,
    )
    tools = make_tools(
        project_id,
        project_name=project_name,
        user_name=user.nome,
        user_email=user.email,
    )
    llm_with_tools = llm.bind_tools(tools)

    # 5. Build the full message list: system + history
    messages: List[BaseMessage] = [SystemMessage(content=SYSTEM_PROMPT)] + history

    # 6. Tool calling loop (max 5 rounds to avoid infinite loops)
    full_response = ""
    max_rounds = 5
    # Rastreia tickets criados *nesta* turn — usado para detectar alucinação de número.
    created_ticket_ids: list[int] = []
    # Ferramentas acionadas nesta resposta (para persistir na coluna 'ferramentas').
    tools_used: list[dict] = []

    for _ in range(max_rounds):
        response = await llm_with_tools.ainvoke(messages)

        # Check for tool calls
        if hasattr(response, "tool_calls") and response.tool_calls:
            # Add AI's tool call message to context
            messages.append(response)

            # Execute each tool and append results
            tool_map = {t.name: t for t in tools}
            for tc in response.tool_calls:
                tool_name = tc["name"]
                tool_args = tc["args"]
                tool_call_id = tc["id"]

                # Signal tool usage start to frontend
                tool_event = json.dumps({
                    "type": "tool_call",
                    "tool": tool_name,
                    "args": tool_args,
                    "id": tool_call_id,
                })
                yield f"data: {tool_event}\n\n"

                # Run the tool
                if tool_name in tool_map:
                    try:
                        result = tool_map[tool_name].invoke(tool_args)
                    except Exception as e:
                        result = f"Erro na ferramenta {tool_name}: {e}"
                else:
                    result = f"Ferramenta desconhecida: {tool_name}"

                # Captura o número real do ticket criado para validação posterior.
                if tool_name == "create_ticket" and isinstance(result, str):
                    m = re.search(r"Número:\s*#(\d+)", result)
                    if m:
                        created_ticket_ids.append(int(m.group(1)))

                # Registra a ferramenta acionada (para persistir junto da resposta).
                tools_used.append({
                    "tool": tool_name,
                    "args": tool_args,
                    "ok": not str(result).lower().startswith("erro"),
                })

                # Signal tool completion to frontend (so loaders can stop spinning).
                tool_done_event = json.dumps({
                    "type": "tool_result",
                    "tool": tool_name,
                    "id": tool_call_id,
                })
                yield f"data: {tool_done_event}\n\n"

                from langchain_core.messages import ToolMessage
                messages.append(
                    ToolMessage(
                        content=str(result),
                        tool_call_id=tool_call_id,
                    )
                )
        else:
            # Final response — coletar tudo primeiro, validar, e então streamar.
            final_llm = ChatGoogleGenerativeAI(
                model="gemini-2.0-flash",
                google_api_key=GEMINI_API_KEY,
                temperature=0.3,
                streaming=True,
            )
            buffered = ""
            async for chunk in final_llm.astream(messages):
                token = chunk.content
                if token:
                    buffered += token

            # ── Guardrail anti-ticket-fantasma ────────────────────────────────
            # Se a resposta menciona "ticket #N" mas nenhum ticket foi criado,
            # OU menciona um número diferente do realmente criado, reescrevemos.
            buffered = _enforce_ticket_truth(buffered, created_ticket_ids)

            # Streama em pequenos pedaços para preservar o feel de typing.
            full_response = buffered
            chunk_size = 8
            for i in range(0, len(buffered), chunk_size):
                piece = buffered[i:i + chunk_size]
                event = json.dumps({"type": "token", "content": piece})
                yield f"data: {event}\n\n"
                await asyncio.sleep(0.01)
            break

    # 7. Persiste resposta da IA e atualiza ticket_numero da conversa, se houver.
    if full_response:
        _save_message(db, conv.codigo, "ai", full_response, tools_used=tools_used or None)

    if created_ticket_ids:
        # Pega o último ticket criado nesta turn como o "principal" da conversa.
        db.query(Conversa).filter(Conversa.codigo == conv.codigo).update(
            {"ticket_numero": created_ticket_ids[-1]}
        )
        db.commit()

    # 8. Signal completion with conversation_id (UUID em string)
    done_event = json.dumps({"type": "done", "conversation_id": str(conv.codigo)})
    yield f"data: {done_event}\n\n"


def _enforce_ticket_truth(text: str, created_ids: list[int]) -> str:
    """
    Guardrail determinístico: o modelo às vezes inventa um número de ticket
    antes mesmo de chamar `create_ticket` (alucinação). Esta função compara o
    que foi *realmente* criado com o que aparece no texto e corrige.
    """
    # Procura padrões como "#123" ou "ticket 123"
    mentioned = [int(n) for n in re.findall(r"#(\d{1,10})", text)]
    mentioned += [int(n) for n in re.findall(r"\bticket\s+(?:n[°º]?\s*)?(\d{1,10})", text, flags=re.IGNORECASE)]
    mentioned_set = set(mentioned)
    real_set = set(created_ids)

    # Caso 1: o modelo afirmou que criou um ticket, mas não criou nenhum.
    if mentioned_set and not real_set:
        return (
            "Não consegui criar o ticket agora — houve uma falha técnica ao "
            "registrá-lo no sistema. Posso tentar novamente? Se preferir, "
            "podemos revisar as informações antes de uma nova tentativa."
        )

    # Caso 2: o modelo mencionou um número que não bate com o realmente criado.
    if real_set and mentioned_set and not mentioned_set.issubset(real_set):
        for fake in mentioned_set - real_set:
            text = re.sub(rf"#\s*{fake}\b", f"#{next(iter(real_set))}", text)
            text = re.sub(
                rf"\bticket\s+(?:n[°º]?\s*)?{fake}\b",
                f"ticket #{next(iter(real_set))}",
                text,
                flags=re.IGNORECASE,
            )

    return text

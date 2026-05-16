import os
import json
from typing import AsyncGenerator, List
from dotenv import load_dotenv

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
from models import Conversation, Message

load_dotenv()

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

SYSTEM_PROMPT = """Você é um assistente de suporte técnico inteligente chamado **Ticket Maker**.
Seu objetivo é ajudar os usuários a resolver problemas relacionados aos sistemas da empresa.

## Suas responsabilidades:

1. **Tentar resolver primeiro**: Antes de criar qualquer ticket, use a base de conhecimento para tentar resolver o problema do usuário. Consulte a ferramenta `search_knowledge_base` sempre que precisar de informações sobre o sistema.

2. **Investigar a demanda**: Faça perguntas claras para entender:
   - O que o usuário estava tentando fazer
   - O que aconteceu de errado (mensagem de erro, comportamento inesperado)
   - Com que frequência acontece (sempre, às vezes, uma única vez)

3. **Verificar duplicatas**: Antes de criar um ticket, SEMPRE use `search_existing_tickets` para verificar se já existe uma demanda similar em aberto.

4. **Criar ticket apenas quando necessário**: Crie um ticket somente se:
   - O problema não puder ser resolvido com orientações
   - Não existir ticket similar já aberto
   - O usuário confirmar que deseja abrir um chamado

5. **Comunicar claramente**: Ao criar um ticket, informe o usuário com o link e o número do ticket criado.

## Diretrizes de comportamento:
- Seja empático e profissional.
- Responda sempre em **português do Brasil**.
- Se a base de conhecimento não tiver informações suficientes, seja honesto e prossiga para criar um ticket.
- Nunca crie tickets duplicados.
- Se criar um ticket, forneça o link direto ao usuário.
"""


# ─────────────────────────────────────────────
# Tools (Function Calling para o Gemini)
# ─────────────────────────────────────────────

def make_tools(project_id: int):
    """Create tool instances bound to the current project context."""

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
        Searches for existing tickets/work packages in OpenProject that are similar to the user's problem.
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
                lines.append(
                    f"- #{t['id']} [{t['status']}] {t['subject']} → {t['url']}"
                )
            return "\n".join(lines)
        except Exception as e:
            return f"Erro ao buscar tickets: {e}"

    @tool
    def create_ticket(subject: str, description: str) -> str:
        """
        Creates a new ticket (work package) in OpenProject for the current project.
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
            result = create_work_package(project_id, subject, description)
            return (
                f"✅ Ticket criado com sucesso!\n"
                f"- Número: #{result['id']}\n"
                f"- Título: {result['subject']}\n"
                f"- Status: {result['status']}\n"
                f"- Link: {result['url']}"
            )
        except Exception as e:
            return f"Erro ao criar ticket: {e}"

    return [search_knowledge_base, search_existing_tickets, create_ticket]


# ─────────────────────────────────────────────
# History helpers
# ─────────────────────────────────────────────

def _load_history(db: Session, conversation_id: int) -> List[BaseMessage]:
    """Load conversation history from the database."""
    messages = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
        .all()
    )
    history = []
    for msg in messages:
        if msg.role == "user":
            history.append(HumanMessage(content=msg.content))
        else:
            history.append(AIMessage(content=msg.content))
    return history


def _save_message(db: Session, conversation_id: int, role: str, content: str):
    """Persist a single message to the database."""
    msg = Message(
        conversation_id=conversation_id,
        role=role,
        content=content,
    )
    db.add(msg)
    db.commit()


def get_or_create_conversation(
    db: Session, conversation_id: int | None, project_id: int
) -> Conversation:
    """Return existing conversation or create a new one."""
    if conversation_id:
        conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
        if conv:
            return conv
    conv = Conversation(project_id=str(project_id))
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
    conversation_id: int | None,
    db: Session,
) -> AsyncGenerator[str, None]:
    """
    Run the LangChain + Gemini agent with tool calling and yield SSE chunks.
    Saves user message and full AI response to the database.
    """
    # 1. Get/Create conversation
    conv = get_or_create_conversation(db, conversation_id, project_id)

    # 2. Save user message
    _save_message(db, conv.id, "user", user_message)

    # 3. Build message history
    history = _load_history(db, conv.id)

    # 4. Configure LLM with tools
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.0-flash",
        google_api_key=GEMINI_API_KEY,
        temperature=0.3,
        streaming=True,
    )
    tools = make_tools(project_id)
    llm_with_tools = llm.bind_tools(tools)

    # 5. Build the full message list: system + history
    messages: List[BaseMessage] = [SystemMessage(content=SYSTEM_PROMPT)] + history

    # 6. Tool calling loop (max 5 rounds to avoid infinite loops)
    full_response = ""
    max_rounds = 5

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

                # Signal tool usage to frontend
                tool_event = json.dumps({
                    "type": "tool_call",
                    "tool": tool_name,
                    "args": tool_args,
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

                from langchain_core.messages import ToolMessage
                messages.append(
                    ToolMessage(
                        content=str(result),
                        tool_call_id=tc["id"],
                    )
                )
        else:
            # Final response — stream it token by token
            final_llm = ChatGoogleGenerativeAI(
                model="gemini-2.0-flash",
                google_api_key=GEMINI_API_KEY,
                temperature=0.3,
                streaming=True,
            )
            async for chunk in final_llm.astream(messages):
                token = chunk.content
                if token:
                    full_response += token
                    event = json.dumps({"type": "token", "content": token})
                    yield f"data: {event}\n\n"
            break

    # 7. Save the AI response to the database
    if full_response:
        _save_message(db, conv.id, "ai", full_response)

    # 8. Signal completion with conversation_id
    done_event = json.dumps({"type": "done", "conversation_id": conv.id})
    yield f"data: {done_event}\n\n"

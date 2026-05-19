from typing import List

from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_postgres import PGVector
from langchain_core.documents import Document

from config import GEMINI_API_KEY, POSTGRES_URL_WITH_SEARCH_PATH as POSTGRES_URL

COLLECTION_NAME = "ticket_maker_rag"

def get_embeddings():
    """Return the configured Google GenAI embeddings model."""
    return GoogleGenerativeAIEmbeddings(
        model="models/gemini-embedding-001",
        google_api_key=GEMINI_API_KEY,
    )

def get_vector_store() -> PGVector:
    """Return a configured PGVector store connected to PostgreSQL."""
    return PGVector(
        embeddings=get_embeddings(),
        collection_name=COLLECTION_NAME,
        connection=POSTGRES_URL,
        use_jsonb=True,
    )

def search_documents(query: str, project_id: str, k: int = 5) -> List[Document]:
    """
    Search the vector store for documents related to the query.
    If project_id is provided, filter results by that project.
    """
    store = get_vector_store()

    filter_dict = {}
    if project_id:
        filter_dict = {"project_id": project_id}

    results = store.similarity_search(
        query,
        k=k,
        filter=filter_dict if filter_dict else None,
    )
    return results

def format_context(documents: List[Document]) -> str:
    """Format retrieved documents into a single context string for the LLM."""
    if not documents:
        return "Nenhum documento relevante encontrado na base de conhecimento."

    parts = []
    for i, doc in enumerate(documents, 1):
        source = doc.metadata.get("source", "desconhecido")
        project = doc.metadata.get("project_name", "")
        header = f"[{i}] Fonte: {source}"
        if project:
            header += f" | Projeto: {project}"
        parts.append(f"{header}\n{doc.page_content}")

    return "\n\n---\n\n".join(parts)

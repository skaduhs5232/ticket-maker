import os
import sys
import argparse
from pathlib import Path
from typing import List
from dotenv import load_dotenv

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter, MarkdownHeaderTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_postgres import PGVector

load_dotenv()

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
POSTGRES_URL = os.environ.get(
    "POSTGRES_URL", "postgresql://postgres:postgres@localhost:5432/ticket_maker"
)
COLLECTION_NAME = "ticket_maker_rag"

def load_markdown_docs(docs_dir: Path) -> List[Document]:
    """
    Recursively reads all .md files from the docs directory.
    Each subdirectory name is used as the project_name metadata.
    """
    documents = []
    md_files = list(docs_dir.rglob("*.md"))

    if not md_files:
        print(f"⚠️  Nenhum arquivo .md encontrado em: {docs_dir}")
        return documents

    print(f"📂 Encontrados {len(md_files)} arquivo(s) Markdown para processar...")

    for md_file in md_files:
        if md_file.name == "README.md":
            continue

        # Determine project from immediate subfolder of docs_dir
        relative = md_file.relative_to(docs_dir)
        parts = relative.parts
        project_name = parts[0] if len(parts) > 1 else "geral"

        content = md_file.read_text(encoding="utf-8")

        doc = Document(
            page_content=content,
            metadata={
                "source": str(md_file.relative_to(docs_dir)),
                "project_name": project_name,
                "file_name": md_file.name,
            },
        )
        documents.append(doc)
        print(f"  ✅ Carregado: {relative} (projeto: {project_name})")

    return documents


def split_documents(documents: List[Document]) -> List[Document]:
    """
    Splits documents preserving Markdown headers as context, then
    applies a recursive character splitter for smaller chunks.
    """
    # Stage 1: Split by Markdown headers to preserve hierarchy
    header_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=[
            ("#", "Header 1"),
            ("##", "Header 2"),
            ("###", "Header 3"),
        ],
        strip_headers=False,
    )

    # Stage 2: Fine-grained splitting with overlap
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=150,
        length_function=len,
        separators=["\n\n", "\n", " ", ""],
    )

    all_chunks = []
    for doc in documents:
        # First split by headers
        header_splits = header_splitter.split_text(doc.page_content)

        # Then fine-split each header block
        for split in header_splits:
            # Propagate original metadata to all chunks
            split.metadata.update(doc.metadata)

        fine_splits = text_splitter.split_documents(header_splits)
        all_chunks.extend(fine_splits)

    return all_chunks


def ingest(docs_dir: Path, clear: bool = False):
    """Main ingestion pipeline."""
    print("\n🚀 Iniciando ingestão de documentos RAG...")
    print(f"   Diretório: {docs_dir.resolve()}")
    print(f"   PostgreSQL: {POSTGRES_URL.split('@')[-1] if '@' in POSTGRES_URL else POSTGRES_URL}")

    # Load
    documents = load_markdown_docs(docs_dir)
    if not documents:
        print("\n❌ Nenhum documento para processar. Abortando.")
        sys.exit(0)

    # Split
    print(f"\n✂️  Dividindo {len(documents)} documento(s) em chunks...")
    chunks = split_documents(documents)
    print(f"   {len(chunks)} chunk(s) gerados.")

    # Embed & Store
    print(f"\n🤖 Gerando embeddings e salvando no PostgreSQL...")
    embeddings = GoogleGenerativeAIEmbeddings(
        model="models/text-embedding-004",
        google_api_key=GEMINI_API_KEY,
    )

    if clear:
        print("   🗑️  Limpando coleção existente...")
        store = PGVector(
            embeddings=embeddings,
            collection_name=COLLECTION_NAME,
            connection=POSTGRES_URL,
            use_jsonb=True,
        )
        store.delete_collection()
        print("   ✅ Coleção limpa.")

    store = PGVector.from_documents(
        documents=chunks,
        embedding=embeddings,
        collection_name=COLLECTION_NAME,
        connection=POSTGRES_URL,
        use_jsonb=True,
    )

    print(f"\n✅ Ingestão concluída! {len(chunks)} chunk(s) salvos na coleção '{COLLECTION_NAME}'.")
    return store


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingestão de documentos Markdown para o RAG")
    parser.add_argument(
        "--docs-dir",
        type=Path,
        default=Path(__file__).parent / "docs",
        help="Diretório raiz dos documentos Markdown (padrão: ./docs)",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Limpa a coleção do PgVector antes de reingerir",
    )
    args = parser.parse_args()

    ingest(args.docs_dir, clear=args.clear)

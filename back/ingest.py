import sys
import argparse
from pathlib import Path
from typing import List, Dict, Optional

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter, MarkdownHeaderTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_postgres import PGVector

from config import GEMINI_API_KEY, POSTGRES_URL_WITH_SEARCH_PATH as POSTGRES_URL
from openproject_service import get_projects

COLLECTION_NAME = "ticket_maker_rag"


def _normalize(s: str) -> str:
    """Normaliza nomes para comparação (case-insensitive, sem espaços/acentos básicos)."""
    import unicodedata
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.lower().replace("_", "").replace("-", "").replace(" ", "")


def map_folders_to_openproject(docs_dir: Path) -> Dict[str, Dict]:
    """
    Lista as subpastas de docs_dir e tenta casar cada uma com um projeto do
    OpenProject (por identifier ou name normalizados).

    Retorna: { folder_name: {"id": int, "name": str, "identifier": str} }
    """
    print("\n Consultando projetos do OpenProject para mapeamento...")
    op_projects = get_projects()
    print(f"   {len(op_projects)} projeto(s) disponíveis no OpenProject.")

    folders = [p for p in docs_dir.iterdir() if p.is_dir()]
    mapping: Dict[str, Dict] = {}

    for folder in folders:
        norm_folder = _normalize(folder.name)
        match = None
        for proj in op_projects:
            if _normalize(proj["identifier"]) == norm_folder or _normalize(proj["name"]) == norm_folder:
                match = proj
                break

        if match:
            mapping[folder.name] = {
                "id": match["id"],
                "name": match["name"],
                "identifier": match["identifier"],
            }
            print(f"   ✅ {folder.name} → OpenProject #{match['id']} ({match['name']})")
        else:
            print(f"   ⚠️  {folder.name}: nenhum projeto correspondente no OpenProject (será ingerido sem project_id)")
            mapping[folder.name] = {"id": None, "name": folder.name, "identifier": folder.name}

    return mapping


def load_markdown_docs(docs_dir: Path, folder_map: Dict[str, Dict]) -> List[Document]:
    """
    Lê recursivamente os arquivos .md do diretório.
    O nome da subpasta imediata é usado para casar com um projeto do OpenProject,
    e o project_id resultante é salvo nos metadados (usado depois pelo filtro do RAG).
    """
    documents = []
    md_files = list(docs_dir.rglob("*.md"))

    if not md_files:
        print(f"⚠️  Nenhum arquivo .md encontrado em: {docs_dir}")
        return documents

    print(f"\n📂 Encontrados {len(md_files)} arquivo(s) Markdown para processar...")

    for md_file in md_files:
        if md_file.name == "README.md":
            continue

        relative = md_file.relative_to(docs_dir)
        parts = relative.parts
        folder_name = parts[0] if len(parts) > 1 else "geral"

        proj = folder_map.get(folder_name, {"id": None, "name": folder_name, "identifier": folder_name})

        content = md_file.read_text(encoding="utf-8")
        if not content.strip():
            print(f"  ⏭️  Pulando arquivo vazio: {relative}")
            continue

        doc = Document(
            page_content=content,
            metadata={
                "source": str(relative),
                "project_id": str(proj["id"]) if proj["id"] is not None else "",
                "project_name": proj["name"],
                "project_identifier": proj["identifier"],
                "file_name": md_file.name,
            },
        )
        documents.append(doc)
        print(f"  ✅ Carregado: {relative} (projeto: {proj['name']} | id={proj['id']})")

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

    # Mapeia pastas → projetos do OpenProject
    folder_map = map_folders_to_openproject(docs_dir)

    # Load
    documents = load_markdown_docs(docs_dir, folder_map)
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
        model="models/gemini-embedding-001",
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
        default=Path(__file__).parent / "documentacoes_projetos",
        help="Diretório raiz dos documentos Markdown (padrão: ./documentacoes_projetos)",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Limpa a coleção do PgVector antes de reingerir",
    )
    args = parser.parse_args()

    ingest(args.docs_dir, clear=args.clear)

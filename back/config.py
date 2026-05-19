import os
from urllib.parse import quote_plus
from dotenv import load_dotenv

load_dotenv()

POSTGRES_HOST = os.environ.get("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.environ.get("POSTGRES_PORT", "5432")
POSTGRES_DB = os.environ.get("POSTGRES_DB", "postgres")
POSTGRES_USER = os.environ.get("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "")
POSTGRES_SCHEMA = os.environ.get("POSTGRES_SCHEMA", "ticket_maker")


def build_postgres_url(include_search_path: bool = False) -> str:
   
    direct = os.environ.get("POSTGRES_URL")
    if direct:
        base = direct
    else:
        user = quote_plus(POSTGRES_USER)
        password = quote_plus(POSTGRES_PASSWORD)
        base = f"postgresql://{user}:{password}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"

    if include_search_path:
        sep = "&" if "?" in base else "?"
        search_path = quote_plus(f"-csearch_path={POSTGRES_SCHEMA},extensions,public")
        base = f"{base}{sep}options={search_path}"
    return base


POSTGRES_URL = build_postgres_url()


POSTGRES_URL_WITH_SEARCH_PATH = build_postgres_url(include_search_path=True)

# ─────────────────────────────────────────────
# Gemini
# ─────────────────────────────────────────────
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# ─────────────────────────────────────────────
# OpenProject
# ─────────────────────────────────────────────
OPENPROJECT_API_URL = os.environ.get("OPENPROJECT_API_URL", "").rstrip("/")
OPENPROJECT_TOKEN = os.environ.get("OPENPROJECT_TOKEN", "")
OPENPROJECT_TIMEOUT = int(os.environ.get("OPENPROJECT_TIMEOUT", 30))
# Projeto onde TODOS os tickets criados pelo agente devem ser abertos.
OPENPROJECT_SUPPORT_PROJECT_ID = int(os.environ.get("OPENPROJECT_SUPPORT_PROJECT_ID", 21))

# ─────────────────────────────────────────────
# Frontend (CORS)
# ─────────────────────────────────────────────
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:4200")


